# A2.1-core 任务包 v1

- 状态：APPROVED_SCOPE / 待独立 PACKAGE_REVIEW；未通过包审不得实施。
- 仓库绝对根：`/Users/qdcc/code/密码技术竞赛/agent-guard`。命令以此为cwd，文中相对路径以此为根。
- 真实授权：role=user，session=`ses_f0ac0e676ffecn71p6Ww7zaqQq`，message=`msg_0f54148e0001ZW7yCMdK0TE97F`。主控已从OpenCode数据库只读查询角色、session和原文。
- 原文：“批准 A2.1-core，按冻结的 Markdown 任务包完成主体、详细独立复核、所有补正和再复核。核心通过后停下来给我查看与审批，不进入 A2.2，不 commit/push/PR/合并。”
- 基线HEAD=`b120c7cf5ec0eafb18305d1207c36dd11655b324`，分支=`feat/a2-execution-gateway`。基线实际manifest与contract hashes由state.json保存，包自身及之后包审结果另绑定SHA256。HEAD不代表未提交工作。
- 实施者：新建 mimo-implementer / MiMo 2.6 Pro，一个writer，无嵌套委派。主控拥有架构/工作流状态/最终接受，实施者不编辑workflow控制文档。
- 包审：NEW reviewer-auto，review_kind=PACKAGE_REVIEW；审需求/接口/隔离及验证设计，不要求未实现行为先跑通。返回PACKAGE_READY后主控运行授权门检查再实施。
- 后续验收：每轮NEW reviewer-auto，review_kind=IMPLEMENTATION_ACCEPTANCE；独立自有资源实跑完整矩阵和反例，不能只认可worker报告。

## 必读路径（全文）

AGENTS.md、AGENT.md、README.md；tasks/workflow/README.md、state-guide.md、context.md、state.json、implementation-contract.md、review-contract.md、issues.md、stages/A2.1-core.md、templates/implementation-report.md；tasks/A2-execution-gateway.md、A2-report.md、A2-review-ckpt1.md、A2-review-ckpt1-r2.md、A1-review-r4.md；docs/security-model.md、oauth-oidc-sm2-mvp.md、acceptance.md。同时读实际contracts/ledger.py与execution.py、ledger全部模块、001—003、测试/隔离fixtures与CI。摘要不得替代原始断言，歧义先报告。

## 目标、所有权、现有工作与禁止事项

一段完整核心：004迁移；可信合成资源/报价与四工具严格参数校验；独立数据库/事务的持久模拟下游；执行、全祖先结算/释放、UNKNOWN恢复；owner/fencing/state/expiry租约；稳定待签outbox；有效回归、说明与报告。缺B不阻碍可信对象分层核心，不冒充真实密码。

既有tracked改动：contracts/__init__.py新增42行。既有untracked：compose.a2.test.yaml、contracts/execution.py、test_execution_contracts.py、A2任务/报告/两轮review；workflow/与tools/workflow_gate.py为主控控制文件。必须保留，不能reset/clean或用旧B分支覆盖。

实施者允许路径：src/agent_guard/execution/**、tools/**（此处为src下业务tools，不是根tools控制工具）、contracts/execution.py及必要加法导出；migrations/004*；tests/**中A2正式测试与必要原回归兼容（不降低断言）；compose.a2.test.yaml；README.md；tasks/A2-report.md；pyproject.toml、constraints.txt或uv.lock（若引入依赖先说明目的/版本/许可/维护及Python3.11安装）。必要新增设计说明放实施报告，不重写原安全/协议/验收或改变冻结ID。

ledger除必要migrate.py兼容外只读；发现需兼容改动先向主控报告调用方/范围/回归，不得擅自修改accept签名。001—003、A1不可变契约语义、B代码/依赖、workflow/**及根tools/**实施者只读。可写专属artifacts/workflow/A2.1-core-impl-<unique>/证据及runs/A2.1-core/implementation-r1.md完整报告；不能编辑任务包/授权/问题台账/审查报告。

禁止commit/push/PR/merge/reset/clean/rebase、修改Git身份/保护、共享清理、生产假验权/假签名开关。不启动A2.2/A2.3/A3、不引入/复制/修改B代码、不实现公网recover/settle/release管理入口。新迁移范围需超过004*时先向主控提出原因，不擅扩授权。

## 冻结验收矩阵：31项，逐项报告

下列前28项运行类按state.independent_run_requirement_ids完整核对；静态末三项也要实际查证。建议新增tests/integration/test_execution_*.py、test_downstream_*.py、test_a2_migrations.py及tests/unit/test_tool_validation.py；具体函数由实施者落实并在报告逐ID映射，不用合并大PASS覆盖多个缺失场景。

| ID | 完整要求/必要验证（同时继承原任务同ID全部断言） |
| --- | --- |
| A2-P01 | 三层订单70000/1成功，唯一真实下游效果；根/中间/叶reserved归0，settled70000/1；RESERVE和SETTLE各一，终态/outbox一致 |
| A2-P02 | 下游持久终局拒绝，FAILED、全路径释放不结算，RELEASE一条；该键不能迟到成功 |
| A2-P03 | 读取/通知金额0但次数预留结算或释放正确；通知持久效果最多一次，读结果固定 |
| A2-P04 | 接受提交前不得执行；提交后真独立子进程终止/重新启动，从持久状态恢复而非finally补救；保留pid/同步与DB断言证据 |
| A2-P05 | 下游订单已提交响应丢失→UNKNOWN额度保留；同键恢复唯一订单、一次结算 |
| A2-P06 | 下游成功、网关终局前崩溃；恢复无重复效果/账本/终局 |
| A2-P07 | 终局事务节点/事件/outbox中途注入异常；全状态/计数/事件/outbox原子回滚，之后可恢复 |
| A2-P08 | 查无结果后旧请求迟到成功；不释放，最终唯一效果和SETTLE |
| A2-P09 | 双恢复者、过期旧worker竞争，独立连接barrier/event每组10轮；终态不被覆盖、一个终局/一个outbox |
| A2-P10 | 接受后祖先撤销/过期/key停用，内部恢复可完成原意图；外部接受重试仍拒绝；真实授权查询后段保留BLOCKED |
| A2-P11 | 当前报价改/删后的已有意图使用原成本/快照；新键要求有效报价；确定性miss→另accept→报价消失→安全重查命中；变grant/holder/参数、撤销、proof重放仍拒绝 |
| A2-P12 | 下游金额/意图/完整快照错配且可能有效果→UNKNOWN保留预算，无伪成功/释放 |
| A2-P13 | 根/中间不足或次数耗尽及接受/结算/恢复并发，10轮、全祖先不超限不负数、不反向锁/死锁无界 |
| A2-P14 | 下游同键同意图和冲突、订单/通知均防重复，执行/查询无或错独立服务凭据拒绝、零泄漏/效果；不能只藏端口 |
| A2-P15-CORE | 四个完整工具ID/版本，重复JSON键/SKU、bool/负/浮点/溢出数量、缺/空集合、scope不足、跨租户/关联错/URL路径注入、快照/祖先包含错等分层负例，零预留/效果。可信fixture授权不是真实验签 |
| A2-P19 | 001及003真实非零预留/撤销/证据升级到004，七旧表全行及完整迁移登记在非法升级时不变；合法重复迁移no-op；旧材料不足sidecar隔离保预算，不能补当前报价执行 |
| A2-P20 | 直接SQL改意图/成本/证据、删除重建路径/操作、改删事件/节点、阶段seq绕过、非法状态/双终局拒绝，旧账本不变；合法预算/撤销/状态UPDATE可用 |
| A2-CKPT1-OBL01 | 候选前schema/静态授权/可信集合，不要求当前报价存在；命中原快照关联+当前权限后仍A1 accept锁后复核/proof/意图 |
| A2-CKPT1-OBL02 | 确定性P11安全重查，包括任意资源/报价解析失败，而非仅金额错误；新键及失效/重放/变意图负例 |
| A2-CKPT1-OBL03 | 可用候选完整持久接受事实；永久不可改删事件+非级联FK或明确DELETE保护防删操作，异常旧行隔离；P20不能靠doc承诺 |
| A2-CKPT1-OBL04 | claim/终局owner+version+合法state+锁后DB有效expiry；无新owner时旧worker过期也拒绝；UNKNOWN保持且不释放未知预算 |
| A2-CKPT1-OBL05 | sidecar不改七旧表、phase/seq CHECK、事件/节点UPDATE/DELETE保护、非法升级全数据和迁移登记保全，合法更新/测试自有清理兼容 |
| A2-CKPT1-OBL06 | 下游执行/查询完整原快照持久化比对；不一致UNKNOWN；不可变outbox、receipt_id/created_at稳定、UTC整数秒iat；缺B PENDING且无伪编码/SM3 |
| WF-A1-REGRESSION | A1原全部unit/PG集成独立实跑并保留U1/P1—14/F1—5语义与根重建、非零升级断言；不硬编码旧测试计数 |
| WF-INDEPENDENT-PROBES | 最终reviewer独立设计绕过/边界探针，保存本轮可复现源与实跑日志；worker不替reviewer选择唯一反例 |
| WF-QUALITY-CHECKS | ruff check/format、diff、全unit/骨架/docs/PG实跑；新增目录显式纳入CI；缺库报错不skip |
| WF-PY311-ENV | 实际Python3.11、依赖安装/约束和真实PG验证；历史CI/本机3.14不能替代。本轮无授权触发远程CI，NOT_RUN不额外阻断但Python3.11本地必须验证 |
| WF-RESOURCE-ISOLATION | worker及reviewer各自独立project/唯一容器/DB/schema，记录归属label、来源、挂载/端口、普通DSN清除、安全目标；前后无关资源不变，清理仅owned |
| WF-IMMUTABLE-BASELINE | 检查001—003内容checksum、A1语义、合法更新、无B代码/依赖偷渡。必要接口兼容须主控确认 |
| WF-DOCS-REPORT | 报告tracked/untracked误措辞纠正，31ID→具体断言/函数/命令结果，README可复现初始化/worker/下游/测试/清理；真实网关缺B不可装配启动，CI不漏新测试 |
| WF-SNAPSHOT-COVERAGE | 主控/reviewer查完整tracked/untracked/deleted及契约SHA256，冻结开始/结束一致；无active writer才review，证据与报告指纹绑定 |

## 关键设计（全部需落盘，不仅声明）

1. 保留同步psycopg、A1 accept(verified,cost)；候选操作永不删除由DB保全实证。候选读miss→报价失败可安全重查，不直接EXISTING返回绕验权；只有新意图取当前有效报价。主控已接受r2解释但核心必须测试。
2. 四工具完整ID：procurement.request.read、procurement.document.read、procurement.order.create、notification.template.send，版本字符串1；严格类型/资源归属/权限集合。A2.1仅可信fixture分层；B负责规范编码/密码，普通JSON结构化持久化不得称RFC8785。
3. 下游同PG实例不同数据库/连接/事务，与网关独立；效果+意图+原报价+结果+终局拒绝原子持久化，唯一operation_id；独立服务secret执行/查询认证。确认失败须持久拒绝该键后续成功，查不到/断连不等于失败。
4. 接受提交后才执行，无DB锁跨网络/下游调用。全局锁序保持principals(如需)→task→根至叶grants→operation→lease；终局内部不用失效用户proof创建新意图，仅原接受事实恢复。所有混合锁路径不得反向获取。
5. RESERVED claim→EXECUTING；过期EXECUTING接管先对账；UNKNOWN取租约但保持UNKNOWN；活跃他人租约/终态/隔离操作无变更。终局owner/fencing/state/DB时效四条件，不能单version；旧worker迟到不覆盖新owner或终态。
6. SETTLE原金额/1从reserved转settled、RELEASE仅减reserved（金额0仍处理calls）；全祖先、操作终态、互斥终局事件、待签outbox同一网关事务。004 phase与seq绑定RESERVE0、终局1并防改删。
7. 原七表不加隔离字段，sidecar处理旧材料不足；旧行/迁移记录保全。合法已接受路径防删，不清零或补造。outbox稳定receipt_id/created_at与不可变材料；UTC整数秒iat由持久时刻派生；签名未实现保持PENDING、UNKNOWN无终局回执。
8. B最新已知77e3570基础原语已有但未验收，完整invoke/result-read、scope/grant/token/祖先快照绑定与证据/回执接口不足。本阶段不fetch/merge/import B来绕依赖，不创建HTTP假验权入口；P16/17真验权、P18真签名、P21HTTP保留后阶段BLOCKED而不计为本段PASS。

## 环境验证、证据与停止

先确认Python3.11可用，若需创建专用venv与安装只能在核实父目录后于自有artifact/env执行；不修改全局Python/Git配置、不从不可信脚本安装。若环境缺失，明确BLOCKED并报告，不换3.14冒称通过。使用TEST DSN、清除普通AGENT_GUARD_DATABASE_URL，日志屏蔽所有DSN/密码/token/key；使用psycopg连接参数不打印secret。

worker资源使用独立于已存在agent-guard-a2-pg的唯一project/容器（或先确认独占命名空间归属），reviewer另建自己的资源；先只读保存无关容器状态，不prune/批量stop/共享down。日志、XML和诊断写artifacts/workflow/A2.1-core-impl-<unique>/；资源归属与清理也留证据。历史probe在本轮隔离目标复验，若版本断言过时用等价完整回归并解释差异，不修改历史失败证据。

实跑命令至少：Python3.11安装可编辑包与锁定dev依赖；python -m ruff check .；python -m ruff format --check .；git diff --check；python -m pytest tests/unit tests/test_scaffold.py tests/test_docs.py --junitxml=<证据>；env -u AGENT_GUARD_DATABASE_URL python -m pytest tests/integration --junitxml=<证据>。额外目录如新增必须在报告和CI明确运行。真实进程终止/重启和10轮并发组不能只异常替身或sleep。

交付runs/A2.1-core/implementation-r1.md按implementation-report模板完整31项矩阵、命令/退出码/pass/fail/error/skip、实际文件清单与证据索引；更新简短A2-report。可以自查标CORE_READY_FOR_REVIEW/READY_FOR_REVIEW，不标ACCEPTED。所有writer停止后交主控冻结。缺必需实跑或阻断项标BLOCKED，不省略。

独立review后同阶段自动补正并fresh reviewer再验；不得放松ID/断言/权限边界。核心完整接受后主控保存acceptance、维持current_stage=A2.1-core并停等用户，完整A2仍PARTIAL；不进入A2.2，不Git发布。
