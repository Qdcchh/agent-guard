"""Real evidence-store access, immutability and post-write expiry rollback."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone

import psycopg
import pytest
from psycopg import sql

from agent_guard.contracts.ledger import AcceptDisposition, ErrorCode, LedgerError
from tests.integration.test_consent_final_decision import _wait_blocked, _wait_expired
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


def _legacy_all_ag_snapshot(conn):
    names = [
        row[0]
        for row in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname=current_schema() "
            "AND left(tablename,3)='ag_' ORDER BY tablename"
        )
    ]
    return {
        name: conn.execute(
            sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY row_to_json(t)::text").format(
                sql.Identifier(name)
            )
        ).fetchall()
        for name in names
    }


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("path", ["before-created", "after-created", "after-existing"])
@pytest.mark.parametrize("expiry", ["proof", "token"])
@pytest.mark.parametrize("positive", [False, True])
def test_legacy_hook_final_clock_and_whole_rollback(
    ledger, tree, dsn, round_id, path, expiry, positive
):
    # Explicit trusted A1 context: this probes the ledger callback boundary,
    # while the existing signed tests above and below cover public verification.
    original = tree.invocation()
    first = ledger.accept(original, tree.cost(amount_fen=100))
    assert first.status == "RESERVED"
    with psycopg.connect(dsn, autocommit=True) as observer:
        assert observer.execute("SELECT count(*) FROM ag_audit_streams").fetchone() == (0,)
        now = int(observer.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0])
        current = (
            replace(
                original,
                proof_jti=original.proof_jti + "-fresh",
                proof_digest=original.proof_digest + "-fresh",
                evidence_ref=original.evidence_ref + "-fresh",
            )
            if path == "after-existing"
            else tree.invocation()
        )
        current = replace(
            current,
            proof_iat=now,
            proof_exp=now + 3 if expiry == "proof" else now + 30,
            token_exp=now + 3 if expiry == "token" else now + 300,
        )
        target = current.proof_exp if expiry == "proof" else current.token_exp
        before = _legacy_all_ag_snapshot(observer)
        calls = []
        observations = []

        def wait(conn, *args):
            calls.append(path)
            if path != "before-created":
                assert args[1] is (
                    AcceptDisposition.EXISTING
                    if path == "after-existing"
                    else AcceptDisposition.CREATED
                )
                assert args[2] is None
            limit = time.monotonic() + 8
            while True:
                observed = int(
                    conn.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0]
                )
                observations.append(observed)
                if positive or observed > target:
                    break
                assert time.monotonic() < limit, (
                    "must cross the real DB deadline within eight seconds"
                )
                time.sleep(0.01)
            if positive:
                conn.execute("SELECT pg_sleep(0.01)")
                observations.append(
                    int(conn.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0])
                )
            return None

        def forbidden_before_create(*args):
            pytest.fail("EXISTING must never execute before_create")

        kwargs = {"before_create": wait} if path == "before-created" else {"after_link": wait}
        if path == "after-existing":
            kwargs["before_create"] = forbidden_before_create
        if positive:
            result = ledger.accept(current, tree.cost(amount_fen=100), **kwargs)
            assert result.disposition is (
                AcceptDisposition.EXISTING
                if path == "after-existing"
                else AcceptDisposition.CREATED
            )
            if path == "after-existing":
                assert result.operation_id == first.operation_id
            assert observations[0] <= observations[-1] < target
            after = _legacy_all_ag_snapshot(observer)
            expected = (
                {"ag_proofs"}
                if path == "after-existing"
                else {
                    "ag_event_seals",
                    "ag_grants",
                    "ag_ledger_event_nodes",
                    "ag_ledger_events",
                    "ag_operations",
                    "ag_proofs",
                }
            )
            assert {name for name in before if before[name] != after[name]} == expected
            assert len(after["ag_proofs"]) == len(before["ag_proofs"]) + 1
            assert len(after["ag_operations"]) == len(before["ag_operations"]) + (
                0 if path == "after-existing" else 1
            )
        else:
            with pytest.raises(LedgerError) as failure:
                ledger.accept(current, tree.cost(amount_fen=100), **kwargs)
            assert failure.value.code is (
                ErrorCode.STALE_REQUEST if expiry == "proof" else ErrorCode.EXPIRED
            )
            assert observations[0] <= target < observations[-1]
            assert _legacy_all_ag_snapshot(observer) == before
        assert calls == [path]


def _snapshot(conn):
    names = (
        "ag_operations",
        "ag_proofs",
        "ag_ledger_events",
        "ag_ledger_event_nodes",
        "ag_operation_evidence",
        "ag_grants",
    )
    return {
        name: conn.execute(
            sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY row_to_json(t)::text").format(
                sql.Identifier(name)
            )
        ).fetchall()
        for name in names
    }


def _install_wait(conn, mode, key):
    conn.execute(
        sql.SQL(
            "CREATE FUNCTION ag_test_evidence_wait() RETURNS trigger AS $$ "
            "BEGIN PERFORM pg_advisory_xact_lock({}); RETURN NEW; END $$ LANGUAGE plpgsql"
        ).format(sql.Literal(key))
    )
    table = "ag_proofs" if mode == "proof-link" else "ag_operation_evidence"
    if mode == "deferred":
        conn.execute(
            "CREATE CONSTRAINT TRIGGER ag_test_evidence_wait_trg AFTER INSERT ON "
            "ag_operation_evidence DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION ag_test_evidence_wait()"
        )
        fragment = "SET CONSTRAINTS ALL IMMEDIATE"
    else:
        action = "UPDATE" if mode == "proof-link" else "INSERT"
        conn.execute(
            sql.SQL(
                "CREATE TRIGGER ag_test_evidence_wait_trg AFTER {} ON {} "
                "FOR EACH ROW EXECUTE FUNCTION ag_test_evidence_wait()"
            ).format(sql.SQL(action), sql.Identifier(table))
        )
        fragment = (
            "UPDATE ag_proofs" if mode == "proof-link" else "INSERT INTO ag_operation_evidence"
        )
    return table, fragment


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("mode", ["evidence", "proof-link", "deferred"])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("positive", [False, True])
def test_bound_accept_final_clock_after_every_wait(
    ledger, dsn, downstream_dsn, round_id, mode, existing, positive
):
    env = signed_env(dsn, downstream_dsn)
    if existing:
        first = env.adapter.accept(env.bundle())
    # A one-second real signed proof, with enough time to deterministically reach
    # the barrier. No widened TTL or fake clock is used.
    while time.time() % 1 > 0.2:
        time.sleep(0.01)
    bundle = env.bundle(proof_lifetime=1)
    deadline = datetime.fromtimestamp(bundle.invocation.proof_exp, tz=timezone.utc)
    key = 82716291
    with psycopg.connect(dsn, autocommit=True) as observer:
        before = _snapshot(observer)
        table, fragment = _install_wait(observer, mode, key)
        try:
            with psycopg.connect(dsn) as blocker, ThreadPoolExecutor(1) as pool:
                blocker.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
                future = pool.submit(env.adapter.accept, bundle)
                _wait_blocked(observer, blocker.info.backend_pid, fragment)
                if not positive:
                    _wait_expired(observer, deadline)
                blocker.commit()
                if positive:
                    result = future.result(timeout=5)
                    assert result.disposition is (
                        AcceptDisposition.EXISTING if existing else AcceptDisposition.CREATED
                    )
                    if existing:
                        assert result.operation_id == first.operation_id
                else:
                    with pytest.raises(LedgerError) as failure:
                        future.result(timeout=5)
                    assert failure.value.code is ErrorCode.STALE_REQUEST
                    assert _snapshot(observer) == before
        finally:
            observer.execute(
                sql.SQL("DROP TRIGGER ag_test_evidence_wait_trg ON {}").format(
                    sql.Identifier(table)
                )
            )
            observer.execute("DROP FUNCTION ag_test_evidence_wait()")
        if not positive:
            # Whole rollback leaves this business request retryable with a new
            # proof, rather than poisoning anti-replay or reserving twice.
            retried = env.adapter.accept(env.bundle())
            assert retried.disposition is (
                AcceptDisposition.EXISTING if existing else AcceptDisposition.CREATED
            )


@pytest.mark.parametrize("accepted", [False, True])
def test_evidence_immutable_and_nonprivileged_role_refused(ledger, dsn, downstream_dsn, accepted):
    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    if accepted:
        env.adapter.accept(bundle)
    import json
    import uuid

    from tests.fixtures.a31_common import namespace_evidence

    evidence_path = namespace_evidence(dsn)
    marker = json.loads(evidence_path.read_text())
    role = "ag31_untrusted_" + uuid.uuid4().hex
    owner_marker = "AG31_UNTRUSTED:" + marker["run_id"] + ":" + marker["schema"] + ":" + role
    created = False
    oid = None
    try:
        with psycopg.connect(dsn) as owner:
            assert owner.execute("SELECT current_database(),current_schema()").fetchone() == (
                marker["database"],
                marker["schema"],
            )
            assert owner.execute(
                "SELECT run_id,database_name FROM ag_test_ownership"
            ).fetchone() == (marker["run_id"], marker["database"])
            assert (
                owner.execute("SELECT oid FROM pg_roles WHERE rolname=%s", (role,)).fetchone()
                is None
            )
            owner.execute(
                sql.SQL(
                    "CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHE"
                    "RIT NOREPLICATION NOBYPASSRLS"
                ).format(sql.Identifier(role))
            )
            owner.execute(
                sql.SQL("COMMENT ON ROLE {} IS {}").format(
                    sql.Identifier(role), sql.Literal(owner_marker)
                )
            )
            owner.execute(
                sql.SQL("GRANT {} TO {} WITH ADMIN FALSE, INHERIT FALSE, SET TRUE").format(
                    sql.Identifier(role), sql.Identifier(owner.info.user)
                )
            )
            owner.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(marker["schema"]), sql.Identifier(role)
                )
            )
            row = owner.execute(
                "SELECT oid,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolinhe"
                "rit,rolreplication,rolbypassrls,shobj_description(oid,'pg_authid'"
                ") FROM pg_roles WHERE rolname=%s",
                (role,),
            ).fetchone()
            oid = row[0]
            assert row[1:8] == (False,) * 7 and row[8] == owner_marker
            membership = owner.execute(
                "SELECT admin_option,inherit_option,set_option FROM pg_auth_member"
                "s WHERE roleid=%s AND member=(SELECT oid FROM pg_roles WHERE roln"
                "ame=current_user)",
                (oid,),
            ).fetchone()
            assert membership == (False, False, True)
        created = True
        role_path = evidence_path.parent / (role + ".created.json")
        role_path.write_text(
            json.dumps(
                {
                    "role": role,
                    "oid": oid,
                    "owner_marker": owner_marker,
                    "flags": row[1:8],
                    "membership": membership,
                    "namespace": marker,
                },
                sort_keys=True,
            )
            + "\n"
        )
        role_path.chmod(0o600)
        with psycopg.connect(dsn) as conn:
            schema = conn.execute("SELECT current_schema()").fetchone()[0]
            for table in ["ag_verified_evidence"] + (["ag_operation_evidence"] if accepted else []):
                for action in [
                    f"UPDATE {table} SET evidence_ref=evidence_ref",
                    f"DELETE FROM {table}",
                ]:
                    with pytest.raises(psycopg.errors.CheckViolation) as failure:
                        with conn.transaction():
                            conn.execute(action)
                    assert failure.value.sqlstate == "23514"
                # Roll back this savepoint so SET LOCAL ROLE cannot survive into
                # the surrounding connection transaction or the next table probe.
                with conn.transaction(force_rollback=True):
                    conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                    assert conn.execute("SELECT current_user").fetchone() == (role,)
                    with pytest.raises(psycopg.errors.InsufficientPrivilege) as failure:
                        with conn.transaction():
                            conn.execute(
                                sql.SQL("SELECT * FROM {}").format(sql.Identifier(schema, table))
                            )
                    assert failure.value.sqlstate == "42501"
            assert conn.execute("SELECT count(*) FROM ag_verified_evidence").fetchone() == (1,)
    finally:
        if created:
            with psycopg.connect(dsn) as owner:
                assert owner.execute(
                    "SELECT oid,shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname=%s",
                    (role,),
                ).fetchone() == (oid, owner_marker)
                assert owner.execute(
                    "SELECT run_id,database_name FROM ag_test_ownership"
                ).fetchone() == (marker["run_id"], marker["database"])
                owner.execute(
                    sql.SQL("REVOKE USAGE ON SCHEMA {} FROM {}").format(
                        sql.Identifier(marker["schema"]), sql.Identifier(role)
                    )
                )
                owner.execute(
                    sql.SQL("REVOKE {} FROM {}").format(
                        sql.Identifier(role), sql.Identifier(owner.info.user)
                    )
                )
                owner.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
                assert (
                    owner.execute("SELECT oid FROM pg_roles WHERE rolname=%s", (role,)).fetchone()
                    is None
                )
            removed = evidence_path.parent / (role + ".removed.json")
            removed.write_text(
                json.dumps(
                    {
                        "role": role,
                        "oid": oid,
                        "owner_marker": owner_marker,
                        "remaining": 0,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
            removed.chmod(0o600)


def test_stage_insert_failure_has_no_accept_effect(ledger, dsn, downstream_dsn):
    env = signed_env(dsn, downstream_dsn)
    with psycopg.connect(dsn, autocommit=True) as conn:
        before = _snapshot(conn)
        conn.execute(
            (
                "CREATE FUNCTION ag_test_stage_fail() RETURNS trigger AS $$ BEGIN "
                "RAISE EXCEPTION 'test stage failure' USING ERRCODE='23514'; END "
                "$$ LANGUAGE plpgsql"
            )
        )
        conn.execute(
            (
                "CREATE TRIGGER ag_test_stage_fail_trg BEFORE INSERT ON "
                "ag_verified_evidence FOR EACH ROW EXECUTE FUNCTION "
                "ag_test_stage_fail()"
            )
        )
        try:
            with pytest.raises(psycopg.errors.CheckViolation):
                env.bundle()
            assert _snapshot(conn) == before
            assert conn.execute("SELECT count(*) FROM ag_verified_evidence").fetchone() == (0,)
        finally:
            conn.execute("DROP TRIGGER ag_test_stage_fail_trg ON ag_verified_evidence")
            conn.execute("DROP FUNCTION ag_test_stage_fail()")


def test_binding_backend_death_rolls_back_without_quarantine(
    ledger, dsn, downstream_dsn, monkeypatch
):
    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    original = env.evidence.binding

    def terminate(bundle):
        normal = original(bundle)

        def bind(conn, operation, disposition):
            conn.execute("SELECT pg_terminate_backend(pg_backend_pid())")

        return normal.compose(bind)

    monkeypatch.setattr(env.evidence, "binding", terminate)
    with psycopg.connect(dsn) as conn:
        before = _snapshot(conn)
    with pytest.raises(LedgerError) as failure:
        env.adapter.accept(bundle)
    assert failure.value.code is ErrorCode.TRUSTED_STATE_UNAVAILABLE
    assert failure.value.__cause__.sqlstate == "57P01"
    print("DB_FAILURE_WITNESS own_backend_terminated sqlstate=57P01 rollback=required")
    with psycopg.connect(dsn) as conn:
        assert _snapshot(conn) == before
        assert conn.execute("SELECT count(*) FROM ag_operation_review_flags").fetchone() == (0,)


def test_legacy_first_material_is_not_fabricated_from_new_retry(ledger, dsn, downstream_dsn):
    from agent_guard.authorization.evidence_store import EvidenceError

    env = signed_env(dsn, downstream_dsn)
    original = env.bundle()
    # Deliberately exercise the retained legacy API, which has no evidence hook.
    accepted = env.service.accept_invocation(original.invocation, original.permissions)
    with psycopg.connect(dsn) as conn:
        before = _snapshot(conn)
    with pytest.raises(EvidenceError, match="legacy operation"):
        env.adapter.accept(env.bundle())
    with psycopg.connect(dsn) as conn:
        assert _snapshot(conn) == before
        assert conn.execute("SELECT count(*) FROM ag_operation_evidence").fetchone() == (0,)
        assert conn.execute(
            "SELECT evidence_ref FROM ag_operations WHERE operation_id=%s",
            (accepted.operation_id,),
        ).fetchone() == (original.evidence_ref,)


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("window", ["token", "ancestor"])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("positive", [False, True])
def test_bound_ledger_final_token_and_ancestor_windows(
    ledger, dsn, round_id, window, existing, positive
):
    """Layered A-clock probe complements the genuinely signed proof cases above."""
    from datetime import timedelta

    from tests.fixtures.state import build_tree

    while time.time() % 1 > 0.2:
        time.sleep(0.01)
    end = datetime.now(timezone.utc) + timedelta(seconds=0.5 if window == "ancestor" else 30)
    with psycopg.connect(dsn) as conn:
        tree = build_tree(conn, valid_until=end)
    key = "late-window"
    if existing:
        ledger.accept(tree.invocation(idempotency_key=key), tree.cost(100))
    verified = tree.invocation(
        idempotency_key=key,
        token_exp=int(time.time()) + (1 if window == "token" else 60),
    )
    deadline = (
        end if window == "ancestor" else datetime.fromtimestamp(verified.token_exp, tz=timezone.utc)
    )
    lock_key = 8517291

    def binding(conn, operation, disposition):
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

    with psycopg.connect(dsn, autocommit=True) as observer:
        before = _snapshot(observer)
        with psycopg.connect(dsn) as blocker, ThreadPoolExecutor(1) as pool:
            blocker.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            future = pool.submit(
                ledger.accept_bound,
                verified,
                tree.cost(100),
                existing_validator=lambda *_: None,
                binding=binding,
            )
            _wait_blocked(observer, blocker.info.backend_pid, "pg_advisory_xact_lock")
            if not positive:
                _wait_expired(observer, deadline)
            blocker.commit()
            if positive:
                assert future.result(timeout=5).disposition is (
                    AcceptDisposition.EXISTING if existing else AcceptDisposition.CREATED
                )
            else:
                with pytest.raises(LedgerError) as failure:
                    future.result(timeout=5)
                assert failure.value.code is ErrorCode.EXPIRED
                assert _snapshot(observer) == before
