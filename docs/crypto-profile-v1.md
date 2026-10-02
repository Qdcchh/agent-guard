# GM-MVP-1 密码与编码配置

状态：SM2/SM3 与 Compact JWS 基础 SDK、部分业务 claims 模式、DID只读解析、静态调用验权、委托收窄及授权码/Token Exchange请求预校验、ID Token/PKCE辅助函数、进程内一次性授权码及唯一根签发、事务性子委托签发、任务与租户管理员的撤销事务及撤销 HTTP 路由、登录/同意与会话 CSRF、开发 TLS 装配、密钥轮换历史公钥、OpenSSL CLI 独立实现固定向量互验均已实现；完整网关验权联调、独立审计检查点及生产密钥托管尚未完成。本配置遵循 [当前接口契约](oauth-oidc-sm2-mvp.md)，不使用历史能力凭证 v1 的签名信封或域前缀。

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

`load_strict_json` 在规范化前拒绝重复字段、浮点、负数、超过 `2^53-1` 的整数和孤立 Unicode 代理项；通用 JSON 输入/规范输出均限 64 KiB，结构深度最多 64、节点最多 4096。超限统一报 `EncodingError`，不泄漏 Python 的整数转换或递归异常。这是解析资源上限收紧，不改变已接受消息的 JWS 签名语义；超过上限的旧输入将被拒绝。业务字段的白名单、整数中 bool 拒绝、时间与权限检查仍由后续 claims 模式和验权器负责。账本 delta 的有界负数属于单独的账本契约，不通过此通用 JSON 入口。

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
- `agent_guard.authorization.forms`、`code`、`exchange`：严格OAuth表单解码，验证授权码换码或Token Exchange请求的客户端密钥证明、端点及正文绑定，输出预校验结果。Basic认证结果、租户及重定向配置必须来自可信服务；静态预校验本身不消费code或登记防重放。授权码的事务处理见下项，子委托的实时撤销/过期和幂等仍待实现。
- `agent_guard.authorization.code_service.AuthorizationCodeService`：以真实PostgreSQL事务生成一次性哈希授权码、核对PKCE和证明、登记防重放、创建唯一根并由AS签SM2 ID/Access Token。输入 `ApprovedAuthorization` 只能由 `ConsentService` 在验证登录会话与 CSRF 后于进程内构造；浏览器入口由 `BrowserLoginApp` 提供。局部测试不构成 M1 整体通过。
- `agent_guard.authorization.exchange_service.TokenExchangeService`：AS 在同一锁序事务内签发收窄子令牌并保存签名快照与委托幂等；可配置 `verification_keys` 以在轮换后继续验签历史 `kid`，旧 key 不再签发。
- `agent_guard.authorization.login`、`consent`、`revocation_http`、`agent_guard.server`：scrypt 口令 KDF 与服务端会话/CSRF、服务端授权请求与任务政策、会话授权的任务/管理员撤销路由、严格私有配置与开发 TLS 装配。

## 依赖与验证

`tongsuopy` 是铜锁 Python SDK（Apache-2.0）；`rfc8785==0.1.4` 由 Trail of Bits 维护（Apache-2.0）。固定版本与当前传递依赖在仓库根 `requirements.lock`；开发依赖在 `requirements-dev.lock`。本地 Windows Python 3.13 已覆盖 SM3 `abc` 标准向量、铜锁公开 SM2 验签向量、临时密钥 JWS 签验、原始 JWS 字节验证、类型/密钥/正文篡改和严格编码拒绝。CI 使用 Python 3.11 验证，并以 OpenSSL CLI 作为独立第二实现对固定消息与 JWS `r||s`/DER 做双向互验；OpenSSL 3 provider 默认 `distid` 与 GB/T 默认不同，测试显式传入 `distid=1234567812345678`，该结论不覆盖所有 OpenSSL 构建或算法套件。

铜锁 Python SDK 的公开接口不允许调用方设置 SM2 用户标识，当前以公开向量锁定标准默认值。独立第二实现的双向验签仍须完成并记录版本、命令及结果；完成前不得将基础 SDK 称为正式签发能力。仓库不保存私钥；测试密钥临时生成。
