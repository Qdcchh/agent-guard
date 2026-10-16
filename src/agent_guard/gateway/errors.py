"""Stable gateway error classification; never interpret exception messages."""

import psycopg

from agent_guard.authorization.evidence_store import EvidenceError
from agent_guard.authorization.permission_snapshot import PermissionSnapshotError
from agent_guard.authorization.verifier import VerificationError
from agent_guard.contracts.execution import ExecutionError
from agent_guard.contracts.ledger import LedgerError
from agent_guard.execution.receipt_projection import ReceiptProjectionError

_STATUS = {
    "INVALID_SCHEMA": 400,
    "INVALID_SIGNATURE": 401,
    "HOLDER_MISMATCH": 401,
    "STALE_REQUEST": 401,
    "SCOPE_DENIED": 403,
    "REVOKED": 403,
    "EXPIRED": 403,
    "REPLAY": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "QUOTE_CONFLICT": 409,
    "BUDGET_EXCEEDED": 422,
    "CALL_LIMIT_EXCEEDED": 422,
    "TRUSTED_STATE_UNAVAILABLE": 503,
    "INTERNAL_ERROR": 500,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "REQUEST_TOO_LARGE": 413,
    "UNSUPPORTED_MEDIA_TYPE": 415,
}
_EXECUTION = {
    "INVALID_PARAMS": "INVALID_SCHEMA",
    "UNSUPPORTED_TOOL": "INVALID_SCHEMA",
    "RESOURCE_NOT_FOUND": "SCOPE_DENIED",
    "RESOURCE_NOT_AUTHORIZED": "SCOPE_DENIED",
    "CONSTRAINT_MISMATCH": "SCOPE_DENIED",
    "OPERATION_NOT_FOUND": "SCOPE_DENIED",
    "QUOTE_INVALID": "QUOTE_CONFLICT",
    "TRUSTED_DEPENDENCY_UNAVAILABLE": "TRUSTED_STATE_UNAVAILABLE",
    "LEGACY_SNAPSHOT_INVALID": "TRUSTED_STATE_UNAVAILABLE",
}
_LEDGER = {"INVALID_CONTEXT": "SCOPE_DENIED", "INVALID_COST": "TRUSTED_STATE_UNAVAILABLE"}


class GatewayError(Exception):
    def __init__(self, code: str):
        if code not in _STATUS:
            raise ValueError("unknown gateway error code")
        self.code = code
        super().__init__(code)


def classify(exc: Exception) -> tuple[int, str]:
    if isinstance(exc, GatewayError):
        code = exc.code
    elif isinstance(exc, VerificationError):
        code = exc.code
    elif isinstance(exc, ExecutionError):
        code = _EXECUTION.get(exc.code.value, "INTERNAL_ERROR")
    elif isinstance(exc, LedgerError):
        code = _LEDGER.get(exc.code.value, exc.code.value)
    elif isinstance(
        exc,
        (
            EvidenceError,
            PermissionSnapshotError,
            ReceiptProjectionError,
            psycopg.Error,
            TimeoutError,
        ),
    ):
        code = "TRUSTED_STATE_UNAVAILABLE"
    else:
        code = "INTERNAL_ERROR"
    if code not in _STATUS:
        code = "INTERNAL_ERROR"
    return _STATUS[code], code
