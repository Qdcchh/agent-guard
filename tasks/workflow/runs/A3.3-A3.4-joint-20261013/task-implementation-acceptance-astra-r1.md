# A3.3/A3.4 新 Astra high 完整独立实施验收

QUEUED_NOT_DISPATCHED：此文件不是授权 reviewer 提前审查或运行。只有主控确认最终唯一整合者真实 STOP、候选与实际完整自查证据冻结、自有业务资源清理后，另提供 activation/final-candidate 才可执行。

真人 2026-10-14 指定全新 gpt-6-astra/high reviewer，不能复用任何实施会话或历史 reviewer。review_kind=IMPLEMENTATION_ACCEPTANCE。完整原要求、联合 PACKAGE_READY、tasks/workflow/review-contract.md、implementation-contract.md 与原 task-joint-final-integration-v1.md 全部适用；只替历史 Sol 角色，不减少义务。不得调用其他 agent、修改受验源码/测试/文档/正式任务。写权仅后续分配独占 UUID evidence。无 Git 发布、额度监测、foreign 资源操作。

完整阅读 AGENTS/AGENT、README/HANDOFF、安全/接口/验收及全部联合 package-v1/requirements-v1/node-bindings-v1/runtime-plan-v1/ownership-v1/interface-v1、引用原要求与 delivery-experiment-contract、A3.1/A3.2 正式接受及历史缺陷、最新用户授权。185 父/177 运行、568 原子(269+95+73+71+60)、55 回归、6 注册、原30目标逐项建立实际实现/调用方/断言/测试/原件矩阵，不能只读实施者成功总结。

开始和结束独立核验所有候选 source/test/fixture/SQL/locks/配置/文档/周边依赖/未跟踪文件/包契约 SHA、Git status/diff；HEAD 只是基线。任何候选漂移使本轮无效。

独立新资源重跑完整 mandatory：Python3.11/PG16/真实 CA+SAN TLS/角色隔离；source 与非 editable wheel 各原20 inherited 全组，PG5002 原cap10800s、每strict500 原cap3600s；全部历史/当前等价探针、A33 actual691场景原断言、六full deployment根×2mode十二fresh、正常三holder四工具256、旧READY字节/非零升级/三域backup-restore/维护keyhistory/README外cwd逐字；适用竞态和真实 kill/restart 各安装10有效轮。仅原两个selfcontained deploy文件可host pytest --noconftest，其他正常conftest不能绕过。检查反例是否真实触发，不能用全绿数量代语义。

独立 wheel 正式4mode×2seed×5000=40000/full10000、warmup2000分离、50实际pending与全部原DAG/攻击/重试/response-loss行；SM2sign/verify/SM3各1000+50、标准向量/OpenSSL、独立DBtrace与TLS空RTT、真实CPU/RSS/WAL/storage/全统计n和分母/600s drain/READY-anchor/全task与预冻结分区完整E4 export、trust/history/pin/wholeattempt-effects-manifest/spoolpeak。不得提高caps/丢数据/无条件分页或用历史PASS代独立fresh。真实noAtomic两commit/DS140000/root高水位140000，对照full最多一接受/effect70000，全部祖先独立oracle及研究production写0。

所有长运行有限detached实际父wait/native落盘；runner-outcome.json进程内native_exit=null不能当native0。独占UUID TEST-only三PG/TLS资源，fullID+owner只清自己，finally清理。原始日志私密保存；公共脱敏另存派生副本，不覆盖原件。

须特别审查已披露的证据例外：本轮 baselines worker 原地脱敏了部分历史失败stdout/XML；两份XML含未转义标记而损坏。主控没有声称原字节完整或伪造恢复。根证据 baselines-root-readback.json、historical-evidence-supplement.json 与 historical-redacted-xml-derived/index.json 明示当前保存状态与可读派生副本；原私密OpenCode transcript仍在。成功分段XML/真实wait已核，但不能据此免除本轮fresh完整独验。独立评估此缺口和覆盖，不隐瞒或自动关闭。

按 templates/review.md 提交完整 REPORT.md、矩阵、所有原件manifest含nested STOP、开始结束指纹和真实资源0、STOP/no_more_writes。结论仅 ACCEPTED/NOT_ACCEPTED/BLOCKED 的审查建议；必需项未运行不得 ACCEPTED，具体阻断附真实触发/文件行号/证据/最小修复与复验要求。主控保存原报告并独立核验后才可正式联合接受。

追加已知问题输入（非已关闭）：本轮整合 official queue 曾用全局镜像前后差推断可删除镜像，未执行注释所说的自有run目录核验；root已暂停队列/worker并要求只基于精确child/run/full-ID归属。首个staticACL actualwait1 FileNotFoundError；第二个noAtomic被root SIGINT，父queue已停止故native UNKNOWN，业务finally清理0。详见本轮integration/controller-queue-ownership-pause.json、queue-interruption-resource-readback.json、resume2-message.txt。新review须确认最终脚本修复与全部新lineage实际证据，不能把这些失败/中断改写成功。

追加必查：controller-measurement-validation-pause.json/resume3-message.txt指出发送前connect失败行可被validate_actual_rows计成COMPLETE、推送wave文件的docker cp allow=True可能沿用旧文件、queue-r2注释宣称但未实际校验run.json归属。须检查最终修复/真实负例与全部实际send依据，禁止把无HTTP发送的占位行补足5000/40000；保留失败原件，HTTP已发送后的错误仍应统计。

发送证据补查：controller-write-observation.json/resume4-message.txt指出计数器在original_send返回前递增，立即失败会被误认OBSERVED。必须检查最终下层实际写入观测和直接触发该路径的回归；无法确认的部分发送应如实UNKNOWN，不得填充分母。progress历史有猜测UTC，最终原件须实际时钟/PID/wait依据。

正式队列元数据补查：主控 official-queue-r2-provenance-root-note.json 记录 queue-r2 使用 run/owner 读取实际 run_id/owner_id 字段导致误报，且未将 provenance_error 纳入停止条件。没有自动镜像删除。最终须核每个真实 child/native/run_id/owner_id/资源ID及候选SHA；保留原记录、派生修正，不把错误元数据当作已核身份。
数值攻击补查：root numeric-attack-preflight-root.json 证实旧 _native_attack class6 的 -1/1.5/2**53 被客户端 strict canonical encoder 拒绝，影响每100例中60例；r3被精确中止，真实父wait -2，不能计正式成功。修复改为仅测量攻击路径输出真实非法数值 JSON，保留真实原proof并明确body/proof绑定；生产编码/签名/校验不变。probe8-numeric-root-readback.json已核100实际OBSERVED/五种各20/HTTP400/peak50/native0/resources0，且27unit通过，但不代替完整fresh40000或完整验收。独立确认生产schema先于proof验证，拒绝确为数值攻击；注意当前helper注释误称strict canonical encoder拒绝true，实际上true与0可编码但工具schema拒绝，最终文档/注释应准确。不得将该说明差异当作伪造试验成功的理由，也不得忽略正式全量复验。
