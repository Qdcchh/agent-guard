# A2 任务交接：可信工具执行、恢复与真实验权网关

状态：待实施。本文件是 A2 实施要求，不是已有实现。沿用 GM-MVP-1 和已验收 A1，不重新设计 OAuth 或密码协议。

## 0. 开工与授权

1. 工作目录：`/Users/qdcc/code/密码技术竞赛/agent-guard`。先读 AGENT.md、本文、A2-report.md、A1-review-r4.md，再检查 `git status --short --branch`、`git diff`、未跟踪文件和 `git log --oneline -5`。
2. 已知 main 基线：`b120c7cf5ec0eafb18305d1207c36dd11655b324`（A1 已合并）；PR #2 和合并后 Python3.11 CI 通过。开工时核对实际状态；不要从旧 feat/a1-ledger 开工，不 reset/clean/rebase/强推覆盖工作。
3. 本任务两份 Markdown 是预先准备的未提交输入，必须保留。若 main 有更新先报告依赖差异；确认安全后可创建本地 `feat/a2-execution-gateway`。不自动拉入/合并 B 的分支，不覆盖 B 模块。
4. 本次只授权编辑、测试和留痕：**不 commit/push/创建 PR/合并/改分支保护**。先由主代理复核，再由用户授权集成。
5. 使用独立真实 PostgreSQL16 测试实例/所有权命名空间；不要清空已有 `agent-guard-test-pg`，不要停止无关容器。只清理自己创建的资源。不打印密码、DSN、token、私钥或敏感业务数据。
6. 先更新报告的基线、依赖状态、分段计划和至多10条技术决定，再编码。技术问题无法在两次尝试内解释，给最小复现并请求指导，不无限重试或降级安全。

## 1. 阅读入口与本轮范围

| 文件 | 必读内容 |
| --- | --- |
| docs/security-model.md | 第2—9节：锁序、全祖先账本、状态机、下游幂等、恢复及回执 |
| docs/oauth-oidc-sm2-mvp.md | 8.1/8.3/8.5、9.4—9.6、10：严格参数、AGPoP、查询、回执、SDK |
| docs/acceptance.md | M4—M9/M12/M13、SEC-04—07、CON、REC、ENG；不要改成全部已通过 |
| src/agent_guard/contracts/ledger.py | 实际 A1 类型，不仅看目标接口示意 |
| ledger/service.py、store.py、validation.py、provisioning.py | 已有接受、锁序、动态复核、证据与事件 |
| migrations/001—003、tests/fixtures、tests/integration | 已应用 checksum、操作不可变触发器、隔离和并发测试 |

完整 A2：可信资源/报价解析，四工具模拟下游，执行/结算/释放/UNKNOWN恢复，持久化回执outbox，真实 B 验证器接入的 HTTP 调用/结果查询，真实 SM2 回执签名。

不做：AS/OP/OAuth/OIDC端点、令牌签发或委托策略、复制密码实现、重新实现 RFC8785/SM3、通用 DID 解析、RP/模型/三代理编排、前端、真实支付、独立审计锚定、完整证据导出与压测（后者属 A3）。只实现必要模块，不铺空目录或占位成功服务。

## 2. 必须分段推进，不能把缺 B 说成全部完成

### A2.1：独立于 B 的执行/恢复核心

先实现真实 PostgreSQL 操作生命周期、可信合成资源/报价服务、四工具模拟下游、租约/恢复和待签回执 outbox。使用 A1 可信对象和仅限 tests 的密码替身做分层测试，不声称真实验签或摘要。此段无需等待 B，可独立交付 `CORE_READY_FOR_REVIEW`；完整 A2 状态仍为 PARTIAL。

### A2.2：接 B 的真实 SDK 与 HTTP

开工核对 B 的实际代码/版本/接口。准备任务时本地所知 `origin/feature/fjr-B-character` 仍指向旧骨架，**不是已交付 SDK**；远程可能随后更新，应重新核对，而非直接认定永远缺依赖。

所需 B 交付：严格解析与规范编码、真实 SM2/SM3、invoke/result-read 验证器、授权约束可信快照/路径包含校验、证据暂存接口、回执签名/验签与测试向量。第10节接口只是目标，必须以双方确认的真实代码为准。

**明确现有接口缺口：** A1 VerifiedInvocation 仅含规范参数等账本字段，不含 scope/ag_constraints 权限快照；A1 验证也只接受 purpose=invoke。结果查询需专用可信契约和验证路径，不要伪造 tool/idempotency 字段或放宽 accept 的 purpose。对接方案须写报告，确认字段归属后实施最小兼容扩展；不暗改共享类型或另造第二套规范编码。

现有 ag_grants 也未存 scope/ag_constraints。检查点一必须确认B提供的不可变权限快照/注册状态存储归属及其与grant/token的绑定；缺失或不匹配时失败关闭。不能拿请求自报约束代替，也不能因有真实签名就跳过祖先权限包含校验。

B 暂缺时可写接口适配设计和使用依赖注入的路由分层测试，但**实际服务装配缺真实验证器须拒绝启动**；不接受任意已验权JSON，不读取环境变量开启假验权，不动态导入 tests 替身，也不以无签名测试宣称 HTTP 安全验收通过。

### A2.3：回执签名与联合交付

使用 B CryptoProvider、规范编码和真实网关 SM2 key。key 从显式初始化/配置加载，与AS、代理和下游凭据分离；不得提交真实私钥。完成真实签验与类型隔离后才生成 receipt_jws。B 缺失时 outbox 保留 PENDING，绝不以占位签名标 READY。

## 3. 文件与技术边界

- 可新增 `execution/`、`tools/`、`gateway/` 等必要模块及 A2 测试；复用同步 psycopg 和 A1。HTTP 可选一种轻量框架（建议 FastAPI），先写依赖目的、许可、版本与约束，再加入必要锁定；同步DB路径不要在async事件循环直接阻塞。
- SQL 从 **004** 起新增，001/002/003 禁改；迁移发现/期望版本继续动态推导。
- ledger/及共享 contracts 修改只限生命周期、授权查询或可信成本接入所需；保留 accept API兼容、拒绝逻辑、根约束及现有测试。抽取最小共享校验可以，禁止为A2整体重写A1。
- B 的密码/授权/身份模块归B；未确认不修改。接口不匹配记录为依赖，不复制实现兜底。
- 可以更新 README 实际完成边界、pyproject/约束、配置占位、CI、compose测试入口及 tasks。不上传父目录内部文件和本地PDF/artifacts。

## 4. 可信参数、报价与幂等

1. 四工具严格沿用方案9.4的完整标识：`procurement.request.read`、`procurement.document.read`、`procurement.order.create`、`notification.template.send`；拒绝缩写/别名/未知工具并补负例，版本只能字符串 `1`。精确验证字段集合、类型、长度/数量/请求大小上限；拒绝重复JSON键、NaN/Infinity、bool数量、负数/浮点/超界金额、未知字段及重复SKU。
2. 有效签名不代表允许资源。检查受信 scope/ag_constraints、完整链权限收窄，以及申请归属租户/任务、文档归属申请、报价版本/供应商/SKU关联、批准收货对象、通知模板/接收方和可访问操作。数组缺失拒绝，空集合表示禁止；每SKU数量为正整数且不超 max_quantity。
3. 可信合成资源来自服务初始化/存储，不由请求上传权威成本。订单总额按固定版本报价和数量安全计算，CNY整数分≤2^53−1；只读/通知金额0但每新操作calls=1。不开放任意URL/路径/文本通知/脚本。
4. 首次接受存完整可信报价快照（版本、供应商、SKU/数量/单价/总额等）且不可变。EXISTING用原成本/快照，不因当前报价变化/删除导致合法重试重新报价或失败。
5. 新操作可信成本必须取自已验证资源；已有操作查找不绕当前静态/动态权限和proof防重放。不能仅凭业务键提前返回成功；同键改变grant/holder/规范参数仍冲突。如需 A1 延迟成本解析接口，报告接口改变理由与兼容回归。
6. 模拟下游使用**独立数据库/独立连接和事务域**，可同一PG实例，不能复用网关连接或单事务。稳定下游键为网关 operation_id；效果/意图/结果/终局拒绝记录有DB唯一约束并在下游事务内原子保存。
7. 下游执行和查询都验证独立网关服务凭据（例如独立注入的服务secret，非代理凭据），不得对任意代理开放。认证失败不执行/不泄露结果；测试无/错凭据与直接访问拒绝。对网络调用不关闭TLS校验；不能把无网络分层测试声称真实TLS部署已验收。
8. 同键同意图返回同一订单/通知/结果，同键不同意图拒绝。只读响应也固定原结果，通知幂等同样真实持久化，不只订单防重复。

## 5. 状态机与恢复硬约束

1. 采用安全模型第5节唯一状态机：RESERVED→EXECUTING；EXECUTING→SUCCEEDED/FAILED/UNKNOWN；UNKNOWN→SUCCEEDED/FAILED/UNKNOWN；终态不可互换、重复终局无变动。
2. 接受提交后才联系下游。持久化执行租约/版本及 owner token；不要持DB事务锁跨下游网络调用。过期执行租约先对账，不等于失败；不能靠进程内锁/队列保证多worker一致性。
3. 恢复仅从数据库已接受的不可变意图、原报价、原路径和 operation_id 出发，不能用HTTP body补工具/参数/成本。内部恢复与外部授权入口分离；撤销/过期/key停用不阻止已接受操作安全对账，不允许其创建新意图。
4. 固定全局锁序与A1兼容：涉及身份/key时先锁它们，再任务/根、根至叶、操作；任何需要混合锁的路径不反向获取。恢复可以不验证当前用户权限，但必须核验持久化接受事实和完整路径。报告列出各入口锁序及死锁防护。
5. 全祖先 SETTLE：reserved各减原金额/1，settled各加原金额/1；RELEASE：reserved各减原金额/1，settled不增。金额0仍处理次数。终态、各节点计数、一次终局事件和回执outbox **同一网关事务提交**。
6. 写RESERVE已有路径的根至叶全节点delta，使用有界负值；每操作只一个RESERVE和最多一个SETTLE或RELEASE（互斥），由事务/唯一约束保障，不只先查再写。事件、节点、首次意图/成本/证据不可被恢复覆盖。
7. 成功只在下游持久化确认且金额/意图/快照一致时结算；返回不一致且可能有效果→UNKNOWN，不释放。超时、断连、503、一次查无结果/404均不能视为确定失败。
8. 确定失败要求下游持久化终局拒绝，使该键不能迟到成功；查无结果则继续同键恢复/查询并保留预算。bounded timeout/backoff/attempts，永久未知不伪造成功或释放，可暂停重试但保持UNKNOWN。
9. 两个恢复者及旧worker迟到结果竞争：下游唯一约束防重复效果，网关lease/version条件迁移防重复结算/释放；过期owner不能覆盖新owner或终态。真崩溃不依赖finally完成清理。
10. 现有001未给 operation.grant_id 或 event_nodes.grant_id 加FK；实现持久化恢复时检查被引用路径删除/同ID重建会否破坏保全。必要时通过新增迁移保护**已接受操作引用的节点/路径**；不能重新开放根删除，也不能删历史数据过升级。避免把未来合法计数UPDATE误拒绝。

## 6. 回执outbox、HTTP与查询

- 终局事务保存稳定 receipt_id、不可变待签payload/结果与 ledger_changes（规范字段见9.5），receipt_status独立PENDING/READY。UNKNOWN没有最终回执；FAILED最终amount_fen=0。
- 回执绑定首次token/proof/intent及最终结果、全祖先delta；用真实SDK计算result_sm3/ledger_sm3，typ=ag-receipt+jwt。签名失败不重下单、不更改业务终态，outbox可恢复；重试返回同一持久化回执，别每次重新签发新ID/iat。
- B缺失可保存结构化待签材料并标依赖未完成，不用伪摘要占据生产签名字段。真实签名可能在事务外，但发布结果须条件更新绑定同一payload。
- POST `/v1/invocations` 精确沿用9.4，原始body bytes送 B 验证器；本轮公开签名端点固定 `https://gateway.agent-guard.test/v1/invocations`，与A1的INVOKE_ENDPOINT一致；查询端点固定同源 `/v1/operations/query`。实际部署使用固定主机映射和可信开发CA，不从Host/X-Forwarded推导签名受众，不关闭TLS验证；不接受Bearer/DPoP降级。若需非默认公开端点，先提交SDK/账本共享可信配置的兼容提案和负例，不能直接删除A1端点检查。202返回operation_id/status/receipt_status；对已有终态不伪装新RESERVED，响应细节在报告中确认。
- POST `/v1/operations/query` 专用 result-read证明与 `{profile,task_id,operation_id}`；仅原grant/holder、同tenant/task且当前权限有效。事务锁后复核key/所有祖先/令牌/proof时效并登记新proof。查询不扣业务次数、不执行下游；proof重放和无权猜operation_id拒绝。
- 不公开 recover/settle/release/sign 管理入口，也无“已验权JSON”“任意成本”入口。worker使用内部命令/服务装配。
- HTTP错误按9.6；A1 INVALID_CONTEXT/COST映射需区分格式、权限和可信依赖故障，不能全归500。AGPoP认证失败challenge正确；错误日志和响应不泄露token、内部栈、其他租户或服务secret。
- 未包含独立审计锚点的材料标UNANCHORED；完整审计导出属A3，不称“签名等于完整日志”。

## 7. 正式验收矩阵（文件中测试ID需对应）

所有账本/下游一致性测试真实PG；并发使用独立连接和barrier/event，每组10轮，不用sleep碰运气。测试断言每层金额/次数、操作/事件/outbox、订单及通知实际数量，不能只看HTTP。

| ID | 场景与必须断言 |
| --- | --- |
| A2-P01 | 三层订单70000/1成功：唯一订单，全祖先reserved=0、settled=70000/1，RESERVE＋SETTLE一次 |
| A2-P02 | 下游持久化终局拒绝：FAILED，全祖先预留释放且无结算，RELEASE一次，迟到执行仍不能成功 |
| A2-P03 | 零金额读取/通知：成功或失败次数正确结算/释放，通知效果最多一次 |
| A2-P04 | 接受提交前中断不产生效果；提交后worker未启动/崩溃，新进程从持久状态恢复 |
| A2-P05 | 下游已提交订单但响应丢失：UNKNOWN保留额度，恢复得到同一订单，一次结算 |
| A2-P06 | 下游成功后、网关终局事务前中断；重新恢复无二次效果/结算 |
| A2-P07 | 终局事务中途注入异常（节点更新/事件/outbox阶段）：计数、状态、事件、outbox全回滚；重试正确 |
| A2-P08 | 下游查无结果后旧请求迟到成功：不提前RELEASE，最终唯一效果与SETTLE |
| A2-P09 | 两恢复者＋过期租约旧worker竞争：终态不可覆盖，只有一终局事件/一回执outbox；10轮 |
| A2-P10 | 已接受后祖先撤销/过期/key停用：内部恢复原意图可完成；外部重试/结果查询拒绝 |
| A2-P11 | 报价修改/删除后的同键新proof重试仍用原快照；新键需当前有效报价，错版本/金额/关联拒绝 |
| A2-P12 | 错下游金额/意图返回且可能已有订单：UNKNOWN预算保留，不能伪成功/失败释放 |
| A2-P13 | 不足根/中间预算、次数耗尽、并发接受与结算/恢复：不超限、无负数/死锁；10轮 |
| A2-P14 | 双下游执行同键与不同意图、无/错服务认证、代理直连：DB唯一性/认证拒绝，订单与通知均覆盖 |
| A2-P15 | 真实授权下的非法params、工具别名、重复JSON字段/重复SKU/bool数量、空/缺失集合、资源跨租户及路径/URL注入、scope不足/子权限超祖先/快照不匹配：零效果/零预留 |
| A2-P16 | 缺/错token/proof、替换body/holder/endpoint、token盗用及proof重放：真实B验证拒绝，不构造假VerifiedInvocation代替 |
| A2-P17 | result-read真实签验、锁等待过TTL、撤销/停用、跨租户/其他holder查询、新proof并发/重放：拒绝或授权读取且零新增业务计数 |
| A2-P18 | outbox签名失败/签后保存前崩溃/返回丢失：业务不重执行、receipt_id/payload稳定、最终真实SM2验签；篡改结果/路径/delta失败 |
| A2-P19 | 001或003已有非零预留/已撤销数据升级到最新：七表原行逐列不变，新增结构正确、重迁移无变化；非法升级原数据及版本记录不变；旧操作快照缺失/格式不合法或证据不全时保留预算、隔离待处理，不能用当前报价补造后执行 |
| A2-P20 | 删除/重建已接受路径、改意图/成本/首次证据、非法状态迁移及双终局：数据库/事务拒绝，合法UPDATE继续可用 |
| A2-P21 | 真实签名HTTP正常采购＋读取＋通知＋授权查询闭环；固定端点/边界、202/error契约；无假验权生产装配 |

缺 B 时 P15可分层测参数和资源，不称密码验收；P16/17的真实签验、P18真实回执、P21真实HTTP明确标BLOCKED。P04至少一条独立进程终止/重启复验；其余注入可分层测试，区分实际断网与异常替身，不宣称都经历真实网络故障。

## 8. 检查点、证据与交付

**检查点一（先停一次）：** 报告填基线/文件所有权/真实B依赖/新增迁移方案/锁序/下游契约/分段计划。先完成必要环境和类型，不先搭全框架。

**检查点二（A2.1收尾）：** P01—14、19—20及P15分层范围有实测；现有A1全部通过。报告标CORE_READY_FOR_REVIEW/PARTIAL，说明未完成B门槛；可以继续已确认的B对接，缺B不要无限等、不要宣称全部完成。

**检查点三（完整A2）：** 真验签HTTP/查询＋真回执＋所有P用例有证据，标READY_FOR_REVIEW，交主代理独立复验。READY不是自动ACCEPTED。

- `tasks/A2-report.md` 保持约150行内摘要，记录基线、环境、接口决策、修改/新增清单、测试ID→文件/函数、脱敏命令/退出码/pass/fail/skip、依赖与限制。
- `artifacts/A2/<run-id>/`保存本地脱敏日志、JUnit、故障/并发断言证据，Git忽略；日志不能泄露实际DSN/token/key。
- 定期检查 `git status`、已跟踪diff及未跟踪文件，读回新文件，不以“写入成功”口头声明替代落盘证据。
- 必跑 ruff check/format、全部unit/骨架/文档、全部integration（缺库报错不skip）；若另建HTTP/下游测试目录，更新CI显式执行，不能默认漏跑。
- README给可执行的安装/迁移/可信合成数据初始化/worker/下游/网关/测试/仅自有资源清理命令；缺B的服务明确拒绝启动。
- 现有A1 68＋78为基线不是新增后的固定期望数；分项报告实际计数。Python3.11基准、新依赖安装、PostgreSQL测试均要验证，远程CI未跑须标NOT RUN。
- 最终回复约500字：状态、报告/证据、实测、BLOCKED/未完成、建议下一步。不提交代码；主代理验收后再决定PR。
