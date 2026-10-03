# B 整合候选补正与合并任务包 v1

状态：USER_SCOPE_GRANTED / PENDING_PACKAGE_REVIEW。运行适配提案已由用户明确批准；包审无阻断前不派实施。

## 1. 授权、版本和角色

仓库：`/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`。HEAD `2051b402c99a3d400d8f12749287075e23a9a521`，基线 main `153f14e9be180a1eb26b0f0e0898048d45170569`，候选分支 `handoff/b-integration-20261003`。现有未提交文档修改属于上一轮用户授权的复核/清理，必须保留；准确清单在本轮 controller/initial-worktree.json。

用户本会话明确请求修复后再复核并合并 main；随后明确回答“批准本轮适配，继续修复与复核”。完整原文及适配范围见 [运行适配提案](runtime-addendum-proposal.md)。授权来源为本会话可见 user 消息/工具问题回复，不编造未暴露的 message_id。

主控负责包、状态、问题台账、调度/冻结及最终 Git 发布；单一 worker 显式请求 `gpt-6.1-sol / medium`；每轮新包审/验收 reviewer 显式请求 `gpt-6-astra / high`。请求模型和有效后台模型证据分开记录。保留工具创建/完成回执，writer 未确认停写不得复核。共享结果/参数/测试接缝彼此依赖，采用串行单 worker，不强行并行拆同一调用链。

## 2. 必读和完整要求

AGENTS.md、AGENT.md、HANDOFF.md、README.md、docs 四份文档、tasks/A2-execution-gateway.md 全文、A1-review-r4.md、A2-review-ckpt1-r2.md、workflow implementation/review-contract、templates、issues、A2.1 完整 acceptance/review-r8/各失败及补正记录、本轮适配提案、上一轮 local-quality-20261004/review.md 和对应实际产品/测试。

[requirements-v1.json](requirements-v1.json) 展开全部 **67 项要求、60 项独立运行义务**。继承原 A2.1 的全部31项和 B 24项、BR 12项，不以修复五个问题代替整段验收。A阶段旧“不引入B/不发布”措辞依当前真实授权和已整合候选解释为保护A语义/不进入下一阶段，不能误删现在已授权B范围，也不能削减具体安全义务。

## 3. 精确产品写范围（唯一 worker）

1. `src/agent_guard/contracts/execution.py`
2. `src/agent_guard/tools/params.py`
3. `src/agent_guard/tools/catalog.py`
4. `src/agent_guard/tools/results.py`
5. `src/agent_guard/execution/service.py`
6. `src/agent_guard/evidence/receipt.py`
7. `tests/unit/test_tool_validation.py`
8. `tests/unit/test_execution_result_variants.py`（新）
9. `tests/unit/test_execution_concurrency_oracle.py`（新）
10. `tests/integration/test_execution_concurrency.py`
11. `tests/integration/test_execution_final_boundaries.py`（新）
12. `tests/integration/test_verified_execution.py`
13. `tests/test_receipt_paths.py`（新）
14. `README.md`
15. `HANDOFF.md`
16. `tasks/A2-report.md`
17. `tasks/workflow/runs/local-remediation-20261004/implementation-r1.md`

全部其余产品文件只读。旧 SQL、state.json、workflow_gate.py、原工作流及历史验收/失败报告、依赖锁不改。主控独占本轮任务/requirements/state/issues/审查报告/调度记录；不在 worker 写期间修改其文件。worker 自有证据目录 `artifacts/workflow/local-remediation-20261004/worker-r1/`，不得写其他 reviewer/controller 目录。

新增缺陷或必需额外路径先报主控，由主控版本化范围/包审；不自行越界。无新依赖、无迁移、无协议签名语义变化、无历史受困数据修复、无 A2.2/A2.3/A3 开发。

## 4. 必须补正的行为与回归

| Issue | 修改要求 | 必需正负控制与状态断言 |
| --- | --- | --- |
| A21-R1-OUTCOME | 终局前把成功结果变体与操作工具一致性绑定；read 仅适用两 read 工具，保留 refusal 全工具语义；共享 bind_result 与执行器契约一致 | order/notification × execute/query 的 read-shaped 异常结果保持 UNKNOWN/全祖先预留、零终局/outbox；再取得合法结果恢复唯一效果/SETTLE。保留正常四工具、refusal、错误操作ID/金额/报价/反向变体负例 |
| BR-FINAL-ITEM-LIMIT | 参数接受前拒绝 >256 项订单，与既有 snapshot/result 读取上限共享常量，维持 bool/重复SKU/字节/深度/数量拒绝 | 256 项完整 PG 接受/执行/恢复合法；257 项及大数组接受前失败，proof/operations/预算/事件/outbox/下游效果零新增；不扩大持久读取上限 |
| BR-FINAL-RECEIPT-DUPLICATE | 离线完整祖先路径 grant ID 全局唯一；保留邻接/深度/holder/签名/时间/账本绑定 | 临时独立真实 AS/GW/三holder密钥、真实签名重算 root→middle→root 及重复ledger路径拒绝；合法三层成功，邻接重复/错序/缺祖先/摘要错拒绝。不得只传坏签名蒙混结构负例 |
| BR-FINAL-P13-ORACLE | 每个线程必须产生可核验结果或异常；有界同步/join；非预期异常由主线程失败；混合竞争只允许已核实的具体租约争抢错误 | RuntimeError、无关ExecutionError、缺worker完成/超时不得假PASS；合法LEASE_LOST竞争和UNKNOWN恢复保持。原真实PG竞争各10轮及全部祖先/效果/终局断言不删减 |
| BR-FINAL-RECEIPT-TEST-BRANCH | future-token 与 future-proof 条件互斥、可达；负例确实改变目标已签token的iat/nbf | 真正future-token拒绝、proof未来5秒接受/6秒拒绝、迟延回执及共同窗口/祖先/key正负控制保持；断言负例分支实际命中 |

不能添加 skip/xfail、宽泛异常断言或更改预期成“接受异常结果”来通过；测试替身仅限明确分层测试，正式密码/PG义务真实执行。

## 5. 环境、验证和历史等价

worker 与 reviewer 使用不同 owner 的 Python3.11/Linux amd64 容器、PG16 实例/网络，网关和下游为不同数据库/事务域；独立schema/只清自有资源。源挂载与日志目录分开；普通部署DSN清除。日志不输出密码/完整DSN/token/私钥。初始现有 agent-guard-a2-pg/verivote 不连接、不停止。

worker 自查：原锁全新安装、pip check、Ruff check/format、git diff --check、全部非集成与PG集成、新增回归、现有本地边界反例修后通过；真实worker进程恢复、规定组10轮、迁移历史checksum、真实TLS/OpenSSL、demo和文档流程按矩阵映射。所有命令记录 argv/退出码/日志/JUnit与环境，不能以固定测试计数代替覆盖。

最终 fresh reviewer 必须在自身独立资源重复完整 source/非editable wheel 运行、证明安装来源无editable/源码shadow/子进程路径正确；检查包携带SQL、空库/A-origin/B-origin升级/no-op/失败原子性；分别明确A1/A2.1/B回归、真实并发/进程/锁故障、TLS与OpenSSL和README/demo。无需依赖用户大模型API。

历史探针索引：`artifacts/workflow/local-remediation-20261004/controller/historical-probe-inventory.json`，已找到原本地A r8/B r2的27个Python文件；只读原件，在自有证据区按原语义复跑。旧过严合法tuple/list断言、旧B barrier与新principal锁之间的冲突要保留原失败，另存适配diff和逐项等价论证；不静默删case。缺失云端最后反例按本包和旧报告重建，明确新构建而非旧原件。reviewer自行设计其他绕过探针，不能只运行worker精选例子。

67个ID每行给代码/具体测试函数/断言、方法与本轮原始证据哈希；60运行ID不能仅inspection PASS。M1—M13与SEC/CON/REC/AUD/E2E/ENG逐项映射本段或后段，整体PARTIAL准确保留。必需项不能等价补齐则BLOCKED，不合并。

## 6. 冻结、补正和合并

基线完整 tracked/untracked/deleted 清单和只读文件 SHA 在 controller 证据区；每轮写后读diff，逐路径核所有权。worker 完成报告含实际变更、完整矩阵、未完成项/证据/资源清理，标READY_FOR_REVIEW或BLOCKED后停写；主控检查回执和进程，再冻结全部候选及本包/矩阵/契约哈希。每轮验收必须新 reviewer，首尾完整指纹一致；反馈回到worker补正再新审。

只有全部本阶段要求闭合、无已知阻断、主控核验原始证据后才接受当前候选。随后精确提交/推送/创建PR，远端最新main、CI和保护重新核对；必要更新主分支基线会使受影响验证重新进行。远端要求 `checks` 通过与代码所有者审核，不改保护、不强推、不自行批准/管理员绕过。无法正常满足审核条件时留可审PR并向用户报告，不能宣称合并完成。

目标是当前候选在声明范围内无已知未解决缺陷且规定验证通过，不是绝对无缺陷、全部项目完成或生产安全保证。
