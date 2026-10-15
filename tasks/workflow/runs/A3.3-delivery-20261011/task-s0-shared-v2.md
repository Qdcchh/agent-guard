# A3.3 S0 共享前置任务草案（不得先开工）

AUTHORIZED_S0_AFTER_ROOT_VERIFIED_FRESH_PACKAGE_READY。主控已亲核新r2 PACKAGE_READY/STOP/45原件与597/Git7；仅授权本S0实施，不授阶段接受。worker请求Sol/low，effective metadata UNKNOWN；持续真人范围经正式授权至A34，worker只完成本S0后STOP，不自行进入S1/A34/Git发布。

必读AGENTS/AGENT、current-policy/HANDOFF、implementation/review/原workflow-contract、A3.3完整正式v2包/173+165需求/508原子/55补正回归/完整节点/所有权/接口/运行计划、原D1—D4和A3.3任务、A3.2接受/失败/补正及实际受影响src/test，不以主控消息概述代替。正式PACKAGE_READY和当前文件SHA传入后再写。

## 独占与串行

仅ownership-v2.S0十三个路径：demo/__init__.py、config.py、init.py、did_bootstrap.py、provision.py、client.py、handoff.py、worker.py、__main__.py、tests/fixtures/a33_demo.py，以及audit/config.py、audit/server.py、tests/integration/test_audit_tls.py这三个v2精确补正路径。不写S1/S2文件、核心SDK/生产迁移/锁/正式文档/state，不导入测试到生产。共享DTO放config.py，不先新增其他文件。__main__本段只暴露已完成S0功能，不import未实现S1。结束自查/真实资源核验、实际接口/文件SHA和STOP后，主控才派S1并行；显式__main__移交最后S2。

## 完整共享适配

按interface-v2七API与实际accepted-api绑定实现，使用严格不可变DTO和现有密码/编解码/身份/AS/GW/账本/audit/receipt/export API，不复制验权/SM2/SQL。完整功能与拒例一起实现，不用docstring或测试替身装进生产。

config：固定version/runUUID/角色/三scope/HTTPS端点/预登记DID、独立公有manifest及每角色私有文件精确allowlist，bounded65536、重复/未知/bool整数/UID/GID/path alias/symlink/越界全部拒绝；check纯离线不创建目录/DB。具体Role/Worker/Holder DTO与每角色file键必须本段在公开接口回执精确固定，S1不猜字段。init独占新owner树CSPRNG、独立SM2用途key/Basic/user secret、私有CA/精确SAN，使用成熟已有工具和0700/0600；真实role不同nonrootUID/最小挂载/三PG域/网络不能靠unset-env假隔离，初始化短命特权步骤明确记录后撤除，normal部署不依赖ignored历史镜像/venv。

handoff：Linux两pair目录0710/socket0660、receiver UID与精确pair GID，planner只第一组/selector两组/executor第二组；sender无目录write，私钥不共用IPC组，双向SO_PEERCRED+run/task/client/方向/目标严格核，bounded65536/token不进入日志或ack。用真实不同UID正向连接、wrongUID/group/target/run/task负例，不能同UID替代。至少真实Linux文件/组/peercred装配自查后再freeze。

operator DID：固定443/CA/SAN/no-redirect/media-type65536，预批准tenant/client/DID/kid/SPKI/purpose独立校验与持钥证明，冻结immutable did_documents，TLS成功不等于批准；旧dict/远端改变不影响factory抓取内容。provision只注册user/TaskPolicy/principals/catalog/真实DS数据及迁移，不手造root/child、VerifiedInvocation或信任包内key。

DemoClient按真实cookie/CSRF/state/nonce/PKCE/token redemption+plannerBasic/redeem PoP、IDToken issuer/aud/nonce核验、两次父Basic/delegate PoP/AS签child，以及invoke/query新proof/current auth；token用途/parent/target固定，四工具version1，正常预算100000/12/2→80000/10/1→70000/8/0。保持原请求/报价/首次材料/非canonical原件/完整所有祖先预算撤销与UNKNOWN语义，无公开recover/fault/sign/skip开关。

Worker复用ExecutionService lease/fence/run/reconcile，持久OwnedOperationRegistry公平有界批次/停止领取并drain。明确可信runner登记accepted IDs到registry与独立worker UID的实际读写/挂载/重启生命周期（operation IDs不是授权，不能靠其他holder可写文件授予能力）；私有credential仍0700/0600，不同角色不能因方便共用UID或secret。配置scope绑定真实accepted操作，漏登记/持久失败不吞掉，由最终完整覆盖探针检出。不得新增生产扫描SQL/schema/模式。

bootstrap维护严格停止drain全部authority writers/真实PID及inflight证据→原RegistrationDescriptor→独立audit注册→恢复；export之后再次冻结scope/latest/history/public trust，受控单scopefactory以SELECT-only导出。S0提供可复用真实接口与fixture给S1，完整三holder/四工具/所有故障的最终联合演示由S1/S2，不冒阶段验收。

## 自查与交付

自有UUID资源/三PG/私有树/网络分离，先核fullID/owner/project/service/mount/UID/start/fullargv，不连无关容器，不prune/shared down。source与非editable wheel在仓库外安装，现锁Python3.11/SQL资源，禁PYTHONPATH/tests-import；配置/初始化/AS与GW工厂/真实DID HTTPS/Basic+PoP/不同UID handoff/持久registry worker/维护bootstrap装配做有限真实正负自查。S0局部自查不替代S2全继承+新阶段矩阵或fresh独立验收。生成共享API实际签名/DTO字段/错误映射、配置canonical示例（公有无secret）、每接口源码SHA、实际测试/命令/exit/XML/raw/SHA、资源完整清单及有限运行上限；向主控交READY_FOR_REVIEW_PENDING_ROOT，不自授ACCEPTED。

出现真实功能/安全/接口必需阻断在本段快速最小补正，保存失败原件，不删assert/skip/放宽预期；非阻断命名/格式快速完成，不引入额外功能或美化。范围/接口实质变化先报主控重规划/新包审；普通字段/实现选择按已审API与安全约束固定。网络失败先zsh -ic setproxy，不输出代理secret；不读额度接口。所有自有writer/资源确实结束后完整manifest与最后STOP/no_more_writes，原进程退出无法观测保UNKNOWN。

## v2明确必要适配

按A33-PR-R1-001消解契约实现 AuditConfig.load(path, *, approved_listener_host: str|None=None) 与 create_server(config, *, store=None, approved_listener_host: str|None=None)。默认所有旧行为与旧测试assert AST不变；opt-in是本run operator分配审计角色的精确canonical RFC1918 IPv4，config.host exactmatch，两入口独立检查，trusted immutable manifest→demo入口显式传同地址。拒0.0.0.0/global/linklocal/multicast/unknown/wrong IP/hostname/noncanonical/bool类型；无隐式env或远端决定。不要改原audit CLI默认serve，不复制server或加proxy，共享secret/namespace。TLS/private/PG/身份/role/scope/注册/framing零写拒绝全部保持。独占test_audit_tls.py追加实际opt-in正负测试；所有原函数原assert AST保存、未影响段不重写。源/wheel本段真实跨容器连通与调用局部自查，最终完整17+补正实际collection由S2冻结后跑。

正式包接受记录 package-ready-v2.json；复审候选SHA d721a00876af439acd03b6a1dfdd9830006cb6e05d38c6fa00373dd97185694f，review STOP SHA d2467aa28298b611ee0fa7b7557f346912a8c6aaa0c0f61b5d593b3c58cb6ee4。原audit TLS 6函数27断言基线在 ignored controller/audit-TLS-original-assertions-before-S0.json，实施后逐条AST核保留。
