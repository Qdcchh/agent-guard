# A2.1-core 实施/补正报告 implementation-r4

- **状态：`READY_FOR_REVIEW`（不是 ACCEPTED）**。补正包 `correction-r3.md` 的 5 项残余、DOC 与 P11 证据缺口已逐条修复并自查完成，等待 **fresh implementation reviewer** 复验。完整 A2 仍为 **PARTIAL**。
- **对应补正包**：`tasks/workflow/runs/A2.1-core/correction-r3.md`，SHA-256 `cedb802105131f77ca7a0e67c6b55c689ae8df2ffde7971871d97dd9fdc6076b`。
- **包审**：`package-review-r2.md`（NEW `ses_f0892f2bfffezCvUsClN3kmSPQ`，`PACKAGE_READY`）——**只确认补正设计可实施，不是代码 ACCEPTED**。
- **被纠正的审查**：`review-r5.md`（NEW `ses_f08c896cbffeptdE23OBohV4bm`，`NOT_ACCEPTED`，snapshot `d7ea969a34b63782d06506d7f6ff9f221c6fbdc0590b2d2d9561e55554364c9c`）。
- **用户授权**：不变，session=`ses_f0ac0e676ffecn71p6Ww7zaqQq`、message=`msg_0f54148e0001ZW7yCMdK0TE97F`，仅 A2.1-core；不进入 A2.2/A2.3/A3，不 B/HTTP/真签名，不 Git 发布。
- **实施 session**：MiMo 2.6 Pro（`opencode-go/mimo-v2.6-pro`），单 writer，续 `ses_f0aa292caffeODmd0G8jUSZ1Y9`。
- **授权门**：`python3 tools/workflow_gate.py verify --root . --state tasks/workflow/state.json --require-authorized` → exit 0，`ok=true`、`status=CHANGES_REQUESTED`、`can_start=true`、`can_accept=false`。
- **Git**：分支 `feat/a2-execution-gateway`，HEAD `b120c7cf5ec0eafb18305d1207c36dd11655b324`（未提交）。**001—006 全部禁改、checksum 未变**；本轮**无新增迁移**。
- **本轮证据根**：`artifacts/workflow/A2.1-core-impl-correction-r3-20261001c3/`（下称 `$A`）。`implementation-r1/r2/r3.md` 与历次 review 证据**均未覆写**。

---

## 1. 架构决定：`ledger/service.py` 最小 A1 接受兼容（主控确认范围）

**问题**：最后一次非锁 candidate lookup 与 A1 的 accept 决定之间存在并发窗口；再加任意次非锁 lookup **不能原子保证 existing 材料可用**（r5 `test_atomic_existing_accept_material_at_last_miss` 10/10 复现）。

**设计**（`src/agent_guard/ledger/service.py`，+64/−3，其他 ledger/contracts/001—006 只读）：

| 设计点 | 实际实现 |
| --- | --- |
| 原默认 API 不变 | `accept(verified, cost)` 签名/语义/动态验权/proof/预算/锁序**完全不变**，内部转调 `_accept_with(..., existing_validator=None)` |
| 新增显式 per-call 入口 | `accept_checked(verified, cost, *, existing_validator)`；校验器**显式逐次传递**，**不存任何可变实例属性**，并发调用不同校验器零串扰 |
| 原子边界 | 校验器在**同一连接/同一锁/同一事务**内、`existing` 实际查到之后、`EXISTING` 返回/提交之前调用（`_accept_tx` 中 `_check_intent` 之后、`link_proof_to_operation` 之前） |
| 三条入口全覆盖 | A2 的 candidate hit／解析失败 fallback／解析成功路径**全部**改走 `accept_checked`；r3 的「最后再 lookup」已**删除**（不是原子修复） |
| 校验器能力边界 | 只读取当前连接上的 operation/path/events；**不 commit、不触下游、不开新连接**；无 HTTP/user 字段/环境开关，无 skipauth/直接 success |
| 失败语义 | 校验器抛 `LEGACY_SNAPSHOT_INVALID` → **原事务整体回滚（含本次新 proof 登记）** → A2 在**事务释放锁之后**用独立连接持久 sidecar 隔离（避免 FK 自锁）→ 原样重抛 |
| 不吞 DB 故障 | A2 只把 `LEGACY_SNAPSHOT_INVALID` 转成持久隔离；**psycopg/其它异常原样传播**，不伪造成数据库成功 |
| 调用链 | `A2 accept_invocation → _accept_checked → ledger.accept_checked → _accept_tx → (existing_validator) → verify_accept_facts`；`_accept_tx` 的 path/锁/新鲜性/proof/意图/预算步骤与顺序原样保留 |

**正式验证**：好/坏材料各 **10 轮**（`test_atomic_existing_material_in_the_accept_transaction`），坏→`LEGACY_SNAPSHOT_INVALID`＋sidecar 持久＋`ag_proofs` 不增（原事务回滚）＋预算不变＋零下游；好→同操作正确 `EXISTING`。另测同实例并发不同校验器零串扰、校验异常回滚后重试重新校验、独立 flag 失败关闭、A1 默认调用全回归。

---

## 2. 逐 issue 修复对照

| Issue | 根因（review-r5 §8） | 实际修复 | 新增正式回归 |
| --- | --- | --- | --- |
| **A21-R1-CANDIDATE**（高） | 最后 miss 后另一连接提交同意图坏 quote，10/10 `EXISTING`／proofs 2／无 flag | §1 的原子 actual-existing 校验（`accept_checked`）；删除 r3 的额外 lookup | `test_execution_r4_regressions.py::test_atomic_existing_material_in_the_accept_transaction[好/坏 × 10 轮]`、`::test_a1_default_accept_is_unchanged`、`::test_validators_do_not_cross_talk_on_one_instance`、`::test_validator_failure_rolls_back_and_retry_rechecks` |
| **A21-R1-LEGACY**（高） | params 1500 层 `RecursionError` 在五个入口漏 flag | `tools/params.py` 增加 `_bounded_depth`（≤8）＋`json.loads` 捕获 `(ValueError, RecursionError, MemoryError)` → `INVALID_PARAMS`；`verify_accept_facts` 把**纯解析**段的可预期异常（含 `RecursionError/TypeError/AttributeError/KeyError/OverflowError`）统一映射 `LEGACY_SNAPSHOT_INVALID`，且该段**不含任何 DB 访问**（不可能吞真实 DB 故障） | `::test_deep_legacy_params_durably_isolated[run/reconcile/candidate/fallback/helper]`、`::test_deep_new_params_rejected_without_flagging_normal_ops` |
| **A21-R2-SNAPSHOT**（中） | `re.match`＋`$` 接受尾 LF；`0\n` 绕过正版本 | 全部标识/版本改 **`fullmatch`** 并显式拒绝控制字符（`catalog._strict_id/_strict_version`、`results._str_field/_version_field`、`params._require_resource_id`）；正版本为非 0、无前导零的十进制串 | `::test_snapshot_identifier_trailing_control_refused[quote_id/quote_version/supplier_id/sku]`、`::test_version_zero_and_control_variants_refused`、`::test_result_identifier_trailing_lf_refused`＋合法 round-trip 正例 |
| **A21-R1-OUTCOME**（高） | typed `items=None/dict` 抛 `TypeError/AttributeError` 卡 EXECUTING；effect 尾 LF 误终局 | `strict_snapshots_equal` 改为**总定义**：`_quote_items_shape_ok`/`_quote_item_shape_ok` **先做 type/shape 检查再遍历属性**；未知容器/条目/字段一律答「不等」→安全 UNKNOWN（保 lease/fencing/无 outbox）；**合法 list 结构照常允许**；effect/result 标识 fullmatch＋控制字符 | `::test_outcome_typed_shape_boundaries_keep_unknown[items-none/item-dict/None-container/bad-entry]`、`::test_outcome_effect_identifier_trailing_lf_keeps_unknown`、`::test_structurally_identical_list_quote_still_settles` |
| **A21-R3-TESTSYNC**（中） | 反序效力测试首锁前 barrier 不保证持锁环；任意 `ILLEGAL_TRANSITION` 也 PASS | 新增**真锁环锚点** `_hold_and_deadlock`：两个真实连接分别持有 operation 行与 task 行，再互换；断言精确 `DeadlockDetected` 且 `pg_stat_activity` 观察到双方 `wait_event_type='Lock'`。反序服务路径测试**只接受 `DeadlockDetected`**；串行化自检断言**必须失败**（不能被普通终局拒绝蒙混） | `::test_reverse_lock_order_produces_a_real_server_deadlock`、`::test_lock_regression_reverse_efficacy_requires_a_real_deadlock`、`::test_lock_regression_efficacy_fails_when_the_race_is_serialized`＋原 10 轮正序完整终局 |
| **A21-R5-P11-EVIDENCE** | 一次未知 `LedgerError` 无 code，10 轮诊断未复现 | 新增 10 轮确定性资源消失竞态，**持久记录**精确 `code`/`detail`/cause 链/barrier 时序/DB 时钟/proof 登记/状态/计数/效果到 `$A/logs/p11-resource-disappearance-diagnostics.json`；失败不 catch 成 PASS；负例记录精确 `RESOURCE_NOT_FOUND` | `::test_p11_resource_disappearance_is_deterministic_with_precise_diagnostics`（10 轮）、`::test_p11_new_key_after_resource_disappearance_is_a_precise_refusal` |
| **DOC-CKPT1-01** | 当前/历史、ckpt1 门槛、006/results 清单、355 证据路径、types doc「004 未实现」 | `contracts/execution.py` 状态机 docstring 改为「004 已强制、005/006 封存」并注明是契约类型而非功能承诺；A2-report 顶层只当下事实、历史段显式标注、真实文件/JUnit 路径与 359 计数；README 双变体保持并实跑 | `$A/logs/readme-smoke.txt`／`readme-snippet.py` |

### 2.1 已关闭项不退化

r3/r5 已独立关闭的 **LOCK／NOTIFY／CHAIN／LOG／BOUNDS／EVENT／UNKNOWN** 全部保留实现与回归；359 项全绿包含其保护；通知最小同 grant/holder 策略**未扩大**；`test_execution_regressions.py`／`test_execution_r3_regressions.py` 原有断言**未删除、未放宽**。

---

## 3. 自查矩阵（31 项冻结 ID）

`$A` = `artifacts/workflow/A2.1-core-impl-correction-r3-20261001c3/`。

### 3.1 运行类（前 28 项）

| 必需 ID | 实现/测试 | 命令/退出码 | pass/fail/error/skip | 关键断言／证据 | 剩余缺口 |
| --- | --- | --- | --- | --- | --- |
| **A2-P01** | `_finalize`；`test_execution_core.py::test_p01*` | `pytest tests/integration`（3.11）exit 0 | 1/0/0/0 | 唯一 70000/1 订单；三层 reserved=0 settled=70000/1；RESERVE+SETTLE；outbox 一致 | 无 |
| **A2-P02** | `tools/results.py`＋`_decide`；`::test_p02*`、`::test_wrong_tool_refusal_never_releases_an_operation_with_an_effect` | 同上 | 2/0/0/0 | 同键持久拒绝才 RELEASE、阻止迟到成功；wrong-tool refusal 有真实订单也不 RELEASE | 无 |
| **A2-P03** | `::test_p03_*`＋正例 | 同上 | 4/0/0/0 | 0 金额计 1 次；成功结算/失败释放；通知恒 1 条；读结果固定 | 无 |
| **A2-P04** | `execution/worker.py`；`test_execution_recovery.py::test_p04_*` | 同上 | 4/0/0/0 | 提交前零效果；真 `SIGKILL`＋新 PID 持久恢复 | 无 |
| **A2-P05** | `::test_p05_*` | 同上 | 1/0/0/0 | 响应丢失→UNKNOWN 保 70000/1；恢复同单一结算 | 无 |
| **A2-P06** | `::test_p06_*`＋P04 真进程 | 同上 | 2/0/0/0 | 无二次效果/结算/终局/outbox | 无 |
| **A2-P07** | `::test_p07_*`＋`test_execution_r4_regressions.py::test_validator_failure_rolls_back_and_retry_rechecks` | 同上 | 5/0/0/0 | 终局四阶段＋**checked 失败 proof 回滚**全回滚后可恢复 | 无 |
| **A2-P08** | `::test_p08_*`＋`::test_real_lock_wait_times_out_without_manual_cancel` | 同上 | 2/0/0/0 | 查无结果不 RELEASE；迟到唯一成功；真实表锁自动超时（自有下游库） | 无 |
| **A2-P09** | `test_execution_recovery.py::test_p09_*`＋**真锁环锚点**＋正序 10 轮 | 同上 | 4/0/0/0 | 10 轮完整终局；真 `DeadlockDetected`＋waitgraph；串行化必须失败 | 无 |
| **A2-P10** | `::test_p10_*` | 同上 | 4/0/0/0 | 撤销/过期/停 key 后内部恢复；外部重试拒绝 | 真实 result-read 留后段 |
| **A2-P11** | `test_execution_quotes.py::test_p11_*`＋`test_execution_r4_regressions.py::test_atomic_existing_material_in_the_accept_transaction`（好/坏 × 10 轮）＋P11 诊断 10 轮 | 同上 | 25/0/0/0 | 最后 miss 后坏材料拒/proof 不留/flag 持久/预算不变；好材料正确 EXISTING；诊断精确 code/cause/时序 | 无 |
| **A2-P12** | `::test_p12_*`＋`test_execution_regressions.py::test_mis_bound_*`＋`test_execution_r3_regressions.py::test_order_result_*`＋`::test_other_tool_results_*`＋`test_execution_r4_regressions.py::test_outcome_*`／`::test_structurally_identical_list_quote_still_settles` | 同上 | 55/0/0/0 | 金额/意图/供应商/单价/错键/坏 result/缺 effect/字符串拒绝/bool 金额/effect-id/缺字段/重复未知/typed bool quote/deep result/items None/dict/尾 LF **全 UNKNOWN**、零 outbox、预算保留；**合法 list 正例 SETTLE** | 无 |
| **A2-P13** | `test_execution_concurrency.py::test_p13_*` | 同上 | 4/0/0/0 | 各组 10 轮、独立连接＋barrier；逐祖先有界非负 | 无 |
| **A2-P14** | `test_downstream.py::test_p14_*` | 同上 | 14/0/0/0 | 唯一效果、冲突不覆盖、凭据拒绝零泄漏 | 无 |
| **A2-P15-CORE** | `tests/unit/test_tool_validation.py`（61）＋`test_execution_validation.py`（17）＋chain/notify/边界组 | 同上 | 61+31+12=104/0/0/0 | 四完整 ID/版本、重复键/SKU、bool/负/浮点/溢出、缺/空集合、scope、跨租户、关联错、URL 注入、快照绑定、祖先包含、通知目标——零预留零效果 | 可信夹具≠真实验签；完整 P15 留 A2.2 |
| **A2-P19** | `test_a2_migrations.py::test_p19_*`＋legacy 组＋`test_execution_r4_regressions.py::test_deep_legacy_params_durably_isolated[5 入口]` | 同上 | 41/0/0/0 | 001/003/004/005→006 非零升级七表逐行不变；非法升级数据+登记不变；重复迁移 no-op；8 类＋深度 params 五入口自动隔离、预算保留 | 无 |
| **A2-P20** | `test_a2_migrations.py::test_p20_*`＋node/seal 组 | 同上 | 18/0/0/0 | 改意图/成本/证据、删操作/路径、改删事件/节点、phase/seq、双终局、非法状态全拒；旧 commit 短集合补不进；seal 不可伪造；合法初写成功 | 无 |
| **A2-CKPT1-OBL01** | `test_execution_quotes.py::test_obl01_*`＋chain/params-quote/原子 existing | 同上 | — | 候选查找前不需要当前报价；**实际 EXISTING 原子材料校验**且不绕动态验权/proof/意图 | 无 |
| **A2-CKPT1-OBL02** | `test_execution_quotes.py::test_obl02_*`＋**P11 精确诊断** | 同上 | 4/0/0/0 | 确定性资源/报价消失 10+ 轮；精确 code/cause/时序/DB 时钟/proof 状态 | 历史未知 `LedgerError` **不作 TTL 解释**，见 §5.3 |
| **A2-CKPT1-OBL03** | legacy／candidate／P20／原子 existing 组 | 同上 | — | 不完整 actual-existing 拒绝、不留新 proof、锁释放后 flag、预算保留 | 无 |
| **A2-CKPT1-OBL04** | `test_execution_recovery.py::test_obl04_*`＋UNKNOWN 组 | 同上 | — | owner/version/state/锁后 expiry；UNKNOWN no-op 现场复核 | 无 |
| **A2-CKPT1-OBL05** | `test_a2_migrations.py::test_obl05_*`＋EVENT 组 | 同上 | — | 七旧表不改行；事件完整封存；合法更新/owned 清理兼容 | 无 |
| **A2-CKPT1-OBL06** | `test_execution_core.py::test_obl06_*`＋SNAPSHOT/OUTCOME 组 | 同上 | — | fullmatch/总定义比较；完整原报价、稳定 UTC iat、不可变 PENDING | 真实 SM3 留 A2.3 |
| **WF-A1-REGRESSION** | A1 全部正式测试 | 同上 | A1 78 项 0 fail/error/skip | U1／P1—14／F1—F5 见 §5.1；**默认 `accept(verified,cost)` 行为未变** | 无 |
| **WF-INDEPENDENT-PROBES** | reviewer 职责 | — | worker 不可代做 | 本轮新增 r4 回归，但**不替 reviewer 选定唯一反例** | **须 fresh reviewer 补做** |
| **WF-QUALITY-CHECKS** | ruff/format/diff/全量 | ruff exit 0、format exit 0（54 files）、`git diff --check` exit 0 | 0 fail/error/skip | `$A/logs/checks.txt`；缺库 `pytest.fail` 不 skip；**串行/未持目标锁的探针必须失败** | 无 |
| **WF-PY311-ENV** | 真实 CPython 3.11.16 | `pip install -e '.[dev]' -c constraints.txt`＋`pip check` exit 0；unit 137／integration 424 全绿 | 与 host 一致 | `$A/logs/py311-verify.log`、`$A/junit/py311-*.xml` | 远程 CI NOT_RUN |
| **WF-RESOURCE-ISOLATION** | 自建独占实例 | `docker run --name agent-guard-a21e-pg --label owner=agent-guard-a21e-20261001c3 … --tmpfs` | — | 归属 label／`Mounts=[]`／127.0.0.1:55437；下游随机名独立库；普通 DSN 未设置 | 未复用既有/审查者资源 |

### 3.2 静态类（末 3 项）

| 必需 ID | 查证 | 结论 | 证据 | 缺口 |
| --- | --- | --- | --- | --- |
| **WF-IMMUTABLE-BASELINE** | 001—006 SHA-256 逐一比对；`ledger/` diff **仅 `service.py` +64/−3**；`contracts/ledger.py` 与 001—006 零改动；无 B 代码/依赖 | **001 `d5e7bb01…`、002 `bae1d72e…`、003 `1d919f8f…`、004 `41527dc2…`、005 `29529103…`、006 `3abb279b…` 全部不变**；本轮无新增迁移 | `$A/logs/checks.txt`、`git diff --stat src/agent_guard/ledger/` | 无 |
| **WF-DOCS-REPORT** | types doc 已改（004 已强制/005-006 封存）；A2-report 当下/历史分离、真实 424 计数与 `$A` 路径；README 双变体实跑 | DOC 修复（待 reviewer 复核） | `README.md`、`tasks/A2-report.md`、`src/agent_guard/contracts/execution.py` | 无 |
| **WF-SNAPSHOT-COVERAGE** | §4 清单；全部新文件落盘；`git diff --check` 干净 | 候选版本已冻结待审 | §4 | 最终冻结属主控/reviewer |

---

## 4. 实际变更清单

### 4.1 主控确认的唯一 ledger 兼容范围

`src/agent_guard/ledger/service.py`：**+64 / −3**（新增 `ExistingMaterialValidator` 类型、`accept_checked`、`_accept_with` 共享流程、`_accept_tx` 中的 per-call 校验调用）。`contracts/ledger.py`、`ledger/` 其他模块、`migrations/001—006` **零修改**。

### 4.2 业务/测试/docs 修改

```
src/agent_guard/execution/service.py   ← accept_checked 接线（删除 r3 额外 lookup）、
                                          strict_snapshots_equal 总定义形状、verify_accept_facts 异常规范化
src/agent_guard/tools/params.py        ← 有界深度＋RecursionError 映射、fullmatch
src/agent_guard/tools/catalog.py       ← fullmatch＋控制字符拒绝（ID/version）
src/agent_guard/tools/results.py       ← fullmatch＋控制字符＋精确版本
src/agent_guard/contracts/execution.py ← 状态机 docstring 更新（004/005/006 已落地）
tests/integration/test_execution_r4_regressions.py  ← 本轮新增 65 项（原子 existing／A1 默认 API 兼容／校验器边界／深度 params 五入口／标识版本 fullmatch／typed 形状总定义）
tests/integration/test_execution_regressions.py     ← 真锁环锚点＋效力自检、锁等待自有下游库
tests/integration/test_execution_r3_regressions.py  ← P11 精确诊断（10 轮持久记录）
tasks/A2-report.md / README.md                      ← DOC 修正
tasks/workflow/runs/A2.1-core/implementation-r4.md   ← 本报告
```

### 4.3 既有文件（保留不覆写）

`compose.a2.test.yaml`、`contracts/execution.py`（加法）、`tests/unit/test_execution_contracts.py`、`tasks/A2-*`、`tasks/workflow/**`（含 `implementation-r1/r2/r3.md`、`review-r2/r3/r5.md`、`correction-r1/r2/r3.md`、`package-review-r1/r2.md`）、`tools/workflow_gate.py`。**deleted／renamed：无。**

---

## 5. 环境、证据与限制

| 项 | 实际值 |
| --- | --- |
| Python 3.11 验证 | Docker `python:3.11-slim`，`Python 3.11.16`，`pip check` 通过；**不以本机 3.14 冒称** |
| PostgreSQL | 16（`postgres:16-alpine`），自建容器 `agent-guard-a21e-pg`（owner `agent-guard-a21e-20261001c3`），网关库＋独立下游库 |
| 依赖 | 无新增；`psycopg==3.2.13`／`pytest==8.3.5`／`ruff==0.11.13` |
| 故障层次 | 真实 `SIGKILL`／真实 PG 事务回滚／**真锁环 `DeadlockDetected`＋waitgraph**／真实表锁自动超时；端口响应丢失与查无结果为明确标注替身 |
| 并发 | 全部并发组各 10 轮，独立连接＋`Barrier`/`Event`；线程异常一律失败 |

### 证据索引（`$A`）

```
logs/py311-verify.log                            Python 3.11.16 完整矩阵（含 README 双变体）
logs/p11-resource-disappearance-diagnostics.json  P11 精确诊断（10 轮 code/cause/时序/DB 事实）
logs/checks.txt                                  迁移 checksum、001—006 未变、ruff/format/diff
logs/readme-smoke.txt / infra/readme-snippet.py  README 逐字程序
logs/docker-before.txt / resource-cleanup.txt    资源归属与仅 owned 清理
junit/py311-unit.xml (137) / py311-integration.xml (424)
infra/pg-up.sh / py311-verify.sh
```

### 5.1 A1 回归（WF-A1-REGRESSION）

U1 `test_input_validation`(46)+`test_rejects`(17)；P1/P2/P4/P7/P14 `test_accept_core`(13)；P3/P5/P6 `test_concurrency`(3，各 10 轮)；P8/P9/P10/P11 `test_state_checks`(11)；P12 `test_rollback`(4)；P13 `test_migrations`(8)；F1 `test_isolation`(7)；F2 `test_invariants`(15)；F3 subject 负例；F4 calls=1；F5 `test_service_config`(19)。**A1 78 项 0 fail/error/skip**，且 `accept(verified,cost)` 默认 API/语义未变。

### 5.2 仍处 BLOCKED／NOT_RUN

| 项目 | 状态 |
| --- | --- |
| 完整 P15 真授权、P16/P17 真签验与 result-read、P18 真 SM2 回执、P21 真实 HTTPS 闭环 | **BLOCKED**（A2.2/A2.3＋B 依赖） |
| 独立审计锚点、证据导出、规模压测 | 未实施（A3，未授权） |
| 远程 CI | **NOT_RUN**（未授权推送） |
| **WF-INDEPENDENT-PROBES** | **NOT_RUN（worker 不可代做）** |
| 通知跨 grant 访问扩大策略 | 严格最小政策（同 grant/holder）；如需扩大**先报主控** |

### 5.3 P11 历史不确定性（如实保留）

- 历史 `inherited.log` 中一次 `LedgerError` **没有记录 code**，r5 诊断 10 轮未复现。**本报告不声称该失败已由 TTL 解释**，也不删除原失败记录。
- 本轮建立的是：资源消失竞态 10/10 确定性命中 `EXISTING`、精确 `code`/`detail`/cause 链/barrier 时序/DB 时钟/proof 登记/状态已持久保存于 `$A/logs/p11-resource-disappearance-diagnostics.json`；负例精确 `RESOURCE_NOT_FOUND`。
- **尚缺**：那次历史失败的真实 code／cause 与触发窗口未知；恢复条件（若与 proof/token TTL 相关）仍需带 `DB now` 与 expiry 快照的受控复现才能判定。

---

## 6. 交付与停止

- 标 **`READY_FOR_REVIEW`** 并**停写**；所有 fix 状态为 **`FIXED_PENDING_REVIEW`**，**不得视为 CLOSED_REVIEWED**。
- 未标记 ACCEPTED、未改 `tasks/workflow/**` 控制文件/包/审查/issues、未 commit/push/PR/合并、未启动 A2.2/A2.3/A3、未引入或复制 B 代码/依赖、**未改动 001—006**、本轮无新增迁移。
- **开发者测试通过不是最终接受**；fresh implementation reviewer 须独立复验原子 actual-existing 校验、params/标识/typed 形状边界、真锁环效力、P11 诊断，以及完整 31 ID 矩阵与全部历史 trigger/绕过变体。
