# 门限批准接入采购网关（2026-10-17）

> 2026-10-17 后续：x402 本机固定演示同日已实现（真实 HTTP 402 + EIP-3009 + 本地测试链结算），见 [x402 设计文档的实现状态](x402-adapter-design-20261016.md)。本文以下内容保留当时阶段记录；文中“不做 x402”“未实现”仅指该阶段范围。

2026-10-17 真人授权：一路完成门限批准接入采购网关及必要安全验证，不做 x402、不恢复
A3.3/A3.4 长实验、不 Git 发布。本页描述**本轮已实现内容、可复现命令与局限**；本轮
已通过 fresh Astra 的独立实施验收（仅 T1–T8，50 个不同检查最终通过）。
[接受记录](../tasks/workflow/runs/threshold-gateway-20261017/acceptance.md)保留范围、失败/中断
及证据入口；整体项目仍为 PARTIAL。

## 1. 已实现（T1–T8）

| 项 | 实现 | 关键位置 |
|---|---|---|
| T1 | 真实 FROST-Ed25519 2-of-3 组签名在现有 `/v1/invocations` 上验证并接入真实 SM2/AGPoP 与采购执行链；组验签用固定 Rust 库产生签名、Python 用成熟 `cryptography==50.0.2` 验证（非自研密码、非假验签） | `tools/threshold_demo/`、`src/agent_guard/threshold/verifier.py` |
| T2 | 可信服务端配置决定 `procurement.order.create` 必须携带批准；同一策略在现有 invoke 路由强制，请求不能选择开关；未配置的既有部署保持原行为；组公钥/策略版本/epoch 只来自配置 | `gateway/config.py`、`gateway/endpoint.py`、`gateway/http_app.py` |
| T3 | 版本化 detached 批准头（`ag-approval`）；绑定租户、任务、完整 root→leaf 授权路径、holder/kid、工具与版本、幂等键、规范参数摘要、金额/币种/报价、action_id、策略版本、key epoch 与有效期；V2 消息域独立，V1 字节不变；跨语言向量 | `threshold/codec.py`、`threshold_demo/src/lib.rs`、`tests/public-vector-v2.json` |
| T4 | 在现有接受事务内比较批准与**实际**操作/可信成本，并原子写持久 action_id→操作/消息绑定；ON CONFLICT 不覆盖，回滚不消耗批准；新增迁移 008 | `threshold/binding.py`、`ledger/service.py`、`migrations/008_threshold_approval.sql` |
| T5 | 批准不替代当前授权、祖先撤销、预算与 proof 新鲜性；锁后最终 DB 时钟再查批准过期（在所有 deferred 约束、journal、证据/发布之后）；接受后内部恢复按不可变意图，不需要重新签批准 | `ledger/service.py::_final_bound_check`、`execution/verified.py` |
| T6 | 真实 PG + 独立下游的 24 个门限集成用例：有效→一单、缺批准、1-of-3/重复/假签名、篡改、过期、锁后过期、祖先撤销、并发重复批准、回滚不烧批准、新进程重启、下游成功失响应恢复、同操作禁止换批准、策略范围、旧部署兼容、持久行不可变 | `tests/integration/test_threshold_gateway.py` |
| T7 | 本机可启动固定门限采购演示（脱敏 JSON 结果）与前端最小入口；公网保持只读；有效批准→一单，不足/篡改/撤销拒绝 | `tools/threshold_gateway_demo.py`、`tools/teacher_demo_server.py`、`web/teacher-demo/app.js` |
| T8 | 本页文档、`tools/threshold_demo/README.md` 更新与复现命令 | 本页 |

## 2. 批准凭据契约（V2）

`ag-approval` 头是 base64url（无填充）编码的规范 JSON。以下省略行动字段的结构示意不是可直接解析的 JSON；完整可解析示例见 `tools/threshold_demo/tests/public-vector-v2.json`：

```text
{"profile":"AG-THRESHOLD-APPROVAL-1",
 "action":{...24 个固定字段...},
 "signature":"<64 字节 Ed25519 组签名的 base64url>"}
```

action 字段顺序（即签名消息中的 JSON 顺序）：

```
version(=2), tenant_id, task_id, root_grant_id, grant_id, path_grant_ids[],
holder_client_id, holder_kid, audience, tool_id, tool_version, currency,
policy_version, key_epoch, action_id, idempotency_key, request_id, quote_id,
quote_version, items[{sku,quantity}], delivery_id, amount_fen,
canonical_params_sha256, expires_at
```

签名消息为 `AGENT-GUARD-THRESHOLD-ACTION-V2\n` 加上上述顺序的确定性 JSON。
`canonical_params_sha256` 是订单参数结构（request_id、quote_id、quote_version、
items、delivery_id）按同一顺序的 SHA-256。V1 原型消息域与字节保持冻结，仅新增 V2
（`tool_version` 与完整路径在 V1 中缺失）。

严格拒绝：重复 JSON 成员、未知字段、浮点/负数/布尔当整数、非规范 base64url、
非规范 envelope 字节、超长头/包、重复 `ag-approval` 头、错误字段类型、路径与
root/leaf 不一致、重复 SKU/参与者、错误摘要、未知版本。

可信配置（私有 config.json，示例值非密钥）：

```json
{
"threshold_approval": {
  "group_public_key": "<32 字节小写 hex>",
  "policy_version": 3,
  "key_epoch": 5,
  "max_lifetime_seconds": 300
}
}
```

启动时严格校验字段完整、hex 长度、版本/epoch 正值与有效期上界；缺节即保持旧行为，
但该部署的 order.create 不接受也不要求批准头。新的本机固定演示装配强制包含该节。

## 3. 接受事务与持久绑定

1. 网关在接受事务外验证 SM2 令牌/AGPoP 与门限组签名，并核对批准与已验请求事实；
2. 现有 `TrustedAcceptBinding.compose` 组合出**每次调用**的回调：在实际操作行/既有
   操作上比较批准（重试用持久化的原始报价与成本，绝不用今天的目录重定价），并写
   `ag_threshold_approvals`（`ON CONFLICT DO NOTHING`，永不覆盖；并发/重复必须与
   原绑定完全一致，否则 `APPROVAL_MISMATCH`）；
3. 组合绑定的 final check 在 `SET CONSTRAINTS ALL IMMEDIATE`、journal、证据/发布
   之后读取数据库时钟：批准已在事务期间过期时回滚整个接受（`EXPIRED`）；
4. 任一失败回滚操作、预算预留、proof 注册、证据链接与批准绑定；批准可安全重试。

迁移 008 新表 `ag_threshold_approvals`：主键 `(tenant_id,task_id,action_id)`、
操作唯一索引、完整路径/金额等 CHECK、UPDATE/DELETE 触发器拒绝与 REVOKE；不修改任何
历史迁移或历史行。`pyproject.toml` wheel data-files 与 `lineage.py` 清单均包含该
文件（sha256 `2349e755...`）。

## 4. 可复现命令

```sh
# Rust 原型与 V2 向量（本机 Rust 1.99/1.94 均可）
cd tools/threshold_demo
cargo test --locked          # 6 旧 + 7 新（V2）
cargo fmt --check
python3 tests/verify_vector.py tests/public-vector.json
python3 tests/verify_vector.py tests/public-vector-v2.json
cd ../..

# 组合 runner（Python 3.11 + linux Rust 签名器）
docker build --platform linux/amd64 -f deploy/threshold-runner/Dockerfile \
  --build-arg PYTHON_BASE=<项目 wheel 模式镜像> -t agent-guard-threshold-runner:local .

# 单元、门限集成（真实 PG/SM2/FROST/独立下游）与固定演示
export AGENT_GUARD_TEST_DATABASE_URL="<test-only DSN>"
docker run --rm -v "$PWD":/work -w /work -e PYTHONPATH=/work/src \
  -e AGENT_GUARD_TEST_DATABASE_URL agent-guard-threshold-runner:local \
  /opt/venv/bin/python -m pytest tests/unit/test_threshold_contracts.py \
  tests/unit/test_threshold_config.py tests/integration/test_threshold_gateway.py -q
docker run --rm -v "$PWD":/work -w /work -e PYTHONPATH=/work/src \
  -e AGENT_GUARD_THRESHOLD_DEMO_DSN="$AGENT_GUARD_TEST_DATABASE_URL" \
  agent-guard-threshold-runner:local \
  /opt/venv/bin/python tools/threshold_gateway_demo.py
```

本轮实际结果（worker 自查，非独立验收）：Rust 13 passed、`cargo fmt --check` 通过；
Python 新单元 22 passed；门限集成 24 passed；固定演示 6/6 用例通过、下游订单 1、
资源剩余 0；`ruff check`/`ruff format --check` 全库通过；非集成全量 1803 passed，
4 个失败均为与本轮无关的既有文档措辞断言与容器 root 权限用例（见 REPORT）。

## 5. 演示与前端

`tools/threshold_gateway_demo.py` 使用真实 AS 签发链、真实网关、真实 PG 与独立下游，
运行：缺批准 → 401；1-of-3/重复参与者被 Rust 签名器拒绝、假签名 → 401；有效批准 →
一单且重试不重复；篡改金额 → 409；祖先撤销 → 403。结果写到
`artifacts/threshold-gateway-demo-live/<run id>/result.json`（脱敏：只有状态码、计数、
资源剩余与限制），并清理自有 schema/下游库/份额材料。

先启动 Docker Desktop，再双击桌面“Agent Guard 服务器”的启动入口；本机页面为
`http://127.0.0.1:18765/#threshold`，状态与公网链接见 `/server`。门限面板新增“运行固定演示”按钮，显示脱敏用例结果；公网监听仍无 POST/控制 token，维持
只读。页面整体设计不变，只更新门限状态与接入入口。

按钮实际调用标准库宿主启动器 `tools/threshold_desktop.py`，自动创建隔离网络与临时
PostgreSQL，容器内运行上述真实演示，结束后按 owner 标签和完整 ID 清理。无需手工
设置 DSN 或在 Mac 安装密码依赖。也可在仓库根目录运行
`python3 tools/threshold_desktop.py`。当前 Mac 已缓存运行镜像；镜像重建依赖项目 wheel
基础镜像，跨机器部署需先按 `deploy/threshold-runner/README.md` 准备。

## 6. 局限（必须与实现一起陈述）

- **同宿主教学部署**：签名份额、网关、数据库在同一台机器、同一 OS 用户管理；不是
  独立组织隔离，不能证明“哪两个人”批准，只证明 2-of-3 组密钥批准了该行动。
- **可信初始化**：组密钥由可信 dealer 一次性生成；演示不实现份额分发、硬件保护或
  dealer 擦除的真实流程。
- **非 SM2 门限**：组签名是 FROST-Ed25519；SM2/SM3 仍只用于现有令牌/AGPoP/回执，
  不把组签名当 SM2。
- **依赖边界**：Rust 原型的上游 NCC 审计针对 v0.6.0，不是固定的 v3.0.0。
- **无 x402**：支付链路仍只有设计文档，未实现。
- **未完成的 A3 验收**：本轮不构成 A3.3/A3.4 联合验收，不宣称生产可用；公网演示仍
  只读；历史证据与失败保持原样。
- 旧版（无 `threshold_approval` 配置）部署行为不变：这是明确的兼容性说明，不是
  “默认开启门限”的声明。
