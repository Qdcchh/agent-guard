"""Real S0 acceptance/query/fault transactions and persistent per-task heads."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import psycopg
import pytest

from agent_guard.audit import journal
from agent_guard.contracts.ledger import AcceptDisposition, LedgerError
from agent_guard.execution.query import AuthorizedQuery
from tests.fixtures.a31_common import read_records, shared_retry_bundle, state
from tests.fixtures.gateway import query_bundle
from tests.fixtures.receipts import (
    accept_retry_only,
    collect_futures,
    legal_shared_operations,
    receipt_services,
    result_read_only,
)
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize(
    "entry,hooks",
    [
        (entry, hooks)
        for entry in ("accept", "checked", "service")
        for hooks in ("none", "before", "after", "both")
    ]
    + [("verified", "none"), ("response", "none")],
)
def test_first_retry_query_atomic_coverage(ledger, dsn, downstream_dsn, entry, hooks, round):
    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    binding = env.evidence.binding(bundle)
    captured = []

    def before(conn, context):
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM ag_ledger_events").fetchone() == (0,)
        assert all(
            row == (0, 0, 0, 0)
            for row in conn.execute(
                "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled FROM ag_grants"
            ).fetchall()
        )
        captured.append(("before", context.tx_id, conn.info.backend_pid))

    def after(conn, op, disposition, baseline):
        assert disposition is AcceptDisposition.CREATED
        assert baseline.tx_id == journal.tx_id(conn)
        assert baseline.origin == "FROM_EMPTY_TASK"
        assert conn.execute("SELECT count(*) FROM ag_audit_records").fetchone() == (0,)
        captured.append(("after", baseline.tx_id, conn.info.backend_pid))

    opts = {
        "before_create": before if hooks in ("before", "both") else None,
        "after_link": after if hooks in ("after", "both") else None,
    }
    # Resolve through the real service, capturing its trustworthy immutable cost.
    if entry in ("accept", "checked"):
        from agent_guard.tools import policy
        from agent_guard.tools.params import parse_tool_id, parse_tool_params

        v = bundle.invocation
        tool = parse_tool_id(v.tool_id)
        quote = policy.resolve_tool_resources(
            env.service._catalog,
            tenant_id=v.tenant_id,
            task_id=v.task_id,
            tool_id=tool,
            params=parse_tool_params(tool, v.canonical_params),
            operation_facts=env.service._operation_facts,
            caller_grant_id=v.grant_id,
            caller_holder_client_id=v.holder_client_id,
            caller_holder_kid=v.holder_kid,
        )
        cost = env.service._cost_for_new(quote)
        opts["after_link"] = binding.after_link(opts["after_link"])
        if entry == "accept":
            accepted = env.service._ledger.accept(v, cost, **opts)
        else:
            accepted = env.service._ledger.accept_checked(
                v, cost, existing_validator=lambda conn, op: None, **opts
            )
    elif entry == "response":
        response = env.adapter.accept_response(bundle, receipt_verifier=None)
        accepted = env.service._find_candidate(bundle.invocation)
        assert response["operation_id"] == accepted.operation_id
    elif entry == "service":
        accepted = env.service.accept_invocation(
            bundle.invocation, bundle.permissions, binding=binding, **opts
        )
    else:
        accepted = env.adapter.accept(bundle)
    records = read_records(dsn)
    assert [r.kind for r in records] == ["BOOTSTRAP", "FIRST"]
    assert (
        records[1].operation_id == accepted.operation_id
        and records[1].evidence_ref == bundle.evidence_ref
    )
    assert records[1].previous_digest == records[0].digest
    with psycopg.connect(dsn) as conn:
        rows = conn.execute("SELECT created_xid FROM ag_audit_records ORDER BY seq").fetchall()
        witness = conn.execute("SELECT audit_created_xid FROM ag_operations").fetchone()[0]
        assert rows == [(witness,), (witness,)]
        expected_hooks = (
            [name for name in ("before", "after") if hooks in (name, "both")]
            if entry in ("accept", "checked", "service")
            else []
        )
        assert [name for name, xid, pid in captured] == expected_hooks
        assert all(xid == witness for name, xid, pid in captured)
        assert len({pid for name, xid, pid in captured}) <= 1
        assert all(
            row
            == (
                accepted.amount_fen
                if hasattr(accepted, "amount_fen")
                else accepted.cost.amount_fen,
                0,
                1,
                0,
            )
            for row in conn.execute(
                "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled FROM ag_grants"
            ).fetchall()
        )
    retry = env.bundle()
    before_state = state(dsn, downstream_dsn)
    returned = env.adapter.accept(retry)
    assert (
        returned.disposition is AcceptDisposition.EXISTING
        and returned.operation_id == accepted.operation_id
    )
    accept_retry_only(
        before_state,
        state(dsn, downstream_dsn),
        evidence_ref=retry.evidence_ref,
        proof_jti=retry.invocation.proof_jti,
        operation_id=accepted.operation_id,
    )
    query = query_bundle(env, accepted.operation_id)
    before_state = state(dsn, downstream_dsn)
    response = AuthorizedQuery(dsn, evidence_store=env.evidence).query(query)
    assert response["status"] == "RESERVED"
    result_read_only(
        before_state,
        state(dsn, downstream_dsn),
        evidence_ref=query.evidence_ref,
        proof_jti=query.query.proof_jti,
        operation_id=accepted.operation_id,
    )


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("interaction", ("FIRST", "RETRY", "QUERY", "TERMINAL", "PUBLISH"))
@pytest.mark.parametrize("fault", ("before_append", "after_append", "missing_record"))
def test_journal_faults_roll_back_business_facts(
    ledger, dsn, downstream_dsn, monkeypatch, interaction, fault, round
):
    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    op = None
    if interaction == "TERMINAL":
        env.service._lease_ttl = 2
    if interaction != "FIRST":
        op = env.adapter.accept(bundle).operation_id
    if interaction == "PUBLISH":
        assert env.service.run_operation(op).status == "SUCCEEDED"
    if interaction == "RETRY":
        bundle = env.bundle()
    elif interaction == "QUERY":
        bundle = query_bundle(env, op)
    key, verifier, publisher = receipt_services(env, dsn)
    original = journal.append_tx

    def faulty(conn, stream, **kwargs):
        if kwargs["kind"] != interaction:
            return original(conn, stream, **kwargs)
        if fault == "before_append":
            raise RuntimeError("layered local append failure")
        if fault == "missing_record":
            return None
        original(conn, stream, **kwargs)
        raise RuntimeError("layered local post-append failure")

    monkeypatch.setattr(journal, "append_tx", faulty)
    before = state(dsn, downstream_dsn)
    if interaction == "FIRST":

        def invoke():
            return env.adapter.accept(bundle)
    elif interaction == "RETRY":

        def invoke():
            return env.adapter.accept(bundle)
    elif interaction == "QUERY":

        def invoke():
            return AuthorizedQuery(dsn, evidence_store=env.evidence).query(bundle)
    elif interaction == "TERMINAL":
        # Claim/DS commit are separate real TXs; fault concerns only terminal TX.
        captured_before = []

        def pause(claim, outcome):
            assert outcome is not None
            captured_before.append(state(dsn, downstream_dsn))

        def invoke():
            return env.service.run_operation(op, pause=pause)
    else:

        def invoke():
            return publisher.publish(op)

    with pytest.raises((RuntimeError, psycopg.Error, LedgerError, journal.JournalError)) as caught:
        invoke()
    if interaction == "TERMINAL":
        assert len(captured_before) == 1
        before = captured_before[0]
    assert state(dsn, downstream_dsn) == before
    cause = caught.value.__cause__ if isinstance(caught.value, LedgerError) else caught.value
    if fault == "missing_record":
        assert getattr(cause, "sqlstate", None) == "23514"
    monkeypatch.setattr(journal, "append_tx", original)
    if interaction in ("FIRST", "RETRY"):
        assert env.adapter.accept(bundle).operation_id
    elif interaction == "QUERY":
        assert AuthorizedQuery(dsn, evidence_store=env.evidence).query(bundle)["operation_id"] == op
    elif interaction == "PUBLISH":
        assert publisher.publish(op).receipt_status == "READY"
    elif interaction == "TERMINAL":
        with psycopg.connect(dsn, autocommit=True) as observer:
            deadline = observer.execute(
                "SELECT extract(epoch FROM lease_expires_at) FROM ag_execution_leases"
            ).fetchone()[0]
            from tests.fixtures.a31_common import wait_past_database_deadline

            wait_past_database_deadline(observer, deadline)
        assert env.service.reconcile(op, owner_token="fault-recovery-owner").status == "SUCCEEDED"


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("same_proof", (True, False))
def test_same_task_accept_race_one_reservation(ledger, dsn, downstream_dsn, same_proof, round):
    env = signed_env(dsn, downstream_dsn)
    first = env.bundle()
    second = first if same_proof else env.bundle()
    barrier = Barrier(2)
    env.service._ledger._lock_timeout_ms = 180000
    env.service._ledger._statement_timeout_ms = 180000

    def run(bundle):
        barrier.wait(15)
        try:
            return env.adapter.accept(bundle)
        except LedgerError as exc:
            return exc

    import time

    with (
        psycopg.connect(dsn) as lock,
        psycopg.connect(dsn, autocommit=True) as observer,
    ):
        lock.execute("SELECT * FROM ag_tasks FOR UPDATE")
        blocker = lock.info.backend_pid
        pool = ThreadPoolExecutor(2)
        futures = [pool.submit(run, b) for b in (first, second)]
        try:
            try:
                deadline = time.monotonic() + 15
                while True:
                    graph = observer.execute(
                        "SELECT pid,pg_blocking_pids(pid),query "
                        "FROM pg_stat_activity WHERE datname=current_database() AND wait_e"
                        "vent_type='Lock'"
                    ).fetchall()
                    task_waiters = {
                        pid
                        for pid, parents, query in graph
                        if blocker in parents and "ag_tasks" in query
                    }
                    principal_waiters = {
                        pid
                        for pid, parents, query in graph
                        if task_waiters.intersection(parents) and "ag_principals" in query
                    }
                    if len(task_waiters) == len(principal_waiters) == 1:
                        assert len(task_waiters | principal_waiters) == 2
                        assert blocker not in task_waiters | principal_waiters
                        print(
                            "REAL_ACCEPT_LOCK_CHAIN",
                            blocker,
                            sorted(task_waiters),
                            sorted(principal_waiters),
                        )
                        break
                    assert time.monotonic() < deadline
                    time.sleep(0.01)
            finally:
                lock.rollback()
        finally:
            try:
                results = collect_futures(futures, timeout=30)
            finally:
                pool.shutdown(wait=True)
    successes = [r for r in results if not isinstance(r, LedgerError)]
    assert len(successes) == (1 if same_proof else 2)
    assert len({r.operation_id for r in successes}) == 1
    records = read_records(dsn)
    assert [r.kind for r in records] == (
        ["BOOTSTRAP", "FIRST"] if same_proof else ["BOOTSTRAP", "FIRST", "RETRY"]
    )
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (1,)
        assert conn.execute(
            "SELECT count(*) FROM ag_ledger_events WHERE phase='RESERVE'"
        ).fetchone() == (1,)


@pytest.mark.parametrize("round", range(10))
def test_task_stream_rows_and_independent_heads(ledger, dsn, downstream_dsn, round):
    items, verifier, publisher = legal_shared_operations(dsn, downstream_dsn)
    first, second = items
    bundle = shared_retry_bundle(second, dsn)
    with (
        psycopg.connect(dsn) as lock,
        psycopg.connect(dsn, autocommit=True) as observer,
    ):
        stream = lock.execute(
            "SELECT stream_id FROM ag_audit_streams WHERE tenant_id=%s",
            (first["tenant"],),
        ).fetchone()[0]
        lock.execute(
            "SELECT head_seq FROM ag_audit_streams WHERE stream_id=%s FOR UPDATE",
            (stream,),
        )
        blocker = lock.execute("SELECT pg_backend_pid()").fetchone()[0]
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(second["adapter"].accept, bundle)
            result = future.result(15)
        assert result.operation_id == second["op"]
        assert observer.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE %s=ANY(pg_blocking_pids(pid))",
            (blocker,),
        ).fetchone() == (0,)
        lock.rollback()
    records = read_records(dsn)
    streams = {r.scope.stream_id for r in records}
    assert len(streams) == 2
    for stream_id in streams:
        own = [r for r in records if r.scope.stream_id == stream_id]
        assert [r.seq for r in own] == list(range(1, len(own) + 1))
        assert all(own[i].previous_digest == own[i - 1].digest for i in range(1, len(own)))


@pytest.mark.parametrize("round", range(10))
def test_sigkill_uncommitted_head_and_real_new_process_no_sequence_burn(
    ledger, dsn, downstream_dsn, round
):
    import multiprocessing
    import os
    import signal
    import time

    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    before = state(dsn, downstream_dsn)
    context = multiprocessing.get_context("fork")
    receiving, sending = context.Pipe(duplex=False)

    def child(kill_target):
        original = journal.append_tx

        def pause(conn, stream, **kwargs):
            result = original(conn, stream, **kwargs)
            if kill_target and kwargs["kind"] == "FIRST":
                sending.send(("at_uncommitted_head", os.getpid(), conn.info.backend_pid))
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    time.sleep(0.01)
                raise RuntimeError("finite child coordination timeout")
            return result

        journal.append_tx = pause
        try:
            returned = env.adapter.accept(bundle)
            sending.send(("accepted", os.getpid(), returned.operation_id))
        except BaseException as exc:
            sending.send(("child_exception", os.getpid(), type(exc).__name__))
            raise

    first = context.Process(target=child, args=(True,))
    first.start()
    try:
        assert receiving.poll(30)
        label, old_pid, old_backend = receiving.recv()
        assert label == "at_uncommitted_head" and old_pid == first.pid
        os.kill(old_pid, signal.SIGKILL)
        first.join(30)
        assert first.exitcode == -signal.SIGKILL
        with psycopg.connect(dsn, autocommit=True) as observer:
            deadline = time.monotonic() + 15
            while observer.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE pid=%s", (old_backend,)
            ).fetchone()[0]:
                assert time.monotonic() < deadline
                time.sleep(0.01)
        assert state(dsn, downstream_dsn) == before
        second = context.Process(target=child, args=(False,))
        second.start()
        second.join(30)
        assert second.exitcode == 0 and second.pid != old_pid
        assert receiving.poll(5)
        label, new_pid, operation = receiving.recv()
        assert label == "accepted" and new_pid == second.pid and operation
        assert [(r.kind, r.seq) for r in read_records(dsn)] == [
            ("BOOTSTRAP", 1),
            ("FIRST", 2),
        ]
    finally:
        if first.is_alive():
            first.kill()
            first.join(30)
        if "second" in locals() and second.is_alive():
            second.kill()
            second.join(30)
        receiving.close()
        sending.close()


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize(
    "mode", ("before_bool", "before_descriptor", "after_bool", "opaque_closure")
)
def test_hooks_never_promote_untrusted_material_or_non_none_returns(
    ledger, dsn, downstream_dsn, mode, round
):
    env = signed_env(dsn, downstream_dsn)
    if mode == "opaque_closure":
        env.adapter.accept(env.bundle())
    bundle = env.bundle()
    trusted = env.evidence.binding(bundle)
    before = state(dsn, downstream_dsn)
    opts = {}
    if mode.startswith("before"):

        def before_hook(conn, context):
            return True if mode == "before_bool" else trusted.descriptor

        opts["before_create"] = before_hook
    elif mode == "after_bool":

        def after_hook(conn, operation, disposition, baseline):
            return True

        opts["after_link"] = after_hook
    else:
        original_trusted = trusted

        def ordinary_binding(conn, operation, disposition):
            return original_trusted(conn, operation, disposition)

        trusted = ordinary_binding
    with pytest.raises((ValueError, LedgerError)):
        env.service.accept_invocation(
            bundle.invocation, bundle.permissions, binding=trusted, **opts
        )
    assert state(dsn, downstream_dsn) == before


def test_signed_retry_preserves_maximum_legal_original_quote(ledger, dsn, downstream_dsn):
    from dataclasses import replace

    from agent_guard.tools import policy
    from agent_guard.tools.catalog import snapshot_from_bytes
    from agent_guard.tools.params import parse_tool_id, parse_tool_params

    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    v = bundle.invocation
    tool = parse_tool_id(v.tool_id)
    quote = policy.resolve_tool_resources(
        env.service._catalog,
        tenant_id=v.tenant_id,
        task_id=v.task_id,
        tool_id=tool,
        params=parse_tool_params(tool, v.canonical_params),
        operation_facts=env.service._operation_facts,
        caller_grant_id=v.grant_id,
        caller_holder_client_id=v.holder_client_id,
        caller_holder_kid=v.holder_kid,
    )
    cost = env.service._cost_for_new(quote)
    # Historical quote storage explicitly accepts plain JSON, including whitespace.
    raw = cost.quote_snapshot + b" " * (65536 - len(cost.quote_snapshot))
    assert len(raw) == 65536 and snapshot_from_bytes(raw) == snapshot_from_bytes(
        cost.quote_snapshot
    )
    cost = replace(cost, quote_snapshot=raw)
    accepted = env.service._ledger.accept(
        v, cost, after_link=env.evidence.binding(bundle).after_link()
    )
    retry = env.bundle()
    before = state(dsn, downstream_dsn)
    returned = env.adapter.accept(retry)
    assert (
        returned.disposition is AcceptDisposition.EXISTING and returned.cost.quote_snapshot == raw
    )
    accept_retry_only(
        before,
        state(dsn, downstream_dsn),
        evidence_ref=retry.evidence_ref,
        proof_jti=retry.invocation.proof_jti,
        operation_id=accepted.operation_id,
    )


def test_claimed_executing_operation_fresh_retry_keeps_complete_state(ledger, dsn, downstream_dsn):
    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    claim = env.service._claim(accepted.operation_id, "actual-executing-retry-owner")
    assert claim.operation.status == "EXECUTING"
    retry = env.bundle()
    before = state(dsn, downstream_dsn)
    returned = env.adapter.accept(retry)
    assert returned.status == "EXECUTING" and returned.disposition is AcceptDisposition.EXISTING
    accept_retry_only(
        before,
        state(dsn, downstream_dsn),
        evidence_ref=retry.evidence_ref,
        proof_jti=retry.invocation.proof_jti,
        operation_id=accepted.operation_id,
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "head_seq",
        "record_kind",
        "record_xid",
        "facts",
        "proof_digest",
        "reserve_node",
        "grant_counter",
        "old_operation",
        "bootstrap",
        "outbox",
        "downstream",
    ),
)
def test_created_full_effect_oracle_rejects_unrelated_or_falsified_deltas(
    ledger, dsn, downstream_dsn, mutation
):
    import copy
    import json

    from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
    from agent_guard.crypto.sm import sm3_b64url
    from tests.fixtures.receipts import accept_created_only

    env = signed_env(dsn, downstream_dsn)
    original = env.adapter.accept(env.bundle())
    bundle = env.bundle(
        "oracle-new", tool="procurement.request.read", params={"request_id": "req-001"}
    )
    before = state(dsn, downstream_dsn)
    result = env.adapter.accept(bundle)
    after = state(dsn, downstream_dsn)
    accept_created_only(before, after, bundle=bundle, result=result)
    bad = copy.deepcopy(after)

    def alter(table, predicate, change):
        for index, (encoded,) in enumerate(bad["gateway"][table]):
            row = json.loads(encoded)
            if predicate(row):
                change(row)
                bad["gateway"][table][index] = (json.dumps(row, separators=(",", ":")),)
                return
        raise AssertionError("negative control target missing")

    if mutation == "head_seq":
        alter(
            "ag_audit_streams",
            lambda row: True,
            lambda row: row.update(head_seq=row["head_seq"] + 1),
        )
    elif mutation in ("record_kind", "record_xid", "facts"):

        def change(row):
            if mutation == "record_kind":
                row["kind"] = "RETRY"
            elif mutation == "record_xid":
                row["created_xid"] = "0"
            else:
                wire = load_strict_json(bytes.fromhex(row["raw"][2:]))
                wire["facts"]["calls"] = 2
                raw = canonical_json_bytes(wire)
                row["raw"] = "\\x" + raw.hex()
                row["digest"] = sm3_b64url(raw)

        alter(
            "ag_audit_records",
            lambda row: row["operation_id"] == result.operation_id,
            change,
        )
    elif mutation == "proof_digest":
        alter(
            "ag_proofs",
            lambda row: row["operation_id"] == result.operation_id,
            lambda row: row.update(proof_digest="corrupt-proof"),
        )
    elif mutation == "reserve_node":
        alter(
            "ag_ledger_event_nodes",
            lambda row: True,
            lambda row: row.update(calls_reserved_delta=2),
        )
    elif mutation == "grant_counter":
        alter("ag_grants", lambda row: True, lambda row: row.update(calls_settled=1))
    elif mutation == "old_operation":
        alter(
            "ag_operations",
            lambda row: row["operation_id"] == original.operation_id,
            lambda row: row.update(status="UNKNOWN"),
        )
    elif mutation == "bootstrap":
        alter(
            "ag_audit_bootstrap",
            lambda row: True,
            lambda row: row.update(boundary="LEGACY_WITH_GAPS"),
        )
    elif mutation == "outbox":
        bad["gateway"]["ag_receipt_outbox"].append(("{}",))
    else:
        bad["downstream"]["ds_operations"].append(("{}",))
    with pytest.raises(AssertionError):
        accept_created_only(before, bad, bundle=bundle, result=result)
    assert state(dsn, downstream_dsn) == after


def _direct_cost(env, bundle):
    from agent_guard.tools import policy
    from agent_guard.tools.params import parse_tool_id, parse_tool_params

    v = bundle.invocation
    tool = parse_tool_id(v.tool_id)
    quote = policy.resolve_tool_resources(
        env.service._catalog,
        tenant_id=v.tenant_id,
        task_id=v.task_id,
        tool_id=tool,
        params=parse_tool_params(tool, v.canonical_params),
        operation_facts=env.service._operation_facts,
        caller_grant_id=v.grant_id,
        caller_holder_client_id=v.holder_client_id,
        caller_holder_kid=v.holder_kid,
    )
    return env.service._cost_for_new(quote)


@pytest.mark.parametrize("entry", ("accept", "checked"))
@pytest.mark.parametrize("disposition", ("CREATED", "EXISTING"))
@pytest.mark.parametrize("behavior", ("normal", "none", "non_none", "raise"))
def test_typed_after_link_executes_once_or_rolls_back(
    ledger, dsn, downstream_dsn, monkeypatch, entry, disposition, behavior
):
    from agent_guard.audit.contracts import EmptyTaskBootstrapSeed, ExistingStreamRef
    from tests.fixtures.receipts import accept_initial_only

    env = signed_env(dsn, downstream_dsn)
    if disposition == "EXISTING":
        env.adapter.accept(env.bundle())
    bundle = env.bundle()
    cost = _direct_cost(env, bundle)
    before = state(dsn, downstream_dsn)
    captured = []
    connections = []
    count_before = len(read_records(dsn))
    seeds = []
    original_capture = journal.capture_empty_task_tx

    def capture(conn, context):
        seed = original_capture(conn, context)
        seeds.append(seed)
        return seed

    monkeypatch.setattr(journal, "capture_empty_task_tx", capture)

    def original_bound(conn, op, actual):
        connections.append(conn)
        captured.append(("binding", journal.tx_id(conn), conn.info.backend_pid))
        assert actual.name == disposition
        assert conn.execute(
            "SELECT operation_id FROM ag_operation_evidence WHERE evidence_ref=%s",
            (bundle.evidence_ref,),
        ).fetchone() == (op.operation_id,)

    trusted = env.evidence.binding(bundle).compose(original_bound)

    def callback(conn, op, actual, baseline):
        captured.append(("callback", journal.tx_id(conn), conn.info.backend_pid))
        assert conn is connections[0] and actual.name == disposition
        assert conn.execute(
            "SELECT operation_id FROM ag_proofs WHERE proof_jti=%s",
            (bundle.invocation.proof_jti,),
        ).fetchone() == (op.operation_id,)
        assert conn.execute("SELECT count(*) FROM ag_audit_records").fetchone() == (count_before,)
        if disposition == "CREATED":
            assert type(baseline) is EmptyTaskBootstrapSeed
            assert baseline.tx_id == journal.tx_id(conn)
            assert baseline.origin == "FROM_EMPTY_TASK"
            assert baseline.scope_key == trusted.descriptor.scope_key
        else:
            assert type(baseline) is ExistingStreamRef and not hasattr(baseline, "tx_id")
            assert (
                baseline.scope.gateway_id,
                baseline.scope.tenant_id,
                baseline.scope.task_id,
            ) == (trusted.descriptor.scope_key)
        if behavior == "raise":
            raise RuntimeError("typed after-link failure")
        if behavior == "non_none":
            return True
        return None

    opts = {"after_link": trusted.after_link(None if behavior == "none" else callback)}
    invoke = env.service._ledger.accept
    if entry == "checked":
        invoke = env.service._ledger.accept_checked
        opts["existing_validator"] = lambda conn, op: None
    if behavior in ("non_none", "raise"):
        with pytest.raises((ValueError, RuntimeError)) as failure:
            invoke(bundle.invocation, cost, **opts)
        assert type(failure.value) is (ValueError if behavior == "non_none" else RuntimeError)
        assert state(dsn, downstream_dsn) == before
    else:
        returned = invoke(bundle.invocation, cost, **opts)
        after = state(dsn, downstream_dsn)
        assert returned.disposition.name == disposition
        if disposition == "CREATED":
            assert len(seeds) == 1
            accept_initial_only(before, after, seed=seeds[0], bundle=bundle, result=returned)
        else:
            assert seeds == []
            accept_retry_only(
                before,
                after,
                evidence_ref=bundle.evidence_ref,
                proof_jti=bundle.invocation.proof_jti,
                operation_id=returned.operation_id,
            )
        with psycopg.connect(dsn) as conn:
            witness = conn.execute(
                "SELECT created_xid FROM ag_audit_records WHERE evidence_ref=%s",
                (bundle.evidence_ref,),
            ).fetchone()[0]
        assert captured[0][1] == witness
    assert [item[0] for item in captured] == (
        ["binding"] if behavior == "none" else ["binding", "callback"]
    )
    assert len({item[1] for item in captured}) == len({item[2] for item in captured}) == 1
