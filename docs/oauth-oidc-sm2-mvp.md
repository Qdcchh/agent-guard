# OAuth、OIDC、SM2/SM3 与 DID：初版实施及接口契约

项目：面向企业多智能体协同的可验证授权与可信执行系统。

状态：实施设计草案，不是已有功能或标准兼容认证。面向 A、B 两人开发；C 不承担初版关键路径。本文中的域名、令牌和密钥均为示意，不含可用凭据。

阅读顺序：第1—4节理解技术，第5—7节确定实现与分工，第8—10节据此联调。事务、状态机及安全边界统一在 [安全模型](security-model.md) 维护；测试清单统一在 [验收矩阵](acceptance.md) 维护。当前只保留GM-MVP-1一条设计路线。A1/A2.1 和 B 整合已有代码；本文接口示意及日程仍是目标设计，不代表全部已验收。B补正已完成独立验收并合并；[正式接受记录](../tasks/workflow/runs/local-remediation-20261004/acceptance.md)保留67项/60运行义务及原失败证据。A2.2本轮已授权实施、仍待独立验收，见[任务包](../tasks/workflow/runs/A2.2-integration-20261004/task-v1.md)。整体项目仍PARTIAL：A2.3持续签名发布、A3独立锚定/导出/完整采购演示/规模对照实验尚未完成，outbox保持 PENDING。 修补前问题保留在 [历史本地质量复核](../tasks/workflow/runs/local-quality-20261004/review.md)。

## 1. 先说明结论

老师给出的方向可以组织为一条完整链路：

```text
用户登录并确认采购范围（OIDC + 用户同意）
    → 授权服务器给统筹代理签发令牌（OAuth + SM2/SM3）
    → 统筹代理委托选品代理，再委托执行代理（Token Exchange + 收窄策略）
    → DID 文档及企业登记表确定代理身份与验证公钥
    → 代理携令牌和 SM2 请求证明调用工具
    → 网关验权、核验当前撤销状态、原子控制共享预算
    → 模拟订单、可验证回执和审计
```

不是“接上四个库即可完成”。OAuth/OIDC 提供交互框架；DID 提供标识与公钥解析；SM2/SM3 提供密码能力。任务级约束、委托收窄、预算、撤销传播与请求完整绑定仍需自行设计实现。

**初版推荐：Python 主线，OAuth/OIDC 协议骨架 + 显式的项目国密扩展 GM-MVP-1。** 授权中心统一签发所有层级令牌，代理签署委托请求，不让代理直接发行可被网关信任的访问令牌。SM2 的 ID Token 由项目自己的 RP 验证，不宣称能直接接任意通用 OIDC 客户端。

唯一需要向老师确认的问题：参考 `liboauth2` 是要求学习其机制，还是要求必须在该仓库上提交可运行 SM2 补丁？下文默认前者；如要求后者，按第4节替换技术路线，不能将“参考”写成“已基于其代码实现”。

## 2. 术语分别是什么

| 名称 | 解决的问题 | 本项目中的位置 | 不能替代什么 |
| --- | --- | --- | --- |
| OAuth 2.0 | 应用如何获得受限访问权 | 签发和使用访问令牌 | 不是密码算法，也不天然解决累计预算 |
| OIDC（OpenID Connect） | 谁完成了登录、登录结果给谁 | 人类用户登录、确认任务的入口 | ID Token 不是采购权限凭证 |
| Access Token | 持有者可对哪些资源做什么 | 代理调用网关的凭证 | 签名有效不表示未撤销或余额充足 |
| ID Token | OP 对一次用户认证事件的声明 | 仅交给登录客户端 RP 验证 | 不传给工具当 Access Token 用 |
| JWT / JWS / JOSE | 声明、签名封装及密钥等消息格式 | 承载 SM2 签名令牌和证明 | Base64url 不是加密，JWT 不必然是 OAuth |
| SM2 | 公钥密码算法体系；这里用数字签名 | AS 签令牌；代理签请求；网关签回执 | 不阻止合法令牌被偷后作为 Bearer 使用 |
| SM3 | 摘要算法 | 意图、请求体、令牌和证据摘要 | 不是签名，也不是加密，不能单独证明是谁发的 |
| Token Exchange（RFC 8693） | 用已持有的令牌换取适合下一服务/代理的令牌 | 多级委托的交互基础 | 不自动提供权限收窄、祖先撤销或共享预算 |
| DPoP（RFC 9449） | 将令牌绑定到客户端密钥，要求证明私钥持有 | 参考其 sender-constrained 思路 | 标准 DPoP 默认不签完整请求体，也不是客户端认证 |
| W3C DID | 可解析的主体标识及验证方法 | 将代理标识绑定到验证密钥 | DID 本身不证明企业成员资格或采购权，不必依赖区块链 |

术语更正：OIDC 的全称是 **OpenID Connect**，不是 Open Identity Connection。

### 2.1 对应到 OAuth 的角色

- Resource Owner：批准采购的用户。
- Authorization Server（AS）：认证用户、保存同意、签发/交换/撤销令牌；兼任 OIDC Provider（OP）。
- Client：统筹、选品、执行三个代理的后端程序；各自独立 `client_id`、客户端凭据和 SM2 私钥。
- Resource Server（RS）：工具网关。订单等下游只信任网关服务身份。
- Relying Party（RP）：统筹代理的 Web 后端，同时提供用户控制台。

两个开发成员不等于两个代理身份：初版仍实现三个独立逻辑代理。先使用确定性脚本，不以模型接入作为验收前提。

### 2.2 一个例子

用户登录只证明“用户甲已登录”，不代表系统可以替其花任意金额。用户另行确认“任务T，采购指定商品，总预算1000元”。AS 签发根令牌给统筹代理；统筹为选品代理申请至多800元的子令牌，选品再为执行代理申请至多700元的子令牌。

子额度不是提前划走的独占资金。另一分支也可能有800元上限，但所有分支加起来仍最多使用根预算1000元。每笔订单都检查根、所有中间节点及当前节点。

## 3. 为什么老师提供 GitHub 被盗令牌案例

GitHub 在2022年4月15日披露：攻击者滥用发给 Heroku、Travis CI 第三方集成的用户 OAuth 令牌，下载多个组织的私有仓库。公告并未称 GitHub 的签名算法被攻破或根签名私钥泄露。[S2]

对本项目的直接启示：

（1）Bearer Token 类似“拿到就能用的通行证”。即使令牌由 SM2 签名，盗取者不修改它也可能直接使用。

（2）需要令牌绑定代理公钥。网关同时要求令牌及该代理对本次请求的签名，单独偷到令牌不能完成调用。

（3）还要检查受众、租户、任务、权限、时效、请求新鲜性和撤销。若令牌与对应私钥一起泄露，持有者证明不能阻止攻击者使用授权范围内的权限。

（4）实验应对比“仅换成SM2的Bearer版”和“SM2令牌 + 密钥绑定 + 请求证明 + 策略/状态检查版”。该实验是机制对照，不是在真实 GitHub 上重演攻击。

## 4. liboauth2 怎么用，不应怎样用

### 4.1 已核查的事实

`OpenIDC/liboauth2` 是供 C 程序构建 OAuth/OIDC 客户端和服务器组件的基础库，README 列有令牌内省、JWT 验证、PKCE、mTLS、DPoP、客户端认证等能力。它是多个 Apache/NGINX 模块的公共引擎，API 还可能变化；不能当成已有完整用户管理与授权页面的独立 OP。[S1]

关键依赖含 OpenSSL、libcurl、jansson、cjose；JOSE 密码处理依赖 cjose。其 `src/jose.c` 的 JWT 创建/验证调用 cjose。所查源码未找到可直接启用的 SM2/SM3 完整路径，不能假定 OpenSSL 有 SM2 就代表上层 JOSE 自动支持 SM2。源码查阅不等于编译验证，落地时须固定提交 SHA、依赖版本并运行测试。

### 4.2 初版路线选择

| 路线 | 实际工作 | 建议 |
| --- | --- | --- |
| Python 主线 | 使用成熟 OAuth 库的流程能力，扩展 SM2 令牌适配层，自己实现任务策略/状态 | 推荐；保留当前工程栈，适合两人并行 |
| 必须修改 liboauth2 | 固定上游版本，跑通标准算法基线，扩展 cjose/密钥解析/算法分派，编译 C 适配组件后接 Python | 仅当老师要求实改该仓库时采用；必须额外排期 |

Python 路线可评估 Authlib；第一天验证实际版本的服务器适配、自定义签名接口与许可证，不能假设 FastAPI 自带完整 OAuth/OIDC 服务器。若框架集成复杂，可将 AS 单独用该库明确支持的 Web 适配运行，A 的网关保持 FastAPI，HTTP 契约不变。

SM2 后端优先验证维护中的 GmSSL Python 绑定或基于 OpenSSL 的可靠适配；必须核对 SM2 消息接口、用户标识、签名编码、随机数来源、标准向量和另一实现验签。名称相似的 `gmssl` 包不一定是同一项目。不得手写椭圆曲线运算，也不得以返回固定签名的占位代码接主链路。

如选择 C 路线：B 先做单独的“给定消息/密钥签验”适配实验，保持业务接口不变；A 不等待 C 模块完成，先按接口开发真实业务和测试替身。上游 Apache-2.0 许可及 NOTICE 等要求须保留，复制代码时标明来源。不建议在初版中同时维护两套 AS。

## 5. 替换算法的兼容边界

OAuth 没有规定所有令牌必须用 RSA 或 JWT。换签名通常发生在令牌封装、客户端断言或持有者证明层，而不是将 OAuth 协议本身“改成 SM2”。

| 位置 | GM-MVP-1 决策 | 是否标准兼容 |
| --- | --- | --- |
| 访问令牌签名 | SM2 + SM3，显式项目算法标识 | 项目双方约定，通用 JWT 库可能拒绝 |
| ID Token 签名 | 同样使用项目 SM2 算法，项目 RP 专门验证 | OIDC 国密实验配置，不宣称完整 OIDC 互通；OIDC Core 包含 RS256 实现要求 |
| 自定义请求/证据摘要 | SM3 | 项目扩展，无需伪称标准字段 |
| PKCE `S256` | 保持 SHA-256 | `S256` 定义就是 SHA-256，不能偷换成 SM3 |
| 标准 DPoP 的 `ath`、`cnf.jkt` | 本初版不复用这两个字段 | RFC 9449 指定 SHA-256；不能改为 SM3 后仍称标准 DPoP |
| TLS、口令存储 | 使用成熟安全配置和口令 KDF | 不把 TLS、口令 KDF 简单替换为 SM3；不宣称全栈全算法国密化 |

本初版采用显式私有 **AGPoP** 令牌使用方式，参考 DPoP 的思想，但使用 SM2、SM3 和完整业务体绑定；不是 RFC 9449 的直接兼容实现。将来如需要标准 DPoP 互通，应独立实现标准配置，保留规定的 SHA-256 字段，不做静默降级。

### 5.1 与历史方案的差异

原通用能力凭证草案已从当前目录删除，仅供Git历史回溯。当前实现只使用本文件定义的OAuth profile，不兼容旧格式，也不维护两套活跃接口。

| 项目 | 原草案 | GM-MVP-1 |
| --- | --- | --- |
| 子权限签发 | 父 holder 直接签署子凭证 | 父 holder 签委托请求，AS 检查并签子令牌 |
| 签名输入 | 自定义域前缀 + JSON 正文 | JWS 原始签名输入；以受保护 typ/alg 区分类型 |
| 链关联 | 请求携带完整凭证链 | 令牌引用根/父授权 ID；AS 注册表保存链与凭证快照 |
| 撤销/预算 | 检查全部祖先 | 保留，不能退化为只验 JWT |

OAuth流程、消息格式和接口按本文；预算与恢复不变量以 [安全模型](security-model.md) 为准。旧的直接子签发接口不实现；若未来改变路线，须经契约PR同步修改全部调用方、测试和文档，不允许隐式兼容回退。

## 6. 初版组成与验收范围

```text
控制台/RP + 统筹代理 ──浏览器授权码登录── AS/OP
       │                                   │
       ├── 两次 Token Exchange ────────────┤
       │      选品代理 → 执行代理            ├── 企业主体/客户端/DID密钥登记
       │                                   └── 授权树与撤销状态
       └── Access Token + AG-Proof ── 工具网关
                                         ├── 同根原子预算/次数账本
                                         ├── 模拟订单服务（独立事务域）
                                         └── SM2签名回执 → 审计检查点
```

初版包含登录及明确同意、SM2 ID/Access Token、三个代理两级委托、DID解析与密钥校验、四工具、持有者证明、祖先预算、撤销、基本幂等、至少“下游成功响应丢失”的恢复测试、可验签回执。

### 6.1 模块职责

| 模块 | 职责 | 禁止事项 |
| --- | --- | --- |
| contracts / crypto | 模式、规范编码、JWS与SM2/SM3适配 | 自研密码或各模块自行拼签名输入 |
| authorization / AS / OP | 登录同意、根签发、交换、收窄策略、撤销管理 | 只凭模型输出授予根权限 |
| identity / DID注册表 | DID解析、企业主体与公钥绑定、key状态 | 自动信任任意DID或新公钥 |
| agents / RP | 用户入口、代理协作、签名工具请求 | 持有企业全权凭据或直接写账本 |
| gateway / ledger | 当前验权、原子接受、预算、幂等及恢复 | 把验签或内省active当成最终执行许可 |
| tools | 可信报价、模拟订单/通知、下游幂等 | 信任代理申报金额、任意通知目标 |
| audit | 签名回执、独立检查点、离线验证 | 把签名当作现实交付或完整日志的证明 |

一个仓库按信任边界划分模块，不将每个模块都拆成微服务。部署权限、密钥及事务域边界见安全模型第2节。

独立审计锚定、完整故障矩阵、规模压测和公平对照是成熟版补齐项，不因 OAuth 改线而删除。初版若暂未完成检查点，不宣称已经能独立检测日志回滚。先做确定性代理和简易页面，不接真实支付，不做 VC 钱包、区块链或通用 DID 网络。

## 7. A/B 如何并行推进

| 成员 | 模块和交付 | 必须给另一方的东西 |
| --- | --- | --- |
| A | 控制台/RP、三代理流程、网关、账本事务、模拟订单/通知、恢复、部署与联调 | 工具 JSON 模式、预算/撤销事务接口、操作状态与端到端样例 |
| B | SM2/SM3、JOSE适配、AS/OP、Token Exchange、DID解析/登记验证、验权SDK、签名回执验证 | 可导入 SDK、真实签名令牌和失败向量、静态验证结果类型、AS HTTP接口 |

公共 `contracts/` 由 B 协调，A 确认其能映射到真实账本。A 负责同根锁和授权树存储事务基础，B 在同一事务边界内实现委托收窄和撤销管理，不各自建立不一致的撤销缓存。

### 7.1 从批准此路线起的七个工作日

| 日次 | A | B | 当日共同验收 |
| --- | --- | --- | --- |
| D1 | 任务/工具/账本模式、HTTPS与部署骨架 | 密码后端试验、确认框架、固定签名参数 | 公共契约、至少一条真实SM2签验向量 |
| D2 | RP回调与会话、四工具的确定性实现 | 授权码、PKCE、ID Token、AS公钥发现 | 用户真实登录并同意，错误state/nonce被拒 |
| D3 | 网关与原子预算、AGPoP请求生成 | 根令牌、DID解析、验权SDK | 真实SM2根令牌调用一次工具 |
| D4 | 三代理编排、委托令牌交付 | 两级Token Exchange、严格收窄 | 统筹→选品→执行，扩权交换拒绝 |
| D5 | 并发预算、下游幂等、基本恢复 | 请求体绑定、重放、撤销、回执验签 | 偷令牌/改参数失败，重试不重复 |
| D6 | 故障注入、入口隔离、展示 | 负例矩阵、密钥失效与证据验证 | 全部初版验收用例通过 |
| D7 | 干净环境部署与演示 | 技术结论与标准边界核对 | 录屏、可复现命令、缺陷/限制清单 |

按每天每人约5—6小时估计，是目标而非保证。必须与10月13日冻结、10月20日交付合并安排；延迟时先删复杂页面和可选场景，不能跳过真实密码或以跳过验权方式联调。

每天至少集成一次。B 未完成 SDK 时 A 使用仅在测试中装配的替身；D3 起替换为真实验签。每项交付需包含正常及拒绝样例。短任务分支、PR、另一人审核、CI通过后合并；本文不修改现有分支保护。

## 8. 公共数据与密码契约（A/B 都必须遵守）

### 8.1 默认参数

| 参数 | 初版约定 |
| --- | --- |
| profile | `GM-MVP-1`，不得与原能力凭证v1混用 |
| issuer | 配置固定 HTTPS 地址，示意 `https://auth.agent-guard.test` |
| gateway audience | 固定 `https://gateway.agent-guard.test`，不接受调用方任意URL |
| 客户端 | `agent-planner`、`agent-selector`、`agent-executor`，初版静态登记 |
| 客户端认证 | 每客户端独立高熵 `client_secret_basic`，仅后端持有，HTTPS传输；另强制SM2请求证明 |
| Access Token TTL | 最多300秒，子令牌不得晚于父或任务过期时间；无刷新令牌 |
| ID Token / 授权码TTL | 300秒 / 60秒，授权码仅能使用一次 |
| 请求证明 | `iat` 最多未来5秒；`iat <= exp <= iat+60`，接受时必须未过期；随机jti至少128位 |
| 初始委托深度 | 根2、第一层1、第二层0；最大链3节点 |
| 数值 | CNY整数分，0至2^53-1；数量必须正整数；bool不是int。仅账本delta字段允许负值，范围为±(2^53-1) |
| 编码 | UTF-8、JSON采用RFC8785规范化、Base64url不带填充；拒绝重复字段 |

任务预算不能因为令牌续签而重置。初版到期后新任务重新同意；不实现刷新或同一任务换链接管历史操作，避免未定义的额度/幂等迁移。

数据库对 `(tenant_id, task_id)` 建立永久唯一根授权约束；创建根前锁任务记录，不能只锁尚未创建的根。原根过期、撤销或令牌响应丢失也不得清零/重建。另一个授权码为同一任务申请根时返回 `invalid_grant / TASK_ALREADY_AUTHORIZED`，由控制台展示已有任务状态。新增预算必须创建经过用户明确审批的新任务，不能自动换task_id绕过原任务上限。

### 8.2 SM2令牌封装

定义项目私有算法标识 `https://github.com/Qdcchh/agent-guard#sm2-sm3-v1`。这是本文约定的标识，不是声称已经注册的 IANA 算法。短称 ALG，下例传输时必须填完整值。

```json
{
  "alg": "https://github.com/Qdcchh/agent-guard#sm2-sm3-v1",
  "typ": "ag-at+jwt",
  "kid": "as-sign-1"
}
```

签名输入严格为 JWS Compact 的 `base64url(header_bytes) + "." + base64url(payload_bytes)` ASCII字节，不在其前面拼原草案域前缀。SM2以标准曲线及SM3处理原消息，SM2用户标识固定为16字节ASCII `1234567812345678`；这不是用户账号。签名输出固定为64字节大端 `r||s`，DER输出由适配层严格转换，验签拒绝长度及整数范围异常。

签发端规范编码；验签端验证收到的原始JWS两段字节，不能解析再重新序列化后验签。验签前只用未验证头部做白名单键查找，禁止据此获取任意网络密钥、选择算法或建立权限。签名通过后再验证claims。SM2已有库若接口期望预摘要，适配层必须按照该库规范处理ZA与消息摘要，禁止漏掉ZA或重复摘要。

`typ` 分别为 `ag-id+jwt`、`ag-at+jwt`、`ag-pop+jwt`、`ag-receipt+jwt`；相同算法也不能跨类型接受。AS只签ID/Access Token，代理只签请求，网关只签回执，密钥与验证入口分离。

### 8.3 ID Token 与 Access Token

ID Token 包含 `iss, sub, aud, iat, exp, auth_time, nonce`。`aud` 必须为登录RP的 `agent-planner`；RP核验预登记issuer、允许算法/密钥、时效、aud及会话中保存的nonce。它不携带工具授权，不用于网关调用；代码流初版不发 `at_hash/c_hash`，不实现Implicit/Hybrid流程。

Access Token 示意（时间及摘要为说明值，不能直接用于调用）：

```json
{
  "iss": "https://auth.agent-guard.test",
  "sub": "user-demo-001",
  "aud": "https://gateway.agent-guard.test",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000300,
  "jti": "token-exec-001",
  "client_id": "agent-executor",
  "scope": "procurement.order.create notification.template.send",
  "act": {
    "sub": "did:web:identity.agent-guard.test:agents:executor",
    "act": {
      "sub": "did:web:identity.agent-guard.test:agents:selector",
      "act": {"sub": "did:web:identity.agent-guard.test:agents:planner"}
    }
  },
  "ag_profile": "GM-MVP-1",
  "ag_tenant_id": "tenant-demo",
  "ag_task_id": "task-001",
  "ag_grant_id": "grant-exec-001",
  "ag_parent_id": "grant-select-001",
  "ag_root_id": "grant-root-001",
  "ag_delegation_remaining": 0,
  "ag_limits": {"currency": "CNY", "amount_fen": 70000, "calls": 10},
  "ag_constraints": {
    "request_ids": ["req-001"],
    "document_ids": ["doc-001"],
    "quote_versions": ["quote-001@1"],
    "skus": ["sku-001"],
    "max_quantity": 2,
    "delivery_ids": ["office-001"],
    "template_ids": ["order-created"],
    "recipient_ids": ["user-demo-001"]
  },
  "ag_cnf": {
    "kid": "did:web:identity.agent-guard.test:agents:executor#key-1",
    "spki_sm3": "BASE64URL_SM3_OF_REGISTERED_SPKI_DER"
  }
}
```

- 所有层级的 `sub` 保持真实授权用户不变，当前代理由最外层 `act.sub` 表示。嵌套 `act` 仅是身份历史，不是逐级权限或撤销状态的来源。[S4]
- `client_id` 为该令牌实际签发给的目标客户端，不把前一代理的认证ID混写为新持有者。AS另在审计中记录交换请求者。
- `ag_*` 是项目扩展。根的 `ag_parent_id=null` 且根ID等于自身授权ID。字段与AS持久化注册表一致；未知关键扩展或不支持版本拒绝。
- 使用授权表保存每节点权限快照、父子关系及签名令牌快照。静态验签不能替代完整路径的权限包含校验和实时状态检查。
- 示例共享一把代理SM2密钥用于客户端请求证明和工具调用；AS密钥始终独立。公钥摘要使用标准化SM2 SPKI DER字节，不能对格式不一致的PEM文本取摘要。

约束模式补充（D1据此形成机器模式）：`ag_constraints`中的七个集合字段均必需，类型为不重复的ASCII字符串数组；`max_quantity`为非负整数。集合缺失是格式错误，空集合表示不允许任何对应资源，不表示无限制；只读授权可用0作为数量上限。所有子集合须包含于父集合，子max_quantity不得增加。报价版本采用固定 `quote_id@version` 键，quote_id和version禁止含`@`，版本使用十进制正整数的无前导零字符串。

`max_quantity`限制每笔订单中每个SKU的数量，不宣称任务累计件数限制；若需累计件数，另增账本维度。items为1—256项且拒绝重复SKU；参数、持久报价快照和结果共用 `MAX_ORDER_ITEMS=256`；每个quantity必须为正整数且不超过max_quantity。可信数据检查申请与租户/任务、文档与申请、报价与申请/SKU/供应商的关联；供应商由批准的报价版本确定，不允许请求替换。通知operation_id须属于该任务且当前授权可访问。四类工具的params字段均必需，拒绝额外字段；不能用客户端声称的关联替代可信查询。

### 8.4 DID不是“字符串贴标签”

初版选 `did:web` 方法：

```text
did:web:identity.agent-guard.test:agents:executor
  → https://identity.agent-guard.test/agents/executor/did.json
```

必须真实解析托管的DID文档并校验id、controller、用途及公钥。`.test` 域名在本地测试部署中由固定主机映射和开发CA支持，不关闭TLS证书验证。生产/公开演示需改为实际受控域名。[S7]

文档采用 `application/did+json`，不使用未定义JSON-LD上下文。SM2验证方法是显式项目扩展，不虚构已标准化的SM2 JWK曲线或W3C密码套件：

```json
{
  "id": "did:web:identity.agent-guard.test:agents:executor",
  "verificationMethod": [{
    "id": "did:web:identity.agent-guard.test:agents:executor#key-1",
    "type": "https://github.com/Qdcchh/agent-guard#Sm2VerificationKeyV1",
    "controller": "did:web:identity.agent-guard.test:agents:executor",
    "https://github.com/Qdcchh/agent-guard#publicKeySpki": "BASE64URL_SPKI_DER"
  }],
  "authentication": ["did:web:identity.agent-guard.test:agents:executor#key-1"],
  "capabilityInvocation": ["did:web:identity.agent-guard.test:agents:executor#key-1"]
}
```

统筹/选品另将相应密钥列入 `capabilityDelegation`。这些用途声明只表示密钥可用于证明该类行为，不会自行授予业务权限。

企业注册表额外绑定 `client_id ↔ tenant_id ↔ DID ↔ kid ↔ 公钥摘要 ↔ 状态`。只允许预登记域名和精确路径，禁止自动访问未知DID、跨域跳转、私网任意地址及任意serviceEndpoint，防止SSRF。密钥首次登记和替换需管理员确认及私钥持有证明；运行中的公钥变化不能自动视为已被企业批准。

初版可由管理员初始化三份DID文档和登记表，不提供公共自助注册。修改、停用与轮换由管理流程执行：新key用新kid，停用旧key使其新调用失败，历史证据保留当时公钥快照。企业登记表才决定成员资格，did:web仍依赖域名/TLS控制，不宣称完全去中心化。

### 8.5 AG-Proof：令牌之外还要签什么

工具请求使用 `Authorization: AGPoP <access_token>` 和 `AG-Proof: <proof_jws>`。不使用标准DPoP头，不允许将同一国密绑定令牌改走Bearer路径。

proof头：固定ALG、`typ=ag-pop+jwt`、`kid=代理DID URL`；proof正文必需字段：

| 字段 | 规则 |
| --- | --- |
| profile / purpose | `GM-MVP-1`；`code-exchange`、`delegate`、`invoke`、`result-read`之一 |
| client_id | 请求者客户端，与注册表及当前holder一致 |
| jti / iat / exp | 每请求新随机ID及短时效，验证窗口见8.1 |
| htm / htu | 固定HTTP方法及配置中的完整HTTPS目标；初版这些POST端点禁止query/fragment |
| token_sm3 | Base64url(SM3(令牌ASCII字节))；委托时绑定subject_token，换授权码时为null |
| body_sm3 | Base64url(SM3(规范化业务/表单映射JSON的UTF-8字节)) |

JSON请求体直接按RFC8785处理；OAuth表单先UTF-8解码为“键→字符串”映射，拒绝重复键；`ag_constraints` 等JSON字符串字段必须使用统一SDK规范编码后填入表单。AG-Proof本身在header，不包含于body摘要。Authorization头不入body，客户端认证结果必须另与proof的client_id及公钥绑定检查。

工具版本、全部参数、任务ID和幂等键都在签名所绑定的body里。只对HTTP路径签名不够。接收方不从不可信 `Host/X-Forwarded-*` 推断htu，使用配置的公开端点。

重放记录唯一键为 `(kid, purpose, htu, jti)`，覆盖证明有效窗口及偏差后才清理。重试重新生成proof，业务幂等键保持不变。此处jti不是业务幂等键，也不是OIDC登录nonce。

## 9. HTTP接口（联调以此为准）

所有响应禁止泄露密钥、原始令牌和其他租户对象。令牌响应含 `Cache-Control: no-store`、`Pragma: no-cache`。TLS保护传输，JWS不加密正文。

### 9.1 AS/OP与密钥发现（B实现，A消费）

| 方法与路径 | 身份要求 | 作用 |
| --- | --- | --- |
| GET /.well-known/openid-configuration | 无 | 发布本项目OP元数据 |
| GET /ag/keys | 无 | 返回AS公开签名密钥，不含私钥 |
| GET/POST /oauth/authorize | 浏览器登录会话 | 授权码流程和用户同意 |
| POST /ag/consent | 登录会话 + CSRF校验 | 确认当前授权请求及任务边界 |
| POST /oauth/token | 客户端认证 + AG-Proof | 授权码换令牌或Token Exchange |
| POST /oauth/introspect | 网关独立服务凭据 | 提供当前令牌状态和元信息 |
| POST /ag/tasks/{task_id}/revoke | 任务所属用户会话或管理员 + CSRF | 撤销根及全部后代 |
| POST /ag/grants/{grant_id}/revoke | 同租户授权管理权限 + CSRF | 撤销指定节点及后代 |

Discovery至少返回 `issuer, authorization_endpoint, token_endpoint, response_types_supported=["code"], subject_types_supported=["public"], id_token_signing_alg_values_supported=[ALG], scopes_supported, token_endpoint_auth_methods_supported=["client_secret_basic"], code_challenge_methods_supported=["S256"], ag_profile, ag_signing_keys_uri`。

`/ag/keys` 返回 `{"profile":"GM-MVP-1","keys":[{"kid":"as-sign-1","alg":"完整ALG","use":"sig","public_key_spki":"BASE64URL_DER"}]}`。这是项目私有密钥发现，不伪称标准JWKS；因此该profile不能直接通过完整标准OIDC认证。A固定信任issuer和该HTTPS地址，不接受token自己指定密钥来源。未来标准兼容配置需增加标准算法与JWKS另行验证。

### 9.2 用户登录与根授权

初版预置合成用户、采购申请及客户端。真实密码登录由成熟框架完成，不用“传user_id即登录”。本地初始化生成密码，禁止提交固定可用密码。用户同意与登录分别记录。

授权请求参数：

```text
response_type=code
client_id=agent-planner
redirect_uri=https://console.agent-guard.test/oauth/callback
scope=openid procurement.request.read procurement.document.read procurement.order.create notification.template.send
state=<与浏览器会话绑定的随机值>
nonce=<本次登录随机值>
code_challenge=<按RFC7636使用SHA-256计算>
code_challenge_method=S256
ag_task_id=task-001
```

AS不信任URL附带任意预算。根据已登录用户读取任务及租户策略，展示允许工具、资源、总额、时效和委托深度；`POST /ag/consent` 使用 `{authorization_request_id, decision:"approve"|"deny", csrf_token}`，授权参数从服务端保存的请求和用户确认记录读取。用户只能确认其有权操作的任务。

AS将用户、任务、client_id、精确redirect_uri、scope、PKCE挑战、nonce和同意快照绑定到一次性code。回调只带code/state，不带访问令牌。RP验证state后在后端请求：

```http
POST /oauth/token
Authorization: Basic <agent-planner的独立客户端凭据>
AG-Proof: <purpose=code-exchange，已登记planner密钥签名>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=...&redirect_uri=...&code_verifier=...
```

AS验证客户端、proof、code一次性与有效期、redirect_uri和PKCE。根持有者固定为该已登记客户端的DID/key，不允许在换码时任意换人。根授权与code消费同事务提交，网络丢失不允许重复换码；用户重新发起流程时必须重新确认任务，不默默重复创建预算任务。

两个不同code并发兑换同一任务也只能创建一个根，受8.1的任务唯一约束限制。新登录可重新认证用户，但不自动给原任务创建第二份预算。

成功响应：`{access_token, token_type:"AGPoP", expires_in:300, scope, id_token, ag_grant_id, ag_task_id}`。RP验证SM2 ID Token后建立服务端会话；访问令牌和私钥留在后端，不放入URL、前端localStorage或模型上下文。OIDC会话Cookie使用Secure、HttpOnly和合适SameSite，登录/同意均防CSRF。

### 9.3 两级代理委托：Token Exchange

本项目选用“父代理为已登记子代理申请受限令牌”的profile。RFC8693允许具体信任策略由部署定义，目标代理由私有 `ag_delegate_client_id` 指定，不能将该参数误称为RFC8693标准字段。初版不接受actor_token输入，也不做用户冒充。

```http
POST /oauth/token
Authorization: Basic <父代理自己的客户端凭据>
AG-Proof: <父代理SM2密钥签名，purpose=delegate>
Content-Type: application/x-www-form-urlencoded
```

解码后的表单参数：

```text
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
subject_token=<父Access Token>
subject_token_type=urn:ietf:params:oauth:token-type:access_token
requested_token_type=urn:ietf:params:oauth:token-type:access_token
audience=https://gateway.agent-guard.test
scope=procurement.order.create notification.template.send
ag_delegate_client_id=agent-executor
ag_amount_limit_fen=70000
ag_call_limit=10
ag_ttl_seconds=180
ag_delegation_remaining=0
ag_constraints=<按8.3结构规范编码的JSON字符串>
ag_delegation_key=<该委托业务的稳定随机键>
```

上例实际HTTP传输须做表单百分号编码。AS依次验证：

（1）Basic认证的父client_id、proof签名者、父令牌当前act及ag_cnf一致。不能拿自己的认证凭据交换偷来的别人的令牌。

（2）父令牌类型、issuer、audience、时效、任务、根及所有祖先状态有效。虽然subject_token的aud为网关，AS仅在明确允许的交换端点接受自家签发、登记的此类token，不将其作为AS的普通访问令牌。

（3）目标client在同租户登记且允许接受该任务委托，读取其批准DID及key；请求者不能提交任意公钥。所有scope、资源、参数、金额、次数、时间、深度只能收窄，超出直接拒绝，不静默扩大。

（4）与执行接受/撤销共用同根锁，在事务内复核动态状态；创建一个不可变子授权节点，记录委托者、接收者、父根ID和签名请求摘要。签发不是预算扣减。

（5）委托幂等键作用域 `(parent_grant_id, requesting_client_id, ag_delegation_key)`；绑定完整委托意图。新proof重试返回同一子节点及其原令牌，不重复建节点；改目标或权限拒绝，当前撤销/过期仍先检查。持久化签发结果或使用outbox，不能重试时续期或重置额度。

幂等命中也检查已有子节点、祖先、接收者与绑定key均有效；子已撤销/过期或key已停用时拒绝，不创建替代节点。有效重试返回原token，`expires_in=max(0, token.exp-now)`按当前时间重算，不能返回最初寿命。默认key轮换不使旧token自动绑定到新key。

成功响应：

```json
{
  "access_token": "CHILD_SM2_JWS",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "AGPoP",
  "expires_in": 180,
  "scope": "procurement.order.create notification.template.send",
  "ag_grant_id": "grant-exec-001",
  "ag_parent_id": "grant-select-001",
  "ag_root_id": "grant-root-001"
}
```

child令牌由AS签名，绑定接收者SM2公钥。父代理拿到child令牌也不能用父私钥冒充child调用。初版确定性编排器通过本地对象/受控IPC交给对应代理；明确同进程仅验证逻辑身份，不提供进程失陷隔离。拆容器后使用固定接收端及认证通道传递，禁止让模型决定发送URL。此处“Agent 2 Agent”是授权场景，不代表已经实现某一独立A2A消息协议规范。

### 9.4 工具调用与结果查询（A实现）

```http
POST /v1/invocations
Authorization: AGPoP <执行代理Access Token>
AG-Proof: <执行代理签名，purpose=invoke>
Content-Type: application/json
```

```json
{
  "profile": "GM-MVP-1",
  "task_id": "task-001",
  "tool_id": "procurement.order.create",
  "tool_version": "1",
  "idempotency_key": "purchase-001",
  "params": {
    "request_id": "req-001",
    "quote_id": "quote-001",
    "quote_version": "1",
    "items": [{"sku": "sku-001", "quantity": 1}],
    "delivery_id": "office-001"
  }
}
```

四工具的完整参数契约如下，字段均必需，拒绝额外字段：

| tool_id | params | 可信约束 |
| --- | --- | --- |
| procurement.request.read | request_id | 申请属于当前租户/任务且在授权集合内 |
| procurement.document.read | request_id, document_id | 文档在授权集合且与该申请可信关联，不接受任意URL/路径 |
| procurement.order.create | request_id, quote_id, quote_version, items[{sku, quantity}], delivery_id | items为1—256项；受批准报价、SKU、数量、收货对象约束，检查8.3节的关联与重复SKU规则 |
| notification.template.send | template_id, recipient_id, operation_id | 模板/接收方在批准集合，操作属于当前任务且可访问，无任意消息载荷 |

所有tool_version固定字符串 `1`。可信服务按已绑定报价计算金额，禁止代理提供权威总价。只读及通知金额成本为0，新操作次数成本为1。

接受返回202：`{operation_id, status, receipt_status:"PENDING"}`。首次为RESERVED；同键同意图重试返回原操作的真实当前状态（包括终态），不二次预留。业务键作用域为租户/任务/tool_id/key；意图绑定grant_id、holder、tool_version和规范params，不含proof的jti与时间。相同任务不同令牌jti若对应同一不可变grant无需改变业务意图；换授权节点则视为冲突，初版不提供换链接管。

查询用 `POST /v1/operations/query`，相同AGPoP+AG-Proof，purpose为result-read，body为 `{profile, task_id, operation_id}`。只允许原授权节点/holder且当前权限有效，结果读取不再次扣业务次数。返回 `{operation_id, status, receipt_status, result, receipt_jws}`；无最终回执时receipt_jws为null，UNKNOWN不伪装成FAILED。

### 9.5 内省、撤销及回执

`POST /oauth/introspect` 使用网关的独立Basic服务凭据，form为 `token=...&token_type_hint=access_token`；无效/未知/撤销令牌返回200 `{"active":false}`，不泄露细节。有效响应含 `active, iss, sub, aud, exp, scope, client_id, act, ag_grant_id, ag_root_id, ag_cnf`。

内省的active只是读取时刻的状态，**不能消除检查到执行之间的竞态**。初版AS与网关使用同一可信PostgreSQL实例的授权/账本域及相同根锁协议，由网关接受事务再检查全部祖先撤销、时效、密钥状态与额度。模拟订单仍使用独立事务域，不能与网关一笔事务掩盖故障。

两个 `/ag/.../revoke` 都是项目管理接口，不标成RFC7009端点。body为 `{reason_code:"USER_CANCELLED"}`；返回 `{revocation_id, effective_at, scope:"SUBTREE"}`。归属/管理权限与CSRF从会话验证，不接受body自报角色。撤销事务提交后，新的交换及业务接受拒绝；已接受操作仅由内部恢复通道继续原意图。

最终回执JWS的payload含 `profile, receipt_id, operation_id, tenant_id, task_id, root_grant_id, grant_id, token_sm3, proof_sm3, intent_sm3, tool_id, tool_version, status, amount_fen, result_sm3, ledger_sm3, iat`。使用独立网关签名key、typ=ag-receipt+jwt。回执不包含原始token或秘密；后续独立检查点绑定其摘要和顺序，历史验证使用可信公钥快照。

`amount_fen`表示最终实际结算额：SUCCEEDED为经下游确认的预留成本，只读/通知为0；确定无效果的FAILED为0；UNKNOWN不生成最终回执。每次操作持久化规范对象 `ledger_changes={operation_id, events:[...]}`，events按预留、终局变动顺序排列；每个事件含 `phase`（RESERVE/SETTLE/RELEASE）和根至叶排列的 `nodes`，每节点含 `grant_id, amount_reserved_delta, amount_settled_delta, calls_reserved_delta, calls_settled_delta`，必须覆盖全部适用节点且不可重复。

RESERVE对各节点记录金额/次数预留增加；SETTLE记录预留等额减少、已结算等额增加；RELEASE记录预留减少、已结算增量为0。失败不能既结算又释放，重试/恢复不追加第二次终局变动。事件与对应账本事务原子持久化。`ledger_sm3=Base64url(SM3(规范化ledger_changes字节))`，导出必须附ledger_changes及授权路径材料，验证器重算摘要并核对节点路径、阶段、金额及次数规则。单笔材料验证的是变动关联，不独自证明整个任务历史完整；累计预算与全量审计需结合可信状态快照/完整已锚定记录。

`token_sm3`、`proof_sm3`分别为完整Compact JWS原始ASCII字节的SM3再Base64url编码；`intent_sm3`和`result_sm3`为规范化意图/最终结果JSON字节的SM3再Base64url编码。第一次接受时原子持久化这些输入关联，后续重试的proof另记审计事件，不覆盖首次接受证据。用于复核的原token/proof只放在受访问控制的证据存储，不写应用日志；持久化可用部署密钥加密，与私钥存储隔离。

增加 `POST /v1/evidence/export`（A提供导出，B提供验证器），仅允许预登记、具有审计角色的独立管理服务凭据通过HTTPS调用，body为 `{task_id}`，服务端检查其租户与任务权限。导出包包含manifest版本、规范请求/结果、首次token/proof、授权树和签名快照、报价快照、ledger_changes、最终回执，以及可用检查点；示范仅导出合成数据及已失效测试token，不暴露私钥。初版无检查点则标注 `anchoring_status:"UNANCHORED"`，只能验证签名与关联，不能声称完整性或防回滚。

离线验证器从部署时独立交付的可信配置获得AS、网关及审计端公钥/指纹，不能把证据包自带的新公钥当信任根。历史密钥快照须能关联到可信登记记录；不得用当前DID文档倒推历史授权。网关回执key由A生成并经B验证接口验收，密钥轮换使用新kid；可信配置中的旧key保留用于历史验签，撤销状态另行说明。

### 9.6 错误契约

OAuth端点保持OAuth风格：`{"error":"invalid_request","ag_error":"DELEGATION_EXPANSION"}`。初版映射：

| 场景 | HTTP / error | ag_error示例 |
| --- | --- | --- |
| Basic客户端认证失败 | 401 / invalid_client | CLIENT_AUTH_FAILED |
| 授权码/PKCE失败 | 400 / invalid_grant | CODE_OR_PKCE_INVALID |
| Token Exchange输入token或proof无效、撤销、扩权 | 400 / invalid_request | SUBJECT_INVALID / PROOF_INVALID / REVOKED / DELEGATION_EXPANSION |
| audience不允许 | 400 / invalid_target | TARGET_DENIED |
| 不支持grant | 400 / unsupported_grant_type | GRANT_UNSUPPORTED |
| 非法scope | 400 / invalid_scope | SCOPE_DENIED |

网关使用 `{"error":{"code":"...","request_id":"..."}}`：400 INVALID_SCHEMA；401 INVALID_SIGNATURE/HOLDER_MISMATCH/STALE_REQUEST；403 SCOPE_DENIED/REVOKED/EXPIRED；409 REPLAY/IDEMPOTENCY_CONFLICT/QUOTE_CONFLICT；422 BUDGET_EXCEEDED/CALL_LIMIT_EXCEEDED；503 TRUSTED_STATE_UNAVAILABLE。AGPoP认证失败响应带对应WWW-Authenticate challenge，不错误标为Bearer或DPoP。

## 10. Python模块接口与联调夹具

以下伪接口保留原设计语义，不作为当前调用API。实际A2.2入口为`InvocationVerifier.verify_bundle`→`VerifiedExecution.accept`，以及`InvocationVerifier.verify_query_bundle`→`AuthorizedQuery.query`；后者用冻结`VerifiedQueryBundle`保留`VerifiedResultQuery`、真实`PermissionSource`和opaque evidenceRef。同事务复核原ownership/原材料/当前权限，按principals→task→root至leaf→operation锁序，全部晚依赖和约束flush后用最终DBclock检查新鲜性。B输出共享实现，网关不复制密码算法。响应沿用规范编码65536字节上限，坏可信材料/超限503且query proof回滚。两公开POST入口及显式公钥配置/TLS启动见README；回执持续发布、导出仍为后段目标。

```python
class CryptoProvider:
    def sign_jws(self, payload: dict, *, key_id: str, token_type: str) -> str: ...
    def verify_jws(self, token: str, *, expected_type: str, trusted_keys) -> dict: ...
    def sm3_b64url(self, data: bytes) -> str: ...

class IdentityResolver:
    def resolve_registered(self, client_id: str, tenant_id: str, purpose: str): ...

class InvocationVerifier:
    def verify_static(self, token: str, proof: str, *, endpoint: str,
                      method: str, body: bytes, now: int) -> "VerifiedInvocation": ...

class GrantPolicy:
    def validate_child(self, parent_snapshot, requested, recipient) -> "ChildSpec": ...

class ExecutionService:
    def accept(self, verified: "VerifiedInvocation") -> "Operation": ...
    def query_authorized(self, verified: "VerifiedInvocation") -> "Operation": ...
    def recover(self, operation_id: str) -> "Operation": ...
```

VerifiedInvocation至少包括 `subject, tenant_id, task_id, holder_client_id, holder_kid, grant_id, root_id, ancestor_ids, token_exp, token_digest, proof_digest, proof_jti, proof_iat, proof_exp, endpoint, purpose, normalized_body, intent_digest, evidence_ref`。evidence_ref指向受控暂存的原始证据，接受事务将其与操作绑定；不指向客户端指定路径。仅能由受信任模块在进程内构造，不允许外部提交JSON伪装“已验权”。`verify_static` 不负责最终余额判断；`accept` 在事务内重新读状态、登记防重放并预留。

统一夹具：租户tenant-demo、任务task-001、根100000分；分支上限80000分；订单报价70000分。B提供真实签名token及对应公开测试key标识、规范编码字节/摘要向量和错误样例；A提供可信报价、数据库种子、并发预留断言和下游幂等接口。仅测试用固定私钥如需存仓库必须隔离且醒目标记，不能用于开发部署。

第一批分支：B `feat/gm-token-codec`、`feat/oidc-code-flow`；A `feat/execution-ledger`、`feat/mock-procurement`。接口定义先合并，后续新增case与实现同PR更新，禁止“先随便返回成功，联调后再补安全”。

## 11. 预算与状态机的实施入口

OAuth不替代业务一致性。A/B共同实现 [安全模型](security-model.md) 第3—7节的唯一根、锁序、接受时效复核、祖先账本、下游幂等、恢复及撤销边界；此处不再维护第二份状态机。仅通过SM2验签或内省active不能直接执行，UNKNOWN不等于FAILED。

## 12. 验收入口、演示与剩余工作

初版M1—M13与成熟版回归、性能、交付清单统一维护在 [验收矩阵](acceptance.md)。当前已有阶段实现，但完整项目仍 PARTIAL；不得把文档审查、局部测试或历史阶段通过当作当前整体验收通过。

建议五分钟演示：用户确认预算 → 显示三代理与DID密钥绑定 → 正常采购 → 复制token盗用失败 → 并发争抢预算 → 模拟响应丢失和恢复 → 导出并验证回执。

初版不宣称：完整OIDC认证通过、标准DPoP互通、完全去中心化身份、全栈国密、生产级安全或首创OAuth委托。成熟版继续补独立审计锚定、完整故障矩阵、50并发/10000调用目标、开销拆分与公平基线。密码替换是实施内容，组合机制与实验证据才是创新主张的依据。

### 开工前的三个确认门槛

- 老师是否要求修改liboauth2本体。若是，先给C适配与Python调用做最小签验实验，重新估算排期。
- 是否接受“SM2应用令牌/证明 + 保留标准PKCE与TLS”的混合边界。若要求连PKCE都改为SM3，必须另定显式方法名和兼容测试，不能继续标S256。
- D1结束前A/B共同确认算法标识、签名格式、SM2用户标识、DID扩展、端点和错误码；用相同夹具确认结果，再分头开发。

## 13. 官方资料与证据范围

- [S1] [OpenIDC/liboauth2](https://github.com/OpenIDC/liboauth2)：README、`src/jose.c`、`include/oauth2/openidc.h`、构建依赖；[cjose](https://github.com/OpenIDC/cjose)为其JOSE依赖。查阅不等于已编译或证明所有分支均不支持SM2。
- [S2] [GitHub：第三方OAuth用户令牌被盗事件](https://github.blog/news-insights/company-news/security-alert-stolen-oauth-user-tokens/)：2022-04-15发布，包含后续更新。
- [S3] [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)：身份层、ID Token、授权码流程、签名和必需实现能力。
- [S4] [RFC8693 OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html)：交换请求、delegation/impersonation、act历史，以及撤销传播不自动成立的边界。
- [S5] [RFC9449 DPoP](https://www.rfc-editor.org/rfc/rfc9449.html)：私钥持有证明、SHA-256的ath/jkt、不是客户端认证、默认不签整个请求体。
- [S6] [W3C DID Core](https://www.w3.org/TR/did-core/)：标识、验证方法、用途与解析，不要求使用区块链。
- [S7] [did:web方法说明](https://w3c-ccg.github.io/did-method-web/)：HTTPS解析与域名信任；方法说明不等同于DID Core本身。
- [S8] [RFC7636 PKCE](https://www.rfc-editor.org/rfc/rfc7636.html)：S256定义及code绑定。
- [S9] [RFC7515 JWS](https://www.rfc-editor.org/rfc/rfc7515.html)、[RFC8785 JSON Canonicalization](https://www.rfc-editor.org/rfc/rfc8785.html)：签名输入与规范编码是不同层次，不能混淆。

以上链接用于理解和验证设计。项目私有ALG、AGPoP、ag_*字段、SM2 DID验证方法及业务预算策略为本方案建议，不是这些标准已经提供的现成功能。
