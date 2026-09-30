"""U1: input boundary tests — malformed context/cost is rejected before any
database access, with precise error codes. No database is required here; the
"database unchanged" half of U1 is asserted in the integration suite.
"""

from __future__ import annotations

import pytest

from agent_guard.contracts.ledger import (
    MAX_SAFE_INT,
    ErrorCode,
    LedgerError,
    TrustedCost,
)
from agent_guard.ledger.validation import validate_cost, validate_invocation

pytestmark = pytest.mark.unit


@pytest.fixture()
def valid_invocation():
    """A context object without touching the database."""
    from datetime import datetime, timedelta, timezone

    from tests.fixtures.state import TreeFixture

    now = datetime.now(tz=timezone.utc)
    tree = TreeFixture(
        tenant_id="tenant-demo",
        task_id="task-001",
        subject="user-demo-001",
        root_id="grant-root-1",
        mid_id="grant-mid-1",
        leaf_id="grant-leaf-1",
        planner=("agent-planner", "kid-plan-1"),
        selector=("agent-selector", "kid-sel-1"),
        executor=("agent-executor", "kid-exec-1"),
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        amount_limits=(100000, 80000, 70000),
        call_limits=(10, 8, 5),
    )
    return tree.invocation()


def _expect_context(fn) -> ErrorCode:
    with pytest.raises(LedgerError) as excinfo:
        fn()
    assert excinfo.value.code is ErrorCode.INVALID_CONTEXT
    return excinfo.value.code


def _expect_cost(fn) -> ErrorCode:
    with pytest.raises(LedgerError) as excinfo:
        fn()
    assert excinfo.value.code is ErrorCode.INVALID_COST
    return excinfo.value.code


# ---------------------------------------------------------------- context


def test_valid_context_passes(valid_invocation):
    validate_invocation(valid_invocation)


@pytest.mark.parametrize("field,value", [("profile", "other"), ("purpose", "result-read")])
def test_unsupported_profile_or_purpose_rejected(valid_invocation, field, value):
    obj = valid_invocation.__class__(**{**valid_invocation.__dict__, field: value})
    _expect_context(lambda: validate_invocation(obj))


@pytest.mark.parametrize(
    "field,value",
    [
        ("endpoint", "https://evil.example/v1/invocations"),
        ("method", "GET"),
        ("tool_version", "2"),
        ("tool_version", 1),
    ],
)
def test_unsupported_binding_rejected(valid_invocation, field, value):
    obj = valid_invocation.__class__(**{**valid_invocation.__dict__, field: value})
    _expect_context(lambda: validate_invocation(obj))


@pytest.mark.parametrize(
    "field,value",
    [
        ("subject", ""),
        ("tenant_id", ""),
        ("task_id", "x" * 200),
        ("grant_id", "bad\x00id"),
        ("root_id", ""),
        ("holder_client_id", ""),
        ("holder_kid", "k" * 300),
        ("tool_id", ""),
        ("idempotency_key", ""),
        ("proof_jti", ""),
        ("token_digest", ""),
        ("proof_digest", ""),
        ("intent_digest", ""),
        ("evidence_ref", "e" * 600),
        ("subject", 123),
        ("token_exp", "soon"),
    ],
)
def test_malformed_id_field_rejected(valid_invocation, field, value):
    obj = valid_invocation.__class__(**{**valid_invocation.__dict__, field: value})
    _expect_context(lambda: validate_invocation(obj))


def test_bool_timestamps_are_not_integers(valid_invocation):
    obj = valid_invocation.__class__(**{**valid_invocation.__dict__, "token_exp": True})
    _expect_context(lambda: validate_invocation(obj))


def test_float_timestamps_rejected(valid_invocation):
    obj = valid_invocation.__class__(**{**valid_invocation.__dict__, "proof_exp": 3.5})
    _expect_context(lambda: validate_invocation(obj))


def test_negative_timestamp_rejected(valid_invocation):
    obj = valid_invocation.__class__(**{**valid_invocation.__dict__, "token_exp": -1})
    _expect_context(lambda: validate_invocation(obj))


def test_canonical_params_must_be_bytes(valid_invocation):
    obj = valid_invocation.__class__(**{**valid_invocation.__dict__, "canonical_params": "{}"})
    _expect_context(lambda: validate_invocation(obj))


def test_canonical_params_size_cap(valid_invocation):
    obj = valid_invocation.__class__(
        **{**valid_invocation.__dict__, "canonical_params": b"x" * 65537}
    )
    _expect_context(lambda: validate_invocation(obj))


def test_ancestor_ids_shape(valid_invocation):
    for bad in (("a", "b", "c"), ["a"], ("",)):
        obj = valid_invocation.__class__(**{**valid_invocation.__dict__, "ancestor_ids": bad})
        _expect_context(lambda o=obj: validate_invocation(o))


def test_proof_window_structure():
    from datetime import datetime, timedelta, timezone

    from tests.fixtures.state import TreeFixture

    now = datetime.now(tz=timezone.utc)
    tree = TreeFixture(
        tenant_id="t",
        task_id="k",
        subject="s",
        root_id="r",
        mid_id="m",
        leaf_id="l",
        planner=("p", "pk"),
        selector=("s", "sk"),
        executor=("e", "ek"),
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        amount_limits=(1, 1, 1),
        call_limits=(1, 1, 1),
    )
    base = tree.invocation(proof_iat=1000, proof_exp=1030)

    too_long = base.__class__(**{**base.__dict__, "proof_iat": 1000, "proof_exp": 1061})
    with pytest.raises(LedgerError) as excinfo:
        validate_invocation(too_long)
    assert excinfo.value.code is ErrorCode.STALE_REQUEST

    inverted = base.__class__(**{**base.__dict__, "proof_iat": 1030, "proof_exp": 1000})
    with pytest.raises(LedgerError) as excinfo:
        validate_invocation(inverted)
    assert excinfo.value.code is ErrorCode.STALE_REQUEST


# ------------------------------------------------------------------- cost


def test_valid_cost_passes():
    validate_cost(TrustedCost(amount_fen=0))
    validate_cost(TrustedCost(amount_fen=MAX_SAFE_INT))


@pytest.mark.parametrize("amount", [-1, 1.5, True, False, "100", MAX_SAFE_INT + 1, None])
def test_bad_amount_rejected(amount):
    _expect_cost(lambda: validate_cost(TrustedCost(amount_fen=amount)))


@pytest.mark.parametrize("calls", [0, -1, True, 1.0, "1", MAX_SAFE_INT + 1])
def test_bad_calls_rejected(calls):
    _expect_cost(lambda: validate_cost(TrustedCost(amount_fen=0, calls=calls)))


def test_wrong_currency_rejected():
    _expect_cost(lambda: validate_cost(TrustedCost(amount_fen=1, currency="USD")))


def test_bad_quote_fields_rejected():
    _expect_cost(lambda: validate_cost(TrustedCost(amount_fen=1, quote_snapshot="not-bytes")))
    _expect_cost(lambda: validate_cost(TrustedCost(amount_fen=1, quote_id="q" * 200)))
