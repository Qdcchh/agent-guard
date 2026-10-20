# 独立实施验收：IMPLEMENTATION_ACCEPTANCE / cosm2-full-20261017 / r1

## 1. 结论与范围

**NOT_ACCEPTED**。本轮审查原《双域协同SM2实施规划》完整第0–5节、A1–A7、B1–B9（含两个可选项的已实施目标）及C交付。确认阻断 **COSM2-R1-001**：冻结候选中的C10集成测试以只有一秒的批准有效期完成真实签名前置准备，实际全组执行时在授权域先到期，未到达其要求验证的网关401 EXPIRED。原完整PG组552项结果为551通过、1失败。单独复跑两项C10五轮共10通过，不能消除已观察到的不稳定失败；独立延迟探针稳定复现其原因。没有证据显示生产过期校验失效：独立已签后真实到期探针确实得到401 EXPIRED。必须修复测试同步后重新冻结，另派全新reviewer，不能通过删除/skip/降低401或真实到期要求放行。

受审业务及资料writer由主控明确STOP；本reviewer未修改任何冻结文件、未调用subagent、未commit/push/PR/标签/合并，未触碰8765或他人资源。只写`artifacts/cosm2-full-20261017/review-r1/**`及工具临时内存。整个旧A3.3/A3.4四万次实验未重开，不能借本轮宣布全项目完成。报告中PASS仅表示具体证据范围，不是整体ACCEPTED。

审查日期2026-10-17，Asia/Shanghai。fresh Task `/root/cosm2_full_acceptance_r1`；派发要求为gpt-6.1-sol/high，后台effective metadata不可独立观测，记UNKNOWN。主控明确传递真人连续授权原话及完整范围，未取得原消息ID，不编造ID。本报告是实施验收，不是包审；既有PACKAGE_READY不能替代本轮执行。

## 2. 候选与独立性

仓库 `/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`。实际分支`codex/cosm2-2p-B`，HEAD `6ab288c928f8b63778856d426e3bbbec9511144c`。HEAD仅基线；未提交/未跟踪实现由完整内容清单绑定。开始独立读取2021份文件重算SHA256，零差异；清单自身SHA `ac4a9e62bd8d0493569d2312d3f53d6eb7bdb042f5beecdf70f12fc6e447ab3e`。证据`fingerprint-start.json`与`git-status-start.txt`。结束核验见本报告第9节与`fingerprint-end.json`。

候选ZIP为`复赛冲刺材料-20261018/C交付-COSM2全量-20261017-candidate2.zip`，独立SHA `61d4704945ccd3b63987c2bb07472d8fb46ee6e1e68597a976d77dbb62a29d05`。清单402份来源逐份与仓库原件和复制件比较，ZIP404成员逐字节比较、CRC全通过；`manifest.json`明确`independently_accepted=false`，没有先宣称已接受。review目录自身排除，未以该排除修改候选。实际git diff/current status及18份migration的初始SHA均直接核对。

## 3. 直接检查的实现与边界

已直接阅读AGENTS/AGENT、current-policy、实施/审查契约、review模板、完整原规划及本轮package-v1/package-review/implementation-notes/implementation-report/G1/B6-gate、两份COSM2文档。另读README、security-model、acceptance、oauth接口的相关基线章节；没有把旧阶段承诺当本轮已完成。

实际调用链核对包括：

- `cosign/curve.py`点/标量校验及半诚实公式；`protocol.py`固定ID与ZA/SM3、一次性k1、P2自行计算e、P1成熟最终验签；`encoding.py`规范SPKI/点/r||s转换；`shares.py`先确认签名后原子落盘、0700/0600、角色/符号链接/大小约束。P2无跨轮nonce字段，Python引用释放不证明物理擦除。
- `authz_domain.py`严格V3→策略/到期→真实PermissionSnapshotProvider链签名/逐维收窄→精确链/tenant/task/holder/kid→独立只读事务当前全部祖先状态→重算消息并签partial。撤销按整条路径优先于有效期和预算；Provider与额外查询使用同一SELECT-only DSN。拒绝计数在曲线调用前断言。
- `exec_domain.py`以真实bundle/可信catalog核对请求与金额，先于nonce；失败finally清除k1。`authz_cli.py`JSON stdio有界、partial用64hex避免JSON安全整数，信任输入为公钥/登记/策略；P1父进程不构造授权签名者，实际child读取授权份额。初始化keygen曾生成两份，与运行时读路径区分。
- `threshold/{codec,contracts,verifier,binding}.py`、gateway config/endpoint/factory、ExecutionService/VerifiedExecution：新profile/scheme/V3 sentinel，服务端选方案，原FROST默认及V1/V2/V3消息序列逻辑保持；最终接受事务绑定原意图/付款摘要/DB时钟。COSM2过期401与旧FROST/AS过期403分别保留。
- `cosign/effect.py`和`tools/downstream.py`：先成熟SM2验签/精确金额items/key/quote/tenant/task，后独立事务创建效果；已有记录重放仍验签。`ds_cosm2_bindings`的action/business-key/operation唯一约束与比较防跨操作重放。ExecutionService首次及UNKNOWN重发均从不可变批准表转发原envelope。新下游表须显式provision，18网关迁移未改。
- x402 gate/resource/accept及真实demo：持久operation/批准与payment intent绑定；链结算仍EIP-3009/secp256k1。B9只检查签名、意图、一次性绑定，不独立查询AS动态预算/撤销、墙钟到期或付款结算；该限制实际文档披露，不能写成无条件网关攻陷安全。
- teacher server/desktop/frontend：固定六wire、严格结果校验、坏保存目录不认、保存回放与本次运行分离；本机host/origin/session控制、公网只读。13步时序的授权域红叉、中文旁白、模块、对照、边界与来源实际存在。
- benchmark及真实PG adapter的prepare/timer/finish边界：纯三轮、含真实AS/只读谓词round2、HTTP发送至202三种口径不同；FROST含Python I/O/进程启动/复验。未重新跑900次正式基准，独立核对每行、来源和全部统计。

## 4. 完整原规划矩阵

下表全部属于本轮必需范围。I=本轮独立实跑；S=本轮直接静态查证；H=历史原件/媒体核对。测试的精确node与计数见各JUnit，实际命令见`*.command.json`、`*.exit.json`和脚本。表中共享证据不重复累加测试数。

|原始ID|独立观察与实现/测试证据|状态|
|---|---|---|
|0.1|执行/授权两份协同产出普通SM2，真实授权域门控；core/domain/gateway全链，I+S|PASS|
|0.2-keygen|乘法分享公钥、确认消息，无构造完整d；固定坐标与交叉验证，I+S|PASS|
|0.2-sign1|P1/P2各自从严格结构行动重算M；P2接口无e参数；crosscheck20随机消息，I+S|PASS|
|0.2-sign2/3|Q1曲线/INF拒绝、随机k、r特殊值循环、partial；core50随机成熟验签，I+S|PASS|
|0.2-sign4|round3第一行清k1，s特殊值失败、成熟SM2验证才输出、重复/失败会话拒绝，I+S|PASS|
|0.2-security|半诚实、n=2、非常数时间、物理擦除不可证披露，S|PASS（有边界）|
|0.3-1|18migration初始SHA全匹配；新scheme/profile不改原V1/V2/V3/GM语义，旧回归，I+S|PASS|
|0.3-2|P1、网关、下游最终均crypto.sm成熟验签，OpenSSL正负，I+S|PASS|
|0.3-3|未删负例/不造成功；旧升级列表仅计入既有008/009，原失败保留；本轮失败公开，S+H|PASS，C10另FAIL|
|0.3-4|C包逐文件私钥PEM/带密码DSN/JWS/share_hex扫描零命中；公开vector三字段；生产CLI不输出秘密，I+S|PASS（模式扫描非绝对证明）|
|0.3-5|份额0700/0600与角色拒绝；P1运行父进程不读authz，真实子进程测试，I+S|PASS（非OS强隔离）|
|0.3-6|k1内存一次使用且finally清引用，P2无跨轮状态，I+S|PASS（非物理擦除证明）|
|0.3-7|本轮命令/退出/JUnit/失败/限制归档；历史敏感原bytes不可得明确披露，I+H|PASS|
|0.3-8|分支B、主控唯一整合、无Git发布，S|PASS|
|0.4|scheme/profile/domain/V3顺序/64字节/SPKI与全部八码严格契约，I+S|PASS|
|1/G1|50随机+公开OpenSSL+原A3三交叉；历史G1绿色时序核对，I+H|PASS|
|1/G2|真实PG B6及旧threshold已执行；C10本轮失败，整体代码不能接受，I|FAIL / COSM2-R1-001|
|1/G3|formal02、四PDF、原截图视频/C包来源SHA冻结，H+独立重算|PASS（整体接受仍待）|
|1/optional-order|历史B6真实40绿门后B9再B8，G1/B6门原件与实现记录一致，H|PASS|
|B1|core50组+改消息/错key拒绝、坏点/INF、k1重复/失败、固定坐标与公开向量；非PG全量/openssl，I+S|PASS|
|B2|shares权限/role/确认失败零文件、生成工具与原子写；非PG全量，I+S|PASS|
|B3-1/2|严格V3、policy/audience/epoch/lifetime，非法不入round2，domain测试，I+S|PASS|
|B3-3|真实AS root→mid→leaf、holder/kid/path/scope、坏token/范围拒绝，domain PG，I+S|PASS|
|B3-4|全部祖先撤销/时效/剩余金额与次数，真实SELECT-only UPDATE/INSERT/DELETE/证据读拒绝；独立三祖先撤销优先探针，I+S|PASS|
|B3-5|只读不预留、自行cosm2_message后签partial，拒绝零计数，I+S|PASS|
|B4|默认FROST不变、双向scheme错配/客户端不能选择、成熟SM2严格profile/64字节，完整旧threshold，I+S|PASS|
|B5|可信bundle/quote预检、P0/P1、EXEC_MISMATCH/COSIGN_ABORTED与nonce清理，PG域及父不读authz，I+S|PASS|
|B6-C1|202、同批准新proof重试同operation、一单/一次批准、全部祖先一次结算，I|PASS|
|B6-C2|无批准401 APPROVAL_REQUIRED、零订单/operation/预算/事件/outbox，I|PASS|
|B6-C3|真正只读d1伪partial攻击，401 INVALID_SIGNATURE/零效果，I+S|PASS|
|B6-C4|伪64字节签名401 INVALID_SIGNATURE/零效果，I|PASS|
|B6-C5|保留原签名改金额409 APPROVAL_MISMATCH/零效果，I|PASS|
|B6-C6|签前根/中间撤销AUTHZ_REVOKED零partial；独立root/mid/leaf优先探针，I|PASS|
|B6-C7|签后撤销网关403 REVOKED零新单，I|PASS|
|B6-C8|真实非零reserved/settled剩余量不足AUTHZ_OVER_BUDGET，I|PASS|
|B6-C9|FROST/COSM2两向错配拒绝且不切客户端方案，I|PASS|
|B6-C10|全组中test_c10_expired_is_401签名准备先AUTHZ_EXPIRED；原两项单跑五轮10通过；独立已签到期401通过，I|FAIL / COSM2-R1-001|
|B6-C11|实际签名成熟铜锁独验，public vector OpenSSL正/负，I|PASS|
|B7-result|严格六名称/字段/计数与真实三轮timing/SM3指纹；Launcher实际native0六例、1/1/1/资源0，I+S|PASS|
|B7-entry|实际原Launcher在自有相同字节副本运行；本机server实际按钮产生另一个6/6结果；原媒体native0/actual_wait；公网只读、坏保存负例由全非PG覆盖，I+S+H|PASS（附加UI捕获限制见第7节）|
|B7-docs|启动复现、只读角色、同主机/半诚实/非常数时间/部署局限已直接读，S|PASS|
|B8|原139+新3=当前129加历史13，两个真实CLI各六例成功，本地链2效果/2结算且每正常意图只结一次，I|PASS|
|B8-binding|普通sentinel不可当支付digest；真实支付intent摘要、篡改拒绝，EIP3009保持，I+S|PASS|
|B9-C12|正确service secret仍需有效原共签；无/伪/改金额items/key/tenant/task、已有坏重放、跨operation、并发与UNKNOWN恢复，I+S|PASS（限定边界）|
|B9-forward|首次/恢复均持久原envelope，DS独立DB事务和唯一绑定；旧下游幂等/完整报价行为保留，I+S|PASS|
|A1|OpenSSL3正exit0、改单字节负exit1，checker0，I|PASS|
|A2-nav|新增cosign前于FROST、指定中文机制/13步/模块/三对照/边界，1366原图及当前副本截图，Node与非PG，I+S+H|PASS|
|A2-refusal|红叉在授权域、AUTHZ_REVOKED、后续未发生；EVENT_TYPES/旁白齐，图已肉眼检查，S+H|PASS|
|A2-CSP|self、无内联脚本样式/CDN，真实HTTP与前端逻辑测试，I+S|PASS|
|A3|原三交叉：固定公钥逐坐标、双向验签、20随机compute_e，非PG全量，I+S|PASS|
|A4-environment|formal02完整镜像ID、CPU/Python3.11.17/tongsuopy1.0.1、arm64宿主amd64仿真及并行负载披露，H+S|PASS|
|A4-samples|九项各warm10/raw100、900/90全部OK、同run/environment，独立重算n/median/p95/min/max全部一致，独立脚本|PASS|
|A4-boundaries|round1/2/3/total、真实PG round2、单SM2/验签、FROST进程开销、HTTP→202各自明确；110受理/祖先计数及效果0来源核对，H+S|PASS|
|A4-plot|四PDF中的latency为矢量，median/p95与统计/源码一致，独立渲染肉眼核对，S+H|PASS|
|A5|无数据示意、保存回放/current-run分离、中文六例及单次非统计标签；全非PG/Node/真实native与原媒体，I+S+H|PASS|
|A6-system|用户/三代理/AS授权域/执行域/状态库/下游证据、两个逻辑信任域与agent不持份额，PDF独立渲染，S+H|PASS|
|A6-protocol|三轮、自主重算、谓词检查与标准SM2验签，PDF独立渲染，S+H|PASS|
|A6-negative|7×4=28格，8 OBSERVED/20 NOT_TRIGGERED；各格路径/run/SHA逐个核对，另有DS3条，S+H|PASS|
|A6-style|四图统一中文字形/颜色，实际逐图肉眼无缺字/碰撞，矢量PDF及源表，S+H|PASS|
|A7-screens|11PNG原图SHA核对、全部肉眼看过；总览/1/3/6/示意/真实/记录来源清晰，H|PASS|
|A7-video|ffprobe亲跑MP4/WebM均185.4秒1366×768；120s帧可见真实日期/run_id/来源；终态UUID01af29ac…与native_exit0/actual_wait/current-run匹配，H|PASS（未重新录制）|
|A7-C-table|raw/summary/四图/媒体/来源表完整，402来源/404ZIP逐字节CRC与hash，独立脚本|PASS|
|4-interfaces|B公开vector/API/result契约/拒绝码/运行来源按串行冻结移交文件记录，S+H|PASS|
|5-core/OpenSSL/predicates|原清单逐项已有关联证据，并明确独立接受pending，I+S|PASS|
|5-regression/C1–11|实际C1–11计数及C10失败不能用原自查绿冒充，I|FAIL / COSM2-R1-001|
|5-B7/B8/B9/limits|run_id、可选两项与半诚实等限制实际有资料；不允许无条件gateway-compromise claim，I+S+H|PASS|
|C-history|旧A/core/B6/P1/bench/capture失败及脱敏说明有包成员；full01及capture01/02明确排除；未声称原未脱敏原bytes/SHA保留，S+H|PASS|
|QUALITY|固定Python3.11镜像、ruff/format/Node/diffcheck、全非PG/真实PG/原x402/threshold；PG必跑1失败，I|FAIL / COSM2-R1-001|
|WF-freeze/resource|开始/结束2021文件全SHA、branch/HEAD；只操作随机owner自有PG/network，TEST DSN0600不公开，I|PASS，结束2021/2021一致/资源0|

## 5. 历史问题与兼容性核对

未因自查报告说“全绿”而跳过原测试。当前18migration与初始清单逐字节相同。旧V1/V2/V3 action_message及默认FROST分支没有改格式；COSM2独立profile/domain严格用V3。两处旧升级断言扩大精确列表以包含已有008/009，其他安全断言未放宽。原全非PG五fail历史（3文档、2root权限）保留，本轮非root整体检验其最终候选；容器内RealCli skip用host真实Docker节点补足。

原A FROST基准失败、full01镜像metadata错而排除、capture01/02等待harness失败以及早期worker失败均作为历史；本轮没有覆盖这些冻结历史。敏感trace之前已被worker脱敏覆写、主控未保有原bytes/SHA，此限制在文档及C包直述，不能把公开脱敏副本说成未脱敏原样保存。

## 6. 本轮实跑与证据

镜像经本轮docker image inspect确认：threshold `sha256:997ccb375167a46fb019795a3a59da2d9bc59778b1027e8da85c4f603e8ec567`；x402 `sha256:7c1484073ed19a42683234e65416e0ba78634c1715d2a220a9566ec959a71aaf`，均linux/amd64。arm64 Apple M5 Pro宿主仿真，非独占CPU性能环境。不增加运行依赖。固定容器Python3.11.17/tongsuopy1.0.1；host测试/工具venv为已有Python环境，仅质量/原生Launcher，未把host版本冒充crypto基准。

|实际命令/目标|结果|证据|
|---|---|---|
|非root固定x402镜像 `python -m pytest tests --ignore=tests/integration -p no:cacheprovider -q --tb=short`|exit0，2072pass/0fail/1skip，447.01秒；host已实跑补足该skip|`nonintegration-x402.*`|
|真实PG旧执行/threshold/COSM2+域552|exit1，551pass/1fail/0skip|`integration.command.json/.log/.xml/.exit.json`|
|固定x402正式组129（含COSM2新增）|exit0，129pass|`x402.*`|
|旧x402历史探针13|补齐其要求`/evidence`自有挂载后exit0，13pass|`x402-historical-rerun.*`与`historical-evidence/`|
|host实际Docker旧RealCli|exit0，1pass|`host-realcli.*`|
|原两C10节点各5轮|每轮exit0，合计10pass；不能擦除原失败|`c10-repeat-0…4.*`|
|本reviewer独立负probe|exit0，5pass|`test_independent_probes.py`、`probes.*`|
|COSM2实际Launcher|exit0，六例通过，order/operation/approval=1，资源0|`native-rerun.json/.log/-attach.log`，own replica run301f0ad5…|
|实际x402 sm2-2p及默认frost CLI|各exit0，各6/6；每组2订单/2链交易、资源0|`demo-sm2-2p.*`、`demo-frost-ed25519.*`、两个`x402-live-*`|
|OpenSSL公开向量|checker0；positive0/negative1|`openssl.log/.exit.json`|
|global ruff check / format --check|各exit0；355 files already formatted（含审查自有文件计数，不当候选数）|`ruff-check.*`、`ruff-format.*`|
|Node前端逻辑|exit0|`node.*`|
|git diff --check|exit0，空错误输出|`diffcheck.log`|
|统计/图/包/媒体核验|exit0；900raw/90warm、四图渲染、28格SHA、402/404字节/CRC、185.4sec|`assets_check.py`、`assets-check.json/.log`及`fig-*.png`|
|migration/secret模式/镜像/capture SHA|exit0；18migration无改，secret模式零命中，11截图SHA吻合|`safety_metadata.py`、`safety-metadata.json`|

### 本轮装配失败全部保留

1. 首次错误选择threshold镜像跑全非PG，`test_cosm2_x402_demo.py`收集缺web3，1error；该镜像本来不带x402依赖。改用已有固定x402镜像完整非root重跑，不改代码/skip/依赖。`nonintegration.*`保留。
2. 历史x402 probe首次忘挂它硬编码的`/evidence`，8fail/5pass，均为证据输出FileNotFoundError；补自有挂载原样重跑13pass。`x402-historical.*`与rerun分别保留。
3. 首次native owned-replica未复制migrations，原Launcher不能得到有效result；补齐相同字节migrations后同原Launcher0/6/6。该失败来自reviewer装配，不是候选缺文件。首轮`native-launcher.json`与`extra-runs.log`保留。
4. assets脚本最初假设ZIP带顶层目录，实际成员根为`benchmark/...`；修正review脚本后404成员全等，未改ZIP。UI脚本首次按钮名称不正确，后续实际按钮确实产生771b071e…六例成功，但附加UI捕获的state仍处running/saved-result，`ui-result.json`的自动passed不能作为live UI证据，明确以`ui-correction.json`撤销该推断。未将其当实现缺陷或冒称本轮重新录制成功。

## 7. 未独立重跑与证据等级

正式900基准不重跑（主控允许），仅独立逐行/统计/来源/源码计时边界核对。最终三分钟视频不重新录制，仅ffprobe实际检查、截图与视频120秒帧肉眼、manifest/terminal/result/UUID/SHA关联。原始G1/B6先后门为历史日志核对，当前行为另外实际跑。原captured UI current-run证据不等于本reviewer重新现场采集；本轮真正重跑的是native Launcher/真实server按钮后的业务输出。

B9恢复中的响应丢失是测试装配ConnectionError注入（含前/后真实独立DB commit），不称真实断网；旧x402 abrupt process probe确实子进程退出/新进程恢复。当前阶段未要求生产TLS或远程CI，不运行、不据此宣称生产可部署。未重新验证旧A3四万次或全项目所有PG模块；本轮完整新增COSM2及受影响原execution/threshold/x402回归覆盖如上。

## 8. 阻断及最小补正

|Issue|严重度/状态|位置、触发与证据|必须补正与复验|
|---|---|---|---|
|COSM2-R1-001|P1，阻断，OPEN|`tests/integration/test_cosm2_gateway.py:275–283`及`:286–304`两C10都`expires_in=1`；全组首项在279签名准备被authz_domain.py:67拒AUTHZ_EXPIRED，根本没跑到send/401断言。`integration.xml/.log`确认；独立延迟probe证明跨这一秒即可稳定触发。|给签名准备充分、可验证的有效窗口，先证明拿到有效签名，再确定性等到其真实deadline以后发网关。最终DB时钟用仍在AS/AGPoP有效区间的固定off-lock clock，并证明请求时真实DB已越批准deadline，强制保持401 EXPIRED/零效果/零预算。不可改生产时钟、不skip、不把AUTHZ_EXPIRED当gateway401通过。至少原完整552组及非root整体、受影响C10多轮在并行环境新冻结fresh复验。|

单跑10绿仅证明该缺陷依赖边界时机，不能把最初失败归零。独立5秒有效窗的实际过期header探针通过，所以当前缺陷定位为测试时序可靠性/必跑覆盖闭合，不捏造生产过期绕过。没有要求为该失败改成熟验签或授权安全逻辑。

## 9. 资源、结束指纹与STOP

随机owner、PG/network完整ID和最终清理结果见`owned-resources.json`、`cleanup.json`。只创建自己的PG16 tmpfs/无发布端口实例及bridge网络，只有TEST DSN通过0600 env-file进入自有runner；没有复用root旧PG、没有普通业务DSN、没有inspect/kill其它容器或服务。网关schema与下游数据库由真实fixture分离创建/按marker销毁。原生Launcher另外自建随机label资源并自行完整ID/owner清理，原件含resources_remaining=0；本reviewer仅核对已知token。

全部已启动检查已结束。结束独立全量核验2021/2021 SHA匹配，manifest SHA、branch/HEAD与开始完全相同，零候选字节漂移。`fingerprint-end.json`、`git-status-end.txt`、`cleanup.json`为原件。自有PG16.15 catalog最后核对测试schema/临时DB/ROrole为0|0|0，PG与network按完整ID+owner删除exit0，全部own owner及三个native Launcher token资源均0。runner.env/pg.env已删除，自有代码副本逐文件SHA索引后删除重复源码，仅保留其公开结果；未发现遗留share.json/private key。全部公开log/json/xml/text/markdown再次做私钥PEM/带密码DSN/完整JWS/share_hex模式扫描零命中。自有失败原件保留且SHA可得，见`evidence-index.json`；这不改变历史worker未脱敏原bytes/SHA不可得的事实。

本报告已完整读回，矩阵与唯一OPEN阻断一致。当前总体结论**NOT_ACCEPTED**，候选不得发布为已接受。请保留本报告及失败，针对COSM2-R1-001最小补正后重新冻结，由全新reviewer实施完整验收。所有reviewer活动STOP，外部资源与秘密文件0。
