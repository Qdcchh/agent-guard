"""Independent audit database migration and persistent domain ownership marker."""

from __future__ import annotations

import hashlib
from pathlib import Path

from agent_guard.ledger.migrate import DEFAULT_MIGRATIONS_DIR

AUDIT_SQL_SHA256 = "982e8b4b98049badc2f32eb70579506da65c55b4e80caf594c9a6637a48b5678"


class AuditMigrationError(ValueError):
    """The independent audit database or its immutable lineage is invalid."""


def check_domain(conn, *, owner_role: str) -> None:
    row = conn.execute(
        "SELECT current_user,current_database(),current_setting('server_version_num')::int"
    ).fetchone()
    if (
        row[0] != owner_role
        or row[1] in ("postgres", "template0", "template1")
        or row[2] // 10000 != 16
    ):
        raise AuditMigrationError("independent PG16 audit owner/domain required")
    for name in ("ag_tasks", "ag_operations", "ag_schema_migration_lineages", "ds_operations"):
        if conn.execute("SELECT to_regclass(%s)", (name,)).fetchone()[0] is not None:
            raise AuditMigrationError("gateway or downstream database refused")


def apply_migrations(conn, *, owner_role: str, migration_path: Path | None = None) -> bool:
    check_domain(conn, owner_role=owner_role)
    path = migration_path or DEFAULT_MIGRATIONS_DIR / "audit" / "001_checkpoint_store.sql"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != AUDIT_SQL_SHA256:
        raise AuditMigrationError("audit SQL checksum mismatch")
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(3101001)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ag_audit_schema_migrations(version tex"
            "t PRIMARY KEY,filename text NOT NULL,raw_checksum text NOT NULL,a"
            "pplied_at timestamptz NOT NULL DEFAULT clock_timestamp(),domain_m"
            "arker text NOT NULL,owner_role text NOT NULL)"
        )
        rows = conn.execute(
            "SELECT version,filename,raw_checksum,domain_marker,owner_role FRO"
            "M ag_audit_schema_migrations ORDER BY version"
        ).fetchall()
        expected = (
            "001",
            "001_checkpoint_store.sql",
            AUDIT_SQL_SHA256,
            "AG-INDEPENDENT-AUDIT-1",
            owner_role,
        )
        if rows:
            if rows != [expected]:
                raise AuditMigrationError("audit registry owner/checksum mismatch")
            return False
        if path.read_bytes() != raw:
            raise AuditMigrationError("audit SQL changed before execution")
        conn.execute(raw.decode("utf-8"))
        conn.execute(
            "INSERT INTO ag_audit_schema_migrations(version,filename,raw_check"
            "sum,domain_marker,owner_role) VALUES (%s,%s,%s,%s,%s)",
            expected,
        )
    return True


def require_domain(conn, *, owner_role: str) -> None:
    check_domain(conn, owner_role=owner_role)
    if conn.execute("SELECT to_regclass('ag_audit_schema_migrations')").fetchone()[0] is None:
        raise AuditMigrationError("audit domain not initialized")
    rows = conn.execute(
        "SELECT version,filename,raw_checksum,domain_marker,owner_role FRO"
        "M ag_audit_schema_migrations"
    ).fetchall()
    if rows != [
        ("001", "001_checkpoint_store.sql", AUDIT_SQL_SHA256, "AG-INDEPENDENT-AUDIT-1", owner_role)
    ]:
        raise AuditMigrationError("audit domain marker rejected")
