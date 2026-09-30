# A1 主代理验收记录：需修正后复验

此为第一轮历史验收记录；最新复验与关闭情况见 [A1-review-r2.md](A1-review-r2.md)，不要将本文件全部旧缺陷继续视为未修复。

验收日期：2026-09-30。结论：**NOT_ACCEPTED / 交付状态PARTIAL**。已有主体实现及现有测试有效，但尚不满足A1完整契约；不能进入“全部验收通过”状态。

验收对象：`feat/a1-ledger`，HEAD仍为 `9796825a4aa44f3ca3d6911e1094c15e7803cc35`，包括当前未提交和未跟踪的A1文件。该SHA仅是基线，不能独立代表被验收实现。主代理本轮未修改业务代码/迁移/正式测试，未commit/push；只新增验收材料和本地独立探针。

## 1. 实测结果

环境：Python3.14.7、psycopg3.2.13、PostgreSQL16.15。本次未跑远程GitHub CI或Python3.11环境，不能声称两者已验证。

测试使用主代理新建的独立临时PostgreSQL实例：`agent-guard-a1-review-20260930`，127.0.0.1:55439，tmpfs，一次性凭据；运行结束已停止并自动删除。没有清理或迁移原有 `agent-guard-test-pg` 实例，避免现有测试中的清库逻辑影响已有数据。执行时显式移除了 `AGENT_GUARD_DATABASE_URL`。

| 检查 | 结果 |
| --- | --- |
| `python -m ruff check .` | 通过 |
| `python -m ruff format --check .` | 25个文件已格式化 |
| `pytest tests/unit tests/test_scaffold.py tests/test_docs.py -q` | 49 passed（46个unit＋3个既有骨架/文档测试） |
| `pytest tests/integration -q` | 52 passed，9.33s，0 skipped |
| 主代理独立契约探针 | 4 failed，均为应拒绝但未拒绝 |

证据在本地忽略目录 `artifacts/A1/review-20260930/`：

- `unit.xml`：49项结果。
- `integration.xml`：52项真实数据库结果，含现有P3/P5/P6各10轮及P9锁等待、P12回滚。
- `test_missing_invariants.py`：4项附加探针源码。
- `additional-probes.xml`：4项失败的断言和位置（连接串repr已脱敏）。

复验探针需新建独占测试实例及 `ag_review_probe` 库，设置测试DSN后执行 `pytest artifacts/A1/review-20260930/test_missing_invariants.py -q`。不能指向已有业务库；修复agent应将这些情形改写到安全隔离的正式回归测试，而不是只依赖本地artifacts。

## 2. 必须修复事项

### F1：数据库测试缺少隔离保护（高，开发数据安全）

位置：`tests/fixtures/dbstate.py:18–22`、`tests/integration/conftest.py:26–56`、`tests/integration/test_migrations.py:22–41,117–125`。

当前reset_state对调用方DSN直接执行固定表的 `TRUNCATE ... CASCADE`；迁移测试先无条件删除固定名 `agent_guard_test_migrate` 库。测试入口没有验证目标归属。CLI测试首次调用前未清除 `AGENT_GUARD_DATABASE_URL`，而迁移器优先读取该变量，因此可能迁移无关数据库。README第116行“该变量A1不消费”也与迁移器实现不符。

这些风险来自静态代码证据；本轮没有向已有库实施破坏性验证。

修复要求：

- 在迁移/清理前验证隔离目标，采用本轮独占schema或数据库及明确所有权记录，不仅靠环境变量名称或库名前缀猜安全。
- 不先DROP未知归属的固定库；为测试生成随机名称，只清理本轮成功创建的资源。至少保证两个测试会话互不清理对方状态。
- 使用psycopg连接参数解析/重建DSN，替换 `rsplit("/", 1)`，保留合法连接选项。
- CLI测试在首次调用前清除生产/普通DSN变量，再设置本轮scratch连接；对应README如实说明优先级。
- 增加“错误目标立即拒绝且不执行迁移/清空”“既有同名资源不删除”“普通DSN不会外溢”的回归测试。CI使用同样安全入口。

### F2：永久唯一根没有数据库级兜底（高，持久化不变量）

位置：`migrations/001_init.sql:17–23,42–72,100–102`；接受时检查见 `src/agent_guard/ledger/service.py:149–153`。

独立实测：同tenant/task直接插入第二个根未被约束拒绝；将 `ag_tasks.root_grant_id` 改为不存在的ID也成功执行。现有provisioning API有锁和重复初始化保护，其并发测试确实通过；但没有任务根映射不可变约束或同任务根节点唯一索引，不能满足任务要求的数据库不变量。

这是可信存储/维护路径防误写缺口，**不是已存在公网改库入口，也不等于需要抵抗DB超级用户主动破坏**。

修复要求：新增迁移（不得修改已应用的001）增加根节点部分唯一索引、任务身份与根映射不可变约束，以及跨任务/非根/不存在的根关联校验。明确业务角色禁止删除重建任务根；必要约束使用可延迟机制兼容现有创建顺序。升级前检查已有非法数据，发现问题应报错，不自动删除或清零。

回归需覆盖：绕过provisioning的普通SQL误写被DB拒绝、双code并发初始化、撤销/过期后不重建、001→新版本升级且旧账本不变。原P13对 `['001']` 的硬编码断言需同步到新迁移版本，不能只验证全新库。

### F3：VerifiedInvocation.subject未核对（中，可信接口契约）

位置：`src/agent_guard/ledger/service.py:256–278,295–300`。

独立实测：只把subject换成另一用户，其余授权定位/holder有效，accept仍成功创建预留。输入虽是受信进程内对象，A1任务明确要求与DB主体快照一致；这项防错检查仍应存在，不宣称当前有外部身份伪造漏洞。

修复：锁后路径检查核对全部授权节点subject与context一致，不符INVALID_CONTEXT。新增首次接受及同键重试的负例，验证proof/操作/账本/事件无残留。

### F4：calls未强制等于1（中，计费语义）

位置：`src/agent_guard/ledger/validation.py:125–126`、`migrations/001_init.sql:117`。

独立实测：`TrustedCost(calls=2)`被接受，一次操作预留了两次额度。当前不是少扣绕过，而是违反“每新操作固定计一次”的契约。

修复：保持bool/浮点/越界检查，再要求calls==1，否则INVALID_COST；操作表通过新迁移增加相应CHECK。测试0、2、大值、bool和正常1，并确认EXISTING不额外扣次数。

### F5：数据库连接等待未显式有界（中，失败关闭的可用性）

位置：`src/agent_guard/ledger/service.py:82–93,125–133`。

`psycopg.connect`未显式指定connect_timeout。后续SQL的lock/statement timeout只能约束建连之后的阶段。此项为静态发现，本轮未进行网络黑洞试验。

修复：配置有限正数connect_timeout并映射连接失败；校验lock_timeout、statement_timeout和max_retries范围，避免0关闭超时或非法值导致不执行请求。至少用连接工厂替身验证参数传递/异常映射，不能因这项测试声称真实网络黑洞实验已完成。

## 3. 已确认做好的部分

- `_require_str`现已正确接受错误码参数，报价字段错误归为INVALID_COST；上次单测失败已消除。
- P3/P5/P6确实使用独立连接、线程barrier并重复10轮，不是顺序循环冒充并发。
- 主路径使用DB父子链、根至叶预算、锁后clock_timestamp，EXISTING不重计预算，proof登记早于幂等返回。
- P9有真实持锁等待；P12有真实事务中途异常及CHECK失败后的全量回滚检查。其“连接丢失”一项是抛OperationalError的注入，不是实断网络连接。
- CI已增加PostgreSQL服务，但未提交，远程未运行；不能将本地通过写成GitHub checks已通过。

## 4. 下一轮修复顺序与记录要求

1. 先修F1测试隔离，再运行任何会清库的命令。
2. 修F3/F4并把两项负例加入正式测试；不要只改测试预期让错误行为过关。
3. 以新增迁移修F2，覆盖旧库升级和普通SQL约束测试。
4. 修F5的连接/配置边界；保留A1范围，不接OAuth或A2恢复。
5. 重跑全部既有测试、新增回归和并发10轮，更新报告的实际计数、命令及证据。修复增加测试后不再硬写49/52。

报告措辞修正：原49为46unit＋3骨架/文档；U1集成参数展开为17项而非14；P6应描述CREATED＋EXISTING，不是“一成功一拒绝”；保留真实时间及检查点决定，不引用已被覆盖而无法查到的记录。

READY_FOR_REVIEW只代表待审。各F项关闭后再交主代理复验，本轮不commit/push。建议下一agent只读本文、A1任务规范和涉及文件，避免重新研究整个项目。
