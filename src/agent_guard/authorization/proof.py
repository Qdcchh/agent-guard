"""Client-side AG-Proof construction for the four fixed project purposes."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from urllib.parse import urlsplit

from tongsuopy.crypto.asymciphers.ec import EllipticCurvePrivateKey, EllipticCurvePublicKey

from agent_guard.contracts.encoding import (
    MAX_SAFE_INTEGER,
    EncodingError,
    JsonObject,
    b64url_decode,
    canonical_json_bytes,
)
from agent_guard.crypto.sm import (
    InvalidSm2Signature,
    sign_compact_jws,
    sm3_b64url,
    verify_compact_jws,
)

PURPOSES = frozenset({"code-exchange", "delegate", "invoke", "result-read"})


class ProofInputError(ValueError):
    """An AG-Proof signing input is outside the fixed project profile."""


class ProofVerificationError(ValueError):
    """An AG-Proof does not verify or bind the expected request."""


_PROOF_FIELDS = {
    "profile",
    "purpose",
    "client_id",
    "jti",
    "iat",
    "exp",
    "htm",
    "htu",
    "token_sm3",
    "body_sm3",
}


def sign_ag_proof(
    private_key: EllipticCurvePrivateKey,
    *,
    kid: str,
    client_id: str,
    purpose: str,
    endpoint: str,
    body: JsonObject,
    token: str | None,
    now: int,
    lifetime_seconds: int = 60,
) -> str:
    """Sign a fresh proof bound to a canonical JSON/form mapping.

    For OAuth form requests, ``body`` must be the strict UTF-8 decoded
    key-to-string mapping; callers must reject duplicate form keys before
    passing it here. The proof is distinct from business idempotency keys.
    """
    if purpose not in PURPOSES:
        raise ProofInputError("unsupported AG-Proof purpose")
    if type(client_id) is not str or not client_id:
        raise ProofInputError("client_id required")
    if type(endpoint) is not str:
        raise ProofInputError("endpoint must be a string")
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ProofInputError("endpoint must be fixed HTTPS without query or fragment")
    if type(now) is not int or not 0 <= now <= MAX_SAFE_INTEGER:
        raise ProofInputError("invalid proof time")
    if type(lifetime_seconds) is not int or not 1 <= lifetime_seconds <= 60:
        raise ProofInputError("proof lifetime must be 1-60 seconds")
    if now > MAX_SAFE_INTEGER - lifetime_seconds:
        raise ProofInputError("proof expiration exceeds safe integer range")
    if type(body) is not dict:
        raise ProofInputError("body must be a JSON/form mapping")
    if purpose == "code-exchange":
        if token is not None:
            raise ProofInputError("code exchange must not bind a token")
    elif type(token) is not str or not token or not token.isascii():
        raise ProofInputError("this proof purpose requires an ASCII subject/access token")
    payload: JsonObject = {
        "profile": "GM-MVP-1",
        "purpose": purpose,
        "client_id": client_id,
        "jti": secrets.token_urlsafe(24),
        "iat": now,
        "exp": now + lifetime_seconds,
        "htm": "POST",
        "htu": endpoint,
        "token_sm3": None if token is None else sm3_b64url(token.encode("ascii")),
        "body_sm3": sm3_b64url(canonical_json_bytes(body)),
    }
    return sign_compact_jws(private_key, payload, key_id=kid, token_type="ag-pop+jwt")


def verify_ag_proof(
    proof: str,
    *,
    trusted_keys: Mapping[str, EllipticCurvePublicKey],
    client_id: str,
    purpose: str,
    endpoint: str,
    token: str | None,
    body: JsonObject,
    now: int,
) -> JsonObject:
    """Verify one exact POST AG-Proof without claiming replay registration."""
    if purpose not in PURPOSES or type(now) is not int or now < 0:
        raise ProofVerificationError("unsupported purpose or verification time")
    if type(body) is not dict or type(client_id) is not str or not client_id:
        raise ProofVerificationError("invalid proof context")
    if purpose == "code-exchange" and token is not None:
        raise ProofVerificationError("code exchange must not bind a token")
    if purpose != "code-exchange" and token is None:
        raise ProofVerificationError("proof purpose requires a token")
    if token is not None and (type(token) is not str or not token.isascii()):
        raise ProofVerificationError("token must be ASCII")
    try:
        claims = verify_compact_jws(proof, expected_type="ag-pop+jwt", trusted_keys=trusted_keys)
    except (InvalidSm2Signature, TypeError) as exc:
        raise ProofVerificationError("invalid proof signature or type") from exc
    if set(claims) != _PROOF_FIELDS:
        raise ProofVerificationError("proof fields do not match the profile")
    if (
        claims["profile"] != "GM-MVP-1"
        or claims["purpose"] != purpose
        or claims["client_id"] != client_id
        or claims["htm"] != "POST"
        or claims["htu"] != endpoint
    ):
        raise ProofVerificationError("proof context mismatch")
    jti = claims["jti"]
    if type(jti) is not str or len(jti) > 128:
        raise ProofVerificationError("proof jti must be a string")
    try:
        if len(b64url_decode(jti)) < 16:
            raise ProofVerificationError("proof jti must encode at least 128 bits")
    except EncodingError as exc:
        raise ProofVerificationError("proof jti must be canonical base64url") from exc
    iat, exp = claims["iat"], claims["exp"]
    if type(iat) is not int or type(exp) is not int or not iat <= exp <= iat + 60:
        raise ProofVerificationError("invalid proof timestamps")
    if iat > now + 5 or now >= exp:
        raise ProofVerificationError("stale proof")
    expected_token_digest = None if token is None else sm3_b64url(token.encode("ascii"))
    if claims["token_sm3"] != expected_token_digest:
        raise ProofVerificationError("proof does not bind token")
    try:
        body_digest = sm3_b64url(canonical_json_bytes(body))
    except (EncodingError, TypeError) as exc:
        raise ProofVerificationError("invalid proof body mapping") from exc
    if claims["body_sm3"] != body_digest:
        raise ProofVerificationError("proof does not bind body")
    return claims
