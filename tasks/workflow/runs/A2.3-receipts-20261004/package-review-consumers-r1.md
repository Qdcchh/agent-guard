# 独立审查：PACKAGE_REVIEW／A2.3-receipts v3／consumer-r1

## 1. 结论与范围

2026-10-05，Asia/Shanghai。本轮为 NEW 独立 `PACKAGE_REVIEW`：完整 v3 **PACKAGE_READY**；`task-cli-v1.md` **PACKAGE_READY**；`task-https-v1.md` **PACKAGE_READY**。没有确认的业务、接口、容量或所有权阻断项。两个消费者实现及联合验收尚未完成，完整 A2 **NOT_ACCEPTED**，项目仍 PARTIAL。本结论不关闭待最终验收的容量、格式问题，也不代表实施行为 PASS。

最新真人范围是“验收完A2规划完A3就停吧，太慢了实在是”。本次仅继续完整 A2 实施和独立验收，并交付可接续的 A3 计划；**不得实施或派发 A3 业务**。旧正式包初始 PENDING 标签、旧连续 A3 授权及旧门记录保留为历史，不能覆盖最新限制，也不构成要求重复同包审查的理由。

仅写本 reviewer 自有证据目录；未修改候选、正式任务/报告/问题台账、Git、共享库或其他成员文件；未开 children，未创建业务资源，未执行实施测试或提前接受。

## 2. 独立会话与候选版本

Reviewer：`/root/a23_consumer_package_r1`；owner `a23-consumer-package-r1-20261005`。请求 `gpt-6.1-sol / xhigh`，有效后台 model/effort **UNKNOWN**。仓库固定为 `/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`，另一个父目录 Git 未使用。

分支 `codex/a2.3-receipts`，HEAD `138c08a3496eefb6ef2ceca0d694290dcb95c642`。实际冻结 `consumer-package-freeze-v3-r1.json` SHA `29c60e81da8148f18c86d1d66fe670de163023a66a05c9d5be9133ca6e5fe757`，340 候选。独立开始/结束核查完整 status、index、staged/unstaged diff、每文件 bytes/SHA/mode，均一致；自有差异原文保存为 `git-staged.diff`、`git-unstaged.diff`。

| 绑定 | SHA-256／证据 |
| --- | --- |
| task-v3.md | `74fe26e5c190050dad73eced000b7dc74335c28a2ac2f84c7927efa697ca4098` |
| requirements-v3.json | `3821d592d6e66834cee070a356f0a1e721079b5f0a170e9e84fb59ab7f7d4fd6` |
| node-bindings-v3.json | `c2e741993c050d6f13808940f209b8ff188c1c263e50b451f5c63e40d9625c6b` |
| task-cli-v1.md | `03766bafd8625d68019eac9d89c263c278ac1e6524aba4ba0a7838a6b76a1cd3` |
| task-https-v1.md | `53332cdaff0ef52e56d1351787c161b21a1ea2e3fd045a9336757d23cd8c0532` |
| 实际 core API | `2bd9a6acbd8b615fb5feff5254bb5576d336e040fef5fc2c6c03b64e44a3d93e` |
| 最新真人限制 | `efc2e374c90090421d0b0c01699f3a3079b35e30d1a7b1483a8b39ed07efb90e` |
| Git 起止完整状态 | `start-audit.json`、`end-audit.json` |
| 文件和只读依赖 | `candidate-audit.json` 340、`baseline-v3-audit.json` 338、`common-baseline-audit.json` 340，全匹配 |

读取 AGENTS/AGENT、原 setup workflow-contract、reviewer/implementation 契约与模板、current-policy/context/issues、HANDOFF、原 A2 任务、接口/安全/验收文档、当前完整任务包及所有绑定。文件完整读取入口和字节指纹为 `source-read-manifest.json`；不以 owner 成功摘要替代真实源文件、测试断言及 raw。实际 core 原生 FINAL STOP 已由主控收到，`core-quality-r1-controller-readback.json` 记录实际停写、范围和资源；本轮另直接核源码和历史证据。

## 3. 实际检查的实现与调用链

直接检查 `receipt_publication.py` 的 `ReceiptPublication`、`ReceiptVerifier`、`InternalPublisher`、keyset `pending_page`；原始材料 `validate_original_tx` / `scoped_trust_tx`；`PermissionSnapshotProvider.load/load_tx/_from_records`；`VerifiedExecution.accept_response`、`AuthorizedQuery`、gateway config/factory/endpoint；receipt projection、结果严格 schema、账本 delta codec、RFC8785 编码、SM2 JWS、私有文件 primitives、ledger 接受及终局周边代码。185 个源码文件解析 AST，继承绑定 878 个函数的整文件 SHA、实际断言 source segment 均匹配；源码/断言和 raw 具体绑定保存在索引中。

同一个原 permission 校验体被 `load` 与 `load_tx` 复用，原 `load` 的连接关闭时序保留。历史信任由独立验证的完整 AS 链、不可变 DB 原始上下文和精确 `(tenant, client, kid)` 登记选择，使用共同历史窗口；每操作新建 trust，不按全表 kid 扁平化、不用当前 DID 替代历史、不共享可变 trust。新 GW signing kid/SPKI 与 AS/holder 的角色分离保留。

终态材料由真实数据库投影，检查完整原 token/proof/request、三层路径、phase/seq、各祖先 delta、结果与原 quote 绑定及全部 17 receipt claims。publisher 仅在 outbox 事务中改 `receipt_status/receipt_jws/signed_at`，签名前后验证，READY 再读保持同一签名/时间；不重新终局业务。查询和重复 invoke 的 publication 捕获发生于现有最终授权/DB 时钟前，同事务 proof 回滚、序列化重试局部状态清除及未知错误保留 500。HTTP composition 只含公共 receipt keys。

累计 core15 是**真实已停写的只读依赖**，不追授 core15 写权；本轮新消费者写权只有各自 exact 路径。`core29-source-binding-audit.json` 对全部 29 个 core 节点的实际 symbol 行号/AST/SHA 和局部原文绑定逐一核查。

## 4. 完整需求与验收矩阵

完整矩阵随报告交付：`parent119-review-bindings.json` **119 行／112 个运行义务**；`local88-review-bindings.json` **88 条局部断言／41 节点**。每一 parent 保留原 behavior、run flag、must_assert、继承真实函数或精确局部/G1/G2 对应；每一 local 保留原文、planned file/function、owner、完整有限 case contract、父 ID 和源码/raw 索引。v2 原 behavior/flag/assert 全等；A2.2 原 95 项 behavior/flag 不变；两个子包内嵌节点 JSON 与正式 phase 子集逐字结构相同。

证据标记严格分开：本轮静态查证；既有日志核对；消费者 `PLANNED_NOT_IMPLEMENTED_NOT_RUN`；完整独立实施验收 `NOT_RUN`。索引中的 READY 是设计结论，不是测试 PASS。core29／59 atoms、CLI7／15 atoms、HTTPS5／14 atoms，合计 41／88，均无漏项。

## 5. 专项、容量与历史回归

**N021 公共 64 KiB ±1：合法生产终态当前不可达，理由成立。** 按实际 schema/guard、UUID hex、RFC8785 escaping、17 claims、受控 header/SM2 signature、四工具及 refusal 重新推导，READY 保守上界为 **54872**，PENDING **52155**。order/notification/request/document READY 分别 54872/3361/2947/2949；refusal 全工具不超过 5012。此为保守上界，不虚称实际合法最大值。不得再用已失效的旧 nonledger 聚合 64 KiB 或 65235 相消；本轮没有使用该前提。实际生产 publisher 采用规范 JWS 生成路径，非法人为 padding/损坏原件不纳入合法生产上界。

**N031 outer 1 MiB ±1：在保留的严格九字段和每 component 原 codec 上限下，合法包不可达。** 九个值每个最多 65536，加精确外层 key/colon/comma/braces 140，总上界 **589964 < 1048576**。SDK 已移除旧 nonledger aggregate 64 KiB 早拒，按每个 canonical component（ledger 用原专用 signed-delta codec）计算真实 outer 大小；祖先1..3/JWS16384、depth/node/string、全17绑定与真实验签没有放宽。不存在“合法 pipeline 已到 codec 边界”的主张。

仍保留原 exact codec 65536/65537 和 outer helper 1048576/1048577 数学边界、非法 component 在更早 guard 拒绝、公开 oversize503/proof rollback 及全行族无效应断言。真实 AS root+两次 exchange、256 SKU 短值和 width12/16/17 合法 source/wheel、原聚合失败的 source/wheel raw 与原测试均有绑定；独立全 A2 验收必须再实跑。独立推导及源码前提见 `independent-bounds-audit.json`。

三类真实 PID 窗口计划不混用：core 独立 publisher；CLI 实际 receipt_worker 的 sign→commit、commit→reply loss；integrator 完整 P18。实际 core 测试使用 PG/backend/advisory 观测、SIGKILL、独立新 PID 和独立连接确认 commit 后再丢回复，不能以 exception/finally 代替进程死亡。并发/恢复要求有 barrier、全 futures、每组规定轮次、每祖先四计数和所有 ag/DS 行族；等待超时必须 FAIL。

原 A1 U1/P1–14/F1–5、原 probe/非零升级、A2 历史482、B 原等价250、oracle60、CTX16、A22 两问题和短窗回归均在 G1 中保留。README 原 AS/GW 两流程与新增 publisher 流程同时保留；14 SQL、checksum/PEP517 原锁及 source/noneditable-wheel provenance 保留。真实短窗受父 exp 和 DB 时钟收窄、1秒 proof、5依赖×5deadline×正负×10=500 每模式；本轮读回 source/wheel 共1000记录，未把计划数写成本轮通过。

## 6. 本轮独立实跑

包审未运行实施行为测试、未导入执行产品、未创建 Py3.11/PG/TLS 等业务测试资源。仅执行只读 Git/文件 SHA/mode、stdlib AST/XML/JSON 解析和独立容量数学计算，并只写自有 evidence。最终 `audit.py`、`close_audit.py` 均 native exit0；静态 errors=[]。不把 ruff/format、unit/integration、TLS、迁移、故障、签验或 source/wheel 既有通过称为本轮重跑。

自有校验早期路径映射失败、以及断言首行缩进和 AST source-segment 的表示差异，均在自有脚本补正并保留原日志；未改受审源码、原要求或测试预期。最终比较真实 AST source segment 与正式原断言，全部匹配。

## 7. 既有日志核对与未执行项

直接读取并核哈希、bytes、mode：**489** 个 pre-quality 历史成员、**1565** 个 quality raw/证据成员、**18433** 个环境成员全部匹配。逐 XML named testcase/status/count 解析，最终 source/wheel 各 core882、ordinary1078、affected813，全部 native exit0、F/E/S0。首轮 ordinary1078/3fail、core-source partial396/exit2 保留；partial XML 的额外无名记录不算 PASS。LONG_HEX 脱敏和封存原件的 SHA/权限证据仍保留。

从实际 `core-capacity-r1/candidate` 读取 pre-quality 三个测试文件，SHA 等于旧冻结原 SHA；独立比较 **46** 个旧 test 函数 AST 全相同。实际旧 collect **861** nodeids 是当前 **882** 真集合子集，新增21正好 N011 一项与 N014 二十项，不以最终 quality 副本冒充旧源。见 `original46-and-861-audit.json`。

上述只是既有日志/源码核对；不能替代后续完整 A2 NEW 独立119/112源轮验收，不能关闭历史待最终复核问题。

## 8. 必要补正项及台账边界

仅确认当前入口文案补正：`tasks/workflow/README.md` 第9、17、40行旧 current 段仍含“quality 待完整 core”或“连续实施 A3”的旧表述，第18行 A3 表行也仍写“已授权四段持续闭环”。最新 v3/runtime/latest-human-limit/context 已绑定实际 core STOP 和 A3 仅规划。主控已明确将在本 reviewer 原生 STOP **之后**修正当前指引；本轮补充指出同文件第18行须同步。freeze 期间不得改。该文案 delta 不改变 business/package/ownership/acceptance，不需因此开启同包无实质重复审查。消费者不得修改此入口或据旧段开展 A3。

容量与格式仍 `FIXED_PENDING_FULL_REVIEW`；历史本轮所见 issue 的原严重度、原失败和停止报告不追改。本包审不自行关闭完整实施缺陷、PR 审核或旧运行门。

## 9. 隔离、所有权与结束核验

CLI exact4：`receipt_config.py`、`receipt_worker.py`、`test_receipt_worker_config.py`、`test_receipt_worker_process.py`。HTTPS exact3：`a23_https.py`、`test_gateway_receipt_https.py`、`a2_receipt_demo.py`（完整相对路径见 ownership/local 索引）。各自独立 owner/evidence/Py3.11/PG16/TLS 随机 TESTDSN，清空普通 DSN，独立 GW/DS 事务域、ports/CA/cache/venv/PID；不使用 sibling 活动树、不读取未停写半成品。immutable `consumer-common-baseline-v1` 的340成员及只读444/555权限全匹配；只能在自有执行副本 overlay 自己 exact 路径。共同基线控制文档是历史快照，当前授权和实际派发 freeze 由主控 live 正式记录绑定。

最终整合必须等待每名 writer 原生 FINAL STOP、清理与范围核验后，由主控把 exact **29** 唯一联合路径移交 sole integrator，随后完整自查、冻结全部候选，再 NEW 独立实施验收。原文历史28/conditional29或旧 proposed/API not-frozen字段不能覆盖顶层当前实际 core15/API 绑定及 sole29，不扩张消费者写权。

本轮业务 resources created=0、children=0；双 `owner`/`agent-guard.owner` 容器/网络只读查询均空。当前三个既有容器完整 ID/name 与实际 core STOP cleanup inventory 相同；无清理/stop/prune/DB 操作。起止 Git、候选340文件和 mode 无漂移，scope violations=[]。证据目录是唯一写入白名单，详见 `end-audit.json`。

## 10. 交主控的动作与原生停止

完整读回本报告、119/88 索引、source/raw/environment/history 清单及起止范围证据，保存本 NEW 包审结果；在本原生 FINAL STOP 后完成 README 第9/17/18/40行当前文案 delta，核最新授权，按同一 v3/API/不可变基线分别派 CLI4 与 HTTPS3 独立 worker。禁止消费者改 core 或 peer 路径。之后 allSTOP→sole29 整合→NEW 完整119/112独立 source/wheel验收；不得以本包审或 core 自查设置 full A2 ACCEPTED。完整 A2 接受、A3 计划交付后停止，不开展 A3。

最终自有 `evidence-manifest.json`、`readback.json`、`native-stop-final-r1.json` 记录完整产物读回和停止。交付原生 FINAL STOP 后，本 reviewer 不再写候选或自有证据。
