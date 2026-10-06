# 验收与实验矩阵

本轮 B 补正已独立验收并通过 CI，经 [PR #6](https://github.com/Qdcchh/agent-guard/pull/6) 合并 main。67 项验收、60 项独立运行完成；见 [正式接受记录](../tasks/workflow/runs/local-remediation-20261004/acceptance.md)及 [当前交接](../tasks/workflow/context.md)。整体项目仍 **PARTIAL**：A2.2 已完成95项/88运行义务的独立验收，A2.3内部持续签名发布与真实HTTPS联合流程已完成完整119项/112运行义务独立复验并[正式接受](../tasks/workflow/runs/A2.3-receipts-20261004/acceptance.md)，原r1否决保留为历史；A3独立锚定/导出/交付演示与实验未完成；旧无回执公钥配置保持PENDING兼容。阶段通过不代表绝对无缺陷。

本文是唯一验收清单；[实施方案](oauth-oidc-sm2-mvp.md)定义接口，[安全模型](security-model.md)定义事务与安全边界。M编号为初版里程碑；SEC/CON/REC/AUD/ENG为成熟版回归维度，两者可关联同一测试，不需重复编写两套脚本。

## 1. 初版必须通过（M1—M13）

| 编号 | 测试 | 必须观察的证据 |
| --- | --- | --- |
| M1 | 登录、同意、授权码换SM2 ID/Access Token | 正常成功；state/nonce/redirect/PKCE错误及code重用拒绝 |
| M2 | planner→selector→executor两级委托 | AS统一签发、父根关联与逐维收窄；扩权拒绝 |
| M3 | DID解析与企业注册绑定 | 任意公钥替换、未知DID、错误用途及停用key拒绝 |
| M4 | 盗取token但无绑定私钥 | 工具调用和Token Exchange均失败，不只测试token篡改 |
| M5 | 参数/令牌替换及proof重放 | 商品、收货对象、工具版本、幂等键等签名绑定有效 |
| M6 | 根1000元，两分支同时各700元 | 最多一个接受，全部适用节点账本不超限 |
| M7 | 下游成功但响应丢失 | 只有一单、一次结算，UNKNOWN不提前释放 |
| M8 | 根/中间授权撤销及接受竞态 | 撤销提交后新接受拒绝，既有操作按约定恢复 |
| M9 | 回执验签与关联 | 独立验签、摘要重算；篡改结果、祖先路径、金额或次数delta失败；未锚定包明确标注 |
| M10 | 无模型API的干净部署 | 初始化、签发、委托、执行、攻击脚本和证据导出可复现 |
| M11 | 双code创建同任务根、重复同意、过期后重建 | 唯一根不重置，不产生两份预算 |
| M12 | 重复SKU、空/缺失约束及错误报价关联 | 无逐行数量绕过，缺失字段不默认无限制 |
| M13 | 锁等待超过proof TTL、子撤销后的交换重试 | 过期证明拒绝，幂等不复活失效授权或key |

M1覆盖OIDC代码流，M2—M5/M8覆盖授权安全，M6/M7/M11—M13覆盖预算与故障边界，M9/M10覆盖证据和工程复现。完整日志锚定与大规模实验可在成熟版补齐，但不得将初版未完成项写为已通过。

## 2. 成熟版安全与回归矩阵

| 编号 | 验收内容 | 必须观察的证据 |
| --- | --- | --- |
| SEC-01 | SM2/SM3 标准向量及跨实现验签 | 消息、用户标识、编码、篡改负例 |
| SEC-02 | 规范编码与严格解析 | 字段顺序、中文、重复字段、布尔整数、负数、溢出、未知字段 |
| SEC-03 | AS签发的根和两级委托，三个holder | 真实注册表路径及每一维扩权拒绝 |
| SEC-04 | 请求精确绑定 | 换任务/租户/服务/工具版本/报价/收货对象/holder 拒绝 |
| SEC-05 | AG-Proof抗重放与业务幂等 | proof jti重放拒绝，同键同意图无重复，同键改意图/授权节点拒绝 |
| SEC-06 | 祖先撤销与竞态 | 任意祖先撤销；撤销先提交拒绝；已接受按约定恢复 |
| SEC-07 | 入口与凭据隔离 | 代理直连下游、状态库或任意通知目标失败 |
| CON-01 | 多分支竞争根额度 | 根预算1000元，两分支各请求700元，最多接受一个 |
| CON-02 | 中间祖先额度 | 根有余额但中间祖先不足时拒绝，直接调用和后代共同计账 |
| CON-03 | 调用次数 | 读取/通知/订单均计数，失败与未知按状态机处理 |
| REC-01 | 故障矩阵 | 安全模型列明的全部中断点，祖先账本、下游效果和回执一致 |
| REC-02 | 迟到成功及多恢复者 | 查无结果后旧请求成功，不提前释放、不重复结算 |
| REC-03 | 报价快照跨执行与恢复一致 | 接受后价格变化不替换原快照；错误版本/金额不得执行，不确定效果不释放预算 |
| AUD-01 | 证据验证 | 链/请求/结果错配、篡改、重排、已锚定删除和回滚检测 |
| AUD-02 | 检测边界 | 无最新独立锚点、未锚定尾部的局限明确显示 |
| E2E-01 | 正常采购与攻击演示 | 确定性三代理四工具全链路，不依赖模型 API |
| ENG-01 | 干净环境复现 | 文档命令、依赖、数据库迁移、测试、演示与导出证据可复现 |

## 3. 性能与对照

- 目标规模：50 并发客户端、累计至少10,000次模拟调用；分别报告合法、攻击、重试样本构成。
- 指标：合法验权通过率、正常任务完成率、越权副作用数、预算不变量、重复效果数、撤销延迟。
- 开销：吞吐、P50/P95/P99、凭证尺寸、状态存储；区分密码、数据库、网络和模型推理。
- 报告 CPU/内存/系统、数据库配置、密码库版本、链深度、参数大小、预热与计时口径。不得只挑最佳一次结果。
- 对照：静态凭据/常规权限控制；签名委托但无原子共享预算的消融版；完整方案。已有授权方案做有依据的能力比较，未经同条件测试不声称性能优越。
- 令牌盗用专项对比：仅SM2签名Bearer版与SM2令牌+密钥绑定+AGPoP+状态检查版。前者明确标为消融版，不用于实际业务，也不冒充行业最佳基线。
- 安全负例的0次越权只对所声明测试集和模型成立，不构成普适证明。

## 4. 最终交付

设计与威胁分析、源码与依赖说明、公开测试和原始实验数据（无秘密）、可独立验证的合成证据包、部署复现说明、演示脚本/视频、技术报告和已知限制。10月20日前固定版本；所有材料与该版本保持一致。

## 5. 本段证据与后段责任（30项目标逐项保留）

下表关联本段67项矩阵中的实际测试函数，不另作正式PASS。每行具体断言、source/wheel参数化节点、命令退出码、XML与SHA见 [v1实施报告的完整矩阵索引](../tasks/workflow/runs/local-remediation-20261004/implementation-r1.md)；选定函数与断言绑定见 [文档实施报告的逐项目标索引](../tasks/workflow/runs/local-remediation-20261004/implementation-docs-r1.md)。该历史自查已由fresh r2完整复验并正式接受；A2.2已以95/88 fresh r2完成全部回归及新增公开网关/动态查询，见[本段接受记录](../tasks/workflow/runs/A2.2-integration-20261004/acceptance.md)。

| 原目标 | 本段67ID | 具体测试入口 | 本段观察与后段责任 |
| --- | --- | --- | --- |
| M1 | B-06-CODE-OIDC / B-10-HTTP-TLS | [`test_full_login_authorize_consent_and_redeem`](../tests/integration/test_login_consent.py) | 本段AS正常/负例：B补正ACCEPTED；公开四工具invoke/query已由A2.2独立接受，A2.3候选已有持续发布与真实联合HTTPS链，本候选完整A2已[正式接受](../tasks/workflow/runs/A2.3-receipts-20261004/acceptance.md)，原r1否决保留为历史；A2.2保留全部回归义务 |
| M2 | B-04-TOKEN-POLICY / B-08-DELEGATION / BR-06-REAL-PERMISSIONS | [`test_two_levels_are_as_signed_and_idempotent`](../tests/integration/test_exchange_service.py) | 真AS两级委托/三个holder：B补正ACCEPTED；A2.2保留全部回归义务 |
| M3 | B-03-IDENTITY / B-13-ROTATION-INTEROP / BR-11-CLEAN-CANDIDATE | [`test_historical_registration_is_keyed_by_exact_identity`](../tests/test_permission_snapshot.py) | 默认did:web真TLS与登记/用途/SPKI拒绝：B补正ACCEPTED；A2.2保留全部回归义务 |
| M4 | B-05-INVOKE-PROOF / BR-06-REAL-PERMISSIONS | [`test_static_verifier_rejects_tampering_and_does_not_stage`](../tests/test_authorization.py) | 盗token无私钥拒绝：B补正ACCEPTED；公开invoke已由A2.2独立接受；A2.2保留全部回归义务 |
| M5 | B-05-INVOKE-PROOF / A2-P15-CORE | [`test_proof_signing_helper_interoperates_with_static_verifier`](../tests/test_authorization.py) | 精确签名/参数/proof绑定：B补正ACCEPTED；A2.2保留全部回归义务 |
| M6 | A2-P13 / B-15-CONCURRENCY-TEST-EFFICACY | [`test_p13_two_draws_race_for_the_root_budget`](../tests/integration/test_execution_concurrency.py) | 祖先预算/两个700元并发10轮：B补正ACCEPTED，分层fixture不冒充全HTTP；A2.2保留全部回归义务 |
| M7 | A2-P05 / A2-P06 | [`test_p05_response_lost_keeps_budget_then_settles_same_order`](../tests/integration/test_execution_core.py) | 真实下游+响应丢失port替身和真进程恢复：B补正ACCEPTED；A2.2保留全部回归义务 |
| M8 | A2-P10 / B-09-DYNAMIC-STATE | [`test_p10_revocation_commits_first_then_accept_rejects`](../tests/integration/test_state_checks.py) | 撤销先提交拒绝与接受后内部恢复：B补正ACCEPTED；A2.2保留全部回归义务 |
| M9 | B-12-EVIDENCE-RECEIPT / BR-09-RECEIPT-PROJECTION | [`test_authentic_nonadjacent_duplicate_grant_rejected`](../tests/test_receipt_paths.py) | 真签名SDK和UNANCHORED关联：B补正ACCEPTED；A2.3候选已有持续发布；独立锚定/导出留A3；A2.2保留全部回归义务 |
| M10 | B-23-HANDOFF-REPRODUCIBILITY / BR-11-CLEAN-CANDIDATE | [`test_tls_server_runs_the_full_as_flow`](../tests/integration/test_server_tls.py) | 无模型API source/wheel/README/demo：B补正ACCEPTED；完整演示和导出待A3；A2.2保留全部回归义务 |
| M11 | B-07-ROOT-ISSUANCE / B-06-CODE-OIDC | [`test_two_codes_one_task_real_principal_lock_race`](../tests/integration/test_code_service.py) | 永久唯一根/双code10轮：B补正ACCEPTED；A2.2保留全部回归义务 |
| M12 | A2-P15-CORE / B-04-TOKEN-POLICY | [`test_item_bound_is_enforced_before_accept_and_full_256_recovers`](../tests/integration/test_execution_final_boundaries.py) | 重复/空缺集合/报价关联/256边界：B补正ACCEPTED；A2.2保留全部回归义务 |
| M13 | BR-01-CONSENT-FINAL / B-09-DYNAMIC-STATE | [`test_final_consent_after_late_dependencies`](../tests/integration/test_consent_final_decision.py) | 晚锁窗口及失效重试：B补正ACCEPTED；A2.2保留全部回归义务 |
| SEC-01 | B-01-CRYPTO | [`test_sm2_published_verification_vector`](../tests/test_crypto_profile.py) | 标准向量/OpenSSL双向：B补正ACCEPTED；A2.2保留全部回归义务 |
| SEC-02 | B-02-ENCODING | [`test_strict_json_and_rfc8785_canonicalization`](../tests/test_encoding.py) | 严格编码全入口：B补正ACCEPTED；A2.2保留全部回归义务 |
| SEC-03 | BR-06-REAL-PERMISSIONS | [`test_signed_chain_all_four_tools_and_real_receipt`](../tests/integration/test_verified_execution.py) | 真授权根/两级/三holder：B补正ACCEPTED；A2.2保留全部回归义务 |
| SEC-04 | B-05-INVOKE-PROOF | [`test_static_verifier_rejects_tampering_and_does_not_stage`](../tests/test_authorization.py) | tenant/task/工具/holder精确绑定：B补正ACCEPTED；A2.2保留全部回归义务 |
| SEC-05 | A2-P14 / B-08-DELEGATION | [`test_p14_same_key_same_intent_replays_one_order`](../tests/integration/test_downstream.py) | proof重放/业务键/效果幂等：B补正ACCEPTED；A2.2保留全部回归义务 |
| SEC-06 | A2-P10 / B-09-DYNAMIC-STATE | [`test_p10_revocation_commits_first_then_accept_rejects`](../tests/integration/test_state_checks.py) | 全祖先撤销竞态：B补正ACCEPTED；A2.2保留全部回归义务 |
| SEC-07 | A2-P14 / BR-03-PRIVATE-PATHS / BR-08-EVIDENCE-BINDING | [`test_valid_read_modes_path_and_context`](../tests/test_private_file_primitives.py) | 下游服务凭据、通知目标、DB拒绝角色：B补正ACCEPTED；本轮A2配置/低权限角色已核验，生产部署权限留A3；A2.2保留全部回归义务 |
| CON-01 | A2-P13 | [`test_p13_two_draws_race_for_the_root_budget`](../tests/integration/test_execution_concurrency.py) | 根预算并发：B补正ACCEPTED；A2.2保留全部回归义务 |
| CON-02 | A2-P13 | [`test_p13_intermediate_ancestor_budget_binds_under_concurrency`](../tests/integration/test_execution_concurrency.py) | 中间祖先不足：B补正ACCEPTED；A2.2保留全部回归义务 |
| CON-03 | A2-P03 / A2-P13 | [`test_p03_zero_amount_read_settles_calls`](../tests/integration/test_execution_core.py) | 零金额次数/未知预算保留：B补正ACCEPTED；A2.2保留全部回归义务 |
| REC-01 | A2-P04 / A2-P05 / A2-P06 / A2-P07 / A2-P08 / A2-P09 / B-14-DB-FAILURES | [`test_p06_recovery_after_terminal_window_has_no_duplicate_effect`](../tests/integration/test_execution_core.py) | 本段故障矩阵：B补正ACCEPTED；A2.3候选覆盖内部发布真进程故障，本候选完整A2已[正式接受](../tasks/workflow/runs/A2.3-receipts-20261004/acceptance.md)，原r1否决保留为历史；A2.2保留全部回归义务 |
| REC-02 | A2-P08 / A2-P09 | [`test_p09_two_recoverers_race_one_terminal_and_one_outbox`](../tests/integration/test_execution_recovery.py) | 迟到效果/双恢复者/fencing：B补正ACCEPTED；A2.2保留全部回归义务 |
| REC-03 | A2-P11 / A2-P12 | [`test_p11_existing_intent_survives_quote_edit_and_delete`](../tests/integration/test_execution_quotes.py) | 原报价快照/不一致UNKNOWN：B补正ACCEPTED；A2.2保留全部回归义务 |
| AUD-01 | B-12-EVIDENCE-RECEIPT / BR-09-RECEIPT-PROJECTION | [`test_authenticated_path_mutations_rejected`](../tests/test_receipt_paths.py) | 未锚定签验与改链/结果/delta拒绝：B补正ACCEPTED；锚定删除/回滚检测待A3；A2.2保留全部回归义务 |
| AUD-02 | B-12-EVIDENCE-RECEIPT | [`test_valid_unanchored_receipt`](../tests/test_receipt.py) | UNANCHORED报告边界：B补正ACCEPTED；独立最新锚点待A3；A2.2保留全部回归义务 |
| E2E-01 | B-23-HANDOFF-REPRODUCIBILITY / BR-06-REAL-PERMISSIONS | [`test_signed_chain_all_four_tools_and_real_receipt`](../tests/integration/test_verified_execution.py) | 合成AS演示/进程内四工具：B补正ACCEPTED；A2.3候选已有真实AS/GW四工具发布/query闭环；部署与三代理编排演示留A3.3；A2.2保留全部回归义务 |
| ENG-01 | B-17-B-SUITE-QUALITY / BR-11-CLEAN-CANDIDATE | [`test_init_creates_exclusive_private_tree`](../tests/test_server_private_files.py) | 锁安装/迁移/测试/README：B补正ACCEPTED；完整证据导出待A3；A2.2保留全部回归义务 |

A2.3候选的新增当前证据另由[`test_p21_https_login_consent_pkce_two_exchanges_four_tools_publish_query_offline`](../tests/integration/test_gateway_receipt_https.py)绑定M1/E2E-01真实协议链，[真实CLI崩溃窗口](../tests/integration/test_receipt_worker_process.py)绑定REC-01发布故障，[原材料/路径/结果与独立SDK验证](../tests/integration/test_receipt_publication.py)补充M9/AUD-01。以上已由[完整独立review-r2](../tasks/workflow/runs/A2.3-receipts-20261004/review-r2.md)独立复验并接受；原r1否决保留，且不改变AUD-02独立锚点、ENG-01导出和E2E部署编排的A3责任。

后段归属：A负责A2.2公开invoke/最终动态result-read；A/B负责A2.3持续签名发布与联合验收；A/B联合完成A3独立锚定、证据导出与完整三代理四工具HTTP采购闭环，材料/复现参与者负责独立复现、规模实验与公平对照。已有SDK签验/投影、AS TLS演示、README片段和故障测试不能替代这些交付。50客户端/10,000调用仍为目标，未计作本段性能实测。未锚定尾部、缺最新独立锚点和固定密码依赖维护不确定性仍须在最终报告说明。

原始矩阵与逐函数断言仅保存在本地、Git忽略的 `artifacts/workflow/local-remediation-20261004/worker-r1/requirements-matrix.json` 和 `artifacts/workflow/local-remediation-20261004/worker-docs-r1/goal-map.json`；干净克隆不包含这些原始日志，不以文件缺失或索引代替正式验收。


A2.3补正候选在真实签名/READY前复用原接受事实校验：对不可变报价执行精确总额、数量/原请求及cost currency/calls检查，并逐事件核对历史验真的完整root→leaf路径和四种delta。两列quote/result相互一致不能替代上述约束。校验读取均先于query最终DB时刻，不引入当前报价、下游结果或当前撤销/到期条件；合法零价及迟延终局仍可历史发布。失败保留PENDING/null及原ID/iat，当前query失败回滚proof/link，仅允许原契约的隔离STAGED证据。

容量域分列：本轮独立依据实际validator、q≥1/p≥0/Σq*p≤MAX_SAFE及标识符长度推导，canonical producer订单公开响应包含上界为48187＋2724＋124＝51035字节；兼容真实有效非canonical raw JWS仍可到16384，公开包含上界为48187＋16384＋124＝64695。两者均非共同可达合法最大值。正price的digits(q)＋digits(p)≤17，zero price≤16＋1；旧58168为较松Cartesian/标识符公式，仅历史比较。九个各≤65536组件的outer保守上界589964；1MiB/+1纯codec点并非保留组件profile的合法SDK bundle。组件64KiB、JWS16KiB、公开65536和外壳1MiB守卫不变；真实256 SKU、原边界/故障/回滚探针及范围分类见[完整独立review-r2](../tasks/workflow/runs/A2.3-receipts-20261004/review-r2.md)。本候选完整A2已[正式接受](../tasks/workflow/runs/A2.3-receipts-20261004/acceptance.md)，原r1否决保留。

最新结论：[正式接受](../tasks/workflow/runs/A2.3-receipts-20261004/acceptance.md)与[完整独立review-r2](../tasks/workflow/runs/A2.3-receipts-20261004/review-r2.md)，原[r1否决](../tasks/workflow/runs/A2.3-receipts-20261004/review-r1.md)及[实施自查](../tasks/workflow/runs/A2.3-receipts-20261004/implementation-remediation-r2.md)保留为历史。本轮依据[真人恢复](../tasks/workflow/runs/A2.3-receipts-20261004/user-resume-sol-20261006.md)完成完整复核与接受；最新真人要求协作发布并交接全部A3。当前协作版本通过PR #7交付，暂不合并，A3未实施；CI/审核以PR当前实际head为准。
