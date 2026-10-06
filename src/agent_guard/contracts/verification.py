"""In-process signed-source bundle; never an HTTP-deserializable credential."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent_guard.contracts.execution import TrustedPermissionSnapshot, VerifiedResultQuery
from agent_guard.contracts.ledger import VerifiedInvocation

if TYPE_CHECKING:
    from agent_guard.authorization.permission_snapshot import PermissionSource


@dataclass(frozen=True)
class VerifiedInvocationBundle:
    invocation: VerifiedInvocation
    permissions: TrustedPermissionSnapshot
    evidence_ref: str
    source: PermissionSource


@dataclass(frozen=True)
class VerifiedQueryBundle:
    """Signed query, immutable permission source and exact staged raw evidence."""

    query: VerifiedResultQuery
    permissions: TrustedPermissionSnapshot
    evidence_ref: str
    source: PermissionSource
