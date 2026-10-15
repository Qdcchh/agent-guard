# r4 GQ适配选点纠正

2026-10-09：source GQ全量507P/16F，原raw/XML/exit1保留。worker误将expired-originalproof节点作为第二成功oracle；其原gateway.state仅旧业务表，未含audit，原断言无需改变。主控亲核task-v3原依据“两个原成功全表比较仅允许proof增加”及实际代码，真实两点为window成功与persisted-result fault repair成功。

沿已接受r4修正实施偏离：按冻结baseline函数原字节恢复expired-originalproof；第二点移至修复后同proof成功，严格full_state/result_read_only并保proof+1、accepted别名、全部故障拒例、replay409全域相等与DS不变。不增加第三点、文件、接口或义务，不重复包审。先前STOP/资源转移及失败记录保留；runtime须亲核实际归属再接续。定向repair16两mode后完整GQ/9owned/clock1000/CLI等自查，最终fresh完整独立验收仍必需。

原件核验：artifacts/workflow/A3.1-audit-20261008/controller/r4-gq-site-failure-readback.json。
