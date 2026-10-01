"""SM2-with-SM3 operations for the GM-MVP-1 JWS profile.

This module delegates cryptographic primitives to Tongsuo. It does not implement
SM2 or SM3 itself.
"""

from __future__ import annotations

from collections.abc import Mapping

from tongsuopy.crypto import hashes, serialization
from tongsuopy.crypto.asymciphers import ec
from tongsuopy.crypto.asymciphers.utils import encode_dss_signature
from tongsuopy.crypto.exceptions import InternalError as BackendInternalError
from tongsuopy.crypto.exceptions import InvalidSignature as BackendInvalidSignature

from agent_guard.contracts.encoding import (
    EncodingError,
    JsonObject,
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)

SM2_CURVE = "sm2p256v1"
SM2_USER_ID = b"1234567812345678"
JWS_ALG = "https://github.com/Qdcchh/agent-guard#sm2-sm3-v1"
JWS_TYPES = frozenset({"ag-id+jwt", "ag-at+jwt", "ag-pop+jwt", "ag-receipt+jwt"})
SIGNATURE_ENCODING = "64-byte big-endian r||s in JWS; DER only at the backend boundary"
PUBLIC_KEY_ENCODING = "X.509 SubjectPublicKeyInfo DER"
_SM2_ORDER = int("FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123", 16)


class InvalidSm2Signature(ValueError):
    """The SM2 signature is malformed, uses another profile, or does not verify."""


class InvalidSm2PublicKey(ValueError):
    """The public key is not a canonical SM2 SubjectPublicKeyInfo value."""


def _require_sm2_private_key(key: object) -> ec.EllipticCurvePrivateKey:
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "SM2":
        raise TypeError("private key must be an SM2 private key")
    return key


def _require_sm2_public_key(key: object) -> ec.EllipticCurvePublicKey:
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "SM2":
        raise TypeError("public key must be an SM2 public key")
    return key


def sm3_digest(message: bytes) -> bytes:
    """Return the 32-byte SM3 digest of message."""

    if type(message) is not bytes:
        raise TypeError("message must be bytes")
    digest = hashes.Hash(hashes.SM3())
    digest.update(message)
    return digest.finalize()


def generate_sm2_private_key() -> ec.EllipticCurvePrivateKey:
    """Generate an ephemeral SM2 key with the backend CSPRNG."""

    return ec.generate_private_key(ec.SM2())


def serialize_sm2_public_key(public_key: ec.EllipticCurvePublicKey) -> bytes:
    """Serialize an SM2 public key as canonical SubjectPublicKeyInfo DER."""

    key = _require_sm2_public_key(public_key)
    return key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def load_sm2_public_key(encoded: bytes) -> ec.EllipticCurvePublicKey:
    """Load canonical SubjectPublicKeyInfo DER and reject non-SM2 keys."""

    if type(encoded) is not bytes:
        raise TypeError("encoded public key must be bytes")
    try:
        loaded = serialization.load_der_public_key(encoded)
    except (TypeError, ValueError) as exc:
        raise InvalidSm2PublicKey("invalid SubjectPublicKeyInfo DER") from exc
    if not isinstance(loaded, ec.EllipticCurvePublicKey) or loaded.curve.name != "SM2":
        raise InvalidSm2PublicKey("public key is not on the SM2 curve")
    if serialize_sm2_public_key(loaded) != encoded:
        raise InvalidSm2PublicKey("public key DER is not canonical")
    return loaded


def sign_sm2_message(private_key: ec.EllipticCurvePrivateKey, message: bytes) -> bytes:
    """Sign the complete message with SM2-with-SM3 and return DER r/s."""

    key = _require_sm2_private_key(private_key)
    if type(message) is not bytes:
        raise TypeError("message must be bytes")
    return key.sign(message, ec.ECDSA(hashes.SM3()))


def verify_sm2_message(
    public_key: ec.EllipticCurvePublicKey, message: bytes, signature: bytes
) -> None:
    """Verify one DER-encoded SM2-with-SM3 signature or raise."""

    key = _require_sm2_public_key(public_key)
    if type(message) is not bytes or type(signature) is not bytes:
        raise TypeError("message and signature must be bytes")
    try:
        key.verify(signature, message, ec.ECDSA(hashes.SM3()))
    except (BackendInvalidSignature, BackendInternalError, ValueError) as exc:
        raise InvalidSm2Signature("SM2 signature verification failed") from exc


def _der_to_jws_signature(signature: bytes) -> bytes:
    # A valid SM2 signature has two positive INTEGERs of at most 33 bytes each.
    # The sequence is at most 72 bytes, so DER uses one-byte lengths throughout.
    if len(signature) < 8 or len(signature) > 72:
        raise InvalidSm2Signature("SM2 backend returned malformed DER")
    if signature[0] != 0x30 or signature[1] != len(signature) - 2:
        raise InvalidSm2Signature("SM2 backend returned malformed DER")

    def read_integer(offset: int) -> tuple[int, int]:
        if offset + 2 > len(signature) or signature[offset] != 0x02:
            raise InvalidSm2Signature("SM2 backend returned malformed DER")
        length = signature[offset + 1]
        end = offset + 2 + length
        if length < 1 or length > 33 or end > len(signature):
            raise InvalidSm2Signature("SM2 backend returned malformed DER")
        value = int.from_bytes(signature[offset + 2 : end], "big")
        return value, end

    r, offset = read_integer(2)
    s, offset = read_integer(offset)
    if offset != len(signature) or encode_dss_signature(r, s) != signature:
        raise InvalidSm2Signature("SM2 backend returned noncanonical DER")
    if not (1 <= r < _SM2_ORDER and 1 <= s < _SM2_ORDER):
        raise InvalidSm2Signature("SM2 signature integer is outside the curve order")
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def _jws_to_der_signature(signature: bytes) -> bytes:
    if len(signature) != 64:
        raise InvalidSm2Signature("JWS SM2 signature must be exactly 64 bytes")
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    if not (1 <= r < _SM2_ORDER and 1 <= s < _SM2_ORDER):
        raise InvalidSm2Signature("SM2 signature integer is outside the curve order")
    return encode_dss_signature(r, s)


def _validate_type(token_type: str) -> None:
    if token_type not in JWS_TYPES:
        raise ValueError("unsupported GM-MVP-1 JWS type")


def _valid_key_id(key_id: object) -> bool:
    return (
        type(key_id) is str
        and bool(key_id)
        and all(0x21 <= ord(character) <= 0x7E for character in key_id)
    )


def sign_compact_jws(
    private_key: ec.EllipticCurvePrivateKey,
    payload: JsonObject,
    *,
    key_id: str,
    token_type: str,
) -> str:
    """Sign canonical JWS segments with the fixed project SM2 profile."""

    _validate_type(token_type)
    if not _valid_key_id(key_id):
        raise ValueError("key_id must be nonempty printable ASCII without whitespace")
    if type(payload) is not dict:
        raise TypeError("JWS payload must be a JSON object")
    header: JsonObject = {"alg": JWS_ALG, "typ": token_type, "kid": key_id}
    signing_input = (
        b64url_encode(canonical_json_bytes(header))
        + "."
        + b64url_encode(canonical_json_bytes(payload))
    )
    der_signature = sign_sm2_message(private_key, signing_input.encode("ascii"))
    return signing_input + "." + b64url_encode(_der_to_jws_signature(der_signature))


def verify_compact_jws(
    token: str,
    *,
    expected_type: str,
    trusted_keys: Mapping[str, ec.EllipticCurvePublicKey],
) -> JsonObject:
    """Verify original Compact JWS segments against locally trusted keys.

    This checks the protected header and signature only. Claim validation belongs
    to the caller after this function succeeds.
    """

    _validate_type(expected_type)
    if type(token) is not str:
        raise TypeError("token must be str")
    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidSm2Signature("JWS must contain exactly three segments")
    try:
        header_bytes = b64url_decode(parts[0])
        payload_bytes = b64url_decode(parts[1])
        signature = b64url_decode(parts[2])
        header = load_strict_json(header_bytes)
        payload = load_strict_json(payload_bytes)
    except EncodingError as exc:
        raise InvalidSm2Signature("invalid JWS encoding") from exc
    if type(header) is not dict or set(header) != {"alg", "typ", "kid"}:
        raise InvalidSm2Signature("invalid protected JWS header")
    if header["alg"] != JWS_ALG or header["typ"] != expected_type:
        raise InvalidSm2Signature("JWS algorithm or type mismatch")
    key_id = header["kid"]
    if not _valid_key_id(key_id):
        raise InvalidSm2Signature("invalid JWS key ID")
    public_key = trusted_keys.get(key_id)
    if public_key is None:
        raise InvalidSm2Signature("JWS key ID is not trusted")
    if type(payload) is not dict:
        raise InvalidSm2Signature("JWS payload must be a JSON object")
    signing_input = (parts[0] + "." + parts[1]).encode("ascii")
    verify_sm2_message(public_key, signing_input, _jws_to_der_signature(signature))
    return payload


def sm3_b64url(message: bytes) -> str:
    """Encode the SM3 digest of exact input bytes as unpadded base64url."""

    return b64url_encode(sm3_digest(message))
