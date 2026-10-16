# A2.3-receipts / fullA2 正式任务包 v2

review_kind：PACKAGE_REVIEW。状态：FORMAL_PACKAGE_PENDING_FRESH_REVIEW；业务NOT_RUN。A22已独立接受，真人实施与本段有限适配已授权；实施前仍须新的独立PACKAGE_READY。主控请求gpt-6.1-sol/high、worker gpt-6.1-sol/medium、每轮NEW reviewer gpt-6.1-sol/xhigh，后台有效metadata UNKNOWN。

已有基线为接受提交`8e4e7a3eba6a3e3f0a6a3eb9c3745e2cf7f17d40`、独立完整A22 review-r2 SHA `b9ae21a2c6537d0097e6d9a4e2b4da701953a24c496396b0aa2f1e77728cee13`；95/88及285全候选原生停写/首尾无漂移由主控完整核验。A22已发布[PR #7](https://github.com/Qdcchh/agent-guard/pull/7)，CI/审核另核，不把其未合并当后段阻碍。本段在独立`codex/a2.3-receipts`分支承接接受提交，承接已独立审查的CI-only提交138c08a，PR #7当前head同为该提交。A3全部已另获真人连续授权，但只在完整A2接受后逐段实施。

正式附件：[完整119项/112运行矩阵](requirements-v2.json)、[精确所有权](ownership-v2.json)、[41唯一计划节点/local断言/有限案例](node-bindings-v2.json)、[实际接受A22节点/逐断言绑定](inherited-bindings-v1.json)、[全基线SHA](baseline-manifest-v2.json)、[本段实际适配绑定](runtime-binding-v2.json)、[原批准来源](authorization.json)。原A2任务、安全/接口/项目30目标完整保留。附JSON是规划义务，不是行为PASS；原95行为/88 flag逐字不改，新增24=A2-P18/P21与A23-01..22。7原静态项不当运行；全部112运行义务须final fresh独立实跑。

历史A22-20/PENDING及B原阶段边界只约束其原段和本段旧无receipt_keys兼容路径；新增READY完整P18/P21不能被历史NOT_RUN误否定，也不得删除其安全回归。所有当前文档如实维护，原授权、任务、失败/报告、SQL与锁保持。

规划疑点已独立只读核查：实际AS配置/IdentityResolver要求kid以其不含#的DID加#为前缀，完整委托拒重复DID；不同DID同完整kid的真实合法AS链不可达，未新增产品缺陷，不扩大SDK范围。跨operation/tenant/client共享DID/kid/SPKI仍合法，须按已真实验签完整AS链与不可变DB绑定确定exact tuple，仅为该operation构造新的ReceiptTrust并用原SDK。绝不能整表kid flatten、last-wins或global kid唯一化。

所有owner固定下列标签，计划task path分别/root/a23_core_worker_r1、/root/a23_cli_worker_r1、/root/a23_https_worker_r1、/root/a23_integrator_r1；实际创建/完成回执另记。不先填COMPLETED或资源ID。自有PG16/网络/测试DB随机后缀，source/wheel分离cwd、HOME/TMP/cache_dir、环境与原生日志/包装PID；测试容器repo只读、worker在宿主精确文件实施。清空普通部署DSN，仅自有TESTDSN。只清完整ID+owner核实资源，三个既有agent-guard-a2-pg/verivote容器不得连接/修改。所有外部包装真实退出才STOP，不以/proc空或PID查不到代结束。

## 共享接口与停写顺序

新增core精确第14路径 authorization/permission_snapshot.py。固定拟API `PermissionSnapshotProvider.load_tx(conn, token, *, grant_id, now) -> PermissionSource` 与私有 `_from_records(records, token, now)`：共用唯一原完整签名/登记/DB绑定/权限收窄校验体，禁止publisher复制约80行授权逻辑、monkeypatch连接、由原件自报source构造信任。原load(token,*,grant_id,now)仍原有界psycopg连接读_chain_rows后关闭再调用私有validation，原生命周期/超时/返回/异常语义保持；load_tx用caller conn获取同records并调用同validation。publisher已锁outbox同conn与独立可信历史公钥登记，在真实签验全部token/proof得到的共同历史窗口取SDK合法时刻，绝不能随意取now或未验签raw时间；query仍当前源+原first完整context逐字段对比。new sameTX source、连接关闭时机、latewait finalclock及全部B/SDK回归纳入测试。所有名字是拟冻结接口，并非声明实现存在。

core14先串行，完成实际API/fixture/regression后native停写、自有清理/精确scope检查，controller冻结实际API与全只读依赖SHA；消费者新的独立包审后CLI4和HTTPS3并行各独占文件与资源，HTTPS只直接调用已冻结core服务，不读未冻结CLI。全部worker及children停写后单integrator独占转移28路径联合整合/7docs，完整sourcewheel/historical自查；无新SQL/deps，conditional evidence/receipt.py真实确认/精确包审后才可能第29。共享变更暂停消费者并重新冻结/审包。

## 精确路径与资源


### core (14)

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

独占owner `a23-core-r1-20261005`，证据 `artifacts/workflow/A2.3-receipts-20261004/core-r1/`，资源NOT_CREATED；自有Py/source/wheel/cache/PG16/network/随机TEST gateway与独立downstream DB/CA/ports/PIDs。所有未列精确路径默认只读；controller控制文档独占。

### cli_config (4)

- `src/agent_guard/gateway/receipt_config.py`
- `src/agent_guard/gateway/receipt_worker.py`
- `tests/unit/test_receipt_worker_config.py`
- `tests/integration/test_receipt_worker_process.py`

独占owner `a23-cli-r1-20261005`，证据 `artifacts/workflow/A2.3-receipts-20261004/cli_config-r1/`，资源NOT_CREATED；自有Py/source/wheel/cache/PG16/network/随机TEST gateway与独立downstream DB/CA/ports/PIDs。所有未列精确路径默认只读；controller控制文档独占。

### https_fixture_demo (3)

- `tests/fixtures/a23_https.py`
- `tests/integration/test_gateway_receipt_https.py`
- `tools/a2_receipt_demo.py`

独占owner `a23-https-r1-20261005`，证据 `artifacts/workflow/A2.3-receipts-20261004/https_fixture_demo-r1/`，资源NOT_CREATED；自有Py/source/wheel/cache/PG16/network/随机TEST gateway与独立downstream DB/CA/ports/PIDs。所有未列精确路径默认只读；controller控制文档独占。

### integrator_docs (7)

- `README.md`
- `HANDOFF.md`
- `docs/oauth-oidc-sm2-mvp.md`
- `docs/security-model.md`
- `docs/acceptance.md`
- `tasks/A2-report.md`
- `tasks/workflow/stages/A2.3-receipts.md`

独占owner `a23-integrator-r1-20261005`，证据 `artifacts/workflow/A2.3-receipts-20261004/integrator_docs-r1/`，资源NOT_CREATED；自有Py/source/wheel/cache/PG16/network/随机TEST gateway与独立downstream DB/CA/ports/PIDs。所有未列精确路径默认只读；controller控制文档独占。

## collection和证据门

原95语义逐字保留、88运行不得减；历史stage-only PENDING附明确A23兼容延伸而不改历史正式JSON。继承具体测试节点已由inherited-bindings-v1.json绑定实际接受A22完整source/wheel collection和逐函数/断言；本段仍须独立重新collect/运行，不拿旧PASS充新证据。新增24项具体file/function/parameter domains已在JSON精确规划，尚未实现/collect；worker在批准scope实现完整行为与这些正式回归，停写后必须actual collect且所有planned subclaims映射实际parameterized nodes并实跑。不能把planned名当可运行证据、不能只标题/总count判断覆盖。

每组并发/lateSQL时窗10轮独立连接/barrier/event，目标PID/SQLSTATE/正负控全部异常；每条拒例beforeafter全部祖先四计数/op/event/node/lease/outbox首次材料/evidence/proof links与全部独立ds_*真实效果，不只HTTP。publication仅3字段允许变化，query合法只proof与允许STAGED事实。sign→commit真SIGKILL和commit→回复真实丢失新PID同PG恢复，故障类型不假称TLS断网。

最后integrator和fresh reviewer分别独立source/noneditablewheel Python3.11 PG16，exact锁/PEP517/本轮实际14SQL与checksum/实际parentCLIworkerchild来源、全部普通/docs/PG/A1单列/原A2历史482/B原及等价250/A1原4+1及升级等价/oracle60/CTX16/A22两r1补正/旧AS和GW README+新publisher联合流程，全部119/112原子效果与privacy evidence原件。实际收集计数、不硬写未来数量；A3后续SQL以各包inventory。完整版本起止tracked/untracked/deleted/modes/契约hash、所有原生stop、自有资源0、无关资源同fullID未动后才fresh全验收。每轮补正换新reviewer完整矩阵，设计作者不得兼独立包审。

## 完整119项语义矩阵

全部下列为NOT_RUN，每行需JSON中具体参数/断言/oracle/owner/phase和未来actual node/evidence绑定。7 inherited static项依原义务，112独立运行项不可缩减。

| ID | 原始行为/义务（不减） | 运行 |
|---|---|---|
| A2-P01 | 三层订单70000/1成功，唯一真实下游效果；根/中间/叶reserved归0，settled70000/1；RESERVE和SETTLE各一，终态/outbox一致 | 必需NOT_RUN |
| A2-P02 | 下游持久终局拒绝，FAILED、全路径释放不结算，RELEASE一条；该键不能迟到成功 | 必需NOT_RUN |
| A2-P03 | 读取/通知金额0但次数预留结算或释放正确；通知持久效果最多一次，读结果固定 | 必需NOT_RUN |
| A2-P04 | 接受提交前不得执行；提交后真独立子进程终止/重新启动，从持久状态恢复而非finally补救；保留pid/同步与DB断言证据 | 必需NOT_RUN |
| A2-P05 | 下游订单已提交响应丢失→UNKNOWN额度保留；同键恢复唯一订单、一次结算 | 必需NOT_RUN |
| A2-P06 | 下游成功、网关终局前崩溃；恢复无重复效果/账本/终局 | 必需NOT_RUN |
| A2-P07 | 终局事务节点/事件/outbox中途注入异常；全状态/计数/事件/outbox原子回滚，之后可恢复 | 必需NOT_RUN |
| A2-P08 | 查无结果后旧请求迟到成功；不释放，最终唯一效果和SETTLE | 必需NOT_RUN |
| A2-P09 | 双恢复者、过期旧worker竞争，独立连接barrier/event每组10轮；终态不被覆盖、一个终局/一个outbox | 必需NOT_RUN |
| A2-P10 | 接受后祖先撤销/过期/key停用，内部恢复可完成原意图；外部接受重试仍拒绝；真实授权查询本段须完整独立验证 | 必需NOT_RUN |
| A2-P11 | 当前报价改/删后的已有意图使用原成本/快照；新键要求有效报价；确定性miss→另accept→报价消失→安全重查命中；变grant/holder/参数、撤销、proof重放仍拒绝 | 必需NOT_RUN |
| A2-P12 | 下游金额/意图/完整快照错配且可能有效果→UNKNOWN保留预算，无伪成功/释放 | 必需NOT_RUN |
| A2-P13 | 根/中间不足或次数耗尽及接受/结算/恢复并发，10轮、全祖先不超限不负数、不反向锁/死锁无界 | 必需NOT_RUN |
| A2-P14 | 下游同键同意图和冲突、订单/通知均防重复，执行/查询无或错独立服务凭据拒绝、零泄漏/效果；不能只藏端口 | 必需NOT_RUN |
| A2-P15-CORE | 四个完整工具ID/版本，重复JSON键/SKU、bool/负/浮点/溢出数量、缺/空集合、scope不足、跨租户/关联错/URL路径注入、快照/祖先包含错等分层负例，零预留/效果。可信fixture授权不是真实验签 | 必需NOT_RUN |
| A2-P19 | 001及003真实非零预留/撤销/证据升级到004，七旧表全行及完整迁移登记在非法升级时不变；合法重复迁移no-op；旧材料不足sidecar隔离保预算，不能补当前报价执行 | 必需NOT_RUN |
| A2-P20 | 直接SQL改意图/成本/证据、删除重建路径/操作、改删事件/节点、阶段seq绕过、非法状态/双终局拒绝，旧账本不变；合法预算/撤销/状态UPDATE可用 | 必需NOT_RUN |
| A2-CKPT1-OBL01 | 候选前schema/静态授权/可信集合，不要求当前报价存在；命中原快照关联+当前权限后仍A1 accept锁后复核/proof/意图 | 必需NOT_RUN |
| A2-CKPT1-OBL02 | 确定性P11安全重查，包括任意资源/报价解析失败，而非仅金额错误；新键及失效/重放/变意图负例 | 必需NOT_RUN |
| A2-CKPT1-OBL03 | 可用候选完整持久接受事实；永久不可改删事件+非级联FK或明确DELETE保护防删操作，异常旧行隔离；P20不能靠doc承诺 | 必需NOT_RUN |
| A2-CKPT1-OBL04 | claim/终局owner+version+合法state+锁后DB有效expiry；无新owner时旧worker过期也拒绝；UNKNOWN保持且不释放未知预算 | 必需NOT_RUN |
| A2-CKPT1-OBL05 | sidecar不改七旧表、phase/seq CHECK、事件/节点UPDATE/DELETE保护、非法升级全数据和迁移登记保全，合法更新/测试自有清理兼容 | 必需NOT_RUN |
| A2-CKPT1-OBL06 | 下游执行/查询完整原快照持久化比对；不一致UNKNOWN；不可变outbox、receipt_id/created_at稳定、UTC整数秒iat；缺B PENDING且无伪编码/SM3 | 必需NOT_RUN |
| WF-A1-REGRESSION | A1原全部unit/PG集成独立实跑并保留U1/P1—14/F1—5语义与根重建、非零升级断言；不硬编码旧测试计数 | 必需NOT_RUN |
| WF-INDEPENDENT-PROBES | 最终reviewer独立设计绕过/边界探针，保存本轮可复现源与实跑日志；worker不替reviewer选择唯一反例 | 必需NOT_RUN |
| WF-QUALITY-CHECKS | ruff check/format、diff、全unit/骨架/docs/PG实跑；新增目录显式纳入CI；缺库报错不skip | 必需NOT_RUN |
| WF-PY311-ENV | 实际Python3.11、依赖安装/约束和真实PG验证；历史CI/本机3.14不能替代。本轮无授权触发远程CI，NOT_RUN不额外阻断但Python3.11本地必须验证 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。 | 必需NOT_RUN |
| WF-RESOURCE-ISOLATION | worker及reviewer各自独立project/唯一容器/DB/schema，记录归属label、来源、挂载/端口、普通DSN清除、安全目标；前后无关资源不变，清理仅owned | 必需NOT_RUN |
| WF-IMMUTABLE-BASELINE | 检查001—003内容checksum、A1语义、合法更新、无B代码/依赖偷渡。必要接口兼容须主控确认 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。 | 原静态义务NOT_RUN |
| WF-DOCS-REPORT | 报告tracked/untracked误措辞纠正，31ID→具体断言/函数/命令结果，README可复现初始化/worker/下游/测试/清理；真实网关缺B不可装配启动，CI不漏新测试 本轮语境：B已在候选内，保护原A语义和历史SQL；新用户已授权Git发布/CI/条件合并。 | 原静态义务NOT_RUN |
| WF-SNAPSHOT-COVERAGE | 主控/reviewer查完整tracked/untracked/deleted及契约SHA256，冻结开始/结束一致；无active writer才review，证据与报告指纹绑定 | 原静态义务NOT_RUN |
| B-01-CRYPTO | 成熟SM2/SM3、ALG/typ/rawJWS/userID/DER-rs严格；标准向量及OpenSSL双向实跑，不改PKCE S256 | 必需NOT_RUN |
| B-02-ENCODING | 全原JSON/Unicode/类型/大小深度/词数边界及raw/JWS/DID/SDK入口，合法负delta仅明确字段；原两issue正式独立闭环 | 必需NOT_RUN |
| B-03-IDENTITY | 默认did:web实际HTTPS/CA/目的/controller/SPKI/企业注册/拒redirect与未批准目标；不是全部仅注入字典 | 必需NOT_RUN |
| B-04-TOKEN-POLICY | 根/两级子各维收窄、空/缺约束拒、完整AS快照与A权限链真实绑定 | 必需NOT_RUN |
| B-05-INVOKE-PROOF | 原body/holder/endpoint/tenant/task/版本/业务键/proof拒绝，静态验证与最终接受分离，零新增状态 | 必需NOT_RUN |
| B-06-CODE-OIDC | 登录、state/nonce/redirect/S256/CSRF/cookie/code一次性；政策/TX/所有晚锁时效全部触发与变体 | 必需NOT_RUN |
| B-07-ROOT-ISSUANCE | 同task永久唯一根，code消费/根/proof/签名快照同txn；双code10轮，原数据不清零 | 必需NOT_RUN |
| B-08-DELEGATION | 父/接收者/完整链可信，签发不占预算；同key/失响应/真进程恢复，撤销/到期/key停用retry不复活 | 必需NOT_RUN |
| B-09-DYNAMIC-STATE | AS/执行/撤销统一锁序、锁后DBclock、完整祖先/key；内省active非永久许可 | 必需NOT_RUN |
| B-10-HTTP-TLS | 全路由格式/媒体/重复头与body/大小/超时/认证/角色/会话拒绝；固定HTTPS/真TLS/脱敏/无生产旁路 | 必需NOT_RUN |
| B-11-RESULT-READ | 真实专用query签验/精确DTO与权限投影；不伪invoke字段。A最终动态查询实现留A2.2且文档不可伪PASS | 必需NOT_RUN |
| B-12-EVIDENCE-RECEIPT | 受控原材料暂存/接受关联、独立AS/GW历史信任、真实规范投影/签验负例；持续outbox签发/导出留后段 | 必需NOT_RUN |
| B-13-ROTATION-INTEROP | AS/client/GW用途与生命周期、旧key历史验证及新调用停用；OpenSSL/源与非editable wheel真互验 | 必需NOT_RUN |
| B-14-DB-FAILURES | 真实DB故障/锁timeout/终止backend/serialization失败关闭和原子回滚，错误不误标坏材料永久隔离 | 必需NOT_RUN |
| B-15-CONCURRENCY-TEST-EFFICACY | 原全部竞争组各10轮，独立连接+可达同步、目标锁/PID/SQLSTATE/负控，不吞异常假PASS | 必需NOT_RUN |
| B-16-A1-REGRESSION | 全A1 U1/P1—14/F1—5与原5probe/等价更强升级，001—003历史checksum，原默认accept API | 必需NOT_RUN |
| B-17-B-SUITE-QUALITY | fresh3.11锁安装、完整source/wheel非集成SDK/PG/OpenSSL/TLS/demo/lint/format及全文测试效力/许可维护审读 | 必需NOT_RUN |
| B-18-RESOURCE-ISOLATION | 每worker/reviewer独占owner/容器/project/DB/schema/缓存，普通DSN清除、精确清理、原资源前后核对 | 必需NOT_RUN |
| B-19-CONTRACT-MERGE | freeze且实际实现invoke bundle/query/evidence/seq投影，调用方一致，原A2.1默认/checked路径不丢 | 必需NOT_RUN |
| B-20-MIGRATION-MERGE | 空库/common前缀/A-origin/B-origin合法升级、非零撤销证据、全部registry及失败原子性、重复no-op | 必需NOT_RUN |
| B-21-SHARED-FILE-MERGE | README/init/fixtures/conftest/deps/CI/migrate语义整合与完整manifest，不覆盖任何一侧功能 | 必需NOT_RUN |
| B-22-ORIGINAL-GOAL | 全M/SEC/CON/REC/AUD/E2E/ENG逐项真实等级/后段责任映射；不拿模块合并候选当比赛完成 | 原静态义务NOT_RUN |
| B-23-HANDOFF-REPRODUCIBILITY | README/手册/升级/初始化/角色/key/合成demo可复现，准确当前版本/限制，不复制B旧main未实现文字 | 必需NOT_RUN |
| B-24-FINAL-BINDING | 完整candidate/契约起止snapshot、每批receipt/native停止与完整独立报告/issue闭环 | 原静态义务NOT_RUN |
| BR-01-CONSENT-FINAL | policy晚锁跨request/session到期两类各10轮零code/event/approved；client key/DID耗时不漏最终期限；core，test_consent_final_decision.py | 必需NOT_RUN |
| BR-02-HTTP-REJECTION | 全挂载路径65536/65537、分块/中断/格式/媒体拒绝4xx；DB503/真实内部500准确，无效果/原敏感材料不回显；http，test_http_request_limits.py+integrator真TLS | 必需NOT_RUN |
| BR-03-PRIVATE-PATHS | FIFO/socket/directory/file及parent link/危险祖先权限/竞态拒绝，独占不覆盖、多umask真实CLI，所有owned子进程退出；private+integrator | 必需NOT_RUN |
| BR-04-LINEAGE-HISTORY | A001—006/B004—009原字节与编号不变，原registry旧行全部字段含applied_at保全，sidecar来源可核验；core | 必需NOT_RUN |
| BR-05-LINEAGE-ATOMIC | 未知/错filename/checksum/缺中间/混合/伪登记/孤立schema失败前后全业务/legacy+sidecar registry不变，并发迁移/真实中断/重复升级；core+reviewer | 必需NOT_RUN |
| BR-06-REAL-PERMISSIONS | 真AS根→两级子→完整snapshot→现有四工具接受/执行；改token/path/scope/holder/SPKI/resources拒、各祖先账本/下游效果正确；core+integrator | 必需NOT_RUN |
| BR-07-QUERY-DTO | 单一subject/method/query字段，真实签验与完整权限/evidence绑定；无tool/key虚字段/不预留不执行，下游动态查询后段明确不计完成；core | 必需NOT_RUN |
| BR-08-EVIDENCE-BINDING | 可信暂存不可改删、raw/digest/ref/当前proof精确关联，接受同txn first/retry独立link，注入失败proof/计数/关联全回滚，旧opaque材料不补造；core | 必需NOT_RUN |
| BR-09-RECEIPT-PROJECTION | 真A outbox材料phase/seq/节点集合验证后投影唯一v1，B规范+真实签验向量；未知字段/错seq/重复/错delta拒；原ID/iat/PENDING材料不变；core | 必需NOT_RUN |
| BR-10-IMPORT-PROVENANCE | 精确import-map及固定B blob/当前A hash，不覆盖A ledger.service/001—006/全部旧测试或原报告，全部增删rename/mode列入manifest；core+controller | 原静态义务NOT_RUN |
| BR-11-CLEAN-CANDIDATE | 整合后freshsource及非editable wheel、空/两legacy升级、全A/B套件、实际demo/TLS/README；CI配置显式包含所有新目录，远程未授权不触发；integrator+reviewer | 必需NOT_RUN |
| BR-12-WORKFLOW-BARRIER | 真人读回/所有包与实际plan版本、真实NEW模型ID/资源、每批双开工门/worker门/freeze和最终require-accepted门；结构检查不替代语义；controller+reviewer | 原静态义务NOT_RUN |
| A2-P15 | 真实授权公开HTTP下全部非法参数、别名、重复JSON/SKU、bool/浮点、空缺集合、注入、跨租户/资源关联、scope/祖先快照错配：拒绝且零效果/零预留；完整原断言，不只分层CORE | 必需NOT_RUN |
| A2-P16 | 真实B验签公开调用缺/错token/proof、换body/holder/endpoint、盗token、重放拒绝；父私钥不能使用子token，零业务变化 | 必需NOT_RUN |
| A2-P17 | 真实result-read仅原tenant/task/subject/root/grant/holder/kid、当前权限；锁后TTL/全祖先撤销/停用；新proof并发/重放；查询无业务计数或下游/租约效果 | 必需NOT_RUN |
| A2-P21-HTTP | 真实受信CA HTTPS的正常四工具采购/读取/通知与查询，固定endpoint、202/error和重复返回当前状态；持续回执签名明确留A2.3，不将完整P21标PASS | 必需NOT_RUN |
| A22-01-REUSE | 复用真实InvocationVerifier/VerifiedExecution/ExecutionService；不复制SM2/SM3/编码/OAuth；生产装配只允许真实provider/evidence/execution | 必需NOT_RUN |
| A22-02-TRANSPORT | 可信ASGI https、固定两条POST路径；不从Host/Forwarded推htu，拒query/fragment变体、编码路径绕过、GET/未知/管理路径、Bearer/DPoP降级 | 必需NOT_RUN |
| A22-03-FRAMING | 请求/响应/头大小有界，拒重复敏感头、组合凭据、非法ASCII/CRLF、Content-Length/Transfer-Encoding歧义、压缩、错类型、断连、body过大/深度/重复键/NaN；不消耗业务预算 | 必需NOT_RUN |
| A22-04-INVOKE | 首次invoke202返回operation_id与真实status/receipt_status，事务提交后内部worker执行；HTTP不隐式启动业务或签名；已终态同键新proof仍202但status不伪RESERVED | 必需NOT_RUN |
| A22-05-QUERY-BUNDLE | 新增可信query bundle保留PermissionSource及opaque evidenceRef，保原canonical-result API兼容；不可从请求构造可信对象/自报权限 | 必需NOT_RUN |
| A22-06-QUERY-LOCKS | 真实PG锁序principals排序→task→root-leafgrants→operation；检查完整不可变授权链；不伪装invoke DTO或放宽A1purpose；与接受/恢复/撤销锁序兼容 | 必需NOT_RUN |
| A22-07-QUERY-OWNERSHIP | 查询仅原授权节点、holder/key、tenant/task/subject/root；当前权限仍覆盖原tool/params且原操作可核验；跨身份猜ID拒绝不泄露存在/内容 | 必需NOT_RUN |
| A22-08-QUERY-FINAL-CLOCK | 所有可能阻塞的证据/行读取/约束处理后最终DBclock_timestamp；重读已锁key/全祖先并检查token/proof及grantnotbefore/expiry；等待或latebinding超过TTL拒绝，事务完整回滚 | 必需NOT_RUN |
| A22-09-QUERY-REPLAY | 查询proof唯一kid/purpose/endpoint/jti并同事务operation/evidence关联；并发同proof最多一成功，10轮；失败不消耗proof，不覆盖首次证据 | 必需NOT_RUN |
| A22-10-QUERY-ZERO-COST | 读取RESERVED/EXECUTING/UNKNOWN/SUCCEEDED/FAILED合法状态；result仅可信持久事实，回执null/PENDING；不创建操作/事件/outbox、改预算/lease或执行下游，beforeafter全路径计数/业务行一致 | 必需NOT_RUN |
| A22-11-QUERY-EVIDENCE | query_binding在同事务验证真实raw/token/proof/body/context/source对应关系，换ref/错source/legacy不全拒绝；不把query写作invoke retry；优先ag_proofs关联无迁移 | 必需NOT_RUN |
| A22-12-QUERY-PERMISSION | 当前签名token、DB权限源与历史原操作所需资源/tool/收窄逐项一致；坏可信源/不完整链/缺原事实失败关闭，不能靠签名或缓存放行 | 必需NOT_RUN |
| A22-13-DYNAMIC-RACES | 真实撤销/key停用vsquery/accept线性化及锁等待TTL、lateDB依赖；独立连接event/barrier每组10轮、捕获全部异常和完成，负控证明触发目标 | 必需NOT_RUN |
| A22-14-ERRORS | 9.6网关稳定嵌套error{code,request_id}：400schema、401signature/holder/stale+AGPoPchallenge、403scope/revoked/expired、409replay/intent/quote、422budget/calls、503trustedstate；不按异常文字猜分类 | 必需NOT_RUN |
| A22-15-FAIL-CLOSED | PG/身份/权限/证据不可用/超时失败关闭，无零超时配置；HTTP事件循环不被同步DB阻塞，等待有界；503后潜在工作仍遵守原子性/幂等，不宣称线程已被杀 | 必需NOT_RUN |
| A22-16-PRIVATE-CONFIG | 独立网关配置只需AS公开信任key和已批准identity；不加载AS签名私钥、代理私钥；服务secret与DSN独立私有且不输出；配置不可通过alias变更信任 | 必需NOT_RUN |
| A22-17-STARTUP | 明确gateway init/check/run及内部worker调用，TLS证书/配置/key/provider缺失拒启动；不默认DSN、不测试替身/跳验开关、不自行迁移/reset部署DB；网关/下游独立事务与凭据 | 必需NOT_RUN |
| A22-18-REAL-TLS | 真实网络gateway进程和开发CA，默认客户端证书/主机名校验；错误CA/host拒绝、公开签名域名仍固定；不得sslverifyfalse；独立PID/就绪/退出证据 | 必需NOT_RUN |
| A22-19-PRIVACY | 所有响应/log/CLI stdout stderr不泄原token/proof/secret/DSN/privatekey/内部栈/其他租户；合成标记负例验证，request_id由服务生成不回显攻击者header | 必需NOT_RUN |
| A22-20-BOUNDARIES | A2.3持续签名、A3锚定/导出/部署/规模实验未做；outboxPENDING/receipt_jwsnull，UNANCHORED材料仍不冒充独立审计；P21/P18后段子断言明确 | 必需NOT_RUN |
| A22-21-DOCS | 同步当前HANDOFF/README/A2-report/context/stage及接口/安全/验收文档，修正旧当前状态；保历史契约/报告/SQL/锁；干净clone本地链接和可执行CLI复现 | 必需NOT_RUN |
| A22-22-REGRESSION | 继承67项/60原独立运行义务全部保持，完整source及非editablewheel正式测试/独立探针/历史失败与等价适配按原要求重跑；新增query不能改变A1accept/API | 必需NOT_RUN |
| A22-23-ENV-PROVENANCE | worker/reviewer各独占Python3.11/PG16，精确runtime/devlock及PEP517setuptools80.9；wheel不受srcshadow且携带全SQL，父/子进程来源见证 | 必需NOT_RUN |
| A22-24-FREEZE-RESOURCES | 全候选tracked/untracked/deleted/modes起止SHA，原生writer停写/资源owner核；禁止共享DSN/容器、仅清自有资源，证据完整退出码/hash/JUnit | 必需NOT_RUN |
| A2-P18 | 完整原P18：真实持久发布、签名失败/签后保存前真崩溃/保存后返回丢失、receipt_id/payload/iat稳定、业务不重做、篡改结果/路径/delta拒绝 | 必需NOT_RUN |
| A2-P21 | 完整原P21：真实登录同意/根授权/两级委托、四工具HTTPS调用、内部持久终局、发布、当前授权查询与独立可信公钥回执验签 | 必需NOT_RUN |
| A23-01-REAL-SIGNER | 复用crypto.sm真实SM2/JWS/SM3与evidence.receipt独立验签，不复制密码实现、不假Verified对象 | 必需NOT_RUN |
| A23-02-KEY-SEPARATION | 独立网关receipt私钥/kid，拒AS/holder角色重用、缺key/公钥不匹配；AS/holder/downstream分离；HTTP不加载signer私钥 | 必需NOT_RUN |
| A23-03-PRIVATE-INIT | 显式init独占private_files，安全权限/路径/symlink/已存在原文件不覆盖；只合成key，check离线、run缺配置失败关闭，无默provision | 必需NOT_RUN |
| A23-04-TRUST-ROTATION | 外部可信GW历史公钥配置、发布当前kid、旧Ready按旧kid验签且原字节稳定；未知kid/自带key/缺历史key失败关闭 | 必需NOT_RUN |
| A23-05-IMMUTABLE-MATERIAL | 终局op/outbox/原首次token-proof-request/context/source/完整ASsignedchain/报价/result/path/event/delta全绑定；错误/缺/legacy原件失败关闭 | 必需NOT_RUN |
| A23-06-ATOMIC-PUBLICATION | 真实PG有界TX条件PENDING→READY，仅receipt_status/JWS/signed_at写；READY字节/签发时刻/材料不可变，不创建第二outbox，无其他业务写 | 必需NOT_RUN |
| A23-07-STABLE-CLAIMS | UUID5receipt_id、iat从created_at；首次token/proof/intent/result/ledger规范摘要及完整17claims；重签前崩溃payload不变，保存后JWS字节不变 | 必需NOT_RUN |
| A23-08-SIGN-FAILURE | 密码后端或存储错误失败关闭，PENDING/null保留、无下游/计数/lease/event/终态改变，故障移除原操作正常发布 | 必需NOT_RUN |
| A23-09-PRECOMMIT-CRASH | 真独立publisher进程在sign后commit前SIGKILL；原资源/数据库持久无假finally；新PID恢复同payload/id/iat仅一次持久发布；未提交SM2重签字节可不同 | 必需NOT_RUN |
| A23-10-POSTCOMMIT-LOSS | 真进程保存READY后响应未交付/死亡；新进程同id获取原JWS/signed_at，无重复签或效果 | 必需NOT_RUN |
| A23-11-CONCURRENCY | 多publisher独立连接/真实barrier/DB锁每组10轮，claim/重复同op/恢复竞争；完整祖先四计数/业务/全部DS表不变，唯一Ready | 必需NOT_RUN |
| A23-12-HISTORICAL-FRESHNESS | 已接受操作撤销/过期/key停用后内部终局/发布仍可完成，原件历史共同窗口验证；外部invoke retry/query必须当前权限/新proof | 必需NOT_RUN |
| A23-13-PUBLIC-READY-QUERY | 专用query严格A2.2全部动态授权、全晚等待finalclock；PENDING兼容/READY真实persistedreceipt验证、badsignature/错claims/digest/type/key503 proof回滚 | 必需NOT_RUN |
| A23-14-PUBLIC-INVOKE-STATUS | 202首次Pending/terminalretry实际receipt状态；所有额外publication读取/验签在接受TX最终clock前，禁止commit后lateDBwait泄漏已过期证明 | 必需NOT_RUN |
| A23-15-NONTERMINAL | RESERVED/EXECUTING/UNKNOWN没有最终outbox/receipt；内外非法状态均拒绝，不伪FAIL或释放 | 必需NOT_RUN |
| A23-16-INTERNAL-CLI | 真实可持续重启内部publisher CLI，仅operator严格私有配置（不发明签名配置协议）/显式DSN；bounded polls/attempts/SQL/错误脱敏，一个坏材料不饿死其他合法待签项；无公开sign/recover管理路由 | 必需NOT_RUN |
| A23-17-REAL-HTTPS-CHAIN | 受信CA+固定AS/GW hostname验证的真实login/consent/code/IDtoken/两级exchange/fourtool/query；非线程inprocess假全链，持久DB归属明确 | 必需NOT_RUN |
| A23-18-ATTACK-CLOSURE | 完整HTTP路径token盗用/bodyholderendpointtamper/replay/crossowner/currentrevoke拒绝，beforeafter全祖先业务及DS零越权/重复效果；公开response不暴露raw证据/secret | 必需NOT_RUN |
| A23-19-OFFLINE-MUTATIONS | 独立ReceiptTrust真实verify_receipt_bundle，结果/amount/祖先缺重排重复/全节点delta/首次proof/token/receipt类型/kid篡改失败；UNANCHORED边界 | 必需NOT_RUN |
| A23-20-SOURCE-WHEEL | 完整source+非editablewheel Python3.11 PG16锁安装/14SQL/真实parentchild模块来源/新CLI README流程/所有A1A2B95回归/原历史等价与失败 | 必需NOT_RUN |
| A23-21-A2-ACCEPTANCE | 完整P01-P21逐原断言及M/SEC/CON/REC/AUD/E2E/ENG30目标映射；A3锚定/导出/规模/三代理编排标NOTRUN不移除目标；只声明完整A2 | 必需NOT_RUN |
| A23-22-FREEZE-RESOURCES | 所有workers native停写/只读依赖精确scope/全候选起止哈希、freshreview完整矩阵原始日志/失败/资源fullID与0余留；不碰无关资源 | 必需NOT_RUN |

## 冻结设计契约

## 2. 实际API与建议冻结的最小扩展

实际已有：crypto.sm.sign_compact_jws / verify_compact_jws / sm3_b64url；evidence.receipt.ReceiptTrust / verify_receipt_bundle；execution.receipt_projection.ReceiptProjection / project_receipt(conn, operation_id)；EvidenceStore.binding(bundle)的逐调用closure；ExecutionService.accept_invocation(..., binding=...)；ExecutionLedger.accept_bound(..., existing_validator=..., binding=...)。后者在CREATED与EXISTING callback后处理proof链接，再 `_final_bound_check` flush deferred constraints并最终DBclock，无需改ledger.service。

建议新API冻结在 execution/receipt_publication.py：

* `ReceiptPublication` frozen DTO：operation_id, receipt_id（非终态为null）, receipt_status, receipt_jws, signed_at。无私钥/原件字段。PENDING只有null签名与null signed_at；READY二者有效。
* `ReceiptVerifier(*, issuer, as_keys, gateway_keys, registrations: Mapping[tuple[str,str,str], RegisteredIdentity], permission_provider: PermissionSnapshotProvider)` 持独立issuer/AS/GW公钥、完整可信tuple registry及冻结PermissionSnapshotProvider；不再接收整表静态ReceiptTrust。同conn使用`scoped_trust_tx`按真实验签AS全链、DB绑定、完整first context与合法共同历史时窗确定exact tuples，仅构造该链的新ReceiptTrust并调用原SDK；禁止全表按kid flatten/last-wins、新global kid unique、未验签raw自报选择信任和实例共享trust切换。`read_tx(conn, operation_id) -> ReceiptPublication` 同事务读取outbox及完整投影/首次原件；终态PENDING仍严格验证材料；READY构建AG-EVIDENCE-1并调用真实verify_receipt_bundle，且decoded receipt全部17claims与project_receipt.claims_bytes精确相等。拒绝签名正确但错iat/id/op/digest/result/path的材料。UNKNOWN等非终态无outbox返回PENDING/null；任何非终态带outbox失败关闭。
* `InternalPublisher(dsn, *, private_key, signing_kid, verifier, connect_timeout=5, lock_timeout_ms=10000, statement_timeout_ms=15000)` 真实SM2私钥与公钥匹配，禁止AS/holder SPKI角色复用。`publish(operation_id) -> ReceiptPublication` 完整有界事务；`pending_page(*, after_operation_id, limit)` 有界keyset只读候选列表。具体数字可收窄，不可设0无限。
* publish锁自己outbox行FOR UPDATE；不反向锁principals/task/grants/op。读取终局不可变operation/path/events/source/evidence/result/报价；签验原件共同历史窗口，真实SM2签名后真实自验与完整claims一致；UPDATE仅WHERE receipt_status=PENDING；写READY/JWS/signed_at三个字段，commit后仅序列化DTO。READY命中验证原保存签名并返回原字节，绝不重签或更新timestamp。
* `VerifiedExecution.accept_response(bundle, *, receipt_verifier) -> dict` 保现有accept API/AcceptResult。每次调用独立closure先执行原EvidenceStore.binding，随后同一conn/op读取严格publication状态与材料，存逐调用局部结果。原accept_bound所有wait/finalclock/commit完成后才形成 `{operation_id,status,receipt_status}`；没有额外SQL。事务重试时closure数据覆盖/清空且返回仅当前成功attempt，禁止实例属性或线程串话。CREATED无outbox为PENDING；terminal EXISTING READY真实状态。callback返回之前publication读取/验签全部完成，不能commit以后另read补状态。
* AuthorizedQuery增加可选只公钥ReceiptVerifier；保原PENDING无receipt_keys兼容。READY无可信key或者坏signed_at/签名/claims503且query proof回滚。所有public响应编码/验签/投影/约束和晚wait在最终时效检查前；当前完整key/ancestor/source/ownership/proof规则不变。

原件 helper 放 execution/original_material.py：复用当前 AuthorizedQuery._original 完整context逐字重建；query传当前经过真实verify的PermissionSource。publisher不能把当前now传 PermissionSnapshotProvider.load 来拒历史过期操作，也不能把 evidence中的source自报JSON当权威；从同事务真实DB grant/token不可变快照、独立历史公钥登记、真实签名claims及共同历史时间重建PermissionSource，再与原first.source.material()/context核对。PermissionSnapshotProvider.load_tx按v2前置决策同conn重建source，共用私有_from_records唯一原校验体，旧load生命周期保持；revalidate同conn比较既有binding。不新开provider连接跨事务装配、不复制B授权逻辑、不用current DID倒推历史key。此共享路径已精确加入core14；不同额外shared改变仍须重新加scope审包。

execution/store.fetch_outbox当前没有 signed_at（行147—169）；本段最小添加读取字段及专用锁outbox/条件发布helper。SQL004只限制PENDING/null与READY/non-null并保护READY不可变，没有signed_at有效性CHECK；这是静态schema事实而非新确认产品漏洞。服务必须检查PENDING非null signed_at、READY空/未来/早于created_at等不一致，错误失败关闭。未有证据需要新SQL，不改历史checksum。

## 3. 配置与CLI冻结边界

public GatewayConfig增加唯一可选`receipt_keys`（kid->SM2 public PEM）字段；缺字段严格兼容旧config=PENDING-only；显式空/错误/unknown字段拒绝，不静默忽略。new keys不可alias改变；AS/holder/gateway按canonicalSPKI比较角色分离，新receipt signing kid角色冲突拒绝；现有不同tenant/client holder共享同DID/kid/SPKI合法登记保留，不加global kid唯一限制。HTTP factory传完整tuple登记和冻结provider给ReceiptVerifier，仅持公钥并按op已验链构造ReceiptTrust，永不读取signer私钥。历史kid保留，轮换只能新kid、新公钥；旧READY/JWS原样验证。

private publisher config固定字段建议：`profile, gateway_config_path, signing_kid, signing_key_path, connect_timeout_seconds, lock_timeout_ms, statement_timeout_ms, batch_size, poll_interval_ms`；exact schema、positive bounded整数（bool拒绝）。profile GM-MVP-1，不含DSN、AS/holder私钥、downstream_secret。operator路径读取全用既有descriptor-bound private_files，不仅chmod检查。`check`与`run`相同loader/builder/key一致性；check无DB连接。

`python -m agent_guard.gateway.receipt_worker init --out NEW --gateway-config OLD --kid NEWKID` 只新建0700目录和0600 signer PEM/publisher.json/gateway-public.json；旧input字节不变；公钥基于真实CSPRNG独立SM2私钥。原public config secrets_path若相对旧目录，写新副本须安全解析为原绝对引用；不复制或读取downstream secret，不复制AS/holder私钥。拒已占kid、已有目标/symlink/unsafe ancestor/自然open错误，多umask/竞争进程真实负例。部分失败只能留安全私有部分文件且明确失败，不覆盖旧文件或修权限。

`check --config`; `run --config`仅显式`AG_RECEIPT_DATABASE_URL`，缺省失败，不fallback部署普通DSN；无自动migration/provision/reset。bounded batch keyset轮转，坏材料不永久饿死后续合法pending；一个周期失败收集但不泄raw/DSN/栈。内部publisher是直接服务/CLI，不新增公开sign/recover管理路由。不称配置operatorsigned：配置安全加载而非发明签名配置协议。

## 4. 串行前置后可审并行

ownership-v2.json列逐文件，没有目录glob许可。core先独占共享前置和其测试，native stop/资源清理/范围核验后冻结实际constructor/helper/DTO/API与其内容SHA。CLI/config与HTTPS fixture/demo再各自fresh PACKAGE_READY绑定同一冻结前置才并行，各不读对方未冻结源码或fixture。HTTPS可以直接调用冻结InternalPublisher；CLI加入真实联合闭环由final integrator串行完成。所有worker停止后精确写权转移给单integrator，整合必须完整selfcheck。共享API变更先停止消费者，重冻结和重新审包，不能交叉写。

core/cli/https/integrator各owner以本包精确所有权标签为准，reviewer另用新的独占标签，各独占ignored证据/源码copy/wheel/venv/cache/PG16容器/network/随机TEST gateway库与独立downstream库/端口/CA/PID。所有parent+child源来源可核，命令仅自有TESTDSN，普通DSN清除。创建前后fullIDs/labels/mount/config/project与资源清单留存，只有实际成功创建同owner可清理；不连接agent-guard-a2-pg/verivote或其他worker资源。当前本计划资源全部NOT_CREATED。

## 5. 故障、拒例及P18/P21的真实证据

共同效果oracle：before/after每层四计数、ag_operations全部原列、event+node、lease/fencing、outbox全部材料、first/retry evidence及query proof绑定、ds_*所有业务表。publication只允许三个发布字段变化；失败全回滚PENDING/null，不重执行下游。query合法仅新proof绑定与允许STAGED审计材料；非法proof rollback，修原数据用同proof成功随后重放409。修改raw/context/source/quote/result链等保持原故障原件与精确预期typedcode；未知程序错保500，不按文字分类。

签发失败至少真实backend签发错误/错key/type/储存约束或真实PG中断分类验证，恢复原条件后发布同operation；测试注入和真DB故障分别记录。core sign→commit SIGKILL须独立真实子进程直接调用冻结InternalPublisher，不导入尚未写CLI；CLI阶段由tests/integration/test_receipt_worker_process.py使用实际receipt_worker PID重复两故障窗口，S2整合完整P18。core SIGKILL须实际完成真实sign后在自有PG outbox UPDATE或commit deferred barrier同步，确认pg_stat_activity/backend PID目标等待，SIGKILL后新PID持久PENDING并恢复。测试自有barrier函数/触发器不是产品迁移；不得生产ENV hook。commit→响应丢失须确认独立连接已见READY再阻断实际stdout/IPC交付或杀独立publisher（关闭读取端真实broken-pipe也可），新PID取原JWS/signed_at；不能仅raise模拟网络。该内部publisher/CLI故障不是“真实TLS网络断网”，真实网关返回丢失可另有HTTPS连接关闭证据。SM2随机签名在precommit重试可能不同，只要求payload/id/iat稳定；一旦commit JWS字节不变。

并发每组10轮：同op双publisher、publisher/query、publisher/invoke retry、两恢复者/旧worker、撤销/停用与外部query/accept；独立连接、barrier/event、全部future异常收集、PID/SQLSTATE与正负控证明窗口可达，不sleep碰运气。签名行锁不能与执行锁形成反向锁。

完整P21新增一个同场景真实网络联合链，不能拼接两个历史TLS测试：固定 auth.agent-guard.test/gateway.agent-guard.test + 受信开发CA/SAN hostname，独立AS/GW进程；浏览器GET登录CSRF→POST密码→authorize state/nonce/精确redirect/S256→consent→code-exchange真实AGPoP→RP验证IDToken→planner到selector、selector到executor两次真实AS exchange（不同Basic/SM2 key）→procurement.request.read、procurement.document.read、procurement.order.create、notification.template.send四个ToolId/version字符串1真实HTTP（notification.send与全部短名仅负例）→内部执行独立下游持久终局→InternalPublisher真实签发→当前授权新proof query READY→独立ReceiptTrust offline verify。每工具唯一效果/预算/稳定回执；notification引用已有可访问操作。wrongCA/wronghost/盗token/父key冒child/bodyendpointtamper/replay/跨owner/revoke/tokenTTL各真拒例且全效果零新增，响应无raw证据或secret。

## 6. 容量疑点 NOT_CONFIRMED

evidence/receipt.py 195—200对整个非ledger outer默认canonical_json_bytes：MAX_JSON_BYTES65536、MAX_JSON_NODES4096、depth64、累计stringbytes65536。最终1MiB检查之前可能先拒聚合。纯静态上界：ancestor_tokens三段各≤16384，token_jws重复leaf再≤16384，proof_jws/receipt_jws各≤16384，最多六个16KiB字符串=98304（未计request/result/keys/envelope）；这只是schema上界，不证明同时真实合法。token限制、完整PermissionSource.material的重复token与snapshot封装64KiB、7约束集、SKU权限字符串/HTTP64KiB/签名body编码和result关联共同限制实际可达宽度。256条短SKU是待真实AS/HTTP证明的合法容量候选，256条128字符SKU无法只按DTO估算当作真实合法最大，更不能56187 DTO shape冒充HTTP合法上限。当前没有实际合法业务阳性或PASS、没有新confirmed static defect。

建议正式core允许 evidence/receipt.py 精确有条件最小修正：先在新tests中获得真实AS登录授权/两级委托、公钥登记、合法public256SKU请求/持久result/receipt材料的容量阳性，验证每component原profile限额；若可达外层过早拒绝，保原v1所有签名输入/17claims/typ/JSON限额，通过严格outer字段schema，逐component调用原canonical_json_bytes，ledger专用canonical_signed codec；outer准确尺寸=2+各canonical key长度+colon+canonical value长度+逗号，<=1048576（不是ledger+nonledger两个对象的近似和）。ancestor_tokens数组仍1—3且各ASCII16KiB；request/result分别64KiB/depth/node不全局放宽。objects接口版本AG-EVIDENCE-1保持；容量校验语义变动在formalpkg明确v1兼容扩展理由/原拒例保持。若需改变签名/编码共享语义，则另版本/兼容提案审包，不能先实施。query result+receipt envelope仍65536，真实最大业务组合精确encoded长度验证，不默认扩HTTP response；超限503 proof回滚。此scope并非必须制造容量缺陷才能发布。

## 7. 项目30目标和剩A3

完整A2必须重跑M1—M9/M11—M13、SEC-01—07、CON-01—03、REC-01—03适用全部原断言：M1/2/3本段P21联合入口；M4/5 SEC04/05真HTTP攻击；M6 CON01/02完整根/中间竞争；M7 REC01/02真故障及P18发布；M8 SEC06撤销；M9真offline全关联与UNANCHORED；M11唯一根；M12合法256/重复SKU/全资源约束；M13 late-lock TTL与收窄父子真实期限。E2E-01本段完成确定性真实联合HTTP采购/攻击验证，但A3.3还需可交付三代理编排/五分钟演示/部署流程。

准确剩余责任：M10/ENG-01 A2锁安装/sourcewheel/README仅部分，A3.3干净TLS部署初始化/攻击demo，A3.2完整证据导出；AUD-01 A2单笔签名/结果/祖先/delta关联部分，A3.1真实独立检查点和连续记录，A3.2重排/删除/相对最新外部锚点回滚检测；AUD-02 A2 UNANCHORED限制说明，A3.2独立最新锚点/未锚定尾部报告。E2E-01 A3.3部署/三代理产品演示。性能50客户端/≥10000调用、Bearer和无原子预算公平消融、各样本/错误/效果/开销分解、CPU内存DB配置/重复批次与原始数据、版本一致技术材料在A3.4。四段逐段fresh正式建包→工作→完整独立验收，不提前把这些目标移除或PASS。

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

## 设计来源与限定

`requirements-v2.json`完整119/112及逐参数/断言/whole-effect/owner/phase；`ownership-v2.json`core14/CLI4/HTTPS3/docs7精确28路径与conditional29。主控decision已读取内容SHA：5db6d960a13fcc08c90884ccbe817133496e0c20aef5f8eedafc3e508e081c0c。原设计私有permission helper不得复制授权validation；本正式v2以新增permission_snapshot共享接口单validation为准。capacity仍NOT_CONFIRMED仅conditional，未声称真实合法最大案例或PASS。实际接受commit/原始collection/全部当前只读文件SHA已由正式附件绑定；新API仍未实施，core停写后必须核实际内容和消费者依赖。规划作者不会参与独立包审。

private配置数值拟冻结：connect_timeout_seconds 1—30（默认5），lock_timeout_ms 1—60000（默认10000），statement_timeout_ms 1—60000（默认15000），batch_size 1—256（默认32），poll_interval_ms 100—60000（默认1000）。所有exact int/bool拒绝、0及负/超上界拒绝，check/run同loader；不增加持久lease/新的SQL/依赖。ReceiptPublication非终态receipt_id=null；PENDING/READY结构与signed_at一致性必须验证。容量codec若无真实合法可达证据不得擅改，仅在formal conditional精确授权/独立包审后按最小方案。

## 设计修订与精确作用域（行为均NOT_RUN）

本正式包等待独立PACKAGE_REVIEW，NOT_PACKAGE_READY / NOT_ACCEPTANCE / NOT_RUN。A22真实接受API/commit/collection及当前全部只读依赖SHA已绑定正式附件；新API须实施后停写再冻结，消费者另审。所有旧草案原件字节保留。

P21所有正例精确ToolId为procurement.request.read、procurement.document.read、procurement.order.create、notification.template.send，tool_version均字符串1；notification.send及其他短名只作为零新增效果的拒例。

A23-19 unit仅codec边界。core在tests/integration/test_receipt_publication.py拟test_real_as_public_256_sku_capacity_publish_query_offline：真实AS根与两级子、合法短唯一256SKU、实际公开HTTP接受及PG result/terminal/outbox持久、真实签发/当前query/独立SDK offline，source+noneditablewheel完整运行；不消费未来a23_https fixture。后HTTPS阶段tests/integration/test_gateway_receipt_https.py拟test_https_real_legal_256_sku_capacity_receipt_pipeline将同材料放入真CA/SAN AS+GW进程闭环。SDKouter过早限额仍NOT_CONFIRMED，合成blob/DTO算术不是容量可达阳性；只有该真实pipeline确认后才审准conditional第29路径最小逐component旧profile与strictouter准确括号/key/冒号/逗号长度<=1MiB，不扩任何component/JWS/global JSON/public65536。超限公开query503 proof回滚；保留原失败证据。

P18 core真独立子进程直接调用冻结InternalPublisher，真实SM2 sign后PG barrier/PID/SQL wait确认再SIGKILL，新PID同PG恢复PENDING；commit→reply丢失以独立conn见READY后真实stdout/IPC丢失/kill，新PID取原JWS/signed_at。CLI phase实际receipt_worker PID承接两故障窗口；S2 sole integrator及fresh reviewer完整P18。仅receipt_status/receipt_jws/signed_at允许发布变化，全部原件/计数/event/node/lease/DS保持，payload/id/iat稳定，commit后JWS稳定；竞争组10轮和所有异常/正负控保留。

新增confirmed仅规划compat A23-PREFLIGHT-R1-TUPLE-SCOPED-TRUST：Gateway trusted registrations保持(tenant,client,kid)。拟ReceiptVerifier构造持独立issuer/as_keys/gateway_keys、完整tuple registrations及permission_provider。拟original_material.scoped_trust_tx(conn,operation_id,*,issuer,as_keys,gateway_keys,registrations,permission_provider)只在同conn完整真实AS签验/DB binding/合法历史时窗/完整firstcontext后返回单链ReceiptTrust；SDK链内DID唯一保证kid映射清晰，继续调用原verify_receipt_bundle比17claims，不复制授权或签验。当前query传current source并保持完整原firstcontext；publisher历史source用load_tx共用唯一_from_records，旧load先关闭own conn再validation的生命周期不变。禁止raw自报选择信任、whole-registry flatten kid last-wins、global kid unique、current DID倒推历史和共享可变trust；HTTP公钥，new signingkid与AS/holder角色分离。

A23-04/12/13具体追加节点：unit/test_receipt_publication.py::test_scoped_receipt_trust_preserves_exact_legal_registration_tuples；integration/test_receipt_publication.py::test_two_legal_operations_shared_holder_kid_publish_independently；integration/test_gateway_receipt_query.py::test_shared_holder_kid_current_query_and_offline_use_operation_scope。双tenant/不同client共享同DID/kid/SPKI，实际AS独立根→public accept→terminal→publish/query/offline两个均合法；登记forward/reverse、SUCCEEDED/FAILED、sequential/10轮concurrent，错exact tuple/SPKI/cross-owner真负例，bad material proof回滚、修复同proof200再409，全部oracle/三字段only/原件稳定。所有名字PLANNED_NOT_IMPLEMENTED_NOT_COLLECTED_NOT_RUN；实现停写后才actual collect/实跑/绑定精确参数节点及断言行。无新需求ID，无新任意路径。

core14先停写冻结实际接口，再消费者fresh包审，CLI4/HTTPS3独立并行不消费peer半成品。all native STOP且owned0后主控精确transfer28（conditional29须确认/包审）给sole integrator，全sourcewheel/历史/A1/14SQL/原95+A23/P18/P21/30goals完整自查；起止manifest及失败原件保全，新fresh119/112完整验收，不引入可选视频、生产DID/RPC硬门，不放宽安全或略过审查。



## 41节点、真实时窗和故障验证的执行契约

node-bindings-v2.json每个file/function仅声明一次，sole_initial_owner/phase/local assertion atoms明确；local refs联合覆盖父must_assert，G1仅完整整合实跑、G2仅主控实际native冻结/资源核验。不得将每个node重复映whole parent、发明笛卡尔参数或把计划名当collected证据。完整node具体值、案例及原source path见附件，原38测试/3独立静态检查均须最终闭合。

真AS短窗使用实际root8s、mid最多6s、leaf请求3s，每次exchange ttl=min(requested,parent.exp-actual_now-2)>0并核真实签名/持久deadline；余量不足fixture必须真实报失败并改善创建时机，不放宽时效、改clock、重试去掉失败或skip。真实1s AGPoP，positive释放时DBclock<exp，negative到达exp后释放；每added晚依赖与原8wait/4window正负组各10轮，保barrier/event、backend PID/目标SQL、全部异常和完整ag/DS3 oracle。祖先到期同时可能约束子/token，不称隔离父过期。

新增晚依赖包括outbox、projection、key lookup、source load_tx、deferred constraints；所有当前auth/proof/serialization/SDK检查都先于最后DBclock和commit，commit后无额外SQL。真实签后保存前SIGKILL由core直接InternalPublisher独立PID完成；CLI阶段再真实receipt_worker PID重现。保存后独立conn观测READY，再真实stdout/IPC loss或kill、不同PID恢复原字节，不能把raise称网络故障。每竞态10轮独立连接与可达同步，sign/commit/reply/效果精确层次区分。

真实容量不是DTO算术：实际AS根/两次委托、公网固定真实接受、PG报价/result/terminal、publish/query/offline全部处理256短唯一SKU(s000..s255)、qty1/unit1，共256分；原JWS16KiB、组件JSON64KiB/depth64/nodes4096、公开响应64KiB均不扩大。仅确证合法实际材料外层64KiB聚合早拒才申请精确SDK第29path/语义修订、fresh重新审包；不得因codec/blob单位阳性自行扩大scope。合法边界不达时保原失败及真实原因，不用更短请求冒充256最大测试。

持久坏材料/READY测试setup与恢复只在已核owner的独占测试namespace，若需要模拟存储损坏则精确test-only写/恢复并立即恢复原trigger，明确不是普通生产SQL允许或修复API。生产直接SQL不可变/READY原字节保护须另外真实拒绝回归；不在生产增加关闭trigger/skip路径。坏可信READY503及query proof原子回滚、未知程序错误500、材料修复后同proof可用/重放409仍需真实观察。

core串行仅自己的14路径与节点，自查全部core语义/真实故障/源与wheel关键回归，原生停写并自有资源0后主控冻结实际API和共享fixtures。每消费者另开fresh包审核真实冻结依赖，再CLI4/HTTPS3精确独占并行；不能读peer半成品。all STOP后主控将exact28 union转唯一integrator，单writer联合整合与7docs，完整source+非editablewheel Py3.11/PG16、所有普通/PG/quality/14SQL/锁/PEP517/真实父子moduleSHA/TLS/OpenSSL/README旧两流程+新publisher/P21/A1单列/历史原件失败+等价/oracle60/CTX16/两A22 P2及全部119/112自查。所有新生产路径纳原CI收集，缺必需项不标READY。

主控核所有native STOP、精确变更/只读依赖/实际资源0、逐command/exit/log/JUnit/SHA与完整功能断言映射后冻结全候选，新的独立reviewer完整119/112实跑/历史反例与自设计探针。补正仍同段且换新reviewer全复验。完整A2 ACCEPTED只能由fresh完整证据与主控读回得出；随后继续已授权A3四段，分别新正式规划包→独立包审→实施→停写全冻结→fresh完整验收，不自动声称项目或生产安全完成。

## v2 实际修正与基线

前轮独立PACKAGE_READY报告完整保留于package-review-r1.md；该结论仅适用v1，不替代本v2新的独立包审。已清理owner占位、未来A22绑定说明、旧现行文档状态和provenance标注。当前HEAD为已独立审查的CI-only提交`138c08a3496eefb6ef2ceca0d694290dcb95c642`，产品接受基线仍为`8e4e7a3eba6a3e3f0a6a3eb9c3745e2cf7f17d40`；唯一产品树差异为CI超时25→45分钟，所有测试/保护/权限保持，新远端CI仍须实际通过。正式inherited-bindings-v1仍精确绑定已接受业务源；新增A23业务全NOT_RUN。完整当前baseline-manifest-v2及忽略目录全freeze才代表v2候选，不沿用v1快照或小型CI静态审查冒充完整验收。
