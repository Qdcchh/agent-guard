# 窄补正 r3 实施交付

状态：FIXED_PENDING_REVIEW / READY_FOR_REVIEW。整体仍 PARTIAL、NOT_ACCEPTED。本报告仅实施自查，issue关闭与完整67项/60义务的fresh source/wheel独立验收由主控另派reviewer；没有Git提交、推送或进入后段。角色继承请求gpt-6.1-sol/medium，后台有效元数据UNKNOWN。

## 最小修改及语义

只修改 [正式测试](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/tests/unit/test_execution_concurrency_oracle.py) 的 `test_worker_timeout_is_bounded_and_cannot_pass`：`_race([blocked, lambda: 2], timeout=0.05)` 改为单参与者 `_race([blocked], timeout=0.05)` 并加职责注释。其他五函数AST逐字等价，_race及业务/SQL/依赖不变。[精确diff](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/oracle-change.diff)。正式文件SHA256 `ddb1abc52cee904825af3364e0b269f851880234006d4290e3399f048cc1a13e`。

r2 单线程延后0.2秒时peer先进入0.05秒Barrier导致BrokenBarrier，blocked回调无法进入；只读诊断10/10已确认。原报告、原失败及诊断不覆盖。这轮结构隔离使超时负控只检测真实阻塞者，而多线程成功/预期错误/RuntimeError/无关ExecutionError/缺完成继续由其他正式控制承担，不删除多线程义务。单参与者真实延迟启动200ms仍进入blocked并因真实未释放线程精确报 `race workers timed out`。保持entered为真、release未放行、线程alive、finally释放与join(1)及全部退出；不可达startup仍在1秒边界明确拒绝。

## 自查矩阵

| 目标 | 触发/断言 | 实际结果及证据 |
| --- | --- | --- |
| 正常调度10轮 | 真实blocked；精确timeout、entered、alive、未release、最终全退出 | 10 PASS；[60控制源](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/probe_controls.py)、[日志](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/controls-60.log) |
| 单参与者200ms迟延10轮 | Timer在Thread包装前创建；延后唯一worker，真实进入后timeout、全退出 | 10 PASS；同上 |
| join-gate10轮 | 被包装join(1)实际放行唯一worker，无rendezvous环；精确timeout及退出 | 10 PASS；同上 |
| startup不可达10轮 | readiness有界失败；cleanup放行并全退出 | 10 PASS；精确startup错误 |
| 伪造timeout10轮 | 未进入blocked却伪报timeout；entered等断言拒绝 | 10 PASS（有效拒绝mutant） |
| 禁用真实timeout检查10轮 | 真实_race timeout=6，blocked 5秒拒绝，不能假PASS | 10 PASS（有效拒绝mutant） |
| 原r1两个调度探针 | 原件保留；新预期对应单参与者结构，原gate/延时不降低 | join-gate10轮+Timer原等价1次通过；[原件1](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/probe_oracle_scheduling.py)、[原件2](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/probe_oracle_scheduling_repeated.py)、[diff1](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/probe-timer-adaptation.diff)、[diff2](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/probe-adaptation.diff)、[日志](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/old-r1-adapted.log)、[Timer日志](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/timer-original-equivalent.log) |
| 正式默认pytest oracle | 六节点，其他多参与者正负控制全保留 | 6 PASS；[XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/oracle.xml) |
| 默认完整非集成 | 无--assert=plain，全部正式非集成 | 952 PASS；[XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/full-nonintegration.xml)、[日志](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/full-nonintegration.log) |
| 真实PG P13 | root预算/祖先预算/call limit/accept-settle-recovery四组，原ROUNDS=10，各轮完整终态与精确错误义务 | 四节点PASS，共40轮；[XML](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/p13.xml)、[日志](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/p13.log) |
| Ruff/diff | 原仓库148 Python文件check/format，git diff --check | 均exit0；[check](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/ruff-check.log)、[format](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/ruff-format.log)、[diff](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/diff-check.log) |
| 范围/旧证据/Git | 仅获准文件变化；stage entries/staged diff/HEAD/branch匹配派发；旧证据全部哈希不变 | 246候选、25429旧证据文件；[范围](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/scope-readonly.json) |
| 进程/资源 | 测试已结束，PG client=0；owner及完整ID精确移除，自有network空后删除，原3容器不变 | [清理](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/cleanup.json)、[进程](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/processes-before-cleanup.log)、[命令](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/finish-commands.json) |

原r2 peer已进barrier的双参与者场景保留为失败证据；修后负控只有一个参与者，故不声称原场景仍存在或被同结构证明。当前等价迟延验证针对唯一真实blocked参与者，保留真实异常/拒绝与完整退出，不延长正式50ms、不吞异常。

## 环境、命令和限制

独占owner `br-cr3-b506978cb3`，Linux/amd64 Python3.11.17，UID501自有venv，requirements-dev.lock安装后普通非editable `pip install --no-deps .`、pip check正常；安装agent_guard来自/venv/site-packages，repo以只读mount供Ruff和源码输入。测试来自自有精确candidate；PYTHONPATH仅candidate测试，不含src，业务使用安装包。OpenSSL3.5.7、PG16自有独立DB、最小untrusted role属性/授权均按包创建。同DB固定锁测试串行；纯线程探针不用PG。sys.flags.optimize=0、无PYTHONOPTIMIZE；60控制以--assert=plain运行（不禁用Python assert），默认6/952/PG均原pytest断言重写。[环境](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/environment.log)、[flags](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/flags.log)、[安装](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/install-locks.log)、[角色](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/role-create.log)、[bootstrap命令](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/bootstrap-commands.json)、[实跑命令/退出码](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/local-remediation-20261004/worker-correction-r3/verification-commands.json)。

这轮没有重复完整1388 PG/source-wheel全验收或TLS/SM2业务套件，按窄补正包只跑P13及上述完整非集成；fresh最终reviewer须独立完成原完整67/60义务。本轮没有装配失败或产品失败；旧r2失败仍只读保留。

全部自有测试进程及资源已清理。保存索引与stop-binding后停止写入，交主控fresh复核，不自行关闭issue。
