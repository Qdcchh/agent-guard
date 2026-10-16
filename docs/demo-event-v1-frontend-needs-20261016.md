# DemoEvent v1：前端对接需求（A 提给 B，由 B 定稿）

日期：2026-10-16（同日补充场景 2/4/5/7 与门限所需的参与方和事件）。本文是 A 的需求清单，不是已实现接口。共同契约由 B 编辑定稿，A、C 审阅；B 改动任何名称后告诉 A，前端按定稿调整。

## 1. 分工文件已经够用的部分

《三人协作实施计划》已经给出事件字段骨架：`schema_version, run_id, scenario_id, seq, event_id, cause_id, source, actor, target, stage, event_type, status, reason_code, observed_at, monotonic_ms, safe_payload, evidence_ref`，以及 `source`（live / replay / illustrative）、`status` 七种取值、`after_seq` 轮询和 `safe_payload` 白名单原则。这些保持不变。

还缺三样，否则两边会各自猜：读取接口的具体形状、各字段的取值词表、每类事件的 `safe_payload` 内容。下面补齐，并按测试代码列出场景 1、3、6 的最小事件序列。

## 2. 读取接口（建议）

```
GET /api/runs/{run_id}/events?after_seq=0&limit=200
→ 200 {
  "schema_version": 1,
  "run_id": "...",
  "scenario_id": "stolen-token",
  "source": "live",            // 或 replay
  "events": [ ... ],           // 按 seq 升序
  "next_after_seq": 17,
  "terminal": false,           // 终局事件已持久化后才为 true
  "complete": true             // false 表示采集有缺口，前端显示"轨迹不完整"
}
```

- `run_id` 从 `/api/state` 的 `job` 中取，请在 job 里加 `run_id`。
- 未知 run_id 返回 404；只读、无副作用；沿用现有 Host/Origin 校验。
- 回放必须读取保存下来的真实事件文件。历史运行没有事件记录的，返回 `events: []` 且 `complete: false`，前端只显示原有摘要。
- 轮询间隔前端取 0.5–1 秒。

## 3. 取值词表

**actor / target（固定 ID，前端据此定位泳道）**

`user, planner, selector, executor, attacker, as, gateway, ledger, downstream, audit, verifier`；
场景 4 用 `executor-2` 表示第二条委托链上的执行方；场景 7 用 `worker`（原执行进程）与 `recovery`（恢复进程）；
预留 `coordinator, signer-1, signer-2, signer-3`（门限）、`x402`、`model`（以后接真实大模型）。

**event_type**

| 类型 | 含义 |
|---|---|
| `fixture.setup` | 测试前置动作，例如"测试取得 executor 令牌副本"。前端会标为测试注入，不画成协议消息 |
| `token.issued` | AS 签发令牌（根或子） |
| `delegation.requested` / `delegation.issued` / `delegation.rejected` | Token Exchange 申请、签发、拒绝 |
| `request.sent` | 某方向网关或 AS 发出请求 |
| `check.passed` / `check.rejected` | 某项检查的实际结果，检查名见下 |
| `lock.waiting` | 接受事务正在等待另一事务的锁（场景 6 用） |
| `revocation.committed` | 撤销事务已提交 |
| `accept.committed` / `accept.rejected` | 接受事务提交或拒绝 |
| `process.crashed` | 执行进程中断（场景 7），status 用 failed |
| `operation.reconciled` | 恢复进程对账确认并结算 |
| `receipt.published` | 签名回执进入待发布队列 |
| `readback.state` | 运行后读回预算与下游状态 |
| `run.terminal` / `run.error` | 本轮结束 / 程序失败（不同于"拒绝请求"） |
| 预留：`threshold.share_signed`、`threshold.aggregated`、`threshold.verified`、`intent.proposed` | 门限签名与真实模型 |

**检查名 `safe_payload.check`**

`token_signature`（SM2 验签）、`holder_binding`（ag_cnf 与 AG-Proof 签名者）、`request_binding`（token_sm3 / body_sm3）、`freshness`（jti、时效）、`ancestor_state`（撤销、过期）、`budget`、`delegation_narrowing`（需带 `dimension`：amount / calls / ttl / depth / scope / audience / recipient / resource）。

如果网关内部某项检查无法单独观测，就不要发它的 `check.*` 事件；前端会把它画成"讲解"而不是"事件"。只发实际拿得到的结果。

## 4. safe_payload 白名单（按事件类型）

| 事件 | 需要的字段 |
|---|---|
| `token.issued` / `delegation.issued` | `grant_alias`（如 root / mid / leaf）、`parent_alias`、`holder`、`holder_kid`（如 `executor#key-1`）、`limits: {amount_fen, calls}`、`scope`（工具名列表）、`expires_in` |
| `delegation.requested` | 上一行字段的"父授权值"与"申请值"并排：`parent_limits`、`requested_limits`、`parent_scope`、`requested_scope` |
| `request.sent` | `endpoint`（如 `/v1/invocations`）、`token_holder`、`proof_signer_kid`、`tool_id`、`body_sm3_prefix`（前 8 位即可） |
| `check.*` | `check`、`dimension`（可选）、`expected`、`observed`（都用公开别名） |
| `*.rejected` | `http_status`、`reason_code`（实际返回值） |
| `revocation.committed` | `grant_alias`、`txn_ref`（脱敏） |
| `lock.waiting` | `waiting_on`（对应事件的 event_id） |
| `accept.committed` | `operation`（别名）、`reserved_fen`、`levels`；同幂等键返回已有操作时 `existing: true` |
| `check.rejected`（budget） | `limit_fen`、`reserved_fen`、`requested_fen` |
| `process.crashed` | `signal`、`after`（如 downstream_commit） |
| `operation.reconciled` | `operation`、`settled_fen` |
| `threshold.*` | `share`（份额序号）、`shares`（已到份额列表）、`threshold`、`total`；不得含任何份额或私钥材料 |
| `readback.state` | `budget_before` / `budget_after`（每级 `{reserved_fen, settled_fen, calls}`）、`orders_before` / `orders_after`、`notifications_before` / `notifications_after`；可选 `grants_before` / `grants_after`（授权树节点数）、`operations_before` / `operations_after` |

禁止出现：完整 token、AG-Proof 原文、私钥、口令、Cookie、数据库连接串、本机绝对路径、原始日志。

## 5. 三个重点场景的最小事件序列（依据现有测试代码）

**场景 1 stolen-token（`test_attack_set_exact_binding_no_side_effects[stolen-0]`）**
测试用 planner 的密钥、kid 和 client_id 签 AG-Proof，配上 executor 的令牌发往网关。

1. `fixture.setup`：测试取得 executor 令牌，`proof_signer_kid = planner#…`
2. `request.sent`：attacker → gateway，`token_holder = executor`，`proof_signer_kid = planner#…`
3. `check.passed token_signature`（如果可观测）
4. `check.rejected holder_binding`，带实际 `http_status` 与 `reason_code`
5. `readback.state`：前后预算、订单、通知均不变
6. `run.terminal`

**场景 3 delegation-scope（`test_browser_root_and_two_delegations_real_https[amount-0]` 与 `[scope-0]`）**
测试先做一次合法交换（200），再用扩权参数申请：amount 用例把 `ag_amount_limit_fen` 设为 `100001`，scope 用例在 scope 中追加 `unauthorized.tool`；AS 返回 400，业务状态不变。

1. `delegation.requested` + `delegation.issued`：合法收窄正例
2. `delegation.requested`：带父值与申请值（金额或 scope）
3. `delegation.rejected`：actor = as，`dimension` 指明超出的维度，实际 `reason_code`
4. `readback.state`：业务状态不变
5. `run.terminal`

网关没有收到请求，不发任何网关事件，前端画成"未发生"。金额请用实际观测值，前端不会再用 800/900 这类讲解示例冒充。

**场景 6 revocation（`test_root_mid_calls_revocation_final_clock_races[revoke-first-0]`）**
测试先在一个事务里对根授权执行撤销但暂不提交；接受请求发出后确实在等这把锁（`pg_blocking_pids` 可见），然后撤销提交，接受返回 401 或 403，三级计数全为 0。

1. `request.sent`：executor → gateway
2. `lock.waiting`：接受事务在等撤销事务，`waiting_on` 指向撤销事务
3. `revocation.committed`：`grant_alias = root`
4. `accept.rejected`：`cause_id` 指向上一条，带实际状态码与原因
5. `readback.state`：三级预算与下游均为 0
6. `run.terminal`

注意：测试中的撤销是直接提交撤销事务，不是通过用户点击撤销接口。前端会如实标注"撤销根授权（测试直接提交撤销事务）"。

## 6. 前端的承诺

- 只按 `seq` 排序、按 `event_id` 去重；发现序号缺口时等待补拉，超时则提示缺口。
- 不用计时器生成任何结果；断线时停住并提示，不会继续画成功。
- 收到不认识的 `event_type` 时显示为"未识别事件"，不静默丢弃。
- 现场、回放、示意三种来源在页面上醒目区分。
