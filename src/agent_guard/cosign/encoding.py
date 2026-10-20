"""Canonical SM2 point and signature encodings using the mature backend."""

from tongsuopy.crypto.asymciphers import ec

from agent_guard.cosign.curve import on_curve
from agent_guard.crypto.sm import (
    _der_to_jws_signature,
    _jws_to_der_signature,
    load_sm2_public_key,
    serialize_sm2_public_key,
)


def public_point_to_spki(point) -> bytes:
    if not on_curve(point):
        raise ValueError("invalid public point")
    return serialize_sm2_public_key(ec.EllipticCurvePublicNumbers(*point, ec.SM2()).public_key())


def spki_to_public_point(encoded: bytes) -> tuple[int, int]:
    numbers = load_sm2_public_key(encoded).public_numbers()
    return numbers.x, numbers.y


def signature_rs_to_der(signature: bytes) -> bytes:
    if type(signature) is not bytes:
        raise TypeError("signature must be bytes")
    return _jws_to_der_signature(signature)


def signature_der_to_rs(signature: bytes) -> bytes:
    if type(signature) is not bytes:
        raise TypeError("signature must be bytes")
    return _der_to_jws_signature(signature)


def point_to_hex(point) -> str:
    if not on_curve(point):
        raise ValueError("invalid point")
    return "04" + "".join(v.to_bytes(32, "big").hex() for v in point)


def point_from_hex(value: str) -> tuple[int, int]:
    if type(value) is not str or len(value) != 130 or value != value.lower():
        raise ValueError("expected canonical uncompressed point hex")
    try:
        raw = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError("invalid point hex") from exc
    if len(raw) != 65 or raw[0] != 4 or raw.hex() != value:
        raise ValueError("invalid point encoding")
    point = int.from_bytes(raw[1:33], "big"), int.from_bytes(raw[33:], "big")
    if not on_curve(point):
        raise ValueError("invalid point")
    return point
