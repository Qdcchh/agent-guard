# A2 当前实现与验收索引

更新：2026-10-05。**B 补正 ACCEPTED，PR #6 已合并 main（`d7e91c7`），整体项目 PARTIAL。** 当前证据：[完整独立复核](workflow/runs/local-remediation-20261004/review-r2.md)、[正式接受记录](workflow/runs/local-remediation-20261004/acceptance.md)、[当前上下文](workflow/context.md)。67 项／60 项独立运行完成，source/wheel 各 952＋1388 通过，远端 CI 同样通过。

**A2.2 ACCEPTED**：fresh [review-r2](workflow/runs/A2.2-integration-20261004/review-r2.md)完成95项/88运行义务，source/wheel各1022普通＋1930真实PG及最终独立增强全部通过；两项P2已CLOSED_REVIEWED_R2。主控核619原始哈希、150命令/46JUnit、全285冻结、完整断言/case绑定与实际资源余留0，见[接受记录](workflow/runs/A2.2-integration-20261004/acceptance.md)。历史r1否决、四实施轮及全部失败/适配保留；CTX持续回归。下一步发布受验收分支并正式建包A2.3，合并受阻仍继续。

## 版本与历史

- 历史B候选分支 `handoff/b-integration-20261003`，实施基线 HEAD `2051b402c99a3d400d8f12749287075e23a9a521`；worker 未执行 Git 提交或发布。
- main 基线 `153f14e9be180a1eb26b0f0e0898048d45170569`，包含历史已验收 A2.1。
- 历史依据：[A2.1 acceptance](workflow/runs/A2.1-core/acceptance.md)、[review-r8](workflow/runs/A2.1-core/review-r8.md)、[implementation-r5](workflow/runs/A2.1-core/implementation-r5.md)。仅适用当时版本。
- 修补前缺陷：[本地质量复核](workflow/runs/local-quality-20261004/review.md)。旧云端数字/XML未完整交付，不作本轮实跑证明。

当前A2.2分支`codex/a2.2-integration`，HEAD文档基线280022e保留、产品基线d7e91c7；worker未commit/push/PR。原暂停检查点不追改；r1否决的两项经r4补正和fresh r2完整复验关闭，A2.2 ACCEPTED。95项/88运行义务及精确范围见[task-v1](workflow/runs/A2.2-integration-20261004/task-v1.md)，不能复用历史通过数字放行。

## 实现与边界

r4同段补正自查完成：终态原件投影的`DOWNSTREAM_INCONSISTENT`局部转换为503，未知typed及程序错误保留500。正式回归覆盖16个持久结果损坏变体、同proof修复成功及重放拒绝、全业务表与独立下游零变化；短窗按真实AS父`exp`和当前时间选择带余量的子TTL，新跨秒组与原组均保留真实锁后目标deadline正负控。根/中层到期同时约束叶/token，不能声称隔离祖先过期。两项已由fresh r2完整95/88独立复核关闭。

| 范围 | 当前说明 |
| --- | --- |
| A2.1 生命周期、四工具、可信报价、租约、全祖先预算、UNKNOWN恢复、outbox | 已有实现和历史验收；本轮修正成功结果变体与共享256项边界 |
| B→A真实验签、权限快照、同事务原证据绑定、最终时刻检查 | 进程内实现已通过完整独立复验；公开HTTP接入已由A2.2 fresh r2独立接受 |
| 离线回执及规范投影SDK | 本轮拒绝非邻接重复grant，future-token真签名触发；不持续发布 |
| P13测试效力 | 本轮有界全结果/异常收集、精确租约错误及有效失败负控 |
| A2.2公开invoke与最终动态result-read | 95/88 fresh r2 ACCEPTED，两个P2已独立关闭 |
| A2.3持续签发/发布及完整A2联合验收 | 未完成；outbox保持PENDING |
| A3独立锚点、导出、完整HTTP演示与规模/对照实验 | 未完成 |

## 本轮证据

独占Linux amd64、Python3.11.17、非root UID501、原锁安装、真实PG16；源码挂载只读且自有逐字执行副本，独立非editable wheel。完整source/wheel非集成与PG、真实进程和10轮竞争、TLS/OpenSSL、README/demo、历史原件失败与等价diff、资源精确清理均以实施报告的实际命令/JUnit/哈希为准。

原五项及新增超时负控问题均由 fresh r2 关闭；历史实施与失败报告保留原状态，不能替代当前接受记录。最新[用户授权](workflow/runs/A2.2-integration-20261004/authorization-expansion-20261004.json)要求A2.2接受后处理合并，并无论合并是否成功都继续A2.3与完整A2验收；A2.3本段适配已批准、独立包审待完成，完整A2接受后全部[A3](workflow/stages/A3-closure.md)已获[真人授权](workflow/runs/A3-closure-20261004/authorization.json)，逐段规划/实施/独立复核。

后续持续范围见[完整A3真人授权](workflow/runs/A3-closure-20261004/authorization.json)和[四段计划](workflow/stages/A3-closure.md)。历史单段停止点被最新真人要求覆盖；每段仍须正式包审和完整独立验收。
