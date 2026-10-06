# A2.3 core quality-r1 实施与完整自查交付

状态：READY_FOR_CONSUMERS / actual FINAL STOP。完整 A2 尚 NOT_ACCEPTED；本报告不替代后续 CLI/HTTPS 整合及 NEW 独立完整验收。最新真人范围为完成完整 A2 验收、收敛 A3 可接续分段规划后停止，不实施 A3。

本轮 requested gpt-6.1-sol / medium，effective UNKNOWN，无 children。authoritative quality-v1 独立 PACKAGE_READY 后新 owner `a23-core-quality-r1-20261005`、新 Linux Python3.11/PG16/source 与非 editable wheel 环境，未复用旧 owner 的容器、数据库、venv 或输出文件。开工完整 freeze327、历史 raw472、审查 raw17 指纹见 baseline-readback.json / authorization-read-r1.json；旧正式包 pending 标签属于历史冻结状态。

## 实际改动及接口

本轮精确 scope8，实际仅6路径变化：receipt_publication.py 相邻 SQL 字符串拆分，verified.py / factory.py 既有顶层 import 排序，receipts fixture 新 optional `public=False` 分支及两 integration 文件各一个有限补证函数。SDK 容量修复与 unit 源承接容量 STOP 候选，本轮未再改变。三格式修改完整 before/after、AST/SQL/import 多重集合及副作用审查见 format-equivalence-r1.json 与 format-before/format-after；既有861测试函数 AST 保留见 original861-function-preservation-final.json。最终 lint-final-r2、format-final-r2、git-diff-check-final-r1 全部 native exit0，未增加规则豁免。

API 17 个实际签名、模块路径/源 SHA/行号见 api-signatures-final-r1.json。累计15路径真实 SHA 与全部 candidate、锁文件绑定见 source-manifest-final-r1.json / scope-final-r1.json；它们不是15路径新写权。PermissionSnapshotProvider load 仍先关闭独立连接后原完整验证，load_tx 复用 caller conn 和同一 _from_records；scoped historical trust 按 operation 使用实际 AS signed chain、DB exact tuple/source/原始完整 context 与 SDK共同历史窗，不 flatten shared kid 或共享 mutable trust。Publisher 顺序为 outbox FOR UPDATE →同 conn 完整 projection/source/trust →真实 SM2 sign/self-SDK/17claims →仅 publication3 字段原子更新；READY 验原 JWS/signed_at 不重签。query/accept_response 的额外读取、SDK/编码/约束均在最终 DB clock 之前；原 accept/default result 生命周期不变，未知 receipt runtime 保留 HTTP500。

N011 新补证 `test_rotation_new_pending_and_bundle_self_key_never_supply_trust`：1项，真实新 PENDING 使用 new kid，旧 READY 原字节/时间不变，外部自签 unknown kid 及 bundle 自带 key 均拒绝，全部行族稳定。N014 新补证 `test_shared_kid_concurrent_current_query_cross_owner_and_trust_repair`：forward/reverse 各10项，真实合法共享 holder kid 的两 operation 当前查询，独立 backend PID/barrier、全部 futures，cross-owner403，wrong exact tuple/真实 wrong SPKI503，修复 trusted material 后同 proof200及 replay409；实际 HTTP新增 proof ref/token/proof/body 精确对应，全 ag_* 与 ds_* 行族 oracle 保留。共21个新增节点，原861保留；核心最终29绑定唯一881项加 unknown-runtime500 独立1项，共882。

## 实际完整运行

| run / XML同名 | cases | FAIL | ERROR | SKIP | exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| core-source-final-r1 | 882 | 0 | 0 | 0 | 0 |
| core-wheel-final-r1 | 882 | 0 | 0 | 0 | 0 |
| ordinary-source-final-r2 | 1078 | 0 | 0 | 0 | 0 |
| ordinary-wheel-final-r2 | 1078 | 0 | 0 | 0 | 0 |
| affected-source-final-r1 | 813 | 0 | 0 | 0 | 0 |
| affected-wheel-final-r1 | 813 | 0 | 0 | 0 | 0 |

actual-test-runs-final-r1.json 保存逐 case 原生结果、完整命令/退出/日志/XML SHA；各 collect-*.log 给出真实收集 ID，core29-local-bindings-final-r1.json 给出29局部原子、最新函数/逐 assert 行及 source/wheel 绑定，补充 helper/fault/regression 关联见 supporting-assertions-final-r1.json。所有期限组串行，无删除/skip/预期削弱、续同 grant 或改 clock/TTL。

core source/wheel 各500真实期限记录分别250正控/250负控、目标门缺失0，含 outbox/projection/key lookup/source load/deferred 及 proof/token/root/mid/leaf 原窗口；actual SQL/backend PID、签发/截止/释放 DBclock 与效果断言见 deadline500-sourcewheel-final-r1.json 索引原 JSON。旧 affected 每轮813包含原8 query wait 各10正/负共160、四AS token/root/mid/leaf窗口跨秒/非跨秒正/负共160、撤销/key竞争120、原CTX16、oversize trusted projection503/rollback2，以及 SDK/provider/轮换/真实HTTP/TLS/evidence/SM2 等全部已收集组；其运行断言由原冻结源码和实际 XML绑定，不伪造未输出的内存时戳。

真实短256与宽12/16/17均在最终 source/wheel 各完整执行：真实 AS登录/同意/root/两exchange、公开202、独立DS终局、READY发布、当前query、独立SDK与重复READY原字节/时间、祖先四counter及全行族效果。宽16/17原组件仍分别合法（source62583/65145、每JWS<16384、request/result/ledger<65536），旧 nonledger编码实际67058/68938、新九字段outer68262/70142均通过；宽12旧59550/new60754通过。actual capacity/components 原 JSON按两 run前缀保存，绝不以 schema padded object 当真实链路。

历史真实失败不删除：core-source-r1 是覆盖补证授权后的安全 SIGINT INTERRUPTED / native exit2，partial396 PASS不算完整轮；supplement smoke21 PASS只是局部结果。ordinary-source-final-r1 为1075 PASS/3 FAIL/0 ERROR/SKIP，macOS bindmount umask0777 权限语义失败；umask-filesystem-probe-r1 真实 mkdir errno13 exit1原件及 r2 对照保留。r2同 euid501/parent0700/umask0777显示 bindmount拒绝而 Linux-native写/读0600与新目录000通过，仅切 OWN TMPDIR到自有容器原生目录，完整 ordinary source/wheel r2各1078 PASS，不改候选/时钟/权限预期，不复跑未受影响的已通过core。owned supplement lint首FAIL与修复全ruff日志保留；原历史容量/核心失败 raw472只读不变。

## 容量边界和来源

public-envelope-bounds-final-r1.json / bounds_final.py 以最终15 SHA及实际 encoder/result/SM2/UUID/query/projection源绑定。kind=CONSERVATIVE_UNREACHABILITY_BOUND_NOT_LEGAL_PIPELINE_MAXIMUM；成功 result schema READY 上界 order54872、notification3361、request2947、document2949，PENDING分别52155/641/230/231；FAILED另见 refusal_unicode 分表（Unicode astral4/fullwidth3/escape2，controls由原 _str_field拒绝），全部小于整体54872。它们是保守不可达证明，不是合法业务 max。

九个分别<=65536 的 component 精确 outer delimiter/key开销140，9*65536+140=589964<1048576；SDK已无旧整体 nonledger64KiB聚合 guard，各 component原64KiB/depth64/node4096/累计string64KiB及原 signed-delta codec、ASCII JWS16KiB/ancestor1..3/17claims/真实签名不减，public HTTP仍64KiB。N021合法公共65536/65537及N031合法outer1MiB/+1不可达；真实合法pipeline、原 codec/非法oversize拒例/精确helper算术与公开oversize503+proof/link回滚分开说明。bounds JSON的 boundary_obligations 旧 pending/54873 文案是生成时历史文字，当前运行绑定以上实际 source/wheel exit/XML 与实际计算54872（54873仍保守）；不改已生成原件或虚报可达。下一 fresh包/完整审查独立核该不可达决议。

provenance-sourcewheel-final-r1.json、source/wheel import-witness.jsonl及真实 child JSON保存 Python3.11实际 PID/PPID、executable、模块及测试SHA、source/wheel prefix和无shadow验证，真publisher precommit SIGKILL、已READY后reply loss/死亡的独立新PID恢复不以 raise冒充。fresh locks/PEP517非editable wheel各实际 command/log、pip-freeze两日志、wheel-inventory-final-r1.json 与 wheel-production-final-source-equality.json / wheel14SQL-source-equality-final.json 绑定全部生产 Python与原14 SQL，环境实际信息见 environment-final-r1.json。

## 停写与资源

全部测试、wrapper、子进程/futures实际完成后，精确 fullID + owner/agent-guard.owner 双标签复核，仅清实际成功创建自有容器/网络；资源剩余0，foreign三容器 fullID/name未变，详情 cleanup-final-r1.json / process-inventory-final-r1.log。完整候选327路径起止、6/8范围变化、其余默认只读及历史472+审查17 SHA/bytes/modes、HEAD/index不变见 scope-final-r1.json，无违规。JUnit/日志隐私原件与公开版 SHA见 JUnit-redaction-final-r1.json。最终 artifact-manifest-final-r1.json 与 environment-content-manifest-final-r1.json 索引本轮全部必需 raw/来源；native-stop-final-r1.json记录实际FINAL STOP。
