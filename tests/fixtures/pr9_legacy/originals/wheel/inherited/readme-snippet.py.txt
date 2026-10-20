import os, subprocess, sys, time
import psycopg
from datetime import datetime, timedelta, timezone

from agent_guard.contracts.execution import (
    GrantConstraints, ToolId, TrustedPermissionSnapshot,
)
from agent_guard.contracts.ledger import VerifiedInvocation
from agent_guard.execution.service import ExecutionService
from agent_guard.ledger import apply_migrations, provisioning as prov
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.tools.catalog import (
    CatalogDelivery, CatalogDocument, CatalogQuote, CatalogQuoteLine,
    CatalogRecipient, CatalogRequest, CatalogTemplate, TrustedCatalog,
)
from agent_guard.tools.downstream import MockDownstream

GATEWAY_DSN = os.environ["AGENT_GUARD_TEST_DATABASE_URL"]
DOWNSTREAM_DSN = os.environ["AG_SMOKE_DOWNSTREAM_DSN"]
SERVICE_SECRET = os.environ.get("AG_SMOKE_SECRET", "smoke-only-service-secret")

with psycopg.connect(GATEWAY_DSN) as conn:            # 迁移
    print("migrations applied:", apply_migrations(conn))

# ---- 可信初始化：身份、根/中/叶授权（只由可信初始化创建，无自助注册入口）
with psycopg.connect(GATEWAY_DSN) as conn:
    with conn.transaction():
        for client, kid in (("agent-planner","kid-plan"),("agent-selector","kid-select"),
                            ("agent-executor","kid-exec")):
            prov.register_principal(conn, tenant_id="tenant-demo", client_id=client, kid=kid)
        now, later = datetime.now(tz=timezone.utc), datetime.now(tz=timezone.utc)+timedelta(days=1)
        prov.create_task_root(conn, tenant_id="tenant-demo", task_id="task-001",
            grant_id="grant-root", subject="user-demo-001",
            holder_client_id="agent-planner", holder_kid="kid-plan",
            amount_limit=100000, call_limit=10, not_before=now, expires_at=later)
        prov.create_child_grant(conn, parent_grant_id="grant-root", grant_id="grant-mid",
            holder_client_id="agent-selector", holder_kid="kid-select",
            amount_limit=80000, call_limit=8, not_before=now, expires_at=later)
        prov.create_child_grant(conn, parent_grant_id="grant-mid", grant_id="grant-leaf",
            holder_client_id="agent-executor", holder_kid="kid-exec",
            amount_limit=70000, call_limit=5, not_before=now, expires_at=later)

# ---- 可信合成资源与报价：只由可信初始化种子，不接受请求上传的成本
catalog = TrustedCatalog(
    requests=[CatalogRequest("req-001","tenant-demo","task-001")],
    documents=[CatalogDocument("doc-001","req-001")],
    quotes=[CatalogQuote("quote-001","1","supplier-001","req-001",
                         (CatalogQuoteLine("sku-001",1,70000),))],
    deliveries=[CatalogDelivery("office-001","tenant-demo","req-001")],
    templates=[CatalogTemplate("order-created")],
    recipients=[CatalogRecipient("user-demo-001")],
)
leaf = {"request_ids":("req-001",),"document_ids":("doc-001",),
        "quote_versions":("quote-001@1",),"skus":("sku-001",),
        "delivery_ids":("office-001",),"template_ids":("order-created",),
        "recipient_ids":("user-demo-001",),"max_quantity":2}
snapshot = TrustedPermissionSnapshot(
    grant_id="grant-leaf", root_id="grant-root", tenant_id="tenant-demo",
    task_id="task-001", subject="user-demo-001",
    scope=tuple(t.value for t in ToolId),
    chain=(GrantConstraints(**leaf),)*3,
    chain_grant_ids=("grant-root","grant-mid","grant-leaf"),   # 必须与 DB 路径逐节点一致
)

# ---- 下游 provision：独立数据库、独立连接/事务、独立服务 secret
downstream = MockDownstream(DOWNSTREAM_DSN, service_secret=SERVICE_SECRET,
    approved_suppliers=("supplier-001",), approved_recipients=("user-demo-001",),
    served_requests=("req-001",))
downstream.provision()
downstream.reset()

# ---- 接受一次操作：严格参数 + 分层授权 + 候选/报价 + A1 accept
service = ExecutionService(gateway_dsn=GATEWAY_DSN, ledger=ExecutionLedger(GATEWAY_DSN),
    catalog=catalog, downstream=downstream, downstream_secret=SERVICE_SECRET)
params = (b'{"request_id":"req-001","quote_id":"quote-001","quote_version":"1",'
          b'"items":[{"sku":"sku-001","quantity":1}],"delivery_id":"office-001"}')
now_s = int(time.time())
accepted = service.accept_invocation(VerifiedInvocation(
    subject="user-demo-001", tenant_id="tenant-demo", task_id="task-001",
    grant_id="grant-leaf", root_id="grant-root",
    holder_client_id="agent-executor", holder_kid="kid-exec",
    tool_id="procurement.order.create", tool_version="1",
    idempotency_key="smoke-order", canonical_params=params,
    token_exp=now_s+300, proof_iat=now_s, proof_exp=now_s+30, proof_jti="smoke-jti-1",
    token_digest="opaque-token-digest", proof_digest="opaque-proof-digest",
    intent_digest="opaque-intent-digest", evidence_ref="smoke-evidence",
    ancestor_ids=("grant-root","grant-mid")), snapshot)
print("accepted:", accepted.operation_id, accepted.status, accepted.cost.amount_fen)

# ---- worker：真实子进程；配置只读环境变量，stdout/stderr 不含 DSN/secret
env = {k: os.environ[k] for k in ("PATH","HOME","LANG","LC_ALL","TMPDIR") if k in os.environ}
env["PYTHONPATH"] = os.environ.get("PYTHONPATH","")
env.update(AG_WORKER_GATEWAY_DSN=GATEWAY_DSN, AG_WORKER_DOWNSTREAM_DSN=DOWNSTREAM_DSN,
    AG_WORKER_SERVICE_SECRET=SERVICE_SECRET, AG_WORKER_OPERATION_ID=accepted.operation_id,
    AG_WORKER_APPROVED_SUPPLIERS="supplier-001", AG_WORKER_APPROVED_RECIPIENTS="user-demo-001",
    AG_WORKER_SERVED_REQUESTS="req-001", AG_WORKER_OWNER_TOKEN="smoke-worker")
print(subprocess.run([sys.executable,"-m","agent_guard.execution.worker"], env=env,
                     capture_output=True, text=True, timeout=60).stdout.strip())
# 恢复/重复步骤：已终局的操作会被拒绝(ILLEGAL_TRANSITION)，不会重复结算或重复出回执
print(subprocess.run([sys.executable,"-m","agent_guard.execution.worker"], env=env,
                     capture_output=True, text=True, timeout=60).stderr.strip())
