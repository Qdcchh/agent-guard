"""Revocation HTTP boundary: session, CSRF, path and body strictness (no DB)."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone

from agent_guard.authorization.discovery import DiscoveryEndpoint
from agent_guard.authorization.grant_revocation_service import (
    GrantRevocationError,
    GrantRevocationResult,
)
from agent_guard.authorization.http_app import AuthorizationHttpApp
from agent_guard.authorization.introspection_endpoint import IntrospectionEndpoint
from agent_guard.authorization.login import LoginError, SessionContext
from agent_guard.authorization.revocation_http import RevocationHttpApp
from agent_guard.authorization.revocation_service import (
    TaskRevocationError,
    TaskRevocationResult,
)
from agent_guard.authorization.token_endpoint import TokenClient, TokenEndpoint
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.crypto.sm import generate_sm2_private_key
from tests.test_introspection_endpoint import FakeInspector
from tests.test_token_endpoint import FakeCodes, FakeExchanges

SESSION = "session-token-value-0123456789"
CSRF = "csrf-token-value-0123456789"
EFFECTIVE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeSessions:
    def __init__(self) -> None:
        self.context = SessionContext("tenant-001", "user-001", 1000, b"s" * 32)
        self.error: LoginError | None = None
        self.calls: list[tuple[str, str]] = []

    def verify_session_csrf(self, *, session_token, csrf_token):
        self.calls.append((session_token, csrf_token))
        if self.error is not None:
            raise self.error
        return self.context


class FakeTasks:
    def __init__(self) -> None:
        self.result = TaskRevocationResult("revoke-task-1", EFFECTIVE)
        self.error: TaskRevocationError | None = None
        self.calls: list[dict] = []

    def revoke_task(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class FakeGrants:
    def __init__(self) -> None:
        self.result = GrantRevocationResult("revoke-grant-1", EFFECTIVE)
        self.error: GrantRevocationError | None = None
        self.calls: list[dict] = []

    def revoke_grant(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


def _app():
    sessions, tasks, grants = FakeSessions(), FakeTasks(), FakeGrants()
    app = RevocationHttpApp(sessions=sessions, tasks=tasks, grants=grants)
    return app, sessions, tasks, grants


def _headers(*, session=SESSION, csrf=CSRF, csrf_header=True):
    headers = [(b"cookie", f"ag_session={session}~{csrf}".encode())]
    if csrf_header:
        headers.append((b"x-csrf-token", csrf.encode()))
    return headers


def _body(value=None):
    if value is None:
        value = {"reason_code": "USER_CANCELLED"}
    return canonical_json_bytes(value)


def test_handles_only_the_two_revocation_paths():
    app, _, _, _ = _app()
    assert app.handles("/ag/tasks/task-1/revoke")
    assert app.handles("/ag/grants/grant-1/revoke")
    assert not app.handles("/ag/tasks/task-1")
    assert not app.handles("/oauth/token")
    assert not app.handles("/ag/tasks/a/b/revoke")


def test_task_revoke_uses_session_tenant_and_subject():
    app, sessions, tasks, _ = _app()
    response = app.dispatch(
        method="POST", path="/ag/tasks/task-001/revoke", headers=_headers(), body=_body()
    )
    assert response.status == 200
    payload = load_strict_json(response.body)
    assert payload["revocation_id"] == "revoke-task-1"
    assert payload["scope"] == "SUBTREE"
    assert tasks.calls[0]["tenant_id"] == "tenant-001"
    assert tasks.calls[0]["authenticated_subject"] == "user-001"
    assert tasks.calls[0]["task_id"] == "task-001"
    assert sessions.calls == [(SESSION, CSRF)]


def test_grant_revoke_uses_registry_checked_admin_subject():
    app, _, _, grants = _app()
    response = app.dispatch(
        method="POST", path="/ag/grants/grant-xyz/revoke", headers=_headers(), body=_body()
    )
    assert response.status == 200
    assert grants.calls[0]["grant_id"] == "grant-xyz"
    assert grants.calls[0]["authenticated_admin_subject"] == "user-001"
    assert grants.calls[0]["tenant_id"] == "tenant-001"


def test_missing_session_or_csrf_header_is_unauthenticated():
    app, sessions, tasks, _ = _app()
    no_cookie = app.dispatch(
        method="POST",
        path="/ag/tasks/task-001/revoke",
        headers=[(b"x-csrf-token", CSRF.encode())],
        body=_body(),
    )
    assert no_cookie.status == 401
    no_header = app.dispatch(
        method="POST",
        path="/ag/tasks/task-001/revoke",
        headers=_headers(csrf_header=False),
        body=_body(),
    )
    assert no_header.status == 401
    assert sessions.calls == []
    assert tasks.calls == []


def test_duplicate_or_wrong_csrf_and_bad_body_rejected():
    app, _, tasks, _ = _app()
    duplicated = app.dispatch(
        method="POST",
        path="/ag/tasks/task-001/revoke",
        headers=_headers() + [(b"x-csrf-token", CSRF.encode())],
        body=_body(),
    )
    assert duplicated.status == 400
    for bad in (
        canonical_json_bytes({"reason_code": "OTHER"}),
        canonical_json_bytes({"reason_code": "USER_CANCELLED", "extra": "x"}),
        b"not-json",
    ):
        assert (
            app.dispatch(
                method="POST",
                path="/ag/tasks/task-001/revoke",
                headers=_headers(),
                body=bad,
            ).status
            == 400
        )
    assert tasks.calls == []


def test_service_error_status_mapping():
    app, _, tasks, grants = _app()
    tasks.error = TaskRevocationError("NOT_TASK_OWNER")
    assert (
        app.dispatch(
            method="POST", path="/ag/tasks/t/revoke", headers=_headers(), body=_body()
        ).status
        == 403
    )
    tasks.error = TaskRevocationError("TASK_NOT_FOUND")
    assert (
        app.dispatch(
            method="POST", path="/ag/tasks/t/revoke", headers=_headers(), body=_body()
        ).status
        == 404
    )
    grants.error = GrantRevocationError("NOT_ADMIN")
    assert (
        app.dispatch(
            method="POST", path="/ag/grants/g/revoke", headers=_headers(), body=_body()
        ).status
        == 403
    )
    grants.error = GrantRevocationError("ALREADY_REVOKED")
    assert (
        app.dispatch(
            method="POST", path="/ag/grants/g/revoke", headers=_headers(), body=_body()
        ).status
        == 409
    )
    grants.error = GrantRevocationError("TRUSTED_STATE_UNAVAILABLE")
    assert (
        app.dispatch(
            method="POST", path="/ag/grants/g/revoke", headers=_headers(), body=_body()
        ).status
        == 503
    )


def test_method_and_path_id_validation():
    app, _, tasks, _ = _app()
    assert (
        app.dispatch(method="GET", path="/ag/tasks/t/revoke", headers=_headers(), body=b"").status
        == 405
    )
    assert (
        app.dispatch(
            method="POST", path="/ag/tasks/bad id/revoke", headers=_headers(), body=_body()
        ).status
        == 400
    )
    assert tasks.calls == []


def _asgi(app, scope):
    events = [{"type": "http.request", "body": scope.pop("_body", b""), "more_body": False}]
    sent = []

    async def receive():
        return events.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    return sent


def test_asgi_app_mounts_revocation_routes():
    revocation, _, _, _ = _app()
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
                hashlib.sha256(b"synthetic-test-only-gateway-secret").digest(),
            ),
            inspector=FakeInspector(),
        ),
        revocation=revocation,
    )
    scope = {
        "type": "http",
        "scheme": "https",
        "path": "/ag/tasks/task-001/revoke",
        "method": "POST",
        "query_string": b"",
        "headers": _headers(),
        "_body": _body(),
    }
    sent = _asgi(app, scope)
    assert sent[0]["status"] == 200
