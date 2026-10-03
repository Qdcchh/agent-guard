"""Tenant-admin subtree revocation and authorization races."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from agent_guard.authorization.exchange_service import TokenExchangeError
from agent_guard.authorization.grant_revocation_service import (
    GrantRevocationError,
    GrantRevocationService,
)
from agent_guard.ledger.provisioning import revoke_grant
from tests.fixtures.dbstate import fetch_one
from tests.integration.test_exchange_service import TENANT, _exchange, _form, _root

pytestmark = pytest.mark.integration
ADMIN = "admin-001"


def _register_admin(dsn, *, tenant=TENANT, active=True):
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO ag_tenant_admins (tenant_id, subject, active) VALUES (%s, %s, %s)",
            (tenant, ADMIN, active),
        )


def test_admin_revokes_child_subtree_only_and_retry_is_idempotent(ledger, dsn):
    as_key, keys, registrations, exchanges, root = _root(dsn)
    child = _exchange(exchanges, keys, registrations, _form(as_key, root.access_token))
    leaf = _exchange(
        exchanges,
        keys,
        registrations,
        _form(as_key, child.access_token, recipient="executor", ttl=100),
        holder="selector",
    )
    _register_admin(dsn)
    service = GrantRevocationService(dsn)
    first = service.revoke_grant(
        tenant_id=TENANT, grant_id=child.ag_grant_id, authenticated_admin_subject=ADMIN
    )
    again = service.revoke_grant(
        tenant_id=TENANT, grant_id=child.ag_grant_id, authenticated_admin_subject=ADMIN
    )
    assert first == again
    assert first.scope == "SUBTREE"
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grant_revocations") == (1,)
    assert fetch_one(
        dsn, "SELECT revoked FROM ag_grants WHERE grant_id = %s", (root.ag_grant_id,)
    ) == (False,)
    for target in (child.ag_grant_id, leaf.ag_grant_id):
        assert fetch_one(
            dsn, "SELECT revoked, revoked_at FROM ag_grants WHERE grant_id = %s", (target,)
        ) == (True, first.effective_at)
    with pytest.raises(TokenExchangeError, match="REVOKED"):
        _exchange(
            exchanges,
            keys,
            registrations,
            _form(as_key, child.access_token, recipient="executor", ttl=100),
            holder="selector",
        )


def test_admin_registry_and_tenant_are_authoritative(ledger, dsn):
    _, _, _, _, root = _root(dsn)
    service = GrantRevocationService(dsn)
    with pytest.raises(GrantRevocationError, match="NOT_ADMIN"):
        service.revoke_grant(
            tenant_id=TENANT, grant_id=root.ag_grant_id, authenticated_admin_subject=ADMIN
        )
    _register_admin(dsn, active=False)
    with pytest.raises(GrantRevocationError, match="NOT_ADMIN"):
        service.revoke_grant(
            tenant_id=TENANT, grant_id=root.ag_grant_id, authenticated_admin_subject=ADMIN
        )
    with pytest.raises(GrantRevocationError, match="GRANT_NOT_FOUND"):
        service.revoke_grant(
            tenant_id="other-tenant", grant_id=root.ag_grant_id, authenticated_admin_subject=ADMIN
        )
    assert fetch_one(
        dsn, "SELECT revoked FROM ag_grants WHERE grant_id = %s", (root.ag_grant_id,)
    ) == (False,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grant_revocations") == (0,)


def test_prior_revocation_is_not_repackaged_as_admin_event(ledger, dsn):
    _, _, _, _, root = _root(dsn)
    _register_admin(dsn)
    with psycopg.connect(dsn) as conn:
        revoke_grant(conn, root.ag_grant_id)
    with pytest.raises(GrantRevocationError, match="ALREADY_REVOKED"):
        GrantRevocationService(dsn).revoke_grant(
            tenant_id=TENANT, grant_id=root.ag_grant_id, authenticated_admin_subject=ADMIN
        )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grant_revocations") == (0,)


def test_admin_revoke_and_exchange_cannot_leave_active_descendant(ledger, dsn):
    as_key, keys, registrations, exchanges, root = _root(dsn)
    _register_admin(dsn)
    service = GrantRevocationService(dsn)
    form = _form(as_key, root.access_token)
    with ThreadPoolExecutor(max_workers=2) as pool:
        revoke_future = pool.submit(
            service.revoke_grant,
            tenant_id=TENANT,
            grant_id=root.ag_grant_id,
            authenticated_admin_subject=ADMIN,
        )
        exchange_future = pool.submit(_exchange, exchanges, keys, registrations, form)
        assert revoke_future.result().scope == "SUBTREE"
        try:
            exchange_future.result()
        except TokenExchangeError as exc:
            assert exc.code == "REVOKED"
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants WHERE NOT revoked") == (0,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grant_revocations") == (1,)


def test_admin_event_is_immutable(ledger, dsn):
    _, _, _, _, root = _root(dsn)
    _register_admin(dsn)
    GrantRevocationService(dsn).revoke_grant(
        tenant_id=TENANT, grant_id=root.ag_grant_id, authenticated_admin_subject=ADMIN
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "UPDATE ag_grant_revocations SET reason_code = reason_code WHERE grant_id = %s",
                (root.ag_grant_id,),
            )


@pytest.mark.parametrize("round_id", range(10))
def test_admin_revoke_exchange_real_principal_lock_race(ledger, dsn, round_id):
    from tests.integration.test_exchange_service import locked_race

    as_key, keys, registrations, exchanges, root = _root(dsn)
    _register_admin(dsn)
    service = GrantRevocationService(dsn)
    form = _form(as_key, root.access_token)
    results = locked_race(
        dsn,
        lambda: service.revoke_grant(
            tenant_id=TENANT, grant_id=root.ag_grant_id, authenticated_admin_subject=ADMIN
        ),
        lambda: _exchange(exchanges, keys, registrations, form),
    )
    assert results[0].scope == "SUBTREE"
    if isinstance(results[1], TokenExchangeError):
        assert results[1].code == "REVOKED"
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants WHERE NOT revoked") == (0,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grant_revocations") == (1,)
