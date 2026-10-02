"""A2-P13: concurrent accept / settle / recovery against real ancestor budgets.

Every round builds isolated data and races real concurrent work coordinated by
``threading.Barrier``; each racer opens its own database connection. No sleeps
are used for ordering and no sequential loop stands in for concurrency. Each
round asserts that every ancestor stays inside its limit and that nothing goes
negative.
"""

from __future__ import annotations

import threading

import psycopg
import pytest

from agent_guard.contracts.execution import ExecutionError, OperationStatus
from agent_guard.contracts.ledger import AcceptDisposition, ErrorCode, LedgerError
from tests.fixtures.dbstate import fetch_counters, fetch_counts
from tests.fixtures.execution import (
    RECIPIENT_ID,
    REQUEST_ID,
    SUPPLIER_ID,
    build_env,
    order_params,
    permission_for,
    read_params,
)
from tests.fixtures.isolation import reset_state
from tests.fixtures.state import build_tree

pytestmark = pytest.mark.integration

ROUNDS = 10


class _Grant:
    def __init__(self, grant_id, amount_limit, call_limit):
        self.grant_id = grant_id
        self.amount_limit = amount_limit
        self.call_limit = call_limit


def assert_within_limits(dsn, grants):
    for grant in grants:
        counters = fetch_counters(dsn, grant.grant_id)
        for key in ("amount_reserved", "amount_settled", "calls_reserved", "calls_settled"):
            assert counters[key] >= 0, f"{grant.grant_id}.{key} = {counters[key]}"
        assert counters["amount_reserved"] + counters["amount_settled"] <= grant.amount_limit, (
            f"{grant.grant_id} amount over limit: {counters}"
        )
        assert counters["calls_reserved"] + counters["calls_settled"] <= grant.call_limit, (
            f"{grant.grant_id} calls over limit: {counters}"
        )


def make_env(a2, tree):
    """A fully independent service instance: its own connections and downstream."""
    return build_env(
        tree=tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        approved_suppliers=(SUPPLIER_ID,),
        approved_recipients=(RECIPIENT_ID,),
        served_requests=(REQUEST_ID,),
    )


def _race(callables):
    barrier = threading.Barrier(len(callables))
    results: list[tuple[str, object]] = []
    lock = threading.Lock()

    def runner(fn):
        barrier.wait()
        try:
            value = fn()
            with lock:
                results.append(("ok", value))
        except (ExecutionError, LedgerError) as exc:
            with lock:
                results.append(("err", exc))

    threads = [threading.Thread(target=runner, args=(fn,)) for fn in callables]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


# --------------------------------------------------- root budget contention


def test_p13_two_draws_race_for_the_root_budget(a2, namespace):
    """P13: a mid-level draw and a leaf-level draw race for one root budget.

    Both consume the same root allowance, so exactly one accept wins and the
    other is a budget rejection. Ten rounds over independent connections.
    """
    totals = {"created": 0, "rejected": 0}
    for round_no in range(ROUNDS):
        reset_state(namespace)
        with psycopg.connect(a2.gateway_dsn) as conn:
            tree = build_tree(
                conn,
                root_limit=80000,
                mid_limit=80000,
                leaf_limit=70000,
                root_calls=10,
                mid_calls=10,
                leaf_calls=10,
            )
        grants = [
            _Grant(tree.root_id, 80000, 10),
            _Grant(tree.mid_id, 80000, 10),
            _Grant(tree.leaf_id, 70000, 10),
        ]

        def mid_draw(_rn=round_no, _tree=tree):
            def call():
                env = make_env(a2, _tree)
                inv = _tree.invocation(
                    idempotency_key=f"p13-root-{_rn}-mid",
                    jti=f"jti-p13-root-{_rn}-mid",
                    grant_id=_tree.mid_id,
                    ancestor_ids=(_tree.root_id,),
                    holder=_tree.selector,
                    tool_id="procurement.order.create",
                    params=order_params(),
                )
                snapshot = permission_for(_tree, grant_id=_tree.mid_id)
                return env.service.accept_invocation(inv, snapshot)

            return call

        def leaf_draw(_rn=round_no, _tree=tree):
            def call():
                env = make_env(a2, _tree)
                inv = _tree.invocation(
                    idempotency_key=f"p13-root-{_rn}-leaf",
                    jti=f"jti-p13-root-{_rn}-leaf",
                    tool_id="procurement.order.create",
                    params=order_params(),
                )
                return env.service.accept_invocation(inv, env.permission())

            return call

        results = _race([mid_draw(), leaf_draw()])
        ok = [r for kind, r in results if kind == "ok"]
        err = [r for kind, r in results if kind == "err"]
        assert len(ok) == 1, f"round {round_no}: {results}"
        assert len(err) == 1, f"round {round_no}: {results}"
        assert isinstance(err[0], LedgerError) and err[0].code is ErrorCode.BUDGET_EXCEEDED
        assert ok[0].disposition is AcceptDisposition.CREATED

        root = fetch_counters(a2.gateway_dsn, tree.root_id)
        assert root["amount_reserved"] == 70000
        assert root["amount_settled"] == 0
        assert_within_limits(a2.gateway_dsn, grants)
        assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1
        totals["created"] += 1
        totals["rejected"] += 1

    assert totals == {"created": ROUNDS, "rejected": ROUNDS}


# ------------------------------------------- intermediate budget contention


def test_p13_intermediate_ancestor_budget_binds_under_concurrency(a2, namespace):
    """P13: the root has room but the mid ancestor does not; 10 racing rounds."""
    totals = {"rejected": 0}
    for round_no in range(ROUNDS):
        reset_state(namespace)
        with psycopg.connect(a2.gateway_dsn) as conn:
            tree = build_tree(
                conn,
                root_limit=100000,
                mid_limit=80000,
                leaf_limit=70000,
                root_calls=10,
                mid_calls=10,
                leaf_calls=10,
            )
        env = make_env(a2, tree)
        grants = [
            _Grant(tree.root_id, 100000, 10),
            _Grant(tree.mid_id, 80000, 10),
            _Grant(tree.leaf_id, 70000, 10),
        ]
        # consume 50000 of the mid budget with a direct mid-level call
        direct = tree.invocation(
            idempotency_key=f"p13-mid-{round_no}",
            jti=f"jti-p13-mid-{round_no}",
            grant_id=tree.mid_id,
            ancestor_ids=(tree.root_id,),
            holder=tree.selector,
            tool_id="procurement.order.create",
            params=order_params(),
        )
        snapshot = permission_for(tree, grant_id=tree.mid_id)
        first = env.service.accept_invocation(direct, snapshot)
        assert first.disposition is AcceptDisposition.CREATED

        def attempt(side, _rn=round_no, _tree=tree):
            def call():
                e = make_env(a2, _tree)
                inv = _tree.invocation(
                    idempotency_key=f"p13-leaf-{_rn}-{side}",
                    jti=f"jti-p13-leaf-{_rn}-{side}",
                    tool_id="procurement.order.create",
                    params=order_params(),
                )
                return e.service.accept_invocation(inv, e.permission())

            return call

        results = _race([attempt("a"), attempt("b")])
        ok = [r for kind, r in results if kind == "ok"]
        err = [r for kind, r in results if kind == "err"]
        assert len(ok) == 0, f"round {round_no}: {results}"
        assert len(err) == 2
        assert all(e.code is ErrorCode.BUDGET_EXCEEDED for e in err), results

        assert_within_limits(a2.gateway_dsn, grants)
        assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1
        totals["rejected"] += 2

    assert totals == {"rejected": 2 * ROUNDS}


# ------------------------------------------------------ call-limit races


def test_p13_call_limit_exhaustion_under_concurrency(a2, namespace):
    """P13: zero-amount reads racing for the last call; 10 rounds, one wins."""
    totals = {"created": 0, "rejected": 0}
    for round_no in range(ROUNDS):
        reset_state(namespace)
        with psycopg.connect(a2.gateway_dsn) as conn:
            tree = build_tree(
                conn,
                root_limit=0,
                mid_limit=0,
                leaf_limit=0,
                root_calls=1,
                mid_calls=1,
                leaf_calls=1,
            )
        grants = [
            _Grant(tree.root_id, 0, 1),
            _Grant(tree.mid_id, 0, 1),
            _Grant(tree.leaf_id, 0, 1),
        ]

        def attempt(side, _rn=round_no, _tree=tree):
            def call():
                e = make_env(a2, _tree)
                inv = _tree.invocation(
                    idempotency_key=f"p13-calls-{_rn}-{side}",
                    jti=f"jti-p13-calls-{_rn}-{side}",
                    tool_id="procurement.request.read",
                    params=read_params(),
                )
                return e.service.accept_invocation(inv, e.permission())

            return call

        results = _race([attempt("a"), attempt("b")])
        ok = [r for kind, r in results if kind == "ok"]
        err = [r for kind, r in results if kind == "err"]
        assert len(ok) == 1, f"round {round_no}: {results}"
        assert len(err) == 1
        assert err[0].code is ErrorCode.CALL_LIMIT_EXCEEDED, results
        assert ok[0].cost.amount_fen == 0

        assert_within_limits(a2.gateway_dsn, grants)
        assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1
        totals["created"] += 1
        totals["rejected"] += 1

    assert totals == {"created": ROUNDS, "rejected": ROUNDS}


# -------------------------------------------- accept vs settle/recover race


def test_p13_concurrent_accept_settle_and_recovery(a2, namespace):
    """P13: accepting a new intent while another settles and a third recovers.

    Ten rounds, three independent connections and a barrier. The ancestors stay
    inside their limits, nothing goes negative and the first operation ends
    terminal exactly once with exactly one outbox row.
    """
    for round_no in range(ROUNDS):
        reset_state(namespace)
        with psycopg.connect(a2.gateway_dsn) as conn:
            tree = build_tree(
                conn,
                root_limit=1_000_000,
                mid_limit=1_000_000,
                leaf_limit=1_000_000,
                root_calls=1000,
                mid_calls=1000,
                leaf_calls=1000,
            )
        grants = [
            _Grant(tree.root_id, 1_000_000, 1000),
            _Grant(tree.mid_id, 1_000_000, 1000),
            _Grant(tree.leaf_id, 1_000_000, 1000),
        ]
        env_a = make_env(a2, tree)
        inv_a = tree.invocation(
            idempotency_key=f"p13-mix-a-{round_no}",
            jti=f"jti-p13-mix-a-{round_no}",
            tool_id="procurement.order.create",
            params=order_params(),
        )
        first = env_a.service.accept_invocation(inv_a, env_a.permission())
        assert first.disposition is AcceptDisposition.CREATED
        inv_b = tree.invocation(
            idempotency_key=f"p13-mix-b-{round_no}",
            jti=f"jti-p13-mix-b-{round_no}",
            tool_id="procurement.order.create",
            params=order_params(),
        )

        def accept_new(_inv=inv_b, _tree=tree):
            def call():
                env = make_env(a2, _tree)
                return env.service.accept_invocation(_inv, env.permission())

            return call

        def settle_first(_op=first.operation_id, _tree=tree, _rn=round_no):
            def call():
                env = make_env(a2, _tree)
                return env.service.run_operation(_op, owner_token=f"p13-settle-{_rn}")

            return call

        def recover_first(_op=first.operation_id, _tree=tree, _rn=round_no):
            def call():
                env = make_env(a2, _tree)
                return env.service.reconcile(_op, owner_token=f"p13-recover-{_rn}")

            return call

        results = _race([accept_new(), settle_first(), recover_first()])
        errors = [r for kind, r in results if kind == "err"]
        # only lease contention may refuse one of the two workers
        assert len(errors) <= 1, results
        assert_within_limits(a2.gateway_dsn, grants)

        # the race may legitimately end in UNKNOWN (the query-only worker won
        # the lease before anything was executed); either way there is never a
        # second effect and never a negative counter.
        status = a2.service.operation_status(first.operation_id)
        assert status in (OperationStatus.SUCCEEDED.value, OperationStatus.UNKNOWN.value)
        assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 2

        if status != OperationStatus.SUCCEEDED.value:
            from tests.fixtures.execution import expire_lease

            expire_lease(a2.gateway_dsn, first.operation_id)
            final = make_env(a2, tree).service.run_operation(
                first.operation_id, owner_token=f"p13-final-{round_no}"
            )
            assert final.status == OperationStatus.SUCCEEDED.value

        assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 1
        assert fetch_counters(a2.gateway_dsn, tree.leaf_id)["amount_settled"] == 70000
        assert_within_limits(a2.gateway_dsn, grants)
