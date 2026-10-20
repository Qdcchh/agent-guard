# A3.1/A3.2 接口与验收合同（2026-10-08）

状态：PLANNING_BASELINE，待本轮独立规划审查；业务 NOT_RUN，非业务 PACKAGE_READY / IMPLEMENTATION_ACCEPTANCE。本合同只消解接口和验收设计，不授实施、测试、数据库、容器、安装或 Git 发布权。请求主控 Astra、worker Sol/medium、fresh reviewer Astra/high；后台有效 metadata UNKNOWN。历史 Sol/xhigh、A23 pending、旧日期和旧 hash 仅是历史快照，不控制本轮。

本轮权威为 authorization.md、current-policy.md、package.md、本合同以及同目录 requirements.json / test-plan.json 的当前解释。requirements.json 原 A31/A32 40父项、168子断言逐字保留；每个原子 ID 对应 test-plan.json audit_atoms 的 finite_case_ref，运行覆盖取 audit_nodes.local_assertion_atoms 与 audit_native_obligations 的联合。原文行为必须完整满足，不能用单节点、计数、摘要或 ignored 链接替代。§10给出逐父项节映射；JSON原子原文无需再复制巨表。全部 A2 119/269、21P、30goals、原前段和历史失败等价义务保留；不生成51个继承 wrapper。

## 1. 已接受依赖与当前真实接口

完整 A2 接受记录为 ../A2.3-receipts-20261004/acceptance.md；本轮读取产品绑定为 baseline.json（HEAD 2a8cc7da4867ad1876350855c0ed5569c5ce6472、发布快照 a85a822085707874ef8dd6fb47c8601cf1a56c81，产品字节关系由主控核验）。旧规划针对未接受 A23 的判断必须以实际代码替换；未来每段正式包再绑定届时实际接受的源、完整树、调用方、接口和证据。此处 hash 是本轮读取基线，不是未来候选 freeze。

真实已有：ExecutionLedger.accept / accept_checked(existing_validator) / accept_bound(existing_validator,binding) 汇入 ledger/service.py::_accept_tx；ExecutionService.accept_invocation(binding=None) 的 candidate hit、报价失败安全 recheck、新报价与事务竞态最终汇入同接受事务。EvidenceStore.binding(bundle) 当前返回逐调用普通 closure；它同 TX revalidate PermissionSource、核 STAGED 原件并建立 immutable first/retry link。VerifiedExecution.accept 使用该 binding；accept_response 当前另包外围 closure，先原 binding 再 ReceiptVerifier.read_tx/响应物化。AuthorizedQuery.query->_query_tx 保留真实 query bundle/source、原 first 材料、当前动态权限、query purpose proof/link、响应和末尾 clock。query_binding 当前不插入 kind=query 的 operation_evidence，成功 query 的必要关联由 proof/link 加原件与新增 journal 实现，不能把 STAGED 当成功。

真实首次 READY writer 是 execution/receipt_publication.py::InternalPublisher.publish：仅锁 ag_receipt_outbox，read_tx 验证、project_receipt、真实 sign_compact_jws、自验、UPDATE PENDING→READY、flush。已 READY 返回持久原 JWS。ExecutionService._finalize 已有 task→grants→operation/lease、owner/version/state/expiry 初查后四 counter/event/PENDING/status 写入；新增 journal 等待后必须增加最后 fence，不把早查当晚查。

真实密码 SDK 为 crypto/sm.py 的 Tongsuo SM2/SM3、固定 USER ID、SPKI、64字节 r||s、GM原始JWS输入，encoding.py 的 RFC8785/strict codec；当前 JWS_TYPES 只有 id/at/pop/receipt，没有 checkpoint。当前没有 audit 模块、execution007、task export / task verifier、TrustedAcceptBinding 或 WriteFence 新 API；下节均为拟新增。

现 evidence/receipt.py::verify_receipt_bundle 已按逐组件 canonical 字节和 ledger 专属 codec 计算准确外层1MiB，没有历史草案 other_bytes 整 outer 65KiB 问题。原 A2 容量缺口已闭合，51035/64695是包含域上界，不是共同可达最大值。A32-03旧“待A23容量闭环”解释为保持此实际接受行为及真实合法业务再验证；不复活旧问题，不放宽现边界。

## 2. 日志 scope、字节与必需事实

选择每 gateway/tenant/task 唯一 stream，随机持久 UUID、epoch=1，无 reset/re-epoch；sequence 从1连续且回滚不烧号，禁止 nextval/global head。gateway_id 从可信固定 INVOKE_ENDPOINT 规范 origin 得到，不能从 Host/Forwarded/body/callback bool/环境 skip 值得到。重启读取持久 scope；回滚缺 stream 时对外部登记核对，不能新 UUID 绕过已登记 task。

genesis=SDK SM3(规范固定 profile/gateway_id/tenant_id/task_id/stream_id/epoch 对象)，不使用空值或凭空零。journal profile 为 AG-AUDIT-JOURNAL-1；canonical record 严格字段为 journal_profile,stream_id,gateway_id,tenant_id,task_id,epoch,seq,record_id,kind,operation_id(nullable),evidence_ref(nullable),previous_digest,recorded_at(整数UTC秒),facts。digest=sm3_b64url(完整 canonical record bytes)，不包含自身；保存、传送、导出原字节。record_id 含 kind 前缀并绑定真实唯一事件，FIRST/TERMINAL各用op、RETRY/QUERY用本次 evidenceRef、PUBLISH用receiptID，不共用同一个无kind ID。

默认 mandatory kinds 仅 BOOTSTRAP、FIRST、RETRY、QUERY、TERMINAL、首次 PUBLISH；BOOTSTRAP为启用边界，不是业务交互。按A31-S01消解旧design的“所有lease/UNKNOWN/quarantine都日志”：本轮不增加这三类额外记录或 coverage 门。原 claim/UNKNOWN/quarantine 语义和恢复保留；若未来正式包有具体理由新增辅助记录，先明确字段/guard/新增等待后的fence及精确测试，再独立包审，不能暗增约束。不是整个AS签发/撤销审计，不包括拒绝TX和孤儿STAGED。

facts 使用固定kind字段，只容安全IDs/digests/非负计数/status/fencing/path<=3；FIRST含intent/token/proof/source/context/RESERVE/quote原件及path摘要，RETRY/QUERY含当次材料、原operation、当前source、确切响应/status/JWS摘要；TERMINAL含完整ledger/result/outbox/fence；PUBLISH含原JWS ASCII摘要/receiptID/signed_at；BOOTSTRAP含snapshot root。负delta仅原 canonical_ledger_changes_bytes 编码后取摘要，不放入普通JSON负数。ID<=512 ASCII、record_id<=2048 ASCII、kind<=64 ASCII、SM3摘要规范32字节b64url，raw record<=32768。保持默认65536 bytes、4096 nodes、depth64、总字符串65536及safe integer；拒绝重复/未知字段、float、bool-as-int、溢出、非法负值、非canonical记录。

拟GW表：ag_audit_streams、ag_audit_records、ag_audit_bootstrap、ag_audit_bootstrap_chunks、ag_audit_delivery、ag_audit_delivery_batches；具体SQL列、FK、不可变guard和完整库存由正式S0落盘。stream metadata immutable，head每次只old+1且对应本TX真实record；records/snapshot/chunks/pending exact body 不可改删。deferred coverage 按数据库本creating xid、scope、op/ref、实际facts核 FIRST/RETRY/QUERY/TERMINAL/首次READY，不接受客户端声明；record反查事实。新enabled任务的旧binary无journal写必须拒绝，未enabled历史不rewrite。row guards不代替正常装配成功正例。

## 3. 事务内 seed、默认结构责任与最终时钟

新增拟类型 JournalScope / ExistingStreamRef / LockedAcceptContext / EmptyTaskBootstrapSeed / TrustedAcceptBinding 在 audit/contracts.py 与 evidence_store 内部契约固定。seed是本次 _accept_tx 局部、深不可变tuple/bytes、绑定scope/root/current TX/capture DBtime/schema lineage/FROM_EMPTY_TASK，包含有界真实基线原件/chunks/count/root/wire，不含connection/shared mutable/global状态；事务重试重新捕获，不跨TX复用。

新增拟 BeforeCreate(conn,LockedAcceptContext)->None、AfterLink(conn,OperationRow,AcceptDisposition,ExistingStreamRef|EmptyTaskBootstrapSeed|None)->None。所有ledger/service接受入口保留原位置及必需keyword，增 before_create=None,after_link=None 并逐分支传递；旧bound两个原callable仍必需。non-None非callable写前拒绝，单侧hook允许；它们只准备/附加真实材料，不创建/替换seed，不拥有append，不connect/commit/network。None不解除enabled日志责任。

EvidenceStore.binding拟返回模块内构造的 TrustedAcceptBinding：descriptor来自exact已验VerifiedInvocationBundle/PermissionSource，逐调用immutable、含scope/原source绑定与材料能力，调用行为保留原bind。VerifiedExecution.accept_response 的外围composite拟用同受信wrapper显式保留descriptor，同时保留原出版验证等待；不反射closure/name，不凭opaque evidenceRef/STAGED存在复原可信bundle。direct accept/checked若enabled本次要signed交互，通过相同可信材料附加器绑定；普通callback非真实性证据。不复制AS密码/权限实现。

结构capture/ensure/append内建于ledger._accept_tx、service._finalize、query._query_tx、InternalPublisher.publish，不是由可选callback开关控制。已有stream必须记录允许成功的本次交互；缺stream的legacy opaque/非A3 trusted路线保留旧语义；真实A3 public bundle缺stream仅全task空历史/四零可自动方案A，否则须维护。需要A3能力但007/scope/材料不可用则拒绝，不业务成功降级。

CREATED顺序固定：load path→principals→task→root至leaf grants→初始freshclock→proof登记→business key查找→预算检查→结构 capture（insert/reserve之前）→insert operation→所有祖先reservation/RESERVE→原binding/PermissionSource复核→proof-link全部等待→可选材料after_link→结构核真实材料→晚ensure_stream/append BOOTSTRAP1+FIRST2→flush→已锁principal/grants/必要source复核→最终数据库clock→纯内存return/commit。已有stream只FIRST；EXISTING只RETRY，不capture零seed、不重新报价/预留/计数；交易竞态按实际row而非前读判断。证据不足不能用新retry修旧first/quote/result/outbox。

capture在task锁下检查完整task grant集合，所有off-path四counter及所有accepted op/event/nodes/seals/linked proofs/evidence/lease/outbox/review/sidecar历史；cap+1探测超限整TX拒绝，无截断。尚未link的本次proof和独立STAGED孤儿不冒accepted历史。新正成本c/calls1：bootstrap所有grant真实零、无本次op/event，FIRST仅加一次c/1。任何旧历史/非零counter，即使新key miss，也不得EMPTY seed或reserve后减cost倒推。

旧task：停旧GW/worker/publisher/AS writers、drain在途TX、维护协调/强锁，然后task→grants→operations→leases→outboxes→head，保存真实非零counter/status/asof/schema/material能力snapshot；seq1 BOOTSTRAP。旧opaque/short/missingraw保留预算与原事实并明确GAP，不能伪造过去FIRST/顺序/时间。新grant后入：实际provisioning/exchange持task锁；首次FIRST携完整真实AS签名链/不可变intent/path/绑定可信创建来源，预留前核从未执行且四零，才introduced-zero。已有非零/旧FIRST/未知来源/gap节点不能清零，不要求以后所有grant提前bootstrap，不扩成全AS审计。

锁序：public principals→task→root-to-leaf grants→operation→lease/outbox→journal head；内部终局保留task起序；publisher仅outbox→已有head，无outbox→task bootstrap。head后不能首次取业务锁/网络，约束业务等待须预先处理，flush后只有已锁状态复核与最后clock。query先完成全部原件/link/projection/response限额，再QUERY、flush、finalclock，不将seq塞响应产生循环。首次READY先真实签验/UPDATE再PUBLISH、flush；READY重试原JWS无第二PUBLISH。

终局拟 capture_write_fence 锁下捕获合法prestatus/owner/version/expiry；暂写counter/event/PENDING/terminal status→TERMINAL→flush→assert_write_fence_current(expected_terminal)，最后DBclock核owner/version/status/expiry，允许本TX刚写终局，不调用“已terminal拒绝”的旧helper误杀。禁止续租洗白迟到。过期整TX回滚所有counter/event/status/outbox/journal/head；已下游效果仍原意图待恢复，不RELEASE或重执行。辅助路径将来若新增等待亦必末尾fence。

## 4. 迁移、wheel及自有隔离

保留原14 SQL raw、checksum、registry/applied_at、历史 _V2_COMPLETION_FLOOR。原库存是common001–003、execution004–006、authorization004–010、infrastructure/lineage001，绝非authorization001–010。新增execution007依赖execution006+authorization010，完整GW qualified bundle总15；audit001独立audit DB/registry，不能算GW第16份。

migrate._discover 默认原standalone001–006固定发现/校验；007只由显式bundle协调器依双依赖执行，已有bundle-aware返回语义保持。custom历史目录保留原缺文件/checksum/TOCTOU/B谱系/旧非零拒绝；直接raw依赖型007在DDL前拒绝。lineage空库初始化先原A001–006 legacy registry及原applied_at，再依赖有序auth010→execution007；不能现空库for common/execution直接顺带007。source/非editable wheel、异cwd必须包含15GW+独立audit001且各入口各库存真实核对。PG16现基线支持；PG14需按实际能力明确支持或明确拒绝，不能默认声称兼容。

S0精确扩展 isolation.py 显式新GW表/reset closure：仅assert_owned成功的run namespace，migration owner可精确TRUNCATE，生产runtime无TRUNCATE/DDL；不删guard、不DISABLE TRIGGER/session_replication_role/no-journal环境、不清ag_%、不碰audit DB、marker/provenance或无关资源。旧无007分支保持。若真实guard无法安全owned TRUNCATE，正式包重新选择每例namespace与精确conftest范围，不先授无限fixture写权。lineage最新15与remaining-count按真实manifest精确改；旧14 completion floor拒绝、旧upgrade返回和历史失败不改。重复signed task/reset必须无旧stream/head/pending，fresh genesis seq1。

## 5. 独立检查点、传送与恢复

独立audit进程/DB/签名key/private配置/TLS权限域；同机只称逻辑隔离。operator本机CLI init/register/check预登记gateway/scope/stream/genesis/bootstrap/boundary，writer不能自注册/重登记回滚task；无公共register/sign路由。bootstrap_cli migrate/bootstrap/describe-pending只产public descriptor，S0不import未完成service。新task本地提交后operator登记；未登记delivery=REGISTRATION_REQUIRED保留pending/预算，不为网络注册持业务锁。

拟POST /v1/audit/append严格{batch_profile,stream_id,entries:[b64url(raw)]}，entries1–64，实际canonical body<=65536。逐条raw<=32768，canonical/SM3/schema/scope/seq/prev均核，整批原子无部分接受。batch_id=SM3(exact canonical body)。audit TX stream row锁→先按batch查重→相同原bytes返回原JWS/issued_at/checkpointID→否则start=latest+1且连续prev→全部records→真实SM2签名自验→batch/checkpoint/head→commit→response。同seq不同raw/gap/fork拒绝；旧range换批409 RECONCILE_REQUIRED，不因SM2随机性重复签同事实。

checkpoint新增typ=ag-checkpoint+jwt，沿原alg/USERID/raw JWS；claims严格profile=GM-MVP-1,checkpoint_version=AG-CHECKPOINT-1,checkpoint_id,stream_id,gateway_id,tenant_id,task_id,epoch,sequence,head_digest,previous_checkpoint_digest,issued_at,kid。payloadkid=protectedkid；previous=SM3(previous原JWS ASCII)，首个null且genesis绑定；JWS ASCII<=16384。只信独立audit公钥/role/sequence范围，拒receipt/at/pop替代、unknown/wrong-role/SPKI/签名/字段；通用SDK类型列表只显式追加此typ。

latest返回持久原JWS，长停写不重签伪新时间。history固定此次observed latest ID/seq，分页实际canonical<=65536、每次最多64候选，按编码长度最大合法前缀；少页/漏链不能当完整，不能截断JWS。reader独立role、CA/hostname验证固定HTTPS，无plainHTTP/redirect/verify=False/任意用户URL。writer/reader/operator/signer权限分离，AS/holder/GW/downstream凭据不能冒充audit；错误脱敏不输出token/DSN。

delivery短TX仅锁delivery row，已有pending先复用，否则取连续最多64条按实际b64+metadata+JSON编码选最大合法prefix，persist immutable exactbody/batchdigest/start/end、设pending再commit释放锁→TLS→独立验scope/seq/head/previous签名→新短TX条件单调ACK并只clear匹配pending。不能rawsum估算、跳坏条、跨网络持head/task锁；单条不装明拒。pending后新journal增长和SIGKILL重启不能改变body/边界；双sender同pending，晚旧ACK不退cursor/清新批。remote-ahead先固定latest、多页previous原JWS链与本地每seq/hash连续前缀核对，不凭latest seq跳cursor；bad sig/missing page保持pending。坏stream有界轮转不饿死正常task。

audit/GW备份回退只对run-owned真实DB演练：与外部保留CP比较lowerseq/sameseqwronghead拒startup/append/export，不新epoch逃逸。无外部最新观察只能relative minimum或UNKNOWN，共同key/anchor失陷为明确局限。remote存前死亡无partial，存后丢回复新PID取原JWS；pending/send/localACK前后所有死亡窗口均真SIGKILL、不同newPID、同持久DB，不mock恢复。

## 6. 导出认证、快照、framing和容量

拟固定HTTPS POST /v1/evidence/export，仅严格body={task_id}，独立预登记audit管理凭据提供可信tenant/task权限；不用body租户、自报role、tool AGPoP或AS/GW/downstream凭据。same-name跨tenant/错role/TLS/framing/重复未知字段/超限拒绝，无DB写。export不invoke/recover/sign/register/任意URL。独立reader外部取得CP，export角色不能append/sign；公共trust和audit凭据初始化由S0严格配置，本地0700/0600，无默认业务DSN或私钥进入GW public HTTP。

READ ONLY REPEATABLE READ同快照捕获S/H、bootstrap、全部<=S journal/material、runtime observation；snapshot_as_of为该快照transaction_timestamp标签+规范snapshot标识，不是每行更新时间或当前未撤销证明。完整有界物化0700目录/0600 spool，header counts/root确定后结束DBTX才下载，无业务head锁跨网络；future terminal/READY/JWS不渗入。export自身不写GW/DS/audit/delivery；并发变化按TX/journal归属核，不要求全球状态不变。断连/进程死亡只清本次副本，不能删数据库原件；失败/超限回应前503，不截断。

AG-TASK-EVIDENCE-2采用canonical NDJSON：frame bytes<=65535，加单LF<=65536；无CRLF/BOM/空line/尾随extra。OBJECT_CHUNK严格{frame_type,object_kind,object_id,chunk_index,chunk_count,total_raw_bytes,object_digest,data}，object_id<=512ASCII，canonical b64url fragment<=24576 raw（encoded<=32768）。count=ceil(total/24576)，非末片exact24576，末片exact余量；原65536切24576/24576/16384。kind限token/proof/ancestor_token/receipt/checkpoint raw<=16384；journal<=32768；request/result/ledger/quote/context/source/raw_authorization_snapshot/typed_snapshot_metadata<=65536；祖先最多3枚分别object。未知kind或超logical raw拒绝，不改假ID拆超限物体。

同object chunks连续index0起且metadata恒定，稳定kind/ID顺序；每片接收前限line含LF<=65536，无LF长流不能无界增长，decoder先encoded限再decode，当前object最多65536缓存。重组exact raw长度/SM3/元数据一致后交原codec；原非canonical request保留raw摘要另核canonical intent。metadata用typed refs，不嵌整个task array/base64巨对象。

object fold I0=SM3(canonical{profile:'AG-TASK-OBJECT-INDEX-1',scope})，I_next=SM3(canonical{profile,previous,kind,id,total_raw_bytes,object_digest,chunk_count})，bootstrap专用AG-BOOTSTRAP-INDEX-1。wire fold固定scope/profile起始，每frame含LF摘要，W_next=SM3(canonical{profile:'AG-TASK-WIRE-1',previous,index,frame_digest,wire_bytes})；footer只宣告此前W/before_footer_frames/before_footer_wire_bytes，不自引用hash。读者加真实footer字节计全量，footer完整且EOF无extra才完整；缺footer=INCOMPLETE。fold只内部完整性，不作外部信任根。

全包wire<=268435456、frames<=400000、objects<=200000、journal<=100000、operations<=20000，含全部b64/metadata/JSON/LF/header/footer；bootstrap同总限且小root manifest<=32768。默认codec/节点/深度/总字符串限保持，不整包json.loads/canonical。10000固定 workload须从真实合法业务生成后精确wire/count preflight（四工具、token/proof/ancestor tree/retry/query/terminal/PUBLISH/CP/bootstrap全部计）；不代A34真实50并发10000calls。10000最大legal payload可能超256MiB，此时明确容量拒绝，正式包再规划固定持久snapshot分页或调整仅外包上限并审包，不能无限内存或删材料。codec合成65536边界与真正可达最大合法业务正例分开。

## 7. 组件验签、外部信任与诚实结论

现ReceiptTrust / VerifiedReceipt / verify_receipt_bundle为单笔AG-EVIDENCE-1、UNANCHORED。拟 ReceiptComponents + verify_receipt_components 是最小提取原SM2/claims/child narrowing/proof/historical共同窗口/intent/全祖先ledger delta语义；不是第二套密码实现。旧wrapper保留严格旧fields/version、逐组件原边界、准确outer1MiB及UNANCHORED返回；新task逐笔独立components aggregate<=1MiB，不先拼巨型v1 outer，不能切片绕过单组件限额。256不同合法SKU及三层真实AS树、holder proof、可信quote→public接受→真实PG result/node ledger/receipt→export→offline作为联合source/wheel正例，不拿随机blob冒合法业务。

独立AS/GW/holder/audit/catalog公钥和历史kid/SPKI/DID/client/tenant/role/sequence范围、scope/genesis/bootstrap/boundary、minimum或observed-latest CP由operator外部可信渠道交付；证据包自带key/自签登记/current DID/旧合法CP不能升信任根。TLS reader保存公有CP与请求时观察依据，旧CP JWS不重签；无最新外部观察不能保证最新。offline CLI只读public trust/external CP/bundle，无网络/DB/私钥/model API/env；输入SHA前后不变，不输出raw token。

验证顺序：strict framing/count/fold→seq1..S/prev/genesis→外部bootstrap/CP签名及previous链→相对minimum/latest的seq+head→全部FIRST/RETRY/QUERY本次原件及原operation关联→TERMINAL真实quote/result/完整path四delta/PUBLISH原JWS→bootstrap四counter加后续reserve/settle/release逐grant重算。检测已锚prefix修改/重排/删除/整op遗漏及相对外部锚回滚；改全部内部root不能绕过外部head。篡改单字段应到正确失败层，不能schema先败掩盖绑定检验。

报告分列cryptographic_consistency、anchored_prefix=N/cutoff=S/tail、freshness=EXTERNAL_OBSERVATION_PROVIDED/MINIMUM_ONLY/UNKNOWN、historyboundary/legacy IDs、逐grant四counter、current_auth=UNKNOWN、downstream_truth=ATTESTED_NOT_INDEPENDENTLY_PROVEN。anchored_execution_semantics只由BOOTSTRAP/FIRST/TERMINAL重构ACCEPTED_NONTERMINAL/SUCCEEDED/FAILED/LEGACY_GAP及derivation/cutoff摘要，外部保证仅<=N；无TERMINAL不释放。runtime_status_as_of是同RR快照ag_operations.status观察，始终assurance=UNANCHORED_AS_OF_DB_OBSERVATION，N=S亦不升级。TERMINAL后未PUBLISH为PENDING；只<=S PUBLISH绑定READY原JWS。

必须诚实正控：FIRST后无query无辅助kind，RESERVED→EXECUTING→UNKNOWN同S/H、同预留而不同runtime observation；合法非终局 observation被改且无密钥重算index/footer可能不可由锚检出。无最新CP时未锚tail全删并重算内部root也不能伪称DETECTED。仅N=S且独立exactpin证明relative throughN完整；legacy gap/short/missing raw不COMPLETE。历史共同窗口不证明真实接受时刻/当前未撤销，signed下游结果不独立证明现实效果，bootstrap不证明启用前未被伪造。

## 8. 精确拟文件 owner、串行和并行

以下是未来正式包候选allowlist，不是现在写权。每行路径集合必须正式逐文件SHA绑定；任何新增路径先更包审，不能整目录授予。共享接口/fixtures先S0串行自查STOP+主控读回冻结，S1只消费冻结输入，禁止import/read同阶段peer半成品；S1各STOP后单integrator凭明确移交可补正原writer路径，先更新精确allowlist，不并写。

A31 S0 a31-shared唯一writer：migrations/007_audit_journal.sql、migrations/audit/001_checkpoint_store.sql、pyproject.toml；src/agent_guard/audit/{__init__,bootstrap_cli,contracts,journal}.py；authorization/evidence_store.py、crypto/sm.py、execution/{query,service,store,verified,receipt_publication}.py、ledger/{lineage,migrate,service}.py；tests/fixtures/{a31_common,isolation}.py；tests/integration/test_audit_{atomicity,clock,fencing,lock_order,upgrade}.py、test_lineage_migrations.py、test_migrations.py、test_a2_migrations.py；tests/unit/test_audit_journal.py。receipt_publication是本轮实际确认新增精确S0路径。无必要修改execution/worker、gateway/factory、两个旧execution回归或conftest；若事实需要须正式重审。

A31 S1 a31-service：audit/{__main__,checkpoint,config,http_app,migrate,operator_cli,server,store}.py；tests/fixtures/a31_audit_service.py；tests/integration/test_audit_{service,tls}.py、tests/unit/test_checkpoint_contract.py。A31 S1 a31-delivery：audit/{client,delivery,delivery_cli}.py；tests/fixtures/a31_delivery.py；tests/integration/test_audit_delivery.py、tests/unit/test_audit_client.py。delivery独自冻结transport harness，不能依赖peer service半成品，真实双服务S2联合。

A32 S0 a32-shared：evidence/{receipt,receipt_semantics,task_bundle}.py；gateway/{__main__,config,evidence_auth}.py；tests/fixtures/a32_common.py；tests/unit/test_receipt_components.py、test_task_bundle_codec.py。实际已存在组件helper可复用则不重复新建。S0只codec/auth配置，不提前import未来export模块。

A32 S1 a32-export：evidence/export.py、gateway/{evidence_endpoint,evidence_http_app}.py；tests/fixtures/a32_export.py；tests/integration/test_evidence_export.py、test_evidence_export_tls.py。a32-verify：evidence/{task_verify,verify_cli}.py；tests/fixtures/a32_offline.py；tests/integration/test_evidence_offline.py、tests/unit/test_task_evidence_verify.py。verifier消费冻结public fixture不依赖未完成export；export消费冻结auth/codec不依赖verify CLI。

A31/A32 S2 single-integrator：HANDOFF.md、README.md、docs/{acceptance,crypto-profile-v1,oauth-oidc-sm2-mvp,security-model}.md、tasks/A3.1-report.md或A3.2-report.md、tasks/workflow/{README,context,current-policy,issues}.md、stages/A3.1-audit.md或A3.2-evidence.md；tests/fixtures/a31_joint.py或a32_joint.py、tests/integration/test_a31_joint_tls.py或test_a32_joint_tls.py；A32额外gateway/factory.py挂真实route。只一个writer且S1全STOP。后段A33消费实际接受的CLI/config/trust/framing/report；A34消费真实固定workload wire计数，当前不假设其API已接受。

每worker独占run namespace/GW/DS/audit DB、迁移/runtime role、CA/port/PID/backendPID/private/cache/spool/evidence目录；verify只独占readonly输入/cache并禁止socket。实际名字/有限timeouts/资源指标在正式包机器预检冻结，不复用旧机器值、不读私钥/env/DSN、不碰agent-guard-a2-pg/verivote/旧进程或容器。物理同host声明局限。写者native STOP、文件全文读回/SHA、资源余留0后才移交。

## 9. 完整验收与进入后段门

test-plan 42个audit planned nodes仅有限责任分配，不证明函数存在/collect/run；每父项由全部原子+native义务UNION闭合。正式实施授权后才实际collect绑定参数；全部race/fault/crash每参数10round，真实barrier/独立connection/backendPID、正负边界/SQLSTATE/所有child异常/native exit/真实PID死亡和新PID恢复。普通纯codec点不无理由十轮。跨proof/token/ancestor/lease expiry必须真实锁等待，正例释放后仍fresh，反例全TX事实回滚，不mock clock或sleep猜顺序。

状态观察包括所有GW原七表/证据/完整祖先四counter/all event nodes/seals/op/lease/outbox/journal/bootstrap/chunks/head/delivery/audit records/checkpoints/DS效果，不只rowcount；独立STAGED可留但不linked。正常默认None成功与故意漏线guard拒绝分别证明；全拒绝不算功能完成。sameproof最多一成功；freshproof同businesskey多RETRY仅一reservation/effect/terminal；撤销先commit阻新公开接受，accept先commit后旧意图恢复合法。

source与fresh非editable wheel、干净不同cwd、所有父子进程import来源、真实SM2/SM3向量/互操作、PG/TLS、README字面CLI、15GW及audit001、原A1/A2/B/历史trigger/oracle/失败等价/预算撤销恢复全继承。禁止选择wrapper计数或局部SDK代完整联调。A31真实login/consent/root/two exchange/四工具HTTPS→run/reconcile→publisher/query→bootstrap descriptor→operator register→pending delivery→reader observedpin；A32该流程→audit管理export→pure offline，均真实CLI进程/source+wheel。最终30goal按实际node/子断言/command/DB观察逐目标映射；A33/A34仍NOT_RUN不能项目ACCEPTED。

阶段门：实际前段ACCEPTED、真实API/SQL/完整矩阵/资源/基线绑定→新独立业务PACKAGE_REVIEW→明确真人本段实施指令→完整自查→native STOP/fullfreeze→fresh Astra/high独立完整复验→必要补正再fresh复验。请求metadata未知保留UNKNOWN及同类有限适配授权具体记录，不放宽安全/资源/验收。A31接受才冻结A32实际依赖；A32接受才冻结A33；容量预检不能代A34。此次仅规划一致性审查，不可宣称四业务段PACKAGE_READY。

## 10. 原ID到合同节与finite cases

下表每项都引用同目录test-plan.json中的同前缀所有finite_case_ref及其audit_nodes/native union；requirements.json相同ID全部assertions原文仍必需，局部节点不能宣称整父项。具体168逐原子到节/节点映射另在audit-findings.json assertion_mapping，可携带到干净检出。

| 原父项 | 合同节 | 计划case范围 |
|---|---|---|
| A31-01 | 2,4,9 | A31-01.* |
| A31-02 | 1,2,3,9 | A31-02.* |
| A31-03 | 3,9 | A31-03.* |
| A31-04 | 3,9 | A31-04.* |
| A31-05 | 3,9 | A31-05.* |
| A31-06 | 3,8,9 | A31-06.* |
| A31-07 | 3,9 | A31-07.* |
| A31-08 | 2,3,5,9 | A31-08.* |
| A31-09 | 4,8,9 | A31-09.* |
| A31-10 | 2,3,4,6,9 | A31-10.* |
| A31-11 | 1,5,9 | A31-11.* |
| A31-12 | 5,9 | A31-12.* |
| A31-13 | 5,9 | A31-13.* |
| A31-14 | 5,9 | A31-14.* |
| A31-15 | 5,8,9 | A31-15.* |
| A31-16 | 5,7,9 | A31-16.* |
| A31-17 | 5,7,9 | A31-17.* |
| A31-18 | 5,6,9 | A31-18.* |
| A31-19 | 5,9 | A31-19.* |
| A31-20 | 5,7,9 | A31-20.* |
| A31-21 | 8,9 | A31-21.* |
| A31-S01 | 2,3,9 | A31-S01.* |
| A32-01 | 6,9 | A32-01.* |
| A32-02 | 6,9 | A32-02.* |
| A32-03 | 1,7,9 | A32-03.* |
| A32-04 | 6,8,9 | A32-04.* |
| A32-05 | 6,7,9 | A32-05.* |
| A32-06 | 6,7,9 | A32-06.* |
| A32-07 | 3,7,9 | A32-07.* |
| A32-08 | 6,8,9 | A32-08.* |
| A32-09 | 5,7,9 | A32-09.* |
| A32-10 | 7,9 | A32-10.* |
| A32-11 | 7,9 | A32-11.* |
| A32-12 | 6,7,9 | A32-12.* |
| A32-13 | 5,7,9 | A32-13.* |
| A32-14 | 7,9 | A32-14.* |
| A32-15 | 5,7,9 | A32-15.* |
| A32-16 | 7,9 | A32-16.* |
| A32-17 | 7,8,9 | A32-17.* |
| A32-18 | 8,9 | A32-18.* |
