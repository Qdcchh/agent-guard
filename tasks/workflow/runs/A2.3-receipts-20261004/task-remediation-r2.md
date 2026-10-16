# A2 同段 quote/facts 补正与唯一整合 r2（正式待新独立包审）

真人恢复授权继续有效。独立reviewer r1已实际NOT_ACCEPTED、原生FINAL STOP、自有资源0并经主控完整读回；完整报告原样保存review-r1.md。当前只启用新独立PACKAGE_REVIEW，冻结核准新增文件所有权、真实依赖与容量域说明后，方可激活sole worker。worker请求gpt-6.1-sol/medium，有效metadata UNKNOWN，不得children或自标接受，不实施A3。

## 缺陷与范围

A23-R1-PUBLISH-QUOTE-ARITHMETIC，P2阻断：普通SQL immutable guard正控有效；仅在自有故障fixture把原quote和result同一单位价+1，原total/首次签名材料/params/账本/DS保持，source和非editablewheel各1F/exit1，真实publisher仍commit READY，SDK仅一致性验收通过而当前query503。完整失败、CorruptRow原始探针、全119报告均只读保留。完整source r2=2798P/1F/exit1，wheel r2=2799P/exit0；r4/r5为真实中断，不称整套green。

最小补正应复用 execution.service.verify_accept_facts / tools.catalog.snapshot_from_bytes 的既有严格原接受事实校验，绑定已读取operation、完整events和真实root→leaf path，在真实sign及publication更新前 fail closed。历史发布不重新查询/采用当前quote、下游结果，不按当前撤销或到期拒绝已接受终局，不增授预算，不改receipt ID/iat/原17claims/签名输入或任何接口。新读取与约束都在query原最终DB时刻之前，pub不倒锁。

拟sole writer业务范围：src/agent_guard/execution/original_material.py；必要时receipt_publication.py仅错误归一；tests/integration/test_receipt_publication.py、tests/unit/test_receipt_publication.py及tests/integration/test_receipt_worker_process.py增加真实回归。可在已有README/docs/security-model/docs/acceptance/docs/oauth接口及tasks/A2-report同步本段事实。拟新增纯文档范围：docs/crypto-profile-v1.md历史状态段；src/agent_guard/execution/__init__.py模块docstring；.github/CODEOWNERS仅旧管理员例外注释（精确 * @Qdcchh 规则保持）。这三处须独立包审确认无行为/密码参数/保护变化。所有其他源文件/测试/SQL/依赖锁/旧workflow门只读；controller状态与正式报告仅主控写。

回归必须先保留新增严格断言在旧候选上的真实失败；覆 coherent quote/result价格、错误总额/溢出/数量关联/原cost currency/calls/quote identity 等契约既有义务，正常immutable guard正控、bad-baseline全部ag+DS行不新增变化、PENDING/null原ID/iat、恢复原材料后同op真实READY、合法零价/延期终局/撤销后历史发布仍合法、当前query/SDK既有行为、CLI不因坏首行饿死合法行。不得改旧assert、skip、期待码或生产环境开关。实际新增组合由实现者依据完整原合同确定，不为凑数镜像实现。

容量分列当前canonical producer上界58168与兼容有效原始JWS域；后者SDK上限16384，独立r1补证真实非canonical16KiB和16385。合法当前query/合法原始接受quote域按每项q*p<=MAX_SAFE→digits(q)+digits(p)<=17（零价也成立）推导保守64695，非真实合法最大值。独立包审须核实际全guard/caller，不承接结论。保实际4/12/16/17宽256SKU、原组件64KiB/JWS16KiB、公开65536/65537真实拒绝与proof回滚、outer589964及1MiB/+1 codec/非法组件原点。

## 整合、完整自查与交回

sole worker停写后重新绑定原119项/112运行义务、41nodes/88atoms、全部原must_assert；source和自己fresh构建非editablewheel实际LinuxPy3.11/PG16/SM2/SM3/TLS普通/全PG/完整继承回归、独立DS、10轮全future与全状态oracle、真实core/CLI两PID故障、联合HTTPS、README全部字面流程、锁安装/14SQL/环境与父子进程provenance、ruff/format/源码wheel文档同版均完整执行。已有finite temp目录、低权限role/membership与真实premint适配可按原条件新owner复用设计，保存本轮实际原件，不能承接旧PASS。收集数按实际节点，不硬编码旧2799/1169。一般无理由不重复额外未受影响组，但本轮整体自查必需。

只用全新自有fullID+双labels、绝对ignored evidence、独占DB/schema/role/CA/端口/PID，ordinaryDSN清除，三foreign不连接修改；成功create/Mounts/匿名volume全映射，最后精确核归属清理所有自有资源及真实nativePID 0。全部失败/原件/脱敏双哈希、完整Markdown实施报告、119逐must_assert索引、wheel91生产条目与package provenance、source/doc/runtime/metadata差异、begin/end精确范围和STOP交回。只标FIXED_PENDING_FULL_REVIEW/READY_FOR_NEW_REVIEW，关闭及接受由全新astra/medium独立完整119/112 reviewer决定。不得Git/PR/CI/merge/A3。

## 实际只读依赖与受保护边界

必读完整根AGENTS/AGENT/HANDOFF、workflow README/current-policy/context/issues/implementation-contract/review-contract及tasks/workflow/runs/setup/codex-astra-sol-v1/workflow-contract.md；tasks/A2-execution-gateway.md、docs/oauth-oidc-sm2-mvp.md、docs/security-model.md、docs/acceptance.md；A22正式acceptance与review-r2；A23 task-v3/requirements-v3/node-bindings-v3/ownership-v3及全部capacity/quality/consumer/CI-runtime正式包审与实施报告、user-stop/user-resume、正式review-r1原文与本轮补正包审。报告中119逐must_assert原文及本轮新探针需完整读，不能只看P2摘要。

最低代码依赖：execution.service.verify_accept_facts、tools.catalog.snapshot_from_bytes、execution.store/fetch_events/fetch_operation、receipt_projection/project_receipt、original_material/scoped_trust_tx/validate_original_tx、receipt_publication/ReceiptVerifier/InternalPublisher、query/AuthorizedQuery、verified调用链、gateway endpoint/http_app/receipt_worker/config/factory、PermissionSnapshotProvider、原ledger/grant锁序和最终时刻、evidence.receipt SDK/crypto.sm原始JWS、SQL immutable guards。全部只读依赖被完整候选manifest按字节/mode覆盖；旧service.py和receipt_projection.py不在写范围。先真实核import graph，避免循环依赖。使用已读取操作/事件/permission snapshot原path；必须证path来自验证过的完整原chain或可信DB绑定，不能只让events自己证明自己。纯helper不增加当前授权/当前catalog依赖，也不允许PUBLIC读取把新proof登记commit后才校验。

精确sole worker允许13路径：
- src/agent_guard/execution/original_material.py
- src/agent_guard/execution/receipt_publication.py（仅确有必要的原异常归一/调用接线）
- tests/integration/test_receipt_publication.py
- tests/unit/test_receipt_publication.py
- tests/integration/test_receipt_worker_process.py
- README.md
- docs/security-model.md
- docs/acceptance.md
- docs/oauth-oidc-sm2-mvp.md
- tasks/A2-report.md
- docs/crypto-profile-v1.md（仅历史/现行状态与引用，不改规范密码/编码/签名参数）
- src/agent_guard/execution/__init__.py（仅模块docstring；原exports及其余AST保持）
- .github/CODEOWNERS（仅删除或修正管理员例外过时注释；现有有效规则逐字保持）

无SQL、依赖、workflow gate、CI step、branch protection、CODEOWNER规则、SDK限制或receipt claims改变；全共享接口保持现有冻结签名，容量新domain解释作补充不替代v3原must_assert或原helper/raw点。若出现确需扩大写范围/实质接口变化，先停写交主控，新包审后才实施；已有本次真人同段有限运行适配授权持续，不重复询问。

## Reviewer补正复验重点

本包审新astra/medium、PACKAGE_REVIEW、只读包与完整候选，不创建环境或跑产品suite；核119/112不缩减、真实helper/path依赖/锁序、13paths单writer、历史报价及签名兼容域、P3仅说明范围、真实运行资源/原件保存计划。包审不能关闭P2，也不把尚未实施的回归当PASS或因未实施自动BLOCKED。原READY包只保留历史，不视作新补正READY。正式包审完整报告原样由主控落盘，actual FINAL STOP/readback后sole worker方可启动。

实施交回后主控完整读回/核资源与nativeSTOP/13paths diff，重新冻结整个候选。全新astra/medium IMPLEMENTATION_ACCEPTANCE不能复用r1 Task；原119/112、41/88逐must_assert完整独立source与noneditablewheel全部运行，r1新缺陷及所有失败/容量/原始签名兼容/新回归独立承接。只有无已知阻断且全部必需闭合才能ACCEPTED。不要把补正的局部绿/自查/包READY当完整验收。

正式否决原文：`tasks/workflow/runs/A2.3-receipts-20261004/review-r1.md`，SHA256 `2922e2aed6e19a4dfb47a98c9514e8d9941b1756869f12b0c1d05ae988eccbf0`；完整原始reviewer证据与逐must_assert绑定：`artifacts/workflow/A2.3-receipts-20261004/full-acceptance-reviewer-r1/`，原件只读。主控最终读回：`artifacts/workflow/A2.3-receipts-20261004/controller-resume-r1/full-review-final-readback-r1.json`。

本轮独占owner `a23-integrator-remediation-r2-20261005`，实施证据 `artifacts/workflow/A2.3-receipts-20261004/integrator-remediation-r2/`。包审owner `a23-remediation-package-r2-20261005`，证据 `artifacts/workflow/A2.3-receipts-20261004/remediation-package-reviewer-r2/`，只读不创建业务环境/children。完整包审候选清单由主控写毕后创建 `artifacts/workflow/A2.3-receipts-20261004/controller-resume-r1/remediation-package-freeze-r2.json`，不自引用。
