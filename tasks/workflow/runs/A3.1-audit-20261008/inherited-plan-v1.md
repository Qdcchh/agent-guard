# A3.1 inherited 完整必跑计划 v1

本文件与 `inherited-bindings-v1.json` 是正式建包的静态绑定，不是 PACKAGE_READY、collect 结果或本段通过。A3.1 当前全部 **NOT_RUN**。实际前段依据是完整 A2 的 acceptance.md 与正式 review-r2.md；r2 SHA256 为 `b3b6dbbf591ee672552674df56364969e8ce6173551f501a74097e2c5705bece`。A2.1/A2.2 接受与复核、现行授权/角色、已接受 A3 规划及 audit-contract 已全文读取绑定。后台有效模型/档位仍 UNKNOWN。

## 完整范围与查阅

保留 requirements-v3 的119个ID/behavior、112个 independent_run_required、269条 must_assert逐字原文；保留P01—P21以及另列P15-CORE/P21-HTTP的局部责任，不能用23个P前缀行冒充23个原P。planning requirements 的 inherited_A2 与原119四元组精确相等。另携带 A3.1新增22父项/21运行标记/95原子原文、原30目标及逐目标未来归属。

机器文件按索引去重：`requirements`保存原文及269义务ID；`obligations`绑定真实r2的具体函数、case、helper作用范围；`actual_current_bindings`将979个实际接受callable ref定位到当前实际文件/SHA；`file_inventory`保存完整读取后AST的函数行、函数/AST摘要、断言、raises、调用及原parametrize表达式。当前测试、fixtures、77产品Python及历史/增强/native runner均读取解析；静态类/Protocol只作静态定位，不造运行case。实际读取文件摘要独立保存在 `read_bindings`。

`historical_cases`保留44份实际XML中的12520个历史case结果；`historical_case_sets`按摘要去重精确有序case集合；`historical_assertion_binding_sets`去重实际旧断言/helper定位。引用集合时展开原列表，不使用集合计数代替覆盖。`historical_runs_and_fresh_run_obligations`携带真实命令形态/旧exit/XML SHA与新owner重绑门。全部旧caseID仅是**历史A2**观察，绝不是本轮A31 nodeID或PASS。

原41 nodes/88 atoms是A23局部责任；95旧 inherited entries是A22继承。两者均不足以证明当前119/269完整运行映射。此次以实际接受的semantic269、personal119及source-assertions为主索引，并保留41/88 atom-specific补充责任；所有原义务并集必须在新完整运行后逐项重绑。当前979引用的文件SHA与r2实际接受绑定无差异，不能据此继承执行通过。

## source 与 fresh 非editable wheel 必跑

sole integrator与fresh独立reviewer分别完成以下全部组；新冻结源码、新owner资源、新venv/干净不同cwd、完整原命令记录/日志/XML/SHA/exit。下表数字是**A2实际接受事实**，不是A31目标计数或先验通过。A31按真实collect确定数量，包括新增节点；无故漏case/skip/error/异常归类不能通过。

| 原生义务 | A2 source事实 | A2 wheel事实 | A31必需动作 |
|---|---|---|---|
| 全普通/tests，排除integration |1185P exit0|1185P exit0|完整普通含docs/crypto/SDK/private配置，不仅audit目录 |
| 全PG integration |2810P exit0|2810P exit0|完整真实PG/TLS、独立事务、全部原并发/恢复与新增journal路径 |
| 精确deadline grid |500P exit0|500P exit0|完整5依赖×2正负×5时限×10轮真实锁等待 |
| 增强完整组 |487P exit0|原484P/3F exit1；原407未受影响PASS＋原受影响模块新完整80P exit0|重新跑完整增强487语义并集，保旧3F及其触发/参数/观测；本段不得预设拼接旧绿 |
| A1当前/原invariant/root rebuild/升级 |67普通/87PG；4P＋1P；原upgrade1F，等价1P|同范围|保持原U1/P1—14/F1—5、旧非零升级和明确等价，70为旧摘要误计 |
| A2历史原组 |482P|482P|全部原运行义务，10轮与实际全效果比较 |
| B历史原组＋等价 |原221P/25F/4E；等价250P|同范围|原失败真实保留并分类；等价保全部安全语义/仅已审有限适配 |
| 独立oracle/CTX/变体/边界 |60 oracle及完整CTX16，18 formal/6 corrected independent/2 escaped/2 noncanonical/2 public boundary/1 precommit|实际对应组完整|精确绑定每变体参数及实际故障层，保early独立5P1F编码器失误 |
| README、AS/GW四工具、publisher CLI、demo、SDK、interop与SQL14 |实际native命令/退出/观察|实际native命令/退出/观察|独立真实命令及子PID/import来源，非局部SDK/wrapper替代 |

普通命令形态为新解释器 `-m pytest tests --ignore=tests/integration`，PG为 `-m pytest tests/integration`。精确、增强、历史、oracle及native入口按机器文件中真实run形态重绑。上述是未来授权后的命令计划；此worker没有执行collect、pytest、ruff、安装、DB、容器或旧builder。不得直接运行旧命令里的container ID、/e、旧venv、owner、DB或ports。

## 精确时限与增强失败的当前可达触发

原 `probes/test_precise_deadline.py::test_reviewer_precise_final_deadline_code` 的实际decorators为 dependency={outbox,projection,key-lookup,source-load,deferred}、expired={False,True}、deadline_kind={proof,token,root,mid,leaf}、round=range(10)。这些是从实际探针AST取得的有限值，不是计划标签。依赖等待后在真实最终数据库时钟重新判断；正例释放后仍fresh，反例正确EXPIRED且全部事务事实不变，不用mock clock、延长TTL或sleep猜竞争。

增强 `fresh-probes/test_r2_real_second.py::test_real_root_cross_second_two_children_and_persisted_deadline` 实际 window={root,mid,leaf,token}、positive={False,True}、round_id=range(10)，共80；完整source/wheel模块真实SHA均为 `2c8eb9b020b4a0fae841fb3174bbb167c57938cd7ecc9c84cc4533f9a0729a4f`。保存wheel原3F的原caseID、class、参数和outcome及新完整80的独立caseID；新80是替代受影响整个模块，不只是重跑3例。r2判定依据为真实wall/monotonic间断、原407不受影响与新80逐case结果。物理原因及第三次原503的精确PG cause仍UNKNOWN。A31若重复此类失败必须保原件、即时记录明确backendPID/实际cause和wall/monotonic，不能改assert/TTL/skip以造绿。

其他增强原可达入口也必须继承：完整zero-effects/status与late dependency、实际public permission controls、query dynamic effects、response schema/bounds、所有TLS child import sources、compound拒绝、真实PG serialization（failures={1,3}×10）、gateway SIGKILL、trusted-material与boundary probes。各函数实际decorator/断言/SHA已在机器文件保存；并发必须观察独立connection/backendPID/barrier及child异常/exit，不把固定round参数当有效竞争证明。

## 旧失败、等价与native过程

`historical_original_equivalent_outcomes`保存原A1失败、B原221/25/4和5份等价文件的exact_diff/SHA。原始脚本与等价脚本分别保持独立路径。原失败触发包含旧registry/谱系、非零迁移、旧DB名/环境契约等已接受分类；A31必须用当前真实源/API核差异，不能把原组重标全绿、删除原assert或盲目使用历史run label。同类owner/资源适配只改自有装配，标准或新migration导致的新差异先审正式包。

原A2 core、publisher direct、gateway actual CLI与README真实SIGKILL窗口继续必需：在真实持久PG观察sign完成/UPDATE或commit等待、accepted到DS/terminal各窗口，原PID确实死亡，不同新PID在同DB恢复；无finally修复或替代business key。保护原budget/祖先四counter、operation immutable facts、event/event_node seal、lease fencing、唯一outbox/PENDING及三publication字段、first/retry/query evidence原文、完整DS effect/intent/result/refusal。signed终局历史校验不能改成当前quote/revoke/expiry或DS读取前提。

native README/SM2/SQL14脚本当前实路径、SHA、函数及真实旧command记录已绑定，仍需新owner重绑；字面CLI原公开配置、CA/SAN/HTTPS/privateFD/20s与15s时限保留。旧Desktop bind拒绝FD根因UNKNOWN，原生/tmp UID501私有0700/0600适配按实际新环境复核；不得以pathname stat或trace成功声称已解释旧失败。缺失observer末exit不能补造0；停止/资源余留用本轮真实native证据核验，另有SIGKILL动态义务不可由资源清单代替。

## 14 SQL的实际源绑定与A31回归门

`sql_inventory14`完整列出当前raw-source SHA、大小及原registry universal-newline-normalized SHA：common001—003、execution004—006、authorization004—010、infrastructure/lineage001，共14。授权历史不存在001—003，audit001尚不存在。当前LF文件两种SHA一致，算法仍分列；_discover保registry规范换行摘要，并独立raw摘要检查执行前TOCTOU。旧sql/checksum/filename/applied_at与_v2 completion floor不改。

当前 `ledger/migrate._discover`（53—76）、`apply_migrations`（112—153）、`lineage.apply_bundle_migrations`（435—495）以及 `_V2_COMPLETION_FLOOR`实际代码已读取。A31新增execution007依赖execution006＋authorization010，只由显式bundle协调器执行；default standalone001—006与custom目录旧完整性门保持。现空库初始化循环把全部common/execution写入legacy registry，正式实施必须显式避免将新增007在auth010前顺带执行。新增GW完整qualified库存为15；独立audit001在另audit DB，不是GW第16。

`tests/fixtures/isolation.assert_owned`173—188和reset_state191—201实际当前先核namespace marker，再精确表集合TRUNCATE；A31仅在已核owned范围扩reset closure，不能删guard、disable trigger、session_replication_role、扫ag_%或runtime授DDL/TRUNCATE。旧无007分支保持。新stream/head/bootstrap/pending必须完整重置且fresh genesis seq1；若guard不支持安全owned reset，需新精确namespace方案和包审。

实际迁移回归以当前test_migrations、test_a2_migrations、test_lineage_migrations每函数/参数/断言绑定为入口，保A/B空库/非零升级、坏checksum/TOCTOU/filename、unknown/partial lineage、原applied_at与依赖拒绝/二次幂等；source/wheel/不同cwd与每native入口核真实库存/哈希。PG16为已观察基线；PG14支持或显式拒绝必须按实际能力确认，不默认声称兼容。

## A31新增与旧回归影响并集

新增原文在 `A31_new_requirements_original`，没有伪造新实际node。正式包还须消费planning test-plan的A31 finite case责任并在实施后绑定collect结果。

| 新增范围 | 旧回归直接影响 | 必需补充观察 |
|---|---|---|
| A31-01—07同事务journal/clock/fence/锁序 |原P01—21、CKPT1六义务、B09/B11/B12/B14/B15、A22 query/freshness/races、A23 publication |原全状态＋journal/head/bootstrap/delivery，成功仍可达及故意漏线拒绝，最后clock/fence在新等待后仍真生效 |
| A31-08—10 bootstrap/迁移/coverage guard |WF-A1、BR04/05/08/09、B20、A2非零升级/ledger/evidence |历史非零保全、原14指纹、auth010→007依赖；bootstrap不伪造启用前事实，未知/缺失raw明确gap |
| A31-11—17独立checkpoint/audit service |B01/02/10/13、A23 key/trust/rotation/crypto、WF-resource/provenance |新typ真实SM2，独立权限/DB/TLS/key；原sign域不变；真存前/后死亡、新PID、原JWS去重/history/pin回滚 |
| A31-18—20 delivery/ACK/history |P04—14/P18、A23 CLI/concurrency/crash/immutability |encoded完整body限额、immutable pending、网络外短事务、晚ACK不回退、不凭latest跳cursor、完整previous JWS链 |
| A31-21＋S01 |119/269全部、41/88局部、30goals |S0→S1→S2STOP/freeze；真实AS/GW四工具到operator/register/delivery/reader观察pin；辅助状态不擅增门 |

以上关系是影响面，不声称旧test已覆盖新增journal/checkpoint原子。全部新增race/fault/crash参数10round；普通codec无需无理由10轮。所有父项按原子及native义务UNION闭合，不取代表节点计数。新主状态journal/bootstrap/checkpoint/delivery不在旧31ag/3DS oracle中，必须明确扩完整观察；跨GW/DS/audit不声称同一原子快照。

## 正式运行绑定门与停止

包审前静态包可使用真实旧函数与有限原参数，尚未实施的A31函数不存在是明确实施后门。实施STOP后必须实际collect source及fresh非editable wheel，保存精确parameterized nodeIDs/模块来源/断言/分支作用、runlabel/command/exit/raw/XML/DB观察及SHA，再由fresh独立reviewer完整实跑。任何新测试缺失、旧runner兼容未知或新增guard导致成功不可达，均不得提前PASS；先更包或补正精确责任。

新wheel与源码逐文件/SQL原字节一致，全部父/子进程实际import路径；原accepted wheel SHA仅历史。新operator/reader的外部public信任材料和CP必须独立，UNANCHORED本地一致性不能升为独立审计，未锚tail/latest未知、bootstrap之前legacy gaps和下游真实效果局限继续明确。30目标须按实际原node/command/效果逐目标映射；A3.2—A3.4剩余导出、部署、三holder、规模/消融/材料仍NOT_RUN，A3.1通过不得标项目完整接受。

此worker仅写本两份正式包文件及独占ignored工作证据。已全文读回JSON/Markdown并核摘要；无业务实现、collect/test、DB、容器、安装、Git或子agent。原生STOP后由主控冻结交新独立包审，不能用本worker表格替代独立审查。
