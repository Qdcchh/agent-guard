# A2.1-core 实施/补正报告 implementation-r1

- **状态：`READY_FOR_REVIEW`（不是 ACCEPTED）**。A2.1-core 主体已实施并完成自查；完整 A2 仍为 **PARTIAL**。
- **对应任务包**：`tasks/workflow/runs/A2.1-core/task-v1.md`（v1，frozen，SHA-256 `67896f80e7b80fe05087f88ef08576c805117bfdd12654addff03efadf2bfec4`）；完整包审 `tasks/workflow/runs/A2.1-core/package-review-r1.md`（`PACKAGE_READY`）。
- **用户授权**：role=user，session=`ses_f0ac0e676ffecn71p6Ww7zaqQq`，message=`msg_0f54148e0001ZW7yCMdK0TE97F`，原文见 `tasks/workflow/state.json:authorization.source_message`。范围**仅 A2.1-core**；不进入 A2.2/A2.3/A3，不 commit/push/PR/合并。
- **实施 task/session**：本轮 `mimo-implementer`／MiMo 2.6 Pro（`opencode-go/mimo-v2.6-pro`），单 writer、无嵌套委派。
- **Git**：分支 `feat/a2-execution-gateway`，HEAD `b120c7cf5ec0eafb18305d1207c36dd11655b324`（与基线相同，本轮未提交任何内容）。工作区状态见 §2。
- **授权门**：`python3 tools/workflow_gate.py verify --root . --state tasks/workflow/state.json --require-authorized` → exit 0，`ok=true`、`can_start=true`、`can_accept=false`、`accepted=false`（实施前实跑；`authorization_is_structural_only=true`，真人消息已由主控核对）。

---

## 1. 最终行为与实际变更

### 1.1 交付的行为（A2.1-core 一段完整核心）

| 能力 | 落点 | 关键语义 |
| --- | --- | --- |
| 004 迁移 | `migrations/004_execution_lifecycle.sql` | sidecar／lease／outbox 三张新表；七旧表**只加约束与触发器、不加列不改行**；phase↔seq 绑定、事件/节点防改删、状态机迁移、已接受路径与操作防删、非法升级预检 |
| 可信合成资源与报价 | `src/agent_guard/tools/catalog.py` | 只由可信初始化种子；订单总额由固定报价版本 × 数量计算（CNY 整数分，≤2^53−1）；报价改/删不影响已接受意图 |
| 四工具严格参数 | `src/agent_guard/tools/params.py` | 完整四 ID／字符串版本 `"1"`；拒绝重复 JSON 键、重复 SKU、bool/负/浮点/溢出数量、缺/空集合、未知字段、别名、URL/路径注入 |
| 分层授权（可信对象） | `src/agent_guard/tools/policy.py` | 快照绑定、完整链收窄（子集合⊆父、max_quantity 不增）、scope、资源归属/关联；**不是真实验签** |
| 独立事务域模拟下游 | `src/agent_guard/tools/downstream.py` | 独立数据库/连接/事务；稳定键＝operation_id；效果/意图/结果/终局拒绝唯一约束原子保存；服务 secret 认证 |
| 执行/结算/释放/UNKNOWN 恢复 | `src/agent_guard/execution/service.py` | 候选→原快照→A1 accept；miss 后任意资源/报价解析失败安全重查；终局四阶段单事务；不一致/未知一律 UNKNOWN 保预算 |
| 租约 | `src/agent_guard/execution/store.py` | owner+version+合法 state+锁后 DB 有效 expiry 四条件；RESERVED→EXECUTING 同事务；过期 EXECUTING 先对账；UNKNOWN 保持 UNKNOWN |
| 待签 outbox | `src/agent_guard/execution/receipts.py` | 稳定 receipt_id、不可变材料、created_at 派生 UTC 整数秒 iat；缺 B 保持 `PENDING`／`receipt_jws=NULL`，无伪 SM3/RFC8785 |
| 真实进程 worker | `src/agent_guard/execution/worker.py` | `python -m agent_guard.execution.worker`；配置只读环境变量，不打印 DSN/secret |

### 1.2 实际 Git 状态（tracked／untracked／deleted 分开，纠正 DOC-CKPT1-01）

**本轮 tracked 修改（4 个文件，均为加法/兼容扩展，未删弱任何断言）**

| 文件 | 变更 | 性质 |
| --- | --- | --- |
| `src/agent_guard/contracts/__init__.py` | +44（原基线已 +42 的导出，本轮再加 `TrustedPermissionSnapshot` 一项） | 纯加法导出 |
| `README.md` | +49/−2 | 新增 A2.1 结构说明与可复现的测试库／worker／清理命令 |
| `tests/fixtures/isolation.py` | +51/−13 | scratch 库辅助函数泛化为 `_create/_drop_named_database`，新增下游库辅助与 `TABLES` 三张 004 新表；未改任何断言语义 |
| `tests/integration/conftest.py` | +47 | 新增 `downstream_db`／`downstream_dsn`／`a2` 夹具 |

**本轮新增 untracked 文件（21 个，全部在授权路径内）**

```
migrations/004_execution_lifecycle.sql
src/agent_guard/execution/__init__.py
src/agent_guard/execution/receipts.py
src/agent_guard/execution/service.py
src/agent_guard/execution/store.py
src/agent_guard/execution/worker.py
src/agent_guard/tools/__init__.py
src/agent_guard/tools/catalog.py
src/agent_guard/tools/downstream.py
src/agent_guard/tools/params.py
src/agent_guard/tools/policy.py
tests/fixtures/execution.py
tests/integration/test_a2_migrations.py
tests/integration/test_downstream.py
tests/integration/test_execution_concurrency.py
tests/integration/test_execution_core.py
tests/integration/test_execution_quotes.py
tests/integration/test_execution_recovery.py
tests/integration/test_execution_validation.py
tests/unit/test_tool_validation.py
tasks/workflow/runs/A2.1-core/implementation-r1.md   (本报告)
```

**既有 untracked 文件（本轮全部保留，未覆盖/未删除）**

```
compose.a2.test.yaml                     ← 未修改（本轮资源用独立 docker run 实例，见 §3）
src/agent_guard/contracts/execution.py   ← 加法扩展：TrustedPermissionSnapshot、DOWNSTREAM_INTENT_CONFLICT
tests/unit/test_execution_contracts.py   ← 未修改
tasks/A2-execution-gateway.md / A2-report.md / A2-review-ckpt1.md / A2-review-ckpt1-r2.md
tasks/workflow/** (README/context/implementation-contract/review-contract/issues/
                   state-guide/state.json/stages/*/templates/*)
tools/workflow_gate.py
```

**deleted / renamed：无。** 本轮未删除、未重命名任何文件。

> **DOC-CKPT1-01 纠正**：旧 `A2-report.md` 把 `compose.a2.test.yaml` 误列为已跟踪修改并称"本轮又追加执行类型导出"。实际：该 Compose **始终是 untracked**，本轮也未改动；已跟踪修改只有 `src/agent_guard/contracts/__init__.py`。已在 `tasks/A2-report.md` §3 改写并注明，`A2-report.md` 状态行与检查点表同步更新（128 行）。

### 1.3 共享契约变化（只做加法）

`src/agent_guard/contracts/execution.py`（既有 untracked，授权允许加法导出）：

- 新增 `TrustedPermissionSnapshot`：A2.1 分层检查用的**可信夹具**对象（scope＋root→leaf 约束链＋绑定字段）。docstring 明确：这不是 B 的权限快照契约、不是验签，生产路径无 B 快照即失败关闭。
- 新增 `ExecutionErrorCode.DOWNSTREAM_INTENT_CONFLICT`：同键不同意图的下游拒绝码（原语义不改，只加成员）。
- 其余既有类型（`TrustedQuoteSnapshot`／`GrantConstraints`／`DownstreamOutcome`／`LeaseGrant`／`PendingReceipt`／`VerifiedResultQuery`）**语义未改**；`OperationStatus` 的 docstring 仍如实写"004 尚未落地时仅为应用侧约定"，本轮 004 落地后由数据库触发器强制。

`src/agent_guard/contracts/__init__.py`：仅加法导出（含 `TrustedPermissionSnapshot`）。A1 的 `VerifiedInvocation`／`TrustedCost`／`AcceptResult`／`ErrorCode` **未改签名、未改语义**。

### 1.4 ledger 调用方与锁序

- `ledger/service.py`、`store.py`、`validation.py`、`provisioning.py`、`migrations/001—003` **零修改**（`git status` 可证）。`execution/` 只**调用** `ledger.store.load_path / lock_task / lock_grants_root_to_leaf / lock_principals / db_now_epoch / fetch_operation_by_business_key` 与 `ExecutionLedger.accept(verified, cost)`，未改 accept 签名。
- 全局锁序保持 `principals（如需）→ task → 根至叶 grants → operation → lease`；`_claim`、`_finalize`、`_mark_unknown` 三条路径都按此顺序加锁，无反向获取。下游调用在网关事务**外**。
- `migrate.py` 未改；004 由既有的动态版本发现自动纳入（`expected_versions()` 从目录推导）。

### 1.5 运行依赖

**无新增运行依赖**。`pyproject.toml`、`constraints.txt`、`uv.lock` 本轮均未改动（`psycopg[binary]==3.2.13`、`pytest==8.3.5`、`ruff==0.11.13` 沿用既有锁定）。未引入 HTTP 框架（A2.1 无 HTTP 入口）。

---

## 2. 自查矩阵（31 项冻结 ID 逐项实际映射）

说明：`命令` 列为仓库根目录实际执行；所有集成测试使用真实 PostgreSQL 16 与**独立下游数据库**。`证据` 根为 `artifacts/workflow/A2.1-core-impl-20261001w1/`（下表简写 `$A`）。计数取自 JUnit XML，不使用旧固定总数。

### 2.1 运行类（前 28 项）

| 必需 ID | 具体实现/测试文件函数 | 实际命令/退出码 | pass/fail/error/skip | 断言/证据路径 | 剩余缺口 |
| --- | --- | --- | --- | --- | --- |
| **A2-P01** 三层订单 70000/1 唯一效果 | `execution/service.py:run_operation`→`_finalize`；`tests/integration/test_execution_core.py::test_p01_three_layer_order_settles_once` | `pytest tests/integration/test_execution_core.py`（3.11 容器）exit 0 | 1 passed / 0 / 0 / 0 | 唯一 `ds_orders` 行；根/中/叶 `amount_reserved=0,amount_settled=70000,calls_settled=1`；事件 `(RESERVE,0)+(SETTLE,1)`；outbox `SUCCEEDED/70000/PENDING/jws=NULL`；`ledger_changes.events` 顺序 RESERVE→SETTLE、节点根→叶 | 无 |
| **A2-P02** 下游持久终局拒绝 | `tools/downstream.py:_refuse_reason`（供应商未获服务→持久拒绝）；`test_execution_core.py::test_p02_persisted_refusal_releases_and_blocks_late_success` | 同上 exit 0 | 1 / 0 / 0 / 0 | `FAILED`；全路径 `reserved=0,settled=0`；事件 `(RESERVE,0)+(RELEASE,1)`；outbox `FAILED/amount_fen=0`；同一键迟到 execute 仍 `final_rejection=True`、`ds_orders=0`；二次 run 报 `ILLEGAL_TRANSITION` | 无 |
| **A2-P03** 零金额读取/通知 | `test_execution_core.py::test_p03_zero_amount_read_settles_calls`、`::test_p03_zero_amount_failure_releases_calls`、`::test_p03_notification_effect_at_most_once_and_read_result_fixed` | 同上 exit 0 | 3 / 0 / 0 / 0 | 金额 0／calls=1 预留；成功 `calls_settled=1`、失败 `calls_reserved→0`；`ds_notifications` 恒为 1；读结果字节重复查询完全一致 | 无 |
| **A2-P04** 真实进程恢复 | `execution/worker.py`（真实子进程）；`test_execution_recovery.py::test_p04_accept_alone_never_touches_the_downstream`、`::test_p04_rejected_accept_leaves_no_operation_and_no_effect`、`::test_p04_real_process_never_started_is_recovered_by_a_new_process`、`::test_p04_p06_real_process_killed_in_crash_window_then_restarted` | 同上 exit 0 | 4 / 0 / 0 / 0 | 提交前下游 0 行；拒绝接受 0 预留 0 效果；`subprocess.Popen` + `SIGKILL`（`proc.pid==observed["pid"]`），崩溃窗口内 `EXECUTING`+1 订单+0 终局；新进程恢复后 1 订单/1 SETTLE/1 outbox | 无（真实进程，非 finally/异常替身） |
| **A2-P05** 响应丢失→UNKNOWN | `test_execution_core.py::test_p05_response_lost_keeps_budget_then_settles_same_order`（`ResponseLossPort` 端口边界双，**非真实断网**） | 同上 exit 0 | 1 / 0 / 0 / 0 | UNKNOWN 保 `reserved=70000/1`、事件仅 RESERVE、outbox 0；接管恢复后同**一**订单、1 SETTLE、`fencing_version` 递增 | 无 |
| **A2-P06** 终局窗口崩溃 | `test_execution_core.py::test_p06_recovery_after_terminal_window_has_no_duplicate_effect`、`test_execution_recovery.py::test_p04_p06_real_process_killed_in_crash_window_then_restarted` | 同上 exit 0 | 2 / 0 / 0 / 0 | 无二次效果/结算/终局事件/outbox；`ds_orders=1`、`ag_ledger_events=2`、`ag_receipt_outbox=1` | 无 |
| **A2-P07** 终局事务原子回滚 | `execution/store.py` 四个可注入步骤；`test_execution_core.py::test_p07_terminal_transaction_rolls_back_completely`（参数化 counters/event/outbox/status） | 同上 exit 0 | 4 / 0 / 0 / 0 | 每个注入点后 `ag_ledger_events=1`、`event_nodes=3`、`outbox=0`、计数回到 reserved；解除注入后可正常恢复并恰好一次终局 | 无 |
| **A2-P08** 查无结果后迟到成功 | `test_execution_core.py::test_p08_query_none_does_not_release_then_late_success_settles` | 同上 exit 0 | 1 / 0 / 0 / 0 | query→None 时**不 RELEASE**、预算保留、事件仅 RESERVE；迟到请求落地后唯一效果＋1 SETTLE | 无 |
| **A2-P09** 双恢复者/过期旧 worker | `test_execution_recovery.py::test_p09_two_recoverers_race_one_terminal_and_one_outbox`、`::test_p09_expired_old_worker_cannot_overwrite_the_new_terminal`、`::test_p09_unknown_claim_keeps_unknown_and_never_releases` | 同上 exit 0 | 3 / 0 / 0 / 0 | 各 10 轮、`threading.Barrier`＋独立连接；每轮恰好 1 终局/1 outbox/1 效果；旧 worker 迟到被 `LEASE_LOST`/`ILLEGAL_TRANSITION` 拒绝；UNKNOWN claim 保持 UNKNOWN | 无 |
| **A2-P10** 撤销/过期/停用 | `test_execution_recovery.py::test_p10_internal_recovery_completes_after_revocation`、`::test_p10_external_retry_rejected_after_revocation`、`::test_p10_external_retry_rejected_after_key_deactivation`、`::test_p10_expiry_blocks_external_retry_but_not_internal_recovery` | 同上 exit 0 | 4 / 0 / 0 / 0 | 内部恢复仅凭持久事实完成原意图且不新建意图（`ag_operations` 计数不变）；外部重试分别 `REVOKED`/`HOLDER_MISMATCH`/`EXPIRED` | **真实授权查询（result-read 真验权）保留 BLOCKED 后段**（A2.2/P17） |
| **A2-P11** 报价改/删后原快照 | `test_execution_quotes.py::test_p11_existing_intent_survives_quote_edit_and_delete`、`::test_p11_new_key_requires_a_valid_current_quote`、`::test_p11_wrong_quote_version_amount_or_association_is_refused`、`::test_p11_changed_grant_holder_or_params_stay_conflicts`、`::test_p11_revocation_still_blocks_new_intents` | 同上 exit 0 | 5 / 0 / 0 / 0 | 同键重试返回 `EXISTING`＋原 `quote_snapshot`/`amount_fen`/`accepted_at`；新键 `QUOTE_INVALID` 且 0 预留；改 grant/holder/params 仍 `IDEMPOTENCY_CONFLICT`、proof 重放 `REPLAY`、撤销 `REVOKED` | 无 |
| **A2-P12** 金额/意图/快照错配 | `test_execution_core.py::test_p12_amount_mismatch_keeps_budget_and_never_settles`、`::test_p12_intent_mismatch_keeps_budget`、`::test_p12_same_total_different_supplier_never_settles`、`::test_p12_reallocated_unit_prices_never_settles` | 同上 exit 0 | 4 / 0 / 0 / 0 | 真实下游已产生效果（`effect_ref` 非空）但比对不一致 → 一律 UNKNOWN、预算保留、outbox 0；同总额不同供应商/单价分配同样拒绝结算 | 无 |
| **A2-P13** 预算/次数并发 | `test_execution_concurrency.py::test_p13_two_draws_race_for_the_root_budget`、`::test_p13_intermediate_ancestor_budget_binds_under_concurrency`、`::test_p13_call_limit_exhaustion_under_concurrency`、`::test_p13_concurrent_accept_settle_and_recovery` | 同上 exit 0 | 4 / 0 / 0 / 0 | 各组 10 轮、`threading.Barrier`＋每线程独立连接；`assert_within_limits` 逐祖先 `reserved+settled<=limit` 且非负；无死锁（全部 10 轮在 4.7s 内收敛） | 无 |
| **A2-P14** 下游幂等/冲突/认证 | `test_downstream.py::test_p14_same_key_same_intent_replays_one_order`、`::test_p14_notification_and_read_are_idempotent_too`、`::test_p14_same_key_different_intent_is_refused`、`::test_p14_concurrent_downstream_executions_one_effect`、`::test_p14_execute_refuses_missing_or_wrong_service_secret`、`::test_p14_query_refuses_missing_or_wrong_service_secret`、`::test_p14_unauthenticated_call_cannot_be_forced_by_a_direct_agent`、`::test_p14_unknown_operation_query_returns_none_without_leaking`、`::test_p14_refused_key_can_never_produce_an_effect_later` | 同上 exit 0 | 14（含参数化）/ 0 / 0 / 0 | 订单与通知均唯一约束防重复（并发 10 轮每轮恰 1 效果）；同键不同意图 `DOWNSTREAM_INTENT_CONFLICT`；无/错/代理凭据 `DOWNSTREAM_UNAUTHORIZED` 且 0 效果、detail 不回显 secret；拒绝键永不复活 | 认证在服务层强制，非"藏端口" |
| **A2-P15-CORE** 分层负例 | `tests/unit/test_tool_validation.py`（61 项纯进程内）＋`tests/integration/test_execution_validation.py::test_p15_*`（17 项 PG 断言） | 同上 exit 0 | 61 + 31 = 92 / 0 / 0 / 0 | 四完整 ID/字符串版本；重复 JSON 键/SKU、bool/负/浮点/溢出、缺/空集合、scope 不足、跨租户、关联错、URL/路径注入、快照绑定错、祖先包含错、max_quantity 上调——**每一例 `assert_zero_state`**：0 操作/0 预留/0 事件/0 下游效果 | **可信夹具≠真实验签**；完整 P15 真授权留 A2.2 |
| **A2-P19** 非零升级保全 | `test_a2_migrations.py::test_p19_upgrade_from_001_preserves_nonzero_seven_tables`、`::test_p19_upgrade_from_003_preserves_nonzero_seven_tables`、`::test_p19_illegal_upgrade_changes_nothing`、`::test_p19_repeated_migration_is_a_no_op`、`::test_p19_legacy_material_is_quarantined_and_never_backfilled`、`::test_p19_missing_evidence_is_quarantined_too` | 同上 exit 0 | 6 / 0 / 0 / 0 | 001/003 真实非零预留＋撤销＋证据升级后 `SELECT *` 七表逐行完全相同；非法升级（RESERVE/1 旧事件）→ `CheckViolation` 且七表与 `ag_schema_migrations` 完全不变（仍 001—003）；重复迁移 `[]`；旧材料不足→sidecar 隔离、预算保留、不补当前报价执行 | 无 |
| **A2-P20** 直接 SQL 防绕过 | `test_a2_migrations.py::test_p20_intent_cost_and_evidence_cannot_be_rewritten_by_sql`、`::test_p20_accepted_operations_and_paths_cannot_be_deleted`、`::test_p20_events_and_nodes_cannot_be_updated_or_deleted`、`::test_p20_phase_seq_binding_and_double_terminal_are_refused`、`::test_p20_illegal_status_transitions_are_refused`、`::test_p20_legitimate_updates_still_work`、`::test_p20_unreferenced_non_root_grant_delete_stays_possible` | 同上 exit 0 | 7 / 0 / 0 / 0 | 改意图/成本/证据/tool/grant/accepted_at 全部 `CheckViolation` 且前后行相等；删操作、删已接受路径节点、先删事件节点再删事件全被拒；`(RESERVE,1)/(SETTLE,0)/(RELEASE,0)/(SETTLE,2)` 插入被拒；双终局/非法状态迁移被拒（含同值重写）；合法计数/撤销/状态 UPDATE 与未引用非根节点删除仍可用 | 无 |
| **A2-CKPT1-OBL01** 候选前静态校验 | `test_execution_quotes.py::test_obl01_candidate_lookup_never_requires_a_current_quote`、`::test_obl01_static_authorization_rejects_before_any_candidate_lookup` | 同上 exit 0 | 2 / 0 / 0 / 0 | 报价删除后候选命中仍返回 `EXISTING`＋原成本；新 proof 被登记并关联同一操作；重放仍 `REPLAY`；静态拒绝发生在候选读取之前（`ag_proofs=0`） | 无 |
| **A2-CKPT1-OBL02** 确定性安全重查 | `test_execution_quotes.py::test_obl02_deterministic_miss_accept_gone_then_safe_recheck`（参数化 `quote`/`resource` 两种解析失败）、`::test_obl02_recheck_still_refuses_new_keys_and_replays`、`::test_obl02_changed_intent_is_still_refused_after_the_recheck` | 同上 exit 0 | 4 / 0 / 0 / 0 | `threading.Event` 精确排序：A 首次候选 miss→阻塞于解析→B 提交同键→报价/资源消失→A 安全重查命中并返回同操作/同成本；仅 1 操作/1 RESERVE/1 次预留；新键仍拒、重放仍拒、变意图仍拒 | 无 |
| **A2-CKPT1-OBL03** 接受事实与防删 | `test_a2_migrations.py::test_p19_legacy_material_is_quarantined_and_never_backfilled`、`::test_p20_accepted_operations_and_paths_cannot_be_deleted`、`test_execution_quotes.py::test_obl01_*` | 同上 exit 0 | 3 / 0 / 0 / 0 | 候选行完整持久化接受事实可读回；`ag_operations` BEFORE DELETE、`ag_grants` 被引用节点 BEFORE DELETE、事件/节点 UPDATE/DELETE 全触发器实测（非 doc 承诺）；异常旧行进 `ag_operation_review_flags` 隔离 | 无 |
| **A2-CKPT1-OBL04** 租约四条件 | `execution/store.py:assert_terminal_write_allowed`；`test_execution_recovery.py::test_obl04_expired_lease_without_any_new_owner_is_still_refused`、`::test_obl04_live_lease_by_another_owner_is_refused`、`::test_p09_unknown_claim_keeps_unknown_and_never_releases` | 同上 exit 0 | 3 / 0 / 0 / 0 | owner／version／state／expiry 同时校验；**无新 owner 仅时间流逝**也拒旧 worker；owner 错、version 错各自被拒；活跃他人租约拒并"无变更"（owner/fencing 不动）；UNKNOWN 保持且不释放 | 无 |
| **A2-CKPT1-OBL05** sidecar/phase-seq/保全 | `test_a2_migrations.py::test_obl05_sidecar_and_lease_do_not_change_legacy_rows`、`::test_obl05_test_owned_cleanup_still_works`、`::test_p19_illegal_upgrade_changes_nothing`、`::test_p20_events_and_nodes_cannot_be_updated_or_deleted` | 同上 exit 0 | 4 / 0 / 0 / 0 | sidecar/lease 写入前后七表 `SELECT *` 完全相同；七表**无** `*quarantine*`/`*review*` 新列；phase/seq CHECK、事件/节点防改删实测；`reset_state`（TRUNCATE 级自有清理）不受行级触发器影响 | 无 |
| **A2-CKPT1-OBL06** 完整报价/稳定材料 | `test_execution_core.py::test_obl06_receipt_material_is_stable_immutable_and_unsigned`、`::test_obl06_full_snapshot_comparison_drives_the_decision`、`::test_p12_same_total_different_supplier_never_settles` | 同上 exit 0 | 3 / 0 / 0 / 0 | 逐字段比对含供应商与逐行单价；outbox 重读完全相同（`receipt_id` 确定性、`iat=int(created_at.timestamp())`、UTC tz）；6 种改写/删除 SQL 全被拒；材料不含 `sm3`/`rfc8785` 字样；`PENDING`/`receipt_jws=NULL` | 真实 SM2 `result_sm3`/`ledger_sm3` 留 A2.3 |
| **WF-A1-REGRESSION** | A1 原全部测试＋3 个历史探针 | `pytest tests/unit tests/test_scaffold.py tests/test_docs.py` exit 0（137 passed，其中 A1 原 68＋checkpoint-1 8）；`pytest tests/integration` exit 0（184 passed，其中 A1 原 78）；历史探针 `pytest artifacts/A1/review-*` exit 0/0/1 | A1 146 项全部通过、0 fail/error/skip；探针 4+1 passed | U1（`test_input_validation` 46＋`test_rejects` 17）、P1—P14（`test_accept_core` 13／`test_concurrency` 3／`test_state_checks` 11／`test_rollback` 4／`test_invariants` 15／`test_migrations` 8／`test_isolation` 7）逐项映射见 §5.2；根重建拒绝与非零七表升级保全实测 | 见 §5.3 探针版本断言差异 |
| **WF-INDEPENDENT-PROBES** | — | — | NOT_RUN（worker 阶段按定义不可代做） | 本项要求"**最终 reviewer 独立设计**绕过/边界探针并保存可复现源与实跑日志；worker 不替 reviewer 选择唯一反例"。worker 未编造探针、也未声明任何"唯一反例"覆盖 | **必须由独立 reviewer 完成**，是验收前唯一非 worker 项 |
| **WF-QUALITY-CHECKS** | ruff/format/diff/全量测试 | `python -m ruff check .` exit 0（All checks passed）；`python -m ruff format --check .` exit 0（51 files already formatted）；`git diff --check` exit 0（无输出）；unit+骨架+文档 exit 0；`pytest tests/integration` exit 0（缺库即 `pytest.fail`，不 skip） | 0 fail/error/skip | `$A/logs/checks-host.txt`、`$A/logs/py311-verify.log`、`$A/junit/*.xml` | 新增测试全部放在既有 `tests/unit`、`tests/integration` 目录，**CI 无需新增目录**（见 §4.3） |
| **WF-PY311-ENV** | 真实 CPython 3.11.16（`python:3.11-slim`，digest `sha256:e41613d42d48…`）容器内完整矩阵 | `pip install -e '.[dev]' -c constraints.txt` exit 0；ruff check/format exit 0；unit 137 passed；integration 184 passed；整体 exit 0 | 与 host 一致，0 fail/error/skip | `$A/logs/py311-verify.log`（含 `pip freeze`）；`$A/junit/py311-unit.xml`、`py311-integration.xml` | 本机仅有 3.14/3.9，**不以 3.14 冒称**；远程 CI 未授权推送 → NOT_RUN（不额外阻断） |
| **WF-RESOURCE-ISOLATION** | 自建独占实例 | `docker run -d --name agent-guard-a21w-pg --label owner=agent-guard-a21w-20261001w1 … --tmpfs /var/lib/postgresql/data -p 127.0.0.1:55434:5432 postgres:16-alpine` | — | 归属 label／容器 ID `a97b52e989df…`／`Mounts=[]`（tmpfs）／端口仅 127.0.0.1；下游为随机名独立库 `ag_test_downstream_*`；普通 `AGENT_GUARD_DATABASE_URL` 全程未设置且 worker 不读取；`$A/logs/docker-before.txt`、`pg-container-inspect.txt`、`resource-cleanup.txt` | 未复用既有 `agent-guard-a2-pg`／`verivote-*`；清理仅自有资源 |

### 2.2 静态类（末 3 项）

| 必需 ID | 实际查证 | 命令/退出码 | 结论 | 证据 | 剩余缺口 |
| --- | --- | --- | --- | --- | --- |
| **WF-IMMUTABLE-BASELINE** | 001—003 SHA-256 与包审冻结值逐一比对；`git diff` 确认 `ledger/**`、`migrations/001—003` 零修改；A1 `accept(verified,cost)` 签名未改；无 B 代码/依赖引入 | `shasum -a 256 migrations/*.sql` exit 0 | 001 `d5e7bb01…`、002 `bae1d72e…`、003 `1d919f8f…` **与 package-review-r1 §2.2 完全一致**；`git status` 只有 4 个允许路径内 tracked 修改 | `$A/logs/checks-host.txt`、§1.2 | 无 |
| **WF-DOCS-REPORT** | README 增补 A2.1 结构＋可复现初始化/worker/下游/测试/清理命令；A2-report 纠正 tracked/untracked 笔误并更新检查点表；本报告 31 项逐 ID→函数/命令/计数/证据；缺 B 生产装配拒绝（无假验权开关、无签名替身）；CI 无需改（新测试全在既有目录） | `git diff --stat README.md tasks/A2-report.md` | DOC-CKPT1-01 已纠正（仍待 reviewer 复核关闭） | `README.md`、`tasks/A2-report.md`、本文件 | 无 |
| **WF-SNAPSHOT-COVERAGE** | 本报告 §1.2 给出完整 tracked/untracked/deleted 清单；004 与全部新文件 SHA-256 见 `$A/logs/checks-host.txt`（迁移）与实际文件；`git diff --check` 干净；无 writer 并发写入 | `git status --short --branch --untracked-files=all` exit 0 | 候选版本已冻结待审；契约/任务包 hash 由 state.json 与包审绑定 | §1.2、`$A/logs/checks-host.txt` | **最终冻结与指纹核对属主控/reviewer 职责** |

---

## 3. 环境、故障和资源

### 3.1 环境

| 项 | 实际值 |
| --- | --- |
| 本机解释器 | Python 3.14.7（`.venv`）／系统 3.9.6；**无 3.11 解释器** |
| Python 3.11 验证 | Docker 镜像 `python:3.11-slim`（`Python 3.11.16`，digest `sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e`）内 `pip install -e '.[dev]' -c constraints.txt` |
| 依赖锁定 | `psycopg==3.2.13`、`psycopg-binary==3.2.13`、`pytest==8.3.5`、`ruff==0.11.13`（constraints.txt 既有，未改） |
| PostgreSQL | 16（`postgres:16-alpine`），自建容器 `agent-guard-a21w-pg`（ID `a97b52e989df2a8bf0e941451cba0b88ba4c4e924ad222893266d9dff7aaa143`） |
| 数据库拓扑 | 网关账本库 `agent_guard_a21w_gw`（run-exclusive schema `ag_test_run_*`）＋**独立下游库** `ag_test_downstream_<random>`；两者同实例、不同库/连接/事务 |
| 连接凭据 | 仅本轮 TEST DSN；普通 `AGENT_GUARD_DATABASE_URL` 全程未设置，worker/pytest 均不读取；日志/JUnit 不含 DSN/密码/token/secret（worker 的异常信息只含类型与 detail） |

### 3.2 故障层次（明确区分，未互相冒充）

| 层次 | 本轮是否使用 | 如何实现 |
| --- | --- | --- |
| 真实独立进程终止/重启 | **是** | `subprocess.Popen([sys.executable, "-m", "agent_guard.execution.worker"])` ＋ `signal.SIGKILL`；PID 与同步文件证据 |
| 真实 PostgreSQL 事务回滚 | **是** | P07 注入点后真实 `conn.transaction()` 回滚并重跑恢复 |
| 端口边界响应丢失双 | 是（标注） | `ResponseLossPort`：真实下游提交后报告"响应丢失"。**不是真实断网**，报告中不作此声明 |
| 查询返回"查无结果" | 是（标注） | `NoneThenRealPort`：前 N 次 query 返回 `None`。**不是真实网络故障** |
| Monkeypatch 步骤注入 | 是（标注） | P07 对 `execution/store.py` 四个步骤注入异常；无运行时旁路开关 |
| 租约 TTL 时间流逝 | 是（确定性） | 直接把 `lease_expires_at` 移到过去（等价于 TTL 到期），**不 sleep 碰运气** |
| 真实断网／TLS 部署／真实 SM2/SM3 | **否** | 后段 A2.2/A2.3；本轮不作任何相关声明 |

### 3.3 并发与同步

- 全部并发组各 **10 轮**（A2-P09 三组、A2-P13 四组、A2-P14 一组）。
- 同步一律 `threading.Barrier` / `threading.Event`；每个 racer 自建 `ExecutionService`／`ExecutionLedger`／连接，**独立连接**。
- 无 `sleep` 用于竞态判定；仅 P10 的有效期窗口用**轮询真实数据库时钟条件**（`expires_at <= clock_timestamp()`）而非固定等待。

### 3.4 资源归属与清理

| 资源 | 归属标记 | 处置 |
| --- | --- | --- |
| 容器 `agent-guard-a21w-pg` | `--label owner=agent-guard-a21w-20261001w1`、`purpose=a21-core-implementation-tests`、`managed-by=docker-run-not-compose` | 本轮自建，**按名精确删除** |
| 库 `agent_guard_a21w_gw` | 随容器 tmpfs | 随容器消失 |
| 库 `ag_test_downstream_*` | `tests.fixtures.isolation.create_downstream_database`（随机名、created 标记） | 每个测试会话结束自行 DROP |
| 库 `ag_review_probe` / `ag_review_f2` / `ag_review_upgrade` | 本轮为复验历史探针而创建（位于自有容器内） | 按名 DROP |
| schema `ag_test_run_*` | 所有权标记表 `ag_test_ownership` | 每会话 `release_namespace` 自行 DROP |

**未触碰**：既有 `agent-guard-a2-pg`（project `agent-guard-a2`）、`verivote-web`／`verivote-api`、`agent-guard_default`／`agent-guard-a2_default` 网络、`agent-guard-test-pg`；未执行任何 `docker prune`／批量 `stop`／共享 `down`。前后对照见 `$A/logs/docker-before.txt` 与 `resource-cleanup.txt`。

---

## 4. 31 项之外的必查专项（对应 review-contract §6 C1—C6）

| 专项 | 实际观察 |
| --- | --- |
| C1 Compose/PG 所有权 | 本轮**未使用**任何既有 Compose project；自建 `docker run` 实例带归属 label，端口 55434 与既有 55432/55433 不冲突；`compose.a2.test.yaml` 保持原样未改动 |
| C2/P11 候选与重查 | 候选查找前仅 schema/静态授权/可信集合；命中用原快照＋持久事实仍走 A1 accept；miss 后**任意**资源/报价解析失败安全重查（OBL02 参数化 `quote`/`resource` 两种） |
| C3/P19 非零升级 | sidecar 不改七表行形状；001→004 与 003→004 均真实非零预留＋撤销＋证据，`SELECT *` 前后逐行相同；非法升级七表与迁移登记全保全 |
| C4/P20 事件与候选保全 | `ag_ledger_events_phase_seq` CHECK（RESERVE/0、SETTLE|RELEASE/1）＋`UNIQUE(operation_id,seq)`；事件/节点 UPDATE/DELETE 触发器；`ag_operations` 与被引用 `ag_grants` 的 DELETE 触发器；直接删操作、先删事件再删操作、路径删除重建全部实测拒绝 |
| C5 租约/DB 时效 | owner＋fencing＋合法 state＋`clock_timestamp()` 有效 expiry 四条件；无接管者也拒过期旧 worker；UNKNOWN claim 保持 UNKNOWN；EXECUTING 接管先 query 对账 |
| C6 完整报价/稳定材料 | 执行与查询持久化并逐字段比对**完整** `TrustedQuoteSnapshot`（含供应商、逐行单价）；不一致 UNKNOWN；`receipt_id`/`created_at`/UTC 整数秒 iat 稳定、材料不可改删；缺 B 保持 `PENDING` |
| P04 真进程 | 真实 `Popen`＋`SIGKILL`＋PID/同步文件＋DB 断言；新进程从持久状态恢复 |
| P15-CORE 四工具负例 | 92 个负例（61 unit＋31 integration）全部 `assert_zero_state`；不免除后段真实验权 |
| A1 全量回归 | A1 146 项正式用例 0 fail/error/skip；根同 ID 重建拒绝（`test_root_rebuild` 探针＋`test_invariants`）、非零七表升级（`test_migrations::test_p13_upgrade_from_001_keeps_existing_ledger`）均实跑 |
| 全部并发/回滚/恢复 | 每组 10 轮、独立连接＋barrier/event、逐祖先金额/次数、操作/事件/outbox 与订单/通知数量一并断言 |

---

## 5. 问题、限制和移交

### 5.1 问题台账

| Issue ID | 状态 | 说明 |
| --- | --- | --- |
| **DOC-CKPT1-01** | `FIXED_PENDING_REVIEW` | 已在 `tasks/A2-report.md` §3 纠正 tracked/untracked 与"追加导出"笔误，并在本报告 §1.2 复述实际 Git 状态。**须由独立 reviewer 复核后才能 CLOSED_REVIEWED** |

本轮未发现新的阻断缺陷；未删除、未降级任何既有断言或需求。

### 5.2 A1 回归逐项映射（WF-A1-REGRESSION）

| A1 要求 | 实际测试落点（本轮实跑） |
| --- | --- |
| U1 | `tests/unit/test_input_validation.py`（46）＋`tests/integration/test_rejects.py`（17） |
| P1 | `test_accept_core.py::test_p1_three_layer_reservation` |
| P2 | `test_accept_core.py::test_p2_*`（8 例） |
| P3 | `test_concurrency.py::test_p3_two_branches_race_for_root_budget`（10 轮） |
| P4 | `test_accept_core.py::test_p4_intermediate_ancestor_budget_binds` |
| P5 | `test_concurrency.py::test_p5_call_limit_race_with_zero_amount`（10 轮） |
| P6 | `test_concurrency.py::test_p6_concurrent_same_key_one_operation`（10 轮） |
| P7 | `test_accept_core.py::test_p7_*`（3 例） |
| P8 | `test_state_checks.py::test_p8_*` |
| P9 | `test_state_checks.py::test_p9_lock_wait_until_proof_expires_is_rejected` |
| P10 | `test_state_checks.py::test_p10_*` |
| P11 | `test_state_checks.py::test_p11_*`＋F2 DB 回归 |
| P12 | `test_rollback.py::test_p12_*`（4 例） |
| P13 | `test_migrations.py::test_p13_*`（8 例，版本由目录动态推导） |
| P14 | `test_accept_core.py::test_p14_retry_reuses_original_cost_and_evidence` |
| F1 隔离 | `test_isolation.py`（7 例）＋下游随机名库/归属标记 |
| F2 唯一根与重建 | `test_invariants.py`＋历史探针 `test_root_rebuild.py`（1 passed） |
| F3 subject | `test_accept_core.py::test_p2_*`＋探针 `test_missing_invariants.py`（4 passed） |
| F4 calls=1 | `test_input_validation.py`＋`test_rejects.py`＋002 `ag_operations_single_call` |
| F5 有界连接/配置 | `test_service_config.py`（19） |

### 5.3 历史探针承接（未修改历史证据）

- `test_missing_invariants.py`（`ee232af9…`）：**4 passed**，exit 0。
- `test_root_rebuild.py`（`27d58251…`）：**1 passed**，exit 0。
- `test_upgrade_nonzero.py`（`ab58df8e…`）：**1 failed**，exit 1。失败点是探针自身硬编码的 `assert apply_migrations(conn) == ["002"]`（`test_upgrade_nonzero.py:46`）；仓库现含 001—004，实际应用列表为 `["002","003","004"]`。这正是包审 §5.3 预告的"历史源码硬编码 `["002"]`"情形。**历史文件未改动**，失败证据保留在 `$A/junit/probe-upgrade-nonzero.xml`。等价且更强的正式回归：`test_a2_migrations.py::test_p19_upgrade_from_001_preserves_nonzero_seven_tables`（动态推导版本、七表逐行比较、另加撤销与计数断言）与 `test_migrations.py::test_p13_upgrade_from_001_keeps_existing_ledger`。详细说明见 `$A/logs/a1-historical-probes.txt`。

### 5.4 明确的限制与后段 BLOCKED

| 项目 | 本轮状态 |
| --- | --- |
| 完整 P15 真实授权（B 验证器＋可信 grant/token/祖先绑定） | **BLOCKED**（缺 B）；本轮仅可信对象分层，已在矩阵注明 |
| A2-P16 真 token/proof 签验、body/holder/endpoint 替换、盗 token | **BLOCKED**（A2.2＋B） |
| A2-P17 result-read 真验权、TTL、撤销/停用、跨租户/holder、并发 proof | **BLOCKED**（A2.2＋B）；`VerifiedResultQuery` 已备类型但生产路径失败关闭 |
| A2-P18 真 SM2 回执签名、签后崩溃、篡改验签 | **BLOCKED**（A2.3＋B）；本段仅稳定待签材料＋原子 outbox＋恢复不重复业务 |
| A2-P21 真实 HTTPS 联合闭环 | **BLOCKED**（A2.2/A2.3） |
| 独立审计锚点、证据导出、规模压测 | **未实施**（A3 范围，未授权） |
| 远程 CI | **NOT_RUN**（未授权推送/触发）；本地 CI 配置已确认会收集全部新增测试（均在既有 `tests/unit`、`tests/integration`） |
| WF-INDEPENDENT-PROBES | **NOT_RUN（worker 不可代做）**，须独立 reviewer 补齐 |
| `ag_review_upgrade` 历史探针 | 1 failed（探针自身过时版本断言），见 §5.3 |

### 5.5 证据索引

根目录 `artifacts/workflow/A2.1-core-impl-20261001w1/`：

```
logs/checks-host.txt            ruff check/format、git diff --check、迁移 SHA-256
logs/py311-verify.log           Python 3.11.16 完整矩阵（含 pip freeze、安装输出）
logs/host-unit.txt              host unit+骨架+文档 运行输出
logs/host-integration.txt       host 全 integration 运行输出
logs/a1-historical-probes.txt   历史探针复验与版本断言差异说明
logs/a1-probes-run.txt          三个探针的实际命令/退出码
logs/docker-before.txt          创建资源前无关容器/网络只读快照
logs/pg-container-inspect.txt   自建容器 ID/端口/挂载/归属 label
logs/resource-cleanup.txt       清理命令与前后对照（仅自有资源）
junit/py311-unit.xml            137 passed（Python 3.11）
junit/py311-integration.xml     184 passed（Python 3.11）
junit/host-unit.xml / host-integration.xml
junit/probe-missing-invariants.xml / probe-root-rebuild.xml / probe-upgrade-nonzero.xml
infra/pg-up.sh                  自建实例启动脚本（可复现）
infra/py311-verify.sh           Python 3.11 完整矩阵脚本（可复现）
```

### 5.6 测试计数汇总（不使用旧固定总数）

| 套件 | Python 3.11.16 | 其中本轮新增 | 其中 A1 保留 | fail/error/skip |
| --- | --- | --- | --- | --- |
| unit＋骨架＋文档 | 137 | 61（`test_tool_validation`） | 68（A1）＋8（checkpoint-1 `test_execution_contracts`） | 0 / 0 / 0 |
| integration | 184 | 106（`test_execution_core` 18、`test_execution_recovery` 13、`test_execution_quotes` 11、`test_execution_concurrency` 4、`test_execution_validation` 31、`test_downstream` 14、`test_a2_migrations` 15） | 78（A1） | 0 / 0 / 0 |
| 历史独立探针 | 5（+1 过时断言） | — | 5 | 1 failed（§5.3） |

---

## 6. 交付与停止

- 本阶段自查完成后标 **`READY_FOR_REVIEW`** 并**停写**，交主控冻结候选版本，由**全新 reviewer** 按 `review_kind=IMPLEMENTATION_ACCEPTANCE` 独立实跑验收。
- 未标记 ACCEPTED、未修改 `tasks/workflow/**`（state/issues/契约/审查报告）、未 commit/push/PR/合并、未启动 A2.2/A2.3/A3、未引入或复制 B 代码/依赖。
- **开发者测试通过不是最终接受**；WF-INDEPENDENT-PROBES 与全部独立实跑、绕过变体、资源核验须由 reviewer 独立完成。
