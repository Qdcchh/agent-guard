"""P13: migrations are versioned, idempotent and non-destructive.

Scratch databases use random names owned by this run (review F1): a
pre-existing same-name database is refused and never dropped, and only
databases this run created are cleaned up. Version expectations are derived
from the migrations directory, never hardcoded, so new migrations are covered.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import psycopg
import pytest

from agent_guard.contracts.ledger import AcceptDisposition
from agent_guard.ledger.migrate import (
    DEFAULT_MIGRATIONS_DIR,
    MigrationError,
    applied_versions,
    apply_migrations,
)
from agent_guard.ledger.provisioning import revoke_grant
from agent_guard.ledger.service import ExecutionLedger
from tests.fixtures.dbstate import fetch_counters
from tests.fixtures.isolation import (
    IsolationError,
    ScratchDatabase,
    create_scratch_database,
    drop_scratch_database,
)
from tests.fixtures.state import build_tree

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


def expected_versions(migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> list[str]:
    return sorted(p.name.split("_", 1)[0] for p in migrations_dir.glob("*.sql"))


@pytest.fixture()
def scratch(namespace) -> ScratchDatabase:
    """A random-named database created (and later dropped) by this run only."""
    created = create_scratch_database(namespace.base_dsn)
    try:
        yield created
    finally:
        drop_scratch_database(namespace.base_dsn, created)


def test_p13_fresh_database_migrates_and_is_versioned(scratch):
    versions = expected_versions()
    with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
        applied = apply_migrations(conn)
        assert applied == versions
        assert set(applied_versions(conn)) == set(versions)

        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name LIKE 'ag_%' "
            "ORDER BY table_name"
        ).fetchall()
        names = [row[0] for row in tables]
        for expected in (
            "ag_tasks",
            "ag_principals",
            "ag_grants",
            "ag_tenant_admins",
            "ag_grant_revocations",
            "ag_operations",
            "ag_proofs",
            "ag_ledger_events",
            "ag_ledger_event_nodes",
        ):
            assert expected in names


def test_p13_re_migration_is_a_no_op_and_preserves_data(scratch):
    with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
        assert apply_migrations(conn) == expected_versions()

    with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
        tree = build_tree(conn)

    # re-running on an already migrated database applies nothing
    with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
        assert apply_migrations(conn) == []
        assert set(applied_versions(conn)) == set(expected_versions())
        count = conn.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'ag_tasks'"
        ).fetchone()[0]
        assert count == 1
        assert conn.execute("SELECT count(*) FROM ag_grants").fetchone()[0] == 3
        assert (
            conn.execute(
                "SELECT root_grant_id FROM ag_tasks WHERE tenant_id = %s AND task_id = %s",
                (tree.tenant_id, tree.task_id),
            ).fetchone()[0]
            == tree.root_id
        )

    # reconnecting later still sees the data and a third run stays a no-op
    with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
        assert apply_migrations(conn) == []
        assert conn.execute("SELECT count(*) FROM ag_grants").fetchone()[0] == 3


def test_p13_edited_applied_migration_is_rejected(scratch, tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_init.sql").write_text("CREATE TABLE ag_demo (id int);")
    with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
        assert apply_migrations(conn, migrations) == ["001"]

    (migrations / "001_init.sql").write_text("CREATE TABLE ag_demo (id bigint);")
    with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
        with pytest.raises(MigrationError, match="changed after being applied"):
            apply_migrations(conn, migrations)


def test_p13_upgrade_from_001_keeps_existing_ledger(scratch, tmp_path):
    """001 -> latest migrations upgrade in place without touching stored state.

    The 001 database first records a *real* nonzero accept (70000 fen / 1 call
    through :class:`ExecutionLedger`) and a real revocation, so counters,
    revocation flags, the operation, its proof and its ledger events all exist
    before the upgrade. After upgrading to every migration in the directory,
    all rows of all seven business tables must be exactly the same.
    """
    only_001 = tmp_path / "only001"
    only_001.mkdir()
    (only_001 / "001_init.sql").write_bytes((DEFAULT_MIGRATIONS_DIR / "001_init.sql").read_bytes())
    with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
        assert apply_migrations(conn, only_001) == ["001"]
    with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
        tree = build_tree(conn)

    ledger = ExecutionLedger(scratch.dsn)
    result = ledger.accept(tree.invocation(), tree.cost(amount_fen=70000))
    assert result.disposition is AcceptDisposition.CREATED
    assert result.cost.amount_fen == 70000
    with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
        revoke_grant(conn, tree.root_id)

    before = _snapshot_business_tables(scratch.dsn)
    assert all(before[table] for table in _BUSINESS_TABLE_ORDER)
    root = fetch_counters(scratch.dsn, tree.root_id)
    assert root["amount_reserved"] == 70000
    assert root["calls_reserved"] == 1

    with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
        applied = apply_migrations(conn)  # full directory: newer migrations only
        assert applied == [v for v in expected_versions() if v != "001"]
        assert set(applied_versions(conn)) == set(expected_versions())

    assert _snapshot_business_tables(scratch.dsn) == before


def _snapshot_business_tables(dsn: str) -> dict[str, list[tuple]]:
    """Every row of every business table, in a deterministic order."""
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        return {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
            for table, order in _BUSINESS_TABLE_ORDER.items()
        }


def test_p13_preexisting_same_name_database_is_never_deleted(namespace):
    """A database this run did not create is refused and left untouched."""
    name = f"ag_test_migrate_{secrets.token_hex(8)}"
    with psycopg.connect(namespace.base_dsn, autocommit=True, connect_timeout=5) as conn:
        assert (
            conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone() is None
        )
        conn.execute(f'CREATE DATABASE "{name}"')
    try:
        with pytest.raises(IsolationError, match="already exists"):
            create_scratch_database(namespace.base_dsn, name=name)
        # the pre-existing database is still there
        with psycopg.connect(namespace.base_dsn, connect_timeout=5) as conn:
            assert (
                conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
                is not None
            )
    finally:
        with psycopg.connect(namespace.base_dsn, autocommit=True, connect_timeout=5) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def test_p13_unowned_scratch_refuses_drop(namespace):
    fake = ScratchDatabase(name="ag_test_migrate_" + "b" * 16, dsn="", created=False)
    with pytest.raises(IsolationError, match="not created by this run"):
        drop_scratch_database(namespace.base_dsn, fake)


def test_p13_cli_entry_reports_status(scratch, monkeypatch):
    """CLI uses AGENT_GUARD_TEST_DATABASE_URL only when the ordinary var is absent."""
    monkeypatch.delenv("AGENT_GUARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("AGENT_GUARD_TEST_DATABASE_URL", raising=False)
    from agent_guard.ledger.migrate import main

    assert main([]) == 2  # no DSN configured: refuse rather than guess

    monkeypatch.setenv("AGENT_GUARD_TEST_DATABASE_URL", scratch.dsn)
    assert main([]) == 0  # first run applies
    assert main([]) == 0  # second run: up to date
    with psycopg.connect(scratch.dsn, connect_timeout=5) as conn:
        assert conn.execute("SELECT count(*) FROM ag_schema_migrations").fetchone()[0] == len(
            expected_versions()
        )


def test_p13_cli_prefers_ordinary_dsn_when_set(namespace, monkeypatch):
    """Documented priority: AGENT_GUARD_DATABASE_URL wins over the test var."""
    ordinary = create_scratch_database(namespace.base_dsn)
    test_target = create_scratch_database(namespace.base_dsn)
    try:
        monkeypatch.setenv("AGENT_GUARD_DATABASE_URL", ordinary.dsn)
        monkeypatch.setenv("AGENT_GUARD_TEST_DATABASE_URL", test_target.dsn)
        from agent_guard.ledger.migrate import main

        assert main([]) == 0
        with psycopg.connect(ordinary.dsn, connect_timeout=5) as conn:
            assert conn.execute("SELECT count(*) FROM ag_schema_migrations").fetchone()[0] > 0
        with psycopg.connect(test_target.dsn, connect_timeout=5) as conn:
            tables = conn.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'ag_schema_migrations'"
            ).fetchone()[0]
            assert tables == 0  # the ordinary variable won; test target untouched
    finally:
        drop_scratch_database(namespace.base_dsn, ordinary)
        drop_scratch_database(namespace.base_dsn, test_target)
