"""Assemble the full AS/OP application from validated private configuration.

``build_app`` is the single composition point: every route, service and trust
input comes from :class:`ServerConfig` and :class:`SecretsBundle`. No request
header influences issuer, endpoints, keys or tenants. The returned application
still requires the ASGI server to supply an accurate ``https`` scheme.
"""

from __future__ import annotations

from collections.abc import Callable

import psycopg
from tongsuopy.crypto import serialization

from agent_guard.authorization.browser import BrowserLoginApp
from agent_guard.authorization.code_service import AuthorizationCodeService
from agent_guard.authorization.consent import AuthorizeClient, ConsentService
from agent_guard.authorization.discovery import DiscoveryEndpoint
from agent_guard.authorization.exchange_service import TokenExchangeService
from agent_guard.authorization.grant_revocation_service import GrantRevocationService
from agent_guard.authorization.http_app import AuthorizationHttpApp
from agent_guard.authorization.introspection import IntrospectionService
from agent_guard.authorization.introspection_endpoint import IntrospectionEndpoint
from agent_guard.authorization.login import LoginService
from agent_guard.authorization.revocation_http import RevocationHttpApp
from agent_guard.authorization.revocation_service import TaskRevocationService
from agent_guard.authorization.token_endpoint import TokenClient, TokenEndpoint
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.crypto.sm import serialize_sm2_public_key
from agent_guard.identity.resolver import IdentityError, IdentityResolver, RegisteredIdentity
from agent_guard.server.config import ConfigError, SecretsBundle, ServerConfig, secret_sha256
from agent_guard.server.middleware import RequestTimeoutMiddleware
from agent_guard.server.private_files import read_private_file


def _load_as_private_key(path: str):
    try:
        raw = read_private_file(path)
        key = serialization.load_pem_private_key(raw, password=None)
    except (OSError, ValueError, TypeError) as exc:
        raise ConfigError("AS signing key cannot be loaded from its PEM path") from exc
    if getattr(key, "curve", None) is None or key.curve.name != "SM2":
        raise ConfigError("AS signing key is not an SM2 private key")
    return key


def _load_public_key(pem: str, label: str):
    try:
        key = serialization.load_pem_public_key(pem.encode("ascii"))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ConfigError(f"{label} spki_pem is invalid") from exc
    if getattr(key, "curve", None) is None or key.curve.name != "SM2":
        raise ConfigError(f"{label} key is not SM2")
    return key


def _load_registered_spki(pem: str, client_id: str) -> bytes:
    return serialize_sm2_public_key(_load_public_key(pem, f"identity {client_id}"))


def build_app(
    config: ServerConfig,
    secrets: SecretsBundle,
    *,
    dsn: str,
    connector: Callable[..., psycopg.Connection] = psycopg.connect,
) -> RequestTimeoutMiddleware:
    """Compose every AS/OP service and route; fails fast on configuration errors."""
    if not isinstance(config, ServerConfig) or not isinstance(secrets, SecretsBundle):
        raise ConfigError("validated server config and secret bundle required")
    if type(dsn) is not str or not dsn:
        raise ConfigError("a database DSN is required")
    if set(config.clients) != set(secrets.client_secrets):
        raise ConfigError("client secret bundle does not cover every configured client")
    for client_id in config.clients:
        secret_sha256(secrets.client_secrets[client_id])
    secret_sha256(secrets.gateway_secret)

    as_key = _load_as_private_key(config.as_signing_key_path)
    as_public = as_key.public_key()
    verification_keys = {config.signing_kid: as_public}
    for kid, pem in config.historical_verification_keys.items():
        verification_keys[kid] = _load_public_key(pem, f"historical:{kid}")
    token_endpoint = config.issuer.rstrip("/") + "/oauth/token"

    registrations: dict[tuple[str, str], RegisteredIdentity] = {}
    for client_id, identity in config.identities.items():
        spki_der = _load_registered_spki(identity.spki_pem, client_id)
        registrations[(identity.tenant_id, identity.client_id)] = RegisteredIdentity(
            tenant_id=identity.tenant_id,
            client_id=identity.client_id,
            did=identity.did,
            kid=identity.kid,
            spki_der=spki_der,
        )

    # Capture private immutable bytes once; caller aliases cannot change runtime trust.
    documents = {url: canonical_json_bytes(doc) for url, doc in config.did_documents.items()}

    def fetch_document(url: str) -> bytes:
        document = documents.get(url)
        if document is None:
            raise IdentityError("DID document unavailable")
        return document

    identities = IdentityResolver(
        registrations,
        allowed_hosts=config.identity_allowed_hosts,
        fetch_document=fetch_document,
    )

    codes = AuthorizationCodeService(
        dsn,
        issuer=config.issuer,
        token_endpoint=token_endpoint,
        signing_key=as_key,
        signing_kid=config.signing_kid,
        identities=identities,
        connector=connector,
    )
    exchanges = TokenExchangeService(
        dsn,
        issuer=config.issuer,
        token_endpoint=token_endpoint,
        signing_key=as_key,
        signing_kid=config.signing_kid,
        identities=identities,
        verification_keys=verification_keys,
        connector=connector,
    )
    login = LoginService(
        dsn,
        session_ttl_seconds=config.session_ttl_seconds,
        csrf_ttl_seconds=config.csrf_ttl_seconds,
        connector=connector,
    )
    consent = ConsentService(
        dsn,
        clients={
            client_id: AuthorizeClient(
                client_id=client_id,
                tenant_id=registration.tenant_id,
                redirect_uri=registration.redirect_uri,
            )
            for client_id, registration in config.clients.items()
        },
        sessions=login,
        codes=codes,
        request_ttl_seconds=config.request_ttl_seconds,
        connector=connector,
    )

    token_clients = {
        client_id: TokenClient(
            client_id,
            registration.tenant_id,
            registration.redirect_uri,
            secret_sha256(secrets.client_secrets[client_id]),
        )
        for client_id, registration in config.clients.items()
    }
    gateway_client = TokenClient(
        config.gateway_client_id, "service", None, secret_sha256(secrets.gateway_secret)
    )

    try:
        token_routes = TokenEndpoint(clients=token_clients, codes=codes, exchanges=exchanges)
    except ValueError as exc:
        raise ConfigError("invalid trusted client registration") from exc

    app = AuthorizationHttpApp(
        discovery=DiscoveryEndpoint(issuer=config.issuer, signing_keys=verification_keys),
        token=token_routes,
        introspection=IntrospectionEndpoint(
            gateway_client=gateway_client,
            inspector=IntrospectionService(
                dsn,
                issuer=config.issuer,
                as_keys=verification_keys,
                identities=identities,
                connector=connector,
            ),
        ),
        browser=BrowserLoginApp(login=login, consent=consent),
        revocation=RevocationHttpApp(
            sessions=login,
            tasks=TaskRevocationService(dsn, connector=connector),
            grants=GrantRevocationService(dsn, connector=connector),
        ),
    )
    return RequestTimeoutMiddleware(app, timeout_seconds=config.request_timeout_seconds)
