# GPT 6.1 Sol 的 A2 独立复核指南

日期：2026-10-06。仓库：`/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`。

真人已按本指南[恢复完整复核](runs/A2.3-receipts-20261004/user-resume-sol-20261006.md)，本轮全量独立复验及必要同段补正、证据/清理/交接获授权，现已[完整独立接受](runs/A2.3-receipts-20261004/acceptance.md)并完成收尾；以下接手事实为指南编写时历史，不能当当前待复核。旧停止保留为历史。切换请求配置已生效，实际有效metadata仍UNKNOWN；本次不发布Git或实施A3。

## 模型和独立性

建议主控 `gpt-6.1-sol / high`，每轮全新 reviewer `gpt-6.1-sol / xhigh`，必要补正 worker 保持 `gpt-6.1-sol / medium`。这组请求配置已获2026-10-06真人采用并同步现行角色入口；历史任务和报告中的请求配置不追改。后台有效 metadata 未暴露时写 `UNKNOWN`。

主控负责授权、冻结、证据核验和状态；reviewer 亲自审代码、运行完整矩阵、写独立结论。使用新的 reviewer 子会话，以正式任务、冻结候选、原始要求及失败记录为输入；不只发送主控成功摘要，不复用实施者或旧 reviewer。reviewer 不再派生子 agent，不写候选。主控也不在它审查期间修改候选。使用相同模型不取消角色独立性，但不能宣称具备不同模型带来的交叉验证。

官方将 6.1 Sol 定位为适合复杂编码、接近 Astra 表现且成本更低；这支持尝试该配置，不证明它在本项目上等同 Astra，也不保证发现所有缺陷。[模型说明](https://developers.openai.com/api/docs/models/gpt-6.1-sol)

标准速度下每百万 token，Sol 普通输入/缓存输入/输出为50/2.5/250 credits，Astra为250/25/1250。相同 token 用量时普通输入与输出费用为五分之一、缓存输入费用为十分之一；实际总量和推理档位可能不同，不能保证120 credits完成。[官方计费](https://learn.chatgpt.com/docs/pricing)

## 接手事实与阅读顺序

1. 先读根目录 AGENTS.md、AGENT.md、HANDOFF.md，以及 workflow 的 README.md、current-policy.md、context.md、issues.md、implementation-contract.md、review-contract.md、`runs/setup/codex-astra-sol-v1/workflow-contract.md`。当前真人授权优先；历史完成、pending和停止措辞需按时间辨别。
2. 读 `tasks/A2-execution-gateway.md`，`docs/oauth-oidc-sm2-mvp.md`、`docs/security-model.md`、`docs/acceptance.md`，以及A2.2正式 `runs/A2.2-integration-20261004/acceptance.md` 和对应复核证据。
3. 下述运行文件均位于 `tasks/workflow/runs/A2.3-receipts-20261004/`：state.json、task-v3.md、requirements-v3.json、node-bindings-v3.json、ownership-v3.json、inherited-bindings-v1.json、runtime-binding-v3.json，及后续实际适配/包审。继续读 task-full-acceptance-resume-r1.md、review-r1.md、task-remediation-r2.md、package-review-remediation-r2.md、runtime-binding-remediation-r2.json、implementation-remediation-r2.md。core/CLI/HTTPS等报告按依赖阅读，不能代替源码。
4. 保留 user-stop-20261005.md、user-resume-20261005.md、user-stop-after-selfcheck-20261005.md。未来恢复另录真人原话，不删旧停止记录。原完整复核任务可作要求索引，其旧 owner、资源、freeze和旧轮次不得直接复用。

编写本指南时实际 HEAD 为 `2a8cc7da4867ad1876350855c0ed5569c5ce6472`，分支 `handoff/a23-local-20261005`，已有文档未提交修改和未跟踪报告。父目录属于另一个Git仓库。接手须重查真实root、分支、HEAD、index、所有dirty/untracked/deleted/rename、remote和PR，不能把这里记录当当前实查；不得reset/clean、覆盖或丢弃既有成果。

整合补正已完成完整自查：source和非editable wheel各1185普通、2810完整PG集成通过，另有增强、时限、历史和边界组。它们只是自查。前轮独立r1为NOT_ACCEPTED，P2仍是FIXED_PENDING_REVIEW；新复验未执行。PR #7此前的旧HEAD CI成功不代表当前候选CI/审核通过。

整合者封存证据exit0后原生会话触及用量限制；主控完成行政收尾，不是worker原生成功STOP。恢复时核原生活动状态、进程、证据和归属，不伪造回执。上次自有资源已清理；Docker关闭时无法实时查容器，不能把连接失败写成容器为零。

## 主控冻结与派发

只因更换模型不重复业务包审；如范围、共享接口、依赖或所有权发生实质变化，重新规划并新开独立PACKAGE_REVIEW。同类有限运行适配已有持续真人批准，保留具体适配与授权来源，不降低门槛、不改旧门、不补造metadata。

先确认所有writer停写、测试子进程退出及自有资源核验，再生成新轮完整候选清单：Git状态、staged/unstaged diff、tracked和有关nonignored untracked、删除/重命名、模式/symlink、逐文件及清单SHA-256，涵盖源代码、调用方、测试、fixtures、SQL、依赖锁、配置、正式任务与影响判断的文档。不能仅冻结HEAD或diff。新增本指南和接续文档也使旧最终清单不再代表当前完整候选，必须重新冻结。

派发新的 `IMPLEMENTATION_ACCEPTANCE`，绑定新轮次、唯一owner、独占ignored证据目录和完整清单。审查开始及结束，reviewer本人重新核全候选与Git。唯一可写区域为其本轮自有证据、探针与隔离资源；历史证据只读。漂移则本轮不能接受，重新冻结并新开复核。

## 完整复核顺序

### 先建立要求和真实断言的对应关系

从原要求和实际JSON独立核对119项、112运行义务、269条must_assert、41节点和88本地原子，不以数量相等替代语义完整。每项绑定实际实现/调用方、源断言及helper效果、测试case、运行标签、命令/退出码、日志/XML/SHA、实际观察与缺口。覆盖索引、AST调用和helper union只能定位，不能证明本次触发了某分支或父项全部通过。

审实际全调用链、差异和周边代码，特别是输入可信边界、锁序、最终DB时刻、回滚、状态机及跨事务域恢复。区分本人实跑、本人静态查证、历史日志核对和NOT_RUN；全绿计数不能替代负例确实触发目标条件的证据。

### 优先验证已知P2及邻接风险

稳定问题ID：`A23-R1-PUBLISH-QUOTE-ARITHMETIC`。旧反例在自有可信材料故障fixture中同时改变原quote与result单价，原total/params/账本/DS不变，publisher仍签名READY。正常SQL不可变guard原本有效；该缺陷不是外部SQL权限突破。

直接审 `execution/original_material.py` 的 `validate_original_tx` → `execution/service.py` 的 `verify_accept_facts` → `tools/catalog.py` 的原接受事实校验，连同receipt_publication/query/SDK/CLI调用方。验证拒绝发生在真实签名及READY更新之前，完整原root→leaf与事件绑定正确，不引入当前报价、撤销、到期或下游读取作为历史终局发布的新前提，不倒锁。

亲自执行原coherent反例及新变体：单价/总额/溢出/数量/quote identity/currency/calls；普通immutable guard正控；拒绝时零签名、PENDING/null与31 ag＋3 DS完整基线；恢复原材料后同operation合法发布；零价、当前报价移除、撤销/过期后的合法历史发布；真实CLI batch=1坏首行不饿死合法行及新PID恢复。保留现有CHECK正控，不为造坏行删除SQL约束。HTTP静态拒绝允许的STAGED证据与publisher拒绝零新变化必须按各自契约分别断言。

先运行这组可尽早发现阻断，避免明知缺陷仍重复长套件；通过后仍必须完成下面全部验收。确认阻断时保留失败并交补正，不能凭修补后的局部绿直接接受。

### 独立完成全矩阵

- 本轮fresh Linux Python3.11、PG16、精确锁安装，真实Tongsuo SM2/SM3、OpenSSL/TLS；14 SQL与迁移checksum/历史非零数据保全。source和自行fresh构建安装的非editable wheel分别collect并完整执行普通与PG集成、质量检查、前段回归和所需探针。
- 全祖先累计金额/次数、撤销、当前验权、新鲜性、幂等、UNKNOWN预算不释放、恢复不可变意图。并发10轮有效竞争，独立连接/barrier/锁等待、所有futures和实际业务/数据库效果均验证，不能仅观察请求返回码。
- 真实core及CLI签后commit前SIGKILL、READY被独立连接观察后的reply loss/终止、新PID恢复，同receipt ID/iat及持久JWS字节。用可信原生/proc观察；Rosetta空进程视图不能证明进程退出。
- 真实CA/SAN的AS+GW同场景链：login/consent/code/ID Token、两次exchange、四个canonical tools、终局/publish/当前query/独立SDK；盗token、父冒child、篡改/重放、跨owner、撤销过期、无管理路由及全状态拒例。README原AS/GW流程也实跑。
- A1/A2/B原历史探针与现行等价、oracle60、增强487、严格时限500、CTX16及A2.2两项历史P2。数字为已有组的定位线索，按本轮实际collect和义务判定，不机械追数。原失败与逐项等价触发/断言要保留并解释，不把原B的221P/25F/4E或A1升级失败改写成原组全绿；不能仅凭旧归因忽略本轮新失败。
- 必须核对late dependency各子义务的精确错误码/HTTP映射，只有raises(LedgerError)不足以证明STALE_REQUEST与EXPIRED；不把父期限和叶/token同时到期冒称独立祖先期限探针。
- 容量按N021/N031真实validator和合法域独立推导；区分canonical producer保守58168、兼容合法raw JWS域保守64695与真实最大值，不能直接承接这两个数字。保留256 SKU及4/12/16/17宽、原64KiB组件、raw JWS16384/16385、public65536/65537及proof回滚、outer589964与1MiB/+1等原门。SDK外壳与public DTO不能混算，合法宽17成功不是阈值拒例。
- reviewer自行设计跨包绕过、边界或状态变体探针。照跑worker脚本及旧反例不能单独称为本轮独立探针。

### 避免已知运行和证据陷阱

复用已验证runner设计前先读源码并重绑新owner/路径/DSN；不复制旧PASS或旧私有数据库。外部探针先核fixture装配和少量smoke，再跑全组。起跑前读回所需低权限role及成员语义，清普通部署DSN，GW与DS保持独立连接/事务域。

source/wheel复制输入排除pycache/pyc，记录实际导入路径、sys.path、安装元数据、轮文件hash、77 Python及14 SQL的对应字节；不要靠事后find_spec冒充运行时加载证据。wheel SQL位置按真实安装核实，不能猜site-packages路径。`dist-final`是旧完整2810自查所测制品，`dist-stop`后来只改METADATA/RECORD；不得把旧完整运行追溯归给新制品，本轮用新冻结候选重建并完整跑。

运行前绑定本轮A23_RECEIPT_EVIDENCE、A23_RUN_LABEL、A23_CLI_EVIDENCE、A23_CLI_RUN_LABEL、A23_HTTPS_EVIDENCE；每命令即时保存开始、环境、完整raw、结束和实际退出码，避免外层wrapper回执漏存。必需deadline/锁/PID/容量观察与case一同保留。脱敏副本与原件双SHA，原件权限0600，敏感值不进聊天或Git。

一秒proof可沿用已批准的真实DB/wall对齐设计，但先审适配，不改TTL、时钟、claims、产品或断言。网络失败先在同一交互shell尝试setproxy，避免输出代理值；产品PG/TLS测试不继承代理。已有工具满足条件时不要无谓重装。

## 节约用量与结束条件

一次只保留一个完整验收reviewer。主控负责必要调度/核证，不并行重复同一套审查。详细日志落盘，工具只回摘要及所需失败片段；用脚本生成索引，reviewer逐义务亲判。已由本人本轮完整运行覆盖且版本一致的组准确绑定，不无理由重跑；不能用worker或旧reviewer日志抵本轮必跑。短、稳定的交接摘要防止反复读取整段会话，不能删去必要原要求和失败证据。

启动前、关键阶段结束后观察实际余额；这是账户共享余额，不是本任务独占成本表。用户的120 credits是余额信息，不自动视为已批准全部花完或新的硬上限。不保证能跑完；接近用户后来明确设定的预算线时应保留可恢复检查点和原始证据，不能省略义务换取ACCEPTED。

报告按review-contract模板给出完整119矩阵、逐must_assert证据、代码发现、原缺陷本轮依据、运行与失败、未执行项、范围限制和A3边界。仅全部必需项闭合且无已知阻断才ACCEPTED。发现缺陷则保留原件、稳定ID、触发/影响/复现；在真人恢复的补正范围内由writer处理，完整自查/停写/新冻结后换全新reviewer完整复验。

结束核精确fullID＋owner标签＋Mounts，只删除本轮成功自建容器/网络/匿名卷；全wrapper及child PID退出，核无关资源前后不变。不prune、不连接无关容器或共享库。主控原样保存完整报告后核原件、结论和首尾指纹，再更新issues/state/HANDOFF；未知回执保持UNKNOWN。

复核接受不自动授权提交/推送/PR/合并。未来真人明确恢复交付范围后再按实际CI和审核处理；不强推、不绕保护、不沿用PR #6管理员例外。A3不在本指南执行范围。

## 切换后可发送的恢复指令

以下仅为用户可采用的文本，不是已发生的授权：

> 已切换主agent为gpt-6.1-sol/high。请按tasks/workflow/sol-review-guide-20261006.md恢复A2完整独立复验，reviewer使用全新gpt-6.1-sol/xhigh，必要补正worker使用gpt-6.1-sol/medium，未知有效metadata记UNKNOWN。保留现有成果，先核真实Git、授权、停写、资源和完整候选；执行完整119/112验收及必要同段补正，不降低标准。完成复核、证据、资源清理和交接后停止；这次不提交、推送、创建PR、合并或实施A3。
