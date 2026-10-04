"""Real verifier/PG acceptance through the strict public ASGI endpoints."""

import psycopg
import pytest

from tests.fixtures.gateway import app_for, query_bundle, raw_material, request, state
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


def send_bundle(app, dsn, bundle, *, query=False):
    token, proof, body = raw_material(dsn, bundle)
    return request(
        app,
        path="/v1/operations/query" if query else "/v1/invocations",
        body=body,
        headers=[
            (b"content-type", b"application/json"),
            (b"authorization", b"AGPoP " + token),
            (b"ag-proof", proof),
        ],
    )


def test_real_http_invoke_query_retry_and_no_implicit_worker(ledger, dsn, downstream_dsn):
    env = signed_env(dsn, downstream_dsn)
    app = app_for(env, dsn)
    bundle = env.bundle()
    status, accepted, _ = send_bundle(app, dsn, bundle)
    assert status == 202 and set(accepted) == {"operation_id", "status", "receipt_status"}
    assert accepted["status"] == "RESERVED"
    with psycopg.connect(downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_operations").fetchone() == (0,)
    before = state(dsn, proofs=False)
    status, answer, _ = send_bundle(
        app, dsn, query_bundle(env, accepted["operation_id"]), query=True
    )
    assert status == 200 and answer["result"] is None
    assert state(dsn, proofs=False) == before
    assert env.service.run_operation(accepted["operation_id"]).status == "SUCCEEDED"
    assert send_bundle(app, dsn, env.bundle())[1]["status"] == "SUCCEEDED"
    status, answer, _ = send_bundle(
        app, dsn, query_bundle(env, accepted["operation_id"]), query=True
    )
    assert status == 200 and answer["result"]["kind"] == "order"
    assert answer["receipt_status"] == "PENDING" and answer["receipt_jws"] is None
    status, replay, _ = send_bundle(app, dsn, bundle)
    assert status == 409 and replay["error"]["code"] == "REPLAY"
    app._executor.shutdown()


def test_unknown_operation_uniform_scope_and_zero_changes(ledger, dsn, downstream_dsn):
    env = signed_env(dsn, downstream_dsn)
    app = app_for(env, dsn)
    bundle = query_bundle(env, "guessed-sensitive-id")
    before = state(dsn)
    status, body, _ = send_bundle(app, dsn, bundle, query=True)
    assert status == 403 and body["error"]["code"] == "SCOPE_DENIED"
    assert "guessed-sensitive-id" not in str(body)
    assert state(dsn) == before
    app._executor.shutdown()


@pytest.mark.parametrize(
    "variant,expected,code",
    [
        ("sku-scope", 403, "SCOPE_DENIED"),
        ("request-scope", 403, "SCOPE_DENIED"),
        ("bool", 400, "INVALID_SCHEMA"),
        ("duplicate-sku", 400, "INVALID_SCHEMA"),
        ("tool-alias", 400, "INVALID_SCHEMA"),
        ("version", 400, "INVALID_SCHEMA"),
        ("extra", 400, "INVALID_SCHEMA"),
        ("url", 400, "INVALID_SCHEMA"),
        ("stale", 401, "STALE_REQUEST"),
        ("holder", 401, "INVALID_SIGNATURE"),
        ("endpoint", 401, "INVALID_SIGNATURE"),
        ("body", 401, "INVALID_SIGNATURE"),
        ("bad-token", 401, "INVALID_SIGNATURE"),
        ("missing-proof", 401, "INVALID_SIGNATURE"),
        ("bearer", 401, "INVALID_SIGNATURE"),
    ],
)
def test_real_signed_http_rejections_zero_budget_effect(
    ledger, dsn, downstream_dsn, variant, expected, code
):
    import time

    from agent_guard.authorization.proof import sign_ag_proof
    from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
    from agent_guard.contracts.ledger import INVOKE_ENDPOINT

    env = signed_env(dsn, downstream_dsn)
    original = env.bundle()
    token, proof, body = raw_material(dsn, original)
    value = load_strict_json(body)
    if variant == "sku-scope":
        value["params"]["items"][0]["sku"] = "other-sku"
    if variant == "request-scope":
        value["params"]["request_id"] = "other-request"
    if variant == "bool":
        value["params"]["items"][0]["quantity"] = True
    if variant == "duplicate-sku":
        value["params"]["items"] *= 2
    if variant == "tool-alias":
        value["tool_id"] = "order.create"
    if variant == "version":
        value["tool_version"] = 1
    if variant == "extra":
        value["params"]["amount_fen"] = 1
    if variant == "url":
        value["params"]["request_id"] = "https://evil.test"
    holder = "planner" if variant == "holder" else "executor"
    proof = sign_ag_proof(
        env.keys[holder],
        kid=env.registrations[("tenant-001", "agent-" + holder)].kid,
        client_id="agent-" + holder,
        purpose="invoke",
        endpoint=INVOKE_ENDPOINT + "/wrong" if variant == "endpoint" else INVOKE_ENDPOINT,
        token=env.token,
        body=value,
        now=int(time.time()) - (61 if variant == "stale" else 0),
    ).encode()
    if variant == "body":
        value["idempotency_key"] = "changed-after-signing"
    if variant == "bad-token":
        token = b"synthetic-sensitive-token-marker"
    if variant == "missing-proof":
        proof = b""
    scheme = b"Bearer " if variant == "bearer" else b"AGPoP "
    before = state(dsn)
    app = app_for(env, dsn)
    status, answer, headers = request(
        app,
        body=canonical_json_bytes(value),
        headers=[
            (b"content-type", b"application/json"),
            (b"authorization", scheme + token),
            (b"ag-proof", proof),
        ],
    )
    assert status == expected and answer["error"]["code"] == code
    assert state(dsn) == before
    assert all(
        marker not in str(answer) for marker in [env.token, "synthetic-sensitive-token-marker", dsn]
    )
    if expected == 401:
        assert headers[b"www-authenticate"].startswith(b"AGPoP ")
    with psycopg.connect(downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_operations").fetchone() == (0,)
    app._executor.shutdown()


def test_real_http_conflicts_budget_and_database_failure(ledger, dsn, downstream_dsn):
    env = signed_env(dsn, downstream_dsn)
    app = app_for(env, dsn)
    first = env.bundle()
    status, answer, _ = send_bundle(app, dsn, first)
    assert status == 202
    assert env.service.run_operation(answer["operation_id"]).status == "SUCCEEDED"
    before = state(dsn)
    changed = env.bundle(
        params={
            "request_id": "req-001",
            "quote_id": "quote-001",
            "quote_version": "1",
            "items": [{"sku": "sku-001", "quantity": 2}],
            "delivery_id": "office-001",
        }
    )
    status, error, _ = send_bundle(app, dsn, changed)
    assert status == 409 and error["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert state(dsn) == before
    status, error, _ = send_bundle(app, dsn, env.bundle("second-budget"))
    assert status == 422 and error["error"]["code"] == "BUDGET_EXCEEDED"
    assert state(dsn) == before
    # A real self-owned backend death at the same-transaction query binding.
    normal = env.evidence.query_binding

    def terminate(bundle):
        bind = normal(bundle)

        def check(conn):
            bind(conn)
            conn.execute("SELECT pg_terminate_backend(pg_backend_pid())")

        return check

    env.evidence.query_binding = terminate
    status, error, _ = send_bundle(app, dsn, query_bundle(env, answer["operation_id"]), query=True)
    assert status == 503 and error["error"]["code"] == "TRUSTED_STATE_UNAVAILABLE"
    assert state(dsn) == before
    app._executor.shutdown()
