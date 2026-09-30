"""GM-MVP-1 authorization claim and verification helpers."""

from agent_guard.authorization.claims import ClaimsError, validate_access_claims, validate_child
from agent_guard.authorization.code import CodeExchangeError, CodeExchangePreflight
from agent_guard.authorization.code_service import (
    ApprovedAuthorization,
    AuthorizationCodeError,
    AuthorizationCodeService,
)
from agent_guard.authorization.exchange import ExchangeError, ExchangePreflight
from agent_guard.authorization.forms import FormError, decode_oauth_form
from agent_guard.authorization.oidc import OidcValidationError, pkce_s256_challenge, verify_id_token
from agent_guard.authorization.policy import ChildSpec, DelegationError, GrantPolicy
from agent_guard.authorization.proof import ProofInputError, sign_ag_proof
from agent_guard.authorization.verifier import InvocationVerifier, VerificationError

__all__ = [
    "ClaimsError",
    "validate_access_claims",
    "validate_child",
    "CodeExchangeError",
    "CodeExchangePreflight",
    "ApprovedAuthorization",
    "AuthorizationCodeError",
    "AuthorizationCodeService",
    "ExchangeError",
    "ExchangePreflight",
    "FormError",
    "decode_oauth_form",
    "OidcValidationError",
    "pkce_s256_challenge",
    "verify_id_token",
    "ChildSpec",
    "DelegationError",
    "GrantPolicy",
    "ProofInputError",
    "sign_ag_proof",
    "InvocationVerifier",
    "VerificationError",
]
