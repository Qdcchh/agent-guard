# A3.1接口补正 v4

PROPOSED_FOR_PACKAGE_REVIEW_NOT_DISPATCHED。继承interface-contract-v2/v3全部wire/DTO/SQL/容量/时钟/材料安全约束，下列修正r3确认矛盾；不改HTTP、密码/签名或原锁强度。

- journal.append_tx在_material_tx后、head前对非null op及verified evidence父行按统一顺序实际KEY SHARE；空结果拒绝。publisher仍无task/grant/op FOR UPDATE，已有outbox序列化稳定JWS；不得head后首次取父锁。SDK缺父/材料JournalError与真实PG错误分层，绝不伪造PG SQLSTATE；直接SQL原guard/FK保持。
- query实际op FOR UPDATE；用真实public query_binding装配（普通closure，保原bind一次）暂停已强锁路径，观察publisher先等op且尚未持head，再让query append/flush/commit。10轮/mode，真实不同backend与独立head/阻塞证据、完整QUERY+PUBLISH oracle。
- retry fetch_operation_by_business_key是普通SELECT，绑定/proof-link带真实FK KEY SHARE；与publisher弱锁兼容。10轮/mode使用原public调用/可信accept-binding.compose观察原绑定，不额外FOR UPDATE、不得要求publisher必阻塞于op或声称生产retry旧强锁死锁。验证原弱锁兼容、真实head交错、稳定捕获响应和完整RETRY+PUBLISH oracle；等待证据不得自选期望。
- TrustedAfterLink.__call__：先self.binding(conn,operation,disposition)，再在_callback非None时调用它(conn,operation,disposition,baseline)，只一次；非None返回明确拒绝，异常原样失败回滚同TX。None保原行为，callback不可取代原binding/descriptor，也不关闭capture/append/final clock。原proof已link、结构append尚未执行；CREATED baseline为本TX seed/已有stream，EXISTING为已有stream，不伪造后者tx_id字段。
- 首组captured必须最终按entry/hooks核执行次数、顺序及真实同TX XID，不能只在未执行callback内放assert。新增typed factory矩阵：entry accept/checked × disposition CREATED/EXISTING × behavior normal/none/non_none/raise；正常/None严格合法效果，负例全部域字节回滚、原绑定/回调调用次数独立观测，原互斥控制继续。

GQ精确适配及其余内部投影/深不可变、原件门、captured response、initial/full_state oracle沿用v3。当前补正路径与planned节点见ownership/node-bindings-v4，全部source/wheel集中控制和完整后续自查/独立验收保留；大型实体高水位NOT_RUN限制不能改写为通过。
