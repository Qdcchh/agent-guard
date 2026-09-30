"""Client-side AG-Proof construction for the four fixed project purposes."""

from __future__ import annotations

import secrets
from urllib.parse import urlsplit

from tongsuopy.crypto.asymciphers.ec import EllipticCurvePrivateKey

from agent_guard.contracts.encoding import MAX_SAFE_INTEGER, JsonObject, canonical_json_bytes
from agent_guard.crypto.sm import sign_compact_jws, sm3_b64url

PURPOSES = frozenset({"code-exchange", "delegate", "invoke", "result-read"})


class ProofInputError(ValueError):
    """An AG-Proof signing input is outside the fixed project profile."""


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
