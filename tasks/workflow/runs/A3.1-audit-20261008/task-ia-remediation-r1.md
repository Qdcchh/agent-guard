# A3.1 独立验收 r1 最小补正

唯一writer `/root/a31_s2_resume_low_r1`，请求 gpt-6.1-sol/low，有效metadata UNKNOWN。真人授权沿用 user-resume-low-through-a31-20261010.md；只完成A3.1后停，不进入A3.2或Git。主控负责正式state/task/ownership/接受。

先读AGENTS/AGENT、current-policy、implementation/review-contract、原workflow-contract、原始A2/A3.1任务与接口/安全/验收、正式requirements-v1及最新v4/v5绑定、原S2任务、正式review-r1.md及其全部实际缺陷证据。r1全冻结493/所有writer STOP/资源0已经主控亲核；保留原失败、全部dirty/untracked、SQL及依赖锁，不reset/clean。

稳定阻断A31-IA-R1-001：默认legacy未启用stream，binding/baseline均None。before_create(CREATED)或after_link(CREATED/EXISTING)真实等待跨过proof/token期限后，当前仍提交。对应A31-S01.04；source/wheel各14探针8P6F/native1。原件在artifacts/workflow/A3.1-audit-20261008/full-acceptance-reviewer-sol-high-r1，不覆盖。

独占正式写权仅 `src/agent_guard/ledger/service.py`、`tests/integration/test_evidence_binding.py`。允许在本轮新自有ignored目录 `artifacts/workflow/A3.1-audit-20261008/ia-remediation-low-r1/` 写运行装配、探针、报告、raw/XML/native及资源清单；不覆盖旧证据或其他正式文件。原S2的23路径写权本轮不继续生效。两个正式文件开工前记录实际完整SHA与diff；保护其全部既有成果。

最小修复：EXISTING执行after_link后，CREATED执行before_create或after_link后，即使binding/baseline均None仍执行既有末尾_final_bound_check。保留deferred约束flush、locked rows reload、路径/撤销/期限与最后真实DB clock；保留旧无hook语义、hook exactly once/None契约、EXISTING不执行before_create。无接口、SQL、依赖或安全模型变更，属于恢复已批准同一义务，不重新包审。

补正式有意义回归：三种实际执行路径×proof/token真实过期、完整AG全表回滚、正例、exactly-once及不该执行的hook；真实PG时钟有限等待而非mock，错误分类保持原标准。不可删除/skip/放宽原断言、预算、撤销、签名、TTL。先 source 与正常noneditable wheel 跑原独立14及新回归，全部闭合再长组。

承接成熟运行recipe与最新source native proc/clock actual-wait/增强QUERY装配，重新创建自己的fresh fullID/private/PID/DB；新输出均本轮目录。UUID/角色按正式fixture要求，integrator-source/wheel，token固定78baf8708f66-integrator-source/wheel、project固定ag-a31-78baf8708f66-integrator-source/wheel及正式对应container/DB名，不加attempt前缀；fresh独立性由实际新fullID/private/PID与自有空DB证明。旧资源已清零，不借用reviewer资源或PASS。验owner/project/mount/caps/UID/start/argv/PGID，仅精确自有资源清理，不碰verivote。网络失败先setproxy。

完成source/wheel完整20组自查及141/133/269/95闭包。ledger SDK实际改变，不能声称旧SDK SHA未变；仅确证真正未受影响的组才可保留已核自查证据，影响SDK/调用链的组重跑。当前收集数按实际新增测试调整完整集合与精确XML/native节点守卫，不减少原4222/1000或原组集合；整组7200有限预算仅沿用完整nonclock，其他原门不降低。10轮竞争、真进程恢复、历史原件与现行等价探针、真实SM2/SM3/PG/TLS、clock完整1000等不减。

原r1 replacement六个final argv过渡空值不是新的产品缺陷；本轮在必要身份阶段保实际ARM native记录，不cache回填或空argvsignal，不给每个短命PID另加硬门。同步observer超过名义2秒如实记录，正式任务未规定总墙钟≤2秒；保5秒observer/6秒join有限failclosed，不扩工具硬化循环。

完成后写简短实施报告、真实矩阵/原始证据manifest，保所有原失败，停止全部自有writer与进程，精确归属清理resource0，回交STOP(native_status COMPLETED_STOPPED)。不能自己关闭issue/标ACCEPTED；主控亲核后整树freeze，另开fresh Sol/high完整独立复验。
