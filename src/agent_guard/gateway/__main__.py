"""Explicit synthetic public-trust init, offline check, and mandatory TLS run."""

import argparse
import os
import secrets
import sys
from pathlib import Path

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
from agent_guard.gateway.config import load_gateway_config, load_gateway_secrets
from agent_guard.gateway.factory import build_app
from agent_guard.server.__main__ import _did_document, _public_pem
from agent_guard.server.config import ConfigError
from agent_guard.server.private_files import private_directory, read_private_file


def init_config(out: Path):
    # Synthetic discarded signing keys are used only to make a valid public
    # example. Gateway init stores no AS or agent private keys, creates no DB.
    as_key = generate_sm2_private_key()
    agent = generate_sm2_private_key()
    did = "did:web:identity.agent-guard.test:agents:executor"
    kid = did + "#key-1"
    config = {
        "issuer": "https://auth.agent-guard.test",
        "as_keys": {"as-sign-1": _public_pem(as_key)},
        "identities": [
            {
                "tenant_id": "tenant-demo",
                "client_id": "agent-executor",
                "did": did,
                "kid": kid,
                "spki_pem": _public_pem(agent),
                "current": True,
            }
        ],
        "identity_allowed_hosts": ["identity.agent-guard.test"],
        "did_documents": {
            "https://identity.agent-guard.test/agents/executor/did.json": _did_document(
                did, kid, serialize_sm2_public_key(agent.public_key()), delegating=False
            )
        },
        "catalog": {
            n: []
            for n in ("requests", "documents", "quotes", "deliveries", "templates", "recipients")
        },
        "secrets_path": "secrets.json",
        "request_timeout_seconds": 20,
        "max_workers": 8,
    }
    load_gateway_config(canonical_json_bytes(config))
    with private_directory(out, create=True) as directory:
        directory.write_file("config.json", canonical_json_bytes(config))
        directory.write_file(
            "secrets.json",
            canonical_json_bytes(
                {
                    "note": "synthetic test-only; replace trust and secret before use",
                    "downstream_secret": secrets.token_urlsafe(32),
                }
            ),
        )
    print(
        "wrote synthetic gateway public trust and private downstream secret; configure approved "
        "trust and catalog before use"
    )


def _load(path):
    config_path = Path(path)
    config = load_gateway_config(read_private_file(config_path))
    secret_path = Path(load_strict_json(config.raw)["secrets_path"])
    if not secret_path.is_absolute():
        secret_path = config_path.parent / secret_path
    return config, load_gateway_secrets(read_private_file(secret_path))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agent_guard.gateway")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--out", required=True)
    check = sub.add_parser("check")
    check.add_argument("--config", required=True)
    run = sub.add_parser("run")
    run.add_argument("--config", required=True)
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=8444)
    run.add_argument("--ssl-certfile", required=True)
    run.add_argument("--ssl-keyfile", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            init_config(Path(args.out))
            return 0
        config, secret = _load(args.config)
        if args.command == "check":
            build_app(
                config,
                secret,
                gateway_dsn="offline-gateway-check",
                downstream_dsn="offline-downstream-check",
            )
            print("gateway config ok (offline)")
            return 0
        gateway_dsn = os.environ.get("AG_GATEWAY_DATABASE_URL")
        downstream_dsn = os.environ.get("AG_GATEWAY_DOWNSTREAM_DATABASE_URL")
        if not gateway_dsn or not downstream_dsn:
            raise ConfigError("explicit gateway/downstream database environment required")
        app = build_app(config, secret, gateway_dsn=gateway_dsn, downstream_dsn=downstream_dsn)
        import uvicorn

        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            ssl_certfile=args.ssl_certfile,
            ssl_keyfile=args.ssl_keyfile,
            access_log=False,
            log_level="critical",
            proxy_headers=False,
        )
        return 0
    except (OSError, ValueError, TypeError):
        print("error: invalid or unsafe gateway configuration/TLS startup", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
