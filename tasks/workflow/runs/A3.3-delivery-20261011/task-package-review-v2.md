# A3.3 新独立包审任务 v2

review_kind=PACKAGE_REVIEW；请求gpt-6.1-sol/high，有效metadata未知记UNKNOWN。只读项目/code/callers/原需求与正式包；仅写自己新UUID ignored证据，不运行业务测试、不建容器/DB、不写正式文件、不做Git写入、不派其他agent。主控冻结清单单独提供；首末亲核文件SHA与实际Git，全部writer STOP。

必读AGENTS/AGENT、current-policy、HANDOFF、implementation/review/original workflow-contract、最新连续真人授权，原A2完整任务/接口/安全/验收、原A3规划requirements/test-plan/D1—D4合同、A3.1接受、A3.2正式接受/r1否决/补正/r2原件索引及受影响实际SDK、factory/CLI、tests。读取本目录package-v2/requirements-v2/node-bindings-v2/ownership-v2/runtime-plan-v2/interface-v2/upstream-pins/accepted-api-bindings。完整173父项/165运行义务/269+95+73+71原子、55新回归、21语义23声明30目标不得减少；17新根为PLANNED未实施，不能以尚未通过新功能拒绝包审，也不能由包审替代IMPLEMENTATION_ACCEPTANCE。

独立确认真实browser cookie/CSRF/state/nonce/PKCE+两AS签child与父Basic/PoP、四tool/query/worker、公钥用途与DID固定HTTPS审批、三PG/TLS/UID/mount/network最小权限、maintenance bootstrap/audit register/delivery/export最新外部pin/完整offline、256SKU/oldcaps、10有效竞争与真kill/restart/发布轮换升级备份恢复、clean source/wheel/实际5分钟脚本等全部原义务接口/所有权/完整运行证据计划闭合。特别核新pair IPC权限是否真实可行（0710/0660/精确两GID/双向SO_PEERCRED/非0不同UID/私钥0700/0600），Dockerfile/Compose交付是否干净可复现，S0串行共享冻结→S1独立文件与资源→全部STOP→S2唯一整合。只有真实必要scope变化提出具体owner/接口/测试补齐；不扩无关功能或美化。A34完整逐task/预冻分区export+全manifest/oracle允许，分页只在原义单scope必要且实际超cap又不能完整分区时另正式审，勿新加无条件分页门。

返回完整每ID/父项及必要问题依据、PACKAGE_READY / PACKAGE_CHANGES_REQUESTED / BLOCKED；原历史停止/pending不代当前真人scope/实际A32接受。不自授实施/下一阶段权限或更改state。报告、完整manifest、最后STOP/no_more_writes；由root核证决定。

## v2 必要装配补正：A33-PR-R1-001

r1独立包审结论 PACKAGE_CHANGES_REQUESTED，完整覆盖173/165/508/55/17/21/23/30及587/Git7；STOP与完整失败证据由 review-r1.md 固定。只补 audit 回环监听的实际跨容器装配缺口，A32接受与旧门不变。v2需全新独立PACKAGE_REVIEW后才可实施。

S0唯一增写 audit/config.py、audit/server.py、tests/integration/test_audit_tls.py；其它core继续只读。既有AuditConfig严格schema不增环境开关，默认load接受loopback/server仍只127.0.0.1，旧0.0.0.0拒例全部保留。拟接口：AuditConfig.load(path: Path, *, approved_listener_host: str | None = None)；create_server(config, *, store=None, approved_listener_host: str | None = None)。None保持旧行为；显式opt-in必须是本run已分配audit角色的精确canonical RFC1918 IPv4且config.host与其逐字一致。拒绝未批准/其它IP、公网、全接口0.0.0.0、multicast/link-local/unspecified/非canonical/hostname/bool/错误类型。可信operator初始化唯一owned network内已分配地址，保存公有不可变资源/role映射，正常demo入口从已校验映射传相同地址给load和create_server；不能由请求、远端DID、holder或环境变量决定。地址只是bind许可，不授audit身份或DB权限。

不修改现audit CLI默认serve路径；A33 demo入口直接按上述精确参数调用create_server并受控运行。无proxy/复制server/共享网络namespace。TLS最低版本/CA/SAN、private_files、PG verify-full、注册stream/key、writer/reader role/scope、HTTP framing/body及零写拒绝全部原样。S0 test_audit_tls追加精确opt-in/未批准/公共/错地址拒例，所有旧assert AST保留；S1 role test真实分离容器通过固定DNS HTTPS append/latest/history/records，验证错CA/SAN/明文/credential/role/scope/未注册/framing拒绝无持久写。受影响旧audit config/server/TLS及完整继承矩阵均由S2与新独立验收source/wheel fresh执行。

本轮必须全新 reviewer；v1 PACKAGE_CHANGES_REQUESTED不可当接受。完整覆盖保持，禁止为命名或美化新增无关阻断。
