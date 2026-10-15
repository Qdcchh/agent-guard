"""Service-owned full PG atomicity, actual process races and recovery controls."""

import json
import os
import signal
from dataclasses import replace

import psycopg
import pytest

from agent_guard.audit.checkpoint import verify_checkpoint
from agent_guard.audit.contracts import (
    CheckpointTrust,
    decode_history_page,
    decode_record_page,
    encode_append_batch,
)
from agent_guard.audit.store import AuditStoreError, register_key, register_stream
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key, sm3_b64url
from tests.fixtures.a31_audit_service import (
    CTX,
    TABLES,
    all_rows,
    foreign_rows,
    observe_prefix,
    receive,
    service_context,
    worker,
)


@pytest.fixture
def audit_service():
    with service_context() as fixture:
        yield fixture


@pytest.fixture(scope="session")
def service_tls(tmp_path_factory):
    from tests.integration.test_audit_tls import service_tls as tls_fixture

    return tls_fixture.__wrapped__(tmp_path_factory)


def body(fixture, start=0, end=2):
    return encode_append_batch(fixture.scope.stream_id, fixture.records[start:end]).exact_body


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize(
    "case", ["duplicate", "gap", "oldrange", "fork", "wrongprev_scope", "partialfault"]
)
def test_atomic_batch_continuity_fork_rejection(audit_service, case, round, monkeypatch):
    f = audit_service
    foreign = foreign_rows()
    assert f.latest() is None
    observe_prefix(f, 0)
    original = f.append(body(f))
    before = all_rows(f)
    assert f.append(body(f)) == original and all_rows(f) == before
    if case == "duplicate":
        observe_prefix(f, 2)
        assert foreign_rows() == foreign
        return
    raw = body(f, 2, 4)
    if case == "gap":
        raw = body(f, 3, 4)
    elif case == "oldrange":
        raw = body(f, 0, 1)
    elif case == "fork":
        value = load_strict_json(f.records[1])
        value["recorded_at"] = "2026-10-09T01:00:00.000001Z"
        raw = encode_append_batch(f.scope.stream_id, (canonical_json_bytes(value),)).exact_body
    elif case == "wrongprev_scope":
        value = load_strict_json(f.records[2])
        value["previous_digest"] = sm3_b64url(b"fork")
        raw = encode_append_batch(f.scope.stream_id, (canonical_json_bytes(value),)).exact_body
    if case == "partialfault":
        import agent_guard.audit.store as module

        def broken(*args, **kwargs):
            raise RuntimeError("private fixture sign failure after real inserts")

        with monkeypatch.context() as patch:
            patch.setattr(module, "sign_checkpoint", broken)
            with pytest.raises(RuntimeError):
                f.append(raw)
        # A real PG uniqueness failure after the first new record also rolls
        # back every independent audit table and does not consume sequence.
        duplicate = load_strict_json(f.records[3])
        duplicate["record_id"] = load_strict_json(f.records[2])["record_id"]
        duplicate["evidence_ref"] = load_strict_json(f.records[2])["evidence_ref"]
        real_fault = encode_append_batch(
            f.scope.stream_id, (f.records[2], canonical_json_bytes(duplicate))
        ).exact_body
        with pytest.raises(psycopg.errors.UniqueViolation) as failure:
            f.append(real_fault)
        assert failure.value.sqlstate == "23505"
    else:
        with pytest.raises(AuditStoreError):
            f.append(raw)
    assert all_rows(f) == before and foreign_rows() == foreign
    observe_prefix(f, 2)


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("case", ["samebatch", "adjacentbatches"])
def test_two_audit_pids_same_batch_original_jws(audit_service, case, round):
    f = audit_service
    before = all_rows(f)
    foreign = foreign_rows()
    barrier = CTX.Barrier(3)
    children = []
    for raw in (body(f), body(f) if case == "samebatch" else body(f, 2, 4)):
        parent, child = CTX.Pipe()
        process = CTX.Process(target=worker, args=(f, raw, child, barrier))
        process.start()
        child.close()
        children.append((process, parent))
    try:
        ready = [receive(pipe) for _, pipe in children]
        assert all(r["phase"] == "ready" for r in ready)
        assert len({r["pid"] for r in ready}) == 2 and len({r["backend"] for r in ready}) == 2
        barrier.wait(timeout=15)
        results = [receive(pipe) for _, pipe in children]
        for process, _ in children:
            process.join(10)
            assert not process.is_alive()
        if case == "samebatch":
            assert all(r["phase"] == "done" for r in results)
            assert results[0]["jws"] == results[1]["jws"]
            assert len({r["backend"] for r in results}) == 2
            assert all(p.exitcode == 0 for p, _ in children)
            state = observe_prefix(f, 2)
            assert len(state["ag_checkpoints"]) == len(state["ag_checkpoint_batches"]) == 1
        else:
            assert results[0]["phase"] == "done"
            assert results[1]["phase"] == "done" or (
                results[1]["phase"] == "error"
                and results[1]["code"] == "RECONCILE_REQUIRED"
                and children[1][0].exitcode != 0
            )
            if results[1]["phase"] == "error":
                f.append(body(f, 2, 4))
            state = observe_prefix(f, 4)
            assert len(state["ag_checkpoints"]) == len(state["ag_checkpoint_batches"]) == 2
        for table in (
            "ag_audit_schema_migrations",
            "ag_audit_checkpoint_keys",
            "ag_audit_principals",
            "ag_test_ownership",
        ):
            assert state[table] == before[table]
        assert foreign_rows() == foreign
    finally:
        for process, pipe in children:
            if process.is_alive():
                process.kill()
                process.join(10)
            pipe.close()


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize(
    "phase", ["presign", "midinsert", "precommit", "postcommit_preresponse", "lostresponse"]
)
def test_audit_sigkill_commit_response_windows(audit_service, service_tls, phase, round):
    f = audit_service
    if phase == "lostresponse":
        return lost_http_response(f, service_tls)
    before = all_rows(f)
    foreign = foreign_rows()
    parent, child = CTX.Pipe()
    process = CTX.Process(target=worker, args=(f, body(f), child, None, phase))
    process.start()
    child.close()
    try:
        event = receive(parent)
        assert event["phase"] == phase and event["pid"] == process.pid and event["backend"] > 0
        process.kill()
        process.join(10)
        assert process.exitcode == -signal.SIGKILL
        committed = phase in ("postcommit_preresponse", "lostresponse")
        if committed:
            old = f.latest()
            persisted = observe_prefix(f, 2)
        else:
            assert all_rows(f) == before
            observe_prefix(f, 0)
            old = None
        # Recovery runs a real new process over the same persistent DB.
        recovery_parent, recovery_child = CTX.Pipe()
        recovery = CTX.Process(target=worker, args=(f, body(f), recovery_child))
        recovery.start()
        recovery_child.close()
        assert recovery.pid != process.pid
        result = receive(recovery_parent)
        recovery.join(10)
        assert result["phase"] == "done" and recovery.exitcode == 0
        if committed:
            assert result["jws"] == old and all_rows(f) == persisted
        observe_prefix(f, 2)
        assert foreign_rows() == foreign
        recovery_parent.close()
    finally:
        if process.is_alive():
            process.kill()
            process.join(10)
        parent.close()


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("case", ["multipage", "appendduringread", "keyrotate", "keyrange"])
def test_checkpoint_history_encoded_pages_rotation(audit_service, case, round):
    f = audit_service
    foreign = foreign_rows()
    store = f.store()
    for entry in f.records[:70]:
        f.append(encode_append_batch(f.scope.stream_id, (entry,)).exact_body, store)
    first = f.latest(store)
    assert f.latest(store) == first
    observed = verify_checkpoint(first, trust=(f.trust,), expected_scope=f.scope)
    pin = observed.claims.checkpoint_id
    baseline = all_rows(f)
    if case in ("keyrotate", "keyrange"):
        key = generate_sm2_private_key()
        trust = CheckpointTrust(
            "audit-2",
            "AUDIT_SIGNER",
            serialize_sm2_public_key(key.public_key()),
            71 if case == "keyrotate" else 72,
            None,
        )
        with psycopg.connect(f.dsn) as conn:
            register_key(conn, trust)
            if case == "keyrotate":
                register_key(conn, replace(f.trust, last_sequence=70))
        from agent_guard.audit.store import AuditStore

        rotated = AuditStore(f.dsn, owner_role=f.owner_role, private_key=key, key_id=trust.kid)
        after_key = all_rows(f)
        if case == "keyrange":
            with pytest.raises(ValueError):
                f.append(body(f, 70, 71), rotated)
            assert all_rows(f) == after_key
        else:
            second = f.append(body(f, 70, 71), rotated)
            seen = verify_checkpoint(second, trust=(f.trust, trust), expected_scope=f.scope)
            assert seen.claims.previous_checkpoint_digest == sm3_b64url(first.encode("ascii"))
            assert set(baseline["ag_checkpoints"]).issubset(set(all_rows(f)["ag_checkpoints"]))
            after_rotation = all_rows(f)
            with pytest.raises(ValueError):
                f.append(body(f, 71, 72), store)
            assert all_rows(f) == after_rotation
    history, entries = [], []
    for is_records in (False, True):
        cursor = 0
        pages = 0
        while True:
            raw = f.page(pin, cursor, records=is_records, store=store)
            assert len(raw) <= 65536
            page = decode_record_page(raw) if is_records else decode_history_page(raw)
            assert page.observed_checkpoint_id == pin and page.observed_sequence == 70
            values = page.entries if is_records else page.checkpoints
            (entries if is_records else history).extend(values)
            pages += 1
            if case == "appendduringread" and pages == 1 and not is_records:
                f.append(body(f, 70, 71), store)
            if page.next_after_sequence is None:
                break
            assert page.next_after_sequence > cursor
            cursor = page.next_after_sequence
        assert pages >= 2
    assert tuple(entries) == f.records[:70]
    assert len(history) == 70 and history[-1] == first
    previous = None
    for jws in history:
        seen = verify_checkpoint(jws, trust=(f.trust,), expected_scope=f.scope)
        assert seen.claims.previous_checkpoint_digest == previous
        previous = seen.jws_digest
    for bad in (True, -1, 70, 71):
        with pytest.raises(ValueError):
            f.page(pin, bad, records=True)
    with pytest.raises(AuditStoreError):
        f.page("missing-pin", 0)
    assert foreign_rows() == foreign


def logical_backup(f):
    """Exact run-owned durable facts exported from an actual committed DB."""
    state = all_rows(f)
    return {table: state[table] for table in TABLES if table != "ag_audit_schema_migrations"}


def restore_backup(target, snapshot):
    """Restore into a new owned empty schema through ordinary immutable inserts."""
    from psycopg import sql

    from tests.fixtures.isolation import assert_owned

    assert_owned(target.namespace)
    # A newly initialized schema has registrations only. Restore into another
    # new owned schema with the same migration; never alter existing facts.
    with psycopg.connect(target.dsn) as conn:
        present = conn.execute("SELECT count(*) FROM ag_checkpoint_streams").fetchone()[0]
        assert present == 0
        for table in (
            "ag_audit_checkpoint_keys",
            "ag_checkpoint_streams",
            "ag_audit_principals",
            "ag_checkpoint_records",
            "ag_checkpoints",
            "ag_checkpoint_batches",
        ):
            for row in snapshot[table]:
                values = list(row)
                if table == "ag_checkpoint_streams":
                    # Defer head FK to checkpoints restored later in same TX.
                    pass
                conn.execute(
                    sql.SQL("INSERT INTO {} VALUES ({})").format(
                        sql.Identifier(table), sql.SQL(",").join(sql.Placeholder() for _ in values)
                    ),
                    values,
                )


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("case", ["lowerseq", "same_seq_fork", "missingpin"])
def test_audit_restore_behind_external_pin_refused(audit_service, case, round):
    from agent_guard.audit.migrate import apply_migrations
    from tests.fixtures.a31_audit_service import ServiceFixture
    from tests.fixtures.isolation import acquire_namespace, assert_owned, release_namespace

    f = audit_service
    foreign = foreign_rows()
    f.append(body(f))
    backup = logical_backup(f)
    f.append(body(f, 2, 4))
    pin = f.latest()
    expected = all_rows(f)
    ns = acquire_namespace(os.environ["AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL"])
    try:
        target = ServiceFixture(
            ns, f.key, f.trust, f.scope, f.records, f.writer, f.reader, f.owner_role
        )
        with psycopg.connect(ns.dsn) as conn:
            apply_migrations(conn, owner_role=f.owner_role)
        if case == "same_seq_fork":
            # Independent branch generated in another actual DB with changed
            # record bytes, leaving the same scope and final sequence.
            with service_context(source=f) as branch:
                altered = list(branch.records)
                for index in range(2, 4):
                    value = load_strict_json(altered[index])
                    if index == 2:
                        value["recorded_at"] = "2026-10-09T00:00:00.000002Z"
                    value["previous_digest"] = sm3_b64url(altered[index - 1])
                    altered[index] = canonical_json_bytes(value)
                branch.records = tuple(altered)
                branch.append(body(branch))
                branch.append(body(branch, 2, 4))
                backup = logical_backup(branch)
        restore_backup(target, backup)
        before = all_rows(target)
        if case == "missingpin":
            store = target.store()
            assert store.external_pins == () and store.rollback_assurance == "UNKNOWN"
            # Honest observer knows only current data, cannot detect rollback.
            assert target.latest(store) != pin
        else:
            with pytest.raises(
                AuditStoreError,
                match="EXTERNAL_PIN_ROLLBACK" if case == "lowerseq" else "EXTERNAL_PIN_FORK",
            ):
                target.store(external_pins=(pin,), external_trust=(f.trust,))
            parent, child = CTX.Pipe()
            restarted = CTX.Process(
                target=worker, args=(target, body(target), child), kwargs={"startup_pins": (pin,)}
            )
            restarted.start()
            child.close()
            try:
                result = receive(parent)
                restarted.join(10)
                assert restarted.pid != os.getpid() and restarted.exitcode == 1
                assert result["phase"] == "error"
                assert result["code"] == (
                    "EXTERNAL_PIN_ROLLBACK" if case == "lowerseq" else "EXTERNAL_PIN_FORK"
                )
            finally:
                if restarted.is_alive():
                    restarted.kill()
                    restarted.join(10)
                parent.close()
        assert all_rows(target) == before
        # Existing scope registration cannot change its stream identity/epoch.
        from agent_guard.audit.contracts import RegistrationDescriptor, genesis_digest
        from tests.fixtures.a31_common import FACTS

        facts = FACTS["BOOTSTRAP"]
        other_scope = replace(f.scope, stream_id="00000000-0000-0000-0000-000000000001")
        descriptor = RegistrationDescriptor(
            other_scope,
            genesis_digest(other_scope),
            facts["manifest_digest"],
            facts["boundary"],
            facts["index_root"],
            1,
            1,
            1,
        )
        with psycopg.connect(ns.dsn) as conn:
            with pytest.raises(AuditStoreError):
                register_stream(conn, descriptor)
        assert all_rows(target) == before and all_rows(f) == expected and foreign_rows() == foreign
    finally:
        assert_owned(ns)
        release_namespace(ns)


def lost_http_response(f, directory):
    import threading

    from tests.fixtures.a31_audit_service import tls_worker
    from tests.integration.test_audit_tls import request

    foreign = foreign_rows()
    import multiprocessing

    from tongsuopy.crypto import serialization

    spawn = multiprocessing.get_context("spawn")
    key_pem = f.key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    child_fixture = replace(f, key=None)
    parent, child = spawn.Pipe()
    process = spawn.Process(
        target=tls_worker,
        args=(child_fixture, directory, child),
        kwargs={"pause_response": True, "key_pem": key_pem},
    )
    process.start()
    child.close()
    failures = []

    def call():
        try:
            request(event["port"], directory, "/v1/audit/append", body(f), credential=f.writer)
        except Exception as exc:
            failures.append(type(exc).__name__)

    try:
        event = receive(parent)
        assert event["phase"] == "ready"
        client = threading.Thread(target=call)
        client.start()
        paused = receive(parent)
        assert paused["phase"] == "lostresponse" and paused["pid"] == process.pid
        original = f.latest()
        before = observe_prefix(f, 2)
        process.kill()
        process.join(10)
        client.join(10)
        assert process.exitcode == -signal.SIGKILL and not client.is_alive() and failures
        restart_parent, restart_child = spawn.Pipe()
        restart = spawn.Process(
            target=tls_worker,
            args=(child_fixture, directory, restart_child),
            kwargs={"key_pem": key_pem},
        )
        restart.start()
        restart_child.close()
        try:
            ready = receive(restart_parent)
            assert ready["pid"] != paused["pid"]
            status, raw = request(
                ready["port"], directory, "/v1/audit/append", body(f), credential=f.writer
            )
            assert status == 200 and json.loads(raw)["checkpoint_jws"] == original
            assert all_rows(f) == before and foreign_rows() == foreign
            restart_parent.send("stop")
            restart.join(10)
            assert restart.exitcode == 0
        finally:
            if restart.is_alive():
                restart.kill()
                restart.join(10)
            restart_parent.close()
    finally:
        if process.is_alive():
            process.kill()
            process.join(10)
        parent.close()


def test_frozen_shared_real_bootstrap_descriptor(audit_service, ledger, dsn, downstream_dsn):
    """Consume the frozen journal's actual manifest digest and committed raw bytes."""
    from agent_guard.audit.journal import describe_pending_tx
    from agent_guard.audit.store import register_principal
    from tests.integration.test_verified_execution import signed_env

    f = audit_service
    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    accepted = env.adapter.accept(bundle)
    with psycopg.connect(dsn) as conn:
        row = conn.execute("SELECT gateway_id,tenant_id,task_id FROM ag_audit_streams").fetchone()
        descriptor = describe_pending_tx(conn, scope_key=tuple(row))
        entries = tuple(
            bytes(row[0])
            for row in conn.execute(
                "SELECT raw FROM ag_audit_records WHERE stream_id=%s ORDER BY seq",
                (descriptor.scope.stream_id,),
            ).fetchall()
        )
    assert len(entries) == 2
    assert descriptor.bootstrap_digest == load_strict_json(entries[0])["facts"]["manifest_digest"]
    assert descriptor.bootstrap_digest != sm3_b64url(entries[0])
    before = foreign_rows()
    with psycopg.connect(f.dsn) as conn:
        register_stream(conn, descriptor)
        register_principal(
            conn,
            credential_id="writer-real",
            credential=f.writer,
            role="WRITER",
            stream_id=descriptor.scope.stream_id,
        )
    raw = encode_append_batch(descriptor.scope.stream_id, entries).exact_body
    jws = f.store().append(raw, credential_id="writer-real", credential=f.writer)
    seen = verify_checkpoint(jws, trust=(f.trust,), expected_scope=descriptor.scope)
    assert seen.claims.sequence == 2 and seen.claims.head_digest == sm3_b64url(entries[-1])
    assert (
        foreign_rows() == before
        and accepted.operation_id == load_strict_json(entries[-1])["operation_id"]
    )
