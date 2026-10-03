"""HTTP token adapter: Basic authentication, strict headers and dispatch."""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import urlencode

from agent_guard.authorization.code_service import AuthorizationCodeError, CodeRedeemResult
from agent_guard.authorization.exchange import TOKEN_EXCHANGE_GRANT
from agent_guard.authorization.exchange_service import TokenExchangeError, TokenExchangeResult
from agent_guard.authorization.token_endpoint import TokenClient, TokenEndpoint
from agent_guard.contracts.encoding import load_strict_json

CLIENT = "agent-planner"
SECRET = b"test-only-synthetic-client-secret-32-bytes"
REDIRECT = "https://console.agent-guard.test/oauth/callback"


class FakeCodes:
    def __init__(self):
        self.calls = []
        self.error = None

    def redeem(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise AuthorizationCodeError(self.error)
        return CodeRedeemResult("at", "id", "AGPoP", 300, "openid", "grant-root", "task-1")


class FakeExchanges:
    def __init__(self):
        self.calls = []
        self.error = None

    def exchange(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise TokenExchangeError(self.error)
        return TokenExchangeResult(
            "at-child",
            "urn:ietf:params:oauth:token-type:access_token",
            "AGPoP",
            180,
            "procurement.order.create",
            "grant-child",
            "grant-root",
            "grant-root",
        )


def _auth(secret=SECRET):
    return "Basic " + base64.b64encode(CLIENT.encode("ascii") + b":" + secret).decode("ascii")


def _fixture():
    codes, exchanges = FakeCodes(), FakeExchanges()
    endpoint = TokenEndpoint(
        clients={
            CLIENT: TokenClient(CLIENT, "tenant-1", REDIRECT, hashlib.sha256(SECRET).digest())
        },
        codes=codes,
        exchanges=exchanges,
    )
    return endpoint, codes, exchanges


def _request(endpoint, form, *, auth=None, proofs=("signed-proof",), content_type=None):
    return endpoint.handle(
        content_type=content_type or "application/x-www-form-urlencoded",
        raw_form=urlencode(form).encode("ascii"),
        authorization_headers=(_auth(),) if auth is None else auth,
        proof_headers=proofs,
    )


def test_code_and_exchange_dispatch_with_no_store():
    endpoint, codes, exchanges = _fixture()
    code_form = {
        "grant_type": "authorization_code",
        "code": "abc",
        "redirect_uri": REDIRECT,
        "code_verifier": "verifier",
    }
    issued = _request(endpoint, code_form)
    assert issued.status == 200
    assert issued.headers["Cache-Control"] == "no-store"
    assert issued.headers["Pragma"] == "no-cache"
    assert load_strict_json(issued.body)["ag_grant_id"] == "grant-root"
    assert codes.calls[0]["authenticated_client_id"] == CLIENT
    assert codes.calls[0]["tenant_id"] == "tenant-1"
    assert codes.calls[0]["expected_redirect_uri"] == REDIRECT

    delegated = _request(endpoint, {"grant_type": TOKEN_EXCHANGE_GRANT})
    assert delegated.status == 200
    assert load_strict_json(delegated.body)["ag_grant_id"] == "grant-child"
    assert exchanges.calls[0]["authenticated_client_id"] == CLIENT


def test_invalid_basic_and_duplicate_headers_never_reach_services():
    endpoint, codes, exchanges = _fixture()
    form = {"grant_type": "authorization_code"}
    for auth in (
        (),
        (_auth(), _auth()),
        (_auth(b"wrong-secret"),),
        ("Bearer abc",),
        ("Basic !!!",),
    ):
        response = _request(endpoint, form, auth=auth)
        assert response.status == 401
        assert load_strict_json(response.body)["error"] == "invalid_client"
        assert response.headers["WWW-Authenticate"].startswith("Basic ")
    assert not codes.calls and not exchanges.calls


def test_duplicate_proof_bad_content_type_and_unsupported_grant_rejected():
    endpoint, codes, exchanges = _fixture()
    form = {"grant_type": "authorization_code"}
    for kwargs in (
        {"proofs": ()},
        {"proofs": ("a", "b")},
        {"content_type": "application/json"},
    ):
        assert _request(endpoint, form, **kwargs).status == 400
    assert (
        load_strict_json(_request(endpoint, {"grant_type": "password"}).body)["error"]
        == "unsupported_grant_type"
    )
    assert not codes.calls and not exchanges.calls


def test_service_errors_have_oauth_shape_without_reflecting_request():
    endpoint, codes, exchanges = _fixture()
    codes.error = "CODE_OR_PKCE_INVALID"
    response = _request(endpoint, {"grant_type": "authorization_code", "code": "secret-code"})
    assert response.status == 400
    assert load_strict_json(response.body) == {
        "error": "invalid_grant",
        "ag_error": "CODE_OR_PKCE_INVALID",
    }
    assert b"secret-code" not in response.body
    exchanges.error = "TRUSTED_STATE_UNAVAILABLE"
    unavailable = _request(endpoint, {"grant_type": TOKEN_EXCHANGE_GRANT})
    assert unavailable.status == 503
    assert load_strict_json(unavailable.body)["error"] == "temporarily_unavailable"


def test_duplicate_form_field_rejected_before_dispatch():
    endpoint, codes, exchanges = _fixture()
    response = endpoint.handle(
        content_type="application/x-www-form-urlencoded",
        raw_form=b"grant_type=authorization_code&grant_type=password",
        authorization_headers=(_auth(),),
        proof_headers=("signed-proof",),
    )
    assert response.status == 400
    assert not codes.calls and not exchanges.calls
