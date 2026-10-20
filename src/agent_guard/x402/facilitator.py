"""Local facilitator wrapping the pinned official x402 SDK's EVM exact scheme.

The facilitator verifies the EIP-3009 authorization against the real local
chain (signature recovery, balance and a full ``transferWithAuthorization``
simulation) and settles by broadcasting the real token transaction and waiting
for its receipt and Transfer event. All of that is the SDK's implementation;
this module only maps between the gateway's strictly parsed plain dictionaries
and the SDK's typed models, and never trusts or echoes a remote
``invalid_message``.
"""

from __future__ import annotations

from x402 import x402FacilitatorSync
from x402.mechanisms.evm import FacilitatorWeb3Signer
from x402.mechanisms.evm.exact import register_exact_evm_facilitator
from x402.schemas import PaymentPayload, PaymentRequirements

from agent_guard.x402.contracts import X402Error

MAX_ERROR_MESSAGE = 512


class LocalFacilitator:
    """Verification and settlement over one local EVM service."""

    def __init__(
        self,
        *,
        rpc_url: str,
        private_key: str,
        network: str,
        confirmation_timeout_seconds: float = 30.0,
    ):
        self._signer = FacilitatorWeb3Signer(
            private_key=private_key,
            rpc_url=rpc_url,
            confirmation_timeout_seconds=confirmation_timeout_seconds,
        )
        self._facilitator = x402FacilitatorSync()
        register_exact_evm_facilitator(self._facilitator, self._signer, networks=[network])

    @property
    def address(self) -> str:
        return self._signer.address

    def verify(self, *, payload: dict, requirements: dict) -> dict:
        """Run the SDK's real verify; returns a bounded plain result."""
        sdk_payload = _payload_model(payload)
        sdk_requirements = _requirements_model(requirements)
        try:
            result = self._facilitator.verify(sdk_payload, sdk_requirements)
        except X402Error:
            raise
        except Exception:  # noqa: BLE001 - a broken facilitator is not a valid payment
            return {"is_valid": False, "invalid_reason": "FACILITATOR_UNAVAILABLE", "payer": None}
        return {
            "is_valid": bool(result.is_valid),
            "invalid_reason": _bounded(result.invalid_reason),
            "payer": _bounded(result.payer, 64),
        }

    def settle(self, *, payload: dict, requirements: dict) -> dict:
        """Run the SDK's real settlement; returns a bounded plain result."""
        sdk_payload = _payload_model(payload)
        sdk_requirements = _requirements_model(requirements)
        try:
            result = self._facilitator.settle(sdk_payload, sdk_requirements)
        except X402Error:
            raise
        except Exception:  # noqa: BLE001 - broadcast may have happened
            return {
                "success": False,
                "error_reason": "SETTLEMENT_PENDING",
                "transaction": "",
                "network": sdk_requirements.network,
                "payer": None,
            }
        return {
            "success": bool(result.success),
            "error_reason": _bounded(result.error_reason),
            "transaction": _bounded(result.transaction, 68),
            "network": _bounded(str(result.network), 64),
            "payer": _bounded(result.payer, 64),
        }


def _payload_model(payload: dict) -> PaymentPayload:
    document = {
        "x402Version": 2,
        "payload": payload["payload"],
        "accepted": _requirements_dict(payload["accepted"]),
    }
    if payload.get("resource") is not None:
        document["resource"] = {
            key: value
            for key, value in payload["resource"].items()
            if value is not None and key in ("url", "description", "mimeType")
        }
    try:
        return PaymentPayload.model_validate(document)
    except Exception as exc:  # noqa: BLE001 - pydantic errors never leak
        raise X402Error("invalid payment payload model", code="INVALID_PAYMENT_MODEL") from exc


def _requirements_model(requirements: dict) -> PaymentRequirements:
    try:
        return PaymentRequirements.model_validate(_requirements_dict(requirements))
    except Exception as exc:  # noqa: BLE001
        raise X402Error("invalid payment requirements model", code="INVALID_PAYMENT_MODEL") from exc


def _requirements_dict(requirements: dict) -> dict:
    return {
        "scheme": requirements["scheme"],
        "network": requirements["network"],
        "asset": requirements["asset"],
        "amount": requirements["amount"],
        "payTo": requirements["payTo"],
        "maxTimeoutSeconds": requirements["maxTimeoutSeconds"],
        "extra": dict(requirements.get("extra") or {}),
    }


def _bounded(value, limit: int = MAX_ERROR_MESSAGE) -> str | None:
    if value is None:
        return None
    text = str(value)
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in text):
        return "UNPRINTABLE"
    return text[:limit]
