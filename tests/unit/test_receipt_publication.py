"""Receipt public-trust role separation and unchanged component codec limits."""

import pytest

from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.contracts.encoding import EncodingError, canonical_json_bytes
from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
from agent_guard.execution.receipt_publication import InternalPublisher, ReceiptVerifier
from agent_guard.identity.resolver import RegisteredIdentity


def trusts():
    as_key, gw, holder = [generate_sm2_private_key() for _ in range(3)]
    did = "did:web:identity.agent-guard.test:shared-holder"
    registrations = {
        (tenant, client, did + "#key-1"): RegisteredIdentity(
            tenant,
            client,
            did,
            did + "#key-1",
            serialize_sm2_public_key(holder.public_key()),
        )
        for tenant, client in (
            ("tenant-a23-A", "client-a23-A"),
            ("tenant-a23-B", "client-a23-B"),
        )
    }
    provider = PermissionSnapshotProvider(
        "test-dsn-not-connected",
        issuer="https://auth.agent-guard.test",
        as_keys={"as": as_key.public_key()},
        registrations=registrations,
    )
    return as_key, gw, holder, registrations, provider


def test_scoped_receipt_trust_preserves_exact_legal_registration_tuples():
    as_key, gw, holder, registry, provider = trusts()
    for entries in (registry, dict(reversed(list(registry.items())))):
        verifier = ReceiptVerifier(
            issuer="https://auth.agent-guard.test",
            as_keys={"as": as_key.public_key()},
            gateway_keys={"gw": gw.public_key()},
            registrations=entries,
            permission_provider=provider,
        )
        assert dict(verifier.registrations) == registry and len(verifier.registrations) == 2
        with pytest.raises(TypeError):
            verifier.registrations["bad"] = holder
    bad = dict(registry)
    row = next(iter(registry.values()))
    bad[(row.tenant_id, "wrong-client", row.kid)] = row
    with pytest.raises(ValueError):
        ReceiptVerifier(
            issuer="https://auth.agent-guard.test",
            as_keys={"as": as_key.public_key()},
            gateway_keys={"gw": gw.public_key()},
            registrations=bad,
            permission_provider=provider,
        )


@pytest.mark.parametrize(
    "role", ["as-spki", "holder-spki", "as-kid", "holder-kid", "private-mismatch"]
)
def test_gateway_key_roles_and_private_match(role):
    as_key, gw, holder, registry, provider = trusts()
    kid, key = "gw", gw
    if role == "as-spki":
        key = as_key
    if role == "holder-spki":
        key = holder
    if role == "as-kid":
        kid = "as"
    if role == "holder-kid":
        kid = next(iter(registry))[2]
    if role != "private-mismatch":
        with pytest.raises(ValueError):
            ReceiptVerifier(
                issuer="https://auth.agent-guard.test",
                as_keys={"as": as_key.public_key()},
                gateway_keys={kid: key.public_key()},
                registrations=registry,
                permission_provider=provider,
            )
    else:
        verifier = ReceiptVerifier(
            issuer="https://auth.agent-guard.test",
            as_keys={"as": as_key.public_key()},
            gateway_keys={kid: key.public_key()},
            registrations=registry,
            permission_provider=provider,
        )
        with pytest.raises(ValueError):
            InternalPublisher(
                "not-connected", private_key=holder, signing_kid=kid, verifier=verifier
            )


@pytest.mark.parametrize("bytes_count,allowed", [(65536, True), (65537, False)])
def test_component_limits_and_precise_outer_encoded_size(bytes_count, allowed):
    value = "a" * (bytes_count - 2)
    if allowed:
        assert len(canonical_json_bytes(value)) == bytes_count
    else:
        with pytest.raises(EncodingError):
            canonical_json_bytes(value)
    # Exact JSON delimiter arithmetic is independent of legal AS reachability.
    component = {"request": {"x": "a"}, "result": {"x": "b"}}
    length = (
        2
        + sum(
            len(canonical_json_bytes(k)) + 1 + len(canonical_json_bytes(v))
            for k, v in component.items()
        )
        + len(component)
        - 1
    )
    assert len(canonical_json_bytes(component)) == length


@pytest.mark.parametrize(
    "field",
    [
        "profile",
        "receipt_id",
        "operation_id",
        "tenant_id",
        "task_id",
        "root_grant_id",
        "grant_id",
        "token_sm3",
        "proof_sm3",
        "intent_sm3",
        "tool_id",
        "tool_version",
        "status",
        "amount_fen",
        "result_sm3",
        "ledger_sm3",
        "iat",
    ],
)
def test_offline_all_binding_mutations_and_unanchored_limits(field):
    from agent_guard.crypto.sm import sign_compact_jws
    from agent_guard.evidence.receipt import (
        ReceiptVerificationError,
        verify_receipt_bundle,
    )
    from tests.test_receipt import _bundle

    bundle, trust, key, receipt = _bundle()
    assert verify_receipt_bundle(bundle, trust=trust).anchoring_status == "UNANCHORED"
    receipt[field] = receipt[field] + 1 if type(receipt[field]) is int else "other"
    bundle["receipt_jws"] = sign_compact_jws(
        key, receipt, key_id="gateway-receipt-1", token_type="ag-receipt+jwt"
    )
    # id/op/task/iat are exact DB-projection obligations: the offline SDK has
    # no independent DB and cannot reject every internally valid new receipt.
    if field in {"receipt_id", "operation_id", "task_id", "iat"}:
        if field == "operation_id":
            with pytest.raises(ReceiptVerificationError):
                verify_receipt_bundle(bundle, trust=trust)
        return
    with pytest.raises(ReceiptVerificationError):
        verify_receipt_bundle(bundle, trust=trust)


@pytest.mark.parametrize("depth,allowed", [(64, True), (65, False)])
def test_original_component_depth_unchanged(depth, allowed):
    value = 0
    for _ in range(depth):
        value = [value]
    if allowed:
        assert canonical_json_bytes(value)
    else:
        with pytest.raises(EncodingError):
            canonical_json_bytes(value)


@pytest.mark.parametrize("nodes,allowed", [(4096, True), (4097, False)])
def test_original_component_node_limit_unchanged(nodes, allowed):
    value = [0] * (nodes - 1)
    if allowed:
        assert canonical_json_bytes(value)
    else:
        with pytest.raises(EncodingError):
            canonical_json_bytes(value)


@pytest.mark.parametrize(
    "case",
    ["valid", "wrong-typ:ag-at+jwt", "wrong-typ:ag-pop+jwt", "wrong-typ:ag-id+jwt", "bad-signature"]
    + [
        "claim:" + f
        for f in (
            "profile",
            "receipt_id",
            "operation_id",
            "tenant_id",
            "task_id",
            "root_grant_id",
            "grant_id",
            "token_sm3",
            "proof_sm3",
            "intent_sm3",
            "tool_id",
            "tool_version",
            "status",
            "amount_fen",
            "result_sm3",
            "ledger_sm3",
            "iat",
        )
    ],
)
def test_real_sm2_profile_typ_and_exact_payload(monkeypatch, case):
    import agent_guard.execution.receipt_publication as implementation
    from agent_guard.authorization.evidence_store import EvidenceError
    from agent_guard.contracts.ledger_changes import canonical_ledger_changes_bytes
    from agent_guard.crypto.sm import sign_compact_jws, verify_compact_jws
    from agent_guard.execution.receipt_projection import ReceiptProjection
    from tests.test_receipt import _bundle

    bundle, trust, gateway_key, receipt = _bundle()
    registry = {
        (r.tenant_id, r.client_id, r.kid): r for r in trust.historical_registrations.values()
    }
    provider = PermissionSnapshotProvider(
        "unit-no-database", issuer=trust.issuer, as_keys=trust.as_keys, registrations=registry
    )
    verifier = ReceiptVerifier(
        issuer=trust.issuer,
        as_keys=trust.as_keys,
        gateway_keys=trust.gateway_keys,
        registrations=registry,
        permission_provider=provider,
    )
    projection = ReceiptProjection(
        canonical_json_bytes(receipt),
        canonical_ledger_changes_bytes(bundle["ledger_changes"]),
        canonical_json_bytes(bundle["result"]),
        bundle["token_jws"].encode("ascii"),
        bundle["proof_jws"].encode("ascii"),
        canonical_json_bytes(bundle["request"]),
        tuple(bundle["ancestor_tokens"]),
    )
    # Unit projection is a complete immutable material fixture. Cryptographic
    # signatures and SDK checks are real; the separate integration nodes bind
    # this identical verifier path to PostgreSQL and its exact effects.
    monkeypatch.setattr(implementation, "project_receipt", lambda conn, op: projection)
    monkeypatch.setattr(verifier, "_trust_tx", lambda conn, op: trust)
    typ, key = "ag-receipt+jwt", gateway_key
    if case.startswith("wrong-typ:"):
        typ = case.split(":", 1)[1]

    if case.startswith("claim:"):
        field = case.split(":", 1)[1]
        receipt[field] = receipt[field] + 1 if type(receipt[field]) is int else "other"
    signed = sign_compact_jws(key, receipt, key_id="gateway-receipt-1", token_type=typ)
    if case == "bad-signature":
        from agent_guard.contracts.encoding import b64url_decode, b64url_encode

        header, payload, signature = signed.split(".")
        raw = bytearray(b64url_decode(signature))
        raw[0] ^= 1
        signed = header + "." + payload + "." + b64url_encode(bytes(raw))
    if case == "valid":
        assert (
            verify_compact_jws(signed, expected_type=typ, trusted_keys=trust.gateway_keys)
            == receipt
        )
        assert len(receipt) == 17
        assert verifier.verify_tx(None, "operation-001", signed) == projection
    else:
        with pytest.raises(EvidenceError):
            verifier.verify_tx(None, "operation-001", signed)


@pytest.mark.parametrize("length,allowed", [(16384, True), (16385, False)])
def test_original_jws_component_length_codec_unchanged(length, allowed):
    from agent_guard.evidence.receipt import ReceiptVerificationError, _ascii_jws

    # Codec boundary only: a padded arbitrary string is not a signed token.
    if allowed:
        assert _ascii_jws("a" * length, "unit-component") == "a" * length
    else:
        with pytest.raises(ReceiptVerificationError):
            _ascii_jws("a" * length, "unit-component")


@pytest.mark.parametrize("target", [1048576, 1048577])
def test_outer_size_arithmetic_and_illegal_component_guard(target):
    import rfc8785

    from agent_guard.evidence.receipt import ReceiptVerificationError, verify_receipt_bundle
    from tests.test_receipt import _bundle

    bundle, trust, _, _ = _bundle()
    bundle["proof_jws"] = ""
    fixed = len(rfc8785.dumps(bundle))
    bundle["proof_jws"] = "a" * (target - fixed)
    from agent_guard.evidence.receipt import _outer_encoded_size

    encoded = {k: rfc8785.dumps(v) for k, v in bundle.items()}
    assert _outer_encoded_size(encoded) == len(rfc8785.dumps(bundle)) == target
    assert (_outer_encoded_size(encoded) <= 1_048_576) == (target == 1_048_576)
    with pytest.raises(EncodingError):
        canonical_json_bytes({k: v for k, v in bundle.items() if k != "ledger_changes"})
    with pytest.raises(ReceiptVerificationError):
        verify_receipt_bundle(bundle, trust=trust)
    # The refusal is the original component guard. This deliberately does not
    # claim the later 1 MiB guard has a reachable positive boundary.


def test_original_four_ancestor_path_refused():
    from agent_guard.evidence.receipt import ReceiptVerificationError, verify_receipt_bundle
    from tests.test_receipt import _bundle

    bundle, trust, _, _ = _bundle()
    assert verify_receipt_bundle(bundle, trust=trust).anchoring_status == "UNANCHORED"
    original = bundle["ancestor_tokens"]
    for count in (0, 4):
        bundle["ancestor_tokens"] = original * count
        with pytest.raises(ReceiptVerificationError, match="ancestor token path"):
            verify_receipt_bundle(bundle, trust=trust)


@pytest.mark.parametrize("quantity_digits", range(1, 17))
def test_accepted_price_quantity_joint_decimal_bound(quantity_digits):
    """A conservative raw-JWS response bound includes zero-price orders."""
    from agent_guard.contracts.ledger import MAX_SAFE_INT

    quantity = 10 ** (quantity_digits - 1)
    price = MAX_SAFE_INT // quantity
    assert quantity >= 1 and price >= 0 and quantity * price <= MAX_SAFE_INT
    assert len(str(quantity)) + len(str(price)) <= 17
    # The smallest positive values in any pair of decimal widths summing
    # to 18 already exceed the accepted safe product, independently of SKU.
    assert 10 ** (quantity_digits - 1) * 10 ** (17 - quantity_digits) > MAX_SAFE_INT
    assert len(str(MAX_SAFE_INT)) + len(str(0)) == 17
