"""Versioned SQL migration runner for the A1 ledger schema.

Migrations live in ``migrations/NNN_name.sql`` at the repository root and are
applied in lexical order inside one transaction each. Applied versions and
file checksums are recorded in ``ag_schema_migrations``; re-running is a
no-op, and editing an already-applied migration is rejected.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import psycopg

MIGRATIONS_TABLE = "ag_schema_migrations"
_FILENAME_RE = re.compile(r"^(?P<version>\d{3})_[A-Za-z0-9_]+\.sql$")

DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


class MigrationError(Exception):
    """Raised when migrations cannot be applied safely."""


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


def _discover(migrations_dir: Path) -> list[tuple[str, str, str]]:
    if not migrations_dir.is_dir():
        raise MigrationError(f"migrations directory not found: {migrations_dir}")
    found: list[tuple[str, str, str]] = []
    for path in sorted(migrations_dir.iterdir()):
        if not path.is_file():
            continue
        match = _FILENAME_RE.match(path.name)
        if match is None:
            if path.suffix == ".sql":
                raise MigrationError(f"bad migration filename: {path.name}")
            continue
        sql = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        found.append((match.group("version"), path.name, checksum))
    if not found:
        raise MigrationError(f"no migrations found in {migrations_dir}")
    return found


def applied_versions(conn: psycopg.Connection) -> dict[str, str]:
    """Return ``{version: checksum}`` for migrations already applied."""
    _ensure_registry(conn)
    rows = conn.execute(
        f"SELECT version, checksum FROM {MIGRATIONS_TABLE} ORDER BY version"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def apply_migrations(conn: psycopg.Connection, migrations_dir: Path | None = None) -> list[str]:
    """Apply pending migrations; returns the versions applied in this run."""
    directory = Path(migrations_dir) if migrations_dir is not None else DEFAULT_MIGRATIONS_DIR
    pending = _discover(directory)

    with conn.transaction():
        _ensure_registry(conn)
        already = applied_versions(conn)
        applied_now: list[str] = []
        for version, filename, checksum in pending:
            known = already.get(version)
            if known is not None:
                if known != checksum:
                    raise MigrationError(
                        f"migration {filename} changed after being applied "
                        f"(recorded {known[:12]}..., current {checksum[:12]}...)"
                    )
                continue
            sql = (directory / filename).read_text(encoding="utf-8")
            conn.execute(sql)
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
    migrations_dir = Path(args[0]) if args else None
    try:
        with psycopg.connect(dsn) as conn:
            applied = apply_migrations(conn, migrations_dir)
    except (MigrationError, psycopg.Error) as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1
    print(f"applied: {', '.join(applied)}" if applied else "already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
