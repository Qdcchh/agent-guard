"""Independent, offline receipt checks with synthetic test-only SM2 keys."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from agent_guard.contracts.encoding import EncodingError, canonical_json_bytes
from agent_guard.contracts.ledger_changes import canonical_ledger_changes_bytes
from agent_guard.crypto.sm import serialize_sm2_public_key, sign_compact_jws, sm3_b64url
from agent_guard.evidence.receipt import (
    ReceiptTrust,
    ReceiptVerificationError,
    verify_receipt_bundle,
)
from agent_guard.identity.resolver import RegisteredIdentity
from tests.test_authorization import DID, ISSUER, KID, NOW, _body, _claims, _fixture, _sign_pair


def _node(*, reserve: int, settled: int, calls_reserve: int, calls_settled: int):
    return {
        "grant_id": "grant-root",
        "amount_reserved_delta": reserve,
        "amount_settled_delta": settled,
        "calls_reserved_delta": calls_reserve,
        "calls_settled_delta": calls_settled,
    }


def _bundle(*, status="SUCCEEDED"):
    as_key, holder_key, _, _, _ = _fixture()
    from agent_guard.crypto.sm import generate_sm2_private_key

    gateway_key = generate_sm2_private_key()
    spki = serialize_sm2_public_key(holder_key.public_key())
    token, proof = _sign_pair(as_key, holder_key, _claims(spki), _body())
    request = json.loads(_body())
    result = {"order_id": "synthetic-order-001"} if status == "SUCCEEDED" else {"error": "DECLINED"}
    terminal = (
        _node(reserve=-70000, settled=70000, calls_reserve=-1, calls_settled=1)
        if status == "SUCCEEDED"
        else _node(reserve=-70000, settled=0, calls_reserve=-1, calls_settled=0)
    )
    ledger = {
        "operation_id": "operation-001",
        "events": [
            {
                "phase": "RESERVE",
                "nodes": [_node(reserve=70000, settled=0, calls_reserve=1, calls_settled=0)],
            },
            {"phase": "SETTLE" if status == "SUCCEEDED" else "RELEASE", "nodes": [terminal]},
        ],
    }
    receipt = {
        "profile": "GM-MVP-1",
        "receipt_id": "receipt-001",
        "operation_id": "operation-001",
        "tenant_id": "tenant-001",
        "task_id": "task-001",
        "root_grant_id": "grant-root",
        "grant_id": "grant-root",
        "token_sm3": sm3_b64url(token.encode("ascii")),
        "proof_sm3": sm3_b64url(proof.encode("ascii")),
        "intent_sm3": sm3_b64url(canonical_json_bytes(request)),
        "tool_id": "procurement.order.create",
        "tool_version": "1",
        "status": status,
        "amount_fen": 70000 if status == "SUCCEEDED" else 0,
        "result_sm3": sm3_b64url(canonical_json_bytes(result)),
        "ledger_sm3": sm3_b64url(canonical_ledger_changes_bytes(ledger)),
        "iat": NOW + 40,
    }
    bundle = {
        "manifest_version": "AG-EVIDENCE-1",
        "anchoring_status": "UNANCHORED",
        "receipt_jws": sign_compact_jws(
            gateway_key, receipt, key_id="gateway-receipt-1", token_type="ag-receipt+jwt"
        ),
        "ancestor_tokens": [token],
        "token_jws": token,
        "proof_jws": proof,
        "request": request,
        "result": result,
        "ledger_changes": ledger,
    }
    trust = ReceiptTrust(
        issuer=ISSUER,
        as_keys={"as-sign-1": as_key.public_key()},
        gateway_keys={"gateway-receipt-1": gateway_key.public_key()},
        holder_keys={KID: holder_key.public_key()},
        historical_registrations={
            KID: RegisteredIdentity("tenant-001", "agent-planner", DID, KID, spki)
        },
    )
    return bundle, trust, gateway_key, receipt


@pytest.mark.parametrize("status", ["SUCCEEDED", "FAILED"])
def test_valid_unanchored_receipt(status):
    bundle, trust, _, _ = _bundle(status=status)
    verified = verify_receipt_bundle(bundle, trust=trust)
    assert verified.operation_id == "operation-001"
    assert verified.status == status
    assert verified.amount_fen == (70000 if status == "SUCCEEDED" else 0)
    assert verified.anchoring_status == "UNANCHORED"


def test_modified_result_or_proof_or_untrusted_gateway_key_rejected():
    bundle, trust, _, _ = _bundle()
    changed = deepcopy(bundle)
    changed["result"]["order_id"] = "other-order"
    with pytest.raises(ReceiptVerificationError):
        verify_receipt_bundle(changed, trust=trust)
    changed = deepcopy(bundle)
    changed["proof_jws"] += "x"
    with pytest.raises(ReceiptVerificationError):
        verify_receipt_bundle(changed, trust=trust)
    wrong = ReceiptTrust(
        trust.issuer,
        trust.as_keys,
        {"unknown": next(iter(trust.gateway_keys.values()))},
        trust.holder_keys,
        trust.historical_registrations,
    )
    with pytest.raises(ReceiptVerificationError):
        verify_receipt_bundle(bundle, trust=wrong)


def test_re_signed_bad_ancestor_delta_still_rejected():
    bundle, trust, gateway_key, receipt = _bundle()
    changed = deepcopy(bundle)
    changed["ledger_changes"]["events"][1]["nodes"][0]["calls_settled_delta"] = 0
    updated = dict(
        receipt, ledger_sm3=sm3_b64url(canonical_ledger_changes_bytes(changed["ledger_changes"]))
    )
    changed["receipt_jws"] = sign_compact_jws(
        gateway_key, updated, key_id="gateway-receipt-1", token_type="ag-receipt+jwt"
    )
    with pytest.raises(ReceiptVerificationError, match="terminal delta"):
        verify_receipt_bundle(changed, trust=trust)
    changed = deepcopy(bundle)
    updated = dict(receipt, amount_fen=60000)
    changed["receipt_jws"] = sign_compact_jws(
        gateway_key, updated, key_id="gateway-receipt-1", token_type="ag-receipt+jwt"
    )
    with pytest.raises(ReceiptVerificationError, match="receipt amount"):
        verify_receipt_bundle(changed, trust=trust)
    changed = deepcopy(bundle)
    changed["ancestor_tokens"] = [bundle["token_jws"], bundle["token_jws"]]
    with pytest.raises(ReceiptVerificationError):
        verify_receipt_bundle(changed, trust=trust)
    changed = deepcopy(bundle)
    changed["anchoring_status"] = "ANCHORED"
    with pytest.raises(ReceiptVerificationError, match="anchoring"):
        verify_receipt_bundle(changed, trust=trust)


def test_only_named_delta_fields_accept_signed_integers():
    bundle, _, _, _ = _bundle()
    ledger = deepcopy(bundle["ledger_changes"])
    ledger["events"][1]["nodes"][0]["amount_reserved_delta"] = -70000
    assert canonical_ledger_changes_bytes(ledger)
    ledger["events"][1]["nodes"][0]["calls_settled_delta"] = True
    with pytest.raises(EncodingError):
        canonical_ledger_changes_bytes(ledger)
    ledger["events"][1]["nodes"][0]["calls_settled_delta"] = 1
    ledger["operation_id"] = -1
    with pytest.raises(EncodingError):
        canonical_ledger_changes_bytes(ledger)
