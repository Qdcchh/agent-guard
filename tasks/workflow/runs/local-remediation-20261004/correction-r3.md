# B 整合窄补正 r3：隔离超时目标与多线程启动

同一用户授权、阶段、task-v1/v2 PACKAGE_READY、67项/60运行义务和运行适配保持不变。本补正仍仅一个原批准测试路径，属于BR-FINAL-P13-TIMEOUT-CONTROL残余，未扩展阶段/接口/源代码。

## 依据

[正式review-r1](review-r1.md)、[correction-r2](correction-r2.md)、[r2实施历史交付](implementation-r2.md)、[r2后只读诊断](diagnostic-r2.md)。r2自查曾952非集成、P13四组各10、调度60通过，但主控读回指出仅一个线程延后的缺口，worker独占3.11只读实测10/10确认：peer先到0.05秒Barrier后BrokenBarrier，blocked永不进入，负控在startup entered误失败。这是正式测试不稳，不是业务错误或oracle假PASS。r2报告只代表当时交付，不能放行当前版本；原报告/两轮探针失败/全部日志保留不改。

## 唯一产品范围与确定性要求

worker `/root/implementation_r1`（继承请求gpt-6.1-sol/medium，有效后台UNKNOWN）仅可改 `tests/unit/test_execution_concurrency_oracle.py`。其他候选及原worker/reviewer/controller证据只读。新证据和implementation.md只写自有 `artifacts/workflow/local-remediation-20261004/worker-correction-r3/`，主控原样复制报告。派发快照 controller/correction-r3-dispatch-baseline.json。禁止Git写、主控state/issues修改、新依赖或业务源修改。

采纳最小职责隔离方案：执行超时负控使用 `_race([blocked], timeout=0.05)`，使单个真实阻塞者的启动就绪独立于多参与者Barrier启动偏斜。必须保留entered为真、release未放行、线程仍alive、精确timed out及finally有界释放/退出的断言；startup就绪等待有界、超时明确报错。不仅扩长50ms、不跳过或吞错。补充简明注释说明为何单参与者正确隔离此测试目的。

这不是删除多线程验收义务：既有多参与者success/expected error/RuntimeError/无关ExecutionError/缺完成负控逐字保留；正式P13四组各10轮及完整最终矩阵照常执行。原两线程单延后反例继续保留为r2版本失败证据，修后新超时负控只有一个参与者，必须说明触发条件结构变化的原因，并在自有等价探针中证明此参与者真实迟延启动也正确timeout而不会假失败，不冒称原“peer已进barrier”的场景仍存在。

## 验证与停写

完整oracle、正常/200ms延后/join-gate各10轮、startup不可达/伪造timeout/禁用真正timeout检查各10轮，全部目标分支/真实异常/全线程退出；原r1调度反例（保原件、仅自有探针调用/旧预期适配与diff）。默认pytest非集成全套、真实PG P13四组各10轮、Ruff check/format/diff。Python3.11普通非root、sys.flags.optimize=0，PG16及独占资源owner/ID；同DB含固定advisory key测试串行，PG不用于纯线程探针。日志和进程观察不输出DSN/凭据。

先确保自有Timer/Thread装配顺序和pytest assertion-rewrite语义正确；原装配失败照实保留，别为字符串诊断反复误判业务。自有探针可用--assert=plain但默认全套必须保留。停写前核精确候选范围与只读旧证据，按stage entries/diff口径核Git，不把raw index字节和git ls-files摘要混比。

交付绝对路径链接的完整implementation.md与证据索引/哈希、清理和stop-binding，标FIXED_PENDING_REVIEW/READY_FOR_REVIEW。主控核验后另开fresh reviewer全67/60、source/wheel整体，不由本自查关闭issue。
