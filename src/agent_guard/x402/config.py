"""Fixed local x402 deployment configuration (trusted operator input).

Every payment fact lives here and is never taken from a request, a model, a
402 challenge or a browser. The only mutable-by-run value is the address of
the token deployed by the local chain bootstrap; even that is fixed in the
configuration object before any operation is accepted.

The resource server is intentionally restricted to loopback HTTP(S); this is
the local test-chain profile and it must not be reused as a production
configuration (no production TLS disabling code exists here).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from agent_guard.x402.contracts import (
    PaymentOffer,
    PaymentProfile,
    X402Error,
)

_REQUIRED = (
    "AG_X402_GATEWAY_DSN",
    "AG_X402_PAYER_KEY",
    "AG_X402_FACILITATOR_KEY",
    "AG_X402_RPC_URL",
    "AG_X402_TOKEN",
    "AG_X402_PAY_TO",
    "AG_X402_RESOURCE_URL",
    "AG_X402_STATUS_URL",
    "AG_X402_OFFER_QUOTE_ID",
    "AG_X402_OFFER_QUOTE_VERSION",
    "AG_X402_OFFER_ASSET_AMOUNT",
)

_LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value or len(value) > 4096:
        raise X402Error(f"missing deployment configuration: {name}", code="CONFIG_MISSING")
    return value


def _bounded_int(name: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise X402Error(f"invalid deployment configuration: {name}", code="CONFIG_INVALID")
    if not minimum <= value <= maximum:
        raise X402Error(f"invalid deployment configuration: {name}", code="CONFIG_INVALID")
    return value


def _loopback_url(name: str, value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise X402Error(f"invalid deployment configuration: {name}", code="CONFIG_INVALID") from exc
    if parsed.scheme not in ("http", "https") or parsed.hostname not in _LOOPBACK_HOSTS:
        raise X402Error(f"{name} must use a loopback test endpoint", code="CONFIG_NOT_LOOPBACK")
    if parsed.username or parsed.password or parsed.fragment:
        raise X402Error(f"invalid deployment configuration: {name}", code="CONFIG_INVALID")
    if parsed.query:
        raise X402Error(f"invalid deployment configuration: {name}", code="CONFIG_INVALID")
    return value


@dataclass(frozen=True)
class X402Deployment:
    """One immutable local deployment; keys are synthetic test keys only."""

    gateway_dsn: str
    rpc_url: str
    chain_id: int
    token: str
    asset_name: str
    asset_version: str
    pay_to: str
    resource_url: str
    status_url: str
    offer: PaymentOffer
    max_timeout_seconds: int
    payer_key: str
    facilitator_key: str
    http_timeout_seconds: int = 15
    chain_confirm_timeout_seconds: int = 60

    def __post_init__(self) -> None:
        _loopback_url("AG_X402_RPC_URL", self.rpc_url)
        _loopback_url("AG_X402_RESOURCE_URL", self.resource_url)
        _loopback_url("AG_X402_STATUS_URL", self.status_url)
        _bounded_int("chain_id", self.chain_id, minimum=1, maximum=9007199254740991)
        _bounded_int("max_timeout_seconds", self.max_timeout_seconds, minimum=1, maximum=86400)
        _bounded_int("http_timeout_seconds", self.http_timeout_seconds, minimum=1, maximum=120)
        _bounded_int(
            "chain_confirm_timeout_seconds",
            self.chain_confirm_timeout_seconds,
            minimum=1,
            maximum=600,
        )
        if type(self.payer_key) is not str or not self.payer_key.startswith("0x"):
            raise X402Error("invalid payer key", code="CONFIG_INVALID")
        if type(self.facilitator_key) is not str or not self.facilitator_key.startswith("0x"):
            raise X402Error("invalid facilitator key", code="CONFIG_INVALID")
        if self.payer_key.lower() == self.facilitator_key.lower():
            raise X402Error("payer and facilitator keys must differ", code="CONFIG_INVALID")
        # Build once at construction so an inconsistent profile fails closed
        # before any operation can be accepted.
        _ = self.profile

    @property
    def profile(self) -> PaymentProfile:
        return PaymentProfile(
            network=f"eip155:{self.chain_id}",
            chain_id=self.chain_id,
            asset=self.token,
            asset_name=self.asset_name,
            asset_version=self.asset_version,
            pay_to=self.pay_to,
            resource_url=self.resource_url,
            status_url=self.status_url,
            max_timeout_seconds=self.max_timeout_seconds,
            offers=(self.offer,),
        )

    @classmethod
    def from_env(cls) -> "X402Deployment":
        values = {name: _require_env(name) for name in _REQUIRED}
        try:
            raw_chain_id = int(os.environ.get("AG_X402_CHAIN_ID", "31337"))
        except ValueError as exc:
            raise X402Error(
                "invalid deployment configuration: AG_X402_CHAIN_ID", code="CONFIG_INVALID"
            ) from exc
        chain_id = _bounded_int(
            "AG_X402_CHAIN_ID", raw_chain_id, minimum=1, maximum=9007199254740991
        )
        try:
            raw_timeout = int(os.environ.get("AG_X402_MAX_TIMEOUT_SECONDS", "3600"))
        except ValueError as exc:
            raise X402Error(
                "invalid deployment configuration: AG_X402_MAX_TIMEOUT_SECONDS",
                code="CONFIG_INVALID",
            ) from exc
        max_timeout_seconds = _bounded_int(
            "AG_X402_MAX_TIMEOUT_SECONDS", raw_timeout, minimum=1, maximum=86400
        )
        deployment = cls(
            gateway_dsn=values["AG_X402_GATEWAY_DSN"],
            rpc_url=values["AG_X402_RPC_URL"],
            chain_id=chain_id,
            token=values["AG_X402_TOKEN"].lower(),
            asset_name=os.environ.get("AG_X402_ASSET_NAME", "USD Coin"),
            asset_version=os.environ.get("AG_X402_ASSET_VERSION", "2"),
            pay_to=values["AG_X402_PAY_TO"].lower(),
            resource_url=values["AG_X402_RESOURCE_URL"],
            status_url=values["AG_X402_STATUS_URL"],
            offer=PaymentOffer(
                quote_id=values["AG_X402_OFFER_QUOTE_ID"],
                quote_version=values["AG_X402_OFFER_QUOTE_VERSION"],
                asset_amount=values["AG_X402_OFFER_ASSET_AMOUNT"],
            ),
            max_timeout_seconds=max_timeout_seconds,
            payer_key=values["AG_X402_PAYER_KEY"],
            facilitator_key=values["AG_X402_FACILITATOR_KEY"],
        )
        return deployment

    def profile_for_token(self, token: str) -> PaymentProfile:
        """Profile with the token deployed by this run (same trusted facts)."""
        return PaymentProfile(
            network=f"eip155:{self.chain_id}",
            chain_id=self.chain_id,
            asset=token.lower(),
            asset_name=self.asset_name,
            asset_version=self.asset_version,
            pay_to=self.pay_to,
            resource_url=self.resource_url,
            status_url=self.status_url,
            max_timeout_seconds=self.max_timeout_seconds,
            offers=(self.offer,),
        )
