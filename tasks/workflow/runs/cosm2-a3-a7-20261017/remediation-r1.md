# R1-01 最小补正授权（连续真人范围内）

r1完整独立验收NOT_ACCEPTED，原报告和116文件冻结清单保留，不改写失败历史。唯一阻断R1-01/P2：C包只携带正式run02，缺历史失败run01三原件及对应命令/错误归因，无法仅凭C目录复核110个FROST失败。

补正worker gpt-6.1-sol/low，单一writer独占 tools/cosm2_a_handoff.py、docs/cosm2-a-handoff-20261017.md、新版 复赛冲刺材料-20261018/A交付-20261017-r2/** 及自己artifacts/cosm2-a3-a7-20261017/remediation-r1/**。旧A交付目录、正式run01/run02、所有图/媒体源/benchmark代码与原报告保持不变。不新增B实现，不重测100样本，不改统计或测试预期，不Git发布。

C包新增独立historical-failed-run01目录：原raw.csv、warmup.csv、summary.json、失败命令/原样输出日志；如以worker implementation为归因来源需明确“静态定位/说明”，旧summary整体PARTIAL只是历史旧口径，FROST ERROR+110失败是真正状态，不能改原件。新版manifest和交付表逐文件SHA/原路径、标历史失败/不并入正式统计，保旧包供r1追溯。给C最新入口改r2。

实际新目录打包运行、SHA和全行核对（正式300+30行、失败run01中FROST100+10 ERROR）、原件前后SHA不变、局部ruff/格式/diff、坏/覆盖目标拒绝等必要检查。完整补正报告和原样命令/输出放自有artifacts，STOP后由root冻结新候选并fresh high完整复验。原包范围不变，无需扩大任务或重开包审。
