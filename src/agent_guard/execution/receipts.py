"""Pending-signature receipt material for the A2.1 outbox (9.5).

The terminal gateway transaction writes this material together with the
terminal ledger change. It is *material*, not a receipt: no signature, no SM3
and no canonical encoding is produced here. ``receipt_jws`` stays NULL and
``receipt_status`` stays ``PENDING`` until the internal publisher verifies
and signs the complete original material, then atomically publishes ``READY``.

``receipt_id`` is derived deterministically from the operation id so a retried
terminal transaction can never roll a second identifier, and ``iat`` is derived
from the persisted ``created_at`` as an integer number of UTC seconds so a
retry can never roll a new timestamp. ``ledger_changes_json`` is plain UTF-8
JSON of the structured change object — explicitly *not* B's RFC 8785 canonical
bytes and not covered by any SM3 here.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from agent_guard.contracts.execution import (
    OperationStatus,
    PendingReceipt,
    TerminalAction,
)
from agent_guard.contracts.ledger import PROFILE
from agent_guard.execution.store import EventNodeDelta, LedgerEvent

#: Fixed namespace for the deterministic receipt id; not a secret.
RECEIPT_NAMESPACE = uuid.UUID("5f2b7c1e-0a4d-5a6b-9c8d-3e1f0a2b4c6d")


def receipt_id_for(operation_id: str) -> str:
    """Deterministic, stable receipt identifier for one operation."""
    return uuid.uuid5(RECEIPT_NAMESPACE, f"agent-guard:receipt:{operation_id}").hex


def receipt_iat(created_at: datetime) -> int:
    """UTC integer seconds derived from the persisted outbox timestamp."""
    moment = (
        created_at if created_at.tzinfo is not None else created_at.replace(tzinfo=timezone.utc)
    )
    return int(moment.timestamp())


def _node_payload(node: EventNodeDelta) -> dict:
    return {
        "grant_id": node.grant_id,
        "amount_reserved_delta": node.amount_reserved_delta,
        "amount_settled_delta": node.amount_settled_delta,
        "calls_reserved_delta": node.calls_reserved_delta,
        "calls_settled_delta": node.calls_settled_delta,
    }


def ledger_changes_bytes(
    *,
    operation_id: str,
    reserve_event: LedgerEvent,
    terminal_nodes: tuple[EventNodeDelta, ...],
    terminal_action: TerminalAction,
) -> bytes:
    """Structured ledger change payload: RESERVE first, then the terminal move.

    Nodes are stored root-to-leaf and every applicable node appears exactly
    once per event. The bytes are plain JSON chosen for immutability and
    structural comparison; A2.3 re-encodes them canonically for ``ledger_sm3``.
    """
    payload = {
        "operation_id": operation_id,
        "events": [
            {
                "phase": reserve_event.phase,
                "seq": reserve_event.seq,
                "nodes": [_node_payload(node) for node in reserve_event.nodes],
            },
            {
                "phase": terminal_action.value,
                "seq": 1,
                "nodes": [_node_payload(node) for node in terminal_nodes],
            },
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def build_pending_receipt(
    *,
    operation,  # agent_guard.ledger.store.OperationRow
    action: TerminalAction,
    root_grant_id: str,
    result_bytes: bytes,
    ledger_changes: bytes,
    created_at: datetime,
) -> PendingReceipt:
    """Assemble the immutable material persisted next to the terminal event."""
    status = (
        OperationStatus.SUCCEEDED if action is TerminalAction.SETTLE else OperationStatus.FAILED
    )
    # FAILED receipts report a final amount of 0 (9.5); SUCCEEDED reports the
    # confirmed reserved cost, which is 0 for reads and notifications.
    amount_fen = operation.amount_fen if action is TerminalAction.SETTLE else 0
    return PendingReceipt(
        receipt_id=receipt_id_for(operation.operation_id),
        operation_id=operation.operation_id,
        profile=PROFILE,
        tenant_id=operation.tenant_id,
        task_id=operation.task_id,
        root_grant_id=root_grant_id,
        grant_id=operation.grant_id,
        tool_id=operation.tool_id,
        tool_version=operation.tool_version,
        status=status,
        amount_fen=amount_fen,
        ledger_changes_json=ledger_changes,
        result_bytes=result_bytes,
        token_digest=operation.token_digest,
        proof_digest=operation.proof_digest,
        intent_digest=operation.intent_digest,
        evidence_ref=operation.evidence_ref,
        created_at=created_at,
    )
