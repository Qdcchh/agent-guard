"""Public trust only, immutable config, private files and explicit startup."""

import json
import os
import subprocess
import sys

import pytest

from agent_guard.gateway.__main__ import init_config
from agent_guard.gateway.config import load_gateway_config, load_gateway_secrets
from agent_guard.gateway.factory import build_app
from agent_guard.server.config import ConfigError


def synthetic(tmp_path):
    directory = tmp_path / "gateway"
    init_config(directory)
    return directory, json.loads((directory / "config.json").read_bytes())


def test_init_offline_check_and_no_private_signing_keys(tmp_path, monkeypatch):
    directory, value = synthetic(tmp_path)
    assert set(p.name for p in directory.iterdir()) == {"config.json", "secrets.json"}
    assert b"PRIVATE KEY" not in (directory / "config.json").read_bytes()
    assert directory.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in directory.iterdir())

    def refuse(*args, **kwargs):
        pytest.fail("configuration/startup must not connect/reset/provision a database")

    monkeypatch.setattr("psycopg.connect", refuse)
    config = load_gateway_config((directory / "config.json").read_bytes())
    secrets = load_gateway_secrets((directory / "secrets.json").read_bytes())
    app = build_app(
        config, secrets, gateway_dsn="offline-gateway", downstream_dsn="offline-downstream"
    )
    value["did_documents"].clear()
    # config is isolated canonical immutable bytes, not an alias of parsed input
    assert json.loads(config.raw)["did_documents"]
    app._executor.shutdown()
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_guard.gateway",
            "check",
            "--config",
            str(directory / "config.json"),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert process.returncode == 0 and "offline" in process.stdout


@pytest.mark.parametrize(
    "field,bad",
    [
        ("request_timeout_seconds", 0),
        ("request_timeout_seconds", True),
        ("max_workers", 0),
        ("max_workers", 33),
        ("identities", []),
        ("as_keys", {}),
        ("identity_allowed_hosts", []),
        ("did_documents", {}),
        ("catalog", {}),
    ],
)
def test_config_fail_closed(tmp_path, field, bad):
    _, value = synthetic(tmp_path)
    value[field] = bad
    with pytest.raises(ConfigError):
        load_gateway_config(json.dumps(value).encode())


@pytest.mark.parametrize(
    "variant", ["extra", "duplicate", "private-key", "identity-extra", "weak-secret"]
)
def test_security_fields_strict(tmp_path, variant):
    directory, value = synthetic(tmp_path)
    if variant == "weak-secret":
        with pytest.raises(ConfigError):
            load_gateway_secrets(b'{"note":"test","downstream_secret":"weak"}')
        return
    if variant == "extra":
        value["skip_verification"] = True
    if variant == "identity-extra":
        value["identities"][0]["as_private_key_path"] = "private.pem"
    raw = json.dumps(value).encode()
    if variant == "duplicate":
        raw = raw[:-1] + b',"issuer":"https://evil.test"}'
    if variant == "private-key":
        raw = raw.replace(b"PUBLIC KEY", b"PRIVATE KEY")
    with pytest.raises(ConfigError):
        load_gateway_config(raw)


def test_cli_no_database_fallback_and_requires_tls(tmp_path):
    directory, _ = synthetic(tmp_path)
    command = [
        sys.executable,
        "-m",
        "agent_guard.gateway",
        "run",
        "--config",
        str(directory / "config.json"),
    ]
    env = {k: v for k, v in os.environ.items() if not k.startswith("AG_GATEWAY_")}
    env["AGENT_GUARD_DATABASE_URL"] = "sensitive-deployment-marker"
    for flags in [[], ["--ssl-certfile", "missing-cert", "--ssl-keyfile", "missing-key"]]:
        result = subprocess.run(
            command + flags, env=env, capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 2
        assert "sensitive-deployment-marker" not in result.stdout + result.stderr
    with pytest.raises(ConfigError):
        build_app(
            load_gateway_config((directory / "config.json").read_bytes()),
            load_gateway_secrets((directory / "secrets.json").read_bytes()),
            gateway_dsn="same",
            downstream_dsn="same",
        )


@pytest.mark.parametrize(
    "collection,rows",
    [
        (
            "requests",
            [
                {"request_id": "r", "tenant_id": "tenant-a", "task_id": "t", "status": "APPROVED"},
                {"request_id": "r", "tenant_id": "tenant-b", "task_id": "t", "status": "APPROVED"},
            ],
        ),
        (
            "documents",
            [
                {"document_id": "d", "request_id": "r1", "body": "one"},
                {"document_id": "d", "request_id": "r2", "body": "two"},
            ],
        ),
        (
            "deliveries",
            [
                {"delivery_id": "d", "tenant_id": "a", "request_id": "r"},
                {"delivery_id": "d", "tenant_id": "b", "request_id": "r"},
            ],
        ),
        (
            "quotes",
            [
                {
                    "quote_id": "q",
                    "quote_version": "1",
                    "supplier_id": "s1",
                    "request_id": "r",
                    "lines": [{"sku": "s", "quantity": 1, "unit_price_fen": 1}],
                },
                {
                    "quote_id": "q",
                    "quote_version": "1",
                    "supplier_id": "s2",
                    "request_id": "r",
                    "lines": [{"sku": "s", "quantity": 1, "unit_price_fen": 2}],
                },
            ],
        ),
    ],
)
def test_catalog_lookup_identity_cannot_be_silently_overwritten(tmp_path, collection, rows):
    _, value = synthetic(tmp_path)
    value["catalog"][collection] = rows
    with pytest.raises(ConfigError):
        load_gateway_config(json.dumps(value).encode())
