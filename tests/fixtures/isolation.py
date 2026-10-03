"""Run-exclusive isolation for destructive test operations (review F1).

Design:

- Every pytest session acquires its own schema ``ag_test_run_<token>`` inside
  the target database and records ownership in a marker table inside that
  schema. Destructive operations only ever touch schema-qualified names and
  re-verify the marker first, so two sessions sharing one database never wipe
  each other and a wrong/tampered target is refused *before* any DDL/DML runs.
- Scratch databases for migration tests use random names and are dropped only
  when this run actually created them; a pre-existing same-name resource is
  refused and never deleted.
- DSNs are parsed and rebuilt with ``psycopg.conninfo`` so legal connection
  options survive; nothing is assembled with string splitting.
- Maintenance databases (``postgres``/``template*``) are refused as targets.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg
from psycopg import conninfo

#: Ownership marker stored inside each run-exclusive schema.
MARKER_TABLE = "ag_test_ownership"

#: Strict name patterns: generated tokens only, never caller-controlled text.
SCHEMA_RE = re.compile(r"^ag_test_run_[0-9a-f]{12}$")
SCRATCH_DB_RE = re.compile(r"^ag_test_migrate_[0-9a-f]{16}$")
DOWNSTREAM_DB_RE = re.compile(r"^ag_test_downstream_[0-9a-f]{16}$")

#: Never a legitimate destructive target.
MAINTENANCE_DBS = frozenset({"postgres", "template0", "template1"})

#: Tables owned by the gateway ledger schema (schema-qualified for every wipe).
#: 004 adds three more tables next to the seven A1 business tables; they are
#: wiped together so a run never leaks execution state into the next test.
RESET_TABLES = (
    "ag_operation_evidence",
    "ag_verified_evidence",
    "ag_auth_events",
    "ag_authorization_requests",
    "ag_login_sessions",
    "ag_login_csrf",
    "ag_task_policies",
    "ag_users",
    "ag_grant_revocations",
    "ag_tenant_admins",
    "ag_task_revocations",
    "ag_exchange_evidence",
    "ag_delegations",
    "ag_auth_evidence",
    "ag_grant_tokens",
    "ag_authorization_codes",
    "ag_proofs",
    "ag_ledger_event_nodes",
    "ag_ledger_events",
    "ag_operations",
    "ag_grants",
    "ag_tasks",
    "ag_principals",
    "ag_receipt_outbox",
    "ag_execution_leases",
    "ag_operation_review_flags",
)

# Preserve the original A read-only assertion helper's compatibility view.
TABLES = (
    "ag_proofs",
    "ag_ledger_event_nodes",
    "ag_ledger_events",
    "ag_receipt_outbox",
    "ag_execution_leases",
    "ag_operation_review_flags",
    "ag_operations",
    "ag_grants",
    "ag_tasks",
    "ag_principals",
)

CONNECT_TIMEOUT_S = 5


class IsolationError(Exception):
    """Raised when a target cannot be proven to belong to this test run."""


def build_dsn(base: str, **overrides: str) -> str:
    """Parse and rebuild a DSN, preserving every legal connection option."""
    params = conninfo.conninfo_to_dict(base)
    for key, value in overrides.items():
        if key == "options" and params.get("options"):
            # append instead of clobbering user-supplied options
            params["options"] = f"{params['options']} {value}"
        else:
            params[key] = value
    return conninfo.make_conninfo(**params)


def _require_named_database(dsn: str) -> str:
    params = conninfo.conninfo_to_dict(dsn)
    name = params.get("dbname") or params.get("database")
    if not name:
        raise IsolationError("target DSN must name a database explicitly")
    if name in MAINTENANCE_DBS:
        raise IsolationError(f"refusing maintenance database as target: {name}")
    return name


@dataclass(frozen=True)
class Namespace:
    """One run-exclusive schema with an ownership record."""

    run_id: str
    schema: str
    database: str
    base_dsn: str  # parsed/rebuilt DSN without search_path
    dsn: str  # same DSN with search_path pointing at this run's schema


@dataclass(frozen=True)
class ScratchDatabase:
    """A random-named database created and owned by this run."""

    name: str
    dsn: str
    created: bool  # only True when this call actually created it


def acquire_namespace(base_dsn: str) -> Namespace:
    """Create a run-exclusive schema and its ownership marker.

    Refuses unnamed/maintenance targets before any DDL runs.
    """
    declared = _require_named_database(base_dsn)
    clean = build_dsn(base_dsn)
    run_id = secrets.token_hex(6)
    schema = f"ag_test_run_{run_id}"
    with psycopg.connect(clean, connect_timeout=CONNECT_TIMEOUT_S) as conn:
        database = conn.execute("SELECT current_database()").fetchone()[0]
        if database in MAINTENANCE_DBS:
            raise IsolationError(f"refusing maintenance database as target: {database}")
        if database != declared:
            raise IsolationError(
                f"connected database {database!r} differs from declared {declared!r}"
            )
        with conn.transaction():
            conn.execute(f'CREATE SCHEMA "{schema}"')
            conn.execute(
                f'CREATE TABLE "{schema}".{MARKER_TABLE} ('
                "run_id TEXT PRIMARY KEY,"
                "database_name TEXT NOT NULL,"
                "created_at TIMESTAMPTZ NOT NULL)"
            )
            conn.execute(
                f'INSERT INTO "{schema}".{MARKER_TABLE} (run_id, database_name, created_at) '
                "VALUES (%s, %s, %s)",
                (run_id, database, datetime.now(tz=timezone.utc)),
            )
    return Namespace(
        run_id=run_id,
        schema=schema,
        database=database,
        base_dsn=clean,
        dsn=build_dsn(clean, options=f"-c search_path={schema}"),
    )


def assert_owned(ns: Namespace) -> None:
    """Prove the namespace still belongs to this run; never mutates anything."""
    if not SCHEMA_RE.match(ns.schema) or ns.run_id not in ns.schema:
        raise IsolationError(f"suspicious namespace name: {ns.schema!r}")
    try:
        with psycopg.connect(ns.base_dsn, connect_timeout=CONNECT_TIMEOUT_S) as conn:
            row = conn.execute(
                f'SELECT run_id, database_name FROM "{ns.schema}".{MARKER_TABLE} WHERE run_id = %s',
                (ns.run_id,),
            ).fetchone()
    except psycopg.Error as exc:
        raise IsolationError(f"ownership marker unreadable: {exc}") from exc
    if row is None:
        raise IsolationError("ownership marker missing for this run")
    if row[0] != ns.run_id or row[1] != ns.database:
        raise IsolationError("ownership marker mismatch")


def reset_state(ns: Namespace) -> None:
    """Wipe ledger state inside the run's schema only, after ownership check."""
    assert_owned(ns)
    with psycopg.connect(ns.base_dsn, connect_timeout=CONNECT_TIMEOUT_S) as conn:
        with conn.transaction():
            bundle = conn.execute(
                "SELECT to_regclass(%s)", (f'"{ns.schema}".ag_schema_migration_lineages',)
            ).fetchone()[0]
            tables = RESET_TABLES if bundle is not None else TABLES
            targets = ", ".join(f'"{ns.schema}"."{table}"' for table in tables)
            conn.execute(f"TRUNCATE {targets} RESTART IDENTITY CASCADE")


def release_namespace(ns: Namespace) -> None:
    """Drop only the schema this run created; never touch anything else."""
    try:
        assert_owned(ns)
    except IsolationError as exc:  # pragma: no cover - defensive
        print(f"isolation warning: leaving schema {ns.schema} in place: {exc}")
        return
    with psycopg.connect(ns.base_dsn, connect_timeout=CONNECT_TIMEOUT_S) as conn:
        with conn.transaction():
            conn.execute(f'DROP SCHEMA "{ns.schema}" CASCADE')


def create_scratch_database(admin_dsn: str, name: str | None = None) -> ScratchDatabase:
    """Create a random-named scratch database owned by this run.

    A pre-existing database with the same name is refused and never deleted.
    """
    return _create_named_database(admin_dsn, name, SCRATCH_DB_RE, "ag_test_migrate_")


def drop_scratch_database(admin_dsn: str, scratch: ScratchDatabase) -> None:
    """Drop a scratch database only when this run created it.

    The admin connection must be a *different* database on the same server
    (e.g. the session test database); dropping never runs against maintenance
    or unknown databases.
    """
    _drop_named_database(admin_dsn, scratch, SCRATCH_DB_RE)


def create_downstream_database(admin_dsn: str, name: str | None = None) -> ScratchDatabase:
    """Create the run-owned database used by the mock downstream domain.

    The downstream must live in a different database from the gateway ledger so
    that recovery is genuinely cross-transaction-domain and never relies on one
    local transaction spanning both sides.
    """
    return _create_named_database(admin_dsn, name, DOWNSTREAM_DB_RE, "ag_test_downstream_")


def drop_downstream_database(admin_dsn: str, scratch: ScratchDatabase) -> None:
    """Drop the run-owned downstream database; nothing else is ever touched."""
    _drop_named_database(admin_dsn, scratch, DOWNSTREAM_DB_RE)


def _create_named_database(
    admin_dsn: str,
    name: str | None,
    pattern: "re.Pattern[str]",
    prefix: str,
) -> ScratchDatabase:
    if name is not None and not pattern.match(name):
        raise IsolationError(f"database name not generated by this helper: {name!r}")
    db_name = name or f"{prefix}{secrets.token_hex(8)}"
    if not pattern.match(db_name):
        raise IsolationError(f"database name not generated by this helper: {db_name!r}")
    clean = build_dsn(admin_dsn)
    _require_named_database(clean)
    with psycopg.connect(clean, autocommit=True, connect_timeout=CONNECT_TIMEOUT_S) as conn:
        existing = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
        ).fetchone()
        if existing is not None:
            raise IsolationError(
                f"database {db_name} already exists and is not owned by this run; refusing"
            )
        conn.execute(f'CREATE DATABASE "{db_name}"')
    return ScratchDatabase(name=db_name, dsn=build_dsn(clean, dbname=db_name), created=True)


def _drop_named_database(
    admin_dsn: str, scratch: ScratchDatabase, pattern: "re.Pattern[str]"
) -> None:
    if not scratch.created:
        raise IsolationError(f"database {scratch.name} was not created by this run")
    if not pattern.match(scratch.name):
        raise IsolationError(f"refusing to drop an unexpected database name: {scratch.name!r}")
    admin = build_dsn(admin_dsn)
    _require_named_database(admin)
    with psycopg.connect(admin, autocommit=True, connect_timeout=CONNECT_TIMEOUT_S) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{scratch.name}" WITH (FORCE)')
