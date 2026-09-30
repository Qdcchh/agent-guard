"""Pure format validation for trusted in-process inputs.

Runs before any database access so that malformed input can never touch the
ledger. Boolean values are explicitly rejected before integer checks because
``isinstance(True, int)`` is true in Python; floats are never accepted where
integers are required. All rejections carry explicit :class:`ErrorCode` values.
"""

from __future__ import annotations

from agent_guard.contracts.ledger import (
    CURRENCY,
    INVOKE_ENDPOINT,
    INVOKE_METHOD,
    MAX_ANCESTOR_IDS,
    MAX_DIGEST_LEN,
    MAX_EVIDENCE_REF_LEN,
    MAX_ID_LEN,
    MAX_KID_LEN,
    MAX_PARAMS_BYTES,
    MAX_SAFE_INT,
    MAX_SNAPSHOT_BYTES,
    PROFILE,
    PROOF_MAX_LIFETIME_S,
    PURPOSE_INVOKE,
    TOOL_VERSION,
    ErrorCode,
    LedgerError,
    TrustedCost,
    VerifiedInvocation,
)

_CONTROL_CHARS = {chr(i) for i in range(32)} | {"\x7f"}


def _require_str(
    name: str, value: object, max_len: int, code: ErrorCode = ErrorCode.INVALID_CONTEXT
) -> str:
    if not isinstance(value, str):
        raise LedgerError(code, f"{name} must be a string")
    if value == "":
        raise LedgerError(code, f"{name} must not be empty")
    if len(value) > max_len:
        raise LedgerError(code, f"{name} exceeds {max_len} chars")
    if any(ch in _CONTROL_CHARS for ch in value):
        raise LedgerError(code, f"{name} contains control characters")
    return value


def _require_int(name: str, value: object, code: ErrorCode, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerError(code, f"{name} must be an integer (bool/float rejected)")
    if value < minimum or value > MAX_SAFE_INT:
        raise LedgerError(code, f"{name} outside [{minimum}, {MAX_SAFE_INT}]")
    return value


def _require_bytes(name: str, value: object, max_len: int) -> bytes:
    if not isinstance(value, bytes):
        raise LedgerError(ErrorCode.INVALID_CONTEXT, f"{name} must be bytes")
    if len(value) > max_len:
        raise LedgerError(ErrorCode.INVALID_CONTEXT, f"{name} exceeds {max_len} bytes")
    return value


def validate_invocation(verified: VerifiedInvocation) -> None:
    """Reject malformed context before any database work (``INVALID_CONTEXT``)."""
    if not isinstance(verified, VerifiedInvocation):
        raise LedgerError(ErrorCode.INVALID_CONTEXT, "not a VerifiedInvocation")

    if verified.profile != PROFILE:
        raise LedgerError(ErrorCode.INVALID_CONTEXT, "unsupported profile")
    if verified.purpose != PURPOSE_INVOKE:
        raise LedgerError(ErrorCode.INVALID_CONTEXT, "unsupported purpose")
    if verified.endpoint != INVOKE_ENDPOINT:
        raise LedgerError(ErrorCode.INVALID_CONTEXT, "unexpected endpoint")
    if verified.method != INVOKE_METHOD:
        raise LedgerError(ErrorCode.INVALID_CONTEXT, "unexpected method")
    if verified.tool_version != TOOL_VERSION:
        raise LedgerError(ErrorCode.INVALID_CONTEXT, "unsupported tool_version")

    _require_str("subject", verified.subject, MAX_ID_LEN)
    _require_str("tenant_id", verified.tenant_id, MAX_ID_LEN)
    _require_str("task_id", verified.task_id, MAX_ID_LEN)
    _require_str("grant_id", verified.grant_id, MAX_ID_LEN)
    _require_str("root_id", verified.root_id, MAX_ID_LEN)
    _require_str("holder_client_id", verified.holder_client_id, MAX_ID_LEN)
    _require_str("holder_kid", verified.holder_kid, MAX_KID_LEN)
    _require_str("tool_id", verified.tool_id, MAX_ID_LEN)
    _require_str("idempotency_key", verified.idempotency_key, MAX_ID_LEN)
    _require_str("proof_jti", verified.proof_jti, MAX_ID_LEN)
    _require_str("token_digest", verified.token_digest, MAX_DIGEST_LEN)
    _require_str("proof_digest", verified.proof_digest, MAX_DIGEST_LEN)
    _require_str("intent_digest", verified.intent_digest, MAX_DIGEST_LEN)
    _require_str("evidence_ref", verified.evidence_ref, MAX_EVIDENCE_REF_LEN)

    _require_bytes("canonical_params", verified.canonical_params, MAX_PARAMS_BYTES)

    _require_int("token_exp", verified.token_exp, ErrorCode.INVALID_CONTEXT)
    proof_iat = _require_int("proof_iat", verified.proof_iat, ErrorCode.INVALID_CONTEXT)
    proof_exp = _require_int("proof_exp", verified.proof_exp, ErrorCode.INVALID_CONTEXT)

    if verified.ancestor_ids is not None:
        if not isinstance(verified.ancestor_ids, tuple):
            raise LedgerError(ErrorCode.INVALID_CONTEXT, "ancestor_ids must be a tuple or None")
        if len(verified.ancestor_ids) > MAX_ANCESTOR_IDS:
            raise LedgerError(ErrorCode.INVALID_CONTEXT, "ancestor_ids too long")
        for item in verified.ancestor_ids:
            _require_str("ancestor_ids item", item, MAX_ID_LEN)

    # Structural proof window; comparisons against the clock happen after locks
    # using the database's actual current time (see service.accept).
    if proof_exp < proof_iat:
        raise LedgerError(ErrorCode.STALE_REQUEST, "proof_exp before proof_iat")
    if proof_exp > proof_iat + PROOF_MAX_LIFETIME_S:
        raise LedgerError(ErrorCode.STALE_REQUEST, "proof lifetime exceeds limit")


def validate_cost(cost: TrustedCost) -> None:
    """Reject malformed trusted cost before any database work (``INVALID_COST``)."""
    if not isinstance(cost, TrustedCost):
        raise LedgerError(ErrorCode.INVALID_COST, "not a TrustedCost")
    if cost.currency != CURRENCY:
        raise LedgerError(ErrorCode.INVALID_COST, "unsupported currency")
    _require_int("amount_fen", cost.amount_fen, ErrorCode.INVALID_COST)
    _require_int("calls", cost.calls, ErrorCode.INVALID_COST, minimum=1)
    # Billing contract: one new operation always costs exactly one call
    # (reads/notifications included); A1 has no multi-call operations.
    if cost.calls != 1:
        raise LedgerError(ErrorCode.INVALID_COST, "calls must be exactly 1")
    if cost.quote_id is not None:
        _require_str("quote_id", cost.quote_id, MAX_ID_LEN, ErrorCode.INVALID_COST)
    if cost.quote_version is not None:
        _require_str("quote_version", cost.quote_version, MAX_ID_LEN, ErrorCode.INVALID_COST)
    if cost.quote_snapshot is not None:
        if not isinstance(cost.quote_snapshot, bytes):
            raise LedgerError(ErrorCode.INVALID_COST, "quote_snapshot must be bytes")
        if len(cost.quote_snapshot) > MAX_SNAPSHOT_BYTES:
            raise LedgerError(ErrorCode.INVALID_COST, "quote_snapshot too large")
