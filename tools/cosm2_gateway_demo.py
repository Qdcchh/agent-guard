"""Six fixed real-AS/PG dual-domain SM2 cases, with sanitized local evidence.

Prototype: same host, semi-honest, variable-time Python share arithmetic.
The authorization domain uses a genuine ephemeral SELECT-only PostgreSQL role.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agent_guard.authorization.proof import sign_ag_proof  # noqa: E402
from agent_guard.contracts.encoding import load_strict_json  # noqa: E402
from agent_guard.contracts.execution import ExecutionError, ToolId  # noqa: E402
from agent_guard.contracts.ledger import INVOKE_ENDPOINT  # noqa: E402
from agent_guard.cosign.encoding import point_to_hex  # noqa: E402
from agent_guard.crypto.sm import sm3_digest  # noqa: E402
from agent_guard.execution import store as execution_store  # noqa: E402
from agent_guard.ledger.lineage import apply_bundle_migrations  # noqa: E402
from agent_guard.threshold.codec import compute_params_digest  # noqa: E402
from tests.fixtures.cosm2_readonly import readonly_role  # noqa: E402
from tests.fixtures.execution import DOWNSTREAM_SECRET  # noqa: E402
from tests.fixtures.gateway import raw_material, request  # noqa: E402
from tests.fixtures.isolation import (  # noqa: E402
    acquire_namespace,
    create_downstream_database,
    drop_downstream_database,
    release_namespace,
)
from tests.integration.test_cosm2_gateway import (  # noqa: E402
    build_cosign_env,
    exec_alone_signature,
    make_action,
    revoke_ancestor,
    send,
    sign_header,
)
from tools.threshold_gateway_demo import _remaining, code_of  # noqa: E402

DEMO_ROOT = REPO / "artifacts" / "cosm2-gateway-demo-live"
CASE_ORDER = (
    "cosign-valid-one-order",
    "missing-approval",
    "exec-domain-alone",
    "tampered-amount",
    "revoked-before-cosign",
    "revoked-after-cosign",
)


def _cases(te):
    records = {}
    observations = []
    last_sample = {}

    def snapshot():
        with psycopg.connect(te.dsn) as conn:
            counters = conn.execute(
                "SELECT depth,amount_reserved,amount_settled,calls_reserved,calls_settled "
                "FROM ag_grants ORDER BY depth"
            ).fetchall()
            operations = conn.execute("SELECT count(*) FROM ag_operations").fetchone()[0]
        with psycopg.connect(te.downstream_dsn) as conn:
            orders = conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0]
        return {
            "orders": orders,
            "operations": operations,
            "counters": counters,
            "authz_sign_count": te.signer.authz_signer.sign_count,
        }

    def observe(case_id, location, code, before, passed):
        after = snapshot()
        passed = passed and before == after
        observations.append(
            {
                "case_id": case_id,
                "location": location,
                "observed_code": code,
                "before": before,
                "after": after,
                "passed": bool(passed),
            }
        )

    def refusal(case_id, action, bundle, expected, direct=False):
        before = snapshot()
        if direct:
            party = te.signer.exec_signer._party
            q1 = party.sign_round1()
            try:
                te.signer.authz_signer.respond(
                    action=action,
                    leaf_access_token=te.env.token,
                    q1_hex=point_to_hex(q1),
                    now=int(time.time()),
                )
                code = None
            except ValueError as exc:
                code = getattr(exc, "code", type(exc).__name__)
            finally:
                party._k1 = None
        else:
            code = te.signer.sign_refused(action, bundle=bundle).code
        passed = (
            code == expected and te.signer.authz_signer.sign_count == before["authz_sign_count"]
        )
        observe(case_id, "authorization_domain", code, before, passed)
        return code, passed

    def http_case(name, bundle, header, expected_status, expected_code=None):
        before = snapshot()
        started = time.monotonic_ns()
        wall_start = time.time_ns()
        status, body, _ = send(te, bundle, header)
        ended = time.monotonic_ns()
        last_sample.clear()
        last_sample.update(
            {
                "started_monotonic_ns": started,
                "ended_monotonic_ns": ended,
                "started_unix_ns": wall_start,
                "duration_ms": (ended - started) / 1_000_000,
                "http_status": status,
            }
        )
        record = {"name": name, "passed": status == expected_status, "http_status": status}
        if expected_code is not None:
            actual_code = code_of(body)
            record["code"] = actual_code
            record["passed"] &= actual_code == expected_code
        records[name] = record
        if expected_code is not None:
            location = "gateway_acceptance" if name == "revoked-after-cosign" else "gateway"
            observe(name, location, code_of(body), before, record["passed"])
        return status, body

    missing, _ = make_action(te, key="demo-missing")
    http_case("missing-approval", missing, None, 401, "APPROVAL_REQUIRED")
    alone, action = make_action(te, key="demo-alone")
    http_case(
        "exec-domain-alone",
        alone,
        te.signer.header_for(action, exec_alone_signature(te.signer.directory)),
        401,
        "INVALID_SIGNATURE",
    )
    http_case(
        "fake64-signature",
        alone,
        te.signer.header_for(action, b"\x07" * 64),
        401,
        "INVALID_SIGNATURE",
    )
    # A real stolen executor token is presented with another registered
    # holder's valid SM2 proof. The response is measured at the gateway.
    stolen_header = sign_header(te, action, alone)
    before = snapshot()
    token, _, body = raw_material(te.dsn, alone)
    registration = te.env.registrations[("tenant-001", "agent-selector")]
    proof = sign_ag_proof(
        te.env.keys["selector"],
        kid=registration.kid,
        client_id="agent-selector",
        purpose="invoke",
        endpoint=INVOKE_ENDPOINT,
        token=te.env.token,
        body=load_strict_json(body),
        now=int(time.time()),
    )
    stolen_status, stolen_body, _ = request(
        te.app,
        path="/v1/invocations",
        body=body,
        headers=[
            (b"content-type", b"application/json"),
            (b"authorization", b"AGPoP " + token),
            (b"ag-proof", proof.encode()),
            (b"ag-approval", stolen_header),
        ],
    )
    stolen_code = code_of(stolen_body)
    observe(
        "stolen-token-wrong-holder",
        "gateway",
        stolen_code,
        before,
        stolen_status == 401 and stolen_code in {"HOLDER_MISMATCH", "INVALID_SIGNATURE"},
    )
    # Expand scope directly at P2, preserving a self-consistent params digest.
    scope = {**action, "items": [{"sku": "sku-out-of-scope", "quantity": 1}]}
    scope["canonical_params_sha256"] = compute_params_digest(
        request_id=scope["request_id"],
        quote_id=scope["quote_id"],
        quote_version=scope["quote_version"],
        items=[("sku-out-of-scope", 1)],
        delivery_id=scope["delivery_id"],
    )
    refusal("expanded-scope", scope, alone, "AUTHZ_SCOPE", direct=True)
    tamper_bundle, original = make_action(te, key="demo-tampered")
    signature = te.signer.sign(original, bundle=tamper_bundle)
    http_case(
        "tampered-amount",
        tamper_bundle,
        te.signer.header_for({**original, "amount_fen": 1}, signature),
        409,
        "APPROVAL_MISMATCH",
    )

    # Pre-sign the later revoked request while all original budgets still allow
    # it. Signing makes no reservation and creates no persisted approval row.
    revoked_bundle, revoked_action = make_action(te, key="demo-revoked-after")
    revoked_header = sign_header(te, revoked_action, revoked_bundle)
    bundle, action = make_action(te, key="demo-valid")
    header = sign_header(te, action, bundle)
    timing = te.signer.last_timing_ms.copy()
    status, accepted = http_case("cosign-valid-one-order", bundle, header, 202)
    sample = last_sample.copy()
    valid = records["cosign-valid-one-order"]
    if status == 202:
        operation = accepted["operation_id"]
        valid["passed"] &= te.env.service.run_operation(operation).status == "SUCCEEDED"
        retry_status, retry, _ = send(te, te.env.bundle("demo-valid"), header)
        valid["passed"] &= retry_status == 202 and retry.get("operation_id") == operation

    if status == 202:
        with psycopg.connect(te.dsn) as conn:
            durable = execution_store.fetch_operation(conn, operation)
            envelope = bytes(
                conn.execute(
                    "SELECT envelope_bytes FROM ag_threshold_approvals WHERE operation_id=%s",
                    (operation,),
                ).fetchone()[0]
            )
        base = {
            "service_secret": DOWNSTREAM_SECRET,
            "operation_id": str(uuid.uuid4()),
            "tool_id": ToolId.ORDER_CREATE,
            "canonical_params": durable.canonical_params,
            "quote": te.env.service._quote_of(durable),
            "expected_amount_fen": durable.amount_fen,
            "approval_envelope": envelope,
            "idempotency_key": durable.idempotency_key,
            "tenant_id": durable.tenant_id,
            "task_id": durable.task_id,
        }
        for name, override in (
            ("downstream-no-approval", {"approval_envelope": None}),
            ("downstream-changed-amount", {"expected_amount_fen": 1}),
            ("downstream-replay-new-operation", {}),
        ):
            before = snapshot()
            try:
                te.env.downstream.execute(**{**base, **override})
                code = None
            except ExecutionError as exc:
                code = exc.code.value
            observe(name, "downstream", code, before, code == "DOWNSTREAM_UNAUTHORIZED")

    refusal("over-remaining-budget", revoked_action, revoked_bundle, "AUTHZ_OVER_BUDGET")
    revoke_ancestor(te)
    revoked_code, revoked_passed = refusal(
        "revoked-before-cosign", revoked_action, revoked_bundle, "AUTHZ_REVOKED"
    )
    records["revoked-before-cosign"] = {
        "name": "revoked-before-cosign",
        "passed": revoked_passed,
        "refused_by": "authz",
        "code": revoked_code,
    }
    http_case("revoked-after-cosign", revoked_bundle, revoked_header, 403, "REVOKED")
    return [records[name] for name in CASE_ORDER], timing, sample, observations


def run_demo(dsn: str) -> tuple[int, dict]:
    run_id = str(uuid.uuid4())
    outdir = DEMO_ROOT / run_id
    private = outdir / "private"
    outdir.mkdir(parents=True, mode=0o700)
    private.mkdir(mode=0o700)
    namespace = acquire_namespace(dsn)
    downstream = None
    try:
        with psycopg.connect(namespace.dsn) as conn:
            apply_bundle_migrations(conn)
        downstream = create_downstream_database(namespace.base_dsn)
        with readonly_role(namespace.dsn) as readonly_dsn:
            te = build_cosign_env(namespace.dsn, downstream.dsn, private / "shares", readonly_dsn)
            fingerprint = sm3_digest(te.policy.group_public_key).hex()[:16]
            try:
                cases, timing, sample, observations = _cases(te)
            finally:
                te.app._executor.shutdown()
        with psycopg.connect(namespace.dsn) as conn:
            approvals = conn.execute("SELECT count(*) FROM ag_threshold_approvals").fetchone()[0]
            operations = conn.execute("SELECT count(*) FROM ag_operations").fetchone()[0]
        with psycopg.connect(downstream.dsn) as conn:
            orders = conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0]
    except BaseException as exc:
        (outdir / "failure.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "exception_type": type(exc).__name__,
                    "completed_at": int(time.time()),
                }
            )
            + "\n"
        )
        raise
    finally:
        if downstream is not None:
            drop_downstream_database(namespace.base_dsn, downstream)
        release_namespace(namespace)
        shutil.rmtree(private, ignore_errors=True)
        remaining = _remaining(namespace, downstream, private)
        (outdir / "cleanup.json").write_text(json.dumps({"resources_remaining": remaining}) + "\n")

    passed = all(case["passed"] for case in cases) and (orders, operations, approvals) == (1, 1, 1)
    passed &= not remaining and all(item["passed"] for item in observations)
    result = {
        "run_id": run_id,
        "passed": passed,
        "completed_at": int(time.time()),
        "scheme": "sm2-2p",
        "public_key_fingerprint": fingerprint,
        "orders": orders,
        "operations": operations,
        "approvals": approvals,
        "resources_remaining": len(remaining),
        "cases": cases,
        "timing_ms": {
            "round1": timing["round1"],
            "round2_with_checks": timing["round2"],
            "round3_with_verify": timing["round3"],
        },
    }
    measurement = {
        "version": 1,
        "run_id": run_id,
        "metric": "gateway_accept_e2e",
        "boundary": (
            "before real ASGI request to after HTTP response (expected 202); "
            "excludes effect execution and retry"
        ),
        "unit": "ms",
        "n": 1,
        "samples": [sample],
        "completed_at": result["completed_at"],
    }
    (outdir / "negative-matrix.json").write_text(
        json.dumps(
            {
                "version": 1,
                "run_id": run_id,
                "observations": observations,
                "unobserved_locations": "not triggered; no refusal claim",
            },
            indent=2,
        )
        + "\n"
    )
    (outdir / "measurement.json").write_text(json.dumps(measurement, indent=2) + "\n")
    (outdir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return (0 if passed else 1), result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn")
    args = parser.parse_args(argv)
    dsn = (
        args.dsn
        or os.environ.get("AGENT_GUARD_COSM2_DEMO_DSN")
        or os.environ.get("AGENT_GUARD_TEST_DATABASE_URL")
    )
    if not dsn:
        print("Set AGENT_GUARD_COSM2_DEMO_DSN or AGENT_GUARD_TEST_DATABASE_URL", file=sys.stderr)
        return 2
    try:
        code, result = run_demo(dsn)
    except BaseException as exc:
        print(f"双域共签演示未完成：{type(exc).__name__}", file=sys.stderr)
        return 1
    for case in result["cases"]:
        print(f"{case['name']}: {'PASS' if case['passed'] else 'FAIL'}")
    print("结果目录：", DEMO_ROOT / result["run_id"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
