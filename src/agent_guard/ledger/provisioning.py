"""Trusted in-process initialization fixtures for the A1 ledger state.

These helpers create the synthetic state that tests and future trusted
bootstrapping need: holder key rows, the permanent task root, child grants,
revocation and key deactivation. They are *not* an external entry point —
there is no self-registration or fake DID endpoint. HTTP or untrusted callers
must never reach this module directly.

Consistency rules enforced here so tests cannot construct self-contradictory
state (``tasks/A1-ledger.md`` section 4):

- ``(tenant_id, task_id)`` maps to exactly one root grant, created under the
  task-row lock plus the primary-key unique constraint; re-initialization is
  rejected and never clears balances.
- children belong to the same tenant/task, sit within their parent's validity
  window, never exceed their parent's amount/call limits and stay within
  depth 2;
- issuance, revocation, deactivation and accept share one lock order:
  principal rows, then the task row, then grant nodes root-to-leaf.
"""

from __future__ import annotations

from datetime import datetime

import psycopg

from agent_guard.contracts.ledger import ErrorCode, LedgerError
from agent_guard.ledger import store
from agent_guard.ledger.validation import _require_int, _require_str


class TaskAlreadyInitialized(Exception):
    """Raised when a root already exists for ``(tenant_id, task_id)``.

    Distinct from accept-path :class:`LedgerError` codes on purpose: this is a
    trusted-fixture precondition failure, not a request rejection.
    """


class ProvisioningError(Exception):
    """Raised for invalid trusted fixture state (narrowing/depth violations)."""


def register_principal(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    client_id: str,
    kid: str,
    active: bool = True,
) -> None:
    """Register one holder key; used only by trusted initialization."""
    _require_str("tenant_id", tenant_id, 128)
    _require_str("client_id", client_id, 128)
    _require_str("kid", kid, 256)
    if not isinstance(active, bool):
        raise ProvisioningError("active must be a bool")
    conn.execute(
        "INSERT INTO ag_principals (tenant_id, client_id, kid, active) VALUES (%s, %s, %s, %s)",
        (tenant_id, client_id, kid, active),
    )


def deactivate_principal(
    conn: psycopg.Connection, *, tenant_id: str, client_id: str, kid: str
) -> None:
    """Deactivate a holder key in its own transaction.

    Lock order: the principal row is the first lock class of the shared order,
    so a concurrent accept serializes here and then observes ``active=false``.
    """
    with conn.transaction():
        row = conn.execute(
            "UPDATE ag_principals SET active = FALSE, deactivated_at = clock_timestamp() "
            "WHERE tenant_id = %s AND client_id = %s AND kid = %s "
            "RETURNING tenant_id",
            (tenant_id, client_id, kid),
        ).fetchone()
        if row is None:
            raise ProvisioningError("principal not registered")


def create_task_root(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    task_id: str,
    grant_id: str,
    subject: str,
    holder_client_id: str,
    holder_kid: str,
    amount_limit: int,
    call_limit: int,
    not_before: datetime,
    expires_at: datetime,
) -> str:
    """Create the permanent root grant for one task; at most one root exists.

    The task row is created (and therefore locked) first — the primary key is
    the uniqueness boundary, never a lock on a not-yet-existing root row.
    """
    _require_str("tenant_id", tenant_id, 128)
    _require_str("task_id", task_id, 128)
    _require_str("grant_id", grant_id, 128)
    _require_str("subject", subject, 128)
    _require_str("holder_client_id", holder_client_id, 128)
    _require_str("holder_kid", holder_kid, 256)
    _validate_window(not_before, expires_at)
    amount_limit = _check_positive_limits("amount_limit", amount_limit, allow_zero=True)
    call_limit = _check_positive_limits("call_limit", call_limit, allow_zero=True)

    with conn.transaction():
        conn.execute(
            "INSERT INTO ag_tasks (tenant_id, task_id, root_grant_id) VALUES (%s, %s, %s) "
            "ON CONFLICT (tenant_id, task_id) DO NOTHING",
            (tenant_id, task_id, grant_id),
        )
        row = conn.execute(
            "SELECT root_grant_id FROM ag_tasks WHERE tenant_id = %s AND task_id = %s FOR UPDATE",
            (tenant_id, task_id),
        ).fetchone()
        if row[0] != grant_id:
            raise TaskAlreadyInitialized(f"task {tenant_id}/{task_id} already has root {row[0]}")
        conn.execute(
            "INSERT INTO ag_grants "
            "(grant_id, parent_grant_id, root_grant_id, tenant_id, task_id, subject, "
            " holder_client_id, holder_kid, depth, not_before, expires_at, "
            " amount_limit, call_limit) "
            "VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s)",
            (
                grant_id,
                grant_id,
                tenant_id,
                task_id,
                subject,
                holder_client_id,
                holder_kid,
                not_before,
                expires_at,
                amount_limit,
                call_limit,
            ),
        )
    return grant_id


def create_child_grant(
    conn: psycopg.Connection,
    *,
    parent_grant_id: str,
    grant_id: str,
    holder_client_id: str,
    holder_kid: str,
    amount_limit: int,
    call_limit: int,
    not_before: datetime,
    expires_at: datetime,
) -> str:
    """Create a strictly narrower child under an existing grant."""
    _require_str("parent_grant_id", parent_grant_id, 128)
    _require_str("grant_id", grant_id, 128)
    _require_str("holder_client_id", holder_client_id, 128)
    _require_str("holder_kid", holder_kid, 256)
    _validate_window(not_before, expires_at)
    amount_limit = _check_positive_limits("amount_limit", amount_limit, allow_zero=True)
    call_limit = _check_positive_limits("call_limit", call_limit, allow_zero=True)

    with conn.transaction():
        parent_path = store.load_path(conn, parent_grant_id)
        keys = [(g.tenant_id, g.holder_client_id, g.holder_kid) for g in parent_path]
        store.lock_principals(conn, keys)
        parent_row = parent_path[-1]
        store.lock_task(conn, parent_row.tenant_id, parent_row.task_id)
        locked = store.lock_grants_root_to_leaf(conn, [g.grant_id for g in parent_path])
        parent = locked[-1]

        if parent.depth >= 2:
            raise ProvisioningError("depth limit reached (root + two child levels)")
        if not_before < parent.not_before or expires_at > parent.expires_at:
            raise ProvisioningError("child validity must lie within the parent window")
        if amount_limit > parent.amount_limit or call_limit > parent.call_limit:
            raise ProvisioningError("child limits must not exceed the parent limits")

        conn.execute(
            "INSERT INTO ag_grants "
            "(grant_id, parent_grant_id, root_grant_id, tenant_id, task_id, subject, "
            " holder_client_id, holder_kid, depth, not_before, expires_at, "
            " amount_limit, call_limit) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                grant_id,
                parent.grant_id,
                parent.root_grant_id,
                parent.tenant_id,
                parent.task_id,
                parent.subject,
                holder_client_id,
                holder_kid,
                parent.depth + 1,
                not_before,
                expires_at,
                amount_limit,
                call_limit,
            ),
        )
    return grant_id


def revoke_grant(conn: psycopg.Connection, grant_id: str) -> None:
    """Revoke a grant and its whole subtree (SUBTREE scope), same lock order as accept."""
    _require_str("grant_id", grant_id, 128)
    with conn.transaction():
        path = store.load_path(conn, grant_id)
        keys = [(g.tenant_id, g.holder_client_id, g.holder_kid) for g in path]
        store.lock_principals(conn, keys)
        store.lock_task(conn, path[-1].tenant_id, path[-1].task_id)
        store.lock_grants_root_to_leaf(conn, [g.grant_id for g in path])
        conn.execute(
            "WITH RECURSIVE subtree AS ("
            "  SELECT grant_id FROM ag_grants WHERE grant_id = %s"
            "  UNION ALL"
            "  SELECT g.grant_id FROM ag_grants g JOIN subtree s ON g.parent_grant_id = s.grant_id"
            ") "
            "UPDATE ag_grants SET revoked = TRUE, revoked_at = clock_timestamp() "
            "WHERE grant_id IN (SELECT grant_id FROM subtree)",
            (grant_id,),
        )


def _validate_window(not_before: datetime, expires_at: datetime) -> None:
    if not isinstance(not_before, datetime) or not isinstance(expires_at, datetime):
        raise ProvisioningError("validity bounds must be datetimes")
    if not_before.tzinfo is None or expires_at.tzinfo is None:
        raise ProvisioningError("validity bounds must be timezone-aware")
    if not_before >= expires_at:
        raise ProvisioningError("not_before must be earlier than expires_at")


def _check_positive_limits(name: str, value: object, *, allow_zero: bool) -> int:
    minimum = 0 if allow_zero else 1
    try:
        return _require_int(name, value, ErrorCode.INVALID_CONTEXT, minimum=minimum)
    except LedgerError as exc:
        raise ProvisioningError(str(exc)) from exc
