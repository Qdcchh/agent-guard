# 分阶段实施与独立验收工作流

这套入口保留原有 agent 和会话。主控 `orchestrator-auto` 使用 GPT 6.1 Sol medium；实施子 agent `mimo-implementer` 使用 MiMo 2.6 Pro；每轮新的 `reviewer-auto` 使用 GPT 6.1 Sol xhigh。配置在用户的 OpenCode agents 目录，所有项目任务和验收要求继续保存在本目录 Markdown 中。`subagent_depth=1`，不加显式 steps，不启用 Flash 并行或嵌套委托。

## 当前切换点

检查点一补正复验已通过，依据 `../A2-review-ckpt1-r2.md`。这仅达到 A2.1 主体开工的技术门槛；A2.1 核心尚未实现/验收。新工作流初始 `current_stage=A2.1-core`、`status=AWAITING_USER_APPROVAL`、`authorization.status=PENDING`。本次配置授权不等于实施授权。首先读 `context.md`、`state.json` 和 `stages/A2.1-core.md`，向用户展示将实施的范围，等用户批准。

## 大阶段与人审批

| 阶段 | 本阶段收尾 | 必须停下的位置 |
| --- | --- | --- |
| A2.1-core | 检查点二；独立于 B 的执行/恢复核心；核心验收通过，完整 A2 仍 PARTIAL | 独立复验、补正、再复验全部完成后，停等用户批准 A2.2 |
| A2.2-integration | 已确认且验收的 B 验证器/权限/证据与真实 HTTP、result-read | 本阶段独立复验通过后，停等用户批准 A2.3 |
| A2.3-receipts | 真实 SM2 回执及完整 A2 联合验收 | 完整 A2 验收通过后停等用户；不自动进入 A3或Git集成 |

同一已批准阶段内部的详细复核、所有针对性补正及再复核自动推进，不每个小修复都问用户。实现存在缺陷时不因“实现者完成”停止，而是交回 MiMo 修到满足要求；外部依赖、需要更改需求或反复无新进展时明确 BLOCKED 并停下。

每个大阶段结束都保留当前阶段及其 ACCEPTED 记录，向用户报告实际结果、限制、证据和下一阶段提案。不得自动将 state 切到下一阶段，不先写其业务代码、不先拉入 B、不提前为下一阶段开资源。原任务中的“可以继续已确认的 B 对接”是技术条件，本工作流的新用户要求额外规定阶段间必须人审批。

## 正式开始和恢复

1. 原 Go-Main 停止写入，检查工作区；不覆盖既有修改。已备份旧配置和 OpenCode 历史，但备份不是回退当前代码的指令。
2. 重启 OpenCode 后，从原 Orchestrator 会话分叉并显式选择 `orchestrator-auto`，保留规划历史；原 Go-Main/旧 reviewer 历史保留作参考。分叉不克隆原子会话树，旧 task_id 不能续用为新流程子会话。
3. 在原启动目录使用下面的命令（配置已经落盘；该命令由用户选择何时运行，配置过程没有替用户分叉会话）：

```zsh
cd /Users/qdcc/code/密码技术竞赛
setproxy
opencode --session ses_f0e893afcffeMRWvuS4UsK3x20 --fork --agent orchestrator-auto --model openai/gpt-6.1-sol
```

启动后第一条指令可以是：

> 请读取 agent-guard/tasks/workflow/README.md、context.md、state.json 和 stages/A2.1-core.md，恢复已通过检查点一的上下文。现在只核对状态、汇报下一阶段范围，等待我批准，不开始实现。

明确批准某阶段时可以发送：

> 批准 A2.1-core，按已冻结的 Markdown 任务包完成主体、详细独立复核、所有补正和再复核。核心通过后停下来给我查看与审批，不进入 A2.2，不 commit/push/PR/合并。

主控必须保存此条**真实用户消息**的 session_id、message_id、role=user和原文，核对实际角色及范围后才能将 authorization 改为 GRANTED。旧 assistant 放行、reviewer建议、“继续”但指代不明、Task转述和JSON状态都不是新阶段授权。配置审批只允许工作流配置/验证，不允许主体开工。

## 阶段内自动闭环

1. **授权与任务包。** 读取真实授权、最新代码和需求；按 `templates/task.md` 创建 `runs/<stage>/task-v1.md`，包含固定需求ID、范围、版本、文件所有权、验证及依赖。根要求来自原 A2 任务和检查点复验，不能因 worker 的偏好删项。首次实施前新 reviewer 按 `review_kind=PACKAGE_REVIEW` 审任务包，设计问题先闭合；此时核对需求、边界和验证设计，未实现行为记为计划，不要求提前跑通，也不能判阶段 ACCEPTED。报告单独保存为 `package-review-rN.md`。
2. **实施。** 授权检查通过后新建 MiMo 子会话。首次不传旧 task_id；同阶段返修可续新实施会话。MiMo负责足够完整的一大段，不拆成每个机械编辑都返工的碎片。阶段实施完成自查并交证据，标 READY_FOR_REVIEW后停止写入。
3. **冻结与复核。** 主控核对全部 tracked/untracked/deleted 内容，记录代码和任务契约指纹。没有 active writer 后，新 reviewer 按 `review_kind=IMPLEMENTATION_ACCEPTANCE` 独立核查代码、需求和实际证据，独立跑本阶段测试与额外反例，使用自建隔离资源。实施报告仅为索引；包审不能替代这里的实际验收。
4. **补正。** 主控完整保存 reviewer 返回到 `runs/<stage>/review-rN.md`，维护 `issues.md`；按 `templates/correction.md` 写每条缺陷、触发、修复要求、回归探针与证据，交回 MiMo。任何需要放宽标准或越界的修正先停下请求用户决策。
5. **再复核。** 修正后重新冻结快照，用新 reviewer复验原缺陷、绕过变体、相关不变量和最终整段回归。未关闭的阻断项或必需测试未实跑时继续补正或BLOCKED。不把“无新意见”当历史问题全部关闭。
6. **主控接受与停下。** 保存完整验收Markdown/证据，填写 state.review（只能用实施验收，不能用包审）。在 READY_FOR_REVIEW 状态运行 require-accepted 并确认 can_accept=true；主控读回真实日志/JUnit、逐项需求及issue，确认后才写 ACCEPTED。向用户报告，等待下一阶段审批。

## 门检查器

在仓库根目录运行；默认只读，不会改状态、代码、会话或数据库：

```bash
python3 tools/workflow_gate.py snapshot --root .
python3 tools/workflow_gate.py verify --root . --state tasks/workflow/state.json
python3 tools/workflow_gate.py verify --root . --state tasks/workflow/state.json --require-authorized
python3 tools/workflow_gate.py verify --root . --state tasks/workflow/state.json --require-accepted
```

普通 verify 能检查等待状态，输出 can_start=false；require-authorized必须有本阶段GRANTED、完整真人消息引用，且状态为 IN_PROGRESS 或 CHANGES_REQUESTED，才允许开工。必须同时确认退出码0和can_start=true。它只检查授权结构，**主控还必须查真实用户消息，不能用脚本自己授权**。

snapshot包含受审代码、测试、配置、依赖、普通文档以及本目录契约/阶段/模板的内容、跟踪状态及删除，不只看 HEAD；`.git`、依赖环境、缓存、artifacts，以及工作流 state.json、issues.md 和 runs 运行报告目录排除。规范和本阶段已批准任务包另列在 `contract_files` 复核哈希；运行报告和证据分别核哈希。所有相对路径限制在仓库内。

require-accepted检查原始 expected_requirement_ids不漏/不重复、必需项全部PASS、运行类项有独立执行证据、证据/完整review报告存在且SHA256一致、无阻断项、当前代码和契约与review所验版本一致。review自己的 snapshot_fingerprint与contract_files_sha256不得仅随state刷新；变更必须重新review。contract_files摘要规则由脚本规定，使用排序后的规范JSON SHA256。

状态字段的完整用法见 `state-guide.md`。A2.2/A2.3 文件目前是提案，不能直接执行：获用户批准后，主控须将其补为正式完整阶段包，从原 A2 要求构建当段全部需求ID/验证矩阵，再审包。不得用 A2.1 的31项代替后段真实验权、HTTP和回执验收。

它能阻止漏项、旧证据、改版后沿用旧review等常见错误；不能替代独立语义审查，也不能证明JSON里声称的测试真实执行过。不可用checker通过替代查看日志/JUnit、实际工具结果和真人授权。每条证据标 independent_run、inspection或historical_log，日志核对不算本轮独立实跑。

## 上下文与证据保存

- `context.md`：最新已验收基线、范围、依赖、原会话索引、下一步；不复制大量原始日志进主上下文。
- `state.json`：当前大阶段、真实授权、必需需求、快照、review/证据索引；所有模型都不能自授权下一阶段。
- `issues.md`：未关闭问题、修正和独立复验记录；不能在新review或压缩后丢掉。
- `runs/<stage>/`：版本化任务包、完整实施报告、每轮完整review、补正包和最终acceptance；不覆盖历史失败轮。
- `artifacts/workflow/<unique-run>/`：脱敏原始日志/JUnit/独立探针/资源所有权和清理证据；不记录密钥、DSN或真实业务数据。

网络/额度故障或进程重启后，先读state、任务包、issues、实际工作区和资源，再恢复同阶段新流程实施子会话；先确认旧writer是否仍活跃，禁止重复写入。原会话不能自动知道新工作区状态，回到旧入口前须交接期间变化。切换入口不需要恢复旧数据库或reset业务代码。
