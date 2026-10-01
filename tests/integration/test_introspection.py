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
