"""AS signing-key rotation: historical keys verify, only the current key signs.

Rotation uses a new kid for the new key. Existing root tokens and grant
snapshots signed by the previous kid stay verifiable only while that kid is
listed as a historical verification key; the rotation target signs every new
token. The historical key never signs again.
"""

from __future__ import annotations

import pytest

from agent_guard.authorization.exchange_service import TokenExchangeError, TokenExchangeService
from agent_guard.authorization.introspection import IntrospectionService
from agent_guard.crypto.sm import (
    InvalidSm2Signature,
    generate_sm2_private_key,
    verify_compact_jws,
)
from tests.integration.test_exchange_service import (
    ISSUER,
    TOKEN_ENDPOINT,
    _exchange,
    _form,
    _resolver,
    _root,
)

pytestmark = pytest.mark.integration

OLD_KID = "as-sign-1"
NEW_KID = "as-sign-2"


def _rotated_exchange(dsn, old_public, new_key, registrations, *, include_historical):
    trusted = {NEW_KID: new_key.public_key()}
    if include_historical:
        trusted[OLD_KID] = old_public
    return TokenExchangeService(
        dsn,
        issuer=ISSUER,
        token_endpoint=TOKEN_ENDPOINT,
        signing_key=new_key,
        signing_kid=NEW_KID,
        identities=_resolver(registrations),
        verification_keys=trusted,
    )


def test_rotation_signs_with_new_kid_and_keeps_old_tokens_verifiable(ledger, dsn):
    old_key, keys, registrations, _, root = _root(dsn)
    new_key = generate_sm2_private_key()

    introspection = IntrospectionService(
        dsn,
        issuer=ISSUER,
        as_keys={OLD_KID: old_key.public_key(), NEW_KID: new_key.public_key()},
        identities=_resolver(registrations),
    )
    assert introspection.inspect(root.access_token).active is True
    only_new = IntrospectionService(
        dsn,
        issuer=ISSUER,
        as_keys={NEW_KID: new_key.public_key()},
        identities=_resolver(registrations),
    )
    assert only_new.inspect(root.access_token).active is False

    rotated = _rotated_exchange(
        dsn, old_key.public_key(), new_key, registrations, include_historical=True
    )
    child = _exchange(rotated, keys, registrations, _form(old_key, root.access_token))
    claims = verify_compact_jws(
        child.access_token,
        expected_type="ag-at+jwt",
        trusted_keys={NEW_KID: new_key.public_key()},
    )
    assert claims["ag_parent_id"] == root.ag_grant_id
    assert claims["ag_root_id"] == root.ag_grant_id
    with pytest.raises(InvalidSm2Signature):
        verify_compact_jws(
            child.access_token,
            expected_type="ag-at+jwt",
            trusted_keys={OLD_KID: old_key.public_key()},
        )


def test_rotation_without_historical_key_rejects_old_parent_token(ledger, dsn):
    old_key, keys, registrations, _, root = _root(dsn)
    new_key = generate_sm2_private_key()
    rotated = _rotated_exchange(
        dsn, old_key.public_key(), new_key, registrations, include_historical=False
    )
    with pytest.raises(TokenExchangeError, match="SUBJECT_OR_PROOF_INVALID"):
        _exchange(rotated, keys, registrations, _form(old_key, root.access_token))
