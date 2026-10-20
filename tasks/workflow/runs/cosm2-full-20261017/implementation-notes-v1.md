# 已包审接口解释及实施派发
PACKAGE_READY报告已原样归档，六冻结文件SHA主控再次核验一致。真人连续授权已满足，2026-10-17开始B1/B2，G1通过前不集成网关。

- AUTHZ实际六码，包中七类为计数笔误；加严格解析/无效AS链负例。
- 普通COSM2行动V3 payment_digest为64个0；x402必须真实摘要，普通调用拒绝非sentinel。
- COSM2批准过期401 EXPIRED；旧FROST及授权令牌过期403不变。
- B9下游首次/恢复皆转发持久原envelope和业务idempotency；同批准换operation_id不可再生订单。
- core API: ExecParty()/AuthzParty(),d1/d2测试属性,pub,keygen_msg/keygen_finish/set_public/sign_round1/sign_round2(message,q1)/sign_round3(message,r,s2,s3),compute_e。编码public_point_to_spki/spki_to_public_point,signature_rs_to_der/signature_der_to_rs,point_to_hex/point_from_hex(130hex uncompressed)。shares.generate_shares(DIR,*,key_epoch)与load_share(dir,role=)返回Share(share,public_key_spki,key_epoch,role,public_point)。

2026-10-17 状态更新：包审结束后current-policy只更新实施进度，不变更功能范围和安全义务；原包审开始/结束指纹维持历史记录，最终实施候选另冻结现行policy。B9真实新负例及完整旧执行回归538项通过；旧34失败为两处升级列表未计入008/009，现仅扩大为精确当前列表，原反例和历史迁移均未改，失败原件/脱敏说明保留。
