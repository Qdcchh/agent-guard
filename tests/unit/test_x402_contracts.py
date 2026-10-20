"""Strict x402 profile, intent and wire boundaries (no network, no database).

These tests exercise the trusted-fact comparison layer that decides whether the
controlled payer may sign at all. They run everywhere (only stdlib +
``agent_guard.contracts``) and they deliberately include the tampered cases that
must never reach the chain.
"""

from __future__ import annotations

import pytest

from agent_guard.x402 import intent as intent_module
from agent_guard.x402 import wire
from agent_guard.x402.config import X402Deployment
from agent_guard.x402.contracts import (
    PaymentOffer,
    PaymentProfile,
    X402Error,
    build_intent,
    compute_intent_digest,
)

PAY_TO = "0x" + "ab" * 20
TOKEN = "0x" + "cd" * 20
PAYER = "0x" + "11" * 20
FACILITATOR_KEY = "0x" + "22" * 32
PAYER_KEY = "0x" + "33" * 32
RESOURCE_URL = "http://127.0.0.1:18080/v1/x402/resource/order-create"


def _offer(amount: str = "250000") -> PaymentOffer:
    return PaymentOffer(quote_id="quote-001", quote_version="1", asset_amount=amount)


def _profile(*, amount: str = "250000", pay_to: str = PAY_TO) -> PaymentProfile:
    return PaymentProfile(
        network="eip155:31337",
        chain_id=31337,
        asset=TOKEN,
        asset_name="USD Coin",
        asset_version="2",
        pay_to=pay_to,
        resource_url=RESOURCE_URL,
        status_url="http://127.0.0.1:18080/v1/x402/resource/order-status",
        max_timeout_seconds=3600,
        offers=(_offer(amount),),
    )


def _intent(*, amount: str = "250000", pay_to: str = PAY_TO, valid_before: int = 4_102_444_800):
    return build_intent(
        profile=_profile(amount=amount, pay_to=pay_to),
        tenant_id="tenant-001",
        task_id="task-001",
        grant_id="grant-leaf",
        root_grant_id="grant-root",
        tool_id="procurement.order.create",
        idempotency_key="purchase-1",
        quote_id="quote-001",
        quote_version="1",
        amount_fen=70_000,
        valid_before=valid_before,
    )


def _requirements(intent) -> dict:
    return wire.parse_requirements(
        {
            "scheme": "exact",
            "network": intent.network,
            "asset": intent.asset,
            "amount": intent.asset_amount,
            "payTo": intent.pay_to,
            "maxTimeoutSeconds": 3600,
            "extra": {
                "assetTransferMethod": "eip3009",
                "name": intent.asset_name,
                "version": intent.asset_version,
            },
        }
    )


def _payload(intent, *, nonce: str = "0x" + "9a" * 32) -> dict:
    document = wire.payment_payload_wire(
        resource_url=intent.resource_url,
        requirements=_requirements(intent),
        signature="0x" + "77" * 65,
        authorization={
            "from": PAYER,
            "to": intent.pay_to,
            "value": intent.asset_amount,
            "validAfter": "0",
            "validBefore": str(intent.valid_before),
            "nonce": nonce,
        },
    )
    return wire.parse_payment_payload(wire.encode_header(document))


# ------------------------------------------------------------------ profile


def test_deployment_rejects_non_loopback_and_shared_keys(monkeypatch):
    base = {
        "AG_X402_GATEWAY_DSN": "postgresql://local/test",
        "AG_X402_PAYER_KEY": PAYER_KEY,
        "AG_X402_FACILITATOR_KEY": FACILITATOR_KEY,
        "AG_X402_RPC_URL": "http://127.0.0.1:18545",
        "AG_X402_TOKEN": TOKEN,
        "AG_X402_PAY_TO": PAY_TO,
        "AG_X402_RESOURCE_URL": RESOURCE_URL,
        "AG_X402_STATUS_URL": "http://127.0.0.1:18080/v1/x402/resource/order-status",
        "AG_X402_OFFER_QUOTE_ID": "quote-001",
        "AG_X402_OFFER_QUOTE_VERSION": "1",
        "AG_X402_OFFER_ASSET_AMOUNT": "250000",
    }
    monkeypatch.setenv("AG_X402_MAX_TIMEOUT_SECONDS", "not-a-number")
    for name, value in base.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(X402Error) as exc:
        X402Deployment.from_env()
    assert exc.value.code == "CONFIG_INVALID"

    monkeypatch.setenv("AG_X402_MAX_TIMEOUT_SECONDS", "3600")
    deployment = X402Deployment.from_env()
    assert deployment.profile.asset == TOKEN
    assert deployment.profile.offers == (_offer(),)

    # A remote resource endpoint is refused even if everything else is valid.
    monkeypatch.setenv("AG_X402_RESOURCE_URL", "https://resource.example.com/x")
    with pytest.raises(X402Error) as exc:
        X402Deployment.from_env()
    assert exc.value.code == "CONFIG_NOT_LOOPBACK"
    monkeypatch.setenv("AG_X402_RESOURCE_URL", RESOURCE_URL)

    # The same key for payer and facilitator is a misconfiguration.
    monkeypatch.setenv("AG_X402_FACILITATOR_KEY", PAYER_KEY)
    with pytest.raises(X402Error):
        X402Deployment.from_env()

    # A missing required variable fails closed.
    monkeypatch.delenv("AG_X402_TOKEN")
    with pytest.raises(X402Error) as exc:
        X402Deployment.from_env()
    assert exc.value.code == "CONFIG_MISSING"


# ------------------------------------------------------------------- digest


def test_intent_digest_is_deterministic_and_covers_every_fact():
    first = _intent()
    second = _intent()
    assert first.digest == second.digest
    assert len(first.digest) == 64
    # A different trusted fact always yields a different digest.
    for changed in (
        _intent(amount="250001"),
        _intent(valid_before=4_102_444_801),
        _intent(pay_to="0x" + "ef" * 20),
    ):
        assert changed.digest != first.digest
    # The digest function is total over the declared field set.
    material = first.digest_material()
    assert compute_intent_digest(material) == first.digest
    with pytest.raises(X402Error) as exc:
        compute_intent_digest({key: material[key] for key in list(material)[:-1]})
    assert exc.value.code == "INVALID_DIGEST_FIELDS"
    with pytest.raises(X402Error):
        compute_intent_digest({**material, "extra": 1})
    # Numeric facts are JSON numbers, not strings; a string amount is a
    # different digest even though the field set is complete.
    assert compute_intent_digest({**material, "amount_fen": "70000"}) != first.digest


# --------------------------------------------------------------- challenge


def test_challenge_requires_exactly_one_exact_match():
    intent = _intent()
    requirements = _requirements(intent)
    challenge = {
        "resource": {"url": intent.resource_url},
        "accepts": [requirements],
    }
    assert (
        intent_module.check_challenge(profile=_profile(), intent=intent, challenge=challenge)
        == requirements
    )

    for mutated in (
        {**requirements, "amount": "250001"},
        {**requirements, "payTo": "0x" + "12" * 20},
        {**requirements, "network": "eip155:1"},
        {**requirements, "asset": "0x" + "34" * 20},
        {
            **requirements,
            "extra": {**requirements["extra"], "version": "1"},
        },
    ):
        with pytest.raises(X402Error) as exc:
            intent_module.check_challenge(
                profile=_profile(),
                intent=intent,
                challenge={"resource": {"url": intent.resource_url}, "accepts": [mutated]},
            )
        assert exc.value.code == "CHALLENGE_MISMATCH"

    for broken in (
        {"resource": {"url": "http://127.0.0.1:1/other"}, "accepts": [requirements]},
        {"resource": {"url": intent.resource_url}, "accepts": [requirements, requirements]},
        {"resource": {"url": intent.resource_url}, "accepts": []},
    ):
        with pytest.raises(X402Error):
            intent_module.check_challenge(profile=_profile(), intent=intent, challenge=broken)


def test_signed_payload_must_match_the_persisted_intent():
    intent = _intent()
    payload = _payload(intent)
    assert intent_module.check_signed_payload(intent=intent, payload=payload) is payload
    intent_module.check_requirements_echo(intent=intent, accepted=payload["accepted"])

    authorization = payload["payload"]["authorization"]
    for mutated in (
        {**authorization, "to": "0x" + "12" * 20},
        {**authorization, "value": "250001"},
        {**authorization, "validBefore": str(intent.valid_before + 1)},
        {**authorization, "validAfter": "1"},
    ):
        with pytest.raises(X402Error) as exc:
            intent_module.check_signed_payload(
                intent=intent,
                payload={
                    **payload,
                    "payload": {**payload["payload"], "authorization": mutated},
                },
            )
        assert exc.value.code == "PAYMENT_FACT_MISMATCH"

    for mutated in (
        {**payload["accepted"], "amount": "250001"},
        {**payload["accepted"], "payTo": "0x" + "12" * 20},
        {**payload["accepted"], "network": "eip155:1"},
    ):
        with pytest.raises(X402Error):
            intent_module.check_signed_payload(
                intent=intent, payload={**payload, "accepted": mutated}
            )
    with pytest.raises(X402Error):
        intent_module.check_signed_payload(
            intent=intent,
            payload={**payload, "resource": {"url": "http://127.0.0.1:1/other"}},
        )


# -------------------------------------------------------------------- wire


def test_wire_roundtrip_and_malformed_headers():
    intent = _intent()
    requirements = _requirements(intent)
    challenge = wire.payment_required_wire(
        resource_url=intent.resource_url, requirements=requirements, error=None
    )
    parsed = wire.parse_payment_required(wire.encode_header(challenge))
    assert parsed["accepts"] == [requirements]
    assert parsed["resource"]["url"] == intent.resource_url

    document = wire.payment_payload_wire(
        resource_url=intent.resource_url,
        requirements=requirements,
        signature="0x" + "77" * 65,
        authorization={
            "from": PAYER,
            "to": intent.pay_to,
            "value": intent.asset_amount,
            "validAfter": "0",
            "validBefore": str(intent.valid_before),
            "nonce": "0x" + "9a" * 32,
        },
    )
    reparsed = wire.parse_payment_payload(wire.encode_header(document))
    assert reparsed["payload"]["authorization"]["value"] == intent.asset_amount
    assert wire.encode_header(document) == wire.encode_header(
        wire.payment_payload_wire(
            resource_url=intent.resource_url,
            requirements=requirements,
            signature="0x" + "77" * 65,
            authorization=reparsed["payload"]["authorization"],
        )
    )

    settlement = wire.settlement_wire(
        success=True,
        transaction="0x" + "0" * 63 + "1",
        network=intent.network,
        payer=PAYER,
    )
    settled = wire.parse_payment_response(wire.encode_header(settlement))
    assert settled["success"] is True and settled["transaction"].startswith("0x")

    for bad in (
        b"not+base64!",
        wire.encode_header(b"{}"),
        wire.encode_header(b"[]"),
    ):
        with pytest.raises(X402Error):
            wire.parse_payment_required(bad)
        with pytest.raises(X402Error):
            wire.parse_payment_payload(bad)
    # A payload with an unknown member inside the authorization is rejected
    # instead of being silently ignored.
    with pytest.raises(X402Error):
        wire.parse_payment_payload(
            wire.encode_header(document.replace(b'"nonce"', b'"extra_nonce"'))
        )
