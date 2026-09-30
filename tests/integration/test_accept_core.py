"""Sequential accept-path cases: P1, P2, P4, P7, P14 (plus U1 DB half elsewhere)."""

from __future__ import annotations

import pytest

from agent_guard.contracts.ledger import AcceptDisposition, ErrorCode, LedgerError
from tests.fixtures.dbstate import fetch_all, fetch_counters, fetch_counts, fetch_one

pytestmark = pytest.mark.integration


# ------------------------------------------------------------------- P1


def test_p1_three_layer_reservation(ledger, tree, dsn):
    """P1: one 700 CNY accept reserves 70000 fen / 1 call at root, mid and leaf."""
    result = ledger.accept(tree.invocation(), tree.cost(70000))

    assert result.disposition is AcceptDisposition.CREATED
    assert result.status == "RESERVED"
    assert result.grant_id == tree.leaf_id
    assert result.root_id == tree.root_id
    assert result.cost.amount_fen == 70000

    for grant_id in (tree.root_id, tree.mid_id, tree.leaf_id):
        counters = fetch_counters(dsn, grant_id)
        assert counters["amount_reserved"] == 70000, grant_id
        assert counters["calls_reserved"] == 1, grant_id
        assert counters["amount_settled"] == 0
        assert counters["calls_settled"] == 0

    counts = fetch_counts(dsn)
    assert counts["ag_operations"] == 1
    assert counts["ag_ledger_events"] == 1
    assert counts["ag_ledger_event_nodes"] == 3

    event = fetch_one(
        dsn,
        "SELECT operation_id, phase, seq FROM ag_ledger_events",
    )
    assert event == (result.operation_id, "RESERVE", 0)
    nodes = fetch_all(
        dsn,
        "SELECT position, grant_id, amount_reserved_delta, calls_reserved_delta "
        "FROM ag_ledger_event_nodes ORDER BY position",
    )
    assert nodes == [
        (0, tree.root_id, 70000, 1),
        (1, tree.mid_id, 70000, 1),
        (2, tree.leaf_id, 70000, 1),
    ]


# ------------------------------------------------------------------- P2


def test_p2_unregistered_holder_key_rejected(ledger, dsn):
    """P2: a grant whose holder key was never registered is refused."""
    import psycopg

    from tests.fixtures.state import build_tree

    with psycopg.connect(dsn) as conn:
        tree = build_tree(conn, register_principals=False)
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(tree.invocation(), tree.cost(1))
    assert excinfo.value.code is ErrorCode.HOLDER_MISMATCH
    assert fetch_counts(dsn)["ag_operations"] == 0


def test_p2_holder_mismatch_rejected(ledger, tree):
    """P2: presenting another holder than the grant's holder is refused."""
    forged = tree.invocation(holder=("other-client", "other-kid"))
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(forged, tree.cost(1))
    assert excinfo.value.code is ErrorCode.HOLDER_MISMATCH


def test_p2_cross_tenant_rejected(ledger, tree):
    """P2: a context claiming another tenant cannot use this grant."""
    forged = tree.invocation(tenant_id="tenant-other")
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(forged, tree.cost(1))
    assert excinfo.value.code is ErrorCode.INVALID_CONTEXT


def test_p2_cross_task_rejected(ledger, tree):
    forged = tree.invocation(task_id="task-other")
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(forged, tree.cost(1))
    assert excinfo.value.code is ErrorCode.INVALID_CONTEXT


def test_p2_forged_root_rejected(ledger, tree):
    """P2: a self-declared root id is not trusted."""
    forged = tree.invocation(root_id="grant-root-forged")
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(forged, tree.cost(1))
    assert excinfo.value.code is ErrorCode.INVALID_CONTEXT


def test_p2_truncated_ancestors_rejected(ledger, tree):
    """P2: a shortened ancestor path is refused; the database path is authoritative."""
    forged = tree.invocation(ancestor_ids=(tree.root_id,))  # missing mid
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(forged, tree.cost(1))
    assert excinfo.value.code is ErrorCode.INVALID_CONTEXT

    empty = tree.invocation(ancestor_ids=())
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(empty, tree.cost(1))
    assert excinfo.value.code is ErrorCode.INVALID_CONTEXT


def test_p2_unknown_grant_rejected(ledger, tree):
    forged = tree.invocation(grant_id="grant-nope", ancestor_ids=())
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(forged, tree.cost(1))
    assert excinfo.value.code is ErrorCode.INVALID_CONTEXT


# ------------------------------------------------------------------- P4


def test_p4_intermediate_ancestor_budget_binds(ledger, tree, dsn):
    """P4: root has room and the leaf has room, but the mid ancestor does not.

    A direct call on the parent and a later call on its descendant share the
    same mid-level budget, so the second accept must fail at the mid node.
    """
    # mid limit is 80000; consume 50000 of it via a direct call on the mid node.
    direct = tree.invocation(grant_id=tree.mid_id, ancestor_ids=(tree.root_id,))
    first = ledger.accept(direct, tree.cost(50000))
    assert first.disposition is AcceptDisposition.CREATED

    # descendant wants 50000: root (100000) and leaf (70000) both have room.
    descendant = tree.invocation()
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(descendant, tree.cost(50000))
    assert excinfo.value.code is ErrorCode.BUDGET_EXCEEDED

    assert fetch_counters(dsn, tree.root_id)["amount_reserved"] == 50000
    assert fetch_counters(dsn, tree.mid_id)["amount_reserved"] == 50000
    assert fetch_counters(dsn, tree.leaf_id)["amount_reserved"] == 0
    assert fetch_counts(dsn)["ag_operations"] == 1


# ------------------------------------------------------------------- P7


def test_p7_same_key_different_params_conflicts(ledger, tree, dsn):
    """P7: same business key with different canonical params is a conflict."""
    before = fetch_counters(dsn, tree.leaf_id)
    first = ledger.accept(
        tree.invocation(idempotency_key="purchase-p7", params=b'{"sku":"sku-001"}'),
        tree.cost(70000),
    )
    assert first.disposition is AcceptDisposition.CREATED

    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(
            tree.invocation(idempotency_key="purchase-p7", params=b'{"sku":"sku-002"}'),
            tree.cost(70000),
        )
    assert excinfo.value.code is ErrorCode.IDEMPOTENCY_CONFLICT

    assert fetch_counters(dsn, tree.leaf_id)["amount_reserved"] == before["amount_reserved"] + 70000
    assert fetch_counts(dsn)["ag_operations"] == 1


def test_p7_same_key_different_grant_conflicts(ledger, tree, dsn):
    """P7: reusing the key under another grant/holder is a conflict."""
    first = ledger.accept(tree.invocation(idempotency_key="purchase-shared"), tree.cost(70000))
    assert first.disposition is AcceptDisposition.CREATED
    before = fetch_counters(dsn, tree.mid_id)

    other = tree.invocation(
        grant_id=tree.mid_id,
        ancestor_ids=(tree.root_id,),
        holder=tree.selector,
        idempotency_key="purchase-shared",
    )
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(other, tree.cost(70000))
    assert excinfo.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    # the first accept already reserved the mid ancestor; no extra reservation
    assert fetch_counters(dsn, tree.mid_id) == before
    assert fetch_counts(dsn)["ag_operations"] == 1


def test_p7_same_proof_replay_rejected(ledger, tree, dsn):
    """P7: replaying the very same proof jti is REPLAY, never an idempotent hit."""
    original = tree.invocation(jti="jti-fixed-1")
    first = ledger.accept(original, tree.cost(70000))
    assert first.disposition is AcceptDisposition.CREATED

    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(original, tree.cost(70000))
    assert excinfo.value.code is ErrorCode.REPLAY

    assert fetch_counters(dsn, tree.leaf_id)["amount_reserved"] == 70000
    assert fetch_counts(dsn)["ag_operations"] == 1


# ------------------------------------------------------------------ P14


def test_p14_retry_reuses_original_cost_and_evidence(ledger, tree, dsn):
    """P14: a retry after the quote changed reuses the first accept's snapshot.

    No second reservation, no second RESERVE event, and the first-accept
    evidence is not overwritten by the retry's new proof.
    """
    first_inv = tree.invocation(
        idempotency_key="purchase-p14",
        jti="jti-first",
        token_digest="tok-1",
        proof_digest="proof-1",
        intent_digest="intent-1",
        evidence_ref="evidence-1",
    )
    first_cost = tree.cost(70000, quote_id="quote-001", quote_version="1", quote_snapshot=b"snap-1")
    first = ledger.accept(first_inv, first_cost)
    assert first.disposition is AcceptDisposition.CREATED

    retry_inv = tree.invocation(
        idempotency_key="purchase-p14",
        jti="jti-retry",
        token_digest="tok-2",
        proof_digest="proof-2",
        intent_digest="intent-2",
        evidence_ref="evidence-2",
    )
    new_cost = tree.cost(1, quote_id="quote-002", quote_version="2", quote_snapshot=b"snap-2")
    retried = ledger.accept(retry_inv, new_cost)

    assert retried.disposition is AcceptDisposition.EXISTING
    assert retried.operation_id == first.operation_id
    assert retried.cost.amount_fen == 70000
    assert retried.cost.quote_id == "quote-001"
    assert retried.cost.quote_snapshot == b"snap-1"
    assert retried.accepted_at == first.accepted_at

    assert fetch_counters(dsn, tree.leaf_id)["amount_reserved"] == 70000  # no double reserve
    assert fetch_counts(dsn)["ag_ledger_events"] == 1

    stored = fetch_one(
        dsn,
        "SELECT token_digest, proof_digest, intent_digest, evidence_ref "
        "FROM ag_operations WHERE operation_id = %s",
        (first.operation_id,),
    )
    assert stored == ("tok-1", "proof-1", "intent-1", "evidence-1")

    proofs = fetch_all(
        dsn,
        "SELECT proof_jti, proof_digest, evidence_ref, operation_id "
        "FROM ag_proofs ORDER BY proof_jti",
    )
    assert len(proofs) == 2
    by_jti = {p[0]: p for p in proofs}
    assert by_jti["jti-first"][1:] == ("proof-1", "evidence-1", first.operation_id)
    assert by_jti["jti-retry"][1:] == ("proof-2", "evidence-2", first.operation_id)
