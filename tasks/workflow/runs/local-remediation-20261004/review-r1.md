# 独立实施验收：B-remediation-integration-local-r3 / acceptance-r1

## 1. 结论

**NOT_ACCEPTED。** 本轮完整执行 67 项需求、其中 60 项独立运行义务。完整正式套件通过；新发现一项可稳定复现的正式负控调度问题 **BR-FINAL-P13-TIMEOUT-CONTROL（P2）**，当前不能满足“已知阻断清零”的合并条件。它导致正确 oracle 的测试假失败，并非错误结果被业务接受，也不是 oracle 假 PASS。应在当前阶段补正、停写冻结后交新 reviewer 完整复验。

完整项目仍 **PARTIAL**。A2.2 公开 invoke 与最终动态结果查询、A2.3 持续回执签发发布、A3 独立锚定/导出/三代理四工具公开采购闭环和 50 客户端/10,000 调用规模对照实验未实现/未验收；本轮不将 SDK、AS TLS、进程内四工具执行当作这些交付。

## 2. 身份、授权、冻结及只读边界

Reviewer 为全新 `/root/acceptance_r1`，review_kind 为 IMPLEMENTATION_ACCEPTANCE，非包审或实施者；无派生代理。请求模型 `gpt-6-astra/high`，有效后台模型/档位 **UNKNOWN**，依据已批准 runtime addendum 采用本轮人工与工具证据门。未伪造旧 workflow_gate、运行元数据或云端回执。

仓库 `/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`；分支 `handoff/b-integration-20261003`；HEAD `2051b402c99a3d400d8f12749287075e23a9a521`；main 比较基线 `153f14e9be180a1eb26b0f0e0898048d45170569`。本轮用户授权由父任务可见真人消息、authorization.json 和批准适配交叉核对，允许修补/完整复核/满足正常保护后合并，不允许绕过检查或后段开发。

本 reviewer 的 `verify_freeze.py` 独立重算 controller 清单的全部 **241 项**（240 个现有文件及一个删除项），包括 tracked/untracked/deleted、SHA256/mode、Git status、HEAD/branch、index、staged/unstaged binary diff。首尾 `start.json` / `end.json` 完全一致，清单摘要 `4f757cd9f3742d50a9f14844977a70aa933449ed7e9964d3d9c2988601b092e5`。没有仅用 HEAD 代替候选。native `collaboration.list_agents` 独立观察实施者 completed 且明确停写，文档包 reviewer completed；父任务明确保持控制文件冻结。

唯一写区为本报告目录 `artifacts/workflow/local-remediation-20261004/acceptance-r1/` 与本 reviewer 自有容器。原仓库在容器中只读挂载。没有改正式源码/测试/SQL/依赖/任务/状态/历史报告/其他 worker 或 controller 证据，没有 Git 写入、PR、合并或保护变更。

## 3. 审查范围与调用链

阅读 AGENT/AGENTS、README/HANDOFF、四设计文档、原 A2 全任务、A1 最终验收、A2 检查点、A2.1 acceptance/r8 与历史失败/补正语义、原 workflow 实施/审查契约及模板、Codex 补充契约、本轮 v1/v2/runtime/authorization/requirements/包审/实施/补正文档/state/issues 与 local-quality 报告。旧 PASS 只用于确认要求和触发条件，不替代独立执行。

实际追踪和核对：

- `InvocationVerifier.verify_bundle → PermissionSnapshotProvider.load → EvidenceStore.stage → VerifiedExecution.accept → ExecutionService.accept_invocation → ExecutionLedger.accept_bound`：完整真实签名祖先投影，参数先校验；candidate 使用原成本/快照，最终锁后动态授权、proof 登记、实际 EXISTING validator 与 evidence link 同事务；最终 deferred work 后再取 DB clock。
- A1 保留默认 `accept/accept_checked`。接受锁序 principals→task→root-to-leaf grants；执行 claim/terminal 锁序 task→grants→operation→lease。未知效果保预算；owner/version/state/锁后 expiry 同时约束；不通过当前报价重新构造旧意图。历史短事件封存、七旧表、proof/operation/event/outbox 不可变保护保持。
- `parse_result/bind_result → ExecutionService._decide → _finalize` 及 `project_receipt` 调用方：read 成功形状只允许两种 read 工具；order/notification 的错误 read 形状在 execute/query 均保持 UNKNOWN，无终局/outbox，随后合法结果恢复唯一效果。refusal 的四工具语义与所有字段/报价/effect 绑定保留。
- `MAX_ORDER_ITEMS=256` 同时约束请求、持久快照和结果，参数拒绝先于 proof/operation/预算/事件新增；没有扩张持久读取上限。完整 256 生命周期和 257/1000 零新增断言实跑。
- 离线 receipt 使用独立 AS、GW、三个 holder 密钥，验完真实签名后检查完整 grant-ID 全局唯一和账本位置/摘要。root→middle→root 确实通过相邻链检查，触发新全局重复检查；合法三层通过。future-token 已修改并重签目标 token 的 iat/nbf，proof +5 合法/+6 拒绝与共同历史窗口保持。
- AS code/delegation/consent 的最终时刻检查、根永久唯一、幂等重试不复活撤销/key、统一 principal 锁；HTTP 原始请求边界、真实 TLS/CA 与 did:web 禁 redirect/批准主机/用途/SPKI；私有文件 descriptor/owner/mode/祖先/竞态/FIFO/独占创建；安装 SQL/lineage 原子升级与固定 blob 来源。

没有声称对所有未来攻击或整个 2.3 万行新增实现作形式化证明。具体当前源码函数/行号、测试函数/参数节点、实际 assert/raises 与调用的辅助断言见 `requirements-matrix.json` 和 `assertion-catalog.json`。

## 4. 环境、来源与执行说明

新建独占 owner `acceptance-r1-20261004` 的 Linux amd64 Python 容器和 PostgreSQL16 实例/网络，UID501 下普通 venv 安装与执行，非 root/--target。Python **3.11.17**；PG **16.15**（自有 arm64 Alpine）；OpenSSL CLI **3.5.7**；tongsuopy **1.0.1**，其真实 backend banner **OpenSSL 1.1.1h 22 Sep 2020**。锁版本和全部 distribution/license/direct_url 元数据见 `wheel-final-provenance.log`。

完整源码使用从冻结 240 文件精确复制的自有 candidate，避免迁移测试 import-time 写 subset 触及原仓库。最终 wheel 从另一份精确干净输入用 PEP517 build isolation、固定 `setuptools==80.9.0` 构建，普通非 editable 安装；83 个成员逐一与候选源码/SQL核对。测试副本位于 `/review/wheel-tests`，无 src、无可用 editable hook，主命令 PYTHONPATH 空；原正式 worker fixture 会给子进程设置不存在的 `/review/wheel-tests/src`，该路径未创建、无可加载代码，实测每个子进程仍从 wheel 导入。主进程及真实 subprocess 的实际 agent_guard origins、安装 share SQL 目录和文件摘要被独立记录。自有 sitecustomize 只记录 import 来源，不改业务模块；真实 SIGKILL 子进程的启动来源也先落盘，不依赖 atexit。

网关和下游为不同数据库/连接/事务域。普通部署 DSN 清空，仅自有 TEST DSN；NOLOGIN 非特权 br_s1_untrusted 以及 ADMIN=false/INHERIT=false/SET=true membership 实查。原三容器仅做 inventory，未连接业务库。缺 TEST DSN 的独立负控确实 exit1 / ERROR，不 skip。

以下均为本 reviewer 独立执行，非 worker 的 2340 项日志转述。计数取实际 JUnit 收集，未硬编码为门槛。每个命令的 argv（脱敏）、exit、用时、原始脱敏日志/XML 与 hash 均在证据索引。

| 本轮独立运行 | PASS / FAIL / ERROR / SKIP | Exit | 原证据 |
| --- | --- | --- | --- |
| source-final-nonintegration | 952 / 0 / 0 / 0 | 0 | [source-final-nonintegration.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/source-final-nonintegration.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/source-final-nonintegration.xml) |
| source-final-integration | 1388 / 0 / 0 / 0 | 0 | [source-final-integration.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/source-final-integration.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/source-final-integration.xml) |
| wheel-final-nonintegration | 952 / 0 / 0 / 0 | 0 | [wheel-final-nonintegration.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-final-nonintegration.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-final-nonintegration.xml) |
| wheel-final-integration | 1388 / 0 / 0 / 0 | 0 | [wheel-final-integration.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-final-integration.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-final-integration.xml) |
| a1-current-unit | 70 / 0 / 0 / 0 | 0 | [a1-current-unit.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/a1-current-unit.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/a1-current-unit.xml) |
| a1-current-pg | 87 / 0 / 0 / 0 | 0 | [a1-current-pg.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/a1-current-pg.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/a1-current-pg.xml) |
| a1-original-ag_review_probe | 4 / 0 / 0 / 0 | 0 | [a1-original-ag_review_probe.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/a1-original-ag_review_probe.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/a1-original-ag_review_probe.xml) |
| a1-original-ag_review_f2 | 1 / 0 / 0 / 0 | 0 | [a1-original-ag_review_f2.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/a1-original-ag_review_f2.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/a1-original-ag_review_f2.xml) |
| a1-original-ag_review_upgrade | 0 / 1 / 0 / 0 | 1 | [a1-original-ag_review_upgrade.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/a1-original-ag_review_upgrade.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/a1-original-ag_review_upgrade.xml) |
| a1-upgrade-equivalent | 1 / 0 / 0 / 0 | 0 | [a1-upgrade-equivalent.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/a1-upgrade-equivalent.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/a1-upgrade-equivalent.xml) |
| historical-a2-original | 482 / 0 / 0 / 0 | 0 | [historical-a2-original.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/historical-a2-original.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/historical-a2-original.xml) |
| historical-b-original | 221 / 25 / 4 / 0 | 1 | [historical-b-original.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/historical-b-original.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/historical-b-original.xml) |
| historical-b-equivalent | 250 / 0 / 0 / 0 | 0 | [historical-b-equivalent.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/historical-b-equivalent.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/historical-b-equivalent.xml) |
| source-local-boundary-original | 7 / 0 / 0 / 0 | 0 | [source-local-boundary-original.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/source-local-boundary-original.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/source-local-boundary-original.xml) |
| wheel-local-boundary-original | 7 / 0 / 0 / 0 | 0 | [wheel-local-boundary-original.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-local-boundary-original.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-local-boundary-original.xml) |
| source-independent-compound | 2 / 0 / 0 / 0 | 0 | [source-independent-compound.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/source-independent-compound.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/source-independent-compound.xml) |
| wheel-final-independent-corrected | 22 / 0 / 0 / 0 | 0 | [wheel-final-independent-corrected.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-final-independent-corrected.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-final-independent-corrected.xml) |
| wheel-process-witness | 2 / 0 / 0 / 0 | 0 | [wheel-process-witness.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-process-witness.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-process-witness.xml) |
| wheel-db-witness-isolated | 12 / 0 / 0 / 0 | 0 | [wheel-db-witness-isolated.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-db-witness-isolated.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-db-witness-isolated.xml) |
| wheel-http-db-witness | 30 / 0 / 0 / 0 | 0 | [wheel-http-db-witness.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-http-db-witness.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/wheel-http-db-witness.xml) |
| clean-docs | 2 / 0 / 0 / 0 | 0 | [clean-docs.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/clean-docs.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/clean-docs.xml) |
| missing-test-dsn-negative | 0 / 0 / 1 / 0 | 1 | [missing-test-dsn-negative.log](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/missing-test-dsn-negative.log) / [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/missing-test-dsn-negative.xml) |

Ruff check/format（148文件）、首尾diff-check、fresh locks/pip check、源码和最终wheel README两初始化流程及demo均exit0；实际argv/环境/用时/hash见各同名command.json与索引。原验收A1的68/78不是固定门，当前明确分跑70/87，全部原语义和原4+1探针保留。所有参数节点不按旧计数删减。

## 5. 完整67项矩阵

**64 PASS / 3 FAIL / 0 BLOCKED；60项运行义务全部独立执行。** 三项FAIL均关联唯一新问题BR-FINAL-P13-TIMEOUT-CONTROL。下表完整保留需求语义；JSON提供每个具体函数及所有参数化节点/实际assert/raises、辅助断言索引、源码SHA、命令exit、日志/XML/SHA，未以文件名代替实际断言。每项PASS仅限本轮声明范围。

| ID | 必须验证的行为 | 本轮依据 | 结论 |
| --- | --- | --- | --- |
| A2-P01 | 三层订单70000/1成功，唯一真实下游效果；根/中间/叶reserved归0，settled70000/1；RESERVE和SETTLE各一，终态/outbox一致 | test_p01_three_layer_order_settles_once | PASS |
| A2-P02 | 下游持久终局拒绝，FAILED、全路径释放不结算，RELEASE一条；该键不能迟到成功 | test_p14_refused_key_can_never_produce_an_effect_later；test_p02_persisted_refusal_releases_and_blocks_late_success | PASS |
| A2-P03 | 读取/通知金额0但次数预留结算或释放正确；通知持久效果最多一次，读结果固定 | test_p03_zero_amount_read_settles_calls；test_p03_zero_amount_failure_releases_calls；共3函数，完整节点/断言见JSON | PASS |
| A2-P04 | 接受提交前不得执行；提交后真独立子进程终止/重新启动，从持久状态恢复而非finally补救；保留pid/同步与DB断言证据 | test_p04_accept_alone_never_touches_the_downstream；test_p04_rejected_accept_leaves_no_operation_and_no_effect；共4函数，完整节点/断言见JSON | PASS |
| A2-P05 | 下游订单已提交响应丢失→UNKNOWN额度保留；同键恢复唯一订单、一次结算 | test_p05_response_lost_keeps_budget_then_settles_same_order | PASS |
| A2-P06 | 下游成功、网关终局前崩溃；恢复无重复效果/账本/终局 | test_p06_recovery_after_terminal_window_has_no_duplicate_effect；test_p04_p06_real_process_killed_in_crash_window_then_restarted | PASS |
| A2-P07 | 终局事务节点/事件/outbox中途注入异常；全状态/计数/事件/outbox原子回滚，之后可恢复 | test_p07_terminal_transaction_rolls_back_completely | PASS |
| A2-P08 | 查无结果后旧请求迟到成功；不释放，最终唯一效果和SETTLE | test_p08_query_none_does_not_release_then_late_success_settles | PASS |
| A2-P09 | 双恢复者、过期旧worker竞争，独立连接barrier/event每组10轮；终态不被覆盖、一个终局/一个outbox | test_p09_two_recoverers_race_one_terminal_and_one_outbox；test_p09_expired_old_worker_cannot_overwrite_the_new_terminal；共33函数，完整节点/断言见JSON | PASS |
| A2-P10 | 接受后祖先撤销/过期/key停用，内部恢复可完成原意图；外部接受重试仍拒绝；真实授权查询后段保留BLOCKED | test_p10_internal_recovery_completes_after_revocation；test_p10_external_retry_rejected_after_revocation；共6函数，完整节点/断言见JSON | PASS |
| A2-P11 | 当前报价改/删后的已有意图使用原成本/快照；新键要求有效报价；确定性miss→另accept→报价消失→安全重查命中；变grant/holder/参数、撤销、proof重放仍拒绝 | test_p11_existing_intent_survives_quote_edit_and_delete；test_p11_new_key_requires_a_valid_current_quote；共24函数，完整节点/断言见JSON | PASS |
| A2-P12 | 下游金额/意图/完整快照错配且可能有效果→UNKNOWN保留预算，无伪成功/释放 | test_p12_amount_mismatch_keeps_budget_and_never_settles；test_p12_intent_mismatch_keeps_budget；共55函数，完整节点/断言见JSON | PASS |
| A2-P13 | 根/中间不足或次数耗尽及接受/结算/恢复并发，10轮、全祖先不超限不负数、不反向锁/死锁无界 | test_p13_two_draws_race_for_the_root_budget；test_p13_intermediate_ancestor_budget_binds_under_concurrency；共9函数，完整节点/断言见JSON | PASS |
| A2-P14 | 下游同键同意图和冲突、订单/通知均防重复，执行/查询无或错独立服务凭据拒绝、零泄漏/效果；不能只藏端口 | test_p14_same_key_same_intent_replays_one_order；test_p14_notification_and_read_are_idempotent_too；共9函数，完整节点/断言见JSON | PASS |
| A2-P15-CORE | 四个完整工具ID/版本，重复JSON键/SKU、bool/负/浮点/溢出数量、缺/空集合、scope不足、跨租户/关联错/URL路径注入、快照/祖先包含错等分层负例，零预留/效果。可信fixture授权不是真实验签 | test_read_shaped_nonread_outcome_stays_unknown_then_recovers；test_item_bound_is_enforced_before_accept_and_full_256_recovers；共47函数，完整节点/断言见JSON | PASS |
| A2-P19 | 001及003真实非零预留/撤销/证据升级到004，七旧表全行及完整迁移登记在非法升级时不变；合法重复迁移no-op；旧材料不足sidecar隔离保预算，不能补当前报价执行 | test_p19_upgrade_from_001_preserves_nonzero_seven_tables；test_p19_upgrade_from_003_preserves_nonzero_seven_tables；共28函数，完整节点/断言见JSON | PASS |
| A2-P20 | 直接SQL改意图/成本/证据、删除重建路径/操作、改删事件/节点、阶段seq绕过、非法状态/双终局拒绝，旧账本不变；合法预算/撤销/状态UPDATE可用 | test_p19_upgrade_from_001_preserves_nonzero_seven_tables；test_p19_upgrade_from_003_preserves_nonzero_seven_tables；共45函数，完整节点/断言见JSON | PASS |
| A2-CKPT1-OBL01 | 候选前schema/静态授权/可信集合，不要求当前报价存在；命中原快照关联+当前权限后仍A1 accept锁后复核/proof/意图 | test_real_owned_downstream_lock_has_deadline；test_precommit_interruption_and_real_worker_have_zero_effect；共157函数，完整节点/断言见JSON | PASS |
| A2-CKPT1-OBL02 | 确定性P11安全重查，包括任意资源/报价解析失败，而非仅金额错误；新键及失效/重放/变意图负例 | test_real_owned_downstream_lock_has_deadline；test_precommit_interruption_and_real_worker_have_zero_effect；共157函数，完整节点/断言见JSON | PASS |
| A2-CKPT1-OBL03 | 可用候选完整持久接受事实；永久不可改删事件+非级联FK或明确DELETE保护防删操作，异常旧行隔离；P20不能靠doc承诺 | test_real_owned_downstream_lock_has_deadline；test_precommit_interruption_and_real_worker_have_zero_effect；共157函数，完整节点/断言见JSON | PASS |
| A2-CKPT1-OBL04 | claim/终局owner+version+合法state+锁后DB有效expiry；无新owner时旧worker过期也拒绝；UNKNOWN保持且不释放未知预算 | test_real_owned_downstream_lock_has_deadline；test_precommit_interruption_and_real_worker_have_zero_effect；共157函数，完整节点/断言见JSON | PASS |
| A2-CKPT1-OBL05 | sidecar不改七旧表、phase/seq CHECK、事件/节点UPDATE/DELETE保护、非法升级全数据和迁移登记保全，合法更新/测试自有清理兼容 | test_real_owned_downstream_lock_has_deadline；test_precommit_interruption_and_real_worker_have_zero_effect；共157函数，完整节点/断言见JSON | PASS |
| A2-CKPT1-OBL06 | 下游执行/查询完整原快照持久化比对；不一致UNKNOWN；不可变outbox、receipt_id/created_at稳定、UTC整数秒iat；缺B PENDING且无伪编码/SM3 | test_real_owned_downstream_lock_has_deadline；test_precommit_interruption_and_real_worker_have_zero_effect；共157函数，完整节点/断言见JSON | PASS |
| WF-A1-REGRESSION | A1原全部unit/PG集成独立实跑并保留U1/P1—14/F1—5语义与根重建、非零升级断言；不硬编码旧测试计数 | test_upgrade_preserves_nonzero_reservation_and_all_evidence；test_subject_must_match_database_grant；共97函数，完整节点/断言见JSON | PASS |
| WF-INDEPENDENT-PROBES | 最终reviewer独立设计绕过/边界探针，保存本轮可复现源与实跑日志；worker不替reviewer选择唯一反例 | test_maximum_width_zero_price_order_does_not_accept_read_shape；test_real_pg_serialization_retries_and_atomicity | PASS |
| WF-QUALITY-CHECKS | ruff check/format、diff、全unit/骨架/docs/PG实跑；新增目录显式纳入CI；缺库报错不skip | test_local_markdown_links_resolve；test_fenced_json_examples_parse；共8函数，完整节点/断言见JSON | FAIL |
| WF-PY311-ENV | 实际Python3.11、依赖安装/约束和真实PG验证；历史CI/本机3.14不能替代。本轮无授权触发远程CI，NOT_RUN不额外阻断但Python3.11本地必须验证 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。 | test_tls_server_runs_the_full_as_flow；test_sm2_signatures_interoperate_in_both_directions；共4函数，完整节点/断言见JSON | PASS |
| WF-RESOURCE-ISOLATION | worker及reviewer各自独立project/唯一容器/DB/schema，记录归属label、来源、挂载/端口、普通DSN清除、安全目标；前后无关资源不变，清理仅owned | test_wrong_target_maintenance_database_is_refused；test_wrong_target_unnamed_database_is_refused；共7函数，完整节点/断言见JSON | PASS |
| WF-IMMUTABLE-BASELINE | 检查001—003内容checksum、A1语义、合法更新、无B代码/依赖偷渡。必要接口兼容须主控确认 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。 | 静态/控制逐项核验：import-provenance.json,start.json | PASS |
| WF-DOCS-REPORT | 报告tracked/untracked误措辞纠正，31ID→具体断言/函数/命令结果，README可复现初始化/worker/下游/测试/清理；真实网关缺B不可装配启动，CI不漏新测试 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。 | 静态/控制逐项核验：docs-goal-map.json,all-doc-links.json,clean-docs.xml,wheel-final-readme-observations.json | PASS |
| WF-SNAPSHOT-COVERAGE | 主控/reviewer查完整tracked/untracked/deleted及契约SHA256，冻结开始/结束一致；无active writer才review，证据与报告指纹绑定 | 静态/控制逐项核验：start.json,end.json,native-stop-observation.json,copy-binding.json | PASS |
| B-01-CRYPTO | 成熟SM2/SM3、ALG/typ/rawJWS/userID/DER-rs严格；标准向量及OpenSSL双向实跑，不改PKCE S256 | test_sm2_signatures_interoperate_in_both_directions；test_openssl_jws_segment_verifies_through_b_verifier；共20函数，完整节点/断言见JSON | PASS |
| B-02-ENCODING | 全原JSON/Unicode/类型/大小深度/词数边界及raw/JWS/DID/SDK入口，合法负delta仅明确字段；原两issue正式独立闭环 | test_actual_negative_entry；test_legal_depth_boundary；共42函数，完整节点/断言见JSON | PASS |
| B-03-IDENTITY | 默认did:web实际HTTPS/CA/目的/controller/SPKI/企业注册/拒redirect与未批准目标；不是全部仅注入字典 | test_real_https_route_refusals_preserve_rows_then_succeed；test_verified_tls_exact_transport_boundary_and_get_routes；共22函数，完整节点/断言见JSON | PASS |
| B-04-TOKEN-POLICY | 根/两级子各维收窄、空/缺约束拒、完整AS快照与A权限链真实绑定 | test_signed_chain_all_four_tools_and_real_receipt；test_projection_rejects_read_shaped_nonread_success；共29函数，完整节点/断言见JSON | PASS |
| B-05-INVOKE-PROOF | 原body/holder/endpoint/tenant/task/版本/业务键/proof拒绝，静态验证与最终接受分离，零新增状态 | test_signed_chain_all_four_tools_and_real_receipt；test_projection_rejects_read_shaped_nonread_success；共24函数，完整节点/断言见JSON | PASS |
| B-06-CODE-OIDC | 登录、state/nonce/redirect/S256/CSRF/cookie/code一次性；政策/TX/所有晚锁时效全部触发与变体 | test_policy_lock_final_expiry；test_login_csrf_lock_expiry；共36函数，完整节点/断言见JSON | PASS |
| B-07-ROOT-ISSUANCE | 同task永久唯一根，code消费/根/proof/签名快照同txn；双code10轮，原数据不清零 | test_code_is_one_use_and_signs_root_and_id_token；test_two_codes_for_one_task_cannot_create_two_roots；共5函数，完整节点/断言见JSON | PASS |
| B-08-DELEGATION | 父/接收者/完整链可信，签发不占预算；同key/失响应/真进程恢复，撤销/到期/key停用retry不复活 | test_same_delegation_key_real_wait；test_double_code_unique_root_real_wait；共17函数，完整节点/断言见JSON | PASS |
| B-09-DYNAMIC-STATE | AS/执行/撤销统一锁序、锁后DBclock、完整祖先/key；内省active非永久许可 | test_policy_lock_final_expiry；test_login_csrf_lock_expiry；共32函数，完整节点/断言见JSON | PASS |
| B-10-HTTP-TLS | 全路由格式/媒体/重复头与body/大小/超时/认证/角色/会话拒绝；固定HTTPS/真TLS/脱敏/无生产旁路 | test_real_services_reject_transport_before_effects_with_positive_control；test_real_malformed_and_unknown_fields_have_no_effects；共35函数，完整节点/断言见JSON | PASS |
| B-11-RESULT-READ | 真实专用query签验/精确DTO与权限投影；不伪invoke字段。A最终动态查询实现留A2.2且文档不可伪PASS | test_canonical_query_requires_subject_and_explicit_method；test_callback_only_verifier_cannot_enter_production_query_or_bundle；共8函数，完整节点/断言见JSON | PASS |
| B-12-EVIDENCE-RECEIPT | 受控原材料暂存/接受关联、独立AS/GW历史信任、真实规范投影/签验负例；持续outbox签发/导出留后段 | test_bound_accept_final_clock_after_every_wait；test_evidence_immutable_and_nonprivileged_role_refused；共24函数，完整节点/断言见JSON | PASS |
| B-13-ROTATION-INTEROP | AS/client/GW用途与生命周期、旧key历史验证及新调用停用；OpenSSL/源与非editable wheel真互验 | test_rotation_signs_with_new_kid_and_keeps_old_tokens_verifiable；test_rotation_without_historical_key_rejects_old_parent_token；共6函数，完整节点/断言见JSON | PASS |
| B-14-DB-FAILURES | 真实DB故障/锁timeout/终止backend/serialization失败关闭和原子回滚，错误不误标坏材料永久隔离 | test_real_pg_serialization_retries_and_atomicity；test_real_services_reject_transport_before_effects_with_positive_control；共20函数，完整节点/断言见JSON | PASS |
| B-15-CONCURRENCY-TEST-EFFICACY | 原全部竞争组各10轮，独立连接+可达同步、目标锁/PID/SQLSTATE/负控，不吞异常假PASS | test_policy_lock_final_expiry；test_login_csrf_lock_expiry；共12函数，完整节点/断言见JSON | FAIL |
| B-16-A1-REGRESSION | 全A1 U1/P1—14/F1—5与原5probe/等价更强升级，001—003历史checksum，原默认accept API | test_upgrade_preserves_nonzero_reservation_and_all_evidence；test_subject_must_match_database_grant；共97函数，完整节点/断言见JSON | PASS |
| B-17-B-SUITE-QUALITY | fresh3.11锁安装、完整source/wheel非集成SDK/PG/OpenSSL/TLS/demo/lint/format及全文测试效力/许可维护审读 | test_used_revoked_root_cannot_be_deleted_and_reinserted_with_same_id；test_subject_must_match_database_grant；共637函数，完整节点/断言见JSON | FAIL |
| B-18-RESOURCE-ISOLATION | 每worker/reviewer独占owner/容器/project/DB/schema/缓存，普通DSN清除、精确清理、原资源前后核对 | test_wrong_target_maintenance_database_is_refused；test_wrong_target_unnamed_database_is_refused；共7函数，完整节点/断言见JSON | PASS |
| B-19-CONTRACT-MERGE | freeze且实际实现invoke bundle/query/evidence/seq投影，调用方一致，原A2.1默认/checked路径不丢 | test_signed_chain_all_four_tools_and_real_receipt；test_projection_rejects_read_shaped_nonread_success；共13函数，完整节点/断言见JSON | PASS |
| B-20-MIGRATION-MERGE | 空库/common前缀/A-origin/B-origin合法升级、非零撤销证据、全部registry及失败原子性、重复no-op | test_public_a_view_rejects_b_legacy_before_bootstrap；test_completed_bundle_missing_evidence_namespace_refuses；共28函数，完整节点/断言见JSON | PASS |
| B-21-SHARED-FILE-MERGE | README/init/fixtures/conftest/deps/CI/migrate语义整合与完整manifest，不覆盖任何一侧功能 | test_public_a_view_rejects_b_legacy_before_bootstrap；test_completed_bundle_missing_evidence_namespace_refuses；共23函数，完整节点/断言见JSON | PASS |
| B-22-ORIGINAL-GOAL | 全M/SEC/CON/REC/AUD/E2E/ENG逐项真实等级/后段责任映射；不拿模块合并候选当比赛完成 | 静态/控制逐项核验：docs-goal-map.json,all-doc-links.json | PASS |
| B-23-HANDOFF-REPRODUCIBILITY | README/手册/升级/初始化/角色/key/合成demo可复现，准确当前版本/限制，不复制B旧main未实现文字 | test_tls_server_runs_the_full_as_flow | PASS |
| B-24-FINAL-BINDING | 完整candidate/契约起止snapshot、每批receipt/native停止与完整独立报告/issue闭环 | 静态/控制逐项核验：start.json,end.json,native-stop-observation.json,cleanup.json | PASS |
| BR-01-CONSENT-FINAL | policy晚锁跨request/session到期两类各10轮零code/event/approved；client key/DID耗时不漏最终期限；core，test_consent_final_decision.py | test_policy_lock_final_expiry；test_login_csrf_lock_expiry；共36函数，完整节点/断言见JSON | PASS |
| BR-02-HTTP-REJECTION | 全挂载路径65536/65537、分块/中断/格式/媒体拒绝4xx；DB503/真实内部500准确，无效果/原敏感材料不回显；http，test_http_request_limits.py+integrator真TLS | test_real_services_reject_transport_before_effects_with_positive_control；test_real_malformed_and_unknown_fields_have_no_effects；共35函数，完整节点/断言见JSON | PASS |
| BR-03-PRIVATE-PATHS | FIFO/socket/directory/file及parent link/危险祖先权限/竞态拒绝，独占不覆盖、多umask真实CLI，所有owned子进程退出；private+integrator | test_valid_read_modes_path_and_context；test_create_context_retains_handle_for_six_exclusive_writes；共48函数，完整节点/断言见JSON | PASS |
| BR-04-LINEAGE-HISTORY | A001—006/B004—009原字节与编号不变，原registry旧行全部字段含applied_at保全，sidecar来源可核验；core | test_public_a_view_rejects_b_legacy_before_bootstrap；test_completed_bundle_missing_evidence_namespace_refuses；共28函数，完整节点/断言见JSON | PASS |
| BR-05-LINEAGE-ATOMIC | 未知/错filename/checksum/缺中间/混合/伪登记/孤立schema失败前后全业务/legacy+sidecar registry不变，并发迁移/真实中断/重复升级；core+reviewer | test_public_a_view_rejects_b_legacy_before_bootstrap；test_completed_bundle_missing_evidence_namespace_refuses；共28函数，完整节点/断言见JSON | PASS |
| BR-06-REAL-PERMISSIONS | 真AS根→两级子→完整snapshot→现有四工具接受/执行；改token/path/scope/holder/SPKI/resources拒、各祖先账本/下游效果正确；core+integrator | test_signed_chain_all_four_tools_and_real_receipt；test_projection_rejects_read_shaped_nonread_success；共29函数，完整节点/断言见JSON | PASS |
| BR-07-QUERY-DTO | 单一subject/method/query字段，真实签验与完整权限/evidence绑定；无tool/key虚字段/不预留不执行，下游动态查询后段明确不计完成；core | test_canonical_query_requires_subject_and_explicit_method；test_callback_only_verifier_cannot_enter_production_query_or_bundle；共8函数，完整节点/断言见JSON | PASS |
| BR-08-EVIDENCE-BINDING | 可信暂存不可改删、raw/digest/ref/当前proof精确关联，接受同txn first/retry独立link，注入失败proof/计数/关联全回滚，旧opaque材料不补造；core | test_bound_accept_final_clock_after_every_wait；test_evidence_immutable_and_nonprivileged_role_refused；共24函数，完整节点/断言见JSON | PASS |
| BR-09-RECEIPT-PROJECTION | 真A outbox材料phase/seq/节点集合验证后投影唯一v1，B规范+真实签验向量；未知字段/错seq/重复/错delta拒；原ID/iat/PENDING材料不变；core | test_bound_accept_final_clock_after_every_wait；test_evidence_immutable_and_nonprivileged_role_refused；共24函数，完整节点/断言见JSON | PASS |
| BR-10-IMPORT-PROVENANCE | 精确import-map及固定B blob/当前A hash，不覆盖A ledger.service/001—006/全部旧测试或原报告，全部增删rename/mode列入manifest；core+controller | 静态/控制逐项核验：import-provenance.json,start.json,historical-copy-binding.json | PASS |
| BR-11-CLEAN-CANDIDATE | 整合后freshsource及非editable wheel、空/两legacy升级、全A/B套件、实际demo/TLS/README；CI配置显式包含所有新目录，远程未授权不触发；integrator+reviewer | test_p19_upgrade_from_001_preserves_nonzero_seven_tables；test_p19_upgrade_from_003_preserves_nonzero_seven_tables；共602函数，完整节点/断言见JSON | PASS |
| BR-12-WORKFLOW-BARRIER | 真人读回/所有包与实际plan版本、真实NEW模型ID/资源、每批双开工门/worker门/freeze和最终require-accepted门；结构检查不替代语义；controller+reviewer | 静态/控制逐项核验：native-stop-observation.json,start.json,end.json | PASS |

## 6. 新发现：BR-FINAL-P13-TIMEOUT-CONTROL

**P2，OPEN_CONFIRMED，阻断当前接受。** 位置：`tests/unit/test_execution_concurrency_oracle.py:70-71`，`_race([blocked, lambda: 2], timeout=0.05)` 后立即 `assert entered.is_set()`。`_race` 的 deadline 在 thread.start 前建立；调度器可以在这 50ms 内尚未运行 blocked 线程。此时 `_race` 正确抛出 `race workers timed out`，但该正式测试因 entered 尚未置位而失败。

本 reviewer 第一探针 `probe_oracle_scheduling.py` 把真实线程启动延后 200ms，原测试稳定在第71行失败。第二探针 `probe_oracle_scheduling_repeated.py` 让线程在清理 join 时才开始运行，10/10 记录同一个正式失败；同时记录 `_race` 精确异常 `race workers timed out`，所有 owned 线程均退出。它没有替换 `_race` 的结果或模拟业务错误，只控制启动调度并记录真实异常。源码、原命令/exit0（诊断成功）和逐轮 JSON 在 `oracle-scheduling-{probe,repeated}.log`；不能把诊断脚本 exit0 解释为正式测试通过。

影响是正式负控不确定、忙碌 CI/调度延迟下可假失败，也不能保证这一轮实际进入了预定“已经执行但阻塞”的分支。没有观察到 RuntimeError/无关 ExecutionError/缺完成被吞掉，没有观察到错结算或业务绕过。当前 P13 业务竞争各10轮及精确 LEASE_LOST oracle 均通过；原 BR-FINAL-P13-ORACLE 的产品测试收集漏洞已修，本条是新增负控确定性问题。

**最小补正要求：** 在既有授权的正式 oracle 测试文件内，使“worker 已进入阻塞体”成为明确事件同步事实，再验证有界执行超时；可将启动就绪和执行期限分别控制，或明确分别测试启动超时和执行超时。不要依赖将 50ms 任意调大；不要移除 timeout/缺完成/主线程异常/精确 LEASE_LOST 断言，不加 skip/xfail，不吞未预期异常。保留受控延迟启动正负两种调度，真实阻塞 worker、缺完成、RuntimeError、无关错误的负控与 bounded cleanup。验证应证明每次命中期望分支且所有线程退出，随后 fresh reviewer 对完整候选复验。

对应矩阵 FAIL：`WF-QUALITY-CHECKS`、`B-15-CONCURRENCY-TEST-EFFICACY`、`B-17-B-SUITE-QUALITY`。其余通过项只表达各自已执行要求，不抵消这一缺陷。

## 7. 历史原件、等价与缺陷闭环

历史原件完整绑定见 `historical-copy-binding.json` / `a1-original-copy-binding.json`。从原本地来源、controller 只读副本、reviewer 原副本逐字 hash 核对；自有适配仅改 `historical-adapted/`，完整差异在 `historical-adaptations.diff`，未修改任何正式或原始测试。

| 原件/问题 | 本轮原实跑与等价处理 | 本轮结论 |
| --- | --- | --- |
| A1 四不变量、根同 ID 删除重建 | 原要求独占 DB 原件 4+1 PASS；主体、一次调用、唯一根、根映射和已用撤销根不能重建断言保留 | 关闭证据保持 |
| A1 非零升级 | 原件 FAIL：旧仅002预期，当前实际002—006。适配仅新独占 DB 名和完整精确后缀；非零70000/1及七表全行比较不变，1 PASS；正式迁移另验全部registry/noop/非法原子性 | 等价充分；原失败保留 |
| A2 原本地 r8 探针 | 16文件、482参数节点原件全 PASS，无适配。包括真实进程/锁、报价竞态、旧材料隔离、反序锁负控、合法 list 与坏 typed shape、SQL封存等 | 历史安全义务本轮重跑 |
| B 原件250节点 | 221 PASS/25 FAIL/4 ERROR；其中20二次 principal 锁 Barrier 冲突、2旧9版本期待、2旧异常类期待、5硬编码旧DB；均原样留日志/XML | 未把原失败当产品失败或抹去 |
| B 两竞争组20节点 | 每 backend 只在首次 principal 锁前 Barrier；后续锁复核仍调用真实锁函数；保留两个独立PID实际 Lock 等待、全部根/委托/proof/预算断言、各10轮 | 适配全250 PASS；`logs/races-lock-observations.jsonl` |
| B 迁移/私有文件/旧DB | 期待精确 A 兼容 base+1..006；完整旧登记含applied_at、七表、非法/noop断言不变。私有覆盖拒绝改精确 ConfigError 且 cause=FileExistsError、原字节不变；仅自有 DB 名更换 | 等价充分，无删case |
| 上轮 local-quality 原7边界 | 原文件逐字绑定，自有副本在源码和最终 wheel 各7 PASS | 三个原失败触发已修 |
| A21-R1-OUTCOME / BR-FINAL-ITEM-LIMIT | 新正式参数节点及自选零价/最大数量/最长SKU复合探针：read伪变体保所有祖先预留、256唯一恢复、257/1000接受前零新增 | 本轮 CLOSED_REVIEWED |
| BR-FINAL-RECEIPT-DUPLICATE | 独立真实 AS/GW/三holder签名、合法三层、非相邻重复及重复ledger/错序/缺祖先/摘要错；非坏签名蒙混结构 | 本轮 CLOSED_REVIEWED |
| BR-FINAL-P13-ORACLE | 捕获所有 worker BaseException、有界join、结果完整性；RuntimeError/无关错/缺完成/精确LEASE_LOST负控，真实PG各10轮 | 原问题本轮修复；新增 TIMEOUT-CONTROL 未关闭 |
| BR-FINAL-RECEIPT-TEST-BRANCH | 已签leaf iat=nbf=base+1、proof/receipt=base 明确断言；13窗口参数节点与真实延迟恢复均通过 | 本轮 CLOSED_REVIEWED |
| LOCAL-DOC-CLEAN-CHECKOUT | 冻结240文件交付副本不带 ignored artifacts，正式docs2 PASS；9路径91链接/5 JSON块和30目标函数真实存在，删除旧setup可由Git追溯 | 本轮 CLOSED_REVIEWED |
| 历史 LOCK/LEGACY/NOTIFY/CHAIN/LOG/BOUNDS/EVENT/CANDIDATE/SNAPSHOT/UNKNOWN/TESTSYNC | 原482探针、全部正式回归和源/wheel全套重新执行；函数、具体断言/节点及日志在矩阵，不仅承接旧PASS | 当前声明行为保持 |
| 历史 P11 未知 LedgerError | 当前确定性错码/时序/DBclock窗口及全部原482重跑通过；旧一次没有code/cause的根因仍不可追溯 | 只关闭当前可验证义务；不伪称由TTL解释 |

缺失云端最后反例原源码/XML仍未找到，未冒充找回。按批准适配从原要求/失败报告重建五边界，独立验证具体触发/断言与正负控制；旧过严 tuple/list 两失败原件也未找到，提供的 r8 原件已经是合法 list 控制，实际 execute/query 均 SETTLE，坏 typed shape 均 UNKNOWN。本轮并未伪造旧失败记录。当前必需行为已有等价或更强证据，不因原文件缺失删除义务。

## 8. 自选探针、真实等级与 harness 失败

自选 `test_maximum_width_zero_price_order_does_not_accept_read_shape` 组合了256个128字节SKU、每项最大安全整数数量、零单价，execute/query 两种已持久效果场景。错误 read 形状保持 UNKNOWN/三祖先一次调用预留，恢复后唯一订单/唯一SETTLE/outbox；再以同业务键257项验证接受前INVALID_PARAMS且全计数不变。源码与wheel实跑各2 PASS。

另自建 `test_real_pg_serialization_retries_and_atomicity`，真实 SERIALIZABLE 连接读哨兵后由第二连接提交更新，原连接更新得到真实 SQLSTATE40001；并非手工 raise。一次冲突成功重试和连续三次耗尽回滚各10轮：独立backend、原接受/evidence/proof/全祖先快照不变、无隔离flag；合法重试只有一个新proof/link/operation并最终SUCCEEDED。实际55P03、57P01、HTTP503/500、SIGKILL/重启、迁移真进程死亡及10轮互斥另有 raw witness。

明确区分：下游响应丢失、无结果、恶意结果及部分写异常是 port/callback 注入，落地效果/预算/事务断言用真实PG；没有声称做了真实网络断连。TLS/HTTP/did:web、独立进程 SIGKILL、PG锁timeout/backend终止及40001是真的。持续签发/锚定/E2E/规模实验和远端CI NOT_RUN，前者不属本段，后者由主控正常Git阶段处理，不拿尚缺GitHub审核阻断本地产品验收。

以下 reviewer 自建环境/诊断问题全部保留，不归为产品缺陷：

1. 初次 role+CREATE DATABASE 合并到同一 psql 命令导致事务错误；保留失败，分开执行成功后才正式测试。
2. 首轮 no-build-isolation 用到 setuptools79.0.1，源码和wheel各952+1388虽通过，不替代锁80.9证据。最终改PEP517隔离、干净输入普通安装；源码和wheel完整全套全部重跑，以上表为最终依据。
3. 自选40001探针首版错误期待 ag_proofs 全库仅1条，忽略真实AS签发/两级交换已有3条；20 FAIL/2 PASS原日志保留。修正自有断言为原基线+1且精确当前proof_jti一条，保留完整耗尽回滚对比，最终22 PASS，差异在 `serialization-harness-correction.diff`。
4. 同时跑 final wheel 和额外 evidence 可读见证时误用同一 DB、不同schema。正式用例固定 advisory key82716291是DB级，导致真实等待互扰，目标SQL未到预期锁及过期窗口。原 full部分运行91 FAIL/378 PASS和额外89 FAIL/12 PASS均保留exit2中止记录；仅SIGINT自己已确认PID4957/5761。独立两schema同DB探针实证该key互阻55P03；修正后 full wheel使用独占wheel_isolated，额外见证使用wheel_witness，最终完整1388及另库12全部通过，非局部重跑替代。
5. 首版来源审计过严地拒绝任何字符串以/src结尾。实际正式worker fixture只添加不存在的wheel-tests/src；无源码目录，所有真实origin始终安装wheel。保留审计失败和修正diff，改为核对不存在及实际每PID来源，655个副本文件绑定和45个观测subprocess均通过；没有放过可用源码shadow。
6. 一次宿主进程清单诊断意外显示自建临时测试DSN；持久命令/日志的密码均脱敏，未接触部署凭据，已销毁对应容器。此为reviewer操作偏差，不能写成产品泄密发现或声称从未发生。

## 9. 文档、供应链及局限

95条原B import-map项目逐一核固定commit/blob/hash，A001—006与main、B004—009与固定B commit原字节一致；34个原A测试文件的既有test函数全部保留。完整manifest包含全部增删/mode，B新增绑定接口而未覆盖A默认API。installed share 的14SQL内容与候选一致，实跑空库、common/A/B每个前缀、非零业务/撤销/证据、no-op及非法登记/结构失败原子性。

`docs-goal-map.json` 保留30个原目标、对应具体函数和实际断言，不将本段SELF_CHECK/已复验映射提升为整个比赛目标PASS。本文的正式结论由主控关联到本轮state；冻结文档继续保留“实施交付时待复验”表述是准确历史上下文，不要求reviewer越权改state。

依赖元数据/许可和真实库版本已核。setuptools上游关于macOS sdist排除规则Unicode规范化的已知风险依然适用；本轮仅明确Linux干净输入wheel受测范围，未构建或发布sdist，不声称通用修复或零漏洞。见[维护者公告](https://github.com/pypa/setuptools/security/advisories/GHSA-h35f-9h28-mq5c)。tongsuopy1.0.1的发布/许可元数据不能证明完整维护与安全回补，旧backend banner如实保留，见[项目发布元数据](https://pypi.org/project/tongsuopy/)。这不是全面依赖漏洞审计。

## 10. 清理、证据入口与交主控

自有Python容器 `04ad35695a23449d5a349f68c58b9e3022f8a4b1f15c2d5205a8b824839a0a30`、PG容器 `1a1190869afa4bb8b21409be45cfddeaf779b33e0a111905b08d455513988e52` 和网络 `d2214d2707debf1168c04631b87fc3725a49a766a5f08645f81d346fbe35ee89`，在确认测试进程退出、完整ID/owner/网络成员后精确删除，owned剩余0。临时DB随自有tmpfs PG销毁。原三个容器ID/labels/运行状态保持；只做inventory，不声称比较其业务数据。

本目录入口：[67行完整矩阵](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/requirements-matrix.json)、[实际断言目录](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/assertion-catalog.json)、[证据索引](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/evidence-index.json)、[起始绑定](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/start.json)、[结束绑定](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/end.json)、[清理记录](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/acceptance-r1/cleanup.json)。矩阵每运行行含具体测试函数/行号/参数化节点/实际assert与raises、源码SHA、命令exit及日志/XML/SHA；静态七行有完整控制/来源/文档核验。补充脚本、原失败、修正diff、环境和来源日志都在索引，未用成功摘要替代原证据。

交主控：原样保存本完整报告，当前继续 **NOT_ACCEPTED**；按证据关闭已修五边界与docs问题，新增并补正BR-FINAL-P13-TIMEOUT-CONTROL，保留操作偏差和历史原失败，不把包审/全绿正式套件作为放行。完成补正后停写、完整冻结、另开fresh reviewer；本 reviewer完成索引最终读回后停止写入。未Git写、未进入后段、未宣称已合并。
