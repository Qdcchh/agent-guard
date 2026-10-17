# B6 可选项前置门（实际自查）
2026-10-17：真实隔离PG16+AS+独立下游，COSM2 16项与原FROST网关24项共40 passed，退出0。原件 artifacts/cosm2-full-20261017/integration/b6-threshold-r4.{log,xml,exit}。B7实际六用例全绿，run_id b944d1ab-4525-46a9-8bb1-1a9dbdbdca00，严格result orders/operations/approvals=1，resources_remaining=0；measurement/negative-matrix附同目录。主控直接核对原输出与JSON。准许按原顺序实施B9，然后B8；不是最终独立验收。

失败历史保留：r1 fixture导出不匹配；r2/r3最终时钟测试错误注入了AS令牌nbf之前的时间。诊断证实403来自真实令牌有效期校验，改为签名时真实有效、批准截止前一秒的固定早期时钟，DB仍实际走过期限，命中批准finalTX401拒绝。未为该失败更改生产expiry逻辑。授权域另修复整条路径先看撤销、再有效期、后额度，避免根额度耗尽遮住中间节点撤销；真实回归已加入。R1敏感测试输出已脱敏，原未脱敏输出未保留，相关报告明确其证据局限。
