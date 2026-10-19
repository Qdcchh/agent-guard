# 固定A32 HTTPS loopback地址勘误

前补充legacy-current-migration-and-loopback-addendum.md中两域都127.0.0.1的建议有误，原文作为失败过程记录保留。本页覆盖其gateway地址细节，其余scope/断言/门控不变。

root已逐原test_a32_joint_tls.py核对：audit reader监听127.0.0.1:443，而gateway在原331行显式--host 127.0.0.2 --port443；两服务并存且独立CA。将gateway误映到.1时真实TLS正确拒绝wrong issuer，原失败保留，不能放宽TLS。

CI ephemeral VM及trusted nested controller必须使用audit.agent-guard.test→127.0.0.1、gateway.agent-guard.test→127.0.0.2。原URL、SNI/SAN、端口443及分别CA不变，不改用户Mac全局hosts。CI两loopback地址都需以原非root身份bind443预备检查；仅ephemeral VM调整unprivileged_port_start，不将pytest全改root。实际TLS行为由完整原A32及70TLS测试检验，绝不靠固定hosts替代证书验签。
