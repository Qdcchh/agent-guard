"""Strict, bounded parsing and canonical serialization of x402 v2 wire objects.

Only the pinned profile is accepted: ``x402Version = 2``, scheme ``exact`` on
an ``eip155`` network and the ``eip3009`` asset transfer method. Every parser
in this module is strict about the complete field set: duplicate JSON members,
unknown fields (including extension objects), booleans or floats where integers
are required, negative values, numbers outside the canonical decimal bounds and
non-canonical base64 are all rejected. Nothing in this module signs, sends or
trusts anything by itself.
"""

from __future__ import annotations

import base64
import binascii
import json

from agent_guard.contracts.encoding import EncodingError, load_strict_json
from agent_guard.x402.contracts import (
    ADDRESS_PATTERN,
    DECIMAL_PATTERN,
    DIGEST_PATTERN,
    MAX_HEADER_BYTES,
    MAX_IDENTIFIER,
    MAX_REQUIREMENTS,
    MAX_RESOURCE_DESCRIPTION,
    NETWORK_PATTERN,
    NONCE_PATTERN,
    SCHEME,
    TRANSFER_METHOD,
    WIRE_VERSION,
    X402Error,
)

_REQUIREMENT_FIELDS = {
    "scheme",
    "network",
    "asset",
    "amount",
    "payTo",
    "maxTimeoutSeconds",
    "extra",
}
_EXTRA_FIELDS = {"assetTransferMethod", "name", "version"}
_RESOURCE_FIELDS = {"url", "description", "mimeType"}
_REQUIRED_FIELDS = {"x402Version", "accepts", "error", "resource", "extensions"}
_PAYLOAD_FIELDS = {"x402Version", "resource", "accepted", "payload", "extensions"}
_INNER_PAYLOAD_FIELDS = {"signature", "authorization"}
_AUTHORIZATION_FIELDS = {"from", "to", "value", "validAfter", "validBefore", "nonce"}
_SETTLEMENT_FIELDS = {"success", "errorReason", "transaction", "network", "payer"}
_HEX = frozenset("0123456789abcdefABCDEF")
_LOWER_HEX = frozenset("0123456789abcdef")


def _error(detail: str, code: str = "INVALID_PAYMENT_WIRE") -> X402Error:
    return X402Error(detail, code=code)


def _string(name: str, value: object, *, upper: int = MAX_IDENTIFIER) -> str:
    if type(value) is not str or not 1 <= len(value) <= upper:
        raise _error(f"invalid {name}")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise _error(f"invalid {name}")
    return value


def _decimal(name: str, value: object) -> str:
    if type(value) is not str or DECIMAL_PATTERN.fullmatch(value) is None:
        raise _error(f"invalid {name}")
    return value


def _timestamp(name: str, value: object) -> str:
    if type(value) is not str or not value.isdigit() or not 1 <= len(value) <= 78:
        raise _error(f"invalid {name}")
    if len(value) > 1 and value.startswith("0"):
        raise _error(f"non-canonical {name}")
    return value


def _address(name: str, value: object) -> str:
    if type(value) is not str or ADDRESS_PATTERN.fullmatch(value) is None:
        raise _error(f"invalid {name}")
    return value


def _hex_field(name: str, value: object, length: int) -> str:
    if type(value) is not str or len(value) != length or not value.startswith("0x"):
        raise _error(f"invalid {name}")
    if any(c not in _HEX for c in value[2:]):
        raise _error(f"invalid {name}")
    return value


def _int(name: str, value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or isinstance(value, bool) or not minimum <= value <= maximum:
        raise _error(f"invalid {name}")
    return value


def _exact(value: object, fields: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise _error(f"exact {label} fields required")
    return value


def decode_header(header: bytes, *, label: str) -> bytes:
    """Decode one canonical base64 header value; never echoes raw bytes."""
    if type(header) is not bytes or not 1 <= len(header) <= MAX_HEADER_BYTES:
        raise _error(f"invalid {label} header")
    try:
        text = header.decode("ascii")
    except UnicodeDecodeError as exc:
        raise _error(f"invalid {label} header encoding") from exc
    if any(c.isspace() for c in text):
        raise _error(f"invalid {label} header encoding")
    padded = text + "=" * (-len(text) % 4)
    try:
        raw = base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _error(f"invalid {label} header encoding") from exc
    if base64.b64encode(raw).decode("ascii").rstrip("=") != text.rstrip("="):
        raise _error(f"non-canonical {label} header encoding")
    if not 1 <= len(raw) <= MAX_HEADER_BYTES:
        raise _error(f"invalid {label} header")
    return raw


def encode_header(raw: bytes) -> bytes:
    """Canonical standard-base64 header value used by this fixed profile."""
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_HEADER_BYTES:
        raise _error("header payload out of bounds")
    return base64.b64encode(raw)


def _json_object(raw: bytes, label: str) -> dict:
    try:
        value = load_strict_json(raw)
    except EncodingError as exc:
        raise _error(f"invalid {label} JSON") from exc
    if type(value) is not dict:
        raise _error(f"invalid {label} object")
    return value


# --------------------------------------------------------------- 402 challenge


def parse_payment_required(header: bytes) -> dict:
    """Parse one PAYMENT-REQUIRED challenge into validated plain facts."""
    raw = decode_header(header, label="PAYMENT-REQUIRED")
    value = _exact(_json_object(raw, "PAYMENT-REQUIRED"), _REQUIRED_FIELDS, "PAYMENT-REQUIRED")
    if value["x402Version"] != WIRE_VERSION or type(value["x402Version"]) is not int:
        raise _error("unsupported x402 version")
    if value["extensions"] is not None:
        raise _error("unsupported x402 extensions", code="UNSUPPORTED_EXTENSION")
    error = value["error"]
    if error is not None:
        error = _string("error", error, upper=512)
    resource = None if value["resource"] is None else parse_resource(value["resource"])
    accepts = value["accepts"]
    if type(accepts) is not list or not 1 <= len(accepts) <= MAX_REQUIREMENTS:
        raise _error("invalid accepts list")
    offers = [parse_requirements(entry) for entry in accepts]
    return {"error": error, "resource": resource, "accepts": offers}


def parse_resource(value: object) -> dict:
    if type(value) is not dict or set(value) - _RESOURCE_FIELDS or "url" not in value:
        raise _error("exact resource fields required")
    url = _string("resource url", value["url"], upper=512)
    description = value.get("description")
    if description is not None:
        description = _string("resource description", description, upper=MAX_RESOURCE_DESCRIPTION)
    mime = value.get("mimeType")
    if mime is not None:
        mime = _string("resource mimeType", mime, upper=128)
    return {"url": url, "description": description, "mimeType": mime}


def parse_requirements(value: object) -> dict:
    if type(value) is not dict:
        raise _error("exact payment requirements fields required")
    if set(value) not in (set(_REQUIREMENT_FIELDS), set(_REQUIREMENT_FIELDS) - {"extra"}):
        raise _error("exact payment requirements fields required")
    if value.get("scheme") != SCHEME:
        raise _error("unsupported payment scheme", code="UNSUPPORTED_SCHEME")
    network = value["network"]
    if type(network) is not str or NETWORK_PATTERN.fullmatch(network) is None:
        raise _error("invalid payment network")
    asset = _address("asset", value["asset"])
    amount = _decimal("amount", value["amount"])
    pay_to = _address("payTo", value["payTo"])
    timeout = _int("maxTimeoutSeconds", value["maxTimeoutSeconds"], minimum=1, maximum=86400)
    extra = value.get("extra", {})
    extra = _parse_extra(extra)
    return {
        "scheme": SCHEME,
        "network": network,
        "asset": asset,
        "amount": amount,
        "payTo": pay_to,
        "maxTimeoutSeconds": timeout,
        "extra": extra,
    }


def _parse_extra(value: object) -> dict:
    if type(value) is not dict or set(value) - _EXTRA_FIELDS:
        raise _error("exact payment extra fields required")
    method = value.get("assetTransferMethod", TRANSFER_METHOD)
    if method != TRANSFER_METHOD:
        raise _error("unsupported asset transfer method", code="UNSUPPORTED_TRANSFER_METHOD")
    name = value.get("name")
    version = value.get("version")
    if name is None or version is None:
        raise _error("EIP-712 domain name and version are required")
    return {
        "assetTransferMethod": TRANSFER_METHOD,
        "name": _string("domain name", name),
        "version": _string("domain version", version, upper=32),
    }


# ------------------------------------------------------------ payment payload


def parse_payment_payload(header: bytes) -> dict:
    """Parse one PAYMENT-SIGNATURE header into validated plain facts."""
    raw = decode_header(header, label="PAYMENT-SIGNATURE")
    value = _exact(_json_object(raw, "PAYMENT-SIGNATURE"), _PAYLOAD_FIELDS, "PAYMENT-SIGNATURE")
    if value["x402Version"] != WIRE_VERSION or type(value["x402Version"]) is not int:
        raise _error("unsupported x402 version")
    if value["extensions"] is not None:
        raise _error("unsupported x402 extensions", code="UNSUPPORTED_EXTENSION")
    resource = None if value["resource"] is None else parse_resource(value["resource"])
    accepted = parse_requirements(value["accepted"])
    inner = _exact(value["payload"], _INNER_PAYLOAD_FIELDS, "payment payload")
    signature = _hex_field("signature", inner["signature"], 132)
    if not signature.startswith("0x"):
        raise _error("invalid signature")
    authorization = _exact(inner["authorization"], _AUTHORIZATION_FIELDS, "authorization fields")
    nonce = authorization["nonce"]
    if type(nonce) is not str or NONCE_PATTERN.fullmatch(nonce) is None:
        raise _error("invalid nonce")
    return {
        "resource": resource,
        "accepted": accepted,
        "payload": {
            "signature": signature,
            "authorization": {
                "from": _address("from", authorization["from"]),
                "to": _address("to", authorization["to"]),
                "value": _decimal("value", authorization["value"]),
                "validAfter": _timestamp("validAfter", authorization["validAfter"]),
                "validBefore": _timestamp("validBefore", authorization["validBefore"]),
                "nonce": nonce,
            },
        },
    }


def parse_payment_response(header: bytes) -> dict:
    """Parse one PAYMENT-RESPONSE header into validated plain facts."""
    raw = decode_header(header, label="PAYMENT-RESPONSE")
    value = _exact(_json_object(raw, "PAYMENT-RESPONSE"), _SETTLEMENT_FIELDS, "PAYMENT-RESPONSE")
    success = value["success"]
    if type(success) is not bool:
        raise _error("invalid settlement success flag")
    transaction = value["transaction"]
    if type(transaction) is not str or not transaction.startswith("0x"):
        raise _error("invalid settlement transaction")
    if transaction != "":
        transaction = _hex_field("transaction", transaction, 66)
    network = value["network"]
    if type(network) is not str or NETWORK_PATTERN.fullmatch(network) is None:
        raise _error("invalid settlement network")
    payer = value["payer"]
    if payer is not None:
        payer = _address("payer", payer)
    reason = value["errorReason"]
    if reason is not None:
        reason = _string("errorReason", reason)
    return {
        "success": success,
        "errorReason": reason,
        "transaction": transaction,
        "network": network,
        "payer": payer,
    }


# ---------------------------------------------------------------- serializers


def requirements_wire(
    *,
    network: str,
    asset: str,
    amount: str,
    pay_to: str,
    max_timeout_seconds: int,
    asset_name: str,
    asset_version: str,
) -> bytes:
    """Canonical wire bytes for one trusted requirement object."""
    return _canonical_json(
        {
            "scheme": SCHEME,
            "network": network,
            "asset": asset,
            "amount": amount,
            "payTo": pay_to,
            "maxTimeoutSeconds": max_timeout_seconds,
            "extra": {
                "assetTransferMethod": TRANSFER_METHOD,
                "name": asset_name,
                "version": asset_version,
            },
        }
    )


def payment_required_wire(*, resource_url: str, requirements: dict, error: str | None) -> bytes:
    document = {
        "x402Version": WIRE_VERSION,
        "resource": {"url": resource_url},
        "accepts": [requirements],
        "error": error,
        "extensions": None,
    }
    return _canonical_json(document)


def payment_payload_wire(
    *,
    resource_url: str,
    requirements: dict,
    signature: str,
    authorization: dict,
) -> bytes:
    """Canonical PAYMENT-SIGNATURE document for the fixed local profile."""
    return _canonical_json(
        {
            "x402Version": WIRE_VERSION,
            "resource": {"url": resource_url},
            "accepted": requirements,
            "payload": {"signature": signature, "authorization": authorization},
            "extensions": None,
        }
    )


def settlement_wire(*, success: bool, transaction: str, network: str, payer: str | None) -> bytes:
    document = {
        "success": success,
        "errorReason": None if success else "settlement_failed",
        "transaction": transaction,
        "network": network,
        "payer": payer,
    }
    return _canonical_json(document)


def _canonical_json(document: dict) -> bytes:
    try:
        return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:  # pragma: no cover - defensive
        raise _error("wire object cannot be encoded") from exc


def digest_text(value: str) -> str:
    if type(value) is not str or DIGEST_PATTERN.fullmatch(value) is None:
        raise _error("invalid digest")
    return value
