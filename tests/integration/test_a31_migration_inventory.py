"""Original14 immutable SQL plus actual GW15 and independent audit001 CLI inventory."""

import hashlib
import os
import subprocess
import sys

import psycopg
import pytest

from agent_guard.audit.migrate import AUDIT_SQL_SHA256
from agent_guard.ledger.lineage import applied_lineage_versions, load_manifest
from tests.fixtures.a31_audit_service import record_native
from tests.fixtures.a31_joint import private_json, run_operator
from tests.fixtures.isolation import create_scratch_database, drop_scratch_database

pytestmark = pytest.mark.integration
ORIGINAL14 = {
    "001_init.sql": "d5e7bb01b9713b7fd9f80b5da85ea039bdf311e2d4a8b6a191d7c48eb43b148c",
    "002_root_invariants.sql": "bae1d72e1cf3dbe95ea73408e43196cdaa51297279319ac2dbf6111a68d44519",
    "003_root_delete_guard.sql": "1d919f8f59a8d4f4bfe49a278006dd4b79f1bb8d791e701ec604ae051ec7527b",
    "004_execution_lifecycle.sql": (
        "41527dc2926c379895527b16d71c059d9bf8adac6d1f0a930d48361cbc964c98"
    ),
    "005_event_node_seal.sql": "29529103ec7ffab8f785746edc4823a14e5e41d364010e3578e732e1a4e39c9e",
    "006_event_seal.sql": "3abb279bc88b2fd7b2ff427a57fda407b77908182ec612334d500bea2f76760c",
    "b/004_authorization_code.sql": (
        "ac8f9235fb5601453b225ff95a6ca16241a03c2ada0c0a6a8ae96cb7786c1957"
    ),
    "b/005_delegation.sql": "176f3743702022ded8b0d0691e4456a92c392884152f9e9142ffba91a68350f3",
    "b/006_task_revocation.sql": "39a5f4b2c632f86d3511c7d69db04f576d33dfe1bfdc7a868e685a55ebf37784",
    "b/007_admin_grant_revocation.sql": (
        "6d7d44a2056d25f7c085c734b7ead77ffc36b0bec2d6f82cf3542a4d63fb3820"
    ),
    "b/008_login_consent.sql": "6bfd359aff88c69909995b85fc15434d07390b93e3d2da9daf10ffe88b5e579e",
    "b/009_consent_policy_snapshot.sql": (
        "ee94ca3672497c0c0d5c67b04041afe12cf1618abb4f26363376dceea44974f1"
    ),
    "b/010_evidence_store.sql": "a694e2f523b7c44f2ef1d17238552ddf98252d8d37b00d34f19342237dd927e0",
    "lineage/001_registry.sql": "12da43d61229f481a3309e58ab73400615f8740644404e9698177942fe399a13",
}
CURRENT007 = "4ae5b1c1a2d6d2cdd4355a43961a13fccdb3dbff0661278dd78ea347326fd1de"


def test_full_original14_current15_cli_inventory_and_idempotence(dsn, namespace):
    scratch = create_scratch_database(namespace.base_dsn)
    env = dict(os.environ, AGENT_GUARD_TEST_DATABASE_URL=scratch.dsn)
    env.pop("AGENT_GUARD_DATABASE_URL", None)
    try:
        with psycopg.connect(scratch.dsn) as c:
            before_tables = c.execute(
                "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
            ).fetchone()[0]
            assert before_tables == 0
        for i in range(2):
            p = subprocess.run(
                [sys.executable, "-m", "agent_guard.ledger.migrate", "--bundle"],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            record_native(
                "joint-migrate-cli",
                {
                    "argv": [sys.executable, "-m", "agent_guard.ledger.migrate", "--bundle"],
                    "returncode": p.returncode,
                    "stdout": p.stdout,
                    "stderr": p.stderr,
                },
            )
            assert p.returncode == 0, "private CLI output retained by owned runner"
            if i == 0:
                assert p.stdout.strip() == "applied: " + ", ".join(
                    ["authorization:" + f"{n:03}" for n in range(4, 11)] + ["execution:007"]
                )
            else:
                assert p.stdout.strip() == "already up to date"
            with psycopg.connect(scratch.dsn) as c:
                versions = applied_lineage_versions(c)
                assert len(versions) == 15
                registry = c.execute(
                    (
                        "SELECT row_to_json(t)::text FROM "
                        "ag_schema_migration_lineages t ORDER BY row_to_json(t)::text"
                    )
                ).fetchall()
                if i == 0:
                    first, first_registry = versions, registry
                else:
                    assert versions == first
                    assert registry == first_registry  # includes applied_at, not only checksums
        manifest = load_manifest()
        expected = {**ORIGINAL14, "007_audit_journal.sql": CURRENT007}
        sql = []
        for m in manifest.migrations:
            h = hashlib.sha256((manifest.directory / m.relative_path).read_bytes()).hexdigest()
            assert h == expected[m.relative_path]
            assert versions[m.key] == m.checksum == h
            if m.relative_path in ORIGINAL14:
                sql.append(m.relative_path)
        assert len(sql) == 14
        assert set(sql) == set(ORIGINAL14)
        assert set(versions) == {m.key for m in manifest.migrations}
        assert len(manifest.migrations) == 15
        original_versions = {
            m.key: versions[m.key] for m in manifest.migrations if m.relative_path in ORIGINAL14
        }
        assert len(original_versions) == 14
        assert original_versions == {
            m.key: ORIGINAL14[m.relative_path]
            for m in manifest.migrations
            if m.relative_path in ORIGINAL14
        }
    finally:
        drop_scratch_database(dsn, scratch)


def test_independent_audit001_cli_inventory_owner_and_idempotence(tmp_path):
    base = os.environ["AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL"]
    scratch = create_scratch_database(base)
    try:
        with psycopg.connect(scratch.dsn) as conn:
            assert conn.execute(
                "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
            ).fetchone() == (0,)
            owner = conn.execute("SELECT current_user").fetchone()[0]
        connection = private_json(
            tmp_path / "operator" / "connection.json", {"dsn": scratch.dsn, "owner_role": owner}
        )
        assert run_operator(connection, "init").returncode == 0
        with psycopg.connect(scratch.dsn) as conn:
            first = conn.execute(
                "SELECT * FROM ag_audit_schema_migrations ORDER BY version"
            ).fetchall()
            assert len(first) == 1
            assert first[0][0:3] == ("001", "001_checkpoint_store.sql", AUDIT_SQL_SHA256)
            assert first[0][-2:] == ("AG-INDEPENDENT-AUDIT-1", owner)
            for forbidden in (
                "ag_tasks",
                "ag_operations",
                "ds_operations",
                "ag_schema_migration_lineages",
            ):
                assert conn.execute("SELECT to_regclass(%s)", (forbidden,)).fetchone() == (None,)
        raw = (load_manifest().directory / "audit" / "001_checkpoint_store.sql").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == AUDIT_SQL_SHA256
        assert run_operator(connection, "init").returncode == 0
        assert run_operator(connection, "check").returncode == 0
        with psycopg.connect(scratch.dsn) as conn:
            assert (
                conn.execute("SELECT * FROM ag_audit_schema_migrations ORDER BY version").fetchall()
                == first
            )
    finally:
        drop_scratch_database(base, scratch)
