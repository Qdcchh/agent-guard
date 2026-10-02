"""Real TLS server assembly: boot the full AS over HTTPS and drive the flow.

Requires the OpenSSL CLI and uvicorn; both are present on the CI runner. The
test connects with a deliberately unverified TLS context only because the
certificate is a throwaway dev certificate -- this is a development boundary,
never a claim of production TLS posture.
"""

from __future__ import annotations

import base64
import http.client
import os
import re
import shutil
import ssl
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlsplit

import psycopg
import pytest
import uvicorn
from tongsuopy.crypto import serialization

from agent_guard.authorization.oidc import pkce_s256_challenge
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.authorization.provisioning import register_task_policy, register_user
from agent_guard.contracts.encoding import (
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
from agent_guard.identity.resolver import METHOD_TYPE, SPKI_PROPERTY
from agent_guard.ledger.provisioning import register_principal
from agent_guard.server.config import load_secrets, load_server_config, resolve_paths
from agent_guard.server.factory import build_app
from tests.fixtures.dbstate import fetch_one

pytestmark = pytest.mark.integration

ISSUER = "https://auth.agent-guard.test"
REDIRECT = "https://console.agent-guard.test/oauth/callback"
DID = "did:web:identity.agent-guard.test:agents:planner"
KID = DID + "#key-1"
TENANT = "tenant-001"
SUBJECT = "user-001"
PASSWORD = "synthetic-test-only-password"
VERIFIER = "A" * 43
CLIENT_SECRET = "synthetic-test-only-planner-secret-48"
GATEWAY_SECRET = "synthetic-test-only-gateway-secret-48"
CONSTRAINTS = {
    "request_ids": ["req-001"],
    "document_ids": [],
    "quote_versions": ["quote-001@1"],
    "skus": ["sku-001"],
    "max_quantity": 2,
    "delivery_ids": ["office-001"],
    "template_ids": [],
    "recipient_ids": [],
}


def _pem_private(key) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _pem_public(key) -> str:
    return (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )


def _authorize_params():
    return {
        "response_type": "code",
        "client_id": "agent-planner",
        "redirect_uri": REDIRECT,
        "scope": "openid procurement.order.create",
        "state": "state-value-123456",
        "nonce": b64url_encode(b"nonce-value-1234567890"),
        "code_challenge": pkce_s256_challenge(VERIFIER),
        "code_challenge_method": "S256",
        "ag_task_id": "task-001",
    }


def test_tls_server_runs_the_full_as_flow(ledger, dsn, tmp_path):
    if shutil.which("openssl") is None:
        pytest.fail("openssl CLI is required for the TLS server test", pytrace=False)

    cert_path = tmp_path / "tls-cert.pem"
    key_path = tmp_path / "tls-key.pem"
    generated = subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-days",
            "1",
            "-nodes",
            "-subj",
            "/CN=localhost",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert generated.returncode == 0, generated.stderr

    as_key = generate_sm2_private_key()
    planner_key = generate_sm2_private_key()
    as_key_path = tmp_path / "as-sign-key.pem"
    as_key_path.write_bytes(_pem_private(as_key))
    if os.name != "nt":
        as_key_path.chmod(0o600)
    spki = serialize_sm2_public_key(planner_key.public_key())
    document = {
        "id": DID,
        "verificationMethod": [
            {"id": KID, "type": METHOD_TYPE, "controller": DID, SPKI_PROPERTY: b64url_encode(spki)}
        ],
        "authentication": [KID],
        "capabilityInvocation": [KID],
        "capabilityDelegation": [KID],
    }
    config_raw = canonical_json_bytes(
        {
            "issuer": ISSUER,
            "as_signing_key_path": "as-sign-key.pem",
            "secrets_path": "secrets.json",
            "signing_kid": "as-sign-1",
            "clients": {"agent-planner": {"tenant_id": TENANT, "redirect_uri": REDIRECT}},
            "gateway_client_id": "gateway-introspect",
            "identities": {
                "agent-planner": {
                    "tenant_id": TENANT,
                    "did": DID,
                    "kid": KID,
                    "spki_pem": _pem_public(planner_key),
                }
            },
            "identity_allowed_hosts": ["identity.agent-guard.test"],
            "did_documents": {
                "https://identity.agent-guard.test/agents/planner/did.json": document
            },
            "session_ttl_seconds": 1800,
            "csrf_ttl_seconds": 600,
            "request_ttl_seconds": 300,
            "request_timeout_seconds": 10,
        }
    )
    secrets = load_secrets(
        canonical_json_bytes(
            {
                "note": "test-only",
                "client_secrets": {"agent-planner": CLIENT_SECRET},
                "gateway_secret": GATEWAY_SECRET,
            }
        )
    )
    with psycopg.connect(dsn) as conn:
        register_principal(conn, tenant_id=TENANT, client_id="agent-planner", kid=KID)
        register_user(conn, tenant_id=TENANT, subject=SUBJECT, password=PASSWORD)
        register_task_policy(
            conn,
            tenant_id=TENANT,
            task_id="task-001",
            owner_subject=SUBJECT,
            scope="openid procurement.order.create",
            constraints=CONSTRAINTS,
            amount_limit_fen=100000,
            call_limit=10,
            task_expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=600),
        )
    config = resolve_paths(load_server_config(config_raw), tmp_path)
    app = build_app(config, secrets, dsn=dsn)

    uv_config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),
        log_level="error",
        access_log=False,
        lifespan="off",
    )
    server = uvicorn.Server(uv_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 30
        while not server.started and time.time() < deadline:
            time.sleep(0.05)
        if not server.started:
            pytest.fail("uvicorn TLS server did not start", pytrace=False)
        if not server.servers or not server.servers[0].sockets:
            pytest.fail("uvicorn bound no listening sockets", pytrace=False)
        port = server.servers[0].sockets[0].getsockname()[1]
        _drive_flow(port, planner_key)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_tasks") == (1,)


def _request(port, method, path, body=None, headers=None):
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    connection = http.client.HTTPSConnection("127.0.0.1", port, context=context, timeout=20)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            response.read(),
        )
    finally:
        connection.close()


def _drive_flow(port: int, planner_key) -> None:
    def check(status, body, expected, step, headers=None):
        assert status == expected, (
            f"{step}: expected {expected}, got {status}, body={body[:400]!r}, headers={headers}"
        )

    status, headers, body = _request(
        port, "GET", "/.well-known/openid-configuration", headers={"Host": "evil.example"}
    )
    check(status, body, 200, "discovery")
    assert load_strict_json(body)["issuer"] == ISSUER

    status, headers, _ = _request(port, "GET", "/ag/login")
    check(status, b"", 200, "login page")
    login_csrf = headers["set-cookie"].split("ag_login_csrf=", 1)[1].split(";", 1)[0]

    status, headers, _ = _request(
        port,
        "POST",
        "/ag/login",
        body=urlencode(
            {
                "tenant_id": TENANT,
                "subject": SUBJECT,
                "password": PASSWORD,
                "csrf_token": login_csrf,
                "return_to": "/dashboard",
            }
        ),
        headers={
            "Cookie": f"ag_login_csrf={login_csrf}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    check(status, b"", 303, "login submit")
    session_cookie = headers["set-cookie"].split("ag_session=", 1)[1].split(";", 1)[0]

    status, _, body = _request(
        port,
        "GET",
        "/oauth/authorize?" + urlencode(_authorize_params()),
        headers={"Cookie": f"ag_session={session_cookie}"},
    )
    check(status, body, 200, "authorize")
    match_id = re.search(rb'name="request_id" value="([^"]+)"', body)
    match_csrf = re.search(rb'name="csrf_token" value="([^"]+)"', body)
    assert match_id is not None and match_csrf is not None, body[:400]
    request_id = match_id.group(1).decode()
    csrf = match_csrf.group(1).decode()
    assert csrf == session_cookie.split("~", 1)[1]

    status, headers, _ = _request(
        port,
        "POST",
        "/ag/consent",
        body=urlencode({"request_id": request_id, "decision": "approve", "csrf_token": csrf}),
        headers={
            "Cookie": f"ag_session={session_cookie}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    check(status, b"", 303, "consent approve", headers=headers)
    code = parse_qs(urlsplit(headers["location"]).query)["code"][0]

    token_form = {
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
        endpoint=ISSUER + "/oauth/token",
        body=token_form,
        token=None,
        now=int(time.time()),
    )
    basic = "Basic " + base64.b64encode(f"agent-planner:{CLIENT_SECRET}".encode("ascii")).decode(
        "ascii"
    )
    status, _, body = _request(
        port,
        "POST",
        "/oauth/token",
        body=urlencode(token_form),
        headers={
            "Authorization": basic,
            "AG-Proof": proof,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    check(status, body, 200, "token redeem")
    tokens = load_strict_json(body)
    assert tokens["token_type"] == "AGPoP"

    gateway_basic = "Basic " + base64.b64encode(
        f"gateway-introspect:{GATEWAY_SECRET}".encode("ascii")
    ).decode("ascii")
    status, _, body = _request(
        port,
        "POST",
        "/oauth/introspect",
        body=urlencode({"token": tokens["access_token"], "token_type_hint": "access_token"}),
        headers={
            "Authorization": gateway_basic,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    check(status, body, 200, "introspect")
    assert load_strict_json(body)["active"] is True

    status, _, body = _request(
        port,
        "POST",
        "/ag/tasks/task-001/revoke",
        body=canonical_json_bytes({"reason_code": "USER_CANCELLED"}),
        headers={
            "Cookie": f"ag_session={session_cookie}",
            "X-CSRF-Token": session_cookie.split("~", 1)[1],
            "Content-Type": "application/json",
        },
    )
    check(status, body, 200, "revoke")
    assert load_strict_json(body)["scope"] == "SUBTREE"
