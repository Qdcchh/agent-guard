# A3.3 正式任务包 v3：补齐本地注册确认

v2 PACKAGE_READY 后 S0 已实施并在真实缺口 A33-S0-001 处 PARTIAL STOP；13路径成果保留，132自有容器及45卷/网络已主控亲核清退，原1417证据完整保留。完整S0/阶段未接受。本v3尚未 PACKAGE_READY，不授实施。

仅增加 additive audit.delivery.confirm_registered_tx 与明确核心所有权，demo.register_bootstrap 在独立 audit 事务成功提交后复用它。完整契约见 [interface-v3.json](interface-v3.json)；现有真实API/DTO/file keys见 [冻结部分接口](shared-interface-s0-r1.json)。可信operator是已有威胁边界，确认函数不伪造外部签名回执，不开放HTTP/ENV/holder操作。

原 [v2包](package-v2.md)、D1—D4、原A2/A3任务及所有安全义务不减。v3 requirements原173父项/165运行义务与269+95+73+71=508原子逐字段保持，55补正节点保留；为原A33-05.05/10.02补6必需注册案例和3计划根，计划总根20，实际参数/节点仅最终collection确定。

正式附件：requirements-v3.json、node-bindings-v3.json、ownership-v3.json、runtime-plan-v3.json、interface-v3.json、accepted-api-bindings-v3.json及原upstream-pins.json。v1/r1否决与v2/r2接受/STOP不改，实际S0 partial根核 [报告](s0-partial-r1.md)。

无schema/migration/依赖/预算/撤销/信任变更；旧delivery全部11函数AST和原delivery测试86assert保留。补正writer新Sol/low独占15路径，现已冻结13路径最小承接，不重写。新独立Sol/high全覆盖包审后才派writer；其局部源/wheel实测+STOP/资源核验后冻结共享接口，再派原S1独立场景与部署writer，全部STOP后唯一S2整合完整自查。最终全继承20组+新增71原子+55补正+6注册案例source/非editable wheel及新完整独立验收必须实际完成。

运行前置固定三PG --locale=C --encoding=UTF8，实际C/C/UTF8核验；publisher单列UPDATE(evidence_ref)满足既有FOR KEY SHARE，不加全表UPDATE。g3 locale、g4 SQL_ASCII、g5权限/REGISTRATION_REQUIRED等所有失败保留。原r8 wheel二进制copy失败且镜像已清退如实记录；下一最终wheel重新构建并保原件，不补造旧二进制。root有限R13 guard单独管理，不由worker/reviewer清理。

连续真人范围至A3.4完整独立接受后收尾STOP；不Git发布、不查额度、不问重复有限装配批准、不加非阻断功能。项目仍PARTIAL，无绝对无缺陷结论。
