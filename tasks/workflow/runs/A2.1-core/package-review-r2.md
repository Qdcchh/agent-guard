# 独立审查：PACKAGE_REVIEW／A2.1-core／NEW package-r2

## 1. 结论与范围
- **结论：PACKAGE_READY；未发现阻断补正包的设计缺陷。** 日期：2026-10-01，Asia/Shanghai；结束核验：20:30:35+08:00。
- 仅审 `correction-r3.md` 的范围、架构、兼容性、所有权与验证计划；**不接受现有代码，不关闭实施缺陷**。state 仍为 `CHANGES_REQUESTED`，完整 A2／项目仍为 PARTIAL。
- 已通过 OpenCode SQLite **只读查询**核实原授权：role=user，`msg_0f54148e0001ZW7yCMdK0TE97F`／`ses_f0ac0e676ffecn71p6Ww7zaqQq`，原文批准 A2.1 主体、全部同阶段补正与再复核。
- 原 stage:9、task-v1:24 允许经主控确认的必要 A1 兼容修正；本包:7–15 已明确确认 `ledger/service.py` 最小扩展，**不是未经授权的新阶段**。
- 不允许进入 A2.2/A2.3/A3；完整 P15 真实授权、P16/P17 真实验证、P18 真实签名、P21 HTTP 闭环仍为后段／B依赖 BLOCKED，不计完成。

## 2. 独立会话与冻结绑定
- 根目录 **R**：`/Users/qdcc/code/密码技术竞赛/agent-guard`；下文相对位置均以 R 为根；报告由主控保存为 `tasks/workflow/runs/A2.1-core/package-review-r2.md`。
- 实际 session：`ses_f0892f2bfffezCvUsClN3kmSPQ`，SQLite 中本轮 user 消息同时匹配 PACKAGE_REVIEW 与补正包 hash；模型 `openai/gpt-6.1-sol`。Task ID 未暴露；session variant 为 default，实际推理档位不可独立确认，不虚报 xhigh。
- 分支／HEAD：`feat/a2-execution-gateway`／`b120c7cf5ec0eafb18305d1207c36dd11655b324`；主控声明无 writer，state 记录实施者已停写；未声称查询过调度器。
- 开始／结束独立生成的 **100项 snapshot**：`d7ea969a34b63782d06506d7f6ff9f221c6fbdc0590b2d2d9561e55554364c9c`，与提供值及 manifest 一致。
- 新契约摘要：`24b2bf395b9d4ee8b2e754bf85e443dd25f5315e6b4098772c98984bb671c045`；逐文件 gate 散列通过，包含 correction-r3；**不沿用** r5 的旧摘要 `27f22d55…`。
- correction-r3 SHA256：`cedb802105131f77ca7a0e67c6b55c689ae8df2ffde7971871d97dd9fdc6076b`；完整 review-r5：`ba09960b1c248d811452a4e35c33b386735be753de2e8050122971ea4398110c`。
- 控制输入两次散列一致：state=`7c05e3fbd497ea938688c86d4aef87b14dab21ce828287f17f089728e0171d50`；issues=`88e63e9df062e904ebe40656c7306e73153faabe9d5d478135faab47b2bb8312`。
- Git：4 tracked 修改、60普通 untracked；staged 空、无删除／重命名。binary unstaged diff=`a91d85c31814e2a43ae91a8a91c47adc4da10c809af8c1413437f0cd43ca9e1c`；空 staged=`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- 全量 porcelain 状态摘要=`0eed364d7d1388693354d429080278c2f0d53853594bb9f5e18fcb4776dda71f`，结束一致；排除沿既有控制／生成规则，正式包另入契约，state/issues另核；没有新增排除。

## 3. 实际静态检查与架构要求
- 全文读 AGENTS/AGENT、README、三份 docs、原 A1/A2 task及历次验收、两轮 ckpt1、workflow契约/stage/state-guide/模板、task-v1、correction-r1—r3、package-r1、完整 review-r2/r3/r5、issues；worker报告只作声明索引。
- 直接读 ledger 全模块、两份可信契约、001—006、execution service/store、params/catalog/results/policy、相关接受/回滚/报价/锁测试、隔离fixtures、CI/依赖/Compose，以及 r5 last-miss、r4-boundaries、P11 diagnostic 探针源码。
- **原子边界正确**：当前 A2 `service.py:247–256` 最后非锁 miss 不能约束 A1 `ledger/service.py:198–224` 的实际 EXISTING；包要求把完整校验移入后者事务，消除了“继续增加 lookup”的错误修复路线。
- 实施须让 **candidate hit、解析失败 fallback、解析成功后的接受路径**均使用 checked 入口；在动态验权/proof/完整意图比较仍有效的前提下，提交前用**同 conn**读取实际 operation/path/events并校验；不要把会另开连接的 `_ensure_accept_material` 原样塞入 callback。
- validator 必须可信、per-call、无实例可变存储，不重取当前报价、不联系下游、不提交事务、不改变锁序；异常须传播并回滚新 proof，不能忽略返回值或宽泛吞 DB 故障。A2 **退出拒绝事务、释放锁后**才独立持久 flag，避免 FK 自等待。
- 保持原 `accept(verified,cost)` 默认语义及调用方兼容；复验加入同实例并发不同 validator、防串扰、异常回滚、重试后重新校验、独立 flag 失败关闭。现有持久结构足够支持该修正；**001—006全部禁改，本轮不新增迁移**。

## 4. 完整31项需求矩阵
全部属当前必需；原始子断言完整继承 task-v1:34–64、原 A2§7、ckpt1-r2:15–20及正式stage，未删减/重命名。下表均为**计划完整／行为未执行**，不是 PASS；P=原A2，O=ckpt1义务，W=stage/工作流。C/REC/QT/CON/VAL/REG/REG3为相应 `tests/integration/test_execution_*`，DS=`test_downstream`，MIG=`test_a2_migrations`；S=execution service/store，L=ledger。
| ID／来源 | 实现／测试计划 | 必须观察及r3新增影响 |
|---|---|---|
| A2-P01／P | S终局；C::test_p01* | 唯一70000/1订单；三层计数、事件/outbox一致 |
| A2-P02／P | results/下游；C/REG3 refusal | 同键持久拒绝才释放；阻止迟到成功，错shape不释放 |
| A2-P03／P | 零额工具；C::test_p03* | 0金额仍计1次，读取固定、通知最多一次 |
| A2-P04／P | worker；REC::test_p04* | 提交前零效果；真实终止/新PID持久恢复 |
| A2-P05／P | run/reconcile；C::test_p05* | 下游已提交响应丢失，UNKNOWN保预算、恢复同单 |
| A2-P06／P | worker/终局；REC | 下游成功后崩溃，不重复效果、结算或outbox |
| A2-P07／P | 终局事务；C/独立回滚探针 | 节点/事件/outbox/status中途失败全回滚；checked失败proof亦回滚 |
| A2-P08／P | reconcile/连接；C/锁超时探针 | 查无结果不释放；迟到唯一成功，等待有界 |
| A2-P09／P | claim/finalize；REC/REG | fencing、失租、双恢复者；正序10轮终局及精确反序效力 |
| A2-P10／P | 内部恢复/L动态复核；REC | 撤销/过期/停key后恢复原意图；外部checked重试仍拒绝 |
| A2-P11／P | A2→L checked；QT/last-miss探针 | 最后miss后好/坏材料各10轮；原成本、proof回滚、flag持久 |
| A2-P12／P | decide/results；C/REG3/边界探针 | execute/query坏typed shape或ID→UNKNOWN保预算，无outbox；合法list正例 |
| A2-P13／P | L/S混合锁；CON | 所有祖先金额/次数有界非负；规定组10轮，无反向锁 |
| A2-P14／P | 独立下游；DS | 同键订单/通知唯一；冲突及无/错服务认证零效果/泄漏 |
| A2-P15-CORE／P+stage | params/policy；unit/VAL | 四工具严格schema/权限/归属负例零新增状态；补深度/标识边界 |
| A2-P19／P | 迁移/material；MIG/legacy探针 | 非零七表/完整registry保全；深params五入口自动隔离、不执行 |
| A2-P20／P | 001—006 guards；MIG/seal探针 | 直接SQL改删/重建/双终局拒绝；合法UPDATE及初写保持 |
| A2-CKPT1-OBL01／O | static→candidate→checked；QT | 不依赖当前报价；实际EXISTING原子材料校验且不绕动态验权 |
| A2-CKPT1-OBL02／O | miss/fallback；QT/P11 diagnostic | 资源及报价消失确定性10+轮；精确错误码/时序/DBtime/TTL |
| A2-CKPT1-OBL03／O | material/sidecar/永久事实；REG/MIG | 不完整实际existing拒绝、不留新proof；锁释放后flag、预算保留 |
| A2-CKPT1-OBL04／O | lease四条件；REC/stale探针 | owner/version/state/锁后expiry；UNKNOWN no-op也现场核验 |
| A2-CKPT1-OBL05／O | sidecar/phase-seq/seals；MIG | 七旧表不改行；事件完整封存及合法更新/owned清理兼容 |
| A2-CKPT1-OBL06／O | snapshot/results/receipts；C/REG3 | fullmatch/总定义比较；完整原报价、稳定UTC iat、不可变PENDING |
| WF-A1-REGRESSION／W+A1 | 全A1 unit/PG及历史探针 | U1/P1—14/F1—5、根重建/升级；默认accept成本/证据/拒绝全保持 |
| WF-INDEPENDENT-PROBES／W | fresh reviewer自选探针 | 原trigger及绕过、checked并发/回滚/flag，无固定测试数量替代 |
| WF-QUALITY-CHECKS／W | ruff/diff/全正式suite/CI | 无缺库skip；精确锁效力，故意串行/未取得目标锁必须失败 |
| WF-PY311-ENV／W | 新3.11安装/constraints/PG16 | 真实环境及安装验证；缺环境BLOCKED，旧CI不能替代 |
| WF-RESOURCE-ISOLATION／W | 独占project/DB/schema | worker/reviewer分离，TEST DSN，完整归属及仅owned清理 |
| WF-IMMUTABLE-BASELINE／W | hash/L调用方及默认回归 | 当前迁移基线静态一致；001—006不改、仅service最小兼容、无B偷渡 |
| WF-DOCS-REPORT／W | README/A2-report/types/report-r4 | 当下/历史、006/results清单、JUnit路径/diagnostic准确，不虚报关闭 |
| WF-SNAPSHOT-COVERAGE／W | manifest/contracts/Git | 本包绑定一致；实施后重新冻结全tracked/untracked及fresh验收 |

## 5. 专项与历史回归承接
C1独占资源、C2原子候选/P11、C3非零升级、C4永久事件/路径、C5四条件租约、C6完整快照/稳定材料均保留；P04真进程恢复、所有规定并发组10轮、逐祖先账本/操作/事件/outbox/真实效果及A1历史探针等价说明未被定向修复替代。合法list结构不得因旧过严探针改为强制tuple。

## 6. 本轮独立核验命令
所有仓库命令 cwd=R；证据为本轮工具输出随报告保存，未创建日志/XML文件。
| 实际命令 | exit／结果 |
|---|---|
| `git status/branch/rev-parse/diff/diff --cached/ls-files/log`；两种 `diff --check` | 各0；实际范围见§2，whitespace无错误 |
| `python3 -B tools/workflow_gate.py snapshot --root .`，开始/结束 | 各0；100项、指纹一致；末次输出001—006逐文件hash |
| `python3 -B tools/workflow_gate.py verify --root . --state tasks/workflow/state.json`，两次 | 各0；errors=[]，结构性can_start=true，can_accept=false；不替代包审/真人授权 |
| `shasum -a 256` 控制输入/包/r5及Git输出；`sqlite3 -readonly …`授权/session查询 | 各0；hash稳定、真实user授权和本轮模型/session匹配 |

## 7. 历史证据与未执行项
仅核对既有日志：r5 `inherited.log:224–234`记录215通过/1失败，`p11-diagnostic.log`记录10通过；旧失败没有code，后者不能追溯解释。r5完整报告及探针源码/相关XML用于检查修正目标，**不是本轮独立重跑**。
本轮行为测试/探针创建数 **0**：ruff、pytest/A1回归、Python3.11安装、PG迁移/回滚、并发、SIGKILL/重启、README烟测均NOT_RUN（包审边界，非实施失败）；真实断网/TLS/密码/HTTP/远程CI亦未运行，未填任何行为PASS。

## 8. 开放问题与补正要求
**无新增包阻断；下列实施问题全部承接，均未由本轮关闭。** E=`artifacts/workflow/A2.1-core-review-r5-4f8c2d19/`；来源为r5§8、实际静态位置及E探针/历史日志。
| Issue／严重度／需求 | 位置、trigger→影响；包内具体纠正／未来复验 |
|---|---|
| A21-R1-CANDIDATE／高／P11,O01/O03 | A2 service:247–256→L service:198–224；最后miss后坏材料仍EXISTING/提交proof；E `test_r5_confirm:14–34`。同事务actualexisting校验，坏/好各10轮，拒绝proof回滚、flag持久 |
| A21-R1-LEGACY／高／P19,O03 | params:119–138、service:883–890；1500层抛递归异常漏flag；E `test_r4_boundaries:32–49`。有界解析/精确异常映射，五入口保预算零调用，不吞DB故障 |
| A21-R2-SNAPSHOT／中／P19,O06 | catalog:137–154；尾LF及`0\n`过模式→旧事实执行/释放；E boundaries:21–60。完整字符串/正版本检查，raw/typed/result控制字符负例及合法roundtrip |
| A21-R1-OUTCOME／高／P12,O06 | service:816–845、results:148–154；None/dict崩溃停EXECUTING、effect尾LF误终局；E boundaries:62–83。先type/shape后访问，总定义安全UNKNOWN/fencing/nooutbox；合法list保持 |
| A21-R3-TESTSYNC／中／P09,WF-QUALITY | REG:359–426；首锁前barrier及任意异常可非目标通过；E boundaries:196–214。实际持锁环/event/DB waitgraph，精确deadlock/lock-timeout；串行/未持目标锁必须失败 |
| DOC-CKPT1-01／低／WF-DOCS | A2-report:5,22,35,110,126–132及types:35–38；当前/历史、实现/证据路径矛盾。按包同步最新状态/实际清单/JUnit，保留历史报告和双README烟测 |
| A21-R5-P11-EVIDENCE／验证缺口，非新代码缺陷／O02 | E inherited.log:225–230未知LedgerError；诊断未复现。保原fail，记录code/安全detail/cause、同步、DBtime/expiry；无据不得解释为TTL，未闭合部分明确恢复条件 |
既有 CLOSED_REVIEWED 的 LOCK/NOTIFY/CHAIN/LOG/BOUNDS/EVENT/UNKNOWN 保留 **r3/r5历史关闭依据**，全部要求后续回归；包审没有重新证明或关闭它们。

## 9. 资源与结束核验
未写文件、创建目录/env/业务DB/schema/容器、连接业务PG、消费部署DSN、委派或操作Git写入；仅只读查询OpenCode元数据。自有资源与cleanup均无；未动既有资源，不夸称已核其业务数据摘要。代码/契约/Git/控制输入结束核验一致，无观察到漂移。

## 10. 交主控动作
保存本完整报告并绑定真实session及新契约摘要；核授权门后仅派同阶段r3补正，交付implementation-r4并停写，再冻结新候选，由NEW **IMPLEMENTATION_ACCEPTANCE**独立实跑完整31项及历史/新增反例。**PACKAGE_READY只确认补正设计可实施，不是代码ACCEPTED，不授权后段或Git发布。**
