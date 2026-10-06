# 分阶段实施与独立验收工作流

当前：**完整A2已独立接受；协作版本通过PR #7交付，暂不合并；同学接续全部A3，A3仍未实施。** [同学交接](../../docs/A3-HANDOFF.md) · [当前约定](current-policy.md) · [上下文](context.md) · [接受](runs/A2.3-receipts-20261004/acceptance.md) · [完整review-r2](runs/A2.3-receipts-20261004/review-r2.md) · [发布边界](runs/A2.3-receipts-20261004/README.md)。原119/112/269/41/88闭合；历史失败与旧停止保留。

## 正式闭环

1. 主控核真人授权、范围和完整需求，按 [任务模板](templates/task.md)冻结版本化包、精确文件所有权、只读依赖哈希、资源与断言矩阵。
2. fresh reviewer做PACKAGE_REVIEW；PACKAGE_READY不是行为PASS，也不授实施权限。
3. 授权、包审及本段获批运行绑定/适配齐全后派发。共享接口/迁移/依赖/fixtures先串行；worker任务非常适合协作时按独立文件和依赖边界拆分，开合适数量子agent。分工须纳入审包，不同文件也不能消费未冻结的共享半成品。
4. worker自查并交[完整报告](templates/implementation-report.md)、命令退出码/log/JUnit/哈希后停写；主控核全部writer/进程停止、精确范围与资源归属，冻结全部候选。
5. 新独立reviewer按[审查契约](review-contract.md)做IMPLEMENTATION_ACCEPTANCE：完整当段矩阵、历史触发/变体、前段回归、真实PG/并发/进程/故障/负控与起止指纹。历史日志、替身和局部通过不能代替。
6. 按[补正模板](templates/correction.md)保留稳定issue、失败轮和证据；实施者只能标FIXED_PENDING_REVIEW，fresh独立实证才能关闭。范围或需求改变重新审包。
7. 主控读回完整报告与原始证据，无阻断且所有必需验证齐备才接受；缺资料、有效绑定或必需实跑时NOT_ACCEPTED/BLOCKED。最终只声明已验证条件内的结论。

## 门、证据和维护

基础安全与独立性义务见[Codex补充契约](runs/setup/codex-astra-sol-v1/workflow-contract.md)，当前角色以现行约定为准。原 tools/workflow_gate.py及旧机器门保持原样；[state-guide](state-guide.md)描述历史结构，旧state.json是A2.1历史，不得改授权/哈希来制造放行。旧门属于历史运行方式，不是同学个人模型/路径前置；新段记录实际同等回执/冻结/隔离/完整实跑适配；未知有效模型元数据记UNKNOWN，不把请求值冒充后台证明。

[修补前67项目录](runs/local-quality-20261004/requirements-matrix.json)为历史部分查证，不是新阶段验收矩阵。[实施契约](implementation-contract.md)/[复核契约](review-contract.md)继续适用；runs保存正式包、授权、实施/失败/复核/接受记录，artifacts/workflow保存本地Git忽略的脱敏原始证据。干净检出不含原始artifacts，正式报告须自足说明断言、结果及限制。

发现过时、错误、重复或无用的现行内容，随任务修改或删除并修复引用；历史授权、失败/接受证据、SQL及依赖锁保留。只运行和清理可核owner的自有资源，不连接普通部署DSN、不停止无关容器、不绕过平台阻断。旧setup说明原件可从Git2051b40追溯，历史报告中的旧路径不是当前运行依赖。

换模型或新会话可使用[逐阶段接续提示词](continue-prompt.md)；仅用户实际发送才构成授权，不能把模板当真人消息。当前同学接续全部A3，按阶段门依次推进；本次发布者不实施A3、不合并。
