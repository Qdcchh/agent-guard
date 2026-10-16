"""Real PG metric controls; native normal-owner pilot/official is a separate entry.

Layered signed_env fixtures are not described as normal browser authorization.
The delivery reference uses SignedTransport; native assembly separately uses
an independent persistent audit PostgreSQL and true four-writer bootstrap.
"""

import time

import psycopg
import pytest
from psycopg.rows import dict_row

from agent_guard.audit.delivery import DeliveryWorker, verify_checkpoint
from agent_guard.contracts.ledger import LedgerError
from experiments.agent_guard_bench.microbench import (
    collect_database_storage,
    collect_process_hardware,
    run_independent_database_trace,
)
from experiments.agent_guard_bench.runner import (
    MissingPrerequisite,
    _bounded_waves,
    _task_groups,
)
from experiments.agent_guard_bench.statistics import (
    effect_budget_metrics,
    rate,
    revocation_bounds,
)
from experiments.agent_guard_bench.workload import generate_suite
from tests.fixtures.a31_common import read_records
from tests.fixtures.a31_delivery import SignedTransport, tls_dir
from tests.fixtures.execution import order_params
from tests.integration.test_receipt_publication import final_env

pytestmark = pytest.mark.integration


def test_terminal_receipt_journal_checkpoint_drain_metrics(ledger, dsn, downstream_dsn):
    started = time.monotonic_ns()
    env, operation, _, _, publisher = final_env(dsn, downstream_dsn)
    terminal = time.monotonic_ns()
    publication = publisher.publish(operation)
    ready = time.monotonic_ns()
    records = read_records(dsn)
    transport = SignedTransport(records[0].scope, tls_dir())
    try:
        with psycopg.connect(dsn) as connection:
            connection.execute("UPDATE ag_audit_delivery SET registration_state='REGISTERED'")
        worker = DeliveryWorker(
            lambda: psycopg.connect(dsn), transport.client, trust=transport.trust
        )
        report = worker.deliver_once(records[0].scope.stream_id)
        anchored = time.monotonic_ns()
        assert report.status == "ACKED"
        with psycopg.connect(dsn) as connection:
            status, receipt_status, receipt_jws = connection.execute(
                "SELECT o.status,r.receipt_status,r.receipt_jws FROM ag_operations o "
                "JOIN ag_receipt_outbox r USING(operation_id) WHERE operation_id=%s",
                (operation,),
            ).fetchone()
            ack, head = connection.execute(
                "SELECT ack_sequence,ack_head_digest FROM ag_audit_delivery"
            ).fetchone()
            checkpoint = connection.execute(
                "SELECT checkpoint_jws FROM ag_audit_delivery_batches"
            ).fetchone()[0]
        assert status == "SUCCEEDED" and receipt_status == "READY"
        assert (
            receipt_jws == publication.receipt_jws
            and ack == len(records)
            and head == records[-1].digest
        )
        assert verify_checkpoint(
            checkpoint, trust=transport.trust, expected_scope=records[0].scope
        ).claims.sequence == len(records)
        assert rate(1, started, terminal)["duration_ns"] < rate(1, started, anchored)["duration_ns"]
        assert started < terminal <= ready <= anchored
    finally:
        transport.close()


def test_effect_budget_revocation_metrics_with_database_oracle(a2):
    accepted = a2.service.accept_invocation(
        a2.invocation(idempotency_key="measurement-real", params=order_params()),
        a2.permission(),
    )
    assert a2.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
    policies = {
        grant: {"amount_limit": amount, "call_limit": calls}
        for grant, amount, calls in zip(
            (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id),
            a2.tree.amount_limits,
            a2.tree.call_limits,
            strict=True,
        )
    }
    with psycopg.connect(a2.gateway_dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        nodes = connection.execute(
            "SELECT e.event_id,n.* FROM ag_ledger_events e "
            "JOIN ag_ledger_event_nodes n USING(event_id) "
            "WHERE e.operation_id=%s ORDER BY e.event_id,n.position",
            (accepted.operation_id,),
        ).fetchall()
        grants = connection.execute(
            "SELECT grant_id,amount_reserved,amount_settled,calls_reserved,calls_settled "
            "FROM ag_grants WHERE grant_id=ANY(%s)",
            (list(policies),),
        ).fetchall()
    facts = {
        g["grant_id"]: {
            "final_counters": [
                g[k]
                for k in (
                    "amount_reserved",
                    "amount_settled",
                    "calls_reserved",
                    "calls_settled",
                )
            ],
            "events": [
                {
                    "sequence": n["event_id"],
                    "delta": [
                        n[k]
                        for k in (
                            "amount_reserved_delta",
                            "amount_settled_delta",
                            "calls_reserved_delta",
                            "calls_settled_delta",
                        )
                    ],
                }
                for n in nodes
                if n["grant_id"] == g["grant_id"]
            ],
        }
        for g in grants
    }
    with psycopg.connect(a2.downstream_dsn) as downstream:
        effects = downstream.execute(
            "SELECT operation_id FROM ds_orders WHERE operation_id=%s",
            (accepted.operation_id,),
        ).fetchall()
    metrics = effect_budget_metrics(
        policies=policies,
        facts=facts,
        effects=[
            {
                "operation_id": e[0],
                "intent_hash": "independently-approved-measurement-intent",
                "permitted_by_policy": True,
            }
            for e in effects
        ],
    )
    assert not metrics["budget_set_violations"] and not metrics["duplicate_effects"]
    assert set(metrics["all_ancestor_highwater"]) == set(policies)
    assert all(
        v["amount"] == 70000 and v["calls"] == 1 for v in metrics["all_ancestor_highwater"].values()
    )
    lower = time.monotonic_ns()
    with psycopg.connect(a2.gateway_dsn) as connection:
        connection.execute(
            "UPDATE ag_grants SET revoked=true,revoked_at=clock_timestamp() WHERE grant_id=%s",
            (a2.tree.root_id,),
        )
    upper = time.monotonic_ns()
    sent = time.monotonic_ns()
    with pytest.raises(LedgerError):
        a2.service.accept_invocation(
            a2.invocation(idempotency_key="measurement-post-revoke", params=order_params()),
            a2.permission(),
        )
    ended = time.monotonic_ns()
    with psycopg.connect(a2.gateway_dsn) as connection:
        clock = connection.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0]
    bounds = revocation_bounds(
        commit_lower_ns=lower,
        commit_upper_ns=upper,
        rejected_send_ns=sent,
        rejected_end_ns=ended,
        server_clock_ns=int(clock * 1_000_000_000),
    )
    assert 0 <= bounds["lower_ns"] <= bounds["upper_ns"]
    assert len(effects) == 1


def test_environment_capacity_storage_manifest_and_payload_preflight(dsn):
    hardware = collect_process_hardware()
    assert hardware["logical_cpus"] > 0 and hardware["architecture"]
    with psycopg.connect(dsn) as connection:
        storage = collect_database_storage(connection)
    assert any(s[0] == "server_version" for s in storage["settings"])
    assert all(row[3] <= row[5] and row[4] <= row[5] for row in storage["relation_sizes"])
    traced = run_independent_database_trace(
        lambda: psycopg.connect(dsn),
        lambda connection: connection.execute("SELECT count(*) FROM ag_grants").fetchone(),
    )
    assert traced["connections"] == 1 and traced["query_count"] == 5
    assert (
        traced["official_attempts"] == 0 and traced["db_clock_before"] <= traced["db_clock_final"]
    )


def test_pilot_not_counted_and_all_fixed_repetitions_retained(dsn):
    plans = generate_suite()
    assert len(plans) == 8 and sum(len(p.intentions) for p in plans) == 40000
    assert sum(len(p.warmup) for p in plans) == 2000
    assert [p.mode for p in plans[:4]] == [p.mode for p in plans[4:]][::-1]
    pairs = [g for g in _task_groups(plans[0], plans[0].intentions) if g[0].attack_class == 9]
    assert len(pairs) == 50 and all(
        len(g) == 2 and g[0].root == g[1].root and g[0].leaf != g[1].leaf for g in pairs
    )
    assert [len(w) for w in _bounded_waves(pairs)] == [25, 25]
    # Real PG negative control proves that these pure plans have not minted
    # grants or inserted 40000 pretend operations into this owned fixture.
    with psycopg.connect(dsn) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM ag_operations WHERE task_id LIKE %s", ("A9-P%",)
            ).fetchone()[0]
            == 0
        )
    from experiments.agent_guard_bench.runner import run_native_owned_repetition

    with pytest.raises(MissingPrerequisite, match="all STOP"):
        run_native_owned_repetition(
            mode=plans[0].mode, seed=plans[0].seed, evidence_directory="unused"
        )
