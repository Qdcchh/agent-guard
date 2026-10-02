"""A2-P15-CORE unit half: strict four-tool parameter and permission parsing.

Pure, database-free rejection tests. The database half (zero reservation and
zero effect for every negative case) lives in
``tests/integration/test_execution_validation.py``. Building trusted objects
here is layered testing, not a claim that anything was signature-verified.
"""

from __future__ import annotations

import pytest

from agent_guard.contracts.execution import (
    ExecutionError,
    ExecutionErrorCode,
    GrantConstraints,
    ToolId,
)
from agent_guard.tools import params, policy

pytestmark = pytest.mark.unit

ORDER_OK = (
    b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
    b'"items":[{"sku":"sku-001","quantity":1}],"delivery_id":"office-001"}'
)


def _code(exc: ExecutionError) -> ExecutionErrorCode:
    return exc.code


# --------------------------------------------------------------- tool id


def test_four_complete_tool_ids_are_accepted():
    for value in ToolId:
        assert params.parse_tool_id(value.value) is value


@pytest.mark.parametrize(
    "alias",
    [
        "order.create",
        "procurement.order",
        "request.read",
        "document.read",
        "notification.send",
        "procurement.order.create ",
        "Procurement.order.create",
        "PROCUREMENT.ORDER.CREATE",
        "",
        "unknown.tool",
    ],
)
def test_tool_aliases_and_unknown_tools_are_refused(alias):
    with pytest.raises(ExecutionError) as excinfo:
        params.parse_tool_id(alias)
    assert excinfo.value.code in (
        ExecutionErrorCode.UNSUPPORTED_TOOL,
        ExecutionErrorCode.INVALID_PARAMS,
    )


@pytest.mark.parametrize("version", ["2", "01", 1, 1.0, True, None, ""])
def test_tool_version_must_be_the_string_one(version):
    with pytest.raises(ExecutionError):
        params.parse_tool_version(version)


def test_tool_version_string_one_is_accepted():
    assert params.parse_tool_version("1") == "1"


# ------------------------------------------------------------- strict JSON


def test_duplicate_json_keys_are_refused():
    raw = (
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"items":[{"sku":"sku-001","quantity":1}],"delivery_id":"office-001",'
        b'"delivery_id":"office-002"}'
    )
    with pytest.raises(ExecutionError) as excinfo:
        params.parse_tool_params("procurement.order.create", raw)
    assert "duplicate JSON key" in excinfo.value.detail


def test_duplicate_item_keys_and_duplicate_skus_are_refused():
    dup_key = (
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"items":[{"sku":"sku-001","quantity":1,"quantity":2}],"delivery_id":"office-001"}'
    )
    with pytest.raises(ExecutionError) as excinfo:
        params.parse_tool_params("procurement.order.create", dup_key)
    assert "duplicate JSON key" in excinfo.value.detail

    dup_sku = (
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"items":[{"sku":"sku-001","quantity":1},{"sku":"sku-001","quantity":2}],'
        b'"delivery_id":"office-001"}'
    )
    with pytest.raises(ExecutionError) as excinfo:
        params.parse_tool_params("procurement.order.create", dup_sku)
    assert "duplicate SKU" in excinfo.value.detail


@pytest.mark.parametrize(
    "quantity",
    [b"true", b"false", b"-1", b"0", b"1.5", b"1e3", b"9007199254740992"],
)
def test_bool_negative_float_and_overflow_quantities_are_refused(quantity):
    raw = (
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"items":[{"sku":"sku-001","quantity":' + quantity + b'}],"delivery_id":"office-001"}'
    )
    with pytest.raises(ExecutionError) as excinfo:
        params.parse_tool_params("procurement.order.create", raw)
    assert excinfo.value.code is ExecutionErrorCode.INVALID_PARAMS


@pytest.mark.parametrize("payload", [b"[]", b"{}", b"null", b""])
def test_missing_or_empty_item_collections_are_refused(payload):
    raw = (
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
        b'"items":' + payload + b',"delivery_id":"office-001"}'
    )
    with pytest.raises(ExecutionError):
        params.parse_tool_params("procurement.order.create", raw)


def test_missing_and_unknown_fields_are_refused():
    missing = (
        b'{"quote_id":"quote-001","quote_version":"1",'
        b'"items":[{"sku":"sku-001","quantity":1}],"delivery_id":"office-001"}'
    )
    with pytest.raises(ExecutionError) as excinfo:
        params.parse_tool_params("procurement.order.create", missing)
    assert "missing fields" in excinfo.value.detail

    extra = b'{"request_id":"req-001","amount_fen":1}'
    with pytest.raises(ExecutionError) as excinfo:
        params.parse_tool_params("procurement.request.read", extra)
    assert "unknown fields" in excinfo.value.detail


@pytest.mark.parametrize(
    "bad",
    [b"../etc/passwd", b"https://evil.test/x", b"a/b", b"a\\\\b", b"%2e%2e", b"a b", b"a@b"],
)
def test_url_and_path_injection_into_resource_ids_is_refused(bad):
    raw = b'{"request_id":' + b'"' + bad + b'"}'
    with pytest.raises(ExecutionError) as excinfo:
        params.parse_tool_params("procurement.request.read", raw)
    assert excinfo.value.code is ExecutionErrorCode.INVALID_PARAMS


def test_non_finite_numbers_and_non_object_params_are_refused():
    with pytest.raises(ExecutionError):
        params.parse_tool_params("procurement.request.read", b'{"request_id":"req-001","x":NaN}')
    for raw in (b"[]", b'"str"', b"1"):
        with pytest.raises(ExecutionError):
            params.parse_tool_params("procurement.request.read", raw)


def test_non_utf8_params_are_refused():
    with pytest.raises(ExecutionError):
        params.parse_tool_params("procurement.request.read", b'{"request_id":"\xff"}')


def test_quote_version_must_be_a_decimal_positive_string():
    for version in (b"0", b"01", b"-1", b"1.0", b"v1", b"1@2"):
        raw = (
            b'{"request_id":"req-001","quote_id":"quote-001","quote_version":' + version + b","
            b'"items":[{"sku":"sku-001","quantity":1}],"delivery_id":"office-001"}'
        )
        with pytest.raises(ExecutionError):
            params.parse_tool_params("procurement.order.create", raw)


def test_valid_order_params_round_trip():
    parsed = params.parse_tool_params("procurement.order.create", ORDER_OK)
    assert parsed.request_id == "req-001"
    assert parsed.quote_id == "quote-001"
    assert parsed.quote_version == "1"
    assert parsed.delivery_id == "office-001"
    assert [(i.sku, i.quantity) for i in parsed.items] == [("sku-001", 1)]


def test_valid_read_document_and_notification_params():
    read = params.parse_tool_params("procurement.request.read", b'{"request_id":"req-001"}')
    assert read.request_id == "req-001"

    doc = params.parse_tool_params(
        "procurement.document.read", b'{"request_id":"req-001","document_id":"doc-001"}'
    )
    assert doc.document_id == "doc-001"

    note = params.parse_tool_params(
        "notification.template.send",
        b'{"template_id":"order-created","recipient_id":"user-demo-001","operation_id":"op-1"}',
    )
    assert note.template_id == "order-created"


# ------------------------------------------------------------- constraints


def test_missing_constraint_set_is_a_format_error():
    data = {
        "request_ids": [],
        "document_ids": [],
        "quote_versions": [],
        "skus": [],
        "delivery_ids": [],
        "template_ids": [],
        # recipient_ids missing
        "max_quantity": 1,
    }
    with pytest.raises(ExecutionError) as excinfo:
        policy.constraints_from_mapping(data)
    assert "missing fields" in excinfo.value.detail


def test_empty_constraint_set_is_legal_and_means_forbidden():
    constraints = policy.constraints_from_mapping(
        {
            "request_ids": (),
            "document_ids": (),
            "quote_versions": (),
            "skus": (),
            "delivery_ids": (),
            "template_ids": (),
            "recipient_ids": (),
            "max_quantity": 0,
        }
    )
    assert constraints.request_ids == ()
    assert constraints.max_quantity == 0


@pytest.mark.parametrize("bad", [True, False, -1, 1.5, "1"])
def test_max_quantity_rejects_bool_float_negative_and_strings(bad):
    data = {
        "request_ids": (),
        "document_ids": (),
        "quote_versions": (),
        "skus": (),
        "delivery_ids": (),
        "template_ids": (),
        "recipient_ids": (),
        "max_quantity": bad,
    }
    with pytest.raises(ExecutionError):
        policy.constraints_from_mapping(data)


def test_duplicate_constraint_entries_are_refused():
    data = {
        "request_ids": ["req-001", "req-001"],
        "document_ids": (),
        "quote_versions": (),
        "skus": (),
        "delivery_ids": (),
        "template_ids": (),
        "recipient_ids": (),
        "max_quantity": 1,
    }
    with pytest.raises(ExecutionError):
        policy.constraints_from_mapping(data)


# ------------------------------------------------------- narrowing and scope


def _chain(leaf_kwargs=None, parent_kwargs=None) -> tuple[GrantConstraints, ...]:
    base = {
        "request_ids": ("req-001",),
        "document_ids": ("doc-001",),
        "quote_versions": ("quote-001@1",),
        "skus": ("sku-001",),
        "delivery_ids": ("office-001",),
        "template_ids": ("order-created",),
        "recipient_ids": ("user-demo-001",),
        "max_quantity": 2,
    }
    parent = {**base, **(parent_kwargs or {})}
    leaf = {**base, **(leaf_kwargs or {})}
    return (
        policy.constraints_from_mapping(parent),
        policy.constraints_from_mapping(leaf),
    )


def test_child_set_outside_parent_is_refused():
    chain = _chain(leaf_kwargs={"skus": ("sku-001", "sku-999")})
    with pytest.raises(ExecutionError) as excinfo:
        policy.check_narrowing(chain)
    assert excinfo.value.code is ExecutionErrorCode.CONSTRAINT_MISMATCH


def test_child_max_quantity_increase_is_refused():
    chain = _chain(parent_kwargs={"max_quantity": 1}, leaf_kwargs={"max_quantity": 2})
    with pytest.raises(ExecutionError) as excinfo:
        policy.check_narrowing(chain)
    assert excinfo.value.code is ExecutionErrorCode.CONSTRAINT_MISMATCH


def test_valid_narrowing_chain_is_accepted():
    chain = _chain(parent_kwargs={"max_quantity": 4}, leaf_kwargs={"max_quantity": 2})
    policy.check_narrowing(chain)


def test_empty_scope_forbids_every_tool():
    snapshot = policy.permission_snapshot_from_mapping(
        {
            "grant_id": "g-leaf",
            "root_id": "g-root",
            "tenant_id": "tenant-demo",
            "task_id": "task-001",
            "subject": "user-demo-001",
            "scope": [],
            "chain": [chain_to_mapping(c) for c in _chain()],
            "chain_grant_ids": ["g-root", "g-leaf"],
        }
    )
    for tool in ToolId:
        with pytest.raises(ExecutionError) as excinfo:
            policy.check_scope(snapshot, tool)
        assert excinfo.value.code is ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED


def chain_to_mapping(constraints: GrantConstraints) -> dict:
    return {
        "request_ids": list(constraints.request_ids),
        "document_ids": list(constraints.document_ids),
        "quote_versions": list(constraints.quote_versions),
        "skus": list(constraints.skus),
        "delivery_ids": list(constraints.delivery_ids),
        "template_ids": list(constraints.template_ids),
        "recipient_ids": list(constraints.recipient_ids),
        "max_quantity": constraints.max_quantity,
    }


def test_snapshot_binding_mismatch_is_refused():
    snapshot = policy.permission_snapshot_from_mapping(
        {
            "grant_id": "g-leaf",
            "root_id": "g-root",
            "tenant_id": "tenant-demo",
            "task_id": "task-001",
            "subject": "user-demo-001",
            "scope": ["procurement.order.create"],
            "chain": [chain_to_mapping(c) for c in _chain()],
            "chain_grant_ids": ["g-root", "g-leaf"],
        }
    )
    for field, value in (
        ("grant_id", "g-other"),
        ("root_id", "g-other"),
        ("tenant_id", "tenant-other"),
        ("task_id", "task-other"),
        ("subject", "user-other"),
    ):
        kwargs = {
            "grant_id": "g-leaf",
            "root_id": "g-root",
            "tenant_id": "tenant-demo",
            "task_id": "task-001",
            "subject": "user-demo-001",
            field: value,
        }
        with pytest.raises(ExecutionError) as excinfo:
            policy.check_snapshot_binding(snapshot, **kwargs)
        assert excinfo.value.code is ExecutionErrorCode.CONSTRAINT_MISMATCH


def test_permission_snapshot_rejects_missing_or_extra_fields():
    good = {
        "grant_id": "g-leaf",
        "root_id": "g-root",
        "tenant_id": "tenant-demo",
        "task_id": "task-001",
        "subject": "user-demo-001",
        "scope": ["procurement.order.create"],
        "chain": [chain_to_mapping(c) for c in _chain()],
        "chain_grant_ids": ["g-root", "g-leaf"],
    }
    with pytest.raises(ExecutionError):
        policy.permission_snapshot_from_mapping({k: v for k, v in good.items() if k != "scope"})
    with pytest.raises(ExecutionError):
        policy.permission_snapshot_from_mapping({**good, "extra": 1})
    with pytest.raises(ExecutionError):
        policy.permission_snapshot_from_mapping({**good, "chain": []})


def test_quote_membership_uses_the_id_at_version_key():
    chain = _chain(
        parent_kwargs={"quote_versions": ("quote-999@9",)},
        leaf_kwargs={"quote_versions": ("quote-999@9",)},
    )
    with pytest.raises(ExecutionError) as excinfo:
        policy.check_static_authorization(
            bind_snapshot(chain),
            grant_id="g-leaf",
            root_id="g-root",
            tenant_id="tenant-demo",
            task_id="task-001",
            subject="user-demo-001",
            tool_id=ToolId.ORDER_CREATE,
            params=params.parse_tool_params("procurement.order.create", ORDER_OK),
        )
    assert excinfo.value.code is ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED
    assert "quote-001@1" in excinfo.value.detail


def bind_snapshot(chain, ids=None) -> object:
    return policy.permission_snapshot_from_mapping(
        {
            "grant_id": "g-leaf",
            "root_id": "g-root",
            "tenant_id": "tenant-demo",
            "task_id": "task-001",
            "subject": "user-demo-001",
            "scope": ["procurement.order.create"],
            "chain": [chain_to_mapping(c) for c in chain],
            "chain_grant_ids": list(ids if ids is not None else ("g-root", "g-leaf")[: len(chain)]),
        }
    )


def test_stored_snapshot_association_is_checked():
    from agent_guard.contracts.execution import QuoteItem, TrustedQuoteSnapshot
    from agent_guard.tools.catalog import snapshot_to_bytes

    good = TrustedQuoteSnapshot(
        quote_id="quote-001",
        quote_version="1",
        supplier_id="supplier-001",
        items=(QuoteItem(sku="sku-001", quantity=1, unit_price_fen=70000),),
        total_fen=70000,
    )
    parsed = params.parse_tool_params("procurement.order.create", ORDER_OK)
    assert (
        policy.check_stored_snapshot(
            tool_id=ToolId.ORDER_CREATE,
            params=parsed,
            amount_fen=70000,
            quote_snapshot_bytes=snapshot_to_bytes(good),
        )
        == good
    )

    with pytest.raises(ExecutionError) as excinfo:
        policy.check_stored_snapshot(
            tool_id=ToolId.ORDER_CREATE,
            params=parsed,
            amount_fen=70000,
            quote_snapshot_bytes=None,
        )
    assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID

    wrong_items = TrustedQuoteSnapshot(
        quote_id="quote-001",
        quote_version="1",
        supplier_id="supplier-001",
        items=(QuoteItem(sku="sku-002", quantity=1, unit_price_fen=70000),),
        total_fen=70000,
    )
    with pytest.raises(ExecutionError):
        policy.check_stored_snapshot(
            tool_id=ToolId.ORDER_CREATE,
            params=parsed,
            amount_fen=70000,
            quote_snapshot_bytes=snapshot_to_bytes(wrong_items),
        )

    with pytest.raises(ExecutionError):
        policy.check_stored_snapshot(
            tool_id=ToolId.REQUEST_READ,
            params=params.parse_tool_params(
                "procurement.request.read", b'{"request_id":"req-001"}'
            ),
            amount_fen=5,
            quote_snapshot_bytes=None,
        )
