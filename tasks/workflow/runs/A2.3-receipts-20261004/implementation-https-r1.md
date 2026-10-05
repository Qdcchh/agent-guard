# HTTPS / fixture / demo implementation r1

原生结论：FINAL STOP / READY_FOR_INTEGRATION。owner `a23-https-r1-20261005`。请求 sol / medium；effective model / effort UNKNOWN。未启 children。没有 A3 实施，没有 full A2 ACCEPTED 声明。正式完整119/112、sole integrator combined29 与 fresh reviewer 验收仍是父任务。

候选写入仅 `tests/fixtures/a23_https.py`、`tests/integration/test_gateway_receipt_https.py`、`tools/a2_receipt_demo.py`。原控制事实为最新真人授权、PACKAGE_READY consumer review SHA11149fdff96c4289ce1cd7ae367c3977df6330cb0795de60aca552debcd13f41，以及实际 pre-dispatch freeze；common 控制文档是历史快照，没有追改 baseline-v3。未消费活动 CLI worker，直接调用冻结 InternalPublisher。core15 SHA 实读一致；其历史882/1078/813自查仅冻结依赖，不作为本 worker 验收。

每个场景使用新生成 AS/GW/三 holder SM2 密钥、随机真实密码和 Basic secret、新 CA、两个 SAN 叶证书、随机独立 AS/GW PID/ports、独立 gateway schema 与独立 downstream scratch DB。客户端真实验证 CA 与固定 `auth.agent-guard.test` / `gateway.agent-guard.test` SAN。实际 server/gateway CLI 执行 password、cookie/CSRF、consent、state、nonce、exact redirect、S256、code-holder proof；独立 IDToken SDK 验证后，两次不同 Basic/SM2 holder 实际 AS exchange 得到 root→child→child。没有 direct mintroot、假 VerifiedInvocation 或模型 API。

四 canonical tools / string version1 依次真实执行读取、文档、采购、通知；通知使用此前真实订单 operation。全三祖先四 counter 验证 reserve/settle，独立 downstream 持久 SUCCEEDED，四 RESERVE/SETTLE、24 event nodes、4 READY、1 order、1 notification、4 downstream operation。真实 InternalPublisher 仅三 publication fields、repeat byte-identical；当前 fresh result-read proof 查询仅新增一 ag_proofs 和一 ag_verified_evidence，精确关联 operation/jti/evidence_ref，其余全部 ag_*、ds_* 行族完全相同。独立 SDK trust 来自 parent-side 公钥与历史登记，验证17 claims，结果仅 UNANCHORED。

5 nodes /14 local atoms 实际映射见 actual-bindings.json；33 collected nodes 与逐例 PFES 见 junit-node-manifest.json。26 negative parameters 覆盖 stolen token、parent-key/child-token、body/holder/endpoint/key、invoke/query replay、proof expiry、tenant/task/grant/holder/key cross-owner、root/mid/leaf revocation/expiry 与 key disable、unsigned /sign /recover /settle。expiry 等待实际 PG clock；proof expiry 只拒绝过期 proof，不错误断言仍合法 fresh query 也失效。每个拒例完整比较全部持久行族，只允许最多一新增 STAGED verifier fact；公响应限定 error code/request_id，并检查 raw credentials、proof、私钥、DSN、stack、evidence 无泄露。祖先 expiry 与子 token exp 同时受真实 AS bounded delegation 约束，没有声称能够让有效子 token 超过失效祖先。

256 个唯一短 SKU 通过同一真实 TLS 全链。采购 request7434、quote12148、result12232、ledger1069、public13486、permission source32625、outer39397 bytes；token≤4234、proof715、receipt1130。沿用原 JWS16KiB、component64KiB/public65536、outer1MiB codec，不声称256×128全可达，不把 codec helper 当合法 TLS positive。N021保守54872、公64KiB合法边界不可达；N031九component≤64KiB+140=589964、outer1MiB合法边界不可达，继承 exact codec/illegal oversize503/proof rollback义务没有改动。

| 最终或相关验证 | 原生结果 |
|---|---|
| source-frozen-33 | P33 F0 E0 S0，97.55s |
| wheel-frozen-33 | P33 F0 E0 S0，94.98s |
| source-related-regression | P183 F0 E0 S0，67.67s |
| wheel-related-regression | P183 F0 E0 S0，63.13s |
| source/wheel-frozen-demo | 两个真正 `python -m tools.a2_receipt_demo` 进程 exit0 |
| source/wheel extreme umask repaired | 各1 PASS，调用方 umask0777 |
| frozen-quality / frozen-format | exit0 / exit0 |
| git diff --check | exit0 |

最终 wheel SHA d9ce87adaa170ac4023bef0a89b29d89d2d66086663025be9a76d706dd511b0a；真实 PEP517构建，非 editable 安装。source 从 common完整340树仅 overlay3；wheel tests/tools同来源，wheel package真实 site-packages 加载，最终父/子 module SHA均记录且无 src shadow。真实 Linux Python3.11、PG16；锁 SHA与实际版本见 source/wheel-final-provenance.log。old regressions 覆盖既有 TLS、login/consent、exchange、receipt SDK/codec、READY corruption query proof rollback及HTTP factory从不读signer私钥，不重复完整 core late-clock 大套件。

所有 first FAIL 与补正记录保留：apt mirror502 exit100重试成功；ruff39 errors与分阶段修正；strengthened proof-expiry错误测试预期导致1F32P后修正；demo driver两次错误模块/path调用后真正CLI成功；umask0777证书不可读首次source/wheel各ERROR，OpenSSL子进程私有umask077+extension0600后双方PASS；末次格式补正后冻结两侧33再次PASS。最终同步只对 own generated pycache 的 chown报Permission denied，三候选复制和SHA均一致，wheel build/install均成功；生成缓存不参与source tree，copy排除 __pycache__/*.pyc。部分早期实验没有逐命令三源快照，不作为最终版本证明；最终命令均保存对应 source snapshot。pytest fixture注册有1条 AssertRewriteWarning，无skip或测试绕过，explicit full-row refusal oracle仍实际执行。

start-audit 最初不必要完整docker inspect被即刻缩减为foreign ID/name/image/Running/StartedAt；未输出/保留foreign env，原与缩减SHA及原因记在audit-privacy-repair.json。该非必要原inspect不作为运行原件证据。密码在命令和日志仅 redacted，own private.json已删除，运行临时CA/keys/config均已回收。

command-index.json为实际command/exit/logSHA；junit-node-manifest.json包括失败原XML和最终逐node PFES；actual-bindings.json是5nodes/14atoms逐函数/断言行绑定；source-read-api-manifest.json与core15-readback.json记录full-byte/JSON/AST及实API SHA（full-byte manifest本身不冒充语义验收）；child-provenance-stop.json核132个最终TLS子PID原生终止；owned-drain-check.log证实只余容器PID1 sleep，test schemas0/scratch DB0。resource-stop-audit.json仅按实际创建fullID+双owner label逐个stop/remove本人PG/Python/network；最终双label剩余0，foreign3 ID/image/Running/StartedAt前后完全一致。scope-end.json核main341/common340无异常，HEAD/branch/index与开始相同，peer独占exact4明确排除，正式包/core/SQL/deps/CI未变。

可复用隔离设计脚本：integrator_runner.py，必须提供新 A23_INTEGRATOR_OWNER 与新绝对 A23_INTEGRATOR_EVIDENCE，支持 create / wheel / test / cleanup，拒绝复用本worker owner/目录。脚本当前固定 COMMON+HTTPS exact3，仅为本子包复现参考；不是最终 combined29 runner，sole integrator 必须基于 allSTOP 后新的完整冻结树纳入 CLI、7docs和core，并用其自有fullID/双label/网络/数据库/venv/HOME/cache。demo_driver.py仅做自有 schema/DB申请、迁移与回收并启动真实演示，无业务伪造。公开demo本身须显式两条 disposable TEST DSN，不提供部署私钥或 production ENV skip hook。

完整父任务整合与新独立验收尚未执行；本子包到此停止写入并移交，READY_FOR_INTEGRATION。
