"""RP-side ID Token verification and standard S256 PKCE helper.

This is not a login/session server. The RP must independently bind ``state``
to its browser session and keep its client secret and tokens server-side.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping

from tongsuopy.crypto.asymciphers.ec import EllipticCurvePublicKey

from agent_guard.contracts.encoding import MAX_SAFE_INTEGER, JsonObject, b64url_encode
from agent_guard.crypto.sm import InvalidSm2Signature, verify_compact_jws

_ID_FIELDS = {"iss", "sub", "aud", "iat", "exp", "auth_time", "nonce"}
_PKCE_RE = re.compile(r"[A-Za-z0-9._~-]{43,128}\Z", re.ASCII)


class OidcValidationError(ValueError):
    """An ID Token or PKCE verifier is invalid for this login session."""


def pkce_s256_challenge(verifier: str) -> str:
    """RFC 7636 S256; deliberately SHA-256, not SM3."""
    if type(verifier) is not str or not _PKCE_RE.fullmatch(verifier):
        raise OidcValidationError("PKCE verifier must use 43-128 unreserved ASCII characters")
    return b64url_encode(hashlib.sha256(verifier.encode("ascii")).digest())


def verify_id_token(
    token: str,
    *,
    trusted_keys: Mapping[str, EllipticCurvePublicKey],
    issuer: str,
    client_id: str,
    expected_nonce: str,
    now: int,
) -> JsonObject:
    """Verify one fixed-profile SM2 ID Token; never grant tool access with it."""
    if not issuer.startswith("https://") or not client_id or not expected_nonce:
        raise OidcValidationError("fixed issuer, client and session nonce required")
    if type(now) is not int or now < 0:
        raise OidcValidationError("invalid verification time")
    try:
        claims = verify_compact_jws(token, expected_type="ag-id+jwt", trusted_keys=trusted_keys)
    except (InvalidSm2Signature, TypeError) as exc:
        raise OidcValidationError("invalid ID Token signature or type") from exc
    if set(claims) != _ID_FIELDS:
        raise OidcValidationError("ID Token fields do not match the profile")
    if claims["iss"] != issuer or claims["aud"] != client_id:
        raise OidcValidationError("ID Token issuer or audience mismatch")
    if type(claims["sub"]) is not str or not claims["sub"]:
        raise OidcValidationError("invalid ID Token subject")
    if claims["nonce"] != expected_nonce:
        raise OidcValidationError("ID Token nonce mismatch")
    times = (claims["iat"], claims["exp"], claims["auth_time"])
    if any(type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER for value in times):
        raise OidcValidationError("ID Token timestamps must be safe integers")
    issued, expires, authenticated = times
    if not authenticated <= issued <= now < expires or expires - issued > 300:
        raise OidcValidationError("ID Token outside validity window")
    return claims
