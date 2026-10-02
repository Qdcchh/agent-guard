# Agent Guard

**面向企业多智能体协同的可验证授权与可信执行系统。**

目标：即使智能体输出受恶意内容影响，工具执行仍受明确的任务授权、委托边界和共享预算约束，并提供可独立验证的执行证据。

> 当前状态：A1 执行账本已实现并通过阶段验收（版本化迁移、原子接受、共享预算、抗重放、业务幂等、撤销/时效复核、根生命周期防护、并发与回滚用例均跑在真实 PostgreSQL 上）。2026-09-30 本地正式套件 146 项及独立探针 5 项通过，条件与边界见 [A1最终验收记录](tasks/A1-review-r4.md)。A2.1-core 执行/恢复核心（004 迁移、可信资源报价、四工具严格参数、独立事务域模拟下游、执行/结算/释放/UNKNOWN 恢复、租约与待签 outbox）已实施，等待独立验收；完整 A2 仍为 PARTIAL。**真实验签/HTTP 网关/SM2/SM3/DID/签名回执/审计检查点与前端均尚未实现**；验收矩阵 M/SEC/CON 各项不得视为已通过。

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

首版固定 CNY 币种、商品与报价数据、收货对象；金额为整数分。采购金额由可信服务依据报价版本和数量计算，不信任代理申报金额。

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

当前设计统一采用 GM-MVP-1：OAuth/OIDC流程、AS统一签发、SM2/SM3、DID绑定及私有AGPoP请求证明。规划采用 Python 3.11、FastAPI网关、PostgreSQL、成熟密码/OAuth库及 Docker Compose；AS框架适配须先做可行性验证。当前只安装基础开发工具，密码库选型须先完成测试向量、签名格式、SM2 用户标识和互操作验证。该国密profile不是完整标准OIDC/DPoP互通声明。

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

后续按需增加 `crypto/`、`authorization/`、`gateway/`、`agents/`、`audit/`、`benchmarks/`。不以空目录或占位接口充当实现。`VerifiedInvocation` / `TrustedPermissionSnapshot` 是**可信进程内输入**，只能由未来 B 的验证器与可信初始化构造；不存在“已验权 JSON”直接入库的入口，也没有生产假验权开关。

文档按上述顺序阅读。旧通用凭证协议与重复架构文档已移除，可通过Git历史查看；威胁模型和执行状态机已合并。Markdown是唯一文档源，PDF仅作本地导出，不入库且需自行重新生成。

## 5. 开发环境与验证

要求 Python 3.11+（CI 基准 3.11）、Git、Docker（仅测试数据库需要）。以下在仓库根目录执行（macOS/Linux）：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]' -c constraints.txt
python -m ruff check .
python -m ruff format --check .
python -m pytest tests/unit tests/test_scaffold.py tests/test_docs.py
```

### A1 账本：数据库、迁移与集成测试

```bash
# 1) 启动隔离的测试 PostgreSQL（127.0.0.1:55432，数据在 tmpfs，无宿主 volume）
docker compose -f compose.test.yaml up -d --wait

# 2) 导出测试专用连接串（凭据仅用于本 compose 的测试容器；可注入自己的密码）
export AGENT_GUARD_TEST_PG_PASSWORD="${AGENT_GUARD_TEST_PG_PASSWORD:-agent-guard-test-only-pw}"
export AGENT_GUARD_TEST_DATABASE_URL="postgresql://agent_guard_test:${AGENT_GUARD_TEST_PG_PASSWORD}@127.0.0.1:55432/agent_guard_test"

# 3) 执行版本化迁移（幂等，可重复运行）
python -m agent_guard.ledger.migrate

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

下游认证只认独立的网关服务 secret（`AG_WORKER_SERVICE_SECRET` / `DownstreamPort(service_secret=...)`）；代理自身的凭据一律拒绝，认证失败不执行、不返回结果。**B 的真实验证器与签名尚未交付，服务装配不得用测试替身冒充生产验权**：`contracts/execution.py` 的可信类型只能由可信初始化/测试夹具构造，任何试图把“已验权 JSON”接进生产的路径都应失败关闭。回执 outbox 保持 `PENDING`、`receipt_jws` 为 NULL，直到 A2.3 用真实 SM2 签名。

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

从最新 `main` 创建短期任务分支，提交 PR，CI通过后Squash merge。队友PR须由CODEOWNERS指定的仓库负责人 `Qdcchh` 审核批准；负责人自己的PR免审批，但合并前仍须确认CI通过、分支最新且讨论解决。当前通过管理员豁免实现负责人的免审批，队友仅有Write权限；若未来增加其他管理员，该豁免同样适用，须重新审视权限策略。禁止强推或删除main。

修改前先阅读 [AGENT.md](AGENT.md)、[实施与接口](docs/oauth-oidc-sm2-mvp.md)、[安全模型](docs/security-model.md)和[验收矩阵](docs/acceptance.md)。设计文档不代表实现完成；选型和契约变更需先明确边界、更新测试与文档，再进入真实实现。
