# A2.1-core 实施/补正报告 implementation-r2

- **状态：`READY_FOR_REVIEW`（不是 ACCEPTED）**。补正包 `correction-r1.md` 的 10 条代码阻断项与 DOC 项已逐条修复并自查完成，等待 **fresh reviewer** 复验。完整 A2 仍为 **PARTIAL**。
- **对应补正包**：`tasks/workflow/runs/A2.1-core/correction-r1.md`，SHA-256 `c6c27944f4d3750df18eff9505c884d9f6b74133c6b1ce350b3c906684d7f394`。
- **被纠正的审查**：`tasks/workflow/runs/A2.1-core/review-r2.md`（NEW reviewer，`NOT_ACCEPTED`，snapshot `b2ad9065b9d24a3e71f6f3e27a42416326da2a8c9bd0cbfa3d6be9003c279288`）。
- **用户授权**：不变，session=`ses_f0ac0e676ffecn71p6Ww7zaqQq`、message=`msg_0f54148e0001ZW7yCMdK0TE97F`，仅 A2.1-core；不进入 A2.2/A2.3/A3。
- **实施 session**：MiMo 2.6 Pro（`opencode-go/mimo-v2.6-pro`），单 writer、无嵌套委派；本轮会话 `ses_f0aa292caffeODmd0G8jUSZ1Y9` 续接。
- **授权门**：`python3 tools/workflow_gate.py verify --root . --state tasks/workflow/state.json --require-authorized` → exit 0，`ok=true`、`status=CHANGES_REQUESTED`、`can_start=true`、`can_accept=false`。
- **Git**：分支 `feat/a2-execution-gateway`，HEAD `b120c7cf5ec0eafb18305d1207c36dd11655b324`（本轮未提交）。001—004 **未改动**（checksum 见 §2.4）；按主控授权新增 `migrations/005_event_node_seal.sql`。
- **本轮证据根**：`artifacts/workflow/A2.1-core-impl-correction-20261001c1/`（下称 `$A`）。r1 的 `implementation-r1.md` 与 review-r2 证据**均未覆写**。

---

## 1. 逐 issue 修复对照（10 条代码阻断＋DOC）

| Issue | 严重性 | 根因（review §8） | 实际修复位置与行为 | 新增正式回归 |
| --- | --- | --- | --- | --- |
| **A21-R1-LOCK** | 高 | `_claim` 先 `FOR UPDATE operation` 再 task/grants，终局相反；10/10 死锁 | `execution/service.py:_claim` 改为**非锁读**定位不可变字段 → `lock_task` → `load_path` → `lock_grants_root_to_leaf` → `lock_operation`（锁后复核 tenant/task/grant 未变）→ `claim_lease`；`_finalize`/`_mark_unknown` 同序。全局锁序统一为 `task → 根至叶 grants → operation → lease`，无反向获取 | `test_execution_regressions.py::test_claim_lock_acquisition_order_is_task_grants_operation_lease`、`::test_finalize_lock_acquisition_order_is_task_grants_operation_lease`、`::test_claim_and_finalize_interleaved_never_deadlock`（10 轮，barrier 强制双向交错，断言无 `DeadlockDetected` 且有界完成） |
| **A21-R1-LEGACY** | 高 | worker 只查已有 flag，未手动 helper 的旧行 8 变体直接执行/释放 | 新增 `execution/service.py:verify_accept_facts()`：完整校验严格参数、`tool_version`、币种、calls=1、金额边界、报价身份/版本、完整快照、首次证据、**全 RESERVE 路径与逐节点 delta**；`_ensure_accept_material()` 在 **run / reconcile / 候选 hit / 安全重查 fallback / claim 前**自动调用；任何缺口→`_quarantine()`（**独立连接独立事务**，抛异常也不回滚）+ `LEGACY_SNAPSHOT_INVALID`，预算保留、零下游调用 | `::test_legacy_material_is_auto_quarantined_at_every_entry[8 变体 × run/reconcile/candidate/helper]`（32 例，001—004 旧库→005 升级后逐入口）、`::test_quarantine_survives_the_callers_rollback` |
| **A21-R1-OUTCOME** | 高 | 未比较 `operation_id`，未验证结果/effect 语义与精确类型 | `execution/service.py:_decide` 严格绑定：`outcome.operation_id == operation.operation_id`、`tool_id` 为真 `ToolId`、`canonical_params` 为 bytes 且相等、`amount_fen` 为**非 bool int**、`final_rejection` 必须是**真 bool**、`result_bytes` 非空 bytes 且 JSON 中 `operation_id` 绑定本操作、`kind` 与工具一致（order/notification/read/refusal）、完整快照+币种+报价身份一致、per-tool effect 规则（订单/通知必须有 `effect_ref`，读取必须无）。**只有同键持久终局拒绝才 RELEASE**；任何不符→UNKNOWN、无 outbox | `::test_mis_bound_outcome_keeps_unknown_and_never_terminal[8 变体]`（other-key-success/refusal、missing-effect、malformed-result、unbound-result、string-refusal、bool-amount、wrong-kind）、`::test_same_key_refusal_only_releases_its_own_operation` |
| **A21-R1-NOTIFY** | 高 | 仅查 template/recipient，未查引用操作 | 新增 `tools/policy.py:check_operation_access()`：可信 DB 查询目标操作存在、**同 tenant/task**、且**原 grant/holder 可访问**（严格最小政策：只有拥有该操作的 grant+holder 可指向它；跨 grant 默认拒绝，扩大策略须先报主控）。`resolve_tool_resources(operation_facts=…)` 由 `execution/service.py:_operation_facts` 提供持久事实，**不信任 body 自报** | `::test_notification_target_access_is_verified[absent/cross-tenant/cross-task/other-grant]`（零新增 proof/预留/操作/通知）、`::test_notification_to_a_real_same_grant_target_is_allowed` |
| **A21-R1-CHAIN** | 高 | 只比较所提供相邻约束，未核完整 DB 路径 | `contracts/execution.py:TrustedPermissionSnapshot` 新增 `chain_grant_ids`（root-first，逐层绑定 grant 身份）；`tools/policy.py:check_chain_against_path()` 与不可变 DB 父链**逐节点/层数**比对，且 `chain[0]` 必须是 `root_id`、`chain[-1]` 必须是 `grant_id`；`check_static_authorization(db_path=…)` 在候选查找前执行 | `::test_truncated_or_reordered_chain_is_refused[leaf-only/missing-mid/extra-depth/reordered]`、`::test_chain_bound_to_another_path_is_refused`、`::test_root_mid_and_leaf_calls_are_all_allowed_with_their_own_chain` |
| **A21-R1-LOG** | 中 | worker stderr 与 `RunResult.reason` 拼原异常回显 secret | 新增 `execution/service.py:safe_reason()`：只输出**稳定错误码或异常类名**，绝不带原消息；`_call_downstream` 的 reason、`worker.py` 的 stderr 全部改用它；配置解析错误也收敛为固定文案，只打印变量**名** | `::test_worker_redacts_a_malformed_dsn`、`::test_worker_redacts_a_downstream_error_carrying_a_secret`、`::test_safe_reason_never_carries_the_message` |
| **A21-R1-BOUNDS** | 中 | 下游 `lock_timeout`/`statement_timeout` 均 0，需手动取消 | `tools/downstream.py:_bounded_timeout` + `_connect()` 为每条下游连接设置有限正 `lock_timeout`/`statement_timeout`，拒绝 0/bool/float/越界；`execution/service.py:_apply_limits()` 同样约束网关读连接 | `::test_downstream_and_gateway_waits_are_bounded`、`::test_real_lock_wait_times_out_without_manual_cancel`（真实 ACCESS EXCLUSIVE 阻塞，**不取消自有 backend**，自动超时→UNKNOWN 保预算） |
| **A21-R1-EVENT** | 高 | commit 后仍可 INSERT 第四节点 | **新增 `migrations/005_event_node_seal.sql`**（001—004 未改）：`ag_operation_path_ids()` 求 root→leaf 路径；`ag_ledger_event_nodes_guard_insert()` 强制位置连续、grant 与该位置路径节点一致、delta 与 phase/成本精确一致、总数不超路径长度（**拒绝追加**）；`ag_ledger_events_complete_set()` 为 `DEFERRABLE INITIALLY DEFERRED` 约束触发器，**COMMIT 时**要求节点集完整（缺节点整体回滚）。005 预检拒绝悬空 grant／空节点集／节点数超路径的旧库，**不清零**；短节点集旧库可升级并由运行时隔离 | `::test_committed_event_node_set_cannot_be_appended[RESERVE/SETTLE]`、`::test_wrong_node_shape_is_refused_and_rolls_back[position/path/delta/extra]`、`::test_incomplete_node_set_is_rolled_back_at_commit`、`::test_outbox_material_matches_the_database_events_exactly`、`::test_a_legitimate_terminal_node_set_still_writes` |
| **A21-R1-CANDIDATE** | 高 | 只核 items 与总额，报价身份不符仍 EXISTING | `execution/service.py:verify_accept_facts()` 比对**全部持久身份**：`quote_id`/`quote_version`/`currency`/`amount_fen` 与快照逐字段一致、快照 items 与 params items 一致、`tool_version`/calls 一致；不符→自动 sidecar 隔离、保预算、不补当前报价 | `::test_candidate_identity_mismatch_is_quarantined[quote-id/quote-version/currency/amount]`、`::test_candidate_snapshot_identity_mismatch_is_quarantined` |
| **A21-R2-SNAPSHOT** | 中 | `int/str` 强转＋普通 JSON 接受 bool/浮点/数字串/重复/未知/null/负乘积 | `tools/catalog.py:snapshot_from_bytes` 全面重写为**有界严格存储 schema**：`object_pairs_hook` 拒重复键、`parse_constant` 拒 NaN/Infinity、精确字段集拒未知/缺失、精确类型（bool/float/数字串一律拒）、正数量、非负有界单价、唯一 SKU、ID 非空、币种固定 CNY、逐行安全累加并**重算总额**；**禁止任何强转修复** | `::test_stored_snapshot_strict_schema_rejects[21 变体]`、`::test_stored_snapshot_round_trip_still_works`、`::test_malformed_snapshot_is_quarantined_by_the_entries` |
| **DOC-CKPT1-01** | 低 | tracked 数、阶段/004/数量/环境残留；README 缺可执行步骤 | `README.md` 新增**可执行**全流程（TEST DSN 清除→自建实例→迁移→可信初始化→下游 provision→一次接受→真实 worker→恢复→清理），并按**逐字抽出的 100 行程序实跑通过**；`tasks/A2-report.md` 改写为真实 Git 状态（**4 个 tracked**、逐项 untracked、无 deleted）、真实计数与阶段 | `$A/logs/readme-smoke.txt`（`SMOKE_OK`）、`$A/infra/readme-snippet.py` |

### 1.1 测试夹具的修正（不降低负例标准）

- 通知正例改为引用**真实**、同 grant/holder 拥有的操作（`tests/fixtures/execution.py:make_reference_operation`），因为严格访问政策会拒绝编造的目标 id；这是**修正错误装配**，所有负例（absent／跨租户／跨任务／other-grant／模板／接收方／注入）**全部保留并加强**。
- 权限链正例改为 `permission_for()` 自动生成 `chain_grant_ids`，与 DB 路径逐节点一致；负例新增 leaf-only／缺 mid／超长／重排／跨路径拼接五类。
- 原 r1 中靠 `dataclasses.replace(permission, chain=…)` 截短链的写法已废弃（它正是 A21-R1-CHAIN 的漏洞来源）。

---

## 2. 自查矩阵（31 项冻结 ID）

`$A` = `artifacts/workflow/A2.1-core-impl-correction-20261001c1/`。计数取自 JUnit XML，不使用旧固定总数。

### 2.1 运行类（前 28 项）

| 必需 ID | 实现/测试函数 | 命令/退出码 | pass/fail/error/skip | 断言要点／证据 | 剩余缺口 |
| --- | --- | --- | --- | --- | --- |
| **A2-P01** | `execution/service.py:_finalize`；`test_execution_core.py::test_p01_three_layer_order_settles_once` | `pytest tests/integration`（3.11）exit 0 | 1/0/0/0 | 唯一订单；三层 reserved=0 settled=70000/1；RESERVE/SETTLE 各一；outbox `SUCCEEDED/70000/PENDING` | 无 |
| **A2-P02** | `tools/downstream.py:_refuse_reason`；`::test_p02_persisted_refusal_releases_and_blocks_late_success` | 同上 | 1/0/0/0 | FAILED＋RELEASE 一次；该键迟到 execute 仍 `final_rejection`；二次 run `ILLEGAL_TRANSITION` | 无 |
| **A2-P03** | `::test_p03_zero_amount_read_settles_calls`、`::test_p03_zero_amount_failure_releases_calls`、`::test_p03_notification_effect_at_most_once_and_read_result_fixed` | 同上 | 3/0/0/0 | 金额 0／calls=1；成功结算／失败释放次数正确；通知恒 1 条；读结果固定 | 无 |
| **A2-P04** | `execution/worker.py` 真实子进程；`test_execution_recovery.py::test_p04_*`（4） | 同上 | 4/0/0/0 | 提交前零效果；`SIGKILL` 后新 PID 从持久状态恢复（PID/同步/DB 断言） | 无 |
| **A2-P05** | `::test_p05_response_lost_keeps_budget_then_settles_same_order` | 同上 | 1/0/0/0 | UNKNOWN 保 70000/1；恢复同一订单一次结算 | 无 |
| **A2-P06** | `::test_p06_recovery_after_terminal_window_has_no_duplicate_effect`＋P04 真进程用例 | 同上 | 2/0/0/0 | 无二次效果/结算/终局/outbox | 无 |
| **A2-P07** | `::test_p07_terminal_transaction_rolls_back_completely`（4 注入点） | 同上 | 4/0/0/0 | 节点/事件/outbox/status 各阶段全回滚，之后可恢复 | 无 |
| **A2-P08** | `::test_p08_query_none_does_not_release_then_late_success_settles`＋`test_execution_regressions.py::test_real_lock_wait_times_out_without_manual_cancel` | 同上 | 2/0/0/0 | 查无结果不 RELEASE；迟到成功唯一效果＋1 SETTLE；真实锁等待**自动**超时→UNKNOWN | 无 |
| **A2-P09** | `test_execution_recovery.py::test_p09_*`（3）＋`test_execution_regressions.py::test_claim_and_finalize_interleaved_never_deadlock` | 同上 | 4/0/0/0 | 双恢复者/旧 worker 各 10 轮；**锁反序 10 轮无死锁**；终态不覆盖；一终局/一 outbox | 无 |
| **A2-P10** | `test_execution_recovery.py::test_p10_*`（4） | 同上 | 4/0/0/0 | 内部恢复完成原意图且不新建；外部重试 `REVOKED`/`HOLDER_MISMATCH`/`EXPIRED` | 真实 result-read 查询保留后段 BLOCKED |
| **A2-P11** | `test_execution_quotes.py::test_p11_*`（5） | 同上 | 5/0/0/0 | 原快照/原成本/原 accepted_at；新键 `QUOTE_INVALID` 零预留；改 grant/holder/params／撤销／重放拒绝 | 无 |
| **A2-P12** | `test_execution_core.py::test_p12_*`（4）＋`test_execution_regressions.py::test_mis_bound_outcome_*`（8） | 同上 | 12/0/0/0 | 金额/意图/供应商/单价分配/错键/坏 result/缺 effect/字符串拒绝/bool 金额**全部 UNKNOWN**，零 outbox、预算保留 | 无 |
| **A2-P13** | `test_execution_concurrency.py::test_p13_*`（4） | 同上 | 4/0/0/0 | 各组 10 轮、独立连接＋barrier；逐祖先 `reserved+settled<=limit` 且非负 | 无 |
| **A2-P14** | `test_downstream.py::test_p14_*`（9） | 同上 | 14（含参数化）/0/0/0 | 订单/通知唯一约束；同键不同意图拒绝；无/错/代理凭据拒绝且零泄漏 | 无 |
| **A2-P15-CORE** | `tests/unit/test_tool_validation.py`（61）＋`test_execution_validation.py::test_p15_*`（17）＋`test_execution_regressions.py` chain/notify 组 | 同上 | 61+31+12 = 104/0/0/0 | 四完整 ID/字符串版本；重复键/SKU、bool/负/浮点/溢出、缺/空集合、scope、跨租户、关联错、URL 注入、快照绑定错、**祖先包含错/截短链**、**通知目标不存在/跨租户/跨 grant**——每例零预留零效果 | 可信夹具≠真实验签；完整 P15 留 A2.2 |
| **A2-P19** | `test_a2_migrations.py::test_p19_*`（6）＋`test_execution_regressions.py::test_legacy_material_*`（32） | 同上 | 38/0/0/0 | 001/003 非零升级七表逐行不变；非法升级数据+登记不变；重复迁移 no-op；**8 种旧材料 × 4 入口自动隔离**、预算保留、零下游 | 无 |
| **A2-P20** | `test_a2_migrations.py::test_p20_*`（7）＋`test_execution_regressions.py::test_*node*`（8） | 同上 | 15/0/0/0 | 改意图/成本/证据、删操作/路径、改删事件/节点、phase/seq、双终局、非法状态全拒；**追加/错位置/错路径/错 delta/缺节点**全拒并整体回滚；合法 UPDATE 与首次原子写仍可用 | 无 |
| **A2-CKPT1-OBL01** | `test_execution_quotes.py::test_obl01_*`（2）＋chain 组 | 同上 | 2/0/0/0 | 候选查找前不需要当前报价；命中仍走 A1 accept（proof 登记/重放拒绝）；完整链绑定 | 无 |
| **A2-CKPT1-OBL02** | `test_execution_quotes.py::test_obl02_*`（3） | 同上 | 4/0/0/0 | Event 精确排序 miss→另一 accept 提交→报价/资源消失→安全重查命中；新键/重放/变意图拒绝 | 无 |
| **A2-CKPT1-OBL03** | `test_execution_regressions.py::test_legacy_*`、`::test_candidate_*`、`test_a2_migrations.py::test_p20_*` | 同上 | — | 接受事实完整持久；**入口自动**隔离而非手动 helper；防删引用链实测 | 无 |
| **A2-CKPT1-OBL04** | `test_execution_recovery.py::test_obl04_*`（2）、`::test_p09_unknown_claim_*`、`test_execution_regressions.py::test_finalize_lock_*` | 同上 | — | owner/version/state/expiry 四条件；无接管也拒过期；UNKNOWN 保持；锁序正确 | 无 |
| **A2-CKPT1-OBL05** | `test_a2_migrations.py::test_obl05_*`（2）＋EVENT 组 | 同上 | — | sidecar/lease 不改七表、无新列；phase/seq、事件/节点防改删；**节点集封存**；TRUNCATE 清理兼容 | 无 |
| **A2-CKPT1-OBL06** | `test_execution_core.py::test_obl06_*`（2）＋SNAPSHOT 组＋`::test_outbox_material_matches_the_database_events_exactly` | 同上 | — | 完整快照逐字段比对；receipt_id/created_at/UTC 整数秒 iat 稳定；材料不可改删；**ledger_changes 与 DB 事件内容一致**；无伪 SM3/RFC8785 | 真实 SM3 留 A2.3 |
| **WF-A1-REGRESSION** | A1 全部正式测试 | `pytest tests/integration` exit 0 | A1 78 项 0 fail/error/skip | U1／P1—P14／F1—F5 逐项见 §5.1 | 无 |
| **WF-INDEPENDENT-PROBES** | reviewer 职责 | — | worker 阶段不可代做 | 本轮把 10 条 trigger 转为 98 项正式拒绝测试，但**不替 reviewer 选定唯一反例** | **须 fresh reviewer 补做** |
| **WF-QUALITY-CHECKS** | ruff/format/diff/全量 | ruff exit 0、format exit 0（52 files）、`git diff --check` exit 0 | 0 fail/error/skip | `$A/logs/checks.txt`；缺库 `pytest.fail` 不 skip | 无 |
| **WF-PY311-ENV** | 真实 CPython 3.11.16（`python:3.11-slim`） | `pip install -e '.[dev]' -c constraints.txt`＋`pip check` exit 0；unit 137／integration 282 全绿 | 与 host 一致 | `$A/logs/py311-verify.log`、`$A/junit/py311-*.xml` | 远程 CI NOT_RUN（未授权） |
| **WF-RESOURCE-ISOLATION** | 自建独占实例 | `docker run --name agent-guard-a21c-pg --label owner=agent-guard-a21c-20261001c1 … --tmpfs` | — | 归属 label／`Mounts=[]`／端口 127.0.0.1:55435；下游随机名独立库；普通 DSN 全程未设置；前后无关容器不变 | 未复用 `agent-guard-a2-pg`／`verivote-*`／reviewer 旧库 |

### 2.2 静态类（末 3 项）

| 必需 ID | 实际查证 | 结论 | 证据 | 缺口 |
| --- | --- | --- | --- | --- |
| **WF-IMMUTABLE-BASELINE** | 001—004 SHA-256 逐一比对冻结值；`src/agent_guard/ledger/` `git diff` 为空；A1 `accept(verified,cost)` 未改；无 B 代码/依赖 | **001 `d5e7bb01…`、002 `bae1d72e…`、003 `1d919f8f…`、004 `41527dc2…` 与 r1/r2 冻结值完全一致**；005 为新增 | `$A/logs/checks.txt` | 无 |
| **WF-DOCS-REPORT** | README 可执行全流程＋逐字烟测；A2-report 真实 4 tracked／逐项 untracked／无 deleted、真实计数与阶段；缺 B 生产装配拒绝；CI 无需改（新测试全在既有目录） | DOC-CKPT1-01 修复（待 reviewer 复核关闭） | `README.md`、`tasks/A2-report.md`、`$A/logs/readme-smoke.txt` | 无 |
| **WF-SNAPSHOT-COVERAGE** | §3 完整 tracked/untracked/deleted 清单；005 与全部新文件实际落盘；`git diff --check` 干净 | 候选版本已冻结待审 | §3 | 最终冻结/指纹核对属主控与 reviewer |

---

## 3. 实际变更清单（tracked／untracked／deleted）

### 3.1 tracked 修改（4 个，均在授权路径内）

| 文件 | 变更 | 性质 |
| --- | --- | --- |
| `README.md` | +163/−2 | A2.1 可执行全流程（含逐字验证过的程序） |
| `src/agent_guard/contracts/__init__.py` | +44 | 纯加法导出 |
| `tests/fixtures/isolation.py` | +51/−13 | scratch 库辅助泛化＋下游库辅助＋`TABLES` 增 004/005 新表 |
| `tests/integration/conftest.py` | +47 | A2 夹具 |

`src/agent_guard/ledger/**`、`migrations/001—003`、`pyproject.toml`、`constraints.txt` **零修改**。

### 3.2 新增（本轮 22 个，含 005 与新回归）

```
migrations/005_event_node_seal.sql                    ← 主控明确批准的同阶段补正
tests/integration/test_execution_regressions.py        ← 10 issue 正式回归（98 例）
（r1 已有并继续维护：migrations/004_execution_lifecycle.sql、
 src/agent_guard/execution/{__init__,receipts,service,store,worker}.py、
 src/agent_guard/tools/{__init__,catalog,downstream,params,policy}.py、
 tests/fixtures/execution.py、tests/integration/test_execution_*.py、
 tests/integration/test_downstream.py、test_a2_migrations.py、
 tests/unit/test_tool_validation.py）
tasks/workflow/runs/A2.1-core/implementation-r2.md      ← 本报告
```

### 3.3 既有 untracked（全部保留，未覆写/未删除）

`compose.a2.test.yaml`（**两轮均未改动**）、`src/agent_guard/contracts/execution.py`（本轮加法：`TrustedPermissionSnapshot.chain_grant_ids`、`safe_reason` 所需无新类型）、`tests/unit/test_execution_contracts.py`、`tasks/A2-*`、`tasks/workflow/**`（含 `implementation-r1.md`、`review-r2.md`、`correction-r1.md`）、`tools/workflow_gate.py`。

**deleted／renamed：无。**

---

## 4. 环境、证据与资源

| 项 | 实际值 |
| --- | --- |
| Python 3.11 验证 | Docker `python:3.11-slim`，`Python 3.11.16`，`pip check` 通过；**不以本机 3.14 冒称** |
| host 解释器 | Python 3.14.7（仅开发迭代，不作 3.11 证据） |
| PostgreSQL | 16（`postgres:16-alpine`），自建容器 `agent-guard-a21c-pg`（owner label `agent-guard-a21c-20261001c1`），网关库＋独立下游库 |
| 依赖 | 无新增；`psycopg==3.2.13`／`pytest==8.3.5`／`ruff==0.11.13` 沿用 `constraints.txt` |
| 故障层次 | 真实 `SIGKILL`／真实 PG 事务回滚／真实锁等待（**不手动取消**）／租约 TTL 由 DB 时钟移动（不 sleep）；端口响应丢失与查询无结果为**明确标注的替身**，不冒充真实断网/TLS/真密码 |
| 并发 | 全部并发组各 10 轮，独立连接＋`threading.Barrier`/`Event` |
| 日志脱敏 | `safe_reason` 只出稳定码/类名；worker 配置错误只打印变量名；malformed DSN 与含 secret 的下游异常均有捕获断言 |

### 证据索引（`$A` = `artifacts/workflow/A2.1-core-impl-correction-20261001c1/`）

```
logs/py311-verify.log        Python 3.11.16 完整矩阵（pip check/freeze、ruff、unit、integration、README 烟测）
logs/checks.txt              迁移 checksum、ruff/format/diff、host 解释器声明
logs/readme-smoke.txt        README 逐字程序实跑输出（SMOKE_OK）
logs/docker-before.txt       创建资源前无关容器只读快照
logs/resource-cleanup.txt    清理命令与前后对照（仅自有资源）
junit/py311-unit.xml         137 passed
junit/py311-integration.xml  282 passed（0 fail/error/skip）
infra/pg-up.sh               自建实例启动脚本
infra/py311-verify.sh        3.11 完整矩阵脚本
infra/readme-snippet.py      从 README 逐字抽出的程序
```

---

## 5. A1 回归映射与限制

### 5.1 A1（WF-A1-REGRESSION）逐项落点

U1 `test_input_validation`(46)+`test_rejects`(17)；P1/P2/P4/P7/P14 `test_accept_core`(13)；P3/P5/P6 `test_concurrency`(3，各 10 轮)；P8/P9/P10/P11 `test_state_checks`(11)；P12 `test_rollback`(4)；P13 `test_migrations`(8)；F1 `test_isolation`(7)；F2 `test_invariants`(15)；F3 subject 负例；F4 calls=1；F5 `test_service_config`(19)。**A1 78 项 0 fail/error/skip**，未删弱任何断言。

### 5.2 仍处 BLOCKED／NOT_RUN（不伪 PASS）

| 项目 | 状态 |
| --- | --- |
| 完整 P15 真授权、P16/P17 真签验与 result-read、P18 真 SM2 回执、P21 真实 HTTPS 闭环 | **BLOCKED**（A2.2/A2.3＋B 依赖） |
| 独立审计锚点、证据导出、规模压测 | 未实施（A3，未授权） |
| 远程 CI | **NOT_RUN**（未授权推送）；CI 已覆盖全部新测试目录 |
| **WF-INDEPENDENT-PROBES** | **NOT_RUN（worker 不可代做）**，须 fresh reviewer 独立设计并保存源/日志 |
| 通知跨 grant 访问的扩大策略 | 采用严格最小政策（同 grant/holder）；如需跨 grant，**先报主控**批准可信策略 |

### 5.3 本轮未覆盖/未验证

- r2 review 的 149 个独立 case 中失败的 52 项，本轮以**新写正式回归**覆盖其 trigger 语义，但**未复制其观察断言为通过目标**；fresh reviewer 仍须独立复跑原 trigger 与变体。
- `test_upgrade_nonzero.py` 历史探针仍因自身硬编码 `["002"]` 失败（r1 已记录，非迁移缺陷）；等价更强回归见 `test_p19_*`。

---

## 6. 交付与停止

- 本阶段补正自查完成后标 **`READY_FOR_REVIEW`** 并**停写**；所有 fix 状态为 **`FIXED_PENDING_REVIEW`**，**不得视为 CLOSED_REVIEWED**。
- 未标记 ACCEPTED、未改 `tasks/workflow/**` 控制文件/包/审查/issues、未 commit/push/PR/合并、未启动 A2.2/A2.3/A3、未引入或复制 B 代码/依赖、未改动 001—004。
- **开发者测试通过不是最终接受**；fresh reviewer 须独立复验全部历史 trigger/绕过变体、真实锁交错、旧库入口、同键拒绝/迟到效果、完整权限链、已提交事件封存与整段必跑矩阵。
