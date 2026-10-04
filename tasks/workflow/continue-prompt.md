# 换模型后的接续提示词

将下面整段发给新的主会话；主会话在界面选择 `gpt-6.1-sol / high`。这段文字只有用户实际发送后才构成本段授权，文件自身不是授权。

```text
请继续 Agent Guard 项目，仓库为 /Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff，不要误用父目录的另一个 Git 仓库。

先读取 AGENTS.md、AGENT.md、HANDOFF.md、tasks/workflow/README.md、tasks/workflow/current-policy.md、tasks/workflow/context.md、tasks/workflow/issues.md、tasks/workflow/stages/A2.2-integration.md、tasks/workflow/stages/A2.3-receipts.md，以及 tasks/A2-execution-gateway.md、docs/oauth-oidc-sm2-mvp.md、docs/security-model.md、docs/acceptance.md和相关实现测试；检查真实 Git 分支、工作区改动及远端状态。不要依赖上一个模型的上下文，也不要覆盖已有未提交文档。B 补正已通过独立验收并由 PR #6 合入 main，产品基线 d7e91c75014d1097c822936a16559229e2b4906a。历史报告是证据，不是当前待办。

本次只授权继续下一个尚未完成的大阶段：若 A2.2 尚未正式接受就做 A2.2；只有 A2.2 已正式接受才做 A2.3。若两段都已正式接受，请先汇报并提出 A3 任务包，不自动开展 A3。先简要说明本次阶段、交付目标和已存在的能力，再按工作流推进；不要重复开发已验收部分。

主 agent 使用 gpt-6.1-sol/high；实施 worker 使用 gpt-6.1-sol/medium；每次包审和每轮实现验收使用新的独立 gpt-6.1-sol/xhigh reviewer。实际后台配置无法核实就记 UNKNOWN，不伪造元数据。主控先建立完整版本化任务包、精确文件范围、需求/断言矩阵与独占资源方案，独立包审通过后才实施。原本轮有限运行适配不自动继承；如果原生运行门仍有缺口，先写出适用于本阶段的具体适配方案并向我确认，这不影响已经明确授权的阅读和建包。

在本次获批阶段内持续完成实施、自查、停写冻结、独立完整验收、缺陷补正和新 reviewer 复验。保留真实签名、真实 PostgreSQL、并发/进程恢复、source/wheel 及前段回归等完整要求；不跳过、不降低断言，不用历史日志代替独立实跑。每次只完成这一大阶段，通过后停止，向我说明验收证据、局限和下一段建议，不自动进入下一阶段或部署。

发现过时、错误、重复或无用的现行文档内容，应随任务修改或删除并修复引用。历史授权、失败/验收记录、原始证据、迁移与依赖锁不得因“过时”删除或改写事实。交接状态以当前事实为准。

本次也授权通过验收后的 commit、push 和创建 PR；合并仍需 CI 和仓库审核条件满足。PR #6 的管理员审核豁免仅限那一次，不自动复用；如再次需要例外，先提供可审 PR 和通过的 CI，再询问我。任何真正阻塞、范围变更或需我决定的问题及时提出，其余在已有授权范围内继续推进。
```

每段结束后再发送同一提示词，会依据正式接受状态选择 A2.2 或 A2.3；A3 必须另外明确批准。可以在最后追加本轮时间、资源或交付限制。切换模型前后都保留当前 checkout；新会话先读 Git 状态，不要重置文档改动。
