"""Fixed local 2-of-3 threshold purchase demo over the real gateway.

This is a *local teaching demo*: it uses the real signed AS root→leaf chain,
the real SM2/AGPoP gateway, the real PostgreSQL ledger, an independent mock
downstream and the pinned Rust FROST signer. It never pretends to be a
production deployment; it writes sanitized JSON evidence only.

Run from the repository root with the project test environment:

    export AGENT_GUARD_TEST_DATABASE_URL=...   # or AGENT_GUARD_THRESHOLD_DEMO_DSN
    python tools/threshold_gateway_demo.py

The script exits 0 only when every expected case happened, and prints the
result directory for the local demo page.
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

from agent_guard.authorization.grant_revocation_service import (  # noqa: E402
    GrantRevocationService,
)
from agent_guard.authorization.provisioning import grant_tenant_admin  # noqa: E402
from agent_guard.ledger.lineage import apply_bundle_migrations  # noqa: E402
from agent_guard.threshold.contracts import ThresholdApprovalPolicy  # noqa: E402
from agent_guard.threshold.verifier import ThresholdApprovalVerifier  # noqa: E402
from tests.fixtures.gateway import app_for, raw_material, request  # noqa: E402
from tests.fixtures.isolation import (  # noqa: E402
    acquire_namespace,
    create_downstream_database,
    drop_downstream_database,
    release_namespace,
)
from tests.fixtures.threshold import RustThresholdSigner, approval_action  # noqa: E402
from tests.integration.test_verified_execution import signed_env  # noqa: E402

POLICY_VERSION = 3
KEY_EPOCH = 5
TENANT = "tenant-001"
TASK = "task-001"
DEMO_ROOT = REPO / "artifacts" / "threshold-gateway-demo-live"


def send(app, dsn, bundle, header):
    token, proof, body = raw_material(dsn, bundle)
    headers = [
        (b"content-type", b"application/json"),
        (b"authorization", b"AGPoP " + token),
        (b"ag-proof", proof),
    ]
    if header is not None:
        headers.append((b"ag-approval", header))
    return request(app, path="/v1/invocations", body=body, headers=headers)


def code_of(body):
    error = body.get("error") if isinstance(body, dict) else None
    return error.get("code") if isinstance(error, dict) else None


def run_demo(dsn: str) -> tuple[int, dict]:
    run_id = str(uuid.uuid4())
    outdir = DEMO_ROOT / run_id
    private = outdir / "private"
    outdir.mkdir(parents=True, mode=0o700)
    private.mkdir(mode=0o700)
    namespace = acquire_namespace(dsn)
    downstream = None
    cases: list[dict] = []
    resources_remaining: list[str] = []
    try:
        with psycopg.connect(namespace.dsn) as conn:
            apply_bundle_migrations(conn)
        downstream = create_downstream_database(namespace.base_dsn)
        env = signed_env(namespace.dsn, downstream.dsn)
        signer = RustThresholdSigner(private / "signers")
        policy = ThresholdApprovalPolicy(
            group_public_key=bytes.fromhex(signer.enroll()),
            policy_version=POLICY_VERSION,
            key_epoch=KEY_EPOCH,
            max_lifetime_seconds=3600,
        )
        app = app_for(
            env, namespace.dsn, threshold_verifier=ThresholdApprovalVerifier(policy=policy)
        )
        try:
            cases = _cases(env, signer, app, namespace.dsn, downstream.dsn)
        finally:
            app._executor.shutdown()

        with psycopg.connect(namespace.dsn) as conn:
            budget = [
                [int(value) for value in row]
                for row in conn.execute(
                    "SELECT depth, amount_reserved, amount_settled, calls_reserved, calls_settled "
                    "FROM ag_grants ORDER BY depth"
                ).fetchall()
            ]
            approvals = conn.execute("SELECT count(*) FROM ag_threshold_approvals").fetchone()[0]
            operations = conn.execute("SELECT count(*) FROM ag_operations").fetchone()[0]
        with psycopg.connect(downstream.dsn) as conn:
            orders = conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0]
        passed = all(case["passed"] for case in cases)
    finally:
        if downstream is not None:
            drop_downstream_database(namespace.base_dsn, downstream)
        release_namespace(namespace)
        shutil.rmtree(private, ignore_errors=True)
        resources_remaining = _remaining(namespace, downstream, private)

    result = {
        "demo": "threshold-gateway-purchase",
        "run_id": run_id,
        "profile": "AG-GUARD-THRESHOLD-APPROVAL-1",
        "passed": passed,
        "cases": cases,
        "operations": operations,
        "approvals": approvals,
        "orders": orders,
        "budget": budget,
        "resources_remaining": resources_remaining,
        "limitations": [
            "same-host teaching deployment; trusted dealer and one OS user",
            "FROST-Ed25519 group approval is not an SM2 signature",
            "no independent organization isolation; not production ready",
            "no x402 payment path",
        ],
    }
    (outdir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return (0 if passed else 1), result


def _remaining(namespace, downstream, private) -> list[str]:
    """Verify this run left no owned schema/database/signer material."""
    remaining = []
    with psycopg.connect(namespace.base_dsn, autocommit=True) as conn:
        if (
            conn.execute("SELECT to_regnamespace(%s)", (namespace.schema,)).fetchone()[0]
            is not None
        ):
            remaining.append("isolated_schema")
        if (
            downstream is not None
            and conn.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (downstream.name,)
            ).fetchone()
            is not None
        ):
            remaining.append("downstream_database")
    if private.exists():
        remaining.append("signer_material")
    return remaining


def _cases(env, signer, app, dsn, downstream_dsn):
    cases: list[dict] = []

    def record(name, passed, http_status=None, code=None, **extra):
        entry = {"name": name, "passed": bool(passed)}
        if http_status is not None:
            entry["http_status"] = int(http_status)
        if code is not None:
            entry["code"] = code
        entry.update(extra)
        cases.append(entry)

    # 1. missing approval is rejected before any ledger work
    bundle = env.bundle("demo-missing")
    status, body, _ = send(app, dsn, bundle, None)
    record(
        "missing-approval",
        status == 401 and code_of(body) == "APPROVAL_REQUIRED",
        status,
        code_of(body),
    )

    # 2. one-of-three and duplicate participants are refused by the real signer
    _, action = _action(env, signer, "demo-refusal", "action-demo-refusal")
    one = signer.sign_refused(action, ("signer-1",))
    duplicate = signer.sign_refused(action, ("signer-1", "signer-1"))
    record(
        "insufficient-and-duplicate",
        one.returncode != 0 and duplicate.returncode != 0,
        extra={"one_returncode": one.returncode, "duplicate_returncode": duplicate.returncode},
    )

    # 3. a fake 64-byte signature is rejected by the gateway
    fake = b"\x07" * 64
    status, body, _ = send(app, dsn, env.bundle("demo-refusal"), signer.header_for(action, fake))
    record(
        "fake-signature",
        status == 401 and code_of(body) == "INVALID_SIGNATURE",
        status,
        code_of(body),
    )

    # 4. valid approval creates exactly one order; a retry stays idempotent
    bundle, action = _action(env, signer, "demo-valid", "action-demo-valid")
    header = signer.header_for(action, signer.sign(action))
    status, accepted, _ = send(app, dsn, bundle, header)
    valid = status == 202
    operation_id = accepted.get("operation_id") if isinstance(accepted, dict) else None
    if valid:
        valid = env.service.run_operation(operation_id).status == "SUCCEEDED"
    retry_status, retry_body, _ = send(app, dsn, env.bundle("demo-valid"), header)
    retry = retry_status == 202 and retry_body.get("operation_id") == operation_id
    with psycopg.connect(downstream_dsn) as conn:
        orders_after_valid = conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0]
    record(
        "valid-approval-one-order",
        valid and retry and orders_after_valid == 1,
        status,
        code_of(accepted) if not valid else None,
        retry_http_status=retry_status,
        orders=orders_after_valid,
    )

    # 5. tampered amount is signed but never matches the trusted operation cost
    bundle, action = _action(env, signer, "demo-valid", "action-demo-tampered", amount_fen=1)
    status, body, _ = send(app, dsn, bundle, signer.header_for(action, signer.sign(action)))
    record(
        "tampered-amount",
        status == 409 and code_of(body) == "APPROVAL_MISMATCH",
        status,
        code_of(body),
    )

    # 6. ancestor revocation refuses a freshly signed approval
    with psycopg.connect(dsn) as conn:
        mid = conn.execute(
            "SELECT grant_id FROM ag_grants WHERE depth=1 AND task_id=%s", (TASK,)
        ).fetchone()[0]
        grant_tenant_admin(conn, tenant_id=TENANT, subject="demo-admin")
    GrantRevocationService(dsn).revoke_grant(
        tenant_id=TENANT, grant_id=mid, authenticated_admin_subject="demo-admin"
    )
    bundle, action = _action(env, signer, "demo-revoked", "action-demo-revoked", amount_fen=100)
    status, body, _ = send(app, dsn, bundle, signer.header_for(action, signer.sign(action)))
    record("revoked-ancestor", status == 403 and code_of(body) == "REVOKED", status, code_of(body))

    return cases


def _action(env, signer, key, action_id, **overrides):
    bundle = env.bundle(key)
    action = approval_action(
        bundle,
        action_id=action_id,
        policy_version=POLICY_VERSION,
        key_epoch=KEY_EPOCH,
        expires_at=int(time.time()) + 300,
        **overrides,
    )
    return bundle, action


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=None)
    args = parser.parse_args(argv)
    dsn = (
        args.dsn
        or os.environ.get("AGENT_GUARD_THRESHOLD_DEMO_DSN")
        or os.environ.get("AGENT_GUARD_TEST_DATABASE_URL")
    )
    if not dsn:
        print(
            "需要本机演示数据库：设置 AGENT_GUARD_THRESHOLD_DEMO_DSN 或 "
            "AGENT_GUARD_TEST_DATABASE_URL（例如 compose.test.yaml 的测试库）。",
            file=sys.stderr,
        )
        return 2
    run_id = None
    try:
        code, result = run_demo(dsn)
        run_id = result["run_id"]
    except BaseException as exc:  # noqa: BLE001 - never leak DSN/raw exception text
        print(f"门限采购演示未完成：{type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"门限采购固定演示：{'全部用例符合预期' if code == 0 else '存在未符合预期的用例'}")
    for case in result["cases"]:
        print(
            f"  {case['name']}: {'通过' if case['passed'] else '未通过'}"
            + (f"（HTTP {case['http_status']}" if "http_status" in case else "")
            + (f" {case['code']}" if case.get("code") else "")
            + ("）" if "http_status" in case else "")
        )
    print(
        f"  操作 {result['operations']}，批准绑定 {result['approvals']}，"
        f"下游订单 {result['orders']}，资源剩余 {len(result['resources_remaining'])}"
    )
    print("结果目录：", DEMO_ROOT / run_id)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
