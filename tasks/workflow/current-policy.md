# 现行角色与边界

当前演示前端子任务（2026-10-15）：真人授权本地可操作演示页，worker 指定 `gpt-6.1-sol / low`。用户随后授权补齐安全场景台：复用现有真实安全测试，新增固定场景运行、明确标注的历史记录回放与能力全景；范围为页面与本地固定动作适配器、演示检查及说明；A3.3/A3.4完整实验和联合验收仍暂停。此角色覆盖仅适用于当前前端任务，不把旧OpenCode配置当作本次worker。

当前角色覆盖：2026-10-14真人继续授权；worker OpenCode Go `deepseek-v4.1-flash/max`，全新reviewer `gpt-6-astra/high`，主控按用户当前Astra设置。effective metadata未观测仍UNKNOWN。见[本轮授权](runs/A3.3-A3.4-joint-20261013/user-resume-opencode-astra-20261014.md)。

当前2026-10-15：真人明确要求先暂停并解释卡住原因。worker与当前测量已停，当前driver真实父wait -2、精确owner资源0；guard已不在运行。source/wheel对照扩展分段自查及测量修复探针已运行；正式40000尚未完成：r6已有3组COMPLETE回执、各5000条，尚未经主控完整接受；complete模式存在bootstrap随累积状态增长导致TTL失败的阻塞，待恢复后处理。此前失败、中断与证据缺口保留。完整联合最终自查和全新独立验收仍未完成，项目仍PARTIAL；当前进程及证据以[state](runs/A3.3-A3.4-joint-20261013/state.json)与本轮controller-checkpoint为准。恢复入口见[中断接续记录](runs/A3.3-A3.4-joint-20261013/resume-after-platform-interruption-20261014.md)。

当前真人2026-10-13明确授权A3.3与A3.4做完一起完整独立验收，见[新授权](runs/A3.3-A3.4-joint-20261013/user-joint-acceptance-20261013.md)。覆盖先单独正式接受A33再实施A34的顺序。A3.1、A3.2已正式独立接受；A33 v3/S0/S1成果承接，source/非editable wheel场景各691参数分段自查已root封存，A33正常装配已封存分段自查，A34共享层已停写并由root核验21737原件及19运行资源0；对照与测量已平台中断，完整联合自查/独验尚未执行，项目仍PARTIAL。旧暂停/恢复/失败/验收保持原文，不作当前停止门。

[合并正式包](runs/A3.3-A3.4-joint-20261013/package-v1.md)与[state](runs/A3.3-A3.4-joint-20261013/state.json)：185父/177运行、568原子(269+95+73+71+60)、55回归、6注册与40000正式实验不减。fresh联合PACKAGE_REVIEW后唯一S2完成真实正常装配/CLI/部署/256/维护/文档并冻结接口，再研究共享串行与独立文件/资源worker；全部STOP与资源核验后唯一联合整合、一次完整selfcheck和全新完整IMPLEMENTATION_ACCEPTANCE。有真正阻断最小补正、保失败并换新完整reviewer。PACKAGE_READY或分段自查不是接受。

| 角色 | 请求配置 | 职责 |
|---|---|---|
| 主控 | Astra / 用户当前设置 | 授权、精确所有权、调度/冻结、证据与接受 |
| worker | OpenCode Go deepseek-v4.1-flash / max | 批准范围实施/补正、自查、停写 |
| reviewer | gpt-6-astra / high，每轮新任务 | 包审与完整实施验收分离 |

有效metadata未观测就记UNKNOWN，不将请求配置冒充后台证明。[实施契约](implementation-contract.md)、[验收契约](review-contract.md)及[原契约](runs/setup/codex-astra-sol-v1/workflow-contract.md)完整性/独立性/安全要求保持，推进次序以新真人授权为准。

同类有限运行适配已持续真人批准，原话见[历史](current-policy-history.md)；不重复问电源/额度，不降低验收或改旧caps/保护，不扩大部署权限。有限detached supervisor真实落native child退出/原件与精确owner资源清理，不能因宿主session缺席伪造0。网络失败先尝试setproxy。

共享接口/迁移/fixtures先串行停写冻结；按精确文件与独占资源分工、不消费peer半成品；显式移交后唯一整合。范围/接口实质变化fresh包审。不删assert/skip/放宽预期；原SM2/SM3、PG/TLS、完整预算撤销、10有效竞争、真进程恢复、source/wheel、前段与历史/等价探针、原始失败证据保持。重复已通过且真实未受影响检查应复用，最终联合完整自查与新独立验收必跑。

不查额度、不Git发布；保全部既有提交/index/dirty/untracked，不reset/clean/强推，不改Git身份或保护。发布另需当前真人授权和实际CI/审核，PR6例外不沿用。只清理核实fullID/owner的自有资源，不连接/inspect/修改外部容器，不prune/shared down。主控有限guard单独管理，worker/reviewer不触碰。最终联合接受、材料和精确自有清理后停止。

现行文档只保当前事实/执行规则/入口；历史授权、失败、接受、SQL与锁保留，[历史约定](current-policy-history.md)、[历史问题](issues-history.md)按需追溯，不重复生成长文。[A3.2接受](runs/A3.2-evidence-20261011/acceptance.md)与[机器记录](runs/A3.2-evidence-20261011/acceptance.json)不重开。
