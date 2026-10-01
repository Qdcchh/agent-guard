# A/B 联调契约与运行手册（B 侧维护）

状态：截至本文件，`origin/main` 为 `b120c7c`，只含 A1 账本；A 的 HTTP 网关、四工具、下游执行/恢复与 `/v1/evidence/export` 尚未出现，因此端到端联调未完成。本文列出已可独立验证的 B 侧接口/夹具，以及等待 A 提供的确切接口与字段。不把本文当作已实现能力。

## 1. 已就绪的 B 侧联调材料

| 组件 | 入口 | 用途 |
| --- | --- | --- |
| 静态验权 SDK | `agent_guard.authorization.verifier.InvocationVerifier.verify_static` | 校验 Access Token、AG-Proof、holder 绑定与工具参数，产出唯一可信的 `VerifiedInvocation` |
| 接受事务（A1，位于 main） | `agent_guard.ledger.service.ExecutionLedger.accept(verified, TrustedCost)` | 加锁、原子预算/幂等/重放决定；网关不得绕过 |
| 内省（网关照会） | `oauth/introspect` 适配层 / `IntrospectionService` | `active:true` 只是查询时点快照，不代替接受事务 |
| 固定互操作向量 | `tests/fixtures/interop.py`、`tests/test_interop_vectors.py` | TEST-ONLY 固定 SM2 密钥、SPKI/DER 与 SM3 摘要、根与两级子令牌、executor AG-Proof、三方路径 `AG-EVIDENCE-1` 包及负例 |
| 证据验证器 | `agent_guard.evidence.receipt.verify_receipt_bundle(bundle, trust=ReceiptTrust(...))` | 独立可信配置下的单笔未锚定证据校验 |
| 开发 AS（TLS） | `python -m agent_guard.server init/check/run` | 生成合成密钥/配置、校验、以 uvicorn 提供 HTTPS |
| 接缝集成测试 | `tests/integration/test_as_ledger_integration.py` | B 两级委托令牌 → B 验权 → A1 `accept`，含盗用/篡改/重放/撤销/预算/内省分离 |

固定向量的冻结值：每个密钥的 SPKI base64url 与 SM3 在 `tests/fixtures/interop.py` 的 `SPKI_B64`/`SPKI_SM3`；默认调用请求与约束的规范 SM3 为 `REQUEST_SM3`/`CONSTRAINTS_SM3`。签名随机化，因此令牌串不冻结，由固定私钥按模板现签。

## 2. 等待 A 提供的接口与字段

### 2.1 工具调用 `POST /v1/invocations`

- Headers：`Authorization: AGPoP <access_token>`、`AG-Proof: <proof_jws>`（type `ag-pop+jwt`，`purpose=invoke`，`htu` 为部署配置端点，禁止从 Host/X-Forwarded 推导）。
- Body 字段（严格、拒绝额外字段）：`profile="GM-MVP-1"`、`task_id`、`tool_id`、`tool_version="1"`、`idempotency_key`、`params`。
- 四工具 `params`：
  - `procurement.request.read`: `request_id`
  - `procurement.document.read`: `request_id`, `document_id`
  - `procurement.order.create`: `request_id`, `quote_id`, `quote_version`, `items[{sku,quantity}]`, `delivery_id`
  - `notification.template.send`: `template_id`, `recipient_id`, `operation_id`
- 接受流程：`verify_static` → `accept`；可信成本来自报价解析器（禁止代理申报金额）；返回 `202 {operation_id, status:"RESERVED", receipt_status:"PENDING"}`。
- 错误码按设计 9.6（400/401/403/409/422/503），不要泄露可信状态细节。

### 2.2 结果查询 `POST /v1/operations/query`

- 相同 AGPoP + AG-Proof，`purpose=result-read`；body `{profile, task_id, operation_id}`；返回 `{operation_id, status, receipt_status, result, receipt_jws}`；无终局回执时 `receipt_jws=null`，UNKNOWN 不得伪装 FAILED。

### 2.3 执行状态与恢复（安全模型第 5 节）

- 状态：`RESERVED→EXECUTING→SUCCEEDED|FAILED|UNKNOWN`；`UNKNOWN` 必须保留预留，只有查询/同键恢复确认后才转终态；`FAILED` 必须是持久化终局，不能以单次连接错误判定。
- 恢复通道不接收旧用户签名创建新意图，不增加工具/参数/金额；多恢复者使用租约或版本条件更新。

### 2.4 证据导出 `POST /v1/evidence/export`

- 仅预登记、具有审计角色的独立服务凭据（HTTPS）可调用；body `{task_id}`。
- 返回 `AG-EVIDENCE-1` 包，字段严格为：`manifest_version`、`anchoring_status`、`receipt_jws`、`ancestor_tokens`（根到叶，最后一项等于 `token_jws`）、`token_jws`、`proof_jws`、`request`（首次接受的规范调用对象）、`result`、`ledger_changes`。
- `receipt_jws` payload 字段：`profile, receipt_id, operation_id, tenant_id, task_id, root_grant_id, grant_id, token_sm3, proof_sm3, intent_sm3, tool_id, tool_version, status, amount_fen, result_sm3, ledger_sm3, iat`；`typ=ag-receipt+jwt`，独立网关签名 key。
- `ledger_changes={operation_id, events:[...]}`，事件含 `phase`（RESERVE/SETTLE/RELEASE）与根至叶 `nodes`，每节点含 `grant_id, amount_reserved_delta, amount_settled_delta, calls_reserved_delta, calls_settled_delta`；只允许这四个 delta 为有界负整数；`ledger_sm3=SM3(RFC8785(ledger_changes))`。
- 无独立检查点时 `anchoring_status` 必须为 `UNANCHORED`；不得自报 `ANCHORED`。
- A 生成网关回执 key（新 kid），向 B 独立提供 kid + SPKI 公钥；私钥只在网关。轮换用新 kid，旧公钥仅用于历史验签。

### 2.5 其他

- 证据暂存：`InvocationVerifier` 的 `stage_evidence(token, proof, body)` 必须把原始证据放入受访问控制存储并返回不透明 `evidence_ref`，不得指向客户端路径。
- 下游幂等：稳定 `operation_id` 由网关生成；首次接受固定的报价快照（quote_id/version/sku/数量/总额/摘要）贯穿执行与恢复；同键同意图返回同一效果，同键不同意图拒绝。
- 通知：固定模板与批准接收方，不开放任意 URL/脚本/转发。
- 企业/DID 登记：仍由 B 的 `IdentityResolver` 只读预登记快照；A 不得自建另一份信任来源。

## 3. 运行手册

```bash
# B 侧一次性准备（开发边界，目录必须私密）
python -m agent_guard.server init --out ../ag-as-dev
python -m agent_guard.server check --config ../ag-as-dev/config.json
# 开发自签证书
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=localhost \
  -keyout ../ag-as-dev/tls-key.pem -out ../ag-as-dev/tls-cert.pem
# 以 TLS 启动 AS（需要 PostgreSQL；禁用了代理头信任）
AGENT_GUARD_DATABASE_URL=postgresql://... python -m agent_guard.server run \
  --config ../ag-as-dev/config.json --ssl-certfile ../ag-as-dev/tls-cert.pem \
  --ssl-keyfile ../ag-as-dev/tls-key.pem

# 固定互操作向量（无数据库，A 可导入 fixtures.interop 复用）
python -m pytest tests/test_interop_vectors.py
# A 网关消费 B SDK 的接缝测试（真实 PostgreSQL）
python -m pytest tests/integration/test_as_ledger_integration.py
# 证据验证器（合成向量）
python -m pytest tests/test_receipt.py
```

## 4. 与验收矩阵的关系

已局部覆盖：M1 相关（登录/同意/换码）、M2（两级委托签发与收窄）、M3（DID/登记静态校验）、M4（盗用令牌无私钥失败，验权与接缝层）、M5 的静态部分（参数/令牌绑定、proof 防重放）、M8 的事务部分（撤销后拒绝）、SEC-01/02/05/06 的 SDK 与账本部分、AUD-02（UNANCHORED 局限）。仍未覆盖：A 侧 HTTP 网关与四工具的 HTTP 语义、M6/M7/M11/M12/M13 的端到端与恢复路径、M9 对 A 真实导出包的验证、M10 的干净部署演示。待 A 提供上述接口后按本文联调，再更新验收状态。
