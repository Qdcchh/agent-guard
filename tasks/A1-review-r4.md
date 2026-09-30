# A1 最终验收

日期：2026-09-30。结论：**A1 ACCEPTED**。独立 reviewer 未发现实质性或阻断缺陷，主代理核对实际日志/XML 后接受；F1—F5 全部关闭。本结论仅适用于 A1 进程内账本，不代表 A2、密码机制或端到端系统完成。

## 最终实测

隔离环境：Python 3.14.7、psycopg 3.2.13、PostgreSQL 16.15；reviewer 自建一次性容器，localhost 动态端口 57732。数据库测试清除普通 `AGENT_GUARD_DATABASE_URL`，只使用本轮专用 TEST DSN。

| 命令（仓库根目录） | 结果 |
| --- | --- |
| `.venv/bin/python -m ruff check .` | 通过 |
| `.venv/bin/python -m ruff format --check .` | 29 文件通过 |
| `git diff --check` | 通过 |
| `.venv/bin/python -m agent_guard.ledger.migrate` 两次 | 首次应用 001/002/003，第二次无变更 |
| `.venv/bin/python -m pytest tests/unit tests/test_scaffold.py tests/test_docs.py` | 68 passed |
| `.venv/bin/python -m pytest tests/integration` | 78 passed，10.82 秒 |
| `.venv/bin/python -m pytest artifacts/A1/review-20260930/test_missing_invariants.py` | 4 passed（ag_review_probe） |
| `.venv/bin/python -m pytest artifacts/A1/review-20260930-r2/test_root_rebuild.py` | 1 passed（ag_review_f2） |

正式套件 146 项＋独立探针 5 项，共 **151 项通过，0 failure/error/skip**。P3/P5/P6 各执行 10 轮并发。pytest 实跑附带 `-vv --color=no --junitxml=<对应证据文件>`。

- 003 根 DELETE 触发器实际启用；同 ID 重建被拒绝，70000 分/1 次/撤销状态及 RESERVED 操作保持不变。
- 正式非零升级测试覆盖 001→003，七张业务表全行不变；没有修改或误用历史硬编码 002 的升级探针。
- 001/002 checksum 与既有库记录一致；本轮未改历史迁移。
- 只删除本轮自建容器。既有三个容器及原测试库迁移记录、七表只读摘要前后不变；原测试库仍为 001/002，应用 003 需另行明确执行。

证据保存在本地忽略目录 `artifacts/A1/review-20260930-r4-7e62b91d04af/`：unit/integration/four-probes/root-rebuild 日志及 XML、checks.log、database-verify.log、旧库前后核验及 cleanup.log。不上传 artifacts、数据库快照或连接凭据。

## 边界与非阻断建议

- 本次本地未验证 Python 3.11、远程 CI、wheel 部署及真实网络故障；推送后的 CI 结果需另行核对。
- 非阻断可选增强：非法旧库升级失败用例可增加非零预留/撤销后七表和完整迁移登记表快照。当前只比较版本号与非法根数量，未发现实际回滚缺陷，不阻断 A1。
- 没有实现 OAuth/OIDC、SM2/SM3、DID、HTTP 网关、下游执行/结算/恢复或前端。A1 可信对象不能直接暴露为网络验权输入。
- 用户本轮授权提交并推送 A1 功能分支，不授权绕过保护合并 main。文档 PR #1 尚未合并，分支基线依赖仍需保留。
