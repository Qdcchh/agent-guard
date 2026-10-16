"""Real PG, TLS, SM2, dual senders and persistent process-death recovery."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

import psycopg
import pytest

from agent_guard.audit.contracts import decode_append_batch
from agent_guard.audit.delivery import (
    DeliveryWorker,
    ack_pending_tx,
    prepare_pending_tx,
    verify_checkpoint,
)
from agent_guard.contracts.encoding import b64url_encode
from tests.fixtures.a31_common import read_records, state
from tests.fixtures.a31_delivery import SignedTransport, atomic_marker, tls_dir
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


@pytest.fixture
def delivery_env(ledger, dsn, downstream_dsn):
    env = signed_env(dsn, downstream_dsn)
    env.adapter.accept(env.bundle())
    records = read_records(dsn)
    assert len(records) == 2
    transport = SignedTransport(records[0].scope, tls_dir())
    with psycopg.connect(dsn) as conn:
        conn.execute("UPDATE ag_audit_delivery SET registration_state='REGISTERED'")

    def connect():
        conn = psycopg.connect(dsn, connect_timeout=5)
        conn.execute("SET lock_timeout='3s'")
        conn.execute("SET statement_timeout='30s'")
        conn.commit()
        return conn

    worker = DeliveryWorker(connect, transport.client, trust=transport.trust)
    try:
        yield env, transport, worker, records
    finally:
        transport.close()


def unchanged_business(before, after):
    assert set(before) == set(after) == {"gateway", "downstream"}
    assert before["downstream"] == after["downstream"]
    assert set(before["gateway"]) == set(after["gateway"])
    for name in before["gateway"]:
        if name not in ("ag_audit_delivery", "ag_audit_delivery_batches"):
            assert before["gateway"][name] == after["gateway"][name], name


def test_exact_pending_ack_and_no_business_effect(delivery_env, dsn, downstream_dsn):
    _, transport, worker, records = delivery_env
    before = state(dsn, downstream_dsn)
    assert worker.deliver_once(records[0].scope.stream_id).status == "ACKED"
    after = state(dsn, downstream_dsn)
    unchanged_business(before, after)
    with psycopg.connect(dsn) as conn:
        assert conn.execute(
            "SELECT ack_sequence,ack_head_digest,pending_batch_id FROM ag_audit_delivery"
        ).fetchone() == (2, records[-1].digest, None)
        body, jws = conn.execute(
            "SELECT exact_body,checkpoint_jws FROM ag_audit_delivery_batches"
        ).fetchone()
    assert decode_append_batch(bytes(body)).entries == tuple(r.raw for r in records)
    assert (
        verify_checkpoint(
            jws, trust=transport.trust, expected_scope=records[0].scope
        ).claims.sequence
        == 2
    )
    assert worker.deliver_once(records[0].scope.stream_id).status == "NO_PENDING"


@pytest.mark.parametrize("failure", ("unavailable", "redirect", "bad-signature"))
@pytest.mark.parametrize("round", range(10))
def test_failed_response_keeps_immutable_pending(delivery_env, dsn, downstream_dsn, failure, round):
    _, transport, worker, records = delivery_env
    before = state(dsn, downstream_dsn)
    transport.failure = failure
    if failure == "bad-signature":
        with pytest.raises(ValueError):
            worker.deliver_once(records[0].scope.stream_id)
    else:
        assert worker.deliver_once(records[0].scope.stream_id).status == "UNAVAILABLE"
    with psycopg.connect(dsn) as conn:
        pending = prepare_pending_tx(conn, records[0].scope.stream_id)
        assert conn.execute("SELECT ack_sequence FROM ag_audit_delivery").fetchone() == (0,)
    unchanged_business(before, state(dsn, downstream_dsn))
    transport.failure = None
    assert worker.deliver_once(records[0].scope.stream_id).status == "ACKED"
    assert transport.requests[0][1] == transport.requests[-1][1] == pending.exact_body


@pytest.mark.parametrize("round", range(10))
def test_dual_sender_exact_duplicate_and_network_without_locks(delivery_env, dsn, round):
    _, transport, worker, records = delivery_env
    barrier = threading.Barrier(2)
    original = transport.client.append
    observer_mutex = threading.Lock()

    def append(batch):
        barrier.wait(15)
        with observer_mutex, psycopg.connect(dsn) as conn:
            conn.execute("SET LOCAL lock_timeout='1s'")
            conn.execute("SELECT stream_id FROM ag_audit_delivery FOR UPDATE NOWAIT").fetchall()
        barrier.wait(15)
        return original(batch)

    transport.client.append = append
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(worker.deliver_once, records[0].scope.stream_id) for _ in range(2)]
        assert [f.result(30).status for f in futures] == ["ACKED", "ACKED"]
    assert transport.requests[0][1] == transport.requests[1][1]
    with psycopg.connect(transport.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM transport_batches").fetchone() == (1,)


@pytest.mark.parametrize("round", range(10))
def test_late_ack_does_not_clear_new_pending(delivery_env, dsn, round):
    env, transport, worker, records = delivery_env
    sid = records[0].scope.stream_id
    with psycopg.connect(dsn) as conn:
        pending = prepare_pending_tx(conn, sid)
    cp = verify_checkpoint(
        transport.client.append(decode_append_batch(pending.exact_body)),
        trust=transport.trust,
        expected_scope=records[0].scope,
    )
    with psycopg.connect(dsn) as conn:
        assert ack_pending_tx(conn, pending, cp)
    env.adapter.accept(env.bundle())
    with psycopg.connect(dsn) as conn:
        newer = prepare_pending_tx(conn, sid)
    assert newer.start_sequence == 3
    with psycopg.connect(dsn) as conn:
        assert ack_pending_tx(conn, pending, cp)
        assert prepare_pending_tx(conn, sid) == newer
    assert worker.deliver_once(sid).status == "ACKED"


CHILD = r"""
import json,os,time,pathlib,psycopg
from tests.fixtures.a31_delivery import atomic_marker
from agent_guard.audit.client import AuditClient
from agent_guard.audit.contracts import CheckpointTrust
from agent_guard.audit.delivery import DeliveryWorker
import agent_guard.audit.delivery as delivery
from agent_guard.contracts.encoding import b64url_decode
c=json.loads(pathlib.Path(os.environ['DELIVERY_CHILD_CONFIG']).read_text())
def pause(phase):
 if phase==c['phase']:
  atomic_marker(c['marker'], {'pid':os.getpid(),'phase':phase})
  while True:time.sleep(.1)
def connect():return psycopg.connect(c['dsn'],connect_timeout=5)
client=AuditClient(c['origin'],ca_file='/private/ca.pem',writer_credential='writer:DELIVERY_FIXTURE_SECRET_0123456789',reader_credential='reader:DELIVERY_FIXTURE_SECRET_0123456789',timeout=2)
original=client.append
def append(batch):
 pause('before_send');jws=original(batch);pause('after_remote');return jws
client.append=append
ack=delivery.ack_pending_tx
def ack_hook(conn,pending,cp):
 pause('before_ack');result=ack(conn,pending,cp);pause('in_ack');return result
delivery.ack_pending_tx=ack_hook
trust=tuple(CheckpointTrust(k['kid'],k['role'],b64url_decode(k['spki_der']),
 k['first_sequence'],k['last_sequence']) for k in c['trust'])
result=DeliveryWorker(connect,client,trust=trust).deliver_once(c['stream_id'])
pause('after_ack')
assert result.status in ('ACKED','NO_PENDING')
"""


@pytest.mark.parametrize(
    "phase",
    (
        "before_send",
        "remote_commit",
        "after_remote",
        "before_ack",
        "in_ack",
        "after_ack",
    ),
)
@pytest.mark.parametrize("round", range(10))
def test_real_sigkill_new_process_persistent_recovery(
    delivery_env, dsn, downstream_dsn, tmp_path, phase, round
):
    _, transport, worker, records = delivery_env
    marker = tmp_path / "marker.json"
    config = tmp_path / "child.json"
    trust = [{**asdict(k), "spki_der": b64url_encode(k.spki_der)} for k in transport.trust]
    config.write_text(
        json.dumps(
            {
                "dsn": dsn,
                "origin": transport.origin,
                "trust": trust,
                "stream_id": records[0].scope.stream_id,
                "phase": phase,
                "marker": str(marker),
            }
        )
    )
    config.chmod(0o600)
    child_env = os.environ.copy()
    child_env["DELIVERY_CHILD_CONFIG"] = str(config)
    before = state(dsn, downstream_dsn)
    child = subprocess.Popen(
        [sys.executable, "-c", CHILD],
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    release_response = threading.Event()
    if phase == "remote_commit":

        def remote_committed():
            atomic_marker(marker, {"pid": child.pid, "phase": phase})
            assert release_response.wait(15)

        transport.after_commit = remote_committed
    try:
        deadline = time.monotonic() + 30
        while not marker.exists():
            if child.poll() is not None:
                _, error = child.communicate()
                raise AssertionError("child exited before barrier: " + error.decode())
            assert time.monotonic() < deadline, "native child barrier timeout"
            time.sleep(0.02)
        observed = json.loads(marker.read_text())
        assert observed == {"pid": child.pid, "phase": phase}
        os.kill(child.pid, signal.SIGKILL)
        assert child.wait(10) == -signal.SIGKILL
        release_response.set()
        unchanged_business(before, state(dsn, downstream_dsn))
        with psycopg.connect(dsn) as conn:
            pending_before = conn.execute(
                "SELECT exact_body,batch_id FROM ag_audit_delivery_batches"
            ).fetchone()
        cfg = json.loads(config.read_text())
        cfg["phase"] = "none"
        config.write_text(json.dumps(cfg))
        replacement = subprocess.Popen(
            [sys.executable, "-c", CHILD],
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert replacement.pid != child.pid
        _, error = replacement.communicate(timeout=30)
        assert replacement.returncode == 0, error.decode()
        # Each invocation is a new OS process, and the database was never reset.
        with psycopg.connect(dsn) as conn:
            pending_after = conn.execute(
                "SELECT exact_body,batch_id FROM ag_audit_delivery_batches"
            ).fetchone()
            assert pending_after == pending_before
            assert conn.execute(
                "SELECT ack_sequence,pending_batch_id FROM ag_audit_delivery"
            ).fetchone() == (2, None)
        with psycopg.connect(transport.dsn) as conn:
            assert conn.execute("SELECT count(*) FROM transport_batches").fetchone() == (1,)
        unchanged_business(before, state(dsn, downstream_dsn))
    finally:
        release_response.set()
        if child.poll() is None:
            child.kill()
            child.wait(10)
        child.communicate()


@pytest.mark.parametrize("round", range(10))
def test_maximal_encoded_prefix_and_finite_fairness(delivery_env, dsn, downstream_dsn, round):
    env, transport, worker, records = delivery_env
    for _ in range(70):
        env.adapter.accept(env.bundle())
    all_records = read_records(dsn)
    before = state(dsn, downstream_dsn)
    sid = records[0].scope.stream_id
    with psycopg.connect(dsn) as conn:
        pending = prepare_pending_tx(conn, sid)
        assert prepare_pending_tx(conn, sid) == pending
    batch = decode_append_batch(pending.exact_body)
    assert len(batch.exact_body) <= 65536 and len(batch.entries) <= 64
    assert batch.entries == tuple(r.raw for r in all_records[: len(batch.entries)])
    if len(batch.entries) < 64:
        from agent_guard.audit.contracts import encode_append_batch
        from agent_guard.contracts.encoding import EncodingError

        with pytest.raises(EncodingError):
            encode_append_batch(sid, batch.entries + (all_records[len(batch.entries)].raw,))
    outcomes = worker.deliver_round(("missing-stream", sid))
    assert tuple(o.status for o in outcomes) == ("UNAVAILABLE", "ACKED")
    assert outcomes[-1].stream_id == sid
    unchanged_business(before, state(dsn, downstream_dsn))


@pytest.mark.parametrize("mutation", ("sequence", "head", "previous", "stream"))
@pytest.mark.parametrize("round", range(10))
def test_ack_mismatch_has_full_rollback(delivery_env, dsn, downstream_dsn, mutation, round):
    from dataclasses import replace

    from agent_guard.audit.delivery import DeliveryError

    env, transport, worker, records = delivery_env
    sid = records[0].scope.stream_id
    with psycopg.connect(dsn) as conn:
        pending = prepare_pending_tx(conn, sid)
    cp = verify_checkpoint(
        transport.client.append(decode_append_batch(pending.exact_body)),
        trust=transport.trust,
        expected_scope=records[0].scope,
    )
    claims = cp.claims
    if mutation == "sequence":
        claims = replace(claims, sequence=1)
    elif mutation == "head":
        claims = replace(claims, head_digest=records[0].digest)
    elif mutation == "previous":
        claims = replace(claims, previous_checkpoint_digest=records[0].digest)
    else:
        claims = replace(claims, stream_id="other")
    before = state(dsn, downstream_dsn)
    with pytest.raises(DeliveryError), psycopg.connect(dsn) as conn:
        ack_pending_tx(conn, pending, replace(cp, claims=claims))
    assert state(dsn, downstream_dsn) == before


def test_tls_hostname_and_role_refused(delivery_env):
    from agent_guard.audit.client import AuditClient, AuditUnavailable

    _, transport, _, records = delivery_env
    client = AuditClient(
        transport.origin.replace("localhost", "127.0.0.1"),
        ca_file="/private/ca.pem",
        writer_credential="writer:DELIVERY_FIXTURE_SECRET_0123456789",
        reader_credential="reader:DELIVERY_FIXTURE_SECRET_0123456789",
        timeout=2,
    )
    with pytest.raises(AuditUnavailable):
        client.latest(records[0].scope.stream_id)
    client = AuditClient(
        transport.origin,
        ca_file="/private/ca.pem",
        writer_credential="reader:DELIVERY_FIXTURE_SECRET_0123456789",
        reader_credential="reader:DELIVERY_FIXTURE_SECRET_0123456789",
        timeout=2,
    )
    with psycopg.connect(transport.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM transport_batches").fetchone() == (0,)
    from agent_guard.audit.contracts import encode_append_batch

    with pytest.raises(AuditUnavailable):
        client.append(
            encode_append_batch(records[0].scope.stream_id, tuple(r.raw for r in records))
        )


def reconciliation_setup(delivery_env, dsn, *, remote_ahead=False, count=40):
    """Real signed execution records, unmodified SQL guards and bounded exact parent."""
    from agent_guard.audit.contracts import encode_append_batch

    env, transport, worker, records = delivery_env
    for _ in range(count):
        env.adapter.accept(env.bundle())
    records = read_records(dsn)
    sid = records[0].scope.stream_id
    with psycopg.connect(dsn) as conn:
        parent = prepare_pending_tx(conn, sid)
    batch = decode_append_batch(parent.exact_body)
    print(
        "R5_REAL_PARENT_CAPACITY",
        parent.end_sequence,
        len(batch.exact_body),
        len(records),
        [len(r.raw) for r in records[:2]],
    )
    partial = len(batch.entries) // 2
    transport.client.append(encode_append_batch(sid, batch.entries[:partial]))
    if remote_ahead:
        transport.client.append(
            encode_append_batch(
                sid, tuple(r.raw for r in records[partial : parent.end_sequence + 1])
            )
        )
    return transport, worker, records, parent, partial


@pytest.mark.parametrize("case", ("partial", "covered", "aligned", "same_pin"))
@pytest.mark.parametrize("round", range(10))
def test_reconciliation_child_suffix_and_parent_ack(delivery_env, dsn, downstream_dsn, case, round):
    from agent_guard.audit.contracts import encode_append_batch
    from agent_guard.audit.delivery import (
        ack_reconciled_pending_tx,
        prepare_reconciliation_child_tx,
    )

    transport, worker, records, parent, partial = reconciliation_setup(
        delivery_env, dsn, remote_ahead=case in ("covered", "same_pin")
    )
    sid = parent.stream_id
    before = state(dsn, downstream_dsn)
    proof = worker._proof(sid)
    if case == "aligned":
        transport.client.append(
            encode_append_batch(sid, tuple(r.raw for r in records[partial : parent.end_sequence]))
        )
    if case == "partial":
        with psycopg.connect(dsn) as conn:
            child = prepare_reconciliation_child_tx(conn, parent, proof)
            assert prepare_reconciliation_child_tx(conn, parent, proof) == child
            assert prepare_pending_tx(conn, sid) == parent
        assert (child.start_sequence, child.end_sequence) == (
            partial + 1,
            parent.end_sequence,
        )
        assert child.base_checkpoint_digest == proof.prefix.checkpoint_digest
        assert (
            decode_append_batch(child.exact_body).entries
            == decode_append_batch(parent.exact_body).entries[partial:]
        )
        barrier = threading.Lock()
        original = transport.client.append

        def append(batch):
            with barrier, psycopg.connect(dsn) as conn:
                conn.execute("SELECT stream_id FROM ag_audit_delivery FOR UPDATE NOWAIT").fetchall()
            return original(batch)

        transport.client.append = append
    assert worker.deliver_once(sid).status == "ACKED"
    with psycopg.connect(dsn) as conn:
        assert conn.execute(
            "SELECT ack_sequence,ack_head_digest,pending_batch_id FROM ag_audit_delivery"
        ).fetchone() == (parent.end_sequence, parent.end_digest, None)
        row = conn.execute(
            "SELECT exact_body,base_checkpoint_digest,checkpoint_jws "
            "FROM ag_audit_delivery_batches WHERE batch_id=%s",
            (parent.batch_id,),
        ).fetchone()
        assert bytes(row[0]) == parent.exact_body and row[1] == parent.base_checkpoint_digest
        signed = verify_checkpoint(row[2], trust=transport.trust, expected_scope=records[0].scope)
        assert signed.claims.sequence >= parent.end_sequence
        newer = prepare_pending_tx(conn, sid)
    if case == "same_pin":
        # The same CP extends beyond the old parent and covers the next first record.
        next_proof = worker._proof(sid)
        assert next_proof.prefix.checkpoint_jws == proof.prefix.checkpoint_jws
        with psycopg.connect(dsn) as conn:
            next_child = prepare_reconciliation_child_tx(conn, newer, next_proof)
        assert next_child.start_sequence == parent.end_sequence + 2
        assert next_child.end_sequence == newer.end_sequence
    # Late parent proof cannot clear the newer pending; child response isn't parent ACK authority.
    late_proof = worker._proof(sid)
    with psycopg.connect(dsn) as conn:
        assert not ack_reconciled_pending_tx(conn, parent, late_proof)
        assert prepare_pending_tx(conn, sid) == newer
    assert worker.deliver_once(sid).status == "ACKED"
    unchanged_business(before, state(dsn, downstream_dsn))


@pytest.mark.parametrize("failure", ("changed-pin", "missing-page", "bad-record", "bad-history"))
@pytest.mark.parametrize("round", range(10))
def test_reconciliation_reader_failures_preserve_all_state(
    delivery_env, dsn, downstream_dsn, failure, round
):
    transport, worker, records, parent, _ = reconciliation_setup(
        delivery_env, dsn, remote_ahead=True
    )
    before = state(dsn, downstream_dsn)
    transport.failure = failure
    from agent_guard.audit.delivery import DeliveryError

    with pytest.raises((ValueError, DeliveryError)) as rejected:
        worker.deliver_once(parent.stream_id)
    assert not isinstance(rejected.value, (SystemExit, KeyboardInterrupt))
    assert state(dsn, downstream_dsn) == before
    transport.failure = None
    assert worker.deliver_once(parent.stream_id).status == "ACKED"


@pytest.mark.parametrize(
    "mutation", ("base", "body", "id", "stream", "factory", "copy", "rollback", "ackrollback")
)
@pytest.mark.parametrize("round", range(10))
def test_reconciliation_binding_rejection_and_rollback(
    delivery_env, dsn, downstream_dsn, mutation, round
):
    import copy
    from dataclasses import replace

    from agent_guard.audit.delivery import (
        DeliveryError,
        ack_reconciled_pending_tx,
        prepare_reconciliation_child_tx,
    )

    _, worker, _, parent, _ = reconciliation_setup(
        delivery_env,
        dsn,
        count=8,
        remote_ahead=mutation == "ackrollback",
    )
    proof = worker._proof(parent.stream_id)
    before = state(dsn, downstream_dsn)
    if mutation == "base":
        parent = replace(parent, base_checkpoint_digest=parent.end_digest)
    elif mutation == "body":
        parent = replace(parent, exact_body=parent.exact_body + b" ")
    elif mutation == "id":
        parent = replace(parent, batch_id=parent.end_digest)
    elif mutation == "stream":
        parent = replace(parent, stream_id="other")
    elif mutation == "factory":
        proof = replace(proof, local_raw=())
    elif mutation == "copy":
        proof = copy.copy(proof)
    with (
        pytest.raises((DeliveryError, ValueError, RuntimeError)),
        psycopg.connect(dsn) as conn,
    ):
        if mutation == "ackrollback":
            assert ack_reconciled_pending_tx(conn, parent, proof)
            raise RuntimeError("forced rollback after covered parent ACK")
        prepare_reconciliation_child_tx(conn, parent, proof)
        if mutation == "rollback":
            raise RuntimeError("forced rollback after child persisted")
    assert state(dsn, downstream_dsn) == before


@pytest.mark.parametrize("round", range(10))
def test_database_lock_timeout_does_not_starve_healthy_stream(
    delivery_env, dsn, downstream_dsn, round
):
    from tests.fixtures.a31_common import wait_for_blocked

    _, transport, worker, records = delivery_env
    sid = records[0].scope.stream_id
    before = state(dsn, downstream_dsn)
    # The healthy next stream uses a separate owned GW namespace.
    from agent_guard.ledger.lineage import apply_bundle_migrations
    from tests.fixtures.isolation import acquire_namespace, release_namespace

    namespace = acquire_namespace(os.environ["AGENT_GUARD_TEST_DATABASE_URL"])
    healthy = namespace.dsn
    try:
        with psycopg.connect(healthy) as conn:
            apply_bundle_migrations(conn)
        env = signed_env(healthy, downstream_dsn)
        env.adapter.accept(env.bundle())
        healthy_records = read_records(healthy)
        healthy_sid = healthy_records[0].scope.stream_id
        healthy_transport = SignedTransport(healthy_records[0].scope, tls_dir())
        with psycopg.connect(healthy) as conn:
            conn.execute("UPDATE ag_audit_delivery SET registration_state='REGISTERED'")
        first = True

        def connect():
            nonlocal first
            target = dsn if first else healthy
            first = False
            conn = psycopg.connect(target)
            conn.execute("SET lock_timeout='1s'")
            conn.commit()
            return conn

        combined = DeliveryWorker(connect, healthy_transport.client, trust=healthy_transport.trust)
        with (
            psycopg.connect(dsn) as blocker,
            psycopg.connect(dsn, autocommit=True) as observer,
        ):
            blocker.execute("SELECT stream_id FROM ag_audit_delivery FOR UPDATE")
            blocker_pid = blocker.info.backend_pid
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(combined.deliver_round, (sid, healthy_sid))
                blocked = wait_for_blocked(
                    observer,
                    blocker_pid=blocker_pid,
                    table="ag_audit_delivery",
                    futures=(future,),
                )
                outcomes = future.result(15)
            assert [o.status for o in outcomes] == ["UNAVAILABLE", "ACKED"]
            error = combined.database_failures[0]
            assert error[0] == sid and isinstance(error[1], psycopg.errors.LockNotAvailable)
            assert error[2] == "55P03"
            print(
                "R5_REAL_LOCK_TIMEOUT",
                blocker_pid,
                blocked,
                error[2],
                type(error[1]).__name__,
            )
        assert state(dsn, downstream_dsn)["gateway"] == before["gateway"]
        with psycopg.connect(healthy) as conn:
            assert conn.execute(
                "SELECT ack_sequence,pending_batch_id FROM ag_audit_delivery"
            ).fetchone() == (2, None)
        healthy_transport.close()
    finally:
        release_namespace(namespace)


RECONCILIATION_CHILD = r"""
import json,os,time,pathlib,psycopg,hashlib
from tests.fixtures.a31_delivery import atomic_marker
from agent_guard.audit.client import AuditClient
from agent_guard.audit.contracts import CheckpointTrust
from agent_guard.audit.delivery import DeliveryWorker
import agent_guard.audit.delivery as delivery
from agent_guard.contracts.encoding import b64url_decode
c=json.loads(pathlib.Path(os.environ['DELIVERY_CHILD_CONFIG']).read_text())
def pause(phase):
 if phase==c['phase']:
  identity={'pid':os.getpid(),'uid':os.getuid(),'kernel_start':pathlib.Path('/proc/self/stat').read_text().split()[21],
   'argv_sha256':hashlib.sha256(pathlib.Path('/proc/self/cmdline').read_bytes()).hexdigest(),'phase':phase}
  atomic_marker(c['marker'], identity)
  while True:time.sleep(.1)
def connect():return psycopg.connect(c['dsn'],connect_timeout=5)
client=AuditClient(c['origin'],ca_file='/private/ca.pem',writer_credential='writer:DELIVERY_FIXTURE_SECRET_0123456789',reader_credential='reader:DELIVERY_FIXTURE_SECRET_0123456789',timeout=2)
original=client.append
def append(batch):
 if batch.start_sequence>1:
  pause('child_saved');pause('pre_child_send')
 jws=original(batch)
 if batch.start_sequence>1:pause('child_response_before_parent_ack')
 return jws
client.append=append
ack=delivery.ack_reconciled_pending_tx
def ack_hook(conn,parent,proof):
 pause('pre_parent_ack');return ack(conn,parent,proof)
delivery.ack_reconciled_pending_tx=ack_hook
trust=tuple(CheckpointTrust(k['kid'],k['role'],b64url_decode(k['spki_der']),
 k['first_sequence'],k['last_sequence']) for k in c['trust'])
result=DeliveryWorker(connect,client,trust=trust).deliver_once(c['stream_id'])
pause('post_parent_ack')
assert result.status in ('ACKED','NO_PENDING')
print(json.dumps({'pid':os.getpid(),'uid':os.getuid(),'kernel_start':pathlib.Path('/proc/self/stat').read_text().split()[21],
 'argv_sha256':hashlib.sha256(pathlib.Path('/proc/self/cmdline').read_bytes()).hexdigest(),'status':result.status}))
"""


@pytest.mark.parametrize(
    "phase",
    (
        "child_saved",
        "pre_child_send",
        "remote_child_commit_lost_response",
        "child_response_before_parent_ack",
        "pre_parent_ack",
        "post_parent_ack",
    ),
)
@pytest.mark.parametrize("round", range(10))
def test_reconciliation_child_sigkill_recovery(
    delivery_env, dsn, downstream_dsn, tmp_path, phase, round
):
    from agent_guard.audit.contracts import encode_append_batch

    env, transport, worker, records = delivery_env
    for _ in range(8):
        env.adapter.accept(env.bundle())
    records = read_records(dsn)
    sid = records[0].scope.stream_id
    with psycopg.connect(dsn) as conn:
        parent = prepare_pending_tx(conn, sid)
    partial = parent.end_sequence // 2
    transport.client.append(encode_append_batch(sid, tuple(r.raw for r in records[:partial])))
    before = state(dsn, downstream_dsn)
    marker, config = tmp_path / "r5-marker.json", tmp_path / "r5-child.json"
    cfg = {
        "dsn": dsn,
        "origin": transport.origin,
        "trust": [{**asdict(k), "spki_der": b64url_encode(k.spki_der)} for k in transport.trust],
        "stream_id": sid,
        "phase": phase,
        "marker": str(marker),
    }
    config.write_text(json.dumps(cfg))
    config.chmod(0o600)
    child_env = {**os.environ, "DELIVERY_CHILD_CONFIG": str(config)}
    child = subprocess.Popen(
        [sys.executable, "-c", RECONCILIATION_CHILD],
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    released = threading.Event()
    if phase == "remote_child_commit_lost_response":

        def committed():
            info = {
                "pid": child.pid,
                "uid": os.stat("/proc/" + str(child.pid)).st_uid,
                "kernel_start": open("/proc/" + str(child.pid) + "/stat").read().split()[21],
                "argv_sha256": __import__("hashlib")
                .sha256(open("/proc/" + str(child.pid) + "/cmdline", "rb").read())
                .hexdigest(),
                "phase": phase,
            }
            atomic_marker(marker, info)
            assert released.wait(20)

        transport.after_commit = committed
    try:
        deadline = time.monotonic() + 30
        while not marker.exists():
            if child.poll() is not None:
                _, error = child.communicate()
                raise AssertionError(
                    "reconciliation child exited before barrier: " + error.decode()
                )
            assert time.monotonic() < deadline
            time.sleep(0.01)
        identity = json.loads(marker.read_text())
        assert identity["pid"] == child.pid and identity["uid"] == os.getuid()
        assert identity["phase"] == phase and identity["kernel_start"].isdigit()
        assert len(identity["argv_sha256"]) == 64
        with psycopg.connect(dsn) as conn:
            child_before = conn.execute(
                "SELECT batch_id,exact_body,start_sequence,end_sequence,base_checkpoint_digest "
                "FROM ag_audit_delivery_batches WHERE batch_id<>%s",
                (parent.batch_id,),
            ).fetchone()
            assert child_before is not None
            assert (
                bytes(child_before[1])
                == encode_append_batch(
                    sid, tuple(r.raw for r in records[partial : parent.end_sequence])
                ).exact_body
            )
        os.kill(child.pid, signal.SIGKILL)
        assert child.wait(10) == -signal.SIGKILL
        released.set()
        transport.after_commit = None
        unchanged_business(before, state(dsn, downstream_dsn))
        cfg["phase"] = "none"
        config.write_text(json.dumps(cfg))
        replacement = subprocess.Popen(
            [sys.executable, "-c", RECONCILIATION_CHILD],
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        output, error = replacement.communicate(timeout=30)
        assert replacement.returncode == 0, error.decode()
        new_identity = json.loads(output)
        assert new_identity["pid"] == replacement.pid != identity["pid"]
        assert new_identity["uid"] == identity["uid"]
        assert (
            new_identity["kernel_start"] != identity["kernel_start"] or replacement.pid != child.pid
        )
        print(
            "R5_NATIVE_RECOVERY",
            json.dumps(
                {
                    "killed": identity,
                    "killed_exit": -9,
                    "replacement": new_identity,
                    "replacement_exit": replacement.returncode,
                }
            ),
        )
        with psycopg.connect(dsn) as conn:
            assert (
                conn.execute(
                    "SELECT batch_id,exact_body,start_sequence,end_sequence,"
                    "base_checkpoint_digest FROM ag_audit_delivery_batches WHERE batch_id<>%s",
                    (parent.batch_id,),
                ).fetchone()
                == child_before
            )
            assert conn.execute(
                "SELECT ack_sequence,ack_head_digest,pending_batch_id FROM ag_audit_delivery"
            ).fetchone() == (parent.end_sequence, parent.end_digest, None)
            assert prepare_pending_tx(conn, sid) is None
        with psycopg.connect(transport.dsn) as conn:
            assert conn.execute("SELECT count(*) FROM transport_batches").fetchone() == (2,)
        assert transport.requests[-1][0] != "/v1/audit/append" or transport.requests[-1][1] in (
            parent.exact_body,
            bytes(child_before[1]),
        )
        unchanged_business(before, state(dsn, downstream_dsn))
        print("R5_FULL_STATE", repr(state(dsn, downstream_dsn)))
    finally:
        released.set()
        transport.after_commit = None
        if child.poll() is None:
            child.kill()
            child.wait(10)
        child.communicate()


@pytest.mark.parametrize("field", ("body", "start", "end", "digest", "base", "completion"))
@pytest.mark.parametrize("round", range(10))
def test_reconciliation_child_field_collisions(delivery_env, dsn, downstream_dsn, field, round):
    from agent_guard.audit.contracts import encode_append_batch
    from agent_guard.audit.delivery import DeliveryError, prepare_reconciliation_child_tx

    transport, worker, records, parent, partial = reconciliation_setup(delivery_env, dsn, count=8)
    proof = worker._proof(parent.stream_id)
    child = encode_append_batch(
        parent.stream_id, decode_append_batch(parent.exact_body).entries[partial:]
    )
    values = [
        child.stream_id,
        child.batch_id,
        child.exact_body,
        child.start_sequence,
        child.end_sequence,
        child.end_digest,
        proof.prefix.checkpoint_digest,
    ]
    if field == "body":
        values[2] = parent.exact_body
    elif field == "start":
        values[3] += 1
    elif field == "end":
        values[4] -= 1  # Existing FK target, wrong immutable end relative to exact body.
    elif field == "digest":
        values[5] = records[0].digest
    elif field == "base":
        values[6] = records[0].digest
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO ag_audit_delivery_batches(stream_id,batch_id,exact_body,"
            "start_sequence,end_sequence,end_digest,base_checkpoint_digest) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            values,
        )
        if field == "completion":
            conn.execute(
                "UPDATE ag_audit_delivery_batches SET checkpoint_jws=%s,"
                "ack_at=clock_timestamp() WHERE batch_id=%s",
                (proof.prefix.checkpoint_jws, child.batch_id),
            )
    before = state(dsn, downstream_dsn)
    with pytest.raises((DeliveryError, ValueError)), psycopg.connect(dsn) as conn:
        prepare_reconciliation_child_tx(conn, parent, proof)
    assert state(dsn, downstream_dsn) == before


@pytest.mark.parametrize("round", range(10))
def test_reconciliation_dual_senders_and_late_child(delivery_env, dsn, downstream_dsn, round):
    from agent_guard.audit.delivery import DeliveryError, ack_pending_tx

    transport, worker, records, parent, partial = reconciliation_setup(delivery_env, dsn)
    barrier = threading.Barrier(2)
    original = transport.client.append
    bodies = []
    observer_mutex = threading.Lock()

    def append(batch):
        if batch.start_sequence > 1:
            barrier.wait(20)
            with observer_mutex, psycopg.connect(dsn) as conn:
                conn.execute("SELECT stream_id FROM ag_audit_delivery FOR UPDATE NOWAIT")
            bodies.append(batch.exact_body)
            barrier.wait(20)
        return original(batch)

    transport.client.append = append
    before = state(dsn, downstream_dsn)
    with ThreadPoolExecutor(2) as pool:
        results = [pool.submit(worker.deliver_once, parent.stream_id) for _ in range(2)]
        statuses = [r.result(30).status for r in results]
    assert statuses.count("ACKED") >= 1
    assert set(statuses) <= {"ACKED", "RECONCILE_REQUIRED"}
    assert len(bodies) == 2 and bodies[0] == bodies[1]
    with psycopg.connect(dsn) as conn:
        newer = prepare_pending_tx(conn, parent.stream_id)
    cp = verify_checkpoint(
        original(decode_append_batch(bodies[0])),
        trust=transport.trust,
        expected_scope=records[0].scope,
    )
    current = state(dsn, downstream_dsn)
    with pytest.raises(DeliveryError), psycopg.connect(dsn) as conn:
        ack_pending_tx(conn, parent, cp)
    assert state(dsn, downstream_dsn) == current
    with psycopg.connect(dsn) as conn:
        assert prepare_pending_tx(conn, parent.stream_id) == newer
    unchanged_business(before, current)
