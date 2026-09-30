"""Canonical JSON, strict JSON parsing, and unpadded base64url."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import NoReturn, TypeAlias, cast

import rfc8785

MAX_SAFE_INTEGER = (1 << 53) - 1

_BASE64URL_RE = re.compile(r"[A-Za-z0-9_-]*\Z", re.ASCII)

JsonValue: TypeAlias = None | bool | int | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class EncodingError(ValueError):
    """The input is not valid under the Agent Guard v1 encoding profile."""


class DuplicateKeyError(EncodingError):
    """A JSON object contains a duplicate member name."""


def _reject_float(_: str) -> NoReturn:
    raise EncodingError("floating-point values are not allowed")


def _reject_constant(value: str) -> NoReturn:
    raise EncodingError(f"non-finite JSON number is not allowed: {value}")


def _parse_int(value: str) -> int:
    if value.startswith("-"):
        raise EncodingError("negative integers are not allowed")
    parsed = int(value)
    if not 0 <= parsed <= MAX_SAFE_INTEGER:
        raise EncodingError(f"integer is outside 0..{MAX_SAFE_INTEGER}")
    return parsed


def _object_from_pairs(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON member: {key!r}")
        result[key] = value
    return result


def _validate_json_value(value: object, path: str = "$") -> None:
    if value is None or type(value) in (bool, str):
        return
    if type(value) is int:
        if not 0 <= value <= MAX_SAFE_INTEGER:
            raise EncodingError(f"integer at {path} is outside 0..{MAX_SAFE_INTEGER}")
        return
    if type(value) is float:
        raise EncodingError(f"floating-point value at {path} is not allowed")
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise EncodingError(f"object member name at {path} is not a string")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise EncodingError(f"unsupported value at {path}: {type(value).__name__}")


def load_strict_json(raw: bytes | str) -> JsonValue:
    """Parse one JSON value while rejecting duplicates and unsafe number forms."""

    if type(raw) is bytes:
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise EncodingError("JSON must be valid UTF-8") from exc
    elif type(raw) is str:
        text = raw
    else:
        raise TypeError("raw JSON must be bytes or str")

    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_from_pairs,
            parse_float=_reject_float,
            parse_int=_parse_int,
            parse_constant=_reject_constant,
        )
    except EncodingError:
        raise
    except json.JSONDecodeError as exc:
        raise EncodingError("invalid JSON") from exc

    _validate_json_value(value)
    return cast(JsonValue, value)


def canonical_json_bytes(value: JsonValue) -> bytes:
    """Return RFC 8785 bytes after applying the stricter v1 value profile."""

    _validate_json_value(value)
    try:
        return rfc8785.dumps(value)
    except rfc8785.CanonicalizationError as exc:
        raise EncodingError("value cannot be canonicalized with RFC 8785") from exc


def b64url_encode(value: bytes) -> str:
    """Encode bytes as canonical, unpadded base64url."""

    if type(value) is not bytes:
        raise TypeError("value must be bytes")
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    """Decode canonical, unpadded base64url and reject alternative spellings."""

    if type(value) is not str:
        raise TypeError("value must be str")
    if not _BASE64URL_RE.fullmatch(value):
        raise EncodingError("value is not unpadded base64url")

    encoded = value.encode("ascii")
    padded = encoded + b"=" * (-len(encoded) % 4)
    try:
        decoded = base64.b64decode(padded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise EncodingError("invalid base64url value") from exc
    if b64url_encode(decoded) != value:
        raise EncodingError("non-canonical base64url value")
    return decoded
