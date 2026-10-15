# A3.1 S0联合补正任务 v4

PROPOSED_FOR_PACKAGE_REVIEW_NOT_DISPATCHED。真人已[恢复](user-resume-docs-20261009.md)；r3包审暂停未完成，仅其两处确认阻断作为补正依据。完整继承task-v2/v3、requirements-v1、node-bindings-v2及inherited-plan-v3的安全/运行/验收义务；冲突处以下及interface-contract-v4优先。旧包/报告不追改。

累计141父项/133运行、269继承断言和95新增原子不减；原14SQL和锁不改。requested worker Sol/medium、fresh reviewer Sol/high，effective metadata UNKNOWN。S0产品停写/自有资源0，source1139P、wheel834P/1F及旧140漏观测只属于历史失败候选，不当新候选通过。

唯一补正者只写6条精确路径：src/agent_guard/audit/journal.py、src/agent_guard/execution/receipt_publication.py、src/agent_guard/authorization/evidence_store.py、tests/integration/test_audit_lock_order.py、tests/integration/test_audit_atomicity.py、tests/integration/test_gateway_query.py。其余26条既有共享路径只读；无目录写权，发现额外真实必要范围先报主控，不自行扩大。ownership-v4继承原S1/S2边界。

1. 在journal head之前按operation→verified evidence取得必需父行KEY SHARE，保publisher outbox→弱FK→head；缺父拒绝、真实异常层/SQLSTATE、全部DB guard和原强锁不改。修对应注释。query强锁实际旧环10轮/mode；retry普通读/弱FK兼容竞争10轮/mode，禁止人为加FOR UPDATE造环。
2. typed AfterLink在原binding之后同connection/TX执行callback一次，原proof真实关联后/append前；None保持，非None/异常整TX回滚，原bind只一次/互斥约束不变。首组140加次数/顺序/XID最终断言；typed CREATED/EXISTING正常/None/非None/异常独立正负控，两种direct入口完整状态与基线核验。
3. GQ只改两个成功oracle，full_state/result_read_only绑定当次op/ref/proof、staging=False；保160窗口/16故障、所有负例、accepted-evidence别名/proof+1/DS全相等，不能过滤审计域。

先集中验证上述全部已知问题及缺父控制，再完整当前S0 source/非editable wheel ordinary、9owned集成、受影响1000时钟、bootstrap CLI、collection及质量/安装来源检查。真实未受影响证据可凭精确依赖证明复用，不把旧分段PASS拼为新整组PASS。全部STOP/资源0，主控核六路径范围/原件/实际共享API/SQL/fixtures后冻结，才派S1 service12/delivery6并行。

全部S0/S1 STOP后明确移交给唯一S2整合者，保三新增自包含历史等价文件、联合TLS/CLI及完整141/133自查；停写冻结后fresh reviewer亲审代码、全矩阵/独立探针，缺陷补正后再fresh完整复验。PACKAGE_READY不是业务接受，本段接受/证据资源收尾后停，不自动A3.2或Git发布。

包审完整核141/95设计矩阵、当前六路径和实际调用/FK/测试方案；不重复展开与本次无关的历史叙述或重新生成不变索引。未变绑定凭实际SHA及正式接受记录核对，历史原件仍可精确追溯。实施验收仍须完整亲跑，不能复用旧PASS。
