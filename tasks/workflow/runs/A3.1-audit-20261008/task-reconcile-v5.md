# A3.1 remote-ahead 恢复补充 v5（待包审，未派发）

本文件承接task/interface/ownership/node-bindings-v4及原v2/v3、安全/实施/审查合同。141父项/133运行、269继承断言和95原子完整保留，requirements-v1字节不改。最新连续授权见user-extend-through-a33-20261009.md；本补充仍只实施A3.1，后段须消费实际已接受基线。worker Sol/medium、fresh reviewer Sol/high，有效metadata UNKNOWN。

实质缺口A31-S1-RECONCILE-PENDING-BOUNDARY：不可变pending1..64遇远端原CP32或CP32→CP65，正常exact-end/previousCP ACK或直接跳cursor都不合法，原pure证明正例无法闭合恢复。服务原strict start=latest+1、oldrange换批409且不重签保持；不改SQL/guard/wire/原pending，不将永久RECONCILE_REQUIRED当完成。

只授权ownership-reconcile-v5的既有delivery6精确路径，待双S1 native STOP/资源0、主控读回冻结以及fresh PACKAGE_READY后唯一writer实施。所有其他文件只读，实质额外范围先精确补包；不得改原断言、skip或放宽预期。既有normalACK/pureproof自查不等于本补充或全A3.1接受。

恢复语义见interface-reconcile-v5.md；本段集中补正和完整delivery source/非editablewheel自查后STOP/资源0。再向唯一S2整合者显式移交，完成真实联合TLS/CLI、全段141/133完整自查与候选冻结，fresh独立IMPLEMENTATION_ACCEPTANCE；阻断补正后fresh完整复验，验收保全部历史失败和原件。

包审重点仅本实质恢复差异与其实际代码/调用/guard/原子/owner依赖；已冻结未影响S0与不变原子凭现SHA和接受设计核，不反复重述历史。补充原子覆盖不删A31-12 oldrange拒例，既有A31-20 lateACK/rollback/fairness/records与history负例保留。

同段集中补正A31-S1-LOCKTIMEOUT-FAIRNESS：现per-stream轮转未捕获真实psycopg.Error，某stream delivery-row lock_timeout可中止本轮、阻断后续健康stream。只在逐stream边界处理数据库失败并继续有界轮转，保事务退出/回滚、脱敏与错误原件；测试真实独立PG锁等待超时→健康stream继续，适用10轮/source及wheel，不catch系统退出或吞业务错误作ACK。仍在同delivery.py/test精确路径，无新增范围或SQL改变。
