"""Frozen S0 fixtures: codec-only bytes and real signed gateway/PG helpers."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import psycopg

from agent_guard.audit.contracts import JournalScope, genesis_digest, scope_object
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.crypto.sm import sm3_b64url
from tests.fixtures.receipts import full_state

SCOPE = JournalScope(
    "https://gateway.agent-guard.test",
    "tenant-codec",
    "task-codec",
    "ef8b83d2-fb3d-45c8-b711-2cf78025baf8",
    1,
)
STAMP = "2026-10-09T00:00:00.000001Z"
DIGEST = sm3_b64url(b"CODEC_ONLY_SYNTHETIC_MATERIAL")
FACTS = {
    "BOOTSTRAP": {
        "boundary": "NEW_EMPTY",
        "root_grant_id": "root",
        "snapshot_as_of": STAMP,
        "schema_lineage_digest": DIGEST,
        "index_root": DIGEST,
        "manifest_digest": DIGEST,
        "object_count": 1,
        "chunk_count": 1,
        "wire_bytes": 1,
    },
    "FIRST": {
        "root_grant_id": "root",
        "grant_id": "leaf",
        "path_ids": ["root", "mid", "leaf"],
        "intent_digest": DIGEST,
        "token_digest": DIGEST,
        "proof_digest": DIGEST,
        "body_digest": DIGEST,
        "context_digest": DIGEST,
        "source_digest": DIGEST,
        "source_material_digest": DIGEST,
        "reserve_digest": DIGEST,
        "quote_digest": None,
        "amount_fen": 1,
        "calls": 1,
        "currency": "CNY",
        "introduced_grants": [],
    },
    "RETRY": {
        "first_evidence_ref": "first",
        "intent_digest": DIGEST,
        "token_digest": DIGEST,
        "proof_digest": DIGEST,
        "body_digest": DIGEST,
        "context_digest": DIGEST,
        "source_digest": DIGEST,
        "source_material_digest": DIGEST,
        "response_kind": "ACCEPT_RESULT",
        "response_digest": DIGEST,
        "status": "RESERVED",
        "receipt_status": "PENDING",
        "receipt_jws_digest": None,
    },
    "QUERY": {
        "first_evidence_ref": "first",
        "token_digest": DIGEST,
        "proof_digest": DIGEST,
        "body_digest": DIGEST,
        "context_digest": DIGEST,
        "source_digest": DIGEST,
        "source_material_digest": DIGEST,
        "response_digest": DIGEST,
        "status": "RESERVED",
        "receipt_status": "PENDING",
        "result_digest": None,
        "receipt_jws_digest": None,
    },
    "TERMINAL": {
        "first_evidence_ref": "first",
        "status": "SUCCEEDED",
        "action": "SETTLE",
        "result_digest": DIGEST,
        "ledger_digest": DIGEST,
        "pending_receipt_digest": DIGEST,
        "receipt_id": "receipt",
        "owner_token": "owner",
        "fencing_version": 1,
        "lease_expires_at": STAMP,
        "path_ids": ["root", "mid", "leaf"],
    },
    "PUBLISH": {
        "receipt_id": "receipt",
        "receipt_jws_digest": DIGEST,
        "signed_at": STAMP,
    },
}


def codec_record(kind="BOOTSTRAP", *, seq=None, previous=None, scope=SCOPE) -> bytes:
    """Strict wire test vector; never passed off as real business/signature."""
    suffix = (
        scope.stream_id
        if kind == "BOOTSTRAP"
        else "current"
        if kind in ("RETRY", "QUERY")
        else "receipt"
        if kind == "PUBLISH"
        else "op"
    )
    return canonical_json_bytes(
        {
            **scope_object(scope),
            "seq": seq or (1 if kind == "BOOTSTRAP" else 2),
            "record_id": kind + ":" + suffix,
            "kind": kind,
            "operation_id": None if kind == "BOOTSTRAP" else "op",
            "evidence_ref": None
            if kind == "BOOTSTRAP"
            else "current"
            if kind in ("RETRY", "QUERY")
            else "first",
            "previous_digest": previous or genesis_digest(scope),
            "recorded_at": STAMP,
            "facts": FACTS[kind],
        }
    )


def read_records(dsn):
    namespace_evidence(dsn)
    from agent_guard.audit.contracts import decode_journal_record

    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT raw,digest,created_xid FROM ag_audit_records ORDER BY stream_id,seq"
        ).fetchall()
    result = []
    for raw, digest, xid in rows:
        record = decode_journal_record(bytes(raw))
        assert record.digest == digest and type(xid) is str and xid.isdigit()
        result.append(record)
    return tuple(result)


def wait_for_blocked(observer, *, blocker_pid, table, timeout=15, futures=(), advisory_key=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for future in futures:
            if future.done():
                future.result()
                raise AssertionError("worker completed before required real dependency wait")
        rows = observer.execute(
            "SELECT pid FROM pg_stat_activity WHERE %s=ANY(pg_blocking_pids(pid)) "
            "AND query LIKE %s",
            (blocker_pid, "%" + table + "%"),
        ).fetchall()
        if rows:
            pids = tuple(pid for (pid,) in rows)
            assert all(pid != blocker_pid for pid in pids)
            if advisory_key is not None:
                witnessed = observer.execute(
                    "SELECT h.pid,w.pid,h.database,h.classid,h.objid,h.objsubid,h"
                    ".mode,h.granted,w.granted "
                    "FROM pg_locks h JOIN pg_locks w USING(locktype,database,clas"
                    "sid,objid,objsubid) "
                    "WHERE h.locktype='advisory' AND h.pid=%s AND w.pid=ANY(%s) "
                    "AND h.database=(SELECT oid FROM pg_database WHERE datname=current_database()) "
                    "AND h.classid=%s AND h.objid=%s AND h.objsubid=1 "
                    "AND h.mode='ExclusiveLock' AND w.mode=h.mode AND h.granted AND NOT w.granted",
                    (blocker_pid, list(pids), advisory_key >> 32, advisory_key & 0xFFFFFFFF),
                ).fetchall()
                assert {row[1] for row in witnessed} == set(pids)
                print(
                    "REAL_ADVISORY_WAIT",
                    observer.execute("SELECT current_schema()").fetchone()[0],
                    advisory_key,
                    witnessed,
                )
            return pids
        time.sleep(0.01)
    raise AssertionError("independent backend did not reach actual lock wait")


def wait_past_database_deadline(observer, deadline, *, timeout=180):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        now = observer.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0]
        if now >= deadline:
            return
        time.sleep(0.01)
    raise AssertionError("finite real database deadline was not reached")


def namespace_evidence(dsn, *, connection=None):
    """Read back the real namespace marker and retain only nonsecret parameters."""
    from contextlib import nullcontext

    reader = nullcontext(connection) if connection is not None else psycopg.connect(dsn)
    with reader as conn:
        schema, database = conn.execute("SELECT current_schema(),current_database()").fetchone()
        run_id, marker_database, created_at = conn.execute(
            "SELECT run_id,database_name,created_at FROM ag_test_ownership"
        ).fetchone()
        assert schema == "ag_test_run_" + run_id and database == marker_database
        parameters = {
            key: value
            for key, value in conn.info.get_parameters().items()
            if key in ("user", "host", "port", "dbname", "options", "sslmode", "sslrootcert")
        }
    configured = os.environ.get("A31_TEST_EVIDENCE_DIR")
    evidence = Path(configured) if configured else Path(tempfile.mkdtemp(prefix="ag31-namespace-"))
    evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = evidence / (run_id + ".json")
    if not path.exists():
        path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "schema": schema,
                    "database": database,
                    "marker_created_at": created_at.isoformat(),
                    "parameters": parameters,
                },
                sort_keys=True,
            )
            + "\n"
        )
        path.chmod(0o600)
    return path


def state(dsn, downstream_dsn):
    namespace_evidence(dsn)
    return full_state(dsn, downstream_dsn)


def shared_retry_bundle(item, dsn):
    from agent_guard.authorization.proof import sign_ag_proof
    from agent_guard.contracts.encoding import load_strict_json
    from agent_guard.contracts.ledger import INVOKE_ENDPOINT

    with psycopg.connect(dsn) as conn:
        body = bytes(
            conn.execute(
                "SELECT e.body_bytes FROM ag_verified_evidence e "
                "JOIN ag_operations o ON o.evidence_ref=e.evidence_ref "
                "WHERE o.operation_id=%s",
                (item["op"],),
            ).fetchone()[0]
        )
    proof = sign_ag_proof(
        item["key"],
        kid=item["registration"].kid,
        client_id=item["client"],
        purpose="invoke",
        endpoint=INVOKE_ENDPOINT,
        body=load_strict_json(body),
        token=item["token"],
        now=int(time.time()),
    )
    return item["iv"].verify_bundle(item["token"], proof, body=body, now=int(time.time()))
