# 独立审查：PACKAGE_REVIEW / B-remediation-integration-local-r3 / r1

## 1. 结论与范围

**PACKAGE_READY。包级阻断项：无。** 这只表示当前修补包具备实施条件，不是代码通过、IMPLEMENTATION_ACCEPTANCE、缺陷关闭或允许立即合并。产品仍为 PARTIAL，五个现有问题仍 OPEN / 待实施与独立验证。67 项要求和 60 项独立运行义务全部保留；本轮未运行任何行为测试，未创建 Python/PG 容器、数据库或业务资源。

审查时间：2026-10-04，Asia/Shanghai。仓库 `/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`；HEAD `2051b402c99a3d400d8f12749287075e23a9a521`，分支 `handoff/b-integration-20261003`。比较基线按本包 `153f14e9be180a1eb26b0f0e0898048d45170569`；远端保护由主控另行核对，本 reviewer 未查询远端。

授权按主控传入的真人原文、`authorization.json` 与已批准运行适配解释：允许本轮修补、完整复核和满足普通保护后的 Git 发布/合并；没有 A2.2/A2.3/A3 或部署授权。本轮不替真人另行授予权限。普通代码所有者审核尚未满足属于后段发布条件，不是阻止这个包开始修补的理由。

## 2. 独立性、版本与冻结证据

- 本会话为 fresh `/root/package_review_r1`，仅审包，不是实施者；未派生其他 agent。主控给定请求角色为 `gpt-6-astra / high`；后台有效模型/档位元数据没有由本会话独立取得，记 UNKNOWN，不以自述或请求值冒充有效值。
- `collaboration.list_agents` 显示主控与本 reviewer 运行，上一轮辅助 reviewer 已完成；没有本轮产品 worker。未声称已完整审计宿主所有进程。
- 开始独立重算四个包文件 SHA-256，全部匹配 `controller/package-freeze-r1.json`，记录于 `hash-before.json`。结束重复核对见 `hash-after.json`，四文件一致。
- 关联契约/产品/测试/配置及 tracked、untracked、deleted 的独立内容和 mode 清单见 `independent-candidate-check.json`，结束核对见 `hash-after.json`。Git 状态、mode 清单和历史原件校验保存在 `independent-static-checks.json`。
- 主控 `initial-worktree.json` 的 228 项中，唯一与当前内容不同的是本轮 requirements：初始 `b332ae…`，正式冻结值 `4e06f8…`。这是冻结前计划补充与正式包摘要的差别；本 reviewer 起止均为冻结值，**不是审查期间漂移**。实施基线必须明确采用 initial 清单加正式 package-freeze 覆盖，不应将初始 requirements 值误当待恢复版本。
- 本轮仅在 `artifacts/workflow/local-remediation-20261004/package-review-r1/` 写证据与本报告。没有改源码、正式测试、控制包、历史报告、SQL、依赖或 Git 配置，没有 commit/push/PR/merge。

## 3. 实际静态检查与方案判断

阅读并对照 AGENTS/AGENT、四个当前包文件、原 implementation/review-contract 与四份模板、Codex 补充契约、原 A2 全部 P 要求/检查点义务、A1 最终验收、A2.1 acceptance 与失败/补正记录、旧问题台账、上一轮 local-quality 报告，以及设计/安全/验收/密码配置、README/HANDOFF。历史报告的 PASS 和测试计数只作为原义务与触发条件来源，本轮不承接其代码通过结论。

实际追踪了以下相关路径：

1. `ExecutionService.accept_invocation` 在 `_read_path_ids`、静态权限、candidate 与账本接受前调用 `parse_tool_params`；因此 `_parse_items` 加数量边界可在 proof/operations/预留/效果新增前拒绝。`catalog.snapshot_from_bytes` 与 `results.parse_result` 当前分别写死 256；允许的 `contracts/execution.py` 可承载统一常量，由三者导入，不需新模块/依赖/迁移，也不需扩大读取上限。
2. `run_operation/reconcile → _decide → parse_result/bind_result → _finalize`：当前 read 分支只核 tool 字符串相等，未排除 order/notification。包要求在终局前绑定结果变体正确；shared binder 收严可同时保护 `execution/receipt_projection.py` 的调用方，保留 refusal 四工具语义以及原键/意图/完整快照/金额/effect 检查。
3. `verify_receipt_bundle → verify_compact_jws → validate_access_claims/validate_child → _verify_ledger`：当前子链只挡相邻重复，root/middle/root 的不同有效 token 可在 ID 层非相邻重复。离线完整路径全局唯一性是正确修复位置；按唯一授权路径逐位置核账本已有能力，仍需重复 ledger 节点负例。
4. `tests/integration/test_execution_concurrency.py::_race` 的 barrier 在 try 外，未捕获 RuntimeError，join 无界；混合竞争只断言 errors 数量。包的全线程完成、异常收集、有界同步和精确 LEASE_LOST 限制直接覆盖漏洞，新增 unit oracle 文件可验证故意异常/缺完成/超时不能假通过。
5. `test_offline_receipt_common_time_window_with_authentic_rebindings` 的 `startswith("future-")` 先吞掉 future-token；互斥分支和已签 token 的 iat/nbf 命中断言是正确补正。不应据此声称产品时间验证已有漏洞。

### 五项补正及回归的充分性

| 原问题 | 包设计结论 | 必须保留的实施/验收观察 |
| --- | --- | --- |
| A21-R1-OUTCOME | 计划充分 | order/notification × execute/query 共四触发；异常 UNKNOWN、所有祖先原预留、零终局/outbox；其后合法恢复唯一效果与一次 SETTLE；四工具正常成功、refusal、错ID/金额/报价和反向变体均保留 |
| BR-FINAL-ITEM-LIMIT | 计划充分 | 256 正常接受/执行/恢复；257 与大数组在接受前拒绝，proof/operation/每祖先预算/event/outbox/下游增量全零；bool/重复SKU/字节/深度/数量既有负例继续 |
| BR-FINAL-RECEIPT-DUPLICATE | 计划充分 | 独立真实 AS/GW/三个 holder key；root→middle→root 需重签全部受影响材料、重算摘要、合法时间/holder/邻接，拒绝确来自结构；合法三层与错序/缺祖先/相邻重复/重复ledger/错摘要分别覆盖 |
| BR-FINAL-P13-ORACLE | 计划充分 | RuntimeError、无关 ExecutionError、缺worker/超时必须使主线程失败；合法 LEASE_LOST 精确条件可接受；原四类 P13 竞争每组10轮，全祖先/效果/终局断言不得删除 |
| BR-FINAL-RECEIPT-TEST-BRANCH | 计划充分 | future-token 实际改变并重签目标 token；future-proof +5接受/+6拒绝保持；迟延终局、共同窗口、祖先/key控制不退化；不能只靠坏签名拒绝 |

### 17 个精确写路径

六个实现/契约路径（execution contract、params、catalog、results、execution service、offline receipt）覆盖上述改动；七个正式测试路径覆盖新增单元/PG/签名/oracle与现有 branch 修正；README/HANDOFF/A2-report 三个用户索引和一份 implementation 报告覆盖交付。**没有发现本方案必需而未授权的第18条产品路径。** 其他源码、fixtures、SQL、依赖锁与历史报告继续只读；额外必要缺陷/路径仍按包要求重新版本化并审包。

`pyproject.toml` 的 testpaths 为 tests；CI 已分别执行全部 tests 非集成与全部 tests/integration，因此计划新增的 unit、顶层 receipt 及 integration 文件会被收集，不需要为当前新文件修改 CI。

一个已核实的调用方注意点：`receipt_projection.project_receipt` 先调用 shared `bind_result`，再做自己的变体检查。收严 binder 后，现有 `test_projection_rejects_read_shaped_nonread_success` 会提前得到 `ExecutionError(DOWNSTREAM_INCONSISTENT)`，而不是当前预期的 `ReceiptProjectionError`。该入口本来已可传播 parse/bind 的 ExecutionError，没有“所有拒绝必须 ReceiptProjectionError”的统一现行实现承诺。允许在既有授权测试文件里精确断言这个新提前拒绝码并保持 rollback、原投影可重现和 outbox 不变；不得捕获 Exception 或删除原对抗 case。这是同一安全拒绝的更早执行，不是把异常结果改成成功。若实施选择统一投影异常接口，则必须先申请增加 projection 文件范围，不能自行越界。

## 4. 完整 67 项计划矩阵

以下每行只评价要求/验证计划，均不表示行为 PASS。原来源：A2-P 为原 A2 §7，OBL 为 ckpt1-r2 六义务，WF 为原工作流/A1回归；B/BR 为恢复的 B 24 项及补正 12 项，ID 与上一轮 67 行目录逐项相同，无新增替换或删除。60 行标“独立运行”的最终实现验收必须使用 fresh reviewer 当前原始证据；其余7行仍需完整静态/控制证据。

表中列出计划正式测试/检查入口，精确 test node、参数化分支、观察断言、命令/JUnit/hash 的最终绑定仍必须由实施者与 fresh reviewer 完成；不能拿文件名或旧计数代替。五项新增边界由 task-v1 §4补充，不能只运行表内旧函数。所有行的测试当前均为 PLANNED_NOT_RUN。

| 需求 ID | 最终独立运行义务 | 计划入口 | 必须观察的完整行为 / 设计结论 |
| --- | --- | --- | --- |
| A2-P01 | 是 | `tests/integration/test_execution_core.py` | 三层订单70000/1成功，唯一真实下游效果；根/中间/叶reserved归0，settled70000/1；RESERVE和SETTLE各一，终态/outbox一致；计划完整，未执行。 |
| A2-P02 | 是 | `tests/integration/test_execution_core.py`<br>`tests/integration/test_downstream.py` | 下游持久终局拒绝，FAILED、全路径释放不结算，RELEASE一条；该键不能迟到成功；计划完整，未执行。 |
| A2-P03 | 是 | `tests/integration/test_execution_core.py` | 读取/通知金额0但次数预留结算或释放正确；通知持久效果最多一次，读结果固定；计划完整，未执行。 |
| A2-P04 | 是 | `tests/integration/test_execution_recovery.py` | 接受提交前不得执行；提交后真独立子进程终止/重新启动，从持久状态恢复而非finally补救；保留pid/同步与DB断言证据；计划完整，未执行。 |
| A2-P05 | 是 | `tests/integration/test_execution_recovery.py` | 下游订单已提交响应丢失→UNKNOWN额度保留；同键恢复唯一订单、一次结算；计划完整，未执行。 |
| A2-P06 | 是 | `tests/integration/test_execution_recovery.py` | 下游成功、网关终局前崩溃；恢复无重复效果/账本/终局；计划完整，未执行。 |
| A2-P07 | 是 | `tests/integration/test_execution_recovery.py` | 终局事务节点/事件/outbox中途注入异常；全状态/计数/事件/outbox原子回滚，之后可恢复；计划完整，未执行。 |
| A2-P08 | 是 | `tests/integration/test_execution_recovery.py` | 查无结果后旧请求迟到成功；不释放，最终唯一效果和SETTLE；计划完整，未执行。 |
| A2-P09 | 是 | `tests/integration/test_execution_recovery.py` | 双恢复者、过期旧worker竞争，独立连接barrier/event每组10轮；终态不被覆盖、一个终局/一个outbox；计划完整，未执行。 |
| A2-P10 | 是 | `tests/integration/test_execution_validation.py` | 接受后祖先撤销/过期/key停用，内部恢复可完成原意图；外部接受重试仍拒绝；真实授权查询后段保留BLOCKED；计划完整，未执行。 |
| A2-P11 | 是 | `tests/integration/test_execution_quotes.py`<br>`tests/integration/test_execution_r4_regressions.py` | 当前报价改/删后的已有意图使用原成本/快照；新键要求有效报价；确定性miss→另accept→报价消失→安全重查命中；变grant/holder/参数、撤销、proof重放仍拒绝；计划完整，未执行。 |
| A2-P12 | 是 | `tests/integration/test_execution_final_boundaries.py`<br>`tests/integration/test_execution_regressions.py` | 下游金额/意图/完整快照错配且可能有效果→UNKNOWN保留预算，无伪成功/释放；计划完整，未执行。 |
| A2-P13 | 是 | `tests/integration/test_execution_concurrency.py` | 根/中间不足或次数耗尽及接受/结算/恢复并发，10轮、全祖先不超限不负数、不反向锁/死锁无界；计划完整，未执行。 |
| A2-P14 | 是 | `tests/integration/test_downstream.py` | 下游同键同意图和冲突、订单/通知均防重复，执行/查询无或错独立服务凭据拒绝、零泄漏/效果；不能只藏端口；计划完整，未执行。 |
| A2-P15-CORE | 是 | `tests/integration/test_execution_validation.py`<br>`tests/integration/test_execution_final_boundaries.py` | 四个完整工具ID/版本，重复JSON键/SKU、bool/负/浮点/溢出数量、缺/空集合、scope不足、跨租户/关联错/URL路径注入、快照/祖先包含错等分层负例，零预留/效果。可信fixture授权不是真实验签；计划完整，未执行。 |
| A2-P19 | 是 | `tests/integration/test_a2_migrations.py`<br>`tests/integration/test_migrations.py` | 001及003真实非零预留/撤销/证据升级到004，七旧表全行及完整迁移登记在非法升级时不变；合法重复迁移no-op；旧材料不足sidecar隔离保预算，不能补当前报价执行；计划完整，未执行。 |
| A2-P20 | 是 | `tests/integration/test_a2_migrations.py`<br>`tests/integration/test_execution_regressions.py` | 直接SQL改意图/成本/证据、删除重建路径/操作、改删事件/节点、阶段seq绕过、非法状态/双终局拒绝，旧账本不变；合法预算/撤销/状态UPDATE可用；计划完整，未执行。 |
| A2-CKPT1-OBL01 | 是 | `tests/integration/test_execution_regressions.py`<br>`tests/integration/test_execution_r3_regressions.py`<br>`tests/integration/test_execution_r4_regressions.py`<br>`tests/integration/test_execution_r5_regressions.py`<br>`tests/integration/test_a2_migrations.py` | 候选前schema/静态授权/可信集合，不要求当前报价存在；命中原快照关联+当前权限后仍A1 accept锁后复核/proof/意图；计划完整，未执行。 |
| A2-CKPT1-OBL02 | 是 | `tests/integration/test_execution_regressions.py`<br>`tests/integration/test_execution_r3_regressions.py`<br>`tests/integration/test_execution_r4_regressions.py`<br>`tests/integration/test_execution_r5_regressions.py`<br>`tests/integration/test_a2_migrations.py` | 确定性P11安全重查，包括任意资源/报价解析失败，而非仅金额错误；新键及失效/重放/变意图负例；计划完整，未执行。 |
| A2-CKPT1-OBL03 | 是 | `tests/integration/test_execution_regressions.py`<br>`tests/integration/test_execution_r3_regressions.py`<br>`tests/integration/test_execution_r4_regressions.py`<br>`tests/integration/test_execution_r5_regressions.py`<br>`tests/integration/test_a2_migrations.py` | 可用候选完整持久接受事实；永久不可改删事件+非级联FK或明确DELETE保护防删操作，异常旧行隔离；P20不能靠doc承诺；计划完整，未执行。 |
| A2-CKPT1-OBL04 | 是 | `tests/integration/test_execution_regressions.py`<br>`tests/integration/test_execution_r3_regressions.py`<br>`tests/integration/test_execution_r4_regressions.py`<br>`tests/integration/test_execution_r5_regressions.py`<br>`tests/integration/test_a2_migrations.py` | claim/终局owner+version+合法state+锁后DB有效expiry；无新owner时旧worker过期也拒绝；UNKNOWN保持且不释放未知预算；计划完整，未执行。 |
| A2-CKPT1-OBL05 | 是 | `tests/integration/test_execution_regressions.py`<br>`tests/integration/test_execution_r3_regressions.py`<br>`tests/integration/test_execution_r4_regressions.py`<br>`tests/integration/test_execution_r5_regressions.py`<br>`tests/integration/test_a2_migrations.py` | sidecar不改七旧表、phase/seq CHECK、事件/节点UPDATE/DELETE保护、非法升级全数据和迁移登记保全，合法更新/测试自有清理兼容；计划完整，未执行。 |
| A2-CKPT1-OBL06 | 是 | `tests/integration/test_execution_regressions.py`<br>`tests/integration/test_execution_r3_regressions.py`<br>`tests/integration/test_execution_r4_regressions.py`<br>`tests/integration/test_execution_r5_regressions.py`<br>`tests/integration/test_a2_migrations.py` | 下游执行/查询完整原快照持久化比对；不一致UNKNOWN；不可变outbox、receipt_id/created_at稳定、UTC整数秒iat；缺B PENDING且无伪编码/SM3；计划完整，未执行。 |
| WF-A1-REGRESSION | 是 | `tests`<br>`README.md`<br>`tasks/workflow/runs/local-remediation-20261004/task-v1.md` | A1原全部unit/PG集成独立实跑并保留U1/P1—14/F1—5语义与根重建、非零升级断言；不硬编码旧测试计数；计划完整，未执行。 |
| WF-INDEPENDENT-PROBES | 是 | `tests`<br>`README.md`<br>`tasks/workflow/runs/local-remediation-20261004/task-v1.md` | 最终reviewer独立设计绕过/边界探针，保存本轮可复现源与实跑日志；worker不替reviewer选择唯一反例；计划完整，未执行。 |
| WF-QUALITY-CHECKS | 是 | `tests`<br>`README.md`<br>`tasks/workflow/runs/local-remediation-20261004/task-v1.md` | ruff check/format、diff、全unit/骨架/docs/PG实跑；新增目录显式纳入CI；缺库报错不skip；计划完整，未执行。 |
| WF-PY311-ENV | 是 | `tests`<br>`README.md`<br>`tasks/workflow/runs/local-remediation-20261004/task-v1.md` | 实际Python3.11、依赖安装/约束和真实PG验证；历史CI/本机3.14不能替代。本轮无授权触发远程CI，NOT_RUN不额外阻断但Python3.11本地必须验证 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。；计划完整，未执行。 |
| WF-RESOURCE-ISOLATION | 是 | `tests`<br>`README.md`<br>`tasks/workflow/runs/local-remediation-20261004/task-v1.md` | worker及reviewer各自独立project/唯一容器/DB/schema，记录归属label、来源、挂载/端口、普通DSN清除、安全目标；前后无关资源不变，清理仅owned；计划完整，未执行。 |
| WF-IMMUTABLE-BASELINE | 否（静态/控制核验） | `tests`<br>`README.md`<br>`tasks/workflow/runs/local-remediation-20261004/task-v1.md` | 检查001—003内容checksum、A1语义、合法更新、无B代码/依赖偷渡。必要接口兼容须主控确认 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。；计划完整，未执行。 |
| WF-DOCS-REPORT | 否（静态/控制核验） | `tests`<br>`README.md`<br>`tasks/workflow/runs/local-remediation-20261004/task-v1.md` | 报告tracked/untracked误措辞纠正，31ID→具体断言/函数/命令结果，README可复现初始化/worker/下游/测试/清理；真实网关缺B不可装配启动，CI不漏新测试 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。；计划完整，未执行。 |
| WF-SNAPSHOT-COVERAGE | 否（静态/控制核验） | `tests`<br>`README.md`<br>`tasks/workflow/runs/local-remediation-20261004/task-v1.md` | 主控/reviewer查完整tracked/untracked/deleted及契约SHA256，冻结开始/结束一致；无active writer才review，证据与报告指纹绑定；计划完整，未执行。 |
| B-01-CRYPTO | 是 | `tests/test_crypto_profile.py`<br>`tests/test_interop_vectors.py`<br>`tests/integration/test_sm2_interop.py` | 成熟SM2/SM3、ALG/typ/rawJWS/userID/DER-rs严格；标准向量及OpenSSL双向实跑，不改PKCE S256；计划完整，未执行。 |
| B-02-ENCODING | 是 | `tests/test_encoding.py`<br>`tests/test_crypto_profile.py` | 全原JSON/Unicode/类型/大小深度/词数边界及raw/JWS/DID/SDK入口，合法负delta仅明确字段；原两issue正式独立闭环；计划完整，未执行。 |
| B-03-IDENTITY | 是 | `tests/test_authorization.py`<br>`tests/integration/test_server_tls.py` | 默认did:web实际HTTPS/CA/目的/controller/SPKI/企业注册/拒redirect与未批准目标；不是全部仅注入字典；计划完整，未执行。 |
| B-04-TOKEN-POLICY | 是 | `tests/test_authorization.py`<br>`tests/test_exchange.py`<br>`tests/integration/test_verified_execution.py` | 根/两级子各维收窄、空/缺约束拒、完整AS快照与A权限链真实绑定；计划完整，未执行。 |
| B-05-INVOKE-PROOF | 是 | `tests/test_authorization.py`<br>`tests/integration/test_verified_execution.py` | 原body/holder/endpoint/tenant/task/版本/业务键/proof拒绝，静态验证与最终接受分离，零新增状态；计划完整，未执行。 |
| B-06-CODE-OIDC | 是 | `tests/test_code_exchange.py`<br>`tests/test_login_consent.py`<br>`tests/integration/test_login_consent.py`<br>`tests/integration/test_consent_final_decision.py` | 登录、state/nonce/redirect/S256/CSRF/cookie/code一次性；政策/TX/所有晚锁时效全部触发与变体；计划完整，未执行。 |
| B-07-ROOT-ISSUANCE | 是 | `tests/integration/test_code_service.py` | 同task永久唯一根，code消费/根/proof/签名快照同txn；双code10轮，原数据不清零；计划完整，未执行。 |
| B-08-DELEGATION | 是 | `tests/integration/test_exchange_service.py` | 父/接收者/完整链可信，签发不占预算；同key/失响应/真进程恢复，撤销/到期/key停用retry不复活；计划完整，未执行。 |
| B-09-DYNAMIC-STATE | 是 | `tests/integration/test_key_rotation.py`<br>`tests/integration/test_consent_final_decision.py`<br>`tests/integration/test_verified_execution.py` | AS/执行/撤销统一锁序、锁后DBclock、完整祖先/key；内省active非永久许可；计划完整，未执行。 |
| B-10-HTTP-TLS | 是 | `tests/test_http_request_limits.py`<br>`tests/integration/test_http_boundaries.py`<br>`tests/integration/test_server_tls.py` | 全路由格式/媒体/重复头与body/大小/超时/认证/角色/会话拒绝；固定HTTPS/真TLS/脱敏/无生产旁路；计划完整，未执行。 |
| B-11-RESULT-READ | 是 | `tests/test_result_read_verifier.py`<br>`tests/test_query_contract.py` | 真实专用query签验/精确DTO与权限投影；不伪invoke字段。A最终动态查询实现留A2.2且文档不可伪PASS；计划完整，未执行。 |
| B-12-EVIDENCE-RECEIPT | 是 | `tests/test_receipt.py`<br>`tests/test_receipt_paths.py`<br>`tests/integration/test_evidence_binding.py`<br>`tests/integration/test_verified_execution.py` | 受控原材料暂存/接受关联、独立AS/GW历史信任、真实规范投影/签验负例；持续outbox签发/导出留后段；计划完整，未执行。 |
| B-13-ROTATION-INTEROP | 是 | `tests/integration/test_key_rotation.py`<br>`tests/integration/test_sm2_interop.py` | AS/client/GW用途与生命周期、旧key历史验证及新调用停用；OpenSSL/源与非editable wheel真互验；计划完整，未执行。 |
| B-14-DB-FAILURES | 是 | `tests/integration/test_rollback.py`<br>`tests/integration/test_evidence_binding.py` | 真实DB故障/锁timeout/终止backend/serialization失败关闭和原子回滚，错误不误标坏材料永久隔离；计划完整，未执行。 |
| B-15-CONCURRENCY-TEST-EFFICACY | 是 | `tests/integration/test_execution_concurrency.py`<br>`tests/unit/test_execution_concurrency_oracle.py`<br>`tests/integration/test_consent_final_decision.py` | 原全部竞争组各10轮，独立连接+可达同步、目标锁/PID/SQLSTATE/负控，不吞异常假PASS；计划完整，未执行。 |
| B-16-A1-REGRESSION | 是 | `tests/integration/test_accept_core.py`<br>`tests/integration/test_invariants.py`<br>`tests/integration/test_state_checks.py`<br>`tests/integration/test_concurrency.py`<br>`tests/integration/test_rollback.py`<br>`tests/integration/test_rejects.py`<br>`tests/integration/test_isolation.py`<br>`tests/unit/test_input_validation.py` | 全A1 U1/P1—14/F1—5与原5probe/等价更强升级，001—003历史checksum，原默认accept API；计划完整，未执行。 |
| B-17-B-SUITE-QUALITY | 是 | `tests` | fresh3.11锁安装、完整source/wheel非集成SDK/PG/OpenSSL/TLS/demo/lint/format及全文测试效力/许可维护审读；计划完整，未执行。 |
| B-18-RESOURCE-ISOLATION | 是 | `tests/fixtures/isolation.py` | 每worker/reviewer独占owner/容器/project/DB/schema/缓存，普通DSN清除、精确清理、原资源前后核对；计划完整，未执行。 |
| B-19-CONTRACT-MERGE | 是 | `tests/integration/test_verified_execution.py`<br>`tests/test_query_contract.py` | freeze且实际实现invoke bundle/query/evidence/seq投影，调用方一致，原A2.1默认/checked路径不丢；计划完整，未执行。 |
| B-20-MIGRATION-MERGE | 是 | `tests/integration/test_lineage_migrations.py`<br>`tests/integration/test_migrations.py` | 空库/common前缀/A-origin/B-origin合法升级、非零撤销证据、全部registry及失败原子性、重复no-op；计划完整，未执行。 |
| B-21-SHARED-FILE-MERGE | 是 | `.github/workflows/ci.yml`<br>`pyproject.toml`<br>`tests/integration/conftest.py` | README/init/fixtures/conftest/deps/CI/migrate语义整合与完整manifest，不覆盖任何一侧功能；计划完整，未执行。 |
| B-22-ORIGINAL-GOAL | 否（静态/控制核验） | `docs/acceptance.md` | 全M/SEC/CON/REC/AUD/E2E/ENG逐项真实等级/后段责任映射；不拿模块合并候选当比赛完成；计划完整，未执行。 |
| B-23-HANDOFF-REPRODUCIBILITY | 是 | `README.md`<br>`tests/demo_b_flow.py`<br>`tests/integration/test_server_tls.py` | README/手册/升级/初始化/角色/key/合成demo可复现，准确当前版本/限制，不复制B旧main未实现文字；计划完整，未执行。 |
| B-24-FINAL-BINDING | 否（静态/控制核验） | `tasks/workflow/runs/local-remediation-20261004/task-v1.md` | 完整candidate/契约起止snapshot、每批receipt/native停止与完整独立报告/issue闭环；计划完整，未执行。 |
| BR-01-CONSENT-FINAL | 是 | `tests/test_code_exchange.py`<br>`tests/test_login_consent.py`<br>`tests/integration/test_login_consent.py`<br>`tests/integration/test_consent_final_decision.py` | policy晚锁跨request/session到期两类各10轮零code/event/approved；client key/DID耗时不漏最终期限；core，test_consent_final_decision.py；计划完整，未执行。 |
| BR-02-HTTP-REJECTION | 是 | `tests/test_http_request_limits.py`<br>`tests/integration/test_http_boundaries.py`<br>`tests/integration/test_server_tls.py` | 全挂载路径65536/65537、分块/中断/格式/媒体拒绝4xx；DB503/真实内部500准确，无效果/原敏感材料不回显；http，test_http_request_limits.py+integrator真TLS；计划完整，未执行。 |
| BR-03-PRIVATE-PATHS | 是 | `tests/test_private_file_primitives.py`<br>`tests/test_server_private_files.py` | FIFO/socket/directory/file及parent link/危险祖先权限/竞态拒绝，独占不覆盖、多umask真实CLI，所有owned子进程退出；private+integrator；计划完整，未执行。 |
| BR-04-LINEAGE-HISTORY | 是 | `tests/integration/test_lineage_migrations.py`<br>`tests/integration/test_migrations.py` | A001—006/B004—009原字节与编号不变，原registry旧行全部字段含applied_at保全，sidecar来源可核验；core；计划完整，未执行。 |
| BR-05-LINEAGE-ATOMIC | 是 | `tests/integration/test_lineage_migrations.py`<br>`tests/integration/test_migrations.py` | 未知/错filename/checksum/缺中间/混合/伪登记/孤立schema失败前后全业务/legacy+sidecar registry不变，并发迁移/真实中断/重复升级；core+reviewer；计划完整，未执行。 |
| BR-06-REAL-PERMISSIONS | 是 | `tests/test_authorization.py`<br>`tests/test_exchange.py`<br>`tests/integration/test_verified_execution.py` | 真AS根→两级子→完整snapshot→现有四工具接受/执行；改token/path/scope/holder/SPKI/resources拒、各祖先账本/下游效果正确；core+integrator；计划完整，未执行。 |
| BR-07-QUERY-DTO | 是 | `tests/test_result_read_verifier.py`<br>`tests/test_query_contract.py` | 单一subject/method/query字段，真实签验与完整权限/evidence绑定；无tool/key虚字段/不预留不执行，下游动态查询后段明确不计完成；core；计划完整，未执行。 |
| BR-08-EVIDENCE-BINDING | 是 | `tests/test_receipt.py`<br>`tests/test_receipt_paths.py`<br>`tests/integration/test_evidence_binding.py`<br>`tests/integration/test_verified_execution.py` | 可信暂存不可改删、raw/digest/ref/当前proof精确关联，接受同txn first/retry独立link，注入失败proof/计数/关联全回滚，旧opaque材料不补造；core；计划完整，未执行。 |
| BR-09-RECEIPT-PROJECTION | 是 | `tests/test_receipt.py`<br>`tests/test_receipt_paths.py`<br>`tests/integration/test_evidence_binding.py`<br>`tests/integration/test_verified_execution.py` | 真A outbox材料phase/seq/节点集合验证后投影唯一v1，B规范+真实签验向量；未知字段/错seq/重复/错delta拒；原ID/iat/PENDING材料不变；core；计划完整，未执行。 |
| BR-10-IMPORT-PROVENANCE | 否（静态/控制核验） | `.github/workflows/ci.yml`<br>`pyproject.toml`<br>`tests/integration/conftest.py` | 精确import-map及固定B blob/当前A hash，不覆盖A ledger.service/001—006/全部旧测试或原报告，全部增删rename/mode列入manifest；core+controller；计划完整，未执行。 |
| BR-11-CLEAN-CANDIDATE | 是 | `tests` | 整合后freshsource及非editable wheel、空/两legacy升级、全A/B套件、实际demo/TLS/README；CI配置显式包含所有新目录，远程未授权不触发；integrator+reviewer；计划完整，未执行。 |
| BR-12-WORKFLOW-BARRIER | 否（静态/控制核验） | `tasks/workflow/runs/local-remediation-20261004/task-v1.md` | 真人读回/所有包与实际plan版本、真实NEW模型ID/资源、每批双开工门/worker门/freeze和最终require-accepted门；结构检查不替代语义；controller+reviewer；计划完整，未执行。 |

## 5. 历史原件、等价重建与独立探针

独立 SHA 校验确认主控复制的 A2 r8/B r2 共27个 Python 文件与原路径字节一致；A1三份文件另行核对也一致，合计30个文件，详细逐项值见 `independent-static-checks.json`。A1“原5探针”是前两文件中的4+1测试，不是5个文件；第三份非零升级探针额外保留。

包的“原件只读 → 自有副本 → 保留原失败 → 保存适配diff/逐项等价理由 → fresh reviewer 实跑”方法充分，且可实际检验：

- 合法 tuple/list：只允许去掉容器类型导致的过严拒绝预期，成功分支要继续断言完整 quote/意图/键/金额、唯一效果、全祖先账本及 event/outbox。结构内容错配仍 UNKNOWN，不能泛化成任意 iterable 通过。
- B 老竞争探针 `test_r1_races_current.py::contend` 在每次 `store.lock_principals` 调用都 barrier；当前 code/exchange 在事务末再次检查 principal，新重复调用会与另一线程持锁/等待构成不可达 barrier。等价副本可以只在每个目标 backend 首次入口同步，但须记录实际独立 PID、锁表/query/阻塞者、两参与者结果、DBclock/期限、10轮完整状态与合法/非法控制，不能把同步简单删除或把 timeout 当通过。
- A1 `test_upgrade_nonzero.py` 硬编码仅升级到002，且绑定 `ag_review_upgrade` 固定库名。原件在独占本轮实例中运行并保留过时期待失败；等价本轮版本必须覆盖非零70000/1预留与撤销/证据、七旧表全部列行、完整旧registry含 applied_at、空库/两legacy来源/重复no-op/非法失败原子性。固定测试库名只能存在于本轮独占容器，不能改为连接原共享库。
- 原探针硬编码 `/evidence/logs`、plugin imports、固定库名均是 runner 装配事项：可在本轮独占 mount/副本解决，原源码不改。每次适配要区分环境装配修正和安全断言变化。
- 未找回的云端最终反例必须明确标为新构建；按上一轮报告与 task-v1 的五项触发重建，再由新 reviewer 另行设计变体。不能将新日志描述为云端原件恢复，不能用找到的27文件数量推导“历史已全部覆盖”。无法等价补齐的必需义务仍 BLOCKED，不合并。

包已经明确禁止 skip/xfail、宽泛异常、删除case及降低断言，且最终 reviewer 自选探针不能由 worker 精选例子取代。历史缺口此时是有检查方法的实施验证工作，**不是因为尚未实跑就判包 FAIL/BLOCKED**。

## 6. 环境、source/wheel、角色和矩阵要求

资源隔离计划充分：worker 与 reviewer 不同owner、独立 Python3.11/Linux amd64 与 PG16/网络、分离源码与日志挂载；网关/下游不同DB与事务域；普通部署DSN清除；只清理自建资源；不连接/停止 agent-guard-a2-pg 与 verivote。最终证据需保留 owner、容器完整ID、image/版本、mount/project/schema/cache、创建与清理记录；不把 inventory 一致说成业务DB内容比较。

source 与非editable wheel计划充分且必须落实：fresh原锁安装/pip check，分别跑非集成、PG、SDK/OpenSSL/TLS/demo、迁移与新增/历史回归。wheel环境不能可见或通过PYTHONPATH导入 src；需保存 `agent_guard.__file__`、相关子模块路径、distribution元数据/安装路径、无editable证据，并在真实worker子进程中验证同一来源。SQL要从安装包数据目录实取并核hash，在空库、A-origin、B-origin重复升级/失败场景执行。源码只读挂载不免除安装副本一致性检查。现有fixture/helpers可位于测试副本，不能使被测 agent_guard 偷回源码树。

角色独立与冻结计划充分：single worker停写/测试进程退出后主控核所有权、只读基线及候选全清单，再 fresh reviewer验收；包审 reviewer 不继续充当本轮实现验收 reviewer。tool请求模型与有效元数据分开，本轮 approved addendum允许未暴露有效字段为UNKNOWN，不伪造原旧门通过。

所有67项与M1—M13、SEC/CON/REC/AUD/E2E/ENG均需明确本段与后段边界；真实B签验已在本段，不能沿旧A“缺B”一律排除。最终动态query/公开网关、持续outbox签发、独立锚定/完整端到端/规模实验仍留对应后段，不允许把局部真实签验当完整A2或比赛完成。

## 7. 本轮检查与未执行边界

本轮仅执行读取、源码/测试静态查证、Git只读清单、SHA-256/JSON ID核验及自有报告写入。`independent-static-checks.json` 保存67/60计数、ID差集为空、原件哈希及Git状态；源码/SQL/正式测试没有执行或修改。

Ruff、pytest、PG、真实进程恢复/并发/DB故障、SM2签验、OpenSSL、TLS、README/demo、source/wheel、远端CI均 **NOT_RUN（PACKAGE_REVIEW阶段不应运行）**。既有报告中结果只作历史触发/标准的核对，不作为本轮通过证据。没有打开/消费部署凭据或连接既有DB，也没有要清理的本轮业务资源。

## 8. 问题台账与交主控动作

| 项目 | 状态 | 主控动作 |
| --- | --- | --- |
| 本轮包级设计阻断 | 无 | 保留当前四文件冻结版本与本完整报告，记录 PACKAGE_READY |
| 五个原代码/测试问题 | OPEN，未实施、未关闭 | 已有真人适配授权范围内派唯一worker；按完整67/60矩阵自查，完成后停止 |
| projection提前拒绝错误类型 | 已静态确认的兼容注意项，非包阻断 | 按第3节精确更新测试，或若选择改projection接口先重新定范围；禁止宽泛catch |
| initial requirements旧哈希 | 初始快照与正式冻结的前置差别，非审查漂移 | 明确正式package-freeze覆盖初始requirements；只读其余基线不变 |
| 云端原证据不全 | 历史缺口继续保留 | 依第5节等价重建并fresh独立执行；无法补齐则实施验收BLOCKED |
| Git保护/代码所有者review | 后段发布条件，未由本轮核实 | 验收通过后重新核远端；不能正常满足则留可审PR报告用户，不管理员绕过 |

主控应核读本报告和独立哈希记录，再记录本轮授权/包审/所有权/运行回执对应关系后派发。实施者只能 FIXED_PENDING_REVIEW / READY_FOR_REVIEW，不能关闭问题；停写与完整冻结后另开新独立验收。最终阶段通过仍须完整证据核验和正常Git保护才可合并。

**本 reviewer 到此停止；PACKAGE_READY 不是代码 ACCEPTED，也不是无缺陷保证。**
