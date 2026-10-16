"""Explicit local maintenance bootstrap and public registration descriptor CLI."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import asdict

import psycopg

from agent_guard.audit.journal import (
    bootstrap_task_tx,
    describe_pending_tx,
    gateway_origin,
)
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.ledger.lineage import apply_bundle_migrations


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Local journal maintenance; stop and drain all writers before bootstrap"
    )
    parser.add_argument("action", choices=("migrate", "bootstrap", "describe-pending"))
    parser.add_argument("--tenant-id")
    parser.add_argument("--task-id")
    parser.add_argument("--writers-stopped-and-drained", action="store_true")
    args = parser.parse_args(argv)
    dsn = os.environ.get("AGENT_GUARD_DATABASE_URL")
    if not dsn:
        print("explicit local database configuration required", file=sys.stderr)
        return 2
    if args.action != "migrate" and (not args.tenant_id or not args.task_id):
        parser.error("tenant-id and task-id required")
    if args.action == "bootstrap" and not args.writers_stopped_and_drained:
        parser.error("maintenance requires stopped and drained writers")
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.execute("SET LOCAL lock_timeout='10s'")
            conn.execute("SET LOCAL statement_timeout='30s'")
            if args.action == "migrate":
                applied = apply_bundle_migrations(conn)
                output = {"applied": [list(item) for item in applied]}
            else:
                fn = bootstrap_task_tx if args.action == "bootstrap" else describe_pending_tx
                output = asdict(
                    fn(conn, scope_key=(gateway_origin(), args.tenant_id, args.task_id))
                )
        print(canonical_json_bytes(output).decode("ascii"))
        return 0
    except (psycopg.Error, ValueError):
        print("journal maintenance rejected", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
