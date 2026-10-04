# A2.2-integration 任务包 v1

状态：实施范围用户明确批准；运行适配亦已批准；包审待完成，未派发业务实施。基线HEAD `280022e`（文档提交保留），产品main `d7e91c7`。当前分支 `codex/a2.2-integration`。仓库绝对根 `/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`，不在父repo运行命令。授权原文与来源见 authorization.json。

## 目标与复用

补齐GM-MVP-1固定HTTPS网关invoke与result-read，复用已验收真实B密码/权限源/证据与A执行接受。仅A2.2；不签发/发布回执，不导出/锚定/部署，不进入A2.3/A3。每项完整义务见 requirements-v1.json：继承原67项60run不减少，新增28项；逐项断言映射、独立实跑并保持原历史失败/等价说明，不能只复制旧PASS。

必读AGENTS/AGENT/HANDOFF、原A2任务全篇、接口8/9/10、安全模型全篇、项目验收、A1/A2.1/B当前接受与全部问题台账、implementation/review契约、current-policy、模板以及实际调用方。原A2任务的旧路径/授权/待实施声明仅为历史；行为要求继续有效，最新真人授权优先。

## 串行范围与所有权

单worker串行完成共享query bundle/evidence/类型错误与装配、公开HTTP、正式正负测试及当前文档，禁止同文件并发。允许新增或修改仅下列精确文件（不要求创建无用途文件）：

- `src/agent_guard/gateway/__init__.py`
- `src/agent_guard/gateway/http_app.py`
- `src/agent_guard/gateway/endpoint.py`
- `src/agent_guard/gateway/config.py`
- `src/agent_guard/gateway/factory.py`
- `src/agent_guard/gateway/__main__.py`
- `src/agent_guard/gateway/errors.py`
- `src/agent_guard/execution/query.py`
- `src/agent_guard/contracts/verification.py`
- `src/agent_guard/contracts/execution.py`
- `src/agent_guard/authorization/verifier.py`
- `src/agent_guard/authorization/proof.py`
- `src/agent_guard/authorization/claims.py`
- `src/agent_guard/authorization/evidence_store.py`
- `tests/unit/test_gateway_boundary.py`
- `tests/unit/test_gateway_config.py`
- `tests/unit/test_gateway_errors.py`
- `tests/integration/test_gateway_http.py`
- `tests/integration/test_gateway_query.py`
- `tests/integration/test_gateway_tls.py`
- `tests/fixtures/gateway.py`
- `README.md`
- `HANDOFF.md`
- `docs/oauth-oidc-sm2-mvp.md`
- `docs/security-model.md`
- `docs/acceptance.md`
- `tasks/A2-report.md`
- `tasks/workflow/stages/A2.2-integration.md`
- `tasks/workflow/runs/A2.2-integration-20261004/implementation-r1.md`

其余源代码、既有正式测试/fixtures、历史迁移、SQLregistry、锁文件、pyproject/.github均只读。无需新增框架，复用uvicorn+原生ASGI、psycopg、tongsuopy；若确需额外文件/迁移/接口范围，先报主控重新审包，不悄悄扩大。主控独占本轮state、授权、任务/矩阵、台账、workflow入口/context/current-policy与最终报告；worker仅在上述指定当前文档及实施报告修改。自有 artifacts/workflow/A2.2-integration-20261004/worker-r1/ 内探针/环境/证据允许写，历史artifacts只读。

## 已确认接口与设计

1. invoke既有 `InvocationVerifier.verify_bundle`→`VerifiedExecution.accept`→`ExecutionService.accept_invocation`→`ExecutionLedger.accept_bound`及EvidenceStore.binding继续用；HTTP不接受已验权JSON，不启动下游，只返回202与真实当前operationstatus。已有终态重试保真实状态，不伪装新预留。
2. query新增冻结bundle保留VerifiedResultQuery、PermissionSource和opaque evidenceRef；增加真实verifier入口同时保持旧canonical-result API。EvidenceStore新增query原件绑定，优先用现有ag_proofs.operation_id/evidence_ref同事务关联；ag_operation_evidence仅first/retry，不将query伪作retry，无需修改B010。
3. query独立事务服务：严格DTO/purpose/endpoint→加载权威完整path→principals排序、task、root-leafgrants、operation固定锁序→身份/时效/权限包含/原操作ownership与可信材料核查→registerproof/link→读取可信result/outbox→约束flush与所有可能阻塞工作完成→重读已锁key/祖先与clock_timestamp最后新鲜性→commit。禁止fakeinvoke DTO或放宽A1acceptpurpose，禁止预算/业务/lease写入。坏原操作/legacy事实不从当前报价补造，失败关闭。
4. HTTP仅固定HTTPS `https://gateway.agent-guard.test/v1/invocations` 与 `/v1/operations/query` POST；严守8.5/9.4/9.6，原始body交真实verifier。头/体/framing/JSON有界与重复拒绝，敏感头不得合并后再验。同步签验/DB用受控线程离开事件循环，数据库等待有界；墙钟timeout遵循网关error envelope，不错误复用AS裸error。
5. 稳定分类错误须显式typedcode，不能靠解析异常文本。现有VerificationError可最小兼容扩展code/子类（保ValueError兼容和原验签逻辑），分别验证token/proof、schema、scope、expiry/holder，domain DB/执行错误按9.6映射。认证失败用AGPoPchallenge；不泄露内部细节，requestID服务生成。
6. 网关独立配置/CLI和真实装配不加载AS私钥；使用固定AS公开keys、登记identity/不可变DID配置、可信catalog、真实EvidenceStore/PermissionSnapshotProvider/ledger/execution和独立认证下游。秘密/DSN分开注入，私有文件安全primitive复用。init仅显式生成合成开发配置，不自动连接/重置库；check配置不连DB；run强制TLS、不推断Host/proxy、不缺配置默认启动。具体字段在实施报告列至多10个明确技术决定，源代码须严格检查字段/类型/alias。

## 验证与资源

worker/reviewer分别独占Linux Python3.11容器/venv（UID501可复用前段模式）、PG16容器+network、TEST gateway与独立downstream DB。初始既有容器 agent-guard-a2-pg、verivote-web、verivote-api 禁止连接/改动/清理。记录完整容器ID/labels/network/进程，清理核owner。不得dockerprune或共享compose down，禁普通部署DSN回退和打印秘密。精确runtime/devlocks与PEP517setuptools80.9，source逐字自有copy；非editablewheel独立目录无srcshadow，SQL全携带，子进程来源见证。

自查及fresh最终review完整跑所有非集成与integration，A1单列、A2/B原67运行/历史探针等价/新六补正回归及oracle负控。真实HTTP新P15/P16/P17和P21适用部分、真实TLSgateway进程/四工具/终态重试、新proof查询、每组10轮真实并发和确定性锁后TTL（包括lateDB依赖）须独立探针验证。至少一条真进程崩溃恢复、新网关进程可查询持久终态。拒绝/并发/故障断言beforeafter全部祖先金额次数、proof/操作/事件/outbox/下游效果，分离允许staging evidence与业务零新增。任何失败/skip保原件并补正，不弱断言。旧setuptools/历史升级/testtuple过严等适配保原失败与等价说明，不能伪造原日志找回。

## 自查、停写与闭环

worker交完整implementation-r1.md、版本与每条ID映射、真实退出码/JUnit、哈希索引、环境/安装出处、resources前后、自有清理/停止凭据及限制；状态READY_FOR_REVIEW/FIXED_PENDING_REVIEW。正式验收矩阵由新reviewer实跑，不自己标ACCEPTED。停写后主控核实际范围/只读哈希/所有进程，再冻结新候选派fresh reviewer。缺陷保稳定ID，新范围/需求重新审包；允许已获批本段内补正循环。通过后主控按授权commit/push/PR和必需CI，审核例外另问；完成A2.2后停止汇报。

## 冻结的HTTP细节与错误映射

- invoke无论CREATED/EXISTING均202，仅返回operation_id/status/receipt_status；status从真实接受结果/可信当前操作取得，不返回内部disposition。query成功200，仅operation_id/status/receipt_status/result/receipt_jws；未终态result=null，未发布receipt_jws=null。PENDING不得伪READY，legacy/corrupt材料503失败关闭。
- 不存在operation与其他tenant/task/grant/holder/kid对象统一403 SCOPE_DENIED，避免存在性枚举，不回显ID。当前过期403 EXPIRED、撤销403 REVOKED、key/holder mismatch401 HOLDER_MISMATCH，严格时效401 STALE_REQUEST。格式先独立schema验证；scope/资源授权失败403 SCOPE_DENIED；参数格式/未知tool/version/重复字段400 INVALID_SCHEMA。
- ExecutionError INVALID_PARAMS/UNSUPPORTED_TOOL→400 INVALID_SCHEMA；RESOURCE_NOT_FOUND/RESOURCE_NOT_AUTHORIZED/CONSTRAINT_MISMATCH/OPERATION_NOT_FOUND→403 SCOPE_DENIED；QUOTE_INVALID→409 QUOTE_CONFLICT；TRUSTED_DEPENDENCY_UNAVAILABLE/LEGACY_SNAPSHOT_INVALID→503 TRUSTED_STATE_UNAVAILABLE；其余不应该从publicaccept/query正常冒出，未分类编程错误500 INTERNAL_ERROR，不假装客户端格式失败。
- LedgerError REPLAY/IDEMPOTENCY_CONFLICT→409同码；BUDGET_EXCEEDED/CALL_LIMIT_EXCEEDED→422同码；TRUSTED_STATE_UNAVAILABLE/INVALID_COST→503 TRUSTED_STATE_UNAVAILABLE；INVALID_CONTEXT在可信结构校验后的授权上下文错配→403 SCOPE_DENIED。Ledger其它明确码同9.6。
- HTTP framing/media/过大/未知/错误method分别400 INVALID_SCHEMA、415 UNSUPPORTED_MEDIA_TYPE、413 REQUEST_TOO_LARGE、404 NOT_FOUND、405 METHOD_NOT_ALLOWED；所有error都使用统一嵌套code/request_id，敏感认证失败challenge仅AGPoP；no-store/pragma no-cache及content-type/content-length。request_id用服务端UUID十六进制32字符，不信任输入header。
- proof.py/claims.py允许仅兼容typed错误分类扩展，不改变验证算法、字段、窗口或签发语义；全AS/SDK正式回归必须通过。禁止按旧异常字符串推断HTTP安全语义。
