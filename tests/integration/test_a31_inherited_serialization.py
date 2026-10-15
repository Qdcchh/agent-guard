import json

import psycopg
import pytest

from agent_guard.contracts.ledger import ErrorCode, LedgerError
from tests.fixtures.receipts import full_state
from tests.integration.test_evidence_binding import _snapshot
from tests.integration.test_verified_execution import signed_env


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("failures", [1, 3])
def test_real_pg_serialization_retries_and_atomicity(
    ledger, dsn, downstream_dsn, monkeypatch, round_id, failures
):
    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    with psycopg.connect(dsn) as c:
        c.execute("CREATE TABLE review_serialization_sentinel (id int primary key, value int)")
        c.execute("INSERT INTO review_serialization_sentinel VALUES(1,0)")
        before = _snapshot(c)
    complete_before = full_state(dsn, downstream_dsn)
    attempts = []
    errors = []
    original_binding = env.evidence.binding

    def serializable(*a, **kw):
        c = psycopg.connect(*a, **kw)
        c.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
        return c

    monkeypatch.setattr(env.service._ledger, "_connector", serializable)

    def binding(bundle):
        original = original_binding(bundle)

        def collide(c, op, disposition):
            c.execute("SELECT value FROM review_serialization_sentinel WHERE id=1").fetchone()
            attempts.append(c.info.backend_pid)
            if len(attempts) <= failures:
                with psycopg.connect(dsn) as other:
                    assert other.info.backend_pid != c.info.backend_pid
                    other.execute(
                        "UPDATE review_serialization_sentinel SET value=value+1 WHERE id=1"
                    )
                try:
                    c.execute("UPDATE review_serialization_sentinel SET value=value+1 WHERE id=1")
                except psycopg.errors.SerializationFailure as exc:
                    errors.append(exc.sqlstate)
                    raise

        return original.compose(collide)

    monkeypatch.setattr(env.evidence, "binding", binding)
    try:
        if failures == 3:
            with pytest.raises(LedgerError) as caught:
                env.adapter.accept(bundle)
            assert caught.value.code is ErrorCode.TRUSTED_STATE_UNAVAILABLE
            assert caught.value.__cause__.sqlstate == "40001"
            assert len(attempts) == 3 and len(set(attempts)) == 3
            with psycopg.connect(dsn) as c:
                assert _snapshot(c) == before
                assert full_state(dsn, downstream_dsn) == complete_before
                assert c.execute("SELECT count(*) FROM ag_operation_review_flags").fetchone() == (
                    0,
                )
            monkeypatch.setattr(env.evidence, "binding", original_binding)
            accepted = env.adapter.accept(bundle)
        else:
            accepted = env.adapter.accept(bundle)
            assert len(attempts) == 2 and len(set(attempts)) == 2
        assert errors == ["40001"] * failures
        with psycopg.connect(dsn) as c:
            assert c.execute("SELECT count(*) FROM ag_operations").fetchone() == (1,)
            assert c.execute("SELECT count(*) FROM ag_proofs").fetchone() == (
                len(before["ag_proofs"]) + 1,
            )
            assert c.execute(
                "SELECT count(*) FROM ag_proofs WHERE proof_jti=%s", (bundle.invocation.proof_jti,)
            ).fetchone() == (1,)
            assert c.execute("SELECT count(*) FROM ag_operation_evidence").fetchone() == (1,)
        assert env.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
        print(
            "REAL_SERIALIZATION_WITNESS "
            + json.dumps(
                {
                    "round": round_id,
                    "backend_pids": attempts,
                    "sqlstates": errors,
                    "retry_success": True,
                    "atomicity": True,
                }
            )
        )
    finally:
        with psycopg.connect(dsn) as c:
            c.execute("DROP TABLE review_serialization_sentinel")
