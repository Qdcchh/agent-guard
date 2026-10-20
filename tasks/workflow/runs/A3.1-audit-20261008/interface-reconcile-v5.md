# A3.1 pending恢复补充接口 v5（PROPOSED，未放行）

保持全部v2—v4 wire/DTO/SQL、ordinary pending resend与normal exact-end/previousCP ACK。新增恢复分支只落实A31-20.02完整pin证明后的exact pending ACK；不以最新sequence跳cursor，不伪造每个边界CP，不重签oldrange。所有网络请求仍来自先持久化的不可变exact batch；normal父pending的原body/id从不替换。

1. 固定外部reader originalJWS pin N，按原pure reconcile核完整history+records两页族、全部seq/raw/hash/prev/scope/genesis/bootstrap及每CP边界、外部key/role/range；本地比N短/分叉、缺页/坏sig/换pin等均保pending及全域不变。原baseCP必须为首次genesis/null或完整已认证原JWS链的确切成员；后续追赶可复用同一个确切covering pin，不能凭caller DTO声称已验证。
2. N>=parent.end：将exact parent body与已核prefix中的同range原bytes全等对照；仅对当前同body/id/range/base的parent进行短TX条件ACK，cursor只到parent.end/其原end_digest，batch存该原covering JWS、cursor保其digest作为远端锚。该CP可以覆盖更长前缀，绝不宣称它signed sequence=parent.end。normal ACK函数的exact-end/previousCP断言不减。晚响应不清新parent、不退cursor。
3. N<parent.end且远端已提交parent的合法前缀：由parent原entries确定唯一未提交suffix N+1..parent.end，作为独立reconciliation child batch存于既有batch表，使用现canonical encoder/真实body<=65536、entries<=64和每raw<=32768、SM3 batchid；child.baseCP=pin digest。parent不改，cursor.pending仍指parent。short TX只锁delivery row并重新核当前parent/cursor、exact slice、全部child fields；既有child须完全一致，拒歧义/不一致归属。parent-child关联由stream/range/原body slice/baseCP确定性核验，不靠可伪造标签。
4. TX关闭释放全部锁后，发送已持久child exact bytes至原append接口（remote start必须N+1）。相同child重启/丢回复重用原bytes和远端原JWS/time；新竞争导致409则重新独立固定pin完整证明，再选择仍未提交suffix，保旧child/失败不改。child回复自身不得清parent或推进cursor。重新独立获得覆盖parent.end的完整证明后才按步骤2确认parent。
5. 下一普通最大pending可能横跨同covering pin，继续同恢复分支；追至pin N后head须等其原head，下一normal append N+1/base=该pin digest，原previousCP链恢复。一次有限turn有界、坏stream仍轮转，全部网络位于DB锁外。

新增内部拟入口仅delivery.py：`authenticate_reconciliation(local_records,observed,history_pages,record_pages,trust,*,expected_stream)->AuthenticatedReconciliation`；`prepare_reconciliation_child_tx(conn,parent:PendingBatch,proof:AuthenticatedReconciliation)->PendingBatch|None`；`ack_reconciled_pending_tx(conn,parent:PendingBatch,proof:AuthenticatedReconciliation)->bool`。AuthenticatedReconciliation为本模块内部可信factory构造的深不可变能力：持expected_stream、经真实SM2重验的original observed/prefix、经完整核验的原records、原checkpoint链digest成员以及模块私有factory provenance；不含connection/network/mutable对象，普通caller自造ObservedCheckpoint/VerifiedRemotePrefix或同形dict不能替代。authenticate在所有DB锁/网络外纯核验，复用原reconcile全部验证并真实认证原JWS，不接受bool/skip。短TX两helper先验factory provenance/全部bound数据，再匹配当下parent/cursor及不可变local原slice；外部与未认证DTO不得获得ACK权限。这是同一受信进程的明确装配能力，不宣称Python私有属性提供OS隔离；HTTP不暴露factory/ACK入口。具体内部字段构造及负控由包审核实，现公共DTO/SQL不改。

必要新增控制在既有test_audit_delivery.py/test_audit_client.py：partial32/parent64、CP32→65/parent64、crossing65..70、aligned及同pin复用；child确定性持久/重发/field碰撞/精确network body；parent与child两sender、晚child/晚parent不清新批；pin变化、badbase/slice/sig/page/record/hash/role/scope、DB rollback全值相等；所有child saved/pre-send/remotecommit/lostreply/childresponse/pre-parentACK/post-parentACK适用tuple各10轮真实SIGKILL/newPID/持久DB；source/wheel完整正负矩阵。原A31-12/18/19/20测试与数据库guards保持，不用负例拒绝替代合法恢复正例。

本稿待双S1停写/资源0和完整候选freeze后fresh PACKAGE_REVIEW。没有PACKAGE_READY前不实施。完整S2自查及新独立实施验收不省略。
