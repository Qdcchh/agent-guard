# COSM2 图件与来源

本轮三张矢量 PDF 使用真实固定运行 `01af29ac-26be-4616-851d-d8afa38fa46e` 的结果与负例观察。该运行由本机会话的固定按钮启动，六用例通过，操作、批准、订单各 1，残留资源 0。全阶段完整独立验收仍另行进行；这些材料不是普适安全证明。

`fig-system.pdf` 与 `fig-protocol.pdf` 是已实现 B1-B7 的结构示意，不是运行事件回放。图中区分授权域与执行域，智能体不持有份额。安全模型为半诚实、n=2、同主机；参考曲线运算非常数时间，P1 独立进程不等于 OS 强制隔离。效果端独立验签的 B9 能力单独核查。

`fig-negative.pdf` 保留七攻击×四位置。8 个实际触发位置显示原样拒绝码，其余 20 格为 NOT_TRIGGERED，不推导通过或拒绝。AS 列没有观察到拒绝。网关验签列包含请求与批准绑定检查。来源文件含 12 条真实观察：原 9 条覆盖本矩阵及缺批准用例，另外 3 条效果端绕过拒绝保留在索引的 `additional_effect_observations` 中，不虚构第五列。

`cosm2-figures-sources.json` 包含同 run_id 的 `result.json`、`negative-matrix.json` 的路径与 SHA-256，逐格方案、位置、拒绝码、用例、运行标识与固定容器内脚本入口。命令字段表示实际固定内层入口，私有 DSN 通过临时 env-file 提供，未写入公开命令。本地可写 JSON 不是独立密码学证明。生成器拒绝错误身份、未知字段、重复键、布尔计数、未知或重复用例、失败或未清理运行、计数变化，以及只提供部分效果端观察的集合。

重建本轮三图：

```sh
python tools/cosm2_paper_figures.py --cosm2-run 01af29ac-26be-4616-851d-d8afa38fa46e
```

需要 ReportLab 和中文字体；本次使用 bundled ReportLab 4.4.9、`/System/Library/Fonts/STHeiti Light.ttc` 的 subfont 0，未复制系统字体。字体 SHA、确切命令、PDF SHA、逐页 PNG 与视觉检查记录见 `artifacts/cosm2-full-20261017/figures/pdf-metadata.json`。历史三图原始字节与 SHA 保存在该目录的 `prior-canonical/`。可用 `--historical` 明确重建历史 PARTIAL 模式；不把历史未测改写为已测。

`fig-latency.pdf` 由基准测试 worker 独立维护，本生成器不读写它。
