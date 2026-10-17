"""Fixed local x402 exact/EVM/EIP-3009 purchase demo over the real gateway.

This is a *local teaching demo*: it uses the real signed AS root->leaf chain,
the real SM2/AGPoP + FROST threshold gateway, the real PostgreSQL ledger, the
real x402 HTTP resource server, a real local Anvil chain with the real
FiatToken bytecode and real EIP-3009 signatures. It never pretends to be a
production deployment, never touches real funds and writes sanitized JSON
evidence only.

Every case runs in its own isolated schema/database so that quote uniqueness
and CNY budgets stay exactly as strict as in production; only the local test
chain is shared. The script exits 0 only when every expected case happened and
prints the result directory for the local demo page.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import uuid
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agent_guard.execution.service import ExecutionService  # noqa: E402
from agent_guard.ledger.lineage import apply_bundle_migrations  # noqa: E402
from agent_guard.ledger.service import ExecutionLedger  # noqa: E402
from agent_guard.threshold.contracts import ThresholdApprovalPolicy  # noqa: E402
from agent_guard.threshold.verifier import ThresholdApprovalVerifier  # noqa: E402
from agent_guard.x402 import state, wire  # noqa: E402
from agent_guard.x402.chain import AUTHORIZATION_USED_TOPIC, ChainReader  # noqa: E402
from agent_guard.x402.client import X402HttpClient  # noqa: E402
from agent_guard.x402.config import X402Deployment  # noqa: E402
from agent_guard.x402.contracts import PaymentOffer, build_intent  # noqa: E402
from agent_guard.x402.facilitator import LocalFacilitator  # noqa: E402
from agent_guard.x402.gate import PaymentGatedDownstream  # noqa: E402
from agent_guard.x402.localchain import AnvilService, bootstrap_token  # noqa: E402
from agent_guard.x402.resource import X402ResourceServer  # noqa: E402
from agent_guard.x402.signer import X402Payer, create_nonce  # noqa: E402
from tests.fixtures.execution import DOWNSTREAM_SECRET, build_catalog  # noqa: E402
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
OFFER_AMOUNT = "250000"
BUDGET_LIMIT = "100000000"
APPROVAL_LIFETIME = 900
DEMO_ROOT = Path(
    os.environ.get("AGENT_GUARD_X402_DEMO_ROOT") or (REPO / "artifacts" / "x402-gateway-demo-live")
)


@dataclass
class DemoChain:
    """One shared local test chain with the real FiatToken deployment."""

    rpc_url: str
    chain_id: int
    admin_key: str
    payer_key: str
    payer: X402Payer
    merchant: str
    token: str


class CaseWorld:
    """One isolated schema/database plus one fixed x402 deployment."""

    def __init__(
        self,
        *,
        chain: DemoChain,
        reader: ChainReader,
        facilitator: LocalFacilitator,
        base_dsn: str,
        private_root: Path,
        label: str,
        quote_id: str,
        offer_amount: str,
        payer_address: str,
        budget_limit: str | None = None,
    ):
        self.label = label
        self.payer_address = payer_address
        self._base_dsn = base_dsn
        self._private_root = private_root
        self.namespace = acquire_namespace(base_dsn)
        self.downstream = None
        self.app = None
        self.server = None
        try:
            with psycopg.connect(self.namespace.dsn) as conn:
                apply_bundle_migrations(conn)
            self.downstream = create_downstream_database(self.namespace.base_dsn)
            self.env = signed_env(self.namespace.dsn, self.downstream.dsn, leaf_ttl=180)
            self.private = private_root / label
            self.signer = RustThresholdSigner(self.private)
            self.policy = ThresholdApprovalPolicy(
                group_public_key=bytes.fromhex(self.signer.enroll()),
                policy_version=POLICY_VERSION,
                key_epoch=KEY_EPOCH,
                max_lifetime_seconds=3600,
            )
            self.port = _free_port()
            self.deployment = X402Deployment(
                gateway_dsn=self.namespace.dsn,
                rpc_url=chain.rpc_url,
                chain_id=chain.chain_id,
                token=chain.token,
                asset_name="USD Coin",
                asset_version="2",
                pay_to=chain.merchant,
                resource_url=(f"http://127.0.0.1:{self.port}/v1/x402/resource/order-create"),
                status_url=f"http://127.0.0.1:{self.port}/v1/x402/resource/order-status",
                offer=PaymentOffer(
                    quote_id=quote_id,
                    quote_version="1",
                    asset_amount=offer_amount,
                ),
                max_timeout_seconds=3600,
                payer_key=chain.payer_key,
                facilitator_key=chain.admin_key,
            )
            self.reader = reader
            self.client = X402HttpClient(
                resource_url=self.deployment.resource_url, timeout_seconds=15
            )
            self.gate = PaymentGatedDownstream(
                deployment=self.deployment,
                downstream=self.env.downstream,
                downstream_secret=DOWNSTREAM_SECRET,
                client=self.client,
                payer=chain.payer,
                reader=reader,
            )
            self.service = ExecutionService(
                gateway_dsn=self.namespace.dsn,
                ledger=ExecutionLedger(self.namespace.dsn),
                catalog=build_catalog(TENANT, TASK),
                downstream=self.gate,
                downstream_secret=DOWNSTREAM_SECRET,
            )
            self.verifier = ThresholdApprovalVerifier(policy=self.policy)
            self.server = X402ResourceServer(
                deployment=self.deployment,
                facilitator=facilitator,
                reader=reader,
                downstream=self.env.downstream,
                downstream_secret=DOWNSTREAM_SECRET,
            )
            self.app = app_for(
                self.env,
                self.namespace.dsn,
                threshold_verifier=self.verifier,
                payment=self.deployment,
            )
            state.seed_asset_budget(
                self.namespace.dsn,
                tenant_id=TENANT,
                task_id=TASK,
                asset=chain.token,
                chain_id=chain.chain_id,
                amount_limit=budget_limit or BUDGET_LIMIT,
            )
        except BaseException:
            self.close()
            raise

    # ------------------------------------------------------------- helpers

    def accept_paid(self, key, *, deployment=None, app=None, **overrides):
        bundle = self.env.bundle(key)
        dep = deployment or self.deployment
        invocation = bundle.invocation
        expires_at = int(time.time()) + APPROVAL_LIFETIME
        intent = build_intent(
            profile=dep.profile,
            tenant_id=invocation.tenant_id,
            task_id=invocation.task_id,
            grant_id=invocation.grant_id,
            root_grant_id=invocation.root_id,
            tool_id=invocation.tool_id,
            idempotency_key=invocation.idempotency_key,
            quote_id=dep.offer.quote_id,
            quote_version=dep.offer.quote_version,
            amount_fen=70_000,
            valid_before=expires_at,
        )
        action_kwargs = dict(
            action_id=f"action-{key}",
            policy_version=self.policy.policy_version,
            key_epoch=self.policy.key_epoch,
            expires_at=expires_at,
            version=3,
            payment_digest=intent.digest,
        )
        action_kwargs.update(overrides)
        action = approval_action(bundle, **action_kwargs)
        header = self.signer.header_for(action, self.signer.sign(action))
        token, proof, body = raw_material(self.namespace.dsn, bundle)
        status, accepted, _headers = request(
            app if app is not None else self.app,
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
            # Debug seam: re-drive the endpoint directly so the real exception
            # is visible instead of the public INTERNAL_ERROR envelope.
            (app if app is not None else self.app)._endpoint.handle(
                "/v1/invocations", token.decode(), proof.decode(), body, approval=header
            )
        return bundle, intent, status, accepted

    def alternate_app(self, **overrides) -> tuple:
        """A second real gateway app with a modified deployment profile."""
        deployment = replace(self.deployment, **overrides)
        app = app_for(
            self.env,
            self.namespace.dsn,
            threshold_verifier=self.verifier,
            payment=deployment,
        )
        return deployment, app

    def authorization_events(self, nonce: str) -> int:
        topic = "0x" + self.payer_address.lower().removeprefix("0x").rjust(64, "0")
        logs = self.reader.web3.eth.get_logs(
            {
                "address": self.reader.web3.to_checksum_address(self.deployment.token),
                "fromBlock": 0,
                "toBlock": "latest",
                "topics": [AUTHORIZATION_USED_TOPIC, topic, nonce],
            }
        )
        return len(logs)

    def confirm_settled(self, record, amount: str = OFFER_AMOUNT) -> bool:
        deadline = time.time() + 30
        while time.time() < deadline:
            confirmation = self.reader.confirm(
                payer=self.payer_address.lower(),
                pay_to=self.deployment.pay_to,
                amount=amount,
                nonce=record.nonce,
            )
            if confirmation.settled:
                return bool(confirmation.transfer_matched)
            time.sleep(0.5)
        return False

    def budget(self):
        with psycopg.connect(self.namespace.dsn) as conn:
            return conn.execute(
                "SELECT amount_reserved, amount_settled FROM ag_payment_budgets "
                "WHERE tenant_id=%s AND task_id=%s AND asset=%s AND chain_id=%s",
                (TENANT, TASK, self.deployment.token, self.deployment.chain_id),
            ).fetchone()

    def budget_row(self):
        with psycopg.connect(self.namespace.dsn) as conn:
            return [
                str(value)
                for value in conn.execute(
                    "SELECT amount_limit, amount_reserved, amount_settled "
                    "FROM ag_payment_budgets WHERE tenant_id=%s AND task_id=%s",
                    (TENANT, TASK),
                ).fetchone()
            ]

    def payment_row(self, operation_id: str):
        with psycopg.connect(self.namespace.dsn) as conn:
            return conn.execute(
                "SELECT status, nonce, tx_hash FROM ag_payment_states WHERE operation_id=%s",
                (operation_id,),
            ).fetchone()

    def counts(self) -> dict:
        with psycopg.connect(self.namespace.dsn) as conn:
            operations = conn.execute("SELECT count(*) FROM ag_operations").fetchone()[0]
            approvals = conn.execute("SELECT count(*) FROM ag_threshold_approvals").fetchone()[0]
            payments = conn.execute("SELECT count(*) FROM ag_payment_states").fetchone()[0]
            transactions = conn.execute(
                "SELECT count(*) FROM ag_payment_states "
                "WHERE status='SETTLED' AND tx_hash IS NOT NULL"
            ).fetchone()[0]
        with psycopg.connect(self.downstream.dsn) as conn:
            orders = conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0]
        return {
            "operations": operations,
            "approvals": approvals,
            "orders": orders,
            "payments": payments,
            "transactions": transactions,
        }

    def close(self) -> list[str]:
        if self.server is not None:
            self.server.stop()
        if self.app is not None:
            executor = getattr(self.app, "_executor", None)
            if executor is not None:
                executor.shutdown()
        if self.downstream is not None:
            drop_downstream_database(self.namespace.base_dsn, self.downstream)
        release_namespace(self.namespace)
        shutil.rmtree(getattr(self, "private", self._private_root / self.label), ignore_errors=True)
        remaining = []
        with psycopg.connect(self.namespace.base_dsn, autocommit=True) as conn:
            if (
                conn.execute("SELECT to_regnamespace(%s)", (self.namespace.schema,)).fetchone()[0]
                is not None
            ):
                remaining.append(f"schema:{self.label}")
            if (
                self.downstream is not None
                and conn.execute(
                    "SELECT 1 FROM pg_database WHERE datname=%s", (self.downstream.name,)
                ).fetchone()
                is not None
            ):
                remaining.append(f"database:{self.label}")
        if (self._private_root / self.label).exists():
            remaining.append(f"signer:{self.label}")
        self.downstream = None
        self.app = None
        self.server = None
        return remaining


def _record(cases, name, passed, http_status=None, code=None, **extra):
    entry = {"name": name, "passed": bool(passed)}
    if http_status is not None:
        entry["http_status"] = int(http_status)
    if code is not None:
        entry["code"] = code
    entry.update(extra)
    cases.append(entry)


def _code_of(body):
    error = body.get("error") if isinstance(body, dict) else None
    return error.get("code") if isinstance(error, dict) else None


def case_paid(world: CaseWorld, cases: list[dict]) -> None:
    _b, _i, status, accepted = world.accept_paid("demo-paid")
    valid = status == 202 and accepted.get("status") == "RESERVED"
    operation_id = accepted.get("operation_id") if isinstance(accepted, dict) else None
    settled = confirmed = replay = False
    if valid:
        valid = world.service.run_operation(operation_id).status == "SUCCEEDED"
    if valid:
        row = world.payment_row(operation_id)
        settled = row is not None and row[0] == "SETTLED"
        if settled:
            stored = state.load_payment(world.namespace.dsn, operation_id)
            confirmed = world.confirm_settled(stored) and (
                world.authorization_events(stored.nonce) == 1
            )
            material = state.load_authorization_material(world.namespace.dsn, operation_id)
            if confirmed and material is not None:
                _authorization, payload, _sha = material
                response = world.client.order_create(
                    operation_id=operation_id,
                    payment_header=wire.encode_header(payload),
                )
                replay = response.status == 200 and (
                    json.loads(response.body).get("already_existed") is True
                )
    _record(
        cases,
        "paid-flow-settles-once",
        valid and settled and confirmed,
        status,
        _code_of(accepted) if not valid else None,
        orders=world.counts()["orders"],
    )
    _record(cases, "replay-does-not-pay-twice", valid and replay)


def case_v2(world: CaseWorld, cases: list[dict]) -> None:
    _b, _i, status, body = world.accept_paid("demo-v2", version=2)
    _record(
        cases,
        "v2-approval-refused",
        status == 401 and _code_of(body) == "APPROVAL_REQUIRED",
        status,
        _code_of(body),
    )


def case_over_budget(world: CaseWorld, cases: list[dict]) -> None:
    over, app = world.alternate_app(
        offer=PaymentOffer(
            quote_id="quote-001",
            quote_version="1",
            asset_amount=str(int(BUDGET_LIMIT) + 1),
        )
    )
    try:
        before = world.budget()
        _b, _i, status, body = world.accept_paid("demo-over-budget", deployment=over, app=app)
        after = world.budget()
        _record(
            cases,
            "over-budget-refused",
            status == 422 and _code_of(body) == "PAYMENT_BUDGET_EXCEEDED" and after == before,
            status,
            _code_of(body),
        )
    finally:
        app._executor.shutdown()


def case_unknown_recovery(world: CaseWorld, cases: list[dict]) -> None:
    before_reserved, before_settled = world.budget()
    _b, _i, status, accepted = world.accept_paid("demo-recovery")
    ok = status == 202
    nonce = None
    if ok:
        operation_id = accepted["operation_id"]
        world.server.stop()
        stored = state.load_payment(world.namespace.dsn, operation_id)
        signed = _sign_payment_intent(world, stored)
        state.authorize(
            world.namespace.dsn,
            operation_id=operation_id,
            nonce=signed["nonce"],
            authorization_json=json.dumps(
                signed["authorization"], ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8"),
            payload_json=signed["document"],
            payload_sha256=signed["payload_sha256"],
        )
        unknown = world.service.run_operation(operation_id, owner_token="demo-recovery-worker")
        row = world.payment_row(operation_id)
        ok = (
            unknown.status == "UNKNOWN"
            and row is not None
            and row[0] == "UNKNOWN"
            and row[1] == signed["nonce"]
            and world.budget() == (before_reserved + Decimal(OFFER_AMOUNT), before_settled)
        )
        if ok:
            world.server.__enter__()
            recovered = world.service.run_operation(
                operation_id, owner_token="demo-recovery-worker"
            )
            final = world.payment_row(operation_id)
            nonce = signed["nonce"]
            ok = (
                recovered.status == "SUCCEEDED"
                and final is not None
                and final[0] == "SETTLED"
                and final[1] == signed["nonce"]
                and world.authorization_events(signed["nonce"]) == 1
            )
            if ok:
                stored = state.load_payment(world.namespace.dsn, operation_id)
                ok = world.confirm_settled(stored)
    _record(
        cases,
        "unknown-recovery-same-nonce",
        ok and nonce is not None,
        status,
        _code_of(accepted) if status != 202 else None,
        same_nonce=nonce is not None,
    )


def _sign_payment_intent(world: CaseWorld, stored) -> dict:
    """Sign one real EIP-3009 authorization for the stored payment intent."""
    return X402Payer(world.deployment.payer_key).create_payload(
        profile=world.deployment.profile,
        intent=stored.intent,
        nonce=create_nonce(),
    )


def case_tamper(world: CaseWorld, cases: list[dict]) -> None:
    _b, _i, status, accepted = world.accept_paid("demo-tamper")
    ok = False
    if status == 202:
        operation_id = accepted["operation_id"]
        stored = state.load_payment(world.namespace.dsn, operation_id)
        attacker = X402Payer("0x" + os.urandom(32).hex())
        forged = attacker.create_payload(
            profile=world.deployment.profile,
            intent=stored.intent,
            nonce=create_nonce(),
        )
        probe = world.client.order_create(
            operation_id=operation_id,
            payment_header=wire.encode_header(forged["document"]),
        )
        ok = probe.status == 409 and b"PAYMENT_NOT_PERSISTED" in probe.body
    _record(
        cases,
        "forged-payment-refused",
        ok,
        status,
        _code_of(accepted) if status != 202 else None,
    )


CASES = (
    ("paid", OFFER_AMOUNT, case_paid),
    ("v2", OFFER_AMOUNT, case_v2),
    ("over-budget", str(int(BUDGET_LIMIT) + 1), case_over_budget),
    ("recovery", OFFER_AMOUNT, case_unknown_recovery),
    ("tamper", OFFER_AMOUNT, case_tamper),
)


def run_demo(dsn: str) -> tuple[int, dict]:
    run_id = str(uuid.uuid4())
    outdir = DEMO_ROOT / run_id
    private_root = outdir / "private"
    outdir.mkdir(parents=True, mode=0o700)
    private_root.mkdir(mode=0o700)
    anvil = None
    cases: list[dict] = []
    totals = {"operations": 0, "approvals": 0, "orders": 0, "payments": 0, "transactions": 0}
    budgets: list[list[str]] = []
    remaining: list[str] = []
    limitations = [
        "local test chain and test token only; no real asset or production network",
        "same-host single-OS-user teaching setup; not commercially usable",
        "chain signature is EIP-712/EIP-3009, not SM2; SM2 remains the gateway protocol",
        "synthetic pre-funded test tokens; no CNY or fiat asset moves anywhere",
        "not a full-project acceptance; only this fixed x402 demo is exercised",
    ]
    try:
        anvil = AnvilService()
        anvil.start()
        payer_key = "0x" + os.urandom(32).hex()
        chain = DemoChain(
            rpc_url=anvil.rpc_url,
            chain_id=anvil.chain_id,
            admin_key="0x" + os.urandom(32).hex(),
            payer_key=payer_key,
            payer=X402Payer(payer_key),
            merchant="0x" + os.urandom(20).hex(),
            token="",
        )
        chain.token = bootstrap_token(
            rpc_url=chain.rpc_url,
            admin_key=chain.admin_key,
            payer_address=chain.payer.address,
            token_name="USD Coin",
            token_symbol="USDC",
            decimals=6,
            mint_amount=10_000_000,
        ).lower()
        reader = ChainReader(chain.rpc_url, chain_id=chain.chain_id, token_address=chain.token)
        facilitator = LocalFacilitator(
            rpc_url=chain.rpc_url,
            private_key=chain.admin_key,
            network=f"eip155:{chain.chain_id}",
            confirmation_timeout_seconds=30.0,
        )
        for label, offer_amount, case in CASES:
            world = CaseWorld(
                chain=chain,
                reader=reader,
                facilitator=facilitator,
                base_dsn=dsn,
                private_root=private_root,
                label=label,
                quote_id="quote-001",
                offer_amount=offer_amount,
                payer_address=chain.payer.address,
            )
            try:
                world.server.__enter__()
                try:
                    case(world, cases)
                finally:
                    world.server.stop()
                counts = world.counts()
                for key, value in counts.items():
                    totals[key] += value
                budgets.append([label] + world.budget_row())
            finally:
                remaining.extend(world.close())
    finally:
        if anvil is not None:
            anvil.stop()
        shutil.rmtree(private_root, ignore_errors=True)
        if private_root.exists():
            remaining.append("signer_material")
        if anvil is not None and getattr(anvil, "_process", None) is not None:
            remaining.append("anvil_process")
    passed = bool(cases) and all(case["passed"] for case in cases) and not remaining
    result = {
        "demo": "x402-gateway-purchase",
        "run_id": run_id,
        "profile": "x402-v2-exact-evm-eip3009-local",
        "passed": passed,
        "cases": cases,
        "operations": totals["operations"],
        "approvals": totals["approvals"],
        "orders": totals["orders"],
        "payments": totals["payments"],
        "transactions": totals["transactions"],
        "asset_budgets": budgets,
        "resources_remaining": remaining,
        "limitations": limitations,
    }
    (outdir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return (0 if passed else 1), result


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=None)
    args = parser.parse_args(argv)
    dsn = (
        args.dsn
        or os.environ.get("AGENT_GUARD_X402_DEMO_DSN")
        or os.environ.get("AGENT_GUARD_TEST_DATABASE_URL")
    )
    if not dsn:
        print(
            "需要本机 x402 演示数据库：设置 AGENT_GUARD_X402_DEMO_DSN。",
            file=sys.stderr,
        )
        return 2
    run_id = None
    try:
        code, result = run_demo(dsn)
        run_id = result["run_id"]
    except BaseException as exc:  # noqa: BLE001 - never leak DSN/raw exception text
        print(f"x402 支付演示未完成：{type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"x402 支付固定演示：{'全部用例符合预期' if code == 0 else '存在未符合预期的用例'}")
    for case in result["cases"]:
        line = f"  {case['name']}: {'通过' if case['passed'] else '未通过'}"
        if "http_status" in case:
            line += f"（HTTP {case['http_status']}"
            line += f" {case['code']}）" if case.get("code") else "）"
        print(line)
    print(
        f"  操作 {result['operations']}，批准绑定 {result['approvals']}，"
        f"下游订单 {result['orders']}，支付 {result['payments']}，"
        f"真实结算交易 {result['transactions']}，"
        f"资源剩余 {len(result['resources_remaining'])}"
    )
    print("结果目录：", DEMO_ROOT / run_id)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
