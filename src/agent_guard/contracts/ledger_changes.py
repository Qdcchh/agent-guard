"""Canonical ledger deltas: the sole v1 JSON exception for signed integers."""

from __future__ import annotations

import rfc8785

from agent_guard.contracts.encoding import (
    MAX_JSON_BYTES,
    MAX_SAFE_INTEGER,
    EncodingError,
    _decode_json,
)

_DELTA_FIELDS = {
    "amount_reserved_delta",
    "amount_settled_delta",
    "calls_reserved_delta",
    "calls_settled_delta",
}


def _validate_ledger(value: object, *, internal: bool = False) -> None:
    """Allow bounded negatives only in the four explicit node delta fields."""
    if type(value) is not dict or set(value) != {"operation_id", "events"}:
        raise EncodingError("invalid ledger_changes object")
    if type(value["operation_id"]) is not str or not 1 <= len(value["operation_id"]) <= 256:
        raise EncodingError("invalid ledger operation_id")
    events = value["events"]
    if type(events) is not list or not 1 <= len(events) <= 2:
        raise EncodingError("ledger events must contain one or two rows")
    for event in events:
        if type(event) is not dict or set(event) != (
            {"phase", "nodes", "seq"} if internal else {"phase", "nodes"}
        ):
            raise EncodingError("invalid ledger event")
        if internal and (type(event["seq"]) is not int or event["seq"] not in (0, 1)):
            raise EncodingError("invalid internal ledger sequence")
        if type(event["phase"]) is not str or event["phase"] not in {
            "RESERVE",
            "SETTLE",
            "RELEASE",
        }:
            raise EncodingError("invalid ledger phase")
        nodes = event["nodes"]
        if type(nodes) is not list or not 1 <= len(nodes) <= 3:
            raise EncodingError("ledger nodes must contain one to three rows")
        for node in nodes:
            if type(node) is not dict or set(node) != {"grant_id", *_DELTA_FIELDS}:
                raise EncodingError("invalid ledger node")
            if type(node["grant_id"]) is not str or not 1 <= len(node["grant_id"]) <= 256:
                raise EncodingError("invalid ledger grant_id")
            for name in _DELTA_FIELDS:
                delta = node[name]
                if type(delta) is not int or not -MAX_SAFE_INTEGER <= delta <= MAX_SAFE_INTEGER:
                    raise EncodingError("invalid signed ledger delta")


def canonical_ledger_changes_bytes(value: object) -> bytes:
    """Unique v1 encoding; internal seq is never accepted on the signed wire."""
    _validate_ledger(value)
    try:
        encoded = rfc8785.dumps(value)
    except rfc8785.CanonicalizationError as exc:
        raise EncodingError("ledger changes cannot be canonicalized") from exc
    if len(encoded) > MAX_JSON_BYTES:
        raise EncodingError("ledger changes exceed byte bound")
    return encoded


def load_ledger_changes(raw: bytes, *, internal: bool = False) -> dict:
    """Dedicated strict signed-delta schema, sharing the central JSON decoder."""

    def integer(text):
        digits = text[1:] if text.startswith("-") else text
        if len(digits) > len(str(MAX_SAFE_INTEGER)) or text == "-0":
            raise EncodingError("invalid ledger integer")
        number = int(text)
        if not -MAX_SAFE_INTEGER <= number <= MAX_SAFE_INTEGER:
            raise EncodingError("ledger integer out of range")
        return number

    value = _decode_json(raw, integer_parser=integer)
    _validate_ledger(value, internal=internal)
    # Validate Unicode and canonical bounds without granting seq wire authority.
    public = {
        "operation_id": value["operation_id"],
        "events": [{"phase": row["phase"], "nodes": row["nodes"]} for row in value["events"]],
    }
    canonical_ledger_changes_bytes(public)
    return value
