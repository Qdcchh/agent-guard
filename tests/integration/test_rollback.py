"""P12: mid-write failures roll back everything; later accepts still work.

Fault injection is limited to monkeypatching storage steps (no runtime
bypass switches). All rollbacks run against real database transactions.
"""

from __future__ import annotations

import psycopg
import pytest

from agent_guard.contracts.ledger import AcceptDisposition, ErrorCode, LedgerError
from agent_guard.ledger import store
from tests.fixtures.dbstate import fetch_counters, fetch_counts

pytestmark = pytest.mark.integration


def _assert_no_state(dsn: str, tree) -> None:
    counts = fetch_counts(dsn)
    assert counts["ag_operations"] == 0
    assert counts["ag_proofs"] == 0
    assert counts["ag_ledger_events"] == 0
    assert counts["ag_ledger_event_nodes"] == 0
    for grant_id in (tree.root_id, tree.mid_id, tree.leaf_id):
        counters = fetch_counters(dsn, grant_id)
        assert counters["amount_reserved"] == 0, grant_id
        assert counters["calls_reserved"] == 0, grant_id


def test_p12_exception_after_first_node_update_rolls_back(ledger, tree, dsn, monkeypatch):
    """P12: failing after the first node's reservation update must undo it all."""
    original = store.apply_reservation
    calls = {"n": 0}

    def flaky(conn, grant_id, amount_fen, calls_arg):
        original(conn, grant_id, amount_fen, calls_arg)
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("injected failure after first node update")

    monkeypatch.setattr(store, "apply_reservation", flaky)

    with pytest.raises(RuntimeError, match="injected failure"):
        ledger.accept(tree.invocation(), tree.cost(70000))
    assert calls["n"] == 1

    _assert_no_state(dsn, tree)

    # a fresh request works normally afterwards
    monkeypatch.undo()
    result = ledger.accept(tree.invocation(jti="jti-p12-after"), tree.cost(70000))
    assert result.disposition is AcceptDisposition.CREATED
    assert fetch_counters(dsn, tree.leaf_id)["amount_reserved"] == 70000
    assert fetch_counts(dsn)["ag_operations"] == 1
    assert fetch_counts(dsn)["ag_ledger_events"] == 1


def test_p12_failure_before_commit_rolls_back(ledger, tree, dsn, monkeypatch):
    """P12: a connection-level failure at the last step fails closed and rolls back."""

    def broken(conn, **kwargs):
        raise psycopg.OperationalError("simulated connection loss before commit")

    monkeypatch.setattr(store, "link_proof_to_operation", broken)

    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(tree.invocation(), tree.cost(70000))
    assert excinfo.value.code is ErrorCode.TRUSTED_STATE_UNAVAILABLE

    _assert_no_state(dsn, tree)
    monkeypatch.undo()
    result = ledger.accept(tree.invocation(jti="jti-p12-recover"), tree.cost(70000))
    assert result.disposition is AcceptDisposition.CREATED


def test_p12_constraint_failure_rolls_back_and_is_not_db_unavailable(
    ledger, tree, dsn, monkeypatch
):
    """P12: a constraint violation mid-write rolls back and is not disguised
    as a database-availability error (which would wrongly close no state)."""

    def violating(conn, grant_id, amount_fen, calls_arg):
        # deliberately break the safe-form CHECK on the counter columns
        conn.execute(
            "UPDATE ag_grants SET amount_reserved = amount_limit + 1 WHERE grant_id = %s",
            (grant_id,),
        )

    monkeypatch.setattr(store, "apply_reservation", violating)

    with pytest.raises(psycopg.errors.CheckViolation):
        ledger.accept(tree.invocation(), tree.cost(70000))

    _assert_no_state(dsn, tree)
    monkeypatch.undo()
    result = ledger.accept(tree.invocation(jti="jti-p12-consistent"), tree.cost(70000))
    assert result.disposition is AcceptDisposition.CREATED


def test_p12_partial_proof_and_event_never_persist(ledger, tree, dsn, monkeypatch):
    """P12: failing between the operation insert and the event insert leaves
    neither the operation nor the proof behind."""
    monkeypatch.setattr(
        store,
        "insert_reserve_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("no event")),
    )

    with pytest.raises(RuntimeError, match="no event"):
        ledger.accept(tree.invocation(), tree.cost(70000))

    _assert_no_state(dsn, tree)
