"""A2-P14: downstream idempotency, intent conflicts and service authentication.

The mock downstream is a real separate database with its own unique
constraints. The independent *gateway service secret* is the only accepted
credential: agent/caller secrets are refused and nothing is executed or leaked.
Authentication is enforced by the service itself, not by hiding a port.
"""

from __future__ import annotations

import threading

import psycopg
import pytest

from agent_guard.contracts.execution import (
    ExecutionError,
    ExecutionErrorCode,
    ToolId,
    TrustedQuoteSnapshot,
)
from agent_guard.tools.catalog import snapshot_from_bytes
from tests.fixtures.execution import (
    ORDER_AMOUNT_FEN,
    SUPPLIER_ID,
    notification_params,
    order_params,
    read_params,
)

pytestmark = pytest.mark.integration

ROUNDS = 10


def _execute(env, *, operation_id, tool_id, params, quote, amount):
    return env.downstream.execute(
        service_secret=env.secret,
        operation_id=operation_id,
        tool_id=tool_id,
        canonical_params=params,
        quote=quote,
        expected_amount_fen=amount,
    )


def _quote() -> TrustedQuoteSnapshot:
    from agent_guard.contracts.execution import QuoteItem

    return TrustedQuoteSnapshot(
        quote_id="quote-001",
        quote_version="1",
        supplier_id=SUPPLIER_ID,
        items=(QuoteItem(sku="sku-001", quantity=1, unit_price_fen=ORDER_AMOUNT_FEN),),
        total_fen=ORDER_AMOUNT_FEN,
    )


def _counts(a2) -> dict[str, int]:
    with psycopg.connect(a2.downstream_dsn) as conn:
        return {
            "ops": conn.execute("SELECT count(*) FROM ds_operations").fetchone()[0],
            "orders": conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0],
            "notifications": conn.execute("SELECT count(*) FROM ds_notifications").fetchone()[0],
        }


# ------------------------------------------------------------ idempotency


def test_p14_same_key_same_intent_replays_one_order(a2):
    """P14: the same key and intent always produce the very same order."""
    inv = a2.tree.invocation(
        idempotency_key="p14-replay",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    quote = snapshot_from_bytes(accepted.cost.quote_snapshot)

    first = _execute(
        a2,
        operation_id=accepted.operation_id,
        tool_id=ToolId.ORDER_CREATE,
        params=order_params(),
        quote=quote,
        amount=ORDER_AMOUNT_FEN,
    )
    assert first.already_existed is False
    for _ in range(3):
        again = _execute(
            a2,
            operation_id=accepted.operation_id,
            tool_id=ToolId.ORDER_CREATE,
            params=order_params(),
            quote=quote,
            amount=ORDER_AMOUNT_FEN,
        )
        assert again.already_existed is True
        assert again.effect_ref == first.effect_ref
        assert again.result_bytes == first.result_bytes

    assert _counts(a2) == {"ops": 1, "orders": 1, "notifications": 0}


def test_p14_notification_and_read_are_idempotent_too(a2):
    """P14: notifications and reads are protected exactly like orders."""
    from tests.fixtures.execution import make_reference_operation

    target = make_reference_operation(a2, key="p14-note-target", settle=True)
    inv = a2.tree.invocation(
        idempotency_key="p14-note",
        tool_id="notification.template.send",
        params=notification_params(operation_id=target),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    first = _execute(
        a2,
        operation_id=accepted.operation_id,
        tool_id=ToolId.NOTIFICATION_SEND,
        params=notification_params(operation_id=target),
        quote=None,
        amount=0,
    )
    second = _execute(
        a2,
        operation_id=accepted.operation_id,
        tool_id=ToolId.NOTIFICATION_SEND,
        params=notification_params(operation_id=target),
        quote=None,
        amount=0,
    )
    assert second.already_existed is True
    assert second.effect_ref == first.effect_ref
    assert _counts(a2)["notifications"] == 1

    read_inv = a2.tree.invocation(
        idempotency_key="p14-read",
        tool_id="procurement.request.read",
        params=read_params(),
    )
    read_accepted = a2.service.accept_invocation(read_inv, a2.permission())
    one = _execute(
        a2,
        operation_id=read_accepted.operation_id,
        tool_id=ToolId.REQUEST_READ,
        params=read_params(),
        quote=None,
        amount=0,
    )
    two = _execute(
        a2,
        operation_id=read_accepted.operation_id,
        tool_id=ToolId.REQUEST_READ,
        params=read_params(),
        quote=None,
        amount=0,
    )
    assert two.already_existed is True
    assert two.result_bytes == one.result_bytes  # the read result is fixed


def test_p14_same_key_different_intent_is_refused(a2):
    """P14: reusing a downstream key with another intent never overwrites."""
    inv = a2.tree.invocation(
        idempotency_key="p14-conflict",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    quote = snapshot_from_bytes(accepted.cost.quote_snapshot)
    first = _execute(
        a2,
        operation_id=accepted.operation_id,
        tool_id=ToolId.ORDER_CREATE,
        params=order_params(),
        quote=quote,
        amount=ORDER_AMOUNT_FEN,
    )

    from agent_guard.contracts.execution import QuoteItem

    other_quote = TrustedQuoteSnapshot(
        quote_id="quote-001",
        quote_version="1",
        supplier_id=SUPPLIER_ID,
        items=(QuoteItem(sku="sku-001", quantity=2, unit_price_fen=ORDER_AMOUNT_FEN // 2),),
        total_fen=ORDER_AMOUNT_FEN,
    )
    for tool_id, params, bad_quote, amount in (
        (ToolId.ORDER_CREATE, order_params(items=(("sku-001", 2),)), quote, ORDER_AMOUNT_FEN),
        (ToolId.ORDER_CREATE, order_params(), other_quote, ORDER_AMOUNT_FEN),
        (ToolId.NOTIFICATION_SEND, notification_params(), None, 0),
        (ToolId.REQUEST_READ, read_params(), None, 0),
    ):
        with pytest.raises(ExecutionError) as excinfo:
            _execute(
                a2,
                operation_id=accepted.operation_id,
                tool_id=tool_id,
                params=params,
                quote=bad_quote,
                amount=amount,
            )
        assert excinfo.value.code is ExecutionErrorCode.DOWNSTREAM_INTENT_CONFLICT

    # the first effect is untouched
    assert _counts(a2) == {"ops": 1, "orders": 1, "notifications": 0}
    query = a2.downstream.query(service_secret=a2.secret, operation_id=accepted.operation_id)
    assert query.effect_ref == first.effect_ref


def test_p14_concurrent_downstream_executions_one_effect(a2):
    """P14: two concurrent executions of one key produce exactly one effect."""
    for round_no in range(ROUNDS):
        key = f"op-p14-conc-{round_no}"
        quote = _quote()
        barrier = threading.Barrier(2)
        results: list[object] = []
        lock = threading.Lock()

        def attempt(_barrier=barrier, _key=key, _quote=quote, _lock=lock, _results=results) -> None:
            _barrier.wait()
            try:
                outcome = _execute(
                    a2,
                    operation_id=_key,
                    tool_id=ToolId.ORDER_CREATE,
                    params=order_params(),
                    quote=_quote,
                    amount=ORDER_AMOUNT_FEN,
                )
                with _lock:
                    _results.append(outcome)
            except ExecutionError as exc:  # pragma: no cover - asserted below
                with _lock:
                    _results.append(exc)

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        outcomes = [r for r in results if not isinstance(r, Exception)]
        assert len(outcomes) == 2, results
        assert len({r.effect_ref for r in outcomes}) == 1
        assert sorted(r.already_existed for r in outcomes) == [False, True]

    assert _counts(a2)["orders"] == ROUNDS
    assert _counts(a2)["ops"] == ROUNDS


# --------------------------------------------------------- authentication


@pytest.mark.parametrize(
    "secret",
    ["", "wrong-secret", "agent-executor-secret", "test-only-downstream-service-secret "],
)
def test_p14_execute_refuses_missing_or_wrong_service_secret(a2, secret):
    """P14: only the independent gateway service secret may execute."""
    inv = a2.tree.invocation(
        idempotency_key="p14-auth-exec",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    with pytest.raises(ExecutionError) as excinfo:
        a2.downstream.execute(
            service_secret=secret,
            operation_id=accepted.operation_id,
            tool_id=ToolId.ORDER_CREATE,
            canonical_params=order_params(),
            quote=snapshot_from_bytes(accepted.cost.quote_snapshot),
            expected_amount_fen=ORDER_AMOUNT_FEN,
        )
    assert excinfo.value.code is ExecutionErrorCode.DOWNSTREAM_UNAUTHORIZED
    # the presented secret is never echoed back
    if secret:
        assert secret not in excinfo.value.detail
        assert secret not in str(excinfo.value)
    assert _counts(a2) == {"ops": 0, "orders": 0, "notifications": 0}


@pytest.mark.parametrize("secret", ["", "wrong-secret", "agent-planner-secret"])
def test_p14_query_refuses_missing_or_wrong_service_secret(a2, secret):
    """P14: unauthorised queries leak nothing and change nothing."""
    inv = a2.tree.invocation(
        idempotency_key="p14-auth-query",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    _execute(
        a2,
        operation_id=accepted.operation_id,
        tool_id=ToolId.ORDER_CREATE,
        params=order_params(),
        quote=snapshot_from_bytes(accepted.cost.quote_snapshot),
        amount=ORDER_AMOUNT_FEN,
    )
    with pytest.raises(ExecutionError) as excinfo:
        a2.downstream.query(service_secret=secret, operation_id=accepted.operation_id)
    assert excinfo.value.code is ExecutionErrorCode.DOWNSTREAM_UNAUTHORIZED
    assert _counts(a2) == {"ops": 1, "orders": 1, "notifications": 0}


def test_p14_unauthenticated_call_cannot_be_forced_by_a_direct_agent(a2):
    """P14: an agent presenting its own identity is refused exactly the same way."""
    inv = a2.tree.invocation(
        idempotency_key="p14-agent-direct",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = a2.service.accept_invocation(inv, a2.permission())
    with pytest.raises(ExecutionError) as excinfo:
        a2.downstream.execute(
            service_secret=a2.tree.executor[1],  # the agent's own kid
            operation_id=accepted.operation_id,
            tool_id=ToolId.ORDER_CREATE,
            canonical_params=order_params(),
            quote=snapshot_from_bytes(accepted.cost.quote_snapshot),
            expected_amount_fen=ORDER_AMOUNT_FEN,
        )
    assert excinfo.value.code is ExecutionErrorCode.DOWNSTREAM_UNAUTHORIZED
    assert _counts(a2)["orders"] == 0

    # and the query path leaks nothing about the accepted operation
    with pytest.raises(ExecutionError):
        a2.downstream.query(service_secret="agent-kid", operation_id=accepted.operation_id)


def test_p14_unknown_operation_query_returns_none_without_leaking(a2):
    """P14: an unknown key is ``None`` (not a failure) and not an error dump."""
    assert a2.downstream.query(service_secret=a2.secret, operation_id="never-existed") is None
    assert _counts(a2) == {"ops": 0, "orders": 0, "notifications": 0}


def test_p14_refused_key_can_never_produce_an_effect_later(a2):
    """P14: a persisted terminal refusal makes a later success impossible."""
    env_kwargs = dict(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        approved_suppliers=frozenset({"nobody"}),
    )
    from tests.fixtures.execution import build_env

    env = build_env(**env_kwargs)
    env.downstream.provision()
    inv = env.tree.invocation(
        idempotency_key="p14-refused",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    accepted = env.service.accept_invocation(inv, env.permission())
    outcome = _execute(
        env,
        operation_id=accepted.operation_id,
        tool_id=ToolId.ORDER_CREATE,
        params=order_params(),
        quote=snapshot_from_bytes(accepted.cost.quote_snapshot),
        amount=ORDER_AMOUNT_FEN,
    )
    assert outcome.final_rejection is True

    # even a later call with the "right" material cannot create an order
    late = _execute(
        env,
        operation_id=accepted.operation_id,
        tool_id=ToolId.ORDER_CREATE,
        params=order_params(),
        quote=snapshot_from_bytes(accepted.cost.quote_snapshot),
        amount=ORDER_AMOUNT_FEN,
    )
    assert late.final_rejection is True
    assert late.effect_ref is None
    assert _counts(env)["orders"] == 0
