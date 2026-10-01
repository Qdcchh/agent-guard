"""Token Exchange form, parent holder proof and child preflight tests."""

from urllib.parse import urlencode

import pytest

from agent_guard.authorization.exchange import (
    ACCESS_TOKEN_TYPE,
    TOKEN_EXCHANGE_GRANT,
    ExchangeError,
    ExchangePreflight,
)
from agent_guard.authorization.forms import FormError, decode_oauth_form
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from agent_guard.crypto.sm import (
    generate_sm2_private_key,
    serialize_sm2_public_key,
    sign_compact_jws,
)
from agent_guard.identity.resolver import (
    METHOD_TYPE,
    SPKI_PROPERTY,
    IdentityResolver,
    RegisteredIdentity,
)
from tests.test_authorization import DID, ISSUER, KID, NOW, _claims

TOKEN_ENDPOINT = ISSUER + "/oauth/token"
SELECTOR_DID = "did:web:identity.agent-guard.test:agents:selector"


def _document(did: str, kid: str, spki: bytes, *, delegating: bool) -> dict:
    result = {
        "id": did,
        "verificationMethod": [
            {
                "id": kid,
                "type": METHOD_TYPE,
                "controller": did,
                SPKI_PROPERTY: b64url_encode(spki),
            }
        ],
        "authentication": [kid],
        "capabilityInvocation": [kid],
    }
    if delegating:
        result["capabilityDelegation"] = [kid]
    return result


def _fixture():
    as_key = generate_sm2_private_key()
    planner_key = generate_sm2_private_key()
    selector_key = generate_sm2_private_key()
    planner_spki = serialize_sm2_public_key(planner_key.public_key())
    selector_spki = serialize_sm2_public_key(selector_key.public_key())
    selector_kid = SELECTOR_DID + "#key-1"
    documents = {
        "https://identity.agent-guard.test/agents/planner/did.json": _document(
            DID, KID, planner_spki, delegating=True
        ),
        "https://identity.agent-guard.test/agents/selector/did.json": _document(
            SELECTOR_DID, selector_kid, selector_spki, delegating=True
        ),
    }
    registrations = {
        ("tenant-001", "agent-planner"): RegisteredIdentity(
            "tenant-001", "agent-planner", DID, KID, planner_spki
        ),
        ("tenant-001", "agent-selector"): RegisteredIdentity(
            "tenant-001", "agent-selector", SELECTOR_DID, selector_kid, selector_spki
        ),
    }
    resolver = IdentityResolver(
        registrations,
        allowed_hosts=frozenset({"identity.agent-guard.test"}),
        fetch_document=lambda url: canonical_json_bytes(documents[url]),
    )
    preflight = ExchangePreflight(
        issuer=ISSUER,
        token_endpoint=TOKEN_ENDPOINT,
        as_keys={"as-sign-1": as_key.public_key()},
        identities=resolver,
    )
    parent = _claims(planner_spki)
    token = sign_compact_jws(as_key, parent, key_id="as-sign-1", token_type="ag-at+jwt")
    form = {
        "grant_type": TOKEN_EXCHANGE_GRANT,
        "subject_token": token,
        "subject_token_type": ACCESS_TOKEN_TYPE,
        "requested_token_type": ACCESS_TOKEN_TYPE,
        "audience": "https://gateway.agent-guard.test",
        "scope": "procurement.order.create",
        "ag_delegate_client_id": "agent-selector",
        "ag_amount_limit_fen": "80000",
        "ag_call_limit": "8",
        "ag_ttl_seconds": "180",
        "ag_delegation_remaining": "1",
        "ag_constraints": canonical_json_bytes(parent["ag_constraints"]).decode("utf-8"),
        "ag_delegation_key": "YWJjZGVmZ2hpamtsbW5vcA",
    }
    return planner_key, documents, preflight, form


def _proof(planner_key, form):
    return sign_ag_proof(
        planner_key,
        kid=KID,
        client_id="agent-planner",
        purpose="delegate",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=form["subject_token"],
        now=NOW,
    )


def test_exchange_preflight_binds_basic_parent_proof_and_child():
    planner_key, _, preflight, form = _fixture()
    result = preflight.verify(
        raw_form=urlencode(form).encode("ascii"),
        proof=_proof(planner_key, form),
        authenticated_client_id="agent-planner",
        now=NOW,
    )
    assert result.parent.raw["ag_grant_id"] == "grant-root"
    assert result.child.recipient_client_id == "agent-selector"
    assert result.child.amount_limit_fen == 80000
    assert result.child.expires_at == NOW + 180


def test_exchange_preflight_rejects_stolen_token_and_changed_form():
    planner_key, _, preflight, form = _fixture()
    proof = _proof(planner_key, form)
    raw_form = urlencode(form).encode("ascii")
    with pytest.raises(ExchangeError, match="Basic"):
        preflight.verify(
            raw_form=raw_form, proof=proof, authenticated_client_id="agent-selector", now=NOW
        )
    form["ag_amount_limit_fen"] = "70000"
    with pytest.raises(ExchangeError):
        preflight.verify(
            raw_form=urlencode(form).encode("ascii"),
            proof=proof,
            authenticated_client_id="agent-planner",
            now=NOW,
        )


def test_exchange_preflight_rejects_wrong_key_and_missing_did_purpose():
    planner_key, documents, preflight, form = _fixture()
    wrong_proof = _proof(generate_sm2_private_key(), form)
    with pytest.raises(ExchangeError):
        preflight.verify(
            raw_form=urlencode(form).encode("ascii"),
            proof=wrong_proof,
            authenticated_client_id="agent-planner",
            now=NOW,
        )
    documents["https://identity.agent-guard.test/agents/planner/did.json"].pop(
        "capabilityDelegation"
    )
    with pytest.raises(ExchangeError):
        preflight.verify(
            raw_form=urlencode(form).encode("ascii"),
            proof=_proof(planner_key, form),
            authenticated_client_id="agent-planner",
            now=NOW,
        )


@pytest.mark.parametrize(
    "raw",
    [
        b"a=1&a=2",
        b"a=1&%61=2",
        b"a=%GG",
        b"a=%FF",
        b"a=1&&b=2",
        b"a=1=2",
    ],
)
def test_form_decoder_rejects_ambiguity(raw):
    with pytest.raises(FormError):
        decode_oauth_form(raw)


def test_form_decoder_normalizes_percent_encoding_and_spaces():
    assert decode_oauth_form(b"scope=one+two&note=%E4%B8%AD%E6%96%87") == {
        "scope": "one two",
        "note": "中文",
    }
