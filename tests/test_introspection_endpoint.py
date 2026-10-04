"""Gateway-only introspection request boundary tests."""

from __future__ import annotations

import base64
import hashlib

from agent_guard.authorization.introspection import IntrospectionError, IntrospectionResult
from agent_guard.authorization.introspection_endpoint import IntrospectionEndpoint
from agent_guard.authorization.token_endpoint import TokenClient
from agent_guard.contracts.encoding import load_strict_json

SERVICE = "gateway-introspect"
SECRET = b"synthetic-test-only-independent-gateway-secret"


class FakeInspector:
    def __init__(self):
        self.tokens = []
        self.unavailable = False

    def inspect(self, token):
        self.tokens.append(token)
        if self.unavailable:
            raise IntrospectionError("unavailable")
        return IntrospectionResult(False)


def _basic(secret=SECRET, client_id=SERVICE):
    return "Basic " + base64.b64encode(client_id.encode("ascii") + b":" + secret).decode("ascii")


def _endpoint():
    inspector = FakeInspector()
    endpoint = IntrospectionEndpoint(
        gateway_client=TokenClient(SERVICE, "service", None, hashlib.sha256(SECRET).digest()),
        inspector=inspector,
    )
    return endpoint, inspector


def _request(endpoint, *, auth=None, body=b"token=abc&token_type_hint=access_token", ctype=None):
    return endpoint.handle(
        content_type=ctype or "application/x-www-form-urlencoded",
        raw_form=body,
        authorization_headers=(_basic(),) if auth is None else auth,
    )


def test_only_gateway_basic_can_inspect():
    endpoint, inspector = _endpoint()
    for auth in (
        (),
        (_basic(), _basic()),
        (_basic(b"wrong"),),
        (_basic(client_id="agent-planner"),),
    ):
        result = _request(endpoint, auth=auth)
        assert result.status == 401
        assert result.headers["WWW-Authenticate"] == 'Basic realm="agent-guard-gateway"'
    assert inspector.tokens == []
    result = _request(endpoint)
    assert result.status == 200
    assert result.headers["Cache-Control"] == "no-store"
    assert load_strict_json(result.body) == {"active": False}
    assert inspector.tokens == ["abc"]


def test_strict_form_and_unavailable_state():
    endpoint, inspector = _endpoint()
    for body in (
        b"token=abc&token=def&token_type_hint=access_token",
        b"token=abc&token_type_hint=refresh_token",
        b"token=abc",
        b"token=abc&token_type_hint=access_token&client_id=x",
    ):
        assert _request(endpoint, body=body).status == 400
    assert _request(endpoint, ctype="application/json").status == 400
    assert inspector.tokens == []
    inspector.unavailable = True
    unavailable = _request(endpoint)
    assert unavailable.status == 503
    assert load_strict_json(unavailable.body) == {"error": "temporarily_unavailable"}
