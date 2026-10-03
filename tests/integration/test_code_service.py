"""Real PostgreSQL authorization-code consumption and unique-root tests."""

from __future__ import annotations

import secrets
import time
from urllib.parse import urlencode

import psycopg
import pytest

from agent_guard.authorization.claims import validate_access_claims
from agent_guard.authorization.code_service import (
    ApprovedAuthorization,
    AuthorizationCodeError,
    AuthorizationCodeService,
)
from agent_guard.authorization.oidc import pkce_s256_challenge, verify_id_token
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from agent_guard.crypto.sm import (
    generate_sm2_private_key,
    serialize_sm2_public_key,
    verify_compact_jws,
)
from agent_guard.identity.resolver import (
    METHOD_TYPE,
    SPKI_PROPERTY,
    IdentityResolver,
    RegisteredIdentity,
)
from agent_guard.ledger.provisioning import deactivate_principal, register_principal
from tests.fixtures.dbstate import fetch_one

pytestmark = pytest.mark.integration

ISSUER = "https://auth.agent-guard.test"
TOKEN_ENDPOINT = ISSUER + "/oauth/token"
REDIRECT = "https://console.agent-guard.test/oauth/callback"
DID = "did:web:identity.agent-guard.test:agents:planner"
KID = DID + "#key-1"
VERIFIER = "A" * 43


def _setup(dsn):
    as_key = generate_sm2_private_key()
    planner_key = generate_sm2_private_key()
    spki = serialize_sm2_public_key(planner_key.public_key())
    document = {
        "id": DID,
        "verificationMethod": [
            {"id": KID, "type": METHOD_TYPE, "controller": DID, SPKI_PROPERTY: b64url_encode(spki)}
        ],
        "authentication": [KID],
        "capabilityInvocation": [KID],
        "capabilityDelegation": [KID],
    }
    resolver = IdentityResolver(
        {
            ("tenant-001", "agent-planner"): RegisteredIdentity(
                "tenant-001", "agent-planner", DID, KID, spki
            )
        },
        allowed_hosts=frozenset({"identity.agent-guard.test"}),
        fetch_document=lambda url: canonical_json_bytes(document),
    )
    service = AuthorizationCodeService(
        dsn,
        issuer=ISSUER,
        token_endpoint=TOKEN_ENDPOINT,
        signing_key=as_key,
        signing_kid="as-sign-1",
        identities=resolver,
    )
    with psycopg.connect(dsn) as conn:
        register_principal(conn, tenant_id="tenant-001", client_id="agent-planner", kid=KID)
    return service, as_key, planner_key


def _approved(now):
    return ApprovedAuthorization(
        tenant_id="tenant-001",
        task_id="task-001",
        subject="user-001",
        client_id="agent-planner",
        redirect_uri=REDIRECT,
        pkce_challenge=pkce_s256_challenge(VERIFIER),
        scope="openid procurement.order.create",
        constraints={
            "request_ids": ["req-001"],
            "document_ids": [],
            "quote_versions": ["quote-001@1"],
            "skus": ["sku-001"],
            "max_quantity": 2,
            "delivery_ids": ["office-001"],
            "template_ids": [],
            "recipient_ids": [],
        },
        amount_limit_fen=100000,
        call_limit=10,
        task_expires_at=now + 240,
        auth_time=now - 10,
        nonce=secrets.token_urlsafe(16),
        consent_ref="consent-001",
    )


def _redeem(service, planner_key, code, *, verifier=VERIFIER, proof_lifetime=60):
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "code_verifier": verifier,
    }
    proof = sign_ag_proof(
        planner_key,
        kid=KID,
        client_id="agent-planner",
        purpose="code-exchange",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=None,
        now=int(time.time()),
        lifetime_seconds=proof_lifetime,
    )
    return service.redeem(
        raw_form=urlencode(form).encode("ascii"),
        proof=proof,
        authenticated_client_id="agent-planner",
        tenant_id="tenant-001",
        expected_redirect_uri=REDIRECT,
    )


def test_code_is_one_use_and_signs_root_and_id_token(ledger, dsn):
    service, as_key, planner_key = _setup(dsn)
    approved = _approved(int(time.time()))
    code = service.issue_code(approved).code
    issued = _redeem(service, planner_key, code)
    assert issued.token_type == "AGPoP"
    assert issued.expires_in <= 300
    claims = verify_compact_jws(
        issued.access_token,
        expected_type="ag-at+jwt",
        trusted_keys={"as-sign-1": as_key.public_key()},
    )
    assert validate_access_claims(claims, issuer=ISSUER, now=int(time.time())).raw[
        "ag_grant_id"
    ] == (issued.ag_grant_id)
    assert claims["ag_parent_id"] is None
    assert claims["ag_cnf"]["kid"] == KID
    assert (
        verify_id_token(
            issued.id_token,
            trusted_keys={"as-sign-1": as_key.public_key()},
            issuer=ISSUER,
            client_id="agent-planner",
            expected_nonce=approved.nonce,
            now=int(time.time()),
        )["sub"]
        == "user-001"
    )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_tasks") == (1,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (1,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grant_tokens") == (1,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_proofs") == (1,)
    with pytest.raises(AuthorizationCodeError, match="CODE_OR_PKCE_INVALID"):
        _redeem(service, planner_key, code)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (1,)


def test_two_codes_for_one_task_cannot_create_two_roots(ledger, dsn):
    service, _, planner_key = _setup(dsn)
    approved = _approved(int(time.time()))
    first = service.issue_code(approved).code
    second = service.issue_code(approved).code
    _redeem(service, planner_key, first)
    with pytest.raises(AuthorizationCodeError, match="TASK_ALREADY_AUTHORIZED"):
        _redeem(service, planner_key, second)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_tasks") == (1,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (1,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_auth_evidence") == (1,)


def test_wrong_pkce_and_deactivated_key_do_not_consume_code(ledger, dsn):
    service, _, planner_key = _setup(dsn)
    code = service.issue_code(_approved(int(time.time()))).code
    with pytest.raises(AuthorizationCodeError, match="CODE_OR_PKCE_INVALID"):
        _redeem(service, planner_key, code, verifier="B" * 43)
    assert fetch_one(dsn, "SELECT consumed_at FROM ag_authorization_codes") == (None,)
    with psycopg.connect(dsn) as conn:
        deactivate_principal(conn, tenant_id="tenant-001", client_id="agent-planner", kid=KID)
    with pytest.raises(AuthorizationCodeError, match="CLIENT_KEY_INVALID"):
        _redeem(service, planner_key, code)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_tasks") == (0,)


@pytest.mark.parametrize("round_id", range(10))
def test_two_codes_one_task_real_principal_lock_race(ledger, dsn, round_id):
    from tests.integration.test_exchange_service import locked_race

    service, _, key = _setup(dsn)
    first = service.issue_code(_approved(int(time.time()))).code
    second = service.issue_code(_approved(int(time.time()))).code
    results = locked_race(
        dsn, lambda: _redeem(service, key, first), lambda: _redeem(service, key, second)
    )
    errors = [r for r in results if isinstance(r, AuthorizationCodeError)]
    assert len(errors) == 1 and errors[0].code == "TASK_ALREADY_AUTHORIZED"
    assert fetch_one(dsn, "SELECT count(*) FROM ag_tasks") == (1,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (1,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_auth_evidence") == (1,)
    assert fetch_one(
        dsn, "SELECT count(*) FROM ag_authorization_codes WHERE consumed_at IS NOT NULL"
    ) == (1,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_proofs") == (1,)


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("deferred", [False, True])
@pytest.mark.parametrize("positive", [False, True])
def test_code_final_proof_after_late_write(ledger, dsn, round_id, deferred, positive):
    from tests.integration.test_exchange_service import late_issuance_wait

    service, _, key = _setup(dsn)
    code = service.issue_code(_approved(int(time.time()))).code
    late_issuance_wait(
        dsn,
        lambda: _redeem(service, key, code, proof_lifetime=1),
        table="ag_authorization_codes",
        action="UPDATE",
        deferred=deferred,
        positive=positive,
        error_type=AuthorizationCodeError,
    )
    if not positive:
        assert fetch_one(dsn, "SELECT count(*) FROM ag_tasks") == (0,)
        assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (0,)
        assert fetch_one(dsn, "SELECT count(*) FROM ag_auth_evidence") == (0,)
        assert fetch_one(dsn, "SELECT count(*) FROM ag_proofs") == (0,)
        assert fetch_one(dsn, "SELECT consumed_at FROM ag_authorization_codes") == (None,)
        assert _redeem(service, key, code).ag_grant_id
