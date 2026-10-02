"""Layered resource authorization for the four tools (A2.1 core).

This is the *trusted-object* layer required by ``A2-P15-CORE``: it checks the
trusted permission snapshot's scope, the complete root-to-leaf narrowing chain
and the trusted resource associations of the catalog. It is **not** signature
verification, not B's permission-snapshot contract and not a substitute for the
A1 dynamic accept checks (revocation, expiry, holder binding, proof freshness),
which still run afterwards inside the accept transaction.

Every rejection is explicit and side-effect free: a refused call reserves
nothing, executes nothing and leaks nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from agent_guard.contracts.execution import (
    DocumentReadParams,
    ExecutionError,
    ExecutionErrorCode,
    GrantConstraints,
    NotificationSendParams,
    OrderCreateParams,
    RequestReadParams,
    ToolId,
    TrustedPermissionSnapshot,
    TrustedQuoteSnapshot,
)
from agent_guard.contracts.ledger import MAX_SAFE_INT
from agent_guard.tools.catalog import (
    CatalogDocument,
    CatalogRequest,
    TrustedCatalog,
    snapshot_from_bytes,
)

#: The seven mandatory ``ag_constraints`` set fields plus ``max_quantity``.
_CONSTRAINT_SETS = (
    "request_ids",
    "document_ids",
    "quote_versions",
    "skus",
    "delivery_ids",
    "template_ids",
    "recipient_ids",
)

#: Mapping keys accepted by :func:`constraints_from_mapping`.
_CONSTRAINT_FIELDS = frozenset(_CONSTRAINT_SETS) | {"max_quantity"}

#: Mapping keys accepted by :func:`permission_snapshot_from_mapping`.
_SNAPSHOT_FIELDS = frozenset(
    {
        "grant_id",
        "root_id",
        "tenant_id",
        "task_id",
        "subject",
        "scope",
        "chain",
        "chain_grant_ids",
    }
)


def _fail(detail: str, code: ExecutionErrorCode = ExecutionErrorCode.INVALID_PARAMS):
    return ExecutionError(code, detail)


# ---------------------------------------------------------- strict builders


def constraints_from_mapping(data: Mapping[str, object]) -> GrantConstraints:
    """Build :class:`GrantConstraints`, refusing missing/extra/mistyped fields.

    A missing set field is a format error; an *empty* set is legal and means
    "no corresponding resource is allowed" (never "unlimited").
    """
    if not isinstance(data, Mapping):
        raise _fail("constraints must be a mapping")
    missing = _CONSTRAINT_FIELDS - set(data)
    if missing:
        raise _fail(f"constraints missing fields: {sorted(missing)}")
    extra = set(data) - _CONSTRAINT_FIELDS
    if extra:
        raise _fail(f"constraints have unknown fields: {sorted(extra)}")

    parsed: dict[str, object] = {}
    for name in _CONSTRAINT_SETS:
        raw = data[name]
        if not isinstance(raw, (list, tuple)):
            raise _fail(f"constraints.{name} must be a list of strings")
        values: list[str] = []
        seen: set[str] = set()
        for entry in raw:
            if not isinstance(entry, str) or entry == "":
                raise _fail(f"constraints.{name} entries must be non-empty strings")
            if entry in seen:
                raise _fail(f"constraints.{name} has duplicate entry: {entry}")
            seen.add(entry)
            values.append(entry)
        parsed[name] = tuple(values)

    max_quantity = data["max_quantity"]
    if isinstance(max_quantity, bool) or not isinstance(max_quantity, int):
        raise _fail("constraints.max_quantity must be an integer (bool/float rejected)")
    if max_quantity < 0 or max_quantity > MAX_SAFE_INT:
        raise _fail("constraints.max_quantity out of range")
    parsed["max_quantity"] = max_quantity
    return GrantConstraints(**parsed)  # type: ignore[arg-type]


def permission_snapshot_from_mapping(data: Mapping[str, object]) -> TrustedPermissionSnapshot:
    """Build the trusted fixture snapshot, refusing missing/extra fields."""
    if not isinstance(data, Mapping):
        raise _fail("permission snapshot must be a mapping")
    missing = _SNAPSHOT_FIELDS - set(data)
    if missing:
        raise _fail(f"permission snapshot missing fields: {sorted(missing)}")
    extra = set(data) - _SNAPSHOT_FIELDS
    if extra:
        raise _fail(f"permission snapshot has unknown fields: {sorted(extra)}")
    chain_raw = data["chain"]
    if not isinstance(chain_raw, (list, tuple)) or not chain_raw:
        raise _fail("permission snapshot chain must be a non-empty list")
    chain = tuple(constraints_from_mapping(entry) for entry in chain_raw)
    ids_raw = data["chain_grant_ids"]
    if not isinstance(ids_raw, (list, tuple)) or not ids_raw:
        raise _fail("permission snapshot chain_grant_ids must be a non-empty list")
    chain_grant_ids = tuple(ids_raw)
    if len(chain_grant_ids) != len(chain):
        raise _fail("permission snapshot chain and chain_grant_ids must have equal length")
    for entry in chain_grant_ids:
        if not isinstance(entry, str) or entry == "":
            raise _fail("permission snapshot chain_grant_ids entries must be non-empty strings")
    if len(set(chain_grant_ids)) != len(chain_grant_ids):
        raise _fail("permission snapshot chain_grant_ids must be unique")
    scope_raw = data["scope"]
    if not isinstance(scope_raw, (list, tuple)):
        raise _fail("permission snapshot scope must be a list of tool ids")
    scope: list[str] = []
    for entry in scope_raw:
        if not isinstance(entry, str) or entry == "":
            raise _fail("permission snapshot scope entries must be non-empty strings")
        scope.append(entry)
    return TrustedPermissionSnapshot(
        grant_id=str(data["grant_id"]),
        root_id=str(data["root_id"]),
        tenant_id=str(data["tenant_id"]),
        task_id=str(data["task_id"]),
        subject=str(data["subject"]),
        scope=tuple(scope),
        chain=chain,
        chain_grant_ids=chain_grant_ids,
    )


# ------------------------------------------------------------- scope/chain


def check_snapshot_binding(
    snapshot: TrustedPermissionSnapshot,
    *,
    grant_id: str,
    root_id: str,
    tenant_id: str,
    task_id: str,
    subject: str,
) -> None:
    """A snapshot for another grant/task/tenant/subject is never reused."""
    if snapshot.grant_id != grant_id:
        raise _fail(
            "permission snapshot is for another grant", ExecutionErrorCode.CONSTRAINT_MISMATCH
        )
    if snapshot.root_id != root_id:
        raise _fail(
            "permission snapshot is for another root", ExecutionErrorCode.CONSTRAINT_MISMATCH
        )
    if snapshot.tenant_id != tenant_id:
        raise _fail(
            "permission snapshot is for another tenant", ExecutionErrorCode.CONSTRAINT_MISMATCH
        )
    if snapshot.task_id != task_id:
        raise _fail(
            "permission snapshot is for another task", ExecutionErrorCode.CONSTRAINT_MISMATCH
        )
    if snapshot.subject != subject:
        raise _fail(
            "permission snapshot is for another subject", ExecutionErrorCode.CONSTRAINT_MISMATCH
        )


def check_scope(snapshot: TrustedPermissionSnapshot, tool_id: ToolId) -> None:
    """An empty scope forbids every tool; unknown/absent tools are refused."""
    if tool_id.value not in snapshot.scope:
        raise ExecutionError(
            ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
            f"tool not in granted scope: {tool_id.value}",
        )


def _subset(child: tuple[str, ...], parent: tuple[str, ...]) -> bool:
    return set(child) <= set(parent)


def check_chain_against_path(
    snapshot: TrustedPermissionSnapshot,
    db_path: tuple[str, ...],
) -> None:
    """Bind the trusted chain to the immutable database parent chain.

    ``db_path`` is the root-first grant id list read from the database. The
    supplied chain must describe **exactly** that path: same length, same nodes
    in the same order, ending at the leaf and starting at the root. A chain that
    drops a restrictive ancestor, reorders layers, splices another path or pads
    the depth is refused, so a caller can never bypass an ancestor's limits by
    simply not supplying them.
    """
    if not db_path:
        raise _fail("database grant path must not be empty", ExecutionErrorCode.CONSTRAINT_MISMATCH)
    supplied = snapshot.chain_grant_ids
    if len(snapshot.chain) != len(db_path):
        raise _fail(
            "permission chain length does not match the database grant path",
            ExecutionErrorCode.CONSTRAINT_MISMATCH,
        )
    if len(supplied) != len(db_path):
        raise _fail(
            "permission chain_grant_ids length does not match the database grant path",
            ExecutionErrorCode.CONSTRAINT_MISMATCH,
        )
    for position, (supplied_id, db_id) in enumerate(zip(supplied, db_path, strict=False)):
        if supplied_id != db_id:
            raise _fail(
                f"permission chain layer {position} does not bind to the database path",
                ExecutionErrorCode.CONSTRAINT_MISMATCH,
            )
    if supplied[0] != snapshot.root_id:
        raise _fail(
            "permission chain does not start at the declared root",
            ExecutionErrorCode.CONSTRAINT_MISMATCH,
        )
    if supplied[-1] != snapshot.grant_id:
        raise _fail(
            "permission chain does not end at the declared grant",
            ExecutionErrorCode.CONSTRAINT_MISMATCH,
        )


def check_narrowing(chain: tuple[GrantConstraints, ...]) -> None:
    """Every child constraint set is a subset of its parent, never expanding.

    ``max_quantity`` may only stay equal or decrease down the chain. The chain
    is root-first and must contain at least the root and the leaf.
    """
    if not chain:
        raise _fail("constraint chain must not be empty", ExecutionErrorCode.CONSTRAINT_MISMATCH)
    for index in range(1, len(chain)):
        parent, child = chain[index - 1], chain[index]
        for name in _CONSTRAINT_SETS:
            if not _subset(getattr(child, name), getattr(parent, name)):
                raise _fail(
                    f"child {name} is not a subset of its parent",
                    ExecutionErrorCode.CONSTRAINT_MISMATCH,
                )
        if child.max_quantity > parent.max_quantity:
            raise _fail(
                "child max_quantity must not exceed the parent",
                ExecutionErrorCode.CONSTRAINT_MISMATCH,
            )


def _require_member(name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ExecutionError(
            ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
            f"{name} is not in the granted set: {value}",
        )


def _require_quote_member(quote_id: str, quote_version: str, allowed: tuple[str, ...]) -> None:
    key = f"{quote_id}@{quote_version}"
    if key not in allowed:
        raise ExecutionError(
            ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
            f"quote version is not in the granted set: {key}",
        )


# --------------------------------------------------------- per-tool checks


def check_static_authorization(
    snapshot: TrustedPermissionSnapshot,
    *,
    grant_id: str,
    root_id: str,
    tenant_id: str,
    task_id: str,
    subject: str,
    tool_id: ToolId,
    params: RequestReadParams | DocumentReadParams | OrderCreateParams | NotificationSendParams,
    db_path: tuple[str, ...] | None = None,
) -> None:
    """Schema/static authorization and trusted-set checks only.

    Runs before any candidate lookup and never requires a *current* quote to
    exist: it only looks at the trusted permission snapshot and the immutable
    database parent chain. Failures here are hard rejections with zero
    reservation and zero effect. When ``db_path`` is supplied the chain must
    bind to it node for node, so a truncated or spliced chain cannot be used to
    skip a restrictive ancestor.
    """
    check_snapshot_binding(
        snapshot,
        grant_id=grant_id,
        root_id=root_id,
        tenant_id=tenant_id,
        task_id=task_id,
        subject=subject,
    )
    if db_path is not None:
        check_chain_against_path(snapshot, db_path)
    check_narrowing(snapshot.chain)
    check_scope(snapshot, tool_id)
    leaf = snapshot.chain[-1]

    if isinstance(params, RequestReadParams):
        _require_member("request_id", params.request_id, leaf.request_ids)
    elif isinstance(params, DocumentReadParams):
        _require_member("request_id", params.request_id, leaf.request_ids)
        _require_member("document_id", params.document_id, leaf.document_ids)
    elif isinstance(params, OrderCreateParams):
        _require_member("request_id", params.request_id, leaf.request_ids)
        _require_quote_member(params.quote_id, params.quote_version, leaf.quote_versions)
        for item in params.items:
            _require_member("sku", item.sku, leaf.skus)
            if item.quantity > leaf.max_quantity:
                raise ExecutionError(
                    ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
                    f"quantity {item.quantity} exceeds max_quantity {leaf.max_quantity}",
                )
        _require_member("delivery_id", params.delivery_id, leaf.delivery_ids)
    else:
        _require_member("template_id", params.template_id, leaf.template_ids)
        _require_member("recipient_id", params.recipient_id, leaf.recipient_ids)


#: ``(tenant_id, task_id, grant_id, holder_client_id, holder_kid)`` of a
#: referenced operation, or ``None`` when it does not exist.
OperationAccessFacts = tuple[str, str, str, str, str]


def check_operation_access(
    facts: OperationAccessFacts | None,
    *,
    tenant_id: str,
    task_id: str,
    grant_id: str,
    holder_client_id: str,
    holder_kid: str,
) -> None:
    """Trusted access check for a notification's referenced operation.

    Deliberately the *strict minimal* policy from the query boundary: only the
    grant and holder that own the referenced operation may target it. A
    different grant is refused rather than assumed to have access; widening this
    requires an explicit trusted policy decision first. The lookup is a trusted
    database read of persisted accept facts, never anything the request body
    claims about itself.
    """
    if facts is None:
        raise ExecutionError(
            ExecutionErrorCode.RESOURCE_NOT_FOUND,
            "referenced operation does not exist",
        )
    ref_tenant, ref_task, ref_grant, ref_client, ref_kid = facts
    if ref_tenant != tenant_id or ref_task != task_id:
        raise ExecutionError(
            ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
            "referenced operation belongs to another tenant/task",
        )
    if ref_grant != grant_id:
        raise ExecutionError(
            ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
            "referenced operation is not accessible to this grant",
        )
    if ref_client != holder_client_id or ref_kid != holder_kid:
        raise ExecutionError(
            ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
            "referenced operation is not accessible to this holder",
        )


def resolve_tool_resources(
    catalog: TrustedCatalog,
    *,
    tenant_id: str,
    task_id: str,
    tool_id: ToolId,
    params: RequestReadParams | DocumentReadParams | OrderCreateParams | NotificationSendParams,
    operation_facts: Callable[[str], OperationAccessFacts | None] | None = None,
    caller_grant_id: str | None = None,
    caller_holder_client_id: str | None = None,
    caller_holder_kid: str | None = None,
) -> TrustedQuoteSnapshot | None:
    """Trusted resource and quote resolution for a NEW intent.

    Any failure here (unknown resource, broken association, missing or invalid
    quote, inaccessible notification target) is a resolution failure: the caller
    must safely re-check the candidate lookup before rejecting, because a
    concurrent accept may already have committed this business key.
    """
    if isinstance(params, RequestReadParams):
        _lookup_request(catalog, tenant_id=tenant_id, task_id=task_id, request_id=params.request_id)
        return None

    if isinstance(params, DocumentReadParams):
        _lookup_request(catalog, tenant_id=tenant_id, task_id=task_id, request_id=params.request_id)
        _lookup_document(catalog, request_id=params.request_id, document_id=params.document_id)
        return None

    if isinstance(params, OrderCreateParams):
        _lookup_request(catalog, tenant_id=tenant_id, task_id=task_id, request_id=params.request_id)
        return catalog.build_order_snapshot(
            tenant_id=tenant_id,
            task_id=task_id,
            request_id=params.request_id,
            quote_id=params.quote_id,
            quote_version=params.quote_version,
            items=tuple((item.sku, item.quantity) for item in params.items),
            delivery_id=params.delivery_id,
        )

    if catalog.get_template(params.template_id) is None:
        raise ExecutionError(
            ExecutionErrorCode.RESOURCE_NOT_FOUND,
            f"unknown template_id: {params.template_id}",
        )
    if catalog.get_recipient(params.recipient_id) is None:
        raise ExecutionError(
            ExecutionErrorCode.RESOURCE_NOT_FOUND,
            f"unknown recipient_id: {params.recipient_id}",
        )
    # The referenced operation is a real persisted fact that must be checked
    # against the caller's own grant/holder before anything is reserved.
    if operation_facts is None or caller_grant_id is None:
        raise ExecutionError(
            ExecutionErrorCode.TRUSTED_DEPENDENCY_UNAVAILABLE,
            "operation access resolver is not configured",
        )
    check_operation_access(
        operation_facts(params.operation_id),
        tenant_id=tenant_id,
        task_id=task_id,
        grant_id=caller_grant_id,
        holder_client_id=caller_holder_client_id or "",
        holder_kid=caller_holder_kid or "",
    )
    return None


def check_stored_snapshot(
    *,
    tool_id: ToolId,
    params: RequestReadParams | DocumentReadParams | OrderCreateParams | NotificationSendParams,
    amount_fen: int,
    quote_snapshot_bytes: bytes | None,
) -> TrustedQuoteSnapshot | None:
    """Validate the *persisted* accept facts of a candidate against its params.

    This is the "original snapshot association" check: the immutable stored
    snapshot must still describe exactly what was accepted. A missing, malformed
    or mismatching snapshot is ``LEGACY_SNAPSHOT_INVALID`` so the caller can
    quarantine the operation instead of back-filling it from a current quote.
    """
    if tool_id is ToolId.ORDER_CREATE:
        snapshot = snapshot_from_bytes(quote_snapshot_bytes)
        if snapshot is None:
            raise ExecutionError(
                ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
                "accepted order has no persisted quote snapshot",
            )
        if not isinstance(params, OrderCreateParams):
            raise ExecutionError(ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID, "tool/params mismatch")
        expected = {(item.sku, item.quantity) for item in params.items}
        actual = {(item.sku, item.quantity) for item in snapshot.items}
        if expected != actual or len(snapshot.items) != len(params.items):
            raise ExecutionError(
                ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
                "persisted quote snapshot does not match the accepted items",
            )
        if snapshot.total_fen != amount_fen:
            raise ExecutionError(
                ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
                "persisted quote snapshot total does not match the reserved amount",
            )
        return snapshot

    if quote_snapshot_bytes is not None:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            "zero-amount tool must not carry a quote snapshot",
        )
    if amount_fen != 0:
        raise ExecutionError(
            ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
            "zero-amount tool has a non-zero reserved amount",
        )
    return None


def check_evidence_complete(*, digests: tuple[str, ...]) -> None:
    """First-accept evidence must be present before anything is executed."""
    for value in digests:
        if not isinstance(value, str) or value == "":
            raise ExecutionError(
                ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID,
                "persisted first-accept evidence is incomplete",
            )


def authorize_tool_call(
    snapshot: TrustedPermissionSnapshot,
    *,
    grant_id: str,
    root_id: str,
    tenant_id: str,
    task_id: str,
    subject: str,
    tool_id: ToolId,
    params: RequestReadParams | DocumentReadParams | OrderCreateParams | NotificationSendParams,
    catalog: TrustedCatalog,
    db_path: tuple[str, ...] | None = None,
    operation_facts: Callable[[str], OperationAccessFacts | None] | None = None,
    caller_holder_client_id: str | None = None,
    caller_holder_kid: str | None = None,
) -> TrustedQuoteSnapshot | None:
    """Convenience wrapper: static checks plus resource/quote resolution."""
    check_static_authorization(
        snapshot,
        grant_id=grant_id,
        root_id=root_id,
        tenant_id=tenant_id,
        task_id=task_id,
        subject=subject,
        tool_id=tool_id,
        params=params,
        db_path=db_path,
    )
    return resolve_tool_resources(
        catalog,
        tenant_id=tenant_id,
        task_id=task_id,
        tool_id=tool_id,
        params=params,
        operation_facts=operation_facts,
        caller_grant_id=grant_id,
        caller_holder_client_id=caller_holder_client_id,
        caller_holder_kid=caller_holder_kid,
    )


def _lookup_request(
    catalog: TrustedCatalog,
    *,
    tenant_id: str,
    task_id: str,
    request_id: str,
) -> CatalogRequest:
    request = catalog.get_request(request_id)
    if request is None:
        raise ExecutionError(
            ExecutionErrorCode.RESOURCE_NOT_FOUND, f"unknown request_id: {request_id}"
        )
    if request.tenant_id != tenant_id or request.task_id != task_id:
        raise ExecutionError(
            ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
            "request belongs to another tenant/task",
        )
    return request


def _lookup_document(
    catalog: TrustedCatalog,
    *,
    request_id: str,
    document_id: str,
) -> CatalogDocument:
    document = catalog.get_document(document_id)
    if document is None:
        raise ExecutionError(
            ExecutionErrorCode.RESOURCE_NOT_FOUND, f"unknown document_id: {document_id}"
        )
    if document.request_id != request_id:
        raise ExecutionError(
            ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
            "document is not bound to this procurement request",
        )
    return document
