"""Server configuration and secret validation tests (no database)."""

from __future__ import annotations

import pytest
from tongsuopy.crypto import serialization

from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
from agent_guard.identity.resolver import METHOD_TYPE, SPKI_PROPERTY
from agent_guard.server.config import (
    ConfigError,
    SecretsBundle,
    load_secrets,
    load_server_config,
    secret_sha256,
)

ISSUER = "https://auth.agent-guard.test"
DID = "did:web:identity.agent-guard.test:agents:planner"
KID = DID + "#key-1"


def _pem_public(key) -> str:
    return (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )


def _pem_private(key) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _planner() -> tuple[object, str, dict]:
    key = generate_sm2_private_key()
    spki = serialize_sm2_public_key(key.public_key())
    document = {
        "id": DID,
        "verificationMethod": [
            {"id": KID, "type": METHOD_TYPE, "controller": DID, SPKI_PROPERTY: b64url_encode(spki)}
        ],
        "authentication": [KID],
        "capabilityInvocation": [KID],
        "capabilityDelegation": [KID],
    }
    return key, _pem_public(key), document


def _config_bytes(planner_pem: str, document: dict, **overrides) -> bytes:
    base = {
        "issuer": ISSUER,
        "as_signing_key_path": "as-sign-key.pem",
        "secrets_path": "secrets.json",
        "signing_kid": "as-sign-1",
        "clients": {
            "agent-planner": {
                "tenant_id": "tenant-001",
                "redirect_uri": "https://console.agent-guard.test/oauth/callback",
            }
        },
        "gateway_client_id": "gateway-introspect",
        "identities": {
            "agent-planner": {
                "tenant_id": "tenant-001",
                "did": DID,
                "kid": KID,
                "spki_pem": planner_pem,
            }
        },
        "identity_allowed_hosts": ["identity.agent-guard.test"],
        "did_documents": {"https://identity.agent-guard.test/agents/planner/did.json": document},
        "session_ttl_seconds": 1800,
        "csrf_ttl_seconds": 600,
        "request_ttl_seconds": 300,
        "request_timeout_seconds": 10,
    }
    base.update(overrides)
    return canonical_json_bytes(base)


def _secrets_bytes(**overrides) -> bytes:
    base = {
        "note": "test-only",
        "client_secrets": {"agent-planner": "a" * 48},
        "gateway_secret": "b" * 48,
    }
    base.update(overrides)
    return canonical_json_bytes(base)


def test_valid_config_and_secrets_load():
    _, planner_pem, document = _planner()
    config = load_server_config(_config_bytes(planner_pem, document))
    assert config.issuer == ISSUER
    assert config.clients["agent-planner"].redirect_uri.endswith("/oauth/callback")
    assert config.identities["agent-planner"].kid == KID
    secrets = load_secrets(_secrets_bytes())
    assert isinstance(secrets, SecretsBundle)
    assert secret_sha256("a" * 48) != secret_sha256("b" * 48)


def test_config_rejects_unknown_fields_and_duplicates():
    _, planner_pem, document = _planner()
    with pytest.raises(ConfigError, match="fields"):
        load_server_config(_config_bytes(planner_pem, document, unknown_field="x"))
    duplicate = b'{"issuer":"https://auth.agent-guard.test","issuer":"https://x"}'
    with pytest.raises(ConfigError):
        load_server_config(duplicate)


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"issuer": "http://auth.agent-guard.test"}, "HTTPS"),
        ({"issuer": "https://auth.agent-guard.test/oauth"}, "origin"),
        ({"signing_kid": "bad kid"}, "signing_kid"),
        ({"session_ttl_seconds": 10}, "session_ttl_seconds"),
        ({"request_timeout_seconds": 0}, "request_timeout_seconds"),
        ({"request_timeout_seconds": True}, "request_timeout_seconds"),
        (
            {
                "clients": {
                    "agent-planner": {"tenant_id": "tenant-001", "redirect_uri": "http://x/y"}
                }
            },
            "HTTPS",
        ),
        ({"identity_allowed_hosts": []}, "identity_allowed_hosts"),
        ({"identity_allowed_hosts": ["HTTPS://x"]}, "hostname"),
        ({"did_documents": {}}, "did_documents"),
    ],
)
def test_config_rejects_invalid_fields(override, match):
    _, planner_pem, document = _planner()
    with pytest.raises(ConfigError, match=match):
        load_server_config(_config_bytes(planner_pem, document, **override))


def test_config_rejects_bad_identity_material():
    _, planner_pem, document = _planner()
    other = generate_sm2_private_key()
    with pytest.raises(ConfigError, match="kid"):
        load_server_config(
            _config_bytes(
                planner_pem,
                document,
                identities={
                    "agent-planner": {
                        "tenant_id": "tenant-001",
                        "did": DID,
                        "kid": "did:web:other.example#key-1",
                        "spki_pem": planner_pem,
                    }
                },
            )
        )
    with pytest.raises(ConfigError, match="PEM public key"):
        load_server_config(
            _config_bytes(
                planner_pem,
                document,
                identities={
                    "agent-planner": {
                        "tenant_id": "tenant-001",
                        "did": DID,
                        "kid": KID,
                        "spki_pem": "-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n",
                    }
                },
            )
        )
    with pytest.raises(ConfigError, match="host"):
        load_server_config(
            _config_bytes(
                planner_pem,
                document,
                identities={
                    "agent-planner": {
                        "tenant_id": "tenant-001",
                        "did": "did:web:evil.example:agents:planner",
                        "kid": "did:web:evil.example:agents:planner#key-1",
                        "spki_pem": planner_pem,
                    }
                },
            )
        )
    with pytest.raises(ConfigError, match="no approved did document"):
        load_server_config(
            _config_bytes(
                planner_pem,
                document,
                did_documents={"https://identity.agent-guard.test/agents/selector/did.json": {}},
            )
        )
    assert other is not None


def test_secrets_reject_weak_or_malformed_values():
    with pytest.raises(ConfigError, match="secret"):
        load_secrets(_secrets_bytes(gateway_secret="short"))
    with pytest.raises(ConfigError, match="fields"):
        load_secrets(_secrets_bytes(extra="x"))
    with pytest.raises(ConfigError, match="client_secrets"):
        load_secrets(_secrets_bytes(client_secrets={}))
    with pytest.raises(ConfigError):
        secret_sha256("")
    with pytest.raises(ConfigError):
        secret_sha256(123)
