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


def init_config(
    out: Path,
    *,
    export_credential_id=None,
    export_tenant_id=None,
    export_task_ids=None,
    evidence_local_inputs=None,
):
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
            for n in (
                "requests",
                "documents",
                "quotes",
                "deliveries",
                "templates",
                "recipients",
            )
        },
        "secrets_path": "secrets.json",
        "request_timeout_seconds": 20,
        "max_workers": 8,
    }
    export_secret = None
    if export_credential_id is not None:
        from agent_guard.server.config import secret_sha256

        export_secret = secrets.token_urlsafe(32)
        config["export_credentials"] = [
            {
                "credential_id": export_credential_id,
                "credential_sha256": secret_sha256(export_secret).hex(),
                "tenant_id": export_tenant_id,
                "task_ids": export_task_ids,
            }
        ]
        config["evidence_local_inputs"] = evidence_local_inputs
    load_gateway_config(canonical_json_bytes(config))
    with private_directory(out, create=True) as directory:
        directory.write_file("config.json", canonical_json_bytes(config))
        if export_secret is not None:
            directory.write_file(
                "export-credential.json",
                canonical_json_bytes(
                    {
                        "credential_id": export_credential_id,
                        "secret": export_secret,
                        "note": "independent synthetic export credential; protect this file",
                    }
                ),
            )
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
    init.add_argument("--export-credential-id")
    init.add_argument("--export-tenant-id")
    init.add_argument("--export-task-id", action="append")
    init.add_argument("--evidence-trust-file")
    init.add_argument("--evidence-pin-file")
    init.add_argument("--evidence-history-file")
    check = sub.add_parser("check")
    check.add_argument("--config", required=True)
    run = sub.add_parser("run")
    run.add_argument("--config", required=True)
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=8444)
    run.add_argument("--ssl-certfile", required=True)
    run.add_argument("--ssl-keyfile", required=True)
    run.add_argument("--export-spool-parent")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            options = (
                args.export_credential_id,
                args.export_tenant_id,
                args.export_task_id,
                args.evidence_trust_file,
                args.evidence_pin_file,
                args.evidence_history_file,
            )
            if any(v is not None for v in options) and any(v is None for v in options):
                raise ConfigError("all independent export initialization arguments required")
            inputs = (
                None
                if not any(v is not None for v in options)
                else {
                    "trust_file": args.evidence_trust_file,
                    "external_pin_file": args.evidence_pin_file,
                    "external_checkpoint_history_file": args.evidence_history_file,
                }
            )
            init_config(
                Path(args.out),
                export_credential_id=args.export_credential_id,
                export_tenant_id=args.export_tenant_id,
                export_task_ids=args.export_task_id,
                evidence_local_inputs=inputs,
            )
            return 0
        config, secret = _load(args.config)
        if args.command == "check":
            print("gateway config ok (offline)")
            return 0
        gateway_dsn = os.environ.get("AG_GATEWAY_DATABASE_URL")
        downstream_dsn = os.environ.get("AG_GATEWAY_DOWNSTREAM_DATABASE_URL")
        if not gateway_dsn or not downstream_dsn:
            raise ConfigError("explicit gateway/downstream database environment required")
        export_dsn = os.environ.get("AG_GATEWAY_EXPORT_DATABASE_URL")
        export_configured = "export_credentials" in load_strict_json(config.raw)
        if export_configured != bool(export_dsn and args.export_spool_parent):
            raise ConfigError("explicit independent export database and spool required")
        if not export_configured and (export_dsn or args.export_spool_parent):
            raise ConfigError("export resources require registration")
        export_factory = None
        if export_configured:
            import psycopg

            if export_dsn in (gateway_dsn, downstream_dsn):
                raise ConfigError("independent SELECT-only export database credentials required")

            def export_factory():
                return psycopg.connect(export_dsn, connect_timeout=5)

        app = build_app(
            config,
            secret,
            gateway_dsn=gateway_dsn,
            downstream_dsn=downstream_dsn,
            export_connection_factory=export_factory,
            export_spool_parent=args.export_spool_parent,
        )
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
        print(
            "error: invalid or unsafe gateway configuration/TLS startup",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
