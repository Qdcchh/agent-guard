# Agent Guard 当前交接

更新：2026-10-04（Asia/Shanghai）。**v1实施交付时五项 FIXED_PENDING_REVIEW，整体项目 PARTIAL。后续接受与合并结论读取本轮 state 及主控关联的正式报告。** 自查证据见 [implementation-r1](tasks/workflow/runs/local-remediation-20261004/implementation-r1.md)，后续阶段状态见 [本轮 state](tasks/workflow/runs/local-remediation-20261004/state.json)；本次文档同步见 [implementation-docs-r1](tasks/workflow/runs/local-remediation-20261004/implementation-docs-r1.md)。[质量复核报告](tasks/workflow/runs/local-quality-20261004/review.md) 保留为本轮修补前的缺陷依据。

## 1. 实际版本

- 当前仓库：`/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`。父目录另有一个尚无提交的 Git 仓库，不要混用。
- 当前分支：`handoff/b-integration-20261003`，HEAD `2051b402c99a3d400d8f12749287075e23a9a521`。
- 远端 main：`153f14e9be180a1eb26b0f0e0898048d45170569`，A2.1 已合入。两远端 SHA 均在本轮通过 ls-remote 核实。
- 开始时工作树干净，原 `product-manifest.json` 186 项文件全部哈希匹配。本轮修改文档后该清单仍只代表 2026-10-03 原始传输；未改其哈希冒充新快照。
- 原 B 来源提交：`e521a461adb18d5fed89c8d1094647cb35eeff56`；原云端候选 206 项指纹：`5a8f5a3be1e9021a0907d5aec3c8c48a4999d7ba0527e307450829f53b01f540`（历史交接值，不是 Git SHA，未在本机重建）。

## 2. 已有能力与最终目标

A1 原子账本和 A2.1 四工具执行/租约/恢复/祖先预算/outbox 有历史验收。当前候选加入 B 的真实 SM2/SM3、授权码、两级委托、登录同意、撤销、AS HTTPS、DID/登记绑定、权限快照、证据存储与同事务绑定、只读回执投影。S1—S4 以及 DID 不可变配置快照、回执历史时间窗口、CRLF 迁移兼容、迁移 CLI 超时脱敏、check/run 配置一致性已实施，不能当未做过重新开发。

最终目标仍是用户同意 → 三代理两级收窄委托 → 真实签名工具请求 → 共享预算/幂等/撤销 → 故障恢复 → 可验证回执/审计的采购原型，并在 2026-10-20 前形成部署复现、演示、实验及技术材料。当前进程内接入不等于完整公开网关：A2.2 公开 invoke/最终动态查询、A2.3 持续签发发布、A3 锚定/导出/端到端演示与规模对照实验尚未完成，outbox 保持 PENDING。

## 3. 本轮补正与待复验

| ID | v1实施交付时状态（后续结论见本轮state） |
| --- | --- |
| BR-FINAL-RECEIPT-DUPLICATE | FIXED_PENDING_REVIEW：完整祖先路径 grant ID 全局唯一，独立 AS/GW/三 holder 真签名正负回归 |
| A21-R1-OUTCOME | FIXED_PENDING_REVIEW：共享 bind_result 与终局执行器同时绑定成功变体与工具，异常保持 UNKNOWN 后合法恢复 |
| BR-FINAL-ITEM-LIMIT | FIXED_PENDING_REVIEW：参数/快照/结果共享 256 项上限，257/大数组接受前零新增 |
| BR-FINAL-P13-ORACLE | FIXED_PENDING_REVIEW：有界收集全线程结果，主线程拒意外异常，混合竞争只认精确 live-owner LEASE_LOST |
| BR-FINAL-RECEIPT-TEST-BRANCH | FIXED_PENDING_REVIEW：future-token 可达且重新真实签名，5 秒/6 秒 proof 窗口保留 |

五项均须 fresh reviewer 完整独立复验；包审 PACKAGE_READY 与实施自查不代表接受。离线异常重复路径由受信签名者生成，不是签名伪造或在线预算绕过证明。

## 4. 实测和历史证据边界

本轮 worker 使用独占 Linux amd64 Python3.11.17 容器、非 root UID501、锁定 venv、普通非 editable 安装及 PG16 独占实例。源挂载只读，完整 source 测试在自有逐字副本运行；wheel 测试在无 src/agent_guard 的独立目录，检查父/子进程安装来源与包携带 SQL。完整命令、原失败、JUnit、哈希、环境/资源、67 项矩阵见实施报告及其证据目录，阶段状态以本轮 state 和后续独立验收报告为准。

原云端 source/wheel 各2307通过、7个A反例和B重复grant失败、历史A2 tuple/list 两失败与B同步20失败均为历史交接陈述。本轮重新运行找到的本地 A2 482节点与 B250节点原件副本，不代表找回缺失的云端最后探针/XML；本轮新边界回归明确是重建。旧合法 list 语义保留，不能以原件绿宣称云端缺口已追溯解释。

## 5. 工作流与待补资料

先读 [Codex 补充契约](tasks/workflow/runs/setup/codex-astra-sol-v1/workflow-contract.md)、[工作流入口](tasks/workflow/README.md)、[上下文](tasks/workflow/context.md)、[问题台账](tasks/workflow/issues.md)。桌面契约已原样保存，不改变其正文。

旧 `tasks/workflow/state.json` 保留 A2.1 历史验收，不是当前 B 控制状态；旧门只读运行 `can_accept=false`。当前正式包和用户批准的运行适配已落盘；请求模型 gpt-6.1-sol/medium，有效后台元数据 UNKNOWN，不能补造模型/停止/接受字段放行。辅助静态子审计不冒充正式新 reviewer。

原本地仓库 `/Users/qdcc/code/密码技术竞赛/agent-guard/tasks/workflow/runs/B-remediation-integration/` 有 task-v1、requirements-v1、接口和迁移 DRAFT 设计，可帮助恢复67项/60项义务；原草稿不作为本轮放行依据；本轮正式包见 [task-v1](tasks/workflow/runs/local-remediation-20261004/task-v1.md)。内部报告未复制或公开。[恢复清单](tasks/workflow/runs/local-quality-20261004/requirements-matrix.json) 逐项保留未闭合状态。

需从原云端取得的关键资料（以下是历史相对路径，本机缺失）：

- `tasks/workflow/runs/B-remediation-integration/workers/integrator-1/implementation-cloud-r2.md`
- `artifacts/workflow/br-final-independent-review-r1/{review.md,requirements-matrix.json,defects.json}`
- `artifacts/workflow/br-final-independent-review-r2/{candidate-retry-start.json,binding-retry-start.json,defects.json,source-full.xml,wheel-full.xml,corrected-adversarial.xml,receipt-duplicate-parent.xml}`
- 同 r2 下 `retry-1/` 的历史 A2/B 原始与等价回归、命令回执和资源清理证据。

原交付有意未包含 B 内部报告、云端控制记录及完整原始证据；不能为了修链接造一份通过报告。旧云端阻断和清理事实保留在 Git `2051b40:HANDOFF.md`，不把旧停止日志当成本机实时资源状态。

## 6. 继续与清理

按本轮正式包和用户已批准适配，实施停写后由主控冻结，再启动全新独立完整复验；必需义务无法等价补齐时 BLOCKED。不要从旧初始状态重做 A2.1，不自动进入 A2.2/A2.3/A3，worker 不执行 Git 发布；用户已授权的条件提交/推送/合并由主控在验收及远端正常门满足后处理。

前次质量复核清理仅限仓库内无用 `.DS_Store`、被 Codex 契约替代的旧 setup 文档和自建测试容器。保留正式任务、历史验收/失败报告、SQL、依赖锁和本轮失败证据；现行 context/A2-report/workflow/HANDOFF 的错误旧状态直接移除，原文可从 Git 恢复。

既有 `agent-guard-a2-pg`、verivote 等资源未连接、未停止、未删除。若以后运行过 bundle 升级，Git 代码回退不意味着数据库能无损降级。
