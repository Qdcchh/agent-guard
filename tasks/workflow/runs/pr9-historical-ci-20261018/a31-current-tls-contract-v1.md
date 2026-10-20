# 本轮A31 TLS夹具契约

完整普通PG初次verify-full装配已实际1509pass/1error，47m46s，1000原clock矩阵完成；未执行余下6092目标，不称全部绿。首error为tests/fixtures/a31_delivery.tls_dir()硬编码/private/owner.json、/e/resources.json、旧owner UUID/role token/容器名与bind mount。不能伪造旧owner来绕过检查。

新增显式PR9_A31_TLS_RECEIPT（本轮helper receipt的绝对路径）与PR9_CI_OWNER（实际期望随机owner）；无新receipt时保留全部旧分支归属/manifest/mount/DSN断言。新分支必须拒绝文件/任意祖先符号链接，root0700、receipt/CA/server证书/私钥0600；严格字段/全64hex ID、owner、文件来源SHA。使用真实docker inspect按全ID和agent-guard.pr9-owner核验实际活容器；不可仅凭receipt的true字段。真实audit DSN必须verify-full、CA路径等于该root/ca.pem、host为证书SAN允许localhost或127.0.0.1；在真实独立audit连接查询pg_stat_ssl证明TLS。root helper生成RSA证书SAN不变，实际连接CA/主机验证仍由libpq完成。receipt绑定ca_sha256、server_certificate_sha256及明确绝对tls_root，禁止任意路径外取CA。

tls_dir仍返回真实server.pem/server.key所在Path；SignedTransport新分支只从经过上述绑定验证的该Path/ca.pem建立AuditClient，旧分支保持/private/ca.pem。不添加可关闭验权/TLS的开关，不改生产代码，不削减原投递/回滚/持久恢复/SM2断言。

独占：low pr9_ci_worker只写tests/fixtures/a31_delivery.py与新增tests/unit/test_pr9_a31_tls_context.py；原query适配文件保持已冻结SHA。root只写tools/pr9_ci_audit_tls.py与ci.yml，将receipt准确提供给后续pytest；共享接口先本契约冻结。low可读取root helper并在其自有当前PG生成真实receipt，原失败与原TLS跑结果保留。新夹具错owner/短ID/文件篡改/路径链接/非verify-full/错误CA等应拒绝；相关audit_delivery真实整文件实跑，继续剩余普通PG诊断，最终fresh完整矩阵另验。原始日志私有且不上传，全部own资源按fullID+owner清理。
