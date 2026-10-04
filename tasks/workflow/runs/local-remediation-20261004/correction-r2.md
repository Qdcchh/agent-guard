# B 整合窄补正 r2：确定性超时负控

## 授权和绑定

同一阶段用户已批准修复、复核、条件合并与本轮运行适配，见 [authorization](authorization.json)、[task-v1](task-v1.md)、[task-v2](task-v2.md)。原67项/60项要求及两个 PACKAGE_READY 不变。此补正在已审批17路径中的单一测试文件内，无新产品路径/依赖/协议/阶段，不需要扩大任务包或重新向用户索取已有授权。

对应 [review-r1](review-r1.md)，fresh reviewer `/root/acceptance_r1`，NOT_ACCEPTED；报告SHA256 `f1a695a978df8d796c1937a6ee9cdc739e184ade5d109755f8e185fa2828af54`。241项候选摘要 `4f757cd9f3742d50a9f14844977a70aa933449ed7e9964d3d9c2988601b092e5`；reviewer原生completed、资源已清、首尾一致。实施继续由 `/root/implementation_r1`（请求gpt-6.1-sol/medium，有效后台UNKNOWN）串行处理，主控不写测试实现。

## 精确所有权

唯一产品可写路径：`tests/unit/test_execution_concurrency_oracle.py`。

worker仅可另写自有 `artifacts/workflow/local-remediation-20261004/worker-correction-r2/` 的脚本/日志/XML/报告/清单，最终 `implementation.md` 由主控原样复制到正式运行目录。其他一切候选、旧实施报告、reviewer/controller证据、SQL、源代码、依赖、文档和任务控制文件只读。完整派发基线由主控随后保存于 controller/correction-r2-dispatch-baseline.json。

## 必须补正

| ID / 需求 | 触发和影响 | 修正与回归 |
| --- | --- | --- |
| BR-FINAL-P13-TIMEOUT-CONTROL / WF-QUALITY-CHECKS、B-15、B-17 | P2；正式测试在 `_race(...timeout=0.05)` 正确timeout后即要求entered，延迟线程启动会使负控误失败。独立两探针及10/10重复已保留，详见review §6 | 明确区分“尚未启动”与“已进入阻塞体”并用有界事件同步证明目标分支。受控延迟启动也应正确判断。不得只扩大50ms、删除entered/timeout/缺完成/精确异常断言、skip/xfail或吞错。保留真实线程阻塞、有界join和finally释放；确保每次命中期望分支且所有自有线程退出 |

审查者原探针位于 acceptance-r1/probe_oracle_scheduling.py 与 probe_oracle_scheduling_repeated.py；只读原件，在worker自有目录运行。若旧探针直接调用已重构测试函数的签名，允许仅适配自有副本调用方式并保留原件/diff/等价说明，不能删掉延迟条件或断言。至少覆盖正常启动、迟延启动、目标体已进入阻塞、缺worker完成、RuntimeError、无关ExecutionError和精确LEASE_LOST。用正负控制证明删去/禁用oracle超时能力时测试不能假PASS；不改正式 `_race`。

## 验证和停写

使用独占Linux Python3.11普通非root环境及PG16，标签/ID/网络/DB有清晰owner；不得连接或清理原三容器。同库含固定DB级advisory key的测试必须串行，额外探针使用不同数据库；不同schema不当作DB锁隔离。所有shell日志脱敏，不输出原始DSN/凭据。

本轮worker可按纯测试影响范围执行：新旧oracle全部参数节点、受控调度反例及重复正负控制、完整非集成、真实P13文件各原10轮、ruff check/format和diff-check。若需要范围外修改先报告，不擅自扩展。最终新reviewer仍独立完成原67/60、source与非editable wheel整段和历史/新反例，不用本轮局部自查放行。

保留真实命令/exit/日志/XML、文件指纹、原失败/适配diff、环境资源与清理。报告新旧覆盖、确定性依据和局限，标FIXED_PENDING_REVIEW/READY_FOR_REVIEW；禁止自行关闭issue、ACCEPTED或Git写。报告链接采用绝对文件路径以便主控原样移入runs。停写后主控核对全部只读候选、原报告/证据未变，冻结并新开reviewer。
