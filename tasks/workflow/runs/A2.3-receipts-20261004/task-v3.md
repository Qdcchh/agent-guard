# A2.3-receipts / fullA2 消费者正式任务包 v3

review_kind: PACKAGE_REVIEW。CONSUMER_PACKAGE_REVIEW_PENDING；core15实际原生STOP、范围/资源0/局部selfcheck经主控读回，完整A2仍NOT_ACCEPTED。本段真人实施和有限适配已获授权；完整v3及CLI/HTTPS两个子包须由同一个NEW独立reviewer完整包审并明确分别放行，不能沿用core包审或以局部通过替代最终验收。

主控sol/high、worker sol/medium、每轮新reviewer sol/xhigh；原生回执如实记录，后台effective UNKNOWN。接受产品基线8e4e7a3、独立A22报告b9ae21a2不变；当前HEAD138c08a承接CI-only25→45分钟。该HEAD必需CI37235233187实际SUCCESS（1022普通/1930PG），PR7仍按实际审核条件合并，PR6管理员例外不继承。A23不因该审核等待停止。最新真人明确“验收完A2规划完A3就停吧，太慢了实在是”，见A3-closure-20261004/authorization-limit-20261005.json：完整A2验收和A3可接续规划完成后停止，本次不实施A3，取代以前连续实施A3的授权。

附件：requirements-v3.json完整119/112，node-bindings-v3.json41节点/88本地断言，ownership-v3.json精确core15/CLI4/HTTPS3/docs7，inherited-bindings-v1.json实际接受A22全部节点/逐断言，runtime-binding-v3.json及真实authorization.json，baseline-manifest-v3.json与ignored完整freeze。当前core实际API/15源SHA/AST/局部证据见core-api-bindings-v1.json和原样implementation报告；AST签名不代替源码/行为审查。v1/v2原件为历史设计与包审证据，不能把其中尚未实施/CIpending措辞当当前状态。

原95行为/88flag与新增24父项、全部must_assert/88本地原子不减；完整当段仍须source/noneditablewheel独立重新collect/实跑。core selfcheck仅给消费者真实依赖；消费者local union不能证明整个父项。历史PENDING边界仅为旧未配置receipt_keys兼容路径，不能否定新READY义务。A3独立锚定/导出/部署/三代理/性能公平实验仍未完成，不将本段UNANCHORED单笔签名冒充独立审计。

## 当前文件所有权与共享接口

CLI4和HTTPS3各独占精确文件及owner/resources，正式完整子包分别task-cli-v1.md/task-https-v1.md。完整v3和两个子包经一次NEW独立完整包审、分别PACKAGE_READY及原生STOP/主控读回后可并行；避免同一完整矩阵由两个reviewer重复包审。core实际停止且只读，不得再写；共享API变化必须停止消费者、重规划冻结与新包审。并行测试使用root派发前复制的consumer-common-baseline-v1完整不可变树，仅overlay自己的精确4或3文件，禁止从活跃main复制peer半成品。main peer路径明确并行写区，其他候选/HEAD/index全只读。

所有资源独立owner/fullID LinuxPy3.11/source/wheel/cache/HOME/PG16/随机TEST网关和独立DS数据库/网络/CA/ports/PIDs。只注入独占TEST目标，清普通DSN；不得连接或修改三个既有无关容器。只清实际成功创建、完整ID+owner核实的资源；wrapper真退出/所有子PID结束/自有0才STOP。worker不修改formal/Git/SQL/deps/CI，不开子agent；owner边界不因方便扩大。

实际core共用PermissionSnapshotProvider.load_tx与唯一私有验证体，旧load有界own连接先关闭再验证；原件 helper 按独立真实AS全链/immutableDB/共同历史窗口选exact(tenant,client,kid)，每operation/per-call新ReceiptTrust调用原SDK并核17claims。跨operation合法同DID/kid/SPKI保持，不flatten/last-wins/globalunique/currentDIDfallback/共享可变trust。publisher仅outbox→同conn原件/投影，不倒锁principal/task/grants/op。accept_response逐调用原binding+publication读取在最后DBclock及commit前，commit后无SQL。public factory只公钥，receipt_keys缺省兼容/空错误拒绝；当前实际constructor/helpers/返回类型按core-api绑定完整代码逐字复核，不能凭历史建议名猜接口。


### core (15)

owner `a23-core-quality-r1-20261005`，证据 `artifacts/workflow/A2.3-receipts-20261004/core-quality-r1`；状态 ACTUAL_OWNED0_AFTER_STOP。

- `src/agent_guard/execution/receipt_publication.py`
- `src/agent_guard/execution/original_material.py`
- `src/agent_guard/execution/receipts.py`
- `src/agent_guard/execution/query.py`
- `src/agent_guard/execution/verified.py`
- `src/agent_guard/execution/store.py`
- `src/agent_guard/gateway/config.py`
- `src/agent_guard/gateway/factory.py`
- `src/agent_guard/gateway/endpoint.py`
- `tests/fixtures/receipts.py`
- `tests/unit/test_receipt_publication.py`
- `tests/integration/test_receipt_publication.py`
- `tests/integration/test_gateway_receipt_query.py`
- `src/agent_guard/authorization/permission_snapshot.py`
- `src/agent_guard/evidence/receipt.py`

### cli_config (4)

owner `a23-cli-r1-20261005`，证据 `artifacts/workflow/A2.3-receipts-20261004/cli_config-r1/`；状态 NOT_CREATED。

- `src/agent_guard/gateway/receipt_config.py`
- `src/agent_guard/gateway/receipt_worker.py`
- `tests/unit/test_receipt_worker_config.py`
- `tests/integration/test_receipt_worker_process.py`

### https_fixture_demo (3)

owner `a23-https-r1-20261005`，证据 `artifacts/workflow/A2.3-receipts-20261004/https_fixture_demo-r1/`；状态 NOT_CREATED。

- `tests/fixtures/a23_https.py`
- `tests/integration/test_gateway_receipt_https.py`
- `tools/a2_receipt_demo.py`

### integrator_docs (7)

owner `a23-integrator-r1-20261005`，证据 `artifacts/workflow/A2.3-receipts-20261004/integrator_docs-r1/`；状态 NOT_CREATED。

- `README.md`
- `HANDOFF.md`
- `docs/oauth-oidc-sm2-mvp.md`
- `docs/security-model.md`
- `docs/acceptance.md`
- `tasks/A2-report.md`
- `tasks/workflow/stages/A2.3-receipts.md`

## 完整119项原始行为矩阵

全阶段运行状态NOT_RUN_PENDING_FINAL完整119/112；core已有局部实跑另绑定，不冒完整parent PASS。一个NEW reviewer完整覆盖v3及两子包、逐个判断其范围和可开工性；它不代替后续NEW独立实施验收。原始逐子断言与local有限参数/原子分工以正式JSON为准。

| ID | 原始行为（不减） | 独立运行 |
| --- | --- | --- |
| A2-P01 | 三层订单70000/1成功，唯一真实下游效果；根/中间/叶reserved归0，settled70000/1；RESERVE和SETTLE各一，终态/outbox一致 | 必需 |
| A2-P02 | 下游持久终局拒绝，FAILED、全路径释放不结算，RELEASE一条；该键不能迟到成功 | 必需 |
| A2-P03 | 读取/通知金额0但次数预留结算或释放正确；通知持久效果最多一次，读结果固定 | 必需 |
| A2-P04 | 接受提交前不得执行；提交后真独立子进程终止/重新启动，从持久状态恢复而非finally补救；保留pid/同步与DB断言证据 | 必需 |
| A2-P05 | 下游订单已提交响应丢失→UNKNOWN额度保留；同键恢复唯一订单、一次结算 | 必需 |
| A2-P06 | 下游成功、网关终局前崩溃；恢复无重复效果/账本/终局 | 必需 |
| A2-P07 | 终局事务节点/事件/outbox中途注入异常；全状态/计数/事件/outbox原子回滚，之后可恢复 | 必需 |
| A2-P08 | 查无结果后旧请求迟到成功；不释放，最终唯一效果和SETTLE | 必需 |
| A2-P09 | 双恢复者、过期旧worker竞争，独立连接barrier/event每组10轮；终态不被覆盖、一个终局/一个outbox | 必需 |
| A2-P10 | 接受后祖先撤销/过期/key停用，内部恢复可完成原意图；外部接受重试仍拒绝；真实授权查询本段须完整独立验证 | 必需 |
| A2-P11 | 当前报价改/删后的已有意图使用原成本/快照；新键要求有效报价；确定性miss→另accept→报价消失→安全重查命中；变grant/holder/参数、撤销、proof重放仍拒绝 | 必需 |
| A2-P12 | 下游金额/意图/完整快照错配且可能有效果→UNKNOWN保留预算，无伪成功/释放 | 必需 |
| A2-P13 | 根/中间不足或次数耗尽及接受/结算/恢复并发，10轮、全祖先不超限不负数、不反向锁/死锁无界 | 必需 |
| A2-P14 | 下游同键同意图和冲突、订单/通知均防重复，执行/查询无或错独立服务凭据拒绝、零泄漏/效果；不能只藏端口 | 必需 |
| A2-P15-CORE | 四个完整工具ID/版本，重复JSON键/SKU、bool/负/浮点/溢出数量、缺/空集合、scope不足、跨租户/关联错/URL路径注入、快照/祖先包含错等分层负例，零预留/效果。可信fixture授权不是真实验签 | 必需 |
| A2-P19 | 001及003真实非零预留/撤销/证据升级到004，七旧表全行及完整迁移登记在非法升级时不变；合法重复迁移no-op；旧材料不足sidecar隔离保预算，不能补当前报价执行 | 必需 |
| A2-P20 | 直接SQL改意图/成本/证据、删除重建路径/操作、改删事件/节点、阶段seq绕过、非法状态/双终局拒绝，旧账本不变；合法预算/撤销/状态UPDATE可用 | 必需 |
| A2-CKPT1-OBL01 | 候选前schema/静态授权/可信集合，不要求当前报价存在；命中原快照关联+当前权限后仍A1 accept锁后复核/proof/意图 | 必需 |
| A2-CKPT1-OBL02 | 确定性P11安全重查，包括任意资源/报价解析失败，而非仅金额错误；新键及失效/重放/变意图负例 | 必需 |
| A2-CKPT1-OBL03 | 可用候选完整持久接受事实；永久不可改删事件+非级联FK或明确DELETE保护防删操作，异常旧行隔离；P20不能靠doc承诺 | 必需 |
| A2-CKPT1-OBL04 | claim/终局owner+version+合法state+锁后DB有效expiry；无新owner时旧worker过期也拒绝；UNKNOWN保持且不释放未知预算 | 必需 |
| A2-CKPT1-OBL05 | sidecar不改七旧表、phase/seq CHECK、事件/节点UPDATE/DELETE保护、非法升级全数据和迁移登记保全，合法更新/测试自有清理兼容 | 必需 |
| A2-CKPT1-OBL06 | 下游执行/查询完整原快照持久化比对；不一致UNKNOWN；不可变outbox、receipt_id/created_at稳定、UTC整数秒iat；缺B PENDING且无伪编码/SM3 | 必需 |
| WF-A1-REGRESSION | A1原全部unit/PG集成独立实跑并保留U1/P1—14/F1—5语义与根重建、非零升级断言；不硬编码旧测试计数 | 必需 |
| WF-INDEPENDENT-PROBES | 最终reviewer独立设计绕过/边界探针，保存本轮可复现源与实跑日志；worker不替reviewer选择唯一反例 | 必需 |
| WF-QUALITY-CHECKS | ruff check/format、diff、全unit/骨架/docs/PG实跑；新增目录显式纳入CI；缺库报错不skip | 必需 |
| WF-PY311-ENV | 实际Python3.11、依赖安装/约束和真实PG验证；历史CI/本机3.14不能替代。本轮无授权触发远程CI，NOT_RUN不额外阻断但Python3.11本地必须验证 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。 | 必需 |
| WF-RESOURCE-ISOLATION | worker及reviewer各自独立project/唯一容器/DB/schema，记录归属label、来源、挂载/端口、普通DSN清除、安全目标；前后无关资源不变，清理仅owned | 必需 |
| WF-IMMUTABLE-BASELINE | 检查001—003内容checksum、A1语义、合法更新、无B代码/依赖偷渡。必要接口兼容须主控确认 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。 | 原静态义务 |
| WF-DOCS-REPORT | 报告tracked/untracked误措辞纠正，31ID→具体断言/函数/命令结果，README可复现初始化/worker/下游/测试/清理；真实网关缺B不可装配启动，CI不漏新测试 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。 | 原静态义务 |
| WF-SNAPSHOT-COVERAGE | 主控/reviewer查完整tracked/untracked/deleted及契约SHA256，冻结开始/结束一致；无active writer才review，证据与报告指纹绑定 | 原静态义务 |
| B-01-CRYPTO | 成熟SM2/SM3、ALG/typ/rawJWS/userID/DER-rs严格；标准向量及OpenSSL双向实跑，不改PKCE S256 | 必需 |
| B-02-ENCODING | 全原JSON/Unicode/类型/大小深度/词数边界及raw/JWS/DID/SDK入口，合法负delta仅明确字段；原两issue正式独立闭环 | 必需 |
| B-03-IDENTITY | 默认did:web实际HTTPS/CA/目的/controller/SPKI/企业注册/拒redirect与未批准目标；不是全部仅注入字典 | 必需 |
| B-04-TOKEN-POLICY | 根/两级子各维收窄、空/缺约束拒、完整AS快照与A权限链真实绑定 | 必需 |
| B-05-INVOKE-PROOF | 原body/holder/endpoint/tenant/task/版本/业务键/proof拒绝，静态验证与最终接受分离，零新增状态 | 必需 |
| B-06-CODE-OIDC | 登录、state/nonce/redirect/S256/CSRF/cookie/code一次性；政策/TX/所有晚锁时效全部触发与变体 | 必需 |
| B-07-ROOT-ISSUANCE | 同task永久唯一根，code消费/根/proof/签名快照同txn；双code10轮，原数据不清零 | 必需 |
| B-08-DELEGATION | 父/接收者/完整链可信，签发不占预算；同key/失响应/真进程恢复，撤销/到期/key停用retry不复活 | 必需 |
| B-09-DYNAMIC-STATE | AS/执行/撤销统一锁序、锁后DBclock、完整祖先/key；内省active非永久许可 | 必需 |
| B-10-HTTP-TLS | 全路由格式/媒体/重复头与body/大小/超时/认证/角色/会话拒绝；固定HTTPS/真TLS/脱敏/无生产旁路 | 必需 |
| B-11-RESULT-READ | 真实专用query签验/精确DTO与权限投影；不伪invoke字段。A最终动态查询实现留A2.2且文档不可伪PASS | 必需 |
| B-12-EVIDENCE-RECEIPT | 受控原材料暂存/接受关联、独立AS/GW历史信任、真实规范投影/签验负例；持续outbox签发/导出留后段 | 必需 |
| B-13-ROTATION-INTEROP | AS/client/GW用途与生命周期、旧key历史验证及新调用停用；OpenSSL/源与非editable wheel真互验 | 必需 |
| B-14-DB-FAILURES | 真实DB故障/锁timeout/终止backend/serialization失败关闭和原子回滚，错误不误标坏材料永久隔离 | 必需 |
| B-15-CONCURRENCY-TEST-EFFICACY | 原全部竞争组各10轮，独立连接+可达同步、目标锁/PID/SQLSTATE/负控，不吞异常假PASS | 必需 |
| B-16-A1-REGRESSION | 全A1 U1/P1—14/F1—5与原5probe/等价更强升级，001—003历史checksum，原默认accept API | 必需 |
| B-17-B-SUITE-QUALITY | fresh3.11锁安装、完整source/wheel非集成SDK/PG/OpenSSL/TLS/demo/lint/format及全文测试效力/许可维护审读 | 必需 |
| B-18-RESOURCE-ISOLATION | 每worker/reviewer独占owner/容器/project/DB/schema/缓存，普通DSN清除、精确清理、原资源前后核对 | 必需 |
| B-19-CONTRACT-MERGE | freeze且实际实现invoke bundle/query/evidence/seq投影，调用方一致，原A2.1默认/checked路径不丢 | 必需 |
| B-20-MIGRATION-MERGE | 空库/common前缀/A-origin/B-origin合法升级、非零撤销证据、全部registry及失败原子性、重复no-op | 必需 |
| B-21-SHARED-FILE-MERGE | README/init/fixtures/conftest/deps/CI/migrate语义整合与完整manifest，不覆盖任何一侧功能 | 必需 |
| B-22-ORIGINAL-GOAL | 全M/SEC/CON/REC/AUD/E2E/ENG逐项真实等级/后段责任映射；不拿模块合并候选当比赛完成 | 原静态义务 |
| B-23-HANDOFF-REPRODUCIBILITY | README/手册/升级/初始化/角色/key/合成demo可复现，准确当前版本/限制，不复制B旧main未实现文字 | 必需 |
| B-24-FINAL-BINDING | 完整candidate/契约起止snapshot、每批receipt/native停止与完整独立报告/issue闭环 | 原静态义务 |
| BR-01-CONSENT-FINAL | policy晚锁跨request/session到期两类各10轮零code/event/approved；client key/DID耗时不漏最终期限；core，test_consent_final_decision.py | 必需 |
| BR-02-HTTP-REJECTION | 全挂载路径65536/65537、分块/中断/格式/媒体拒绝4xx；DB503/真实内部500准确，无效果/原敏感材料不回显；http，test_http_request_limits.py+integrator真TLS | 必需 |
| BR-03-PRIVATE-PATHS | FIFO/socket/directory/file及parent link/危险祖先权限/竞态拒绝，独占不覆盖、多umask真实CLI，所有owned子进程退出；private+integrator | 必需 |
| BR-04-LINEAGE-HISTORY | A001—006/B004—009原字节与编号不变，原registry旧行全部字段含applied_at保全，sidecar来源可核验；core | 必需 |
| BR-05-LINEAGE-ATOMIC | 未知/错filename/checksum/缺中间/混合/伪登记/孤立schema失败前后全业务/legacy+sidecar registry不变，并发迁移/真实中断/重复升级；core+reviewer | 必需 |
| BR-06-REAL-PERMISSIONS | 真AS根→两级子→完整snapshot→现有四工具接受/执行；改token/path/scope/holder/SPKI/resources拒、各祖先账本/下游效果正确；core+integrator | 必需 |
| BR-07-QUERY-DTO | 单一subject/method/query字段，真实签验与完整权限/evidence绑定；无tool/key虚字段/不预留不执行，下游动态查询后段明确不计完成；core | 必需 |
| BR-08-EVIDENCE-BINDING | 可信暂存不可改删、raw/digest/ref/当前proof精确关联，接受同txn first/retry独立link，注入失败proof/计数/关联全回滚，旧opaque材料不补造；core | 必需 |
| BR-09-RECEIPT-PROJECTION | 真A outbox材料phase/seq/节点集合验证后投影唯一v1，B规范+真实签验向量；未知字段/错seq/重复/错delta拒；原ID/iat/PENDING材料不变；core | 必需 |
| BR-10-IMPORT-PROVENANCE | 精确import-map及固定B blob/当前A hash，不覆盖A ledger.service/001—006/全部旧测试或原报告，全部增删rename/mode列入manifest；core+controller | 原静态义务 |
| BR-11-CLEAN-CANDIDATE | 整合后freshsource及非editable wheel、空/两legacy升级、全A/B套件、实际demo/TLS/README；CI配置显式包含所有新目录，远程未授权不触发；integrator+reviewer | 必需 |
| BR-12-WORKFLOW-BARRIER | 真人读回/所有包与实际plan版本、真实NEW模型ID/资源、每批双开工门/worker门/freeze和最终require-accepted门；结构检查不替代语义；controller+reviewer | 原静态义务 |
| A2-P15 | 真实授权公开HTTP下全部非法参数、别名、重复JSON/SKU、bool/浮点、空缺集合、注入、跨租户/资源关联、scope/祖先快照错配：拒绝且零效果/零预留；完整原断言，不只分层CORE | 必需 |
| A2-P16 | 真实B验签公开调用缺/错token/proof、换body/holder/endpoint、盗token、重放拒绝；父私钥不能使用子token，零业务变化 | 必需 |
| A2-P17 | 真实result-read仅原tenant/task/subject/root/grant/holder/kid、当前权限；锁后TTL/全祖先撤销/停用；新proof并发/重放；查询无业务计数或下游/租约效果 | 必需 |
| A2-P21-HTTP | 真实受信CA HTTPS的正常四工具采购/读取/通知与查询，固定endpoint、202/error和重复返回当前状态；持续回执签名明确留A2.3，不将完整P21标PASS | 必需 |
| A22-01-REUSE | 复用真实InvocationVerifier/VerifiedExecution/ExecutionService；不复制SM2/SM3/编码/OAuth；生产装配只允许真实provider/evidence/execution | 必需 |
| A22-02-TRANSPORT | 可信ASGI https、固定两条POST路径；不从Host/Forwarded推htu，拒query/fragment变体、编码路径绕过、GET/未知/管理路径、Bearer/DPoP降级 | 必需 |
| A22-03-FRAMING | 请求/响应/头大小有界，拒重复敏感头、组合凭据、非法ASCII/CRLF、Content-Length/Transfer-Encoding歧义、压缩、错类型、断连、body过大/深度/重复键/NaN；不消耗业务预算 | 必需 |
| A22-04-INVOKE | 首次invoke202返回operation_id与真实status/receipt_status，事务提交后内部worker执行；HTTP不隐式启动业务或签名；已终态同键新proof仍202但status不伪RESERVED | 必需 |
| A22-05-QUERY-BUNDLE | 新增可信query bundle保留PermissionSource及opaque evidenceRef，保原canonical-result API兼容；不可从请求构造可信对象/自报权限 | 必需 |
| A22-06-QUERY-LOCKS | 真实PG锁序principals排序→task→root-leafgrants→operation；检查完整不可变授权链；不伪装invoke DTO或放宽A1purpose；与接受/恢复/撤销锁序兼容 | 必需 |
| A22-07-QUERY-OWNERSHIP | 查询仅原授权节点、holder/key、tenant/task/subject/root；当前权限仍覆盖原tool/params且原操作可核验；跨身份猜ID拒绝不泄露存在/内容 | 必需 |
| A22-08-QUERY-FINAL-CLOCK | 所有可能阻塞的证据/行读取/约束处理后最终DBclock_timestamp；重读已锁key/全祖先并检查token/proof及grantnotbefore/expiry；等待或latebinding超过TTL拒绝，事务完整回滚 | 必需 |
| A22-09-QUERY-REPLAY | 查询proof唯一kid/purpose/endpoint/jti并同事务operation/evidence关联；并发同proof最多一成功，10轮；失败不消耗proof，不覆盖首次证据 | 必需 |
| A22-10-QUERY-ZERO-COST | 读取RESERVED/EXECUTING/UNKNOWN/SUCCEEDED/FAILED合法状态；result仅可信持久事实，回执null/PENDING；不创建操作/事件/outbox、改预算/lease或执行下游，beforeafter全路径计数/业务行一致 | 必需 |
| A22-11-QUERY-EVIDENCE | query_binding在同事务验证真实raw/token/proof/body/context/source对应关系，换ref/错source/legacy不全拒绝；不把query写作invoke retry；优先ag_proofs关联无迁移 | 必需 |
| A22-12-QUERY-PERMISSION | 当前签名token、DB权限源与历史原操作所需资源/tool/收窄逐项一致；坏可信源/不完整链/缺原事实失败关闭，不能靠签名或缓存放行 | 必需 |
| A22-13-DYNAMIC-RACES | 真实撤销/key停用vsquery/accept线性化及锁等待TTL、lateDB依赖；独立连接event/barrier每组10轮、捕获全部异常和完成，负控证明触发目标 | 必需 |
| A22-14-ERRORS | 9.6网关稳定嵌套error{code,request_id}：400schema、401signature/holder/stale+AGPoPchallenge、403scope/revoked/expired、409replay/intent/quote、422budget/calls、503trustedstate；不按异常文字猜分类 | 必需 |
| A22-15-FAIL-CLOSED | PG/身份/权限/证据不可用/超时失败关闭，无零超时配置；HTTP事件循环不被同步DB阻塞，等待有界；503后潜在工作仍遵守原子性/幂等，不宣称线程已被杀 | 必需 |
| A22-16-PRIVATE-CONFIG | 独立网关配置只需AS公开信任key和已批准identity；不加载AS签名私钥、代理私钥；服务secret与DSN独立私有且不输出；配置不可通过alias变更信任 | 必需 |
| A22-17-STARTUP | 明确gateway init/check/run及内部worker调用，TLS证书/配置/key/provider缺失拒启动；不默认DSN、不测试替身/跳验开关、不自行迁移/reset部署DB；网关/下游独立事务与凭据 | 必需 |
| A22-18-REAL-TLS | 真实网络gateway进程和开发CA，默认客户端证书/主机名校验；错误CA/host拒绝、公开签名域名仍固定；不得sslverifyfalse；独立PID/就绪/退出证据 | 必需 |
| A22-19-PRIVACY | 所有响应/log/CLI stdout stderr不泄原token/proof/secret/DSN/privatekey/内部栈/其他租户；合成标记负例验证，request_id由服务生成不回显攻击者header | 必需 |
| A22-20-BOUNDARIES | A2.3持续签名、A3锚定/导出/部署/规模实验未做；outboxPENDING/receipt_jwsnull，UNANCHORED材料仍不冒充独立审计；P21/P18后段子断言明确 | 必需 |
| A22-21-DOCS | 同步当前HANDOFF/README/A2-report/context/stage及接口/安全/验收文档，修正旧当前状态；保历史契约/报告/SQL/锁；干净clone本地链接和可执行CLI复现 | 必需 |
| A22-22-REGRESSION | 继承67项/60原独立运行义务全部保持，完整source及非editablewheel正式测试/独立探针/历史失败与等价适配按原要求重跑；新增query不能改变A1accept/API | 必需 |
| A22-23-ENV-PROVENANCE | worker/reviewer各独占Python3.11/PG16，精确runtime/devlock及PEP517setuptools80.9；wheel不受srcshadow且携带全SQL，父/子进程来源见证 | 必需 |
| A22-24-FREEZE-RESOURCES | 全候选tracked/untracked/deleted/modes起止SHA，原生writer停写/资源owner核；禁止共享DSN/容器、仅清自有资源，证据完整退出码/hash/JUnit | 必需 |
| A2-P18 | 完整原P18：真实持久发布、签名失败/签后保存前真崩溃/保存后返回丢失、receipt_id/payload/iat稳定、业务不重做、篡改结果/路径/delta拒绝 | 必需 |
| A2-P21 | 完整原P21：真实登录同意/根授权/两级委托、四工具HTTPS调用、内部持久终局、发布、当前授权查询与独立可信公钥回执验签 | 必需 |
| A23-01-REAL-SIGNER | 复用crypto.sm真实SM2/JWS/SM3与evidence.receipt独立验签，不复制密码实现、不假Verified对象 | 必需 |
| A23-02-KEY-SEPARATION | 独立网关receipt私钥/kid，拒AS/holder角色重用、缺key/公钥不匹配；AS/holder/downstream分离；HTTP不加载signer私钥 | 必需 |
| A23-03-PRIVATE-INIT | 显式init独占private_files，安全权限/路径/symlink/已存在原文件不覆盖；只合成key，check离线、run缺配置失败关闭，无默provision | 必需 |
| A23-04-TRUST-ROTATION | 外部可信GW历史公钥配置、发布当前kid、旧Ready按旧kid验签且原字节稳定；未知kid/自带key/缺历史key失败关闭 | 必需 |
| A23-05-IMMUTABLE-MATERIAL | 终局op/outbox/原首次token-proof-request/context/source/完整ASsignedchain/报价/result/path/event/delta全绑定；错误/缺/legacy原件失败关闭 | 必需 |
| A23-06-ATOMIC-PUBLICATION | 真实PG有界TX条件PENDING→READY，仅receipt_status/JWS/signed_at写；READY字节/签发时刻/材料不可变，不创建第二outbox，无其他业务写 | 必需 |
| A23-07-STABLE-CLAIMS | UUID5receipt_id、iat从created_at；首次token/proof/intent/result/ledger规范摘要及完整17claims；重签前崩溃payload不变，保存后JWS字节不变 | 必需 |
| A23-08-SIGN-FAILURE | 密码后端或存储错误失败关闭，PENDING/null保留、无下游/计数/lease/event/终态改变，故障移除原操作正常发布 | 必需 |
| A23-09-PRECOMMIT-CRASH | 真独立publisher进程在sign后commit前SIGKILL；原资源/数据库持久无假finally；新PID恢复同payload/id/iat仅一次持久发布；未提交SM2重签字节可不同 | 必需 |
| A23-10-POSTCOMMIT-LOSS | 真进程保存READY后响应未交付/死亡；新进程同id获取原JWS/signed_at，无重复签或效果 | 必需 |
| A23-11-CONCURRENCY | 多publisher独立连接/真实barrier/DB锁每组10轮，claim/重复同op/恢复竞争；完整祖先四计数/业务/全部DS表不变，唯一Ready | 必需 |
| A23-12-HISTORICAL-FRESHNESS | 已接受操作撤销/过期/key停用后内部终局/发布仍可完成，原件历史共同窗口验证；外部invoke retry/query必须当前权限/新proof | 必需 |
| A23-13-PUBLIC-READY-QUERY | 专用query严格A2.2全部动态授权、全晚等待finalclock；PENDING兼容/READY真实persistedreceipt验证、badsignature/错claims/digest/type/key503 proof回滚 | 必需 |
| A23-14-PUBLIC-INVOKE-STATUS | 202首次Pending/terminalretry实际receipt状态；所有额外publication读取/验签在接受TX最终clock前，禁止commit后lateDBwait泄漏已过期证明 | 必需 |
| A23-15-NONTERMINAL | RESERVED/EXECUTING/UNKNOWN没有最终outbox/receipt；内外非法状态均拒绝，不伪FAIL或释放 | 必需 |
| A23-16-INTERNAL-CLI | 真实可持续重启内部publisher CLI，仅operator严格私有配置（不发明签名配置协议）/显式DSN；bounded polls/attempts/SQL/错误脱敏，一个坏材料不饿死其他合法待签项；无公开sign/recover管理路由 | 必需 |
| A23-17-REAL-HTTPS-CHAIN | 受信CA+固定AS/GW hostname验证的真实login/consent/code/IDtoken/两级exchange/fourtool/query；非线程inprocess假全链，持久DB归属明确 | 必需 |
| A23-18-ATTACK-CLOSURE | 完整HTTP路径token盗用/bodyholderendpointtamper/replay/crossowner/currentrevoke拒绝，beforeafter全祖先业务及DS零越权/重复效果；公开response不暴露raw证据/secret | 必需 |
| A23-19-OFFLINE-MUTATIONS | 独立ReceiptTrust真实verify_receipt_bundle，结果/amount/祖先缺重排重复/全节点delta/首次proof/token/receipt类型/kid篡改失败；UNANCHORED边界 | 必需 |
| A23-20-SOURCE-WHEEL | 完整source+非editablewheel Python3.11 PG16锁安装/14SQL/真实parentchild模块来源/新CLI README流程/所有A1A2B95回归/原历史等价与失败 | 必需 |
| A23-21-A2-ACCEPTANCE | 完整P01-P21逐原断言及M/SEC/CON/REC/AUD/E2E/ENG30目标映射；A3锚定/导出/规模/三代理编排标NOTRUN不移除目标；只声明完整A2 | 必需 |
| A23-22-FREEZE-RESOURCES | 所有workers native停写/只读依赖精确scope/全候选起止哈希、freshreview完整矩阵原始日志/失败/资源fullID与0余留；不碰无关资源 | 必需 |

## 3. 配置与CLI冻结边界

public GatewayConfig增加唯一可选`receipt_keys`（kid->SM2 public PEM）字段；缺字段严格兼容旧config=PENDING-only；显式空/错误/unknown字段拒绝，不静默忽略。new keys不可alias改变；AS/holder/gateway按canonicalSPKI比较角色分离，新receipt signing kid角色冲突拒绝；现有不同tenant/client holder共享同DID/kid/SPKI合法登记保留，不加global kid唯一限制。HTTP factory传完整tuple登记和冻结provider给ReceiptVerifier，仅持公钥并按op已验链构造ReceiptTrust，永不读取signer私钥。历史kid保留，轮换只能新kid、新公钥；旧READY/JWS原样验证。

private publisher config固定字段建议：`profile, gateway_config_path, signing_kid, signing_key_path, connect_timeout_seconds, lock_timeout_ms, statement_timeout_ms, batch_size, poll_interval_ms`；exact schema、positive bounded整数（bool拒绝）。profile GM-MVP-1，不含DSN、AS/holder私钥、downstream_secret。operator路径读取全用既有descriptor-bound private_files，不仅chmod检查。`check`与`run`相同loader/builder/key一致性；check无DB连接。

`python -m agent_guard.gateway.receipt_worker init --out NEW --gateway-config OLD --kid NEWKID` 只新建0700目录和0600 signer PEM/publisher.json/gateway-public.json；旧input字节不变；公钥基于真实CSPRNG独立SM2私钥。原public config secrets_path若相对旧目录，写新副本须安全解析为原绝对引用；不复制或读取downstream secret，不复制AS/holder私钥。拒已占kid、已有目标/symlink/unsafe ancestor/自然open错误，多umask/竞争进程真实负例。部分失败只能留安全私有部分文件且明确失败，不覆盖旧文件或修权限。

`check --config`; `run --config`仅显式`AG_RECEIPT_DATABASE_URL`，缺省失败，不fallback部署普通DSN；无自动migration/provision/reset。bounded batch keyset轮转，坏材料不永久饿死后续合法pending；一个周期失败收集但不泄raw/DSN/栈。内部publisher是直接服务/CLI，不新增公开sign/recover管理路由。不称配置operatorsigned：配置安全加载而非发明签名配置协议。


## 5. 故障、拒例及P18/P21的真实证据

共同效果oracle：before/after每层四计数、ag_operations全部原列、event+node、lease/fencing、outbox全部材料、first/retry evidence及query proof绑定、ds_*所有业务表。publication只允许三个发布字段变化；失败全回滚PENDING/null，不重执行下游。query合法仅新proof绑定与允许STAGED审计材料；非法proof rollback，修原数据用同proof成功随后重放409。修改raw/context/source/quote/result链等保持原故障原件与精确预期typedcode；未知程序错保500，不按文字分类。

签发失败至少真实backend签发错误/错key/type/储存约束或真实PG中断分类验证，恢复原条件后发布同operation；测试注入和真DB故障分别记录。core sign→commit SIGKILL须独立真实子进程直接调用冻结InternalPublisher，不导入尚未写CLI；CLI阶段由tests/integration/test_receipt_worker_process.py使用实际receipt_worker PID重复两故障窗口，S2整合完整P18。core SIGKILL须实际完成真实sign后在自有PG outbox UPDATE或commit deferred barrier同步，确认pg_stat_activity/backend PID目标等待，SIGKILL后新PID持久PENDING并恢复。测试自有barrier函数/触发器不是产品迁移；不得生产ENV hook。commit→响应丢失须确认独立连接已见READY再阻断实际stdout/IPC交付或杀独立publisher（关闭读取端真实broken-pipe也可），新PID取原JWS/signed_at；不能仅raise模拟网络。该内部publisher/CLI故障不是“真实TLS网络断网”，真实网关返回丢失可另有HTTPS连接关闭证据。SM2随机签名在precommit重试可能不同，只要求payload/id/iat稳定；一旦commit JWS字节不变。

并发每组10轮：同op双publisher、publisher/query、publisher/invoke retry、两恢复者/旧worker、撤销/停用与外部query/accept；独立连接、barrier/event、全部future异常收集、PID/SQLSTATE与正负控证明窗口可达，不sleep碰运气。签名行锁不能与执行锁形成反向锁。

完整P21新增一个同场景真实网络联合链，不能拼接两个历史TLS测试：固定 auth.agent-guard.test/gateway.agent-guard.test + 受信开发CA/SAN hostname，独立AS/GW进程；浏览器GET登录CSRF→POST密码→authorize state/nonce/精确redirect/S256→consent→code-exchange真实AGPoP→RP验证IDToken→planner到selector、selector到executor两次真实AS exchange（不同Basic/SM2 key）→procurement.request.read、procurement.document.read、procurement.order.create、notification.template.send四个ToolId/version字符串1真实HTTP（notification.send与全部短名仅负例）→内部执行独立下游持久终局→InternalPublisher真实签发→当前授权新proof query READY→独立ReceiptTrust offline verify。每工具唯一效果/预算/稳定回执；notification引用已有可访问操作。wrongCA/wronghost/盗token/父key冒child/bodyendpointtamper/replay/跨owner/revoke/tokenTTL各真拒例且全效果零新增，响应无raw证据或secret。


## 容量、编码和故障证据等级

core真实AS登录/consent/root两级exchange→publicaccept→独立PG终局→真实publisher→当前query→offlineSDK的原256短SKU及新12/16/17字节宽SKU大合法数量路径，已经新精确conditional包审和SDK修复后source/wheel实际实跑，证据由主控读回绑定。原16/17合法组合aggregate早拒FAIL及PENDING无额外效果实证保留，不能追改成旧通过。只证明实际测试场景，不声称256×128任意宽SKU可达或最大；各component/JWS/JSON深度nodes/stringbytes/公开65536原限额均不扩大。conditional第29路径SDK已按新独立包审实施并停写，精确outer1MiB编码兼容扩展及原安全拒例完整复验；这些仍不是fullA2独立接受。

N021精确65536/65537响应边界须按真实四工具schema/escaping/JWS/关联证明区分合法可达和测试故障注入；任何新绑定决定需实际core上界/正负例证据与独立包审，不放宽生产字段限额或假称替换projection为合法业务。缺该证据保持未闭合，原public上限和proof回滚/全效果语义不减。

N021/N031具体证据分类提案见capacity-reachability-bindings-v1.json，保留原精确codec/outer测试点与全部父语义。旧SDK64KiB聚合产生的65235相消上界在修复后废止，不能作为当前证据；N021按四工具/refusal、实际UUID32/receipt/kid/JWS schema保守编码上界重新核证。N031按严格九字段、每component原64KiB与精确keys/colon/commas重算物理上界，使1MiB合法正控边界不可达；不能继续用已移除的非ledger整体64KiB前提。新reviewer须独立读全部真实guard、生成ID、签名长度、canonical escaping/fields及source/wheel正负证据后决定，任何无法证明的前提仍OPEN；不把codec点、故障注入或提前拒绝说成真实合法业务到达边界，也不改原限额或削断言。

原新增晚依赖outbox/projection/key/source load_tx/deferred与旧8wait/4window均保留：真实AS root8s/mid≤6/leaf3签发余量、真实1sproof，release前DBclock正负控、目标SQL/backendPID/可达barrier/event，各组10round/full futures异常及所有ag与DS3 oracle。parent expiry可能同时约束子/token，不假称独立父过期。签后commit前真SIGKILL、独立conn已见READY后真实IPC/stdout交付丢失/newPID原JWS，内部进程故障不叫TLS断网。测试损坏材料仅own namespace精确恢复trigger，生产不可变保护另验证；无ENV跳验/关journal/关闭生产guards。

## 7. 项目30目标和剩A3

完整A2必须重跑M1—M9/M11—M13、SEC-01—07、CON-01—03、REC-01—03适用全部原断言：M1/2/3本段P21联合入口；M4/5 SEC04/05真HTTP攻击；M6 CON01/02完整根/中间竞争；M7 REC01/02真故障及P18发布；M8 SEC06撤销；M9真offline全关联与UNANCHORED；M11唯一根；M12合法256/重复SKU/全资源约束；M13 late-lock TTL与收窄父子真实期限。E2E-01本段完成确定性真实联合HTTP采购/攻击验证，但A3.3还需可交付三代理编排/五分钟演示/部署流程。

准确剩余责任：M10/ENG-01 A2锁安装/sourcewheel/README仅部分，A3.3干净TLS部署初始化/攻击demo，A3.2完整证据导出；AUD-01 A2单笔签名/结果/祖先/delta关联部分，A3.1真实独立检查点和连续记录，A3.2重排/删除/相对最新外部锚点回滚检测；AUD-02 A2 UNANCHORED限制说明，A3.2独立最新锚点/未锚定尾部报告。E2E-01 A3.3部署/三代理产品演示。性能50客户端/≥10000调用、Bearer和无原子预算公平消融、各样本/错误/效果/开销分解、CPU内存DB配置/重复批次与原始数据、版本一致技术材料在A3.4。A3四段目标和未来验收要求保留为接续规划，本次不实施；不提前把这些目标移除或PASS。

## 8. 完整运行与验收交付计划

单integrator与fresh reviewer各自全source/noneditablewheel Python3.11 Linux UID501、真实PG16；锁安装/PEP517/14SQL、actual parent+CLI+workerchild importfile/metadata/no-srcshadow；ruff check/format、普通/骨架/docs/全integration，A1单列U1/P1—14/F1—5，原历史A2 482/B原与等价250/A1原4+1升级等价、oracle60、CTX16、A22 r1RESULT-ERROR/SHORT-WINDOW完整正式补正、所有新节点/README旧两流程+新CLI联合运行。计数按实际收集不硬编码历史PASS数。所有测试路径落tests已有pytest testpaths，CI已有整目录收集，但仍静态/实际核新文件确收集；不修改.github获得假绿。

每119项必须具体parameterized node→源断言行/效果oracle→runlabel→command/exit/log/JUnit/hash，失败与适配保原件；privacy脱敏保JSON/XML结构与前后SHA，不匹配删除断言或覆盖同名日志。完整候选tracked/nonignored-untracked/deleted/modes与contracts/readonly依赖起止hash，所有writer/native子进程停止、自有资源0后fresh sol/xhigh完整119/112。此规划所有项目NOT_RUN，任何本轮接受/缺陷关闭只能由正式独立验收产生。

## 9. 30目标逐项可审映射（全部计划NOT_RUN）

| 原ID | A2完整证据义务 | A3剩余 |
|---|---|---|
| M1 | B-06/B-10及P21真实login/consent/state/nonce/redirect/S256/code一次性/IDToken | A3.3部署复现 |
| M2 | B-08/BR-06及P21两次真实ASexchange/三个holder/逐维收窄扩权拒 | A3.3可交付三代理编排 |
| M3 | B-03/13真实DID CA/用途/登记/SPKI/停用拒 | A3.3部署密钥运维演示 |
| M4 | P16/BR-06盗token无holderkey，invoke与exchange失败 | A3.4公平Bearer消融 |
| M5 | P15/16/17 body/params/holder/endpoint/jti精确绑定 | A3.3攻击脚本 |
| M6 | P13根100000两支70000竞争，最多一个接受 | A3.4规模/对照 |
| M7 | P05/06/08真实持久唯一订单/UNKNOWN保预算 | A3.3故障演示 |
| M8 | P10/A22动态竞态撤销先提交新accept拒、旧恢复 | A3.3撤销演示 |
| M9 | P18真实receipt/result/path/全部delta验签拒篡改、UNANCHORED | A3.1/2独立锚定/导出 |
| M10 | A23-20 sourcewheel安装/README内部发布片段 | A3.2导出+A3.3干净TLS部署攻击演示 |
| M11 | B-07/code真实唯一根/双code/重复同意/过期不重建 | A3.3部署完整重跑 |
| M12 | P15/M12统一256、SKU重/约束缺空/报价关联 | A3.4样本边界说明 |
| M13 | A22最终时钟/父子窗口补正/交换失效幂等拒 | A3每新入口同不变量 |
| SEC-01 | B-01/13真实标准向量/OpenSSL双向/原始segments/type | A3.1 checkpoint新typ正式版本契约 |
| SEC-02 | B-02全严格JSON/规范编码/签名和signeddelta专用边界 | A3.2有界大包分帧 |
| SEC-03 | BR-06/P21三holder两级收窄/所有维扩权拒 | A3.3三代理隔离边界 |
| SEC-04 | P15/16任务租户受众工具版本报价deliveryholder换值拒 | A3.3攻击演示 |
| SEC-05 | P14/16/17 query/invoke proof重放与业务键效果幂等 | A3.4规模/重试样本 |
| SEC-06 | P10全祖先撤销线性化及内部恢复 | A3.3撤销场景 |
| SEC-07 | P14/BR-03/08/A23-02独立服务secret/DB拒角色/固定通知/私钥隔离 | A3.3部署实际权限隔离 |
| CON-01 | P13根竞争完整10轮 | A3.4压力规模 |
| CON-02 | P13根有余额中间不足直接与后代累计 | A3.4规模样本 |
| CON-03 | P03/13读取通知订单次数、失败释放UNKNOWN保留 | A3.4统计口径 |
| REC-01 | P04—09/18安全模型所有中断点/计数事件outbox效果一致 | A3.1checkpoint/A3.2导出新故障 |
| REC-02 | P08/09迟到成功/多恢复者/fencing/唯一终局 | A3.3演示+A3.4恢复开销 |
| REC-03 | P11/12原完整报价跨恢复，不一致UNKNOWN | A3.3演示 |
| AUD-01 | P18/B-12/BR-09单笔链请求结果delta关联 | A3.1独立检查点+A3.2篡改重排删除回滚检测 |
| AUD-02 | UNANCHORED/缺最新锚/尾部/同宿主局限 | A3.2最新外部锚点验证与边界报告 |
| E2E-01 | P21一条真实HTTPS联合闭环四工具正常及攻击 | A3.3确定性产品编排/可交付demo |
| ENG-01 | A23-20锁安装/迁移/测试/sourcewheel/内部CLI README | A3.2导出+A3.3干净部署+A3.4材料版本一致 |

remote main=d7e91c7为主控当前只读查证上下文；strict checks app15368/至少1 approval+CODEOWNER限制需实际发布时重新查证，不承接PR6管理员例外。A2.2合并审核受阻仍从已接受commit继续A2.3/fullA2及后续授权A3；后段不混进前受审head，不修改保护/假批/强推。A3未来新增SQL以各正式包真实inventory为准，不将本轮14固定成未来总数。正式MD自足完整矩阵语义/证据索引，精确多千函数/node/断言/hash放rawJSON去重复，不能因此省完整复核。


## 元数据补正与独立放行

95继承来源已绑定真实accepted A22，A23 final重新collect/完整实跑仍待allSTOP；G1本轮完整整合义务不写成未来A22待接受。历史provenance-map从v1原件逐字恢复，current_source map独立实际SHA。原r2两个P3已由新容量包reviewer独立核证具体补正并经原生STOP/主控完整读回，见package-review-capacity-r1.md；不把历史问题闭合冒作业务接受。新notification局部上界备注须绑定afterfix实际证明，不能沿用3359。

CLI4/HTTPS3实际STOP后主控核scope7/只读依赖、每command/exit/rawlog/JUnit/SHA/actual node+断言与own0，再转exact29给sole integrator。integrator联合全部7docs/CLI+HTTPS完整119/112源与wheel、A1/A2/B/历史原失败与等价/oracle60/CTX16/README旧两流程+新publisher、14SQL/Pep517锁/OpenSSL/TLS/所有PID来源自查。所有worker/nativechildren停止后完整候选tracked/untracked/deleted/modes/contracts/hash冻结，NEW独立完整reviewer亲自全实跑、自设计探针、完整119矩阵和issue闭环；失败同段补正再NEW完整复验。完整A2接受后收敛A3四段可接续计划、保留未来各段规划/包审/工作/完整验收要求，然后停止；不派发A3实施，不将项目标完成或绝对无缺陷。
