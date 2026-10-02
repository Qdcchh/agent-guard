# A2.1-core 补正包 r3／最小A1接受兼容检查

- 同阶段原真人授权msg_0f54148e0001ZW7yCMdK0TE97F / ses_f0ac0e676ffecn71p6Ww7zaqQq，不发布/不后段。完整review-r5.md，reviewer ses_f08c896cbffeptdE23OBohV4bm/openai/gpt-6.1-sol，NOT_ACCEPTED。
- 受审snapshot d7ea969a34b63782d06506d7f6ff9f221c6fbdc0590b2d2d9561e55554364c9c，contract27f22d55e88bb824a87b6e3c4124e69b030d4a59e6a5238572d130d0bae0ab7f。续workflow MiMo ses_f0aa292caffeODmd0G8jUSZ1Y9，但**本包须先NEW PACKAGE_REVIEW无阻断**后授权gate才实施。
- 必读全部原要求/task-v1、correction-r1/r2、完整reviews/最新issues、安全/接口/验收和工作流。原5+新2已闭合保持回归，5残余+DOC+P11证据缺口不能丢弃。

## 主控架构决定与文件范围（同一阶段兼容修正）

最后一次候选查找与A1事务决定之间存在并发窗口，**再加任意次非锁lookup不能原子保证existing材料可用**。这里确需A1调用方兼容修正；主控按stage“必要兼容先说明”明确允许仅 `src/agent_guard/ledger/service.py` 的最小共享接受路径扩展，其他ledger、contracts/ledger.py及001—006仍只读，不改变原accept默认API/语义/动态权限/proof/预算。

建议新增独立可信进程内入口（如accept_checked），或使用不改变默认行为的显式per-call检查参数；原 `accept(verified,cost)` 调用保持兼容。共享原事务流程，**实际existing查到后、EXISTING成功返回/事务提交前**，在相同连接/锁/事务内执行A2完整持久材料校验，不能在调用前后补查代替。校验能力不得来自HTTP/user字段/环境开关；不允许启用skipauth/直接success。不要把validator存到可变实例属性（并发调用污染），显式传递percall，不能扩到密码/网络层。

检查需要的operation/path/events必须在当前事务连接读取；如果完整接受材料不可用，拒绝并回滚本请求proof登记等所有临时写，然后由A2在**拒绝事务释放锁之后**独立连接持久sidecar隔离。不要在持锁事务里开第二连接flag导致自己FK锁等待；不能通过新入口绕原授权新鲜性或A1调用方行为。合法EXISTING仍无二次计费/不重取当前报价、首次证据不覆盖。

允许范围：原业务/测试/docs-report＋上述ledger/service.py最小兼容（不重写整体服务），完整runs/A2.1-core/implementation-r4.md、ownedartifact correction-r3-*。无新增迁移需要，本轮禁止更改001—006，不再扩迁移版本除非先报告确需。本兼容修正只是原子收严同阶段接受不变量，不变用户范围；独立包审若认为需要放宽或越界则BLOCKED请求决策。

## 逐项补正与必须正式验证

| Issue / requirement | 最新已确认trigger与影响 | 必须修正/回归（参考r5源probe与原要求） |
| --- | --- | --- |
| CANDIDATE 高 / P11,OBL01/03 | 最后miss后另A1提交同意图坏quote，10/10 actualEXISTING/newproof已提交/无flag | 按上节**原子actualexisting**校验，在最后miss之后event同步另连接提交坏/好材料各10轮；坏→拒/新proof不留/sidecar持久/原预算不变，好→同操作正确EXISTING。所有A1默认调用/并发/拒绝行为不变，校验异常不伪数据库成功 |
| LEGACY 高 / P19,OBL03 | snapshot深度已修但旧params1500层五入口RecursionError无flag | params输入size/depth/数值/字符串等边界与解析异常统一；在旧材料verify边界把可预期schema/编码/递归异常映射LEGACY_SNAPSHOT_INVALID，**run/reconcile/candidate/fallback/helper**自动持久flag/保预算零调用。新入参格式拒绝也稳定但不误标既有正常操作；严防genericcatch吞真实DB故障 |
| SNAPSHOT 中 / P19,OBL06 | regex.match与$接受quote/version/supplier/SKU尾LF，0 LF绕正版本；旧材料进入run而未隔离 | 所有安全标识/版本匹配用**完整字符串**语义（fullmatch或明确控制字符拒绝），正整数version非0无前导零；旧rawbytes/typed快照/结果中的尾LF/CR/Unicode/control负例和合法roundtrip。直接接受输入的ID规则也按既定schema精确，不只是某一个field打补丁 |
| OUTCOME 残余 / P12,OBL06 | typed snapshot.itemsNone/dict抛TypeError/AttributeError、已有单停EXECUTING；effect尾LF错误终局 | 校验是**总定义**：未知typed对象/容器/条目/type/字段以“不可信outcome”处理，安全UNKNOWN并保持lease/fencing/nooutbox；items合法list结构仍允许。先type/shape后遍历attributes，正确处理坏quote/result标识，不借宽泛catch绕后端授权。execute/query各坏shape＋合法list正例，原结果全字段绑定保持 |
| TESTSYNC 中 / P09,WF-QUALITY | 正式reverse-efficacy首锁前barrier不保证双方持锁，不交错/仅ILLEGAL_TRANSITION也PASS | **独立线程/DB锁明确持有环**：一方已持operation，另一方已持task，然后event/DB观测才允许取第二锁，精确DeadlockDetected/LockNotAvailable+waitgraph目标断言；不能接受任意异常。正序10round仍完整终局；故意串行/未取得目标locks的探针必须使效力测试失败，不能添加误负例只图绿 |
| DOC 低 / WF-DOCS | report当前段未标history/ckpt1门槛/006-results清单/355证据路径不准，typesdoc004仍未实现 | 统一当前最顶部与历史索引，写当前业务已实现但待验收、最新报告/actualfiles/JUnit路径；旧报告不覆写，当前types说明非功能承诺但别滞留未落地false。README双变体已修保持烟测，完整31ID/issue与错误诊断准确 |
| A21-R5-P11-EVIDENCE / OBL02 | 额外resource[3]一次unknown LedgerError，10diag未复现，无code不能确定是否过TTL合法拒绝 | 保存原fail不删，复验脚本/正式并发记录精确exception.code/detail安全摘要/cause、barrier时序、DBtime和proof/tokenexpiry/状态，确定性resource消失10+轮，失败不能catch成PASS。若因过期为合法拒绝给原时序/窗口及现在受控同步证据，不能无据声称旧失败已解释；记录尚缺部分具体恢复条件 |

**证据根** artifacts/workflow/A2.1-core-review-r5-4f8c2d19/，包含r5 selfprobes与旧r4适配，非finding list-only过严断言保留原因，不强制tuple。所有closed原issue及矩阵逐项全回归，不只5fix测试。

## 环境、自查和停止

Python3.11真实安装/PG16独立下游、真SIGKILL重启/所有并发10round/001—006 checksum与七表升级保全/A1全正式回归/历史probe等价说明/README流程如原包。尤其新ledger兼容默认API unit/PG/P1—14/proof重放/撤销/幂等/成本/连接有界都不退化。

完整implementation-r4.md记录结构设计及调用方、安全失败事务/独立flag、自查31ID、逐issue fix/新回归/精确诊断、真实diff/allnew、资源归属/cleanup与limits。update A2-report短索引，不改主控workflow台账/授权/审查/包。标FIXED_PENDING_REVIEW/READY_FOR_REVIEW停写，fresh implementation reviewer最后全矩阵验收；本包包审通过不接受代码。阶段通过后停，不进入A2.2/不Git发布。
