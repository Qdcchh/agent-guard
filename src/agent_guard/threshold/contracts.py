"""Trusted in-process contracts for the versioned threshold approval.

The approval is a *separate* credential from the SM2 token/AGPoP pair. It never
replaces current authorization, revocation, budget or proof-freshness checks:
it proves that the configured FROST quorum or COSM2 parties approved the exact action the
gateway is about to accept.

Trust boundary: :class:`VerifiedThresholdApproval` is produced only by
``agent_guard.threshold.verifier`` after an actual configured Ed25519 or mature SM2 signature
check. A request can never deserialize directly into it; the HTTP layer only
passes opaque header bytes.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_guard.authorization.claims import GATEWAY_AUDIENCE

PROFILE = "AG-THRESHOLD-APPROVAL-1"
COSM2_PROFILE = "AG-COSM2-APPROVAL-1"
COSM2_DOMAIN = b"AGENT-GUARD-COSM2-ACTION-V1\n"
ACTION_DOMAIN = b"AGENT-GUARD-THRESHOLD-ACTION-V2\n"
ACTION_VERSION = 2
#: x402-bound action: V2 fields plus the payment-intent digest as the last
#: field. The V2 domain and bytes stay frozen for existing approvals.
ACTION_DOMAIN_V3 = b"AGENT-GUARD-THRESHOLD-ACTION-V3\n"
ACTION_VERSION_V3 = 3
TOOL_ID = "procurement.order.create"
TOOL_VERSION = "1"
CURRENCY = "CNY"

#: Bounded detached-header capacity (the envelope plus signature as base64url).
MAX_HEADER_BYTES = 32768
#: Bounded envelope capacity after base64url decoding.
MAX_ENVELOPE_BYTES = 24576
MAX_ACTION_ITEMS = 256
MAX_PATH_IDS = 3
MAX_IDENTIFIER = 128
MAX_LIFETIME_SECONDS = 86400
MAX_VERSION = 2**53 - 1


class ThresholdApprovalError(ValueError):
    """Typed rejection with a stable code; never carries raw header bytes."""

    def __init__(self, detail: str, *, code: str = "INVALID_APPROVAL"):
        self.code = code
        super().__init__(detail)


class COSM2ApprovalExpired(ThresholdApprovalError):
    """COSM2 approval expiry, distinct from authorization and FROST expiry."""

    def __init__(self):
        super().__init__("COSM2 approval expired", code="EXPIRED")


@dataclass(frozen=True)
class ThresholdApprovalPolicy:
    """Trusted operator configuration; the request never supplies any of it."""

    group_public_key: bytes
    policy_version: int
    key_epoch: int
    max_lifetime_seconds: int = 3600
    tool_id: str = TOOL_ID
    audience: str = GATEWAY_AUDIENCE

    scheme: str = "frost-ed25519"

    def __post_init__(self):
        if self.scheme == "frost-ed25519":
            if type(self.group_public_key) is not bytes or len(self.group_public_key) != 32:
                raise ThresholdApprovalError("group public key must be 32 raw bytes")
        elif self.scheme == "sm2-2p":
            from agent_guard.crypto.sm import load_sm2_public_key

            try:
                load_sm2_public_key(self.group_public_key)
            except (ValueError, TypeError) as exc:
                raise ThresholdApprovalError("canonical SM2 SPKI required") from exc
        else:
            raise ThresholdApprovalError("unsupported trusted approval scheme")
        for name in ("policy_version", "key_epoch", "max_lifetime_seconds"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= MAX_VERSION
            ):
                raise ThresholdApprovalError(f"invalid trusted {name}")
        if self.max_lifetime_seconds > MAX_LIFETIME_SECONDS:
            raise ThresholdApprovalError("trusted approval lifetime is unbounded")
        if self.tool_id != TOOL_ID or self.audience != GATEWAY_AUDIENCE:
            raise ThresholdApprovalError("unsupported trusted approval scope")


@dataclass(frozen=True)
class ThresholdApprovalExpectation:
    """Facts the verified SM2/AGPoP invocation already proved for this request."""

    tenant_id: str
    task_id: str
    root_grant_id: str
    grant_id: str
    holder_client_id: str
    holder_kid: str
    tool_id: str
    tool_version: str
    idempotency_key: str
    canonical_params: bytes
    path_grant_ids: tuple[str, ...] | None = None
    amount_fen: int | None = None


@dataclass(frozen=True)
class VerifiedThresholdApproval:
    """Immutable, signature-checked approval facts carried into the accept TX."""

    action_id: str
    tenant_id: str
    task_id: str
    root_grant_id: str
    grant_id: str
    path_grant_ids: tuple[str, ...]
    holder_client_id: str
    holder_kid: str
    audience: str
    tool_id: str
    tool_version: str
    currency: str
    policy_version: int
    key_epoch: int
    idempotency_key: str
    request_id: str
    quote_id: str
    quote_version: str
    items: tuple[tuple[str, int], ...]
    delivery_id: str
    amount_fen: int
    canonical_params_sha256: str
    expires_at: int
    message_sha256: str
    envelope_bytes: bytes
    envelope_sm3: str
    signature: bytes
    #: Set only for a signature-checked V3 action; the digest of the exact
    #: x402 payment intent the quorum approved. ``None`` for V2 approvals.
    payment_digest: str | None = None
