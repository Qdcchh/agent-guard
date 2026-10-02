# A2.1-core 实施/补正报告 implementation-r5

- **状态：`READY_FOR_REVIEW`（不是 ACCEPTED）**。补正包 `correction-r4.md` 的两项窄修复（SNAPSHOT 版本完整匹配、DOC 当前事实索引）已完成并自查，等待 **fresh reviewer** 复验完整 31 ID 矩阵与独立反例。完整 A2 仍为 **PARTIAL**。
- **对应补正包**：`tasks/workflow/runs/A2.1-core/correction-r4.md`，SHA-256 `74223c6e07cdf0ef346dcfb50b381aa29df3c07efb5c03bcb2c757bd5792af73`。
- **被纠正的审查**：`review-r7.md`（NEW `ses_f07b43a4affenxt8HroNe3U3FB`，`NOT_ACCEPTED`，27 PASS / 4 FAIL，snapshot `17a3b2c7a61ccc82348de5fc6de6840d8f37861b98c6851a45983981d524f3f5`）。
- **用户授权**：不变，session=`ses_f0ac0e676ffecn71p6Ww7zaqQq`、message=`msg_0f54148e0001ZW7yCMdK0TE97F`，仅 A2.1-core；不进入 A2.2/A2.3/A3，不 B/HTTP/真签名，不 Git 发布。
- **实施 session**：MiMo 2.6 Pro（`opencode-go/mimo-v2.6-pro`），单 writer，续 `ses_f0aa292caffeODmd0G8jUSZ1Y9`。
- **授权门**：`python3 tools/workflow_gate.py verify --root . --state tasks/workflow/state.json --require-authorized` → exit 0，`ok=true`、`status=CHANGES_REQUESTED`、`can_start=true`、`can_accept=false`。
- **Git**：分支 `feat/a2-execution-gateway`，HEAD `b120c7cf5ec0eafb18305d1207c36dd11655b324`（未提交）。**本轮不改 `ledger/`、不改 001—006、无新增迁移**。
- **本轮证据根**：`artifacts/workflow/A2.1-core-impl-correction-r4-20261002c4/`（下称 `$A`）。`implementation-r1/r2/r3/r4.md` 与历次 review 证据**均未覆写**。

---

## 1. Fix 1 — A21-R2-SNAPSHOT：`quote_version` 完整字符串校验

### 1.1 实际遗漏与修复

| 位置 | 修复前 | 修复后 |
| --- | --- | --- |
| `src/agent_guard/tools/params.py:233` | `if not _QUOTE_VERSION_RE.match(quote_version) or quote_version == "0"` —— **前缀匹配**，`01`/`00`/`1x`/`1@2`/`1 2`/`1.0`/`1e2`/超长全部通过 | `if _QUOTE_VERSION_RE.fullmatch(quote_version) is None` —— **完整字符串**匹配 |
| 三处 `_VERSION_RE` 模式 | `0\|[1-9][0-9]{0,17}`（含 `0` 分支，靠事后 `== "0"` 兜底） | 统一为 `[1-9][0-9]{0,17}`（首位 1-9、1—18 位、无前导零、非 0），三处规则**完全一致** |
| `tools/catalog.py:_strict_version` | 已 `fullmatch` | 同上模式，去掉冗余 `== "0"` |
| `tools/results.py:_version_field` | 已 `fullmatch` | 同上模式，去掉冗余 `== "0"` |

**拒绝矩阵**（parser 与 catalog/results 全部拒绝）：`0`/`00`/`01`/`007`/`1x`/`1@2`/`1 2`/`1.0`/`1e2`/`1/2`/`-1`/`+1`/空/空格/`1\n`/`0\n`/`1\r`/`\x00`/19 位/非 ASCII 数字。
**合法正例**：`1`、`2`、`10`、`999999999999999999`（既定 18 位上限）——parser、存储快照、结果 schema 三处一致通过。

### 1.2 接受入口负例（拒绝确因格式，非缺资源/权限）

`tests/integration/test_execution_r5_regressions.py::test_accept_entry_refuses_an_illegal_version_before_any_state` 对**每一个**非法版本：

- **可信 catalog 特意种入同一非法版本**（`CatalogQuote("quote-001", <illegal>, …)`）；
- **可信 permission 集合特意授予同一非法版本**（`quote_versions=("quote-001@<illegal>",)`）；
- 请求体携带同一非法版本。

观察：拒绝码为 **`INVALID_PARAMS`**（格式规则，不是 `QUOTE_INVALID`/`RESOURCE_NOT_*`），并且 **候选 lookup 从未发生**（`_find_candidate` 计数为空）；`ag_proofs`／`ag_operations`／`ag_ledger_events`／`ag_ledger_event_nodes`／`ag_receipt_outbox`／`ag_execution_leases`／三层计数／下游三表**全部零新增**。

### 1.3 保留的既有行为（未改稳定机制）

- **合法版本端到端**：`test_accept_entry_still_accepts_the_defined_legal_versions` —— `1`/`2`/18 位均 `CREATED`、`quote_version` 正确、`amount_fen=70000`、`calls=1`、1 operation/1 proof/1 RESERVE。
- **报价删除幂等**：`test_quote_deletion_still_yields_the_original_cost` —— 删除当前报价后同键重试仍 `EXISTING`、原快照/原成本/原 accepted_at，1 operation/1 RESERVE。
- **旧坏材料隔离**：`test_illegal_version_in_a_stored_snapshot_is_quarantined` —— 存储快照带 `01` 的旧行在 `run_operation` 自动 `LEGACY_SNAPSHOT_INVALID`＋持久 flag、预算不变、零下游。
- **未改** `ledger/`、001—006、已关闭的稳定安全机制（LOCK/NOTIFY/CHAIN/LOG/BOUNDS/EVENT/UNKNOWN/LEGACY/OUTCOME/CANDIDATE/TESTSYNC）；合法 list 语义保持（不改 tuple）。

### 1.4 新增正式回归（98 项）

| 组 | 用例 |
| --- | --- |
| parser 层 | `test_params_quote_version_rejects_every_non_decimal_positive_string`（20 非法）、`::…_accepts_the_defined_legal_strings`（4 合法） |
| 存储快照层 | `test_stored_snapshot_quote_version_uses_the_same_rule`（20）、`::…_accepts_the_same_legal_strings`（4） |
| 结果 schema 层 | `test_result_quote_version_uses_the_same_rule`（20）、`::…_accepts_the_same_legal_strings`（4） |
| 接受入口 | `test_accept_entry_refuses_an_illegal_version_before_any_state`（20）、`::…_still_accepts_the_defined_legal_versions`（4）、`test_illegal_version_in_a_stored_snapshot_is_quarantined` |
| 保留行为 | `test_quote_deletion_still_yields_the_original_cost` |

---

## 2. Fix 2 — DOC-CKPT1-01：`tasks/A2-report.md` 全文重建

按要求**重建整个当前文件为 ≤100 行当下事实索引**（现 66 行），不再保留未标历史的旧计划块：

- **顶部**：`READY_FOR_REVIEW`（不是 ACCEPTED）、完整 A2 PARTIAL、本轮 `implementation-r5.md`、历史轮次仅作链接。
- **§1 基线/环境**：实际 HEAD、Python 3.11.16、PG 16、`001—006` 全部已落地、远程 CI NOT_RUN。
- **§2 Git 状态**：**tracked 5**（`README.md`／`contracts/__init__.py`／`ledger/service.py`／`tests/fixtures/isolation.py`／`tests/integration/conftest.py`），完整新增清单（含 `006`／`tools/results.py`／五份补正回归测试／`implementation-r5.md`），deleted/renamed 无。
- **§3 验证结果**：从本轮运行结果取值 —— ruff exit 0、**56 files** formatted、unit **137**、integration **522**、迁移 ×2、README 双变体 SMOKE_OK；证据路径指向 `$A` 精确 owned 路径。
- **§4/§5**：当前范围/后续 BLOCKED、31 ID 指向 `implementation-r5.md`。
- **types docstring**（`contracts/execution.py:35–42`）本轮复核：已写「004 已强制、005/006 封存、契约类型非功能承诺」，**无旧冻结设计指令残留**，未再改动。
- 旧 `implementation-r1—r4.md`／`review-*.md`／`package-review-*.md` **不覆写**，只在顶部作历史链接。

已全文扫描确认：`359`／`424`／`tracked 4`／「主体未开工」／「004 仅计划」等旧表述在当前 A2-report 中**零残留**。

---

## 3. 自查矩阵（31 项冻结 ID）

`$A` = `artifacts/workflow/A2.1-core-impl-correction-r4-20261002c4/`。计数取自本轮 JUnit XML。

### 3.1 运行类（前 28 项）

| 必需 ID | 实现/测试 | 命令/退出码 | pass/fail/error/skip | 关键断言／证据 | 剩余缺口 |
| --- | --- | --- | --- | --- | --- |
| **A2-P01** | `execution/service.py:_finalize`；`test_execution_core.py::test_p01*` | `pytest tests/integration`（3.11）exit 0 | 1/0/0/0 | 唯一 70000/1 订单；三层 reserved=0 settled=70000/1；RESERVE+SETTLE；outbox 一致 | 无 |
| **A2-P02** | `tools/results.py`＋`_decide`；`::test_p02*`＋refusal 组 | 同上 | 2/0/0/0 | 同键持久拒绝才 RELEASE、阻止迟到成功；wrong-tool refusal 有真实订单也不 RELEASE | 无 |
| **A2-P03** | `::test_p03_*`＋正例 | 同上 | 4/0/0/0 | 0 金额计 1 次；成功结算/失败释放；通知恒 1 条；读结果固定 | 无 |
| **A2-P04** | `execution/worker.py`；`test_execution_recovery.py::test_p04_*` | 同上 | 4/0/0/0 | 提交前零效果；真 `SIGKILL`＋新 PID 持久恢复 | 无 |
| **A2-P05** | `::test_p05_*` | 同上 | 1/0/0/0 | 响应丢失→UNKNOWN 保 70000/1；恢复同单一结算 | 无 |
| **A2-P06** | `::test_p06_*`＋P04 真进程 | 同上 | 2/0/0/0 | 无二次效果/结算/终局/outbox | 无 |
| **A2-P07** | `::test_p07_*`＋checked callback 回滚组 | 同上 | 5/0/0/0 | 终局四阶段＋checked 失败 proof 回滚全回滚后可恢复 | 无 |
| **A2-P08** | `::test_p08_*`＋`::test_real_lock_wait_times_out_without_manual_cancel` | 同上 | 2/0/0/0 | 查无结果不 RELEASE；迟到唯一成功；真实表锁自动超时 | 无 |
| **A2-P09** | `test_execution_recovery.py::test_p09_*`＋真锁环锚点＋正序 10 轮 | 同上 | 4/0/0/0 | 10 轮完整终局；真 `DeadlockDetected`＋waitgraph；串行化必须失败 | 无 |
| **A2-P10** | `::test_p10_*` | 同上 | 4/0/0/0 | 撤销/过期/停 key 后内部恢复；外部重试拒绝 | 真实 result-read 留后段 |
| **A2-P11** | `test_execution_quotes.py::test_p11_*`＋原子 existing 好/坏各 10＋P11 诊断 10＋**版本接受入口 20** | 同上 | 45/0/0/0 | 原成本/快照；原子竞态好→EXISTING 坏→拒+flag+proof 不留；**非法版本候选 lookup 前零新增** | 无 |
| **A2-P12** | `::test_p12_*`＋mis-bound／order-result／other-tool／typed 形状组 | 同上 | 55/0/0/0 | 金额/意图/供应商/单价/错键/坏 result/缺 effect/字符串拒绝/bool 金额/effect-id/缺字段/重复未知/typed bool quote/deep result/items None/dict/尾 LF **全 UNKNOWN**、零 outbox；合法 list SETTLE | 无 |
| **A2-P13** | `test_execution_concurrency.py::test_p13_*` | 同上 | 4/0/0/0 | 各组 10 轮、独立连接＋barrier；逐祖先有界非负 | 无 |
| **A2-P14** | `test_downstream.py::test_p14_*` | 同上 | 14/0/0/0 | 唯一效果、冲突不覆盖、凭据拒绝零泄漏 | 无 |
| **A2-P15-CORE** | `tests/unit/test_tool_validation.py`（61）＋`test_execution_validation.py`（17）＋chain/notify/边界＋**版本 parser 40** | 同上 | 61+31+12+40=144/0/0/0 | 四完整 ID/字符串版本、重复键/SKU、bool/负/浮点/溢出、缺/空集合、scope、跨租户、关联错、URL 注入、快照绑定、祖先包含、通知目标、**quote_version 01/00/1x/1@2 等全拒**——零预留零效果 | 可信夹具≠真实验签；完整 P15 留 A2.2 |
| **A2-P19** | `test_a2_migrations.py::test_p19_*`＋legacy/deep 组 | 同上 | 41/0/0/0 | 001/003/004/005→006 非零升级七表逐行不变；非法升级数据+登记不变；重复迁移 no-op；深度 params 五入口自动隔离 | 无 |
| **A2-P20** | `test_a2_migrations.py::test_p20_*`＋node/seal 组 | 同上 | 18/0/0/0 | 改意图/成本/证据、删操作/路径、改删事件/节点、phase/seq、双终局、非法状态全拒；旧 commit 短集合补不进；seal 不可伪造；合法初写成功 | 无 |
| **A2-CKPT1-OBL01** | `test_execution_quotes.py::test_obl01_*`＋chain/params-quote/原子 existing＋**版本接受入口** | 同上 | — | 候选查找前不需要当前报价；实际 EXISTING 原子材料校验；**候选 lookup 前版本格式拒绝** | 无 |
| **A2-CKPT1-OBL02** | `test_execution_quotes.py::test_obl02_*`＋P11 精确诊断 | 同上 | 4/0/0/0 | 确定性资源/报价消失 10+ 轮；精确 code/cause/时序/DB 时钟/proof 状态 | 历史未知 `LedgerError` **不作 TTL 解释**（§5.3） |
| **A2-CKPT1-OBL03** | legacy／candidate／P20／原子 existing 组 | 同上 | — | 不完整 actual-existing 拒绝、不留新 proof、锁释放后 flag、预算保留 | 无 |
| **A2-CKPT1-OBL04** | `test_execution_recovery.py::test_obl04_*`＋UNKNOWN 组 | 同上 | — | owner/version/state/锁后 expiry；UNKNOWN no-op 现场复核 | 无 |
| **A2-CKPT1-OBL05** | `test_a2_migrations.py::test_obl05_*`＋EVENT 组 | 同上 | — | 七旧表不改行；事件完整封存；合法更新/owned 清理兼容 | 无 |
| **A2-CKPT1-OBL06** | `test_execution_core.py::test_obl06_*`＋SNAPSHOT/OUTCOME 组 | 同上 | — | fullmatch/总定义比较；完整原报价、稳定 UTC iat、不可变 PENDING | 真实 SM3 留 A2.3 |
| **WF-A1-REGRESSION** | A1 全部正式测试 | 同上 | A1 78 项 0 fail/error/skip | U1／P1—14／F1—F5 见 §5.1；默认 `accept(verified,cost)` 语义未变 | 无 |
| **WF-INDEPENDENT-PROBES** | reviewer 职责 | — | worker 不可代做 | 本轮新增 98 项版本边界回归，但**不替 reviewer 选定唯一反例** | **须 fresh reviewer 补做** |
| **WF-QUALITY-CHECKS** | ruff/format/diff/全量 | ruff exit 0、format exit 0（**56 files**）、`git diff --check` exit 0 | 0 fail/error/skip | `$A/logs/checks.txt`；缺库 `pytest.fail` 不 skip | 无 |
| **WF-PY311-ENV** | 真实 CPython 3.11.16 | `pip install -e '.[dev]' -c constraints.txt`＋`pip check` exit 0；unit 137／integration 522 全绿 | 与 host 一致 | `$A/logs/py311-verify.log`、`$A/junit/py311-*.xml` | 远程 CI NOT_RUN |
| **WF-RESOURCE-ISOLATION** | 自建独占实例 | `docker run --name agent-guard-a21f-pg --label owner=agent-guard-a21f-20261002c4 … --tmpfs` | — | 归属 label／`Mounts=[]`／127.0.0.1:55438；下游随机名独立库；普通 DSN 未设置 | 未复用既有/审查者/他人资源（`ab-review-*` 记录为 unowned 留置） |

### 3.2 静态类（末 3 项）

| 必需 ID | 查证 | 结论 | 证据 | 缺口 |
| --- | --- | --- | --- | --- |
| **WF-IMMUTABLE-BASELINE** | 001—006 SHA-256 逐一比对；`ledger/` diff 仍仅 `service.py` +64/−3（本轮零改动）；`contracts/ledger.py` 与 001—006 零改动；无 B 代码/依赖 | **001 `d5e7bb01…`、002 `bae1d72e…`、003 `1d919f8f…`、004 `41527dc2…`、005 `29529103…`、006 `3abb279b…` 全部不变**；本轮无新增迁移 | `$A/logs/checks.txt` | 无 |
| **WF-DOCS-REPORT** | A2-report **全文重建**（66 行当下事实索引）；tracked 5／完整新增清单／56 files／522 计数／`$A` 精确路径／31 ID 指向 implementation-r5；types docstring 复核无旧设计指令 | DOC 修复（待 reviewer 复核） | `tasks/A2-report.md`、`README.md`、`src/agent_guard/contracts/execution.py` | 无 |
| **WF-SNAPSHOT-COVERAGE** | §4 清单；全部新文件落盘；`git diff --check` 干净 | 候选版本已冻结待审 | §4 | 最终冻结属主控/reviewer |

---

## 4. 实际变更清单

### 4.1 本轮修改（业务/测试/报告）

```
src/agent_guard/tools/params.py        ← _QUOTE_VERSION_RE 改完整字符串匹配（+模式去掉 0 分支）
src/agent_guard/tools/catalog.py       ← _VERSION_RE 同模式，去掉冗余 == "0"
src/agent_guard/tools/results.py       ← _VERSION_RE 同模式，去掉冗余 == "0"
tests/integration/test_execution_r5_regressions.py  ← 本轮新增 98 项
tasks/A2-report.md                     ← 全文重建（66 行当下事实索引）
tasks/workflow/runs/A2.1-core/implementation-r5.md   ← 本报告
```

### 4.2 未改动（本轮）

`src/agent_guard/ledger/**`（含 `service.py`）、`migrations/001—006`、`contracts/ledger.py`、`pyproject.toml`、`constraints.txt`、README、全部既有测试与已闭安全机制。

### 4.3 tracked 5（累计）

`README.md`、`src/agent_guard/contracts/__init__.py`、`src/agent_guard/ledger/service.py`、`tests/fixtures/isolation.py`、`tests/integration/conftest.py`。

### 4.4 既有文件（保留不覆写）

`compose.a2.test.yaml`、`contracts/execution.py`、`tests/unit/test_execution_contracts.py`、`tasks/A2-*`、`tasks/workflow/**`（含 `implementation-r1—r4.md`、`review-r2/r3/r5/r7.md`、`correction-r1—r4.md`、`package-review-r1/r2.md`）、`tools/workflow_gate.py`。**deleted／renamed：无。**

---

## 5. 环境、证据与限制

| 项 | 实际值 |
| --- | --- |
| Python 3.11 验证 | Docker `python:3.11-slim`，`Python 3.11.16`，`pip check` 通过；**不以本机 3.14 冒称** |
| PostgreSQL | 16（`postgres:16-alpine`），自建容器 `agent-guard-a21f-pg`（owner `agent-guard-a21f-20261002c4`），网关库＋独立下游库 |
| 依赖 | 无新增 |
| 故障层次 | 真实 `SIGKILL`／真实 PG 事务回滚／真锁环 `DeadlockDetected`＋waitgraph／真实表锁自动超时；端口响应丢失与查无结果为明确标注替身 |
| 并发 | 全部并发组各 10 轮，独立连接＋`Barrier`/`Event`；线程异常一律失败 |

### 证据索引（`$A`）

```
logs/py311-verify.log    Python 3.11.16 完整矩阵（含 README 双变体）
logs/checks.txt          迁移 checksum、001—006 未变、ledger 范围、ruff/format/diff、tracked 5
logs/readme-smoke.txt    README 逐字程序
logs/docker-before.txt   创建资源前容器快照（含他人 unowned 容器记录）
logs/resource-cleanup.txt 仅 owned 清理与前后对照
junit/py311-unit.xml (137) / py311-integration.xml (522)
infra/pg-up.sh / py311-verify.sh / readme-snippet.py
```

### 5.1 A1 回归（WF-A1-REGRESSION）

U1 `test_input_validation`(46)+`test_rejects`(17)；P1/P2/P4/P7/P14 `test_accept_core`(13)；P3/P5/P6 `test_concurrency`(3，各 10 轮)；P8/P9/P10/P11 `test_state_checks`(11)；P12 `test_rollback`(4)；P13 `test_migrations`(8)；F1 `test_isolation`(7)；F2 `test_invariants`(15)；F3 subject 负例；F4 calls=1；F5 `test_service_config`(19)。**A1 78 项 0 fail/error/skip**。

### 5.2 仍处 BLOCKED／NOT_RUN

| 项目 | 状态 |
| --- | --- |
| 完整 P15 真授权、P16/P17 真签验与 result-read、P18 真 SM2 回执、P21 真实 HTTPS 闭环 | **BLOCKED**（A2.2/A2.3＋B 依赖） |
| 独立审计锚点、证据导出、规模压测 | 未实施（A3，未授权） |
| 远程 CI | **NOT_RUN**（未授权推送） |
| **WF-INDEPENDENT-PROBES** | **NOT_RUN（worker 不可代做）** |
| 通知跨 grant 访问扩大策略 | 严格最小政策（同 grant/holder）；如需扩大**先报主控** |

### 5.3 P11 历史不确定性（如实保留）

历史 `inherited.log` 中一次 `LedgerError` **没有记录 code**，r5/r7 诊断多轮未复现。**本报告不声称该失败已由 TTL 解释**，也不删除原失败记录；r7 已确认当前 mandatory 缺口闭合（受控 code/时序/DB 时钟同步证据），历史未知根因风险继续保留。

---

## 6. 交付与停止

- 标 **`READY_FOR_REVIEW`** 并**停写**；所有 fix 状态为 **`FIXED_PENDING_REVIEW`**，**不得视为 CLOSED_REVIEWED**。
- 未标记 ACCEPTED、未改 `tasks/workflow/**` 控制文件/包/审查/issues、未 commit/push/PR/合并、未启动 A2.2/A2.3/A3、未引入或复制 B 代码/依赖、**未改 `ledger/`／001—006、本轮无新增迁移**。
- **开发者测试通过不是最终接受**；fresh reviewer 须独立复验版本完整匹配（parser＋三处一致＋接受入口零新增）、DOC 当前事实索引，以及完整 31 ID 矩阵与全部历史 trigger/绕过变体。
