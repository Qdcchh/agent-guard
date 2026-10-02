"""Transactional one-use authorization-code redemption and root issuance.

Only a separately authenticated login/consent component may construct an
``ApprovedAuthorization`` and call ``issue_code``. There is deliberately no
public HTTP shortcut that accepts a claimed user ID as login or consent.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import psycopg
from tongsuopy.crypto.asymciphers.ec import EllipticCurvePrivateKey

from agent_guard.authorization.claims import ClaimsError, parse_constraints, parse_scope
from agent_guard.authorization.code import CodeExchangeError, CodeExchangePreflight
from agent_guard.contracts.encoding import (
    MAX_SAFE_INTEGER,
    b64url_decode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.contracts.ledger import ErrorCode, LedgerError
from agent_guard.crypto.sm import sign_compact_jws, sm3_b64url
from agent_guard.identity.resolver import IdentityError, IdentityResolver
from agent_guard.ledger import store
from agent_guard.ledger.provisioning import TaskAlreadyInitialized, create_task_root

_SAFE_ID = re.compile(r"[\x21-\x7e]{1,128}\Z", re.ASCII)
ROOT_DELEGATION_DEPTH = 2


class AuthorizationCodeError(ValueError):
    """A trusted consent/code request cannot be issued or redeemed."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ApprovedAuthorization:
    """Snapshot from a real authenticated user session and confirmed consent."""

    tenant_id: str
    task_id: str
    subject: str
    client_id: str
    redirect_uri: str
    pkce_challenge: str
    scope: str
    constraints: dict
    amount_limit_fen: int
    call_limit: int
    task_expires_at: int
    auth_time: int
    nonce: str
    consent_ref: str


@dataclass(frozen=True)
class CodeIssueResult:
    code: str
    expires_in: int


@dataclass(frozen=True)
class CodeRedeemResult:
    access_token: str
    id_token: str
    token_type: str
    expires_in: int
    scope: str
    ag_grant_id: str
    ag_task_id: str


def _id(value: object, name: str) -> str:
    if type(value) is not str or not _SAFE_ID.fullmatch(value):
        raise AuthorizationCodeError(f"INVALID_{name.upper()}")
    return value


def _utc_epoch(value: int) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


class AuthorizationCodeService:
    """Use the A1 task/root uniqueness constraint as the code redemption boundary."""

    def __init__(
        self,
        dsn: str,
        *,
        issuer: str,
        token_endpoint: str,
        signing_key: EllipticCurvePrivateKey,
        signing_kid: str,
        identities: IdentityResolver,
        connector: Callable[..., psycopg.Connection] = psycopg.connect,
    ) -> None:
        if type(issuer) is not str or not issuer.startswith("https://"):
            raise ValueError("fixed HTTPS issuer required")
        self._dsn = dsn
        self._issuer = issuer
        self._signing_key = signing_key
        self._signing_kid = signing_kid
        self._identities = identities
        self._connector = connector
        self._preflight = CodeExchangePreflight(
            token_endpoint=token_endpoint, identities=identities
        )
        self._token_endpoint = token_endpoint

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

    def issue_code(
        self, approved: ApprovedAuthorization, *, conn: psycopg.Connection | None = None
    ) -> CodeIssueResult:
        """Persist a hashed 60-second code after a trusted consent decision."""
        if not isinstance(approved, ApprovedAuthorization):
            raise AuthorizationCodeError("CONSENT_REQUIRED")
        for name in ("tenant_id", "task_id", "subject", "client_id", "consent_ref"):
            _id(getattr(approved, name), name)
        redirect = urlsplit(approved.redirect_uri)
        if redirect.scheme != "https" or not redirect.netloc or redirect.fragment:
            raise AuthorizationCodeError("REDIRECT_INVALID")
        try:
            if len(b64url_decode(approved.nonce)) < 16:
                raise AuthorizationCodeError("NONCE_INVALID")
            if len(b64url_decode(approved.pkce_challenge)) != 32:
                raise AuthorizationCodeError("PKCE_CHALLENGE_INVALID")
            scopes = parse_scope(approved.scope)
            constraints = parse_constraints(approved.constraints)
        except (ValueError, TypeError, ClaimsError) as exc:
            raise AuthorizationCodeError("CONSENT_SNAPSHOT_INVALID") from exc
        if "openid" not in scopes:
            raise AuthorizationCodeError("OPENID_SCOPE_REQUIRED")
        for name in ("amount_limit_fen", "call_limit", "task_expires_at", "auth_time"):
            value = getattr(approved, name)
            if type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER:
                raise AuthorizationCodeError("CONSENT_SNAPSHOT_INVALID")
        if approved.task_expires_at > 253402300799:
            raise AuthorizationCodeError("CONSENT_SNAPSHOT_INVALID")
        try:
            holder = self._identities.resolve_registered(
                approved.client_id, approved.tenant_id, "authentication"
            )
        except IdentityError as exc:
            raise AuthorizationCodeError("CLIENT_KEY_INVALID") from exc
        code = secrets.token_urlsafe(32)
        code_sha256 = hashlib.sha256(code.encode("ascii")).digest()
        try:
            with self._connect() if conn is None else nullcontext(conn) as active_conn:
                with active_conn.transaction():
                    now_epoch = store.db_now_epoch(active_conn)
                    now = datetime.fromtimestamp(now_epoch, tz=timezone.utc)
                    if approved.task_expires_at <= now_epoch or approved.auth_time > now_epoch:
                        raise AuthorizationCodeError("CONSENT_SNAPSHOT_EXPIRED")
                    if active_conn.execute(
                        "SELECT 1 FROM ag_tasks WHERE tenant_id = %s AND task_id = %s",
                        (approved.tenant_id, approved.task_id),
                    ).fetchone():
                        raise AuthorizationCodeError("TASK_ALREADY_AUTHORIZED")
                    active_conn.execute(
                        "INSERT INTO ag_authorization_codes "
                        "(code_sha256, tenant_id, task_id, subject, client_id, holder_kid, "
                        "holder_spki_sm3, redirect_uri, pkce_challenge, nonce, auth_time, "
                        "scope, constraints_json, amount_limit_fen, call_limit, task_expires_at, "
                        "consent_ref, consented_at, expires_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                        "%s, %s, %s, %s, %s)",
                        (
                            code_sha256,
                            approved.tenant_id,
                            approved.task_id,
                            approved.subject,
                            approved.client_id,
                            holder.registration.kid,
                            holder.registration.spki_sm3,
                            approved.redirect_uri,
                            approved.pkce_challenge,
                            approved.nonce,
                            approved.auth_time,
                            " ".join(sorted(scopes)),
                            canonical_json_bytes(constraints),
                            approved.amount_limit_fen,
                            approved.call_limit,
                            _utc_epoch(approved.task_expires_at),
                            approved.consent_ref,
                            now,
                            now + timedelta(seconds=60),
                        ),
                    )
        except psycopg.Error as exc:
            raise AuthorizationCodeError("TRUSTED_STATE_UNAVAILABLE") from exc
        return CodeIssueResult(code=code, expires_in=60)

    def redeem(
        self,
        *,
        raw_form: bytes,
        proof: str,
        authenticated_client_id: str,
        tenant_id: str,
        expected_redirect_uri: str,
    ) -> CodeRedeemResult:
        """Consume exactly once and create one root + signed token atomically."""
        try:
            with self._connect() as conn:
                pre = self._preflight.verify(
                    raw_form=raw_form,
                    proof=proof,
                    authenticated_client_id=authenticated_client_id,
                    tenant_id=tenant_id,
                    expected_redirect_uri=expected_redirect_uri,
                    now=int(store.db_now_epoch(conn)),
                )
                with conn.transaction():
                    row = conn.execute(
                        "SELECT tenant_id, task_id, subject, client_id, holder_kid, "
                        "holder_spki_sm3, redirect_uri, pkce_challenge, nonce, auth_time, "
                        "scope, constraints_json, amount_limit_fen, call_limit, task_expires_at, "
                        "expires_at, consumed_at "
                        "FROM ag_authorization_codes WHERE code_sha256 = %s FOR UPDATE",
                        (pre.code_sha256,),
                    ).fetchone()
                    if row is None or row[16] is not None:
                        raise AuthorizationCodeError("CODE_OR_PKCE_INVALID")
                    (
                        code_tenant,
                        task_id,
                        subject,
                        code_client,
                        holder_kid,
                        holder_spki_sm3,
                        redirect_uri,
                        challenge,
                        nonce,
                        auth_time,
                        scope,
                        constraints_json,
                        amount_limit,
                        call_limit,
                        task_expires_at,
                        code_expires_at,
                        _,
                    ) = row
                    if (
                        code_tenant != tenant_id
                        or code_client != authenticated_client_id
                        or holder_kid != pre.holder_kid
                        or holder_spki_sm3 != pre.holder_spki_sm3
                        or redirect_uri != pre.redirect_uri
                        or challenge != pre.pkce_challenge
                    ):
                        raise AuthorizationCodeError("CODE_OR_PKCE_INVALID")
                    keys = store.lock_principals(conn, [(tenant_id, code_client, holder_kid)])
                    principal = keys.get((tenant_id, code_client, holder_kid))
                    if principal is None or not principal.active:
                        raise AuthorizationCodeError("CLIENT_KEY_INVALID")
                    now_float = store.db_now_epoch(conn)
                    now = int(now_float)
                    if (
                        now_float >= code_expires_at.timestamp()
                        or now_float >= task_expires_at.timestamp()
                        or now_float >= pre.proof_exp
                        or pre.proof_iat > now_float + 5
                    ):
                        raise AuthorizationCodeError("CODE_OR_PROOF_EXPIRED")
                    evidence_id = "code-" + uuid.uuid4().hex
                    conn.execute(
                        "INSERT INTO ag_auth_evidence "
                        "(evidence_id, code_sha256, request_sm3, proof_jws) "
                        "VALUES (%s, %s, %s, %s)",
                        (evidence_id, pre.code_sha256, pre.request_digest, proof),
                    )
                    store.record_proof(
                        conn,
                        holder_kid=holder_kid,
                        purpose="code-exchange",
                        endpoint=self._token_endpoint,
                        proof_jti=pre.proof_jti,
                        proof_digest=pre.proof_digest,
                        evidence_ref=evidence_id,
                    )
                    root_id = "grant-" + uuid.uuid4().hex
                    token_exp = min(now + 300, int(task_expires_at.timestamp()))
                    if token_exp <= now:
                        raise AuthorizationCodeError("TASK_EXPIRED")
                    create_task_root(
                        conn,
                        tenant_id=tenant_id,
                        task_id=task_id,
                        grant_id=root_id,
                        subject=subject,
                        holder_client_id=code_client,
                        holder_kid=holder_kid,
                        amount_limit=amount_limit,
                        call_limit=call_limit,
                        not_before=_utc_epoch(now),
                        expires_at=_utc_epoch(token_exp),
                    )
                    constraints = load_strict_json(constraints_json)
                    actor = {"sub": pre.holder_did}
                    access_payload = {
                        "iss": self._issuer,
                        "sub": subject,
                        "aud": "https://gateway.agent-guard.test",
                        "iat": now,
                        "nbf": now,
                        "exp": token_exp,
                        "jti": "token-" + uuid.uuid4().hex,
                        "client_id": code_client,
                        "scope": scope,
                        "act": actor,
                        "ag_profile": "GM-MVP-1",
                        "ag_tenant_id": tenant_id,
                        "ag_task_id": task_id,
                        "ag_grant_id": root_id,
                        "ag_parent_id": None,
                        "ag_root_id": root_id,
                        "ag_delegation_remaining": ROOT_DELEGATION_DEPTH,
                        "ag_limits": {
                            "currency": "CNY",
                            "amount_fen": amount_limit,
                            "calls": call_limit,
                        },
                        "ag_constraints": constraints,
                        "ag_cnf": {"kid": holder_kid, "spki_sm3": holder_spki_sm3},
                    }
                    access_token = sign_compact_jws(
                        self._signing_key,
                        access_payload,
                        key_id=self._signing_kid,
                        token_type="ag-at+jwt",
                    )
                    id_token = sign_compact_jws(
                        self._signing_key,
                        {
                            "iss": self._issuer,
                            "sub": subject,
                            "aud": code_client,
                            "iat": now,
                            "exp": now + 300,
                            "auth_time": auth_time,
                            "nonce": nonce,
                        },
                        key_id=self._signing_kid,
                        token_type="ag-id+jwt",
                    )
                    conn.execute(
                        "INSERT INTO ag_grant_tokens "
                        "(grant_id, token_jws, token_sm3, scope, constraints_json, actor_json, "
                        "holder_spki_sm3, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            root_id,
                            access_token,
                            sm3_b64url(access_token.encode("ascii")),
                            scope,
                            constraints_json,
                            canonical_json_bytes(actor),
                            holder_spki_sm3,
                            _utc_epoch(token_exp),
                        ),
                    )
                    conn.execute(
                        "UPDATE ag_authorization_codes "
                        "SET consumed_at = clock_timestamp(), root_grant_id = %s "
                        "WHERE code_sha256 = %s",
                        (root_id, pre.code_sha256),
                    )
                    return CodeRedeemResult(
                        access_token=access_token,
                        id_token=id_token,
                        token_type="AGPoP",
                        expires_in=token_exp - now,
                        scope=scope,
                        ag_grant_id=root_id,
                        ag_task_id=task_id,
                    )
        except CodeExchangeError as exc:
            raise AuthorizationCodeError("CODE_OR_PKCE_INVALID") from exc
        except TaskAlreadyInitialized as exc:
            raise AuthorizationCodeError("TASK_ALREADY_AUTHORIZED") from exc
        except LedgerError as exc:
            code = "PROOF_REPLAY" if exc.code is ErrorCode.REPLAY else "TRUSTED_STATE_INVALID"
            raise AuthorizationCodeError(code) from exc
        except psycopg.Error as exc:
            raise AuthorizationCodeError("TRUSTED_STATE_UNAVAILABLE") from exc
