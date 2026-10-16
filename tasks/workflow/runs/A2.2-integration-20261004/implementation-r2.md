# A2.2 恢复后暂停检查点 r2

状态：**PAUSED_BY_USER**；不是READY_FOR_REVIEW或ACCEPTED。用户明确要求十五分钟内暂停，主控03:27:16 UTC转达；本报告记录当前停写检查点，95项/88运行完整验收矩阵仍**NOT_READY_PAUSED**。旧formal implementation-r1及第一暂停40项证据原样保留。本轮无commit/push/PR/reset/checkout/clean，不进入A2.3。

worker `/root/a22_worker_r1`；请求gpt-6.1-sol/medium，有效后台metadata UNKNOWN。分支`codex/a2.2-integration`，HEAD`280022e9d7005daa8d551ba0e4c52e3228e3add5`，产品基线d7e91c7。本轮实施/运行适配授权与PACKAGE_READY保留。主控拥有state/任务/授权/矩阵/问题及四控制文档，worker未改这些文件。

## 保存版本与实现

已保存真实query bundle/source/evidence同事务绑定、零业务成本AuthorizedQuery、typed token/proof错误、两固定HTTPS POST的严格ASGI/真实endpoint、AS公钥/identity/catalog私有配置与init/check/run及新增正式测试。修复合法未授权SKU403、catalog按实际lookup key去重、原件JSON精确对象/字段503、可信祖先坏签名503；HTTP头压缩/组合凭据/ASCII/framing与容量超时路径已补。

响应边界沿用既有GM编码完整JSON **65536字节**，没有改编码profile。HTTP把编码放在异常映射范围内，坏可信payload/超限503；query提交前编码及byteguard拒绝，proof回滚。初稿1MiB是冗余上限；65536字符另加JSON开销不能作合法正例，最终以63000字节载荷正例和超限/强制byteguard负控实跑。旧尝试失败保存，不以改原编码器兜底。

query新增principals/task/grants/operation/evidence/proofINSERT/link/deferred八类晚依赖10轮正负控；root/mid/leaf各撤销/各holder key停用10轮先后线性化；真实AS短root/mid/leaf/token窗口。子令牌不得晚于祖先，因此父到期负例亦使依赖叶/token到期，不声称隔离父过期而叶有效。自有补充probe另逐根/中/叶断言四计数不变、deactivate的grant整行不变、全部ds_*行不变，source/wheel各138通过。

真实CA/hostname验证的独立gateway进程四工具、新proof查询、真SIGKILL worker后持久恢复、gateway新PID重启后查终态已在小smoke通过。uvicorn0.35 graceful shutdown恢复并重发SIGTERM，因此自发停止的实际exit=-15合法，测试精确允许0或-SIGTERM；源码依据保存在uvicorn-signal-behavior.log。回执始终PENDING/null。

当前HANDOFF/README/设计/安全/验收/A2-report/stage已同步IN_PROGRESS/待独立验收及可独立执行的启动步骤；最新文档尚需最终重跑链接/逐字流程。contracts/execution旧future/pending query说明已修，字段语义未改变。

## 测试版本绑定与实际命令

final-r2构建/强制安装exit0，Linux amd64 Python3.11.17 UID501，原精确locks/setuptools80.9，PG16，独立下游DB。wheel携14 SQL，父子import witness留存，尚未做最终全记录审计。`copy-current-r2-binding.json`逐字绑定274项，`wheel-inventory-r2.json`保存最终wheel完整成员哈希。暂停主树与该测试copy比对，仅以下后续文档不同：`tasks/A2-report.md, docs/security-model.md, docs/oauth-oidc-sm2-mvp.md, docs/acceptance.md`；源码/测试一致。该copy是具体被测版本，不能以旧日志替代新文档检查。`pause-r2-candidate-observation.json`记录主树实际tracked/untracked/mode/hash及Git，主控另做最终暂停freeze。

下表测试统计为实际JUnit的 tests/failures/errors/skips；exit2为用户中断，exit127为暂停后禁止后续Python执行，**NOT_RUN**而非业务失败或通过。其它无JUnit步骤只能按实际命令与断言记录。全部更早失败/r1/r3/r4与过渡旧final仍保留，详见run-registry；表内部分节点通过不构成95项完成。

| 命令 | 实际exit | JUnit tests/failures/errors/skips |
| --- | --- | --- |
| source-final-r2-nonintegration | 0 | 1022 / 0 / 0 / 0 |
| source-final-r2-integration | 2 | 1141 / 0 / 0 / 0 |
| wheel-final-r2-nonintegration | 127 | — |
| wheel-final-r2-integration | 127 | — |
| historical-a2-original | 0 | 482 / 0 / 0 / 0 |
| a1-original-ag_review_probe | 0 | 4 / 0 / 0 / 0 |
| a1-original-ag_review_f2 | 0 | 1 / 0 / 0 / 0 |
| a1-original-ag_review_upgrade | 1 | 1 / 1 / 0 / 0 |
| historical-b-original | 2 | 47 / 30 / 4 / 0 |
| a1-upgrade-equivalent | 127 | — |
| historical-b-equivalent | 127 | — |
| a1-current-unit | 127 | — |
| a1-current-pg | 127 | — |
| source-independent | 0 | 26 / 0 / 0 / 0 |
| wheel-independent | 0 | 26 / 0 / 0 / 0 |
| source-local-boundary-original | 0 | 7 / 0 / 0 / 0 |
| wheel-local-boundary-original | 0 | 7 / 0 / 0 / 0 |
| source-a22-independent | 0 | 138 / 0 / 0 / 0 |
| wheel-a22-independent | 0 | 138 / 0 / 0 / 0 |
| oracle-controls-60 | 0 | 60 / 0 / 0 / 0 |
| wheel-process-witness | 0 | 2 / 0 / 0 / 0 |
| wheel-db-witness | 0 | 132 / 0 / 0 / 0 |
| wheel-http-db-witness | 0 | 30 / 0 / 0 / 0 |
| clean-docs | 0 | 2 / 0 / 0 / 0 |
| source-readme | 0 | — |
| wheel-readme | 0 | — |
| source-demo | 0 | — |
| wheel-demo | 0 | — |
| probe_oracle_scheduling_repeated-original-current | 1 | — |
| probe_oracle_scheduling_repeated_adapted | 0 | — |
| response-unit-smoke-r2 | 0 | 3 / 0 / 0 / 0 |
| response-pg-smoke-r2 | 0 | 3 / 0 / 0 / 0 |

## 已知失败与中断

- 首轮new-pg-r1 129失败，共同硬编码tenant-demo与真实tenant-001不匹配；修正后r2 127通过/3失败：两处测试漏捕获RESOURCE_NOT_FOUND、TLS配置tuple被严格JSON拒绝。按真实类型/JSON数组修正。
- r3导入编辑误将VerifiedInvocation落入query目的tuple，主动SIGINT exit2并精确修复；r4 297通过/1失败为uvicorn停机exit预期，上述小TLS链已补证。恢复前空stdout格式化事故与恢复依据保持原件，恢复后未再使用旧format_owned.py。
- permission补充测试曾误用scope/chain字段名，首小轮2失败/17通过；修正后通过。追加HTTPprobe最初重签未变token导致可信leaf原件不一致，改为保原token触发所需真实资源拒绝；跨租户身份本来401 HOLDER_MISMATCH，按冻结分类解释，失败原件保留。
- 历史A1升级原件固定期望仅002，当前实际002—006，原失败已保存；对应等价adapt尚未运行（暂停gate127）。历史B原件用户中断，不声称完整原失败已确认。oracle原调度重复probe失败及等价适配成功均保存。
- 旧pre-response-bound整段PG主动停止exit2并保原件；最终r2源码PG再次因用户暂停SIGINT。最终wheel普通/PG、A1单列和历史等价组均未开始，不用旧952/1388替代。

## 停止、资源及恢复

暂停时对自有venv的`bin/python`仅改名`python-paused`阻止已运行logger封装自动开启后续测试，再SIGINT本轮pytest，保其输出/JUnit/exit。logger正常结束；后续计划调用精确exit127，未启动Python测试。最后容器进程观察仅sleep PID1及观察脚本，无pytest/gateway/worker。所有exec会话已完成。

`pause-cleanup-r2.json`核自有Python/PG完整ID及owner=`a22-worker-resume-r2-20261004`与创建metadata一致后按ID删除，network亦按ID/owner删除，三个cleanup exit0。自有容器/network余留0，private-password删除。三个无关容器前后仍原完整ID/running，未连接或改动。宿主自有copy/venv/wheel及全部日志保留为证据，不删用户workspace。

明确恢复后：先核主控pause指纹/Git及本报告，仍承接同一包；按新独占owner重建Linux/Python3.11/PG16，不直接运行manage.py复用已销毁owner或硬编码旧资源；现有venv python-paused仅历史环境，不作为最终运行证明。保全部失败日志，新轮不同label/目录。先补copy包含全部当前控制包文件并使文档与主树一致，精确locks/setuptools80.9重建source/非editablewheel/14SQL/父子来源；短真实invoke/query/TLS冒烟后完整source/wheel普通+PG、历史B原件完整重跑与A1/B等价适配、A1单列、独立探针、oracle/README逐字两旧流程+新gateway启动及新文档全链接、lint/format/diff。最后逐项95→实际节点/断言/exit/JUnit/hash及限制，资源清理并停写，交fresh reviewer；不能只以本次通过的片段标READY。

本报告与evidence-index-pause-r2.json生成后即原生完成停写，交主控保存正式checkpoint与暂停指纹。
