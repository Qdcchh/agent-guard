"""Explicit private configuration for the independent local audit service."""

from __future__ import annotations

import ipaddress
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from psycopg.conninfo import conninfo_to_dict
from tongsuopy.crypto import serialization

from agent_guard.audit.contracts import CheckpointTrust, exact_object, identifier
from agent_guard.contracts.encoding import b64url_decode


def validate_approved_listener(host: object, approved_listener_host: object) -> None:
    """Validate an explicit operator bind permission, independently of TLS/ACLs."""
    if type(host) is not str or type(approved_listener_host) is not str:
        raise ValueError("exact approved IPv4 listener required")
    try:
        address = ipaddress.IPv4Address(approved_listener_host)
    except ipaddress.AddressValueError as exc:
        raise ValueError("canonical approved IPv4 listener required") from exc
    if str(address) != approved_listener_host or host != approved_listener_host:
        raise ValueError("exact approved IPv4 listener required")
    if not any(
        address in ipaddress.IPv4Network(network)
        for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    ):
        raise ValueError("RFC1918 approved IPv4 listener required")


def private_bytes(path: Path) -> bytes:
    path = Path(path)
    info = path.lstat()
    parent = path.parent.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid()
        or parent.st_mode & 0o077
    ):
        raise ValueError("private owner-only regular configuration required")
    if info.st_size > 65536:
        raise ValueError("private configuration capacity")
    return path.read_bytes()


@dataclass(frozen=True)
class AuditConfig:
    dsn: str
    owner_role: str
    key_id: str
    private_key_path: Path
    tls_certificate: Path
    tls_private_key: Path
    host: str
    port: int
    external_pins: tuple[str, ...]
    external_trust: tuple[CheckpointTrust, ...]

    @classmethod
    def load(cls, path: Path, *, approved_listener_host: str | None = None):
        value = exact_object(
            private_bytes(path),
            {
                "dsn",
                "owner_role",
                "key_id",
                "private_key_path",
                "tls_certificate",
                "tls_private_key",
                "host",
                "port",
                "external_pins",
                "external_trust",
            },
        )
        if approved_listener_host is not None:
            validate_approved_listener(value["host"], approved_listener_host)
        elif value["host"] not in ("127.0.0.1", "::1"):
            raise ValueError("local fixed audit listener required")
        if type(value["port"]) is not int or not 1 <= value["port"] <= 65535:
            raise ValueError("local fixed audit listener required")
        dsn = conninfo_to_dict(value["dsn"])
        if (
            dsn.get("sslmode") != "verify-full"
            or not dsn.get("sslrootcert")
            or dsn.get("user") != value["owner_role"]
            or dsn.get("dbname") in (None, "postgres", "template0", "template1")
        ):
            raise ValueError("independent verified TLS audit connection required")
        identifier(value["owner_role"])
        identifier(value["key_id"], maximum=128)
        if type(value["external_pins"]) is not list or type(value["external_trust"]) is not list:
            raise ValueError("explicit external pin/trust lists required")
        trust = []
        for item in value["external_trust"]:
            if type(item) is not dict or set(item) != {
                "kid",
                "role",
                "spki_der",
                "first_sequence",
                "last_sequence",
            }:
                raise ValueError("invalid external trust descriptor")
            trust.append(CheckpointTrust(**{**item, "spki_der": b64url_decode(item["spki_der"])}))
        for name in ("private_key_path", "tls_certificate", "tls_private_key"):
            file = Path(value[name])
            if not file.is_absolute():
                raise ValueError("absolute private paths required")
            private_bytes(file)
            value[name] = file
        return cls(
            **{
                **value,
                "external_pins": tuple(value["external_pins"]),
                "external_trust": tuple(trust),
            }
        )

    def signing_key(self):
        key = serialization.load_pem_private_key(
            private_bytes(self.private_key_path), password=None
        )
        if key.curve.name != "SM2":
            raise ValueError("SM2 private signing key required")
        return key
