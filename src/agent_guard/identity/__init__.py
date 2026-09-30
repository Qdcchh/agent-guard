"""Administrator-approved DID identity resolution."""

from agent_guard.identity.resolver import (
    IdentityError,
    IdentityResolver,
    RegisteredIdentity,
    ResolvedIdentity,
    did_web_url,
)

__all__ = [
    "IdentityError",
    "IdentityResolver",
    "RegisteredIdentity",
    "ResolvedIdentity",
    "did_web_url",
]
