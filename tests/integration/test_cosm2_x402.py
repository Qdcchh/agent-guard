"""B8 genuine local-chain settlement with COSM2 payment intent and B9 effects."""

import psycopg
import pytest

from agent_guard.cosign.authz_domain import CosignRefused
from agent_guard.x402.chain import ChainReader
from agent_guard.x402.facilitator import LocalFacilitator
from tests.integration.test_x402_gateway import chain as chain_fixture
from tools.x402_gateway_demo import (
    OFFER_AMOUNT,
    CaseWorld,
    case_paid,
)

chain = chain_fixture
pytestmark = pytest.mark.integration


@pytest.fixture()
def world(chain, namespace, tmp_path):
    reader = ChainReader(chain.rpc_url, chain_id=chain.chain_id, token_address=chain.token)
    facilitator = LocalFacilitator(
        rpc_url=chain.rpc_url,
        private_key=chain.admin_key,
        network=f"eip155:{chain.chain_id}",
        confirmation_timeout_seconds=30.0,
    )
    value = CaseWorld(
        chain=chain,
        reader=reader,
        facilitator=facilitator,
        base_dsn=namespace.base_dsn,
        private_root=tmp_path,
        label="sm2-payment",
        quote_id="quote-001",
        offer_amount=OFFER_AMOUNT,
        payer_address=chain.payer.address,
        approval_scheme="sm2-2p",
    )
    try:
        value.server.__enter__()
        yield value
    finally:
        assert value.close() == []


def test_cosm2_paid_once_and_tampered_digest_zero_effect(world):
    cases = []
    case_paid(world, cases)
    assert len(cases) == 2 and all(case["passed"] for case in cases)
    assert len(world.cosm2_evidence) == 1 and world.cosm2_evidence[0]["passed"]
    assert world.counts() == {
        "operations": 1,
        "approvals": 1,
        "orders": 1,
        "payments": 1,
        "transactions": 1,
    }
    with psycopg.connect(world.downstream.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_cosm2_bindings").fetchone() == (1,)
    with psycopg.connect(world.namespace.dsn) as conn:
        envelope, payment_digest = conn.execute(
            "SELECT envelope_bytes,payment_digest FROM ag_threshold_approvals"
        ).fetchone()
        assert payment_digest != "0" * 64
        assert bytes(envelope).find(b"AG-COSM2-APPROVAL-1") >= 0


def test_execution_rebuilds_payment_digest_instead_of_trusting_action(world):
    before = world.counts()
    before_round1 = world.signer.exec_signer.round1_count
    with pytest.raises(CosignRefused) as error:
        world.accept_paid("changed-action-digest", payment_digest="f" * 64)
    assert error.value.code == "EXEC_MISMATCH"
    assert world.signer.exec_signer.round1_count == before_round1
    assert world.counts() == before
