# A2.2 r1正式补正：同一已批准范围

目标：按本轮独立review正式确认的完整问题清单补正同一已批准A2.2包。原95项/88实跑义务、原67/60、所有历史回归/安全边界保持。reviewer已原生完成停写；主控核全部518项证据、95项语义、全部115个运行及JUnit和完整280项冻结一致，正式保存review-r1。结论NOT_ACCEPTED：86 PASS/9 FAIL，由以下两个P2导致。

## 正式确认的两项

1. A22-R1-RESULT-ERROR：可信持久结果错误operation/结果类型/[]时，真实source和wheel返回500，契约要求503 TRUSTED_STATE_UNAVAILABLE。在AuthorizedQuery终态投影上下文仅转换typed DOWNSTREAM_INCONSISTENT为EvidenceError；其他未知或程序错误仍500，不按异常文本或全局捕获吞掉错误。持久损坏不得接受、不得泄漏内部值、proof/binding业务状态整体回滚。正式回归需覆盖order/read/notify/refusal多形状错误、错误operation ID/total，正控，各祖先金额次数与业务事件/outbox/lease/独立下游全部前后相同；分离允许STAGED evidence。修复原数据后用同一个未被消耗proof成功，再重放409，证明失败登记实际回滚。

2. A22-R1-SHORT-WINDOW：signed_env_window根期限int(time.time())+3但子请求固定ttl3，跨秒即请求子exp超父exp，测试在可信ASfixture设置阶段失败，未到查询锁后窗口断言。修复必须实际AS签发、真实父期限收窄；根据真实token父exp和真实当前请求时间选择可用TTL，并保留必要安全余量/有界失败诊断。不要只把测试绕开、不伪时间/DTO、不跳过AS验权、不吞InvalidRequest或无界重试。可适度增加短窗以覆盖可信设置开销，但负控仍等待选中实际持久deadline，确保原target根/mid/leaf/token窗口在最后SQL等待后过期；正控在期限内真实成功。新正式回归强制跨至少一个真实秒边界且父仍有效，10轮收集所有异常，断言真实签名root->mid->leaf各exp收窄、目标查询确实触发正负控而非设置提前拒绝。说明合法子有效期必须被祖先约束，根/mid过期含leaf/token同时过期的真实语义。

## 范围和工作边界

原task-v1列29文件中implementation-r1.md历史原件不可改，继续原28个精确业务/当前文档文件；本次预计query.py、tests/fixtures/gateway.py、tests/integration/test_gateway_query.py、必要errors测试、当前交接/实施说明。旧SQL、依赖、.github、原formal包/授权/实施r1/r2/r3/pause/review-r1只读。controller独占state/issues/workflow控制文档；worker只独占其原允许源码/测试/当前文档及新的ignored resume-r4。范围如需增加先报，不临时跨writer。

## 必需自查与新的独立复核

先独立自有环境复现并保留原错误，然后修复正式源码和回归；记录全部failed命令/log/XML与每次适配。source/wheel完整普通+PG、A1单列、A2历史原482、B原失败/等价250、A1原4+1/等价升级、六旧补正和oracle60、完整95/88、先前context完整字段16变体与原proof过期新query正控、全部增强/真实TLS四工具/真进程故障/README/doc检查继续实跑。不能只跑新增2项或继承reviewer环境及PASS。计数按实际收集，原测试义务保持，新增正式回归纳入新矩阵。所有真实并发/确定性锁后TTL组10轮，完整祖先与下游效果/原始数据/原件哈希/明确类型失败断言。

own Linux Python3.11 UID501、PG16容器/network、gateway/独立DS DB，建议owner a22-worker-resume-r4-20261004，只自己精确IDs可清理，三个既有无关容器不连接不改。原始artifacts任何密码文件不可打印；测试XML有异常时需要语义保结构脱敏并记录前后sha/次数。轮末完整原始hash索引/运行注册/完整需求矩阵/候选指纹/资源零余留/报告implementation-r4.md；只READY_FOR_REVIEW与FIXED_PENDING_REVIEW，原生停写。主控范围核验全冻结后另开fresh reviewer sol/xhigh全95/88，不沿用r1review结论。

最新真人已授权通过A2.2后无论merge是否可行继续A2.3完整A2再分段全部A3；本次业务补正仍仅A2.2，当前文档可准确提及后续授权但不冒称下一段实现。有限适配已批准；本阶段不改旧机器门/后台UNKNOWN/保护。审计历史原件全部保留。

正式原件：[review-r1](review-r1.md) SHA256 `49b4b4f638a095fea1432db61203af0666d770224fe1c6bf539242540a00712c`。原95项需求JSON不变；补正未扩展业务写入范围，无需用新需求替换原包。当前控制与后续授权已据真人修正，实施者仍不得写state/issues/工作流控制文件。
