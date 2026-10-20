"""Private receipt signer configuration; no AS, holder or downstream secrets."""

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from tongsuopy.crypto import serialization

from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
from agent_guard.execution.receipt_publication import InternalPublisher, ReceiptVerifier
from agent_guard.gateway.config import load_gateway_config, receipt_public_keys
from agent_guard.identity.resolver import RegisteredIdentity, did_web_url
from agent_guard.server.config import ConfigError, _https_url, _string
from agent_guard.server.factory import _load_public_key
from agent_guard.server.private_files import private_directory, read_private_file

BOUNDS = {
    "connect_timeout": (1, 30, 5),
    "lock_timeout_ms": (1, 60000, 10000),
    "statement_timeout_ms": (1, 60000, 15000),
    "batch_size": (1, 256, 32),
    "poll_interval_ms": (100, 60000, 1000),
}
_FIELDS = {
    "issuer",
    "as_keys",
    "identities",
    "receipt_keys",
    "signing_kid",
    "private_key_path",
} | set(BOUNDS)


@dataclass(frozen=True)
class ReceiptWorkerConfig:
    raw: bytes = field(repr=False)
    private_key: object = field(repr=False)

    def publisher(self, dsn):
        value = load_strict_json(self.raw)
        as_keys, registrations, public_keys = _trust(value)
        provider = PermissionSnapshotProvider(
            dsn, issuer=value["issuer"], as_keys=as_keys, registrations=registrations
        )
        verifier = ReceiptVerifier(
            issuer=value["issuer"],
            as_keys=as_keys,
            gateway_keys=public_keys,
            registrations=registrations,
            permission_provider=provider,
        )
        return InternalPublisher(
            dsn,
            private_key=self.private_key,
            signing_kid=value["signing_kid"],
            verifier=verifier,
            **{
                name: value[name]
                for name in ("connect_timeout", "lock_timeout_ms", "statement_timeout_ms")
            },
        )


def _trust(value):
    _https_url(value["issuer"], "issuer", allow_query=False)
    if type(value["as_keys"]) is not dict or not value["as_keys"]:
        raise ConfigError("nonempty AS public trust required")
    if any(type(pem) is not str for pem in value["as_keys"].values()):
        raise ConfigError("AS public PEM required")
    as_keys = {
        _string(k, "AS kid"): _load_public_key(pem, "AS trust")
        for k, pem in value["as_keys"].items()
    }
    rows = value["identities"]
    if type(rows) is not list or not 1 <= len(rows) <= 256:
        raise ConfigError("bounded historical identity registry required")
    registrations = {}
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"tenant_id", "client_id", "did", "kid", "spki_pem", "current"}
            or type(row["current"]) is not bool
        ):
            raise ConfigError("exact public identity fields required")
        for name in ("tenant_id", "client_id", "did", "kid"):
            _string(row[name], name)
        did_web_url(row["did"])
        if not row["kid"].startswith(row["did"] + "#") or row["kid"] == row["did"] + "#":
            raise ConfigError("identity kid must belong to DID")
        if type(row["spki_pem"]) is not str:
            raise ConfigError("identity public PEM required")
        registration = RegisteredIdentity(
            row["tenant_id"],
            row["client_id"],
            row["did"],
            row["kid"],
            serialize_sm2_public_key(_load_public_key(row["spki_pem"], "identity")),
        )
        key = (registration.tenant_id, registration.client_id, registration.kid)
        if key in registrations:
            raise ConfigError("duplicate exact historical identity tuple")
        registrations[key] = registration
    if (
        type(value["receipt_keys"]) is not dict
        or not value["receipt_keys"]
        or any(type(pem) is not str for pem in value["receipt_keys"].values())
    ):
        raise ConfigError("nonempty receipt public PEM trust required")
    public = receipt_public_keys(value, as_keys=as_keys, registrations=registrations)
    _string(value["signing_kid"], "signing_kid")
    if value["signing_kid"] not in public:
        raise ConfigError("unknown receipt signing kid")
    return as_keys, registrations, public


def load_receipt_worker_config(path):
    """The same offline strict private loader serves both check and run."""
    try:
        path = Path(path)
        value = load_strict_json(read_private_file(path))
        if type(value) is not dict or set(value) != _FIELDS:
            raise ConfigError("exact receipt worker fields required")
        for name, (lower, upper, _) in BOUNDS.items():
            if type(value[name]) is not int or not lower <= value[name] <= upper:
                raise ConfigError("bounded exact integer receipt setting required")
        _, _, public = _trust(value)
        if type(value["private_key_path"]) is not str or not value["private_key_path"]:
            raise ConfigError("private signing path required")
        key_path = Path(value["private_key_path"])
        if not key_path.is_absolute():
            key_path = path.parent / key_path
        key = serialization.load_pem_private_key(read_private_file(key_path), password=None)
        if getattr(getattr(key, "curve", None), "name", None) != "SM2" or (
            serialize_sm2_public_key(key.public_key())
            != serialize_sm2_public_key(public[value["signing_kid"]])
        ):
            raise ConfigError("private signer does not match independent public trust")
        return ReceiptWorkerConfig(canonical_json_bytes(value), key)
    except (ValueError, TypeError, KeyError, UnicodeError, OSError) as exc:
        raise ConfigError("invalid or unsafe receipt worker configuration") from exc


def init_receipt_worker(gateway_path, out, *, signing_kid="gw-receipt-1"):
    """Create a new signer and public gateway copy without opening secrets."""
    gateway_path, out = Path(gateway_path), Path(out)
    original = load_gateway_config(read_private_file(gateway_path))
    public = load_strict_json(original.raw)
    _string(signing_kid, "signing_kid")
    if signing_kid in public.get("receipt_keys", {}):
        raise ConfigError("new signing kid must not replace existing public trust")
    secret = Path(public["secrets_path"])
    if not secret.is_absolute():
        secret = gateway_path.parent / secret
    # Validate ancestors before lexical normalization: '..' cannot erase a link.
    with private_directory(secret.parent):
        info = os.lstat(secret)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) not in (0o400, 0o600)
        ):
            raise ConfigError("unsafe downstream secret reference")
        public["secrets_path"] = os.path.abspath(secret)
    key = generate_sm2_private_key()
    public.setdefault("receipt_keys", {})[signing_kid] = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )
    load_gateway_config(canonical_json_bytes(public))
    config = {name: public[name] for name in ("issuer", "as_keys", "identities", "receipt_keys")}
    config.update(signing_kid=signing_kid, private_key_path="receipt-key.pem")
    config.update({name: default for name, (_, _, default) in BOUNDS.items()})
    _trust(config)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    with private_directory(out, create=True) as directory:
        directory.write_file("receipt-key.pem", pem)
        directory.write_file("config.json", canonical_json_bytes(config))
        directory.write_file("gateway-public.json", canonical_json_bytes(public))
