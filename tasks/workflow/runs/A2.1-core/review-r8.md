# 独立审查：IMPLEMENTATION_ACCEPTANCE／A2.1-core／NEW r8

## 1. 结论与范围
- **结论：ACCEPTED，仅针对本轮冻结的 A2.1-core／检查点二。31 项必需要求全部 PASS，当前阻断项为零。**
- 日期／时区：2026-10-02，Asia/Shanghai；最终冻结核验时间 **07:53:35+08:00**。完整 A2／项目仍为 **PARTIAL**。
- 完整 P15 真实授权、P16/P17 真验证与 result-read、P18 真 SM2 签名、P21 真实 HTTPS 闭环仍为后段／B依赖 **BLOCKED，未计完成**。
- **不允许进入 A2.2/A2.3/A3；不授权 Git 提交、推送、PR、合并或发布。** 未修改受审源码、正式测试、要求、state、issues或正式报告。

## 2. 独立会话、授权与冻结绑定
- 仓库根 **R**：`/Users/qdcc/code/密码技术竞赛/agent-guard`；宿主仓库命令均以 R 为 cwd；下文源码相对路径以 R 解析。
- 模型：**openai/gpt-6.1-sol**；当前推理配置 **high**，历史 xhigh 不覆盖它。API 未暴露本轮真实 session／Task ID，请主控绑定实际调用记录。
- 原授权：`ses_f0ac0e676ffecn71p6Ww7zaqQq`／`msg_0f54148e0001ZW7yCMdK0TE97F`；恢复消息 `msg_0f9cc37f8001PyAvQX6K0ucvFu`。按父任务已核原消息，且与正式包/state一致，仅恢复同阶段 scope，本轮未自行授权。
- 分支／HEAD：`feat/a2-execution-gateway`／`b120c7cf5ec0eafb18305d1207c36dd11655b324`；**5 tracked 修改、67 普通 untracked**；staged 空，无删除／重命名。
- Writer 停写依据为父任务确认及 state 的 STOPPED_READY_FOR_REVIEW；没有冒称查询过调度器。开始／结束未观察到漂移。
- 独立重建 **102 项 snapshot**，开始／结束与执行副本的文件内容及 mode 一致：**`15dc8782e1788e0bae6359a5c7538287db679078012b50f8901ab72dea4c5b09`**。
- 契约逐文件重算及排序摘要：**`43c996ada95eebca2c5cbc72bd21b792aed03ad687736baeb4d8041a974b09a2`**；worker报告hash **`fd264c1b34cfb0bc5821ab4da7e6bbd2493ae1f869ea7665f5232fd2e619b199`**，仅作声明索引。
- 证据根 **E**：[artifacts/workflow/A2.1-core-review-r8-2fd79c61/](/Users/qdcc/code/密码技术竞赛/agent-guard/artifacts/workflow/A2.1-core-review-r8-2fd79c61/)。
- [evidence-index.json](/Users/qdcc/code/密码技术竞赛/agent-guard/artifacts/workflow/A2.1-core-review-r8-2fd79c61/evidence-index.json) SHA256：**`07fc53e3307663d4840ce2e202e857a635d96bef31a8fdaf28caf4f941c7b330`**；含 state-guide 兼容的31行 requirements、14项关闭记录、原始日志/XML/probes/commands与逐文件hash，已解析读回并核验全部引用。
- 沿原冻结排除规则；正式包另核契约hash，state/issues/worker报告另核内容hash。未新增受审源码／测试排除项。

## 3. 实际静态检查与调用链
- 全文读取 task-v1、correction-r1—r4、两包审、完整 review-r2/r3/r5/r7、issues、workflow/stage/state/模板、AGENT、原 A1/A2任务与历次验收、两轮ckpt1、三份docs、README及implementation-r1—r5；worker报告不作证明。
- 检查完整 tracked/staged diff、untracked清单、全部实际 contracts/ledger/execution/tools、001—006、全部正式测试与fixtures、依赖/CI/Compose；具体源码与hash见 `inspection.json`。
- 追踪 `accept_invocation→params/policy/catalog→_accept_checked→A1._accept_tx`：三条接受路径均 checked；动态权限/proof/意图检查后，同conn校验实际 EXISTING，拒绝回滚proof，释放锁后独立持久flag。
- 追踪 `run/reconcile→接受材料→task→根至叶grants→operation→lease→独立下游→decide/finalize`；核验四条件租约、全祖先终局原子事务、UNKNOWN保预算、不可变事件/outbox与稳定UTC iat。
- 以下 U/G/P/N/H/SM 为**本轮独立实跑**；I 为**本轮静态查证**。可信fixture不等于密码验证，普通JSON不等于RFC8785／SM3。

## 4. 完整需求与验收矩阵
全部31项均当前必需，ID与state完全一致；P来源为原A2§7，OBL为ckpt1-r2六义务，WF为正式stage/合同。G=正式PG，U=unit，P=继承源码本轮重跑，N=新r8，H=A1原探针，SM=README；完整命令、testcase IDs及hash见index。
| ID | 实现／正式测试或探针 | 必须观察及本轮结果 | 证据／状态 |
|---|---|---|---|
| A2-P01 | finalize；core::test_p01 | 唯一70000/1订单；三层预留0、结算70000/1；事件/outbox一致 | G/SM **PASS** |
| A2-P02 | decide/results；core::test_p02、refusal探针 | 同键持久拒绝才RELEASE、不结算；阻止迟到成功；错键/工具UNKNOWN | G/P **PASS** |
| A2-P03 | 零额工具；core::test_p03、通知并发 | 0金额仍计1次；结算/释放正确；读结果固定、通知唯一 | G/P **PASS** |
| A2-P04 | worker；recovery::test_p04、entry_windows | 未提交不可见且零效果；真实SIGKILL、新PID持久恢复 | G/P **PASS** |
| A2-P05 | run/recovery；core::test_p05 | 真下游提交＋响应丢失替身→UNKNOWN保70000/1；同单一次结算 | G **PASS** |
| A2-P06 | worker终局窗口；recovery/followups | kill时1单/0outbox；重启仍1单、1终局、1outbox | G/P **PASS** |
| A2-P07 | 终局事务、checked callback | 真实部分节点/事件/outbox/status全回滚；callback拒绝proof回滚、重试重检 | G/P **PASS** |
| A2-P08 | reconcile/downstream；deadline | 查无结果不释放；迟到唯一成功；实际SQL持锁自动有界超时 | G/P **PASS** |
| A2-P09 | claim/finalize；恢复/锁效力探针 | 规定10轮；fencing、旧UNKNOWN40例、真持锁环及串行/异常/无进展反测 | G/P **PASS** |
| A2-P10 | 内部恢复／A1动态复核；recovery::test_p10 | 撤销/过期/停key后恢复原意图；外部checked重试拒绝；真查询后段 | G/P **PASS** |
| A2-P11 | candidate/params；quotes、last-miss、r5回归/r8 | 原成本/快照；最后miss好坏各10；严格非法版本拒绝，最大版本执行/删报价重试 | G/P/N **PASS** |
| A2-P12 | decide/results；full-binding、typed探针 | 完整键/工具/意图/报价/结果/effect关联；坏shape安全UNKNOWN；合法list结算 | G/P/N **PASS** |
| A2-P13 | 全祖先预算／混合锁；concurrency::test_p13 | 根/中间/次数/接受结算恢复各10轮；有界非负，无反序无界等待 | G/P **PASS** |
| A2-P14 | 独立MockDownstream；downstream/通知探针 | 同键唯一、冲突不覆盖；执行/查询无错服务认证零效果/泄漏 | G/P **PASS** |
| A2-P15-CORE | params/policy；validation/unit/r8 | 四工具、类型/集合/scope/归属/完整链负例零新增；非法可信集/catalog仍格式拒绝 | U/G/N **PASS** |
| A2-P19 | migrations/material；upgrade/legacy探针 | 001/003/004/005→006合法非法七表/full registry保全；深params五入口持久隔离 | G/P **PASS** |
| A2-P20 | 001—006 guards；SQL/seal/savepoint探针 | 意图/证据/事件/节点/操作/路径改删、双终局拒绝；合法UPDATE/初写有效 | G/P **PASS** |
| A2-CKPT1-OBL01 | static→candidate→checked | 候选不依赖当前报价；版本schema先拒；实际EXISTING同事务校验，不绕动态复核 | G/P/N **PASS** |
| A2-CKPT1-OBL02 | miss→解析失败→安全重查 | 好/坏/撤销/重放/过期各10；精确code/cause、时序、DBtime/expiry及全状态落盘 | G/P **PASS** |
| A2-CKPT1-OBL03 | 完整事实/sidecar/永久防删 | 最后miss坏材料拒绝、不留proof；锁释放后flag；flag失败亦不成功 | G/P **PASS** |
| A2-CKPT1-OBL04 | lease四条件/UNKNOWN现场复核 | owner/version/state/锁后expiry；无接管过期拒绝，旧返回不覆盖当前事实 | G/P **PASS** |
| A2-CKPT1-OBL05 | sidecar/phase-seq/seals | 七表不改行、全部已提交事件封存；升级回滚、合法更新/owned清理兼容 | G/P **PASS** |
| A2-CKPT1-OBL06 | snapshots/results/receipts | 三处版本规则一致；完整原报价；不可变PENDING材料、稳定ID/time/UTC iat | G/P/N **PASS** |
| WF-A1-REGRESSION | A1全部＋原探针 | 独立68 unit/78 PG，U1/P1—14/F1—5；原4＋1通过，升级等价增强保全 | G/H/P **PASS** |
| WF-INDEPENDENT-PROBES | 新r8＋继承源码当前重跑 | 新58例：Unicode/control、三schema、查找前零状态、最大版本全生命周期；最终482通过 | P/N **PASS** |
| WF-QUALITY-CHECKS | ruff/diff/full suites/CI | 检查及137/522正式套件无fail/error/skip；新增目录收集，锁效力反测有效 | U/G/I **PASS** |
| WF-PY311-ENV | 新3.11约束安装/PG16 | CPython3.11.16、pip check/freeze、psycopg3.2.13、真实PG16.15 | ENV/G **PASS** |
| WF-RESOURCE-ISOLATION | owner/独立DB/schema | RO源码、独占新PG/下游；普通DSN未继承；仅owned精确清理，原7资源核对 | RES **PASS** |
| WF-IMMUTABLE-BASELINE | HEAD/冻结迁移/默认A1 | 001—003及其他A1基线不变；获准service最小兼容；004—006 checksum一致，无B偷渡 | I/G **PASS** |
| WF-DOCS-REPORT | 当前report/README/worker索引 | 66行当前事实、tracked5、137/522、56格式文件与证据入口一致；README双烟测 | I/SM **PASS** |
| WF-SNAPSHOT-COVERAGE | manifest/contracts/Git/copy | 102项及契约、控制输入、执行副本开始/结束一致，无观察到漂移 | I **PASS** |
后续完整P15/P16/P17/P18真签名/P21仍排除于本段完成；P18内本段稳定材料及业务恢复已实测，未整体移出。

## 5. 必查专项与历史回归
- C1独占资源、C2原子候选/P11、C3七表升级、C4永久事件/路径、C5四条件租约、C6完整报价/稳定材料均有当前实跑，不以设计放行替代。
- A1 P3/P5/P6、A2 P09/P13/P14、通知、P11报价/资源消失与拒绝变体、旧新终局、固定锁交错及真持锁环规定组均独立连接＋Barrier/Event **各10轮**。
- 独立进程探针观察 **393→394、975→976、1355→1356**；旧exit **−9**、新exit **0**；kill前后逐祖先计数、真实订单、事件/outbox完整断言，正式套件另执行真实恢复。
- 001/003/004/005×合法/非法 **8组合**比较非零70000/1、撤销、七表全部列/行与**完整registry**；重复no-op；直接SQL封存/伪造/并发/savepoint及合法初写均通过。

## 6. 本轮独立命令／退出码／计数
环境：新 Python3.11.16、PG16.15、psycopg/binary3.2.13、pytest8.3.5、ruff0.11.13、setuptools79.0.1；正式执行cwd为hash一致的自有 `/evidence/candidate`。表中exit为真实子命令值，`run.py`驱动exit0不替代pytest结果；完整argv/cache/XML见 `*-command.json`。
| 实际命令／目标 | 真exit | pass/fail/error/skip／结果 | E原件 |
|---|---:|---|---|
| `pip install -e /evidence/candidate[dev] -c …/constraints.txt`；`pip check/freeze` | 各0 | 新约束安装/检查通过；无新增运行依赖，不宣称完整传递依赖锁 | install、pip-check/freeze、environment |
| `ruff check --no-cache .`；`ruff format --check --no-cache .`；`git diff --check` | 各0 | check通过；**56 files**格式正确；开始/结束diff干净 | quality-*、diff-check* |
| `pytest tests/unit tests/test_scaffold.py tests/test_docs.py` | 0 | **137/0/0/0** | unit.log/xml |
| `pytest tests/integration` | 0 | **522/0/0/0** | integration.log/xml |
| A1原unit/骨架/docs；八个A1 PG文件独立分跑 | 0/0 | **68/0/0/0；78/0/0/0** | a1-unit、a1-pg |
| 11个A2 PG文件显式分跑 | 0 | **444/0/0/0**，含新增98版本回归 | a2-pg.log/xml |
| `python -m agent_guard.ledger.migrate`两次；结束checksum/DB核验 | 各0 | 首次001—006，第二次no-op；六版本checksum正确、test schema0 | migrate-*、database-end/final |
| 借用r7源 `pytest /evidence/probes`，原424项 | 1 | **422/2/0/0**；两条合法list过严UNKNOWN预期，非finding | inherited-current.log/xml |
| 新写 `test_r8_independent.py`独立分跑 | 0 | **58/0/0/0** | fresh-r8.log/xml、probe源码 |
| 首次自有list适配后的全探针 | 1 | **480/2/0/0**；遗留无条件UNKNOWN计数断言，reviewer适配错误 | final-probes.log/xml、first源码 |
| 完整适配后全探针，不skip/删case | 0 | **482/0/0/0**，424继承＋58新r8 | probes-verified.log/xml、adaptation.diff |
| 原A1四探针／根重建／旧002升级探针 | 0/0/1 | **4/0/0/0；1/0/0/0；0/1/0/0**，旧版本期待如§7 | history-*日志/XML及child命令 |
| README逐字Python程序，两种新空库初始化 | 0 | 两种SMOKE_OK；三层70000/1、1单、2事件/6节点、1 PENDING NULL outbox | readme-snippet/driver、smoke、observations |
| `verify-binding.py`、owner/完整ID cleanup、最终index引用核验 | 0 | 冻结一致；owned剩余0；最终证据引用hash全部匹配 | binding-*、resources、cleanup、index |

## 7. 历史核对、非finding与未执行边界
- r5原失败日志 **仅历史核对**：resource[3]收到无code的LedgerError。此次当前受控50例精确code/cause/DBclock/proof窗口均通过；**历史根因仍不可追溯，不声称TTL已解释**。
- 继承函数保留r7名称但运行资源/数据库/结果均为新r8。合法tuple→list字段未变，原契约允许结构比较；仅修正自有过严探针，并增强精确SETTLE/效果/outbox/全祖先计数，正式测试及历史原件未改。
- 原升级探针第46行只期待`["002"]`，当前实际002—006故exit1；本轮动态8组合七表/full registry断言等价且更强，未将旧失败冒报通过。
- 最后重复binding核验重写自有结束时间，index旧metadata hash检查正确报exit1；仅重算自有metadata引用后最终核验exit0。过程保存在harness notes，代码/契约没有漂移。
- 实际执行PG回滚、自动SQL锁超时、自有backend真实终止、SIGKILL/重启；响应丢失/无结果/坏outcome为port替身。真实断网、TLS/wheel部署、密码/HTTP及远程CI **NOT_RUN**，不冒称通过、不新增本段后段门槛。

## 8. Issue逐项闭环与残余风险
下列均 **CLOSED_REVIEWED，仅绑定本轮指纹**；原严重度不降级。无新增确认缺陷，无待实施补正；完整关闭证据为G/P/N及index。
| Issue／严重度／要求 | 当前位置、原trigger及本轮关闭依据 |
|---|---|
| A21-R2-SNAPSHOT／中／P11,P15-CORE,OBL01/06 | params:235–237、catalog:155–167、results:269–275；原前缀/0/leadingzero/尾字符绕过均fullmatch拒绝；可信非法集/catalog零新增，三schema与最大版本生命周期通过 |
| DOC-CKPT1-01／低／WF-DOCS | A2-report:1–66；原阶段/迁移/counts/tracked/路径矛盾已重建当前索引；实际Git、收集计数、双README实跑一致，旧报告仅历史 |
| A21-R1-LEGACY／高／P19,OBL03 | service:361–395,920–1035；原8类及深params五入口自动持久flag、保预算、零下游，fallback不漏 |
| A21-R1-OUTCOME／高／P02/P12,OBL06 | service:549–660,849–909/results；错键/工具/结果/effect/报价、坏实际dataclass均UNKNOWN；合法list正常结算 |
| A21-R1-CANDIDATE／高／P11,OBL01/03 | service:301–338、ledger/service:261–276；最后miss好坏各10、同时活跃validator10、proof回滚/内部retry/flag失败/真实DB失联有效 |
| A21-R3-TESTSYNC／中／P09,WF-QUALITY | test_execution_regressions:213–616；真双方持锁环10观察精确DeadlockDetected/Lock等待；串行、线程异常、无进展不能假PASS |
| A21-R1-LOCK／高／P09/P13 | service:478–525,684–785；原反序交错回归，统一task→grants→operation→lease，10轮完整终局 |
| A21-R1-NOTIFY／高／P15-CORE | policy:355–393,446–460；不存在/跨tenant/task/grant/holder目标拒绝零新增，合法通知与10轮幂等通过 |
| A21-R1-CHAIN／高／P15-CORE,OBL01 | policy:207–248；省mid/leaf-only/重排/错层/拼接拒绝；完整DB路径及根/中/叶正例保持 |
| A21-R1-LOG／中／安全日志 | service:103–111、worker:133–151；malformed DSN/含secret异常诊断不回显；结论限已测路径 |
| A21-R1-BOUNDS／中／P08/F5 | downstream:150–162、service:164–192；真实表锁自动超时、不人工cancel，UNKNOWN保预算；0/bool配置拒绝 |
| A21-R1-EVENT／高／P20,OBL05/06 | 005/006触发器；旧短RESERVE/SETTLE补节点、seal伪造/并发/savepoint绕过均拒绝；旧行/outbox不变，合法初写有效 |
| A21-R3-UNKNOWN／中／P09,OBL04 | service:755–785；公开旧query阻塞→失租→新终态/liveowner共40例，准确拒绝，不返回cached UNKNOWN |
| A21-R5-P11-EVIDENCE／验证缺口／OBL02 | E `p11-clock-evidence.json`；当前mandatory同步/精确codes/causes/proof与DB时间证据齐；只关闭当前缺口，历史未知根因风险保留 |

## 9. 隔离资源与结束核验
- owner=`a2.1-core-review-r8-2fd79c61`；新PG **534c03b1f624…**、Python **99c21f31db3c…**、网络 **a09452815e15…**；完整ID/镜像/label/mount见resources.json。PG tmpfs、无公开端口；原仓库RO、自有E RW，网关/随机下游不同数据库与事务。
- 普通部署DSN未继承；日志/XML屏蔽完整及pytest截断凭据。仅核完整ID＋owner后删除本轮两容器及空网络，均exit0，owned剩余 **0**；自有探针/原始日志/缓存保留。
- 原A2、verivote两容器及ab-review-a/b四容器共 **7** 个既有资源身份/配置/运行起始/暂停状态前后一致；此次外部新增/删除/变化均0，未连接其DB，不把inventory相同夸称业务数据摘要验证。结束102项、契约、控制输入、Git及执行副本一致。

## 10. 交主控的明确动作
**原样保存本完整r8报告及最终index，核对原始日志/XML、14项关闭依据与上述指纹；按state-guide绑定真实reviewer会话，执行最终checker后记录当前A2.1-core ACCEPTED。随后维持当前阶段、完整A2 PARTIAL，停等用户查看与下一阶段另行批准；不进入后段，不引入B，不进行Git发布。**
