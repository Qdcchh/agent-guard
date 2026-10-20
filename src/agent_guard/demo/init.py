"""Exclusive synthetic key tree; privileged UID assignment is explicit and finite."""

from __future__ import annotations

import hashlib
import os
import secrets
import subprocess
from pathlib import Path
from types import MappingProxyType

from tongsuopy.crypto import serialization

from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
from agent_guard.demo.config import (
    HOLDERS,
    PAIR_NAMES,
    PRIVATE_FILES,
    ROLES,
    VERSION,
    DemoConfigError,
    InitManifest,
    integer,
    run_uuid,
    safe_base,
    text,
)
from agent_guard.identity.resolver import METHOD_TYPE, SPKI_PROPERTY
from agent_guard.server.private_files import private_directory

HOSTS = {
    "as": "auth.agent-guard.test",
    "gateway": "gateway.agent-guard.test",
    "did": "identity.agent-guard.test",
    "audit": "audit.agent-guard.test",
}


def _pem(key):
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _public(key):
    return (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )


def _openssl(argv):
    result = subprocess.run(["openssl", *argv], capture_output=True, timeout=30, check=False)
    if result.returncode != 0:
        raise DemoConfigError("TLS initialization failed")


def _tls(root):
    operator = root / "operator"
    _openssl(
        [
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(operator / "ca-key.pem"),
            "-out",
            str(operator / "ca.pem"),
            "-days",
            "2",
            "-subj",
            "/CN=Agent Guard synthetic private CA",
        ]
    )
    for role, host in HOSTS.items():
        directory = root / role
        _openssl(
            [
                "req",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(directory / "tls-key.pem"),
                "-out",
                str(operator / (role + ".csr")),
                "-subj",
                "/CN=" + host,
            ]
        )
        ext = operator / (role + ".ext")
        ext.write_text("subjectAltName=DNS:" + host + "\nextendedKeyUsage=serverAuth\n")
        _openssl(
            [
                "x509",
                "-req",
                "-in",
                str(operator / (role + ".csr")),
                "-CA",
                str(operator / "ca.pem"),
                "-CAkey",
                str(operator / "ca-key.pem"),
                "-CAcreateserial",
                "-out",
                str(directory / "tls.pem"),
                "-days",
                "2",
                "-extfile",
                str(ext),
            ]
        )
    for directory in (root / role for role in ROLES):
        for file in directory.iterdir():
            file.chmod(0o600)


def init_run(out_dir: Path, *, run_id: str, owner_id: str, role_uids, handoff_gids) -> InitManifest:
    run_uuid(run_id)
    text(owner_id)
    out_dir = safe_base(out_dir)
    if set(role_uids) != ROLES or set(handoff_gids) != set(PAIR_NAMES):
        raise DemoConfigError("exact role UID/pair GID maps required")
    for uid in role_uids.values():
        integer(uid)
    for gid in handoff_gids.values():
        integer(gid)
    if (
        len(set(role_uids.values())) != len(ROLES)
        or len(set(handoff_gids.values())) != 2
        or set(role_uids.values()) & set(handoff_gids.values())
    ):
        raise DemoConfigError("distinct role UIDs and separate IPC groups required")
    if os.geteuid() != 0:
        raise DemoConfigError("short-lived privileged initialization required for role ownership")
    with private_directory(out_dir, create=True):
        for role in ROLES:
            with private_directory(out_dir / role, create=True):
                pass
    keys = {name: generate_sm2_private_key() for name in ("as", "publisher", "audit", *HOLDERS)}
    docs, identities = {}, {}
    client_secrets = {"agent-" + h: secrets.token_urlsafe(32) for h in HOLDERS}
    downstream_secret = secrets.token_urlsafe(32)
    export_secret = secrets.token_urlsafe(32)
    audit_registration = {
        "writer_id": "demo-publisher",
        "writer_secret": secrets.token_urlsafe(32),
        "reader_id": "demo-operator-reader",
        "reader_secret": secrets.token_urlsafe(32),
        "publisher_reader_id": "demo-publisher-reader",
        "publisher_reader_secret": secrets.token_urlsafe(32),
    }
    login = {
        "tenant_id": "tenant-demo",
        "subject": "user-demo",
        "password": secrets.token_urlsafe(32),
    }
    registry = []
    for holder in HOLDERS:
        did = "did:web:identity.agent-guard.test:agents:" + holder
        kid = did + "#key-1"
        spki = serialize_sm2_public_key(keys[holder].public_key())
        document = {
            "id": did,
            "verificationMethod": [
                {
                    "id": kid,
                    "type": METHOD_TYPE,
                    "controller": did,
                    SPKI_PROPERTY: b64url_encode(spki),
                }
            ],
            "authentication": [kid],
            "capabilityInvocation": [kid],
        }
        if holder != "executor":
            document["capabilityDelegation"] = [kid]
        url = f"https://identity.agent-guard.test/agents/{holder}/did.json"
        docs[url] = document
        identity = {
            "tenant_id": "tenant-demo",
            "client_id": "agent-" + holder,
            "did": did,
            "kid": kid,
            "spki_pem": _public(keys[holder]),
        }
        identities["agent-" + holder] = {k: v for k, v in identity.items() if k != "client_id"}
        registry.append(
            {
                **identity,
                "spki_der": b64url_encode(spki),
                "purposes": ["authentication", "capabilityInvocation"]
                + (["capabilityDelegation"] if holder != "executor" else []),
            }
        )
    public = {
        "version": VERSION,
        "run_id": run_id,
        "owner_id": owner_id,
        "issuer": "https://auth.agent-guard.test",
        "as_keys": {"as-sign-1": _public(keys["as"])},
        "receipt_keys": {"gw-receipt-1": _public(keys["publisher"])},
        "audit_keys": {"audit-sign-1": _public(keys["audit"])},
        "registrations": registry,
        "export_credentials": [
            {
                "credential_id": "demo-export",
                "credential_sha256": hashlib.sha256(export_secret.encode("ascii")).hexdigest(),
                "tenant_id": "tenant-demo",
                "task_ids": ["task-demo"],
            }
        ],
    }
    as_config = {
        "issuer": "https://auth.agent-guard.test",
        "as_signing_key_path": "signing-key.pem",
        "secrets_path": "secrets.json",
        "signing_kid": "as-sign-1",
        "clients": {
            "agent-" + h: {
                "tenant_id": "tenant-demo",
                "redirect_uri": f"https://console.agent-guard.test/oauth/{h}-callback",
            }
            for h in HOLDERS
        },
        "gateway_client_id": "gateway-introspect",
        "identities": identities,
        "identity_allowed_hosts": ["identity.agent-guard.test"],
        "did_documents": docs,
        "session_ttl_seconds": 1800,
        "csrf_ttl_seconds": 600,
        "request_ttl_seconds": 300,
        "request_timeout_seconds": 10,
    }
    catalog = {
        "requests": [
            {
                "request_id": "req-001",
                "tenant_id": "tenant-demo",
                "task_id": "task-demo",
                "status": "APPROVED",
            }
        ],
        "documents": [
            {
                "document_id": "doc-001",
                "request_id": "req-001",
                "body": "synthetic document",
            }
        ],
        "quotes": [
            {
                "quote_id": "quote-001",
                "quote_version": "1",
                "supplier_id": "supplier-001",
                "request_id": "req-001",
                "lines": [{"sku": "sku-001", "quantity": 1, "unit_price_fen": 70000}],
            }
        ],
        "deliveries": [
            {
                "delivery_id": "office-001",
                "tenant_id": "tenant-demo",
                "request_id": "req-001",
            }
        ],
        "templates": [{"template_id": "order-created", "body": "order-created"}],
        "recipients": [{"recipient_id": "user-demo"}],
    }
    gw_config = {
        "issuer": "https://auth.agent-guard.test",
        "as_keys": public["as_keys"],
        "receipt_keys": public["receipt_keys"],
        "identities": [{**v, "client_id": c, "current": True} for c, v in identities.items()],
        "identity_allowed_hosts": ["identity.agent-guard.test"],
        "did_documents": docs,
        "catalog": catalog,
        "secrets_path": "secrets.json",
        "request_timeout_seconds": 20,
        "max_workers": 8,
    }
    public["catalog"] = catalog
    from agent_guard.gateway.config import load_gateway_config
    from agent_guard.server.config import load_server_config

    load_server_config(canonical_json_bytes(as_config))
    load_gateway_config(canonical_json_bytes(gw_config))
    from agent_guard.gateway.receipt_config import BOUNDS

    publisher_config = {
        n: gw_config[n] for n in ("issuer", "as_keys", "identities", "receipt_keys")
    }
    publisher_config.update(signing_kid="gw-receipt-1", private_key_path="signing-key.pem")
    publisher_config.update({n: default for n, (_, _, default) in BOUNDS.items()})
    for name, key in keys.items():
        with private_directory(out_dir / name) as directory:
            directory.write_file("signing-key.pem", _pem(key))
    payloads = {
        "operator": {
            "approval-registry.json": {
                "run_id": run_id,
                "challenge": b64url_encode(secrets.token_bytes(32)),
                "registrations": registry,
            },
            "user-login.json": login,
            "audit-registration.json": audit_registration,
        },
        "as": {
            "config.json": as_config,
            "secrets.json": {
                "note": "synthetic test-only role secrets",
                "client_secrets": client_secrets,
                "gateway_secret": secrets.token_urlsafe(32),
            },
        },
        "gateway": {
            "config.json": gw_config,
            "secrets.json": {
                "note": "synthetic test-only independent downstream",
                "downstream_secret": downstream_secret,
            },
        },
        "did": {"config.json": {"version": VERSION, "run_id": run_id, "documents": docs}},
        "worker": {"config.json": gw_config},
        "publisher": {
            "publisher-config.json": publisher_config,
            "audit-delivery.json": {
                "writer_id": audit_registration["writer_id"],
                "writer_secret": audit_registration["writer_secret"],
                "reader_id": audit_registration["publisher_reader_id"],
                "reader_secret": audit_registration["publisher_reader_secret"],
            },
        },
        "audit": {},
        "export": {
            "export-credential.json": {
                "credential_id": "demo-export",
                "secret": export_secret,
            }
        },
        "offline": {},
        **{
            h: {
                "config.json": {
                    "client_id": "agent-" + h,
                    "kid": identities["agent-" + h]["kid"],
                    "redirect_uri": as_config["clients"]["agent-" + h]["redirect_uri"],
                }
            }
            for h in HOLDERS
        },
    }
    for role, files in payloads.items():
        with private_directory(out_dir / role) as directory:
            for name, value in files.items():
                directory.write_file(name, canonical_json_bytes(value))
            if role in HOLDERS:
                directory.write_file("basic-secret.txt", client_secrets["agent-" + role].encode())
            if role == "worker":
                directory.write_file("downstream-secret.txt", downstream_secret.encode())
            if role == "operator":
                directory.write_file("downstream-secret.txt", downstream_secret.encode())
    _tls(out_dir)
    # Pair directories are separate mounts; runtime holders never mount owner root.
    ipc = out_dir / "ipc"
    ipc.mkdir(mode=0o700)
    for pair in PAIR_NAMES:
        parent, receiver = pair.split("-")
        path = ipc / pair
        path.mkdir(mode=0o710)
        os.chown(path, role_uids[receiver], handoff_gids[pair])
        path.chmod(0o710)
    private_names = {
        "signing_key": "signing-key.pem",
        "basic_secret": "basic-secret.txt",
        "tls_key": "tls-key.pem",
        "ca_key": "ca-key.pem",
        "approval_registry": "approval-registry.json",
        "user_login": "user-login.json",
        "audit_registration": "audit-registration.json",
        "audit_delivery": "audit-delivery.json",
        "secrets": "secrets.json",
        "downstream_secret": "downstream-secret.txt",
        "authority_dsn": "authority-dsn.txt",
        "downstream_dsn": "downstream-dsn.txt",
        "audit_dsn": "audit-dsn.txt",
        "readonly_dsn": "readonly-dsn.txt",
        "export_credential": "export-credential.json",
        "audit_config": "audit-config.json",
        "publisher_config": "publisher-config.json",
    }
    roles = {}
    for role in ROLES:
        pairs = []
        for pair in PAIR_NAMES:
            parent, receiver = pair.split("-")
            if role not in (parent, receiver):
                continue
            peer = receiver if role == parent else parent
            pairs.append(
                {
                    "socket_path": str(ipc / pair / "child.sock"),
                    "self_uid": role_uids[role],
                    "peer_uid": role_uids[peer],
                    "self_client_id": "agent-" + role,
                    "peer_client_id": "agent-" + peer,
                    "run_id": run_id,
                    "task_id": "task-demo",
                    "pair_gid": handoff_gids[pair],
                    "receiver_uid": role_uids[receiver],
                }
            )
        roles[role] = {
            "version": VERSION,
            "run_id": run_id,
            "owner_id": owner_id,
            "role": role,
            "uid": role_uids[role],
            "gid": role_uids[role],
            "supplementary_gids": [p["pair_gid"] for p in pairs],
            "public_config_file": "config.json",
            "private_files": {k: private_names[k] for k in PRIVATE_FILES[role]},
            "handoff": pairs,
        }
        with private_directory(out_dir / role) as directory:
            directory.write_file("role.json", canonical_json_bytes(roles[role]))
            directory.write_file("public-trust.json", canonical_json_bytes(public))
            directory.write_file(
                "ca.pem", (out_dir / "operator" / "ca.pem").read_bytes()
            ) if role != "operator" else None
            if not (out_dir / role / "config.json").exists():
                directory.write_file(
                    "config.json",
                    canonical_json_bytes({"version": VERSION, "run_id": run_id, "role": role}),
                )
    run_config = {
        "version": VERSION,
        "run_id": run_id,
        "owner_id": owner_id,
        "scope": {
            "gateway_origin": "https://gateway.agent-guard.test",
            "tenant_id": "tenant-demo",
            "task_id": "task-demo",
        },
        "endpoints": {
            "issuer": "https://auth.agent-guard.test",
            "gateway_origin": "https://gateway.agent-guard.test",
            "audit_origin": "https://audit.agent-guard.test",
            "did_urls": {
                h: f"https://identity.agent-guard.test/agents/{h}/did.json" for h in HOLDERS
            },
        },
        "roles": roles,
        "public_manifest": "public-manifest.json",
        "approved_did_manifest": "approved-did-manifest.json",
        "resource_manifest": "resource-manifest.json",
    }
    with private_directory(out_dir) as directory:
        directory.write_file("run.json", canonical_json_bytes(run_config))
        directory.write_file("public-manifest.json", canonical_json_bytes(public))
        directory.write_file(
            "resource-manifest.json",
            canonical_json_bytes(
                {
                    "version": VERSION,
                    "run_id": run_id,
                    "owner_id": owner_id,
                    "status": "INITIALIZED_NOT_DEPLOYED",
                    "role_uids": dict(role_uids),
                    "handoff_gids": dict(handoff_gids),
                    "audit_listener_host": None,
                }
            ),
        )
    for name in ("run.json", "public-manifest.json", "resource-manifest.json"):
        (out_dir / name).chmod(0o444)
    hashes = {}
    for role in ROLES:
        directory = out_dir / role
        for file in directory.iterdir():
            hashes[str(file.relative_to(out_dir))] = hashlib.sha256(file.read_bytes()).hexdigest()
            os.chown(file, role_uids[role], role_uids[role])
            file.chmod(0o600)
        os.chown(directory, role_uids[role], role_uids[role])
        directory.chmod(0o700)
    return InitManifest(run_id, owner_id, out_dir, out_dir / "run.json", MappingProxyType(hashes))


def activate_runtime(config, *, role_dsns, audit_listener_host: str, resource_manifest):
    """Finite trusted init: create missing role DSNs and freeze allocated resources.

    Runs as short-lived root in the new owner tree before any normal process.
    DSNs are supplied only by the trusted owner provisioner, never by holders.
    No network discovery or inherited environment determines the audit address.
    """
    import stat

    from psycopg.conninfo import conninfo_to_dict

    from agent_guard.audit.config import validate_approved_listener
    from agent_guard.demo.config import DemoRunConfig, exact

    if type(config) is not DemoRunConfig or os.geteuid() != 0:
        raise DemoConfigError("short-lived privileged owned runtime activation required")
    validate_approved_listener(audit_listener_host, audit_listener_host)
    exact(
        resource_manifest,
        ("version", "run_id", "owner_id", "project", "roles", "databases", "networks"),
    )
    if (
        resource_manifest["version"],
        resource_manifest["run_id"],
        resource_manifest["owner_id"],
    ) != (VERSION, config.run_id, config.owner_id):
        raise DemoConfigError("resource ownership mismatch")
    exact(resource_manifest["roles"], ROLES)
    for name, role in config.roles.items():
        entry = resource_manifest["roles"][name]
        exact(entry, ("uid", "gid", "listener_host", "container_id"))
        if (entry["uid"], entry["gid"]) != (role.uid, role.gid) or (
            name == "audit" and entry["listener_host"] != audit_listener_host
        ):
            raise DemoConfigError("allocated resource role mismatch")
        if type(entry["container_id"]) is not str or not __import__("re").fullmatch(
            r"[0-9a-f]{64}", entry["container_id"]
        ):
            raise DemoConfigError("full resource container identity required")
    exact(resource_manifest["databases"], ("authority", "downstream", "audit"))
    if len(set(resource_manifest["databases"].values())) != 3:
        raise DemoConfigError("three independent database domains required")
    expected_roles = {
        r: {k for k in role.private_files if k.endswith("_dsn")} for r, role in config.roles.items()
    }
    if set(role_dsns) != {r for r, names in expected_roles.items() if names}:
        raise DemoConfigError("exact role connection map required")
    values = {}
    for name, connections in role_dsns.items():
        exact(connections, expected_roles[name])
        for key, dsn in connections.items():
            if type(dsn) is not str:
                raise DemoConfigError("private connection type")
            parsed = conninfo_to_dict(dsn)
            if (
                parsed.get("sslmode") != "verify-full"
                or not parsed.get("sslrootcert")
                or parsed.get("dbname") in (None, "postgres", "template0", "template1")
                or parsed.get("user")
                != (
                    "demo_gateway_export"
                    if name == "gateway" and key == "readonly_dsn"
                    else "demo_" + name.replace("-", "_")
                )
            ):
                raise DemoConfigError("exact role-specific verified TLS connection required")
            domain = (
                "authority"
                if key in ("authority_dsn", "readonly_dsn")
                else "downstream"
                if key == "downstream_dsn"
                else "audit"
            )
            if parsed.get("host") != resource_manifest["databases"][domain]:
                raise DemoConfigError("role database domain mismatch")
            values[config.roles[name].private_files[key]] = (
                dsn.encode(),
                config.roles[name],
            )
    audit = config.roles["audit"]
    audit_dsn = role_dsns["audit"]["audit_dsn"]
    audit_config = {
        "dsn": audit_dsn,
        "owner_role": "demo_audit",
        "key_id": "audit-sign-1",
        "private_key_path": str(audit.private_files["signing_key"]),
        "tls_certificate": str(audit.public_config_file.parent / "tls.pem"),
        "tls_private_key": str(audit.private_files["tls_key"]),
        "host": audit_listener_host,
        "port": 443,
        "external_pins": [],
        "external_trust": [],
    }
    values[audit.private_files["audit_config"]] = (
        canonical_json_bytes(audit_config),
        audit,
    )
    # Validate the entire plan before creating anything; activation is exclusive.
    for path, (_, role) in values.items():
        info = path.parent.lstat()
        if (
            path.parent.is_symlink()
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != role.uid
            or stat.S_IMODE(info.st_mode) != 0o700
            or path.exists()
            or path.is_symlink()
        ):
            raise DemoConfigError("activation target unsafe or already initialized")
    activated = config.base_dir / "allocated-resources.json"
    if activated.exists() or activated.is_symlink():
        raise DemoConfigError("runtime resources already frozen")
    for path, (raw, role) in values.items():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.fchown(fd, role.uid, role.gid)
            os.fchmod(fd, 0o600)
            data = memoryview(raw)
            while data:
                count = os.write(fd, data)
                if count <= 0:
                    raise DemoConfigError("activation persistence failed")
                data = data[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
    with private_directory(config.base_dir) as directory:
        directory.write_file("allocated-resources.json", canonical_json_bytes(resource_manifest))
    activated.chmod(0o444)
    return activated
