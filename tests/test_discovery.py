"""Public, project-specific AS discovery never exports signing secrets."""

from __future__ import annotations

import pytest

from agent_guard.authorization.discovery import DiscoveryEndpoint
from agent_guard.contracts.encoding import b64url_decode, load_strict_json
from agent_guard.crypto.sm import JWS_ALG, generate_sm2_private_key, serialize_sm2_public_key


def test_discovery_and_project_key_document():
    private = generate_sm2_private_key()
    endpoint = DiscoveryEndpoint(
        issuer="https://auth.agent-guard.test",
        signing_keys={"as-sign-1": private.public_key()},
    )
    metadata = endpoint.handle_get("/.well-known/openid-configuration")
    assert metadata.status == 200
    assert metadata.headers["Content-Type"] == "application/json"
    body = load_strict_json(metadata.body)
    assert body["issuer"] == "https://auth.agent-guard.test"
    assert body["token_endpoint"] == "https://auth.agent-guard.test/oauth/token"
    assert body["ag_signing_keys_uri"] == "https://auth.agent-guard.test/ag/keys"
    assert body["id_token_signing_alg_values_supported"] == [JWS_ALG]
    assert body["code_challenge_methods_supported"] == ["S256"]
    assert "jwks_uri" not in body
    keys = load_strict_json(endpoint.handle_get("/ag/keys").body)
    assert keys["profile"] == "GM-MVP-1"
    assert keys["keys"][0]["kid"] == "as-sign-1"
    assert b64url_decode(keys["keys"][0]["public_key_spki"]) == serialize_sm2_public_key(
        private.public_key()
    )
    assert "private_key" not in keys["keys"][0]
    assert endpoint.handle_get("/other").status == 404


@pytest.mark.parametrize(
    "issuer",
    [
        "http://auth.example",
        "https://auth.example/path",
        "https://user@auth.example",
        "https://auth.example?x=1",
    ],
)
def test_discovery_rejects_ambiguous_issuer(issuer):
    with pytest.raises(ValueError):
        DiscoveryEndpoint(
            issuer=issuer, signing_keys={"as-sign-1": generate_sm2_private_key().public_key()}
        )


def test_missing_or_invalid_trusted_signing_key_rejected():
    with pytest.raises(ValueError):
        DiscoveryEndpoint(issuer="https://auth.example", signing_keys={})
    with pytest.raises(ValueError):
        DiscoveryEndpoint(
            issuer="https://auth.example",
            signing_keys={"bad kid": generate_sm2_private_key().public_key()},
        )
