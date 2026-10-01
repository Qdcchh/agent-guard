"""result-read negative cases the fixed-vector suite does not already cover.

Already covered elsewhere (not repeated here): wrong purpose, extra body
fields, wrong endpoint, tampered operation_id and stolen holder key.
"""

from __future__ import annotations

import dataclasses

import pytest

from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.authorization.verifier import InvocationVerifier, VerificationError
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.contracts.ledger import QUERY_ENDPOINT
from agent_guard.crypto.sm import sign_compact_jws
from agent_guard.identity.resolver import IdentityResolver
from tests.fixtures import interop

NOW = 1_800_000_000


def _verifier(*, resolver=None) -> InvocationVerifier:
    return InvocationVerifier(
        issuer=interop.ISSUER,
        as_keys={interop.AS_KID: interop.as_key().public_key()},
        identities=resolver if resolver is not None else interop.resolver(),
        stage_evidence=lambda token, proof, body: "evidence-result-read",
    )


def _reject(verifier, chain, *, proof, body, now=NOW, method="POST", token=None):
    with pytest.raises(VerificationError):
        verifier.verify_result_read(
            token if token is not None else chain.executor_token,
            proof,
            endpoint=QUERY_ENDPOINT,
            method=method,
            body=body,
            now=now,
        )


def test_result_read_rejects_expired_and_future_proofs():
    chain = interop.interop_chain(NOW)
    request = interop.result_read_request()
    body = canonical_json_bytes(request)
    expired = interop.result_read_proof(chain, request, NOW - 100)
    _reject(_verifier(), chain, proof=expired, body=body)
    future = interop.result_read_proof(chain, request, NOW + 30)
    _reject(_verifier(), chain, proof=future, body=body)


def test_result_read_rejects_expired_token():
    chain = interop.interop_chain(NOW)
    claims = dict(chain.executor_claims)
    claims["iat"] = NOW - 400
    claims["nbf"] = NOW - 400
    claims["exp"] = NOW - 100
    expired_token = sign_compact_jws(
        interop.as_key(), claims, key_id=interop.AS_KID, token_type="ag-at+jwt"
    )
    request = interop.result_read_request()
    proof = sign_ag_proof(
        interop.agent_key("executor"),
        kid=interop.agent_kid("executor"),
        client_id="agent-executor",
        purpose="result-read",
        endpoint=QUERY_ENDPOINT,
        body=request,
        token=expired_token,
        now=NOW,
    )
    _reject(
        _verifier(), chain, proof=proof, body=canonical_json_bytes(request), token=expired_token
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("iss", "https://evil.example"), ("aud", "https://evil.example")],
)
def test_result_read_rejects_wrong_issuer_or_audience(field, value):
    chain = interop.interop_chain(NOW)
    request = interop.result_read_request()
    claims = dict(chain.executor_claims)
    claims[field] = value
    wrong_token = sign_compact_jws(
        interop.as_key(), claims, key_id=interop.AS_KID, token_type="ag-at+jwt"
    )
    proof = interop.result_read_proof(chain, request, NOW)
    _reject(_verifier(), chain, proof=proof, body=canonical_json_bytes(request), token=wrong_token)


def test_result_read_rejects_wrong_method():
    chain = interop.interop_chain(NOW)
    request = interop.result_read_request()
    proof = interop.result_read_proof(chain, request, NOW)
    _reject(
        _verifier(),
        chain,
        proof=proof,
        body=canonical_json_bytes(request),
        method="GET",
    )


def test_result_read_rejects_task_mismatch_and_tampered_task():
    chain = interop.interop_chain(NOW)
    request = interop.result_read_request()
    wrong_task = {
        "profile": "GM-MVP-1",
        "task_id": "task-other",
        "operation_id": "operation-interop-1",
    }
    valid_over_wrong_task = interop.result_read_proof(chain, wrong_task, NOW)
    _reject(
        _verifier(),
        chain,
        proof=valid_over_wrong_task,
        body=canonical_json_bytes(wrong_task),
    )
    valid_over_right_task = interop.result_read_proof(chain, request, NOW)
    _reject(
        _verifier(),
        chain,
        proof=valid_over_right_task,
        body=canonical_json_bytes(wrong_task),
    )


def test_result_read_rejects_deactivated_holder_key():
    registrations = interop.registered_identities()
    executor_key = (interop.TENANT, "agent-executor")
    registrations[executor_key] = dataclasses.replace(registrations[executor_key], active=False)
    documents = interop.did_documents()
    resolver = IdentityResolver(
        registrations,
        allowed_hosts=frozenset({"identity.agent-guard.test"}),
        fetch_document=lambda url: canonical_json_bytes(documents[url]),
    )
    chain = interop.interop_chain(NOW)
    request = interop.result_read_request()
    proof = interop.result_read_proof(chain, request, NOW)
    _reject(
        _verifier(resolver=resolver),
        chain,
        proof=proof,
        body=canonical_json_bytes(request),
    )
