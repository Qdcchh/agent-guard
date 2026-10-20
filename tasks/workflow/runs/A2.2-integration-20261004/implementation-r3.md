# A2.2 implementation-r3 — READY_FOR_REVIEW

状态是worker自查READY_FOR_REVIEW，不是ACCEPTED。主控原生停写回执、最终冻结及fresh xhigh独立验收仍PENDING。

任务A2.2-integration-20261004 task-v1 / requirements-v1，95项/88必需运行，PACKAGE_READY、实施与有限运行适配GRANTED。角色/root/a22_worker_r1，请求gpt-6.1-sol/medium；后台实际生效模型metadata UNKNOWN。容量恢复未切换配置。owner a22-worker-resume-r3-20261004。

分支codex/a2.2-integration；HEAD 280022e9d7005daa8d551ba0e4c52e3228e3add5，产品基线d7e91c75014d1097c822936a16559229e2b4906a。没有commit/push/PR/reset/clean、依赖/锁/SQL/CI/旧正式测试修改。没有实施A2.3；后续合并/A2.3新授权由主控按后段包执行。

## 最终行为与实际范围

复用既有真实invoke验签/PermissionSource/同事务首次证据链；invoke仅接受，真实内部worker进程执行下游。VerifiedQueryBundle/AuthorizedQuery采用统一锁序，在proof INSERT/link、evidence、operation、deferred等全部晚DB等待后最终DB clock复核根/中/叶时效/撤销/holder key、ownership、当前权限、完整不可变原件。查询零业务/预算/lease效果，失败query proof回滚。HTTPS仅固定两个POST，严格header/body/schema/framing、有界线程和DB等待、typed错误/隐私；config init/check/run只加载AS公钥/identity/catalog，TLS必需、没有默认DB/隐式provision。

r3 A22-CTX-FIRST-BINDING（P2，FIXED_PENDING_REVIEW）：修前16同shape原context错值真实PG均错误200，修前exit1/16fail保留。query._original由immutable operation/raw token/proof/body/hash及PermissionSource重建完整context；16正式拒例+原invoke proof已过期而新query proof合法正例17项，以及短联合19项实际通过。不是跨身份绕过结论，现ownership仍有效；不错误要求原proof如今新鲜，不统捕所有程序错误为503。

r3相对dispatch实际变更：HANDOFF.md, docs/security-model.md, src/agent_guard/execution/query.py, tasks/A2-report.md, tasks/workflow/stages/A2.2-integration.md, tests/integration/test_gateway_query.py。完整tracked/untracked/staged/unstaged见final-status.txt与两份patch；无删除/rename。28 worker可写路径（原29扣除受保护formal r1），没有worker修改root控制文档/历史report。

276项起始copy-start-r3-binding；全部source/wheel/历史/新增业务运行绑定copy-final-r3-binding。最终仅HANDOFF/A2-report/stage三文档变动，源码/正式tests/锁/14SQL不变；已同步clean candidate与wheel-tests，绑定copy-final-r3-doc-complete-binding，两环境各2文档测试重跑、链接/diff/只读检查通过。formal implementation-r3由主控待存，本轮没有假称该文件已存在；主控正式保存/链接后需最终文档核验。

## 实际命令与结果

计数是tests/failures/errors/skipped。每条实际argv/exit/time/log/XML/SHA和node在run-registry-r3.json。

| label | exit | JUnit tests/fail/error/skip |
| --- | --- | --- |
| source-final-r3-nonintegration | 0 | 1022/0/0/0 |
| source-final-r3-integration | 0 | 1832/0/0/0 |
| wheel-final-r3-nonintegration | 0 | 1022/0/0/0 |
| wheel-final-r3-integration | 0 | 1832/0/0/0 |
| historical-a2-original | 0 | 482/0/0/0 |
| historical-b-original | 1 | 250/25/4/0 |
| historical-b-equivalent | 0 | 250/0/0/0 |
| a1-current-unit | 0 | 70/0/0/0 |
| a1-current-pg | 0 | 87/0/0/0 |
| a1-original-ag_review_probe | 0 | 4/0/0/0 |
| a1-original-ag_review_f2 | 0 | 1/0/0/0 |
| a1-original-ag_review_upgrade | 1 | 1/1/0/0 |
| a1-upgrade-equivalent | 0 | 1/0/0/0 |
| source-independent | 0 | 26/0/0/0 |
| wheel-independent | 0 | 26/0/0/0 |
| source-local-boundary-original | 0 | 7/0/0/0 |
| wheel-local-boundary-original | 0 | 7/0/0/0 |
| oracle-controls-60 | 0 | 60/0/0/0 |
| source-a22-independent | 0 | 335/0/0/0 |
| wheel-a22-independent | 0 | 335/0/0/0 |
| wheel-process-witness | 0 | 2/0/0/0 |
| wheel-db-witness | 0 | 132/0/0/0 |
| wheel-http-db-witness | 0 | 30/0/0/0 |
| clean-docs | 0 | 2/0/0/0 |
| source-final-docs-r3 | 0 | 2/0/0/0 |
| wheel-final-docs-r3 | 0 | 2/0/0/0 |
| source-readme | 0 | 无JUnit，命令/观测见registry |
| wheel-readme | 0 | 无JUnit，命令/观测见registry |
| source-readme-gateway | 0 | 无JUnit，命令/观测见registry |
| wheel-readme-gateway | 0 | 无JUnit，命令/观测见registry |
| source-demo | 0 | 无JUnit，命令/观测见registry |
| wheel-demo | 0 | 无JUnit，命令/观测见registry |
| wheel-provenance | 0 | 无JUnit，命令/观测见registry |

四大普通/PG组是未加live observer的完整运行。后续各335增强项=原138（公开18+动态祖先120）+完整zero-effect192+真TLS child来源1+DTO/编码最大形状4。晚等待8类×正负×10轮；root/mid/leaf撤销/各holder key两种先后×10轮；全5状态、proof重放10轮、context16+过期原proof正例。每祖先四计数、操作/事件/outbox/lease与全部ds_*由正式原断言及独立wrapper组合核验，保持barrier/PG锁/PID/SQLSTATE/异常收集，不能以旧单函数泛称全部后置条件。

B原250为221pass/25fail/4error；原件完整保留，等价250全pass。75行historical-adaptations.diff只适配独占DB名、当前迁移集合、每PID初次barrier及ConfigError保留FileExistsError cause，无删除/弱化业务断言。A1原4+1通过、原升级旧仅002预期失败保留，002—006等价升级通过。旧oracle scheduling原重复脚本exit1保留，等价exit0；单原及其适配exit0。oracle60实际三种调度与异常/超时负控通过。旧P11不可复现根因UNKNOWN仍如实保留。

真实TLS四工具、默认CA/hostname、独立gateway/worker、真SIGKILL/new worker与gateway新PID持久查询由正式全PG及独立child节点分别断言。只读venv observer不改生产入口/argv、不读secret ENV；用__main__.__spec__.name/__file__及service模块识别，SIGKILL前落盘；两个被杀PID与worker-sync/live-map/实际死亡关联记录。观察就绪不代表业务完成；追加前件/启用条件/hash/live map及最终逐字还原都有证据。

## 响应界限与证据层次

公共编码与响应统一65536 bytes。旧1MiB实现尝试/63000过严正例适配保留r2历史，不再声称1MiB上限。DTO/规范编码四种最大字段过近似实际frame：order56187、notification4673、read6286、refusal8349 bytes；parser-valid，非最大合法公开HTTP请求/真实持久订单。真实operation/tool名更短，token/body容量和金额乘积不允许全部字段同时业务取最大；实际四工具TLS业务闭环另有节点。1MiB trusted projection注入验证编码层503+proof回滚；真实projection缩小byteguard64验证guard层503+回滚，不能将这两个注入称合法响应越过65536。

真签名合法短祖先窗口遵守链时间不变量，组合root/mid/leaf到期边界与原独立parent回归分层；不把leaf window泛称独立root/mid过期。坏可信材料shape与同shape16错值503；400 schema、403合法未授权SKU/scope/resource、401签名/token、409 replay/conflict、503 trusted-state、500未知程序错误分别保留实际节点。

## 95项完整自查索引

requirements-matrix-r3.json逐项保留完整behavior、file/function/line、实际参数化node/命令exit/log/XML/hash及清理/静态依据；assertion-catalog-r3.json保留断言原文、decorator与调用。以下每行索引不是以名称替代语义验收；fresh reviewer仍独立复核复合义务。

| ID | 精确断言索引（完整见JSON该ID） | 实际node映射/组数 |
| --- | --- | --- |
| A2-P01 | tests/integration/test_execution_core.py::test_p01_three_layer_order_settles_once | 2节点 / 2组exit0；待fresh |
| A2-P02 | tests/integration/test_downstream.py::test_p14_refused_key_can_never_produce_an_effect_later; tests/integration/test_execution_core.py::test_p02_persisted_refusal_releases_and_blocks_late_success | 4节点 / 2组exit0；待fresh |
| A2-P03 | tests/integration/test_execution_core.py::test_p03_zero_amount_read_settles_calls; tests/integration/test_execution_core.py::test_p03_zero_amount_failure_releases_calls | 6节点 / 2组exit0；待fresh |
| A2-P04 | tests/integration/test_execution_recovery.py::test_p04_accept_alone_never_touches_the_downstream; tests/integration/test_execution_recovery.py::test_p04_rejected_accept_leaves_no_operation_and_no_effect | 10节点 / 3组exit0；待fresh |
| A2-P05 | tests/integration/test_execution_core.py::test_p05_response_lost_keeps_budget_then_settles_same_order | 2节点 / 2组exit0；待fresh |
| A2-P06 | tests/integration/test_execution_core.py::test_p06_recovery_after_terminal_window_has_no_duplicate_effect; tests/integration/test_execution_recovery.py::test_p04_p06_real_process_killed_in_crash_window_then_restarted | 5节点 / 3组exit0；待fresh |
| A2-P07 | tests/integration/test_execution_core.py::test_p07_terminal_transaction_rolls_back_completely | 8节点 / 2组exit0；待fresh |
| A2-P08 | tests/integration/test_execution_core.py::test_p08_query_none_does_not_release_then_late_success_settles | 2节点 / 2组exit0；待fresh |
| A2-P09 | tests/integration/test_execution_recovery.py::test_p09_two_recoverers_race_one_terminal_and_one_outbox; tests/integration/test_execution_recovery.py::test_p09_expired_old_worker_cannot_overwrite_the_new_terminal | 208节点 / 2组exit0；待fresh |
| A2-P10 | tests/integration/test_execution_recovery.py::test_p10_internal_recovery_completes_after_revocation; tests/integration/test_execution_recovery.py::test_p10_external_retry_rejected_after_revocation | 14节点 / 3组exit0；待fresh |
| A2-P11 | tests/integration/test_execution_quotes.py::test_p11_existing_intent_survives_quote_edit_and_delete; tests/integration/test_execution_quotes.py::test_p11_new_key_requires_a_valid_current_quote | 10节点 / 2组exit0；待fresh |
| A2-P12 | tests/integration/test_execution_core.py::test_p12_amount_mismatch_keeps_budget_and_never_settles; tests/integration/test_execution_core.py::test_p12_intent_mismatch_keeps_budget | 372节点 / 2组exit0；待fresh |
| A2-P13 | test_oracle_controls.py::test_actual_timeout_under_scheduling; test_oracle_controls.py::test_missing_startup_is_diagnostic_and_bounded | 80节点 / 5组exit0；待fresh |
| A2-P14 | tests/integration/test_downstream.py::test_p14_same_key_same_intent_replays_one_order; tests/integration/test_downstream.py::test_p14_notification_and_read_are_idempotent_too | 28节点 / 2组exit0；待fresh |
| A2-P15-CORE | tests/integration/test_execution_final_boundaries.py::test_read_shaped_nonread_outcome_stays_unknown_then_recovers; tests/integration/test_execution_final_boundaries.py::test_item_bound_is_enforced_before_accept_and_full_256_recovers | 204节点 / 4组exit0；待fresh |
| A2-P19 | tests/integration/test_a2_migrations.py::test_p19_upgrade_from_001_preserves_nonzero_seven_tables; tests/integration/test_a2_migrations.py::test_p19_upgrade_from_003_preserves_nonzero_seven_tables | 81节点 / 3组exit0；待fresh |
| A2-P20 | tests/integration/test_a2_migrations.py::test_p19_upgrade_from_001_preserves_nonzero_seven_tables; tests/integration/test_a2_migrations.py::test_p19_upgrade_from_003_preserves_nonzero_seven_tables | 232节点 / 2组exit0；待fresh |
| A2-CKPT1-OBL01 | historical-original/a2/test_deadline.py::test_real_owned_downstream_lock_has_deadline; historical-original/a2/test_entry_windows.py::test_precommit_interruption_and_real_worker_have_zero_effect | 1188节点 / 3组exit0；待fresh |
| A2-CKPT1-OBL02 | historical-original/a2/test_deadline.py::test_real_owned_downstream_lock_has_deadline; historical-original/a2/test_entry_windows.py::test_precommit_interruption_and_real_worker_have_zero_effect | 1188节点 / 3组exit0；待fresh |
| A2-CKPT1-OBL03 | historical-original/a2/test_deadline.py::test_real_owned_downstream_lock_has_deadline; historical-original/a2/test_entry_windows.py::test_precommit_interruption_and_real_worker_have_zero_effect | 1188节点 / 3组exit0；待fresh |
| A2-CKPT1-OBL04 | historical-original/a2/test_deadline.py::test_real_owned_downstream_lock_has_deadline; historical-original/a2/test_entry_windows.py::test_precommit_interruption_and_real_worker_have_zero_effect | 1188节点 / 3组exit0；待fresh |
| A2-CKPT1-OBL05 | historical-original/a2/test_deadline.py::test_real_owned_downstream_lock_has_deadline; historical-original/a2/test_entry_windows.py::test_precommit_interruption_and_real_worker_have_zero_effect | 1188节点 / 3组exit0；待fresh |
| A2-CKPT1-OBL06 | historical-original/a2/test_deadline.py::test_real_owned_downstream_lock_has_deadline; historical-original/a2/test_entry_windows.py::test_precommit_interruption_and_real_worker_have_zero_effect | 1188节点 / 3组exit0；待fresh |
| WF-A1-REGRESSION | historical-adapted/a1/test_upgrade_nonzero.py::test_upgrade_preserves_nonzero_reservation_and_all_evidence; historical-original/a1/test_missing_invariants.py::test_subject_must_match_database_grant | 468节点 / 9组exit0；待fresh |
| WF-INDEPENDENT-PROBES | probes/test_independent_compound.py::test_maximum_width_zero_price_order_does_not_accept_read_shape; probes/test_r2_independent.py::test_oracle_baseexception_is_collected_and_rethrown_in_caller | 52节点 / 2组exit0；待fresh |
| WF-QUALITY-CHECKS | test_oracle_controls.py::test_actual_timeout_under_scheduling; test_oracle_controls.py::test_missing_startup_is_diagnostic_and_bounded | 87节点 / 7组exit0；待fresh |
| WF-PY311-ENV | tests/integration/test_server_tls.py::test_tls_server_runs_the_full_as_flow; tests/integration/test_sm2_interop.py::test_sm2_signatures_interoperate_in_both_directions | 9节点 / 5组exit0；待fresh |
| WF-RESOURCE-ISOLATION | tests/integration/test_isolation.py::test_wrong_target_maintenance_database_is_refused; tests/integration/test_isolation.py::test_wrong_target_unnamed_database_is_refused | 21节点 / 3组exit0；待fresh |
| WF-IMMUTABLE-BASELINE | readonly-baseline-r3.json; historical-evidence-readonly-r3.json; wheel-inventory-final-r3.json | 0节点 / 0组exit0；待fresh |
| WF-DOCS-REPORT | current-document-links.json; final-doc-only-synchronization.json; source-final-docs-r3.xml; wheel-final-docs-r3.xml; source-readme-observations.json; wheel-readme-observations.json; source-readme-gateway-observations.json; wheel-readme-gateway-observations.json | 0节点 / 0组exit0；待fresh |
| WF-SNAPSHOT-COVERAGE | copy-start-r3-binding.json; copy-final-r3-binding.json; copy-final-r3-doc-complete-binding.json; final-candidate-r3.json | 0节点 / 0组exit0；待fresh |
| B-01-CRYPTO | tests/integration/test_sm2_interop.py::test_sm2_signatures_interoperate_in_both_directions; tests/integration/test_sm2_interop.py::test_openssl_jws_segment_verifies_through_b_verifier | 46节点 / 4组exit0；待fresh |
| B-02-ENCODING | historical-adapted/b/test_r2_encoding.py::test_actual_negative_entry; historical-adapted/b/test_r2_encoding.py::test_legal_depth_boundary | 167节点 / 3组exit0；待fresh |
| B-03-IDENTITY | tests/integration/test_http_boundaries.py::test_real_https_route_refusals_preserve_rows_then_succeed; tests/integration/test_http_boundaries.py::test_verified_tls_exact_transport_boundary_and_get_routes | 130节点 / 4组exit0；待fresh |
| B-04-TOKEN-POLICY | tests/integration/test_verified_execution.py::test_signed_chain_all_four_tools_and_real_receipt; tests/integration/test_verified_execution.py::test_projection_rejects_read_shaped_nonread_success | 174节点 / 4组exit0；待fresh |
| B-05-INVOKE-PROOF | tests/integration/test_verified_execution.py::test_signed_chain_all_four_tools_and_real_receipt; tests/integration/test_verified_execution.py::test_projection_rejects_read_shaped_nonread_success | 154节点 / 4组exit0；待fresh |
| B-06-CODE-OIDC | tests/integration/test_consent_final_decision.py::test_policy_lock_final_expiry; tests/integration/test_consent_final_decision.py::test_login_csrf_lock_expiry | 446节点 / 4组exit0；待fresh |
| B-07-ROOT-ISSUANCE | tests/integration/test_code_service.py::test_code_is_one_use_and_signs_root_and_id_token; tests/integration/test_code_service.py::test_two_codes_for_one_task_cannot_create_two_roots | 106节点 / 2组exit0；待fresh |
| B-08-DELEGATION | historical-adapted/b/test_r1_races_current.py::test_same_delegation_key_real_wait; historical-adapted/b/test_r1_races_current.py::test_double_code_unique_root_real_wait | 160节点 / 3组exit0；待fresh |
| B-09-DYNAMIC-STATE | tests/integration/test_consent_final_decision.py::test_policy_lock_final_expiry; tests/integration/test_consent_final_decision.py::test_login_csrf_lock_expiry | 565节点 / 3组exit0；待fresh |
| B-10-HTTP-TLS | tests/integration/test_browser_boundary.py::test_real_services_reject_transport_before_effects_with_positive_control; tests/integration/test_browser_boundary.py::test_real_malformed_and_unknown_fields_have_no_effects | 1170节点 / 5组exit0；待fresh |
| B-11-RESULT-READ | tests/test_query_contract.py::test_canonical_query_requires_subject_and_explicit_method; tests/test_query_contract.py::test_callback_only_verifier_cannot_enter_production_query_or_bundle | 18节点 / 2组exit0；待fresh |
| B-12-EVIDENCE-RECEIPT | tests/integration/test_evidence_binding.py::test_bound_accept_final_clock_after_every_wait; tests/integration/test_evidence_binding.py::test_evidence_immutable_and_nonprivileged_role_refused | 655节点 / 5组exit0；待fresh |
| B-13-ROTATION-INTEROP | tests/integration/test_key_rotation.py::test_rotation_signs_with_new_kid_and_keeps_old_tokens_verifiable; tests/integration/test_key_rotation.py::test_rotation_without_historical_key_rejects_old_parent_token | 12节点 / 2组exit0；待fresh |
| B-14-DB-FAILURES | probes/test_real_serialization.py::test_real_pg_serialization_retries_and_atomicity; tests/integration/test_browser_boundary.py::test_real_services_reject_transport_before_effects_with_positive_control | 771节点 / 7组exit0；待fresh |
| B-15-CONCURRENCY-TEST-EFFICACY | test_oracle_controls.py::test_actual_timeout_under_scheduling; test_oracle_controls.py::test_missing_startup_is_diagnostic_and_bounded | 440节点 / 5组exit0；待fresh |
| B-16-A1-REGRESSION | historical-adapted/a1/test_upgrade_nonzero.py::test_upgrade_preserves_nonzero_reservation_and_all_evidence; historical-original/a1/test_missing_invariants.py::test_subject_must_match_database_grant | 468节点 / 9组exit0；待fresh |
| B-17-B-SUITE-QUALITY | historical-adapted/b/legacy/test_history1.py::test_used_revoked_root_cannot_be_deleted_and_reinserted_with_same_id; historical-adapted/b/legacy/test_history4.py::test_subject_must_match_database_grant | 6285节点 / 13组exit0；待fresh |
| B-18-RESOURCE-ISOLATION | tests/integration/test_isolation.py::test_wrong_target_maintenance_database_is_refused; tests/integration/test_isolation.py::test_wrong_target_unnamed_database_is_refused | 21节点 / 3组exit0；待fresh |
| B-19-CONTRACT-MERGE | tests/integration/test_verified_execution.py::test_signed_chain_all_four_tools_and_real_receipt; tests/integration/test_verified_execution.py::test_projection_rejects_read_shaped_nonread_success | 104节点 / 4组exit0；待fresh |
| B-20-MIGRATION-MERGE | tests/integration/test_lineage_migrations.py::test_public_a_view_rejects_b_legacy_before_bootstrap; tests/integration/test_lineage_migrations.py::test_completed_bundle_missing_evidence_namespace_refuses | 218节点 / 4组exit0；待fresh |
| B-21-SHARED-FILE-MERGE | tests/integration/test_lineage_migrations.py::test_public_a_view_rejects_b_legacy_before_bootstrap; tests/integration/test_lineage_migrations.py::test_completed_bundle_missing_evidence_namespace_refuses | 190节点 / 6组exit0；待fresh |
| B-22-ORIGINAL-GOAL | current-document-links.json; final-doc-only-synchronization.json | 0节点 / 0组exit0；待fresh |
| B-23-HANDOFF-REPRODUCIBILITY | tests/integration/test_server_tls.py::test_tls_server_runs_the_full_as_flow | 2节点 / 2组exit0；待fresh |
| B-24-FINAL-BINDING | final-candidate-r3.json; cleanup-r3.json; live-witness-restoration.json | 0节点 / 0组exit0；待fresh |
| BR-01-CONSENT-FINAL | tests/integration/test_consent_final_decision.py::test_policy_lock_final_expiry; tests/integration/test_consent_final_decision.py::test_login_csrf_lock_expiry | 446节点 / 4组exit0；待fresh |
| BR-02-HTTP-REJECTION | tests/integration/test_browser_boundary.py::test_real_services_reject_transport_before_effects_with_positive_control; tests/integration/test_browser_boundary.py::test_real_malformed_and_unknown_fields_have_no_effects | 1170节点 / 5组exit0；待fresh |
| BR-03-PRIVATE-PATHS | tests/test_private_file_primitives.py::test_valid_read_modes_path_and_context; tests/test_private_file_primitives.py::test_create_context_retains_handle_for_six_exclusive_writes | 308节点 / 2组exit0；待fresh |
| BR-04-LINEAGE-HISTORY | tests/integration/test_lineage_migrations.py::test_public_a_view_rejects_b_legacy_before_bootstrap; tests/integration/test_lineage_migrations.py::test_completed_bundle_missing_evidence_namespace_refuses | 218节点 / 4组exit0；待fresh |
| BR-05-LINEAGE-ATOMIC | tests/integration/test_lineage_migrations.py::test_public_a_view_rejects_b_legacy_before_bootstrap; tests/integration/test_lineage_migrations.py::test_completed_bundle_missing_evidence_namespace_refuses | 218节点 / 4组exit0；待fresh |
| BR-06-REAL-PERMISSIONS | tests/integration/test_verified_execution.py::test_signed_chain_all_four_tools_and_real_receipt; tests/integration/test_verified_execution.py::test_projection_rejects_read_shaped_nonread_success | 174节点 / 4组exit0；待fresh |
| BR-07-QUERY-DTO | tests/test_query_contract.py::test_canonical_query_requires_subject_and_explicit_method; tests/test_query_contract.py::test_callback_only_verifier_cannot_enter_production_query_or_bundle | 18节点 / 2组exit0；待fresh |
| BR-08-EVIDENCE-BINDING | tests/integration/test_evidence_binding.py::test_bound_accept_final_clock_after_every_wait; tests/integration/test_evidence_binding.py::test_evidence_immutable_and_nonprivileged_role_refused | 655节点 / 5组exit0；待fresh |
| BR-09-RECEIPT-PROJECTION | tests/integration/test_evidence_binding.py::test_bound_accept_final_clock_after_every_wait; tests/integration/test_evidence_binding.py::test_evidence_immutable_and_nonprivileged_role_refused | 655节点 / 5组exit0；待fresh |
| BR-10-IMPORT-PROVENANCE | wheel-inventory-final-r3.json; provenance-summary-r3.json; real-sigkill-live-map-correlations.json; readonly-baseline-r3.json | 0节点 / 0组exit0；待fresh |
| BR-11-CLEAN-CANDIDATE | historical-adapted/b/legacy/test_history1.py::test_used_revoked_root_cannot_be_deleted_and_reinserted_with_same_id; historical-adapted/b/legacy/test_history4.py::test_subject_must_match_database_grant | 6285节点 / 13组exit0；待fresh |
| BR-12-WORKFLOW-BARRIER | final-candidate-r3.json; cleanup-r3.json; historical-evidence-readonly-r3.json | 0节点 / 0组exit0；待fresh |
| A2-P15 | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1066节点 / 6组exit0；待fresh |
| A2-P16 | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1066节点 / 6组exit0；待fresh |
| A2-P17 | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1066节点 / 6组exit0；待fresh |
| A2-P21-HTTP | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1066节点 / 6组exit0；待fresh |
| A22-01-REUSE | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1066节点 / 6组exit0；待fresh |
| A22-02-TRANSPORT | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1022节点 / 6组exit0；待fresh |
| A22-03-FRAMING | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1030节点 / 6组exit0；待fresh |
| A22-04-INVOKE | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1022节点 / 6组exit0；待fresh |
| A22-05-QUERY-BUNDLE | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1026节点 / 6组exit0；待fresh |
| A22-06-QUERY-LOCKS | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_complete_zero_effects.py::test_every_status_all_downstream_rows | 1646节点 / 6组exit0；待fresh |
| A22-07-QUERY-OWNERSHIP | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1022节点 / 6组exit0；待fresh |
| A22-08-QUERY-FINAL-CLOCK | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_complete_zero_effects.py::test_every_status_all_downstream_rows | 1406节点 / 6组exit0；待fresh |
| A22-09-QUERY-REPLAY | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_complete_zero_effects.py::test_every_status_all_downstream_rows | 1406节点 / 6组exit0；待fresh |
| A22-10-QUERY-ZERO-COST | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_complete_zero_effects.py::test_every_status_all_downstream_rows | 1646节点 / 6组exit0；待fresh |
| A22-11-QUERY-EVIDENCE | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_complete_zero_effects.py::test_every_status_all_downstream_rows | 1937节点 / 7组exit0；待fresh |
| A22-12-QUERY-PERMISSION | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1022节点 / 6组exit0；待fresh |
| A22-13-DYNAMIC-RACES | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_complete_zero_effects.py::test_every_status_all_downstream_rows | 1679节点 / 7组exit0；待fresh |
| A22-14-ERRORS | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1066节点 / 6组exit0；待fresh |
| A22-15-FAIL-CLOSED | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1022节点 / 6组exit0；待fresh |
| A22-16-PRIVATE-CONFIG | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1022节点 / 6组exit0；待fresh |
| A22-17-STARTUP | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1022节点 / 6组exit0；待fresh |
| A22-18-REAL-TLS | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1022节点 / 6组exit0；待fresh |
| A22-19-PRIVACY | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1066节点 / 6组exit0；待fresh |
| A22-20-BOUNDARIES | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1066节点 / 6组exit0；待fresh |
| A22-21-DOCS | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1066节点 / 6组exit0；待fresh |
| A22-22-REGRESSION | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 6323节点 / 15组exit0；待fresh |
| A22-23-ENV-PROVENANCE | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1066节点 / 6组exit0；待fresh |
| A22-24-FREEZE-RESOURCES | a22-probes/test_child_import_sources.py::test_real_tls_children_have_live_import_sources; a22-probes/test_public_permission_controls.py::test_public_rejects_full_scope_and_schema_matrix | 1066节点 / 6组exit0；待fresh |

## 环境、失败、隐私与资源

Linux amd64 Python3.11.17 UID501在Mac Docker Rosetta运行，不冒称native arm。独立PG16、gateway/downstream数据库/事务域、无host PG port；/repo只读、/review自有写入。精确runtime/dev锁和PEP517 setuptools80.9.0；非editable wheel无src shadow，73包文件+14SQL逐字相同，父/实际child路径见证。版本/角色/OpenSSL/依赖许可证实际元数据见environment/provenance日志，无新增依赖。source-import-witness唯一已知前导违例是quality-small错误import exit91，quality-small-r2显式source path通过；wheel无违例，final组若错误来源会exit91。

harness-errors-r3.md保留r1 format_owned空stdout/恢复历史、r3首次lint2长行、错误import、双conftest collection exit2、过期原proof UTC helper错误和修复。原collection-error XML被后续exit1误复用覆盖不可恢复：registry原exit2只有完整原log/command，cases=[]且无该XML；现存XML仅属于exit1 r2（19项18pass1fail），最终19pass是唯一r3 XML，不重建冒充。

失败harness traceback的独占密码已精确脱敏，3XML原SHA→后SHA与20/32/2计数、case状态不变记录。属于证据隐私修正，不表示公开HTTP曾泄露。全部本轮execution XML/log/command/JSON/报告/registry/index最终隐私扫描；公开HTTP无secret泄露由真实拒例/子进程stdout断言独立支持。私钥只在自有容器tmp fixture/README私有目录，容器销毁清除；私有password文件已删。

r2全部458证据、r1 22历史原件逐SHA不变；r1 18历史draft哈希不被当成现行源码必须保持。历史SQL/锁/旧tests/正式state/task/auth/issues/report未改。

cleanup-r3.json记录fullIDs/owner核验、stop/rm/network-rm实际exit0、自有container/network余留0。三个无关容器原fullID前后仍在、未连接/改动/清理；只读observer逐字还原。所有owned服务/子进程随自有容器停止销毁，workspace/证据/草稿保留。原生停写回执由本次FINAL及主控保存，未伪造后续freeze/review。

## 限制与移交

worker完整95/88自查完成；fresh独立验收/主控最终freeze/正式报告落盘/issue关闭仍PENDING，A22-CTX-FIRST-BINDING仅FIXED_PENDING_REVIEW。A2.3持续签发发布、A3锚定、部署/50clients10k未在此worker执行；receipt仍PENDING/null，不冒称完整项目完成。后续授权由主控办理。

evidence-index-r3.json覆盖全部raw command/log/XML/probe/diff/JSON/报告SHA，copies/venvs/wheels分别由精确manifest绑定，索引自身SHA在原生FINAL。交回后停止全部写入，等主控scope核/原样formal保存/全freeze/fresh xhigh独立实跑。

最终隐私扫描初次exit1发现catalog测试源码synthetic DSN示例（值未输出）；首次直接JSON文本regex脱敏损坏转义quote结构，JSONDecodeError exit1，损坏件保留。由未改正式测试AST再生catalog匹配原SHA后，逐已解析字符串脱敏、原子JSON验证替换并更新矩阵hash。原测试字节/断言/行号及执行证据不变；细节见assertion-catalog-privacy-r3.json，不冒称生产接口或业务组失败。

该catalog首扫命中实为JSON转义关闭quote后的URI前缀误匹配；解析字符串后实际完整DSN替换数为0，修复后catalog原SHA与新SHA相同。不是新增真实凭据泄露。最终privacy扫描按JSON语义字符串/XML文本执行，避免把结构转义算作URI。
