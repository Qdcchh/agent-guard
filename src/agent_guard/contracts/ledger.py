"""Minimal trusted in-process contracts for the A1 execution ledger.

This module defines the smallest shared input/output types needed by the
accept transaction. It contains no cryptography and no network entry point.

Trust boundary: ``VerifiedInvocation`` is a *trusted in-process input*. It is
NOT a cryptographic proof. A frozen dataclass only prevents accidental
mutation; it cannot defend against malicious code in the same process.
Only B's future verifier (``InvocationVerifier.verify_static``) is allowed to
construct it in production. HTTP requests must never deserialize directly
into it. Tests constructing it directly is legitimate layered testing and is
not a claim that signature verification has happened.

A1 does not implement RFC 8785 canonicalization, SM3, token parsing or any
OAuth/OIDC endpoint. Digest fields are opaque strings carried through to
storage; idempotency comparison additionally checks the raw intent fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

#: GM-MVP-1 arithmetic bound: integers must fit in IEEE-754 safe range.
MAX_SAFE_INT = 2**53 - 1

#: Fixed profile identifier; mixing with the legacy capability-credential v1
#: profile is forbidden.
PROFILE = "GM-MVP-1"

#: Only purpose accepted by :meth:`ExecutionLedger.accept`.
PURPOSE_INVOKE = "invoke"

#: Purpose of the read-only operation query; never reserves budget.
PURPOSE_RESULT_READ = "result-read"

#: Fixed gateway audience/endpoint for tool invocations (no caller-supplied URLs).
INVOKE_ENDPOINT = "https://gateway.agent-guard.test/v1/invocations"

#: Fixed gateway endpoint for authorized result reads (no caller-supplied URLs).
QUERY_ENDPOINT = "https://gateway.agent-guard.test/v1/operations/query"

#: Fixed HTTP method bound by the future AG-Proof.
INVOKE_METHOD = "POST"

#: The single supported tool version, as a string, not an integer.
TOOL_VERSION = "1"

#: The single supported currency; amounts are integer fen (cents).
CURRENCY = "CNY"

#: Maximum proof lifetime: ``proof_exp <= proof_iat + PROOF_MAX_LIFETIME_S``.
PROOF_MAX_LIFETIME_S = 60

#: Maximum tolerated clock skew for ``proof_iat`` being in the future.
PROOF_MAX_FUTURE_SKEW_S = 5

#: Structural cap on ancestor lists (root + at most two child levels).
MAX_ANCESTOR_IDS = 2

#: Field length caps (format validation, reasonable upper bounds).
MAX_ID_LEN = 128
MAX_KID_LEN = 256
MAX_EVIDENCE_REF_LEN = 512
MAX_DIGEST_LEN = 128
MAX_PARAMS_BYTES = 65536
MAX_SNAPSHOT_BYTES = 65536


class ErrorCode(str, Enum):
    """Explicit rejection codes for the in-process accept interface.

    These are internal status values, not HTTP statuses; A2 maps them later.
    Mapping conventions used by A1 (documented in ``tasks/A1-report.md``):

    - ``INVALID_CONTEXT``: malformed/unsupported invocation context (bad
      profile/purpose/endpoint/method/tool_version, unknown grant, tenant or
      task mismatch, forged root, truncated/looping ancestor path).
    - ``INVALID_COST``: malformed trusted cost (non-CNY, bool/float/negative/
      out-of-range amount or calls).
    - ``HOLDER_MISMATCH``: holder binding failure (verified holder differs from
      the grant holder, holder key not registered, or key deactivated).
    - ``EXPIRED``: outside an authorization validity window (any grant node not
      yet effective or expired, or ``token_exp`` passed).
    - ``REVOKED``: any node on the path is revoked.
    - ``STALE_REQUEST``: proof freshness failure (``proof_iat`` too far in the
      future, ``proof_exp`` passed, or structural ``iat <= exp <= iat+60``
      violation).
    - ``REPLAY``: ``(holder_kid, purpose, endpoint, proof_jti)`` already used.
    - ``IDEMPOTENCY_CONFLICT``: business key reused with a different intent.
    - ``BUDGET_EXCEEDED``: amount budget insufficient at an applicable node.
    - ``CALL_LIMIT_EXCEEDED``: call-count limit insufficient at a node.
    - ``TRUSTED_STATE_UNAVAILABLE``: database unreachable/timeout; fail closed,
      never presented as success or as an idempotent hit.
    """

    INVALID_CONTEXT = "INVALID_CONTEXT"
    INVALID_COST = "INVALID_COST"
    HOLDER_MISMATCH = "HOLDER_MISMATCH"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    STALE_REQUEST = "STALE_REQUEST"
    REPLAY = "REPLAY"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    CALL_LIMIT_EXCEEDED = "CALL_LIMIT_EXCEEDED"
    TRUSTED_STATE_UNAVAILABLE = "TRUSTED_STATE_UNAVAILABLE"


class AcceptDisposition(str, Enum):
    """Whether this call created the operation or hit an existing one."""

    CREATED = "CREATED"
    EXISTING = "EXISTING"


class LedgerError(Exception):
    """Raised for every rejected accept, carrying an explicit :class:`ErrorCode`."""

    def __init__(self, code: ErrorCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}" if detail else code.value)


@dataclass(frozen=True)
class VerifiedInvocation:
    """Trusted in-process invocation context (see module docstring).

    Field semantics follow ``docs/oauth-oidc-sm2-mvp.md`` sections 8/9/10 and
    ``tasks/A1-ledger.md`` section 3.1. ``ancestor_ids`` when provided is the
    full root-to-parent path in root-first order and must match the database
    path exactly; the immutable database parent chain remains authoritative.
    """

    subject: str
    tenant_id: str
    task_id: str
    grant_id: str
    root_id: str
    holder_client_id: str
    holder_kid: str
    tool_id: str
    idempotency_key: str
    canonical_params: bytes
    token_exp: int
    proof_iat: int
    proof_exp: int
    proof_jti: str
    token_digest: str
    proof_digest: str
    intent_digest: str
    evidence_ref: str
    ancestor_ids: tuple[str, ...] | None = None
    profile: str = PROFILE
    purpose: str = PURPOSE_INVOKE
    endpoint: str = INVOKE_ENDPOINT
    method: str = INVOKE_METHOD
    tool_version: str = TOOL_VERSION


@dataclass(frozen=True)
class TrustedCost:
    """Trusted cost of one operation, from A2's quote resolver, not the client.

    A1 receives it from test fixtures only. There is no public "pay whatever
    you claim" interface. Read/notify tools use ``amount_fen=0``; every new
    operation still costs one call. The quote snapshot is fixed at first
    accept and reused for idempotent retries without re-pricing.
    """

    amount_fen: int
    calls: int = 1
    currency: str = CURRENCY
    quote_id: str | None = None
    quote_version: str | None = None
    quote_snapshot: bytes | None = field(default=None)


@dataclass(frozen=True)
class AcceptResult:
    """Successful accept result; internal status values, not HTTP codes.

    For ``EXISTING`` hits the *original* cost snapshot and the *original*
    ``accepted_at`` are returned: retries never re-price or re-reserve.
    """

    operation_id: str
    grant_id: str
    root_id: str
    status: str
    disposition: AcceptDisposition
    cost: TrustedCost
    accepted_at: datetime

    @property
    def is_created(self) -> bool:
        return self.disposition is AcceptDisposition.CREATED
