# demo-fixes-20261017 独立实施验收

结论：**ACCEPTED（仅本轮有界小修复）**。未发现阻断回归；不代表用户原先报告的“期望 404、实得 400”已经复现并定位，也不改变全项目 PARTIAL 状态。

## 范围、独立性与冻结

- 新建 reviewer 会话 `/root/demo_fix_acceptance`；未实施生产改动、未调用子 agent、未运行 Git 命令。
- 本轮候选改动：`tools/teacher_demo_server.py`、`tests/test_teacher_demo_server.py`、`docs/teacher-demo-events-v1.md`。已有用户前端改动不属于本轮修复，完整保留。
- 主控声明实施者 STOP/native 0；读取 worker STOP/REPORT。按指定只写 `artifacts/demo-fixes-20261017/review/` 下探针、日志与报告。
- 开始与结束独立逐文件校验 manifest 的全部 **823** 文件，均零差异；manifest SHA-256 `75739dec834187fdd4b536227265eda03799519395964543761573c4388fd431`。冻结 status 文件前后相同，SHA-256 `dd369c13c355de7dcb4c7c05e869d825604c5f4e98e42b194fd161d2484f82d4`，列明三项修复文件及两项用户前端 dirty。遵从本轮禁止 Git 指令，未另外运行 Git status；用全部冻结文件内容散列核验保持不变，不冒称重采集 Git 状态。
- 证据：`freeze-start.json`、`freeze-end.json`。

## 本轮完整矩阵与结果

| 义务 | 方法与证据等级 | 结果 |
| --- | --- | --- |
| 事件接口/服务、事件分页、桌面边界整体回归 | 本轮独立实跑三个 unittest 模块，`unittest.log`、`unittest-result.json` | **29/29，0 failure/error/skip，native 0**；12 server + 7 events + 10 desktop |
| 固定合法未知 UUID、非法 UUID、查询边界 | 本轮独立启动真实本机 HTTP 服务，非替换 event_response；`http_probe.py`、`http-probe-results.json` | **12/12，native 0** |
| Host/Origin/token、公网只读、路径遍历、互斥及真实父 wait 约束不退化 | 上述正式回归断言及实现静态查证 | PASS；业务子进程为正式单元测试替身，未冒充真实采购 |
| 历史门限 503 记录及当前状态 | 独立核对历史失败、worker 最新真实结果、root 控制接口真实结果；`threshold-evidence-check.json` | 历史失败确为 503；两次当前结果均 **6/6**、批准首次/重试 **202**、operations/approvals/orders **1/1/1**、resources_remaining **[]** |
| 门限迁移/绑定一致性 | 本轮独立静态查证 lineage.py、binding.py、009 SQL、gateway/errors.py | 009 已登记且 checksum 与文件一致；审批 INSERT/SELECT 的 payment_digest 列存在；数据库错误映射 503 |
| 文档、原始失败解释、范围保护 | 静态查证事件接口文档、候选测试和实现；核对 worker 报告 | 当前契约准确；必须保留下述证据限制 |
| 资源与冻结 | 关闭本轮 HTTP 服务、join 服务线程；29 测试完成退出；起止 823 文件核验 | PASS；reviewer 无存活子进程/自建容器/数据库/网络资源 |

实跑命令：

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_teacher_demo_server tests.test_teacher_demo_events tests.test_desktop_server -v
PYTHONDONTWRITEBYTECODE=1 python3 artifacts/demo-fixes-20261017/review/http_probe.py
```

宿主 Python 版本以 `unittest-result.json` 实际记录为准。本次未安装依赖或声称重新验证 Python 3.11 干净安装。

## 两项问题的准确判断

### 门限有效批准 503

直接读取原始结果 `2fe7ae99-8db8-4260-95a6-12f31a278f85/result.json`：有效批准首次及重试 503、TRUSTED_STATE_UNAVAILABLE，三项业务计数 0；其余五例通过。worker 将原因定位为 x402 实施期间审批绑定先引用 payment_digest、009 迁移稍后才加入固定迁移清单的短暂不一致。该时间线为 worker 既有日志解释，本 reviewer 未另做长历史追索；独立静态核对确认当前三处已一致，且数据库异常映射能够解释该 503。原始数据库异常日志缺失，**UndefinedColumn 是合理推断，不能写成已观测原始异常**。

当前恢复状态有实际业务证据：worker 真实 CLI `66455c36-0d54-4245-822b-c6a14c7e1562` 与 root 运行中控制接口 `9982ea76-0998-4832-9eab-c65a6cea4548` 的原始结果均通过，root live-state 记录 native_exit 0、actual_wait true。本 reviewer 复用并核对这些真实证据，**未第三次重跑门限、未连接共享数据库**。本轮无门限源码变动；现有实现已经包含此前修复。

### 期望 404、实得 400

用户原报告本轮**未复现，不能宣称原失败根因已定位/修复**。本轮 29 项回归全通过，独立固定未知标准 UUID `22222222-2222-4222-8222-222222222222` 实际 HTTP 返回 404。

此次源码修复的是另一项、方向相反的边界：旧路由只接收 `[0-9a-f-]{36}`，部分非法 ID 提前落到 404；现改为捕获单一路径段，再统一经 UUID 解析和规范小写比较，使 `not-a-uuid`、35 位、非 hex 36 位、大写 UUID 返回 400。正式测试原有合法未知 UUID →404 断言保留，新加四种非法输入断言。本轮实际 HTTP 逐项通过。

worker REPORT 的任务2标题“已复现并修复”仅适用于上述新发现边界，**不适用于用户原报告**。此处作证据口径澄清，不据措辞作额外阻断。

现有查询优先级已核实且文档一致：未知合法 UUID + 数值范围越界仍 404；未知合法 UUID + 无法解析的数值或重复参数返回 400；已知运行无事件文件返回 200 空页，范围越界返回 400。探针覆盖这些组合。

## 未执行及停止

未重跑 x402、完整 PG、安全长实验或整个仓库测试；本轮只涉及事件路由小改动，门限真实证据已有主控新运行及 worker 独立运行，未将这些既有结果冒充 reviewer 本轮独立实跑。未访问共享 55432 或外部容器，未改源码/用户前端/历史证据，未提交推送。HTTP 探针资源已关闭，单元测试父进程已真实退出。完成报告与 STOP 后停止写入；主控可在正式读取验收后重启桌面服务加载修复。
