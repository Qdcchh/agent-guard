"""Independent r2 fault variants designed from _original/receipt projection."""

from datetime import datetime, timezone

import psycopg
import pytest
from psycopg import sql

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode
from agent_guard.execution.query import AuthorizedQuery
from tests.fixtures.a31_joint import assert_query_delta
from tests.fixtures.gateway import app_for, query_bundle, raw_material
from tests.integration.test_consent_final_decision import _wait_expired
from tests.integration.test_gateway_http import send_bundle as send_raw_http_bundle
from tests.integration.test_verified_execution import signed_env


def send_bundle(app, dsn, bundle, *, query=False):
    """Project a real preverified AtomicQuery through the real HTTP error boundary.

    query_bundle has already performed real SM2 verification and STAGED this
    exact material. AtomicQuery rollback includes that staged row unchanged.
    Normal HTTP verification stages a new row and is covered by the joint flow.
    """
    assert query is True
    token, proof, body = raw_material(dsn, bundle)
    endpoint = app._endpoint
    original_handle = endpoint.handle
    previous_instance_handle = endpoint.__dict__.get("handle")

    def preverified_handle(path, observed_token, observed_proof, observed_body):
        assert path == "/v1/operations/query"
        assert observed_token.encode("ascii") == token
        assert observed_proof.encode("ascii") == proof
        assert observed_body == body
        endpoint.schema(observed_body, query=True)
        return 200, endpoint._queries.query(bundle)

    endpoint.handle = preverified_handle
    try:
        return send_raw_http_bundle(app, dsn, bundle, query=True)
    finally:
        if previous_instance_handle is None:
            del endpoint.handle
        else:
            endpoint.handle = original_handle


def full(dsn, prefix="ag_"):
    with psycopg.connect(dsn) as c:
        names = [
            x[0]
            for x in c.execute(
                (
                    "SELECT tablename FROM pg_tables WHERE "
                    "schemaname=current_schema() AND tablename LIKE %s ORDER BY tablename"
                ),
                (prefix + "%",),
            )
        ]
        rows = {
            n: c.execute(
                sql.SQL(
                    "SELECT row_to_json(t)::text FROM {} t ORDER BY row_to_json(t)::text"
                ).format(sql.Identifier(n))
            ).fetchall()
            for n in names
        }
        if prefix == "ag_":
            rows["accepted_evidence"] = c.execute(
                (
                    "SELECT row_to_json(e)::text FROM ag_operation_evidence "
                    "l JOIN ag_verified_evidence e USING(evidence_"
                    "ref) ORDER BY l.operation_id,l.kind,l.evidenc"
                    "e_ref"
                )
            ).fetchall()
            counters = c.execute(
                (
                    "SELECT "
                    "grant_id,amount_reserved,amount_settled,calls"
                    "_reserved,calls_settled FROM ag_grants ORDER "
                    "BY depth"
                )
            ).fetchall()
            assert len(counters) == 3
            rows["all_ancestor_four_counters"] = counters
        else:
            assert {"ds_operations", "ds_orders", "ds_notifications"} <= rows.keys()
        return rows


CONTEXT_VARIANTS = {
    "tenant_id": "r2-wrong-tenant",
    "task_id": "r2-wrong-task",
    "root_id": "r2-wrong-root",
    "tool_id": "procurement.document.read",
    "tool_version": "17",
    "idempotency_key": "r2-new-intent",
    "canonical_params": "eyJyZXF1ZXN0X2lkIjoicmVxLTAwMSJ9",
    "ancestor_ids": ["r2-wrong-ancestor"],
    "token_digest": "r2-token-marker",
    "proof_digest": "r2-proof-marker",
    "intent_digest": "r2-intent-marker",
    "token_exp": 7,
    "proof_iat": 11,
    "proof_exp": 13,
    "proof_jti": "r2-proof-jti",
    "profile": "GM-MVP-R2",
}


@pytest.mark.parametrize("field", CONTEXT_VARIANTS)
def test_same_shape_context_integrity_and_full_rollback(ledger, dsn, downstream_dsn, field):
    env = signed_env(dsn, downstream_dsn)
    op = env.adapter.accept(env.bundle()).operation_id
    bundle = query_bundle(env, op)
    with psycopg.connect(dsn) as c:
        ref, raw = c.execute(
            (
                "SELECT evidence_ref,context_json FROM "
                "ag_verified_evidence WHERE evidence_ref=(SELE"
                "CT evidence_ref FROM ag_operations WHERE oper"
                "ation_id=%s)"
            ),
            (op,),
        ).fetchone()
        original = bytes(raw)
        value = load_strict_json(original)
        assert value[field] != CONTEXT_VARIANTS[field]
        value[field] = CONTEXT_VARIANTS[field]
        c.execute("ALTER TABLE ag_verified_evidence DISABLE TRIGGER USER")
        c.execute(
            "UPDATE ag_verified_evidence SET context_json=%s WHERE evidence_ref=%s",
            (canonical_json_bytes(value), ref),
        )
        c.execute("ALTER TABLE ag_verified_evidence ENABLE TRIGGER USER")
    before, downstream = full(dsn), full(downstream_dsn, "ds_")
    app = app_for(env, dsn)
    try:
        status, result, headers = send_bundle(app, dsn, bundle, query=True)
        assert status == 503 and result["error"]["code"] == "TRUSTED_STATE_UNAVAILABLE"
        assert headers[b"cache-control"] == b"no-store"
        assert not any(
            m in str(result) for m in ["r2-token-marker", "r2-proof-marker", "r2-intent-marker"]
        )
        assert full(dsn) == before and full(downstream_dsn, "ds_") == downstream
        with psycopg.connect(dsn) as c:
            c.execute("ALTER TABLE ag_verified_evidence DISABLE TRIGGER USER")
            c.execute(
                "UPDATE ag_verified_evidence SET context_json=%s WHERE evidence_ref=%s",
                (original, ref),
            )
            c.execute("ALTER TABLE ag_verified_evidence ENABLE TRIGGER USER")
        repaired = full(dsn)
        status, repaired_answer, _ = send_bundle(app, dsn, bundle, query=True)
        assert status == 200
        after = full(dsn)
        assert len(after["ag_proofs"]) == len(repaired["ag_proofs"]) + 1
        assert_query_delta(repaired, after, bundle, op, observed_response=repaired_answer)
        assert send_bundle(app, dsn, bundle, query=True)[0] == 409
        assert full(dsn) == after and full(downstream_dsn, "ds_") == downstream
    finally:
        app._executor.shutdown()


def test_expired_historical_proof_fresh_query_keeps_complete_business_state(
    ledger, dsn, downstream_dsn
):
    env = signed_env(dsn, downstream_dsn)
    original = env.bundle(proof_lifetime=3)
    op = env.adapter.accept(original).operation_id
    with psycopg.connect(dsn, autocommit=True) as c:
        _wait_expired(c, datetime.fromtimestamp(original.invocation.proof_exp, timezone.utc))
        assert c.execute(
            "SELECT extract(epoch FROM clock_timestamp())>%s", (original.invocation.proof_exp,)
        ).fetchone() == (True,)
    query = query_bundle(env, op)
    assert query.query.proof_iat >= original.invocation.proof_exp
    before, downstream = full(dsn), full(downstream_dsn, "ds_")
    answer = AuthorizedQuery(dsn, evidence_store=env.evidence).query(query)
    assert answer["status"] == "RESERVED"
    after = full(dsn)
    assert len(after["ag_proofs"]) == len(before["ag_proofs"]) + 1
    assert_query_delta(before, after, query, op, observed_response=answer)
    assert full(downstream_dsn, "ds_") == downstream


FAULTS = [
    (s, f)
    for s in ["order", "request", "document", "notification", "refusal"]
    for f in ["operation", "kind", "array"]
] + [("order", "total"), ("order", "supplier"), ("notification", "recipient"), ("refusal", "tool")]


@pytest.mark.parametrize("shape,fault", FAULTS)
def test_terminal_result_fault_repair_same_proof_then_replay(
    ledger, dsn, downstream_dsn, shape, fault
):
    env = signed_env(dsn, downstream_dsn)
    if shape == "notification":
        anchor = env.adapter.accept(env.bundle()).operation_id
        assert env.service.run_operation(anchor).status == "SUCCEEDED"
        first = env.bundle(
            "r2-notify",
            tool="notification.template.send",
            params={
                "template_id": "order-created",
                "recipient_id": "user-demo-001",
                "operation_id": anchor,
            },
        )
    elif shape in ["request", "document"]:
        params = {"request_id": "req-001"}
        if shape == "document":
            params["document_id"] = "doc-001"
        first = env.bundle("r2-read", tool="procurement." + shape + ".read", params=params)
    else:
        first = env.bundle()
        if shape == "refusal":
            env.service._downstream._approved_suppliers = frozenset()
    op = env.adapter.accept(first).operation_id
    terminal = "FAILED" if shape == "refusal" else "SUCCEEDED"
    assert env.service.run_operation(op).status == terminal
    bundle = query_bundle(env, op)
    with psycopg.connect(dsn) as c:
        raw = bytes(
            c.execute(
                "SELECT result_bytes FROM ag_receipt_outbox WHERE operation_id=%s", (op,)
            ).fetchone()[0]
        )
    result = load_strict_json(raw)
    corrupt = dict(result)
    if fault == "operation":
        corrupt["operation_id"] = "r2-persistent-private-marker"
    if fault == "kind":
        corrupt["kind"] = "refusal" if shape != "refusal" else "read"
    if fault == "total":
        corrupt["total_fen"] += 2
    if fault == "supplier":
        corrupt["supplier_id"] = "r2-persistent-private-marker"
    if fault == "recipient":
        corrupt["recipient_id"] = "r2-persistent-private-marker"
    if fault == "tool":
        corrupt["tool_id"] = "procurement.document.read"

    def rewrite(value):
        with psycopg.connect(dsn) as c:
            c.execute("ALTER TABLE ag_receipt_outbox DISABLE TRIGGER USER")
            c.execute(
                "UPDATE ag_receipt_outbox SET result_bytes=%s WHERE operation_id=%s", (value, op)
            )
            c.execute("ALTER TABLE ag_receipt_outbox ENABLE TRIGGER USER")

    rewrite(b"[]" if fault == "array" else canonical_json_bytes(corrupt))
    before, downstream = full(dsn), full(downstream_dsn, "ds_")
    app = app_for(env, dsn)
    try:
        code, error, headers = send_bundle(app, dsn, bundle, query=True)
        assert code == 503 and error["error"]["code"] == "TRUSTED_STATE_UNAVAILABLE"
        assert "r2-persistent-private-marker" not in str(error)
        assert headers[b"cache-control"] == b"no-store" and headers[b"pragma"] == b"no-cache"
        assert full(dsn) == before and full(downstream_dsn, "ds_") == downstream
        rewrite(raw)
        repaired = full(dsn)
        code, answer, _ = send_bundle(app, dsn, bundle, query=True)
        assert code == 200 and answer["result"] == result and answer["status"] == terminal
        assert answer["receipt_jws"] is None and answer["receipt_status"] == "PENDING"
        after = full(dsn)
        assert len(after["ag_proofs"]) == len(repaired["ag_proofs"]) + 1
        assert_query_delta(repaired, after, bundle, op, observed_response=answer)
        code, error, _ = send_bundle(app, dsn, bundle, query=True)
        assert code == 409 and error["error"]["code"] == "REPLAY"
        assert full(dsn) == after and full(downstream_dsn, "ds_") == downstream
    finally:
        app._executor.shutdown()


@pytest.mark.parametrize("kind", ["typed", "runtime"])
def test_projection_unknown_errors_do_not_become_503(
    ledger, dsn, downstream_dsn, monkeypatch, kind
):
    from agent_guard.execution import query as module

    env = signed_env(dsn, downstream_dsn)
    op = env.adapter.accept(env.bundle()).operation_id
    assert env.service.run_operation(op).status == "SUCCEEDED"
    query = query_bundle(env, op)
    before, downstream = full(dsn), full(downstream_dsn, "ds_")

    def fail(*args):
        if kind == "typed":
            raise ExecutionError(ExecutionErrorCode.LEASE_LOST)
        raise RuntimeError("r2-programming-private-marker")

    monkeypatch.setattr(module, "project_receipt", fail)
    app = app_for(env, dsn)
    try:
        code, error, _ = send_bundle(app, dsn, query, query=True)
        assert code == 500 and error["error"]["code"] == "INTERNAL_ERROR"
        assert "r2-programming-private-marker" not in str(error)
        assert full(dsn) == before and full(downstream_dsn, "ds_") == downstream
    finally:
        app._executor.shutdown()
