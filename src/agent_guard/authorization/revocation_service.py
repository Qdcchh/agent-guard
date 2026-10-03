"""Transactional task-owner cancellation in the shared AS/ledger state domain.

This is a trusted in-process entry point, not an HTTP authorization handler.
The caller must derive ``authenticated_subject`` from an established user
session with CSRF validation; untrusted JSON must never supply that value.
Admin grant-level revocation remains a separate, unimplemented boundary.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import psycopg

from agent_guard.contracts.ledger import LedgerError
from agent_guard.ledger import store

_SAFE_ID = re.compile(r"[\x21-\x7e]{1,128}\Z", re.ASCII)


class TaskRevocationError(ValueError):
    """The cancellation decision was denied or trusted state was unavailable."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TaskRevocationResult:
    revocation_id: str
    effective_at: datetime
    scope: str = "SUBTREE"


class TaskRevocationService:
    """Cancel one task permanently under the common AS/ledger lock order."""

    def __init__(
        self,
        dsn: str,
        *,
        connector: Callable[..., psycopg.Connection] = psycopg.connect,
    ) -> None:
        self._dsn = dsn
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

    def revoke_task(
        self,
        *,
        tenant_id: str,
        task_id: str,
        authenticated_subject: str,
        reason_code: str = "USER_CANCELLED",
    ) -> TaskRevocationResult:
        """Revoke the root and all descendants; repeat calls return one event.

        Authentication and CSRF are performed by a separate trusted user
        session layer. The database root subject is checked again here to
        prevent a cross-user or cross-tenant cancellation.
        """
        if (
            any(
                type(value) is not str or not _SAFE_ID.fullmatch(value)
                for value in (tenant_id, task_id, authenticated_subject)
            )
            or reason_code != "USER_CANCELLED"
        ):
            raise TaskRevocationError("INVALID_REQUEST")
        try:
            with self._connect() as conn:
                with conn.transaction():
                    task_row = conn.execute(
                        "SELECT root_grant_id FROM ag_tasks WHERE tenant_id = %s AND task_id = %s",
                        (tenant_id, task_id),
                    ).fetchone()
                    if task_row is None:
                        raise TaskRevocationError("TASK_NOT_FOUND")
                    root_id = task_row[0]
                    root = store.load_path(conn, root_id)
                    if len(root) != 1:
                        raise TaskRevocationError("TRUSTED_STATE_INVALID")
                    grant = root[0]
                    store.lock_principals(
                        conn, [(tenant_id, grant.holder_client_id, grant.holder_kid)]
                    )
                    task = store.lock_task(conn, tenant_id, task_id)
                    locked = store.lock_grants_root_to_leaf(conn, [root_id])[0]
                    if (
                        task.root_grant_id != root_id
                        or locked.parent_grant_id is not None
                        or locked.depth != 0
                        or locked.tenant_id != tenant_id
                        or locked.task_id != task_id
                    ):
                        raise TaskRevocationError("TRUSTED_STATE_INVALID")
                    if locked.subject != authenticated_subject:
                        raise TaskRevocationError("NOT_TASK_OWNER")
                    existing = conn.execute(
                        "SELECT revocation_id, effective_at FROM ag_task_revocations "
                        "WHERE tenant_id = %s AND task_id = %s",
                        (tenant_id, task_id),
                    ).fetchone()
                    if existing is not None:
                        if not locked.revoked:
                            raise TaskRevocationError("TRUSTED_STATE_INVALID")
                        return TaskRevocationResult(existing[0], existing[1])
                    effective_at = conn.execute("SELECT clock_timestamp()").fetchone()[0]
                    revocation_id = "revoke-" + uuid.uuid4().hex
                    conn.execute(
                        "WITH RECURSIVE subtree AS ("
                        "  SELECT grant_id FROM ag_grants WHERE grant_id = %s"
                        "  UNION ALL"
                        "  SELECT g.grant_id FROM ag_grants g "
                        "  JOIN subtree s ON g.parent_grant_id = s.grant_id"
                        ") "
                        "UPDATE ag_grants SET revoked = TRUE, revoked_at = %s "
                        "WHERE grant_id IN (SELECT grant_id FROM subtree) AND NOT revoked",
                        (root_id, effective_at),
                    )
                    conn.execute(
                        "INSERT INTO ag_task_revocations "
                        "(tenant_id, task_id, root_grant_id, revocation_id, subject, "
                        "reason_code, effective_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (
                            tenant_id,
                            task_id,
                            root_id,
                            revocation_id,
                            authenticated_subject,
                            reason_code,
                            effective_at,
                        ),
                    )
                    return TaskRevocationResult(revocation_id, effective_at)
        except LedgerError as exc:
            raise TaskRevocationError("TRUSTED_STATE_INVALID") from exc
        except psycopg.Error as exc:
            raise TaskRevocationError("TRUSTED_STATE_UNAVAILABLE") from exc
