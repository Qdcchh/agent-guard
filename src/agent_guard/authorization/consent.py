"""Browser authorization requests and user consent in the AS trust domain.

Only this service, driven by a verified login session and CSRF token, may turn
a persisted request plus the trusted task policy into an
``ApprovedAuthorization``. The client can supply ``client_id``, ``redirect_uri``,
``scope``, ``state``, ``nonce``, PKCE challenge and ``ag_task_id`` -- never a
tenant, a subject, an amount limit or an already-approved authorization.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg

from agent_guard.authorization.claims import (
    ClaimsError,
    parse_constraints,
    parse_scope,
)
from agent_guard.authorization.code_service import (
    ROOT_DELEGATION_DEPTH,
    ApprovedAuthorization,
    AuthorizationCodeError,
    AuthorizationCodeService,
)
from agent_guard.authorization.login import LoginError, LoginService
from agent_guard.contracts.encoding import (
    EncodingError,
    JsonObject,
    b64url_decode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.ledger import store

_SAFE_ID = re.compile(r"[\x21-\x7e]{1,128}\Z", re.ASCII)
_STATE = re.compile(r"[\x21-\x7e]{8,512}\Z", re.ASCII)
_AUTHORIZE_FIELDS = {
    "response_type",
    "client_id",
    "redirect_uri",
    "scope",
    "state",
    "nonce",
    "code_challenge",
    "code_challenge_method",
    "ag_task_id",
}
_DECISIONS = frozenset({"approve", "deny"})


class ConsentError(ValueError):
    """The authorization request or consent decision is rejected."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AuthorizeClient:
    client_id: str
    tenant_id: str
    redirect_uri: str
    active: bool = True


@dataclass(frozen=True)
class AuthorizeParams:
    client_id: str
    redirect_uri: str
    scope: str
    scopes: frozenset[str]
    state: str
    nonce: str
    pkce_challenge: str
    task_id: str


@dataclass(frozen=True)
class TaskPolicy:
    tenant_id: str
    task_id: str
    owner_subject: str
    scope: str
    scopes: frozenset[str]
    constraints: JsonObject
    amount_limit_fen: int
    call_limit: int
    task_expires_at: datetime
    active: bool
    version: int


@dataclass(frozen=True)
class AuthorizeRequestView:
    request_id: str
    tenant_id: str
    task_id: str
    client_id: str
    scope: str
    available_scope: str
    amount_limit_fen: int
    call_limit: int
    task_expires_at: int
    constraints: JsonObject
    policy_version: int
    delegation_depth: int
    csrf_token: str


@dataclass(frozen=True)
class ConsentRedirect:
    location: str


def _redirect(uri: str, params: Mapping[str, str]) -> str:
    parts = urlsplit(uri)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _policy_snapshot(policy: TaskPolicy) -> bytes:
    return canonical_json_bytes(
        {
            "tenant_id": policy.tenant_id,
            "task_id": policy.task_id,
            "owner_subject": policy.owner_subject,
            "scope": policy.scope,
            "constraints": policy.constraints,
            "amount_limit_fen": policy.amount_limit_fen,
            "call_limit": policy.call_limit,
            "task_expires_at": policy.task_expires_at.isoformat(),
            "active": policy.active,
            "policy_version": policy.version,
            "delegation_depth": ROOT_DELEGATION_DEPTH,
        }
    )


def parse_authorize_params(params: object) -> AuthorizeParams:
    """Validate the exact browser authorization query/form against the profile."""
    if type(params) is not dict or set(params) != _AUTHORIZE_FIELDS:
        raise ConsentError("REQUEST_INVALID")
    if any(type(value) is not str for value in params.values()):
        raise ConsentError("REQUEST_INVALID")
    if params["response_type"] != "code":
        raise ConsentError("RESPONSE_TYPE_UNSUPPORTED")
    if type(params["client_id"]) is not str or not _SAFE_ID.fullmatch(params["client_id"]):
        raise ConsentError("CLIENT_INVALID")
    if type(params["ag_task_id"]) is not str or not _SAFE_ID.fullmatch(params["ag_task_id"]):
        raise ConsentError("TASK_INVALID")
    redirect = urlsplit(params["redirect_uri"])
    if (
        redirect.scheme != "https"
        or not redirect.netloc
        or redirect.username is not None
        or redirect.password is not None
        or redirect.fragment
    ):
        raise ConsentError("REDIRECT_INVALID")
    try:
        scopes = parse_scope(params["scope"])
    except ClaimsError as exc:
        raise ConsentError("SCOPE_DENIED") from exc
    if "openid" not in scopes:
        raise ConsentError("SCOPE_DENIED")
    if not _STATE.fullmatch(params["state"]):
        raise ConsentError("STATE_INVALID")
    if params["code_challenge_method"] != "S256":
        raise ConsentError("PKCE_METHOD_UNSUPPORTED")
    try:
        if len(b64url_decode(params["code_challenge"])) != 32:
            raise ConsentError("PKCE_CHALLENGE_INVALID")
        if len(b64url_decode(params["nonce"])) < 16 or len(params["nonce"]) > 128:
            raise ConsentError("NONCE_INVALID")
    except EncodingError as exc:
        raise ConsentError("REQUEST_INVALID") from exc
    return AuthorizeParams(
        client_id=params["client_id"],
        redirect_uri=params["redirect_uri"],
        scope=" ".join(sorted(scopes)),
        scopes=scopes,
        state=params["state"],
        nonce=params["nonce"],
        pkce_challenge=params["code_challenge"],
        task_id=params["ag_task_id"],
    )


class ConsentService:
    """Persist one request per session and issue a code only on real consent."""

    def __init__(
        self,
        dsn: str,
        *,
        clients: Mapping[str, AuthorizeClient],
        sessions: LoginService,
        codes: AuthorizationCodeService,
        request_ttl_seconds: int = 300,
        connector: Callable[..., psycopg.Connection] = psycopg.connect,
    ) -> None:
        if not clients or sessions is None or codes is None:
            raise ValueError("clients, login sessions and code service are required")
        if type(request_ttl_seconds) is not int or not 30 <= request_ttl_seconds <= 3600:
            raise ValueError("request_ttl_seconds must be an integer within [30, 3600]")
        for key, client in clients.items():
            redirect = urlsplit(client.redirect_uri)
            if (
                not isinstance(client, AuthorizeClient)
                or key != client.client_id
                or not _SAFE_ID.fullmatch(key)
                or not _SAFE_ID.fullmatch(client.tenant_id)
                or redirect.scheme != "https"
                or not redirect.netloc
                or redirect.username is not None
                or redirect.password is not None
                or redirect.fragment
                or type(client.active) is not bool
            ):
                raise ValueError("invalid trusted authorize client registration")
        self._dsn = dsn
        self._clients = dict(clients)
        self._sessions = sessions
        self._codes = codes
        self._request_ttl = request_ttl_seconds
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

    def create_request(
        self, *, session_token: str, csrf_token: str, params: object
    ) -> AuthorizeRequestView:
        """Validate and persist a request bound to the live session and policy."""
        context = self._sessions.verify_session_csrf(
            session_token=session_token, csrf_token=csrf_token
        )
        parsed = parse_authorize_params(params)
        client = self._clients.get(parsed.client_id)
        if client is None or not client.active:
            raise ConsentError("CLIENT_INVALID")
        if client.redirect_uri != parsed.redirect_uri:
            raise ConsentError("REDIRECT_INVALID")
        if client.tenant_id != context.tenant_id:
            raise ConsentError("CLIENT_INVALID")
        try:
            with self._connect() as conn:
                with conn.transaction():
                    now = store.db_now_epoch(conn)
                    policy = self._load_policy(conn, client.tenant_id, parsed.task_id)
                    if policy is None or not policy.active:
                        raise ConsentError("TASK_NOT_FOUND")
                    if policy.owner_subject != context.subject:
                        raise ConsentError("NOT_TASK_OWNER")
                    if now >= policy.task_expires_at.timestamp():
                        raise ConsentError("TASK_EXPIRED")
                    if not parsed.scopes <= policy.scopes:
                        raise ConsentError("SCOPE_DENIED")
                    request_id = "authreq-" + uuid.uuid4().hex
                    conn.execute(
                        "INSERT INTO ag_authorization_requests "
                        "(request_id, session_sha256, tenant_id, task_id, subject, client_id, "
                        " redirect_uri, scope, pkce_challenge, nonce, state, "
                        " policy_snapshot_json, status, expires_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', "
                        "clock_timestamp() + (%s * interval '1 second'))",
                        (
                            request_id,
                            context.session_sha256,
                            client.tenant_id,
                            parsed.task_id,
                            context.subject,
                            client.client_id,
                            parsed.redirect_uri,
                            parsed.scope,
                            parsed.pkce_challenge,
                            parsed.nonce,
                            parsed.state,
                            _policy_snapshot(policy),
                            self._request_ttl,
                        ),
                    )
                    self._insert_event(
                        conn,
                        event_type="authorize_request",
                        tenant_id=client.tenant_id,
                        subject=context.subject,
                        request_id=request_id,
                        detail={"client_id": client.client_id, "task_id": parsed.task_id},
                    )
                    policy_expiry = int(policy.task_expires_at.timestamp())
        except psycopg.Error as exc:
            raise ConsentError("TRUSTED_STATE_UNAVAILABLE") from exc
        return AuthorizeRequestView(
            request_id=request_id,
            tenant_id=client.tenant_id,
            task_id=parsed.task_id,
            client_id=client.client_id,
            scope=parsed.scope,
            available_scope=policy.scope,
            amount_limit_fen=policy.amount_limit_fen,
            call_limit=policy.call_limit,
            task_expires_at=policy_expiry,
            constraints=policy.constraints,
            policy_version=policy.version,
            delegation_depth=ROOT_DELEGATION_DEPTH,
            csrf_token=csrf_token,
        )

    def decide(
        self,
        *,
        session_token: str,
        csrf_token: str,
        request_id: str,
        decision: str,
    ) -> ConsentRedirect:
        """Approve or deny once; only approval may issue an authorization code."""
        if (
            type(request_id) is not str
            or not _SAFE_ID.fullmatch(request_id)
            or decision not in _DECISIONS
        ):
            raise ConsentError("INVALID_DECISION")
        self._sessions.verify_session_csrf(session_token=session_token, csrf_token=csrf_token)
        try:
            with self._connect() as conn:
                with conn.transaction():
                    row = conn.execute(
                        "SELECT session_sha256, tenant_id, task_id, subject, client_id, "
                        " redirect_uri, scope, pkce_challenge, nonce, state, status, "
                        " expires_at, policy_snapshot_json "
                        "FROM ag_authorization_requests WHERE request_id = %s FOR UPDATE",
                        (request_id,),
                    ).fetchone()
                    if row is None:
                        raise ConsentError("REQUEST_NOT_FOUND")
                    (
                        session_hash,
                        tenant_id,
                        task_id,
                        subject,
                        client_id,
                        redirect_uri,
                        scope,
                        challenge,
                        nonce,
                        state,
                        status,
                        request_expires_at,
                        policy_snapshot,
                    ) = row
                    context = self._sessions.verify_session_csrf_locked(
                        conn, session_token=session_token, csrf_token=csrf_token
                    )
                    if bytes(session_hash) != context.session_sha256 or subject != context.subject:
                        raise ConsentError("REQUEST_NOT_FOUND")
                    if tenant_id != context.tenant_id:
                        raise ConsentError("REQUEST_NOT_FOUND")
                    if status != "pending":
                        raise ConsentError("ALREADY_DECIDED")
                    if store.db_now_epoch(conn) >= request_expires_at.timestamp():
                        raise ConsentError("REQUEST_EXPIRED")
                    if decision == "deny":
                        event_id = self._insert_event(
                            conn,
                            event_type="consent",
                            tenant_id=tenant_id,
                            subject=subject,
                            request_id=request_id,
                            detail={"decision": "deny"},
                        )
                        self._mark_decided(conn, request_id, "denied", event_id)
                        return ConsentRedirect(
                            _redirect(redirect_uri, {"error": "access_denied", "state": state})
                        )
                    policy = self._load_policy(conn, tenant_id, task_id, lock=True)
                    if policy is None or not policy.active:
                        raise ConsentError("TASK_UNAVAILABLE")
                    if policy.owner_subject != context.subject:
                        raise ConsentError("NOT_TASK_OWNER")
                    if policy_snapshot is None or bytes(policy_snapshot) != _policy_snapshot(
                        policy
                    ):
                        raise ConsentError("TASK_POLICY_CHANGED")
                    if store.db_now_epoch(conn) >= policy.task_expires_at.timestamp():
                        raise ConsentError("TASK_EXPIRED")
                    scopes = parse_scope(scope)
                    if not scopes <= policy.scopes:
                        raise ConsentError("SCOPE_DENIED")
                    event_id = self._insert_event(
                        conn,
                        event_type="consent",
                        tenant_id=tenant_id,
                        subject=subject,
                        request_id=request_id,
                        detail={"decision": "approve"},
                    )
                    self._mark_decided(conn, request_id, "approved", event_id)
                    approved = ApprovedAuthorization(
                        tenant_id=tenant_id,
                        task_id=task_id,
                        subject=subject,
                        client_id=client_id,
                        redirect_uri=redirect_uri,
                        pkce_challenge=challenge,
                        scope=" ".join(sorted(scopes)),
                        constraints=policy.constraints,
                        amount_limit_fen=policy.amount_limit_fen,
                        call_limit=policy.call_limit,
                        task_expires_at=int(policy.task_expires_at.timestamp()),
                        auth_time=context.auth_time,
                        nonce=nonce,
                        consent_ref=event_id,
                    )
                    result = self._codes.issue_code(approved, conn=conn)
                    return ConsentRedirect(
                        _redirect(redirect_uri, {"code": result.code, "state": state})
                    )
        except ConsentError:
            raise
        except LoginError as exc:
            raise ConsentError(exc.code) from exc
        except AuthorizationCodeError as exc:
            raise ConsentError(exc.code) from exc
        except psycopg.Error as exc:
            raise ConsentError("TRUSTED_STATE_UNAVAILABLE") from exc

    def _load_policy(
        self, conn: psycopg.Connection, tenant_id: str, task_id: str, *, lock: bool = False
    ) -> TaskPolicy | None:
        row = conn.execute(
            "SELECT tenant_id, task_id, owner_subject, scope, constraints_json, "
            " amount_limit_fen, call_limit, task_expires_at, active, policy_version "
            "FROM ag_task_policies WHERE tenant_id = %s AND task_id = %s"
            + (" FOR UPDATE" if lock else ""),
            (tenant_id, task_id),
        ).fetchone()
        if row is None:
            return None
        try:
            scopes = parse_scope(row[3])
            constraints = parse_constraints(load_strict_json(row[4]))
        except (ClaimsError, EncodingError, TypeError) as exc:
            raise ConsentError("TRUSTED_STATE_INVALID") from exc
        return TaskPolicy(
            tenant_id=row[0],
            task_id=row[1],
            owner_subject=row[2],
            scope=row[3],
            scopes=scopes,
            constraints=constraints,
            amount_limit_fen=row[5],
            call_limit=row[6],
            task_expires_at=row[7],
            active=row[8],
            version=row[9],
        )

    @staticmethod
    def _insert_event(
        conn: psycopg.Connection,
        *,
        event_type: str,
        tenant_id: str,
        subject: str,
        request_id: str,
        detail: JsonObject,
    ) -> str:
        event_id = "event-" + uuid.uuid4().hex
        conn.execute(
            "INSERT INTO ag_auth_events "
            "(event_id, event_type, tenant_id, subject, request_id, detail_json) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (event_id, event_type, tenant_id, subject, request_id, canonical_json_bytes(detail)),
        )
        return event_id

    @staticmethod
    def _mark_decided(
        conn: psycopg.Connection, request_id: str, status: str, consent_ref: str
    ) -> None:
        conn.execute(
            "UPDATE ag_authorization_requests "
            "SET status = %s, consent_ref = %s, decided_at = clock_timestamp() "
            "WHERE request_id = %s",
            (status, consent_ref, request_id),
        )
