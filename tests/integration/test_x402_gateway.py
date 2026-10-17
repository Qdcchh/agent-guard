"""X6: real x402 loop over real PostgreSQL, real Anvil and real FROST signing.

No mock parts anywhere in the payment path: the gateway PG is the real test
database, the chain is a real local Anvil with the real FiatToken V2.2
bytecode, the payer signature is a real EIP-712/EIP-3009 signature, the
resource server speaks real HTTP, and settlement is a real EVM transaction
confirmed through its Transfer event.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from agent_guard.authorization.grant_revocation_service import GrantRevocationService
from agent_guard.authorization.provisioning import grant_tenant_admin
from agent_guard.contracts.execution import ExecutionError
from agent_guard.execution.service import ExecutionService
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.threshold.verifier import ThresholdApprovalVerifier
from agent_guard.x402 import state, wire
from agent_guard.x402.chain import AUTHORIZATION_USED_TOPIC, ChainConfirmation, ChainReader
from agent_guard.x402.client import X402HttpClient
from agent_guard.x402.config import X402Deployment
from agent_guard.x402.contracts import PaymentOffer, build_intent
from agent_guard.x402.facilitator import LocalFacilitator
from agent_guard.x402.gate import PaymentGatedDownstream
from agent_guard.x402.localchain import AnvilService, bootstrap_token
from agent_guard.x402.resource import X402ResourceServer
from agent_guard.x402.signer import X402Payer, create_nonce
from tests.fixtures.execution import DOWNSTREAM_SECRET, build_catalog
from tests.fixtures.gateway import app_for, raw_material, request
from tests.fixtures.threshold import RustThresholdSigner, approval_action
from tests.integration.test_verified_execution import signed_env

OFFER_AMOUNT = "250000"
BUDGET_LIMIT = "100000000"
APPROVAL_LIFETIME = 900
TENANT = "tenant-001"
TASK = "task-001"

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Chain:
    """Module-scoped real local EVM with the real token and one payer."""

    service: AnvilService
    rpc_url: str
    chain_id: int
    admin_key: str
    payer: X402Payer
    payer_key: str
    merchant: str
    token: str


@dataclass
class X402Env:
    chain: Chain
    dsn: str
    downstream_dsn: str
    env: object
    signer: RustThresholdSigner
    policy: object
    verifier: ThresholdApprovalVerifier
    deployment: X402Deployment
    reader: ChainReader
    facilitator: LocalFacilitator
    gate: PaymentGatedDownstream
    server: X402ResourceServer
    service: ExecutionService
    client: X402HttpClient
    app: object


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def chain():
    service = AnvilService()
    service.start()
    payer_key = "0x" + secrets.token_bytes(32).hex()
    payer = X402Payer(payer_key)
    admin_key = "0x" + secrets.token_bytes(32).hex()
    merchant = "0x" + secrets.token_bytes(20).hex()
    token = bootstrap_token(
        rpc_url=service.rpc_url,
        admin_key=admin_key,
        payer_address=payer.address,
        token_name="USD Coin",
        token_symbol="USDC",
        decimals=6,
        mint_amount=10_000_000,
    ).lower()
    yield Chain(
        service=service,
        rpc_url=service.rpc_url,
        chain_id=31337,
        admin_key=admin_key,
        payer=payer,
        payer_key=payer_key,
        merchant=merchant,
        token=token,
    )
    service.stop()


def _deployment(
    chain: Chain, dsn: str, *, port: int, offer_amount: str = OFFER_AMOUNT, token: str | None = None
):
    return X402Deployment(
        gateway_dsn=dsn,
        rpc_url=chain.rpc_url,
        chain_id=chain.chain_id,
        token=(token or chain.token).lower(),
        asset_name="USD Coin",
        asset_version="2",
        pay_to=chain.merchant,
        resource_url=f"http://127.0.0.1:{port}/v1/x402/resource/order-create",
        status_url=f"http://127.0.0.1:{port}/v1/x402/resource/order-status",
        offer=PaymentOffer(quote_id="quote-001", quote_version="1", asset_amount=offer_amount),
        max_timeout_seconds=3600,
        payer_key=chain.payer_key,
        facilitator_key=chain.admin_key,
    )


@pytest.fixture()
def x402_env(ledger, dsn, downstream_dsn, tmp_path, chain):
    env = signed_env(dsn, downstream_dsn)
    signer = RustThresholdSigner(tmp_path / "frostdemo")
    policy = ThresholdApprovalPolicyForTests(signer.enroll())
    verifier = ThresholdApprovalVerifier(policy=policy)
    port = _free_port()
    deployment = _deployment(chain, dsn, port=port)
    reader = ChainReader(chain.rpc_url, chain_id=chain.chain_id, token_address=chain.token.lower())
    facilitator = LocalFacilitator(
        rpc_url=chain.rpc_url,
        private_key=chain.admin_key,
        network=deployment.profile.network,
        confirmation_timeout_seconds=30.0,
    )
    client = X402HttpClient(resource_url=deployment.resource_url, timeout_seconds=15)
    gate = PaymentGatedDownstream(
        deployment=deployment,
        downstream=env.downstream,
        downstream_secret=DOWNSTREAM_SECRET,
        client=client,
        payer=chain.payer,
        reader=reader,
    )
    service = ExecutionService(
        gateway_dsn=dsn,
        ledger=ExecutionLedger(dsn),
        catalog=build_catalog(TENANT, TASK),
        downstream=gate,
        downstream_secret=DOWNSTREAM_SECRET,
    )
    server = X402ResourceServer(
        deployment=deployment,
        facilitator=facilitator,
        reader=reader,
        downstream=env.downstream,
        downstream_secret=DOWNSTREAM_SECRET,
    )
    app = app_for(env, dsn, threshold_verifier=verifier, payment=deployment)
    state.seed_asset_budget(
        dsn,
        tenant_id=TENANT,
        task_id=TASK,
        asset=chain.token.lower(),
        chain_id=chain.chain_id,
        amount_limit=BUDGET_LIMIT,
    )
    server.__enter__()
    try:
        yield X402Env(
            chain=chain,
            dsn=dsn,
            downstream_dsn=downstream_dsn,
            env=env,
            signer=signer,
            policy=policy,
            verifier=verifier,
            deployment=deployment,
            reader=reader,
            facilitator=facilitator,
            gate=gate,
            server=server,
            service=service,
            client=client,
            app=app,
        )
    finally:
        server.stop()
        app._executor.shutdown()


def ThresholdApprovalPolicyForTests(public_key_hex: str):
    from agent_guard.threshold.contracts import ThresholdApprovalPolicy

    return ThresholdApprovalPolicy(
        group_public_key=bytes.fromhex(public_key_hex),
        policy_version=3,
        key_epoch=5,
        max_lifetime_seconds=3600,
    )


def accept_paid(
    x: X402Env,
    *,
    key: str,
    deployment: X402Deployment | None = None,
    app=None,
    expires_at: int | None = None,
    delay_before_send: float = 0.0,
    bundle=None,
    **overrides,
):
    """Real FROST V3 approval through the real gateway HTTP accept route.

    Nothing here walks around the gateway: the acceptance (and therefore the
    payment policy) is enforced by ``GatewayEndpoint`` inside the ASGI app.
    """
    if bundle is None:
        bundle = x.env.bundle(key)
    dep = deployment or x.deployment
    invocation = bundle.invocation
    if expires_at is None:
        expires_at = int(time.time()) + APPROVAL_LIFETIME
    intent = build_intent(
        profile=dep.profile,
        tenant_id=invocation.tenant_id,
        task_id=invocation.task_id,
        grant_id=invocation.grant_id,
        root_grant_id=invocation.root_id,
        tool_id=invocation.tool_id,
        idempotency_key=invocation.idempotency_key,
        quote_id="quote-001",
        quote_version="1",
        amount_fen=70_000,
        valid_before=expires_at,
    )
    action_kwargs = dict(
        action_id=f"action-{key}",
        policy_version=x.policy.policy_version,
        key_epoch=x.policy.key_epoch,
        expires_at=expires_at,
        version=3,
        payment_digest=intent.digest,
    )
    action_kwargs.update(overrides)
    action = approval_action(bundle, **action_kwargs)
    header = x.signer.header_for(action, x.signer.sign(action))
    token, proof, body = raw_material(x.dsn, bundle)
    target_app = app if app is not None else x.app
    if delay_before_send > 0:
        time.sleep(delay_before_send)
    status, accepted, _headers = request(
        target_app,
        path="/v1/invocations",
        body=body,
        headers=[
            (b"content-type", b"application/json"),
            (b"authorization", b"AGPoP " + token),
            (b"ag-proof", proof),
            (b"ag-approval", header),
        ],
    )
    if status == 500:
        # Debug seam: re-drive the endpoint directly so the real exception is
        # visible instead of the public INTERNAL_ERROR envelope.
        target_app._endpoint.handle(
            "/v1/invocations", token.decode(), proof.decode(), body, approval=header
        )
    return bundle, intent, header, status, accepted


def _payment_row(dsn: str, operation_id: str):
    with psycopg.connect(dsn) as conn:
        return conn.execute(
            "SELECT status, nonce, payload_sha256, tx_hash, failure_code "
            "FROM ag_payment_states WHERE operation_id=%s",
            (operation_id,),
        ).fetchone()


def _operation_status(dsn: str, operation_id: str):
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT status FROM ag_operations WHERE operation_id=%s", (operation_id,)
        ).fetchone()
    return None if row is None else row[0]


def _operation_count(x: X402Env) -> int:
    with psycopg.connect(x.dsn) as conn:
        return conn.execute(
            "SELECT count(*) FROM ag_operations WHERE tenant_id=%s AND task_id=%s",
            (TENANT, TASK),
        ).fetchone()[0]


def _intent_count(x: X402Env) -> int:
    with psycopg.connect(x.dsn) as conn:
        return conn.execute(
            "SELECT count(*) FROM ag_payment_intents WHERE tenant_id=%s AND task_id=%s",
            (TENANT, TASK),
        ).fetchone()[0]


def _budget_for(x: X402Env, token: str):
    with psycopg.connect(x.dsn) as conn:
        return conn.execute(
            "SELECT amount_reserved, amount_settled FROM ag_payment_budgets "
            "WHERE tenant_id=%s AND task_id=%s AND asset=%s AND chain_id=%s",
            (TENANT, TASK, token.lower(), x.chain.chain_id),
        ).fetchone()


def _budget(x: X402Env):
    return _budget_for(x, x.chain.token)


def _cny_counters(x: X402Env):
    with psycopg.connect(x.dsn) as conn:
        return conn.execute(
            "SELECT amount_reserved, amount_settled, calls_reserved, calls_settled "
            "FROM ag_grants WHERE tenant_id=%s AND task_id=%s ORDER BY depth",
            (TENANT, TASK),
        ).fetchall()


def _order_count(dsn: str) -> int:
    with psycopg.connect(dsn) as conn:
        return conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0]


def _authorization_events(
    x: X402Env,
    payer: str,
    nonce: str,
    *,
    reader: ChainReader | None = None,
    token: str | None = None,
) -> int:
    r = reader or x.reader
    topic_payer = "0x" + payer.lower().removeprefix("0x").rjust(64, "0")
    logs = r.web3.eth.get_logs(
        {
            "address": r.web3.to_checksum_address(token or x.chain.token),
            "fromBlock": 0,
            "toBlock": "latest",
            "topics": [AUTHORIZATION_USED_TOPIC, topic_payer, nonce],
        }
    )
    return len(logs)


def _confirm_settled(x: X402Env, record, *, reader: ChainReader | None = None) -> None:
    r = reader or x.reader
    deadline = time.time() + 30
    confirmation = None
    while time.time() < deadline:
        confirmation = r.confirm(
            payer=x.chain.payer.lower_address,
            pay_to=x.chain.merchant,
            amount=OFFER_AMOUNT,
            nonce=record.nonce,
        )
        if confirmation.settled:
            break
        time.sleep(0.5)
    assert confirmation is not None and confirmation.settled, confirmation
    assert confirmation.transfer_matched


def test_paid_order_settles_on_chain_once_and_resumes(x402_env):
    x = x402_env
    before_reserved, before_settled = _budget(x)

    _bundle, _intent, _header, status, accepted = accept_paid(x, key="paid-1")
    assert status == 202, accepted
    operation_id = accepted["operation_id"]
    assert accepted["status"] == "RESERVED"

    assert _operation_status(x.dsn, operation_id) == "RESERVED"
    pending = _payment_row(x.dsn, operation_id)
    assert pending[0] == "UNPAID" and pending[1] is None and pending[2] is None
    reserved, settled = _budget(x)
    assert reserved == before_reserved + Decimal(OFFER_AMOUNT)
    assert settled == before_settled

    run = x.service.run_operation(operation_id)
    assert run.status == "SUCCEEDED", run

    record = state.load_payment(x.dsn, operation_id)
    assert record.status.value == "SETTLED"
    assert record.nonce and record.tx_hash
    _confirm_settled(x, record)
    assert _authorization_events(x, x.chain.payer.lower_address, record.nonce) == 1
    assert _order_count(x.downstream_dsn) == 1

    reserved, settled = _budget(x)
    assert settled == before_settled + Decimal(OFFER_AMOUNT)
    assert reserved == before_reserved
    assert x.reader.balance_of(x.chain.merchant) == int(OFFER_AMOUNT)

    # A resumed worker refuses to re-run a terminal operation: the durable
    # record is read back unchanged and stays single-authorization.
    assert _operation_status(x.dsn, operation_id) == "SUCCEEDED"
    assert _authorization_events(x, x.chain.payer.lower_address, record.nonce) == 1
    assert _order_count(x.downstream_dsn) == 1

    # A replayed PAYMENT-SIGNATURE is answered from durable state, never
    # re-verified or transferred again.
    material = state.load_authorization_material(x.dsn, operation_id)
    assert material is not None
    _authorization, payload, _sha = material
    response = x.client.order_create(
        operation_id=operation_id, payment_header=wire.encode_header(payload)
    )
    assert response.status == 200
    assert b'"already_existed":true' in response.body.replace(b" ", b"")
    assert _authorization_events(x, x.chain.payer.lower_address, record.nonce) == 1
    assert _order_count(x.downstream_dsn) == 1


def test_accept_refuses_v2_approval_without_payment_digest(x402_env):
    """A V2 approval can never opt out of the paid-tool V3 digest obligation."""
    x = x402_env
    before_ops = _operation_count(x)
    before_intents = _intent_count(x)
    before_orders = _order_count(x.downstream_dsn)
    before_budget = _budget(x)

    _b, _i, _h, status, accepted = accept_paid(x, key="v2-1", version=2)
    assert status == 401, accepted
    assert accepted["error"]["code"] == "APPROVAL_REQUIRED", accepted

    assert _operation_count(x) == before_ops
    assert _intent_count(x) == before_intents
    assert _order_count(x.downstream_dsn) == before_orders
    assert _budget(x) == before_budget


def test_accept_refuses_wrong_payment_digest_and_rolls_back(x402_env):
    """An approval over a different payment digest rolls the whole accept back."""
    x = x402_env
    before_ops = _operation_count(x)
    before_intents = _intent_count(x)
    before_orders = _order_count(x.downstream_dsn)
    before_budget = _budget(x)

    _b, _i, _h, status, accepted = accept_paid(x, key="wrong-digest-1", payment_digest="0" * 64)
    assert status == 409, accepted
    assert accepted["error"]["code"] == "APPROVAL_MISMATCH", accepted

    assert _operation_count(x) == before_ops
    assert _intent_count(x) == before_intents
    assert _order_count(x.downstream_dsn) == before_orders
    assert _budget(x) == before_budget


def test_accept_refuses_over_budget_offer_without_burning_budget(x402_env):
    """An offer above the independent asset budget is refused in-transaction."""
    x = x402_env
    over = replace(
        x.deployment,
        offer=PaymentOffer(
            quote_id="quote-001",
            quote_version="1",
            asset_amount=str(int(BUDGET_LIMIT) + 1),
        ),
    )
    over_app = app_for(x.env, x.dsn, threshold_verifier=x.verifier, payment=over)
    try:
        before_ops = _operation_count(x)
        before_intents = _intent_count(x)
        before_orders = _order_count(x.downstream_dsn)
        before_budget = _budget(x)

        _b, _i, _h, status, accepted = accept_paid(
            x, key="over-budget-1", deployment=over, app=over_app
        )
        assert status == 422, accepted
        assert accepted["error"]["code"] == "PAYMENT_BUDGET_EXCEEDED", accepted

        assert _operation_count(x) == before_ops
        assert _intent_count(x) == before_intents
        assert _order_count(x.downstream_dsn) == before_orders
        assert _budget(x) == before_budget
    finally:
        over_app._executor.shutdown()


def test_unknown_authorization_recovers_after_server_restart(x402_env):
    """A persisted authorization survives an unreachable server: the retry
    reconciles, reuses the same nonce and settles exactly once."""
    x = x402_env
    before_reserved, before_settled = _budget(x)
    before_orders = _order_count(x.downstream_dsn)

    _b, _i, _h, status, accepted = accept_paid(x, key="recovery-1")
    assert status == 202, accepted
    operation_id = accepted["operation_id"]
    reserved, settled = _budget(x)
    assert reserved == before_reserved + Decimal(OFFER_AMOUNT)
    assert settled == before_settled

    # Crash window: the real authorization was persisted before any network
    # call and the server is unreachable when the worker first runs.
    x.server.stop()
    record = state.load_payment(x.dsn, operation_id)
    signed = x.chain.payer.create_payload(
        profile=x.deployment.profile, intent=record.intent, nonce=create_nonce()
    )
    state.authorize(
        x.dsn,
        operation_id=operation_id,
        nonce=signed["nonce"],
        authorization_json=json.dumps(
            signed["authorization"], ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8"),
        payload_json=signed["document"],
        payload_sha256=signed["payload_sha256"],
    )

    first = x.service.run_operation(operation_id, owner_token="worker-recovery-1")
    assert first.status == "UNKNOWN", first
    unknown = _payment_row(x.dsn, operation_id)
    assert unknown[0] == "UNKNOWN", unknown
    assert unknown[1] == signed["nonce"]
    assert _operation_status(x.dsn, operation_id) == "UNKNOWN"
    reserved, settled = _budget(x)
    assert reserved == before_reserved + Decimal(OFFER_AMOUNT)
    assert settled == before_settled
    assert _authorization_events(x, x.chain.payer.lower_address, signed["nonce"]) == 0
    assert _order_count(x.downstream_dsn) == before_orders

    # Recovery: the idempotent retry sends the persisted payload, never a new
    # authorization, and the chain confirms exactly one transfer.
    x.server.__enter__()
    second = x.service.run_operation(operation_id, owner_token="worker-recovery-1")
    assert second.status == "SUCCEEDED", second

    settled_record = state.load_payment(x.dsn, operation_id)
    assert settled_record.status.value == "SETTLED"
    assert settled_record.nonce == signed["nonce"]
    _confirm_settled(x, settled_record)
    assert _authorization_events(x, x.chain.payer.lower_address, signed["nonce"]) == 1
    assert _order_count(x.downstream_dsn) == before_orders + 1
    assert _operation_status(x.dsn, operation_id) == "SUCCEEDED"
    reserved, settled = _budget(x)
    assert reserved == before_reserved
    assert settled == before_settled + Decimal(OFFER_AMOUNT)


def test_lost_response_after_real_settlement_recovers_without_new_transfer(x402_env):
    """The real payment settles and the real order exists; only the worker
    never hears about it. Recovery reads the durable records back."""
    x = x402_env
    before_reserved, before_settled = _budget(x)
    before_orders = _order_count(x.downstream_dsn)

    _b, _i, _h, status, accepted = accept_paid(x, key="lost-response-1")
    assert status == 202, accepted
    operation_id = accepted["operation_id"]

    real_gate = x.gate

    class LoseResponse:
        """Run the real flow to completion; lose only its result."""

        def execute(self, **kwargs):
            real_gate.execute(**kwargs)
            raise ConnectionError("synthetic response loss after real settlement")

        def query(self, **kwargs):
            return real_gate.query(**kwargs)

    x.service._downstream = LoseResponse()
    try:
        first = x.service.run_operation(operation_id, owner_token="worker-lost-1")
    finally:
        x.service._downstream = real_gate
    assert first.status == "UNKNOWN", first

    # The independent effects are already durable and on chain.
    settled_row = _payment_row(x.dsn, operation_id)
    assert settled_row[0] == "SETTLED" and settled_row[3], settled_row
    assert _order_count(x.downstream_dsn) == before_orders + 1
    record = state.load_payment(x.dsn, operation_id)
    assert record.nonce and record.tx_hash
    _confirm_settled(x, record)
    assert _authorization_events(x, x.chain.payer.lower_address, record.nonce) == 1
    reserved, settled = _budget(x)
    assert reserved == before_reserved
    assert settled == before_settled + Decimal(OFFER_AMOUNT)

    # The resumed worker recovers the same durable outcome with no new
    # transfer, no new order and no re-signed authorization.
    second = x.service.run_operation(operation_id, owner_token="worker-lost-1")
    assert second.status == "SUCCEEDED", second
    recovered = state.load_payment(x.dsn, operation_id)
    assert recovered.nonce == record.nonce and recovered.tx_hash == record.tx_hash
    assert _operation_status(x.dsn, operation_id) == "SUCCEEDED"
    assert _order_count(x.downstream_dsn) == before_orders + 1
    assert _authorization_events(x, x.chain.payer.lower_address, record.nonce) == 1
    reserved, settled = _budget(x)
    assert reserved == before_reserved
    assert settled == before_settled + Decimal(OFFER_AMOUNT)


def test_direct_http_tampering_is_refused_without_side_effects(x402_env):
    """Direct probes against the real HTTP resource server change nothing."""
    x = x402_env
    before_orders = _order_count(x.downstream_dsn)

    _b, _i, _h, status, accepted = accept_paid(x, key="tamper-1")
    assert status == 202, accepted
    operation_id = accepted["operation_id"]
    accepted_budget = _budget(x)
    record = state.load_payment(x.dsn, operation_id)
    attacker = X402Payer("0x" + secrets.token_bytes(32).hex())

    # 1. A signed payment for an operation that persisted nothing is refused.
    forged = attacker.create_payload(
        profile=x.deployment.profile, intent=record.intent, nonce=create_nonce()
    )
    probe = x.client.order_create(
        operation_id=operation_id, payment_header=wire.encode_header(forged["document"])
    )
    assert probe.status == 409, probe
    assert b"PAYMENT_NOT_PERSISTED" in probe.body

    # 2. The real authorization is persisted first.
    real = x.chain.payer.create_payload(
        profile=x.deployment.profile, intent=record.intent, nonce=create_nonce()
    )
    state.authorize(
        x.dsn,
        operation_id=operation_id,
        nonce=real["nonce"],
        authorization_json=json.dumps(
            real["authorization"], ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8"),
        payload_json=real["document"],
        payload_sha256=real["payload_sha256"],
    )

    # 3. A malformed header gets a fresh 402 challenge, nothing else.
    malformed = x.client.order_create(operation_id=operation_id, payment_header=b"%%%%%%%%")
    assert malformed.status == 402, malformed
    assert malformed.header("PAYMENT-REQUIRED") is not None

    # 4. A different payload for the same nonce is refused on material
    #    mismatch, never verified.
    tampered = attacker.create_payload(
        profile=x.deployment.profile, intent=record.intent, nonce=real["nonce"]
    )
    mismatch = x.client.order_create(
        operation_id=operation_id,
        payment_header=wire.encode_header(tampered["document"]),
    )
    assert mismatch.status == 409, mismatch
    assert b"PAYMENT_MATERIAL_MISMATCH" in mismatch.body

    # Every probe left the durable state and the independent budget untouched.
    assert _payment_row(x.dsn, operation_id) == (
        "AUTHORIZED",
        real["nonce"],
        real["payload_sha256"],
        None,
        None,
    )
    assert _order_count(x.downstream_dsn) == before_orders
    assert _budget(x) == accepted_budget

    # The genuine persisted payload still settles exactly once.
    run = x.service.run_operation(operation_id)
    assert run.status == "SUCCEEDED", run
    settled_row = _payment_row(x.dsn, operation_id)
    assert settled_row[0] == "SETTLED" and settled_row[1] == real["nonce"]
    assert _order_count(x.downstream_dsn) == before_orders + 1
    assert _authorization_events(x, x.chain.payer.lower_address, real["nonce"]) == 1
    reserved, settled = _budget(x)
    assert reserved == accepted_budget[0] - Decimal(OFFER_AMOUNT)
    assert settled == accepted_budget[1] + Decimal(OFFER_AMOUNT)


def _try_run(x: X402Env, operation_id: str, owner_token: str) -> str:
    try:
        return x.service.run_operation(operation_id, owner_token=owner_token).status
    except ExecutionError as exc:
        return f"ERROR_{exc.code.value}"


_RECOVERY_SCRIPT = r"""
import json
import os

from agent_guard.execution.service import ExecutionService
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.tools.downstream import MockDownstream
from agent_guard.x402.chain import ChainReader
from agent_guard.x402.client import X402HttpClient
from agent_guard.x402.config import X402Deployment
from agent_guard.x402.contracts import PaymentOffer
from agent_guard.x402.gate import PaymentGatedDownstream
from agent_guard.x402.signer import X402Payer
from tests.fixtures.execution import DOWNSTREAM_SECRET, build_catalog

cfg = json.loads(os.environ["AG_X402_RECOVERY_JSON"])
deployment = X402Deployment(
    gateway_dsn=cfg["dsn"],
    rpc_url=cfg["rpc_url"],
    chain_id=cfg["chain_id"],
    token=cfg["token"],
    asset_name="USD Coin",
    asset_version="2",
    pay_to=cfg["merchant"],
    resource_url=cfg["resource_url"],
    status_url=cfg["status_url"],
    offer=PaymentOffer(
        quote_id="quote-001", quote_version="1", asset_amount=cfg["offer_amount"]
    ),
    max_timeout_seconds=3600,
    payer_key=cfg["payer_key"],
    facilitator_key=cfg["facilitator_key"],
)
reader = ChainReader(
    cfg["rpc_url"], chain_id=cfg["chain_id"], token_address=cfg["token"]
)
downstream = MockDownstream(
    cfg["downstream_dsn"],
    service_secret=DOWNSTREAM_SECRET,
    approved_suppliers={"supplier-001"},
    approved_recipients={"user-demo-001"},
    served_requests={"req-001"},
)
gate = PaymentGatedDownstream(
    deployment=deployment,
    downstream=downstream,
    downstream_secret=DOWNSTREAM_SECRET,
    client=X402HttpClient(resource_url=deployment.resource_url, timeout_seconds=15),
    payer=X402Payer(cfg["payer_key"]),
    reader=reader,
)
service = ExecutionService(
    gateway_dsn=cfg["dsn"],
    ledger=ExecutionLedger(cfg["dsn"]),
    catalog=build_catalog(cfg["tenant_id"], cfg["task_id"]),
    downstream=gate,
    downstream_secret=DOWNSTREAM_SECRET,
)
result = service.run_operation(cfg["operation_id"], owner_token=cfg["owner_token"])
print(json.dumps({"status": result.status}))
"""


def test_unknown_payment_recovers_in_independent_process(x402_env):
    """X4: the UNKNOWN recovery is done by a brand-new Python process that
    only sees the preserved real PG rows and the preserved real chain."""
    x = x402_env
    before_reserved, before_settled = _budget(x)
    before_orders = _order_count(x.downstream_dsn)
    before_balance = x.reader.balance_of(x.chain.merchant)

    _b, _i, _h, status, accepted = accept_paid(x, key="proc-recovery-1")
    assert status == 202, accepted
    operation_id = accepted["operation_id"]

    # Crash window: real authorization persisted, server unreachable.
    x.server.stop()
    record = state.load_payment(x.dsn, operation_id)
    signed = x.chain.payer.create_payload(
        profile=x.deployment.profile, intent=record.intent, nonce=create_nonce()
    )
    state.authorize(
        x.dsn,
        operation_id=operation_id,
        nonce=signed["nonce"],
        authorization_json=json.dumps(
            signed["authorization"], ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8"),
        payload_json=signed["document"],
        payload_sha256=signed["payload_sha256"],
    )
    first = x.service.run_operation(operation_id, owner_token="worker-proc-1")
    assert first.status == "UNKNOWN", first
    assert _operation_status(x.dsn, operation_id) == "UNKNOWN"

    # The server comes back; the recovery itself runs outside this process.
    x.server.__enter__()

    env = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
        if key in os.environ
    }
    env["PYTHONPATH"] = os.pathsep.join(
        part
        for part in (str(REPO_ROOT / "src"), str(REPO_ROOT), os.environ.get("PYTHONPATH", ""))
        if part
    )
    env["AG_X402_RECOVERY_JSON"] = json.dumps(
        {
            "dsn": x.dsn,
            "downstream_dsn": x.downstream_dsn,
            "operation_id": operation_id,
            "owner_token": "worker-proc-1",
            "rpc_url": x.chain.rpc_url,
            "chain_id": x.chain.chain_id,
            "token": x.chain.token,
            "merchant": x.chain.merchant,
            "payer_key": x.chain.payer_key,
            "facilitator_key": x.chain.admin_key,
            "resource_url": x.deployment.resource_url,
            "status_url": x.deployment.status_url,
            "tenant_id": TENANT,
            "task_id": TASK,
            "offer_amount": OFFER_AMOUNT,
        }
    )
    finished = subprocess.run(
        [sys.executable, "-c", _RECOVERY_SCRIPT],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert finished.returncode == 0, finished.stderr[-2000:]
    lines = [line for line in finished.stdout.splitlines() if line.startswith("{")]
    assert lines, finished.stdout
    assert json.loads(lines[-1]) == {"status": "SUCCEEDED"}, finished.stdout

    settled_record = state.load_payment(x.dsn, operation_id)
    assert settled_record.status.value == "SETTLED"
    assert settled_record.nonce == signed["nonce"]
    _confirm_settled(x, settled_record)
    assert _authorization_events(x, x.chain.payer.lower_address, signed["nonce"]) == 1
    assert _order_count(x.downstream_dsn) == before_orders + 1
    assert _operation_status(x.dsn, operation_id) == "SUCCEEDED"
    reserved, settled = _budget(x)
    assert reserved == before_reserved
    assert settled == before_settled + Decimal(OFFER_AMOUNT)
    assert x.reader.balance_of(x.chain.merchant) == before_balance + int(OFFER_AMOUNT)


def test_concurrent_runs_settle_exactly_once(x402_env):
    """X6: two workers race on the same accepted operation. Whatever the
    losers do, the real chain, the real order store and both budgets see a
    single payment."""
    x = x402_env
    before_reserved, before_settled = _budget(x)
    before_orders = _order_count(x.downstream_dsn)
    before_balance = x.reader.balance_of(x.chain.merchant)

    _b, _i, _h, status, accepted = accept_paid(x, key="concurrent-1")
    assert status == 202, accepted
    operation_id = accepted["operation_id"]

    outcomes: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker(token: str) -> None:
        barrier.wait()
        try:
            outcome = x.service.run_operation(operation_id, owner_token=token).status
        except ExecutionError as exc:
            outcome = f"ERROR_{exc.code.value}"
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=worker, args=(f"race-{position}",)) for position in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not any(thread.is_alive() for thread in threads), outcomes
    assert len(outcomes) == 2, outcomes
    assert outcomes.count("SUCCEEDED") >= 1, outcomes
    assert set(outcomes) <= {
        "SUCCEEDED",
        "ERROR_LEASE_LOST",
        "ERROR_ILLEGAL_TRANSITION",
    }, outcomes

    record = state.load_payment(x.dsn, operation_id)
    assert record.status.value == "SETTLED"
    assert record.nonce and record.tx_hash
    _confirm_settled(x, record)
    assert _authorization_events(x, x.chain.payer.lower_address, record.nonce) == 1
    assert _order_count(x.downstream_dsn) == before_orders + 1
    assert _operation_status(x.dsn, operation_id) == "SUCCEEDED"
    reserved, settled = _budget(x)
    assert reserved == before_reserved
    assert settled == before_settled + Decimal(OFFER_AMOUNT)
    assert x.reader.balance_of(x.chain.merchant) == before_balance + int(OFFER_AMOUNT)
    assert _cny_counters(x) == [(0, 70_000, 0, 1)] * 3


def test_ancestor_revocation_blocks_payment_without_side_effects(x402_env):
    """X6: after a real subtree revocation the paid tool cannot even be
    accepted again; nothing moves in the ledger or on chain."""
    x = x402_env
    _b, _i, _h, status, accepted = accept_paid(x, key="revoked-1")
    assert status == 202, accepted

    with psycopg.connect(x.dsn) as conn:
        mid = conn.execute(
            "SELECT grant_id FROM ag_grants WHERE depth=1 AND tenant_id=%s AND task_id=%s",
            (TENANT, TASK),
        ).fetchone()[0]
        grant_tenant_admin(conn, tenant_id=TENANT, subject="admin-revoke")
    GrantRevocationService(x.dsn).revoke_grant(
        tenant_id=TENANT,
        grant_id=mid,
        authenticated_admin_subject="admin-revoke",
    )

    before_ops = _operation_count(x)
    before_intents = _intent_count(x)
    before_orders = _order_count(x.downstream_dsn)
    before_budget = _budget(x)
    before_counters = _cny_counters(x)
    before_balance = x.reader.balance_of(x.chain.merchant)

    _b2, _i2, _h2, refused_status, refused = accept_paid(x, key="revoked-2")
    assert refused_status == 403, refused
    assert refused["error"]["code"] == "REVOKED", refused

    assert _operation_count(x) == before_ops
    assert _intent_count(x) == before_intents
    assert _order_count(x.downstream_dsn) == before_orders
    assert _budget(x) == before_budget
    assert _cny_counters(x) == before_counters
    assert x.reader.balance_of(x.chain.merchant) == before_balance


def test_expired_approval_is_refused_at_accept(x402_env):
    """X4: an approval that was signed in time but expires before the accept
    transaction can never create an operation."""
    x = x402_env
    before_ops = _operation_count(x)
    before_intents = _intent_count(x)
    before_budget = _budget(x)
    before_counters = _cny_counters(x)

    expires_at = int(time.time()) + 2
    _b, _i, _h, status, refused = accept_paid(
        x,
        key="expired-approval-1",
        expires_at=expires_at,
        delay_before_send=max(0.0, expires_at - time.time() + 1.5),
    )
    assert status == 403, refused
    assert refused["error"]["code"] == "EXPIRED", refused

    assert _operation_count(x) == before_ops
    assert _intent_count(x) == before_intents
    assert _order_count(x.downstream_dsn) == 0
    assert _budget(x) == before_budget
    assert _cny_counters(x) == before_counters


def test_expired_authorization_never_settles_or_recovers(x402_env):
    """X4: an authorization whose real validity window has passed cannot be
    settled and cannot be recovered into a payment by a retry."""
    x = x402_env
    before_reserved, before_settled = _budget(x)
    before_orders = _order_count(x.downstream_dsn)
    before_balance = x.reader.balance_of(x.chain.merchant)

    expires_at = int(time.time()) + 6
    _b, _i, _h, status, accepted = accept_paid(x, key="expired-auth-1", expires_at=expires_at)
    assert status == 202, accepted
    operation_id = accepted["operation_id"]

    # Let the real EIP-3009 validity window close before the worker runs.
    time.sleep(max(0.0, expires_at - time.time() + 1.5))

    first = _try_run(x, operation_id, "worker-expired-1")
    assert first != "SUCCEEDED", first

    nonce = _payment_row(x.dsn, operation_id)[1]
    assert nonce
    assert _authorization_events(x, x.chain.payer.lower_address, nonce) == 0
    assert _order_count(x.downstream_dsn) in (before_orders, before_orders + 1)
    assert x.reader.balance_of(x.chain.merchant) == before_balance
    reserved, settled = _budget(x)
    assert settled == before_settled
    assert reserved in (before_reserved, before_reserved + Decimal(OFFER_AMOUNT))
    assert all(row[1] == 0 and row[3] == 0 for row in _cny_counters(x)), _cny_counters(x)

    # The retry sees the preserved rows only; the expired window is closed for
    # good, so no fresh authorization and no transfer can appear.
    second = _try_run(x, operation_id, "worker-expired-1")
    assert second != "SUCCEEDED", second
    assert _authorization_events(x, x.chain.payer.lower_address, nonce) == 0
    assert x.reader.balance_of(x.chain.merchant) == before_balance
    assert _budget(x)[1] == before_settled
    row = _payment_row(x.dsn, operation_id)
    assert row is not None and row[0] != "SETTLED", row
    assert all(row[1] == 0 and row[3] == 0 for row in _cny_counters(x)), _cny_counters(x)


# ---------------------------------------------------------------------------
# R1 blocker regressions: fail-closed refusal, strict confirmation, no double
# reservation. The clock-moving regressions (expired-unused release and
# settled-before-deadline) run after every clock-independent test; the
# concurrent tight-budget regression runs last and owns its own asset budget.
# ---------------------------------------------------------------------------


def test_repeat_accept_never_reserves_asset_budget_twice(x402_env, monkeypatch):
    """R1-03: replaying the same approved action must not reserve the
    independent asset budget a second time, before or after settlement."""
    x = x402_env
    before_reserved, before_settled = _budget(x)
    expires_at = int(time.time()) + 600
    _b, _i, _h, status, first = accept_paid(x, key="reserve-once", expires_at=expires_at)
    assert status == 202, first
    operation_id = first["operation_id"]
    accepted_budget = _budget(x)
    assert accepted_budget[0] == before_reserved + Decimal(OFFER_AMOUNT)
    assert accepted_budget[1] == before_settled

    # Replay the exact signed action bytes instead of a fresh signature.
    signature = bytes.fromhex(
        json.loads((x.signer.directory / "sig-action-reserve-once.json").read_text())
    )
    monkeypatch.setattr(x.signer, "sign", lambda action: signature)

    _b2, _i2, _h2, status, second = accept_paid(x, key="reserve-once", expires_at=expires_at)
    assert status == 202, second
    assert second["operation_id"] == operation_id
    assert second["status"] == "RESERVED"
    assert _budget(x) == accepted_budget
    assert _operation_count(x) == 1
    assert _intent_count(x) == 1
    assert _cny_counters(x) == [(70_000, 0, 1, 0)] * 3
    assert _order_count(x.downstream_dsn) == 0

    run = x.service.run_operation(operation_id)
    assert run.status == "SUCCEEDED", run
    record = state.load_payment(x.dsn, operation_id)
    assert record.status.value == "SETTLED"
    _confirm_settled(x, record)
    settled_budget = _budget(x)
    assert settled_budget == (
        accepted_budget[0] - Decimal(OFFER_AMOUNT),
        accepted_budget[1] + Decimal(OFFER_AMOUNT),
    )

    # The same retry after settlement still finds the one settled payment.
    _b3, _i3, _h3, status, third = accept_paid(x, key="reserve-once", expires_at=expires_at)
    assert status == 202, third
    assert third["operation_id"] == operation_id
    assert third["status"] == "SUCCEEDED"
    assert _budget(x) == settled_budget
    assert _operation_count(x) == 1
    assert _intent_count(x) == 1
    assert _authorization_events(x, x.chain.payer.lower_address, record.nonce) == 1
    assert _order_count(x.downstream_dsn) == 1
    assert _cny_counters(x) == [(0, 70_000, 0, 1)] * 3


def test_candidate_transaction_cannot_confirm_foreign_or_unused_nonce(x402_env, monkeypatch):
    """R1-02: a settlement hash is only a lookup hint. Confirmation needs the
    nonce's own AuthorizationUsed event and the exact Transfer in the receipt."""
    x = x402_env
    before_reserved, before_settled = _budget(x)
    before_balance = x.reader.balance_of(x.chain.merchant)

    _b, _i, _h, status, accepted = accept_paid(x, key="nonce-bind-a")
    assert status == 202, accepted
    operation_id = accepted["operation_id"]
    assert x.service.run_operation(operation_id).status == "SUCCEEDED"
    record = state.load_payment(x.dsn, operation_id)
    assert record.tx_hash and record.nonce
    _confirm_settled(x, record)

    # The nonce's own candidate does confirm, with the exact transfer.
    own = x.reader.confirm(
        payer=x.chain.payer.lower_address,
        pay_to=x.chain.merchant,
        amount=OFFER_AMOUNT,
        nonce=record.nonce,
        candidate_tx=record.tx_hash,
    )
    assert own.settled and own.transfer_matched and own.authorization_used

    # The very same real receipt must never confirm a nonce it does not carry.
    unused = create_nonce()
    ghost = x.reader.confirm(
        payer=x.chain.payer.lower_address,
        pay_to=x.chain.merchant,
        amount=OFFER_AMOUNT,
        nonce=unused,
        candidate_tx=record.tx_hash,
    )
    assert not ghost.settled, ghost
    assert ghost.receipt_status == 1
    assert not ghost.authorization_used and not ghost.nonce_consumed
    assert ghost.reason == "candidate transaction does not carry this authorization"
    assert x.reader.authorization_state(payer=x.chain.payer.lower_address, nonce=unused) is False

    # Without any candidate the unused nonce also stays unsettled.
    empty = x.reader.confirm(
        payer=x.chain.payer.lower_address,
        pay_to=x.chain.merchant,
        amount=OFFER_AMOUNT,
        nonce=unused,
    )
    assert not empty.settled and not empty.authorization_used and not empty.nonce_consumed
    assert empty.reason == "no authorization event found"

    # A failed nonce-bound lookup never falls back to the candidate hash.
    monkeypatch.setattr(x.reader, "authorization_used_hashes", lambda **kwargs: (False, ()))
    unavailable = x.reader.confirm(
        payer=x.chain.payer.lower_address,
        pay_to=x.chain.merchant,
        amount=OFFER_AMOUNT,
        nonce=record.nonce,
        candidate_tx=record.tx_hash,
    )
    assert not unavailable.settled, unavailable
    assert unavailable.reason == "authorization event lookup is unavailable"

    # A reader bound to another chain never settles either.
    wrong_chain = ChainReader(
        x.chain.rpc_url, chain_id=x.chain.chain_id + 1, token_address=x.chain.token
    )
    mismatched = wrong_chain.confirm(
        payer=x.chain.payer.lower_address,
        pay_to=x.chain.merchant,
        amount=OFFER_AMOUNT,
        nonce=record.nonce,
        candidate_tx=record.tx_hash,
    )
    assert not mismatched.settled, mismatched
    assert "chain" in mismatched.reason

    reserved, settled = _budget(x)
    assert reserved == before_reserved
    assert settled == before_settled + Decimal(OFFER_AMOUNT)
    assert x.reader.balance_of(x.chain.merchant) == before_balance + int(OFFER_AMOUNT)
    assert _cny_counters(x) == [(0, 70_000, 0, 1)] * 3


def test_transient_verifier_outage_keeps_reservation_and_recovers(x402_env, monkeypatch):
    """R1-01: a transient verifier outage is UNKNOWN, never a release; the
    persisted live authorization still settles exactly once on recovery."""
    x = x402_env
    _b, _i, _h, status, accepted = accept_paid(x, key="transient-1")
    assert status == 202, accepted
    operation_id = accepted["operation_id"]
    accepted_budget = _budget(x)
    before_orders = _order_count(x.downstream_dsn)
    before_balance = x.reader.balance_of(x.chain.merchant)

    real_verify = x.facilitator.verify
    monkeypatch.setattr(
        x.facilitator,
        "verify",
        lambda **kwargs: {
            "is_valid": False,
            "invalid_reason": "FACILITATOR_UNAVAILABLE",
            "payer": None,
        },
    )
    first = x.service.run_operation(operation_id, owner_token="worker-transient-1")
    assert first.status == "UNKNOWN", first
    row = _payment_row(x.dsn, operation_id)
    assert row[0] == "UNKNOWN", row
    assert row[4] == "PAYMENT_HTTP_503", row
    assert row[1] is not None
    assert _budget(x) == accepted_budget
    assert _authorization_events(x, x.chain.payer.lower_address, row[1]) == 0
    assert _order_count(x.downstream_dsn) == before_orders
    assert x.reader.balance_of(x.chain.merchant) == before_balance

    # The verifier recovers and the persisted payload is still payable.
    monkeypatch.setattr(x.facilitator, "verify", real_verify)
    material = state.load_authorization_material(x.dsn, operation_id)
    assert material is not None
    replay = x.client.order_create(
        operation_id=operation_id, payment_header=wire.encode_header(material[1])
    )
    assert replay.status == 200, replay
    assert _authorization_events(x, x.chain.payer.lower_address, row[1]) == 1
    assert _order_count(x.downstream_dsn) == before_orders + 1
    assert x.reader.balance_of(x.chain.merchant) == before_balance + int(OFFER_AMOUNT)

    # The worker reconciles the durable outcome without a second transfer.
    second = x.service.run_operation(operation_id, owner_token="worker-transient-1")
    assert second.status == "SUCCEEDED", second
    record = state.load_payment(x.dsn, operation_id)
    assert record.status.value == "SETTLED"
    assert record.nonce == row[1]
    _confirm_settled(x, record)
    assert _authorization_events(x, x.chain.payer.lower_address, record.nonce) == 1
    assert _order_count(x.downstream_dsn) == before_orders + 1
    reserved, settled = _budget(x)
    assert reserved == accepted_budget[0] - Decimal(OFFER_AMOUNT)
    assert settled == accepted_budget[1] + Decimal(OFFER_AMOUNT)
    assert _cny_counters(x) == [(0, 70_000, 0, 1)] * 3


def test_expired_live_authorization_releases_only_when_chain_proves_it(x402_env):
    """R1-01: the reservation is released only once the configured chain's own
    time has passed the signed validBefore deadline; a raw replay is refused."""
    x = x402_env
    before_reserved, before_settled = _budget(x)
    before_orders = _order_count(x.downstream_dsn)
    before_balance = x.reader.balance_of(x.chain.merchant)

    expires_at = int(time.time()) + 15
    _b, _i, _h, status, accepted = accept_paid(x, key="expired-release-1", expires_at=expires_at)
    assert status == 202, accepted
    operation_id = accepted["operation_id"]

    # Move the real chain's own clock past the signed validity window.
    x.reader.web3.provider.make_request("anvil_setNextBlockTimestamp", [expires_at + 1])
    x.reader.web3.provider.make_request("anvil_mine", [])
    head = x.reader.latest_block_timestamp()
    assert head is not None and head >= expires_at

    first = x.service.run_operation(operation_id)
    assert first.status == "UNKNOWN", first
    row = _payment_row(x.dsn, operation_id)
    assert row[0] == "FAILED", row
    assert row[4] is not None and row[4].startswith("PAYMENT_REFUSED_"), row
    assert row[1] is not None and row[3] is None, row
    assert _operation_status(x.dsn, operation_id) == "UNKNOWN"
    reserved, settled = _budget(x)
    assert reserved == before_reserved
    assert settled == before_settled
    assert _authorization_events(x, x.chain.payer.lower_address, row[1]) == 0
    assert _order_count(x.downstream_dsn) == before_orders
    assert x.reader.balance_of(x.chain.merchant) == before_balance
    assert _cny_counters(x) == [(70_000, 0, 1, 0)] * 3

    # A raw replay of the released payload must never reopen the payment.
    material = state.load_authorization_material(x.dsn, operation_id)
    assert material is not None
    replay = x.client.order_create(
        operation_id=operation_id, payment_header=wire.encode_header(material[1])
    )
    assert replay.status == 409, replay
    assert b"PAYMENT_FAILED" in replay.body
    assert _budget(x) == (before_reserved, before_settled)
    assert _order_count(x.downstream_dsn) == before_orders


def test_settled_before_deadline_never_released_by_lost_lookup_after_expiry(x402_env, monkeypatch):
    """R1-01 (final): expiry alone proves only that no *future* settlement can
    happen, never the absence of a past one. A payment that really settled
    before the deadline stays reserved while the nonce-bound lookup is
    unavailable after it, and the same payload recovers exactly once."""
    x = x402_env
    before_reserved, before_settled = _budget(x)
    before_orders = _order_count(x.downstream_dsn)
    before_balance = x.reader.balance_of(x.chain.merchant)

    head = x.reader.latest_block_timestamp()
    expires_at = max(int(time.time()), head or 0) + 30
    _b, _i, _h, status, accepted = accept_paid(x, key="settled-expiry-1", expires_at=expires_at)
    assert status == 202, accepted
    operation_id = accepted["operation_id"]
    accepted_budget = _budget(x)
    assert accepted_budget[0] == before_reserved + Decimal(OFFER_AMOUNT)

    # The real server settles and really creates the order; only the gateway's
    # own confirmation is lost, so its durable record must stay UNKNOWN.
    real_reader = x.gate._reader

    class LostConfirmation:
        """Delegate every real read; lose only the settlement confirmation."""

        def __getattr__(self, name):
            return getattr(real_reader, name)

        def confirm(self, **kwargs):
            return ChainConfirmation(
                settled=False,
                tx_hash=kwargs.get("candidate_tx"),
                receipt_status=None,
                authorization_used=False,
                transfer_matched=False,
                nonce_consumed=False,
                reason="synthetic confirmation loss",
            )

    x.gate._reader = LostConfirmation()
    try:
        first = x.service.run_operation(operation_id, owner_token="worker-settled-expiry-1")
    finally:
        x.gate._reader = real_reader
    assert first.status == "UNKNOWN", first
    row = _payment_row(x.dsn, operation_id)
    assert row[0] == "UNKNOWN", row
    assert row[4] == "SETTLEMENT_UNCONFIRMED", row
    assert row[1] is not None and row[3] is None, row
    nonce = row[1]
    assert _operation_status(x.dsn, operation_id) == "UNKNOWN"
    # The payment really settled before the deadline and the order exists.
    assert _authorization_events(x, x.chain.payer.lower_address, nonce) == 1
    assert _order_count(x.downstream_dsn) == before_orders + 1
    assert x.reader.balance_of(x.chain.merchant) == before_balance + int(OFFER_AMOUNT)
    assert _budget(x) == accepted_budget
    assert _cny_counters(x) == [(70_000, 0, 1, 0)] * 3

    # Move the configured chain's own clock past the signed deadline.
    x.reader.web3.provider.make_request("anvil_setNextBlockTimestamp", [expires_at + 1])
    x.reader.web3.provider.make_request("anvil_mine", [])
    head = x.reader.latest_block_timestamp()
    assert head is not None and head >= expires_at

    # The retry cannot see the nonce-bound event (lookup unavailable) and the
    # verifier refuses the now-expired payload: the refusal branch must keep
    # the reservation because the token still says the nonce was consumed.
    with monkeypatch.context() as patched:
        patched.setattr(x.reader, "authorization_used_hashes", lambda **kwargs: (False, ()))
        retry = x.service.run_operation(operation_id, owner_token="worker-settled-expiry-1")
    assert retry.status == "UNKNOWN", retry
    row = _payment_row(x.dsn, operation_id)
    assert row[0] == "UNKNOWN", row
    assert row[4] == "PAYMENT_HTTP_402", row
    assert row[1] == nonce, row
    assert _operation_status(x.dsn, operation_id) == "UNKNOWN"
    assert _budget(x) == accepted_budget
    assert _authorization_events(x, x.chain.payer.lower_address, nonce) == 1
    assert _order_count(x.downstream_dsn) == before_orders + 1
    assert x.reader.balance_of(x.chain.merchant) == before_balance + int(OFFER_AMOUNT)
    assert _cny_counters(x) == [(70_000, 0, 1, 0)] * 3

    # An unreadable token state is equally not a release.
    with monkeypatch.context() as patched:
        patched.setattr(x.reader, "authorization_used_hashes", lambda **kwargs: (False, ()))
        patched.setattr(x.reader, "authorization_state", lambda **kwargs: None)
        again = x.service.run_operation(operation_id, owner_token="worker-settled-expiry-1")
    assert again.status == "UNKNOWN", again
    row = _payment_row(x.dsn, operation_id)
    assert row[0] == "UNKNOWN", row
    assert row[4] == "PAYMENT_HTTP_402", row
    assert _budget(x) == accepted_budget
    assert _operation_status(x.dsn, operation_id) == "UNKNOWN"

    # The restored reader recovers the one real settled payment from the same
    # persisted payload: no second transfer, no second order, no release.
    third = x.service.run_operation(operation_id, owner_token="worker-settled-expiry-1")
    assert third.status == "SUCCEEDED", third
    record = state.load_payment(x.dsn, operation_id)
    assert record.status.value == "SETTLED"
    assert record.nonce == nonce
    _confirm_settled(x, record)
    assert _authorization_events(x, x.chain.payer.lower_address, nonce) == 1
    assert _order_count(x.downstream_dsn) == before_orders + 1
    reserved, settled = _budget(x)
    assert reserved == before_reserved
    assert settled == before_settled + Decimal(OFFER_AMOUNT)
    assert _cny_counters(x) == [(0, 70_000, 0, 1)] * 3
    assert x.reader.balance_of(x.chain.merchant) == before_balance + int(OFFER_AMOUNT)


def test_concurrent_fresh_accepts_under_tight_budget_reserve_once(x402_env, monkeypatch):
    """R1-03: two concurrent fresh AGPoP acceptances of the same approved
    action race while the asset budget has room for exactly one reservation.
    One operation, one intent and one reservation exist before and after the
    real settlement; the loser answers from the existing operation."""
    x = x402_env
    before_orders = _order_count(x.downstream_dsn)
    shared_budget_before = _budget(x)

    # Budget limits are immutable by design, so the race gets its own real
    # FiatToken V2.2 asset identity seeded with room for exactly one
    # reservation instead of rewriting shared budget state.
    token = bootstrap_token(
        rpc_url=x.chain.rpc_url,
        admin_key=x.chain.admin_key,
        payer_address=x.chain.payer.address,
        token_name="USD Coin",
        token_symbol="USDC",
        decimals=6,
        mint_amount=1_000_000,
    ).lower()
    deployment = _deployment(x.chain, x.dsn, port=_free_port(), token=token)
    reader = ChainReader(x.chain.rpc_url, chain_id=x.chain.chain_id, token_address=token)
    client = X402HttpClient(resource_url=deployment.resource_url, timeout_seconds=15)
    gate = PaymentGatedDownstream(
        deployment=deployment,
        downstream=x.env.downstream,
        downstream_secret=DOWNSTREAM_SECRET,
        client=client,
        payer=x.chain.payer,
        reader=reader,
    )
    service = ExecutionService(
        gateway_dsn=x.dsn,
        ledger=ExecutionLedger(x.dsn),
        catalog=build_catalog(TENANT, TASK),
        downstream=gate,
        downstream_secret=DOWNSTREAM_SECRET,
    )
    server = X402ResourceServer(
        deployment=deployment,
        facilitator=x.facilitator,
        reader=reader,
        downstream=x.env.downstream,
        downstream_secret=DOWNSTREAM_SECRET,
    )
    app = app_for(x.env, x.dsn, threshold_verifier=x.verifier, payment=deployment)
    state.seed_asset_budget(
        x.dsn,
        tenant_id=TENANT,
        task_id=TASK,
        asset=token,
        chain_id=x.chain.chain_id,
        amount_limit=OFFER_AMOUNT,
    )
    server.__enter__()
    try:
        assert _budget_for(x, token) == (Decimal(0), Decimal(0))
        assert reader.balance_of(x.chain.merchant) == 0

        key = "concurrent-accept-1"
        expires_at = int(time.time()) + 600

        # The Rust fixture writes one signature per action id and refuses a
        # second one, so the same real FROST approval is replayed (like T1)
        # while each racing request carries its own fresh AGPoP proof.
        signed: list[bytes] = []
        sign_lock = threading.Lock()
        real_sign = x.signer.sign

        def sign_once(action):
            with sign_lock:
                if not signed:
                    signed.append(real_sign(action))
                return signed[0]

        monkeypatch.setattr(x.signer, "sign", sign_once)

        outcomes: list[tuple[int, dict]] = []
        outcomes_lock = threading.Lock()

        def race() -> list[tuple[int, dict]]:
            outcomes.clear()
            bundles = (x.env.bundle(key), x.env.bundle(key))
            barrier = threading.Barrier(2)

            def worker(bundle) -> None:
                barrier.wait()
                try:
                    _b, _i, _h, status, accepted = accept_paid(
                        x,
                        key=key,
                        bundle=bundle,
                        deployment=deployment,
                        app=app,
                        expires_at=expires_at,
                    )
                    result = (status, accepted)
                except Exception as exc:  # noqa: BLE001 - surfaced in the assertions
                    result = (0, {"exception": repr(exc)})
                with outcomes_lock:
                    outcomes.append(result)

            threads = [threading.Thread(target=worker, args=(bundle,)) for bundle in bundles]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=120)
            assert not any(thread.is_alive() for thread in threads), outcomes
            assert len(outcomes) == 2, outcomes
            return list(outcomes)

        first_race = race()
        assert [status for status, _ in first_race] == [202, 202], first_race
        operation_ids = {accepted["operation_id"] for _, accepted in first_race}
        assert len(operation_ids) == 1, first_race
        operation_id = operation_ids.pop()
        assert {accepted["status"] for _, accepted in first_race} == {"RESERVED"}, first_race

        assert _operation_count(x) == 1
        assert _intent_count(x) == 1
        assert _budget_for(x, token) == (Decimal(OFFER_AMOUNT), Decimal(0))
        assert _cny_counters(x) == [(70_000, 0, 1, 0)] * 3
        assert _order_count(x.downstream_dsn) == before_orders
        assert reader.balance_of(x.chain.merchant) == 0

        run = service.run_operation(operation_id, owner_token="worker-concurrent-accept-1")
        assert run.status == "SUCCEEDED", run
        record = state.load_payment(x.dsn, operation_id)
        assert record.status.value == "SETTLED"
        _confirm_settled(x, record, reader=reader)
        assert (
            _authorization_events(
                x, x.chain.payer.lower_address, record.nonce, reader=reader, token=token
            )
            == 1
        )
        assert _order_count(x.downstream_dsn) == before_orders + 1
        assert reader.balance_of(x.chain.merchant) == int(OFFER_AMOUNT)
        settled_budget = (Decimal(0), Decimal(OFFER_AMOUNT))
        assert _budget_for(x, token) == settled_budget
        assert _cny_counters(x) == [(0, 70_000, 0, 1)] * 3

        second_race = race()
        assert [status for status, _ in second_race] == [202, 202], second_race
        assert {accepted["operation_id"] for _, accepted in second_race} == {operation_id}
        assert {accepted["status"] for _, accepted in second_race} == {"SUCCEEDED"}, second_race
        assert _budget_for(x, token) == settled_budget
        assert _operation_count(x) == 1
        assert _intent_count(x) == 1
        assert (
            _authorization_events(
                x, x.chain.payer.lower_address, record.nonce, reader=reader, token=token
            )
            == 1
        )
        assert _order_count(x.downstream_dsn) == before_orders + 1
        assert _cny_counters(x) == [(0, 70_000, 0, 1)] * 3
        assert _budget(x) == shared_budget_before
    finally:
        server.stop()
        app._executor.shutdown()
