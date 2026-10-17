# COSM2 A3–A7：独立交付 ACCEPTED，全A保持PARTIAL

2026-10-17（Asia/Shanghai）。主控已读回fresh r2完整报告、抽查原始证据、亲核170文件候选SHA与ZIP完整性，接受**A端可独立完成的工具、设计资产、现有来源媒体和新版C交接包**。唯一R1-01/P2已独立关闭。r1 NOT_ACCEPTED、原旧C包、失败run01及两份旧源字节快照均保留。

**这不是完整A3–A7接受。** 真人已确认B没有开始；B1/B3/B4–B7真实依赖未交付。三交叉测试仍3 failed/0 skipped，六项共签/DB/e2e测量仍n0/null，COSM2七攻击和共签现场媒体未做。未接管B、未恢复旧长期实验、未Git发布。

## 交付入口

- [新版C包说明](../../../../复赛冲刺材料-20261018/A交付-20261017-r2/交付说明.md)
- [新版ZIP](../../../../复赛冲刺材料-20261018/A交付-20261017-r2.zip)：34文件，32份源/副本+manifest/说明，SHA `b5cea3dace5e1b516156ead6daf08afac172403edef51925a85bef5c190d00b7`。
- [完整r2独立报告](review-r2.md)；[r1否决与缺陷](review-r1.md)；[原始范围](package-v1.md)。
- [候选交接与续跑说明](../../../../docs/cosm2-a-handoff-20261017.md)。该说明及包内静态归因副本保留**候选冻结时状态**，其“待复验”描述不代表当前结论；最新验收以本记录为准，不改写历史副本及其SHA。

## 已完成的独立内容

A3参考fixture与三交叉测试已写，明确真实导入B，缺依赖失败而非skip。A4基准、统计与严格出图工具完成，单方SM2签/验和真实Rust FROST各100正式+10预热成功；300正式+30预热原件保留。首次run01的FROST100正式+10预热失败另行完整保留，原始输出/命令/静态归因已入C包，不混合统计。

A5已做固定B7根的strict只读保存结果适配、六用例中文名、run_id/原completed_at/来源和单次耗时，运行按钮禁用且无新增COSM2 POST路由；保存summary不伪造实时事件。A6四张中文矢量图完成并独立渲染检查：系统/协议为设计；负例中COSM2全部未测、只有三格FROST历史对照；延迟为部分原语实测。A7保留9张原始无标注截图、185.36秒实际浏览器历史/示意导览（WebM/MP4），不是共签现场运行；本地C包含来源/命令/run_id/状态/逐文件SHA。

## 实际验证与证据

本轮请求worker gpt-6.1-sol/low，fresh reviewer gpt-6.1-sol/high；实际调度按此请求，effective后台metadata未观测UNKNOWN。原样命令与输出均在artifacts/cosm2-a3-a7-20261017/：controller/*.txt、measure/implementation.md和formal-02-command-output.txt、ui/implementation.md、figures/implementation.md、remediation-r1/implementation.md、review-r2/checks.json及原始txt/XML/JSON。

```text
$ [tool Python] -m pytest [六套相关文件] -q
81 passed
exit=0
$ [tool Python] -m pytest [补正test_handoff_remediation.py] -q
16 passed
exit=0
$ node tests/test_teacher_demo_frontend_logic.cjs
teacher demo frontend logic: passed
exit=0
$ [tool Python] -m ruff check [本轮相关Python文件]
All checks passed!
exit=0
$ [tool Python] -m ruff format --check [本轮相关Python文件]
10 files already formatted
exit=0
$ git diff --check
exit=0
```

上面是便于阅读的摘要，完整无占位argv、stdout/stderr、实际运行时间和退出码在r2 checks.json/txt/XML。r2另独跑9项关键负例、隔离重新打包、32源/副本及ZIP34项全字节核对；两轮660行独立重算与图source相符；1366×768两状态/13步/两卡/来源/禁用按钮测试通过，0页面错误/业务POST；四图实际Poppler渲染查看，视频ffprobe/抽帧实查1366×768/185.36s。

r1独立真实密码runner烟测SM2签/验/FROST各3正式+1预热成功、整体PARTIAL/exit2；三交叉真实3 failed/exit1。r2对64项r1未变化原证据逐SHA核对，未重跑100或重录视频，不冒称既有日志为本轮实跑。全仓ruff保留原16问题/3格式文件，局部检查通过，不称全仓绿色。

正式条件为Apple M5 Pro arm64宿主、固定amd64 Docker仿真、Python3.11.17/tongsuopy1.0.1；FROST包含进程启动、文件I/O、Rust共签和Python Ed25519复验。该数据不代表COSM2或网关e2e。图与包均已写明边界。

## 冻结、资源与后续条件

170文件清单SHA `c01c641b410e8435d6c865ee2a68fa7a8bab49b46e6bc8546648b23ec8d50257`，reviewer开始/结束、主控最终读回一致。r2报告原文SHA `984e1417107f0913891938aa9af383757131d4bbb6a442268014b1f678588643`。接受后只追加当前policy索引和本记录，不改已验代码/数据/图/媒体/包/冻结说明。

全体worker/reviewer STOP。主控核实本轮127.0.0.1:50087服务PID4211命令行后SIGINT，原session真实wait exit0；浏览器/fixture服务已结束，所有本轮唯一名称测量/复核容器已退出；无DB/业务订单。仅自有证据文件和工具依赖缓存留存，不触碰外部容器或服务。

后续解除条件：B1最终API/核心/公开向量→真实三交叉与OpenSSL；B3→含数据库谓词时延；B4–B7→真实共签网关、攻击/拒绝位置、明确的e2e样本（B7原字段只有三轮）；B7→原生控制、真实截图与三分钟现场。每轮新建run，不补写旧CSV。不自动发送给C，不擅自扩展到B；用户如要全A最终闭合，需先有这些真实交付。
