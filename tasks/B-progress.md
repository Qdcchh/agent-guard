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
- 合成 B 授权演示 `python -m tests.demo_b_flow`，不代表完整浏览器或网关流程。

## 未完成的关键闭环

1. 生产化部署边界仍未做：TLS 证书由部署方提供，反向代理只允许可信来源的 `X-Forwarded-*`（当前方案不读取）；密钥轮换、销毁与泄露处置手册待写。
2. 与 A 的真实网关、下游、证据导出集成；B 验证器尚无 A 导出的真实最终回执。M1—M13 不能按局部单测宣称整体通过。
3. SM2 第二独立实现互验、历史密钥配置/轮换、完整审计检查点与部署运行手册。

## 最新验证

- 本机：`ruff check .` 与 `ruff format --check .` 通过；`pytest -q -m "not integration"` 全绿（本机仍无测试 PostgreSQL/openssl，未在本地伪造集成或 TLS 通过）。
- GitHub Actions CI（Python 3.11 + PostgreSQL 16 服务容器）：
  - run #19，head `29bd3e7`：success，覆盖迁移 `008`、登录/同意/换码真实数据库路径与合成演示。
  - run #21，head `3ad3299`：success，额外覆盖会话 + CSRF 撤销 HTTP 路由（任务所有者、租户管理员、跨租户、重复与并发撤销）。
  - run #25，head `f041619`：success，覆盖开发 TLS 装配与真实 HTTPS 全链路（登录→同意→换码→内省→撤销）；期间 run #23/#24 因 TLS 测试读取响应头大小写问题失败，已定位修复。

## 续跑顺序

登录/同意闭环、撤销 HTTP 路由与开发 TLS 装配已落地；下一步与 A 的网关/账本/证据导出进行真实联调（M1—M13），并补 SM2 第二实现互验与密钥轮换/独立检查点。
