# 独立审查：PACKAGE_REVIEW／cosm2-full-20261017／r1

## 1. 结论与边界

**PACKAGE_READY**。无阻断项。受审对象为 `tasks/workflow/runs/cosm2-full-20261017/package-v1.md` v1 及六文件冻结清单；本结论是实施包审查，**不是实现 ACCEPTED，也不是测试 PASS**。原规划第0–5节、A1–A7、B1–B9、G1–G3及C交接清单均在范围内。B8/B9由最新连续授权纳入目标，仍必须B6全绿后实施，B9优先。G1未通过不得集成网关。

当前项目仍PARTIAL。原A3.3/A3.4四万次长实验不属于本轮，不重开该阶段、不套用其历史568项矩阵。C论文正文不代写，交付其可写清单、真实数据和媒体。Git发布和实际Git标签不在授权内；本地冻结候选清单满足本轮冻结动作。

本轮只读查看业务源代码及历史证据，未实施、未运行未实现行为测试、未启动容器/业务服务/数据库。仅写本reviewer自有 `artifacts/cosm2-full-20261017/package-review-r1/` 报告和静态证据。报告供主控原样归档；本reviewer不设置阶段接受或派发实施。

## 2. 独立性、版本与授权

- Fresh reviewer子任务：`/root/cosm2_full_package_review`；请求角色gpt-6.1-sol/high；后台effective metadata无法独立观测，记UNKNOWN。
- 仓库：`/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`。
- 实际分支：`codex/cosm2-2p-B`；HEAD：`6ab288c928f8b63778856d426e3bbbec9511144c`。未提交及未跟踪资产属于基线，完整保留。
- 授权依据：本轮包及current-policy首段记录真人原话“你直接把B的部分也做了吧，从头开始，一直到我发给你的那个markdown里面的所有内容都被实施”；本reviewer收到主控明确传递该真人授权。未取得原消息ID，不编造ID。现行首段覆盖其下旧“不接管B”历史限制。
- 冻结清单：`../controller/package-sha256.json`；清单自身SHA256 `44ea6eec3d3980ef2940614b119bc24e9f7a2b769115df605f9851a4fc172e4b`。开始和结束均独立重算六项，全部一致；详见 `fingerprints-end.json`。核心包SHA256 `ac4fa102dbfda7c4ed966c159db94b5e4c74687ec9a813c5d3113fdbb3960a20`。
- 原始规划SHA256 `7136a4a5cf187c784f977b5033dc9c7533a6baf4ab2bf21fb557e7f53ce67f0e`；契约/policy/AGENT均在同一冻结清单。
- 原始staged/unstaged、状态证据分别为 `staged-start.patch`、`diff-start.patch`、`status-start.txt`；实际阅读的33项文件另有 `baseline-read-sha256.json`。开始/结束受审包及所读依赖无漂移。包由主控冻结，业务尚未派发；不把未提交HEAD冒充完整候选。
- 后续IMPLEMENTATION_ACCEPTANCE必须另冻结全部代码/测试/配置/依赖/资料/原始数据，并由全新reviewer独立实跑。本轮六项包指纹不替代后续完整实现候选指纹。

## 3. 已直接核对的基线及接口判断

直接查看原始规划全文、AGENTS/AGENT、current-policy、implementation-contract、review-contract及review模板，以及README、oauth-oidc-sm2-mvp、安全模型和验收入口。重点实际代码：

1. `threshold/contracts.py` 当前公钥固定32字节、无scheme；`codec.py`现有V2/V3字段顺序、严格解析、profile和消息域；`verifier.py`签名路径及expectation；`binding.py`原子持久化原始envelope、path、支付摘要及最终DB时钟检查。新增COSM2 profile分支可复用VerifiedThresholdApproval，不需要修改001–009迁移。
2. `authorization/permission_snapshot.py`实际Provider.load自行连接数据库，查ag_grants/ag_grant_tokens，验证AS签名、历史holder/kid注册、父子逐维收窄及完整root→leaf链。B3必须给Provider自身也配置只读DSN，不能仅其额外预算查询只读。PermissionSource.snapshot不含holder/kid，B3须从已验证链或可信状态比对，不能假设不存在的属性。
3. `gateway/config.py`目前严格固定FROST配置字段；`endpoint.py`由服务端要求批准，真实token/AGPoP先验证，再批准验签，最后执行绑定；`factory.py`实际装配下游。需要串行共享API冻结后同步调用方，不能只新增scheme字段。
4. `execution/service.py`当前首次execute和UNKNOWN恢复execute都从持久operation取事实，调用下游时没有批准及业务idempotency_key参数；B9须覆盖两条调用路径及正常装配，原envelope可从不可变ag_threshold_approvals取得。`tools/downstream.py`独立数据库/事务，当前无密码验证，以operation_id唯一幂等，服务secret及完整可信报价已存在。
5. `x402/accept.py`按真实intent重算并精确匹配payment_digest，V3已有支撑。`tools/x402_gateway_demo.py`使用真实Anvil/FiatToken/EIP-3009和独立数据库；新scheme开关不替换结算算法。
6. `tests/fixtures/{gateway,threshold}.py`和`tests/integration/test_threshold_gateway.py`提供真实AS链、独立下游、零效果/全祖先计数、并发、最终时钟、撤销、持久重启/丢响应恢复等基线。原FROST过期断言403是真实兼容义务。
7. `tools/threshold_gateway_demo.py`、现有COSM2 server/result严格解析、`tests/test_cosm2_demo_result.py`、crosscheck、benchmark、参考实现与sm.py已读。A既有工具是可复用起点；bench的round2-db/e2e当前仍待实现，crosscheck当前依赖缺B失败，均不能算已通过。现有“B工具不存在”临时状态断言应改为对应实际部署状态测试，保留缺失时明确失败/禁用的语义。

## 4. 完整需求与计划矩阵

下表状态统一为“计划完整，行为NOT_RUN”；是包设计核对，不是运行通过。测试文件/探针表示实施与后续独验应落实的入口，不能充当已存在的断言。

|原始来源/ID|本轮交付与需要独立观察的断言|实现/计划测试入口与门控|
|---|---|---|
|0.1/0.2|双域乘法分享、确认消息、固定ID、P2自主重算M/e；r及s特殊值重试；P1最终铜锁验签；半诚实边界|cosign curve/protocol，test_cosm2_core，参考逐式比对|
|0.3-1/0.4|001–009与旧V1/V2/V3字节冻结；新增scheme/profile/域；V3、64字节r‖s、SPKI规范|controller迁移基线、codec/verifier兼容负例与旧threshold回归|
|0.3-2|P1/网关/效果端最终验签均成熟sm.verify_sm2_message|代码调用链与真实正负验签|
|0.3-3/4/7|不伪造不删负例；无秘密/完整token日志；原样命令输出/失败保留|全自查/独验原件及C包内容检查|
|0.3-5/6|0700/0600，按域读取份额，k1内存且失败清除，P2无跨轮nonce|shares权限/角色负例，core重复/失败会话测试；P1子进程实证，不宣称OS强制隔离|
|0.3-8|codex/cosm2-2p-B，唯一集成；不commit/push/PR|分支已静态确认，root最终整合/冻结|
|1/G1|核心和公开向量OpenSSL真绿前不接网关；失败只能声明设计/原型|B1/A1/A3原始输出；保留历史失败|
|1/G2|冻结代码、真实C1–C11通过数；未绿前端/论文不能声称集成已实现|后续全量候选冻结/独验；B6后B9/B8|
|1/G3|基准数据、四图、媒体和C表冻结；日期真实|原始samples、图/媒体SHA/命令/run_id；本地候选冻结名|
|B1|50随机密钥成熟验签，篡消息/错钥拒绝；非法点/INF；未开/重复/失败会话；固定坐标；三字段公开向量无秘密|新增test_cosm2_core、tests/cosm2-public-vector.json；A1/A3交叉核验|
|B2|各域keygen/确认后才写；权限/role过宽拒绝；确认失败零文件；public元数据仅公开信息|shares/keygen，test_cosm2_shares|
|B3|严格V3→policy/time→AS全链/holder/kid/scope→全祖先撤销/有效期/余量→重算M→partial；只读不预留|authz_domain；六个AUTHZ_*及解析/坏链拒绝，拒绝零sign_round2调用；SELECT-only角色真实UPDATE/INSERT/DELETE拒绝探针|
|B4|缺scheme旧行为；服务端二选一；COSM2严格V3/profile/64字节/成熟验签；同Verified对象与接受绑定|contracts/codec/verifier/config；两向错配、请求头不能切换；旧全回归|
|B5|可信请求tool/key/params/报价金额核对先于round1；真实P0及P1子进程协调；EXEC_MISMATCH/COSIGN_ABORTED且清理nonce|exec_domain/authz_cli/fixture enroll/sign/sign_refused/header_for及domain测试|
|B6-C1|正常202一单；新鲜proof、同批准重试同operation；一次预留/结算/批准/效果|真实PG+AS+独立下游test_cosm2_gateway；查询全祖先/operation/approval/事件/outbox|
|B6-C2|无批准401 APPROVAL_REQUIRED、零效果/零预留|同上|
|B6-C3|仅执行域d1+随机partial，401 INVALID_SIGNATURE、零订单|须真正只持d1构造攻击，不能换成另一种坏签名冒充|
|B6-C4|伪64字节401 INVALID_SIGNATURE、零效果|真实网关入口|
|B6-C5|共签后篡金额409 APPROVAL_MISMATCH、零效果|保留原签名，命中真实金额绑定拒绝|
|B6-C6|签前任意祖先撤销AUTHZ_REVOKED，零partial/签名/订单|真实撤销事务+authz counter|
|B6-C7|签后撤销，网关403 REVOKED、零新订单|真实动态接受事务；不只测静态签名|
|B6-C8|任意祖先剩余量不足AUTHZ_OVER_BUDGET|非零reserved/settled余量，不能只改leaf总限额|
|B6-C9|FROST部署拒COSM2，反向亦拒绝|配置/信封交叉，客户端无法选scheme|
|B6-C10|COSM2过期401 EXPIRED；FROST既有403保持|scheme-specific错误映射及最终事务时钟过期回归|
|B6-C11|实际产出签名铜锁标准验签通过|真实公开公钥/消息/签名；不能把字节格式相同称为恶意安全证明|
|B7|固定C1/2/3/5/6/7、严格原result字段/名称/计数、真实三轮timing、指纹；本机cosm2-run/桌面，公网只读|cosm2_gateway_demo、server、desktop、前端与docs/cosm2-gateway-20261020.md；资源归零|
|B9/C12|B6绿后优先；下游配置公钥独立铜锁验签；原批准与金额/items/key及完整规范意图绑定；绕过网关无有效共签零单|downstream/factory/service首次及恢复路径；无/伪/篡改/不同意图/重放探针，保留旧下游幂等/报价/secret行为|
|B8|B6绿且B9后；scheme开关、真实V3 payment_digest；正常本地链仅结算一次、篡改拒绝|x402_gateway_demo及现有x402回归；EIP-3009/secp256k1保持|
|A1|B公开向量OpenSSL3正例和改一字节负例；正确distid和DER|cosm2_vector_check真实输出；不是参考向量旧成功替代|
|A2|cosign导航/13步/授权域红叉/旁白/modules/三项对照/边界与来源；CSP self无CDN内联|web三个文件、Node、1366×768实看；旧示意资产保留来源|
|A3|固定坐标、双向验签、20随机消息compute_e完全一致|现有test_cosm2_crosscheck三项真实全绿，无参考fallback|
|A4|固定镜像/CPU环境记录；10预热100正式、各原始样本/失败；三轮/总/DB谓词/单SM2/验签/FROST进程开销/e2e|bench/plot；summary每项n/median/p95/min/max；e2e独立measurement.json同run_id，明确边界，禁止三轮和冒充e2e|
|A5|严格六用例/中文名/本次现场运行与历史回放分离；无结果示意；三轮标单次非统计|FIXED_DEMOS、server、真实B7结果、Node与浏览器核验|
|A6|四矢量PDF统一字体颜色，系统信任域/无agent份额、协议谓词/标准验签；7攻击×4拒绝位置仅真实数据|paper_figures、latency；每格来源/命令/run_id/SHA；矢量/逐页渲染QA；未触发格不伪造拒绝码|
|A7|原图总览/1/3/6/共签示意+真实/记录；真实3分钟视频可见run_id/日期/来源；完整C包|截图与录屏真实文件、raw/summary/四图/媒体/来源表/全部历史失败，不改旧失败字节|
|4接口|B1→A1/A3/A4 API/向量先冻结；B7→A5字段不改；拒绝码、命令/run_id→A6/A7/C|串行共享API后精确独占文件移交；不消费半成品|
|5交接|逐项真实勾选核心/向量/谓词/回归/C1–11实际数/run_id/B9/B8/局限；未验项目仅设计/后续|本地C包/可写清单；不把包审当实现证明|
|QUALITY/隔离/独验|Python3.11固定依赖及镜像，ruff check/format，相关unit+原threshold/x402完整回归、真实独占PG16；amd64仿真披露|脱敏命令/退出码/JUnit/容器fullID与owner；测试DSN及两个业务数据库；STOP→完整SHA→fresh IMPLEMENTATION_ACCEPTANCE|

## 5. 已消解的普通解释与非阻断实施注意

以下是原始规划和基线间的具体解释，不修改被冻结包，不豁免原义务：

- **AUTHZ计数**：原0.4实际有六个AUTHZ_*（REVOKED/EXPIRED/PATH_MISMATCH/SCOPE/OVER_BUDGET/POLICY_MISMATCH），包的“七类AUTHZ”是计数笔误。全部六码均必须覆盖，严格解析及无效AS链还须安全拒绝并证明不调用sign_round2；不凭空另发明第七码。
- **C10**：原FROST EXPIRED映射403；原COSM2 C10明确401。仅COSM2批准超时采用401，保留FROST与其他原验权过期行为，分别测试；不能全局把EXPIRED改401。
- **无支付V3**：COSM2普通采购仍严格V3。可定义新profile专用无支付sentinel `"0"*64`，普通调用要求该值；有x402时必须使用真实intent摘要且维持精确绑定。不能修改旧V2/V3字节、把sentinel作为支付绕过开关。该选择由主控消息明确提出，本reviewer认可其与新增profile兼容，应在共享API/文档及负例固化。
- **B9参数与恢复**：items本来已在V3；业务idempotency_key与下游operation_id不是同一物。新参数从持久operation取得，批准从不可变ag_threshold_approvals取，不能用当前客户端重试头替换。首次及恢复execute都转发原envelope。下游在副作用之前验证，坏批准不得在已有记录replay分支绕过校验。对同签名行动换operation_id的重放必须保证不会新增订单，或明确拒绝；业务幂等要求不能因新参数丢失。此为原B9精确意图及原下游不重复效果义务的直接覆盖，不要求改历史迁移。
- **威胁说法**：B9能证明所测无批准/篡改意图无法产生效果；不能宣称同主机管理员失陷、任意恶意P1/P2或所有网关失陷都被解决。P1进程分离及文件读路径不是OS级强制隔离；Python对象置空也不是可证明物理内存擦除。
- **性能口径**：B7固定result不含e2e，不能增字段破坏A解析；同run_id sidecar合理。FROST含进程启动；数据库谓词必须真实。严格保留失败样本与历史失败C副本；不得混机器/改旧summary，不能把旧A3.3/A3.4重测当本轮必须项。

这些解释属于实现时必须落实的接口约束和验收检查，不是当前发现的业务实现缺陷；实现尚未开始，不为尚无新代码开缺陷单。若后续实现偏离它们或更改冻结包范围，须重新判定影响并按review契约处理。

## 6. 本轮实际执行、资源与结束核验

实际只执行只读cat/sed/rg/git和Python hashlib；git/哈希命令退出码0。一次搜索使用了不存在的旧文件猜测名，rg返回路径错误后改读实际 `authorization/permission_snapshot.py` 与 `test_verified_execution`引用；没有把失败搜索算测试结果。无pytest/ruff/Node/OpenSSL/数据库/链/浏览器行为测试，本轮行为测试统一NOT_RUN（符合PACKAGE_REVIEW）。没有新依赖安装，没有创建/连接业务资源，无需容器/数据库清理。未输出秘密。

审查开始六冻结项均匹配；结束重新读取全部六项及33项静态阅读清单、git staged/unstaged/status，均一致。静态输出证据见本目录 `metadata.json`、`baseline-read-sha256.json`、`fingerprints-end.json`、`status-start.txt`、`status-end.txt`、`diff-start.patch`、`staged-start.patch`。报告写入后已读回检查完整表格与结论。

主控可在核对本报告、真人连续授权及冻结指纹后，按包派发已配置worker，首先完成core/G1，后续遵守B6→B9→B8门。最终全部writer停止、完整候选冻结后，另请fresh reviewer执行完整IMPLEMENTATION_ACCEPTANCE。本reviewer至此STOP。
