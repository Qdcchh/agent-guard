# A3.3/A3.4 交付与实验合同（规划基线）

2026-10-08。状态：PLANNING_BASELINE；业务 NOT_RUN，接口 NOT_FROZEN，非业务 PACKAGE_READY。本文与同目录 requirements.json/test-plan.json 构成可移植规划依据，不依赖 ignored 历史目录才能理解。历史 original_* 只是来源快照，其中旧授权、model、owner、API 与哈希均不自动生效。本轮真人只授权查漏、消矛盾、明确接口验收；不得据此实施、建业务资源、执行 collect/test/DB/容器/安装或 Git 发布。

请求配置：主控 Astra（本轮未指定档位）、worker Sol/medium、每轮新独立 reviewer Astra/high；实际有效 model/effort 均 UNKNOWN。规划包可以接受独立 PACKAGE_REVIEW 检查规划一致性；四个业务阶段仍须届时前段真实 ACCEPTED、接口/候选/运行资源冻结、新正式包审与真人开工。完整 A2 的真实接受见 `../A2.3-receipts-20261004/acceptance.md`，绑定 HEAD `2a8cc7da4867ad1876350855c0ed5569c5ce6472` 与本轮 baseline.json，不能将历史 published SHA 或历史 PASS 等同新候选。

## D1 范围、前段接口与状态门

最终保留原 30 目标、A2-P01—P21、完整 A1/B/A22/A23 和将来已接受 A31/A32 的行为、子断言、历史失败触发或经证明等价的负例。requirements.json 的 26 个 A33/A34 父项、131 条子断言全部保留；末尾映射每条到合同段与拟定完整 case。test-plan.json 的 33 个交付节点是26核心、3预检、4原生运行义务（原official/crypto两项加独立DB trace/TLS RTT两项）；51个重复继承 wrapper 不实施，原21P/30目标义务不删除。unit/precheck/native 的局部能力不能冒领整个父项 PASS。

A33消费 A31 的真实日志/首次材料/seed/最终数据库时刻/检查点协议和 A32 的真实导出/离线信任/容量规范。必须逐项重新绑定：配置 schema、迁移资源/登记、构造器及错误映射、worker启动停止、check命令副作用、submit/ACK/重传/历史key、export授权与S/H固定快照、manifest/frame/对象边界、offline verifier与external latest输入、查询状态与READY响应。每项保存接受报告、精确源/调用方/测试节点/SHA、版本和兼容说明。当前 A31/A32 尚未实施，以上均为拟设计，缺冻结继续串行，不派worker猜API。本文不承诺现有 `python -m agent_guard.demo` 或研究CLI可用。

初版范围遵循 docs/acceptance.md M1—M13 及其安全/并发/恢复/审计/工程维度，成熟版扩展维度继续保留并分阶段交付；不将成熟版能力描述成已有初版，不以阶段成果放弃已授权最终目标。旧10月20日不是本轮全部A3期限。可选增强如模型接入、独立下游RPC、真实视频不占初版关键路径；确定性可复现脚本与真实source/wheel运行证据为必需。

## D2 角色、TLS、初始化、独立信任

部署包含独立 AS/OP、GW、DID HTTPS服务、audit检查点服务、publisher、持续执行worker与planner/selector/executor三个holder。三holder各自独立PID/containerID、client_id、SM2私钥和Basic credential；线程或同UID共享全部私有目录只能证明逻辑身份，不能证明凭据隔离。holder只能访问固定AS/GW/DID/handoff路由，实际跨角色文件读取、账本/DS连接拒例由role内部执行并保exit。角色容器/不同UID、最小只读mount、无PG路由、非root/只读rootfs及自有tmpfs实现可核隔离。共同宿主管理员是可信假设，不称跨组织部署。

AS与GW使用同一权威账本事务域；DS为独立数据库、独立连接/事务和服务secret；audit是独立PG实例/签名key/存储域，至少三个PG信任域。同机独立DB只能证明逻辑隔离，不证明独立机构或物理容灾。保留当前 MockDownstream.execute/query，不虚构额外TLS RPC daemon；可信执行worker持有GW+DS必要role credential。当前 gateway.factory.build_app 明确要求两个不同DSN并构造DS adapter，GW仍持DS secret/DSN，必须如实列权限；不能以unset env声称已经拆分。未来若精确最小factory拆分确有需要，先扩正式ownership并审包。

初始化仅显式新owner目录，CSPRNG生成独立AS/各holder/GW receipt/audit用途key和角色secret。复用 private_files 描述符绑定的exclusive 0700目录/0400或0600文件保护，拒symlink、alias、错误owner/mode/重复初始化且不覆盖。不得读取旧密钥作为模板、输出token/proof/password/DSN/private traceback或提供模型绕GW凭据。operator短命provision注册用户/password hash/principals/TaskPolicy/catalog/allowlists、执行版本迁移及DS.provision；绝不能直接create_task_root/child或构造VerifiedInvocation替代公开AS授权。

TLS采用真实CA/SAN/hostname验证，无verify关闭、无全局hosts或系统trust修改；容器固定DNS:443兼容did:web无任意port的解析边界，宿主loopback随机port只用于本轮operator映射。若传输证书RSA、应用签名SM2，明确非全栈国密TLS。每角色仅自身私钥mount：AS signer/客户端验证材料，holder自身key/secret，GW公开trust+当前必须DS材料，worker必要两库role，publisher receipt signer+账本role，audit audit signer+自己的DB，export专属受限管理role，offline仅公钥。运行manifest记录实际权限，不能用秘密字段缺失代替拒例。

DID bootstrap：operator从预登记三个固定HTTPS URL取得文档，独立CA/hostname、no redirect、media-type、65536-byte上限；现IdentityResolver检查id/controller/kid/SPKI与authentication/capabilityInvocation，planner/selector另有capabilityDelegation。operator独立批准registry和持钥证明；同kid新key即使TLS可信也拒。记录取得URL/UTC/cert公开fingerprint/规范字节SM3，冻结approved manifest，通过受控只读渠道分发AS/GW。当前factory捕获immutable did_documents继续使用，不新增生产resolver mode；运行远端/原dict变化不修改已捕获trust，不声称逐请求实时DID解析。wrongCA/SAN、跨域redirect、未知URL/用途/替key/重复key/超大文档、缺manifest/hash错误和holder写trust必须拒；保留B默认HTTPS resolver回归。

独立公钥manifest包含用途/issuer/kid/SPKI/有效历史和版本，经operator独立渠道交付；不能从token或export包自带key建立信任。轮换AS/GW/audit新kid，保留全部历史公钥、旧READY原字节不重签。holder新kid须审批持钥证明及受控快照分发，停用旧key拒外部invoke/query/exchange-retry；已接受意图内部恢复及历史签验不重新授权。备份记录as-of一致性、权威/DS/audit/材料各快照关系；缺历史材料标GAP，latest audit外部信任不得随账本回退，不伪造缺失seq。

## D3 可复现工作流与完整部署验收

拟 DemoRunConfig 固定协议版本、runUUID、角色只读配置/公开摘要/私有引用、固定endpoint、ownermanifest。拟CLI init/check/provision/start/normal/attacks/faults/export/verify/stop；check纯离线无DB，start只启自有资源，stop只清本owner。handoff为固定注册目标的0600 Unix socket+peer验证或固定内网mTLS，child token只交指定holder，禁止任意URL/脚本。持续worker有界扫描RESERVED/expired EXECUTING/UNKNOWN、公平cursor与已有lease/fence，只处理持久不可变operation，不能每invoke启Python冒充正常处理成本。故障控制仅测试/演示装配，不给生产HTTP增加fault/skip。

真流程：浏览器cookie/CSRF/state/nonce/固定redirect/S256授权码与ID Token验签→planner根→父Basic与purpose=delegate真proof两次AS Token Exchange→selector→executor→四工具→当前授权查询→业务terminal→持续READY回执→journal→独立checkpoint→固定快照export→独立trust/latest offline。root/mid/leaf金额整数CNY分100000/80000/70000，calls12/10/8、depth2/1/0、scope/resource/参数/金额/次数/有效期逐维收窄。四工具官方ID依次 `procurement.request.read`、`procurement.document.read`、`procurement.order.create`、`notification.template.send`，tool_version是字符串"1"。原文短名只是内部别名，不能发HTTP。

固定invoke endpoint为 `https://gateway.agent-guard.test/v1/invocations`、query为`https://gateway.agent-guard.test/v1/operations/query`，POST与purpose分别invoke/result-read，每次fresh jti、完整raw body/token digest绑定。order70000分批准SKU quantity1；读/通知0金额仍每操作calls1；通知引用原订单operation且原grant/holder归属，固定template/recipient拒任意URL。查询必须原holder/grant当前有效，不换planner冒OWNER通过；在真实授权窗口内用fresh result-read proof观察terminal/READY，poll单列，不把早期PENDING查询当最终READY证据；过期后用独立audit role导出。

A33攻击覆盖盗token无key及盗parent错误Basic、同proof重放/新proof原键、同键换grant/intent、tenant/task/aud/toolversion/quote/delivery/holder错配，重复JSON/SKU、bool/负/溢出/空scope/未知字段、URL通知扩权、每委托维扩权、expiry/任祖先撤销/key disable及失效retry。预算双合法70000分支争100000至多一接受，root余而mid不足拒，直系/后代共同记账，四工具次数均计。每拒例独立核全祖先四counter、operation/event/outbox/DS，无业务新增；仅允许原协议的STAGED材料单列，不把stage当accept。

故障矩阵完整覆盖：reserve commit后未起worker/真SIGKILL新PID恢复；DS commit后同步点kill与lease接管；terminal内部node/event/outbox故障同TX回滚（明确layered注入，不冒精确SIGKILL窗口）；UNKNOWN不release、查无后late success、双recoverer、旧owner/version/expiry拒、恢复期间撤销；接受后quote修改删除仍原snapshot，坏金额/intent/variant留UNKNOWN。publisher签前/签后save前kill、READY后丢响应保持receipt_id/iat/payload/bytes；audit checkpoint持久后丢响应/restart复用结果、seq连续拒分叉/回退；export失败/截断/重排/已锚定删除/rollback/raw关联/错typ/kid/path/all-node delta/result篡改拒。未锚定尾部、无latest、unsigned状态篡改诚实正控仍按A32有限结论报告。

全安全竞态/故障组每source/wheel有效tuple 10轮：真实独立PG连接backendID/barrier/event、old/newPID、clock/SQLSTATE/每future异常/exit全收，不用sleep-only证明；普通schema/doc/正例一次即可，不把10轮误扩所有节点。验证真锁后TTL、撤销commit先拒与accept先允许内部恢复；新增journal/query/constraint等待之后最终DBclock必须仍有效，终局新增工作后重核owner/version/state/expiry，不能续租掩盖超期。

干净source非editable与fresh wheel非editable分别Python3.11、runtime/dev locks、PEP517固定构建、pipcheck、仓库外cwd/空PYTHONPATH/no tests import，记录父/子进程真实site-packages出处/wheel SHA/SQL资源。wheel需包含新demo与每新增迁移登记，保留现14SQL/checksum/legacy发现边界。旧001/003非零/撤销/七证据表逐列升级保全、非法升级无变、bundle第一次apply重复noop；备份/恢复与key rotation实跑。256items最大合法body/result/宽两级授权是可达正例，层级超限负例不同，公开export需最晚synthetic token exp已过或撤销且无livecredential/DSN/private。

最终README逐字normal/attacks/faults/export/offline/stop命令完整实跑，5分钟实际脚本及result/version/限制；视频/terminal.cast能真实录制则另交SHA，未录明确，不伪动画。每owner独立project/network/PG/namespace/venv/artifactUUID，禁止普通DSN回退、prune或共享down，仅manifest+fullID+双owner核证清理，native自身资源0余留；失败原件保留。

## D4 精确候选文件、串行共享与唯一整合

以下是未来拟改文件，不是当前写权。正式包将每个路径绑定唯一writer、read-only依赖SHA与运行资源。

| 阶段/写者 | 精确拟文件与边界 |
| --- | --- |
| A33 S0 shared_front 串行 | `src/agent_guard/demo/{__init__,config,init,did_bootstrap,provision,client,handoff,worker,__main__}.py`，`tests/fixtures/a33_demo.py`；包入口S0不能import未完成S1模块；停止并冻结真实API/hash后下发 |
| A33 S1 scenarios | `src/agent_guard/demo/{holder,runner,faults}.py`，`tests/integration/test_a33_scenarios.py`；只消费冻结S0 |
| A33 S1 deploy | `tests/integration/test_a33_roles.py`、`tests/integration/test_a33_clean_deploy.py`；拥有独立资源，S0局部子检查只能PRECHECK_ONLY，不能完整A33-03/11/12/13 PASS |
| A33 S2 sole integrator | 全部S1 native STOP后，`src/agent_guard/demo/__main__.py`唯一写权从S0转移；`deploy/demo/compose.yaml`、`pyproject.toml`、`docs/deployment-demo.md`、`tests/test_a33_documents.py`及最终入口；冻结final main/compose/roles/runner/wheel后只读重跑deploy-writer测试全部参数/断言及整体流程 |
| A34 S0 shared_front 串行 | `experiments/agent_guard_bench/{__init__,workload,oracle,research_contracts,research_store,research_service,research_worker,research_evidence}.py`、`experiments/research-schema.sql`、`experiments/workload-v1.json`、`experiments/baseline-capabilities.json`、`tests/fixtures/a34_experiment.py`、`tests/unit/test_a34_workload.py`；新研究家族先冻结context/schema/accept/terminal再并行；这些精确研究家族文件是本轮为旧缺口提出的最小候选扩展，正式包必审 |
| A34 S1 baseline | `experiments/agent_guard_bench/{static_acl,signed_no_atomic,sm2_bearer}.py`、`tests/integration/test_a34_baselines.py`；不得再写共享schema/service |
| A34 S1 measurement | `experiments/agent_guard_bench/{runner,statistics,microbench}.py`、`tests/unit/test_a34_statistics.py`、`tests/unit/test_a34_microbench.py`、`tests/integration/test_a34_experiments.py`；消费冻结S0和baseline能力，基线未冻结不开展官方实验 |
| 最终 sole integrator/controller | `docs/experiment-report.md`、`docs/technical-report.md`、`experiments/README.md`、`tests/test_a34_documents.py`、README/HANDOFF/tasks/A2-report、协议/安全/验收入口；controller独占本轮及未来精确run状态/授权/需求/资源/冻结，不修改旧根state |

不创建51个`test_a33_inherited_closure.py`占位wrapper。若新增研究依赖锁需要`experiments/requirements.lock`，仅复用已有锁定依赖，正式allowlist显式加入再审；不默加依赖。原ownership-v1中的writer是历史建议，不是有效writer分配。共享front、迁移、schema、兼容、最终CLI先串行，之后满足依赖才并行，所有writer STOP后单一整合，整体完整selfcheck及fresh独立实施复核不由分段绿色代替。

## E1 四种模式与独立研究类型/持久化合同

complete仅真实production AS/GW/SDK路径，保全部receipt/journal/audit/export成本。三research mode单独包/network/ports/DB/own schema，不进入production wheel/default ENV/HTTP，无skip auth开关、不改生产CHECK/trigger/FK。staticACL用三distinct CSPRNG rolecredential、真实tenant/tool/resource/quantity/delivery policy与可信quote/下游幂等；许可集正负controls，不allowall；无委托/PoP/原子祖先预算/审计能力须显式。

noAtomic保真AS三层签名、PoP/registry/来源链/收窄/currentstate/strictparams/quote/幂等，仅消融共享预算原子性。Bearer保真实AS code/exchange PoP、token SM2签名/issuer/aud/typ/TTL/cnf与owner登记/来源链/currentstate/scope/资源/quote/原子所有祖先budget与idem，去掉invoke presenter私钥持有及proof完整绑定/重放。attacker仅持有效executor token、不持executor私钥，在原scope请求真实order应产生效果；资源/通知归属仍按token-owner grant/holder判断，不换attacker holder触发无关mismatch；full同token无key/错key零效果。扩权/篡改/expiry/revoke/key disable仍拒并有valid-holder正控。

研究context必须研究专用，禁止假VerifiedInvocationBundle/EvidenceStore.binding/production ag_proofs。公共字段：schema_version、authentication_mode、verified AS claims与raw token digest、signed PermissionSource、tenant/task/root/grant/path、token-owner holder_client/kid、canonical raw body/params/intent digest/tool/version/key、固定endpoint/method、trusted cost/quote snapshot、server correlation/time及持有证明状态。ResearchPoPContext还有真实raw proof/digest/jti/iat/exp/purpose/htu并且holder_possession=VERIFIED；ResearchBearerContext明确proof=None、holder_possession=NOT_VERIFIED。server nonce/hash只是correlation，不得改名proof_jti或冒客户签名。收到但不验的proof只能UNVERIFIED/IGNORED；无proof盗token真实请求也必须可效力演示。

独立schema明确`research_intent_keys` PK(tenant,task,tool,idempotency_key)、`research_operations` immutable原grant/holder/toolversion/canonicalparams/cost/quote/first_evidence/accepted_at、`research_counters` immutable ID/path/limit与四integer计数、`research_events`唯一RESERVE/terminal与全node delta、`research_leases`owner/fence/expiry、`research_proofs`仅PoP唯一域、`research_evidence` raw token/body及nullable真实proof、first/retry关联、`research_outbox`/可选研究journal。raw材料只能受限存储，公开raw rows脱敏。引用均指本研究operation，不依赖production FK；约束保nonnegative/bounded/immutable/一次terminal/唯一key，noAtomic不复制<=limit CHECK，Bearer保该约束。AS authority ag_principals/tasks/grants/grant_tokens是真撤销原行，不复制滞后缓存；production ag_grants计数不写且单独核0。

Bearer研究receipt/evidence须有独立schema/version和proof absence语义，不能把不含PoP的研究证据送production receipt verifier后声称同等验签。若未提供相同发布/审计机制，capabilities明确N/A和实际成本差异；noAtomic研究日志初始化不得复用前置独占task/full-task journal bootstrap造成接受串行，零基线/introduced node的真实性另冻结并核证。

验证器复用成熟SM2/JWS/SM3/canonical/claims/IdentityResolver/PermissionSnapshotProvider/load/revalidate、strictparams/policy/catalog/results和MockDownstream，不复制密码、monkeypatch verifier或伪proof；私有helper不是已承诺公共API，正式绑定实际函数/错误映射。研究网络可使用隔离DNS同固定canonical HTTPS origin消费真PoP；若独立URL，明确研究verify_ag_proof adapter固定htu，不能偷换htu或给生产verifier加可选endpoint。

## E2 研究接受、终局、撤销与效力oracle

接受RC单TX锁序：authority principals排序去重→task→root-to-leaf grants **FOR SHARE**（非FOR KEY SHARE）→精确单业务键行协议→research operation/lease/evidence→可选journal head最后。完整真source/path/root/tenant/task/owner/active/revoked/not_before/exp重核；SHARE持到最终DBclock/commit，与真实撤销写锁冲突，同时允许不同键接受者共享。不能沿生产principal/task FOR UPDATE，不能最后调production _final_bound_check升级锁，也不能在SHARE ag_grants写counter。same-key INSERT ON CONFLICT+精确tuple行互斥 protects不存在键创建与retry；不同竞争键不得共用task/root/head前置mutex。unique异常回滚/savepoint后只重读真实committed同键并逐字段检查，不泛化成功。

PoP唯一登记先于idem shortcut；EXISTING用原不可变cost/quote/首次材料/operation，不新扣预算，freshlink和当前状态/finalclock仍同TX，同proof拒并回滚。新noAtomic不锁counter读全祖先四值→旧值额度检查→创建operation→按root-to-leaf普通`counter=counter+delta`UPDATE及真实RESERVE/node，避免丢失增量但不再条件check、SERIALIZABLE/RR重试或预算CHECK恢复安全性。journal head只能预算读后最后取。Bearer先root-to-leaf研究counter FOR UPDATE后atomic check/update。constraintflush、同模式重读已保护authority/source、最终实际DBclock(token/grants/真PoP窗口)后只纯内存返回commit，不能再有可等待SQL/签名/network。

新grant必须真实AS签发后且无研究执行事实时建立零counter/immutable limit/path基线，不能重建task清零。研究终局/UNKNOWN/recovery必须使用本家store/operation/event/lease/outbox，不能调用production terminal counter writer或伪造生产first material。固定stable operation_id，真DS service secret/execute/query/quote once-effect；UNKNOWN不release，confirmed FAILED release、SUCCEEDED settle全祖先；lease owner/version/nonterminal/expiry在新增约束/日志后最终DBclock核，terminal/event/node/outbox同TX最多一次。accept后revoke不使内部恢复无效；后续外部retry/query/newkey仍真currentstate拒。

真实撤销先commit→共享锁等待后读取invalid全回滚；接受先SHARE→撤销writer等待直到接受commit。记录独立连接backend/barrier、precommit/成功TX返回/postcommit可见monotonic上下界，effective_at是TX内clock不能冒commit timestamp。不改commit-timestamp配置造精度。实测必须保存pg_locks/pg_blocking_pids/wait SQL/SQLSTATE/全部future异常；FOR SHARE兼容性现仅源码推导，不写PASS。

10轮独立安全race：每轮fresh真AS task/root100000、calls>=2，两个不同mid各80000/leaf各70000与不同键/真实proof/70000可信quote；T1/T2都SHARE authority且读rootcounter0/check后、首次UPDATE前barrier。noAtomic应两真实commit→两DS order实际140000、root高水位140000，每branch70000，计数/events一致；complete同语义public path最多一accept/effect70000、全节点≤limit。不同root/同键/共同mid低额、丢失UPDATE/前置锁/production CHECK回滚/自动重读都不能证明消融；未出现真实双提交则NOT_DEMONSTRATED。普通perf不加barrier/sleep。

独立oracle来自预批准workload authority、实际签名链/limit、可信quote、immutable op、全祖先RESERVE/SETTLE/RELEASE时序和4counter初值、DS operations/orders/notifications/results，在一致RR READ ONLY观察中重建全过程高水位，不只root末值。approval truth不能来自mode自报HTTP202。两竞争请求均可能权限合法但容量只准一，集合超额与holder盗用分列。same intent expected oneeffect、拒例零reservation/effect、stage单列；生产authority counters与research计数分开核。valid-holder资源扩权负控独立于早期holder拒绝，错误层不替代后续predicate效力。

## E3 固定实验调度、TTL、攻击和重试

候选将于正式审包前冻结：四mode×seeds2026100501/2026100502×5000 measured=40000，complete10000；每repeat250 warmup独立task另计，共2000。rep1 staticACL→noAtomic→complete→Bearer，rep2反转；official性能wheel noneditable，source/wheel功能/安全双方复现及测量接口验证，不混统计。旧3×10000/10000微基准为历史建议，本轮2×5000及1000微基准候选优先，不重复要求矛盾计数。

每repeat3500legal=875任务T0000..T0874四工具，client slot=t mod50；1000attack=10类各100（盗token/错holder父交换/重放/body替换/域错配/资源扩权/strictSKU/委托扩权/失效状态/预算次数竞争）；500retry=250freshproof原键/100原proof重发/100terminal freshproof原键/50lost-response freshproof原键。calls12/10/8、amount100000/80000/70000及真70000报价；除class2必须复用固定legal原件以构成真正重放外，正常/攻击隔离task，class9共100测量行是50对同root A9-P<p>、两不同mid/leaf/键，不是100独立root。控制race10轮另列，不混普通计时。

class2重放固定case c=0..99引用已计入3500legal的T0500+c之request.read（index4*(500+c)），不是专用新task；原legal只计一次，另100次真实发送计attack，不加未计准备invoke。精确复用原token/proof/body/key/holder/grant，同task slot在原请求完成或失败后、下一工具前立即发送，目标签发到重发≤5s、硬界原proof≤60s且root≤300s不变；不得重签或换目标。与retry sameproof100的T0250..0349完全分开。PoP模式独立从已提交proof/link/operation核原proof确被消费，并核本次wire原字节；前次失败/消费未知、过期或更早层拒绝均保真实行但不能证明replay predicate，缺实际前置则该覆盖INCOMPLETE、不挑成功目标或补造请求。staticACL/Bearer同凭据/字节重复仍真实测量，proof-replay=N/A，单列idem/once-effect，不伪造proof。独立安全probe在official计数外用fresh真实task执行原请求+原proof重放，source/wheel各10轮核proof消费和业务零新增；不能拿它替换正式100行的实际计数/局限。

固定targets：fresh T0000..0249 request index4t；sameproof T0250..0349 request index4t；terminal T0350..0449 order index4t+2；loss T0450..0499 order index4t+2。原目标都来自3500legal，没有额外未计invoke初始化；同完整rawbody/intent/key/grant/holder。loss真实响应丢失原legal row保networkfailure/statusunknown，不由retry覆盖。terminal独立真实见证，不按成功后选最快targets；Bearer同字节重复PoP机制N/A，不能伪replay proof。

每task真browser/root/two exchange初始化单列；roottoken≤300s、proof≤60s（5s future skew沿原协议），send即时签proof，不预签整批、不续同grant/改clock。hard task调度deadline rootissue+240s；sameproof目标≤5s重发、硬≤60s，过期先拒就记录freshness层而不声称unique replay检查。task-local四工具顺序与目标retry穿插，不先跑3500再500。connect5/read30/dependency120秒、last measured send后drain600秒是候选冻结值，未满足依赖用可用原材料发真实既定意图并记录dependency_unmet/expired层；无法实际send则保planned missing INCOMPLETE，不造行、換target或漏失败。

AS login/exchange/query/poll/audit绝不充invoke。AS层错holder/扩委托拒绝单列真实证据；该计划行仍须冻结实际gateway request：专用attack task真实已签ancestor token+明确错holder proof+原expanded canonical intent，记录ancestor fallback/missingchild/AS failure，不伪child或validchild。早期holder拒绝不能证明resource predicate，补充valid-holder独立负控另计。各mode角色/credential/许可集差异预冻到capabilities，无unsigned substitute；不能发送仍INCOMPLETE，若canonical fallback不适合意图，必须官方计时前更版重新审，不能后调样本。

50个真实同时在途client槽/线程，首波50fresh task request由barrier放行，保存send/end/active证据要求observed peak≥50；server实际max32，不能说50 server并行，不缩client50或full10000。HTTP timeout后真实future继续持server槽，记录late effects且drain核之。AS初始化/依赖等待/调度延迟单列，closed-loop coordinated omission说明；一轮task完成需四工具terminal，证据完成另量，不把accept吞吐当task完成。

## E4 公平、计时、容量与最终验收

capabilities表逐mode记录credential类型/尺寸、delegation/PoP/replay/currentstate/原子budget/idem/工具policy/DS/receipt/journal/checkpoint/export与共同持久化成本；每能力实际正负controls，缺审计N/A不是成功，不删complete成本求快。无法同其余成本时仅报告当前配置实际差额，不称纯PoP单变量或普适/行业优越。

每actual invoke一sanitized JSONL row：run/mode/seed/client/task/tool/class/keyhash、token/proof/body bytes、plan/send/responseend monotonicns、transport/status/code/rejectlayer/opID、retry target/receiptstatus；不存活Authorization/AGProof/DSN/key。planned row与实际send分离，duplicates/missing/count mismatch失败或INCOMPLETE。保所有timeout/expired/reject/socket/SQL异常/late轨迹，官方两rep原数据+范围/平均+全部rerun lineage不挑最佳。latency=实际client end-send，分all/failed/legal/attack/retry/tool/class，nearest-rank ceil(p*n)-1和n；timeout实际end与观察截止单列。

attempt/authpass/newaccept吞吐分母为first actual send到last actual client response/failure end的send-response窗口，另列计划dispatch/初始化等待；terminal/READY/anchor各count/own completion-drain observation窗口与缺口，不拿异步接受分母冒完成性能。报告合法authpass/capacityadmission/四工具task完成率/证据完成率、越权effects/duplicateeffects/全祖先高水位/撤销上下界；测试集full0违规有限结论，baseline真实违规保留。drain截止未完仍INCOMPLETE并保存继续后台事件，缺审计明确N/A，不能自动COMPLETE。

四个原生有限义务分别是`runner.py::run_official_mode_repetition`、`microbench.py::run_real_crypto_microbenchmark`、`microbench.py::run_independent_database_trace`、`microbench.py::run_independent_tls_roundtrip_reference`；四项均是未来拟函数、NOT_RUN/NOT_FROZEN，各ordinary重复一次，官方另按固定4mode×2rep执行，安全race/fault每适用tuple仍10轮。official runner不覆盖A34-09，crypto仅09.01/.02/.05，DBtrace仅09.03/.05，TLSRTT仅09.04/.05；A34-05由unit计划schema、official真实发送/重试/层次及effect_budget独立policy/DS oracle并集，不能unit或runner自报闭合。

真实SM2sign/verify/SM3各1000 measured+50warmup候选，固定key/profile/body/chain3与向量/OpenSSL互操作；DB等待/连接/query trace独立run说明instrumentation成本且不改变最后DBclock，TLS空RTT只参考，不从total减估计密码/RTT冒精确分解。模型N/A。

正式preflight重新读真实host/Docker/CPU/RAM/quota/arch/translation/Python/tongsuopy/OpenSSL/psycopg/PG/settings/连接/TLSreuse/server32/workerquota/lease/checkpointbatch/image digest/锁来源，每repeat CPU/RSS/heap+index+toast/rows/DB/WAL可用度/导出bytes前后diff。历史15logicalCPU/24GiB、Docker约7.75GiB/aarch64与394GiB可用只作历史观察，不是当前实测；实际Docker limit UNKNOWN待读。三PG各512MiB/worker4/PGconn100只是起始建议，不要求16GiB人为硬门，不因资源改变50/10000。pilot仅功能/计数/资源label独立，不计official、不按表现换seed/target/比例/order；需quota变更先formal amendment再freeze。

A32候选cap wire256MiB、400000frames、200000objects、100000journal、20000operations，frame含换行≤64KiB、raw chunk24576/journal32768，原材料64KiB/JWS16KiB等更严边界不放宽。正式A33最大256SKU/A34固定工作负载逐task或正式freeze任务分区完整export预检，记录每包/总计与物化spool峰值；不得以把所有任务硬拼单包导致超cap后静默截断，或依数据好坏分片丢record。A32若真实schema/cap不同必须正式审包解决，超限明确拒并保未完成，不能256MiB整包上界放宽HTTP65536。public synthetic包在最晚token过期/撤销后分发，trust/latest独立保存；历史签验按原窗口，当前授权UNKNOWN/DS事实ATTESTED/unsigned runtime UNANCHORED和尾部局限保留。

最终必须全30目标逐原行为→actual case/assertion/command/exit/XML/SHA，完整前段ID及新增补正/history等价/negativecontrols、source/wheel全回归、官方4mode×2repeat及独立微基准/静态材料并集。fresh reviewer真实独立运行完整官方集，不能只读worker logs冒重跑。所有writer nativeSTOP且tracked/nonignored全路径/hash freeze后复核，失败原件+补正fresh复验；缺requiredrun不得ACCEPTED。release固定commit/wheel/locks/schema/workload/rawdata/trust/latest SHA，设计/威胁/技术/部署/实验报告及可执行实际demo与运行证据一致。规划审查不能授业务PACKAGE_READY。

工程预算只条件建议：A33装配及故障/sourcewheel2—4工程日，selfcheck/freshreview补正1—2；A34研究家族/能力/oracle1—3，实验/材料/复核1—2；接口稳定且无严重回归才适用，无截止承诺。正式40000/r纯测量，若r=10/50/100 attempts/s则约66.7/13.3/6.7分钟，另加8轮bootstrap/warmup/drain/export/oracle与独立重跑；这些是情景算术不是性能预测。预算不足保留目标与INCOMPLETE，削可选页面/视频/模型而非安全或原实验。

## M 逐项可核映射

以下每条ID的完整原文以同目录requirements.json为准，不复制历史巨量快照。全部映射仅PLANNED_NOT_IMPLEMENTED_NOT_RUN；列出的case是未来完整父项case，不代表unit/precheck能覆盖所有子断言。test-plan.json保存精确局部slice及native义务，正式建包还须从真实accepted前段展开原测试节点/参数化与source/wheel义务。

| 原子ID | 合同节 | 拟case/独立义务（按实际能力并集） |
| --- | --- | --- |
| A33-01.01 | D2 | `tests/integration/test_a33_roles.py::test_role_init_trust_and_private_mounts` |
| A33-01.02 | D2 | `tests/integration/test_a33_roles.py::test_role_init_trust_and_private_mounts` |
| A33-01.03 | D2 | `tests/integration/test_a33_roles.py::test_role_init_trust_and_private_mounts` |
| A33-01.04 | D2 | `tests/integration/test_a33_roles.py::test_role_init_trust_and_private_mounts` |
| A33-02.01 | D2 | `tests/integration/test_a33_roles.py::test_operator_https_did_approval_and_immutable_distribution` |
| A33-02.02 | D2 | `tests/integration/test_a33_roles.py::test_operator_https_did_approval_and_immutable_distribution` |
| A33-02.03 | D2 | `tests/integration/test_a33_roles.py::test_operator_https_did_approval_and_immutable_distribution` |
| A33-02.04 | D2 | `tests/integration/test_a33_roles.py::test_operator_https_did_approval_and_immutable_distribution` |
| A33-02.05 | D2 | `tests/integration/test_a33_roles.py::test_operator_https_did_approval_and_immutable_distribution` |
| A33-02.06 | D2 | `tests/integration/test_a33_roles.py::test_operator_https_did_approval_and_immutable_distribution` |
| A33-03.01 | D2/D4 | `tests/integration/test_a33_roles.py::test_three_holder_processes_os_and_network_denials` |
| A33-03.02 | D2/D4 | `tests/integration/test_a33_roles.py::test_three_holder_processes_os_and_network_denials` |
| A33-03.03 | D2/D4 | `tests/integration/test_a33_roles.py::test_three_holder_processes_os_and_network_denials` |
| A33-03.04 | D2/D4 | `tests/integration/test_a33_roles.py::test_three_holder_processes_os_and_network_denials` |
| A33-03.05 | D2/D4 | `tests/integration/test_a33_roles.py::test_three_holder_processes_os_and_network_denials` |
| A33-04.01 | D3 | `tests/integration/test_a33_scenarios.py::test_browser_root_and_two_delegations_real_https` |
| A33-04.02 | D3 | `tests/integration/test_a33_scenarios.py::test_browser_root_and_two_delegations_real_https` |
| A33-04.03 | D3 | `tests/integration/test_a33_scenarios.py::test_browser_root_and_two_delegations_real_https` |
| A33-04.04 | D3 | `tests/integration/test_a33_scenarios.py::test_browser_root_and_two_delegations_real_https` |
| A33-04.05 | D3 | `tests/integration/test_a33_scenarios.py::test_browser_root_and_two_delegations_real_https` |
| A33-05.01 | D3/D1 | `tests/integration/test_a33_scenarios.py::test_three_holder_four_tools_query_receipt_anchor_export` |
| A33-05.02 | D3/D1 | `tests/integration/test_a33_scenarios.py::test_three_holder_four_tools_query_receipt_anchor_export` |
| A33-05.03 | D3/D1 | `tests/integration/test_a33_scenarios.py::test_three_holder_four_tools_query_receipt_anchor_export` |
| A33-05.04 | D3/D1 | `tests/integration/test_a33_scenarios.py::test_three_holder_four_tools_query_receipt_anchor_export` |
| A33-05.05 | D3/D1 | `tests/integration/test_a33_scenarios.py::test_three_holder_four_tools_query_receipt_anchor_export` |
| A33-06.01 | D2/D3 | `tests/integration/test_a33_scenarios.py::test_downstream_separate_domain_service_auth_and_effects` |
| A33-06.02 | D2/D3 | `tests/integration/test_a33_scenarios.py::test_downstream_separate_domain_service_auth_and_effects` |
| A33-06.03 | D2/D3 | `tests/integration/test_a33_scenarios.py::test_downstream_separate_domain_service_auth_and_effects` |
| A33-06.04 | D2/D3 | `tests/integration/test_a33_scenarios.py::test_downstream_separate_domain_service_auth_and_effects` |
| A33-06.05 | D2/D3 | `tests/integration/test_a33_scenarios.py::test_downstream_separate_domain_service_auth_and_effects` |
| A33-07.01 | D3 | `tests/integration/test_a33_scenarios.py::test_attack_set_exact_binding_no_side_effects` |
| A33-07.02 | D3 | `tests/integration/test_a33_scenarios.py::test_attack_set_exact_binding_no_side_effects` |
| A33-07.03 | D3 | `tests/integration/test_a33_scenarios.py::test_attack_set_exact_binding_no_side_effects` |
| A33-07.04 | D3 | `tests/integration/test_a33_scenarios.py::test_attack_set_exact_binding_no_side_effects` |
| A33-07.05 | D3 | `tests/integration/test_a33_scenarios.py::test_attack_set_exact_binding_no_side_effects` |
| A33-08.01 | D3/E2 | `tests/integration/test_a33_scenarios.py::test_root_mid_calls_revocation_final_clock_races` |
| A33-08.02 | D3/E2 | `tests/integration/test_a33_scenarios.py::test_root_mid_calls_revocation_final_clock_races` |
| A33-08.03 | D3/E2 | `tests/integration/test_a33_scenarios.py::test_root_mid_calls_revocation_final_clock_races` |
| A33-08.04 | D3/E2 | `tests/integration/test_a33_scenarios.py::test_root_mid_calls_revocation_final_clock_races` |
| A33-08.05 | D3/E2 | `tests/integration/test_a33_scenarios.py::test_root_mid_calls_revocation_final_clock_races` |
| A33-09.01 | D3 | `tests/integration/test_a33_scenarios.py::test_process_crash_late_success_recovery_fault_matrix` |
| A33-09.02 | D3 | `tests/integration/test_a33_scenarios.py::test_process_crash_late_success_recovery_fault_matrix` |
| A33-09.03 | D3 | `tests/integration/test_a33_scenarios.py::test_process_crash_late_success_recovery_fault_matrix` |
| A33-09.04 | D3 | `tests/integration/test_a33_scenarios.py::test_process_crash_late_success_recovery_fault_matrix` |
| A33-09.05 | D3 | `tests/integration/test_a33_scenarios.py::test_process_crash_late_success_recovery_fault_matrix` |
| A33-09.06 | D3 | `tests/integration/test_a33_scenarios.py::test_process_crash_late_success_recovery_fault_matrix` |
| A33-10.01 | D3/D1 | `tests/integration/test_a33_scenarios.py::test_receipt_audit_export_faults_and_offline_mutations` |
| A33-10.02 | D3/D1 | `tests/integration/test_a33_scenarios.py::test_receipt_audit_export_faults_and_offline_mutations` |
| A33-10.03 | D3/D1 | `tests/integration/test_a33_scenarios.py::test_receipt_audit_export_faults_and_offline_mutations` |
| A33-10.04 | D3/D1 | `tests/integration/test_a33_scenarios.py::test_receipt_audit_export_faults_and_offline_mutations` |
| A33-10.05 | D3/D1 | `tests/integration/test_a33_scenarios.py::test_receipt_audit_export_faults_and_offline_mutations` |
| A33-11.01 | D3/D4 | `tests/integration/test_a33_clean_deploy.py::test_clean_source_wheel_without_model_api` |
| A33-11.02 | D3/D4 | `tests/integration/test_a33_clean_deploy.py::test_clean_source_wheel_without_model_api` |
| A33-11.03 | D3/D4 | `tests/integration/test_a33_clean_deploy.py::test_clean_source_wheel_without_model_api` |
| A33-11.04 | D3/D4 | `tests/integration/test_a33_clean_deploy.py::test_clean_source_wheel_without_model_api` |
| A33-11.05 | D3/D4 | `tests/integration/test_a33_clean_deploy.py::test_clean_source_wheel_without_model_api` |
| A33-12.01 | D2/D3 | `tests/integration/test_a33_clean_deploy.py::test_rotation_upgrade_backup_restore_owner_cleanup` |
| A33-12.02 | D2/D3 | `tests/integration/test_a33_clean_deploy.py::test_rotation_upgrade_backup_restore_owner_cleanup` |
| A33-12.03 | D2/D3 | `tests/integration/test_a33_clean_deploy.py::test_rotation_upgrade_backup_restore_owner_cleanup` |
| A33-12.04 | D2/D3 | `tests/integration/test_a33_clean_deploy.py::test_rotation_upgrade_backup_restore_owner_cleanup` |
| A33-12.05 | D2/D3 | `tests/integration/test_a33_clean_deploy.py::test_rotation_upgrade_backup_restore_owner_cleanup` |
| A33-13.01 | D3/E4 | `tests/integration/test_a33_clean_deploy.py::test_max_legal_payload_bounded_package_and_expired_public_export` |
| A33-13.02 | D3/E4 | `tests/integration/test_a33_clean_deploy.py::test_max_legal_payload_bounded_package_and_expired_public_export` |
| A33-13.03 | D3/E4 | `tests/integration/test_a33_clean_deploy.py::test_max_legal_payload_bounded_package_and_expired_public_export` |
| A33-13.04 | D3/E4 | `tests/integration/test_a33_clean_deploy.py::test_max_legal_payload_bounded_package_and_expired_public_export` |
| A33-13.05 | D3/E4 | `tests/integration/test_a33_clean_deploy.py::test_max_legal_payload_bounded_package_and_expired_public_export` |
| A33-14.01 | D1/D3/D4/E4 | `tests/test_a33_documents.py::test_release_materials_commands_and_actual_demo_artifacts` |
| A33-14.02 | D1/D3/D4/E4 | `tests/test_a33_documents.py::test_release_materials_commands_and_actual_demo_artifacts` |
| A33-14.03 | D1/D3/D4/E4 | `tests/test_a33_documents.py::test_release_materials_commands_and_actual_demo_artifacts` |
| A33-14.04 | D1/D3/D4/E4 | `tests/test_a33_documents.py::test_release_materials_commands_and_actual_demo_artifacts` |
| A33-14.05 | D1/D3/D4/E4 | `tests/test_a33_documents.py::test_release_materials_commands_and_actual_demo_artifacts` |
| A34-01.01 | E3 | `tests/unit/test_a34_workload.py::test_fixed_seeds_counts_classes_and_no_posthoc_selection` |
| A34-01.02 | E3 | `tests/unit/test_a34_workload.py::test_fixed_seeds_counts_classes_and_no_posthoc_selection` |
| A34-01.03 | E3 | `experiments/agent_guard_bench/runner.py::run_official_mode_repetition` |
| A34-01.04 | E3 | `tests/unit/test_a34_workload.py::test_fixed_seeds_counts_classes_and_no_posthoc_selection` |
| A34-01.05 | E3 | `experiments/agent_guard_bench/runner.py::run_official_mode_repetition` |
| A34-02.01 | E1/E4 | `tests/integration/test_a34_baselines.py::test_fair_capabilities_and_equal_workload_resources` |
| A34-02.02 | E1/E4 | `tests/integration/test_a34_baselines.py::test_fair_capabilities_and_equal_workload_resources` |
| A34-02.03 | E1/E4 | `tests/integration/test_a34_baselines.py::test_fair_capabilities_and_equal_workload_resources` |
| A34-02.04 | E1/E4 | `tests/integration/test_a34_baselines.py::test_fair_capabilities_and_equal_workload_resources` |
| A34-02.05 | E1/E4 | `tests/integration/test_a34_baselines.py::test_fair_capabilities_and_equal_workload_resources` |
| A34-03.01 | E1/E2 | `tests/integration/test_a34_baselines.py::test_real_signed_no_atomic_isolated_budget_race` |
| A34-03.02 | E1/E2 | `tests/integration/test_a34_baselines.py::test_real_signed_no_atomic_isolated_budget_race` |
| A34-03.03 | E1/E2 | `tests/integration/test_a34_baselines.py::test_real_signed_no_atomic_isolated_budget_race` |
| A34-03.04 | E1/E2 | `tests/integration/test_a34_baselines.py::test_real_signed_no_atomic_isolated_budget_race` |
| A34-03.05 | E1/E2 | `tests/integration/test_a34_baselines.py::test_real_signed_no_atomic_isolated_budget_race` |
| A34-04.01 | E1/E2 | `tests/integration/test_a34_baselines.py::test_real_sm2_bearer_stolen_token_effect_and_full_denial` |
| A34-04.02 | E1/E2 | `tests/integration/test_a34_baselines.py::test_real_sm2_bearer_stolen_token_effect_and_full_denial` |
| A34-04.03 | E1/E2 | `tests/integration/test_a34_baselines.py::test_real_sm2_bearer_stolen_token_effect_and_full_denial` |
| A34-04.04 | E1/E2 | `tests/integration/test_a34_baselines.py::test_real_sm2_bearer_stolen_token_effect_and_full_denial` |
| A34-04.05 | E1/E2 | `tests/integration/test_a34_baselines.py::test_real_sm2_bearer_stolen_token_effect_and_full_denial` |
| A34-05.01 | E2/E3 | `tests/unit/test_a34_workload.py::test_attack_retry_intents_and_policy_oracle` + `experiments/agent_guard_bench/runner.py::run_official_mode_repetition` |
| A34-05.02 | E2/E3 | `experiments/agent_guard_bench/runner.py::run_official_mode_repetition` |
| A34-05.03 | E2/E3 | `tests/unit/test_a34_workload.py::test_attack_retry_intents_and_policy_oracle` + `experiments/agent_guard_bench/runner.py::run_official_mode_repetition` |
| A34-05.04 | E2/E3 | `tests/unit/test_a34_workload.py::test_attack_retry_intents_and_policy_oracle` + `experiments/agent_guard_bench/runner.py::run_official_mode_repetition` |
| A34-05.05 | E2/E3 | `tests/unit/test_a34_workload.py::test_attack_retry_intents_and_policy_oracle` + `tests/integration/test_a34_experiments.py::test_effect_budget_revocation_metrics_with_database_oracle` + `experiments/agent_guard_bench/runner.py::run_official_mode_repetition` |
| A34-06.01 | E3/E4 | `tests/integration/test_a34_experiments.py::test_terminal_receipt_journal_checkpoint_drain_metrics` |
| A34-06.02 | E3/E4 | `tests/integration/test_a34_experiments.py::test_terminal_receipt_journal_checkpoint_drain_metrics` |
| A34-06.03 | E3/E4 | `tests/integration/test_a34_experiments.py::test_terminal_receipt_journal_checkpoint_drain_metrics` |
| A34-06.04 | E3/E4 | `tests/integration/test_a34_experiments.py::test_terminal_receipt_journal_checkpoint_drain_metrics` |
| A34-06.05 | E3/E4 | `tests/integration/test_a34_experiments.py::test_terminal_receipt_journal_checkpoint_drain_metrics` |
| A34-07.01 | E4 | `tests/unit/test_a34_statistics.py::test_all_rows_percentiles_failure_retention_and_rate_denominators` |
| A34-07.02 | E4 | `tests/unit/test_a34_statistics.py::test_all_rows_percentiles_failure_retention_and_rate_denominators` |
| A34-07.03 | E4 | `tests/unit/test_a34_statistics.py::test_all_rows_percentiles_failure_retention_and_rate_denominators` |
| A34-07.04 | E4 | `tests/unit/test_a34_statistics.py::test_all_rows_percentiles_failure_retention_and_rate_denominators` |
| A34-07.05 | E4 | `tests/unit/test_a34_statistics.py::test_all_rows_percentiles_failure_retention_and_rate_denominators` |
| A34-08.01 | E2/E4 | `tests/integration/test_a34_experiments.py::test_effect_budget_revocation_metrics_with_database_oracle` |
| A34-08.02 | E2/E4 | `tests/integration/test_a34_experiments.py::test_effect_budget_revocation_metrics_with_database_oracle` |
| A34-08.03 | E2/E4 | `tests/integration/test_a34_experiments.py::test_effect_budget_revocation_metrics_with_database_oracle` |
| A34-08.04 | E2/E4 | `tests/integration/test_a34_experiments.py::test_effect_budget_revocation_metrics_with_database_oracle` |
| A34-08.05 | E2/E4 | `tests/integration/test_a34_experiments.py::test_effect_budget_revocation_metrics_with_database_oracle` |
| A34-09.01 | E4 | `tests/unit/test_a34_microbench.py::test_real_crypto_microbench_count_and_measurement_contract` + `experiments/agent_guard_bench/microbench.py::run_real_crypto_microbenchmark` |
| A34-09.02 | E4 | `experiments/agent_guard_bench/microbench.py::run_real_crypto_microbenchmark` |
| A34-09.03 | E4 | `experiments/agent_guard_bench/microbench.py::run_independent_database_trace` |
| A34-09.04 | E4 | `experiments/agent_guard_bench/microbench.py::run_independent_tls_roundtrip_reference` |
| A34-09.05 | E4 | `experiments/agent_guard_bench/microbench.py::run_real_crypto_microbenchmark` + `experiments/agent_guard_bench/microbench.py::run_independent_database_trace` + `experiments/agent_guard_bench/microbench.py::run_independent_tls_roundtrip_reference` |
| A34-10.01 | E4 | `tests/integration/test_a34_experiments.py::test_environment_capacity_storage_manifest_and_payload_preflight` |
| A34-10.02 | E4 | `tests/integration/test_a34_experiments.py::test_environment_capacity_storage_manifest_and_payload_preflight` |
| A34-10.03 | E4 | `tests/integration/test_a34_experiments.py::test_environment_capacity_storage_manifest_and_payload_preflight` |
| A34-10.04 | E4 | `tests/integration/test_a34_experiments.py::test_environment_capacity_storage_manifest_and_payload_preflight` |
| A34-10.05 | E4 | `tests/integration/test_a34_experiments.py::test_environment_capacity_storage_manifest_and_payload_preflight` |
| A34-11.01 | E3/E4 | `tests/integration/test_a34_experiments.py::test_pilot_not_counted_and_all_fixed_repetitions_retained` |
| A34-11.02 | E3/E4 | `tests/integration/test_a34_experiments.py::test_pilot_not_counted_and_all_fixed_repetitions_retained` |
| A34-11.03 | E3/E4 | `tests/integration/test_a34_experiments.py::test_pilot_not_counted_and_all_fixed_repetitions_retained` |
| A34-11.04 | E3/E4 | `tests/integration/test_a34_experiments.py::test_pilot_not_counted_and_all_fixed_repetitions_retained` |
| A34-11.05 | E3/E4 | `tests/integration/test_a34_experiments.py::test_pilot_not_counted_and_all_fixed_repetitions_retained` |
| A34-12.01 | D1/E4 | `tests/test_a34_documents.py::test_final_thirty_goal_matrix_and_release_materials` |
| A34-12.02 | D1/E4 | `tests/test_a34_documents.py::test_final_thirty_goal_matrix_and_release_materials` |
| A34-12.03 | D1/E4 | `tests/test_a34_documents.py::test_final_thirty_goal_matrix_and_release_materials` |
| A34-12.04 | D1/E4 | `tests/test_a34_documents.py::test_final_thirty_goal_matrix_and_release_materials` |
| A34-12.05 | D1/E4 | `tests/test_a34_documents.py::test_final_thirty_goal_matrix_and_release_materials` |

STOP：本文只规划，本worker未执行任何业务运行；完成全文读回及自有范围核证后原生停写，由主控核证与独立规划review，不由worker自授接受。
