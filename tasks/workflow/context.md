# 当前上下文与迁移交接

配置日期：2026-10-01（Asia/Shanghai）。本文件恢复关键事实与来源，不宣布新的业务验收或实施授权。

## 已确认状态

- 项目：`/Users/qdcc/code/密码技术竞赛/agent-guard`。原 OpenCode 启动目录为其父目录 `/Users/qdcc/code/密码技术竞赛`。
- Git HEAD：`b120c7cf5ec0eafb18305d1207c36dd11655b324`。A1@main已验收；当前checkout `feat/a2-execution-gateway`，开工时仍须核对实际分支、HEAD、tracked及untracked，禁止reset或覆盖其他工作。
- `../A1-review-r4.md`：A1最终ACCEPTED，独立正式套件146＋额外探针5；数量是历史记录，不是未来固定门槛。后来main合并及CI记录以原主会话和真实Git结果为准。
- `../A2-review-ckpt1-r2.md`：检查点一补正复验ACCEPTED，取代首轮NOT_ACCEPTED，仅达到A2.1开工技术门槛。独立76 unit/骨架/文档及lint/format、Compose只读核对通过；78项A1 PG结果本轮只核对日志，没有独立重跑写库/旧容器清理全过程。不能把这些设计放行当实现验收。
- A2.1主体未开始；执行器、004、恢复、下游持久化及outbox行为均须实施并独立验证。
- `../A2-report.md` 状态仍是“等待复验”，102行仍有已跟踪清单笔误；已通过r2复验是当前事实，旧报告不得倒退任务。下一实施轮纠正报告，不以记录笔误无谓阻止已允许的核心方案。

## 切换前工作区（仅作索引，启动时重核对）

已跟踪修改：`src/agent_guard/contracts/__init__.py`新增42行。

未跟踪既有工作：`compose.a2.test.yaml`、`src/agent_guard/contracts/execution.py`、`tests/unit/test_execution_contracts.py`、`tasks/A2-execution-gateway.md`、`tasks/A2-report.md`、`tasks/A2-review-ckpt1.md`、`tasks/A2-review-ckpt1-r2.md`。这些是既有实施/验收输入，不可当成可丢弃的新文件。另新增本次工作流文件时，区分控制配置与业务变更。

## 必须继承的要求

读取原A2任务全篇和r2复验六条主体义务，不能只读本摘要：

1. 候选成本入口不依赖当前报价存在；miss后资源/报价解析失败须安全重查；命中仍过A1动态验权/proof/意图比较。
2. P11确定性并发：首次miss→另一调用accept提交→报价消失/解析失败→安全重查返回原操作，且新键、撤销、重放和变意图仍拒绝。
3. 可用候选完整接受事实持久化、异常旧行隔离；永久事件引用＋事件不可改删＋非级联FK防删须P20实测，否则004增加明确操作DELETE保护。
4. 租约终局写同时绑定owner、fencing version、合法状态和锁后数据库当前时刻下有效expiry；无接管者时过期旧worker也不能写；UNKNOWN恢复不释放未知预算。
5. 004使用sidecar保全旧七表、phase/seq CHECK及事件/节点UPDATE/DELETE保护；非法升级原数据与版本登记保持不变；合法计数/撤销/状态更新仍有效。
6. 执行与查询比对完整持久化快照；可能有效果但不一致保持UNKNOWN。outbox不可变，iat由持久created_at按UTC整数秒派生；普通JSON不冒充RFC8785/SM3，缺B保持PENDING。

## B与其他边界

- 最新已知远程跟踪 B 分支 `origin/feature/fjr-B-character` 为 `77e3570`，基础SM2/SM3、严格编码和Compact JWS已有代码但未完整验收。此为既有复验记录，不等于配置时重新fetch或验收B。
- 完整invoke/result-read验证器、scope/ag_constraints与grant/token/祖先的可信绑定、证据接口、回执签验/向量仍未全部确认；A2.2/2.3需要单独依赖核查与人审批。
- A2.1不合并、复制、修改或引入B代码/运行依赖来绕过接口；不修改001—003，不重写A1，不加生产假验权/假密码。必要共享契约仅按任务的兼容范围扩展。
- 不commit/push/PR/合并/改保护、不清理无关容器/共享库。实现和独立review分别使用明确归属的隔离资源。
- 缺B时P15仅参数/资源分层；P16/17真实验签、P18真回执、P21真实HTTP闭环保持后续门槛，完整A2始终PARTIAL。

## 历史会话索引

| 用途 | OpenCode session ID |
| --- | --- |
| 原Orchestrator规划/验收主线 | `ses_f0e893afcffeMRWvuS4UsK3x20` |
| 原Go-Main实施主线 | `ses_f124bb894ffeZBhtfwIl4Zb3Si` |
| 检查点一独立review及补正复验 | `ses_f0d49fcdcffejlzhvBPQ5aT02N` |

只把历史task/session ID当参考，不在新Task调用中续用。原会话和所有原agent保持。新流程需从原Orchestrator分叉，并用本Markdown向全新的MiMo子会话传递实施事实。

## 当前下一步

**等待用户批准 A2.1-core。** 配置请求仅授权配置工作流。批准后先核对实际工作区与源文件、冻结任务包/需求清单并审任务包，再完成核心主体及独立详细复核、补正、再复核。核心通过后必须停下来给用户查看和审批，不进入A2.2。
