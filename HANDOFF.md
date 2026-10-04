# Agent Guard 当前交接

更新：2026-10-04（Asia/Shanghai）。**B 补正 ACCEPTED，PR #6 已合并 main；整体项目 PARTIAL。** [正式验收](tasks/workflow/runs/local-remediation-20261004/acceptance.md)及 [fresh r2 复核](tasks/workflow/runs/local-remediation-20261004/review-r2.md)：67 项通过、60 项独立运行，source/wheel 各 952＋1388 测试通过。远端 CI 同样通过。

## 1. 实际版本

- 仓库：`/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`；父目录是另一个 Git 仓库，不要混用。
- 已合并产品基线：`d7e91c75014d1097c822936a16559229e2b4906a`，见 [PR #6](https://github.com/Qdcchh/agent-guard/pull/6)。后续文档提交以实时 Git 为准。
- `product-manifest.json` 仅代表 2026-10-03 传输快照，不能当当前清单；历史交接和缺失云端原件的边界保留在正式报告，不冒称已取回原件。

## 2. 已有能力与最终目标

A1 原子账本和 A2.1 四工具执行/租约/恢复/祖先预算/outbox 有历史验收。当前候选加入 B 的真实 SM2/SM3、授权码、两级委托、登录同意、撤销、AS HTTPS、DID/登记绑定、权限快照、证据存储与同事务绑定、只读回执投影。S1—S4 以及 DID 不可变配置快照、回执历史时间窗口、CRLF 迁移兼容、迁移 CLI 超时脱敏、check/run 配置一致性已实施，不能当未做过重新开发。

最终目标仍是用户同意 → 三代理两级收窄委托 → 真实签名工具请求 → 共享预算/幂等/撤销 → 故障恢复 → 可验证回执/审计的采购原型，并在 2026-10-20 前形成部署复现、演示、实验及技术材料。当前进程内接入不等于完整公开网关：A2.2 公开 invoke/最终动态查询、A2.3 持续签发发布、A3 锚定/导出/端到端演示与规模对照实验尚未完成，outbox 保持 PENDING。

## 3. 已关闭问题与证据

结果变体与工具绑定、256 项统一边界、完整祖先 grant 唯一性、P13 全线程异常收集、future-token 真签名分支，以及后续发现的超时负控调度问题，均经 fresh r2 独立复验关闭。完整失败轮、补正和关闭依据见 [问题台账](tasks/workflow/issues.md)，不要把 v1 的 FIXED_PENDING_REVIEW 当当前状态。

## 4. 下一步

先读 [工作流](tasks/workflow/README.md)、[当前上下文](tasks/workflow/context.md)、[现行角色与维护约定](tasks/workflow/current-policy.md)。主 agent 请求 `gpt-6.1-sol / high`，reviewer 请求 `gpt-6.1-sol / xhigh`，worker 仍为 `gpt-6.1-sol / medium`；有效后台元数据未暴露时记 UNKNOWN。

下一业务阶段是 [A2.2](tasks/workflow/stages/A2.2-integration.md)，待用户批准后建包和独立包审；随后 [A2.3](tasks/workflow/stages/A2.3-receipts.md)，最后 A3。每段必须覆盖原始要求、明确接口和精确文件范围、独立资源及全部回归，不能把已有进程内验证重复开发成假接入。旧门未迁移，本轮有限适配不自动延续。

## 5. 文档与资源维护

随任务直接更新过时或错误的当前指引、删除无用重复内容并修复引用；历史授权、失败/验收证据和 SQL/依赖锁保留。已清理自有测试容器及约 674 MiB 缓存，原始证据保留。既有 agent-guard-a2-pg、verivote 等无关资源未改动；以后仅清理可核实归属的资源。代码回退不等于数据库可无损降级。
