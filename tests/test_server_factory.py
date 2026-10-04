"""Composed AS/OP application tests without a database connection."""

from __future__ import annotations

import asyncio
import base64
import os

import pytest
from tongsuopy.crypto import serialization

from agent_guard.contracts.encoding import load_strict_json
from agent_guard.crypto.sm import generate_sm2_private_key
from agent_guard.server.config import (
    ConfigError,
    SecretsBundle,
    load_secrets,
    load_server_config,
    resolve_paths,
)
from agent_guard.server.factory import build_app
from agent_guard.server.middleware import RequestTimeoutMiddleware
from tests.test_server_config import ISSUER, _config_bytes, _pem_public, _planner, _secrets_bytes

DSN = "postgresql://synthetic-test-only@127.0.0.1:1/synthetic"


def _write_as_key(tmp_path) -> str:
    key = generate_sm2_private_key()
    path = tmp_path / "as-sign-key.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    if os.name != "nt":
        path.chmod(0o600)
    return str(path)


def _app(tmp_path):
    _, planner_pem, document = _planner()
    _write_as_key(tmp_path)
    config = load_server_config(_config_bytes(planner_pem, document))
    config = resolve_paths(config, tmp_path)
    secrets = load_secrets(_secrets_bytes())
    return build_app(config, secrets, dsn=DSN)


def _call(app, *, path, method="GET", headers=(), body=b"", scheme="https"):
    events = [{"type": "http.request", "body": body, "more_body": False}]
    sent = []

    async def receive():
        return events.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "scheme": scheme,
                "path": path,
                "method": method,
                "query_string": b"",
                "headers": list(headers),
            },
            receive,
            send,
        )
    )
    return sent


def test_discovery_ignores_host_and_forwarded_headers(tmp_path):
    app = _app(tmp_path)
    evil_headers = [
        (b"host", b"evil.example"),
        (b"x-forwarded-proto", b"http"),
        (b"x-forwarded-host", b"evil.example"),
        (b"forwarded", b"for=evil;proto=http"),
    ]
    sent = _call(app, path="/.well-known/openid-configuration", headers=evil_headers)
    assert sent[0]["status"] == 200
    payload = load_strict_json(sent[1]["body"])
    assert payload["issuer"] == ISSUER
    assert payload["token_endpoint"] == ISSUER + "/oauth/token"


def test_http_scheme_is_rejected_fail_closed(tmp_path):
    app = _app(tmp_path)
    sent = _call(app, path="/ag/keys", scheme="http")
    assert sent[0]["status"] == 403


def test_token_route_rejects_bad_basic_without_touching_services(tmp_path):
    app = _app(tmp_path)
    wrong = base64.b64encode(b"agent-planner:wrong-secret").decode("ascii")
    sent = _call(
        app,
        path="/oauth/token",
        method="POST",
        headers=[
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"authorization", f"Basic {wrong}".encode("ascii")),
            (b"ag-proof", b"synthetic-proof"),
        ],
        body=b"grant_type=authorization_code",
    )
    assert sent[0]["status"] == 401


def test_build_app_rejects_missing_secret_or_key(tmp_path):
    _, planner_pem, document = _planner()
    config = load_server_config(_config_bytes(planner_pem, document))
    secrets = SecretsBundle(note="t", client_secrets={"other": "x" * 48}, gateway_secret="y" * 48)
    with pytest.raises(ConfigError, match="cover"):
        build_app(config, secrets, dsn=DSN)
    _write_as_key(tmp_path)
    secrets = load_secrets(_secrets_bytes())
    with pytest.raises(ConfigError, match="signing key"):
        build_app(config, secrets, dsn=DSN)


def test_discovery_advertises_historical_verification_keys(tmp_path):
    _, planner_pem, document = _planner()
    old_key = generate_sm2_private_key()
    _write_as_key(tmp_path)
    config = load_server_config(
        _config_bytes(
            planner_pem,
            document,
            historical_verification_keys=[{"kid": "as-sign-0", "spki_pem": _pem_public(old_key)}],
        )
    )
    config = resolve_paths(config, tmp_path)
    app = build_app(config, load_secrets(_secrets_bytes()), dsn=DSN)
    sent = _call(app, path="/ag/keys")
    assert sent[0]["status"] == 200
    payload = load_strict_json(sent[1]["body"])
    assert {entry["kid"] for entry in payload["keys"]} == {"as-sign-1", "as-sign-0"}


def test_timeout_middleware_bounds_dispatch():
    async def slow(scope, receive, send):
        await asyncio.sleep(2)

    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "scheme": "https"}
    asyncio.run(RequestTimeoutMiddleware(slow, timeout_seconds=1)(scope, receive, send))
    assert sent[0]["status"] == 503

    async def fast(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    sent.clear()
    asyncio.run(RequestTimeoutMiddleware(fast, timeout_seconds=1)(scope, receive, send))
    assert sent[0]["status"] == 204
    with pytest.raises(ValueError):
        RequestTimeoutMiddleware(fast, timeout_seconds=0)


@pytest.mark.parametrize(
    "mutation,initial", [("append", False), ("clear", True), ("replace", False), ("alias", True)]
)
def test_runtime_did_snapshot_survives_caller_mutation(tmp_path, mutation, initial):
    from copy import deepcopy

    from agent_guard.identity.resolver import IdentityError
    from tests.test_server_config import KID

    _, pem, document = _planner()
    document["capabilityDelegation"] = [KID] if initial else []
    _write_as_key(tmp_path)
    config = resolve_paths(load_server_config(_config_bytes(pem, document)), tmp_path)
    secrets = load_secrets(_secrets_bytes())

    def no_database(*args, **kwargs):
        pytest.fail("building and resolving a configured snapshot must not connect")

    def allowed(app):
        resolver = app._app._token._codes._identities
        try:
            resolver.resolve_registered("agent-planner", "tenant-001", "capabilityDelegation")
        except IdentityError:
            return False
        return True

    app = build_app(config, secrets, dsn=DSN, connector=no_database)
    assert allowed(app) is initial
    url = next(iter(config.did_documents))
    if mutation == "append":
        config.did_documents[url]["capabilityDelegation"].append(KID)
    elif mutation == "clear":
        config.did_documents[url]["capabilityDelegation"].clear()
    elif mutation == "replace":
        replacement = deepcopy(config.did_documents[url])
        replacement["capabilityDelegation"] = [KID]
        config.did_documents[url] = replacement
    else:
        alias = config.did_documents
        alias.clear()
    assert allowed(app) is initial
    rebuilt = build_app(config, secrets, dsn=DSN, connector=no_database)
    assert allowed(rebuilt) is not initial
