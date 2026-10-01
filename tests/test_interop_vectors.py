"""Frozen B-side interop vectors and their negative cases (no database)."""

from __future__ import annotations

from copy import deepcopy

import pytest

from agent_guard.authorization.claims import validate_access_claims, validate_child
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.authorization.verifier import VerificationError
from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from agent_guard.contracts.ledger import INVOKE_ENDPOINT
from agent_guard.contracts.ledger_changes import canonical_ledger_changes_bytes
from agent_guard.crypto.sm import (
    serialize_sm2_public_key,
    sign_compact_jws,
    sm3_b64url,
    verify_compact_jws,
)
from agent_guard.evidence.receipt import ReceiptVerificationError, verify_receipt_bundle
from tests.fixtures import interop

NOW = 1_800_000_000


def test_frozen_spki_and_digest_vectors():
    for name in ("as", "planner", "selector", "executor", "gateway-receipt"):
        key = (
            interop.as_key()
            if name == "as"
            else (
                interop.gateway_receipt_key()
                if name == "gateway-receipt"
                else interop.agent_key(name)
            )
        )
        spki = serialize_sm2_public_key(key.public_key())
        assert b64url_encode(spki) == interop.SPKI_B64[name]
        assert sm3_b64url(spki) == interop.SPKI_SM3[name]
    assert sm3_b64url(canonical_json_bytes(interop.invocation_request())) == interop.REQUEST_SM3
    assert sm3_b64url(canonical_json_bytes(interop.CONSTRAINTS)) == interop.CONSTRAINTS_SM3


def test_chain_narrows_and_verifies_against_fixed_as_key():
    chain = interop.interop_chain(NOW)
    key = interop.as_key().public_key()
    claims = [
        validate_access_claims(
            verify_compact_jws(token, expected_type="ag-at+jwt", trusted_keys={"as-sign-1": key}),
            issuer=interop.ISSUER,
            now=NOW,
        )
        for token in (chain.root_token, chain.selector_token, chain.executor_token)
    ]
    validate_child(claims[0], claims[1])
    validate_child(claims[1], claims[2])
    assert [claim.raw["ag_delegation_remaining"] for claim in claims] == [2, 1, 0]
    assert claims[2].actors == (
        interop.agent_did("executor"),
        interop.agent_did("selector"),
        interop.agent_did("planner"),
    )
    assert claims[0].raw["ag_parent_id"] is None
    assert claims[1].raw["ag_parent_id"] == interop.ROOT_GRANT
    assert claims[2].raw["ag_parent_id"] == interop.SELECTOR_GRANT
    assert claims[2].raw["ag_limits"]["amount_fen"] == 70000


def test_verifier_builds_trusted_invocation_from_fixed_vectors():
    chain = interop.interop_chain(NOW)
    request = interop.invocation_request()
    proof = interop.invocation_proof(chain, request, NOW)
    verified = interop.verifier().verify_static(
        chain.executor_token,
        proof,
        endpoint=INVOKE_ENDPOINT,
        method="POST",
        body=canonical_json_bytes(request),
        now=NOW,
    )
    assert verified.tenant_id == interop.TENANT
    assert verified.task_id == interop.TASK
    assert verified.subject == interop.SUBJECT
    assert verified.holder_client_id == "agent-executor"
    assert verified.grant_id == interop.EXECUTOR_GRANT
    assert verified.root_id == interop.ROOT_GRANT
    assert verified.tool_id == "procurement.order.create"
    assert verified.token_exp == chain.executor_claims["exp"]
    assert verified.intent_digest == sm3_b64url(canonical_json_bytes(request))


def test_stolen_tampered_and_type_swapped_vectors_fail():
    chain = interop.interop_chain(NOW)
    request = interop.invocation_request()
    body = canonical_json_bytes(request)
    stolen = sign_ag_proof(
        interop.agent_key("planner"),
        kid=interop.agent_kid("executor"),
        client_id="agent-executor",
        purpose="invoke",
        endpoint=INVOKE_ENDPOINT,
        body=request,
        token=chain.executor_token,
        now=NOW,
    )
    with pytest.raises(VerificationError):
        interop.verifier().verify_static(
            chain.executor_token,
            stolen,
            endpoint=INVOKE_ENDPOINT,
            method="POST",
            body=body,
            now=NOW,
        )
    proof = interop.invocation_proof(chain, request, NOW)
    tampered = deepcopy(request)
    tampered["params"]["items"][0]["quantity"] = 1
    tampered["params"]["delivery_id"] = "office-002"
    with pytest.raises(VerificationError):
        interop.verifier().verify_static(
            chain.executor_token,
            proof,
            endpoint=INVOKE_ENDPOINT,
            method="POST",
            body=canonical_json_bytes(tampered),
            now=NOW,
        )
    id_token_type = sign_compact_jws(
        interop.as_key(),
        chain.executor_claims,
        key_id="as-sign-1",
        token_type="ag-id+jwt",
    )
    with pytest.raises(VerificationError):
        interop.verifier().verify_static(
            id_token_type,
            proof,
            endpoint=INVOKE_ENDPOINT,
            method="POST",
            body=body,
            now=NOW,
        )


def test_evidence_bundle_verifies_and_tampering_is_detected():
    bundle, trust = interop.evidence_bundle(NOW)
    verified = verify_receipt_bundle(bundle, trust=trust)
    assert verified.operation_id == "operation-interop-1"
    assert verified.status == "SUCCEEDED"
    assert verified.amount_fen == 70000
    assert verified.anchoring_status == "UNANCHORED"

    changed = deepcopy(bundle)
    changed["result"]["order_id"] = "other-order"
    with pytest.raises(ReceiptVerificationError):
        verify_receipt_bundle(changed, trust=trust)

    changed = deepcopy(bundle)
    changed["ancestor_tokens"] = [bundle["ancestor_tokens"][0]]
    with pytest.raises(ReceiptVerificationError):
        verify_receipt_bundle(changed, trust=trust)

    changed = deepcopy(bundle)
    changed["anchoring_status"] = "ANCHORED"
    with pytest.raises(ReceiptVerificationError, match="anchoring"):
        verify_receipt_bundle(changed, trust=trust)

    # Re-sign a semantically wrong terminal delta: the gateway signature is
    # valid but the ancestor path amount/call rules must still reject it.
    changed = deepcopy(bundle)
    changed["ledger_changes"]["events"][1]["nodes"][2]["calls_settled_delta"] = 0
    receipt = verify_compact_jws(
        bundle["receipt_jws"],
        expected_type="ag-receipt+jwt",
        trusted_keys={interop.GATEWAY_RECEIPT_KID: interop.gateway_receipt_key().public_key()},
    )
    updated = dict(
        receipt, ledger_sm3=sm3_b64url(canonical_ledger_changes_bytes(changed["ledger_changes"]))
    )
    changed["receipt_jws"] = sign_compact_jws(
        interop.gateway_receipt_key(),
        updated,
        key_id=interop.GATEWAY_RECEIPT_KID,
        token_type="ag-receipt+jwt",
    )
    with pytest.raises(ReceiptVerificationError, match="terminal delta"):
        verify_receipt_bundle(changed, trust=trust)
