"""Final result variant and 256-item accept boundaries against real PostgreSQL."""

from dataclasses import replace

import psycopg
import pytest

from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode, ToolId
from agent_guard.tools.catalog import (
    CatalogQuote,
    CatalogQuoteLine,
    snapshot_from_bytes,
)
from tests.fixtures.dbstate import fetch_counters, fetch_counts
from tests.fixtures.execution import (
    constraints_for,
    expire_lease,
    order_params,
    permission_for,
)
from tests.integration.test_verified_execution import TOOLS, signed_env

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("tool", [TOOLS[2], TOOLS[3]])
@pytest.mark.parametrize("entry", ["execute", "query"])
def test_read_shaped_nonread_outcome_stays_unknown_then_recovers(
    ledger, dsn, downstream_dsn, tool, entry
):
    env = signed_env(dsn, downstream_dsn)
    params = None
    if tool == TOOLS[3]:
        target = env.adapter.accept(
            env.bundle("target", tool=TOOLS[0], params={"request_id": "req-001"})
        )
        assert env.service.run_operation(target.operation_id).status == "SUCCEEDED"
        params = {
            "template_id": "order-created",
            "recipient_id": "user-demo-001",
            "operation_id": target.operation_id,
        }
    before_counts = fetch_counts(dsn)
    with psycopg.connect(dsn) as conn:
        grants = [row[0] for row in conn.execute("SELECT grant_id FROM ag_grants ORDER BY depth")]
    before_counters = {g: fetch_counters(dsn, g) for g in grants}
    accepted = env.adapter.accept(env.bundle("boundary", tool=tool, params=params))
    operation = env.service.load_operation(accepted.operation_id)
    real = env.downstream

    class ReadShapedPort:
        def execute(self, **kwargs):
            return self.bad(real.execute(**kwargs))

        def query(self, **kwargs):
            return self.bad(real.query(**kwargs))

        def bad(self, outcome):
            assert outcome is not None
            return replace(
                outcome,
                effect_ref=None,
                result_bytes=canonical_json_bytes(
                    {
                        "kind": "read",
                        "operation_id": accepted.operation_id,
                        "tool_id": tool,
                    }
                ),
            )

    if entry == "query":
        real.execute(
            service_secret=env.service._secret,
            operation_id=accepted.operation_id,
            tool_id=ToolId(tool),
            canonical_params=operation.canonical_params,
            quote=snapshot_from_bytes(operation.quote_snapshot),
            expected_amount_fen=operation.amount_fen,
        )
    env.service._downstream = ReadShapedPort()
    result = (env.service.run_operation if entry == "execute" else env.service.reconcile)(
        accepted.operation_id
    )
    assert result.status == "UNKNOWN" and result.action is None
    assert env.service.outbox_entry(accepted.operation_id) is None
    for g in grants:
        b = before_counters[g]
        assert fetch_counters(dsn, g) == dict(
            b,
            amount_reserved=b["amount_reserved"] + operation.amount_fen,
            calls_reserved=b["calls_reserved"] + 1,
        )
    with psycopg.connect(dsn) as conn:
        assert conn.execute(
            "SELECT phase FROM ag_ledger_events WHERE operation_id=%s",
            (accepted.operation_id,),
        ).fetchall() == [("RESERVE",)]
    assert fetch_counts(dsn)["ag_receipt_outbox"] == before_counts["ag_receipt_outbox"]
    env.service._downstream = real
    expire_lease(dsn, accepted.operation_id)
    assert env.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
    for g in grants:
        b = before_counters[g]
        assert fetch_counters(dsn, g) == dict(
            b,
            amount_settled=b["amount_settled"] + operation.amount_fen,
            calls_settled=b["calls_settled"] + 1,
        )
    with psycopg.connect(dsn) as conn:
        assert conn.execute(
            "SELECT phase FROM ag_ledger_events WHERE operation_id=%s ORDER BY seq",
            (accepted.operation_id,),
        ).fetchall() == [("RESERVE",), ("SETTLE",)]
    assert fetch_counts(dsn)["ag_receipt_outbox"] == before_counts["ag_receipt_outbox"] + 1
    table = "ds_orders" if tool == TOOLS[2] else "ds_notifications"
    with psycopg.connect(downstream_dsn) as conn:
        assert conn.execute(
            f"SELECT count(*) FROM {table} WHERE operation_id=%s",
            (accepted.operation_id,),
        ).fetchone() == (1,)


@pytest.mark.parametrize("count", [256, 257, 1000])
def test_item_bound_is_enforced_before_accept_and_full_256_recovers(a2, count):
    skus = tuple(f"sku-{i}" for i in range(count))
    a2.catalog.replace_quote(
        CatalogQuote(
            "quote-001",
            "1",
            "supplier-001",
            "req-001",
            tuple(CatalogQuoteLine(sku, 1, 1) for sku in skus),
        )
    )
    permission = permission_for(
        a2.tree, chain=tuple(constraints_for(i, skus=skus) for i in range(3))
    )
    before_counts = fetch_counts(a2.gateway_dsn)
    grants = (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id)
    before = {g: fetch_counters(a2.gateway_dsn, g) for g in grants}
    invocation = a2.tree.invocation(
        tool_id=TOOLS[2], params=order_params(items=tuple((sku, 1) for sku in skus))
    )
    if count > 256:
        with pytest.raises(ExecutionError) as exc:
            a2.service.accept_invocation(invocation, permission)
        assert exc.value.code is ExecutionErrorCode.INVALID_PARAMS
        assert fetch_counts(a2.gateway_dsn) == before_counts
        assert {g: fetch_counters(a2.gateway_dsn, g) for g in grants} == before
        with psycopg.connect(a2.downstream_dsn) as conn:
            for table in ("ds_orders", "ds_notifications", "ds_operations"):
                assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
        return
    accepted = a2.service.accept_invocation(invocation, permission)
    assert accepted.cost.amount_fen == 256
    real = a2.downstream

    class LostResponse:
        def execute(self, **kwargs):
            real.execute(**kwargs)
            raise RuntimeError("synthetic response loss after real durable effect")

        def query(self, **kwargs):
            return real.query(**kwargs)

    a2.service._downstream = LostResponse()
    assert a2.service.run_operation(accepted.operation_id).status == "UNKNOWN"
    for g in grants:
        assert fetch_counters(a2.gateway_dsn, g) == dict(
            amount_reserved=256, amount_settled=0, calls_reserved=1, calls_settled=0
        )
    assert a2.service.outbox_entry(accepted.operation_id) is None
    expire_lease(a2.gateway_dsn, accepted.operation_id)
    a2.service._downstream = real
    assert a2.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
    assert (
        len(
            snapshot_from_bytes(
                a2.service.load_operation(accepted.operation_id).quote_snapshot
            ).items
        )
        == 256
    )
    for g in grants:
        assert fetch_counters(a2.gateway_dsn, g) == dict(
            amount_reserved=0, amount_settled=256, calls_reserved=0, calls_settled=1
        )
    with psycopg.connect(a2.gateway_dsn) as conn:
        assert conn.execute(
            "SELECT phase FROM ag_ledger_events WHERE operation_id=%s ORDER BY seq",
            (accepted.operation_id,),
        ).fetchall() == [("RESERVE",), ("SETTLE",)]
    with psycopg.connect(a2.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_orders").fetchone() == (1,)
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 1
