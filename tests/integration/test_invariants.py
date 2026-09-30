"""Formal regressions for review F2/F3/F4: database-level root invariants,
subject binding and single-call billing.

These are the safely-isolated rewrites of the reviewer's independent probes.
"""

from __future__ import annotations

import secrets
from dataclasses import replace

import psycopg
import pytest

from agent_guard.contracts.ledger import (
    AcceptDisposition,
    ErrorCode,
    LedgerError,
    TrustedCost,
)
from agent_guard.ledger.migrate import DEFAULT_MIGRATIONS_DIR, applied_versions, apply_migrations
from agent_guard.ledger.provisioning import create_task_root, revoke_grant
from tests.fixtures.dbstate import fetch_all, fetch_counters, fetch_counts, fetch_one
from tests.fixtures.isolation import create_scratch_database, drop_scratch_database
from tests.fixtures.state import default_window

pytestmark = pytest.mark.integration

#: Deterministic full-row read order for the seven business tables.
_BUSINESS_TABLE_ORDER = {
    "ag_tasks": "tenant_id, task_id",
    "ag_principals": "tenant_id, client_id, kid",
    "ag_grants": "grant_id",
    "ag_operations": "operation_id",
    "ag_proofs": "holder_kid, purpose, endpoint, proof_jti",
    "ag_ledger_events": "event_id",
    "ag_ledger_event_nodes": "event_id, position",
}


def _snapshot_business_tables(dsn: str) -> dict[str, list[tuple]]:
    """Every row of every business table, in a deterministic order."""
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        return {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
            for table, order in _BUSINESS_TABLE_ORDER.items()
        }


# ------------------------------------------------------------------ F2


def test_f2_database_rejects_second_root_for_same_task(ledger, tree, namespace):
    """A plain-SQL second root for one task is refused by the database."""
    another = f"root-dup-{secrets.token_hex(4)}"
    with psycopg.connect(namespace.dsn, connect_timeout=5) as conn:
        with pytest.raises(psycopg.IntegrityError):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO ag_grants "
                    "(grant_id, parent_grant_id, root_grant_id, tenant_id, task_id, subject, "
                    "holder_client_id, holder_kid, depth, not_before, expires_at, "
                    "amount_limit, call_limit) "
                    "SELECT %s, NULL, %s, tenant_id, task_id, subject, "
                    "holder_client_id, holder_kid, 0, not_before, expires_at, "
                    "amount_limit, call_limit FROM ag_grants WHERE grant_id = %s",
                    (another, another, tree.root_id),
                )
    assert fetch_counts(namespace.dsn)["ag_grants"] == 3


def test_f2_task_root_mapping_must_not_change(ledger, tree, namespace):
    """The task identity and root mapping are immutable at the database level."""
    with psycopg.connect(namespace.dsn, connect_timeout=5) as conn:
        with pytest.raises(psycopg.IntegrityError):
            with conn.transaction():
                conn.execute(
                    "UPDATE ag_tasks SET root_grant_id = %s WHERE tenant_id = %s AND task_id = %s",
                    ("nonexistent-replacement-root", tree.tenant_id, tree.task_id),
                )
        with pytest.raises(psycopg.IntegrityError):
            with conn.transaction():
                conn.execute(
                    "UPDATE ag_tasks SET root_grant_id = %s WHERE tenant_id = %s AND task_id = %s",
                    (tree.mid_id, tree.tenant_id, tree.task_id),
                )


def test_f2_task_root_must_not_be_deleted(ledger, tree, namespace):
    """Task roots cannot be deleted and rebuilt."""
    with psycopg.connect(namespace.dsn, connect_timeout=5) as conn:
        with pytest.raises(psycopg.IntegrityError):
            with conn.transaction():
                conn.execute(
                    "DELETE FROM ag_tasks WHERE tenant_id = %s AND task_id = %s",
                    (tree.tenant_id, tree.task_id),
                )
    assert fetch_counts(namespace.dsn)["ag_tasks"] == 1


def test_f2_root_grant_requires_matching_task_mapping(ledger, tree, namespace):
    """A root grant with no matching task mapping is refused (orphan root)."""
    valid_from, valid_until = default_window()
    with psycopg.connect(namespace.dsn, connect_timeout=5) as conn:
        with pytest.raises(psycopg.IntegrityError):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO ag_grants "
                    "(grant_id, parent_grant_id, root_grant_id, tenant_id, task_id, subject, "
                    "holder_client_id, holder_kid, depth, not_before, expires_at, "
                    "amount_limit, call_limit) VALUES "
                    "('root-unmapped', NULL, 'root-unmapped', %s, %s, 'u', 'c', 'k', 0, "
                    "%s, %s, 1, 1)",
                    ("tenant-orphan", "task-orphan", valid_from, valid_until),
                )
    assert fetch_counts(namespace.dsn)["ag_grants"] == 3


def test_f2_task_row_requires_existing_root_grant(ledger, tree, namespace):
    """A task row pointing at a nonexistent or non-root grant is refused."""
    with psycopg.connect(namespace.dsn, connect_timeout=5) as conn:
        with pytest.raises(psycopg.IntegrityError):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO ag_tasks (tenant_id, task_id, root_grant_id) VALUES (%s, %s, %s)",
                    ("tenant-x", "task-x", "grant-does-not-exist"),
                )
        with pytest.raises(psycopg.IntegrityError):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO ag_tasks (tenant_id, task_id, root_grant_id) VALUES (%s, %s, %s)",
                    (tree.tenant_id, tree.task_id + "-alt", tree.mid_id),
                )
    assert fetch_counts(namespace.dsn)["ag_tasks"] == 1


def test_f2_root_grant_cannot_be_deleted_and_rebuilt_with_same_id(ledger, tree, namespace):
    """A used and revoked root grant cannot be deleted and re-inserted with the
    same id to reset its counters and revocation (review F2 remainder).

    Formal version of the reviewer's failing probe: a childless root with a
    real 70000-fen / 1-call reservation is revoked, then plain SQL deletes it
    and re-inserts the same id with default counters inside one transaction.
    The database must reject the delete; after the rollback every business
    table stays identical, and legal reserve/revocation UPDATEs keep working.
    """
    root_id = f"standalone-root-{secrets.token_hex(4)}"
    task_id = f"standalone-task-{secrets.token_hex(4)}"
    with psycopg.connect(namespace.dsn, connect_timeout=5) as conn:
        create_task_root(
            conn,
            tenant_id=tree.tenant_id,
            task_id=task_id,
            grant_id=root_id,
            subject=tree.subject,
            holder_client_id=tree.planner[0],
            holder_kid=tree.planner[1],
            amount_limit=100000,
            call_limit=10,
            not_before=tree.not_before,
            expires_at=tree.expires_at,
        )

    # legal counter UPDATEs through the real accept path
    request = replace(
        tree.invocation(grant_id=tree.root_id),
        task_id=task_id,
        grant_id=root_id,
        root_id=root_id,
        ancestor_ids=(),
    )
    result = ledger.accept(request, tree.cost(amount_fen=70000))
    assert result.disposition is AcceptDisposition.CREATED
    counters = fetch_counters(namespace.dsn, root_id)
    assert counters["amount_reserved"] == 70000
    assert counters["calls_reserved"] == 1

    # legal revocation UPDATE through the trusted provisioning path
    with psycopg.connect(namespace.dsn, connect_timeout=5) as conn:
        revoke_grant(conn, root_id)
    assert fetch_one(
        namespace.dsn, "SELECT revoked FROM ag_grants WHERE grant_id = %s", (root_id,)
    ) == (True,)

    before = _snapshot_business_tables(namespace.dsn)

    # attack: delete the root and rebuild it with the same id in one
    # transaction; the rebuilt row would carry default counters/revocation
    with psycopg.connect(namespace.dsn, connect_timeout=5) as conn:
        with pytest.raises(psycopg.IntegrityError):
            with conn.transaction():
                conn.execute(
                    "CREATE TEMP TABLE old_root AS SELECT * FROM ag_grants WHERE grant_id = %s",
                    (root_id,),
                )
                conn.execute("DELETE FROM ag_grants WHERE grant_id = %s", (root_id,))
                conn.execute(
                    "INSERT INTO ag_grants "
                    "(grant_id, parent_grant_id, root_grant_id, tenant_id, task_id, subject, "
                    "holder_client_id, holder_kid, depth, not_before, expires_at, "
                    "amount_limit, call_limit) "
                    "SELECT grant_id, parent_grant_id, root_grant_id, tenant_id, task_id, "
                    "subject, holder_client_id, holder_kid, depth, not_before, expires_at, "
                    "amount_limit, call_limit FROM old_root"
                )

    # the rejection rolled everything back: all seven business tables identical
    assert _snapshot_business_tables(namespace.dsn) == before


def test_f2_upgrade_rejects_illegal_existing_data(namespace, tmp_path):
    """Pre-upgrade checks abort loudly instead of deleting or clearing rows."""
    only_001 = tmp_path / "only001"
    only_001.mkdir()
    (only_001 / "001_init.sql").write_bytes((DEFAULT_MIGRATIONS_DIR / "001_init.sql").read_bytes())
    scratch = create_scratch_database(namespace.base_dsn)
    try:
        with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
            assert apply_migrations(conn, only_001) == ["001"]
            with conn.transaction():
                # illegal state behind no API: two roots for one task
                conn.execute(
                    "INSERT INTO ag_tasks (tenant_id, task_id, root_grant_id) VALUES (%s,%s,%s)",
                    ("t-illegal", "k-illegal", "root-illegal-a"),
                )
                for suffix in ("a", "b"):
                    conn.execute(
                        "INSERT INTO ag_grants "
                        "(grant_id, parent_grant_id, root_grant_id, tenant_id, task_id, "
                        "subject, holder_client_id, holder_kid, depth, not_before, "
                        "expires_at, amount_limit, call_limit) VALUES "
                        "(%s, NULL, %s, 't-illegal', 'k-illegal', 'u', 'c', 'k', 0, now(), "
                        "now() + interval '1 day', 1, 1)",
                        (f"root-illegal-{suffix}", f"root-illegal-{suffix}"),
                    )
        with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
            with pytest.raises(psycopg.Error, match="pre-check"):
                apply_migrations(conn)  # the full directory must refuse to upgrade
        with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
            # the failed upgrade rolled back: 001 stays the only applied
            # version and the illegal rows were neither deleted nor "fixed"
            assert list(applied_versions(conn)) == ["001"]
            assert (
                conn.execute(
                    "SELECT count(*) FROM ag_grants WHERE tenant_id = 't-illegal'"
                ).fetchone()[0]
                == 2
            )
    finally:
        drop_scratch_database(namespace.base_dsn, scratch)


# ------------------------------------------------------------------ F3


def test_f3_subject_must_match_database_grants(ledger, tree, namespace):
    """F3: first accept with another user's subject is rejected with no residue."""
    forged = tree.invocation(subject="another-user-not-the-grant-subject")
    with pytest.raises(LedgerError) as caught:
        ledger.accept(forged, tree.cost(1))
    assert caught.value.code is ErrorCode.INVALID_CONTEXT
    assert "subject mismatch" in caught.value.detail
    assert fetch_counts(namespace.dsn)["ag_operations"] == 0
    assert fetch_counts(namespace.dsn)["ag_proofs"] == 0
    assert fetch_counts(namespace.dsn)["ag_ledger_events"] == 0


def test_f3_same_key_retry_with_wrong_subject_is_rejected(ledger, tree, namespace):
    """F3: an idempotent retry carrying a wrong subject cannot smuggle through."""
    key = "purchase-f3"
    first = ledger.accept(tree.invocation(idempotency_key=key), tree.cost(70000))
    assert first.disposition is AcceptDisposition.CREATED
    before = fetch_counters(namespace.dsn, tree.leaf_id)

    forged = tree.invocation(
        idempotency_key=key,
        jti="jti-f3-forged",
        subject="another-user-not-the-grant-subject",
    )
    with pytest.raises(LedgerError) as caught:
        ledger.accept(forged, tree.cost(70000))
    assert caught.value.code is ErrorCode.INVALID_CONTEXT

    # the rejected retry left nothing behind
    assert fetch_counts(namespace.dsn)["ag_operations"] == 1
    assert fetch_counts(namespace.dsn)["ag_ledger_events"] == 1
    assert fetch_counters(namespace.dsn, tree.leaf_id) == before
    proofs = fetch_all(namespace.dsn, "SELECT proof_jti FROM ag_proofs")
    assert [row[0] for row in proofs] != ["jti-f3-forged"]
    assert ("jti-f3-forged",) not in proofs


# ------------------------------------------------------------------ F4


@pytest.mark.parametrize("calls", [0, 2, 99, 2**53 - 1])
def test_f4_calls_must_be_exactly_one(ledger, tree, namespace, calls):
    """F4: one operation always costs exactly one call, never more or less."""
    with pytest.raises(LedgerError) as caught:
        ledger.accept(tree.invocation(), tree.cost(0, calls=calls))
    assert caught.value.code is ErrorCode.INVALID_COST
    assert fetch_counts(namespace.dsn)["ag_operations"] == 0


def test_f4_bool_calls_are_not_integers(ledger, tree, namespace):
    for value in (True, False):
        with pytest.raises(LedgerError) as caught:
            ledger.accept(tree.invocation(), TrustedCost(amount_fen=0, calls=value))
        assert caught.value.code is ErrorCode.INVALID_COST
    assert fetch_counts(namespace.dsn)["ag_operations"] == 0


def test_f4_existing_retry_does_not_consume_extra_calls(ledger, tree, namespace):
    """F4: an idempotent retry must not add another call to the reservation."""
    key = "purchase-f4"
    first = ledger.accept(tree.invocation(idempotency_key=key), tree.cost(0))
    assert first.disposition is AcceptDisposition.CREATED
    assert fetch_counters(namespace.dsn, tree.leaf_id)["calls_reserved"] == 1

    retry = tree.invocation(idempotency_key=key, jti="jti-f4-retry")
    again = ledger.accept(retry, tree.cost(0))
    assert again.disposition is AcceptDisposition.EXISTING
    assert fetch_counters(namespace.dsn, tree.leaf_id)["calls_reserved"] == 1
    assert fetch_counts(namespace.dsn)["ag_ledger_events"] == 1
