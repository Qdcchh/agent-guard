# A2.2 主控接受记录

2026-10-05（Asia/Shanghai），**A2.2-integration ACCEPTED；整体项目 PARTIAL。** 主控收到 `/root/a22_acceptance_r2` 实际原生 COMPLETED，完整读回[review-r2](review-r2.md)，并独立核对全部95项语义/88运行义务。请求角色为gpt-6.1-sol/xhigh，有效后台metadata UNKNOWN；使用已批准本段有限适配，旧门未改。

受审HEAD为`280022e9d7005daa8d551ba0e4c52e3228e3add5`，分支`codex/a2.2-integration`；未提交候选以285项完整文件/模式、Git状态、semantic index和diff绑定，首尾一致。冻结SHA256 `e985399777b8b5347dfae608388633e53a018b45bee52eed9bb367a77695cf3f`，entries摘要 `c93742d25837ba6037e4b2a97a8ba8fe9f35fa8c1b2b04c5c2206c09206d59e9`。

报告逐字保存，SHA256 `b9ae21a2c6537d0097e6d9a4e2b4da701953a24c496396b0aa2f1e77728cee13`。主控核619原始文件bytes/modes/SHA、150命令/46JUnit、28,300个包括失败与中断的case，1683测试/helper函数、499实现符号、4151映射函数组、51,446实际PASS引用、16,997断言/调用行、29,791 helper边、376实际运行源码及10个collection↔JUnit双射，未发现证据缺口。未把失败或历史日志计作当前正式PASS。

唯一未插桩正式组：source/wheel各1022普通＋1930真实PG，共5904 PASS，FAIL/ERROR/SKIP均0。各variant最终独立118＋335＋1真实网关SIGKILL恢复；wheel另2进程＋132DB＋30HTTP-DB，共1072 PASS。A1单列70/87与原4＋1/等价升级、A2历史482、B等价250、oracle60及TLS/OpenSSL/README两流程、新网关CLI/真实子进程来源核验均完成。原B221/25/4、原升级/断言重写/权限/缓存/pytest报告故障及中断保留，具体等价边界见完整报告。

**CLOSED_REVIEWED_R2**：A22-R1-RESULT-ERROR、A22-R1-SHORT-WINDOW。前者只转换可信终态投影的typed DOWNSTREAM_INCONSISTENT为503，未知错误仍500；真实损坏、完整回滚、同proof修复和重放独立通过。后者真实AS根/中间/叶有效期、强制跨秒、锁后目标deadline正负每组10轮及全四计数/DS3独立通过。A22-CTX-FIRST-BINDING保持CLOSED_REVIEWED_R1，并以本轮16字段变体/过期原proof合法新query回归确认。无新增已确认阻断缺陷，不声明绝对无缺陷或生产安全。

所有owned运行原生结束，自有2容器/网络/私密运行文件已移除，实际owner查询余留0，临时observer恢复ABSENT。三个原有无关容器完整ID/Running保持，主控额外核其mount未变；未连接其数据库。完整原始证据保存在本地Git忽略`artifacts/workflow/A2.2-integration-20261004/reviewer-r2/`，索引SHA `965bc23885c6658e3230e997ade731eeea964439e5a4dbedc086c7c169fabc14`；干净克隆不含这些原始日志，正式完整报告及本记录自足说明已验证范围。

验收之后的报告保存与现行文档/state/问题状态维护属于主控收尾，逐项记录delta并再次核全部产品/测试/SQL/依赖/CI与受审字节相同；不冒称新增收尾文档已在原285冻结中。验收不代表Git已发布或main已合并：先提交/PR，再核实际CI与审核，PR #6管理员例外不继承。合并阻碍不阻止按已有连续真人授权继续A2.3正式包审与完整A2；A3四段在完整A2接受后实施。
