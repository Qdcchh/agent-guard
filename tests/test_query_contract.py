"""The compatibility DTO stays distinct; canonical query requires identity/method."""

from dataclasses import MISSING, fields

import pytest

from agent_guard.authorization.verifier import (
    InvocationVerifier,
    VerificationError,
    VerifiedOperationQuery,
)
from agent_guard.contracts.execution import VerifiedResultQuery
from agent_guard.crypto.sm import generate_sm2_private_key
from agent_guard.identity.resolver import IdentityResolver


def test_canonical_query_requires_subject_and_explicit_method():
    canonical = {f.name: f for f in fields(VerifiedResultQuery)}
    public = {f.name for f in fields(VerifiedOperationQuery)}
    assert canonical["subject"].default is MISSING
    assert canonical["method"].default is MISSING
    assert "subject" in public and "method" not in public
    assert not {"tool_id", "idempotency_key", "canonical_params"} & set(canonical)


def test_callback_only_verifier_cannot_enter_production_query_or_bundle():
    verifier = InvocationVerifier(
        issuer="https://auth.agent-guard.test",
        as_keys={"as": generate_sm2_private_key().public_key()},
        identities=IdentityResolver({}, allowed_hosts=frozenset({"identity.agent-guard.test"})),
        stage_evidence=lambda *_: "fixture-only",
    )
    for method in [verifier.verify_bundle, verifier.verify_canonical_result_read]:
        with pytest.raises(VerificationError, match="real trusted"):
            method("token", "proof", body=b"{}", now=1)
