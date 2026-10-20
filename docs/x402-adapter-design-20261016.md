# x402 支付适配位置与后续接口草案

2026-10-17 最新：X1–X8 本地测试链阶段已独立 ACCEPTED，见[接受记录](../tasks/workflow/runs/x402-gateway-20261017/acceptance.md)。未知结果保留预算；释放须同时证明授权已过期、配置链正确且 nonce 明确未使用。门限批准已接入网关；下文“拟议/后续”保留原设计语境。

状态（2026-10-17 更新）：本机固定演示已实现，见文末[实现状态](#实现状态2026-10-17-更新)；本文原状态“设计草案、未接入”仅代表 2026-10-16 当时。生产支付链路、真实资产与生产网络仍未实现，本文的接口与状态机说明仍是接入生产的前置设计。

## 协议位置

现有 OAuth/Token Exchange 与 AGPoP 决定代理能否提出并执行某个采购动作。拟议的门限凭据若完成集成，只增加对特定行动的集体批准。x402 则位于获授权行动之后、外部付费资源之前，处理资源服务器给出的支付要求及支付证明。付款成功不能代替当前授权、撤销、预算或业务幂等检查。

```text
结构化采购意图 → 现有网关验权与接受 → 支付适配器 → x402 资源服务器
                                      ↘ 受控支付签名组件 / facilitator
```

## 后续最小接口

适配器的输入须是已经固定的不可变行动，而不是浏览器或模型传来的任意付款对象。内部 `PaymentIntent` 至少绑定 `task_id`、授权路径、行动 ID、业务幂等键、资源 URL、收款方、网络、资产、资产最小单位金额、报价摘要与失效时间；该对象的摘要须与适用的行动批准一致。现有 CNY 整数分预算不直接转换为链上资产单位。跨币种时必须先建立可信报价与兑换边界；没有这一边界时使用独立测试资产预算。

收到 `402 Payment Required` 后，适配器只接受固定版本及明确允许的 scheme/network，逐字段核对资源、收款方、资产、金额和过期时间。报价发生变化时重新取得任务授权和适用的门限批准。支付材料由受控签名组件生成；前端和模型不持有支付私钥，也不把研究用的门限签名直接当作网络支付签名。

状态至少区分 `UNPAID`、`AUTHORIZED`、`SUBMITTING`、`UNKNOWN`、`SETTLED`。发送或结算响应丢失后保留 `UNKNOWN`，先按稳定业务键和交易标识查询或对账，不能把超时当作未付款并立即重付。外部支付和本地预算没有天然原子事务。后续测试须覆盖换收款方、换网络、改金额、报价过期、重复提交和结算超时，并分别记录资源响应与支付终局。

x402 v2 核心规范把 payment flow 的顺序交给 scheme 和网络决定；默认 `authorization` 流程是 verify → resource → settle，另有先 settle 的流程。因此后续实现须先固定 x402 规范/SDK 提交、scheme、network 和测试环境，再按该组合设计状态机，不能把上述默认流程当作所有方案的行为。

参考：[x402 v2 核心规范](https://github.com/x402-foundation/x402/blob/main/specs/x402-specification-v2.md)、[HTTP 传输规范](https://github.com/x402-foundation/x402/blob/main/specs/transports-v2/http.md)。查阅日期：2026-10-16。正式实现时固定具体提交和依赖锁，并按当时规范重新核对。

## 实现状态（2026-10-17 更新）

2026-10-17 授权后，本机测试链固定演示已实现；范围仍是本地演示，不是生产接入。

- **协议与依赖锁**：x402 v2 `exact` / EVM（EIP-3009），固定顺序 verify → resource → settle。规范 pin `x402-foundation/x402@faa1c694c66a3732aaabbce93bdae140e521a67d`（Apache-2.0）；Python SDK `x402[evm]==2.25.0`（MIT，hash-pinned 全闭包在 `requirements-x402.lock`）；本地 EVM 为 Anvil v1.8.5（MIT OR Apache-2.0）；测试代币为可复现编译的 Circle FiatTokenV2_2（Apache-2.0，OZ 3.4.2 MIT）。逐项 provenance、编译配方与许可证见 `dependencies/x402-20261017/README.md`。
- **运行镜像与装配**：`agent-guard-x402-runner:20261017` 扩展未改动的 threshold runner 镜像（Python 3.11.17、Rust 门限签名器、Anvil、SDK 与已编译代币）。构建、部署顺序与 SDK 构造见 `deploy/x402-runner/README.md`。
- **代码与迁移**：`src/agent_guard/x402/`（intent / accept / gate / state / resource / facilitator / chain / signer / wire），新增 `migrations/009_x402_payment.sql`（支付意图、独立资产预算、持久支付状态）；旧 001–008 迁移未改。支付预算独立于 CNY 整数分预算，且随授权撤销一起受祖先检查约束。
- **驱动来源**：适配器只从现有网关已接受的不可变采购操作出发；PaymentIntent 绑定租户/任务、完整授权路径、操作与业务键、资源 URL、收款方、network/chainId、asset、最小单位整数金额、报价摘要与有效期。付款证明不替代 OAuth/SM2/AGPoP/门限批准；换收款方/网络/资产/金额/资源或变更批准对象都会被拒绝。
- **恢复语义**：签名授权与 nonce 在网络发送前持久化；响应丢失或终局不明保持 `UNKNOWN` 且预算保留，按持久 nonce/交易哈希/链事件对账，不当作未付重付；重放先查存储，不重签不同 nonce、不重复结算。真实独立进程恢复有集成测试覆盖。
- **本机演示**：`python3 tools/x402_desktop.py`（或演示页“x402 支付”按钮）在专用 Docker/PG/Anvil 上跑固定用例并自动清理；页面与固定演示仅本机可控制，公网只读。
- **诚实边界**：仅本地测试链与自建测试代币，无真实资产、用户钱包或生产网络；链上签名是 EIP-3009（非 SM2）；演示密钥与门限份额由同一宿主、同一 OS 用户管理；本机演示通过不代表完整项目验收。
