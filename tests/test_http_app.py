"""Raw ASGI header and body handling for AS public/token/introspection routes."""

from __future__ import annotations

import asyncio
import base64
import hashlib

from agent_guard.authorization.discovery import DiscoveryEndpoint
from agent_guard.authorization.http_app import AuthorizationHttpApp
from agent_guard.authorization.introspection_endpoint import IntrospectionEndpoint
from agent_guard.authorization.token_endpoint import TokenClient, TokenEndpoint
from agent_guard.contracts.encoding import load_strict_json
from agent_guard.crypto.sm import generate_sm2_private_key
from tests.test_introspection_endpoint import FakeInspector
from tests.test_token_endpoint import FakeCodes, FakeExchanges

SECRET = b"synthetic-test-only-asgi-client-secret-32-bytes"
GATEWAY_SECRET = b"synthetic-test-only-asgi-gateway-secret-32-bytes"


def _basic(client_id, secret):
    return b"Basic " + base64.b64encode(client_id.encode("ascii") + b":" + secret)


def _app():
    codes, exchanges, inspector = FakeCodes(), FakeExchanges(), FakeInspector()
    app = AuthorizationHttpApp(
        discovery=DiscoveryEndpoint(
            issuer="https://auth.agent-guard.test",
            signing_keys={"as-sign-1": generate_sm2_private_key().public_key()},
        ),
        token=TokenEndpoint(
            clients={
                "agent-planner": TokenClient(
                    "agent-planner",
                    "tenant-001",
                    "https://console.agent-guard.test/oauth/callback",
                    hashlib.sha256(SECRET).digest(),
                )
            },
            codes=codes,
            exchanges=exchanges,
        ),
        introspection=IntrospectionEndpoint(
            gateway_client=TokenClient(
                "gateway-introspect", "service", None, hashlib.sha256(GATEWAY_SECRET).digest()
            ),
            inspector=inspector,
        ),
    )
    return app, codes, inspector


def _request(app, *, path, method="POST", scheme="https", headers=None, body=b"", query=b""):
    events = [{"type": "http.request", "body": body, "more_body": False}]
    sent = []

    async def receive():
        return events.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "scheme": scheme,
                "path": path,
                "method": method,
                "query_string": query,
                "headers": headers or [],
            },
            receive,
            send,
        )
    )
    assert sent[0]["type"] == "http.response.start"
    assert sent[1]["type"] == "http.response.body"
    return sent[0]["status"], load_strict_json(sent[1]["body"]), sent[0]["headers"]


def test_token_route_preserves_duplicate_auth_and_proof_headers():
    app, codes, _ = _app()
    form = b"grant_type=authorization_code"
    headers = [
        (b"content-type", b"application/x-www-form-urlencoded"),
        (b"authorization", _basic("agent-planner", SECRET)),
        (b"ag-proof", b"synthetic-proof"),
    ]
    status, body, _ = _request(app, path="/oauth/token", headers=headers, body=form)
    assert status == 200
    assert body["ag_grant_id"] == "grant-root"
    assert len(codes.calls) == 1
    status, _, _ = _request(app, path="/oauth/token", headers=headers + [headers[1]], body=form)
    assert status == 401
    status, _, _ = _request(app, path="/oauth/token", headers=headers + [headers[2]], body=form)
    assert status == 400
    assert len(codes.calls) == 1


def test_gateway_introspection_and_public_discovery():
    app, _, inspector = _app()
    headers = [
        (b"content-type", b"application/x-www-form-urlencoded"),
        (b"authorization", _basic("gateway-introspect", GATEWAY_SECRET)),
    ]
    status, body, _ = _request(
        app,
        path="/oauth/introspect",
        headers=headers,
        body=b"token=unknown&token_type_hint=access_token",
    )
    assert status == 200
    assert body == {"active": False}
    assert inspector.tokens == ["unknown"]
    status, body, _ = _request(app, path="/.well-known/openid-configuration", method="GET")
    assert status == 200
    assert body["ag_profile"] == "GM-MVP-1"
    status, body, _ = _request(app, path="/ag/keys", method="GET")
    assert status == 200
    assert body["keys"][0]["kid"] == "as-sign-1"


def test_insecure_oversized_or_ambiguous_requests_fail_closed():
    app, codes, _ = _app()
    headers = [
        (b"content-type", b"application/x-www-form-urlencoded"),
        (b"authorization", _basic("agent-planner", SECRET)),
        (b"ag-proof", b"synthetic-proof"),
    ]
    assert _request(app, path="/oauth/token", scheme="http", headers=headers)[0] == 403
    assert _request(app, path="/oauth/token", headers=headers, query=b"code=secret")[0] == 400
    assert _request(app, path="/oauth/token", headers=headers, body=b"x" * 65537)[0] == 400
    assert _request(app, path="/oauth/token", headers=headers + [headers[0]])[0] == 400
    assert _request(app, path="/oauth/token", method="GET")[0] == 405
    assert _request(app, path="/unknown")[0] == 404
    assert codes.calls == []
