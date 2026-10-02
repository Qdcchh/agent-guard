# 独立审查：IMPLEMENTATION_ACCEPTANCE／A2.1-core／NEW r5

## 1. 结论与范围
- 日期：2026-10-01，Asia/Shanghai；资源清理及结束绑定核验完成于 **19:59:48+08:00**，交付前再次核验无漂移。
- **正式结论：NOT_ACCEPTED。** 31项矩阵为 **21 PASS、9 FAIL、1 BLOCKED**；28项运行类义务均实际执行，未以历史结果替代。
- 正式 unit **137**、PG integration **355** 全绿，但不能抵消独立反例确认的残余缺陷。
- 阻断 issue：**A21-R1-LEGACY、A21-R1-OUTCOME、A21-R1-CANDIDATE、A21-R2-SNAPSHOT、A21-R3-TESTSYNC**；另保留 P11 复跑不确定性。
- 仅评价冻结的 **A2.1-core／检查点二**；完整A2及项目仍 **PARTIAL**。未修改被审源码、正式测试、标准、状态、台账或报告。
- **不允许进入A2.2/A2.3/A3，不授权提交、推送、PR、合并或发布。**

## 2. 独立会话、授权与冻结绑定
| 项目 | 本轮独立核对结果 |
|---|---|
| Reviewer | fresh r5；模型 **openai/gpt-6.1-sol**；API未暴露当前session/Task ID及实际推理档位，须主控关联真实调用，未借用历史ID |
| 根目录 R | `/Users/qdcc/code/密码技术竞赛/agent-guard`；宿主仓库命令均以R为cwd |
| 真人授权 | 与任务包/state一致：`ses_f0ac0e676ffecn71p6Ww7zaqQq`／`msg_0f54148e0001ZW7yCMdK0TE97F`；仅core及同阶段补正；本轮未自行授予权限 |
| 分支／HEAD | `feat/a2-execution-gateway`／`b120c7cf5ec0eafb18305d1207c36dd11655b324` |
| 100项snapshot，开始／结束 | **`d7ea969a34b63782d06506d7f6ff9f221c6fbdc0590b2d2d9561e55554364c9c`**；重新生成清单、逐文件散列，与state及执行副本一致 |
| 契约摘要，开始／结束 | **`27f22d55e88bb824a87b6e3c4124e69b030d4a59e6a5238572d130d0bae0ab7f`**；逐文件重算及排序JSON摘要一致 |
| worker报告／issues | SHA256分别为 **`70027c61f50b1c7876cb004e8a5e577ac9a358915610ffc603b34e725c553117`**／**`43e4510ba40f04f3e1e68a2142fa6bf030f5eff9b6f2fb11b7f6c690aa22e9de`**，开始/结束不变 |
| 完整Git范围 | **4 tracked修改、57 untracked**；staged为空，无删除/重命名；完整diff与清单保存在E，未操作Git写入 |
| Writer／排除 | 父任务确认停写，state记录STOPPED_READY_FOR_REVIEW；未发现漂移，不夸称已查询调度器。仅沿冻结规则排除artifacts/生成缓存/控制运行记录，正式包另核契约hash |

证据根 **E**：[artifacts/workflow/A2.1-core-review-r5-4f8c2d19/](/Users/qdcc/code/密码技术竞赛/agent-guard/artifacts/workflow/A2.1-core-review-r5-4f8c2d19/)；完整 [evidence-index.json](/Users/qdcc/code/密码技术竞赛/agent-guard/artifacts/workflow/A2.1-core-review-r5-4f8c2d19/evidence-index.json) 已读回、解析并核验引用hash。
**Index SHA256：`99fd737d0061e4a50c1be9595822fc1955e235706bc6f926d7b4d6d2f9d97718`**；含31项status/reason/path/SHA256/kind/exit、issue闭环、102个证据条目、56个源/契约条目及原始命令/JUnit。

## 3. 实际检查的实现与调用链
已读正式task-v1、两份correction、完整review-r2/r3及issues；workflow合同/状态/阶段/模板，原A2、两轮ckpt1、A1任务与历次验收、AGENT、README、三份原设计/安全/验收文档；检查完整tracked diff、全部新增业务源码、001—006及受影响测试/fixtures、依赖、CI和Compose。
追踪 `accept_invocation→params/policy/catalog→A1 accept`、`run/reconcile→材料验证→claim→独立下游→decide/finalize`；核对动态授权、锁序、DB时效、事务回滚、证据/事件/outbox不可变性及资源生命周期。
**静态查证不替代行为实跑；worker报告仅是声明索引。** 本轮未把可信初始化对象当密码验证，也未把任意同进程构造对象的可能性泛化为公网漏洞。
下文 **U/G/P/N/D/H/SM/S/I/RES** 对应E内 unit/integration/probes/fresh-r5/p11-diagnostic/history/README/冻结/静态/资源证据；C、REC、QT、CON、VAL、DS、MIG、REG、REG3分别指相应 `tests/integration/test_execution_*`、`test_downstream`、`test_a2_migrations`、两份regressions文件。

## 4. 完整需求与验收矩阵
以下31项均属当前必需；P来源为原A2§7，OBL来源为ckpt1-r2§13—20，WF来源为正式stage/合同。G/U/P/N/D/H/SM均为**本轮独立实跑**，I为**本轮静态查证**；具体函数及证据完整hash/真实exit见索引。
| ID | 实现／测试、探针 | 必须观察及本轮结果 | 证据 | 状态／缺口 |
|---|---|---|---|---|
| A2-P01 | finalize；C::test_p01* | 唯一70000分订单；三层预留0、结算70000/1，事件/outbox一致 | G/SM | PASS |
| A2-P02 | decide/downstream；C::test_p02*、REG3 refusal | 同键持久拒绝释放、不结算、阻止迟到成功；错键/错工具拒绝保持UNKNOWN | G/P | PASS |
| A2-P03 | 零成本工具；C::test_p03*、通知并发 | 0金额仍计1次；结算/释放正确，读取固定、通知最多一次 | G/P | PASS |
| A2-P04 | worker；REC::test_p04*、entry_windows/kill | 未提交不可见、零效果；真SIGKILL后新PID恢复持久状态 | G/P/O | PASS |
| A2-P05 | run/recovery；C::test_p05* | 真实下游提交后响应丢失替身→UNKNOWN保70000/1；恢复同单一次结算 | G | PASS |
| A2-P06 | worker终局窗口；REC::test_p04_p06* | kill时1单/0outbox；重启仍1单、1终局、1outbox | G/P/O | PASS |
| A2-P07 | 终局事务；C::test_p07*、partial_terminal | 实际部分节点/事件/outbox写后异常全回滚，保原预留，随后恢复 | G/P | PASS |
| A2-P08 | reconcile；C::test_p08*、deadline | 查无结果不释放；迟到成功一次；实际SQL锁自动超时 | G/P | PASS |
| A2-P09 | claim/finalize；REC、锁/UNKNOWN探针 | 独立10轮fencing及恢复正确；正式反序测试可非目标通过 | G/P | **FAIL：TESTSYNC** |
| A2-P10 | 内部恢复/A1动态复核；REC::test_p10* | 撤销/过期/key停用后内部原意图恢复；外部重试拒绝 | G | PASS；真查询后段 |
| A2-P11 | candidate；QT、r5 last-miss | 正常原快照/三方身份通过；最后miss竞态10/10返回不可用EXISTING | G/P/N | **FAIL：CANDIDATE** |
| A2-P12 | decide/results；C、REG3、typed边界 | 基本错配已修；None/dict抛错，effect尾LF仍SETTLE/outbox | G/P | **FAIL：OUTCOME** |
| A2-P13 | 全祖先预算/混合锁；CON、独立锁探针 | 根/中间/次数/接受结算恢复各10轮有界非负；固定锁交错完整终局 | G/P | PASS |
| A2-P14 | 独立下游；DS::test_p14*、通知10轮 | 同键唯一效果、冲突不覆盖；执行/查询无错服务凭据拒绝 | G/P | PASS |
| A2-P15-CORE | params/policy；VAL、unit、chain/notify | 四工具、严格参数/集合/scope/归属/完整DB链负例零新增状态 | U/G/P | PASS，仅可信fixture层 |
| A2-P19 | migrations/material；MIG、upgrade/deep/LF | 七表/完整登记升级保全；深参数漏flag、非法LF旧快照可执行/释放 | G/P/N | **FAIL：LEGACY/SNAPSHOT** |
| A2-P20 | 004—006 guards；MIG、seal/savepoint | 改意图/证据、删路径/操作、事件改删/追加、双终局拒绝；合法更新有效 | G/P | PASS |
| A2-CKPT1-OBL01 | static→candidate→A1；QT、last-miss | 不依赖当前报价且动态验权完整；原子EXISTING材料检查仍缺口 | G/N | **FAIL：CANDIDATE** |
| A2-CKPT1-OBL02 | miss解析失败重查；QT/P11 repetitions | 首批60case通过；额外分跑resource[3]未知LedgerError，诊断10轮未复现 | G/P/D | **BLOCKED：验证不确定性** |
| A2-CKPT1-OBL03 | 接受事实/sidecar/永久防删 | 防删成立；深参数及最后miss候选未自动持久隔离 | G/P/N | **FAIL：LEGACY/CANDIDATE** |
| A2-CKPT1-OBL04 | lease四条件；REC、fresh/stale probes | owner/version/state/锁后DBexpiry；无接管过期拒绝，UNKNOWN现场复核 | G/P | PASS |
| A2-CKPT1-OBL05 | sidecars/phase-seq/seals | 七旧表保全；旧短集合封存，合法计数/撤销/状态/owned清理兼容 | G/P | PASS |
| A2-CKPT1-OBL06 | snapshot/results/receipts | 稳定ID/time/UTC iat及不可变PENDING通过；LF/typed异常语义不足 | G/P/N | **FAIL：SNAPSHOT/OUTCOME** |
| WF-A1-REGRESSION | A1全部＋原探针＋增强升级 | U1/P1—14/F1—5保持；68 unit/78 PG及原4＋1通过 | A1/H/P | PASS |
| WF-INDEPENDENT-PROBES | 继承重跑＋本轮自写r5探针 | 源码、观察、失败均保存；自选last-miss正负、版本LF、语义及诊断 | P/N/D | PASS，非业务放行 |
| WF-QUALITY-CHECKS | ruff/diff/full suites/CI/efficacy | 质量及正式套件全绿无skip；正式反序有效性仍不成立 | U/G/P/I | **FAIL：TESTSYNC** |
| WF-PY311-ENV | 新3.11安装/constraints/PG | CPython3.11.16、约束安装/pip check、真实PG16.15 | ENV/U/G | PASS |
| WF-RESOURCE-ISOLATION | owner/完整ID/独立DB/schema | 新隔离资源、普通DSN未继承、仅owned清理、无关inventory一致 | RES | PASS |
| WF-IMMUTABLE-BASELINE | HEAD及历史候选逐字节比较 | 001—003/A1/依赖/CI不变；004/005旧hash保持，无B偷渡 | I/A1 | PASS |
| WF-DOCS-REPORT | README/A2-report/contracts/report | README双变体成功；现行计划/阶段/清单/证据入口仍矛盾 | I/SM | **FAIL：DOC** |
| WF-SNAPSHOT-COVERAGE | 完整manifest/contracts/Git/copy | 100项及另列契约/控制输入开始结束一致，无候选漂移 | S | PASS |

**后续边界：**完整P15真实授权、P16 token/proof签验、P17 result-read、P18真实SM2签名、P21 HTTPS闭环仍 **后续阶段／B依赖BLOCKED**，不计PASS；P18当前outbox材料与恢复义务已实跑。

## 5. 必查专项与历史回归
| 专项 | 本轮结果 |
|---|---|
| C1 | Compose只读渲染project为agent-guard／agent-guard-a2；reviewer另用独占owner网络/容器，不复用二者 |
| C2/P11 | 报价/资源消失及拒绝变体已跑；最后miss新绕过确认，额外复跑不确定性保留 |
| C3/P19 | 001/003/004/005×合法/非法共8组合，真实非零预留/撤销、七表全行和完整registry比较；重复no-op |
| C4/P20 | 新/旧完整及旧短事件封存；直接SQL、seal并发伪造及savepoint回滚/合法初写通过 |
| C5 | 失owner/version/expiry/终態均拒绝；public run/reconcile对终態/新liveowner各10轮，共40轮准确拒绝 |
| C6 | 完整原报价、同总额单价分配、稳定待签材料均验证；LF和typed异常残余不被正例抵消 |

P04独立探针观察PID **395→396**，旧exit **−9**、新exit **0**，效果/三层计数/事件/outbox完整；随后继承分跑再次真实kill/restart。
A1 P3/P5/P6、A2 P09/P13/P14及通知、P11、旧新终局、固定锁交错规定组均执行10轮；使用独立连接与Barrier/Event，不以sleep制造竞态。

## 6. 本轮独立实跑命令与计数
环境：Python **3.11.16**，PG **16.15**，psycopg/binary **3.2.13**，pytest **8.3.5**，ruff **0.11.13**；正式套件cwd为哈希相同的自有 `/evidence/candidate`，原仓库只读。
| 实际命令／目标 | 真实exit | pass/fail/error/skip或结果 | E内日志/XML |
|---|---:|---|---|
| `pip install -e /evidence/candidate[dev] -c …/constraints.txt`；`pip check/freeze` | 各0 | 新环境安装、约束及依赖检查通过，无新增运行依赖 | install、pip-check、pip-freeze |
| `ruff check --no-cache /repo`；`ruff format --check --no-cache /repo` | 0/0 | check通过；**54 files**格式通过 | quality-check/format.log |
| `git diff --check`，开始/结束 | 0/0 | 无whitespace错误 | diff-check*.log |
| `pytest tests/unit tests/test_scaffold.py tests/test_docs.py` | 0 | **137/0/0/0** | unit.log/xml |
| `pytest tests/integration` | 0 | **355/0/0/0**，含所有新增A2目录及A1 | integration.log/xml |
| A1 unit/骨架/docs；八个A1 PG文件独立分跑 | 0/0 | **68/0/0/0；78/0/0/0** | a1-unit、a1-pg |
| `python -m agent_guard.ledger.migrate` 两次 | 0/0 | 首次001—006，第二次no-op；完整registry checksum结束核验 | migrate-first/repeat、database-end |
| `pytest /evidence/probes`，继承＋r4源码本轮实跑 | 1 | **265/21/0/0**；其中两条list-only断言归非finding | probes.log/xml |
| 自写 `test_r5_confirm.py` | 1 | **12/12/0/0**；last-miss负例10失败/正例10通过，版本LF2失败/list语义2通过 | fresh-r5.log/xml |
| 216项继承探针额外分跑 | 1 | **215/1/0/0**；P11 resource[3]未知LedgerError，未抹去 | inherited.log/xml |
| 自写P11保原断言、记录coded异常诊断10轮 | 0 | **10/0/0/0**；未复现，不能解释先前失败 | p11-diagnostic.log/xml |
| 原A1四探针／根同ID重建／旧升级探针 | 0/0/1 | **4/0/0/0；1/0/0/0；0/1/0/0**，旧升级期待过时 | history-*日志/XML |
| README精确提取原文程序，两种新空库初始化 | 0 | 两种SMOKE_OK；三层70000/1、1单、2事件/6节点、1 PENDING NULL outbox | readme-smoke、snippet/driver、observations |
| 资源/DB核验、精确cleanup、结束与最终冻结核验 | 各0 | owned剩余0、test schema0、3无关容器一致、指纹一致 | RES/S；完整命令见index |

重复分跑不累计为不同case总量；原始失败日志保留。借用216项源码仅适配006迁移后缀期待，实际diff保存在 `inherited-source-adaptation.diff`，未弱化安全断言。
索引生成首次发生reviewer自有路径分派错误exit1，已纠正并留 `index-build-first-error.json`；未影响业务运行、未改被审文件。

## 7. 历史核对与未执行边界
r2/r3完整报告及r4源码/归属记录用于定位触发；**旧日志及worker的137/355、smoke声明不支持本轮PASS**。继承探针和README均在r5新资源重新执行。
原升级探针第46行仍期待仅`["002"]`，实际为002—006，故失败；源码未改，当前8组合对七表/完整登记的动态升级断言等价且更强。
真实执行PG回滚、自动锁超时、SIGKILL/重启；响应丢失/无结果/错outcome是port替身。**真实断网、TLS/wheel部署、SM2/SM3、HTTP及远程CI NOT_RUN**；后段排除项不另充作A2.1本地环境阻断。

## 8. 每项issue闭环、触发与补正
位置相对R；service/catalog/params/results/policy均为相应execution/tools源码。关闭仅绑定本轮冻结指纹；高/中开放项阻断。观察精确行号及源入口见index/observation-index。
| Issue／严重度／要求 | 位置、trigger及实际观察／影响 | 状态／具体补正或关闭依据 |
|---|---|---|
| A21-R1-LOCK／高／P09,P13 | service:445–492,651–677；原反序可触发交错10轮均完整终局，无死锁 | **CLOSED_REVIEWED**；统一task→grants→operation→lease保持，TESTSYNC另列 |
| A21-R1-NOTIFY／高／P15-CORE | policy:355–393,446–460；absent/跨tenant/task/grant/holder拒绝，合法目标及通知10轮通过 | **CLOSED_REVIEWED**；最小同grant/holder政策未扩大 |
| A21-R1-CHAIN／高／P15-CORE,OBL01 | policy:207–248；省mid、截短、重排、错层/拼接拒绝，根/中/叶正例通过 | **CLOSED_REVIEWED**；完整DB路径绑定，不声称B验签 |
| A21-R1-LOG／中／安全日志 | worker:133–151、service:103–111,497–512；malformed DSN/secret异常诊断无marker泄漏 | **CLOSED_REVIEWED**；结论限已测路径 |
| A21-R1-BOUNDS／中／P08 | downstream:150–162、service:164–192；真实表锁自动超时，不cancel，UNKNOWN保预算；0/bool配置拒绝 | **CLOSED_REVIEWED**；有界连接与SQL等待保持 |
| A21-R1-EVENT／高／P20,OBL05/06 | 006:85–140；旧短RESERVE/SETTLE补节点、seal并发伪造均拒绝，旧行/outbox不变；savepoint及合法初写成功 | **本轮CLOSED_REVIEWED**；保留001—006 checksum与直接SQL回归 |
| A21-R3-UNKNOWN／中／P09,OBL04 | service:722–752；旧query阻塞→过期→新owner终局/liveowner→旧None，40轮准确错误、无旧UNKNOWN覆盖 | **本轮CLOSED_REVIEWED**；no-op现场四条件修复成立 |
| A21-R1-LEGACY／高／P19,OBL03 | params:119–138、service:354–362,883–890；1500层旧params五入口RecursionError且无flag，calls预留1保留、零下游 | **OPEN残余**；有界参数深度/解析异常规范化，转LEGACY错误并全入口独立事务持久隔离；不能只修snapshot解析 |
| A21-R2-SNAPSHOT／中／P19,OBL06 | catalog:105–107,137–154；quote/version/supplier/SKU尾LF均接受，`0\n`亦通过正版本检查；旧supplierLF run实际FAILED/RELEASE、无flag | **OPEN残余**；fullmatch＋精确正版本/控制字符检查；非法旧事实保预算/零调用，合法roundtrip保持 |
| A21-R1-OUTCOME／高原issue／P12,OBL06 | service:555,637,816–845；items=None/dict四例TypeError/AttributeError，真实订单存在却停EXECUTING；results:153允许effect/result ID尾LF，两例SETTLE/outbox | **OPEN残余**；完整typed形状校验须总定义，异常安全UNKNOWN/fence/no outbox；标识符fullmatch。未证明超额或新增未授权支出 |
| A21-R1-CANDIDATE／高／P11,OBL01/03 | service:247–256→ledger:187–224；最后miss后另A1提交同意图坏quote材料，10/10 EXISTING、proofs2、flag=false，预算未重复 | **OPEN残余**；在接受决定内原子核实际existing材料，拒绝事务不提交新proof，隔离独立持久；再加非锁查找不能闭合。A1兼容扩展先由主控确认范围 |
| A21-R3-TESTSYNC／中／P09,WF-QUALITY | REG:252–275,359–426；首锁前barrier不保证持锁环；强制串行后正式“反序有效性”仍从ILLEGAL_TRANSITION而PASS | **OPEN残余**；用Event/DB观察固定双方持锁目标交错，精确死锁/锁超时断言，不接受任意异常；正序10轮仍须完整终局。异常/无进展负例现已能失败 |
| DOC-CKPT1-01／低／WF-DOCS | A2-report:5,22,35,110,126–132及contracts/execution:35–38；最新门槛、主体/004状态、006/results清单、355证据路径仍矛盾 | **OPEN_NONBLOCKING**；明确所有历史段，更新最新ckpt1-r2、真实文件/证据入口；README迁移双变体已修 |

**非finding：**仅将同字段QuoteItem序列从tuple换为list，两例结算正确；契约execution:213–215允许结构比较，未观察数据错配或竞态。保留旧两条过严失败，不据容器差异新增漏洞；r5两正例独立确认。
**验证不确定性：**额外继承分跑P11一次返回LedgerError，但旧探针未记录code；诊断10轮通过不能追溯原因。OBL02保留BLOCKED，要求复验时记录精确code/cause/同步与DB事实；未编造代码缺陷ID。

## 9. 隔离资源、清理与结束核验
- 本轮owner **a21-review-r5-4f8c2d19**；PG **676a5d253414…**、Python **a9b3920e1e02…**、网络 **dc3056e9b5bf…**；完整ID、镜像digest、标签和来源在resources.json。
- PG仅tmpfs、无宿主卷/公开端口；原仓库 `/repo:ro`，自有E `/evidence:rw`；gateway与随机下游库独立连接/事务。普通部署DSN未继承，日志脱敏，不输出secret/完整DSN。
- r4遗留两容器及网络先核原完整ID/owner/member再限定清理，未复用数据；r5结束仅按核实完整ID清理，均exit0，**owned剩余0**。
- 清理前仅review_gw和系统库、test schema0，001—006完整registry checksum正确；历史探针/README自建库均已删除。
- agent-guard-a2-pg、verivote-web/api的ID/镜像/标签/挂载/端口/运行起始时间inventory前后一致；未连接其DB，不把inventory相同夸称业务数据摘要核验。
- 被审100项、执行副本、契约、state/issues/worker报告及Git状态开始/结束/交付前一致；证据与探针保留，正式报告由主控保存。

## 10. 交主控的明确动作
原样保存本完整r5报告及index，维持 **NOT_ACCEPTED**；按本轮证据关闭EVENT/UNKNOWN并保持既有五项关闭，保留五项残余、DOC和P11验证缺口。
仅在当前A2.1委派具体补正；冻结后fresh reviewer复验原触发、相关变体及完整31/28矩阵，不以正式355全绿或重复非锁查找放行。
**本轮没有阶段ACCEPTED；不推进后段、不引入B、不进行Git发布。**
