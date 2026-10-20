# 独立审查：PACKAGE_REVIEW / A2.2-integration / 第1轮

## 1. 结论与范围

- 日期：2026-10-04T08:52:55.539512+08:00，Asia/Shanghai。
- 结论：**PACKAGE_READY**。无阻断修改项；不构成行为PASS或阶段ACCEPTED。
- 对象：[task-v1.md](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/tasks/workflow/runs/A2.2-integration-20261004/task-v1.md)、完整requirements-v1、authorization、runtime提案、baseline-manifest和state，绑定本轮256项冻结清单。
- 本轮仅A2.2公开invoke与最终动态result-read；既有A1/A2.1/B回归保持。95需求/88独立运行义务与state严格一一对应，继承67/60无ID或运行旗标删除，A2-P10将查询从后段明确提升为本段必测。
- 项目仍PARTIAL。A2-P18持续回执签名/发布、完整P21含真回执、A3锚定/导出/完整演示/规模实验和部署不在本段；回执保持PENDING、receipt_jws=null。不允许自动进入下一阶段。
- 本轮未修改受审包、源码、正式测试、正式报告或台账；未commit/push/PR/合并/改保护；未调其他agent；未运行业务测试、启动业务服务或创建业务资源。

## 2. 独立会话、授权与冻结

| 项目 | 独立核对结果 |
| --- | --- |
| Reviewer Task | fresh `/root/a22_package_r1`；角色请求gpt-6.1-sol/xhigh；有效后台模型/档位UNKNOWN，不以请求或自述当证明 |
| 仓库 | `/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff` |
| 分支 / HEAD | `codex/a2.2-integration` / `280022e9d7005daa8d551ba0e4c52e3228e3add5` |
| 真人授权 | authorization记录当前用户执行continue-prompt代码块，仅推进A2.2；异步批准“批准 A2.2 本轮有限适配”。主控在当前会话核真人消息；本子会话核记录与明确派发依据，未获得message_id，未编造消息或授权 |
| 适用约定 | AGENTS/AGENT、current-policy、implementation/review-contract、review模板、原补充契约及本轮获批有限适配；旧机器门不被伪修改或冒用 |
| Writer冻结 | 主控明确确认256条冻结保存后产品/包无写入；两次实际hash、mode、Git全inventory独立核对一致 |
| Git差异 | staged/unstaged产品diff为空；仅6个本轮包文件untracked，无删除/重命名；HEAD保留280022e文档提交 |
| 基线清单 | 250条baseline内容/mode逐条匹配，29精确允许路径与task Markdown集合相同且无重复 |
| 全包冻结清单 | 256条，等于全部tracked+非忽略untracked；无缺项。freeze文件SHA `163872bfc9f2d68f0a47d2b838cb123b2e3ecfdc9de0e77fd3edb6b00126e725` |
| 开始指纹 | [start-fingerprint.json](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/package-r1/start-fingerprint.json)，SHA `25d19d64dd3498b9df13bf7b44fa2bfcabd7665001b2ceca89eea4c3548e81a6` |
| 结束指纹 | [end-fingerprint.json](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/package-r1/end-fingerprint.json)，SHA `4da717e1a9999adf979d62ff867305863184fce1f554d0e851be6ede8874405f`；256内容/mode与开始逐条相等，HEAD/branch/status相同 |
| 矩阵核对 | [package-checks.json](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/package-r1/package-checks.json)，SHA `6de152200615c408a4ad0f60d362b5c6558e0738c3b3126d862b23e3065861c7`；95唯一ID、88run、state次序一致；旧67/60全保留 |
| 快照排除 | Git忽略的本轮自有 `/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/package-r1` 与主控controller证据目录；受审源码/测试/需求/契约没有排除 |

任务包六文件SHA（不是只靠HEAD）：

- `authorization.json`：`fb79284323a41ffe1eaacda8b670c690180e3b9fc347dd5874e49cf863fe744a`
- `baseline-manifest.json`：`3a3d72bc078a42b33a910bde471c00e04f1e6ee2817ca5cafd99b4731fd56a21`
- `requirements-v1.json`：`78fbd45ab53a1e04631592d94b1b8e8d6ed13371579e7b015f96f810cf892704`
- `runtime-addendum-proposal.md`：`1ea490abad1045b11774902faa4bc78b93ea9d64c1a44bc3bd406720b3141007`
- `state.json`：`36cbc6d4e3045113acfc4558f55e006e6777ddae3fcbdc1d973b90b29a847292`
- `task-v1.md`：`4a04e50b7a67350ae4e29640cc798ceb6f0d83c19b86ee77e8d48a97ab4d8f32`

## 3. 实际静态查证与方案适配

直接读AGENTS/AGENT、README/HANDOFF、原A2全文、接口文档8—10及相关方案、安全模型全文、验收矩阵、工作流入口/context/current-policy/issues/契约/模板、A1-review-r4、A2.1接受记录、B补正正式接受与review-r2定位、上一67项矩阵和任务包、本轮六文件。历史日志和旧通过数量仅作为出处及回归计划，未称本轮重跑。原A2旧路径/禁止B/旧权限文字依本轮真人授权解释；原安全行为不变。

必要基线代码实际读取：`authorization/verifier.py`真实invoke/canonical-result验证；`permission_snapshot.py`完整签名祖先与历史registration来源；`evidence_store.py`暂存、原件校验和first/retry闭包；`contracts/verification.py`与`contracts/execution.py`的独立可信类型；`ledger/service.py`接受、最终时钟、动态校验；`ledger/store.py`path/principals/task/grants/proof登记与关联；`execution/verified.py`、`execution/store.py`持久操作/事件/outbox读取、`execution/service.py`持久接受事实校验；`execution/worker.py`真实内部CLI；`server/config.py/factory.py/private_files.py/__main__.py`配置及安全文件原语；`identity/resolver.py`、`proof.py`、`claims.py`；pyproject和CI。静态读取没有执行密码/HTTP/DB业务。

必要测试实际读过的断言包括`test_query_contract.py`可信query字段与callback-only生产拒绝、`test_result_read_verifier.py`真实专用proof拒绝、`test_permission_snapshot.py`历史identity键绑定、`test_evidence_binding.py`晚证据/proof-link/deferred等待后时钟与rollback及backend终止、`test_verified_execution.py`真实四工具入口，以及integration conftest和TLS夹具装配。其余现有测试节点仅用AST定位供矩阵计划，未声称完成本轮深度行为验收。

| 核心项 | 包设计与基线兼容判断 |
| --- | --- |
| query bundle/source | 保留独立VerifiedResultQuery与PermissionSource、opaque evidenceRef；与既有canonical-result API兼容，无fakeinvoke、无请求自报权限。provider已将完整AS签名路径、约束、历史key绑定到DB事实；新增bundle文件在允许范围 |
| query evidence | 新query_binding在同事务重校原token/proof/body/context/source；现有ag_proofs支持purpose/endpoint/jti及operation_id/evidence_ref关联。B010只允许first/retry，本包明确不伪query为retry，无需改历史SQL |
| query锁/零成本 | principals排序→task→root-leafgrants→operation符合现有接受/撤销和恢复取子集的方向。预算、业务、lease不写；可复用store现有锁、proof和持久材料读取。仅原grant/holder/kid/tenant/task/subject/root且当前资源权限覆盖原意图；未知ID/他人对象统一403 |
| 最后时钟 | query在所有证据、行读取、proof关联及deferred constraint工作后，重读已持有的key/祖先，再clock_timestamp检查token/proof/grant窗口后commit；计划含lateDB依赖而非仅首次锁等待。现有accept_bound同样已有SET CONSTRAINTS后的final bound check，回归要求完整 |
| typed错误 | Verifier、proof与claims可兼容增加code/子类，保ValueError兼容、算法/字段/窗口/签发语义；域ExecutionError/LedgerError已有code。网关不能通过异常文字映射；严格schema和scope分开。本包已冻结400/401/403/409/422/503及内部500，认证challenge为AGPoP |
| 公开HTTP | 两条固定HTTPS POST、原body送真实验证器；敏感头不合并，framing/大小/类型/重复/深度/NaN严格；同步工作到有界线程，DB等待有界。invoke 202 current真实状态；query 200可信材料，未终态result=null；no-store与服务生成32hex request_id |
| 私有配置/装配 | gateway独立config/factory/CLI只加载AS公开信任key、批准identity、不可变DID与catalog，真实EvidenceStore/PermissionSnapshotProvider/ledger/execution/下游；不调用AS加载私钥的factory。安全文件primitive可只读复用，无需改server代码。init/check/run无隐式连接/迁移/reset，run强制TLS |
| worker/下游复现 | 现有`python -m agent_guard.execution.worker`已有单operation、run/reconcile、独立gateway/downstream DSN、独立服务secret、allowlist、lease、进程同步/恢复。新gateway CLI/README可用既有worker配置装配，HTTP不执行下游。可信catalog初始化、下游provision和完整B bundle迁移已有API；没有需要新worker路径的确定缺口 |
| 文件范围 | 29精确路径覆盖网关7文件、独立query、bundle/DTO、typed B错误与evidence、正式unit/PG/TLS测试及fixture、当前文档/实施报告；单writer串行合理。既有pytest/CI已递归收集tests/unit和tests/integration，包发现和wheel SQL清单现有可用，无需新依赖、SQL或CI改动 |

## 4. 完整95项逐项包审矩阵

完整原断言不在下表重复，已逐项绑定本轮requirements-v1 SHA和独立[requirement-package-checks.json](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/package-r1/requirement-package-checks.json)，其95个对象逐条保存原behavior、来源、必需/run旗标、代码/计划链、计划测试路径、现有节点定位、设计结果与NOT_RUN。该文件SHA：`aae53c810769fd2f4eb1c42523309f85d2f8b3db82a521dcf4e25bcb1b142862`。所有条目设计结果为PLAN_COMPLETE；**所有行为状态都是NOT_RUN_PACKAGE_REVIEW**。下表现有test名仅是运行计划定位，不是已执行证据；新增测试节点待worker实施后精确落盘并由fresh实现reviewer绑定assert/log/XML/hash。复合行为各子断言均在JSON保持，不允许只测代表项。

| 需求ID | 当前必需与证据要求 | 既有/计划实现链 | 测试节点或计划路径 | 本轮包审结果 |
| --- | --- | --- | --- | --- |
| A2-P01 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_core.py::test_p01_three_layer_order_settles_once | 计划完整；行为NOT_RUN |
| A2-P02 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_downstream.py::test_p14_refused_key_can_never_produce_an_effect_later<br>tests/integration/test_execution_core.py::test_p02_persisted_refusal_releases_and_blocks_late_success | 计划完整；行为NOT_RUN |
| A2-P03 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_core.py::test_p03_zero_amount_read_settles_calls<br>tests/integration/test_execution_core.py::test_p03_zero_amount_failure_releases_calls | 计划完整；行为NOT_RUN |
| A2-P04 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_recovery.py::test_p04_accept_alone_never_touches_the_downstream<br>tests/integration/test_execution_recovery.py::test_p04_rejected_accept_leaves_no_operation_and_no_effect<br>tests/integration/test_execution_recovery.py::test_p04_p06_real_process_killed_in_crash_window_then_restarted | 计划完整；行为NOT_RUN |
| A2-P05 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_core.py::test_p05_response_lost_keeps_budget_then_settles_same_order | 计划完整；行为NOT_RUN |
| A2-P06 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_core.py::test_p06_recovery_after_terminal_window_has_no_duplicate_effect<br>tests/integration/test_execution_recovery.py::test_p04_p06_real_process_killed_in_crash_window_then_restarted | 计划完整；行为NOT_RUN |
| A2-P07 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_core.py::test_p07_terminal_transaction_rolls_back_completely | 计划完整；行为NOT_RUN |
| A2-P08 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_core.py::test_p08_query_none_does_not_release_then_late_success_settles | 计划完整；行为NOT_RUN |
| A2-P09 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_recovery.py::test_p09_two_recoverers_race_one_terminal_and_one_outbox<br>tests/integration/test_execution_recovery.py::test_p09_expired_old_worker_cannot_overwrite_the_new_terminal | 计划完整；行为NOT_RUN |
| A2-P10 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_recovery.py::test_p10_internal_recovery_completes_after_revocation<br>tests/integration/test_execution_recovery.py::test_p10_external_retry_rejected_after_revocation | 计划完整；行为NOT_RUN |
| A2-P11 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_quotes.py::test_p11_existing_intent_survives_quote_edit_and_delete<br>tests/integration/test_execution_quotes.py::test_p11_new_key_requires_a_valid_current_quote | 计划完整；行为NOT_RUN |
| A2-P12 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_core.py::test_p12_amount_mismatch_keeps_budget_and_never_settles<br>tests/integration/test_execution_core.py::test_p12_intent_mismatch_keeps_budget | 计划完整；行为NOT_RUN |
| A2-P13 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_concurrency.py | 计划完整；行为NOT_RUN |
| A2-P14 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_downstream.py::test_p14_same_key_same_intent_replays_one_order<br>tests/integration/test_downstream.py::test_p14_notification_and_read_are_idempotent_too | 计划完整；行为NOT_RUN |
| A2-P15-CORE | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_final_boundaries.py::test_read_shaped_nonread_outcome_stays_unknown_then_recovers<br>tests/integration/test_execution_final_boundaries.py::test_item_bound_is_enforced_before_accept_and_full_256_recovers | 计划完整；行为NOT_RUN |
| A2-P19 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_a2_migrations.py::test_p19_upgrade_from_001_preserves_nonzero_seven_tables<br>tests/integration/test_a2_migrations.py::test_p19_upgrade_from_003_preserves_nonzero_seven_tables | 计划完整；行为NOT_RUN |
| A2-P20 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_a2_migrations.py::test_p19_upgrade_from_001_preserves_nonzero_seven_tables<br>tests/integration/test_a2_migrations.py::test_p19_upgrade_from_003_preserves_nonzero_seven_tables | 计划完整；行为NOT_RUN |
| A2-CKPT1-OBL01 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_regressions.py<br>tests/integration/test_execution_r3_regressions.py<br>tests/integration/test_execution_r4_regressions.py<br>tests/integration/test_execution_r5_regressions.py<br>tests/integration/test_a2_migrations.py | 计划完整；行为NOT_RUN |
| A2-CKPT1-OBL02 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_regressions.py<br>tests/integration/test_execution_r3_regressions.py<br>tests/integration/test_execution_r4_regressions.py<br>tests/integration/test_execution_r5_regressions.py<br>tests/integration/test_a2_migrations.py | 计划完整；行为NOT_RUN |
| A2-CKPT1-OBL03 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_regressions.py<br>tests/integration/test_execution_r3_regressions.py<br>tests/integration/test_execution_r4_regressions.py<br>tests/integration/test_execution_r5_regressions.py<br>tests/integration/test_a2_migrations.py | 计划完整；行为NOT_RUN |
| A2-CKPT1-OBL04 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_regressions.py<br>tests/integration/test_execution_r3_regressions.py<br>tests/integration/test_execution_r4_regressions.py<br>tests/integration/test_execution_r5_regressions.py<br>tests/integration/test_a2_migrations.py | 计划完整；行为NOT_RUN |
| A2-CKPT1-OBL05 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_regressions.py<br>tests/integration/test_execution_r3_regressions.py<br>tests/integration/test_execution_r4_regressions.py<br>tests/integration/test_execution_r5_regressions.py<br>tests/integration/test_a2_migrations.py | 计划完整；行为NOT_RUN |
| A2-CKPT1-OBL06 | 是；必须独立实跑 | execution/service.py、execution/store.py | tests/integration/test_execution_regressions.py<br>tests/integration/test_execution_r3_regressions.py<br>tests/integration/test_execution_r4_regressions.py<br>tests/integration/test_execution_r5_regressions.py<br>tests/integration/test_a2_migrations.py | 计划完整；行为NOT_RUN |
| WF-A1-REGRESSION | 是；必须独立实跑 | ledger/service.py、execution/service.py | tests<br>README.md<br>tasks/workflow/runs/local-remediation-20261004/task-v1.md | 计划完整；行为NOT_RUN |
| WF-INDEPENDENT-PROBES | 是；必须独立实跑 | ledger/service.py、execution/service.py | tests<br>README.md<br>tasks/workflow/runs/local-remediation-20261004/task-v1.md | 计划完整；行为NOT_RUN |
| WF-QUALITY-CHECKS | 是；必须独立实跑 | ledger/service.py、execution/service.py | tests<br>README.md<br>tasks/workflow/runs/local-remediation-20261004/task-v1.md | 计划完整；行为NOT_RUN |
| WF-PY311-ENV | 是；必须独立实跑 | ledger/service.py、execution/service.py | tests/integration/test_server_tls.py::test_tls_server_runs_the_full_as_flow<br>tests/integration/test_sm2_interop.py::test_sm2_signatures_interoperate_in_both_directions | 计划完整；行为NOT_RUN |
| WF-RESOURCE-ISOLATION | 是；必须独立实跑 | ledger/service.py、execution/service.py | tests/integration/test_isolation.py::test_wrong_target_maintenance_database_is_refused<br>tests/integration/test_isolation.py::test_wrong_target_unnamed_database_is_refused | 计划完整；行为NOT_RUN |
| WF-IMMUTABLE-BASELINE | 是；静态/控制义务 | import-provenance.json、start.json | tests<br>README.md<br>tasks/workflow/runs/local-remediation-20261004/task-v1.md | 计划完整；行为NOT_RUN |
| WF-DOCS-REPORT | 是；静态/控制义务 | docs-goal-map.json、all-doc-links.json、clean-docs.xml、wheel-readme-observations.json | tests<br>README.md<br>tasks/workflow/runs/local-remediation-20261004/task-v1.md | 计划完整；行为NOT_RUN |
| WF-SNAPSHOT-COVERAGE | 是；静态/控制义务 | start.json、end.json、native-stop-observation.json、copy-binding.json | tests<br>README.md<br>tasks/workflow/runs/local-remediation-20261004/task-v1.md | 计划完整；行为NOT_RUN |
| B-01-CRYPTO | 是；必须独立实跑 | crypto/sm.py | tests/integration/test_sm2_interop.py::test_sm2_signatures_interoperate_in_both_directions<br>tests/integration/test_sm2_interop.py::test_openssl_jws_segment_verifies_through_b_verifier | 计划完整；行为NOT_RUN |
| B-02-ENCODING | 是；必须独立实跑 | contracts/encoding.py、crypto/sm.py | tests/test_encoding.py<br>tests/test_crypto_profile.py | 计划完整；行为NOT_RUN |
| B-03-IDENTITY | 是；必须独立实跑 | identity/resolver.py | tests/integration/test_http_boundaries.py::test_real_https_route_refusals_preserve_rows_then_succeed<br>tests/integration/test_http_boundaries.py::test_verified_tls_exact_transport_boundary_and_get_routes | 计划完整；行为NOT_RUN |
| B-04-TOKEN-POLICY | 是；必须独立实跑 | authorization/claims.py、authorization/exchange.py | tests/integration/test_verified_execution.py::test_signed_chain_all_four_tools_and_real_receipt<br>tests/integration/test_verified_execution.py::test_projection_rejects_read_shaped_nonread_success | 计划完整；行为NOT_RUN |
| B-05-INVOKE-PROOF | 是；必须独立实跑 | authorization/verifier.py、authorization/proof.py | tests/integration/test_verified_execution.py::test_signed_chain_all_four_tools_and_real_receipt<br>tests/integration/test_verified_execution.py::test_projection_rejects_read_shaped_nonread_success | 计划完整；行为NOT_RUN |
| B-06-CODE-OIDC | 是；必须独立实跑 | authorization/code_service.py、authorization/consent.py | tests/integration/test_consent_final_decision.py::test_policy_lock_final_expiry<br>tests/integration/test_consent_final_decision.py::test_login_csrf_lock_expiry | 计划完整；行为NOT_RUN |
| B-07-ROOT-ISSUANCE | 是；必须独立实跑 | authorization/code_service.py、ledger/provisioning.py | tests/integration/test_code_service.py::test_code_is_one_use_and_signs_root_and_id_token<br>tests/integration/test_code_service.py::test_two_codes_for_one_task_cannot_create_two_roots | 计划完整；行为NOT_RUN |
| B-08-DELEGATION | 是；必须独立实跑 | authorization/exchange_service.py、authorization/exchange.py | tests/integration/test_exchange_service.py | 计划完整；行为NOT_RUN |
| B-09-DYNAMIC-STATE | 是；必须独立实跑 | authorization/exchange_service.py、authorization/introspection.py | tests/integration/test_consent_final_decision.py::test_policy_lock_final_expiry<br>tests/integration/test_consent_final_decision.py::test_login_csrf_lock_expiry | 计划完整；行为NOT_RUN |
| B-10-HTTP-TLS | 是；必须独立实跑 | authorization/http_app.py、server/factory.py | tests/integration/test_browser_boundary.py::test_real_services_reject_transport_before_effects_with_positive_control<br>tests/integration/test_browser_boundary.py::test_real_malformed_and_unknown_fields_have_no_effects | 计划完整；行为NOT_RUN |
| B-11-RESULT-READ | 是；必须独立实跑 | authorization/verifier.py、contracts/execution.py | tests/test_query_contract.py::test_canonical_query_requires_subject_and_explicit_method<br>tests/test_query_contract.py::test_callback_only_verifier_cannot_enter_production_query_or_bundle | 计划完整；行为NOT_RUN |
| B-12-EVIDENCE-RECEIPT | 是；必须独立实跑 | evidence/receipt.py、execution/receipt_projection.py | tests/integration/test_evidence_binding.py::test_bound_accept_final_clock_after_every_wait<br>tests/integration/test_evidence_binding.py::test_evidence_immutable_and_nonprivileged_role_refused | 计划完整；行为NOT_RUN |
| B-13-ROTATION-INTEROP | 是；必须独立实跑 | identity/resolver.py、crypto/sm.py | tests/integration/test_key_rotation.py::test_rotation_signs_with_new_kid_and_keeps_old_tokens_verifiable<br>tests/integration/test_key_rotation.py::test_rotation_without_historical_key_rejects_old_parent_token | 计划完整；行为NOT_RUN |
| B-14-DB-FAILURES | 是；必须独立实跑 | ledger/service.py、authorization/evidence_store.py | tests/integration/test_browser_boundary.py::test_real_services_reject_transport_before_effects_with_positive_control | 计划完整；行为NOT_RUN |
| B-15-CONCURRENCY-TEST-EFFICACY | 是；必须独立实跑 | ledger/service.py、execution/service.py | tests/integration/test_execution_concurrency.py<br>tests/unit/test_execution_concurrency_oracle.py<br>tests/integration/test_consent_final_decision.py | 计划完整；行为NOT_RUN |
| B-16-A1-REGRESSION | 是；必须独立实跑 | ledger/service.py、ledger/store.py | tests/integration/test_accept_core.py<br>tests/integration/test_invariants.py<br>tests/integration/test_state_checks.py<br>tests/integration/test_concurrency.py<br>tests/integration/test_rollback.py<br>tests/integration/test_rejects.py<br>tests/integration/test_isolation.py<br>tests/unit/test_input_validation.py | 计划完整；行为NOT_RUN |
| B-17-B-SUITE-QUALITY | 是；必须独立实跑 | crypto/sm.py、ledger/migrate.py | tests | 计划完整；行为NOT_RUN |
| B-18-RESOURCE-ISOLATION | 是；必须独立实跑 | ledger/migrate.py | tests/integration/test_isolation.py::test_wrong_target_maintenance_database_is_refused<br>tests/integration/test_isolation.py::test_wrong_target_unnamed_database_is_refused | 计划完整；行为NOT_RUN |
| B-19-CONTRACT-MERGE | 是；必须独立实跑 | execution/verified.py、authorization/permission_snapshot.py | tests/integration/test_verified_execution.py::test_signed_chain_all_four_tools_and_real_receipt<br>tests/integration/test_verified_execution.py::test_projection_rejects_read_shaped_nonread_success | 计划完整；行为NOT_RUN |
| B-20-MIGRATION-MERGE | 是；必须独立实跑 | ledger/lineage.py、ledger/migrate.py | tests/integration/test_lineage_migrations.py::test_public_a_view_rejects_b_legacy_before_bootstrap<br>tests/integration/test_lineage_migrations.py::test_completed_bundle_missing_evidence_namespace_refuses | 计划完整；行为NOT_RUN |
| B-21-SHARED-FILE-MERGE | 是；必须独立实跑 | ledger/lineage.py、ledger/migrate.py | tests/integration/test_lineage_migrations.py::test_public_a_view_rejects_b_legacy_before_bootstrap<br>tests/integration/test_lineage_migrations.py::test_completed_bundle_missing_evidence_namespace_refuses | 计划完整；行为NOT_RUN |
| B-22-ORIGINAL-GOAL | 是；静态/控制义务 | docs-goal-map.json、all-doc-links.json | docs/acceptance.md | 计划完整；行为NOT_RUN |
| B-23-HANDOFF-REPRODUCIBILITY | 是；必须独立实跑 | server/factory.py、server/__main__.py | tests/integration/test_server_tls.py::test_tls_server_runs_the_full_as_flow | 计划完整；行为NOT_RUN |
| B-24-FINAL-BINDING | 是；静态/控制义务 | start.json、end.json、native-stop-observation.json、cleanup.json | tasks/workflow/runs/local-remediation-20261004/task-v1.md | 计划完整；行为NOT_RUN |
| BR-01-CONSENT-FINAL | 是；必须独立实跑 | authorization/consent.py | tests/integration/test_consent_final_decision.py::test_policy_lock_final_expiry<br>tests/integration/test_consent_final_decision.py::test_login_csrf_lock_expiry | 计划完整；行为NOT_RUN |
| BR-02-HTTP-REJECTION | 是；必须独立实跑 | authorization/http_app.py、server/middleware.py | tests/integration/test_browser_boundary.py::test_real_services_reject_transport_before_effects_with_positive_control<br>tests/integration/test_browser_boundary.py::test_real_malformed_and_unknown_fields_have_no_effects | 计划完整；行为NOT_RUN |
| BR-03-PRIVATE-PATHS | 是；必须独立实跑 | server/private_files.py | tests/test_private_file_primitives.py::test_valid_read_modes_path_and_context<br>tests/test_private_file_primitives.py::test_create_context_retains_handle_for_six_exclusive_writes | 计划完整；行为NOT_RUN |
| BR-04-LINEAGE-HISTORY | 是；必须独立实跑 | ledger/lineage.py | tests/integration/test_lineage_migrations.py::test_public_a_view_rejects_b_legacy_before_bootstrap<br>tests/integration/test_lineage_migrations.py::test_completed_bundle_missing_evidence_namespace_refuses | 计划完整；行为NOT_RUN |
| BR-05-LINEAGE-ATOMIC | 是；必须独立实跑 | ledger/lineage.py | tests/integration/test_lineage_migrations.py::test_public_a_view_rejects_b_legacy_before_bootstrap<br>tests/integration/test_lineage_migrations.py::test_completed_bundle_missing_evidence_namespace_refuses | 计划完整；行为NOT_RUN |
| BR-06-REAL-PERMISSIONS | 是；必须独立实跑 | authorization/verifier.py、authorization/permission_snapshot.py | tests/integration/test_verified_execution.py::test_signed_chain_all_four_tools_and_real_receipt<br>tests/integration/test_verified_execution.py::test_projection_rejects_read_shaped_nonread_success | 计划完整；行为NOT_RUN |
| BR-07-QUERY-DTO | 是；必须独立实跑 | authorization/verifier.py、contracts/execution.py | tests/test_query_contract.py::test_canonical_query_requires_subject_and_explicit_method<br>tests/test_query_contract.py::test_callback_only_verifier_cannot_enter_production_query_or_bundle | 计划完整；行为NOT_RUN |
| BR-08-EVIDENCE-BINDING | 是；必须独立实跑 | authorization/evidence_store.py、ledger/service.py | tests/integration/test_evidence_binding.py::test_bound_accept_final_clock_after_every_wait<br>tests/integration/test_evidence_binding.py::test_evidence_immutable_and_nonprivileged_role_refused | 计划完整；行为NOT_RUN |
| BR-09-RECEIPT-PROJECTION | 是；必须独立实跑 | execution/receipt_projection.py、evidence/receipt.py | tests/integration/test_evidence_binding.py::test_bound_accept_final_clock_after_every_wait<br>tests/integration/test_evidence_binding.py::test_evidence_immutable_and_nonprivileged_role_refused | 计划完整；行为NOT_RUN |
| BR-10-IMPORT-PROVENANCE | 是；静态/控制义务 | import-provenance.json、start.json、historical-copy-binding.json | .github/workflows/ci.yml<br>pyproject.toml<br>tests/integration/conftest.py | 计划完整；行为NOT_RUN |
| BR-11-CLEAN-CANDIDATE | 是；必须独立实跑 | ledger/lineage.py、server/factory.py | tests/integration/test_a2_migrations.py::test_p19_upgrade_from_001_preserves_nonzero_seven_tables<br>tests/integration/test_a2_migrations.py::test_p19_upgrade_from_003_preserves_nonzero_seven_tables | 计划完整；行为NOT_RUN |
| BR-12-WORKFLOW-BARRIER | 是；静态/控制义务 | native-stop-observation.json、start.json、end.json | tasks/workflow/runs/local-remediation-20261004/task-v1.md | 计划完整；行为NOT_RUN |
| A2-P15 | 是；必须独立实跑 | authorization/verifier.py + tools/params.py/policy.py + gateway/http_app.py（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A2-P16 | 是；必须独立实跑 | InvocationVerifier.verify_bundle + VerifiedExecution.accept + gateway endpoint（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A2-P17 | 是；必须独立实跑 | verify_query_bundle + execution/query.py + EvidenceStore.query_binding（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A2-P21-HTTP | 是；必须独立实跑 | gateway factory/CLI → 真实TLS → 四工具 → 现有worker → authorized query（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-01-REUSE | 是；必须独立实跑 | 真实B verifier → VerifiedExecution → ExecutionService → accept_bound（复用计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-02-TRANSPORT | 是；必须独立实跑 | gateway/http_app.py/endpoint.py/errors.py + 真实B/PG服务（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-03-FRAMING | 是；必须独立实跑 | gateway/http_app.py/endpoint.py/errors.py + 真实B/PG服务（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-04-INVOKE | 是；必须独立实跑 | gateway/http_app.py/endpoint.py/errors.py + 真实B/PG服务（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-05-QUERY-BUNDLE | 是；必须独立实跑 | authorization/verifier.py/evidence_store.py + contracts/verification.py + execution/query.py（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-06-QUERY-LOCKS | 是；必须独立实跑 | authorization/verifier.py/evidence_store.py + contracts/verification.py + execution/query.py（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-07-QUERY-OWNERSHIP | 是；必须独立实跑 | authorization/verifier.py/evidence_store.py + contracts/verification.py + execution/query.py（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-08-QUERY-FINAL-CLOCK | 是；必须独立实跑 | authorization/verifier.py/evidence_store.py + contracts/verification.py + execution/query.py（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-09-QUERY-REPLAY | 是；必须独立实跑 | authorization/verifier.py/evidence_store.py + contracts/verification.py + execution/query.py（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-10-QUERY-ZERO-COST | 是；必须独立实跑 | authorization/verifier.py/evidence_store.py + contracts/verification.py + execution/query.py（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-11-QUERY-EVIDENCE | 是；必须独立实跑 | authorization/verifier.py/evidence_store.py + contracts/verification.py + execution/query.py（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-12-QUERY-PERMISSION | 是；必须独立实跑 | authorization/verifier.py/evidence_store.py + contracts/verification.py + execution/query.py（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-13-DYNAMIC-RACES | 是；必须独立实跑 | authorization/verifier.py/evidence_store.py + contracts/verification.py + execution/query.py（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-14-ERRORS | 是；必须独立实跑 | gateway/http_app.py/endpoint.py/errors.py + 真实B/PG服务（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-15-FAIL-CLOSED | 是；必须独立实跑 | gateway/http_app.py/endpoint.py/errors.py + 真实B/PG服务（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-16-PRIVATE-CONFIG | 是；必须独立实跑 | gateway/config.py/factory.py/__main__.py + server/private_files.py + 现有execution.worker（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-17-STARTUP | 是；必须独立实跑 | gateway/config.py/factory.py/__main__.py + server/private_files.py + 现有execution.worker（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-18-REAL-TLS | 是；必须独立实跑 | gateway/config.py/factory.py/__main__.py + server/private_files.py + 现有execution.worker（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-19-PRIVACY | 是；必须独立实跑 | gateway/http_app.py/endpoint.py/errors.py + 真实B/PG服务（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-20-BOUNDARIES | 是；必须独立实跑 | 本轮完整source/wheel候选、原正式测试与历史探针、主控状态/资源/文档（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-21-DOCS | 是；必须独立实跑 | 本轮完整source/wheel候选、原正式测试与历史探针、主控状态/资源/文档（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-22-REGRESSION | 是；必须独立实跑 | 本轮完整source/wheel候选、原正式测试与历史探针、主控状态/资源/文档（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-23-ENV-PROVENANCE | 是；必须独立实跑 | 本轮完整source/wheel候选、原正式测试与历史探针、主控状态/资源/文档（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |
| A22-24-FREEZE-RESOURCES | 是；必须独立实跑 | 本轮完整source/wheel候选、原正式测试与历史探针、主控状态/资源/文档（计划） | tests/integration/test_gateway_http.py<br>tests/integration/test_gateway_query.py<br>tests/integration/test_gateway_tls.py<br>tests/unit/test_gateway_boundary.py<br>tests/unit/test_gateway_config.py | 计划完整；行为NOT_RUN |

## 5. 专项、历史回归及资源计划

| 专项 | 完整计划核验 |
| --- | --- |
| A1/A2.1全部历史义务 | U1/P1—14/F1—5、根永久唯一/不可重建、七表非零升级、旧SQL checksum、C1—C6和CKPT1六义务均继承；A2规定竞争组10轮、真实SIGKILL/新PID恢复，账本/效果/事件/outbox同步断言，不能用固定计数代替 |
| B与六补正问题 | 全B24/BR12保留；OUTCOME、ITEM-LIMIT、RECEIPT-DUPLICATE、P13-ORACLE、RECEIPT-TEST-BRANCH、P13-TIMEOUT-CONTROL及干净文档/工作流证据保护均由完整source/wheel＋历史探针/负控验证，不能只重跑新gateway |
| 历史原件与适配 | 原67任务包历史probe inventory和接受记录仍为出处；原A482、B等价探针等按原断言复跑，原失败、合法tuple/list过严、旧升级期望、旧B barrier适配保存原件/diff/等价说明；缺失云端原件明确新重构，旧P11一次无code异常不编造根因 |
| 新真实HTTP/TLS | 新P15/P16/P17、P21-HTTP每子断言；受信开发CA与hostname默认校验，错CA/host负控；独立gateway PID/就绪/退出和持久终态重启查询，四工具真实签名、终态重试与新proof查询 |
| 新query边界 | 完整ownership与权限/路径、坏原事实与ref/source替换、proof并发最多一成功、成功/失败零业务计数；所有可能晚DB阻塞后TTL；撤销/key停用vsquery/accept线性化，各规定组10轮，独立连接barrier/event、目标PID/SQLSTATE、完整异常收集和有效负控 |
| 全source/非editablewheel | 各自全非集成/PG集成、lint/format/diff、A1单列、demo/README、历史探针；精确runtime/devlock、Python3.11、PEP517 setuptools80.9，Linux构建wheel，全部SQL携带；测试副本在src外，去editable/PYTHONPATH shadow，父/子进程来源见证 |
| 资源创建/操作 | worker与reviewer分别独占Linux/Python3.11环境、PG16容器＋network、gateway/独立downstream数据库；可复用UID501模式，创建前记录owner标签/名字/配置来源，创建后完整ID/挂载/端口/schema/进程清单；不是复用他人数据库或靠端口差异隔离 |
| 无关资源/秘密 | 禁连接、变更或清理agent-guard-a2-pg、verivote-web/api。清普通部署DSN只注入TEST DSN；不得打印secret/完整DSN/token/私钥。资源销毁前核完整ID/labels/owner，只删本轮成功创建资源；禁prune/共享compose down；全自有进程退出后冻结 |
| 当前文档 | 29路径涵盖worker需更新的README/HANDOFF/A2-report/stage/方案/安全/验收；主控拥有context/current-policy/issues/state与工作流入口。文档完成后须干净复制检查链接及逐字CLI复现；历史记录不改 |

## 6. 本轮执行证据

**本轮只有PACKAGE_REVIEW，未执行未实现行为测试，未创建业务测试资源。** 没有Ruff/Pytest/PG/HTTPS/SM2实跑结果或预计通过数。仅静态cat/sed/rg、Git状态与SHA/权限/JSON集合比较；最终核验脚本exit0。首次清单读取脚本误按files而实际schema为entries，KeyError在写指纹前退出；随后按真实schema重算，保存完整256条开始/结束结果，未触碰业务或受审文件。

可核对静态证据为start/end fingerprint、package-checks和95条requirement-package-checks；原67及31项历史正式通过仅核来源/义务，不算本轮行为通过。Python3工具仅用于元数据解析，不冒充Python3.11安装/运行验证。

## 7. 既有证据及尚未执行

A1历史验收、A2.1 r8/接受、B补正review-r2/接受记录、当前HANDOFF/context提供已合并能力及失败闭环出处；旧计数952/1388、原A482/探针等为历史记录。新fresh实施验收必须自身完整重跑，旧日志不替代。真实DB回滚、SIGKILL、断网与异常替身、真实TLS、真实SM2分别报告；包审不把未做业务测试当阻断，也不宣称它们已经通过。

远程CI按本轮用户授权在验收后Git发布阶段触发，条件合并不包括PR#6管理员例外；本包审未触发远程动作。

## 8. 缺陷与非阻断维护意见

**无已确认阻断包缺陷，无必须新增允许写路径。** 未把实现缺失/测试尚未运行当PACKAGE_CHANGES_REQUESTED或BLOCKED；没有关闭任何既有实施问题。

1. runtime-addendum-proposal正文保留“待批准/适配仍须确认”，而本轮authorization和state已GRANTED，主控提供实际异步批准。本proposal作为批准对象与正文原案保留不改变授权结论；主控当前状态/收尾应给清晰批准引用，避免读者误认未批准。
2. 继承WF-PY311/BR-11的“本轮无授权远程CI”等旧句仅代表原B任务语境，task-v1和真实接续提示词已明确验收后commit/push/PR/必需CI及条件审核。应在当前文档/报告澄清语境，不能将旧句当新限制或提前运行依据。
3. 每条精确正式test node/assert/log/hash需在worker交付和fresh实施验收落盘，当前file-level计划不作行为证据。内部config字段可在gateway允许文件与实施报告完成明确技术决定；公开协议/签名语义本包已冻结，不能以技术决定扩大它们。
4. 若实现实际证明需要额外helper/迁移/readonly源修改，按task既定规则停具体动作，主控改包/重冻/fresh包审；当前未发现这一需要，不要求过度拆模块。

## 9. 隔离与结束核验

本轮仅自有`/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/package-r1`内报告、JSON和指纹；无业务容器/network/DB/schema/venv/子服务创建，无部署DSN注入，无秘密读取或输出，无资源清理。未连接共享或既有数据库，也未声称其业务行得到全量比较。受审256条起止SHA/mode、完整Gitinventory/HEAD/branch/status一致；250条baseline逐条一致。报告目录与controller证据均属明确快照排除，正式6文件和所有受审产品未改。

## 10. 交主控的动作

可按已获本轮真人实施授权与有限运行适配派发单worker，继续A2.2实施/自查/停写冻结，再创建**新的**独立reviewer完成全部95项、88运行义务及完整回归。PACKAGE_READY只放行包质量，不能将state改ACCEPTED、复用本reviewer实施验收、冒充旧machine gate通过或进入A2.3。主控可原样保存本报告到正式package-review-r1并绑定SHA；本reviewer已完成且停写。
