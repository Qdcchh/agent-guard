"""Canonical JSON, strict JSON parsing, and unpadded base64url."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import NoReturn, TypeAlias, cast

import rfc8785

MAX_SAFE_INTEGER = (1 << 53) - 1
MAX_JSON_BYTES = 65536
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 4096

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
    # Check the lexical form before int(): Python's decimal conversion limit
    # otherwise leaks ValueError for attacker-controlled long JSON numbers.
    if len(value) > len(str(MAX_SAFE_INTEGER)):
        raise EncodingError(f"integer is outside 0..{MAX_SAFE_INTEGER}")
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


def _validate_json_string(value: str, path: str) -> int:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise EncodingError(f"unpaired Unicode surrogate at {path}")
    size = len(value.encode("utf-8"))
    if size > MAX_JSON_BYTES:
        raise EncodingError(f"string at {path} exceeds the JSON byte limit")
    return size


def _validate_json_value(value: object) -> None:
    stack: list[tuple[object, int, str]] = [(value, 0, "$")]
    nodes = 0
    string_bytes = 0
    while stack:
        item, depth, path = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise EncodingError("JSON structure exceeds the node limit")
        if depth > MAX_JSON_DEPTH:
            raise EncodingError("JSON structure exceeds the depth limit")
        if item is None or type(item) is bool:
            continue
        if type(item) is str:
            string_bytes += _validate_json_string(item, path)
        elif type(item) is int:
            if not 0 <= item <= MAX_SAFE_INTEGER:
                raise EncodingError(f"integer at {path} is outside 0..{MAX_SAFE_INTEGER}")
        elif type(item) is float:
            raise EncodingError(f"floating-point value at {path} is not allowed")
        elif type(item) is list:
            if len(item) > MAX_JSON_NODES - nodes - len(stack):
                raise EncodingError("JSON structure exceeds the node limit")
            stack.extend((child, depth + 1, f"{path}[{index}]") for index, child in enumerate(item))
        elif type(item) is dict:
            if len(item) > MAX_JSON_NODES - nodes - len(stack):
                raise EncodingError("JSON structure exceeds the node limit")
            for key, child in item.items():
                if type(key) is not str:
                    raise EncodingError(f"object member name at {path} is not a string")
                string_bytes += _validate_json_string(key, path)
                stack.append((child, depth + 1, f"{path}.{key}"))
        else:
            raise EncodingError(f"unsupported value at {path}: {type(item).__name__}")
        if string_bytes > MAX_JSON_BYTES:
            raise EncodingError("JSON strings exceed the byte limit")


def _decode_json(raw: bytes | str, *, integer_parser) -> JsonValue:
    """Shared bounded lexical decoder; callers must validate their exact schema."""

    if type(raw) is bytes:
        if len(raw) > MAX_JSON_BYTES:
            raise EncodingError("JSON exceeds the byte limit")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise EncodingError("JSON must be valid UTF-8") from exc
    elif type(raw) is str:
        text = raw
    else:
        raise TypeError("raw JSON must be bytes or str")

    try:
        if len(text.encode("utf-8")) > MAX_JSON_BYTES:
            raise EncodingError("JSON exceeds the byte limit")
    except UnicodeEncodeError as exc:
        raise EncodingError("JSON contains an unpaired Unicode surrogate") from exc

    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_from_pairs,
            parse_float=_reject_float,
            parse_int=integer_parser,
            parse_constant=_reject_constant,
        )
    except EncodingError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise EncodingError("invalid JSON") from exc

    return cast(JsonValue, value)


def load_strict_json(raw: bytes | str) -> JsonValue:
    """Strict generic profile: negative integers remain forbidden."""
    value = _decode_json(raw, integer_parser=_parse_int)
    _validate_json_value(value)
    return value


def canonical_json_bytes(value: JsonValue) -> bytes:
    """Return RFC 8785 bytes after applying the stricter v1 value profile."""

    _validate_json_value(value)
    try:
        encoded = rfc8785.dumps(value)
    except rfc8785.CanonicalizationError as exc:
        raise EncodingError("value cannot be canonicalized with RFC 8785") from exc
    if len(encoded) > MAX_JSON_BYTES:
        raise EncodingError("canonical JSON exceeds the byte limit")
    return encoded


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
