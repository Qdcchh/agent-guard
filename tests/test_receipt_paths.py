"""Authentic three-holder signatures reaching offline path structure checks."""

from copy import deepcopy

import pytest

from agent_guard.authorization.claims import validate_access_claims, validate_child
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.contracts.ledger import INVOKE_ENDPOINT
from agent_guard.contracts.ledger_changes import canonical_ledger_changes_bytes
from agent_guard.crypto.sm import (
    generate_sm2_private_key,
    serialize_sm2_public_key,
    sign_compact_jws,
    sm3_b64url,
    verify_compact_jws,
)
from agent_guard.evidence.receipt import (
    ReceiptTrust,
    ReceiptVerificationError,
    verify_receipt_bundle,
)
from agent_guard.identity.resolver import RegisteredIdentity
from tests.test_authorization import ISSUER, NOW, _claims
from tests.test_receipt import _bundle


def _signed_path(ids=("grant-root", "grant-mid", "grant-leaf")):
    bundle, _, gateway, receipt = _bundle()
    as_key = generate_sm2_private_key()
    holders = [generate_sm2_private_key() for _ in ids]
    registrations = {}
    path = []
    actor = None
    for index, (grant_id, key) in enumerate(zip(ids, holders, strict=True)):
        client = f"agent-holder-{index}"
        did = f"did:web:identity.agent-guard.test:agents:holder-{index}"
        kid = did + "#key-1"
        spki = serialize_sm2_public_key(key.public_key())
        registrations[kid] = RegisteredIdentity("tenant-001", client, did, kid, spki)
        claims = _claims(spki)
        actor = {"sub": did, **({"act": actor} if actor is not None else {})}
        claims.update(
            client_id=client,
            act=actor,
            ag_grant_id=grant_id,
            ag_parent_id=ids[index - 1] if index else None,
            ag_delegation_remaining=2 - index,
            jti=f"token-{index}",
            ag_cnf={"kid": kid, "spki_sm3": sm3_b64url(spki)},
        )
        path.append(claims)
    trust = ReceiptTrust(
        ISSUER,
        {"as-sign-1": as_key.public_key()},
        {"gateway-receipt-1": gateway.public_key()},
        {r.kid: key.public_key() for r, key in zip(registrations.values(), holders, strict=True)},
        registrations,
    )
    # Prove each adjacent pair is otherwise valid; nonadjacent ID repetition
    # reaches the new global check, rather than a signature/holder/time failure.
    parsed = [validate_access_claims(claims, issuer=ISSUER, now=NOW) for claims in path]
    for parent, child in zip(parsed, parsed[1:], strict=False):
        validate_child(parent, child)
    bundle["ancestor_tokens"] = [
        sign_compact_jws(as_key, c, key_id="as-sign-1", token_type="ag-at+jwt") for c in path
    ]
    bundle["token_jws"] = bundle["ancestor_tokens"][-1]
    leaf = path[-1]
    bundle["proof_jws"] = sign_ag_proof(
        holders[-1],
        kid=leaf["ag_cnf"]["kid"],
        client_id=leaf["client_id"],
        purpose="invoke",
        endpoint=INVOKE_ENDPOINT,
        token=bundle["token_jws"],
        body=bundle["request"],
        now=NOW,
    )
    for event in bundle["ledger_changes"]["events"]:
        node = event["nodes"][0]
        event["nodes"] = [dict(node, grant_id=grant_id) for grant_id in ids]
    receipt.update(
        grant_id=ids[-1],
        token_sm3=sm3_b64url(bundle["token_jws"].encode()),
        proof_sm3=sm3_b64url(bundle["proof_jws"].encode()),
    )
    _resign(bundle, gateway, receipt)
    for token in bundle["ancestor_tokens"]:
        assert verify_compact_jws(token, expected_type="ag-at+jwt", trusted_keys=trust.as_keys)
    assert verify_compact_jws(
        bundle["proof_jws"], expected_type="ag-pop+jwt", trusted_keys=trust.holder_keys
    )
    return bundle, trust, gateway, receipt


def _resign(bundle, gateway, receipt):
    receipt["ledger_sm3"] = sm3_b64url(canonical_ledger_changes_bytes(bundle["ledger_changes"]))
    bundle["receipt_jws"] = sign_compact_jws(
        gateway, receipt, key_id="gateway-receipt-1", token_type="ag-receipt+jwt"
    )


def test_authentic_nonadjacent_duplicate_grant_rejected():
    bundle, trust, _, _ = _signed_path(("grant-root", "grant-mid", "grant-root"))
    with pytest.raises(ReceiptVerificationError, match="duplicate grant in ancestor path"):
        verify_receipt_bundle(bundle, trust=trust)


def test_authentic_three_layer_unique_path_passes():
    bundle, trust, _, _ = _signed_path()
    assert verify_receipt_bundle(bundle, trust=trust).amount_fen == 70000


@pytest.mark.parametrize(
    "mutation", ["duplicate-ledger", "reorder", "missing", "adjacent", "digest"]
)
def test_authenticated_path_mutations_rejected(mutation):
    bundle, trust, gateway, receipt = _signed_path()
    changed = deepcopy(bundle)
    if mutation == "duplicate-ledger":
        for event in changed["ledger_changes"]["events"]:
            event["nodes"][2] = deepcopy(event["nodes"][0])
        _resign(changed, gateway, receipt)
    elif mutation == "reorder":
        changed["ancestor_tokens"][0], changed["ancestor_tokens"][1] = (
            changed["ancestor_tokens"][1],
            changed["ancestor_tokens"][0],
        )
    elif mutation == "missing":
        del changed["ancestor_tokens"][1]
    elif mutation == "adjacent":
        changed["ancestor_tokens"][1] = changed["ancestor_tokens"][0]
    else:
        receipt["token_sm3"] = sm3_b64url(canonical_json_bytes({"other": "token"}))
        _resign(changed, gateway, receipt)
    # Tokens and receipt retain authentic signatures; only their bindings differ.
    assert verify_compact_jws(
        changed["receipt_jws"],
        expected_type="ag-receipt+jwt",
        trusted_keys=trust.gateway_keys,
    )
    with pytest.raises(ReceiptVerificationError):
        verify_receipt_bundle(changed, trust=trust)
