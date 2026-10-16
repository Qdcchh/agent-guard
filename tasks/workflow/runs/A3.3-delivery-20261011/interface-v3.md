# A33 v3 接口补正

现行契约以 [interface-v3.json](interface-v3.json) 的 local_registration_confirmation 为准，实际部分S0 API见 [shared-interface-s0-r1.json](shared-interface-s0-r1.json)。原 [v2接口](interface-v2.md) 保历史并继续约束未改义务。

新函数仅可信本地维护确认。独立remote注册全部提交后，再在operator自有authority事务确认 exact committed descriptor；只转 registration_state，不改cursor/业务/ACK，不把调用参数称远端证明。初次非法cursor和描述符不一致零写，已注册幂等无回滚。真进程中断恢复和完整源/wheel矩阵必跑。
