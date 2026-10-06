# Agent Guard

**面向企业多智能体协同的可验证授权与可信执行系统。**

目标：即使智能体输出受恶意内容影响，工具执行仍受明确的任务授权、委托边界和共享预算约束，并提供可独立验证的执行证据。

本轮 B 补正已独立验收并通过 CI，经 [PR #6](https://github.com/Qdcchh/agent-guard/pull/6) 合并 main。67 项验收、60 项独立运行完成；见 [正式接受记录](tasks/workflow/runs/local-remediation-20261004/acceptance.md)及 [当前交接](tasks/workflow/context.md)。整体项目仍 **PARTIAL**：A2.2 已完成95项/88运行义务的独立验收，A2.3内部持续签名发布与真实HTTPS联合流程已完成完整119项/112运行义务独立复验并[正式接受](tasks/workflow/runs/A2.3-receipts-20261004/acceptance.md)，原r1否决保留为历史；A3独立锚定/导出/交付演示与实验未完成；旧无回执公钥配置保持PENDING兼容。阶段通过不代表绝对无缺陷。

`product-manifest.json` 保留 2026-10-03 原始交付的 186 项文件哈希；本轮文档已更新，该清单仅用于核对历史传输快照，不是当前工作树清单。旧云端内部报告与原始证据没有随此分支完整交付，不能把旧工作流 `state.json` 的 A2.1 `ACCEPTED` 当作 B 整合放行。

同学接续请读 [A3 完整交接](docs/A3-HANDOFF.md)：从 `codex/a2.2-integration` / [PR #7](https://github.com/Qdcchh/agent-guard/pull/7) 获取完整A2，逐段完成全部A3。本次暂不合并main；本机绑定/个人调度/私有原件不发布，历史证据访问边界见[说明](tasks/workflow/runs/A2.3-receipts-20261004/README.md)。

## 1. 项目目标

面向全国密码技术竞赛构建可运行、可测试、可复现的工程原型，于 **2026 年 10 月 20 日**前完成工程与材料。重点不是通用聊天平台，而是智能体到业务副作用之间的可信执行边界。

1. 基于 SM2/SM3 的授权凭证、规范编码与请求持有者证明。
2. 根授权、至少两级子委托、至少三个代理身份；逐级权限只能收窄。
3. 对根及全部适用祖先实施共享额度控制，避免并发分支累计超额。
4. 请求抗重放、业务幂等、明确的撤销边界和异常恢复。
5. 授权链、请求、执行效果、签名回执与独立检查点的证据关联。
6. 可脱离大模型运行的确定性安全测试和公开条件下的效率实验。

以上均为开发目标，不是已完成能力或普适安全保证。

## 2. 场景与范围

### 主场景：企业协同采购

用户确认采购申请、资源范围、固定收货对象和预算。统筹、选品、执行三个代理通过两级委托完成任务。并行分支共享根预算，恶意报价内容不应扩大实际执行权限。

| 工具标识（v1） | 功能 |
| --- | --- |
| `procurement.request.read` | 查询授权范围内的采购申请 |
| `procurement.document.read` | 读取申请关联的商品与报价文档 |
| `procurement.order.create` | 按可信报价创建模拟订单 |
| `notification.template.send` | 向批准接收方发送固定模板模拟通知 |

首版固定 CNY 币种、商品与报价数据、收货对象；金额为整数分。订单参数、持久报价快照和结果共用最多 256 项边界，超过该上限在接受前拒绝。采购金额由可信服务依据报价版本和数量计算，不信任代理申报金额。

退款仅作为主线稳定后的可选轻量适配。不会接入真实支付、训练大模型、自研密码算法、构建完整采购平台或引入区块链。模型接口可替换，无模型 API 时使用确定性代理进行复现。

## 3. 架构与技术路线

```text
用户登录并确认任务 → OAuth/OIDC AS统一签发（SM2）
                              ↓
统筹代理 → AS交换子令牌 → 选品代理 → AS交换 → 执行代理
                              ↓ Access Token + AGPoP（DID/登记密钥绑定）
                         统一执行网关
                    验权 / 抗重放 / 动态状态检查
                              ↓
                 PostgreSQL 预算预留与操作记录
                              ↓
                 模拟业务服务（独立幂等状态）
                              ↓
                 结算 / 签名回执 / 独立审计锚定
```

当前设计统一采用 GM-MVP-1：OAuth/OIDC流程、AS统一签发、SM2/SM3、DID绑定及私有AGPoP请求证明。规划采用 Python 3.11、FastAPI网关、PostgreSQL、成熟密码/OAuth库及 Docker Compose；AS框架适配须先做可行性验证。当前使用固定 tongsuopy 1.0.1 的 SM2/SM3 与原生 ASGI/uvicorn 装配；固定向量及 OpenSSL 互验属于现有测试，维护与跨平台限制见 [密码配置](docs/crypto-profile-v1.md)。该国密profile不是完整标准OIDC/DPoP互通声明。

代理不得持有下游管理凭据或可信状态库访问凭据。单仓库不意味着共享密钥、数据库权限或信任域。网关与下游之间不假定存在分布式事务。

## 4. 当前仓库结构

```text
AGENT.md                    AI 开发约束（详细）
AGENTS.md                   自动发现入口，指向 AGENT.md
docs/
  oauth-oidc-sm2-mvp.md      当前路线：术语、架构、A/B分工与HTTP/SDK接口
  security-model.md         威胁模型、事务、撤销、恢复及审计边界
  acceptance.md             初版/成熟版验收、性能实验及交付清单
src/agent_guard/
  contracts/ledger.py        最小进程内契约（可信输入类型、错误码）
  contracts/execution.py     A2 可信类型（工具参数、报价快照、租约、待签回执）
  ledger/                    A1：迁移器、SQL存储、原子接受、可信初始化夹具
  tools/                     严格四工具参数、可信资源/报价目录、模拟下游（独立库）
  execution/                 A2.1：接受流程、租约、终局账本、outbox、真实 worker
migrations/                  版本化 SQL 迁移（checksum 保护，勿改历史文件）
tests/                       骨架/文档检查、U1输入边界、P1—P14集成与并发用例
tests/unit/test_tool_validation.py         四工具/权限快照严格拒绝（纯进程内）
tests/integration/test_execution_*.py      A2.1 执行/恢复/租约/报价/并发
tests/integration/test_downstream.py       下游幂等、意图冲突、服务认证
tests/integration/test_a2_migrations.py    004 升级保全与直接 SQL 防绕过
compose.test.yaml            A1 隔离测试 PostgreSQL（仅本地 127.0.0.1）
compose.a2.test.yaml         A2 测试 PostgreSQL（独立 Compose project）
constraints.txt              运行依赖可复现约束
.github/workflows/ci.yml     lint + unit + 迁移 + 真实 PostgreSQL 集成测试
```

已增加 `crypto/`、`authorization/`、`identity/`、`evidence/`、`server/`、`gateway/`及`execution/query.py`。其余网关、代理、审计与实验能力按后续范围实施，不以空目录充当实现。`VerifiedInvocation` / `TrustedPermissionSnapshot` 是**可信进程内输入**，由真实 B 验证适配器或可信初始化构造；不存在“已验权 JSON”直接入库的入口，也没有生产假验权开关。

文档按上述顺序阅读。旧通用凭证协议与重复架构文档已移除，可通过Git历史查看；威胁模型和执行状态机已合并。Markdown是唯一文档源，PDF仅作本地导出，不入库且需自行重新生成。

## 5. 开发环境与验证

要求 Python 3.11+（CI 基准 3.11）、Git、Docker（仅测试数据库需要）。以下在仓库根目录执行（macOS/Linux）：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
python -m pip check
python -m ruff check .
python -m ruff format --check .
python -m pytest tests --ignore=tests/integration
```

### A1 账本：数据库、迁移与集成测试

```bash
# 1) 启动隔离的测试 PostgreSQL（127.0.0.1:55432，数据在 tmpfs，无宿主 volume）
docker compose -f compose.test.yaml up -d --wait

# 2) 导出测试专用连接串（凭据仅用于本 compose 的测试容器；可注入自己的密码）
export AGENT_GUARD_TEST_PG_PASSWORD="${AGENT_GUARD_TEST_PG_PASSWORD:-agent-guard-test-only-pw}"
export AGENT_GUARD_TEST_DATABASE_URL="postgresql://agent_guard_test:${AGENT_GUARD_TEST_PG_PASSWORD}@127.0.0.1:55432/agent_guard_test"

# 3) 设置下述 test-only 拒绝探针角色，再执行完整 bundle 迁移
python -m agent_guard.ledger.migrate --bundle

# 4) 集成测试（真实 PostgreSQL；缺库时报错退出，不会静默跳过）
python -m pytest tests/integration

# 5) 清理（无需删 volume；tmpfs 数据随容器消失）
docker compose -f compose.test.yaml down
```

测试专用凭据是显式的 test-only 值，只作用于本机 127.0.0.1 的一次性容器，不得用于任何部署；生产/演示凭据由部署时独立注入。变量优先级如实说明：迁移器 `python -m agent_guard.ledger.migrate` 先读 `AGENT_GUARD_DATABASE_URL`（未来服务/正式库预留），未设置时回退 `AGENT_GUARD_TEST_DATABASE_URL`；pytest 集成测试入口只读取 `AGENT_GUARD_TEST_DATABASE_URL`，不会触碰 `AGENT_GUARD_DATABASE_URL` 指向的库。测试会在目标库内创建本轮独占 schema（`ag_test_run_*`，含所有权标记），清库只作用于该 schema；迁移用的 scratch 库为随机名且仅清理自建资源。

Windows 可使用 `.venv\Scripts\Activate.ps1` 激活环境。`.env.example` 仅提供未来配置约定，不包含可用凭据。开发工具使用固定版本，账本运行依赖（psycopg）经 `constraints.txt` 锁定。禁止提交 `.env`、私钥、token、数据库快照及敏感日志；`artifacts/` 下的本地测试日志不入库。

### A2.1 执行核心：可执行的初始化、下游、接受、worker、恢复与清理

A2.1 的执行/恢复测试需要 **两个相互独立的数据库**：网关账本库和模拟下游库（下游是独立事务域，绝不同库同事务）。下面的命令在仓库根目录逐条执行即可走完全过程；**每一步都使用自己独占的实例/命名空间，只清理自建资源**，并且全程不设置、不打印普通部署 DSN。

```bash
# 0) 普通部署 DSN 必须先清除，只使用本轮 TEST DSN（不打印任何连接串）
unset AGENT_GUARD_DATABASE_URL
export AGENT_GUARD_TEST_DATABASE_URL="postgresql://agent_guard_a21c:<test-only-pw>@127.0.0.1:55435/agent_guard_a21c_gw"
export AG_SMOKE_DOWNSTREAM_DSN="postgresql://agent_guard_a21c:<test-only-pw>@127.0.0.1:55435/agent_guard_a21c_downstream"
export PYTHONPATH="$PWD/src"

# 1) 自建独占 PostgreSQL 实例（名称/端口换成自己的唯一值；只清理这一个）
docker run -d --name agent-guard-a21c-pg \
  --label owner=<your-run-id> --label purpose=a21-core-tests \
  -p 127.0.0.1:55435:5432 --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_USER=agent_guard_a21c -e POSTGRES_PASSWORD=<test-only-pw> \
  -e POSTGRES_DB=agent_guard_a21c_gw postgres:16-alpine
docker exec agent-guard-a21c-pg psql -U agent_guard_a21c -d postgres \
  -c "CREATE DATABASE agent_guard_a21c_downstream"

# 2) 迁移：001—006 幂等。CLI-first 在空库上打印全部版本；
#    之后再运行任何迁移入口都必须是 no-op（输出 already up to date / []）
python -m agent_guard.ledger.migrate     # -> applied: 001, 002, 003, 004, 005, 006
python -m agent_guard.ledger.migrate     # -> already up to date
```

下面这段 Python 就是可信初始化、下游 provision、一次操作接受、worker 与恢复的完整可执行程序（已按原文逐字实跑通过，输出见下）。初始化是一次性的：重复运行前请换用空库，否则 `register_principal` 会因主键重复拒绝，这正是“根与身份不重建”的表现。

```python
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
```

预期输出（与实跑一致）。**迁移行取决于是否已经 CLI-first 跑过**：

```text
# 若上面第 2) 步已用 CLI 迁移过空库，程序里的 apply_migrations 是 no-op：
migrations applied: []
accepted: <operation_id> RESERVED 70000
{"action": "SETTLE", ..., "status": "SUCCEEDED"}
worker failed: ILLEGAL_TRANSITION
```

```text
# 若跳过第 2) 步、直接让程序迁移一个全新空库，则打印全部版本：
migrations applied: ['001', '002', '003', '004', '005', '006']
```

```bash
# 3) 跑完整测试（缺库报错退出，不静默 skip）；下游随机名库由测试会话自建自删
python -m pytest tests/integration

# 4) 清理：只删自建实例/库；不要对共享 project 执行 down/prune
docker rm -f agent-guard-a21c-pg
```

下游认证只认独立的网关服务 secret（`AG_WORKER_SERVICE_SECRET` / `DownstreamPort(service_secret=...)`）；代理自身的凭据一律拒绝，认证失败不执行、不返回结果。**上面的 A2.1 示例是可信初始化驱动的底层执行演示，不是浏览器到采购的端到端链路**。真实 B 入口为 `InvocationVerifier.verify_bundle` 加 `VerifiedExecution.accept`；不能用测试回调或“已验权 JSON”绕过该适配器。回执 outbox 保持 `PENDING`、`receipt_jws` 为 NULL，此底层示例没有配置A2.3回执信任；新内部发布流程见下文。

### 完整 B→A 测试、角色与 bundle 升级

完整测试需 PostgreSQL 16、OpenSSL CLI 和仅属于本轮的测试数据库角色/资源。
测试角色需要在自有数据库创建 schema、在同一实例创建随机测试数据库；生产数据库
不适合作为测试目标。下面 SQL **只由隔离测试实例的管理员执行一次**，把
`agent_guard_test` 替换为本轮测试连接角色；不得授予受保护业务表访问权限：

```sql
CREATE ROLE br_s1_untrusted NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOINHERIT NOREPLICATION NOBYPASSRLS;
GRANT br_s1_untrusted TO agent_guard_test
  WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
```

证据拒绝测试先成功 `SET LOCAL ROLE` 并断言 `current_user`，再要求保护表读取
真实返回 `42501`；角色切换失败不会算作通过。CI 在一次性 PostgreSQL 容器里
创建相同角色，不触及生产授权。

```bash
unset AGENT_GUARD_DATABASE_URL
python -m agent_guard.ledger.migrate --bundle
python -m agent_guard.ledger.migrate --bundle  # 第二次无写入
python -m pytest tests --ignore=tests/integration
python -m pytest tests/integration
python -m tests.demo_b_flow
```

`--bundle` 保留原 A001–006/B004–009 的固定字节与所有旧 registry 行，识别合法
common/A/B 前缀并在单一事务中追加命名空间 lineage 和证据表。旧 A 入口保留
六版本兼容视图；尚未升级的 B 历史不能伪装成 A004–006。既有 v2 sidecar
缺少原始 14 个完成条目中的任一条时拒绝，不重建已丢失证据。目录、校验和、
provenance、触发器损坏亦拒绝。先备份并验证恢复；没有无损降级承诺。

`tests.demo_b_flow` 是合成数据的授权演示，真实数据库/SM2 签名支持根、两级
委托、盗用拒绝及撤销；不冒充完整采购 HTTP 演示。四工具真实签名接入与恢复
在 `tests/integration/test_verified_execution.py` 验证。公开HTTP网关和动态operation查询已完成A2.2独立验收；候选内部连续发布见A2.3流程，独立审计导出待A3.2。

### 私有配置与开发 HTTPS

`init` 只创建**不存在**的目录，保持一个目录描述符贯穿 AS key、三个 agent
key、config 与 secrets 六次写入。新目录0700、文件0600；读取只接受0400/0600。
不修复现有目录权限、不覆盖已有文件，不支持安全原语的平台失败关闭。
最终私有目录必须由当前有效 UID 拥有且模式0700。各级祖先只信任 root 或当前
UID；group/other 可写祖先必须带 sticky 位，且选中子项须由当前 UID 拥有、
不可 group/other 写。禁止路径链接，不允许直接在 /tmp 放私有文件。
该边界不抵御 root/当前 UID 被攻陷，也不承诺函数返回后的路径永不改变。
普通 umask022/077 都可用；umask0777 在写入秘密之前失败，可能留下空目录。
中途失败可能留下私有的部分文件；自行确认归属后清理，不自动删除可能被替换
的路径。CLI 拒绝以固定非零错误退出，不输出 traceback 或秘密。

```bash
# RUN_PRIVATE_PARENT 必须是自己拥有的安全0700父目录；RUN_CONFIG_DIR 尚不存在。
export RUN_CONFIG_DIR="$RUN_PRIVATE_PARENT/as-demo"
(umask 022; python -m agent_guard.server init --out "$RUN_CONFIG_DIR")
python -m agent_guard.server check --config "$RUN_CONFIG_DIR/config.json"
# 从自己的测试资源注入数据库连接串，不打印到日志。
export AGENT_GUARD_DATABASE_URL="$AGENT_GUARD_TEST_DATABASE_URL"
python -m agent_guard.server run --config "$RUN_CONFIG_DIR/config.json" \
  --host 127.0.0.1 --port 8443 --ssl-certfile "$TLS_CERT_FILE" --ssl-keyfile "$TLS_KEY_FILE"
# 本终端 Ctrl-C 后确认进程退出；客户端须指定测试CA并校验对应DNS/SAN。
unset AGENT_GUARD_DATABASE_URL
```

生成的密钥/口令仅用于合成开发数据，不可提交或当作部署身份。factory 使用
`did_documents` 在 build_app 时一次序列化为私有不可变字节快照；嵌套列表、
整份文档和原 mapping 的后续修改均不能改变已构建 runtime，新建 runtime 才读取新配置。
`check` 与 `run` 使用相同组件装配校验，check 不连接数据库或启动服务。factory 不执行
实时 DID 网络获取。单独的 `IdentityResolver` 默认 fetch 路径支持受批准
`did:web` 的 HTTPS；集成测试用受控测试 DNS、合成 CA 和实际 TLS 服务器验证
CA/hostname、重定向、目标、用途、controller、SPKI 与停用/轮换拒绝。
这两种配置不能混同，测试 DNS 也不是部署 DNS 安全保证。

离线回执验证按所有祖先 token 的 iat/nbf/exp 与 proof 的原 +5 秒未来偏差和排他
exp 边界求一个共同可能的历史接受时刻，且不晚于已签 receipt iat。终局/恢复可
晚于 token/proof 到期。该格式没有独立签入精确接受时间，结论仍依赖受信 GW
终局声明；不会改写原 token/proof/receipt 时间，也不放宽在线验权。

自定义 legacy SQL 继续使用历史通用换行归一化 checksum，已有 CRLF 登记重复
执行保持原行（含 applied_at）；独立 raw digest 防止执行前换字节。canonical bundle
仍校验原 SQL 字节。迁移 CLI 显式 connect_timeout=5，失败固定脱敏诊断和非零退出。

### A2.2 网关配置与 HTTPS 启动

本段已完成95项/88运行义务的独立验收，见[接受记录](tasks/workflow/runs/A2.2-integration-20261004/acceptance.md)。网关只提供`POST /v1/invocations`与
`POST /v1/operations/query`，使用规范中的固定HTTPS签名端点。
Authorization须为`AGPoP <access-token>`，另带`AG-Proof`，body为严格JSON。
invoke只原子接受并返回202，不自动调用下游；可信内部worker单独推进。
query使用同一授权链的当前权限、当前key/撤销/时效及新proof，零业务金额/次数。
未知或非本人operation统一403；终局前result为null，未配置receipt_keys的旧query仅兼容已有PENDING且回执null；持久READY需要可信回执公钥，否则query返回503；配置独立回执公钥后返回经过同事务原件/17claims验签的当前PENDING或READY，READY含原持久JWS。

以下步骤可独立执行；所有路径/DSN由操作者自己的资源注入，不依赖artifacts。
`init`生成合成公开信任与私有下游secret，AS/代理私钥不会写入网关目录。
正式调用须把config里的issuer、AS公钥、历史身份登记、当前DID快照和catalog
替换为批准的可信来源；AS及代理私钥由各自独立信任域保管。

```bash
export RUN_GATEWAY_CONFIG_DIR="$RUN_PRIVATE_PARENT/gateway-demo"
(umask 022; python -m agent_guard.gateway init --out "$RUN_GATEWAY_CONFIG_DIR")
python -m agent_guard.gateway check --config "$RUN_GATEWAY_CONFIG_DIR/config.json"
# 使用独立的网关/下游数据库；管理员显式完成bundle/下游迁移和可信初始化。
# factory/check/run不会reset、provision或隐式迁移数据库。
export AG_GATEWAY_DATABASE_URL="$RUN_GATEWAY_DSN"
export AG_GATEWAY_DOWNSTREAM_DATABASE_URL="$RUN_DOWNSTREAM_DSN"
python -m agent_guard.gateway run --config "$RUN_GATEWAY_CONFIG_DIR/config.json" \
  --host 127.0.0.1 --port 8444 --ssl-certfile "$TLS_CERT_FILE" --ssl-keyfile "$TLS_KEY_FILE"
# Ctrl-C并等待退出；客户端以自己的可信CA校验TLS及gateway.agent-guard.test SAN。
unset AG_GATEWAY_DATABASE_URL AG_GATEWAY_DOWNSTREAM_DATABASE_URL
```

没有默认DB或普通部署DSN回退，TLS证书/密钥必需，配置/私有文件失败关闭。
请求最多65536字节、最多100个头且头累计65536字节；只接受JSON UTF-8。
响应JSON沿用GM-MVP-1规范编码的65536字节上限，包含转义后的完整序列化大小；坏可信结果或超限
返回503 TRUSTED_STATE_UNAVAILABLE。查询在提交前校验该上限，失败不消耗proof。
同步DB工作在有界线程池执行，超时后容量直到真实线程退出才释放。
已接受事务可在HTTP超时后完成，客户端用新proof和原业务幂等键重试。
响应含服务生成的32位hex request_id，禁止缓存；401只声明AGPoP挑战。
此私有GM-MVP-1协议不声明标准DPoP兼容。公开HTTP只保留两条POST路径；内部签名发布使用独立receipt_worker CLI，独立锚定仍留A3。

### A2.3 内部回执发布与真实 HTTPS 联合演示

Use a current-owned 0700 parent with trusted ancestors. The old gateway config and its downstream secret remain private regular 0400/0600 files. `init` reads only public gateway configuration; it checks secret-reference metadata and never opens or copies the secret contents. It creates one new 0700 directory, three 0600 files, an independent CSPRNG SM2 key, and a gateway public copy preserving historical receipt keys. Existing paths or signing kids fail closed. An extreme umask may safely leave an empty inaccessible leaf; use a new target after operator cleanup.

```sh
python -m agent_guard.gateway.receipt_worker init --gateway-config "$PRIVATE/gateway/config.json" --out "$PRIVATE/receipt" --signing-kid gw-receipt-1
python -m agent_guard.gateway.receipt_worker check --config "$PRIVATE/receipt/config.json"
AG_RECEIPT_DATABASE_URL="$OWNED_TEST_DSN" python -m agent_guard.gateway.receipt_worker run --config "$PRIVATE/receipt/config.json"
```

Use `$PRIVATE/receipt/gateway-public.json` as the gateway's public configuration copy. This contains no signing private key. Receipt worker config contains public historical AS/holder/GW trust and the receipt signer path, with exact bounded integer settings. `check` uses the same loader and builder offline. `run` only accepts `AG_RECEIPT_DATABASE_URL`, never provisions or migrates a database, and publishes already committed terminal outbox rows. Poll/batch and SQL waits are bounded; corrupt rows stay PENDING while keyset rotation reaches later rows. Restart reads committed READY JWS/signed_at unchanged. `run --once` handles one page; `run --operation-id ID` internally returns the persistent publication for one operation. No public signing/recovery HTTP route is added. UNANCHORED receipts verify association and signature; full audit completeness remains A3.

真实合成联合演示需要两条自有可丢弃TEST DSN：网关与下游分属独立数据库/事务。演示生成临时AS/GW/三holder密钥、CA和SAN证书，运行真实登录同意、PKCE、两次exchange、四工具、内部发布、当前query与独立SDK验签；退出回收临时配置和进程，结果为UNANCHORED。

```bash
AGENT_GUARD_TEST_DATABASE_URL="$RUN_GATEWAY_TEST_DSN" AGENT_GUARD_TEST_DOWNSTREAM_DATABASE_URL="$RUN_DOWNSTREAM_TEST_DSN" python -m tools.a2_receipt_demo
```

本轮source/noneditable-wheel完整独立复验覆盖119项/112运行义务，主控核证后[正式接受](tasks/workflow/runs/A2.3-receipts-20261004/acceptance.md)；原r1 NOT_ACCEPTED及所有失败保留，局部演示或自查不构成接受。真实HTTPS联合演示展示协议与业务链；部署、三代理编排及独立审计导出仍属A3。

### 非 editable wheel 复现

构建后端固定 `setuptools==80.9.0`，仅构建 wheel。先从官方 PyPI 核对版本、
许可与 SHA256；以下为 uv 前端的隔离 PEP517 复现示例，v1实际构建和安装
命令以实施报告为准。示例中的目录均应为自有独占的新目录：

```bash
uv build --wheel --python python3.11 --out-dir "$RUN_WHEEL_DIR" .
uv venv --python python3.11 "$RUN_WHEEL_VENV"
uv pip install --python "$RUN_WHEEL_VENV/bin/python" -r requirements-dev.lock
uv pip install --python "$RUN_WHEEL_VENV/bin/python" --no-deps "$RUN_WHEEL_DIR"/agent_guard-*.whl
uv pip check --python "$RUN_WHEEL_VENV/bin/python"
```

以下是源码模式复现示例；v1交付的实际命令与普通非editable安装方式以实施报告为准。
源码模式在新建锁定venv安装wheel提供发行元数据，再显式选择 `src`。这是源码测试，不计入非 editable wheel 的隔离验证：

```bash
uv venv --python python3.11 "$RUN_SOURCE_VENV"
uv pip install --python "$RUN_SOURCE_VENV/bin/python" -r requirements-dev.lock
uv pip install --python "$RUN_SOURCE_VENV/bin/python" --no-deps "$RUN_WHEEL_DIR"/agent_guard-*.whl
uv pip check --python "$RUN_SOURCE_VENV/bin/python"
export PYTHONPATH="$PWD/src"
"$RUN_SOURCE_VENV/bin/python" -m pytest tests
unset PYTHONPATH
```

实际复核将精确测试副本放到源码树外，移除 `PYTHONPATH` 和 editable hooks，
该目录不含 `src` 或复制的 `agent_guard` 包，父进程及每个 Python 子进程都须
证明从安装的 wheel 导入。wheel 包含全部 common/A/B/lineage SQL；可通过
`AGENT_GUARD_MIGRATIONS_DIR` 指定可信完整迁移目录，不从任意 cwd 猜目录。
具体构建输入、依赖元数据、wheel成员/哈希、实跑命令和结果见 [本轮实施报告](tasks/workflow/runs/local-remediation-20261004/implementation-r1.md)。

setuptools 80.9.0 的官方元数据列出 CVE-2026-59890：macOS 非 ASCII 文件名
规范化差异可能绕过 sdist 的 MANIFEST 排除。本轮在 Linux 从明确干净输入构建
wheel 并检查全部成员，不构建/发布 sdist；这不是 macOS sdist 风险已修复的声明。
密码版本不升级，Tongsuo/BabaSSL 8.3.2 的维护不确定性见密码配置。

## 6. 实施计划

| 日期（2026） | 交付与验收 |
| --- | --- |
| 9/23—9/25 | 协议、威胁模型、状态机、密码库验证及数据库设计 |
| 9/26—9/30 | 三代理、两级委托、四工具完整链路；正常执行、越权拒绝、并发不超额、重试不重复 |
| 10/1—10/7 | 祖先额度、撤销竞态、故障恢复、独立检查点与离线验证 |
| 10/8—10/13 | 安全与故障矩阵、对照实验、性能开销拆分；10/13 功能冻结 |
| 10/14—10/17 | 干净环境复现、工程文档、图表、演示材料 |
| 10/18—10/20 | 缺陷修复、最终验收、固定版本与提交包 |
| 10/21—10/23 | 提交缓冲，不安排关键研发 |

A 负责可信执行与集成；B 负责密码授权及审计核心；C 在后期负责材料整理与复现验收。每位开发者负责自身模块的测试与技术文档。详细内部排班不进入仓库。

## 7. 验收与研究重点

- 每个适用额度节点满足 `settled + reserved <= limit`，通过数据库断言检查。
- 同一业务键不产生重复订单；同键不同意图或授权链必须拒绝。
- 未知结果不直接释放预留；恢复不得产生新的业务意图。
- 撤销提交先于操作接受时拒绝；已接受操作允许按约定恢复，不承诺回滚。
- 独立验证器检查已锚定证据的签名、顺序与关联，并报告检测盲区。
- 目标测试规模：50 并发客户端、至少 10,000 次模拟调用。最终报告真实结果，不将目标写作实测。

研究重点为层级共享预算与可恢复执行的组合设计，以及授权至效果的证据关联。需与静态凭据、常规权限控制及已有可验证授权方案比较；消融版明确标注。不得仅凭国密替换、增加签名或模型数量声称创新。

完整验收清单见 [acceptance.md](docs/acceptance.md)。

## 8. 协作入口

OAuth/OIDC、SM2/SM3、Agent间委托与DID的唯一当前设计见 [实施及接口契约](docs/oauth-oidc-sm2-mvp.md)。不再并行维护父holder直接签发子凭证的旧路线。老师是否要求实改liboauth2本体仍需确认，该问题影响实现选型，不允许绕开既定安全契约。

当前A3从完整A2协作分支 `codex/a2.2-integration` 或已接受前段创建短期分支，PR暂以该分支为base；A2合并后再核真实main并调整base。按已授权范围提交PR，必需CI与实际审核条件满足后才可申请后续合并；本次暂不合并。不得自批、强推或删除 main；管理员审核豁免必须另有明确授权，不因作者是负责人而自动使用。PR #6 已获本次具体豁免并合并，后续 PR 不自动继承；当前角色、授权和交付见 [现行工作流约定](tasks/workflow/current-policy.md)。

修改前先阅读 [AGENT.md](AGENT.md)、[实施与接口](docs/oauth-oidc-sm2-mvp.md)、[安全模型](docs/security-model.md)和[验收矩阵](docs/acceptance.md)。设计文档不代表实现完成；选型和契约变更需先明确边界、更新测试与文档，再进入真实实现。


A2.3补正候选在真实签名/READY前复用原接受事实校验：对不可变报价执行精确总额、数量/原请求及cost currency/calls检查，并逐事件核对历史验真的完整root→leaf路径和四种delta。两列quote/result相互一致不能替代上述约束。校验读取均先于query最终DB时刻，不引入当前报价、下游结果或当前撤销/到期条件；合法零价及迟延终局仍可历史发布。失败保留PENDING/null及原ID/iat，当前query失败回滚proof/link，仅允许原契约的隔离STAGED证据。

容量域分列：本轮独立依据实际validator、q≥1/p≥0/Σq*p≤MAX_SAFE及标识符长度推导，canonical producer订单公开响应包含上界为48187＋2724＋124＝51035字节；兼容真实有效非canonical raw JWS仍可到16384，公开包含上界为48187＋16384＋124＝64695。两者均非共同可达合法最大值。正price的digits(q)＋digits(p)≤17，zero price≤16＋1；旧58168为较松Cartesian/标识符公式，仅历史比较。九个各≤65536组件的outer保守上界589964；1MiB/+1纯codec点并非保留组件profile的合法SDK bundle。组件64KiB、JWS16KiB、公开65536和外壳1MiB守卫不变；真实256 SKU、原边界/故障/回滚探针及范围分类见[完整独立review-r2](tasks/workflow/runs/A2.3-receipts-20261004/review-r2.md)。本候选完整A2已[正式接受](tasks/workflow/runs/A2.3-receipts-20261004/acceptance.md)，原r1否决保留。

最新结论：[正式接受](tasks/workflow/runs/A2.3-receipts-20261004/acceptance.md)与[完整独立review-r2](tasks/workflow/runs/A2.3-receipts-20261004/review-r2.md)，原[r1否决](tasks/workflow/runs/A2.3-receipts-20261004/review-r1.md)及[实施自查](tasks/workflow/runs/A2.3-receipts-20261004/implementation-remediation-r2.md)保留为历史。本轮依据[真人恢复](tasks/workflow/runs/A2.3-receipts-20261004/user-resume-sol-20261006.md)完成完整复核与接受；最新真人要求协作发布并交接全部A3。当前协作版本通过PR #7交付，暂不合并，A3未实施；CI/审核以PR当前实际head为准。
