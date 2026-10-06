"""Strict GM-MVP-1 access-token claims and delegation narrowing.

These are static checks only. Issuance and execution must recheck the
authoritative grant tree and key state under the shared database lock.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent_guard.contracts.encoding import MAX_SAFE_INTEGER, JsonObject

PROFILE = "GM-MVP-1"
GATEWAY_AUDIENCE = "https://gateway.agent-guard.test"
SCOPES = frozenset(
    {
        "openid",
        "procurement.request.read",
        "procurement.document.read",
        "procurement.order.create",
        "notification.template.send",
    }
)
CONSTRAINT_SETS = (
    "request_ids",
    "document_ids",
    "quote_versions",
    "skus",
    "delivery_ids",
    "template_ids",
    "recipient_ids",
)
_AT_FIELDS = {
    "iss",
    "sub",
    "aud",
    "iat",
    "nbf",
    "exp",
    "jti",
    "client_id",
    "scope",
    "act",
    "ag_profile",
    "ag_tenant_id",
    "ag_task_id",
    "ag_grant_id",
    "ag_parent_id",
    "ag_root_id",
    "ag_delegation_remaining",
    "ag_limits",
    "ag_constraints",
    "ag_cnf",
}
_ASCII_ID = re.compile(r"[\x21-\x7e]+\Z", re.ASCII)
_QUOTE_VERSION = re.compile(r"[^@]+@[1-9][0-9]*\Z", re.ASCII)


class ClaimsError(ValueError):
    """A signed claim set violates the fixed authorization profile."""

    def __init__(self, detail: str, *, code: str = "INVALID_SIGNATURE"):
        self.code = code
        super().__init__(detail)


def _object(value: object, fields: set[str], name: str) -> JsonObject:
    if type(value) is not dict or set(value) != fields:
        raise ClaimsError(f"{name} fields do not match the profile")
    return value


def _string(value: object, name: str) -> str:
    if type(value) is not str or not value or not _ASCII_ID.fullmatch(value):
        raise ClaimsError(f"{name} must be nonempty printable ASCII")
    return value


def _integer(value: object, name: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER:
        raise ClaimsError(f"{name} must be a nonnegative safe integer")
    return value


def parse_scope(value: object) -> frozenset[str]:
    if type(value) is not str:
        raise ClaimsError("scope must be a string")
    parts = value.split(" ")
    if not parts or any(not part for part in parts) or len(set(parts)) != len(parts):
        raise ClaimsError("scope must be unique space-separated names")
    if not set(parts) <= SCOPES:
        raise ClaimsError("unsupported scope")
    return frozenset(parts)


def parse_constraints(value: object) -> JsonObject:
    constraints = _object(value, set(CONSTRAINT_SETS) | {"max_quantity"}, "ag_constraints")
    for name in CONSTRAINT_SETS:
        items = constraints[name]
        if type(items) is not list or len(items) != len(set(map(str, items))):
            raise ClaimsError(f"{name} must be a unique array")
        for item in items:
            _string(item, name)
            if name == "quote_versions" and not _QUOTE_VERSION.fullmatch(item):
                raise ClaimsError("quote version must be quote_id@positive_version")
    _integer(constraints["max_quantity"], "max_quantity")
    return constraints


def parse_actor(value: object) -> tuple[str, ...]:
    actors: list[str] = []
    while True:
        if type(value) is not dict:
            raise ClaimsError("act must be a nested object")
        if set(value) not in ({"sub"}, {"sub", "act"}):
            raise ClaimsError("act fields do not match the profile")
        actors.append(_string(value["sub"], "act.sub"))
        if len(actors) > 3 or len(set(actors)) != len(actors):
            raise ClaimsError("invalid actor chain")
        if "act" not in value:
            return tuple(actors)
        value = value["act"]


@dataclass(frozen=True)
class AccessClaims:
    raw: JsonObject
    scopes: frozenset[str]
    actors: tuple[str, ...]
    constraints: JsonObject


def validate_access_claims(
    payload: object, *, issuer: str, audience: str = GATEWAY_AUDIENCE, now: int
) -> AccessClaims:
    claims = _object(payload, _AT_FIELDS, "access token")
    if claims["iss"] != issuer or claims["aud"] != audience:
        raise ClaimsError("issuer or audience mismatch")
    for name in (
        "sub",
        "jti",
        "client_id",
        "ag_tenant_id",
        "ag_task_id",
        "ag_grant_id",
        "ag_root_id",
    ):
        _string(claims[name], name)
    if claims["ag_profile"] != PROFILE:
        raise ClaimsError("unsupported profile")
    iat = _integer(claims["iat"], "iat")
    nbf = _integer(claims["nbf"], "nbf")
    exp = _integer(claims["exp"], "exp")
    if not iat <= now or not nbf <= now < exp or not iat <= nbf < exp:
        raise ClaimsError("access token outside validity window", code="EXPIRED")
    if exp - iat > 300:
        raise ClaimsError("access token lifetime exceeds 300 seconds")
    remaining = _integer(claims["ag_delegation_remaining"], "delegation remaining")
    if remaining > 2:
        raise ClaimsError("delegation depth exceeds profile")
    actors = parse_actor(claims["act"])
    if len(actors) + remaining != 3:
        raise ClaimsError("actor history and delegation depth disagree")
    parent = claims["ag_parent_id"]
    if len(actors) == 1:
        if parent is not None or claims["ag_grant_id"] != claims["ag_root_id"]:
            raise ClaimsError("invalid root grant references")
    elif parent is None or _string(parent, "ag_parent_id") == claims["ag_grant_id"]:
        raise ClaimsError("invalid parent grant reference")
    limits = _object(claims["ag_limits"], {"currency", "amount_fen", "calls"}, "ag_limits")
    if limits["currency"] != "CNY":
        raise ClaimsError("unsupported currency")
    _integer(limits["amount_fen"], "amount_fen")
    _integer(limits["calls"], "calls")
    cnf = _object(claims["ag_cnf"], {"kid", "spki_sm3"}, "ag_cnf")
    _string(cnf["kid"], "ag_cnf.kid")
    _string(cnf["spki_sm3"], "ag_cnf.spki_sm3")
    constraints = parse_constraints(claims["ag_constraints"])
    return AccessClaims(claims, parse_scope(claims["scope"]), actors, constraints)


def validate_child(parent: AccessClaims, child: AccessClaims) -> None:
    """Reject any static expansion; caller must also check live parent state."""
    p, c = parent.raw, child.raw
    for name in ("iss", "sub", "aud", "ag_profile", "ag_tenant_id", "ag_task_id", "ag_root_id"):
        if c[name] != p[name]:
            raise ClaimsError(f"child changed {name}")
    if c["ag_parent_id"] != p["ag_grant_id"] or c["ag_grant_id"] == p["ag_grant_id"]:
        raise ClaimsError("child parent reference mismatch")
    if child.actors != (child.actors[0], *parent.actors):
        raise ClaimsError("child actor history mismatch")
    if c["ag_delegation_remaining"] >= p["ag_delegation_remaining"]:
        raise ClaimsError("child delegation depth not reduced")
    if c["iat"] < p["iat"] or c["nbf"] < p["nbf"] or c["exp"] > p["exp"]:
        raise ClaimsError("child expanded validity window")
    if not child.scopes <= parent.scopes:
        raise ClaimsError("child expanded scope")
    for name in ("amount_fen", "calls"):
        if c["ag_limits"][name] > p["ag_limits"][name]:
            raise ClaimsError(f"child expanded {name}")
    for name in CONSTRAINT_SETS:
        if not set(child.constraints[name]) <= set(parent.constraints[name]):
            raise ClaimsError(f"child expanded {name}")
    if child.constraints["max_quantity"] > parent.constraints["max_quantity"]:
        raise ClaimsError("child expanded max_quantity")
