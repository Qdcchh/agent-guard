# A2.1-core 最终阶段验收与人审批停点

日期：2026-10-02（Asia/Shanghai）。**主控结论：A2.1-core ACCEPTED；完整 A2／整体项目仍 PARTIAL，后段真实验证器/HTTP/回执依赖未闭合。** 当前阶段维持A2.1-core，到此停止，不启动A2.2、不引入B、不提交/推送/PR/合并。

## 1. 授权、分工与候选版本

- 真实原批准：role=user，session `ses_f0ac0e676ffecn71p6Ww7zaqQq`，message `msg_0f54148e0001ZW7yCMdK0TE97F`；已从OpenCode原用户消息读回，批准A2.1主体及同段详细复核/补正/再复核，不后段/Git发布。
- 用户额度暂停与恢复：msg_0f887e93e001D7S0b27RlnzOD3暂停；msg_0f9cc37f8001PyAvQX6K0ucvFu继续；真实消息已读回，仅恢复同一授权，不授下一阶段。
- 实施唯一writer：MiMo 2.6 Pro / opencode-go/mimo-v2.6-pro，workflow新session `ses_f0aa292caffeODmd0G8jUSZ1Y9`，首轮实现及4轮补正，最后停写READY_FOR_REVIEW。主控未替代其业务实现。
- 最终NEW独立reviewer：`ses_f06312272ffeGlM7w2nBLXi2DM`，实际openai/gpt-6.1-sol，high配置；主控同模型high。旧文档medium/xhigh仅历史，不覆盖当前配置。
- 分支/HEAD：feat/a2-execution-gateway / b120c7cf5ec0eafb18305d1207c36dd11655b324。实现仍未提交，HEAD不是受验未提交代码的版本标识。
- 完整102项候选指纹：`15dc8782e1788e0bae6359a5c7538287db679078012b50f8901ab72dea4c5b09`。
- 独立review契约摘要：`43c996ada95eebca2c5cbc72bd21b792aed03ad687736baeb4d8041a974b09a2`。task-v1及4补正包、原需求、安全/接口/验收材料均保留hash，state中完整manifest可恢复。

## 2. 实際完成范围

- 004执行生命周期：合法状态迁移、操作/路径保全、互斥终局事件、lease/outbox/旧材料隔离sidecar；005节点形状/完整集合，006transaction seal封存包括旧已提交事件。不改已应用001—006的原checksum来修缺陷。
- 可信合成资源/报价、严格四工具参数和分层scope/完整DB路径绑定；订单金额来自可信快照，不是客户端自报；通知只能指向存在、同tenant/task且原grant/holder可访问的操作。
- 独立数据库/连接/事务域持久模拟下游，执行/查询服务认证、稳定operation_id幂等、订单/通知/读结果持久性；确定终局拒绝防止迟到成功。
- 执行、全祖先SETTLE/RELEASE、UNKNOWN保预算/恢复；owner+fencing+合法state+锁后DB有效expiry；无DB锁跨下游调用，统一锁序、旧worker不覆盖或误报当前状态。
- A1最小兼容accept_checked：保留默认accept(verified,cost)，per-call可信validator在同连接/锁/事务中检查actualEXISTING材料；拒绝proof回滚，释放锁后独立隔离。修复最后非锁lookup后的TOCTOU窗口，不增加假验权入口。
- 稳定不可变待签outbox、receipt_id/created_at/UTC整数秒iat、首次证据及全路径ledger_changes；缺B保持PENDING/receipt_jws=NULL，不伪SM3/JWS/RFC8785。
- 全新增拒绝/故障/并发/迁移/恢复测试、README可执行双初始化流程与worker烟测；报告当前事实索引已纠正。

## 3. 最终独立实测（不是实施者自述）

环境：Python3.11.16、PostgreSQL16.15、psycopg/binary3.2.13、pytest8.3.5、ruff0.11.13；独立owner PG/Python容器、gateway/下游不同数据库事务域。受审源码只读，测试副本逐102项内容/mode绑定。

| 验证 | 最终结果 |
| --- | --- |
| 正式unit/骨架/文档 | 137 passed，0 fail/error/skip |
| 正式PG integration | 522 passed，0 fail/error/skip |
| A1独立分套回归 | 68 unit＋78 PG passed（正式全套内子集，不重复累计） |
| A2独立分套PG | 444 passed（正式PG内子集） |
| 新r8自选探针 | 58 passed（最终独立探针内子集） |
| 最终独立全探针 | 482 passed，0 fail/error/skip；424继承＋58新反例 |
| Ruff check/format、diff check | exit0；56文件格式正确 |
| 迁移/升级 | 空库001—006、重复no-op；001/003/004/005×合法非法8组合，七表全列/行与完整registry保全 |
| 并发/故障 | 规定组各10轮、独立连接与barrier/event；真SIGKILL新PID恢复、真实PG回滚、真实锁自动超时/目标锁环、validator内真实owned backend终止 |
| README | program-first与CLI-first逐字新库流程均SMOKE_OK；实际订单/全祖先计数/事件/outbox断言 |

主控直接核对：原unit.xml/integration.xml/probes-verified.xml/fresh-r8.xml/A1分套XML的tests/failures/errors/skipped；31项全部PASS及证据原件SHA256，完整issue闭环及最终manifest/contract；probe-adaptation.diff只修正合法list过严预期并增强成功后置断言，没有删case/skip/弱化正式要求；cleanup.json精确owner/ID清理原件。完整多证据矩阵保留在最终index，state.review存每ID主证据摘要并绑定该index。

## 4. 独立闭环、门检查与证据

- 首次PACKAGE_REVIEW通过后才MiMo开工；原子接受兼容改变再次NEW包审后实施。包审不是实现接受。
- 完整独立实现报告保留r2/r3/r5/r7失败及r8接受；r1/r4因额度中断、r6工具中断无完整结论，状态与证据保留，不算阶段接受轮。
- 原所有14条issue（含DOC和P11当前验证缺口）由r8独立原触发、变体、相关不变量及整段回归关闭，主控核查记录 `tasks/workflow/issues.md`；不能用formal全绿抵消早期probe失败。
- 在state=READY_FOR_REVIEW时运行绝对root/state的workflow_gate verify --require-accepted：**exit0、ok=true、can_accept=true、errors=[]**。主控再核31ID与index、完整原需求和issues、实际snapshot一致后才写ACCEPTED。checker只证明结构/指纹/证据存在，不能替代语义、测试真实性或真人授权；三者分别已人工/工具查证。

证据入口：

1. 完整最终独立报告 `tasks/workflow/runs/A2.1-core/review-r8.md`，SHA256 `93c4b0d06f46a2ca1d9a6745091ae8b7408081717b22e5c07a881ed7c44a04a7`。
2. 原始证据 `artifacts/workflow/A2.1-core-review-r8-2fd79c61/`，index SHA256 `07fc53e3307663d4840ce2e202e857a635d96bef31a8fdaf28caf4f941c7b330`。本地忽略，含全部logs/XML/probe源/commands/observations/resource与freeze；不要上传真实凭据或忽略目录。
3. worker报告 `implementation-r1—r5.md`、四补正包、两包审、全部独立失败报告和原始artifact历史，均保留不覆盖。
4. 当前权威控制状态：tasks/workflow/state.json；问题全生命周期：issues.md。原A2-report中的READY为最后worker停写时索引，冻结后不再修改以免破坏review绑定，最终ACCEPTED以本报告/state为准。

## 5. 已知限制与下一阶段提案（未授权执行）

- 完整A2／项目PARTIAL：真实B invoke/result-read验证器、权限快照grant/token/祖先绑定、受控证据接口、真实HTTP/AGPoP/TLS联合闭环以及SM2回执仍未按本stage实现/验收。
- 下一提案A2.2-integration：用户新批准后再核B真实交付/独立验收，冻结完整本段任务包/矩阵、包审、MiMo实施与独立验收。本次不fetch/import B、不预建业务资源、不写下一段代码。
- r5一次旧unknown LedgerError缺code/cause不能追溯；当前P11精确受控同步/clock/codes义务已独立闭合，但保留历史风险，不编造TTL根因。
- 原升级探针硬编码只002仍原样记录fail，当前动态8组保全等价更强；合法list原过严probe失败也保留，最终自有适配有明确语义和完整后置断言，不宣称全部历史原件都通过。
- 响应丢失/无结果/错误outcome为标注port替身，不是真实断网；TLS/wheel部署、真实密码/HTTP、远程CI未本轮运行。Python3.11/PG和进程重启/事务回滚是实际验证；依赖未全部传递锁定，不称生产级或通用exactly-once证明。
- 本轮review只清自身owned两容器/空网络，既有7资源身份配置起始/暂停状态一致，未连接其业务DB；不把inventory核对称为业务数据全量比较。

## 6. 人审批停止

**本阶段收尾完成，到此停止。current_stage保持A2.1-core，等待用户查看结果并另行批准A2.2。** 未commit/push/PR/合并/改保护，未引入B、未进入A2.2/A2.3/A3。接受本阶段不授权下一阶段或Git发布。
