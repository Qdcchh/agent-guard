# A2 当前实现与验收索引

更新：2026-10-05。2026-10-05 23:47真人指令要求完成本轮完整整合自查、证据和自有资源清理后停止，不再开展独立验收、Git/PR/CI/merge或A3。本轮补正后的新独立复验未执行、完整A2未接受，原r1 NOT_ACCEPTED保留；P2修复待审。


更新：2026-10-05。**B 补正 ACCEPTED，PR #6 已合并 main（`d7e91c7`），整体项目 PARTIAL。** 当前证据：[完整独立复核](workflow/runs/local-remediation-20261004/review-r2.md)、[正式接受记录](workflow/runs/local-remediation-20261004/acceptance.md)、[当前上下文](workflow/context.md)。67 项／60 项独立运行完成，source/wheel 各 952＋1388 通过，远端 CI 同样通过。

**A2.2 ACCEPTED**：fresh [review-r2](workflow/runs/A2.2-integration-20261004/review-r2.md)完成95项/88运行义务，source/wheel各1022普通＋1930真实PG及最终独立增强全部通过；两项P2已CLOSED_REVIEWED_R2。主控核619原始哈希、150命令/46JUnit、全285冻结、完整断言/case绑定与实际资源余留0，见[接受记录](workflow/runs/A2.2-integration-20261004/acceptance.md)。历史r1否决、四实施轮及全部失败/适配保留；CTX持续回归。A2.2已发布；CI超时25分钟经独立审查调整为45分钟，PR #7 head为138c08a，新CI已SUCCESS（run37235233187），仅审核REVIEW_REQUIRED、尚未合并。2026-10-05 23:47真人指令要求完成本轮完整整合自查、证据和自有资源清理后停止，不再开展独立验收、Git/PR/CI/merge或A3。本轮补正后的新独立复验未执行、完整A2未接受，原r1 NOT_ACCEPTED保留；P2修复待审。

## 版本与历史

- 历史B候选分支 `handoff/b-integration-20261003`，实施基线 HEAD `2051b402c99a3d400d8f12749287075e23a9a521`；worker 未执行 Git 提交或发布。
- main 基线 `153f14e9be180a1eb26b0f0e0898048d45170569`，包含历史已验收 A2.1。
- 历史依据：[A2.1 acceptance](workflow/runs/A2.1-core/acceptance.md)、[review-r8](workflow/runs/A2.1-core/review-r8.md)、[implementation-r5](workflow/runs/A2.1-core/implementation-r5.md)。仅适用当时版本。
- 修补前缺陷：[本地质量复核](workflow/runs/local-quality-20261004/review.md)。旧云端数字/XML未完整交付，不作本轮实跑证明。

A2.2受审文档基线280022e和产品基线d7e91c7保留；主控已发布接受提交8e4e7a3至[PR #7](https://github.com/Qdcchh/agent-guard/pull/7)，CI已SUCCESS/审核REVIEW_REQUIRED，尚未合并。当前另用`codex/a2.3-receipts`续接，承接已独立审查的CI-only提交138c08a；PR #7 head为该提交。原暂停检查点不追改；r1否决的两项经r4补正和fresh r2完整复验关闭，A2.2 ACCEPTED。95项/88运行义务及精确范围见[task-v1](workflow/runs/A2.2-integration-20261004/task-v1.md)，不能复用历史通过数字放行。

## 实现与边界

r4同段补正自查完成：终态原件投影的`DOWNSTREAM_INCONSISTENT`局部转换为503，未知typed及程序错误保留500。正式回归覆盖16个持久结果损坏变体、同proof修复成功及重放拒绝、全业务表与独立下游零变化；短窗按真实AS父`exp`和当前时间选择带余量的子TTL，新跨秒组与原组均保留真实锁后目标deadline正负控。根/中层到期同时约束叶/token，不能声称隔离祖先过期。两项已由fresh r2完整95/88独立复核关闭。

| 范围 | 当前说明 |
| --- | --- |
| A2.1 生命周期、四工具、可信报价、租约、全祖先预算、UNKNOWN恢复、outbox | 已有实现和历史验收；本轮修正成功结果变体与共享256项边界 |
| B→A真实验签、权限快照、同事务原证据绑定、最终时刻检查 | 进程内实现已通过完整独立复验；公开HTTP接入已由A2.2 fresh r2独立接受 |
| 离线回执及规范投影SDK | 原SDK拒绝非邻接重复grant、future-token真签名触发；A2.3候选由独立内部publisher持续发布，本轮补正后的新独立复验未执行、完整A2未接受，本轮自查收尾后按真人指令停止、原r1否决保留 |
| P13测试效力 | 本轮有界全结果/异常收集、精确租约错误及有效失败负控 |
| A2.2公开invoke与最终动态result-read | 95/88 fresh r2 ACCEPTED，两个P2已独立关闭 |
| A2.3持续签发/发布及完整A2联合验收 | 核心/CLI/HTTPS局部自查通过并停写；唯一整合者完成119项/112运行义务的联合自查后按真人指令停止；本轮补正后的新独立复验未执行、完整A2未接受、原r1否决保留；旧无receipt_keys配置保持PENDING兼容 |
| A3独立锚点、导出、完整HTTP演示与规模/对照实验 | 未完成 |

## 本轮证据

历史整合r1环境记录：独占Linux amd64、Python3.11.17、非root UID501、原锁安装、真实PG16；源码挂载只读且自有逐字执行副本，独立非editable wheel。完整source/wheel非集成与PG、真实进程和10轮竞争、TLS/OpenSSL、README/demo、历史原件失败与等价diff、资源精确清理均以实施报告的实际命令/JUnit/哈希为准。

2026-10-05 23:47真人指令要求完成本轮完整整合自查、证据和自有资源清理后停止，不再开展独立验收、Git/PR/CI/merge或A3。本轮补正后的新独立复验未执行、完整A2未接受，原r1 NOT_ACCEPTED保留；P2修复待审。

旧停止已由本次恢复授权覆盖；当前范围见[恢复授权](workflow/runs/A2.3-receipts-20261004/user-resume-20261005.md)和[A3接续计划](A3-plan.md)。规划不代替未来正式包审或业务授权。

本轮补正依据：[正式补正任务](workflow/runs/A2.3-receipts-20261004/task-remediation-r2.md)；历史整合依据：[恢复任务](workflow/runs/A2.3-receipts-20261004/task-resume-integrator-r1.md)；实际命令、JUnit、119项逐断言与资源结束证据由唯一整合者报告交主控，fresh独立接受前不标ACCEPTED。

历史整合r1联合自查使用完整353基线与29路径候选，LinuxPython3.11/PG16 source和非editablewheel。两mode完整普通各1169P；完整PG原各2799已执行，2797P/2F/0E/0S，两个F为隔离runner遗漏原CI规定的denial-probe角色；角色语义补齐后精确受影响两例各2P。原完整run exit1、全部失败及补正新标签保留，不冒称单一原全绿run。原B历史失败与等价、A1原探针/升级等价、oracle60、487历史增强、CTX/RESULT/SHORT-WINDOW与README旧两流程/新publisher/联合demo分别绑定本人实际证据；该历史轮当时要求后续独立复验；2026-10-05 23:47最新真人指令覆盖后续安排，本次补正仅完成完整自查、证据与资源清理后停止，本轮补正后的新独立复验未执行；完整A2未接受。


A2.3补正候选在真实签名/READY前复用原接受事实校验：对不可变报价执行精确总额、数量/原请求及cost currency/calls检查，并逐事件核对历史验真的完整root→leaf路径和四种delta。两列quote/result相互一致不能替代上述约束。校验读取均先于query最终DB时刻，不引入当前报价、下游结果或当前撤销/到期条件；合法零价及迟延终局仍可历史发布。失败保留PENDING/null及原ID/iat，当前query失败回滚proof/link，仅允许原契约的隔离STAGED证据。

容量域分列：当前canonical producer的订单公开响应保守包含上界为58168字节；兼容有效原始签名JWS（含非canonical JSON空白）的单JWS仍可到16384字节，不能套用canonical JWS上界。原接受事实要求q≥1、p≥0、每项q*p及Σq*p≤MAX_SAFE；p>0时digits(q)+digits(p)≥18会使最小乘积≥10^16>MAX_SAFE，p=0时至多16+1位。因此每项联合数字宽度≤17，256项比松Cartesian32位省3840字节，得到兼容域公开响应保守上界64695字节。两者均不是实际合法最大值；组件64KiB/JWS16KiB、公开65536和外层1MiB守卫保持不变，真实边界/非法组件探针仍独立保留。补正自查不代表正式接受；本轮按真人指令在自查、证据和资源清理后停止，本轮补正后的新独立复验未执行、完整A2未接受，原r1 NOT_ACCEPTED保留，P2仅标FIXED_PENDING_REVIEW。

本轮完整自查报告：`workflow/runs/A2.3-receipts-20261004/implementation-remediation-r2.md`；最新真人停止指令：`workflow/runs/A2.3-receipts-20261004/user-stop-after-selfcheck-20261005.md`。本轮补正后的新独立复验未执行；完整A2未接受，原[r1否决](workflow/runs/A2.3-receipts-20261004/review-r1.md)保留。
