"""A2-P19, A2-P20 and the checkpoint-1 migration obligations OBL03/OBL05.

All of these run against real PostgreSQL scratch databases created and dropped
by this run only. The seven legacy business tables must keep their exact rows
across a legal upgrade, an illegal upgrade must change nothing at all, and
direct SQL must never rewrite intent/evidence, delete accepted facts or bypass
the phase/seq and status rules — while legitimate counter, revocation and
status updates keep working.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import psycopg
import pytest

from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode, OperationStatus
from agent_guard.contracts.ledger import AcceptDisposition
from agent_guard.execution import store as exec_store
from agent_guard.ledger import applied_versions, apply_migrations
from agent_guard.ledger.migrate import DEFAULT_MIGRATIONS_DIR
from agent_guard.ledger.provisioning import revoke_grant
from agent_guard.ledger.service import ExecutionLedger
from tests.fixtures.dbstate import fetch_all, fetch_counters, fetch_counts, fetch_one
from tests.fixtures.execution import order_params, read_params
from tests.fixtures.isolation import (
    ScratchDatabase,
    create_scratch_database,
    drop_scratch_database,
)
from tests.fixtures.state import build_tree

pytestmark = pytest.mark.integration

#: Deterministic full-row read order for the seven legacy business tables.
_BUSINESS_TABLE_ORDER = {
    "ag_tasks": "tenant_id, task_id",
    "ag_principals": "tenant_id, client_id, kid",
    "ag_grants": "grant_id",
    "ag_operations": "operation_id",
    "ag_proofs": "holder_kid, purpose, endpoint, proof_jti",
    "ag_ledger_events": "event_id",
    "ag_ledger_event_nodes": "event_id, position",
}


def expected_versions(migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> list[str]:
    return sorted(p.name.split("_", 1)[0] for p in migrations_dir.glob("*.sql"))


def snapshot_business_tables(dsn: str) -> dict[str, list[tuple]]:
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        return {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
            for table, order in _BUSINESS_TABLE_ORDER.items()
        }


def assert_tables_unchanged(before: dict, after: dict) -> None:
    assert set(before) == set(after)
    for table in before:
        assert before[table] == after[table], f"{table} changed across the upgrade"


@pytest.fixture()
def scratch(namespace) -> ScratchDatabase:
    created = create_scratch_database(namespace.base_dsn)
    try:
        yield created
    finally:
        drop_scratch_database(namespace.base_dsn, created)


def _only(migrations_dir: Path, names: list[str]) -> Path:
    subset = migrations_dir.parent / f"subset-{secrets.token_hex(6)}"
    subset.mkdir()
    for name in names:
        (subset / name).write_bytes((DEFAULT_MIGRATIONS_DIR / name).read_bytes())
    return subset


def _seed_nonzero_state(dsn: str) -> None:
    """A real 70000/1 accept plus a real revocation and real evidence rows."""
    with psycopg.connect(dsn) as conn:
        tree = build_tree(conn)
    ledger = ExecutionLedger(dsn)
    result = ledger.accept(
        tree.invocation(
            idempotency_key="seed-op",
            jti="jti-seed",
            token_digest="tok-seed",
            proof_digest="proof-seed",
            intent_digest="intent-seed",
            evidence_ref="evidence-seed",
        ),
        tree.cost(amount_fen=70000, quote_snapshot=b"legacy-snapshot-bytes"),
    )
    assert result.disposition is AcceptDisposition.CREATED
    with psycopg.connect(dsn) as conn:
        revoke_grant(conn, tree.mid_id)
    return tree


# ------------------------------------------------------------------- P19


def test_p19_upgrade_from_001_preserves_nonzero_seven_tables(scratch):
    """P19: 001 -> latest keeps every row of the seven legacy tables intact."""
    only_001 = _only(DEFAULT_MIGRATIONS_DIR, ["001_init.sql"])
    try:
        with psycopg.connect(scratch.dsn) as conn:
            assert apply_migrations(conn, only_001) == ["001"]
        tree = _seed_nonzero_state(scratch.dsn)

        before = snapshot_business_tables(scratch.dsn)
        assert all(before[table] for table in _BUSINESS_TABLE_ORDER)
        counters = fetch_counters(scratch.dsn, tree.root_id)
        assert counters["amount_reserved"] == 70000
        assert counters["calls_reserved"] == 1

        with psycopg.connect(scratch.dsn) as conn:
            applied = apply_migrations(conn)
            assert applied == [v for v in expected_versions() if v != "001"]
            assert set(applied_versions(conn)) == set(expected_versions())

        after = snapshot_business_tables(scratch.dsn)
        assert_tables_unchanged(before, after)
    finally:
        import shutil

        shutil.rmtree(only_001, ignore_errors=True)


def test_p19_upgrade_from_003_preserves_nonzero_seven_tables(scratch):
    """P19: 003 -> 004 is the exact path the A2.1 schema change takes."""
    only_003 = _only(
        DEFAULT_MIGRATIONS_DIR,
        ["001_init.sql", "002_root_invariants.sql", "003_root_delete_guard.sql"],
    )
    try:
        with psycopg.connect(scratch.dsn) as conn:
            assert apply_migrations(conn, only_003) == ["001", "002", "003"]
        tree = _seed_nonzero_state(scratch.dsn)

        before = snapshot_business_tables(scratch.dsn)
        with psycopg.connect(scratch.dsn) as conn:
            applied = apply_migrations(conn)
            assert applied == ["004", "005", "006"]

        after = snapshot_business_tables(scratch.dsn)
        assert_tables_unchanged(before, after)
        assert fetch_counters(scratch.dsn, tree.root_id)["amount_reserved"] == 70000
        assert fetch_one(
            scratch.dsn, "SELECT revoked FROM ag_grants WHERE grant_id = %s", (tree.mid_id,)
        ) == (True,)
        # the sidecar exists but is empty: the legacy rows are untouched
        assert fetch_counts(scratch.dsn)["ag_operation_review_flags"] == 0
    finally:
        import shutil

        shutil.rmtree(only_003, ignore_errors=True)


def test_p19_illegal_upgrade_changes_nothing(scratch):
    """P19: a legacy event violating the phase/seq rule aborts the upgrade."""
    only_003 = _only(
        DEFAULT_MIGRATIONS_DIR,
        ["001_init.sql", "002_root_invariants.sql", "003_root_delete_guard.sql"],
    )
    try:
        with psycopg.connect(scratch.dsn) as conn:
            apply_migrations(conn, only_003)
        tree = _seed_nonzero_state(scratch.dsn)
        operation_id = fetch_one(scratch.dsn, "SELECT operation_id FROM ag_operations")[0]

        # corrupt legacy row that 004 must refuse to accept
        with psycopg.connect(scratch.dsn) as conn:
            with conn.transaction():
                conn.execute(
                    "INSERT INTO ag_ledger_events (operation_id, phase, seq) "
                    "VALUES (%s,'RESERVE',1)",
                    (operation_id,),
                )

        before = snapshot_business_tables(scratch.dsn)
        registry_before = fetch_all(
            scratch.dsn,
            "SELECT version, filename, checksum FROM ag_schema_migrations ORDER BY version",
        )

        with psycopg.connect(scratch.dsn) as conn:
            with pytest.raises(psycopg.errors.CheckViolation):
                apply_migrations(conn)

        after = snapshot_business_tables(scratch.dsn)
        assert_tables_unchanged(before, after)
        registry_after = fetch_all(
            scratch.dsn,
            "SELECT version, filename, checksum FROM ag_schema_migrations ORDER BY version",
        )
        assert registry_after == registry_before
        assert [row[0] for row in registry_after] == ["001", "002", "003"]
        assert fetch_counters(scratch.dsn, tree.root_id)["amount_reserved"] == 70000
    finally:
        import shutil

        shutil.rmtree(only_003, ignore_errors=True)


def test_p19_repeated_migration_is_a_no_op(scratch):
    """P19: re-running the full directory applies nothing and changes nothing."""
    with psycopg.connect(scratch.dsn) as conn:
        assert apply_migrations(conn) == expected_versions()
    tree = _seed_nonzero_state(scratch.dsn)
    before = snapshot_business_tables(scratch.dsn)

    with psycopg.connect(scratch.dsn) as conn:
        assert apply_migrations(conn) == []
        assert apply_migrations(conn) == []
        assert set(applied_versions(conn)) == set(expected_versions())

    assert_tables_unchanged(before, snapshot_business_tables(scratch.dsn))
    assert fetch_counters(scratch.dsn, tree.root_id)["amount_reserved"] == 70000


# ------------------------------------------------------ legacy material


def test_p19_legacy_material_is_quarantined_and_never_backfilled(a2):
    """P19/OBL03: insufficient accepted material is isolated, the budget stays
    reserved and nothing is executed from a replacement current quote."""
    # an operation accepted with unusable snapshot bytes (a legacy row shape)
    with psycopg.connect(a2.gateway_dsn) as conn:
        legacy = a2.tree.invocation(
            idempotency_key="legacy-material",
            jti="jti-legacy",
            tool_id="procurement.order.create",
            params=order_params(),
        )
    from agent_guard.contracts.ledger import TrustedCost

    result = a2.ledger.accept(
        legacy,
        TrustedCost(
            amount_fen=70000,
            calls=1,
            currency="CNY",
            quote_id="quote-001",
            quote_version="1",
            quote_snapshot=b"not-a-valid-snapshot",
        ),
    )
    assert result.disposition is AcceptDisposition.CREATED

    assert a2.service.quarantine_if_insufficient(result.operation_id) is True
    flag = a2.service.review_flag(result.operation_id)
    assert flag is not None
    assert flag["reason"] == "insufficient accepted material"
    assert flag["detail"]["code"] == ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID.value

    with pytest.raises(ExecutionError) as excinfo:
        a2.service.run_operation(result.operation_id, owner_token="legacy-worker")
    assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID

    # the reserved budget is preserved and never re-priced from a current quote
    counters = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    assert counters["amount_reserved"] == 70000
    assert counters["amount_settled"] == 0
    assert counters["calls_reserved"] == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 1
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 0
    with psycopg.connect(a2.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_operations").fetchone()[0] == 0

    # the sidecar does not touch the legacy tables
    rows = fetch_one(
        a2.gateway_dsn,
        "SELECT quote_snapshot FROM ag_operations WHERE operation_id = %s",
        (result.operation_id,),
    )
    assert rows[0] == b"not-a-valid-snapshot"


def test_p19_missing_evidence_is_quarantined_too(a2):
    """P19/OBL03: incomplete first-accept evidence is isolated automatically.

    The row is written through the legitimate store helpers so the 005 node-set
    seal accepts it; only the *evidence* is blank, which is exactly the legacy
    shape that must be quarantined instead of executed.
    """
    from agent_guard.ledger import store as ls

    with psycopg.connect(a2.gateway_dsn) as conn:
        with conn.transaction():
            ls.insert_operation(
                conn,
                operation_id="legacy-no-evidence",
                tenant_id=a2.tree.tenant_id,
                task_id=a2.tree.task_id,
                tool_id="procurement.request.read",
                idempotency_key="legacy-no-evidence",
                grant_id=a2.tree.leaf_id,
                holder_client_id=a2.tree.executor[0],
                holder_kid=a2.tree.executor[1],
                tool_version="1",
                canonical_params=read_params(),
                currency="CNY",
                amount_fen=0,
                calls=1,
                quote_id=None,
                quote_version=None,
                quote_snapshot=None,
                token_digest="",  # the legacy gap
                proof_digest="proof",
                intent_digest="intent",
                evidence_ref="evidence",
            )
            nodes = [a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id]
            for grant_id in nodes:
                ls.apply_reservation(conn, grant_id, 0, 1)
            ls.insert_reserve_event(
                conn,
                operation_id="legacy-no-evidence",
                seq=0,
                nodes=[(i, g, 0, 1) for i, g in enumerate(nodes)],
            )

    assert a2.service.quarantine_if_insufficient("legacy-no-evidence") is True
    assert a2.service.review_flag("legacy-no-evidence") is not None
    # every internal entry refuses it automatically, not only the helper
    for entry in ("run", "reconcile"):
        with pytest.raises(ExecutionError) as excinfo:
            if entry == "run":
                a2.service.run_operation("legacy-no-evidence", owner_token="legacy-owner")
            else:
                a2.service.reconcile("legacy-no-evidence", owner_token="legacy-owner")
        assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID
    assert a2.service.review_flag("legacy-no-evidence") is not None
    counters = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    assert counters["amount_reserved"] == 0
    assert counters["calls_reserved"] == 1
    with psycopg.connect(a2.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_operations").fetchone()[0] == 0


# ------------------------------------------------------------------- P20


def test_p20_intent_cost_and_evidence_cannot_be_rewritten_by_sql(a2):
    """P20: direct SQL cannot change the accepted intent, cost or evidence."""
    inv = a2.tree.invocation(
        idempotency_key="p20-immutable",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    before = fetch_one(
        a2.gateway_dsn,
        "SELECT canonical_params, amount_fen, token_digest, proof_digest, intent_digest, "
        "evidence_ref, quote_snapshot FROM ag_operations WHERE operation_id = %s",
        (accepted.operation_id,),
    )

    for column, value in (
        ("canonical_params", b'{"tampered":1}'),
        ("amount_fen", 1),
        ("token_digest", "tampered"),
        ("proof_digest", "tampered"),
        ("intent_digest", "tampered"),
        ("evidence_ref", "tampered"),
        ("quote_snapshot", b"tampered"),
        ("tool_id", "notification.template.send"),
        ("grant_id", a2.tree.mid_id),
        ("accepted_at", "2000-01-01T00:00:00Z"),
    ):
        with psycopg.connect(a2.gateway_dsn) as conn:
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    conn.execute(
                        f"UPDATE ag_operations SET {column} = %s WHERE operation_id = %s",
                        (value, accepted.operation_id),
                    )

    after = fetch_one(
        a2.gateway_dsn,
        "SELECT canonical_params, amount_fen, token_digest, proof_digest, intent_digest, "
        "evidence_ref, quote_snapshot FROM ag_operations WHERE operation_id = %s",
        (accepted.operation_id,),
    )
    assert after == before


def test_p20_accepted_operations_and_paths_cannot_be_deleted(a2):
    """P20/OBL03: an accepted operation and its path survive every delete order."""
    inv = a2.tree.invocation(
        idempotency_key="p20-delete",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    with psycopg.connect(a2.gateway_dsn) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute(
                    "DELETE FROM ag_operations WHERE operation_id = %s", (accepted.operation_id,)
                )

    # deleting any node of the accepted path is refused
    for grant_id in (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id):
        with psycopg.connect(a2.gateway_dsn) as conn:
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    conn.execute("DELETE FROM ag_grants WHERE grant_id = %s", (grant_id,))

    # "delete the events first, then the operation" is refused at step one
    with psycopg.connect(a2.gateway_dsn) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute(
                    "DELETE FROM ag_ledger_event_nodes WHERE event_id IN "
                    "(SELECT event_id FROM ag_ledger_events WHERE operation_id = %s)",
                    (accepted.operation_id,),
                )
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute(
                    "DELETE FROM ag_ledger_events WHERE operation_id = %s",
                    (accepted.operation_id,),
                )

    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_event_nodes"] == 3
    assert fetch_counts(a2.gateway_dsn)["ag_grants"] == 3


def test_p20_events_and_nodes_cannot_be_updated_or_deleted(a2):
    """P20/OBL05: ledger events and nodes are permanently immutable."""
    inv = a2.tree.invocation(
        idempotency_key="p20-events",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    a2.service.run_operation(accepted.operation_id, owner_token="p20-events")

    for sql, params in (
        (
            "UPDATE ag_ledger_events SET phase = %s WHERE operation_id = %s",
            ("RELEASE", accepted.operation_id),
        ),
        ("UPDATE ag_ledger_events SET seq = 7 WHERE operation_id = %s", (accepted.operation_id,)),
        ("DELETE FROM ag_ledger_events WHERE operation_id = %s", (accepted.operation_id,)),
        (
            "UPDATE ag_ledger_event_nodes SET amount_reserved_delta = 0 WHERE grant_id = %s",
            (a2.tree.root_id,),
        ),
        ("DELETE FROM ag_ledger_event_nodes WHERE grant_id = %s", (a2.tree.root_id,)),
    ):
        with psycopg.connect(a2.gateway_dsn) as conn:
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    conn.execute(sql, params)

    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 2
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_event_nodes"] == 6


def test_p20_phase_seq_binding_and_double_terminal_are_refused(a2):
    """P20: the RESERVE/0 and terminal/1 rule cannot be bypassed by raw SQL."""
    inv = a2.tree.invocation(
        idempotency_key="p20-phase-seq",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    for phase, seq in (("RESERVE", 1), ("SETTLE", 0), ("RELEASE", 0), ("SETTLE", 2)):
        with psycopg.connect(a2.gateway_dsn) as conn:
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    conn.execute(
                        "INSERT INTO ag_ledger_events (operation_id, phase, seq) VALUES (%s,%s,%s)",
                        (accepted.operation_id, phase, seq),
                    )

    a2.service.run_operation(accepted.operation_id, owner_token="p20-terminal")

    # a second terminal event is refused by the unique (operation_id, seq) rule
    with psycopg.connect(a2.gateway_dsn) as conn:
        with pytest.raises(psycopg.errors.UniqueViolation):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO ag_ledger_events (operation_id, phase, seq) "
                    "VALUES (%s,'RELEASE',1)",
                    (accepted.operation_id,),
                )
        # and the status can never move out of a terminal state
        for status in ("FAILED", "UNKNOWN", "EXECUTING", "RESERVED"):
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    conn.execute(
                        "UPDATE ag_operations SET status = %s WHERE operation_id = %s",
                        (status, accepted.operation_id),
                    )
        # even rewriting the same terminal value is refused
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute(
                    "UPDATE ag_operations SET status = 'SUCCEEDED' WHERE operation_id = %s",
                    (accepted.operation_id,),
                )

    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 2


def test_p20_illegal_status_transitions_are_refused(a2):
    """P20: only the documented state machine transitions are accepted."""
    inv = a2.tree.invocation(
        idempotency_key="p20-transitions",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    operation_id = accepted.operation_id

    with psycopg.connect(a2.gateway_dsn) as conn:
        # RESERVED may only become EXECUTING
        for status in ("SUCCEEDED", "FAILED", "UNKNOWN"):
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    conn.execute(
                        "UPDATE ag_operations SET status = %s WHERE operation_id = %s",
                        (status, operation_id),
                    )
        # RESERVED -> EXECUTING is legal
        with conn.transaction():
            conn.execute(
                "UPDATE ag_operations SET status = 'EXECUTING' WHERE operation_id = %s",
                (operation_id,),
            )
        # EXECUTING may not go back to RESERVED
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute(
                    "UPDATE ag_operations SET status = 'RESERVED' WHERE operation_id = %s",
                    (operation_id,),
                )
        # UNKNOWN -> UNKNOWN is a documented no-op and stays allowed
        with conn.transaction():
            conn.execute(
                "UPDATE ag_operations SET status = 'UNKNOWN' WHERE operation_id = %s",
                (operation_id,),
            )
        with conn.transaction():
            conn.execute(
                "UPDATE ag_operations SET status = 'UNKNOWN' WHERE operation_id = %s",
                (operation_id,),
            )

    assert a2.service.operation_status(operation_id) == "UNKNOWN"


def test_p20_legitimate_updates_still_work(a2):
    """P20: counters, revocation and legal status moves remain available."""
    from agent_guard.ledger import provisioning as prov

    inv = a2.tree.invocation(
        idempotency_key="p20-legit",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    with psycopg.connect(a2.gateway_dsn) as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE ag_grants SET amount_reserved = amount_reserved WHERE grant_id = %s",
                (a2.tree.root_id,),
            )
        prov.revoke_grant(conn, a2.tree.mid_id)
        with conn.transaction():
            conn.execute(
                "UPDATE ag_operations SET status = 'EXECUTING' WHERE operation_id = %s",
                (accepted.operation_id,),
            )

    assert fetch_one(
        a2.gateway_dsn, "SELECT revoked FROM ag_grants WHERE grant_id = %s", (a2.tree.mid_id,)
    ) == (True,)
    assert a2.service.operation_status(accepted.operation_id) == "EXECUTING"

    # and the terminal path still works afterwards
    result = a2.service.run_operation(accepted.operation_id, owner_token="p20-legit-run")
    assert result.status == OperationStatus.SUCCEEDED.value
    counters = fetch_counters(a2.gateway_dsn, a2.tree.leaf_id)
    assert counters["amount_settled"] == 70000


def test_p20_unreferenced_non_root_grant_delete_stays_possible(a2):
    """P20: only accepted paths are protected; ordinary nodes keep old semantics."""
    from agent_guard.ledger import provisioning as prov

    not_before, expires_at = a2.tree.not_before, a2.tree.expires_at
    with psycopg.connect(a2.gateway_dsn) as conn:
        prov.create_child_grant(
            conn,
            parent_grant_id=a2.tree.root_id,
            grant_id="p20-unused-child",
            holder_client_id=a2.tree.planner[0],
            holder_kid=a2.tree.planner[1],
            amount_limit=1,
            call_limit=1,
            not_before=not_before,
            expires_at=expires_at,
        )
        with conn.transaction():
            conn.execute("DELETE FROM ag_grants WHERE grant_id = 'p20-unused-child'")
    assert fetch_one(
        a2.gateway_dsn, "SELECT count(*) FROM ag_grants WHERE grant_id = 'p20-unused-child'"
    ) == (0,)


# ------------------------------------------------------------------ OBL05


def test_obl05_sidecar_and_lease_do_not_change_legacy_rows(a2):
    """OBL05: the 004 structures are additive; the legacy rows stay identical."""
    inv = a2.tree.invocation(
        idempotency_key="obl05-sidecar",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    before = snapshot_business_tables(a2.gateway_dsn)

    with psycopg.connect(a2.gateway_dsn, autocommit=True) as conn:
        exec_store.flag_operation(
            conn, operation_id=accepted.operation_id, reason="test", detail={"a": 1}
        )

    after = snapshot_business_tables(a2.gateway_dsn)
    assert_tables_unchanged(before, after)
    assert fetch_counts(a2.gateway_dsn)["ag_operation_review_flags"] == 1
    # the seven legacy tables never gained an isolation column
    columns = fetch_all(
        a2.gateway_dsn,
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_name IN ('ag_tasks','ag_principals','ag_grants','ag_operations',"
        "'ag_proofs','ag_ledger_events','ag_ledger_event_nodes') "
        "AND (column_name LIKE %s OR column_name LIKE %s)",
        ("%quarantine%", "%review%"),
    )
    assert columns == []


def test_obl05_test_owned_cleanup_still_works(a2, namespace):
    """OBL05: run-owned TRUNCATE cleanup is unaffected by the row-level guards."""
    inv = a2.tree.invocation(
        idempotency_key="obl05-cleanup",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    a2.service.run_operation(accepted.operation_id, owner_token="obl05-cleanup")
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1

    from tests.fixtures.isolation import reset_state

    reset_state(namespace)
    counts = fetch_counts(a2.gateway_dsn)
    assert counts["ag_operations"] == 0
    assert counts["ag_ledger_events"] == 0
    assert counts["ag_receipt_outbox"] == 0
    assert counts["ag_execution_leases"] == 0
    assert counts["ag_operation_review_flags"] == 0
