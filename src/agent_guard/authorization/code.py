"""Authorization-code exchange preflight before the one-use AS transaction."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urlsplit

from agent_guard.authorization.forms import FormError, decode_oauth_form
from agent_guard.authorization.oidc import OidcValidationError, pkce_s256_challenge
from agent_guard.authorization.proof import ProofVerificationError, verify_ag_proof
from agent_guard.contracts.encoding import EncodingError, b64url_decode, canonical_json_bytes
from agent_guard.crypto.sm import sm3_b64url
from agent_guard.identity.resolver import IdentityError, IdentityResolver

_FORM_FIELDS = {"grant_type", "code", "redirect_uri", "code_verifier"}


class CodeExchangeError(ValueError):
    """A code exchange request is malformed or not bound to its client key."""


@dataclass(frozen=True)
class CodeExchangePreflightResult:
    client_id: str
    tenant_id: str
    holder_did: str
    holder_kid: str
    holder_spki_sm3: str
    code_sha256: bytes
    redirect_uri: str
    pkce_challenge: str
    proof_jti: str
    proof_iat: int
    proof_exp: int
    proof_digest: str
    request_digest: str


class CodeExchangePreflight:
    """Validate form/AG-Proof before consuming a persisted authorization code.

    ``tenant_id`` and ``expected_redirect_uri`` must come from trusted client
    and code records. The AS transaction must compare code hash, client, task,
    redirect, challenge, expiry and unused status under lock; consume the code
    and create the unique root atomically. This class never does either.
    """

    def __init__(self, *, token_endpoint: str, identities: IdentityResolver) -> None:
        parsed = urlsplit(token_endpoint)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("fixed HTTPS token endpoint required")
        self._token_endpoint = token_endpoint
        self._identities = identities

    def verify(
        self,
        *,
        raw_form: bytes,
        proof: str,
        authenticated_client_id: str,
        tenant_id: str,
        expected_redirect_uri: str,
        now: int,
    ) -> CodeExchangePreflightResult:
        if type(authenticated_client_id) is not str or not authenticated_client_id:
            raise CodeExchangeError("authenticated client required")
        if type(tenant_id) is not str or not tenant_id:
            raise CodeExchangeError("trusted tenant required")
        try:
            form = decode_oauth_form(raw_form)
            if set(form) != _FORM_FIELDS or form["grant_type"] != "authorization_code":
                raise CodeExchangeError("invalid authorization-code form")
            if form["redirect_uri"] != expected_redirect_uri:
                raise CodeExchangeError("redirect_uri mismatch")
            code = form["code"]
            if len(code) > 128 or len(b64url_decode(code)) < 16:
                raise CodeExchangeError("authorization code must be high-entropy base64url")
            challenge = pkce_s256_challenge(form["code_verifier"])
            identity = self._identities.resolve_registered(
                authenticated_client_id, tenant_id, "authentication"
            )
            signed_proof = verify_ag_proof(
                proof,
                trusted_keys={identity.registration.kid: identity.public_key},
                client_id=authenticated_client_id,
                purpose="code-exchange",
                endpoint=self._token_endpoint,
                token=None,
                body=form,
                now=now,
            )
        except (
            FormError,
            EncodingError,
            OidcValidationError,
            IdentityError,
            ProofVerificationError,
            TypeError,
        ) as exc:
            raise CodeExchangeError("invalid code exchange form, client key or proof") from exc
        return CodeExchangePreflightResult(
            client_id=authenticated_client_id,
            tenant_id=tenant_id,
            holder_did=identity.registration.did,
            holder_kid=identity.registration.kid,
            holder_spki_sm3=identity.registration.spki_sm3,
            code_sha256=hashlib.sha256(code.encode("ascii")).digest(),
            redirect_uri=expected_redirect_uri,
            pkce_challenge=challenge,
            proof_jti=signed_proof["jti"],
            proof_iat=signed_proof["iat"],
            proof_exp=signed_proof["exp"],
            proof_digest=sm3_b64url(proof.encode("ascii")),
            request_digest=sm3_b64url(canonical_json_bytes(form)),
        )
