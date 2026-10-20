# A3.1 IMPLEMENTATION_ACCEPTANCE — NOT_ACCEPTED

本轮建议 **NOT_ACCEPTED**。稳定阻断 ID **A31-IA-R1-001（P2）**：新增 ledger accept 回调在默认未启用 audit stream 的任务上等待到 proof/token 过期后，返回 `None` 仍能成功提交。独立 source 与非 editable wheel 各运行完整 14 个新探针，均 **8 PASS / 6 FAIL / 0 ERROR / 0 SKIP，native exit=1**。不是静态疑点或测试参数中的 `[FAILED]` 字符串。正式候选未改；已真实 STOP，自有资源为 0。

请求配置 gpt-6.1-sol/high；可核有效模型与 reasoning metadata 均 **UNKNOWN**。真人后续明确 reviewer Sol/high 覆盖早期文件中的其他配置措辞。本报告仅作独立 reviewer 建议，不自行接受，不进入 A3.2/A3.3，不发布 Git/PR/CI。

## 阻断与最小补正

[issue JSON](issues/A31-IA-R1-001.json) 与 [实际证据](independent-deadline-defect-evidence.json) 绑定两个 fresh mode 的原生 command、raw、XML SHA、14 个节点结果和 12 条真实 DB clock 观察。

`src/agent_guard/ledger/service.py:405` 新 `before_create`，`:384` / `:463` 新 `after_link` 都允许 `None` 返回。`:397`（EXISTING）与 `:477`（CREATED）仅在 `binding is not None or baseline is not None` 时调用 `_final_bound_check`。默认 legacy 任务的两者均为 None，因此新回调后的最后 DB clock 没有执行。独立比较冻结候选与原 HEAD 确认这两个 optional hook 属于本次新增调用链。

六个场景为 before-created / after-created / after-existing × proof / token。每个先验证无回调的旧默认正例 RESERVED，再设置真实新 deadline，通过回调中的同一实际 PG connection 查询 `clock_timestamp()`，有限等待至 DB 整秒 `target+1`。回调返回 None。期待 proof `STALE_REQUEST` / token `EXPIRED`，且全部 ag 表不变；实际 CREATED / EXISTING 成功、error=None。CREATED 改变 ag_event_seals、ag_grants、ag_ledger_event_nodes、ag_ledger_events、ag_operations、ag_proofs 六表；EXISTING 持久新增 ag_proofs 关联。两 mode 十二次全部实际跨秒，没有 mock clock、TTL 放宽、删除原 assertion 或 skip。

这是明确使用 synthetic trusted A1 invocation 的 **可信 ledger API 新 callback 边界**；本证据不宣称公开路由的签名验证可被绕过。正式 A31-S01.04 要求任何新增等待后都执行最后 freshclock/fence；原已签描述符或已启用 stream 分支通过不能证明此默认分支。

最小补正应让 CREATED 中执行过的 before_create / after_link、EXISTING 中执行过的 after_link 都触发末尾 `_final_bound_check`，即使 binding/baseline 均为空；保留既有 locked-row reload、deferred flush 后最后 DB clock 及旧默认正例。保留本轮原失败与全旧门。补正后必须由另一 fresh reviewer 完整重新执行两 mode 全20与各 clock1000；本轮结果不能通过只重跑六例转为接受。

## 本轮独立完成范围

每 mode 都新建物理 PG/audit/Py，Linux UID501/Python3.11，Py768MiB、PG512MiB、无 host ports，独立 private/fullID/PID/DB。角色 reviewer-source / reviewer-wheel，formal fixture UUID 保持 78baf870-8f66-4961-9e24-8f4554e65c65。所有标签、mount、cap、owner JSON、正常安装、16 SQL/original14 SHA 与模块来源独立核验。source 为正常非 editable source install；wheel 为本轮 fresh PEP517 wheel install。没有借用 integrator 资源、native PASS 或日志作为独立通过证据。

| 实际完整组/探针 | source | wheel |
|---|---:|---:|
| prerequisite TLS/GW receipt/短 proof/segmented TLS | native0；51/33/1/22 节点 | native0；51/33/1/22 节点 |
| selected ordinary whole | 1338 XML，native0，0F/0E/0S | 1338 XML，native0，0F/0E/0S |
| selected current PG nonclock whole | 4222 XML，native0，0F/0E/0S；5635.571s | 4222 XML，native0，0F/0E/0S；5610.949s |
| 新独立 priority14 whole | 8P/6F/0E/0S；native1 | 8P/6F/0E/0S；native1 |
| 余18 selected（含 clock1000） | NOT_RUN_AFTER_CONFIRMED_FAILURE | NOT_RUN_AFTER_CONFIRMED_FAILURE |

完整4222与普通1338保原集合、所有参数和原 assertion，核 actual nodeids 精确等于本轮独立 collect、raw/XML SHA 与 command；退出码/child returncode 均0、timeout=false、detached=[]。当前整组包含两套原60个真实 SIGKILL/newPID/recovery 场景与相应原10轮断言；独立14另列，不能替代全20闭包。

按主控最新明确授权，两个4222完成后，将新增安全边界探针提前到长继承组之前；实际阻断后停余18。旧 full pipeline 在预置 `FileExistsError` 控制边界退出1，边界没有执行后续 native command，保留原 terminal/raw；这是调度停止，不是产品组失败。两个 priority supervisor 自然退出1，对应实际14失败，无超时或孤儿。不能声称全20或 clock1000已跑通过，也不能借历史四个 clock500 日志填入本轮。

[完整40组状态及 raw/XML/native 指针](selected40-independent-evidence.json)、[141父需求](requirement141-matrix.json)、[133运行旗标](runtime133-matrix.json)、[269原继承子义务](inherited269-matrix.json)、[95新原子：88运行/7 native](atom95-matrix.json)、[完整 native 门与原30目标范围](native-obligations-matrix.json)、[汇总](review-summary.json)。每项保原 must_assert、源码 assertion SHA、原参数/source 映射和真实已跑/未跑状态。共享组选中完成只证明表中声明范围；整体 NOT_ACCEPTED。A32/A33/A34 内容继续 NOT_RUN，项目不接受。

## 深层审查及运行适配边界

亲读正式任务/版本、需求/契约/原始文档/既往问题/原断言映射，并沿 ledger accept→可信 material/binding→journal capture/append/head→final clock、terminal owner/fence、receipt publication/query、delivery signer lock/lease/ACK、reader reconciliation capability/page/history/pin、lineage/migrations、原 SDK import/provenance/安装链核可信边界。实际新探针另含 copy/replace/直接构造/改 parent capability 与真实 TLS wrong pin/reorder/duplicate page 的7项恢复正负例，以及真实 reader append403/writer append200/reader latest 的1项，均通过。

允许适配仅在自有 prepared runner/test venv 内：source 官方 ARM BusyBox native proc observer、fresh owner/gate env、真实 Z 分类、查询 QUERY oracle 的 provenance/journal 等价解释、独立实际 normal SDK provenance。增强三个原探针原 assertion/decorator、80真实跨秒、签名、TTL、SIGKILL保持；本轮已亲审等价语义/小控制，但增强余组选中在阻断后 NOT_RUN。enhanced `.pth` 限本轮 fresh test venv，未进入正常 SDK wheel/package；本轮生产候选未写。之前 preflight Z 分类/env 控制失败和 TLS collect count50实际51的装配错误原始证据全保留，修正原门表达/计数后本轮实际 prerequisite/control 完成；不作为产品失败或替代长期全组选中。

source primary identity 为官方 ARM kernel NUL argv，实际 UID/kernel start/PGID/SHA；Python/Rosetta marker 是另一观测层，SHA 不混称。原 source 两套60恢复场景有6个 replacement final row 恰落在空 argv 转换观测，已核存档，未回填 cached SHA、不据 cache 发信号；有限6个额外身份补充因真实缺陷停跑，明确 NOT_RUN。已自然退出的短命 forest 不另加“每PID必须有raw argv”的新产品门。详见 native matrix 与保留原 ARM/raw/Registry。此身份材料缺口不被包装为独立补充 PASS 或新的产品问题。

本轮 source4222 natural cleanup 同步 observation 实际 **2.381650s**，wheel0.019476s；原 runner `budget_seconds=2` 在一次 `registry.alive` 返回后检查截止，是等待预算，正式任务没有要求总同步观察墙钟≤2。本轮观察返回空 live identities、无 signal；native observer 5s/join6有限 failclosed。记录实际超2事实，不机械判另一产品失败，也不宣称总耗时≤2。

## 冻结、原件归档与 STOP

独立首尾 inventory 均493（tracked/untracked/deleted/symlink/mode/bytes），HEAD `2a8cc7da4867ad1876350855c0ed5569c5ce6472`，branch `handoff/a23-local-20261005`；正式 freeze SHA **bb8ba41c72ecd0e8a81adde0c93e2e3ddf3dd8c5d0ea479b492220c54a7221b5**。全部6项 HEAD/branch/status/index/staged/unstaged controls 与冻结及首尾逐 byte 相同，stop record SHA一致。保护原 dirty/index；未误用父目录 Git。[首验](start-freeze-readback.json)、[终验](end-freeze-readback.json)。

[归档记录](archive-and-cleanup.json) 绑定 source7772/wheel7755 native普通文件：tar member bytes逐SHA核验、实际每文件UID/mode、各6 Unix socket原类型/元数据（无普通文件字节），private/sidecar原字节单独保留。少数早期 root 控制观测文件只读以UID0归档，保其真实UID，不chmod/chown、不冒称所有文件UID501。原 raw/XML/manifest 在本ignored目录，权限0700/0600；报告仅输出有限非敏感字段，不输出DSN/JWS/私钥。

两mode各4 aux DB通过owner comment/PG fullID门先cleanup native0；随后 exact原6容器/2网络/4匿名卷/2private全部实际 inspect/exists不存在，已知 supervisor/child/等待器均ps不存在。只读 collector此前精确UID/start/nativeSHA/PGID SIGTERM后实际absent、host143，为受控辅助停止。foreign verivote容器仅公开inventory读取，未连接/修改；主控wakeguard3551排除不signal。[最终实际STOP/资源0](final-STOP-resource-zero.json)。

本轮结束于 NOT_ACCEPTED / OPEN A31-IA-R1-001。正式补正由主控安排；本 reviewer 不再写候选或运行后续阶段。
