# 分阶段实施与独立验收工作流

当前恢复检查点：NEW完整A2独立reviewer r1已原生FINAL STOP、自有资源0，主控完整读回；结论 **NOT_ACCEPTED**。P2 `A23-R1-PUBLISH-QUOTE-ARITHMETIC` 为OPEN_CONFIRMED：损坏quote/result一致却算术错误仍签READY，正常SQL不可变保护有效。原source完整2798P/1F/exit1、wheel2799P/exit0及中断/失败全保留。正式原文见 tasks/workflow/runs/A2.3-receipts-20261004/review-r1.md；当前补正 task-remediation-r2 与13文件所有权已由新 Astra medium 独立包审 PACKAGE_READY，报告见 tasks/workflow/runs/A2.3-receipts-20261004/package-review-remediation-r2.md；主控已核原生 FINAL STOP/完整指纹/资源0，正调度唯一 Sol medium worker。补正后完整自查与全新reviewer119/112必须重做；本次不实施A3，不提交/发布未接受候选。以下旧冻结前措辞属于该时点记录，不能替代当前真实执行。

更新：2026-10-05。真人已[恢复A2](runs/A2.3-receipts-20261004/user-resume-20261005.md)，覆盖此前取消指令。本次完成整合、完整自查、新独立119项/112运行义务验收、必要补正和Git交付；实际CI与审核满足后合并main，更新交接并停止，不实施A3。完整A2当前NOT_ACCEPTED。

## 当前入口与顺序

先核项目自身真实Git、远端和PR，再读[HANDOFF](../../HANDOFF.md)、[context](context.md)、[现行约定](current-policy.md)、[state](runs/A2.3-receipts-20261004/state.json)、[issues](issues.md)、原A2任务、接口/安全/验收文档和实际调用方。

A2.2 [正式接受](runs/A2.2-integration-20261004/acceptance.md)为95项/88运行义务；PR #7最后实际OPEN、HEAD138c08a、CI SUCCESS、审核REVIEW_REQUIRED，交付时再次核实。A2.3 [v3任务包](runs/A2.3-receipts-20261004/task-v3.md)、requirements/node-bindings/ownership-v3及[消费者包审](runs/A2.3-receipts-20261004/package-review-consumers-r1.md)已PACKAGE_READY；旧pending和初始NOT_CREATED字段属于历史冻结，不覆盖当前真实原生STOP与运行。core、CLI、HTTPS及[sole29联合整合与完整自查](runs/A2.3-receipts-20261004/implementation-resume-r1.md)已原生停写，自有资源0；新完整独立IMPLEMENTATION_ACCEPTANCE仍须亲自执行。具体本轮入口：[恢复整合包](runs/A2.3-receipts-20261004/task-resume-integrator-r1.md)。

[当前有限运行绑定](runs/A2.3-receipts-20261004/runtime-binding-resume-r1.json)有持续真人批准，有效metadata未暴露记UNKNOWN。旧机器门保持原样，不降低验收。B/A1/A2.1/A2.2持续完整回归；局部自查、PACKAGE_READY和历史日志不是完整A2接受。A3仅保留[已有接续规划](../A3-plan.md)，不自动实施。旧[停止记录](runs/A2.3-receipts-20261004/user-stop-20261005.md)作为历史证据保留。

## 正式闭环

1. 主控核真人授权、范围和完整需求，按 [任务模板](templates/task.md)冻结版本化包、精确文件所有权、只读依赖哈希、资源与断言矩阵。
2. fresh reviewer做PACKAGE_REVIEW；PACKAGE_READY不是行为PASS，也不授实施权限。
3. 授权、包审及本段获批运行绑定/适配齐全后派发。共享接口/迁移/依赖/fixtures先串行；worker任务非常适合协作时按独立文件和依赖边界拆分，开合适数量子agent。分工须纳入审包，不同文件也不能消费未冻结的共享半成品。
4. worker自查并交[完整报告](templates/implementation-report.md)、命令退出码/log/JUnit/哈希后停写；主控核全部writer/进程停止、精确范围与资源归属，冻结全部候选。
5. 新独立reviewer按[审查契约](review-contract.md)做IMPLEMENTATION_ACCEPTANCE：完整当段矩阵、历史触发/变体、前段回归、真实PG/并发/进程/故障/负控与起止指纹。历史日志、替身和局部通过不能代替。
6. 按[补正模板](templates/correction.md)保留稳定issue、失败轮和证据；实施者只能标FIXED_PENDING_REVIEW，fresh独立实证才能关闭。范围或需求改变重新审包。
7. 主控读回完整报告与原始证据，无阻断且所有必需验证齐备才接受；缺资料、有效绑定或必需实跑时NOT_ACCEPTED/BLOCKED。最终只声明已验证条件内的结论。

## 门、证据和维护

基础安全与独立性义务见[Codex补充契约](runs/setup/codex-astra-sol-v1/workflow-contract.md)，当前角色以现行约定为准。原 tools/workflow_gate.py及旧机器门保持原样；[state-guide](state-guide.md)描述历史结构，旧state.json是A2.1历史，不得改授权/哈希来制造放行。当前尚无完整机器门移植，有限人工与工具适配仅按本段明确批准的对象使用；未知有效模型元数据记UNKNOWN，不把请求值冒充后台证明。

[修补前67项目录](runs/local-quality-20261004/requirements-matrix.json)为历史部分查证，不是新阶段验收矩阵。[实施契约](implementation-contract.md)/[复核契约](review-contract.md)继续适用；runs保存正式包、授权、实施/失败/复核/接受记录，artifacts/workflow保存本地Git忽略的脱敏原始证据。干净检出不含原始artifacts，正式报告须自足说明断言、结果及限制。

发现过时、错误、重复或无用的现行内容，随任务修改或删除并修复引用；历史授权、失败/接受证据、SQL及依赖锁保留。只运行和清理可核owner的自有资源，不连接普通部署DSN、不停止无关容器、不绕过平台阻断。旧setup说明原件可从Git2051b40追溯，历史报告中的旧路径不是当前运行依赖。

换模型或新会话可使用[逐阶段接续提示词](continue-prompt.md)；仅用户实际发送才构成授权，不能把模板当真人消息。明确只做A2.2时，其范围限制优先于模板中下一未完成阶段的通用选择。

当前接续入口：[state](runs/A2.3-receipts-20261004/state.json)、[恢复授权](runs/A2.3-receipts-20261004/user-resume-20261005.md)、[v3完整任务包](runs/A2.3-receipts-20261004/task-v3.md)。sole29完整自查已停写→CI预算45→75独立审查已通过→全候选冻结→NEW独立完整119/112验收；失败同段补正后换新reviewer完整复验；正式接受后Git交付和条件合并，更新交接并停止。

当前完整验收入口：[正式119/112独立任务](runs/A2.3-receipts-20261004/task-full-acceptance-resume-r1.md)。CI小包仅PACKAGE_READY/CI_ONLY_CHANGE_REVIEWED，不代替业务验收或新HEAD实际CI；完整A2仍NOT_ACCEPTED。
