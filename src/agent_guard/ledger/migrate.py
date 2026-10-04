"""Versioned SQL migration runner for the A1 ledger schema.

Migrations live in ``migrations/NNN_name.sql`` at the repository root and are
applied in lexical order inside one transaction each. Applied versions and
file checksums are recorded in ``ag_schema_migrations``; re-running is a
no-op, and editing an already-applied migration is rejected.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

import psycopg

MIGRATIONS_TABLE = "ag_schema_migrations"
_FILENAME_RE = re.compile(r"^(?P<version>\d{3})_[A-Za-z0-9_]+\.sql$")

_SOURCE_MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"
DEFAULT_MIGRATIONS_DIR = (
    _SOURCE_MIGRATIONS
    if (_SOURCE_MIGRATIONS / "001_init.sql").is_file()
    else Path(sys.prefix) / "share" / "agent-guard" / "migrations"
)


class MigrationError(Exception):
    """Raised when migrations cannot be applied safely."""


def _migrations_dir() -> Path:
    """Resolve the trusted deployment override, never the caller's cwd."""
    override = os.environ.get("AGENT_GUARD_MIGRATIONS_DIR")
    return Path(override) if override else DEFAULT_MIGRATIONS_DIR


def _ensure_registry(conn: psycopg.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
            version     TEXT PRIMARY KEY,
            filename    TEXT NOT NULL,
            checksum    TEXT NOT NULL,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        )
        """
    )


def _discover(migrations_dir: Path) -> list[tuple[str, str, str, str]]:
    if not migrations_dir.is_dir():
        raise MigrationError(f"migrations directory not found: {migrations_dir}")
    found: list[tuple[str, str, str, str]] = []
    for path in sorted(migrations_dir.iterdir()):
        if not path.is_file():
            continue
        match = _FILENAME_RE.match(path.name)
        if match is None:
            if path.suffix == ".sql":
                raise MigrationError(f"bad migration filename: {path.name}")
            continue
        data = path.read_bytes()
        # Preserve the original universal-newline registry checksum. The raw
        # digest independently detects even newline-only execution races.
        sql = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        version = match.group("version")
        if any(item[0] == version for item in found):
            raise MigrationError(f"duplicate migration version: {version}")
        found.append((version, path.name, checksum, hashlib.sha256(data).hexdigest()))
    if not found:
        raise MigrationError(f"no migrations found in {migrations_dir}")
    return found


def applied_versions(conn: psycopg.Connection) -> dict[str, str]:
    """Return the A/common execution view, never ambiguous B numeric versions."""
    from agent_guard.ledger.lineage import (
        _exists,
        _legacy_rows,
        _recognize,
        applied_lineage_versions,
        load_manifest,
    )

    if _exists(conn, "ag_schema_migration_lineages"):
        return {
            version: digest
            for (namespace, version), digest in applied_lineage_versions(conn).items()
            if namespace in ("common", "execution")
        }
    _ensure_registry(conn)
    source, _ = _recognize(_legacy_rows(conn), load_manifest())
    if source == "B":
        raise MigrationError(
            "B legacy history requires bundle migration for the A compatibility view"
        )
    return _raw_applied_versions(conn)


def _raw_applied_versions(conn: psycopg.Connection) -> dict[str, str]:
    """Internal legacy writer lookup; filenames/checksums are checked by its caller."""
    rows = conn.execute(
        f"SELECT version, checksum FROM {MIGRATIONS_TABLE} ORDER BY version"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def apply_migrations(conn: psycopg.Connection, migrations_dir: Path | None = None) -> list[str]:
    """Apply pending migrations; returns the versions applied in this run."""
    directory = Path(migrations_dir) if migrations_dir is not None else _migrations_dir()
    pending = _discover(directory)

    from agent_guard.ledger.lineage import _COORDINATOR, _exists, apply_bundle_migrations

    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout = '10s'")
        conn.execute("SET LOCAL statement_timeout = '15s'")
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_COORDINATOR,))
        if _exists(conn, "ag_schema_migration_lineages"):
            if directory.resolve() != _migrations_dir().resolve():
                raise MigrationError("custom legacy directory cannot mutate bundle history")
            before = applied_versions(conn)
            apply_bundle_migrations(conn)
            return [v for v in applied_versions(conn) if v not in before]
        _ensure_registry(conn)
        already = _raw_applied_versions(conn)
        filenames = dict(
            conn.execute("SELECT version,filename FROM ag_schema_migrations").fetchall()
        )
        applied_now: list[str] = []
        for version, filename, checksum, raw_checksum in pending:
            known = already.get(version)
            if known is not None:
                if known != checksum or filenames[version] != filename:
                    raise MigrationError(
                        f"migration {filename} changed after being applied "
                        f"(recorded {known[:12]}..., current {checksum[:12]}...)"
                    )
                continue
            data = (directory / filename).read_bytes()
            if hashlib.sha256(data).hexdigest() != raw_checksum:
                raise MigrationError("migration changed before execution")
            conn.execute(data.decode("utf-8"))
            conn.execute(
                f"INSERT INTO {MIGRATIONS_TABLE} (version, filename, checksum) VALUES (%s, %s, %s)",
                (version, filename, checksum),
            )
            applied_now.append(version)
    return applied_now


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m agent_guard.ledger.migrate [migrations_dir]``.

    Uses ``AGENT_GUARD_DATABASE_URL`` (falling back to
    ``AGENT_GUARD_TEST_DATABASE_URL``) and never prints connection details.
    """
    import os
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    dsn = os.environ.get("AGENT_GUARD_DATABASE_URL") or os.environ.get(
        "AGENT_GUARD_TEST_DATABASE_URL"
    )
    if not dsn:
        print(
            "error: set AGENT_GUARD_DATABASE_URL or AGENT_GUARD_TEST_DATABASE_URL",
            file=sys.stderr,
        )
        return 2
    bundle = bool(args and args[0] == "--bundle")
    if bundle:
        args.pop(0)
    if len(args) > 1:
        print("usage: migrate [--bundle] [trusted-migrations-directory]", file=sys.stderr)
        return 2
    migrations_dir = Path(args[0]) if args else None
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if bundle:
                from agent_guard.ledger.lineage import apply_bundle_migrations, load_manifest

                applied = [
                    f"{ns}:{v}"
                    for ns, v in apply_bundle_migrations(conn, load_manifest(migrations_dir))
                ]
            else:
                applied = apply_migrations(conn, migrations_dir)
    except (MigrationError, psycopg.Error, OSError, ValueError):
        print("migration failed: configuration, connection or migration rejected", file=sys.stderr)
        return 1
    print(f"applied: {', '.join(applied)}" if applied else "already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# Explicit bundle APIs are also available alongside the legacy runner. Imports
# remain lazy because lineage recognition shares the legacy registry builder.
def apply_bundle_migrations(conn, manifest=None):
    from agent_guard.ledger.lineage import apply_bundle_migrations as apply

    return apply(conn, manifest)


def applied_lineage_versions(conn):
    from agent_guard.ledger.lineage import applied_lineage_versions as read

    return read(conn)
