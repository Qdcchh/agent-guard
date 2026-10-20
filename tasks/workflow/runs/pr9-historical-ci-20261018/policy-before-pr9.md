# 现行角色与范围：COSM2全量实施（2026-10-17）

真人最新授权：“你直接把B的部分也做了吧，从头开始，一直到我发给你的那个markdown里面的所有内容都被实施”。范围为原《双域协同SM2实施规划》第0–5节、A1–A7、B1–B9及C交接清单，覆盖此前只做A/不得接管B的限制。不恢复旧A3.3/A3.4四万次长实验。原始规划保持原样，当前任务包及澄清见[package-v1](runs/cosm2-full-20261017/package-v1.md)、[包审](runs/cosm2-full-20261017/package-review-r1.md)、[实施接口](runs/cosm2-full-20261017/implementation-notes-v1.md)。

|角色|请求模型|职责|
|---|---|---|
|worker|gpt-6.1-sol / low|按共享接口串行冻结、独占文件/资源实施与补正，自查、STOP|
|每轮全新reviewer|gpt-6.1-sol / high|PACKAGE_REVIEW与完整IMPLEMENTATION_ACCEPTANCE分开，独立静态检查/实跑/探针|
|主控|当前会话配置|直接核对真人授权、资源与候选SHA、完整报告、整合交付及接受|

请求参数由实际派发工具明确设置；后台effective metadata未观测，记UNKNOWN，不冒称后台证明。

当前完整阶段 **ACCEPTED**：全新high r2完整独验与主控复核已完成，详见[正式接受](runs/cosm2-full-20261017/acceptance.md)及[原样r2](runs/cosm2-full-20261017/review-r2.md)。非PG2072+host1补闭、真实PG552、付款142、并行延迟8和独立7探针均通过；图/数据/媒体/C来源核验闭合。r1因C10签前窗口不稳定被否决并原样保留，仅补测试同步后全新r2接受。2674开始/结束SHA与主控复算一致，自有资源/秘密0。现在仅接受状态和最终包装元数据更新，不修改受审代码/实测数据。不代表旧A3长实验完成。

## 持续有效的工程与审查规则

- 保留继承index/dirty/untracked及历史失败；不得reset/clean/覆盖他人工作。不commit/push/PR/合并，不改Git身份/保护；旧发布授权不沿用。本地冻结用完整内容清单SHA和候选命名，不给旧HEAD打标签冒充当前实现。
- 遵循AGENT.md及[实施契约](implementation-contract.md)/[审查契约](review-contract.md)的安全、独立性、实跑、资源和证据要求。两份契约内旧模型/旧阶段矩阵仅为历史，不替代本轮当前角色及完整原COSM2矩阵。已有真人连续授权，不重复问阶段实施许可。
- 共享API先冻结并移交，文件与资源独占，禁止消费半成品。停止全部候选writer→冻结源码、测试、fixtures、配置依赖、资料与原始数据SHA→全新high reviewer。审查期间不写受审文件；reviewer仅写自有排除目录、只清理自身资源。完整报告原样归档，有阻断则保失败补正并换全新reviewer。
- 迁移001–009与V1/V2/V3旧字节、GM-MVP-1语义保持。P1/网关/下游最终SM2验签只用成熟实现；份额曲线计算仅半诚实非常数时间原型。零假签名/假成功/删负例/弱化预期；保全部祖先撤销预算、幂等、恢复和原证据检查。
- 只创建/连接明确归属的独占测试资源，仅TEST DSN、独立网关与下游事务。PG/网络无共享down/prune，不inspect无关容器；秘密env0600不输出，份额0600/目录0700，令牌/秘密不进公开结果。日志敏感字段须显式脱敏并记录原件是否可用，不冒称逐字原样。
- 原始数据/失败历史不改写，排除与失败原因公开。性能需记录镜像/CPU/仿真/计时边界/真实n与并行负载；示意、现场、本地保存回放分开。半诚实n=2/同主机/非OS强隔离/物理内存擦除不可证、B9动态状态复核边界随交付披露。
- 最终完整原规划闭合、fresh独验接受、材料交付及精确自有资源归零后STOP；无用户授权不向C或其他人发送消息、无Git发布。

本次重写前的全部原文（含旧授权、模型、失败和接受记录）已按字节保存为[历史快照](runs/cosm2-full-20261017/policy-before-current-rewrite.md)，不作为当前阶段执行指令。原有[current-policy-history](current-policy-history.md)、历史stage原件保持。冻结前仍以当前本页、原COSM2需求和本轮最终接受记录为准。

## 完整实施独验r1与补正

全新gpt-6.1-sol/high审查已STOP，结论NOT_ACCEPTED，唯一阻断COSM2-R1-001：C10两项仅一秒有效期，完整PG组551pass/1fail在签名前被AUTHZ_EXPIRED，未到达目标网关断言。非PG2072pass/1skip由host1pass补闭，x402142pass，其余原矩阵通过；详见[r1原样报告](runs/cosm2-full-20261017/review-r1.md)。2021开始/结束SHA相同，审查自有资源0。不得以单独C10十次绿抵销失败。当前仅low worker独占补正两C10同步，保持真实到期后401 EXPIRED及零效果，生产安全逻辑不改；其后新候选冻结、全新high r2完整独验。candidate2仍是失败轮候选，绝非已接受交付。

补正worker已STOP：唯一测试文件变更，完整552/552、并行签前延迟8/8、相关非root89及目标质量检查通过，自有资源0。原401/EXPIRED、真实DB最终检查及零效果断言保持且增加可达性证明；[补正自查报告](runs/cosm2-full-20261017/remediation-r1.md)。此为自查，当前冻结candidate3并交全新high r2，r1失败不覆盖。

本页下方r1与补正段为过程历史；最终状态以本页ACCEPTED及acceptance.md为准。
