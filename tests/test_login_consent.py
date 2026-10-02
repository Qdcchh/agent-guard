"""Browser login/consent boundary and password KDF unit tests (no database)."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

import pytest

from agent_guard.authorization.browser import BrowserLoginApp
from agent_guard.authorization.consent import (
    AuthorizeRequestView,
    ConsentError,
    ConsentRedirect,
    parse_authorize_params,
)
from agent_guard.authorization.discovery import DiscoveryEndpoint
from agent_guard.authorization.http_app import AuthorizationHttpApp
from agent_guard.authorization.introspection_endpoint import IntrospectionEndpoint
from agent_guard.authorization.login import LoginError, LoginResult
from agent_guard.authorization.passwords import hash_password, verify_password
from agent_guard.authorization.token_endpoint import TokenClient, TokenEndpoint
from agent_guard.contracts.encoding import b64url_encode, load_strict_json
from agent_guard.crypto.sm import generate_sm2_private_key
from tests.test_introspection_endpoint import FakeInspector
from tests.test_token_endpoint import FakeCodes, FakeExchanges

REDIRECT = "https://console.agent-guard.test/oauth/callback"
SESSION = "session-token-value-0123456789"
CSRF = "csrf-token-value-0123456789"


def _params(**overrides):
    base = {
        "response_type": "code",
        "client_id": "agent-planner",
        "redirect_uri": REDIRECT,
        "scope": "openid procurement.order.create",
        "state": "state-value-123456",
        "nonce": b64url_encode(secrets.token_bytes(16)),
        "code_challenge": b64url_encode(secrets.token_bytes(32)),
        "code_challenge_method": "S256",
        "ag_task_id": "task-001",
    }
    base.update(overrides)
    return base


class FakeLogin:
    def __init__(self) -> None:
        self.csrf = CSRF
        self.result = LoginResult(SESSION, CSRF, datetime.now(tz=timezone.utc))
        self.error: LoginError | None = None
        self.calls: list[dict] = []

    def issue_login_csrf(self) -> str:
        return self.csrf

    def login(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if not kwargs["csrf_cookie"] or kwargs["login_csrf"] != kwargs["csrf_cookie"]:
            raise LoginError("INVALID_CREDENTIALS")
        return self.result


class FakeConsent:
    def __init__(self) -> None:
        self.view = AuthorizeRequestView(
            request_id="authreq-1",
            tenant_id="tenant-001",
            task_id="task-001",
            client_id="agent-planner",
            scope="openid procurement.order.create",
            available_scope="openid procurement.order.create",
            amount_limit_fen=100000,
            call_limit=10,
            task_expires_at=1800000000,
            constraints={"skus": ["sku-001"]},
            policy_version=1,
            delegation_depth=2,
            csrf_token=CSRF,
        )
        self.redirect = ConsentRedirect(REDIRECT + "?code=CODE123&state=state-value-123456")
        self.create_error: ConsentError | None = None
        self.decide_error: ConsentError | None = None
        self.calls: list[tuple[str, dict]] = []

    def create_request(self, **kwargs):
        self.calls.append(("create", kwargs))
        if self.create_error is not None:
            raise self.create_error
        return self.view

    def decide(self, **kwargs):
        self.calls.append(("decide", kwargs))
        if self.decide_error is not None:
            raise self.decide_error
        return self.redirect


def _app():
    login, consent = FakeLogin(), FakeConsent()
    return BrowserLoginApp(login=login, consent=consent), login, consent


def _dispatch(app, *, method, path, query=b"", headers=(), body=b""):
    return app.dispatch(
        method=method, path=path, query_string=query, headers=list(headers), body=body
    )


def _cookie(name, value):
    return (b"cookie", f"{name}={value}".encode("ascii"))


# --------------------------------------------------------------------- password


def test_password_kdf_round_trip_and_rejection():
    encoded = hash_password("correct horse battery staple")
    assert encoded.startswith("scrypt$")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong", encoded)
    assert not verify_password("", encoded)
    for malformed in ("", "sha256$abc", "scrypt$1$2$3$AA$BB", encoded.replace("scrypt", "bcrypt")):
        assert not verify_password("correct horse battery staple", malformed)
    with pytest.raises(ValueError):
        hash_password("")


# ------------------------------------------------------------- param validation


def test_authorize_params_are_strict_and_bound_to_pkce_and_nonce():
    parsed = parse_authorize_params(_params())
    assert parsed.client_id == "agent-planner"
    assert parsed.task_id == "task-001"
    assert parsed.scopes == frozenset({"openid", "procurement.order.create"})

    with pytest.raises(ConsentError):
        parse_authorize_params({**_params(), "extra": "x"})
    with pytest.raises(ConsentError, match="RESPONSE_TYPE"):
        parse_authorize_params(_params(response_type="token"))
    with pytest.raises(ConsentError, match="SCOPE"):
        parse_authorize_params(_params(scope="openid unknown.scope"))
    with pytest.raises(ConsentError, match="SCOPE"):
        parse_authorize_params(_params(scope="procurement.order.create"))
    with pytest.raises(ConsentError, match="PKCE_METHOD"):
        parse_authorize_params(_params(code_challenge_method="plain"))
    with pytest.raises(ConsentError, match="PKCE_CHALLENGE"):
        parse_authorize_params(_params(code_challenge=b64url_encode(b"short")))
    with pytest.raises(ConsentError):
        parse_authorize_params(_params(nonce=b64url_encode(b"short")))
    with pytest.raises(ConsentError):
        parse_authorize_params(_params(state="short"))


# -------------------------------------------------------------------- login UI


def test_login_get_issues_csrf_cookie_and_hidden_field():
    app, login, _ = _app()
    response = _dispatch(app, method="GET", path="/ag/login")
    assert response.status == 200
    assert login.csrf in response.headers["Set-Cookie"]
    assert login.csrf.encode() in response.body


def test_login_post_requires_matching_csrf_and_creates_session():
    app, login, _ = _app()
    form = {
        "tenant_id": "tenant-001",
        "subject": "user-001",
        "password": "secret",
        "csrf_token": CSRF,
        "return_to": "/dashboard",
    }
    ok = _dispatch(
        app,
        method="POST",
        path="/ag/login",
        headers=(_cookie("ag_login_csrf", CSRF),),
        body=urlencode(form).encode(),
    )
    assert ok.status == 303
    assert ok.headers["Location"] == "/dashboard"
    assert "ag_session=" in ok.headers["Set-Cookie"]
    assert "~" in ok.headers["Set-Cookie"]

    no_cookie = _dispatch(app, method="POST", path="/ag/login", body=urlencode(form).encode())
    assert no_cookie.status == 401
    login.error = LoginError("INVALID_CREDENTIALS")
    rejected = _dispatch(
        app,
        method="POST",
        path="/ag/login",
        headers=(_cookie("ag_login_csrf", CSRF),),
        body=urlencode(form).encode(),
    )
    assert rejected.status == 401


def test_login_rejects_off_site_return_to():
    app, login, _ = _app()
    response = _dispatch(
        app,
        method="GET",
        path="/ag/login",
        query=urlencode({"return_to": "https://evil.example/steal"}).encode(),
    )
    assert response.status == 200
    assert b'value="/"' in response.body


# ----------------------------------------------------------------- authorize UI


def test_authorize_without_session_redirects_to_login():
    app, _, consent = _app()
    query = urlencode(_params()).encode()
    response = _dispatch(app, method="GET", path="/oauth/authorize", query=query)
    assert response.status == 302
    assert response.headers["Location"].startswith("/ag/login?return_to=")
    assert consent.calls == []


def test_authorize_with_session_renders_consent_page():
    app, _, consent = _app()
    query = urlencode(_params()).encode()
    response = _dispatch(
        app,
        method="GET",
        path="/oauth/authorize",
        query=query,
        headers=(_cookie("ag_session", f"{SESSION}~{CSRF}"),),
    )
    assert response.status == 200
    assert b"authreq-1" in response.body
    assert CSRF.encode() in response.body
    assert consent.calls[0][0] == "create"


def test_consent_approve_and_deny_never_put_token_in_url():
    app, _, consent = _app()
    approve = _dispatch(
        app,
        method="POST",
        path="/ag/consent",
        headers=(_cookie("ag_session", f"{SESSION}~{CSRF}"),),
        body=urlencode(
            {"request_id": "authreq-1", "decision": "approve", "csrf_token": CSRF}
        ).encode(),
    )
    assert approve.status == 303
    assert approve.headers["Location"] == consent.redirect.location
    assert "access_token" not in approve.headers["Location"]

    consent.redirect = ConsentRedirect(REDIRECT + "?error=access_denied&state=state-value-123456")
    deny = _dispatch(
        app,
        method="POST",
        path="/ag/consent",
        headers=(_cookie("ag_session", f"{SESSION}~{CSRF}"),),
        body=urlencode(
            {"request_id": "authreq-1", "decision": "deny", "csrf_token": CSRF}
        ).encode(),
    )
    assert deny.status == 303
    assert "error=access_denied" in deny.headers["Location"]


def test_consent_rejects_missing_session_bad_fields_and_ambiguous_cookie():
    app, _, consent = _app()
    form = urlencode(
        {"request_id": "authreq-1", "decision": "approve", "csrf_token": CSRF}
    ).encode()
    assert _dispatch(app, method="POST", path="/ag/consent", body=form).status == 401
    bad = urlencode({"request_id": "authreq-1", "decision": "approve", "extra": "x"}).encode()
    response = _dispatch(
        app,
        method="POST",
        path="/ag/consent",
        headers=(_cookie("ag_session", f"{SESSION}~{CSRF}"),),
        body=bad,
    )
    assert response.status == 400
    consent.decide_error = ConsentError("ALREADY_DECIDED")
    duplicated = _dispatch(
        app,
        method="POST",
        path="/ag/consent",
        headers=(
            _cookie("ag_session", f"{SESSION}~{CSRF}"),
            _cookie("ag_session", f"{SESSION}~{CSRF}"),
        ),
        body=form,
    )
    assert duplicated.status == 400
    assert load_strict_json(duplicated.body)["error"] == "REQUEST_INVALID"


def test_unsupported_methods_and_paths_fail_closed():
    app, _, _ = _app()
    assert _dispatch(app, method="PUT", path="/ag/login").status == 405
    assert _dispatch(app, method="GET", path="/ag/consent").status == 405
    assert _dispatch(app, method="POST", path="/nope").status == 405


def _asgi(app, scope):
    events = [{"type": "http.request", "body": b"", "more_body": False}]
    sent = []

    async def receive():
        return events.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    return sent


def test_asgi_app_mounts_browser_routes():
    browser, _, _ = _app()
    gateway_secret = b"synthetic-test-only-gateway-secret-32b"
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
                    REDIRECT,
                    hashlib.sha256(b"synthetic-test-only-secret-32-bytes").digest(),
                )
            },
            codes=FakeCodes(),
            exchanges=FakeExchanges(),
        ),
        introspection=IntrospectionEndpoint(
            gateway_client=TokenClient(
                "gateway-introspect",
                "service",
                None,
                hashlib.sha256(gateway_secret).digest(),
            ),
            inspector=FakeInspector(),
        ),
        browser=browser,
    )
    sent = _asgi(
        app,
        {
            "type": "http",
            "scheme": "https",
            "path": "/ag/login",
            "method": "GET",
            "query_string": b"",
            "headers": [],
        },
    )
    assert sent[0]["status"] == 200
    assert any(name == b"set-cookie" for name, _ in sent[0]["headers"])
