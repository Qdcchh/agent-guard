"""Canonical ledger deltas: the sole v1 JSON exception for signed integers."""

from __future__ import annotations

import rfc8785

from agent_guard.contracts.encoding import MAX_SAFE_INTEGER, EncodingError

_DELTA_FIELDS = {
    "amount_reserved_delta",
    "amount_settled_delta",
    "calls_reserved_delta",
    "calls_settled_delta",
}


def canonical_ledger_changes_bytes(value: object) -> bytes:
    """Allow bounded negatives only in the four explicit node delta fields."""
    if type(value) is not dict or set(value) != {"operation_id", "events"}:
        raise EncodingError("invalid ledger_changes object")
    if type(value["operation_id"]) is not str or not 1 <= len(value["operation_id"]) <= 256:
        raise EncodingError("invalid ledger operation_id")
    events = value["events"]
    if type(events) is not list or not 1 <= len(events) <= 2:
        raise EncodingError("ledger events must contain one or two rows")
    for event in events:
        if type(event) is not dict or set(event) != {"phase", "nodes"}:
            raise EncodingError("invalid ledger event")
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
    try:
        return rfc8785.dumps(value)
    except rfc8785.CanonicalizationError as exc:
        raise EncodingError("ledger changes cannot be canonicalized") from exc
