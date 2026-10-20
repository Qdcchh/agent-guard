"""Controlled x402 payer: real EIP-712/EIP-3009 signing through the pinned SDK.

The payer key lives only in this process, is generated once per run for a
synthetic local-chain wallet and is never exposed to a browser, a model or a
request. Signing happens **only** from the immutable trusted intent: the
requirements, authorization fields and outer payload are built from trusted
values, serialized to the pinned wire profile, re-parsed strictly and compared
again before the caller may persist or transmit them.

The EIP-3009 signing itself is the official SDK's machinery
(``build_typed_data_for_signing`` plus the SDK's ``EthAccountSigner``); no
cryptographic algorithm is reimplemented here.
"""

from __future__ import annotations

import hashlib
import secrets

from eth_account import Account
from eth_utils import to_checksum_address
from x402.mechanisms.evm.eip712 import build_typed_data_for_signing
from x402.mechanisms.evm.signers import EthAccountSigner
from x402.mechanisms.evm.types import (
    ExactEIP3009Authorization,
    TypedDataField,
)

from agent_guard.x402 import intent as intent_module
from agent_guard.x402 import wire
from agent_guard.x402.contracts import PaymentIntent, PaymentProfile, X402Error


def create_nonce() -> str:
    """Unpredictable 32-byte EIP-3009 nonce, one per persisted authorization."""
    return "0x" + secrets.token_bytes(32).hex()


class X402Payer:
    """Synthetic local-chain payer holding one in-memory key."""

    def __init__(self, private_key: str | None = None):
        key = private_key if private_key is not None else "0x" + secrets.token_bytes(32).hex()
        try:
            account = Account.from_key(key)
        except (ValueError, TypeError) as exc:
            raise X402Error("invalid synthetic payer key", code="INVALID_PAYER_KEY") from exc
        self._account = account
        self._signer = EthAccountSigner(account)

    @property
    def address(self) -> str:
        return self._account.address

    @property
    def lower_address(self) -> str:
        return self._account.address.lower()

    def create_payload(
        self,
        *,
        profile: PaymentProfile,
        intent: PaymentIntent,
        nonce: str,
    ) -> dict:
        """Build and sign the complete PAYMENT-SIGNATURE document.

        Returns ``{"document": bytes, "nonce": str, "payload_sha256": str,
        "authorization": dict}`` where ``document`` is the exact canonical
        wire bytes that must be persisted before transmission.
        """
        if profile.network != intent.network or profile.chain_id != intent.chain_id:
            raise X402Error("profile and intent networks differ", code="PAYMENT_FACT_MISMATCH")
        # web3.py inside the facilitator SDK only accepts checksummed EIP-55
        # addresses; the address case is not part of the EIP-712/3009 bytes.
        authorization = ExactEIP3009Authorization(
            from_address=self._account.address,
            to=to_checksum_address(intent.pay_to),
            value=intent.asset_amount,
            valid_after="0",
            valid_before=str(intent.valid_before),
            nonce=nonce,
        )
        domain, types, primary_type, message = build_typed_data_for_signing(
            authorization,
            intent.chain_id,
            intent.asset,
            intent.asset_name,
            intent.asset_version,
        )
        typed_fields: dict[str, list[TypedDataField]] = {
            type_name: [TypedDataField(name=f["name"], type=f["type"]) for f in fields]
            for type_name, fields in types.items()
        }
        signature = self._signer.sign_typed_data(domain, typed_fields, primary_type, message)
        if type(signature) is not bytes or len(signature) != 65:
            raise X402Error("payer produced an unusable signature", code="INVALID_SIGNATURE")

        requirements = {
            "scheme": "exact",
            "network": intent.network,
            "asset": intent.asset,
            "amount": intent.asset_amount,
            "payTo": intent.pay_to,
            "maxTimeoutSeconds": profile.max_timeout_seconds,
            "extra": {
                "assetTransferMethod": "eip3009",
                "name": intent.asset_name,
                "version": intent.asset_version,
            },
        }
        document = wire.payment_payload_wire(
            resource_url=intent.resource_url,
            requirements=requirements,
            signature="0x" + signature.hex(),
            authorization={
                "from": self._account.address,
                "to": authorization.to,
                "value": intent.asset_amount,
                "validAfter": "0",
                "validBefore": str(intent.valid_before),
                "nonce": nonce,
            },
        )
        # The exact bytes that will be transmitted are re-parsed strictly and
        # compared against the trusted intent before anything is persisted.
        parsed = wire.parse_payment_payload(wire.encode_header(document))
        intent_module.check_signed_payload(intent=intent, payload=parsed)
        return {
            "document": document,
            "nonce": nonce,
            "payload_sha256": hashlib.sha256(document).hexdigest(),
            "authorization": parsed["payload"]["authorization"],
        }
