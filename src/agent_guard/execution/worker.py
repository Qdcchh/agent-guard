"""Real-process execution worker for the A2.1 core.

Run as ``python -m agent_guard.execution.worker``. All configuration comes from
environment variables; nothing that could be a credential (DSN, service secret)
is ever printed or logged. The worker drives exactly one operation through the
internal lifecycle — there is no HTTP endpoint and no management entry point.

Environment variables:

``AG_WORKER_GATEWAY_DSN``
    Gateway ledger database (test-only DSN; required).
``AG_WORKER_DOWNSTREAM_DSN``
    Independent downstream database (test-only DSN; required).
``AG_WORKER_SERVICE_SECRET``
    Independent downstream gateway service secret (required).
``AG_WORKER_APPROVED_SUPPLIERS`` / ``AG_WORKER_APPROVED_RECIPIENTS`` /
``AG_WORKER_SERVED_REQUESTS``
    Comma-separated downstream allow-lists; an empty value serves nothing
    (the downstream fails closed).
``AG_WORKER_OPERATION_ID``
    The operation to process (required).
``AG_WORKER_OWNER_TOKEN``
    Lease owner token; generated when absent.
``AG_WORKER_LEASE_TTL``
    Lease lifetime in seconds (default 30).
``AG_WORKER_MODE``
    ``run`` (default) or ``reconcile`` (query-only).
``AG_WORKER_SYNC_FILE`` / ``AG_WORKER_RELEASE_FILE``
    Optional synchronization pair used by the process-restart tests: when both
    are set the worker records its PID after the downstream call and waits for
    the release file before writing the terminal transaction. That is the crash
    window the tests kill a real process in; it is not a security switch.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid

from agent_guard.execution.service import ExecutionService, safe_reason
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.tools.catalog import TrustedCatalog
from agent_guard.tools.downstream import MockDownstream

DEFAULT_LEASE_TTL = 30
DEFAULT_PAUSE_WAIT_S = 60.0


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        # only the variable *name* is printed: never the value it holds
        print(f"worker config error: {name} is required", file=sys.stderr)
        raise SystemExit(2)
    return value


def _pause_hook(sync_file: str, release_file: str):
    def pause(claim, outcome) -> None:
        payload = {
            "pid": os.getpid(),
            "operation_id": claim.operation.operation_id,
            "previous_status": claim.previous_status,
            "lease_owner": claim.lease.owner_token,
            "fencing_version": claim.lease.fencing_version,
            "outcome_seen": outcome is not None,
        }
        with open(sync_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
        deadline = time.monotonic() + DEFAULT_PAUSE_WAIT_S
        while time.monotonic() < deadline:
            if os.path.exists(release_file):
                return
            time.sleep(0.05)
        raise TimeoutError("release file never appeared")

    return pause


def main() -> int:
    gateway_dsn = _require_env("AG_WORKER_GATEWAY_DSN")
    downstream_dsn = _require_env("AG_WORKER_DOWNSTREAM_DSN")
    secret = _require_env("AG_WORKER_SERVICE_SECRET")
    operation_id = _require_env("AG_WORKER_OPERATION_ID")

    def _allow(name: str) -> frozenset[str]:
        return frozenset(e for e in os.environ.get(name, "").split(",") if e)

    suppliers = _allow("AG_WORKER_APPROVED_SUPPLIERS")
    recipients = _allow("AG_WORKER_APPROVED_RECIPIENTS")
    served_requests = _allow("AG_WORKER_SERVED_REQUESTS")
    owner = os.environ.get("AG_WORKER_OWNER_TOKEN") or uuid.uuid4().hex
    try:
        ttl = int(os.environ.get("AG_WORKER_LEASE_TTL", str(DEFAULT_LEASE_TTL)))
    except ValueError:
        print("worker config error: AG_WORKER_LEASE_TTL must be an integer", file=sys.stderr)
        return 2
    mode = os.environ.get("AG_WORKER_MODE", "run")
    sync_file = os.environ.get("AG_WORKER_SYNC_FILE", "")
    release_file = os.environ.get("AG_WORKER_RELEASE_FILE", "")

    pause = _pause_hook(sync_file, release_file) if sync_file and release_file else None

    downstream = MockDownstream(
        downstream_dsn,
        service_secret=secret,
        approved_suppliers=suppliers,
        approved_recipients=recipients,
        served_requests=served_requests,
    )
    service = ExecutionService(
        gateway_dsn=gateway_dsn,
        ledger=ExecutionLedger(gateway_dsn),
        catalog=TrustedCatalog(),
        downstream=downstream,
        downstream_secret=secret,
        lease_ttl_seconds=ttl,
    )

    try:
        if mode == "reconcile":
            result = service.reconcile(operation_id, owner_token=owner, pause=pause)
        elif mode == "run":
            result = service.run_operation(operation_id, owner_token=owner, pause=pause)
        else:
            print(
                "worker config error: AG_WORKER_MODE must be 'run' or 'reconcile'", file=sys.stderr
            )
            return 2
    except Exception as exc:  # noqa: BLE001 - fail closed, never echo credentials
        # A stable code/class name only. The raw message may embed the DSN, the
        # service secret or request parameters, so it is deliberately dropped.
        print(f"worker failed: {safe_reason(exc)}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "operation_id": result.operation_id,
                "status": result.status,
                "previous_status": result.previous_status,
                "action": None if result.action is None else result.action.value,
                "downstream_called": result.downstream_called,
                "owner_token_prefix": result.lease.owner_token[:8] if result.lease else None,
                "fencing_version": result.lease.fencing_version if result.lease else None,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
