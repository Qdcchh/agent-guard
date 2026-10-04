"""Pinned provenance-preserving PostgreSQL 16 bundle migrations.

Recognition replays exact SQL in a rollback-only owned schema. Migration roles
require CREATE SCHEMA. Existing business data and legacy rows are never rewritten.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path

import psycopg
from psycopg import sql

from agent_guard.ledger.migrate import MigrationError, _ensure_registry, _migrations_dir

_COORDINATOR = 71437951721190301
# The first v2 bundle committed this exact set atomically. This historical
# completion floor is deliberately independent of future manifest additions.
_V2_COMPLETION_FLOOR = frozenset(
    [("common", v) for v in ("001", "002", "003")]
    + [("execution", v) for v in ("004", "005", "006")]
    + [("authorization", v) for v in ("004", "005", "006", "007", "008", "009", "010")]
    + [("infrastructure", "001")]
)
_PINNED = (
    (
        "common",
        "001",
        "001_init.sql",
        "001_init.sql",
        "d5e7bb01b9713b7fd9f80b5da85ea039bdf311e2d4a8b6a191d7c48eb43b148c",
        "153f14e9be180a1eb26b0f0e0898048d45170569",
        "b64d70e4cc7753fea94e673d4e1b9423aded2cde",
    ),
    (
        "common",
        "002",
        "002_root_invariants.sql",
        "002_root_invariants.sql",
        "bae1d72e1cf3dbe95ea73408e43196cdaa51297279319ac2dbf6111a68d44519",
        "153f14e9be180a1eb26b0f0e0898048d45170569",
        "51a98a5a21d688d249a5aeffe5c81322c6eb7b8e",
    ),
    (
        "common",
        "003",
        "003_root_delete_guard.sql",
        "003_root_delete_guard.sql",
        "1d919f8f59a8d4f4bfe49a278006dd4b79f1bb8d791e701ec604ae051ec7527b",
        "153f14e9be180a1eb26b0f0e0898048d45170569",
        "e97450d6b5e9658a11c8acac9085681c3ed2255b",
    ),
    (
        "execution",
        "004",
        "004_execution_lifecycle.sql",
        "004_execution_lifecycle.sql",
        "41527dc2926c379895527b16d71c059d9bf8adac6d1f0a930d48361cbc964c98",
        "153f14e9be180a1eb26b0f0e0898048d45170569",
        "6bda545911d3ff0c82e68829a8351374df9ba72f",
    ),
    (
        "execution",
        "005",
        "005_event_node_seal.sql",
        "005_event_node_seal.sql",
        "29529103ec7ffab8f785746edc4823a14e5e41d364010e3578e732e1a4e39c9e",
        "153f14e9be180a1eb26b0f0e0898048d45170569",
        "abe22624318f316d60bb737d37e82dfd39f2a018",
    ),
    (
        "execution",
        "006",
        "006_event_seal.sql",
        "006_event_seal.sql",
        "3abb279bc88b2fd7b2ff427a57fda407b77908182ec612334d500bea2f76760c",
        "153f14e9be180a1eb26b0f0e0898048d45170569",
        "01979b4a001ffa0b879837f430d3b2d304099c5c",
    ),
    (
        "authorization",
        "004",
        "004_authorization_code.sql",
        "b/004_authorization_code.sql",
        "ac8f9235fb5601453b225ff95a6ca16241a03c2ada0c0a6a8ae96cb7786c1957",
        "e521a461adb18d5fed89c8d1094647cb35eeff56",
        "311d6e3db3eb1266954427f9dd7b6c988066df0c",
    ),
    (
        "authorization",
        "005",
        "005_delegation.sql",
        "b/005_delegation.sql",
        "176f3743702022ded8b0d0691e4456a92c392884152f9e9142ffba91a68350f3",
        "e521a461adb18d5fed89c8d1094647cb35eeff56",
        "ac78ff91456a7f063c7e321d4e82b483bd113eb5",
    ),
    (
        "authorization",
        "006",
        "006_task_revocation.sql",
        "b/006_task_revocation.sql",
        "39a5f4b2c632f86d3511c7d69db04f576d33dfe1bfdc7a868e685a55ebf37784",
        "e521a461adb18d5fed89c8d1094647cb35eeff56",
        "3bcea2054b274992c523fedd8b1cb11ed2ab6491",
    ),
    (
        "authorization",
        "007",
        "007_admin_grant_revocation.sql",
        "b/007_admin_grant_revocation.sql",
        "6d7d44a2056d25f7c085c734b7ead77ffc36b0bec2d6f82cf3542a4d63fb3820",
        "e521a461adb18d5fed89c8d1094647cb35eeff56",
        "bede405dd065a3b3f2b38af6339cb26b48c0a757",
    ),
    (
        "authorization",
        "008",
        "008_login_consent.sql",
        "b/008_login_consent.sql",
        "6bfd359aff88c69909995b85fc15434d07390b93e3d2da9daf10ffe88b5e579e",
        "e521a461adb18d5fed89c8d1094647cb35eeff56",
        "fd0ae8c826d2c614498f8dad0cecc846874fe5dd",
    ),
    (
        "authorization",
        "009",
        "009_consent_policy_snapshot.sql",
        "b/009_consent_policy_snapshot.sql",
        "ee94ca3672497c0c0d5c67b04041afe12cf1618abb4f26363376dceea44974f1",
        "e521a461adb18d5fed89c8d1094647cb35eeff56",
        "8c371e706226c605557ebf8821b52a6c42ce7d4b",
    ),
    (
        "authorization",
        "010",
        "010_evidence_store.sql",
        "b/010_evidence_store.sql",
        "a694e2f523b7c44f2ef1d17238552ddf98252d8d37b00d34f19342237dd927e0",
        "B-remediation-integration",
        None,
    ),
    (
        "infrastructure",
        "001",
        "001_registry.sql",
        "lineage/001_registry.sql",
        "12da43d61229f481a3309e58ab73400615f8740644404e9698177942fe399a13",
        "B-remediation-integration",
        None,
    ),
)


@dataclass(frozen=True)
class Migration:
    namespace: str
    version: str
    filename: str
    relative_path: str
    checksum: str
    source_commit: str
    source_blob: str | None
    dependencies: tuple[tuple[str, str], ...]

    @property
    def key(self) -> tuple[str, str]:
        return self.namespace, self.version


@dataclass(frozen=True)
class BundleManifest:
    directory: Path
    migrations: tuple[Migration, ...]


def _entries() -> tuple[Migration, ...]:
    result = []
    for row in _PINNED:
        ns, version = row[:2]
        if ns == "infrastructure" or (ns == "common" and version == "001"):
            deps = ()
        elif version == "004":
            deps = (("common", "003"),)
        else:
            deps = ((ns, f"{int(version) - 1:03}"),)
        result.append(Migration(*row, deps))
    return tuple(result)


def load_manifest(directory: Path | None = None) -> BundleManifest:
    manifest = BundleManifest(
        Path(directory) if directory is not None else _migrations_dir(), _entries()
    )
    _validate_manifest(manifest)
    return manifest


def _validate_manifest(manifest: BundleManifest) -> None:
    if type(manifest) is not BundleManifest or manifest.migrations != _entries():
        raise MigrationError("unrecognized bundle manifest")
    for migration in manifest.migrations:
        try:
            data = (manifest.directory / migration.relative_path).read_bytes()
        except OSError as exc:
            raise MigrationError("bundle migration file unavailable") from exc
        if hashlib.sha256(data).hexdigest() != migration.checksum:
            raise MigrationError(f"bundle checksum mismatch: {migration.relative_path}")


def _sql_text(manifest: BundleManifest, migration: Migration) -> str:
    # Execute the same in-memory bytes whose hash was checked, rather than a
    # second unchecked read after manifest discovery.
    data = (manifest.directory / migration.relative_path).read_bytes()
    if hashlib.sha256(data).hexdigest() != migration.checksum:
        raise MigrationError("migration changed before execution")
    return data.decode("utf-8")


def _exists(conn: psycopg.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n "
        "ON n.oid=c.relnamespace WHERE n.nspname=current_schema() "
        "AND c.relname=%s)",
        (name,),
    ).fetchone()[0]


def _legacy_rows(conn: psycopg.Connection) -> list[tuple]:
    if not _exists(conn, "ag_schema_migrations"):
        return []
    kind = conn.execute(
        "SELECT c.relkind FROM pg_class c JOIN pg_namespace n "
        "ON n.oid=c.relnamespace WHERE n.nspname=current_schema() "
        "AND c.relname='ag_schema_migrations'"
    ).fetchone()
    if kind != ("r",):
        raise MigrationError("legacy registry must be an ordinary table")
    return conn.execute(
        "SELECT version, filename, checksum, applied_at FROM ag_schema_migrations ORDER BY version"
    ).fetchall()


def _legacy_json(rows: list[tuple]) -> str:
    return json.dumps(
        [[*row[:3], row[3].astimezone(timezone.utc).isoformat()] for row in rows],
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _recognize(rows: list[tuple], manifest: BundleManifest) -> tuple[str, list[Migration]]:
    common = [m for m in manifest.migrations if m.namespace == "common"]
    for source, ns in (("A", "execution"), ("B", "authorization")):
        branch = common + [
            m for m in manifest.migrations if m.namespace == ns and m.version != "010"
        ]
        if len(rows) <= len(branch) and all(
            row[:3] == (m.version, m.filename, m.checksum)
            for row, m in zip(rows, branch, strict=False)
        ):
            return ("common-only" if len(rows) <= 3 else source), branch[: len(rows)]
    raise MigrationError("unknown, mixed, gapped or modified legacy migration history")


def _catalog(conn: psycopg.Connection, schema: str) -> tuple:
    """Security-relevant catalog shape; never normalize expressions or source code."""
    # pg_get_* prints a namespace qualifier only when needed. Select the same
    # isolated search_path for both sides so only that known namespace differs.
    conn.execute(
        "SELECT set_config('search_path', %s, true)",
        (sql.Identifier(schema).as_string(conn) + ", pg_catalog",),
    )
    relation_filter = (
        "n.nspname=%s AND c.relname LIKE 'ag_%%' AND c.relname <> "
        "'ag_test_ownership' AND c.relkind IN ('r','p','v','m','S')"
    )
    queries = [
        "SELECT c.relname,c.relkind,c.relpersistence,c.relrowsecurity,c.relforcerowsecurity,"
        "c.reloptions,c.relacl::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        f"WHERE {relation_filter} AND c.relkind IN ('r','p','v','m','S') ORDER BY 1",
        "SELECT c.relname,a.attnum,a.attname,format_type(a.atttypid,a.atttypmod),"
        "a.attnotnull,a.attidentity,a.attgenerated,co.collname,"
        "pg_get_expr(d.adbin,d.adrelid) FROM pg_attribute a "
        "JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum "
        "LEFT JOIN pg_collation co ON co.oid=a.attcollation "
        f"WHERE {relation_filter} AND a.attnum>0 AND NOT a.attisdropped ORDER BY 1,2",
        "SELECT c.relname,k.conname,k.contype,k.condeferrable,k.condeferred,k.convalidated,"
        "pg_get_constraintdef(k.oid,false) FROM pg_constraint k "
        "JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        f"WHERE {relation_filter} ORDER BY 1,2",
        "SELECT c.relname,ic.relname,i.indisvalid,i.indisready,pg_get_indexdef(i.indexrelid) "
        "FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid "
        "JOIN pg_class ic ON ic.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        f"WHERE {relation_filter} ORDER BY 1,2",
        "SELECT c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid,false) "
        "FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        f"WHERE {relation_filter} AND NOT t.tgisinternal ORDER BY 1,2",
        "SELECT p.proname,pg_get_function_identity_arguments(p.oid),pg_get_functiondef(p.oid),"
        "p.prosecdef,p.proleakproof,p.provolatile,p.proparallel,p.proconfig,p.proacl::text "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname=%s AND p.proname LIKE 'ag_%%' ORDER BY 1,2",
        "SELECT c.relname,s.seqtypid::regtype::text,s.seqstart,s.seqincrement,"
        "s.seqmax,s.seqmin,s.seqcache,s.seqcycle FROM pg_sequence s "
        "JOIN pg_class c ON c.oid=s.seqrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        f"WHERE {relation_filter} ORDER BY 1",
        "SELECT c.relname,p.polname,p.polcmd,p.polpermissive,p.polroles::text,"
        "pg_get_expr(p.polqual,p.polrelid),pg_get_expr(p.polwithcheck,p.polrelid) "
        "FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        f"WHERE {relation_filter} ORDER BY 1,2",
    ]

    def normalize(value):
        if isinstance(value, str):
            # Only known namespace qualification; preserve the complete SQL.
            return value.replace(sql.Identifier(schema).as_string(conn) + ".", "<schema>.").replace(
                schema + ".", "<schema>."
            )
        if isinstance(value, (list, tuple)):
            return tuple(normalize(x) for x in value)
        return value

    return tuple(normalize(conn.execute(query, (schema,)).fetchall()) for query in queries)


def _check_catalog(
    conn: psycopg.Connection, manifest: BundleManifest, expected: list[Migration], *, registry: bool
) -> None:
    original_path = conn.execute("SHOW search_path").fetchone()[0]
    target = conn.execute("SELECT current_schema()").fetchone()[0]
    if target is None:
        raise MigrationError("migration target requires an existing owned schema")
    scratch = "ag_migration_probe_" + secrets.token_hex(16)
    try:
        with conn.transaction():
            actual = _catalog(conn, target)
            # Always roll back this savepoint, even on successful recognition.
            with conn.transaction(force_rollback=True):
                conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(scratch)))
                conn.execute(
                    "SELECT set_config('search_path', %s, true)",
                    (sql.Identifier(scratch).as_string(conn) + ", pg_catalog",),
                )
                if registry:
                    _ensure_registry(conn)
                for migration in expected:
                    conn.execute(_sql_text(manifest, migration))
                desired = _catalog(conn, scratch)
            if actual != desired:
                raise MigrationError("registered migration history does not match exact catalog")

    finally:
        # The rollback-only savepoint clears errors before restoring the path.
        # A broken transport/aborted outer transaction is allowed to propagate.
        conn.execute("SELECT set_config('search_path', %s, true)", (original_path,))


def _add(
    conn: psycopg.Connection, migration: Migration, *, origin: str, source: str, original_time=None
) -> None:
    conn.execute(
        "INSERT INTO ag_schema_migration_lineages "
        "(namespace,version,original_filename,checksum,origin,source_lineage,"
        "original_applied_at,applied_at) VALUES (%s,%s,%s,%s,%s,%s,%s,"
        "COALESCE(%s,clock_timestamp()))",
        (
            *migration.key,
            migration.filename,
            migration.checksum,
            origin,
            source,
            original_time,
            original_time,
        ),
    )


def _validated_state(conn: psycopg.Connection, manifest: BundleManifest) -> list[Migration]:
    legacy = _legacy_rows(conn)
    source, original = _recognize(legacy, manifest)
    infra = next(m for m in manifest.migrations if m.namespace == "infrastructure")
    bindings = conn.execute(
        "SELECT source_lineage,registry_json,registry_sha256,"
        "infrastructure_sha256 FROM ag_schema_legacy_binding"
    ).fetchall()
    raw = _legacy_json(legacy)
    expected_binding = (source, raw, hashlib.sha256(raw.encode()).hexdigest(), infra.checksum)
    if bindings != [expected_binding]:
        raise MigrationError("legacy registry binding changed or is missing")
    rows = conn.execute(
        "SELECT namespace,version,original_filename,checksum,origin,"
        "source_lineage,original_applied_at,applied_at "
        "FROM ag_schema_migration_lineages ORDER BY namespace,version"
    ).fetchall()
    known = {m.key: m for m in manifest.migrations}
    original_rows = {m.key: row for m, row in zip(original, legacy, strict=True)}
    present = set()
    for ns, version, filename, checksum, origin, lineage, original_time, applied_time in rows:
        key = ns, version
        migration = known.get(key)
        if migration is None or (filename, checksum) != (migration.filename, migration.checksum):
            raise MigrationError("unknown or modified lineage record")
        old = original_rows.get(key)
        if old is not None:
            if (origin, lineage, original_time, applied_time) != (
                "legacy-import",
                source,
                old[3],
                old[3],
            ):
                raise MigrationError("modified imported provenance")
        elif (origin, lineage, original_time) != ("new", migration.source_commit, None):
            raise MigrationError("invalid new migration provenance")
        present.add(key)
    if not set(original_rows) <= present or infra.key not in present:
        raise MigrationError("missing migration provenance")
    if not _V2_COMPLETION_FLOOR <= present:
        raise MigrationError("completed v2 bundle migration history is missing")
    for key in present:
        if not set(known[key].dependencies) <= present:
            raise MigrationError("lineage dependency gap")
    ordered = [m for m in manifest.migrations if m.key in present]
    _check_catalog(conn, manifest, ordered, registry=True)
    return ordered


def apply_bundle_migrations(
    conn: psycopg.Connection, manifest: BundleManifest | None = None
) -> list[tuple[str, str]]:
    """Validate and atomically merge recognized A/B history under one bounded lock."""
    manifest = load_manifest() if manifest is None else manifest
    _validate_manifest(manifest)
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout = '10s'")
        conn.execute("SET LOCAL statement_timeout = '15s'")
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_COORDINATOR,))
        if _exists(conn, "ag_schema_migration_lineages") != _exists(
            conn, "ag_schema_legacy_binding"
        ):
            raise MigrationError("orphan lineage registry")
        if _exists(conn, "ag_schema_migration_lineages"):
            applied = _validated_state(conn, manifest)
        else:
            rows = _legacy_rows(conn)
            source, applied = _recognize(rows, manifest)
            _check_catalog(conn, manifest, applied, registry=_exists(conn, "ag_schema_migrations"))
            if not rows:
                # A-compatible initialization is deliberately recorded in the
                # old registry before binding it, as on a normal empty A DB.
                _ensure_registry(conn)
                for m in manifest.migrations:
                    if m.namespace not in ("common", "execution"):
                        continue
                    conn.execute(_sql_text(manifest, m))
                    conn.execute(
                        "INSERT INTO ag_schema_migrations (version,filename,checksum) "
                        "VALUES (%s,%s,%s)",
                        (m.version, m.filename, m.checksum),
                    )
                rows = _legacy_rows(conn)
                source, applied = _recognize(rows, manifest)
            infra = next(m for m in manifest.migrations if m.namespace == "infrastructure")
            conn.execute(_sql_text(manifest, infra))
            raw = _legacy_json(rows)
            conn.execute(
                "INSERT INTO ag_schema_legacy_binding "
                "(source_lineage,registry_json,registry_sha256,infrastructure_sha256) "
                "VALUES (%s,%s,%s,%s)",
                (source, raw, hashlib.sha256(raw.encode()).hexdigest(), infra.checksum),
            )
            for m, row in zip(applied, rows, strict=True):
                _add(conn, m, origin="legacy-import", source=source, original_time=row[3])
            _add(conn, infra, origin="new", source=infra.source_commit)
            applied = [*applied, infra]
        present = {m.key for m in applied}
        newly = []
        for migration in manifest.migrations:
            if migration.key in present:
                continue
            if not set(migration.dependencies) <= present:
                raise MigrationError("unsatisfied migration dependency")
            conn.execute(_sql_text(manifest, migration))
            _add(conn, migration, origin="new", source=migration.source_commit)
            present.add(migration.key)
            newly.append(migration.key)
        _validated_state(conn, manifest)
        return newly


def applied_lineage_versions(conn: psycopg.Connection) -> dict[tuple[str, str], str]:
    """Read the full validated namespace view; no implicit upgrade."""
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout = '10s'")
        conn.execute("SET LOCAL statement_timeout = '15s'")
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_COORDINATOR,))
        return {m.key: m.checksum for m in _validated_state(conn, load_manifest())}
