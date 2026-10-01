"""Deployment-only configuration and secret loading for the AS server.

The configuration file holds public identifiers, paths and TTL bounds; it must
never contain a plaintext client secret, DB credential or private key. Secrets
live in a separate operator-private file and are never committed, logged or
echoed. Scheme, issuer and every proof target come only from this configuration
and the trusted ASGI scope -- never from request headers.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from tongsuopy.crypto import serialization

from agent_guard.contracts.encoding import EncodingError, JsonObject, load_strict_json
from agent_guard.identity.resolver import did_web_url

_SAFE_ID = re.compile(r"[\x21-\x7e]{1,128}\Z", re.ASCII)
_HOST = re.compile(r"[a-z0-9.-]+\Z", re.ASCII)
_CONFIG_FIELDS = {
    "issuer",
    "as_signing_key_path",
    "secrets_path",
    "signing_kid",
    "clients",
    "gateway_client_id",
    "identities",
    "identity_allowed_hosts",
    "did_documents",
    "session_ttl_seconds",
    "csrf_ttl_seconds",
    "request_ttl_seconds",
    "request_timeout_seconds",
}
_SECRET_FIELDS = {"note", "client_secrets", "gateway_secret"}
_TTL_BOUNDS = {
    "session_ttl_seconds": (30, 86400),
    "csrf_ttl_seconds": (30, 86400),
    "request_ttl_seconds": (30, 3600),
    "request_timeout_seconds": (1, 60),
}


class ConfigError(ValueError):
    """A server configuration or secret bundle is invalid or ambiguous."""


@dataclass(frozen=True)
class ClientRegistration:
    client_id: str
    tenant_id: str
    redirect_uri: str


@dataclass(frozen=True)
class IdentityRegistration:
    client_id: str
    tenant_id: str
    did: str
    kid: str
    spki_pem: str


@dataclass(frozen=True)
class ServerConfig:
    issuer: str
    as_signing_key_path: str
    secrets_path: str
    signing_kid: str
    clients: dict[str, ClientRegistration]
    gateway_client_id: str
    identities: dict[str, IdentityRegistration]
    identity_allowed_hosts: frozenset[str]
    did_documents: dict[str, JsonObject]
    session_ttl_seconds: int
    csrf_ttl_seconds: int
    request_ttl_seconds: int
    request_timeout_seconds: int


@dataclass(frozen=True)
class SecretsBundle:
    """Operator-private plaintext secrets; never serialized into config files."""

    note: str
    client_secrets: dict[str, str]
    gateway_secret: str


def secret_sha256(secret: object) -> bytes:
    """Digest one deployment secret; rejects weak or non-ASCII values."""
    if type(secret) is not str or not 32 <= len(secret) <= 256 or not secret.isascii():
        raise ConfigError("secret must be ASCII within [32, 256] characters")
    return hashlib.sha256(secret.encode("ascii")).digest()


def _string(value: object, name: str) -> str:
    if type(value) is not str or not _SAFE_ID.fullmatch(value):
        raise ConfigError(f"{name} must be printable ASCII within 128 characters")
    return value


def _https_url(value: object, name: str, *, allow_query: bool) -> str:
    if type(value) is not str:
        raise ConfigError(f"{name} must be a string")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or (not allow_query and parsed.query)
    ):
        raise ConfigError(f"{name} must be an HTTPS URL")
    return value


def _ttl(value: object, name: str) -> int:
    lower, upper = _TTL_BOUNDS[name]
    if type(value) is not int or isinstance(value, bool) or not lower <= value <= upper:
        raise ConfigError(f"{name} must be an integer within [{lower}, {upper}]")
    return value


def _spki_pem(value: object, name: str) -> str:
    if type(value) is not str:
        raise ConfigError(f"{name} must be a PEM string")
    try:
        key = serialization.load_pem_public_key(value.encode("ascii"))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ConfigError(f"{name} is not a valid PEM public key") from exc
    if getattr(key, "curve", None) is None or key.curve.name != "SM2":
        raise ConfigError(f"{name} is not an SM2 public key")
    return value


def load_server_config(raw: bytes) -> ServerConfig:
    """Parse and validate one strict-JSON server configuration document."""
    try:
        value = load_strict_json(raw)
    except (EncodingError, UnicodeError) as exc:
        raise ConfigError("config must be strict JSON without duplicates") from exc
    if type(value) is not dict or set(value) != _CONFIG_FIELDS:
        raise ConfigError("config fields do not match the profile")
    issuer = _https_url(value["issuer"], "issuer", allow_query=False)
    if urlsplit(issuer).path not in ("", "/"):
        raise ConfigError("issuer must be an HTTPS origin without a path")
    signing_kid = _string(value["signing_kid"], "signing_kid")
    as_key_path = _string(value["as_signing_key_path"], "as_signing_key_path")
    secrets_path = _string(value["secrets_path"], "secrets_path")
    gateway_client_id = _string(value["gateway_client_id"], "gateway_client_id")

    clients_raw = value["clients"]
    if type(clients_raw) is not dict or not clients_raw:
        raise ConfigError("clients must be a nonempty object")
    clients: dict[str, ClientRegistration] = {}
    for client_id, entry in clients_raw.items():
        client_id = _string(client_id, "client_id")
        if type(entry) is not dict or set(entry) != {"tenant_id", "redirect_uri"}:
            raise ConfigError(f"client {client_id} fields do not match the profile")
        clients[client_id] = ClientRegistration(
            client_id=client_id,
            tenant_id=_string(entry["tenant_id"], "tenant_id"),
            redirect_uri=_https_url(entry["redirect_uri"], "redirect_uri", allow_query=True),
        )

    hosts_raw = value["identity_allowed_hosts"]
    if (
        type(hosts_raw) is not list
        or not hosts_raw
        or len(set(map(str, hosts_raw))) != len(hosts_raw)
    ):
        raise ConfigError("identity_allowed_hosts must be a unique nonempty list")
    allowed_hosts = frozenset()
    for host in hosts_raw:
        if type(host) is not str or not _HOST.fullmatch(host):
            raise ConfigError("identity host must be a plain lowercase hostname")
        allowed_hosts = allowed_hosts | {host}

    identities_raw = value["identities"]
    if type(identities_raw) is not dict or not identities_raw:
        raise ConfigError("identities must be a nonempty object")
    identities: dict[str, IdentityRegistration] = {}
    for client_id, entry in identities_raw.items():
        client_id = _string(client_id, "client_id")
        if type(entry) is not dict or set(entry) != {"tenant_id", "did", "kid", "spki_pem"}:
            raise ConfigError(f"identity {client_id} fields do not match the profile")
        identity = IdentityRegistration(
            client_id=client_id,
            tenant_id=_string(entry["tenant_id"], "tenant_id"),
            did=entry["did"] if type(entry["did"]) is str else "",
            kid=_string(entry["kid"], "kid"),
            spki_pem=_spki_pem(entry["spki_pem"], f"identity {client_id} spki_pem"),
        )
        try:
            document_url = did_web_url(identity.did)
        except ValueError as exc:
            raise ConfigError(f"identity {client_id} did is not a did:web identifier") from exc
        if identity.kid != identity.did + "#" + identity.kid.split("#", 1)[-1]:
            raise ConfigError(f"identity {client_id} kid is not scoped to its did")
        if document_url.split("/", 3)[2] not in allowed_hosts:
            raise ConfigError(f"identity {client_id} did host is not approved")
        identities[client_id] = identity

    documents_raw = value["did_documents"]
    if type(documents_raw) is not dict or not documents_raw:
        raise ConfigError("did_documents must be a nonempty object")
    documents: dict[str, JsonObject] = {}
    for url, document in documents_raw.items():
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.hostname not in allowed_hosts
            or type(document) is not dict
        ):
            raise ConfigError(f"did document {url!r} is not an approved HTTPS object")
        documents[url] = document
    for identity in identities.values():
        if did_web_url(identity.did) not in documents:
            raise ConfigError(f"identity {identity.client_id} has no approved did document")

    for name in _TTL_BOUNDS:
        _ttl(value[name], name)

    return ServerConfig(
        issuer=issuer,
        as_signing_key_path=as_key_path,
        secrets_path=secrets_path,
        signing_kid=signing_kid,
        clients=clients,
        gateway_client_id=gateway_client_id,
        identities=identities,
        identity_allowed_hosts=allowed_hosts,
        did_documents=documents,
        session_ttl_seconds=value["session_ttl_seconds"],
        csrf_ttl_seconds=value["csrf_ttl_seconds"],
        request_ttl_seconds=value["request_ttl_seconds"],
        request_timeout_seconds=value["request_timeout_seconds"],
    )


def resolve_paths(config: ServerConfig, base_dir: str | Path) -> ServerConfig:
    """Resolve relative key/secrets paths against the configuration directory."""

    base = Path(base_dir)

    def resolved(value: str) -> str:
        path = Path(value)
        return str(path if path.is_absolute() else base / path)

    return replace(
        config,
        as_signing_key_path=resolved(config.as_signing_key_path),
        secrets_path=resolved(config.secrets_path),
    )


def load_secrets(raw: bytes) -> SecretsBundle:
    """Parse the operator-private secret file; validates entropy, stores nothing."""
    try:
        value = load_strict_json(raw)
    except (EncodingError, UnicodeError) as exc:
        raise ConfigError("secrets must be strict JSON without duplicates") from exc
    if type(value) is not dict or set(value) != _SECRET_FIELDS:
        raise ConfigError("secret file fields do not match the profile")
    note = value["note"]
    if type(note) is not str:
        raise ConfigError("secret file note must be a string")
    client_secrets_raw = value["client_secrets"]
    if type(client_secrets_raw) is not dict or not client_secrets_raw:
        raise ConfigError("client_secrets must be a nonempty object")
    client_secrets: dict[str, str] = {}
    for client_id, secret in client_secrets_raw.items():
        client_id = _string(client_id, "client_id")
        secret_sha256(secret)
        client_secrets[client_id] = secret
    gateway_secret = value["gateway_secret"]
    secret_sha256(gateway_secret)
    return SecretsBundle(note=note, client_secrets=client_secrets, gateway_secret=gateway_secret)
