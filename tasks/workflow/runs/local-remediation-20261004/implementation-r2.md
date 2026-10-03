# BR-FINAL-P13-TIMEOUT-CONTROL 窄补正 r2 实施报告

**READY_FOR_REVIEW；FIXED_PENDING_REVIEW，未ACCEPTED。整体项目PARTIAL。** 本worker交付后停止写入，后续结论读取 [本轮state](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/tasks/workflow/runs/local-remediation-20261004/state.json) 和fresh正式报告。

## 依据与所有权

依据 [correction-r2](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/tasks/workflow/runs/local-remediation-20261004/correction-r2.md)、[review-r1](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/tasks/workflow/runs/local-remediation-20261004/review-r1.md)（SHA f1a695a978df8d796c1937a6ee9cdc739e184ade5d109755f8e185fa2828af54）及既有真人授权/运行适配。单串行 `/root/implementation_r1`，继承请求gpt-6.1-sol/medium，有效后台metadata UNKNOWN，无派生代理。原67/60不降低；本次只做已批准窄自查，最后fresh reviewer仍须独立完整source/wheel与67/60，不能以本报告放行。

唯一产品改动 [test_execution_concurrency_oracle.py](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/tests/unit/test_execution_concurrency_oracle.py)，SHA256 `f10efeb09e859b3bc98e89edbea8b4ee4f6ab35998f53a2b964d1484c75a6e1a`。自有脚本/原失败/XML/日志/本报告仅写 `/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2`。产品源、_race、PG测试、SQL、依赖、现行文档、旧报告/worker/reviewer证据和控制状态只读，无Git提交/推送/重置/保护修改。

## 确定性修正

旧负控在_race的50ms总deadline已到而目标线程未被调度时，即要求entered，导致正确timeout的测试假失败。补正保留_race(...timeout=0.05)与精确timed out期待，独立自有OwnedThread.join在尚未entered时先调用底层有界join(1)，再要求明确startup-entered。先调用底层join使“join请求才放行”的原独立调度门可达，没有先等entered再join的环。目标真实blocked回调置entered后等待release，5秒自限保护与1秒startup准备分开；不是把_race的50ms扩大。超时后继续断言entered、release未置位、blocked线程仍活着；finally释放release并每个线程join(1)，断言全部退出。5秒保护保证错误oracle禁用超时时也不会留下无限阻塞，但该场景正式测试必须失败。

原缺完成、RuntimeError主线程cause、无关ExecutionError、LEASE_LOST精确detail与正常全结果测试逐字保留。没有skip/xfail、吞错、删除或弱化断言。改动见 [单文件diff](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/oracle-change.diff)。

## 原反例和适配

两reviewer原调度探针逐字复制、自有副本原样运行：首条确实在原entered断言失败；第二条10/10记录原失败、精确race workers timed out、所有线程退出。原脚本及原日志在本目录，[真实装配命令回执](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/bootstrap-commands.json)绑定退出0为“诊断成功”，不能解释为原正式测试通过。

修后首条原件仍原样运行，输出PASS_UNEXPECTED：这是旧诊断标签，实际含义是修后目标正式函数完整通过，不是新失败。重复原件仅在自有副本把“旧正式必须失败”期待改为修后直接调用通过，仍保留原run gate、join(1)放行、每轮精确oracle异常与全部退出断言，10/10通过；原条件曾注释为cleanup时才启动，修后同一join(1)是有界startup同步请求，证明join触发调度可达，并未删延迟条件。[精确适配diff](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/probe-adaptation.diff)保留原差异。

新自有60节点：正常启动/真实200ms gate延迟/join请求才放行各10；startup始终不可达直到cleanup时放行10；伪造timeout异常10；禁用真实_race的50ms超时、以原oracle timeout6秒实际运行10。正控每轮命中原timed out、正式entered/alive/release断言并全退出；缺启动明确诊断blocked worker did not enter within startup bound，清理仍退出；两oracle变异均被正式测试拒绝。没有数据库的线程探针不连接PG；正式PG测试串行，未以不同schema冒充DB级锁隔离。

## 实际自查

| 运行 | pass/fail/error/skip | 退出码 | 原证据 |
| --- | --- | --- | --- |
| 正式oracle默认pytest | 6/0/0/0 | 0 | [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/oracle-formal.xml) |
| 修后调度/正负控制最终 | 60/0/0/0 | 0 | [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/scheduling-controls-r3.xml) |
| 完整非集成默认pytest | 952/0/0/0 | 0 | [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/full-nonintegration.xml) |
| 真实P13完整文件 | 4/0/0/0 | 0 | [XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/p13-real-pg.xml) |
| 原仓RO Ruff check / format | 全通过 /148文件已格式化 | 各0 | repo-ruff-check.log /repo-ruff-format.log |
| git diff --check | 无空白错误 | 0 | diff-check.log |

P13四节点均保留ROUNDS=10循环、真实独立连接与全部祖先预算/效果/账本/outbox断言，共四组各10轮。新旧oracle全部参数节点包含在正式6项和默认完整952项；此窄补正不重复完整1388 PG、wheel或历史全矩阵，不声称替代后续fresh验收。[全部真实验证argv/退出码](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/verification-commands.json)、[XML具体节点与计数/SHA](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/xml-summary.json)给出实际证据。

## 自有harness失败保留

1. 专项首轮30FAIL/30PASS：20正控witness把pytest assertion-rewrite附加的诊断解释误判为不精确原消息；另10个timer-delay在Thread已monkeypatch后构造Timer，Timer.__init__调用被替换全局Thread.__init__导致TypeError。正式产品文件未因此再改。
2. 第二轮用--assert=plain与明确pyproject配置保留精确原错误文本，50PASS/10FAIL；仅剩上述Timer构造问题。plain不禁用Python assert。仅自有harness把Timer构造移到Thread包装前，200ms真实gate/全部断言不变，[harness修正diff](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/control-harness-fix.diff)；第三轮全60PASS。两原日志/XML全部保留，不能计为通过。
3. 清理后inventory比较错误使用Docker ps JSON不存在的Running字段导致KeyError，资源删除已完成。原before/after原文及错误回执保留；只读改为实际State，核三个既有容器IDs/labels/state/network/mount/ports一致，[最终清理](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/cleanup.json)。
4. 初次scope检查错误用raw .git/index SHA对比dispatch的git ls-files --stage -z SHA，得到false。未写回index；用相同stage-z口径重算及staged binary diff、HEAD/branch全一致，[Git比较修正](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/scope-git-recovery.json)。这不是已观察到staging变化，也没有raw index起始字节基线可声称stat-cache漂移。

## 环境、只读与资源

新独占owner `br-cr2-cca03994f7`，显式linux/amd64 Python3.11-slim，实际3.11.17、UID501普通venv/requirements-dev.lock/普通非editable安装/pip check0；OpenSSL3.5.7。/repo原仓RO，/e仅自有证据RW；完整候选逐文件副本绑定candidate-before.json，唯一产品更新只刷新允许的测试文件。产品模块从/venv安装目录导入，测试从自有candidate导入，未使用--target或editable。实际wheel元数据Generator=setuptools(80.9.0)，PEP517隔离按pyproject固定后端；venv种子setuptools79.0.1如实记录，不冒充运行环境全部为80.9。[Python无优化/安装构建信息](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/python-flags.log)确认sys.flags.optimize=0、PYTHONOPTIMIZE=null。宿主3.14不计业务验收。

PG16-alpine为自建tmpfs实例，测试库cr2_tests，网关与fixture创建的随机下游DB独立事务域。br_s1_untrusted NOLOGIN/非特权及ADMIN=false、INHERIT=false、SET=true按原要求创建，普通部署DSN未注入。没有连接既有三容器业务库。

[243项dispatch范围核验](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/scope-readonly.json)中仅允许正式测试变化；其初次index字段误比较已由上段独立修正。9424个只读源码/测试/SQL/依赖/v1证据文件哈希不变；旧文档34、补正文档14、reviewer339证据索引全部重核不变。原报告和控制文件未修改，HEAD/branch和stage index/diff一致。

自有Python `7a0c38cff555f4a41b164543320ed2da14f46c6b3c3cabe5e0e325eef2e9f856`、PG `f6dff3da52816c1c304b2aed65e79de6f35cfb4cc952816371baa4babf272745`、network `147da5361b8018ada34cc06ce5e7a1906948e3ecd3152b188647417270ec2d57`；测试进程结束后docker top仅sleep，PG owned client为0，核owner/完整ID/网络两成员后精确删除两容器及空网络，owner containers/networks剩余0。既有agent-guard-a2-pg和verivote三容器只读inventory核一致；未比较业务数据，不清其他资源。[清理真实命令/退出码](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r2/finish-commands.json)保存各步。

## 移交

BR-FINAL-P13-TIMEOUT-CONTROL仅标FIXED_PENDING_REVIEW；不关闭issue、不改state，不Git发布、不进入A2.2/A2.3/A3。整体PARTIAL/outbox PENDING边界保持。主控核native完成、单路径指纹和只读证据后冻结，另fresh reviewer完整独立复验原67/60/source/wheel。全部自有测试/探针进程和资源清理完成，本报告与最终SHA索引归档后停止写入。

**READY_FOR_REVIEW，停止写入。**
