"""The task and v1 wrappers consume one real receipt verification path."""

from dataclasses import replace

import pytest

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.evidence.receipt import verify_receipt_bundle
from agent_guard.evidence.receipt_semantics import (
    ReceiptVerificationError,
    verify_receipt_components,
)
from tests.fixtures.a32_common import signed_receipt_material


def test_component_semantics_legacy_v1_compatibility():
    m = signed_receipt_material(noncanonical_request=True)
    result = verify_receipt_components(m["components"], m["receipt_trust"])
    assert result == verify_receipt_bundle(m["v1_bundle"], trust=m["receipt_trust"])
    assert result.operation_id == m["expected"]["operation_id"]
    assert result.amount_fen == 70000
    assert m["components"].request_raw.startswith(b" \n")
    assert result.anchoring_status == "UNANCHORED"


@pytest.mark.parametrize(
    "component",
    [
        "token_jws",
        "proof_jws",
        "receipt_jws",
        "request_raw",
        "result_raw",
        "ledger_raw",
        "quote_raw",
        "context_raw",
        "source_raw",
    ],
)
def test_component_original_mutations_rejected(component):
    m = signed_receipt_material()
    c = m["components"]
    raw = getattr(c, component)
    if component.endswith("jws"):
        changed = raw[:-1] + (b"A" if raw[-1:] != b"A" else b"B")
    elif component == "ledger_raw":
        changed = raw.replace(b'"calls_settled_delta":1', b'"calls_settled_delta":0')
    else:
        value = load_strict_json(raw)
        if component == "request_raw":
            value["idempotency_key"] = "different"
        elif component == "result_raw":
            value["order_id"] = "other"
        elif component == "quote_raw":
            value["quote_id"] = "quote-other"
        elif component == "context_raw":
            value["proof_jti"] = "different"
        else:
            value["snapshot"]["tenant_id"] = "other"
        changed = canonical_json_bytes(value)
    assert changed != raw
    with pytest.raises(ValueError):
        verify_receipt_components(replace(c, **{component: changed}), m["receipt_trust"])


@pytest.mark.parametrize(
    "field,raw",
    [
        ("token_jws", b"x" * 16385),
        ("request_raw", b"x" * 65537),
        ("result_raw", bytearray(b"{}")),
        ("ancestor_tokens", [b"a"]),
    ],
)
def test_receipt_component_capacity_and_deep_immutability(field, raw):
    c = signed_receipt_material()["components"]
    with pytest.raises(ReceiptVerificationError):
        replace(c, **{field: raw})


def test_public_task_fixture_independent_real_signatures_and_typedrefs():
    from io import BytesIO

    from agent_guard.audit.checkpoint import verify_checkpoint
    from agent_guard.audit.contracts import genesis_digest
    from agent_guard.crypto.sm import sm3_b64url
    from agent_guard.evidence.task_bundle import iter_frames
    from tests.fixtures.a32_common import signed_task_material

    m = signed_task_material()
    assert verify_receipt_components(m["components"], m["receipt_trust"]).status == "SUCCEEDED"
    frames = list(iter_frames(BytesIO(m["bundle_raw"])))
    assert frames[0]["object_count"] == len(m["objects"])
    previous = genesis_digest(m["scope"])
    for seq, record in enumerate(m["records"], 1):
        assert record.seq == seq and record.previous_digest == previous
        previous = sm3_b64url(record.raw)
    cp = verify_checkpoint(
        m["external_pin"]["checkpoint_jws"],
        trust=m["external_trust"]["audit_keys"],
        expected_scope=m["scope"],
    )
    assert cp.claims.sequence == 4 and cp.claims.head_digest == previous
    assert m["registration"]["genesis_digest"] == genesis_digest(m["scope"])
    assert set(m["public_trust"]) == {
        "version",
        "issuer",
        "as_keys",
        "gateway_keys",
        "holder_keys",
        "historical_registrations",
        "catalog",
        "audit_keys",
        "scope",
        "registration",
    }
    assert b"PRIVATE KEY" not in canonical_json_bytes(m["public_trust"])
    assert m["expected_report"]["current_auth"] == "UNKNOWN"
    assert len({ident for _, ident, _ in m["objects"]}) == len(m["objects"])
