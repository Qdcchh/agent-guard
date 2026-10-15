"""Migration closure, NULL-safe SQL schemas, and immutable reverse witnesses."""

import hashlib

import psycopg
import pytest

from agent_guard.audit.contracts import canonical_json_bytes
from agent_guard.contracts.encoding import load_strict_json
from agent_guard.ledger.lineage import apply_bundle_migrations, load_manifest
from agent_guard.ledger.migrate import apply_migrations
from tests.fixtures.a31_common import FACTS, codec_record, state
from tests.fixtures.gateway import query_bundle
from tests.fixtures.isolation import acquire_namespace, release_namespace
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", tuple(FACTS))
@pytest.mark.parametrize("mutation", ("missing", "null", "bool", "unknown"))
def test_sql_required_fact_schema_rejects_missing_and_ambiguous(ledger, dsn, kind, mutation):
    valid = codec_record(kind)
    with psycopg.connect(dsn) as conn:
        conn.execute("SELECT ag_audit_wire_schema(%s,%s)", (valid, kind))
        value = load_strict_json(valid)
        key = next(k for k in value["facts"] if k != "first_evidence_ref")
        if mutation == "missing":
            value["facts"].pop(key)
        elif mutation == "unknown":
            value["facts"]["unknown_security_field"] = "x"
        else:
            value["facts"][key] = None if mutation == "null" else True
        with pytest.raises(psycopg.Error) as caught:
            with conn.transaction():
                conn.execute(
                    "SELECT ag_audit_wire_schema(%s,%s)",
                    (canonical_json_bytes(value), kind),
                )
        assert caught.value.sqlstate == "23514"


def test_standalone_old_six_then_qualified_audit_upgrade(namespace):
    target = acquire_namespace(namespace.base_dsn)
    try:
        with psycopg.connect(target.dsn) as conn:
            assert apply_migrations(conn) == ["001", "002", "003", "004", "005", "006"]
            assert conn.execute("SELECT to_regclass('ag_audit_streams')").fetchone() == (None,)
            apply_bundle_migrations(conn)
            assert apply_bundle_migrations(conn) == []
            assert conn.execute("SELECT count(*) FROM ag_schema_migration_lineages").fetchone() == (
                15,
            )
        entry = next(
            m
            for m in load_manifest().migrations
            if m.namespace == "execution" and m.version == "007"
        )
        assert (
            hashlib.sha256(
                (load_manifest().directory / entry.relative_path).read_bytes()
            ).hexdigest()
            == entry.checksum
        )
    finally:
        release_namespace(target)


@pytest.mark.parametrize("round", range(10))
def test_late_query_record_cannot_reuse_historical_proof(ledger, dsn, downstream_dsn, round):
    from agent_guard.execution.query import AuthorizedQuery

    env = signed_env(dsn, downstream_dsn)
    op = env.adapter.accept(env.bundle()).operation_id
    AuthorizedQuery(dsn, evidence_store=env.evidence).query(query_bundle(env, op))
    before = state(dsn, downstream_dsn)
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT "
            "stream_id,seq,record_id,kind,operation_id,evidence_ref,previous_d"
            "igest,digest,raw,material_binding_bytes,recorded_at,created_xid "
            "FROM ag_audit_records WHERE kind='QUERY'"
        ).fetchone()
        data = load_strict_json(bytes(row[8]))
        data["seq"] += 1
        data["previous_digest"] = row[7]
        raw = canonical_json_bytes(data)
        with pytest.raises(psycopg.Error) as caught:
            with conn.transaction():
                conn.execute(
                    "INSERT INTO ag_audit_records "
                    "(stream_id,seq,record_id,kind,operation_id,evidence_ref,previous_"
                    "digest,digest,raw,material_binding_bytes,recorded_at,created_xid)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        row[0],
                        data["seq"],
                        row[2],
                        row[3],
                        row[4],
                        row[5],
                        row[7],
                        row[7],
                        raw,
                        row[9],
                        row[10],
                        row[11],
                    ),
                )
        assert caught.value.sqlstate == "23514"
    assert state(dsn, downstream_dsn) == before


@pytest.mark.parametrize("round", range(10))
def test_maintenance_baseline_preserves_legacy_rows_and_owned_reset_closure(
    ledger, tree, dsn, downstream_dsn, namespace, round
):
    from agent_guard.audit import journal
    from tests.fixtures.isolation import reset_state

    # Explicitly layered historical A1 intent; no signature claim is made.
    accepted = ledger.accept(tree.invocation(), tree.cost(70000))
    before = state(dsn, downstream_dsn)
    assert not before["gateway"]["ag_audit_streams"]
    scope = (journal.gateway_origin(), tree.tenant_id, tree.task_id)
    with psycopg.connect(dsn) as conn:
        registration = journal.bootstrap_task_tx(conn, scope_key=scope)
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
        assert registration.boundary == "LEGACY_WITH_GAPS"
        assert registration.object_count and registration.chunk_count and registration.wire_bytes
    after = state(dsn, downstream_dsn)
    for name, rows in before["gateway"].items():
        if not name.startswith("ag_audit_"):
            assert after["gateway"][name] == rows
    assert after["downstream"] == before["downstream"]
    with psycopg.connect(dsn) as conn:
        assert conn.execute(
            "SELECT status FROM ag_operations WHERE operation_id=%s",
            (accepted.operation_id,),
        ).fetchone() == ("RESERVED",)
        assert conn.execute("SELECT kind FROM ag_audit_records ORDER BY seq").fetchall() == [
            ("BOOTSTRAP",)
        ]
        repeated = journal.bootstrap_task_tx(conn, scope_key=scope)
        assert repeated == registration
    assert state(dsn, downstream_dsn) == after
    reset_state(namespace)
    with psycopg.connect(dsn) as conn:
        for name in (
            "ag_audit_delivery",
            "ag_audit_delivery_batches",
            "ag_audit_records",
            "ag_audit_bootstrap_chunks",
            "ag_audit_bootstrap",
            "ag_audit_streams",
            "ag_event_seals",
        ):
            from psycopg import sql

            assert conn.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(name))
            ).fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM ag_schema_migration_lineages").fetchone() == (15,)


@pytest.mark.parametrize(
    "field",
    ("wire_bytes", "index_root", "objects", "chunks", "manifest_bytes", "origin"),
)
def test_seed_complete_projection_tampering_rolls_back_first(
    ledger, dsn, downstream_dsn, monkeypatch, field
):
    from dataclasses import replace

    from agent_guard.audit import journal
    from tests.fixtures.a31_common import DIGEST

    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    before = state(dsn, downstream_dsn)
    original = journal.ensure_stream_tx

    def ensure(conn, seed):
        if field == "wire_bytes":
            value = seed.wire_bytes - 1
        elif field == "index_root":
            value = DIGEST
        elif field == "objects":
            value = seed.objects[:-1]
        elif field == "chunks":
            value = seed.chunks[:-1]
        elif field == "manifest_bytes":
            value = seed.manifest_bytes + b" "
        else:
            value = "UNTRUSTED"
        return original(conn, replace(seed, **{field: value}))

    monkeypatch.setattr(journal, "ensure_stream_tx", ensure)
    with pytest.raises(journal.JournalError):
        env.adapter.accept(bundle)
    assert state(dsn, downstream_dsn) == before


def test_independent_audit_001_inventory_and_least_privilege_database_boundary(dsn):
    import os
    import secrets
    import sys
    from pathlib import Path

    from psycopg import conninfo, sql

    audit_dsn = os.environ["AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL"]
    target = acquire_namespace(audit_dsn)
    role = "ag31_runtime_" + target.run_id
    password = secrets.token_urlsafe(32)
    created_role = False
    inventory = {
        "ag_checkpoint_streams",
        "ag_checkpoint_records",
        "ag_checkpoint_batches",
        "ag_checkpoints",
        "ag_audit_principals",
        "ag_audit_checkpoint_keys",
    }
    paths = list(Path(sys.prefix).glob("share/**/audit/001_checkpoint_store.sql"))
    assert len(paths) == 1
    data = paths[0].read_bytes()
    try:
        with psycopg.connect(target.dsn) as owner:
            owner.execute(data.decode())
            tables = {
                name
                for (name,) in owner.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname=current_schema()"
                )
            }
            assert tables == inventory | {"ag_test_ownership"}
            owner.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE"
                ).format(sql.Identifier(role), sql.Literal(password))
            )
            created_role = True
            owner.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(target.schema), sql.Identifier(role)
                )
            )
            owner.execute(
                sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                    sql.Identifier(target.schema), sql.Identifier(role)
                )
            )
        runtime_dsn = conninfo.make_conninfo(target.dsn, user=role, password=password)
        with psycopg.connect(runtime_dsn) as runtime:
            assert runtime.execute(
                "SELECT current_user,current_database(),current_schema()"
            ).fetchone() == (role, target.database, target.schema)
            assert runtime.execute(
                "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user"
            ).fetchone() == (False, False, False)
            for name in inventory:
                assert runtime.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(name))
                ).fetchone() == (0,)
            with pytest.raises(psycopg.Error) as caught:
                with runtime.transaction():
                    runtime.execute("CREATE TABLE forbidden_runtime_ddl (id integer)")
            assert caught.value.sqlstate == "42501"
        # The dedicated audit login does not exist at the independent gateway PG.
        wrong_gateway = conninfo.make_conninfo(dsn, user=role, password=password)
        with pytest.raises(psycopg.OperationalError):
            psycopg.connect(wrong_gateway).close()
        with psycopg.connect(dsn) as gateway:
            assert gateway.execute("SELECT to_regclass('ag_checkpoint_streams')").fetchone() == (
                None,
            )
        print(
            "AUDIT001_INSTALLED_MEMBER",
            str(paths[0]),
            hashlib.sha256(data).hexdigest(),
            sorted(inventory),
        )
    finally:
        release_namespace(target)
        if created_role:
            with psycopg.connect(audit_dsn, autocommit=True) as owner:
                owner.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def _actual_as_branch_env(dsn, downstream_dsn):
    from tests.integration import test_verified_execution as original

    captured_root, captured_exchange = [], []
    root, exchange = original._root, original._exchange

    def capture_root(*args, **kwargs):
        value = root(*args, **kwargs)
        captured_root.append(value)
        return value

    def capture_exchange(*args, **kwargs):
        value = exchange(*args, **kwargs)
        captured_exchange.append(value)
        return value

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(original, "_root", capture_root)
        patch.setattr(original, "_exchange", capture_exchange)
        env = original.signed_env(dsn, downstream_dsn)
    assert len(captured_root) == 1 and len(captured_exchange) == 2
    return env, captured_root[0][3], captured_exchange[0]


def _actual_new_as_leaf(env, exchanges, child):
    from dataclasses import replace

    from tests.integration import test_verified_execution as original

    form = original._form(env.as_key, child.access_token, recipient="executor", ttl=60)
    form["scope"] = " ".join(original.TOOLS)
    leaf = original._exchange(exchanges, env.keys, env.registrations, form, holder="selector")
    return replace(env, token=leaf.access_token), leaf.ag_grant_id


@pytest.mark.parametrize("round", range(10))
def test_real_post_bootstrap_as_branch_introduced_zero_and_known_reuse(
    ledger, dsn, downstream_dsn, round
):
    import json

    from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
    from agent_guard.crypto.sm import sm3_b64url, verify_compact_jws
    from tests.fixtures.a31_common import namespace_evidence, read_records
    from tests.fixtures.receipts import accept_created_only, accept_introduced_only

    env, exchanges, child = _actual_as_branch_env(dsn, downstream_dsn)
    env.adapter.accept(
        env.bundle(
            "old-zero-read", tool="procurement.request.read", params={"request_id": "req-001"}
        )
    )
    new_env, leaf_id = _actual_new_as_leaf(env, exchanges, child)
    signed = verify_compact_jws(
        new_env.token,
        expected_type="ag-at+jwt",
        trusted_keys={"as-sign-1": env.as_key.public_key()},
    )
    assert signed["ag_grant_id"] == leaf_id
    bundle = new_env.bundle("new-branch-order")
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT grant_id,parent_grant_id,root_grant_id,depth,holder_client_id,hol"
            "der_kid,amount_reserved,amount_settled,calls_reserved,calls_settled FROM"
            " ag_grants WHERE grant_id=%s",
            (leaf_id,),
        ).fetchone()
        (token,) = conn.execute(
            "SELECT token_jws FROM ag_grant_tokens WHERE grant_id=%s", (leaf_id,)
        ).fetchone()
    assert row[6:] == (0, 0, 0, 0) and token == new_env.token
    expected = dict(
        zip(
            ("grant_id", "parent_id", "root_id", "depth", "holder_client_id", "holder_kid"),
            row[:6],
            strict=True,
        )
    )
    expected.update(
        grant_token_digest=sm3_b64url(token.encode("ascii")),
        source_material_digest=sm3_b64url(bundle.source.material()),
        amount_reserved=0,
        amount_settled=0,
        calls_reserved=0,
        calls_settled=0,
    )
    before = state(dsn, downstream_dsn)
    result = new_env.adapter.accept(bundle)
    after = state(dsn, downstream_dsn)
    assert result.cost.amount_fen == 70000
    accept_introduced_only(
        before,
        after,
        bundle=bundle,
        result=result,
        introduced_grants=(canonical_json_bytes(expected),),
    )
    known = new_env.bundle(
        "known-new-zero-read", tool="procurement.request.read", params={"request_id": "req-001"}
    )
    reuse_before = state(dsn, downstream_dsn)
    reused = new_env.adapter.accept(known)
    reuse_after = state(dsn, downstream_dsn)
    accept_created_only(reuse_before, reuse_after, bundle=known, result=reused)
    records = read_records(dsn)
    assert [r.kind for r in records] == ["BOOTSTRAP", "FIRST", "FIRST", "FIRST"]
    assert load_strict_json(records[2].facts_bytes)["introduced_grants"] == [expected]
    assert load_strict_json(records[3].facts_bytes)["introduced_grants"] == []
    with psycopg.connect(dsn) as conn:
        counters = conn.execute(
            "SELECT grant_id,amount_reserved,amount_settled,calls_reserved,calls_sett"
            "led FROM ag_grants ORDER BY grant_id"
        ).fetchall()
    # Both initial and known reads consume calls; only the new path reserves money.
    path = bundle.source.snapshot.chain_grant_ids
    assert {grant: tuple(values) for grant, *values in counters if grant in path} == {
        path[0]: (70000, 0, 3, 0),
        path[1]: (70000, 0, 3, 0),
        path[2]: (70000, 0, 2, 0),
    }
    terminal_before = state(dsn, downstream_dsn)
    terminal_result = new_env.service.run_operation(result.operation_id)
    assert terminal_result.status == "SUCCEEDED"
    terminal_after = state(dsn, downstream_dsn)
    terminal_records = read_records(dsn)
    assert terminal_records[:-1] == records and terminal_records[-1].kind == "TERMINAL"
    facts = load_strict_json(terminal_records[-1].facts_bytes)
    assert (
        facts["path_ids"] == list(path)
        and facts["action"] == "SETTLE"
        and facts["status"] == "SUCCEEDED"
    )
    assert (
        terminal_records[-1].operation_id == result.operation_id
        and facts["first_evidence_ref"] == bundle.evidence_ref
    )
    with psycopg.connect(dsn) as conn:
        settled = conn.execute(
            "SELECT grant_id,amount_reserved,amount_settled,calls_reserved,calls_sett"
            "led FROM ag_grants ORDER BY grant_id"
        ).fetchall()
        nodes = conn.execute(
            "SELECT n.position,n.grant_id,n.amount_reserved_delta,n.amount_settled_de"
            "lta,n.calls_reserved_delta,n.calls_settled_delta FROM ag_ledger_event_no"
            "des n JOIN ag_ledger_events e USING(event_id) WHERE e.operation_id=%s AN"
            "D e.phase='SETTLE' ORDER BY n.position",
            (result.operation_id,),
        ).fetchall()
    assert nodes == [(i, g, -70000, 70000, -1, 1) for i, g in enumerate(path)]
    assert {grant: tuple(values) for grant, *values in settled if grant in path} == {
        path[0]: (0, 70000, 2, 1),
        path[1]: (0, 70000, 2, 1),
        path[2]: (0, 70000, 1, 1),
    }
    mutable = {
        "ag_operations",
        "ag_execution_leases",
        "ag_grants",
        "ag_ledger_events",
        "ag_ledger_event_nodes",
        "ag_event_seals",
        "ag_receipt_outbox",
        "ag_audit_records",
        "ag_audit_streams",
    }
    for table in terminal_before["gateway"]:
        if table not in mutable:
            assert terminal_after["gateway"][table] == terminal_before["gateway"][table]
    marker = namespace_evidence(dsn)
    (marker.parent / (marker.stem + "-introduced-" + str(round) + ".json")).write_text(
        json.dumps(
            {
                "before": before,
                "after": after,
                "known_before": reuse_before,
                "known_after": reuse_after,
                "expected_introduced": expected,
                "counter_readback": counters,
                "terminal_before": terminal_before,
                "terminal_after": terminal_after,
                "terminal_counters": settled,
                "terminal_nodes": nodes,
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("mode", ("introduced", "offpath-empty"))
@pytest.mark.parametrize(
    "counter", ("amount_reserved", "amount_settled", "calls_reserved", "calls_settled")
)
def test_actual_nonzero_new_and_offpath_counter_cannot_be_zero_baseline(
    ledger, dsn, downstream_dsn, round, mode, counter
):
    import json
    import time

    from psycopg import sql

    from agent_guard.audit import journal
    from agent_guard.crypto.sm import verify_compact_jws
    from tests.fixtures.a31_common import namespace_evidence

    marker = namespace_evidence(dsn)
    evidence = marker.parent / (
        marker.stem + "-nonzero-" + mode + "-" + counter + "-" + str(round) + ".json"
    )
    diagnostic = {"counter": counter, "mode": mode, "round": round, "timeline": []}

    def observe(phase):
        with psycopg.connect(dsn) as conn:
            database_time, backend = conn.execute(
                "SELECT clock_timestamp(),pg_backend_pid()"
            ).fetchone()
            grants = conn.execute(
                "SELECT grant_id,parent_grant_id,root_grant_id,created_at,not_before,"
                "expires_at FROM ag_grants ORDER BY grant_id"
            ).fetchall()
        diagnostic["timeline"].append(
            {
                "phase": phase,
                "wall_time": time.time(),
                "monotonic": time.monotonic(),
                "database_clock": database_time.isoformat(),
                "backend_pid": backend,
                "grant_windows": [
                    [value.isoformat() if hasattr(value, "isoformat") else value for value in row]
                    for row in grants
                ],
            }
        )
        evidence.write_text(json.dumps(diagnostic, indent=2) + "\n")
        evidence.chmod(0o600)

    diagnostic["before_prepare"] = state(dsn, downstream_dsn)
    observe("before_actual_as_prepare")
    try:
        env, exchanges, child = _actual_as_branch_env(dsn, downstream_dsn)
        observe("after_actual_as_prepare")
        if mode == "introduced":
            env.adapter.accept(
                env.bundle(
                    "old-zero-read",
                    tool="procurement.request.read",
                    params={"request_id": "req-001"},
                )
            )
        new_env, leaf_id = _actual_new_as_leaf(env, exchanges, child)
        with psycopg.connect(dsn) as conn:
            conn.execute(
                sql.SQL("UPDATE ag_grants SET {}=1 WHERE grant_id=%s").format(
                    sql.Identifier(counter)
                ),
                (leaf_id,),
            )
            assert conn.execute(
                "SELECT count(*) FROM ag_operations WHERE grant_id=%s", (leaf_id,)
            ).fetchone() == (0,)
        chosen = new_env if mode == "introduced" else env
        diagnostic["grant_id"] = leaf_id
        diagnostic["before_bundle"] = state(dsn, downstream_dsn)
        claims = verify_compact_jws(
            chosen.token,
            expected_type="ag-at+jwt",
            trusted_keys={"as-sign-1": env.as_key.public_key()},
        )
        diagnostic["signed_token_window"] = {key: claims[key] for key in ("iat", "nbf", "exp")}
        observe("before_new_proof_bundle")
        bundle = chosen.bundle(
            "nonzero-baseline-refusal",
            tool="procurement.request.read",
            params={"request_id": "req-001"},
        )
        diagnostic["verified_request_window"] = {
            name: getattr(bundle.invocation, name)
            for name in ("token_exp", "proof_iat", "proof_exp", "proof_jti")
        }
        diagnostic["before"] = state(dsn, downstream_dsn)
        observe("before_counter_accept")
        with pytest.raises(journal.JournalError):
            chosen.adapter.accept(bundle)
        assert state(dsn, downstream_dsn) == diagnostic["before"]
        diagnostic["expected_counter_refusal"] = "JournalError"
    except BaseException as exc:
        diagnostic["exception"] = {
            "type": type(exc).__name__,
            "code": str(getattr(exc, "code", None)),
            "sqlstate": getattr(exc, "sqlstate", None),
        }
        raise
    finally:
        diagnostic["after"] = state(dsn, downstream_dsn)
        observe("final_actual_state")


@pytest.mark.parametrize("capacity", ("actual-objects", "actual-logical-raw"))
def test_actual_capture_capacity_overflow_rolls_back_complete_first(
    ledger, dsn, downstream_dsn, monkeypatch, capacity
):
    import json
    from dataclasses import replace

    from agent_guard.audit import journal
    from agent_guard.audit.contracts import SnapshotObject
    from agent_guard.crypto.sm import sm3_b64url
    from tests.fixtures.a31_common import namespace_evidence

    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    before = state(dsn, downstream_dsn)
    original = journal.ensure_stream_tx

    def ensure(conn, seed):
        if capacity == "actual-objects":
            actual = (seed.objects[0],) * 200001
            assert len(actual) == 200001
            changed = replace(seed, objects=actual, object_count=len(actual))
        else:
            raw = b"x" * 65537
            obj = SnapshotObject("request", "overflow-actual-raw", raw, sm3_b64url(raw))
            assert len(obj.raw) == 65537
            changed = replace(seed, objects=(obj,), object_count=1)
        return original(conn, changed)

    monkeypatch.setattr(journal, "ensure_stream_tx", ensure)
    reason = (
        "bootstrap object capacity mismatch"
        if capacity == "actual-objects"
        else "bootstrap object bytes/digest mismatch"
    )
    try:
        with pytest.raises(journal.JournalError, match=reason):
            env.adapter.accept(bundle)
        assert state(dsn, downstream_dsn) == before
    finally:
        marker = namespace_evidence(dsn)
        (marker.parent / (marker.stem + "-capacity-" + capacity + ".json")).write_text(
            json.dumps(
                {
                    "before": before,
                    "after": state(dsn, downstream_dsn),
                    "capacity": capacity,
                    "expected_reason": reason,
                },
                indent=2,
            )
            + "\n"
        )


def test_rolled_back_seed_never_reused_in_new_transaction(ledger, dsn, downstream_dsn, monkeypatch):
    import json

    from agent_guard.audit import journal
    from tests.fixtures.a31_common import namespace_evidence
    from tests.fixtures.receipts import accept_initial_only

    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    before = state(dsn, downstream_dsn)
    original = journal.ensure_stream_tx
    captured = []

    def fail_first(conn, seed):
        captured.append(seed)
        assert seed.tx_id == journal.tx_id(conn)
        raise RuntimeError("owned rollback before initial stream")

    monkeypatch.setattr(journal, "ensure_stream_tx", fail_first)
    with pytest.raises(RuntimeError, match="owned rollback before initial stream"):
        env.adapter.accept(bundle)
    assert state(dsn, downstream_dsn) == before and len(captured) == 1
    old = captured[0]

    def stale(conn, seed):
        captured.append(seed)
        assert seed.tx_id == journal.tx_id(conn) and seed.tx_id != old.tx_id
        return original(conn, old)

    monkeypatch.setattr(journal, "ensure_stream_tx", stale)
    with pytest.raises(journal.JournalError, match="bootstrap seed transaction/schema mismatch"):
        env.adapter.accept(bundle)
    stale_after = state(dsn, downstream_dsn)
    assert stale_after == before and len(captured) == 2

    def fresh(conn, seed):
        captured.append(seed)
        assert seed.tx_id == journal.tx_id(conn) and seed.tx_id not in {
            s.tx_id for s in captured[:-1]
        }
        return original(conn, seed)

    monkeypatch.setattr(journal, "ensure_stream_tx", fresh)
    result = env.adapter.accept(bundle)
    after = state(dsn, downstream_dsn)
    assert len(captured) == 3
    accept_initial_only(before, after, seed=captured[-1], bundle=bundle, result=result)
    marker = namespace_evidence(dsn)
    (marker.parent / (marker.stem + "-seed-reuse.json")).write_text(
        json.dumps(
            {
                "before": before,
                "stale_after": stale_after,
                "fresh_after": after,
                "capture_xids": [s.tx_id for s in captured],
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "same-wrong-scope",
        "base-stream",
        "record-seq",
        "record-id",
        "record-kind",
        "record-op",
        "record-ref",
        "record-prev",
        "record-stream",
        "record-time",
        "record-digest",
        "record-raw",
        "stream-genesis",
        "stream-created-xid",
        "base-unknown",
        "unrelated-downstream",
        "omitted-task-metadata",
        "omitted-token-raw",
    ),
)
def test_initial_full_snapshot_oracle_rejects_column_scope_and_domain_corruption(
    ledger, dsn, downstream_dsn, monkeypatch, mutation
):
    import copy
    import json
    from dataclasses import replace

    from agent_guard.audit import journal
    from agent_guard.contracts.encoding import EncodingError, canonical_json_bytes, load_strict_json
    from agent_guard.crypto.sm import sm3_b64url
    from tests.fixtures.a31_common import DIGEST, namespace_evidence
    from tests.fixtures.receipts import accept_initial_only

    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    before = state(dsn, downstream_dsn)
    original = journal.capture_empty_task_tx
    captured = []

    def capture(conn, context):
        seed = original(conn, context)
        captured.append(seed)
        return seed

    monkeypatch.setattr(journal, "capture_empty_task_tx", capture)
    result = env.adapter.accept(bundle)
    after = state(dsn, downstream_dsn)
    seed = captured[0]
    accept_initial_only(before, after, seed=seed, bundle=bundle, result=result)
    changed = copy.deepcopy(after)

    def alter(table, fn, predicate=lambda row: True):
        matches = 0
        rows = []
        for (encoded,) in changed["gateway"][table]:
            row = json.loads(encoded)
            if predicate(row):
                fn(row)
                matches += 1
            rows.append((json.dumps(row, separators=(",", ":")),))
        assert matches == 1
        changed["gateway"][table] = sorted(rows)

    if mutation == "same-wrong-scope":
        alter("ag_audit_streams", lambda r: r.update(tenant_id="another-tenant"))
        records = sorted(
            (json.loads(encoded) for (encoded,) in changed["gateway"]["ag_audit_records"]),
            key=lambda r: r["seq"],
        )
        previous = records[0]["previous_digest"]
        for row in records:
            payload = load_strict_json(bytes.fromhex(row["raw"][2:]))
            payload["tenant_id"] = "another-tenant"
            payload["previous_digest"] = previous
            raw = canonical_json_bytes(payload)
            digest = sm3_b64url(raw)
            row.update(raw="\\x" + raw.hex(), digest=digest, previous_digest=previous)
            previous = digest
        changed["gateway"]["ag_audit_records"] = sorted(
            (json.dumps(row, separators=(",", ":")),) for row in records
        )
        alter("ag_audit_streams", lambda r: r.update(head_digest=previous))
    elif mutation == "base-stream":
        alter("ag_audit_bootstrap", lambda r: r.update(stream_id="elsewhere"))
    elif mutation.startswith("record-"):
        key = mutation[7:]
        column = {
            "seq": "seq",
            "id": "record_id",
            "kind": "kind",
            "op": "operation_id",
            "ref": "evidence_ref",
            "prev": "previous_digest",
            "stream": "stream_id",
            "time": "recorded_at",
            "digest": "digest",
            "raw": "raw",
        }[key]
        value = {
            "seq": 9,
            "id": "BOOTSTRAP:other",
            "kind": "FIRST",
            "op": "other-op",
            "ref": "other-ref",
            "prev": DIGEST,
            "stream": "other-stream",
            "time": "2020-01-01T00:00:00+00:00",
            "digest": DIGEST,
            "raw": "\\x7b7d",
        }[key]
        alter(
            "ag_audit_records",
            lambda r: r.update({column: value}),
            lambda r: r["kind"] == "BOOTSTRAP",
        )
    elif mutation == "stream-genesis":
        alter("ag_audit_streams", lambda r: r.update(genesis_digest=DIGEST))
    elif mutation == "stream-created-xid":
        alter("ag_audit_streams", lambda r: r.update(created_xid="0"))
    elif mutation == "base-unknown":
        alter("ag_audit_bootstrap", lambda r: r.update(unexpected="value"))
    elif mutation == "unrelated-downstream":
        changed["downstream"]["ds_unrelated"] = [("{}",)]
    elif mutation.startswith("omitted-"):

        def chosen(o):
            return (
                (o.kind == "typed_snapshot_metadata" and o.object_id.startswith("ag_tasks:"))
                if mutation == "omitted-task-metadata"
                else o.object_id.endswith(":token_jws")
            )

        omitted = [o for o in seed.objects if chosen(o)]
        assert omitted
        seed = replace(
            seed,
            objects=tuple(o for o in seed.objects if o not in omitted),
            object_count=seed.object_count - len(omitted),
        )
    with pytest.raises((AssertionError, EncodingError, KeyError)):
        accept_initial_only(before, changed, seed=seed, bundle=bundle, result=result)
    marker = namespace_evidence(dsn)
    (marker.parent / (marker.stem + "-initial-oracle-" + mutation + ".json")).write_text(
        json.dumps(
            {"before": before, "after": after, "corrupted": changed, "mutation": mutation}, indent=2
        )
        + "\n"
    )


@pytest.mark.parametrize(
    "table,column,kind",
    (
        ("ag_grant_tokens", "token_jws", "token"),
        ("ag_auth_evidence", "proof_jws", "proof"),
        ("ag_exchange_evidence", "proof_jws", "proof"),
        ("ag_receipt_outbox", "receipt_jws", "receipt"),
    ),
)
@pytest.mark.parametrize("boundary", ("cap", "cap-plus-one", "non-ascii"))
def test_actual_text_snapshot_logical_raw_bounds(
    ledger, dsn, downstream_dsn, table, column, kind, boundary
):
    """Opaque stored-byte limit controls; never claimed as valid padded JWS."""
    import json

    from agent_guard.audit import journal
    from agent_guard.contracts.encoding import load_strict_json
    from agent_guard.crypto.sm import sm3_b64url
    from tests.fixtures.a31_common import namespace_evidence
    from tests.fixtures.receipts import CorruptRow, receipt_services

    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    if table == "ag_receipt_outbox":
        op = env.adapter.accept(bundle).operation_id
        assert env.service.run_operation(op).status == "SUCCEEDED"
        _, _, publisher = receipt_services(env, dsn)
        assert publisher.publish(op).receipt_status == "READY"
    identity = {
        "ag_grant_tokens": "grant_id",
        "ag_auth_evidence": "evidence_id",
        "ag_exchange_evidence": "evidence_id",
        "ag_receipt_outbox": "operation_id",
    }[table]
    with psycopg.connect(dsn) as conn:
        key, original = conn.execute(
            psycopg.sql.SQL("SELECT {},{} FROM {} ORDER BY {} LIMIT 1").format(
                *map(psycopg.sql.Identifier, (identity, column, table, identity))
            )
        ).fetchone()
        assert type(original) is str and 0 < len(original.encode("ascii")) <= 16384
        scope = (journal.gateway_origin(), bundle.invocation.tenant_id, bundle.invocation.task_id)
        original_seed = journal._snapshot(
            conn, scope, bundle.invocation.root_id, empty=table != "ag_receipt_outbox"
        )
        matches = [
            o
            for o in original_seed.objects
            if o.kind == kind
            and o.object_id.endswith(":" + column)
            and o.raw == original.encode("ascii")
        ]
        assert len(matches) >= 1
    value = "A" * (16384 if boundary == "cap" else 16385) if boundary != "non-ascii" else "é"
    baseline = state(dsn, downstream_dsn)
    with CorruptRow(dsn, table, {identity: key}, {column: value}):
        before = state(dsn, downstream_dsn)
        try:
            with psycopg.connect(dsn) as conn:
                conn.execute("SELECT task_id FROM ag_tasks FOR UPDATE")
                if boundary == "cap":
                    seed = journal._snapshot(
                        conn, scope, bundle.invocation.root_id, empty=table != "ag_receipt_outbox"
                    )
                    found = [
                        o
                        for o in seed.objects
                        if o.kind == kind
                        and o.object_id.endswith(":" + column)
                        and o.raw == value.encode("ascii")
                    ]
                    assert len(found) == 1 and found[0].digest == sm3_b64url(value.encode("ascii"))
                    refs = [
                        load_strict_json(o.raw)["columns"][column]
                        for o in seed.objects
                        if o.kind == "typed_snapshot_metadata"
                        and o.object_id.startswith(table + ":")
                        and o.object_id.split(":")[-1].isdigit()
                    ]
                    assert {
                        "kind": kind,
                        "object_id": found[0].object_id,
                        "digest": found[0].digest,
                    } in refs
                else:
                    reason = (
                        "logical snapshot object capacity exceeded"
                        if boundary == "cap-plus-one"
                        else "signed snapshot text must be ASCII"
                    )
                    with pytest.raises(journal.JournalError, match=reason):
                        journal._snapshot(
                            conn,
                            scope,
                            bundle.invocation.root_id,
                            empty=table != "ag_receipt_outbox",
                        )
            assert state(dsn, downstream_dsn) == before
        finally:
            marker = namespace_evidence(dsn)
            (
                marker.parent / (marker.stem + "-text-cap-" + table + "-" + boundary + ".json")
            ).write_text(
                json.dumps(
                    {
                        "before": before,
                        "after": state(dsn, downstream_dsn),
                        "table": table,
                        "column": column,
                        "kind": kind,
                        "boundary": boundary,
                        "stored_cap_probe_is_opaque": True,
                        "valid_original_text_preserved_as_kind": True,
                    },
                    indent=2,
                )
                + "\n"
            )
    assert state(dsn, downstream_dsn) == baseline
