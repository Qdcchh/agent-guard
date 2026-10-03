"""Strict four-tool parameter parsing (docs/oauth-oidc-sm2-mvp.md 9.4).

Pure, database-free and side-effect free: malformed input is rejected before
anything touches a ledger, a downstream or a quote. This module parses the
*already accepted* ``canonical_params`` bytes of a trusted invocation plus its
``tool_id``/``tool_version``; it performs no signature verification and never
treats a request-supplied cost as authoritative.

Rejections follow the project rules (AGENTS.md): duplicate JSON keys, booleans
where integers belong, negative/float/out-of-range numbers, missing or empty
collections, unknown/extra fields, unknown tools or aliases, non-``1`` tool
versions and URL/path injection into resource identifiers are all refused with
an explicit :class:`ExecutionErrorCode`.
"""

from __future__ import annotations

import json
import re

from agent_guard.contracts.execution import (
    MAX_ORDER_ITEMS,
    DocumentReadParams,
    ExecutionError,
    ExecutionErrorCode,
    NotificationSendParams,
    OrderCreateParams,
    OrderItem,
    RequestReadParams,
    ToolId,
)
from agent_guard.contracts.ledger import (
    MAX_ID_LEN,
    MAX_PARAMS_BYTES,
    MAX_SAFE_INT,
    TOOL_VERSION,
)

#: Plain ASCII resource identifiers only. Anything that could become a URL, a
#: path segment, a scheme or an escape sequence is refused before lookup.
_RESOURCE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
#: ``quote_version`` is a *whole-string* decimal positive integer without
#: leading zeros: 1..18 digits, first digit 1-9. ``0``, ``01``, ``00``, ``1x``,
#: ``1@2``, ``1 2``, ``1.0``, ``1e2`` and anything over the length limit are
#: all rejected, and a trailing LF/CR is never a partial match.
_QUOTE_VERSION_RE = re.compile(r"[1-9][0-9]{0,17}")
#: Maximum nesting accepted while decoding persisted/request JSON.
_MAX_JSON_DEPTH = 8

_CONTROL_CHARS = {chr(i) for i in range(32)} | {"\x7f"}

#: Exact parameter field sets for the four tools; nothing else is accepted.
_PARAM_FIELDS: dict[ToolId, frozenset[str]] = {
    ToolId.REQUEST_READ: frozenset({"request_id"}),
    ToolId.DOCUMENT_READ: frozenset({"request_id", "document_id"}),
    ToolId.ORDER_CREATE: frozenset(
        {"request_id", "quote_id", "quote_version", "items", "delivery_id"}
    ),
    ToolId.NOTIFICATION_SEND: frozenset({"template_id", "recipient_id", "operation_id"}),
}

#: Aliases and shortenings that must never resolve to a real tool.
_TOOL_ALIASES = frozenset(
    {
        "order.create",
        "procurement.order",
        "request.read",
        "document.read",
        "notification.send",
        "notification.template",
        "procurement.order.create ",
        "Procurement.order.create",
    }
)

ToolParams = RequestReadParams | DocumentReadParams | OrderCreateParams | NotificationSendParams


# ------------------------------------------------------------------ helpers


def _fail(detail: str) -> ExecutionError:
    return ExecutionError(ExecutionErrorCode.INVALID_PARAMS, detail)


def _require_str(name: str, value: object, *, max_len: int = MAX_ID_LEN) -> str:
    if not isinstance(value, str):
        raise _fail(f"{name} must be a string")
    if value == "":
        raise _fail(f"{name} must not be empty")
    if len(value) > max_len:
        raise _fail(f"{name} exceeds {max_len} chars")
    if any(ch in _CONTROL_CHARS for ch in value):
        raise _fail(f"{name} contains control characters")
    return value


def _require_resource_id(name: str, value: object) -> str:
    """Resource ids are plain identifiers: no URL, no path, no escapes."""
    text = _require_str(name, value)
    if _RESOURCE_ID_RE.fullmatch(text) is None:
        raise _fail(f"{name} is not a plain resource identifier")
    return text


def _require_quantity(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(f"{name} must be an integer (bool/float rejected)")
    if value < 1:
        raise _fail(f"{name} must be positive")
    if value > MAX_SAFE_INT:
        raise _fail(f"{name} exceeds the safe integer range")
    return value


def _reject_constant(name: str) -> None:
    raise _fail(f"non-finite JSON number {name} is not allowed")


def _bounded_depth(value: object, depth: int = 0) -> None:
    """Reject over-deep JSON before it can exhaust the interpreter stack."""
    if depth > _MAX_JSON_DEPTH:
        raise _fail("params are nested too deeply")
    if isinstance(value, dict):
        for entry in value.values():
            _bounded_depth(entry, depth + 1)
    elif isinstance(value, list):
        for entry in value:
            _bounded_depth(entry, depth + 1)


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise _fail(f"duplicate JSON key: {key}")
        seen[key] = value
    return seen


def _decode_object(raw: bytes, *, what: str) -> dict[str, object]:
    if not isinstance(raw, (bytes, bytearray)):
        raise _fail(f"{what} must be bytes")
    if len(raw) > MAX_PARAMS_BYTES:
        raise _fail(f"{what} exceeds {MAX_PARAMS_BYTES} bytes")
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _fail(f"{what} is not valid UTF-8") from exc
    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except ExecutionError:
        raise
    except (ValueError, RecursionError, MemoryError) as exc:
        # foreseeable parse failures are a stable INVALID_PARAMS; real database
        # faults never reach this parser and are never swallowed here
        raise _fail(f"{what} is not valid JSON") from exc
    _bounded_depth(decoded)
    if not isinstance(decoded, dict):
        raise _fail(f"{what} must be a JSON object")
    return decoded


def _check_exact_fields(data: dict[str, object], allowed: frozenset[str], *, what: str) -> None:
    missing = allowed - set(data)
    if missing:
        raise _fail(f"{what} is missing fields: {sorted(missing)}")
    extra = set(data) - allowed
    if extra:
        raise _fail(f"{what} has unknown fields: {sorted(extra)}")


# ------------------------------------------------------------------ parsing


def parse_tool_id(raw: object) -> ToolId:
    """Resolve one of the four complete tool ids; aliases are never accepted."""
    text = _require_str("tool_id", raw)
    if text in _TOOL_ALIASES:
        raise ExecutionError(
            ExecutionErrorCode.UNSUPPORTED_TOOL, f"tool alias is not allowed: {text}"
        )
    try:
        return ToolId(text)
    except ValueError as exc:
        raise ExecutionError(
            ExecutionErrorCode.UNSUPPORTED_TOOL, f"unsupported tool_id: {text}"
        ) from exc


def parse_tool_version(raw: object) -> str:
    """The only tool version is the string ``1`` (never the integer 1)."""
    if isinstance(raw, bool) or not isinstance(raw, str):
        raise ExecutionError(
            ExecutionErrorCode.INVALID_PARAMS, "tool_version must be the string '1'"
        )
    if raw != TOOL_VERSION:
        raise ExecutionError(ExecutionErrorCode.INVALID_PARAMS, f"unsupported tool_version: {raw}")
    return raw


def _parse_items(raw: object) -> tuple[OrderItem, ...]:
    if not isinstance(raw, list):
        raise _fail("items must be a JSON array")
    if len(raw) == 0:
        raise _fail("items must not be empty")
    if len(raw) > MAX_ORDER_ITEMS:
        raise _fail(f"items exceeds {MAX_ORDER_ITEMS} entries")
    items: list[OrderItem] = []
    seen_skus: set[str] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise _fail(f"items[{index}] must be an object")
        _check_exact_fields(entry, frozenset({"sku", "quantity"}), what=f"items[{index}]")
        sku = _require_resource_id(f"items[{index}].sku", entry["sku"])
        if sku in seen_skus:
            raise _fail(f"duplicate SKU in items: {sku}")
        seen_skus.add(sku)
        quantity = _require_quantity(f"items[{index}].quantity", entry["quantity"])
        items.append(OrderItem(sku=sku, quantity=quantity))
    return tuple(items)


def parse_tool_params(tool_id: object, raw: bytes) -> ToolParams:
    """Parse ``canonical_params`` for ``tool_id`` under the strict 9.4 contract."""
    tool = parse_tool_id(tool_id)
    data = _decode_object(raw, what="params")
    fields = _PARAM_FIELDS[tool]
    _check_exact_fields(data, fields, what="params")

    if tool is ToolId.REQUEST_READ:
        return RequestReadParams(request_id=_require_resource_id("request_id", data["request_id"]))

    if tool is ToolId.DOCUMENT_READ:
        return DocumentReadParams(
            request_id=_require_resource_id("request_id", data["request_id"]),
            document_id=_require_resource_id("document_id", data["document_id"]),
        )

    if tool is ToolId.ORDER_CREATE:
        quote_version = _require_str("quote_version", data["quote_version"], max_len=MAX_ID_LEN)
        if _QUOTE_VERSION_RE.fullmatch(quote_version) is None:
            raise _fail("quote_version must be a decimal positive integer string")
        return OrderCreateParams(
            request_id=_require_resource_id("request_id", data["request_id"]),
            quote_id=_require_resource_id("quote_id", data["quote_id"]),
            quote_version=quote_version,
            items=_parse_items(data["items"]),
            delivery_id=_require_resource_id("delivery_id", data["delivery_id"]),
        )

    return NotificationSendParams(
        template_id=_require_resource_id("template_id", data["template_id"]),
        recipient_id=_require_resource_id("recipient_id", data["recipient_id"]),
        operation_id=_require_resource_id("operation_id", data["operation_id"]),
    )
