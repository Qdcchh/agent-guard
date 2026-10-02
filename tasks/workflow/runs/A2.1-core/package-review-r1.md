# 独立审查：PACKAGE_REVIEW／A2.1-core／本次 NEW 审查

## 1. 结论与范围

- **审查日期／时区：**2026-10-01，Asia/Shanghai。初次指纹核验时间为 10:26:13，结束指纹核验时间为 10:32:10，随后再次只读复核包一致性。
- **review_kind：**`PACKAGE_REVIEW`。
- **本轮结论：`PACKAGE_READY`。**
- **受审对象：**[A2.1-core task-v1.md](/Users/qdcc/code/密码技术竞赛/agent-guard/tasks/workflow/runs/A2.1-core/task-v1.md)，以及其要求的原始任务、工作流契约、安全／接口／验收文档和实际基线。
- **授权范围：**仅 A2.1-core 主体、同阶段详细独立复核、补正和再复核；核心通过后停止等待用户查看与审批。
- **当前实现状态：**A2.1 主体尚未实现，完整 A2／项目仍为 **PARTIAL**。本报告不设置阶段 `ACCEPTED`，不填写 `state.review`。
- **阻断项：**未发现阻断本包的实质性方案矛盾、需求删减或授权越界。既有 `DOC-CKPT1-01` 保持非阻断开放状态，须在主体交付报告中纠正。
- **后续依赖：**完整 P15 真实授权、P16／P17 真实验证、P18 真实签名部分、P21 真实 HTTPS 联合闭环仍属 A2.2／A2.3及 B 依赖，不计为本阶段完成。
- **是否允许进入下一大阶段：否。**本报告不授权 A2.2、A2.3 或 A3。
- **权限边界：**本轮只读；未修改受审文件、测试、标准、状态或报告；未创建业务数据库、schema、容器或服务；未 commit／push／PR／合并／修改 Git 配置或保护。

**结论依据：**31 项冻结需求及六条检查点一后续义务完整保留；核心架构与现有 A1 接受接口、锁序、事务边界和历史迁移兼容；未来验证计划要求真实 PostgreSQL、独立下游事务域、确定性并发、真实进程终止／重启、直接 SQL 防绕过及独立 reviewer 实跑。未实现行为没有被写成已通过。

---

## 2. 独立会话与候选版本

本报告中未写成绝对路径的文件名均以以下根目录解析：

`/Users/qdcc/code/密码技术竞赛/agent-guard`

### 2.1 元数据、授权与冻结

| 项目 | 实际值／独立核对结果 |
|---|---|
| Reviewer session／Task ID | 当前工具接口未暴露真实 ID；检查 `OPENCODE_SESSION_ID`、`OPENCODE_TASK_ID` 均未取得值。**不编造 ID，不借用历史会话 ID。**主控保存时应从实际本次子会话记录关联。 |
| 模型 | `openai/gpt-6.1-sol`，由本轮运行指令明确提供。 |
| 推理档位 | 工作流要求 reviewer-auto 使用 xhigh；本轮接口未提供可独立读取的实际档位元数据，因此不把配置声明冒充运行时查证。 |
| 审查轮号 | 父任务指定 NEW，未给出报告 rN 编号；由主控保存时关联，本报告不猜测编号。 |
| 当前阶段 | `A2.1-core`，与 state、任务包和本次审查请求一致。 |
| 真人授权引用 | session=`ses_f0ac0e676ffecn71p6Ww7zaqQq`；message=`msg_0f54148e0001ZW7yCMdK0TE97F`。 |
| 授权核查等级 | 主控已从 OpenCode 只读 DB 核对真实 role／session／原文，是本次明确提供的授权来源事实。本轮独立核对包与 state 中引用和原文一致，**未自行查询该 DB，也未自行授予 GRANTED**。 |
| 当前 state | `IN_PROGRESS`／`authorization.status=GRANTED`／`review=null`。 |
| 实际分支／HEAD | `feat/a2-execution-gateway`／`b120c7cf5ec0eafb18305d1207c36dd11655b324`。 |
| Writer 冻结 | 主控明确确认无 writer；本轮开始、结束及最后复核未观察到文件或 Git 状态漂移。没有把单次 hash 相等称为原子文件系统快照。 |
| Staged diff | 空。 |
| Unstaged diff | 仅 `src/agent_guard/contracts/__init__.py`，42 行加法导出；全文检查，未发现 A1 接口删除或语义改写。 |
| 删除／重命名 | 未发现。 |
| 文件清单入口 | `tasks/workflow/state.json:snapshot.manifest`，75 项完整清单；本轮逐文件核验，并另外独立遍历重建清单比较。 |
| 快照排除 | state、issues、runs 报告目录及契约规定的控制／生成内容排除；任务包另入 contract_files，issues/state 本轮另核 hash。未新增排除规则。 |

真实授权原文与包、state 一致：

> 批准 A2.1-core，按冻结的 Markdown 任务包完成主体、详细独立复核、所有补正和再复核。核心通过后停下来给我查看与审批，不进入 A2.2，不 commit/push/PR/合并。

### 2.2 独立核验指纹

下列值开始与结束一致：

| 对象 | SHA-256／指纹 |
|---|---|
| task-v1.md | `67896f80e7b80fe05087f88ef08576c805117bfdd12654addff03efadf2bfec4` |
| 完整 snapshot | `bf2717112af336f17f79ebbe499c2610b9394d48daea187ea159ac81b89f4958` |
| 21 个 contract_files 的规范摘要 | `701a06938365ba0dd74399f1952566d57562bd141dcecdff2398cd8cc45cbef5` |
| state.json | `6aa456bab6a2d93b14d6e2164e49f7303338c79ea67fe52dd3d05b3c474918d4` |
| issues.md | `5a9051bc9c353ec29536cdef0136b5d072d60e0b72667bf35278a7de4175318d` |
| unstaged binary diff | `111b7787afb1f861040a04f54a25ca8cd5443975093340e2c47f952a8605af23` |
| staged binary diff | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| porcelain Git 状态，含全部普通 untracked | `3990686287800ac756530fab2313bbec559f8cd97c18dd151763015ca33bff33` |

原始依据的实际 hash 也与 contract_files 一致：

| 原始依据 | SHA-256 |
|---|---|
| tasks/A2-execution-gateway.md | `ceab732b618de7b33a866a161a250349e447c8f62182c07405362990afa0abb4` |
| tasks/A2-review-ckpt1-r2.md | `d9ff41bd7a9a7694010628de5a96e3ac723aaa4d90c4347c550da7b339016e42` |
| tasks/A1-review-r4.md | `d1f02bdf6f73ab2510386f0002a27967b981bb25e249c15990f6fd0909fe18bb` |

历史迁移与实际 HEAD 内容逐个比较一致：

| 迁移 | 工作区与 HEAD 共同 SHA-256 |
|---|---|
| 001_init.sql | `d5e7bb01b9713b7fd9f80b5da85ea039bdf311e2d4a8b6a191d7c48eb43b148c` |
| 002_root_invariants.sql | `bae1d72e1cf3dbe95ea73408e43196cdaa51297279319ac2dbf6111a68d44519` |
| 003_root_delete_guard.sql | `1d919f8f59a8d4f4bfe49a278006dd4b79f1bb8d791e701ec604ae051ec7527b` |

### 2.3 实际 untracked 清单

`git ls-files --others --exclude-standard` 实际列出 24 项：

```text
compose.a2.test.yaml
src/agent_guard/contracts/execution.py
tasks/A2-execution-gateway.md
tasks/A2-report.md
tasks/A2-review-ckpt1-r2.md
tasks/A2-review-ckpt1.md
tasks/workflow/README.md
tasks/workflow/context.md
tasks/workflow/implementation-contract.md
tasks/workflow/issues.md
tasks/workflow/review-contract.md
tasks/workflow/runs/A2.1-core/task-v1.md
tasks/workflow/runs/setup/20261001-setup.md
tasks/workflow/stages/A2.1-core.md
tasks/workflow/stages/A2.2-integration.md
tasks/workflow/stages/A2.3-receipts.md
tasks/workflow/state-guide.md
tasks/workflow/state.json
tasks/workflow/templates/correction.md
tasks/workflow/templates/implementation-report.md
tasks/workflow/templates/review.md
tasks/workflow/templates/task.md
tests/unit/test_execution_contracts.py
tools/workflow_gate.py
```

快照为 **54 tracked＋21 untracked＝75 项**，与普通 Git untracked 数量不同不是漏文件：state、issues 和两个 runs 文件按规则排除；快照另外覆盖被 Git 忽略的本地 PDF。PDF仅作字节指纹核验，没有把它作为替代 Markdown 的需求来源。

---

## 3. 实际检查的实现、调用链与包架构

### 3.1 全文阅读范围

已全文读取：

- AGENTS.md、AGENT.md、README.md。
- task-v1.md 的全部 87 行及其全部必读工作流文件：README、state-guide、context、state、implementation-contract、review-contract、issues、A2.1 stage、implementation-report 模板。
- 本轮 review 模板，以及 task／correction 模板和 A2.2／A2.3 提案、setup 记录。
- 原 A2 任务、A2-report、检查点一初审与补正复验。
- 原 A1 任务、A1-report、A1 各轮 review 至最终 r4、HANDOFF。
- security-model.md、oauth-oidc-sm2-mvp.md、acceptance.md。
- contracts/ledger.py、execution.py、导出文件；ledger 全部模块；001—003。
- 全部现有 unit、integration、骨架／文档测试，以及 state／dbstate／isolation／conftest。
- CI、两个 Compose、pyproject、constraints、相关配置文件。
- 三份历史独立探针源码：原四项不变量、根同 ID 重建、非零升级探针。

没有以 worker 报告或历史“通过”声明替代实际文件检查。

### 3.2 实际 A1 接受链与兼容判断

| 实际位置 | 查证事实及对 A2.1 的影响 |
|---|---|
| `ledger/service.py:125–280` | `accept(verified,cost)` 保留；先格式校验，再事务内发现路径、锁主体／task／根至叶、锁后实际 DB 时间复核，登记 proof 后查业务键。包要求的候选命中仍回此路径，未设计绕过入口。 |
| `service.py:198–224,350–367` | EXISTING 返回原成本与 accepted_at，比较 grant、holder、tool/version、参数；不重新预留。A2 候选流程必须提供原成本，不能把候选查找本身当验权成功。 |
| `service.py:284–348` | 全路径 subject、归属、root、depth、holder/key、撤销、有效期与 proof 新鲜性检查实际存在。内部恢复与外部 accept 分离不会要求删除这些检查。 |
| `store.py:118–215` | 实际路径来源为 DB 父子链；主体排序、task、根至叶锁序与包一致；业务键查找不执行动态授权，适合内部候选用途而非公开成功捷径。 |
| `store.py:218–359` | proof／首次操作／预留／RESERVE 事件在同事务关联。未来终局需新增自己的持久化路径，不能用现有 A1 RESERVE 测试冒充结算证据。 |
| `validation.py:119–139` | 数值边界、bool／float 拒绝、calls 必须为 1；snapshot 为受信 bytes，A1 不解析完整业务资源。包正确要求 A2 补严格工具及资源校验。 |
| `provisioning.py:148–228` | 子授权、撤销沿用兼容锁序；A2 恢复不得先锁 operation 再反向锁这些节点。 |
| `001:137–170` | 首次意图／成本／证据 UPDATE 不可改；没有完整 A2 状态迁移、事件不可改删和路径防删，包明确由 004 实施，不声称已具备。 |
| `001:189–215` | event→operation 为非级联 FK；event_nodes→event 有级联删除。004 对事件／节点的防改删以及 P20 绕过测试是必要的，包完整保留。 |
| `002:18–155`、`003:6–18` | 非法旧数据预检、唯一根、任务映射保护、calls=1、根 DELETE 防护均为既有基线；包不允许改历史文件或清零旧数据。 |
| `migrate.py:69–94` | 当前迁移发现动态，执行及登记置于事务内。新增 004 不需修改历史版本期待；旧行和完整登记比较必须由新测试覆盖。 |

### 3.3 架构、所有权和依赖结论

1. **接受／执行边界合理。**接受提交后执行；下游调用不跨持有网关锁；终局将全祖先计数、操作状态、互斥事件及 outbox 原子提交。
2. **下游是真正独立事务域的计划。**同 PG 实例不同数据库、连接、事务；不是同事务模拟“跨域恢复”。执行和查询均须独立服务认证。
3. **UNKNOWN 语义未削弱。**超时、断连、503、查无结果、可能已有副作用的错配均不能 RELEASE。确定失败必须有持久终局拒绝。
4. **候选成本竞态已闭合到计划。**当前报价不存在不能阻止候选命中；miss 后任意资源／报价解析失败安全重查；重查仍回 A1 动态复核、proof 和意图比较。
5. **租约计划充分。**owner、fencing、合法状态、锁后 DB expiry 四条件；没有接管者时过期旧 worker 仍须拒绝；UNKNOWN claim 不被改成 EXECUTING。
6. **持久材料和迁移范围合理。**sidecar 不改变旧七表行形状；原完整报价和接受事实不可变；outbox created_at／receipt_id／UTC 整数秒 iat 稳定，B 缺失时保持 PENDING。
7. **权限边界明确。**A2.1 可信 fixture 不等于完整 B 权限快照。新代码必须在允许的 execution／业务 tools／execution contracts／004／正式测试等范围内；ledger 非 migrate.py 兼容修改须先交主控确认。
8. **CI 存在可用基线。**当前明确运行 unit、骨架／文档及整个 integration 目录。按包建议将新增测试放在这些目录内会被收集；若另外开目录，则不能因包内一般要求而擅改未授予的 CI 文件，须由主控处理所有权并确保显式纳入。
9. **资源隔离设计充分但尚待实现。**当前 A1/A2 Compose 默认 project 确实不同；A2 文件仍有固定容器名及端口。实施者不能照抄固定实例启动命令复用已有容器，须按包要求使用本轮独占 project／容器／命名空间并记录所有权。
10. **B 依赖没有被冒认完成。**没有 fetch／merge／复制／import B；远端 77e3570 的状态仅作为历史索引，本轮未重新核验其交付内容。当前核心不依赖它，后段必须重新确认真实 SDK。

---

## 4. 完整需求与验收矩阵

### 矩阵说明

- 实际核对：**task 31 行＝state 31 个唯一 expected IDs**；28 个 independent_run IDs 恰为前 28 项。
- 下表为**设计和未来验证计划**，不是行为测试结果；全部新 A2 行为测试本轮未执行。
- 计划落点：
  - **E**：`src/agent_guard/execution/**`
  - **T**：`src/agent_guard/tools/**`
  - **C**：`src/agent_guard/contracts/execution.py`
  - **M**：`migrations/004*`
  - **TX**：拟新增 `tests/integration/test_execution_*.py`
  - **TD**：拟新增 `tests/integration/test_downstream_*.py`
  - **TM**：拟新增 `tests/integration/test_a2_migrations.py`
  - **TU**：拟新增 `tests/unit/test_tool_validation.py`，配套 PG 拒绝断言
- 以上是包提供的新增位置及本轮检查的映射，不是已经存在的实现／函数。交付报告必须填写实际函数名和证据，不能仅保留这些通配符。

| 需求 ID／原始来源 | 当前阶段必需 | 实现／调用链 | 测试／独立探针计划 | 必须观察的断言 | 证据类型 | 设计结论／缺口 |
|---|---|---|---|---|---|---|
| A2-P01／原 A2 §7 | 是 | E→T→终局事务 | TX／TD 三层订单 | 唯一订单；根／中／叶 reserved=0，settled=70000/1；RESERVE、SETTLE 各一次；终态/outbox 一致 | 原文、包、A1 静态检查 | 计划完整；未执行 |
| A2-P02／原 A2 §5、§7 | 是 | T 持久拒绝→E RELEASE | TX／TD 终局失败及迟到执行 | FAILED；全路径释放、不结算；唯一 RELEASE；该键此后不能成功 | 静态设计检查 | 计划完整；未执行 |
| A2-P03／原 A2 §4、§7 | 是 | 四工具→E／T | TX／TD 零额读／通知 | 金额 0、calls=1；成功结算／失败释放次数正确；固定读取结果；通知最多一次 | 静态设计检查 | 计划完整；未执行 |
| A2-P04／原 A2 §7、§8 | 是 | accept 提交→持久 worker 恢复 | TX＋真实独立子进程终止／重启 | 提交前零效果；提交后由新进程恢复；保存 PID、同步及持久 DB 证据，不依赖 finally | 静态设计检查 | 计划明确要求真进程；未执行 |
| A2-P05／原 A2 §5、§7 | 是 | T 已提交→E UNKNOWN→恢复 | TX／TD 响应丢失 | UNKNOWN 保留全路径预算；同一订单；最终一次结算 | 静态设计检查 | 计划完整；未执行 |
| A2-P06／原 A2 §7 | 是 | T 成功→网关终局前中断→恢复 | TX 中断恢复 | 无第二效果／结算／终局事件／outbox；首次事实不覆盖 | 静态设计检查 | 计划完整；未执行 |
| A2-P07／原 A2 §5、§7 | 是 | 全路径计数／事件／outbox 单事务 | TX 分阶段异常注入，真实 PG | 节点更新、事件、outbox 各中断点均全回滚；原状态不半提交；随后可恢复 | 静态设计检查 | 计划完整；未执行 |
| A2-P08／原 A2 §5、§7 | 是 | query→UNKNOWN→同键恢复 | TX／TD 明确协调迟到请求 | 查不到不 RELEASE；迟到成功唯一效果、一次 SETTLE；超时重试有界 | 静态设计检查 | 计划完整；未执行 |
| A2-P09／原 A2 §7，r2 §13.4 | 是 | E claim／接管／终局条件写 | TX 独立连接、barrier/event，10 轮 | 双恢复者与旧 worker；终态不覆盖；一终局／一 outbox；无接管但过期也拒绝 | 静态设计检查 | 计划完整；未执行 |
| A2-P10／原 A2 §5、§7 | 是，查询真实验证后段 | 持久原意图恢复；外部仍 accept | TX 接受后撤销／过期／key 停用 | 内部可完成原操作，不创建新意图；外部重试拒绝；真实授权查询不得冒报通过 | 静态设计检查 | 分段边界明确；未执行 |
| A2-P11／原 A2 §4、§7；r2 §13.1–2 | 是 | 候选→原快照→A1 accept；miss→解析→安全重查 | TX 确定性 miss/提交/删报价竞态及拒绝变体 | 返回同一原操作／成本；新键拒绝；改 grant/holder/参数、撤销、proof 重放均不绕过 | 静态设计检查 | 计划完整；未执行 |
| A2-P12／原 A2 §5、§7；r2 §13.6 | 是 | E 比较 T 持久结果 | TX／TD 金额、意图、完整快照错配 | 同总额不同供应商／单价分配也拒绝结算；可能有效果时 UNKNOWN、预算保留 | 静态设计检查 | 计划完整；未执行 |
| A2-P13／原 A2 §7 | 是 | A1 accept 与 E 终局／恢复混合锁路径 | TX，相关并发组 10 轮 | 根／中间金额不足、次数耗尽；全祖先不超限、不负数；不反向锁／无无界死锁 | 静态设计检查 | 计划完整；未执行 |
| A2-P14／原 A2 §4、§7 | 是 | T execute/query 独立认证及持久唯一性 | TD 双执行、冲突、无／错凭据、代理直连 | 订单／通知均最多一次；冲突拒绝；认证失败零效果、零结果泄漏 | 静态设计检查 | 计划完整；未执行 |
| A2-P15-CORE／原 P15＋检查点二边界 | 是，仅分层 | E／T 严格参数与可信 fixture 权限集合／链 | TU＋PG 分层负例 | 完整四工具／字符串版本；重复字段/SKU、bool/负/浮点/溢出、缺/空集合、scope/祖先包含/快照/租户关联/URL路径负例；零预留／效果 | 原文、类型、包静态检查 | 计划完整；不是真实验签 |
| A2-P19／原 A2 §7；r2 §13.5 | 是 | migrate→M sidecar／保护结构 | TM：001 和003非零升级、非法升级、重复迁移 | 七表全部原列原行、非零预算／撤销／证据保全；非法升级完整登记不变；不足旧材料隔离，不能补当前报价 | 原文、迁移器和现有测试静态检查 | 计划完整；现有非法升级测试不足以替代新增完整断言 |
| A2-P20／原 A2 §5、§7；r2 §13.3、5 | 是 | M 约束／触发器＋E 条件终局 | TM／TX 直接 SQL 绕过 | 改意图/成本/首次证据，直接或先改删事件再删操作，路径删除重建，事件节点改删，phase/seq、非法状态／双终局拒绝；合法 UPDATE 有效 | 原文、实际 DB DDL 静态检查 | 计划完整；004 防护尚未实现 |
| A2-CKPT1-OBL01／r2 §13.1 | 是 | 候选前静态校验→原事实权限核对→A1 | TX 候选命中／无报价 | 不预先依赖当前报价；命中仍动态授权、proof、完整意图比较 | 原文＋实际 accept 静态检查 | 计划完整；未执行 |
| A2-CKPT1-OBL02／r2 §13.2 | 是 | miss 后任意解析失败安全重查 | TX barrier/event，含资源失败而非仅金额失败 | 并发 accept 提交后原操作可返回；新键、失效、重放、改意图负例均拒绝 | 静态设计检查 | 计划完整；未执行 |
| A2-CKPT1-OBL03／r2 §13.3 | 是 | 持久接受事实＋M 防删引用链 | TM／TX 删除顺序变体 | 可用候选事实完整；异常旧行隔离；永久候选不能删后再次 CREATED；必要时明确 DELETE 保护 | 实际 001 FK／包静态检查 | 计划完整；不能仅凭 FK 文档声称闭合 |
| A2-CKPT1-OBL04／r2 §13.4 | 是 | E claim／终局 DB 时效 | TX 过期无接管、旧 owner/version、UNKNOWN 接管 | owner/version/state/expiry 同时满足；UNKNOWN 保持；接管先对账；未知不释放 | 静态设计检查 | 计划完整；未执行 |
| A2-CKPT1-OBL05／r2 §13.5 | 是 | M sidecar／phase-seq／不可改删 | TM＋A1 回归 | RESERVE0／终局1；旧七表不加隔离列；升级失败全保全；合法计数、撤销、状态和 owned 清理兼容 | 原文、现有隔离 fixture 静态检查 | 计划完整；未执行 |
| A2-CKPT1-OBL06／r2 §13.6 | 是 | T 完整原快照→E 稳定 outbox | TD／TX 结构错配、材料重复读取／恢复 | 执行／查询比较全部快照；错配 UNKNOWN；材料不可变；receipt_id/created_at/UTC iat 稳定；PENDING、无伪 RFC8785／SM3 | 实际类型＋包静态检查 | 计划完整；未执行 |
| WF-A1-REGRESSION／A1 任务及历次 review | 是 | 现有 A1 全链＋受影响接口 | 全部 A1 unit／integration、历史探针或等价正式断言 | U1、P1—P14、F1—F5 保持；根同 ID 重建拒绝；非零迁移；不得固定旧计数代替覆盖 | 实际代码、全部测试和历史探针静态检查 | 计划完整；本轮未重跑 |
| WF-INDEPENDENT-PROBES／review-contract §3、§6 | 是，实施验收实跑 | 新 reviewer 自选重要绕过／边界 | 独立 owned 探针，保存源／日志 | 不被 worker 唯一反例限定；历史变体、受影响不变量及整体回归均查 | 包／契约静态检查 | 计划充分；本轮未创建业务探针 |
| WF-QUALITY-CHECKS／AGENT、原 A2 §8 | 是 | 全源码／测试／CI | ruff、format、diff、unit／骨架／docs、全 integration | 缺 PG 报错不 skip；新增目录不漏；实际退出码、分项计数与证据 | CI／包静态检查；本轮 diff 检查执行 | 计划完整；其余质量／行为测试未执行 |
| WF-PY311-ENV／原 A2 §8、review-contract §4 | 是，实施验收实跑 | Python3.11＋约束安装＋真实 PG16 | 专属 env 安装与完整验证 | 本机3.14／历史 CI 不能替代；缺环境 BLOCKED；远程 CI 未授权只记 NOT_RUN | 依赖文件、CI、包静态检查 | 计划完整；本轮不安装环境 |
| WF-RESOURCE-ISOLATION／F1、C1、契约 §5 | 是，实施验收实跑 | 独立 project／容器／DB/schema；仅 TEST DSN | worker/reviewer 分别 owned；归属及前后资源证据 | 不复用既有 worker DB；不共享 down；普通 DSN 清除；清理仅 owned；无关资源不变 | 隔离代码／Compose 静态检查及只读渲染 | 计划完整；未创建资源 |
| WF-IMMUTABLE-BASELINE／原 A2 §3、review-contract §6 | 是，静态为主 | 001—003、A1 语义／调用方、B 边界 | checksum／实际 diff／兼容回归 | 历史迁移内容不变；不重写 A1；无 B 偷渡；必要接口改动先确认 | 本轮独立 hash、diff、代码检查 | 当前基线一致；实施后仍需重核 |
| WF-DOCS-REPORT／原 A2 §8、issues | 是，静态为主 | README、A2-report、完整 implementation report | 每 ID→实际函数／命令／证据；复现说明 | 纠正 tracked/untracked；如实区分 fixture/真密码、故障层次、未运行；缺 B 不装配假网关 | 报告／模板／包静态检查 | 计划完整；`DOC-CKPT1-01` 仍待交付纠正 |
| WF-SNAPSHOT-COVERAGE／review-contract §2 | 是，静态为主 | 完整 manifest、contract、报告／证据绑定 | 主控冻结；reviewer 开始／结束独立核验 | tracked/untracked/deleted、调用方和契约不遗漏；无 writer；漂移则本轮失效 | 本轮独立清单重建／hash／Git 检查 | 本包核验一致；不可用于未来代码验收 |

### 4.1 后续门槛，未计为本段完成

| 项目 | 本阶段边界与后续义务 | 本轮结论 |
|---|---|---|
| 完整 A2-P15 | 真实 B 验证器和可信 grant/token/祖先权限绑定下重跑所有拒绝条件 | 后续阶段／依赖未闭合，不是 PASS |
| A2-P16 | 真 token/proof 签验、body/holder/endpoint 替换、盗 token、重放 | A2.2／B 依赖 |
| A2-P17 | 真 result-read、锁后 TTL、撤销／停用、跨租户／holder、并发 proof，零业务计数 | A2.2／B 依赖；不能放宽 A1 purpose 或伪造 invoke 字段 |
| A2-P18 | **本段保留**稳定不可变待签材料、原子 outbox、恢复不重复业务；真签名、签后保存前崩溃、真实摘要篡改验签等在 A2.3 | 部分本段计划已映射 P06/P07/OBL06；真签名未实施／依赖未闭合 |
| A2-P21 | 固定 HTTPS 端点、真 AGPoP、完整采购／读取／通知／授权查询联合闭环 | A2.2/A2.3；完整闭环不能提前宣布通过 |
| 独立审计锚点、导出、规模实验 | 原 A2 明确排除的 A3 范围 | 未实施、未授权；PENDING 材料不是签名回执或独立审计 |

---

## 5. 本阶段必查专项与历史回归

### 5.1 C1—C6 与核心专项

| 专项 | 本轮实际观察／未来证据要求 |
|---|---|
| C1 Compose／PG 所有权 | 本轮只读渲染确认 A1 project=`agent-guard`、A2=`agent-guard-a2`；均 localhost、tmpfs、无 host volume。未来 worker/reviewer 必须各自独占，不能直接复用这个固定 A2 容器。未执行运行标签／清理验证。 |
| C2／P11 候选和重查 | 原要求、r2 六义务、包、实际 accept 顺序一致；确定性 miss→并发提交→资源/报价失败→安全重查被明确要求。实际 A2 实现及竞态测试尚无。 |
| C3／P19 非零升级 | sidecar 设计不改原七表行形状；001／003 非零升级和非法升级全表／完整迁移登记比较均被要求。现有非法升级回归只有版本／根数量，不能充当本阶段增强断言。 |
| C4／P20 永久保全 | 实际 FK 关系已检查；包要求 phase-seq、防事件节点改删、操作直接删及先改删事件再删操作、路径重建拒绝。需要未来 SQL 实证，不以历史设计放行关闭主体义务。 |
| C5 租约／DB 时效 | 包比基线 LeaseGrant docstring 更明确要求 owner/version/state/expiry；不允许只实现 version。尤其过期无接管者、UNKNOWN 保持、EXECUTING 接管先 query 均须实测。 |
| C6 完整报价／稳定材料 | DownstreamOutcome 已有完整 quote 类型，PendingReceipt 为 byte 材料与持久 created_at。只是类型，不证明 runtime 持久性／不可改写；未来测试还须供应商／单价分配错配和 UTC iat。 |
| P04 真进程恢复 | 包明确要求独立进程被终止并重新启动、PID／同步／DB证据；异常注入、同进程重调或 finally 不足。 |
| P15-CORE 四工具负例 | 四个完整 ID 和字符串版本已在基线类型定义；严格工具／资源／scope／祖先集合拒绝尚待实施，零预留／效果是验收要求。 |
| 全并发／回滚／恢复 | 原任务所有并发组十轮要求由全文继承，不能只跑 P09／P13；独立连接和 barrier/event，逐祖先金额／次数、操作／事件／outbox、订单／通知一起断言。 |

### 5.2 A1 全量回归映射

这些是后续 `WF-A1-REGRESSION` 的具体保护对象，本轮仅做源代码和断言语义检查：

| A1 要求 | 实际已有测试落点 |
|---|---|
| U1 | `test_input_validation.py`＋`test_rejects.py` |
| P1 | `test_accept_core.py::test_p1_three_layer_reservation` |
| P2 | `test_accept_core.py::test_p2_*` |
| P3 | `test_concurrency.py::test_p3_two_branches_race_for_root_budget` |
| P4 | `test_accept_core.py::test_p4_intermediate_ancestor_budget_binds` |
| P5 | `test_concurrency.py::test_p5_call_limit_race_with_zero_amount` |
| P6 | `test_concurrency.py::test_p6_concurrent_same_key_one_operation` |
| P7 | `test_accept_core.py::test_p7_*` |
| P8 | `test_state_checks.py::test_p8_*` |
| P9 | `test_state_checks.py::test_p9_lock_wait_until_proof_expires_is_rejected` |
| P10 | `test_state_checks.py::test_p10_*` |
| P11 | `test_state_checks.py::test_p11_*`＋F2 DB 回归 |
| P12 | `test_rollback.py::test_p12_*` |
| P13 | `test_migrations.py::test_p13_*` |
| P14 | `test_accept_core.py::test_p14_retry_reuses_original_cost_and_evidence` |

### 5.3 历史缺陷／探针承接

| 历史项 | 本轮独立静态复核 | 后续实跑／绕过变体 |
|---|---|---|
| F1 隔离 | owned schema 标记、随机 scratch、DSN conninfo 解析、普通 DSN 清除和同名不删测试实际存在 | 新 A2 下游 DB和清理须同样保护；新 reviewer 不复用 worker 资源 |
| F2 唯一根及同 ID 重建 | 002、003 与根重建正式测试已读；childless、70000/1、已撤销、同事务 DELETE/reinsert、七表不变触发条件被保留 | 根／task 映射负例继续跑；新增已接受非根路径／操作删除变体映射 P20 |
| F3 subject | service 全路径锁前／锁后检查及首次／同键错误 subject 正式断言存在 | 不能只在新意图路径验证，候选命中仍须拒绝 |
| F4 calls=1 | 应用及002约束存在；0/2/大值/bool/EXISTING计数回归存在 | 四工具和 SETTLE/RELEASE/UNKNOWN 次数一起检查 |
| F5 有界连接／配置 | accept connect_timeout、lock/statement bounds、有限 deadlock重试及连接工厂测试存在 | 新执行／下游／恢复等待与重试也须有界；替身不是网络黑洞证据 |
| 原四项独立探针 | 与正式 F2/F3/F4 测试比较，核心触发和拒绝断言被保留，正式测试部分更强 | 实施验收需复跑原探针或明确记录等价正式覆盖，不得默默跳过 |
| 根重建独立探针 | 正式回归保留无子节点、非零预留、撤销、同 ID 重建，并增强七表全行比较 | 继续实跑，不能以子节点 FK 恰好阻断代替根保护 |
| 非零升级独立探针 | 历史源码硬编码 `["002"]`；正式用例动态推导版本并增加撤销、全七表比较 | 不改历史失败／成功证据；新 004 用正式等价测试，同时补003起点及非法升级全保全 |

历史探针源码指纹：

```text
test_missing_invariants.py
ee232af92406feca833f5915a4e3750c85c63ec261beae538b2981161b9bb75c

test_root_rebuild.py
27d58251dbdd8494333edbf4d6302c44e4d48f7196676458de1850e937564ef1

test_upgrade_nonzero.py
ab58df8e9885f2721bdc0efef444dd2ad8332b0341148e7f64a14f6c0464a391
```

**本轮没有重新关闭任何实施缺陷。**A1 历史关闭状态是前段记录；C1—C6 的设计放行不等于 A2 主体行为通过。

---

## 6. 本轮独立执行与证据

**本轮仅 PACKAGE_REVIEW，未执行未实现行为测试，未创建业务测试资源。**

执行环境为 Darwin／zsh，所有仓库命令 cwd 均为指定仓库根。以下为实际执行的只读核验，不是 pytest 实跑，也不产生业务 PASS 计数。

| 实际命令／程序 | 目标 | 退出码 | 实际结果／计数 | 证据 |
|---|---|---:|---|---|
| `git status --short --branch --untracked-files=all`、`git diff --stat`、`git diff`、`git diff --cached`、`git log --oneline -5`、`git ls-files --deleted` | 工作区、tracked diff、基线 | 0 | 1 个 tracked 修改，＋42 行；staged空；无删除 | 本轮工具输出及第2节清单／diff指纹 |
| `python3 -B tools/workflow_gate.py verify --root . --state tasks/workflow/state.json` | state／授权结构及契约 hash | 0 | `ok=true`、`can_start=true`、`can_accept=false`、`accepted=false`；errors=[] | 本轮实际 JSON 输出 |
| 本轮内存 Python 初次核验程序 | fresh snapshot、21契约逐文件hash、state/issues/diff/status | 0 | snapshot 与 state 完全相同；75项；21契约无 mismatch；31唯一 IDs；28运行 IDs | 第2节完整摘要 |
| `git diff --check`、`git diff --cached --check`、HEAD／branch／untracked 查询 | whitespace、实际基线／清单 | 0 | 两个 diff check 无输出；24普通 untracked | 本轮工具输出 |
| 本轮独立目录遍历／SHA-256／矩阵解析程序 | 不仅信任 gate：另行重建manifest、比较HEAD迁移、解析task表 | 0 | 独立 manifest相同；31行顺序／ID等于正式清单；运行清单等于前28；001—003与HEAD相同 | 第2、4、5节结果和指纹 |
| `docker compose -f compose.test.yaml config --format json` 与 A2 对应命令，经内存程序只输出非凭据字段 | 只读渲染 project、端口、挂载 | 各0 | A1/A2 project不同；55432／55433仅127.0.0.1；tmpfs；volumes=[]；资源创建数0 | 第5节 C1；原始环境值未输出 |
| 本轮结束 hash／Git 核验程序，随后再次 diff checks | 检测审查期间漂移 | 0 | 包／snapshot／contracts／state／issues／diff／status均与开始一致 | 第2节指纹及结束时间 |
| `snapshot` 输出送只读 Python 比较程序，再次重算契约 hash／31ID | 最后包一致性复核 | 0 | `manifest=75`、`contracts_count=21`、`requirements=31`、`runtime_requirements=28`，全部 MATCH | 本轮实际输出 |

### 证据保存方式

- 本轮未创建 owned 探针文件、log、JUnit 或临时目录；**不存在可以虚填的 artifacts 路径**。
- 本轮只读程序的输出、具体结果及指纹随本报告和会话工具记录交主控保存。
- 为便于复现，包指纹核验可在仓库根执行下列只读命令。它只复核包一致性，不验证业务：

```bash
python3 -B tools/workflow_gate.py verify \
  --root . --state tasks/workflow/state.json
```

```python
# 在仓库根以 python3 -B 执行；不写文件、不连接数据库。
import hashlib
import json
import pathlib
import re
import runpy

root = pathlib.Path.cwd()
gate = runpy.run_path(str(root / "tools/workflow_gate.py"))
state = json.loads((root / "tasks/workflow/state.json").read_text())
actual = gate["snapshot"](root)
assert actual == state["snapshot"]
assert actual["fingerprint"] == (
    "bf2717112af336f17f79ebbe499c2610b9394d48daea187ea159ac81b89f4958"
)

pairs = []
for item in state["contract_files"]:
    digest = hashlib.sha256((root / item["path"]).read_bytes()).hexdigest()
    assert digest == item["sha256"]
    pairs.append({"path": item["path"], "sha256": digest})

assert gate["contract_files_sha256"](pairs) == (
    "701a06938365ba0dd74399f1952566d57562bd141dcecdff2398cd8cc45cbef5"
)

task = (root / "tasks/workflow/runs/A2.1-core/task-v1.md").read_bytes()
assert hashlib.sha256(task).hexdigest() == (
    "67896f80e7b80fe05087f88ef08576c805117bfdd12654addff03efadf2bfec4"
)
rows = re.findall(
    r"^\| (A2-[A-Z0-9-]+|WF-[A-Z0-9-]+) \|",
    task.decode(),
    re.M,
)
assert len(rows) == len(set(rows)) == 31
assert rows == state["expected_requirement_ids"]
assert state["independent_run_requirement_ids"] == rows[:28]
print("MATCH: frozen package only; no implementation acceptance")
```

门检查器的 `can_start=true` 是**授权结构结果**；本轮没有用它绕过先获 PACKAGE_READY 的门槛，也没有运行 `--require-accepted`。

---

## 7. 历史证据与未执行项

### 7.1 历史材料的使用等级

| 历史来源 | 材料记载 | 本轮核对内容 | 本轮未独立重跑原因／影响 |
|---|---|---|---|
| A1-review 至 r4 | 历史F1—F5失败、补正、最终146正式测试＋5探针 | 全文读来源；独立读当前代码／正式测试／历史探针，比较触发与断言 | 本轮包审，不作A1当前行为再验收；历史数量不支持本轮行为PASS |
| A2-review-ckpt1 | 首轮C1—C6设计问题及73项记录 | 全文读缺陷及补正要求 | 不复用旧失败或成功结论作为本包 verdict |
| A2-review-ckpt1-r2 | 检查点一设计放行、76项及PG日志核对记录 | 六条主体义务逐项对包／实际基线；确认PG78项是该轮日志核对，不是本轮执行 | 仅提供原始后续义务和历史门槛 |
| A2-report | worker的环境、方案、历史测试声明 | 当作索引；与实际Git、类型、SQL、CI比较 | 不把worker报告视为证明；既有笔误仍开放 |
| setup记录 | 初始workflow配置和门测试声明 | 读其角色／配置边界，与实际gate代码和当前state比较 | 未重新查外部配置或原OpenCode历史DB |

本轮**没有打开并重核历史原始日志/XML的执行结果**；上表是历史文档／探针源码检查，不是“本轮独立实跑”，也不冒称为已完成原始日志核验。

### 7.2 当前未执行范围

| 项目 | 本轮状态／原因 |
|---|---|
| ruff check／format | NOT_RUN：本轮只读包审；未来实施验收必须执行 |
| unit／骨架／docs／integration／A1全回归 | NOT_RUN：没有实施候选，本轮不启动行为测试 |
| Python3.11安装、依赖安装／锁定验证 | NOT_RUN：包审不创建env；未来缺环境不得豁免 |
| 真实PG迁移、重复迁移、非零升级、非法升级回滚 | NOT_RUN：未创建／连接测试DB |
| A2 adversarial probes、全部并发组十轮 | NOT_RUN：本轮评估设计充分性；未来独立验收实跑 |
| 真进程终止／重新启动 | NOT_RUN：未来P04硬门槛 |
| 异常替身、真实DB回滚、真实断网 | 均未运行；没有把任一层次冒称另一层次 |
| TLS部署、wheel部署 | 未运行；不以Compose静态渲染替代 |
| 真实SM2/SM3、B验证器、真签名回执／HTTP | 未运行且后段依赖未闭合 |
| 远程CI | NOT_RUN：没有推送／触发授权；不是本地包审额外阻断条件 |

这些 NOT_RUN 是包审与实施验收的正确分界，既不构成未实现行为失败，也不支持行为成功。

---

## 8. 缺陷、修正要求与问题台账

### 8.1 真实开放问题

| Issue ID／严重度／是否阻断 | 原始要求 | 文件／触发 | 影响与本轮证据 | 具体修正 | 复验／当前状态 |
|---|---|---|---|---|---|
| **DOC-CKPT1-01／低／非阻断** | WF-DOCS-REPORT；r2:22–24 | `tasks/A2-report.md:102` 仍把未跟踪 Compose列入tracked，并声称本轮又追加导出 | 本轮Git确认仅contracts/__init__.py为tracked修改，＋42行；Compose未跟踪。旧报告清单会误导变更／证据归属，但最新包明确纠正，未削弱主体要求 | 主体交付更新A2-report：既有＋42与本轮增量分开；Compose及其他新文件按实际tracked/untracked记录；更新最新门槛／证据索引，避免保留错误现行状态 | 对最终Git／manifest／实际diff逐项核对；**保持 OPEN_NONBLOCKING，本轮不关闭** |

未发现新的实质性包缺陷，未为凑数量制造问题。

### 8.2 已消歧的记录差异，不作为阻断缺陷

- `context.md:51` 和 `stages/A2.1-core.md:3` 保留初始“等待／待用户批准”措辞；workflow README及setup也保存初始状态。它们不是本次真实授权证明。
- 最新 task-v1、state 和本次父任务明确给出 GRANTED、真实消息及仅 A2.1 的范围，要求内容没有因此冲突，本轮可明确消歧。
- 主控不应在保存本报告时顺手修改这些已冻结契约再沿用本次指纹；若修正文档，应按契约重新冻结并新开审查。当前实施指令须明确以已核真人授权及 task-v1 为准，而不是让 worker自行解释旧状态。
- 旧 A2-report 中固定 Compose操作与 r2“同项目”说明不能授权复用旧资源；本包的新独占资源规则优先且更严格。

### 8.3 历史问题状态

- A1 F1—F5：保留前段历史关闭记录；本轮已重新静态检查相关实现、断言和绕过变体，但**没有以包审宣布当前实施回归 PASS**。
- C1—C6：保留历史设计放行；所有主体义务仍在31ID内，不关闭、不移出。
- DOC-CKPT1-01：如上开放。
- 后段 B缺口：保留后续门槛／未闭合状态，不作为本段核心包阻断，也不说已完成。

---

## 9. 资源与结束核验

- **本轮自建目录／env／容器／Compose project／DB/schema：无。**
- **数据库连接：无。**没有使用 worker数据库、共享schema或现有测试库。
- **DSN处理：**只读Compose渲染子进程移除了普通／TEST DSN及Compose覆盖变量；未打印DSN、密码、token或key。其他只读核验未消费数据库环境变量。
- **清理：无。**没有资源创建，不执行任何 `down`、`rm`、DROP、TRUNCATE、prune或批量stop。
- **既有资源：**未对既有容器／数据库发出运行、迁移或清理命令；未把“未操作”夸大为独立检查过其全部持久数据前后摘要。
- **受审文件：**没有编辑或创建仓库文件，Python核验均使用 `-B`。
- **结束核验：**包、完整snapshot、21契约、state、issues、staged/unstaged diff及完整Git状态与开始一致；最后一致性复核仍为 MATCH。
- **漂移／冻结失效：未发现。**

---

## 10. 交主控的明确动作

1. 原样保存完整 Markdown 为本次 `package-review-rN.md`，关联真实本次 reviewer session／Task元数据；不要补造不可观测元数据。
2. **不要将本报告填入 `state.review`，不要设置 A2.1 ACCEPTED，不使用包审通过 `--require-accepted`。**
3. 主控核对已验证真人授权、scope、task-v1及本报告指纹；运行规定授权门，确认退出0和`can_start=true`后，才派发新的 MiMo实施会话。
4. 实施者保留既有工作，遵守文件所有权与独占资源要求；纠正 `DOC-CKPT1-01`；提交完整31ID实际实现／函数／命令／结果／原始证据索引。
5. 实施完成停写，冻结完整候选版本，再由 **NEW reviewer** 执行 `IMPLEMENTATION_ACCEPTANCE`：全部必跑验证、历史探针或等价断言、绕过变体、确定性并发十轮、真实进程恢复、迁移保全及全阶段回归。
6. 缺必需环境／证据时按契约报告 BLOCKED，不用本轮 PACKAGE_READY作豁免。
7. A2.1完整技术接受后仍停下给用户查看与审批；**不进入A2.2／A2.3／A3，不进行Git发布。**

## 最终包审 verdict

**`PACKAGE_READY`**

仅绑定本报告列出的 task-v1／snapshot／contract指纹，表示当前 Markdown任务包足以支持授权范围内的 A2.1-core实施与后续严格独立验收。**不表示任何未实现 A2行为已经通过，也不表示 A2.1、完整 A2或项目已被接受。**
