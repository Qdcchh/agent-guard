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
    signature_message,
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


def test_signature_domains_are_explicit_and_separated():
    payload = {"version": "1"}
    capability = signature_message("capability", payload)
    invocation = signature_message("invocation", payload)
    assert capability.startswith(b"AGENT-GUARD/v1/capability\n")
    assert capability != invocation

    with pytest.raises(EncodingError):
        signature_message("capabilitY", payload)
