# A2.1-core 补正包 r1

- 状态：同一已授权阶段的自动补正，不新增大阶段，不降验收要求。
- 真实用户授权仍为session `ses_f0ac0e676ffecn71p6Ww7zaqQq`、message `msg_0f54148e0001ZW7yCMdK0TE97F`，原文与正式task-v1/state一致；“继续”仅恢复同一阶段，不作为下一段批准。
- 完整审查：`tasks/workflow/runs/A2.1-core/review-r2.md`；NEW reviewer=`ses_f09c688edffenINjKt4oOU8erV`，实际openai/gpt-6.1-sol；结论NOT_ACCEPTED。
- 受审snapshot=`b2ad9065b9d24a3e71f6f3e27a42416326da2a8c9bd0cbfa3d6be9003c279288`；当轮contract摘要=`701a06938365ba0dd74399f1952566d57562bd141dcecdff2398cd8cc45cbef5`。
- 续本workflow新建MiMo session=`ses_f0aa292caffeODmd0G8jUSZ1Y9`，不是历史Go-Main。单writer，完成后停止交主控，fresh reviewer再验。
- 必读正式task-v1、原任务/ckpt1-r2、完整review-r2、issues及implementation/review契约，不能只读本表摘要。
- 审查证据根：`artifacts/workflow/A2.1-core-review-r2-c6d39e12/`，evidence-index、observation-index及probes/包含完整trigger与实跑反例；r1中断历史也保留，别覆盖删除。反例源可借鉴转正式回归，不把原观察型断言原样复制为通过目标。

## 主控明确的范围与迁移决定

004已经由worker及review实际应用，未跟踪不等于可改checksum。**不得修改001—004。** 防event追加/封存等数据库补正用新增 `migrations/005*`，允许多个005前缀文件须仍遵循迁移器唯一version（建议一个005）。主控确认这属于原A2任务“004+”及同阶段补正，不是需求或阶段扩张；task-v1要求新增版本超004需先报告，此处正式给出确认。保留旧表原行，非法升级拒绝不清零，必要sidecar标记异常旧操作但不产生效果/释放。

本补正允许原实施文件范围＋migrations/005*、完整 `runs/A2.1-core/implementation-r2.md`及owned `artifacts/workflow/A2.1-core-impl-correction-<unique>/`；其余不变。workflow状态/包/审查/issues只由主控编辑，worker不能改需求矩阵；ledger仍只读，发现必要修改先请求。B/HTTP/真回执仍排除，不commit/push/PR/合并/改保护。

## 逐项补正（全部阻断项必须闭合）

| Issue / requirements | 严重性/trigger与证据 | 必须修正行为 | 正式回归与自查证据 |
| --- | --- | --- | --- |
| A21-R1-LOCK / P09,P13 | 高；_claim先operation FOR UPDATE再task/grants，终局相反；review10/10deadlock | 非锁读定位、统一task→根至叶→operation→lease，锁后复核不可变定位及完整接受事实；必要有界retry，不能只重试掩盖反序 | event/barrier固定反向交错10轮、接受/恢复/终局整体竞争，无DeadlockDetected/无界锁，不超限，完整计数/效果 |
| A21-R1-LEGACY / P19,OBL03 | 高；worker仅查已有flag，未手动helper的旧行8变体执行/释放 | 自动在run/reconcile/候选hit与fallback/claim及必要终局验证完整参数/工具版本/币种calls成本/快照/首次证据/完整RESERVE路径及delta；无材料自动sidecar持久隔离、预算不变、零下游调用，不要求用户先手动隔离 | 001/003/004旧库missing/malformed/extra/evidence/items/quote/bool/incomplete-reserve各变体各入口；flag真正持久化不能随抛异常rollback；不补当前目录 |
| A21-R1-OUTCOME / P02,P12,OBL06 | 高；其他key拒绝释放后原key迟到成功，string false/bool金额等终局 | 精确outcome类型、operation_id、tool/params/fullquote/currency/amount、每工具effect及结构化result绑定；真正同键持久拒绝才RELEASE，异常UNKNOWN/no outbox；拒绝payload/结果不可互相伪装 | execute/query不同key-success/refusal、bad result/missing effect/types/quote各变体；late original成功保预算；合法订单/读取/通知/拒绝正例 |
| A21-R1-NOTIFY / P15-CORE | 高；不存在及cross-tenant目标仍通知 | 接受前可信DB查询引用操作存在、同tenant/task且可访问。采用原查询边界的严格最小政策：原授权grant/holder访问自己操作；若需要跨grant访问先向主控提出可信策略，不把same-task默认可访问。不能信body | absent/cross-tenant/task/未获权holder或grant，零新增proof/预留/操作/通知；同grant/holder目标正例；retry不要以当前资源存在破坏已接受事实 |
| A21-R1-CHAIN / P15-CORE,OBL01 | 高；leaf-only/缺mid/超长链accept，省限制祖先绕过 | 可信分层快照每层约束与grant身份/顺序绑定，并对DB完整root→leaf比对层数/节点/收窄，不仅相邻 supplied检查。可以加法扩展可信契约及更新fixtures，不复制B实现 | omitted/reordered/wrong-layer/root/extra/spliced-negative；根/中间/叶调用合法正例，0预留/效果；保持A1路径权威 |
| A21-R1-LOG / WF-DOCS,安全日志 | 中；worker stderr和RunResult.reason拼原异常回显secret marker | 稳定错误码和安全摘要，不打印DSN/secret/token/敏感params或完整底层异常；配置解析错误也收敛，内部诊断不输出原消息 | malformed DSN、下游异常夹secret/SQLparams，捕获stdout/stderr/reason无marker；真实错误可追踪但不泄露 |
| A21-R1-BOUNDS / P08,F5关联 | 中；下游sql lock/statement_timeout=0，真锁等待需手动取消 | 每条下游执行/查询及gateway只读连接设置有限正连接/SQL等待上限，拒绝bool/0/非法配置，必要尝试/退避有界；异常UNKNOWN不释放 | 独立锁实际自动timeout不依赖reviewer cancel；设置值/超时码/时长/预算断言；正常连接/执行查询保持 |
| A21-R1-EVENT / P20,OBL05,06 | 高；commit后RESERVE/SETTLE第四节点INSERT成功，outbox仍三节点 | 新005在事务/DB层保护完整节点集合、不可改删及提交后封存；位置/根至叶ID/数量/delta精确。拒append/错位置/错delta/额外/缺节点，合法A1首次写RESERVE及A2终局同事务仍成功；不能关闭trigger过测试 | direct SQL aftercommit追加/相同事务错误节点、错路径/delta缺额外，回滚全状态；ledger_changes与event全内容一致；001/003/004→005数据保全/非法升级 |
| A21-R1-CANDIDATE / P11,OBL03 | 高；持久quote ID/version与params/成本列不同仍EXISTING | 候选全部持久工具/参数/报价ID版本/币种成本/fullsnapshot关联一致，拒绝/隔离不完整接受事实，不能拿当前报价修补 | deleted-current-quote hit、miss后recheck、升级旧行身份/版本/currency错配；proof不额外消费/预算不变；合法retry原成本 |
| A21-R2-SNAPSHOT / P19,OBL06 | 中；int/str强转接受bool/float/numericstr/duplicate/unknown/null/negative product | 有界严格存储JSONschema：精确字段/type/ID/version/唯一SKU/正数量/非负有界price/total，重复键/未知/NaN/Infinity拒绝，安全乘加和总额重算；禁止自动强转修复 | 合法roundtrip与所有旧rawbytes变体、超界/大小/深度；run/query/candidate自动隔离零效果；普通JSON不声称RFC8785 |
| DOC-CKPT1-01 / WF-DOCS-REPORT | 低但阶段报告质量仍要修；实际4tracked却文中onlycontracts、004/数量/环境残留 | 报告当下状态/旧历史分开，真实tracked/untracked/计数/变更范围；README给可执行可信初始化/下游provision/操作接受/worker/recovery/cleanup，普通DSN清除 | 只用自有实例照README smoke，保存命令与真实效果，完整31ID矩阵/元数据/限制不伪PASS；旧r1报告不覆盖，r2纠错索引 |

## 验证、环境与交付

全量原任务/31ID要求继续，不删除/skip/改松测试为凑通过。修改测试夹具让通知目标真实合法、chain完整，是修正测试装配，不降低负例标准；说明原错误fixture为何不能作为安全正例。将发现触发及变体加入正式测试，保留review历史源/日志。

Python3.11+真实PG独立容器/下游事务、所有并发组10轮、真进程SIGKILL/重启、001—004旧checksum不变、005升级七表/完整登记保全、A1完整回归、质量与README烟测必须实跑；层次替身/断网/TLS口径继续如实。新worker资源不能复用review旧库；只清owner明确自有实例，ordinary DSN清除、证据脱敏。

写 `runs/A2.1-core/implementation-r2.md` 按模板包含每个issue实际修复/新增负例/自查证据、全部31ID映射、tracked/untracked/deleted、实际模型/session、PG/Python/env、日志/JUnit/资源清理、限制。更新A2-report短索引，不编辑主控issues。标FIXED_PENDING_REVIEW而不是关闭、停写READY_FOR_REVIEW；必需项缺证据明确BLOCKED。

主控冻结新snapshot/contract，再NEW reviewer对每条原trigger/变体和完整阶段回归独立验收。10条代码阻断及DOC记录不得遗漏。核心接受后仍停等用户，不进入后段/发布。
