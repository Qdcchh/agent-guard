"""Real B-authorization -> A1-ledger integration across the defined seam.

This is the interface that exists in ``origin/main`` today: B's AS issues root
and two delegated SM2 tokens, B's static verifier turns a signed tool request
into a trusted ``VerifiedInvocation``, and A's ``ExecutionLedger.accept`` makes
the locked, atomic budget decision. It is not the A-side HTTP gateway, tools,
downstream execution or evidence export -- those are not implemented yet, so
M1-M13 remain unproven as a whole.
"""

from __future__ import annotations

import json
import time

import psycopg
import pytest

from agent_guard.authorization.introspection import IntrospectionService
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.authorization.verifier import InvocationVerifier, VerificationError
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.contracts.ledger import (
    INVOKE_ENDPOINT,
    AcceptDisposition,
    ErrorCode,
    LedgerError,
    TrustedCost,
)
from agent_guard.ledger.provisioning import revoke_grant
from agent_guard.ledger.service import ExecutionLedger
from tests.fixtures.dbstate import fetch_counters, fetch_one
from tests.integration.test_exchange_service import (
    ISSUER,
    TENANT,
    _exchange,
    _form,
    _resolver,
    _root,
)

pytestmark = pytest.mark.integration

AS_KID = "as-sign-1"
AMOUNT_FEN = 70000
TOOLS = "procurement.order.create"


def _invocation_body(idempotency_key: str, *, quantity: int = 1) -> bytes:
    return canonical_json_bytes(
        {
            "profile": "GM-MVP-1",
            "task_id": "task-001",
            "tool_id": TOOLS,
            "tool_version": "1",
            "idempotency_key": idempotency_key,
            "params": {
                "request_id": "req-001",
                "quote_id": "quote-001",
                "quote_version": "1",
                "items": [{"sku": "sku-001", "quantity": quantity}],
                "delivery_id": "office-001",
            },
        }
    )


class Bridge:
    """B verifier output feeding A's ledger for one two-level delegation."""

    def __init__(self, dsn):
        self.as_key, self.keys, self.registrations, self.exchanges, self.root = _root(dsn)
        self.resolver = _resolver(self.registrations)
        first = _exchange(
            self.exchanges,
            self.keys,
            self.registrations,
            _form(self.as_key, self.root.access_token),
        )
        second = _exchange(
            self.exchanges,
            self.keys,
            self.registrations,
            _form(self.as_key, first.access_token, recipient="executor", ttl=100),
            holder="selector",
        )
        self.selector_token = first.access_token
        self.executor_token = second.access_token
        self.selector_grant = first.ag_grant_id
        self.executor_grant = second.ag_grant_id
        self.executor = self.registrations[(TENANT, "agent-executor")]
        self.staged: list[tuple[str, str, bytes]] = []
        self.verifier = InvocationVerifier(
            issuer=ISSUER,
            as_keys={AS_KID: self.as_key.public_key()},
            identities=self.resolver,
            stage_evidence=self._stage,
        )
        self.ledger = ExecutionLedger(dsn)

    def _stage(self, token: str, proof: str, body: bytes) -> str:
        self.staged.append((token, proof, body))
        return f"evidence-{len(self.staged)}"

    def verified(self, idempotency_key: str, *, quantity: int = 1, proof_key=None, now=None):
        body = _invocation_body(idempotency_key, quantity=quantity)
        now = now or int(time.time())
        proof = sign_ag_proof(
            proof_key if proof_key is not None else self.keys["executor"],
            kid=self.executor.kid,
            client_id="agent-executor",
            purpose="invoke",
            endpoint=INVOKE_ENDPOINT,
            body=json.loads(body),
            token=self.executor_token,
            now=now,
        )
        return self.verifier.verify_static(
            self.executor_token, proof, endpoint=INVOKE_ENDPOINT, method="POST", body=body, now=now
        )

    def accept(self, idempotency_key: str, *, cost_fen: int = AMOUNT_FEN, **kwargs):
        return self.ledger.accept(self.verified(idempotency_key, **kwargs), TrustedCost(cost_fen))


def test_two_level_delegation_executor_token_is_accepted_by_a1_ledger(ledger, dsn):
    bridge = Bridge(dsn)
    result = bridge.accept("purchase-001")
    assert result.disposition is AcceptDisposition.CREATED
    assert result.root_id == bridge.root.ag_grant_id
    assert result.grant_id == bridge.executor_grant
    assert fetch_one(dsn, "SELECT count(*) FROM ag_operations") == (1,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_ledger_events") == (1,)
    for grant_id in (bridge.root.ag_grant_id, bridge.selector_grant, bridge.executor_grant):
        counters = fetch_counters(dsn, grant_id)
        assert counters["amount_reserved"] == AMOUNT_FEN
        assert counters["calls_reserved"] == 1
    assert len(bridge.staged) == 1 and bridge.staged[0][0] == bridge.executor_token


def test_stolen_executor_token_without_holder_key_is_rejected_before_ledger(ledger, dsn):
    bridge = Bridge(dsn)
    with pytest.raises(VerificationError):
        bridge.verified("purchase-stolen", proof_key=bridge.keys["planner"])
    assert bridge.staged == []
    assert fetch_one(dsn, "SELECT count(*) FROM ag_operations") == (0,)


def test_tampered_params_are_rejected_before_ledger(ledger, dsn):
    bridge = Bridge(dsn)
    body = _invocation_body("purchase-tamper")
    now = int(time.time())
    proof = sign_ag_proof(
        bridge.keys["executor"],
        kid=bridge.executor.kid,
        client_id="agent-executor",
        purpose="invoke",
        endpoint=INVOKE_ENDPOINT,
        body=json.loads(body),
        token=bridge.executor_token,
        now=now,
    )
    tampered = body.replace(b'"quantity":1', b'"quantity":2')
    with pytest.raises(VerificationError):
        bridge.verifier.verify_static(
            bridge.executor_token,
            proof,
            endpoint=INVOKE_ENDPOINT,
            method="POST",
            body=tampered,
            now=now,
        )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_operations") == (0,)


def test_idempotent_retry_does_not_reserve_twice(ledger, dsn):
    bridge = Bridge(dsn)
    first = bridge.accept("purchase-002")
    retry = bridge.accept("purchase-002")
    assert retry.disposition is AcceptDisposition.EXISTING
    assert retry.operation_id == first.operation_id
    assert retry.cost.amount_fen == first.cost.amount_fen
    counters = fetch_counters(dsn, first.grant_id)
    assert counters["amount_reserved"] == AMOUNT_FEN
    assert fetch_one(dsn, "SELECT count(*) FROM ag_operations") == (1,)


def test_proof_replay_is_rejected_by_the_ledger(ledger, dsn):
    bridge = Bridge(dsn)
    replay = bridge.verified("purchase-003")
    bridge.ledger.accept(replay, TrustedCost(AMOUNT_FEN))
    with pytest.raises(LedgerError) as error:
        bridge.ledger.accept(replay, TrustedCost(AMOUNT_FEN))
    assert error.value.code is ErrorCode.REPLAY
    assert fetch_one(dsn, "SELECT count(*) FROM ag_operations") == (1,)


def test_revoked_ancestor_blocks_new_accept_and_idempotent_retry(ledger, dsn):
    bridge = Bridge(dsn)
    first = bridge.accept("purchase-004")
    with psycopg.connect(dsn) as conn:
        revoke_grant(conn, bridge.root.ag_grant_id)
    with pytest.raises(LedgerError) as new_operation:
        bridge.accept("purchase-005")
    assert new_operation.value.code is ErrorCode.REVOKED
    with pytest.raises(LedgerError) as retry:
        bridge.accept("purchase-004")
    assert retry.value.code is ErrorCode.REVOKED
    assert fetch_one(dsn, "SELECT count(*) FROM ag_operations") == (1,)
    counters = fetch_counters(dsn, first.grant_id)
    assert counters["amount_reserved"] == AMOUNT_FEN


def test_intermediate_ancestor_revocation_blocks_executor_accept(ledger, dsn):
    bridge = Bridge(dsn)
    selector_grant = fetch_one(
        dsn,
        "SELECT grant_id FROM ag_grants WHERE holder_client_id = 'agent-selector'",
    )[0]
    with psycopg.connect(dsn) as conn:
        revoke_grant(conn, selector_grant)
    with pytest.raises(LedgerError) as error:
        bridge.accept("purchase-006")
    assert error.value.code is ErrorCode.REVOKED


def test_introspection_active_is_not_an_execution_permit(ledger, dsn):
    bridge = Bridge(dsn)
    introspection = IntrospectionService(
        dsn,
        issuer=ISSUER,
        as_keys={AS_KID: bridge.as_key.public_key()},
        identities=bridge.resolver,
    )
    assert introspection.inspect(bridge.executor_token).active is True

    bridge.accept("purchase-007")
    # The token is still cryptographically valid and the grant active...
    assert introspection.inspect(bridge.executor_token).active is True
    # ...but the locked accept transaction must still reject the exhausted budget.
    with pytest.raises(LedgerError) as error:
        bridge.accept("purchase-008")
    assert error.value.code is ErrorCode.BUDGET_EXCEEDED

    with psycopg.connect(dsn) as conn:
        revoke_grant(conn, bridge.root.ag_grant_id)
    assert introspection.inspect(bridge.executor_token).active is False


def test_leaf_budget_below_requested_amount_is_rejected(ledger, dsn):
    bridge = Bridge(dsn)
    with pytest.raises(LedgerError) as error:
        bridge.accept("purchase-009", cost_fen=80000)
    assert error.value.code is ErrorCode.BUDGET_EXCEEDED
    assert fetch_one(dsn, "SELECT count(*) FROM ag_operations") == (0,)


def test_executor_audience_and_holder_are_bound_in_verified_context(ledger, dsn):
    bridge = Bridge(dsn)
    verified = bridge.verified("purchase-010")
    assert verified.holder_client_id == "agent-executor"
    assert verified.holder_kid == bridge.executor.kid
    assert verified.subject == "user-001"
    assert verified.tenant_id == TENANT
    assert verified.task_id == "task-001"
    assert verified.grant_id == bridge.executor_grant
    assert verified.root_id == bridge.root.ag_grant_id
    assert verified.tool_id == TOOLS
    assert verified.ancestor_ids is None
    assert verified.token_digest and verified.proof_digest and verified.intent_digest
