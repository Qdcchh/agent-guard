# GM-MVP-1 密码与编码配置

状态：SM2/SM3 与 Compact JWS 基础 SDK、部分业务 claims 模式、DID只读解析、静态调用验权、委托收窄策略及ID Token/PKCE辅助函数已实现；独立第二实现互验、授权服务、事务性委托/撤销、完整验权入口及密钥生命周期尚未完成。本配置遵循 [当前接口契约](oauth-oidc-sm2-mvp.md)，不使用历史能力凭证 v1 的签名信封或域前缀。

## 固定参数

| 项目 | GM-MVP-1 取值 |
| --- | --- |
| SM2 后端 | `tongsuopy==1.0.1`，底层铜锁，曲线 `sm2p256v1` |
| SM2 用户标识 | ASCII `1234567812345678`，固定值，不由请求方指定 |
| SM3 | 铜锁实现 |
| JWS `alg` | `https://github.com/Qdcchh/agent-guard#sm2-sm3-v1`，项目私有标识 |
| JWS `typ` | `ag-id+jwt`、`ag-at+jwt`、`ag-pop+jwt`、`ag-receipt+jwt` |
| 签名输入 | 收到的 Compact JWS 前两段 ASCII 字节，格式为 `base64url(header).base64url(payload)` |
| JWS 签名 | 64 字节大端 `r||s`；后端 DER 仅在适配层转换 |
| 公钥 | X.509 SubjectPublicKeyInfo DER |
| 编码 | RFC 8785 规范 JSON、UTF-8、无填充且规范的 base64url |

签发时规范编码 header 和 payload；验签时对**原始收到的两段**验签，不重排字段再验签。受保护 header 只接受 `alg`、`typ`、`kid`，算法和类型必须精确匹配；`kid` 仅查调用方传入的本地可信公钥映射。不能从令牌里的 URL 获取密钥。SM2 后端对完整 JWS 签名输入执行 SM2-with-SM3，应用层不预哈希，避免漏掉或重复处理 ZA。

`load_strict_json` 在规范化前拒绝重复字段、浮点、负数和超过 `2^53-1` 的整数；业务字段的白名单、整数中 bool 拒绝、时间与权限检查仍由后续 claims 模式和验权器负责。账本 delta 的有界负数属于单独的账本契约，不通过此通用 JSON 入口。

## 当前接口

- `agent_guard.contracts`：`load_strict_json`、`canonical_json_bytes`、`b64url_encode`、`b64url_decode`。
- `agent_guard.crypto`：SM2 临时密钥生成、公钥 SPKI DER 编解码、SM2 完整消息签验、SM3 摘要、`sign_compact_jws`、`verify_compact_jws`。
- `verify_compact_jws` 只完成线格式、受保护 header、可信 key 查找和密码验签；返回 payload 后仍须按令牌类型校验 claims。不可将其返回值直接转换成账本 `VerifiedInvocation`。
- `agent_guard.authorization.claims`：严格验证Access Token字段、时效、actor链、范围和子令牌静态收窄；不代替AS事务性签发或实时授权树校验。
- `agent_guard.identity.resolver`：只读取管理员预批准的 `(tenant_id, client_id) → DID/kid/SPKI` 快照，固定did:web主机白名单、HTTPS、无重定向，并对照文档用途和公钥。它不提供自助登记或数据库生命周期管理。
- `agent_guard.authorization.verifier.InvocationVerifier`：对固定调用端点验签Access Token与AG-Proof、绑定持有者、令牌摘要和规范请求体，验证工具参数静态约束后构造账本的可信进程内输入。调用方必须提供受控原始证据暂存回调；账本接受事务仍须检查重放、授权链、撤销、时效、key状态、可信业务关联与预算。
- `agent_guard.authorization.oidc`：RP侧ID Token的SM2签验、nonce/aud/issuer/时效验证及标准S256 PKCE辅助函数；不包含真实登录、浏览器session或AS HTTP端点。
- `agent_guard.authorization.proof.sign_ag_proof`：客户端侧生成每次新jti的短时AG-Proof，绑定固定HTTPS端点、token原始字节摘要和规范业务/表单映射摘要。OAuth表单重复键拒绝仍由HTTP解码层负责。
- `agent_guard.authorization.policy.GrantPolicy`：将已验签父令牌与预登记接收者、交换请求逐维比较，输出不可变 `ChildSpec`；不签发、存储或改变预算。AS仍须在同根锁事务内重验父子状态及幂等，再保存授权节点和原签名令牌。

## 依赖与验证

`tongsuopy` 是铜锁 Python SDK（Apache-2.0）；`rfc8785==0.1.4` 由 Trail of Bits 维护（Apache-2.0）。固定版本与当前传递依赖在仓库根 `requirements.lock`；开发依赖在 `requirements-dev.lock`。本地 Windows Python 3.12 已覆盖 SM3 `abc` 标准向量、铜锁公开 SM2 验签向量、临时密钥 JWS 签验、原始 JWS 字节验证、类型/密钥/正文篡改和严格编码拒绝。CI 使用 Python 3.11 验证。

铜锁 Python SDK 的公开接口不允许调用方设置 SM2 用户标识，当前以公开向量锁定标准默认值。独立第二实现的双向验签仍须完成并记录版本、命令及结果；完成前不得将基础 SDK 称为正式签发能力。仓库不保存私钥；测试密钥临时生成。
