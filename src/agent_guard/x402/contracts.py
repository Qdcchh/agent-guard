"""Trusted in-process contracts for the fixed local x402 exact/EVM profile.

The x402 layer never accepts payment facts from a request or from a remote
``402`` challenge. All trusted values in this module are produced either by
operator configuration (``PaymentProfile``), by the existing accepted
operation (operation facts, quote identity, CNY amount) or by the verified V3
threshold approval (``payment_digest``). Remote wire objects are parsed into
plain, validated dictionaries by :mod:`agent_guard.x402.wire` and compared
against these trusted objects; they never become trusted types directly.

Pinned profile: x402 v2 transport, ``exact`` scheme on ``eip155`` with the
``eip3009`` asset transfer method. No other scheme, transfer method or network
family is accepted.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum

from agent_guard.contracts.encoding import canonical_json_bytes

PROFILE = "AG-X402-PAYMENT-INTENT-1"
WIRE_VERSION = 2
SCHEME = "exact"
TRANSFER_METHOD = "eip3009"
NETWORK_PATTERN = re.compile(r"eip155:[1-9][0-9]{0,17}\Z", re.ASCII)
ADDRESS_PATTERN = re.compile(r"0x[0-9a-fA-F]{40}\Z", re.ASCII)
LOWER_ADDRESS_PATTERN = re.compile(r"0x[0-9a-f]{40}\Z", re.ASCII)
DECIMAL_PATTERN = re.compile(r"[1-9][0-9]{0,77}\Z", re.ASCII)
NONCE_PATTERN = re.compile(r"0x[0-9a-f]{64}\Z", re.ASCII)
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

#: Bounded sizes for wire parsing (never unbounded header/body material).
MAX_HEADER_BYTES = 65536
MAX_BODY_BYTES = 65536
MAX_REQUIREMENTS = 8
MAX_RESOURCE_DESCRIPTION = 512
MAX_IDENTIFIER = 128

#: The exact field order of the payment digest. Both the approving signer and
#: the accept transaction build the digest from these semantic fields; the
#: message is the RFC 8785 canonical JSON encoding of the fixed-order object.
DIGEST_FIELDS = (
    "profile",
    "tenant_id",
    "task_id",
    "grant_id",
    "root_grant_id",
    "tool_id",
    "idempotency_key",
    "quote_id",
    "quote_version",
    "amount_fen",
    "scheme",
    "transfer_method",
    "network",
    "chain_id",
    "asset",
    "asset_name",
    "asset_version",
    "asset_amount",
    "pay_to",
    "resource_url",
    "valid_before",
)


class X402Error(ValueError):
    """Typed rejection with a stable code; never carries raw payment bytes."""

    def __init__(self, detail: str, *, code: str = "X402_INVALID"):
        self.code = code
        super().__init__(detail)


class PaymentStatus(str, Enum):
    """Durable payment state machine (never a claim about resource delivery)."""

    UNPAID = "UNPAID"
    AUTHORIZED = "AUTHORIZED"
    SUBMITTING = "SUBMITTING"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


TERMINAL_PAYMENT_STATUSES = (PaymentStatus.SETTLED, PaymentStatus.FAILED)


@dataclass(frozen=True)
class PaymentOffer:
    """One trusted, explicit test-asset price for one quote version.

    There is deliberately no CNY-to-asset computation anywhere: the operator
    seeds the asset amount in the same trusted configuration that the V3
    approval covers, and the ``amount_fen`` field only records the already
    approved CNY reference cost.
    """

    quote_id: str
    quote_version: str
    asset_amount: str  # canonical decimal string, smallest unit

    def __post_init__(self):
        if type(self.quote_id) is not str or not 1 <= len(self.quote_id) <= MAX_IDENTIFIER:
            raise X402Error("invalid offer quote_id")
        if type(self.quote_version) is not str or not self.quote_version.isdigit():
            raise X402Error("invalid offer quote_version")
        if (
            type(self.asset_amount) is not str
            or DECIMAL_PATTERN.fullmatch(self.asset_amount) is None
        ):
            raise X402Error("asset amount must be a canonical decimal string")

    @property
    def key(self) -> str:
        return f"{self.quote_id}@{self.quote_version}"


@dataclass(frozen=True)
class PaymentProfile:
    """Trusted operator profile for one fixed local x402 deployment.

    The resource URL, recipient, network, asset and per-quote asset amounts are
    all fixed here. A request, a model or the remote resource server can never
    extend or alter this profile; mismatching payment facts are refused before
    any signature is created.
    """

    network: str
    chain_id: int
    asset: str
    asset_name: str
    asset_version: str
    pay_to: str
    resource_url: str
    status_url: str
    max_timeout_seconds: int
    offers: tuple[PaymentOffer, ...]

    def __post_init__(self):
        if NETWORK_PATTERN.fullmatch(self.network or "") is None:
            raise X402Error("invalid payment network")
        if self.network != f"eip155:{self.chain_id}":
            raise X402Error("network and chain id differ")
        if isinstance(self.chain_id, bool) or not isinstance(self.chain_id, int):
            raise X402Error("invalid chain id")
        for name, value in (("asset", self.asset), ("pay_to", self.pay_to)):
            if type(value) is not str or LOWER_ADDRESS_PATTERN.fullmatch(value) is None:
                raise X402Error(f"invalid {name}")
        for name, value, upper in (
            ("asset_name", self.asset_name, MAX_IDENTIFIER),
            ("asset_version", self.asset_version, 32),
        ):
            if type(value) is not str or not 1 <= len(value) <= upper:
                raise X402Error(f"invalid {name}")
        for name, value in (("resource_url", self.resource_url), ("status_url", self.status_url)):
            if type(value) is not str or not 1 <= len(value) <= 512:
                raise X402Error(f"invalid {name}")
        if isinstance(self.max_timeout_seconds, bool) or not (
            isinstance(self.max_timeout_seconds, int) and 1 <= self.max_timeout_seconds <= 86400
        ):
            raise X402Error("invalid payment timeout")
        if not isinstance(self.offers, tuple) or not self.offers:
            raise X402Error("at least one trusted payment offer is required")
        seen = set()
        for offer in self.offers:
            if type(offer) is not PaymentOffer:
                raise X402Error("trusted payment offers required")
            if offer.key in seen:
                raise X402Error("duplicate payment offer")
            seen.add(offer.key)

    def offer_for(self, quote_id: str, quote_version: str) -> PaymentOffer:
        for offer in self.offers:
            if offer.quote_id == quote_id and offer.quote_version == quote_version:
                return offer
        raise X402Error("no trusted payment offer for the quote", code="NO_PAYMENT_OFFER")

    def offer_for_key(self, key: str) -> PaymentOffer:
        quote_id, _, quote_version = key.partition("@")
        if not quote_version:
            raise X402Error("invalid payment offer key")
        return self.offer_for(quote_id, quote_version)


@dataclass(frozen=True)
class PaymentIntent:
    """Immutable payment facts of one accepted operation.

    ``digest`` is exactly the value the V3 threshold action signed as
    ``payment_digest``. The digest covers every field of this object, so a
    402 challenge that changes any payment fact can never be signed.
    """

    tenant_id: str
    task_id: str
    grant_id: str
    root_grant_id: str
    tool_id: str
    idempotency_key: str
    quote_id: str
    quote_version: str
    amount_fen: int
    network: str
    chain_id: int
    asset: str
    asset_name: str
    asset_version: str
    asset_amount: str
    pay_to: str
    resource_url: str
    valid_before: int
    digest: str

    @property
    def network_chain(self) -> int:
        return int(self.network.split(":", 1)[1])

    def digest_material(self) -> dict:
        return {
            "profile": PROFILE,
            "tenant_id": self.tenant_id,
            "task_id": self.task_id,
            "grant_id": self.grant_id,
            "root_grant_id": self.root_grant_id,
            "tool_id": self.tool_id,
            "idempotency_key": self.idempotency_key,
            "quote_id": self.quote_id,
            "quote_version": self.quote_version,
            "amount_fen": self.amount_fen,
            "scheme": SCHEME,
            "transfer_method": TRANSFER_METHOD,
            "network": self.network,
            "chain_id": self.chain_id,
            "asset": self.asset,
            "asset_name": self.asset_name,
            "asset_version": self.asset_version,
            "asset_amount": self.asset_amount,
            "pay_to": self.pay_to,
            "resource_url": self.resource_url,
            "valid_before": self.valid_before,
        }


def compute_intent_digest(facts: dict) -> str:
    """SHA-256 over the canonical fixed-order payment facts.

    The function is total over ``DIGEST_FIELDS``: a missing or extra key is a
    hard error instead of a silently different digest.
    """
    if type(facts) is not dict or set(facts) != set(DIGEST_FIELDS):
        raise X402Error("exact payment digest fields required", code="INVALID_DIGEST_FIELDS")
    ordered = {name: facts[name] for name in DIGEST_FIELDS}
    return hashlib.sha256(canonical_json_bytes(ordered)).hexdigest()


def build_intent(
    *,
    profile: PaymentProfile,
    tenant_id: str,
    task_id: str,
    grant_id: str,
    root_grant_id: str,
    tool_id: str,
    idempotency_key: str,
    quote_id: str,
    quote_version: str,
    amount_fen: int,
    valid_before: int,
) -> PaymentIntent:
    """Build the payment intent from trusted accept facts plus the profile."""
    offer = profile.offer_for(quote_id, quote_version)
    if isinstance(amount_fen, bool) or not isinstance(amount_fen, int) or amount_fen < 0:
        raise X402Error("invalid CNY reference amount")
    if isinstance(valid_before, bool) or not isinstance(valid_before, int) or valid_before < 1:
        raise X402Error("invalid payment validity bound")
    facts = {
        "profile": PROFILE,
        "tenant_id": tenant_id,
        "task_id": task_id,
        "grant_id": grant_id,
        "root_grant_id": root_grant_id,
        "tool_id": tool_id,
        "idempotency_key": idempotency_key,
        "quote_id": quote_id,
        "quote_version": quote_version,
        "amount_fen": amount_fen,
        "scheme": SCHEME,
        "transfer_method": TRANSFER_METHOD,
        "network": profile.network,
        "chain_id": profile.chain_id,
        "asset": profile.asset,
        "asset_name": profile.asset_name,
        "asset_version": profile.asset_version,
        "asset_amount": offer.asset_amount,
        "pay_to": profile.pay_to,
        "resource_url": profile.resource_url,
        "valid_before": valid_before,
    }
    return PaymentIntent(
        tenant_id=tenant_id,
        task_id=task_id,
        grant_id=grant_id,
        root_grant_id=root_grant_id,
        tool_id=tool_id,
        idempotency_key=idempotency_key,
        quote_id=quote_id,
        quote_version=quote_version,
        amount_fen=amount_fen,
        network=profile.network,
        chain_id=profile.chain_id,
        asset=profile.asset,
        asset_name=profile.asset_name,
        asset_version=profile.asset_version,
        asset_amount=offer.asset_amount,
        pay_to=profile.pay_to,
        resource_url=profile.resource_url,
        valid_before=valid_before,
        digest=compute_intent_digest(facts),
    )


def require_approval_digest(intent: PaymentIntent, approval_digest: str | None) -> None:
    """The V3 approval must carry exactly this payment digest."""
    if (
        approval_digest is None
        or DIGEST_PATTERN.fullmatch(approval_digest or "") is None
        or approval_digest != intent.digest
    ):
        raise X402Error(
            "threshold approval does not cover this payment intent",
            code="PAYMENT_DIGEST_MISMATCH",
        )
