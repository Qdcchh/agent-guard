"""A1 execution ledger: real PostgreSQL state store and atomic accept.

Trusted in-process components only. No OAuth/OIDC endpoints, no SM2/SM3, no
HTTP entry point and no downstream execution live here.
"""

from agent_guard.ledger.migrate import MigrationError, applied_versions, apply_migrations
from agent_guard.ledger.provisioning import (
    ProvisioningError,
    TaskAlreadyInitialized,
    create_child_grant,
    create_task_root,
    deactivate_principal,
    register_principal,
    revoke_grant,
)
from agent_guard.ledger.service import ExecutionLedger

__all__ = [
    "ExecutionLedger",
    "MigrationError",
    "ProvisioningError",
    "TaskAlreadyInitialized",
    "apply_migrations",
    "applied_versions",
    "create_child_grant",
    "create_task_root",
    "deactivate_principal",
    "register_principal",
    "revoke_grant",
]
