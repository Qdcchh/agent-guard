# 问题与独立复验账本

## 当前：完整A2 r1 NOT_ACCEPTED，补正r2包审待执行

- **A23-R1-PUBLISH-QUOTE-ARITHMETIC / P2 / OPEN_CONFIRMED**：正常SQL immutable UPDATE被拒；仅在自有CorruptRow故障fixture同时改变quote/result单位价、保留原total/首次证据/params/ledger/DS，source/wheel真实publisher仍签并commitREADY、SDK接受而当前query503/新proof登记回滚。完整state证明仅publication三列变化；恢复原材料同proof200→409。触发/原件/补正要求见正式review-r1.md（原样保存）。新补正包待独立PACKAGE_REVIEW，worker不自闭；必须新完整119/112 reviewer复验。
- **A23-R1-SOURCE-FULL-GREEN / REQUIRED_COVERAGE_GAP / OPEN_NOT_RUN_COMPLETE_GREEN_SOURCE**：本轮source完整未全绿（2798P1F真实短proof跨秒；中断r4/r5原件保留），wheel完整2799P不能替代source。所有新候选必须source/wheel完整实跑。原容量/格式项在整体未接受期间继续FIXED_PENDING_FULL_REVIEW，独立r1观察不冒称全A2接受。

- **A23-R1-STALE-HISTORICAL-COMMENTS / P3 / OPEN_NONBLOCKING**：CODEOWNERS旧管理员例外注释、execution旧B缺失/PENDING-only docstring及crypto-profile-v1历史交付/current header；仅准确说明与引用补正，有效CODEOWNER规则/其余AST/规范密码参数保持。

以下为各时点历史记录。

## 2026-10-05 本次恢复A2

真人[恢复授权](runs/A2.3-receipts-20261004/user-resume-20261005.md)覆盖旧停止。现行容量/格式仍FIXED_PENDING_FULL_REVIEW，上界标签待本轮独立核闭；[sole29联合整合与完整自查](runs/A2.3-receipts-20261004/implementation-resume-r1.md)已完成并原生STOP，CI预算45→75已另经独立小包审查并应用；NEW119/112独立验收尚未执行，不据分段自查关闭。下方各轮历史状态保留，不覆盖当前state。A3本次不实施。

## 2026-10-05 A2.3 包审文档补正

[v1包审](runs/A2.3-receipts-20261004/package-review-r1.md) PACKAGE_READY，无阻断；[新r2包审](runs/A2.3-receipts-20261004/package-review-r2.md)完整119/112 PACKAGE_READY；无阻断。CURRENT-DOC-STATE实质错误CLOSED_REVIEWED_R2；STALE-PLANNING与PROVENANCE-LABEL在该历史r2时PARTIALLY_FIXED_OPEN_NONBLOCKING_R2，后由capacity-r1独立核证补正CLOSED_REVIEWED_CAPACITY_R1，完整残余位置见报告§8，coreSTOP后的新消费者包补正并由新reviewer核验。不得虚闭。

- A23-PKG-R1-STALE-PLANNING：正式owner和已接受A22节点绑定替代过时占位说明。
- A23-PKG-R1-PROVENANCE-LABEL：v3历史来源哈希保留并明确标历史，v2现行来源重新哈希。
- A23-PKG-R1-CURRENT-DOC-STATE：README/接口/交接/上下文显示A22实际接受、CI-only新提交与A23仅规划的真实状态。


## 2026-10-05 当前 A2.2：fresh r2 ACCEPTED

[review-r2](runs/A2.2-integration-20261004/review-r2.md)及[主控接受](runs/A2.2-integration-20261004/acceptance.md)：95 PASS/88独立运行，source/wheel各1022＋1930正式通过，最终1072独立增强通过；原生COMPLETED、完整285与Git无漂移、owner余留0，619原始证据经主控读回。

- **A22-R1-RESULT-ERROR / P2 / CLOSED_REVIEWED_R2**：真实持久结果损坏503、未知typed/runtime500、同proof修复200→409及全业务/DS3零变化独立通过。
- **A22-R1-SHORT-WINDOW / P2 / CLOSED_REVIEWED_R2**：真AS父子安全收窄、真实跨秒、四窗口正负每组10轮及目标DB deadline/全四计数独立通过。
- **A22-CTX-FIRST-BINDING / CLOSED_REVIEWED_R1，REGRESSION_VERIFIED_R2**：16同形字段拒绝及过期原proof合法新query保持。

没有本轮新增已确认阻断产品缺陷。下方为对应历史版本的当时状态，不覆盖本节；所有失败、中断、适配与历史报告保留。A2.3仍须最终fresh完整验收，A3本次仅规划，Git/main以实际CI与审核为准。

## 2026-10-04 当前权威闭环：fresh r2 ACCEPTED

[完整review-r2](runs/local-remediation-20261004/review-r2.md)和[主控接受记录](runs/local-remediation-20261004/acceptance.md)：67项全PASS、60项独立运行，247项候选首尾一致，303证据hash经主控读回；声明范围内已知阻断清零，整体PARTIAL。以下旧轮记录保留当时状态，不覆盖本段。

**CLOSED_REVIEWED_R2**：A21-R1-OUTCOME、BR-FINAL-ITEM-LIMIT、BR-FINAL-RECEIPT-DUPLICATE、BR-FINAL-P13-ORACLE、BR-FINAL-RECEIPT-TEST-BRANCH、BR-FINAL-P13-TIMEOUT-CONTROL、LOCAL-DOC-CLEAN-CHECKOUT。最后一项P13残余经单阻塞参与者修正、独立60调度/负控及多线程/真实PG全回归确认；未删弱义务。LOCAL-DOC-LINK修正已在干净检出docs复验；LOCAL-WORKFLOW-EVIDENCE当前67/60义务按已批准适配闭合，缺失云端原件与旧P11未知根因限制继续保留，不冒称恢复。

Git发布与main合并仍须满足必需CI及正常独立审核；此关闭不授权后段开发、部署或保护绕过。

## 2026-10-04 r3交付待新独立验收

[implementation-r3](runs/local-remediation-20261004/implementation-r3.md)已停写，BR-FINAL-P13-TIMEOUT-CONTROL为FIXED_PENDING_REVIEW。只改变超时负控为单真实阻塞参与者，其他多线程正负控制及P13四组各10轮保留；60控制、6 oracle、952非集成、P13/Ruff/diff均实施自查通过。主控核63证据hash、单文件范围与Git暂存/HEAD不变；不以自查关闭问题，待fresh完整67/60复核。

## 2026-10-04 窄补正 r2 后残余与 r3

[implementation-r2](runs/local-remediation-20261004/implementation-r2.md) 保留当时自查交付。主控读回指出单线程延后变体，[diagnostic-r2](runs/local-remediation-20261004/diagnostic-r2.md) 在独占Python3.11中10/10确认同一 BR-FINAL-P13-TIMEOUT-CONTROL 残余：peer先超时，blocked无法进入。仍 OPEN_CONFIRMED，不启动r2候选的完整验收；按[correction-r3](runs/local-remediation-20261004/correction-r3.md)单文件职责隔离补正，保留多线程其他负控及P13整组义务。未发现新的业务源缺陷。

## 2026-10-04 本轮独立 r1：原缺陷已修，新增负控调度问题

[完整 review-r1](runs/local-remediation-20261004/review-r1.md) 对241项冻结候选独立完成67项/60项运行义务，64 PASS/3 FAIL，结论 NOT_ACCEPTED。source与严格锁定构建的非editable wheel各952非集成+1388 PG通过，原始失败、等价探针、环境编排偏差及资源清理均保留。请求 gpt-6-astra/high，后台有效元数据 UNKNOWN，使用真人已批准的有限适配。

- **CLOSED_REVIEWED_R1**：A21-R1-OUTCOME、BR-FINAL-ITEM-LIMIT、BR-FINAL-RECEIPT-DUPLICATE、BR-FINAL-P13-ORACLE、BR-FINAL-RECEIPT-TEST-BRANCH、LOCAL-DOC-CLEAN-CHECKOUT。原五项触发和变体已独立实跑；不代表整个候选已接受。
- **BR-FINAL-P13-TIMEOUT-CONTROL / P2 / OPEN_CONFIRMED**：`tests/unit/test_execution_concurrency_oracle.py:70-71` 在50ms有界timeout后错误要求blocked回调已开始。受控延迟启动10/10正式断言假失败；oracle正确报timeout，未发现业务绕过或假PASS。影响WF-QUALITY-CHECKS、B-15-CONCURRENCY-TEST-EFFICACY、B-17-B-SUITE-QUALITY。按[窄补正r2](runs/local-remediation-20261004/correction-r2.md)建立确定性进入/启动同步，保留所有超时/完整性/异常/清理断言，再交fresh reviewer整段复验。
- **LOCAL-WORKFLOW-EVIDENCE / VERIFIED_FOR_R1**：当前67/60义务和历史等价证据已独立核验；缺失原云端日志仍未取回，不冒称原件，旧一次P11异常根因不可追溯的历史风险保留。

下面各段为对应当时版本的历史记录；当前优先读取本段和本轮state。

## 2026-10-04 当前 B 整合候选补记

本段只追加当前候选的质量发现，不改写下文历史 r8 关闭证据。详见 [本地质量复核](runs/local-quality-20261004/review.md)。基线 HEAD `2051b40` **NOT_ACCEPTED**。用户随后批准修复与运行适配；[本轮包审](runs/local-remediation-20261004/package-review-r1.md) 已 PACKAGE_READY，当前实施进行中，尚无正式 issue 关闭。

| ID | 当前候选状态 | 本轮证据 |
| --- | --- | --- |
| A21-R1-OUTCOME | REOPENED_LOCAL_DIAGNOSTIC / 阻断 | 订单、通知 read 形状误 SETTLE 两项纯函数失败；不冒充 PG 生命周期实跑 |
| BR-FINAL-ITEM-LIMIT | OPEN / 阻断 | 257 项 params 未拒绝而持久快照拒绝；256 正控制通过 |
| BR-FINAL-P13-ORACLE | OPEN_STATIC_CONFIRMED / 阻断 | worker 异常漏收集及错误码未限定；本轮未跑并发负控 |
| BR-FINAL-RECEIPT-DUPLICATE | OPEN_STATIC_CONFIRMED / 阻断 | 离线祖先路径未检查全路径 grant 唯一性；本轮未复跑真实签名反例 |
| BR-FINAL-RECEIPT-TEST-BRANCH | OPEN_STATIC_CONFIRMED / 覆盖缺口 | future-token 被通用 future 前缀分支遮蔽 |
| LOCAL-DOC-LINK | 文档已修正，验证见当前报告 | README 原本引用未交付的 B 修补报告 |
| LOCAL-DOC-CLEAN-CHECKOUT | FIXED_PENDING_REVIEW | 文档收尾新增验收页链接指向Git忽略artifacts，本地存在检查不足；须改可交付入口并在不含artifacts的精确干净副本实跑docs检查，见本轮correction-docs-r1 |
| LOCAL-WORKFLOW-EVIDENCE | ADAPTATION_GRANTED / VERIFICATION_PENDING | 正式包和包审已完成，用户已批准有限运行适配；历史原件/缺失证据的等价补齐与完整独立运行仍待核验 |

下方“当前权威状态”等措辞仅在原 A2.1 历史阶段范围内有效，不能覆盖此 B 整合候选的未关闭问题。

状态日期：2026-10-01。检查点一C1—C6设计/类型补正已被A2-review-ckpt1-r2.md技术放行；这些主体行为尚未实现，已作为A2-CKPT1-OBL01—06保留在A2.1-core任务和必需矩阵，不能因历史设计放行而省略实现复验。

## 当前记录

| ID | 来源/范围 | 状态 | 处理与复验要求 |
| --- | --- | --- | --- |
| DOC-CKPT1-01 | A2-report.md 变更清单笔误 | OPEN_NONBLOCKING | 下一主体实施纠正tracked/untracked与重复导出措辞；review读Git实际状态确认，不能伪报新增导出 |

## 每轮追加规范

## 首轮实现审查中断后的发现索引（尚未正式结论）

2026-10-01：reviewer session `ses_f0a2fe2deffeJ426h91wyVZ6yC` 因额度失败终止，没有完整返回Markdown，不能算已完成验收。代码快照仍为 `b2ad9065b9d24a3e71f6f3e27a42416326da2a8c9bd0cbfa3d6be9003c279288`。保留原目录 `artifacts/workflow/A2.1-core-review-r1-8a71f3bc/`，以下为主控核对其真实日志/JSONL所得的待新reviewer独立确认项，不用它们冒称新轮独立实跑PASS。未形成修正或关闭记录。

| ID | 需求/触发与观察 | 证据 | 状态/复验要求 |
| --- | --- | --- | --- |
| A21-R1-LOCK | P09/P13：claim实际先FOR UPDATE operation再task/grants，终局相反；10轮均观察DeadlockDetected | probe-observations.jsonl 1—10；execution/service.py _claim；probes/ | OPEN_PENDING_CONFIRMATION；确定性锁反转复现，修正全局顺序并10轮验 |
| A21-R1-LEGACY | P19/OBL03：直接worker入口未自动验证/隔离extra/malformed params、missing snapshot/evidence、错误item/quote及不完整RESERVE，产生订单/终局或释放 | 同JSONL 11—18；entry.log/xml | OPEN_PENDING_CONFIRMATION；每个入口接受事实保全、异常旧行保留预算无效果 |
| A21-R1-OUTCOME | P02/P12/OBL06：别的operation_id成功/拒绝被接受；missing effect、未绑定result、字符串拒绝/bool金额未拒；错误键拒绝释放后原键仍能下单 | 同JSONL 19—24 | OPEN_PENDING_CONFIRMATION；完整typed outcome/operation/effect/result/quote绑定及UNKNOWN |
| A21-R1-NOTIFY | P15-CORE：通知目标不存在/跨租户/other-grant仍接受并实际通知 | 同JSONL 25—27 | OPEN_PENDING_CONFIRMATION；可信操作存在/租户任务/访问权真实查证 |
| A21-R1-CHAIN | P15-CORE：截短可信约束链仍接受 | 同JSONL 28 | OPEN_PENDING_CONFIRMATION；完整root→leaf与DB父链对应 |
| A21-R1-LOG | WF-RESOURCE/QUALITY：worker错误输出泄漏合成secret marker | 同JSONL 29 | OPEN_PENDING_CONFIRMATION；错误与日志脱敏，原异常不回显 |
| A21-R1-BOUNDS | P08/F5：下游lock_timeout/statement_timeout均0，实际锁阻塞需取消owned backend | 同JSONL 85/108；deadline.log/xml | OPEN_PENDING_CONFIRMATION；连接后SQL等待上限、失败未知不释放 |
| A21-R1-EVENT | P20/OBL05/06：已提交RESERVE或SETTLE事件仍可append第四节点，outbox未同步 | 同JSONL 86—87；followups.log/xml | OPEN_PENDING_CONFIRMATION；插入/完整性/封存边界保护不可变全路径 |
| A21-R1-CANDIDATE | P11/OBL03：候选quote身份不一致仍EXISTING未隔离 | 同JSONL 114 | OPEN_PENDING_CONFIRMATION；候选完整成本/快照字段一致性 |

同目录也保留已跑全套日志、P11拒绝变体50轮、真实进程SIGKILL/重启、部分终局回滚、四种升级保全等正向证据；新reviewer必须区分历史核对与自己实跑，不能丢弃反例或用正向抵消阻断。中断reviewer自建两容器/网络仍在，归属owner=`a21-review-r1-8a71f3bc`，先核对resources.json与真实ID/label，限定清理本工作流owned资源，不动既有A2/verivote。

## r2正式确认（2026-10-01）

完整报告：`runs/A2.1-core/review-r2.md`；NEW session=`ses_f09c688edffenINjKt4oOU8erV`，实际模型openai/gpt-6.1-sol。结论NOT_ACCEPTED；完整31矩阵及本轮所有实跑见报告。自有资源已清理，r1遗留资源也按owner/ID精确清理；旧“仍在”为中断时历史记录。证据根 `artifacts/workflow/A2.1-core-review-r2-c6d39e12/`，evidence-index.json与probe-observations.jsonl保存每项路径/哈希、实跑观察及触发位置。

上表九项A21-R1-*全部升级为 **OPEN_CONFIRMED_BLOCKING**（高/中严重度见review §8），新增加 **A21-R2-SNAPSHOT / OPEN_CONFIRMED_BLOCKING**：catalog快照解码以int/str强转及普通JSON接受bool/浮点/数字字符串/重复未知字段/null、负数乘积等，违反严格存储模式；须精确类型/范围/字段/唯一SKU/总额检查且旧材料失败自动隔离保预算。DOC-CKPT1-01仍OPEN_NONBLOCKING，报告清单/数量/阶段笔误及README可复现初始化说明需一起修正。

每项修正包均为 `runs/A2.1-core/correction-r1.md`，实际变更/自查待MiMo记录；当前未修复、未关闭。后续fresh reviewer须独立复验所有历史trigger与变体、全矩阵回归，不靠正式137/184项全绿抵消反例149不同case中的52项失败。

## correction-r1已交付，等待r3独立复验

MiMo同一workflow session停写，完整报告 `runs/A2.1-core/implementation-r2.md`。上述10个代码issue及DOC-CKPT1-01现均标 **FIXED_PENDING_REVIEW**，不写CLOSED。新增005不修改001—004，98项正式拒绝回归；worker自查Python3.11 unit137/PG282通过、README烟测SMOKE_OK，只是实施证据。

变更/证据按issue对应：LOCK非锁定位统一锁序；LEGACY所有入口verify_accept_facts持久隔离；OUTCOME稳定key/result/type/effect绑定；NOTIFY可信DB同grant/holder访问；CHAIN追加chain_grant_ids对应DB完整路径；LOG safe_reason；BOUNDS有限SQL连接设置/真锁timeout；EVENT005节点shape+deferred完整集合；CANDIDATE成本/参数/快照身份全一致；SNAPSHOT严格解码；DOC当下真实清单/README流程。自查证据根 `artifacts/workflow/A2.1-core-impl-correction-20261001c1/`。r3须独立复验原trigger/绕过变体、005含旧库升级边界及全31项，不以新增回归数量替代语义。

## r3独立结果及当前准确状态

完整 `runs/A2.1-core/review-r3.md`，NEW session=`ses_f0970a878ffegigoOO59gEQydI`，实际openai/gpt-6.1-sol；snapshot3814a5869984e334d12aa768a7aefbbc88a98f617ed519064af4b918fb471aba，结论NOT_ACCEPTED。证据根 `artifacts/workflow/A2.1-core-review-r3-936bc079/`；主控核对完整evidence-index哈希及final XML，正式137/282通过、独立216case中60失败。下表取代上方“全部pending”的历史状态，所有触发/修复/历史证据仍保留。

| Issue | 当前状态 | 独立关闭或残余依据、下一复验要求 |
| --- | --- | --- |
| A21-R1-LOCK | CLOSED_REVIEWED（绑定r3） | 非锁定位统一顺序，独立保留旧触发能力10轮精准终局/计数/outbox无deadlock；正式测试效力另列TESTSYNC，不因此撤销代码修复事实 |
| A21-R1-NOTIFY | CLOSED_REVIEWED（绑定r3） | 不存在/跨tenant/task/holder/grant拒绝，合法目标和10轮通知正常；最小策略未扩大 |
| A21-R1-CHAIN | CLOSED_REVIEWED（绑定r3） | 全DB链绑定，省mid/leaf-only/重排/错层/拼接拒绝，根/中/叶正例保持 |
| A21-R1-LOG | CLOSED_REVIEWED（绑定r3） | malformed DSN及secret异常stdout/stderr/reason脱敏实证；只限已测路径 |
| A21-R1-BOUNDS | CLOSED_REVIEWED（绑定r3） | 真实锁自动约5秒timeout，未cancel；正常执行query和非法配置回归 |
| A21-R1-LEGACY | OPEN_CONFIRMED_RESIDUAL | 原8类已隔离；深层快照RecursionError及params quote错身份仍漏flag，所有入口保预算零下游须闭合 |
| A21-R1-OUTCOME | OPEN_CONFIRMED_RESIDUAL | basic键/type已修；order/notification/read/refusal字段和effect/result绑定、重复未知JSON、typed bool quote仍误终局 |
| A21-R1-EVENT | OPEN_CONFIRMED_RESIDUAL | 新完整集合已封存；升级前commit短RESERVE/SETTLE仍可补两次INSERT改历史/outbox不变，新增迁移封旧事件 |
| A21-R1-CANDIDATE | OPEN_CONFIRMED_RESIDUAL | snapshot→cost已修；params quote_id/version与其二者错配仍run/candidate/fallback通过，三方一致性 |
| A21-R2-SNAPSHOT | OPEN_CONFIRMED_RESIDUAL | 基本schema已修；非法ID/version和1500深度异常未统一隔离，存储/结果边界完善 |
| DOC-CKPT1-01 | OPEN_NONBLOCKING（部分修复） | 真实tracked4/README烟测已修；旧未跑/未开始/004计划/182和CLI-first输出仍现行，标历史并同步当下 |
| A21-R3-UNKNOWN | OPEN_CONFIRMED_BLOCKING | service._mark_unknown缓存UNKNOWN早return；旧claim过期新owner已SUCCEEDED后10/10旧worker仍报UNKNOWN（DB未覆盖）；no-op也当前锁后owner/version/state/expiry或真实终态 |
| A21-R3-TESTSYNC | OPEN_CONFIRMED_BLOCKING | 正式REG锁测试barrier在持task后二次wait不可能相遇、吞BrokenBarrierError；10操作仅RESERVE无outbox却PASS。纠同步＋拒未预期异常＋每轮完整终局进展 |

下一补正包 `runs/A2.1-core/correction-r2.md`，MiMo不得覆盖历史失败日志或自行关闭；所有closed项后续全回归保护，若出现新回归可重开。

## correction-r2交付待r4

同MiMo session停止写入，report=`runs/A2.1-core/implementation-r3.md`；自查证据 `artifacts/workflow/A2.1-core-impl-correction-r2-20261001c2/`，Python3.11 unit137/PG355、README两个变体烟测。LEGACY/OUTCOME/EVENT/CANDIDATE/SNAPSHOT残余、UNKNOWN/TESTSYNC及DOC现标FIXED_PENDING_REVIEW（不是CLOSED）；r3已关闭5项继续回归保护。

修复索引：results.py单次有界每工具result精确shape和字段关联；candidate三方params/cost/snapshot报价身份；catalog ID/version/depth统一解析异常与入口隔离；006新增不可变transaction seal sidecar限制当前创建event节点写、不改001—005旧行；UNKNOWN现场四条件；锁回归同步移至可达点且拒任意线程异常并逐轮完整终局计数；报告顶层当下/历史区分与迁移no-op说明。最终关闭仍待fresh reviewer独立原trigger/变体和完整矩阵。

## r4中断观察索引（不算完成审查）

NEW reviewer `ses_f09170d1cffeYHkFN5L76xDlU3` 因usage limit终止、无完整报告。snapshot仍d7ea969a34b63782d06506d7f6ff9f221c6fbdc0590b2d2d9561e55554364c9c。artifact=`artifacts/workflow/A2.1-core-review-r4-7bf291ac/`，保留formal/probes日志/XML/source/observations。主控读fresh-r4.log观察：旧反例基本修好，new70case有以下待新reviewer确认项（不能用历史log作为下一轮独立PASS）：

- SNAPSHOT/LEGACY残余：regex用match与`$`接受quote_id/version/supplier/sku尾随LF；旧supplier LF仍运行；深嵌套legacy params五入口漏持久flag（snapshot深度已修不等于params已修）。
- OUTCOME残余：typed quote items=None/item=dict/items=list和effect尾LF execute/query失败，需查实际UNKNOWN语义而非generic crash，精确关联校验。
- CANDIDATE残余：最后一次候选miss后并发A1接受，A1返回EXISTING前未完整核候选材料（last-miss-race probe）。
- TESTSYNC残余：正式“反序有效性”测试不发生目标交错也可PASS（reverse-efficacy probe）；原正式锁进展及no-error测试已改善。
- 正向证据：UNKNOWN public run/reconcile 终态/新liveowner10轮均通过，005→006七表/registry合法非法、old short seal伪造并发和savepoint正常初写均通过。未正式关闭issue，待完整独立报告。

中断资源owner=`a21-review-r4-7bf291ac`，py id738641e87517、pg idfe956146f597，按resources.json/owner确认后仅清本workflowowned资源，不共享down。下一fresh reviewer从新独立资源复验，完整范围不缩水。

## r5正式确认及剩余边界

完整report `runs/A2.1-core/review-r5.md`，NEW session `ses_f08c896cbffeptdE23OBohV4bm` / openai/gpt-6.1-sol；同100项snapshot d7ea969a34b63782d06506d7f6ff9f221c6fbdc0590b2d2d9561e55554364c9c，NOT_ACCEPTED，21PASS/9FAIL/1BLOCKED。证据root `artifacts/workflow/A2.1-core-review-r5-4f8c2d19/`，完整index及原JUnit保留；r4owned遗留和r5资源均已cleanup。主控以r5闭环覆盖前方pending历史状态。

- **CLOSED_REVIEWED（r5）**：EVENT（006旧短集合、seal伪造/并发/savepoint封存有效）与UNKNOWN（public40round旧worker准确失租/终态不误报）。已闭LOCK/NOTIFY/CHAIN/LOG/BOUNDS回归保持关闭。
- **OPEN_CONFIRMED_RESIDUAL**：LEGACY（深legacy params五入口RecursionError无持久flag）；SNAPSHOT（regex.match+$尾LF/0 LF，旧supplierLF实际释放无flag）；OUTCOME（typed itemsNone/dict异常停止EXECUTING，不安全UNKNOWN；effect尾LF仍终局）；CANDIDATE（最后一次非锁miss→另A1提交坏同意图→实际A1EXISTING/proofs2/无flag，10轮）；TESTSYNC（反序有效性首锁前barrier不保证持锁环，generic异常/强制串行也PASS）。DOC仍OPEN_NONBLOCKING（当前与历史/清单/路径矛盾）。
- **A21-R5-P11-EVIDENCE / OPEN_VERIFICATION_GAP**：额外继承P11 resource[3]一次LedgerError没记录code/cause，诊断10轮未复现；不编造新代码缺陷，不默删原失败。OBL02当前BLOCKED，后续精确code/cause/同步/DB当前时间proof窗口证据及有效重复复验闭合。
- **非finding保留理由**：items同字段tuple改list应合法结构比较，2过严失败不作为issue；r5正例实证，不能强制tuple修到“过严探针通过”。

下一correction-r3必须解决原子EXISTING检查的A1最小兼容集成设计；主控先审包确认文件范围，不再追加无锁重查碰运气。无需求降低、无新阶段。若反复尝试无证据/进展才停具体BLOCKED；目前新增关闭两项有效进展。

## correction-r3交付待r6

NEW包审 `runs/A2.1-core/package-review-r2.md` PACKAGE_READY，session ses_f0892f2bfffezCvUsClN3kmSPQ，确认same-stage最小ledger/service兼容扩展；原accept默认行为不变。MiMo同session停写完整 `implementation-r4.md`，自查Python3.11 unit137/PG424、README双烟测通过，仅实施证据。

LEGACY/OUTCOME/CANDIDATE/SNAPSHOT/TESTSYNC残余与DOC标FIXED_PENDING_REVIEW；closed7项回归保护。atomic accept_checked校验器在actualexisting事务同conn只读材料，失败txn/proof rollback后独立flag；params深度异常统一隔离、ID fullmatch、typed shape总定义、真持锁环反序精确诊断与no-progress失败、DOC最新状态清单。worker证据 `artifacts/workflow/A2.1-core-impl-correction-r3-20261001c3/`。

A21-R5-P11-EVIDENCE仍 **OPEN_VERIFICATION_GAP**：本轮10轮精确diagnostic落盘，但不能追溯旧unknown LedgerError的code/cause，不声称被TTL解释。r6须评估当前要求的有效独立同步/异常code/时间窗口证据是否足够闭合，保旧fail及不确定性说明，不能无据忽略或机械复用历史BLOCKED。

## r6工具中断（保持待验收，不丢证据）

NEW reviewer session ses_f07fb4086ffeaWkDmUBM3mDghi在Task工具中断后没有返回完整report，artifact=`artifacts/workflow/A2.1-core-review-r6-ccf8e91a/`；代码101项snapshot17a3b2c7a61ccc82348de5fc6de6840d8f37861b98c6851a45983981d524f3f5仍一致。主控只核对日志：formal137/424、A1分跑68/78、history4+1、README双smoke；继承320case记录318pass/2fail，两个fail为已明确非finding的合法items list要求UNKNOWN过严断言，不因此假定整个stage接受或闭合其他issue。

旧owned py=d10144ad71c4、pg=318bd9c17d9e，owner=a2.1-core-review-r6-ccf8e91a，resources.json核完整ID后只清本workflow资源；**ab-caseb-r3-pg属于另一个工作，禁止清理或连接**。新fresh reviewer另建资源，旧日志不能代本轮mandatory实跑。

## r7正式闭环：剩一个版本匹配残余＋DOC

完整review-r7.md，NEW session ses_f07b43a4affenxt8HroNe3U3FB/openai/gpt-6.1-sol，高推理档位，snapshot17a3b2c7a61ccc82348de5fc6de6840d8f37861b98c6851a45983981d524f3f5，NOT_ACCEPTED（27PASS/4FAIL）。evidence root=`artifacts/workflow/A2.1-core-review-r7-a93e6b42/`，index/完整raw日志保存。

- **CLOSED_REVIEWED（r7）**：LEGACY（params深度五入口持久隔离）；OUTCOME（坏typedshape安全UNKNOWN、full结果关联、合法list）；CANDIDATE（actualexisting原子callback、lastmiss好坏10轮/同instance同时validator/retry/rollback/flagfail/realDB失联）；TESTSYNC（真实目标锁环10轮，串行/异常/无进展不能假PASS）；A21-R5-P11-EVIDENCE当前mandatory缺口（当前controlled确切codes/time同步的好坏/撤销/重放/过期各10轮证据充分）。旧一次unknownLedgerError根因仍不可追溯，作为历史风险保留，不声称TTL已解释。
- 之前LOCK/NOTIFY/CHAIN/LOG/BOUNDS/EVENT/UNKNOWN七项本轮全回归保持CLOSED。
- **A21-R2-SNAPSHOT OPEN_CONFIRMED_RESIDUAL**：params.py quote_version还是match前缀（37/232—238），01/00/1x/1@2/1/2/1空格2/1.0/1e2/超既定长度parser通过；构造对应可信集合/目录时3变体实际CREATED，预留70000/1/proof，无下游效果。修完整正整数wholematch，在候选lookup前格式拒绝零新增。
- DOC-CKPT1-01仍OPEN_NONBLOCKING且WF-DOCS未过：当前report门槛/主体/004未实现/359/漏5tracked-service/漏006/results/旧路径，须真实当前短索引替换旧段或整段标历史，不断局部替数字留下矛盾。

下一窄补正 `runs/A2.1-core/correction-r4.md`，只params版本全匹配与有效正式parser/接受拒绝回归、当下报告文档；原31要求不降低，新freeze/fresh验收后再最终门检查。

## correction-r4交付／用户暂停与恢复

MiMo已停写，完整implementation-r5.md（hash fd264c1b34cfb0bc5821ab4da7e6bbd2493ae1f869ea7665f5232fd2e619b199）与owned artifacts/workflow/A2.1-core-impl-correction-r4-20261002c4/留存。SNAPSHOT及DOC标FIXED_PENDING_REVIEW，尚未关闭；其余全部已闭代码/当前P11gap继续全回归。version params/catalog/results规则统一fullmatch正整数1—18位、非法可信集合/catalog仍格式拒零新增；A2-report整个66行当下事实短索引重建。自查Python3.11 unit137/PG522、56formatfiles、双READMEsmoke通过，只是worker证据。

用户曾要求额度停点（真实msg_0f887e93e001D7S0b27RlnzOD3），主控在补正后/新review前停止，没有接受阶段；随后真实msg_0f9cc37f8001PyAvQX6K0ucvFu“继续”已读回，仅恢复原已批准A2.1。当前snapshot102项15dc8782e1788e0bae6359a5c7538287db679078012b50f8901ab72dea4c5b09，下一fresh r8完整独立验收，保持所有原义务与历史风险。无commit/push/后段/业务资源启动越界。

## r8最终独立闭环（当前权威状态，历史记录不覆盖）

完整review-r8.md：NEW session `ses_f06312272ffeGlM7w2nBLXi2DM`，实际openai/gpt-6.1-sol/high，针对102项snapshot15dc8782e1788e0bae6359a5c7538287db679078012b50f8901ab72dea4c5b09，31必需项全PASS、无blocking。原始证据index `artifacts/workflow/A2.1-core-review-r8-2fd79c61/evidence-index.json` hash07fc53e3307663d4840ce2e202e857a635d96bef31a8fdaf28caf4f941c7b330。主控核对31项引用hash、原XML137unit/522PG/482probe/58new、资源cleanup原件及probe适配diff，不用worker成功声明关闭。

下列14项全部 **CLOSED_REVIEWED（绑定r8，非降级）**：

| Issue | 实际修正索引 | 本轮独立复验/关闭依据 |
| --- | --- | --- |
| A21-R1-LOCK | 统一task→grants→operation→lease，非锁定位 | 原反序交错10轮、精准终局计数/唯一效果/outbox；review §8/G/P |
| A21-R1-LEGACY | 全入口严格verify_accept_facts＋rollback后持久sidecar | 原8类/深params五入口/候选fallback保预算零下游、flag持久；G/P |
| A21-R1-OUTCOME | strict per-tool result+typed quote总定义/full关联 | 键/工具/意图/报价/effect/result/坏typed形状execute/queryUNKNOWN，合法list正例；G/P/N |
| A21-R1-NOTIFY | 可信目标存在/tenant/task/grant/holder | absent/跨身份负例0新增，合法通知10轮幂等；G/P |
| A21-R1-CHAIN | 完整DB父链逐层grantIDs/约束收窄 | 缺mid/leafonly/重排/错层/拼接拒，根/中/叶正例；G/P |
| A21-R1-LOG | 稳定安全码/摘要，不输出原异常 | malformedDSN/secret异常stdout/stderr/reason不泄marker；G/P |
| A21-R1-BOUNDS | 下游和网关read连接有限正SQL等待 | 真锁自动timeout（不cancel），UNKNOWN保预算，非法配置拒；G/P |
| A21-R1-EVENT | 005形状完整性＋006transaction seal | 旧短集合/append/seal伪造并发/savepoint防绕过、合法初写；G/P |
| A21-R1-CANDIDATE | A1兼容accept_checked同txn实际existing检查 | lastmiss好坏各10、两个活跃validators/rollback/retry/flag失败/真DB失联；G/P/N |
| A21-R2-SNAPSHOT | params/catalog/results版本fullmatch/schema/depth/types | 原前缀/0/leadingzero/control/Unicode/大小版本边界，可信非法集/catalog0新增，最大版本生命周期；G/P/N |
| A21-R3-UNKNOWN | no-op也当前owner/version/state/DBexpiry | public旧query失租/新终态/liveowner40例准确拒，不误报cachedstate；G/P |
| A21-R3-TESTSYNC | 真双方持锁环精确目标/不吞异常、逐轮进展 | 10轮DeadlockDetected/Lock观测，串行/异常/无进展不能假PASS；G/P |
| DOC-CKPT1-01 | 当前66行报告真实facts/files/counts/paths | Git5tracked、137/522/56files、全部新增清单、README双逐字smoke；I/SM |
| A21-R5-P11-EVIDENCE | 当前controlled确定性code/cause/DBclock/proof窗口 | 本轮50正负/撤销/重放/过期case同步实证齐；仅关闭当前mandatory缺口；P |

**仍保留的非阻断历史风险/边界**：r5旧一次无code LedgerError不可追溯原因（不声称TTL解释）；合法list曾有过严probe，r8仅修改自有probe为完整成功后置断言且保原失败，非删弱要求；旧升级probe硬编码002依旧记录fail，当前动态8升级组等价更强。B/真实HTTP/真签名/独立锚定/远程CI尚未本stage完成，不能把它们当PASS。后续新回归可重开已闭项，原触发/失败/修复证据与所有报告保留。

保留issue ID、requirement ID、严重性、真实位置、触发、影响、证据、修正包/实际变更、有效回归探针、新review session及独立复验结果。实施者完成只能标FIXED_PENDING_REVIEW；只有新review实证和主控核查后才能CLOSED_REVIEWED。非阻断意见保留理由和后续范围，不能悄悄消失。历史失败轮与证据不覆盖、不删除。


## A2.2 r3 自查补正（历史状态，现已由r1独立复核闭合）

- **A22-CTX-FIRST-BINDING / P2 / FIXED_PENDING_REVIEW**：`execution/query.py::_original`原先只校验原context形状及部分字段，16个同形错误值在真实PG探针中返回200，违反原件一致性失败关闭要求；当前ownership检查仍有效，未证明跨身份绕过。已由immutable operation的摘要绑定token/proof/request及完整PermissionSource重建全部VerifiedInvocation并比较canonical context；正式16拒例和历史原proof过期/新query proof合法正例已自查通过。必须由fresh reviewer独立触发、核失败query proof回滚/零业务效果及完整95/88矩阵后才关闭。证据/变更/实际命令见[implementation-r3](runs/A2.2-integration-20261004/implementation-r3.md)，不以worker成功声明关闭。
- **证据限制（保留）**：r3首次双conftest collection exit2原XML被后续exit1误覆盖，无法恢复；原exit2完整log/command仍在且registry无XML、cases为空，现存19项XML只绑定exit1，最终19通过有独立文件。3份失败JUnit中的自有运行密码精确脱敏，原/后SHA及case结构状态不变有记录；未发生已证明的公开HTTP密码泄露。catalog JSON直接文本脱敏损坏后从未改正式测试AST逐字重建，实际为跨转义quote URI前缀误匹配，完整DSN替换数0；损坏件及失败保留。后续reviewer独立实跑，不以这些历史失败XML冒充成功。

## A2.2 独立 r1（2026-10-05记录）

[完整review-r1](runs/A2.2-integration-20261004/review-r1.md)结论NOT_ACCEPTED。95项86 PASS/9 FAIL，两个P2导致；主控已核518原始证据哈希、115命令及JUnit与280项冻结。

| issue | 状态 | 触发与补正 |
| --- | --- | --- |
| A22-R1-RESULT-ERROR | FIXED_PENDING_REVIEW / P2 | 真实持久结果wrong operation/read形状/[]返回500，契约要求503；限终态可信投影上下文转换typed DOWNSTREAM_INCONSISTENT，保留未知错误500。复验完整状态零变化、修复同proof成功及重放409。 |
| A22-R1-SHORT-WINDOW | FIXED_PENDING_REVIEW / P2 | 真AS父根3秒且子固定ttl3跨秒即超父期限，source/wheel各PG同一失败；按真实父exp/当前时间安全收窄，正式10轮强制跨秒，保留原查询锁后窗口负控及完整真实签名。 |
| A22-CTX-FIRST-BINDING | CLOSED_REVIEWED_R1 | fresh source/wheel各16字段变体及原proof过期新query正控通过；不是整段接受。 |

按[correction-r1](runs/A2.2-integration-20261004/correction-r1.md)同范围补正，再新reviewer全95/88独立复验。原harness失败、隐私脱敏前后哈希和历史报告全部保留。

## A2.2 r4补正自查与主控停写核验

[完整implementation-r4](runs/A2.2-integration-20261004/implementation-r4.md)已原生COMPLETED，source/wheel各1022普通+1930 PG及独立增强335全通过；两项P2只标FIXED_PENDING_REVIEW。主控核558证据/110命令JUnit、764函数及7761case refs、284项候选/只读范围与实际owner容器/network余留0；HEAD、分支、语义index和staged diff未变。最终wheel增强独占重跑，原共享cache轮/历史适配失败/隐私封存失败保留。下一步fresh r2全95/88独立验收，不能以本自查关闭或合并。

## A2.3 core-r1 原生 STOP / NEEDS_REPLAN（历史停止与当前补正基础）

- **A23-CORE-R1-AGGREGATE-CAPACITY / P2 / OPEN_CONFIRMED**：真实AS root及两次exchange、public202、独立DS终局后的256唯一SKU宽16/17、qty35184372088831、unit1各原component合法，SDK非ledger聚合67058/68938被默认64KiB codec提前拒。历史SDK未修改；直接publisher再次确认异常链与所有ag/DS行SHA不变、三祖先预算正确保留、outboxPENDING/null。详见[完整停止报告](runs/A2.3-receipts-20261004/implementation-core-r1.md)。新精确SDK1+四测试文件包审后实施，保每component原限额/签名语义，精确outer1MiB；最新完整source/wheel、自查和fresh完整119/112验收后才可能关闭。
- core14实际范围/311源/262原始证据/29局部绑定/15JUnit runs已读回，own0；861只是收集数，旧partial PASS/FAIL、签名debug139、原wheel143、最新测试NOT_RUN全部保留，不据此释放消费者。r2两个元数据P3留给新包独立核补正，不由主控自行关闭。
- A2.2两项P2已由fresh r2 CLOSED_REVIEWED_R2，见[正式接受](runs/A2.2-integration-20261004/acceptance.md)；上述历史r1/r4段落不是当前待接受。PR7 head138c08a CI SUCCESS，仅正常审核条件未满足。

## A2.3 capacity-v1 新独立包审（历史范围放行）

[完整package-review-capacity-r1](runs/A2.3-receipts-20261004/package-review-capacity-r1.md)已原生FINAL STOP/独立PACKAGE_READY，主控完整119/112、41节点/88原子、674来源、318候选/266raw/21自有产物及Git起止全核无漂移。仅精确SDK1+既有四fixture/test文件补正被激活，不授旧core14完整写权；业务未修、完整A2 NOT_ACCEPTED。

- A23-PKG-R1-STALE-PLANNING、A23-PKG-R1-PROVENANCE-LABEL：CLOSED_REVIEWED_CAPACITY_R1，仅各原具体metadata静态义务，不是业务通过。
- A23-CORE-R1-AGGREGATE-CAPACITY：P2 OPEN_CONFIRMED，按已审包实施，最终fresh完整119/112 sourcewheel验收前不关闭。
- A23-CAPACITY-PKG-R1-BOUND-LABEL：P3 OPEN_NONBLOCKING_NEW_BOUND_RECOMPUTATION_REQUIRED，历史notification局部3359低2bytes；当前保守3361、全局54873仍覆盖四tool，历史65235移除旧聚合限额后失效。worker新逐tool/refusal/真实status/kid/UUID/claims/源码SHA重算，保exact codec边界和真实超限503/proof rollback，后续NEW完整验收核闭。

## A2.3 capacity-r1实际STOP与quality-v1（当前）

容量缺陷：FIXED_PENDING_FULL_REVIEW，源/wheel宽12/16/17及短256各4PASS，unit/原SDK各61PASS；完整core NOT_RUN，原失败保留。新逐工具上界已实际重算54872/3361/2947/2949、PENDING52155及outer589964，最终fresh完整验收再核闭。

**A23-CORE-QUALITY-FORMAT / P2 / OPEN_CONFIRMED**：完整ruff42→owned补正后3FAIL；receipt_publication.py E501、verified.py I001、factory.py I001在旧5只读范围。format通过不豁免ruff。quality-v1精确原5+format3已由NEW reviewer核包PACKAGE_READY，原119/112不减；下一步实施；纯格式和完整最终core源轮一次，自有0与新消费者包审/最终独立验收仍必需。

## quality-r1实际STOP（当前）

A23-CORE-QUALITY-FORMAT已实施且全ruff/format通过，标FIXED_PENDING_FULL_REVIEW；容量P2同样待最终fresh验收。A2.3 quality-r1已原生STOP/READY_FOR_CONSUMERS：source/wheel各核心882、普通1078、受影响旧回归813全部通过，主控核327候选/精确6-of-8范围、489历史原件、1565证据和18433环境成员、29局部断言绑定/真实来源与资源0。首轮失败和partial396中断保留。这是核心自查，不是完整A2接受；下一步一个NEW独立reviewer完整审v3和CLI4/HTTPS3两个子包，分别放行后并行接入；allSTOP后sole29整合自查和NEW独立完整119项/112运行义务验收。 最新真人要求“验收完A2规划完A3就停吧，太慢了实在是”：本次完成完整A2验收和A3可接续分段计划后停止，不实施A3；此前连续实施全部A3的授权由本次限制覆盖。
