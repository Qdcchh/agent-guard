# COSM2 基准（A4）

只测真实实现。冻结 core API 已可测三轮与总时间；`--with-gateway` 启用真实 AS 全链、SELECT-only PostgreSQL 授权谓词，以及真实 HTTP/ASGI 网关受理。未启用时这两项如实记录 `n=0`、`NOT_MEASURED` 和 disabled reason；`--require-complete` 对任何缺项或失败退出2。B6/B9稳定后已完成本环境正式测量，正式来源为 `results/20261017-full-02/`，九项均n=100、预热10、零失败。

历史 `results/20261017-measure-a3a4-01/`（含失败）及 `...-02/`（当时部分实测）保持原样，不能与新轮拼接。`results/20261017-full-smoke-01/`为2+1冒烟；`...-full-01/`虽然计时全部完成，但输入env的镜像ID截断，保留原样并排除正式来源。主控核对实际完整镜像ID后，新`...-full-02/`独立重测全部九项，未拼接。目录必须全新，失败也保留，再用新run_id。每项10次预热和100次正式；九项共900条正式记录、90条预热记录。无删除异常值、无混环境。

| 指标 | 实际计时边界 |
|---|---|
| cosm2_round1 | P1 round1，排除 keygen |
| cosm2_round2 | P2 round2 密码计算，不含谓词/数据库 |
| cosm2_round3 | P1 round3，包含铜锁最终 SM2 验签 |
| cosm2_total | 同一次签名的 round1 至 round3，包含最终复验，无数据库 |
| cosm2_round2_db | Q1 提前准备，计时只含真实 AS 全链验证、SELECT-only DB 全祖先谓词与 P2 round2；最终 P1 round3/复验在计时后完成以清理nonce |
| sm2_sign | 铜锁签名，排除生成密钥 |
| sm2_verify | 铜锁验签，含 public_key() 提取 |
| frost_sign_quorum | Python 写行动文件、Rust 进程启动/I/O/真实2-of-3签名、Python Ed25519复验，排除 enrollment |
| gateway_e2e | 请求发出至 HTTP 202 RESERVED 响应，含真实验权、批准验签与数据库受理；请求bundle/proof/共签/header/原始请求准备均在计时前，排除下游worker、订单效果和回执 |

两个数据库适配器各自创建并释放独占schema、独立下游DB、临时SELECT-only角色，绝不清理外部资源。round2_db不预留。e2e每个预热/正式样本使用新的业务幂等键，AS签发足够的合成金额及次数额度；结束校验110个不同键、110个operation、110条批准、三个祖先均预留7700000分/110次、settled0、下游订单0。不能用幂等重试替代新受理。秘密份额仅临时0700目录/0600文件，结束删除；raw/summary不保存令牌、份额、nonce或DSN。

`raw.csv` 与 `warmup.csv` 保留全部尝试及错误类型；`summary.json` 给每项n/median/p95/min/max/status/reason/attempts/failures。p95为nearest rank `ceil(.95*n)`。v2 summary记录全部九项边界、适配器错误类型和e2e计数证据；绘图重新计算全部统计，拒绝错误、混run/环境、丢预热、重复/不连续编号和不匹配的真实受理计数。三轮和不作为受理e2e。

运行必须使用固定镜像、完整镜像ID、CPU/宿主及runner架构元数据。当前固定runner为Python3.11/Tongsuopy1.0.1，amd64镜像运行在arm64宿主，披露Docker仿真；不同环境禁止拼接。FROST包含进程开销，不能拿该值声称算法本身优劣。

从仓库根使用主控提供的自有隔离测试网络和私有env文件（不得打印DSN）：

```sh
docker run --rm --pull never --network "$OWNED_TEST_NETWORK" \
  --env-file "$OWNED_RUNNER_ENV_FILE" -v "$PWD:/work" -w /work \
  -e PYTHONPATH=/work/src:/work agent-guard-threshold-gateway-runner:20261017 \
  /opt/venv/bin/python -m experiments.cosm2_bench.bench \
  --output experiments/cosm2_bench/results/20261017-new-unique-run \
  --samples 100 --warmup 10 --with-gateway --require-complete
python -m experiments.cosm2_bench.plot experiments/cosm2_bench/results/20261017-full-02 \
  --output '复赛冲刺材料-20261018/论文模板/figures/fig-latency.pdf'
```

`AGENT_GUARD_TEST_DATABASE_URL`仅来自该私有env；元数据还需COSM2_IMAGE、COSM2_IMAGE_ID、COSM2_HOST_CPU、COSM2_HOST_ARCH、AGENT_GUARD_THRESHOLD_DEMO_BIN（主控runner.env已有）。缺数据库配置不产生伪测量，summary记适配器错误且退出2。无`--with-gateway`可在无网环境测七项，完整要求仍退出2。

绘图仅使用既有工具依赖（`requirements-plot.lock`），不增加产品依赖。macOS工具环境及中文字体可参照历史A4资料；矢量PDF旁source.json映射run_id、数据SHA、命令、字体SHA、配色及所有计时边界。需要渲染PDF目视检查后再交付。

自查：

```sh
python -m pytest tests/unit/test_cosm2_bench.py -q
```
