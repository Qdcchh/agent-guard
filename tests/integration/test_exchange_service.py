"""Real PostgreSQL tests for AS-owned child issuance and idempotent retries."""

from __future__ import annotations

import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import psycopg
import pytest

from agent_guard.authorization.code_service import ApprovedAuthorization, AuthorizationCodeService
from agent_guard.authorization.exchange_service import TokenExchangeError, TokenExchangeService
from agent_guard.authorization.oidc import pkce_s256_challenge
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
    did_web_url,
)
from agent_guard.ledger import store
from agent_guard.ledger.provisioning import deactivate_principal, register_principal, revoke_grant
from tests.fixtures.dbstate import fetch_one

pytestmark = pytest.mark.integration

ISSUER = "https://auth.agent-guard.test"
TOKEN_ENDPOINT = ISSUER + "/oauth/token"
REDIRECT = "https://console.agent-guard.test/oauth/callback"
VERIFIER = "A" * 43
TENANT = "tenant-001"
TASK = "task-001"


def _resolver(registrations):
    """Rebuild the DID-document resolver for already registered identities."""
    documents = {}
    for registration in registrations.values():
        name = registration.client_id.removeprefix("agent-")
        document = {
            "id": registration.did,
            "verificationMethod": [
                {
                    "id": registration.kid,
                    "type": METHOD_TYPE,
                    "controller": registration.did,
                    SPKI_PROPERTY: b64url_encode(registration.spki_der),
                }
            ],
            "authentication": [registration.kid],
            "capabilityInvocation": [registration.kid],
        }
        if name != "executor":
            document["capabilityDelegation"] = [registration.kid]
        documents[did_web_url(registration.did)] = document
    return IdentityResolver(
        registrations,
        allowed_hosts=frozenset({"identity.agent-guard.test"}),
        fetch_document=lambda url: canonical_json_bytes(documents[url]),
    )


def _identities():
    keys = {name: generate_sm2_private_key() for name in ("planner", "selector", "executor")}
    registrations = {}
    for name, key in keys.items():
        did = f"did:web:identity.agent-guard.test:agents:{name}"
        kid = did + "#key-1"
        spki = serialize_sm2_public_key(key.public_key())
        registrations[(TENANT, f"agent-{name}")] = RegisteredIdentity(
            TENANT, f"agent-{name}", did, kid, spki
        )
    return keys, registrations, _resolver(registrations)


def _root(dsn):
    as_key = generate_sm2_private_key()
    keys, registrations, resolver = _identities()
    with psycopg.connect(dsn) as conn:
        for registration in registrations.values():
            register_principal(
                conn, tenant_id=TENANT, client_id=registration.client_id, kid=registration.kid
            )
    codes = AuthorizationCodeService(
        dsn,
        issuer=ISSUER,
        token_endpoint=TOKEN_ENDPOINT,
        signing_key=as_key,
        signing_kid="as-sign-1",
        identities=resolver,
    )
    exchanges = TokenExchangeService(
        dsn,
        issuer=ISSUER,
        token_endpoint=TOKEN_ENDPOINT,
        signing_key=as_key,
        signing_kid="as-sign-1",
        identities=resolver,
    )
    now = int(time.time())
    approved = ApprovedAuthorization(
        tenant_id=TENANT,
        task_id=TASK,
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
    code = codes.issue_code(approved).code
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "code_verifier": VERIFIER,
    }
    planner = registrations[(TENANT, "agent-planner")]
    proof = sign_ag_proof(
        keys["planner"],
        kid=planner.kid,
        client_id="agent-planner",
        purpose="code-exchange",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=None,
        now=int(time.time()),
    )
    root = codes.redeem(
        raw_form=urlencode(form).encode("ascii"),
        proof=proof,
        authenticated_client_id="agent-planner",
        tenant_id=TENANT,
        expected_redirect_uri=REDIRECT,
    )
    return as_key, keys, registrations, exchanges, root


def _form(as_key, token, *, recipient="selector", delegation_key=None, ttl=180):
    parent = verify_compact_jws(
        token, expected_type="ag-at+jwt", trusted_keys={"as-sign-1": as_key.public_key()}
    )
    return {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "audience": "https://gateway.agent-guard.test",
        "scope": "procurement.order.create",
        "ag_delegate_client_id": f"agent-{recipient}",
        "ag_amount_limit_fen": "80000" if recipient == "selector" else "70000",
        "ag_call_limit": "8" if recipient == "selector" else "7",
        "ag_ttl_seconds": str(ttl),
        "ag_delegation_remaining": str(parent["ag_delegation_remaining"] - 1),
        "ag_constraints": canonical_json_bytes(parent["ag_constraints"]).decode("utf-8"),
        "ag_delegation_key": delegation_key or secrets.token_urlsafe(16),
    }


def _exchange(service, keys, registrations, form, *, holder="planner", proof=None):
    registration = registrations[(TENANT, f"agent-{holder}")]
    if proof is None:
        proof = sign_ag_proof(
            keys[holder],
            kid=registration.kid,
            client_id=f"agent-{holder}",
            purpose="delegate",
            endpoint=TOKEN_ENDPOINT,
            body=form,
            token=form["subject_token"],
            now=int(time.time()),
        )
    return service.exchange(
        raw_form=urlencode(form).encode("ascii"),
        proof=proof,
        authenticated_client_id=f"agent-{holder}",
    )


def test_two_levels_are_as_signed_and_idempotent(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    first_form = _form(as_key, root.access_token)
    first = _exchange(service, keys, registrations, first_form)
    retry = _exchange(service, keys, registrations, first_form)
    assert retry.access_token == first.access_token
    assert retry.ag_grant_id == first.ag_grant_id
    assert retry.expires_in <= first.expires_in
    second = _exchange(
        service,
        keys,
        registrations,
        _form(as_key, first.access_token, recipient="executor", ttl=100),
        holder="selector",
    )
    claims = verify_compact_jws(
        second.access_token,
        expected_type="ag-at+jwt",
        trusted_keys={"as-sign-1": as_key.public_key()},
    )
    assert claims["ag_parent_id"] == first.ag_grant_id
    assert claims["ag_root_id"] == root.ag_grant_id
    assert claims["ag_delegation_remaining"] == 0
    assert claims["client_id"] == "agent-executor"
    assert claims["act"]["act"]["act"]["sub"].endswith(":planner")
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (3,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grant_tokens") == (3,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (2,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_exchange_evidence") == (3,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_proofs") == (4,)


def test_conflicting_intent_and_stolen_token_are_rejected(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    _exchange(service, keys, registrations, form)
    changed = dict(form, ag_amount_limit_fen="70000")
    with pytest.raises(TokenExchangeError, match="DELEGATION_KEY_CONFLICT"):
        _exchange(service, keys, registrations, changed)
    with pytest.raises(TokenExchangeError, match="SUBJECT_OR_PROOF_INVALID"):
        _exchange(service, keys, registrations, form, holder="selector")
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (1,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_proofs") == (2,)


def test_first_issuance_rejects_expansion_and_revoked_parent(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    expanded = dict(form, ag_amount_limit_fen="100001")
    with pytest.raises(TokenExchangeError, match="DELEGATION_INVALID"):
        _exchange(service, keys, registrations, expanded)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (0,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_proofs") == (1,)
    with psycopg.connect(dsn) as conn:
        revoke_grant(conn, root.ag_grant_id)
    with pytest.raises(TokenExchangeError, match="REVOKED"):
        _exchange(service, keys, registrations, form)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (1,)


def test_proof_replay_is_distinct_from_delegation_retry(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    registration = registrations[(TENANT, "agent-planner")]
    proof = sign_ag_proof(
        keys["planner"],
        kid=registration.kid,
        client_id="agent-planner",
        purpose="delegate",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=root.access_token,
        now=int(time.time()),
    )
    _exchange(service, keys, registrations, form, proof=proof)
    with pytest.raises(TokenExchangeError, match="PROOF_REPLAY"):
        _exchange(service, keys, registrations, form, proof=proof)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (1,)


def test_revocation_and_key_deactivation_block_retries(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    first = _exchange(service, keys, registrations, form)
    with psycopg.connect(dsn) as conn:
        revoke_grant(conn, first.ag_grant_id)
    with pytest.raises(TokenExchangeError, match="CHILD_INACTIVE"):
        _exchange(service, keys, registrations, form)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (2,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_exchange_evidence") == (1,)
    with psycopg.connect(dsn) as conn:
        deactivate_principal(
            conn,
            tenant_id=TENANT,
            client_id="agent-selector",
            kid=registrations[(TENANT, "agent-selector")].kid,
        )
    with pytest.raises(TokenExchangeError, match="CLIENT_KEY_INVALID"):
        _exchange(service, keys, registrations, form)


def test_concurrent_same_key_returns_one_child(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_exchange, service, keys, registrations, form) for _ in range(2)]
        results = [future.result() for future in futures]
    assert results[0].access_token == results[1].access_token
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (2,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (1,)


def test_expired_child_cannot_be_revived_by_retry(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token, ttl=2)
    issued = _exchange(service, keys, registrations, form)
    payload = verify_compact_jws(
        issued.access_token,
        expected_type="ag-at+jwt",
        trusted_keys={"as-sign-1": as_key.public_key()},
    )
    time.sleep(max(0, payload["exp"] - time.time() + 0.2))
    with pytest.raises(TokenExchangeError, match="CHILD_INACTIVE"):
        _exchange(service, keys, registrations, form)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (2,)


def test_proof_expiring_while_waiting_for_task_lock_is_rejected(ledger, dsn, monkeypatch):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    issued_at = int(time.time())
    proof = sign_ag_proof(
        keys["planner"],
        kid=registrations[(TENANT, "agent-planner")].kid,
        client_id="agent-planner",
        purpose="delegate",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=root.access_token,
        now=issued_at,
        lifetime_seconds=5,
    )
    waiting = threading.Event()
    original_lock_task = store.lock_task

    def observed_lock_task(conn, tenant_id, task_id):
        waiting.set()
        return original_lock_task(conn, tenant_id, task_id)

    monkeypatch.setattr(store, "lock_task", observed_lock_task)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with psycopg.connect(dsn) as blocker:
            with blocker.transaction():
                blocker.execute(
                    "SELECT root_grant_id FROM ag_tasks WHERE tenant_id = %s AND task_id = %s "
                    "FOR UPDATE",
                    (TENANT, TASK),
                )
                future = pool.submit(_exchange, service, keys, registrations, form, proof=proof)
                assert waiting.wait(timeout=5), "exchange did not reach task lock"
                time.sleep(max(0, issued_at + 5 - time.time() + 0.2))
        with pytest.raises(TokenExchangeError, match="PROOF_EXPIRED"):
            future.result()
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (0,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_proofs") == (1,)
