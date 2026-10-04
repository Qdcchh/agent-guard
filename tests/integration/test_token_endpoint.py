"""HTTP token boundary with real AS transactions and PostgreSQL."""

from __future__ import annotations

import base64
import hashlib
import time
from urllib.parse import urlencode

import pytest

from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.authorization.token_endpoint import TokenClient, TokenEndpoint
from agent_guard.contracts.encoding import load_strict_json
from tests.fixtures.dbstate import fetch_one
from tests.integration.test_code_service import (
    KID,
    REDIRECT,
    TOKEN_ENDPOINT,
    VERIFIER,
    _approved,
    _setup,
)
from tests.integration.test_exchange_service import (
    TENANT,
    _form,
    _root,
)
from tests.test_token_endpoint import FakeCodes, FakeExchanges

pytestmark = pytest.mark.integration
SECRET = b"synthetic-test-only-client-secret-of-adequate-length"


def _basic(client_id: str, secret: bytes = SECRET) -> str:
    return "Basic " + base64.b64encode(client_id.encode("ascii") + b":" + secret).decode("ascii")


def test_code_http_boundary_redeems_once_and_rejects_stolen_basic(ledger, dsn):
    codes, _, planner_key = _setup(dsn)
    code = codes.issue_code(_approved(int(time.time()))).code
    endpoint = TokenEndpoint(
        clients={
            "agent-planner": TokenClient(
                "agent-planner", TENANT, REDIRECT, hashlib.sha256(SECRET).digest()
            )
        },
        codes=codes,
        exchanges=FakeExchanges(),
    )
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "code_verifier": VERIFIER,
    }
    proof = sign_ag_proof(
        planner_key,
        kid=KID,
        client_id="agent-planner",
        purpose="code-exchange",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=None,
        now=int(time.time()),
    )
    params = {
        "content_type": "application/x-www-form-urlencoded",
        "raw_form": urlencode(form).encode("ascii"),
        "proof_headers": (proof,),
    }
    denied = endpoint.handle(authorization_headers=(_basic("agent-planner", b"wrong"),), **params)
    assert denied.status == 401
    assert fetch_one(dsn, "SELECT consumed_at FROM ag_authorization_codes") == (None,)
    issued = endpoint.handle(authorization_headers=(_basic("agent-planner"),), **params)
    assert issued.status == 200
    assert load_strict_json(issued.body)["token_type"] == "AGPoP"
    assert issued.headers["Cache-Control"] == "no-store"
    repeated = endpoint.handle(authorization_headers=(_basic("agent-planner"),), **params)
    assert repeated.status == 400
    assert load_strict_json(repeated.body)["error"] == "invalid_grant"
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (1,)


def test_exchange_http_boundary_uses_parent_basic_and_signed_proof(ledger, dsn):
    as_key, keys, registrations, exchanges, root = _root(dsn)
    endpoint = TokenEndpoint(
        clients={
            "agent-planner": TokenClient(
                "agent-planner", TENANT, REDIRECT, hashlib.sha256(SECRET).digest()
            ),
            "agent-selector": TokenClient(
                "agent-selector", TENANT, None, hashlib.sha256(SECRET).digest()
            ),
        },
        codes=FakeCodes(),
        exchanges=exchanges,
    )
    form = _form(as_key, root.access_token)
    planner = registrations[(TENANT, "agent-planner")]
    proof = sign_ag_proof(
        keys["planner"],
        kid=planner.kid,
        client_id="agent-planner",
        purpose="delegate",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=root.access_token,
        now=int(time.time()),
    )
    params = {
        "content_type": "application/x-www-form-urlencoded",
        "raw_form": urlencode(form).encode("ascii"),
        "proof_headers": (proof,),
    }
    stolen = endpoint.handle(authorization_headers=(_basic("agent-selector"),), **params)
    assert stolen.status == 400
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (0,)
    issued = endpoint.handle(authorization_headers=(_basic("agent-planner"),), **params)
    assert issued.status == 200
    assert load_strict_json(issued.body)["ag_parent_id"] == root.ag_grant_id
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (1,)
