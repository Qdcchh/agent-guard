"""Last real authorization clock after each added journal dependency wait."""

from builtins import ExceptionGroup
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from agent_guard.audit import journal
from agent_guard.contracts.ledger import LedgerError
from agent_guard.execution.query import AuthorizedQuery
from agent_guard.ledger import store as ledger_store
from tests.fixtures.a31_common import (
    state,
    wait_for_blocked,
    wait_past_database_deadline,
)
from tests.fixtures.gateway import query_bundle, signed_env_window
from tests.fixtures.receipts import (
    accept_created_only,
    accept_retry_only,
    result_read_only,
)
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("interaction", ("invoke", "query"))
@pytest.mark.parametrize("phase", ("capture", "link", "head", "flush"))
@pytest.mark.parametrize("window", ("proof", "token", "root", "mid", "leaf"))
@pytest.mark.parametrize("expired", (False, True))
def test_final_public_clock_after_journal_wait(
    ledger, dsn, downstream_dsn, monkeypatch, interaction, phase, window, expired, round
):
    env = (
        signed_env(dsn, downstream_dsn)
        if window == "proof"
        else signed_env_window(dsn, downstream_dsn, "leaf" if window == "token" else window)
    )
    first = (
        env.bundle(tool="procurement.request.read", params={"request_id": "req-001"})
        if phase == "capture" and interaction == "invoke"
        else env.bundle()
    )
    op = env.adapter.accept(first).operation_id
    bundle = (
        env.bundle(proof_lifetime=2)
        if interaction == "invoke" and window == "proof"
        else env.bundle()
        if interaction == "invoke"
        else query_bundle(env, op, lifetime=2 if window == "proof" else 60)
    )
    context = bundle.invocation if interaction == "invoke" else bundle.query
    before = state(dsn, downstream_dsn)
    original = None
    with (
        psycopg.connect(dsn) as lock,
        psycopg.connect(dsn, autocommit=True) as observer,
    ):
        schema, database = observer.execute("SELECT current_schema(),current_database()").fetchone()
        run_id, owner_database = observer.execute(
            "SELECT run_id,database_name FROM ag_test_ownership"
        ).fetchone()
        assert schema == "ag_test_run_" + run_id and database == owner_database
        marker = int(run_id, 16)
        assert 0 < marker < 2**48
        print("CLOCK_SCOPE_LOCK", schema, database, run_id, marker)
        lock.execute("SET LOCAL lock_timeout='180s'")
        if window == "proof":
            deadline = context.proof_exp
        elif window == "token":
            deadline = context.token_exp
        else:
            depth = {"root": 0, "mid": 1, "leaf": 2}[window]
            deadline = observer.execute(
                "SELECT extract(epoch FROM expires_at) FROM ag_grants WHERE depth=%s",
                (depth,),
            ).fetchone()[0]
        if phase == "head":
            lock.execute("SELECT head_seq FROM ag_audit_streams FOR UPDATE")
            wait_table = "ag_audit_streams"
        else:
            lock.execute("SELECT pg_advisory_xact_lock(%s)", (marker,))
            wait_table = "pg_advisory_xact_lock"
            if phase == "capture" and interaction == "invoke":
                original = journal.capture_empty_task_tx

                def capture(conn, context):
                    baseline = original(conn, context)
                    conn.execute("SELECT pg_advisory_xact_lock(%s)", (marker,))
                    return baseline

                # A fresh CREATED intent exercises the structural capture hook.
                bundle = env.bundle(
                    "new-clock-key",
                    proof_lifetime=2 if window == "proof" else 60,
                )
                context = bundle.invocation
                deadline = context.proof_exp if window == "proof" else deadline
                before = state(dsn, downstream_dsn)
                monkeypatch.setattr(journal, "capture_empty_task_tx", capture)
            elif phase in ("capture", "link"):
                original = ledger_store.link_proof_to_operation

                def link(conn, **kwargs):
                    original(conn, **kwargs)
                    conn.execute("SELECT pg_advisory_xact_lock(%s)", (marker,))

                monkeypatch.setattr(ledger_store, "link_proof_to_operation", link)
            else:
                wait_table = "SET CONSTRAINTS ALL IMMEDIATE"
                observer.execute(
                    "CREATE FUNCTION ag_test_audit_flush_wait() RETURNS trigger "
                    "LANGUAGE plpgsql AS $$ "
                    f"BEGIN PERFORM pg_advisory_xact_lock({marker}); RETURN NULL; END $$"
                )
                observer.execute(
                    "CREATE CONSTRAINT TRIGGER ag_test_audit_flush_wait AFTER INSERT "
                    "ON ag_audit_records "
                    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
                    "ag_test_audit_flush_wait()"
                )
        blocker = lock.execute("SELECT pg_backend_pid()").fetchone()[0]
        # Finite lock limits exceed the tested expiry; no timeout substitutes for
        # the requested final EXPIRED/STALE_REQUEST authorization decision.
        env.service._ledger._lock_timeout_ms = 180000
        env.service._ledger._statement_timeout_ms = 180000
        invoke = (
            (lambda: env.adapter.accept(bundle))
            if interaction == "invoke"
            else (lambda: AuthorizedQuery(dsn, evidence_store=env.evidence).query(bundle))
        )
        if interaction == "query":
            query = AuthorizedQuery(dsn, evidence_store=env.evidence)
            query._ledger._lock_timeout_ms = 180000
            query._ledger._statement_timeout_ms = 180000

            def invoke():
                return query.query(bundle)

        clocks = observer.execute(
            "SELECT grant_id,extract(epoch FROM expires_at) FROM ag_grants ORDER BY depth"
        ).fetchall()
        print("CLOCK_DEADLINES", window, context.token_exp, context.proof_exp, deadline, clocks)
        assert (
            context.proof_exp < context.token_exp
            if window == "proof"
            else context.proof_exp > deadline
        )
        try:
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(invoke)
                try:
                    try:
                        pids = wait_for_blocked(
                            observer,
                            blocker_pid=blocker,
                            table=wait_table,
                            futures=(future,),
                            advisory_key=None if phase == "head" else marker,
                        )
                        assert len(pids) == 1
                        if expired:
                            wait_past_database_deadline(observer, deadline)
                        else:
                            assert (
                                observer.execute(
                                    "SELECT extract(epoch FROM clock_timestamp())"
                                ).fetchone()[0]
                                < deadline
                            )
                    finally:
                        lock.commit()
                except Exception as observation:
                    try:
                        future.result(180)
                    except Exception as child:
                        if child is observation:
                            raise
                        raise ExceptionGroup(
                            "wait observation and actual worker failure",
                            [observation, child],
                        ) from child
                    raise
                if expired:
                    with pytest.raises(LedgerError) as caught:
                        future.result(180)
                    assert caught.value.code.value == (
                        "STALE_REQUEST" if window == "proof" else "EXPIRED"
                    )
                    assert state(dsn, downstream_dsn) == before
                else:
                    returned = future.result(180)
                    if interaction == "query":
                        assert returned["operation_id"] == op
                        result_read_only(
                            before,
                            state(dsn, downstream_dsn),
                            evidence_ref=bundle.evidence_ref,
                            proof_jti=context.proof_jti,
                            operation_id=op,
                        )
                    elif phase != "capture":
                        assert returned.operation_id == op
                        accept_retry_only(
                            before,
                            state(dsn, downstream_dsn),
                            evidence_ref=bundle.evidence_ref,
                            proof_jti=context.proof_jti,
                            operation_id=op,
                        )
                    else:
                        assert returned.operation_id != op
                        accept_created_only(
                            before,
                            state(dsn, downstream_dsn),
                            bundle=bundle,
                            result=returned,
                        )
        finally:
            lock.rollback()
            if phase == "flush":
                observer.execute("DROP TRIGGER ag_test_audit_flush_wait ON ag_audit_records")
                observer.execute("DROP FUNCTION ag_test_audit_flush_wait()")


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("window", ("proof", "token", "root", "mid", "leaf"))
@pytest.mark.parametrize("phase", ("capture", "chunks"))
@pytest.mark.parametrize("expired", (False, True))
def test_initial_seed_and_chunk_wait(
    ledger, dsn, downstream_dsn, monkeypatch, phase, window, expired, round
):
    import json

    from agent_guard.audit.contracts import EmptyTaskBootstrapSeed
    from tests.fixtures.a31_common import namespace_evidence
    from tests.fixtures.receipts import accept_initial_only

    env = (
        signed_env(dsn, downstream_dsn)
        if window == "proof"
        else signed_env_window(dsn, downstream_dsn, "leaf" if window == "token" else window)
    )
    bundle = env.bundle(proof_lifetime=2 if window == "proof" else 60)
    context = bundle.invocation
    before = state(dsn, downstream_dsn)
    captured = []
    original = journal.capture_empty_task_tx
    with psycopg.connect(dsn) as blocker, psycopg.connect(dsn, autocommit=True) as observer:
        schema, database = observer.execute("SELECT current_schema(),current_database()").fetchone()
        run, owned_database = observer.execute(
            "SELECT run_id,database_name FROM ag_test_ownership"
        ).fetchone()
        assert schema == "ag_test_run_" + run and database == owned_database
        marker = int(run, 16)
        assert 0 < marker < 2**48
        blocker.execute("SELECT pg_advisory_xact_lock(%s)", (marker,))
        pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]

        def capture(conn, ctx):
            seed = original(conn, ctx)
            assert type(seed) is EmptyTaskBootstrapSeed
            assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (0,)
            assert conn.execute("SELECT count(*) FROM ag_ledger_events").fetchone() == (0,)
            captured.append(seed)
            if phase == "capture":
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (marker,))
            return seed

        monkeypatch.setattr(journal, "capture_empty_task_tx", capture)
        if phase == "chunks":
            observer.execute(
                f"CREATE FUNCTION ag_test_initial_chunk_wait() RETURNS trigger LANGUAGE "
                f"plpgsql AS $$ BEGIN PERFORM pg_advisory_xact_lock({marker}); RETURN "
                f"NEW; END $$"
            )
            observer.execute(
                "CREATE TRIGGER ag_test_initial_chunk_wait BEFORE INSERT ON "
                "ag_audit_bootstrap_chunks FOR EACH ROW EXECUTE FUNCTION "
                "ag_test_initial_chunk_wait()"
            )
        deadline = (
            context.proof_exp
            if window == "proof"
            else context.token_exp
            if window == "token"
            else observer.execute(
                "SELECT extract(epoch FROM expires_at) FROM ag_grants WHERE depth=%s",
                ({"root": 0, "mid": 1, "leaf": 2}[window],),
            ).fetchone()[0]
        )
        env.service._ledger._lock_timeout_ms = 180000
        env.service._ledger._statement_timeout_ms = 180000
        details = {
            "schema": schema,
            "database": database,
            "run_id": run,
            "marker": marker,
            "blocker_pid": pid,
            "deadline": str(deadline),
            "proof_exp": context.proof_exp,
            "token_exp": context.token_exp,
        }
        target = namespace_evidence(dsn).parent / (run + "-initial-wait")
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        evidence = target / f"{expired}-{phase}-{window}-{round}.json"
        result = None
        try:
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(env.adapter.accept, bundle)
                try:
                    try:
                        details["waiter_pids"] = wait_for_blocked(
                            observer,
                            blocker_pid=pid,
                            table="pg_advisory_xact_lock"
                            if phase == "capture"
                            else "INSERT INTO ag_audit_bootstrap_chunks",
                            futures=(future,),
                            advisory_key=marker,
                        )
                        assert len(details["waiter_pids"]) == 1
                        if expired:
                            wait_past_database_deadline(observer, deadline)
                        else:
                            assert (
                                observer.execute(
                                    "SELECT extract(epoch FROM clock_timestamp())"
                                ).fetchone()[0]
                                < deadline
                            )
                    finally:
                        blocker.commit()
                except Exception as observation:
                    try:
                        future.result(180)
                    except Exception as child:
                        if child is observation:
                            raise
                        raise ExceptionGroup(
                            "observation and actual initial-worker failure", [observation, child]
                        ) from child
                    raise
                if expired:
                    with pytest.raises(LedgerError) as caught:
                        future.result(180)
                    details["code"] = caught.value.code.value
                    assert details["code"] == ("STALE_REQUEST" if window == "proof" else "EXPIRED")
                    assert state(dsn, downstream_dsn) == before
                else:
                    result = future.result(180)
                    assert result.cost.amount_fen == 70000
                    assert len(captured) == 1
                    accept_initial_only(
                        before,
                        state(dsn, downstream_dsn),
                        seed=captured[0],
                        bundle=bundle,
                        result=result,
                    )
        finally:
            blocker.rollback()
            after = state(dsn, downstream_dsn)
            evidence.write_text(
                json.dumps(
                    {
                        "details": details,
                        "before": before,
                        "after": after,
                        "captured_seed": None
                        if not captured
                        else {
                            "tx_id": captured[0].tx_id,
                            "origin": captured[0].origin,
                            "objects": [
                                [o.kind, o.object_id, o.raw.hex(), o.digest]
                                for o in captured[0].objects
                            ],
                            "manifest_raw": captured[0].manifest_bytes.hex(),
                            "counts": [
                                captured[0].object_count,
                                captured[0].chunk_count,
                                captured[0].wire_bytes,
                            ],
                        },
                    },
                    indent=2,
                )
                + "\n"
            )
            if phase == "chunks":
                observer.execute(
                    "DROP TRIGGER ag_test_initial_chunk_wait ON ag_audit_bootstrap_chunks"
                )
                observer.execute("DROP FUNCTION ag_test_initial_chunk_wait()")
