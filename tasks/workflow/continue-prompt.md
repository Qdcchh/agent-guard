# A3 协作接续入口

先读[完整同学交接](../../docs/A3-HANDOFF.md)、[HANDOFF](../../HANDOFF.md)、[现行约定](current-policy.md)、[原始安全](../../docs/security-model.md)/[接口](../../docs/oauth-oidc-sm2-mvp.md)/[验收](../../docs/acceptance.md)、[完整A2接受](runs/A2.3-receipts-20261004/acceptance.md)及[A3计划](../A3-plan.md)。

当前完整A2已独立接受，A3四段未实施；协作代码从 `codex/a2.2-integration` / PR #7 开始，本次暂不合并main。先检查实际仓库根、分支/HEAD/index/dirty/untracked、远端与PR，保留全部成员成果，不reset/clean或强推。不得用历史本机state/模型配置/raw路径作为同学开工前置。

同学接续范围为全部A3，按A3.1→A3.2→A3.3→A3.4顺序推进。先从真实已接受产品和原始目标建立本段正式版本包、全需求/断言矩阵、接口/依赖/精确文件与资源所有权；fresh独立包审通过后实施。共享前置先串行，独立部分按包并行，唯一整合者完整自查，各writer停写后冻结全候选；新独立reviewer亲自审代码/调用方、跑完整矩阵及独立探针，必要补正保留失败并换新reviewer完整复验。全部必需项闭合才能接受并进入下一段。

禁止删断言/skip/放宽预期换取通过。保留真实SM2/SM3、PG/TLS、全预算/撤销、10轮有效竞争、真进程恢复、source/非editablewheel、前段回归及历史/等价探针。四段最终交付包括外部检查点/日志、有界导出/离线验证、干净部署与三holder完整链、50客户端/完整方案至少10000调用、公平对照及全部最终材料。最终Git/PR/CI与审核另核；本次发布者不做A3、不合并。
