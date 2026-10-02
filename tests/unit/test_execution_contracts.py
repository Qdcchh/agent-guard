"""A2 contract type checks: identifiers and state machine values must match
the protocol (docs/oauth-oidc-sm2-mvp.md 9.4, docs/security-model.md 5).

These tests pin shared-type constants only. They verify no cryptography and
no execution behavior.
"""

from __future__ import annotations

import pytest

from agent_guard.contracts.execution import (
    TERMINAL_STATUSES,
    ExecutionError,
    ExecutionErrorCode,
    OperationStatus,
    ReceiptStatus,
    TerminalAction,
    ToolId,
)

pytestmark = pytest.mark.unit


def test_tool_identifiers_are_the_complete_protocol_values():
    assert ToolId.REQUEST_READ.value == "procurement.request.read"
    assert ToolId.DOCUMENT_READ.value == "procurement.document.read"
    assert ToolId.ORDER_CREATE.value == "procurement.order.create"
    assert ToolId.NOTIFICATION_SEND.value == "notification.template.send"
    assert len({t.value for t in ToolId}) == 4


def test_operation_status_matches_security_model_state_machine():
    assert {s.value for s in OperationStatus} == {
        "RESERVED",
        "EXECUTING",
        "SUCCEEDED",
        "FAILED",
        "UNKNOWN",
    }
    assert set(TERMINAL_STATUSES) == {OperationStatus.SUCCEEDED, OperationStatus.FAILED}


def test_terminal_actions_are_exclusive_and_receipt_status_independent():
    assert {a.value for a in TerminalAction} == {"SETTLE", "RELEASE"}
    assert {s.value for s in ReceiptStatus} == {"PENDING", "READY"}


def test_execution_error_codes_are_distinct():
    values = [code.value for code in ExecutionErrorCode]
    assert len(values) == len(set(values))
    assert "TRUSTED_DEPENDENCY_UNAVAILABLE" in values
    assert "DOWNSTREAM_INCONSISTENT" in values


def test_execution_error_carries_code():
    err = ExecutionError(ExecutionErrorCode.LEASE_LOST, "fencing version stale")
    assert err.code is ExecutionErrorCode.LEASE_LOST
    assert "LEASE_LOST" in str(err)


def test_downstream_outcome_binds_full_quote_snapshot():
    """C6: the outcome must expose the whole snapshot, not ids/totals only."""
    from dataclasses import fields

    from agent_guard.contracts.execution import DownstreamOutcome, TrustedQuoteSnapshot

    names = {f.name for f in fields(DownstreamOutcome)}
    assert "quote" in names
    assert "quote_id" not in names and "quote_version" not in names
    quote_type = next(f.type for f in fields(DownstreamOutcome) if f.name == "quote")
    assert "TrustedQuoteSnapshot" in str(quote_type)
    # the snapshot itself carries supplier and per-line unit prices
    snap_names = {f.name for f in fields(TrustedQuoteSnapshot)}
    assert {"quote_id", "quote_version", "supplier_id", "items", "total_fen"} <= snap_names


def test_pending_receipt_material_is_byte_immutable():
    """Receipt material stores plain bytes, never a shared mutable dict."""
    import dataclasses
    import inspect
    from datetime import datetime, timezone

    from agent_guard.contracts.execution import (
        OperationStatus,
        PendingReceipt,
    )

    fields_by_name = {f.name: f for f in dataclasses.fields(PendingReceipt)}
    assert "ledger_changes_json" in fields_by_name
    assert "ledger_changes" not in fields_by_name
    assert "created_at" in fields_by_name  # receipt iat derives from it
    assert inspect.isclass(PendingReceipt)
    material = PendingReceipt(
        receipt_id="receipt-1",
        operation_id="op-1",
        profile="GM-MVP-1",
        tenant_id="tenant-demo",
        task_id="task-001",
        root_grant_id="grant-root-1",
        grant_id="grant-leaf-1",
        tool_id="procurement.order.create",
        tool_version="1",
        status=OperationStatus.SUCCEEDED,
        amount_fen=70000,
        ledger_changes_json=b'{"operation_id":"op-1","events":[]}',
        result_bytes=b"{}",
        token_digest="opaque-not-sm3",
        proof_digest="opaque-not-sm3",
        intent_digest="opaque-not-sm3",
        evidence_ref="evidence://run/op-1",
        created_at=datetime.now(tz=timezone.utc),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        material.result_bytes = b"tampered"
    with pytest.raises(dataclasses.FrozenInstanceError):
        material.ledger_changes_json = b"{}"


def test_result_query_requires_evidence_ref():
    """Result-read proofs register into ag_proofs whose evidence_ref is NOT NULL."""
    import dataclasses

    from agent_guard.contracts.execution import VerifiedResultQuery

    names = {f.name for f in dataclasses.fields(VerifiedResultQuery)}
    assert "evidence_ref" in names
    assert "tool_id" not in names and "idempotency_key" not in names
