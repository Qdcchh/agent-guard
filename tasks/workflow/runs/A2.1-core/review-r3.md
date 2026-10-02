# 独立审查：IMPLEMENTATION_ACCEPTANCE／A2.1-core／r3

## 1. 结论与范围

- **结论：NOT_ACCEPTED。** 正式套件全绿，但本轮独立反例证明补正尚未闭合。
- 日期／时区：2026-10-01，Asia/Shanghai；结束冻结核验时间 **17:01:36+08:00**。
- 原10项代码 issue：**5项可关闭，5项仍有残余缺陷**；另确认2项新缺陷。DOC项部分修正，仍未关闭。
- 31项需求逐项检查：**18 PASS、13 FAIL**；28项运行类义务均有本轮实际执行，没有以历史日志替代必跑验证。
- 仅审 **A2.1-core／检查点二**。完整A2与项目仍为 **PARTIAL**。
- **不允许进入A2.2/A2.3/A3**；不授权commit、push、PR、合并或发布。
- 未修改受审源码、正式测试、标准、state、issues或报告；仅写本轮自有探针、代码副本、日志/XML及证据索引。

## 2. 独立会话、授权与冻结版本

| 项目 | 独立核对结果 |
| --- | --- |
| Reviewer | NEW r3；实际模型 **`openai/gpt-6.1-sol`**；接口及环境未暴露真实session/Task ID或实际推理档位，由主控关联真实调用记录，不编造 |
| 仓库 | `/Users/qdcc/code/密码技术竞赛/agent-guard`；下文源文件相对路径均以此为根 |
| 真人授权 | 父任务提供且与正式包/state一致：`ses_f0ac0e676ffecn71p6Ww7zaqQq`／`msg_0f54148e0001ZW7yCMdK0TE97F`，仅A2.1；本轮未自行授予权限 |
| Writer冻结 | 父任务明确MiMo `ses_f0aa292caffeODmd0G8jUSZ1Y9` 已停写；state记录STOPPED_READY_FOR_REVIEW；开始/结束内容与Git一致。未将哈希一致夸大为独立调度器“无writer”证明 |
| 分支／HEAD | `feat/a2-execution-gateway`／`b120c7cf5ec0eafb18305d1207c36dd11655b324` |
| 开始／结束snapshot | **`3814a5869984e334d12aa768a7aefbbc88a98f617ed519064af4b918fb471aba`**，97项完整manifest重新生成且一致 |
| 开始／结束contract摘要 | **`c17869452226d18ea8e72870f588452b19dc1f03c81002a056bf83fef9a6c8d1`**，各文件重新散列及排序规范JSON摘要一致 |
| task-v1／correction-r1 | SHA256分别为 `67896f80e7b80fe05087f88ef08576c805117bfdd12654addff03efadf2bfec4`／`c6c27944f4d3750df18eff9505c884d9f6b74133c6b1ce350b3c906684d7f394` |
| issues／worker报告 | SHA256分别为 `7fc328d0201dac9b23de34e3f21c4bc56e502ab75077d60361b9bf31f5d05474`／`70aebc00d0655093ee62730e2a1f482f4dcc624cf3c6bee3b4cc9a3034c66e68`，开始/结束不变 |
| Git范围 | 4个tracked修改；staged为空，无删除/重命名；完整untracked源、迁移、测试及关联文件已纳入审查 |
| 执行副本／排除范围 | 原仓库只读挂载；正式测试在自有97文件精确副本执行。沿冻结规则排除artifacts/生成缓存/控制运行记录；正式包另列contract；未借排除规则改受审文件 |

## 3. 实际检查与证据入口

已全文读正式task-v1、correction-r1、完整review-r2、issues及workflow要求；原A2任务、两轮检查点、A1任务/各轮验收、AGENT、README和三份原设计/安全/验收文档。
已检查完整tracked diff、全部execution/tools/contracts新增实现、001—005、A1 ledger全部调用模块、所有unit/integration测试及fixtures、CI、依赖和Compose。
重点追踪 `accept_invocation→policy/catalog→A1 accept`、`run/reconcile→材料验证→claim→独立下游→decide/finalize`，检查锁序、隔离持久性、租约时效、失败路径及数据库防绕过。

证据根 **E**：[artifacts/workflow/A2.1-core-review-r3-936bc079/](/Users/qdcc/code/密码技术竞赛/agent-guard/artifacts/workflow/A2.1-core-review-r3-936bc079/)。
完整 [evidence-index.json](/Users/qdcc/code/密码技术竞赛/agent-guard/artifacts/workflow/A2.1-core-review-r3-936bc079/evidence-index.json) SHA256：**`0450e61e3659a36067536c250fe5f4d0d81e9b0edd9e7abaa65f49ff08331e57`**。
索引含31项status/reason/evidence path/SHA256/kind/exit、117个证据文件条目、命令与JUnit计数；已读回并核验引用哈希。
别名：**S**冻结/Git；**Q**质量；**ENV**安装环境；**U/G**最终全unit/PG；**A1/A2**分套；**P**继承探针本轮复跑；**N**新r3反例及最终全探针；**O**观察JSONL/行号索引；**M**迁移；**H**原A1探针；**SMOKE**README；**RES/I**资源/静态检查。
以下行为证据均为**本轮独立实跑**；`I`为本轮静态查证，历史报告/旧日志不支持当前行为PASS。

## 4. 完整需求矩阵

31个ID及28个runtime ID与state完全一致。测试简称：`C/REC/QT/CON/VAL/DS/MIG/REG`对应 `test_execution_core/recovery/quotes/concurrency/validation.py`、`test_downstream.py`、`test_a2_migrations.py`、`test_execution_regressions.py`。

| 需求ID／来源 | 当前必需 | 实现／正式测试与独立探针 | 观察断言、本轮结果及证据 | 状态 |
| --- | --- | --- | --- | --- |
| A2-P01／A2§7 | 是 | `_finalize`；C::test_p01* | 唯一70000分订单；三层预留归零、结算70000/1；事件/outbox一致；G/A2 | PASS |
| A2-P02／A2§5/7 | 是 | `_decide`；C::test_p02*；r3 result-binding | 正常持久拒绝阻止迟到成功；但错误工具的“refusal”结果可在已有订单时释放；G/P/N | **FAIL：OUTCOME** |
| A2-P03／A2§4/7 | 是 | 零额工具；C::test_p03*、r2_positive、通知并发探针 | 合法读结果固定、通知成功/拒绝calls正确，10轮通知唯一效果；结果错配另归P12；G/P | PASS |
| A2-P04／A2§7/8 | 是 | worker；REC::test_p04*、entry_windows、真实kill探针 | 未提交操作对真实worker不可见；SIGKILL后新PID从持久状态恢复；G/P/O | PASS |
| A2-P05／A2§5/7 | 是 | run/recovery；C::test_p05* | 真下游提交＋响应丢失替身→UNKNOWN保70000/1，同单一次结算；G/A2 | PASS |
| A2-P06／A2§7 | 是 | worker终局窗口；REC::test_p04_p06*、followups | 真kill时1订单/0outbox；重启后仍1订单、1终局、1outbox；G/P/O | PASS |
| A2-P07／A2§5/7 | 是 | terminal事务；C::test_p07*、partial_terminal_rollback | 真实部分节点/事件/outbox写后异常全回滚，保原预算，随后恢复；G/P | PASS |
| A2-P08／A2§5/7 | 是 | reconcile/downstream；C::test_p08*、deadline | 查无结果不释放、迟到同键成功；真SQL锁自动约5秒超时，无人工cancel，保预算；G/P/O | PASS |
| A2-P09／A2§7 | 是 | claim/finalize；REC::test_p09*、锁交错、stale_unknown | 正确锁交错10轮及终局fence通过；旧UNKNOWN返回过时状态；正式锁测试可无终局进展而绿；G/P/N | **FAIL：UNKNOWN、TESTSYNC** |
| A2-P10／A2§5/7 | 是，真查询后段 | 内部恢复/A1动态复核；REC::test_p10* | 撤销/过期/key停用后原操作可恢复；外部重试拒绝；G/A2 | PASS |
| A2-P11／A2§4/7 | 是 | candidate；QT::test_p11*、r3 params_quote | 原快照重试/竞态通过；params quote身份与成本/快照不同仍可命中或执行；G/P/N | **FAIL：CANDIDATE** |
| A2-P12／A2§5/7 | 是 | `_decide`；C::test_p12*、完整result各工具反例 | 原错键/基本类型已拒；effect/result ID及字段、重复未知JSON、typed quote bool仍可误终局；G/P/N | **FAIL：OUTCOME** |
| A2-P13／A2§7 | 是 | 全祖先预算/混合锁；CON::test_p13*、独立锁探针 | 根/中间/次数/接受结算恢复各10轮；全祖先有界非负；独立固定交错10轮精确终局，无死锁；G/P | PASS |
| A2-P14／A2§4/7 | 是 | MockDownstream；DS::test_p14*、通知双执行 | 独立库唯一效果、冲突不覆盖；执行/查询无错服务凭据拒绝；订单/通知10轮；G/P | PASS |
| A2-P15-CORE／阶段范围 | 是，仅可信对象 | params/policy；VAL、unit、chain/notify探针 | 四工具严格参数/资源拒绝；目标存在及同tenant/task/grant/holder；完整DB链；拒绝零新增状态；U/G/P/N | PASS |
| A2-P19／A2§7 | 是 | migrations/material checks；MIG、升级/旧行探针 | 001/003/004合法非法升级七表/完整登记保全；原8类隔离通过；深层快照及params错配仍漏隔离；G/P/N/M | **FAIL：LEGACY、SNAPSHOT、CANDIDATE** |
| A2-P20／A2§5/7 | 是 | 004/005 guards；MIG、SQL append探针 | 改删/新节点shape/缺节点提交拒绝；升级前已commit短RESERVE/SETTLE仍能补INSERT改历史；G/P/N | **FAIL：EVENT** |
| A2-CKPT1-OBL01／ckpt1-r2§13.1 | 是 | static→candidate→A1；QT::test_obl01* | 不依赖当前报价、动态验权/proof intact；候选params→成本身份关联仍不完整；G/P/N | **FAIL：CANDIDATE** |
| A2-CKPT1-OBL02／§13.2 | 是 | miss安全重查；QT::test_obl02*、60轮变体 | 真miss→另一accept提交→报价/申请消失→重查；新键/撤销/重放/改意图拒绝；G/P/O | PASS |
| A2-CKPT1-OBL03／§13.3 | 是 | 接受事实、sidecar、防删链 | 永久操作/path保护成立；深层/错身份接受材料仍未自动隔离；G/P/N | **FAIL：LEGACY、CANDIDATE、SNAPSHOT** |
| A2-CKPT1-OBL04／§13.4 | 是 | lease四条件；REC及fresh lease/stale_unknown | 错owner/version、锁后expiry拒绝；但UNKNOWN早返回不查当前lease/state，10/10报过时状态；未改DB终态；G/P/N | **FAIL：UNKNOWN** |
| A2-CKPT1-OBL05／§13.5 | 是 | sidecar/phase-seq/005 seal | 七表保全、合法UPDATE及改删保护通过；旧commit短集合INSERT仍未封存；G/P/N/M | **FAIL：EVENT** |
| A2-CKPT1-OBL06／§13.6 | 是 | snapshots/outcome/receipts | 稳定ID/created_at/UTC iat/PENDING通过；result材料绑定、旧事件封存及深度/身份schema不足；G/P/N | **FAIL：OUTCOME、EVENT、SNAPSHOT** |
| WF-A1-REGRESSION／A1与契约 | 是 | A1全部正式测试、原4＋1探针、动态升级 | 独立68 unit＋78 PG；U1/P1—14/F1—5保持；原探针5通过，过时002断言留证据、6组合等价增强升级通过；A1/H/P/M | PASS |
| WF-INDEPENDENT-PROBES／契约§3/6 | 是 | 151继承/适配＋65新r3 case | 最终216个不同case：156通过、60失败，源码/观察/XML保存；执行义务完成不抵消缺陷；P/N/O | PASS |
| WF-QUALITY-CHECKS／AGENT/A2§8 | 是 | ruff/diff/全正式套件/CI；test-efficacy | 质量命令、137 unit、282 PG全执行无skip；但正式锁回归吞异常、零终局仍通过；Q/U/G/N | **FAIL：TESTSYNC** |
| WF-PY311-ENV／A2§8 | 是 | 新Python容器、约束安装、真实PG | CPython3.11.16新安装/pip check，psycopg3.2.13，PG16.15；未加依赖；ENV/U/G | PASS |
| WF-RESOURCE-ISOLATION／契约§5 | 是 | 新owner资源、独立DB/schema | 原仓库RO、自有E RW；普通DSN清除；仅自建资源清理；无关3容器inventory相同；RES/M | PASS |
| WF-IMMUTABLE-BASELINE／原任务 | 是 | HEAD字节比对/A1回归/004 hash | 001—003、A1 ledger/contracts/依赖与HEAD一致；004原hash保留；005获同阶段授权；I/S/A1 | PASS |
| WF-DOCS-REPORT／A2§8、DOC | 是 | README/A2-report/implementation-r2 | tracked4已纠正、README原文烟测成功；当前报告仍有环境/阶段/迁移/计数矛盾与无效锁验证声明；I/SMOKE/N | **FAIL：DOC、TESTSYNC** |
| WF-SNAPSHOT-COVERAGE／契约§2 | 是 | 完整manifest/contract/Git/执行副本 | 全97项及另列contract开始/结束一致，state/issues/report/Git无漂移；S/I | PASS |

后续边界：完整P15真实授权、P16 token/proof签验、P17 result-read、P18真实SM2签名/验签、P21 HTTPS联合闭环均 **后续阶段／B依赖BLOCKED，未计PASS**。
P18本阶段稳定待签材料和业务恢复已实跑，未将整个P18移出。

## 5. 专项与历史回归

| 专项 | 本轮实际结果 |
| --- | --- |
| C1 | A1/A2 Compose渲染project分别agent-guard/agent-guard-a2；reviewer另用owner独占网络/容器，不复用它们 |
| C2/P11 | 合法候选、5种报价竞态模式各10轮＋申请消失10轮通过；错params quote身份变体仍失败 |
| C3/P19 | 001/003/004×合法/非法6组合：真实70000/1、撤销、七表全行、完整迁移登记及重复no-op通过；入口残余缺口保留 |
| C4/P20 | 完整新事件的shape/commit保护通过；旧短集合可在005后分两事务由1补成3，SETTLE outbox仍旧材料 |
| C5 | 新鲜错owner/version、无接管过期、锁等待后过期及旧新终局竞争通过；UNKNOWN过时返回另有确认缺陷 |
| C6 | 同总额双行重分配保持UNKNOWN；稳定UTC iat/PENDING通过；result/effect关联及严格存储边界未闭合 |
| 真进程恢复 | 独立探针记录PID **434→435、587→588、740→741**，旧进程exit **-9**、新进程exit **0**；正式套件及最终全探针也再次执行 |
| 并发 | A1 P3/P5/P6、A2 P09/P13/P14正式组各10轮；独立固定锁交错、旧新终局、通知、P11各10轮；新UNKNOWN反例10轮 |
| 原A1升级探针 | 原源码未改：硬编码`["002"]`，当前实际后缀含003/004/005，故exit1；当前动态6组合逐七表/完整登记比较等价且更强 |

## 6. 本轮独立命令、退出码与JUnit

环境：**Python3.11.16、PostgreSQL16.15、psycopg/psycopg-binary3.2.13、pytest8.3.5、ruff0.11.13、setuptools79.0.1**。
宿主命令cwd为受审根；正式测试cwd为自有 `/evidence/candidate`。参数、缓存/XML及真实pytest退出码保存在E命令JSON；驱动脚本exit0不替代子命令exit1。

| 实际命令／目标 | 退出码 | pass/fail/error/skip | E内原件／别名 |
| --- | --- | --- | --- |
| `pip install -e /evidence/candidate[dev] -c /evidence/candidate/constraints.txt`；`pip check` | 0／0 | 新约束安装及依赖检查通过 | install.log、pip-check.log／ENV |
| `ruff check --no-cache .`；`ruff format --check --no-cache .`；结束对只读/repo再检查 | 各0 | check通过；52文件格式通过 | quality-*.log／Q |
| `git diff --check`，开始/结束 | 0／0 | 无whitespace错误 | diff-check*.log／Q |
| `pytest tests/unit tests/test_scaffold.py tests/test_docs.py`，初次及最终 | 0／0 | **137/0/0/0**，两次均同 | unit.xml、final-unit.xml／U |
| `pytest tests/integration`，初次及最终 | 0／0 | **282/0/0/0**，两次均同 | integration.xml、final-integration.xml／G |
| 独立分跑A1 unit/骨架/docs；八个A1 PG文件 | 0／0 | **68/0/0/0；78/0/0/0** | a1-unit.xml、a1-pg.xml／A1 |
| 独立分跑八个A2 PG文件 | 0 | **204/0/0/0** | a2-pg.xml／A2 |
| `python -m agent_guard.ledger.migrate`两次 | 0／0 | 首次001—005，第二次no-op；结束登记checksum核对 | migrate-*.log、database-end.json／M |
| `pytest /evidence/probes`，继承/适配完成后的151 case | 0 | **151/0/0/0** | inherited-verified.xml／P |
| 新`test_r3_independent.py`；`test_r3_more.py` | 1／1 | **0/53/0/0；5/7/0/0** | fresh.xml、fresh-more.xml／N |
| 最终`pytest /evidence/probes`，全部216 case | 1 | **156/60/0/0** | final-probes.log/xml／N |
| 原`test_missing_invariants.py`；`test_root_rebuild.py` | 0／0 | **4/0/0/0；1/0/0/0** | 对应log/XML／H |
| 原`test_upgrade_nonzero.py` | 1 | **0/1/0/0**，上述过时版本断言 | 对应log/XML／H |
| README原文程序＋CLI-first＋独立DB后置断言 | 0 | SMOKE_OK；三层70000/1、唯一订单、2事件/6节点/1 PENDING outbox | readme-smoke.log、原文程序/driver／SMOKE |
| 资源核验、精确cleanup、结束冻结核验 | 0 | owned容器0，测试schema0，无关inventory一致 | RES/S |

重复分跑不累计为不同case数。正式套件为419个case全绿；独立最终探针为216个case、60个真实验收断言失败。
环境首次准备发生自有目录`FileExistsError`，核对owner/ID后续接；探针适配前两次为149/2及150/1，失败属于reviewer deadline记录/004非法setup适配，不作应用缺陷；均保留原日志/XML与说明。

## 7. 历史材料与未执行边界

- r2报告、观察与源码仅为历史索引；借用探针源码后在本轮新数据库实际重跑，没有复制旧成功结果作为本轮证明。
- 最小适配仅在自有副本：004＋005迁移期待、保持原逆序触发能力的锁同步、自动timeout而非cancel、追加004升级组合；历史源码未改。
- 当前fixtures提供真实合法通知目标及完整chain_grant_ids；新增链反例同时提供对应截短/重排ID，拒绝不是缺新增字段的setup假阳性。
- 本轮真实执行PG事务回滚、锁等待自动超时、进程SIGKILL/新PID重启；响应丢失、错outcome、查无结果是明确的port替身。
- 远程CI **NOT_RUN，未授权触发**；真实断网、TLS/wheel部署、SM2/SM3和HTTP闭环未执行，不作通过声明；这些后段范围不另加为A2.1环境阻碍。

## 8. Issue逐项闭环与具体补正

下表简称`service/catalog/policy`为相应execution/tools源码；所有关闭仅绑定本轮冻结指纹。残余共享根因不重复计罪，但不能据部分修复关闭较宽的原issue。

| Issue／严重度／要求 | 修复事实、原trigger及绕过变体、本轮独立证据 | 当前状态／具体纠正 |
| --- | --- | --- |
| A21-R1-LOCK／高／P09,P13 | `service:442–480`非锁定位后task→grants→operation→lease。原反序交错适配保留旧实现触发能力；本轮10轮必须final-ok、精确三层结算/唯一效果/outbox；P/O | **CLOSED_REVIEWED**；正式测试自身缺陷另列TESTSYNC |
| A21-R1-LEGACY／高／P19,OBL03 | `service:316–350`自动验证＋独立事务隔离；原8类及run/reconcile/candidate/helper32正式组合、本轮旧探针拒绝且flag持久。深层快照及params错身份变体仍无flag；G/P/N | **OPEN残余**；按下述SNAPSHOT/CANDIDATE修复全入口，保预算/零下游，避免通用解析异常绕过持久隔离 |
| A21-R1-OUTCOME／高／P02,P12,OBL06 | 原错operation、缺effect、unbound/basic type触发已拒；但`service:549–581,761–783`仅普通json.loads取operation/kind。改order_id、供应商、总额/items、通知ID/目标、read tool、重复未知字段仍SETTLE；wrong-tool refusal可RELEASE且真实订单存在；G/P/N/O | **OPEN_CONFIRMED_RESIDUAL**；单次有界严格每工具result解析，精确类型/字段，effect_ref与result ID、意图/报价/amount全部绑定；错配UNKNOWN/no outbox；execute/query均回归 |
| A21-R1-NOTIFY／高／P15-CORE | `policy:355–393,446–460`可信DB目标存在、tenant/task/grant/holder查证。原absent/cross-tenant/other-grant及新增cross-task/wrong-holder拒绝；合法目标正例和10轮通知通过；G/P/N | **CLOSED_REVIEWED**；严格最小访问政策未扩大 |
| A21-R1-CHAIN／高／P15-CORE,OBL01 | `policy:207–248`完整chain_grant_ids与DB路径逐层绑定；原leaf-only/缺mid/超长，新增重排/错层/拼接均拒绝，根/中/叶正例保持；G/P/N | **CLOSED_REVIEWED**；不据可信fixture声称B验权完成 |
| A21-R1-LOG／中／安全日志、WF-DOCS | `service:99–107,485–499`和worker安全码替代原异常；原malformed DSN marker及含secret下游异常捕获无泄漏；G/P | **CLOSED_REVIEWED**；结论限已测诊断路径 |
| A21-R1-BOUNDS／中／P08,F5 | downstream连接SQL上限5s/10s，gateway读连接有界；原真ACCESS EXCLUSIVE触发自动约5.02秒结束，未cancel，UNKNOWN保70000/1、零效果；G/P/O | **CLOSED_REVIEWED**；正常执行/query及非法0/bool配置已回归 |
| A21-R1-EVENT／高／P20,OBL05/06 | 005挡完整事件第四节点及新事件缺/错节点；但`005:131–143,209–212`只对event INSERT延迟查完整性。旧已commit短RESERVE/SETTLE在升级后两次补INSERT成功，节点1→3，SETTLE outbox不变；N/O | **OPEN_CONFIRMED_RESIDUAL**；新增经主控确认的迁移封存旧事件及事务边界，禁止补历史；保旧行，不改已应用001—005；增加旧短集合/outbox升级负例 |
| A21-R1-CANDIDATE／高／P11,OBL03 | 原snapshot→cost身份错配已隔离；`service:820–837`漏params.quote_id/version比较。成本/snapshot均quote-001@1、params另ID/版本时run可下单结算，candidate/fallback可EXISTING且无flag；N/O | **OPEN_CONFIRMED_RESIDUAL**；params↔成本列↔完整snapshot三方身份一致，所有入口自动持久隔离，拒绝时proof/预算不新增 |
| A21-R2-SNAPSHOT／中／P19,OBL06 | 原bool/float/string/重复未知/负乘积拒绝已通过；`catalog:122–127,173–183,259–265`仍仅非空ID，接受0/01/文本版本及控制/URL/超长身份；深度1500抛RecursionError，run/reconcile/candidate均无flag；N/O | **OPEN_CONFIRMED_RESIDUAL**；合法ID/version、有界深度/大小、统一解析异常映射LEGACY_SNAPSHOT_INVALID并持久隔离；result解析深度异常也应安全UNKNOWN |
| DOC-CKPT1-01／低／WF-DOCS | tracked4清单修正且原文烟测成功；`A2-report:10,21,34,126`仍称3.11未跑/主体未开工/004未实现/182；README261与CLI-first实际`[]`输出不符；I/SMOKE | **OPEN_NONBLOCKING、部分修复**；明确历史段落与当前事实，同步真实命令/计数/阶段，不覆盖历史报告 |
| A21-R3-UNKNOWN／中、阻断／P09,OBL04 | `service:676–681`缓存UNKNOWN直接返回。旧claim过期、新owner已SUCCEEDED后，旧查询无结果仍报UNKNOWN，10/10；DB仍SUCCEEDED、预算/事件未被覆盖；N/O | **OPEN_CONFIRMED_BLOCKING**；UNKNOWN no-op也核当前state/owner/version/expiry，返回失租错误或正确当前终态；补公开run/reconcile同步竞态 |
| A21-R3-TESTSYNC／中、阻断／WF-QUALITY,P09 | `REG:248–299`task和operation共用barrier；第二wait时已持task，另一线程无法到达，BrokenBarrierError被吞。独立调用正式函数仍“通过”，却10操作全部仅RESERVE、0outbox、已有10订单；N/O | **OPEN_CONFIRMED_BLOCKING**；修同步位置，禁止接受未预期线程异常；每轮必须真实终局进展并断言全部计数/事件/outbox/效果，不能仅“无DeadlockDetected” |

## 9. 资源、清理与结束核验

- 本轮owner：**`a2.1-core-review-r3-936bc079`**；PG容器 `381dfba707bc…`、Python容器 `e144931a6fb1…`；完整ID、镜像SHA、标签及挂载见RES/resources.json。
- PG仅tmpfs，无宿主卷或公开端口；Python原仓库RO、自有E RW；网关与随机下游库使用独立连接/事务域。
- 普通部署DSN/worker配置未继承；仅本轮TEST DSN；日志/XML连接信息及secret已脱敏，没有真实token/key。
- 清理前仅review_gw与系统库、测试schema **0**，001—005完整登记checksum正确；只按核对过的owner/完整ID删本轮两容器及空网络，均exit0，owned容器剩余 **0**。
- 原agent-guard-a2-pg、verivote-web/api的ID/镜像/标签/挂载/端口/Running/StartedAt前后一致；未连接其DB，不将容器核对夸大为业务数据摘要核验。
- 受审97文件、执行副本、contract、state、issues、worker报告和Git开始/结束一致；本轮探针/日志/XML/cache/index保留，历史证据未改删。

## 10. 交主控动作

**保存本完整r3报告及证据索引，维持NOT_ACCEPTED，不设置阶段ACCEPTED。**
按冻结版本关闭LOCK/NOTIFY/CHAIN/LOG/BOUNDS；保留LEGACY/OUTCOME/EVENT/CANDIDATE/SNAPSHOT和DOC残余，新增UNKNOWN/TESTSYNC，委派仅当前A2.1补正。
数据库修复使用经主控确认的新版本迁移，遵守已应用checksum不可变；修复后重新冻结并fresh reviewer复验原trigger、变体及完整阶段，不以282项全绿替代语义证据。
**不进入下一大阶段；真实B授权/密码、HTTP和签名回执继续保留后续依赖与真人审批门槛。**
