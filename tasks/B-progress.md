# B 角色进度与续跑入口（2026-10-01）

分支：`feature/fjr-B-character`，PR #3。此记录只描述已落地代码与待办，不替代 [`docs/acceptance.md`](../docs/acceptance.md) 的 M1—M13 验收。不要将分支推送等同于合并 main。

## 已落地

- SM2/SM3 JWS、AG-Proof、DID/企业登记校验、静态验权 SDK 与严格工具参数校验。
- 一次性授权码兑换、根令牌/ID Token 签发、两层 AS 签发的事务性 Token Exchange。
- 任务所有者撤销、租户管理员登记及节点子树撤销的数据库事务；网关独立凭据内省。
- OP 元数据、AS 公开密钥文档，以及令牌/内省/发现四条路由的 ASGI 入口。
- `AG-EVIDENCE-1` 单笔未锚定回执的离线签名、摘要、祖先和账本 delta 验证；四个 delta 字段允许有界负整数。
- 合成 B 授权演示 `python -m tests.demo_b_flow`，不代表完整浏览器或网关流程。

## 未完成的关键闭环

1. 真实用户登录、会话、浏览器 `/oauth/authorize`、`/ag/consent`、CSRF、state/nonce/redirect 绑定及服务端任务政策读取。`ApprovedAuthorization` 只能从可信同意结果构造，绝不能接受外部自报 user_id/额度。
2. 任务/节点撤销的会话授权与 CSRF HTTP 路由；目前只有可信进程内事务组件。
3. TLS ASGI 服务器/反向代理装配、私有凭据初始化与部署验证。ASGI scope 的 `scheme` 必须由可信服务器准确设置；不能信任任意 `X-Forwarded-*`。
4. 与 A 的真实网关、下游、证据导出集成；B 验证器尚无 A 导出的真实最终回执。M1—M13 不能按局部单测宣称整体通过。
5. SM2 第二独立实现互验、历史密钥配置/轮换、完整审计检查点与部署运行手册。

## 续跑顺序

先阅读 `AGENT.md`、README 与三个设计/验收文档，检查分支和工作区；再实现可信登录/同意会话与授权请求持久化，补拒绝/并发/恢复测试。随后装配管理路由和 TLS 服务，再与 A 的网关/证据导出进行 M1—M13 联调。每节点运行 `python -m ruff check .`、`python -m ruff format --check .`、`python -m pytest`；本机无 Docker/测试 PostgreSQL 时不能将失败的集成测试当作通过，使用 GitHub CI 的真实 PostgreSQL 结果核验。只向现有 B 分支提交/推送，不自行合并 main。
