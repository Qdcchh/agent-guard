# 双域协同 SM2 网关原型

实现日期：2026-10-17（按规划提前实施）；文件名沿用规划的交付日期。原规划A1–A7/B1–B9及C交付已通过全新gpt-6.1-sol/high完整r2独立验收并正式接受，见[接受记录](../tasks/workflow/runs/cosm2-full-20261017/acceptance.md)。r1唯一C10测试时序阻断经最小补正、完整复验关闭，原失败保留。

## 协议及信任边界

方案配置为 `sm2-2p`，批准profile为 `AG-COSM2-APPROVAL-1`；签名消息为 `AGENT-GUARD-COSM2-ACTION-V1\n` 加严格V3行动的固定字段序JSON。份额以乘法关系形成SM2公钥，完整私钥不重建。执行域发Q1，授权域自己验证AS签名的root→mid→leaf委托链、精确holder/kid/路径和范围，并以独立SELECT-only角色查询所有祖先的撤销、有效期、剩余金额及次数；全部通过后自行重算消息及SM3(ZA||M)，才产生部分签名。执行域合成后用tongsuopy标准SM2验签，通过才输出64字节r||s。网关同样只调用成熟的 `crypto.sm.verify_sm2_message`。

授权域签名是只读检查，不预留预算。网关在接受事务中继续检查当前撤销、有效期、额度、持有者证明新鲜性与原批准的精确行动；签后撤销仍拒绝。业务幂等与nonce分别处理。同一批准重试需新鲜AGPoP且只关联原operation，不能新增订单。普通COSM2采购仍为V3，`payment_digest`固定64个0；支付部署必须换成真实付款意图摘要，不能拿该占位值绕过付款。

服务端配置决定方案，请求头不能选方案。缺少scheme仍是原FROST行为，旧V1/V2/V3字节和迁移001–009保持。COSM2批准过期返回401 EXPIRED，旧FROST及授权令牌过期仍为403。篡改金额在网关以独立可信报价/已接受不可变成本比对后返回409 APPROVAL_MISMATCH，最终接受事务仍重复绑定。

## 本机启动

先启动Docker Desktop，在仓库根运行：

```sh
python3 tools/teacher_demo_server.py
```

打开 `http://127.0.0.1:8765/` → 双域共签 → 运行固定演示。也可直接运行 `python3 tools/cosm2_desktop.py`，它创建自己独占的临时网络、PostgreSQL和runner，运行六个真实用例，按owner/fullID清理；不连接现有业务库、不发布数据库端口。公网入口只读，只有本机同源且通过会话令牌的固定控制动作能启动。保存的结果始终标为回放，新会话不会把磁盘记录冒称本次现场运行。协议时序示意与左栏真实结果分别标注来源。

固定镜像为 `agent-guard-threshold-gateway-runner:20261017`。首次在新机器部署可按 `deploy/threshold-runner/README.md` 构建；本机已有该镜像。镜像ID、运行环境、命令及输出均随阶段证据保存。当前Apple M5 Pro arm64运行amd64镜像，属于Docker仿真，不能把耗时写成本机原生性能。本机Docker内容存储存在显式platform参数找不到已有tag的问题，运行使用 `--pull never` 且不传 `--platform`，保留其真实架构警告。

## 复现核心与集成

```sh
docker run --rm --pull never --network none -v "$PWD:/work" -w /work \
  -e PYTHONPATH=/work/src agent-guard-threshold-gateway-runner:20261017 \
  /opt/venv/bin/python -m pytest tests/unit/test_cosm2_core.py \
  tests/unit/test_cosm2_shares.py tests/unit/test_cosm2_crosscheck.py -q
python3 tools/cosm2_vector_check.py tests/cosm2-public-vector.json
```

OpenSSL核验需要OpenSSL3，脚本优先发现Homebrew安装；正例成功和单字节篡改失败都必须满足。核心G1实跑76项通过，含50组随机密钥及三项参考实现交叉测试。B3/B5实跑19项覆盖真实AS链、SELECT-only权限拒绝、所有六码AUTHZ拒绝、P0/P1和nonce清理。B6提前门实跑COSM2 16项及原FROST网关24项共40项通过。以上为早期自查计数；最终独立实跑为非PG2072+host1补闭、真实PG552和x402142，详见接受记录。

数据库集成使用自己独占的一次性PostgreSQL16及两个独立业务数据库；只提供TEST连接，禁止复用共享库。真实固定演示可直接由桌面启动器创建全部临时资源，无需将DSN放命令行。手动集成命令为在相同镜像和独占网络内运行 `pytest tests/integration/test_cosm2_gateway.py tests/integration/test_threshold_gateway.py -q`，凭据通过0600 env-file注入且不输出。

## 数据与证据

固定演示写入 `artifacts/cosm2-gateway-demo-live/<run_id>/result.json`，严格保留原规划字段。`measurement.json` 额外记录实际HTTP调用前至202响应后的受理耗时（不包含签名前置准备、下游worker及结算），不能用三个签名阶段求和冒充。`negative-matrix.json` 保存实际拒绝位置、原样返回码、前后订单/操作/祖先预算及授权域签名计数；未触发的位置不推断为通过。三轮耗时是该次运行值，前端标明“单次运行，非统计结果”。

首次绿色固定演示run_id：`b944d1ab-4525-46a9-8bb1-1a9dbdbdca00`，六用例全部通过，操作/批准/订单各1，资源剩余0。此前失败run `b0ddb2c2-480a-4642-bf4f-fa3360809068` 原件保留，不能从交付中隐藏。新正式基准另开run，保留所有预热、样本、失败，不能混入旧机器/旧失败数据。完整原始命令与审查入口：`tasks/workflow/runs/cosm2-full-20261017/`、`artifacts/cosm2-full-20261017/`。

## 局限

半诚实两方(n=2)原型，无恶意安全证明、零知识证明或t-of-n推广。Python标量乘非常数时间，仅用于份额计算；SM2/SM3最终验签和哈希使用成熟实现。Python清除nonce引用不代表物理内存已可证明擦除。两域在同一主机同一OS用户下，P1子进程和0700/0600路径约束不是独立组织或OS强制隔离，管理员失陷不在所测安全保证内。只读角色是真实独立数据库角色，仅获ag_grants/ag_grant_tokens SELECT与schema USAGE，已实测写入及证据表读取拒绝；主机管理员仍能配置这些信任输入。

本地结果JSON和SHA清单是可复现实验记录，不是独立审计证明。测试失败输出中出现过合成JWS/临时角色密码，公开失败日志已脱敏；部分未脱敏原件未保留且没有原SHA，报告明确该证据限制，不冒称全部输出逐字原样。生产CLI不打印令牌、份额或数据库连接串。无真实资产、无生产部署安全声明。

正式性能来源 `20261017-full-02`：九项各100次、预热各10次，raw900/warmup90，全部成功。控制器另存run-conditions.json：本阶段并行集成测试/录屏准备共享宿主，未控制CPU隔离/频率或用户其他负载；保留全部样本，不将其当独占性能或吞吐率结论。纯共签中位数15.888ms/p95 16.325ms；含AS/只读谓词的round2为25.966/27.516ms；新受理HTTP→202为71.580/87.021ms，这三个边界不可相加或混称。

## 效果端独立验签（B9）

生产factory在配置sm2-2p时，同时为ExecutionService及MockDownstream配置同一COSM2公钥策略。执行器在首次执行和UNKNOWN重发时从不可变ag_threshold_approvals读取原envelope，再把持久操作的租户、任务和业务幂等键一并转发；下游先成熟SM2验签和精确金额/商品/参数/报价标识/业务键比对，再在独立事务中以签名action和业务键唯一绑定operation，防止同批准换操作编号重复造单。既有结果回放分支也不能绕过验签。

独立下游增加ds_cosm2_bindings表，由现有显式MockDownstream.provision()幂等初始化；已有部署须先执行原下游provision步骤，factory按既有约定不自动改库。网关迁移001–009未改。C12覆盖正确服务凭据下无批准、伪签、改金额、改商品、改业务键/租户/任务、已有记录坏批准、换operation重放、并发双操作和响应丢失恢复。相关完整旧执行回归538项通过。

该效果端门只复核签名、精确业务意图和一次性绑定，不独立查询AS、当前撤销、预算、付款结算或重做墙钟到期决定；已被接受的不可变工作仍可延迟执行/恢复。因此可写“所测无有效共签或业务意图错配无法产生订单”，不能无条件写“网关被攻破后任何订单都无法产生”，也不能覆盖同主机管理员失陷。

## x402共签付款意图（B8）

运行工具新增 `--approval-scheme sm2-2p`；省略仍是旧FROST。示例（在固定x402 runner和自己的独占测试PG环境内）：`python tools/x402_gateway_demo.py --approval-scheme sm2-2p`。该工具自己启动并停止本地Anvil，不使用真实资产。与B9组合装配时付款gate和resource服务从持久数据库转发原始批准上下文，不能用请求字段代替。

准确说法：**付款意图必须经双域SM2共签批准；链上结算签名仍是EIP-3009（secp256k1），未替换。** 执行域自己从可信配置重算payment_digest；篡改该绑定被拒绝且不产生效果。原固定结果格式保持兼容，真实批准方案/profile/各用例公钥及额外篡改观测记录在版本化cosm2-payment-binding.json，不能从旧展示profile字段推断实际签名算法。

真实本地链run_id `5fffa6e5-f95b-4fd7-a898-9f7b8dbb3113`，六用例全通过；正常付款只结算一次，另一个恢复用例也只产生一次效果。六个独立用例合计2张订单、2笔链交易（不是单个正常请求付两次）。142项回归（原139矩阵+新增3项）通过，原命令输出及sidecar位于artifacts/cosm2-full-20261017/x402/。该环境是固定amd64 x402 runner仿真，和纯签名基准镜像分别记录，不能混合为同一组性能样本。

最终现场媒体采用真实按钮run `01af29ac-26be-4616-851d-d8afa38fa46e`，capture-03包含11份原始截图和185.4秒WebM/MP4，native退出0、实际wait与current-run来源一致；四图PDF已实际渲染校验。此前两份采集失败的视频与原成功业务结果同时保留为失败采集历史，不冒称最终视频。
