# 实施与独立验收工作流

当前角色覆盖：2026-10-14真人继续授权；worker OpenCode Go `deepseek-v4.1-flash/max`，全新reviewer `gpt-6-astra/high`，主控按用户当前Astra设置。effective metadata未观测仍UNKNOWN。正在恢复A34实施，以下旧Sol角色及中断状态为此前记录；完整自查/40000/独验仍NOT_RUN。见[本轮授权](runs/A3.3-A3.4-joint-20261013/user-resume-opencode-astra-20261014.md)。

当前2026-10-14：两实施worker平台中断，A34仍未完成；root核本轮自有资源0并停guard。完整联合自查/40000/新独验NOT_RUN。接续见[当前入口](runs/A3.3-A3.4-joint-20261013/resume-after-platform-interruption-20261014.md)，不将本次中断当用户取消。
A3.1与A3.2已正式独立接受；A3.2新r2完整source/非editable wheel各20组及159/151、269+95+73义务闭合，A32-IA-R1-001已关闭。A3.3 S0注册确认补正、S1场景及S2正常装配均已封存分段自查；联合包PACKAGE_READY，A3.4共享层STOP已root核验，对照与测量平台中断，完整联合自查及新独立验收尚未执行，项目仍PARTIAL。

[A3.2正式接受](runs/A3.2-evidence-20261011/acceptance.md)与[机器版本/证据索引](runs/A3.2-evidence-20261011/acceptance.json)。 [最新联合验收授权](runs/A3.3-A3.4-joint-20261013/user-joint-acceptance-20261013.md)持续至A3.4完整独立接受、最终材料及自有清理后STOP；取消额度监测，不Git发布。worker Sol/low，每轮新reviewer Sol/high，有效metadata UNKNOWN。

1. 核真人授权、实际基线、完整需求/断言、精确文件和自有资源，冻结版本化任务包。
2. fresh reviewer做PACKAGE_REVIEW；授权、PACKAGE_READY和运行绑定齐备后才实施。共享接口先串行停写冻结，独立文件/资源再并行。
3. 全writer自查并STOP；主控亲核范围、进程、资源及原件，唯一整合完成完整自查，再冻结候选。
4. 新reviewer亲自做完整IMPLEMENTATION_ACCEPTANCE：审代码、全矩阵、前段回归、原失败/等价探针、真实PG/TLS/并发/新进程与首尾指纹。局部自查不能替代。
5. 缺陷保失败证据，精确补正；范围/接口实质变化重新包审。fresh完整复验无阻断且必需项闭合才接受。

[现行角色与边界](current-policy.md) · [实施契约](implementation-contract.md) · [审查契约](review-contract.md) · [原补充契约](runs/setup/codex-astra-sol-v1/workflow-contract.md) · [任务模板](templates/task.md) · [报告模板](templates/implementation-report.md) · [补正模板](templates/correction.md) · [接续](continue-prompt.md)。

旧机器门/state-guide属于历史，不改门或补造metadata放行。runs保正式授权/任务/报告；artifacts保本地原始证据，正式报告须自足且新代码不得运行时依赖ignored历史文件。现行入口只保当前事实与索引，历史见[问题原文](issues-history.md)和[约定原文](current-policy-history.md)；仅需要追溯具体事项时读取。

历史[连续至A3.3授权](runs/A3.1-audit-20261008/user-extend-through-a33-20261009.md)：优先功能/安全/必需验收阻断，普通问题自主处理，非阻断问题迅速收尾，避免无关修整与重复验证。
