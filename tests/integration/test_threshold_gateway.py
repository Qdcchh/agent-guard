"""T6: real 2-of-3 FROST approval through the real SM2/AGPoP gateway and ledger.

Every case uses the real signed AS root→leaf chain, the real PostgreSQL ledger,
an independent downstream database and the pinned Rust FROST signer. No
cryptographic check is doubled or simulated here.
"""

from __future__ import annotations

import hashlib
import multiprocessing
import threading
import time
from dataclasses import dataclass

import psycopg
import pytest

from agent_guard.audit import journal
from agent_guard.authorization.grant_revocation_service import GrantRevocationService
from agent_guard.authorization.provisioning import grant_tenant_admin
from agent_guard.execution.service import ExecutionService
from agent_guard.execution.verified import VerifiedExecution
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.threshold.codec import action_message
from agent_guard.threshold.contracts import ThresholdApprovalPolicy
from agent_guard.threshold.verifier import ThresholdApprovalVerifier
from tests.fixtures.execution import DOWNSTREAM_SECRET, build_catalog
from tests.fixtures.gateway import app_for, query_bundle, raw_material, request, state
from tests.fixtures.threshold import RustThresholdSigner, approval_action
from tests.integration.test_verified_execution import TOOLS, signed_env

pytestmark = pytest.mark.integration

POLICY_VERSION = 3
KEY_EPOCH = 5
TENANT = "tenant-001"
TASK = "task-001"


@dataclass
class ThresholdEnv:
    env: object
    signer: RustThresholdSigner
    policy: ThresholdApprovalPolicy
    app: object
    dsn: str
    downstream_dsn: str


def build_threshold_env(dsn, downstream_dsn, tmp_path):
    env = signed_env(dsn, downstream_dsn)
    signer = RustThresholdSigner(tmp_path / "frostdemo")
    policy = ThresholdApprovalPolicy(
        group_public_key=bytes.fromhex(signer.enroll()),
        policy_version=POLICY_VERSION,
        key_epoch=KEY_EPOCH,
        max_lifetime_seconds=3600,
    )
    app = app_for(env, dsn, threshold_verifier=ThresholdApprovalVerifier(policy=policy))
    return ThresholdEnv(env, signer, policy, app, dsn, downstream_dsn)


@pytest.fixture()
def threshold_env(ledger, dsn, downstream_dsn, tmp_path):
    value = build_threshold_env(dsn, downstream_dsn, tmp_path)
    try:
        yield value
    finally:
        value.app._executor.shutdown()


def make_action(
    te: ThresholdEnv,
    *,
    key: str = "purchase-1",
    action_id: str | None = None,
    expires_in: int = 120,
    bundle=None,
    **mutations,
):
    bundle = bundle if bundle is not None else te.env.bundle(key)
    arguments = {
        "action_id": action_id if action_id is not None else f"action-{key}",
        "policy_version": te.policy.policy_version,
        "key_epoch": te.policy.key_epoch,
        "expires_at": int(time.time()) + expires_in,
    }
    arguments.update(mutations)
    return bundle, approval_action(bundle, **arguments)


def send(te: ThresholdEnv, bundle, header=None, *, path="/v1/invocations", extra=None):
    token, proof, body = raw_material(te.dsn, bundle)
    headers = [
        (b"content-type", b"application/json"),
        (b"authorization", b"AGPoP " + token),
        (b"ag-proof", proof),
    ]
    if header is not None:
        headers.append((b"ag-approval", header))
    if extra:
        headers.extend(extra)
    return request(te.app, path=path, body=body, headers=headers)


def accept_approved(te, key="purchase-1", **mutations):
    bundle, action = make_action(te, key=key, **mutations)
    header = te.signer.header_for(action, te.signer.sign(action))
    return bundle, action, header, send(te, bundle, header)


def counters(dsn):
    with psycopg.connect(dsn) as conn:
        return conn.execute(
            "SELECT depth, amount_reserved, amount_settled, calls_reserved, calls_settled "
            "FROM ag_grants ORDER BY depth"
        ).fetchall()


def counter_values(dsn):
    return [row[1:] for row in counters(dsn)]


def approval_rows(dsn):
    with psycopg.connect(dsn) as conn:
        return conn.execute(
            "SELECT tenant_id, task_id, action_id, operation_id, path_ids, message_sha256, "
            "envelope_sm3, amount_fen, quote_id, policy_version, key_epoch "
            "FROM ag_threshold_approvals ORDER BY action_id"
        ).fetchall()


def proof_count(dsn):
    with psycopg.connect(dsn) as conn:
        return conn.execute("SELECT count(*) FROM ag_proofs").fetchone()[0]


def order_count(dsn):
    with psycopg.connect(dsn) as conn:
        return conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0]


def test_valid_approval_creates_one_order_and_retry_stays_idempotent(threshold_env):
    te = threshold_env
    bundle, action, header, (status, accepted, _) = accept_approved(te)
    assert status == 202 and accepted["status"] == "RESERVED"

    assert te.env.service.run_operation(accepted["operation_id"]).status == "SUCCEEDED"
    assert order_count(te.downstream_dsn) == 1
    rows = approval_rows(te.dsn)
    assert len(rows) == 1
    assert rows[0][0:4] == (TENANT, TASK, "action-purchase-1", accepted["operation_id"])
    assert tuple(rows[0][4]) == tuple(action["path_grant_ids"])
    assert rows[0][5] == hashlib.sha256(action_message(action)).hexdigest()
    assert rows[0][7] == 70000 and rows[0][8] == "quote-001"
    assert rows[0][9] == POLICY_VERSION and rows[0][10] == KEY_EPOCH
    assert tuple(counters(te.dsn)[0][1:]) == (0, 70000, 0, 1)

    # A retry with a fresh proof and the same approval is EXISTING: no second
    # reservation, order, evidence link or approval row.
    retry_bundle = te.env.bundle("purchase-1")
    status, answer, _ = send(te, retry_bundle, header)
    assert status == 202
    assert answer["operation_id"] == accepted["operation_id"]
    assert answer["status"] == "SUCCEEDED"
    assert order_count(te.downstream_dsn) == 1
    assert len(approval_rows(te.dsn)) == 1
    assert counter_values(te.dsn) == [(0, 70000, 0, 1)] * 3
    with psycopg.connect(te.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (1,)


def test_valid_approval_still_respects_budget(threshold_env):
    te = threshold_env
    bundle, action, header, (status, accepted, _) = accept_approved(te)
    assert status == 202
    assert te.env.service.run_operation(accepted["operation_id"]).status == "SUCCEEDED"

    _, second_action = make_action(te, key="purchase-2", action_id="action-purchase-2")
    second_header = te.signer.header_for(second_action, te.signer.sign(second_action))
    second_bundle = te.env.bundle("purchase-2")
    status, body, _ = send(te, second_bundle, second_header)
    assert status == 422 and body["error"]["code"] == "BUDGET_EXCEEDED"
    assert order_count(te.downstream_dsn) == 1
    assert len(approval_rows(te.dsn)) == 1
    with psycopg.connect(te.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (1,)


def test_missing_approval_is_rejected_without_touching_the_ledger(threshold_env):
    te = threshold_env
    before = proof_count(te.dsn)
    bundle = te.env.bundle("purchase-1")
    status, body, _ = send(te, bundle, None)
    assert status == 401 and body["error"]["code"] == "APPROVAL_REQUIRED"
    with psycopg.connect(te.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM ag_threshold_approvals").fetchone() == (0,)
    assert proof_count(te.dsn) == before
    assert counter_values(te.dsn) == [(0, 0, 0, 0)] * 3
    assert order_count(te.downstream_dsn) == 0


def test_real_signer_refuses_one_of_three_and_duplicate_participant(threshold_env):
    te = threshold_env
    _, action = make_action(te)
    one = te.signer.sign_refused(action, ("signer-1",))
    duplicate = te.signer.sign_refused(action, ("signer-1", "signer-1"))
    assert one.returncode != 0 and duplicate.returncode != 0
    assert not (te.signer.directory / "refused-signer-1-sig.json").exists()
    assert not (te.signer.directory / "refused-signer-1-signer-1-sig.json").exists()


def test_foreign_group_and_fake_signatures_are_rejected(threshold_env, tmp_path):
    te = threshold_env
    _, action = make_action(te)
    foreign = RustThresholdSigner(tmp_path / "foreign")
    foreign.enroll()
    foreign_signature = foreign.sign(action)
    status, body, _ = send(
        te, te.env.bundle("purchase-1"), te.signer.header_for(action, foreign_signature)
    )
    assert status == 401 and body["error"]["code"] == "INVALID_SIGNATURE"

    fake = b"\x01" * 64
    status, body, _ = send(te, te.env.bundle("purchase-1"), te.signer.header_for(action, fake))
    assert status == 401 and body["error"]["code"] == "INVALID_SIGNATURE"
    with psycopg.connect(te.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (0,)
    assert counter_values(te.dsn) == [(0, 0, 0, 0)] * 3


@pytest.mark.parametrize(
    "variant,expected_code,expected_status",
    [
        ("amount", "APPROVAL_MISMATCH", 409),
        ("delivery", "APPROVAL_MISMATCH", 409),
        ("task", "APPROVAL_MISMATCH", 409),
        ("holder", "APPROVAL_MISMATCH", 409),
        ("policy", "APPROVAL_MISMATCH", 409),
        ("epoch", "APPROVAL_MISMATCH", 409),
        ("request", "APPROVAL_MISMATCH", 409),
    ],
)
def test_tampered_approval_facts_are_rejected(
    threshold_env, variant, expected_code, expected_status
):
    te = threshold_env
    mutations = {
        "amount": {"amount_fen": 1},
        "delivery": {"delivery_id": "office-evil"},
        "task": {"task_id": "task-evil"},
        "holder": {"holder_kid": "kid-evil"},
        "policy": {"policy_version": POLICY_VERSION + 1},
        "epoch": {"key_epoch": KEY_EPOCH + 1},
        "request": {"request_id": "req-evil"},
    }[variant]
    bundle, action = make_action(te, **mutations)
    header = te.signer.header_for(action, te.signer.sign(action))
    status, body, _ = send(te, bundle, header)
    assert status == expected_status and body["error"]["code"] == expected_code
    with psycopg.connect(te.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM ag_threshold_approvals").fetchone() == (0,)
    assert counter_values(te.dsn) == [(0, 0, 0, 0)] * 3
    assert order_count(te.downstream_dsn) == 0


def test_expired_approval_is_rejected(threshold_env):
    te = threshold_env
    bundle, action = make_action(te, expires_in=1)
    header = te.signer.header_for(action, te.signer.sign(action))
    time.sleep(2)
    status, body, _ = send(te, bundle, header)
    assert status == 403 and body["error"]["code"] == "EXPIRED"
    with psycopg.connect(te.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM ag_threshold_approvals").fetchone() == (0,)
    assert counter_values(te.dsn) == [(0, 0, 0, 0)] * 3


def test_approval_expiring_after_initial_verification_is_refused_at_final_clock(
    ledger, dsn, downstream_dsn, tmp_path
):
    env = signed_env(dsn, downstream_dsn)
    proofs_before = proof_count(dsn)
    signer = RustThresholdSigner(tmp_path / "finalclock")
    policy = ThresholdApprovalPolicy(
        group_public_key=bytes.fromhex(signer.enroll()),
        policy_version=POLICY_VERSION,
        key_epoch=KEY_EPOCH,
        max_lifetime_seconds=3600,
    )
    # The early check sees a slightly older clock (as if verification happened
    # earlier); the authoritative decision is the database clock under the
    # acceptance transaction after all deferred/journal/publication work.
    app = app_for(
        env,
        dsn,
        threshold_verifier=ThresholdApprovalVerifier(policy=policy),
        now=lambda: int(time.time()) - 5,
    )
    try:
        te = ThresholdEnv(env, signer, policy, app, dsn, downstream_dsn)
        bundle, action = make_action(te, expires_in=2)
        header = signer.header_for(action, signer.sign(action))
        time.sleep(3)
        status, body, _ = send(te, bundle, header)
        assert status == 403 and body["error"]["code"] == "EXPIRED"
        with psycopg.connect(dsn) as conn:
            assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (0,)
            assert conn.execute("SELECT count(*) FROM ag_threshold_approvals").fetchone() == (0,)
        assert proof_count(dsn) == proofs_before
        assert counter_values(dsn) == [(0, 0, 0, 0)] * 3
        assert order_count(downstream_dsn) == 0
    finally:
        app._executor.shutdown()


def test_valid_approval_then_ancestor_revocation_rejects_retry(threshold_env):
    te = threshold_env
    bundle, action, header, (status, accepted, _) = accept_approved(te)
    assert status == 202
    with psycopg.connect(te.dsn) as conn:
        mid = conn.execute(
            "SELECT grant_id FROM ag_grants WHERE depth=1 AND task_id=%s", (TASK,)
        ).fetchone()[0]
        grant_tenant_admin(conn, tenant_id=TENANT, subject="admin-revoke")
    GrantRevocationService(te.dsn).revoke_grant(
        tenant_id=TENANT, grant_id=mid, authenticated_admin_subject="admin-revoke"
    )

    retry_bundle = te.env.bundle("purchase-1")
    status, body, _ = send(te, retry_bundle, header)
    assert status == 403 and body["error"]["code"] == "REVOKED"
    with psycopg.connect(te.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM ag_threshold_approvals").fetchone() == (1,)
        assert conn.execute(
            "SELECT count(*) FROM ag_proofs WHERE operation_id IS NOT NULL"
        ).fetchone() == (1,)
    assert counter_values(te.dsn) == [(70000, 0, 1, 0)] * 3
    assert order_count(te.downstream_dsn) == 0


def test_concurrent_duplicate_approval_has_one_effect(threshold_env):
    te = threshold_env
    bundle, action = make_action(te)
    header = te.signer.header_for(action, te.signer.sign(action))
    first = te.env.bundle("purchase-1")
    second = te.env.bundle("purchase-1")

    barrier = threading.Barrier(2)
    results = []

    def worker(bundle):
        barrier.wait()
        results.append(send(te, bundle, header))

    threads = [threading.Thread(target=worker, args=(bundle,)) for bundle in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert len(results) == 2
    statuses = sorted(status for status, _, _ in results)
    assert statuses[0] in (202, 409) and 202 in statuses, results
    with psycopg.connect(te.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM ag_threshold_approvals").fetchone() == (1,)
    assert counter_values(te.dsn) == [(70000, 0, 1, 0)] * 3
    operation_id = None
    with psycopg.connect(te.dsn) as conn:
        operation_id = conn.execute("SELECT operation_id FROM ag_operations").fetchone()[0]
    assert te.env.service.run_operation(operation_id).status == "SUCCEEDED"
    assert order_count(te.downstream_dsn) == 1


def test_failed_accept_transaction_does_not_consume_the_approval(threshold_env, monkeypatch):
    te = threshold_env
    bundle, action = make_action(te)
    header = te.signer.header_for(action, te.signer.sign(action))
    proofs_before = proof_count(te.dsn)
    original = journal.append_accept_tx
    calls = {"count": 0}

    def flaky(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("injected failure after the approval binding")
        return original(*args, **kwargs)

    monkeypatch.setattr(journal, "append_accept_tx", flaky)
    status, _, _ = send(te, bundle, header)
    assert status == 500
    with psycopg.connect(te.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM ag_threshold_approvals").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM ag_operation_evidence").fetchone() == (0,)
    assert proof_count(te.dsn) == proofs_before
    assert counter_values(te.dsn) == [(0, 0, 0, 0)] * 3

    retry_bundle = te.env.bundle("purchase-1")
    status, accepted, _ = send(te, retry_bundle, header)
    assert status == 202 and calls["count"] == 2
    with psycopg.connect(te.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_threshold_approvals").fetchone() == (1,)
        assert (
            conn.execute("SELECT operation_id FROM ag_threshold_approvals").fetchone()[0]
            == accepted["operation_id"]
        )


def _restart_child(dsn, env, approval, queue):
    try:
        ledger = ExecutionLedger(dsn)
        service = ExecutionService(
            gateway_dsn=dsn,
            ledger=ledger,
            catalog=build_catalog(TENANT, TASK),
            downstream=env.downstream,
            downstream_secret=DOWNSTREAM_SECRET,
        )
        adapter = VerifiedExecution(service, evidence_store=env.evidence)
        bundle = env.bundle("purchase-1")
        response = adapter.accept_response(bundle, receipt_verifier=None, approval=approval)
        queue.put(
            {"ok": True, "operation_id": response["operation_id"], "status": response["status"]}
        )
    except BaseException as exc:  # noqa: BLE001 - the child reports only a class name
        queue.put({"ok": False, "error": type(exc).__name__})


def test_restart_in_a_new_process_reuses_the_durable_binding(threshold_env):
    te = threshold_env
    bundle, action = make_action(te)
    header = te.signer.header_for(action, te.signer.sign(action))
    status, accepted, _ = send(te, bundle, header)
    assert status == 202
    assert te.env.service.run_operation(accepted["operation_id"]).status == "SUCCEEDED"
    assert order_count(te.downstream_dsn) == 1

    from agent_guard.threshold.codec import decode_header, parse_envelope

    # Rebuild the verified approval in this process exactly as the gateway did.
    verifier = ThresholdApprovalVerifier(policy=te.policy)
    from agent_guard.threshold.contracts import ThresholdApprovalExpectation

    invocation = bundle.invocation
    approval = verifier.verify(
        header,
        expected=ThresholdApprovalExpectation(
            tenant_id=invocation.tenant_id,
            task_id=invocation.task_id,
            root_grant_id=invocation.root_id,
            grant_id=invocation.grant_id,
            holder_client_id=invocation.holder_client_id,
            holder_kid=invocation.holder_kid,
            tool_id=invocation.tool_id,
            tool_version=invocation.tool_version,
            idempotency_key=invocation.idempotency_key,
            canonical_params=invocation.canonical_params,
            path_grant_ids=tuple([*invocation.ancestor_ids, invocation.grant_id]),
        ),
        now=int(time.time()),
    )
    assert decode_header(header) and parse_envelope(decode_header(header))

    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    child = context.Process(target=_restart_child, args=(te.dsn, te.env, approval, queue))
    child.start()
    outcome = queue.get(timeout=120)
    child.join(timeout=120)
    assert outcome["ok"] is True, outcome
    assert child.exitcode == 0
    assert outcome["operation_id"] == accepted["operation_id"]
    assert order_count(te.downstream_dsn) == 1
    with psycopg.connect(te.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM ag_threshold_approvals").fetchone() == (1,)
    assert counter_values(te.dsn) == [(0, 70000, 0, 1)] * 3


def test_downstream_response_loss_recovery_keeps_original_approval(threshold_env):
    te = threshold_env
    bundle, action = make_action(te)
    header = te.signer.header_for(action, te.signer.sign(action))

    class LoseResponse:
        def execute(self, **kwargs):
            te.env.downstream.execute(**kwargs)
            raise ConnectionError("synthetic response loss after independent commit")

        def query(self, **kwargs):
            return te.env.downstream.query(**kwargs)

    te.env.service._downstream = LoseResponse()
    status, accepted, _ = send(te, bundle, header)
    assert status == 202
    assert te.env.service.run_operation(accepted["operation_id"]).status == "UNKNOWN"
    assert order_count(te.downstream_dsn) == 1
    with psycopg.connect(te.dsn) as conn:
        owner = conn.execute(
            "SELECT owner_token FROM ag_execution_leases WHERE operation_id=%s",
            (accepted["operation_id"],),
        ).fetchone()[0]
    assert (
        te.env.service.reconcile(accepted["operation_id"], owner_token=owner).status == "SUCCEEDED"
    )
    assert order_count(te.downstream_dsn) == 1
    assert len(approval_rows(te.dsn)) == 1
    assert counter_values(te.dsn) == [(0, 70000, 0, 1)] * 3


def test_operation_cannot_be_rebound_to_a_different_approval(threshold_env):
    te = threshold_env
    bundle, action, header, (status, accepted, _) = accept_approved(te)
    assert status == 202

    _, other_action = make_action(te, action_id="action-purchase-1b")
    other_header = te.signer.header_for(other_action, te.signer.sign(other_action))
    retry_bundle = te.env.bundle("purchase-1")
    status, body, _ = send(te, retry_bundle, other_header)
    assert status == 409 and body["error"]["code"] == "APPROVAL_MISMATCH"
    rows = approval_rows(te.dsn)
    assert len(rows) == 1 and rows[0][2] == "action-purchase-1"
    assert rows[0][3] == accepted["operation_id"]
    assert counter_values(te.dsn) == [(70000, 0, 1, 0)] * 3


def test_approval_header_is_scoped_to_the_trusted_policy(threshold_env):
    te = threshold_env
    # a non-order tool must not carry an approval header
    read_bundle = te.env.bundle("read-1", tool=TOOLS[0], params={"request_id": "req-001"})
    status, body, _ = send(te, read_bundle, b"AAAA")
    assert status == 400 and body["error"]["code"] == "INVALID_SCHEMA"
    assert counter_values(te.dsn) == [(0, 0, 0, 0)] * 3

    # the query route never accepts one either
    _, _, _, (status, accepted, _) = accept_approved(te, key="purchase-q")
    assert status == 202
    query = query_bundle(te.env, accepted["operation_id"])
    status, body, _ = send(te, query, b"AAAA", path="/v1/operations/query")
    assert status == 400 and body["error"]["code"] == "INVALID_SCHEMA"


def test_legacy_deployment_without_policy_keeps_compatibility(
    ledger, dsn, downstream_dsn, tmp_path
):
    env = signed_env(dsn, downstream_dsn)
    legacy_app = app_for(env, dsn)
    try:
        bundle = env.bundle("legacy-1")
        status, accepted, _ = send(
            ThresholdEnv(env, None, None, legacy_app, dsn, downstream_dsn), bundle, None
        )
        assert status == 202
        status, body, _ = send(
            ThresholdEnv(env, None, None, legacy_app, dsn, downstream_dsn),
            env.bundle("legacy-2"),
            b"AAAA",
        )
        assert status == 400 and body["error"]["code"] == "INVALID_SCHEMA"
    finally:
        legacy_app._executor.shutdown()


def test_durable_approval_rows_are_immutable(threshold_env):
    te = threshold_env
    _, _, _, (status, accepted, _) = accept_approved(te)
    assert status == 202
    with psycopg.connect(te.dsn) as conn:
        with pytest.raises(psycopg.Error):
            conn.execute(
                "UPDATE ag_threshold_approvals SET amount_fen = 1 WHERE action_id = %s",
                ("action-purchase-1",),
            )
        conn.rollback()
        with pytest.raises(psycopg.Error):
            conn.execute(
                "DELETE FROM ag_threshold_approvals WHERE action_id = %s",
                ("action-purchase-1",),
            )
        conn.rollback()
        assert conn.execute(
            "SELECT amount_fen, operation_id FROM ag_threshold_approvals"
        ).fetchone() == (70000, accepted["operation_id"])


def test_evidence_and_state_unchanged_on_no_approval(threshold_env):
    te = threshold_env
    before = state(te.dsn, proofs=False)
    bundle = te.env.bundle("purchase-1")
    status, _, _ = send(te, bundle, None)
    assert status == 401
    after = state(te.dsn, proofs=False)
    assert after == before
