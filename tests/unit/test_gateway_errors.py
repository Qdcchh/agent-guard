"""Explicit public codes never depend on exception detail text."""

import pytest

from agent_guard.authorization.verifier import VerificationError
from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode
from agent_guard.contracts.ledger import ErrorCode, LedgerError
from agent_guard.gateway.errors import classify
from agent_guard.x402.contracts import X402Error


@pytest.mark.parametrize(
    "code,status,public",
    [
        (ExecutionErrorCode.INVALID_PARAMS, 400, "INVALID_SCHEMA"),
        (ExecutionErrorCode.UNSUPPORTED_TOOL, 400, "INVALID_SCHEMA"),
        (ExecutionErrorCode.RESOURCE_NOT_FOUND, 403, "SCOPE_DENIED"),
        (ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED, 403, "SCOPE_DENIED"),
        (ExecutionErrorCode.CONSTRAINT_MISMATCH, 403, "SCOPE_DENIED"),
        (ExecutionErrorCode.OPERATION_NOT_FOUND, 403, "SCOPE_DENIED"),
        (ExecutionErrorCode.QUOTE_INVALID, 409, "QUOTE_CONFLICT"),
        (ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID, 503, "TRUSTED_STATE_UNAVAILABLE"),
        (ExecutionErrorCode.TRUSTED_DEPENDENCY_UNAVAILABLE, 503, "TRUSTED_STATE_UNAVAILABLE"),
        (ExecutionErrorCode.ILLEGAL_TRANSITION, 500, "INTERNAL_ERROR"),
    ],
)
def test_execution_typed_mapping(code, status, public):
    assert classify(ExecutionError(code, "secret EXPIRED REPLAY")) == (status, public)


@pytest.mark.parametrize("code", list(ErrorCode))
def test_ledger_typed_mapping(code):
    status, public = classify(LedgerError(code, "secret"))
    assert status in (401, 403, 409, 422, 503)
    assert public == {
        "INVALID_CONTEXT": "SCOPE_DENIED",
        "INVALID_COST": "TRUSTED_STATE_UNAVAILABLE",
    }.get(code.value, code.value)


def test_unclassified_and_verifier_errors():
    assert classify(ValueError("REPLAY secret")) == (500, "INTERNAL_ERROR")
    assert classify(VerificationError("unrelated", code="EXPIRED")) == (403, "EXPIRED")


@pytest.mark.parametrize(
    "code,status,public",
    [
        ("PAYMENT_APPROVAL_MISSING", 401, "APPROVAL_REQUIRED"),
        ("PAYMENT_DIGEST_MISSING", 401, "APPROVAL_REQUIRED"),
        ("PAYMENT_DIGEST_MISMATCH", 409, "APPROVAL_MISMATCH"),
        ("CHALLENGE_MISMATCH", 409, "APPROVAL_MISMATCH"),
        ("NO_ASSET_BUDGET", 422, "PAYMENT_BUDGET_EXCEEDED"),
        ("ASSET_BUDGET_EXCEEDED", 422, "PAYMENT_BUDGET_EXCEEDED"),
        ("PAYMENT_STATE_CONFLICT", 409, "PAYMENT_CONFLICT"),
        ("PAYMENT_NOT_FOUND", 409, "PAYMENT_CONFLICT"),
        ("CONFIG_INVALID", 503, "TRUSTED_STATE_UNAVAILABLE"),
        ("X402_INVALID", 500, "INTERNAL_ERROR"),
    ],
)
def test_x402_typed_mapping(code, status, public):
    assert classify(X402Error("secret payment bytes", code=code)) == (status, public)
