"""Exact trusted local confirmation after independently committed registration."""

from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict, replace

import psycopg
import pytest

from agent_guard.audit.client import AuditClient
from agent_guard.audit.contracts import CheckpointTrust, genesis_digest
from agent_guard.audit.delivery import (
    DeliveryError,
    DeliveryWorker,
    confirm_registered_tx,
    prepare_pending_tx,
)
from agent_guard.audit.journal import bootstrap_task_tx, describe_pending_tx
from agent_guard.audit.migrate import apply_migrations
from agent_guard.audit.server import create_server
from agent_guard.audit.store import (
    AuditStore,
    AuditStoreError,
    register_key,
    register_principal,
    register_stream,
)
from agent_guard.contracts.encoding import EncodingError
from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key, sm3_b64url
from tests.fixtures.a31_audit_service import record_native
from tests.fixtures.a31_common import state
from tests.fixtures.isolation import acquire_namespace, release_namespace
from tests.integration.test_audit_tls import tls_config
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def registration_tls(tmp_path_factory):
    from tests.integration.test_audit_tls import service_tls

    return service_tls.__wrapped__(tmp_path_factory)


@pytest.fixture
def registration(ledger, dsn, downstream_dsn, registration_tls):
    env = signed_env(dsn, downstream_dsn)
    env.adapter.accept(env.bundle())
    with psycopg.connect(dsn) as conn:
        row = conn.execute("SELECT gateway_id,tenant_id,task_id FROM ag_audit_streams").fetchone()
        descriptor = describe_pending_tx(conn, scope_key=row)
    ns = acquire_namespace(os.environ["AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL"])
    key = generate_sm2_private_key()
    trust = CheckpointTrust(
        "registration-audit", "AUDIT_SIGNER", serialize_sm2_public_key(key.public_key()), 1, None
    )
    writer, reader = secrets.token_urlsafe(36), secrets.token_urlsafe(36)
    with psycopg.connect(ns.dsn) as conn:
        owner = conn.execute("SELECT current_user").fetchone()[0]
        apply_migrations(conn, owner_role=owner)

    class Remote:
        def commit(self, candidate=descriptor, *, fail=False):
            with psycopg.connect(ns.dsn) as conn:
                register_stream(conn, candidate)
                register_key(conn, trust)
                register_principal(
                    conn,
                    credential_id="writer",
                    credential=writer,
                    role="WRITER",
                    stream_id=descriptor.scope.stream_id,
                )
                register_principal(
                    conn,
                    credential_id="reader",
                    credential=reader,
                    role="READER",
                    stream_id=descriptor.scope.stream_id,
                )
                if fail:
                    raise RuntimeError("remote rollback")

        def rows(self):
            with psycopg.connect(ns.dsn) as conn:
                return tuple(
                    conn.execute(
                        "SELECT row_to_json(t)::text FROM " + table + " t ORDER BY 1"
                    ).fetchall()
                    for table in (
                        "ag_checkpoint_streams",
                        "ag_audit_checkpoint_keys",
                        "ag_audit_principals",
                    )
                )

    remote = Remote()
    try:
        yield descriptor, remote, ns, key, trust, writer, reader, owner
    finally:
        release_namespace(ns)


def cursor(dsn):
    with psycopg.connect(dsn) as conn:
        return conn.execute("SELECT * FROM ag_audit_delivery ORDER BY stream_id").fetchall()


def test_registered_confirmation_real_remote_and_delivery(
    registration, dsn, downstream_dsn, registration_tls
):
    descriptor, remote, ns, key, trust, writer, reader, owner = registration
    remote.commit()
    before = state(dsn, downstream_dsn)
    with psycopg.connect(dsn) as conn:
        assert confirm_registered_tx(conn, descriptor=descriptor) is True
    after = state(dsn, downstream_dsn)
    for domain in before:
        for table in before[domain]:
            if table != "ag_audit_delivery":
                assert before[domain][table] == after[domain][table]
    initial = cursor(dsn)
    with psycopg.connect(dsn) as conn:
        assert confirm_registered_tx(conn, descriptor=descriptor) is False
    assert cursor(dsn) == initial
    fixture = type("Fixture", (), {"dsn": ns.dsn, "owner_role": owner, "trust": trust})()
    store = AuditStore(ns.dsn, owner_role=owner, private_key=key, key_id=trust.kid)
    server = create_server(tls_config(fixture, registration_tls), store=store)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        client = AuditClient(
            "https://localhost:" + str(server.server_port),
            ca_file=str(registration_tls / "ca.pem"),
            writer_credential="writer:" + writer,
            reader_credential="reader:" + reader,
        )
        worker = DeliveryWorker(lambda: psycopg.connect(dsn), client, trust=(trust,))
        assert worker.deliver_once(descriptor.scope.stream_id).status == "ACKED"
        acked = cursor(dsn)
        assert acked[0][1] > 0
        remote_acked = remote.rows()
        with psycopg.connect(dsn) as conn:
            assert confirm_registered_tx(conn, descriptor=descriptor) is False
        assert cursor(dsn) == acked
        assert remote.rows() == remote_acked
    finally:
        server.shutdown()
        thread.join(10)
        server.server_close()


def test_registered_confirmation_rejections_zero_write(
    registration, dsn, downstream_dsn, namespace
):
    descriptor, remote, *_ = registration
    remote.commit()
    before = state(dsn, downstream_dsn)
    remote_before = remote.rows()
    other = sm3_b64url(b"different registration")
    candidates = [None, asdict(descriptor)]
    for name in ("genesis_digest", "bootstrap_digest", "index_root"):
        candidates.append(replace(descriptor, **{name: other}))
    for name in ("object_count", "chunk_count", "wire_bytes"):
        candidates.extend(
            [
                replace(descriptor, **{name: 0}),
                replace(descriptor, **{name: getattr(descriptor, name) + 1}),
            ]
        )
    candidates.append(
        replace(
            descriptor,
            boundary="LEGACY_WITH_GAPS" if descriptor.boundary == "NEW_EMPTY" else "NEW_EMPTY",
        )
    )
    for name in ("gateway_id", "tenant_id", "task_id", "stream_id"):
        changed = (
            "https://other.example"
            if name == "gateway_id"
            else "00000000-0000-0000-0000-000000000001"
            if name == "stream_id"
            else "other"
        )
        candidates.append(replace(descriptor, scope=replace(descriptor.scope, **{name: changed})))
        new_scope = replace(descriptor.scope, **{name: changed})
        candidates.append(
            replace(descriptor, scope=new_scope, genesis_digest=genesis_digest(new_scope))
        )
    # Frozen DTOs normally reject booleans/epoch before entering the helper. Probe
    # tampered exact instances as well: the helper must independently revalidate.
    for name in ("object_count", "chunk_count", "wire_bytes"):
        candidate = replace(descriptor)
        object.__setattr__(candidate, name, True)
        candidates.append(candidate)
    candidate = replace(descriptor, scope=replace(descriptor.scope))
    object.__setattr__(candidate.scope, "epoch", 2)
    candidates.append(candidate)
    for candidate in candidates:
        with psycopg.connect(dsn) as conn:
            with pytest.raises((DeliveryError, EncodingError, TypeError)) as rejected:
                confirm_registered_tx(conn, descriptor=candidate)
        after = state(dsn, downstream_dsn)
        assert after == before
        assert remote.rows() == remote_before
        record_native(
            "a33-registration-rejection",
            {
                "case_refs": ["A33-REG-03", "A33-REG-04"],
                "candidate": asdict(candidate) if hasattr(candidate, "scope") else candidate,
                "exception": type(rejected.value).__name__,
                "error": str(rejected.value),
                "before": before,
                "after": after,
                "remote": remote_before,
            },
        )
    with psycopg.connect(dsn) as conn:
        confirm_registered_tx(conn, descriptor=descriptor)
        conn.rollback()
    assert state(dsn, downstream_dsn) == before
    assert remote.rows() == remote_before
    # The production trigger already rejects a direct head corruption. Keep
    # its exact SQLSTATE and unchanged durable state; never disable that guard.
    with pytest.raises(psycopg.errors.CheckViolation) as protected:
        with psycopg.connect(dsn) as conn:
            conn.execute("UPDATE ag_audit_delivery SET ack_head_digest=%s", (other,))
    assert protected.value.sqlstate == "23514"
    record_native(
        "a33-registration-original-cursor-guard",
        {
            "SQLSTATE": protected.value.sqlstate,
            "before": before,
            "after": state(dsn, downstream_dsn),
        },
    )
    assert state(dsn, downstream_dsn) == before
    # A real persisted pending batch is another illegal initial cursor. The
    # transaction remains local and is rolled back after the helper rejects it.
    with psycopg.connect(dsn) as conn:
        assert confirm_registered_tx(conn, descriptor=descriptor) is True
        assert prepare_pending_tx(conn, descriptor.scope.stream_id) is not None
        conn.execute("UPDATE ag_audit_delivery SET registration_state='REGISTRATION_REQUIRED'")
        malformed = conn.execute("SELECT * FROM ag_audit_delivery").fetchall()
        assert malformed[0][4] is not None
        with pytest.raises(DeliveryError, match="initial delivery cursor"):
            confirm_registered_tx(conn, descriptor=descriptor)
        assert conn.execute("SELECT * FROM ag_audit_delivery").fetchall() == malformed
        conn.rollback()
    assert state(dsn, downstream_dsn) == before
    from tests.fixtures.isolation import reset_state

    reset_state(namespace)
    signed_env(dsn, downstream_dsn)
    with psycopg.connect(dsn) as conn:
        uncommitted = bootstrap_task_tx(
            conn, scope_key=("https://gateway.agent-guard.test", "tenant-001", "task-001")
        )
        original = conn.execute("SELECT * FROM ag_audit_delivery").fetchall()
        with pytest.raises(DeliveryError, match="committed local bootstrap"):
            confirm_registered_tx(conn, descriptor=uncommitted)
        assert conn.execute("SELECT * FROM ag_audit_delivery").fetchall() == original
        conn.rollback()
    assert remote.rows() == remote_before


def test_registered_confirmation_crash_recovery(registration, dsn, downstream_dsn, tmp_path):
    descriptor, remote, *_ = registration
    initial = state(dsn, downstream_dsn)
    remote_empty = remote.rows()
    with pytest.raises(RuntimeError, match="remote rollback"):
        remote.commit(fail=True)
    assert remote.rows() == remote_empty
    assert state(dsn, downstream_dsn) == initial
    remote.commit()
    remote_committed = remote.rows()
    with pytest.raises(AuditStoreError, match="REGISTRATION_CONFLICT"):
        remote.commit(replace(descriptor, bootstrap_digest=sm3_b64url(b"conflict")))
    assert remote.rows() == remote_committed
    assert state(dsn, downstream_dsn) == initial
    payload = tmp_path / "descriptor.json"
    payload.write_text(json.dumps(asdict(descriptor)))
    payload.chmod(0o600)
    program = """
import hashlib,json,os,sys,time
from pathlib import Path
import psycopg
from agent_guard.audit.contracts import JournalScope,RegistrationDescriptor
from agent_guard.audit.delivery import confirm_registered_tx
v=json.loads(Path(sys.argv[1]).read_text());v['scope']=JournalScope(**v['scope'])
with psycopg.connect(os.environ['A33_CONFIRM_DSN']) as conn:
 assert confirm_registered_tx(conn,descriptor=RegistrationDescriptor(**v)) is True
 raw=Path('/proc/self/cmdline').read_bytes()
 info={'pid':os.getpid(),'uid':os.getuid(),'start_ticks':Path('/proc/self/stat').read_text().split()[21],'argv_nul_hex':raw.hex(),'argv_sha256':hashlib.sha256(raw).hexdigest()}
 marker=Path(sys.argv[2]);temporary=marker.with_suffix('.pending')
 temporary.write_text(json.dumps(info));os.replace(temporary,marker)
 if sys.argv[3]=='hold':
  while True:time.sleep(.1)
"""
    for round_id in range(10):
        marker = tmp_path / ("operator-" + str(round_id) + ".json")
        child_env = dict(os.environ, A33_CONFIRM_DSN=dsn)
        child = subprocess.Popen(
            [sys.executable, "-c", program, str(payload), str(marker), "hold"],
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 15
            while not marker.exists():
                assert child.poll() is None
                assert time.monotonic() < deadline
                time.sleep(0.01)
            killed = json.loads(marker.read_text())
            assert killed["pid"] == child.pid
            child.kill()
            stdout, stderr = child.communicate(timeout=10)
            assert child.returncode == -signal.SIGKILL
            assert state(dsn, downstream_dsn) == initial
            assert remote.rows() == remote_committed
            new_marker = tmp_path / ("recovery-" + str(round_id) + ".json")
            recovery = subprocess.run(
                [sys.executable, "-c", program, str(payload), str(new_marker), "commit"],
                env=child_env,
                capture_output=True,
                timeout=15,
            )
            assert recovery.returncode == 0, recovery.stderr.decode()
            recovered = json.loads(new_marker.read_text())
            assert recovered["pid"] != killed["pid"]
            record_native(
                "a33-registration-kill-recovery",
                {
                    "round": round_id,
                    "case_refs": ["A33-REG-05", "A33-REG-06"],
                    "killed": killed,
                    "recovered": recovered,
                    "kill_exit": child.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "recovery_exit": recovery.returncode,
                },
            )
            with psycopg.connect(dsn) as conn:
                assert confirm_registered_tx(conn, descriptor=descriptor) is False
            assert remote.rows() == remote_committed
            # Each next independent transaction-death round starts with the same
            # original descriptor/cursor. Test cleanup resets only registration.
            with psycopg.connect(dsn) as conn:
                conn.execute(
                    "UPDATE ag_audit_delivery SET registration_state='REGISTRATION_REQUIRED'"
                )
            assert state(dsn, downstream_dsn) == initial
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
