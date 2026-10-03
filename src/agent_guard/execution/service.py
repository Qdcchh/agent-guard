"""A2.1 execution service: accept, execute, settle/release, UNKNOWN recovery.

One trusted in-process service over a real PostgreSQL gateway ledger and an
independent downstream transaction domain. It has no HTTP entry point, no
"already verified JSON" path and no production authentication/crypto double.

Accept flow (``docs/security-model.md`` 4, checkpoint-1 obligation C2 and
``A2-CKPT1-OBL01/02``):

1. strict tool/parameter parsing and the *static* trusted authorization checks
   (snapshot binding, full-chain narrowing bound to the immutable database
   parent chain, scope, trusted resource sets) — never requires a current quote
   to exist;
2. a read-only business-key candidate lookup against ``ag_operations``;
3. a candidate hit is only usable when the **complete** persisted accept facts
   are intact (tool, version, params, cost identity, currency, quote identity,
   full snapshot, first-accept evidence and the whole RESERVE path/deltas); a
   gap is quarantined into the sidecar and never executed or re-priced. An
   intact candidate still goes through ``ExecutionLedger.accept`` for the
   lock-after dynamic checks, proof anti-replay and full intent comparison;
4. only a brand new intent resolves the current trusted quote; *any* resource
   or quote resolution failure safely re-checks the candidate.

Execution/recovery rules (``docs/security-model.md`` 5/6):

* every internal entry (run/reconcile/claim/candidate) re-verifies the complete
  persisted accept facts and quarantines automatically — nothing depends on a
  manual helper being called first;
* the lease claim happens in its own gateway transaction with the global lock
  order ``task -> grants root-to-leaf -> operation -> lease``; no lock is held
  across the downstream call and no path acquires locks in the reverse order;
* an expired ``EXECUTING`` lease is taken over and reconciled with the
  downstream first; ``UNKNOWN`` claims keep ``UNKNOWN``;
* the downstream outcome is validated as a *typed* record bound to this
  operation's stable key, tool, intent, complete quote, currency, amount and
  per-tool effect/result shape. Only a same-key persisted terminal refusal
  produces ``FAILED``/``RELEASE``; anything inconsistent keeps ``UNKNOWN`` and
  the reserved budget.
* the terminal gateway transaction atomically applies every ancestor counter
  change, the single mutually exclusive terminal event and the pending-signature
  outbox material.

Diagnostics never echo raw exceptions, DSNs, secrets or request parameters:
callers only ever see a stable error code plus a class name.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

import psycopg

from agent_guard.contracts.execution import (
    DownstreamOutcome,
    DownstreamPort,
    ExecutionError,
    ExecutionErrorCode,
    LeaseGrant,
    OperationStatus,
    TerminalAction,
    ToolId,
    TrustedPermissionSnapshot,
    TrustedQuoteSnapshot,
)
from agent_guard.contracts.ledger import (
    CURRENCY,
    MAX_SAFE_INT,
    AcceptResult,
    TrustedCost,
    VerifiedInvocation,
)
from agent_guard.execution import receipts
from agent_guard.execution import store as exec_store
from agent_guard.execution.store import ClaimResult
from agent_guard.ledger import store as ledger_store
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.tools import policy, results
from agent_guard.tools.catalog import (
    TrustedCatalog,
    snapshot_from_bytes,
    snapshot_to_bytes,
)
from agent_guard.tools.params import (
    OrderCreateParams,
    parse_tool_id,
    parse_tool_params,
    parse_tool_version,
)

DEFAULT_LEASE_TTL_S = 30
DEFAULT_CONNECT_TIMEOUT_S = 5
DEFAULT_LOCK_TIMEOUT_MS = 10_000
DEFAULT_STATEMENT_TIMEOUT_MS = 15_000

_TERMINAL_FOR_ACTION = {
    TerminalAction.SETTLE: OperationStatus.SUCCEEDED.value,
    TerminalAction.RELEASE: OperationStatus.FAILED.value,
}


def safe_reason(exc: BaseException) -> str:
    """A stable, non-leaking diagnostic: code/class only, never the message.

    Raw exception text can carry DSNs, service secrets, SQL parameters or
    request payloads, so it is never propagated into logs or ``RunResult``.
    """
    if isinstance(exc, ExecutionError):
        return exc.code.value
    return type(exc).__name__


@dataclass(frozen=True)
class RunResult:
    """Outcome of one worker step; carries the evidence a test needs."""

    operation_id: str
    status: str
    previous_status: str | None
    action: TerminalAction | None
    lease: LeaseGrant | None
    outcome: DownstreamOutcome | None
    downstream_called: bool
    reason: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.action is not None


class ExecutionService:
    """Trusted in-process execution lifecycle over real PostgreSQL."""

    def __init__(
        self,
        *,
        gateway_dsn: str,
        ledger: ExecutionLedger,
        catalog: TrustedCatalog,
        downstream: DownstreamPort,
        downstream_secret: str,
        lease_ttl_seconds: int = DEFAULT_LEASE_TTL_S,
        connector: Callable[..., psycopg.Connection] | None = None,
        lock_timeout_ms: int = DEFAULT_LOCK_TIMEOUT_MS,
        statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    ) -> None:
        if not downstream_secret:
            raise ValueError("downstream_secret must be configured")
        self._dsn = gateway_dsn
        self._ledger = ledger
        self._catalog = catalog
        self._downstream = downstream
        self._secret = downstream_secret
        self._lease_ttl = lease_ttl_seconds
        self._lock_timeout_ms = _bounded_timeout("lock_timeout_ms", lock_timeout_ms)
        self._statement_timeout_ms = _bounded_timeout("statement_timeout_ms", statement_timeout_ms)
        self._connector: Callable[..., psycopg.Connection] = (
            connector if connector is not None else psycopg.connect
        )

    # -------------------------------------------------------- connections

    def _apply_limits(self, conn: psycopg.Connection) -> None:
        conn.execute(
            "SELECT set_config('lock_timeout', %s, false), "
            "set_config('statement_timeout', %s, false)",
            (f"{self._lock_timeout_ms}ms", f"{self._statement_timeout_ms}ms"),
        )

    def _connect(self) -> psycopg.Connection:
        conn = self._connector(
            self._dsn, autocommit=False, connect_timeout=DEFAULT_CONNECT_TIMEOUT_S
        )
        try:
            self._apply_limits(conn)
        except BaseException:
            conn.close()
            raise
        return conn

    def _read(self) -> psycopg.Connection:
        """Bounded read-only connection: waits are capped just like writes."""
        conn = self._connector(
            self._dsn, autocommit=True, connect_timeout=DEFAULT_CONNECT_TIMEOUT_S
        )
        try:
            self._apply_limits(conn)
        except BaseException:
            conn.close()
            raise
        return conn

    # ------------------------------------------------------------- accept

    def accept_invocation(
        self, verified: VerifiedInvocation, snapshot: TrustedPermissionSnapshot, *, binding=None
    ) -> AcceptResult:
        """Reserve budget for one invocation through the full A2 accept flow."""
        tool = parse_tool_id(verified.tool_id)
        parse_tool_version(verified.tool_version)
        params = parse_tool_params(tool, verified.canonical_params)

        # The immutable database parent chain is authoritative for the chain
        # binding; read it without locking so nothing is held across later work.
        db_path = self._read_path_ids(verified.grant_id)

        # (1) static trusted authorization — no current quote is consulted here.
        policy.check_static_authorization(
            snapshot,
            grant_id=verified.grant_id,
            root_id=verified.root_id,
            tenant_id=verified.tenant_id,
            task_id=verified.task_id,
            subject=verified.subject,
            tool_id=tool,
            params=params,
            db_path=db_path,
        )

        # (2) read-only candidate lookup; the row is an immutable accept fact.
        existing = self._find_candidate(verified)
        if existing is not None:
            return self._accept_from_candidate(verified, existing, db_path, binding=binding)

        # (3) only a new intent resolves the current trusted quote.
        try:
            quote_snapshot = policy.resolve_tool_resources(
                self._catalog,
                tenant_id=verified.tenant_id,
                task_id=verified.task_id,
                tool_id=tool,
                params=params,
                operation_facts=self._operation_facts,
                caller_grant_id=verified.grant_id,
                caller_holder_client_id=verified.holder_client_id,
                caller_holder_kid=verified.holder_kid,
            )
        except ExecutionError:
            # any resource/quote resolution failure must safely re-check the
            # candidate: a concurrent accept may already have committed the key.
            existing = self._find_candidate(verified)
            if existing is None:
                raise
            return self._accept_from_candidate(verified, existing, db_path, binding=binding)

        # A concurrent accept may have committed this business key while the
        # quote was being resolved. The check therefore belongs *inside* the
        # accept transaction, not in another non-locking lookup afterwards.
        return self._accept_checked(verified, self._cost_for_new(quote_snapshot), binding=binding)

    def _read_path_ids(self, grant_id: str) -> tuple[str, ...]:
        with self._read() as conn:
            try:
                path = ledger_store.load_path(conn, grant_id)
            except psycopg.Error:
                raise
            except Exception:
                # A missing/unknown grant is rejected by A1 accept with
                # INVALID_CONTEXT; do not leak anything about the path here.
                return ()
        return tuple(g.grant_id for g in path)

    def _operation_facts(self, operation_id: str) -> policy.OperationAccessFacts | None:
        with self._read() as conn:
            row = exec_store.fetch_operation(conn, operation_id)
        if row is None:
            return None
        return (row.tenant_id, row.task_id, row.grant_id, row.holder_client_id, row.holder_kid)

    def _find_candidate(self, verified: VerifiedInvocation):
        with self._read() as conn:
            return ledger_store.fetch_operation_by_business_key(
                conn,
                verified.tenant_id,
                verified.task_id,
                verified.tool_id,
                verified.idempotency_key,
            )

    def _accept_from_candidate(self, verified, row, db_path, *, binding=None) -> AcceptResult:
        """Use the persisted accept facts and still go through A1 accept.

        The complete accept material is verified automatically on this path
        (not only when somebody calls a helper first): any gap is quarantined
        and the request is refused instead of being served from incomplete
        material or re-priced from a current quote.
        """
        # the persisted facts are checked against the *operation's own* path,
        # which is not necessarily the caller's (a retry may come from a
        # different grant and must then be refused by A1's intent check).
        self._ensure_accept_material(row.operation_id, row=row)
        cost = TrustedCost(
            amount_fen=row.amount_fen,
            calls=row.calls,
            currency=row.currency,
            quote_id=row.quote_id,
            quote_version=row.quote_version,
            quote_snapshot=row.quote_snapshot,
        )
        return self._accept_checked(verified, cost, binding=binding)

    def _accept_checked(self, verified, cost: TrustedCost, *, binding=None) -> AcceptResult:
        """Enter the accept transaction with an atomic existing-material check.

        The validator is created per call and closed over a local holder, so
        concurrent calls can never cross-talk. It runs inside the accept
        transaction on the same connection and reads the operation/path/events
        there; it never commits, never contacts a downstream and never opens
        another connection. When it refuses, the request (and its new proof)
        roll back first and only then is the quarantine persisted on a separate
        connection, so the flag can never self-deadlock on the row's own
        foreign key while the rejecting transaction still holds the locks.
        """
        seen: dict[str, str] = {}

        def validator(conn, existing) -> None:
            seen["operation_id"] = existing.operation_id
            path_ids = ()
            try:
                path_ids = tuple(
                    g.grant_id for g in ledger_store.load_path(conn, existing.grant_id)
                )
            except psycopg.Error:
                raise
            except Exception:  # noqa: BLE001 - an unreadable path is unusable material
                path_ids = ()
            events = exec_store.fetch_event_nodes(conn, existing.operation_id)
            verify_accept_facts(existing, events, db_path=path_ids)

        try:
            if binding is not None:
                return self._ledger.accept_bound(
                    verified, cost, existing_validator=validator, binding=binding
                )
            return self._ledger.accept_checked(verified, cost, existing_validator=validator)
        except ExecutionError as exc:
            # only material refusals are converted into a durable quarantine;
            # real database faults must propagate untouched
            if exc.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID and seen.get("operation_id"):
                self._quarantine(
                    seen["operation_id"],
                    reason="insufficient accepted material",
                    detail={"code": exc.code.value},
                )
            raise

    def _cost_for_new(self, quote_snapshot: TrustedQuoteSnapshot | None) -> TrustedCost:
        if quote_snapshot is None:
            return TrustedCost(
                amount_fen=0,
                calls=1,
                currency=CURRENCY,
                quote_id=None,
                quote_version=None,
                quote_snapshot=None,
            )
        return TrustedCost(
            amount_fen=quote_snapshot.total_fen,
            calls=1,
            currency=quote_snapshot.currency,
            quote_id=quote_snapshot.quote_id,
            quote_version=quote_snapshot.quote_version,
            quote_snapshot=snapshot_to_bytes(quote_snapshot),
        )

    # -------------------------------------------------- accept-fact checks

    def _ensure_accept_material(
        self,
        operation_id: str,
        *,
        db_path: tuple[str, ...] | None = None,
        row=None,
    ) -> None:
        """Read-only full accept-material check with automatic quarantine.

        Every internal entry point runs this: run, reconcile, candidate hit and
        the safe-recheck fallback. Nothing is executed, settled, released or
        reserved from incomplete material, and the budget of such an operation
        is preserved untouched.
        """
        with self._read() as conn:
            operation = row if row is not None else exec_store.fetch_operation(conn, operation_id)
            if operation is None:
                raise ExecutionError(ExecutionErrorCode.OPERATION_NOT_FOUND, "unknown operation_id")
            if db_path is None:
                try:
                    db_path = tuple(
                        g.grant_id for g in ledger_store.load_path(conn, operation.grant_id)
                    )
                except psycopg.Error:
                    raise
                except Exception:
                    db_path = ()
            events = exec_store.fetch_event_nodes(conn, operation_id)
        try:
            verify_accept_facts(operation, events, db_path=db_path)
        except ExecutionError as exc:
            self._quarantine(
                operation_id,
                reason="insufficient accepted material",
                detail={"code": exc.code.value},
            )
            raise

    def _operation_facts_checked(self, operation_id: str):
        return self._operation_facts(operation_id)

    # -------------------------------------------------------------- worker

    def run_operation(
        self,
        operation_id: str,
        *,
        owner_token: str | None = None,
        pause: Callable[[ClaimResult, DownstreamOutcome | None], None] | None = None,
    ) -> RunResult:
        """Full worker step: verify, claim, execute or reconcile, then finalize.

        ``RESERVED`` means the intent has never been claimed, so the worker
        executes it. ``EXECUTING``/``UNKNOWN`` means a downstream call may
        already have happened, so the worker queries first and only re-issues
        the *idempotent* execute when nothing is known yet.

        ``pause`` is an optional synchronization seam invoked **between** the
        downstream call and the terminal transaction. It is used by the real
        process-restart tests to observe (and kill a process inside) the crash
        window; it never bypasses any check and defaults to ``None``.
        """
        owner = owner_token or uuid.uuid4().hex
        self._ensure_accept_material(operation_id)
        claim = self._claim(operation_id, owner)
        if claim.previous_status == OperationStatus.RESERVED.value:
            outcome, called, reason = self._call_downstream(
                lambda: self._downstream.execute(
                    service_secret=self._secret,
                    operation_id=operation_id,
                    tool_id=ToolId(claim.operation.tool_id),
                    canonical_params=claim.operation.canonical_params,
                    quote=self._quote_of(claim.operation),
                    expected_amount_fen=claim.operation.amount_fen,
                )
            )
        else:
            outcome, called, reason = self._call_downstream(
                lambda: self._downstream.query(
                    service_secret=self._secret, operation_id=operation_id
                )
            )
            if outcome is None and not reason:
                outcome, called, reason = self._call_downstream(
                    lambda: self._downstream.execute(
                        service_secret=self._secret,
                        operation_id=operation_id,
                        tool_id=ToolId(claim.operation.tool_id),
                        canonical_params=claim.operation.canonical_params,
                        quote=self._quote_of(claim.operation),
                        expected_amount_fen=claim.operation.amount_fen,
                    )
                )
        if pause is not None:
            pause(claim, outcome)
        return self._finalize(claim, outcome, downstream_called=called, reason=reason)

    def reconcile(
        self,
        operation_id: str,
        *,
        owner_token: str | None = None,
        pause: Callable[[ClaimResult, DownstreamOutcome | None], None] | None = None,
    ) -> RunResult:
        """Query-only recovery: never issues a new downstream request.

        A missing record is not a failure; the budget stays reserved and the
        operation stays ``UNKNOWN`` until a record appears.
        """
        owner = owner_token or uuid.uuid4().hex
        self._ensure_accept_material(operation_id)
        claim = self._claim(operation_id, owner)
        outcome, called, reason = self._call_downstream(
            lambda: self._downstream.query(service_secret=self._secret, operation_id=operation_id)
        )
        if pause is not None:
            pause(claim, outcome)
        return self._finalize(claim, outcome, downstream_called=called, reason=reason)

    def _claim(self, operation_id: str, owner_token: str) -> ClaimResult:
        """Acquire the lease under the single global lock order.

        ``task -> grants root-to-leaf -> operation -> lease``. The operation is
        first located with a *non-locking* read so that this path never takes
        the operation row before the task/grants, which is the order the
        terminal transaction uses. Locking in the opposite order deadlocks
        deterministically against a concurrent terminal write.
        """
        with self._connect() as conn:
            with conn.transaction():
                probe = exec_store.fetch_operation(conn, operation_id)
                if probe is None:
                    raise ExecutionError(
                        ExecutionErrorCode.OPERATION_NOT_FOUND, "unknown operation_id"
                    )
                # lock order: task -> grants root-to-leaf -> operation -> lease
                task = ledger_store.lock_task(conn, probe.tenant_id, probe.task_id)
                path = ledger_store.load_path(conn, probe.grant_id)
                grants = ledger_store.lock_grants_root_to_leaf(conn, [g.grant_id for g in path])
                if (
                    task.root_grant_id != grants[0].grant_id
                    or task.root_grant_id != path[0].grant_id
                ):
                    raise ExecutionError(
                        ExecutionErrorCode.ILLEGAL_TRANSITION, "operation path root mismatch"
                    )
                # lock-after re-check of the immutable location
                locked = exec_store.lock_operation(conn, operation_id)
                if locked is None:
                    raise ExecutionError(
                        ExecutionErrorCode.OPERATION_NOT_FOUND, "unknown operation_id"
                    )
                if (
                    locked.tenant_id != probe.tenant_id
                    or locked.task_id != probe.task_id
                    or locked.grant_id != probe.grant_id
                ):
                    raise ExecutionError(
                        ExecutionErrorCode.ILLEGAL_TRANSITION,
                        "operation location changed while claiming",
                    )
                return exec_store.claim_lease(
                    conn,
                    operation_id=operation_id,
                    owner_token=owner_token,
                    lease_ttl_seconds=self._lease_ttl,
                )

    def _quote_of(self, operation) -> TrustedQuoteSnapshot | None:
        return snapshot_from_bytes(operation.quote_snapshot)

    def _call_downstream(self, fn):
        """Run one downstream call; anomalies are never a terminal failure.

        The returned reason is a stable code/class name only — the raw
        exception text is deliberately discarded because it may embed the DSN,
        the service secret or request parameters.
        """
        try:
            outcome = fn()
        except ExecutionError as exc:
            if exc.code is ExecutionErrorCode.DOWNSTREAM_UNAUTHORIZED:
                raise
            return None, True, safe_reason(exc)
        except Exception as exc:  # fail safe: uncertainty never releases budget
            return None, True, safe_reason(exc)
        return outcome, True, ""

    # ----------------------------------------------------------- finalize

    def _decide(self, operation, outcome: DownstreamOutcome) -> TerminalAction | None:
        """Settle only on a fully bound confirmed effect, release only on a
        fully bound persisted refusal; anything else keeps UNKNOWN.

        The downstream record is parsed **once** by
        :func:`agent_guard.tools.results.parse_result` against a strict
        per-tool schema, and then bound to this operation's own key, tool,
        intent, complete quote, currency, amount and effect id. There is no
        per-case whitelist of "acceptable" fields: a record that does not
        describe exactly what was accepted is unusable and keeps the budget.
        """
        if outcome is None:
            return None
        if not isinstance(outcome, DownstreamOutcome):
            return None
        # the stable downstream key must be this operation's own key
        if outcome.operation_id != operation.operation_id:
            return None
        if not isinstance(outcome.tool_id, ToolId):
            return None
        if outcome.tool_id.value != operation.tool_id:
            return None
        if not isinstance(outcome.canonical_params, bytes):
            return None
        if outcome.canonical_params != operation.canonical_params:
            return None
        # booleans are ints in Python: refuse them explicitly
        if isinstance(outcome.amount_fen, bool) or not isinstance(outcome.amount_fen, int):
            return None
        if not isinstance(outcome.final_rejection, bool):
            return None
        if not isinstance(outcome.result_bytes, bytes) or not outcome.result_bytes:
            return None

        # the typed quote must be exactly the accepted one (types included)
        try:
            stored = snapshot_from_bytes(operation.quote_snapshot)
        except ExecutionError:
            return None
        if not strict_snapshots_equal(outcome.quote, stored):
            return None
        if stored is not None and (
            stored.currency != operation.currency
            or stored.quote_id != operation.quote_id
            or stored.quote_version != operation.quote_version
            or stored.total_fen != operation.amount_fen
        ):
            return None

        # one strict parse of the persisted result, then bind it to this op
        try:
            record = results.parse_result(outcome.result_bytes)
            effect_id = results.bind_result(
                record, operation_id=operation.operation_id, tool_id=operation.tool_id
            )
        except ExecutionError:
            return None

        if outcome.final_rejection is True:
            # a refusal creates no effect and reports a zero amount, and the
            # record must be a refusal for *this* tool
            if not isinstance(record, results.RefusalResult):
                return None
            if outcome.amount_fen != 0 or outcome.effect_ref is not None:
                return None
            return TerminalAction.RELEASE

        if outcome.final_rejection is False and isinstance(record, results.RefusalResult):
            # a refusal record can never be dressed up as a success
            return None

        # success shape is per tool and the effect id must be the record's own
        if outcome.amount_fen != operation.amount_fen:
            return None
        if effect_id is None:
            if outcome.effect_ref is not None:
                return None
            if not isinstance(record, results.ReadResult):
                return None
        else:
            if outcome.effect_ref != effect_id:
                return None
            if operation.tool_id == ToolId.ORDER_CREATE.value:
                if not isinstance(record, results.OrderResult):
                    return None
                assert stored is not None
                if record.supplier_id != stored.supplier_id:
                    return None
                if (
                    record.quote_id != stored.quote_id
                    or record.quote_version != stored.quote_version
                ):
                    return None
                if record.total_fen != stored.total_fen or record.total_fen != operation.amount_fen:
                    return None
                if tuple(record.items) != tuple(
                    (i.sku, i.quantity, i.unit_price_fen) for i in stored.items
                ):
                    return None
                if not _result_items_sum(record):
                    return None
            elif operation.tool_id == ToolId.NOTIFICATION_SEND.value:
                if not isinstance(record, results.NotificationResult):
                    return None
                params = parse_tool_params(ToolId(operation.tool_id), operation.canonical_params)
                if record.template_id != params.template_id:
                    return None
                if record.recipient_id != params.recipient_id:
                    return None
            else:
                return None
        return TerminalAction.SETTLE

    def _finalize(
        self,
        claim: ClaimResult,
        outcome: DownstreamOutcome | None,
        *,
        downstream_called: bool,
        reason: str,
    ) -> RunResult:
        action = self._decide(claim.operation, outcome)
        if action is None:
            status = self._mark_unknown(claim)
            return RunResult(
                operation_id=claim.operation.operation_id,
                status=status,
                previous_status=claim.previous_status,
                action=None,
                lease=claim.lease,
                outcome=outcome,
                downstream_called=downstream_called,
                reason=reason or "no confirmed downstream record",
            )

        operation_id = claim.operation.operation_id
        with self._connect() as conn:
            with conn.transaction():
                task = ledger_store.lock_task(
                    conn, claim.operation.tenant_id, claim.operation.task_id
                )
                path = ledger_store.load_path(conn, claim.operation.grant_id)
                grants = ledger_store.lock_grants_root_to_leaf(conn, [g.grant_id for g in path])
                if task.root_grant_id != grants[0].grant_id:
                    raise ExecutionError(
                        ExecutionErrorCode.ILLEGAL_TRANSITION, "operation path root mismatch"
                    )
                current = exec_store.assert_terminal_write_allowed(
                    conn,
                    operation_id=operation_id,
                    owner_token=claim.lease.owner_token,
                    fencing_version=claim.lease.fencing_version,
                )
                events = exec_store.fetch_event_nodes(conn, operation_id)
                reserve = next((e for e in events if e.phase == "RESERVE"), None)
                if reserve is None:
                    raise ExecutionError(
                        ExecutionErrorCode.ILLEGAL_TRANSITION,
                        "operation has no RESERVE event",
                    )
                # the persisted accept material must still be complete here
                verify_accept_facts(current, events, db_path=tuple(g.grant_id for g in grants))
                nodes = exec_store.terminal_node_deltas(
                    grants, action, current.amount_fen, current.calls
                )
                # stage 1: every applicable ancestor's counters
                exec_store.apply_terminal_counters(conn, nodes)
                # stage 2: the single mutually exclusive terminal event
                exec_store.insert_terminal_event(
                    conn, operation_id=operation_id, action=action, nodes=nodes
                )
                # stage 3: immutable pending-signature outbox material
                created_at = conn.execute("SELECT clock_timestamp()").fetchone()[0]
                ledger_changes = receipts.ledger_changes_bytes(
                    operation_id=operation_id,
                    reserve_event=reserve,
                    terminal_nodes=nodes,
                    terminal_action=action,
                )
                material = receipts.build_pending_receipt(
                    operation=current,
                    action=action,
                    root_grant_id=grants[0].grant_id,
                    result_bytes=outcome.result_bytes,
                    ledger_changes=ledger_changes,
                    created_at=created_at,
                )
                exec_store.insert_pending_receipt(conn, material)
                # stage 4: the status transition itself
                exec_store.transition_status(
                    conn,
                    operation_id=operation_id,
                    from_status=current.status,
                    to_status=_TERMINAL_FOR_ACTION[action],
                )
        return RunResult(
            operation_id=operation_id,
            status=_TERMINAL_FOR_ACTION[action],
            previous_status=claim.previous_status,
            action=action,
            lease=claim.lease,
            outcome=outcome,
            downstream_called=downstream_called,
            reason=reason,
        )

    def _mark_unknown(self, claim: ClaimResult) -> str:
        """Keep the budget reserved; write UNKNOWN only under the four checks.

        Even this "no-op" path takes the global lock order and re-reads the
        **current** state, owner, fencing version and lease expiry. A stale
        worker whose lease expired while another owner reached a terminal state
        is refused here instead of returning a cached ``UNKNOWN`` over the real
        terminal state; nothing in the database is overwritten either way.
        """
        with self._connect() as conn:
            with conn.transaction():
                ledger_store.lock_task(conn, claim.operation.tenant_id, claim.operation.task_id)
                path = ledger_store.load_path(conn, claim.operation.grant_id)
                ledger_store.lock_grants_root_to_leaf(conn, [g.grant_id for g in path])
                current = exec_store.assert_terminal_write_allowed(
                    conn,
                    operation_id=claim.operation.operation_id,
                    owner_token=claim.lease.owner_token,
                    fencing_version=claim.lease.fencing_version,
                )
                # the cached claim state is never the answer: use what the
                # database says right now, under these locks
                if current.status == OperationStatus.UNKNOWN.value:
                    return current.status
                row = exec_store.transition_status(
                    conn,
                    operation_id=claim.operation.operation_id,
                    from_status=current.status,
                    to_status=OperationStatus.UNKNOWN.value,
                )
                return row.status

    # ----------------------------------------------------------- material

    def _quarantine(self, operation_id: str, *, reason: str, detail: dict) -> None:
        """Persist the quarantine in its own transaction.

        Deliberately a separate connection: it must survive the caller's
        rollback, otherwise an exception would discard the flag together with
        the failed work and the operation would look untouched.
        """
        with self._connect() as conn:
            with conn.transaction():
                exec_store.flag_operation(
                    conn, operation_id=operation_id, reason=reason, detail=detail
                )

    def quarantine_if_insufficient(self, operation_id: str) -> bool:
        """Explicit helper kept for tooling; entries auto-quarantine without it."""
        with self._read() as conn:
            row = exec_store.fetch_operation(conn, operation_id)
        if row is None:
            raise ExecutionError(ExecutionErrorCode.OPERATION_NOT_FOUND, "unknown operation_id")
        try:
            self._ensure_accept_material(operation_id, row=row)
        except ExecutionError:
            return True
        return False

    # ------------------------------------------------------------ queries

    def operation_status(self, operation_id: str) -> str:
        with self._read() as conn:
            row = exec_store.fetch_operation(conn, operation_id)
        if row is None:
            raise ExecutionError(ExecutionErrorCode.OPERATION_NOT_FOUND, "unknown operation_id")
        return row.status

    def load_operation(self, operation_id: str):
        with self._read() as conn:
            return exec_store.fetch_operation(conn, operation_id)

    def outbox_entry(self, operation_id: str) -> dict | None:
        with self._read() as conn:
            return exec_store.fetch_outbox(conn, operation_id)

    def review_flag(self, operation_id: str) -> dict | None:
        with self._read() as conn:
            return exec_store.fetch_review_flag(conn, operation_id)


# --------------------------------------------------------------- helpers


def _result_items_sum(record: "results.OrderResult") -> bool:
    """The order record's total must recompute from its own lines."""
    total = 0
    for _sku, quantity, price in record.items:
        total += quantity * price
        if total > MAX_SAFE_INT:
            return False
    return total == record.total_fen


def _quote_item_shape_ok(item) -> bool:
    """A quote line must be a QuoteItem-like object with exact integer fields.

    Checked *before* any attribute is read, so ``None``/dict/other containers
    are "untrusted" instead of raising ``TypeError``/``AttributeError`` and
    leaving the operation stuck in ``EXECUTING``.
    """
    for name in ("sku", "quantity", "unit_price_fen"):
        if not hasattr(item, name):
            return False
    if not isinstance(item.sku, str) or item.sku == "":
        return False
    for name in ("quantity", "unit_price_fen"):
        value = getattr(item, name)
        if isinstance(value, bool) or not isinstance(value, int):
            return False
    return True


def _quote_items_shape_ok(items) -> bool:
    """The items container may be a tuple *or* a list of well-shaped lines."""
    if not isinstance(items, (tuple, list)):
        return False
    return all(_quote_item_shape_ok(item) for item in items)


def strict_snapshots_equal(left, right) -> bool:
    """Type-exact snapshot comparison: ``True`` never equals ``1``.

    This is a *total* definition: an unknown typed object, container, entry or
    field shape is answered "not equal" (hence UNKNOWN) instead of raising, and
    a structurally identical list is accepted just like a tuple.
    """
    if left is None or right is None:
        return left is right
    if type(left) is not type(right):
        return False
    for name in ("quote_id", "quote_version", "supplier_id", "currency", "total_fen", "items"):
        if not hasattr(left, name) or not hasattr(right, name):
            return False
    if type(left.total_fen) is not int or isinstance(left.total_fen, bool):
        return False
    if type(right.total_fen) is not int or isinstance(right.total_fen, bool):
        return False
    for name in ("quote_id", "quote_version", "supplier_id", "currency"):
        if not isinstance(getattr(left, name), str) or not isinstance(getattr(right, name), str):
            return False
    if left.quote_id != right.quote_id or left.quote_version != right.quote_version:
        return False
    if left.supplier_id != right.supplier_id:
        return False
    if left.total_fen != right.total_fen or left.currency != right.currency:
        return False
    if not _quote_items_shape_ok(left.items) or not _quote_items_shape_ok(right.items):
        return False
    if len(left.items) != len(right.items):
        return False
    for a, b in zip(left.items, right.items, strict=False):
        if (a.sku, a.quantity, a.unit_price_fen) != (b.sku, b.quantity, b.unit_price_fen):
            return False
    return True


def _bounded_timeout(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer (bool/float rejected)")
    if value < 1 or value > 600_000:
        raise ValueError(f"{name} must be within [1, 600000]")
    return value


def verify_accept_facts(operation, events, *, db_path: tuple[str, ...]) -> None:
    """Validate the complete persisted accept material of one operation.

    Covers the strict tool/parameter form, the tool version, the cost identity
    (currency, calls, amount bounds), the quote identity and full snapshot, the
    first-accept evidence and the whole RESERVE path with its exact deltas.
    Any gap raises ``LEGACY_SNAPSHOT_INVALID`` so the caller can quarantine;
    nothing here reaches a downstream or re-prices from a current quote.
    """
    fail = ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID

    if not isinstance(operation.calls, int) or isinstance(operation.calls, bool):
        raise ExecutionError(fail, "accepted calls must be an integer")
    if operation.calls != 1:
        raise ExecutionError(fail, "accepted operation must cost exactly one call")
    if isinstance(operation.amount_fen, bool) or not isinstance(operation.amount_fen, int):
        raise ExecutionError(fail, "accepted amount must be an integer")
    if operation.amount_fen < 0 or operation.amount_fen > MAX_SAFE_INT:
        raise ExecutionError(fail, "accepted amount out of range")
    if operation.currency != CURRENCY:
        raise ExecutionError(fail, "accepted currency is not CNY")

    for name in ("token_digest", "proof_digest", "intent_digest", "evidence_ref"):
        value = getattr(operation, name)
        if not isinstance(value, str) or value == "":
            raise ExecutionError(fail, "persisted first-accept evidence is incomplete")

    # Foreseeable schema/encoding/recursion problems in the persisted material
    # are one safe answer: LEGACY_SNAPSHOT_INVALID so the caller quarantines.
    # This block is pure parsing over already-read values, so a real database
    # fault can never be swallowed here.
    try:
        tool = parse_tool_id(operation.tool_id)
        parse_tool_version(operation.tool_version)
        params = parse_tool_params(tool, operation.canonical_params)
        quote_snapshot = snapshot_from_bytes(operation.quote_snapshot)
    except ExecutionError as exc:
        raise ExecutionError(fail, f"accepted material is not usable: {exc.code.value}") from exc
    except (RecursionError, ValueError, TypeError, AttributeError, KeyError, OverflowError) as exc:
        raise ExecutionError(
            fail, f"accepted material is not decodable: {type(exc).__name__}"
        ) from exc
    if tool is ToolId.ORDER_CREATE:
        if quote_snapshot is None:
            raise ExecutionError(fail, "accepted order has no persisted quote snapshot")
        if operation.quote_id is None or operation.quote_version is None:
            raise ExecutionError(fail, "accepted order has no persisted quote identity")
        # three-way identity: params <-> cost columns <-> stored snapshot
        if not isinstance(params, OrderCreateParams):
            raise ExecutionError(fail, "accepted order parameters are not an order")
        if params.quote_id != operation.quote_id:
            raise ExecutionError(fail, "accepted params quote_id does not match the cost")
        if params.quote_version != operation.quote_version:
            raise ExecutionError(fail, "accepted params quote_version does not match the cost")
        if quote_snapshot.quote_id != operation.quote_id:
            raise ExecutionError(fail, "stored quote_id does not match the snapshot")
        if quote_snapshot.quote_version != operation.quote_version:
            raise ExecutionError(fail, "stored quote_version does not match the snapshot")
        if quote_snapshot.currency != operation.currency:
            raise ExecutionError(fail, "stored quote currency does not match the cost")
        if quote_snapshot.total_fen != operation.amount_fen:
            raise ExecutionError(fail, "stored quote total does not match the reserved amount")
        expected = {(item.sku, item.quantity) for item in params.items}
        actual = {(item.sku, item.quantity) for item in quote_snapshot.items}
        if expected != actual or len(quote_snapshot.items) != len(params.items):
            raise ExecutionError(fail, "stored quote snapshot does not match the accepted items")
    else:
        if quote_snapshot is not None:
            raise ExecutionError(fail, "zero-amount tool must not carry a quote snapshot")
        if operation.quote_id is not None or operation.quote_version is not None:
            raise ExecutionError(fail, "zero-amount tool must not carry a quote identity")
        if operation.amount_fen != 0:
            raise ExecutionError(fail, "zero-amount tool has a non-zero reserved amount")

    # every ledger event must cover the whole root-to-leaf path exactly, and
    # there must be exactly one RESERVE and at most one terminal event
    if not db_path:
        raise ExecutionError(fail, "accepted operation has no readable grant path")
    reserve = [event for event in events if event.phase == "RESERVE"]
    terminal = [event for event in events if event.phase in ("SETTLE", "RELEASE")]
    if len(reserve) != 1:
        raise ExecutionError(fail, "accepted operation must have exactly one RESERVE event")
    if len(terminal) > 1:
        raise ExecutionError(fail, "accepted operation has more than one terminal event")
    for event in events:
        if event.phase == "RESERVE" and event.seq != 0:
            raise ExecutionError(fail, "RESERVE event must be sequence 0")
        if event.phase in ("SETTLE", "RELEASE") and event.seq != 1:
            raise ExecutionError(fail, "terminal event must be sequence 1")
        nodes = event.nodes
        if len(nodes) != len(db_path):
            raise ExecutionError(fail, "ledger event does not cover the whole grant path")
        for position, (node, grant_id) in enumerate(zip(nodes, db_path, strict=False)):
            if node.position != position or node.grant_id != grant_id:
                raise ExecutionError(fail, "ledger event node path does not match the grant path")
            if event.phase == "RESERVE":
                want = (operation.amount_fen, 0, operation.calls, 0)
            elif event.phase == "SETTLE":
                want = (
                    -operation.amount_fen,
                    operation.amount_fen,
                    -operation.calls,
                    operation.calls,
                )
            else:
                want = (-operation.amount_fen, 0, -operation.calls, 0)
            got = (
                node.amount_reserved_delta,
                node.amount_settled_delta,
                node.calls_reserved_delta,
                node.calls_settled_delta,
            )
            if got != want:
                raise ExecutionError(
                    fail, f"{event.phase} event node deltas do not match the accepted cost"
                )
