# A2.2-integration 实施检查点 worker-r1

- 状态：**PAUSED_BY_USER**。非 READY_FOR_REVIEW、非 ACCEPTED。
- 用户明确要求“请在合适地方暂停，我要出门”；主控于本轮转达，优先停止继续实施及后续长验证。
- 包：task-v1.md、requirements-v1.json、authorization.json、runtime-addendum-proposal.md；独立包审 PACKAGE_READY。本次暂停不改变授权或已批准阶段范围。
- worker：`/root/a22_worker_r1`；请求配置由主控指定 gpt-6.1-sol/medium；有效后台metadata UNKNOWN。
- 分支：`codex/a2.2-integration`；HEAD `280022e9d7005daa8d551ba0e4c52e3228e3add5`（文档基线，未commit/push/PR）。产品基线d7e91c7。
- 证据目录：`artifacts/workflow/A2.2-integration-20261004/worker-r1/`；控制文件由主控拥有，本worker未改任务/矩阵/授权/state/context/current-policy/workflow入口。

## 保存的实现与测试草稿

以下18个非空Python文件属于worker写范围；暂停后全部用stdlib ast.parse成功，仅证明语法可解析，不证明导入、行为或安全满足。

- `src/agent_guard/authorization/claims.py`
- `src/agent_guard/authorization/evidence_store.py`
- `src/agent_guard/authorization/proof.py`
- `src/agent_guard/authorization/verifier.py`
- `src/agent_guard/contracts/verification.py`
- `src/agent_guard/execution/query.py`
- `tests/fixtures/gateway.py`
- `tests/integration/test_gateway_http.py`
- `tests/integration/test_gateway_query.py`
- `tests/unit/test_gateway_boundary.py`
- `tests/unit/test_gateway_errors.py`
- `src/agent_guard/gateway/__init__.py`
- `src/agent_guard/gateway/__main__.py`
- `src/agent_guard/gateway/config.py`
- `src/agent_guard/gateway/endpoint.py`
- `src/agent_guard/gateway/errors.py`
- `src/agent_guard/gateway/factory.py`
- `src/agent_guard/gateway/http_app.py`

已保存：冻结query bundle、保canonical-result API、同事务query evidence binding、独立零业务成本query服务、typed token/proof错误与公共映射、两固定HTTPS POST ASGI transport/endpoint、只加载AS公开信任的独立配置/装配/CLI。queries按principals/task/root-leaf/operation顺序、原ownership/材料/当前权限复核，proof登记关联、约束flush后最终clock检查。这些是**待验证实现草稿**，不可作为已具备能力声明。

新增正式测试草稿包含ASGI拒绝/隐私/超时容量、typed映射、真实B→A invoke/query流程、全部五状态零业务成本、query并发重放10轮、操作/proof-link/deferred锁后时效正负对照10轮、撤销/key停用先后线性化10轮、ref/source/ownership替换与legacy材料拒绝。测试未收集、未运行；没有通过计数。

未创建 `tests/unit/test_gateway_config.py`、`tests/integration/test_gateway_tls.py`。未修改 `contracts/execution.py`。README/HANDOFF/设计/安全/验收/A2-report/stage等worker文档尚未同步，维持此前内容；主控已指出stage旧“未授权”状态需恢复后修正。已有主控3控制文档改动保留。

## 已执行命令及真实限制

1. 只读读取Git状态、任务包、实现/周边代码、主要规范与历史harness。完整必读资料和逐条原断言的续接复核仍需继续；早期多文件输出有截断，不冒称全篇已读。
2. 自建Python3.11-slim容器和独占PG16-alpine容器/network，执行apt基础构建工具安装、requirements-dev.lock安装、setuptools80.9.0/wheel安装、逐字 `/source` copy、非editable包安装和pip check。安装shell最终exit0，日志记录agent-guard0.0.1构建成功及锁定runtime/dev包；该copy在新增模块完成前创建，不是最终候选source/wheel证据。未记录最终父子import出处，未完成精确PEP517环境/SQLwheel核验。
3. 首次Ruff在RO挂载上尝试cache，exit2（只读缓存）；随后`ruff check --no-cache`检查草稿，有大量E501/一条I001，exit1，不能称lint通过。原终端合并命令尾部cat使shell最终exit0，不代表Ruff成功。
4. format harness把`ruff format -`的空stdout误写到owned文件，造成13源文件草稿变空；暂停检查diff发现后立即恢复。五tracked文件按HEAD280022e字节读取、重放已保存edit_core.py；八新增源文件从**本worker此前工具调用原文**提取精确heredoc、重放fix_transport.py。恢复后13源文件均非空且ast.parse通过。首次恢复因会话日志schema匹配错误，AssertionError exit1，未更改只读/控制文件；改用实际custom_tool_call/input字段后恢复exit0。`format-harness-recovery.json`保存完整恢复依据。错误format脚本/空query-format.py保留为失败证据，不应再次使用。没有把删除行状态当候选冻结。
5. stdlib ast.parse恢复后18文件exit0，见syntax-checkpoint.json。**没有执行pytest、没有JUnit、没有运行新网关/真实TLS、没有业务PG事务测试、没有完整历史回归、没有source/wheel最终验证。**

## 具体续接待处理事项

- 先完整补读本段95项/88run、原A2接口/安全/验收及原A1/A2/B正式接受/问题/探针，核包与现有草稿差异。
- 修复/替换格式化harness，仅读写29允许范围；对新模块运行实际lint/format和imports，保留此前失败。当前草稿未格式化，不可直接进入review。
- 已知待核：verifier“duplicate or unauthorized SKU”共用默认400，合法未授权SKU应显式403；未知tool/坏params分类须保持schema先于权限。trusted corrupt JSON/receipt材料异常需统一503，不误作编程500；配置未知字段/路径/identity/catalog边界需正式测试。
- 测试草稿中的 `test_rejection_before_services` path变体同时传默认path和changes path，需排除重复kwarg；`test_real_http_invoke_query_retry_and_no_implicit_worker`含一条无效条件占位断言，应删除占位并以真实断言替换；不属于已有原测试弱化。
- 补全真实TLS独立gateway进程和默认CA/hostname负控、四工具/真worker崩溃恢复/网关重启查询，扩query所有晚依赖、token/grant窗口及当前权限/原事实负例；重放等并发要捕获所有异常并实跑目标/负控。
- 重新自建owner资源（已全部销毁，不复用共享容器）；安装真实Python3.11精确锁及setuptools80.9构建、最终source copy和非editablewheel无shadow/父子来源/全部SQL证据。
- 原67/60回归及历史A1/A2/B原失败与等价适配、六补正/oracle负控、所有source/wheel suite、A1单列、demo/逐字README都仍必需。本轮所有95项的行为完成状态均NOT_RUN，详见下表。
- 最后同步worker当前文档、完整95ID→真实node/断言/exit/JUnit/hash，再停writer与清owner资源，交主控freeze/freshreviewer。当前只是用户暂停检查点。

## 95项矩阵（暂停检查点）

| 必需ID | 保存的节点/映射情况 | 本轮行为结果 | 实际exit/JUnit/限制 |
| --- | --- | --- | --- |
| A2-P01 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P02 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P03 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P04 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P05 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P06 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P07 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P08 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P09 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P10 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P11 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P12 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P13 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P14 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P15-CORE | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P19 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P20 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-CKPT1-OBL01 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-CKPT1-OBL02 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-CKPT1-OBL03 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-CKPT1-OBL04 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-CKPT1-OBL05 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-CKPT1-OBL06 | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| WF-A1-REGRESSION | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| WF-INDEPENDENT-PROBES | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| WF-QUALITY-CHECKS | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| WF-PY311-ENV | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| WF-RESOURCE-ISOLATION | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| WF-IMMUTABLE-BASELINE | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| WF-DOCS-REPORT | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| WF-SNAPSHOT-COVERAGE | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-01-CRYPTO | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-02-ENCODING | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-03-IDENTITY | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-04-TOKEN-POLICY | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-05-INVOKE-PROOF | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-06-CODE-OIDC | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-07-ROOT-ISSUANCE | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-08-DELEGATION | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-09-DYNAMIC-STATE | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-10-HTTP-TLS | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-11-RESULT-READ | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-12-EVIDENCE-RECEIPT | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-13-ROTATION-INTEROP | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-14-DB-FAILURES | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-15-CONCURRENCY-TEST-EFFICACY | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-16-A1-REGRESSION | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-17-B-SUITE-QUALITY | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-18-RESOURCE-ISOLATION | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-19-CONTRACT-MERGE | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-20-MIGRATION-MERGE | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-21-SHARED-FILE-MERGE | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-22-ORIGINAL-GOAL | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-23-HANDOFF-REPRODUCIBILITY | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| B-24-FINAL-BINDING | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| BR-01-CONSENT-FINAL | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| BR-02-HTTP-REJECTION | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| BR-03-PRIVATE-PATHS | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| BR-04-LINEAGE-HISTORY | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| BR-05-LINEAGE-ATOMIC | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| BR-06-REAL-PERMISSIONS | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| BR-07-QUERY-DTO | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| BR-08-EVIDENCE-BINDING | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| BR-09-RECEIPT-PROJECTION | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| BR-10-IMPORT-PROVENANCE | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| BR-11-CLEAN-CANDIDATE | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| BR-12-WORKFLOW-BARRIER | 继承正式suite/历史probe；未重跑 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P15 | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P16 | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P17 | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A2-P21-HTTP | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-01-REUSE | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-02-TRANSPORT | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-03-FRAMING | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-04-INVOKE | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-05-QUERY-BUNDLE | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-06-QUERY-LOCKS | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-07-QUERY-OWNERSHIP | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-08-QUERY-FINAL-CLOCK | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-09-QUERY-REPLAY | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-10-QUERY-ZERO-COST | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-11-QUERY-EVIDENCE | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-12-QUERY-PERMISSION | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-13-DYNAMIC-RACES | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-14-ERRORS | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-15-FAIL-CLOSED | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-16-PRIVATE-CONFIG | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-17-STARTUP | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-18-REAL-TLS | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-19-PRIVACY | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-20-BOUNDARIES | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-21-DOCS | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-22-REGRESSION | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-23-ENV-PROVENANCE | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |
| A22-24-FREEZE-RESOURCES | 新gateway/query草稿及新测试草稿；未运行；无实际断言证据 | NOT_RUN | 无pytest exit/JUnit；暂停前未达到完整自查 |

## 资源清理与停止

创建前已有 `agent-guard-a2-pg`、`verivote-web`、`verivote-api`；本worker未连接、修改、停止或删除它们，清理后仍全部原ID运行。仅本轮owner `a22-worker-r1-20261004` 的Python容器、PG容器及network，逐项完整ID/label核验后docker rm/network rm，三个exit0。见cleanup-owned.json（完整ID、RO/RW挂载与前后实际情况），resources-created.json（成功创建记录）。清理后owner过滤容器/network均0。

安装在暂停前已完成，无pytest/网关/worker进程启动，无业务事务待收尾；删除自有Python容器终止其中sleep进程并销毁自有venv/copy；PG tmpfs随容器销毁。自生resource-private.json/test.env凭据材料已在清理后删除，只保脱敏归属记录。用户workspace、历史证据与无关容器未删。

本报告和证据index生成完毕即停止worker全部写入，等待主控记录暂停指纹。证据index不是实现通过声明；恢复须真人续接授权，不自动跑A2.3/A3/部署或Git发布。
