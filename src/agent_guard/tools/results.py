"""Strict, bounded per-tool result schema for downstream outcome records.

The gateway decides ``SETTLE``/``RELEASE`` from a downstream record, so that
record is security-relevant material: it must be parsed **once**, strictly and
completely, and every field must be bound to the operation's own persisted
accept facts. Nothing here is cryptography and nothing here produces an RFC
8785 canonical form or an SM3 digest — those belong to B at A2.3.

Canonical shapes (exactly these fields, no extras, no duplicates, no non-finite
numbers). The mock downstream in :mod:`agent_guard.tools.downstream` writes
exactly these, and this module is the single place that reads them back.

``kind="order"`` (``procurement.order.create`` success)::

    {"kind": "order", "operation_id": str, "order_id": str,
     "supplier_id": str, "quote_id": str, "quote_version": str,
     "items": [{"sku": str, "quantity": int>0, "unit_price_fen": int>=0}, ...],
     "total_fen": int>=0}

``kind="notification"`` (``notification.template.send`` success)::

    {"kind": "notification", "operation_id": str, "notification_id": str,
     "template_id": str, "recipient_id": str}

``kind="read"`` (``procurement.request.read`` / ``procurement.document.read``
success; the fixed payload itself is the effect)::

    {"kind": "read", "operation_id": str, "tool_id": str}

``kind="refusal"`` (a persisted terminal refusal; never an effect)::

    {"kind": "refusal", "operation_id": str, "tool_id": str, "reason": str}

A refusal is only trusted when it binds to *this* operation's key **and** tool:
a refusal record for another tool can never release an operation that already
has an effect.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from agent_guard.contracts.execution import (
    MAX_ORDER_ITEMS,
    ExecutionError,
    ExecutionErrorCode,
    ToolId,
)

#: Hard bounds so a hostile payload cannot exhaust the parser.
MAX_RESULT_BYTES = 65536
MAX_RESULT_DEPTH = 8
MAX_RESULT_ITEMS = MAX_ORDER_ITEMS
MAX_RESULT_STR = 512

#: Resource identifiers: plain ASCII, no URL/path/control/escape material.
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
#: ``quote_version``: whole-string decimal positive integer, no leading zeros
#: (same rule as ``tools.params``/``tools.catalog``).
_VERSION_RE = re.compile(r"[1-9][0-9]{0,17}")
#: A trailing LF/CR or any control character is never a legal identifier.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

_ORDER_FIELDS = frozenset(
    {
        "kind",
        "operation_id",
        "order_id",
        "supplier_id",
        "quote_id",
        "quote_version",
        "items",
        "total_fen",
    }
)
_NOTIFICATION_FIELDS = frozenset(
    {"kind", "operation_id", "notification_id", "template_id", "recipient_id"}
)
_READ_FIELDS = frozenset({"kind", "operation_id", "tool_id"})
_REFUSAL_FIELDS = frozenset({"kind", "operation_id", "tool_id", "reason"})
_ITEM_FIELDS = frozenset({"sku", "quantity", "unit_price_fen"})

_MAX_SAFE = 2**53 - 1


@dataclass(frozen=True)
class OrderResult:
    kind: str
    operation_id: str
    order_id: str
    supplier_id: str
    quote_id: str
    quote_version: str
    items: tuple[tuple[str, int, int], ...]  # (sku, quantity, unit_price_fen)
    total_fen: int


@dataclass(frozen=True)
class NotificationResult:
    kind: str
    operation_id: str
    notification_id: str
    template_id: str
    recipient_id: str


@dataclass(frozen=True)
class ReadResult:
    kind: str
    operation_id: str
    tool_id: str


@dataclass(frozen=True)
class RefusalResult:
    kind: str
    operation_id: str
    tool_id: str
    reason: str


ResultRecord = OrderResult | NotificationResult | ReadResult | RefusalResult


def _fail(detail: str) -> ExecutionError:
    """Every result problem is the same safe answer: not usable, keep UNKNOWN."""
    return ExecutionError(ExecutionErrorCode.DOWNSTREAM_INCONSISTENT, detail)


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise _fail("result has a duplicate JSON key")
        seen[key] = value
    return seen


def _reject_constant(name: str) -> None:
    raise _fail(f"result has a non-finite number: {name}")


def _depth_ok(value: object, depth: int = 0) -> None:
    if depth > MAX_RESULT_DEPTH:
        raise _fail("result is nested too deeply")
    if isinstance(value, dict):
        for entry in value.values():
            _depth_ok(entry, depth + 1)
    elif isinstance(value, list):
        for entry in value:
            _depth_ok(entry, depth + 1)


def _str_field(name: str, value: object, *, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or value == "":
        raise _fail(f"result.{name} must be a non-empty string")
    if len(value) > MAX_RESULT_STR:
        raise _fail(f"result.{name} is too long")
    if _CONTROL_RE.search(value):
        raise _fail(f"result.{name} contains a control character")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise _fail(f"result.{name} is not a plain identifier")
    return value


def _int_field(name: str, value: object, *, minimum: int, maximum: int) -> int:
    """Exact integers only: bool/float/numeric strings are refused."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(f"result.{name} must be an integer (bool/float rejected)")
    if value < minimum or value > maximum:
        raise _fail(f"result.{name} outside [{minimum}, {maximum}]")
    return value


def parse_result(raw: bytes) -> ResultRecord:
    """Parse the persisted result payload once, strictly and completely.

    Any problem — malformed JSON, duplicate/unknown/missing fields, wrong
    types, out-of-range numbers, over-deep or over-large payloads — raises
    ``DOWNSTREAM_INCONSISTENT`` so the caller keeps the operation UNKNOWN
    instead of settling or releasing from material it cannot trust.
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise _fail("result must be bytes")
    if len(raw) > MAX_RESULT_BYTES:
        raise _fail("result is too large")
    try:
        decoded = json.loads(
            bytes(raw).decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except ExecutionError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise _fail("result is not valid JSON") from exc
    _depth_ok(decoded)
    if not isinstance(decoded, dict):
        raise _fail("result must be a JSON object")

    kind = decoded.get("kind")
    if kind == "order":
        _check_fields(decoded, _ORDER_FIELDS)
        items_raw = decoded["items"]
        if not isinstance(items_raw, list) or not items_raw:
            raise _fail("result.items must be a non-empty array")
        if len(items_raw) > MAX_RESULT_ITEMS:
            raise _fail("result.items is too large")
        items: list[tuple[str, int, int]] = []
        seen: set[str] = set()
        for index, entry in enumerate(items_raw):
            if not isinstance(entry, dict):
                raise _fail(f"result.items[{index}] must be an object")
            _check_fields(entry, _ITEM_FIELDS, prefix=f"items[{index}]")
            sku = _str_field(f"items[{index}].sku", entry["sku"], pattern=_ID_RE)
            if sku in seen:
                raise _fail("result.items has a duplicate SKU")
            seen.add(sku)
            quantity = _int_field(
                f"items[{index}].quantity",
                entry["quantity"],
                minimum=1,
                maximum=_MAX_SAFE,
            )
            price = _int_field(
                f"items[{index}].unit_price_fen",
                entry["unit_price_fen"],
                minimum=0,
                maximum=_MAX_SAFE,
            )
            items.append((sku, quantity, price))
        return OrderResult(
            kind="order",
            operation_id=_str_field("operation_id", decoded["operation_id"]),
            order_id=_str_field("order_id", decoded["order_id"], pattern=_ID_RE),
            supplier_id=_str_field("supplier_id", decoded["supplier_id"], pattern=_ID_RE),
            quote_id=_str_field("quote_id", decoded["quote_id"], pattern=_ID_RE),
            quote_version=_version_field(decoded["quote_version"]),
            items=tuple(items),
            total_fen=_int_field("total_fen", decoded["total_fen"], minimum=0, maximum=_MAX_SAFE),
        )

    if kind == "notification":
        _check_fields(decoded, _NOTIFICATION_FIELDS)
        return NotificationResult(
            kind="notification",
            operation_id=_str_field("operation_id", decoded["operation_id"]),
            notification_id=_str_field(
                "notification_id", decoded["notification_id"], pattern=_ID_RE
            ),
            template_id=_str_field("template_id", decoded["template_id"], pattern=_ID_RE),
            recipient_id=_str_field("recipient_id", decoded["recipient_id"], pattern=_ID_RE),
        )

    if kind == "read":
        _check_fields(decoded, _READ_FIELDS)
        return ReadResult(
            kind="read",
            operation_id=_str_field("operation_id", decoded["operation_id"]),
            tool_id=_str_field("tool_id", decoded["tool_id"]),
        )

    if kind == "refusal":
        _check_fields(decoded, _REFUSAL_FIELDS)
        return RefusalResult(
            kind="refusal",
            operation_id=_str_field("operation_id", decoded["operation_id"]),
            tool_id=_str_field("tool_id", decoded["tool_id"]),
            reason=_str_field("reason", decoded["reason"]),
        )

    raise _fail("result has an unknown kind")


def _version_field(value: object) -> str:
    text = _str_field("quote_version", value)
    if _CONTROL_RE.search(text):
        raise _fail("result.quote_version contains a control character")
    if _VERSION_RE.fullmatch(text) is None:
        raise _fail("result.quote_version must be a decimal positive integer string")
    return text


def _check_fields(data: dict, allowed: frozenset[str], *, prefix: str = "result") -> None:
    missing = allowed - set(data)
    if missing:
        raise _fail(f"{prefix} is missing fields: {sorted(missing)}")
    extra = set(data) - allowed
    if extra:
        raise _fail(f"{prefix} has unknown fields: {sorted(extra)}")


def bind_result(record: ResultRecord, *, operation_id: str, tool_id: str) -> str | None:
    """Bind a parsed record to the operation's own key and tool.

    Returns the effect id the record asserts (``None`` for reads and
    refusals). Anything that does not describe *this* operation and *this*
    tool raises, so a mismatched record can never settle or release it.
    """
    if record.operation_id != operation_id:
        raise _fail("result does not belong to this operation")
    if isinstance(record, RefusalResult):
        # a refusal must name the tool it refused, or it proves nothing
        if record.tool_id != tool_id:
            raise _fail("refusal record is for another tool")
        return None
    if isinstance(record, OrderResult):
        if tool_id != "procurement.order.create":
            raise _fail("order result returned for a non-order tool")
        return record.order_id
    if isinstance(record, NotificationResult):
        if tool_id != "notification.template.send":
            raise _fail("notification result returned for another tool")
        return record.notification_id
    # A read-shaped success must also be a read operation.
    if not isinstance(record, ReadResult) or tool_id not in (
        ToolId.REQUEST_READ.value,
        ToolId.DOCUMENT_READ.value,
    ):
        raise _fail("read result returned for a non-read tool")
    if record.tool_id != tool_id:
        raise _fail("read result is for another tool")
    return None
