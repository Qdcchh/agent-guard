# A1 第二次主代理复验：仅F2仍未关闭

日期：2026-09-30。结论：**NOT_ACCEPTED / PARTIAL**。F1、F3、F4、F5已关闭；F2已有修复有效，但“禁止根授权删除重建”仍有可复现缺口。无需重做已通过模块。

对象：`feat/a1-ledger`，基线HEAD仍为 `9796825a4aa44f3ca3d6911e1094c15e7803cc35`，本轮验收包含工作区内尚未提交的实现。主代理没有修改业务代码、迁移或正式测试，没有commit/push。

## 1. 独立验证结果

新建并使用专属临时PostgreSQL容器 `agent-guard-a1-review-20260930-r2`（127.0.0.1:55439、tmpfs、一次性凭据），没有使用或清理原有测试实例。验收结束已停止并自动删除。

| 检查 | 实际结果 |
| --- | --- |
| Ruff及格式检查 | 通过，29个文件已格式化 |
| unit＋骨架＋文档 | 68 passed，0.09s |
| PostgreSQL integration | 77 passed，11.01s，无skip |
| 第一轮4项独立探针原样复跑 | 4 passed，0.16s |
| 新增非零账本001→002升级探针 | 1 passed，0.14s |
| 根被删除并以相同ID重建探针 | **1 failed，0.18s**：应拒绝但未拒绝 |

运行环境沿用本机Python3.14.7、psycopg3.2.13与PostgreSQL16镜像。Python3.11、远程GitHub CI及真实网络黑洞实验未运行，不声称通过。

本地证据：`artifacts/A1/review-20260930-r2/` 内的 `unit.xml`、`integration.xml`、`previous-probes.xml`、`upgrade-nonzero.xml`、`root-rebuild.xml`；新增探针源码为同目录 `test_upgrade_nonzero.py`、`test_root_rebuild.py`。第一轮探针源码保留在 `artifacts/A1/review-20260930/test_missing_invariants.py`。

## 2. 各项关闭情况

- **F1关闭**：每会话独占schema与所有权标记、随机scratch库及仅删除自建资源、DSN解析、CLI测试清除普通DSN已落实并有实际回归。这里的保证针对正常可信测试进程，仍应只向明确授权的测试实例运行测试。
- **F3关闭**：subject在DB路径检查中校验，锁后再次检查；第一次调用和幂等重试的负例通过。
- **F4关闭**：应用与002迁移均限制calls=1；原calls=2探针已被拒绝。
- **F5关闭**：显式连接超时、配置范围和有界重试已落实，连接工厂替身测试通过。不将替身测试当作实际网络故障实验。
- **F2部分关闭**：第二个根、修改任务映射、删除任务等已被拒绝；但下面的同ID删除重建仍然成功。

## 3. 唯一剩余代码阻断：同ID删除重建根

位置：`migrations/002_root_invariants.sql:97–107,148–151`，以及001中的grant不可变UPDATE触发器。

002禁止DELETE任务行，但没有禁止DELETE根授权行。任务→根的外键是可延迟的；在同一事务中删掉根，再以相同ID重新插入，到提交时外键和根映射检查仍满足。部分唯一索引也不阻止“先删后插”。

独立实测步骤：

1. 创建无子节点的根，通过真实 `ExecutionLedger.accept()` 预留70000分和1次调用。
2. 撤销该根，确认状态 `(amount_reserved=70000, calls_reserved=1, revoked=true)`。
3. 一个事务内DELETE该根，再用相同ID和原身份/时效/上限INSERT；省略预算计数和撤销列，使其采用默认值。
4. 事务成功提交。新连接查询得到 `(0, 0, false)`，原operation仍保留 `amount_fen=70000`。

这是原F2的生命周期不变量要求，不是新增OAuth功能。需要可信SQL写入路径，不是当前公网攻击入口，也不要求抵抗超级用户禁用触发器等主动破坏。

修复要求：

- 增加新迁移003，**不要修改已应用001或002**。
- 给 `ag_grants` 增加根行DELETE防护，例如 `BEFORE DELETE` 检查 `OLD.parent_grant_id IS NULL` 后以明确完整性错误拒绝。不要阻断正常预留计数UPDATE或撤销UPDATE。
- 正式回归覆盖：无子节点、已有真实预留、已撤销根，在同一事务中尝试相同ID删除重建；要求拒绝且原金额/次数/撤销/操作/证据均不变。
- 继续保留全部已有测试与两级授权场景；安全隔离测试使用本轮schema清理，不通过关闭生产触发器来让测试过关。

## 4. 需要加强的一项正式回归

`tests/integration/test_migrations.py:117–150` 的升级测试只 `build_tree()`，计数为0，且只比较grant/task/principal，不能证明真实旧账本和证据不丢。

主代理额外在001库真实接受一笔70000分操作，比较七张业务表全部行，升级到002后完全不变：**当前升级实测通过，没有发现002清零行为**。但这条场景仍应加入正式测试，以保护003及后续迁移。

请把该情形纳入正式升级回归：使用非零预留，比较task、principal、grant、operation、proof、event、event_nodes（包含所有计数字段）；版本期望从迁移目录推导。升级碰到非法旧数据时报错，并确认事务回滚、旧数据和已应用版本不变。不要只改测试名称或复用全零快照宣称已覆盖。

## 5. 下一轮实施agent最短指令

读取本文，仅修F2剩余删除重建缺口，并加强非零账本升级回归。保留F1/F3/F4/F5成果；新增003迁移，不改001/002。运行全量测试、原4探针及根删除重建回归，记录实际数量与证据，更新A1-report。不要commit/push，不扩展到A2，再交主代理复验。
