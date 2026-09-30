"""Atomic accept transaction for the A1 execution ledger.

``ExecutionLedger.accept`` is the linearization point for one tool invocation
reservation. It is a synchronous, in-process interface over a real PostgreSQL
transaction; there is no HTTP entry point and no "already authorized JSON"
path. A1 performs no downstream effects.

Transaction order (``docs/security-model.md`` section 4 and
``tasks/A1-ledger.md`` section 4.1):

1. pure format validation of the trusted context and cost;
2. read the immutable grant path from the database (authoritative) and check
   it belongs to the unique root of the same tenant/task;
3. lock holder key rows (sorted), then the task row, then grant nodes
   root-to-leaf — the same order used by issuance/revocation/deactivation;
4. with the locks held, re-check key state, holder binding, every node's
   validity/revocation, token expiry and proof freshness using the database's
   actual current time (``clock_timestamp()``), never the transaction start;
5. register the proof jti under the unique scope
   ``(holder_kid, purpose, endpoint, proof_jti)`` — a hit is ``REPLAY``;
6. look up the business key ``(tenant_id, task_id, tool_id, idempotency_key)``:
   same intent returns the original operation (``EXISTING``, original cost,
   no second reservation) and links the new proof; different intent rejects;
7. first accept checks amount/call budgets at the root and every applicable
   node, then atomically records the reservation, the immutable operation with
   first-accept evidence and exactly one ``RESERVE`` ledger event.

Any failure rolls back the whole transaction: no partial proof, budget or
operation state is left behind, and a rejected request does not permanently
consume its proof jti.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timezone

import psycopg

from agent_guard.contracts.ledger import (
    PROOF_MAX_FUTURE_SKEW_S,
    AcceptDisposition,
    AcceptResult,
    ErrorCode,
    LedgerError,
    TrustedCost,
    VerifiedInvocation,
)
from agent_guard.ledger import store
from agent_guard.ledger.validation import validate_cost, validate_invocation

#: Bounded retries for deadlock/serialization failures only; never an infinite loop.
MAX_TX_RETRIES = 3

#: Upper bounds for connect/lock waiting and statement execution (fail closed).
DEFAULT_CONNECT_TIMEOUT_S = 5
DEFAULT_LOCK_TIMEOUT_MS = 10_000
DEFAULT_STATEMENT_TIMEOUT_MS = 15_000

#: Accepted configuration ranges; 0 is rejected because PostgreSQL treats 0 as
#: "no timeout", which would silently unbound the wait.
CONFIG_BOUNDS: dict[str, tuple[int, int]] = {
    "connect_timeout_s": (1, 60),
    "lock_timeout_ms": (1, 600_000),
    "statement_timeout_ms": (1, 600_000),
    "max_retries": (1, 10),
}

_PROOF_UNIQUE_CONSTRAINT = "ag_proofs_pkey"
_OPERATION_UNIQUE_CONSTRAINT = "ag_operations_business_key"
_TASK_UNIQUE_CONSTRAINT = "ag_tasks_pkey"


def _utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def _bounded(name: str, value: object) -> int:
    """Validate a timeout/retry setting: bounded positive int, never 0/bool."""
    lower, upper = CONFIG_BOUNDS[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer (bool/float rejected)")
    if value < lower or value > upper:
        raise ValueError(f"{name} must be within [{lower}, {upper}], got {value}")
    return value


def _cost_from_row(row: store.OperationRow) -> TrustedCost:
    return TrustedCost(
        amount_fen=row.amount_fen,
        calls=row.calls,
        currency=row.currency,
        quote_id=row.quote_id,
        quote_version=row.quote_version,
        quote_snapshot=row.quote_snapshot,
    )


class ExecutionLedger:
    """Trusted in-process accept interface over a real PostgreSQL state store."""

    def __init__(
        self,
        dsn: str,
        *,
        connect_timeout_s: int = DEFAULT_CONNECT_TIMEOUT_S,
        lock_timeout_ms: int = DEFAULT_LOCK_TIMEOUT_MS,
        statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
        max_retries: int = MAX_TX_RETRIES,
        connector: Callable[..., psycopg.Connection] | None = None,
    ) -> None:
        self._dsn = dsn
        self._connect_timeout_s = _bounded("connect_timeout_s", connect_timeout_s)
        self._lock_timeout_ms = _bounded("lock_timeout_ms", lock_timeout_ms)
        self._statement_timeout_ms = _bounded("statement_timeout_ms", statement_timeout_ms)
        self._max_retries = _bounded("max_retries", max_retries)
        # injectable connection factory so tests can double the connection layer
        self._connector: Callable[..., psycopg.Connection] = (
            connector if connector is not None else psycopg.connect
        )

    # ------------------------------------------------------------------ public

    def accept(self, verified: VerifiedInvocation, cost: TrustedCost) -> AcceptResult:
        """Reserve budget for one invocation, exactly once per business key."""
        validate_invocation(verified)
        validate_cost(cost)

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                with self._connect() as conn:
                    with conn.transaction():
                        return self._accept_tx(conn, verified, cost)
            except (psycopg.errors.DeadlockDetected, psycopg.errors.SerializationFailure) as exc:
                last_error = exc
                if attempt == self._max_retries:
                    break
                continue
            except psycopg.errors.OperationalError as exc:
                raise LedgerError(
                    ErrorCode.TRUSTED_STATE_UNAVAILABLE, "database unavailable"
                ) from exc
            except psycopg.errors.UniqueViolation as exc:
                raise self._map_unique_violation(exc) from exc
        raise LedgerError(
            ErrorCode.TRUSTED_STATE_UNAVAILABLE, "deadlock retries exhausted"
        ) from last_error

    # ------------------------------------------------------------- transaction

    def _connect(self) -> psycopg.Connection:
        conn = self._connector(self._dsn, autocommit=False, connect_timeout=self._connect_timeout_s)
        try:
            # set_config() accepts bind parameters; plain SET does not.
            conn.execute(
                "SELECT set_config('lock_timeout', %s, false), "
                "set_config('statement_timeout', %s, false)",
                (f"{self._lock_timeout_ms}ms", f"{self._statement_timeout_ms}ms"),
            )
        except BaseException:
            conn.close()
            raise
        return conn

    def _accept_tx(
        self, conn: psycopg.Connection, verified: VerifiedInvocation, cost: TrustedCost
    ) -> AcceptResult:
        # (1) trusted path discovery — database parent chain is authoritative.
        path = store.load_path(conn, verified.grant_id)
        self._check_path(path, verified)

        # (2) unified lock order: principals, task, grants root-to-leaf.
        keys = [(g.tenant_id, g.holder_client_id, g.holder_kid) for g in path]
        principals = store.lock_principals(conn, keys)
        task = store.lock_task(conn, verified.tenant_id, verified.task_id)
        if task.root_grant_id != path[0].grant_id or task.root_grant_id != verified.root_id:
            raise LedgerError(ErrorCode.INVALID_CONTEXT, "task root mismatch")
        grants = store.lock_grants_root_to_leaf(conn, [g.grant_id for g in path])
        self._check_path(grants, verified)

        # (3) linearization point: re-check state at the actual current time.
        now = store.db_now_epoch(conn)
        self._check_freshness(grants, principals, verified, now)

        # (4) proof anti-replay registration before any idempotent shortcut.
        store.record_proof(
            conn,
            holder_kid=verified.holder_kid,
            purpose=verified.purpose,
            endpoint=verified.endpoint,
            proof_jti=verified.proof_jti,
            proof_digest=verified.proof_digest,
            evidence_ref=verified.evidence_ref,
        )

        # (5) business key: EXISTING never re-prices, re-reserves or re-counts.
        existing = store.fetch_operation_by_business_key(
            conn,
            verified.tenant_id,
            verified.task_id,
            verified.tool_id,
            verified.idempotency_key,
        )
        if existing is not None:
            self._check_intent(existing, verified)
            store.link_proof_to_operation(
                conn,
                holder_kid=verified.holder_kid,
                purpose=verified.purpose,
                endpoint=verified.endpoint,
                proof_jti=verified.proof_jti,
                operation_id=existing.operation_id,
            )
            return AcceptResult(
                operation_id=existing.operation_id,
                grant_id=existing.grant_id,
                root_id=grants[0].grant_id,
                status=existing.status,
                disposition=AcceptDisposition.EXISTING,
                cost=_cost_from_row(existing),
                accepted_at=_utc(existing.accepted_at),
            )

        # (6) first accept: budget at root and every applicable node.
        self._check_budget(grants, cost)

        operation_id = uuid.uuid4().hex
        inserted = store.insert_operation(
            conn,
            operation_id=operation_id,
            tenant_id=verified.tenant_id,
            task_id=verified.task_id,
            tool_id=verified.tool_id,
            idempotency_key=verified.idempotency_key,
            grant_id=verified.grant_id,
            holder_client_id=verified.holder_client_id,
            holder_kid=verified.holder_kid,
            tool_version=verified.tool_version,
            canonical_params=verified.canonical_params,
            currency=cost.currency,
            amount_fen=cost.amount_fen,
            calls=cost.calls,
            quote_id=cost.quote_id,
            quote_version=cost.quote_version,
            quote_snapshot=cost.quote_snapshot,
            token_digest=verified.token_digest,
            proof_digest=verified.proof_digest,
            intent_digest=verified.intent_digest,
            evidence_ref=verified.evidence_ref,
        )
        for grant in grants:
            store.apply_reservation(conn, grant.grant_id, cost.amount_fen, cost.calls)
        store.insert_reserve_event(
            conn,
            operation_id=operation_id,
            seq=0,
            nodes=[
                (position, grant.grant_id, cost.amount_fen, cost.calls)
                for position, grant in enumerate(grants)
            ],
        )
        store.link_proof_to_operation(
            conn,
            holder_kid=verified.holder_kid,
            purpose=verified.purpose,
            endpoint=verified.endpoint,
            proof_jti=verified.proof_jti,
            operation_id=operation_id,
        )
        return AcceptResult(
            operation_id=operation_id,
            grant_id=verified.grant_id,
            root_id=grants[0].grant_id,
            status=inserted.status,
            disposition=AcceptDisposition.CREATED,
            cost=cost,
            accepted_at=_utc(inserted.accepted_at),
        )

    # ------------------------------------------------------------------ checks

    def _check_path(self, path: list[store.GrantRow], verified: VerifiedInvocation) -> None:
        root = path[0]
        leaf = path[-1]
        if root.parent_grant_id is not None or root.depth != 0:
            raise LedgerError(ErrorCode.INVALID_CONTEXT, "path does not start at a root")
        if root.grant_id != verified.root_id:
            raise LedgerError(ErrorCode.INVALID_CONTEXT, "forged root_id")
        if leaf.grant_id != verified.grant_id:
            raise LedgerError(ErrorCode.INVALID_CONTEXT, "path does not end at grant_id")
        if len(path) > 3:
            raise LedgerError(ErrorCode.INVALID_CONTEXT, "grant chain too deep")
        for position, grant in enumerate(path):
            if grant.tenant_id != verified.tenant_id or grant.task_id != verified.task_id:
                raise LedgerError(ErrorCode.INVALID_CONTEXT, "tenant/task mismatch on path")
            if grant.root_grant_id != root.grant_id:
                raise LedgerError(ErrorCode.INVALID_CONTEXT, "path root mismatch")
            if grant.subject != verified.subject:
                raise LedgerError(
                    ErrorCode.INVALID_CONTEXT,
                    f"subject mismatch on path: {grant.grant_id}",
                )
            if grant.depth != position:
                raise LedgerError(ErrorCode.INVALID_CONTEXT, "inconsistent grant depth")
            if position > 0 and grant.parent_grant_id != path[position - 1].grant_id:
                raise LedgerError(ErrorCode.INVALID_CONTEXT, "broken parent chain")
        db_ancestors = tuple(g.grant_id for g in path[:-1])
        if verified.ancestor_ids is not None and verified.ancestor_ids != db_ancestors:
            raise LedgerError(ErrorCode.INVALID_CONTEXT, "ancestor_ids not the database path")

    def _check_freshness(
        self,
        grants: list[store.GrantRow],
        principals: dict[tuple[str, str, str], store.PrincipalRow],
        verified: VerifiedInvocation,
        now: float,
    ) -> None:
        for grant in grants:
            key = (grant.tenant_id, grant.holder_client_id, grant.holder_kid)
            principal = principals.get(key)
            if principal is None:
                raise LedgerError(ErrorCode.HOLDER_MISMATCH, "holder key not registered")
            if not principal.active:
                raise LedgerError(ErrorCode.HOLDER_MISMATCH, "holder key deactivated")

        leaf = grants[-1]
        if (
            leaf.holder_client_id != verified.holder_client_id
            or leaf.holder_kid != verified.holder_kid
        ):
            raise LedgerError(ErrorCode.HOLDER_MISMATCH, "holder does not match grant")

        for grant in grants:
            if grant.revoked:
                raise LedgerError(ErrorCode.REVOKED, f"grant revoked: {grant.grant_id}")
            if now < _utc(grant.not_before).timestamp():
                raise LedgerError(ErrorCode.EXPIRED, f"grant not yet effective: {grant.grant_id}")
            if now >= _utc(grant.expires_at).timestamp():
                raise LedgerError(ErrorCode.EXPIRED, f"grant expired: {grant.grant_id}")

        if now >= verified.token_exp:
            raise LedgerError(ErrorCode.EXPIRED, "token expired")
        if verified.proof_iat > now + PROOF_MAX_FUTURE_SKEW_S:
            raise LedgerError(ErrorCode.STALE_REQUEST, "proof_iat too far in the future")
        if now >= verified.proof_exp:
            raise LedgerError(ErrorCode.STALE_REQUEST, "proof expired")

    def _check_intent(self, existing: store.OperationRow, verified: VerifiedInvocation) -> None:
        """Idempotency binds the raw intent fields, not just the intent digest.

        ``purpose``, ``proof_jti`` and signature timestamps are not part of the
        business intent.
        """
        same = (
            existing.grant_id == verified.grant_id
            and existing.holder_client_id == verified.holder_client_id
            and existing.holder_kid == verified.holder_kid
            and existing.tool_id == verified.tool_id
            and existing.tool_version == verified.tool_version
            and existing.canonical_params == verified.canonical_params
        )
        if not same:
            raise LedgerError(
                ErrorCode.IDEMPOTENCY_CONFLICT, "business key reused with a different intent"
            )

    def _check_budget(self, grants: list[store.GrantRow], cost: TrustedCost) -> None:
        for grant in grants:
            if grant.amount_settled > grant.amount_limit:
                raise LedgerError(ErrorCode.BUDGET_EXCEEDED, "settled exceeds limit")
            if cost.amount_fen > grant.amount_limit - grant.amount_settled:
                raise LedgerError(ErrorCode.BUDGET_EXCEEDED, "amount limit exceeded")
            if grant.amount_reserved > grant.amount_limit - grant.amount_settled - cost.amount_fen:
                raise LedgerError(ErrorCode.BUDGET_EXCEEDED, "amount limit exceeded")
        for grant in grants:
            if grant.calls_settled > grant.call_limit:
                raise LedgerError(ErrorCode.CALL_LIMIT_EXCEEDED, "settled calls exceed limit")
            if cost.calls > grant.call_limit - grant.calls_settled:
                raise LedgerError(ErrorCode.CALL_LIMIT_EXCEEDED, "call limit exceeded")
            if grant.calls_reserved > grant.call_limit - grant.calls_settled - cost.calls:
                raise LedgerError(ErrorCode.CALL_LIMIT_EXCEEDED, "call limit exceeded")

    @staticmethod
    def _map_unique_violation(exc: psycopg.errors.UniqueViolation) -> LedgerError:
        constraint = (exc.diag.constraint_name if exc.diag is not None else "") or ""
        if constraint == _PROOF_UNIQUE_CONSTRAINT:
            return LedgerError(ErrorCode.REPLAY, "proof jti already used")
        if constraint == _OPERATION_UNIQUE_CONSTRAINT:
            return LedgerError(ErrorCode.IDEMPOTENCY_CONFLICT, "business key already used")
        if constraint == _TASK_UNIQUE_CONSTRAINT:
            return LedgerError(ErrorCode.INVALID_CONTEXT, "task root already exists")
        return LedgerError(ErrorCode.IDEMPOTENCY_CONFLICT, f"unique violation: {constraint}")


def open_ledger(dsn: str, **kwargs: object) -> ExecutionLedger:
    """Factory kept for callers/tests that only need default settings."""
    return ExecutionLedger(dsn, **kwargs)  # type: ignore[arg-type]
