# 工程交接：Agent Guard / A1账本验收收尾

> **最新结论（2026-09-30）：A1 ACCEPTED。** 最终独立复验 68 单元/骨架＋78 集成＋5 探针全部通过，F1—F5 关闭，见 [tasks/A1-review-r4.md](tasks/A1-review-r4.md)。用户已授权提交并推送当前 A1 分支，不合并 main。下方第三轮停点及正文均为历史快照；不要重复已完成的修复或验收。原测试库仍未应用 003；本地验证未覆盖 Python 3.11/远程 CI/wheel/真实网络故障，推送后需核对 CI。主代理继续以方向指导、委派与复核为主。

> **2026-09-30 接手后更新：** 以下正文是原交接快照。当前新增 003 根 DELETE 防护及正式根重建/非零七表升级回归，78 集成＋68 单元/骨架测试通过，reviewer 无阻断发现。最终验收仍待独立探针重跑与留痕。下一步以 [tasks/A1-review-r3.md](tasks/A1-review-r3.md) 为准，不再重复已完成的 003 修复。用户要求主代理主要指导、委派和复核，本轮到此停点；未提交/推送，原测试库未应用 003。

更新时间：2026-09-30。本文依据当前工作区、实际测试、Git/GitHub查询及本次对话整理。**当前交接只新增本文，不实现功能、不重构、不回退、不提交。**

## 1. 接手先看这五点

1. 仓库根目录：`/Users/qdcc/code/密码技术竞赛/agent-guard`。不要在父目录初始化另一个Git仓库。
2. 当前分支 `feat/a1-ledger`，HEAD为 `9796825a4aa44f3ca3d6911e1094c15e7803cc35`。A1实现和任务材料大量为**未跟踪文件**，默认git diff不包含它们；绝不能reset/clean覆盖。
3. 最新正式结论见 [tasks/A1-review-r2.md](tasks/A1-review-r2.md)：**A1 NOT_ACCEPTED / PARTIAL，仅F2根删除重建缺口仍阻断。** 不要只看实施agent报告正文里的历史“全部通过”。
4. 先修根授权行的DELETE保护（新增003迁移，不改001/002），并把非零账本升级验证纳入正式测试。不做A2或B的OAuth/密码工作。
5. 用户本轮明确禁止commit；目前没有对A1新获提交/推送授权。修复、记录、复验后等待用户指示，不绕过main保护。

## 2. 最终目标与用户约束

### 项目目标

三人参加全国密码技术竞赛，题目已改为 **“面向企业多智能体协同的可验证授权与可信执行系统”**。保留A1-26可验证授权/受控工具执行主线，以企业协同采购为完整主场景；轻量客服退款适配为可选项。目标是2026-10-20前完成可复现的成熟竞赛工程与材料，10-23截止，最后三天只做提交缓冲。原9-30初版是计划目标，当前实际仅到A1账本验收收尾，不能写成端到端初版已完成。

安全目标：根＋至少两级子委托、至少三代理、四工具、权限逐级收窄、SM2/SM3、持有者请求绑定、全部祖先累计额度、撤销、幂等/抗重放、异常恢复、独立证据验证。不以签名替换或模型数量单独声称创新。

### 人员与协作

- A是当前用户，负责可信执行、数据库、工具/代理集成、部署与后续演示。
- B熟悉Python和密码学，负责密码、AS/OP、授权、DID/验权SDK与审计核心。
- C任务较少且靠后，主要10月8日后做文档/图表/演示及复现，不承担前期关键依赖。对外内部规范只称A/B/C，语气客观，不评价成员忙闲或能力。
- A按阶段拆分：A1账本与接受；A2真实验权/HTTP网关、下游执行与恢复；A3端到端、部署、实验与演示。约“三分之一”是独立交付范围，不是代码行数或已完成整个项目的比例。
- 实施agent需持续写结构化记录，留脱敏命令、结果和文件清单，便于主代理验收节省token。不能仅凭子agent说成功就验收。

### 文件、表单和安全约束

- 父目录的 `01-协作规范与分工.md`、`02-自命题填写说明.md` **留在仓库外，不上传、不复制入仓库**；参考题目docx同样不上传。
- 自命题表单：内容/性能指标各≤400字符，所需知识/仪器各≤200；已压缩至361、350（含换行）、98、139字符。指标是拟验收目标，不是已有测量。性能编号改为普通正文“（1）”，不是Markdown有序列表，以便PDF复制。再次修改须重新计数。
- README必须包含目标、计划、真实完成边界；AGENT.md保留单数文件，AGENTS.md只是自动发现入口。
- 用户要求文档收敛，通用docs只保留三份；任务材料放tasks，不恢复多套冲突协议。PDF是本地导出，保留但不入库，可能已过期。
- 不提交真实私钥、token、业务数据、`.env`、数据库快照和敏感日志；artifacts为本地忽略目录。
- 不自研密码，不加跳过验权/永远成功开关，不把测试输入当密码证明。无真实支付；不要求GPU、模型训练或区块链。
- 测试必须真实PostgreSQL；不以SQLite或内存账本代替并发语义，缺库不得静默skip后宣称成功。不得为测试误清用户已有库或停止无关容器。

## 3. Git/GitHub状态（交接时已查询）

- 公开仓库：<https://github.com/Qdcchh/agent-guard>。最初私有，用户后来明确要求公开。
- origin为HTTPS：`https://github.com/Qdcchh/agent-guard.git`。已登录GitHub账号为Qdcchh；先前补过workflow scope，令牌只在凭据管理器，不写本文。
- 历史：`e762049` 初始化；`9796825` 文档收敛和OAuth国密设计。
- 文档PR #1：<https://github.com/Qdcchh/agent-guard/pull/1>，交接时仍 **OPEN / REVIEW_REQUIRED**，head=`docs/consolidate-gm-mvp`，base=`main`，没有mergedAt。该PR的原文档CI此前通过，**不等于A1的新版CI通过**。
- A1分支从该文档提交建立，尚无A1提交/远程分支。main仍不含未合并文档；别从旧main重新开工。后续文档PR若Squash合并，须在用户授权集成时处理基线，避免重复引入文档提交，不能现在擅自rebase/强推。
- main保护：1名非作者批准、checks通过且分支最新、讨论解决、管理员同样受限；禁止强推/删除；只允许Squash merge，合并后删任务分支。
- 队友 `wa-rui` 已邀请并在前次查询中确认Write权限，已请求其审核PR #1。不能用当前作者账号自批PR；另一个队友用户名未提供。

## 4. 已完成什么，尚未完成什么

### 已完成（实现，不只是规划）

- Python包骨架、基本lint/测试CI、项目与协议文档、内部申报/协作文档。
- A1同步psycopg进程内接口 `ExecutionLedger.accept(VerifiedInvocation, TrustedCost)`。
- 类型/格式检查、DB父子路径、统一锁序、锁后实际DB时间、subject/holder/key/撤销/有效期复核。
- 全路径预算和次数原子预留、DB proof唯一性、业务幂等、RESERVED操作、可信报价快照及首次/重试证据关联、RESERVE事件。
- 版本化SQL迁移器及001/002，禁止篡改已应用迁移checksum；002修复部分根约束和calls=1。
- 真实PostgreSQL集成、并发10轮、回滚/状态测试；测试隔离修复；CI已在工作区配置PostgreSQL服务，尚未上传运行。

### 当前进行位置

A1经历两次主代理验收。首轮F1—F5中，F1测试隔离、F3主体核对、F4每操作1次、F5有界连接已关闭。F2的唯一根索引和任务映射保护有效，但根授权行仍可同ID删后重建。最近一次操作是复验、写报告和本次交接，不是在实现新功能。

### 未完成（依序）

1. 修完F2余项：新增003阻止根授权行DELETE，保留正常计数/撤销UPDATE。
2. 正式加入同ID删后重建回归，及真实非零预留/全部账本证据的迁移升级回归。
3. 重跑lint、全部测试、并发组和独立探针，更新A1-report及最新验收结果。
4. 验收通过后，由用户决定提交/推送；处理文档PR #1依赖，使用PR，不直推main。
5. 再划分A2与B对接。OAuth/OIDC、SM2/SM3、DID、HTTP入口、模型/RP/三代理业务流程、下游订单、结算/释放/恢复、回执签名、独立审计、前端均**未实现**。

## 5. 关键技术决策及原因

- 一个Monorepo，减少契约分叉；模块有独立信任边界，不等于共享凭据或数据库权限。
- 当前唯一设计为GM-MVP-1。AS统一签根与子令牌，父代理只签委托请求；取代旧的“父直接签子凭证”路线，避免维护两套权限链格式。
- OAuth管授权，OIDC管人的登录；Access Token和ID Token分开。SM2用于签名，SM3用于项目摘要；自定义AGPoP绑定密钥和完整请求，不伪称标准DPoP。PKCE的S256保持SHA-256，不偷换语义。
- JWS签名验证原始编码两段，不把旧自定义域前缀拼进去；SM2 profile/用户标识/签名格式已在方案定义，但尚未落地密码库。
- DID采用did:web＋企业登记表：解析公钥不自动赋予企业权限。不做区块链、通用钱包，也不宣称全OIDC/DPoP互通或全栈国密。
- 同一tenant/task永久唯一根；子额度共享上限，不签发即独占。所有祖先计账，读/通知金额0但次数1。
- 同步psycopg＋版本化SQL，避免A1同时引入ORM/异步框架复杂度。BIGINT安全边界≤2^53−1，bool/浮点不当整数，delta允许明确有界负值。
- 锁序为相关主体/key→任务/根→根至叶。锁后 `clock_timestamp()` 复核时效，不用事务启动时now掩盖排队过期。
- proof_jti不是幂等键。EXISTING免重复计费，不免当前验权；保留首次证据，重试另关联proof。
- A1仅接受可信内部对象，不验SM2。frozen dataclass不是安全隔离；A2只能从B真实验证器构造，不能开“已验权JSON”网络入口。
- AS/网关账本共享可信事务域以明确撤销/接受边界；下游独立事务域，未来未知结果保留预留，不能超时即释放。撤销不回滚已接受操作。

## 6. 当前唯一代码阻断与回归缺口

详见 [tasks/A1-review-r2.md](tasks/A1-review-r2.md)，不要重新处理已关闭的F项。

### F2同ID根重建（已实测失败）

`002_root_invariants.sql`保护了ag_tasks DELETE/UPDATE，并用可延迟FK关联根；ag_grants只有UPDATE保护，无根DELETE防护。

复现：无子节点根→真实预留70000分/1次→撤销→同事务DELETE根并以同ID重新INSERT（计数/撤销列取默认值）→提交成功。新连接查到根 `(reserved=0,calls_reserved=0,revoked=false)`，而operation仍记录70000分。

是可信SQL维护路径的生命周期不变量缺口，不是当前公网攻击入口；不要求抵抗超级用户禁用触发器。合理修复是新增003中的 `BEFORE DELETE` 根行防护（依据OLD.parent_grant_id），不改001/002、不清零旧库、不关闭触发器通过测试。

### 升级正式测试不足

`tests/integration/test_migrations.py` 的001→002测试只build_tree，计数为0且仅比较少数表。主代理已用真实70000分预留比较七张表全部行，确认当前001→002不丢状态；需将其纳入正式回归并扩展到003。探针中版本硬编码002是当时快照，新增003后应让**正式测试**按实际版本推导，不能把期望版本失败误认为迁移数据丢失。

### 其他限制/技术债（不是本轮新功能任务）

- Python3.11与A1远程CI尚未实跑；本机3.14通过不能等价代替。
- constraints.txt只固定psycopg/psycopg-binary，非全部传递/构建依赖锁；不要宣称完全可复现供应链。
- 迁移脚本位于仓库根migrations，当前验证的是仓库/可编辑安装；没有验证构建wheel后在仓库外运行迁移。
- 测试容器tmpfs、固定容器名与55432端口是本地开发方案，不是生产部署。
- README开头“已通过自动化测试”指现有套件；最终验收仍未过，真实状态以最新review为准。
- task报告保留历史实施agent“全部修复”等文字，页首及最新review优先；不得照抄历史计数和自查结论。

## 7. 文件地图

### 开发依据

| 路径 | 当前作用 |
| --- | --- |
| README.md | 项目目标/范围/阶段、A1运行命令、协作入口 |
| AGENT.md / AGENTS.md | 开发约束及自动发现入口 |
| docs/oauth-oidc-sm2-mvp.md | 唯一当前架构、术语、A/B分工、OAuth/国密/DID和HTTP/SDK契约 |
| docs/security-model.md | 威胁假设、锁序、账本、撤销、恢复与审计边界 |
| docs/acceptance.md | 初版/成熟版、性能和交付清单，不代表各项已实现 |
| tasks/A1-ledger.md | 本阶段范围、接口、U1/P1—P14与留痕要求 |
| tasks/A1-report.md | 实施agent交付记录；页首已更新为PARTIAL |
| tasks/A1-review.md | 首轮历史缺陷，不是当前未关闭清单 |
| tasks/A1-review-r2.md | 最新复验结论，下一步唯一权威修复清单 |

### 实现与环境

| 路径 | 当前作用 |
| --- | --- |
| src/agent_guard/contracts/ledger.py | VerifiedInvocation/TrustedCost/AcceptResult、枚举与常量 |
| src/agent_guard/ledger/validation.py | 纯输入校验，成本错误码、calls=1 |
| src/agent_guard/ledger/service.py | accept事务编排、动态复核、幂等、预算、连接超时/重试 |
| src/agent_guard/ledger/store.py | SQL、行类型、锁与证据/事件存储 |
| src/agent_guard/ledger/provisioning.py | 可信初始化、根/子节点、撤销/key停用夹具，无HTTP授权入口 |
| src/agent_guard/ledger/migrate.py | SQL发现/checksum/迁移CLI，普通DSN优先于TEST DSN |
| migrations/001_init.sql | 原始7张业务表、计数约束、grant/operation不可变UPDATE触发器 |
| migrations/002_root_invariants.sql | 升级预检、根部分唯一索引、任务不可变/禁删、延迟关联、calls=1；仍漏根DELETE |
| compose.test.yaml | PostgreSQL16测试容器，localhost:55432，tmpfs |
| pyproject.toml / constraints.txt | 新增psycopg依赖、pytest标记、固定驱动版本 |
| .github/workflows/ci.yml | 工作区中新版：PostgreSQL服务＋lint＋unit＋迁移＋integration |
| .env.example / .gitignore | 配置占位；忽略环境/秘密/artifacts/PDF等 |

### 测试及证据

- `tests/unit/test_input_validation.py`：类型/边界；`test_service_config.py`：超时配置、连接工厂、失败映射/重试。
- `tests/integration/test_accept_core.py`、`test_rejects.py`、`test_concurrency.py`、`test_state_checks.py`、`test_rollback.py`：账本/拒绝/10轮并发/时效撤销/回滚。
- `test_migrations.py`：迁移与scratch；`test_invariants.py`：F2/F3/F4；`test_isolation.py`：F1隔离。
- `tests/fixtures/state.py`：可信合成身份/树/调用/成本；`isolation.py`：会话独占schema、所有权标记、随机scratch与DSN解析；`dbstate.py`：只读断言查询。
- `tests/test_scaffold.py`、`tests/test_docs.py`：包导入/版本及文档链接/JSON检查，不是安全验收。
- `artifacts/A1/20260929T1700-a1-r1/`、`20260930-a1-f-fixes-r2/`：实施agent两轮证据。
- `artifacts/A1/review-20260930/`：主代理首轮XML和4项独立探针 `test_missing_invariants.py`。
- `artifacts/A1/review-20260930-r2/`：最新独立复验XML；`test_root_rebuild.py`当前失败；`test_upgrade_nonzero.py`001→002非零升级通过。
- `.venv/`本地环境及上述artifacts都被忽略，不在GitHub；换机器前应另行安全保存必要证据，不能只克隆仓库期望拿到未提交文件。

## 8. 未提交工作区（本次交接读取git status确认）

已跟踪修改仅3项：

1. `.github/workflows/ci.yml`：增加PostgreSQL及集成步骤。
2. `README.md`：A1实现边界、安装/数据库/隔离/迁移命令。
3. `pyproject.toml`：psycopg运行依赖、unit/integration标记。

未跟踪：`compose.test.yaml`、`constraints.txt`、`migrations/`、`src/agent_guard/contracts/`、`src/agent_guard/ledger/`、`tasks/`、`tests/__init__.py`、`tests/fixtures/`、`tests/integration/`、`tests/unit/`，以及本次新增 `HANDOFF.md`。全部属于需要保留的工程工作，不是可随手清理的缓存。

没有暂存/提交A1；没有A1的commit可用于恢复。父目录内部两份Markdown已有历史修改但不属于本repo。现有SQL迁移是未跟踪文件，却已在开发/验收库应用，**未跟踪不等于允许改历史迁移**。

## 9. 已验证结果与运行状态

最近独立复验（2026-09-30，非本次交接重新测试）：

| 项目 | 结果 |
| --- | --- |
| Ruff / 格式 | 通过，29文件 |
| unit＋3项骨架/文档 | 68通过（65 unit＋3） |
| PostgreSQL integration | 77通过，11.01秒，无skip |
| 首轮4探针原样复跑 | 4通过 |
| 非零预留/证据001→002升级 | 1通过 |
| 同ID删后重建根 | **1失败**，已验证提交后预留/撤销被清除 |

上述145套件测试全绿不能抵消独立探针失败。P3/P5/P6确实独立连接＋barrier各10轮；P9有真实锁等待；P12有真实DB回滚，但连接丢失项使用OperationalError注入，不是实断网络。

交接时Docker daemon正常，`agent-guard-test-pg`健康运行于127.0.0.1:55432；其已有状态不要擅自清空。两次主代理review临时容器均已删除。系统还有其他项目容器，禁止docker prune或批量stop。没有启动本项目HTTP服务，因为没有实现。

安装/本地pytest环境为Python3.14.7、psycopg3.2.13、测试PG16.15。未验证Python3.11、A1远程CI、wheel部署、真实OAuth/密码/模型/下游/恢复性能。

## 10. 下一步最小执行计划

1. 阅读AGENT、A1-review-r2及002迁移，检查工作区仍是上述状态；不要重新搜整个标准体系。
2. 先把根同ID重建探针转成正式集成回归，确认当前失败；明确无子节点且有预留/已撤销场景，避免外键到子节点恰好遮住bug。
3. 新增003根DELETE防护，不影响合法预算UPDATE与撤销。对已有数据不得清零/修复式删除。
4. 加强正式升级测试：001库实际accept非零操作，保存七表全部内容，升级到所有最新版本后逐项一致；错误数据升级须回滚且保留原版本记录。
5. 在安全隔离实例运行全量测试、并发10轮、原4探针和新根保护用例；已过项不能退化或skip。记录实际计数，不沿用旧68/77。
6. 更新A1-report和新增复验记录；没有user新授权不commit/push。验收通过只代表A1，不进入A2。

## 11. 常用命令与安全注意

以下均在仓库根目录执行。连接串从本地测试环境注入，不写入报告；**迁移器普通DSN优先**，测试前确认并移除可能指向正式库的 `AGENT_GUARD_DATABASE_URL`。

```bash
git status --short --branch
git log --oneline -5
git diff --stat
git diff --check
git ls-files --others --exclude-standard

.venv/bin/python -m pip install -e '.[dev]' -c constraints.txt
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m pytest tests/unit tests/test_scaffold.py tests/test_docs.py -q

docker compose -f compose.test.yaml ps
# 仅确认无冲突且需要启动时：
docker compose -f compose.test.yaml up -d --wait

# 先配置AGENT_GUARD_TEST_DATABASE_URL为明确授权的测试实例。
# 环境变量含密码，不要在日志中打印。
env -u AGENT_GUARD_DATABASE_URL .venv/bin/python -m pytest tests/integration -q
# 若需要手动迁移，确认目标后才执行：
env -u AGENT_GUARD_DATABASE_URL .venv/bin/python -m agent_guard.ledger.migrate

gh pr view 1 --repo Qdcchh/agent-guard
```

- 默认git diff不含新文件；先列未跟踪文件、读实际代码，不能只审3个已跟踪diff。
- 不自动执行compose down：现有测试容器tmpfs数据会消失。主代理前两轮用另起的临时实例55439端口验证，结束只清理自己创建的实例。
- 独立探针有专用数据库名断言：原4探针要求 `ag_review_probe`；根重建要求 `ag_review_f2`；非零升级要求 `ag_review_upgrade`。用新建隔离实例和正确数据库，不改断言去指向用户已有库。
- 有些探针未放入正式tests，默认pytest不会运行它们；将关键场景纳入正式回归，保留历史失败证据。
- 如以后获得推送授权，SSH在本环境曾超时，HTTPS成功。可临时使用 `GIT_TERMINAL_PROMPT=0 git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push ...`，不修改全局Git配置；本轮不要执行push。

## 12. 历史尝试、否决方案及对话独有信息

- 初期多次委派strong/fast写文档出现长时间等待、空结果或“成功但实际无文件”。确实发生过主代理read回查文件不存在；并非Word格式问题，文档一直是Markdown。后续主代理apply_patch成功，研究/只读review子agent可用。根因没有最终证明是提供商故障，不要重新无限派发大写入任务或擅自改OpenCode全局配置。
- 用户曾授权初始化并上传GitHub，但A1阶段与本次交接明确要求不commit/push，**历史授权不能覆盖当前限制**。
- 最初私有仓库无法在当时账号套餐启用分支保护；用户明确同意转公开，才启用保护。不要为了绕审核临时关闭保护。
- 第一次HTTPS推送被workflow scope拒绝，用户已手动授权后成功。不要把令牌或一次性授权码写入文件。
- 老师允许参考A1-26换场景自命题，不必再反复争论是否能参考；但不要把原题已有的共享预算/恢复/审计说成首次发明。正式赛规和评分标准未提供，不得编造。
- 老师提出OAuth＋SM2/SM3＋OIDC＋Agent2Agent＋DID，并给 `https://github.com/OpenIDC/liboauth2` 与2022年GitHub第三方OAuth令牌被盗公告。liboauth2是C基础库，不是开箱即用完整OP；所查源码不足以证明直接支持SM2。**是否必须实改liboauth2本体仍未得到用户/老师确认**，当前计划默认参考机制、Python主线。
- OIDC正确名称OpenID Connect。ID Token不当工具授权；偷有效Bearer令牌不是破解签名，换SM2还需持有者绑定/最小权限/撤销。不要把PKCE S256或标准DPoP ath/jkt里的SHA-256暗改成SM3仍标标准兼容。
- “可信执行”项目名不额外承诺TEE硬件；“Agent2Agent”是授权场景，不等于已实现某独立A2A消息协议。
- 原protocol-v1/architecture/execution-state/threat-model文件已合并或删除，有效内容在三份docs；不要恢复成两套活跃协议。
- 最近两次review未修业务代码，只运行安全隔离测试、写探针及报告。后续模型不应误把主代理的复现探针当已修复实现。

## 13. 交接核对与完成边界

撰写前已检查Git状态/三项已跟踪diff、最新报告、001/002迁移列表、subject检查代码、依赖约束、PR状态和Docker运行状态；撰写后再次核对。此轮只生成HANDOFF.md，不重跑全部验收、不修改已知bug、不提交。

成功的下一轮交付应是：F2余项真实修复＋新增回归＋所有旧测试保持通过＋最新留痕，然后交回验收。不要用“145测试全绿”提前宣布A1通过，也不要趁交接顺手搭建OAuth、重构目录或扩展A2。
