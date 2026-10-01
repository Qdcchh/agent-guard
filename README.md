# Agent Guard

**面向企业多智能体协同的可验证授权与可信执行系统。**

目标：即使智能体输出受恶意内容影响，工具执行仍受明确的任务授权、委托边界和共享预算约束，并提供可独立验证的执行证据。

> 当前状态：A1 执行账本已通过阶段验收，详见 [A1最终验收记录](tasks/A1-review-r4.md)。B 的 SM2/SM3、严格编码、GM-MVP-1 Compact JWS，以及部分只读 DID 解析、令牌/AG-Proof 静态验权、委托收窄策略、授权码和 Token Exchange 请求预校验、ID Token/PKCE 校验代码已实现；一次性授权码与唯一根签发、事务性子委托签发、任务所有者撤销已有进程内数据库实现，并新增严格 Basic 认证的 `/oauth/token` 请求适配层（尚未挂载 HTTP 监听器）。独立第二实现互验尚未完成。OAuth/OIDC 登录和同意 HTTP 服务端点、企业登记管理、管理员节点撤销与撤销 HTTP 接口、完整验权联调、HTTP 网关、执行/结算/恢复、签名回执、审计检查点与前端仍未实现。局部测试通过不代表端到端安全目标已实现。

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

当前设计统一采用 GM-MVP-1：OAuth/OIDC 流程、AS 统一签发、SM2/SM3、DID 绑定及私有 AGPoP 请求证明。规划采用 Python 3.11、FastAPI 网关、PostgreSQL、成熟密码/OAuth 库及 Docker Compose。基础密码 SDK 使用铜锁 Python SDK；签名格式、用户标识和编码规则见 [密码配置](docs/crypto-profile-v1.md)。标准向量已验证，独立第二实现互验与 AS 框架适配仍须完成。该国密 profile 不代表完整标准 OIDC/DPoP 互通。

代理不得持有下游管理凭据或可信状态库访问凭据。单仓库不意味着共享密钥、数据库权限或信任域。网关与下游之间不假定存在分布式事务。

## 4. 当前仓库结构

```text
AGENT.md                    AI 开发约束（详细）
AGENTS.md                   自动发现入口，指向 AGENT.md
docs/
  oauth-oidc-sm2-mvp.md      当前路线：术语、架构、A/B分工与HTTP/SDK接口
  security-model.md         威胁模型、事务、撤销、恢复及审计边界
  acceptance.md             初版/成熟版验收、性能实验及交付清单
  crypto-profile-v1.md      GM-MVP-1 SM2/SM3 与 JWS 线格式配置
src/agent_guard/
  contracts/encoding.py      严格 JSON、RFC 8785、base64url
  contracts/ledger.py        最小进程内契约（可信输入类型、错误码）
  crypto/                    SM2/SM3 与 Compact JWS 基础 SDK
  authorization/             严格claims、静态验权、ID Token与PKCE辅助函数
  identity/                  did:web受控解析与登记快照核对
  ledger/                    A1：迁移器、SQL存储、原子接受、可信初始化夹具
migrations/                  版本化 SQL 迁移（checksum 保护，勿改历史文件）
tests/                       SDK、U1输入边界、P1—P14集成与并发用例
compose.test.yaml            隔离测试 PostgreSQL（仅本地 127.0.0.1）
requirements*.lock           固定运行及开发依赖版本
.github/workflows/ci.yml     lint + unit + 迁移 + 真实 PostgreSQL 集成测试
```

后续按需增加 `authorization/`、`gateway/`、`tools/`、`agents/`、`audit/`、`benchmarks/`。不以空目录或占位接口充当实现。A1 的 `VerifiedInvocation` 是**可信进程内输入**，只能由未来 B 的验证器构造；不存在“已验权 JSON”直接入库的入口。

文档按上述顺序阅读。旧通用凭证协议与重复架构文档已移除，可通过Git历史查看；威胁模型和执行状态机已合并。Markdown是唯一文档源，PDF仅作本地导出，不入库且需自行重新生成。

## 5. 开发环境与验证

要求 Python 3.11+（CI 基准 3.11）、Git、Docker（仅测试数据库需要）。以下在仓库根目录执行（macOS/Linux）：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
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

# 3) 执行版本化迁移（幂等，可重复运行）
python -m agent_guard.ledger.migrate

# 4) 集成测试（真实 PostgreSQL；缺库时报错退出，不会静默跳过）
python -m pytest tests/integration

# 5) 清理（无需删 volume；tmpfs 数据随容器消失）
docker compose -f compose.test.yaml down
```

迁移 `004_authorization_code.sql`、`005_delegation.sql` 与 `006_task_revocation.sql` 为增量升级：新增一次性授权码、签名令牌快照、受控证明、不可变委托关系及任务撤销记录；不修改已有账本行或旧迁移。已有数据库也用同一迁移命令升级；迁移器校验历史 checksum，失败会回滚，不提供自动降级。部署前备份并限制 AS 表的数据库角色访问；005 将证明 JWS 保存在受限表中，证据保留/访问控制须由部署负责。`AuthorizationCodeService` 是仅供可信登录/同意服务调用的进程内组件，不能把外部提交的 `user_id` 或 `ApprovedAuthorization` JSON 直接交给它；`TokenExchangeService` 须由已完成 Basic 客户端认证的服务端调用；`TaskRevocationService` 的 subject 必须来自已验证且有 CSRF 防护的用户会话，不能直接使用外部自报值。完整 HTTP 流程尚未实现。

`TokenEndpoint` 是可挂载到 TLS HTTP 服务的纯请求适配层：输入原始表单与逐条 Authorization/AG-Proof 头，使用部署时私有注入的高熵客户端密钥 SHA-256 摘要进行 Basic 校验，调用上述两个事务服务，并返回 OAuth 形状、禁止缓存的响应。它不自行提供监听器、客户端密钥初始化、用户登录或同意页面；HTTP 服务必须保留重复头信息并限制请求大小，不能从用户提交值推导 tenant、redirect 或密钥。可用 `python -m pytest tests/test_token_endpoint.py tests/integration/test_token_endpoint.py` 验证接口与真实数据库签发（后者需要测试 PostgreSQL）。

`IntrospectionService` 与 `IntrospectionEndpoint` 提供网关专用的令牌状态查询：独立 Basic 服务凭据、严格表单、签名及不可变快照验证，并在同一锁序下复查祖先撤销、期限和密钥状态。无效令牌只返回 `active:false`，可信数据库不可用则失败关闭。它们同样尚未挂载 TLS HTTP 监听器；`active:true` 是查询时点快照，绝非网关执行许可，网关仍需在接受事务内重新验权。运行 `python -m pytest tests/test_introspection_endpoint.py tests/integration/test_introspection.py` 验证接口及数据库路径。

迁移 `007_admin_grant_revocation.sql` 新增租户管理员登记及不可变节点撤销记录，不改写现有授权或账本数据。可信部署流程须先在 `ag_tenant_admins` 登记真实管理员，并限制该表的写权限；外部请求不得自行登记。`GrantRevocationService` 只接受已验证且有 CSRF 防护的管理员会话传入的主体，并在数据库中再次核验管理员资格，按根至叶锁序撤销目标子树；它尚未挂载管理 HTTP 接口。升级前备份，用相同迁移命令增量升级；旧数据库若缺少 007 将不能调用该服务。集成测试为 `python -m pytest tests/integration/test_grant_revocation_service.py`。

`verify_receipt_bundle` 提供 B 侧 `AG-EVIDENCE-1` 单笔未锚定证据的离线验证：可信 AS、网关及历史 holder 公钥和登记快照必须独立配置，不能从证据包自带字段建立信任。验证器复核签名、授权祖先收窄、AG-Proof、调用与结果摘要，以及根至叶 RESERVE/SETTLE/RELEASE 的金额和次数变动；只有四种账本 delta 允许有界负整数。运行 `python -m pytest tests/test_receipt.py`。当前没有 A 侧证据导出和独立审计检查点，因此不宣称任务历史完整、防回滚或 M9 整项通过。

明天演示 B 侧授权闭环时，在设置隔离测试数据库连接变量 `AGENT_GUARD_TEST_DATABASE_URL` 后运行 `python -m tests.demo_b_flow`。该命令在本轮独占 schema 内生成合成身份和密钥，展示根签发、两级委托、盗取令牌拒绝、幂等重试与撤销拒绝，结束后仅清理自己创建的 schema；不打印原始令牌或密钥。它不包含浏览器登录、真实 HTTP 监听、网关订单执行或独立审计锚定，不可据此声称 M1—M13 全部通过。

测试专用凭据是显式的 test-only 值，只作用于本机 127.0.0.1 的一次性容器，不得用于任何部署；生产/演示凭据由部署时独立注入。变量优先级如实说明：迁移器 `python -m agent_guard.ledger.migrate` 先读 `AGENT_GUARD_DATABASE_URL`（未来服务/正式库预留），未设置时回退 `AGENT_GUARD_TEST_DATABASE_URL`；pytest 集成测试入口只读取 `AGENT_GUARD_TEST_DATABASE_URL`，不会触碰 `AGENT_GUARD_DATABASE_URL` 指向的库。测试会在目标库内创建本轮独占 schema（`ag_test_run_*`，含所有权标记），清库只作用于该 schema；迁移用的 scratch 库为随机名且仅清理自建资源。

Windows 可使用 `.venv\Scripts\Activate.ps1` 激活环境。`.env.example` 仅提供未来配置约定，不包含可用凭据。`requirements.lock` 与 `requirements-dev.lock` 固定当前运行和开发依赖版本。禁止提交 `.env`、私钥、token、数据库快照及敏感日志；`artifacts/` 下的本地测试日志不入库。

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
