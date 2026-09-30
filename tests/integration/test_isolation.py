"""F1 regressions: destructive test tooling must be provably isolated.

Covers the review requirements: a wrong target is refused before any
migrate/wipe runs, pre-existing same-name resources are never deleted, an
ordinary (non-test) DSN is never touched by the suite, and two run namespaces
do not wipe each other.
"""

from __future__ import annotations

import psycopg
import pytest

from agent_guard.ledger import apply_migrations
from tests.fixtures.dbstate import fetch_counts
from tests.fixtures.isolation import (
    IsolationError,
    Namespace,
    acquire_namespace,
    assert_owned,
    build_dsn,
    create_scratch_database,
    drop_scratch_database,
    release_namespace,
    reset_state,
)
from tests.fixtures.state import build_tree

pytestmark = pytest.mark.integration


def test_wrong_target_maintenance_database_is_refused(namespace):
    """Pointing at a maintenance database fails before any DDL/DML runs."""
    bad = build_dsn(namespace.base_dsn, dbname="postgres")
    with pytest.raises(IsolationError, match="maintenance database"):
        acquire_namespace(bad)
    with psycopg.connect(bad, connect_timeout=5) as conn:
        leaked = conn.execute(
            "SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'ag\\_test\\_run\\_%'"
        ).fetchone()[0]
    assert leaked == 0


def test_wrong_target_unnamed_database_is_refused(namespace):
    params_dsn = build_dsn(namespace.base_dsn, dbname="")
    with pytest.raises(IsolationError, match="must name a database"):
        acquire_namespace(params_dsn)


def test_reset_state_refuses_tampered_namespace_without_wiping(namespace):
    """Ownership is re-verified before every wipe; a mismatched marker blocks it."""
    other = acquire_namespace(namespace.base_dsn)
    try:
        with psycopg.connect(other.dsn, connect_timeout=5) as conn:
            apply_migrations(conn)
            build_tree(conn)
        with psycopg.connect(other.base_dsn, connect_timeout=5) as conn:
            conn.execute(
                f'UPDATE "{other.schema}".ag_test_ownership SET run_id = %s',
                ("someone-else",),
            )
        tampered = Namespace(
            run_id=other.run_id,
            schema=other.schema,
            database=other.database,
            base_dsn=other.base_dsn,
            dsn=other.dsn,
        )
        with pytest.raises(IsolationError, match="marker"):
            reset_state(tampered)
        # nothing was wiped: the tree is still there
        assert fetch_counts(other.dsn)["ag_grants"] == 3
    finally:
        # restore the marker so the namespace can be released safely
        with psycopg.connect(other.base_dsn, connect_timeout=5) as conn:
            conn.execute(
                f'UPDATE "{other.schema}".ag_test_ownership SET run_id = %s',
                (other.run_id,),
            )
        release_namespace(other)


def test_two_namespaces_do_not_wipe_each_other(namespace, migrated):
    reset_state(namespace)  # baseline: previous tests may have left rows behind
    with psycopg.connect(namespace.dsn, connect_timeout=5) as conn:
        apply_migrations(conn)
        build_tree(conn, tenant_id="ns-a", task_id="ns-a")
    other = acquire_namespace(namespace.base_dsn)
    try:
        with psycopg.connect(other.dsn, connect_timeout=5) as conn:
            apply_migrations(conn)
        reset_state(other)  # wipes only `other`, never `namespace`
        assert fetch_counts(namespace.dsn)["ag_grants"] == 3
        assert fetch_counts(other.dsn)["ag_grants"] == 0
    finally:
        release_namespace(other)


def test_ordinary_dsn_is_never_touched_by_test_flow(namespace, migrated, monkeypatch):
    """Setting AGENT_GUARD_DATABASE_URL must not migrate or wipe that database."""
    decoy = create_scratch_database(namespace.base_dsn)
    try:
        monkeypatch.setenv("AGENT_GUARD_DATABASE_URL", decoy.dsn)
        # the normal test flow: namespace-local migration and reset
        with psycopg.connect(namespace.dsn, connect_timeout=5) as conn:
            apply_migrations(conn)
        reset_state(namespace)
        with psycopg.connect(decoy.dsn, connect_timeout=5) as conn:
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')"
            ).fetchall()
            schemas = conn.execute(
                "SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'ag\\_test\\_run\\_%'"
            ).fetchone()[0]
        assert tables == []
        assert schemas == 0
    finally:
        drop_scratch_database(namespace.base_dsn, decoy)


def test_assert_owned_detects_missing_marker(namespace):
    other = acquire_namespace(namespace.base_dsn)
    try:
        with psycopg.connect(other.base_dsn, connect_timeout=5) as conn:
            conn.execute(f'DROP TABLE "{other.schema}".ag_test_ownership')
        with pytest.raises(IsolationError, match="marker"):
            assert_owned(other)
        with pytest.raises(IsolationError, match="marker"):
            reset_state(other)
    finally:
        with psycopg.connect(other.base_dsn, connect_timeout=5) as conn:
            conn.execute(
                f'CREATE TABLE "{other.schema}".ag_test_ownership ('
                "run_id TEXT PRIMARY KEY, database_name TEXT NOT NULL, "
                "created_at TIMESTAMPTZ NOT NULL)"
            )
            conn.execute(
                f'INSERT INTO "{other.schema}".ag_test_ownership VALUES (%s, %s, now())',
                (other.run_id, other.database),
            )
        release_namespace(other)


def test_scratch_creation_rejects_foreign_names(namespace):
    with pytest.raises(IsolationError, match="not generated"):
        create_scratch_database(namespace.base_dsn, name="victim_database")
    with pytest.raises(IsolationError, match="not generated"):
        create_scratch_database(namespace.base_dsn, name='ag_test_migrate_x"; DROP DATABASE x;--')
