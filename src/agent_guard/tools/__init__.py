"""Trusted tools layer: strict parameters, resources/quotes, mock downstream.

No cryptography, no HTTP entry point and no client-declared cost live here.
See ``agent_guard.contracts.execution`` for the shared trusted types and
``agent_guard.execution`` for the gateway lifecycle on top of this layer.
"""

from agent_guard.tools.catalog import (
    CURRENCY,
    CatalogDelivery,
    CatalogDocument,
    CatalogQuote,
    CatalogQuoteLine,
    CatalogRecipient,
    CatalogRequest,
    CatalogTemplate,
    TrustedCatalog,
    snapshot_from_bytes,
    snapshot_to_bytes,
    snapshots_equal,
)
from agent_guard.tools.downstream import MockDownstream
from agent_guard.tools.params import parse_tool_id, parse_tool_params, parse_tool_version
from agent_guard.tools.policy import (
    authorize_tool_call,
    check_evidence_complete,
    check_narrowing,
    check_scope,
    check_snapshot_binding,
    check_static_authorization,
    check_stored_snapshot,
    constraints_from_mapping,
    permission_snapshot_from_mapping,
    resolve_tool_resources,
)

__all__ = [
    "CURRENCY",
    "CatalogDelivery",
    "CatalogDocument",
    "CatalogQuote",
    "CatalogQuoteLine",
    "CatalogRecipient",
    "CatalogRequest",
    "CatalogTemplate",
    "MockDownstream",
    "TrustedCatalog",
    "authorize_tool_call",
    "check_evidence_complete",
    "check_narrowing",
    "check_scope",
    "check_snapshot_binding",
    "check_static_authorization",
    "check_stored_snapshot",
    "constraints_from_mapping",
    "parse_tool_id",
    "parse_tool_params",
    "parse_tool_version",
    "permission_snapshot_from_mapping",
    "resolve_tool_resources",
    "snapshot_from_bytes",
    "snapshot_to_bytes",
    "snapshots_equal",
]
