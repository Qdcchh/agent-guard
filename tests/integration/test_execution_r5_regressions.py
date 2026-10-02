"""A2.1 correction-r4 regressions: whole-string quote_version enforcement.

Formal tests for the two items still open after review-r7:

* **A21-R2-SNAPSHOT** residual — ``tools/params.py`` matched the quote version
  by *prefix*, so ``01``/``00``/``1x``/``1@2``/``1 2``/``1.0``/``1e2`` and
  over-length strings were parsed and could reserve. All three version
  validators now share one whole-string rule.
* **DOC-CKPT1-01** — reported separately (``tasks/A2-report.md``).

The accept-entry negatives deliberately give the trusted permission set *and*
the trusted catalog the very same illegal version, so a rejection proves the
rule is a **format** rule and not a missing-resource / missing-permission rule.
Everything is refused *before* the candidate lookup: no proof, budget,
operation, event, outbox row or downstream effect is ever created.
"""

from __future__ import annotations

import json

import psycopg
import pytest

from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode, ToolId
from agent_guard.tools.catalog import (
    CatalogDelivery,
    CatalogQuote,
    CatalogQuoteLine,
    CatalogRequest,
    snapshot_from_bytes,
)
from agent_guard.tools.params import parse_tool_params
from agent_guard.tools.results import parse_result
from tests.fixtures.dbstate import fetch_counters, fetch_counts
from tests.fixtures.execution import (
    ORDER_AMOUNT_FEN,
    REQUEST_ID,
    build_env,
    constraints_for,
    order_params,
)

pytestmark = pytest.mark.integration

#: Every version that the whole-string rule must refuse.
ILLEGAL_VERSIONS = (
    "0",
    "00",
    "01",
    "007",
    "1x",
    "1@2",
    "1 2",
    "1.0",
    "1e2",
    "1/2",
    "-1",
    "+1",
    "",
    " ",
    "1\n",
    "0\n",
    "1\r",
    "\x00",
    "1" * 19,  # one over the defined 18-digit limit
    "٠١",  # non-ASCII digits
)

#: The defined length limit is 18 digits (``[1-9][0-9]{0,17}``).
LEGAL_VERSIONS = ("1", "2", "10", "9" * 18)


def _order_raw(version: str) -> bytes:
    return (
        b'{"request_id":"req-001","quote_id":"quote-001","quote_version":'
        + json.dumps(version).encode()
        + b',"items":[{"sku":"sku-001","quantity":1}],"delivery_id":"office-001"}'
    )


def _snapshot_raw(version: str) -> bytes:
    return json.dumps(
        {
            "quote_id": "quote-001",
            "quote_version": version,
            "supplier_id": "supplier-001",
            "items": [{"sku": "sku-001", "quantity": 1, "unit_price_fen": 70000}],
            "total_fen": 70000,
            "currency": "CNY",
        }
    ).encode()


def _result_raw(version: str) -> bytes:
    return json.dumps(
        {
            "kind": "order",
            "operation_id": "op-1",
            "order_id": "order-1",
            "supplier_id": "supplier-001",
            "quote_id": "quote-001",
            "quote_version": version,
            "items": [{"sku": "sku-001", "quantity": 1, "unit_price_fen": 70000}],
            "total_fen": 70000,
        },
        separators=(",", ":"),
    ).encode()


# ------------------------------------------------------------- parser layer


@pytest.mark.parametrize("version", ILLEGAL_VERSIONS)
def test_params_quote_version_rejects_every_non_decimal_positive_string(version):
    """A21-R2-SNAPSHOT: the order params parser uses a whole-string rule."""
    with pytest.raises(ExecutionError) as excinfo:
        parse_tool_params(ToolId.ORDER_CREATE, _order_raw(version))
    assert excinfo.value.code is ExecutionErrorCode.INVALID_PARAMS, version


@pytest.mark.parametrize("version", LEGAL_VERSIONS)
def test_params_quote_version_accepts_the_defined_legal_strings(version):
    parsed = parse_tool_params(ToolId.ORDER_CREATE, _order_raw(version))
    assert parsed.quote_version == version


@pytest.mark.parametrize("version", ILLEGAL_VERSIONS)
def test_stored_snapshot_quote_version_uses_the_same_rule(version):
    """A21-R2-SNAPSHOT: the stored-snapshot decoder agrees with the parser."""
    with pytest.raises(ExecutionError) as excinfo:
        snapshot_from_bytes(_snapshot_raw(version))
    assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID, version


@pytest.mark.parametrize("version", LEGAL_VERSIONS)
def test_stored_snapshot_quote_version_accepts_the_same_legal_strings(version):
    assert snapshot_from_bytes(_snapshot_raw(version)) is not None


@pytest.mark.parametrize("version", ILLEGAL_VERSIONS)
def test_result_quote_version_uses_the_same_rule(version):
    """A21-R2-SNAPSHOT: the result schema applies the same whole-string rule."""
    with pytest.raises(ExecutionError) as excinfo:
        parse_result(_result_raw(version))
    assert excinfo.value.code is ExecutionErrorCode.DOWNSTREAM_INCONSISTENT, version


@pytest.mark.parametrize("version", LEGAL_VERSIONS)
def test_result_quote_version_accepts_the_same_legal_strings(version):
    record = parse_result(_result_raw(version))
    assert record.quote_version == version


# ------------------------------------------------------- accept-entry layer


def _seed_catalog_with_version(env, version: str) -> None:
    """Put the very same (possibly illegal) version in the trusted catalog."""
    env.catalog.add_request(CatalogRequest(REQUEST_ID, env.tree.tenant_id, env.tree.task_id))
    env.catalog.add_quote(
        CatalogQuote(
            "quote-001",
            version,
            "supplier-001",
            REQUEST_ID,
            (CatalogQuoteLine("sku-001", 1, ORDER_AMOUNT_FEN),),
        )
    )
    env.catalog.add_delivery(CatalogDelivery("office-001", env.tree.tenant_id, REQUEST_ID))


def _permission_with_version(a2, version: str):
    """Permission sets deliberately grant the very same (illegal) version."""
    return a2.permission(
        chain=tuple(
            constraints_for(
                depth,
                quote_versions=(f"quote-001@{version}",),
                skus=("sku-001", "sku-002"),
            )
            for depth in range(3)
        )
    )


@pytest.mark.parametrize("version", ILLEGAL_VERSIONS)
def test_accept_entry_refuses_an_illegal_version_before_any_state(a2, version):
    """A21-R2-SNAPSHOT: format, not availability, is what refuses the version.

    Both the trusted catalog and the trusted permission set contain the exact
    illegal version, so the request is refused for its *format*. The refusal
    happens before the candidate lookup, and no proof, budget, operation,
    event, outbox row or downstream effect is created.
    """
    env = build_env(tree=a2.tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)
    _seed_catalog_with_version(env, version)
    permission = _permission_with_version(a2, version)

    baseline_counts = fetch_counts(a2.gateway_dsn)
    baseline_counters = {
        grant_id: fetch_counters(a2.gateway_dsn, grant_id)
        for grant_id in (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id)
    }
    lookups: list[bool] = []
    original_find = env.service._find_candidate

    def counting_find(verified, _orig=original_find, _calls=lookups):
        _calls.append(True)
        return _orig(verified)

    env.service._find_candidate = counting_find  # type: ignore[method-assign]

    with pytest.raises(ExecutionError) as excinfo:
        env.service.accept_invocation(
            a2.tree.invocation(
                idempotency_key=f"ver-{version!r}",
                tool_id=ToolId.ORDER_CREATE.value,
                params=order_params(quote_version=version),
            ),
            permission,
        )
    # the format rule fires first, with the plain parser error
    assert excinfo.value.code is ExecutionErrorCode.INVALID_PARAMS, version
    # the candidate lookup is never reached
    assert lookups == [], lookups
    # zero new state of any kind
    assert fetch_counts(a2.gateway_dsn) == baseline_counts
    for grant_id, expected in baseline_counters.items():
        assert fetch_counters(a2.gateway_dsn, grant_id) == expected
    with psycopg.connect(a2.downstream_dsn) as conn:
        for table in ("ds_operations", "ds_orders", "ds_notifications"):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


@pytest.mark.parametrize("version", LEGAL_VERSIONS)
def test_accept_entry_still_accepts_the_defined_legal_versions(a2, version):
    """A21-R2-SNAPSHOT: the legal maximum and small versions still work end to end."""
    env = build_env(tree=a2.tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)
    _seed_catalog_with_version(env, version)
    permission = _permission_with_version(a2, version)
    accepted = env.service.accept_invocation(
        a2.tree.invocation(
            idempotency_key=f"ver-ok-{version}",
            tool_id=ToolId.ORDER_CREATE.value,
            params=order_params(quote_version=version),
        ),
        permission,
    )
    assert accepted.disposition.value == "CREATED"
    assert accepted.cost.quote_version == version
    assert accepted.cost.amount_fen == ORDER_AMOUNT_FEN
    counts = fetch_counts(a2.gateway_dsn)
    assert counts["ag_operations"] == 1
    assert counts["ag_proofs"] == 1
    assert counts["ag_ledger_events"] == 1
    counters = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    assert counters["amount_reserved"] == ORDER_AMOUNT_FEN
    assert counters["calls_reserved"] == 1


def test_illegal_version_in_a_stored_snapshot_is_quarantined(a2):
    """A21-R2-SNAPSHOT: legacy material carrying an illegal version is isolated."""
    from agent_guard.contracts.ledger import TrustedCost

    operation_id = a2.ledger.accept(
        a2.tree.invocation(
            idempotency_key="ver-legacy",
            tool_id=ToolId.ORDER_CREATE.value,
            params=order_params(),
        ),
        TrustedCost(
            70000,
            quote_id="quote-001",
            quote_version="01",
            quote_snapshot=_snapshot_raw("01"),
        ),
    ).operation_id
    before = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    with pytest.raises(ExecutionError) as excinfo:
        a2.service.run_operation(operation_id, owner_token="ver-legacy")
    assert excinfo.value.code is ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID
    assert a2.service.review_flag(operation_id) is not None
    assert fetch_counters(a2.gateway_dsn, a2.tree.root_id) == before
    with psycopg.connect(a2.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_operations").fetchone()[0] == 0


# ------------------------------------------------- preserved behaviour


def test_quote_deletion_still_yields_the_original_cost(a2):
    """A21-R2-SNAPSHOT: nothing about the version rule changes P11 semantics."""
    from agent_guard.contracts.ledger import AcceptDisposition

    env = build_env(tree=a2.tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)
    _seed_catalog_with_version(env, "1")
    permission = _permission_with_version(a2, "1")
    first = env.service.accept_invocation(
        a2.tree.invocation(
            idempotency_key="ver-delete",
            jti="jti-ver-delete-1",
            tool_id=ToolId.ORDER_CREATE.value,
            params=order_params(),
        ),
        permission,
    )
    assert first.disposition is AcceptDisposition.CREATED
    original = first.cost.quote_snapshot

    env.catalog.remove_quote("quote-001", "1")
    retried = env.service.accept_invocation(
        a2.tree.invocation(
            idempotency_key="ver-delete",
            jti="jti-ver-delete-2",
            tool_id=ToolId.ORDER_CREATE.value,
            params=order_params(),
        ),
        permission,
    )
    assert retried.disposition is AcceptDisposition.EXISTING
    assert retried.operation_id == first.operation_id
    assert retried.cost.quote_snapshot == original
    assert retried.cost.amount_fen == ORDER_AMOUNT_FEN
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 1
