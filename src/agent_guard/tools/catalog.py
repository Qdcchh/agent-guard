"""Trusted synthetic resources and quote resolution (A2.1 core).

The catalog is seeded only by trusted initialization; it is never uploaded by a
request and never priced from caller input. It is the single authority for

* which procurement requests/documents/deliveries exist and to which tenant and
  task they belong,
* which quote version a supplier offers, with per-SKU unit prices and offered
  quantities,
* which notification templates and recipients are approved.

``build_order_snapshot`` computes the CNY-integer-fen total from a *fixed*
quote version and the requested quantities and returns the complete immutable
:class:`TrustedQuoteSnapshot` that the gateway stores at first accept and that
the downstream validates afterwards. Later edits or deletions of a quote can
never re-price an already accepted operation.

Nothing here is B's cryptography or B's canonical encoding: snapshot bytes are
plain UTF-8 JSON chosen for structural comparison and immutability.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Iterable

from agent_guard.contracts.execution import (
    MAX_ORDER_ITEMS,
    ExecutionError,
    ExecutionErrorCode,
    QuoteItem,
    TrustedQuoteSnapshot,
)
from agent_guard.contracts.ledger import MAX_SAFE_INT

CURRENCY = "CNY"


@dataclass(frozen=True)
class CatalogRequest:
    request_id: str
    tenant_id: str
    task_id: str
    status: str = "APPROVED"


@dataclass(frozen=True)
class CatalogDocument:
    document_id: str
    request_id: str
    body: str = "synthetic document body"


@dataclass(frozen=True)
class CatalogQuoteLine:
    sku: str
    quantity: int
    unit_price_fen: int


@dataclass(frozen=True)
class CatalogQuote:
    quote_id: str
    quote_version: str
    supplier_id: str
    request_id: str
    lines: tuple[CatalogQuoteLine, ...]


@dataclass(frozen=True)
class CatalogDelivery:
    delivery_id: str
    tenant_id: str
    request_id: str


@dataclass(frozen=True)
class CatalogTemplate:
    template_id: str
    body: str = "order-created"


@dataclass(frozen=True)
class CatalogRecipient:
    recipient_id: str


# ------------------------------------------------------------ serialization

#: Exact stored-schema fields of a serialized snapshot. Unknown fields are a
#: hard error: a stored snapshot is persisted accept material and must never be
#: "repaired" by ignoring what we do not understand.
_SNAPSHOT_FIELDS = frozenset(
    {"quote_id", "quote_version", "supplier_id", "items", "total_fen", "currency"}
)
_ITEM_FIELDS = frozenset({"sku", "quantity", "unit_price_fen"})
#: Serialized form is always produced by :func:`snapshot_to_bytes`, so the
#: currency key is present and fixed.
_SNAPSHOT_MAX_ITEMS = MAX_ORDER_ITEMS
_SNAPSHOT_MAX_BYTES = 65536
_SNAPSHOT_MAX_DEPTH = 8
#: Resource identifiers are plain ASCII only: no URL, path, control or escape
#: material may appear in persisted accept material.
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
#: ``quote_version`` is a *whole-string* decimal positive integer without
#: leading zeros (same rule as ``tools.params``/``tools.results``).
_VERSION_RE = re.compile(r"[1-9][0-9]{0,17}")
#: Any control character (including a trailing LF/CR) is never a legal identity.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise ExecutionError(
                ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
                "quote snapshot has a duplicate JSON key",
            )
        seen[key] = value
    return seen


def _reject_constant(name: str) -> None:
    raise ExecutionError(
        ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
        f"quote snapshot has a non-finite number: {name}",
    )


def _strict_str(name: str, value: object) -> str:
    if not isinstance(value, str) or value == "":
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            f"{name} must be a non-empty string",
        )
    return value


def _strict_id(name: str, value: object) -> str:
    text = _strict_str(name, value)
    if _CONTROL_RE.search(text):
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            f"{name} contains a control character",
        )
    if _ID_RE.fullmatch(text) is None:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            f"{name} is not a plain resource identifier",
        )
    return text


def _strict_version(value: object) -> str:
    text = _strict_str("quote_version", value)
    if _CONTROL_RE.search(text):
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            "quote_version contains a control character",
        )
    if _VERSION_RE.fullmatch(text) is None:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            "quote_version must be a decimal positive integer string",
        )
    return text


def _bounded_depth(value: object, depth: int = 0) -> None:
    if depth > _SNAPSHOT_MAX_DEPTH:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            "quote snapshot is nested too deeply",
        )
    if isinstance(value, dict):
        for entry in value.values():
            _bounded_depth(entry, depth + 1)
    elif isinstance(value, list):
        for entry in value:
            _bounded_depth(entry, depth + 1)


def _strict_int(name: str, value: object, *, minimum: int, maximum: int) -> int:
    """Exact integer semantics: bool/float/numeric strings are never accepted."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            f"{name} must be an integer (bool/float/numeric-string rejected)",
        )
    if value < minimum or value > maximum:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            f"{name} outside [{minimum}, {maximum}]",
        )
    return value


def snapshot_to_bytes(snapshot: TrustedQuoteSnapshot) -> bytes:
    """Plain UTF-8 JSON of the snapshot; NOT B's canonical encoding / SM3."""
    return json.dumps(
        asdict(snapshot), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def snapshot_from_bytes(raw: bytes | None) -> TrustedQuoteSnapshot | None:
    """Strictly decode the stored snapshot; ``None`` stays ``None``.

    The stored form is persisted accept material, so decoding is deliberately
    unforgiving: exact field sets, exact types, no duplicate keys, no non-finite
    numbers, positive quantities, non-negative bounded prices and a total that
    must recompute from the lines. Nothing is coerced or defaulted. Any problem
    raises ``LEGACY_SNAPSHOT_INVALID`` so the caller quarantines the operation
    instead of executing it against a replacement quote.
    """
    if raw is None:
        return None
    if not isinstance(raw, (bytes, bytearray)):
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID, "quote snapshot must be bytes"
        )
    if len(raw) > _SNAPSHOT_MAX_BYTES:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID, "quote snapshot is too large"
        )
    try:
        decoded = json.loads(
            bytes(raw).decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except ExecutionError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            "quote snapshot is not valid JSON",
        ) from exc
    _bounded_depth(decoded)
    if not isinstance(decoded, dict):
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            "quote snapshot must be an object",
        )

    missing = _SNAPSHOT_FIELDS - set(decoded)
    if missing:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            f"quote snapshot is missing fields: {sorted(missing)}",
        )
    extra = set(decoded) - _SNAPSHOT_FIELDS
    if extra:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            f"quote snapshot has unknown fields: {sorted(extra)}",
        )

    items_raw = decoded["items"]
    if not isinstance(items_raw, list) or not items_raw:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            "quote snapshot items must be a non-empty array",
        )
    if len(items_raw) > _SNAPSHOT_MAX_ITEMS:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            "quote snapshot has too many items",
        )

    items: list[QuoteItem] = []
    seen_skus: set[str] = set()
    for index, entry in enumerate(items_raw):
        if not isinstance(entry, dict):
            raise ExecutionError(
                ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
                f"quote snapshot item {index} must be an object",
            )
        missing_item = _ITEM_FIELDS - set(entry)
        if missing_item:
            raise ExecutionError(
                ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
                f"quote snapshot item {index} is missing fields: {sorted(missing_item)}",
            )
        extra_item = set(entry) - _ITEM_FIELDS
        if extra_item:
            raise ExecutionError(
                ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
                f"quote snapshot item {index} has unknown fields: {sorted(extra_item)}",
            )
        sku = _strict_id(f"items[{index}].sku", entry["sku"])
        if sku in seen_skus:
            raise ExecutionError(
                ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
                f"quote snapshot has a duplicate SKU: {sku}",
            )
        seen_skus.add(sku)
        quantity = _strict_int(
            f"items[{index}].quantity",
            entry["quantity"],
            minimum=1,
            maximum=MAX_SAFE_INT,
        )
        unit_price_fen = _strict_int(
            f"items[{index}].unit_price_fen",
            entry["unit_price_fen"],
            minimum=0,
            maximum=MAX_SAFE_INT,
        )
        items.append(QuoteItem(sku=sku, quantity=quantity, unit_price_fen=unit_price_fen))

    total_fen = _strict_int("total_fen", decoded["total_fen"], minimum=0, maximum=MAX_SAFE_INT)
    currency = _strict_str("currency", decoded["currency"])
    if currency != CURRENCY:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            f"quote snapshot currency is not {CURRENCY}",
        )

    snapshot = TrustedQuoteSnapshot(
        quote_id=_strict_id("quote_id", decoded["quote_id"]),
        quote_version=_strict_version(decoded["quote_version"]),
        supplier_id=_strict_id("supplier_id", decoded["supplier_id"]),
        items=tuple(items),
        total_fen=total_fen,
        currency=currency,
    )

    # Safe recomputation: every partial sum is bounded before the next add.
    recomputed = 0
    for item in snapshot.items:
        recomputed += item.quantity * item.unit_price_fen
        if recomputed > MAX_SAFE_INT:
            raise ExecutionError(
                ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
                "quote snapshot line total overflows the safe range",
            )
    if recomputed != snapshot.total_fen:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            "quote snapshot total does not match its own lines",
        )
    return snapshot


def snapshots_equal(left: TrustedQuoteSnapshot | None, right: TrustedQuoteSnapshot | None) -> bool:
    """Field-by-field comparison including supplier and unit-price allocation."""
    if left is None or right is None:
        return left is right
    return (
        left.quote_id == right.quote_id
        and left.quote_version == right.quote_version
        and left.supplier_id == right.supplier_id
        and left.total_fen == right.total_fen
        and left.currency == right.currency
        and len(left.items) == len(right.items)
        and all(
            a.sku == b.sku and a.quantity == b.quantity and a.unit_price_fen == b.unit_price_fen
            for a, b in zip(left.items, right.items, strict=False)
        )
    )


# ------------------------------------------------------------------ catalog


class TrustedCatalog:
    """Seeded, mutable only through these trusted methods, resource authority."""

    def __init__(
        self,
        *,
        requests: Iterable[CatalogRequest] = (),
        documents: Iterable[CatalogDocument] = (),
        quotes: Iterable[CatalogQuote] = (),
        deliveries: Iterable[CatalogDelivery] = (),
        templates: Iterable[CatalogTemplate] = (),
        recipients: Iterable[CatalogRecipient] = (),
    ) -> None:
        self._requests: dict[str, CatalogRequest] = {}
        self._documents: dict[str, CatalogDocument] = {}
        self._quotes: dict[tuple[str, str], CatalogQuote] = {}
        self._deliveries: dict[str, CatalogDelivery] = {}
        self._templates: dict[str, CatalogTemplate] = {}
        self._recipients: dict[str, CatalogRecipient] = {}
        for item in requests:
            self.add_request(item)
        for item in documents:
            self.add_document(item)
        for item in quotes:
            self.add_quote(item)
        for item in deliveries:
            self.add_delivery(item)
        for item in templates:
            self.add_template(item)
        for item in recipients:
            self.add_recipient(item)

    # ----------------------------------------------------------- mutation

    def add_request(self, item: CatalogRequest) -> None:
        self._requests[item.request_id] = item

    def add_document(self, item: CatalogDocument) -> None:
        self._documents[item.document_id] = item

    def add_quote(self, item: CatalogQuote) -> None:
        self._quotes[(item.quote_id, item.quote_version)] = item

    def add_delivery(self, item: CatalogDelivery) -> None:
        self._deliveries[item.delivery_id] = item

    def add_template(self, item: CatalogTemplate) -> None:
        self._templates[item.template_id] = item

    def add_recipient(self, item: CatalogRecipient) -> None:
        self._recipients[item.recipient_id] = item

    def remove_quote(self, quote_id: str, quote_version: str) -> None:
        self._quotes.pop((quote_id, quote_version), None)

    def replace_quote(self, item: CatalogQuote) -> None:
        self._quotes[(item.quote_id, item.quote_version)] = item

    def remove_request(self, request_id: str) -> None:
        self._requests.pop(request_id, None)

    def remove_document(self, document_id: str) -> None:
        self._documents.pop(document_id, None)

    def remove_delivery(self, delivery_id: str) -> None:
        self._deliveries.pop(delivery_id, None)

    # ----------------------------------------------------------- lookups

    def get_request(self, request_id: str) -> CatalogRequest | None:
        return self._requests.get(request_id)

    def get_document(self, document_id: str) -> CatalogDocument | None:
        return self._documents.get(document_id)

    def get_quote(self, quote_id: str, quote_version: str) -> CatalogQuote | None:
        return self._quotes.get((quote_id, quote_version))

    def get_delivery(self, delivery_id: str) -> CatalogDelivery | None:
        return self._deliveries.get(delivery_id)

    def get_template(self, template_id: str) -> CatalogTemplate | None:
        return self._templates.get(template_id)

    def get_recipient(self, recipient_id: str) -> CatalogRecipient | None:
        return self._recipients.get(recipient_id)

    # ------------------------------------------------------- resolution

    def build_order_snapshot(
        self,
        *,
        tenant_id: str,
        task_id: str,
        request_id: str,
        quote_id: str,
        quote_version: str,
        items: tuple[tuple[str, int], ...],
        delivery_id: str,
    ) -> TrustedQuoteSnapshot:
        """Compute the trusted cost of one order from a fixed quote version.

        Every association is looked up in the trusted catalog: the request must
        belong to the tenant/task, the quote must be the current version of the
        request, the delivery must be approved for that request, every SKU must
        be offered and the quantity must not exceed the offered quantity. Only
        then is the total computed, in integer fen and bounded.
        """
        request = self._requests.get(request_id)
        if request is None:
            raise ExecutionError(
                ExecutionErrorCode.RESOURCE_NOT_FOUND,
                f"unknown request_id: {request_id}",
            )
        if request.tenant_id != tenant_id or request.task_id != task_id:
            raise ExecutionError(
                ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
                "request does not belong to this tenant/task",
            )

        quote = self._quotes.get((quote_id, quote_version))
        if quote is None:
            raise ExecutionError(
                ExecutionErrorCode.QUOTE_INVALID,
                f"no current quote for {quote_id}@{quote_version}",
            )
        if quote.request_id != request_id:
            raise ExecutionError(
                ExecutionErrorCode.QUOTE_INVALID,
                "quote is not bound to this procurement request",
            )

        delivery = self._deliveries.get(delivery_id)
        if delivery is None:
            raise ExecutionError(
                ExecutionErrorCode.RESOURCE_NOT_FOUND,
                f"unknown delivery_id: {delivery_id}",
            )
        if delivery.tenant_id != tenant_id or delivery.request_id != request_id:
            raise ExecutionError(
                ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
                "delivery target is not approved for this request",
            )

        offered = {line.sku: line for line in quote.lines}
        if not offered:
            raise ExecutionError(ExecutionErrorCode.QUOTE_INVALID, "quote has no lines")

        snapshot_items: list[QuoteItem] = []
        total = 0
        for sku, quantity in items:
            line = offered.get(sku)
            if line is None:
                raise ExecutionError(
                    ExecutionErrorCode.QUOTE_INVALID,
                    f"SKU not offered by this quote: {sku}",
                )
            if quantity > line.quantity:
                raise ExecutionError(
                    ExecutionErrorCode.QUOTE_INVALID,
                    f"quantity {quantity} exceeds offered quantity for {sku}",
                )
            if isinstance(quantity, bool) or not isinstance(quantity, int):
                raise ExecutionError(
                    ExecutionErrorCode.INVALID_PARAMS, "quantity must be an integer"
                )
            total += quantity * line.unit_price_fen
            if total > MAX_SAFE_INT:
                raise ExecutionError(
                    ExecutionErrorCode.QUOTE_INVALID,
                    "order total exceeds the safe range",
                )
            snapshot_items.append(
                QuoteItem(sku=sku, quantity=quantity, unit_price_fen=line.unit_price_fen)
            )

        return TrustedQuoteSnapshot(
            quote_id=quote.quote_id,
            quote_version=quote.quote_version,
            supplier_id=quote.supplier_id,
            items=tuple(snapshot_items),
            total_fen=total,
            currency=CURRENCY,
        )
