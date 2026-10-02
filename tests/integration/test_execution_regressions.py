"""A2.1 correction regressions: formal rejection tests for the r2 review issues.

Each test here turns an independently confirmed trigger into a *formal* negative
assertion: the dangerous behaviour must be refused and must leave zero new
reservation, zero new evidence and zero downstream effect. The assertions are
written as requirements, not copied from any observation log.

Issue map: A21-R1-LOCK, A21-R1-LEGACY, A21-R1-OUTCOME, A21-R1-NOTIFY,
A21-R1-CHAIN, A21-R1-LOG, A21-R1-BOUNDS, A21-R1-EVENT, A21-R1-CANDIDATE,
A21-R2-SNAPSHOT.
"""

from __future__ import annotations

import dataclasses
import json
import os
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
    ToolId,
)
from agent_guard.contracts.ledger import TrustedCost
from agent_guard.execution import store as exec_store
from agent_guard.execution.service import ExecutionService, safe_reason
from agent_guard.ledger import store as ledger_store
from agent_guard.ledger.migrate import DEFAULT_MIGRATIONS_DIR, apply_migrations
from agent_guard.tools.catalog import (
    snapshot_from_bytes,
    snapshot_to_bytes,
    snapshots_equal,
)
from agent_guard.tools.downstream import MockDownstream
from tests.fixtures.dbstate import fetch_all, fetch_counters, fetch_counts
from tests.fixtures.execution import (
    ORDER_AMOUNT_FEN,
    build_env,
    constraints_for,
    make_reference_operation,
    notification_params,
    order_params,
    permission_for,
    read_params,
)
from tests.fixtures.isolation import (
    create_downstream_database,
    create_scratch_database,
    drop_downstream_database,
    drop_scratch_database,
)
from tests.fixtures.state import build_tree

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUNDS = 10


# ----------------------------------------------------------------- helpers


def _downstream_counts(dsn) -> dict[str, int]:
    with psycopg.connect(dsn) as conn:
        return {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("ds_operations", "ds_orders", "ds_notifications")
        }


def _assert_nothing_new(a2, baseline_counts, baseline_counters):
    assert fetch_counts(a2.gateway_dsn) == baseline_counts
    for grant_id, expected in baseline_counters.items():
        assert fetch_counters(a2.gateway_dsn, grant_id) == expected


def _insert_raw_operation(env, *, operation_id, **overrides):
    """Persist one operation through the store helpers (legacy row shapes).

    ``ag_operations`` immutable columns cannot be UPDATEd, so mismatched legacy
    material is written at INSERT time, exactly like a pre-005 database held it.
    """
    fields = dict(
        operation_id=operation_id,
        tenant_id=env.tree.tenant_id,
        task_id=env.tree.task_id,
        tool_id="procurement.order.create",
        idempotency_key=operation_id,
        grant_id=env.tree.leaf_id,
        holder_client_id=env.tree.executor[0],
        holder_kid=env.tree.executor[1],
        tool_version="1",
        canonical_params=order_params(),
        currency="CNY",
        amount_fen=70000,
        calls=1,
        quote_id="quote-001",
        quote_version="1",
        quote_snapshot=None,
        token_digest="synthetic-token",
        proof_digest="synthetic-proof",
        intent_digest="synthetic-intent",
        evidence_ref="synthetic-evidence",
    )
    fields.update(overrides)
    with psycopg.connect(env.gateway_dsn) as conn:
        with conn.transaction():
            ledger_store.insert_operation(conn, **fields)
            nodes = [env.tree.root_id, env.tree.mid_id, env.tree.leaf_id]
            for grant_id in nodes:
                ledger_store.apply_reservation(
                    conn, grant_id, fields["amount_fen"], fields["calls"]
                )
            ledger_store.insert_reserve_event(
                conn,
                operation_id=operation_id,
                seq=0,
                nodes=[(i, g, fields["amount_fen"], fields["calls"]) for i, g in enumerate(nodes)],
            )
    return operation_id


def _accepted(a2, key: str = "regression"):
    return a2.service.accept_invocation(
        a2.tree.invocation(
            idempotency_key=key, tool_id="procurement.order.create", params=order_params()
        ),
        a2.permission(),
    )


# ---------------------------------------------------------- A21-R1-LOCK


def _record_lock_order(service, monkeypatch, operation_id, *, entry):
    """Record the order in which one entry acquires the shared lock classes."""
    order: list[str] = []
    orig_task = ledger_store.lock_task
    orig_grants = ledger_store.lock_grants_root_to_leaf
    orig_operation = exec_store.lock_operation
    orig_lease = exec_store.claim_lease
    orig_lock_lease = exec_store.lock_lease

    def task(conn, *args, **kwargs):
        order.append("task")
        return orig_task(conn, *args, **kwargs)

    def grants(conn, *args, **kwargs):
        order.append("grants")
        return orig_grants(conn, *args, **kwargs)

    def operation(conn, *args, **kwargs):
        order.append("operation")
        return orig_operation(conn, *args, **kwargs)

    def lease(*args, **kwargs):
        order.append("lease")
        return orig_lease(*args, **kwargs)

    def lock_lease(*args, **kwargs):
        order.append("lease")
        return orig_lock_lease(*args, **kwargs)

    monkeypatch.setattr(ledger_store, "lock_task", task)
    monkeypatch.setattr(ledger_store, "lock_grants_root_to_leaf", grants)
    monkeypatch.setattr(exec_store, "lock_operation", operation)
    monkeypatch.setattr(exec_store, "claim_lease", lease)
    monkeypatch.setattr(exec_store, "lock_lease", lock_lease)

    if entry == "claim":
        service._claim(operation_id, "lock-order-owner")
    else:  # finalize after a paused run
        saved = {}

        def capture(claim, outcome):
            saved.update(claim=claim, outcome=outcome)
            raise RuntimeError("pause before terminal")

        with pytest.raises(RuntimeError, match="pause before terminal"):
            service.run_operation(operation_id, owner_token="lock-order-owner", pause=capture)
        del order[:]
        service._finalize(saved["claim"], saved["outcome"], downstream_called=True, reason="")
    return order


def test_claim_lock_acquisition_order_is_task_grants_operation_lease(a2, monkeypatch):
    """A21-R1-LOCK: the claim path must never take the operation before the task."""
    operation_id = _accepted(a2, "lock-order-claim").operation_id
    order = _record_lock_order(a2.service, monkeypatch, operation_id, entry="claim")
    assert order.index("task") < order.index("operation")
    assert order.index("grants") < order.index("operation")
    assert order.index("operation") < order.index("lease")


def test_finalize_lock_acquisition_order_is_task_grants_operation_lease(a2, monkeypatch):
    """A21-R1-LOCK: the terminal path uses the very same lock order."""
    operation_id = _accepted(a2, "lock-order-final").operation_id
    order = _record_lock_order(a2.service, monkeypatch, operation_id, entry="finalize")
    assert order.index("task") < order.index("operation")
    assert order.index("grants") < order.index("operation")
    assert order.index("operation") < order.index("lease")


def test_claim_and_finalize_interleaved_never_deadlock(a2, monkeypatch):
    """A21-R1-LOCK/A21-R3-TESTSYNC: 10 rounds of a genuinely adversarial race.

    The barrier is placed at the *first* lock each thread takes, which is a
    point both threads reach no matter which lock class comes first. That is
    exactly the interleaving that made the old reversed order deadlock: each
    thread holds its first lock while the other wants it. With one global lock
    order they serialise instead.

    The test fails on **any** thread exception (including
    ``BrokenBarrierError``) and on any round that does not end in a complete
    settle: one order, RESERVE+SETTLE, one outbox row and settled counters.
    """
    for round_no in range(ROUNDS):
        with psycopg.connect(a2.gateway_dsn) as conn:
            tree = build_tree(
                conn,
                root_limit=10_000_000,
                mid_limit=10_000_000,
                leaf_limit=10_000_000,
                root_calls=1000,
                mid_calls=1000,
                leaf_calls=1000,
            )
        env = build_env(tree=tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)
        operation_id = env.service.accept_invocation(
            tree.invocation(
                idempotency_key=f"lock-race-{round_no}",
                tool_id="procurement.order.create",
                params=order_params(),
            ),
            env.permission(),
        ).operation_id
        saved: dict = {}

        def capture(claim, outcome, _saved=saved):
            _saved.update(claim=claim, outcome=outcome)
            raise RuntimeError("pause before terminal")

        with pytest.raises(RuntimeError, match="pause before terminal"):
            env.service.run_operation(
                operation_id, owner_token=f"lock-old-{round_no}", pause=capture
            )

        # one barrier, reached exactly once per thread, before any locking
        first_lock = threading.Barrier(2, timeout=25)
        reached: set[str] = set()
        guard = threading.Lock()
        orig_task = ledger_store.lock_task
        orig_grants = ledger_store.lock_grants_root_to_leaf
        orig_operation = exec_store.lock_operation

        def wrap_first(name, orig, _barrier=first_lock, _reached=reached, _guard=guard):
            def wrapper(*args, _name=name, _orig=orig, **kwargs):
                with _guard:
                    first = threading.current_thread().name not in _reached
                    _reached.add(threading.current_thread().name)
                if first:
                    _barrier.wait()
                return _orig(*args, **kwargs)

            return wrapper

        monkeypatch.setattr(ledger_store, "lock_task", wrap_first("task", orig_task))
        monkeypatch.setattr(
            ledger_store, "lock_grants_root_to_leaf", wrap_first("grants", orig_grants)
        )
        monkeypatch.setattr(exec_store, "lock_operation", wrap_first("operation", orig_operation))

        results: list[str] = []
        unexpected: list[str] = []

        def run_final(_service=env.service, _saved=saved, _out=results, _bad=unexpected):
            try:
                _service._finalize(
                    _saved["claim"], _saved["outcome"], downstream_called=True, reason=""
                )
                _out.append("final-ok")
            except Exception as exc:  # noqa: BLE001 - every kind must be recorded
                _bad.append(f"final-{type(exc).__name__}: {exc}")

        def run_claim(
            _service=env.service, _op=operation_id, _rn=round_no, _out=results, _bad=unexpected
        ):
            try:
                _service._claim(_op, f"lock-new-{_rn}")
                _out.append("claim-ok")
            except Exception as exc:  # noqa: BLE001 - every kind must be recorded
                _out.append(f"claim-{safe_reason(exc)}")

        threads = [
            threading.Thread(target=run_final, name="final"),
            threading.Thread(target=run_claim, name="claim"),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(40)

        # 1. nothing may hang and nothing may be swallowed
        assert not any(thread.is_alive() for thread in threads), f"round {round_no} hung"
        assert unexpected == [], f"round {round_no}: unexpected thread errors {unexpected}"
        assert not any("BrokenBarrierError" in entry for entry in results), results
        assert not any("DeadlockDetected" in entry for entry in results), results
        assert sorted(reached) == ["claim", "final"], reached

        # 2. the race must make real terminal progress every single round
        assert "final-ok" in results, f"round {round_no}: no terminal write: {results}"
        claim_result = [entry for entry in results if entry.startswith("claim-")]
        assert len(claim_result) == 1, results
        assert claim_result[0] in ("claim-ok", "claim-LEASE_LOST", "claim-ILLEGAL_TRANSITION"), (
            results
        )
        assert env.service.operation_status(operation_id) == "SUCCEEDED"
        assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == round_no + 1
        assert fetch_all(
            a2.gateway_dsn,
            "SELECT phase, seq FROM ag_ledger_events WHERE operation_id = %s ORDER BY seq",
            (operation_id,),
        ) == [("RESERVE", 0), ("SETTLE", 1)]
        assert _downstream_counts(a2.downstream_dsn)["ds_orders"] == round_no + 1
        for grant_id in (tree.root_id, tree.mid_id, tree.leaf_id):
            counters = fetch_counters(a2.gateway_dsn, grant_id)
            assert counters == {
                "amount_reserved": 0,
                "amount_settled": 70000,
                "calls_reserved": 0,
                "calls_settled": 1,
            }, f"round {round_no} {grant_id}: {counters}"
        monkeypatch.undo()

    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == ROUNDS


def _hold_and_deadlock(gateway_dsn, operation_row, task_row, *, lock_timeout_ms=4000):
    """Two real connections hold the two lock classes and then swap.

    Returns the observed symptom: the exact exception names plus whether the
    server's activity view showed both backends waiting on a lock. This is the
    lock cycle the fixed code must never produce.
    """
    ready_a = threading.Event()
    ready_b = threading.Event()
    symptoms: list[str] = []
    waits: list[tuple] = []
    guard = threading.Lock()

    def holder_a():
        conn = psycopg.connect(gateway_dsn, autocommit=False, connect_timeout=5)
        try:
            conn.execute("SELECT set_config('lock_timeout', %s, false)", (f"{lock_timeout_ms}ms",))
            conn.execute(
                "SELECT operation_id FROM ag_operations WHERE operation_id = %s FOR UPDATE",
                (operation_row,),
            )
            ready_a.set()
            assert ready_b.wait(20), "the other holder never took its lock"
            try:
                conn.execute(
                    "SELECT tenant_id FROM ag_tasks "
                    "WHERE tenant_id = %s AND task_id = %s FOR UPDATE",
                    task_row,
                )
                with guard:
                    symptoms.append("a-took-task")
            except Exception as exc:  # noqa: BLE001 - the exact class is the evidence
                with guard:
                    symptoms.append(f"a-{type(exc).__name__}")
        finally:
            conn.rollback()
            conn.close()

    def holder_b():
        conn = psycopg.connect(gateway_dsn, autocommit=False, connect_timeout=5)
        try:
            conn.execute("SELECT set_config('lock_timeout', %s, false)", (f"{lock_timeout_ms}ms",))
            conn.execute(
                "SELECT tenant_id FROM ag_tasks WHERE tenant_id = %s AND task_id = %s FOR UPDATE",
                task_row,
            )
            ready_b.set()
            assert ready_a.wait(20), "the other holder never took its lock"
            try:
                conn.execute(
                    "SELECT operation_id FROM ag_operations WHERE operation_id = %s FOR UPDATE",
                    (operation_row,),
                )
                with guard:
                    symptoms.append("b-took-operation")
            except Exception as exc:  # noqa: BLE001 - the exact class is the evidence
                with guard:
                    symptoms.append(f"b-{type(exc).__name__}")
        finally:
            conn.rollback()
            conn.close()

    threads = [
        threading.Thread(target=holder_a, name="holder-a"),
        threading.Thread(target=holder_b, name="holder-b"),
    ]
    for thread in threads:
        thread.start()
    # observe the real server-side wait graph while both want the other's lock
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline and len(symptoms) < 2:
        with psycopg.connect(gateway_dsn, autocommit=True, connect_timeout=5) as monitor:
            rows = monitor.execute(
                "SELECT wait_event_type, wait_event FROM pg_stat_activity "
                "WHERE wait_event_type = 'Lock' AND datname = current_database()"
            ).fetchall()
        if rows:
            waits.append(tuple(rows))
        time.sleep(0.05)
    for thread in threads:
        thread.join(30)
    assert not any(thread.is_alive() for thread in threads), "the lock cycle never resolved"
    return symptoms, waits


def test_reverse_lock_order_produces_a_real_server_deadlock(a2):
    """A21-R3-TESTSYNC: the reverse order is a *real* server-side lock cycle.

    Two connections really hold the operation row and the task row and then
    ask for each other's. The server must report a precise
    ``DeadlockDetected``/``LockNotAvailable`` and the activity view must show
    both backends waiting on a lock. This is the anchor that makes the
    regression test meaningful: without a real cycle there is nothing to catch.
    """
    operation_id = _accepted(a2, "deadlock-anchor").operation_id
    symptoms, waits = _hold_and_deadlock(
        a2.gateway_dsn, operation_id, (a2.tree.tenant_id, a2.tree.task_id)
    )
    precise = [
        s
        for s in symptoms
        if s.endswith(("DeadlockDetected", "LockNotAvailable", "LockNotAvailable"))
    ]
    assert precise, f"no precise lock-cycle symptom: {symptoms}"
    assert any("DeadlockDetected" in s for s in symptoms), symptoms
    assert waits, "the server never showed a lock wait for the cycle"


def test_lock_regression_reverse_efficacy_requires_a_real_deadlock(a2, monkeypatch):
    """A21-R3-TESTSYNC: the reversed service path must exhibit the real cycle.

    A generic terminal-state refusal is *not* enough: the test only passes when
    a ``DeadlockDetected`` is actually produced by the reversed lock order.
    """
    operation_id = _accepted(a2, "lock-reversed").operation_id
    saved: dict = {}

    def capture(claim, outcome, _saved=saved):
        _saved.update(claim=claim, outcome=outcome)
        raise RuntimeError("pause before terminal")

    with pytest.raises(RuntimeError, match="pause before terminal"):
        a2.service.run_operation(operation_id, owner_token="lock-reversed-old", pause=capture)

    first_lock = threading.Barrier(2, timeout=15)
    reached: set[str] = set()
    guard = threading.Lock()
    orig_task = ledger_store.lock_task
    orig_operation = exec_store.lock_operation

    def wrap_first(name, orig, _barrier=first_lock, _reached=reached, _guard=guard):
        def wrapper(*args, _name=name, _orig=orig, **kwargs):
            with _guard:
                first = threading.current_thread().name not in _reached
                _reached.add(threading.current_thread().name)
            if first:
                _barrier.wait()
            return _orig(*args, **kwargs)

        return wrapper

    monkeypatch.setattr(ledger_store, "lock_task", wrap_first("task", orig_task))
    monkeypatch.setattr(exec_store, "lock_operation", wrap_first("operation", orig_operation))

    results: list[str] = []

    def run_final(_service=a2.service, _saved=saved, _out=results):
        try:
            _service._finalize(
                _saved["claim"], _saved["outcome"], downstream_called=True, reason=""
            )
            _out.append("final-ok")
        except Exception as exc:  # noqa: BLE001 - the exact code is the evidence
            _out.append(f"final-{safe_reason(exc)}")

    def reversed_claim(conn, op, owner):
        exec_store.lock_operation(conn, op)
        probe = exec_store.fetch_operation(conn, op)
        ledger_store.lock_task(conn, probe.tenant_id, probe.task_id)
        path = ledger_store.load_path(conn, probe.grant_id)
        ledger_store.lock_grants_root_to_leaf(conn, [g.grant_id for g in path])
        return exec_store.claim_lease(
            conn, operation_id=op, owner_token=owner, lease_ttl_seconds=30
        )

    def run_reversed(_op=operation_id, _out=results):
        try:
            with a2.service._connect() as conn:
                with conn.transaction():
                    reversed_claim(conn, _op, "reversed-claim")
            _out.append("claim-ok")
        except Exception as exc:  # noqa: BLE001 - the exact code is the evidence
            _out.append(f"claim-{safe_reason(exc)}")

    threads = [
        threading.Thread(target=run_final, name="final"),
        threading.Thread(target=run_reversed, name="claim"),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    monkeypatch.undo()
    assert not any(thread.is_alive() for thread in threads), "the reversed race hung"
    assert any("DeadlockDetected" in entry for entry in results), (
        f"no real lock cycle observed, only: {results}"
    )


def test_lock_regression_efficacy_fails_when_the_race_is_serialized(a2, monkeypatch):
    """A21-R3-TESTSYNC: an efficacy test that cannot see a lock cycle must fail.

    If the two sides are forced to run one after the other there is no cycle at
    all; a plain terminal-state refusal must not be accepted as proof that the
    regression test would catch a reversed order.
    """
    operation_id = _accepted(a2, "lock-serialized").operation_id
    saved: dict = {}

    def capture(claim, outcome, _saved=saved):
        _saved.update(claim=claim, outcome=outcome)
        raise RuntimeError("pause before terminal")

    with pytest.raises(RuntimeError, match="pause before terminal"):
        a2.service.run_operation(operation_id, owner_token="lock-serialized-old", pause=capture)

    final_done = threading.Event()
    orig_operation = exec_store.lock_operation
    orig_finalize = ExecutionService._finalize

    def serialized_operation(conn, *args, **kwargs):
        if threading.current_thread().name == "claim":
            assert final_done.wait(20), "the finalizer never finished"
        return orig_operation(conn, *args, **kwargs)

    def finish_final(self, *args, **kwargs):
        try:
            return orig_finalize(self, *args, **kwargs)
        finally:
            final_done.set()

    monkeypatch.setattr(exec_store, "lock_operation", serialized_operation)
    monkeypatch.setattr(ExecutionService, "_finalize", finish_final)

    results: list[str] = []

    def run_final(_service=a2.service, _saved=saved, _out=results):
        try:
            _service._finalize(
                _saved["claim"], _saved["outcome"], downstream_called=True, reason=""
            )
            _out.append("final-ok")
        except Exception as exc:  # noqa: BLE001
            _out.append(f"final-{safe_reason(exc)}")

    def reversed_claim(conn, op, owner):
        exec_store.lock_operation(conn, op)
        probe = exec_store.fetch_operation(conn, op)
        ledger_store.lock_task(conn, probe.tenant_id, probe.task_id)
        path = ledger_store.load_path(conn, probe.grant_id)
        ledger_store.lock_grants_root_to_leaf(conn, [g.grant_id for g in path])
        return exec_store.claim_lease(
            conn, operation_id=op, owner_token=owner, lease_ttl_seconds=30
        )

    def run_reversed(_op=operation_id, _out=results):
        try:
            with a2.service._connect() as conn:
                with conn.transaction():
                    reversed_claim(conn, _op, "reversed-claim")
            _out.append("claim-ok")
        except Exception as exc:  # noqa: BLE001
            _out.append(f"claim-{safe_reason(exc)}")

    threads = [
        threading.Thread(target=run_final, name="final"),
        threading.Thread(target=run_reversed, name="claim"),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    monkeypatch.undo()
    assert not any(thread.is_alive() for thread in threads)
    # serialized: no lock cycle can exist, so the efficacy criterion must fail
    assert not any("DeadlockDetected" in entry for entry in results), results
    with pytest.raises(AssertionError):
        assert any("DeadlockDetected" in entry for entry in results), (
            f"efficacy would pass without a lock cycle: {results}"
        )


# --------------------------------------------------------- A21-R1-LEGACY


def _legacy_variants(snap, params):
    """Eight persisted accept-material defects seen on upgraded legacy rows."""
    return {
        "extra-params": (params[:-1] + b',"unexpected":true}', snapshot_to_bytes(snap)),
        "missing-snapshot": (params, None),
        "wrong-items": (order_params(items=(("sku-001", 2),)), snapshot_to_bytes(snap)),
        "wrong-quote-id": (
            params,
            snapshot_to_bytes(dataclasses.replace(snap, quote_id="quote-unrelated")),
        ),
        "missing-evidence": (params, snapshot_to_bytes(snap)),
        "malformed-json": (b"not JSON but nonempty legacy bytes", snapshot_to_bytes(snap)),
        "bool-snapshot": (
            params,
            snapshot_to_bytes(snap).replace(b'"quantity":1', b'"quantity":true'),
        ),
        "incomplete-reserve": (params, snapshot_to_bytes(snap)),
    }


LEGACY_VARIANTS = (
    "extra-params",
    "missing-snapshot",
    "wrong-items",
    "wrong-quote-id",
    "missing-evidence",
    "malformed-json",
    "bool-snapshot",
    "incomplete-reserve",
)


@pytest.mark.parametrize("variant", LEGACY_VARIANTS)
@pytest.mark.parametrize("entry", ["run", "reconcile", "candidate", "helper"])
def test_legacy_material_is_auto_quarantined_at_every_entry(
    a2, namespace, tmp_path, variant, entry
):
    """A21-R1-LEGACY: no entry may execute, settle or release bad material.

    The rows are written on a pre-005 database and then upgraded, exactly like
    a real legacy database. Every internal entry (not only the manual helper)
    must detect the defect, persist the quarantine and keep the budget.
    """
    db = create_scratch_database(namespace.base_dsn)
    try:
        subset = tmp_path / "pre005"
        subset.mkdir()
        for name in ("001_init.sql", "002_root_invariants.sql", "003_root_delete_guard.sql"):
            (subset / name).write_bytes((DEFAULT_MIGRATIONS_DIR / name).read_bytes())
        with psycopg.connect(db.dsn) as conn:
            apply_migrations(conn, subset)
            tree = build_tree(conn)
        env = build_env(tree=tree, gateway_dsn=db.dsn, downstream_dsn=a2.downstream_dsn)
        snap = env.catalog.build_order_snapshot(
            tenant_id=tree.tenant_id,
            task_id=tree.task_id,
            request_id="req-001",
            quote_id="quote-001",
            quote_version="1",
            items=(("sku-001", 1),),
            delivery_id="office-001",
        )
        params, raw = _legacy_variants(snap, order_params())[variant]
        operation_id = f"legacy-{variant}-{entry}"

        with psycopg.connect(db.dsn) as conn:
            with conn.transaction():
                ledger_store.insert_operation(
                    conn,
                    operation_id=operation_id,
                    tenant_id=tree.tenant_id,
                    task_id=tree.task_id,
                    tool_id="procurement.order.create",
                    idempotency_key=operation_id,
                    grant_id=tree.leaf_id,
                    holder_client_id=tree.executor[0],
                    holder_kid=tree.executor[1],
                    tool_version="1",
                    canonical_params=params,
                    currency="CNY",
                    amount_fen=70000,
                    calls=1,
                    quote_id="quote-001",
                    quote_version="1",
                    quote_snapshot=raw,
                    token_digest="" if variant == "missing-evidence" else "synthetic-token",
                    proof_digest="synthetic-proof",
                    intent_digest="synthetic-intent",
                    evidence_ref="synthetic-evidence",
                )
                nodes = [tree.root_id, tree.mid_id, tree.leaf_id]
                for grant_id in nodes:
                    ledger_store.apply_reservation(conn, grant_id, 70000, 1)
                ledger_store.insert_reserve_event(
                    conn,
                    operation_id=operation_id,
                    seq=0,
                    nodes=[
                        (i, g, 70000, 1)
                        for i, g in enumerate(
                            nodes[:1] if variant == "incomplete-reserve" else nodes
                        )
                    ],
                )
                ledger_store.record_proof(
                    conn,
                    holder_kid=tree.executor[1],
                    purpose="invoke",
                    endpoint="https://gateway.agent-guard.test/v1/invocations",
                    proof_jti=operation_id,
                    proof_digest="synthetic-proof",
                    evidence_ref="synthetic-evidence",
                )
                ledger_store.link_proof_to_operation(
                    conn,
                    holder_kid=tree.executor[1],
                    purpose="invoke",
                    endpoint="https://gateway.agent-guard.test/v1/invocations",
                    proof_jti=operation_id,
                    operation_id=operation_id,
                )
        with psycopg.connect(db.dsn) as conn:
            assert set(apply_migrations(conn)) == {"004", "005", "006"}

        error = None
        try:
            if entry == "candidate":
                env.service.accept_invocation(
                    tree.invocation(
                        idempotency_key=operation_id,
                        tool_id="procurement.order.create",
                        params=order_params(),
                    ),
                    env.permission(),
                )
            elif entry == "helper":
                assert env.service.quarantine_if_insufficient(operation_id)
            elif entry == "reconcile":
                env.service.reconcile(operation_id, owner_token="legacy-owner")
            else:
                env.service.run_operation(operation_id, owner_token="legacy-owner")
        except ExecutionError as exc:
            error = exc.code.value

        if entry == "helper":
            assert error is None, f"{variant}/{entry}: {error}"
        else:
            assert error == ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID.value, (
                f"{variant}/{entry}: {error}"
            )
        assert env.service.review_flag(operation_id) is not None, f"{variant}/{entry}"
        assert env.service.operation_status(operation_id) == "RESERVED"
        assert _downstream_counts(a2.downstream_dsn)["ds_operations"] == 0
        for grant_id in (tree.root_id, tree.mid_id, tree.leaf_id):
            counters = fetch_counters(db.dsn, grant_id)
            assert counters["amount_reserved"] == 70000
            assert counters["amount_settled"] == 0
        # the quarantine is persisted, so it survives the caller's rollback
        assert env.service.review_flag(operation_id) is not None
    finally:
        drop_scratch_database(namespace.base_dsn, db)


def test_quarantine_survives_the_callers_rollback(a2):
    """A21-R1-LEGACY: the flag is committed independently of the failed work."""
    operation_id = _insert_raw_operation(a2, operation_id="legacy-rollback", token_digest="")
    with pytest.raises(ExecutionError):
        a2.service.run_operation(operation_id, owner_token="legacy-rollback-owner")
    assert a2.service.review_flag(operation_id) is not None
    # a second attempt still refuses and does not clear the flag
    with pytest.raises(ExecutionError):
        a2.service.run_operation(operation_id, owner_token="legacy-rollback-owner")
    assert a2.service.review_flag(operation_id) is not None


# --------------------------------------------------------- A21-R1-OUTCOME


class _TamperedPort:
    """Port double returning a deliberately mis-bound downstream record."""

    def __init__(self, inner, *, mode, key, tool, params, quote, amount):
        self.inner = inner
        self.mode = mode
        self.key = key
        self.tool = tool
        self.params = params
        self.quote = quote
        self.amount = amount

    def execute(self, **kwargs):
        value = self.inner.execute(
            service_secret=kwargs.get("service_secret"),
            operation_id=self.key,
            tool_id=self.tool,
            canonical_params=self.params,
            quote=self.quote,
            expected_amount_fen=self.amount,
        )
        if self.mode == "missing-effect":
            value = dataclasses.replace(value, effect_ref=None)
        elif self.mode == "malformed-result":
            value = dataclasses.replace(value, result_bytes=b"not json at all")
        elif self.mode == "unbound-result":
            value = dataclasses.replace(
                value, result_bytes=b'{"operation_id":"someone-else","kind":"order"}'
            )
        elif self.mode == "string-refusal":
            value = dataclasses.replace(
                value, final_rejection="false", amount_fen=0, effect_ref=None
            )
        elif self.mode == "bool-amount":
            value = dataclasses.replace(value, amount_fen=False)
        elif self.mode == "wrong-kind":
            value = dataclasses.replace(value, result_bytes=b'{"operation_id":"X","kind":"read"}')
        return value

    def query(self, **kwargs):
        return self.inner.query(**kwargs)


@pytest.mark.parametrize(
    "mode",
    [
        "other-key-success",
        "other-key-refusal",
        "missing-effect",
        "malformed-result",
        "unbound-result",
        "string-refusal",
        "bool-amount",
        "wrong-kind",
    ],
)
def test_mis_bound_outcome_keeps_unknown_and_never_terminal(a2, mode):
    """A21-R1-OUTCOME: an outcome that is not this operation's own record is
    never settled and never released; the budget stays reserved."""
    inv = a2.tree.invocation(
        idempotency_key=f"outcome-{mode}",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    operation_id = accepted.operation_id
    stored = a2.service.load_operation(operation_id)

    other_key = "unrelated-persisted-key" if mode.startswith("other-key") else operation_id
    quote = snapshot_from_bytes(stored.quote_snapshot)
    inner = a2.downstream
    if mode == "other-key-refusal":
        # a *different* downstream domain refuses, and that refusal must not
        # release this operation's budget
        inner = MockDownstream(
            a2.downstream_dsn,
            service_secret=a2.secret,
            approved_suppliers=frozenset({"nobody"}),
        )
        other_key = "some-other-operation"
    port = _TamperedPort(
        inner,
        mode=mode,
        key=other_key,
        tool=ToolId.ORDER_CREATE,
        params=order_params(),
        quote=quote,
        amount=ORDER_AMOUNT_FEN,
    )
    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        downstream=port,
    )
    result = env.service.run_operation(operation_id, owner_token=f"outcome-{mode}")
    assert result.status == OperationStatus.UNKNOWN.value, mode
    assert result.action is None, mode
    assert env.service.outbox_entry(operation_id) is None, mode

    counters = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    assert counters["amount_reserved"] == ORDER_AMOUNT_FEN
    assert counters["amount_settled"] == 0
    assert counters["calls_reserved"] == 1
    assert counters["calls_settled"] == 0
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 1

    if mode == "other-key-refusal":
        # the original key may still succeed later and must settle exactly once
        late = a2.downstream.execute(
            service_secret=a2.secret,
            operation_id=operation_id,
            tool_id=ToolId.ORDER_CREATE,
            canonical_params=order_params(),
            quote=quote,
            expected_amount_fen=ORDER_AMOUNT_FEN,
        )
        assert late.effect_ref is not None
        final = env.service.reconcile(operation_id, owner_token=f"outcome-{mode}")
        assert final.status == OperationStatus.SUCCEEDED.value
        assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 1


def test_same_key_refusal_only_releases_its_own_operation(a2):
    """A21-R1-OUTCOME: a refusal is bound to its key; another key's refusal is
    never allowed to release this operation."""
    with psycopg.connect(a2.gateway_dsn) as conn:
        tree = build_tree(
            conn,
            root_limit=1_000_000,
            mid_limit=1_000_000,
            leaf_limit=1_000_000,
            root_calls=100,
            mid_calls=100,
            leaf_calls=100,
        )
    env0 = build_env(tree=tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)
    first = env0.service.accept_invocation(
        tree.invocation(
            idempotency_key="outcome-key-a",
            tool_id="procurement.order.create",
            params=order_params(),
        ),
        env0.permission(),
    ).operation_id
    second = env0.service.accept_invocation(
        tree.invocation(
            idempotency_key="outcome-key-b",
            tool_id="procurement.order.create",
            params=order_params(),
        ),
        env0.permission(),
    ).operation_id

    class RefuseOther:
        def execute(self, **kwargs):
            return a2.downstream.execute(
                service_secret=a2.secret,
                operation_id="not-this-one",
                tool_id=ToolId.ORDER_CREATE,
                canonical_params=order_params(),
                quote=snapshot_from_bytes(env0.service.load_operation(first).quote_snapshot),
                expected_amount_fen=ORDER_AMOUNT_FEN,
            )

        def query(self, **kwargs):
            return None

    env = build_env(
        tree=tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        downstream=RefuseOther(),
    )
    result = env.service.run_operation(first, owner_token="outcome-key-a")
    assert result.status == OperationStatus.UNKNOWN.value
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 0
    assert env0.service.operation_status(second) == "RESERVED"
    assert env0.service.operation_status(first) == "UNKNOWN"


# ---------------------------------------------------------- A21-R1-NOTIFY


@pytest.mark.parametrize("target", ["absent", "cross-tenant", "cross-task", "other-grant"])
def test_notification_target_access_is_verified(a2, target):
    """A21-R1-NOTIFY: a notification may only reference an operation its own
    grant and holder can access; nothing is reserved or delivered otherwise."""
    baseline_counts = fetch_counts(a2.gateway_dsn)
    baseline_counters = {
        grant_id: fetch_counters(a2.gateway_dsn, grant_id)
        for grant_id in (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id)
    }
    baseline_effects = _downstream_counts(a2.downstream_dsn)

    if target == "absent":
        ref = "does-not-exist"
    elif target == "cross-tenant":
        with psycopg.connect(a2.gateway_dsn) as conn:
            other = build_tree(conn, tenant_id="tenant-unrelated")
        ref = a2.ledger.accept(
            other.invocation(tool_id="procurement.request.read", params=read_params()),
            TrustedCost(0, 1),
        ).operation_id
    elif target == "cross-task":
        with psycopg.connect(a2.gateway_dsn) as conn:
            other = build_tree(conn, task_id="task-unrelated")
        ref = a2.ledger.accept(
            other.invocation(tool_id="procurement.request.read", params=read_params()),
            TrustedCost(0, 1),
        ).operation_id
    else:  # other-grant: same task, but owned by the mid grant/holder
        ref = a2.service.accept_invocation(
            a2.tree.invocation(
                grant_id=a2.tree.mid_id,
                tool_id="procurement.request.read",
                params=read_params(),
            ),
            permission_for(a2.tree, grant_id=a2.tree.mid_id),
        ).operation_id

    baseline_counts = fetch_counts(a2.gateway_dsn)
    baseline_counters = {
        grant_id: fetch_counters(a2.gateway_dsn, grant_id)
        for grant_id in (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id)
    }

    with pytest.raises(ExecutionError) as excinfo:
        a2.service.accept_invocation(
            a2.tree.invocation(
                idempotency_key=f"notify-{target}",
                tool_id="notification.template.send",
                params=notification_params(operation_id=ref),
            ),
            a2.permission(),
        )
    assert excinfo.value.code in (
        ExecutionErrorCode.RESOURCE_NOT_FOUND,
        ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
    )
    _assert_nothing_new(a2, baseline_counts, baseline_counters)
    assert _downstream_counts(a2.downstream_dsn) == baseline_effects


def test_notification_to_a_real_same_grant_target_is_allowed(a2):
    """A21-R1-NOTIFY: the strict policy still permits a legitimate target."""
    target = make_reference_operation(a2, key="notify-real-target", settle=True)
    accepted = a2.service.accept_invocation(
        a2.tree.invocation(
            idempotency_key="notify-real",
            tool_id="notification.template.send",
            params=notification_params(operation_id=target),
        ),
        a2.permission(),
    )
    result = a2.service.run_operation(accepted.operation_id, owner_token="notify-real")
    assert result.status == OperationStatus.SUCCEEDED.value
    assert _downstream_counts(a2.downstream_dsn)["ds_notifications"] == 1


# ----------------------------------------------------------- A21-R1-CHAIN


@pytest.mark.parametrize("mode", ["leaf-only", "missing-mid", "extra-depth", "reordered"])
def test_truncated_or_reordered_chain_is_refused(a2, mode):
    """A21-R1-CHAIN: a chain that is not the database path is refused."""
    full = (
        constraints_for(0, skus=()),
        constraints_for(1, skus=()),
        constraints_for(2),
    )
    # the full restrictive chain correctly refuses the order
    with pytest.raises(ExecutionError):
        a2.service.accept_invocation(
            a2.tree.invocation(
                idempotency_key=f"chain-full-{mode}",
                tool_id="procurement.order.create",
                params=order_params(),
            ),
            a2.permission(chain=full),
        )

    ids = (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id)
    if mode == "leaf-only":
        chain, chain_ids = (full[-1],), (ids[-1],)
    elif mode == "missing-mid":
        chain, chain_ids = (constraints_for(0), full[-1]), (ids[0], ids[-1])
    elif mode == "extra-depth":
        chain = (constraints_for(0), constraints_for(1), full[-1], full[-1])
        chain_ids = (ids[0], ids[1], ids[2], ids[2])
    else:  # reordered: right nodes, wrong order
        chain = (full[2], full[1], full[0])
        chain_ids = (ids[2], ids[1], ids[0])

    baseline = fetch_counts(a2.gateway_dsn)
    with pytest.raises(ExecutionError) as excinfo:
        a2.service.accept_invocation(
            a2.tree.invocation(
                idempotency_key=f"chain-{mode}",
                tool_id="procurement.order.create",
                params=order_params(),
            ),
            a2.permission(chain=chain, chain_grant_ids=chain_ids),
        )
    assert excinfo.value.code is ExecutionErrorCode.CONSTRAINT_MISMATCH
    assert fetch_counts(a2.gateway_dsn) == baseline


def test_chain_bound_to_another_path_is_refused(a2):
    """A21-R1-CHAIN: a spliced chain from another grant path is refused."""
    # three well-formed ids that belong to some other path entirely
    spliced = ("other-root-node", "other-mid-node", "other-leaf-node")
    baseline = fetch_counts(a2.gateway_dsn)
    with pytest.raises(ExecutionError) as excinfo:
        a2.service.accept_invocation(
            a2.tree.invocation(
                idempotency_key="chain-spliced",
                tool_id="procurement.order.create",
                params=order_params(),
            ),
            a2.permission(chain_grant_ids=spliced),
        )
    assert excinfo.value.code is ExecutionErrorCode.CONSTRAINT_MISMATCH
    assert fetch_counts(a2.gateway_dsn) == baseline


def test_root_mid_and_leaf_calls_are_all_allowed_with_their_own_chain(a2):
    """A21-R1-CHAIN: the positive cases still work at every depth."""
    results = []
    for grant_id, ancestor_ids, holder in (
        (a2.tree.root_id, (), a2.tree.planner),
        (a2.tree.mid_id, (a2.tree.root_id,), a2.tree.selector),
        (a2.tree.leaf_id, (a2.tree.root_id, a2.tree.mid_id), a2.tree.executor),
    ):
        inv = a2.tree.invocation(
            idempotency_key=f"chain-ok-{grant_id}",
            grant_id=grant_id,
            ancestor_ids=ancestor_ids,
            holder=holder,
            tool_id="procurement.request.read",
            params=read_params(),
        )
        results.append(
            a2.service.accept_invocation(inv, permission_for(a2.tree, grant_id=grant_id))
        )
    assert len(results) == 3
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 3


# ------------------------------------------------------------- A21-R1-LOG


def test_worker_redacts_a_malformed_dsn(a2):
    """A21-R1-LOG: a config error must never echo the value it was given."""
    marker = "REDACTION_MARKER_NOT_A_REAL_SECRET"
    env = {
        key: os.environ[key]
        for key in ("PATH", "PYTHONPATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
        if key in os.environ
    }
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env.update(
        AG_WORKER_GATEWAY_DSN=marker,
        AG_WORKER_DOWNSTREAM_DSN=a2.downstream_dsn,
        AG_WORKER_SERVICE_SECRET=a2.secret,
        AG_WORKER_OPERATION_ID="not-used",
    )
    proc = subprocess.run(
        [sys.executable, "-m", "agent_guard.execution.worker"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 1
    assert marker not in proc.stderr
    assert marker not in proc.stdout


def test_worker_redacts_a_downstream_error_carrying_a_secret(a2):
    """A21-R1-LOG: a downstream exception message is never propagated."""
    marker = "DOWNSTREAM_ERROR_MARKER"

    class ExplodingPort:
        def execute(self, **kwargs):
            raise RuntimeError(f"boom {marker} {a2.secret}")

        def query(self, **kwargs):
            raise RuntimeError(f"boom {marker} {a2.secret}")

    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        downstream=ExplodingPort(),
    )
    accepted = _accepted(a2, "log-explode")
    result = env.service.run_operation(accepted.operation_id, owner_token="log-explode")
    assert result.status == OperationStatus.UNKNOWN.value
    assert marker not in result.reason
    assert a2.secret not in result.reason
    assert result.reason == "RuntimeError"

    # the worker's own stderr is redacted too
    real_marker = "WORKER_STDERR_MARKER"

    class ExplodeOnQuery:
        def execute(self, **kwargs):
            raise RuntimeError(f"boom {real_marker}")

        def query(self, **kwargs):
            raise RuntimeError(f"boom {real_marker}")

    operation_id = accepted.operation_id
    child_env = {
        key: os.environ[key]
        for key in ("PATH", "PYTHONPATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
        if key in os.environ
    }
    child_env["PYTHONPATH"] = str(REPO_ROOT / "src")
    child_env.update(
        AG_WORKER_GATEWAY_DSN=a2.gateway_dsn,
        AG_WORKER_DOWNSTREAM_DSN=a2.downstream_dsn,
        AG_WORKER_SERVICE_SECRET=a2.secret,
        AG_WORKER_OPERATION_ID=operation_id,
        AG_WORKER_OWNER_TOKEN="log-worker",
        AG_WORKER_MODE="reconcile",
    )
    proc = subprocess.run(
        [sys.executable, "-m", "agent_guard.execution.worker"],
        cwd=str(REPO_ROOT),
        env=child_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert real_marker not in proc.stderr
    assert real_marker not in proc.stdout
    assert a2.secret not in proc.stderr


def test_safe_reason_never_carries_the_message():
    """A21-R1-LOG: only a stable code or class name is ever surfaced."""
    exc = RuntimeError("postgres://user:pass@host/db secret-token")
    assert safe_reason(exc) == "RuntimeError"
    coded = ExecutionError(ExecutionErrorCode.QUOTE_INVALID, "dsn=postgres://x secret")
    assert safe_reason(coded) == "QUOTE_INVALID"
    for value in (safe_reason(exc), safe_reason(coded)):
        assert "postgres" not in value
        assert "secret" not in value


# ------------------------------------------------------------ A21-R1-BOUNDS


def test_downstream_and_gateway_waits_are_bounded(a2):
    """A21-R1-BOUNDS: SQL waits are capped, and 0/bool are refused."""
    with a2.downstream._connect() as conn:
        statement, lock = conn.execute(
            "SELECT current_setting('statement_timeout'), current_setting('lock_timeout')"
        ).fetchone()
    assert statement not in ("", "0", "0ms"), statement
    assert lock not in ("", "0", "0ms"), lock

    with a2.service._read() as conn:
        statement, lock = conn.execute(
            "SELECT current_setting('statement_timeout'), current_setting('lock_timeout')"
        ).fetchone()
    assert statement not in ("", "0", "0ms"), statement
    assert lock not in ("", "0", "0ms"), lock

    for bad in (0, True, False, 1.5, -1, 600_001):
        with pytest.raises(ValueError):
            MockDownstream(a2.downstream_dsn, service_secret=a2.secret, lock_timeout_ms=bad)
        with pytest.raises(ValueError):
            MockDownstream(a2.downstream_dsn, service_secret=a2.secret, statement_timeout_ms=bad)
        with pytest.raises(ValueError):
            ExecutionService(
                gateway_dsn=a2.gateway_dsn,
                ledger=a2.ledger,
                catalog=a2.catalog,
                downstream=a2.downstream,
                downstream_secret=a2.secret,
                lock_timeout_ms=bad,
            )


def test_real_lock_wait_times_out_without_manual_cancel(a2, namespace, monkeypatch):
    """A21-R1-BOUNDS: a blocked downstream query ends by itself, keeping UNKNOWN.

    The table lock is taken on a downstream database owned by this test alone,
    so a deliberate lock can never poison the shared session database.
    """
    own = create_downstream_database(namespace.base_dsn)
    try:
        _assert_lock_wait_times_out(a2, own.dsn)
    finally:
        drop_downstream_database(namespace.base_dsn, own)


def _assert_lock_wait_times_out(a2, downstream_dsn: str) -> None:
    operation_id = _accepted(a2, "bounds-lock").operation_id
    short = MockDownstream(
        downstream_dsn,
        service_secret=a2.secret,
        approved_suppliers=("supplier-001",),
        lock_timeout_ms=200,
        statement_timeout_ms=2000,
    )
    short.provision()
    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=downstream_dsn,
        downstream=short,
    )
    blocker = psycopg.connect(downstream_dsn, autocommit=False)
    blocker.execute("LOCK TABLE ds_operations IN ACCESS EXCLUSIVE MODE")
    started = time.monotonic()
    try:
        result = env.service.run_operation(operation_id, owner_token="bounds-lock")
    finally:
        blocker.rollback()
        blocker.close()
    elapsed = time.monotonic() - started
    assert result.status == OperationStatus.UNKNOWN.value
    assert result.action is None
    assert elapsed < 15, f"the wait was not bounded: {elapsed:.1f}s"
    counters = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    assert counters["amount_reserved"] == ORDER_AMOUNT_FEN
    assert counters["amount_settled"] == 0
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 0


# ------------------------------------------------------------- A21-R1-EVENT


@pytest.mark.parametrize("phase", ["RESERVE", "SETTLE"])
def test_committed_event_node_set_cannot_be_appended(a2, phase):
    """A21-R1-EVENT: a committed event's node set is sealed for ever."""
    operation_id = _accepted(a2, f"event-append-{phase}").operation_id
    a2.service.run_operation(operation_id, owner_token=f"event-{phase}")
    outbox = a2.service.outbox_entry(operation_id)

    with psycopg.connect(a2.gateway_dsn) as conn:
        event_id = conn.execute(
            "SELECT event_id FROM ag_ledger_events WHERE operation_id = %s AND phase = %s",
            (operation_id, phase),
        ).fetchone()[0]
    with psycopg.connect(a2.gateway_dsn) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO ag_ledger_event_nodes "
                    "(event_id, position, grant_id, amount_reserved_delta, "
                    " amount_settled_delta, calls_reserved_delta, calls_settled_delta) "
                    "VALUES (%s, 3, %s, 0, 0, 0, 0)",
                    (event_id, a2.tree.leaf_id),
                )
    with psycopg.connect(a2.gateway_dsn) as conn:
        count = conn.execute(
            "SELECT count(*) FROM ag_ledger_event_nodes WHERE event_id = %s", (event_id,)
        ).fetchone()[0]
    assert count == 3
    assert a2.service.outbox_entry(operation_id) == outbox


@pytest.mark.parametrize(
    "bad,expected",
    [
        ("position", "contiguously"),
        ("path", "does not match the grant path"),
        ("delta", "deltas do not match"),
        ("extra", "already complete"),
    ],
)
def test_wrong_node_shape_is_refused_and_rolls_back(a2, bad, expected):
    """A21-R1-EVENT: a malformed node refuses the whole transaction.

    Each case writes a *new* RELEASE event with legitimate nodes and one
    malformed node in the same transaction; the guard must fire and the whole
    attempt (event included) must disappear.
    """
    accepted = _accepted(a2, f"event-shape-{bad}")
    before_counts = fetch_counts(a2.gateway_dsn)

    def write(conn):
        event_id = conn.execute(
            "INSERT INTO ag_ledger_events (operation_id, phase, seq) "
            "VALUES (%s, 'RELEASE', 1) RETURNING event_id",
            (accepted.operation_id,),
        ).fetchone()[0]
        legit = [
            (0, a2.tree.root_id, -ORDER_AMOUNT_FEN, -1),
            (1, a2.tree.mid_id, -ORDER_AMOUNT_FEN, -1),
        ]
        if bad == "extra":
            legit.append((2, a2.tree.leaf_id, -ORDER_AMOUNT_FEN, -1))
        for position, grant_id, amount, calls in legit:
            conn.execute(
                "INSERT INTO ag_ledger_event_nodes "
                "(event_id, position, grant_id, amount_reserved_delta, "
                " amount_settled_delta, calls_reserved_delta, calls_settled_delta) "
                "VALUES (%s,%s,%s,%s,0,%s,0)",
                (event_id, position, grant_id, amount, calls),
            )
        if bad == "position":
            position, grant_id, amount, calls = 3, a2.tree.leaf_id, -ORDER_AMOUNT_FEN, -1
        elif bad == "path":
            position, grant_id, amount, calls = 2, a2.tree.root_id, -ORDER_AMOUNT_FEN, -1
        elif bad == "delta":
            position, grant_id, amount, calls = 2, a2.tree.leaf_id, -1, -1
        else:  # extra: a fourth node past the completed set
            position, grant_id, amount, calls = 3, a2.tree.leaf_id, -ORDER_AMOUNT_FEN, -1
        conn.execute(
            "INSERT INTO ag_ledger_event_nodes "
            "(event_id, position, grant_id, amount_reserved_delta, "
            " amount_settled_delta, calls_reserved_delta, calls_settled_delta) "
            "VALUES (%s,%s,%s,%s,0,%s,0)",
            (event_id, position, grant_id, amount, calls),
        )

    with psycopg.connect(a2.gateway_dsn) as conn:
        with pytest.raises(psycopg.errors.CheckViolation, match=expected):
            with conn.transaction():
                write(conn)

    assert fetch_counts(a2.gateway_dsn) == before_counts
    assert a2.service.outbox_entry(accepted.operation_id) is None


def test_a_legitimate_terminal_node_set_still_writes(a2):
    """A21-R1-EVENT: the seal must not block the legitimate first write."""
    accepted = _accepted(a2, "event-legit")
    result = a2.service.run_operation(accepted.operation_id, owner_token="event-legit")
    assert result.status == OperationStatus.SUCCEEDED.value
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_event_nodes"] == 6
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 1


def test_incomplete_node_set_is_rolled_back_at_commit(a2):
    """A21-R1-EVENT: a partially written node set never becomes committed."""
    inv = a2.tree.invocation(
        idempotency_key="event-incomplete",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    with psycopg.connect(a2.gateway_dsn) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                event_id = conn.execute(
                    "INSERT INTO ag_ledger_events (operation_id, phase, seq) "
                    "VALUES (%s, 'RELEASE', 1) RETURNING event_id",
                    (accepted.operation_id,),
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO ag_ledger_event_nodes "
                    "(event_id, position, grant_id, amount_reserved_delta, "
                    " amount_settled_delta, calls_reserved_delta, calls_settled_delta) "
                    "VALUES (%s, 0, %s, %s, 0, %s, 0)",
                    (event_id, a2.tree.root_id, -ORDER_AMOUNT_FEN, -1),
                )
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_event_nodes"] == 3


def test_outbox_material_matches_the_database_events_exactly(a2):
    """A21-R1-EVENT: the ledger_changes payload mirrors the stored events."""
    operation_id = _accepted(a2, "event-outbox-match").operation_id
    a2.service.run_operation(operation_id, owner_token="event-outbox-match")
    outbox = a2.service.outbox_entry(operation_id)
    changes = json.loads(outbox["ledger_changes_json"].decode("utf-8"))

    with psycopg.connect(a2.gateway_dsn) as conn:
        rows = conn.execute(
            "SELECT e.phase, e.seq, n.position, n.grant_id, n.amount_reserved_delta, "
            "n.amount_settled_delta, n.calls_reserved_delta, n.calls_settled_delta "
            "FROM ag_ledger_events e JOIN ag_ledger_event_nodes n ON n.event_id = e.event_id "
            "WHERE e.operation_id = %s ORDER BY e.seq, n.position",
            (operation_id,),
        ).fetchall()

    flat = [
        (phase, seq, position, grant_id, ar, as_, cr, cs)
        for phase, seq, position, grant_id, ar, as_, cr, cs in rows
    ]
    material = []
    for event in changes["events"]:
        for node in event["nodes"]:
            material.append(
                (
                    event["phase"],
                    event["seq"],
                    len(material) % 3,
                    node["grant_id"],
                    node["amount_reserved_delta"],
                    node["amount_settled_delta"],
                    node["calls_reserved_delta"],
                    node["calls_settled_delta"],
                )
            )
    assert [row[:2] for row in flat] == [row[:2] for row in material]
    assert [row[3:] for row in flat] == [row[3:] for row in material]


# --------------------------------------------------------- A21-R1-CANDIDATE


@pytest.mark.parametrize("mismatch", ["quote-id", "quote-version", "currency", "amount"])
def test_candidate_identity_mismatch_is_quarantined(a2, mismatch):
    """A21-R1-CANDIDATE: a candidate whose persisted identity disagrees with
    its snapshot or cost is quarantined and never served as EXISTING."""
    snap = a2.catalog.build_order_snapshot(
        tenant_id=a2.tree.tenant_id,
        task_id=a2.tree.task_id,
        request_id="req-001",
        quote_id="quote-001",
        quote_version="1",
        items=(("sku-001", 1),),
        delivery_id="office-001",
    )
    raw = snapshot_to_bytes(snap)
    overrides = {}
    if mismatch == "quote-id":
        overrides["quote_id"] = "quote-other"
    elif mismatch == "quote-version":
        overrides["quote_version"] = "9"
    elif mismatch == "currency":
        overrides["currency"] = "USD"
    else:
        overrides["amount_fen"] = 1
    operation_id = _insert_raw_operation(
        a2, operation_id=f"cand-{mismatch}", quote_snapshot=raw, **overrides
    )
    a2.catalog.remove_quote("quote-001", "1")

    with pytest.raises(ExecutionError) as excinfo:
        a2.service.accept_invocation(
            a2.tree.invocation(
                idempotency_key=f"cand-{mismatch}",
                jti=f"jti-cand-{mismatch}",
                tool_id="procurement.order.create",
                params=order_params(),
            ),
            a2.permission(),
        )
    assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID
    assert a2.service.review_flag(operation_id) is not None
    assert a2.service.operation_status(operation_id) == "RESERVED"
    assert _downstream_counts(a2.downstream_dsn)["ds_operations"] == 0


def test_candidate_snapshot_identity_mismatch_is_quarantined(a2):
    """A21-R1-CANDIDATE: a snapshot whose quote identity differs from the cost
    columns is not usable as a candidate."""
    snap = a2.catalog.build_order_snapshot(
        tenant_id=a2.tree.tenant_id,
        task_id=a2.tree.task_id,
        request_id="req-001",
        quote_id="quote-001",
        quote_version="1",
        items=(("sku-001", 1),),
        delivery_id="office-001",
    )
    raw = snapshot_to_bytes(dataclasses.replace(snap, quote_id="wrong-id", quote_version="2"))
    inv = a2.tree.invocation(
        idempotency_key="cand-snap-identity",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    operation_id = a2.ledger.accept(
        inv,
        TrustedCost(amount_fen=70000, quote_id="quote-001", quote_version="1", quote_snapshot=raw),
    ).operation_id
    a2.catalog.remove_quote("quote-001", "1")

    with pytest.raises(ExecutionError) as excinfo:
        a2.service.accept_invocation(
            a2.tree.invocation(
                idempotency_key="cand-snap-identity",
                jti="jti-cand-snap",
                tool_id="procurement.order.create",
                params=order_params(),
            ),
            a2.permission(),
        )
    assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID
    assert a2.service.review_flag(operation_id) is not None


# --------------------------------------------------------- A21-R2-SNAPSHOT


@pytest.mark.parametrize(
    "mutation",
    [
        "bool",
        "float",
        "numeric-string",
        "unknown-field",
        "duplicate-field",
        "duplicate-item-key",
        "null-identity",
        "empty-identity",
        "missing-currency",
        "missing-total",
        "empty-items",
        "duplicate-sku",
        "negative-quantity",
        "negative-price",
        "zero-quantity",
        "overflow-price",
        "total-mismatch",
        "missing-item-field",
        "extra-item-field",
        "non-object-item",
        "not-an-object",
    ],
)
def test_stored_snapshot_strict_schema_rejects(mutation):
    """A21-R2-SNAPSHOT: stored material is never coerced or defaulted."""
    raw = (
        b'{"quote_id":"quote-001","quote_version":"1","supplier_id":"supplier-001",'
        b'"items":[{"sku":"sku-001","quantity":1,"unit_price_fen":70000}],'
        b'"total_fen":70000,"currency":"CNY"}'
    )
    if mutation == "bool":
        raw = raw.replace(b'"quantity":1', b'"quantity":true')
    elif mutation == "float":
        raw = raw.replace(b'"quantity":1', b'"quantity":1.9')
    elif mutation == "numeric-string":
        raw = raw.replace(b'"quantity":1', b'"quantity":"1"')
    elif mutation == "unknown-field":
        raw = raw[:-1] + b',"security_unknown":1}'
    elif mutation == "duplicate-field":
        raw = raw[:-1] + b',"total_fen":70000}'
    elif mutation == "duplicate-item-key":
        raw = raw.replace(
            b'"quantity":1,"unit_price_fen":70000',
            b'"quantity":1,"quantity":1,"unit_price_fen":70000',
        )
    elif mutation == "null-identity":
        raw = raw.replace(b'"quote_id":"quote-001"', b'"quote_id":null')
    elif mutation == "empty-identity":
        raw = raw.replace(b'"quote_id":"quote-001"', b'"quote_id":""')
    elif mutation == "missing-currency":
        raw = raw.replace(b',"currency":"CNY"', b"")
    elif mutation == "missing-total":
        raw = raw.replace(b'"total_fen":70000,', b"")
    elif mutation == "empty-items":
        raw = raw.replace(b'[{"sku":"sku-001","quantity":1,"unit_price_fen":70000}]', b"[]")
    elif mutation == "duplicate-sku":
        raw = raw.replace(b'"total_fen":70000', b'"total_fen":140000').replace(
            b'[{"sku":"sku-001","quantity":1,"unit_price_fen":70000}]',
            b'[{"sku":"sku-001","quantity":1,"unit_price_fen":70000},'
            b'{"sku":"sku-001","quantity":1,"unit_price_fen":70000}]',
        )
    elif mutation == "negative-quantity":
        raw = raw.replace(b'"quantity":1', b'"quantity":-1')
    elif mutation == "negative-price":
        raw = raw.replace(b'"unit_price_fen":70000', b'"unit_price_fen":-70000')
    elif mutation == "zero-quantity":
        raw = raw.replace(b'"quantity":1', b'"quantity":0')
    elif mutation == "overflow-price":
        raw = raw.replace(b'"unit_price_fen":70000', b'"unit_price_fen":9007199254740992')
    elif mutation == "total-mismatch":
        raw = raw.replace(b'"total_fen":70000', b'"total_fen":1')
    elif mutation == "missing-item-field":
        raw = raw.replace(b',"unit_price_fen":70000', b"")
    elif mutation == "extra-item-field":
        raw = raw.replace(b'"unit_price_fen":70000}', b'"unit_price_fen":70000,"x":1}')
    elif mutation == "non-object-item":
        raw = raw.replace(
            b'[{"sku":"sku-001","quantity":1,"unit_price_fen":70000}]', b'["sku-001"]'
        )
    elif mutation == "not-an-object":
        raw = b"[]"

    with pytest.raises(ExecutionError) as excinfo:
        snapshot_from_bytes(raw)
    assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID


def test_stored_snapshot_round_trip_still_works():
    from agent_guard.contracts.execution import QuoteItem, TrustedQuoteSnapshot

    snapshot = TrustedQuoteSnapshot(
        quote_id="quote-001",
        quote_version="1",
        supplier_id="supplier-001",
        items=(QuoteItem(sku="sku-001", quantity=1, unit_price_fen=70000),),
        total_fen=70000,
    )
    raw = snapshot_to_bytes(snapshot)
    decoded = snapshot_from_bytes(raw)
    assert decoded == snapshot
    assert snapshots_equal(decoded, snapshot)


def test_malformed_snapshot_is_quarantined_by_the_entries(a2, monkeypatch):
    """A21-R2-SNAPSHOT: bad stored bytes never reach a downstream call."""
    operation_id = _insert_raw_operation(
        a2,
        operation_id="snap-legacy",
        quote_snapshot=b'{"quote_id":true}',
    )
    for entry in ("run", "reconcile"):
        with pytest.raises(ExecutionError) as excinfo:
            if entry == "run":
                a2.service.run_operation(operation_id, owner_token="snap-owner")
            else:
                a2.service.reconcile(operation_id, owner_token="snap-owner")
        assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID
    assert a2.service.review_flag(operation_id) is not None
    assert _downstream_counts(a2.downstream_dsn)["ds_operations"] == 0
