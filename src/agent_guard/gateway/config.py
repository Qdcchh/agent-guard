"""Strict private operator configuration; public AS trust only."""

import re
from dataclasses import dataclass

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.crypto.sm import serialize_sm2_public_key
from agent_guard.identity.resolver import IdentityResolver, RegisteredIdentity, did_web_url
from agent_guard.server.config import ConfigError, _https_url, _string, secret_sha256
from agent_guard.server.factory import _load_public_key
from agent_guard.tools import catalog

_FIELDS = {
    "issuer",
    "as_keys",
    "identities",
    "identity_allowed_hosts",
    "did_documents",
    "catalog",
    "secrets_path",
    "request_timeout_seconds",
    "max_workers",
}
_CATALOG = {
    "requests": (catalog.CatalogRequest, {"request_id", "tenant_id", "task_id", "status"}),
    "documents": (catalog.CatalogDocument, {"document_id", "request_id", "body"}),
    "quotes": (
        catalog.CatalogQuote,
        {"quote_id", "quote_version", "supplier_id", "request_id", "lines"},
    ),
    "deliveries": (catalog.CatalogDelivery, {"delivery_id", "tenant_id", "request_id"}),
    "templates": (catalog.CatalogTemplate, {"template_id", "body"}),
    "recipients": (catalog.CatalogRecipient, {"recipient_id"}),
}


@dataclass(frozen=True)
class GatewayConfig:
    """Canonical bytes isolate every nested operator input from aliases."""

    raw: bytes


@dataclass(frozen=True)
class GatewaySecrets:
    downstream_secret: str


def load_gateway_secrets(raw: bytes):
    value = load_strict_json(raw)
    if (
        type(value) is not dict
        or set(value) != {"note", "downstream_secret"}
        or type(value["note"]) is not str
    ):
        raise ConfigError("invalid gateway secrets fields")
    secret_sha256(value["downstream_secret"])
    return GatewaySecrets(value["downstream_secret"])


def trusted_inputs(value):
    _https_url(value["issuer"], "issuer", allow_query=False)
    keys = value["as_keys"]
    if type(keys) is not dict or not keys:
        raise ConfigError("nonempty AS public keys required")
    as_keys = {_string(k, "AS kid"): _load_public_key(pem, "AS trust") for k, pem in keys.items()}
    hosts = value["identity_allowed_hosts"]
    if (
        type(hosts) is not list
        or not hosts
        or any(type(h) is not str or not h.isascii() for h in hosts)
        or len(hosts) != len(set(hosts))
    ):
        raise ConfigError("approved identity hosts required")
    entries = value["identities"]
    if type(entries) is not list or not entries:
        raise ConfigError("nonempty identity registry required")
    registrations = {}
    current = {}
    for row in entries:
        if (
            type(row) is not dict
            or set(row) != {"tenant_id", "client_id", "did", "kid", "spki_pem", "current"}
            or type(row["current"]) is not bool
        ):
            raise ConfigError("invalid identity registry fields")
        for name in ("tenant_id", "client_id", "did", "kid"):
            _string(row[name], name)
        registration = RegisteredIdentity(
            row["tenant_id"],
            row["client_id"],
            row["did"],
            row["kid"],
            serialize_sm2_public_key(_load_public_key(row["spki_pem"], "identity")),
        )
        key = (registration.tenant_id, registration.client_id, registration.kid)
        if key in registrations:
            raise ConfigError("duplicate identity key")
        registrations[key] = registration
        if row["current"]:
            pair = key[:2]
            if pair in current:
                raise ConfigError("duplicate current identity")
            current[pair] = registration
    if not current:
        raise ConfigError("current identity required")
    documents = value["did_documents"]
    if type(documents) is not dict:
        raise ConfigError("DID snapshots required")
    frozen = {k: canonical_json_bytes(v) for k, v in documents.items()}
    expected = {did_web_url(r.did) for r in current.values()}
    if set(frozen) != expected:
        raise ConfigError("exact current DID snapshots required")
    resolver = IdentityResolver(
        current, allowed_hosts=frozenset(hosts), fetch_document=lambda url: frozen[url]
    )
    for r in current.values():
        resolver.resolve_registered(r.client_id, r.tenant_id, "capabilityInvocation")
    data = value["catalog"]
    if type(data) is not dict or set(data) != set(_CATALOG):
        raise ConfigError("exact catalog collections required")
    seed = {}
    for collection, (kind, fields) in _CATALOG.items():
        rows = data[collection]
        if type(rows) is not list or len(rows) > 256:
            raise ConfigError("bounded catalog array required")
        built = []
        seen = set()
        for row in rows:
            if type(row) is not dict or set(row) != fields:
                raise ConfigError("exact catalog record fields required")
            row = dict(row)
            for name, val in row.items():
                if name not in ("lines", "body"):
                    _string(val, "catalog identifier")
                elif name == "body" and (type(val) is not str or len(val.encode()) > 65536):
                    raise ConfigError("bounded catalog body required")
            lookup_fields = {
                "requests": ("request_id",),
                "documents": ("document_id",),
                "quotes": ("quote_id", "quote_version"),
                "deliveries": ("delivery_id",),
                "templates": ("template_id",),
                "recipients": ("recipient_id",),
            }[collection]
            identity = tuple(row[n] for n in lookup_fields)
            for name in fields - {"lines", "body", "status", "quote_version"}:
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", row[name]):
                    raise ConfigError("invalid catalog identifier")
            if "quote_version" in row and not re.fullmatch(
                r"[1-9][0-9]{0,17}", row["quote_version"]
            ):
                raise ConfigError("invalid quote version")
            if "status" in row and row["status"] not in ("APPROVED", "REJECTED", "PENDING"):
                raise ConfigError("invalid catalog status")
            if identity in seen:
                raise ConfigError("duplicate catalog record")
            seen.add(identity)
            if collection == "quotes":
                lines = row["lines"]
                if type(lines) is not list or not 1 <= len(lines) <= 256:
                    raise ConfigError("bounded quote lines required")
                skus = set()
                for line in lines:
                    if type(line) is not dict or set(line) != {"sku", "quantity", "unit_price_fen"}:
                        raise ConfigError("invalid quote line fields")
                    _string(line["sku"], "sku")
                    if line["sku"] in skus or any(
                        type(line[n]) is not int or not low <= line[n] <= 2**53 - 1
                        for n, low in (("quantity", 1), ("unit_price_fen", 0))
                    ):
                        raise ConfigError("invalid quote line")
                    skus.add(line["sku"])
                row["lines"] = tuple(catalog.CatalogQuoteLine(**v) for v in lines)
            built.append(kind(**row))
        seed[collection] = built
    return as_keys, resolver, registrations, catalog.TrustedCatalog(**seed)


def load_gateway_config(raw: bytes):
    try:
        value = load_strict_json(raw)
        if type(value) is not dict or set(value) != _FIELDS:
            raise ConfigError("exact gateway fields required")
        _string(value["secrets_path"], "secrets_path")
        for name, upper in (("request_timeout_seconds", 60), ("max_workers", 32)):
            if type(value[name]) is not int or not 1 <= value[name] <= upper:
                raise ConfigError("bounded positive gateway setting required")
        trusted_inputs(value)
        return GatewayConfig(canonical_json_bytes(value))
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ConfigError("invalid gateway configuration") from exc
