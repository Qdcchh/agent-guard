"""SQL access layer for the A1 execution ledger.

Every row type here maps one-to-one onto the tables created by
``migrations/001_init.sql``. Locking helpers always take the unified order
required by ``docs/security-model.md`` section 4: principal/key rows first
(sorted), then the task row, then grant nodes root-to-leaf. Issuance,
revocation, accept and identity deactivation share this order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import psycopg

from agent_guard.contracts.ledger import ErrorCode, LedgerError

#: Column slices kept in sync with migrations/001_init.sql.
GRANT_COLUMNS = (
    "grant_id, parent_grant_id, root_grant_id, tenant_id, task_id, subject, "
    "holder_client_id, holder_kid, depth, not_before, expires_at, revoked, "
    "revoked_at, amount_limit, call_limit, amount_reserved, amount_settled, "
    "calls_reserved, calls_settled, created_at"
)


@dataclass(frozen=True)
class TaskRow:
    tenant_id: str
    task_id: str
    root_grant_id: str
    created_at: datetime


@dataclass(frozen=True)
class PrincipalRow:
    tenant_id: str
    client_id: str
    kid: str
    active: bool
    created_at: datetime
    deactivated_at: datetime | None


@dataclass(frozen=True)
class GrantRow:
    grant_id: str
    parent_grant_id: str | None
    root_grant_id: str
    tenant_id: str
    task_id: str
    subject: str
    holder_client_id: str
    holder_kid: str
    depth: int
    not_before: datetime
    expires_at: datetime
    revoked: bool
    revoked_at: datetime | None
    amount_limit: int
    call_limit: int
    amount_reserved: int
    amount_settled: int
    calls_reserved: int
    calls_settled: int
    created_at: datetime


@dataclass(frozen=True)
class OperationRow:
    operation_id: str
    tenant_id: str
    task_id: str
    tool_id: str
    idempotency_key: str
    grant_id: str
    holder_client_id: str
    holder_kid: str
    tool_version: str
    canonical_params: bytes
    currency: str
    amount_fen: int
    calls: int
    quote_id: str | None
    quote_version: str | None
    quote_snapshot: bytes | None
    token_digest: str
    proof_digest: str
    intent_digest: str
    evidence_ref: str
    status: str
    accepted_at: datetime


def _grant(row: tuple) -> GrantRow:
    return GrantRow(*row)


def _task(row: tuple) -> TaskRow:
    return TaskRow(*row)


def _principal(row: tuple) -> PrincipalRow:
    return PrincipalRow(*row)


def _operation(row: tuple) -> OperationRow:
    return OperationRow(*row)


def db_now_epoch(conn: psycopg.Connection) -> float:
    """Actual current time as epoch seconds, not the transaction start time."""
    row = conn.execute("SELECT EXTRACT(EPOCH FROM clock_timestamp())").fetchone()
    return float(row[0])


def load_path(conn: psycopg.Connection, grant_id: str) -> list[GrantRow]:
    """Load the immutable root-to-leaf path for ``grant_id`` without locking.

    The database parent chain is authoritative. A missing node, a cycle, a
    chain deeper than root+2 levels or an unreachable root is rejected as
    ``INVALID_CONTEXT``.
    """
    current = _fetch_grant(conn, grant_id)
    if current is None:
        raise LedgerError(ErrorCode.INVALID_CONTEXT, "unknown grant_id")
    path_leaf_to_root = [current]
    seen = {current.grant_id}
    while current.parent_grant_id is not None:
        if len(path_leaf_to_root) > 2:
            raise LedgerError(ErrorCode.INVALID_CONTEXT, "grant chain too deep")
        if current.parent_grant_id in seen:
            raise LedgerError(ErrorCode.INVALID_CONTEXT, "grant path loop")
        parent = _fetch_grant(conn, current.parent_grant_id)
        if parent is None:
            raise LedgerError(ErrorCode.INVALID_CONTEXT, "incomplete grant path")
        seen.add(parent.grant_id)
        path_leaf_to_root.append(parent)
        current = parent
    path_leaf_to_root.reverse()
    return path_leaf_to_root


def _fetch_grant(conn: psycopg.Connection, grant_id: str) -> GrantRow | None:
    row = conn.execute(
        f"SELECT {GRANT_COLUMNS} FROM ag_grants WHERE grant_id = %s", (grant_id,)
    ).fetchone()
    return _grant(row) if row is not None else None


def lock_principals(
    conn: psycopg.Connection, keys: list[tuple[str, str, str]]
) -> dict[tuple[str, str, str], PrincipalRow]:
    """Lock holder key rows in a unified sorted order; missing rows are OK to
    observe here and are rejected later by the freshness checks."""
    if not keys:
        return {}
    ordered = sorted(set(keys))
    rows = conn.execute(
        "SELECT tenant_id, client_id, kid, active, created_at, deactivated_at "
        "FROM ag_principals "
        "WHERE (tenant_id, client_id, kid) IN ("
        "  SELECT * FROM unnest(%s::text[], %s::text[], %s::text[])) "
        "ORDER BY tenant_id, client_id, kid "
        "FOR UPDATE",
        ([k[0] for k in ordered], [k[1] for k in ordered], [k[2] for k in ordered]),
    ).fetchall()
    return {(r[0], r[1], r[2]): _principal(r) for r in rows}


def lock_task(conn: psycopg.Connection, tenant_id: str, task_id: str) -> TaskRow:
    row = conn.execute(
        "SELECT tenant_id, task_id, root_grant_id, created_at "
        "FROM ag_tasks WHERE tenant_id = %s AND task_id = %s "
        "FOR UPDATE",
        (tenant_id, task_id),
    ).fetchone()
    if row is None:
        raise LedgerError(ErrorCode.INVALID_CONTEXT, "unknown task")
    return _task(row)


def lock_grants_root_to_leaf(conn: psycopg.Connection, grant_ids: list[str]) -> list[GrantRow]:
    """Lock path nodes root-first; returns the locked rows in root-to-leaf order."""
    rows = conn.execute(
        f"SELECT {GRANT_COLUMNS} FROM ag_grants "
        "WHERE grant_id = ANY(%s) "
        "ORDER BY depth ASC, grant_id ASC "
        "FOR UPDATE",
        (grant_ids,),
    ).fetchall()
    locked = [_grant(r) for r in rows]
    if len(locked) != len(set(grant_ids)):
        raise LedgerError(ErrorCode.INVALID_CONTEXT, "grant vanished during lock")
    return locked


def fetch_operation_by_business_key(
    conn: psycopg.Connection,
    tenant_id: str,
    task_id: str,
    tool_id: str,
    idempotency_key: str,
) -> OperationRow | None:
    row = conn.execute(
        "SELECT operation_id, tenant_id, task_id, tool_id, idempotency_key, grant_id, "
        "holder_client_id, holder_kid, tool_version, canonical_params, currency, "
        "amount_fen, calls, quote_id, quote_version, quote_snapshot, token_digest, "
        "proof_digest, intent_digest, evidence_ref, status, accepted_at "
        "FROM ag_operations "
        "WHERE tenant_id = %s AND task_id = %s AND tool_id = %s AND idempotency_key = %s",
        (tenant_id, task_id, tool_id, idempotency_key),
    ).fetchone()
    return _operation(row) if row is not None else None


def record_proof(
    conn: psycopg.Connection,
    *,
    holder_kid: str,
    purpose: str,
    endpoint: str,
    proof_jti: str,
    proof_digest: str,
    evidence_ref: str,
) -> None:
    """Register a proof jti; the unique key is the anti-replay boundary.

    ``operation_id`` is linked in the same transaction once the operation is
    known. A unique violation here is always ``REPLAY``, never a generic
    database failure.
    """
    try:
        conn.execute(
            "INSERT INTO ag_proofs "
            "(holder_kid, purpose, endpoint, proof_jti, proof_digest, evidence_ref) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (holder_kid, purpose, endpoint, proof_jti, proof_digest, evidence_ref),
        )
    except psycopg.errors.UniqueViolation as exc:
        raise LedgerError(ErrorCode.REPLAY, "proof jti already used") from exc


def link_proof_to_operation(
    conn: psycopg.Connection,
    *,
    holder_kid: str,
    purpose: str,
    endpoint: str,
    proof_jti: str,
    operation_id: str,
) -> None:
    conn.execute(
        "UPDATE ag_proofs SET operation_id = %s "
        "WHERE holder_kid = %s AND purpose = %s AND endpoint = %s AND proof_jti = %s",
        (operation_id, holder_kid, purpose, endpoint, proof_jti),
    )


def insert_operation(
    conn: psycopg.Connection,
    *,
    operation_id: str,
    tenant_id: str,
    task_id: str,
    tool_id: str,
    idempotency_key: str,
    grant_id: str,
    holder_client_id: str,
    holder_kid: str,
    tool_version: str,
    canonical_params: bytes,
    currency: str,
    amount_fen: int,
    calls: int,
    quote_id: str | None,
    quote_version: str | None,
    quote_snapshot: bytes | None,
    token_digest: str,
    proof_digest: str,
    intent_digest: str,
    evidence_ref: str,
) -> OperationRow:
    try:
        row = conn.execute(
            "INSERT INTO ag_operations "
            "(operation_id, tenant_id, task_id, tool_id, idempotency_key, grant_id, "
            " holder_client_id, holder_kid, tool_version, canonical_params, currency, "
            " amount_fen, calls, quote_id, quote_version, quote_snapshot, "
            " token_digest, proof_digest, intent_digest, evidence_ref) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "RETURNING operation_id, tenant_id, task_id, tool_id, idempotency_key, "
            "grant_id, holder_client_id, holder_kid, tool_version, canonical_params, "
            "currency, amount_fen, calls, quote_id, quote_version, quote_snapshot, "
            "token_digest, proof_digest, intent_digest, evidence_ref, status, accepted_at",
            (
                operation_id,
                tenant_id,
                task_id,
                tool_id,
                idempotency_key,
                grant_id,
                holder_client_id,
                holder_kid,
                tool_version,
                canonical_params,
                currency,
                amount_fen,
                calls,
                quote_id,
                quote_version,
                quote_snapshot,
                token_digest,
                proof_digest,
                intent_digest,
                evidence_ref,
            ),
        ).fetchone()
    except psycopg.errors.UniqueViolation as exc:
        raise LedgerError(
            ErrorCode.IDEMPOTENCY_CONFLICT, "operation business key already used"
        ) from exc
    return _operation(row)


def apply_reservation(conn: psycopg.Connection, grant_id: str, amount_fen: int, calls: int) -> None:
    """Increase reservation counters; pre-checked in safe form, CHECKs guard the rest."""
    conn.execute(
        "UPDATE ag_grants SET amount_reserved = amount_reserved + %s, "
        "calls_reserved = calls_reserved + %s WHERE grant_id = %s",
        (amount_fen, calls, grant_id),
    )


def insert_reserve_event(
    conn: psycopg.Connection,
    *,
    operation_id: str,
    seq: int,
    nodes: list[tuple[int, str, int, int]],
) -> None:
    """Insert one RESERVE event with root-to-leaf node deltas.

    ``nodes`` items are ``(position, grant_id, amount_delta, calls_delta)`` in
    root-first order. Retries must never call this a second time.
    """
    event_id = conn.execute(
        "INSERT INTO ag_ledger_events (operation_id, phase, seq) "
        "VALUES (%s, 'RESERVE', %s) RETURNING event_id",
        (operation_id, seq),
    ).fetchone()[0]
    for position, grant_id, amount_delta, calls_delta in nodes:
        conn.execute(
            "INSERT INTO ag_ledger_event_nodes "
            "(event_id, position, grant_id, amount_reserved_delta, "
            " amount_settled_delta, calls_reserved_delta, calls_settled_delta) "
            "VALUES (%s, %s, %s, %s, 0, %s, 0)",
            (event_id, position, grant_id, amount_delta, calls_delta),
        )
