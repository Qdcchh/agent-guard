# A3.1 独立审计日志与检查点：正式业务任务包 v2

2026-10-09。当前PACKAGE_REMEDIATION_R1，业务NOT_RUN；[真人授权](authorization.md)已明确从A3.1继续。[state](state.json)同时保留implementation_authorized=true与package_ready/dispatch_ready=false，不将授权当包审通过。请求主控Sol、worker Sol/medium、每轮fresh reviewer Sol/high；有效metadata UNKNOWN。同类有限运行适配持续批准按runtime合同执行，旧workflow门不修改。本段接受、证据/自有资源收尾后停止，不自动A3.2或Git发布。

## 1 基线和权威

正确项目根为/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff，父目录另一个Git。保留本地handoff/a23-local-20261005、HEAD2a8cc7da4867ad1876350855c0ed5569c5ce6472、全部既有dirty/untracked和空index，不reset/clean/重写提交。实际产品与公开a85a822的198路径在本轮建包核同字节，见[baseline](baseline.json)。完整A2已[接受](../A2.3-receipts-20261004/acceptance.md)，正式review-r2 SHA b3b6dbbf591ee672552674df56364969e8ce6173551f501a74097e2c5705bece；旧失败和wheel增强407＋新完整80闭合事实不追改。

原始约束：AGENT/AGENTS、[现行角色](../../current-policy.md)、[实施契约](../../implementation-contract.md)、[独立验收](../../review-contract.md)、setup原workflow契约，原A1/A2/B任务和[接口](../../../../docs/oauth-oidc-sm2-mvp.md)/[安全](../../../../docs/security-model.md)/[验收](../../../../docs/acceptance.md)。四段规划已[独立通过](../A3-planning-20261008/package-review-final.md)，其中[audit接口合同](../A3-planning-20261008/audit-contract.md)A31部分§1—5/8—9为安全语义继承。本包不实施A32任务export/offline、A33三holder部署或A34研究/实验；不新增lease/UNKNOWN/quarantine必需日志种类，不改变原恢复行为。

[requirements-v1](requirements-v1.json)保原A2 119项/112运行/269断言＋A31 22项/21运行/95原子，共141项/133运行/364原断言；原30goals/21P保留，未到本段成熟交付明确后段责任，不提前PASS。[node-bindings](node-bindings-v2.json)为23精确拟节点/7原生义务与95有限case；[继承绑定](inherited-bindings-v1.json)绑定实际旧源码/函数/参数/历史probe，不造wrapper或凭计数闭合。

## 2 业务接口、事务与安全合同

正式细化见[interface-contract-v2](interface-contract-v2.md)和[实际读取绑定](interface-bindings-v2.json)。拟DTO/DDL/新函数皆PROPOSED，实施后才实绑定；不是今日已存在API。旧14SQL、registry/applied_at/历史completion floor、密码签名语义与锁不改，新增GW execution007与独立audit001，qualified依赖有序执行、独立audit registry。standalone默认001—006不误吃007；空bundle legacy后authorization010→007；轮包15GW＋audit001实验证。

journal scope为可信固定gateway origin/tenant/task/streamUUID/epoch1，无reset/global序列或nextval烧号。canonical record/SM3摘要和kind严格且原字节保存；必需BOOTSTRAP/FIRST/RETRY/QUERY/TERMINAL/首次PUBLISH。可信材料descriptor传过accept_response外围响应装配，不能反射closure或用STAGED自报真实；结构capture/ensure/append内建，不由可选None hook开关控制。

首次CREATED在task锁内、reserve/op insert之前捕获完整task全部grant/offpath四counter和旧历史，绑定本TX、scope/schema、真实signed source和captureclock的深不可变seed；非零/旧accepted事实不允许假EMPTY或reserve后反推。原linked材料等待完成后晚ensure_stream+BOOTSTRAP/FIRST、deferredflush和最后实际DBclock，随后只纯内存/commit。EXISTING核原不可变意图/首次材料、freshproof/当前权限并只RETRY；query原链接/响应编码后QUERY再最后clock。缺007/真实材料时需要A3能力的路径失败关闭，legacy非enabled行为保持兼容；维护bootstrap需停writers/drain及真实完整snapshot，缺旧raw只能GAP。

公共principals→task→root-to-leaf grants→operation→lease/outbox→journalhead；head后不首次拿业务锁、不持TX跨网络。真实InternalPublisher仅outbox→已有head，签验/READY写后首次PUBLISH；READY重试原JWS无再签/再日志，不能outbox→task做bootstrap。终局捕获owner/version/prestatus/expiry，写终局后journal/flush，最后expected-terminal四条件与实际DBclock；不能再次调用旧拒terminal helper或续租掩盖过期。任何新等待后逾期整TX业务/计数/event/outbox/head回滚，既有DS效果保持原意图恢复而不释放/重执行。

数据库coverage guard按本TX、scope/op/ref与实际事实核每个requiredkind，旧binary在enabled task漏日志拒；日志反查真实关联，不凭callback客户端bool。不可变records/bootstrap/chunks/pending及严格FK、有限cap+1，不删guard或降低codec。普通None成功正例与故意漏线拒例分别证明，全部拒绝不是功能完成。

checkpoint服务独立PG/key/private/TLS/角色域，operator本地显式登记可信scope/genesis/bootstrap；无公共注册/任意sign或从bundle自带key升信任。strict append1—64 entries/body≤65536，rawrecord≤32768，先exactbatch查重再连续prev/gap/fork；同批重启/丢回复仍原稳定JWS。专属ag-checkpoint+jwt、scope/版本/kid/previous原JWS链，独立reader fixedHTTPS/CA/SAN/latest/history公有锚，不重签旧latest伪新鲜。

delivery仅短TX持久exactencodedpending再网络，按实际body选最大合法prefix，不rawsum；remoteahead使用固定observed pin的history及新增只读records分页，逐历史链+每本地seq/raw/hash核，迟到ACK只清匹配pending且cursor单调；坏stream有界公平。真正SIGKILL/新PID/持久DB核所有send/remotecommit/localACK窗口；回退与外部pin比较拒，不改epoch逃避。

## 3 文件所有权与派发

[ownership-v2](ownership-v2.json)逐文件baselineSHA或NEW列精确allowlist，共63路径；不授目录/glob，原SQL/锁只读。建包两个worker仅各自interface/inherited文档，业务实现worker尚未派发。

S0唯一a31-shared串行实现共享contracts/journal/bootstrap_cli、两个新迁移、旧ledger/evidence/verified/query/terminal/publisher/crypto/migration适配、fixtures及原迁移回归；pyproject注册新模块/SQL。完成自己的完整自查，原生STOP、自有资源0、全文读回和真实接口/字段/错误/SQL/函数SHA冻结后，主控才派S1。

S1 a31-service与a31-delivery按两个互斥allowlist和独立owner资源并行。service消费冻结S0做审计配置/服务/签名/登记/reader/轮换；delivery消费冻结S0做client/pending/ACK/reconcile/CLI并使用自有transport harness，不消费peer未完成文件。各自停止前报告不称全A31接受。

全部STOP后单integrator串行挂联合流程、README字面CLI、现行协议/报告和joint fixture/test；可在主控明确记录精确移交后修改原S0/S1路径，不与任何原writer并写。所有报告/state/需求/授权/资源/freeze由主控维护，worker不可自己ACCEPTED或改门。范围/接口实质变化先冻结新包并fresh包审，不因反复修补削要求。

## 4 运行和自查/验收

[runtime-contract](runtime-contract-v1.json)绑定本轮ownerUUID、五角色精确资源名、隔离DB/网络/证据/私有目录、有限connect/lock/statement/barrier/HTTP/child期限和同类适配来源。包审前仅Docker就绪/公共inventory读取，无A31测试容器；实际fullID/标签/挂载/端口/镜像digest/namespace在自创建后立即落manifest，collision拒。GW/DS独立DB/连接/TX，audit独立实例/key；不同UID/容器或主机的实际隔离程度诚实报告。

Python3.11真实Tongsuo/OpenSSL互验、rfc8785、psycopg、PG16/TLS；使用既有runtime/dev locks与固定PEP517构建，无新增运行依赖。宿主3.14不替代必需3.11；linux/amd64 Tongsuo轮包适配明确arch/translation限，实际Python/库/PG版本与资源quota实核。source非editable与fresh非editablewheel独立安装、仓库外cwd/空PYTHONPATH、父子进程sitepackages和源码/wheel ZIP/安装SQL成员SHA一致；不能代码遮蔽。

完整必跑：ruffcheck/formatcheck、全部ordinary（包括文档/schema/crypto/unit/B）、全部PGintegration/A1/A2/B与本段新增、所有原精准TTL及增强/历史等价native，原预算/撤销/quote/migration/恢复义务＋95新case并集。旧固定1185/2810/500等是历史计数，当前根据实际collect逐case绑定与新增断言判断，不追求固定数字。source/wheel都完整自查，fresh reviewer使用独立own环境亲自完整运行；不是只读workerlog或抽测。

每适用race/fault/crash tuple有效10轮，独立PGconnection/backendPID/barrier/event及全futures/SQLSTATE/exit收齐；正例释放后fresh、负例真正DB锁等待至expiry/fence，finite limits按该case保证expiry先于timeout，不能mockclock/sleep猜/续grant。真正process kill/newPID与layered内部故障各自标签。全前后oracle覆盖原业务/证据/所有祖先四counter/events/nodes/op/lease/outbox/DS＋新journal/bootstrap/chunks/head/pending/checkpoints，不只rowcount。

A31联合正例真实login/consent/root/twoexchange/四工具HTTPS→run/reconcile→publisher/currentholderquery→bootstrappublicdescriptor→operatorregister→persistpending→独立reader observedpin，source和wheel实际CLI子进程。允许未登记delivery REGISTRATION_REQUIRED保pending，不拿网络注册持businesslock。当前current-auth/unsigned runtime/未锚tail和同机逻辑隔离局限保留，不称全项目已完成。

## 5 冻结、独立审查与收尾

建包writers全STOP且主控读回后冻结完整tracked/nonignored树、原始stage/index/dirty/diff和SHA/size/mode，fresh Sol/high做业务PACKAGE_REVIEW。PACKAGE_READY才本段实现资源和写入。完成整合及完整自查后全writers原生STOP/资源核验再freeze完整候选，新Sol/high做IMPLEMENTATION_ACCEPTANCE全部141/133与独立探针。失败保原件，本段補正后另new reviewer完整复验；无已知阻断且全部必需项闭合才正式接受。

每条原始命令/退出/XML/参数/DB/native观察0600落盘，raw/脱敏双SHA及时核，全失败与中断保留；不给秘密/DSN/token/proof/private工具输出。只清成功自建且fullID/双owner标签/挂载可核资源，无关容器不exec/连接/修改，不prune/shareddown。Docker daemon恢复前的无关状态UNKNOWN，不谎称自动restart前后未变；本段自建开始后保存公开元数据对照。

最后同步HANDOFF/A3.1-report/workflow/context/issues/阶段入口及实际Git状态，保持项目PARTIAL/A3.2—4NOT_RUN，资源0和证据保全后STOP。Git提交/推送/PR/合并另需真人授权，不继承PR6管理员例外。

## 6. v2包补正

原v1/r1失败报告和全部原证据保留。新增3个S0精确测试/fixture适配路径，逐字段全部旧效果＋新日志正确性验证，禁止过滤审计域；records两个页族深不可变输入显式进入pure校验signature，并明确S0/S1/S2及finite控制。完整义务不改。继承运行计划补充见[inherited-plan-v2](inherited-plan-v2.md)，补正记录见[package-remediation-r1](package-remediation-r1.md)。尚需fresh Sol/high PACKAGE_REVIEW，未授dispatch/行为通过。
