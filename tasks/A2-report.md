# A2 实施记录与验收入口（当前事实索引）

**状态：`READY_FOR_REVIEW`（不是 ACCEPTED）** — A2.1-core 补正轮（correction-r4）已完成并自查，等待 fresh reviewer 复验。**完整 A2 仍为 PARTIAL。**

- 任务依据：[A2-execution-gateway.md](A2-execution-gateway.md)｜基线验收：[A1-review-r4.md](A1-review-r4.md)（A1 ACCEPTED）
- 本轮详细报告：`tasks/workflow/runs/A2.1-core/implementation-r5.md`（31 ID 全矩阵＋两 fix 证据）
- 历史轮次（不覆写，只作追溯）：`implementation-r1.md`／`-r2.md`／`-r3.md`／`-r4.md`；`review-r2/r3/r5/r7.md`；`package-review-r1/r2.md`；`correction-r1/r2/r3/r4.md`；检查点一 `A2-review-ckpt1.md`／`A2-review-ckpt1-r2.md`

## 1. 当前基线与环境

| 项 | 当前事实 |
| --- | --- |
| 分支／HEAD | `feat/a2-execution-gateway`／`b120c7cf5ec0eafb18305d1207c36dd11655b324`（本地未推送、未 commit） |
| Python | 真实 CPython **3.11.16**（`python:3.11-slim` 容器内安装并跑完整矩阵，`pip check` 通过） |
| PostgreSQL | **16**（网关库＋独立下游库，两个不同数据库/连接/事务域） |
| 依赖 | 无新增；`psycopg==3.2.13`／`pytest==8.3.5`／`ruff==0.11.13`（`constraints.txt`） |
| 迁移 | `001`—`006` **全部已实现并应用**；本轮 001—006 checksum 未变、无新增迁移 |
| 远程 CI | **NOT_RUN**（未授权推送/触发） |

## 2. 当前 Git 状态（tracked 5）

| 文件 | 变更 |
| --- | --- |
| `README.md` | A2.1 可执行全流程（初始化→下游 provision→接受→worker→恢复→清理，双变体实跑） |
| `src/agent_guard/contracts/__init__.py` | 加法导出 |
| `src/agent_guard/ledger/service.py` | **+64/−3**：`accept_checked` 原子 actual-existing 材料校验（主控确认的最小 A1 兼容范围；默认 `accept(verified,cost)` 语义未变） |
| `tests/fixtures/isolation.py` | 下游库辅助＋`TABLES` |
| `tests/integration/conftest.py` | A2 夹具 |

**新增（untracked，全部在授权路径内）**：`migrations/004_execution_lifecycle.sql`、`005_event_node_seal.sql`、`006_event_seal.sql`；`src/agent_guard/contracts/execution.py`；`src/agent_guard/execution/{__init__,receipts,service,store,worker}.py`；`src/agent_guard/tools/{__init__,catalog,downstream,params,policy,results}.py`；`tests/fixtures/execution.py`；`tests/integration/test_{a2_migrations,downstream,execution_core,execution_quotes,execution_recovery,execution_concurrency,execution_validation,execution_regressions,execution_r3_regressions,execution_r4_regressions,execution_r5_regressions}.py`；`tests/unit/test_tool_validation.py`；`tasks/workflow/runs/A2.1-core/implementation-r5.md`。

**deleted／renamed：无。** `src/agent_guard/ledger/` 除 `service.py` 外零改动；`contracts/ledger.py`、`migrations/001—006` 零改动。

## 3. 当前验证结果（本轮实跑，`artifacts/workflow/A2.1-core-impl-correction-r4-20261002c4/`）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `python -m ruff check .` | 0 | All checks passed |
| `python -m ruff format --check .` | 0 | **56 files** already formatted |
| `git diff --check` | 0 | 无 whitespace 错误 |
| `pytest tests/unit tests/test_scaffold.py tests/test_docs.py` | 0 | **137 passed**（0 fail/error/skip） |
| `pytest tests/integration` | 0 | **522 passed**（0 fail/error/skip） |
| `python -m agent_guard.ledger.migrate` ×2 | 0/0 | 首次 001—006，第二次 no-op |
| README 双变体烟测（program-first／CLI-first） | 0 | 两者均 SMOKE_OK；三层 70000/1、1 单、2 事件/6 节点、1 PENDING NULL outbox |

证据：`logs/py311-verify.log`、`logs/checks.txt`、`logs/readme-smoke.txt`、`logs/resource-cleanup.txt`、`junit/py311-unit.xml`、`junit/py311-integration.xml`、`infra/{pg-up.sh,py311-verify.sh,readme-snippet.py}`。

集成 522 项构成：A1 原 78 ＋ A2.1 核心 106 ＋ r2 补正回归 101 ＋ r3 补正回归 74 ＋ r4 补正回归 65 ＋ **r5 版本边界 98**。A1 的 U1／P1—P14／F1—F5 全部保留且通过。

## 4. 当前范围与后续门槛

| 项 | 状态 |
| --- | --- |
| A2.1-core 主体＋四轮补正 | **READY_FOR_REVIEW**（待 fresh reviewer 完整 31 ID＋独立反例验收） |
| 完整 P15 真授权、P16/P17 真签验与 result-read、P18 真 SM2 回执、P21 真实 HTTPS 闭环 | **BLOCKED**（A2.2/A2.3 ＋ B 依赖；未计 PASS） |
| 独立审计锚点、证据导出、规模压测 | 未实施（A3，未授权） |
| 远程 CI | NOT_RUN（未授权） |
| WF-INDEPENDENT-PROBES | 由 fresh reviewer 独立设计（worker 不代选唯一反例） |
| 通知跨 grant 访问 | 严格最小政策（同 grant/holder）；如需扩大**先报主控** |
| P11 历史一次未知 `LedgerError` | **历史不确定性风险保留**：code/cause 无法追认，**不声称由 TTL 解释**；r7 已闭当前 mandatory 缺口 |

## 5. 31 ID 全矩阵

逐 ID 的实现/测试函数、命令、退出码、pass/fail/error/skip、断言与证据索引见 **`tasks/workflow/runs/A2.1-core/implementation-r5.md`**（本轮）；历史矩阵见 `implementation-r1/r2/r3/r4.md` 与各 `review-*.md`，不作当前结论。

**下一步**：fresh reviewer 独立复验 A21-R2-SNAPSHOT 版本残余与 DOC-CKPT1-01，以及完整 31 ID 矩阵和全部历史 trigger/绕过变体；通过后停等用户批准 A2.2，不自动进入。**开发者测试通过不是最终接受。**
