"""B9 independent mature SM2 effect verification and durable replay binding."""

from __future__ import annotations

import uuid

import psycopg
import pytest

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode, ToolId
from agent_guard.execution import store
from agent_guard.threshold.codec import build_envelope
from agent_guard.threshold.contracts import COSM2_PROFILE
from tests.fixtures.execution import DOWNSTREAM_SECRET
from tests.integration.test_cosm2_gateway import (  # noqa: F401 - pytest fixture
    cosm2_env as cosm2_fixture,
)
from tests.integration.test_cosm2_gateway import (
    make_action,
    order_count,
    send,
    sign_header,
)

cosm2_env = cosm2_fixture

pytestmark = pytest.mark.integration


def accepted(te):
    bundle, action = make_action(te)
    status, answer, _ = send(te, bundle, sign_header(te, action, bundle))
    assert status == 202
    with psycopg.connect(te.dsn) as conn:
        operation = store.fetch_operation(conn, answer["operation_id"])
        envelope = bytes(
            conn.execute(
                "SELECT envelope_bytes FROM ag_threshold_approvals WHERE operation_id=%s",
                (operation.operation_id,),
            ).fetchone()[0]
        )
    args = {
        "service_secret": DOWNSTREAM_SECRET,
        "operation_id": operation.operation_id,
        "tool_id": ToolId.ORDER_CREATE,
        "canonical_params": operation.canonical_params,
        "quote": te.env.service._quote_of(operation),
        "expected_amount_fen": operation.amount_fen,
        "approval_envelope": envelope,
        "idempotency_key": operation.idempotency_key,
        "tenant_id": operation.tenant_id,
        "task_id": operation.task_id,
    }
    return operation, action, args


@pytest.mark.parametrize(
    "mutation", ["missing", "fake", "amount", "items", "key", "tenant", "task"]
)
def test_c12_bypassed_gateway_cannot_create_unapproved_or_changed_effect(cosm2_env, mutation):
    te = cosm2_env
    _, action, args = accepted(te)
    if mutation == "missing":
        args["approval_envelope"] = None
    elif mutation == "fake":
        args["approval_envelope"] = build_envelope(action, b"\x07" * 64, profile=COSM2_PROFILE)
    elif mutation == "amount":
        args["expected_amount_fen"] = 1
    elif mutation == "items":
        params = load_strict_json(args["canonical_params"])
        params["items"][0]["quantity"] = 2
        args["canonical_params"] = canonical_json_bytes(params)
    elif mutation == "key":
        args["idempotency_key"] = "different-business-key"
    elif mutation == "tenant":
        args["tenant_id"] = "different-tenant"
    else:
        args["task_id"] = "different-task"
    with pytest.raises(ExecutionError) as error:
        te.env.downstream.execute(**args)
    assert error.value.code == ExecutionErrorCode.DOWNSTREAM_UNAUTHORIZED
    assert order_count(te.downstream_dsn) == 0
    with psycopg.connect(te.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_operations").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM ds_cosm2_bindings").fetchone() == (0,)


def test_same_signed_intent_only_once_and_invalid_existing_replay_refused(cosm2_env):
    te = cosm2_env
    _, _, args = accepted(te)
    outcome = te.env.downstream.execute(**args)
    assert not outcome.already_existed
    assert te.env.downstream.execute(**args).already_existed
    assert order_count(te.downstream_dsn) == 1
    with pytest.raises(ExecutionError):
        te.env.downstream.execute(**{**args, "approval_envelope": None})
    with pytest.raises(ExecutionError):
        te.env.downstream.execute(**{**args, "operation_id": str(uuid.uuid4())})
    assert order_count(te.downstream_dsn) == 1
    with psycopg.connect(te.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_cosm2_bindings").fetchone() == (1,)


@pytest.mark.parametrize("after_commit", [False, True])
def test_original_immutable_envelope_forwarded_initial_and_recovery(cosm2_env, after_commit):
    te = cosm2_env
    operation, _, args = accepted(te)
    original = te.env.downstream
    captured = []

    class LoseFirstResponse:
        def execute(self, **kwargs):
            captured.append(kwargs)
            if len(captured) == 1:
                if after_commit:
                    original.execute(**kwargs)
                raise ConnectionError("synthetic response loss")
            return original.execute(**kwargs)

        def query(self, **kwargs):
            return original.query(**kwargs)

    te.env.service._downstream = LoseFirstResponse()
    assert te.env.service.run_operation(operation.operation_id).status == "UNKNOWN"
    with psycopg.connect(te.dsn) as conn:
        owner = conn.execute(
            "SELECT owner_token FROM ag_execution_leases WHERE operation_id=%s",
            (operation.operation_id,),
        ).fetchone()[0]
    assert (
        te.env.service.run_operation(operation.operation_id, owner_token=owner).status
        == "SUCCEEDED"
    )
    assert len(captured) == (1 if after_commit else 2)
    assert all(call["approval_envelope"] == args["approval_envelope"] for call in captured)
    assert all(call["idempotency_key"] == operation.idempotency_key for call in captured)
    assert order_count(te.downstream_dsn) == 1
    with psycopg.connect(te.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_cosm2_bindings").fetchone() == (1,)


def test_concurrent_same_approval_different_operation_only_one_effect(cosm2_env):
    from concurrent.futures import ThreadPoolExecutor

    te = cosm2_env
    _, _, args = accepted(te)

    def invoke(index):
        try:
            return te.env.downstream.execute(**{**args, "operation_id": f"race-{index}"})
        except ExecutionError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(invoke, range(2)))
    assert sum(answer == ExecutionErrorCode.DOWNSTREAM_UNAUTHORIZED for answer in answers) == 1
    assert order_count(te.downstream_dsn) == 1
