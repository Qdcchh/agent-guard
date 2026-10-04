"""Protocol encoding tests; malformed alternatives must fail closed."""

import pytest

from agent_guard.contracts import (
    MAX_SAFE_INTEGER,
    DuplicateKeyError,
    EncodingError,
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)


def test_strict_json_and_rfc8785_canonicalization():
    parsed = load_strict_json(b'{"z":0,"a":[true,null,"\xe4\xb8\xad"]}')
    assert canonical_json_bytes(parsed) == b'{"a":[true,null,"\xe4\xb8\xad"],"z":0}'


def test_duplicate_member_is_rejected_before_canonicalization():
    with pytest.raises(DuplicateKeyError):
        load_strict_json('{"scope":"read","scope":"write"}')


@pytest.mark.parametrize(
    "raw",
    [
        '{"amount":1.0}',
        '{"amount":-1}',
        '{"amount":-0}',
        f'{{"amount":{MAX_SAFE_INTEGER + 1}}}',
        '{"amount":NaN}',
    ],
)
def test_unsafe_number_forms_are_rejected(raw):
    with pytest.raises(EncodingError):
        load_strict_json(raw)


def test_programmatic_non_json_types_are_rejected():
    with pytest.raises(EncodingError):
        canonical_json_bytes({"items": (1, 2)})  # type: ignore[dict-item]
    with pytest.raises(EncodingError):
        canonical_json_bytes({1: "value"})  # type: ignore[dict-item]


def test_base64url_round_trip_and_strict_rejections():
    raw = b"\x00\xfb\xffagent-guard"
    encoded = b64url_encode(raw)
    assert "=" not in encoded
    assert b64url_decode(encoded) == raw

    for invalid in (encoded + "=", "ab+c", "a", "YW Jj"):
        with pytest.raises(EncodingError):
            b64url_decode(invalid)


def test_duplicate_key_rejection_covers_nested_protected_headers():
    with pytest.raises(DuplicateKeyError):
        load_strict_json('{"alg":"expected","kid":"one","kid":"two"}')


@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff"])
def test_unpaired_surrogates_in_values_and_keys_are_rejected(surrogate):
    escaped = f"\\u{ord(surrogate):04x}"
    for raw in (f'{{"value":"{escaped}"}}', f'{{"{escaped}":1}}'):
        with pytest.raises(EncodingError, match="surrogate"):
            load_strict_json(raw)
    with pytest.raises(EncodingError, match="surrogate"):
        load_strict_json('{"value":"' + surrogate + '"}')
    for value in ({"value": surrogate}, {surrogate: "value"}):
        with pytest.raises(EncodingError, match="surrogate"):
            canonical_json_bytes(value)


def test_chinese_and_supplementary_unicode_remain_canonical():
    value = load_strict_json('{"中文":"😀"}')
    assert canonical_json_bytes(value) == '{"中文":"😀"}'.encode("utf-8")


@pytest.mark.parametrize(
    "raw",
    [
        "1" * 5000,
        "[" * 1500 + "0" + "]" * 1500,
        "[0," * 4096 + "0" + "]" * 4096,
        '"' + "x" * 65536 + '"',
    ],
    ids=["large-integer", "deep-json", "wide-json", "large-raw-body"],
)
def test_raw_json_bounds_fail_with_profile_error(raw):
    with pytest.raises(EncodingError):
        load_strict_json(raw)


def test_programmatic_json_bounds_fail_without_recursion_or_large_output():
    deep: object = 0
    for _ in range(1500):
        deep = [deep]
    for value in (deep, [0] * 4096, {"text": "\n" * 40000}):
        with pytest.raises(EncodingError):
            canonical_json_bytes(value)
