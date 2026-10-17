# COSM2 全量实施包 v1

## 真人授权与范围
真人原话：“你直接把B的部分也做了吧，从头开始，一直到我发给你的那个markdown里面的所有内容都被实施”。这是当前实施授权，覆盖旧 A 阶段不得接管 B 的限制。原始规划为唯一功能需求来源（下列摘要不替代原文）。包含第0–5节、A1–A7、B1–B9以及交接清单；B8/B9待B6全绿后实施，优先B9。时间表提前执行，不伪造未来日期。worker gpt-6.1-sol/low；每轮全新 reviewer gpt-6.1-sol/high，effective metadata未观测为UNKNOWN。原有dirty/untracked全保留。不commit/push/PR，不自动创建Git标签；“冻结标签”以本地候选内容清单和冻结命名完成，Git发布另需明确授权。原本C论文撰写非本轮代写范围，全部可写清单及真实图表/数据交付到本地C包。

## 不变量
严格遵循原文0.2数学、0.3八项硬约束与0.4常量/拒绝码。迁移001–009和V1–V3旧编码保持字节兼容，GM-MVP-1不变。网关、效果端及P1最终验签只用成熟tongsuopy。份额仅运行时临时生成，0700/0600；不输出私密值或完整令牌。k1一次性失败也清除，P2无跨轮nonce状态。半诚实、同主机、非常数时间局限明确。真实AS链、全部祖先只读预算/撤销查询、接受事务动态重检均不可替代。数据库SELECT-only专用角色必须实际验证。进程分离P1作为本轮目标，明确其不等于OS强制隔离。

## 需求与验收矩阵（全部为计划，尚未执行）
|ID|交付与实际验证|
|---|---|
|B1|cosign curve/protocol/encoding，50随机密钥成熟验签、篡改/错钥/无穷远/非法点、一次nonce、固定坐标；公开三字段向量|
|B2|shares/keygen确认后写入，权限/角色/失败零写入；公有元数据不含秘密|
|B3|AuthorizationDomainSigner严格V3→policy/time→AS全链/holder/scope→只读DB全祖先→重算消息→partial；所有七类AUTHZ拒绝及零sign调用、SELECT-only权限探针|
|B4|服务端scheme，旧默认FROST不变，COSM2新profile/域/V3，统一VerifiedThresholdApproval和接受绑定；两向方案错配及无请求切换|
|B5|ExecutionDomainSigner请求/可信报价核对后round1→授权域→round3→信封；EXEC_MISMATCH/COSIGN_ABORTED，P0与独立子进程P1，等效fixture|
|B6|真实PG+AS+独立下游C1–C11：正常幂等、无批准、执行单域、伪64签、篡金额、签前撤销、签后撤销、余量不足、错方案、过期、成熟互验；原threshold全部回归|
|B7|真实固定六用例工具，严格原result.json契约、真实timings，本机cosm2-run/桌面入口、公网只读、文档与启动命令|
|B9|B6绿色后：独立下游配置公钥验签+精确业务意图绑定，转发原ag-approval，C12绕过网关零订单；原业务行为回归|
|B8|B6绿色且B9后：x402 scheme开关、真实V3 payment_digest/本地链正常仅一次及篡改拒绝；EIP3009/secp256k1不变|
|A1/A3/G1|B公开向量OpenSSL正负核验；原三交叉测试全部真实通过；不把旧失败抹掉|
|A2/A5|示意13步保留来源；本次现场运行与保存回放分开，六结果/单次三轮耗时；Node与1366x768实看|
|A4/G3|同固定镜像/CPU环境，10预热+100正式各项原始样本/失败保留；round2-db真实谓词；gateway-e2e明确计时边界和样本数。B7固定result无e2e字段，新增同run_id sidecar measurement.json，不改固定契约；不得三轮和冒充e2e|
|A6|四矢量PDF统一字体配色；七攻击×四位置矩阵仅实跑代码/证据；每格来源、命令/run_id/SHA可核对；渲染逐页QA|
|A7|原图总览/场景1、3、6/共签示意和真实/记录；真实3分钟运行视频可见run_id/日期/来源；完整C包raw/summary/figures/媒体/来源表/全部失败历史|
|G2/交付清单|实际通过数、独立审查、启动说明、局限与可写清单；冻结候选SHA，不宣布整个旧A3长实验完成|
|QUALITY|Python3.11固定依赖环境；ruff check/format、相关unit和完整原threshold/x402回归、实际隔离PG集成；不删除/skip/放宽负例|

## 接口和所有权
先串行冻结共享API，再按独占文件并行。第一批：core worker独占cosign/{__init__,curve,protocol,encoding,shares}.py、tools/cosm2_keygen.py、tests/unit/test_cosm2_{core,shares}.py、tests/cosm2-public-vector.json。gateway worker独占threshold/{contracts,codec,verifier}.py、gateway/config.py与新增scheme单测；不能更改旧字节。domain worker在core/gateway稳定移交后独占authz_domain/exec_domain/authz_cli、tests/fixtures/cosm2.py及domain测试。集成/演示与效果端按后续明确移交，禁止交叉写；root负责唯一整合、资源与证据。不消费peer半成品。

## 验证与资源
只用现有固定镜像agent-guard-threshold-gateway-runner:20261017（Python3.11/tongsuopy1.0.1）及x402固定runner。Docker arm宿主amd64仿真须披露；只建独占随机名PG16与网络，两个独立业务数据库、TEST DSN、owner标记；不得触碰现有服务。运行证据记录脱敏命令、原样输出、退出码、JUnit和资源清理。产物下artifacts/cosm2-full-20261017/。正式数据新run不覆写任何历史。历史失败进入C交付。原附件参考代码如需格式修正须保持数学/语义并保留原SHA，不能把其噪声当生产代码通过。

## 门控与独立审查
本包及关联现行覆盖冻结后全新PACKAGE_REVIEW，无阻断PACKAGE_READY后才写业务代码。G1真实绿色后接网关，B6真实绿色后B9/B8。全部writer STOP，完整代码/测试/配置/文档/原始数据候选清单SHA冻结，全新IMPLEMENTATION_ACCEPTANCE独立实跑。缺陷保留报告与失败原件，补正后新reviewer；不以实施自查冒充接受。最终完整本阶段接受且材料/自有资源清理后停止。
