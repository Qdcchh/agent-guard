"""Service-owned native PG/process/TLS harness; never imports delivery."""

from __future__ import annotations

import json
import multiprocessing
import os
import secrets
import time
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from agent_guard.audit.contracts import (
    CheckpointTrust,
    JournalScope,
    RegistrationDescriptor,
    genesis_digest,
    scope_object,
)
from agent_guard.audit.migrate import apply_migrations
from agent_guard.audit.store import AuditStore, register_key, register_principal, register_stream
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key, sm3_b64url
from tests.fixtures.a31_common import FACTS, STAMP
from tests.fixtures.isolation import acquire_namespace, assert_owned, release_namespace

TABLES = (
    "ag_audit_schema_migrations",
    "ag_checkpoint_streams",
    "ag_checkpoint_records",
    "ag_audit_checkpoint_keys",
    "ag_checkpoints",
    "ag_checkpoint_batches",
    "ag_audit_principals",
)
CTX = multiprocessing.get_context("fork")


def record_native(kind, value):
    """Optional test-only private evidence, with unique files and no stdout."""
    parent = os.environ.get("AG31_SERVICE_EVIDENCE_DIR")
    if parent is None:
        return
    directory = Path(parent)
    if not directory.is_absolute():
        raise AssertionError("absolute private native evidence directory required")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    assert directory.is_dir() and not directory.is_symlink()
    assert info.st_uid == os.getuid() and info.st_mode & 0o077 == 0

    def encode(item):
        if isinstance(item, (bytes, memoryview)):
            return {"raw_hex": bytes(item).hex()}
        if isinstance(item, dict):
            return {str(k): encode(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [encode(v) for v in item]
        if hasattr(item, "isoformat"):
            return item.isoformat()
        return item

    path = directory / (kind + "-" + str(os.getpid()) + "-" + str(time.time_ns()) + ".json")
    with path.open("x") as output:
        json.dump(encode(value), output, sort_keys=True)
    path.chmod(0o600)


@dataclass
class ServiceFixture:
    namespace: object = field(repr=False)
    key: object = field(repr=False)
    trust: CheckpointTrust
    scope: JournalScope
    records: tuple[bytes, ...]
    writer: str = field(repr=False)
    reader: str = field(repr=False)
    owner_role: str

    @property
    def dsn(self):
        return self.namespace.dsn

    def store(self, **extra):
        assert_owned(self.namespace)
        return AuditStore(
            self.dsn,
            owner_role=self.owner_role,
            private_key=self.key,
            key_id=self.trust.kid,
            **extra,
        )

    def append(self, raw, store=None):
        return (store or self.store()).append(raw, credential_id="writer", credential=self.writer)

    def latest(self, store=None):
        return (store or self.store()).latest(
            self.scope.stream_id, credential_id="reader", credential=self.reader
        )

    def page(self, pin, after, *, records=False, store=None):
        return (store or self.store()).page(
            self.scope.stream_id,
            observed_checkpoint_id=pin,
            after_sequence=after,
            credential_id="reader",
            credential=self.reader,
            records=records,
        )


def records(scope, count=150):
    result = []
    previous = genesis_digest(scope)
    for seq in range(1, count + 1):
        kind = "BOOTSTRAP" if seq == 1 else "QUERY"
        raw = canonical_json_bytes(
            {
                **scope_object(scope),
                "seq": seq,
                "record_id": "BOOTSTRAP:" + scope.stream_id
                if seq == 1
                else "QUERY:query-" + str(seq),
                "kind": kind,
                "operation_id": None if seq == 1 else "op",
                "evidence_ref": None if seq == 1 else "query-" + str(seq),
                "previous_digest": previous,
                "recorded_at": STAMP,
                "facts": FACTS[kind],
            }
        )
        previous = sm3_b64url(raw)
        result.append(raw)
    return tuple(result)


@contextmanager
def service_context(*, source=None, sequence=0):
    base = os.environ.get("AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL")
    if not base:
        pytest.fail("independent audit test DSN required; no skip")
    ns = acquire_namespace(base)
    try:
        with psycopg.connect(ns.dsn) as conn:
            role = conn.execute("SELECT current_user").fetchone()[0]
            apply_migrations(conn, owner_role=role)
        if source:
            fixture = ServiceFixture(
                ns,
                source.key,
                source.trust,
                source.scope,
                source.records,
                source.writer,
                source.reader,
                role,
            )
        else:
            key = generate_sm2_private_key()
            scope = JournalScope(
                "https://gateway.agent-guard.test", "tenant", "task", str(uuid.uuid4()), 1
            )
            fixture = ServiceFixture(
                ns,
                key,
                CheckpointTrust(
                    "audit-1", "AUDIT_SIGNER", serialize_sm2_public_key(key.public_key()), 1, None
                ),
                scope,
                records(scope),
                secrets.token_urlsafe(36),
                secrets.token_urlsafe(36),
                role,
            )
        facts = FACTS["BOOTSTRAP"]
        descriptor = RegistrationDescriptor(
            fixture.scope,
            genesis_digest(fixture.scope),
            facts["manifest_digest"],
            facts["boundary"],
            facts["index_root"],
            facts["object_count"],
            facts["chunk_count"],
            facts["wire_bytes"],
        )
        with psycopg.connect(ns.dsn) as conn:
            register_key(conn, fixture.trust)
            register_stream(conn, descriptor)
            register_principal(
                conn,
                credential_id="writer",
                credential=fixture.writer,
                role="WRITER",
                stream_id=fixture.scope.stream_id,
            )
            register_principal(
                conn,
                credential_id="reader",
                credential=fixture.reader,
                role="READER",
                stream_id=fixture.scope.stream_id,
            )
        if sequence:
            from agent_guard.audit.contracts import encode_append_batch

            for entry in fixture.records[:sequence]:
                fixture.append(encode_append_batch(fixture.scope.stream_id, (entry,)).exact_body)
        yield fixture
    finally:
        assert_owned(ns)
        release_namespace(ns)


@pytest.fixture
def audit_service():
    with service_context() as fixture:
        yield fixture


def all_rows(fixture):
    assert_owned(fixture.namespace)
    with psycopg.connect(fixture.dsn) as conn:
        found = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname=current_schema()"
            " AND tablename LIKE 'ag_%' ORDER BY tablename"
        ).fetchall()
        assert {r[0] for r in found} == {*TABLES, "ag_test_ownership"}
        result = {}
        for table in (*TABLES, "ag_test_ownership"):
            rows = conn.execute(
                sql.SQL("SELECT * FROM {} ORDER BY to_jsonb({})::text").format(
                    sql.Identifier(table), sql.Identifier(table)
                )
            ).fetchall()
            result[table] = tuple(
                tuple(bytes(v) if isinstance(v, memoryview) else v for v in row) for row in rows
            )
        record_native("audit-all-rows", result)
        return result


def foreign_rows():
    """Observe all non-audit domains without importing delivery implementations."""
    result = {}
    for key in ("AGENT_GUARD_TEST_DATABASE_URL", "AGENT_GUARD_A31_TEST_DOWNSTREAM_DATABASE_URL"):
        dsn = os.environ[key]
        with psycopg.connect(dsn) as conn:
            tables = conn.execute(
                "SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT I"
                "N ('pg_catalog','information_schema') ORDER BY 1,2"
            ).fetchall()
            for schema, table in tables:
                rows = conn.execute(
                    sql.SQL("SELECT * FROM {}.{} ORDER BY to_jsonb({})::text").format(
                        sql.Identifier(schema), sql.Identifier(table), sql.Identifier(table)
                    )
                ).fetchall()
                result[(key, schema, table)] = rows
    record_native("foreign-all-rows", result)
    return result


def observe_prefix(fixture, count):
    from agent_guard.audit.checkpoint import verify_checkpoint
    from agent_guard.audit.contracts import decode_journal_record

    state = all_rows(fixture)
    stored = state["ag_checkpoint_records"]
    assert len(stored) == count
    for index, row in enumerate(sorted(stored, key=lambda r: r[1])):
        record = decode_journal_record(bytes(row[2]))
        assert row == (
            fixture.scope.stream_id,
            index + 1,
            fixture.records[index],
            record.digest,
            record.previous_digest,
            record.record_id,
        )
    stream = state["ag_checkpoint_streams"][0]
    assert stream[9] == count
    if count:
        jws = fixture.latest()
        observed = verify_checkpoint(jws, trust=(fixture.trust,), expected_scope=fixture.scope)
        assert observed.claims.sequence == count
        assert observed.claims.head_digest == sm3_b64url(fixture.records[count - 1])
        assert (
            stream[10] == observed.claims.head_digest
            and stream[11] == observed.claims.checkpoint_id
        )
        checkpoints = sorted(state["ag_checkpoints"], key=lambda r: r[2])
        previous = None
        for checkpoint in checkpoints:
            seen = verify_checkpoint(
                checkpoint[7], trust=(fixture.trust,), expected_scope=fixture.scope
            )
            assert seen.jws_digest == checkpoint[8]
            assert seen.claims.previous_checkpoint_digest == previous
            assert seen.claims.head_digest == sm3_b64url(fixture.records[seen.claims.sequence - 1])
            previous = seen.jws_digest
        for batch in state["ag_checkpoint_batches"]:
            from agent_guard.audit.contracts import decode_append_batch

            decoded = decode_append_batch(bytes(batch[2]))
            assert (batch[0], batch[1], batch[3], batch[4], batch[5]) == (
                decoded.stream_id,
                decoded.batch_id,
                decoded.start_sequence,
                decoded.end_sequence,
                decoded.end_digest,
            )
            assert any(cp[0] == batch[6] and cp[2] == batch[4] for cp in checkpoints)
    else:
        assert fixture.latest() is None
        assert not state["ag_checkpoints"] and not state["ag_checkpoint_batches"]
    return state


def worker(fixture, body, pipe, barrier=None, phase=None, startup_pins=()):
    """Native process fixture intercepts actual SQL boundaries, no product hooks."""
    try:
        store = fixture.store(
            external_pins=startup_pins, external_trust=(fixture.trust,) if startup_pins else ()
        )
        original_connect = store.connect
        backend = None
        if phase in ("presign",):
            import agent_guard.audit.store as module

            original_sign = module.sign_checkpoint

            def paused(*args, **kwargs):
                pipe.send({"phase": phase, "pid": os.getpid(), "backend": backend})
                assert pipe.recv() == "continue"
                return original_sign(*args, **kwargs)

            module.sign_checkpoint = paused

        class ConnectionProxy:
            def __init__(self, conn):
                self.conn = conn
                self.inserted = 0

            def __enter__(self):
                nonlocal backend
                self.conn.__enter__()
                backend = self.conn.execute("SELECT pg_backend_pid()").fetchone()[0]
                return self

            def __exit__(self, *args):
                result = self.conn.__exit__(*args)
                if phase in ("postcommit_preresponse", "lostresponse") and args[0] is None:
                    pipe.send({"phase": phase, "pid": os.getpid(), "backend": backend})
                    assert pipe.recv() == "continue"
                return result

            @contextmanager
            def transaction(self):
                with self.conn.transaction():
                    yield
                    if phase == "precommit":
                        pipe.send({"phase": phase, "pid": os.getpid(), "backend": backend})
                        assert pipe.recv() == "continue"

            def execute(self, query, params=None):
                result = self.conn.execute(query, params)
                if isinstance(query, str) and query.startswith("INSERT INTO ag_checkpoint_records"):
                    self.inserted += 1
                    if self.inserted == 1 and phase == "midinsert":
                        pipe.send({"phase": phase, "pid": os.getpid(), "backend": backend})
                        assert pipe.recv() == "continue"
                return result

        store.connect = lambda: ConnectionProxy(original_connect())
        if barrier is not None:
            with original_connect() as conn:
                backend = conn.execute("SELECT pg_backend_pid()").fetchone()[0]
            pipe.send({"phase": "ready", "pid": os.getpid(), "backend": backend})
            barrier.wait(timeout=15)
        jws = fixture.append(body, store=store)
        pipe.send({"phase": "done", "pid": os.getpid(), "backend": backend, "jws": jws})
    except Exception as exc:
        pipe.send(
            {
                "phase": "error",
                "pid": os.getpid(),
                "type": type(exc).__name__,
                "code": getattr(exc, "code", None),
                "sqlstate": getattr(exc, "sqlstate", None),
                "traceback": traceback.format_exc(),
            }
        )
        raise
    finally:
        pipe.close()


def receive(pipe):
    assert pipe.poll(20), "finite child observation deadline"
    result = pipe.recv()
    record_native("native-child", result)
    return result


def private_json(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_bytes(canonical_json_bytes(value))
    path.chmod(0o600)
    return path


def tls_worker(fixture, directory, pipe, *, pause_response=False, key_pem=None):
    """Actual HTTPS lost-response fixture with interception after durable append."""
    import threading

    from agent_guard.audit.config import AuditConfig
    from agent_guard.audit.http_app import AuditHTTPApp
    from agent_guard.audit.server import create_server

    directory = Path(directory)
    if key_pem is not None:
        from tongsuopy.crypto import serialization

        fixture.key = serialization.load_pem_private_key(key_pem, password=None)
    if pause_response:
        dispatch = AuditHTTPApp.dispatch

        def intercept(self, *args, **kwargs):
            result = dispatch(self, *args, **kwargs)
            if args[1] == "/v1/audit/append" and result[0] == 200:
                pipe.send({"phase": "lostresponse", "pid": os.getpid()})
                # Finite private barrier before actual socket response.
                assert pipe.poll(30) and pipe.recv() == "continue"
            return result

        AuditHTTPApp.dispatch = intercept
    server = create_server(
        AuditConfig(
            fixture.dsn,
            fixture.owner_role,
            fixture.trust.kid,
            directory / "unused.key",
            directory / "server.pem",
            directory / "server.key",
            "127.0.0.1",
            0,
            (),
            (),
        ),
        store=fixture.store(),
    )
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.start()
    try:
        pipe.send({"phase": "ready", "pid": os.getpid(), "port": server.server_address[1]})
        assert pipe.poll(40) and pipe.recv() == "stop"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(10)
        pipe.close()
