"""SM2/SM3 profile tests using published vectors and generated ephemeral keys."""

import copy

import pytest
from tongsuopy.crypto.asymciphers import ec
from tongsuopy.crypto.asymciphers.utils import encode_dss_signature

from agent_guard.contracts import b64url_decode
from agent_guard.crypto import (
    PUBLIC_KEY_ENCODING,
    SIGNATURE_ENCODING,
    SM2_CURVE,
    SM2_USER_ID,
    InvalidSm2PublicKey,
    InvalidSm2Signature,
    chain_digest,
    create_signed_envelope,
    credential_digest,
    generate_sm2_private_key,
    load_sm2_public_key,
    serialize_sm2_public_key,
    sm3_digest,
    verify_signed_envelope,
    verify_sm2_message,
)


def test_frozen_profile_constants():
    assert SM2_CURVE == "sm2p256v1"
    assert SM2_USER_ID == b"1234567812345678"
    assert "DER" in SIGNATURE_ENCODING
    assert "SubjectPublicKeyInfo" in PUBLIC_KEY_ENCODING


def test_sm3_abc_standard_vector():
    assert sm3_digest(b"abc").hex() == (
        "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
    )


def test_sm2_published_verification_vector():
    # Public verification vector used by the official Tongsuo Python SDK demo.
    # It exercises the standard SM2 user ID and DER r/s encoding; no private key is stored.
    qx = int("09F9DF311E5421A150DD7D161E4BC5C672179FAD1833FC076BB08FF356F35020", 16)
    qy = int("CCEA490CE26775A52DC6EA718CC1AA600AED05FBF35E084A6632F6072DA9AD13", 16)
    r = int("F5A03B0648D2C4630EEAC513E1BB81A15944DA3827D5B74143AC7EACEEE720B3", 16)
    s = int("B1B6AA29DF212FD8763182BC0D421CA1BB9038FD1F7F42D4840B69C485BBC1AA", 16)
    public_key = ec.EllipticCurvePublicNumbers(qx, qy, ec.SM2()).public_key()

    verify_sm2_message(public_key, b"message digest", encode_dss_signature(r, s))


def test_spki_round_trip_rejects_noncanonical_der():
    private_key = generate_sm2_private_key()
    encoded = serialize_sm2_public_key(private_key.public_key())
    loaded = load_sm2_public_key(encoded)
    assert serialize_sm2_public_key(loaded) == encoded

    with pytest.raises(InvalidSm2PublicKey):
        load_sm2_public_key(encoded + b"\x00")


def test_domain_signed_envelope_detects_payload_and_signature_tampering():
    private_key = generate_sm2_private_key()
    public_key = private_key.public_key()
    payload = {"version": "1", "capability_id": "cap_test_001", "amount_limit": 120_00}
    envelope = create_signed_envelope(private_key, payload, "capability")

    assert b64url_decode(envelope["signature"])[0] == 0x30  # type: ignore[arg-type]
    assert verify_signed_envelope(public_key, envelope, "capability") == payload

    changed_payload = copy.deepcopy(envelope)
    changed_payload["payload"]["amount_limit"] = 120_01  # type: ignore[index]
    with pytest.raises(InvalidSm2Signature):
        verify_signed_envelope(public_key, changed_payload, "capability")

    with pytest.raises(InvalidSm2Signature):
        verify_signed_envelope(public_key, envelope, "invocation")

    malformed_signature = copy.deepcopy(envelope)
    malformed_signature["signature"] += "AA"  # type: ignore[operator]
    with pytest.raises(InvalidSm2Signature):
        verify_signed_envelope(public_key, malformed_signature, "capability")

    unknown_envelope_field = copy.deepcopy(envelope)
    unknown_envelope_field["algorithm"] = "SM2SM3"
    with pytest.raises(ValueError, match="only payload and signature"):
        verify_signed_envelope(public_key, unknown_envelope_field, "capability")


def test_credential_and_chain_digests_bind_signature_and_order():
    key = generate_sm2_private_key()
    root = create_signed_envelope(key, {"version": "1", "capability_id": "root"}, "capability")
    child = create_signed_envelope(key, {"version": "1", "capability_id": "child"}, "capability")

    assert len(credential_digest(root)) == 32
    assert len(chain_digest([root, child])) == 32
    assert chain_digest([root, child]) != chain_digest([child, root])
