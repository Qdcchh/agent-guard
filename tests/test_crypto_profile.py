"""GM-MVP-1 SM2/SM3 vectors and Compact JWS security boundaries."""

import json

import pytest
from tongsuopy.crypto.asymciphers import ec
from tongsuopy.crypto.asymciphers.utils import encode_dss_signature

from agent_guard.contracts import b64url_decode, b64url_encode, canonical_json_bytes
from agent_guard.crypto import (
    JWS_ALG,
    PUBLIC_KEY_ENCODING,
    SIGNATURE_ENCODING,
    SM2_CURVE,
    SM2_USER_ID,
    InvalidSm2PublicKey,
    InvalidSm2Signature,
    generate_sm2_private_key,
    load_sm2_public_key,
    serialize_sm2_public_key,
    sign_compact_jws,
    sign_sm2_message,
    sm3_b64url,
    sm3_digest,
    verify_compact_jws,
    verify_sm2_message,
)
from agent_guard.crypto.sm import _der_to_jws_signature


def test_frozen_profile_constants():
    assert SM2_CURVE == "sm2p256v1"
    assert SM2_USER_ID == b"1234567812345678"
    assert "r||s" in SIGNATURE_ENCODING
    assert "SubjectPublicKeyInfo" in PUBLIC_KEY_ENCODING
    assert JWS_ALG == "https://github.com/Qdcchh/agent-guard#sm2-sm3-v1"


def test_sm3_abc_standard_vector():
    expected = "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
    assert sm3_digest(b"abc").hex() == expected
    assert b64url_decode(sm3_b64url(b"abc")).hex() == expected


def test_sm2_published_verification_vector():
    # Public verification vector used by the official Tongsuo Python SDK demo.
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


def test_jws_signs_original_segments_and_uses_raw_rs():
    private_key = generate_sm2_private_key()
    payload = {"profile": "GM-MVP-1", "task_id": "task-001", "note": "中文"}
    token = sign_compact_jws(private_key, payload, key_id="as-sign-1", token_type="ag-at+jwt")
    header_segment, payload_segment, signature_segment = token.split(".")
    assert b64url_decode(header_segment) == canonical_json_bytes(
        {"alg": JWS_ALG, "typ": "ag-at+jwt", "kid": "as-sign-1"}
    )
    assert b64url_decode(payload_segment) == canonical_json_bytes(payload)
    raw_signature = b64url_decode(signature_segment)
    assert len(raw_signature) == 64
    assert (
        verify_compact_jws(
            token, expected_type="ag-at+jwt", trusted_keys={"as-sign-1": private_key.public_key()}
        )
        == payload
    )
    r = int.from_bytes(raw_signature[:32], "big")
    s = int.from_bytes(raw_signature[32:], "big")
    verify_sm2_message(
        private_key.public_key(),
        (header_segment + "." + payload_segment).encode("ascii"),
        encode_dss_signature(r, s),
    )


def test_jws_verifies_signed_original_bytes_without_reserializing():
    key = generate_sm2_private_key()
    # Deliberately noncanonical member order: verification must use received bytes.
    header = b'{"typ":"ag-pop+jwt","kid":"agent-1","alg":"' + JWS_ALG.encode() + b'"}'
    payload = b'{"z":1,"a":2}'
    signed_part = b64url_encode(header) + "." + b64url_encode(payload)
    raw_signature = _der_to_jws_signature(sign_sm2_message(key, signed_part.encode("ascii")))
    token = signed_part + "." + b64url_encode(raw_signature)
    assert verify_compact_jws(
        token, expected_type="ag-pop+jwt", trusted_keys={"agent-1": key.public_key()}
    ) == {"z": 1, "a": 2}


def test_jws_rejects_type_key_payload_and_signature_substitution():
    key = generate_sm2_private_key()
    token = sign_compact_jws(key, {"task_id": "task-001"}, key_id="as-1", token_type="ag-at+jwt")
    header, payload, signature = token.split(".")
    changed_payload = b64url_encode(json.dumps({"task_id": "task-002"}).encode())
    bad_tokens = (
        (token, "ag-id+jwt", {"as-1": key.public_key()}),
        (token, "ag-at+jwt", {"as-1": generate_sm2_private_key().public_key()}),
        (header + "." + changed_payload + "." + signature, "ag-at+jwt", {"as-1": key.public_key()}),
        (
            header + "." + payload + "." + b64url_encode(b"\x00" * 64),
            "ag-at+jwt",
            {"as-1": key.public_key()},
        ),
        (
            header + "." + payload + "." + b64url_encode(b"\x00" * 63),
            "ag-at+jwt",
            {"as-1": key.public_key()},
        ),
    )
    for candidate, expected_type, keys in bad_tokens:
        with pytest.raises(InvalidSm2Signature):
            verify_compact_jws(candidate, expected_type=expected_type, trusted_keys=keys)


def test_jws_rejects_unknown_or_duplicate_header_fields():
    key = generate_sm2_private_key()
    headers = (
        {"alg": JWS_ALG, "typ": "ag-at+jwt", "kid": "as-1", "jku": "https://evil.invalid"},
        '{"alg":"' + JWS_ALG + '","typ":"ag-at+jwt","kid":"as-1","kid":"as-2"}',
    )
    for header in headers:
        header_bytes = (
            canonical_json_bytes(header) if isinstance(header, dict) else header.encode("ascii")
        )
        signing_input = b64url_encode(header_bytes) + "." + b64url_encode(b"{}")
        raw_signature = _der_to_jws_signature(sign_sm2_message(key, signing_input.encode("ascii")))
        token = signing_input + "." + b64url_encode(raw_signature)
        with pytest.raises(InvalidSm2Signature):
            verify_compact_jws(
                token, expected_type="ag-at+jwt", trusted_keys={"as-1": key.public_key()}
            )


def test_jws_rejects_invalid_signing_inputs_and_signature_range():
    key = generate_sm2_private_key()
    with pytest.raises(ValueError):
        sign_compact_jws(key, {}, key_id="as key", token_type="ag-at+jwt")
    with pytest.raises(ValueError):
        sign_compact_jws(key, {}, key_id="as-1", token_type="ag-unknown+jwt")
    with pytest.raises(TypeError):
        sign_compact_jws(key, [], key_id="as-1", token_type="ag-at+jwt")  # type: ignore[arg-type]

    token = sign_compact_jws(key, {}, key_id="as-1", token_type="ag-at+jwt")
    header, payload, _ = token.split(".")
    invalid_range = header + "." + payload + "." + b64url_encode(b"\x00" * 32 + b"\x01" * 32)
    with pytest.raises(InvalidSm2Signature, match="outside the curve order"):
        verify_compact_jws(
            invalid_range, expected_type="ag-at+jwt", trusted_keys={"as-1": key.public_key()}
        )


@pytest.mark.parametrize(
    "payload",
    [
        b'{"note":"\\ud800"}',
        b'{"\\udfff":1}',
        b'{"amount":' + b"1" * 5000 + b"}",
        b'{"nested":' + b"[" * 1500 + b"0" + b"]" * 1500 + b"}",
    ],
)
def test_jws_rejects_signed_invalid_json_with_crypto_error(payload):
    key = generate_sm2_private_key()
    header = canonical_json_bytes({"alg": JWS_ALG, "typ": "ag-at+jwt", "kid": "as-1"})
    signed_part = b64url_encode(header) + "." + b64url_encode(payload)
    signature = _der_to_jws_signature(sign_sm2_message(key, signed_part.encode("ascii")))
    token = signed_part + "." + b64url_encode(signature)
    with pytest.raises(InvalidSm2Signature, match="invalid JWS encoding"):
        verify_compact_jws(
            token, expected_type="ag-at+jwt", trusted_keys={"as-1": key.public_key()}
        )
