"""Persistent mock downstream for A2.1: orders, notifications and reads.

Design anchors: ``docs/security-model.md`` section 6 and
``docs/oauth-oidc-sm2-mvp.md`` 9.4. The mock downstream is a **separate
transaction domain**: its own database, its own connections and its own
transactions. The gateway never reuses its connection and never pretends a
single transaction spans the two domains.

Guarantees implemented here:

* the stable downstream key is the gateway ``operation_id``;
* the intent (tool, canonical params and the complete validated quote
  snapshot), the effect, the result and a terminal refusal are persisted with
  database unique constraints inside one downstream transaction;
* every call must present the independent gateway *service secret*; agent or
  caller credentials are refused and nothing is executed or leaked;
* the same key with the same intent replays the very same order/notification/
  result (``already_existed=True``), the same key with a different intent is
  refused and never overwrites the first record;
* a persisted terminal refusal makes a later success impossible for that key;
* reads produce no monetary effect but their result is fixed on first
  execution, and notifications are idempotent exactly like orders.

This module performs no cryptography: no SM2, no SM3, no RFC 8785 canonical
encoding and no TLS. Byte fields are plain payloads.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict

import psycopg

from agent_guard.contracts.execution import (
    DownstreamOutcome,
    ExecutionError,
    ExecutionErrorCode,
    ToolId,
    TrustedQuoteSnapshot,
)
from agent_guard.tools.catalog import snapshot_from_bytes, snapshot_to_bytes

#: Tables owned by the downstream domain (never mixed with the gateway schema).
DOWNSTREAM_TABLES = ("ds_orders", "ds_notifications", "ds_operations")

DOWNSTREAM_DDL = """
CREATE TABLE IF NOT EXISTS ds_operations (
    operation_id     TEXT PRIMARY KEY,
    tool_id          TEXT NOT NULL,
    canonical_params BYTEA NOT NULL,
    quote_json       BYTEA,
    amount_fen       BIGINT NOT NULL CHECK (amount_fen BETWEEN 0 AND 9007199254740991),
    disposition      TEXT NOT NULL CHECK (disposition IN ('EFFECT', 'REJECTED')),
    effect_ref       TEXT,
    result_bytes     BYTEA NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS ds_orders (
    order_id     TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE REFERENCES ds_operations (operation_id),
    amount_fen   BIGINT NOT NULL CHECK (amount_fen BETWEEN 0 AND 9007199254740991),
    supplier_id  TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS ds_notifications (
    notification_id TEXT PRIMARY KEY,
    operation_id    TEXT NOT NULL UNIQUE REFERENCES ds_operations (operation_id),
    template_id     TEXT NOT NULL,
    recipient_id    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
"""

CONNECT_TIMEOUT_S = 5

#: Bounded SQL waits for every downstream connection. ``connect_timeout`` only
#: bounds TCP setup; without these a query can block on a table lock forever.
#: 0 is rejected because PostgreSQL treats 0 as "no timeout".
DEFAULT_LOCK_TIMEOUT_MS = 5_000
DEFAULT_STATEMENT_TIMEOUT_MS = 10_000
_TIMEOUT_BOUNDS = (1, 600_000)


def _bounded_timeout(name: str, value: object) -> int:
    """Reject bool/0/float/out-of-range waits: an unbounded wait is not allowed."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer (bool/float rejected)")
    if value < _TIMEOUT_BOUNDS[0] or value > _TIMEOUT_BOUNDS[1]:
        raise ValueError(f"{name} must be within [{_TIMEOUT_BOUNDS[0]}, {_TIMEOUT_BOUNDS[1]}]")
    return value


def _check_secret(service_secret: object, expected: str) -> None:
    """Constant-work refusal; the message never echoes the presented value."""
    if not isinstance(service_secret, str) or not service_secret:
        raise ExecutionError(
            ExecutionErrorCode.DOWNSTREAM_UNAUTHORIZED, "missing downstream service secret"
        )
    if not secrets.compare_digest(service_secret.encode("utf-8"), expected.encode("utf-8")):
        raise ExecutionError(
            ExecutionErrorCode.DOWNSTREAM_UNAUTHORIZED, "invalid downstream service secret"
        )


class MockDownstream:
    """Independent-transaction-domain order/notification/read service."""

    def __init__(
        self,
        dsn: str,
        *,
        service_secret: str,
        approved_suppliers: frozenset[str] | set[str] = frozenset(),
        approved_recipients: frozenset[str] | set[str] = frozenset(),
        served_requests: frozenset[str] | set[str] = frozenset(),
        lock_timeout_ms: int = DEFAULT_LOCK_TIMEOUT_MS,
        statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    ) -> None:
        if not service_secret:
            raise ValueError("downstream service secret must be configured")
        self._dsn = dsn
        self._secret = service_secret
        # Downstream-side allow-lists: an empty set serves nothing (fail closed).
        self._approved_suppliers = frozenset(approved_suppliers)
        self._approved_recipients = frozenset(approved_recipients)
        self._served_requests = frozenset(served_requests)
        self._lock_timeout_ms = _bounded_timeout("lock_timeout_ms", lock_timeout_ms)
        self._statement_timeout_ms = _bounded_timeout("statement_timeout_ms", statement_timeout_ms)

    # ------------------------------------------------------------ lifecycle

    def provision(self) -> None:
        """Create the downstream schema in its own database (idempotent)."""
        with self._connect() as conn:
            with conn.transaction():
                conn.execute(DOWNSTREAM_DDL)

    def reset(self) -> None:
        """Drop downstream rows inside this run's own downstream database."""
        with self._connect() as conn:
            with conn.transaction():
                conn.execute(
                    "TRUNCATE " + ", ".join(DOWNSTREAM_TABLES) + " RESTART IDENTITY CASCADE"
                )

    def _connect(self) -> psycopg.Connection:
        """Bounded downstream connection: connect *and* SQL waits are capped."""
        conn = psycopg.connect(self._dsn, autocommit=False, connect_timeout=CONNECT_TIMEOUT_S)
        try:
            conn.execute(
                "SELECT set_config('lock_timeout', %s, false), "
                "set_config('statement_timeout', %s, false)",
                (f"{self._lock_timeout_ms}ms", f"{self._statement_timeout_ms}ms"),
            )
        except BaseException:
            conn.close()
            raise
        return conn

    # ------------------------------------------------------------- execute

    def execute(
        self,
        *,
        service_secret: str,
        operation_id: str,
        tool_id: ToolId,
        canonical_params: bytes,
        quote: TrustedQuoteSnapshot | None,
        expected_amount_fen: int,
    ) -> DownstreamOutcome:
        """Execute (or idempotently replay) one operation key.

        The whole intent, effect, result and any terminal refusal are saved in
        one downstream transaction. The gateway calls this outside its own
        transaction.
        """
        _check_secret(service_secret, self._secret)
        quote_bytes = snapshot_to_bytes(quote) if quote is not None else None

        try:
            with self._connect() as conn:
                with conn.transaction():
                    existing = self._load(conn, operation_id)
                    if existing is not None:
                        return self._replay(existing, tool_id, canonical_params, quote_bytes)
                    return self._first_run(
                        conn,
                        operation_id=operation_id,
                        tool_id=tool_id,
                        canonical_params=canonical_params,
                        quote=quote,
                        quote_bytes=quote_bytes,
                        expected_amount_fen=expected_amount_fen,
                    )
        except psycopg.errors.UniqueViolation:
            # A concurrent writer won the insert race: the database unique
            # constraint is the idempotency boundary, so read its committed row
            # and replay instead of ever producing a second effect.
            with self._connect() as conn:
                row = self._load(conn, operation_id)
            if row is None:  # pragma: no cover - defensive
                raise
            return self._replay(row, tool_id, canonical_params, quote_bytes)

    def query(self, *, service_secret: str, operation_id: str) -> DownstreamOutcome | None:
        """Return the persisted record, or ``None`` when nothing is known yet.

        ``None`` is not a terminal failure: a late request may still land, so
        the caller keeps the budget reserved and continues recovery.
        """
        _check_secret(service_secret, self._secret)
        with self._connect() as conn:
            row = self._load(conn, operation_id)
        return None if row is None else self._row_to_outcome(row)

    # ------------------------------------------------------------ internals

    def _load(self, conn: psycopg.Connection, operation_id: str) -> tuple | None:
        return conn.execute(
            "SELECT operation_id, tool_id, canonical_params, quote_json, amount_fen, "
            "disposition, effect_ref, result_bytes "
            "FROM ds_operations WHERE operation_id = %s",
            (operation_id,),
        ).fetchone()

    def _row_to_outcome(self, row: tuple) -> DownstreamOutcome:
        (
            operation_id,
            tool_id,
            canonical_params,
            quote_json,
            amount_fen,
            disposition,
            effect_ref,
            result_bytes,
        ) = row
        quote = snapshot_from_bytes(bytes(quote_json)) if quote_json is not None else None
        return DownstreamOutcome(
            operation_id=operation_id,
            tool_id=ToolId(tool_id),
            canonical_params=bytes(canonical_params),
            quote=quote,
            amount_fen=amount_fen,
            effect_ref=effect_ref,
            result_bytes=bytes(result_bytes),
            final_rejection=disposition == "REJECTED",
            already_existed=True,
        )

    def _replay(
        self,
        row: tuple,
        tool_id: ToolId,
        canonical_params: bytes,
        quote_bytes: bytes | None,
    ) -> DownstreamOutcome:
        """Same key: identical intent replays, a different intent is refused."""
        stored_tool = ToolId(row[1])
        stored_params = bytes(row[2])
        stored_quote = bytes(row[3]) if row[3] is not None else None
        if (
            stored_tool is not tool_id
            or stored_params != canonical_params
            or stored_quote != quote_bytes
        ):
            raise ExecutionError(
                ExecutionErrorCode.DOWNSTREAM_INTENT_CONFLICT,
                "same downstream key with a different intent",
            )
        return self._row_to_outcome(row)

    def _first_run(
        self,
        conn: psycopg.Connection,
        *,
        operation_id: str,
        tool_id: ToolId,
        canonical_params: bytes,
        quote: TrustedQuoteSnapshot | None,
        quote_bytes: bytes | None,
        expected_amount_fen: int,
    ) -> DownstreamOutcome:
        refusal = self._refuse_reason(
            tool_id=tool_id,
            canonical_params=canonical_params,
            quote=quote,
            expected_amount_fen=expected_amount_fen,
        )
        if refusal is not None:
            result = json.dumps(
                {
                    "kind": "refusal",
                    "operation_id": operation_id,
                    "tool_id": tool_id.value,
                    "reason": refusal,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            conn.execute(
                "INSERT INTO ds_operations "
                "(operation_id, tool_id, canonical_params, quote_json, amount_fen, "
                " disposition, effect_ref, result_bytes) "
                "VALUES (%s, %s, %s, %s, 0, 'REJECTED', NULL, %s)",
                (operation_id, tool_id.value, canonical_params, quote_bytes, result),
            )
            return DownstreamOutcome(
                operation_id=operation_id,
                tool_id=tool_id,
                canonical_params=canonical_params,
                quote=quote,
                amount_fen=0,
                effect_ref=None,
                result_bytes=result,
                final_rejection=True,
                already_existed=False,
            )

        effect_ref: str | None = None
        amount_fen = 0 if quote is None else quote.total_fen
        extra_sql: tuple[str, tuple] | None = None

        if tool_id is ToolId.ORDER_CREATE:
            assert quote is not None
            effect_ref = f"order-{secrets.token_hex(8)}"
            record = {
                "kind": "order",
                "order_id": effect_ref,
                "operation_id": operation_id,
                "supplier_id": quote.supplier_id,
                "quote_id": quote.quote_id,
                "quote_version": quote.quote_version,
                "items": [asdict(item) for item in quote.items],
                "total_fen": quote.total_fen,
            }
            extra_sql = (
                "INSERT INTO ds_orders (order_id, operation_id, amount_fen, supplier_id) "
                "VALUES (%s, %s, %s, %s)",
                (effect_ref, operation_id, quote.total_fen, quote.supplier_id),
            )
        elif tool_id is ToolId.NOTIFICATION_SEND:
            effect_ref = f"notif-{secrets.token_hex(8)}"
            template_id, recipient_id = _notification_targets(canonical_params)
            record = {
                "kind": "notification",
                "notification_id": effect_ref,
                "operation_id": operation_id,
                "template_id": template_id,
                "recipient_id": recipient_id,
            }
            extra_sql = (
                "INSERT INTO ds_notifications "
                "(notification_id, operation_id, template_id, recipient_id) "
                "VALUES (%s, %s, %s, %s)",
                (effect_ref, operation_id, template_id, recipient_id),
            )
        else:
            # exact read shape (tools/results.py): the fixed payload itself
            # is the effect; nothing else may be smuggled into the record
            record = {
                "kind": "read",
                "operation_id": operation_id,
                "tool_id": tool_id.value,
            }

        result = json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        conn.execute(
            "INSERT INTO ds_operations "
            "(operation_id, tool_id, canonical_params, quote_json, amount_fen, "
            " disposition, effect_ref, result_bytes) "
            "VALUES (%s, %s, %s, %s, %s, 'EFFECT', %s, %s)",
            (
                operation_id,
                tool_id.value,
                canonical_params,
                quote_bytes,
                amount_fen,
                effect_ref,
                result,
            ),
        )
        if extra_sql is not None:
            conn.execute(*extra_sql)
        return DownstreamOutcome(
            operation_id=operation_id,
            tool_id=tool_id,
            canonical_params=canonical_params,
            quote=quote,
            amount_fen=amount_fen,
            effect_ref=effect_ref,
            result_bytes=result,
            final_rejection=False,
            already_existed=False,
        )

    def _refuse_reason(
        self,
        *,
        tool_id: ToolId,
        canonical_params: bytes,
        quote: TrustedQuoteSnapshot | None,
        expected_amount_fen: int,
    ) -> str | None:
        """A deterministic business refusal; persisted so the key can never win later."""
        fields = _params_fields(canonical_params)
        if tool_id is ToolId.ORDER_CREATE:
            if quote is None:
                return "order without a validated quote snapshot"
            if quote.supplier_id not in self._approved_suppliers:
                return "supplier is not served by this downstream"
            line_total = sum(item.quantity * item.unit_price_fen for item in quote.items)
            if line_total != quote.total_fen:
                return "quote total does not match its own lines"
            if quote.total_fen != expected_amount_fen:
                return "expected amount does not match the validated quote"
            if not canonical_params:
                return "empty order parameters"
            return None
        if tool_id is ToolId.NOTIFICATION_SEND:
            if not canonical_params:
                return "empty notification parameters"
            if str(fields.get("recipient_id", "")) not in self._approved_recipients:
                return "recipient is not served by this downstream"
            return None
        if not canonical_params:
            return "empty read parameters"
        if str(fields.get("request_id", "")) not in self._served_requests:
            return "request is not served by this downstream"
        return None


def _params_fields(canonical_params: bytes) -> dict:
    """Best-effort read of the persisted params for the downstream record."""
    try:
        decoded = json.loads(bytes(canonical_params).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _notification_targets(canonical_params: bytes) -> tuple[str, str]:
    """Best-effort read of template/recipient for the persisted delivery record."""
    fields = _params_fields(canonical_params)
    return str(fields.get("template_id", "")), str(fields.get("recipient_id", ""))
