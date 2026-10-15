"""Finite, local-only delivery command with externally pinned audit trust."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

import psycopg

from agent_guard.audit.client import AuditClient
from agent_guard.audit.contracts import CheckpointTrust
from agent_guard.audit.delivery import DeliveryWorker
from agent_guard.contracts.encoding import b64url_decode, canonical_json_bytes, load_strict_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="One finite delivery attempt per selected stream")
    parser.add_argument("--config", required=True)
    parser.add_argument("--stream-id", required=True, action="append")
    args = parser.parse_args(argv)
    try:
        path = Path(args.config)
        if (
            path.is_symlink()
            or stat.S_IMODE(path.stat().st_mode) != 0o600
            or stat.S_IMODE(path.parent.stat().st_mode) != 0o700
        ):
            raise ValueError("private configuration required")
        config = load_strict_json(path.read_bytes())
        if type(config) is not dict or set(config) != {
            "origin",
            "ca_file",
            "writer_credential",
            "reader_credential",
            "trust",
        }:
            raise ValueError("exact local configuration required")
        if type(config["trust"]) is not list or not config["trust"]:
            raise ValueError("external checkpoint trust required")
        for key in config["trust"]:
            if type(key) is not dict or set(key) != {
                "kid",
                "role",
                "spki_der",
                "first_sequence",
                "last_sequence",
            }:
                raise ValueError("exact external trust fields required")
        trust = tuple(
            CheckpointTrust(
                k["kid"],
                k["role"],
                b64url_decode(k["spki_der"]),
                k["first_sequence"],
                k["last_sequence"],
            )
            for k in config["trust"]
        )
        client = AuditClient(
            config["origin"],
            ca_file=config["ca_file"],
            writer_credential=config["writer_credential"],
            reader_credential=config["reader_credential"],
        )
        dsn = os.environ["AGENT_GUARD_DATABASE_URL"]

        def connect():
            conn = psycopg.connect(dsn, connect_timeout=5)
            conn.execute("SET lock_timeout='3s'")
            conn.execute("SET statement_timeout='30s'")
            conn.commit()
            return conn

        outcomes = DeliveryWorker(connect, client, trust=trust).deliver_round(tuple(args.stream_id))
        print(
            canonical_json_bytes(
                {"outcomes": [{"stream_id": o.stream_id, "status": o.status} for o in outcomes]}
            ).decode("ascii")
        )
        return 0 if all(o.status in ("ACKED", "NO_PENDING") for o in outcomes) else 1
    except (ValueError, OSError, KeyError, TypeError, psycopg.Error):
        print("audit delivery rejected", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
