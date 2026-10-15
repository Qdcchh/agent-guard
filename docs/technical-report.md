# 技术与实际交付范围

整体状态仍为 **PARTIAL**，本段不构成阶段接受或独立验收。A31/A32 已正式接受；A33/A34 联合 v1 已 PACKAGE_READY，
唯一整合者正在最终候选上执行完整联合自查，全新 Astra/high 独立复验尚未开始。原文档、失败与验收记录保持原文。

正常交付基于现有 SM2/SM3 SDK、真实 AS 签发与持钥 proof、当前 authority 状态与原子全祖先预算、独立 DS once-effect/lease
恢复、独立 audit 检查点、bounded export 与 offline。RSA TLS 加 SM2 应用签名不称全 GM TLS。私密 host 桥不向 holder 授新控制权，
不共享 login 凭据作 host 认证。四工具固定 `tool_version="1"`，金额为 CNY 整数分。

本轮实际完成（冻结候选绑定，详见[实验报告](experiment-report.md)与联合 evidence 目录）：
- A34 官方调度/研究对照的实测能力修复：每安装 10 个真实 fault/权限控制轮；`invoke_write` 只认真实完成的 HTTP 写，
  预发送失败不能补足 actual 分母；首波 50 pending 与 actual=planned 作为 COMPLETE 前置；每波控制文件在 4 个 reader 容器内
  独立 SHA-256/mode/tasks 复核；complete multiwave 的 writer 句柄与每波 publisher 凭据按波隔离。
- 对照基线 source 与 wheel 各 12 节点全过（真实 PG16/TLS/进程，0 fail/error/skip），含每安装 10 轮真实竞态与 10 轮
  kill/lease/fencing/TTL；统计/编码/子进程回归 21/21。
- 官方 wheel 4 模式×2 seed×5000=40000（complete 10000，warmup 2000 排除，真实 50 槽位）按固定顺序实际执行；
  逐配置 native 外层 wait 落盘，资源 full ID+owner 精确清理。

四个原生义务：`runner.py::run_official_mode_repetition`、`microbench.py::run_real_crypto_microbenchmark`、
`microbench.py::run_independent_database_trace`、`microbench.py::run_independent_tls_roundtrip_reference`；
SM2 sign/verify/SM3 各 1000+50，独立 DB trace 与真实 CA/SAN TLS 空 RTT 只作独立参考，不从总时延做精确分解。

下游证明 `ATTESTED_NOT_INDEPENDENTLY_PROVEN`、当前授权 UNKNOWN、独立公开 trust/latest 外部保存、bootstrap 维护管理员
可信边界与未锚尾部局限保持。并非绝对安全或生产级保证；研究模式差异是能力差额与真实成本，不构成单变量/优越性结论。
未完成与 NOT_RUN 项（见实验报告第 5 节）在全部闭合前不得 ACCEPTED；source/wheel 各原 20 inherited、A33 完整矩阵、
原 PG5002/strict500 预算、维护/README/256 与全部历史/等价探针仍须在最终冻结候选上复跑并由新 reviewer 独立执行。
