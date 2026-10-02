# 独立审查：IMPLEMENTATION_ACCEPTANCE／A2.1-core／NEW r7

## 1. 结论与范围
- **结论：NOT_ACCEPTED。** 当前31项：**27 PASS、4 FAIL**；全部28项运行类义务均亲自执行，没有用历史日志替代必跑验证。
- 日期／时区：2026-10-02，Asia/Shanghai；结束绑定核验时间 **01:13:48+08:00**。
- 当前代码阻断：**A21-R2-SNAPSHOT 残余——订单参数 quote_version 仍按前缀匹配接受非法版本**。DOC-CKPT1-01亦未完全修正，WF-DOCS-REPORT不能PASS。
- 仅评价 **A2.1-core／检查点二**；完整A2／项目仍为 **PARTIAL**。完整P15真实授权、P16/P17真实验证、P18真实签名、P21真实HTTP仍属后段／B依赖BLOCKED，未计完成。
- **不允许进入A2.2/A2.3/A3；不授权Git提交、推送、PR、合并或发布。** 未修改受审源码、正式测试、标准、state、issues或报告。

## 2. 独立会话与冻结绑定
- 根目录 **R**：`/Users/qdcc/code/密码技术竞赛/agent-guard`；宿主仓库命令均以R为cwd。
- 模型：**openai/gpt-6.1-sol**；本轮配置推理档位 **high**，历史文档xhigh不覆盖它。API未暴露当前真实session／Task ID，须主控绑定本次调用记录，未借用历史ID。
- 真人授权与正式包/state一致：`ses_f0ac0e676ffecn71p6Ww7zaqQq`／`msg_0f54148e0001ZW7yCMdK0TE97F`，仅A2.1及同阶段补正；主控已核原消息，本轮未自行授权。
- 分支／HEAD：`feat/a2-execution-gateway`／`b120c7cf5ec0eafb18305d1207c36dd11655b324`。实际 **5 tracked修改**，staged空、无删除／重命名；完整untracked清单保留。
- 开始／结束独立重建 **101项snapshot**：**`17a3b2c7a61ccc82348de5fc6de6840d8f37861b98c6851a45983981d524f3f5`**，manifest、执行副本、Git与控制输入均一致。
- 契约逐文件重算及排序摘要：**`24b2bf395b9d4ee8b2e754bf85e443dd25f5315e6b4098772c98984bb671c045`**；worker报告hash **`250c3e44c1d44573fe2a3eb5a8583cc5b7def27b3587abc6fd81e6217122a0cc`**，仅作声明索引。
- Writer停写依据为父任务确认及state记录；本轮无漂移，不夸称查询过调度器。沿冻结排除规则，未新增源码／正式测试排除。
- 证据根 **E**：[artifacts/workflow/A2.1-core-review-r7-a93e6b42/](/Users/qdcc/code/密码技术竞赛/agent-guard/artifacts/workflow/A2.1-core-review-r7-a93e6b42/)。
- [evidence-index.json](/Users/qdcc/code/密码技术竞赛/agent-guard/artifacts/workflow/A2.1-core-review-r7-a93e6b42/evidence-index.json) SHA256：**`6f39e9bcaa8598350a30cf9b626a9131b188128124dc818b3bc73915bf8af88b`**；含完整31行、命令/退出码/JUnit计数、证据hash、关闭项及阻断项，已读回解析并核引用hash。

## 3. 实际静态检查与调用链
- 全文检查正式task-v1、correction-r1/r2/r3、两份包审、完整review-r2/r3/r5及issues；workflow合同/stage/state-guide/模板、AGENT、原A1/A2任务与历次验收、两轮ckpt1、三份原docs、README及当前报告。
- 检查完整tracked diff与相关untracked实现：contracts、ledger调用方、execution service/store/worker/receipts、params/catalog/policy/results/downstream、001—006、隔离fixtures、核心/报价/恢复/并发/迁移/拒绝/补正测试、依赖/CI/Compose。
- 追踪 `accept_invocation→params/policy/catalog→_accept_checked→A1._accept_tx`：三条A2接受路径均走checked；实际EXISTING在动态校验/proof/意图比较后，以同conn读取材料、提交前验证；拒绝回滚proof后独立flag。
- 追踪 `run/reconcile→材料验证→task→根至叶grants→operation→lease→独立下游→decide/finalize`；核验四条件租约、全祖先终局事务、不可变事件/outbox、稳定UTC iat及UNKNOWN保预算。
- **静态查证不替代行为实跑；可信fixture不等于密码验证。** 001—003、其他ledger、A1契约、依赖/CI与HEAD逐字节一致；service最小兼容获包审确认，004—006冻结hash及数据库checksum一致。

## 4. 完整需求与验收矩阵
全部31项均当前必需；P来源为原A2§7，OBL为ckpt1-r2六义务，WF为正式stage/合同。G/U=integration/unit，P=继承探针，N=独立r7，H=A1历史源码本轮重跑，SM=README，I=静态/冻结；除I外均为**本轮独立实跑**，完整函数/命令/hash见index。
| ID | 实现／测试、探针 | 必须观察及本轮结果 | 证据／状态 |
|---|---|---|---|
| A2-P01 | finalize；core::test_p01 | 唯一70000/1订单；三层预留0、结算70000/1；事件/outbox一致 | G/SM **PASS** |
| A2-P02 | decide/results；core::test_p02、refusal探针 | 同键持久拒绝才RELEASE、不结算；迟到不能成功，错键/工具保持UNKNOWN | G/P **PASS** |
| A2-P03 | 零额工具；core::test_p03、通知并发 | 0金额仍计1次；结算/释放正确，读结果固定、通知唯一 | G/P **PASS** |
| A2-P04 | worker；recovery::test_p04、entry_windows | 未提交不可见/零效果；真实SIGKILL及新PID持久恢复 | G/P **PASS** |
| A2-P05 | run/recovery；core::test_p05 | 真下游提交＋响应丢失替身→UNKNOWN保70000/1；恢复同单一次结算 | G **PASS** |
| A2-P06 | worker终局窗口；recovery/followups | kill时1单/0outbox；重启仍1单、1终局、1outbox | G/P **PASS** |
| A2-P07 | 终局事务、checked callback | 部分节点/事件/outbox/status真实回滚；callback拒绝proof回滚、重试重检 | G/P/N **PASS** |
| A2-P08 | reconcile/downstream；deadline | 查无结果不释放，迟到成功唯一；实际SQL锁自动有界超时 | G/P **PASS** |
| A2-P09 | claim/finalize；恢复/锁效力探针 | 规定10轮、fencing/旧UNKNOWN40例；真持锁环10轮及串行/异常/无进展反测 | G/P/N **PASS** |
| A2-P10 | 内部恢复／A1动态复核 | 撤销/过期/停key后恢复原意图；外部checked重试拒绝，真查询留后段 | G/P **PASS** |
| A2-P11 | params/candidate；quotes、last-miss、version-boundary | 原成本/原子好坏竞态通过；但非法版本可被解析并在对应可信集合/目录下预留 | G/P/N **FAIL：SNAPSHOT** |
| A2-P12 | decide/results；typed/outcome探针 | 完整键/工具/意图/报价/结果/effect关联；坏items执行/查询安全UNKNOWN，无outbox | G/P/N **PASS** |
| A2-P13 | 全祖先预算／混合锁；concurrency | 根/中间/次数/接受结算恢复各10轮，有界非负、无反序 | G/P **PASS** |
| A2-P14 | 独立MockDownstream；downstream/通知探针 | 同键唯一、冲突不覆盖；执行/查询无错服务认证零效果/泄漏 | G/P **PASS** |
| A2-P15-CORE | params/policy；validation/unit/version探针 | 普通负例零状态；quote_version `01`/`1x`/`1@2`等未严格拒绝 | U/G/N **FAIL：SNAPSHOT** |
| A2-P19 | migrations/material；upgrade/legacy探针 | 001/003/004/005→006合法非法七表/full registry保全；深params五入口持久隔离 | G/P **PASS** |
| A2-P20 | 001—006 guards；SQL/seal/savepoint探针 | 改删意图/证据/事件/节点/操作/路径、双终局拒绝；合法UPDATE/初写有效 | G/P **PASS** |
| A2-CKPT1-OBL01 | static→candidate→checked | 不依赖当前报价，实际EXISTING同事务验证正确；候选前版本schema仍不完整 | G/P/N **FAIL：SNAPSHOT** |
| A2-CKPT1-OBL02 | miss→解析失败→安全重查 | 自写好/坏/撤销/重放/过期各10轮，记录code/cause/DBtime/expiry及proof/预算/效果 | G/P/N **PASS** |
| A2-CKPT1-OBL03 | 完整事实/sidecar/永久防删 | 最后miss坏材料拒绝、不留proof、锁释放后flag；flag失败亦不成功 | G/P/N **PASS** |
| A2-CKPT1-OBL04 | lease四条件/UNKNOWN现场复核 | owner/version/state/锁后expiry；无接管过期拒绝，旧返回不覆盖当前事实 | G/P **PASS** |
| A2-CKPT1-OBL05 | sidecar/phase-seq/seals | 七表不改行、全部已提交事件封存；升级回滚/合法更新/owned清理兼容 | G/P **PASS** |
| A2-CKPT1-OBL06 | stored/result snapshots、receipts | 存储/结果标识严格、typed安全比较、完整原报价；稳定不可变PENDING材料/UTC iat | G/P/N **PASS** |
| WF-A1-REGRESSION | A1全套＋原探针 | 独立68 unit/78 PG，U1/P1—14/F1—5；原4＋1通过，升级等价增强保全 | G/H/P **PASS** |
| WF-INDEPENDENT-PROBES | 自写r7＋继承重跑 | 自选并发callback、重试/真DB失联、flag失败、P11时钟、typed形状、锁环、版本边界 | P/N **PASS** |
| WF-QUALITY-CHECKS | ruff/diff/full suites/CI | 检查及137/424正式套件无fail/error/skip；新增目录收集，反例失败未隐藏 | U/G/I **PASS** |
| WF-PY311-ENV | 新3.11约束安装/PG16 | CPython3.11.16、pip check/freeze、psycopg3.2.13、真实PG16.15 | ENV/G **PASS** |
| WF-RESOURCE-ISOLATION | owned资源/独立DB/schema | RO原仓库、独占新PG/下游；仅owned清理；原四容器不变，新他人资源未动 | RES **PASS** |
| WF-IMMUTABLE-BASELINE | HEAD/冻结迁移/默认A1回归 | 历史迁移及其他A1不变；获准service最小兼容，无B/HTTP偷渡 | I/G **PASS** |
| WF-DOCS-REPORT | README/A2-report/worker索引 | README双烟测通过；当前报告仍有阶段/迁移/359计数/tracked4/清单路径矛盾 | SM/I **FAIL：DOC** |
| WF-SNAPSHOT-COVERAGE | manifest/contracts/Git/copy | 101项及契约、控制输入、执行副本开始/结束一致，无观察到漂移 | I **PASS** |

## 5. 专项及历史回归
C1独占资源、C2/P11原子候选、C3八组合非零升级、C4直接SQL永久保全、C5四条件租约、C6完整快照/稳定材料均实际覆盖；版本前缀残余不能被这些正例抵消。
P04独立观察 **PID477→478**，旧exit **−9**、新exit **0**；kill前后三层计数、真实订单、事件/outbox完整断言。A1 P3/P5/P6、A2 P09/P13/P14、通知/P11/旧新终局及固定锁交错规定组均独立连接＋Barrier/Event各10轮。
原升级探针源码未改，第46行只期待`["002"]`，实际002—006故失败；当前001/003/004/005×合法/非法八组合比较非零预留/撤销/七表全行及**完整registry**，等价且更强，非迁移缺陷。

## 6. 本轮独立命令／退出码／计数
正式测试cwd为hash相同的自有`/evidence/candidate`；完整argv、缓存/XML路径及子命令退出码保存在E的`*-command.json`，不把run.py驱动exit0当pytest成功。
| 实际命令／目标 | 真实exit | pass/fail/error/skip／结果 | E原件 |
|---|---:|---|---|
| `pip install -e /evidence/candidate[dev] -c …/constraints.txt`；`pip check/freeze` | 各0 | 新约束安装及依赖检查通过，无新增运行依赖 | install、pip-check、pip-freeze、environment |
| `python -m ruff check .`；`ruff format --check .`；`git diff --check` | 各0 | check通过，**55 files**格式正确；开始/结束diff干净 | quality-*、diff-check* |
| `pytest tests/unit tests/test_scaffold.py tests/test_docs.py` | 0 | **137/0/0/0** | unit.log/xml |
| `pytest tests/integration` | 0 | **424/0/0/0**，含全部新增A2及A1 | integration.log/xml |
| A1原unit/骨架/docs；八个A1 PG文件独立分跑 | 0/0 | **68/0/0/0；78/0/0/0** | a1-unit、a1-pg |
| `python -m agent_guard.ledger.migrate`两次；结束checksum检查 | 0/0/0 | 首次001—006，第二次no-op，六版本checksum正确 | migrate-first/repeat、database-end |
| `pytest /evidence/probes`，继承320项原断言 | 1 | **318/2/0/0**；两条合法list过严UNKNOWN断言为非finding | inherited-original.log/xml |
| 最终自写`test_r7_independent.py`全套 | 1 | **92/12/0/0**，104项；12失败为版本schema/预留边界 | final-fresh.log/xml |
| 自写非版本callback/P11/typed/锁环组独立分跑 | 0 | **89/0/0/0**；版本组另跑3正例/12失败 | independent-valid、version-boundary |
| 原A1四探针／根重建／旧升级探针 | 0/0/1 | **4/0/0/0；1/0/0/0；0/1/0/0**，旧版本断言如上 | history-*日志/XML |
| README逐字Python程序，两种新空库流程 | 0 | program-first/CLI-first均SMOKE_OK；三层70000/1、1单、2事件/6节点、1 PENDING NULL outbox | readme-snippet/driver、smoke、observations |
| 冻结/资源核验、精确cleanup、结束绑定 | 0 | owned剩余0，test schema0，原四无关资源身份配置运行状态一致 | binding-*、resources、cleanup、unrelated-comparison |

## 7. 历史核对、非finding与验证限制
- r6日志仅作历史索引；借其探针源码后在**新实例重新执行**。原始320项两条list失败保留；字段相同tuple→list合法，继承及正式正例真实SETTLE，不强制tuple、不修改requirement。
- 首次自写探针14条因fixture默认生成新业务键未触发EXISTING，已在**自有源码**改为显式同键并重跑；原64pass/23fail日志及首版源码保留，9条真实版本失败未抹去。
- 当前P11同步/coded错误/DB时钟证据充分支持OBL02；**历史r5一次未知LedgerError仍无法恢复code/cause，不声称由TTL解释**，保留为历史不确定性风险。
- 实际执行PG回滚、自动SQL锁超时、SIGKILL/重启及callback中真实终止自有backend；响应丢失/无结果/坏outcome为port替身。真实断网、TLS/wheel部署、密码/HTTP及远程CI **NOT_RUN**，不冒称通过，也不额外设为A2.1后段门槛。

## 8. Issue闭环、触发与具体补正
| Issue／严重度／要求 | 位置、trigger、影响与本轮证据 | 状态／具体动作 |
|---|---|---|
| **A21-R2-SNAPSHOT／中／P11、P15-CORE、OBL01** | `src/agent_guard/tools/params.py:37,232–238`仍用`match`；`01/00/1x/1@2/1/2/1 2/1.0/1e2`及超pattern长度均解析通过。对应可信集合/目录边界中3例实际CREATED、预留70000/1、登记proof；无下游效果，未证明金融越权；E version-boundary/final-fresh及观察 | **OPEN_CONFIRMED_RESIDUAL，阻断**；改为完整字符串正整数版本检查、禁止0/前导零/尾部字符，保持既定界限；正式增加parser/接受入口负例及合法正例，候选查找前拒绝、零新增状态 |
| **DOC-CKPT1-01／低／WF-DOCS-REPORT** | `tasks/A2-report.md:5,23,36,106,111–112,128,132–134`仍引用旧ckpt1门槛、主体未开工/004未实现、359与424矛盾、tracked4漏service、漏006/results及路径陈旧；E inspection/Git与实际文件 | **OPEN_NONBLOCKING**；统一当前事实或明确整块历史，补真实tracked5/完整新增清单/55格式文件/424及可定位证据；不改冻结标准，旧报告不覆写 |
| A21-R1-LEGACY／高／P19、OBL03 | params/verify_accept_facts；原8类、深params五入口及fallback均持久flag、保预算、零下游 | **本轮CLOSED_REVIEWED** |
| A21-R1-OUTCOME／高／P12、OBL06 | service::strict_snapshots_equal/results；原字段错配、尾LF、actual dataclass坏items执行/查询安全UNKNOWN；合法list结算 | **本轮CLOSED_REVIEWED** |
| A21-R1-CANDIDATE／高／P11、OBL03 | ledger::accept_checked／service::_accept_checked；最后miss好坏各10、同实例两个同时活跃validator10、异常proof回滚/内部retry重检/flag失败/真DB失联通过 | **本轮CLOSED_REVIEWED** |
| A21-R3-TESTSYNC／中／P09、WF-QUALITY | regressions真实持锁环精确DeadlockDetected；本轮10轮观察双方Lock等待，串行/线程异常/无进展不能假PASS | **本轮CLOSED_REVIEWED** |
| LOCK／NOTIFY／CHAIN／LOG／BOUNDS／EVENT／UNKNOWN | 各稳定A21 issue保持原严重度；统一锁序、可信目标/完整链、诊断脱敏、自动超时、旧短seal/并发/savepoint、公开旧UNKNOWN40例均本轮重跑 | **七项CLOSED_REVIEWED保持**，仅绑定当前指纹 |
| A21-R5-P11-EVIDENCE／验证缺口／OBL02 | 自写确定性resource消失好/坏/撤销/重放/过期各10轮，精确code/cause/时序/DBtime/expiry及全状态落盘；未把异常catch成PASS | **当前mandatory缺口CLOSED_REVIEWED**；历史未知根因风险保留，不伪追溯解释 |

## 9. 资源与结束核验
- owner=`a2.1-core-review-r7-a93e6b42`；新PG **cd36d8b26017…**、Python **f64e53c73c29…**、网络 **7cb50bdf60d6…**；完整ID/镜像/标签/挂载见resources.json。docker-run独占资源，PG tmpfs、无公开端口；原仓库RO、自有E RW，网关与随机下游独立数据库/事务。
- 旧r6先核完整ID、实际`owner`标签及网络成员再精确清理，未复用旧库；本轮结束同样仅删除已核owned两容器/网络，均exit0，剩余owned **0**。日志/XML脱敏、普通部署DSN未继承。
- 原`agent-guard-a2-pg`、verivote两容器及 **ab-caseb-r3-pg**身份/镜像/标签/挂载/网络/运行起始状态不变，未连接其数据库。期间他人新增`ab-review-a-1002c71-pg/py`及`hardcore_bell`，已记录为**unowned并留置**，未误清理；不声称整个容器集合未变化。
- 开始/结束101项候选、执行副本、契约、state/issues/worker报告及Git一致；E中源码/日志/JUnit/观察保留，正式报告由主控保存。

## 10. 交主控动作
**原样保存本完整r7报告及index；维持NOT_ACCEPTED。** 按本轮证据关闭四项残余及当前P11验证缺口，保持既有七项关闭；仅在当前A2.1补正版本完整匹配和DOC事实索引，加入有效正式回归，停写重新冻结后fresh独立验收。**不得以424正式测试全绿或PACKAGE_READY放行；不得推进后段或Git发布。**
