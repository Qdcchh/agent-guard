"""Strict OAuth form decoding before canonical AG-Proof body hashing."""

from __future__ import annotations

import re
from urllib.parse import unquote_to_bytes

_BAD_PERCENT = re.compile(rb"%(?![0-9A-Fa-f]{2})")
_FORM_KEY = re.compile(r"[A-Za-z0-9_]+\Z", re.ASCII)
MAX_FORM_BYTES = 65536


class FormError(ValueError):
    """Malformed or ambiguous application/x-www-form-urlencoded input."""


def decode_oauth_form(raw: bytes) -> dict[str, str]:
    """Decode one UTF-8 form to unique string keys and values.

    A request's AG-Proof binds the resulting canonical JSON mapping, not
    percent-encoded spelling. Duplicate keys and malformed encoding reject
    before either OAuth grant path can inspect the values.
    """
    if type(raw) is not bytes or not raw or len(raw) > MAX_FORM_BYTES:
        raise FormError("form must be nonempty bytes within size limit")
    if any(byte > 0x7F for byte in raw) or _BAD_PERCENT.search(raw):
        raise FormError("form must use valid ASCII percent encoding")
    result: dict[str, str] = {}
    for pair in raw.split(b"&"):
        if pair.count(b"=") != 1:
            raise FormError("each form member needs one equals separator")
        raw_key, raw_value = pair.split(b"=", 1)
        try:
            key = unquote_to_bytes(raw_key.replace(b"+", b" ")).decode("utf-8", "strict")
            value = unquote_to_bytes(raw_value.replace(b"+", b" ")).decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise FormError("form value must be valid UTF-8") from exc
        if not _FORM_KEY.fullmatch(key) or key in result:
            raise FormError("invalid or duplicate form key")
        result[key] = value
    return result
