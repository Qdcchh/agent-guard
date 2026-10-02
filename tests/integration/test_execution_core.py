"""A2.1 core execution behaviour: P01-P08, P12 and the outbox obligations.

Every case runs against a real PostgreSQL gateway ledger and a real independent
downstream database. Injected faults are clearly marked as *layered doubles*
(port-level or monkeypatched store steps) and are never described as real
network outages, real TLS or real cryptography.
"""

from __future__ import annotations

import json

import psycopg
import pytest

from agent_guard.contracts.execution import (
    ExecutionError,
    ExecutionErrorCode,
    OperationStatus,
    TerminalAction,
    ToolId,
)
from agent_guard.contracts.ledger import AcceptDisposition
from agent_guard.execution import store as exec_store
from agent_guard.tools.catalog import snapshot_from_bytes
from tests.fixtures.dbstate import fetch_all, fetch_counters, fetch_counts
from tests.fixtures.execution import (
    ORDER_AMOUNT_FEN,
    SUPPLIER_ID,
    build_env,
    expire_lease,
    make_reference_operation,
    notification_params,
    order_params,
    read_params,
)

pytestmark = pytest.mark.integration


# ----------------------------------------------------------------- helpers


def assert_counters(dsn, grant_id, **expected):
    counters = fetch_counters(dsn, grant_id)
    for key, value in expected.items():
        assert counters[key] == value, f"{grant_id}.{key}: {counters[key]} != {value}"


def assert_three_layer_counters(dsn, tree, **expected):
    for grant_id in (tree.root_id, tree.mid_id, tree.leaf_id):
        assert_counters(dsn, grant_id, **expected)


def ledger_events(dsn, operation_id):
    return fetch_all(
        dsn,
        "SELECT phase, seq FROM ag_ledger_events WHERE operation_id = %s ORDER BY seq",
        (operation_id,),
    )


class ResponseLossPort:
    """Port-boundary double: the real downstream commits, the response is lost.

    This is a *response-loss* injection at the ``DownstreamPort`` boundary. It
    is NOT a real network outage and must not be reported as one.
    """

    def __init__(self, inner):
        self.inner = inner
        self.executed = []

    def execute(self, **kwargs):
        outcome = self.inner.execute(**kwargs)
        self.executed.append(outcome)
        raise RuntimeError("simulated response loss after downstream commit")

    def query(self, **kwargs):
        return self.inner.query(**kwargs)


class NoneThenRealPort:
    """Port double that reports 'nothing known' on the first N queries."""

    def __init__(self, inner, misses: int = 1):
        self.inner = inner
        self.misses = misses
        self.queries = 0

    def execute(self, **kwargs):
        return self.inner.execute(**kwargs)

    def query(self, **kwargs):
        self.queries += 1
        if self.queries <= self.misses:
            return None
        return self.inner.query(**kwargs)


# ------------------------------------------------------------------- P01


def test_p01_three_layer_order_settles_once(a2):
    """P01: one 700 CNY order settles 70000 fen / 1 call on root, mid and leaf."""
    inv = a2.tree.invocation(
        idempotency_key="p01-order",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    assert accepted.disposition is AcceptDisposition.CREATED
    assert accepted.status == "RESERVED"
    assert accepted.cost.amount_fen == ORDER_AMOUNT_FEN

    # accept alone must not have touched the downstream
    with psycopg.connect(a2.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_operations").fetchone()[0] == 0

    result = a2.service.run_operation(accepted.operation_id)
    assert result.status == OperationStatus.SUCCEEDED.value
    assert result.action is TerminalAction.SETTLE

    assert_three_layer_counters(
        a2.gateway_dsn,
        a2.tree,
        amount_reserved=0,
        amount_settled=ORDER_AMOUNT_FEN,
        calls_reserved=0,
        calls_settled=1,
    )
    assert ledger_events(a2.gateway_dsn, accepted.operation_id) == [("RESERVE", 0), ("SETTLE", 1)]

    with psycopg.connect(a2.downstream_dsn) as conn:
        orders = conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0]
        assert orders == 1
        assert conn.execute("SELECT count(*) FROM ds_operations").fetchone()[0] == 1

    outbox = a2.service.outbox_entry(accepted.operation_id)
    assert outbox["status"] == "SUCCEEDED"
    assert outbox["amount_fen"] == ORDER_AMOUNT_FEN
    assert outbox["receipt_status"] == "PENDING"
    assert outbox["receipt_jws"] is None  # B is missing: nothing is signed

    changes = json.loads(outbox["ledger_changes_json"].decode("utf-8"))
    assert changes["operation_id"] == accepted.operation_id
    assert [event["phase"] for event in changes["events"]] == ["RESERVE", "SETTLE"]
    assert [node["grant_id"] for node in changes["events"][1]["nodes"]] == [
        a2.tree.root_id,
        a2.tree.mid_id,
        a2.tree.leaf_id,
    ]
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 1


# ------------------------------------------------------------------- P02


def test_p02_persisted_refusal_releases_and_blocks_late_success(a2):
    """P02: a persisted terminal downstream refusal is FAILED + RELEASE, once."""
    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        approved_suppliers=frozenset({"a-different-supplier"}),
    )
    env.downstream.provision()
    inv = env.tree.invocation(
        idempotency_key="p02-refused",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = env.service.accept_invocation(inv, env.permission())
    assert accepted.disposition is AcceptDisposition.CREATED

    result = env.service.run_operation(accepted.operation_id)
    assert result.status == OperationStatus.FAILED.value
    assert result.action is TerminalAction.RELEASE
    assert result.outcome is not None and result.outcome.final_rejection is True

    assert_three_layer_counters(
        env.gateway_dsn,
        env.tree,
        amount_reserved=0,
        amount_settled=0,
        calls_reserved=0,
        calls_settled=0,
    )
    assert ledger_events(env.gateway_dsn, accepted.operation_id) == [("RESERVE", 0), ("RELEASE", 1)]
    assert fetch_counts(env.gateway_dsn)["ag_ledger_events"] == 2

    outbox = env.service.outbox_entry(accepted.operation_id)
    assert outbox["status"] == "FAILED"
    assert outbox["amount_fen"] == 0  # FAILED receipts report a final amount of 0

    # a late success for the same key is impossible: the refusal is persisted
    late = env.downstream.execute(
        service_secret=env.secret,
        operation_id=accepted.operation_id,
        tool_id=ToolId.ORDER_CREATE,
        canonical_params=order_params(),
        quote=snapshot_from_bytes(accepted.cost.quote_snapshot),
        expected_amount_fen=accepted.cost.amount_fen,
    )
    assert late.final_rejection is True
    assert late.effect_ref is None
    with psycopg.connect(env.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0] == 0

    # and the terminal state is never overwritten
    with pytest.raises(ExecutionError) as excinfo:
        env.service.run_operation(accepted.operation_id)
    assert excinfo.value.code is ExecutionErrorCode.ILLEGAL_TRANSITION


# ------------------------------------------------------------------- P03


def test_p03_zero_amount_read_settles_calls(a2):
    """P03: a read costs 0 fen but still settles exactly one call."""
    inv = a2.tree.invocation(
        idempotency_key="p03-read",
        tool_id="procurement.request.read",
        params=read_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    assert accepted.cost.amount_fen == 0
    assert accepted.cost.calls == 1

    result = a2.service.run_operation(accepted.operation_id)
    assert result.status == OperationStatus.SUCCEEDED.value
    assert result.action is TerminalAction.SETTLE

    assert_three_layer_counters(
        a2.gateway_dsn,
        a2.tree,
        amount_reserved=0,
        amount_settled=0,
        calls_reserved=0,
        calls_settled=1,
    )
    outbox = a2.service.outbox_entry(accepted.operation_id)
    assert outbox["amount_fen"] == 0


def test_p03_zero_amount_failure_releases_calls(a2):
    """P03: a refused zero-amount call releases its reserved call.

    Both zero-amount tools are covered: a read the downstream does not serve
    and a notification to a recipient it does not serve. Each is a persisted
    terminal refusal, so the reserved *call* is released and no receipt claims
    a settlement. The notification targets a *real* operation owned by the same
    grant/holder, because the access policy refuses made-up targets.
    """
    target = make_reference_operation(a2, key="p03-refuse-target", settle=True)

    for tool_id, params in (
        ("procurement.request.read", read_params()),
        (
            "notification.template.send",
            notification_params(operation_id=target),
        ),
    ):
        env = build_env(
            tree=a2.tree,
            gateway_dsn=a2.gateway_dsn,
            downstream_dsn=a2.downstream_dsn,
            approved_recipients=frozenset(),
            served_requests=frozenset(),
        )
        env.downstream.provision()
        key = f"p03-refuse-{tool_id}"
        inv = env.tree.invocation(idempotency_key=key, tool_id=tool_id, params=params)
        before = fetch_counters(env.gateway_dsn, env.tree.root_id)
        accepted = env.service.accept_invocation(inv, env.permission())
        assert accepted.cost.amount_fen == 0
        assert accepted.cost.calls == 1

        result = env.service.run_operation(accepted.operation_id)
        assert result.status == OperationStatus.FAILED.value, tool_id
        assert result.action is TerminalAction.RELEASE, tool_id
        assert result.outcome is not None and result.outcome.final_rejection is True

        # the reserved call is released again: nothing new is left behind
        after = fetch_counters(env.gateway_dsn, env.tree.root_id)
        assert after == before, tool_id
        assert ledger_events(env.gateway_dsn, accepted.operation_id) == [
            ("RESERVE", 0),
            ("RELEASE", 1),
        ]
        outbox = env.service.outbox_entry(accepted.operation_id)
        assert outbox["status"] == "FAILED"
        assert outbox["amount_fen"] == 0


def test_p03_notification_effect_at_most_once_and_read_result_fixed(a2):
    """P03: notifications are persisted-idempotent and reads return a fixed result."""
    target = make_reference_operation(a2, key="p03-notify-target", settle=True)
    note = a2.tree.invocation(
        idempotency_key="p03-notify",
        tool_id="notification.template.send",
        params=notification_params(operation_id=target),
    )
    accepted = a2.service.accept_invocation(note, a2.permission())
    first = a2.service.run_operation(accepted.operation_id)
    assert first.status == OperationStatus.SUCCEEDED.value

    # same key, same intent: the very same notification, never a second one
    replay = a2.downstream.execute(
        service_secret=a2.secret,
        operation_id=accepted.operation_id,
        tool_id=ToolId.NOTIFICATION_SEND,
        canonical_params=notification_params(operation_id=target),
        quote=None,
        expected_amount_fen=0,
    )
    assert replay.already_existed is True
    assert replay.effect_ref == first.outcome.effect_ref
    with psycopg.connect(a2.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_notifications").fetchone()[0] == 1

    # read result is fixed on replay
    read = a2.tree.invocation(
        idempotency_key="p03-read-fixed",
        tool_id="procurement.request.read",
        params=read_params(),
    )
    read_accepted = a2.service.accept_invocation(read, a2.permission())
    one = a2.service.run_operation(read_accepted.operation_id)
    two = a2.downstream.query(service_secret=a2.secret, operation_id=read_accepted.operation_id)
    assert one.outcome.result_bytes == two.result_bytes


# ------------------------------------------------------------- P05 and P08


def test_p05_response_lost_keeps_budget_then_settles_same_order(a2):
    """P05: a committed order whose response is lost keeps the budget reserved."""
    inv = a2.tree.invocation(
        idempotency_key="p05-order",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    port = ResponseLossPort(a2.downstream)
    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        downstream=port,
    )
    result = env.service.run_operation(accepted.operation_id, owner_token="worker-p05-a")
    assert result.status == OperationStatus.UNKNOWN.value
    assert result.action is None
    assert len(port.executed) == 1  # the downstream really committed

    assert_three_layer_counters(
        a2.gateway_dsn,
        a2.tree,
        amount_reserved=ORDER_AMOUNT_FEN,
        amount_settled=0,
        calls_reserved=1,
        calls_settled=0,
    )
    assert ledger_events(a2.gateway_dsn, accepted.operation_id) == [("RESERVE", 0)]
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 0  # UNKNOWN has no receipt

    # a second worker takes over after the lease TTL and settles the same order
    expire_lease(a2.gateway_dsn, accepted.operation_id)
    recovered = env.service.run_operation(accepted.operation_id, owner_token="worker-p05-b")
    assert recovered.status == OperationStatus.SUCCEEDED.value
    assert recovered.action is TerminalAction.SETTLE
    assert recovered.lease.fencing_version > result.lease.fencing_version
    with psycopg.connect(a2.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM ds_operations").fetchone()[0] == 1
    assert ledger_events(a2.gateway_dsn, accepted.operation_id) == [("RESERVE", 0), ("SETTLE", 1)]
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 2


def test_p08_query_none_does_not_release_then_late_success_settles(a2):
    """P08: 'nothing known yet' is not a failure; the late success settles once."""
    inv = a2.tree.invocation(
        idempotency_key="p08-order",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    # the downstream call is lost before it reaches the service: nothing exists
    port = NoneThenRealPort(a2.downstream, misses=1)
    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        downstream=port,
    )
    # query-only recovery: nothing known -> keep UNKNOWN, never RELEASE
    first = env.service.reconcile(accepted.operation_id, owner_token="worker-p08")
    assert first.status == OperationStatus.UNKNOWN.value
    assert first.action is None
    assert_three_layer_counters(
        a2.gateway_dsn,
        a2.tree,
        amount_reserved=ORDER_AMOUNT_FEN,
        amount_settled=0,
        calls_reserved=1,
        calls_settled=0,
    )
    assert ledger_events(a2.gateway_dsn, accepted.operation_id) == [("RESERVE", 0)]

    # the old in-flight request finally lands downstream
    env.downstream.execute(
        service_secret=env.secret,
        operation_id=accepted.operation_id,
        tool_id=ToolId.ORDER_CREATE,
        canonical_params=order_params(),
        quote=snapshot_from_bytes(accepted.cost.quote_snapshot),
        expected_amount_fen=accepted.cost.amount_fen,
    )
    final = env.service.reconcile(accepted.operation_id, owner_token="worker-p08")
    assert final.status == OperationStatus.SUCCEEDED.value
    assert final.action is TerminalAction.SETTLE
    assert_three_layer_counters(
        a2.gateway_dsn,
        a2.tree,
        amount_reserved=0,
        amount_settled=ORDER_AMOUNT_FEN,
        calls_reserved=0,
        calls_settled=1,
    )
    with psycopg.connect(a2.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0] == 1
    assert ledger_events(a2.gateway_dsn, accepted.operation_id) == [("RESERVE", 0), ("SETTLE", 1)]


# ------------------------------------------------------------------- P07


@pytest.mark.parametrize(
    "stage,target",
    [
        ("counters", "apply_terminal_counters"),
        ("event", "insert_terminal_event"),
        ("outbox", "insert_pending_receipt"),
        ("status", "transition_status"),
    ],
)
def test_p07_terminal_transaction_rolls_back_completely(a2, monkeypatch, stage, target):
    """P07: a failure in any terminal stage rolls back counters, event, outbox
    and status together; the operation can then be recovered normally."""
    inv = a2.tree.invocation(
        idempotency_key=f"p07-{stage}",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    original = getattr(exec_store, target)

    def boom(*args, **kwargs):
        raise RuntimeError(f"injected failure at {stage}")

    monkeypatch.setattr(exec_store, target, boom)
    with pytest.raises(RuntimeError, match="injected failure"):
        a2.service.run_operation(accepted.operation_id, owner_token="worker-p07")

    # nothing from the terminal transaction survived
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 1  # only RESERVE
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_event_nodes"] == 3
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 0
    assert_three_layer_counters(
        a2.gateway_dsn,
        a2.tree,
        amount_reserved=ORDER_AMOUNT_FEN,
        amount_settled=0,
        calls_reserved=1,
        calls_settled=0,
    )
    assert a2.service.operation_status(accepted.operation_id) == OperationStatus.EXECUTING.value

    monkeypatch.setattr(exec_store, target, original)
    recovered = a2.service.run_operation(accepted.operation_id, owner_token="worker-p07")
    assert recovered.status == OperationStatus.SUCCEEDED.value
    assert recovered.action is TerminalAction.SETTLE
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 1
    assert ledger_events(a2.gateway_dsn, accepted.operation_id) == [("RESERVE", 0), ("SETTLE", 1)]
    assert_three_layer_counters(
        a2.gateway_dsn,
        a2.tree,
        amount_reserved=0,
        amount_settled=ORDER_AMOUNT_FEN,
        calls_reserved=0,
        calls_settled=1,
    )


# ------------------------------------------------------------------ P12


def _tampered_direct_call(env, accepted, *, quote, params, amount_fen):
    """Simulate a downstream that already executed *different* material.

    This is a direct call into the real mock downstream with different intent
    material, standing in for a tampered or duplicated downstream request. It
    creates a real effect in the real downstream database.
    """
    return env.downstream.execute(
        service_secret=env.secret,
        operation_id=accepted.operation_id,
        tool_id=ToolId.ORDER_CREATE,
        canonical_params=params,
        quote=quote,
        expected_amount_fen=amount_fen,
    )


def test_p12_amount_mismatch_keeps_budget_and_never_settles(a2):
    """P12: a confirmed-but-different amount is UNKNOWN, never a fake success."""
    inv = a2.tree.invocation(
        idempotency_key="p12-amount",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    from agent_guard.contracts.execution import QuoteItem, TrustedQuoteSnapshot

    other = TrustedQuoteSnapshot(
        quote_id="quote-001",
        quote_version="1",
        supplier_id=SUPPLIER_ID,
        items=(QuoteItem(sku="sku-001", quantity=1, unit_price_fen=50000),),
        total_fen=50000,
    )
    outcome = _tampered_direct_call(
        a2, accepted, quote=other, params=order_params(), amount_fen=50000
    )
    assert outcome.effect_ref is not None  # a real effect already exists

    result = a2.service.reconcile(accepted.operation_id)
    assert result.status == OperationStatus.UNKNOWN.value
    assert result.action is None
    assert result.outcome is not None and result.outcome.effect_ref is not None
    assert_three_layer_counters(
        a2.gateway_dsn,
        a2.tree,
        amount_reserved=ORDER_AMOUNT_FEN,
        amount_settled=0,
        calls_reserved=1,
        calls_settled=0,
    )
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 0


def test_p12_intent_mismatch_keeps_budget(a2):
    """P12: different canonical params (a different intent) never settles."""
    inv = a2.tree.invocation(
        idempotency_key="p12-intent",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    altered = order_params(items=(("sku-001", 2),))
    outcome = _tampered_direct_call(
        a2,
        accepted,
        quote=snapshot_from_bytes(accepted.cost.quote_snapshot),
        params=altered,
        amount_fen=ORDER_AMOUNT_FEN,
    )
    assert outcome.effect_ref is not None

    result = a2.service.reconcile(accepted.operation_id)
    assert result.status == OperationStatus.UNKNOWN.value
    assert result.action is None
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 0
    assert_three_layer_counters(
        a2.gateway_dsn,
        a2.tree,
        amount_reserved=ORDER_AMOUNT_FEN,
        amount_settled=0,
        calls_reserved=1,
        calls_settled=0,
    )


def test_p12_same_total_different_supplier_never_settles(a2):
    """P12: an equal total from another supplier is inconsistent -> UNKNOWN."""
    inv = a2.tree.invocation(
        idempotency_key="p12-snapshot",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())

    from agent_guard.contracts.execution import QuoteItem, TrustedQuoteSnapshot

    swapped_supplier = TrustedQuoteSnapshot(
        quote_id="quote-001",
        quote_version="1",
        supplier_id="another-supplier",
        items=(QuoteItem(sku="sku-001", quantity=1, unit_price_fen=ORDER_AMOUNT_FEN),),
        total_fen=ORDER_AMOUNT_FEN,
    )
    _tampered_direct_call(
        a2,
        accepted,
        quote=swapped_supplier,
        params=order_params(),
        amount_fen=ORDER_AMOUNT_FEN,
    )
    result = a2.service.reconcile(accepted.operation_id, owner_token="worker-p12-sup")
    assert result.status == OperationStatus.UNKNOWN.value
    assert result.action is None
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 0
    assert_three_layer_counters(
        a2.gateway_dsn,
        a2.tree,
        amount_reserved=ORDER_AMOUNT_FEN,
        amount_settled=0,
        calls_reserved=1,
        calls_settled=0,
    )


def test_p12_reallocated_unit_prices_never_settles(a2):
    """P12: the same total from a different unit-price allocation is UNKNOWN."""
    from agent_guard.contracts.execution import QuoteItem, TrustedQuoteSnapshot

    inv = a2.tree.invocation(
        idempotency_key="p12-prices",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    reallocated = TrustedQuoteSnapshot(
        quote_id="quote-001",
        quote_version="1",
        supplier_id=SUPPLIER_ID,
        items=(QuoteItem(sku="sku-001", quantity=1, unit_price_fen=ORDER_AMOUNT_FEN - 1),),
        total_fen=ORDER_AMOUNT_FEN - 1,
    )
    _tampered_direct_call(
        a2,
        accepted,
        quote=reallocated,
        params=order_params(),
        amount_fen=ORDER_AMOUNT_FEN - 1,
    )
    result = a2.service.reconcile(accepted.operation_id, owner_token="worker-p12-price")
    assert result.status == OperationStatus.UNKNOWN.value
    assert result.action is None
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 0


# ------------------------------------------------------------------ P06


def test_p06_recovery_after_terminal_window_has_no_duplicate_effect(a2):
    """P06: a confirmed effect with a crashed terminal window settles exactly once."""
    inv = a2.tree.invocation(
        idempotency_key="p06-order",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    outcome = a2.downstream.execute(
        service_secret=a2.secret,
        operation_id=accepted.operation_id,
        tool_id=ToolId.ORDER_CREATE,
        canonical_params=order_params(),
        quote=snapshot_from_bytes(accepted.cost.quote_snapshot),
        expected_amount_fen=accepted.cost.amount_fen,
    )
    assert outcome.effect_ref is not None

    first = a2.service.reconcile(accepted.operation_id, owner_token="worker-p06")
    assert first.status == OperationStatus.SUCCEEDED.value
    assert first.action is TerminalAction.SETTLE
    # terminal states are never written again: a second attempt is refused
    with pytest.raises(ExecutionError) as excinfo:
        a2.service.run_operation(accepted.operation_id, owner_token="worker-p06-again")
    assert excinfo.value.code is ExecutionErrorCode.ILLEGAL_TRANSITION

    with psycopg.connect(a2.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM ds_operations").fetchone()[0] == 1
    assert ledger_events(a2.gateway_dsn, accepted.operation_id) == [("RESERVE", 0), ("SETTLE", 1)]
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 2


# ----------------------------------------------------------------- OBL06


def test_obl06_receipt_material_is_stable_immutable_and_unsigned(a2):
    """OBL06: the outbox material is stable, immutable and never claims a
    signature or a canonical encoding while B is missing."""
    from agent_guard.execution.receipts import receipt_iat

    inv = a2.tree.invocation(
        idempotency_key="obl06-order",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    a2.service.run_operation(accepted.operation_id, owner_token="worker-obl06")

    first = a2.service.outbox_entry(accepted.operation_id)
    second = a2.service.outbox_entry(accepted.operation_id)
    assert first == second  # a retry never rolls a new id/iat/material

    # receipt_id is deterministic for the operation and matches the stored one
    from agent_guard.execution.receipts import receipt_id_for

    assert first["receipt_id"] == receipt_id_for(accepted.operation_id)

    # iat is derived from the persisted created_at as integer UTC seconds
    assert receipt_iat(first["created_at"]) == int(first["created_at"].timestamp())
    assert first["created_at"].tzinfo is not None

    # nothing is signed and nothing claims an SM3 / RFC 8785 encoding
    assert first["receipt_status"] == "PENDING"
    assert first["receipt_jws"] is None
    assert b"sm3" not in first["ledger_changes_json"].lower()
    assert b"rfc8785" not in first["ledger_changes_json"].lower()

    # the material can never be rewritten, and a signed row would be frozen too
    for sql, params in (
        (
            "UPDATE ag_receipt_outbox SET receipt_id = 'tampered' WHERE operation_id = %s",
            (accepted.operation_id,),
        ),
        (
            "UPDATE ag_receipt_outbox SET ledger_changes_json = %s WHERE operation_id = %s",
            (b"{}", accepted.operation_id),
        ),
        (
            "UPDATE ag_receipt_outbox SET result_bytes = %s WHERE operation_id = %s",
            (b"{}", accepted.operation_id),
        ),
        (
            "UPDATE ag_receipt_outbox SET created_at = now() WHERE operation_id = %s",
            (accepted.operation_id,),
        ),
        (
            "UPDATE ag_receipt_outbox SET amount_fen = 0 WHERE operation_id = %s",
            (accepted.operation_id,),
        ),
        ("DELETE FROM ag_receipt_outbox WHERE operation_id = %s", (accepted.operation_id,)),
    ):
        with psycopg.connect(a2.gateway_dsn) as conn:
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    conn.execute(sql, params)

    assert a2.service.outbox_entry(accepted.operation_id) == first


def test_obl06_full_snapshot_comparison_drives_the_decision(a2):
    """OBL06: the *complete* snapshot (supplier and unit prices) is compared."""
    inv = a2.tree.invocation(
        idempotency_key="obl06-snapshot",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    stored = snapshot_from_bytes(accepted.cost.quote_snapshot)
    assert stored is not None
    assert stored.supplier_id == SUPPLIER_ID
    assert [(i.sku, i.quantity, i.unit_price_fen) for i in stored.items] == [
        ("sku-001", 1, ORDER_AMOUNT_FEN)
    ]

    # a byte-identical snapshot settles
    a2.downstream.execute(
        service_secret=a2.secret,
        operation_id=accepted.operation_id,
        tool_id=ToolId.ORDER_CREATE,
        canonical_params=order_params(),
        quote=stored,
        expected_amount_fen=accepted.cost.amount_fen,
    )
    result = a2.service.reconcile(accepted.operation_id, owner_token="worker-obl06-snap")
    assert result.status == OperationStatus.SUCCEEDED.value
    assert result.action is TerminalAction.SETTLE
