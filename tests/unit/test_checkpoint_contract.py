"""Real SM2 checkpoint domain separation and exact signed-claims controls."""

from dataclasses import asdict, replace

import pytest

from agent_guard.audit.checkpoint import sign_checkpoint, verify_checkpoint
from agent_guard.audit.contracts import CheckpointClaims, CheckpointTrust
from agent_guard.contracts.encoding import EncodingError, b64url_encode, canonical_json_bytes
from agent_guard.crypto.sm import (
    JWS_ALG,
    InvalidSm2Signature,
    generate_sm2_private_key,
    serialize_sm2_public_key,
    sign_compact_jws,
    sm3_b64url,
)
from tests.fixtures.a31_common import DIGEST, SCOPE, STAMP


@pytest.mark.parametrize(
    "case",
    [
        "typ",
        "alg",
        "profile_version",
        "scope",
        "kid",
        "signature",
        "wrongrole",
        "spki",
        "duplicate",
        "unknown",
        "bool",
        "range",
        "oversize",
        "protectedkid",
    ],
)
def test_checkpoint_sm2_type_scope_version(case):
    key = generate_sm2_private_key()
    trust = CheckpointTrust(
        "audit", "AUDIT_SIGNER", serialize_sm2_public_key(key.public_key()), 1, 3
    )
    claims = CheckpointClaims(
        "GM-MVP-1",
        "AG-CHECKPOINT-1",
        "cp",
        SCOPE.stream_id,
        SCOPE.gateway_id,
        SCOPE.tenant_id,
        SCOPE.task_id,
        1,
        2,
        DIGEST,
        None,
        STAMP,
        "audit",
    )
    original = sign_checkpoint(claims, private_key=key, key_id="audit")
    observed = verify_checkpoint(original, trust=(trust,), expected_scope=SCOPE)
    assert observed.claims == claims and observed.jws_digest == sm3_b64url(original.encode("ascii"))
    token, trusts, scope = original, (trust,), SCOPE
    if case == "typ":
        for typ in ("ag-receipt+jwt", "ag-at+jwt", "ag-pop+jwt"):
            bad = sign_compact_jws(key, asdict(claims), key_id="audit", token_type=typ)
            with pytest.raises(InvalidSm2Signature):
                verify_checkpoint(bad, trust=trusts, expected_scope=scope)
        return
    if case == "alg":
        parts = original.split(".")
        parts[0] = b64url_encode(
            canonical_json_bytes({"typ": "ag-checkpoint+jwt", "alg": "none", "kid": "audit"})
        )
        token = ".".join(parts)
    elif case in ("profile_version", "unknown", "bool", "protectedkid"):
        value = asdict(claims)
        if case == "profile_version":
            value["checkpoint_version"] = "AG-CHECKPOINT-2"
        if case == "unknown":
            value["public_key"] = b64url_encode(trust.spki_der)
        if case == "bool":
            value["sequence"] = True
        if case == "protectedkid":
            value["kid"] = "other"
        token = sign_compact_jws(key, value, key_id="audit", token_type="ag-checkpoint+jwt")
    elif case == "scope":
        scope = replace(SCOPE, tenant_id="other")
    elif case == "kid":
        trusts = (replace(trust, kid="unknown"),)
    elif case == "signature":
        parts = original.split(".")
        parts[2] = b64url_encode(bytes(64))
        token = ".".join(parts)
    elif case == "wrongrole":
        trusts = (replace(trust, role="RECEIPT_SIGNER"),)
    elif case == "spki":
        trusts = (replace(trust, spki_der=b"fake"),)
    elif case == "duplicate":
        parts = original.split(".")
        payload = canonical_json_bytes(asdict(claims))
        parts[1] = b64url_encode(payload[:-1] + b',"sequence":2}')
        token = ".".join(parts)
    elif case == "range":
        trusts = (replace(trust, first_sequence=3),)
    elif case == "oversize":
        token = "A" * 16385
    with pytest.raises((ValueError, TypeError, EncodingError)):
        verify_checkpoint(token, trust=trusts, expected_scope=scope)
    assert JWS_ALG.startswith("https://")
