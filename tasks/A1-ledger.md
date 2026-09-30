# A1 任务交接：执行账本与原子接受操作

状态：待实施。此任务是A职责的第一阶段，约占其核心工程的三分之一，不按代码行数衡量。目标为2—3个有效工作日；复杂性超出预期时提交阻塞记录，不扩大范围或削弱验收。

## 0. 实施agent首先执行

（1）工作目录为本仓库 `agent-guard/`。读取 `AGENT.md`、本文及 `tasks/A1-report.md`；按下表有针对性地阅读资料，不重复研究全部OAuth标准。

（2）确认当前分支 `feat/a1-ledger`，起点为 `9796825a4aa44f3ca3d6911e1094c15e7803cc35`。先执行 `git status --short --branch`、`git log --oneline -5`，记录工作区原有改动。本任务两份交接文件是预先准备的输入，不得删除或当作他人冲突回退。

（3）起点来自文档PR #1：<https://github.com/Qdcchh/agent-guard/pull/1>。准备任务包时该PR尚未合并；不要切回旧main，也不要擅自reset、rebase、强推或修改分支保护。即使其随后Squash合并，当前起点仍可用于开发，主代理验收后处理分支集成。

（4）环境已知：本机Python 3.14.7可运行现有骨架，CI基准Python 3.11；Docker CLI/Compose可用，但准备任务时daemon未启动。请先检查可用性。可请求用户启动Docker Desktop，或使用用户提供的隔离测试PostgreSQL；不得修改用户已有数据库、全局Git配置或关闭认证。

（5）先补全报告中的基线、环境和三阶段计划，再开始实现。没有用户新的明确授权，不commit/push/创建PR/合并；最终由主代理验收后集成。允许正常编辑、测试和维护本任务文件。

## 1. 阅读材料与完成边界

| 材料 | 必读部分 | 用途 |
| --- | --- | --- |
| README.md / AGENT.md | 状态说明、约束、检查命令 | 不把规划当实现，不跨越B职责 |
| docs/security-model.md | 第3—7节，及第8节证据关联 | 唯一根、锁序、时效、预算、幂等与撤销 |
| docs/oauth-oidc-sm2-mvp.md | 第8.1/8.3/8.5、9.4/9.5及第10节 | 数值/授权约束、proof/幂等作用域、内部类型 |
| docs/acceptance.md | M6/M11/M13、CON-01/02/03 | 本阶段必须提供的数据库断言 |
| pyproject.toml / tests/ / .github/workflows/ci.yml | 当前全部内容很少 | 保留现有测试，扩展而非替换 |

本阶段结束时应有：**可迁移的真实PostgreSQL状态库＋进程内接受接口＋自动并发/回滚测试＋明确留痕**。它不是完整安全网关，不能从网络接收一个“已验权JSON”并执行，也不能声称已完成SM2/OAuth验权。

### 1.1 A整体的三阶段

- A1（本任务）：授权状态/账本schema、原子预留、请求重放与业务幂等、动态状态复核。
- A2（不做）：接B的真实验签SDK与HTTP网关，接可信报价解析、模拟下游，完成执行/结算/释放/恢复及回执outbox。
- A3（不做）：RP与三代理端到端流程、部署和演示、压测故障矩阵、证据导出集成。

### 1.2 必做与不做

必做：版本化迁移；任务唯一根约束；不可变父子授权状态；全部适用节点预算和次数；proof重放唯一性；业务幂等；锁内动态撤销/有效期/key状态复核；持久化RESERVED及首次接受证据引用和RESERVE账本事件；真实PostgreSQL多连接并发测试。

不做：OAuth/OIDC端点、SM2/SM3或DID实现、令牌签发/委托策略、HTTP入口、模型、前端、真实下单、结算/释放/恢复、签名回执、审计检查点。可以预留状态字段，但不得实现永远成功的占位服务。不要大规模改写现有方案文档。

## 2. 文件与协作边界

建议目录（确需时再创建，不铺空文件）：

```text
src/agent_guard/contracts/ledger.py       最小共享输入输出类型
src/agent_guard/ledger/                   事务、存储、错误类型
migrations/                              版本化SQL及迁移入口
tests/unit/                              输入边界测试
tests/integration/                       PostgreSQL并发与事务测试
tests/fixtures/                          可信合成状态/成本夹具
compose.test.yaml                        隔离的开发/测试PostgreSQL
tasks/A1-ledger.md                        本任务规范，不随意降低要求
tasks/A1-report.md                        agent持续更新的交付记录
artifacts/A1/<run-id>/                    本地脱敏测试日志，不入库
```

`contracts/`最终由B协调，但现在没有实现。A1只建立账本需要的最小类型，不等待B完成，也不另复制一套伪Token/SM2模块。模块docstring标注“可信进程内输入，B的未来验证器构造”；新增字段/假设列入报告中的B对接清单。B已有修改时先检查和复用，不能覆盖。

允许更新：上述文件、pyproject.toml、必要锁文件、`.env.example`、测试CI和README的实际运行入口。README只声明实际完成A1，不删除“OAuth/密码/完整网关尚未实现”的边界。

依赖建议：SQLAlchemy Core或直接psycopg二选一，优先简单直接的psycopg 3；用版本化SQL即可，不为几张表堆框架。新增运行依赖要有一致的锁定/约束方案和可复现安装命令，覆盖Python3.11；不得把本机3.14的环境路径或所有无关包冻进仓库。

## 3. 最小进程内契约

建议保留项目方案的命名，类型可以拆分，但语义不得改。A1使用同步Python接口及独立数据库连接，避免同时引入async复杂性。

```python
class ExecutionLedger:
    def accept(
        self,
        verified: VerifiedInvocation,
        cost: TrustedCost,
    ) -> AcceptResult: ...
```

**VerifiedInvocation不是密码学证明。** frozen dataclass只能防意外修改，不能防同进程恶意代码。A1不实现外部解析入口；测试直接构造可信内部输入是合法分层测试，但不得把它描述为真实验签结果。未来仅B验证器生成该对象，HTTP请求不能直接反序列化成它。

### 3.1 最少输入字段

| 字段组 | 内容及检查 |
| --- | --- |
| 授权定位 | subject、tenant_id、task_id、grant_id、root_id、holder_client_id、holder_kid；必须与可信数据库快照一致 |
| 路径 | ancestor_ids（若提供）；以数据库不可变父子路径为权威，不信任调用方提供的缩短路径 |
| 消息绑定 | profile=GM-MVP-1、purpose=invoke、固定受众/endpoint、method=POST、tool_id、tool_version=字符串1 |
| 参数与业务键 | canonical_params（B已规范化的参数字节）、idempotency_key；A1不另实现一套RFC8785或SM3 |
| 时效 | token_exp、proof_iat、proof_exp；DB另存每授权节点not_before/expires_at |
| 防重放 | proof_jti、holder_kid、purpose、endpoint；唯一作用域按此四项 |
| 证据引用 | token_digest、proof_digest、intent_digest、evidence_ref；保存首次接受关联，不打印令牌 |

可以保留原方案中的其他字段。需要格式校验、最大长度和合理上限；未知tenant/task/grant/key、路径循环/不完整、profile/purpose不支持均拒绝。授权节点和父关联不可变，不得通过更新parent指向重置累计额度。

为避免只相信外部传入的intent_digest，幂等比较同时核对原始规范意图字段：grant_id、holder_client_id、holder_kid、tool_id、tool_version、canonical_params。purpose/proof_jti/签名时间不属于业务意图。数据库字节比较即可，不必A1先实现密码摘要。

### 3.2 TrustedCost

包含 `currency="CNY"`、`amount_fen`、`calls=1`、可选可信报价快照标识/版本/字节或引用。只读和通知amount为0，模拟下单为可信报价成本。

它来自未来A2的可信报价解析器；不是客户端自报金额。A1以测试专用成本夹具注入，禁止建立公网“传多少钱就预留多少钱”的接口。首次接受将成本和报价快照与操作一起保存。同键同意图重试使用已接受的原成本，不重取新报价、不再次预留；已有操作和新操作的路径必须分开。

### 3.3 AcceptResult与异常

- 成功结果含 `operation_id`、`grant_id`、`root_id`、`status="RESERVED"`、`disposition="CREATED"|"EXISTING"`、原始成本、accepted_at。
- 不用200/409等HTTP状态作为内部返回；A2再映射HTTP。
- 用明确异常/错误枚举区分 INVALID_CONTEXT、INVALID_COST、REVOKED、EXPIRED、STALE_REQUEST、HOLDER_MISMATCH、REPLAY、IDEMPOTENCY_CONFLICT、BUDGET_EXCEEDED、CALL_LIMIT_EXCEEDED、TRUSTED_STATE_UNAVAILABLE。
- DB故障不能伪装成EXISTING或成功，错误日志必须脱敏。有限deadlock/serialization重试可以实现，但不能无限循环，也不能把约束冲突统称数据库不可用。

## 4. 存储模型与事务要求

表名自行确定，至少覆盖这些事实：

（1）任务行及 `(tenant_id, task_id)` 唯一根关系。过期、撤销、重复初始化也不清零。首次创建锁任务记录＋唯一约束，不能只锁不存在的根。

（2）主体/key登记状态：client、tenant、kid、active；至少能够模拟当前holder停用。初版仅用受信初始化夹具创建；没有自助登记或伪DID端点。

（3）授权树节点：节点ID、父/根、用户/租户/任务/holder、not_before/expires_at、revoked、金额/次数上限、已预留/已结算。至少支持根＋两级子；A1只存储及验证结构，不签发OAuth token或实现收窄HTTP服务。可信夹具仍检查子归属、时间区间、深度和上限，不能构造自相矛盾的测试状态。

（4）操作记录：唯一业务键 `(tenant_id, task_id, tool_id, idempotency_key)`、不可变意图字段、成本/报价快照、当前授权节点、初始证据、状态与时间。

（5）proof记录：唯一键 `(holder_kid, purpose, endpoint, proof_jti)`。成功首次接受及EXISTING重试都同事务关联operation_id、本次proof_digest和evidence_ref；保留重试证据但不覆盖操作的首次证据。可复用proof表承载关联，不必另造复杂事件系统。本阶段不做过期清理；不得用进程内set替代DB唯一性。

（6）RESERVE账本事件：operation_id、phase、根至叶各节点金额/次数delta。与预算和操作同事务。A1只保存规范数据，不计算SM3/不签回执；A2据此形成完整ledger_changes。重试不再插一份RESERVE事件。

金额和次数用BIGINT加CHECK，拒绝负额度、bool、浮点及超过2^53-1的输入。检查 `settled <= limit`、`reserved <= limit - settled` 等安全形式，避免依赖可能溢出的加法；其余累加也要在安全边界内。只有账本delta可使用明确有界的负整数，本阶段RESERVE通常为非负。

### 4.1 接受顺序

（1）校验内部输入和可信成本格式，读取不可变授权路径，核对其确属同租户任务的唯一根。

（2）按统一顺序锁相关主体/key记录，再锁任务/根和根至叶节点。保持与委托/撤销约定兼容。锁等待和DB超时必须有上限。

（3）锁后用PostgreSQL `clock_timestamp()`或等价实际当前时刻，复核当前key/holder、全部祖先not_before/expires_at/revoked、token_exp、proof时效。不能用事务启动时的 `now()`掩盖锁等待过期；proof允许未来偏差5秒、寿命最多60秒，严格按方案检查。

（4）在同事务检查/登记proof唯一性，再查业务键。同键同意图走EXISTING，不检查第二次余额、不加次数；不同意图拒绝。完全相同proof重放仍应拒绝，不能先返回已有操作绕过防重放。

（5）首次接受检查根及所有祖先/叶额度，原子更新预留、写入RESERVED、成本/快照、首次证据及一次RESERVE事件。最后提交。

（6）任一步失败全部回滚。拒绝请求不必永久消耗proof_jti，但不得留下部分proof/预算/操作；成功EXISTING仍须登记本次新proof及其原操作/证据关联，以阻止该证明重放并支持追溯。

整个A1没有下游业务效果。测试对撤销/key停用使用遵循相同锁顺序的可信状态事务，不实现AS管理API。接受先提交后再撤销时保留既有RESERVED，不擅自释放；撤销先提交则新接受拒绝。

## 5. 验收用例（必须真实运行）

所有P类测试使用真实PostgreSQL，不用SQLite，不用内存字典替代账本。并发测试每个worker独立连接，用barrier/event或明确数据库锁协调重叠；不得只写顺序循环声称并发。pytest给集成测试标记，但规定的集成测试命令缺数据库时必须报错，不能静默skip后整体显示成功。

| 编号 | 场景 | 必须断言 |
| --- | --- | --- |
| U1 | 负数、bool、浮点、超界、错误币种/版本/purpose | 拒绝，数据库无变化 |
| P1 | 合法根→中间→叶接受一次700元 | 三层预留均70000分/1次，一条操作及一次RESERVE事件 |
| P2 | 未登记holder/key、跨租户/任务、伪造root/截短祖先 | 拒绝；不信任context自己声称的路径 |
| P3 | 根1000元、两分支各800元，同时各申请700元 | 恰好一个CREATED，一个预算拒绝；根700元不超过1000元 |
| P4 | 根充足，但中间祖先额度不足；直接父调用和后代共用 | 中间节点约束有效，不能仅检查根和叶 |
| P5 | 次数上限1，两个零金额调用竞争；零额度边界 | 最多接受一次，读取/通知不能绕次数 |
| P6 | 同业务键同意图，两份新proof并发；耗尽预算后再重试 | 同一operation_id，CREATED/EXISTING，无二次预留/RESERVE事件；新proof及各自证据关联均登记 |
| P7 | 同键换格式合法的参数，或换另一份有效授权的holder/grant；同proof重放 | 分别IDEMPOTENCY_CONFLICT或REPLAY；余额不变。不支持的工具版本归U1，先INVALID_CONTEXT，不为了测试放宽版本支持 |
| P8 | token/任意祖先未生效、过期、已撤销、key停用 | 拒绝；同键重取也不得绕过当前状态 |
| P9 | 一连接持锁至proof过期，另一连接等待接受 | 释放锁后仍拒绝，证明确实使用锁后时间 |
| P10 | 撤销先提交与接受先提交两种确定顺序 | 前者拒绝，后者原预留保留且后续调用拒绝 |
| P11 | 同任务并发初始化两个根；撤销/过期后重建 | 最多一个根，唯一约束有效，余额不清零 |
| P12 | 写到中途抛异常/约束失败、提交前连接中断 | proof、操作、各节点和事件全回滚；新请求可正常接受 |
| P13 | 迁移空库、已迁移库再次执行、数据持久化后重连 | 版本可检查、不重复建表、不丢已存数据 |
| P14 | 同键重试时可信当前报价已变化 | 读取原成本/快照，不二次预留；首次证据不被新proof覆盖，重试proof与原操作的关联可查 |

故障注入限测试fixture、测试替身或monkeypatch存储步骤，不新增运行环境能开的 `SKIP_AUTH`、`FORCE_SUCCESS`、`TEST_BYPASS`、任意成本HTTP等后门。P12可在第一节点变动后注入异常验证原子回滚，但必须是真实DB事务。

测试精确错误码和DB不变量，不只断言“抛出了某个异常”。并发组至少重复10轮，每轮隔离数据，记录成功/拒绝数；不用随机sleep制造偶然通过。

## 6. 环境与CI

- 建议 `compose.test.yaml` 只启动PostgreSQL，固定明确版本，端口绑定 `127.0.0.1`。使用本地环境注入密码，不提交真实密码，不将宿主机Docker socket挂给应用。
- 测试使用独立数据库/唯一schema，拒绝非测试目标；清理仅限本任务生成的命名空间，不运行对用户已有数据的DROP/volume删除。
- 提供可实际执行的安装、启动、迁移、单测、集成测试、清理命令。两次尝试仍无可用数据库时记录BLOCKED并询问用户，不安装未知系统服务或声称已完成。
- 在CI增加真实PostgreSQL服务及集成测试步骤；服务健康后执行，不静默skip。CI用临时测试凭据且不复用部署凭据。
- 现有 `ruff check`、`ruff format --check`、所有既有pytest必须继续通过。本任务新增测试统计应区分unit/integration与skip，不能只报总通过数。

## 7. 三个检查点与留痕

### 检查点一：契约与环境

先完成最小类型、迁移设计、测试库运行方法及不超过10条实现决定，更新报告。若发现必须改变已定安全语义，停止该部分并提问，不自行删要求。

### 检查点二：纵向正确性

完成P1、P6、P8、P11、P12的实际测试再继续并发优化；报告记录新增文件、已有通过与未通过用例。不要先铺满空模块。

### 检查点三：交付

运行所有用例、重复并发测试、既有检查；生成脱敏结果和自查清单。最多两轮自动修复仍无法解释关键失败时，报告阻塞和最小复现，不无限重试。

**结构化留痕必须落实：**

- `tasks/A1-report.md`：长期可审阅摘要，正文建议不超过150行。记录基线、实际环境、变更地图、接口差异、用例对应测试、真实命令/退出码/通过失败skip、未完成项及B/A2对接事项。
- `artifacts/A1/<run-id>/`：本地运行日志和详细结果，已在gitignore范围内，不上传。输出命令不得包含实际数据库密码/连接串、token或私钥。
- 留下 `git status --short`、已跟踪文件diff，以及**未跟踪新文件清单**。`git diff`默认不含新文件，不能只交空diff声称无变更；新源码由主代理按清单读文件或之后统一暂存审查。
- 不把整个agent对话复制成报告，不截断失败关键信息，不用“应该通过”“预计通过”替代真实测试。没有运行的明确标NOT RUN，环境导致无法运行的标BLOCKED。
- 最终聊天回复控制在约500字：状态、报告路径、关键测试、未完成、下一步；详细信息放报告而非重复粘贴源码。

## 8. 完成标准与交接给主代理

只有U1及P1—P14均有实测证据、真实PostgreSQL并发/回滚通过、文档命令可复现、没有扩大安全接口范围，才可标READY_FOR_REVIEW。否则标PARTIAL或BLOCKED，不影响主代理检查已有工作，但不能宣称A1完成。

主代理验收将先读A1-report、看Git变更、抽查事务锁序/时效及路径/幂等逻辑，再重跑关键测试。不会仅凭报告“通过”接受实现。A1通过不等于整个项目通过，尤其不能对外宣称已完成OAuth、密码、工具副作用防护或恢复。

文档交接文件可以与最终A1代码一并经PR入库；本轮实施agent不要自行提交。用户确认后由主代理处理提交、main文档PR合并后的基线同步及下一阶段任务。
