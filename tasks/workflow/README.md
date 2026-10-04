# 分阶段实施与独立验收工作流

更新：2026-10-04。当前角色和交付以 [现行约定](current-policy.md) 为准；基础义务采用 [Codex 补充契约](runs/setup/codex-astra-sol-v1/workflow-contract.md)；旧 OpenCode 启动命令和初始等待状态已移除。原实施/审查契约保留其安全、独立性和证据义务，角色配置以现行约定为准，工具绑定遵循基础契约与本阶段明确获批的适配。

## 恢复顺序

1. 阅读 [HANDOFF](../../HANDOFF.md)、[当前上下文](context.md)、[当前正式验收](runs/local-remediation-20261004/acceptance.md)、[问题台账](issues.md) 和真实 Git 状态。
2. 阅读 [原 A2 任务](../A2-execution-gateway.md)、设计/安全/验收要求及相关实际实现/测试；历史完成记录不能替代当前证据。
3. 当前 B 整合补正已通过 [fresh r2独立验收](runs/local-remediation-20261004/review-r2.md)，67项/60独立运行全部完成；PR #6 已合入 main（`d7e91c7`），CI 全通过；具体授权与交付见现行约定。A2.1 已有 [历史验收](runs/A2.1-core/acceptance.md)，不得从“尚未实施”重新开工，也不得因旧 state.json 的 ACCEPTED 放行当前 B 分支。
4. 本轮生效包为 [task-v1](runs/local-remediation-20261004/task-v1.md)，用户已明确批准 [运行适配](runs/local-remediation-20261004/runtime-addendum-proposal.md)，授权记录见 [authorization](runs/local-remediation-20261004/authorization.json)。[新独立包审](runs/local-remediation-20261004/package-review-r1.md) 为 PACKAGE_READY，B 验收时控制记录见 [本轮 state](runs/local-remediation-20261004/state.json)。原五项与新增超时负控已由新独立完整验收关闭；失败轮与补正保留，不改旧状态或冒用旧会话。

## 阶段和停止点

| 阶段 | 范围和停止点 |
| --- | --- |
| A2.1-core | 执行/恢复核心有历史验收；新发现继承缺陷仍需按明确范围补正 |
| B-remediation-integration | 本轮ACCEPTED；67项/60独立运行全通过，整体项目仍PARTIAL |
| A2.2-integration | 真实公开 HTTP 调用与最终动态查询；另行批准并建立正式包 |
| A2.3-receipts | 持续真实签名发布、故障恢复、完整 A2 联合验收；另行批准 |
| A3 | 锚定、导出、完整演示和实验；不得自动进入 |

每一大阶段结束保存完整结论并停给用户查看。用户已单独授权本轮验收通过后的 Git 发布及条件合并；后续开发阶段和部署未获授权。

## 正式闭环

1. 主控核对真实用户授权、范围和完整要求，按 [任务模板](templates/task.md) 冻结版本化包、精确文件所有权、只读依赖哈希、资源及测试矩阵。
2. 新 reviewer 做 PACKAGE_REVIEW；PACKAGE_READY 不是实现验收，也不授实施权限。
3. 在授权、包审、运行绑定和门要求均满足后派发。共享接口/迁移/依赖/fixtures 串行；其余仅在无文件冲突时并行，不消费同批半成品。
4. worker 自查、提交 [完整报告](templates/implementation-report.md) 和日志/JUnit/输出哈希后停写；主控核实全部 writer/进程停止、范围和资源归属，再冻结候选。
5. 新 reviewer 按 [审查契约](review-contract.md) 做 IMPLEMENTATION_ACCEPTANCE：完整本段矩阵、历史失败、前段回归、独立真实 PG/并发/进程/故障与负控、起止指纹。旧日志、替身和局部通过不能代替。
6. 按 [补正模板](templates/correction.md) 保留稳定 issue ID、失败轮和证据，实施者只能标 FIXED_PENDING_REVIEW；新独立复验才能关闭。范围/需求改变重新审包。
7. 主控核对原始证据和全矩阵，无阻断且正式门有效通过后才接受；缺资料/绑定/必需实跑时 NOT_ACCEPTED/BLOCKED。

## 门与状态的边界

`tools/workflow_gate.py` 保留原样；[state-guide](state-guide.md) 描述旧结构。`state.json` 是 A2.1 历史验收记录，包含旧项目路径和未随 Git 交付的证据引用，当前分支对它运行 require-accepted 会失败。不要通过更新旧授权、删除要求或重写哈希制造通过。

[67 项恢复目录](runs/local-quality-20261004/requirements-matrix.json) 仅记录修补前当时的部分查证/未完成项，不是正式验收矩阵、新阶段 state 或机器门移植。本轮采用用户明确批准的有限人工与工具证据适配，保持67/60义务，不宣称已迁移通用机器门；JSON 声明不证明真实模型、权限或停止状态。

## 文档和资源

- [context.md](context.md)：当前状态及下一步；[issues.md](issues.md)：历史和当前缺陷生命周期。
- [implementation-contract.md](implementation-contract.md)、[review-contract.md](review-contract.md)：实施和独立复核义务。
- runs：正式任务包、实施/审查/失败/验收历史；本轮有限质量报告单独保存，不冒充正式验收。
- artifacts/workflow：脱敏原始命令、日志/JUnit、探针、指纹与资源证据，Git 忽略；不存可用凭据。
- 只运行与清理可核验自有资源，普通部署 DSN 不作为测试目标，不停无关容器，不绕过平台阻断。

已被替代的 `runs/setup/20261001-setup.md` 配置记录已删除；其原件及旧启动说明可从 Git `2051b40` 追溯。历史包审中的该路径只是当时读取清单，不是当前运行依赖。

换模型或新会话时使用 [逐阶段接续提示词](continue-prompt.md)。提示词必须由用户实际发送才形成授权，不能把仓库中的模板当成用户消息。
