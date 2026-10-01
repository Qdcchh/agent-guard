"""Transactional tenant-admin revocation of one authorization subtree.

The caller must pass a subject from an authenticated, CSRF-protected admin
session.  This service independently checks the tenant-admin registry under
lock; there is deliberately no request-body role or self-enrollment path.
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


class GrantRevocationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class GrantRevocationResult:
    revocation_id: str
    effective_at: datetime
    scope: str = "SUBTREE"


class GrantRevocationService:
    """Revoke a grant and descendants under the common database lock order."""

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

    def revoke_grant(
        self,
        *,
        tenant_id: str,
        grant_id: str,
        authenticated_admin_subject: str,
        reason_code: str = "USER_CANCELLED",
    ) -> GrantRevocationResult:
        if (
            any(
                type(value) is not str or not _SAFE_ID.fullmatch(value)
                for value in (tenant_id, grant_id, authenticated_admin_subject)
            )
            or reason_code != "USER_CANCELLED"
        ):
            raise GrantRevocationError("INVALID_REQUEST")
        try:
            with self._connect() as conn:
                with conn.transaction():
                    path = store.load_path(conn, grant_id)
                    if path[-1].tenant_id != tenant_id:
                        raise GrantRevocationError("GRANT_NOT_FOUND")
                    keys = [(g.tenant_id, g.holder_client_id, g.holder_kid) for g in path]
                    store.lock_principals(conn, keys)
                    admin = conn.execute(
                        "SELECT active FROM ag_tenant_admins "
                        "WHERE tenant_id = %s AND subject = %s FOR UPDATE",
                        (tenant_id, authenticated_admin_subject),
                    ).fetchone()
                    if admin is None or not admin[0]:
                        raise GrantRevocationError("NOT_ADMIN")
                    task = store.lock_task(conn, tenant_id, path[-1].task_id)
                    grants = store.lock_grants_root_to_leaf(conn, [g.grant_id for g in path])
                    if (
                        task.root_grant_id != grants[0].grant_id
                        or grants[0].parent_grant_id is not None
                        or grants[-1].grant_id != grant_id
                        or any(
                            grant.depth != position
                            or grant.tenant_id != tenant_id
                            or grant.task_id != task.task_id
                            or grant.root_grant_id != grants[0].grant_id
                            or (
                                position > 0
                                and grant.parent_grant_id != grants[position - 1].grant_id
                            )
                            for position, grant in enumerate(grants)
                        )
                    ):
                        raise GrantRevocationError("TRUSTED_STATE_INVALID")
                    existing = conn.execute(
                        "SELECT revocation_id, effective_at FROM ag_grant_revocations "
                        "WHERE grant_id = %s",
                        (grant_id,),
                    ).fetchone()
                    if existing is not None:
                        if not grants[-1].revoked:
                            raise GrantRevocationError("TRUSTED_STATE_INVALID")
                        return GrantRevocationResult(existing[0], existing[1])
                    if any(grant.revoked for grant in grants):
                        raise GrantRevocationError("ALREADY_REVOKED")
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
                        (grant_id, effective_at),
                    )
                    conn.execute(
                        "INSERT INTO ag_grant_revocations "
                        "(grant_id, tenant_id, task_id, revocation_id, admin_subject, "
                        "reason_code, effective_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (
                            grant_id,
                            tenant_id,
                            task.task_id,
                            revocation_id,
                            authenticated_admin_subject,
                            reason_code,
                            effective_at,
                        ),
                    )
                    return GrantRevocationResult(revocation_id, effective_at)
        except LedgerError as exc:
            raise GrantRevocationError("GRANT_NOT_FOUND") from exc
        except psycopg.Error as exc:
            raise GrantRevocationError("TRUSTED_STATE_UNAVAILABLE") from exc
