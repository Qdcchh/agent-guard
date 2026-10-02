"""A2-P15-CORE: layered tool/permission negatives with zero reservation.

Every case asserts the *database* outcome: no operation, no reservation at any
ancestor, no ledger event and no downstream effect. This is the trusted-object
layer only — building :class:`TrustedPermissionSnapshot` here is a test fixture
and is **not** real signature verification, so the full P15 with B's verifier
remains a later-stage obligation.
"""

from __future__ import annotations

import psycopg
import pytest

from agent_guard.contracts.execution import (
    ExecutionError,
    ExecutionErrorCode,
    ToolId,
)
from tests.fixtures.dbstate import fetch_counters, fetch_counts
from tests.fixtures.execution import (
    ORDER_AMOUNT_FEN,
    constraints_for,
    document_params,
    notification_params,
    order_params,
    read_params,
)

pytestmark = pytest.mark.integration


def assert_zero_state(a2, env=None, *, baseline=None):
    """Nothing new must be reserved, recorded or executed.

    ``baseline`` is a previous :func:`fetch_counts` snapshot used when the test
    legitimately already holds accepted operations (e.g. a notification target);
    the refusal itself must leave every count exactly where it was.
    """
    env = env or a2
    counts = fetch_counts(env.gateway_dsn)
    if baseline is not None:
        assert counts == baseline
        return
    assert counts["ag_operations"] == 0
    assert counts["ag_ledger_events"] == 0
    assert counts["ag_proofs"] == 0
    assert counts["ag_receipt_outbox"] == 0
    assert counts["ag_execution_leases"] == 0
    for grant_id in (env.tree.root_id, env.tree.mid_id, env.tree.leaf_id):
        counters = fetch_counters(env.gateway_dsn, grant_id)
        assert counters["amount_reserved"] == 0, grant_id
        assert counters["calls_reserved"] == 0, grant_id
        assert counters["amount_settled"] == 0
        assert counters["calls_settled"] == 0
    with psycopg.connect(env.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_operations").fetchone()[0] == 0


def _attempt(a2, *, tool_id, params, permission=None, inv_kwargs=None):
    inv = a2.tree.invocation(
        idempotency_key="p15-case",
        tool_id=tool_id,
        params=params,
        **(inv_kwargs or {}),
    )
    return a2.service.accept_invocation(inv, permission or a2.permission())


# ------------------------------------------------------------ tool identity


@pytest.mark.parametrize("tool_id", ["order.create", "procurement.order", "unknown.tool", ""])
def test_p15_tool_aliases_are_refused_with_zero_state(a2, tool_id):
    with pytest.raises(ExecutionError):
        _attempt(a2, tool_id=tool_id, params=order_params())
    assert_zero_state(a2)


@pytest.mark.parametrize("version", ["2", "01", 1])
def test_p15_tool_version_must_be_the_string_one(a2, version):
    with pytest.raises(ExecutionError):
        _attempt(
            a2,
            tool_id="procurement.order.create",
            params=order_params(),
            inv_kwargs={"tool_version": version},
        )
    assert_zero_state(a2)


# ------------------------------------------------------------ strict params


@pytest.mark.parametrize(
    "raw",
    [
        # duplicate top-level JSON key
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"items":[{"sku":"sku-001","quantity":1}],"delivery_id":"office-001",'
        b'"delivery_id":"office-002"}',
        # duplicate SKU
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"items":[{"sku":"sku-001","quantity":1},{"sku":"sku-001","quantity":1}],'
        b'"delivery_id":"office-001"}',
        # boolean quantity
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"items":[{"sku":"sku-001","quantity":true}],"delivery_id":"office-001"}',
        # negative quantity
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"items":[{"sku":"sku-001","quantity":-1}],"delivery_id":"office-001"}',
        # float quantity
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"items":[{"sku":"sku-001","quantity":1.5}],"delivery_id":"office-001"}',
        # overflow quantity
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"items":[{"sku":"sku-001","quantity":9007199254740992}],"delivery_id":"office-001"}',
        # empty item collection
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"items":[],"delivery_id":"office-001"}',
        # missing item collection
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"delivery_id":"office-001"}',
        # unknown field
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"items":[{"sku":"sku-001","quantity":1}],"delivery_id":"office-001","extra":1}',
        # URL / path injection
        b'{"request_id":"https://evil.test/x","quote_id":"quote-001","quote_version":"1",'
        b'"items":[{"sku":"sku-001","quantity":1}],"delivery_id":"office-001"}',
    ],
)
def test_p15_strict_parameter_rejections_reserve_nothing(a2, raw):
    with pytest.raises(ExecutionError):
        _attempt(a2, tool_id="procurement.order.create", params=raw)
    assert_zero_state(a2)


# ---------------------------------------------------------- permission sets


def test_p15_missing_constraint_set_is_refused(a2):
    from agent_guard.tools import policy

    data = {
        "grant_id": a2.tree.leaf_id,
        "root_id": a2.tree.root_id,
        "tenant_id": a2.tree.tenant_id,
        "task_id": a2.tree.task_id,
        "subject": a2.tree.subject,
        "scope": [ToolId.ORDER_CREATE.value],
        "chain": [
            {
                "request_ids": ["req-001"],
                "document_ids": ["doc-001"],
                "quote_versions": ["quote-001@1"],
                "skus": ["sku-001"],
                "delivery_ids": ["office-001"],
                "template_ids": ["order-created"],
                # recipient_ids deliberately missing
                "max_quantity": 2,
            }
        ],
    }
    with pytest.raises(ExecutionError) as excinfo:
        policy.permission_snapshot_from_mapping(data)
    assert "missing fields" in excinfo.value.detail
    assert_zero_state(a2)


def test_p15_empty_scope_forbids_every_tool(a2):
    permission = a2.permission(scope=())
    for tool_id, params in (
        ("procurement.request.read", read_params()),
        ("procurement.document.read", document_params()),
        ("procurement.order.create", order_params()),
        ("notification.template.send", notification_params()),
    ):
        with pytest.raises(ExecutionError) as excinfo:
            _attempt(a2, tool_id=tool_id, params=params, permission=permission)
        assert excinfo.value.code is ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED
    assert_zero_state(a2)


def test_p15_insufficient_scope_for_one_tool_only(a2):
    permission = a2.permission(scope=(ToolId.REQUEST_READ.value,))
    with pytest.raises(ExecutionError) as excinfo:
        _attempt(
            a2, tool_id="procurement.order.create", params=order_params(), permission=permission
        )
    assert excinfo.value.code is ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED
    # the granted tool still works
    accepted = _attempt(
        a2, tool_id="procurement.request.read", params=read_params(), permission=permission
    )
    assert accepted.cost.amount_fen == 0
    assert accepted.cost.calls == 1


def test_p15_empty_resource_set_forbids_that_resource(a2):
    chain = tuple(constraints_for(depth, skus=()) for depth in range(3))
    permission = a2.permission(chain=chain)
    with pytest.raises(ExecutionError) as excinfo:
        _attempt(
            a2, tool_id="procurement.order.create", params=order_params(), permission=permission
        )
    assert excinfo.value.code is ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED
    assert_zero_state(a2)


# ------------------------------------------------------- binding and chain


def test_p15_snapshot_binding_mismatches_reserve_nothing(a2):
    import dataclasses

    for field in ("grant_id", "root_id", "tenant_id", "task_id", "subject"):
        forged = dataclasses.replace(a2.permission(), **{field: "forged-value"})
        with pytest.raises(ExecutionError) as excinfo:
            _attempt(
                a2,
                tool_id="procurement.order.create",
                params=order_params(),
                permission=forged,
            )
        assert excinfo.value.code is ExecutionErrorCode.CONSTRAINT_MISMATCH, field
    assert_zero_state(a2)


def test_p15_ancestor_inclusion_violation_is_refused(a2):
    from agent_guard.tools import policy

    # the leaf grants a SKU the root never had: the narrowing chain is broken
    chain = (
        constraints_for(0, skus=("sku-002",)),
        constraints_for(1, skus=("sku-002",)),
        constraints_for(2, skus=("sku-001",)),
    )
    with pytest.raises(ExecutionError) as excinfo:
        policy.check_narrowing(chain)
    assert excinfo.value.code is ExecutionErrorCode.CONSTRAINT_MISMATCH

    permission = a2.permission(chain=chain)
    with pytest.raises(ExecutionError):
        _attempt(
            a2, tool_id="procurement.order.create", params=order_params(), permission=permission
        )
    assert_zero_state(a2)


def test_p15_child_max_quantity_increase_is_refused(a2):
    chain = (
        constraints_for(0, max_quantity=1),
        constraints_for(1, max_quantity=1),
        constraints_for(2, max_quantity=5),
    )
    with pytest.raises(ExecutionError) as excinfo:
        _attempt(
            a2,
            tool_id="procurement.order.create",
            params=order_params(),
            permission=a2.permission(chain=chain),
        )
    assert excinfo.value.code is ExecutionErrorCode.CONSTRAINT_MISMATCH
    assert_zero_state(a2)


# ---------------------------------------------------------- resource checks


def test_p15_cross_tenant_and_wrong_associations_reserve_nothing(a2):
    cases = [
        # request belongs to another tenant/task
        {"request_id": "req-002"},
        {"request_id": "req-999"},
        # document not bound to the request
        {"document_id": "doc-999"},
        # quote not in the granted set
        {"quote_id": "quote-999"},
        {"quote_version": "9"},
        # delivery not approved for the request
        {"delivery_id": "office-999"},
    ]
    for kwargs in cases:
        if (
            "items" in kwargs
            or "quote_id" in kwargs
            or "quote_version" in kwargs
            or "delivery_id" in kwargs
        ):
            tool_id, params = "procurement.order.create", order_params(**kwargs)
        elif "document_id" in kwargs:
            tool_id, params = "procurement.document.read", document_params(**kwargs)
        else:
            tool_id, params = "procurement.order.create", order_params(**kwargs)
        with pytest.raises(ExecutionError) as excinfo:
            _attempt(a2, tool_id=tool_id, params=params)
        assert excinfo.value.code in (
            ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
            ExecutionErrorCode.RESOURCE_NOT_FOUND,
            ExecutionErrorCode.QUOTE_INVALID,
        ), kwargs
    assert_zero_state(a2)


def test_p15_cross_tenant_request_is_refused(a2):
    """P15: a request row that belongs to another tenant never authorises."""
    a2.catalog.add_request(
        type(a2.catalog.get_request("req-002"))("req-other-tenant", "tenant-other", a2.tree.task_id)
    )
    chain = tuple(constraints_for(depth, request_ids=("req-other-tenant",)) for depth in range(3))
    permission = a2.permission(chain=chain)
    with pytest.raises(ExecutionError) as excinfo:
        _attempt(
            a2,
            tool_id="procurement.order.create",
            params=order_params(request_id="req-other-tenant"),
            permission=permission,
        )
    assert excinfo.value.code is ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED
    assert_zero_state(a2)


def test_p15_notification_targets_are_checked(a2):
    from tests.fixtures.execution import make_reference_operation

    target = make_reference_operation(a2, key="p15-note-target")
    baseline = fetch_counts(a2.gateway_dsn)
    for kwargs in ({"template_id": "template-999"}, {"recipient_id": "user-999"}):
        with pytest.raises(ExecutionError):
            _attempt(
                a2,
                tool_id="notification.template.send",
                params=notification_params(operation_id=target, **kwargs),
            )
    assert_zero_state(a2, baseline=baseline)
    with psycopg.connect(a2.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_notifications").fetchone()[0] == 0


def test_p15_order_quantity_above_max_quantity_is_refused(a2):
    with pytest.raises(ExecutionError) as excinfo:
        _attempt(
            a2,
            tool_id="procurement.order.create",
            params=order_params(items=(("sku-001", 5),)),
        )
    assert excinfo.value.code is ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED
    assert_zero_state(a2)


def test_p15_order_quantity_above_offered_quantity_is_refused(a2):
    """P15: the quote only offers one unit at this version."""
    permission = a2.permission(chain=tuple(constraints_for(d, max_quantity=9) for d in range(3)))
    with pytest.raises(ExecutionError) as excinfo:
        _attempt(
            a2,
            tool_id="procurement.order.create",
            params=order_params(items=(("sku-001", 2),)),
            permission=permission,
        )
    assert excinfo.value.code is ExecutionErrorCode.QUOTE_INVALID
    assert_zero_state(a2)


def test_p15_read_and_document_paths_reject_injection(a2):
    for tool_id, params in (
        ("procurement.request.read", read_params(request_id="../etc/passwd")),
        ("procurement.document.read", document_params(document_id="https://evil.test/x")),
        (
            "notification.template.send",
            notification_params(operation_id="a/b"),
        ),
    ):
        with pytest.raises(ExecutionError):
            _attempt(a2, tool_id=tool_id, params=params)
    assert_zero_state(a2)


def test_p15_positive_control_for_each_tool(a2):
    """P15: the same fixture accepts all four tools when everything is in scope."""
    from tests.fixtures.execution import make_reference_operation

    target = make_reference_operation(a2, key="p15-positive-target")
    results = [
        _attempt(a2, tool_id="procurement.request.read", params=read_params()),
        _attempt(a2, tool_id="procurement.document.read", params=document_params()),
        _attempt(a2, tool_id="procurement.order.create", params=order_params()),
        _attempt(
            a2,
            tool_id="notification.template.send",
            params=notification_params(operation_id=target),
        ),
    ]
    assert [r.cost.amount_fen for r in results] == [0, 0, ORDER_AMOUNT_FEN, 0]
    assert [r.cost.calls for r in results] == [1, 1, 1, 1]
    counts = fetch_counts(a2.gateway_dsn)
    # 1 reference operation + the four tools
    assert counts["ag_operations"] == 5
    assert counts["ag_ledger_events"] == 5
    assert counts["ag_ledger_event_nodes"] == 15
