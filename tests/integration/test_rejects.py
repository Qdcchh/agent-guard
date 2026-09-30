"""U1 (database half): rejected inputs must leave the database untouched.

The per-field error codes live in tests/unit/test_input_validation.py; this
file proves against a real database that every rejection path is side-effect
free.
"""

from __future__ import annotations

import pytest

from agent_guard.contracts.ledger import ErrorCode, LedgerError, TrustedCost
from tests.fixtures.dbstate import fetch_counters, fetch_counts

pytestmark = pytest.mark.integration


def _baseline(dsn, tree) -> dict[str, int]:
    counts = fetch_counts(dsn)
    assert counts["ag_operations"] == 0
    return counts


def _assert_unchanged(dsn, tree, counts) -> None:
    assert fetch_counts(dsn) == counts
    for grant_id in (tree.root_id, tree.mid_id, tree.leaf_id):
        counters = fetch_counters(dsn, grant_id)
        assert counters["amount_reserved"] == 0
        assert counters["calls_reserved"] == 0


@pytest.mark.parametrize(
    "make_cost,code",
    [
        (lambda: TrustedCost(amount_fen=-1), ErrorCode.INVALID_COST),
        (lambda: TrustedCost(amount_fen=True), ErrorCode.INVALID_COST),
        (lambda: TrustedCost(amount_fen=1.5), ErrorCode.INVALID_COST),
        (lambda: TrustedCost(amount_fen=2**53), ErrorCode.INVALID_COST),
        (lambda: TrustedCost(amount_fen=1, currency="USD"), ErrorCode.INVALID_COST),
        (lambda: TrustedCost(amount_fen=1, calls=0), ErrorCode.INVALID_COST),
        (lambda: TrustedCost(amount_fen=1, calls=True), ErrorCode.INVALID_COST),
    ],
)
def test_u1_bad_cost_rejected_without_db_changes(ledger, tree, dsn, make_cost, code):
    counts = _baseline(dsn, tree)
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(tree.invocation(), make_cost())
    assert excinfo.value.code is code
    _assert_unchanged(dsn, tree, counts)


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("purpose", "result-read", ErrorCode.INVALID_CONTEXT),
        ("profile", "legacy-v1", ErrorCode.INVALID_CONTEXT),
        ("tool_version", "2", ErrorCode.INVALID_CONTEXT),
        ("method", "GET", ErrorCode.INVALID_CONTEXT),
        ("endpoint", "https://evil.example/v1/invocations", ErrorCode.INVALID_CONTEXT),
        ("token_exp", True, ErrorCode.INVALID_CONTEXT),
        ("proof_exp", 2.5, ErrorCode.INVALID_CONTEXT),
        ("params", "not-bytes", ErrorCode.INVALID_CONTEXT),
    ],
)
def test_u1_bad_context_rejected_without_db_changes(ledger, tree, dsn, field, value, code):
    counts = _baseline(dsn, tree)
    forged = tree.invocation(**{field: value})
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(forged, tree.cost(1))
    assert excinfo.value.code is code
    _assert_unchanged(dsn, tree, counts)


def test_u1_proof_window_violations_leave_no_state(ledger, tree, dsn):
    counts = _baseline(dsn, tree)
    too_long = tree.invocation(proof_iat=1000, proof_exp=1061)
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(too_long, tree.cost(1))
    assert excinfo.value.code is ErrorCode.STALE_REQUEST

    inverted = tree.invocation(proof_iat=1030, proof_exp=1000)
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(inverted, tree.cost(1))
    assert excinfo.value.code is ErrorCode.STALE_REQUEST

    _assert_unchanged(dsn, tree, counts)


def test_u1_rejections_do_not_consume_the_business_key(ledger, tree, dsn):
    """A rejected attempt must not block a later valid accept on the same key."""
    counts = _baseline(dsn, tree)
    with pytest.raises(LedgerError):
        ledger.accept(tree.invocation(idempotency_key="purchase-u1"), TrustedCost(amount_fen=-1))
    _assert_unchanged(dsn, tree, counts)

    result = ledger.accept(
        tree.invocation(idempotency_key="purchase-u1", jti="jti-u1-later"), tree.cost(70000)
    )
    assert result.disposition.value == "CREATED"
    assert fetch_counts(dsn)["ag_operations"] == 1
