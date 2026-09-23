# 协议 v1 草案

状态：设计契约，尚未实现。下述接口为目标接口，不表示已有服务。冻结未决密码参数并通过测试前不得签发正式凭证。

## 1. 编码与密码配置

- 结构化消息拟采用 RFC 8785 JSON 规范编码后进行 UTF-8 编码。实现须先检查原始 JSON，拒绝重复字段，再做模式校验和规范化。
- 拒绝未知字段、缺失必需字段、浮点金额、布尔型整数、负额度、越界整数和不明确类型。所有整数限定在 0 至 2^53-1；字段可进一步收紧。
- 标识符限制为 ASCII，时间为 UTC Unix 整数秒，二进制采用无填充 base64url；资源名称的展示文本不用于身份比较。
- 域分离消息：`AGENT-GUARD/v1/<domain>\n` 加规范化正文；domain 分别为 capability、invocation、receipt、checkpoint。签名字段本身不进入自身签名正文。
- SM2 对上述完整消息签名，SM3 用于链、意图及证据摘要；不得自行用“对摘要再签名”的替代路线改变库的 SM2 消息处理语义。
- 凭证摘要覆盖完整签名信封，链摘要覆盖按根至叶排序的凭证摘要数组，两者另用独立 hash 域前缀。
- 待 B 冻结：SM2 库、标准曲线参数、用户标识、签名 DER 或固定 r/s 编码、公钥编码、base64url 严格校验、规范编码测试向量。冻结后不允许靠自动尝试多个格式验签。
- 公钥标识由可信注册表绑定到主体。不得信任凭证自带的任意公钥或由不可信 URL 获取信任根。密钥生成、轮换、撤销、销毁与泄露处置在实现阶段补充专门文档。

## 2. 授权凭证

签名信封为 `{"payload": ..., "signature": ...}`。payload 至少包含：

| 字段 | 类型与语义 |
| --- | --- |
| version | 固定字符串 `1` |
| capability_id | 授权唯一标识 |
| parent_digest | 根为 null；子为完整父凭证摘要 |
| issuer_key_id / holder_key_id | 签发者和持有者的可信公钥标识 |
| tenant_id / task_id | 租户、任务，后代必须相同 |
| audience | 目标工具执行服务标识，后代不得替换 |
| actions | 工具标识及语义版本的集合 |
| resources | 允许的资源 ID 集合，v1 不支持通配符 |
| constraints | 每工具的显式约束，拒绝任意脚本或策略表达式 |
| currency / amount_limit | 固定 CNY / 累计金额上限，整数分 |
| call_limit | 全部工具累计调用上限；读取也计数 |
| not_before / expires_at | 生效和失效秒数，左闭右开 |
| delegation_remaining | 可继续委托的层数 |

根由可信授权服务基于用户确认或可信业务策略签发；子由父 holder 签发给另一已注册 holder。根可设 delegation_remaining=2，第一层最多为1，第二层为0；至少实现三个代理身份。

逐层检查签名、父摘要、签发者等于父 holder、租户/任务/audience 一致。工具、资源、模板、接收方、收货对象等集合只能取子集；数量上限、金额、次数只能不增；时间区间只能包含于父区间；剩余深度最多为父减一。报价版本须在允许范围内。验证整条链，不只验证末端。

子额度是共享上限，不是签发时分配的独占资金。父节点被自身或任何后代使用时均累加其账本，所有路径共同受根限制。授权注册必须检查 ID 唯一；相同 ID 对应不同摘要必须拒绝。

## 3. 调用请求与验权结果

`InvocationRequest` 包含根至叶的 `capability_chain`、请求正文及末端 holder 签名。正文必需字段：version、tenant_id、task_id、audience、chain_digest、tool_id、tool_version、完整 params、request_id、nonce、issued_at、expires_at、idempotency_key。

签名覆盖整个正文。任务、服务及 holder 必须与授权链匹配。nonce 每次外部请求重新生成；幂等键在同一业务操作重试时保持不变。时间窗口及允许时钟偏差在部署配置中固定、记录并测试，不接受调用方任意放宽。

拟内部接口：

```text
verify_invocation(request) -> VerifiedContext
accept_operation(verified_context) -> OperationRecord
recover_operation(operation_id) -> OperationRecord
verify_evidence(package, trusted_checkpoint) -> VerificationReport
```

VerifiedContext 保存已验证链、主体、规范参数及摘要，但不是可转移授权，不向代理暴露为跳过验权的凭据。接受事务重新检查当前撤销、有效期、全部适用额度和请求状态。

## 4. 工具参数

所有参数仅接受显式白名单，禁止额外字段。租户和任务从已验证上下文获取，不由工具重新信任 params 中的声明。

| tool_id（tool_version 固定为 1） | params | 约束 |
| --- | --- | --- |
| procurement.request.read | request_id | 申请在资源集合内且属于该租户与任务 |
| procurement.document.read | request_id, document_id | 文档与该申请具有关联，不允许任意 URL 或路径 |
| procurement.order.create | request_id, quote_id, quote_version, items[{sku, quantity}], delivery_id | 正整数数量、批准商品/供应商/收货对象、可信报价；服务端计算总金额 |
| notification.template.send | template_id, recipient_id, operation_id | 固定模板和批准接收方；关联同租户任务的可访问操作；参数不得变成任意消息载荷 |

报价内容中用于模型阅读的自然语言不作为可信价格依据。接受时确定报价快照及金额，下游使用相同不可变快照进行校验；报价不可用或版本不匹配则拒绝。只读和通知金额成本为0，调用次数成本为1。

## 5. 业务幂等与结果读取

- 外部业务键作用域为 `(tenant_id, task_id, tool_id, idempotency_key)`，数据库唯一约束保证一次接受。
- 首次接受绑定链摘要、holder、工具版本及规范业务参数的意图摘要；同键不同意图、链或 holder 拒绝。nonce、request_id 和新鲜性时间不计入业务意图摘要。
- 同键同意图重试必须先完成当前验权；若已存在则返回原操作状态，不再次预留或扣费。不能因已结算而再次要求“新操作所需余额”。
- 完全重放的 nonce 拒绝；真正重试使用新 nonce。nonce 按 holder 和服务标识唯一记录，在覆盖全部有效请求窗口后才允许清理。
- 结果读取使用独立域 `result-read` 的 holder 签名，覆盖当前授权链摘要、operation_id、nonce 和时间，并重验当前任务/资源/主体权限与撤销；读取不创建业务操作、不再次扣业务次数。与其他请求共享新鲜性与抗重放规则。
- v1 仅允许原 holder 和原授权链读取原操作；根撤销后外部读取拒绝。管理员审计通道独立授权，不复用代理凭据。

## 6. 计划中的 HTTP 接口

| 接口 | 用途 |
| --- | --- |
| POST /v1/authorizations/root | 可信用户/业务入口创建根授权；普通代理不可调用 |
| POST /v1/authorizations/delegations | 注册已签名子委托，检查链与 ID 唯一性 |
| POST /v1/revocations | 可信授权管理主体撤销指定授权及其后代 |
| POST /v1/invocations | 提交 holder 签名调用，返回操作 ID 和状态 |
| POST /v1/operations/query | 签名结果读取请求，避免把凭证放在 URL |

授权管理接口需要独立主体认证，具体认证适配在实现前冻结，不默认信任调用方传入的角色。撤销目标的租户与管理权限必须验证。

错误统一为 `{"error":{"code":"...","request_id":"..."}}`，响应不泄露密钥、内部凭证、其他租户资源或具体越权对象。

| HTTP | 错误码 |
| --- | --- |
| 400 | INVALID_ENCODING, INVALID_SCHEMA |
| 401 | INVALID_SIGNATURE, HOLDER_MISMATCH, STALE_REQUEST |
| 403 | SCOPE_DENIED, DELEGATION_DENIED, REVOKED, EXPIRED |
| 409 | REPLAY, IDEMPOTENCY_CONFLICT, QUOTE_CONFLICT |
| 422 | BUDGET_EXCEEDED, CALL_LIMIT_EXCEEDED |
| 503 | TRUSTED_STATE_UNAVAILABLE |

接受前状态库不可用必须失败关闭。接受后下游超时返回已有操作的 UNKNOWN 状态，不伪装为确定失败。接受成功可返回202，已完成操作可返回200；最终回执与操作状态区分。

## 7. 回执与检查点

最终回执正文至少绑定 receipt_id、operation_id、tenant/task、链摘要、意图摘要、工具及版本、最终状态、预算变动摘要、下游结果摘要和时间，由执行服务密钥签名。暂态查询结果不当作最终回执。

证据记录带连续序号、前记录摘要，独立审计端保存并签署检查点（序号、链头摘要、前检查点摘要、签署时间）。审计端独立凭据与持久化域，不接受任意回退检查点。

离线验证器需要独立获得的可信检查点或其最低序号，不能只相信证据包内自带的旧检查点，否则无法区分合法旧快照与回滚。证据包提供规范参数/结果摘要所需的合成数据、签名和公钥绑定材料。实际敏感载荷需采用独立受控存储或脱敏导出，日志不记录明文密钥。

## 8. 冻结前必须解决

密码库与所有编码参数；时间窗口及偏差；最大链长、请求与证据大小；根和管理主体认证；公钥注册与轮换；每工具 constraints 的机器模式。任何未决项不得用默认放行实现。
