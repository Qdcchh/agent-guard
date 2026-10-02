"""Server-side login sessions, user authentication and pre-auth CSRF.

This is the only component allowed to turn a submitted password into an
authenticated session. It is a trusted in-process service: an HTTP request may
supply credentials, but never a pre-authenticated ``user_id`` or session. Only
token digests are persisted; raw session and CSRF tokens stay with the browser.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import psycopg

from agent_guard.authorization.passwords import dummy_password_hash, verify_password
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.ledger import store

_SAFE_ID = re.compile(r"[\x21-\x7e]{1,128}\Z", re.ASCII)
_TOKEN = re.compile(r"[A-Za-z0-9_-]{20,256}\Z", re.ASCII)


class LoginError(ValueError):
    """Authentication, session or CSRF validation failed; never leaks which."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LoginResult:
    session_token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True)
class SessionContext:
    tenant_id: str
    subject: str
    auth_time: int
    session_sha256: bytes


def _sha256(value: str) -> bytes:
    return hashlib.sha256(value.encode("ascii")).digest()


def _bounded_ttl(value: object, name: str) -> int:
    if type(value) is not int or isinstance(value, bool) or not 30 <= value <= 86400:
        raise ValueError(f"{name} must be an integer within [30, 86400]")
    return value


class LoginService:
    """Issue sessions only after a verified password and one-use login CSRF."""

    def __init__(
        self,
        dsn: str,
        *,
        session_ttl_seconds: int = 1800,
        csrf_ttl_seconds: int = 600,
        connector: Callable[..., psycopg.Connection] = psycopg.connect,
    ) -> None:
        self._dsn = dsn
        self._session_ttl = _bounded_ttl(session_ttl_seconds, "session_ttl_seconds")
        self._csrf_ttl = _bounded_ttl(csrf_ttl_seconds, "csrf_ttl_seconds")
        self._connector = connector

    def _connect(self) -> psycopg.Connection:
        conn = self._connector(self._dsn, autocommit=False, connect_timeout=5)
        try:
            conn.execute(
                "SELECT set_config('lock_timeout', '10000ms', false), "
                "set_config('statement_timeout', '15000ms', false)"
            )
        except BaseException:
            conn.close()
            raise
        return conn

    def issue_login_csrf(self) -> str:
        """Persist a one-use pre-authentication CSRF token and return it."""
        token = secrets.token_urlsafe(32)
        try:
            with self._connect() as conn:
                with conn.transaction():
                    conn.execute(
                        "INSERT INTO ag_login_csrf (token_sha256, expires_at) "
                        "VALUES (%s, clock_timestamp() + (%s * interval '1 second'))",
                        (_sha256(token), self._csrf_ttl),
                    )
        except psycopg.Error as exc:
            raise LoginError("TRUSTED_STATE_UNAVAILABLE") from exc
        return token

    def login(
        self,
        *,
        login_csrf: str,
        csrf_cookie: str,
        tenant_id: str,
        subject: str,
        password: str,
    ) -> LoginResult:
        """Consume the login CSRF once and create a session on valid password.

        The hidden form token and the browser cookie must both be present and
        equal, and the server-side digest must be unused and unexpired.
        """
        if (
            type(login_csrf) is not str
            or type(csrf_cookie) is not str
            or not _TOKEN.fullmatch(login_csrf)
            or not _TOKEN.fullmatch(csrf_cookie)
            or not hmac.compare_digest(login_csrf, csrf_cookie)
            or type(tenant_id) is not str
            or not _SAFE_ID.fullmatch(tenant_id)
            or type(subject) is not str
            or not _SAFE_ID.fullmatch(subject)
            or type(password) is not str
        ):
            raise LoginError("INVALID_CREDENTIALS")
        csrf_hash = _sha256(login_csrf)
        try:
            with self._connect() as conn:
                with conn.transaction():
                    row = conn.execute(
                        "SELECT used_at, expires_at > clock_timestamp() FROM ag_login_csrf "
                        "WHERE token_sha256 = %s FOR UPDATE",
                        (csrf_hash,),
                    ).fetchone()
                    if row is None or row[0] is not None or not row[1]:
                        raise LoginError("INVALID_CREDENTIALS")
                    conn.execute(
                        "UPDATE ag_login_csrf SET used_at = clock_timestamp() "
                        "WHERE token_sha256 = %s",
                        (csrf_hash,),
                    )
                    user = conn.execute(
                        "SELECT password_hash, active FROM ag_users "
                        "WHERE tenant_id = %s AND subject = %s",
                        (tenant_id, subject),
                    ).fetchone()
                    stored = user[0] if user is not None else dummy_password_hash()
                    if not verify_password(password, stored) or user is None or not user[1]:
                        raise LoginError("INVALID_CREDENTIALS")
                    now = int(store.db_now_epoch(conn))
                    session_token = secrets.token_urlsafe(32)
                    csrf_token = secrets.token_urlsafe(32)
                    conn.execute(
                        "INSERT INTO ag_login_sessions "
                        "(session_sha256, tenant_id, subject, auth_time, csrf_sha256, expires_at) "
                        "VALUES (%s, %s, %s, %s, %s, "
                        "clock_timestamp() + (%s * interval '1 second'))",
                        (
                            _sha256(session_token),
                            tenant_id,
                            subject,
                            now,
                            _sha256(csrf_token),
                            self._session_ttl,
                        ),
                    )
                    conn.execute(
                        "INSERT INTO ag_auth_events "
                        "(event_id, event_type, tenant_id, subject, request_id, detail_json) "
                        "VALUES (%s, 'login', %s, %s, NULL, %s)",
                        (
                            "event-" + uuid.uuid4().hex,
                            tenant_id,
                            subject,
                            canonical_json_bytes({"auth_time": now}),
                        ),
                    )
                    expires = conn.execute(
                        "SELECT expires_at FROM ag_login_sessions WHERE session_sha256 = %s",
                        (_sha256(session_token),),
                    ).fetchone()[0]
        except psycopg.Error as exc:
            raise LoginError("TRUSTED_STATE_UNAVAILABLE") from exc
        return LoginResult(session_token, csrf_token, expires)

    def authenticate(self, *, session_token: str) -> SessionContext:
        """Return the live session context or fail closed."""
        if type(session_token) is not str or not _TOKEN.fullmatch(session_token):
            raise LoginError("SESSION_INVALID")
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT s.tenant_id, s.subject, s.auth_time, s.session_sha256 "
                    "FROM ag_login_sessions s JOIN ag_users u "
                    "ON u.tenant_id = s.tenant_id AND u.subject = s.subject "
                    "WHERE s.session_sha256 = %s AND s.revoked_at IS NULL "
                    "AND s.expires_at > clock_timestamp() AND u.active",
                    (_sha256(session_token),),
                ).fetchone()
        except psycopg.Error as exc:
            raise LoginError("TRUSTED_STATE_UNAVAILABLE") from exc
        if row is None:
            raise LoginError("SESSION_INVALID")
        return SessionContext(row[0], row[1], row[2], bytes(row[3]))

    def verify_session_csrf(self, *, session_token: str, csrf_token: str) -> SessionContext:
        """Authenticate the session and require its bound CSRF token."""
        context = self.authenticate(session_token=session_token)
        if type(csrf_token) is not str or not _TOKEN.fullmatch(csrf_token):
            raise LoginError("CSRF_INVALID")
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT csrf_sha256 FROM ag_login_sessions WHERE session_sha256 = %s",
                    (context.session_sha256,),
                ).fetchone()
        except psycopg.Error as exc:
            raise LoginError("TRUSTED_STATE_UNAVAILABLE") from exc
        if row is None or not hmac.compare_digest(bytes(row[0]), _sha256(csrf_token)):
            raise LoginError("CSRF_INVALID")
        return context

    def verify_session_csrf_locked(
        self,
        conn: psycopg.Connection,
        *,
        session_token: str,
        csrf_token: str,
    ) -> SessionContext:
        """Recheck a session/user after taking locks in the caller's decision transaction."""
        if type(session_token) is not str or not _TOKEN.fullmatch(session_token):
            raise LoginError("SESSION_INVALID")
        if type(csrf_token) is not str or not _TOKEN.fullmatch(csrf_token):
            raise LoginError("CSRF_INVALID")
        session_hash = _sha256(session_token)
        row = conn.execute(
            "SELECT s.tenant_id, s.subject, s.auth_time, s.csrf_sha256, "
            "s.expires_at, s.revoked_at, u.active "
            "FROM ag_login_sessions s JOIN ag_users u "
            "ON u.tenant_id = s.tenant_id AND u.subject = s.subject "
            "WHERE s.session_sha256 = %s FOR UPDATE OF s, u",
            (session_hash,),
        ).fetchone()
        if row is None:
            raise LoginError("SESSION_INVALID")
        now = store.db_now_epoch(conn)
        if row[5] is not None or not row[6] or now >= row[4].timestamp():
            raise LoginError("SESSION_INVALID")
        if not hmac.compare_digest(bytes(row[3]), _sha256(csrf_token)):
            raise LoginError("CSRF_INVALID")
        return SessionContext(row[0], row[1], row[2], session_hash)
