# A31 CA传递与TLS用途分离补充 v2

真实audit_delivery已到51pass后，SIGKILL子进程因test_audit_delivery.py内四处固定/private/ca.pem失败。新增授权low pr9_ci_worker独占该测试文件，限把经fixture验证的transport.ca_file显式传给两份0600 child config，再由原CHILD/RECONCILIATION_CHILD读取；两直接AuditClient也用同一ca_file。原子进程/杀进程/SM2/恢复/零效果/错角色/错主机全部断言保持，不造/private全局alias、不改生产AuditClient。

原错主机负例用127.0.0.1访问仅localhost证书，必须真实因SAN失败。因此不把支持127SAN的PG服务器证书复用于测试HTTPS listener。root helper新增root/delivery/目录0700，server.pem/server.key及ca.pem复制件0600；仅DNS:localhost SAN证书由同一本轮CA签发。PG继续root/server.pem（DNSlocalhost+IP127.0.0.1）供真实DSN verify-full使用。receipt新增第10严格字段delivery_server_certificate_sha256；原9字段含义不变，ca仍root/ca.pem，server_certificate_sha256仍PG证书SHA。

新context校验额外delivery目录/文件无symlink、owner/mode、CA复制件与rootCA逐字节SHA一致、delivery cert SHA匹配receipt。tls_dir新分支返回root/delivery，SignedTransport只允许该绑定目录且self.ca_file为root/delivery/ca.pem。旧分支及其/private/ca.pem保持原样。不得改错主机期待或使用DNS失败冒充TLS拒绝。

先root helper STOP/SHA后消费。旧9字段轮通过与失败保留，不称它通过v2；新真实整文件/负探针和其后普通PG诊断，最终全量独验/最新headCI仍必需。
