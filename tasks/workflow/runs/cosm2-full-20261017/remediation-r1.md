# COSM2-R1-001 最小补正自查报告

状态：实施 worker STOP，补正自查通过；不是独立接受，待全新 high reviewer r2。

唯一源码改动为 `tests/integration/test_cosm2_gateway.py` 的两项 C10 和两个局部 helper。与 r1 冻结清单核对的 347 个 src/tools/tests 文件中，只有此文件改变；生产代码、其它测试、原401/EXPIRED和零订单/批准/操作/预算断言、历史失败和 freeze-r1 均未改。原文件从已读内容恢复后 SHA 与冻结清单逐字节相符，保留 `baseline-test.py.txt` 与 `minimal.diff`。

签名前给真实批准10秒窗口，先完成真实共签并用真实网关成熟验签路径证明 header 有效。之后以真实 PostgreSQL `clock_timestamp()` 轮询其 action.expires_at，只有 DB 确实到期才发送请求；15秒单调时钟上限只防卡住，不替代批准时钟，也不将授权域签前拒绝算成功。

第二项冻结的是签名完成时真实且有效的 off-lock clock。实际 DB 已超过期限后，再次证明早期验签仍通过；局部 spy 仅记录真实 final_check 入口的 DB 时间并调用原 final_check，不改生产时钟或检查。测试断言真实最终事务检查调用一次且DB时间>=批准期限，仍要求网关401 EXPIRED并断言事务零效果。此前 token nbf 假触发和 AUTHZ_EXPIRED 均不能满足这些断言。

实际检查：

- 原完整552项集成：552 passed，118.49秒，零失败/错误/跳过。
- 与该完整组同时运行4个独立 pytest namespace：签前延迟0、2.4、4.5、2.4秒，每组两C10，合计8次通过；每组约22秒。注入位置在 action 已确定真实deadline后、真实sign_header前，明确覆盖旧1秒窗无法承受的延迟。
- 非root uid501:20、无网络的相关核心/份额/交叉/策略/domain单测：89 passed。
- 目标文件 Ruff check、format --check 均退出0。按root指令未重复8分钟全非PG组及全局质量；r2需执行完整独验。

全部原样命令、退出码、日志、JUnit 见同目录 `*.command.json`、`*.exit.json`、`*.log`、`*.xml`；延迟插件原文在 `run.py.txt`，宿主临时插件目录已移除。旧review-r1失败原件保持原样。本轮没有失败日志需要脱敏。

随机owner `cosm2-remediation-r1-6b5ef0f48ea5eece`；PG完整ID `4818d658240530b16cacaf2684f0678a0e69717cb9d08d17c8b647d24349c32f`、network完整ID `cb883cafc9e0fd91ce98ad608224679739cdb442ccab61994e98f2876accf10e`。PG16版本/镜像ID及amd64固定runner仿真信息均在本目录。结束catalog schema/database/ROrole计数0|0|0；删除前逐项验证完整ID和owner，容器/网络剩余0，0600的pg.env/runner.env已删除；无端口发布，不复用或触碰其他资源。没有 Git 发布。

最终测试文件 SHA256：`fb83daea87eac90ed4d3ec2043f62f921b8b9e35f9aff66dab1ecdea71b4f41d`。最小diff SHA256：`dd6b0af70a47ae71df9457dd0baa433a4652cf0e3ef83c4a4fadfd2de3459fa4`。
