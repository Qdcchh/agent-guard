# 本轮TLS receipt的真实部署DNS拓扑 v3

部署继承20组会实际执行当前audit_delivery；该消费者的真实auditPG使用pg-audit.agent-guard.test SAN、原部署CA和owner/run。不得伪造旧固定owner，不改其正常PG证书/CA或normal角色拓扑来迁就localhost。

receipt增第11严格字段audit_host，只允许localhost、127.0.0.1、pg-audit.agent-guard.test之一；真实DSN的host必须与该字段逐字相等，sslmode仍verify-full且CA严格绑定root/ca.pem，并真实查询pg_stat_ssl。容器仍必须full64ID、Running、agent-guard.pr9-owner标签等于外部期望PR9_CI_OWNER。root只给compose的pg-audit新增该同owner标签，原owner/run/project标签保留，不伪造资源身份。

fixture只要求root/ca.pem与PG公开server.pem的0600、owner、无symlink、SHA，**不要求导出PG私钥**；服务对PG私钥的持有由真实verify-full TLS连接证明。root helper原自有PG私钥仍仅留其0700 root并在结束删除。delivery目录与私钥/证书/CA复制件的700/600及digest检查保持；delivery仅localhost SAN，原127IP错SAN拒绝仍必须通过。

部署worker可在其已独占supervisor.export_test_inputs专用trusted init（network-none，不给正常operator额外挂载）内，用原CA私钥签发全新仅localhost delivery证书；只向trusted test controller导出delivery key/cert、CA及PG公开cert，绝不导出原CA key/PG key。全部新材料0700/0600，receipt路径按固定/test-inputs/a31-tls映射，DSN根CA路径同步为该绑定CA。receipt true字段须由真实检查/连接得出，消费者仍复验actual docker inspect/TLS，不以导出字符串当证明。

仅trusted顶层/嵌套pytest controller可挂DockerCLI及Docker socket以核验实际资源；普通12正常角色、model/采购operator不获得socket或controller私密输入。CLI从已验证Linux可信工具复制到明确host共享绝对私密目录、只读挂载，不能误把outer容器路径当daemon host路径。创建/记录/清理仍逐fullID+owner，嵌套动态身份不共享。

独占不变：root helper/compose/CI；basicworker current fixture/unit/audit_delivery测试；deployworker supervisor/roles/clean_deploy/deploy helper等原范围。共享字段与路径在此冻结，分别STOP后互相消费；旧10字段轮与原拓扑失败保留，不伪报v3已经全绿。新加host mismatch/未知host负例并真实DNS+CA/当前owner探针，原全部业务/权限/杀进程/证据断言不减。
