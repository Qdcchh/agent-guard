# A3.1 精确继承补正包 v3

2026-10-09，PROPOSED_FOR_PACKAGE_REVIEW_NOT_DISPATCHED。当前实施仍按 v2 的31条 S0 allowlist；此草案不授新路径写权。当前writer已原生STOPPED_NEEDS_REPLAN、自有资源0且主控读回，完整S0未通过；本包同时解决实际40P01锁序矛盾并新开Sol/high PACKAGE_REVIEW。worker 保持 Sol/medium，有效 metadata UNKNOWN。

继承 [task-v2](task-v2.md) 的完整范围、原始约束、安全语义、运行与验收要求；其建包时点 pending/NOT_RUN 措辞作为历史，当前事实以 [state](state.json) 和实际运行证据为准。本次仍只完成 A3.1 后停止，不进入 A3.2—4或 Git 发布。

本补正依据是 source `s0-gateway-scope-r1` 真实4P/1F、exit1：成功 QUERY 增加合法日志/head，而两个原测试成功全表比较仅允许 proof 增加。新增一条共享测试文件写权及三条唯一整合者的当前等价测试路径，并精确恢复三条既有共享路径用于实证锁序补正，见 [ownership-v3](ownership-v3.json)。原 [requirements-v1](requirements-v1.json) 141项/133运行、269继承断言和95新原子、[node-bindings-v2](node-bindings-v2.json) 23拟节点/7原生义务/95有限控制、完整119项继承义务均不改。

共享补正只在fresh v3 PACKAGE_READY后启动。sole Sol/medium worker仅可写四路径：src/agent_guard/audit/journal.py、src/agent_guard/execution/receipt_publication.py、tests/integration/test_audit_lock_order.py、tests/integration/test_gateway_query.py。前二生产路径仅必需FK父锁前置及真实注释；锁序测试新增query/retry各10轮确定性交错及两个缺父拒例；GQ仅原两个成功oracle，保全部160窗口、16故障及原负例。其余28条既有共享路径只读，遇真实需改的缺陷再报精确范围，不泛授31写权。既有test_receipt_publication.py无需写入，现有完整竞争测试原样回归。补正后完整S0 source/wheel、当前ordinary、bootstrap CLI、受影响时钟矩阵、完整collect及所有原件核验必须完成，全部STOP/资源0/实际共享接口冻结后才派S1两writer。三个新增等价路径仅S2唯一整合者写；全141/133 fresh IMPLEMENTATION_ACCEPTANCE不变。

具体接口补充见 [interface-contract-v3](interface-contract-v3.md)，继承运行与原件绑定见 [inherited-plan-v3](inherited-plan-v3.md)。包审须亲核当前完整候选、全部义务和新增路径，不把本草案、S0分段自查或旧 PACKAGE_READY 当本 v3 接受。

[当前节点补充草案](node-bindings-v3.json)绑定新增正式初始流200、真实AS支路10、非零拒绝80、容量回滚2、TEXT原件12、初始oracle负控18及旧TXseed1项/mode和新unit实际收集节点；它补充原v2，不减少原义务。S0仍在完整自查，旧TXseed复用及嵌套mutable节点已由真实收集绑定，本次STOP实际源字节及已执行collection会绑定；补正后完整source/wheel collect和完整自查仍必需；大型实体高水位未运行的局限明确保留，不能用静态检查冒充实际PG高水位运行。

当前实证失败来源：source owned-r7 1139P；wheel owned-r6 834P/1F、40P01。shared resume-r2只读诊断后NEEDS_REPLAN/资源0，无产品改动；旧candidate通过项不等于补正后新候选通过。锁序及缺父拒类见interface-contract-v3，本轮包审须核实际FK及所有调用方锁链、四条精确例外和原95控制全部保留。
