"""Live AS introspection against signed snapshots and PostgreSQL state."""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import urlencode

import psycopg
import pytest

from agent_guard.authorization.introspection import IntrospectionService
from agent_guard.authorization.introspection_endpoint import IntrospectionEndpoint
from agent_guard.authorization.token_endpoint import TokenClient
from agent_guard.contracts.encoding import load_strict_json
from agent_guard.ledger.provisioning import deactivate_principal, revoke_grant
from tests.integration.test_exchange_service import (
    ISSUER,
    TENANT,
    _exchange,
    _form,
    _root,
)

pytestmark = pytest.mark.integration
GATEWAY_SECRET = b"synthetic-test-only-introspection-gateway-secret"


def _endpoint(dsn, as_key, exchanges):
    inspector = IntrospectionService(
        dsn,
        issuer=ISSUER,
        as_keys={"as-sign-1": as_key.public_key()},
        identities=exchanges._identities,
    )
    endpoint = IntrospectionEndpoint(
        gateway_client=TokenClient(
            "gateway-introspect", "service", None, hashlib.sha256(GATEWAY_SECRET).digest()
        ),
        inspector=inspector,
    )
    return endpoint, inspector


def _inspect(endpoint, token):
    auth = "Basic " + base64.b64encode(b"gateway-introspect:" + GATEWAY_SECRET).decode("ascii")
    response = endpoint.handle(
        content_type="application/x-www-form-urlencoded",
        raw_form=urlencode({"token": token, "token_type_hint": "access_token"}).encode("ascii"),
        authorization_headers=(auth,),
    )
    assert response.status == 200
    return load_strict_json(response.body)


def test_live_root_and_child_then_parent_revocation(ledger, dsn):
    as_key, keys, registrations, exchanges, root = _root(dsn)
    endpoint, _ = _endpoint(dsn, as_key, exchanges)
    parent = _inspect(endpoint, root.access_token)
    assert parent["active"] is True
    assert parent["ag_grant_id"] == root.ag_grant_id
    assert parent["client_id"] == "agent-planner"
    child = _exchange(exchanges, keys, registrations, _form(as_key, root.access_token))
    active_child = _inspect(endpoint, child.access_token)
    assert active_child["active"] is True
    assert active_child["ag_root_id"] == root.ag_grant_id
    assert active_child["client_id"] == "agent-selector"
    leaf = _exchange(
        exchanges,
        keys,
        registrations,
        _form(as_key, child.access_token, recipient="executor", ttl=100),
        holder="selector",
    )
    assert _inspect(endpoint, leaf.access_token)["client_id"] == "agent-executor"
    assert _inspect(endpoint, child.access_token + "x") == {"active": False}
    assert _inspect(endpoint, "unknown") == {"active": False}
    with psycopg.connect(dsn) as conn:
        revoke_grant(conn, root.ag_grant_id)
    assert _inspect(endpoint, root.access_token) == {"active": False}
    assert _inspect(endpoint, child.access_token) == {"active": False}
    assert _inspect(endpoint, leaf.access_token) == {"active": False}


def test_child_revocation_and_holder_key_deactivation(ledger, dsn):
    as_key, keys, registrations, exchanges, root = _root(dsn)
    endpoint, _ = _endpoint(dsn, as_key, exchanges)
    child = _exchange(exchanges, keys, registrations, _form(as_key, root.access_token))
    with psycopg.connect(dsn) as conn:
        revoke_grant(conn, child.ag_grant_id)
    assert _inspect(endpoint, root.access_token)["active"] is True
    assert _inspect(endpoint, child.access_token) == {"active": False}
    with psycopg.connect(dsn) as conn:
        deactivate_principal(
            conn,
            tenant_id=TENANT,
            client_id="agent-planner",
            kid=registrations[(TENANT, "agent-planner")].kid,
        )
    assert _inspect(endpoint, root.access_token) == {"active": False}


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("outcome", ["expired", "resolution-failed", "valid"])
def test_introspection_external_resolution_before_final_clock(
    ledger, dsn, monkeypatch, round_id, outcome
):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    from agent_guard.identity.resolver import IdentityError
    from agent_guard.ledger import store

    now = int(time.time())
    as_key, _, _, exchanges, root = _root(dsn, approved_overrides={"task_expires_at": now + 2})
    _, inspector = _endpoint(dsn, as_key, exchanges)
    entered, released = threading.Event(), threading.Event()
    original = exchanges._identities._fetch_document

    def delayed(url):
        entered.set()
        assert released.wait(5)
        if outcome == "resolution-failed":
            raise IdentityError("synthetic resolution failure")
        return original(url)

    monkeypatch.setattr(exchanges._identities, "_fetch_document", delayed)
    with ThreadPoolExecutor(1) as pool, psycopg.connect(dsn, autocommit=True) as conn:
        before = conn.execute("SELECT count(*) FROM ag_proofs").fetchone()
        future = pool.submit(inspector.inspect, root.access_token)
        assert entered.wait(5)
        # A separate transaction can lock the grant while external DID is
        # blocked. This proves there is no network wait inside grant locks.
        with conn.transaction():
            conn.execute("SET LOCAL lock_timeout='200ms'")
            conn.execute("SELECT * FROM ag_grants FOR UPDATE NOWAIT")
        if outcome == "expired":
            while store.db_now_epoch(conn) < now + 2:
                time.sleep(0.01)
        released.set()
        result = future.result(timeout=5)
        assert result.active == (outcome == "valid")
        assert conn.execute("SELECT count(*) FROM ag_proofs").fetchone() == before
