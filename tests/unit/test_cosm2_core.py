"""Core correctness and fail-closed boundaries, with mature final verification."""

import json
from pathlib import Path

import pytest

from agent_guard.contracts.encoding import b64url_decode
from agent_guard.cosign import encoding as enc
from agent_guard.cosign.curve import G, N
from agent_guard.cosign.protocol import AuthzParty, ExecParty, compute_e
from agent_guard.crypto.sm import InvalidSm2Signature, load_sm2_public_key, verify_sm2_message


def parties():
    p1, p2 = ExecParty(), AuthzParty()
    public = p2.keygen_finish(p1.keygen_msg())
    p1.set_public(public)
    return p1, p2, public


@pytest.mark.parametrize("iteration", range(50))
def test_random_mature_signatures(iteration):
    p1, p2, public = parties()
    message = b"COSM2 random mature verification " + str(iteration).encode()
    signature = p1.sign_round3(message, *p2.sign_round2(message, p1.sign_round1()))
    raw = b"".join(v.to_bytes(32, "big") for v in signature)
    der = enc.signature_rs_to_der(raw)
    key = load_sm2_public_key(enc.public_point_to_spki(public))
    verify_sm2_message(key, message, der)
    with pytest.raises(InvalidSm2Signature):
        verify_sm2_message(key, message + b"x", der)
    with pytest.raises(InvalidSm2Signature):
        verify_sm2_message(load_sm2_public_key(enc.public_point_to_spki(G)), message, der)
    assert enc.signature_der_to_rs(der) == raw
    assert enc.spki_to_public_point(enc.public_point_to_spki(public)) == public
    assert enc.point_from_hex(enc.point_to_hex(public)) == public


@pytest.mark.parametrize("point", [None, (0, 0), (True, 2), (1,), [1, 2], (N, -1)])
def test_invalid_points(point):
    _, p2, _ = parties()
    with pytest.raises(ValueError):
        p2.sign_round2(b"message", point)


def test_nonce_one_shot():
    p1, p2, _ = parties()
    with pytest.raises(RuntimeError):
        p1.sign_round3(b"m", 1, 1, 1)
    q1 = p1.sign_round1()
    with pytest.raises(RuntimeError):
        p1.sign_round1()
    partial = p2.sign_round2(b"m", q1)
    with pytest.raises(InvalidSm2Signature):
        p1.sign_round3(b"different", *partial)
    with pytest.raises(RuntimeError):
        p1.sign_round3(b"m", *partial)
    p1.sign_round1()
    with pytest.raises(ValueError):
        p1.sign_round3(b"m", True, 1, 1)
    assert p1._k1 is None


def test_fixed_coordinates_and_digest():
    from tests.fixtures import cosm2_reference as ref

    p1, p2 = ExecParty(), AuthzParty()
    p1.d1, p2.d2 = 0x123456789ABCDEF, 0xFEDCBA987654321
    expected = ref.add(ref.mul(pow(p1.d1 * p2.d2, -1, N), G), ref.neg(G))
    public = p2.keygen_finish(p1.keygen_msg())
    assert public == expected
    assert compute_e(public, b"fixed") == ref.digest_e(public, b"fixed")


def test_public_vector():
    data = json.loads((Path(__file__).parents[1] / "cosm2-public-vector.json").read_text())
    assert set(data) == {"public_key_spki_b64url", "message_b64url", "signature_rs_hex"}
    verify_sm2_message(
        load_sm2_public_key(b64url_decode(data["public_key_spki_b64url"])),
        b64url_decode(data["message_b64url"]),
        enc.signature_rs_to_der(bytes.fromhex(data["signature_rs_hex"])),
    )


@pytest.mark.parametrize("raw", [b"", b"\0" * 64, b"\1" * 63, b"\xff" * 64])
def test_invalid_signature_encoding(raw):
    with pytest.raises(ValueError):
        enc.signature_rs_to_der(raw)
    with pytest.raises(ValueError):
        enc.signature_der_to_rs(raw)


def test_degenerate_key_and_type_rejection():
    one, two = ExecParty(1), AuthzParty(1)
    with pytest.raises(ValueError):
        two.keygen_finish(one.keygen_msg())
    with pytest.raises(TypeError):
        compute_e(G, "string")
    for point in ("04" + "00" * 64, "04" + "FF" * 64):
        with pytest.raises(ValueError):
            enc.point_from_hex(point)
