"""Deterministic B-side interop vectors for A/B conformance tests.

WARNING: the SM2 private keys below are synthetic TEST-ONLY material. They were
generated once and committed only so both sides can run reproducible
conformance vectors. They must never protect real data, be used in a
deployment, or be presented as production keys.

The module mints the exact GM-MVP-1 artifacts A's gateway must handle: a root
token and two narrowed child tokens for the planner -> selector -> executor
chain, an executor AG-Proof for one tool request, and an ``AG-EVIDENCE-1``
unanchored bundle over the same three-node path. Signatures are randomized by
design, so the frozen parts are the keys, SPKI bytes, canonical request bytes
and their SM3 digests.

A gateway test can import :func:`interop_chain`, :func:`resolver` and
:func:`evidence_bundle`, or copy the frozen digests as independent vectors.
"""

from __future__ import annotations

from dataclasses import dataclass

from tongsuopy.crypto import serialization

from agent_guard.authorization.claims import GATEWAY_AUDIENCE, SCOPES
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.authorization.verifier import InvocationVerifier
from agent_guard.contracts.encoding import JsonObject, b64url_encode, canonical_json_bytes
from agent_guard.contracts.ledger import INVOKE_ENDPOINT
from agent_guard.contracts.ledger_changes import canonical_ledger_changes_bytes
from agent_guard.crypto.sm import serialize_sm2_public_key, sign_compact_jws, sm3_b64url
from agent_guard.identity.resolver import (
    METHOD_TYPE,
    SPKI_PROPERTY,
    IdentityResolver,
    RegisteredIdentity,
)

TENANT = "tenant-demo"
TASK = "task-001"
SUBJECT = "user-demo-001"
ISSUER = "https://auth.agent-guard.test"
TOKEN_ENDPOINT = ISSUER + "/oauth/token"
REDIRECT = "https://console.agent-guard.test/oauth/callback"
AS_KID = "as-sign-1"
GATEWAY_RECEIPT_KID = "gateway-receipt-1"
ROOT_GRANT = "grant-root-interop"
SELECTOR_GRANT = "grant-selector-interop"
EXECUTOR_GRANT = "grant-executor-interop"


# TEST-ONLY, synthetic, never deploy.
def _pem(*lines: str) -> str:
    return "\n".join(("-----BEGIN PRIVATE KEY-----", *lines, "-----END PRIVATE KEY-----", ""))


AS_KEY_PEM = _pem(
    "MIGHAgEAMBMGByqGSM49AgEGCCqBHM9VAYItBG0wawIBAQQg1J/CTR/2HnLIg2U+",
    "1w+X+nNN5UW3vmAu5LlnykvDHXOhRANCAASo9f2cChKXO0XCEAD5oZcG1qfYfGDE",
    "tBUMDIhrx2PxahnZB4YFyMs7c4W7AelHkcvRHGkOHTk6IEFVn4zbht3A",
)
PLANNER_KEY_PEM = _pem(
    "MIGHAgEAMBMGByqGSM49AgEGCCqBHM9VAYItBG0wawIBAQQgObkVN1/1Myvf8f7j",
    "NnBKdrdU1zjb8sM8+uCblW8P00ShRANCAATW2bxfTurLpGslr8mQ6uAAMnNuES2o",
    "dE9Wv0qoD1wQYwkW7gP8isUnE/K9LyedHJTn++FADJ9CeLdbn6LeLe6d",
)
SELECTOR_KEY_PEM = _pem(
    "MIGHAgEAMBMGByqGSM49AgEGCCqBHM9VAYItBG0wawIBAQQgMoq7MCxLnA/Y/vEi",
    "iG2NYgGs+48ADnp0HH+UGEqhpXehRANCAAShORSzJlcX2t3aaGnmrLo4lnHY3LU1",
    "9m2v7+pOCUfCtDL73TTPrHs/+s1nBGhgYEsIR44ZMk6aNAbu7KTt8Tdx",
)
EXECUTOR_KEY_PEM = _pem(
    "MIGHAgEAMBMGByqGSM49AgEGCCqBHM9VAYItBG0wawIBAQQgJCYS+wdpNQhaUHOl",
    "ghHO40g9wJl4Gzlz8xT0ndZawnWhRANCAAQzQPT67shnRheJuM1A6JqjSdc0mL3g",
    "osctUceFCdb8RCW5Ukmb5pIyuIE3lfUm/L+UeU+yiSsMM9e5UDw3QpDX",
)
GATEWAY_RECEIPT_KEY_PEM = _pem(
    "MIGHAgEAMBMGByqGSM49AgEGCCqBHM9VAYItBG0wawIBAQQgJKG8HaJdOMwD/721",
    "hWeHUcvB4eAD4eH4QYDen9ks1jahRANCAAS1pd/rby4lORmTog0FGR1cKwzZPkap",
    "JMeE7mKdizTaRyykbDO8YlNq+ntF+LFdKr6uPbnKNoonwetr/rhGNUbb",
)

#: Frozen SPKI DER (canonical SubjectPublicKeyInfo) and its SM3 for each key.
SPKI_B64 = {
    "as": (
        "MFkwEwYHKoZIzj0CAQYIKoEcz1UBgi0DQgAEqPX9nAoSlztFwhAA-aGXBtan2HxgxLQV"
        "DAyIa8dj8WoZ2QeGBcjLO3OFuwHpR5HL0RxpDh05OiBBVZ-M24bdwA"
    ),
    "planner": (
        "MFkwEwYHKoZIzj0CAQYIKoEcz1UBgi0DQgAE1tm8X07qy6RrJa_JkOrgADJzbhEtqHRP"
        "Vr9KqA9cEGMJFu4D_IrFJxPyvS8nnRyU5_vhQAyfQni3W5-i3i3unQ"
    ),
    "selector": (
        "MFkwEwYHKoZIzj0CAQYIKoEcz1UBgi0DQgAEoTkUsyZXF9rd2mhp5qy6OJZx2Ny1NfZt"
        "r-_qTglHwrQy-900z6x7P_rNZwRoYGBLCEeOGTJOmjQG7uyk7fE3cQ"
    ),
    "executor": (
        "MFkwEwYHKoZIzj0CAQYIKoEcz1UBgi0DQgAEM0D0-u7IZ0YXibjNQOiao0nXNJi94KLH"
        "LVHHhQnW_EQluVJJm-aSMriBN5X1Jvy_lHlPsokrDDPXuVA8N0KQ1w"
    ),
    "gateway-receipt": (
        "MFkwEwYHKoZIzj0CAQYIKoEcz1UBgi0DQgAEtaXf628uJTkZk6INBRkdXCsM2T5GqSTH"
        "hO5inYs02kcspGwzvGJTavp7RfixXSq-rj25yjaKJ8Hra_64RjVG2w"
    ),
}
SPKI_SM3 = {
    "as": "uJFHBNgBs_Ld0ajRN1w6iy6l-rvOp7twmfsbsPxGstc",
    "planner": "0jQ4g5731kdBhKK-2OnG9E4XVOTpWVaplh49aDe-m2k",
    "selector": "A99pGriUuJIr1TB8oRADnQeAWb303E-mYRZsIRpWzZE",
    "executor": "qJO50kQHyP7cyipFcmhouNMsD4x1Muoe9Dh97aP9faY",
    "gateway-receipt": "MKgNmeMMYHl_ciTkpwLW0yMB5H0wiGi_gAyAVeLaXKI",
}
#: Frozen canonical request bytes digest for the default invocation request.
REQUEST_SM3 = "pSe4kdqnmt_6Un9iIwJqWFfXj1lSDrGYM6KDMQ4ydU4"
#: Frozen canonical constraints digest for the interop authorization.
CONSTRAINTS_SM3 = "9GT6oJb6GWggBwBSYcYGQ6CINanufOhTXH9tTgGQNeg"

CONSTRAINTS: JsonObject = {
    "request_ids": ["req-001"],
    "document_ids": ["doc-001"],
    "quote_versions": ["quote-001@1"],
    "skus": ["sku-001"],
    "max_quantity": 2,
    "delivery_ids": ["office-001"],
    "template_ids": [],
    "recipient_ids": [],
}


def _key(pem: str):
    return serialization.load_pem_private_key(pem.encode("ascii"), password=None)


def as_key():
    return _key(AS_KEY_PEM)


def gateway_receipt_key():
    return _key(GATEWAY_RECEIPT_KEY_PEM)


def agent_key(name: str):
    return _key(
        {"planner": PLANNER_KEY_PEM, "selector": SELECTOR_KEY_PEM, "executor": EXECUTOR_KEY_PEM}[
            name
        ]
    )


def agent_did(name: str) -> str:
    return f"did:web:identity.agent-guard.test:agents:{name}"


def agent_kid(name: str) -> str:
    return agent_did(name) + "#key-1"


def registered_identities() -> dict[tuple[str, str], RegisteredIdentity]:
    return {
        (TENANT, f"agent-{name}"): RegisteredIdentity(
            TENANT,
            f"agent-{name}",
            agent_did(name),
            agent_kid(name),
            serialize_sm2_public_key(agent_key(name).public_key()),
        )
        for name in ("planner", "selector", "executor")
    }


def did_documents() -> dict[str, dict]:
    documents = {}
    for name in ("planner", "selector", "executor"):
        kid = agent_kid(name)
        spki = serialize_sm2_public_key(agent_key(name).public_key())
        document = {
            "id": agent_did(name),
            "verificationMethod": [
                {
                    "id": kid,
                    "type": METHOD_TYPE,
                    "controller": agent_did(name),
                    SPKI_PROPERTY: b64url_encode(spki),
                }
            ],
            "authentication": [kid],
            "capabilityInvocation": [kid],
        }
        if name != "executor":
            document["capabilityDelegation"] = [kid]
        documents[f"https://identity.agent-guard.test/agents/{name}/did.json"] = document
    return documents


def resolver() -> IdentityResolver:
    documents = did_documents()
    return IdentityResolver(
        registered_identities(),
        allowed_hosts=frozenset({"identity.agent-guard.test"}),
        fetch_document=lambda url: canonical_json_bytes(documents[url]),
    )


def _constraints() -> JsonObject:
    return {
        name: list(value) if isinstance(value, list) else value
        for name, value in CONSTRAINTS.items()
    }


def root_claims(now: int) -> JsonObject:
    return {
        "iss": ISSUER,
        "sub": SUBJECT,
        "aud": GATEWAY_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + 300,
        "jti": f"token-root-{now}",
        "client_id": "agent-planner",
        "scope": " ".join(sorted(SCOPES - {"openid"})),
        "act": {"sub": agent_did("planner")},
        "ag_profile": "GM-MVP-1",
        "ag_tenant_id": TENANT,
        "ag_task_id": TASK,
        "ag_grant_id": ROOT_GRANT,
        "ag_parent_id": None,
        "ag_root_id": ROOT_GRANT,
        "ag_delegation_remaining": 2,
        "ag_limits": {"currency": "CNY", "amount_fen": 100000, "calls": 10},
        "ag_constraints": _constraints(),
        "ag_cnf": {"kid": agent_kid("planner"), "spki_sm3": SPKI_SM3["planner"]},
    }


def selector_claims(now: int) -> JsonObject:
    return {
        "iss": ISSUER,
        "sub": SUBJECT,
        "aud": GATEWAY_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + 180,
        "jti": f"token-selector-{now}",
        "client_id": "agent-selector",
        "scope": "procurement.order.create notification.template.send",
        "act": {"sub": agent_did("selector"), "act": {"sub": agent_did("planner")}},
        "ag_profile": "GM-MVP-1",
        "ag_tenant_id": TENANT,
        "ag_task_id": TASK,
        "ag_grant_id": SELECTOR_GRANT,
        "ag_parent_id": ROOT_GRANT,
        "ag_root_id": ROOT_GRANT,
        "ag_delegation_remaining": 1,
        "ag_limits": {"currency": "CNY", "amount_fen": 80000, "calls": 8},
        "ag_constraints": _constraints(),
        "ag_cnf": {"kid": agent_kid("selector"), "spki_sm3": SPKI_SM3["selector"]},
    }


def executor_claims(now: int) -> JsonObject:
    return {
        "iss": ISSUER,
        "sub": SUBJECT,
        "aud": GATEWAY_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + 100,
        "jti": f"token-executor-{now}",
        "client_id": "agent-executor",
        "scope": "procurement.order.create",
        "act": {
            "sub": agent_did("executor"),
            "act": {
                "sub": agent_did("selector"),
                "act": {"sub": agent_did("planner")},
            },
        },
        "ag_profile": "GM-MVP-1",
        "ag_tenant_id": TENANT,
        "ag_task_id": TASK,
        "ag_grant_id": EXECUTOR_GRANT,
        "ag_parent_id": SELECTOR_GRANT,
        "ag_root_id": ROOT_GRANT,
        "ag_delegation_remaining": 0,
        "ag_limits": {"currency": "CNY", "amount_fen": 70000, "calls": 5},
        "ag_constraints": _constraints(),
        "ag_cnf": {"kid": agent_kid("executor"), "spki_sm3": SPKI_SM3["executor"]},
    }


def invocation_request(idempotency_key: str = "purchase-interop-001") -> JsonObject:
    return {
        "profile": "GM-MVP-1",
        "task_id": TASK,
        "tool_id": "procurement.order.create",
        "tool_version": "1",
        "idempotency_key": idempotency_key,
        "params": {
            "request_id": "req-001",
            "quote_id": "quote-001",
            "quote_version": "1",
            "items": [{"sku": "sku-001", "quantity": 1}],
            "delivery_id": "office-001",
        },
    }


@dataclass(frozen=True)
class InteropChain:
    now: int
    root_token: str
    root_claims: JsonObject
    selector_token: str
    selector_claims: JsonObject
    executor_token: str
    executor_claims: JsonObject


def interop_chain(now: int) -> InteropChain:
    """Mint the fixed planner -> selector -> executor chain for ``now``."""
    as_private = as_key()
    root = root_claims(now)
    selector = selector_claims(now)
    executor = executor_claims(now)
    return InteropChain(
        now=now,
        root_token=sign_compact_jws(as_private, root, key_id=AS_KID, token_type="ag-at+jwt"),
        root_claims=root,
        selector_token=sign_compact_jws(
            as_private, selector, key_id=AS_KID, token_type="ag-at+jwt"
        ),
        selector_claims=selector,
        executor_token=sign_compact_jws(
            as_private, executor, key_id=AS_KID, token_type="ag-at+jwt"
        ),
        executor_claims=executor,
    )


def invocation_proof(chain: InteropChain, request: JsonObject, now: int) -> str:
    return sign_ag_proof(
        agent_key("executor"),
        kid=agent_kid("executor"),
        client_id="agent-executor",
        purpose="invoke",
        endpoint=INVOKE_ENDPOINT,
        body=request,
        token=chain.executor_token,
        now=now,
    )


def result_read_request(operation_id: str = "operation-interop-1") -> JsonObject:
    return {"profile": "GM-MVP-1", "task_id": TASK, "operation_id": operation_id}


def result_read_proof(chain: InteropChain, request: JsonObject, now: int) -> str:
    from agent_guard.contracts.ledger import QUERY_ENDPOINT

    return sign_ag_proof(
        agent_key("executor"),
        kid=agent_kid("executor"),
        client_id="agent-executor",
        purpose="result-read",
        endpoint=QUERY_ENDPOINT,
        body=request,
        token=chain.executor_token,
        now=now,
    )


def verifier() -> InvocationVerifier:
    return InvocationVerifier(
        issuer=ISSUER,
        as_keys={AS_KID: as_key().public_key()},
        identities=resolver(),
        stage_evidence=lambda token, proof, body: "evidence-interop-1",
    )


def _node(grant_id: str, *, reserve: int, settled: int, calls_reserve: int, calls_settled: int):
    return {
        "grant_id": grant_id,
        "amount_reserved_delta": reserve,
        "amount_settled_delta": settled,
        "calls_reserved_delta": calls_reserve,
        "calls_settled_delta": calls_settled,
    }


def evidence_bundle(now: int, *, status: str = "SUCCEEDED"):
    """Build one AG-EVIDENCE-1 bundle and its independent ReceiptTrust."""
    from agent_guard.evidence.receipt import ReceiptTrust

    chain = interop_chain(now)
    request = invocation_request()
    proof = invocation_proof(chain, request, now)
    result = {"order_id": "synthetic-order-001"} if status == "SUCCEEDED" else {"error": "DECLINED"}
    amounts = (ROOT_GRANT, SELECTOR_GRANT, EXECUTOR_GRANT)
    ledger = {
        "operation_id": "operation-interop-1",
        "events": [
            {
                "phase": "RESERVE",
                "nodes": [
                    _node(grant_id, reserve=70000, settled=0, calls_reserve=1, calls_settled=0)
                    for grant_id in amounts
                ],
            },
            {
                "phase": "SETTLE" if status == "SUCCEEDED" else "RELEASE",
                "nodes": [
                    _node(
                        grant_id,
                        reserve=-70000,
                        settled=70000 if status == "SUCCEEDED" else 0,
                        calls_reserve=-1,
                        calls_settled=1 if status == "SUCCEEDED" else 0,
                    )
                    for grant_id in amounts
                ],
            },
        ],
    }
    receipt = {
        "profile": "GM-MVP-1",
        "receipt_id": "receipt-interop-1",
        "operation_id": "operation-interop-1",
        "tenant_id": TENANT,
        "task_id": TASK,
        "root_grant_id": ROOT_GRANT,
        "grant_id": EXECUTOR_GRANT,
        "token_sm3": sm3_b64url(chain.executor_token.encode("ascii")),
        "proof_sm3": sm3_b64url(proof.encode("ascii")),
        "intent_sm3": sm3_b64url(canonical_json_bytes(request)),
        "tool_id": "procurement.order.create",
        "tool_version": "1",
        "status": status,
        "amount_fen": 70000 if status == "SUCCEEDED" else 0,
        "result_sm3": sm3_b64url(canonical_json_bytes(result)),
        "ledger_sm3": sm3_b64url(canonical_ledger_changes_bytes(ledger)),
        "iat": now + 10,
    }
    bundle = {
        "manifest_version": "AG-EVIDENCE-1",
        "anchoring_status": "UNANCHORED",
        "receipt_jws": sign_compact_jws(
            gateway_receipt_key(),
            receipt,
            key_id=GATEWAY_RECEIPT_KID,
            token_type="ag-receipt+jwt",
        ),
        "ancestor_tokens": [chain.root_token, chain.selector_token, chain.executor_token],
        "token_jws": chain.executor_token,
        "proof_jws": proof,
        "request": request,
        "result": result,
        "ledger_changes": ledger,
    }
    registrations = registered_identities()
    trust = ReceiptTrust(
        issuer=ISSUER,
        as_keys={AS_KID: as_key().public_key()},
        gateway_keys={GATEWAY_RECEIPT_KID: gateway_receipt_key().public_key()},
        holder_keys={
            agent_kid(name): agent_key(name).public_key()
            for name in ("planner", "selector", "executor")
        },
        historical_registrations={
            agent_kid(name): registrations[(TENANT, f"agent-{name}")]
            for name in ("planner", "selector", "executor")
        },
    )
    return bundle, trust
