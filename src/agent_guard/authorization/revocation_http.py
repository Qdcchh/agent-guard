"""Session-authenticated, CSRF-protected revocation HTTP boundary.

The caller supplies a login session cookie and the session-bound CSRF token in
``X-CSRF-Token``; the tenant and subject always come from the verified session,
never from the URL or body. Task owner cancellation and tenant-admin subtree
cancellation keep the existing transaction lock order and idempotency rules.
"""

from __future__ import annotations

import re
from datetime import timezone

from agent_guard.authorization.grant_revocation_service import (
    GrantRevocationError,
    GrantRevocationResult,
    GrantRevocationService,
)
from agent_guard.authorization.login import LoginError, LoginService
from agent_guard.authorization.revocation_service import (
    TaskRevocationError,
    TaskRevocationResult,
    TaskRevocationService,
)
from agent_guard.authorization.token_endpoint import TokenResponse
from agent_guard.contracts.encoding import EncodingError, canonical_json_bytes, load_strict_json

_SAFE_ID = re.compile(r"[\x21-\x7e]{1,128}\Z", re.ASCII)
_TASK_RE = re.compile(r"/ag/tasks/([^/]+)/revoke\Z", re.ASCII)
_GRANT_RE = re.compile(r"/ag/grants/([^/]+)/revoke\Z", re.ASCII)
_REASON = "USER_CANCELLED"
_JSON_HEADERS = {"Content-Type": "application/json", "Cache-Control": "no-store"}


class RevocationHttpApp:
    """Map session-authenticated revocation requests to the trusted services."""

    def __init__(
        self,
        *,
        sessions: LoginService,
        tasks: TaskRevocationService,
        grants: GrantRevocationService,
    ) -> None:
        if sessions is None or tasks is None or grants is None:
            raise ValueError("session and both revocation services are required")
        self._sessions = sessions
        self._tasks = tasks
        self._grants = grants

    def handles(self, path: str) -> bool:
        return type(path) is str and bool(_TASK_RE.fullmatch(path) or _GRANT_RE.fullmatch(path))

    def dispatch(self, *, method: str, path: str, headers: object, body: bytes) -> TokenResponse:
        if method != "POST":
            return self._error(405, "METHOD_NOT_ALLOWED")
        match = _TASK_RE.fullmatch(path) if type(path) is str else None
        is_task = match is not None
        if match is None:
            match = _GRANT_RE.fullmatch(path) if type(path) is str else None
        if match is None:
            return self._error(404, "NOT_FOUND")
        target_id = match.group(1)
        if not _SAFE_ID.fullmatch(target_id):
            return self._error(400, "INVALID_REQUEST")
        try:
            session, csrf = _session_tokens(headers)
        except ValueError:
            return self._error(400, "REQUEST_INVALID")
        if session is None or csrf is None:
            return self._error(401, "SESSION_INVALID")
        try:
            reason = _reason_code(body)
        except (EncodingError, UnicodeError, TypeError, ValueError):
            return self._error(400, "INVALID_REQUEST")
        try:
            context = self._sessions.verify_session_csrf(session_token=session, csrf_token=csrf)
        except LoginError as exc:
            if exc.code == "TRUSTED_STATE_UNAVAILABLE":
                return self._error(503, "TEMPORARILY_UNAVAILABLE")
            return self._error(401, "SESSION_INVALID")
        try:
            if is_task:
                result = self._tasks.revoke_task(
                    tenant_id=context.tenant_id,
                    task_id=target_id,
                    authenticated_subject=context.subject,
                    reason_code=reason,
                )
            else:
                result = self._grants.revoke_grant(
                    tenant_id=context.tenant_id,
                    grant_id=target_id,
                    authenticated_admin_subject=context.subject,
                    reason_code=reason,
                )
        except TaskRevocationError as exc:
            return self._error(*_task_status(exc.code))
        except GrantRevocationError as exc:
            return self._error(*_grant_status(exc.code))
        return TokenResponse(200, dict(_JSON_HEADERS), _body(result))

    @staticmethod
    def _error(status: int, code: str) -> TokenResponse:
        return TokenResponse(status, dict(_JSON_HEADERS), canonical_json_bytes({"error": code}))


def _session_tokens(headers: object) -> tuple[str | None, str | None]:
    """Extract the combined session cookie and the CSRF header occurrence."""
    if type(headers) is not list:
        raise ValueError("invalid headers")
    session: str | None = None
    csrf: str | None = None
    for key, value in headers:
        if type(key) is not bytes or type(value) is not bytes:
            raise ValueError("invalid header")
        name = key.lower()
        try:
            text = value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("non-ascii header") from exc
        if name == b"cookie":
            for pair in text.split(";"):
                raw_name, sep, raw_value = pair.strip().partition("=")
                if sep and raw_name == "ag_session":
                    if session is not None:
                        raise ValueError("duplicate session cookie")
                    session = raw_value
        elif name == b"x-csrf-token":
            if csrf is not None:
                raise ValueError("duplicate csrf header")
            csrf = text
    if session is not None:
        combined, sep, embedded = session.partition("~")
        if not sep or not combined or not embedded or "~" in embedded:
            return None, None
        session = combined
    return session, csrf


def _reason_code(body: bytes) -> str:
    if type(body) is not bytes:
        raise ValueError("body must be bytes")
    value = load_strict_json(body)
    if type(value) is not dict or set(value) != {"reason_code"} or value["reason_code"] != _REASON:
        raise ValueError("body must be exactly {reason_code: USER_CANCELLED}")
    return _REASON


def _body(result: TaskRevocationResult | GrantRevocationResult) -> bytes:
    return canonical_json_bytes(
        {
            "revocation_id": result.revocation_id,
            "effective_at": result.effective_at.astimezone(timezone.utc).isoformat(),
            "scope": result.scope,
        }
    )


def _task_status(code: str) -> tuple[int, str]:
    return {
        "TRUSTED_STATE_UNAVAILABLE": (503, code),
        "INVALID_REQUEST": (400, code),
        "TASK_NOT_FOUND": (404, code),
        "NOT_TASK_OWNER": (403, code),
    }.get(code, (409, code))


def _grant_status(code: str) -> tuple[int, str]:
    return {
        "TRUSTED_STATE_UNAVAILABLE": (503, code),
        "INVALID_REQUEST": (400, code),
        "GRANT_NOT_FOUND": (404, code),
        "NOT_ADMIN": (403, code),
    }.get(code, (409, code))
