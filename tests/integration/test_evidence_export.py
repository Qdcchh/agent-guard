"""Native read-only snapshot exports of accepted A31 historical material."""

import io
from pathlib import Path

import psycopg
import pytest

from agent_guard.evidence.export import materialize_task_export
from agent_guard.evidence.task_bundle import iter_frames
from agent_guard.execution.query import AuthorizedQuery
from tests.fixtures.a32_export import (
    cache_checkpoint_rows,
    history_inputs,
    readonly_export_factory,
    record_export_native_evidence,
)
from tests.fixtures.a32_export import export_full_state as full_state
from tests.fixtures.gateway import query_bundle
from tests.fixtures.receipts import receipt_services
from tests.integration.test_verified_execution import TOOLS, signed_env

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("failed_notification", [False, True])
@pytest.mark.parametrize("published", [False, True])
@pytest.mark.parametrize("queried", [False, True])
def test_export_all_material_states_and_four_tools(
    ledger,
    dsn,
    downstream_dsn,
    tmp_path,
    monkeypatch,
    round,
    published,
    queried,
    failed_notification,
):
    import json

    original_dump = json.dumps

    def original_noncanonical(value, *args, **kwargs):
        if (
            type(value) is dict
            and "operation_id" in value
            and ("kind" in value or "events" in value)
        ):
            kwargs.pop("separators", None)
            kwargs["indent"] = 1
        return original_dump(value, *args, **kwargs)

    # Change only the legitimate byte representation at its original writer;
    # real DS rows, accepted fences, terminal journal and publication still run.
    monkeypatch.setattr(json, "dumps", original_noncanonical)
    env = signed_env(dsn, downstream_dsn)
    _, receipt_verifier, publisher = receipt_services(env, dsn)
    operations = []
    for index, tool in enumerate(TOOLS):
        params = [
            {"request_id": "req-001"},
            {"request_id": "req-001", "document_id": "doc-001"},
            None,
            {
                "template_id": "order-created",
                "recipient_id": "user-demo-001",
                "operation_id": operations[0] if operations else "",
            },
        ][index]
        first = env.adapter.accept(
            env.bundle("export-tool-" + str(index), tool=tool, params=params)
        )
        operations.append(first.operation_id)
        env.adapter.accept(env.bundle("export-tool-" + str(index), tool=tool, params=params))
        if queried:
            AuthorizedQuery(
                dsn, evidence_store=env.evidence, receipt_verifier=receipt_verifier
            ).query(query_bundle(env, first.operation_id))
        if index == 3 and failed_notification:
            env.downstream._approved_recipients = frozenset()
        assert env.service.run_operation(first.operation_id).status == (
            "FAILED" if index == 3 and failed_notification else "SUCCEEDED"
        )
        if queried:
            AuthorizedQuery(
                dsn, evidence_store=env.evidence, receipt_verifier=receipt_verifier
            ).query(query_bundle(env, first.operation_id))
        if published:
            publisher.publish(first.operation_id)
            env.adapter.accept(env.bundle("export-tool-" + str(index), tool=tool, params=params))
            if queried:
                AuthorizedQuery(
                    dsn, evidence_store=env.evidence, receipt_verifier=receipt_verifier
                ).query(query_bundle(env, first.operation_id))
    for state in ("RESERVED", "EXECUTING", "UNKNOWN"):
        accepted = env.adapter.accept(
            env.bundle("runtime-" + state, tool=TOOLS[0], params={"request_id": "req-001"})
        )
        if state != "RESERVED":
            claim = env.service._claim(accepted.operation_id, "export-fixture-" + state)
            if state == "UNKNOWN":
                assert env.service._mark_unknown(claim) == "UNKNOWN"
    # Accepted immutable quote originals remain usable after the live supplier quote changes.
    from dataclasses import replace

    from agent_guard.tools.catalog import CatalogQuoteLine

    live = env.service._catalog.get_quote("quote-001", "1")
    env.service._catalog.replace_quote(replace(live, lines=(CatalogQuoteLine("sku-001", 1, 1),)))
    env.service._catalog.remove_quote("quote-001", "1")
    scope, pin, history = history_inputs(dsn, tmp_path)
    spool_parent = tmp_path / "spool"
    spool_parent.mkdir(mode=0o700)
    before = full_state(dsn, downstream_dsn)
    with readonly_export_factory(dsn) as factory:
        with factory() as connection:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute("UPDATE ag_operations SET status=status")
        spool = materialize_task_export(
            factory, scope, pin, spool_parent, external_checkpoint_history=history
        )
        raw = Path(spool.path).read_bytes()
        frames = list(iter_frames(io.BytesIO(raw)))
        assert frames[0]["cutoff_sequence"] == spool.cutoff_sequence
        assert frames[0]["operation_count"] == 7
        from agent_guard.contracts.encoding import (
            b64url_decode,
            canonical_json_bytes,
            load_strict_json,
        )

        metadata = [
            load_strict_json(b64url_decode(f["data"]))
            for f in frames
            if f.get("object_kind") == "typed_snapshot_metadata" and f["chunk_count"] == 1
        ]
        metadata = [m for m in metadata if type(m) is dict]
        observed = [
            m
            for m in metadata
            if type(m) is dict and m.get("metadata_profile") == "AG-TASK-RUNTIME-OBSERVATION-1"
        ]
        assert {m["status"] for m in observed} == (
            {"RESERVED", "EXECUTING", "UNKNOWN", "SUCCEEDED", "FAILED"}
            if failed_notification
            else {"RESERVED", "EXECUTING", "UNKNOWN", "SUCCEEDED"}
        )
        assert len(observed) == 7
        assert any(
            m.get("metadata_profile") == "AG-TASK-ACCEPT-RESULT-1" and m["cost"]["quote_id"] is None
            for m in metadata
        )
        assert any(
            m.get("metadata_profile") == "AG-TASK-ACCEPT-RESULT-1"
            and m["cost"]["quote_id"] is not None
            for m in metadata
        )
        raw_results = [
            b64url_decode(f["data"])
            for f in frames
            if f.get("object_kind") == "result" and f["chunk_count"] == 1
        ]
        assert any(r != canonical_json_bytes(load_strict_json(r)) for r in raw_results)
        assert len(raw) == spool.size
        assert Path(spool.path).stat().st_mode & 0o777 == 0o600
        assert Path(spool.path).parent.stat().st_mode & 0o777 == 0o700
        spool.cleanup()
        assert list(spool_parent.iterdir()) == []
    assert full_state(dsn, downstream_dsn) == before


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize(
    "case",
    [
        "latest",
        "minimumonly",
        "remoteahead",
        "unknownempty",
        "unknowncached",
        "unknownwithoutcache",
        "behind",
        "fork",
        "changedhistory",
    ],
)
def test_export_behind_independent_checkpoint_refused(
    ledger, dsn, downstream_dsn, tmp_path, round, case
):
    from agent_guard.evidence.task_bundle import TaskBundleError

    env = signed_env(dsn, downstream_dsn)
    op = env.adapter.accept(env.bundle())
    env.service.run_operation(op.operation_id)
    mode = (
        "UNKNOWN"
        if case.startswith("unknown")
        else "MINIMUM"
        if case == "minimumonly"
        else "LATEST_OBSERVATION"
    )
    scope, pin, history = history_inputs(
        dsn,
        tmp_path,
        mode=mode,
        sequences=() if case == "unknownempty" else None,
        fault=case if case in {"behind", "fork"} else None,
    )
    if case in {"remoteahead", "unknowncached"}:
        cache_checkpoint_rows(dsn, history, [1, history.last_sequence])
    if case == "changedhistory":
        Path(history.source_path).write_bytes(Path(history.source_path).read_bytes() + b"\n")
    parent = tmp_path / "spool"
    parent.mkdir(mode=0o700)
    before = full_state(dsn, downstream_dsn)
    with readonly_export_factory(dsn) as factory:
        if case in {"behind", "fork", "changedhistory", "unknownwithoutcache"}:
            with pytest.raises(TaskBundleError):
                materialize_task_export(
                    factory, scope, pin, parent, external_checkpoint_history=history
                )
        else:
            spool = materialize_task_export(
                factory, scope, pin, parent, external_checkpoint_history=history
            )
            frames = list(iter_frames(io.BytesIO(Path(spool.path).read_bytes())))
            checkpoints = sum(
                f.get("object_kind") == "checkpoint" and f["chunk_index"] == 0
                for f in frames
                if f["frame_type"] == "OBJECT_CHUNK"
            )
            assert checkpoints == history.checkpoint_count
            spool.cleanup()
    assert list(parent.iterdir()) == []
    assert full_state(dsn, downstream_dsn) == before


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize(
    "change",
    [
        "accept",
        "query",
        "terminal",
        "publish",
        "keyrotate",
        "same_other_task",
        "claim_runtime_transition",
        "unknown_runtime_transition",
        "same_SH_distinct_asof_observation",
    ],
)
def test_export_fixed_cutoff_during_concurrent_changes(
    ledger, dsn, downstream_dsn, tmp_path, monkeypatch, round, change
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from agent_guard.evidence import export

    env = signed_env(dsn, downstream_dsn)
    op = env.adapter.accept(env.bundle())
    if change in {"publish", "keyrotate"}:
        env.service.run_operation(op.operation_id)
    scope, pin, history = history_inputs(dsn, tmp_path)
    parent = tmp_path / "spool"
    parent.mkdir(mode=0o700)
    observed, proceed = Event(), Event()
    original = export._record_material
    seen = []

    def paused(conn, record, projection, objects):
        if not seen:
            seen.append(conn.info.backend_pid)
            observed.set()
            assert proceed.wait(15)
        return original(conn, record, projection, objects)

    monkeypatch.setattr(export, "_record_material", paused)
    with (
        readonly_export_factory(dsn) as factory,
        ThreadPoolExecutor(max_workers=1) as workers,
    ):
        future = workers.submit(
            materialize_task_export,
            factory,
            scope,
            pin,
            parent,
            external_checkpoint_history=history,
        )
        assert observed.wait(15)
        if change == "accept":
            env.adapter.accept(env.bundle())
        elif change == "query":
            AuthorizedQuery(dsn, evidence_store=env.evidence).query(
                query_bundle(env, op.operation_id)
            )
        elif change == "terminal":
            env.service.run_operation(op.operation_id)
        elif change == "publish":
            receipt_services(env, dsn)[2].publish(op.operation_id)
        elif change == "keyrotate":
            from agent_guard.crypto.sm import generate_sm2_private_key

            old_key, _, old_publisher = receipt_services(env, dsn)
            _, _, rotated = receipt_services(
                env, dsn, gateway_key=generate_sm2_private_key(), signing_kid="gw-rotated-export"
            )
            assert rotated._signing_kid != old_publisher._signing_kid
            rotated.publish(op.operation_id)
        elif change == "same_other_task":
            from tests.fixtures.a32_export import accept_other_task

            accept_other_task(dsn, downstream_dsn, monkeypatch)
        else:
            claim = env.service._claim(op.operation_id, "native-export-concurrent")
            if change in {"unknown_runtime_transition", "same_SH_distinct_asof_observation"}:
                assert env.service._mark_unknown(claim) == "UNKNOWN"
        after_writer = full_state(dsn, downstream_dsn)
        with psycopg.connect(dsn) as conn:
            assert conn.info.backend_pid != seen[0]
            current = conn.execute(
                "SELECT head_seq FROM ag_audit_streams WHERE stream_id=%s",
                (scope.stream_id,),
            ).fetchone()[0]
        proceed.set()
        spool = future.result(timeout=30)
        assert spool.cutoff_sequence == history.last_sequence
        if change in {"accept", "query", "terminal", "publish", "keyrotate"}:
            assert spool.cutoff_sequence < current
        else:
            assert spool.cutoff_sequence == current
        frames = list(iter_frames(io.BytesIO(Path(spool.path).read_bytes())))
        if change in {
            "claim_runtime_transition",
            "unknown_runtime_transition",
            "same_SH_distinct_asof_observation",
        }:
            from agent_guard.contracts.encoding import b64url_decode, load_strict_json

            observations = [
                load_strict_json(b64url_decode(f["data"]))
                for f in frames
                if f.get("object_kind") == "typed_snapshot_metadata" and f["chunk_count"] == 1
            ]
            observations = [
                o
                for o in observations
                if type(o) is dict and o.get("metadata_profile") == "AG-TASK-RUNTIME-OBSERVATION-1"
            ]
            assert observations[0]["status"] == "RESERVED"
            if change == "same_SH_distinct_asof_observation":
                import time

                time.sleep(1.1)
                later = materialize_task_export(
                    factory, scope, pin, parent, external_checkpoint_history=history
                )
                later_frames = list(iter_frames(io.BytesIO(Path(later.path).read_bytes())))
                assert (later.cutoff_sequence, later.cutoff_head_digest) == (
                    spool.cutoff_sequence,
                    spool.cutoff_head_digest,
                )
                assert later_frames[0]["snapshot_as_of"] > frames[0]["snapshot_as_of"]
                values = [
                    load_strict_json(b64url_decode(f["data"]))
                    for f in later_frames
                    if f.get("object_kind") == "typed_snapshot_metadata" and f["chunk_count"] == 1
                ]
                assert any(
                    type(v) is dict
                    and v.get("metadata_profile") == "AG-TASK-RUNTIME-OBSERVATION-1"
                    and v["status"] == "UNKNOWN"
                    for v in values
                )
                later.cleanup()
        spool.cleanup()
    assert full_state(dsn, downstream_dsn) == after_writer


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("case", ["opaque", "short", "missingoriginal"])
def test_export_bootstrap_nonzero_opaque_gaps(
    ledger, tree, dsn, downstream_dsn, tmp_path, round, case
):
    from agent_guard.audit import journal

    ledger.accept(tree.invocation(), tree.cost(70000))
    with psycopg.connect(dsn) as conn:
        registration = journal.bootstrap_task_tx(
            conn, scope_key=(journal.gateway_origin(), tree.tenant_id, tree.task_id)
        )
    assert registration.boundary == "LEGACY_WITH_GAPS"
    scope, pin, history = history_inputs(dsn, tmp_path, mode="UNKNOWN", sequences=())
    parent = tmp_path / "spool"
    parent.mkdir(mode=0o700)
    if case != "opaque":
        from tests.fixtures.receipts import CorruptRow

        with psycopg.connect(dsn) as conn:
            kind, ident, index, raw = conn.execute(
                "SELECT object_kind,object_id,chunk_index,raw "
                "FROM ag_audit_bootstrap_chunks WHERE stream_id=%s "
                "ORDER BY object_kind,object_id,chunk_index LIMIT 1",
                (scope.stream_id,),
            ).fetchone()
        raw = bytes(raw)
        changed = raw[:-1] if case == "short" else b"!" + raw[1:]
        pristine = full_state(dsn, downstream_dsn)
        with CorruptRow(
            dsn,
            "ag_audit_bootstrap_chunks",
            {
                "stream_id": scope.stream_id,
                "object_kind": kind,
                "object_id": ident,
                "chunk_index": index,
            },
            {"raw": changed, "total_raw_bytes": len(changed)}
            if case == "short"
            else {"raw": changed},
        ):
            before = full_state(dsn, downstream_dsn)
            with readonly_export_factory(dsn) as factory, pytest.raises(ValueError):
                materialize_task_export(
                    factory, scope, pin, parent, external_checkpoint_history=history
                )
            assert full_state(dsn, downstream_dsn) == before
            assert list(parent.iterdir()) == []
        assert full_state(dsn, downstream_dsn) == pristine
        return
    before = full_state(dsn, downstream_dsn)
    with readonly_export_factory(dsn) as factory:
        spool = materialize_task_export(
            factory, scope, pin, parent, external_checkpoint_history=history
        )
        frames = list(iter_frames(io.BytesIO(Path(spool.path).read_bytes())))
        assert frames[0]["history_boundary"] == "LEGACY_WITH_GAPS"
        assert frames[0]["operation_count"] == 1
        spool.cleanup()
    assert full_state(dsn, downstream_dsn) == before


@pytest.mark.parametrize("round", range(10))
def test_export_wire_bounds_disconnect_synthetic_privacy(
    ledger, dsn, downstream_dsn, tmp_path, round
):
    import multiprocessing
    import os
    import signal
    import time

    env = signed_env(dsn, downstream_dsn)
    env.adapter.accept(env.bundle())
    scope, pin, history = history_inputs(dsn, tmp_path)
    parent = tmp_path / "spool"
    parent.mkdir(mode=0o700)
    before = full_state(dsn, downstream_dsn)
    with readonly_export_factory(dsn) as factory:
        context = multiprocessing.get_context("fork")
        receive, transmit = context.Pipe(duplex=False)

        def child():
            spool = materialize_task_export(
                factory, scope, pin, parent, external_checkpoint_history=history
            )
            transmit.send((spool.path, spool._guardian_pid))
            time.sleep(30)

        process = context.Process(target=child)
        process.start()
        assert receive.poll(15)
        path, guardian = receive.recv()
        native = Path("/proc") / str(process.pid)
        print("REAL_EXPORT_KILL", process.pid, (native / "stat").read_text(), guardian)
        import hashlib

        identities = []
        for pid in (process.pid, guardian):
            proc = Path("/proc") / str(pid)
            stat_raw = (proc / "stat").read_text()
            identities.append(
                {
                    "pid": pid,
                    "uid": int(
                        next(
                            line
                            for line in (proc / "status").read_text().splitlines()
                            if line.startswith("Uid:")
                        ).split()[1]
                    ),
                    "start_ticks": stat_raw[stat_raw.rfind(")") + 2 :].split()[19],
                    "argv_sha256": hashlib.sha256((proc / "cmdline").read_bytes()).hexdigest(),
                    "raw_stat": stat_raw,
                }
            )
        record_export_native_evidence(
            "real-kill-before", {"identities": identities, "spool_path": path}
        )
        os.kill(process.pid, signal.SIGKILL)
        process.join(timeout=10)
        record_export_native_evidence(
            "real-kill-exit", {"pid": process.pid, "exit_code": process.exitcode}
        )
        assert process.exitcode == -signal.SIGKILL
        deadline = time.monotonic() + 10
        while Path(path).exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not Path(path).exists()
        assert list(parent.iterdir()) == []
        receive.close()
        transmit.close()
    assert full_state(dsn, downstream_dsn) == before


def test_export_actual_wire_and_logical_capacity(ledger, dsn, downstream_dsn, tmp_path):
    """Exercise original 256 MiB limit with actual encoded bytes, without reduced caps."""
    import shutil

    from agent_guard.evidence import export
    from agent_guard.evidence.task_bundle import TaskBundleError

    env = signed_env(dsn, downstream_dsn)
    env.adapter.accept(env.bundle())
    scope, pin, history = history_inputs(dsn, tmp_path)
    parent = tmp_path / "spool"
    parent.mkdir(mode=0o700)
    before = full_state(dsn, downstream_dsn)
    with readonly_export_factory(dsn) as factory:
        spool = materialize_task_export(
            factory, scope, pin, parent, external_checkpoint_history=history
        )
        header = next(iter_frames(io.BytesIO(Path(spool.path).read_bytes())))
        spool.cleanup()
    objects_dir = tmp_path / "capacity-objects"
    objects_dir.mkdir(mode=0o700)
    objects = export._Objects(objects_dir)
    objects.add("ledger", "operation", "one", "ledger", b"x")
    objects.add("ledger", "operation", "exact", "ledger", b"x" * 65536)
    with pytest.raises(TaskBundleError):
        objects.add("ledger", "operation", "over", "ledger", b"x" * 65537)
    valid = tmp_path / "small-valid.ndjson"
    header.update(
        object_count=2,
        chunk_count=4,
        journal_count=0,
        cutoff_sequence=0,
        operation_count=0,
    )
    size, _ = export._write(valid, scope, header, objects)
    assert size == valid.stat().st_size
    for index in range(3100):
        objects.add("ledger", "operation", str(index), "ledger", b"x" * 65536)
    rejected = tmp_path / "original-wire-rejection.ndjson"
    with pytest.raises(TaskBundleError, match="wire capacity"):
        export._write(rejected, scope, header, objects)
    assert 256 * 1024 * 1024 - 40000 < rejected.stat().st_size <= 256 * 1024 * 1024
    print(
        "ACTUAL_ORIGINAL_WIRE_LIMIT",
        rejected.stat().st_size,
        objects.raw_bytes,
        len(objects.members),
    )
    record_export_native_evidence(
        "actual-wire-rejection",
        {
            "wire_bytes": rejected.stat().st_size,
            "raw_bytes": objects.raw_bytes,
            "object_count": len(objects.members),
            "original_cap": 256 * 1024 * 1024,
        },
    )
    rejected.unlink()
    valid.unlink()
    shutil.rmtree(objects_dir)
    assert full_state(dsn, downstream_dsn) == before


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize(
    "fault",
    [
        "accepted_at",
        "created_at",
        "evidence_ref",
        "internal_seq",
        "result_projection",
        "missing_original",
    ],
)
def test_export_original_metadata_and_projection_rejections(
    ledger, dsn, downstream_dsn, tmp_path, round, fault
):
    from datetime import timedelta

    from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes, load_strict_json
    from tests.fixtures.receipts import CorruptRow

    env = signed_env(dsn, downstream_dsn)
    op = env.adapter.accept(env.bundle())
    env.adapter.accept(env.bundle())
    env.service.run_operation(op.operation_id)
    scope, pin, history = history_inputs(dsn, tmp_path)
    with psycopg.connect(dsn) as conn:
        if fault == "accepted_at":
            value = conn.execute(
                "SELECT accepted_at FROM ag_operations WHERE operation_id=%s", (op.operation_id,)
            ).fetchone()[0]
            corruption = CorruptRow(
                dsn,
                "ag_operations",
                {"operation_id": op.operation_id},
                {"accepted_at": value + timedelta(seconds=1)},
            )
        elif fault in {"created_at", "evidence_ref", "internal_seq"}:
            at, evidence, raw = conn.execute(
                "SELECT created_at,evidence_ref,ledger_changes_json "
                "FROM ag_receipt_outbox WHERE operation_id=%s",
                (op.operation_id,),
            ).fetchone()
            if fault == "created_at":
                changes = {"created_at": at + timedelta(seconds=1)}
            elif fault == "evidence_ref":
                changes = {
                    "evidence_ref": conn.execute(
                        "SELECT evidence_ref "
                        "FROM ag_verified_evidence WHERE evidence_ref<>%s LIMIT 1",
                        (evidence,),
                    ).fetchone()[0]
                }
            else:
                import json

                import rfc8785

                value = json.loads(bytes(raw))
                value["events"][0]["seq"] += 1
                changes = {"ledger_changes_json": rfc8785.dumps(value)}
            corruption = CorruptRow(
                dsn, "ag_receipt_outbox", {"operation_id": op.operation_id}, changes
            )
        elif fault == "result_projection":
            seq, raw = conn.execute(
                "SELECT seq,material_binding_bytes "
                "FROM ag_audit_records WHERE stream_id=%s AND kind='TERMINAL'",
                (scope.stream_id,),
            ).fetchone()
            value = load_strict_json(bytes(raw))
            value["result"] = b64url_encode(b"{}")
            corruption = CorruptRow(
                dsn,
                "ag_audit_records",
                {"stream_id": scope.stream_id, "seq": seq},
                {"material_binding_bytes": canonical_json_bytes(value)},
            )
        else:
            evidence = conn.execute(
                "SELECT evidence_ref FROM ag_verified_evidence ORDER BY evidence_ref LIMIT 1"
            ).fetchone()[0]
            corruption = CorruptRow(
                dsn, "ag_verified_evidence", {"evidence_ref": evidence}, {"token_bytes": b"{}"}
            )
    parent = tmp_path / "spool"
    parent.mkdir(mode=0o700)
    pristine = full_state(dsn, downstream_dsn)
    with corruption:
        before = full_state(dsn, downstream_dsn)
        with readonly_export_factory(dsn) as factory, pytest.raises(ValueError):
            materialize_task_export(
                factory, scope, pin, parent, external_checkpoint_history=history
            )
        assert list(parent.iterdir()) == []
        assert full_state(dsn, downstream_dsn) == before
    assert full_state(dsn, downstream_dsn) == pristine
