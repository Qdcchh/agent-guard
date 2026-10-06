# GM-MVP-1 密码与编码配置

状态：SM2/SM3 与 Compact JWS 基础 SDK、部分业务 claims 模式、DID只读解析、静态调用验权、委托收窄及授权码/Token Exchange请求预校验、ID Token/PKCE辅助函数、进程内一次性授权码及唯一根签发、事务性子委托签发、任务与租户管理员的撤销事务及撤销 HTTP 路由、登录/同意与会话 CSRF、开发 TLS 装配、密钥轮换历史公钥、OpenSSL CLI 独立实现固定向量互验均已实现；真实 B→A 进程内执行与只读回执投影已接入；公开调用/最终动态查询已由A2.2独立接受，A2.3持续发布候选已实现并完整119项/112运行义务独立复验已正式接受，原r1否决保留为历史，独立锚定和导出仍待A3；独立审计检查点及生产密钥托管尚未完成。本配置遵循 [当前接口契约](oauth-oidc-sm2-mvp.md)，不使用历史能力凭证 v1 的签名信封或域前缀。

历史 v1 实施交付时五项修补均标记 FIXED_PENDING_REVIEW，产品自查不是正式接受；具体命令、原失败、JUnit 和67项/60运行义务见 [v1实施报告](../tasks/workflow/runs/local-remediation-20261004/implementation-r1.md)。后续验收与合并结论以 [本轮控制状态](../tasks/workflow/runs/local-remediation-20261004/state.json) 及主控关联的正式报告为准；本文档同步证据见 [文档实施报告](../tasks/workflow/runs/local-remediation-20261004/implementation-docs-r1.md)。整体项目仍 PARTIAL：A2.2公开调用/最终动态查询已独立接受；A2.3持续签名发布候选已实现，完整119项/112运行义务独立复验已正式接受，原r1否决保留为历史，独立锚定和导出仍待A3；A3独立锚定/导出/完整采购演示/规模对照实验尚未完成。旧无回执公钥配置保持 PENDING 兼容。见[本轮补正任务](../tasks/workflow/runs/A2.3-receipts-20261004/task-remediation-r2.md)及[原独立否决记录](../tasks/workflow/runs/A2.3-receipts-20261004/review-r1.md)。

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
- `agent_guard.identity.resolver`：只读取管理员预批准的 `(tenant_id, client_id) → DID/kid/SPKI` 快照，固定did:web主机白名单、HTTPS、无重定向，并对照文档用途和公钥。它不提供自助登记或数据库生命周期管理。默认解析器具有真实 HTTPS fetch 路径；开发 server factory 则使用显式 `did_documents` 配置快照，不进行实时 DID 获取。两者的测试与部署语义分开记录。
- `agent_guard.authorization.verifier.InvocationVerifier`：对固定调用端点验签Access Token与AG-Proof、绑定持有者、令牌摘要和规范请求体，验证工具参数静态约束后构造账本的可信进程内输入。调用方必须提供受控原始证据暂存回调；账本接受事务仍须检查重放、授权链、撤销、时效、key状态、可信业务关联与预算。
- `agent_guard.authorization.oidc`：RP侧ID Token的SM2签验、nonce/aud/issuer/时效验证及标准S256 PKCE辅助函数；不包含真实登录、浏览器session或AS HTTP端点。
- `agent_guard.authorization.proof.sign_ag_proof`：客户端侧生成每次新jti的短时AG-Proof，绑定固定HTTPS端点、token原始字节摘要和规范业务/表单映射摘要。OAuth表单重复键拒绝仍由HTTP解码层负责。
- `agent_guard.authorization.policy.GrantPolicy`：将已验签父令牌与预登记接收者、交换请求逐维比较，输出不可变 `ChildSpec`；不签发、存储或改变预算。AS仍须在同根锁事务内重验父子状态及幂等，再保存授权节点和原签名令牌。
- `agent_guard.authorization.forms`、`code`、`exchange`：严格OAuth表单解码，验证授权码换码或Token Exchange请求的客户端密钥证明、端点及正文绑定，输出预校验结果。Basic认证结果、租户及重定向配置必须来自可信服务；静态预校验本身不消费code或登记防重放。授权码的事务处理见下项，子委托的实时撤销/过期与幂等由下述事务性 TokenExchangeService 实现。
- `agent_guard.authorization.code_service.AuthorizationCodeService`：以真实PostgreSQL事务生成一次性哈希授权码、核对PKCE和证明、登记防重放、创建唯一根并由AS签SM2 ID/Access Token。输入 `ApprovedAuthorization` 只能由 `ConsentService` 在验证登录会话与 CSRF 后于进程内构造；浏览器入口由 `BrowserLoginApp` 提供。局部测试不构成 M1 整体通过。
- `agent_guard.authorization.exchange_service.TokenExchangeService`：AS 在同一锁序事务内签发收窄子令牌并保存签名快照与委托幂等；可配置 `verification_keys` 以在轮换后继续验签历史 `kid`，旧 key 不再签发。
- `agent_guard.authorization.login`、`consent`、`revocation_http`、`agent_guard.server`：scrypt 口令 KDF 与服务端会话/CSRF、服务端授权请求与任务政策、会话授权的任务/管理员撤销路由、私有配置与开发 TLS 装配。HTTP 请求边界及保留目录描述符的私有路径已进行串行修补；真实 TLS 与文件边界测试结果见v1实施报告；其自查不替代独立全阶段验收，后续结论见本轮控制状态。

## 本轮 B→A 进程内接入

生产进程内接入使用 `InvocationVerifier.verify_bundle`，配置真实
`PermissionSnapshotProvider` 和 `EvidenceStore`，随后调用
`VerifiedExecution.accept`。权限 provider 逐项验证完整 root→leaf 的真实 AS
签名快照、可信历史 `(tenant, client, kid)` 登记与不可变授权树。普通
`verify_static`/`verify_result_read` 回调接口保留兼容，但回调字符串不能代替
本轮真实受控证据存储，也不能进入生产适配器。

`verify_canonical_result_read` 返回包含必填 subject、显式 POST 和真实证据引用的
A `VerifiedResultQuery`；它不验证 operation 所有权、不登记最终查询 proof，
不预留预算。最终动态查询和公开调用 HTTP 网关仍属 A2.2。

证据原材料与关联均不可 UPDATE/DELETE；first 与 retry 使用独立引用，旧的
opaque 首次证据不能用新 token 补造。STAGED 状态记录本身不可变，是否接受由
同事务的 operation link 表示。未接受的孤立暂存记录目前无限期保留隔离，
没有自动 TTL 删除策略或对外任意读取入口。部署角色应按职责最小授权；PUBLIC
没有原材料表权限，不能把服务角色交给请求方。

`execution.receipt_projection.project_receipt` 从数据库读取不可变终局材料，核对
phase/seq/完整路径/delta/结果/真实首次证据之后，使用唯一 B 规范编码与真实 SM3
投影 GM-MVP-1 v1 材料。它不签发、不发布、不把 outbox 改为 READY。测试的临时
独立 GW 签名用于互验；A2.3候选另由内部 `receipt_worker` 持续发布，完整119项/112运行义务独立复验已正式接受，原r1否决保留为历史，独立锚定和导出仍待A3。

离线验证从已认证 token/proof 字段求共同可能接受窗口：所有祖先 iat/nbf ≤ t < exp，
proof iat ≤ t+5 且 t < proof exp，t ≤ signed receipt iat。仍调用原 claims/child/proof
验证器检查完整类型、生命周期、绑定与收窄；不把 proof iat 或终局 iat 当作精确
接受时间。合法迟延恢复的终局可以晚于原授权材料到期。wire 未携带独立认证的 DB
接受时间，因此这里只证明历史时间一致性，加上原可信 GW 终局声明，不声称独立
证明实际接受瞬间。完整root→leaf路径的grant ID必须全局唯一，非邻接重复也拒绝；此检查在全部AS快照验签后逐节点校验路径时执行，ledger_changes仍须与完整路径精确对应。独立AS/GW/三holder真签名正负例见v1报告中的test_receipt_paths。原签名字段、ID、iat、PENDING 与在线新鲜性规则都不改。

## 迁移入口与恢复边界

原 A001—006 原文件与 B004—009 原字节保持不变。B 分支位于 `migrations/b`；
`python -m agent_guard.ledger.migrate --bundle` 在单一事务和有界数据库协调锁中
验证历史、追加 lineage sidecar，保留原 registry 每一旧行的全部字段。
`apply_bundle_migrations` / `applied_lineage_versions` 也可从 `ledger.migrate`
或 `ledger.lineage` 导入。旧 `apply_migrations` / `applied_versions` 保留 A 六版本
视图；升级前的 B 数字版本历史经公开 A 视图读取时失败关闭。既有 sidecar 缺少
原始14条 v2 完成条目时拒绝，不把删除证据当作可重建的未执行迁移。禁止手改旧登记、跳过 checksum 或清库伪装升级。

显式自定义 legacy 目录保留旧通用换行归一化 checksum：LF/CRLF 可正常应用和重复，
旧 CRLF registry 的 checksum/applied_at 不重写。发现时另存原字节 digest，执行前
即使只是换行变化也拒绝并回滚；canonical bundle 的 raw SQL pins 不改变。
迁移 CLI 使用5秒连接超时及既有10秒锁/15秒语句上限，固定脱敏失败诊断。

迁移角色需要目标库 CREATE SCHEMA：严格目录形状校验会在随机、自有、回滚专用
schema 重放固定 SQL，并检查列/约束/索引/函数/触发器及其启用状态。拒绝时回滚
所有迁移写入，恢复 search_path，不降低权限检查。运行迁移前应备份并验证恢复
流程。成功升级后旧二进制不保证兼容；没有无损降级承诺。安装包携带 SQL，
可信管理员可用 `AGENT_GUARD_MIGRATIONS_DIR` 指定完整迁移包，不按 cwd 猜目录。

## 固定依赖、许可和验证范围

`requirements.lock` / `requirements-dev.lock` 保留固定 B 候选原 pins；
`constraints.txt` 汇总相同 pins，未升级或替换密码后端。历史候选验证曾使用
Linux x86_64、CPython 3.11.16、PostgreSQL 16.15；本轮v1自查使用Linux amd64、
CPython 3.11.17、独占PG16，source/wheel分别锁安装、非root UID501、普通非editable
安装。具体版本、原始元数据及资源绑定见v1实施报告，不能混用历史环境证明本轮通过。包元数据支持声明并不是所有
平台的实跑证明；本轮不声称 Windows/macOS/PyPy 已复验。rfc8785 0.1.4
(Apache-2.0) 要求 Python≥3.8；tongsuopy 1.0.1 (Apache-2.0) 声明 Python≥3.6
并列出 CPython/PyPy、Windows/macOS/POSIX；实际选择的传递 cffi 2.1.1
(MIT-0) 要求 Python≥3.10，因此本项目固定环境以 Python3.11 为准。
psycopg/psycopg-binary 3.2.13 为 LGPL-3.0-only；uvicorn 0.35.0 为 BSD-3-Clause；
h11 0.16.0 为 MIT。完整实际发行版元数据随本轮验证证据保存，许可声明不替代
发行部署时对二进制及传递组件的合规审查。

已安装 tongsuopy wheel 的实际原生库版本为 BabaSSL/Tongsuo 8.3.2，导出版本
0x8030200f。它保留 OpenSSL1.1.1h 兼容字符串；仅凭该字符串不能判断安全补丁
缺失，供应方分支存在回移补丁。此 wheel 的精确构建 commit、当前完整维护状态
和全部安全回移覆盖仍未证实，不作“已无已知漏洞”或生产安全保证。继续使用固定
候选是可复现集成决定，并不构成已完成长期依赖维护审计。

固定 SM2/SM3、raw JWS 和公开向量，以及 OpenSSL CLI 双向互验使用明确
`distid=1234567812345678`。SDK 不开放自定义 SM2 用户标识，标准默认值由向量
锁定。具体本轮执行命令、版本、计数、失败修正与剩余范围见实施报告和原始日志；
旧本机/历史 CI 记录不冒充本轮执行。用户已授权完整复核和条件合并；v1 worker未触发远程CI（NOT_RUN），不能写为通过。后续远程CI与正常Git门由主控按授权处理。

本轮完整自查报告：`../tasks/workflow/runs/A2.3-receipts-20261004/implementation-remediation-r2.md`；最新真人停止指令：`../tasks/workflow/runs/A2.3-receipts-20261004/user-stop-after-selfcheck-20261005.md`。本轮补正后的新独立复验未执行；完整A2未接受，原[r1否决](../tasks/workflow/runs/A2.3-receipts-20261004/review-r1.md)保留。
