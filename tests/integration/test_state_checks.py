"""Dynamic-state cases P8, P9, P10, P11: validity windows, revocation, key
status, post-lock freshness, the unique-root rule and lock-ordered revocation.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from agent_guard.contracts.ledger import AcceptDisposition, ErrorCode, LedgerError
from agent_guard.ledger import provisioning as prov
from agent_guard.ledger.provisioning import TaskAlreadyInitialized
from agent_guard.ledger.service import ExecutionLedger
from tests.fixtures.dbstate import fetch_all, fetch_counters, fetch_counts
from tests.fixtures.isolation import reset_state
from tests.fixtures.state import TreeFixture, build_tree, default_window

pytestmark = pytest.mark.integration


def _revoke(dsn: str, grant_id: str) -> None:
    with psycopg.connect(dsn) as conn:
        prov.revoke_grant(conn, grant_id)


def _deactivate(dsn: str, tenant_id: str, client_id: str, kid: str) -> None:
    with psycopg.connect(dsn) as conn:
        prov.deactivate_principal(conn, tenant_id=tenant_id, client_id=client_id, kid=kid)


# ------------------------------------------------------------------- P8


def test_p8_token_expired_rejected(ledger, tree):
    now = int(time.time())
    forged = tree.invocation(token_exp=now - 1)
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(forged, tree.cost(1))
    assert excinfo.value.code is ErrorCode.EXPIRED


def test_p8_ancestor_not_yet_effective_rejected(ledger, dsn):
    """P8: an ancestor whose validity window has not opened rejects the leaf."""
    current = datetime.now(tz=timezone.utc)
    with psycopg.connect(dsn) as conn:
        tree = build_tree(
            conn,
            valid_from=current + timedelta(hours=1),
            valid_until=current + timedelta(hours=2),
        )
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(tree.invocation(), tree.cost(1))
    assert excinfo.value.code is ErrorCode.EXPIRED
    assert "not yet effective" in excinfo.value.detail
    # the root is the first node failing the window check
    assert excinfo.value.detail.endswith(tree.root_id)


def test_p8_expired_ancestor_rejected(ledger, dsn):
    """P8: an expired intermediate ancestor rejects even if the root is valid."""
    current = datetime.now(tz=timezone.utc)
    root_from = current - timedelta(hours=2)
    root_to = current + timedelta(hours=2)
    with psycopg.connect(dsn) as conn:
        for client_id, kid in (("c-plan", "k-plan"), ("c-sel", "k-sel"), ("c-exec", "k-exec")):
            prov.register_principal(conn, tenant_id="t8", client_id=client_id, kid=kid)
        prov.create_task_root(
            conn,
            tenant_id="t8",
            task_id="task8",
            grant_id="root8",
            subject="user-8",
            holder_client_id="c-plan",
            holder_kid="k-plan",
            amount_limit=100000,
            call_limit=10,
            not_before=root_from,
            expires_at=root_to,  # root stays valid
        )
        mid_from = root_from
        mid_to = current - timedelta(hours=1)  # mid expired an hour ago
        prov.create_child_grant(
            conn,
            parent_grant_id="root8",
            grant_id="mid8",
            holder_client_id="c-sel",
            holder_kid="k-sel",
            amount_limit=80000,
            call_limit=8,
            not_before=mid_from,
            expires_at=mid_to,
        )
        prov.create_child_grant(
            conn,
            parent_grant_id="mid8",
            grant_id="leaf8",
            holder_client_id="c-exec",
            holder_kid="k-exec",
            amount_limit=70000,
            call_limit=5,
            not_before=mid_from,
            expires_at=mid_to - timedelta(minutes=1),
        )
    tree = TreeFixture(
        tenant_id="t8",
        task_id="task8",
        subject="user-8",
        root_id="root8",
        mid_id="mid8",
        leaf_id="leaf8",
        planner=("c-plan", "k-plan"),
        selector=("c-sel", "k-sel"),
        executor=("c-exec", "k-exec"),
        not_before=root_from,
        expires_at=root_to,
        amount_limits=(100000, 80000, 70000),
        call_limits=(10, 8, 5),
    )
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(tree.invocation(), tree.cost(1))
    assert excinfo.value.code is ErrorCode.EXPIRED
    assert excinfo.value.detail == "grant expired: mid8"


def test_p8_revoked_ancestor_rejected(ledger, tree, dsn):
    """P8: revoking the mid ancestor rejects descendant calls."""
    _revoke(dsn, tree.mid_id)
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(tree.invocation(), tree.cost(1))
    assert excinfo.value.code is ErrorCode.REVOKED
    assert excinfo.value.detail == f"grant revoked: {tree.mid_id}"


def test_p8_deactivated_key_rejected(ledger, tree, dsn):
    """P8: deactivating the holder key rejects new calls."""
    _deactivate(dsn, tree.tenant_id, tree.executor[0], tree.executor[1])
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(tree.invocation(), tree.cost(1))
    assert excinfo.value.code is ErrorCode.HOLDER_MISMATCH


def test_p8_same_key_retry_cannot_bypass_revocation(ledger, tree, dsn):
    """P8: an idempotent retry is still checked against the current state.

    First accept commits, then the grant is revoked; the same-key retry must
    be rejected (REVOKED), not served as an idempotent hit, while the earlier
    RESERVED operation and its reservation remain untouched.
    """
    key = "purchase-p8-retry"
    first = ledger.accept(tree.invocation(idempotency_key=key), tree.cost(70000))
    assert first.disposition is AcceptDisposition.CREATED

    _revoke(dsn, tree.mid_id)

    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(tree.invocation(idempotency_key=key, jti="jti-p8-late"), tree.cost(70000))
    assert excinfo.value.code is ErrorCode.REVOKED

    assert fetch_counters(dsn, tree.leaf_id)["amount_reserved"] == 70000
    assert fetch_counts(dsn)["ag_operations"] == 1


# ------------------------------------------------------------------- P9


def test_p9_lock_wait_until_proof_expires_is_rejected(dsn, migrated, namespace):
    """P9: freshness uses the post-lock time, not the transaction start.

    One connection holds the task lock past a short proof TTL while another
    accept waits; after the lock is released the accept must still be
    rejected as stale — proving the decision used the time after lock
    acquisition.
    """
    reset_state(namespace)
    lock_held = threading.Event()
    errors: list[object] = []
    elapsed: dict[str, float] = {}

    def hold_lock() -> None:
        with psycopg.connect(dsn) as conn:
            with conn.transaction():
                conn.execute(
                    "SELECT root_grant_id FROM ag_tasks WHERE tenant_id = %s "
                    "AND task_id = %s FOR UPDATE",
                    ("t9", "task9"),
                )
                lock_held.set()
                time.sleep(4.5)  # longer than the 2s proof lifetime below

    with psycopg.connect(dsn) as conn:
        not_before, expires_at = default_window()
        prov.register_principal(conn, tenant_id="t9", client_id="c9", kid="k9")
        prov.create_task_root(
            conn,
            tenant_id="t9",
            task_id="task9",
            grant_id="root9",
            subject="user-9",
            holder_client_id="c9",
            holder_kid="k9",
            amount_limit=100000,
            call_limit=10,
            not_before=not_before,
            expires_at=expires_at,
        )
    tree = TreeFixture(
        tenant_id="t9",
        task_id="task9",
        subject="user-9",
        root_id="root9",
        mid_id="root9",
        leaf_id="root9",
        planner=("c9", "k9"),
        selector=("c9", "k9"),
        executor=("c9", "k9"),
        not_before=not_before,
        expires_at=expires_at,
        amount_limits=(100000, 100000, 100000),
        call_limits=(10, 10, 10),
    )
    # the proof is valid at call time and expired well before the lock releases
    now = int(time.time())
    invocation = tree.invocation(
        grant_id="root9",
        ancestor_ids=(),
        jti="jti-p9",
        proof_iat=now,
        proof_exp=now + 2,
        token_exp=now + 300,
    )

    def accept_when_locked() -> None:
        assert lock_held.wait(timeout=10)
        ledger = ExecutionLedger(dsn)
        started = time.monotonic()
        try:
            ledger.accept(invocation, tree.cost(1))
            errors.append("accept unexpectedly succeeded")
        except LedgerError as exc:
            errors.append(exc.code)
        elapsed["seconds"] = time.monotonic() - started

    holder = threading.Thread(target=hold_lock)
    acceptor = threading.Thread(target=accept_when_locked)
    holder.start()
    acceptor.start()
    holder.join()
    acceptor.join()

    assert errors == [ErrorCode.STALE_REQUEST], errors
    # the accept demonstrably waited for the lock, then judged on post-lock time
    assert elapsed["seconds"] >= 4.0
    assert fetch_counts(dsn)["ag_operations"] == 0


# ------------------------------------------------------------------ P10


def test_p10_revocation_commits_first_then_accept_rejects(ledger, tree, dsn):
    """P10 ordering 1: revocation committed before the accept is refused."""
    _revoke(dsn, tree.mid_id)
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(tree.invocation(), tree.cost(70000))
    assert excinfo.value.code is ErrorCode.REVOKED
    assert fetch_counts(dsn)["ag_operations"] == 0
    assert fetch_counters(dsn, tree.leaf_id)["amount_reserved"] == 0


def test_p10_accept_commits_first_then_reservation_survives(ledger, tree, dsn):
    """P10 ordering 2: an accepted reservation is not released by revocation."""
    first = ledger.accept(tree.invocation(idempotency_key="purchase-p10"), tree.cost(70000))
    assert first.disposition is AcceptDisposition.CREATED

    _revoke(dsn, tree.mid_id)

    # the existing RESERVED is preserved, not released
    for grant_id in (tree.root_id, tree.mid_id, tree.leaf_id):
        counters = fetch_counters(dsn, grant_id)
        assert counters["amount_reserved"] == 70000, grant_id
        assert counters["amount_settled"] == 0

    # subsequent calls with a new key are rejected
    with pytest.raises(LedgerError) as excinfo:
        ledger.accept(tree.invocation(idempotency_key="purchase-p10-late"), tree.cost(1))
    assert excinfo.value.code is ErrorCode.REVOKED
    assert fetch_counts(dsn)["ag_operations"] == 1


# ------------------------------------------------------------------ P11


def test_p11_concurrent_root_initialization_creates_one_root(dsn, migrated, namespace):
    """P11: two concurrent root inits for one task yield at most one root."""
    reset_state(namespace)
    results: list[object] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def init(grant_id: str) -> None:
        not_before, expires_at = default_window()
        with psycopg.connect(dsn) as conn:
            barrier.wait()
            try:
                prov.create_task_root(
                    conn,
                    tenant_id="t11",
                    task_id="task11",
                    grant_id=grant_id,
                    subject="user-11",
                    holder_client_id="c11",
                    holder_kid="k11",
                    amount_limit=100000,
                    call_limit=10,
                    not_before=not_before,
                    expires_at=expires_at,
                )
                with lock:
                    results.append(("ok", grant_id))
            except TaskAlreadyInitialized:
                with lock:
                    results.append(("dup", grant_id))

    with psycopg.connect(dsn) as conn:
        prov.register_principal(conn, tenant_id="t11", client_id="c11", kid="k11")

    threads = [
        threading.Thread(target=init, args=(grant_id,)) for grant_id in ("root11-a", "root11-b")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(kind for kind, _ in results) == ["dup", "ok"], results
    roots = fetch_all(dsn, "SELECT grant_id FROM ag_grants WHERE parent_grant_id IS NULL")
    assert len(roots) == 1
    assert fetch_counts(dsn)["ag_tasks"] == 1


def test_p11_reinit_after_revocation_keeps_balances(dsn, migrated, namespace):
    """P11: re-initializing after revocation never creates a second root and
    never clears the already-reserved budget."""
    reset_state(namespace)
    with psycopg.connect(dsn) as conn:
        tree = build_tree(conn, tenant_id="t11b", task_id="task11b")
    ledger = ExecutionLedger(dsn)
    result = ledger.accept(tree.invocation(), tree.cost(70000))
    assert result.disposition is AcceptDisposition.CREATED
    before = fetch_counters(dsn, tree.leaf_id)

    _revoke(dsn, tree.root_id)

    not_before, expires_at = default_window()
    with psycopg.connect(dsn) as conn:
        with pytest.raises(TaskAlreadyInitialized):
            prov.create_task_root(
                conn,
                tenant_id=tree.tenant_id,
                task_id=tree.task_id,
                grant_id="root-rebuilt",
                subject="user-11b",
                holder_client_id="c11b",
                holder_kid="k11b",
                amount_limit=50000,
                call_limit=1,
                not_before=not_before,
                expires_at=expires_at,
            )

    assert fetch_counts(dsn)["ag_tasks"] == 1
    roots = fetch_all(dsn, "SELECT grant_id FROM ag_grants WHERE parent_grant_id IS NULL")
    assert [row[0] for row in roots] == [tree.root_id]
    assert fetch_counters(dsn, tree.leaf_id) == before  # balances not cleared
