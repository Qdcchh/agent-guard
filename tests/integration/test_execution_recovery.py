"""A2.1 recovery, leases and real process restart: P04, P06, P09, P10, OBL04.

The process-restart cases launch a *real* ``python -m agent_guard.execution.worker``
subprocess and deliver a real ``SIGKILL`` inside the documented crash window.
They are never simulated with an exception inside the test process. Lease
expiry is a real database time condition; tests move ``lease_expires_at`` into
the past instead of sleeping for the TTL, which is deterministic and never a
"sleep and hope" race.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import psycopg
import pytest

from agent_guard.contracts.execution import (
    ExecutionError,
    ExecutionErrorCode,
    OperationStatus,
    TerminalAction,
)
from agent_guard.contracts.ledger import ErrorCode, LedgerError
from agent_guard.execution import store as exec_store
from tests.fixtures.dbstate import fetch_all, fetch_counters, fetch_counts, fetch_one
from tests.fixtures.execution import (
    ORDER_AMOUNT_FEN,
    RECIPIENT_ID,
    REQUEST_ID,
    SUPPLIER_ID,
    build_env,
    expire_lease,
    order_params,
)

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUNDS = 10


# --------------------------------------------------------------- process IO


def _worker_env(a2, operation_id: str, **extra: str) -> dict[str, str]:
    """A minimal environment: nothing inherited that could carry a DSN or key."""
    env = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
        if key in os.environ
    }
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["AG_WORKER_GATEWAY_DSN"] = a2.gateway_dsn
    env["AG_WORKER_DOWNSTREAM_DSN"] = a2.downstream_dsn
    env["AG_WORKER_SERVICE_SECRET"] = a2.secret
    env["AG_WORKER_OPERATION_ID"] = operation_id
    env["AG_WORKER_APPROVED_SUPPLIERS"] = SUPPLIER_ID
    env["AG_WORKER_APPROVED_RECIPIENTS"] = RECIPIENT_ID
    env["AG_WORKER_SERVED_REQUESTS"] = REQUEST_ID
    env.update(extra)
    return env


def start_worker(a2, operation_id: str, **extra: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "agent_guard.execution.worker"],
        cwd=str(REPO_ROOT),
        env=_worker_env(a2, operation_id, **extra),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_for_file(path: Path, *, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return json.loads(path.read_text(encoding="utf-8"))
        time.sleep(0.02)
    raise AssertionError(f"sync file never appeared: {path}")


class NoneThenRealPort:
    """Port double: reports 'nothing known' for the first ``misses`` queries.

    A layered double at the ``DownstreamPort`` boundary; it is not a real
    network outage and is never reported as one.
    """

    def __init__(self, inner, misses: int = 1):
        self.inner = inner
        self.misses = misses
        self.queries = 0

    def execute(self, **kwargs):
        return self.inner.execute(**kwargs)

    def query(self, **kwargs):
        self.queries += 1
        if self.queries <= self.misses:
            return None
        return self.inner.query(**kwargs)


def make_env(a2, **tree_kwargs):
    """A second, purpose-built tree plus its own wired service (same databases)."""
    from tests.fixtures.state import build_tree

    with psycopg.connect(a2.gateway_dsn) as conn:
        tree = build_tree(conn, **tree_kwargs)
    return build_env(tree=tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)


def order_count(a2) -> int:
    with psycopg.connect(a2.downstream_dsn) as conn:
        return conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0]


def operation_count(a2) -> int:
    with psycopg.connect(a2.downstream_dsn) as conn:
        return conn.execute("SELECT count(*) FROM ds_operations").fetchone()[0]


# ------------------------------------------------------------------- P04


def test_p04_accept_alone_never_touches_the_downstream(a2):
    """P04: nothing may execute before the accept transaction has committed."""
    inv = a2.tree.invocation(
        idempotency_key="p04-no-exec",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    assert accepted.status == "RESERVED"
    assert order_count(a2) == 0
    assert operation_count(a2) == 0
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 0


def test_p04_rejected_accept_leaves_no_operation_and_no_effect(a2):
    """P04: a rejected accept reserves nothing and executes nothing."""
    inv = a2.tree.invocation(
        idempotency_key="p04-rejected",
        tool_id="procurement.order.create",
        params=order_params(items=(("sku-001", 1), ("sku-999", 1))),
    )
    with pytest.raises(ExecutionError) as excinfo:
        a2.service.accept_invocation(inv, a2.permission())
    assert excinfo.value.code in (
        ExecutionErrorCode.QUOTE_INVALID,
        ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
        ExecutionErrorCode.RESOURCE_NOT_FOUND,
    )
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 0
    assert order_count(a2) == 0
    for grant_id in (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id):
        counters = fetch_counters(a2.gateway_dsn, grant_id)
        assert counters["amount_reserved"] == 0
        assert counters["calls_reserved"] == 0


def test_p04_real_process_never_started_is_recovered_by_a_new_process(a2, tmp_path):
    """P04: after commit, a worker that never started is recovered by a new one."""
    inv = a2.tree.invocation(
        idempotency_key="p04-never-started",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    assert a2.service.operation_status(accepted.operation_id) == "RESERVED"
    assert order_count(a2) == 0

    proc = start_worker(a2, accepted.operation_id, AG_WORKER_OWNER_TOKEN="worker-p04-new")
    out, err = proc.communicate(timeout=60)
    assert proc.returncode == 0, err
    payload = json.loads(out.strip().splitlines()[-1])
    assert payload["status"] == "SUCCEEDED"
    assert payload["action"] == "SETTLE"
    assert payload["previous_status"] == "RESERVED"

    assert a2.service.operation_status(accepted.operation_id) == "SUCCEEDED"
    assert order_count(a2) == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 2
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 1
    counters = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    assert counters == {
        "amount_reserved": 0,
        "amount_settled": ORDER_AMOUNT_FEN,
        "calls_reserved": 0,
        "calls_settled": 1,
    }


def test_p04_p06_real_process_killed_in_crash_window_then_restarted(a2, tmp_path):
    """P04/P06: a real worker process is SIGKILLed after the downstream commit
    and before the terminal transaction; a brand new process recovers from the
    persistent state with no duplicate effect, ledger change or receipt."""
    inv = a2.tree.invocation(
        idempotency_key="p04-kill-window",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    sync_file = tmp_path / "sync.json"
    release_file = tmp_path / "release.json"
    proc = start_worker(
        a2,
        accepted.operation_id,
        AG_WORKER_OWNER_TOKEN="worker-p04-killed",
        AG_WORKER_SYNC_FILE=str(sync_file),
        AG_WORKER_RELEASE_FILE=str(release_file),
    )
    try:
        observed = wait_for_file(sync_file)
        pid = observed["pid"]
        assert pid == proc.pid
        assert observed["outcome_seen"] is True  # the downstream really committed
        assert observed["fencing_version"] == 1
    finally:
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=30)

    # the killed process left the crash window exactly as designed
    assert a2.service.operation_status(accepted.operation_id) == OperationStatus.EXECUTING.value
    assert order_count(a2) == 1
    assert operation_count(a2) == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 1  # RESERVE only
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 0
    counters = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    assert counters["amount_reserved"] == ORDER_AMOUNT_FEN
    assert counters["amount_settled"] == 0

    # a genuinely new process recovers from the persistent state
    expire_lease(a2.gateway_dsn, accepted.operation_id)
    recovered = start_worker(a2, accepted.operation_id, AG_WORKER_OWNER_TOKEN="worker-p04-restart")
    out, err = recovered.communicate(timeout=60)
    assert recovered.returncode == 0, err
    payload = json.loads(out.strip().splitlines()[-1])
    assert payload["status"] == "SUCCEEDED"
    assert payload["previous_status"] == "EXECUTING"

    assert a2.service.operation_status(accepted.operation_id) == "SUCCEEDED"
    assert order_count(a2) == 1  # no second order
    assert operation_count(a2) == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 2  # RESERVE + SETTLE
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_event_nodes"] == 6
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 1
    for grant_id in (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id):
        counters = fetch_counters(a2.gateway_dsn, grant_id)
        assert counters == {
            "amount_reserved": 0,
            "amount_settled": ORDER_AMOUNT_FEN,
            "calls_reserved": 0,
            "calls_settled": 1,
        }
    # the first process is really gone
    assert proc.poll() is not None


# ------------------------------------------------------------------- P09


def test_p09_two_recoverers_race_one_terminal_and_one_outbox(a2):
    """P09: two independent recoverers over independent connections, 10 rounds.

    Exactly one reaches the terminal transaction; the other is refused. Every
    round ends with one terminal event, one outbox row and one downstream
    effect.
    """
    totals = {"terminal": 0, "refused": 0}
    for round_no in range(ROUNDS):
        key = f"p09-race-{round_no}"
        env = make_env(
            a2,
            root_limit=10_000_000,
            mid_limit=10_000_000,
            leaf_limit=10_000_000,
            root_calls=1000,
            mid_calls=1000,
            leaf_calls=1000,
        )
        inv = env.tree.invocation(
            idempotency_key=key, tool_id="procurement.order.create", params=order_params()
        )
        accepted = env.service.accept_invocation(inv, env.permission())
        barrier = threading.Barrier(2)
        results: list[object] = []
        lock = threading.Lock()

        def worker(
            owner: str,
            _op: str = accepted.operation_id,
            _barrier=barrier,
            _env=env,
            _lock=lock,
            _results=results,
        ) -> None:
            _barrier.wait()
            try:
                result = _env.service.run_operation(_op, owner_token=owner)
                with _lock:
                    _results.append(("ok", result))
            except ExecutionError as exc:
                with _lock:
                    _results.append(("err", exc.code))

        threads = [
            threading.Thread(target=worker, args=(f"p09-{round_no}-a",)),
            threading.Thread(target=worker, args=(f"p09-{round_no}-b",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        ok = [r for kind, r in results if kind == "ok"]
        err = [r for kind, r in results if kind == "err"]
        assert len(ok) == 1, f"round {round_no}: {results}"
        assert err in (
            [ExecutionErrorCode.LEASE_LOST],
            [ExecutionErrorCode.ILLEGAL_TRANSITION],
        ), f"round {round_no}: {results}"
        assert ok[0].status == OperationStatus.SUCCEEDED.value

        # exactly one terminal event and one outbox row per operation
        assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 2 * (round_no + 1)
        assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == round_no + 1
        assert fetch_all(
            a2.gateway_dsn,
            "SELECT phase, seq FROM ag_ledger_events WHERE operation_id = %s ORDER BY seq",
            (accepted.operation_id,),
        ) == [("RESERVE", 0), ("SETTLE", 1)]
        assert order_count(a2) == round_no + 1
        totals["terminal"] += 1
        totals["refused"] += len(err)

    assert totals == {"terminal": ROUNDS, "refused": ROUNDS}


def test_p09_expired_old_worker_cannot_overwrite_the_new_terminal(a2):
    """P09/OBL04: an expired old owner never overwrites a newer owner or a
    terminal state, even with the same operation. Ten deterministic rounds."""
    for round_no in range(ROUNDS):
        key = f"p09-stale-{round_no}"
        env = make_env(
            a2,
            root_limit=10_000_000,
            mid_limit=10_000_000,
            leaf_limit=10_000_000,
            root_calls=1000,
            mid_calls=1000,
            leaf_calls=1000,
        )
        inv = env.tree.invocation(
            idempotency_key=key, tool_id="procurement.order.create", params=order_params()
        )
        accepted = env.service.accept_invocation(inv, env.permission())

        # the old worker claims and commits the downstream effect, then "dies"
        old_claim = None

        def crash_after_downstream(claim, outcome) -> None:
            nonlocal old_claim
            old_claim = claim
            raise RuntimeError("old worker died before the terminal transaction")

        with pytest.raises(RuntimeError, match="died before"):
            env.service.run_operation(
                accepted.operation_id,
                owner_token=f"old-{round_no}",
                pause=crash_after_downstream,
            )
        assert old_claim is not None

        # time passes: the lease expires and a new owner takes over
        expire_lease(a2.gateway_dsn, accepted.operation_id)
        env2 = make_env(
            a2,
            root_limit=10_000_000,
            mid_limit=10_000_000,
            leaf_limit=10_000_000,
            root_calls=1000,
            mid_calls=1000,
            leaf_calls=1000,
        )
        result = env2.service.run_operation(accepted.operation_id, owner_token=f"new-{round_no}")
        assert result.status == OperationStatus.SUCCEEDED.value
        assert result.lease.fencing_version > old_claim.lease.fencing_version

        # the old worker comes back late with its stale fencing version
        with psycopg.connect(a2.gateway_dsn, autocommit=True) as conn:
            with pytest.raises(ExecutionError) as excinfo:
                exec_store.assert_terminal_write_allowed(
                    conn,
                    operation_id=accepted.operation_id,
                    owner_token=old_claim.lease.owner_token,
                    fencing_version=old_claim.lease.fencing_version,
                )
            assert excinfo.value.code in (
                ExecutionErrorCode.LEASE_LOST,
                ExecutionErrorCode.ILLEGAL_TRANSITION,
            )

        assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 2 * (round_no + 1)
        assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == round_no + 1
        assert order_count(a2) == round_no + 1


def test_p09_unknown_claim_keeps_unknown_and_never_releases(a2):
    """P09/OBL04: claiming an UNKNOWN operation keeps UNKNOWN and keeps the budget."""
    inv = a2.tree.invocation(
        idempotency_key="p09-unknown",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    # the downstream call is lost before it reaches the service: nothing exists
    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        downstream=NoneThenRealPort(a2.downstream, misses=0),
    )
    first = env.service.reconcile(accepted.operation_id, owner_token="worker-unknown-1")
    assert first.status == OperationStatus.UNKNOWN.value

    expire_lease(a2.gateway_dsn, accepted.operation_id)
    second = env.service.reconcile(accepted.operation_id, owner_token="worker-unknown-2")
    assert second.status == OperationStatus.UNKNOWN.value
    assert second.previous_status == OperationStatus.UNKNOWN.value
    assert second.action is None

    counters = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    assert counters["amount_reserved"] == ORDER_AMOUNT_FEN
    assert counters["amount_settled"] == 0
    assert counters["calls_reserved"] == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 1
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 0


# ------------------------------------------------------------------ OBL04


def test_obl04_expired_lease_without_any_new_owner_is_still_refused(a2):
    """OBL04: expiry alone blocks the terminal write, even with no new owner."""
    inv = a2.tree.invocation(
        idempotency_key="obl04-expiry",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    claim = None

    def capture(c, outcome) -> None:
        nonlocal claim
        claim = c
        raise RuntimeError("stop before terminal")

    with pytest.raises(RuntimeError, match="stop before terminal"):
        a2.service.run_operation(accepted.operation_id, owner_token="obl04-worker", pause=capture)

    # nobody takes over: only the clock moves
    expire_lease(a2.gateway_dsn, accepted.operation_id)
    with psycopg.connect(a2.gateway_dsn, autocommit=True) as conn:
        with pytest.raises(ExecutionError) as excinfo:
            exec_store.assert_terminal_write_allowed(
                conn,
                operation_id=accepted.operation_id,
                owner_token=claim.lease.owner_token,
                fencing_version=claim.lease.fencing_version,
            )
        assert excinfo.value.code is ExecutionErrorCode.LEASE_LOST

    # owner and version are both required
    with psycopg.connect(a2.gateway_dsn, autocommit=True) as conn:
        with pytest.raises(ExecutionError):
            exec_store.assert_terminal_write_allowed(
                conn,
                operation_id=accepted.operation_id,
                owner_token="somebody-else",
                fencing_version=claim.lease.fencing_version,
            )
        with pytest.raises(ExecutionError):
            exec_store.assert_terminal_write_allowed(
                conn,
                operation_id=accepted.operation_id,
                owner_token=claim.lease.owner_token,
                fencing_version=claim.lease.fencing_version + 5,
            )

    # the budget is still reserved and nothing was released
    counters = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    assert counters["amount_reserved"] == ORDER_AMOUNT_FEN
    assert counters["amount_settled"] == 0
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 1


def test_obl04_live_lease_by_another_owner_is_refused(a2):
    """OBL04: a live lease held by somebody else refuses the claim, no change."""
    inv = a2.tree.invocation(
        idempotency_key="obl04-live",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    a2.service.run_operation(accepted.operation_id, owner_token="obl04-live-a")

    env2 = build_env(tree=a2.tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)
    with pytest.raises(ExecutionError) as excinfo:
        env2.service.run_operation(accepted.operation_id, owner_token="obl04-live-b")
    assert excinfo.value.code in (
        ExecutionErrorCode.LEASE_LOST,
        ExecutionErrorCode.ILLEGAL_TRANSITION,
    )
    row = fetch_one(
        a2.gateway_dsn,
        "SELECT owner_token, fencing_version FROM ag_execution_leases WHERE operation_id = %s",
        (accepted.operation_id,),
    )
    assert row[0] == "obl04-live-a"
    assert row[1] == 1


# ------------------------------------------------------------------- P10


def test_p10_internal_recovery_completes_after_revocation(a2):
    """P10: revoking an ancestor never blocks the internal recovery of an
    already accepted intent, and never creates a second one."""
    from agent_guard.ledger import provisioning as prov

    inv = a2.tree.invocation(
        idempotency_key="p10-order",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    with psycopg.connect(a2.gateway_dsn) as conn:
        prov.revoke_grant(conn, a2.tree.mid_id)

    result = a2.service.run_operation(accepted.operation_id, owner_token="worker-p10")
    assert result.status == OperationStatus.SUCCEEDED.value
    assert result.action is TerminalAction.SETTLE
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1
    assert order_count(a2) == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 2


def test_p10_external_retry_rejected_after_revocation(a2):
    """P10: a revoked ancestor rejects external retries of the same business key."""
    from agent_guard.ledger import provisioning as prov

    inv = a2.tree.invocation(
        idempotency_key="p10-external",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    with psycopg.connect(a2.gateway_dsn) as conn:
        prov.revoke_grant(conn, a2.tree.mid_id)

    retry = a2.tree.invocation(
        idempotency_key="p10-external",
        jti="jti-p10-retry",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    with pytest.raises(LedgerError) as excinfo:
        a2.service.accept_invocation(retry, a2.permission())
    assert excinfo.value.code is ErrorCode.REVOKED

    # the internal recovery of the already accepted intent still completes
    result = a2.service.run_operation(accepted.operation_id, owner_token="worker-p10-ext")
    assert result.status == OperationStatus.SUCCEEDED.value
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 2


def test_p10_external_retry_rejected_after_key_deactivation(a2):
    """P10: a deactivated holder key rejects external retries of the same key."""
    from agent_guard.ledger import provisioning as prov

    inv = a2.tree.invocation(
        idempotency_key="p10-deactivated",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    with psycopg.connect(a2.gateway_dsn) as conn:
        prov.deactivate_principal(
            conn,
            tenant_id=a2.tree.tenant_id,
            client_id=a2.tree.executor[0],
            kid=a2.tree.executor[1],
        )

    retry = a2.tree.invocation(
        idempotency_key="p10-deactivated",
        jti="jti-p10-retry-2",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    with pytest.raises(LedgerError) as excinfo:
        a2.service.accept_invocation(retry, a2.permission())
    assert excinfo.value.code is ErrorCode.HOLDER_MISMATCH

    result = a2.service.run_operation(accepted.operation_id, owner_token="worker-p10-deact")
    assert result.status == OperationStatus.SUCCEEDED.value
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1
    assert order_count(a2) == 1


def test_p10_expiry_blocks_external_retry_but_not_internal_recovery(a2):
    """P10: an expired ancestor rejects external retries; the accepted intent still runs.

    ``ag_grants.expires_at`` is immutable, so the window is fixed at creation
    time and the test waits for the real database clock to pass it (a validity
    window, not a concurrency race).
    """
    import time as _time
    from datetime import datetime, timedelta, timezone

    current = datetime.now(tz=timezone.utc)
    env = make_env(
        a2,
        valid_until=current + timedelta(seconds=2),
        root_limit=10_000_000,
        mid_limit=10_000_000,
        leaf_limit=10_000_000,
    )
    inv = env.tree.invocation(
        idempotency_key="p10-expired",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = env.service.accept_invocation(inv, env.permission())

    deadline = _time.monotonic() + 30
    while _time.monotonic() < deadline:
        with psycopg.connect(a2.gateway_dsn) as conn:
            expired = conn.execute(
                "SELECT count(*) FROM ag_grants WHERE grant_id = %s "
                "AND expires_at <= clock_timestamp()",
                (env.tree.root_id,),
            ).fetchone()[0]
        if expired == 1:
            break
        _time.sleep(0.05)
    else:  # pragma: no cover - defensive
        raise AssertionError("the validity window never closed")

    retry = env.tree.invocation(
        idempotency_key="p10-expired",
        jti="jti-p10-expired",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    with pytest.raises(LedgerError) as excinfo:
        env.service.accept_invocation(retry, env.permission())
    assert excinfo.value.code is ErrorCode.EXPIRED

    result = env.service.run_operation(accepted.operation_id, owner_token="worker-p10-exp")
    assert result.status == OperationStatus.SUCCEEDED.value
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1
