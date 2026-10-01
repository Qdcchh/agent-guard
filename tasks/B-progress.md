# B 角色进度与续跑入口（2026-10-01）

分支：`feature/fjr-B-character`，PR #3。此记录只描述已落地代码与待办，不替代 [`docs/acceptance.md`](../docs/acceptance.md) 的 M1—M13 验收。不要将分支推送等同于合并 main。

## 已落地

- SM2/SM3 JWS、AG-Proof、DID/企业登记校验、静态验权 SDK 与严格工具参数校验。
- 一次性授权码兑换、根令牌/ID Token 签发、两层 AS 签发的事务性 Token Exchange。
- 任务所有者撤销、租户管理员登记及节点子树撤销的数据库事务；网关独立凭据内省。
- 会话 + CSRF 的撤销 HTTP 路由（`RevocationHttpApp`）：`POST /ag/tasks/{task_id}/revoke` 由任务所有者调用，`POST /ag/grants/{grant_id}/revoke` 由可信登记表中的租户管理员调用；租户/主体只来自已验证会话，CSRF 取 `X-CSRF-Token`，请求体严格为 `{reason_code:"USER_CANCELLED"}`，重复请求返回同一撤销记录并复用现有锁序。
- OP 元数据、AS 公开密钥文档，以及令牌/内省/发现四条路由的 ASGI 入口。
- `AG-EVIDENCE-1` 单笔未锚定回执的离线签名、摘要、祖先和账本 delta 验证；四个 delta 字段允许有界负整数。
- 真实登录与同意闭环（迁移 `008_login_consent.sql`）：scrypt 口令 KDF、一次性预认证 CSRF、服务端登录会话与会话绑定 CSRF、服务端授权请求持久化、`ag_task_policies` 任务边界读取、state/nonce/redirect/PKCE 校验。`LoginService`、`ConsentService`、`BrowserLoginApp` 已落地；只有批准分支签发一次性授权码，拒绝分支只记录不签发；`ApprovedAuthorization` 只能由同意服务构造。`AuthorizationHttpApp` 在提供浏览器组件时挂载 `GET/POST /oauth/authorize`、`GET/POST /ag/login`、`POST /ag/consent`。
- 开发 TLS 装配（`agent_guard.server`）：`config.py` 严格私有配置加载（明文 secret 只存在于独立 secrets 文件），`factory.py` 全量组装 + 请求超时中间件，`python -m agent_guard.server init/check/run` 生成合成开发密钥与配置、校验并以 uvicorn（0.35.x，BSD-3）启动 TLS；缺 `AGENT_GUARD_DATABASE_URL` 或证书拒绝启动；issuer/证明目标/scheme 只来自配置与可信 ASGI scope，不信任 `Host`/`X-Forwarded-*`（开发启动默认 `--no-proxy-headers`）。真实 TLS 全链路由 CI 集成测试 `tests/integration/test_server_tls.py` 验证（自签开发证书，非生产装配）。
- 密钥轮换与独立实现互验：配置支持 `historical_verification_keys`（旧 `kid` 仅验签、不再签发），`TokenExchangeService`/`IntrospectionService`/`/ag/keys` 同持历史公钥；`tests/integration/test_key_rotation.py` 验证轮换后旧令牌可验签、新令牌由新 `kid` 签发。`tests/integration/test_sm2_interop.py` 用 OpenSSL CLI 作为独立第二实现做双向签名互验及 JWS r||s/DER 转换互验（CI 环境执行）。README 增加密钥生成/分发/轮换/撤销/销毁与泄露处置边界说明。
- B→A1 接缝联调（`tests/integration/test_as_ledger_integration.py`）：真实 PostgreSQL 上由 B 登录/同意签发根、两级 Token Exchange 得到 executor 令牌，B `InvocationVerifier` 产出 `VerifiedInvocation`，交给 A1 `ExecutionLedger.accept` 做加锁预算决定；覆盖被盗令牌/参数篡改拒绝、幂等重试不重复预留、proof 重放拒绝、根与中间祖先撤销后拒绝、内省 active 不代替接受事务。A 的 HTTP 网关、四工具、下游、恢复与证据导出在 `origin/main` 尚未实现，M1—M13 仍不能整体通过。
- 合成 B 授权演示 `python -m tests.demo_b_flow`，不代表完整浏览器或网关流程。

## 未完成的关键闭环

1. 生产化部署边界仍未做：TLS 证书由部署方提供，反向代理只允许可信来源的 `X-Forwarded-*`（当前方案不读取）；密钥轮换的自动调度、HSM/KMS 托管与泄露取证未实现（README 已给出手工流程与局限）。
2. 与 A 的真实 HTTP 网关、四工具、下游执行/恢复及证据导出联调；`origin/main` 当前仍停在 A1（`b120c7c`，无网关/工具/证据导出），已完成的是 B 令牌经 B 验证器进入 A1 `ExecutionLedger.accept` 的接缝联调。M1—M13 不能按局部测试宣称整体通过。
3. 独立检查点尚未实现，`AG-EVIDENCE-1` 只能验证单笔未锚定证据（UNANCHORED），不能声称检测日志回滚。

## 最新验证

- 本机：`ruff check .` 与 `ruff format --check .` 通过；`pytest -q -m "not integration"` 全绿（本机仍无测试 PostgreSQL/openssl，未在本地伪造集成或 TLS 通过）。
- GitHub Actions CI（Python 3.11 + PostgreSQL 16 服务容器）：
  - run #19，head `29bd3e7`：success，覆盖迁移 `008`、登录/同意/换码真实数据库路径与合成演示。
  - run #21，head `3ad3299`：success，额外覆盖会话 + CSRF 撤销 HTTP 路由（任务所有者、租户管理员、跨租户、重复与并发撤销）。
  - run #25，head `f041619`：success，覆盖开发 TLS 装配与真实 HTTPS 全链路（登录→同意→换码→内省→撤销）。
  - run #29，head `34b71d0`：success，覆盖密钥轮换（历史 `kid` 仅验签）与 OpenSSL CLI 独立实现双向互验及 JWS `r||s`/DER 转换。
  - run #31、#32，head `2ee85f5`/`f408c1a`：B→A1 接缝联调（#31 因同测试内先耗尽额度再做重放用例而失败，已拆分为独立用例；#32 success）。
  - 期间 run #23/#24 因 TLS 测试响应头大小写、#27/#28 因 OpenSSL 3 provider 默认 `distid` 与 GB/T 默认不同而失败；均已定位修复（显式 `distid=1234567812345678`）。

## 续跑顺序

登录/同意闭环、撤销 HTTP 路由、开发 TLS 装配、密钥轮换与 OpenSSL 独立互验均已落地；下一步在 `origin/main` 出现 A 的网关/证据导出后做真实 M1—M13 联调，并补独立审计检查点与生产密钥托管/运行手册。
