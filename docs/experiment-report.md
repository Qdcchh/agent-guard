# A3.4 实验报告（联合实施自查，整体仍为 PARTIAL）

状态：**联合实施自查；本轮不构成 IMPLEMENTATION_ACCEPTANCE，不自 ACCEPT。**
A3.1/A3.2 已正式独立接受；A3.3/A3.4 联合 v1 已 PACKAGE_READY。本报告记录唯一整合者在本轮冻结候选上的**实际运行结果**与**明确 NOT_RUN** 项；
结论均有条件，完整联合自查/全新 Astra/high 独立复验完成前不得把任何子项当作阶段通过。

本报告的原始证据（private/public 原件、native 退出、STOP/manifest）位于
`artifacts/workflow/A34-opencode-resume-b0e3503a-1496-4d97-af71-a5d43c0a86b4/integration/`（ignored 本地证据目录，SHA 另列）。
代码/测试/SQL/fixture 指纹以该目录 `candidate-freeze-at-official-r2.json` 为准；不得以 HEAD 代替 dirty 候选。

## 1. 固定实验调度（不可按性能改样本）

- 官方性能安装固定 **wheel 非 editable**；source 与非 editable wheel 各自做功能/安全复现，统计不混用。
- 4 模式（staticACL、realSM2delegation_noAtomic、complete、realSM2Bearer）× 2 seeds(2026100501/2) × 5000 = **40000 measured**，
  其中 complete = 10000；每重复 250 warmup 另计、**2000 明确排除**。
- 真实在途 **50** 槽位；首波 50 个真实 pending 由 barrier 释放并记录实际 send/end 峰值（配置推断不算）；
  `complete` 另含全部 receipt/READY/anchor/export 成本；Attack 10 类×100、Retry 500（fresh/sameproof/terminal/loss）全保。
- 每个实际 invoke 一条 public JSONL；`invoke_write=OBSERVED` 只给真实完成的 HTTP 请求（HTTP 错误响应仍是 actual），
  预发送连接失败/写未知保留为失败行并**不能**充作 measured invoke；缺行/重复/身份不符一律 INCOMPLETE。
- 四个原生有限义务：`runner.py::run_official_mode_repetition`、`microbench.py::run_real_crypto_microbenchmark`、
  `microbench.py::run_independent_database_trace`、`microbench.py::run_independent_tls_roundtrip_reference`；
  另加 SM2 sign/verify/SM3 各 1000+50、独立 DB trace 与真实 CA/SAN TLS 空 RTT。

## 2. 本轮实际修复与自查（候选绑定）

本轮在授权 runner/statistics/unit tests/测试基线路径上完成了必要的正确性修复，全部失败原件保留：

- `_no_atomic_controls` 由仅 round 0 改为**每安装 10 个有效轮**，每轮独立 task/凭据/租约状态，真实 SIGKILL/wait=-9、
  lease/fencing、撤销、key 停用、TTL 锁等待与 replay/current-state 负例全部保留（`tests/integration/test_a34_baselines.py`）。
- 研究模式 multiwave：resume 不再要求生产 audit signer（研究能力 N/A）；complete multiwave：
  bootstrap/freeze 的 live_drain 前刷新已退出 writer launcher 的真实 hold actor；publisher 每波凭据只持久化本波任务
  （修复 64KiB JSON 上限与 exact-set 检查）。
- 写观测：`counted_send` 只计底层写成功的字节；发送抛错→`UNKNOWN`、连接前失败→`NONE`，二者都保留进失败/时延统计但不能补足
  actual 分母；首波 50 pending 与 actual=planned 作为官方 COMPLETE 前置，单独回归覆盖。
- 每波控制文件在 4 个 reader 容器内独立复核 SHA-256/mode/tasks（fail closed；无陈旧 fallback）。
- 数值攻击 class6 传输修复（root 纯依赖镜像 preflight 确认）：严格 canonical encoder 在真实 HTTP 发送前拒绝
  `-1`、`1.5`、`2**53`，使每类 100 case 中的 60 个到不了线上。修复只改测量攻击材料路径：普通 JSON 编码器输出真实畸形字面量，
  `RoleTLSInvocation.send` 记录 `body_binding=RAW_MALFORMED_NUMERIC_NONCANONICAL` 与 proof 绑定披露；生产编码/签名/校验零改动。
  回归覆盖 5 变体×4 模式×100 case 的真实 `_native_attack` 字节与真实 `GatewayEndpoint.schema` 400 拒绝。
- 修复后定向实跑 `probe8-numeric-class6`：2 波×50 真实客户端，100/100 OBSERVED、全部 HTTP 400、5 变体各 20、
  首波峰值 50、failures/operator errors 0、native 0（真实父等待）、资源 0。完整 40000 在全新 r4 谱系重跑。
- 持续负载回归 `probe7b-sustained-15w`（staticACL，含 r2 失败批 T0550–T0599）：15 波 3600 OBSERVED、0 unknown/failures、
  operator 0 error、首波 50 pending、native 0、资源 0。

实际自查（最终候选，wheel 安装）：
- `probe5-complete-3w`：3 波 × 250 actual，每波 200 accepted/terminal/READY/anchor、150 exports，native wait 0，资源 0。
- `probe3-staticACL-3w`：3 波 × 250 actual，native wait 0。
- `pilot3-complete-o450`（最终源）：250 actual、peak 50、50 个真实响应丢失 + 50 fresh retry，native wait 0。
- 对照基线（轮6）：source 与 wheel 各 12 节点全过（0 fail/error/skip），每安装 10 轮 noAtomic（root 高水位 140000 真实双提交）
  与 10 轮 full 对照（≤1 接受/占用 70000）、10 轮 kill/lease/fencing/TTL（每轮 TTL 均实际观察锁等待、kill wait=-9），
  host ruff/format 0，精确清理 0 残余。
- 统计/编码/子进程回归 21/21 通过（容器内，含真实发送抛错与 HTTP 500 正例）。

## 3. 官方 40000 运行（wheel，实际状态）

官方 r2 谱系按固定顺序 sequential 运行（4 模式×2 seed），每个配置由有限 detached supervisor 真实 `wait` 外层 native 退出并落盘；
`runner-outcome.json` 内 `native_exit` 保持 null（进程内不可自观测）。**逐配置实际结果以最终 manifest/STOP 与各 run 目录为准**；
写稿时状态：谱系运行中（详见本目录同源证据的 queue 状态与各 `official-*/<uuid>` 目录；未完成配置在最终清单中逐条列明，
未运行即 NOT_RUN，不以启动代替完成）。

统计口径：nearest-rank `ceil(p*n)-1`，all/failed/legal/attack/retry/tool/class 各自 n 与分母；attempt/authpass/newaccept
用首 send 到末 end 的 send-response 窗口；terminal/READY/anchor 各自 completion/drain 窗口单列；失败/timeout/SQLSTATE/全部
异常保留；600s drain 末完成部分仍 INCOMPLETE、后台事件保留。

## 4. 原 30 目标逐项（本轮实际状态）

“上游已接受”指 A1/A2/B/A22/A23/A31/A32 历史正式接受记录（本轮**没有**重跑，不等于本轮候选 PASS）；“本轮实跑”仅指上文实际执行。

| ID | 原行为 | 本轮实际状态 |
| --- | --- | --- |
| M1 | 登录、同意、授权码换SM2 ID/Access Token | 本轮 NOT_RUN（绑定 A1/B/A2 上游已接受；须由联合自查/独验实跑闭合） |
| M2 | planner→selector→executor两级委托 | 本轮 ACTUAL_RUN：A34 真实 AS 三层 token 路径（probes/pilots/baselines） |
| M3 | DID解析与企业注册绑定 | 本轮 NOT_RUN（上游 A1/B 已接受；须联合复跑） |
| M4 | 盗取token但无绑定私钥 | 本轮 ACTUAL_RUN：Bearer 对照与 full 零效果（baselines/unit） |
| M5 | 参数/令牌替换及proof重放 | 本轮 ACTUAL_RUN：replay/current-state 负例每轮（baselines 10 轮）与官方攻击行 |
| M6 | 根1000元，两分支同时各700元 | 本轮 ACTUAL_RUN：noAtomic 真实双提交 root 高水位 140000 vs full ≤1/70000（10 轮） |
| M7 | 下游成功但响应丢失 | 本轮 ACTUAL_RUN：o450 真实响应丢失 50 + fresh retry 50、UNKNOWN 保留 |
| M8 | 根/中间授权撤销及接受竞态 | 本轮 ACTUAL_RUN：撤销/恢复、TTL、lease/fencing 每轮 10 次 |
| M9 | 回执验签与关联 | 本轮 ACTUAL_RUN：complete probes/pilots/official 的 READY+anchor（pending 0/unanchored 0） |
| M10 | 无模型API的干净部署 | 本轮 NOT_RUN（A33 六根部署须联合复跑） |
| M11 | 双code创建同任务根、重复同意、过期后重建 | 本轮 NOT_RUN（A33 场景须联合复跑） |
| M12 | 重复SKU、空/缺失约束及错误报价关联 | 本轮 NOT_RUN（A33/A2 场景须联合复跑） |
| M13 | 锁等待超过proof TTL、子撤销后的交换重试 | 本轮 ACTUAL_RUN：TTL 锁每轮真实等待+STALE_REQUEST；撤销负例（baselines 10 轮） |
| SEC-01 | SM2/SM3 标准向量及跨实现验签 | 本轮 NOT_RUN（microbench/向量须在官方后执行并闭合） |
| SEC-02 | 规范编码与严格解析 | 本轮 ACTUAL_RUN：编码/严格解析单元回归与 runner 严格校验 |
| SEC-03 | AS签发的根和两级委托，三个holder | 本轮 ACTUAL_RUN（A34 真实 AS 路径）；三 holder 独立容器部署本轮 NOT_RUN |
| SEC-04 | 请求精确绑定 | 本轮 ACTUAL_RUN：canonical body/digest/identity 校验与官方行 |
| SEC-05 | AG-Proof抗重放与业务幂等 | 本轮 ACTUAL_RUN：replay 负例+REPLAY/EXISTING/IDEMPOTENCY_CONFLICT |
| SEC-06 | 祖先撤销与竞态 | 本轮 ACTUAL_RUN：撤销提交顺序与恢复（baselines 10 轮） |
| SEC-07 | 入口与凭据隔离 | 本轮 NOT_RUN（A33 角色/挂载矩阵须联合复跑） |
| CON-01 | 多分支竞争根额度 | 本轮 ACTUAL_RUN：10 轮 noAtomic/full + 官方 class9 对 |
| CON-02 | 中间祖先额度 | 本轮 ACTUAL_RUN：逐祖先四 counter 断言（baselines） |
| CON-03 | 调用次数 | 本轮 ACTUAL_RUN：calls 预留/结算与 UNKNOWN 保留（baselines） |
| REC-01 | 故障矩阵 | 本轮 ACTUAL_RUN：真 SIGKILL/lease/fencing/UNKNOWN（baselines 10 轮） |
| REC-02 | 迟到成功及多恢复者 | 本轮 NOT_RUN（联合故障矩阵须复跑） |
| REC-03 | 报价快照跨执行与恢复一致 | 本轮 NOT_RUN（下游快照矩阵须复跑） |
| AUD-01 | 证据验证 | 本轮 ACTUAL_RUN：complete READY/anchor 与 export 包（S/H/trust/latest/pin） |
| AUD-02 | 检测边界 | 本轮 ACTUAL_RUN（有限结论）：未锚定尾部/外部 trust 限制保持 |
| E2E-01 | 正常采购与攻击演示 | 本轮 ACTUAL_RUN（A34 official 行）；A33 正常演示本轮 NOT_RUN |
| ENG-01 | 干净环境复现 | 本轮 ACTUAL_RUN（A34 wheel 非 editable 安装、真实 outer wait、资源 0）；README 外 cwd 逐字/A33 复现本轮 NOT_RUN |

## 5. 未运行 / NOT_RUN（诚实保留，不是通过）

- source 与非 editable wheel 各原 **20 inherited 全组**（PG5002 10800s、strict500 各 3600s）、A1/A2/B/A22/A23/A31/A32 全部义务的
  本轮联合复跑：NOT_RUN（历史 harness 入口与实测命令已索引，须在冻结候选+全新资源上重绑）。
- A33 actual691 场景与六 full deployment 根×2 模式十二 fresh、三 holder 四工具 256、维护 keyhistory/旧 READY 字节/非零升级/
  三域 backup-restore/README 外 cwd 逐字：NOT_RUN。
- 官方 40000 之外的全部配置、SM2/SM3 微基准、独立 DB trace/TLS 空 RTT、E4 完整闭合：见第 3 节逐条状态与最终 manifest。
- 视频/terminal.cast：未录制，不用动画代替（可选项，不作为阻断）。

## 6. 已知限制

下游结果 `ATTESTED_NOT_INDEPENDENTLY_PROVEN`；当前授权状态 UNKNOWN；bootstrap 管理员与外部 trust/latest 为可信假设；
未锚定尾部与独立审计检查点边界保持。研究模式差异为能力差额与真实成本，不构成单变量或行业优越性结论。
本轮失败原件（含历史损坏 XML 例外）原样保留，见联合 evidence 目录。

## 7. 证据索引（相对本仓库）

- 冻结候选指纹：`artifacts/workflow/A34-opencode-resume-b0e3503a-1496-4d97-af71-a5d43c0a86b4/integration/candidate-freeze-at-official-r2.json`
- 探针/试点/对照/官方原件：同目录 `measurement/`、`baselines/`、`selfcheck/`
- 联合包/需求/节点绑定：`tasks/workflow/runs/A3.3-A3.4-joint-20261013/{package-v1.md,requirements-v1.json,node-bindings-v1.json,runtime-plan-v1.json}`
