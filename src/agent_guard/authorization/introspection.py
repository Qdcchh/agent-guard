"""Read-only, fail-closed AS access-token introspection.

The caller must authenticate as the configured gateway service before using
this component. An ``active`` result is a snapshot, not permission to execute:
the gateway must still make its own locked accept decision.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import psycopg
from tongsuopy.crypto.asymciphers.ec import EllipticCurvePublicKey

from agent_guard.authorization.claims import (
    ClaimsError,
    validate_access_claims,
    validate_child,
)
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.contracts.ledger import LedgerError
from agent_guard.crypto.sm import InvalidSm2Signature, sm3_b64url, verify_compact_jws
from agent_guard.identity.resolver import IdentityError, IdentityResolver
from agent_guard.ledger import store


class IntrospectionError(RuntimeError):
    """The trusted state could not be read; the caller must fail closed."""


@dataclass(frozen=True)
class IntrospectionResult:
    active: bool
    claims: dict[str, object] | None = None

    def response(self) -> dict[str, object]:
        if not self.active or self.claims is None:
            return {"active": False}
        raw = self.claims
        return {
            "active": True,
            "iss": raw["iss"],
            "sub": raw["sub"],
            "aud": raw["aud"],
            "exp": raw["exp"],
            "scope": raw["scope"],
            "client_id": raw["client_id"],
            "act": raw["act"],
            "ag_grant_id": raw["ag_grant_id"],
            "ag_root_id": raw["ag_root_id"],
            "ag_cnf": raw["ag_cnf"],
        }


class IntrospectionService:
    """Check signed snapshots and the live authorization path under locks."""

    def __init__(
        self,
        dsn: str,
        *,
        issuer: str,
        as_keys: Mapping[str, EllipticCurvePublicKey],
        identities: IdentityResolver,
        connector: Callable[..., psycopg.Connection] = psycopg.connect,
    ) -> None:
        if type(issuer) is not str or not issuer.startswith("https://") or not as_keys:
            raise ValueError("fixed HTTPS issuer and trusted AS keys required")
        self._dsn = dsn
        self._issuer = issuer
        self._as_keys = dict(as_keys)
        self._identities = identities
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

    def inspect(self, token: str) -> IntrospectionResult:
        """Return only ``active:false`` for malformed, unknown or inactive tokens."""
        if type(token) is not str or not token.isascii() or not 1 <= len(token) <= 16384:
            return IntrospectionResult(False)
        try:
            raw = verify_compact_jws(token, expected_type="ag-at+jwt", trusted_keys=self._as_keys)
        except (InvalidSm2Signature, ValueError, TypeError):
            return IntrospectionResult(False)
        try:
            with self._connect() as conn:
                with conn.transaction():
                    now = store.db_now_epoch(conn)
                    leaf_claims = validate_access_claims(raw, issuer=self._issuer, now=int(now))
                    if now >= raw["exp"]:
                        return IntrospectionResult(False)
                    path = store.load_path(conn, raw["ag_grant_id"])
                    if not 1 <= len(path) <= 3:
                        return IntrospectionResult(False)
                    keys = [(g.tenant_id, g.holder_client_id, g.holder_kid) for g in path]
                    principals = store.lock_principals(conn, keys)
                    task = store.lock_task(conn, raw["ag_tenant_id"], raw["ag_task_id"])
                    grants = store.lock_grants_root_to_leaf(conn, [g.grant_id for g in path])
                    now = store.db_now_epoch(conn)
                    if (
                        now >= raw["exp"]
                        or task.root_grant_id != grants[0].grant_id
                        or raw["ag_root_id"] != grants[0].grant_id
                        or grants[-1].grant_id != raw["ag_grant_id"]
                    ):
                        return IntrospectionResult(False)
                    previous = None
                    for position, grant in enumerate(grants):
                        key = (grant.tenant_id, grant.holder_client_id, grant.holder_kid)
                        principal = principals.get(key)
                        if (
                            principal is None
                            or not principal.active
                            or grant.revoked
                            or now < grant.not_before.timestamp()
                            or now >= grant.expires_at.timestamp()
                            or grant.depth != position
                            or grant.root_grant_id != grants[0].grant_id
                            or grant.tenant_id != raw["ag_tenant_id"]
                            or grant.task_id != raw["ag_task_id"]
                            or grant.subject != raw["sub"]
                            or (position == 0 and grant.parent_grant_id is not None)
                            or (
                                position > 0
                                and grant.parent_grant_id != grants[position - 1].grant_id
                            )
                        ):
                            return IntrospectionResult(False)
                        row = conn.execute(
                            "SELECT token_jws, token_sm3, scope, constraints_json, "
                            "actor_json, holder_spki_sm3, expires_at "
                            "FROM ag_grant_tokens WHERE grant_id = %s",
                            (grant.grant_id,),
                        ).fetchone()
                        if row is None:
                            return IntrospectionResult(False)
                        saved_token, digest, scope, constraints, actor, spki_sm3, expires = row
                        claims = validate_access_claims(
                            verify_compact_jws(
                                saved_token,
                                expected_type="ag-at+jwt",
                                trusted_keys=self._as_keys,
                            ),
                            issuer=self._issuer,
                            now=int(now),
                        )
                        r = claims.raw
                        if (
                            now >= r["exp"]
                            or digest != sm3_b64url(saved_token.encode("ascii"))
                            or r["ag_grant_id"] != grant.grant_id
                            or r["ag_parent_id"] != grant.parent_grant_id
                            or r["ag_root_id"] != grant.root_grant_id
                            or r["ag_tenant_id"] != grant.tenant_id
                            or r["ag_task_id"] != grant.task_id
                            or r["sub"] != grant.subject
                            or r["client_id"] != grant.holder_client_id
                            or r["ag_cnf"]["kid"] != grant.holder_kid
                            or r["ag_cnf"]["spki_sm3"] != spki_sm3
                            or r["ag_limits"]["amount_fen"] != grant.amount_limit
                            or r["ag_limits"]["calls"] != grant.call_limit
                            or r["scope"] != scope
                            or canonical_json_bytes(r["ag_constraints"]) != bytes(constraints)
                            or canonical_json_bytes(r["act"]) != bytes(actor)
                            or r["nbf"] != int(grant.not_before.timestamp())
                            or r["exp"] != int(expires.timestamp())
                            or expires != grant.expires_at
                        ):
                            return IntrospectionResult(False)
                        if previous is not None:
                            validate_child(previous, claims)
                        identity = self._identities.resolve_registered(
                            grant.holder_client_id, grant.tenant_id, "capabilityInvocation"
                        )
                        if (
                            identity.registration.kid != grant.holder_kid
                            or identity.registration.spki_sm3 != spki_sm3
                            or claims.actors[0] != identity.registration.did
                        ):
                            return IntrospectionResult(False)
                        previous = claims
                        if position == len(grants) - 1 and (
                            saved_token != token or r != leaf_claims.raw
                        ):
                            return IntrospectionResult(False)
                    return IntrospectionResult(True, raw)
        except (ClaimsError, InvalidSm2Signature, IdentityError, LedgerError, ValueError):
            return IntrospectionResult(False)
        except psycopg.Error as exc:
            raise IntrospectionError("trusted state unavailable") from exc
