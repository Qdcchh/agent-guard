# A34研究共享串行实施

AUTHORIZED_DISPATCHED。主控已核验S2及纯workload实际STOP、完整SHA集合/接口/source与wheel最大256/原件manifest和自有资源0；精确激活记录见a34-shared-activation-v1.json，仅授其中10路径与独占evidence，不授其它阶段。请求worker gpt-6.1-sol/low，effective UNKNOWN。

完整依据为本目录package-ready-v1.json、requirements-v1.json、node-bindings-v1.json、interface-v1.json、runtime-plan-v1.json、ownership-v1.json及真人联合授权；原185/177、568原子、55回归、6注册、40000正式实验不减。读取AGENTS/AGENT及实施/验收契约、原A34合同与实际生产调用链。历史草案状态与接口猜测不能代实际冻结接口。不重复包审或生成大篇规划。

本段唯一10路径：
- experiments/agent_guard_bench/__init__.py
- experiments/agent_guard_bench/oracle.py
- experiments/agent_guard_bench/research_contracts.py
- experiments/agent_guard_bench/research_store.py
- experiments/agent_guard_bench/research_service.py
- experiments/agent_guard_bench/research_worker.py
- experiments/agent_guard_bench/research_evidence.py
- experiments/research-schema.sql
- experiments/baseline-capabilities.json
- tests/fixtures/a34_experiment.py

workload.py/workload-v1.json/test_a34_workload.py由纯输入writer冻结后只读消费；其root读回在artifacts/workflow/A3.3-delivery-20261011/controller/joint-workload-root-readback.json，Py3.14纯unit11通过而ruff缺模块/Py3.11未跑，利用本段已有合规Py3.11环境补验证这些纯unit，不另建业务资源。固定原始mode名称staticACL/realSM2delegation_noAtomic/complete/realSM2Bearer分别对应现行简写staticACL/noAtomic/full/Bearer，必须一一公开映射，不产生新mode或混统计。S2全部生产代码/部署/文档、SQL迁移、依赖锁、formal workflow全部只读。不写三baseline、measurement及最终报告；必要新路径先报告真实功能缺口。原件仅主控激活时分配的独占ignored根，不spawn/Git/远端/额度/foreign/rootguard。

实现一次完整共享行为及实际调用方：互斥真实ResearchPoPContext/BearerContext/ACLContext，严格schema/规范intent/完整signed source/原件引用，authenticate→accept→claim→run/reconcile→finalize→RR oracle可运行公开API。PoP使用真正InvocationVerifier的公开verify_static与own stage_evidence callback，加PermissionSnapshotProvider.load；先结束静态读取TX，再开始同authority实例研究accept TX。生产没有PublicInvocationVerifier类，可仅研究import alias。Bearer仅研究组合公开verify_compact_jws/validate_access_claims/validate_child/IdentityResolver/PermissionSnapshotProvider与独立严格intent parser；proof=None、holder_possession=NOT_VERIFIED、未验来proof=IGNORED，禁止伪VerifiedInvocationBundle或private verifier。ACL的认证与三角色批准policy由后续baseline调用同可信共享接口，不能allow-all。

独占research schema/角色/表与独立DS实例；r34计数、immutable材料/operations/path/quote/first_ref/proofs/links/events/nodes/leases/outbox齐全，原生产ag_grants预算写入0。FOR SHARE所需权限实授最小非预算列UPDATE或自己独占实例的可信研究authority，记录实际SQL权限，不能弱化生产角色。accept锁序sorted principals→task→root-leaf authority FOR SHARE持至commit；精确businesskey锁可串行同key，但noAtomic不能共root/task预算mutex、生产FOR UPDATE helpers、锁升级、KEY SHARE、SERIALIZABLE或lost-update旧值写回。源/active/revoke/所有ancestor TTL与最终DB clock在同TX重验。

noAtomic全祖先RC read/check→仅受控安全探针可用pre-first-update barrier→普通counter=counter+delta，无预算<=limit CHECK/条件UPDATE；Bearer全祖先独立研究counter FOR UPDATE预算原子。proof登记在idem shortcut前；fresh重试当前验权、原意图/报价/首次材料完整比较、不再次计数；同proof拒绝。新意图解析失败重查原candidate，未知/被删报价不得重定价既有操作。约束flush后最后DB clock核token/proof/authority，之后无SQL/network/sign直到commit。真实counter高水位与每次delta可独立回放。

原A34-06.04及既有外部query语义也由本共享段闭合：公开查询适配使用genuine InvocationVerifier.verify_result_read及真实PermissionSource（PoP），Bearer/ACL使用诚实互斥query context；事务中当前来源/权限/持有者/路径/operation归属与最终clock重验，PoP新鲜proof独立purpose/endpoint登记，不用invoke context代query，不扣业务调用、不泄foreign结果。共享API清单是最小集合，必要query方法放既有批准research_contracts/service/store内，不扩大生产入口或研究安全范围。

内部worker仅执行持久已接受不可变意图，用真实MockDownstream公开execute/query与独立连接/事务/服务凭据；holder无DS/PG权限。持久fenced lease TTL30、到期旧worker拒终局、UNKNOWN保留预留/claim保持UNKNOWN、EXECUTING接管先query、迟到effect最多一次。终局原件/完整quote/result验证与所有祖先counter/event/node/outbox同TX；撤销后内部恢复仍可处理既有意图，外部重试仍拒。研究缺独立签名回执/审计能力明确N/A，不伪造full证据，不把plain JSON哈希称独立audit。

fixture复用被冻结正常真实TLS/三holder/AS链接口，不自己造root/child签名或越权初始化。提供后续baseline与measurement所需少量稳定公开输入输出（请求/body/token/proof通道、安全modecontext、信任/注册/quote、真实service/store/DS操作、独立oracle、资源manifest）；不要依赖ignored历史driver作为交付接口。所有长驱动有限detached manager、实际native退出原件、独占owner/fullID/finally清理；全存原始失败，网络失败先setproxy。

共享自查用有意义独立探针检验正负schema/current-state、new/existing/sameproof/changed-intent、所有祖先counter、真实DS once-effect、真实UNKNOWN/lease/fencing与真正kill/restart；证明FOR SHARE与正常撤销兼容、noAtomic真实两独立mid/leaf70000共root100000可两commit/DS140000而原production counters0，不能以假context或线程替代密码和进程。完整正式各10轮/两安装baseline安全与40000留最终联合selfcheck和新独验，不将本段smoke当完整接受。不重复已通过且未变检查；有必需缺陷只做本段最小补正。

完成实际API/DTO/schema/SQL权限/source与wheel非editable运行适配、capabilities真实许可集、冻结3纯输入SHA、完整命令/native/XML/探针/实际模块出处与资源原件，报告已跑/未跑。原件manifest必须含nestedSTOP、最后STOP/no_more_writes/精确资源0，交主控再分开baseline和measurement各独占文件。不能自记ACCEPTED或开始正式40000。
