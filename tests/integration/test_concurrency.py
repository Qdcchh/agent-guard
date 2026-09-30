"""Concurrency cases P3, P5, P6.

Each round builds isolated data and races real concurrent accepts coordinated
by a barrier — no sequential loop masquerading as concurrency and no random
sleeps. Every round records success/reject counts and the totals are asserted.
"""

from __future__ import annotations

import threading
from datetime import datetime

import psycopg
import pytest

from agent_guard.contracts.ledger import (
    PROFILE,
    PURPOSE_INVOKE,
    TOOL_VERSION,
    AcceptDisposition,
    ErrorCode,
    LedgerError,
    TrustedCost,
    VerifiedInvocation,
)
from agent_guard.ledger import provisioning as prov
from agent_guard.ledger.service import ExecutionLedger
from tests.fixtures.dbstate import fetch_all, fetch_counters, fetch_counts
from tests.fixtures.isolation import reset_state
from tests.fixtures.state import INVOKE_ENDPOINT, INVOKE_METHOD, default_window

pytestmark = pytest.mark.integration

ROUNDS = 10


def _make_invocation(
    *,
    subject: str,
    tenant_id: str,
    task_id: str,
    grant_id: str,
    root_id: str,
    holder: tuple[str, str],
    ancestor_ids: tuple[str, ...],
    idempotency_key: str,
    proof_jti: str,
    tool_id: str = "procurement.order.create",
    params: bytes = b'{"sku":"sku-001"}',
) -> VerifiedInvocation:
    now = int(datetime.now().timestamp())
    tag = proof_jti
    return VerifiedInvocation(
        subject=subject,
        tenant_id=tenant_id,
        task_id=task_id,
        grant_id=grant_id,
        root_id=root_id,
        holder_client_id=holder[0],
        holder_kid=holder[1],
        tool_id=tool_id,
        tool_version=TOOL_VERSION,
        idempotency_key=idempotency_key,
        canonical_params=params,
        token_exp=now + 300,
        proof_iat=now,
        proof_exp=now + 30,
        proof_jti=tag,
        token_digest=f"tok-{tag}",
        proof_digest=f"proof-{tag}",
        intent_digest=f"intent-{tag}",
        evidence_ref=f"evidence-{tag}",
        ancestor_ids=ancestor_ids,
        profile=PROFILE,
        purpose=PURPOSE_INVOKE,
        endpoint=INVOKE_ENDPOINT,
        method=INVOKE_METHOD,
    )


def _make_cost(amount_fen: int) -> TrustedCost:
    return TrustedCost(amount_fen=amount_fen, calls=1, quote_id="quote-1", quote_version="1")


def _race(dsn: str, tasks: list[tuple[VerifiedInvocation, TrustedCost]]) -> dict:
    """Run one accept per task concurrently, each worker with its own connection."""
    barrier = threading.Barrier(len(tasks))
    results: list[tuple[str, object]] = []
    lock = threading.Lock()

    def worker(inv: VerifiedInvocation, cost: TrustedCost) -> None:
        ledger = ExecutionLedger(dsn)
        barrier.wait()
        try:
            result = ledger.accept(inv, cost)
            with lock:
                results.append(("ok", result))
        except LedgerError as exc:
            with lock:
                results.append(("err", exc.code))

    threads = [threading.Thread(target=worker, args=task) for task in tasks]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    created = [r for kind, r in results if kind == "ok"]
    rejected = [r for kind, r in results if kind == "err"]
    return {"created": created, "rejected": rejected, "raw": results}


# ------------------------------------------------------------------- P3


def test_p3_two_branches_race_for_root_budget(dsn, migrated, namespace):
    """P3: root 1000 CNY, two branches 800 each ask 700 concurrently.

    Exactly one accept wins; the other is a budget rejection; the root never
    reserves more than the accepted 70000 fen.
    """
    totals = {"created": 0, "rejected": 0}
    for round_no in range(ROUNDS):
        reset_state(namespace)
        with psycopg.connect(dsn) as conn:
            not_before, expires_at = default_window()
            for client_id, kid in (
                ("client-plan", "kid-plan"),
                ("client-a", "kid-a"),
                ("client-b", "kid-b"),
            ):
                prov.register_principal(conn, tenant_id="t3", client_id=client_id, kid=kid)
            prov.create_task_root(
                conn,
                tenant_id="t3",
                task_id="task3",
                grant_id="root3",
                subject="user-3",
                holder_client_id="client-plan",
                holder_kid="kid-plan",
                amount_limit=100000,
                call_limit=10,
                not_before=not_before,
                expires_at=expires_at,
            )
            for grant_id, client_id, kid in (
                ("branch-a", "client-a", "kid-a"),
                ("branch-b", "client-b", "kid-b"),
            ):
                prov.create_child_grant(
                    conn,
                    parent_grant_id="root3",
                    grant_id=grant_id,
                    holder_client_id=client_id,
                    holder_kid=kid,
                    amount_limit=80000,
                    call_limit=8,
                    not_before=not_before,
                    expires_at=expires_at,
                )
        invocations = [
            _make_invocation(
                subject="user-3",
                tenant_id="t3",
                task_id="task3",
                grant_id=grant_id,
                root_id="root3",
                holder=(client_id, kid),
                ancestor_ids=("root3",),
                idempotency_key=f"p3-{round_no}-{side}",
                proof_jti=f"jti-p3-{round_no}-{side}",
            )
            for side, grant_id, client_id, kid in (
                ("a", "branch-a", "client-a", "kid-a"),
                ("b", "branch-b", "client-b", "kid-b"),
            )
        ]
        outcome = _race(dsn, [(inv, _make_cost(70000)) for inv in invocations])

        assert len(outcome["created"]) == 1, f"round {round_no}: {outcome['raw']}"
        assert outcome["rejected"] == [ErrorCode.BUDGET_EXCEEDED], outcome["raw"]
        assert fetch_counters(dsn, "root3")["amount_reserved"] == 70000
        assert fetch_counts(dsn)["ag_operations"] == 1
        totals["created"] += len(outcome["created"])
        totals["rejected"] += len(outcome["rejected"])

    assert totals == {"created": ROUNDS, "rejected": ROUNDS}


# ------------------------------------------------------------------- P5


def test_p5_call_limit_race_with_zero_amount(dsn, migrated, namespace):
    """P5: call limit 1 with zero-amount calls — at most one accept.

    Zero-amount reads/notifications must not bypass call counting and the zero
    amount-limit boundary must hold exactly.
    """
    totals = {"created": 0, "rejected": 0}
    for round_no in range(ROUNDS):
        reset_state(namespace)
        with psycopg.connect(dsn) as conn:
            not_before, expires_at = default_window()
            prov.register_principal(conn, tenant_id="t5", client_id="client-5", kid="kid-5")
            prov.create_task_root(
                conn,
                tenant_id="t5",
                task_id="task5",
                grant_id="root5",
                subject="user-5",
                holder_client_id="client-5",
                holder_kid="kid-5",
                amount_limit=0,
                call_limit=1,
                not_before=not_before,
                expires_at=expires_at,
            )
        invocations = [
            _make_invocation(
                subject="user-5",
                tenant_id="t5",
                task_id="task5",
                grant_id="root5",
                root_id="root5",
                holder=("client-5", "kid-5"),
                ancestor_ids=(),
                idempotency_key=f"p5-{round_no}-{side}",
                proof_jti=f"jti-p5-{round_no}-{side}",
                tool_id="procurement.request.read",
                params=b"{}",
            )
            for side in ("a", "b")
        ]
        outcome = _race(dsn, [(inv, _make_cost(0)) for inv in invocations])

        assert len(outcome["created"]) == 1, f"round {round_no}: {outcome['raw']}"
        assert outcome["rejected"] == [ErrorCode.CALL_LIMIT_EXCEEDED], outcome["raw"]
        counters = fetch_counters(dsn, "root5")
        assert counters["calls_reserved"] == 1
        assert counters["amount_reserved"] == 0
        assert fetch_counts(dsn)["ag_operations"] == 1
        totals["created"] += len(outcome["created"])
        totals["rejected"] += len(outcome["rejected"])

    assert totals == {"created": ROUNDS, "rejected": ROUNDS}


# ------------------------------------------------------------------- P6


def test_p6_concurrent_same_key_one_operation(dsn, migrated, namespace):
    """P6: two new proofs race on one business key and one intent.

    Exactly one CREATED and one EXISTING sharing one operation_id; a single
    reservation and a single RESERVE event; every proof recorded with its own
    evidence and linked to the operation. A retry after the budget is spent
    still returns EXISTING (no second budget check), while a fresh key is a
    budget rejection.
    """
    totals = {"created": 0, "existing": 0, "rejected": 0}
    for round_no in range(ROUNDS):
        reset_state(namespace)
        with psycopg.connect(dsn) as conn:
            not_before, expires_at = default_window()
            prov.register_principal(conn, tenant_id="t6", client_id="client-6", kid="kid-6")
            prov.create_task_root(
                conn,
                tenant_id="t6",
                task_id="task6",
                grant_id="root6",
                subject="user-6",
                holder_client_id="client-6",
                holder_kid="kid-6",
                amount_limit=70000,
                call_limit=10,
                not_before=not_before,
                expires_at=expires_at,
            )
        shared_key = f"p6-{round_no}-shared"

        def inv(side: str, *, _key: str = shared_key, _round: int = round_no) -> VerifiedInvocation:
            return _make_invocation(
                subject="user-6",
                tenant_id="t6",
                task_id="task6",
                grant_id="root6",
                root_id="root6",
                holder=("client-6", "kid-6"),
                ancestor_ids=(),
                idempotency_key=_key,
                proof_jti=f"jti-p6-{_round}-{side}",
                params=b'{"sku":"sku-006"}',
            )

        outcome = _race(dsn, [(inv("a"), _make_cost(70000)), (inv("b"), _make_cost(70000))])
        assert len(outcome["created"]) == 2, f"round {round_no}: {outcome['raw']}"
        dispositions = sorted(r.disposition for r in outcome["created"])
        assert dispositions == [AcceptDisposition.CREATED, AcceptDisposition.EXISTING]
        assert outcome["rejected"] == []
        assert ErrorCode.BUDGET_EXCEEDED not in outcome["rejected"]
        assert len({r.operation_id for r in outcome["created"]}) == 1
        operation_id = outcome["created"][0].operation_id

        # budget is now exhausted: the same key retry still returns EXISTING
        ledger = ExecutionLedger(dsn)
        again = ledger.accept(inv("retry"), _make_cost(70000))
        assert again.disposition is AcceptDisposition.EXISTING
        assert again.operation_id == operation_id

        # a different business key must observe the exhausted budget
        fresh = _make_invocation(
            subject="user-6",
            tenant_id="t6",
            task_id="task6",
            grant_id="root6",
            root_id="root6",
            holder=("client-6", "kid-6"),
            ancestor_ids=(),
            idempotency_key=f"p6-{round_no}-fresh",
            proof_jti=f"jti-p6-{round_no}-fresh",
        )
        with pytest.raises(LedgerError) as excinfo:
            ledger.accept(fresh, _make_cost(70000))
        assert excinfo.value.code is ErrorCode.BUDGET_EXCEEDED

        counters = fetch_counters(dsn, "root6")
        assert counters["amount_reserved"] == 70000  # no double reservation
        assert counters["calls_reserved"] == 1
        assert fetch_counts(dsn)["ag_ledger_events"] == 1
        assert fetch_counts(dsn)["ag_operations"] == 1

        proofs = fetch_all(
            dsn,
            "SELECT proof_jti, proof_digest, operation_id FROM ag_proofs ORDER BY proof_jti",
        )
        assert len(proofs) == 3  # both racers plus the retry
        assert {row[2] for row in proofs} == {operation_id}
        by_jti = {row[0]: row[1] for row in proofs}
        assert by_jti[f"jti-p6-{round_no}-a"] == f"proof-jti-p6-{round_no}-a"
        assert by_jti[f"jti-p6-{round_no}-b"] == f"proof-jti-p6-{round_no}-b"

        totals["created"] += sum(
            1 for r in outcome["created"] if r.disposition is AcceptDisposition.CREATED
        )
        totals["existing"] += sum(
            1 for r in outcome["created"] if r.disposition is AcceptDisposition.EXISTING
        )
        totals["rejected"] += len(outcome["rejected"])

    assert totals == {"created": ROUNDS, "existing": ROUNDS, "rejected": 0}
