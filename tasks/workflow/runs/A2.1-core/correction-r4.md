# A2.1-core 补正包 r4：版本完整匹配及当前事实索引

- 同阶段真实授权msg_0f54148e0001ZW7yCMdK0TE97F / ses_f0ac0e676ffecn71p6Ww7zaqQq不变；续本workflow MiMo ses_f0aa292caffeODmd0G8jUSZ1Y9。完整读task-v1/原任务/各补正/完整review-r7/issues，不用本摘要代要求。
- NEW r7 session ses_f07b43a4affenxt8HroNe3U3FB，NOT_ACCEPTED，27PASS/4FAIL；snapshot17a3b2c7a61ccc82348de5fc6de6840d8f37861b98c6851a45983981d524f3f5，contracts24b2bf395b9d4ee8b2e754bf85e443dd25f5315e6b4098772c98984bb671c045。
- 原全部代码issue除SNAPSHOT版本parser残余已独立关闭，当前P11mandatory缺口已闭、历史一次unknowncode不伪追根因；全部已闭项全回归，不重新设计稳定机制。
- 本轮只原允许业务/测试/报告文件，**不再改ledger、不改001—006、不新增迁移**。report完整runs/A2.1-core/implementation-r5.md、owned artifacts/workflow/A2.1-core-impl-correction-r4-<unique>/允许；workflow授权/台账/包/review由主控编辑，不B/HTTP/后stage/Git。

## 两项窄修复

1. **A21-R2-SNAPSHOT / P11,P15-CORE,OBL01，中阻断**：params.py `_VERSION`的pattern应按完整字符串十进制正整数、非0/无前导零及既定长度限额校验，不用match前缀接受01/00/1x/1@2/1/2/1空格2/1.0/1e2/超长度、LF/CR/control。检查相同含义的版本校验调用方一致，不扩大规范。新增正式parser负例＋**接受入口**负例：可信permission集合和catalog特意具备同非法版本，使拒绝确实源于格式而非缺资源/权限；候选lookup前INVALID_PARAMS/QUOTE schema拒绝、proof/预算/操作/事件/outbox/下游均零新增。合法1/2/既定最大长度字符串正例、原quote删除幂等/旧bad材料隔离保持。r7源probe version-boundary与observations可参考，别仅测试parse正好有异常。
2. **DOC-CKPT1-01 / WF-DOCS-REPORT**：一次性梳理 `tasks/A2-report.md` **整个当前文件**，顶部与所有当前表格一致。建议简洁重建当下索引，不再保留未标历史的旧计划块；原检查点/失败及阶段记录链接旧review/implementation-r1—r4，而非混为当前状态。写实际HEAD/当前READY待复验（不是ACCEPTED）、Python3.11/PG、004—006已落地、真实tracked5（README/contracts-init/ledger-service/isolation/conftest）、完整当前new源码/迁移/测试清单（含006/results/new回归）、实际JUnit计数、format文件数、可定位本轮log路径、31ID引用详细本轮implementation-r5。不要把旧359/424/未实施/未跑3.11当现状。types docstring的实施状态如尚有错误也修同范围说明。旧原report在既有review artifact candidate快照可追溯，旧完整implementation/review证据不覆盖。

## 自查与停止

Python3.11+自有PG/downstream，完整unit/PG/A1旧行为、版本新负例、所有并发10round/真进程恢复/registry及七表保全/README双烟测/质量；日志secretmask、资源owned cleanup。虽然修复窄，最终新reviewer仍完整31矩阵与独立反例，不放宽。

交implementation-r5.md完整31ID及两个issue实际diff/调用方/测试与证据、真实counts/env/resource，并更新当前简短A2-report。所有fixpending，停写READY_FOR_REVIEW，fresh review；不能自ACCEPTED或发布/下一段。
