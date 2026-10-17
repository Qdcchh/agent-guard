"""Durable payment intent, budget reservation and state machine over PostgreSQL.

Two transaction domains meet here but never pretend to be one atomic unit:

* the payment intent, its state row and the independent asset-budget
  reservation are written **inside the existing acceptance transaction** on the
  caller's connection (``reserve_payment_tx``);
* every later state transition opens its own bounded transaction and moves the
  asset budget only for the two terminal outcomes: ``SETTLED`` moves the
  reservation into settled, ``FAILED`` releases it, ``UNKNOWN`` keeps it.

Authorization material (nonce and the complete payload) is persisted before
any network call, and the database guards refuse to rewrite it afterwards.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

import psycopg

from agent_guard.x402.contracts import (
    PaymentIntent,
    PaymentStatus,
    X402Error,
)

DEFAULT_CONNECT_TIMEOUT_S = 5
DEFAULT_LOCK_TIMEOUT_MS = 10_000
DEFAULT_STATEMENT_TIMEOUT_MS = 15_000

_INTENT_COLUMNS = (
    "operation_id,tenant_id,task_id,grant_id,root_grant_id,action_id,payment_digest,"
    "tool_id,idempotency_key,profile,scheme,transfer_method,network,chain_id,asset,"
    "asset_name,asset_version,asset_amount,pay_to,resource_url,amount_fen,quote_id,"
    "quote_version,valid_before"
)

_INSERT_INTENT = (
    f"INSERT INTO ag_payment_intents ({_INTENT_COLUMNS}) VALUES ("
    "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s"
    ") ON CONFLICT (operation_id) DO NOTHING RETURNING operation_id"
)
_SELECT_INTENT = f"SELECT {_INTENT_COLUMNS} FROM ag_payment_intents WHERE operation_id=%s"

_INSERT_STATE = (
    "INSERT INTO ag_payment_states (operation_id,status) VALUES (%s,%s) "
    "ON CONFLICT (operation_id) DO NOTHING RETURNING operation_id"
)
_SELECT_STATE = (
    "SELECT status,nonce,payload_sha256,tx_hash,failure_code,authorized_at,"
    "submitted_at,settled_at FROM ag_payment_states WHERE operation_id=%s"
)


@dataclass(frozen=True)
class PaymentRecord:
    """Persisted intent plus current state; never contains key material."""

    intent: PaymentIntent
    operation_id: str
    status: PaymentStatus
    nonce: str | None
    payload_sha256: str | None
    tx_hash: str | None
    failure_code: str | None
    authorized_at: object
    submitted_at: object
    settled_at: object

    @property
    def has_authorization(self) -> bool:
        return self.nonce is not None and self.payload_sha256 is not None


def _bounded(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer (bool/float rejected)")
    if value < 1 or value > 600_000:
        raise ValueError(f"{name} must be within [1, 600000]")
    return value


def _connect(
    dsn: str,
    connector: Callable[..., psycopg.Connection] | None = None,
) -> psycopg.Connection:
    connect = connector if connector is not None else psycopg.connect
    conn = connect(dsn, autocommit=False, connect_timeout=DEFAULT_CONNECT_TIMEOUT_S)
    try:
        conn.execute(
            "SELECT set_config('lock_timeout', %s, false), "
            "set_config('statement_timeout', %s, false)",
            (f"{DEFAULT_LOCK_TIMEOUT_MS}ms", f"{DEFAULT_STATEMENT_TIMEOUT_MS}ms"),
        )
    except BaseException:
        conn.close()
        raise
    return conn


# ------------------------------------------------------- trusted initialization


def seed_asset_budget(
    dsn: str,
    *,
    tenant_id: str,
    task_id: str,
    asset: str,
    chain_id: int,
    amount_limit: str,
    connector: Callable[..., psycopg.Connection] | None = None,
) -> None:
    """Trusted initialization of one independent asset budget.

    There is deliberately no implicit budget creation on accept: an operation
    whose budget was never seeded fails closed.
    """
    if not amount_limit.isdigit() or not 1 <= len(amount_limit) <= 78:
        raise ValueError("asset budget limit must be a canonical decimal string")
    with _connect(dsn, connector) as conn:
        with conn.transaction():
            conn.execute(
                "INSERT INTO ag_payment_budgets "
                "(tenant_id,task_id,asset,chain_id,amount_limit) VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT (tenant_id,task_id,asset,chain_id) DO NOTHING",
                (tenant_id, task_id, asset, chain_id, amount_limit),
            )


# ------------------------------------------------------------ accept transaction


def reserve_payment_tx(
    conn: psycopg.Connection,
    *,
    operation,
    action_id: str,
    intent: PaymentIntent,
    amount_fen: int,
) -> None:
    """Insert the immutable intent and reserve the independent asset budget.

    Runs inside the acceptance transaction on the same connection: a failure
    rolls the whole acceptance back (operation, CNY reservation, approval row
    and payment reservation together), so a refused payment never burns budget
    or an approval. Retries must find the identical immutable intent; an
    existing intent is validated but never reserves the asset budget again.
    """
    if operation.operation_id is None:
        raise X402Error("operation must exist before its payment intent")
    row = conn.execute(
        _INSERT_INTENT,
        (
            operation.operation_id,
            intent.tenant_id,
            intent.task_id,
            intent.grant_id,
            intent.root_grant_id,
            action_id,
            intent.digest,
            intent.tool_id,
            intent.idempotency_key,
            "AG-X402-PAYMENT-INTENT-1",
            "exact",
            "eip3009",
            intent.network,
            intent.chain_id,
            intent.asset,
            intent.asset_name,
            intent.asset_version,
            Decimal(intent.asset_amount),
            intent.pay_to,
            intent.resource_url,
            amount_fen,
            intent.quote_id,
            intent.quote_version,
            intent.valid_before,
        ),
    ).fetchone()
    if row is None:
        existing = fetch_intent_row(conn, operation.operation_id)
        if existing is None or not _intent_row_matches(
            existing, operation=operation, action_id=action_id, intent=intent, amount_fen=amount_fen
        ):
            raise X402Error(
                "operation is already bound to a different payment intent",
                code="PAYMENT_INTENT_CONFLICT",
            )
        # A retry of the same approved intent must find the state and the
        # already-reserved asset budget untouched: only the fresh insert above
        # may reserve, and exactly once per operation.
        state_row = conn.execute(_SELECT_STATE, (operation.operation_id,)).fetchone()
        if state_row is None:
            raise X402Error("payment intent exists without its state", code="PAYMENT_STATE_MISSING")
        return
    state = conn.execute(_INSERT_STATE, (operation.operation_id, PaymentStatus.UNPAID.value))
    state.fetchone()
    _reserve_budget_tx(conn, intent)


def assert_payment_tx(conn: psycopg.Connection, *, operation_id: str, digest: str) -> None:
    """Final same-transaction check: the committed intent is the approved one."""
    row = conn.execute(
        "SELECT payment_digest FROM ag_payment_intents WHERE operation_id=%s",
        (operation_id,),
    ).fetchone()
    if row is None or row[0] != digest:
        raise X402Error(
            "payment intent disappeared or changed during acceptance",
            code="PAYMENT_INTENT_CONFLICT",
        )


def _reserve_budget_tx(conn: psycopg.Connection, intent: PaymentIntent) -> None:
    budget = conn.execute(
        "SELECT amount_limit, amount_reserved, amount_settled FROM ag_payment_budgets "
        "WHERE tenant_id=%s AND task_id=%s AND asset=%s AND chain_id=%s FOR UPDATE",
        (intent.tenant_id, intent.task_id, intent.asset, intent.chain_id),
    ).fetchone()
    if budget is None:
        raise X402Error(
            "no independent asset budget is configured for this deployment",
            code="NO_ASSET_BUDGET",
        )
    limit, reserved, settled = budget
    amount = Decimal(intent.asset_amount)
    if reserved + settled + amount > limit:
        raise X402Error("independent asset budget exceeded", code="ASSET_BUDGET_EXCEEDED")
    updated = conn.execute(
        "UPDATE ag_payment_budgets SET amount_reserved = amount_reserved + %s "
        "WHERE tenant_id=%s AND task_id=%s AND asset=%s AND chain_id=%s",
        (amount, intent.tenant_id, intent.task_id, intent.asset, intent.chain_id),
    )
    if updated.rowcount != 1:
        raise X402Error("asset budget reservation failed", code="NO_ASSET_BUDGET")


def load_authorization_material(
    dsn: str,
    operation_id: str,
    *,
    connector: Callable[..., psycopg.Connection] | None = None,
) -> tuple[bytes, bytes, str] | None:
    """The exact persisted authorization material, before any retry.

    Returns ``(authorization_json, payload_json, payload_sha256)`` or ``None``
    when nothing was persisted yet. The bytes are returned verbatim because the
    retry must transmit the identical document, never a re-signed one.
    """
    with _connect(dsn, connector) as conn:
        row = conn.execute(
            "SELECT authorization_json, payload_json, payload_sha256 "
            "FROM ag_payment_states WHERE operation_id=%s",
            (operation_id,),
        ).fetchone()
    if row is None or row[1] is None or row[0] is None or row[2] is None:
        return None
    return bytes(row[0]), bytes(row[1]), row[2]


def fetch_intent_row(conn: psycopg.Connection, operation_id: str):
    return conn.execute(_SELECT_INTENT, (operation_id,)).fetchone()


def _intent_row_matches(
    row, *, operation, action_id: str, intent: PaymentIntent, amount_fen: int
) -> bool:
    (
        operation_id,
        tenant_id,
        task_id,
        grant_id,
        root_grant_id,
        row_action_id,
        payment_digest,
        tool_id,
        idempotency_key,
        profile,
        scheme,
        transfer_method,
        network,
        chain_id,
        asset,
        asset_name,
        asset_version,
        asset_amount,
        pay_to,
        resource_url,
        row_amount_fen,
        quote_id,
        quote_version,
        valid_before,
    ) = row
    return (
        operation_id == operation.operation_id
        and tenant_id == intent.tenant_id
        and task_id == intent.task_id
        and grant_id == intent.grant_id
        and root_grant_id == intent.root_grant_id
        and row_action_id == action_id
        and payment_digest == intent.digest
        and tool_id == intent.tool_id
        and idempotency_key == intent.idempotency_key
        and profile == "AG-X402-PAYMENT-INTENT-1"
        and scheme == "exact"
        and transfer_method == "eip3009"
        and network == intent.network
        and chain_id == intent.chain_id
        and asset == intent.asset
        and asset_name == intent.asset_name
        and asset_version == intent.asset_version
        and str(asset_amount) == intent.asset_amount
        and pay_to == intent.pay_to
        and resource_url == intent.resource_url
        and row_amount_fen == amount_fen
        and quote_id == intent.quote_id
        and quote_version == intent.quote_version
        and valid_before == intent.valid_before
    )


# ------------------------------------------------------------------- reads


def load_payment(
    dsn: str,
    operation_id: str,
    *,
    connector: Callable[..., psycopg.Connection] | None = None,
) -> PaymentRecord:
    with _connect(dsn, connector) as conn:
        row = conn.execute(_SELECT_INTENT, (operation_id,)).fetchone()
        if row is None:
            raise X402Error("no payment intent for operation", code="PAYMENT_NOT_FOUND")
        state = conn.execute(_SELECT_STATE, (operation_id,)).fetchone()
        if state is None:
            raise X402Error("payment intent has no state", code="PAYMENT_STATE_MISSING")
    return _record(row, state)


def load_payment_tx(conn: psycopg.Connection, operation_id: str) -> PaymentRecord:
    row = conn.execute(_SELECT_INTENT, (operation_id,)).fetchone()
    if row is None:
        raise X402Error("no payment intent for operation", code="PAYMENT_NOT_FOUND")
    state = conn.execute(_SELECT_STATE, (operation_id,)).fetchone()
    if state is None:
        raise X402Error("payment intent has no state", code="PAYMENT_STATE_MISSING")
    return _record(row, state)


def _record(row, state) -> PaymentRecord:
    (
        operation_id,
        tenant_id,
        task_id,
        grant_id,
        root_grant_id,
        _action_id,
        payment_digest,
        tool_id,
        idempotency_key,
        _profile,
        _scheme,
        _transfer_method,
        network,
        chain_id,
        asset,
        asset_name,
        asset_version,
        asset_amount,
        pay_to,
        resource_url,
        amount_fen,
        quote_id,
        quote_version,
        valid_before,
    ) = row
    intent = PaymentIntent(
        tenant_id=tenant_id,
        task_id=task_id,
        grant_id=grant_id,
        root_grant_id=root_grant_id,
        tool_id=tool_id,
        idempotency_key=idempotency_key,
        quote_id=quote_id,
        quote_version=quote_version,
        amount_fen=amount_fen,
        network=network,
        chain_id=chain_id,
        asset=asset,
        asset_name=asset_name,
        asset_version=asset_version,
        asset_amount=str(asset_amount),
        pay_to=pay_to,
        resource_url=resource_url,
        valid_before=valid_before,
        digest=payment_digest,
    )
    return PaymentRecord(
        intent=intent,
        operation_id=operation_id,
        status=PaymentStatus(state[0]),
        nonce=state[1],
        payload_sha256=state[2],
        tx_hash=state[3],
        failure_code=state[4],
        authorized_at=state[5],
        submitted_at=state[6],
        settled_at=state[7],
    )


# --------------------------------------------------------------- transitions


def authorize(
    dsn: str,
    *,
    operation_id: str,
    nonce: str,
    authorization_json: bytes,
    payload_json: bytes,
    payload_sha256: str,
    connector: Callable[..., psycopg.Connection] | None = None,
) -> PaymentRecord:
    """Persist authorization material before any network call.

    The first writer wins; a concurrent or repeated call must present the
    identical payload hash or it is refused instead of producing a second
    authorization for the same operation.
    """
    with _connect(dsn, connector) as conn:
        with conn.transaction():
            current = _select_state_for_update(conn, operation_id)
            if current.payload_sha256 is not None:
                if current.payload_sha256 != payload_sha256:
                    raise X402Error(
                        "operation already carries different payment material",
                        code="PAYMENT_STATE_CONFLICT",
                    )
                return load_payment_tx(conn, operation_id)
            if current.status not in (PaymentStatus.UNPAID.value, PaymentStatus.UNKNOWN.value):
                raise X402Error(
                    f"illegal payment transition {current.status} -> AUTHORIZED",
                    code="PAYMENT_STATE_CONFLICT",
                )
            row = conn.execute(
                "UPDATE ag_payment_states SET status='AUTHORIZED', nonce=%s, "
                "authorization_json=%s, payload_json=%s, payload_sha256=%s, "
                "authorized_at=clock_timestamp(), updated_at=clock_timestamp() "
                "WHERE operation_id=%s AND payload_sha256 IS NULL RETURNING operation_id",
                (nonce, authorization_json, payload_json, payload_sha256, operation_id),
            ).fetchone()
            if row is None:
                raise X402Error(
                    "concurrent payment authorization conflict",
                    code="PAYMENT_STATE_CONFLICT",
                )
            return load_payment_tx(conn, operation_id)


def mark_submitting(
    dsn: str,
    *,
    operation_id: str,
    connector: Callable[..., psycopg.Connection] | None = None,
) -> PaymentRecord:
    return _transition(
        dsn,
        operation_id=operation_id,
        allowed=(PaymentStatus.AUTHORIZED.value, PaymentStatus.UNKNOWN.value),
        target="SUBMITTING",
        extra_sets="submitted_at=clock_timestamp()",
        connector=connector,
    )


def mark_unknown(
    dsn: str,
    *,
    operation_id: str,
    failure_code: str,
    connector: Callable[..., psycopg.Connection] | None = None,
) -> PaymentRecord:
    """Keep the reservation and the authorization; record uncertainty."""
    with _connect(dsn, connector) as conn:
        with conn.transaction():
            current = _select_state_for_update(conn, operation_id)
            if current.status in (PaymentStatus.SETTLED.value, PaymentStatus.FAILED.value):
                return load_payment_tx(conn, operation_id)
            if current.status != PaymentStatus.UNKNOWN.value:
                conn.execute(
                    "UPDATE ag_payment_states SET status='UNKNOWN', failure_code=%s, "
                    "updated_at=clock_timestamp() WHERE operation_id=%s",
                    (failure_code, operation_id),
                )
            return load_payment_tx(conn, operation_id)


def mark_settled(
    dsn: str,
    *,
    operation_id: str,
    tx_hash: str,
    connector: Callable[..., psycopg.Connection] | None = None,
) -> PaymentRecord:
    """Terminal confirmation: move the private asset reservation to settled."""
    return _transition(
        dsn,
        operation_id=operation_id,
        allowed=(
            PaymentStatus.SUBMITTING.value,
            PaymentStatus.UNKNOWN.value,
            PaymentStatus.AUTHORIZED.value,
        ),
        target="SETTLED",
        extra_sets="tx_hash=%s, settled_at=clock_timestamp()",
        extra_args=(tx_hash,),
        budget="settle",
        connector=connector,
    )


def mark_failed(
    dsn: str,
    *,
    operation_id: str,
    failure_code: str,
    connector: Callable[..., psycopg.Connection] | None = None,
) -> PaymentRecord:
    """Terminal refusal with proven absence of transfer: release the reservation."""
    return _transition(
        dsn,
        operation_id=operation_id,
        allowed=(
            PaymentStatus.UNPAID.value,
            PaymentStatus.AUTHORIZED.value,
            PaymentStatus.SUBMITTING.value,
            PaymentStatus.UNKNOWN.value,
        ),
        target="FAILED",
        extra_sets="failure_code=%s",
        extra_args=(failure_code,),
        budget="release",
        connector=connector,
    )


def _select_state_for_update(conn: psycopg.Connection, operation_id: str):
    intent = conn.execute(
        "SELECT operation_id FROM ag_payment_intents WHERE operation_id=%s", (operation_id,)
    ).fetchone()
    if intent is None:
        raise X402Error("no payment intent for operation", code="PAYMENT_NOT_FOUND")
    row = conn.execute(
        "SELECT status,nonce,payload_sha256,failure_code FROM ag_payment_states "
        "WHERE operation_id=%s FOR UPDATE",
        (operation_id,),
    ).fetchone()
    if row is None:
        raise X402Error("payment intent has no state", code="PAYMENT_STATE_MISSING")
    return _StateView(*row)


@dataclass
class _StateView:
    status: str
    nonce: str | None
    payload_sha256: str | None
    failure_code: str | None


def _transition(
    dsn: str,
    *,
    operation_id: str,
    allowed: tuple[str, ...],
    target: str,
    extra_sets: str,
    extra_args: tuple = (),
    budget: str | None = None,
    connector: Callable[..., psycopg.Connection] | None = None,
) -> PaymentRecord:
    with _connect(dsn, connector) as conn:
        with conn.transaction():
            current = _select_state_for_update(conn, operation_id)
            if current.status == target:
                return load_payment_tx(conn, operation_id)
            if current.status not in allowed:
                raise X402Error(
                    f"illegal payment transition {current.status} -> {target}",
                    code="PAYMENT_STATE_CONFLICT",
                )
            params = (*extra_args, operation_id)
            updated = conn.execute(
                f"UPDATE ag_payment_states SET status=%s, {extra_sets}, "
                "updated_at=clock_timestamp() WHERE operation_id=%s AND status=%s "
                "RETURNING operation_id",
                (target, *params, current.status),
            ).fetchone()
            if updated is None:
                raise X402Error(
                    "concurrent payment transition conflict", code="PAYMENT_STATE_CONFLICT"
                )
            if budget is not None:
                _adjust_budget_tx(conn, operation_id=operation_id, mode=budget)
            return load_payment_tx(conn, operation_id)


def _adjust_budget_tx(conn: psycopg.Connection, *, operation_id: str, mode: str) -> None:
    intent = conn.execute(
        "SELECT tenant_id,task_id,asset,chain_id,asset_amount FROM ag_payment_intents "
        "WHERE operation_id=%s",
        (operation_id,),
    ).fetchone()
    if intent is None:
        raise X402Error("no payment intent for operation", code="PAYMENT_NOT_FOUND")
    tenant_id, task_id, asset, chain_id, amount = intent
    if mode == "settle":
        changed = conn.execute(
            "UPDATE ag_payment_budgets SET amount_reserved = amount_reserved - %s, "
            "amount_settled = amount_settled + %s WHERE tenant_id=%s AND task_id=%s "
            "AND asset=%s AND chain_id=%s AND amount_reserved >= %s",
            (amount, amount, tenant_id, task_id, asset, chain_id, amount),
        )
    elif mode == "release":
        changed = conn.execute(
            "UPDATE ag_payment_budgets SET amount_reserved = amount_reserved - %s "
            "WHERE tenant_id=%s AND task_id=%s AND asset=%s AND chain_id=%s "
            "AND amount_reserved >= %s",
            (amount, tenant_id, task_id, asset, chain_id, amount),
        )
    else:  # pragma: no cover - defensive
        raise X402Error("unknown budget adjustment")
    if changed.rowcount != 1:
        raise X402Error("asset budget adjustment failed", code="ASSET_BUDGET_CONFLICT")


def new_operation_nonce() -> str:
    """A fresh opaque nonce for the payment authorization of one operation."""
    return "0x" + secrets.token_bytes(32).hex()
