"""Bounded signed-delta parsing never weakens generic JSON or v1 wire fields."""

import json

import pytest

from agent_guard.contracts.encoding import EncodingError, load_strict_json
from agent_guard.contracts.ledger_changes import canonical_ledger_changes_bytes, load_ledger_changes


def _row():
    return {
        "operation_id": "op",
        "events": [
            {
                "phase": "RELEASE",
                "seq": 1,
                "nodes": [
                    {
                        "grant_id": "root",
                        "amount_reserved_delta": -1,
                        "amount_settled_delta": 0,
                        "calls_reserved_delta": -1,
                        "calls_settled_delta": 0,
                    }
                ],
            }
        ],
    }


def test_internal_signed_deltas_do_not_enable_negative_generic_json():
    row = _row()
    raw = json.dumps(row).encode()
    assert load_ledger_changes(raw, internal=True) == row
    with pytest.raises(EncodingError):
        load_strict_json(raw)
    with pytest.raises(EncodingError):
        canonical_ledger_changes_bytes(row)
    del row["events"][0]["seq"]
    assert canonical_ledger_changes_bytes(row)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"operation_id":"x","operation_id":"y","events":[]}',
        b'"' + b"x" * 65537 + b'"',
        b'{"operation_id":"\\ud800","events":[]}',
        b"[" * 70 + b"0" + b"]" * 70,
        b"NaN",
        b"-0",
        b"1.0",
        b"1e1",
    ],
)
def test_signed_ledger_parser_rejects_malformed_or_unbounded(raw):
    with pytest.raises(EncodingError):
        load_ledger_changes(raw, internal=True)


@pytest.mark.parametrize(
    "variant", ["negative-seq", "bool-seq", "extra", "float-delta", "bool-delta", "overflow"]
)
def test_signed_exception_is_only_exact_node_delta_fields(variant):
    row = _row()
    if variant == "negative-seq":
        row["events"][0]["seq"] = -1
    if variant == "bool-seq":
        row["events"][0]["seq"] = True
    if variant == "extra":
        row["unexpected"] = -1
    if variant == "float-delta":
        row["events"][0]["nodes"][0]["calls_reserved_delta"] = -1.0
    if variant == "bool-delta":
        row["events"][0]["nodes"][0]["calls_reserved_delta"] = True
    if variant == "overflow":
        row["events"][0]["nodes"][0]["calls_reserved_delta"] = -(2**53)
    with pytest.raises(EncodingError):
        load_ledger_changes(json.dumps(row).encode(), internal=True)
