# COSM2 A1/A2 提前交付 · ACCEPTED

日期：2026-10-17（Asia/Shanghai）。主控核验两名 worker STOP、fresh reviewer 全文及原始证据后接受本轮 A1/A2。分支 `codex/cosm2-2p-A`，未提交/推送。整体项目仍 PARTIAL；不恢复旧长实验。

请求 worker `gpt-6.1-sol / low`、fresh reviewer `gpt-6.1-sol / high`，本轮实际调度采用该配置，后台 effective metadata 未观测为 UNKNOWN。当前角色覆盖已写 current-policy 顶部。

## 交付文件

- `tools/cosm2_vector_check.py`：默认读 B1 三公开字段向量，标准库实现 PEM/DER临时转换及 OpenSSL 3 正验签、恰好翻转一个消息字节的拒签；严格区分工具错误。支持显式 `--openssl` 与 Homebrew 自动发现。
- `web/teacher-demo/index.html`、`app.js`、`style.css`：新增“双域共签 · SM2”，FROST 改作对照；五泳道、三轮及授权域独立检查、两张六项模块卡、正常/撤销分支、对比及局限；13步均明确示意。授权域红叉，拒绝笔网关/下游未发生。保护已有前端和FROST/x402入口。
- 本轮 package、包审、独立完整 [review-r1.md](review-r1.md) 与本接受记录。

## 实际验证

原样命令/输出及退出码：`artifacts/cosm2-a1-a2-20261017/controller/*.log`；worker 18探针日志 `a1-worker/selfcheck.log`；reviewer 30独立探针 `review-r1/probes.log`、`probes-results.json`；浏览器逐步 Range/CSP/交互证据 `review-r1/browser.json` 与截图。主控已直接读取完整review、抽查原始文件并亲自重跑：

```text
$ node tests/test_teacher_demo_frontend_logic.cjs
teacher demo frontend logic: passed
exit=0

$ python3 tools/cosm2_vector_check.py artifacts/cosm2-a1-a2-20261017/a1-worker/reference-public-vector.json
OpenSSL: /opt/homebrew/opt/openssl@3/bin/openssl
positive: Signature Verified Successfully (exit 0)
negative: Signature Verification Failure (exit 1; exactly one byte flipped)
PASS: public vector checked with OpenSSL 3 / SM3 / fixed distid
exit=0

$ /tmp/cosm2-a1-a2-tools-20261017/bin/python -m ruff check tools/cosm2_vector_check.py
All checks passed!
exit=0

$ /tmp/cosm2-a1-a2-tools-20261017/bin/python -m ruff format --check tools/cosm2_vector_check.py
1 file already formatted
exit=0

$ git diff --check
exit=0
```

Reviewer 30探针全部符合预期：3组本轮新参考向量及自动发现的真实OpenSSL正负例、缺B1/工具、坏输入及5种工具替身错误路径。替身仅测试错误分流，不作为密码学证据。Chrome 1366×768下13步、两卡、来源与CSP正常，无裁切/重叠/页面错误；红叉RGB(198,58,46)。局部Ruff锁版0.11.13通过。全仓ruff仍是基线16项问题；format仍是原3文件（附件参考代码及旧x402），未擅修无关文件，不宣称全仓绿色。

## 冻结、基线与资源

17文件候选开始/结束/主控最后读回SHA一致；清单 `controller/candidate-sha256.json`，继承baseline.patch/status及本轮candidate.patch/status保留。review原文复制后SHA `a72aa8698a3538a01a6a15da0fffa947b8c1b60d4d0befef36283c3a7ddfbec3`。接受后的current-policy仅追加状态索引，不修改已验实现。主控对继承的事件文档、server及server测试diff核对完全保留。全体worker/reviewer STOP；本轮独占64682服务PID98308已核对命令行并SIGINT，真实parent wait exit0；所有浏览器及OpenSSL子进程已结束。未创建数据库/容器或业务订单。

## 未完成依赖与复用

**B1 的 `tests/cosm2-public-vector.json` 尚不存在。** 本轮参考实现向量被OpenSSL验证，不代表B核心或G1已过；不勾选论文“B公开向量已验证”。待B提供后，在仓库根执行：

```sh
python3 tools/cosm2_vector_check.py
# 或指定：python3 tools/cosm2_vector_check.py tests/cosm2-public-vector.json --openssl /opt/homebrew/opt/openssl@3/bin/openssl
```

前端仅A2示意骨架，未接B共签核心/真实采购/A5；不证明恶意安全、跨主机隔离或t-of-n实现。工具对未知OpenSSL错误诊断失败关闭，空消息拒绝，支持指定canonical uncompressed SM2 SPKI；未作所有OpenSSL版本兼容保证。A3–A7/B任务及Git发布本轮未做。

截图与原始artifacts为本地Git忽略证据，干净克隆不含这些日志；正式review与本记录保留验证条件和结论。原附件参考实现未改写。
