"""Real signed zero-cost queries, late-lock clocks and dynamic races."""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone

import psycopg
import pytest
from psycopg import sql

from agent_guard.authorization.evidence_store import EvidenceError
from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode
from agent_guard.contracts.ledger import ErrorCode, LedgerError
from agent_guard.execution.query import AuthorizedQuery
from tests.fixtures.gateway import query_bundle, signed_env_window, state
from tests.integration.test_consent_final_decision import _wait_blocked, _wait_expired
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("status", ["RESERVED", "EXECUTING", "UNKNOWN", "SUCCEEDED", "FAILED"])
def test_all_statuses_zero_business_cost(ledger, dsn, downstream_dsn, status):
    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    if status in ("SUCCEEDED", "FAILED"):
        if status == "FAILED":
            env.service._downstream._approved_suppliers = frozenset()
        assert env.service.run_operation(accepted.operation_id).status == status
    elif status == "EXECUTING":
        env.service._claim(accepted.operation_id, "test-query-owner")
    elif status == "UNKNOWN":

        class Unavailable:
            def execute(self, **kwargs):
                raise TimeoutError("synthetic downstream timeout")

            def query(self, **kwargs):
                return None

        env.service._downstream = Unavailable()
        assert env.service.run_operation(accepted.operation_id).status == "UNKNOWN"
    bundle = query_bundle(env, accepted.operation_id)
    before = state(dsn, proofs=False)
    with psycopg.connect(downstream_dsn) as conn:
        ds_before = conn.execute("SELECT * FROM ds_operations ORDER BY operation_id").fetchall()
    response = AuthorizedQuery(dsn, evidence_store=env.evidence).query(bundle)
    assert response["status"] == status
    assert response["receipt_status"] == "PENDING" and response["receipt_jws"] is None
    assert (response["result"] is None) == (status not in ("SUCCEEDED", "FAILED"))
    assert state(dsn, proofs=False) == before
    with psycopg.connect(downstream_dsn) as conn:
        assert (
            conn.execute("SELECT * FROM ds_operations ORDER BY operation_id").fetchall()
            == ds_before
        )
    with psycopg.connect(dsn) as conn:
        assert conn.execute(
            "SELECT operation_id,evidence_ref FROM ag_proofs WHERE purpose='result-read'"
        ).fetchall() == [(accepted.operation_id, bundle.evidence_ref)]
        assert conn.execute(
            "SELECT kind,count(*) FROM ag_operation_evidence GROUP BY kind"
        ).fetchall() == [("first", 1)]


@pytest.mark.parametrize("round_id", range(10))
def test_same_query_proof_only_one_success(ledger, dsn, downstream_dsn, round_id):
    import threading

    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    bundle = query_bundle(env, accepted.operation_id)
    before = state(dsn, proofs=False)
    barrier = threading.Barrier(4)

    def query():
        barrier.wait(timeout=5)
        try:
            return AuthorizedQuery(dsn, evidence_store=env.evidence).query(bundle)
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(4) as pool:
        all_results = list(pool.map(lambda _: query(), range(4)))
    assert sum(type(x) is dict for x in all_results) == 1
    failures = [x for x in all_results if type(x) is not dict]
    assert len(failures) == 3 and all(
        isinstance(x, LedgerError) and x.code is ErrorCode.REPLAY for x in failures
    )
    assert state(dsn, proofs=False) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "operation",
        "grant",
        "root",
        "holder",
        "kid",
        "tenant",
        "task",
        "subject",
        "ref",
        "source",
    ],
)
def test_ownership_and_bundle_replacement_fail_closed(ledger, dsn, downstream_dsn, mutation):
    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    bundle = query_bundle(env, accepted.operation_id)
    if mutation in ("unknown", "operation"):
        bundle = query_bundle(env, "nonexistent")
    elif mutation == "ref":
        other = query_bundle(env, accepted.operation_id)
        bundle = replace(
            bundle,
            evidence_ref=other.evidence_ref,
            query=replace(bundle.query, evidence_ref=other.evidence_ref),
        )
    elif mutation == "source":
        bundle = replace(bundle, source=replace(bundle.source, digest="forged"))
    else:
        name = {
            "holder": "holder_client_id",
            "kid": "holder_kid",
            "grant": "grant_id",
            "root": "root_id",
            "tenant": "tenant_id",
            "task": "task_id",
        }.get(mutation, mutation)
        bundle = replace(bundle, query=replace(bundle.query, **{name: "other"}))
    before = state(dsn)
    with pytest.raises((LedgerError, EvidenceError, ExecutionError, ValueError)) as failure:
        AuthorizedQuery(dsn, evidence_store=env.evidence).query(bundle)
    if mutation in ("unknown", "operation"):
        assert failure.value.code is ExecutionErrorCode.RESOURCE_NOT_FOUND
    elif mutation in ("ref", "source"):
        assert isinstance(failure.value, EvidenceError)
    assert state(dsn) == before


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize(
    "mode",
    [
        "principals",
        "task",
        "grants",
        "operation",
        "evidence",
        "proof-insert",
        "proof-link",
        "deferred",
    ],
)
@pytest.mark.parametrize("positive", [False, True])
def test_final_clock_after_every_query_wait(ledger, dsn, downstream_dsn, round_id, mode, positive):
    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    while time.time() % 1 > 0.15:
        time.sleep(0.01)
    bundle = query_bundle(env, accepted.operation_id, lifetime=1)
    deadline = datetime.fromtimestamp(bundle.query.proof_exp, tz=timezone.utc)
    key = 95719021
    with psycopg.connect(dsn, autocommit=True) as observer:
        before = state(dsn)
        if mode in ("proof-insert", "proof-link", "deferred"):
            observer.execute(
                sql.SQL(
                    "CREATE FUNCTION ag_test_query_wait() RETURNS trigger AS $$ BEGIN PERFORM "
                    "pg_advisory_xact_lock({}); RETURN NEW; END $$ LANGUAGE plpgsql"
                ).format(sql.Literal(key))
            )
            if mode == "deferred":
                observer.execute(
                    "CREATE CONSTRAINT TRIGGER ag_test_query_wait_trg AFTER INSERT ON ag_proofs "
                    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
                    "ag_test_query_wait()"
                )
            else:
                observer.execute(
                    "CREATE TRIGGER ag_test_query_wait_trg AFTER "
                    + ("INSERT" if mode == "proof-insert" else "UPDATE")
                    + " ON ag_proofs FOR EACH ROW EXECUTE FUNCTION ag_test_query_wait()"
                )
        try:
            with psycopg.connect(dsn) as blocker, ThreadPoolExecutor(1) as pool:
                if mode in ("principals", "task", "grants", "evidence"):
                    table = {
                        "principals": "ag_principals",
                        "task": "ag_tasks",
                        "grants": "ag_grants",
                        "evidence": "ag_verified_evidence",
                    }[mode]
                    blocker.execute(
                        sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(
                            sql.Identifier(table)
                        )
                    )
                    fragment = {
                        "principals": "FROM ag_principals",
                        "task": "FROM ag_tasks",
                        "grants": "ag_grants",
                        "evidence": "FROM ag_operation_evidence",
                    }[mode]
                elif mode == "operation":
                    blocker.execute(
                        "SELECT * FROM ag_operations WHERE operation_id=%s FOR UPDATE",
                        (accepted.operation_id,),
                    )
                    fragment = "FROM ag_operations"
                else:
                    blocker.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
                    fragment = (
                        "SET CONSTRAINTS ALL IMMEDIATE"
                        if mode == "deferred"
                        else (
                            "INSERT INTO ag_proofs"
                            if mode == "proof-insert"
                            else "UPDATE ag_proofs"
                        )
                    )
                future = pool.submit(
                    AuthorizedQuery(dsn, evidence_store=env.evidence).query, bundle
                )
                _wait_blocked(observer, blocker.info.backend_pid, fragment)
                if not positive:
                    _wait_expired(observer, deadline)
                blocker.commit()
                if positive:
                    assert future.result(timeout=5)["operation_id"] == accepted.operation_id
                else:
                    with pytest.raises(LedgerError) as failure:
                        future.result(timeout=5)
                    assert failure.value.code is ErrorCode.STALE_REQUEST
                    assert state(dsn) == before
        finally:
            if mode in ("proof-insert", "proof-link", "deferred"):
                observer.execute("DROP TRIGGER ag_test_query_wait_trg ON ag_proofs")
                observer.execute("DROP FUNCTION ag_test_query_wait()")
    if not positive:
        assert (
            AuthorizedQuery(dsn, evidence_store=env.evidence).query(
                query_bundle(env, accepted.operation_id)
            )["status"]
            == "RESERVED"
        )


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("kind", ["revoke", "deactivate"])
@pytest.mark.parametrize("winner", ["query", "mutation"])
@pytest.mark.parametrize("ancestor", ["root", "mid", "leaf"])
def test_query_serializes_with_revocation_and_key_state(
    ledger, dsn, downstream_dsn, round_id, kind, winner, ancestor
):
    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    bundle = query_bundle(env, accepted.operation_id)
    before = state(dsn, proofs=False)
    index = {"root": 0, "mid": 1, "leaf": 2}[ancestor]
    grant_id = bundle.source.snapshot.chain_grant_ids[index]
    client_id = ["agent-planner", "agent-selector", "agent-executor"][index]
    registration = env.registrations[("tenant-001", client_id)]

    def mutate():
        with psycopg.connect(dsn) as conn:
            if kind == "revoke":
                conn.execute(
                    "SELECT * FROM ag_tasks WHERE tenant_id='tenant-001' AND task_id='task-001' "
                    "FOR UPDATE"
                )
                conn.execute("UPDATE ag_grants SET revoked=true WHERE grant_id=%s", (grant_id,))
            else:
                conn.execute(
                    "UPDATE ag_principals SET active=false WHERE tenant_id='tenant-001' "
                    "AND client_id=%s "
                    "AND kid=%s",
                    (client_id, registration.kid),
                )

    with psycopg.connect(dsn, autocommit=True) as observer, ThreadPoolExecutor(1) as pool:
        if winner == "mutation":
            with psycopg.connect(dsn) as blocker:
                if kind == "revoke":
                    blocker.execute(
                        "SELECT * FROM ag_tasks WHERE tenant_id='tenant-001' AND "
                        "task_id='task-001' FOR UPDATE"
                    )
                    blocker.execute(
                        "UPDATE ag_grants SET revoked=true WHERE grant_id=%s",
                        (grant_id,),
                    )
                    fragment = "FROM ag_tasks"
                else:
                    blocker.execute(
                        "UPDATE ag_principals SET active=false WHERE tenant_id='tenant-001' "
                        "AND client_id=%s "
                        "AND kid=%s",
                        (client_id, registration.kid),
                    )
                    fragment = "FROM ag_principals"
                future = pool.submit(
                    AuthorizedQuery(dsn, evidence_store=env.evidence).query, bundle
                )
                _wait_blocked(observer, blocker.info.backend_pid, fragment)
                blocker.commit()
                with pytest.raises(LedgerError) as failure:
                    future.result(timeout=5)
                assert failure.value.code is (
                    ErrorCode.REVOKED if kind == "revoke" else ErrorCode.HOLDER_MISMATCH
                )
        else:
            normal = env.evidence.query_binding

            def held(bundle):
                bind = normal(bundle)

                def check(conn):
                    bind(conn)
                    future = pool.submit(mutate)
                    # mutation is demonstrably waiting on this query's locks
                    _wait_blocked(
                        observer,
                        conn.info.backend_pid,
                        "UPDATE ag_" if kind == "deactivate" else "FROM ag_tasks",
                    )
                    held.future = future

                return check

            env.evidence.query_binding = held
            assert (
                AuthorizedQuery(dsn, evidence_store=env.evidence).query(bundle)["status"]
                == "RESERVED"
            )
            held.future.result(timeout=5)
    after = state(dsn, proofs=False)
    assert all(after[n] == before[n] for n in before if n != "ag_grants")
    if winner == "mutation":
        with psycopg.connect(dsn) as conn:
            assert conn.execute(
                "SELECT count(*) FROM ag_proofs WHERE purpose='result-read'"
            ).fetchone() == (0,)


def test_legacy_original_material_is_never_reconstructed(ledger, dsn, downstream_dsn):
    env = signed_env(dsn, downstream_dsn)
    first = env.bundle()
    accepted = env.service.accept_invocation(first.invocation, first.permissions)
    bundle = query_bundle(env, accepted.operation_id)
    before = state(dsn)
    with pytest.raises(EvidenceError):
        AuthorizedQuery(dsn, evidence_store=env.evidence).query(bundle)
    assert state(dsn) == before


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("window", ["token", "root", "mid", "leaf"])
@pytest.mark.parametrize("positive", [False, True])
@pytest.mark.parametrize("cross_second", [False, True])
def test_final_query_token_and_ancestor_windows(
    ledger, dsn, downstream_dsn, round_id, window, positive, cross_second
):
    from agent_guard.crypto.sm import verify_compact_jws

    observations = []
    env = signed_env_window(
        dsn, downstream_dsn, window, cross_second=cross_second, observations=observations
    )
    with psycopg.connect(dsn) as conn:
        tokens = conn.execute(
            "SELECT t.token_jws,g.expires_at FROM ag_grant_tokens t JOIN ag_grants g "
            "USING(grant_id) ORDER BY g.depth"
        ).fetchall()
    claims = [
        verify_compact_jws(
            token, expected_type="ag-at+jwt", trusted_keys={"as-sign-1": env.as_key.public_key()}
        )
        for token, _ in tokens
    ]
    assert len(claims) == len(observations) + 1 == 3
    assert all(
        c["exp"] == int(expiry.timestamp()) for c, (_, expiry) in zip(claims, tokens, strict=False)
    )
    assert all(
        parent["iat"] <= child["iat"] < child["exp"] <= parent["exp"]
        for parent, child in zip(claims, claims[1:], strict=False)
    )
    assert all(o["now"] + o["ttl"] <= o["parent_exp"] - 2 for o in observations)
    if cross_second:
        assert observations[0]["now"] > observations[0]["parent_iat"]
    print("SHORT_WINDOW_REAL_AS", round_id, window, positive, cross_second, observations)
    accepted = env.adapter.accept(env.bundle())
    bundle = query_bundle(env, accepted.operation_id)
    if window == "token":
        deadline = datetime.fromtimestamp(bundle.query.token_exp, tz=timezone.utc)
    else:
        index = {"root": 0, "mid": 1, "leaf": 2}[window]
        with psycopg.connect(dsn) as conn:
            deadline = conn.execute(
                "SELECT expires_at FROM ag_grants WHERE grant_id=%s",
                (bundle.source.snapshot.chain_grant_ids[index],),
            ).fetchone()[0]
    with (
        psycopg.connect(dsn, autocommit=True) as observer,
        psycopg.connect(dsn) as blocker,
        ThreadPoolExecutor(1) as pool,
    ):
        before = state(dsn)
        all_before = _query_all_rows(dsn, "ag_")
        downstream_before = _query_all_rows(downstream_dsn, "ds_")
        assert {"ds_operations", "ds_orders", "ds_notifications"} <= downstream_before.keys()
        blocker.execute(
            "SELECT * FROM ag_operations WHERE operation_id=%s FOR UPDATE", (accepted.operation_id,)
        )
        future = pool.submit(AuthorizedQuery(dsn, evidence_store=env.evidence).query, bundle)
        _wait_blocked(observer, blocker.info.backend_pid, "FROM ag_operations")
        if not positive:
            _wait_expired(observer, deadline)
        blocker.commit()
        if positive:
            assert future.result(timeout=5)["status"] == "RESERVED"
            all_after = _query_all_rows(dsn, "ag_")
            assert len(all_after["ag_proofs"]) == len(all_before["ag_proofs"]) + 1
            assert {k: v for k, v in all_after.items() if k != "ag_proofs"} == {
                k: v for k, v in all_before.items() if k != "ag_proofs"
            }
        else:
            with pytest.raises(LedgerError) as failure:
                future.result(timeout=5)
            assert failure.value.code is ErrorCode.EXPIRED
            assert state(dsn) == before
            assert _query_all_rows(dsn, "ag_") == all_before
        assert _query_all_rows(downstream_dsn, "ds_") == downstream_before


@pytest.mark.parametrize("target", ["request", "context", "chain"])
@pytest.mark.parametrize("bad", [b"[]", b"1", b"null", b"{}"])
def test_corrupt_trusted_first_material_has_typed_503(ledger, dsn, downstream_dsn, target, bad):
    from agent_guard.crypto.sm import sm3_b64url
    from tests.fixtures.gateway import app_for
    from tests.integration.test_gateway_http import send_bundle

    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    bundle = query_bundle(env, accepted.operation_id)
    # Test administrator fault injection in the own namespace only: no public
    # writer can bypass the immutable evidence trigger.
    with psycopg.connect(dsn) as conn:
        conn.execute("ALTER TABLE ag_verified_evidence DISABLE TRIGGER USER")
        if target == "request":
            conn.execute(
                "UPDATE ag_verified_evidence SET body_bytes=%s,body_sm3=%s "
                "WHERE evidence_ref=(SELECT evidence_ref FROM ag_operations "
                "WHERE operation_id=%s)",
                (bad, sm3_b64url(bad), accepted.operation_id),
            )
        else:
            column = "context_json" if target == "context" else "chain_json"
            conn.execute(
                sql.SQL(
                    "UPDATE ag_verified_evidence SET {}=%s WHERE evidence_ref="
                    "(SELECT evidence_ref FROM ag_operations WHERE operation_id=%s)"
                ).format(sql.Identifier(column)),
                (bad, accepted.operation_id),
            )
        conn.execute("ALTER TABLE ag_verified_evidence ENABLE TRIGGER USER")
    before = state(dsn)
    app = app_for(env, dsn)
    status, error, _ = send_bundle(app, dsn, bundle, query=True)
    assert status == 503 and error["error"]["code"] == "TRUSTED_STATE_UNAVAILABLE"
    assert state(dsn) == before
    app._executor.shutdown()


@pytest.mark.parametrize("ancestor", [0, 1, 2])
def test_corrupt_signed_ancestor_is_trusted_state_failure(ledger, dsn, downstream_dsn, ancestor):
    from tests.fixtures.gateway import app_for, raw_material, request

    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    bundle = query_bundle(env, accepted.operation_id)
    token, proof, body = raw_material(dsn, bundle)
    grant_id = bundle.source.snapshot.chain_grant_ids[ancestor]
    with psycopg.connect(dsn) as conn:
        conn.execute("ALTER TABLE ag_grant_tokens DISABLE TRIGGER USER")
        conn.execute(
            "UPDATE ag_grant_tokens SET token_jws='invalid-signed-ancestor' WHERE grant_id=%s",
            (grant_id,),
        )
        conn.execute("ALTER TABLE ag_grant_tokens ENABLE TRIGGER USER")
    before = state(dsn)
    app = app_for(env, dsn)
    status, error, _ = request(
        app,
        path="/v1/operations/query",
        body=body,
        headers=[
            (b"content-type", b"application/json"),
            (b"authorization", b"AGPoP " + token),
            (b"ag-proof", proof),
        ],
    )
    assert status == 503 and error["error"]["code"] == "TRUSTED_STATE_UNAVAILABLE"
    assert state(dsn) == before
    app._executor.shutdown()


@pytest.mark.parametrize("mutation", ["scope", "constraints", "snapshot", "digest"])
def test_permission_bundle_cannot_substitute_authorization(ledger, dsn, downstream_dsn, mutation):
    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    bundle = query_bundle(env, accepted.operation_id)
    if mutation == "scope":
        bundle = replace(bundle, permissions=replace(bundle.permissions, scope=()))
    elif mutation == "constraints":
        bundle = replace(bundle, permissions=replace(bundle.permissions, chain=()))
    elif mutation == "snapshot":
        changed = replace(bundle.source.snapshot, subject="different-subject")
        bundle = replace(bundle, source=replace(bundle.source, snapshot=changed))
    else:
        bundle = replace(bundle, source=replace(bundle.source, digest="different-digest"))
    before = state(dsn)
    with pytest.raises(EvidenceError):
        AuthorizedQuery(dsn, evidence_store=env.evidence).query(bundle)
    assert state(dsn) == before


@pytest.mark.parametrize("fault", ["encoding", "byte-limit"])
def test_oversized_trusted_projection_rolls_back_query_proof(
    ledger, dsn, downstream_dsn, monkeypatch, fault
):
    from agent_guard.contracts.encoding import canonical_json_bytes
    from agent_guard.execution import query as query_module
    from tests.fixtures.gateway import app_for
    from tests.integration.test_gateway_http import send_bundle

    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    assert env.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
    bundle = query_bundle(env, accepted.operation_id)
    real = query_module.project_receipt

    def oversized(conn, operation_id):
        material = real(conn, operation_id)
        return replace(
            material,
            result_bytes=canonical_json_bytes(
                {"body": "private-oversized-marker" + "x" * (1024 * 1024)}
            ),
        )

    if fault == "encoding":
        monkeypatch.setattr(query_module, "project_receipt", oversized)
    else:
        # Layered negative control forces the explicit post-encoding byte guard
        # with otherwise genuine persisted projection; production cap is fixed.
        monkeypatch.setattr(query_module, "MAX_GATEWAY_RESPONSE_BYTES", 64)
    before = state(dsn)
    app = app_for(env, dsn)
    try:
        status, error, _ = send_bundle(app, dsn, bundle, query=True)
        assert status == 503 and error["error"]["code"] == "TRUSTED_STATE_UNAVAILABLE"
        assert "private-oversized-marker" not in str(error)
        assert state(dsn) == before
    finally:
        app._executor.shutdown()


CHANGES = {
    "tenant_id": "other",
    "task_id": "other",
    "root_id": "other",
    "tool_id": "document.read",
    "tool_version": "2",
    "idempotency_key": "other",
    "canonical_params": "e30",
    "ancestor_ids": [],
    "token_digest": "other",
    "proof_digest": "other",
    "intent_digest": "other",
    "token_exp": 1,
    "proof_iat": 1,
    "proof_exp": 2,
    "proof_jti": "other",
    "profile": "OTHER",
}


@pytest.mark.parametrize("field", CHANGES)
def test_original_context_same_shape_corruption(ledger, dsn, downstream_dsn, field):
    from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
    from tests.fixtures.gateway import app_for
    from tests.integration.test_gateway_http import send_bundle

    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    bundle = query_bundle(env, accepted.operation_id)
    with psycopg.connect(dsn) as conn:
        raw = bytes(
            conn.execute(
                "SELECT context_json FROM ag_verified_evidence WHERE evidence_ref="
                "(SELECT evidence_ref FROM ag_operations WHERE operation_id=%s)",
                (accepted.operation_id,),
            ).fetchone()[0]
        )
        context = load_strict_json(raw)
        assert context[field] != CHANGES[field]
        context[field] = CHANGES[field]
        conn.execute("ALTER TABLE ag_verified_evidence DISABLE TRIGGER USER")
        conn.execute(
            "UPDATE ag_verified_evidence SET context_json=%s WHERE evidence_ref="
            "(SELECT evidence_ref FROM ag_operations WHERE operation_id=%s)",
            (canonical_json_bytes(context), accepted.operation_id),
        )
        conn.execute("ALTER TABLE ag_verified_evidence ENABLE TRIGGER USER")
    before = state(dsn)
    app = app_for(env, dsn)
    try:
        status, error, _ = send_bundle(app, dsn, bundle, query=True)
        assert status == 503 and error["error"]["code"] == "TRUSTED_STATE_UNAVAILABLE"
        assert state(dsn) == before
    finally:
        app._executor.shutdown()


def test_new_query_proof_accepts_expired_original_proof(ledger, dsn, downstream_dsn):
    env = signed_env(dsn, downstream_dsn)
    original = env.bundle(proof_lifetime=1)
    accepted = env.adapter.accept(original)
    with psycopg.connect(dsn) as conn:
        _wait_expired(conn, datetime.fromtimestamp(original.invocation.proof_exp, timezone.utc))
    before = state(dsn, proofs=False)
    result = AuthorizedQuery(dsn, evidence_store=env.evidence).query(
        query_bundle(env, accepted.operation_id)
    )
    assert result["status"] == "RESERVED"
    assert state(dsn, proofs=False) == before


def _query_all_rows(dsn, prefix):
    """Audit every business table, separating permitted STAGED evidence."""
    with psycopg.connect(dsn) as conn:
        names = [
            row[0]
            for row in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname=current_schema() "
                "AND tablename LIKE %s ORDER BY tablename",
                (prefix + "%",),
            )
            if row[0] != "ag_verified_evidence"
        ]
        rows = {
            name: conn.execute(
                sql.SQL(
                    "SELECT row_to_json(t)::text FROM {} t ORDER BY row_to_json(t)::text"
                ).format(sql.Identifier(name))
            ).fetchall()
            for name in names
        }
        if prefix == "ag_":
            rows["accepted_verified_evidence"] = conn.execute(
                "SELECT row_to_json(e)::text FROM ag_operation_evidence l JOIN "
                "ag_verified_evidence e USING(evidence_ref) ORDER BY l.operation_id,l.kind"
            ).fetchall()
        return rows


def _rewrite_result(dsn, operation_id, result_bytes):
    with psycopg.connect(dsn) as conn:
        conn.execute("ALTER TABLE ag_receipt_outbox DISABLE TRIGGER USER")
        conn.execute(
            "UPDATE ag_receipt_outbox SET result_bytes=%s WHERE operation_id=%s",
            (result_bytes, operation_id),
        )
        conn.execute("ALTER TABLE ag_receipt_outbox ENABLE TRIGGER USER")


RESULT_FAULTS = [
    (shape, fault)
    for shape in ("order", "request", "document", "notification", "refusal")
    for fault in ("operation", "variant", "array")
] + [("order", "total")]


@pytest.mark.parametrize("shape,fault", RESULT_FAULTS)
def test_persisted_result_failure_repair_same_proof_and_replay(
    ledger, dsn, downstream_dsn, shape, fault
):
    from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
    from tests.fixtures.gateway import app_for
    from tests.integration.test_gateway_http import send_bundle

    env = signed_env(dsn, downstream_dsn)
    if shape == "notification":
        order = env.adapter.accept(env.bundle())
        assert env.service.run_operation(order.operation_id).status == "SUCCEEDED"
        first = env.bundle(
            "notify",
            tool="notification.template.send",
            params={
                "template_id": "order-created",
                "recipient_id": "user-demo-001",
                "operation_id": order.operation_id,
            },
        )
    elif shape in ("request", "document"):
        params = {"request_id": "req-001"}
        if shape == "document":
            params["document_id"] = "doc-001"
        first = env.bundle("read", tool=f"procurement.{shape}.read", params=params)
    else:
        first = env.bundle()
        if shape == "refusal":
            env.service._downstream._approved_suppliers = frozenset()
    accepted = env.adapter.accept(first)
    terminal = "FAILED" if shape == "refusal" else "SUCCEEDED"
    assert env.service.run_operation(accepted.operation_id).status == terminal
    bundle = query_bundle(env, accepted.operation_id)
    with psycopg.connect(dsn) as conn:
        raw = bytes(
            conn.execute(
                "SELECT result_bytes FROM ag_receipt_outbox WHERE operation_id=%s",
                (accepted.operation_id,),
            ).fetchone()[0]
        )
    original = load_strict_json(raw)
    corrupt = dict(original)
    if fault == "operation":
        corrupt["operation_id"] = "private-corrupt-result-marker"
    elif fault == "total":
        corrupt["total_fen"] += 1
    elif fault == "variant":
        corrupt = (
            {
                "kind": "refusal",
                "operation_id": accepted.operation_id,
                "tool_id": first.invocation.tool_id,
                "reason": "private-corrupt-result-marker",
            }
            if shape != "refusal"
            else {
                "kind": "read",
                "operation_id": accepted.operation_id,
                "tool_id": first.invocation.tool_id,
            }
        )
    _rewrite_result(
        dsn, accepted.operation_id, b"[]" if fault == "array" else canonical_json_bytes(corrupt)
    )
    before = _query_all_rows(dsn, "ag_")
    downstream = _query_all_rows(downstream_dsn, "ds_")
    assert {"ds_operations", "ds_orders", "ds_notifications"} <= downstream.keys()
    app = app_for(env, dsn)
    try:
        status, error, headers = send_bundle(app, dsn, bundle, query=True)
        assert status == 503 and error["error"]["code"] == "TRUSTED_STATE_UNAVAILABLE"
        assert "private-corrupt-result-marker" not in str(error)
        assert headers[b"cache-control"] == b"no-store" and headers[b"pragma"] == b"no-cache"
        assert _query_all_rows(dsn, "ag_") == before
        assert _query_all_rows(downstream_dsn, "ds_") == downstream
        _rewrite_result(dsn, accepted.operation_id, raw)
        repaired = _query_all_rows(dsn, "ag_")
        status, answer, _ = send_bundle(app, dsn, bundle, query=True)
        assert status == 200 and answer["status"] == terminal and answer["result"] == original
        assert answer["receipt_status"] == "PENDING" and answer["receipt_jws"] is None
        after = _query_all_rows(dsn, "ag_")
        assert len(after["ag_proofs"]) == len(repaired["ag_proofs"]) + 1
        assert {k: v for k, v in after.items() if k != "ag_proofs"} == {
            k: v for k, v in repaired.items() if k != "ag_proofs"
        }
        assert _query_all_rows(downstream_dsn, "ds_") == downstream
        status, error, _ = send_bundle(app, dsn, bundle, query=True)
        assert status == 409 and error["error"]["code"] == "REPLAY"
        assert _query_all_rows(dsn, "ag_") == after
        assert _query_all_rows(downstream_dsn, "ds_") == downstream
    finally:
        app._executor.shutdown()


@pytest.mark.parametrize("kind", ["typed-unrelated", "programming"])
def test_unrelated_projection_errors_remain_500_and_rollback(
    ledger, dsn, downstream_dsn, monkeypatch, kind
):
    from agent_guard.execution import query as query_module
    from tests.fixtures.gateway import app_for
    from tests.integration.test_gateway_http import send_bundle

    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    assert env.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
    bundle = query_bundle(env, accepted.operation_id)
    before = _query_all_rows(dsn, "ag_")
    downstream = _query_all_rows(downstream_dsn, "ds_")

    def unrelated(conn, operation_id):
        if kind == "typed-unrelated":
            raise ExecutionError(ExecutionErrorCode.LEASE_LOST)
        raise RuntimeError("private-programming-error-marker")

    monkeypatch.setattr(query_module, "project_receipt", unrelated)
    app = app_for(env, dsn)
    try:
        status, error, _ = send_bundle(app, dsn, bundle, query=True)
        assert status == 500 and error["error"]["code"] == "INTERNAL_ERROR"
        assert "private-programming-error-marker" not in str(error)
        assert _query_all_rows(dsn, "ag_") == before
        assert _query_all_rows(downstream_dsn, "ds_") == downstream
    finally:
        app._executor.shutdown()
