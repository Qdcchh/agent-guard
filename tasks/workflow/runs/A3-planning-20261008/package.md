# A3.1—A3.4 规划基线 v1

日期：2026-10-08。包类型 `PLANNING_BASELINE`，授权见 [authorization](authorization.md)。这是把已有目标、详细草案及已接受 A2 接成一致接口/验收计划的文档包。所有 A3 产品行为 **NOT_IMPLEMENTED / NOT_RUN**，四个业务阶段正式包 **NOT_READY**。本轮独立审查使用 `review_kind=PACKAGE_REVIEW`、`review_scope=PLANNING_BASELINE`；若结果为 PACKAGE_READY，其对象仅本规划文档包，不能填到 A3.1—A3.4 的业务 dispatch 门，不代替业务包审或实施授权。本轮结束后停给用户切换主控。

## 1. 权威范围与当前基线

原始目标以 [验收矩阵](../../../../docs/acceptance.md)、[接口](../../../../docs/oauth-oidc-sm2-mvp.md)、[安全模型](../../../../docs/security-model.md)、[A2原任务](../../../A2-execution-gateway.md)为准；历史任务“待实施”、绝对机器路径和旧主体分工按历史解释，安全行为继续保留。项目由用户本人继续，不恢复同学交接文档。初版 M1—M13 与成熟版 SEC/CON/REC/AUD/E2E/ENG、实验与最终材料分层记账，完整 A3 目标全部保留；10月20日不能推定为本次所有 A3 的完成期限。

实际本地分支 `handoff/a23-local-20261005`、HEAD `2a8cc7da4867ad1876350855c0ed5569c5ce6472`，保留现有dirty与untracked。已发布可移植快照 `a85a822085707874ef8dd6fb47c8601cf1a56c81` 与本地198项产品/测试/tools/SQL/锁/构建/CI指纹一致，见 [baseline.json](baseline.json)。二者文档/编排内容不同，不能为统一分支而reset/clean，也不能把旧混合本机提交直接推远端。未来实施开始先核实际分支/HEAD/index/dirty与产品指纹，再选明确保全既有成果的工作分支；本轮不做Git变更。

完整 A2 [接受记录](../A2.3-receipts-20261004/acceptance.md)及[独立报告](../A2.3-receipts-20261004/review-r2.md)实际完成。review原文SHA为 `b3b6dbbf591ee672552674df56364969e8ce6173551f501a74097e2c5705bece`；source/wheel各1185普通、2810PG、500时限通过，wheel增强原484P/3F保留，以未受影响407＋新原模块完整80逐case闭合，原增强单次不得写成487全绿。原始私有日志保留本地，不复制入规划公共文档。原A1/B失败、UNKNOWN原因、旧observer回执与安全维护局限保留，规划不重做或倒改A2接受。

现有真实调用入口是 `VerifiedExecution.accept/accept_response` → `ExecutionService.accept_invocation` → `ExecutionLedger.accept_bound/_accept_tx`，`AuthorizedQuery.query/_query_tx`，`ExecutionService._finalize`，`InternalPublisher.publish`，`verify_receipt_bundle`。`AcceptBinding`现有回调不等于未来事务内seed/after-link完整hook；现有publisher只锁outbox，未来日志接入不能反向拿task。实际bundle迁移含lineage001、authorization004—010、execution001—006共14份；execution007与audit001均为未来新增，原14份不得改。各源码字节已绑定，拟新增API的签名/契约与存在性详两个合同，不将草案代码当实现。

## 2. 规划内容及优先顺序

- [audit-contract](audit-contract.md)：A3.1日志/事务/检查点和A3.2导出/离线验证；[audit-findings](audit-findings.json)记录具体冲突与消解。
- [delivery-experiment-contract](delivery-experiment-contract.md)：A3.3部署/三holder和A3.4研究模式/调度/统计/材料；[delivery-findings](delivery-findings.json)记录具体冲突与消解。
- [requirements](requirements.json)：继承A2原119项/112运行标记/269 must_assert，以及A3新增66父项/299子断言逐字保全；[test-plan](test-plan.json)保存有限case/原子观察/计划节点和原生义务。
- [baseline](baseline.json)仅说明已接受产品来源；冻结审查文件清单由主控在全部writer停写后另存，本文件不自证冻结。

`original_*`来源标签及既有finite node中的旧候选/hash/owner/机器配额/状态均是历史来源，绝非本轮有效身份、授权、运行资源或collect结果。新计划按原义务→本轮合同消解→正式业务包实绑定的顺序使用；遇到实质语义差异须列稳定finding和独立包审，不默删原断言。当前同义别名仅可留内部标签；HTTP只用四个规范ToolId及字符串version `1`。

历史详细设计与followups已保留在作者本地 artifacts；本规划的安全接口和验收要求须在本目录自足，不能让未来模型“运行旧builder”自动视为完成正式建包。原实现前包审无需新测试已存在或可collect；新测试必须给精确拟文件/函数/有限参数/观察/故障点，实施停写后才将其绑定真实完整参数化节点与实跑证据。

## 3. 全矩阵与阶段依赖

| 阶段 | 新父项 / 运行项 / 子断言 | 依赖 | 必须形成的接口成果 |
| --- | --- | --- | --- |
| A3.1 | 22 / 21 / 168与A32合计 | 当前已接受完整A2 | scope/genesis/bootstrap、原子journal、checkpoint持久服务与sender、迁移/锁序/最终clock契约 |
| A3.2 | 18 / 18 / 同上 | A31真实接受与schema/公钥/ACK/历史接口 | bounded export、外部信任文件/锚、offline CLI和结果分维语义 |
| A3.3 | 14 / 14 / 131与A34合计 | A31/A32真实接受与实际CLI/配置 | 可信初始化、三个holder、服务/凭据隔离、真实演示、升级/轮换/备份恢复 |
| A3.4 | 12 / 12 / 同上 | A33实际接受，冻结实验版本 | 独立研究模式、固定workload、真实测量/全错误/效果oracle与最终材料 |

新增合计66父项/65运行标记/299子断言；继承A2 119/112/269原文保持。按当前继承口径，累计父项/运行项为141/133、159/151、173/165、185/177，仅为完整性索引，不能替代实际测试计数或判定。每段还保留全部30原项目目标和原A2 P01—P21的适用义务；成熟版尚未发生的目标按本段责任/后段交付标出，不提前PASS，不缩掉本段要求。

不新造51个继承wrapper：直接从实际accepted基线绑定旧测试函数、每个参数化节点和子断言，并把跨段新增效果断言明确写到新测试。unit不能证明PG持久、真实TLS、真进程死亡、50在途或正式40000调用；这些必须独立集成/原生运行。重复的目标映射可共享同一真实证据，不为了数字再跑无意义重复组。完整本段自查与fresh独立实施验收仍不可省。

## 4. 真正业务开工前的明确门

| 时点 | 必須核完 | 目前状态 |
| --- | --- | --- |
| A31正式建包 | 实际A2接受/原生STOP/全树与index；当前API/调用链/SQL绑定；全119继承节点/断言；新增22项及精确写路径/接口/有限case | 产品来源已实核；完整业务包尚未冻结/审查 |
| A32/A33/A34各自正式建包 | 前段真实接受与实际schema/CLI/接口/新增完整矩阵；本轮对应合同按已实现内容重绑定 | 前段不存在，明确依赖待完成；不是本规划缺陷或虚构accepted |
| 每段派发前 | 真人实施指令、对应业务包PACKAGE_READY、原生角色/owner、精确写路径/只读依赖hash、有限运行适配、无并行writer冲突 | 本轮不派发业务 |
| 启动自有资源前 | 本轮owner UUID、容器fullID/project/网络/卷/端口/DB/schema/role隔离清单；未知有效metadata保持UNKNOWN；依实际环境绑定有限配额 | 不复用旧PID/容器/DSN；本轮不分配资源 |
| 独立实施验收前 | 全writer原生停写、唯一整合完整自查、全候选冻结、实际新增collect与逐assertion映射、全部原始证据/失败、owner资源清单 | A3全部NOT_RUN |

未来切回6.1 Sol不自动让旧审查“过期”，但任何产品/接口/需求/包实质变化须重新冻结并独立审包。角色切换本身不改安全标准；新实际模型/档位依用户届时要求记录。仅计划期间UNKNOWN未来节点不伪装成BLOCKED的实现失败，也不能在真正派发前忽略未满足门。

## 5. 共有运行、证据与验收合同

真实Tongsuo SM2/SM3、OpenSSL互验、PG16、真实CA/SAN TLS、全部祖先金额/次数、当前撤销/新鲜性/幂等、UNKNOWN预算不释放和原接受事实恢复全部保持。源代码模式和fresh非editable wheel在各自清晰隔离环境全跑；wheel仓库外执行并验证父子进程site-packages来源与SQL成员，不能源码遮蔽。所有正式安全并发/故障组每参数10轮独立连接barrier/event，全futures/异常/SQLSTATE/退出收齐；SIGKILL/新PID/回复丢失须真实持久见证，不拿替身异常当真实崩溃。

每条完整前后oracle至少覆盖全祖先四计数、operation不可变事实/状态、proof/link、事件/节点、租约owner/version/state/expiry、outbox原材料/READY/稳定JWS、独立DS效果/拒绝，以及新增journal/head/pending/checkpoint。允许的孤立STAGED与业务零新增分开，副作用不明保留UNKNOWN。最终clock/租约核验在新增可能等待的SQL/约束/签名后，网络不持业务锁；新增日志失败回滚同事务效果，不从日志旁路创建业务成功。

有限期限采用当前草案的分类基线：普通DB连接5s/锁3s/语句30s，barrier15s，HTTP连接5s与按段read15或30s，child阶段120s/总180s/reap10s，离线验证300s、导出物化600s、容量预检1800s。它们是测试/运行规划上界，不改变token300s/proof≤60s/原lease。正式故意跨TTL的case须逐参数指定更长但有限等待（例如≤180s），同时保证真实expiry先发生、锁/语句timeout后发生，目标错误必须是期限或fence拒绝，不能拿timeout冒替。环境不够先保失败并调整经审查的运行配额/调度，不能减round/改token/删assertion。内存/FD/CPU/PG连接和容量在实际环境核实，旧电脑配额不是硬编码前置。

完整原始记录及时落私有证据目录，保存脱敏命令、起止、实际退出、XML逐case、DB观察、native PID/owner以及原件/脱敏双哈希。失败、中断、补正均保留，原件0600；公开结果无可用token/proof/DSN/私钥。只清理成功自建且fullID/owner/挂载可核资源，无关容器不连接不修改，不prune。全候选内的源码、迁移、测试、fixtures、锁、CLI/README与影响判断的旧调用方均冻结，不能只冻结diff。

本轮无新增运行依赖；未来确需依赖须说明用途/版本/许可/维护并更新锁与轮包验证。GitHub CI按届时实际head核验，现有timeout75只是配置；历史45分钟观测已过时，新增耗时先测再决定CI-only适配，不删测试、不假绿、不绕保护、不继承PR6例外。

## 6. 本轮停写、审查与接续

两规划writer各自精确独占 audit-contract/audit-findings 与 delivery-experiment-contract/delivery-findings；主控独占本package、requirements/test-plan/baseline/state、角色/当前入口与审查记录。其余产品只读。不把一个规划writer的摘要当独立包审，全部writer完成并停写后主控统一跨段接口，核全矩阵/字节保护/文档链接/JSON再冻结；新Astra/high reviewer只读全文、实际依赖代码与历史发现，在自有ignored目录写报告。

发现规划缺陷则主控按稳定ID补正，保留失败报告；实质修改后换新reviewer重审完整规划包。只有独立结论和首尾指纹成立才记录规划基线完成。结果限规划一致性，绝不表示已实现功能、业务包开工许可或产品无缺陷。完成后更新当前入口并停止；用户切回模型后以新明确指令开始A31正式业务建包/实施，不自动执行旧builder或全A3。
