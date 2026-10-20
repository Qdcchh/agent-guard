# COSM2 可写清单与最终交付依据

范围是原《双域协同SM2实施规划》A1–A7、B1–B9，不代表旧A3.3/A3.4四万次长实验完成。本清单复制原第5节并逐项关联实际证据；原始规划文件原样保留。以下项目已由全新gpt-6.1-sol/high完整r2独立验收并由主控接受，见[tasks正式接受](../tasks/workflow/runs/cosm2-full-20261017/acceptance.md)。r1否决及补正原件保留。

- [x] 两方协同SM2核心库：G1 76项，含50随机密钥、三个参考交叉测试，成熟库最终验签；core/命令、日志、JUnit。
- [x] B公开向量经OpenSSL3独立正例和改单字节负例核验：core/openssl.log，公开tests/cosm2-public-vector.json。
- [x] 授权域谓词门控：实际AS完整链，六码AUTHZ拒绝、严格坏输入、全祖先当前状态、零round2拒绝计数；19项域测试、P1修正后35项联合检查。
- [x] 服务端scheme切换、旧编码不变和原门限回归：gateway/91项及integration/b6-threshold-r4 40项。
- [x] C1–C11共11类，16个参数化真实采购集成用例通过；另加真实P1执行进程只读取自身份额测试。包含早期验签及最终DB时钟401过期、签前/签后撤销和真实剩余额度。
- [x] 固定六用例现场运行：最终A7真实按钮run_id 01af29ac-26be-4616-851d-d8afa38fa46e；较早B9启用实跑5efd0b13-bf3e-4062-b8ed-0048e110dbb9，操作/批准/订单各1、资源0。
- [x] B9下游独立成熟SM2验签、精确业务绑定与同批准防跨操作重放：C12及并发/恢复用例；完整旧执行回归538项。
- [x] B8付款意图共签：本地链六用例run5fffa6e5-f95b-4fd7-a898-9f7b8dbb3113，142项回归；EIP-3009/secp256k1结算算法保持。
- [x] 九项真实基准各100正式+10预热，正式来源20261017-full-02，raw900/warmup90、失败0；110个新受理的三祖先真实预留7700000分/110次，效果0（计时排除worker）。
- [x] 四份最终矢量PDF、11份未标注截图及185.4秒真实界面视频已完成渲染/时长与来源校验；同一现场run_id 01af29ac-26be-4616-851d-d8afa38fa46e，capture-03及figure/media metadata绑定。
- [x] 完整C候选包及来源表/SHA/失败历史已经校验：受审candidate3共571份来源、573个包成员，独立复制字节及ZIP CRC/SHA核对通过；最终包追加接受报告/完整r2证据/当前启动与本清单，原受审清单保持。
- [x] fresh gpt-6.1-sol/high完整独立实施验收r2 ACCEPTED：非PG2072+host1补skip、真实PG552、x402142、并行延迟8、独立probe7；r1唯一阻断COSM2-R1-001关闭，原报告及失败保留。

## 必须随文说明的条件

半诚实、n=2、Python标量乘非常数时间；同主机同OS用户，P1进程和权限并非强OS安全隔离；Python不能保证物理内存擦除。真实只读数据库角色仅SELECT两张授权表和schemaUSAGE，写入及证据读取已实际拒绝。授权域不预留，签后撤销由网关接受事务挡住。效果端只复验签名/精确意图/一次性绑定，不独立重做AS动态授权、当前预算/撤销或付款状态，不能作无条件网关失陷安全声明。

基准为Apple M5 Pro arm64宿主上的amd64仿真环境，宿主同时有其他隔离测试及录屏准备，CPU隔离/频率和用户负载未受控。全部原始样本保留，FROST含进程启动/I/O/复验，纯共签/含谓词round2/HTTP202三个边界不同，不用于生产吞吐率或算法优劣结论。full-01因镜像ID记录截断原样保留并排除，full-02全新采样不混行。失败历史有显式脱敏副本，部分未脱敏原件和原SHA不可得，不能写成全部逐字原样保存。

## 来源索引

- 完整原始授权及需求：tasks/workflow/runs/cosm2-full-20261017/package-v1.md、package-review-r1.md、implementation-notes-v1.md；原规划第0–5节。
- 原始命令输出及实际JUnit：artifacts/cosm2-full-20261017/{core,gateway,domains,integration,x402,bench,ui}/；G1与B6门记录只代表自查门，不代替独立验收。
- 真实COSM2结果、受理计时sidecar与负例观测：artifacts/cosm2-gateway-demo-live/<UUID>/。
- 论文图：复赛冲刺材料-20261018/论文模板/figures/，每张图的来源JSON记录命令/run_id/SHA。
- 最终C包以本地新建目录/ZIP交付，未发消息给C，未Git提交/推送/标签。冻结采用内容清单SHA与本地候选命名，不把指向旧HEAD的Git标签冒称未提交实现冻结。
