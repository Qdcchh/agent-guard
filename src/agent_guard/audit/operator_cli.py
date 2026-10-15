"""Explicit local-only operator initialization and immutable registrations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

from agent_guard.audit.config import private_bytes
from agent_guard.audit.contracts import (
    CheckpointTrust,
    JournalScope,
    RegistrationDescriptor,
    exact_object,
)
from agent_guard.audit.migrate import apply_migrations, require_domain
from agent_guard.audit.store import register_key, register_principal, register_stream
from agent_guard.contracts.encoding import b64url_decode


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local independent audit operator")
    parser.add_argument(
        "action", choices=("init", "register-stream", "register-key", "register-principal", "check")
    )
    parser.add_argument("--connection", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    args = parser.parse_args(argv)
    try:
        connection = exact_object(private_bytes(args.connection), {"dsn", "owner_role"})
        from psycopg.conninfo import conninfo_to_dict

        info = conninfo_to_dict(connection["dsn"])
        if (
            info.get("sslmode") != "verify-full"
            or not info.get("sslrootcert")
            or info.get("user") != connection["owner_role"]
        ):
            raise ValueError("verified audit database TLS required")
        with psycopg.connect(connection["dsn"], connect_timeout=5) as conn:
            if args.action == "init":
                apply_migrations(conn, owner_role=connection["owner_role"])
            else:
                require_domain(conn, owner_role=connection["owner_role"])
                if args.action != "check" and args.input is None:
                    raise ValueError("private operator input required")
                if args.action == "register-stream":
                    value = exact_object(
                        private_bytes(args.input),
                        {
                            "scope",
                            "genesis_digest",
                            "bootstrap_digest",
                            "boundary",
                            "index_root",
                            "object_count",
                            "chunk_count",
                            "wire_bytes",
                        },
                        maximum=32768,
                    )
                    value["scope"] = JournalScope(**value["scope"])
                    register_stream(conn, RegistrationDescriptor(**value))
                elif args.action == "register-key":
                    value = exact_object(
                        private_bytes(args.input),
                        {"kid", "role", "spki_der", "first_sequence", "last_sequence"},
                    )
                    value["spki_der"] = b64url_decode(value["spki_der"])
                    register_key(conn, CheckpointTrust(**value))
                elif args.action == "register-principal":
                    value = exact_object(
                        private_bytes(args.input),
                        {"credential_id", "credential", "role", "stream_id"},
                    )
                    register_principal(conn, **value)
    except Exception:
        print("audit operator rejected configuration, domain or registration", file=sys.stderr)
        return 1
    print("audit operator completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
