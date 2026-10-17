# DemoEvent v1：角色 B 后端交接契约（2026-10-16）

本接口给本机老师演示页展示固定安全场景的**测试观测**。当前仅覆盖场景 1（盗令牌 `stolen-token`）、3（委托扩权 `delegation-scope`）和 6（撤销 `revocation`）。事件来自实际运行的集成测试断言及数据库状态读回，不代表生产服务已有通用事件总线。其余场景仍使用原有结果摘要。

## 启动与读取

在仓库根目录启动 `python tools/teacher_demo_server.py`，仅监听 `127.0.0.1:8765`。沿用现有固定动作接口：`POST /api/scenarios/{scenario_id}/run` 或 `/replay`，请求体必须是 `{}`，并遵守演示页的同源会话令牌要求。`GET /api/state` 的 `job.run_id` 是事件运行 ID；成功或失败后同一服务进程内仍可按此 ID 查询。

`GET /api/runs/{run_id}/events?after_seq=0&limit=200` 返回一页。`run_id` 为小写标准 UUID；`after_seq` 为非负整数，`limit` 为 1–200。前端轮询时把上页的 `next_after_seq` 作为下一次 `after_seq`；事件的 `seq` 从 1 连续递增。格式合法但未知的运行 ID 返回 404；`run_id` 格式错误或不是规范小写 UUID 返回 400。查询参数语法错误返回 400；游标/条数范围在找到运行后校验，已知运行越界返回 400，未知运行仍优先返回 404。服务重启后不恢复运行索引；历史回放须重新发起 `/replay` 才会建立新的查询索引。

响应字段：`schema_version`（固定 1）、`run_id`、`scenario_id`、`source`（`live` 或 `replay`）、`events`、`next_after_seq`、`terminal`、`complete`。事件字段：`schema_version`、`run_id`、`scenario_id`、`seq`、`event_id`、`cause_id`、`source`、`actor`、`target`、`stage`、`event_type`、`status`、`reason_code`、`observed_at`（UTC ISO 8601）、`monotonic_ms`、`safe_payload`、`evidence_ref`。前端应以 `event_type` 和 `safe_payload` 渲染，不解析原始日志。

当前实际输出的 `actor` / `target` 只会使用 `attacker`、`planner`、`selector`、`executor`、`as`、`gateway`、`ledger`、`verifier`、`user`；`status` 只会使用 `in_progress`、`waiting`、`passed`、`rejected`、`failed`。`source` 没有 `illustrative` 值；示意内容若由前端提供，必须与本接口返回的观测分开。事件只输出下表中的类型，原需求提到但未独立观测的 `token.issued`、`check.*`、`accept.committed`、门限/x402/模型事件均未实现。

| 事件类型 | actor → target | status | `safe_payload` 字段 |
| --- | --- | --- | --- |
| `fixture.setup` | attacker → attacker | passed | `token_holder`, `proof_signer_kid` |
| `request.sent` | attacker 或 executor → gateway | in_progress | `endpoint`, `token_holder`, `proof_signer_kid`, `tool_id` |
| `delegation.requested` | planner → as | in_progress | `parent_limits`, `requested_limits`, `parent_scope`, `requested_scope` |
| `delegation.issued` | as → selector | passed | `grant_alias`, `parent_alias`, `holder`, `holder_kid`, `limits`, `scope`, `expires_in`, `http_status` |
| `delegation.rejected` | as → planner | rejected | `dimension`, `http_status`；实际错误码在顶层 `reason_code` |
| `lock.waiting` | gateway → ledger | waiting | `waiting_on`，与随后撤销事件的 `event_id` 对应 |
| `revocation.committed` | ledger → gateway | passed | `grant_alias`, `txn_ref` |
| `accept.rejected` | gateway → attacker 或 executor | rejected | `http_status`；实际错误码在顶层 `reason_code` |
| `readback.state` | ledger → user | passed | `budget_before`, `budget_after`, `orders_before`, `orders_after`, `notifications_before`, `notifications_after` |
| `run.terminal` / `run.error` | verifier → user | passed / failed | 空对象 `{}` |

`limits` 是 `{amount_fen, calls}`；预算列表按根、中、叶三级排列，每项是 `{reserved_fen, settled_fen, calls}`。金额均为非负整数分，布尔值不作整数接受。`scope` 是固定工具名列表；`grant_alias` 仅是 `root` / `mid` 等公开别名。委托签发见证里的 `holder_kid` 使用 `selector#key-1`，盗令牌见证里的 `proof_signer_kid` 使用固定的公开 DID key ID；二者均经白名单校验。字段只按对应事件出现，前端不能假定每条事件都有所有字段。

## 事件顺序与语义

| 场景 | 按序出现的事件 |
| --- | --- |
| `stolen-token` | `fixture.setup`、`request.sent`、`accept.rejected`、`readback.state` |
| `delegation-scope` | 金额例和工具范围例各出现 `delegation.requested`、`delegation.issued`、`delegation.requested`、`delegation.rejected`、`readback.state` |
| `revocation` | `request.sent`、`lock.waiting`、`revocation.committed`、`accept.rejected`、`readback.state` |

每个实际通过的场景在原生进程退出、JUnit 用例集合及清理结果核对后追加 `run.terminal`，此时 `terminal:true, complete:true`。运行异常时追加 `run.error`，返回 `terminal:true, complete:false`；这不是一次预期的安全拒绝。运行中可以出现已完成用例的有序前缀，`terminal:false, complete:false`。旧历史材料若没有事件文件，回放返回空 `events`、`terminal:false, complete:false`，不得补画预期事件。`source:replay` 只说明读取已保存的观测，绝不表示重新发送了请求。

`cause_id` 仅用于已有观测的请求/拒绝或撤销/拒绝关联。`evidence_ref` 指向测试用例别名，不是可公开下载的原始日志。当前没有单独观察到的内部 `check.*` 事件；画面可解释安全检查，但不能将解释当作实时事件。`request.sent.safe_payload` 当前不含可选的 `body_sm3_prefix`。

事件文件保存在对应 `artifacts/teacher-scenarios-live/{run_id}/demo-events-v1.json`，由测试见证投影生成，仅含白名单字段、固定工具/身份别名及聚合计数。文件和事件数均有上限。原始 token、私钥、proof、任意请求正文、数据库连接及原始日志不会经该接口返回。此本机演示接口不应直接发布公网。

## 本机实跑样例

下列片段来自 2026-10-16 的保存文件，省略了每条事件共有的 ID、序号、时间与证据引用。完整字段仍按上面的契约读取。

| 运行与事件 | 实际公开字段 | 含义 |
| --- | --- | --- |
| 场景 3 run `00784e31-e17d-457d-ad83-461e3bebccd4` 的 `delegation.issued` | `as → selector`、`passed`、`http_status:200`、`holder_kid:"selector#key-1"`、`limits:{amount_fen:80000,calls:10}` | AS 实际签发合法收窄的中层授权；额度是约束值，不是已花金额 |
| 场景 1 run `6eafe574-995e-4462-a37d-db904a26fdce` 的 `accept.rejected` | `gateway → attacker`、`rejected`、`http_status:401`、`reason_code:"INVALID_SIGNATURE"` | 本轮网关的实际拒绝码；前端不应自行改写成未单独观测的内部检查事件 |
| 场景 6 run `e518e264-1989-4aad-9cb7-6f5a37132240` 的 `revocation.committed` | `ledger → gateway`、`passed`、`grant_alias:"root"`、`txn_ref:"root-revocation"` | 测试同步屏障下撤销事务已提交，随后新接受被拒绝 |
| 修复前失败轮次 `8b5072ac-8f0c-4003-b7ae-8db1e585d5a2` 的 `run.error` | `verifier → user`、`failed`、`reason_code:"RUN_FAILED"`、`safe_payload:{}` | 当时事件投影不接受真实的 `selector#key-1` 别名；该轮始终是 `complete:false`，修复后另起新运行验证 |

场景 1、3、6 的上述成功轮次分别有 1、2、1 项原生 JUnit 用例，父进程退出码均为 0，`complete:true`，专属容器、网络和卷剩余均为 0。各拒绝用例的预算、订单与通知前后读回均相等。它们是本机代表场景的运行记录，仍不等于 A3.3/A3.4 最终联合验收。

## 联调边界

前端应区分“正在运行、成功结束、运行失败、旧材料无事件”四种状态；使用 `complete` 判断本次事件是否完整，不能只看 HTTP 200 或 `terminal`。角色 C 可根据场景 ID 和上述固定顺序编排讲解，但结论以返回的真实事件与原有场景测试结果为准。需要完整数据库、撤销、预算及副作用证据时，沿用现有集成测试和离线验证材料；本接口是有界展示投影，不是独立审计锚。
