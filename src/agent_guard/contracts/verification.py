"""In-process signed-source bundle; never an HTTP-deserializable credential."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent_guard.contracts.execution import TrustedPermissionSnapshot
from agent_guard.contracts.ledger import VerifiedInvocation

if TYPE_CHECKING:
    from agent_guard.authorization.permission_snapshot import PermissionSource


@dataclass(frozen=True)
class VerifiedInvocationBundle:
    invocation: VerifiedInvocation
    permissions: TrustedPermissionSnapshot
    evidence_ref: str
    source: PermissionSource
