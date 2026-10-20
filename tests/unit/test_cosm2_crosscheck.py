"""Real B1 crosschecks. Missing B is a failure, never a reference fallback.

Provisional B contract (requires B confirmation): protocol.ExecParty() and
AuthzParty() expose test-only writable d1/d2; keygen_msg(), keygen_finish(T1),
set_public(P), sign_round1(), sign_round2(message,Q1), sign_round3(message,r,s2,s3).
Public points and signatures are integer tuples; compute_e(P,message) returns int.
"""

import importlib
import secrets

import pytest

from tests.fixtures import cosm2_reference as ref


def b_protocol():
    try:
        return importlib.import_module("agent_guard.cosign.protocol")
    except ModuleNotFoundError as exc:
        pytest.fail(f"B1 dependency unavailable: {exc.name}; no reference fallback")


def parties(module):
    p1, p2 = module.ExecParty(), module.AuthzParty()
    p1.d1, p2.d2 = 0x123456789ABCDEF, 0xFEDCBA987654321  # TEST ONLY
    public = p2.keygen_finish(p1.keygen_msg())
    p1.set_public(public)
    return p1, p2, public


def reference_parties():
    p1, p2 = ref.Party1(), ref.Party2()
    p1.d1, p2.d2 = 0x123456789ABCDEF, 0xFEDCBA987654321  # TEST ONLY
    public = p2.keygen_finish(p1.keygen_msg())
    p1.set_public(public)
    return p1, p2, public


def test_fixed_share_public_coordinates():
    _, _, actual = parties(b_protocol())
    _, _, expected = reference_parties()
    assert actual[0] == expected[0]
    assert actual[1] == expected[1]


def test_bidirectional_signatures_with_tongsuo():
    b1, b2, public = parties(b_protocol())
    from tongsuopy.crypto.asymciphers import ec

    from agent_guard.crypto.sm import verify_sm2_message

    r1, r2, expected = reference_parties()
    assert public == expected
    message = b'AGENT-GUARD-COSM2-ACTION-V1\n{"crosscheck":1}'
    signature = ref.cosign(r1, r2, message)
    backend_public = ec.EllipticCurvePublicNumbers(*public, ec.SM2()).public_key()
    verify_sm2_message(backend_public, message, ref.der_signature(*signature))
    partial = b2.sign_round2(message, b1.sign_round1())
    actual = b1.sign_round3(message, *partial)
    assert ref.verify(public, message, actual)
    verify_sm2_message(backend_public, message, ref.der_signature(*actual))
    assert not ref.verify(public, message + b"x", actual)


def test_compute_e_twenty_random_messages():
    module = b_protocol()
    _, _, public = parties(module)
    for _ in range(20):
        message = secrets.token_bytes(64)
        assert module.compute_e(public, message) == ref.digest_e(public, message)
