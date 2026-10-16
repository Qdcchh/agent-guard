# A3.2 正式任务包 v1

PROPOSED_FOR_PACKAGE_REVIEW / NOT_PACKAGE_READY / NOT_ACCEPTANCE。所有运行 NOT_RUN；请求 Sol/low，有效 metadata UNKNOWN；资源创建/剩余 0。本草稿仅供主控在 A3.1 真正接受后正式重绑定，A3.1现已实际ACCEPTED，当前包待fresh独立包审，不是开工许可。

最新真人授权由本目录authorization.md链接的../A3.1-audit-20261008/user-extend-through-a32-quota-20261011.md控制：完成 A3.1，然后 A3.2 完整接受及资源收尾后停；任何有效额度窗口 remaining<=10% 暂停。现行文档旧 A31-only/A33 连续措辞属已被覆盖的历史事实，不能扩大到 A33/A34/Git。本正式包 worker 仅写 tasks/workflow/runs/A3.2-evidence-20261011/；不改其他目录正式包/state/task/code/tests，不安装、联网、启动容器、测试或 Git。

## 权威与完整性

原行为全文引用 tasks/workflow/runs/A3-planning-20261008/{package.md,audit-contract.md,requirements.json,test-plan.json}；最新规划正式接受 package-review-final.md 只接受规划基线。docs/{oauth-oidc-sm2-mvp,security-model,acceptance}.md、tasks/A2-execution-gateway.md 与完整 A2 acceptance/review-r2 保留原接口、安全和旧回归。工作流 implementation-contract/review-contract 及 setup/codex-astra-sol-v1/workflow-contract 保留独立包审、全自查、真实 STOP、完整 freeze 与 fresh 实施接受门；请求角色按最新真人为 worker Sol/low、新 reviewer Sol/high，UNKNOWN 不伪证有效 metadata。

requirements-v1.json 从原 map 逐字提取完整 18 父项/73 原子（含输入、正/负控、精确 oracle）；node-bindings-v1.json 原样提取 19 计划节点及 3 native，UNION 精确等于73。运行/collect 全 NOT_RUN。继承 A2 119/112/269、A31 全22父项/95原子及21P/30goals、A1/B/旧失败等价不减；累计159父项/151运行标记仅索引，不是实际测试数。无需新增51继承 wrappers。

## 正式采用前主控一次完成

1. 核 A31 fresh 完整 ACCEPTED 原文、全部 writer native STOP、自有资源0、补正 A31-IA-R1-001 独立闭合与当前全候选冻结。不得把当前20组自查、4342/1000或原14数量当独立接受。
2. 核实际 repo/HEAD/branch/index/dirty/untracked/deleted，保全既有成果；逐文件重新 hash 全代码/调用方/SQL/测试/fixtures/锁/文档和继承实际节点。baseline.json 仅当前静态观察，不能成为最终 accepted freeze。
3. 逐项 rebind scope/genesis/bootstrap/chunks/material及RR导出读模型，checkpoint verify/historical ranges/reader fixed observed pin，delivery pending/ACK/remote-ahead，真实 CLI/config/15GW+audit001库存；实质不同接口一次更包审，不猜未来函数。
4. root 落正式版本化包、真实授权引用、精确 allowlist/owner/有界资源规划，fresh Sol/high PACKAGE_REVIEW。已有连续真人授权不重复询问；PACKAGE_READY不代实施接受。实际资源命名/配额与有效原生角色回执在 dispatch 时核证。

## 实施步骤与精确 ownership

ownership-v1.json 是候选逐文件允许集，当前不授写权。S0 a32-shared 唯一 writer：抽取最小 receipt component 语义、AG-TASK-EVIDENCE-2 codec、独立 export auth/config/public fixture；保留 AG-EVIDENCE-1 严格字段/1MiB/组件64KiB/JWS16KiB/UNANCHORED 和历史使用方。冻结 ReceiptComponents/verify_receipt_components 的实际签名、流式 framing/refs/report、auth 输入及离线 public fixture；不可提前 import export。

S0 自查完整相应节点和 v1 旧回归→native STOP/资源0→root 全文读回与 SHA freeze。S1 export 与 verify 在 ownership-v1.json 各独占路径/各独占资源并行：export 消费 frozen auth/codec 与最终 accepted A31；verify 消费 frozen public fixture/codec和外部 trust，不消费 export 半成品。缺正式冻结则停止依赖工作。

S1 export 实现真实 HTTPS POST /v1/evidence/export，严格 {task_id}，独立预登记审计/export role 的可信 tenant/task；不允许业务/AS/holder/downstream 凭据越权。READ ONLY REPEATABLE READ 固定 S/H，完整有界物化私有0700/0600 spool 后结束 DBTX，再下载；失败响应前503、无截断，无业务TX网络/DB写/自动sign/register/recover/任意URL。真实 HTTP spool cleanup/断连/进程死亡保持数据库原件。

S1 verify 实现纯离线 CLI，只读 public trust/bundle/external CP，无 socket/DB/private key/env/model API。全部 FIRST/RETRY/QUERY/TERMINAL/PUBLISH 原件及全部签名、真实 SM2/SM3、历史 registration/role/range、每祖先四计数、外部 bootstrap/genesis/boundary 与独立 latest/minimum 的链接均核，不能信包中keys或current DID。

S1 全 STOP/资源0，root 明确逐路径移交至 sole S2。S2 在 factory 挂真实 evidence_http_app 组合路由，保原 GatewayHttpApp 两路由语义和生命周期；需要 shared main/config 调整仅显式转交后写。完成真实 AS login/consent/PKCE→root→两 exchange→四工具→run/reconcile/publisher/query→audit register/delivery→reader 固定 pin→export→offline 联合，256不同合法SKU宽链正例 source/wheel。同步现行文档与简短 A3.2-report，保历史证据原文。

## 容量与诚实报告

按 audit-contract §6/7：24576 raw chunks、32768 journal、65536 logical objects、16KiB JWS、每帧含LF<=65536、wire<=268435456/400000frames/200000objects/100000records/20000ops；所有b64/JSON/header/footer计入。codec65536合成边界与合法业务可达上界分列；默认bytes/nodes/depth/strings限制不变，不整包json加载，不以假ID拆对象绕限。

10000固定真实合法四工具 workload 的 exact wire/count sizing 是正式义务，含 tree/token/proof/retry/query/terminal/PUBLISH/CP/bootstrap；未执行，不能声称256MiB足够。若超限明确容量拒绝并正式规划固定持久snapshot分页或仅外包上限调整后审包，不删材料/扩大单组件限额；此义务不授权A34 50-client实验。

结果分列 anchored prefix/cutoff/tail、crypto consistency、freshness、history boundary/GAP、每grant四counter；current_auth UNKNOWN，downstream ATTESTED_NOT_INDEPENDENTLY_PROVEN，runtime observation 永远 UNANCHORED_AS_OF_DB_OBSERVATION 即使N=S。保 unsigned非终局runtime改变且重算fold可能不可检测、无latest外部锚未锚tail删除不能伪称检测的正控。无terminal不释放预算，terminal未publish为PENDING，bootstrap不证明启用前真实历史。

## 自查、独立接受与停止

实现 STOP 后实际 collect 把全部19节点/有限维度与73原子/native绑定，不凭函数名/计数关父项。全部兼容并发/故障tuple source+fresh非editable wheel各10轮，独立连接/barrier/backendPID、SQLSTATE/child exit与真SIGKILL新PID；纯codec不无理由十轮。全观察 oracle 按原 before_after_rule：全祖先四counter/op/proof/link/events/nodes/seals/lease/outbox/journal/bootstrap/head/pending/audit/DS，离线input hash前后相同与无网络/DB。

S2 全自查：ruff check/format、完整普通/PG/时限/增强与A1/A2/B/A31旧回归、真实密码向量/OpenSSL、迁移原SQL/checksum/source+noneditablewheel异cwd/父子import provenance/README字面CLI、完整新matrix及原native义务；有限timeout取规划包§5并在实际预检冻结，不能timeout冒充目标freshclock/fence拒绝。失败/中断/补正原件保留，脱敏命令/退出码/XML逐case/DB观察/native owner和双hash完整。

S2 native STOP/资源核验与全候选freeze后 fresh Sol/high IMPLEMENTATION_ACCEPTANCE 覆盖完整当段及继承要求、历史失败和独立变体；必要补正再新freeze/new reviewer。root亲核完整原文与原件、首尾freeze及资源0才能 ACCEPTED。A32接受及收尾后停，不进入A33/A34/Git。本包 worker 在读回/静态完整性/hash/native STOP落盘后停止。


## v1 accepted rebind 与固定安全接口（覆盖前文draft占位）

A3.1正式acceptance.md/review-r2.md及root readback已闭合498全freeze、141/133/269/95、source/wheel各8421/40fresh组、资源0与r1缺陷。baseline.json实际逐源SHA绑定，主控仍核Git控制与完整候选成员；不沿用draft观察hash为最终freeze。本段requirements-v1累积159/151、437断言=269+95+73，原21P和30goal完整原文/归属保留。latest授权以authorization.md正式链接替代旧controller-only路径。上文“正式采用前”步骤1的接受已满足；步骤2/3由本baseline及以下接口落实，真实dispatch/包审/实际collect仍待root。

已接受公共API：audit.contracts JournalScope(gateway_id,tenant_id,task_id,stream_id,epoch)、genesis_digest(scope)、RegistrationDescriptor(scope,genesis_digest,bootstrap_digest,boundary,index_root,object_count,chunk_count,wire_bytes)；CheckpointTrust(kid,role,spki_der,first_sequence,last_sequence)、checkpoint.verify_checkpoint(jws,trust=tuple,expected_scope)、decode_journal_record/decode_history_page/decode_record_page、decode_material_projection(kind,raw)；AuditClient.latest(stream_id), history/records(stream_id,observed_checkpoint_id=...,after_sequence=...)只读固定观察分页。scope/genesis/externaldescriptor必须来自外部可信登记，不从Host/body/包keys推导。journal.stream_tx/require_stream_tx读取已有stream；_snapshot仅privatebootstrap helper，A32 export.py实现自己的只读RR读模型，不调用bootstrap/ensure/append/sign/ack。原材料projection有界262183属于DB浅容器，使用decode_material_projection后解b64为独立context/source/quote/ledger/result<=65536、jws<=16384对象，不把projection作为logical object，不放宽genericcodec。

冻结S0 proposedAPI（实现签名固定，细部内部实现自主）：receipt_semantics.ReceiptComponents(token_jws,proof_jws,ancestor_tokens,request_raw,result_raw,ledger_raw,receipt_jws,quote_raw,context_raw,source_raw)为深不可变bytes/tuple；verify_receipt_components(components,trust:ReceiptTrust)->VerifiedReceipt沿旧组件密码/历史共同窗口/权限收窄/完整path-delta semantics；可选quote/context/source使用None但只对原v1wrapper缺失允许，新task有则必核。不创建另一套密码。task_bundle.iter_frames(binary_stream)严格有界逐帧，encode_object_chunks(kind,id,raw)产canonicalNDJSON；新export.materialize_task_export(connection_factory,scope,external_pin,spool_parent)->immutable spool descriptor（path,size,digest,counts,cutoff,cleanup capability），开READONLY RR、固定完整S/H与snapshot ID/asof，物化完成并关闭TX才返回。失败删除本次spool、回503；headers发送后只允许完整文件下载或断连INCOMPLETE。

HTTP认证冻结：export独立本地注册配置精确{credential_id,credential_sha256,tenant_id,task_ids}条目，task_ids非空有界唯一ASCII IDs；服务Secret用CSPRNG初始化、配置0700/0600，header Authorization: AGExport credential_id:secret，常量时间核hash与可信scope，body只有{task_id}。不是audit现有WRITER/READER注册；旧配置无export条目维持原两路由且export不可用，不能默认共享业务secret。export持read-onlyGW连接及public external-pin文件，无audit writer/AS/holder/downstream私钥。外部reader独立TLS取得latest一次并固定ID分页验previous链，保存公有pin/观察依据；export和offline只消费文件，不为AuditClient要求writer字段而给reader/export writer凭据。

wire frame严格三种：HEADER精确{frame_type,manifest_version,scope,cutoff_sequence,cutoff_head_digest,snapshot_as_of,snapshot_id,history_boundary,bootstrap_digest,object_count,chunk_count,journal_count,operation_count}，manifest_version=AG-TASK-EVIDENCE-2，scope精确{gateway_id,tenant_id,task_id,stream_id,epoch}为上述5字段，计数safe非负，时间UTC整数秒/ID<=512ASCII；OBJECT_CHUNK精确8字段同audit-contract§6；FOOTER精确{frame_type,object_index_root,wire_root,before_footer_frames,before_footer_wire_bytes}。HEADER唯一首帧，FOOTER唯一末帧后EOF；header counts必须匹配完整重组，footer计入总wire。chunk按(kind,id)稳定顺序逐object连续，不跨相同object插片。operation运行观察与typed refs不添wire巨型数组，使用既有typed_snapshot_metadata logical kind、每op一个ID `observation:<operation_id>`，payload精确{metadata_profile,operation_id,status,receipt_status}，metadata_profile=AG-TASK-RUNTIME-OBSERVATION-1，仅快照观察。bootstrap原有typed元数据与raw objects完整保留；FIRST/RETRY/QUERY原record/facts/ref与投影组件通过typed稳定IDs `journal:<seq>:<component>`、原件 `evidence:<ref>:token|proof|request`、op `operation:<id>:ledger|result|quote`关联；bootstrapchunk按原(kind,id)原raw，避免碰撞并验证真实facts摘要，不能猜缺原件。PUBLISH/checkpoint原ASCII JWS作为独立kind；所有既有材料限/ID512保持，过长复合ID用SM3规范固定域ID且保typedref关联，不截断。只有上述确定关系可去重，不用同digest代替kind/身份。opaque/missing历史保原runtime/budget并列GAP，不伪造FIRST或签名。

verify_cli接口冻结：python -m agent_guard.evidence.verify_cli --bundle FILE --trust PUBLIC_TRUST_JSON --external-pin PUBLIC_PIN_JSON --report REPORT_JSON；external-pin允许文件内mode=UNKNOWN且没有CP，不以缺latest冒检测。publictrust精确version/issuer/as_keys/gateway_keys/holder_keys/historical_registrations/catalog/audit_keys/scope/registration，各key由现SPKI/历史RegisteredIdentity codec与role/range核，外部pin含mode(LATEST_OBSERVATION|MINIMUM|UNKNOWN)、checkpoint_jws(nullable)、observed_at(nullable)、scope；不含凭据/privatekeys/URLs。task_verify.verify_task_bundle(binary_stream,external_trust,external_pin)->TaskVerificationReport，不查当前DID或DB、只读输入SHA前后一致。report固定cryptographic_consistency、anchored_prefix、cutoff_sequence、tail、freshness(EXTERNAL_OBSERVATION_PROVIDED|MINIMUM_ONLY|UNKNOWN)、history_boundary、legacy_gap_ids、grant_counters(每grant四计数)、anchored_execution_semantics/derivation、runtime_status_as_of/assurance、current_auth=UNKNOWN、downstream_truth=ATTESTED_NOT_INDEPENDENTLY_PROVEN、limitations与input_sha256。完整离线失败退出2、验证成功且局限如实退出0，不输出rawtoken；runtime assurance始终UNANCHORED_AS_OF_DB_OBSERVATION。

runtime-plan-v1是新owner各mode各writer独占有限规划；资源尚未创建/fullID为空，默认无hostports。具体timeouts见该JSON，20组继承成熟recipe/精确时钟拆500+500/full10round/signonce原TTL/真kill和历史失败保原断言；原92SDK+16SQL仅基线，A32新模块安装成员重新核，不机械固定上限。10000容量真实预检仍NOT_RUN；超限明确拒绝，涉及分页/限额/接口实变需fresh包审，不削材料。包审本身不创建资源/collect/测试。


### 外部输入与typed-ref嵌套schema补齐

所有外部JSON使用strict duplicate/unknown/type拒绝、b64url SPKI decode与已有真实SM2 loader；version固定AG-TASK-TRUST-1。as_keys/gateway_keys/holder_keys为唯一kid→b64urlSPKIDER的对象（各kid<=512ASCII）；historical_registrations为条目数组，每条精确{tenant_id,client_id,did,kid,spki_der,active,role}，active严格bool，role=HOLDER，只将前6字段构造真实RegisteredIdentity并以外部tenant/client/did/kid/SPKI一致性匹配历史source；AS/GW身份由其独立keys及issuer和role map承担，不将holder注册当AS根。audit_keys数组每项精确{kid,role,spki_der,first_sequence,last_sequence}对应CheckpointTrust且role=AUDIT_SIGNER；last_sequence可null。registration精确{genesis_digest,bootstrap_digest,boundary,index_root,object_count,chunk_count,wire_bytes}，scope在trust顶层唯一，按RegistrationDescriptor验证，boundary仅NEW_EMPTY|LEGACY_WITH_GAPS。无自动信任包内同字段。

catalog精确{requests,documents,quotes,deliveries,templates,recipients}，各数组采用现tools.catalog DTO全字段：request{request_id,tenant_id,task_id,status}，document{document_id,request_id,body}，quote{quote_id,quote_version,supplier_id,request_id,lines}且line{sku,quantity,unit_price_fen}，delivery{delivery_id,tenant_id,request_id}，template{template_id,body}，recipient{recipient_id}。只外部可信合成catalog，不把包quote升为权威；历史quote原件验接受事实/成本与授权，当前外部catalog不能替换原quote或要求旧业务当前仍获授权。大catalog采用有界逐条处理，单条现有codec及256SKU上限保持，文件独立总容量受wire上限而不是整catalog默认64KiB加载；初版允许外部catalog列明历史版本，version不可重写。

publicpin精确{mode,checkpoint_jws,observed_at,scope}，mode=UNKNOWN时JWS/观察时间均null；MINIMUM时JWS必真实验签、观察时间允许null；LATEST_OBSERVATION时JWS必真实验签、observed_at必UTC整数秒。这表示外部渠道当时观察的latest而非当前绝对最新；N取CPsequence，无CP为0。CPprevious链所有原JWS仍在包checkpoint对象内完整核至该pin，缺页拒绝；相对minimum不能声明latest。externaltrust/pin文件同时验证scope与登记bootstrap根及boundary。

typed-ref材料关联明确额外metadata逻辑对象（仍typed_snapshot_metadata既有kind，非额外wireframe），profile=AG-TASK-REFS-1，精确{metadata_profile,record_seq,operation_id,evidence_ref,refs}；refs为精确{component,object_kind,object_id}的有界<=16条数组，component固定token|proof|request|context|source|quote|ledger|result|receipt|ancestor_token|checkpoint|runtime，同component ancestor_token最多3且按root→leaf，其他至多1；record_seq真实1..S，op/ref按原record nullable，原record/facts摘要核相应raw。各record需要什么由已接受MATERIAL_FIELDS及真实first/retry/query完整原件决定；BOOTSTRAP外部descriptor+原snapshot完整原件，FIRST/RETRY/QUERY必须含token/proof/request/context/source与适用祖先/quote，TERMINAL含ledger/result与原quote/path，PUBLISH含receipt；缺少legacy原件列GAP，非legacy缺原件拒绝。所有chunk id统一用 `obj:`+SM3(canonical{profile:AG-TASK-OBJECT-ID-1,object_kind,owner_type,owner_id,component,ordinal})，owner_type=bootstrap|journal|evidence|operation|checkpoint|runtime，owner_id为原精确ID/seq文本，ordinal祖先0..2其他0；refs id使用owner_type=journal/component=refs，runtime使用owner_type=runtime/component=runtime。bootstrap原logicalID在对应外部锚定snapshot元数据中完整保留，统一exportID不得改变其raw/index绑定。拒绝同ID不同内容或身份、缺refs、额外无归属对象；不以digest去重不同身份。此段统一ID规则覆盖前文示意ID，不允许worker自行选择另一规则。

TaskVerificationReport字段类型固定：cryptographic_consistency=VERIFIED；anchored_prefix/cutoff_sequence/tail均safe非负整数且tail=S-N；history_boundary为上述boundary；legacy_gap_ids为精确原IDs数组；grant_counters数组每项{grant_id,amount_reserved,amount_settled,calls_reserved,calls_settled}，由bootstrap及全部适用delta重算；anchored_execution_semantics数组每op{operation_id,status,through_sequence,derivation_digest}，status仅ACCEPTED_NONTERMINAL|SUCCEEDED|FAILED|LEGACY_GAP；runtime_status_as_of数组每op{operation_id,status,receipt_status,assurance}，status为已接受实际operation枚举、receipt_status PENDING|READY|null，assurance固定UNANCHORED_AS_OF_DB_OBSERVATION；derivation为固定scope/S/H/登记bootstrap摘要；limitations固定规范枚举HISTORICAL_GAP|NO_LATEST_EXTERNAL_ANCHOR|UNANCHORED_TAIL|UNSIGNED_RUNTIME_OBSERVATION|CURRENT_AUTH_UNKNOWN|DOWNSTREAM_ATTESTATION_ONLY|PRE_BOOTSTRAP_HISTORY_UNPROVEN，按实际条件列出且后三者始终保留；input_sha256精确{bundle,trust,external_pin}小写64hex。输出REPORT_JSON为0600新文件（不覆盖输入），失效输入失败退出2并不给VERIFIED成功报告；成功0同时保诚实局限。
