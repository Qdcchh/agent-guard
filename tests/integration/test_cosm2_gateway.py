"""B6 real AS, SELECT-only authorization domain, gateway and independent effects."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

import psycopg
import pytest

from agent_guard.authorization.grant_revocation_service import GrantRevocationService
from agent_guard.authorization.provisioning import grant_tenant_admin
from agent_guard.cosign.curve import N
from agent_guard.cosign.encoding import signature_rs_to_der
from agent_guard.cosign.protocol import ExecParty
from agent_guard.cosign.shares import load_share
from agent_guard.crypto.sm import load_sm2_public_key, verify_sm2_message
from agent_guard.execution.service import ExecutionService
from agent_guard.execution.verified import VerifiedExecution
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.threshold.codec import cosm2_message
from agent_guard.threshold.contracts import ThresholdApprovalPolicy
from agent_guard.threshold.verifier import ThresholdApprovalVerifier
from agent_guard.tools.downstream import MockDownstream
from tests.fixtures.cosm2 import CosignSigner, readonly_provider
from tests.fixtures.cosm2_readonly import readonly_role
from tests.fixtures.execution import DOWNSTREAM_SECRET
from tests.fixtures.gateway import app_for, state
from tests.fixtures.threshold import RustThresholdSigner, approval_action
from tests.integration.test_threshold_gateway import (
    approval_rows,
    counter_values,
    order_count,
    send,
)
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


@dataclass
class CosignEnv:
    env: object
    signer: object
    policy: object
    app: object
    dsn: str = field(repr=False)
    downstream_dsn: str = field(repr=False)


def build_cosign_env(dsn, downstream_dsn, directory, readonly_dsn, *, env=None, now=None):
    env = env or signed_env(dsn, downstream_dsn)
    signer = CosignSigner(
        directory,
        dsn_readonly=readonly_dsn,
        snapshot_provider=readonly_provider(env.verifier._permission_provider, readonly_dsn),
        token_provider=lambda bundle: env.token,
        catalog=env.service._catalog,
        bundle_provider=lambda action: env.bundle(action["idempotency_key"]),
    )
    signer.enroll()
    downstream = MockDownstream(
        downstream_dsn,
        service_secret=DOWNSTREAM_SECRET,
        approved_suppliers={"supplier-001"},
        approved_recipients={"user-demo-001"},
        served_requests={"req-001"},
        cosign_policy=signer.policy,
    )
    downstream.provision()
    service = ExecutionService(
        gateway_dsn=dsn,
        ledger=ExecutionLedger(dsn),
        catalog=env.service._catalog,
        downstream=downstream,
        downstream_secret=DOWNSTREAM_SECRET,
        cosign_policy=signer.policy,
    )
    env.downstream, env.service = downstream, service
    env.adapter = VerifiedExecution(service, evidence_store=env.evidence)
    app = app_for(
        env, dsn, threshold_verifier=ThresholdApprovalVerifier(policy=signer.policy), now=now
    )
    return CosignEnv(env, signer, signer.policy, app, dsn, downstream_dsn)


@pytest.fixture()
def cosm2_env(ledger, dsn, downstream_dsn, tmp_path):
    with readonly_role(dsn) as readonly_dsn:
        value = build_cosign_env(dsn, downstream_dsn, tmp_path / "shares", readonly_dsn)
        try:
            yield value
        finally:
            value.app._executor.shutdown()


def make_action(te, key="purchase-1", *, expires_in=120, **changes):
    bundle = te.env.bundle(key)
    action = approval_action(
        bundle,
        action_id=f"action-{key}",
        policy_version=te.policy.policy_version,
        key_epoch=te.policy.key_epoch,
        expires_at=int(time.time()) + expires_in,
        version=3,
        payment_digest="0" * 64,
        **changes,
    )
    return bundle, action


def sign_header(te, action, bundle):
    return te.signer.header_for(action, te.signer.sign(action, bundle=bundle))


def assert_zero_effects(te):
    assert order_count(te.downstream_dsn) == 0
    assert approval_rows(te.dsn) == []
    assert counter_values(te.dsn) == [(0, 0, 0, 0)] * 3
    with psycopg.connect(te.dsn) as conn:
        for table in ("ag_operations", "ag_ledger_events", "ag_receipt_outbox"):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)


def revoke_ancestor(te, depth=1):
    with psycopg.connect(te.dsn) as conn:
        grant_id = conn.execute(
            "SELECT grant_id FROM ag_grants WHERE depth=%s", (depth,)
        ).fetchone()[0]
        grant_tenant_admin(conn, tenant_id="tenant-001", subject="cosm2-admin")
    GrantRevocationService(te.dsn).revoke_grant(
        tenant_id="tenant-001", grant_id=grant_id, authenticated_admin_subject="cosm2-admin"
    )


def exec_alone_signature(directory):
    """Actually hold only d1 and invent P2's partial; never construct full d."""
    share = load_share(directory / "exec", role="exec")
    party = ExecParty(share.share, share.public_point)
    party.sign_round1()
    try:
        r, s2, s3 = (secrets.randbelow(N - 1) + 1 for _ in range(3))
        s = (party.d1 * party._k1 * s2 + party.d1 * s3 - r) % N
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")
    finally:
        party._k1 = None


def test_c1_normal_one_order_and_same_approval_retry(cosm2_env):
    te = cosm2_env
    bundle, action = make_action(te)
    header = sign_header(te, action, bundle)
    status, accepted, _ = send(te, bundle, header)
    assert status == 202
    assert te.env.service.run_operation(accepted["operation_id"]).status == "SUCCEEDED"
    status, retry, _ = send(te, te.env.bundle("purchase-1"), header)
    assert status == 202 and retry["operation_id"] == accepted["operation_id"]
    assert order_count(te.downstream_dsn) == 1
    assert len(approval_rows(te.dsn)) == 1
    assert counter_values(te.dsn) == [(0, 70000, 0, 1)] * 3
    with psycopg.connect(te.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (1,)


def test_c2_missing(cosm2_env):
    te = cosm2_env
    before = state(te.dsn)
    status, body, _ = send(te, te.env.bundle(), None)
    assert status == 401 and body["error"]["code"] == "APPROVAL_REQUIRED"
    assert state(te.dsn) == before
    assert_zero_effects(te)


@pytest.mark.parametrize("attack", ["exec-alone", "fake64"])
def test_c3_c4_forgery(cosm2_env, attack):
    te = cosm2_env
    bundle, action = make_action(te)
    signature = (
        exec_alone_signature(te.signer.directory) if attack == "exec-alone" else b"\x07" * 64
    )
    status, body, _ = send(te, bundle, te.signer.header_for(action, signature))
    assert status == 401 and body["error"]["code"] == "INVALID_SIGNATURE"
    assert_zero_effects(te)


def test_c5_preserve_original_signature_then_tamper_amount(cosm2_env):
    te = cosm2_env
    bundle, action = make_action(te)
    signature = te.signer.sign(action, bundle=bundle)
    tampered = {**action, "amount_fen": 1}
    status, body, _ = send(te, bundle, te.signer.header_for(tampered, signature))
    assert status == 409 and body["error"]["code"] == "APPROVAL_MISMATCH"
    assert_zero_effects(te)


@pytest.mark.parametrize("depth", [0, 1])
def test_c6_revoked_before_cosign_zero_partial(cosm2_env, depth):
    te = cosm2_env
    bundle, action = make_action(te)
    revoke_ancestor(te, depth)
    before = te.signer.authz_signer.sign_count
    refused = te.signer.sign_refused(action, bundle=bundle)
    assert refused.code == "AUTHZ_REVOKED"
    assert te.signer.authz_signer.sign_count == before
    assert te.signer.exec_signer._party._k1 is None
    assert_zero_effects(te)


def test_c7_signed_then_revoked(cosm2_env):
    te = cosm2_env
    bundle, action = make_action(te)
    header = sign_header(te, action, bundle)
    revoke_ancestor(te)
    status, body, _ = send(te, bundle, header)
    assert status == 403 and body["error"]["code"] == "REVOKED"
    assert_zero_effects(te)


@pytest.mark.parametrize("settled", [False, True])
def test_c8_actual_remaining_budget(cosm2_env, settled):
    te = cosm2_env
    bundle, action = make_action(te)
    status, accepted, _ = send(te, bundle, sign_header(te, action, bundle))
    assert status == 202
    if settled:
        assert te.env.service.run_operation(accepted["operation_id"]).status == "SUCCEEDED"
    # The existing real operation consumes every applicable ancestor's remaining
    # allowance. No total limit or counter is edited for the negative request.
    counters = counter_values(te.dsn)
    assert all(row[0] + row[1] == 70000 for row in counters)
    second_bundle, second = make_action(te, key="purchase-2")
    before = te.signer.authz_signer.sign_count
    refused = te.signer.sign_refused(second, bundle=second_bundle)
    assert refused.code == "AUTHZ_OVER_BUDGET"
    assert te.signer.authz_signer.sign_count == before
    assert counter_values(te.dsn) == counters
    assert len(approval_rows(te.dsn)) == 1
    assert order_count(te.downstream_dsn) == int(settled)


def test_c9_frost_deployment_refuses_cosm2(cosm2_env, tmp_path):
    te = cosm2_env
    bundle, action = make_action(te)
    header = sign_header(te, action, bundle)
    signer = RustThresholdSigner(tmp_path / "frost-policy")
    policy = ThresholdApprovalPolicy(
        group_public_key=bytes.fromhex(signer.enroll()),
        policy_version=te.policy.policy_version,
        key_epoch=te.policy.key_epoch,
    )
    app = app_for(te.env, te.dsn, threshold_verifier=ThresholdApprovalVerifier(policy=policy))
    try:
        token_app, te.app = te.app, app
        status, _, _ = send(te, bundle, header)
        assert status in {400, 401, 403, 409}
        assert_zero_effects(te)
    finally:
        app._executor.shutdown()
        te.app = token_app


def test_c9_cosm2_deployment_refuses_frost(cosm2_env, tmp_path):
    te = cosm2_env
    bundle, action = make_action(te)
    signer = RustThresholdSigner(tmp_path / "frost")
    signer.enroll()
    frost_action = {key: value for key, value in action.items() if key != "payment_digest"}
    frost_action["version"] = 2
    signature = signer.sign(frost_action)
    status, _, _ = send(te, bundle, signer.header_for(frost_action, signature))
    assert status in {400, 401, 403, 409}
    assert_zero_effects(te)


def _c10_signed_approval(te):
    # Preparation must fit a real window even with concurrent signing/DB load.
    # Prove success before waiting; AUTHZ_EXPIRED can never count as C10 success.
    bundle, action = make_action(te, expires_in=10)
    header = sign_header(te, action, bundle)
    early_clock = int(time.time())
    assert early_clock < action["expires_at"]
    verified = te.app._endpoint._verify_approval(header, bundle)
    assert verified.expires_at == action["expires_at"]
    return bundle, action, header, early_clock


def _c10_wait_for_database_deadline(te, expires_at):
    # Synchronize with the actual authoritative database clock rather than
    # assuming a fixed sleep crossed a wall-clock second boundary.
    timeout = time.monotonic() + 15
    with psycopg.connect(te.dsn, autocommit=True) as conn:
        while True:
            observed = float(
                conn.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0]
            )
            if observed >= expires_at:
                return observed
            assert time.monotonic() < timeout, "database approval deadline was not reached"
            time.sleep(min(0.2, expires_at - observed))


def test_c10_expired_is_401(cosm2_env):
    te = cosm2_env
    bundle, action, header, _early_clock = _c10_signed_approval(te)
    assert _c10_wait_for_database_deadline(te, action["expires_at"]) >= action["expires_at"]
    status, body, _ = send(te, bundle, header)
    assert status == 401 and body["error"]["code"] == "EXPIRED", (status, body)
    assert_zero_effects(te)


def test_c10_final_database_clock_expiry_is_401(cosm2_env, monkeypatch):
    from agent_guard.execution import verified as verified_execution

    te = cosm2_env
    bundle, action, header, early_clock = _c10_signed_approval(te)
    te.app._executor.shutdown()
    te.app = app_for(
        te.env,
        te.dsn,
        threshold_verifier=ThresholdApprovalVerifier(policy=te.policy),
        now=lambda: early_clock,
    )
    final_clock = []
    original_binding = verified_execution.approval_binding

    def observe_binding(approval):
        callback, final_check = original_binding(approval)

        def observe_final_check(conn, operation, disposition):
            final_clock.append(
                float(conn.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0])
            )
            return final_check(conn, operation, disposition)

        return callback, observe_final_check

    monkeypatch.setattr(verified_execution, "approval_binding", observe_binding)
    assert _c10_wait_for_database_deadline(te, action["expires_at"]) >= action["expires_at"]
    # The off-lock verifier genuinely still accepts the original valid header.
    # Only the real acceptance transaction's final DB-clock check rejects it.
    assert early_clock < action["expires_at"]
    assert te.app._endpoint._verify_approval(header, bundle).expires_at == action["expires_at"]
    status, body, _ = send(te, bundle, header)
    assert status == 401 and body["error"]["code"] == "EXPIRED", (status, body)
    assert len(final_clock) == 1 and final_clock[0] >= action["expires_at"]
    assert_zero_effects(te)


def test_c11_standard_mature_verification(cosm2_env):
    te = cosm2_env
    bundle, action = make_action(te)
    signature = te.signer.sign(action, bundle=bundle)
    spki = te.policy.group_public_key
    verify_sm2_message(
        load_sm2_public_key(spki), cosm2_message(action), signature_rs_to_der(signature)
    )


def test_revoked_mid_precedes_exhausted_root(cosm2_env):
    te = cosm2_env
    bundle, action = make_action(te)
    status, accepted, _ = send(te, bundle, sign_header(te, action, bundle))
    assert status == 202
    assert te.env.service.run_operation(accepted["operation_id"]).status == "SUCCEEDED"
    second_bundle, second = make_action(te, key="purchase-2")
    revoke_ancestor(te, depth=1)
    before = te.signer.authz_signer.sign_count
    refused = te.signer.sign_refused(second, bundle=second_bundle)
    assert refused.code == "AUTHZ_REVOKED"
    assert te.signer.authz_signer.sign_count == before
    assert order_count(te.downstream_dsn) == 1
    assert len(approval_rows(te.dsn)) == 1


def test_p1_process_mode_from_enrollment_never_loads_parent_authz_share(
    ledger, dsn, downstream_dsn, tmp_path, monkeypatch
):
    from agent_guard.cosign import exec_domain
    from tests.fixtures import cosm2

    env = signed_env(dsn, downstream_dsn)
    reads = []
    original_load = exec_domain.load_share

    def load_execution_only(directory, *, role):
        reads.append(role)
        assert role == "exec"
        return original_load(directory, role=role)

    def forbid_parent_authz(**kwargs):
        raise AssertionError("P1 coordinator must not instantiate authorization signer")

    monkeypatch.setattr(exec_domain, "load_share", load_execution_only)
    monkeypatch.setattr(cosm2, "AuthorizationDomainSigner", forbid_parent_authz)
    with readonly_role(dsn) as ro:
        signer = CosignSigner(
            tmp_path / "p1",
            dsn_readonly=ro,
            snapshot_provider=readonly_provider(env.verifier._permission_provider, ro),
            token_provider=lambda bundle: env.token,
            catalog=env.service._catalog,
            process=True,
        )
        signer.enroll()
        assert signer.authz_signer is None
        bundle = env.bundle()
        action = approval_action(
            bundle,
            action_id="p1-actual-process",
            policy_version=1,
            key_epoch=1,
            expires_at=int(time.time()) + 60,
            version=3,
            payment_digest="0" * 64,
        )
        signature = signer.sign(action, bundle=bundle)
        assert reads == ["exec"]
        assert signer.exec_signer._party._k1 is None
        verify_sm2_message(
            load_sm2_public_key(signer.policy.group_public_key),
            cosm2_message(action),
            signature_rs_to_der(signature),
        )
        assert_zero_effects(CosignEnv(env, signer, signer.policy, None, dsn, downstream_dsn))
