"""Trusted A2.1 fixtures: catalog, permission snapshots and parameter payloads.

Test assembly only. Building :class:`TrustedPermissionSnapshot` or
:class:`VerifiedInvocation` here is legitimate layered testing and is never a
claim that B's verifier ran or that anything was signed. The catalog data is
synthetic and seeded by the fixture, never uploaded by a request.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass

from agent_guard.contracts.execution import (
    GrantConstraints,
    ToolId,
    TrustedPermissionSnapshot,
)
from agent_guard.execution.service import ExecutionService
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.tools.catalog import (
    CatalogDelivery,
    CatalogDocument,
    CatalogQuote,
    CatalogQuoteLine,
    CatalogRecipient,
    CatalogRequest,
    CatalogTemplate,
    TrustedCatalog,
)
from agent_guard.tools.downstream import MockDownstream
from tests.fixtures.state import TreeFixture

#: Fixture tenant/task/ids mirroring docs 8.3 / 9.4 examples.
TENANT = "tenant-demo"
TASK = "task-001"
SUBJECT = "user-demo-001"
REQUEST_ID = "req-001"
DOCUMENT_ID = "doc-001"
QUOTE_ID = "quote-001"
QUOTE_VERSION = "1"
SUPPLIER_ID = "supplier-001"
SKU = "sku-001"
DELIVERY_ID = "office-001"
TEMPLATE_ID = "order-created"
RECIPIENT_ID = "user-demo-001"
ORDER_AMOUNT_FEN = 70000

#: Independent gateway service secret for the mock downstream (test only).
DOWNSTREAM_SECRET = "test-only-downstream-service-secret"

_jti = itertools.count(1)


# ------------------------------------------------------------- param payloads


def _dump(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def order_params(
    *,
    request_id: str = REQUEST_ID,
    quote_id: str = QUOTE_ID,
    quote_version: str = QUOTE_VERSION,
    items: tuple[tuple[str, int], ...] = ((SKU, 1),),
    delivery_id: str = DELIVERY_ID,
    raw: bytes | None = None,
) -> bytes:
    if raw is not None:
        return raw
    return _dump(
        {
            "request_id": request_id,
            "quote_id": quote_id,
            "quote_version": quote_version,
            "items": [{"sku": sku, "quantity": quantity} for sku, quantity in items],
            "delivery_id": delivery_id,
        }
    )


def read_params(*, request_id: str = REQUEST_ID, raw: bytes | None = None) -> bytes:
    if raw is not None:
        return raw
    return _dump({"request_id": request_id})


def document_params(
    *, request_id: str = REQUEST_ID, document_id: str = DOCUMENT_ID, raw: bytes | None = None
) -> bytes:
    if raw is not None:
        return raw
    return _dump({"request_id": request_id, "document_id": document_id})


def notification_params(
    *,
    template_id: str = TEMPLATE_ID,
    recipient_id: str = RECIPIENT_ID,
    operation_id: str = "operation-ref-1",
    raw: bytes | None = None,
) -> bytes:
    if raw is not None:
        return raw
    return _dump(
        {
            "template_id": template_id,
            "recipient_id": recipient_id,
            "operation_id": operation_id,
        }
    )


# ------------------------------------------------------------------ catalog


def build_catalog(tenant_id: str, task_id: str) -> TrustedCatalog:
    """Seeded synthetic resources: one request/doc/quote/delivery/template/recipient."""
    return TrustedCatalog(
        requests=[
            CatalogRequest(REQUEST_ID, tenant_id, task_id),
            CatalogRequest("req-002", tenant_id, task_id),
        ],
        documents=[CatalogDocument(DOCUMENT_ID, REQUEST_ID)],
        quotes=[
            CatalogQuote(
                QUOTE_ID,
                QUOTE_VERSION,
                SUPPLIER_ID,
                REQUEST_ID,
                (CatalogQuoteLine(SKU, 1, ORDER_AMOUNT_FEN),),
            ),
            CatalogQuote(
                QUOTE_ID,
                "2",
                SUPPLIER_ID,
                REQUEST_ID,
                (CatalogQuoteLine(SKU, 1, ORDER_AMOUNT_FEN),),
            ),
        ],
        deliveries=[CatalogDelivery(DELIVERY_ID, tenant_id, REQUEST_ID)],
        templates=[CatalogTemplate(TEMPLATE_ID)],
        recipients=[CatalogRecipient(RECIPIENT_ID)],
    )


# ---------------------------------------------------------- permission sets


def constraints_for(depth: int, **overrides: object) -> GrantConstraints:
    """Root-first widening chain: every child set is a subset of its parent."""
    base: dict[str, object] = {
        "request_ids": (REQUEST_ID,),
        "document_ids": (DOCUMENT_ID,),
        "quote_versions": (f"{QUOTE_ID}@{QUOTE_VERSION}",),
        "skus": (SKU,),
        "delivery_ids": (DELIVERY_ID,),
        "template_ids": (TEMPLATE_ID,),
        "recipient_ids": (RECIPIENT_ID,),
        "max_quantity": 2,
    }
    widening = {
        0: {
            **base,
            "request_ids": (REQUEST_ID, "req-002"),
            "skus": (SKU, "sku-002"),
            "max_quantity": 4,
        },
        1: {**base, "skus": (SKU, "sku-002"), "max_quantity": 3},
        2: dict(base),
    }
    merged = {**widening[depth], **overrides}
    return GrantConstraints(
        request_ids=tuple(merged["request_ids"]),  # type: ignore[arg-type]
        document_ids=tuple(merged["document_ids"]),  # type: ignore[arg-type]
        quote_versions=tuple(merged["quote_versions"]),  # type: ignore[arg-type]
        skus=tuple(merged["skus"]),  # type: ignore[arg-type]
        delivery_ids=tuple(merged["delivery_ids"]),  # type: ignore[arg-type]
        template_ids=tuple(merged["template_ids"]),  # type: ignore[arg-type]
        recipient_ids=tuple(merged["recipient_ids"]),  # type: ignore[arg-type]
        max_quantity=int(merged["max_quantity"]),  # type: ignore[arg-type]
    )


def path_ids_for(tree: TreeFixture, grant_id: str | None = None) -> tuple[str, ...]:
    """Root-first grant ids of the immutable database path of one grant."""
    target = grant_id or tree.leaf_id
    if target == tree.root_id:
        return (tree.root_id,)
    if target == tree.mid_id:
        return (tree.root_id, tree.mid_id)
    return (tree.root_id, tree.mid_id, tree.leaf_id)


def permission_for(
    tree: TreeFixture,
    *,
    grant_id: str | None = None,
    scope: tuple[str, ...] | None = None,
    chain: tuple[GrantConstraints, ...] | None = None,
    chain_grant_ids: tuple[str, ...] | None = None,
    **overrides: object,
) -> TrustedPermissionSnapshot:
    """Snapshot bound to one grant of ``tree`` with a root-first narrowing chain.

    ``chain_grant_ids`` binds every constraint layer to the grant node it
    describes so the chain cannot be truncated, reordered or spliced: it must
    match the database path node for node.
    """
    target = grant_id or tree.leaf_id
    ids = chain_grant_ids if chain_grant_ids is not None else path_ids_for(tree, target)
    if chain is None:
        chain = tuple(constraints_for(i) for i in range(len(ids)))
    return TrustedPermissionSnapshot(
        grant_id=target,
        root_id=tree.root_id,
        tenant_id=tree.tenant_id,
        task_id=tree.task_id,
        subject=tree.subject,
        scope=scope if scope is not None else tuple(tool.value for tool in ToolId),
        chain=chain,
        chain_grant_ids=ids,
    )


def make_reference_operation(env, *, key: str = "notify-target", settle: bool = False) -> str:
    """A real accepted operation owned by the caller's own grant/holder.

    The notification access policy is deliberately strict (the grant and holder
    that own the referenced operation may target it), so a notification fixture
    must reference a real operation rather than a made-up id.
    """
    inv = env.tree.invocation(
        idempotency_key=key,
        jti=f"jti-{key}",
        tool_id="procurement.request.read",
        params=read_params(),
    )
    operation_id = env.service.accept_invocation(inv, env.permission()).operation_id
    if settle:
        env.service.run_operation(operation_id, owner_token=f"owner-{key}")
    return operation_id


# ------------------------------------------------------------------- bundle


@dataclass
class A2Env:
    """Everything one A2.1 integration test needs, wired to real databases."""

    tree: TreeFixture
    catalog: TrustedCatalog
    service: ExecutionService
    downstream: MockDownstream
    ledger: ExecutionLedger
    gateway_dsn: str
    downstream_dsn: str
    secret: str

    def permission(self, **kwargs: object) -> TrustedPermissionSnapshot:
        return permission_for(self.tree, **kwargs)  # type: ignore[arg-type]

    def invocation(self, **kwargs: object):
        return self.tree.invocation(**kwargs)  # type: ignore[arg-type]


def expire_lease(gateway_dsn: str, operation_id: str) -> None:
    """Move a lease into the past so a takeover can be exercised deterministically.

    The lease lifetime is a real database time condition; tests never sleep for
    it. This helper only moves ``lease_expires_at`` back, exactly as the passage
    of the TTL would, and never touches the owner token or the fencing version.
    """
    import psycopg

    with psycopg.connect(gateway_dsn, connect_timeout=5) as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE ag_execution_leases SET lease_expires_at = clock_timestamp() "
                "- interval '1 second' WHERE operation_id = %s",
                (operation_id,),
            )


def build_env(
    *,
    tree: TreeFixture,
    gateway_dsn: str,
    downstream_dsn: str,
    secret: str = DOWNSTREAM_SECRET,
    approved_suppliers: frozenset[str] | set[str] = (SUPPLIER_ID,),
    approved_recipients: frozenset[str] | set[str] = (RECIPIENT_ID,),
    served_requests: frozenset[str] | set[str] = (REQUEST_ID,),
    lease_ttl_seconds: int = 30,
    catalog: TrustedCatalog | None = None,
    downstream: MockDownstream | None = None,
) -> A2Env:
    catalog = catalog if catalog is not None else build_catalog(tree.tenant_id, tree.task_id)
    downstream = (
        downstream
        if downstream is not None
        else MockDownstream(
            downstream_dsn,
            service_secret=secret,
            approved_suppliers=approved_suppliers,
            approved_recipients=approved_recipients,
            served_requests=served_requests,
        )
    )
    ledger = ExecutionLedger(gateway_dsn)
    service = ExecutionService(
        gateway_dsn=gateway_dsn,
        ledger=ledger,
        catalog=catalog,
        downstream=downstream,
        downstream_secret=secret,
        lease_ttl_seconds=lease_ttl_seconds,
    )
    return A2Env(
        tree=tree,
        catalog=catalog,
        service=service,
        downstream=downstream,
        ledger=ledger,
        gateway_dsn=gateway_dsn,
        downstream_dsn=downstream_dsn,
        secret=secret,
    )
