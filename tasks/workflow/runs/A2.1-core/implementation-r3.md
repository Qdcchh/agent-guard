# A2.1-core 实施/补正报告 implementation-r3

- **状态：`READY_FOR_REVIEW`（不是 ACCEPTED）**。补正包 `correction-r2.md` 的 5 项残余、2 项新边界与 DOC 项已逐条修复并自查完成，等待 **fresh reviewer** 复验。完整 A2 仍为 **PARTIAL**。
- **对应补正包**：`tasks/workflow/runs/A2.1-core/correction-r2.md`，SHA-256 `8d3901e14a3c808a72bafdf0bf7c201d72de7af6d21df8070d72d326acb0a141`。
- **被纠正的审查**：`tasks/workflow/runs/A2.1-core/review-r3.md`（NEW reviewer `ses_f0970a878ffegigoOO59gEQydI`，`NOT_ACCEPTED`，snapshot `3814a5869984e334d12aa768a7aefbbc88a98f617ed519064af4b918fb471aba`）。
- **用户授权**：不变，session=`ses_f0ac0e676ffecn71p6Ww7zaqQq`、message=`msg_0f54148e0001ZW7yCMdK0TE97F`，仅 A2.1-core；不进入 A2.2/A2.3/A3，不 B/HTTP/真签名，不 Git 发布。
- **实施 session**：MiMo 2.6 Pro（`opencode-go/mimo-v2.6-pro`），单 writer、无嵌套委派，续 `ses_f0aa292caffeODmd0G8jUSZ1Y9`。
- **授权门**：`python3 tools/workflow_gate.py verify --root . --state tasks/workflow/state.json --require-authorized` → exit 0，`ok=true`、`status=CHANGES_REQUESTED`、`can_start=true`、`can_accept=false`。
- **Git**：分支 `feat/a2-execution-gateway`，HEAD `b120c7cf5ec0eafb18305d1207c36dd11655b324`（未提交）。**001—005 checksum 全部不变**（§2.3）；按主控同阶段确认新增 `migrations/006_event_seal.sql`。
- **本轮证据根**：`artifacts/workflow/A2.1-core-impl-correction-r2-20261001c2/`（下称 `$A`）。`implementation-r1.md`／`implementation-r2.md` 与历次 review 证据**均未覆写**。

---

## 1. 逐 issue 修复对照

### 1.1 r3 确认的 5 项残余

| Issue | 根因（review-r3 §8） | 实际修复 | 新增正式回归 |
| --- | --- | --- | --- |
| **A21-R1-OUTCOME**（残余） | `_decide` 只 `json.loads` 两次取 `kind`/`operation_id`；改 `order_id`/供应商/总额/items、通知 ID/目标、read tool、重复/未知字段、typed bool quote 仍终局；wrong-tool refusal 有真实订单也 RELEASE | **一次有界严格每工具 result 解析**：新增 `src/agent_guard/tools/results.py` 定义四种规范 shape（order／notification／read／refusal），精确字段集、精确类型（bool/float/数字串全拒）、重复键/NaN/深度/大小全拒；`bind_result()` 把记录绑到本操作 key＋tool；`execution/service.py:_decide` 全部改为 `parse_result → bind_result → strict_snapshots_equal`＋逐字段绑定（effect_id＝result 的 `order_id`/`notification_id`、供应商/报价身份/逐行 items/总额重算、通知 template/recipient 对 params、read tool 对本工具、refusal 必须声明本工具）。**任何错配→UNKNOWN、无 outbox**。下游写入的就是该 shape（`tools/downstream.py` 的 read 记录去掉多余字段） | `test_execution_r3_regressions.py::test_order_result_must_fully_bind_the_accepted_facts[12 变体 × execute/query]`、`::test_wrong_tool_refusal_never_releases_an_operation_with_an_effect`、`::test_other_tool_results_must_fully_bind[3 工具 × 2 入口]`、`::test_valid_order_result_still_settles`、`::test_valid_notification_and_read_results_still_settle` |
| **A21-R1-CANDIDATE**（残余） | `verify_accept_facts` 比 snapshot/cost，却漏 `params.quote_id`/`quote_version` | **三方身份一致**：`verify_accept_facts` 现在比对 `params.quote_id/version ↔ operation.quote_id/version ↔ snapshot.quote_id/version`（＋币种/总额/items）；另在 `accept_invocation` 解析成功后**再查一次候选**，堵住「miss→解析成功→A1 直接 EXISTING」的绕过，保证「不可用候选不登记新 proof」 | `::test_params_quote_identity_binds_cost_and_snapshot[params-quote-id/params-quote-version × run/reconcile/candidate/fallback]`、`::test_consistent_params_cost_and_snapshot_are_accepted` |
| **A21-R2-SNAPSHOT**（残余）＋**A21-R1-LEGACY**（残余） | 版本 `0`/`01`/text、控制/URL/超长 ID accepted；1500 嵌套 `RecursionError` 漏 flag | `tools/catalog.py`：`_strict_id`（`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`）、`_strict_version`（十进制正整数串、无前导零、非 0）、`_bounded_depth`（≤8）；`json.loads` 的 `RecursionError` 统一映射 `LEGACY_SNAPSHOT_INVALID`。深度/身份异常在**所有入口**自动持久隔离，不靠 `int()/str()` 修复 | `::test_stored_snapshot_identity_schema_refuses[8 变体]`、`::test_stored_snapshot_deep_payload_maps_to_the_safe_error`、`::test_deep_legacy_snapshot_is_durably_quarantined[run/reconcile/candidate]` |
| **A21-R1-EVENT**（残余） | 005 只在 event INSERT 时延迟查完整性；旧已 commit 短 RESERVE/SETTLE 可在升级后补 1→2→3 | **新增 `migrations/006_event_seal.sql`**（001—005 未改）：`ag_event_seals(event_id, created_xid)` 由 `ag_ledger_events` 的 AFTER INSERT 触发器写入 `pg_current_xact_id()`；seal 行不可改删、`created_xid` 必须等于当前事务、且**只能在节点集仍为空时创建**（旧已填充事件永远拿不到 seal）；`ag_ledger_event_nodes` 的 INSERT 必须持有「本事务创建的 seal」。**不靠时间猜测、不靠客户端 boolean、不修补旧历史**；合法同事务全 path 初写不受影响 | `::test_pre006_committed_short_event_cannot_be_patched[RESERVE/SETTLE]`、`::test_fresh_full_node_set_still_writes_in_one_transaction`、`::test_seal_rows_cannot_be_forged_or_removed` |

### 1.2 r3 新增 2 项边界

| Issue | 根因 | 实际修复 | 新增正式回归 |
| --- | --- | --- | --- |
| **A21-R3-UNKNOWN**（阻断） | `_mark_unknown` 对 cached `UNKNOWN` 早 return；旧 claim 过期、新 owner 已终局后仍 10/10 报 UNKNOWN | `_mark_unknown` **每次**走统一锁序并 `assert_terminal_write_allowed` 复核**当前 state/owner/fencing/锁后 DB expiry**；终局或失租一律返回稳定错误（`ILLEGAL_TRANSITION`/`LEASE_LOST`），绝不把 cached 旧 state 当结果；正常 UNKNOWN 路径不变（保预算、无 outbox） | `::test_stale_unknown_claim_never_reports_over_a_terminal_state[10 轮]`、`::test_public_entries_also_refuse_the_stale_unknown_write[run/reconcile]`、`::test_normal_unknown_still_keeps_the_budget` |
| **A21-R3-TESTSYNC**（阻断） | 正式锁回归在持 task 后二次 barrier wait 不可能相遇，`BrokenBarrierError` 被吞，10 操作仅 RESERVE 却 PASS | 同步点移到**每个线程的第一个锁**（两种锁序都可达，正是旧反序会死锁的交错）；**任何线程异常都失败**（含 `BrokenBarrierError`）；每轮强制真实终局进展：1 订单、RESERVE+SETTLE、1 outbox、三层 settled、1 订单效果；另加**反序可被抓住**的有效性验证 | `test_execution_regressions.py::test_claim_and_finalize_interleaved_never_deadlock`（重写）、`::test_lock_regression_actually_would_catch_a_reversed_order`、`test_execution_r3_regressions.py::test_lock_regression_has_real_terminal_progress` |

### 1.3 DOC-CKPT1-01（继续修正）

- **A2-report 顶层只写当下事实**：当前环境为真实 CPython 3.11.16＋PG16、004/005/006 均已实现并应用、integration **355**；把「3.11 未跑／主体未开工／004 仅计划／182」明确标注为 **历史（2026-09-30 检查点一轮）**，不再作当前结论。
- **README 迁移输出矛盾修正**：区分 **CLI-first**（`applied: 001…006` → `already up to date` → 程序打印 `migrations applied: []`）与**全新空库由程序迁移**（打印全部版本）两种真实输出，两者均已逐字实跑验证。
- `implementation-r1.md`／`implementation-r2.md` 保留不覆盖，本轮为独立 `implementation-r3.md`。

### 1.4 已关闭项不退化

r3 已独立关闭的 **LOCK／NOTIFY／CHAIN／LOG／BOUNDS** 全部保留原实现与回归（`test_execution_regressions.py` 对应组＋`test_execution_r3_regressions.py`），本轮 355 项全绿即包含其保护；通知最小同 grant/holder 策略**未扩大**。

---

## 2. 自查矩阵（31 项冻结 ID）

`$A` = `artifacts/workflow/A2.1-core-impl-correction-r2-20261001c2/`。计数取自 JUnit XML。

### 2.1 运行类（前 28 项）

| 必需 ID | 实现/测试函数 | 命令/退出码 | pass/fail/error/skip | 关键断言／证据 | 剩余缺口 |
| --- | --- | --- | --- | --- | --- |
| **A2-P01** | `_finalize`；`test_execution_core.py::test_p01*` | `pytest tests/integration`（3.11）exit 0 | 1/0/0/0 | 唯一 70000/1 订单；三层 reserved=0 settled=70000/1；RESERVE+SETTLE；outbox 一致 | 无 |
| **A2-P02** | `_decide`＋`tools/results.py`；`::test_p02*`、`::test_wrong_tool_refusal_never_releases_an_operation_with_an_effect` | 同上 | 2/0/0/0 | 持久拒绝→FAILED+RELEASE 一次、该键不能迟到成功；**wrong-tool refusal 有真实订单也不 RELEASE** | 无 |
| **A2-P03** | `::test_p03_*`（3）＋`::test_valid_notification_and_read_results_still_settle` | 同上 | 4/0/0/0 | 金额 0／calls=1 成功结算与失败释放；通知恒 1 条；读结果固定 | 无 |
| **A2-P04** | `execution/worker.py`；`test_execution_recovery.py::test_p04_*`（4） | 同上 | 4/0/0/0 | 提交前零效果；真实 `SIGKILL`＋新 PID 从持久状态恢复 | 无 |
| **A2-P05** | `::test_p05_*` | 同上 | 1/0/0/0 | 响应丢失→UNKNOWN 保 70000/1；恢复同一订单一次结算 | 无 |
| **A2-P06** | `::test_p06_*`＋P04 真进程 | 同上 | 2/0/0/0 | 无二次效果/结算/终局/outbox | 无 |
| **A2-P07** | `::test_p07_*`（4 注入点） | 同上 | 4/0/0/0 | 节点/事件/outbox/status 各阶段全回滚后可恢复 | 无 |
| **A2-P08** | `::test_p08_*`＋`::test_real_lock_wait_times_out_without_manual_cancel` | 同上 | 2/0/0/0 | 查无结果不 RELEASE；迟到成功唯一效果；真实锁等待自动超时→UNKNOWN | 无 |
| **A2-P09** | `test_execution_recovery.py::test_p09_*`（3）＋锁交错/反序有效性格查 | 同上 | 4/0/0/0 | 各 10 轮；**每轮真实终局进展**、无死锁、无吞异常 | 无 |
| **A2-P10** | `::test_p10_*`（4） | 同上 | 4/0/0/0 | 内部恢复完成原意图不新建；外部重试 REVOKED/HOLDER_MISMATCH/EXPIRED | 真实 result-read 留后段 |
| **A2-P11** | `test_execution_quotes.py::test_p11_*`（5）＋`::test_params_quote_identity_binds_cost_and_snapshot`（4×2） | 同上 | 13/0/0/0 | 原快照/成本/accepted_at；新键 QUOTE_INVALID 零预留；**params↔成本↔快照三方身份**全入口隔离 | 无 |
| **A2-P12** | `::test_p12_*`（4）＋`test_execution_regressions.py::test_mis_bound_*`（8）＋`test_execution_r3_regressions.py::test_order_result_*`（24）＋`::test_other_tool_results_*`（6） | 同上 | 42/0/0/0 | 金额/意图/供应商/单价分配/错键/坏 result/缺 effect/字符串拒绝/bool 金额/effect-id/缺字段/重复未知/typed bool quote/deep result **全部 UNKNOWN**、零 outbox、预算保留 | 无 |
| **A2-P13** | `test_execution_concurrency.py::test_p13_*`（4） | 同上 | 4/0/0/0 | 各组 10 轮、独立连接＋barrier；逐祖先 `reserved+settled<=limit` 且非负 | 无 |
| **A2-P14** | `test_downstream.py::test_p14_*`（9） | 同上 | 14/0/0/0 | 订单/通知唯一约束；同键不同意图拒绝；无/错/代理凭据拒绝零泄漏 | 无 |
| **A2-P15-CORE** | `tests/unit/test_tool_validation.py`（61）＋`test_execution_validation.py::test_p15_*`（17）＋chain/notify 组 | 同上 | 61+31+12=104/0/0/0 | 四完整 ID/字符串版本；重复键/SKU、bool/负/浮点/溢出、缺/空集合、scope、跨租户、关联错、URL 注入、快照绑定、祖先包含、通知目标——每例零预留零效果 | 可信夹具≠真实验签；完整 P15 留 A2.2 |
| **A2-P19** | `test_a2_migrations.py::test_p19_*`（6）＋`test_execution_regressions.py::test_legacy_*`（32）＋`test_execution_r3_regressions.py::test_deep_legacy_*`（3） | 同上 | 41/0/0/0 | 001/003/004/005→006 非零升级七表逐行不变；非法升级数据+登记不变；重复迁移 no-op；8 类旧材料×4 入口＋深度快照自动隔离、预算保留 | 无 |
| **A2-P20** | `test_a2_migrations.py::test_p20_*`（7）＋`test_execution_regressions.py::*node*`（8）＋`test_execution_r3_regressions.py::test_pre006_*`（2）＋`::test_seal_rows_cannot_be_forged_or_removed` | 同上 | 18/0/0/0 | 改意图/成本/证据、删操作/路径、改删事件/节点、phase/seq、双终局、非法状态全拒；**旧 commit 短集合补不进**、seal 不可伪造/删除；合法首次原子写仍成功 | 无 |
| **A2-CKPT1-OBL01** | `test_execution_quotes.py::test_obl01_*`（2）＋chain/params-quote 组 | 同上 | 2/0/0/0 | 候选查找前不需要当前报价；命中仍走 A1 accept；完整链＋三方身份绑定 | 无 |
| **A2-CKPT1-OBL02** | `test_execution_quotes.py::test_obl02_*`（3） | 同上 | 4/0/0/0 | Event 精确排序 miss→另一 accept 提交→报价/资源消失→安全重查命中；新键/重放/变意图拒绝 | 无 |
| **A2-CKPT1-OBL03** | legacy／candidate／P20 组 | 同上 | — | 接受事实完整持久；**全入口自动**隔离；防删引用链＋**事件 seal** 实测 | 无 |
| **A2-CKPT1-OBL04** | `test_execution_recovery.py::test_obl04_*`、`::test_p09_unknown_claim_*`、`::test_stale_unknown_*` | 同上 | — | owner/version/state/expiry 四条件；无接管也拒过期；**UNKNOWN no-op 也复核现场四条件** | 无 |
| **A2-CKPT1-OBL05** | `test_a2_migrations.py::test_obl05_*`＋EVENT 组 | 同上 | — | sidecar/lease 不改七表无新列；phase/seq、事件/节点防改删；**006 封存旧 commit 集合**；TRUNCATE 清理兼容 | 无 |
| **A2-CKPT1-OBL06** | `test_execution_core.py::test_obl06_*`＋SNAPSHOT/OUTCOME 组 | 同上 | — | 完整快照逐字段；receipt_id/created_at/UTC iat 稳定；材料不可改删；**result 严格 schema 绑定**；无伪 SM3/RFC8785 | 真实 SM3 留 A2.3 |
| **WF-A1-REGRESSION** | A1 全部正式测试 | 同上 | A1 78 项 0 fail/error/skip | U1／P1—P14／F1—F5 见 §5.1 | 无 |
| **WF-INDEPENDENT-PROBES** | reviewer 职责 | — | worker 不可代做 | 本轮新增 72 项 r3 回归，但**不替 reviewer 选定唯一反例** | **须 fresh reviewer 补做** |
| **WF-QUALITY-CHECKS** | ruff/format/diff/全量 | ruff exit 0、format exit 0（54 files）、`git diff --check` exit 0 | 0 fail/error/skip | `$A/logs/checks.txt`；缺库 `pytest.fail` 不 skip | 无 |
| **WF-PY311-ENV** | 真实 CPython 3.11.16 | `pip install -e '.[dev]' -c constraints.txt`＋`pip check` exit 0；unit 137／integration 355 全绿 | 与 host 一致 | `$A/logs/py311-verify.log`、`$A/junit/py311-*.xml` | 远程 CI NOT_RUN |
| **WF-RESOURCE-ISOLATION** | 自建独占实例 | `docker run --name agent-guard-a21d-pg --label owner=agent-guard-a21d-20261001c2 … --tmpfs` | — | 归属 label／`Mounts=[]`／127.0.0.1:55436；下游随机名独立库；普通 DSN 未设置 | 未复用既有/审查者资源 |

### 2.2 静态类（末 3 项）

| 必需 ID | 查证 | 结论 | 证据 | 缺口 |
| --- | --- | --- | --- | --- |
| **WF-IMMUTABLE-BASELINE** | 001—005 SHA-256 逐一比对冻结值；`src/agent_guard/ledger/` 无 diff；A1 `accept` 未改；无 B 代码/依赖 | **001 `d5e7bb01…`、002 `bae1d72e…`、003 `1d919f8f…`、004 `41527dc2…`、005 `29529103…` 全部不变**；006 为同阶段授权新增 | `$A/logs/checks.txt` | 无 |
| **WF-DOCS-REPORT** | README 双变体逐字烟测；A2-report 当下事实＋历史段标注；真实 tracked/untracked；缺 B 生产装配拒绝 | DOC 修复（待 reviewer 复核） | `README.md`、`tasks/A2-report.md`、`$A/logs/readme-smoke.txt` | 无 |
| **WF-SNAPSHOT-COVERAGE** | §3 清单；006 与全部新文件落盘；`git diff --check` 干净 | 候选版本已冻结待审 | §3 | 最终冻结属主控/reviewer |

---

## 3. 实际变更清单

### 3.1 tracked 修改（4 个，均在授权路径内）

`README.md`（双变体迁移输出＋当下事实）、`src/agent_guard/contracts/__init__.py`（加法导出）、`tests/fixtures/isolation.py`（下游库辅助＋`TABLES`）、`tests/integration/conftest.py`（A2 夹具）。

`src/agent_guard/ledger/**`、`migrations/001—005`、`pyproject.toml`、`constraints.txt` **零修改**。

### 3.2 本轮新增/实质修改

```
migrations/006_event_seal.sql                       ← 主控同stage确认新增
src/agent_guard/tools/results.py                    ← 严格每工具 result schema（新）
src/agent_guard/execution/service.py                ← _decide 全字段绑定、verify_accept_facts 三方身份+
                                                      全事件覆盖、_mark_unknown 现场四条件、解析后再查候选
src/agent_guard/tools/catalog.py                    ← 严格 ID/version/深度边界
src/agent_guard/tools/downstream.py                 ← read 结果改为规范 shape
src/agent_guard/contracts/execution.py              ← DownstreamOutcome docstring 指向 result 契约
tests/integration/test_execution_r3_regressions.py  ← 72 项 r3 回归（新）
tests/integration/test_execution_regressions.py     ← 锁回归重写＋反序有效性验证
tests/integration/test_a2_migrations.py             ← 006 升级期待
tasks/workflow/runs/A2.1-core/implementation-r3.md   ← 本报告
```

### 3.3 既有文件（保留不覆写）

`compose.a2.test.yaml`（三轮均未改动）、`src/agent_guard/contracts/execution.py`（加法）、`tests/unit/test_execution_contracts.py`、`tasks/A2-*`、`tasks/workflow/**`（含 `implementation-r1/r2.md`、`review-r2/r3.md`、`correction-r1/r2.md`）、`tools/workflow_gate.py`。**deleted／renamed：无。**

---

## 4. 环境、证据与资源

| 项 | 实际值 |
| --- | --- |
| Python 3.11 验证 | Docker `python:3.11-slim`，`Python 3.11.16`，`pip check` 通过；**不以本机 3.14 冒称** |
| PostgreSQL | 16（`postgres:16-alpine`），自建容器 `agent-guard-a21d-pg`（owner `agent-guard-a21d-20261001c2`），网关库＋独立下游库 |
| 依赖 | 无新增；`psycopg==3.2.13`／`pytest==8.3.5`／`ruff==0.11.13` |
| 故障层次 | 真实 `SIGKILL`／真实 PG 事务回滚／真实锁等待（不手动取消）／租约 TTL 由 DB 时钟移动；端口响应丢失与查无结果为**明确标注的替身**，不冒充真实断网/TLS/真密码 |
| 并发 | 全部并发组各 10 轮，独立连接＋`Barrier`/`Event`；**线程异常一律失败** |

### 证据索引（`$A`）

```
logs/py311-verify.log        Python 3.11.16 完整矩阵（pip check/freeze、ruff、unit、integration、README 双变体）
logs/checks.txt              迁移 checksum、001—005 未变、ruff/format/diff
logs/readme-smoke.txt        README 变体 B（CLI-first → no-op）实跑输出
logs/docker-before.txt       创建资源前无关容器只读快照
logs/resource-cleanup.txt    清理命令与前后对照（仅自有资源）
junit/py311-unit.xml         137 passed
junit/py311-integration.xml  355 passed（0 fail/error/skip）
infra/pg-up.sh / py311-verify.sh / readme-snippet.py
```

---

## 5. A1 回归映射与限制

### 5.1 A1（WF-A1-REGRESSION）

U1 `test_input_validation`(46)+`test_rejects`(17)；P1/P2/P4/P7/P14 `test_accept_core`(13)；P3/P5/P6 `test_concurrency`(3，各 10 轮)；P8/P9/P10/P11 `test_state_checks`(11)；P12 `test_rollback`(4)；P13 `test_migrations`(8)；F1 `test_isolation`(7)；F2 `test_invariants`(15)；F3 subject 负例；F4 calls=1；F5 `test_service_config`(19)。**A1 78 项 0 fail/error/skip**，未删弱任何断言。

### 5.2 仍处 BLOCKED／NOT_RUN

| 项目 | 状态 |
| --- | --- |
| 完整 P15 真授权、P16/P17 真签验与 result-read、P18 真 SM2 回执、P21 真实 HTTPS 闭环 | **BLOCKED**（A2.2/A2.3＋B 依赖） |
| 独立审计锚点、证据导出、规模压测 | 未实施（A3，未授权） |
| 远程 CI | **NOT_RUN**（未授权推送） |
| **WF-INDEPENDENT-PROBES** | **NOT_RUN（worker 不可代做）** |
| 通知跨 grant 访问扩大策略 | 严格最小政策（同 grant/holder）；如需扩大**先报主控** |

### 5.3 本轮未覆盖

- r3 的 216 个独立 case 中 60 项失败，本轮以**新写正式回归**覆盖其 trigger 语义，**未复制其观察断言为通过目标**；fresh reviewer 仍须独立复跑原 trigger 与变体。
- 历史 `test_upgrade_nonzero.py` 仍因自身硬编码 `["002"]` 失败（非迁移缺陷）；等价更强回归为 `test_p19_*`（动态推导版本＋七表逐行比较）。

---

## 6. 交付与停止

- 标 **`READY_FOR_REVIEW`** 并**停写**；所有 fix 状态为 **`FIXED_PENDING_REVIEW`**，**不得视为 CLOSED_REVIEWED**。
- 未标记 ACCEPTED、未改 `tasks/workflow/**` 控制文件/包/审查/issues、未 commit/push/PR/合并、未启动 A2.2/A2.3/A3、未引入或复制 B 代码/依赖、未改动 001—005。
- **开发者测试通过不是最终接受**；fresh reviewer 须独立复验 A21-R1-OUTCOME/CANDIDATE/EVENT/LEGACY/SNAPSHOT 残余、A21-R3-UNKNOWN/TESTSYNC 新边界与 DOC，以及完整 31 ID 矩阵与全部历史 trigger/绕过变体。
