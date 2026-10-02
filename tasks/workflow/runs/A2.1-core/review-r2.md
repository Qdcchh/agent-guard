# 独立审查：IMPLEMENTATION_ACCEPTANCE／A2.1-core／r2

## 1. 结论与范围

- **结论：NOT_ACCEPTED。** 本轮正式套件通过，但独立反例确认了10项代码缺陷；9条历史发现均有本轮复现依据，不能关闭。
- 日期：2026-10-01，Asia/Shanghai；结束核验时间 `15:06:35+08:00`。
- 当前阶段仅为 **A2.1-core／检查点二**，依据正式 `task-v1.md`、A2原任务、检查点一r2及原设计/安全/验收文档。完整A2仍为 **PARTIAL**。
- **不允许进入A2.2/A2.3/A3**；不授权commit、push、PR、合并或发布。
- 本轮未修改受审源码、正式测试、标准、state、issues或报告；仅创建自有证据、代码副本、探针和隔离资源。
- 后续真实B验权/密码依赖仍未完成，不能被本轮核心测试替代，也不是本轮核心缺陷的豁免理由。

## 2. 独立会话、授权与版本绑定

| 项目 | 实际核对结果 |
| --- | --- |
| Reviewer | NEW r2；模型 `openai/gpt-6.1-sol`。本API未暴露本轮session/Task ID及实际推理档位，未伪填；主控应从真实调用记录绑定 |
| 仓库 | `/Users/qdcc/code/密码技术竞赛/agent-guard`；本文代码/证据路径均以此为根 |
| 真人授权 | 主控已核角色及原文：`ses_f0ac0e676ffecn71p6Ww7zaqQq`／`msg_0f54148e0001ZW7yCMdK0TE97F`，仅A2.1，不含下一阶段或Git发布 |
| Writer冻结 | 按主控移交，MiMo `ses_f0aa292caffeODmd0G8jUSZ1Y9` 已停写；state为 `READY_FOR_REVIEW`，不是ACCEPTED；开始/结束无候选漂移 |
| 分支／HEAD | `feat/a2-execution-gateway`／`b120c7cf5ec0eafb18305d1207c36dd11655b324` |
| 候选指纹 | **`b2ad9065b9d24a3e71f6f3e27a42416326da2a8c9bd0cbfa3d6be9003c279288`**，独立重新生成，95项manifest开始/结束完全一致 |
| 契约摘要 | **`701a06938365ba0dd74399f1952566d57562bd141dcecdff2398cd8cc45cbef5`**，逐文件重新散列及规范JSON摘要验证 |
| 正式任务包SHA256 | `67896f80e7b80fe05087f88ef08576c805117bfdd12654addff03efadf2bfec4` |
| issues SHA256 | `32bb4ffa9abbfe3e27097e5bf895b32cf78c343dfb336fcf78643c25ebb9d37d`，开始/结束不变 |
| Git范围 | 4个tracked修改；无staged diff、删除或重命名。所有相关untracked源/迁移/测试纳入95项清单，不以HEAD或空diff代替 |
| 执行副本 | 原仓库只读挂载；正式测试在自有 `/evidence/candidate` 执行，避免迁移测试写入受审目录；95个文件内容开始/结束均与候选哈希一致 |
| 排除范围 | 沿冻结规则排除生成缓存、artifacts及控制运行记录；正式task-v1另列契约散列，未借排除规则修改受审内容 |

## 3. 实际检查及证据入口

已阅读要求入口、AGENT、README、三份docs、A2原任务、两轮检查点记录、A1历史/最终验收、正式包、workflow契约/状态/台账/模板；检查完整tracked diff、全部新增execution/tools、004、A2正式测试及相关fixtures。
直接检查了 `accept_invocation → policy/catalog → ExecutionLedger.accept`、`run/reconcile → _claim → downstream → _decide/_finalize`、lease/event/outbox SQL、worker配置/错误输出，以及周边ledger路径、锁序、动态校验、初始化、迁移与001—003约束。
**代码静态查证、以下本轮独立运行、历史报告索引分开处理；worker成功总结不作证明。**

证据根 **E**：`artifacts/workflow/A2.1-core-review-r2-c6d39e12/`。
完整入口：[evidence-index.json](/Users/qdcc/code/密码技术竞赛/agent-guard/artifacts/workflow/A2.1-core-review-r2-c6d39e12/evidence-index.json)，SHA256：
**`c7f57204d2e6e2ebe812dbd92bbf85a21c56cbe50f67213e14e6be1a57780009`**。
索引保存109个证据文件的**relative path、完整SHA256、kind、exit_code**，31项需求状态、命令入口及JUnit实际计数；已读回核对。
别名：`S`冻结/Git；`Q`质量；`ENV`安装环境；`U/G`全unit/PG；`A1/A2`分套回归；`P`继承探针全套；`F/R`补充/重复；`V/N`新r2反例/正例；`E/D`入口/真实锁等待；`M`迁移；`H`A1原历史探针；`O`观察JSONL；`RES/I`资源/不可变基线。
`O=E/probe-observations.jsonl` SHA256：`01f09dc7814f755676ddd749c8ef8950642d097178855a8982de49e8bb5a26f4`；`observation-index.json`给出每种观察的精确行号。

## 4. 完整需求矩阵

31个ID与 `state.expected_requirement_ids` 完全一致；28个运行类ID均有**本轮实际执行**，没有用历史日志补PASS。P项原始来源为A2任务§7及正式包；OBL为检查点一r2§13—20；WF为阶段/验收契约。
测试缩写：`C/REC/QT/CON/VAL/DS/MIG` 分别为 `tests/integration/test_execution_core/recovery/quotes/concurrency/validation.py`、`test_downstream.py`、`test_a2_migrations.py`；探针文件在 `E/probes/`。

| 需求ID | 必需 | 实现／测试或探针 | 必须观察及本轮结果 | 类型／证据 | 状态 |
| --- | --- | --- | --- | --- | --- |
| A2-P01 | 是 | run/_finalize；C::test_p01* | 唯一70000分订单；三层预留归零、结算70000/1；RESERVE/SETTLE/outbox一致 | 独立运行 G/A2 | PASS |
| A2-P02 | 是 | _decide；C::test_p02*；test_review/test_r2_variants | 正常持久拒绝通过；但别的operation拒绝及字符串refusal也释放，原键仍能迟到成功 | 独立运行 G/P/V | **FAIL：OUTCOME** |
| A2-P03 | 是 | 零成本工具；C::test_p03*；test_r2_positive | 合法目标通知失败释放calls；文档结果固定；通知10轮唯一效果，三层计数正确 | 独立运行 G/N/F | PASS |
| A2-P04 | 是 | worker；REC::test_p04*；test_entry_windows/test_followups | 提交前不可见且回滚零效果；真实SIGKILL后新PID恢复持久状态 | 独立运行 G/E/F/O | PASS |
| A2-P05 | 是 | run/recovery；C::test_p05* | 下游真实提交后响应丢失替身→UNKNOWN保70000/1，恢复同单一次结算 | 独立运行 G/A2 | PASS |
| A2-P06 | 是 | worker终局窗口；REC::test_p04_p06* | SIGKILL时1订单、0outbox；重启后仍1订单、1终局、1outbox | 独立运行 G/F/O | PASS |
| A2-P07 | 是 | _finalize/store；C::test_p07*；test_followups | 真实部分节点、事件、outbox写后异常全部回滚，保原预留，之后可恢复 | 独立运行 G/F | PASS |
| A2-P08 | 是 | reconcile/downstream；C::test_p08*；test_deadline | 查无结果/迟到成功语义通过；下游SQL等待无上限，违反配套bounded恢复要求 | 独立运行 G/D/F | **FAIL：BOUNDS** |
| A2-P09 | 是 | _claim/_finalize；REC::test_p09*；test_review | 双恢复者及旧owner终局保护通过；确定性混合锁路径10/10死锁 | 独立运行 G/P/R | **FAIL：LOCK** |
| A2-P10 | 是 | 内部恢复／A1动态复核；REC::test_p10* | 撤销、过期、key停用后原意图可恢复；外部接受重试拒绝；真实查询留后段 | 独立运行 G/A2 | PASS |
| A2-P11 | 是 | candidate；QT::test_p11*；入口/重查探针 | 合法原快照重试及竞态通过；错quote身份候选仍EXISTING、未隔离 | 独立运行 G/F/V/E | **FAIL：CANDIDATE** |
| A2-P12 | 是 | _decide；C::test_p12*；新/继承outcome探针 | 金额/供应商/同总额双行分配错配正确UNKNOWN；错键/result/type/effect却终局 | 独立运行 G/P/V/N | **FAIL：OUTCOME** |
| A2-P13 | 是 | 全祖先预算／混合锁；CON::test_p13* | 根/中间/次数竞争各10轮不超限；claim与终局反向锁导致死锁 | 独立运行 G/P | **FAIL：LOCK** |
| A2-P14 | 是 | MockDownstream；DS::test_p14*；通知并发探针 | 执行/查询无错服务凭据拒绝；意图冲突不覆盖；订单/通知独立库唯一效果 | 独立运行 G/F | PASS |
| A2-P15-CORE | 是 | params/policy；VAL::test_p15*；chain/notify探针 | 普通严格参数负例通过；不存在/跨租户通知目标及截短权限链仍接受 | 独立运行 U/G/P/V | **FAIL：NOTIFY、CHAIN** |
| A2-P19 | 是 | 004／worker入口；MIG::test_p19*；升级/旧行探针 | 七表/完整登记保全通过；非法或证据缺失旧行直接执行，未自动隔离 | 独立运行 G/M/P/V | **FAIL：LEGACY、SNAPSHOT** |
| A2-P20 | 是 | 004 guards；MIG::test_p20*；append探针 | 改删、phase/seq、双终局、合法UPDATE验证通过；提交后事件可添第四节点 | 独立运行 G/P/F | **FAIL：EVENT** |
| A2-CKPT1-OBL01 | 是 | accept静态→candidate→A1；QT::test_obl01* | 入口顺序及动态验权正确；持久快照关联/完整权限链校验不完整 | 独立运行 G/F/V/E | **FAIL：CANDIDATE、CHAIN** |
| A2-CKPT1-OBL02 | 是 | 解析失败安全重查；QT::test_obl02*；重复探针 | 实际miss→另一accept提交→报价/申请消失→重查；撤销/重放/变意图/新键拒绝 | 独立运行 G/F/V | PASS |
| A2-CKPT1-OBL03 | 是 | candidate/sidecar/DELETE guards | 永久操作防删成立；接受事实不足仍可执行或作为候选，隔离依赖手动调用 | 独立运行 G/P/V/E | **FAIL：LEGACY、CANDIDATE** |
| A2-CKPT1-OBL04 | 是 | lease四条件；REC::test_obl04*；fresh lease探针 | 新鲜租约分别验证错owner/错version；锁等待后过期拒绝；UNKNOWN保留、旧owner不覆盖 | 独立运行 G/R/V | PASS |
| A2-CKPT1-OBL05 | 是 | sidecar/phase-seq/event guards | 七表不加列、不改行；改删保护成立，但事件节点集合未封存 | 独立运行 G/M/P/F | **FAIL：EVENT** |
| A2-CKPT1-OBL06 | 是 | snapshot/outcome/receipts | 稳定ID/UTC iat/PENDING及不可改outbox成立；解码、效果绑定及ledger材料一致性有缺陷 | 独立运行 G/P/V/N | **FAIL：OUTCOME、SNAPSHOT、EVENT** |
| WF-A1-REGRESSION | 是 | A1全部正式测试及原探针 | 独立68 unit＋78 PG；原4＋1探针通过；非零升级用当前更强等价断言验证 | 独立运行 A1/H/M/P/R | PASS |
| WF-INDEPENDENT-PROBES | 是 | 继承源码重新审查＋28个新r2case | 独立探针执行/保存义务完成；发现的失败仍是放行阻断，不被该程序项PASS抵消 | 独立运行 P/V/N/O | PASS |
| WF-QUALITY-CHECKS | 是 | ruff、diff、全部正式套件、CI目录 | 所有规定质量/正式测试命令通过；CI收集新增目录；不代表反例通过 | 独立运行 Q/U/G | PASS |
| WF-PY311-ENV | 是 | 新Python容器、约束安装、PG | CPython3.11.16新安装，pip check通过；真实PG16.15；无新增依赖 | 独立运行 ENV/U/G | PASS |
| WF-RESOURCE-ISOLATION | 是 | Docker owner／随机库schema | 新r2实例独占；只用TEST DSN；精确清理；无关容器身份配置状态未变 | 独立运行 RES/ENV | PASS |
| WF-IMMUTABLE-BASELINE | 是 | HEAD字节比对／A1回归 | 001—003、ledger、A1契约、依赖文件与HEAD逐字节相同；无B代码/依赖引入 | 静态查证 I/S＋运行A1 | PASS |
| WF-DOCS-REPORT | 是 | README／A2-report／实施报告 | tracked-only笔误残留、阶段/数量/环境矛盾；缺具体初始化步骤；“不泄secret”与实测冲突 | 静态查证 S；运行P | **FAIL：DOC-CKPT1-01、LOG** |
| WF-SNAPSHOT-COVERAGE | 是 | 独立snapshot/contract/Git核验 | 全95项及另列正式包一致；开始/结束及执行副本无漂移 | 静态/实际核验 S | PASS |

后续边界：完整P15真实授权、P16 token/proof真实签验、P17 result-read、P18真实SM2签名/验签、P21 HTTPS闭环均 **后续阶段／B依赖BLOCKED，未计PASS**。P18中本阶段outbox材料与业务恢复义务已实际测试，未整体移出。

## 5. 专项、历史缺陷及等价性

| 专项 | 本轮结论 |
| --- | --- |
| C1 | A1/A2 Compose只读渲染project分别为 `agent-guard`／`agent-guard-a2`；r2使用独立owner网络及docker-run资源，不接共享project |
| C2/P11 | 报价正例及5种竞态模式各10轮通过；另做实际申请消失10轮；不能据此掩盖错身份候选 |
| C3/P19 | 001/003×合法/非法四组合，真实70000/1、撤销、七表全行及完整迁移登记比较通过；旧行执行隔离失败 |
| C4/P20 | phase/seq、改删及操作/path防删通过；追加节点绕过确认 |
| C5 | owner/version/锁后DB expiry/状态实测通过；全局锁序另有独立阻断 |
| C6 | 同总额双行单价分配变化也保持UNKNOWN；稳定待签材料通过；错误outcome关联和宽松解码失败 |
| P04 | 本轮观察PID `624→625`及再次`763→764`；旧进程exit `-9`，新进程exit `0`，DB效果/计数/事件/outbox完整断言 |
| A1历史F1—F5 | 本轮全部正式回归及原4＋1探针通过；根同ID重建、subject、calls=1、隔离、连接配置均保持 |
| 旧升级探针 | 原源码未修改并实跑：第46行硬编码 `["002"]`，实际为 `["002","003","004"]`，故失败；不是迁移缺陷。当前正式升级及独立四组合比较七表与完整登记，等价且更强 |
| 并发覆盖 | A1 P3/P5/P6、A2 P09/P13/P14正式组各10轮；另有10轮锁反转、旧新终局竞争、根初始化、通知及P11变体；独立连接+barrier/event，不用sleep猜竞态 |

## 6. 本轮独立运行命令与计数

环境：Python **3.11.16**、psycopg/psycopg-binary **3.2.13**、pytest **8.3.5**、ruff **0.11.13**、setuptools **79.0.1**、PostgreSQL **16.15**。
主机命令cwd为仓库根；Docker正式测试cwd为哈希绑定的自有候选副本。完整参数、缓存/XML路径及真实子命令退出码见索引中的 `commands_evidence`。驱动脚本exit0不被用来替代内部pytest失败码。

| 实际命令／执行目标 | 真退出码 | pass/fail/error/skip | 证据 |
| --- | --- | --- | --- |
| `pip install -e /evidence/install-src[dev] -c /repo/constraints.txt`；`pip check` | 0／0 | 安装及依赖检查通过 | ENV |
| `python -m ruff check --no-cache .`；`ruff format --check --no-cache .` | 0／0 | check通过；51 files formatted | Q |
| `git diff --check`，开始及结束 | 0／0 | 无whitespace错误 | Q/S |
| `pytest tests/unit tests/test_scaffold.py tests/test_docs.py` | 0 | **137/0/0/0** | U |
| `pytest tests/integration` | 0 | **184/0/0/0** | G |
| 独立分跑A1原unit/骨架/docs；A1八个PG文件 | 0／0 | **68/0/0/0；78/0/0/0** | A1 |
| 独立分跑七个新增A2 PG文件 | 0 | **106/0/0/0** | A2 |
| `python -m agent_guard.ledger.migrate` 两次 | 0／0 | 首次001—004；第二次no-op，结束registry checksum核对 | M/RES |
| `pytest /evidence/probes`，继承源码本轮重跑 | 1 | **83/38/0/0**，121case | P |
| 分跑 `test_followups.py`／`test_repetitions.py`／`test_upgrade.py` | 1／0／0 | **55/3/0/0；20/0/0/0；4/0/0/0** | F/R/M |
| 分跑 `test_entry_windows.py`／`test_deadline.py` | 1／1 | **1/1/0/0；0/1/0/0** | E/D |
| 新写 `test_r2_variants.py`／`test_r2_positive.py` | 1／0 | **12/14/0/0；2/0/0/0** | V/N |
| A1原 `test_missing_invariants.py`／`test_root_rebuild.py` | 0／0 | **4/0/0/0；1/0/0/0** | H |
| A1原 `test_upgrade_nonzero.py` | 1 | **0/1/0/0**，上述过时版本断言 | H |
| 资源核验、精确cleanup、结束snapshot | 0 | owned容器0、网络已删、测试schema0、指纹不变 | RES/S |

重复分跑不累计为独立case总量：继承探针121case、新r2探针28case，共149个不同case；其结果为 **97 passed、52 failed**，失败均保留。
准备环境有两次reviewer工具脚本 `KeyError: Tmpfs`（optional Docker字段）退出1；尚未运行业务测试。修正自有inventory后安全续接**本轮**已创建资源，记录于 `setup-recovery.json`，未改受审代码或测试。

## 7. 历史证据与未执行边界

- r1只借用了探针**源码**及资源归属记录；未复制r1成功日志充作本轮实跑。实施报告及历史验收数量仅作索引。
- 本轮真实执行：独立PG事务/回滚、真实锁等待及取消自有backend、真实进程SIGKILL/重启。
- 响应丢失、查询无结果及异常outcome为明确标注的port替身；不是实际断网或TLS部署。
- 远程CI **NOT_RUN，未授权触发**；wheel部署、真实网络故障、真实SM2/SM3及HTTP/TLS闭环未执行，不作通过声明。

## 8. 缺陷、纠正与再验要求

下表简称 `service/store/worker` 为 `src/agent_guard/execution/*.py`，`policy/catalog/downstream` 为 `src/agent_guard/tools/*.py`。**高/中严重度各项均阻断本阶段接受**；均为本轮确认，不是仅沿用r1结论。

| Issue／严重度／要求 | 位置、trigger与观察／影响 | 具体纠正及再验要求 |
| --- | --- | --- |
| **A21-R1-LOCK／高**；P09/P13 | `service:343–367,432–448`：claim先FOR UPDATE operation再task/grants，终局相反。独立连接用event固定交错，**10/10 DeadlockDetected**，可中断已有效果操作的恢复；P/O | 非锁读取得不可变定位，再统一task→根至叶grants→operation→lease并锁后复核；必要有界重试。正式加入此固定交错及接受/恢复/终局10轮，不能仅加重试掩盖反序 |
| **A21-R1-LEGACY／高**；P19/OBL03 | `service:269–367,534–559`、`store:223–227`：worker只查已有flag，不自动验证材料。003→004后8种旧行：extra/malformed params、缺snapshot/evidence、错items/quote、bool snapshot、缺RESERVE路径均未flag；7种SUCCEEDED并真实下单，缺snapshot变FAILED并释放。新r2 run/reconcile/candidate也未自动隔离；P/V/O | 每个内部执行/对账/候选入口复核完整接受事实、严格参数/版本/成本/快照、首次证据及全RESERVE路径/delta；不足自动sidecar隔离，保预算、零下游调用。手动helper通过不能代替入口保障；逐入口及旧库变体正式回归 |
| **A21-R1-OUTCOME／高**；P02/P12/OBL06 | `service:386–407,477`：未比较operation_id，未验证结果/effect语义和精确类型。别的键成功被结算；别的键拒绝释放后原键仍下单；字符串`"false"`拒绝在已有订单时释放；坏result、缺effect、bool金额也接受。查询入口新变体同样终局；P/V/O | 严格验证typed outcome、稳定键、工具/意图、完整quote、金额、per-tool effect及结构化result关联；只对同键持久终局拒绝RELEASE，异常保持UNKNOWN/no outbox。执行和query全部变体及迟到原键效果再验 |
| **A21-R1-NOTIFY／高**；P15-CORE | `policy:315–325`：仅查template/recipient，未查引用操作。不存在及跨租户目标均accept并产生1条通知、结算calls；P/O | 接受前可信查询目标存在、同tenant/task且当前授权可访问，固定安全访问政策；不得相信body自报。负例要求零新增proof/预留/操作/通知，加入有效目标正例 |
| **A21-R1-CHAIN／高**；P15-CORE/OBL01 | `policy:186–206,254`、`contracts/execution.py:143–149`：只比较所提供相邻约束，不核完整DB路径。叶-only、缺mid及超长链均接受；完整限制链拒绝的输入可通过省略限制祖先绕过；P/V/O | 将每层可信约束与grant身份/位置及不可变DB父链对应，校验完整root→leaf、层数和每维收窄；在A2.1可信fixture层完成，不冒充B验签。根/中间调用正例及省略/重排/错层负例再验 |
| **A21-R1-LOG／中**；原A2§6、AGENT安全日志、WF-DOCS | `worker:126–127`、`service:373–381`：原异常被格式化输出/带入reason。malformed DSN含合成secret marker，worker stderr确实回显；P/O。未声称已发生生产secret泄漏 | 输出稳定错误码/脱敏摘要，不打印原异常、DSN、secret或敏感参数；配置解析错误亦收敛。加入malformed DSN及下游异常含secret的捕获测试，stdout/stderr/reason均不得泄漏 |
| **A21-R1-BOUNDS／中**；P08、A1 F5关联恢复要求 | `downstream:130–131`：connect_timeout=5不约束建连后的SQL；实际statement_timeout/lock_timeout均`0`。自有ACCESS EXCLUSIVE锁令请求等待，须取消自有backend才得到UNKNOWN；D/F/O | 所有下游执行/查询连接设置有限正SQL等待上限，配置拒绝0，统一有界尝试/退避；失败未知保预算。复验真实锁等待自动超时而非reviewer取消，并检查gateway只读连接上限 |
| **A21-R1-EVENT／高**；P20/OBL05/06 | `004:103–123`、`001:201–215`：仅挡UPDATE/DELETE。已提交RESERVE和SETTLE事件仍可INSERT第四节点，DB节点数4而outbox仍原3节点；P/F/O | 保护事件节点集合的完整性和提交后封存；拒绝追加、错路径/位置/delta/额外节点，不禁合法首次原子写入和owned cleanup。正式直接SQL绕过及outbox与DB材料一致性再验 |
| **A21-R1-CANDIDATE／高**；P11/OBL03 | `policy:328–363`、`service:212–246`：只核items和总额；快照quote_id/version不同于原params/成本列时，报价删除后仍EXISTING，未flag；E/O | 比对所有持久身份/版本/币种及参数、成本、snapshot字段关联，异常候选隔离保预算；不得用当前报价补造。加入升级旧行、候选hit和miss后重查两条路径负例 |
| **A21-R2-SNAPSHOT／中**；P19/OBL06、AGENT严格类型 | `catalog:98–149`：`int/str`强转和普通json解析接受bool、浮点截断、数字字符串、未知/重复字段、null身份；负quantity×负unit_price也能得到合法总额。继承4种及新r2变体均未拒绝；P/V | 使用有界严格存储模式：重复/未知字段拒绝、精确类型、非负有界价格/正数量、合法ID/version、唯一SKU及完整字段、总额重算；禁止强转修复。合法round-trip及各异常旧行隔离/零效果再验 |
| **DOC-CKPT1-01／低、非单独代码阻断**；WF-DOCS | `tasks/A2-report.md:10,21,34,99,102`、`implementation-r1.md:79,94`：仍称tracked只有contracts，实为4文件；阶段/004/环境/182计数有残留矛盾，锁序声明与代码不符。`README:140–155`缺具体可信数据及下游provision步骤；静态S | 当前仍 **OPEN_NONBLOCKING**，不能接受“已纠正”声明。同步真实清单/计数/阶段；提供可执行可信初始化、独立下游provision和操作创建说明，清除普通DSN；主控安排文档烟测，不能改冻结标准 |

历史NOTIFY的“other-grant”也观察到接受，但仅“grant不同”不足以独自证明无访问权：原要求需明确可访问政策。本轮阻断依据是**不存在/跨租户目标及完全未作目标访问查证**，不把未定义政策机械认定为额外漏洞。
其余9条历史项均确认上述实质trigger；**没有代码issue关闭**。快照字段默认currency的观察不是单独定罪依据，SNAPSHOT主要依据重复/未知字段、bool/浮点/负数等明确规则。

## 9. 资源与结束核验

- r1资源先核对原 `resources.json`、完整ID、owner及网络成员；按用户授权精确移除其两容器和owned网络，未复用r1数据；证据 `RES/r1-owned-cleanup.json`。
- 本轮owner **`a21-review-r2-c6d39e12`**；PG容器 `45631f040f69…`、Python容器 `f54dafd8f68d…`；完整ID、镜像digest、标签、挂载及端口见 `resources.json`。
- PG为tmpfs、无宿主卷及公开端口；Python只读挂载原仓库、可写挂载自有E；gateway和随机下游库是独立连接/事务域。
- 普通部署DSN及AG_WORKER配置未继承；只注入本轮TEST DSN；证据日志/XML脱敏。历史原探针用本轮实例中新建的固定安全库名，运行后精确删除。
- 清理前只剩 `review_gw`和系统库，测试schema **0**，迁移登记001—004 checksum正确；随后仅删除核对owner/ID的本轮两容器及网络，均exit0；**owned容器剩余0**。
- 原 `agent-guard-a2-pg`、`verivote-web/api` 的ID、镜像、标签、挂载、端口、Running/StartedAt前后一致；未连接其数据库或触发共享down/prune。
- 受审根、完整95项执行副本及契约开始/结束一致；证据/缓存副本保留，不清历史证据。最终证据为 `cleanup.json`、`unrelated-end.json`、`database-end.log`及 `binding-end.json`。

## 10. 交主控动作

**保留本轮NOT_ACCEPTED及全部证据，不设置阶段ACCEPTED。** 将上述稳定issue和新SNAPSHOT问题交回当前A2.1实施者补正；不得以正式184项全绿、包审READY或手动隔离helper通过关闭入口缺陷。
补正后重新冻结代码/契约，以fresh reviewer复验全部历史trigger、绕过变体、受影响不变量及整段必跑矩阵；重点保留确定性锁交错、旧库直接入口、同键拒绝/迟到效果、完整权限链及已提交事件封存。
本轮不进入下一大阶段；真实B验权、HTTP及签名回执继续按后续独立人审批门槛处理。
