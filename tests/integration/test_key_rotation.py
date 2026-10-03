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


def test_current_client_disable_does_not_replace_historical_receipt_trust(
    ledger, dsn, downstream_dsn
):
    import psycopg

    from agent_guard.contracts.ledger import LedgerError
    from agent_guard.execution.receipt_projection import project_receipt
    from agent_guard.ledger.provisioning import deactivate_principal
    from tests.integration.test_verified_execution import TENANT, signed_env, verify_projection

    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    assert env.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
    with psycopg.connect(dsn) as conn:
        original = project_receipt(conn, accepted.operation_id)
        principal = env.registrations[(TENANT, "agent-executor")]
        deactivate_principal(conn, tenant_id=TENANT, client_id="agent-executor", kid=principal.kid)
    with pytest.raises(LedgerError):
        env.adapter.accept(env.bundle("after-disabled"))
    with psycopg.connect(dsn) as conn:
        assert project_receipt(conn, accepted.operation_id) == original
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (1,)
        assert verify_projection(env, original).status == "SUCCEEDED"


def test_gateway_rotation_requires_separate_historical_and_current_trust():
    from dataclasses import replace

    from agent_guard.contracts.encoding import load_strict_json
    from agent_guard.crypto.sm import sign_compact_jws
    from agent_guard.evidence.receipt import ReceiptVerificationError, verify_receipt_bundle
    from tests.test_receipt import _bundle

    bundle, trust, _, claims = _bundle()
    new = generate_sm2_private_key()
    rotated = replace(trust, gateway_keys={**trust.gateway_keys, "gw-new": new.public_key()})
    assert verify_receipt_bundle(bundle, trust=rotated)
    only_new = replace(trust, gateway_keys={"gw-new": new.public_key()})
    with pytest.raises(ReceiptVerificationError):
        verify_receipt_bundle(bundle, trust=only_new)
    new_bundle = {
        **bundle,
        "receipt_jws": sign_compact_jws(new, claims, key_id="gw-new", token_type="ag-receipt+jwt"),
    }
    assert verify_receipt_bundle(new_bundle, trust=only_new)
    assert (
        load_strict_json(canonical_payload(new_bundle["receipt_jws"]))["receipt_id"]
        == claims["receipt_id"]
    )


def canonical_payload(token):
    from agent_guard.contracts.encoding import b64url_decode

    return b64url_decode(token.split(".")[1])
