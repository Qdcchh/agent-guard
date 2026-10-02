# A2.1-core 补正包 r2（残余＋新边界）

- 同阶段原真人授权：ses_f0ac0e676ffecn71p6Ww7zaqQq / msg_0f54148e0001ZW7yCMdK0TE97F，完整原文task-v1/state中；不下一段、不Git发布。
- 完整review-r3.md，NEW reviewer ses_f0970a878ffegigoOO59gEQydI/openai/gpt-6.1-sol，NOT_ACCEPTED；snapshot3814a5869984e334d12aa768a7aefbbc88a98f617ed519064af4b918fb471aba，contracts c17869452226d18ea8e72870f588452b19dc1f03c81002a056bf83fef9a6c8d1。
- 续本workflow MiMo ses_f0aa292caffeODmd0G8jUSZ1Y9；完整读task-v1、原任务/安全/接口、两轮补正/review及issues。不能以本摘要代原触发与变体。
- 本轮5项代码已独立关闭、5残余、2新边界及DOC仍开放；有效进展明确，不因轮次固定停止或降低要求。
- **主控确认新增migrations/006*属于同stage防护补正**：005已被应用，001—005 checksum不可改。封存旧已commit节点集合等用006，保七表旧行；不得复制修复式DELETE/补造旧节点。允许implementation-r3.md及owned artifacts/workflow/A2.1-core-impl-correction-r2-<unique>/；其余ownership不变。worker不改workflow控制/issues/review/包。
- 原反例源码/精确观察/JUnit见 artifacts/workflow/A2.1-core-review-r3-936bc079/，必须区分适配正例与保存负例trigger；不能让拒绝来自setup缺字段而算目标通过。

## 当前补正义务

| issue/需求 | 实证trigger/影响 | 必须修正与正式再验 |
| --- | --- | --- |
| OUTCOME 高 / P02,P12,OBL06 | service普通json.loads两次只读kind/key；同key但order_id/supplier/total/items、notification ID/target、read tool错配、duplicate/unknown/result typed bool quote仍终局；wrong-tool refusal真实订单存在也RELEASE | **一次有界严格每工具result解析和模式**，所有字段精确类型/集合，拒重复未知/NaN/depth/大小；effect_ref＝result对象ID，operation/tool/意图/报价/amount/per-tool关联全一致。成功与refusal分别明确schema，拒绝结果仍绑定原工具/键/意图及可信持久拒绝；任何错配UNKNOWN保预算/no outbox，execute/query各变体。只增加业务结果校验，不自写RFC8785/密码。合法四工具及拒绝正例保持 |
| CANDIDATE 高 / P11,OBL03 | verify_accept_facts比snapshot/cost却不比params.quote_id/version；params另ID仍run/candidate/fallback，旧数据无flag | **params↔成本columns↔snapshot三方quote_id/version/币种/total/items身份一致**；所有入口错误LEGACY_SNAPSHOT_INVALID＋持久sidecar，保预算零调用，候选拒不登记新proof。hit/fallback/run/reconcile/升级旧行与正常deleted报价retry回归 |
| SNAPSHOT 中＋LEGACY 高 / P19,OBL06 | 版本0/01/text、control/URL/过长IDaccepted；1500嵌套RecursionError漏flag | 存储与结果解析有界size/depth/字符串/数字字面量；exact ID规则、decimal positive版本无leadingzero、无@等原约束；所有已知Unicode/JSON/type/recursion失败稳定映射，**旧接受材料错误自动持久隔离**，result错则UNKNOWN。schema验证不以int/str修复；无超深未处理异常。各入口新增boundary正式测试，原8legacy保持 |
| EVENT 高 / P20,OBL05/06 | 005新event INSERT deferred只保新event；旧commit短RESERVE/SETTLE在升级后合法位置可补1→2→3，SETTLE outbox仍旧 | 新006保护**所有已commit事件（含旧不完整）不可追加**，且合法当前接受/终局同事务可写全path。可用独立封存sidecar/明确transaction-local创建事实设计，不改旧七表行，不靠时间猜测或客户端boolean。旧短材料隔离不修补；完整旧/新事件、跨txn旧短、错位置/path/delta、并发插入、outbox一致/upgrade全保全，direct SQL拒而不是仅入口检查 |
| UNKNOWN 中 / P09,OBL04 | _mark_unknown缓存UNKNOWN早return；旧claim已过期新owner终态后10/10旧worker报UNKNOWN，DB未改 | no-op也统一锁序核**当前state/owner/version/expiry**；失租返回稳定错误或确实当前终态，不把cached旧state当结果。run/reconcile两个公开入口确定性旧query阻塞→expiry→新owner终局→旧none；10轮无旧覆盖且返回准确，正常UNKNOWN仍保预算 |
| TESTSYNC 中 / WF-QUALITY,P09 | 正式test_claim_and_finalize_interleaved使用同barrier在持task后二次wait，同行拿不到task；吞BrokenBarrierError使10有订单却无终局仍PASS | 将同步点移至双方可达且保留能触发旧反序的真实交错；**线程未预期异常必须失败**，明确每轮final-ok/合法失租边界、最终三层reserved/settled、event/outbox及唯一订单必须完成。不能删测试/只assert无deadlock，增故意异常/无progress有效性验证 |
| DOC 低 / WF-DOCS | A2-report未跑3.11/主体未开工/004计划/182旧措辞仍当下；README first migration结果与CLI-first后实际[]矛盾 | 报告顶层只当下事实，历史段明确snapshot日期/已过时，不把历史counts/门槛变结论；同步实际31ID、全部issue、tracked/untracked及本轮计数。README迁移输出区分CLI-first和no-op，原文再烟测；implementation-r1/r2不覆写，r3纠错索引 |

已经关闭LOCK/NOTIFY/CHAIN/LOG/BOUNDS不得退化，全量A1/新核心回归继续运行并保留报告。当前UNKNOWN不要求更换用户授权、通知最小同grant/holder不扩大。所有残余触发不能因固定测试数或只原case通过而省变体。

## 交付与停止

Python3.11+真实PG/downstream独立资源，全部31ID、自有资源归属/cleanup、真SIGKILL重启、10轮并发、001/003/004/005→006非零/非法升级保旧七表与完整登记、SQLsealed旧节点及README烟测。新增正式test验证目标条件确实触发，捕获异常须精确不吞同期失败。

完整runs/A2.1-core/implementation-r3.md含逐issue修复和旧/新trigger测试、命令/exit/JUnit/数据断言、限制、实际清单；更新A2-report，旧证据保留不覆盖。标FIXED_PENDING_REVIEW、READY_FOR_REVIEW停写，主控新freeze/fresh reviewer。必需环境/设计无法闭合报告BLOCKED具体原因，禁止自ACCEPTED或下一段/commit/push。
