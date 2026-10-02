"""SQL access layer for the A2.1 execution lifecycle.

Everything here runs inside a caller-owned gateway transaction and follows the
global lock order ``principals (when needed) -> task -> grants root-to-leaf ->
operation -> lease``; nothing in this module holds a lock across a downstream
call. The A1 ledger modules are used as-is (read/call only) for path loading,
locking and the accept transaction.

The terminal path is deliberately split into small steps
(:func:`apply_terminal_counters`, :func:`insert_terminal_event`,
:func:`insert_pending_receipt`, :func:`transition_status`) so a single gateway
transaction can roll all of them back together and so tests can inject a
failure at a chosen stage without any runtime bypass switch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import psycopg

from agent_guard.contracts.execution import (
    ExecutionError,
    ExecutionErrorCode,
    LeaseGrant,
    OperationStatus,
    PendingReceipt,
    TerminalAction,
)
from agent_guard.contracts.ledger import MAX_SAFE_INT
from agent_guard.ledger import store as ledger_store

OPERATION_COLUMNS = (
    "operation_id, tenant_id, task_id, tool_id, idempotency_key, grant_id, "
    "holder_client_id, holder_kid, tool_version, canonical_params, currency, "
    "amount_fen, calls, quote_id, quote_version, quote_snapshot, token_digest, "
    "proof_digest, intent_digest, evidence_ref, status, accepted_at"
)

TERMINAL_VALUES = (OperationStatus.SUCCEEDED.value, OperationStatus.FAILED.value)


@dataclass(frozen=True)
class EventNodeDelta:
    """One root-to-leaf node change of one ledger event."""

    position: int
    grant_id: str
    amount_reserved_delta: int
    amount_settled_delta: int
    calls_reserved_delta: int
    calls_settled_delta: int


@dataclass(frozen=True)
class LedgerEvent:
    phase: str
    seq: int
    nodes: tuple[EventNodeDelta, ...]


@dataclass(frozen=True)
class ClaimResult:
    """One lease claim: the locked operation, the held lease and the pre-claim state."""

    operation: ledger_store.OperationRow
    lease: LeaseGrant
    previous_status: str


def _utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ reads


def fetch_operation(
    conn: psycopg.Connection, operation_id: str
) -> ledger_store.OperationRow | None:
    row = conn.execute(
        f"SELECT {OPERATION_COLUMNS} FROM ag_operations WHERE operation_id = %s",
        (operation_id,),
    ).fetchone()
    return ledger_store.OperationRow(*row) if row is not None else None


def lock_operation(conn: psycopg.Connection, operation_id: str) -> ledger_store.OperationRow | None:
    """Lock one operation row; ``None`` when it does not exist."""
    row = conn.execute(
        f"SELECT {OPERATION_COLUMNS} FROM ag_operations WHERE operation_id = %s FOR UPDATE",
        (operation_id,),
    ).fetchone()
    return ledger_store.OperationRow(*row) if row is not None else None


def lock_lease(conn: psycopg.Connection, operation_id: str) -> tuple[str, int, datetime] | None:
    """Lock one lease row; ``None`` when the operation has never been leased."""
    row = conn.execute(
        "SELECT owner_token, fencing_version, lease_expires_at "
        "FROM ag_execution_leases WHERE operation_id = %s FOR UPDATE",
        (operation_id,),
    ).fetchone()
    return (row[0], row[1], _utc(row[2])) if row is not None else None


def fetch_path(conn: psycopg.Connection, grant_id: str) -> list[ledger_store.GrantRow]:
    return ledger_store.load_path(conn, grant_id)


def fetch_event_nodes(conn: psycopg.Connection, operation_id: str) -> list[LedgerEvent]:
    """All ledger events of one operation, RESERVE first, nodes root-to-leaf."""
    events: list[LedgerEvent] = []
    rows = conn.execute(
        "SELECT event_id, phase, seq FROM ag_ledger_events "
        "WHERE operation_id = %s ORDER BY seq ASC",
        (operation_id,),
    ).fetchall()
    for event_id, phase, seq in rows:
        nodes = conn.execute(
            "SELECT position, grant_id, amount_reserved_delta, amount_settled_delta, "
            "calls_reserved_delta, calls_settled_delta FROM ag_ledger_event_nodes "
            "WHERE event_id = %s ORDER BY position ASC",
            (event_id,),
        ).fetchall()
        events.append(
            LedgerEvent(
                phase=phase,
                seq=seq,
                nodes=tuple(EventNodeDelta(*node) for node in nodes),
            )
        )
    return events


def fetch_lease(conn: psycopg.Connection, operation_id: str) -> tuple[str, int, datetime] | None:
    row = conn.execute(
        "SELECT owner_token, fencing_version, lease_expires_at "
        "FROM ag_execution_leases WHERE operation_id = %s",
        (operation_id,),
    ).fetchone()
    return (row[0], row[1], _utc(row[2])) if row is not None else None


def fetch_outbox(conn: psycopg.Connection, operation_id: str) -> dict | None:
    row = conn.execute(
        "SELECT operation_id, receipt_id, status, amount_fen, receipt_status, "
        "receipt_jws, created_at, ledger_changes_json, result_bytes "
        "FROM ag_receipt_outbox WHERE operation_id = %s",
        (operation_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "operation_id": row[0],
        "receipt_id": row[1],
        "status": row[2],
        "amount_fen": row[3],
        "receipt_status": row[4],
        "receipt_jws": row[5],
        "created_at": _utc(row[6]),
        "ledger_changes_json": bytes(row[7]),
        "result_bytes": bytes(row[8]),
    }


def fetch_review_flag(conn: psycopg.Connection, operation_id: str) -> dict | None:
    row = conn.execute(
        "SELECT operation_id, reason, detail, flagged_at "
        "FROM ag_operation_review_flags WHERE operation_id = %s",
        (operation_id,),
    ).fetchone()
    if row is None:
        return None
    detail = row[2]
    return {
        "operation_id": row[0],
        "reason": row[1],
        "detail": detail if isinstance(detail, dict) else json.loads(detail),
        "flagged_at": _utc(row[3]),
    }


def is_quarantined(conn: psycopg.Connection, operation_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM ag_operation_review_flags WHERE operation_id = %s", (operation_id,)
    ).fetchone()
    return row is not None


# ------------------------------------------------------------------- lease


def claim_lease(
    conn: psycopg.Connection,
    *,
    operation_id: str,
    owner_token: str,
    lease_ttl_seconds: int,
) -> ClaimResult:
    """Acquire (or take over) the execution lease; caller holds the path locks.

    Claim rules per state (docs/security-model.md 5):

    * ``RESERVED`` -> lease plus ``EXECUTING`` in this same transaction;
    * an expired ``EXECUTING`` lease is taken over with a new fencing version
      and the status is left alone so the worker reconciles first;
    * ``UNKNOWN`` keeps ``UNKNOWN``;
    * a live lease held by somebody else, a terminal status or a quarantined
      operation refuses the claim and changes nothing.
    """
    operation = lock_operation(conn, operation_id)
    if operation is None:
        raise ExecutionError(ExecutionErrorCode.OPERATION_NOT_FOUND, "unknown operation_id")
    previous_status = operation.status
    if operation.status in TERMINAL_VALUES:
        raise ExecutionError(
            ExecutionErrorCode.ILLEGAL_TRANSITION,
            f"operation already terminal: {operation.status}",
        )
    if is_quarantined(conn, operation_id):
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            "operation is quarantined and must not be executed",
        )

    if not isinstance(lease_ttl_seconds, int) or isinstance(lease_ttl_seconds, bool):
        raise ValueError("lease_ttl_seconds must be an integer")
    if lease_ttl_seconds < 1 or lease_ttl_seconds > 3600:
        raise ValueError("lease_ttl_seconds out of range")

    row = lock_lease(conn, operation_id)

    if row is not None:
        current_owner, current_version, expires_at = row
        now = ledger_store.db_now_epoch(conn)
        if current_owner != owner_token and now < expires_at.timestamp():
            raise ExecutionError(
                ExecutionErrorCode.LEASE_LOST, "operation is leased by another live owner"
            )
        fencing = current_version + 1
        updated = conn.execute(
            "UPDATE ag_execution_leases SET owner_token = %s, fencing_version = %s, "
            "lease_expires_at = clock_timestamp() + make_interval(secs => %s), "
            "acquired_at = clock_timestamp() "
            "WHERE operation_id = %s AND fencing_version = %s "
            "RETURNING owner_token, fencing_version, lease_expires_at",
            (owner_token, fencing, lease_ttl_seconds, operation_id, current_version),
        ).fetchone()
        if updated is None:
            raise ExecutionError(ExecutionErrorCode.LEASE_LOST, "lease moved while claiming")
    else:
        fencing = 1
        updated = conn.execute(
            "INSERT INTO ag_execution_leases "
            "(operation_id, owner_token, fencing_version, lease_expires_at) "
            "VALUES (%s, %s, %s, clock_timestamp() + make_interval(secs => %s)) "
            "RETURNING owner_token, fencing_version, lease_expires_at",
            (operation_id, owner_token, fencing, lease_ttl_seconds),
        ).fetchone()

    if operation.status == OperationStatus.RESERVED.value:
        changed = conn.execute(
            "UPDATE ag_operations SET status = %s WHERE operation_id = %s AND status = %s "
            "RETURNING " + OPERATION_COLUMNS,
            (OperationStatus.EXECUTING.value, operation_id, OperationStatus.RESERVED.value),
        ).fetchone()
        if changed is None:
            raise ExecutionError(
                ExecutionErrorCode.ILLEGAL_TRANSITION, "operation left RESERVED while claiming"
            )
        operation = ledger_store.OperationRow(*changed)

    lease = LeaseGrant(
        operation_id=operation_id,
        owner_token=updated[0],
        fencing_version=updated[1],
        expires_at=_utc(updated[2]),
    )
    return ClaimResult(operation=operation, lease=lease, previous_status=previous_status)


# ------------------------------------------------------------- transitions


def transition_status(
    conn: psycopg.Connection,
    *,
    operation_id: str,
    from_status: str,
    to_status: str,
) -> ledger_store.OperationRow:
    """Conditionally move the status; a refused move is ``ILLEGAL_TRANSITION``."""
    changed = conn.execute(
        "UPDATE ag_operations SET status = %s WHERE operation_id = %s AND status = %s "
        "RETURNING " + OPERATION_COLUMNS,
        (to_status, operation_id, from_status),
    ).fetchone()
    if changed is None:
        raise ExecutionError(
            ExecutionErrorCode.ILLEGAL_TRANSITION,
            f"cannot move {operation_id} from {from_status} to {to_status}",
        )
    return ledger_store.OperationRow(*changed)


def assert_terminal_write_allowed(
    conn: psycopg.Connection,
    *,
    operation_id: str,
    owner_token: str,
    fencing_version: int,
) -> ledger_store.OperationRow:
    """The four terminal conditions, evaluated after the row locks are held.

    owner token, fencing version, a legal (non-terminal) state and an unexpired
    lease at the *database* clock after locks. An expired lease is refused even
    when nobody took over.
    """
    operation = lock_operation(conn, operation_id)
    if operation is None:
        raise ExecutionError(ExecutionErrorCode.OPERATION_NOT_FOUND, "unknown operation_id")
    if operation.status in TERMINAL_VALUES:
        raise ExecutionError(
            ExecutionErrorCode.ILLEGAL_TRANSITION,
            f"operation already terminal: {operation.status}",
        )
    lease = lock_lease(conn, operation_id)
    if lease is None:
        raise ExecutionError(ExecutionErrorCode.LEASE_LOST, "no lease held")
    held_owner, held_version, expires_at = lease
    now = ledger_store.db_now_epoch(conn)
    if held_owner != owner_token or held_version != fencing_version:
        raise ExecutionError(
            ExecutionErrorCode.LEASE_LOST, "owner token or fencing version is stale"
        )
    if now >= expires_at.timestamp():
        raise ExecutionError(
            ExecutionErrorCode.LEASE_LOST, "lease expired before the terminal write"
        )
    return operation


# ------------------------------------------------------------- terminal tx


def terminal_node_deltas(
    grants: list[ledger_store.GrantRow],
    action: TerminalAction,
    amount_fen: int,
    calls: int,
) -> tuple[EventNodeDelta, ...]:
    """SETTLE moves reserved -> settled; RELEASE only drops the reservation."""
    deltas: list[EventNodeDelta] = []
    for position, grant in enumerate(grants):
        if action is TerminalAction.SETTLE:
            deltas.append(
                EventNodeDelta(
                    position=position,
                    grant_id=grant.grant_id,
                    amount_reserved_delta=-amount_fen,
                    amount_settled_delta=amount_fen,
                    calls_reserved_delta=-calls,
                    calls_settled_delta=calls,
                )
            )
        else:
            deltas.append(
                EventNodeDelta(
                    position=position,
                    grant_id=grant.grant_id,
                    amount_reserved_delta=-amount_fen,
                    amount_settled_delta=0,
                    calls_reserved_delta=-calls,
                    calls_settled_delta=0,
                )
            )
    return tuple(deltas)


def apply_terminal_counters(conn: psycopg.Connection, nodes: tuple[EventNodeDelta, ...]) -> None:
    """Apply the bounded negative deltas to every applicable ancestor."""
    for node in nodes:
        for name, value in (
            ("amount_reserved_delta", node.amount_reserved_delta),
            ("amount_settled_delta", node.amount_settled_delta),
            ("calls_reserved_delta", node.calls_reserved_delta),
            ("calls_settled_delta", node.calls_settled_delta),
        ):
            if abs(value) > MAX_SAFE_INT:
                raise ExecutionError(ExecutionErrorCode.ILLEGAL_TRANSITION, f"{name} out of range")
        conn.execute(
            "UPDATE ag_grants SET "
            "amount_reserved = amount_reserved + %s, "
            "amount_settled  = amount_settled  + %s, "
            "calls_reserved  = calls_reserved  + %s, "
            "calls_settled   = calls_settled   + %s "
            "WHERE grant_id = %s",
            (
                node.amount_reserved_delta,
                node.amount_settled_delta,
                node.calls_reserved_delta,
                node.calls_settled_delta,
                node.grant_id,
            ),
        )


def insert_terminal_event(
    conn: psycopg.Connection,
    *,
    operation_id: str,
    action: TerminalAction,
    nodes: tuple[EventNodeDelta, ...],
) -> int:
    """Insert the single terminal event (seq=1); a second one is refused."""
    try:
        event_id = conn.execute(
            "INSERT INTO ag_ledger_events (operation_id, phase, seq) VALUES (%s, %s, 1) "
            "RETURNING event_id",
            (operation_id, action.value),
        ).fetchone()[0]
    except psycopg.errors.UniqueViolation as exc:
        raise ExecutionError(
            ExecutionErrorCode.ILLEGAL_TRANSITION, "terminal event already recorded"
        ) from exc
    except psycopg.errors.CheckViolation as exc:
        raise ExecutionError(
            ExecutionErrorCode.ILLEGAL_TRANSITION, "terminal event violates phase/seq binding"
        ) from exc
    for node in nodes:
        conn.execute(
            "INSERT INTO ag_ledger_event_nodes "
            "(event_id, position, grant_id, amount_reserved_delta, amount_settled_delta, "
            " calls_reserved_delta, calls_settled_delta) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                event_id,
                node.position,
                node.grant_id,
                node.amount_reserved_delta,
                node.amount_settled_delta,
                node.calls_reserved_delta,
                node.calls_settled_delta,
            ),
        )
    return event_id


def insert_pending_receipt(conn: psycopg.Connection, material: PendingReceipt) -> None:
    """Persist the immutable pending-signature material of one operation."""
    try:
        conn.execute(
            "INSERT INTO ag_receipt_outbox "
            "(operation_id, receipt_id, profile, tenant_id, task_id, root_grant_id, "
            " grant_id, tool_id, tool_version, status, amount_fen, ledger_changes_json, "
            " result_bytes, token_digest, proof_digest, intent_digest, evidence_ref, "
            " receipt_status, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s)",
            (
                material.operation_id,
                material.receipt_id,
                material.profile,
                material.tenant_id,
                material.task_id,
                material.root_grant_id,
                material.grant_id,
                material.tool_id,
                material.tool_version,
                material.status.value,
                material.amount_fen,
                material.ledger_changes_json,
                material.result_bytes,
                material.token_digest,
                material.proof_digest,
                material.intent_digest,
                material.evidence_ref,
                material.created_at,
            ),
        )
    except psycopg.errors.UniqueViolation as exc:
        raise ExecutionError(
            ExecutionErrorCode.ILLEGAL_TRANSITION, "receipt material already recorded"
        ) from exc


def flag_operation(
    conn: psycopg.Connection,
    *,
    operation_id: str,
    reason: str,
    detail: dict,
) -> None:
    """Quarantine an operation whose persisted material is insufficient."""
    conn.execute(
        "INSERT INTO ag_operation_review_flags (operation_id, reason, detail) "
        "VALUES (%s, %s, %s) "
        "ON CONFLICT (operation_id) DO UPDATE SET reason = EXCLUDED.reason, "
        "detail = EXCLUDED.detail, flagged_at = clock_timestamp()",
        (operation_id, reason, json.dumps(detail, ensure_ascii=False, sort_keys=True)),
    )


def lease_deadline(ttl_seconds: int, *, now: datetime | None = None) -> datetime:
    """Helper for tests/tools that need to reason about expiry windows."""
    base = now or datetime.now(tz=timezone.utc)
    return base + timedelta(seconds=ttl_seconds)
