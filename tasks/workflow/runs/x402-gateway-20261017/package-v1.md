# x402 接入采购执行链 v1

## 真人授权与范围
2026-10-17 真人当前消息：“把x402也做了吧”。承接上一轮要求一路补齐必要安全验证、不要反复精细复核、按原工作流。现在授权 x402，实现并验收，不只是设计。此前“不做x402”仅为旧阶段范围，已被本授权覆盖。OpenCode Go deepseek-v4.1-flash/max 实施；fresh gpt-6-astra/high 包审与实施验收分离，effective UNKNOWN。无Git发布，无旧A33/A34长实验，无真实资产付费或用户钱包。

本阶段为可运行本地测试链 x402 v2 exact/EVM EIP-3009 支付闭环接入现有真实采购链。真实标准签名、真实本地EVM结算与交易回执；不能把内存计数或假验签称作链结算。公网仅浏览，本机一键固定演示。任一生产网络接入/真币不属于本阶段。官方规范固定 x402-foundation/x402@faa1c694c66a3732aaabbce93bdae140e521a67d；Python官方 x402 2.25.0 实际PyPI可取。实施核对SDK与此profile吻合并锁定依赖/许可。允许官方SDK+成熟eth-account/web3及本地EVM(eth-tester/py-evm或Anvil)，测试合约复用官方/OZ成熟签名验证，禁止自研密码或伪造成功。

## 必读及基线
AGENT.md、current-policy.md、README、docs/{oauth-oidc-sm2-mvp,security-model,acceptance,x402-adapter-design-20261016,threshold-gateway-20261017}.md，上一阶段acceptance、实际gateway/threshold/execution/ledger/downstream与tests。当前751+文件既有dirty/staged/untracked必须保留，baseline在artifacts/x402-gateway-20261017/baseline。旧001-008迁移与签名字节不得修改，新增迁移009起，wheel/lineage同步。

## 完整交付 X1–X8
X1 真实协议闭环：固定x402v2 exact/EVM/EIP3009；真实HTTP 402 PAYMENT-REQUIRED、PAYMENT-SIGNATURE及PAYMENT-RESPONSE，官方SDK真实支付签名/验证，本地EVM上交易、收款余额/nonce状态变化与真实receipt。固定authorization顺序verify→resource→settle；若选其它规范flow须说明精确profile。付款不代替OAuth/SM2/AGPoP/门限批准。
X2 可信意图：只从现有真实网关已接受不可变采购操作驱动适配器，不接任意browser/model URL或金额。不可变PaymentIntent绑定租户任务、完整授权路径、门限action/操作/业务键、resource URL、收款方、network/chainId、asset、整数最小单位金额、报价摘要/版本、有效期。须与门限批准可验证关联：可新增V3 action payment digest保留V1/V2，或通过原批准完整覆盖的可信不可变报价映射固定全部支付事实（必须证明不会同quote换对象）。收款/网络/资产/金额/资源/有效期变化必须拒绝；改变批准对象须重新授权及批准。无隐式CNY兑币，独立明确测试资产预算，保留CNY原全祖先预算，独立资产预留持久且不能超支。
X3 持久支付状态与原子预留：UNPAID/AUTHORIZED/SUBMITTING/UNKNOWN/SETTLED等明确状态；签名授权与nonce/完整payload在网络前持久化，同operation幂等且不可换支付intent。支付预算预留与接受绑定在可信事务边界原子，失败无烧批准/预算；重复或并发相同业务不重签不同nonce、不重复扣款/订单。外部chain与PG不伪称原子；钱包私钥仅受控组件，新生成测试钥无真实资产、前端/模型/公开state无私钥原始payload。
X4 故障恢复：响应丢失/广播确认不明→UNKNOWN保持预算、不直接释放或生成新授权重付；按持久nonce/txid/链事件查询终局，区分支付与资源交付状态（付了款但资源失败仍记录已付款，不因HTTP错误当未付）。真实独立进程恢复至少一例；只重试相同持久授权且需安全论据。报价/期限过期与未知终局不能被恢复路径绕过。避免持PG锁进行HTTP/RPC；lease/fencing/并发互斥遵循现有链。
X5 HTTP/钱包安全：严格有界解析(重复/未知安全字段、布尔/浮点/负数/溢出、恶意header/base64)，固定来源与facilitator/RPC白名单、拒绝重定向/任意URL/SSRF；生产HTTPS校验不得关闭，本地loopback/testnetwork例外只能固定演示装配，不能生产环境跳过验权。签名前逐字段与可信intent核对，不能让不可信402决定签名内容；支付私钥与FROST份额分开，链签名不称SM2。
X6 必要验证：真实PG/真实SM2+FROST网关接受→x402 HTTP→真实本地EVM结算的一单一付款正例；缺批准/撤销/超预算不得付款；换payTo/network/asset/amount/resource、过期报价、伪签名/畸形包拒绝；重复并发/重放不重付；接受回滚不烧资产预算；结算成功失响应恢复、未知不释放、进程重启持久恢复。检查全祖先CNY账本、独立资产预算、operation/approval/payment/tx/order关联。范围聚焦，复用未变历史证据，不重跑旧325case等待矩阵/1800广泛/40000。
X7 桌面与页面：保留Claude设计，一键运行固定x402演示，自动专用Docker/PG/localEVM资源准备清理，无host密码库/手动DSN。可复用threshold桌面框架但旧入口保持可用。真实脱敏结果展示402→批准支付→结算/拒绝/UNKNOWN恢复，测试链/测试币标识明确，公网POST403/无控制token/只读结果。真实本机按钮实跑必须成功，别只交容器CLI。
X8 文档与交付：更新旧x402设计状态、协议pin/SDK依赖锁许可/构建运行/迁移/恢复说明，诚实声明本地测试链、非商用真实支付、同宿主/同用户、非SM2链签名、非全项目接受。REPORT命令/exit/pass/fail/skip与局限；STOP无更多写入/精确资源清理。私钥/DSN不进git/公开日志；原失败原件保留。

## 所有权与验收
主实施worker独占src、新009迁移、相关tests、tools、deploy、web/teacher-demo、docs、依赖锁与README；不改tasks/workflow/旧历史/旧迁移/备份。主控只调度/证据/本地服务状态。可在稳定接口冻结后显式移交独立桌面文件，不并发修改共享接口。先fresh包审PACKAGE_READY再实施。worker完成针对性单元+集成/真实链+少量旧threshold回归+lint/format、原生退出与清理后STOP，主控冻结全非ignored源清单，一次fresh独立X1–X8安全验收与必要真实探针。只修实际阻断，不反复精修，不把模拟或工具装配失败称PASS。
