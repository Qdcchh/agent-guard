"""Real PostgreSQL session-authenticated revocation HTTP routes.

Covers task-owner cancellation, tenant-admin subtree cancellation, wrong user,
wrong tenant, non-admin, repeat/idempotent requests, missing session/CSRF and
a concurrent double cancellation through the HTTP boundary.
"""

from __future__ import annotations

import concurrent.futures

import psycopg
import pytest

from agent_guard.authorization.grant_revocation_service import GrantRevocationService
from agent_guard.authorization.login import LoginService
from agent_guard.authorization.provisioning import grant_tenant_admin, register_user
from agent_guard.authorization.revocation_http import RevocationHttpApp
from agent_guard.authorization.revocation_service import TaskRevocationService
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from tests.fixtures.dbstate import fetch_one
from tests.fixtures.state import build_tree

pytestmark = pytest.mark.integration

TENANT = "tenant-001"
SUBJECT = "user-001"
ADMIN = "admin-001"
PASSWORD = "synthetic-test-only-password"
BODY = canonical_json_bytes({"reason_code": "USER_CANCELLED"})


def _stack(dsn):
    login = LoginService(dsn)
    app = RevocationHttpApp(
        sessions=login,
        tasks=TaskRevocationService(dsn),
        grants=GrantRevocationService(dsn),
    )
    return login, app


def _login(login, tenant=TENANT, subject=SUBJECT, password=PASSWORD):
    csrf = login.issue_login_csrf()
    return login.login(
        login_csrf=csrf, csrf_cookie=csrf, tenant_id=tenant, subject=subject, password=password
    )


def _headers(session):
    return [
        (b"cookie", f"ag_session={session.session_token}~{session.csrf_token}".encode()),
        (b"x-csrf-token", session.csrf_token.encode()),
    ]


def test_task_owner_revocation_is_idempotent(ledger, dsn):
    with psycopg.connect(dsn) as conn:
        tree = build_tree(conn, tenant_id=TENANT, task_id="task-001", subject=SUBJECT)
        register_user(conn, tenant_id=TENANT, subject=SUBJECT, password=PASSWORD)
    login, app = _stack(dsn)
    session = _login(login)

    first = app.dispatch(
        method="POST",
        path=f"/ag/tasks/{tree.task_id}/revoke",
        headers=_headers(session),
        body=BODY,
    )
    assert first.status == 200
    revocation_id = load_strict_json(first.body)["revocation_id"]
    assert fetch_one(dsn, "SELECT revoked FROM ag_grants WHERE grant_id = %s", (tree.root_id,)) == (
        True,
    )

    again = app.dispatch(
        method="POST",
        path=f"/ag/tasks/{tree.task_id}/revoke",
        headers=_headers(session),
        body=BODY,
    )
    assert again.status == 200
    assert load_strict_json(again.body)["revocation_id"] == revocation_id


def test_task_revocation_by_other_subject_is_forbidden(ledger, dsn):
    with psycopg.connect(dsn) as conn:
        tree = build_tree(conn, tenant_id=TENANT, task_id="task-001", subject=SUBJECT)
        register_user(conn, tenant_id=TENANT, subject=SUBJECT, password=PASSWORD)
        register_user(conn, tenant_id=TENANT, subject="other", password=PASSWORD)
    login, app = _stack(dsn)
    other = _login(login, subject="other")
    response = app.dispatch(
        method="POST",
        path=f"/ag/tasks/{tree.task_id}/revoke",
        headers=_headers(other),
        body=BODY,
    )
    assert response.status == 403
    assert load_strict_json(response.body)["error"] == "NOT_TASK_OWNER"
    assert fetch_one(dsn, "SELECT revoked FROM ag_grants WHERE grant_id = %s", (tree.root_id,)) == (
        False,
    )


def test_tenant_admin_can_revoke_a_subtree_idempotently(ledger, dsn):
    with psycopg.connect(dsn) as conn:
        tree = build_tree(conn, tenant_id=TENANT, task_id="task-001", subject=SUBJECT)
        register_user(conn, tenant_id=TENANT, subject=ADMIN, password=PASSWORD)
        grant_tenant_admin(conn, tenant_id=TENANT, subject=ADMIN)
    login, app = _stack(dsn)
    admin = _login(login, subject=ADMIN)

    first = app.dispatch(
        method="POST",
        path=f"/ag/grants/{tree.mid_id}/revoke",
        headers=_headers(admin),
        body=BODY,
    )
    assert first.status == 200
    revocation_id = load_strict_json(first.body)["revocation_id"]
    assert fetch_one(dsn, "SELECT revoked FROM ag_grants WHERE grant_id = %s", (tree.mid_id,)) == (
        True,
    )
    # non-revoked sibling branch under the same root is untouched
    assert fetch_one(dsn, "SELECT revoked FROM ag_grants WHERE grant_id = %s", (tree.root_id,)) == (
        False,
    )

    again = app.dispatch(
        method="POST",
        path=f"/ag/grants/{tree.mid_id}/revoke",
        headers=_headers(admin),
        body=BODY,
    )
    assert again.status == 200
    assert load_strict_json(again.body)["revocation_id"] == revocation_id


def test_grant_revocation_by_non_admin_is_forbidden(ledger, dsn):
    with psycopg.connect(dsn) as conn:
        tree = build_tree(conn, tenant_id=TENANT, task_id="task-001", subject=SUBJECT)
        register_user(conn, tenant_id=TENANT, subject=SUBJECT, password=PASSWORD)
    login, app = _stack(dsn)
    session = _login(login)
    response = app.dispatch(
        method="POST",
        path=f"/ag/grants/{tree.mid_id}/revoke",
        headers=_headers(session),
        body=BODY,
    )
    assert response.status == 403
    assert load_strict_json(response.body)["error"] == "NOT_ADMIN"


def test_cross_tenant_revocation_is_not_found(ledger, dsn):
    with psycopg.connect(dsn) as conn:
        tree = build_tree(conn, tenant_id=TENANT, task_id="task-001", subject=SUBJECT)
        register_user(conn, tenant_id="tenant-002", subject=SUBJECT, password=PASSWORD)
    login, app = _stack(dsn)
    foreign = _login(login, tenant="tenant-002")
    response = app.dispatch(
        method="POST",
        path=f"/ag/tasks/{tree.task_id}/revoke",
        headers=_headers(foreign),
        body=BODY,
    )
    assert response.status == 404


def test_missing_session_and_bad_csrf_are_rejected(ledger, dsn):
    with psycopg.connect(dsn) as conn:
        tree = build_tree(conn, tenant_id=TENANT, task_id="task-001", subject=SUBJECT)
        register_user(conn, tenant_id=TENANT, subject=SUBJECT, password=PASSWORD)
    login, app = _stack(dsn)
    session = _login(login)
    path = f"/ag/tasks/{tree.task_id}/revoke"
    assert app.dispatch(method="POST", path=path, headers=[], body=BODY).status == 401
    assert (
        app.dispatch(
            method="POST",
            path=path,
            headers=[
                (b"cookie", f"ag_session={session.session_token}~{session.csrf_token}".encode())
            ],
            body=BODY,
        ).status
        == 401
    )
    assert (
        app.dispatch(
            method="POST",
            path=path,
            headers=[
                (b"cookie", f"ag_session={session.session_token}~{session.csrf_token}".encode()),
                (b"x-csrf-token", b"wrong-csrf-token-value-123"),
            ],
            body=BODY,
        ).status
        == 401
    )


def test_concurrent_grant_revocation_returns_one_event(ledger, dsn):
    with psycopg.connect(dsn) as conn:
        tree = build_tree(conn, tenant_id=TENANT, task_id="task-001", subject=SUBJECT)
        register_user(conn, tenant_id=TENANT, subject=ADMIN, password=PASSWORD)
        grant_tenant_admin(conn, tenant_id=TENANT, subject=ADMIN)
    login, app = _stack(dsn)
    admin = _login(login, subject=ADMIN)
    path = f"/ag/grants/{tree.mid_id}/revoke"

    def call():
        return app.dispatch(method="POST", path=path, headers=_headers(admin), body=BODY)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        responses = [future.result() for future in [pool.submit(call) for _ in range(2)]]
    assert [response.status for response in responses] == [200, 200]
    ids = {load_strict_json(response.body)["revocation_id"] for response in responses}
    assert len(ids) == 1
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grant_revocations") == (1,)
