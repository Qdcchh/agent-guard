"""Tool/result variants must bind before any terminal ledger decision."""

import json
from types import SimpleNamespace

import pytest

from agent_guard.contracts.execution import (
    DownstreamOutcome,
    ExecutionError,
    ExecutionErrorCode,
    TerminalAction,
    ToolId,
)
from agent_guard.execution.service import ExecutionService
from agent_guard.tools.results import bind_result, parse_result


@pytest.mark.parametrize("tool", list(ToolId))
def test_read_success_only_binds_to_read_tools(tool):
    raw = json.dumps({"kind": "read", "operation_id": "op", "tool_id": tool.value}).encode()
    record = parse_result(raw)
    operation = SimpleNamespace(
        operation_id="op",
        tool_id=tool.value,
        canonical_params=b"{}",
        quote_snapshot=None,
        amount_fen=0,
    )
    outcome = DownstreamOutcome("op", tool, b"{}", None, 0, None, raw, False, False)
    decision = ExecutionService._decide(None, operation, outcome)
    if tool in (ToolId.REQUEST_READ, ToolId.DOCUMENT_READ):
        assert bind_result(record, operation_id="op", tool_id=tool.value) is None
        assert decision is TerminalAction.SETTLE
    else:
        with pytest.raises(ExecutionError) as exc:
            bind_result(record, operation_id="op", tool_id=tool.value)
        assert exc.value.code is ExecutionErrorCode.DOWNSTREAM_INCONSISTENT
        assert decision is None


@pytest.mark.parametrize("tool", list(ToolId))
def test_refusal_remains_bound_for_all_four_tools(tool):
    record = parse_result(
        json.dumps(
            {
                "kind": "refusal",
                "operation_id": "op",
                "tool_id": tool.value,
                "reason": "DECLINED",
            }
        ).encode()
    )
    assert bind_result(record, operation_id="op", tool_id=tool.value) is None
    with pytest.raises(ExecutionError) as exc:
        bind_result(record, operation_id="wrong", tool_id=tool.value)
    assert exc.value.code is ExecutionErrorCode.DOWNSTREAM_INCONSISTENT


@pytest.mark.parametrize(
    "kind,tool",
    [
        ("order", ToolId.REQUEST_READ),
        ("notification", ToolId.DOCUMENT_READ),
    ],
)
def test_reverse_success_variant_does_not_bind(kind, tool):
    payload = (
        {
            "kind": "order",
            "operation_id": "op",
            "order_id": "order",
            "supplier_id": "s",
            "quote_id": "q",
            "quote_version": "1",
            "items": [{"sku": "s", "quantity": 1, "unit_price_fen": 1}],
            "total_fen": 1,
        }
        if kind == "order"
        else {
            "kind": "notification",
            "operation_id": "op",
            "notification_id": "n",
            "template_id": "t",
            "recipient_id": "r",
        }
    )
    with pytest.raises(ExecutionError) as exc:
        bind_result(
            parse_result(json.dumps(payload).encode()),
            operation_id="op",
            tool_id=tool.value,
        )
    assert exc.value.code is ExecutionErrorCode.DOWNSTREAM_INCONSISTENT
