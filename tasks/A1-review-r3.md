# A1 第三轮修复与停点记录

日期：2026-09-30。状态：**F2 代码缺口已修复，最终验收收尾待执行**。用户要求主代理以指导、委派及复核为主，并在合适节点停止；本轮不进入 A2、不 commit/push。

## 实际完成

- 实施 agent 新增根同 ID 删除重建正式回归，并在自建 PostgreSQL 16 实例确认修复前失败：`DID NOT RAISE psycopg.IntegrityError`。
- 实施 agent 将 001→最新升级回归加强为真实 70000 分/1 次接受、撤销后七张业务表全行一致，并从迁移目录推导版本。
- 实施 agent 中途触发提供商配额限制，主代理接管小范围收尾：新增 `003_root_delete_guard.sql`，只拒绝根行 DELETE，不修改 001/002，不改写旧数据；修正一处测试格式。
- 独立 reviewer 判断无阻断缺陷，F2 代码修复可关闭；不等于既有数据库已应用 003。

## 实际验证

主代理在本轮自建容器 `agent-guard-a1-f2-fix-r3`（localhost:55440）运行：

| 验证 | 结果 |
| --- | --- |
| `pytest tests/integration -q` | 78 passed，11.22 秒，无 skip；包含原并发 10 轮组、新根保护与非零升级回归 |
| `pytest tests/unit tests/test_scaffold.py tests/test_docs.py -q` | 68 passed |
| `ruff check .` | 通过 |
| `ruff format --check .` | 首次发现一处格式问题，已修正；reviewer 独立复查通过 |
| `git diff --check` | reviewer 独立复查通过 |

证据：`artifacts/A1/20260930-a1-f2-fix-r3/` 下修复前失败日志/XML、修复后 integration.xml 和 unit.xml。artifacts 本地忽略、不提交；日志含一次性 test-only 连接信息，不含生产凭据。没有修改或清空原 `agent-guard-test-pg`；该实例尚未应用 003。

## 下一位实施 agent 的最小任务

1. 可选但建议：增强非法旧库升级失败回归。先真实非零接受与撤销，再制造非法第二根；升级失败前后比较七表全行和 `ag_schema_migrations` 完整行。当前用例只比较版本号与根数量，reviewer 将其列为非阻断覆盖不足。
2. 在新建一次性实例重跑原四项独立探针和根重建探针；本轮尚未重跑，保留历史证据，不改库名安全断言。旧非零升级探针硬编码 002，不能直接作为新增 003 后的预期；正式升级用例已经动态推导版本并通过。
3. 若修改测试，重新跑全量检查并复核，然后记录最终验收结论。不得将本轮 146 项通过等同于所有独立验收步骤完成。
4. Python 3.11、远程 CI、wheel 部署及真实网络故障仍未验证。未经用户授权不提交、推送、合并或处理分支基线。
