"""Strict wire-format helpers shared by Agent Guard protocol objects."""

from agent_guard.contracts.encoding import (
    MAX_SAFE_INTEGER,
    SIGNATURE_DOMAINS,
    DuplicateKeyError,
    EncodingError,
    JsonObject,
    JsonValue,
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    hash_message,
    load_strict_json,
    signature_message,
)

__all__ = [
    "MAX_SAFE_INTEGER",
    "SIGNATURE_DOMAINS",
    "DuplicateKeyError",
    "EncodingError",
    "JsonObject",
    "JsonValue",
    "b64url_decode",
    "b64url_encode",
    "canonical_json_bytes",
    "hash_message",
    "load_strict_json",
    "signature_message",
]
