# A3.3 S0 接口补齐提议

A3.2已正式ACCEPTED，接受pins与实际代码见accepted-api-bindings-v2.json及interface-v2.json。本接口为A3.3正式v1拟新增API，尚未实施/运行/包审接受。未修改正式文件、旧草稿、代码、测试、state或STOP证据。原14父项/71断言及D1—D4仍由既有草稿维护，本文件只消解共享接口。JSON中的签名是拟新增demo API，不冒充现存API；DTO全部严格不可变，秘密repr禁止。

## 配置、初始化与角色边界（A33-01—03、06、11—12；D2/D4）

DemoRunConfig严格字段见JSON；version固定为拟demo-v2，run_id为UUID，owner_id非空合成标识，scope精确三字段。endpoints固定HTTPS origin及三个预登记did:web URL，无任意URL入口。roles必须恰好operator/as/gateway/did/audit/publisher/worker/planner/selector/executor/export/offline；角色公有配置分别交现有ServerConfig/GatewayConfig/AuditConfig解析，禁止宽松透传未知字段。角色private_files按角色精确允许键，值只为私有树内叶文件引用。拒重复JSON、未知字段、bool冒integer、非法UID、符号链接/alias/越界路径及大小超限；配置本身≤65536字节，私钥/秘密不嵌入公共run配置。check纯离线，不连DB、不建目录。

init仅新exclusive owner目录，以现有private_directory/write_file保护0700目录和0600秘密文件；生成独立SM2用途key及CSPRNG角色secret、开发RSA CA和精确SAN证书。operator短命持CA signer/审批/初始化材料，运行后卸除；角色UID显式且各holder不同非0，运行树chown后由各角色以自身UID检查。三holder仅各自key/client Basic及只读公有trust；AS signer和所有client验证secret；GW公钥配置+现factory必须的authority/DS凭据及DS secret；worker必要authority/DS与DS secret；publisher receipt signer+账本role；audit signer+独立audit DSN；export SELECT-only role+private spool；offline仅独立公钥/pin/history。每role最小只读mount、非root/read-only rootfs/tmpfs；authority/DS/audit三个独立PG与网络，holders无PG route。共同宿主管理员受信任；GW仍持DS凭据，不声称隔离为独立机构。实际跨角色读与DB网络拒例来自role内真实进程。

DID审批输入registry必须预先独立绑定tenant/client/DID/kid/SPKI及用途：三holder authentication/capabilityInvocation，planner/selector另有capabilityDelegation。operator按精确URL/443、开发CA/SAN/no-redirect/media-type/65536上限取得，以IdentityResolver.resolve_registered验证再核独立持钥证明；TLS成功不等于SPKI批准。输出冻结canonical字节/hash和公开证书fingerprint，经operator只读渠道分发factory的did_documents，运行不热取远端；轮换新kid另批准并停用旧key。错误CA/SAN/redirect/controller/用途/替key/manifest错必须无新批准配置。

## 真实调用与进程移交（A33-04—05、07—10；D3）

provision仅复用register_user/register_task_policy/register_principal、bundle迁移及MockDownstream.provision，固定catalog/供应商/请求/recipient allowlists；不调用create_task_root/child，也不构造VerifiedInvocation。server.factory.build_app(ServerConfig, SecretsBundle, dsn=authority)与gateway.factory.build_app(GatewayConfig, GatewaySecrets, gateway_dsn=authority, downstream_dsn=independent_ds)为现存绑定。GW export另传SELECT-only connection factory/private spool；普通GW无export registration不传这些参数。使用真实SDK，不import tests或复制密码/SQL。

planner独立进程保存state/nonce/verifier，GET /oauth/authorize→GET/POST /ag/login（真实cookie/CSRF）→POST /ag/consent→固定redirect核state/code→POST /oauth/token authorization_code+S256 verifier+planner Basic和真实redeem proof；verify_id_token独立信任keys/issuer/aud/nonce，Access Token才用于工具。planner POST同一/oauth/token，token-exchange form绑定父token与selector收窄请求，planner Basic+purpose=delegate proof；AS签selector child，定向handoff给selector。selector再以自身Basic/key、selector parent、executor收窄请求做第二次exchange并定向handoff。不能用目标holder Basic冒父身份。金额/calls/depth固定100000/12/2→80000/10/1→70000/8/0并逐维收窄。

handoff采用独立pair目录0710与socket0660（receiver UID/固定pair GID）、双向Linux SO_PEERCRED精确peer UID和注册client/任务/run校验，每对父子独立共享socket目录mount；只允许planner→selector、selector→executor。信封精确version/run_id/task_id/sender/target/token，≤65536，ack不含token；无任意URL/脚本/转发入口，日志只给公开摘要。适配Linux SO_PEERCRED；生产容器平台明确固定Linux，不用同UID假隔离。executor顺序调用四正式tool ID/version字符串1；每invoke/result-read均新sign_ag_proof、固定POST endpoint、精确body/token摘要，query必须原holder/grant且当前有效。poll单列并等terminal+READY；ID Token不作授权。

worker拟OwnedOperationRegistry是本demo持久owner受控操作ID清单，由runner登记每个accepted operation，restart恢复；对全清单公平cursor分批fetch_operation/fetch_lease，选择RESERVED/expired EXECUTING/UNKNOWN调用现有run_operation，query-only故障恢复调用reconcile；不添加扫描SQL、schema或新生产mode。清单不授权业务，持久不可变operation及现lease/fence仍是唯一真相；漏登记由runner重读已接受回执恢复并作为完整覆盖验收失败，不能忽略。批次1..64、轮询有界、stop停止领取并等待当前step；异常逐操作安全码，busy/失lease不会release预算，未知结果保留UNKNOWN。pause仅demo故障装配复用现service seam，不增加生产HTTP开关。publisher复用receipt_worker.run/现InternalPublisher；audit delivery复用现DeliveryWorker/AuditClient。

## Bootstrap、export维护及移交验证（A33-05、09—14；D1/D3/D4）

先真实AS根与两child，尚不invoke。stop/drain AS/GW/worker/publisher等所有authority writers，记录PID退出、inflight完成和不可写保障形成DrainReceipt；不以CLI布尔参数替代证据。调用现bootstrap CLI bootstrap --writers-stopped-and-drained或同bootstrap_task_tx，获得RegistrationDescriptor；独立audit operator register-stream/register-key/register-principal成功核对后恢复服务。若已有pending stream只describe-pending并注册原descriptor，不反复bootstrap覆盖。正常执行/READY/journal后delivery至独立audit持久checkpoint并ACK；丢响应按现协议重传，历史keys保全。

业务terminal且READY后再drain全部writer；用独立reader经AuditClient取得完整既有history至固定H及latest checkpoint，按现load_checkpoint_history验证，冻结独立public trust/external pin/history三文件。GW factory启动只捕获一个scope；受控停export GW、绑定此三文件和SELECT-only role、重启TLS，再固定完整snapshot export；不从请求/包内建立trust、不热更新、不增分页。offline verify_task_bundle(stream, external_trust, external_pin)，历史/最新性/UNANCHORED限制如现A32。公开交付等合成凭据过期或撤销，保全部原件/关联/SHA，无secret/DSN；256SKU和256MiB总包及既有更严HTTP/JWS/frame限制实测，不截断。

本包已绑定A32接受及实际SHA；A32 exact ACL guard与readonly grant生命周期原资格保留，本提议不加阻断。未发现必须扩scope的冲突；上述API是最小适配提议，需正式包审判断。S0串行完成配置/DTO/七模块及fixture，自查实际签名/严格拒例/真实factory装配后STOP+SHA；S1 scenarios及deploy独立资源只消费冻结S0，不互读半成品。所有S1 STOP后S2唯一接手__main__、compose/pyproject/docs并记录文件移交。完整source和非editable wheel真流程/role拒例/10轮原安全竞态故障/原继承矩阵与独立验收仍必需；此处不运行测试，不授READY。


权限补齐：两个pair GID严格不同且非0，planner仅第一组、selector两组、executor仅第二组；各pair目录只mount给该对角色，sender无目录写权限。SO_PEERCRED验证不能代替实际文件权限；成功连通与wrong UID/group拒例均绑定A33-03原义务。私钥/DSN目录0700及文件0600不变，不共用IPC组。初始化的短命特权只用于新owned树chown/mode/mount，不赋予运行holder特权。旧0600 socket提议仅历史，不为放行修改私钥边界。

## v2 必要装配补正：A33-PR-R1-001

r1独立包审结论 PACKAGE_CHANGES_REQUESTED，完整覆盖173/165/508/55/17/21/23/30及587/Git7；STOP与完整失败证据由 review-r1.md 固定。只补 audit 回环监听的实际跨容器装配缺口，A32接受与旧门不变。v2需全新独立PACKAGE_REVIEW后才可实施。

S0唯一增写 audit/config.py、audit/server.py、tests/integration/test_audit_tls.py；其它core继续只读。既有AuditConfig严格schema不增环境开关，默认load接受loopback/server仍只127.0.0.1，旧0.0.0.0拒例全部保留。拟接口：AuditConfig.load(path: Path, *, approved_listener_host: str | None = None)；create_server(config, *, store=None, approved_listener_host: str | None = None)。None保持旧行为；显式opt-in必须是本run已分配audit角色的精确canonical RFC1918 IPv4且config.host与其逐字一致。拒绝未批准/其它IP、公网、全接口0.0.0.0、multicast/link-local/unspecified/非canonical/hostname/bool/错误类型。可信operator初始化唯一owned network内已分配地址，保存公有不可变资源/role映射，正常demo入口从已校验映射传相同地址给load和create_server；不能由请求、远端DID、holder或环境变量决定。地址只是bind许可，不授audit身份或DB权限。

不修改现audit CLI默认serve路径；A33 demo入口直接按上述精确参数调用create_server并受控运行。无proxy/复制server/共享网络namespace。TLS最低版本/CA/SAN、private_files、PG verify-full、注册stream/key、writer/reader role/scope、HTTP framing/body及零写拒绝全部原样。S0 test_audit_tls追加精确opt-in/未批准/公共/错地址拒例，所有旧assert AST保留；S1 role test真实分离容器通过固定DNS HTTPS append/latest/history/records，验证错CA/SAN/明文/credential/role/scope/未注册/framing拒绝无持久写。受影响旧audit config/server/TLS及完整继承矩阵均由S2与新独立验收source/wheel fresh执行。
