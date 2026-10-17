"""Binding between the trusted payment intent and untrusted x402 wire objects.

The remote ``402`` challenge, the requirements echoed in a payment payload and
the signable authorization fields are all *untrusted input*. This module
compares them against the immutable :class:`PaymentIntent` built from the
accepted operation and the trusted profile; only exact matches pass. A
mismatch is a hard refusal and never a reason to re-sign with new values.
"""

from __future__ import annotations

from agent_guard.x402.contracts import (
    PaymentIntent,
    PaymentProfile,
    X402Error,
)


def check_challenge(*, profile: PaymentProfile, intent: PaymentIntent, challenge: dict) -> dict:
    """Select and verify the single acceptable requirement of a challenge.

    Rejects an empty list, more than one matching entry, unsupported entries
    and any fact that differs from the trusted intent.
    """
    matches = [
        requirements
        for requirements in challenge["accepts"]
        if _requirement_matches(intent=intent, requirements=requirements)
    ]
    if len(matches) != 1:
        raise X402Error(
            "402 challenge does not offer exactly the accepted payment",
            code="CHALLENGE_MISMATCH",
        )
    resource = challenge.get("resource")
    if resource is None or resource.get("url") != intent.resource_url:
        raise X402Error("402 challenge resource URL does not match", code="CHALLENGE_MISMATCH")
    return matches[0]


def _requirement_matches(*, intent: PaymentIntent, requirements: dict) -> bool:
    extra = requirements.get("extra") or {}
    network = requirements["network"]
    # The wire carries only ``eip155:<chain id>``; a parsed challenge has no
    # separate chain_id field, so derive it instead of trusting a second copy.
    chain_id = requirements.get("chain_id")
    if chain_id is None:
        chain_id = int(network.split(":", 1)[1])
    return (
        requirements["scheme"] == "exact"
        and network == intent.network
        and chain_id == int(intent.network.split(":", 1)[1])
        and requirements["asset"].lower() == intent.asset
        and requirements["amount"] == intent.asset_amount
        and requirements["payTo"].lower() == intent.pay_to
        and extra.get("assetTransferMethod") == "eip3009"
        and extra.get("name") == intent.asset_name
        and extra.get("version") == intent.asset_version
    )


def check_signed_payload(*, intent: PaymentIntent, payload: dict) -> dict:
    """Verify the exact document about to be transmitted is the approved one.

    The payload is constructed from trusted values by the signing component;
    this check re-reads the document and refuses any drift before it is
    persisted or sent.
    """
    accepted = payload["accepted"]
    authorization = payload["payload"]["authorization"]
    resource = payload["resource"]
    if accepted["scheme"] != "exact":
        raise X402Error("signed payload scheme mismatch", code="PAYMENT_FACT_MISMATCH")
    if accepted["network"] != intent.network:
        raise X402Error("signed payload network mismatch", code="PAYMENT_FACT_MISMATCH")
    if accepted["asset"].lower() != intent.asset:
        raise X402Error("signed payload asset mismatch", code="PAYMENT_FACT_MISMATCH")
    if accepted["amount"] != intent.asset_amount:
        raise X402Error("signed payload amount mismatch", code="PAYMENT_FACT_MISMATCH")
    if accepted["payTo"].lower() != intent.pay_to:
        raise X402Error("signed payload payTo mismatch", code="PAYMENT_FACT_MISMATCH")
    extra = accepted.get("extra") or {}
    if (
        extra.get("assetTransferMethod") != "eip3009"
        or extra.get("name") != intent.asset_name
        or extra.get("version") != intent.asset_version
    ):
        raise X402Error("signed payload EIP-712 domain mismatch", code="PAYMENT_FACT_MISMATCH")
    if resource is None or resource.get("url") != intent.resource_url:
        raise X402Error("signed payload resource mismatch", code="PAYMENT_FACT_MISMATCH")
    if authorization["to"].lower() != intent.pay_to:
        raise X402Error("authorization recipient mismatch", code="PAYMENT_FACT_MISMATCH")
    if authorization["value"] != intent.asset_amount:
        raise X402Error("authorization value mismatch", code="PAYMENT_FACT_MISMATCH")
    if _decimal_int(authorization["validBefore"]) != intent.valid_before:
        raise X402Error("authorization expiry mismatch", code="PAYMENT_FACT_MISMATCH")
    if authorization["validAfter"] != "0":
        raise X402Error("authorization validAfter must be zero", code="PAYMENT_FACT_MISMATCH")
    return payload


def check_requirements_echo(*, intent: PaymentIntent, accepted: dict) -> None:
    """The accepted requirements echoed in a PAYMENT-SIGNATURE must match."""
    extra = accepted.get("extra") or {}
    if (
        accepted["network"] != intent.network
        or accepted["asset"].lower() != intent.asset
        or accepted["amount"] != intent.asset_amount
        or accepted["payTo"].lower() != intent.pay_to
        or extra.get("name") != intent.asset_name
        or extra.get("version") != intent.asset_version
    ):
        raise X402Error("payment payload facts mismatch", code="PAYMENT_FACT_MISMATCH")


def _decimal_int(value: str) -> int:
    if type(value) is not str or not value.isdigit() or len(value) > 78:
        raise X402Error("invalid authorization timestamp", code="PAYMENT_FACT_MISMATCH")
    return int(value)
