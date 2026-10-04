"""Static Token Exchange preflight; never a substitute for AS issuance locks."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from tongsuopy.crypto.asymciphers.ec import EllipticCurvePublicKey

from agent_guard.authorization.claims import AccessClaims, ClaimsError, validate_access_claims
from agent_guard.authorization.forms import FormError, decode_oauth_form
from agent_guard.authorization.policy import ChildSpec, DelegationError, GrantPolicy
from agent_guard.authorization.proof import ProofVerificationError, verify_ag_proof
from agent_guard.contracts.encoding import EncodingError, canonical_json_bytes, load_strict_json
from agent_guard.crypto.sm import InvalidSm2Signature, sm3_b64url, verify_compact_jws
from agent_guard.identity.resolver import IdentityError, IdentityResolver, ResolvedIdentity

TOKEN_EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
_FORM_FIELDS = {
    "grant_type",
    "subject_token",
    "subject_token_type",
    "requested_token_type",
    "audience",
    "scope",
    "ag_delegate_client_id",
    "ag_amount_limit_fen",
    "ag_call_limit",
    "ag_ttl_seconds",
    "ag_delegation_remaining",
    "ag_constraints",
    "ag_delegation_key",
}
_POLICY_FIELDS = _FORM_FIELDS - {
    "grant_type",
    "subject_token",
    "subject_token_type",
    "requested_token_type",
}


class ExchangeError(ValueError):
    """Static Token Exchange authentication, proof or narrowing failed."""


@dataclass(frozen=True)
class AuthenticatedExchange:
    """Signed parent/form/proof without a new-child decision yet."""

    parent: AccessClaims
    recipient: ResolvedIdentity
    form: dict[str, str]
    subject_token: str
    proof_jti: str
    proof_iat: int
    proof_exp: int
    token_digest: str
    proof_digest: str
    request_digest: str
    request_bytes: bytes

    @property
    def requested_child(self) -> dict[str, str]:
        return {key: self.form[key] for key in _POLICY_FIELDS}


@dataclass(frozen=True)
class ExchangePreflightResult:
    parent: AccessClaims
    child: ChildSpec
    proof_jti: str
    proof_iat: int
    proof_exp: int
    token_digest: str
    proof_digest: str
    request_digest: str


class ExchangePreflight:
    """Validate exactly one authenticated delegated exchange request.

    ``authenticated_client_id`` must come from successful Basic client
    authentication, not the request body. The caller must recheck parent,
    ancestors, recipient, proof replay and idempotency under the shared root
    lock before creating a grant or signing a child token.
    """

    def __init__(
        self,
        *,
        issuer: str,
        token_endpoint: str,
        as_keys: dict[str, EllipticCurvePublicKey],
        identities: IdentityResolver,
    ) -> None:
        parsed = urlsplit(token_endpoint)
        if (
            type(issuer) is not str
            or not issuer.startswith("https://")
            or parsed.scheme != "https"
            or parsed.query
            or parsed.fragment
            or not parsed.netloc
            or not as_keys
        ):
            raise ValueError("fixed HTTPS issuer, token endpoint and AS keys required")
        self._issuer = issuer
        self._token_endpoint = token_endpoint
        self._as_keys = dict(as_keys)
        self._identities = identities
        self._policy = GrantPolicy(issuer=issuer)

    def verify(
        self,
        *,
        raw_form: bytes,
        proof: str,
        authenticated_client_id: str,
        now: int,
    ) -> ExchangePreflightResult:
        authenticated = self.authenticate(
            raw_form=raw_form,
            proof=proof,
            authenticated_client_id=authenticated_client_id,
            now=now,
        )
        try:
            child = self._policy.validate_child(
                authenticated.parent,
                authenticated.requested_child,
                authenticated.recipient,
                now=now,
            )
        except DelegationError as exc:
            raise ExchangeError("invalid requested child") from exc
        return ExchangePreflightResult(
            parent=authenticated.parent,
            child=child,
            proof_jti=authenticated.proof_jti,
            proof_iat=authenticated.proof_iat,
            proof_exp=authenticated.proof_exp,
            token_digest=authenticated.token_digest,
            proof_digest=authenticated.proof_digest,
            request_digest=authenticated.request_digest,
        )

    def authenticate(
        self,
        *,
        raw_form: bytes,
        proof: str,
        authenticated_client_id: str,
        now: int,
    ) -> AuthenticatedExchange:
        """Verify parent/holder/proof, deferring child policy to the AS lock."""
        try:
            form = decode_oauth_form(raw_form)
        except FormError as exc:
            raise ExchangeError("malformed OAuth form") from exc
        if set(form) != _FORM_FIELDS:
            raise ExchangeError("unsupported or missing Token Exchange parameter")
        if (
            form["grant_type"] != TOKEN_EXCHANGE_GRANT
            or form["subject_token_type"] != ACCESS_TOKEN_TYPE
            or form["requested_token_type"] != ACCESS_TOKEN_TYPE
        ):
            raise ExchangeError("unsupported Token Exchange token types")
        try:
            constraints = load_strict_json(form["ag_constraints"])
            if canonical_json_bytes(constraints).decode("utf-8") != form["ag_constraints"]:
                raise ExchangeError("ag_constraints must use canonical JSON")
            token = form["subject_token"]
            raw_parent = verify_compact_jws(
                token, expected_type="ag-at+jwt", trusted_keys=self._as_keys
            )
            parent = validate_access_claims(raw_parent, issuer=self._issuer, now=now)
            if authenticated_client_id != raw_parent["client_id"]:
                raise ExchangeError("Basic client does not hold subject token")
            holder = self._identities.resolve_registered(
                raw_parent["client_id"], raw_parent["ag_tenant_id"], "capabilityDelegation"
            )
            if (
                parent.actors[0] != holder.registration.did
                or raw_parent["ag_cnf"]["kid"] != holder.registration.kid
                or raw_parent["ag_cnf"]["spki_sm3"] != holder.registration.spki_sm3
            ):
                raise ExchangeError("parent token holder binding mismatch")
            signed_proof = verify_ag_proof(
                proof,
                trusted_keys={holder.registration.kid: holder.public_key},
                client_id=authenticated_client_id,
                purpose="delegate",
                endpoint=self._token_endpoint,
                token=token,
                body=form,
                now=now,
            )
            recipient = self._identities.resolve_registered(
                form["ag_delegate_client_id"],
                raw_parent["ag_tenant_id"],
                "capabilityInvocation",
            )
        except (
            EncodingError,
            InvalidSm2Signature,
            ClaimsError,
            IdentityError,
            ProofVerificationError,
            TypeError,
            UnicodeError,
        ) as exc:
            raise ExchangeError("invalid Token Exchange token, holder or proof") from exc
        request_bytes = canonical_json_bytes(form)
        return AuthenticatedExchange(
            parent=parent,
            recipient=recipient,
            form=form,
            subject_token=token,
            proof_jti=signed_proof["jti"],
            proof_iat=signed_proof["iat"],
            proof_exp=signed_proof["exp"],
            token_digest=sm3_b64url(token.encode("ascii")),
            proof_digest=sm3_b64url(proof.encode("ascii")),
            request_digest=sm3_b64url(request_bytes),
            request_bytes=request_bytes,
        )
