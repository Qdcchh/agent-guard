"""SM2-with-SM3 operations for the Agent Guard v1 profile.

This module delegates cryptographic primitives to Tongsuo. It does not implement
SM2 or SM3 itself.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from tongsuopy.crypto import hashes, serialization
from tongsuopy.crypto.asymciphers import ec
from tongsuopy.crypto.exceptions import InternalError as BackendInternalError
from tongsuopy.crypto.exceptions import InvalidSignature as BackendInvalidSignature

from agent_guard.contracts.encoding import (
    EncodingError,
    JsonObject,
    JsonValue,
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    hash_message,
    signature_message,
)

SM2_CURVE = "sm2p256v1"
SM2_USER_ID = b"1234567812345678"
SIGNATURE_ENCODING = "ASN.1 DER sequence of INTEGER r and INTEGER s"
PUBLIC_KEY_ENCODING = "X.509 SubjectPublicKeyInfo DER"


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


def _validate_envelope(envelope: Mapping[str, JsonValue]) -> tuple[JsonObject, str]:
    if type(envelope) is not dict:
        raise TypeError("signed envelope must be a JSON object")
    if set(envelope) != {"payload", "signature"}:
        raise ValueError("signed envelope must contain only payload and signature")
    payload = envelope["payload"]
    signature = envelope["signature"]
    if type(payload) is not dict:
        raise TypeError("signed envelope payload must be a JSON object")
    if type(signature) is not str:
        raise TypeError("signed envelope signature must be a string")
    return cast(JsonObject, payload), signature


def create_signed_envelope(
    private_key: ec.EllipticCurvePrivateKey, payload: JsonObject, domain: str
) -> JsonObject:
    """Create a v1 envelope whose signature covers only the complete payload."""

    message = signature_message(domain, payload)
    signature = sign_sm2_message(private_key, message)
    return {"payload": payload, "signature": b64url_encode(signature)}


def verify_signed_envelope(
    public_key: ec.EllipticCurvePublicKey,
    envelope: Mapping[str, JsonValue],
    domain: str,
) -> JsonObject:
    """Validate an envelope shape, encoding, domain, and SM2 signature."""

    payload, encoded_signature = _validate_envelope(envelope)
    try:
        signature = b64url_decode(encoded_signature)
    except EncodingError as exc:
        raise InvalidSm2Signature("SM2 signature encoding is invalid") from exc
    verify_sm2_message(public_key, signature_message(domain, payload), signature)
    return payload


def credential_digest(envelope: Mapping[str, JsonValue]) -> bytes:
    """Digest the complete signed envelope with the credential hash domain."""

    _validate_envelope(envelope)
    body = canonical_json_bytes(cast(JsonObject, envelope))
    return sm3_digest(hash_message("credential", body))


def chain_digest(envelopes: Sequence[Mapping[str, JsonValue]]) -> bytes:
    """Digest ordered credential digests from root to leaf."""

    if isinstance(envelopes, (str, bytes)) or not isinstance(envelopes, Sequence):
        raise TypeError("envelopes must be a sequence")
    encoded_digests: list[JsonValue] = [
        b64url_encode(credential_digest(item)) for item in envelopes
    ]
    body = canonical_json_bytes(encoded_digests)
    return sm3_digest(hash_message("chain", body))
