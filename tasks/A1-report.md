# A1 实施记录与验收入口

状态：**ACCEPTED**（2026-09-30最终独立复验：68单元/骨架＋78集成＋5独立探针全部通过，无失败或skip；reviewer无阻断发现）。最新结论见 [A1-review-r4.md](A1-review-r4.md)。下文及早期review保留历史记录，不将历史失败状态当作当前结论。用户已授权提交/推送A1功能分支，不合并main。

## 1. 基线与范围

- 任务：`tasks/A1-ledger.md`；验收意见：`tasks/A1-review.md`（F1—F5）。
- 基线提交：`9796825a4aa44f3ca3d6911e1094c15e7803cc35`；分支 `feat/a1-ledger`，未创建新提交、未 push。
- 开始前已有变更：两份A1任务文件由主代理预先准备；第二轮新增 `tasks/A1-review.md` 为验收输入。
- 时间：首轮实现 2026-09-29 22:19 起（两次中断会话仅完成阅读/勘察）；验收修复轮 2026-09-30 完成。
- 范围：A1账本与原子接受 + 验收缺陷修复；不包含B验签、A2执行恢复、OAuth/密码实现。

## 2. 环境与复现

- Python 3.14.7（venv；requires-python>=3.11，ruff target py311；**远程 GitHub CI 与 Python3.11 环境本轮未运行，不声称已验证**）。
- PostgreSQL 16.15（compose.test.yaml，127.0.0.1:55432，tmpfs）；psycopg 3.2.13，`constraints.txt` 锁定。
- 隔离（F1 后）：每个 pytest 会话在目标库内建独占 schema `ag_test_run_<token>`＋所有权标记表；清库仅作用于该 schema 且先复核标记；迁移 scratch 库为随机名 `ag_test_migrate_<hex>`，仅清理自建资源；DSN 经 `psycopg.conninfo` 解析/重建。
- 命令链（README §5）：compose up --wait → export `AGENT_GUARD_TEST_DATABASE_URL` → `python -m agent_guard.ledger.migrate` → `pytest tests/integration` → compose down。变量优先级：migrate 先读 `AGENT_GUARD_DATABASE_URL` 再回退 TEST 变量；pytest 只读 TEST 变量。

## 3. 检查点日志

| 检查点 | 时间 | 实际交付 | 验证结果 |
| --- | --- | --- | --- |
| 契约与环境 | 09-29 23:50 | contracts/迁移/锁序/accept 冒烟 | 通过 |
| 纵向正确性 | 09-30 00:30 | P1—P14 全部实测 | 通过 |
| 最终交付（首轮） | 09-30 01:10 | 101 passed、artifacts | 待验收 |
| 验收修复（第二轮） | 09-30 | F1—F5 修复＋回归＋探针复跑 | 见 §5/§7，全部通过 |

## 4. 变更地图（第二轮增量）

| 文件/模块 | 修改目的 | 对应F项 | 是否新增 |
| --- | --- | --- | --- |
| `tests/fixtures/isolation.py` | 独占schema＋所有权标记、随机scratch库、conninfo重建、错误目标拒绝 | F1 | 新增 |
| `tests/integration/conftest.py` | namespace 会话fixture＋收尾释放；清库走隔离层 | F1 | 修改 |
| `tests/fixtures/dbstate.py` | 仅保留只读查询；清库移出 | F1 | 修改 |
| `tests/integration/test_isolation.py` | 错误目标/篡改标记/双会话/普通DSN不外溢/非法名回归 | F1 | 新增 |
| `tests/integration/test_migrations.py` | 随机scratch、动态版本断言、001→002升级、同名不删、CLI清变量 | F1/F2 | 重写 |
| `migrations/002_root_invariants.sql` | 升级前检查、根唯一索引、任务映射不可变/禁删、可延迟FK+双向触发器、calls=1 | F2/F4 | 新增 |
| `src/agent_guard/ledger/service.py` | subject 全路径核对；connect_timeout；配置范围校验；可注入连接工厂 | F3/F5 | 修改 |
| `src/agent_guard/ledger/validation.py` | calls 必须为 1 | F4 | 修改 |
| `tests/integration/test_invariants.py` | 探针四情形正式回归＋F3/F4负例＋升级拒绝非法数据 | F2/F3/F4 | 新增 |
| `tests/unit/test_service_config.py` | 连接工厂替身：参数传递/失败映射/set_config/有界重试 | F5 | 新增 |
| `README.md` | 变量优先级如实描述、隔离说明 | F1 | 修改 |

## 5. 验收映射与实测结果

既有用例映射保持首轮 §5（U1＝`test_input_validation.py`＋`test_rejects.py`（集成展开 **17** 项）；P1—P14 逐项对应 `test_accept_core/concurrency/state_checks/rollback/migrations`）。措辞修正：首轮"49 passed"实为 46 unit＋3 骨架/文档；P6 为 **CREATED＋EXISTING** 共享同一 operation_id（非"一成功一拒绝"）。

第二轮修复用例：

| F项 | 回归用例 | 结果 |
| --- | --- | --- |
| F1 | `test_isolation.py`（错误目标拒绝无副作用、篡改标记拒绝清库、两会话互不清库、普通DSN不外溢、缺标记拒绝、非法scratch名拒绝）＋`test_migrations.py`（同名既有库不删、未自建拒drop、CLI清变量、CLI优先级） | 全部 PASS |
| F2 | `test_invariants.py::test_f2_*`（双根/改映射/删任务/孤儿根/任务指向非法根被DB拒绝；升级遇非法数据报错不删除；001→002升级旧账本不变）＋既有 P11（并发建根、撤销后重建不清零） | 全部 PASS |
| F3 | `test_f3_subject_must_match_database_grants`、`test_f3_same_key_retry_with_wrong_subject_is_rejected`（均断言无 proof/操作/事件/预留残留） | PASS |
| F4 | `test_f4_calls_must_be_exactly_one`（0/2/99/2^53-1）、`test_f4_bool_calls_are_not_integers`、`test_f4_existing_retry_does_not_consume_extra_calls` | PASS |
| F5 | `test_service_config.py`（非法配置 ValueError、connect_timeout 传递、失败映射 TRUSTED_STATE_UNAVAILABLE、set_config 生效、死锁重试有界3次） | PASS |

实际命令记录（`artifacts/A1/20260930-a1-f-fixes-r2/`，均退出码 0）：

| 命令 | 退出码 | 结果 | 耗时 |
| --- | --- | --- | --- |
| `python -m ruff check .` | 0 | 0 违规 | 0.0s |
| `python -m ruff format --check .` | 0 | 29 文件已格式化 | 0.0s |
| `python -m pytest tests/unit tests/test_scaffold.py tests/test_docs.py` | 0 | **68 passed**（65 unit＋3 骨架/文档），0 failed/skipped | 0.2s |
| `python -m agent_guard.ledger.migrate` | 0 | 001+002 已应用 | 0.1s |
| `python -m pytest tests/integration` | 0 | **77 passed**，0 failed/skipped | 11.5s |
| 主代理探针 `test_missing_invariants.py`（一次性 `ag_review_probe` 库，跑完即删） | 0 | **4 passed** | 0.2s |

合计 **145 passed**（68＋77）；并发组 P3/P5/P6 各 10 轮保持；未对网络黑洞做实验，F5 仅连接工厂替身验证（不冒充真实网络实验）；远程 GitHub CI 未运行。

## 6. 留痕位置

- `artifacts/A1/20260930-a1-f-fixes-r2/`：ruff/pytest/migrate/探针输出、git status、untracked 清单（命令行不含密码/连接串，连接串经环境变量传递）。
- 首轮留痕 `artifacts/A1/20260929T1700-a1-r1/` 保留；验收材料 `artifacts/A1/review-20260930/` 保留未改。
- Git：修改 4 个已跟踪文件（ci.yml/README/pyproject，第二轮含 README）＋未跟踪新文件（含 isolation.py、002 迁移、test_isolation/test_invariants/test_service_config 等，清单见 untracked-files.txt）；无 commit/push。

## 7. 未完成项、风险和对接

- 未完成/失败/未运行项：无（U1＋P1—P14＋F1—F5 回归全部实测通过）。NOT RUN：远程 GitHub CI、Python3.11 环境、真实网络黑洞实验（已如实标注）。
- 需要B确认：`VerifiedInvocation` 仅由 B 的 `InvocationVerifier.verify_static` 构造；digest/evidence_ref 为不透明透传。
- A2 对接：`ag_ledger_events` 保存 RESERVE 规范数据；操作状态列预留；002 迁移后 `calls` 恒为 1，A2 结算/释放沿用单次计数语义。
- 是否修改任务安全语义/替身/跳过：未修改安全语义；故障注入仅 monkeypatch 存储步骤；F5 用连接工厂替身；无 skip、无运行时后门。
- 是否有commit/push/远程变化：否。

## 8. 自查结论

实施agent提交时自查为READY_FOR_REVIEW；主代理最新结论为NOT_ACCEPTED / PARTIAL，详见A1-review-r2.md。局限声明同首轮：A1仅为执行账本与原子接受层，不得据此声称OAuth/密码/端到端安全或生产级结论。
