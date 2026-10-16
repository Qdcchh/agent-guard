# A3.4 实验与对照基线包

状态：**联合实施自查进行中，整体仍为 PARTIAL；本目录不构成 ACCEPTED 或独立验收结论。**
A3.1/A3.2 已正式接受；A3.3/A3.4 联合 v1 已有 PACKAGE_READY，完整联合自查与本轮独立复验尚未全部完成。旧失败/旧停止原件保留。

## 1. 目录

| 路径 | 作用 |
| --- | --- |
| `agent_guard_bench/workload.py`、`workload-v1.json` | 冻结的 4 模式×2 seed×5000 measured + 250 warmup/重复 计划、攻击/重试/依赖 DAG 目标 |
| `agent_guard_bench/research_contracts.py`、`research_store.py`、`research_service.py`、`research_worker.py`、`research_evidence.py`、`research-schema.sql` | 研究专用 context/schema/接受/终局/租约；不进入生产 HTTP/ENV/SQL |
| `agent_guard_bench/static_acl.py`、`signed_no_atomic.py`、`sm2_bearer.py` | 三种对照模式（真实角色密码 hash、真实 noAtomic 无共享预算原子性、真实 SM2 Bearer 无 holder 持有证明） |
| `agent_guard_bench/runner.py`、`statistics.py`、`microbench.py` | 官方调度/真实 TLS 传输/oracle 记录/统计（nearest-rank、分母与失败保留）与三个原生微基准义务 |
| `baseline-capabilities.json` | 逐模式能力矩阵（含明确的 N/A 研究能力，不作为成功口径） |
| `../tests/integration/test_a34_baselines.py`、`../tests/unit/test_a34_*.py` | 真实 PG16/TLS/进程的基线自查与纯单元统计/编码回归 |

## 2. 官方固定计划（不可按性能改样本）

- 安装：官方性能固定 **wheel 非 editable**；source 与 wheel 各自做功能/安全复现，统计不混用。
- 4 模式 × 2 seeds(2026100501, 2026100502) × 5000 measured = **40000**（其中 `complete` 10000）；
  每重复 250 warmup 另计、明确排除，共 2000；每模式合计 legal 3500 + attack 1000 + retry 500。
- 真实在途槽位 50（首波 barrier 真实 50 个 pending，峰值来自实际 send/end 区间，不接受配置推断）。
- 10 类攻击各 100；class2 重放复用固定 legal T0000+ 的原 token/proof/body；class9 为 50 对共享 root 的预算竞争。
- 500 retry = 250 fresh-proof 原键 / 100 原 proof 原字节 / 100 terminal 后 fresh intent / 50 真实响应丢失后 fresh retry。
- 每个实际 invoke 一条 public JSONL 行；`invoke_write=OBSERVED` 只用于真实完成的 HTTP 请求；预发送连接失败保留为失败行，
  **不能**充作 measured invoke；missing/重复/身份不符按 INCOMPLETE 处理并保留全部原件。

## 3. 四个原生有限义务（各 ordinary 重复一次）

1. `experiments/agent_guard_bench/runner.py::run_official_mode_repetition`
2. `experiments/agent_guard_bench/microbench.py::run_real_crypto_microbenchmark`
3. `experiments/agent_guard_bench/microbench.py::run_independent_database_trace`
4. `experiments/agent_guard_bench/microbench.py::run_independent_tls_roundtrip_reference`

微基准固定 SM2 sign/verify/SM3 各 1000 measured + 50 warmup；独立 DB trace 与真实 CA/SAN TLS 空 RTT 只作独立参考，
不从总时延做密码/RTT 精确分解。

## 4. 运行与隔离

- 官方/研究运行必须新建独占 UUID 资源（三 PG16/TLS/角色/证据目录），只清理自有 full ID+owner 资源，
  不触碰共享/外部资源，不依赖 ignored 历史脚本。
- 长运行由有限 detached supervisor 承担：`stdin=DEVNULL`、文件 stdout、真实外层 `wait` 记录 native 退出；
  进程内 `runner-outcome.json` 的 `native_exit` 保持 `null`（父进程未观测时不得伪造 0）。
- 研究模式 fail closed：无预算写入生产库、无跳过验权开关；`staticACL`/`Bearer` 的 proof/审计能力明确 N/A。

## 5. 诚实边界（保持）

- 本轮仅实施方自查，结论均有条件；`ACCEPTED`/阶段放行只能由后续全新独立 reviewer 在冻结候选上完成全部实跑后给出。
- 历史失败、中断与损坏的自查 XML 原样保留；不得把历史 PASS 当新候选证据。
- 未锚定尾部、下游 `ATTESTED_NOT_INDEPENDENTLY_PROVEN`、当前授权 UNKNOWN 等限制见 [技术报告](../docs/technical-report.md)。
