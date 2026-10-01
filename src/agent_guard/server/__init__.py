"""Deployment assembly for the AS/OP: configuration, secrets and composed app."""

from agent_guard.server.config import (
    ClientRegistration,
    ConfigError,
    IdentityRegistration,
    SecretsBundle,
    ServerConfig,
    load_secrets,
    load_server_config,
    resolve_paths,
    secret_sha256,
)
from agent_guard.server.factory import build_app
from agent_guard.server.middleware import RequestTimeoutMiddleware

__all__ = [
    "ClientRegistration",
    "ConfigError",
    "IdentityRegistration",
    "RequestTimeoutMiddleware",
    "SecretsBundle",
    "ServerConfig",
    "build_app",
    "load_secrets",
    "load_server_config",
    "resolve_paths",
    "secret_sha256",
]
