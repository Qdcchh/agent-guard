"""AS/OP server CLI: development initialization and TLS startup.

``init`` writes a synthetic test-only configuration tree (AS key, agent keys,
DID documents and generated secrets) into a private directory; it never prints
or commits secrets. ``run`` refuses to start without TLS certificates and a
database DSN. This is a development boundary, not a production deployment.
"""

from __future__ import annotations

import argparse
import os
import secrets as pysecrets
import sys
from pathlib import Path

from tongsuopy.crypto import serialization

from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
from agent_guard.identity.resolver import METHOD_TYPE, SPKI_PROPERTY
from agent_guard.server.config import ConfigError, load_secrets, load_server_config, resolve_paths
from agent_guard.server.factory import build_app
from agent_guard.server.private_files import read_private_file, write_private_file

TEST_ONLY_NOTE = (
    "synthetic init-generated test-only secrets; replace with deployment-generated "
    "secrets before any real use; never commit this file"
)
_AGENTS = ("planner", "selector", "executor")
_DID_PREFIX = "did:web:identity.agent-guard.test:agents:"


def _public_pem(key) -> str:
    return (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )


def _write_private_key(key, path: Path) -> None:
    write_private_file(
        path,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


def _did_document(did: str, kid: str, spki: bytes, *, delegating: bool) -> dict:
    document = {
        "id": did,
        "verificationMethod": [
            {"id": kid, "type": METHOD_TYPE, "controller": did, SPKI_PROPERTY: b64url_encode(spki)}
        ],
        "authentication": [kid],
        "capabilityInvocation": [kid],
    }
    if delegating:
        document["capabilityDelegation"] = [kid]
    return document


def init_config(out_dir: Path, issuer: str) -> None:
    if (
        out_dir.is_symlink()
        or out_dir.exists()
        or any(parent.is_symlink() for parent in out_dir.absolute().parents)
    ):
        print(f"error: refusing to write into existing directory {out_dir}")
        raise SystemExit(2)
    try:
        out_dir.mkdir(mode=0o700)
        if os.name != "nt":
            out_dir.chmod(0o700)
    except OSError as exc:
        print(f"error: cannot create private directory {out_dir}: {exc}")
        raise SystemExit(2) from None

    as_key = generate_sm2_private_key()
    _write_private_key(as_key, out_dir / "as-sign-key.pem")

    documents: dict[str, dict] = {}
    identities: dict[str, dict] = {}
    for name in _AGENTS:
        key = generate_sm2_private_key()
        did = _DID_PREFIX + name
        kid = did + "#key-1"
        spki = serialize_sm2_public_key(key.public_key())
        _write_private_key(key, out_dir / f"agent-{name}.pem")
        documents[f"https://identity.agent-guard.test/agents/{name}/did.json"] = _did_document(
            did, kid, spki, delegating=name in ("planner", "selector")
        )
        identities[f"agent-{name}"] = {
            "tenant_id": "tenant-demo",
            "did": did,
            "kid": kid,
            "spki_pem": _public_pem(key),
        }

    config: dict = {
        "issuer": issuer.rstrip("/"),
        "as_signing_key_path": "as-sign-key.pem",
        "secrets_path": "secrets.json",
        "signing_kid": "as-sign-1",
        "clients": {
            f"agent-{name}": {
                "tenant_id": "tenant-demo",
                "redirect_uri": f"https://console.agent-guard.test/oauth/{name}-callback",
            }
            for name in _AGENTS
        },
        "gateway_client_id": "gateway-introspect",
        "identities": identities,
        "identity_allowed_hosts": ["identity.agent-guard.test"],
        "did_documents": documents,
        "session_ttl_seconds": 1800,
        "csrf_ttl_seconds": 600,
        "request_ttl_seconds": 300,
        "request_timeout_seconds": 10,
    }
    secrets_doc = {
        "note": TEST_ONLY_NOTE,
        "client_secrets": {f"agent-{name}": pysecrets.token_urlsafe(32) for name in _AGENTS},
        "gateway_secret": pysecrets.token_urlsafe(32),
    }
    write_private_file(out_dir / "config.json", canonical_json_bytes(config))
    write_private_file(out_dir / "secrets.json", canonical_json_bytes(secrets_doc))
    print(f"wrote dev config tree under {out_dir} (contains private keys and secrets)")
    print("test-only: replace secrets and keys before any real deployment")


def run_server(args: argparse.Namespace) -> None:
    config_path = Path(args.config)
    try:
        config = load_server_config(read_private_file(config_path))
        config = resolve_paths(config, config_path.parent)
        secrets = load_secrets(read_private_file(config.secrets_path))
    except (ConfigError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        raise SystemExit(2) from None
    dsn = os.environ.get("AGENT_GUARD_DATABASE_URL")
    if not dsn:
        print("error: AGENT_GUARD_DATABASE_URL is required; refusing to guess a database")
        raise SystemExit(2)
    if not args.ssl_certfile or not args.ssl_keyfile:
        print("error: --ssl-certfile and --ssl-keyfile are required (TLS is mandatory)")
        raise SystemExit(2)
    try:
        app = build_app(config, secrets, dsn=dsn)
    except ConfigError as exc:
        print(f"error: {exc}")
        raise SystemExit(2) from None
    import uvicorn

    print(f"starting dev AS on https://{args.host}:{args.port} (development boundary only)")
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        ssl_certfile=args.ssl_certfile,
        ssl_keyfile=args.ssl_keyfile,
        log_level="warning",
        access_log=False,
        proxy_headers=False,
    )


def check_config(args: argparse.Namespace) -> None:
    config_path = Path(args.config)
    try:
        config = load_server_config(read_private_file(config_path))
        config = resolve_paths(config, config_path.parent)
        read_private_file(config.as_signing_key_path)
        load_secrets(read_private_file(config.secrets_path))
    except (ConfigError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        raise SystemExit(2) from None
    print("config ok")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent_guard.server", description="AS/OP dev server")
    sub = parser.add_subparsers(dest="command", required=True)
    init_parser = sub.add_parser("init", help="write a synthetic test-only dev config tree")
    init_parser.add_argument("--out", required=True, help="output directory (created)")
    init_parser.add_argument("--issuer", default="https://auth.agent-guard.test")
    init_parser.set_defaults(func=lambda a: init_config(Path(a.out), a.issuer))

    run_parser = sub.add_parser("run", help="run the AS over TLS (development boundary)")
    run_parser.add_argument("--config", required=True, help="path to config.json")
    run_parser.add_argument("--host", default="127.0.0.1")
    run_parser.add_argument("--port", type=int, default=8443)
    run_parser.add_argument("--ssl-certfile", default=None)
    run_parser.add_argument("--ssl-keyfile", default=None)
    run_parser.set_defaults(func=run_server)

    check_parser = sub.add_parser("check", help="validate config and secrets without starting")
    check_parser.add_argument("--config", required=True)
    check_parser.set_defaults(func=check_config)

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
