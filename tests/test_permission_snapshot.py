"""Trusted-provider configuration rejects guessed/mismatched historical key identity."""

import pytest

from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
from agent_guard.identity.resolver import RegisteredIdentity


@pytest.mark.parametrize("mismatch", ["tenant", "client", "kid", "object"])
def test_historical_registration_is_keyed_by_exact_identity(mismatch):
    key = generate_sm2_private_key()
    registration = RegisteredIdentity(
        "tenant",
        "client",
        "did:web:id.test",
        "did:web:id.test#key",
        serialize_sm2_public_key(key.public_key()),
    )
    index = ["tenant", "client", "did:web:id.test#key"]
    if mismatch == "object":
        registration = object()
    else:
        index[["tenant", "client", "kid"].index(mismatch)] = "other"
    with pytest.raises(ValueError, match="historical registration"):
        PermissionSnapshotProvider(
            "unused",
            issuer="https://auth.test",
            as_keys={"as": key.public_key()},
            registrations={tuple(index): registration},
        )
