# Agent Guard 协作交接

更新：2026-10-06。**完整 A2 已独立接受；项目整体 PARTIAL，A3.1—A3.4 尚未实施。** 本协作版本通过 [PR #7](https://github.com/Qdcchh/agent-guard/pull/7) 交付到 `codex/a2.2-integration`，本次不合并 main。审核与 CI 以该 PR 当前实际 head 为准；本地独立接受不等于 GitHub 审核批准。

同学请直接阅读 [A3 完整交接文档](docs/A3-HANDOFF.md)：包含干净克隆、安装/真实 PG/TLS、已有 CLI、安全约束、全部四段目标与验收、实验及最终材料。代码从上述协作分支开始，勿从尚未包含完整 A2 的旧 main 开工。A3 逐段正式建包、独立包审、实施/整合、停写冻结、独立完整验收；本次发布者不实施 A3。

[正式接受记录](tasks/workflow/runs/A2.3-receipts-20261004/acceptance.md)与[完整独立 review-r2](tasks/workflow/runs/A2.3-receipts-20261004/review-r2.md)覆盖 119 项/112 运行义务/269 原断言/41 节点/88 原子；[公共产品指纹](tasks/A2-public-product-manifest.json)核对协作版本与已接受产品、测试、迁移、锁和 CI 字节相同。只调整当前文档与可移植发布范围，未重写 A2 产品代码。历史报告里的候选 HEAD、模型、路径、当时未发布措辞保留其历史含义，不作为同学的环境或调度前置。

source 与 fresh 非 editable wheel 各1185普通＋2810完整PG＋500精确时限通过；source增强原487P，wheel原484P/3F/exit1保留，以原407未受影响PASS＋原模块新完整80逐case闭合。真实SM2/SM3、全祖先预算/撤销、10轮竞争、真进程恢复、AS/GW四工具链、前段/历史与等价探针完成。旧失败、未知原因、工具操作隐私事件及限制见正式报告，不声称原组全绿、生产安全或绝对无缺陷。

回执仍 **UNANCHORED**，单 operation 一致性不等于独立审计完整性；旧无 receipt_keys 配置只兼容 PENDING/null。剩余 A3 为独立检查点/原子日志、有界导出/离线验证、干净部署与三 holder 演示、50 客户端/完整方案至少10000调用及公平对照和最终材料。

原始日志、密钥/数据库、作者电脑运行绑定/进程快照与个人复核调度指南不进入协作发布。历史授权、失败和接受文字原件保留；缺失的本机历史引用及证据访问边界见[发布说明](tasks/workflow/runs/A2.3-receipts-20261004/README.md)。无需作者的本机目录、代理命令或模型配置即可接续。

[当前工作流](tasks/workflow/README.md) · [现行约定](tasks/workflow/current-policy.md) · [上下文](tasks/workflow/context.md) · [问题台账](tasks/workflow/issues.md) · [A3 计划](tasks/A3-plan.md)。保留保护与 CODEOWNERS；本次不合并、不强推、不沿用 PR #6 管理员例外。
