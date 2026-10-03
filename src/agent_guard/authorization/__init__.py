"""GM-MVP-1 authorization claim and verification helpers."""

from agent_guard.authorization.browser import BrowserLoginApp
from agent_guard.authorization.claims import ClaimsError, validate_access_claims, validate_child
from agent_guard.authorization.code import CodeExchangeError, CodeExchangePreflight
from agent_guard.authorization.code_service import (
    ApprovedAuthorization,
    AuthorizationCodeError,
    AuthorizationCodeService,
)
from agent_guard.authorization.consent import (
    AuthorizeClient,
    AuthorizeRequestView,
    ConsentError,
    ConsentRedirect,
    ConsentService,
    parse_authorize_params,
)
from agent_guard.authorization.exchange import ExchangeError, ExchangePreflight
from agent_guard.authorization.exchange_service import (
    TokenExchangeError,
    TokenExchangeResult,
    TokenExchangeService,
)
from agent_guard.authorization.forms import FormError, decode_oauth_form
from agent_guard.authorization.login import LoginError, LoginResult, LoginService, SessionContext
from agent_guard.authorization.oidc import OidcValidationError, pkce_s256_challenge, verify_id_token
from agent_guard.authorization.passwords import PasswordError, hash_password, verify_password
from agent_guard.authorization.policy import ChildSpec, DelegationError, GrantPolicy
from agent_guard.authorization.proof import ProofInputError, sign_ag_proof
from agent_guard.authorization.revocation_http import RevocationHttpApp
from agent_guard.authorization.revocation_service import (
    TaskRevocationError,
    TaskRevocationResult,
    TaskRevocationService,
)
from agent_guard.authorization.token_endpoint import TokenClient, TokenEndpoint, TokenResponse
from agent_guard.authorization.verifier import (
    InvocationVerifier,
    VerificationError,
    VerifiedOperationQuery,
)

__all__ = [
    "BrowserLoginApp",
    "ClaimsError",
    "validate_access_claims",
    "validate_child",
    "CodeExchangeError",
    "CodeExchangePreflight",
    "ApprovedAuthorization",
    "AuthorizationCodeError",
    "AuthorizationCodeService",
    "AuthorizeClient",
    "AuthorizeRequestView",
    "ConsentError",
    "ConsentRedirect",
    "ConsentService",
    "parse_authorize_params",
    "LoginError",
    "LoginResult",
    "LoginService",
    "SessionContext",
    "PasswordError",
    "hash_password",
    "verify_password",
    "ExchangeError",
    "ExchangePreflight",
    "TokenExchangeError",
    "TokenExchangeResult",
    "TokenExchangeService",
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
    "RevocationHttpApp",
    "TaskRevocationError",
    "TaskRevocationResult",
    "TaskRevocationService",
    "TokenClient",
    "TokenEndpoint",
    "TokenResponse",
    "InvocationVerifier",
    "VerificationError",
    "VerifiedOperationQuery",
]
