"""Browser-facing login and consent handlers for the AS/OP.

This module is a pure request adapter: it reads cookies, query strings and an
already size-limited form body, then calls the trusted login and consent
services. It performs no database access itself and never treats a submitted
``user_id``, tenant, budget or ``ApprovedAuthorization`` as trusted.
"""

from __future__ import annotations

import html
import re
from collections.abc import Mapping
from urllib.parse import urlencode

from agent_guard.authorization.consent import (
    AuthorizeRequestView,
    ConsentError,
    ConsentRedirect,
    ConsentService,
)
from agent_guard.authorization.forms import FormError, decode_oauth_form
from agent_guard.authorization.login import LoginError, LoginService
from agent_guard.authorization.token_endpoint import TokenResponse
from agent_guard.contracts.encoding import canonical_json_bytes

_LOGIN_PATHS = frozenset({"/ag/login", "/oauth/authorize", "/ag/consent"})
_RETURN_TO = re.compile(r"/[A-Za-z0-9._~!$&'()*+,;=:@%/?-]*\Z", re.ASCII)
_HTML_HEADERS = {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}
_JSON_HEADERS = {"Content-Type": "application/json", "Cache-Control": "no-store"}
_LOGIN_FIELDS = {"tenant_id", "subject", "password", "csrf_token", "return_to"}
_CONSENT_FIELDS = {"request_id", "decision", "csrf_token"}
_SESSION_COOKIE = "ag_session"


def _cookie(headers: object, name: str) -> str | None:
    """Return one unique cookie value or fail closed on ambiguity."""
    if type(headers) is not list:
        raise ValueError("invalid headers")
    found: str | None = None
    for key, value in headers:
        if type(key) is not bytes or type(value) is not bytes:
            raise ValueError("invalid header")
        if key.lower() != b"cookie":
            continue
        try:
            text = value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("non-ascii cookie") from exc
        for pair in text.split(";"):
            raw_name, sep, raw_value = pair.strip().partition("=")
            if sep and raw_name == name:
                if found is not None:
                    raise ValueError("duplicate cookie")
                found = raw_value
    return found


def _session_and_csrf(headers: object) -> tuple[str, str] | None:
    """Split the combined session cookie into its session and CSRF tokens."""
    value = _cookie(headers, _SESSION_COOKIE)
    if value is None:
        return None
    session, sep, csrf = value.partition("~")
    if not sep or not session or not csrf or "~" in csrf:
        return None
    return session, csrf


def _safe_return_to(value: str) -> str:
    if type(value) is not str or not _RETURN_TO.fullmatch(value) or value.startswith("//"):
        return "/"
    return value


def _page(title: str, body: str) -> bytes:
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title></head><body>"
        f"<h1>{html.escape(title)}</h1>{body}</body></html>"
    ).encode("utf-8")


def _hidden(fields: Mapping[str, str]) -> str:
    return "".join(
        f'<input type="hidden" name="{html.escape(name)}" value="{html.escape(value)}">'
        for name, value in fields.items()
    )


def _authorize_path(params: Mapping[str, str]) -> str:
    return "/oauth/authorize?" + urlencode(params) if params else "/"


class BrowserLoginApp:
    """Route ``/ag/login``, ``/oauth/authorize`` and ``/ag/consent``."""

    def __init__(self, *, login: LoginService, consent: ConsentService) -> None:
        if login is None or consent is None:
            raise ValueError("login and consent services are required")
        self._login = login
        self._consent = consent

    @property
    def paths(self) -> frozenset[str]:
        return _LOGIN_PATHS

    def dispatch(
        self,
        *,
        method: str,
        path: str,
        query_string: bytes,
        headers: object,
        body: bytes,
    ) -> TokenResponse:
        """Map one HTTP request to a login or consent response."""
        try:
            if path == "/ag/login":
                if method == "GET":
                    return self._login_form(query_string)
                if method == "POST":
                    return self._do_login(headers, body)
            elif path == "/oauth/authorize":
                if method == "GET":
                    return self._authorize(headers, self._query(query_string))
                if method == "POST":
                    return self._authorize(headers, self._form(body))
            elif path == "/ag/consent" and method == "POST":
                return self._consent_decision(headers, body)
            return self._error(405, "METHOD_NOT_ALLOWED")
        except (FormError, ValueError):
            return self._error(400, "REQUEST_INVALID")

    # ------------------------------------------------------------------ login

    def _login_form(self, query_string: bytes) -> TokenResponse:
        params = self._query(query_string)
        return_to = _safe_return_to(params.get("return_to", "/"))
        csrf = self._login.issue_login_csrf()
        body = (
            f'<form method="post" action="/ag/login">'
            f"{_hidden({'csrf_token': csrf, 'return_to': return_to})}"
            '<input name="tenant_id" autocomplete="username">'
            '<input name="subject" autocomplete="username">'
            '<input name="password" type="password" autocomplete="current-password">'
            '<button type="submit">Sign in</button></form>'
        )
        headers = dict(_HTML_HEADERS)
        headers["Set-Cookie"] = f"ag_login_csrf={csrf}; Path=/; Secure; HttpOnly; SameSite=Lax"
        return TokenResponse(200, headers, _page("Sign in", body))

    def _do_login(self, headers: object, body: bytes) -> TokenResponse:
        values = self._form(body)
        if set(values) != _LOGIN_FIELDS:
            return self._error(400, "REQUEST_INVALID")
        cookie = _cookie(headers, "ag_login_csrf")
        try:
            result = self._login.login(
                login_csrf=values["csrf_token"],
                csrf_cookie=cookie or "",
                tenant_id=values["tenant_id"],
                subject=values["subject"],
                password=values["password"],
            )
        except LoginError as exc:
            if exc.code == "TRUSTED_STATE_UNAVAILABLE":
                return self._error(503, "TEMPORARILY_UNAVAILABLE")
            return self._error(401, "INVALID_CREDENTIALS")
        combined = f"{result.session_token}~{result.csrf_token}"
        return TokenResponse(
            303,
            {
                "Location": _safe_return_to(values["return_to"]),
                "Cache-Control": "no-store",
                "Set-Cookie": (
                    f"{_SESSION_COOKIE}={combined}; Path=/; Secure; HttpOnly; SameSite=Lax"
                ),
            },
            b"",
        )

    # -------------------------------------------------------------- authorize

    def _authorize(self, headers: object, params: Mapping[str, str]) -> TokenResponse:
        session_and_csrf = _session_and_csrf(headers)
        if session_and_csrf is None:
            location = "/ag/login?" + urlencode({"return_to": _authorize_path(params)})
            return TokenResponse(302, {"Location": location, "Cache-Control": "no-store"}, b"")
        session, csrf = session_and_csrf
        try:
            view = self._consent.create_request(
                session_token=session, csrf_token=csrf, params=dict(params)
            )
        except LoginError as exc:
            if exc.code == "TRUSTED_STATE_UNAVAILABLE":
                return self._error(503, "TEMPORARILY_UNAVAILABLE")
            location = "/ag/login?" + urlencode({"return_to": _authorize_path(params)})
            return TokenResponse(302, {"Location": location, "Cache-Control": "no-store"}, b"")
        except ConsentError as exc:
            return self._error(400, exc.code)
        return self._consent_page(view, csrf)

    def _consent_page(self, view: AuthorizeRequestView, csrf: str) -> TokenResponse:
        constraints = html.escape(canonical_json_bytes(view.constraints).decode("utf-8"))
        body = (
            f"<p>Task {html.escape(view.task_id)} for {html.escape(view.client_id)}</p>"
            f"<p>Requested scope: {html.escape(view.scope)}</p>"
            f"<p>Policy scope: {html.escape(view.available_scope)}</p>"
            f"<p>Amount limit (fen): {view.amount_limit_fen}; calls: {view.call_limit}</p>"
            f"<p>Expires (Unix time): {view.task_expires_at}</p>"
            f"<p>Delegation depth: {view.delegation_depth}; "
            f"policy version: {view.policy_version}</p>"
            f"<pre>Constraints: {constraints}</pre>"
            f'<form method="post" action="/ag/consent">'
            f"{_hidden({'request_id': view.request_id, 'csrf_token': csrf})}"
            '<button name="decision" value="approve" type="submit">Approve</button>'
            '<button name="decision" value="deny" type="submit">Deny</button></form>'
        )
        return TokenResponse(200, dict(_HTML_HEADERS), _page("Authorize", body))

    # ---------------------------------------------------------------- consent

    def _consent_decision(self, headers: object, body: bytes) -> TokenResponse:
        values = self._form(body)
        if set(values) != _CONSENT_FIELDS:
            return self._error(400, "REQUEST_INVALID")
        session_and_csrf = _session_and_csrf(headers)
        if session_and_csrf is None:
            return self._error(401, "SESSION_INVALID")
        session, _ = session_and_csrf
        try:
            redirect: ConsentRedirect = self._consent.decide(
                session_token=session,
                csrf_token=values["csrf_token"],
                request_id=values["request_id"],
                decision=values["decision"],
            )
        except LoginError as exc:
            if exc.code == "TRUSTED_STATE_UNAVAILABLE":
                return self._error(503, "TEMPORARILY_UNAVAILABLE")
            return self._error(401, "SESSION_INVALID")
        except ConsentError as exc:
            if exc.code == "TRUSTED_STATE_UNAVAILABLE":
                return self._error(503, "TEMPORARILY_UNAVAILABLE")
            return self._error(400, exc.code)
        return TokenResponse(303, {"Location": redirect.location, "Cache-Control": "no-store"}, b"")

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _query(query_string: bytes) -> dict[str, str]:
        if type(query_string) is not bytes:
            raise ValueError("invalid query string")
        return {} if not query_string else decode_oauth_form(query_string)

    @staticmethod
    def _form(body: bytes) -> dict[str, str]:
        if type(body) is not bytes:
            raise ValueError("invalid body")
        return {} if not body else decode_oauth_form(body)

    @staticmethod
    def _error(status: int, code: str) -> TokenResponse:
        return TokenResponse(status, dict(_JSON_HEADERS), canonical_json_bytes({"error": code}))
