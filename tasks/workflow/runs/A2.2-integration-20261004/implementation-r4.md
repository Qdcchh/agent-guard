# A2.2 correction r4 implementation and complete self-check

Status: **READY_FOR_REVIEW**, both P2 corrections **FIXED_PENDING_REVIEW**. This is worker self-check, not independent acceptance. Original95 requirements/88 running obligations (inherited67/60) are preserved; no requirements/old tests/SQL/dependencies/CI/controller files were edited. Requested model gpt-6.1-sol/medium; effective backend metadata UNKNOWN. Later A2.3/fullA2/allA3 authorization remains with the controller; this worker only implemented A2.2 correction-r1.

## Candidate and corrections

Branch codex/a2.2-integration; HEAD280022e9d7005daa8d551ba0e4c52e3228e3add5. The284-entry final manifest matches the current tree and independent source copy byte/mode;256 paths outside the28 allowed worker paths match pre-worker-r4. Only6 allowed paths changed in r4: execution/query.py, fixtures/gateway.py, integration/test_gateway_query.py, HANDOFF.md, A2-report.md and A2.2 stage outline. Product writes stopped before final full suites; subsequent writes were only this owned evidence directory. Semantic Git index SHA means git ls-files --stage -z; it matches the pre baseline, staged diff remains empty. No raw-index baseline exists and no raw-cache equality is claimed. No add/reset/clean/commit/push/PR/merge.

- A22-R1-RESULT-ERROR: terminal trusted projection locally converts only ExecutionErrorCode.DOWNSTREAM_INCONSISTENT to EvidenceError/503. Unrelated LEASE_LOST and RuntimeError stay500 without marker leakage.16 actual persisted-result faults cover five DTO shapes×wrong operation/wrong variant/array plus wrong order total;503 causes full proof/business rollback. Repair uses the same unused proof successfully, then identical replay409; all business/downstream rows remain unchanged, only one successful proof is added. The pre-fix strict4 probe preserves3 failures/1 pass.
- A22-R1-SHORT-WINDOW: real AS-signed parent exp and real current seconds bound each child TTL with an actual margin. Existing80 lock/deadline variants plus80 forced real-second-crossing variants run in each final source/wheel PG group. Actual AS claims and DB expiries are asserted; negative target windows retain the original held-operation lock and final DB clock, full all-ag/accepted-evidence/three-ds oracle/proof rollback. Root/mid expiry also implies leaf/token expiry; no claim of isolated expired ancestor with a valid child token. Pre-fix10 genuine-AS defect observations are separate from acceptance.
- Context16 same-shape corruption regressions plus expired-original-proof/fresh-query positive remain intact and rerun. Existing protocol65536-byte response limit and trusted-material503 boundary remain unchanged. PENDING/null projection is preserved. Query has no budget/calls/lease/event/outbox/downstream effect; invoke still only accepts and existing internal worker executes.

## Real runs and environment

Linux amd64 under Rosetta, Python3.11 UID501; independent owned PG16 and gateway/downstream databases. Ordinary production DSN empty; explicit owned test DSNs only. Exact runtime/dev locks and PEP517 setuptools80.9.0, no new dependency. Installed noneditable wheel has91 members;73 package files+14 SQL match current source exactly. No source shadow. Source/wheel full groups had no module observer. Later read-only sitecustomize observer recorded real __main__.__spec__.name/module paths and PID before real SIGKILL; all observed locations match their environment, then prior absent state was restored. Module-start observation is not business-completion proof; actual TLS/DB/process assertions are separate.

| Final actual group | P/F/E/S | Exit |
| --- | --- | --- |
| source-final-r4-nonintegration | 1022/0/0/0 | 0 |
| source-final-r4-integration | 1930/0/0/0 | 0 |
| wheel-final-r4-nonintegration | 1022/0/0/0 | 0 |
| wheel-final-r4-integration | 1930/0/0/0 | 0 |
| historical-a2-original | 482/0/0/0 | 0 |
| historical-b-equivalent-r3 | 250/0/0/0 | 0 |
| a1-current-unit | 70/0/0/0 | 0 |
| a1-current-pg | 87/0/0/0 | 0 |
| a1-original-ag_review_probe | 4/0/0/0 | 0 |
| a1-original-ag_review_f2 | 1/0/0/0 | 0 |
| a1-upgrade-equivalent | 1/0/0/0 | 0 |
| source-a22-independent | 335/0/0/0 | 0 |
| wheel-a22-independent-r2 | 335/0/0/0 | 0 |
| source-independent | 26/0/0/0 | 0 |
| wheel-independent | 26/0/0/0 | 0 |
| source-local-boundary-original | 7/0/0/0 | 0 |
| wheel-local-boundary-original | 7/0/0/0 | 0 |
| oracle-controls-60 | 60/0/0/0 | 0 |

Both literal old README flows and the new gateway config-init/check/run flow ran in source and wheel, with default CA/hostname verification and real HTTPS child processes. Four tools, real worker/gateway crash/restart, accepted/terminal/null results, CLI demos, migrations/repeat/rollback, original and equivalent controls, clean-copy154 local links and30 goal rows, Ruff check/format/diff/import/build/install/pip-check/OpenSSL/provenance all have individual command/log/XML refs. source PG1280.508s (~21.34min), wheel1284.463s (~21.41min); total CI25min timeout headroom is an observed risk only, remote CI not run or predicted and .github unchanged.

The first wheel335 observation overlapped extras pytest cache. It is retained but excluded as final isolation proof; wheel-independent-r2 has its own exact test copy, cwd/cache/HOME/TMPDIR/database, runs after both earlier wrappers ended, and passes335. The full source/wheel formal groups are uninstrumented; independent probes/witnesses are explicitly instrumented and do not substitute for them.

## Preserved failures and limits

| Original attempt | P/F/E/S | Exit |
| --- | --- | --- |
| a1-original-ag_review_upgrade | 0/1/0/0 | 1 |
| before-fix-repro_result | 1/3/0/0 | 1 |
| candidate-audit-index-raw-failure | 0/0/0/0 | 1 |
| format-owned-r4-r2 | 0/0/0/0 | 2 |
| historical-b-equivalent-r2 | 244/6/0/0 | 1 |
| historical-b-equivalent | 245/5/0/0 | 1 |
| historical-b-original | 218/28/4/0 | 1 |
| install-system | 0/0/0/0 | 1 |
| lint-owned-r4 | 0/0/0/0 | 1 |
| prepare-matrix-initial-error-confirmation | 0/0/0/0 | 1 |
| probe_oracle_scheduling_repeated-original-current | 0/0/0/0 | 1 |

All original failures and actual exits are retained. Historical A1 upgrade and B original assertions reflect old migration/namespace/barrier/config-wrapper expectations; equivalent copies preserve business assertions and adapt only the current namespaces/migration set, initial per-PID barrier, and FileExistsError cause inside ConfigError. Final B equivalent-r3 reruns all250 unchanged parameters/assertions in a fresh namespace. Failed equivalents r1/r2 reflect the owned Linux /review private-path mode and reused legacy schema; loader privacy was not weakened. Only the approved owned mount changed777→700; host/Linux UID/mode differences are recorded. See historical-adaptations.diff, r3 namespace diff and harness-errors-r4.md.

Initial install mkdir, Ruff cache/CLI placement, wrong index hash domain, template preparation failures remain separate harness evidence. Final-seal-r1 and final-seal-r2 also exited1 before producing an index: regenerated AST excerpts required DSN string redaction, then raw JSON escaping required decoded-field scanning. Both failures and the failed catalog receipt are retained; the corrected semantic scan/index validation succeeds without changing original source or test assertions. Earlier r3 missing collection XML remains an unrecoverable historical fact; no replacement XML is attributed to it here and no old result is reused. Historical P11 scheduling root cause remains bounded/unknown; current scheduling/60 oracle negative controls and original failures are preserved rather than claiming a retrospective cause.

JUnit/log/derived evidence private credentials were semantically redacted with original→final SHA/replacement counts and unchanged XML cases/status/timing/JSON structure receipts. This is test-harness evidence privacy, not a finding that public HTTP leaked secrets. Exact source/probe originals are not rewritten. Generated assertion-catalog DSN/compact string excerpts are redacted; byte-bound source SHA and original line/assertions remain authoritative, with a separate catalog privacy receipt. Full request/proof/private-key credentials and full DSNs are absent from shareable execution evidence. Old reviewer518 and worker-r3 424 indexed raw artifacts retain their original hashes. No performance50-clients/10k, deployment or A2.3/A3 implementation is claimed.

## Complete95 semantic self-check rows

Each row below retains its entire frozen behavior. Detailed exact functions, assertion text/line/decorators/helper calls, actual parameterized nodes, command exits/JUnit and SHA refs are normalized once in requirements-matrix.json → test-function-registry.json → assertion-catalog.json/run-registry.json. Each referenced final running group was checked for exit0 and zero failure/error/skip. Static obligations reference actual scope/docs/cleanup receipts. Controller final formal-report/link update and freeze, then a fresh independent reviewer, remain pending.

| ID | Frozen behavior | Actual current self-check |
| --- | --- | --- |
| A2-P01 | 三层订单70000/1成功，唯一真实下游效果；根/中间/叶reserved归0，settled70000/1；RESERVE和SETTLE各一，终态/outbox一致 | PASS_SELF_CHECK; 1 exact function groups; matrix JSON ID |
| A2-P02 | 下游持久终局拒绝，FAILED、全路径释放不结算，RELEASE一条；该键不能迟到成功 | PASS_SELF_CHECK; 2 exact function groups; matrix JSON ID |
| A2-P03 | 读取/通知金额0但次数预留结算或释放正确；通知持久效果最多一次，读结果固定 | PASS_SELF_CHECK; 3 exact function groups; matrix JSON ID |
| A2-P04 | 接受提交前不得执行；提交后真独立子进程终止/重新启动，从持久状态恢复而非finally补救；保留pid/同步与DB断言证据 | PASS_SELF_CHECK; 4 exact function groups; matrix JSON ID |
| A2-P05 | 下游订单已提交响应丢失→UNKNOWN额度保留；同键恢复唯一订单、一次结算 | PASS_SELF_CHECK; 1 exact function groups; matrix JSON ID |
| A2-P06 | 下游成功、网关终局前崩溃；恢复无重复效果/账本/终局 | PASS_SELF_CHECK; 2 exact function groups; matrix JSON ID |
| A2-P07 | 终局事务节点/事件/outbox中途注入异常；全状态/计数/事件/outbox原子回滚，之后可恢复 | PASS_SELF_CHECK; 1 exact function groups; matrix JSON ID |
| A2-P08 | 查无结果后旧请求迟到成功；不释放，最终唯一效果和SETTLE | PASS_SELF_CHECK; 1 exact function groups; matrix JSON ID |
| A2-P09 | 双恢复者、过期旧worker竞争，独立连接barrier/event每组10轮；终态不被覆盖、一个终局/一个outbox | PASS_SELF_CHECK; 33 exact function groups; matrix JSON ID |
| A2-P10 | 接受后祖先撤销/过期/key停用，内部恢复可完成原意图；外部接受重试仍拒绝；真实授权查询本段须完整独立验证 | PASS_SELF_CHECK; 6 exact function groups; matrix JSON ID |
| A2-P11 | 当前报价改/删后的已有意图使用原成本/快照；新键要求有效报价；确定性miss→另accept→报价消失→安全重查命中；变grant/holder/参数、撤销、proof重放仍拒绝 | PASS_SELF_CHECK; 5 exact function groups; matrix JSON ID |
| A2-P12 | 下游金额/意图/完整快照错配且可能有效果→UNKNOWN保留预算，无伪成功/释放 | PASS_SELF_CHECK; 55 exact function groups; matrix JSON ID |
| A2-P13 | 根/中间不足或次数耗尽及接受/结算/恢复并发，10轮、全祖先不超限不负数、不反向锁/死锁无界 | PASS_SELF_CHECK; 12 exact function groups; matrix JSON ID |
| A2-P14 | 下游同键同意图和冲突、订单/通知均防重复，执行/查询无或错独立服务凭据拒绝、零泄漏/效果；不能只藏端口 | PASS_SELF_CHECK; 9 exact function groups; matrix JSON ID |
| A2-P15-CORE | 四个完整工具ID/版本，重复JSON键/SKU、bool/负/浮点/溢出数量、缺/空集合、scope不足、跨租户/关联错/URL路径注入、快照/祖先包含错等分层负例，零预留/效果。可信fixture授权不是真实验签 | PASS_SELF_CHECK; 47 exact function groups; matrix JSON ID |
| A2-P19 | 001及003真实非零预留/撤销/证据升级到004，七旧表全行及完整迁移登记在非法升级时不变；合法重复迁移no-op；旧材料不足sidecar隔离保预算，不能补当前报价执行 | PASS_SELF_CHECK; 28 exact function groups; matrix JSON ID |
| A2-P20 | 直接SQL改意图/成本/证据、删除重建路径/操作、改删事件/节点、阶段seq绕过、非法状态/双终局拒绝，旧账本不变；合法预算/撤销/状态UPDATE可用 | PASS_SELF_CHECK; 45 exact function groups; matrix JSON ID |
| A2-CKPT1-OBL01 | 候选前schema/静态授权/可信集合，不要求当前报价存在；命中原快照关联+当前权限后仍A1 accept锁后复核/proof/意图 | PASS_SELF_CHECK; 41 exact function groups; matrix JSON ID |
| A2-CKPT1-OBL02 | 确定性P11安全重查，包括任意资源/报价解析失败，而非仅金额错误；新键及失效/重放/变意图负例 | PASS_SELF_CHECK; 16 exact function groups; matrix JSON ID |
| A2-CKPT1-OBL03 | 可用候选完整持久接受事实；永久不可改删事件+非级联FK或明确DELETE保护防删操作，异常旧行隔离；P20不能靠doc承诺 | PASS_SELF_CHECK; 59 exact function groups; matrix JSON ID |
| A2-CKPT1-OBL04 | claim/终局owner+version+合法state+锁后DB有效expiry；无新owner时旧worker过期也拒绝；UNKNOWN保持且不释放未知预算 | PASS_SELF_CHECK; 34 exact function groups; matrix JSON ID |
| A2-CKPT1-OBL05 | sidecar不改七旧表、phase/seq CHECK、事件/节点UPDATE/DELETE保护、非法升级全数据和迁移登记保全，合法更新/测试自有清理兼容 | PASS_SELF_CHECK; 28 exact function groups; matrix JSON ID |
| A2-CKPT1-OBL06 | 下游执行/查询完整原快照持久化比对；不一致UNKNOWN；不可变outbox、receipt_id/created_at稳定、UTC整数秒iat；缺B PENDING且无伪编码/SM3 | PASS_SELF_CHECK; 51 exact function groups; matrix JSON ID |
| WF-A1-REGRESSION | A1原全部unit/PG集成独立实跑并保留U1/P1—14/F1—5语义与根重建、非零升级断言；不硬编码旧测试计数 | PASS_SELF_CHECK; 97 exact function groups; matrix JSON ID |
| WF-INDEPENDENT-PROBES | 最终reviewer独立设计绕过/边界探针，保存本轮可复现源与实跑日志；worker不替reviewer选择唯一反例 | PASS_SELF_CHECK; 4 exact function groups; matrix JSON ID |
| WF-QUALITY-CHECKS | ruff check/format、diff、全unit/骨架/docs/PG实跑；新增目录显式纳入CI；缺库报错不skip | PASS_SELF_CHECK; 11 exact function groups; matrix JSON ID |
| WF-PY311-ENV | 实际Python3.11、依赖安装/约束和真实PG验证；历史CI/本机3.14不能替代。本轮无授权触发远程CI，NOT_RUN不额外阻断但Python3.11本地必须验证 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。 | PASS_SELF_CHECK; 4 exact function groups; matrix JSON ID |
| WF-RESOURCE-ISOLATION | worker及reviewer各自独立project/唯一容器/DB/schema，记录归属label、来源、挂载/端口、普通DSN清除、安全目标；前后无关资源不变，清理仅owned | PASS_SELF_CHECK; 7 exact function groups; matrix JSON ID |
| WF-IMMUTABLE-BASELINE | 检查001—003内容checksum、A1语义、合法更新、无B代码/依赖偷渡。必要接口兼容须主控确认 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。 | PASS_SELF_CHECK; static audit; matrix JSON ID |
| WF-DOCS-REPORT | 报告tracked/untracked误措辞纠正，31ID→具体断言/函数/命令结果，README可复现初始化/worker/下游/测试/清理；真实网关缺B不可装配启动，CI不漏新测试 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。 | PASS_SELF_CHECK; static audit; matrix JSON ID |
| WF-SNAPSHOT-COVERAGE | 主控/reviewer查完整tracked/untracked/deleted及契约SHA256，冻结开始/结束一致；无active writer才review，证据与报告指纹绑定 | PASS_SELF_CHECK; static audit; matrix JSON ID |
| B-01-CRYPTO | 成熟SM2/SM3、ALG/typ/rawJWS/userID/DER-rs严格；标准向量及OpenSSL双向实跑，不改PKCE S256 | PASS_SELF_CHECK; 20 exact function groups; matrix JSON ID |
| B-02-ENCODING | 全原JSON/Unicode/类型/大小深度/词数边界及raw/JWS/DID/SDK入口，合法负delta仅明确字段；原两issue正式独立闭环 | PASS_SELF_CHECK; 42 exact function groups; matrix JSON ID |
| B-03-IDENTITY | 默认did:web实际HTTPS/CA/目的/controller/SPKI/企业注册/拒redirect与未批准目标；不是全部仅注入字典 | PASS_SELF_CHECK; 22 exact function groups; matrix JSON ID |
| B-04-TOKEN-POLICY | 根/两级子各维收窄、空/缺约束拒、完整AS快照与A权限链真实绑定 | PASS_SELF_CHECK; 29 exact function groups; matrix JSON ID |
| B-05-INVOKE-PROOF | 原body/holder/endpoint/tenant/task/版本/业务键/proof拒绝，静态验证与最终接受分离，零新增状态 | PASS_SELF_CHECK; 24 exact function groups; matrix JSON ID |
| B-06-CODE-OIDC | 登录、state/nonce/redirect/S256/CSRF/cookie/code一次性；政策/TX/所有晚锁时效全部触发与变体 | PASS_SELF_CHECK; 36 exact function groups; matrix JSON ID |
| B-07-ROOT-ISSUANCE | 同task永久唯一根，code消费/根/proof/签名快照同txn；双code10轮，原数据不清零 | PASS_SELF_CHECK; 5 exact function groups; matrix JSON ID |
| B-08-DELEGATION | 父/接收者/完整链可信，签发不占预算；同key/失响应/真进程恢复，撤销/到期/key停用retry不复活 | PASS_SELF_CHECK; 17 exact function groups; matrix JSON ID |
| B-09-DYNAMIC-STATE | AS/执行/撤销统一锁序、锁后DBclock、完整祖先/key；内省active非永久许可 | PASS_SELF_CHECK; 32 exact function groups; matrix JSON ID |
| B-10-HTTP-TLS | 全路由格式/媒体/重复头与body/大小/超时/认证/角色/会话拒绝；固定HTTPS/真TLS/脱敏/无生产旁路 | PASS_SELF_CHECK; 35 exact function groups; matrix JSON ID |
| B-11-RESULT-READ | 真实专用query签验/精确DTO与权限投影；不伪invoke字段。A最终动态查询实现留A2.2且文档不可伪PASS | PASS_SELF_CHECK; 8 exact function groups; matrix JSON ID |
| B-12-EVIDENCE-RECEIPT | 受控原材料暂存/接受关联、独立AS/GW历史信任、真实规范投影/签验负例；持续outbox签发/导出留后段 | PASS_SELF_CHECK; 24 exact function groups; matrix JSON ID |
| B-13-ROTATION-INTEROP | AS/client/GW用途与生命周期、旧key历史验证及新调用停用；OpenSSL/源与非editable wheel真互验 | PASS_SELF_CHECK; 6 exact function groups; matrix JSON ID |
| B-14-DB-FAILURES | 真实DB故障/锁timeout/终止backend/serialization失败关闭和原子回滚，错误不误标坏材料永久隔离 | PASS_SELF_CHECK; 20 exact function groups; matrix JSON ID |
| B-15-CONCURRENCY-TEST-EFFICACY | 原全部竞争组各10轮，独立连接+可达同步、目标锁/PID/SQLSTATE/负控，不吞异常假PASS | PASS_SELF_CHECK; 15 exact function groups; matrix JSON ID |
| B-16-A1-REGRESSION | 全A1 U1/P1—14/F1—5与原5probe/等价更强升级，001—003历史checksum，原默认accept API | PASS_SELF_CHECK; 97 exact function groups; matrix JSON ID |
| B-17-B-SUITE-QUALITY | fresh3.11锁安装、完整source/wheel非集成SDK/PG/OpenSSL/TLS/demo/lint/format及全文测试效力/许可维护审读 | PASS_SELF_CHECK; 669 exact function groups; matrix JSON ID |
| B-18-RESOURCE-ISOLATION | 每worker/reviewer独占owner/容器/project/DB/schema/缓存，普通DSN清除、精确清理、原资源前后核对 | PASS_SELF_CHECK; 7 exact function groups; matrix JSON ID |
| B-19-CONTRACT-MERGE | freeze且实际实现invoke bundle/query/evidence/seq投影，调用方一致，原A2.1默认/checked路径不丢 | PASS_SELF_CHECK; 13 exact function groups; matrix JSON ID |
| B-20-MIGRATION-MERGE | 空库/common前缀/A-origin/B-origin合法升级、非零撤销证据、全部registry及失败原子性、重复no-op | PASS_SELF_CHECK; 28 exact function groups; matrix JSON ID |
| B-21-SHARED-FILE-MERGE | README/init/fixtures/conftest/deps/CI/migrate语义整合与完整manifest，不覆盖任何一侧功能 | PASS_SELF_CHECK; 23 exact function groups; matrix JSON ID |
| B-22-ORIGINAL-GOAL | 全M/SEC/CON/REC/AUD/E2E/ENG逐项真实等级/后段责任映射；不拿模块合并候选当比赛完成 | PASS_SELF_CHECK; static audit; matrix JSON ID |
| B-23-HANDOFF-REPRODUCIBILITY | README/手册/升级/初始化/角色/key/合成demo可复现，准确当前版本/限制，不复制B旧main未实现文字 | PASS_SELF_CHECK; 1 exact function groups; matrix JSON ID |
| B-24-FINAL-BINDING | 完整candidate/契约起止snapshot、每批receipt/native停止与完整独立报告/issue闭环 | PASS_SELF_CHECK; static audit; matrix JSON ID |
| BR-01-CONSENT-FINAL | policy晚锁跨request/session到期两类各10轮零code/event/approved；client key/DID耗时不漏最终期限；core，test_consent_final_decision.py | PASS_SELF_CHECK; 36 exact function groups; matrix JSON ID |
| BR-02-HTTP-REJECTION | 全挂载路径65536/65537、分块/中断/格式/媒体拒绝4xx；DB503/真实内部500准确，无效果/原敏感材料不回显；http，test_http_request_limits.py+integrator真TLS | PASS_SELF_CHECK; 35 exact function groups; matrix JSON ID |
| BR-03-PRIVATE-PATHS | FIFO/socket/directory/file及parent link/危险祖先权限/竞态拒绝，独占不覆盖、多umask真实CLI，所有owned子进程退出；private+integrator | PASS_SELF_CHECK; 48 exact function groups; matrix JSON ID |
| BR-04-LINEAGE-HISTORY | A001—006/B004—009原字节与编号不变，原registry旧行全部字段含applied_at保全，sidecar来源可核验；core | PASS_SELF_CHECK; 28 exact function groups; matrix JSON ID |
| BR-05-LINEAGE-ATOMIC | 未知/错filename/checksum/缺中间/混合/伪登记/孤立schema失败前后全业务/legacy+sidecar registry不变，并发迁移/真实中断/重复升级；core+reviewer | PASS_SELF_CHECK; 28 exact function groups; matrix JSON ID |
| BR-06-REAL-PERMISSIONS | 真AS根→两级子→完整snapshot→现有四工具接受/执行；改token/path/scope/holder/SPKI/resources拒、各祖先账本/下游效果正确；core+integrator | PASS_SELF_CHECK; 29 exact function groups; matrix JSON ID |
| BR-07-QUERY-DTO | 单一subject/method/query字段，真实签验与完整权限/evidence绑定；无tool/key虚字段/不预留不执行，下游动态查询后段明确不计完成；core | PASS_SELF_CHECK; 8 exact function groups; matrix JSON ID |
| BR-08-EVIDENCE-BINDING | 可信暂存不可改删、raw/digest/ref/当前proof精确关联，接受同txn first/retry独立link，注入失败proof/计数/关联全回滚，旧opaque材料不补造；core | PASS_SELF_CHECK; 24 exact function groups; matrix JSON ID |
| BR-09-RECEIPT-PROJECTION | 真A outbox材料phase/seq/节点集合验证后投影唯一v1，B规范+真实签验向量；未知字段/错seq/重复/错delta拒；原ID/iat/PENDING材料不变；core | PASS_SELF_CHECK; 24 exact function groups; matrix JSON ID |
| BR-10-IMPORT-PROVENANCE | 精确import-map及固定B blob/当前A hash，不覆盖A ledger.service/001—006/全部旧测试或原报告，全部增删rename/mode列入manifest；core+controller | PASS_SELF_CHECK; static audit; matrix JSON ID |
| BR-11-CLEAN-CANDIDATE | 整合后freshsource及非editable wheel、空/两legacy升级、全A/B套件、实际demo/TLS/README；CI配置显式包含所有新目录，远程未授权不触发；integrator+reviewer | PASS_SELF_CHECK; 669 exact function groups; matrix JSON ID |
| BR-12-WORKFLOW-BARRIER | 真人读回/所有包与实际plan版本、真实NEW模型ID/资源、每批双开工门/worker门/freeze和最终require-accepted门；结构检查不替代语义；controller+reviewer | PASS_SELF_CHECK; static audit; matrix JSON ID |
| A2-P15 | 真实授权公开HTTP下全部非法参数、别名、重复JSON/SKU、bool/浮点、空缺集合、注入、跨租户/资源关联、scope/祖先快照错配：拒绝且零效果/零预留；完整原断言，不只分层CORE | PASS_SELF_CHECK; 12 exact function groups; matrix JSON ID |
| A2-P16 | 真实B验签公开调用缺/错token/proof、换body/holder/endpoint、盗token、重放拒绝；父私钥不能使用子token，零业务变化 | PASS_SELF_CHECK; 12 exact function groups; matrix JSON ID |
| A2-P17 | 真实result-read仅原tenant/task/subject/root/grant/holder/kid、当前权限；锁后TTL/全祖先撤销/停用；新proof并发/重放；查询无业务计数或下游/租约效果 | PASS_SELF_CHECK; 18 exact function groups; matrix JSON ID |
| A2-P21-HTTP | 真实受信CA HTTPS的正常四工具采购/读取/通知与查询，固定endpoint、202/error和重复返回当前状态；持续回执签名明确留A2.3，不将完整P21标PASS | PASS_SELF_CHECK; 5 exact function groups; matrix JSON ID |
| A22-01-REUSE | 复用真实InvocationVerifier/VerifiedExecution/ExecutionService；不复制SM2/SM3/编码/OAuth；生产装配只允许真实provider/evidence/execution | PASS_SELF_CHECK; 21 exact function groups; matrix JSON ID |
| A22-02-TRANSPORT | 可信ASGI https、固定两条POST路径；不从Host/Forwarded推htu，拒query/fragment变体、编码路径绕过、GET/未知/管理路径、Bearer/DPoP降级 | PASS_SELF_CHECK; 5 exact function groups; matrix JSON ID |
| A22-03-FRAMING | 请求/响应/头大小有界，拒重复敏感头、组合凭据、非法ASCII/CRLF、Content-Length/Transfer-Encoding歧义、压缩、错类型、断连、body过大/深度/重复键/NaN；不消耗业务预算 | PASS_SELF_CHECK; 9 exact function groups; matrix JSON ID |
| A22-04-INVOKE | 首次invoke202返回operation_id与真实status/receipt_status，事务提交后内部worker执行；HTTP不隐式启动业务或签名；已终态同键新proof仍202但status不伪RESERVED | PASS_SELF_CHECK; 5 exact function groups; matrix JSON ID |
| A22-05-QUERY-BUNDLE | 新增可信query bundle保留PermissionSource及opaque evidenceRef，保原canonical-result API兼容；不可从请求构造可信对象/自报权限 | PASS_SELF_CHECK; 11 exact function groups; matrix JSON ID |
| A22-06-QUERY-LOCKS | 真实PG锁序principals排序→task→root-leafgrants→operation；检查完整不可变授权链；不伪装invoke DTO或放宽A1purpose；与接受/恢复/撤销锁序兼容 | PASS_SELF_CHECK; 7 exact function groups; matrix JSON ID |
| A22-07-QUERY-OWNERSHIP | 查询仅原授权节点、holder/key、tenant/task/subject/root；当前权限仍覆盖原tool/params且原操作可核验；跨身份猜ID拒绝不泄露存在/内容 | PASS_SELF_CHECK; 3 exact function groups; matrix JSON ID |
| A22-08-QUERY-FINAL-CLOCK | 所有可能阻塞的证据/行读取/约束处理后最终DBclock_timestamp；重读已锁key/全祖先并检查token/proof及grantnotbefore/expiry；等待或latebinding超过TTL拒绝，事务完整回滚 | PASS_SELF_CHECK; 3 exact function groups; matrix JSON ID |
| A22-09-QUERY-REPLAY | 查询proof唯一kid/purpose/endpoint/jti并同事务operation/evidence关联；并发同proof最多一成功，10轮；失败不消耗proof，不覆盖首次证据 | PASS_SELF_CHECK; 2 exact function groups; matrix JSON ID |
| A22-10-QUERY-ZERO-COST | 读取RESERVED/EXECUTING/UNKNOWN/SUCCEEDED/FAILED合法状态；result仅可信持久事实，回执null/PENDING；不创建操作/事件/outbox、改预算/lease或执行下游，beforeafter全路径计数/业务行一致 | PASS_SELF_CHECK; 9 exact function groups; matrix JSON ID |
| A22-11-QUERY-EVIDENCE | query_binding在同事务验证真实raw/token/proof/body/context/source对应关系，换ref/错source/legacy不全拒绝；不把query写作invoke retry；优先ag_proofs关联无迁移 | PASS_SELF_CHECK; 15 exact function groups; matrix JSON ID |
| A22-12-QUERY-PERMISSION | 当前签名token、DB权限源与历史原操作所需资源/tool/收窄逐项一致；坏可信源/不完整链/缺原事实失败关闭，不能靠签名或缓存放行 | PASS_SELF_CHECK; 14 exact function groups; matrix JSON ID |
| A22-13-DYNAMIC-RACES | 真实撤销/key停用vsquery/accept线性化及锁等待TTL、lateDB依赖；独立连接event/barrier每组10轮、捕获全部异常和完成，负控证明触发目标 | PASS_SELF_CHECK; 7 exact function groups; matrix JSON ID |
| A22-14-ERRORS | 9.6网关稳定嵌套error{code,request_id}：400schema、401signature/holder/stale+AGPoPchallenge、403scope/revoked/expired、409replay/intent/quote、422budget/calls、503trustedstate；不按异常文字猜分类 | PASS_SELF_CHECK; 17 exact function groups; matrix JSON ID |
| A22-15-FAIL-CLOSED | PG/身份/权限/证据不可用/超时失败关闭，无零超时配置；HTTP事件循环不被同步DB阻塞，等待有界；503后潜在工作仍遵守原子性/幂等，不宣称线程已被杀 | PASS_SELF_CHECK; 12 exact function groups; matrix JSON ID |
| A22-16-PRIVATE-CONFIG | 独立网关配置只需AS公开信任key和已批准identity；不加载AS签名私钥、代理私钥；服务secret与DSN独立私有且不输出；配置不可通过alias变更信任 | PASS_SELF_CHECK; 5 exact function groups; matrix JSON ID |
| A22-17-STARTUP | 明确gateway init/check/run及内部worker调用，TLS证书/配置/key/provider缺失拒启动；不默认DSN、不测试替身/跳验开关、不自行迁移/reset部署DB；网关/下游独立事务与凭据 | PASS_SELF_CHECK; 6 exact function groups; matrix JSON ID |
| A22-18-REAL-TLS | 真实网络gateway进程和开发CA，默认客户端证书/主机名校验；错误CA/host拒绝、公开签名域名仍固定；不得sslverifyfalse；独立PID/就绪/退出证据 | PASS_SELF_CHECK; 2 exact function groups; matrix JSON ID |
| A22-19-PRIVACY | 所有响应/log/CLI stdout stderr不泄原token/proof/secret/DSN/privatekey/内部栈/其他租户；合成标记负例验证，request_id由服务生成不回显攻击者header | PASS_SELF_CHECK; 13 exact function groups; matrix JSON ID |
| A22-20-BOUNDARIES | A2.3持续签名、A3锚定/导出/部署/规模实验未做；outboxPENDING/receipt_jwsnull，UNANCHORED材料仍不冒充独立审计；P21/P18后段子断言明确 | PASS_SELF_CHECK; 7 exact function groups; matrix JSON ID |
| A22-21-DOCS | 同步当前HANDOFF/README/A2-report/context/stage及接口/安全/验收文档，修正旧当前状态；保历史契约/报告/SQL/锁；干净clone本地链接和可执行CLI复现 | PASS_SELF_CHECK; 8 exact function groups; matrix JSON ID |
| A22-22-REGRESSION | 继承67项/60原独立运行义务全部保持，完整source及非editablewheel正式测试/独立探针/历史失败与等价适配按原要求重跑；新增query不能改变A1accept/API | PASS_SELF_CHECK; 753 exact function groups; matrix JSON ID |
| A22-23-ENV-PROVENANCE | worker/reviewer各独占Python3.11/PG16，精确runtime/devlock及PEP517setuptools80.9；wheel不受srcshadow且携带全SQL，父/子进程来源见证 | PASS_SELF_CHECK; 18 exact function groups; matrix JSON ID |
| A22-24-FREEZE-RESOURCES | 全候选tracked/untracked/deleted/modes起止SHA，原生writer停写/资源owner核；禁止共享DSN/容器、仅清自有资源，证据完整退出码/hash/JUnit | PASS_SELF_CHECK; 8 exact function groups; matrix JSON ID |

## Evidence and stop

Authoritative files in this directory: implementation-r4.md, requirements-matrix.json, run-registry.json, assertion-catalog.json, test-function-registry.json, implementation-symbols.json, evidence-index-r4.json, cleanup.json and end-freeze-r4.json. requirements-matrix.md/commands.md are detailed appendices, not old-run summaries. All registry refs are verified against real files and their current SHA. final-r4-candidate-binding.json binds284 candidates; wheel-source-sql-exact-binding.json binds87 source/SQL members. Privacy receipts and all preserved unsuccessful commands are indexed.

Cleanup verifies exact own fullIDs/owner/mounts and exits0: python eb45ac509b4fdfc4644ba7027fcb21a74eca0dfcf311d5fb7669799dc6f9e341, PG be9aebe089d314b4d5fb0803843cef02b992808fcb19d2a032f8f519b32f873e, network b94ee47682c05ec52b5100cf8ffd1536e4ce0f5e1d25b4c306f7f74b0ddf1267. Both observer files restored absent; business process inventory empty; owner containers/networks0. Three prohibited unrelated container IDs/running states unchanged. No writes occur after final evidence index/seal and native completion. Controller alone saves the formal report, closes issues only after independent review and handles later authorized stages.
