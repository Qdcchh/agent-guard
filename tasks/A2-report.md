# A2 当前实现与验收索引

更新：2026-10-04。**B 补正 ACCEPTED，PR #6 已合并 main（`d7e91c7`），整体项目 PARTIAL。** 当前证据：[完整独立复核](workflow/runs/local-remediation-20261004/review-r2.md)、[正式接受记录](workflow/runs/local-remediation-20261004/acceptance.md)、[当前上下文](workflow/context.md)。67 项／60 项独立运行完成，source/wheel 各 952＋1388 通过，远端 CI 同样通过。

## 版本与历史

- 候选分支 `handoff/b-integration-20261003`，实施基线 HEAD `2051b402c99a3d400d8f12749287075e23a9a521`；worker 未执行 Git 提交或发布。
- main 基线 `153f14e9be180a1eb26b0f0e0898048d45170569`，包含历史已验收 A2.1。
- 历史依据：[A2.1 acceptance](workflow/runs/A2.1-core/acceptance.md)、[review-r8](workflow/runs/A2.1-core/review-r8.md)、[implementation-r5](workflow/runs/A2.1-core/implementation-r5.md)。仅适用当时版本。
- 修补前缺陷：[本地质量复核](workflow/runs/local-quality-20261004/review.md)。旧云端数字/XML未完整交付，不作本轮实跑证明。

## 实现与边界

| 范围 | 当前说明 |
| --- | --- |
| A2.1 生命周期、四工具、可信报价、租约、全祖先预算、UNKNOWN恢复、outbox | 已有实现和历史验收；本轮修正成功结果变体与共享256项边界 |
| B→A真实验签、权限快照、同事务原证据绑定、最终时刻检查 | 进程内实现已通过完整独立复验；公开 HTTP 接入仍待 A2.2 |
| 离线回执及规范投影SDK | 本轮拒绝非邻接重复grant，future-token真签名触发；不持续发布 |
| P13测试效力 | 本轮有界全结果/异常收集、精确租约错误及有效失败负控 |
| A2.2公开invoke与最终动态result-read | 未完成 |
| A2.3持续签发/发布及完整A2联合验收 | 未完成；outbox保持PENDING |
| A3独立锚点、导出、完整HTTP演示与规模/对照实验 | 未完成 |

## 本轮证据

独占Linux amd64、Python3.11.17、非root UID501、原锁安装、真实PG16；源码挂载只读且自有逐字执行副本，独立非editable wheel。完整source/wheel非集成与PG、真实进程和10轮竞争、TLS/OpenSSL、README/demo、历史原件失败与等价diff、资源精确清理均以实施报告的实际命令/JUnit/哈希为准。

原五项及新增超时负控问题均由 fresh r2 关闭；历史实施与失败报告保留原状态，不能替代当前接受记录。后续按现行工作流逐阶段批准。
