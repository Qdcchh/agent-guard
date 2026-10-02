"""A2.1 correction-r2 regressions: residual and new r3 boundaries.

Formal rejection tests for the issues still open after review-r3:
A21-R1-OUTCOME, A21-R1-CANDIDATE, A21-R2-SNAPSHOT, A21-R1-LEGACY (residual),
A21-R1-EVENT (residual), A21-R3-UNKNOWN, A21-R3-TESTSYNC.

Every case is a *requirement* assertion, not a copy of any observation log:
the dangerous behaviour must be refused and must leave the budget reserved,
no outbox row and no downstream effect beyond what already existed.
"""

from __future__ import annotations

import dataclasses
import json
import os
import threading
import time
from pathlib import Path

import psycopg
import pytest

from agent_guard.contracts.execution import (
    ExecutionError,
    ExecutionErrorCode,
    OperationStatus,
    TerminalAction,
    ToolId,
)
from agent_guard.contracts.ledger import TrustedCost
from agent_guard.execution import receipts
from agent_guard.execution import store as exec_store
from agent_guard.ledger import store as ledger_store
from agent_guard.ledger.migrate import DEFAULT_MIGRATIONS_DIR, apply_migrations
from agent_guard.tools.catalog import snapshot_from_bytes, snapshot_to_bytes
from tests.fixtures.dbstate import fetch_counters, fetch_counts
from tests.fixtures.execution import (
    ORDER_AMOUNT_FEN,
    REQUEST_ID,
    build_env,
    constraints_for,
    document_params,
    make_reference_operation,
    notification_params,
    order_params,
    read_params,
)
from tests.fixtures.isolation import create_scratch_database, drop_scratch_database
from tests.fixtures.state import build_tree

pytestmark = pytest.mark.integration

ROUNDS = 10


def _effects(dsn) -> dict[str, int]:
    with psycopg.connect(dsn) as conn:
        return {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("ds_operations", "ds_orders", "ds_notifications")
        }


def _accepted(a2, key: str = "r3"):
    return a2.service.accept_invocation(
        a2.tree.invocation(
            idempotency_key=key, tool_id="procurement.order.create", params=order_params()
        ),
        a2.permission(),
    )


class _FixedPort:
    """Port double returning one deliberately mutated downstream record."""

    def __init__(self, value):
        self.value = value

    def execute(self, **kwargs):
        return self.value

    def query(self, **kwargs):
        return self.value


# ---------------------------------------------------------- A21-R1-OUTCOME


def _mutate_order_result(a2, operation_id, mutation):
    row = a2.service.load_operation(operation_id)
    value = a2.downstream.execute(
        service_secret=a2.secret,
        operation_id=operation_id,
        tool_id=ToolId.ORDER_CREATE,
        canonical_params=row.canonical_params,
        quote=snapshot_from_bytes(row.quote_snapshot),
        expected_amount_fen=row.amount_fen,
    )
    result = json.loads(value.result_bytes)
    if mutation == "effect-id":
        result["order_id"] = "order-other"
    elif mutation == "missing-fields":
        result = {"kind": "order", "operation_id": operation_id}
    elif mutation == "wrong-total":
        result["total_fen"] = 1
    elif mutation == "bool-total":
        result["total_fen"] = True
    elif mutation == "wrong-supplier":
        result["supplier_id"] = "supplier-other"
    elif mutation == "wrong-quote":
        result["quote_version"] = "9"
    elif mutation == "wrong-items":
        result["items"][0]["quantity"] = 2
    elif mutation == "unknown":
        result["unknown_security"] = True
    elif mutation == "refusal-tool":
        result = {
            "kind": "refusal",
            "operation_id": operation_id,
            "tool_id": ToolId.NOTIFICATION_SEND.value,
            "reason": "not this tool",
        }
        value = dataclasses.replace(value, final_rejection=True, effect_ref=None, amount_fen=0)
    elif mutation == "typed-quote-bool":
        item = dataclasses.replace(value.quote.items[0], quantity=True)
        value = dataclasses.replace(value, quote=dataclasses.replace(value.quote, items=(item,)))
    raw = json.dumps(result, separators=(",", ":")).encode()
    if mutation == "duplicate":
        raw = raw[:-1] + b',"operation_id":"' + operation_id.encode() + b'"}'
    if mutation == "deep-result":
        raw = (
            b'{"kind":"order","operation_id":"'
            + operation_id.encode()
            + b'","unknown":'
            + b"[" * 1500
            + b"0"
            + b"]" * 1500
            + b"}"
        )
    return dataclasses.replace(value, result_bytes=raw)


@pytest.mark.parametrize("entry", ["execute", "query"])
@pytest.mark.parametrize(
    "mutation",
    [
        "effect-id",
        "missing-fields",
        "wrong-total",
        "bool-total",
        "wrong-supplier",
        "wrong-quote",
        "wrong-items",
        "duplicate",
        "unknown",
        "refusal-tool",
        "typed-quote-bool",
        "deep-result",
    ],
)
def test_order_result_must_fully_bind_the_accepted_facts(a2, entry, mutation):
    """A21-R1-OUTCOME: a record that is not exactly the accepted order keeps
    UNKNOWN. Nothing may settle or release from untrustworthy material."""
    operation_id = _accepted(a2, f"r3-order-{mutation}").operation_id
    value = _mutate_order_result(a2, operation_id, mutation)
    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        downstream=_FixedPort(value),
    )
    result = (
        env.service.run_operation(operation_id, owner_token="r3-order")
        if entry == "execute"
        else env.service.reconcile(operation_id, owner_token="r3-order")
    )
    assert result.status == OperationStatus.UNKNOWN.value, (entry, mutation)
    assert result.action is None
    assert env.service.outbox_entry(operation_id) is None
    for grant_id in (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id):
        counters = fetch_counters(a2.gateway_dsn, grant_id)
        assert counters["amount_reserved"] == ORDER_AMOUNT_FEN
        assert counters["amount_settled"] == 0
        assert counters["calls_reserved"] == 1
        assert counters["calls_settled"] == 0


def test_wrong_tool_refusal_never_releases_an_operation_with_an_effect(a2):
    """A21-R1-OUTCOME: a refusal record for another tool proves nothing about
    this operation and must not release an order that already exists."""
    operation_id = _accepted(a2, "r3-refusal-tool").operation_id
    row = a2.service.load_operation(operation_id)
    # the real downstream has already created an order for this key
    a2.downstream.execute(
        service_secret=a2.secret,
        operation_id=operation_id,
        tool_id=ToolId.ORDER_CREATE,
        canonical_params=row.canonical_params,
        quote=snapshot_from_bytes(row.quote_snapshot),
        expected_amount_fen=row.amount_fen,
    )
    assert _effects(a2.downstream_dsn)["ds_orders"] == 1

    refusal = {
        "kind": "refusal",
        "operation_id": operation_id,
        "tool_id": ToolId.NOTIFICATION_SEND.value,
        "reason": "not this tool",
    }
    value = dataclasses.replace(
        a2.downstream.query(service_secret=a2.secret, operation_id=operation_id),
        result_bytes=json.dumps(refusal, separators=(",", ":")).encode(),
        final_rejection=True,
        effect_ref=None,
        amount_fen=0,
    )
    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        downstream=_FixedPort(value),
    )
    result = env.service.run_operation(operation_id, owner_token="r3-refusal-tool")
    assert result.status == OperationStatus.UNKNOWN.value
    assert result.action is None
    assert env.service.outbox_entry(operation_id) is None
    assert _effects(a2.downstream_dsn)["ds_orders"] == 1
    counters = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    assert counters["amount_reserved"] == ORDER_AMOUNT_FEN
    assert counters["amount_settled"] == 0


@pytest.mark.parametrize("entry", ["execute", "query"])
@pytest.mark.parametrize("tool", ["read", "document", "notification"])
def test_other_tool_results_must_fully_bind(a2, entry, tool):
    """A21-R1-OUTCOME: notification/read records are bound field by field."""
    if tool == "notification":
        target = make_reference_operation(a2, key=f"r3-note-{entry}", settle=True)
        params = notification_params(operation_id=target)
        tool_id = ToolId.NOTIFICATION_SEND
    elif tool == "read":
        params, tool_id = read_params(), ToolId.REQUEST_READ
    else:
        params, tool_id = document_params(), ToolId.DOCUMENT_READ

    operation_id = a2.service.accept_invocation(
        a2.tree.invocation(
            idempotency_key=f"r3-other-{tool}-{entry}",
            tool_id=tool_id.value,
            params=params,
        ),
        a2.permission(),
    ).operation_id
    value = a2.downstream.execute(
        service_secret=a2.secret,
        operation_id=operation_id,
        tool_id=tool_id,
        canonical_params=params,
        quote=None,
        expected_amount_fen=0,
    )
    obj = json.loads(value.result_bytes)
    if tool == "notification":
        obj.update(
            notification_id="different-effect",
            recipient_id="other-recipient",
            template_id="other-template",
        )
    else:
        obj["tool_id"] = ToolId.ORDER_CREATE.value
    value = dataclasses.replace(value, result_bytes=json.dumps(obj).encode())

    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        downstream=_FixedPort(value),
    )
    result = (
        env.service.run_operation(operation_id, owner_token="r3-other")
        if entry == "execute"
        else env.service.reconcile(operation_id, owner_token="r3-other")
    )
    assert result.status == OperationStatus.UNKNOWN.value, (tool, entry)
    assert env.service.outbox_entry(operation_id) is None


def test_valid_order_result_still_settles(a2):
    """A21-R1-OUTCOME: the positive control keeps working with the strict schema."""
    operation_id = _accepted(a2, "r3-order-ok").operation_id
    result = a2.service.run_operation(operation_id, owner_token="r3-order-ok")
    assert result.status == OperationStatus.SUCCEEDED.value
    assert result.action is TerminalAction.SETTLE
    outbox = a2.service.outbox_entry(operation_id)
    assert outbox["receipt_status"] == "PENDING"


def test_valid_notification_and_read_results_still_settle(a2):
    """A21-R1-OUTCOME: positive control for the zero-amount tools."""
    target = make_reference_operation(a2, key="r3-note-ok", settle=True)
    note = a2.service.accept_invocation(
        a2.tree.invocation(
            idempotency_key="r3-note-ok",
            tool_id="notification.template.send",
            params=notification_params(operation_id=target),
        ),
        a2.permission(),
    ).operation_id
    assert a2.service.run_operation(note, owner_token="r3-note-ok").status == "SUCCEEDED"

    read = a2.service.accept_invocation(
        a2.tree.invocation(
            idempotency_key="r3-read-ok",
            tool_id="procurement.request.read",
            params=read_params(),
        ),
        a2.permission(),
    ).operation_id
    assert a2.service.run_operation(read, owner_token="r3-read-ok").status == "SUCCEEDED"


# --------------------------------------------------------- A21-R1-CANDIDATE


@pytest.mark.parametrize("entry", ["run", "reconcile", "candidate", "fallback"])
@pytest.mark.parametrize("mismatch", ["params-quote-id", "params-quote-version"])
def test_params_quote_identity_binds_cost_and_snapshot(a2, monkeypatch, entry, mismatch):
    """A21-R1-CANDIDATE: params <-> cost columns <-> snapshot must agree.

    An operation accepted with params naming a different quote identity than
    its own cost/snapshot is unusable at every entry and is quarantined, not
    served as ``EXISTING`` and not executed.
    """
    params_obj = json.loads(order_params())
    params_obj["quote_id" if mismatch.endswith("id") else "quote_version"] = (
        "quote-other" if mismatch.endswith("id") else "2"
    )
    raw = json.dumps(params_obj, separators=(",", ":")).encode()
    snap = a2.catalog.build_order_snapshot(
        tenant_id=a2.tree.tenant_id,
        task_id=a2.tree.task_id,
        request_id="req-001",
        quote_id="quote-001",
        quote_version="1",
        items=(("sku-001", 1),),
        delivery_id="office-001",
    )
    inv = a2.tree.invocation(
        idempotency_key="r3-candidate",
        tool_id=ToolId.ORDER_CREATE.value,
        params=raw,
    )
    operation_id = a2.ledger.accept(
        inv,
        TrustedCost(
            amount_fen=70000,
            quote_id="quote-001",
            quote_version="1",
            quote_snapshot=snapshot_to_bytes(snap),
        ),
    ).operation_id
    permission = a2.permission(
        chain=tuple(
            constraints_for(
                i, quote_versions=(params_obj["quote_id"] + "@" + params_obj["quote_version"],)
            )
            for i in range(3)
        )
    )
    a2.catalog.remove_quote("quote-001", "1")
    before = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    error = None

    if entry == "fallback":
        original = a2.service._find_candidate
        lookups: list[bool] = []

        def candidate(verified, _orig=original, _calls=lookups):
            _calls.append(True)
            return None if len(_calls) == 1 else _orig(verified)

        monkeypatch.setattr(a2.service, "_find_candidate", candidate)

    try:
        if entry in ("candidate", "fallback"):
            a2.service.accept_invocation(
                a2.tree.invocation(
                    idempotency_key="r3-candidate",
                    tool_id=ToolId.ORDER_CREATE.value,
                    params=raw,
                ),
                permission,
            )
        elif entry == "run":
            a2.service.run_operation(operation_id, owner_token="r3-cand")
        else:
            a2.service.reconcile(operation_id, owner_token="r3-cand")
    except ExecutionError as exc:
        error = exc.code.value

    assert error == ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID.value, (entry, mismatch, error)
    assert a2.service.review_flag(operation_id) is not None
    assert a2.service.operation_status(operation_id) == "RESERVED"
    assert fetch_counters(a2.gateway_dsn, a2.tree.root_id) == before
    assert _effects(a2.downstream_dsn)["ds_operations"] == 0


def test_consistent_params_cost_and_snapshot_are_accepted(a2):
    """A21-R1-CANDIDATE: the positive control binds all three and still works."""
    operation_id = _accepted(a2, "r3-cand-ok").operation_id
    retried = a2.service.accept_invocation(
        a2.tree.invocation(
            idempotency_key="r3-cand-ok",
            jti="jti-r3-cand-ok-retry",
            tool_id="procurement.order.create",
            params=order_params(),
        ),
        a2.permission(),
    )
    assert retried.disposition.value == "EXISTING"
    assert retried.operation_id == operation_id
    assert a2.service.review_flag(operation_id) is None


# --------------------------------------------------------- A21-R2-SNAPSHOT


@pytest.mark.parametrize(
    "mutation",
    [
        "version-zero",
        "version-leading-zero",
        "version-text",
        "id-url",
        "id-control",
        "id-long",
        "id-empty",
        "supplier-url",
    ],
)
def test_stored_snapshot_identity_schema_refuses(mutation):
    """A21-R2-SNAPSHOT: persisted identity follows the exact id/version rules."""
    raw = (
        b'{"quote_id":"quote-001","quote_version":"1","supplier_id":"supplier-001",'
        b'"items":[{"sku":"sku-001","quantity":1,"unit_price_fen":70000}],'
        b'"total_fen":70000,"currency":"CNY"}'
    )
    obj = json.loads(raw)
    if mutation.startswith("version"):
        obj["quote_version"] = {
            "version-zero": "0",
            "version-leading-zero": "01",
            "version-text": "version-x",
        }[mutation]
    elif mutation == "supplier-url":
        obj["supplier_id"] = "https://untrusted.test/path"
    elif mutation == "id-empty":
        obj["quote_id"] = ""
    else:
        obj["supplier_id"] = {
            "id-url": "https://untrusted.test/path",
            "id-control": "bad\nidentity",
            "id-long": "x" * 129,
        }[mutation]
    with pytest.raises(ExecutionError) as excinfo:
        snapshot_from_bytes(json.dumps(obj).encode())
    assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID


def test_stored_snapshot_deep_payload_maps_to_the_safe_error():
    """A21-R2-SNAPSHOT: over-deep JSON never escapes as ``RecursionError``."""
    raw = b'{"unknown":' + b"[" * 1500 + b"0" + b"]" * 1500 + b"}"
    with pytest.raises(ExecutionError) as excinfo:
        snapshot_from_bytes(raw)
    assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID


@pytest.mark.parametrize("entry", ["run", "reconcile", "candidate"])
def test_deep_legacy_snapshot_is_durably_quarantined(a2, entry):
    """A21-R2-SNAPSHOT/LEGACY: a malformed deep snapshot is isolated at every
    entry, with the budget preserved and nothing executed."""
    params = order_params()
    raw = b'{"unknown":' + b"[" * 1500 + b"0" + b"]" * 1500 + b"}"
    inv = a2.tree.invocation(
        idempotency_key="deep-old", tool_id=ToolId.ORDER_CREATE.value, params=params
    )
    operation_id = a2.ledger.accept(
        inv,
        TrustedCost(amount_fen=70000, quote_id="quote-001", quote_version="1", quote_snapshot=raw),
    ).operation_id
    error = None
    try:
        if entry == "run":
            a2.service.run_operation(operation_id, owner_token="deep-old")
        elif entry == "reconcile":
            a2.service.reconcile(operation_id, owner_token="deep-old")
        else:
            a2.service.accept_invocation(
                a2.tree.invocation(
                    idempotency_key="deep-old",
                    tool_id=ToolId.ORDER_CREATE.value,
                    params=params,
                ),
                a2.permission(),
            )
    except Exception as exc:  # noqa: BLE001 - the type itself is asserted below
        error = type(exc).__name__
    assert error is not None, entry
    assert a2.service.review_flag(operation_id) is not None, entry
    assert _effects(a2.downstream_dsn)["ds_operations"] == 0
    for grant_id in (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id):
        counters = fetch_counters(a2.gateway_dsn, grant_id)
        assert counters["amount_reserved"] == 70000
        assert counters["amount_settled"] == 0


# ----------------------------------------------------------- A21-R1-EVENT


def _seed_short_event(a2, namespace, tmp_path, phase):
    """Build a pre-006 database whose committed event is deliberately short."""
    db = create_scratch_database(namespace.base_dsn)
    subset = tmp_path / f"pre006-{phase}"
    subset.mkdir()
    # 005's deferred completeness trigger would refuse a short event, so the
    # legacy shape is written on a pre-005 database and then upgraded
    for name in (
        "001_init.sql",
        "002_root_invariants.sql",
        "003_root_delete_guard.sql",
        "004_execution_lifecycle.sql",
    ):
        (subset / name).write_bytes((DEFAULT_MIGRATIONS_DIR / name).read_bytes())
    with psycopg.connect(db.dsn) as conn:
        apply_migrations(conn, subset)
        tree = build_tree(conn)
    env = build_env(tree=tree, gateway_dsn=db.dsn, downstream_dsn=a2.downstream_dsn)
    snap = env.catalog.build_order_snapshot(
        tenant_id=tree.tenant_id,
        task_id=tree.task_id,
        request_id="req-001",
        quote_id="quote-001",
        quote_version="1",
        items=(("sku-001", 1),),
        delivery_id="office-001",
    )
    operation_id = f"r3-short-{phase}"
    with psycopg.connect(db.dsn) as conn:
        with conn.transaction():
            ledger_store.insert_operation(
                conn,
                operation_id=operation_id,
                tenant_id=tree.tenant_id,
                task_id=tree.task_id,
                tool_id=ToolId.ORDER_CREATE.value,
                idempotency_key=operation_id,
                grant_id=tree.leaf_id,
                holder_client_id=tree.executor[0],
                holder_kid=tree.executor[1],
                tool_version="1",
                canonical_params=order_params(),
                currency="CNY",
                amount_fen=70000,
                calls=1,
                quote_id="quote-001",
                quote_version="1",
                quote_snapshot=snapshot_to_bytes(snap),
                token_digest="synthetic",
                proof_digest="synthetic",
                intent_digest="synthetic",
                evidence_ref="synthetic",
            )
            nodes = [tree.root_id, tree.mid_id, tree.leaf_id]
            for grant_id in nodes:
                ledger_store.apply_reservation(conn, grant_id, 70000, 1)
            # deliberately ONE node instead of the full path
            ledger_store.insert_reserve_event(
                conn,
                operation_id=operation_id,
                seq=0,
                nodes=[(0, tree.root_id, 70000, 1)],
            )
            if phase == "SETTLE":
                from agent_guard.contracts.execution import TerminalAction

                exec_store.transition_status(
                    conn,
                    operation_id=operation_id,
                    from_status="RESERVED",
                    to_status="EXECUTING",
                )
                grants = ledger_store.load_path(conn, tree.leaf_id)
                deltas = exec_store.terminal_node_deltas(grants, TerminalAction.SETTLE, 70000, 1)
                exec_store.apply_terminal_counters(conn, deltas)
                exec_store.insert_terminal_event(
                    conn, operation_id=operation_id, action=TerminalAction.SETTLE, nodes=deltas[:1]
                )
                reserve = exec_store.fetch_event_nodes(conn, operation_id)[0]
                changes = receipts.ledger_changes_bytes(
                    operation_id=operation_id,
                    reserve_event=reserve,
                    terminal_nodes=deltas[:1],
                    terminal_action=TerminalAction.SETTLE,
                )
                exec_store.insert_pending_receipt(
                    conn,
                    receipts.build_pending_receipt(
                        operation=exec_store.fetch_operation(conn, operation_id),
                        action=TerminalAction.SETTLE,
                        root_grant_id=tree.root_id,
                        result_bytes=b"{}",
                        ledger_changes=changes,
                        created_at=conn.execute("SELECT clock_timestamp()").fetchone()[0],
                    ),
                )
                exec_store.transition_status(
                    conn,
                    operation_id=operation_id,
                    from_status="EXECUTING",
                    to_status="SUCCEEDED",
                )
    return db, env, tree, operation_id


@pytest.mark.parametrize("phase", ["RESERVE", "SETTLE"])
def test_pre006_committed_short_event_cannot_be_patched(a2, namespace, tmp_path, phase):
    """A21-R1-EVENT: an already committed event keeps its node set for ever,
    even when the patching rows look perfectly well formed."""
    db, env, tree, operation_id = _seed_short_event(a2, namespace, tmp_path, phase)
    try:
        with psycopg.connect(db.dsn) as conn:
            assert apply_migrations(conn) == ["005", "006"]
        box = env.service.outbox_entry(operation_id)
        with psycopg.connect(db.dsn) as conn:
            event_id = conn.execute(
                "SELECT event_id FROM ag_ledger_events WHERE operation_id = %s AND phase = %s",
                (operation_id, phase),
            ).fetchone()[0]
        refused = []
        for index, grant_id in enumerate((tree.mid_id, tree.leaf_id), start=1):
            with psycopg.connect(db.dsn) as conn:
                with pytest.raises(psycopg.errors.CheckViolation):
                    with conn.transaction():
                        conn.execute(
                            "INSERT INTO ag_ledger_event_nodes "
                            "(event_id, position, grant_id, amount_reserved_delta, "
                            " amount_settled_delta, calls_reserved_delta, calls_settled_delta) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (
                                event_id,
                                index,
                                grant_id,
                                70000 if phase == "RESERVE" else -70000,
                                0 if phase == "RESERVE" else 70000,
                                1 if phase == "RESERVE" else -1,
                                0 if phase == "RESERVE" else 1,
                            ),
                        )
            refused.append(index)

        with psycopg.connect(db.dsn) as conn:
            count = conn.execute(
                "SELECT count(*) FROM ag_ledger_event_nodes WHERE event_id = %s", (event_id,)
            ).fetchone()[0]
        assert count == 1, f"{phase}: history was patched"
        assert len(refused) == 2
        assert env.service.outbox_entry(operation_id) == box
        # the short material is isolated at runtime and never repaired
        assert env.service.quarantine_if_insufficient(operation_id) is True
    finally:
        drop_scratch_database(namespace.base_dsn, db)


def test_fresh_full_node_set_still_writes_in_one_transaction(a2):
    """A21-R1-EVENT: the seal must not block a legitimate first write."""
    operation_id = _accepted(a2, "r3-seal-ok").operation_id
    result = a2.service.run_operation(operation_id, owner_token="r3-seal-ok")
    assert result.status == OperationStatus.SUCCEEDED.value
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_event_nodes"] == 6
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 1
    with psycopg.connect(a2.gateway_dsn) as conn:
        seals = conn.execute("SELECT count(*) FROM ag_event_seals").fetchone()[0]
    assert seals == 2


def test_seal_rows_cannot_be_forged_or_removed(a2):
    """A21-R1-EVENT: the seal is a database fact, not a client boolean."""
    operation_id = _accepted(a2, "r3-seal-forge").operation_id
    a2.service.run_operation(operation_id, owner_token="r3-seal-forge")
    with psycopg.connect(a2.gateway_dsn) as conn:
        event_id = conn.execute(
            "SELECT event_id FROM ag_ledger_events WHERE operation_id = %s AND phase = 'RESERVE'",
            (operation_id,),
        ).fetchone()[0]
    for sql, params in (
        ("UPDATE ag_event_seals SET created_xid = '999' WHERE event_id = %s", (event_id,)),
        ("DELETE FROM ag_event_seals WHERE event_id = %s", (event_id,)),
    ):
        with psycopg.connect(a2.gateway_dsn) as conn:
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    conn.execute(sql, params)
    # a seal cannot be created for an event that already has nodes
    with psycopg.connect(a2.gateway_dsn) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO ag_event_seals (event_id, created_xid) "
                    "VALUES (%s, pg_current_xact_id()::text)",
                    (event_id,),
                )


# ---------------------------------------------------------- A21-R3-UNKNOWN


def _reconcile_none_first(a2, operation_id, owner, monkeypatch, misses=1):
    from agent_guard.tools.downstream import MockDownstream

    class NoneThenReal:
        def __init__(self, inner, limit):
            self.inner = inner
            self.limit = limit
            self.queries = 0

        def execute(self, **kwargs):
            return self.inner.execute(**kwargs)

        def query(self, **kwargs):
            self.queries += 1
            return None if self.queries <= self.limit else self.inner.query(**kwargs)

    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        downstream=NoneThenReal(
            MockDownstream(a2.downstream_dsn, service_secret=a2.secret), misses
        ),
    )
    return env


@pytest.mark.parametrize("round_no", range(ROUNDS))
def test_stale_unknown_claim_never_reports_over_a_terminal_state(a2, monkeypatch, round_no):
    """A21-R3-UNKNOWN: an expired worker must not answer with a cached UNKNOWN
    once another owner reached a terminal state."""
    operation_id = _accepted(a2, f"r3-unknown-{round_no}").operation_id
    env = _reconcile_none_first(a2, operation_id, "first", monkeypatch)
    first = env.service.reconcile(operation_id, owner_token="first")
    assert first.status == OperationStatus.UNKNOWN.value

    from tests.fixtures.execution import expire_lease

    expire_lease(a2.gateway_dsn, operation_id)
    old = a2.service._claim(operation_id, "old")
    expire_lease(a2.gateway_dsn, operation_id)
    new = a2.service.run_operation(operation_id, owner_token="new")
    assert new.status == OperationStatus.SUCCEEDED.value

    error = None
    returned = None
    try:
        returned = a2.service._finalize(old, None, downstream_called=True, reason="query not found")
    except ExecutionError as exc:
        error = exc.code.value
    # either a stable lease/transition error, or the real current terminal state
    assert error in ("LEASE_LOST", "ILLEGAL_TRANSITION") or (
        returned is not None and returned.status == "SUCCEEDED"
    ), (error, returned)
    assert a2.service.operation_status(operation_id) == "SUCCEEDED"
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 1


@pytest.mark.parametrize("entry", ["run", "reconcile"])
def test_public_entries_also_refuse_the_stale_unknown_write(a2, monkeypatch, entry):
    """A21-R3-UNKNOWN: both public entries check the live lease/state."""
    operation_id = _accepted(a2, f"r3-unknown-pub-{entry}").operation_id
    env = _reconcile_none_first(a2, operation_id, "first", monkeypatch)
    assert env.service.reconcile(operation_id, owner_token="first").status == "UNKNOWN"

    from tests.fixtures.execution import expire_lease

    expire_lease(a2.gateway_dsn, operation_id)
    saved: dict = {}

    def capture(claim, outcome, _saved=saved):
        _saved.update(claim=claim, outcome=outcome)
        raise RuntimeError("pause")

    with pytest.raises(RuntimeError, match="pause"):
        a2.service.run_operation(operation_id, owner_token="stale", pause=capture)
    expire_lease(a2.gateway_dsn, operation_id)
    assert a2.service.run_operation(operation_id, owner_token="fresh").status == "SUCCEEDED"

    error = None
    try:
        a2.service._finalize(saved["claim"], None, downstream_called=True, reason="nothing known")
    except ExecutionError as exc:
        error = exc.code.value
    assert error in ("LEASE_LOST", "ILLEGAL_TRANSITION")
    assert a2.service.operation_status(operation_id) == "SUCCEEDED"


def test_normal_unknown_still_keeps_the_budget(a2):
    """A21-R3-UNKNOWN: the legitimate UNKNOWN path is unchanged."""
    operation_id = _accepted(a2, "r3-unknown-ok").operation_id
    env = _reconcile_none_first(a2, operation_id, "first", None)
    result = env.service.reconcile(operation_id, owner_token="first")
    assert result.status == OperationStatus.UNKNOWN.value
    counters = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    assert counters["amount_reserved"] == ORDER_AMOUNT_FEN
    assert counters["amount_settled"] == 0
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 0


# --------------------------------------------------------- A21-R3-TESTSYNC


def test_lock_regression_has_real_terminal_progress(a2, monkeypatch):
    """A21-R3-TESTSYNC: the lock race must produce a complete settle each round
    and must never swallow a thread exception."""
    from tests.integration.test_execution_regressions import (
        test_claim_and_finalize_interleaved_never_deadlock,
    )

    errors: list[str] = []
    real_barrier = threading.Barrier

    class RecordedBarrier:
        def __init__(self, *args, **kwargs):
            self.inner = real_barrier(*args, **kwargs)

        def wait(self, *args, **kwargs):
            try:
                return self.inner.wait(*args, **kwargs)
            except threading.BrokenBarrierError:
                errors.append(threading.current_thread().name)
                raise

    monkeypatch.setattr(threading, "Barrier", RecordedBarrier)
    test_claim_and_finalize_interleaved_never_deadlock(a2, monkeypatch)
    counts = fetch_counts(a2.gateway_dsn)
    assert errors == [], f"BrokenBarrierError was raised in {errors}"
    assert counts["ag_receipt_outbox"] == ROUNDS
    assert counts["ag_ledger_events"] == 2 * ROUNDS
    assert _effects(a2.downstream_dsn)["ds_orders"] == ROUNDS
    assert counts["ag_ledger_event_nodes"] == 6 * ROUNDS


# ------------------------------------------------- A21-R5-P11-EVIDENCE


def _cause_chain(exc) -> list[str]:
    chain: list[str] = []
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        chain.append(type(exc).__name__)
        exc = exc.__cause__ or exc.__context__
    return chain


def test_p11_resource_disappearance_is_deterministic_with_precise_diagnostics(
    a2, monkeypatch, tmp_path
):
    """A21-R5-P11-EVIDENCE: 10+ deterministic rounds of the resource-disappearance
    race, recording the exact error code, cause chain, barrier timing and the
    database facts instead of leaving an unexplained failure behind.

    Nothing here is caught into a pass: any unexpected exception fails the test.
    The historical ``LedgerError`` without a recorded code is *not* claimed to be
    explained by any TTL; only what these rounds actually establish is asserted.
    """
    diagnostics: list[dict] = []
    for round_no in range(10):
        with psycopg.connect(a2.gateway_dsn) as conn:
            tree = build_tree(
                conn,
                root_limit=10_000_000,
                mid_limit=10_000_000,
                leaf_limit=10_000_000,
                root_calls=1000,
                mid_calls=1000,
                leaf_calls=1000,
            )
        env = build_env(tree=tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)
        key = f"p11-diag-{round_no}"
        first = threading.Event()
        committed = threading.Event()
        timeline: dict[str, float] = {}
        original_find = env.service._find_candidate
        lookups: list[bool] = []

        def blocking_find(
            verified, _orig=original_find, _calls=lookups, _t=timeline, _first=first, _go=committed
        ):
            row = _orig(verified)
            _calls.append(row is not None)
            if len(_calls) == 1:
                assert row is None, "the first lookup must miss for this race"
                _t["a_lookup_miss"] = time.monotonic()
                _first.set()
                assert _go.wait(20), "the competing accept never committed"
                _t["a_resumed"] = time.monotonic()
            return row

        monkeypatch.setattr(env.service, "_find_candidate", blocking_find)

        competitor: list[str] = []
        competitor_error: list[str] = []

        def commit_other(
            _first=first,
            _go=committed,
            _t=timeline,
            _key=key,
            _a2=a2,
            _out=competitor,
            _err=competitor_error,
            _env=env,
            _tree=tree,
        ):
            assert _first.wait(20), "the first accept never reached resolution"
            _t["b_start"] = time.monotonic()
            try:
                other = build_env(
                    tree=_tree, gateway_dsn=_a2.gateway_dsn, downstream_dsn=_a2.downstream_dsn
                )
                _out.append(
                    other.service.accept_invocation(
                        _tree.invocation(
                            idempotency_key=_key,
                            jti=f"jti-{_key}-b",
                            tool_id="procurement.order.create",
                            params=order_params(),
                        ),
                        other.permission(),
                    ).operation_id
                )
                # the resource disappears exactly between the first miss and the
                # safe re-check: the first accept must still find the competitor
                _env.catalog.remove_request(REQUEST_ID)
                _t["resource_removed"] = time.monotonic()
            except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
                _err.append(f"{type(exc).__name__}: {exc}")
                raise
            finally:
                _t["b_done"] = time.monotonic()
                _go.set()

        thread = threading.Thread(target=commit_other, name="competitor")
        thread.start()
        error_code = None
        error_detail = None
        returned = None
        try:
            returned = env.service.accept_invocation(
                tree.invocation(
                    idempotency_key=key,
                    jti=f"jti-{key}-a",
                    tool_id="procurement.order.create",
                    params=order_params(),
                ),
                env.permission(),
            )
        except ExecutionError as exc:
            error_code = exc.code.value
            error_detail = exc.detail
        thread.join(30)
        assert not thread.is_alive()
        assert competitor and not competitor_error

        with psycopg.connect(a2.gateway_dsn) as conn:
            db_now = conn.execute("SELECT now()::text").fetchone()[0]
            proofs = conn.execute("SELECT count(*) FROM ag_proofs").fetchone()[0]
            op_row = conn.execute(
                "SELECT status, token_digest <> '', accepted_at::text "
                "FROM ag_operations WHERE operation_id = %s",
                (competitor[0],),
            ).fetchone()
            proof_rows = conn.execute(
                "SELECT proof_jti, recorded_at::text FROM ag_proofs "
                "WHERE operation_id = %s ORDER BY proof_jti",
                (competitor[0],),
            ).fetchall()
            lease = conn.execute(
                "SELECT count(*) FROM ag_execution_leases WHERE operation_id = %s",
                (competitor[0],),
            ).fetchone()[0]

        entry = {
            "round": round_no,
            "disposition": None if returned is None else returned.disposition.value,
            "returned_operation": None if returned is None else returned.operation_id,
            "error_code": error_code,
            "error_detail": error_detail,
            "cause_chain": []
            if error_code is None
            else _cause_chain(ExecutionError(ExecutionErrorCode.QUOTE_INVALID, "")),
            "lookups": list(lookups),
            "competitor_operation": competitor[0],
            "db_now": db_now,
            "proofs": proofs,
            "operation_status": op_row[0] if op_row else None,
            "operation_has_token_digest": op_row[1] if op_row else None,
            "accepted_at": op_row[2] if op_row else None,
            "proofs_registered": [list(row) for row in proof_rows],
            "leases": lease,
            "elapsed_first_to_resume_ms": round(
                (timeline["a_resumed"] - timeline["a_lookup_miss"]) * 1000, 3
            ),
            "elapsed_competitor_ms": round((timeline["b_done"] - timeline["b_start"]) * 1000, 3),
            "counters": fetch_counters(a2.gateway_dsn, tree.root_id),
            "effects": _effects(a2.downstream_dsn),
        }
        diagnostics.append(entry)

        # every round must be the deterministic positive outcome, and nothing
        # may be swallowed into a pass
        assert error_code is None, f"round {round_no}: unexpected {error_code} {error_detail}"
        assert returned is not None and returned.operation_id == competitor[0]
        assert returned.disposition.value == "EXISTING"
        assert lookups == [False, True], lookups
        assert entry["counters"]["amount_reserved"] == ORDER_AMOUNT_FEN
        assert entry["effects"]["ds_operations"] == 0
        monkeypatch.undo()

    # the diagnostics are real evidence: written to a durable file, never
    # hidden inside a warning or dropped because of a junit family setting
    out_dir = Path(os.environ.get("AG_TEST_DIAG_DIR", str(tmp_path)))
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "p11-resource-disappearance-diagnostics.json"
    target.write_text(json.dumps(diagnostics, indent=2, sort_keys=True), encoding="utf-8")
    assert target.exists() and target.stat().st_size > 0
    assert len(diagnostics) == 10
    assert all(entry["disposition"] == "EXISTING" for entry in diagnostics)


def test_p11_new_key_after_resource_disappearance_is_a_precise_refusal(a2, monkeypatch):
    """A21-R5-P11-EVIDENCE: the negative case keeps a precise, recorded code."""
    a2.catalog.remove_request(REQUEST_ID)
    code = None
    detail = None
    cause: list[str] = []
    try:
        a2.service.accept_invocation(
            a2.tree.invocation(
                idempotency_key="p11-diag-new-key",
                tool_id="procurement.order.create",
                params=order_params(),
            ),
            a2.permission(),
        )
    except ExecutionError as exc:
        code = exc.code.value
        detail = exc.detail
        cause = _cause_chain(exc)
    assert code == "RESOURCE_NOT_FOUND", (code, detail, cause)
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 0
    assert _effects(a2.downstream_dsn)["ds_operations"] == 0
