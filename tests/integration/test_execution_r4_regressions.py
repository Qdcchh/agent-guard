"""A2.1 correction-r3 regressions: atomic accept material and boundary shapes.

Formal rejection tests for the issues still open after review-r5:
A21-R1-CANDIDATE (atomic actual-existing material), A21-R1-LEGACY (deep
params at every entry), A21-R2-SNAPSHOT (identifier/version control chars),
A21-R1-OUTCOME (total-definition typed shapes), plus the A1 default-API
compatibility checks for the new ``accept_checked`` entry.

Every case is a requirement assertion, never a copy of an observation log.
"""

from __future__ import annotations

import dataclasses
import json
import threading

import psycopg
import pytest

from agent_guard.contracts.execution import (
    ExecutionError,
    ExecutionErrorCode,
    OperationStatus,
    ToolId,
)
from agent_guard.contracts.ledger import TrustedCost
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.tools.catalog import snapshot_from_bytes, snapshot_to_bytes
from agent_guard.tools.params import parse_tool_params
from agent_guard.tools.results import parse_result
from tests.fixtures.dbstate import fetch_counters, fetch_counts, fetch_one
from tests.fixtures.execution import (
    ORDER_AMOUNT_FEN,
    build_env,
    order_params,
    read_params,
)
from tests.fixtures.state import build_tree

pytestmark = pytest.mark.integration


def _effects(dsn) -> dict[str, int]:
    with psycopg.connect(dsn) as conn:
        return {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("ds_operations", "ds_orders", "ds_notifications")
        }


def _big_tree(a2):
    with psycopg.connect(a2.gateway_dsn) as conn:
        return build_tree(
            conn,
            root_limit=10_000_000,
            mid_limit=10_000_000,
            leaf_limit=10_000_000,
            root_calls=1000,
            mid_calls=1000,
            leaf_calls=1000,
        )


# ------------------------------------------- A21-R1-CANDIDATE (atomic)


@pytest.mark.parametrize("valid", [False, True])
@pytest.mark.parametrize("round_no", range(10))
def test_atomic_existing_material_in_the_accept_transaction(a2, monkeypatch, round_no, valid):
    """A21-R1-CANDIDATE: the actual EXISTING row is checked inside the accept
    transaction, after the last non-locking miss and before EXISTING returns.

    A competing accept commits *during* the first accept's window. Bad
    material must be refused, rolled back (no new proof) and durably
    quarantined; good material must return the correct EXISTING result.
    """
    tree = _big_tree(a2)
    env = build_env(tree=tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)
    key = f"r4-atomic-{round_no}-{valid}"
    ready = threading.Event()
    done = threading.Event()
    created: list[str] = []
    errors: list[str] = []
    original_checked = env.ledger.accept_checked

    def delayed_accept(
        verified, cost, *, existing_validator, _orig=original_checked, _ready=ready, _done=done
    ):
        _ready.set()
        assert _done.wait(20), "the competing accept never finished"
        return _orig(verified, cost, existing_validator=existing_validator)

    monkeypatch.setattr(env.ledger, "accept_checked", delayed_accept)

    snap = env.catalog.build_order_snapshot(
        tenant_id=tree.tenant_id,
        task_id=tree.task_id,
        request_id="req-001",
        quote_id="quote-001",
        quote_version="1",
        items=(("sku-001", 1),),
        delivery_id="office-001",
    )
    snapshot_bytes = snapshot_to_bytes(snap) if valid else b"invalid accepted legacy quote"

    def commit_other(
        _ready=ready,
        _done=done,
        _key=key,
        _tree=tree,
        _out=created,
        _err=errors,
        _bytes=snapshot_bytes,
    ):
        assert _ready.wait(20), "the first accept never reached its window"
        try:
            other = build_env(
                tree=_tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn
            )
            _out.append(
                other.ledger.accept(
                    _tree.invocation(
                        idempotency_key=_key,
                        tool_id=ToolId.ORDER_CREATE.value,
                        params=order_params(),
                    ),
                    TrustedCost(
                        70000, quote_id="quote-001", quote_version="1", quote_snapshot=_bytes
                    ),
                ).operation_id
            )
        except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
            _err.append(f"{type(exc).__name__}: {exc}")
            raise
        finally:
            _done.set()

    thread = threading.Thread(target=commit_other, name="competitor")
    thread.start()
    returned = None
    error_code = None
    try:
        returned = env.service.accept_invocation(
            tree.invocation(
                idempotency_key=key,
                jti=f"jti-{key}-a",
                tool_id=ToolId.ORDER_CREATE.value,
                params=order_params(),
            ),
            env.permission(),
        )
    except ExecutionError as exc:
        error_code = exc.code.value
    thread.join(30)
    assert not thread.is_alive()
    assert created and not errors

    counts = fetch_counts(a2.gateway_dsn)
    flag = env.service.review_flag(created[0]) is not None
    assert _effects(a2.downstream_dsn)["ds_operations"] == 0
    assert counts["ag_operations"] == 1
    for grant_id in (tree.root_id, tree.mid_id, tree.leaf_id):
        assert fetch_counters(a2.gateway_dsn, grant_id) == {
            "amount_reserved": 70000,
            "amount_settled": 0,
            "calls_reserved": 1,
            "calls_settled": 0,
        }

    if valid:
        assert error_code is None
        assert returned is not None and returned.operation_id == created[0]
        assert returned.disposition.value == "EXISTING"
        assert counts["ag_proofs"] == 2, counts["ag_proofs"]
        assert not flag
    else:
        assert error_code == ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID.value
        assert flag, "unusable existing material must be durably quarantined"
        # the refusing request's proof was rolled back with its transaction
        assert counts["ag_proofs"] == 1, counts["ag_proofs"]
    monkeypatch.undo()


def test_a1_default_accept_is_unchanged(a2):
    """The default A1 entry keeps its exact API and behaviour."""
    tree = _big_tree(a2)
    inv = tree.invocation(
        idempotency_key="r4-default-api",
        tool_id=ToolId.ORDER_CREATE.value,
        params=order_params(),
    )
    cost = TrustedCost(
        70000, quote_id="quote-001", quote_version="1", quote_snapshot=b"opaque-legacy-bytes"
    )
    result = ExecutionLedger(a2.gateway_dsn).accept(inv, cost)
    assert result.disposition.value == "CREATED"
    assert result.cost.amount_fen == 70000
    # no material validator runs: an opaque snapshot is untouched by accept
    assert fetch_one(
        a2.gateway_dsn,
        "SELECT quote_snapshot FROM ag_operations WHERE operation_id = %s",
        (result.operation_id,),
    ) == (b"opaque-legacy-bytes",)
    assert fetch_counts(a2.gateway_dsn)["ag_proofs"] == 1


def test_validators_do_not_cross_talk_on_one_instance(a2):
    """Per-call validators on one service instance cannot contaminate each other."""
    tree = _big_tree(a2)
    env = build_env(tree=tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)
    good_key, bad_key = "r4-nocross-good", "r4-nocross-bad"
    snap = env.catalog.build_order_snapshot(
        tenant_id=tree.tenant_id,
        task_id=tree.task_id,
        request_id="req-001",
        quote_id="quote-001",
        quote_version="1",
        items=(("sku-001", 1),),
        delivery_id="office-001",
    )
    for key, raw in ((good_key, snapshot_to_bytes(snap)), (bad_key, b"legacy bad material")):
        env.ledger.accept(
            tree.invocation(
                idempotency_key=key, tool_id=ToolId.ORDER_CREATE.value, params=order_params()
            ),
            TrustedCost(70000, quote_id="quote-001", quote_version="1", quote_snapshot=raw),
        )

    calls: list[str] = []

    def make_validator(name, allow):
        def validator(conn, existing):
            calls.append(f"{name}:{existing.idempotency_key}")
            if not allow:
                raise ExecutionError(
                    ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID, f"refused by {name}"
                )

        return validator

    # the same instance, two different validators, interleaved calls
    with pytest.raises(ExecutionError):
        env.ledger.accept_checked(
            tree.invocation(
                idempotency_key=bad_key,
                jti="jti-nocross-bad",
                tool_id=ToolId.ORDER_CREATE.value,
                params=order_params(),
            ),
            TrustedCost(70000, quote_id="quote-001", quote_version="1", quote_snapshot=b"x"),
            existing_validator=make_validator("strict", allow=False),
        )
    ok = env.ledger.accept_checked(
        tree.invocation(
            idempotency_key=good_key,
            jti="jti-nocross-good",
            tool_id=ToolId.ORDER_CREATE.value,
            params=order_params(),
        ),
        TrustedCost(70000, quote_id="quote-001", quote_version="1", quote_snapshot=b"x"),
        existing_validator=make_validator("lenient", allow=True),
    )
    assert ok.disposition.value == "EXISTING"
    assert calls == [f"strict:{bad_key}", f"lenient:{good_key}"]


def test_validator_failure_rolls_back_and_retry_rechecks(a2):
    """A refused candidate consumes no proof; a later retry re-validates."""
    tree = _big_tree(a2)
    env = build_env(tree=tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)
    key = "r4-rollback-retry"
    snap = env.catalog.build_order_snapshot(
        tenant_id=tree.tenant_id,
        task_id=tree.task_id,
        request_id="req-001",
        quote_id="quote-001",
        quote_version="1",
        items=(("sku-001", 1),),
        delivery_id="office-001",
    )
    env.ledger.accept(
        tree.invocation(
            idempotency_key=key, tool_id=ToolId.ORDER_CREATE.value, params=order_params()
        ),
        TrustedCost(
            70000, quote_id="quote-001", quote_version="1", quote_snapshot=snapshot_to_bytes(snap)
        ),
    )
    proofs_before = fetch_counts(a2.gateway_dsn)["ag_proofs"]
    attempts: list[bool] = []

    def flaky(conn, existing, _calls=attempts):
        _calls.append(True)
        if len(_calls) == 1:
            raise ExecutionError(ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID, "first attempt")

    with pytest.raises(ExecutionError) as excinfo:
        env.ledger.accept_checked(
            tree.invocation(
                idempotency_key=key,
                jti="jti-rollback-1",
                tool_id=ToolId.ORDER_CREATE.value,
                params=order_params(),
            ),
            TrustedCost(70000, quote_id="quote-001", quote_version="1", quote_snapshot=b"x"),
            existing_validator=flaky,
        )
    assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID
    # the refused request rolled its own proof back
    assert fetch_counts(a2.gateway_dsn)["ag_proofs"] == proofs_before

    # a retry with a fresh validator re-checks the same persisted material
    retry = env.ledger.accept_checked(
        tree.invocation(
            idempotency_key=key,
            jti="jti-rollback-2",
            tool_id=ToolId.ORDER_CREATE.value,
            params=order_params(),
        ),
        TrustedCost(70000, quote_id="quote-001", quote_version="1", quote_snapshot=b"x"),
        existing_validator=flaky,
    )
    assert retry.disposition.value == "EXISTING"
    assert attempts == [True, True]
    assert fetch_counts(a2.gateway_dsn)["ag_proofs"] == proofs_before + 1


def test_accept_checked_requires_a_callable_validator(a2):
    with pytest.raises(ValueError):
        a2.ledger.accept_checked(
            a2.tree.invocation(),
            a2.tree.cost(1),
            existing_validator=None,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError):
        a2.ledger.accept_checked(
            a2.tree.invocation(),
            a2.tree.cost(1),
            existing_validator="not-callable",  # type: ignore[arg-type]
        )


# ------------------------------------------------ A21-R1-LEGACY (deep params)


DEEP_PARAMS = b'{"request_id":' + b"[" * 1500 + b"0" + b"]" * 1500 + b"}"


def test_deep_new_params_are_rejected_without_touching_normal_operations(a2):
    """A21-R1-LEGACY: over-deep *new* params are a stable INVALID_PARAMS."""
    with pytest.raises(ExecutionError) as excinfo:
        parse_tool_params(ToolId.REQUEST_READ, DEEP_PARAMS)
    assert excinfo.value.code is ExecutionErrorCode.INVALID_PARAMS
    assert fetch_counts(a2.gateway_dsn)["ag_proofs"] == 0


@pytest.mark.parametrize("entry", ["run", "reconcile", "candidate", "fallback", "helper"])
def test_deep_legacy_params_durably_isolated_at_every_entry(a2, monkeypatch, entry):
    """A21-R1-LEGACY: 1500-deep legacy params never escape as RecursionError."""
    tree = _big_tree(a2)
    env = build_env(tree=tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)
    operation_id = env.ledger.accept(
        tree.invocation(
            idempotency_key="deep-params",
            tool_id=ToolId.REQUEST_READ.value,
            params=DEEP_PARAMS,
        ),
        TrustedCost(0, 1),
    ).operation_id
    before = fetch_counters(a2.gateway_dsn, tree.root_id)
    proofs_before = fetch_counts(a2.gateway_dsn)["ag_proofs"]
    error = None

    if entry == "fallback":
        original = env.service._find_candidate
        calls: list[int] = []

        def find(verified, _orig=original, _calls=calls):
            _calls.append(1)
            return None if len(_calls) == 1 else _orig(verified)

        monkeypatch.setattr(env.service, "_find_candidate", find)
        env.catalog.remove_request("req-001")

    try:
        if entry == "run":
            env.service.run_operation(operation_id, owner_token="deep-legacy")
        elif entry == "reconcile":
            env.service.reconcile(operation_id, owner_token="deep-legacy")
        elif entry == "helper":
            assert env.service.quarantine_if_insufficient(operation_id)
        else:
            env.service.accept_invocation(
                tree.invocation(
                    idempotency_key="deep-params",
                    jti="jti-deep-params",
                    tool_id=ToolId.REQUEST_READ.value,
                    params=read_params(),
                ),
                env.permission(),
            )
    except ExecutionError as exc:
        error = exc.code.value

    assert env.service.review_flag(operation_id) is not None, entry
    assert error in (ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID.value, None), (entry, error)
    assert fetch_counters(a2.gateway_dsn, tree.root_id) == before
    assert _effects(a2.downstream_dsn)["ds_operations"] == 0
    assert fetch_counts(a2.gateway_dsn)["ag_proofs"] == proofs_before


# --------------------------------------- A21-R2-SNAPSHOT (identifier edges)


@pytest.mark.parametrize("field", ["quote_id", "quote_version", "supplier_id", "sku"])
@pytest.mark.parametrize("suffix", ["\n", "\r", "\x00", " "])
def test_snapshot_identifier_trailing_control_refused(a2, field, suffix):
    """A21-R2-SNAPSHOT: identifiers and versions are full-string matches."""
    obj = {
        "quote_id": "quote-001",
        "quote_version": "1",
        "supplier_id": "supplier-001",
        "items": [{"sku": "sku-001", "quantity": 1, "unit_price_fen": 70000}],
        "total_fen": 70000,
        "currency": "CNY",
    }
    if field == "sku":
        obj["items"][0]["sku"] = obj["items"][0]["sku"] + suffix
    else:
        obj[field] = str(obj[field]) + suffix
    with pytest.raises(ExecutionError) as excinfo:
        snapshot_from_bytes(json.dumps(obj).encode())
    assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID


@pytest.mark.parametrize("version", ["0", "0\n", "01", "1\n", "version-x", ""])
def test_snapshot_version_rules_refuse_all_but_a_plain_positive_decimal(version):
    obj = {
        "quote_id": "quote-001",
        "quote_version": version,
        "supplier_id": "supplier-001",
        "items": [{"sku": "sku-001", "quantity": 1, "unit_price_fen": 70000}],
        "total_fen": 70000,
        "currency": "CNY",
    }
    with pytest.raises(ExecutionError) as excinfo:
        snapshot_from_bytes(json.dumps(obj).encode())
    assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID


def test_snapshot_legal_round_trip_still_works():
    obj = {
        "quote_id": "quote-001",
        "quote_version": "1",
        "supplier_id": "supplier-001",
        "items": [{"sku": "sku-001", "quantity": 1, "unit_price_fen": 70000}],
        "total_fen": 70000,
        "currency": "CNY",
    }
    assert snapshot_from_bytes(json.dumps(obj).encode()) is not None


@pytest.mark.parametrize("suffix", ["\n", "\r"])
def test_result_identifier_trailing_control_refused(suffix):
    """A21-R2-SNAPSHOT: result identifiers follow the same full-string rule."""
    raw = json.dumps(
        {
            "kind": "order",
            "operation_id": "op-1",
            "order_id": f"order-1{suffix}",
            "supplier_id": "supplier-001",
            "quote_id": "quote-001",
            "quote_version": "1",
            "items": [{"sku": "sku-001", "quantity": 1, "unit_price_fen": 70000}],
            "total_fen": 70000,
        },
        separators=(",", ":"),
    ).encode()
    with pytest.raises(ExecutionError) as excinfo:
        parse_result(raw)
    assert excinfo.value.code is ExecutionErrorCode.DOWNSTREAM_INCONSISTENT


# --------------------------------------------- A21-R1-OUTCOME (typed shape)


class _QuoteStub:
    """A typed object with an unusable ``items`` shape."""

    def __init__(self, items):
        self.quote_id = "quote-001"
        self.quote_version = "1"
        self.supplier_id = "supplier-001"
        self.currency = "CNY"
        self.total_fen = ORDER_AMOUNT_FEN
        self.items = items


class _Entry(dict):
    """A dict posing as a quote line."""


@pytest.mark.parametrize(
    "items",
    [None, "not-a-list", 7, _Entry(sku="sku-001"), {"sku": "sku-001"}, (None,), ("x",)],
)
def test_outcome_typed_shape_boundaries_keep_unknown(a2, items):
    """A21-R1-OUTCOME: an unusable typed quote never raises and never settles.

    The comparison is a total definition: type/shape is checked before any
    attribute is read, so ``None``/dict/other containers answer "not equal"
    (hence UNKNOWN) instead of leaving the operation stuck in EXECUTING.
    """
    from agent_guard.tools.catalog import snapshot_from_bytes as _decode

    operation_id = a2.service.accept_invocation(
        a2.tree.invocation(
            idempotency_key=f"r4-shape-{id(items)}",
            tool_id=ToolId.ORDER_CREATE.value,
            params=order_params(),
        ),
        a2.permission(),
    ).operation_id
    row = a2.service.load_operation(operation_id)
    value = a2.downstream.execute(
        service_secret=a2.secret,
        operation_id=operation_id,
        tool_id=ToolId.ORDER_CREATE,
        canonical_params=row.canonical_params,
        quote=_decode(row.quote_snapshot),
        expected_amount_fen=row.amount_fen,
    )
    value = dataclasses.replace(value, quote=_QuoteStub(items))

    class Port:
        def execute(self, **kwargs):
            return value

        def query(self, **kwargs):
            return value

    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        downstream=Port(),
    )
    result = env.service.run_operation(operation_id, owner_token="r4-shape")
    assert result.status == OperationStatus.UNKNOWN.value
    assert result.action is None
    assert env.service.outbox_entry(operation_id) is None
    assert fetch_counters(a2.gateway_dsn, a2.tree.root_id)["amount_settled"] == 0


def test_outcome_effect_identifier_trailing_lf_keeps_unknown(a2):
    """A21-R1-OUTCOME: a trailing LF in the effect id is not a valid binding."""
    operation_id = a2.service.accept_invocation(
        a2.tree.invocation(
            idempotency_key="r4-effect-lf",
            tool_id=ToolId.ORDER_CREATE.value,
            params=order_params(),
        ),
        a2.permission(),
    ).operation_id
    row = a2.service.load_operation(operation_id)
    value = a2.downstream.execute(
        service_secret=a2.secret,
        operation_id=operation_id,
        tool_id=ToolId.ORDER_CREATE,
        canonical_params=row.canonical_params,
        quote=snapshot_from_bytes(row.quote_snapshot),
        expected_amount_fen=row.amount_fen,
    )
    obj = json.loads(value.result_bytes)
    obj["order_id"] = obj["order_id"] + "\n"
    value = dataclasses.replace(
        value, effect_ref=obj["order_id"], result_bytes=json.dumps(obj).encode()
    )

    class Port:
        def execute(self, **kwargs):
            return value

        def query(self, **kwargs):
            return value

    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        downstream=Port(),
    )
    result = env.service.run_operation(operation_id, owner_token="r4-effect-lf")
    assert result.status == OperationStatus.UNKNOWN.value
    assert env.service.outbox_entry(operation_id) is None


@pytest.mark.parametrize("entry", ["execute", "query"])
def test_structurally_identical_list_quote_still_settles(a2, entry):
    """A21-R1-OUTCOME: a legal list of the same quote lines is *not* a mismatch."""
    from agent_guard.tools.catalog import snapshot_from_bytes as _decode

    operation_id = a2.service.accept_invocation(
        a2.tree.invocation(
            idempotency_key=f"r4-list-{entry}",
            tool_id=ToolId.ORDER_CREATE.value,
            params=order_params(),
        ),
        a2.permission(),
    ).operation_id
    row = a2.service.load_operation(operation_id)
    value = a2.downstream.execute(
        service_secret=a2.secret,
        operation_id=operation_id,
        tool_id=ToolId.ORDER_CREATE,
        canonical_params=row.canonical_params,
        quote=_decode(row.quote_snapshot),
        expected_amount_fen=row.amount_fen,
    )
    value = dataclasses.replace(
        value, quote=dataclasses.replace(value.quote, items=list(value.quote.items))
    )

    class Port:
        def execute(self, **kwargs):
            return value

        def query(self, **kwargs):
            return value

    env = build_env(
        tree=a2.tree,
        gateway_dsn=a2.gateway_dsn,
        downstream_dsn=a2.downstream_dsn,
        downstream=Port(),
    )
    result = (
        env.service.run_operation(operation_id, owner_token="r4-list")
        if entry == "execute"
        else env.service.reconcile(operation_id, owner_token="r4-list")
    )
    assert result.status == OperationStatus.SUCCEEDED.value
    assert fetch_counts(a2.gateway_dsn)["ag_receipt_outbox"] == 1
    assert _effects(a2.downstream_dsn)["ds_orders"] == 1
    for grant_id in (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id):
        assert fetch_counters(a2.gateway_dsn, grant_id) == {
            "amount_reserved": 0,
            "amount_settled": ORDER_AMOUNT_FEN,
            "calls_reserved": 0,
            "calls_settled": 1,
        }
