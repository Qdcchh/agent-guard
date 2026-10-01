"""Real PostgreSQL task-owner cancellation and exchange/revoke ordering."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from agent_guard.authorization.exchange_service import TokenExchangeError
from agent_guard.authorization.revocation_service import TaskRevocationError, TaskRevocationService
from tests.fixtures.dbstate import fetch_one
from tests.integration.test_exchange_service import TASK, TENANT, _exchange, _form, _root

pytestmark = pytest.mark.integration


def test_owner_cancellation_revokes_descendants_and_is_idempotent(ledger, dsn):
    as_key, keys, registrations, exchanges, root = _root(dsn)
    form = _form(as_key, root.access_token)
    child = _exchange(exchanges, keys, registrations, form)
    service = TaskRevocationService(dsn)
    first = service.revoke_task(tenant_id=TENANT, task_id=TASK, authenticated_subject="user-001")
    again = service.revoke_task(tenant_id=TENANT, task_id=TASK, authenticated_subject="user-001")
    assert first == again
    assert first.scope == "SUBTREE"
    assert first.revocation_id.startswith("revoke-")
    assert fetch_one(dsn, "SELECT count(*) FROM ag_task_revocations") == (1,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants WHERE revoked") == (2,)
    assert fetch_one(
        dsn, "SELECT revoked_at FROM ag_grants WHERE grant_id = %s", (root.ag_grant_id,)
    ) == (first.effective_at,)
    assert fetch_one(
        dsn, "SELECT revoked_at FROM ag_grants WHERE grant_id = %s", (child.ag_grant_id,)
    ) == (first.effective_at,)
    with pytest.raises(TokenExchangeError, match="REVOKED"):
        _exchange(exchanges, keys, registrations, form)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (1,)


def test_non_owner_and_unknown_task_do_not_revoke(ledger, dsn):
    _, _, _, _, root = _root(dsn)
    service = TaskRevocationService(dsn)
    with pytest.raises(TaskRevocationError, match="NOT_TASK_OWNER"):
        service.revoke_task(tenant_id=TENANT, task_id=TASK, authenticated_subject="another-user")
    with pytest.raises(TaskRevocationError, match="TASK_NOT_FOUND"):
        service.revoke_task(
            tenant_id="another-tenant", task_id=TASK, authenticated_subject="user-001"
        )
    with pytest.raises(TaskRevocationError, match="INVALID_REQUEST"):
        service.revoke_task(
            tenant_id=TENANT,
            task_id=TASK,
            authenticated_subject="user-001",
            reason_code="ARBITRARY_REASON",
        )
    assert fetch_one(
        dsn, "SELECT revoked FROM ag_grants WHERE grant_id = %s", (root.ag_grant_id,)
    ) == (False,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_task_revocations") == (0,)


def test_cancel_and_exchange_cannot_leave_active_child(ledger, dsn):
    as_key, keys, registrations, exchanges, root = _root(dsn)
    service = TaskRevocationService(dsn)
    form = _form(as_key, root.access_token)
    with ThreadPoolExecutor(max_workers=2) as pool:
        revoke_future = pool.submit(
            service.revoke_task,
            tenant_id=TENANT,
            task_id=TASK,
            authenticated_subject="user-001",
        )
        exchange_future = pool.submit(_exchange, exchanges, keys, registrations, form)
        revoked = revoke_future.result()
        try:
            exchange_future.result()
        except TokenExchangeError as exc:
            assert exc.code == "REVOKED"
    assert revoked.scope == "SUBTREE"
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants WHERE NOT revoked") == (0,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_task_revocations") == (1,)


def test_revocation_record_is_immutable(ledger, dsn):
    _root(dsn)
    TaskRevocationService(dsn).revoke_task(
        tenant_id=TENANT, task_id=TASK, authenticated_subject="user-001"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "UPDATE ag_task_revocations SET reason_code = reason_code "
                "WHERE tenant_id = %s AND task_id = %s",
                (TENANT, TASK),
            )
