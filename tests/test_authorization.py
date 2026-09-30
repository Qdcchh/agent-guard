"""B's signed-token, DID holder and static gateway boundary tests."""

import json

import pytest

from agent_guard.authorization.claims import ClaimsError, validate_access_claims, validate_child
from agent_guard.authorization.oidc import OidcValidationError, pkce_s256_challenge, verify_id_token
from agent_guard.authorization.policy import DelegationError, GrantPolicy
from agent_guard.authorization.proof import ProofInputError, sign_ag_proof
from agent_guard.authorization.verifier import InvocationVerifier, VerificationError
from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from agent_guard.crypto.sm import (
    generate_sm2_private_key,
    serialize_sm2_public_key,
    sign_compact_jws,
    sm3_b64url,
)
from agent_guard.identity.resolver import (
    METHOD_TYPE,
    SPKI_PROPERTY,
    IdentityError,
    IdentityResolver,
    RegisteredIdentity,
    ResolvedIdentity,
    did_web_url,
)
from agent_guard.ledger.validation import validate_invocation

NOW = 1_800_000_000
ISSUER = "https://auth.agent-guard.test"
ENDPOINT = "https://gateway.agent-guard.test/v1/invocations"
DID = "did:web:identity.agent-guard.test:agents:planner"
KID = DID + "#key-1"


def _claims(spki: bytes) -> dict:
    return {
        "iss": ISSUER,
        "sub": "user-001",
        "aud": "https://gateway.agent-guard.test",
        "iat": NOW - 10,
        "nbf": NOW - 10,
        "exp": NOW + 200,
        "jti": "token-001",
        "client_id": "agent-planner",
        "scope": "procurement.request.read procurement.order.create",
        "act": {"sub": DID},
        "ag_profile": "GM-MVP-1",
        "ag_tenant_id": "tenant-001",
        "ag_task_id": "task-001",
        "ag_grant_id": "grant-root",
        "ag_parent_id": None,
        "ag_root_id": "grant-root",
        "ag_delegation_remaining": 2,
        "ag_limits": {"currency": "CNY", "amount_fen": 100000, "calls": 10},
        "ag_constraints": {
            "request_ids": ["req-001"],
            "document_ids": ["doc-001"],
            "quote_versions": ["quote-001@1"],
            "skus": ["sku-001"],
            "max_quantity": 2,
            "delivery_ids": ["office-001"],
            "template_ids": [],
            "recipient_ids": [],
        },
        "ag_cnf": {"kid": KID, "spki_sm3": sm3_b64url(spki)},
    }


def _body() -> bytes:
    return canonical_json_bytes(
        {
            "profile": "GM-MVP-1",
            "task_id": "task-001",
            "tool_id": "procurement.order.create",
            "tool_version": "1",
            "idempotency_key": "purchase-001",
            "params": {
                "request_id": "req-001",
                "quote_id": "quote-001",
                "quote_version": "1",
                "items": [{"sku": "sku-001", "quantity": 1}],
                "delivery_id": "office-001",
            },
        }
    )


def _fixture():
    as_key = generate_sm2_private_key()
    holder_key = generate_sm2_private_key()
    spki = serialize_sm2_public_key(holder_key.public_key())
    entry = RegisteredIdentity("tenant-001", "agent-planner", DID, KID, spki)
    document = {
        "id": DID,
        "verificationMethod": [
            {
                "id": KID,
                "type": METHOD_TYPE,
                "controller": DID,
                SPKI_PROPERTY: b64url_encode(spki),
            }
        ],
        "authentication": [KID],
        "capabilityInvocation": [KID],
        "capabilityDelegation": [KID],
    }
    resolver = IdentityResolver(
        {("tenant-001", "agent-planner"): entry},
        allowed_hosts=frozenset({"identity.agent-guard.test"}),
        fetch_document=lambda url: canonical_json_bytes(document),
    )
    staged = []
    verifier = InvocationVerifier(
        issuer=ISSUER,
        as_keys={"as-sign-1": as_key.public_key()},
        identities=resolver,
        stage_evidence=lambda token, proof, body: (
            staged.append((token, proof, body)) or "evidence-001"
        ),
    )
    return as_key, holder_key, document, verifier, staged


def _sign_pair(as_key, holder_key, claims, body):
    token = sign_compact_jws(as_key, claims, key_id="as-sign-1", token_type="ag-at+jwt")
    proof = sign_compact_jws(
        holder_key,
        {
            "profile": "GM-MVP-1",
            "purpose": "invoke",
            "client_id": "agent-planner",
            "jti": "YWJjZGVmZ2hpamtsbW5vcA",
            "iat": NOW,
            "exp": NOW + 30,
            "htm": "POST",
            "htu": ENDPOINT,
            "token_sm3": sm3_b64url(token.encode("ascii")),
            "body_sm3": sm3_b64url(canonical_json_bytes(json.loads(body))),
        },
        key_id=KID,
        token_type="ag-pop+jwt",
    )
    return token, proof


def test_static_verifier_builds_ledger_context_only_after_signatures():
    as_key, holder_key, _, verifier, staged = _fixture()
    body = _body()
    token, proof = _sign_pair(
        as_key, holder_key, _claims(serialize_sm2_public_key(holder_key.public_key())), body
    )
    verified = verifier.verify_static(
        token, proof, endpoint=ENDPOINT, method="POST", body=body, now=NOW
    )
    assert verified.grant_id == "grant-root"
    assert verified.holder_kid == KID
    assert verified.tool_id == "procurement.order.create"
    assert verified.token_digest == sm3_b64url(token.encode("ascii"))
    assert staged == [(token, proof, body)]
    validate_invocation(verified)


def test_static_verifier_rejects_tampering_and_does_not_stage():
    as_key, holder_key, _, verifier, staged = _fixture()
    body = _body()
    claims = _claims(serialize_sm2_public_key(holder_key.public_key()))
    token, proof = _sign_pair(as_key, holder_key, claims, body)
    bad_body = body.replace(b'"quantity":1', b'"quantity":2')
    for candidate_token, candidate_proof, candidate_body in (
        (token, proof, bad_body),
        (token, proof[:-1] + ("A" if proof[-1] != "A" else "B"), body),
        (token, proof, body.replace(b'"task-001"', b'"task-002"')),
    ):
        with pytest.raises(VerificationError):
            verifier.verify_static(
                candidate_token,
                candidate_proof,
                endpoint=ENDPOINT,
                method="POST",
                body=candidate_body,
                now=NOW,
            )
    assert staged == []


def test_signed_unknown_claim_and_wrong_holder_are_rejected():
    as_key, holder_key, _, verifier, _ = _fixture()
    body = _body()
    claims = _claims(serialize_sm2_public_key(holder_key.public_key()))
    claims["ag_unknown"] = "x"
    token, proof = _sign_pair(as_key, holder_key, claims, body)
    with pytest.raises(VerificationError):
        verifier.verify_static(token, proof, endpoint=ENDPOINT, method="POST", body=body, now=NOW)
    claims.pop("ag_unknown")
    other_key = generate_sm2_private_key()
    token, proof = _sign_pair(as_key, other_key, claims, body)
    with pytest.raises(VerificationError):
        verifier.verify_static(token, proof, endpoint=ENDPOINT, method="POST", body=body, now=NOW)


def test_did_document_change_is_not_automatic_registry_approval():
    _, holder_key, document, verifier, _ = _fixture()
    assert did_web_url(DID) == "https://identity.agent-guard.test/agents/planner/did.json"
    document["verificationMethod"][0][SPKI_PROPERTY] = b64url_encode(
        serialize_sm2_public_key(generate_sm2_private_key().public_key())
    )
    with pytest.raises(IdentityError):
        verifier._identities.resolve_registered(
            "agent-planner", "tenant-001", "capabilityInvocation"
        )
    assert holder_key is not None


def test_child_policy_rejects_expansion_and_unknown_fields():
    key = generate_sm2_private_key()
    parent = _claims(serialize_sm2_public_key(key.public_key()))
    child = json.loads(json.dumps(parent))
    child.update(
        {
            "client_id": "agent-selector",
            "act": {
                "sub": "did:web:identity.agent-guard.test:agents:selector",
                "act": parent["act"],
            },
            "ag_grant_id": "grant-child",
            "ag_parent_id": "grant-root",
            "ag_delegation_remaining": 1,
            "ag_limits": {"currency": "CNY", "amount_fen": 80000, "calls": 8},
            "scope": "procurement.request.read",
        }
    )
    validated_parent = validate_access_claims(parent, issuer=ISSUER, now=NOW)
    validated_child = validate_access_claims(child, issuer=ISSUER, now=NOW)
    validate_child(validated_parent, validated_child)
    child["ag_limits"]["amount_fen"] = 100001
    with pytest.raises(ClaimsError, match="expanded amount_fen"):
        validate_child(validated_parent, validate_access_claims(child, issuer=ISSUER, now=NOW))
    child["unknown"] = True
    with pytest.raises(ClaimsError, match="fields"):
        validate_access_claims(child, issuer=ISSUER, now=NOW)


def test_id_token_is_bound_to_rp_nonce_audience_and_type():
    key = generate_sm2_private_key()
    claims = {
        "iss": ISSUER,
        "sub": "user-001",
        "aud": "agent-planner",
        "iat": NOW - 10,
        "exp": NOW + 100,
        "auth_time": NOW - 20,
        "nonce": "browser-session-nonce",
    }
    token = sign_compact_jws(key, claims, key_id="as-sign-1", token_type="ag-id+jwt")
    options = {
        "trusted_keys": {"as-sign-1": key.public_key()},
        "issuer": ISSUER,
        "client_id": "agent-planner",
        "expected_nonce": "browser-session-nonce",
        "now": NOW,
    }
    assert verify_id_token(token, **options) == claims
    with pytest.raises(OidcValidationError, match="nonce"):
        verify_id_token(token, **{**options, "expected_nonce": "other"})
    with pytest.raises(OidcValidationError, match="audience"):
        verify_id_token(token, **{**options, "client_id": "agent-executor"})
    with pytest.raises(OidcValidationError, match="type"):
        verify_id_token(
            sign_compact_jws(key, claims, key_id="as-sign-1", token_type="ag-at+jwt"), **options
        )


def test_pkce_uses_standard_s256_and_rejects_bad_verifier():
    verifier = "A" * 43
    assert pkce_s256_challenge(verifier) == "DwBzhbb51LfusnSGBa_hqYSgo7-j8BTQnip4TOnlzRo"
    with pytest.raises(OidcValidationError):
        pkce_s256_challenge("too-short")


def test_proof_signing_helper_interoperates_with_static_verifier():
    as_key, holder_key, _, verifier, _ = _fixture()
    body = _body()
    token = sign_compact_jws(
        as_key,
        _claims(serialize_sm2_public_key(holder_key.public_key())),
        key_id="as-sign-1",
        token_type="ag-at+jwt",
    )
    proof = sign_ag_proof(
        holder_key,
        kid=KID,
        client_id="agent-planner",
        purpose="invoke",
        endpoint=ENDPOINT,
        body=json.loads(body),
        token=token,
        now=NOW,
    )
    assert verifier.verify_static(
        token, proof, endpoint=ENDPOINT, method="POST", body=body, now=NOW
    ).proof_jti
    with pytest.raises(ProofInputError):
        sign_ag_proof(
            holder_key,
            kid=KID,
            client_id="agent-planner",
            purpose="invoke",
            endpoint="https://evil.example/path?query=1",
            body=json.loads(body),
            token=token,
            now=NOW,
        )


def _delegation_inputs():
    recipient_key = generate_sm2_private_key()
    recipient_spki = serialize_sm2_public_key(recipient_key.public_key())
    recipient_did = "did:web:identity.agent-guard.test:agents:selector"
    recipient = ResolvedIdentity(
        RegisteredIdentity(
            "tenant-001",
            "agent-selector",
            recipient_did,
            recipient_did + "#key-1",
            recipient_spki,
        ),
        recipient_key.public_key(),
    )
    parent_key = generate_sm2_private_key()
    parent = validate_access_claims(
        _claims(serialize_sm2_public_key(parent_key.public_key())), issuer=ISSUER, now=NOW
    )
    requested = {
        "audience": "https://gateway.agent-guard.test",
        "scope": "procurement.order.create",
        "ag_delegate_client_id": "agent-selector",
        "ag_amount_limit_fen": "80000",
        "ag_call_limit": "8",
        "ag_ttl_seconds": "180",
        "ag_delegation_remaining": "1",
        "ag_constraints": canonical_json_bytes(
            {
                **parent.constraints,
                "max_quantity": 1,
            }
        ).decode("utf-8"),
        "ag_delegation_key": "YWJjZGVmZ2hpamtsbW5vcA",
    }
    return parent, requested, recipient


def test_grant_policy_produces_narrow_child_spec():
    parent, requested, recipient = _delegation_inputs()
    spec = GrantPolicy(issuer=ISSUER).validate_child(parent, requested, recipient, now=NOW)
    assert spec.parent_grant_id == "grant-root"
    assert spec.recipient_client_id == "agent-selector"
    assert spec.recipient_spki_sm3 == recipient.registration.spki_sm3
    assert spec.amount_limit_fen == 80000
    assert spec.expires_at == NOW + 180
    assert json.loads(spec.constraints_json)["max_quantity"] == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("audience", "https://evil.example"),
        ("scope", "notification.template.send"),
        ("ag_delegate_client_id", "agent-executor"),
        ("ag_amount_limit_fen", "100001"),
        ("ag_call_limit", "11"),
        ("ag_ttl_seconds", "301"),
        ("ag_delegation_remaining", "2"),
        ("ag_delegation_key", "short"),
        ("ag_amount_limit_fen", "01"),
        ("ag_amount_limit_fen", "9" * 5000),
    ],
)
def test_grant_policy_rejects_expansion_and_malformed_values(field, value):
    parent, requested, recipient = _delegation_inputs()
    requested[field] = value
    with pytest.raises(DelegationError):
        GrantPolicy(issuer=ISSUER).validate_child(parent, requested, recipient, now=NOW)


def test_grant_policy_rejects_resource_expansion_and_stale_parent():
    parent, requested, recipient = _delegation_inputs()
    constraints = json.loads(requested["ag_constraints"])
    constraints["skus"].append("sku-not-approved")
    requested["ag_constraints"] = canonical_json_bytes(constraints).decode("utf-8")
    with pytest.raises(DelegationError, match="resource expansion"):
        GrantPolicy(issuer=ISSUER).validate_child(parent, requested, recipient, now=NOW)
    requested["ag_constraints"] = canonical_json_bytes(parent.constraints).decode("utf-8")
    with pytest.raises(DelegationError, match="expired"):
        GrantPolicy(issuer=ISSUER).validate_child(parent, requested, recipient, now=NOW + 201)
