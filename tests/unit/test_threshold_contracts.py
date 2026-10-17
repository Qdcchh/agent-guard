"""Cross-language vectors and strict approval-header boundaries (no database)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from agent_guard.threshold.codec import (
    ACTION_FIELD_ORDER,
    ACTION_FIELD_ORDER_V3,
    action_message,
    build_envelope,
    compute_params_digest,
    decode_header,
    encode_header,
    parse_action,
    parse_action_v3,
    parse_envelope,
)
from agent_guard.threshold.contracts import (
    ACTION_DOMAIN,
    ACTION_DOMAIN_V3,
    ACTION_VERSION_V3,
    MAX_ENVELOPE_BYTES,
    ThresholdApprovalError,
    ThresholdApprovalExpectation,
    ThresholdApprovalPolicy,
)
from agent_guard.threshold.verifier import ThresholdApprovalVerifier

REPO = Path(__file__).resolve().parents[2]
V2_VECTOR = REPO / "tools/threshold_demo/tests/public-vector-v2.json"
V3_VECTOR = REPO / "tools/threshold_demo/tests/public-vector-v3.json"
V1_VECTOR = REPO / "tools/threshold_demo/tests/public-vector.json"

V1_FIELD_ORDER = (
    "version",
    "tenant_id",
    "task_id",
    "root_grant_id",
    "grant_id",
    "holder_client_id",
    "holder_kid",
    "audience",
    "tool_id",
    "currency",
    "policy_version",
    "key_epoch",
    "action_id",
    "idempotency_key",
    "request_id",
    "quote_id",
    "quote_version",
    "items",
    "delivery_id",
    "amount_fen",
    "canonical_params_sha256",
    "expires_at",
)


def _vector(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _message_from_fields(action: dict, order, domain: bytes) -> bytes:
    """Rebuild the message from semantic fields in the declared wire order."""
    ordered = {name: action[name] for name in order}
    return domain + json.dumps(ordered, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _ed25519(public_hex: str):
    return Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex))


def test_v2_public_vector_rebuilds_exact_bytes_and_verifies():
    vector = _vector(V2_VECTOR)
    action = vector["action"]
    assert action["version"] == 2
    message = _message_from_fields(action, ACTION_FIELD_ORDER, ACTION_DOMAIN)
    assert hashlib.sha256(message).hexdigest() == vector["message_sha256"]
    signature = bytes.fromhex(vector["signature_hex"])
    _ed25519(vector["group_public_key_hex"]).verify(signature, message)
    with pytest.raises(InvalidSignature):
        _ed25519(vector["group_public_key_hex"]).verify(signature, message + b"x")


def test_v1_vector_bytes_remain_frozen():
    vector = _vector(V1_VECTOR)
    message = _message_from_fields(
        vector["action"], V1_FIELD_ORDER, b"AGENT-GUARD-THRESHOLD-ACTION-V1\n"
    )
    assert hashlib.sha256(message).hexdigest() == vector["message_sha256"]
    assert b'"tool_version"' not in message
    _ed25519(vector["group_public_key_hex"]).verify(bytes.fromhex(vector["signature_hex"]), message)


def test_codec_builds_the_same_bytes_as_the_committed_vector():
    vector = _vector(V2_VECTOR)
    parsed = parse_action(vector["action"])
    assert action_message(parsed) == _message_from_fields(
        vector["action"], ACTION_FIELD_ORDER, ACTION_DOMAIN
    )
    assert parsed["canonical_params_sha256"] == compute_params_digest(
        request_id=parsed["request_id"],
        quote_id=parsed["quote_id"],
        quote_version=parsed["quote_version"],
        items=[(item["sku"], item["quantity"]) for item in parsed["items"]],
        delivery_id=parsed["delivery_id"],
    )


VECTOR_NOW = 4_102_444_800 - 3_600


def _expected_from_vector(vector: dict) -> ThresholdApprovalExpectation:
    action = vector["action"]
    params = json.dumps(
        {
            "request_id": action["request_id"],
            "quote_id": action["quote_id"],
            "quote_version": action["quote_version"],
            "items": action["items"],
            "delivery_id": action["delivery_id"],
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return ThresholdApprovalExpectation(
        tenant_id=action["tenant_id"],
        task_id=action["task_id"],
        root_grant_id=action["root_grant_id"],
        grant_id=action["grant_id"],
        holder_client_id=action["holder_client_id"],
        holder_kid=action["holder_kid"],
        tool_id=action["tool_id"],
        tool_version=action["tool_version"],
        idempotency_key=action["idempotency_key"],
        canonical_params=params,
        path_grant_ids=tuple(action["path_grant_ids"]),
    )


def _policy_for(vector: dict) -> ThresholdApprovalPolicy:
    action = vector["action"]
    return ThresholdApprovalPolicy(
        group_public_key=bytes.fromhex(vector["group_public_key_hex"]),
        policy_version=action["policy_version"],
        key_epoch=action["key_epoch"],
        max_lifetime_seconds=86400,
    )


def test_verifier_accepts_only_exact_vector_facts():
    vector = _vector(V2_VECTOR)
    policy = _policy_for(vector)
    verifier = ThresholdApprovalVerifier(policy=policy)
    header = encode_header(build_envelope(vector["action"], bytes.fromhex(vector["signature_hex"])))
    expected = _expected_from_vector(vector)
    approval = verifier.verify(header, expected=expected, now=VECTOR_NOW)
    assert approval.action_id == vector["action"]["action_id"]
    assert approval.path_grant_ids == tuple(vector["action"]["path_grant_ids"])
    assert approval.expires_at == vector["action"]["expires_at"]

    # every request-side fact must match exactly
    for mutated in (
        replace(expected, tenant_id="tenant-other"),
        replace(expected, task_id="task-other"),
        replace(expected, root_grant_id="grant-other"),
        replace(expected, grant_id="grant-other"),
        replace(expected, path_grant_ids=("grant-root", "grant-leaf")),
        replace(expected, holder_client_id="agent-other"),
        replace(expected, holder_kid="kid-other"),
        replace(expected, tool_version="2"),
        replace(expected, idempotency_key="idem-other"),
        replace(expected, canonical_params=b'{"request_id":"req-001"}'),
    ):
        with pytest.raises(ThresholdApprovalError) as exc:
            verifier.verify(header, expected=mutated, now=VECTOR_NOW)
        assert exc.value.code in ("APPROVAL_MISMATCH", "INVALID_APPROVAL")


def test_verifier_rejects_wrong_key_trust_and_expiry():
    vector = _vector(V2_VECTOR)
    header = encode_header(build_envelope(vector["action"], bytes.fromhex(vector["signature_hex"])))
    expected = _expected_from_vector(vector)
    other_key = bytes(range(32))
    wrong = ThresholdApprovalVerifier(
        policy=ThresholdApprovalPolicy(
            group_public_key=other_key,
            policy_version=vector["action"]["policy_version"],
            key_epoch=vector["action"]["key_epoch"],
            max_lifetime_seconds=86400,
        )
    )
    with pytest.raises(ThresholdApprovalError) as exc:
        wrong.verify(header, expected=expected, now=VECTOR_NOW)
    assert exc.value.code == "INVALID_SIGNATURE"

    policy = _policy_for(vector)
    changed_policy = ThresholdApprovalVerifier(
        policy=ThresholdApprovalPolicy(
            group_public_key=policy.group_public_key,
            policy_version=policy.policy_version + 1,
            key_epoch=policy.key_epoch,
            max_lifetime_seconds=policy.max_lifetime_seconds,
        )
    )
    with pytest.raises(ThresholdApprovalError) as exc:
        changed_policy.verify(header, expected=expected, now=VECTOR_NOW)
    assert exc.value.code == "APPROVAL_MISMATCH"

    changed_epoch = ThresholdApprovalVerifier(
        policy=ThresholdApprovalPolicy(
            group_public_key=policy.group_public_key,
            policy_version=policy.policy_version,
            key_epoch=policy.key_epoch + 1,
            max_lifetime_seconds=policy.max_lifetime_seconds,
        )
    )
    with pytest.raises(ThresholdApprovalError) as exc:
        changed_epoch.verify(header, expected=expected, now=VECTOR_NOW)
    assert exc.value.code == "APPROVAL_MISMATCH"

    verifier = ThresholdApprovalVerifier(policy=policy)
    with pytest.raises(ThresholdApprovalError) as exc:
        verifier.verify(header, expected=expected, now=vector["action"]["expires_at"])
    assert exc.value.code == "EXPIRED"
    with pytest.raises(ThresholdApprovalError):
        verifier.verify(header, expected=expected, now=-1)
    tight = ThresholdApprovalVerifier(
        policy=ThresholdApprovalPolicy(
            group_public_key=policy.group_public_key,
            policy_version=policy.policy_version,
            key_epoch=policy.key_epoch,
            max_lifetime_seconds=60,
        )
    )
    with pytest.raises(ThresholdApprovalError) as exc:
        tight.verify(header, expected=expected, now=VECTOR_NOW)
    assert exc.value.code == "INVALID_APPROVAL"


def test_envelope_boundaries_reject_ambiguity():
    vector = _vector(V2_VECTOR)
    action = parse_action(vector["action"])
    signature = bytes.fromhex(vector["signature_hex"])
    envelope = build_envelope(action, signature)
    assert parse_envelope(envelope) == (action, signature)
    assert decode_header(encode_header(envelope)) == envelope

    # duplicate JSON member
    duplicated = envelope.replace(
        b'"profile":"AG-THRESHOLD-APPROVAL-1"',
        b'"profile":"AG-THRESHOLD-APPROVAL-1","profile":"AG-THRESHOLD-APPROVAL-1"',
    )
    with pytest.raises(ThresholdApprovalError):
        parse_envelope(duplicated)

    # unknown member / wrong profile / non-canonical spacing
    unknown = envelope.replace(b'"profile":', b'"extra":1,"profile":')
    with pytest.raises(ThresholdApprovalError) as exc:
        parse_envelope(unknown)
    assert exc.value.code == "INVALID_SCHEMA"
    with pytest.raises(ThresholdApprovalError):
        parse_envelope(envelope.replace(b"AG-THRESHOLD-APPROVAL-1", b"AG-THRESHOLD-APPROVAL-2"))
    with pytest.raises(ThresholdApprovalError):
        parse_envelope(envelope.replace(b'{"action":', b'{"action": ', 1))
    # unknown action field and non-canonical digest
    with pytest.raises(ThresholdApprovalError):
        parse_action({**action, "new_security_field": True})
    tampered = dict(action)
    tampered["canonical_params_sha256"] = "0" * 64
    with pytest.raises(ThresholdApprovalError):
        parse_envelope(build_envelope(tampered, signature))
    with pytest.raises(ThresholdApprovalError):
        parse_envelope(envelope + b" ")
    with pytest.raises(ThresholdApprovalError):
        parse_envelope(b"x" * (MAX_ENVELOPE_BYTES + 1))
    with pytest.raises(ThresholdApprovalError):
        decode_header(b"not+base64!")
    with pytest.raises(ThresholdApprovalError):
        decode_header(b"a" * 33000)


def test_action_field_order_constant_matches_wire_contract():
    assert len(ACTION_FIELD_ORDER) == 24
    assert ACTION_FIELD_ORDER[0] == "version"
    assert ACTION_FIELD_ORDER[-1] == "expires_at"
    assert "path_grant_ids" in ACTION_FIELD_ORDER and "tool_version" in ACTION_FIELD_ORDER
    assert re.fullmatch(r"[A-Za-z0-9._:@\-]+", "grant-mid_1.2:x@y")


def test_v3_public_vector_appends_payment_digest_and_verifies():
    vector = _vector(V3_VECTOR)
    action = vector["action"]
    assert action["version"] == ACTION_VERSION_V3
    assert ACTION_FIELD_ORDER_V3 == ACTION_FIELD_ORDER + ("payment_digest",)
    assert len(action) == len(ACTION_FIELD_ORDER_V3) == 25
    message = _message_from_fields(action, ACTION_FIELD_ORDER_V3, ACTION_DOMAIN_V3)
    assert hashlib.sha256(message).hexdigest() == vector["message_sha256"]
    signature = bytes.fromhex(vector["signature_hex"])
    _ed25519(vector["group_public_key_hex"]).verify(signature, message)
    # The digest is inside the signed bytes: flipping it invalidates the quorum signature.
    digest = action["payment_digest"]
    flipped = ("0" if digest[0] != "0" else "1") + digest[1:]
    assert flipped != digest
    tampered = message.replace(digest.encode("ascii"), flipped.encode("ascii"), 1)
    assert tampered != message
    with pytest.raises(InvalidSignature):
        _ed25519(vector["group_public_key_hex"]).verify(signature, tampered)
    # Codec rebuilds exactly the committed bytes and keeps the digest last.
    parsed = parse_action_v3(action)
    assert action_message(parsed) == message
    assert list(parsed)[-1] == "payment_digest"


def test_parse_action_v3_rejects_missing_or_malformed_digest():
    action = _vector(V3_VECTOR)["action"]
    for mutated in (
        {key: value for key, value in action.items() if key != "payment_digest"},
        {**action, "payment_digest": action["payment_digest"].upper()},
        {**action, "payment_digest": action["payment_digest"][:-1]},
    ):
        with pytest.raises(ThresholdApprovalError):
            parse_action_v3(mutated)


def test_verifier_carries_v3_digest_and_leaves_v2_without_one():
    vector = _vector(V3_VECTOR)
    verifier = ThresholdApprovalVerifier(policy=_policy_for(vector))
    header = encode_header(build_envelope(vector["action"], bytes.fromhex(vector["signature_hex"])))
    expected = _expected_from_vector(vector)
    approval = verifier.verify(header, expected=expected, now=VECTOR_NOW)
    assert approval.payment_digest == vector["action"]["payment_digest"]
    assert approval.action_id == vector["action"]["action_id"]
    # A tampered digest is rejected before any acceptance path sees the facts.
    tampered = dict(vector["action"])
    tampered["payment_digest"] = ("0" if tampered["payment_digest"][0] != "0" else "1") + (
        tampered["payment_digest"][1:]
    )
    with pytest.raises(ThresholdApprovalError) as exc:
        verifier.verify(
            encode_header(build_envelope(tampered, bytes.fromhex(vector["signature_hex"]))),
            expected=expected,
            now=VECTOR_NOW,
        )
    assert exc.value.code == "INVALID_SIGNATURE"
    # V2 approvals keep the field absent (None), so they can never fund a payment.
    v2 = _vector(V2_VECTOR)
    v2_approval = ThresholdApprovalVerifier(policy=_policy_for(v2)).verify(
        encode_header(build_envelope(v2["action"], bytes.fromhex(v2["signature_hex"]))),
        expected=_expected_from_vector(v2),
        now=VECTOR_NOW,
    )
    assert v2_approval.payment_digest is None
