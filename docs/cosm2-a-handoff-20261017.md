# 双域共签：A 端独立交付与待 B 项

2026-10-17（Asia/Shanghai）。用户已授权连续推进 A3–A7，并明确 B 尚未开始。本轮交付状态 **PARTIAL**；A1/A2 前段接受保持，不能把当前工具、设计图或历史回放写成共签核心和真实集成已经完成。worker 请求 gpt-6.1-sol/low，fresh reviewer 请求 gpt-6.1-sol/high。

本地给 C 的最新目录：[A交付-20261017-r2](../复赛冲刺材料-20261018/A交付-20261017-r2/交付说明.md)。
旧[r1目录](../复赛冲刺材料-20261018/A交付-20261017/交付说明.md)保留追溯，不覆盖。
r1独立验收为NOT_ACCEPTED（R1-01：C包未携带失败run01原件）；r2只补交失败历史，待fresh完整复验，不能自称接受。没有擅自发送外部消息或发布Git。

| 任务 | 已做 | 尚待真实依赖 |
|---|---|---|
| A3 | 参考 fixture、固定份额公钥/双向签验/20消息摘要三项交叉测试 | B1 核心和 API；当前固定 runner 实跑三项明确失败，不 skip |
| A4 | 基准/统计/坏数据验证/绘图工具；单SM2签名、验签、Rust FROST各100样本+10预热，raw与summary齐全 | 共签三轮/总耗时、B3含数据库谓词、真实网关e2e均n=0/null |
| A5 | B7固定根严格读取、六例中文展示、run_id/原完成时间/来源、单次三轮耗时 | B7真实产物与native控制接入；无新POST路由，执行按钮禁用 |
| A6 | 两张设计矢量图、部分负例矩阵、部分延迟图，统一中文字体配色 | COSM2七攻击矩阵全未测；FROST仅三格历史对照，不替代共签 |
| A7 | 9张无标注原图、185.36秒实际浏览器回放导览（WebM/MP4）、本地C包及逐项SHA/来源表 | 共签真实结果截图和3分钟现场运行录屏 |

A1 的 B1 公开向量复验也仍待 B；当前只有参考实现向量被真实 OpenSSL 验过。

## 实测条件和数据

正式run `20261017-measure-a3a4-02`，镜像 `agent-guard-threshold-gateway-runner:20261017`，镜像ID见summary。Apple M5 Pro arm64宿主，amd64 Docker仿真，Python3.11.17、tongsuopy1.0.1。以下为本环境100样本、p95最近秩法，不是共签性能或网关受理时间：

| 测量项 | 中位数 ms | p95 ms |
|---|---:|---:|
| 铜锁SM2签名 |0.241729|0.255625|
| 铜锁SM2验签 |0.2381245|0.263834|
| Rust FROST 2-of-3（含启动/I/O/复验） |23.297625|25.866|

`experiments/cosm2_bench/results/20261017-measure-a3a4-02/{raw.csv,warmup.csv,summary.json}`为正式原件。首次run01的FROST行动schema错误导致真实失败，原始数据完整保留，不将两轮混合。图表保留全部正式样本，不删异常。B7契约只给三轮timing_ms，三轮相加不能充当网关e2e。

## 工具与使用

```sh
# B1到位并确认README所列API后，在固定runner内运行：
python -m pytest tests/unit/test_cosm2_crosscheck.py -q
# B1公开向量到位后：
python3 tools/cosm2_vector_check.py
# 新环境/新run的正式测量和绘图：
# 详见 experiments/cosm2_bench/README.md；输出目录必须全新。
# 系统/协议/部分矩阵重建（来源SHA变化需人工复核）：
python3 tools/cosm2_paper_figures.py
# 截图/回放导览：先显式启动本机服务，工具只点击读取历史记录。
python3 tools/teacher_demo_server.py --port 8765
# 另一个终端，配置Playwright模块/Chrome和ffmpeg后：
node tools/cosm2_a_capture.cjs --url http://127.0.0.1:8765/ --out artifacts/cosm2-a3-a7-20261017/NEW-CAPTURE --record
```

工具环境使用临时venv：pytest8.3.5、Ruff0.11.13、ReportLab4.4.4、matplotlib3.10.7、pypdf6.1.1；绘图锁在experiments/cosm2_bench/requirements-plot.lock，不修改产品依赖。中文字体STHeiti由本机加载嵌入PDF，不复制系统字体；Poppler渲染检查。Playwright使用bundled runtime与本机Chrome；首次录屏因缺Playwright ffmpeg退出，安装仅工具缓存后以新目录重录，失败记录保留。

C包由以下命令实际生成，拒绝覆盖已有目录并逐文件核SHA：

```sh
python3 tools/cosm2_a_handoff.py \
  --bench-run experiments/cosm2_bench/results/20261017-measure-a3a4-02 \
  --failed-bench-run experiments/cosm2_bench/results/20261017-measure-a3a4-01 \
  --captures artifacts/cosm2-a3-a7-20261017/capture-02 \
  --output '复赛冲刺材料-20261018/A交付-20261017-r2'
```

该目录已存在，再运行需选择全新输出目录。C包manifest固定标为PARTIAL，不能直接用于宣称最终共签完成；B交付后应新建run和更新图/媒体/状态，不补写旧CSV。

## 已执行检查和证据

主控实际运行相关pytest：**81 passed**，原Node测试通过，新增/修改Python局部Ruff check/format通过，git diff --check通过。A3固定runner交叉测试**3 failed，B1缺失**；基准完整模式退出2因六项未测，不把非零写成全面成功。全仓Ruff仍有与基线相同16个问题、3个格式文件（旧x402与参考附件），未擅修无关文件。

原样证据：`artifacts/cosm2-a3-a7-20261017/{controller,measure,ui,figures,capture-02}/`；录屏ffprobe尺寸1366×768、时长185.36秒，截图与视频SHA都在capture-manifest。只点击三次scenario replay，没有现场业务POST、没有共签订单。历史采购run_id为`372d14ad-6c78-49f5-b4a2-6234fcdf48bf`；三场景回放来源为A3.3 source r14历史自查，明确非联合验收/非本次运行。

设计局限保持：半诚实、n=2、同主机逻辑域、参考曲线非常数时间；不证明宿主机失陷隔离或效果端独立验签。原C论文模板未改，本包提供可引用资产和不可写成已实现的边界。


## run01历史失败：命令、原件与静态归因

r2的`historical-failed-run01/`与正式`benchmark/`严格分开。前者携带run01原样`raw.csv`（300行）、`warmup.csv`（30行）、`summary.json`及原始`formal-command-output.txt`，还有本说明和原worker实施说明作为归因上下文。每份源/副本SHA、原路径、run_id与FAILED状态见r2 manifest和交付表。

run01的SM2两项各100正式+10预热成功；FROST为100正式+10预热共110个`ERROR/AssertionError`，metric n=0、统计null、failures=110。旧summary整体`PARTIAL`是当时旧口径，**不表示FROST成功**；r2 manifest将该历史run标为FAILED且`included_in_formal_statistics=false`。不改旧summary字节、不合并两轮，不将失败run出图。正式run02仍为三项各100正式+10预热全部OK。

以下是当时run01真实执行命令的重列（依据原实施记录；本次补正没有重新运行密码测量），退出码2；stdout/stderr原样保存于包内`historical-failed-run01/formal-command-output.txt`：

```sh
docker run --pull never --rm --network none --name cosm2-measure-formal-20261017-a3a4 \
  -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/src:/workspace \
  -e AGENT_GUARD_THRESHOLD_DEMO_BIN=/usr/local/bin/threshold-demo \
  -e COSM2_IMAGE=agent-guard-threshold-gateway-runner:20261017 \
  -e COSM2_IMAGE_ID=sha256:997ccb375167a46fb019795a3a59da2d9bc59778b1027e8da85c4f603e8ec567 \
  -e COSM2_HOST_CPU='Apple M5 Pro' -e COSM2_HOST_ARCH=arm64 \
  --entrypoint python agent-guard-threshold-gateway-runner:20261017 \
  -m experiments.cosm2_bench.bench \
  --output experiments/cosm2_bench/results/20261017-measure-a3a4-01 \
  --samples 100 --warmup 10 --require-complete
```

**归因是静态定位/说明，不是新实跑证据**：初版采用V1合成行动，却把URL填入旧V1的audience标识字段；旧Rust V1字段字符规则禁止斜线。worker随后改用已有V2行动并用唯一action_id避免create_new输出碰撞，另起run02；run01原始错误日志只记录`AssertionError`类型，不应从该日志声称取得更细的Rust错误码。包内`implementation-static-attribution.md`完整保留原说明，其中还有之后的图表样式修补，这些均不是B核心/共签/谓词实跑证据。
