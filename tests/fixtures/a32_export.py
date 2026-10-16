"""Native accepted A31 rows and a separate SELECT-only export connection."""

import secrets
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

import psycopg
from psycopg import sql

from agent_guard.audit.checkpoint import sign_checkpoint
from agent_guard.audit.contracts import CheckpointTrust, JournalScope, utc_text
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.crypto.sm import (
    generate_sm2_private_key,
    serialize_sm2_public_key,
    sm3_b64url,
)
from agent_guard.evidence.task_bundle import load_checkpoint_history


def task_scope(dsn):
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT gateway_id,tenant_id,task_id,stream_id,epoch "
            "FROM ag_audit_streams ORDER BY stream_id"
        ).fetchone()
    assert row is not None
    return JournalScope(*row)


def history_inputs(dsn, directory, *, mode="LATEST_OBSERVATION", sequences=None, fault=None):
    from datetime import datetime, timezone

    scope = task_scope(dsn)
    key = generate_sm2_private_key()
    trust = (
        CheckpointTrust(
            "export-test-audit",
            "AUDIT_SIGNER",
            serialize_sm2_public_key(key.public_key()),
            1,
            None,
        ),
    )
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT seq,digest FROM ag_audit_records WHERE stream_id=%s ORDER BY seq",
            (scope.stream_id,),
        ).fetchall()
    selected = [row for row in rows if sequences is None or row[0] in sequences]
    jwss = []
    previous = None
    for seq, head in selected:
        if fault == "behind":
            seq += len(rows)
        if fault == "fork":
            head = sm3_b64url(b"genuine signed foreign journal head")
        jws = sign_checkpoint(
            {
                **asdict(scope),
                "profile": "GM-MVP-1",
                "checkpoint_version": "AG-CHECKPOINT-1",
                "checkpoint_id": str(uuid.uuid4()),
                "sequence": seq,
                "head_digest": head,
                "previous_checkpoint_digest": previous,
                "issued_at": utc_text(datetime.now(timezone.utc)),
                "kid": "export-test-audit",
            },
            private_key=key,
            key_id="export-test-audit",
        )
        jwss.append(jws)
        previous = sm3_b64url(jws.encode("ascii"))
    pin = {
        "mode": mode,
        "checkpoint_jws": None if mode == "UNKNOWN" else jwss[-1],
        "observed_at": None if mode == "UNKNOWN" else int(datetime.now(timezone.utc).timestamp()),
        "scope": asdict(scope),
    }
    path = Path(directory) / (str(uuid.uuid4()) + ".history")
    path.write_bytes(b"".join(canonical_json_bytes({"checkpoint_jws": j}) + b"\n" for j in jwss))
    with path.open("rb") as stream:
        descriptor = load_checkpoint_history(
            stream,
            external_trust={"scope": scope, "audit_keys": trust},
            external_pin=pin,
        )
    return scope, pin, descriptor


def cache_checkpoint_rows(dsn, history, sequences):
    """Fixture migration role persists genuine original CPs with real batch bytes."""
    from agent_guard.audit.contracts import (
        decode_checkpoint_claims,
        encode_append_batch,
    )
    from agent_guard.contracts.encoding import b64url_decode, load_strict_json

    with history.open_readonly() as stream, psycopg.connect(dsn) as conn:
        for raw in stream:
            jws = load_strict_json(raw[:-1])["checkpoint_jws"]
            cp = decode_checkpoint_claims(b64url_decode(jws.split(".")[1]))
            if cp.sequence not in sequences:
                continue
            record = conn.execute(
                "SELECT raw FROM ag_audit_records WHERE stream_id=%s AND seq=%s",
                (history.scope.stream_id, cp.sequence),
            ).fetchone()
            batch = encode_append_batch(history.scope.stream_id, (bytes(record[0]),))
            conn.execute(
                "INSERT INTO ag_audit_delivery_batches"
                "(stream_id,batch_id,exact_body,start_sequence,"
                "end_sequence,end_digest,base_checkpoint_digest,checkpoint_jws,ack_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())",
                (
                    batch.stream_id,
                    batch.batch_id,
                    batch.exact_body,
                    batch.start_sequence,
                    batch.end_sequence,
                    batch.end_digest,
                    cp.previous_checkpoint_digest,
                    jws,
                ),
            )


@contextmanager
def readonly_export_factory(dsn):
    """Migration fixture installs a new login with no production write capability."""
    name = "a32_export_" + uuid.uuid4().hex
    password = secrets.token_urlsafe(32)
    with psycopg.connect(dsn) as conn:
        schema = conn.execute("SELECT current_schema()").fetchone()[0]
        conn.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(name), sql.Literal(password)
            )
        )
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(schema), sql.Identifier(name)
            )
        )
        conn.execute(
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                sql.Identifier(schema), sql.Identifier(name)
            )
        )
    info = psycopg.conninfo.conninfo_to_dict(dsn)
    info.update(user=name, password=password)
    value = psycopg.conninfo.make_conninfo(**info)
    try:
        yield lambda: psycopg.connect(value, connect_timeout=5)
    finally:
        with psycopg.connect(dsn) as conn:
            conn.execute(
                sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM {}").format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            )
            conn.execute(
                sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            )
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))


def export_full_state(dsn, downstream_dsn):
    """Retain every original table row alongside the complete comparison oracle."""
    import json
    import os
    import uuid

    from tests.fixtures.receipts import full_state

    state = full_state(dsn, downstream_dsn)
    target = os.environ.get("A31_TEST_EVIDENCE_DIR")
    if target:
        directory = Path(target) / "export-full-row-oracles"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / (str(uuid.uuid4()) + ".json")
        with path.open("x") as output:
            os.chmod(path, 0o600)
            json.dump({"node": os.environ.get("PYTEST_CURRENT_TEST"), "state": state}, output)
    return state


def record_export_native_evidence(label, data):
    import json
    import os
    import uuid

    directory = Path(os.environ["A31_TEST_EVIDENCE_DIR"]) / "export-native-process"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / (label + "-" + str(uuid.uuid4()) + ".json")
    with path.open("x") as output:
        os.chmod(path, 0o600)
        json.dump({"node": os.environ.get("PYTEST_CURRENT_TEST"), **data}, output)


def accept_other_task(dsn, downstream_dsn, monkeypatch):
    """Create a second real AS task and genuinely signed invocation."""
    import time

    from agent_guard.authorization.proof import sign_ag_proof
    from tests.integration import test_exchange_service as exchange
    from tests.integration.test_verified_execution import INVOKE_ENDPOINT, signed_env

    with monkeypatch.context() as patch:
        original_register = exchange.register_principal

        def reuse_principal(conn, **kwargs):
            present = conn.execute(
                "SELECT 1 FROM ag_principals WHERE tenant_id=%s AND client_id=%s AND kid=%s",
                (kwargs["tenant_id"], kwargs["client_id"], kwargs["kid"]),
            ).fetchone()
            if present is None:
                return original_register(conn, **kwargs)

        patch.setattr(exchange, "register_principal", reuse_principal)
        patch.setattr(exchange, "TASK", "export-other-task")
        env = signed_env(dsn, downstream_dsn)
    from tests.fixtures.execution import build_catalog

    env.service._catalog = build_catalog(exchange.TENANT, "export-other-task")
    request = {
        "profile": "GM-MVP-1",
        "task_id": "export-other-task",
        "tool_id": "procurement.request.read",
        "tool_version": "1",
        "idempotency_key": "other-task-first",
        "params": {"request_id": "req-001"},
    }
    now = int(time.time())
    proof = sign_ag_proof(
        env.keys["executor"],
        kid=env.registrations[(exchange.TENANT, "agent-executor")].kid,
        client_id="agent-executor",
        purpose="invoke",
        endpoint=INVOKE_ENDPOINT,
        body=request,
        token=env.token,
        now=now,
        lifetime_seconds=60,
    )
    return env.adapter.accept(
        env.verifier.verify_bundle(env.token, proof, body=canonical_json_bytes(request), now=now)
    )
