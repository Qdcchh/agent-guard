"""Explicit init/check and internal bounded continuous receipt publisher CLI."""

import argparse
import json
import os
import sys
import time

from agent_guard.authorization.evidence_store import EvidenceError
from agent_guard.contracts.encoding import load_strict_json
from agent_guard.contracts.ledger import LedgerError
from agent_guard.gateway.receipt_config import init_receipt_worker, load_receipt_worker_config


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "error: invalid receipt worker arguments\n")


def publication_json(publication):
    return {
        "operation_id": publication.operation_id,
        "receipt_id": publication.receipt_id,
        "receipt_status": publication.receipt_status,
        "receipt_jws": publication.receipt_jws,
        "signed_at": publication.signed_at.isoformat() if publication.signed_at else None,
    }


def run(config, dsn, *, once=False, operation_id=None):
    publisher = config.publisher(dsn)
    settings = load_strict_json(config.raw)
    if operation_id is not None:
        print(json.dumps(publication_json(publisher.publish(operation_id))), flush=True)
        return
    cursor = ""
    while True:
        # Every selected row advances the cursor, including unusable materials.
        # Wrap only after reaching the end; a corrupt first row cannot starve
        # later legal PENDING rows, even with a page size of one.
        rows = publisher.pending_page(after_operation_id=cursor, limit=settings["batch_size"])
        for operation in rows:
            cursor = operation
            try:
                publisher.publish(operation)
            except (EvidenceError, LedgerError, ValueError, TypeError, KeyError):
                print("receipt publication deferred", file=sys.stderr, flush=True)
        if once:
            return
        if not rows:
            cursor = ""
        time.sleep(settings["poll_interval_ms"] / 1000)


def main(argv=None):
    parser = _Parser(prog="agent_guard.gateway.receipt_worker")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--gateway-config", required=True)
    init.add_argument("--out", required=True)
    init.add_argument("--signing-kid", "--kid", default="gw-receipt-1")
    check = sub.add_parser("check")
    check.add_argument("--config", required=True)
    start = sub.add_parser("run")
    start.add_argument("--config", required=True)
    start.add_argument("--once", action="store_true")
    start.add_argument("--operation-id")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            init_receipt_worker(args.gateway_config, args.out, signing_kid=args.signing_kid)
            print("created private receipt signer and gateway public copy")
            return 0
        config = load_receipt_worker_config(args.config)
        if args.command == "check":
            config.publisher("offline-receipt-check")
            print("receipt worker config ok (offline)")
            return 0
        dsn = os.environ.get("AG_RECEIPT_DATABASE_URL")
        if not dsn:
            raise ValueError("explicit receipt database required")
        run(config, dsn, once=args.once, operation_id=args.operation_id)
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, TypeError, KeyError, LedgerError):
        print("error: invalid configuration or receipt publication unavailable", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
