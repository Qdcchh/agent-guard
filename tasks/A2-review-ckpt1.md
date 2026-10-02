# A2 检查点一验收：需补正后复验

日期：2026-09-30。结论：**NOT_ACCEPTED（检查点一）**，暂不开始 A2.1 主体实现。检查点一已实际交付，但环境隔离和部分核心方案尚未闭合；不是认定尚未实现的执行器/004/HTTP本身有缺陷。B缺失不阻止A2.1分层实施。

依据：实际 Git 状态、新增文件、A2-report、既定任务与设计、独立 reviewer 检查。主代理未修改业务代码、测试、Compose或现有报告，不提交/推送。

## 1. 已确认的交付与验证

- 分支 `feat/a2-execution-gateway`，HEAD `b120c7c`。
- 新增 `compose.a2.test.yaml`、`contracts/execution.py`、`test_execution_contracts.py`及两份任务文档。
- **实际另有已跟踪修改**：`src/agent_guard/contracts/__init__.py`新增42行导出；报告“未改任何既有文件/已跟踪diff无”与实际不符。该修改为加法，未发现导入回归，必须更正记录。
- reviewer独立运行：unit/骨架/文档 **73 passed**；ruff check通过、format **31 files**通过、diff检查通过。
- `artifacts/A2/ckpt1/`已有A1 PG基线 **78 passed**记录；本轮验收只核对证据，**未独立重跑写库集成**。Python3.11/远程CI本检查点未跑，A2行为主体未实施。
- 实际新增类型与分段边界基本正确：无伪密码、无网络已验权JSON入口；完整A2尚为PARTIAL。

## 2. 主体开工前的必改项

### C1：Compose所有权隔离（高）

`compose.a2.test.yaml`和A1 Compose默认project均为`agent-guard`，service均为`postgres`；reviewer确认运行A2容器也是该标签。不同container_name/端口不隔离Compose管理范围，交替up/down可能重建或删除另一套容器，tmpfs数据随之丢失。未发现本轮已经损坏A1的证据。

**要求：** A2加固定独立顶层`name`或所有命令统一使用独立`-p`；修正启动/清理文档。旧A2容器仍有旧标签：先核对容器ID、Compose标签、配置来源、挂载和状态，记录其测试数据可丢弃性；仅处理已确认本任务自建A2容器，禁止用共享project的down粗放清理。若不能确认所有权或数据可丢弃，先问用户。复验两Compose渲染project不同，新实例标签正确，无关资源不变。

### C2：成本重试流程闭合（高）

报告决定1是“先当前报价解析再accept”，决定2声称“删报价仍可EXISTING”。但报价解析失败会在进入A1 EXISTING前拒绝；A1返回原成本不能自动解决A2前置流程。

**要求：** 可以保留A1 accept签名，但明确完整流程：可信静态验权/严格参数检查→内部业务键候选查找→已有候选使用其原成本/快照及持久化关联事实做当前权限核对→仍调用A1 accept完成锁后动态复核、防重放、完整意图比较。命中不直接返成功、不绕撤销/过期/holder/grant/参数冲突。仅新键取当前报价；列明候选删除/保全和查找miss后并发接受的处理，包括在解析失败时安全重查候选，不能把竞态错误转换为成功。P11设计须覆盖删报价后同键成功、新键拒绝、撤销/重放/变意图仍拒绝。

### C3：迁移与旧行保全（中）

计划给ag_operations增加review_required列/置位，但已有升级回归前后SELECT *比较七表全行；即使默认FALSE，加列也改变tuple形状，且与原行不变承诺边界不清。

**要求：** 优先新增按operation_id关联的隔离sidecar表，记录原因而不改变原七表行。若另选加列方案，先提出保留原列逐列精确比较的明确兼容方案，不直接删弱升级断言。旧材料不足保留预算、隔离待处理，不补造当前报价或证据。

### C4：终局互斥约束不足（高）

UNIQUE(operation_id,seq)不限制phase/seq对应，SETTLE/1和RELEASE/2可共存，多次RESERVE也可用不同seq。报告当前“数据库保障互斥”不成立。

**要求：** 004设计增加RESERVE→seq=0、SETTLE/RELEASE→seq=1约束，结合原唯一性保障一次预留/最多一个终局；保护已写事件/节点不被UPDATE/DELETE绕过，并列明与现有测试隔离清理兼容方法。预检错误旧数据时拒绝升级不修复式清零。后续P20包含直接SQL绕过负例。检查点一只需闭合设计，不要求先实现整个004。

### C5：租约claim/恢复与状态图（中）

补表说明：RESERVED取得租约同时→EXECUTING；过期EXECUTING接管租约先对账不释放；UNKNOWN取恢复租约但保持UNKNOWN；活跃租约/终态/隔离操作拒绝或无变动返回。明确每种入口的锁序、owner+version+实际DB时效条件及旧worker迟到处理，不能统一claim强制UNKNOWN→EXECUTING或放宽状态图。

### C6：下游完整报价绑定（中）

DownstreamOutcome只返回quote_id/version、规范参数和总额，未定义完整快照，不能排除同总额/同ID但供应商或单价分配不同。

**要求：** 在实际类型和说明中返回持久化完整TrustedQuoteSnapshot或已定义的等价可验证绑定材料；执行幂等比较与查询对账均绑定原快照。A2.1结构化比较即可，无须伪SM3；不一致可能已有效果→UNKNOWN。记录非订单工具及终局拒绝时的字段语义。

## 3. 同步修正/记录（不要求等待B）

- **报告真实性：** 补入contracts/__init__.py修改，明确004只是计划、非已实现；类型docstring不能称尚不存在的004已经强制执行。列出实际diff和未跟踪文件。
- **查询门槛：** VerifiedResultQuery缺evidence_ref，A1 proof登记列为NOT NULL；说明subject/路径绑定的可信来源，GrantConstraints不等于带scope、grant/token绑定及完整祖先的权限快照。可修可信类型/接口提案，生产B契约仍待确认；不把占位当确认。
- **回执稳定材料：** 固定iat（如由持久化created_at派生），区分结构化JSON/普通字节与B规范编码后的字节；frozen dataclass内部dict仍可变，明确复制/不可变存储边界；A1不透明摘要不能直接当真实SM3。真实B签名尚未实施，不将此称为已生成错误回执。

## 4. 最短交回指令

只修检查点一，不开始主体：依次完成C1—C6方案补正、必要Compose/可信类型及契约测试修改，更新A2-report及证据；保持001—003及A1业务逻辑不变。提交文件清单、两个Compose隔离渲染/标签核验、unit/lint/format、报告矛盾纠正、未决B项，然后停止等待主代理复验。不commit/push/PR，不降低任务矩阵。
