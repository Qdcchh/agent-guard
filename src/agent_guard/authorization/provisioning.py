"""Trusted in-process provisioning for users, task policies and tenant admins.

This is not an HTTP entry point: there is no self-registration and no request
body can enroll a user or an administrator. Passwords are stored only through
the scrypt KDF in :mod:`agent_guard.authorization.passwords`.
"""

from __future__ import annotations

import re
from datetime import datetime

import psycopg

from agent_guard.authorization.claims import (
    CONSTRAINT_SETS,
    ClaimsError,
    parse_constraints,
    parse_scope,
)
from agent_guard.authorization.passwords import hash_password
from agent_guard.contracts.encoding import canonical_json_bytes

_SAFE_ID = re.compile(r"[\x21-\x7e]{1,128}\Z", re.ASCII)


class ProvisioningError(ValueError):
    """Invalid trusted bootstrap input for the authorization state."""


def _id(value: object, name: str) -> str:
    if type(value) is not str or not _SAFE_ID.fullmatch(value):
        raise ProvisioningError(f"{name} must be printable ASCII within 128 characters")
    return value


def _limit(value: object, name: str) -> int:
    if type(value) is not int or isinstance(value, bool) or not 0 <= value <= (1 << 53) - 1:
        raise ProvisioningError(f"{name} must be a nonnegative safe integer")
    return value


def _expiry(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ProvisioningError(f"{name} must be a timezone-aware datetime")
    return value


def register_user(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    subject: str,
    password: str,
    active: bool = True,
) -> None:
    """Create one synthetic user with a scrypt password encoding."""
    _id(tenant_id, "tenant_id")
    _id(subject, "subject")
    if not isinstance(active, bool):
        raise ProvisioningError("active must be a bool")
    try:
        encoded = hash_password(password)
    except ValueError as exc:
        raise ProvisioningError("password rejected") from exc
    conn.execute(
        "INSERT INTO ag_users (tenant_id, subject, password_hash, active) VALUES (%s, %s, %s, %s)",
        (tenant_id, subject, encoded, active),
    )


def set_user_password(
    conn: psycopg.Connection, *, tenant_id: str, subject: str, password: str
) -> None:
    _id(tenant_id, "tenant_id")
    _id(subject, "subject")
    try:
        encoded = hash_password(password)
    except ValueError as exc:
        raise ProvisioningError("password rejected") from exc
    row = conn.execute(
        "UPDATE ag_users SET password_hash = %s WHERE tenant_id = %s AND subject = %s "
        "RETURNING subject",
        (encoded, tenant_id, subject),
    ).fetchone()
    if row is None:
        raise ProvisioningError("user not registered")


def register_task_policy(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    task_id: str,
    owner_subject: str,
    scope: str,
    constraints: object,
    amount_limit_fen: int,
    call_limit: int,
    task_expires_at: datetime,
    active: bool = True,
) -> None:
    """Create the server-side task boundary shown to the consent UI."""
    _id(tenant_id, "tenant_id")
    _id(task_id, "task_id")
    _id(owner_subject, "owner_subject")
    if not isinstance(active, bool):
        raise ProvisioningError("active must be a bool")
    try:
        scopes = parse_scope(scope)
        validated = parse_constraints(constraints)
    except (ClaimsError, TypeError) as exc:
        raise ProvisioningError("invalid task policy scope or constraints") from exc
    if "openid" not in scopes:
        raise ProvisioningError("task policy scope must include openid")
    if not isinstance(validated, dict) or set(validated) != set(CONSTRAINT_SETS) | {"max_quantity"}:
        raise ProvisioningError("unexpected constraints shape")
    amount = _limit(amount_limit_fen, "amount_limit_fen")
    calls = _limit(call_limit, "call_limit")
    expiry = _expiry(task_expires_at, "task_expires_at")
    conn.execute(
        "INSERT INTO ag_task_policies "
        "(tenant_id, task_id, owner_subject, scope, constraints_json, amount_limit_fen, "
        " call_limit, task_expires_at, active) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            tenant_id,
            task_id,
            owner_subject,
            " ".join(sorted(scopes)),
            canonical_json_bytes(validated),
            amount,
            calls,
            expiry,
            active,
        ),
    )


def grant_tenant_admin(
    conn: psycopg.Connection, *, tenant_id: str, subject: str, active: bool = True
) -> None:
    """Register one tenant administrator for the separate revocation boundary."""
    _id(tenant_id, "tenant_id")
    _id(subject, "subject")
    if not isinstance(active, bool):
        raise ProvisioningError("active must be a bool")
    conn.execute(
        "INSERT INTO ag_tenant_admins (tenant_id, subject, active) VALUES (%s, %s, %s)",
        (tenant_id, subject, active),
    )
