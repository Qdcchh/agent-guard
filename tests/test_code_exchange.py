"""Authorization-code preflight tests; code consumption remains a DB concern."""

from urllib.parse import urlencode

import pytest

from agent_guard.authorization.code import CodeExchangeError, CodeExchangePreflight
from agent_guard.authorization.oidc import pkce_s256_challenge
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.crypto.sm import generate_sm2_private_key
from tests.test_authorization import KID, NOW
from tests.test_exchange import TOKEN_ENDPOINT, _fixture

REDIRECT = "https://console.agent-guard.test/oauth/callback"


def _code_fixture():
    planner_key, _, exchange, _ = _fixture()
    preflight = CodeExchangePreflight(
        token_endpoint=TOKEN_ENDPOINT, identities=exchange._identities
    )
    form = {
        "grant_type": "authorization_code",
        "code": "YWJjZGVmZ2hpamtsbW5vcA",
        "redirect_uri": REDIRECT,
        "code_verifier": "A" * 43,
    }
    proof = sign_ag_proof(
        planner_key,
        kid=KID,
        client_id="agent-planner",
        purpose="code-exchange",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=None,
        now=NOW,
    )
    return preflight, form, proof


def _verify(preflight, form, proof, **overrides):
    options = {
        "raw_form": urlencode(form).encode("ascii"),
        "proof": proof,
        "authenticated_client_id": "agent-planner",
        "tenant_id": "tenant-001",
        "expected_redirect_uri": REDIRECT,
        "now": NOW,
    }
    return preflight.verify(**{**options, **overrides})


def test_code_exchange_preflight_binds_client_key_redirect_and_pkce():
    preflight, form, proof = _code_fixture()
    result = _verify(preflight, form, proof)
    assert result.client_id == "agent-planner"
    assert result.pkce_challenge == pkce_s256_challenge("A" * 43)
    assert len(result.code_sha256) == 32
    assert result.proof_jti


def test_code_exchange_preflight_rejects_redirect_form_and_wrong_proof():
    preflight, form, proof = _code_fixture()
    with pytest.raises(CodeExchangeError, match="redirect"):
        _verify(preflight, form, proof, expected_redirect_uri="https://other.example/callback")
    form["code"] = "short"
    with pytest.raises(CodeExchangeError):
        _verify(preflight, form, proof)
    form["code"] = "YWJjZGVmZ2hpamtsbW5vcA"
    wrong_proof = sign_ag_proof(
        generate_sm2_private_key(),
        kid=KID,
        client_id="agent-planner",
        purpose="code-exchange",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=None,
        now=NOW,
    )
    with pytest.raises(CodeExchangeError):
        _verify(preflight, form, wrong_proof)
    with pytest.raises(CodeExchangeError):
        _verify(
            preflight,
            form,
            proof,
            raw_form=urlencode(form).encode("ascii") + b"&code=duplicate",
        )


def test_code_exchange_preflight_rejects_proof_after_expiry():
    preflight, form, proof = _code_fixture()
    with pytest.raises(CodeExchangeError):
        _verify(preflight, form, proof, now=NOW + 61)
