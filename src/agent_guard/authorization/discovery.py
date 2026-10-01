"""Project-specific OP discovery and public AS signing-key responses.

The key document is intentionally not a JWKS: GM-MVP-1 uses a project SM2
JWS algorithm identifier and SPKI encoding, not a standard SM2 JWK curve.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from tongsuopy.crypto.asymciphers.ec import EllipticCurvePublicKey

from agent_guard.authorization.claims import SCOPES
from agent_guard.authorization.token_endpoint import TokenResponse
from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from agent_guard.crypto.sm import JWS_ALG, serialize_sm2_public_key

_KID = re.compile(r"[\x21-\x7e]{1,128}\Z", re.ASCII)
_JSON_HEADERS = {"Content-Type": "application/json", "Cache-Control": "public, max-age=300"}


class DiscoveryEndpoint:
    """Build fixed public metadata from deployment-trusted issuer and keys."""

    def __init__(self, *, issuer: str, signing_keys: Mapping[str, EllipticCurvePublicKey]) -> None:
        if type(issuer) is not str:
            raise ValueError("fixed HTTPS issuer required")
        parsed = urlsplit(issuer)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("issuer must be an HTTPS origin")
        if not signing_keys:
            raise ValueError("at least one trusted AS signing key required")
        keys = []
        for kid, key in sorted(signing_keys.items()):
            if type(kid) is not str or not _KID.fullmatch(kid):
                raise ValueError("invalid AS signing key ID")
            keys.append(
                {
                    "kid": kid,
                    "alg": JWS_ALG,
                    "use": "sig",
                    "public_key_spki": b64url_encode(serialize_sm2_public_key(key)),
                }
            )
        origin = issuer.rstrip("/")
        self._metadata = canonical_json_bytes(
            {
                "issuer": origin,
                "authorization_endpoint": origin + "/oauth/authorize",
                "token_endpoint": origin + "/oauth/token",
                "response_types_supported": ["code"],
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": [JWS_ALG],
                "scopes_supported": sorted(SCOPES),
                "token_endpoint_auth_methods_supported": ["client_secret_basic"],
                "code_challenge_methods_supported": ["S256"],
                "ag_profile": "GM-MVP-1",
                "ag_signing_keys_uri": origin + "/ag/keys",
            }
        )
        self._keys = canonical_json_bytes({"profile": "GM-MVP-1", "keys": keys})

    def handle_get(self, path: str) -> TokenResponse:
        if path == "/.well-known/openid-configuration":
            return TokenResponse(200, dict(_JSON_HEADERS), self._metadata)
        if path == "/ag/keys":
            return TokenResponse(200, dict(_JSON_HEADERS), self._keys)
        return TokenResponse(404, {"Content-Type": "application/json"}, b"{}")
