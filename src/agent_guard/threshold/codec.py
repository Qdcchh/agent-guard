"""Exact, cross-language codec for the V2 threshold approval action.

The bytes produced here are the *same* bytes the pinned Rust prototype produces
in ``ApprovalActionV2::message``: the domain separator followed by the
deterministic JSON encoding of the fixed struct in declaration order. This
module builds the encoding from the semantic fields (never from a serialized
fixture's incidental key order), so both implementations can be compared on
independent vectors.

The encoding is deliberately not the repository's GM-MVP-1/JWS encoding and is
versioned by its own domain separator.
"""

from __future__ import annotations

import hashlib
import json
import re

from agent_guard.contracts.encoding import (
    EncodingError,
    JsonValue,
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.threshold.contracts import (
    ACTION_DOMAIN,
    ACTION_DOMAIN_V3,
    ACTION_VERSION,
    ACTION_VERSION_V3,
    COSM2_DOMAIN,
    COSM2_PROFILE,
    CURRENCY,
    MAX_ACTION_ITEMS,
    MAX_ENVELOPE_BYTES,
    MAX_HEADER_BYTES,
    MAX_IDENTIFIER,
    MAX_PATH_IDS,
    MAX_VERSION,
    PROFILE,
    TOOL_ID,
    TOOL_VERSION,
    ThresholdApprovalError,
)

#: Wire field order. This is the declaration order of the Rust struct and the
#: only accepted order for the canonical envelope.
ACTION_FIELD_ORDER = (
    "version",
    "tenant_id",
    "task_id",
    "root_grant_id",
    "grant_id",
    "path_grant_ids",
    "holder_client_id",
    "holder_kid",
    "audience",
    "tool_id",
    "tool_version",
    "currency",
    "policy_version",
    "key_epoch",
    "action_id",
    "idempotency_key",
    "request_id",
    "quote_id",
    "quote_version",
    "items",
    "delivery_id",
    "amount_fen",
    "canonical_params_sha256",
    "expires_at",
)

#: V3 appends the x402 payment-intent digest to the frozen V2 field order.
ACTION_FIELD_ORDER_V3 = ACTION_FIELD_ORDER + ("payment_digest",)

_ENVELOPE_FIELDS = {"profile", "action", "signature"}
_ITEM_FIELDS = {"sku", "quantity"}
_ID_CHARS = re.compile(r"[A-Za-z0-9._:@\-]+\Z", re.ASCII)
_QUOTE_VERSION = re.compile(r"[1-9][0-9]{0,17}\Z", re.ASCII)
_HEX64 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def _schema(detail: str) -> ThresholdApprovalError:
    return ThresholdApprovalError(detail, code="INVALID_SCHEMA")


def _identifier(name: str, value: object) -> str:
    if type(value) is not str or not 1 <= len(value) <= MAX_IDENTIFIER:
        raise _schema(f"invalid {name}")
    if _ID_CHARS.fullmatch(value) is None:
        raise _schema(f"invalid {name}")
    return value


def _bounded_int(name: str, value: object, *, minimum: int = 1, maximum: int = MAX_VERSION) -> int:
    if type(value) is not int or isinstance(value, bool) or not minimum <= value <= maximum:
        raise _schema(f"invalid {name}")
    return value


def _serialize(value: JsonValue) -> bytes:
    """Deterministic JSON identical to serde_json for the restricted values."""
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise _schema("action cannot be encoded") from exc


def compute_params_digest(
    *,
    request_id: str,
    quote_id: str,
    quote_version: str,
    items: object,
    delivery_id: str,
) -> str:
    """SHA-256 over the fixed order parameter structure in Rust field order."""
    rows = []
    for entry in items:
        if isinstance(entry, (tuple, list)) and len(entry) == 2:
            sku, quantity = entry
        elif isinstance(entry, dict):
            sku, quantity = entry["sku"], entry["quantity"]
        else:
            raise _schema("invalid order item entry")
        rows.append({"sku": sku, "quantity": quantity})
    params = {
        "request_id": request_id,
        "quote_id": quote_id,
        "quote_version": quote_version,
        "items": rows,
        "delivery_id": delivery_id,
    }
    return hashlib.sha256(_serialize(params)).hexdigest()


def parse_action(value: object) -> dict:
    """Validate one V2 action and return it in exact wire field order."""
    if type(value) is not dict or set(value) != set(ACTION_FIELD_ORDER):
        raise _schema("exact threshold action fields required")
    if value["version"] != ACTION_VERSION or type(value["version"]) is not int:
        raise _schema("unsupported threshold action version")
    tenant_id = _identifier("tenant_id", value["tenant_id"])
    task_id = _identifier("task_id", value["task_id"])
    root_grant_id = _identifier("root_grant_id", value["root_grant_id"])
    grant_id = _identifier("grant_id", value["grant_id"])
    holder_client_id = _identifier("holder_client_id", value["holder_client_id"])
    # Holder kids follow the DID URL fragment form and may carry '#'.
    holder_kid = value["holder_kid"]
    if (
        type(holder_kid) is not str
        or not 1 <= len(holder_kid) <= 256
        or any(not 0x21 <= ord(c) <= 0x7E for c in holder_kid)
    ):
        raise _schema("invalid holder_kid")
    action_id = _identifier("action_id", value["action_id"])
    idempotency_key = _identifier("idempotency_key", value["idempotency_key"])
    request_id = _identifier("request_id", value["request_id"])
    quote_id = _identifier("quote_id", value["quote_id"])
    delivery_id = _identifier("delivery_id", value["delivery_id"])

    raw_path = value["path_grant_ids"]
    if type(raw_path) is not list or not 1 <= len(raw_path) <= MAX_PATH_IDS:
        raise _schema("invalid authorization path")
    path_grant_ids = [_identifier("path_grant_ids", entry) for entry in raw_path]
    if len(set(path_grant_ids)) != len(path_grant_ids):
        raise _schema("duplicate authorization path node")
    if path_grant_ids[0] != root_grant_id or path_grant_ids[-1] != grant_id:
        raise _schema("authorization path does not match root/leaf")

    audience = value["audience"]
    if (
        type(audience) is not str
        or not 1 <= len(audience) <= MAX_IDENTIFIER
        or any(not 0x21 <= ord(c) <= 0x7E for c in audience)
    ):
        raise _schema("invalid audience")
    if value["tool_id"] != TOOL_ID or value["tool_version"] != TOOL_VERSION:
        raise _schema("unsupported tool or tool version")
    if value["currency"] != CURRENCY:
        raise _schema("unsupported currency")

    policy_version = _bounded_int("policy_version", value["policy_version"])
    key_epoch = _bounded_int("key_epoch", value["key_epoch"])
    amount_fen = _bounded_int("amount_fen", value["amount_fen"], minimum=0)
    expires_at = _bounded_int("expires_at", value["expires_at"])

    quote_version = value["quote_version"]
    if type(quote_version) is not str or _QUOTE_VERSION.fullmatch(quote_version) is None:
        raise _schema("invalid quote version")

    raw_items = value["items"]
    if type(raw_items) is not list or not 1 <= len(raw_items) <= MAX_ACTION_ITEMS:
        raise _schema("invalid order items")
    items = []
    seen: set[str] = set()
    for entry in raw_items:
        if type(entry) is not dict or set(entry) != _ITEM_FIELDS:
            raise _schema("exact order item fields required")
        sku = _identifier("sku", entry["sku"])
        if sku in seen:
            raise _schema("duplicate sku")
        seen.add(sku)
        items.append({"sku": sku, "quantity": _bounded_int("quantity", entry["quantity"])})

    digest = value["canonical_params_sha256"]
    if type(digest) is not str or _HEX64.fullmatch(digest) is None:
        raise _schema("invalid parameter digest")
    computed = compute_params_digest(
        request_id=request_id,
        quote_id=quote_id,
        quote_version=quote_version,
        items=items,
        delivery_id=delivery_id,
    )
    if digest != computed:
        raise _schema("parameter digest does not match the action")

    return {
        "version": ACTION_VERSION,
        "tenant_id": tenant_id,
        "task_id": task_id,
        "root_grant_id": root_grant_id,
        "grant_id": grant_id,
        "path_grant_ids": path_grant_ids,
        "holder_client_id": holder_client_id,
        "holder_kid": holder_kid,
        "audience": audience,
        "tool_id": TOOL_ID,
        "tool_version": TOOL_VERSION,
        "currency": CURRENCY,
        "policy_version": policy_version,
        "key_epoch": key_epoch,
        "action_id": action_id,
        "idempotency_key": idempotency_key,
        "request_id": request_id,
        "quote_id": quote_id,
        "quote_version": quote_version,
        "items": items,
        "delivery_id": delivery_id,
        "amount_fen": amount_fen,
        "canonical_params_sha256": digest,
        "expires_at": expires_at,
    }


def parse_action_v3(value: object) -> dict:
    """Validate one V3 action (V2 fields plus the payment digest) in wire order."""
    if type(value) is not dict or set(value) != set(ACTION_FIELD_ORDER_V3):
        raise _schema("exact threshold action fields required")
    if value["version"] != ACTION_VERSION_V3 or type(value["version"]) is not int:
        raise _schema("unsupported threshold action version")
    digest = value["payment_digest"]
    if type(digest) is not str or _HEX64.fullmatch(digest) is None:
        raise _schema("invalid payment digest")
    base = {name: value[name] for name in ACTION_FIELD_ORDER}
    base["version"] = ACTION_VERSION
    parsed = parse_action(base)
    parsed["version"] = ACTION_VERSION_V3
    parsed["payment_digest"] = digest
    return {name: parsed[name] for name in ACTION_FIELD_ORDER_V3}


def action_message(action: dict) -> bytes:
    """Exact cross-language message bytes of one parsed action (V2 or V3)."""
    if type(action) is not dict:
        raise _schema("exact threshold action fields required")
    fields = set(action)
    if fields == set(ACTION_FIELD_ORDER):
        order, domain = ACTION_FIELD_ORDER, ACTION_DOMAIN
    elif fields == set(ACTION_FIELD_ORDER_V3):
        if action["version"] != ACTION_VERSION_V3 or type(action["version"]) is not int:
            raise _schema("unsupported threshold action version")
        order, domain = ACTION_FIELD_ORDER_V3, ACTION_DOMAIN_V3
    else:
        raise _schema("exact threshold action fields required")
    ordered = {name: action[name] for name in order}
    return domain + _serialize(ordered)


def cosm2_message(action: dict) -> bytes:
    """COSM2 signs strictly validated V3 fields under its own domain."""
    return COSM2_DOMAIN + _serialize(parse_action_v3(action))


def build_envelope(action: dict, signature: bytes, *, profile: str = PROFILE) -> bytes:
    """Canonical detached envelope for tests/demo; never used to trust a call."""
    if type(action) is not dict:
        raise _schema("exact threshold action fields required")
    fields = set(action)
    if fields == set(ACTION_FIELD_ORDER):
        order = ACTION_FIELD_ORDER
    elif (
        fields == set(ACTION_FIELD_ORDER_V3)
        and action["version"] == ACTION_VERSION_V3
        and type(action["version"]) is int
    ):
        order = ACTION_FIELD_ORDER_V3
    else:
        raise _schema("exact threshold action fields required")
    if type(signature) is not bytes or len(signature) != 64:
        raise _schema("invalid threshold signature material")
    if profile not in (PROFILE, COSM2_PROFILE):
        raise _schema("unsupported approval profile")
    if profile == COSM2_PROFILE:
        parse_action_v3(action)
    ordered = {name: action[name] for name in order}
    return canonical_json_bytes(
        {"profile": profile, "action": ordered, "signature": b64url_encode(signature)}
    )


def encode_header(envelope: bytes) -> bytes:
    if type(envelope) is not bytes or not 1 <= len(envelope) <= MAX_ENVELOPE_BYTES:
        raise _schema("invalid approval envelope")
    return b64url_encode(envelope).encode("ascii")


def decode_header(header: bytes) -> bytes:
    """Strictly decode one ``ag-approval`` header value to canonical envelope bytes."""
    if type(header) is not bytes or not 1 <= len(header) <= MAX_HEADER_BYTES:
        raise _schema("invalid approval header")
    try:
        text = header.decode("ascii")
        return b64url_decode(text)
    except (UnicodeError, EncodingError, ValueError) as exc:
        raise _schema("invalid approval header encoding") from exc


def parse_envelope(envelope: bytes, *, profile: str = PROFILE) -> tuple[dict, bytes]:
    """Parse the canonical envelope; returns ``(action, signature_bytes)``."""
    if type(envelope) is not bytes or not 1 <= len(envelope) <= MAX_ENVELOPE_BYTES:
        raise _schema("invalid approval envelope")
    try:
        value = load_strict_json(envelope)
    except EncodingError as exc:
        raise _schema("invalid approval envelope JSON") from exc
    if profile not in (PROFILE, COSM2_PROFILE):
        raise _schema("unsupported approval profile")
    if type(value) is not dict or set(value) != _ENVELOPE_FIELDS or value["profile"] != profile:
        raise _schema("exact approval envelope fields required")
    raw_action = value["action"]
    if profile == COSM2_PROFILE:
        action = parse_action_v3(raw_action)
    elif type(raw_action) is dict and raw_action.get("version") == ACTION_VERSION_V3:
        action = parse_action_v3(raw_action)
    else:
        action = parse_action(raw_action)
    signature = value["signature"]
    if type(signature) is not str:
        raise _schema("invalid threshold signature")
    try:
        raw_signature = b64url_decode(signature)
    except (EncodingError, ValueError) as exc:
        raise _schema("invalid threshold signature") from exc
    if len(raw_signature) != 64:
        raise _schema("invalid threshold signature length")
    try:
        canonical = canonical_json_bytes(value)
    except EncodingError as exc:
        raise _schema("approval envelope is not canonical") from exc
    if canonical != envelope:
        raise _schema("approval envelope is not canonical")
    return action, raw_signature
