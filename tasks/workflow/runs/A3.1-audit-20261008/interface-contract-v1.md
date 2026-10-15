# A3.1 共享接口合同 v1

状态：PROPOSED_FOR_PACKAGE_REVIEW；业务 NOT_RUN；有效模型/档位 UNKNOWN。请求 worker Sol/medium、reviewer Sol/high，依本段 authorization.md/current-policy.md，不沿用规划的历史Astra或旧Sol/xhigh。只有独立业务包审可授 PACKAGE_READY；本文件不授实施。源字节、真实现有signature和原子索引见 interface-bindings-v1.json。拟新增API的 implemented_sha=null，不能冒称已存在；S0完整自查、全文读回、原生STOP后由主控冻结实际signature/SQL/fixture SHA，S1才消费。

本合同承接已接受A2及规划 audit-contract.md §1–5/8–9、requirements/test-plan完整原文，补足S0可实施的接口边界。A31 22父项/21运行标记（A31-S01静态项）及全部原子、119/112继承、21P、30goals与历史失败等价义务不删减；JSON保留原子原文及节点联合引用。A3.2导出/离线验证未实施，只预留必要证据字段。

## 1. 真实调用链及兼容入口

真实ledger.accept/accept_checked/accept_bound→_accept_with→_accept_tx；bound既有existing_validator和binding仍为必需keyword，调用性质不变。ExecutionService.accept_invocation的candidate命中、quote失败安全recheck、新quote与事务内竞态均经_accept_checked。EvidenceStore.binding目前是逐调用closure，原事务PermissionSource.revalidate、STAGED原件对照、first/retry immutable link必须保留。VerifiedExecution.accept_response目前外围closure捕获publication/响应；此等待在最终clock之前，不得改成提交后读取。

拟以上三个ledger入口以及_accept_with/_accept_tx均追加keyword `before_create: BeforeCreate|None=None, after_link: AfterLink|None=None`；service.accept_invocation/_accept_from_candidate/_accept_checked同名透传。既有位置参数、return、error和old-callable必需性不改。所有non-None hook写前验callable；单侧hook合法，返回必须None；不connect/commit/network，不替换结构seed，不自行append。默认None仍由ledger承担enabled结构责任。直接accept/checked对已enabled scope需要可信signed材料；普通closure、opaque evidenceRef或STAGED存在不构成真实性证明。未enabled缺stream的旧opaque入口保持A1/A2语义；真实A3 signed路线缺007或必需材料则明确拒绝，禁止成功降级。

默认结构writer位于ledger._accept_tx、service._finalize、query._query_tx、InternalPublisher.publish。publisher才是真实首次READY writer：outbox锁→ReceiptVerifier.read_tx/project/sign/selfverify→PENDING更新READY→PUBLISH→flush；READY重试返回原JWS/signed_at且不加PUBLISH。终局当前仅早期assert_terminal_write_allowed；必须追加后述最后fence，不再次调用旧helper误拒本TX已terminal。

## 2. S0公共DTO与拟signature

全部DTO frozen且只含深不可变tuple/bytes/标量；下列省略type的字段依同名既有定义或本段字段说明，S0实际signature冻结时必须展开，不容无型dict；HTTP不能构造TrustedAcceptBinding/seed/fence。表内signature为拟实施精确消费面，内部helper可拆分但不能改变语义；新runtime不得import S1半成品。

| owner/path | PROPOSED interface | 返回/消费者 |
|---|---|---|
| audit/contracts.py | `JournalScope(gateway_id:str,tenant_id:str,task_id:str,stream_id:str,epoch:int)` | epoch固定1；服务/递送共同使用 |
| 同上 | `ExistingStreamRef(scope:JournalScope,genesis_digest:str,bootstrap_digest:str)` | 不缓存可变head；写时重新锁head |
| 同上 | `LockedAcceptContext(scope_key:tuple[str,str,str],root_grant_id:str,path_ids:tuple[str,...],invocation_context:bytes,source_digest:str|None,tx_id:str)` | 不含conn；source_digest是PermissionSource.digest，另记material摘要 |
| 同上 | `SnapshotObject(kind:str,object_id:str,raw:bytes,digest:str)`；`SnapshotChunk(kind:str,object_id:str,index:int,count:int,total_raw_bytes:int,object_digest:str,raw:bytes)` | chunks由同object切24576；不能以拆假ID容超限object |
| 同上 | `EmptyTaskBootstrapSeed(scope_key,root_grant_id,tx_id,captured_at,origin,schema_lineage,objects,chunks,object_count,chunk_count,wire_bytes,index_root,manifest_bytes)` | captured_at固定UTC文本；origin=FROM_EMPTY_TASK；schema_lineage tuple(namespace,version,rawsha)；本TX局部，不含connection/共享dict |
| 同上 | `BeforeCreate(conn,context:LockedAcceptContext)->None` | CREATED材料prepare，ledger先capture再调用；EXISTING不调用 |
| 同上 | `AfterLink(conn,operation:OperationRow,disposition:AcceptDisposition,baseline:ExistingStreamRef|EmptyTaskBootstrapSeed|None)->None` | proof-link后材料attach；传不可变baseline不能换seed |
| authorization/evidence_store.py | `TrustedAcceptBinding.__call__(conn,operation,disposition)->None`；内部 `compose(callback)->TrustedAcceptBinding` | 仅模块内受信factory构造，descriptor不可变；compose保留同descriptor和原bind能力 |
| audit/contracts.py | `AcceptDescriptor(scope_key,root_id,path_ids,evidence_ref,context_bytes,source_digest,source_material_bytes,token_digest,proof_digest,body_digest)` | 从exact VerifiedInvocationBundle/PermissionSource创建并DB复核，不从closure反射或caller dict生成 |
| audit/journal.py | `capture_empty_task_tx(conn,context)->EmptyTaskBootstrapSeed|ExistingStreamRef|None` | load全task并cap+1，007/可信路线/历史判定；必须insert/reserve之前 |
| 同上 | `ensure_stream_tx(conn,seed:EmptyTaskBootstrapSeed)->ExistingStreamRef` | 验当前xid/scope/root/raw/root/count再晚建stream/snapshot/chunks/BOOTSTRAP；已有stream不可换genesis |
| 同上 | `append_tx(conn,stream:ExistingStreamRef,*,kind:str,operation_id:str|None,evidence_ref:str|None,facts_bytes:bytes)->JournalRecord` | 在真实业务锁/材料完成之后锁head；seq=head+1、不烧号、不自行commit |
| 同上 | `bootstrap_task_tx(conn,*,scope_key:tuple[str,str,str])->RegistrationDescriptor`；`describe_pending_tx(conn,*,scope_key)->RegistrationDescriptor` | 维护模式已停writers/drain和强锁；后者只读public descriptor |
| audit/contracts.py | `JournalRecord(scope,seq,record_id,kind,operation_id,evidence_ref,previous_digest,recorded_at,facts_bytes,raw,digest)` | raw是完整canonical record；digest=SDK SM3(raw)；不将digest塞进raw |
| execution/store.py | `capture_write_fence(conn,*,operation_id,owner_token,fencing_version)->WriteFence` | 锁operation/lease，复用原早期四条件，返回prestatus/真实expiry/本TX ID |
| 同上 | `assert_write_fence_current(conn,fence:WriteFence,*,expected_terminal:str)->None` | flush后只重读已锁rows→最终DBclock；合法本TXterminal可通过，无续租 |
| audit/contracts.py | `WriteFence(operation_id,owner_token,fencing_version,pre_status,expires_at,tx_id)` | expiry固定UTC精确文本；不序列化为public凭据 |
| 同上 | `encode_append_batch(stream_id:str,entries:tuple[bytes,...])->AppendBatch`；`decode_append_batch(raw:bytes)->AppendBatch` | strict exactbody及batch_id；service/delivery共同消费 |
| 同上 | `AppendBatch(stream_id,entries,exact_body,batch_id,start_sequence,end_sequence,end_digest)` | body只有batch_profile/stream_id/entries；其余均从entries派生 |
| 同上 | `decode_checkpoint_claims(raw:bytes)->CheckpointClaims` | 仅codec/schema，不自行认证或信任包内key |
| 同上 | `CheckpointTrust(kid,role,spki_der,first_sequence,last_sequence)`；`ObservedCheckpoint(jws,claims,jws_digest,observed_at)` | role=AUDIT_SIGNER；key range由外部operator登记，last nullable开放上界 |
| 同上 | `RegistrationDescriptor(scope,genesis_digest,bootstrap_digest,boundary,index_root,object_count,chunk_count,wire_bytes)` | boundary NEW_EMPTY/LEGACY_WITH_GAPS；public本地提交后operator登记 |
| 同上 | `PendingBatch(stream_id,batch_id,exact_body,start_sequence,end_sequence,end_digest,base_checkpoint_digest)`；`DeliveryCursor(stream_id,ack_sequence,ack_head_digest,ack_checkpoint_digest,pending_batch_id)` | 不含私钥/DSN/网络对象；ACK条件匹配exact pending |
| 同上 | `HistoryPage(stream_id,observed_checkpoint_id,observed_sequence,checkpoints:tuple[str,...],next_after_sequence:int|None)` | 固定观察边界，不以page length判断完整 |

不新增AS验签/权限或SM算法实现；复用PermissionSnapshotProvider、原SM3/JWS、ledger_changes专用signed-delta codec。S0公共fixture提供真实generated签名、bytes和负例参数；service/delivery各使用自有transport/resource，S1不读取同阶段peer实现。

## 3. 严格record/facts字节

profile AG-AUDIT-JOURNAL-1。raw字段exact：`journal_profile,stream_id,gateway_id,tenant_id,task_id,epoch,seq,record_id,kind,operation_id,evidence_ref,previous_digest,recorded_at,facts`。seq整数1..MAX_SAFE；epoch=1；recorded_at为非负Unix时刻对应的UTC微秒精确文本；ID printable ASCII 1..512、record_id<=2048，UUID持久随机，gateway_id由可信固定INVOKE_ENDPOINT规范origin推导，不能Host/Forwarded/body/环境跳过值。digest canonical未填充b64url解码必须32bytes。拒重复/未知/float/bool-as-int/negative/overflow/noncanonical，默认65536bytes/4096nodes/depth64/总字符串65536保持，单record<=32768。timestamp文本统一`YYYY-MM-DDTHH:MM:SS.ffffffZ`并与DB原timestamp精确对照，不把微秒丢成epoch整数。

genesis=SM3(canonical{journal_profile,gateway_id,tenant_id,task_id,stream_id,epoch})；首prev=genesis。record_id固定kind冒号绑定事件：BOOTSTRAP:<stream>、FIRST:<op>、RETRY:<evidenceRef>、QUERY:<evidenceRef>、TERMINAL:<op>、PUBLISH:<receiptID>。业务kind operation非null；BOOTSTRAP两ref null；FIRST/RETRY/QUERY evidence非null；TERMINAL/PUBLISH evidence_ref=原first ref，可为legacy null并明确gap。

每kind facts keys **exact**如下；所有摘要来自注明的真实原字节，不重新生成替代。nullable仅明确标记，不能省key；所有path按root→leaf且1..3，非负counter/delta以专用codec摘要存。

| kind | exact facts | 原件及关系 |
|---|---|---|
| BOOTSTRAP | `boundary,root_grant_id,snapshot_as_of,schema_lineage_digest,index_root,manifest_digest,object_count,chunk_count,wire_bytes` | seq1，小manifest<=32768；schema_lineage_digest取canonical qualified inventory；snapshot含全task原事实能力/GAP，不编造旧FIRST |
| FIRST | `root_grant_id,grant_id,path_ids,intent_digest,token_digest,proof_digest,body_digest,context_digest,source_digest,source_material_digest,reserve_digest,quote_digest,amount_fen,calls,currency,introduced_grants` | token/proof ASCII、request/context/source exact raw、canonical RESERVE全nodes；quote nullable，保原zero price；introduced_grants为严格下述tuple，无后减cost推零 |
| RETRY | `first_evidence_ref,intent_digest,token_digest,proof_digest,body_digest,context_digest,source_digest,source_material_digest,response_kind,response_digest,status,receipt_status,receipt_jws_digest` | 当次exactsource/material/proof；原first不可替；response_digest是同TX实际返回canonical响应，receipt_jws_digest nullable |
| QUERY | `first_evidence_ref,token_digest,proof_digest,body_digest,context_digest,source_digest,source_material_digest,response_digest,status,receipt_status,result_digest,receipt_jws_digest` | result/JWS nullable，proof purpose=result-read/QUERY_ENDPOINT；当前query raw与原op首次材料分开，不能把STAGED当成功 |
| TERMINAL | `first_evidence_ref,status,action,result_digest,ledger_digest,pending_receipt_digest,receipt_id,owner_token,fencing_version,lease_expires_at,path_ids` | full原pending签名材料摘要和canonical完整ledger_changes，结果exact bytes；action SETTLE/RELEASE对应SUCCEEDED/FAILED；最终fence同TX核 |
| PUBLISH | `receipt_id,receipt_jws_digest,signed_at` | exact ASCII persisted JWS、原receiptID与精确DB signed_at；首次READY同TX、重试不重签 |

introduced_grants exact element `{grant_id,parent_id,root_id,depth,holder_client_id,holder_kid,grant_token_digest,source_material_digest,amount_reserved,amount_settled,calls_reserved,calls_settled}`，四counter全0。仅bootstrap未列的真实新grant且预留前无任何accepted历史/旧FIRST引用、存在已验真实AS签名链及immutable DB绑定可列；未知来源/非零/gap节点不能纳入零起点。祖先token/raw source另存原evidence，FIRST摘要不能替代以后重验原件。

RETRY response_kind严格ACCEPT_RESULT或ACCEPT_RESPONSE。普通accept原return是AcceptResult而非HTTPdict：S0定义唯一既有AcceptResult canonical投影（operation_id,grant_id,root_id,status,disposition,cost,accepted_at）供response_digest；accept_response wrapper显式记录实际3字段响应覆盖该投影，并以内部descriptor能力标记response形态，不加HTTP字段。QUERY保现5字段response，seq不塞响应以免循环。必须冻结二种RETRY响应形态的exact projection fixture及digest算法，不允许泛用str(dataclass)。

## 4. 同TX次序、seed与维护边界

CREATED：load path→principals→task→root至leaf grants→初始clock/freshness→proof登记→business key miss→预算→ledger.capture(全task，insert/reserve前)→BeforeCreate材料→operation/全祖先reservation/RESERVE→原binding/PermissionSource复核→proof-link全部等待→AfterLink材料→核真实事实/响应→晚ensure_stream(seed)+BOOTSTRAP1/FIRST2（已有stream仅FIRST）→flush→已锁principal/path/必要PermissionSource复核→最后DBclock→纯内存return/commit。实际TX竞态行优先于candidate前读；EXISTING只RETRY，无capture空seed/新报价/新reservation。每deadlock/serialization重试重新建立seed和wrapper响应，不跨TX复用。

capture在task锁下完整枚举task grants（含offpath），四counter及accepted operations/events/nodes/seals、linked proofs/first-retry evidence、lease/outbox/review/sidecar历史。尚未link的本次proof与孤立STAGED不冒accepted历史。全零、无上述历史才origin=FROM_EMPTY_TASK；任意offpath非零或旧历史整TX拒自动启用，即使新businesskey miss。cap+1探测不能截断。真实成本c/calls1：snapshot全grant零且无本次op/event；FIRST后全祖先仅增加c/1一次。seed schema/currentxid/scope/root/capturetime/raw/chunks/roots/counts由same-TX DB捕获，hook不能伪造。

seed/snapshot同规划容量：object kind token/proof/ancestor_token/receipt/checkpoint<=16384，journal<=32768，request/result/ledger/quote/context/source/raw_authorization_snapshot/typed_snapshot_metadata<=65536；chunks raw<=24576（65536为24576/24576/16384），全snapshot wire<=268435456、frames<=400000、objects<=200000、operations<=20000、journal<=100000；小manifest<=32768。typed_snapshot_metadata不能把全task塞一巨JSON。index fold使用AG-BOOTSTRAP-INDEX-1按(kind,id)确定顺序，折每object的kind/id/rawlength/digest/chunkcount；wire按实际b64/metadata/canonical/LF计数，固定profile/scope起始，不无界digest list。超限整TX无stream/chunks/reserve；本轮不降低这些限额也不做A32 framing/export。

旧task维护：停旧GW/worker/publisher/AS writer→drain在途→独占维护协调→task→全部grants→operations→leases→outboxes→head；真实schema/asof/nonzero counter/status/material能力全snapshot，seq1 BOOTSTRAP。opaque/short/missingraw按原值GAP，不修预算或伪造启用前顺序。public publisher若无stream不作outbox→task bootstrap；需要A3的旧task先维护，否则failclosed。未来AS child exchange/provisioning已持task锁；_claim/_finalize/_mark_unknown真实持task，publisher/quarantine不误称持task；维护停止这两类在途writer。S0只读核锁链，不无必要扩大AS写权。

公开锁序 principals→task→root至leaf grants→op→lease/outbox→head；internal terminal从task起；publisher outbox→已有head。head后不得首次取业务锁或网络，相关约束所需业务锁提前完成。QUERY在全部原件/source/proof-link/receipt projection/response capacity后append→flush→已锁复核→最后clock。终局capture_write_fence早核后暂写四counter/event/PENDING/status→TERMINAL→flush→assert_write_fence_current(expected_terminal)→最后clock。helper必须核本TX/原owner/version/未改expiry/expected状态，允许本TXterminal；不得续租洗白。逾期全TX回滚counter/event/outbox/status/journal/head，原已下游效果仍原意图恢复，不能RELEASE或再执行业务。

## 5. execution007拟schema与数据库防漏线

现14份SQL/raw/checksum/registry/applied_at/_V2_COMPLETION_FLOOR全部immutable。007只新增表/约束/trigger及必要guard，不重写旧行、不修改旧SQL。以下SQL列为S0必须实现/冻结的最小关系，全部表不使用nextval；text IDs/digests按§3，seq/count bigint有限safeint，bytes为bytea，时间timestamptz，created_xid text由数据库trigger写pg_current_xact_id()，不信传入值。

| GW table | 列、键/FK、变更权限 |
|---|---|
| ag_audit_streams | stream_id PK；gateway_id,tenant_id,task_id,epoch=1,genesis_digest,bootstrap_digest,enabled_at,created_xid immutable；UNIQUE(gateway,tenant,task)；FK(tenant,task)→ag_tasks；head_seq/head_digest仅合法append从old+1更新且同TX匹配record（初始0/genesis） |
| ag_audit_records | PK(stream_id,seq)，UNIQUE(stream_id,record_id)；kind,operation_id nullable FK→operations,evidence_ref nullable FK→verified_evidence,previous_digest,digest,raw,recorded_at,created_xid；FK stream；操作scope必须与stream一致；raw/facts持久原字节；额外material_binding_bytes为有界canonical对象原件关联投影（不是journal wire字段），SQL比较其中context/source/quote/ledger/result/JWS原bytes与对应DB列；SDK核投影各摘要与facts一致，INSERT后不可UPDATE/DELETE；kind业务唯一关系由partial unique FIRST/TERMINAL op、PUBLISH receipt、RETRY/QUERY ref约束 |
| ag_audit_bootstrap | stream_id PK/FK；boundary,snapshot_as_of,root_grant_id,index_root,manifest_digest,manifest_bytes,schema_lineage_bytes,object_count,chunk_count,wire_bytes,created_xid；immutable，与BOOTSTRAP seq1 exact绑定 |
| ag_audit_bootstrap_chunks | PK(stream_id,object_kind,object_id,chunk_index)，FK bootstrap；chunk_count,total_raw_bytes,object_digest,raw,created_xid；immutable，连续chunks exactlength/full对象摘要由SDK结构writer核，DB核计数/长度/同xid/manifest关系 |
| ag_audit_delivery | stream_id PK/FK；ack_sequence,ack_head_digest,ack_checkpoint_digest(nullable),pending_batch_id(nullable),registration_state；ACK单调条件更新，pending FK(stream,batch_id)→delivery_batches DEFERRABLE；初始0/genesis/null；不得reset/re-epoch |
| ag_audit_delivery_batches | PK(stream_id,batch_id)，FK stream；exact_body,start_sequence,end_sequence,end_digest,base_checkpoint_digest(nullable),created_at immutable；checkpoint_jws/ack_at初始null→一次绑定不可替；batch重试复用exact原bytes；start/end records FK及scope核 |

不额外新增辅助生命周期kind或AS全审计。deferred CONSTRAINT triggers均本creating-xid/实际scope/关系核双向coverage：enabled当TX operation+RESERVE创建要求FIRST、operation_evidence first/retry要求对应记录、proof purpose=result-read的成功link要求QUERY、terminal event/status/PENDING要求TERMINAL、首次PENDING→READY要求PUBLISH；BOOTSTRAP必须stream初建seq1且原snapshot匹配。反向records不能孤立：本TX实际事件/链接必须存在，first/token/proof/intent/quote/完整path/node/cost/status/result/outbox/JWS等可由DB行精确对照。QUERY从proof/link+ag_verified_evidence context定位op，不要求不存在的kind=query operation_evidence。

DB创建xid由新trigger局部见证，不能仅读客户端facts.created_xid；对旧不可变行用于retry不假称其creating-xid为本TX。本TX旧binary漏journal在enabled scope拒绝，未enabled历史不rewrite。直接SQL插record无真实事件/错误facts、改删记录/snapshot/chunks/exactbody、head跳号、晚补过去记录均23514；FK错误23503；真实SQLSTATE全留。material_binding_bytes的每logical物体遵守§4上界，不做无界全raw合包；可逐kind只保存数据库不能从已有digest列独立核对的必需原bytes，S0冻结exact projection。SQL guard不冒称内置SM3/RFC8785可验签：SDK负责canonical、密码/完整snapshot摘要/response重算；DB负责实际列/原bytes/关联/transaction/coverage，在runtime role权限下防遗漏，任意DB管理员失陷为既有局限。S0必须逐kind冻结实际SQL可核字段表及正常默认None材料hooks装配成功、故意漏线拒绝两类正负证据，不以全拒绝当完工。

007依赖execution006+authorization010，GW qualified库存15；audit001独立DB/registry不算第16。migrate._discover默认standalone001–006固定识别/校验；直接依赖型007/custom缺文件/checksum/TOCTOU先DDL前拒。lineage当前_entries只自动前版本依赖和空库for(common,execution)须改为显式007双依赖；空库先原001–006 legacy registry/applied_at，auth010后007。旧upgrade/applied兼容返回按真实新增版本保持；历史14 completion floor不能改成15或抹掉旧失败。pyproject source/wheel共享15GW+独立audit001 inventory。现lineage明确PG16门；本段选择PG16支持、PG14明确拒绝，不未经测试宣称兼容。

isolation.reset_state目前按bundle有无选择RESET_TABLES，再owned qualified TRUNCATE；新007存在分支显式加入上六表及现ag_event_seals，只assert_owned成立的namespace、migration owner执行；旧未007分支保持。runtime无DDL/TRUNCATE，不改guard、不DISABLE/session_replication_role/no-journal skip，不清ag_%/marker/provenance/auditDB。若实现需conftest或其他旧fixture修改，先精确扩ownership独立审包。

## 6. audit001、checkpoint、reader与S1冻结消费

独立audit DB仅 `ag_audit_schema_migrations(version,filename,raw_checksum,applied_at)` 和下列audit域表；拒启动指向GW/DS或缺独立role/domain marker。operator CLI init/register/check只本机，注册固定scope/stream/genesis/bootstrap/boundary和writer/reader，不能writer自登记或替换同scope。无公共register/sign HTTP。私有配置0700/0600，GW publicHTTP不加载audit signer key，AS/holder/GW/downstream凭据不能充audit。

| audit表 | 最小字段/关系 |
|---|---|
| ag_checkpoint_streams | stream_id PK；scope/epoch/genesis/bootstrap/boundary/public descriptor immutable+unique scope；latest_sequence,latest_digest,latest_checkpoint_id条件前进，无reset |
| ag_checkpoint_records | PK(stream_id,seq) FK stream；raw,digest,previous_digest,record_id immutable；UNIQUE(stream,record_id) |
| ag_checkpoint_batches | PK(stream_id,batch_id) FK stream；exact_body,start_sequence,end_sequence,end_digest,checkpoint_id immutable；相同batch先查原bytes再返回，不重签 |
| ag_checkpoints | checkpoint_id PK，stream_id FK，sequence/head_digest/previous_checkpoint_digest/issued_at/kid/jws/jws_digest immutable；UNIQUE(stream,sequence)；batch FK checkpoint，stream latest FK checkpoint DEFERRABLE |
| ag_audit_principals | credential_id PK，role WRITER/READER，credential verifier与scope绑定；独立operator配置，无public返回secret |
| ag_audit_checkpoint_keys | kid PK，role=AUDIT_SIGNER,spki_der,first_sequence,last_sequence；外部公钥信任版本受operator管理，历史JWS不重写 |

公共 `POST /v1/audit/append` strict canonical `{batch_profile:'AG-AUDIT-BATCH-1',stream_id,entries:[b64url(raw)]}`；entries1..64，实际body<=65536；每raw<=32768并用§3 fixed-kind schema核canonical/SM3/scope/seq/prev，整批原子。batch_id=SM3(exact_body)而非另加batch_id请求字段。stream row锁→先batch查重（原bytes相同返回原JWS）→新批start=latest+1/prev=head且全条连续→records→真实SM2 sign/selfverify→batch/checkpoint/head→commit→`{checkpoint_jws}`响应。oldrange换批409 RECONCILE_REQUIRED；同seq不同raw/gap/fork拒；双进程/随机SM2不能同事实重签。

checkpoint typ=ag-checkpoint+jwt，仅显式追加crypto/sm.py JWS_TYPES；alg/USERID/raw64签名/原JWS域不变。claims keys exact `profile,checkpoint_version,checkpoint_id,stream_id,gateway_id,tenant_id,task_id,epoch,sequence,head_digest,previous_checkpoint_digest,issued_at,kid`，profile GM-MVP-1/version AG-CHECKPOINT-1，payload kid=protected kid，sequence>=1，previous为前持久原JWS ASCII SM3或首null，首CP完整连续前缀从genesis/BOOTSTRAP核。ASCII JWS<=16384。S1 checkpoint.py拟 `sign_checkpoint(claims,*,private_key,key_id)->str`、`verify_checkpoint(jws,*,trust:tuple[CheckpointTrust,...],expected_scope:JournalScope)->ObservedCheckpoint`；只信外部audit公钥/role/range，拒receipt/at/pop/未知kid/wrongrole/SPKI/badsig/重复未知字段。S0只冻结schema/可信fixtures，signer实现由S1。

reader固定HTTPS POST `/v1/audit/latest` strict `{stream_id}`返回`{checkpoint_jws}`（无CP为明确NO_CHECKPOINT）；`/v1/audit/history` strict `{stream_id,observed_checkpoint_id,after_sequence}`返回HistoryPage字段canonical JSON。observed_checkpoint_id是此次latest独立观察pin，服务固定其stream/seq边界；每页最多64候选且实际<=65536最大合法前缀，next_after_sequence仅完整页末seq或null，缺页/断previous不能算complete。latest长停写仍原JWS/time；rotation可信历史sequence ranges外部提供，不信history附带key。writer/reader分role、固定URL/CA/hostname，禁止HTTP/redirect/verify=False/用户任意URL；错误脱敏。

## 7. delivery exact pending、ACK与remote ahead

S1 client.py拟 `AuditClient.append(batch:AppendBatch)->str`、`latest(stream_id)->str|None`、`history(stream_id,*,observed_checkpoint_id,after_sequence)->HistoryPage`；client仅transport不信response，delivery独立verify。delivery.py拟 `prepare_pending_tx(conn,stream_id)->PendingBatch|None`、`ack_pending_tx(conn,pending,checkpoint:ObservedCheckpoint)->bool`、`reconcile_remote_ahead(local_records,observed,history_pages,trust)->VerifiedRemotePrefix`；后一函数纯校验，返回确切sequence/head/JWS digest，不能只返回boolean。`deliver_once(stream_id)->DeliveryOutcome`界定REGISTRATION_REQUIRED/NO_PENDING/ACKED/RECONCILE_REQUIRED/UNAVAILABLE，不把网络失败当成功。

短TX只锁delivery row，不取task/head：已有pending复用exactbytes；否则稳定读取连续records，最多64逐候选encode_append_batch选实际b64+metadata+JSON<=65536最大prefix，不rawsum、不跳条，single不装明拒→persist immutable batch/exactbody/digest/start/end/baseCP并设pending→commit释放所有锁→TLS→验独立scope/seq/end_digest/previousCP→新短TX条件单调ACK。remote失败保pending/预算不变，新journal增长和SIGKILL重启不改变body/边界。双sender共用同pending，晚旧ACK只可幂等已同CP状态，不能退cursor或清新batch；只clear匹配stream/batch/body/start/end。

remoteahead先固定reader latest JWS（独立验证role/scope/range），history完整previous原JWS链，再对本地每seq/raw/digest连续前缀核到observed sequence。仅history JWS不含全部journal，不能证明中间本地record。故最小新增reader `/v1/audit/records`：strict `{stream_id,observed_checkpoint_id,after_sequence}` 返回 `{stream_id,observed_checkpoint_id,observed_sequence,entries:[b64url(raw)],next_after_sequence}`；观察边界固定，最多64候选、实际canonical<=65536最大合法prefix，单raw<=32768，缺条/错误游标拒绝，不能截断raw。S0冻结 `RecordPage(stream_id,observed_checkpoint_id,observed_sequence,entries:tuple[bytes,...],next_after_sequence:int|None)` 及 `AuditClient.records(stream_id,*,observed_checkpoint_id,after_sequence)->RecordPage`；history仍tuple原JWS，不在一页附大batch体。remoteahead必须联合history+records，逐seq/prev/SM3/scope核本地真实前缀，各CP边界head与record对齐，缺页/badsig/fork保持pending不ACK。该新增API为真实对账必需，纳入本正式包独立审查；不另授文件写权。S1不得简化成latest seq跳cursor。

audit/GW真备份回退对外部保留CP核lowerseq/sameseqwronghead，拒startup/append及未来export，不能新stream/epoch/register覆盖。无外部最新观察仅MINIMUM_ONLY/UNKNOWN，不伪称检测共同回滚。同机仅逻辑隔离，key/anchor共同失陷局限保留。每坏stream有界timeout和轮转，正常task不能饥饿；网络始终在DB锁外。

## 8. owner、S0 STOP冻结与完整门

S0精确文件仍规划§8：migrations/007_audit_journal.sql、migrations/audit/001_checkpoint_store.sql、pyproject.toml；audit/{__init__,bootstrap_cli,contracts,journal}.py；authorization/evidence_store.py、crypto/sm.py、execution/{query,service,store,verified,receipt_publication}.py、ledger/{lineage,migrate,service}.py；tests/fixtures/{a31_common,isolation}.py；tests/integration/test_audit_{atomicity,clock,fencing,lock_order,upgrade}.py、test_lineage_migrations.py、test_migrations.py、test_a2_migrations.py；tests/unit/test_audit_journal.py。真实firstREADY、末fence、JWS_TYPES三个关键路径已列，不需要自行扩scope。新增reader records能力在既有S1 audit/{http_app,store,client}.py与测试allowlist内，不引入新文件；正式包必须将此消费接口及atoms绑定独立审查。

S0 STOP移交须实际源/SQL rawsha/signature、15GW+audit001 inventory、全部DTO strict字段/byte fixtures、各kind事实SQL核表、reset精确closure、trusted wrapper/None/各分支传递证明、默认装配正例/漏线拒绝、全task预留前seed/维护/GAP/introduced-zero、所有晚等待最后clock/fence实际source/wheel用例。S1 service消费冻结schema/fixtures且只其owner；delivery自有transport harness，不import peer半成品；S2唯一integrator待两S1全STOP后真实TLS联合，读回/全freeze/资源余留0→fresh Sol/high完整独立实施复验。所有竞争/故障/真实SIGKILL参数十轮，独立connections/backendPID/barriers/所有child exceptions/native exit/真实不同新PID，同持久DB；纯codec无理由不十轮。全GW/证据/祖先四counter/events/nodes/seals/lease/outbox/journal/bootstrap/chunks/head/delivery/audit/DS逐行观察，不只响应或总数。

本建包worker只写此合同/JSON与自有ignored证据；无test/collect/PG/TLS/安装/容器/Git/业务资源。本轮不能授业务PACKAGE_READY。原规划的A32字段/未来锚定与未锚tail/current-auth/downstream真实效果局限不删，但不编造A32 API已实现。后续任何signature/schema/锁序/owner变更先补包独立审查后再freeze。
