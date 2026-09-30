"""Pure Token Exchange narrowing policy for an AS transaction.

This module never signs a token or inserts a grant. The caller must first
authenticate the requesting client and AG-Proof, verify the subject token,
resolve the recipient from the approved registry, then recheck all live grant
and key state under the shared root lock before persisting this specification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from agent_guard.authorization.claims import (
    CONSTRAINT_SETS,
    GATEWAY_AUDIENCE,
    AccessClaims,
    ClaimsError,
    parse_constraints,
    parse_scope,
    validate_access_claims,
)
from agent_guard.contracts.encoding import (
    MAX_SAFE_INTEGER,
    EncodingError,
    b64url_decode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.crypto.sm import serialize_sm2_public_key
from agent_guard.identity.resolver import ResolvedIdentity

_REQUEST_FIELDS = {
    "audience",
    "scope",
    "ag_delegate_client_id",
    "ag_amount_limit_fen",
    "ag_call_limit",
    "ag_ttl_seconds",
    "ag_delegation_remaining",
    "ag_constraints",
    "ag_delegation_key",
}
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)


class DelegationError(ValueError):
    """A Token Exchange request attempts expansion or violates the profile."""


def _number(value: object, name: str) -> int:
    if type(value) is not str or not _DECIMAL.fullmatch(value):
        raise DelegationError(f"{name} must be canonical nonnegative decimal")
    if len(value) > 16:
        raise DelegationError(f"{name} exceeds safe integer range")
    number = int(value)
    if number > MAX_SAFE_INTEGER:
        raise DelegationError(f"{name} exceeds safe integer range")
    return number


@dataclass(frozen=True)
class ChildSpec:
    """Validated immutable inputs to a later atomic issuance decision."""

    parent_grant_id: str
    root_grant_id: str
    tenant_id: str
    task_id: str
    subject: str
    recipient_client_id: str
    recipient_did: str
    recipient_kid: str
    recipient_spki_sm3: str
    audience: str
    scope: str
    amount_limit_fen: int
    call_limit: int
    not_before: int
    expires_at: int
    delegation_remaining: int
    constraints_json: bytes
    delegation_key: str


class GrantPolicy:
    """Validate one requested child against a verified parent snapshot."""

    def __init__(self, *, issuer: str) -> None:
        if type(issuer) is not str or not issuer.startswith("https://"):
            raise ValueError("GrantPolicy requires a configured HTTPS issuer")
        self._issuer = issuer

    def validate_child(
        self,
        parent_snapshot: AccessClaims,
        requested: Mapping[str, str],
        recipient: ResolvedIdentity,
        *,
        now: int,
    ) -> ChildSpec:
        if type(now) is not int or not 0 <= now <= MAX_SAFE_INTEGER:
            raise DelegationError("invalid issuance time")
        if not isinstance(parent_snapshot, AccessClaims):
            raise DelegationError("parent must be verified access claims")
        if set(requested) != _REQUEST_FIELDS or any(type(v) is not str for v in requested.values()):
            raise DelegationError("delegation fields do not match the profile")
        if not isinstance(recipient, ResolvedIdentity) or not recipient.registration.active:
            raise DelegationError("recipient is not an active registered identity")
        if serialize_sm2_public_key(recipient.public_key) != recipient.registration.spki_der:
            raise DelegationError("recipient key does not match approved SPKI")
        try:
            parent = validate_access_claims(
                parent_snapshot.raw,
                issuer=self._issuer,
                audience=GATEWAY_AUDIENCE,
                now=now,
            )
        except (ClaimsError, KeyError, TypeError) as exc:
            raise DelegationError("parent access claims are invalid or expired") from exc
        p = parent.raw
        registration = recipient.registration
        if p["ag_delegation_remaining"] == 0:
            raise DelegationError("parent has no remaining delegation depth")
        if (
            registration.tenant_id != p["ag_tenant_id"]
            or requested["ag_delegate_client_id"] != registration.client_id
            or registration.did in parent.actors
        ):
            raise DelegationError("recipient is not permitted on this tenant/actor path")
        if requested["audience"] != GATEWAY_AUDIENCE:
            raise DelegationError("audience expansion is forbidden")
        try:
            scopes = parse_scope(requested["scope"])
            constraints = parse_constraints(load_strict_json(requested["ag_constraints"]))
        except (ClaimsError, EncodingError) as exc:
            raise DelegationError("invalid child scope or constraints") from exc
        if "openid" in scopes or not scopes <= parent.scopes:
            raise DelegationError("scope expansion is forbidden")
        amount = _number(requested["ag_amount_limit_fen"], "amount limit")
        calls = _number(requested["ag_call_limit"], "call limit")
        ttl = _number(requested["ag_ttl_seconds"], "TTL")
        remaining = _number(requested["ag_delegation_remaining"], "remaining depth")
        if amount > p["ag_limits"]["amount_fen"] or calls > p["ag_limits"]["calls"]:
            raise DelegationError("budget or call expansion is forbidden")
        if not 1 <= ttl <= 300 or ttl > p["exp"] - now:
            raise DelegationError("child TTL exceeds parent validity")
        if remaining != p["ag_delegation_remaining"] - 1:
            raise DelegationError("child depth must decrease by exactly one")
        for name in CONSTRAINT_SETS:
            if not set(constraints[name]) <= set(parent.constraints[name]):
                raise DelegationError(f"resource expansion is forbidden: {name}")
        if constraints["max_quantity"] > parent.constraints["max_quantity"]:
            raise DelegationError("quantity expansion is forbidden")
        delegation_key = requested["ag_delegation_key"]
        try:
            if len(b64url_decode(delegation_key)) < 16:
                raise DelegationError("delegation key must encode at least 128 bits")
        except (EncodingError, TypeError) as exc:
            raise DelegationError("delegation key must be canonical base64url") from exc
        return ChildSpec(
            parent_grant_id=p["ag_grant_id"],
            root_grant_id=p["ag_root_id"],
            tenant_id=p["ag_tenant_id"],
            task_id=p["ag_task_id"],
            subject=p["sub"],
            recipient_client_id=registration.client_id,
            recipient_did=registration.did,
            recipient_kid=registration.kid,
            recipient_spki_sm3=registration.spki_sm3,
            audience=GATEWAY_AUDIENCE,
            scope=" ".join(sorted(scopes)),
            amount_limit_fen=amount,
            call_limit=calls,
            not_before=now,
            expires_at=now + ttl,
            delegation_remaining=remaining,
            constraints_json=canonical_json_bytes(constraints),
            delegation_key=delegation_key,
        )
