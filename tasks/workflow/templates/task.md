# <stage> 任务包 v<N>

- 状态：DRAFT / APPROVED（必须对应真人授权，不由实施者自填）
- 当前阶段、技术边界、用户授权消息引用与原文：
- 基线HEAD、真实工作区manifest、冻结任务契约SHA256：
- 必读：AGENT.md、workflow/implementation-contract.md、review-contract.md、context.md、当前stage、原任务/安全/验收、最新review及issues
- 所有路径基于仓库绝对根解析，命令在仓库根运行；从父目录启动的会话不能误读同名路径。
- 首次包审：review_kind=PACKAGE_REVIEW，独立报告/结论 PACKAGE_READY 或 PACKAGE_CHANGES_REQUESTED/BLOCKED；不判代码通过。包审无阻断后才发实施Task。
- 实施后每轮复验：review_kind=IMPLEMENTATION_ACCEPTANCE，全套实际证据；包审报告不得填为state.review。

## 目标、范围和所有权

写清一大段完整行为、允许路径、现有未提交工作、禁止路径/动作、资源归属和后段排除。不只列文件名。

## 固定验收矩阵

每个expected_requirement_id单独写要求、验证方法、测试文件/函数或待新增位置、必要状态/计数/效果断言、故障/并发/重启负例、是否必须独立实跑。不得删减原任务。

## 关键设计和依赖

继承检查点复验的主体义务，记录接口、锁序/状态机/数据保全、B真实交付范围、未决项及失败关闭。需要改变需求的决定先报主控/用户。

## 验证与证据

命令、Python/PG/依赖环境、实现资源和独立review资源隔离策略、日志/JUnit/探针输出路径、脱敏/清理记录。禁止缺库skip和固定测试数量替代覆盖。

## 交付和停止

实施报告路径、原A2-report摘要更新、实际tracked/untracked/deleted清单、状态READY_FOR_REVIEW、停写交主控。阶段内自动返修；本阶段ACCEPTED后主控停等用户批准下一段。
