"""COSM2 trusted scheme selection, strict envelopes and compatibility."""

import json
from dataclasses import replace

import pytest

from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from agent_guard.cosign.encoding import public_point_to_spki
from agent_guard.cosign.protocol import AuthzParty, ExecParty
from agent_guard.gateway.config import threshold_policy
from agent_guard.gateway.errors import classify
from agent_guard.server.config import ConfigError
from agent_guard.threshold.codec import build_envelope, cosm2_message, encode_header, parse_envelope
from agent_guard.threshold.contracts import (
    COSM2_DOMAIN,
    COSM2_PROFILE,
    COSM2ApprovalExpired,
    ThresholdApprovalError,
    ThresholdApprovalPolicy,
)
from agent_guard.threshold.verifier import ThresholdApprovalVerifier
from tests.unit.test_threshold_contracts import (
    V3_VECTOR,
    VECTOR_NOW,
    _expected_from_vector,
    _policy_for,
    _vector,
)


def signed():
    action = _vector(V3_VECTOR)["action"]
    action["payment_digest"] = "0" * 64
    p1, p2 = ExecParty(), AuthzParty()
    public = p2.keygen_finish(p1.keygen_msg())
    p1.set_public(public)
    message = cosm2_message(action)
    signature = b"".join(
        v.to_bytes(32, "big")
        for v in p1.sign_round3(message, *p2.sign_round2(message, p1.sign_round1()))
    )
    policy = ThresholdApprovalPolicy(
        public_point_to_spki(public),
        action["policy_version"],
        action["key_epoch"],
        max_lifetime_seconds=86400,
        scheme="sm2-2p",
    )
    return action, signature, policy


def test_sm2_approval_verifies_with_shared_result_and_independent_domain():
    action, signature, policy = signed()
    assert cosm2_message(action).startswith(COSM2_DOMAIN)
    envelope = build_envelope(action, signature, profile=COSM2_PROFILE)
    expected = _expected_from_vector({"action": action})
    result = ThresholdApprovalVerifier(policy=policy).verify(
        encode_header(envelope),
        expected=expected,
        now=VECTOR_NOW,
    )
    assert result.envelope_bytes == envelope
    assert result.payment_digest == "0" * 64
    assert result.amount_fen == action["amount_fen"]
    with pytest.raises(ThresholdApprovalError):
        parse_envelope(envelope)


def test_amount_tamper_with_original_signature_is_mismatch_before_crypto():
    action, signature, policy = signed()
    expected = replace(_expected_from_vector({"action": action}), amount_fen=action["amount_fen"])
    action["amount_fen"] += 1
    with pytest.raises(ThresholdApprovalError) as exc:
        ThresholdApprovalVerifier(policy=policy).verify(
            encode_header(build_envelope(action, signature, profile=COSM2_PROFILE)),
            expected=expected,
            now=VECTOR_NOW,
        )
    assert exc.value.code == "APPROVAL_MISMATCH"


def test_fake_signature_and_expiry_have_distinct_rejections():
    action, _, policy = signed()
    expected = _expected_from_vector({"action": action})
    header = encode_header(build_envelope(action, b"\0" * 64, profile=COSM2_PROFILE))
    verifier = ThresholdApprovalVerifier(policy=policy)
    with pytest.raises(ThresholdApprovalError) as exc:
        verifier.verify(header, expected=expected, now=VECTOR_NOW)
    assert exc.value.code == "INVALID_SIGNATURE"
    with pytest.raises(COSM2ApprovalExpired) as exc:
        verifier.verify(header, expected=expected, now=action["expires_at"])
    assert classify(exc.value) == (401, "EXPIRED")
    from agent_guard.authorization.verifier import VerificationError

    assert classify(VerificationError("old expiry", code="EXPIRED")) == (403, "EXPIRED")


def test_both_scheme_mismatches_and_v2_are_rejected():
    action, signature, policy = signed()
    expected = _expected_from_vector({"action": action})
    sm2_header = encode_header(build_envelope(action, signature, profile=COSM2_PROFILE))
    frost_vector = _vector(V3_VECTOR)
    frost_header = encode_header(
        build_envelope(
            frost_vector["action"],
            bytes.fromhex(frost_vector["signature_hex"]),
        )
    )
    for configured, header in [(policy, frost_header), (_policy_for(frost_vector), sm2_header)]:
        with pytest.raises(ThresholdApprovalError):
            ThresholdApprovalVerifier(policy=configured).verify(
                header, expected=expected, now=VECTOR_NOW
            )
    action.pop("payment_digest")
    action["version"] = 2
    with pytest.raises(ThresholdApprovalError):
        cosm2_message(action)


def test_sm2_config_canonical_spki_and_exact_scheme_fields():
    _, _, policy = signed()
    data = dict(
        scheme="sm2-2p",
        group_public_key_spki_b64url=b64url_encode(policy.group_public_key),
        policy_version=policy.policy_version,
        key_epoch=policy.key_epoch,
        max_lifetime_seconds=policy.max_lifetime_seconds,
    )
    assert threshold_policy({"threshold_approval": data}) == policy
    for changes in [
        dict(scheme="unknown"),
        dict(group_public_key="ab" * 32),
        dict(group_public_key_spki_b64url=data["group_public_key_spki_b64url"] + "="),
        dict(policy_version=True),
        dict(group_public_key_spki_b64url="AA"),
    ]:
        with pytest.raises(ConfigError):
            threshold_policy({"threshold_approval": data | changes})


def test_cosm2_rejects_unknown_boolean_duplicate_and_noncanonical_inputs():
    action, signature, _ = signed()
    for mutate in [
        lambda a: a.update(extra=1),
        lambda a: a.update(amount_fen=True),
        lambda a: a.update(payment_digest="A" * 64),
        lambda a: a.update(version=True),
    ]:
        changed = dict(action)
        mutate(changed)
        with pytest.raises(ThresholdApprovalError):
            cosm2_message(changed)
    envelope = build_envelope(action, signature, profile=COSM2_PROFILE)
    duplicate = envelope.replace(b'"profile":', b'"profile":"duplicate","profile":')
    for raw in [duplicate, envelope + b" "]:
        with pytest.raises(ThresholdApprovalError):
            parse_envelope(raw, profile=COSM2_PROFILE)
    value = json.loads(envelope)
    value["signature"] += "="
    with pytest.raises(ThresholdApprovalError):
        parse_envelope(canonical_json_bytes(value), profile=COSM2_PROFILE)


@pytest.mark.parametrize("paid", [False, True])
def test_normal_sentinel_rejects_real_digest_but_paid_route_preserves_it(monkeypatch, paid):
    """Isolate routing decision; cryptographic acceptance is covered above."""
    from types import SimpleNamespace

    from agent_guard.gateway.endpoint import GatewayEndpoint
    from agent_guard.gateway.errors import GatewayError

    endpoint = object.__new__(GatewayEndpoint)
    endpoint._threshold = SimpleNamespace(
        policy=SimpleNamespace(
            scheme="sm2-2p",
            tool_id="procurement.order.create",
        )
    )
    endpoint._payment = object() if paid else None
    endpoint._now = lambda: VECTOR_NOW
    endpoint._receipt_verifier = None
    endpoint._verifier = SimpleNamespace(verify_bundle=lambda *a, **k: object())
    endpoint._execution = SimpleNamespace(accept_response=lambda *a, **k: {"accepted": True})
    endpoint._verify_approval = lambda *a: SimpleNamespace(payment_digest="a" * 64)
    monkeypatch.setattr("agent_guard.gateway.endpoint.payment_binding", lambda *a: (None, None))
    action = _vector(V3_VECTOR)["action"]
    body = canonical_json_bytes(
        dict(
            profile="GM-MVP-1",
            task_id=action["task_id"],
            tool_id=action["tool_id"],
            tool_version=action["tool_version"],
            idempotency_key=action["idempotency_key"],
            params={
                key: action[key]
                for key in ["request_id", "quote_id", "quote_version", "items", "delivery_id"]
            },
        )
    )
    if paid:
        assert endpoint.handle("/v1/tools/invoke", "", "", body, approval=b"opaque")[0] == 202
    else:
        with pytest.raises(GatewayError) as exc:
            endpoint.handle("/v1/tools/invoke", "", "", body, approval=b"opaque")
        assert classify(exc.value) == (409, "APPROVAL_MISMATCH")


def test_final_transaction_cosm2_expiry_uses_401(monkeypatch):
    from types import SimpleNamespace

    from agent_guard.threshold.binding import approval_binding

    action, signature, policy = signed()
    approval = ThresholdApprovalVerifier(policy=policy).verify(
        encode_header(build_envelope(action, signature, profile=COSM2_PROFILE)),
        expected=_expected_from_vector({"action": action}),
        now=VECTOR_NOW,
    )
    conn = SimpleNamespace(
        execute=lambda *a: SimpleNamespace(fetchone=lambda: ("op", approval.message_sha256))
    )
    monkeypatch.setattr(
        "agent_guard.threshold.binding.ledger_store.db_now_epoch", lambda c: approval.expires_at
    )
    _, final = approval_binding(approval)
    with pytest.raises(COSM2ApprovalExpired) as exc:
        final(conn, SimpleNamespace(operation_id="op"), None)
    assert classify(exc.value) == (401, "EXPIRED")
