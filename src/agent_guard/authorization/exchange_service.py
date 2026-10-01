"""Transactional AS-owned child issuance for the GM-MVP-1 exchange profile.

Only an independently authenticated OAuth client may call ``exchange``.  The
service owns the issuance decision; the preflight is not an authorization to
insert a grant or to return a previously issued token.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg
from tongsuopy.crypto.asymciphers.ec import EllipticCurvePrivateKey, EllipticCurvePublicKey

from agent_guard.authorization.claims import (
    GATEWAY_AUDIENCE,
    ClaimsError,
    validate_access_claims,
    validate_child,
)
from agent_guard.authorization.exchange import (
    AuthenticatedExchange,
    ExchangeError,
    ExchangePreflight,
)
from agent_guard.authorization.policy import DelegationError, GrantPolicy
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.contracts.ledger import ErrorCode, LedgerError
from agent_guard.crypto.sm import (
    InvalidSm2Signature,
    sign_compact_jws,
    sm3_b64url,
    verify_compact_jws,
)
from agent_guard.identity.resolver import IdentityError, IdentityResolver
from agent_guard.ledger import store


class TokenExchangeError(ValueError):
    """A Token Exchange request was rejected without exposing trusted state."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TokenExchangeResult:
    access_token: str
    issued_token_type: str
    token_type: str
    expires_in: int
    scope: str
    ag_grant_id: str
    ag_parent_id: str
    ag_root_id: str


def _utc_epoch(value: int) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


class TokenExchangeService:
    """Issue one immutable child per parent/requester/business key.

    All active key rows, the task and root-to-parent grants use the same lock
    order as the execution ledger and revocation path.  An idempotent retry
    still needs a newly signed proof and all current state checks.
    """

    def __init__(
        self,
        dsn: str,
        *,
        issuer: str,
        token_endpoint: str,
        signing_key: EllipticCurvePrivateKey,
        signing_kid: str,
        identities: IdentityResolver,
        verification_keys: Mapping[str, EllipticCurvePublicKey] | None = None,
        connector: Callable[..., psycopg.Connection] = psycopg.connect,
    ) -> None:
        self._dsn = dsn
        self._issuer = issuer
        self._token_endpoint = token_endpoint
        self._signing_key = signing_key
        self._signing_kid = signing_kid
        self._identities = identities
        self._connector = connector
        trusted = (
            dict(verification_keys)
            if verification_keys is not None
            else {signing_kid: signing_key.public_key()}
        )
        if signing_kid not in trusted or not all(
            isinstance(key, EllipticCurvePublicKey) for key in trusted.values()
        ):
            raise ValueError("trusted AS verification keys must include the signing kid")
        self._trusted_keys = trusted
        self._preflight = ExchangePreflight(
            issuer=issuer,
            token_endpoint=token_endpoint,
            as_keys=self._trusted_keys,
            identities=identities,
        )
        self._policy = GrantPolicy(issuer=issuer)

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

    def exchange(
        self,
        *,
        raw_form: bytes,
        proof: str,
        authenticated_client_id: str,
    ) -> TokenExchangeResult:
        """Authenticate, recheck under locks, and return a signed child token."""
        try:
            with self._connect() as conn:
                authenticated = self._preflight.authenticate(
                    raw_form=raw_form,
                    proof=proof,
                    authenticated_client_id=authenticated_client_id,
                    now=int(store.db_now_epoch(conn)),
                )
                with conn.transaction():
                    return self._exchange_tx(conn, authenticated, proof)
        except ExchangeError as exc:
            raise TokenExchangeError("SUBJECT_OR_PROOF_INVALID") from exc
        except (DelegationError, ClaimsError) as exc:
            raise TokenExchangeError("DELEGATION_INVALID") from exc
        except IdentityError as exc:
            raise TokenExchangeError("CLIENT_KEY_INVALID") from exc
        except LedgerError as exc:
            code = "PROOF_REPLAY" if exc.code is ErrorCode.REPLAY else "TRUSTED_STATE_INVALID"
            raise TokenExchangeError(code) from exc
        except psycopg.Error as exc:
            raise TokenExchangeError("TRUSTED_STATE_UNAVAILABLE") from exc

    def _exchange_tx(
        self, conn: psycopg.Connection, authenticated: AuthenticatedExchange, proof: str
    ) -> TokenExchangeResult:
        parent_claims = authenticated.parent.raw
        path = store.load_path(conn, parent_claims["ag_grant_id"])
        tenant = parent_claims["ag_tenant_id"]
        task_id = parent_claims["ag_task_id"]
        recipient = authenticated.recipient.registration
        keys = [(g.tenant_id, g.holder_client_id, g.holder_kid) for g in path]
        keys.append((tenant, recipient.client_id, recipient.kid))
        principals = store.lock_principals(conn, keys)
        task = store.lock_task(conn, tenant, task_id)
        grants = store.lock_grants_root_to_leaf(conn, [g.grant_id for g in path])
        if (
            len(grants) != len(path)
            or task.root_grant_id != grants[0].grant_id
            or parent_claims["ag_root_id"] != grants[0].grant_id
            or parent_claims["ag_grant_id"] != grants[-1].grant_id
        ):
            raise TokenExchangeError("SUBJECT_INVALID")
        now_float = store.db_now_epoch(conn)
        now = int(now_float)
        if authenticated.proof_iat > now_float + 5 or now_float >= authenticated.proof_exp:
            raise TokenExchangeError("PROOF_EXPIRED")
        for position, grant in enumerate(grants):
            if (
                grant.depth != position
                or grant.root_grant_id != grants[0].grant_id
                or grant.tenant_id != tenant
                or grant.task_id != task_id
                or grant.subject != parent_claims["sub"]
                or (position > 0 and grant.parent_grant_id != grants[position - 1].grant_id)
                or (position == 0 and grant.parent_grant_id is not None)
            ):
                raise TokenExchangeError("SUBJECT_INVALID")
            key = (tenant, grant.holder_client_id, grant.holder_kid)
            if key not in principals or not principals[key].active:
                raise TokenExchangeError("CLIENT_KEY_INVALID")
            if grant.revoked:
                raise TokenExchangeError("REVOKED")
            if (
                now_float < grant.not_before.timestamp()
                or now_float >= grant.expires_at.timestamp()
            ):
                raise TokenExchangeError("SUBJECT_EXPIRED")
        recipient_key = (tenant, recipient.client_id, recipient.kid)
        if recipient_key not in principals or not principals[recipient_key].active:
            raise TokenExchangeError("CLIENT_KEY_INVALID")
        if now_float >= parent_claims["exp"]:
            raise TokenExchangeError("SUBJECT_EXPIRED")
        self._check_snapshots(conn, grants, authenticated, now)

        # Preserve exact business intent without duplicating the raw bearer
        # token in the delegation table; its immutable token snapshot is held
        # separately in ag_grant_tokens.
        intent = dict(authenticated.form)
        intent["subject_token"] = authenticated.token_digest
        intent_bytes = canonical_json_bytes(intent)
        intent_sm3 = sm3_b64url(intent_bytes)
        parent_id = grants[-1].grant_id
        delegation_key = authenticated.form["ag_delegation_key"]
        existing = conn.execute(
            "SELECT intent_sm3, intent_json, child_grant_id FROM ag_delegations "
            "WHERE parent_grant_id = %s AND requesting_client_id = %s "
            "AND delegation_key = %s",
            (parent_id, grants[-1].holder_client_id, delegation_key),
        ).fetchone()
        if existing is not None and (
            existing[0] != intent_sm3 or bytes(existing[1]) != intent_bytes
        ):
            raise TokenExchangeError("DELEGATION_KEY_CONFLICT")

        evidence_id = "exchange-" + uuid.uuid4().hex
        store.record_proof(
            conn,
            holder_kid=grants[-1].holder_kid,
            purpose="delegate",
            endpoint=self._token_endpoint,
            proof_jti=authenticated.proof_jti,
            proof_digest=authenticated.proof_digest,
            evidence_ref=evidence_id,
        )
        if existing is not None:
            child_id = existing[2]
            result = self._retry_result(conn, grants, child_id, authenticated, now_float)
        else:
            child = self._policy.validate_child(
                authenticated.parent,
                authenticated.requested_child,
                authenticated.recipient,
                now=now,
            )
            if child.expires_at <= now_float:
                raise TokenExchangeError("SUBJECT_EXPIRED")
            child_id = "grant-" + uuid.uuid4().hex
            actor = {"sub": child.recipient_did, "act": parent_claims["act"]}
            payload = {
                "iss": self._issuer,
                "sub": child.subject,
                "aud": GATEWAY_AUDIENCE,
                "iat": now,
                "nbf": now,
                "exp": child.expires_at,
                "jti": "token-" + uuid.uuid4().hex,
                "client_id": child.recipient_client_id,
                "scope": child.scope,
                "act": actor,
                "ag_profile": "GM-MVP-1",
                "ag_tenant_id": child.tenant_id,
                "ag_task_id": child.task_id,
                "ag_grant_id": child_id,
                "ag_parent_id": parent_id,
                "ag_root_id": child.root_grant_id,
                "ag_delegation_remaining": child.delegation_remaining,
                "ag_limits": {
                    "currency": "CNY",
                    "amount_fen": child.amount_limit_fen,
                    "calls": child.call_limit,
                },
                "ag_constraints": load_strict_json(child.constraints_json),
                "ag_cnf": {"kid": child.recipient_kid, "spki_sm3": child.recipient_spki_sm3},
            }
            token = sign_compact_jws(
                self._signing_key,
                payload,
                key_id=self._signing_kid,
                token_type="ag-at+jwt",
            )
            conn.execute(
                "INSERT INTO ag_grants "
                "(grant_id, parent_grant_id, root_grant_id, tenant_id, task_id, subject, "
                "holder_client_id, holder_kid, depth, not_before, expires_at, "
                "amount_limit, call_limit) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    child_id,
                    parent_id,
                    child.root_grant_id,
                    tenant,
                    task_id,
                    child.subject,
                    child.recipient_client_id,
                    child.recipient_kid,
                    grants[-1].depth + 1,
                    _utc_epoch(now),
                    _utc_epoch(child.expires_at),
                    child.amount_limit_fen,
                    child.call_limit,
                ),
            )
            conn.execute(
                "INSERT INTO ag_grant_tokens "
                "(grant_id, token_jws, token_sm3, scope, constraints_json, actor_json, "
                "holder_spki_sm3, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    child_id,
                    token,
                    sm3_b64url(token.encode("ascii")),
                    child.scope,
                    child.constraints_json,
                    canonical_json_bytes(actor),
                    child.recipient_spki_sm3,
                    _utc_epoch(child.expires_at),
                ),
            )
            conn.execute(
                "INSERT INTO ag_delegations "
                "(parent_grant_id, requesting_client_id, delegation_key, intent_sm3, "
                "intent_json, child_grant_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    parent_id,
                    grants[-1].holder_client_id,
                    delegation_key,
                    intent_sm3,
                    intent_bytes,
                    child_id,
                ),
            )
            result = self._result(token, payload, now_float)
        conn.execute(
            "INSERT INTO ag_exchange_evidence "
            "(evidence_id, parent_grant_id, child_grant_id, request_sm3, proof_jws) "
            "VALUES (%s, %s, %s, %s, %s)",
            (evidence_id, parent_id, child_id, authenticated.request_digest, proof),
        )
        return result

    def _check_snapshots(
        self,
        conn: psycopg.Connection,
        grants: list[store.GrantRow],
        authenticated: AuthenticatedExchange,
        now: int,
    ) -> None:
        previous = None
        for grant in grants:
            row = conn.execute(
                "SELECT token_jws, token_sm3, scope, constraints_json, actor_json, "
                "holder_spki_sm3, expires_at FROM ag_grant_tokens WHERE grant_id = %s",
                (grant.grant_id,),
            ).fetchone()
            if row is None:
                raise TokenExchangeError("SUBJECT_INVALID")
            token, digest, scope, constraints, actor, holder_spki, expires = row
            try:
                claims = validate_access_claims(
                    verify_compact_jws(
                        token, expected_type="ag-at+jwt", trusted_keys=self._trusted_keys
                    ),
                    issuer=self._issuer,
                    now=now,
                )
                if previous is not None:
                    validate_child(previous, claims)
            except (ClaimsError, InvalidSm2Signature, ValueError) as exc:
                raise TokenExchangeError("SUBJECT_INVALID") from exc
            raw = claims.raw
            if (
                digest != sm3_b64url(token.encode("ascii"))
                or raw["ag_grant_id"] != grant.grant_id
                or raw["ag_parent_id"] != grant.parent_grant_id
                or raw["ag_root_id"] != grant.root_grant_id
                or raw["ag_tenant_id"] != grant.tenant_id
                or raw["ag_task_id"] != grant.task_id
                or raw["sub"] != grant.subject
                or raw["client_id"] != grant.holder_client_id
                or raw["ag_cnf"]["kid"] != grant.holder_kid
                or raw["ag_cnf"]["spki_sm3"] != holder_spki
                or raw["ag_limits"]["amount_fen"] != grant.amount_limit
                or raw["ag_limits"]["calls"] != grant.call_limit
                or raw["scope"] != scope
                or canonical_json_bytes(raw["ag_constraints"]) != bytes(constraints)
                or canonical_json_bytes(raw["act"]) != bytes(actor)
                or raw["nbf"] != int(grant.not_before.timestamp())
                or raw["exp"] != int(expires.timestamp())
                or expires != grant.expires_at
            ):
                raise TokenExchangeError("SUBJECT_INVALID")
            previous = claims
            if grant.grant_id == authenticated.parent.raw["ag_grant_id"]:
                if token != authenticated.subject_token or raw != authenticated.parent.raw:
                    raise TokenExchangeError("SUBJECT_INVALID")

    def _retry_result(
        self,
        conn: psycopg.Connection,
        grants: list[store.GrantRow],
        child_id: str,
        authenticated: AuthenticatedExchange,
        now_float: float,
    ) -> TokenExchangeResult:
        child = store.load_path(conn, child_id)[-1]
        parent = grants[-1]
        recipient = authenticated.recipient.registration
        if (
            child.parent_grant_id != parent.grant_id
            or child.root_grant_id != parent.root_grant_id
            or child.tenant_id != parent.tenant_id
            or child.task_id != parent.task_id
            or child.subject != parent.subject
            or child.depth != parent.depth + 1
            or child.holder_client_id != recipient.client_id
            or child.holder_kid != recipient.kid
            or child.revoked
            or now_float < child.not_before.timestamp()
            or now_float >= child.expires_at.timestamp()
        ):
            raise TokenExchangeError("CHILD_INACTIVE")
        row = conn.execute(
            "SELECT token_jws, token_sm3, scope, constraints_json, actor_json, "
            "holder_spki_sm3, expires_at FROM ag_grant_tokens WHERE grant_id = %s",
            (child_id,),
        ).fetchone()
        if row is None:
            raise TokenExchangeError("CHILD_INACTIVE")
        token, digest, scope, constraints, actor, holder_spki, expires = row
        try:
            payload = verify_compact_jws(
                token, expected_type="ag-at+jwt", trusted_keys=self._trusted_keys
            )
            claims = validate_access_claims(payload, issuer=self._issuer, now=int(now_float))
            validate_child(authenticated.parent, claims)
        except (ClaimsError, InvalidSm2Signature, ValueError) as exc:
            raise TokenExchangeError("CHILD_INACTIVE") from exc
        if (
            digest != sm3_b64url(token.encode("ascii"))
            or payload["ag_grant_id"] != child_id
            or payload["ag_parent_id"] != parent.grant_id
            or payload["ag_root_id"] != parent.root_grant_id
            or payload["client_id"] != recipient.client_id
            or payload["act"]["sub"] != recipient.did
            or payload["ag_cnf"] != {"kid": recipient.kid, "spki_sm3": recipient.spki_sm3}
            or holder_spki != recipient.spki_sm3
            or payload["scope"] != scope
            or canonical_json_bytes(payload["ag_constraints"]) != bytes(constraints)
            or canonical_json_bytes(payload["act"]) != bytes(actor)
            or payload["ag_limits"]["amount_fen"] != child.amount_limit
            or payload["ag_limits"]["calls"] != child.call_limit
            or payload["nbf"] != int(child.not_before.timestamp())
            or payload["exp"] != int(expires.timestamp())
            or expires != child.expires_at
        ):
            raise TokenExchangeError("CHILD_INACTIVE")
        return self._result(token, payload, now_float)

    @staticmethod
    def _result(token: str, payload: dict, now_float: float) -> TokenExchangeResult:
        return TokenExchangeResult(
            access_token=token,
            issued_token_type="urn:ietf:params:oauth:token-type:access_token",
            token_type="AGPoP",
            expires_in=max(0, payload["exp"] - int(now_float)),
            scope=payload["scope"],
            ag_grant_id=payload["ag_grant_id"],
            ag_parent_id=payload["ag_parent_id"],
            ag_root_id=payload["ag_root_id"],
        )
