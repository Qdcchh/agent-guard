"""Real PostgreSQL origin/prefix preservation and fail-closed catalog recognition."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from agent_guard.ledger.lineage import (
    _catalog,
    applied_lineage_versions,
    apply_bundle_migrations,
    load_manifest,
)
from agent_guard.ledger.migrate import MigrationError, applied_versions, apply_migrations
from agent_guard.ledger.service import ExecutionLedger
from tests.fixtures.isolation import acquire_namespace, release_namespace
from tests.fixtures.state import build_tree

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def target(namespace):
    ns = acquire_namespace(namespace.base_dsn)
    try:
        yield ns
    finally:
        release_namespace(ns)


def _prefix(target, tmp_path, source, count):
    folder = tmp_path / "prefix"
    folder.mkdir()
    manifest = load_manifest()
    entries = [m for m in manifest.migrations if m.namespace == "common"]
    entries += [
        m
        for m in manifest.migrations
        if m.namespace == ("execution" if source == "A" else "authorization") and m.version != "010"
    ]
    for migration in entries[:count]:
        data = (manifest.directory / migration.relative_path).read_bytes()
        assert hashlib.sha256(data).hexdigest() == migration.checksum
        (folder / migration.filename).write_bytes(data)
    if count:
        with psycopg.connect(target.dsn) as conn:
            apply_migrations(conn, folder)


def _dump(conn):
    schema = conn.execute("SELECT current_schema()").fetchone()[0]
    tables = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname=%s ORDER BY tablename", (schema,)
    ).fetchall()
    return {
        name: sorted(
            conn.execute(
                sql.SQL("SELECT row_to_json(t)::text FROM {} t").format(
                    sql.Identifier(schema, name)
                )
            ).fetchall()
        )
        for (name,) in tables
    }


def _no_probe(conn):
    assert conn.execute(
        "SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'ag_migration_probe_%%'"
    ).fetchone() == (0,)


@pytest.mark.parametrize("count", range(4, 10))
def test_public_a_view_rejects_b_legacy_before_bootstrap(target, tmp_path, count):
    _prefix(target, tmp_path, "B", count)
    with psycopg.connect(target.dsn) as conn:
        before = _dump(conn)
        with pytest.raises(MigrationError):
            with conn.transaction():
                applied_versions(conn)
        assert _dump(conn) == before
        apply_bundle_migrations(conn)
        assert all(_dump(conn)[key] == rows for key, rows in before.items())
        assert set(applied_versions(conn)) == {"001", "002", "003", "004", "005", "006"}


def test_completed_bundle_missing_evidence_namespace_refuses(target, downstream_dsn):
    from tests.integration.test_verified_execution import signed_env

    with psycopg.connect(target.dsn) as conn:
        apply_bundle_migrations(conn)
        assert apply_bundle_migrations(conn) == []
    env = signed_env(target.dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    with psycopg.connect(target.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operation_evidence").fetchone() == (1,)
        conn.execute(
            "ALTER TABLE ag_schema_migration_lineages DISABLE TRIGGER ag_schema_lineages_guard"
        )
        conn.execute(
            "DELETE FROM ag_schema_migration_lineages "
            "WHERE namespace='authorization' AND version='010'"
        )
        conn.execute(
            "ALTER TABLE ag_schema_migration_lineages ENABLE TRIGGER ag_schema_lineages_guard"
        )
        conn.execute("DROP TABLE ag_operation_evidence, ag_verified_evidence")
        conn.execute("DROP FUNCTION ag_verified_evidence_immutable()")
    with psycopg.connect(target.dsn) as conn:
        before = _dump(conn)
        schema = conn.execute("SELECT current_schema()").fetchone()[0]
        path = conn.execute("SHOW search_path").fetchone()[0]
        catalog = _catalog(conn, schema)
        conn.execute("SELECT set_config('search_path',%s,true)", (path,))
        with pytest.raises(MigrationError):
            with conn.transaction():
                apply_bundle_migrations(conn)
        assert _dump(conn) == before
        assert _catalog(conn, schema) == catalog
        conn.execute("SELECT set_config('search_path',%s,true)", (path,))
        assert conn.execute(
            "SELECT status FROM ag_operations WHERE operation_id=%s", (accepted.operation_id,)
        ).fetchone() == ("RESERVED",)
        _no_probe(conn)


@pytest.mark.parametrize(
    "source,count", [("A", i) for i in range(7)] + [("B", i) for i in range(4, 10)]
)
def test_every_legal_prefix_preserves_all_old_rows(target, tmp_path, source, count):
    _prefix(target, tmp_path, source, count)
    if count:
        with psycopg.connect(target.dsn) as conn:
            tree = build_tree(conn)
        ExecutionLedger(target.dsn).accept(tree.invocation(), tree.cost(100))
        with psycopg.connect(target.dsn) as conn:
            conn.execute("UPDATE ag_grants SET revoked=true WHERE grant_id=%s", (tree.mid_id,))
            conn.execute("UPDATE ag_principals SET active=false WHERE kid=%s", (tree.planner[1],))
    with psycopg.connect(target.dsn) as conn:
        before = _dump(conn)
        path = conn.execute("SHOW search_path").fetchone()[0]
        apply_bundle_migrations(conn)
        after = _dump(conn)
        assert all(after[k] == v for k, v in before.items())
        versions = applied_lineage_versions(conn)
        assert len(versions) == 14
        assert set(applied_versions(conn)) == {"001", "002", "003", "004", "005", "006"}
        assert apply_bundle_migrations(conn) == []
        assert _dump(conn) == after
        assert conn.execute("SHOW search_path").fetchone()[0] == path
        _no_probe(conn)
        if count:
            assert (
                conn.execute(
                    "SELECT amount_reserved,calls_reserved FROM ag_grants ORDER BY depth"
                ).fetchall()
                == [(100, 1)] * 3
            )


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE ag_schema_migrations SET filename='004_authorization_code.sql' WHERE version='004'",
        "UPDATE ag_schema_migrations SET checksum=repeat('0',64) WHERE version='001'",
        "DELETE FROM ag_schema_migrations WHERE version='002'",
        (
            "INSERT INTO ag_schema_migrations VALUES "
            "('099','099_unknown.sql',repeat('0',64),clock_timestamp())"
        ),
        "ALTER TABLE ag_principals ADD COLUMN counterfeit text",
        "ALTER TABLE ag_grants DROP CONSTRAINT ag_grants_call_limit_check",
        "ALTER TABLE ag_tasks DISABLE TRIGGER USER",
        (
            "CREATE OR REPLACE FUNCTION ag_root_delete_guard() RETURNS trigger "
            "AS $$ BEGIN RETURN OLD; END $$ LANGUAGE plpgsql"
        ),
        "CREATE TABLE ag_unregistered (x int)",
    ],
)
def test_legacy_corruption_is_atomic(target, tmp_path, mutation):
    _prefix(target, tmp_path, "A", 6)
    with psycopg.connect(target.dsn) as conn:
        # Discover named constraints/functions from exact source where needed.
        if mutation == "ALTER TABLE ag_grants DROP CONSTRAINT ag_grants_call_limit_check":
            row = conn.execute(
                (
                    "SELECT conname FROM pg_constraint WHERE "
                    "conrelid='ag_grants'::regclass AND contype='c' ORDER BY conname "
                    "LIMIT 1"
                )
            ).fetchone()
            conn.execute(
                sql.SQL("ALTER TABLE ag_grants DROP CONSTRAINT {}").format(sql.Identifier(row[0]))
            )
        elif "ag_root_delete_guard()" in mutation:
            conn.execute(
                (
                    "CREATE OR REPLACE FUNCTION ag_grants_root_delete_guard() RETURNS "
                    "trigger AS $$ BEGIN RETURN OLD; END $$ LANGUAGE plpgsql"
                )
            )
        else:
            conn.execute(mutation)
    with psycopg.connect(target.dsn) as conn:
        before = _dump(conn)
        path = conn.execute("SHOW search_path").fetchone()[0]
        schema = conn.execute("SELECT current_schema()").fetchone()[0]
        catalog = _catalog(conn, schema)
        # Catalog read intentionally sets its own normalized path; restore test context.
        conn.execute("SELECT set_config('search_path',%s,true)", (path,))
        with pytest.raises((MigrationError, psycopg.Error)):
            with conn.transaction():
                apply_bundle_migrations(conn)
        assert _dump(conn) == before
        assert _catalog(conn, schema) == catalog
        conn.execute("SELECT set_config('search_path',%s,true)", (path,))
        _no_probe(conn)


@pytest.mark.parametrize(
    "mutation",
    [
        (
            "ALTER TABLE ag_schema_migration_lineages DISABLE TRIGGER "
            "ag_schema_lineages_guard; UPDATE ag_schema_migration_lineages SET "
            "source_lineage='forged' WHERE namespace='execution'; ALTER TABLE "
            "ag_schema_migration_lineages ENABLE TRIGGER "
            "ag_schema_lineages_guard"
        ),
        (
            "UPDATE ag_schema_migrations SET applied_at=applied_at+interval '1 "
            "second' WHERE version='001'"
        ),
        "ALTER TABLE ag_verified_evidence DISABLE TRIGGER ag_verified_evidence_guard",
        "DROP INDEX ag_operation_first_evidence",
    ],
)
def test_initialized_bundle_corruption_refuses_without_mutation(target, mutation):
    with psycopg.connect(target.dsn) as conn:
        apply_bundle_migrations(conn)
    with psycopg.connect(target.dsn) as conn:
        conn.execute(mutation)
    with psycopg.connect(target.dsn) as conn:
        before = _dump(conn)
        with pytest.raises(MigrationError):
            with conn.transaction():
                apply_bundle_migrations(conn)
        assert _dump(conn) == before
        _no_probe(conn)


def test_original_sql_pinned_bytes_and_duplicate_versions(target, tmp_path):
    manifest = load_manifest()
    for migration in manifest.migrations:
        data = (manifest.directory / migration.relative_path).read_bytes()
        assert hashlib.sha256(data).hexdigest() == migration.checksum
    folder = tmp_path / "duplicates"
    folder.mkdir()
    (folder / "001_a.sql").write_text("CREATE TABLE ag_demo(x int)")
    (folder / "001_b.sql").write_text("CREATE TABLE ag_other(x int)")
    with psycopg.connect(target.dsn) as conn:
        before = _dump(conn)
        with pytest.raises(MigrationError, match="duplicate"):
            apply_migrations(conn, folder)
        assert _dump(conn) == before


@pytest.mark.parametrize("round_id", range(10))
def test_two_real_migration_processes_serialize(target, round_id):
    import os
    import subprocess
    import sys
    import time

    from agent_guard.ledger.lineage import _COORDINATOR

    script = """import os,psycopg
from agent_guard.ledger.lineage import apply_bundle_migrations
with psycopg.connect(os.environ['S1_TEST_DSN']) as c:
 print(c.info.backend_pid,flush=True)
 result=apply_bundle_migrations(c)
 print(len(result),flush=True)
"""
    env = dict(os.environ, S1_TEST_DSN=target.dsn)
    children = []
    with (
        psycopg.connect(target.dsn) as blocker,
        psycopg.connect(target.dsn, autocommit=True) as observer,
    ):
        blocker.execute("SELECT pg_advisory_xact_lock(%s)", (_COORDINATOR,))
        try:
            for _ in range(2):
                child = subprocess.Popen(
                    [sys.executable, "-B", "-c", script],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                children.append(child)
            pids = [int(p.stdout.readline().strip()) for p in children]
            assert len(set(pids)) == 2
            print(f"MIGRATION_RACE_WITNESS blocker={blocker.info.backend_pid} backends={pids}")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                blocked = observer.execute(
                    "SELECT pid FROM pg_stat_activity WHERE pid=ANY(%s) "
                    "AND %s=ANY(pg_blocking_pids(pid))",
                    (pids, blocker.info.backend_pid),
                ).fetchall()
                if len(blocked) == 2:
                    break
                time.sleep(0.01)
            else:
                raise AssertionError("both real processes did not reach migration coordinator")
            blocker.commit()
            counts = []
            for child in children:
                out, err = child.communicate(timeout=10)
                assert child.returncode == 0, err
                counts.append(int(out.strip()))
            assert sorted(counts) == [0, 7]
            assert len(applied_lineage_versions(observer)) == 14
            _no_probe(observer)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)


def test_actual_process_death_rolls_back_mid_upgrade(target, tmp_path):
    import os
    import signal
    import subprocess
    import sys
    import time

    _prefix(target, tmp_path, "B", 9)
    with psycopg.connect(target.dsn) as conn:
        before = _dump(conn)
    script = """import os,time,psycopg
import agent_guard.ledger.lineage as l
original=l._add
def pause(c,*a,**kw):
 original(c,*a,**kw)
 print('MID_DDL',flush=True)
 time.sleep(60)
l._add=pause
with psycopg.connect(os.environ['S1_TEST_DSN']) as c:
 print(c.info.backend_pid,flush=True)
 l.apply_bundle_migrations(c)
"""
    child = subprocess.Popen(
        [sys.executable, "-B", "-c", script],
        env=dict(os.environ, S1_TEST_DSN=target.dsn),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        backend = int(child.stdout.readline().strip())
        assert child.stdout.readline().strip() == "MID_DDL"
        child.send_signal(signal.SIGKILL)
        child.wait(timeout=5)
        assert child.returncode == -signal.SIGKILL
        print(
            f"MIGRATION_KILL_WITNESS process={child.pid} backend={backend} "
            f"returncode={child.returncode}"
        )
        with psycopg.connect(target.dsn, autocommit=True) as conn:
            deadline = time.monotonic() + 5
            while conn.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE pid=%s)", (backend,)
            ).fetchone()[0]:
                assert time.monotonic() < deadline
                time.sleep(0.01)
            assert _dump(conn) == before
            _no_probe(conn)
            apply_bundle_migrations(conn)
            assert len(applied_lineage_versions(conn)) == 14
            assert all(_dump(conn)[k] == v for k, v in before.items())
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_probe_timeout_restores_search_path_and_no_scratch(target, monkeypatch):
    import agent_guard.ledger.lineage as lineage

    with psycopg.connect(target.dsn) as conn:
        path = conn.execute("SHOW search_path").fetchone()[0]
        before = _dump(conn)
        original = lineage._catalog

        def timeout(connection, schema):
            if schema.startswith("ag_migration_probe_"):
                connection.execute("SET LOCAL statement_timeout='30ms'")
                connection.execute("SELECT pg_sleep(1)")
            return original(connection, schema)

        monkeypatch.setattr(lineage, "_catalog", timeout)
        with pytest.raises(psycopg.errors.QueryCanceled) as failure:
            with conn.transaction():
                apply_bundle_migrations(conn)
        assert failure.value.sqlstate == "57014"
        assert conn.execute("SHOW search_path").fetchone()[0] == path
        assert _dump(conn) == before
        _no_probe(conn)


@pytest.mark.parametrize("count", range(4, 10))
def test_b_origin_preserves_available_real_as_history(target, tmp_path, count):
    from datetime import datetime, timedelta, timezone

    from agent_guard.authorization.code_service import AuthorizationCodeService
    from agent_guard.authorization.consent import AuthorizeClient, ConsentService
    from agent_guard.authorization.grant_revocation_service import GrantRevocationService
    from agent_guard.authorization.login import LoginService
    from agent_guard.authorization.provisioning import register_task_policy, register_user
    from agent_guard.authorization.revocation_service import TaskRevocationService
    from tests.integration.test_exchange_service import (
        ISSUER,
        REDIRECT,
        TENANT,
        TOKEN_ENDPOINT,
        _exchange,
        _form,
        _root,
    )
    from tests.integration.test_grant_revocation_service import ADMIN, _register_admin
    from tests.integration.test_login_consent import CONSTRAINTS, PASSWORD, _params

    _prefix(target, tmp_path, "B", count)
    as_key, keys, registrations, exchanges, root = _root(target.dsn)
    child = None
    if count >= 5:
        form = _form(as_key, root.access_token)
        child = _exchange(exchanges, keys, registrations, form)
        assert _exchange(exchanges, keys, registrations, form).access_token == child.access_token
    if count >= 7:
        _register_admin(target.dsn)
        GrantRevocationService(target.dsn).revoke_grant(
            tenant_id=TENANT, grant_id=child.ag_grant_id, authenticated_admin_subject=ADMIN
        )
    if count >= 6:
        TaskRevocationService(target.dsn).revoke_task(
            tenant_id=TENANT, task_id="task-001", authenticated_subject="user-001"
        )
    if count >= 8:
        with psycopg.connect(target.dsn) as conn:
            register_user(conn, tenant_id=TENANT, subject="user-001", password=PASSWORD)
            register_task_policy(
                conn,
                tenant_id=TENANT,
                task_id="consent-history",
                owner_subject="user-001",
                scope="openid procurement.order.create",
                constraints=CONSTRAINTS,
                amount_limit_fen=100000,
                call_limit=10,
                task_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
        login = LoginService(target.dsn)
        csrf = login.issue_login_csrf()
        session = login.login(
            login_csrf=csrf,
            csrf_cookie=csrf,
            tenant_id=TENANT,
            subject="user-001",
            password=PASSWORD,
        )
        if count >= 9:
            codes = AuthorizationCodeService(
                target.dsn,
                issuer=ISSUER,
                token_endpoint=TOKEN_ENDPOINT,
                signing_key=as_key,
                signing_kid="as-sign-1",
                identities=exchanges._identities,
            )
            consent = ConsentService(
                target.dsn,
                clients={"agent-planner": AuthorizeClient("agent-planner", TENANT, REDIRECT)},
                sessions=login,
                codes=codes,
            )
            params = _params(ag_task_id="consent-history")
            request = consent.create_request(
                session_token=session.session_token, csrf_token=session.csrf_token, params=params
            )
            assert (
                "code="
                in consent.decide(
                    session_token=session.session_token,
                    csrf_token=session.csrf_token,
                    request_id=request.request_id,
                    decision="approve",
                ).location
            )
    with psycopg.connect(target.dsn) as conn:
        # Legitimate counter/key updates are part of the preserved old history.
        conn.execute(
            "UPDATE ag_grants SET amount_reserved=11,amount_settled=7,"
            "calls_reserved=1,calls_settled=1"
        )
        conn.execute("UPDATE ag_principals SET active=false")
    with psycopg.connect(target.dsn) as conn:
        before = _dump(conn)
        assert before["ag_authorization_codes"] and before["ag_auth_evidence"]
        assert before["ag_grant_tokens"]
        apply_bundle_migrations(conn)
        after = _dump(conn)
        # 009 adds the policy-version/snapshot columns, so old row columns must
        # be compared by original names rather than rejecting additive schema.
        for name, rows in before.items():
            expected = [json.loads(r[0]) for r in rows]
            actual = [json.loads(r[0]) for r in after[name]]
            if expected:
                fields = set(expected[0])
                assert sorted(
                    json.dumps({k: v for k, v in row.items() if k in fields}, sort_keys=True)
                    for row in actual
                ) == sorted(json.dumps(row, sort_keys=True) for row in expected)
            else:
                assert actual == []
        assert apply_bundle_migrations(conn) == []
        assert _dump(conn) == after
        _no_probe(conn)


@pytest.mark.parametrize("count", [4, 5, 6])
def test_a_origin_preserves_real_terminal_outbox(target, tmp_path, downstream_dsn, count):
    from agent_guard.tools.downstream import MockDownstream
    from tests.fixtures.execution import DOWNSTREAM_SECRET, build_env, order_params

    _prefix(target, tmp_path, "A", count)
    with psycopg.connect(target.dsn) as conn:
        tree = build_tree(conn)
    downstream = MockDownstream(downstream_dsn, service_secret=DOWNSTREAM_SECRET)
    downstream.provision()
    downstream.reset()
    env = build_env(tree=tree, gateway_dsn=target.dsn, downstream_dsn=downstream_dsn)
    result = env.service.accept_invocation(env.invocation(params=order_params()), env.permission())
    assert env.service.run_operation(result.operation_id).status == "SUCCEEDED"
    with psycopg.connect(target.dsn) as conn:
        before = _dump(conn)
        assert before["ag_receipt_outbox"] and before["ag_ledger_events"]
        apply_bundle_migrations(conn)
        after = _dump(conn)
        assert all(after[k] == v for k, v in before.items())
        assert conn.execute("SELECT count(*) FROM ag_operation_evidence").fetchone() == (0,)
        assert conn.execute(
            "SELECT receipt_status,receipt_jws FROM ag_receipt_outbox"
        ).fetchone() == ("PENDING", None)


def test_legacy_custom_filename_mismatch_is_not_silently_accepted(target, tmp_path):
    folder = tmp_path / "custom"
    folder.mkdir()
    (folder / "001_demo.sql").write_text("CREATE TABLE ag_demo (x int)")
    with psycopg.connect(target.dsn) as conn:
        apply_migrations(conn, folder)
    with psycopg.connect(target.dsn) as conn:
        conn.execute("UPDATE ag_schema_migrations SET filename='001_other.sql'")
    with psycopg.connect(target.dsn) as conn:
        before = _dump(conn)
        with pytest.raises(MigrationError):
            apply_migrations(conn, folder)
        assert _dump(conn) == before


def test_bundle_binding_independent_of_session_timezone(target):
    with psycopg.connect(target.dsn) as conn:
        apply_bundle_migrations(conn)
    with psycopg.connect(target.dsn) as conn:
        conn.execute("SET TIME ZONE 'Asia/Shanghai'")
        assert apply_bundle_migrations(conn) == []
        assert len(applied_lineage_versions(conn)) == 14


@pytest.mark.parametrize(
    "key",
    [("common", v) for v in ("001", "002", "003")]
    + [("execution", v) for v in ("004", "005", "006")]
    + [("authorization", v) for v in ("004", "005", "006", "007", "008", "009", "010")]
    + [("infrastructure", "001")],
)
def test_every_original_completion_entry_is_required_without_repair(target, key):
    with psycopg.connect(target.dsn) as conn:
        apply_bundle_migrations(conn)
        conn.execute(
            "ALTER TABLE ag_schema_migration_lineages DISABLE TRIGGER ag_schema_lineages_guard"
        )
        conn.execute(
            "DELETE FROM ag_schema_migration_lineages WHERE namespace=%s AND version=%s", key
        )
        conn.execute(
            "ALTER TABLE ag_schema_migration_lineages ENABLE TRIGGER ag_schema_lineages_guard"
        )
    with psycopg.connect(target.dsn) as conn:
        before = _dump(conn)
        with pytest.raises(MigrationError, match="missing"):
            with conn.transaction():
                apply_bundle_migrations(conn)
        assert _dump(conn) == before
        _no_probe(conn)


@pytest.mark.parametrize("count", range(7))
def test_public_a_view_preserves_each_legacy_a_prefix(target, tmp_path, count):
    _prefix(target, tmp_path, "A", count)
    with psycopg.connect(target.dsn) as conn:
        actual = applied_versions(conn)
        expected = {
            m.version: m.checksum
            for m in load_manifest().migrations
            if m.namespace in ("common", "execution") and int(m.version) <= count
        }
        assert actual == expected
