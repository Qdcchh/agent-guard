# 分阶段实施与独立验收工作流

更新：2026-10-05。当前 **A2.2 已完成独立验收 ACCEPTED**，整体 **PARTIAL**。保留HEAD280022e与全部已有修改。最新用户已授权A2.2复核通过后合并，并无论能否合并都继续A2.3、完整验收A2；[真人原话](runs/A2.2-integration-20261004/authorization-expansion-20261004.json)覆盖此前单段停止点。完整A2接受后全部[A3](stages/A3-closure.md)已获[真人授权](runs/A3-closure-20261004/authorization.json)，逐段规划/实施/独立复核。角色、协作与文档维护见[现行约定](current-policy.md)。

## 当前入口与顺序

1. 读取[HANDOFF](../../HANDOFF.md)、[context](context.md)、[本段state](runs/A2.2-integration-20261004/state.json)、[issues](issues.md)及真实Git，不重置工作区。
2. [A2.2 task-v1](runs/A2.2-integration-20261004/task-v1.md)、[95项/88运行义务](runs/A2.2-integration-20261004/requirements-v1.json)、[原授权](runs/A2.2-integration-20261004/authorization.json)、本段有限适配及[PACKAGE_READY](runs/A2.2-integration-20261004/package-review-r1.md)有效；历史包头初始状态不等于现态。
3. **A2.2 ACCEPTED**：fresh [review-r2](runs/A2.2-integration-20261004/review-r2.md)完成95项/88运行义务，source/wheel各1022普通＋1930真实PG及最终独立增强全部通过；两项P2已CLOSED_REVIEWED_R2。主控核619原始哈希、150命令/46JUnit、全285冻结、完整断言/case绑定与实际资源余留0，见[接受记录](runs/A2.2-integration-20261004/acceptance.md)。历史r1否决、四实施轮及全部失败/适配保留；CTX持续回归。下一步发布受验收分支并正式建包A2.3，合并受阻仍继续。
4. 读取[原A2任务](../A2-execution-gateway.md)、接口/安全/验收文档及调用方；B补正[正式接受](runs/local-remediation-20261004/acceptance.md)经PR #6合入d7e91c7，A2.1有历史验收，均为回归基线。
5. A2.2接受后按实际CI/审核处理merge；合并阻碍不阻止已授权[A2.3](stages/A2.3-receipts.md)和完整A2验收。后段[有限适配](runs/A2.3-receipts-20261004/runtime-addendum-proposal.md)已[批准](runs/A2.3-receipts-20261004/authorization.json)，正式包与独立PACKAGE_READY须先完成。PR #6管理员例外不继承；新例外须先准备可审PR和通过CI再询问。

| 阶段 | 当前范围 |
| --- | --- |
| A1/A2.1/B | 已有验收/合并，持续全部回归 |
| A2.2 | 95/88 fresh r2 ACCEPTED；Git发布与实际CI/审核另核 |
| A2.3 | 已授权在A2.2接受后续接：持续真实签发/恢复/完整P18/P21和A2联合验收；本段适配已批准、正式包审待完成 |
| A3 | 完整A2接受后已授权四段持续闭环，含本地复现部署/演示/实验；未实施 |

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
