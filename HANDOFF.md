agent-guard 当前技术状态与接手说明

出具日期：2026-10-03 UTC
核对范围：现有源码、工作区状态、保存的实施和独立复核记录；本次仅编写交接并只读核对，没有启动测试、修改产品代码、清理资源或重试被阻断的复核。
结论：BLOCKED / NOT_ACCEPTED。当前候选有完整 source 与非 editable wheel 的 2307 项通过记录，但已知阻塞缺陷仍在，独立复核缺少最终报告和完整验收矩阵，不能进入 A2.2 或宣称安全验收、生产就绪、比赛全部完成。

一 接手时最需要知道的事

1. 当前主要工作是 B-remediation-integration。S1 至 S4 的整合及五项后续 B/整合修复已经实施；无需把它们当成未做过重新开发。当前并非干净 Git 工作树，也不是一个已经发布的最终提交。
2. 三个继承 A 的修复仍未获额外批准：执行结果类型误分类、257 项输入在接受后被既有上限卡住、P13 并发测试 oracle 不充分。B 离线回执重复 grant 路径缺陷及一个新增测试分支遮蔽问题也未修。
3. 本轮独立复核和用户在 14:26 请求的同一复核续做都遭到平台风险阻断；后一次在 14:39:30 再次中断。没有有效最终 review.md、requirements-matrix.json 或最终 ACCEPTED 结论。已完成命令的结果仍可作为局部证据。
4. 旧的 11:44 交接写“历史回放和资源清理未验证”，这是当时事实。本次只读核对已找到 14:38 的终结与清理记录，详见第五节；不能继续把这些命令写成仍未完成，也不能据此声称当前整个机器绝对没有运行进程。
5. 用户在 14:45 另行授权把当前代码提交到 GitHub 的独立 handoff 分支供本地查看。最初因集成权限 403 被阻断，在用户补充授权后已复查可访问且有 admin 权限，正在准备发布。计划分支为 handoff/b-integration-20261003，但本文出具时远端分支与 commit 尚待验证，不能据此假定已发布。授权不包括 PR、merge、部署或新修复。
6. 计划 GitHub 交付为经过筛查的 186 项产品文件，覆盖源码、测试、SQL、锁文件和可公开文档，并附安全传输清单；完整云端证据和控制记录不包含在此上传范围。它与原始 206 项候选清单并非完全相同的文件集合。仓库以前发布的工作流记录也不能代表当前执行状态。实际包含/排除项及 commit 以发布完成后的验证记录为准。

二 精确版本和工作区

仓库目录：
/workspace/scratch/a7ac4a3b238b/restoration/restored/密码技术竞赛/agent-guard

仓库地址：
https://github.com/Qdcchh/agent-guard
此地址是仓库定位。交接发布完成前，不能把该仓库现有 main 当作当前工作候选。

Git 分支：main
Git HEAD 基线：153f14e9be180a1eb26b0f0e0898048d45170569
固定 B 来源提交：e521a461adb18d5fed89c8d1094647cb35eeff56
首次 S1 实施前产品指纹：c7717215a416e340bd9d74274324fcde49cd0816cdba1b367aa59379db74ac21
S4 v2 开始前的已停止候选：348739fae050449b0542ba349e56db167ff0ae7947b11ea440f78e30bae71cb1
当前被测工作候选指纹：5a8f5a3be1e9021a0907d5aec3c8c48a4999d7ba0527e307450829f53b01f540

注意：40 位 HEAD 是 Git commit；64 位当前候选是产品文件清单的 SHA-256 指纹，包含未提交产品文件，不是 commit SHA。只 checkout HEAD 得不到当前候选。

2026-10-03 14:28:36 的 binding-retry-start.json 确认候选指纹一致，清单有 206 项，306 个只读文件、533 项保护记录和 644 项 freeze 检查无差异。S4 v2 在 38 个允许路径中改变了 16 个；累计 S4 改变 25 个。此次文档核对再次逐项读取这 206 个产品文件，其文件 SHA-256 全部与 candidate-retry-start.json 相符；未重新计算或冒充完整验收门。

自 S1 实施前基线起的累计产品变化是 119 条：15 tracked、104 untracked、0 删除。精确逐路径 before/after hash、mode、state 在 interrupted-cumulative-source-delta.json。这个数量不包括所有工作流记录，也不把用户初始工作区已有未提交差异归为本次新工作。

累计变化中的 15 个 tracked 产品路径：
- .github/workflows/ci.yml
- README.md
- constraints.txt
- pyproject.toml
- src/agent_guard/__init__.py
- src/agent_guard/contracts/__init__.py
- src/agent_guard/contracts/execution.py
- src/agent_guard/contracts/ledger.py
- src/agent_guard/execution/service.py
- src/agent_guard/ledger/migrate.py
- src/agent_guard/ledger/service.py
- tasks/A2-report.md
- tests/fixtures/isolation.py
- tests/integration/conftest.py
- tests/integration/test_migrations.py

当前 git status --short 还显示 HANDOFF.md、tasks/workflow/issues.md、tasks/workflow/state.json 有未提交修改，共 18 个 tracked 修改，均未暂存。还存在未跟踪的 B 模块、迁移、锁文件、测试、文档及工作流目录。不要覆盖、清理或把这些全部误称为本轮新增。

interrupted-tracked-candidate-vs-HEAD.patch 只覆盖上述 15 个 tracked 路径相对 HEAD 的差异；它不含 104 个 untracked 产品路径，不是完整源码包，也不是相对用户初始工作区的纯新增补丁。

历史 A001–006、B004–009 SQL，原始验收与原交付仍保留；旧 tasks/A2-report.md 字节另有归档。历史 SQL、已应用迁移记录和旧验收不能被重写。原 Mac 外部符号链接没有用于云端执行。

三 已完成工作及责任归属

S1 核心整合
- 整合 A/B 迁移来源与共享契约。
- 接通真实授权链、权限快照、证据绑定和 A 接受/执行路径。
- 增加最终时刻状态检查及只读回执投影。

S2 HTTP 边界
- 修正 HTTP 边界拒绝分类，覆盖请求体、媒体类型、重复 header、认证、会话及角色边界。

S3 私有文件
- 使用绑定目录描述符的私有路径校验，非阻塞拒绝非普通文件；保留竞态和部分失败负例。

S4 交付整合
- 将目录描述符保护接入六次 CLI 私有写入。
- 完成真实 CA/主机名校验 HTTPS 和默认 DID 解析验证。
- 完善 CI、打包、手册、source/wheel 来源校验、真实 README 路径及互操作测试。
- 当前范围仍是进程内 B→A 整合。A2.2 公开调用及最终动态查询、A2.3 持续签发/导出、A3 锚定和性能阶段没有启动。

S4 v2 已实施的五项修复
- DID 配置快照：build_app 时保存独立不可变字节，防止调用方后续修改别名或嵌套配置改变已构建运行时。来源是固定 B 的行为。
- 离线回执时间一致性：验证一个共同可行的历史接受窗口，保留 proof 五秒偏差、所有 token/proof/key 约束；没有把 proof_iat 或迟延 receipt_iat 冒充实际 DB 接受时间，没有修改 wire 字段。来源是固定 B。
- CRLF 旧迁移兼容：保留历史归一化 checksum，另存原始字节摘要用于执行前检查；不改旧 registry/hash/applied_at。原始字节与归一化校验冲突是此次整合回归。
- 迁移 CLI：显式连接超时和固定脱敏错误输出。旧 CLI 风险在整合迁移入口中被保留，不能笼统归咎于 B 原作者。
- check/run 配置一致性：共享组件校验，预期配置错误安全归类，真正的 RuntimeError 不被吞掉。来源是 B 配置/工厂/CLI 组合不一致。

r2 的已保存 defects.json 已把上述五项记为 CLOSED_REVIEWED_R2，并有具体回归证据。这是单项关闭记录，不等于完整独立复核或阶段验收完成；实施报告中较早的 FIXED_PENDING_INDEPENDENT_REVIEW 描述应按时间理解。

另需保留的归因
- receipt_projection 的结果变体缺口和 lineage 的完成迁移下限问题，来自新增 S1 整合文件，固定 B 源中不存在这些文件。
- applied_versions 的 A-view 问题来自 A/B 命名空间兼容改造；原 B 独立数字 registry 行为本身有其上下文。
- 三个未批准的 A 缺陷继承自已接受 A2.1，相关缺陷逻辑/原测试字节未擅改。execution/service.py 在整合中存在其他已授权差异，并不等于其整个文件与 HEAD 一字不差；未改的是相应 A 缺陷逻辑。

四 测试事实及不能混同的失败

下述数量来自保存的 JUnit XML、同名 .exit/.log 和 argv；不同集合有重叠，不能相加成独立覆盖量。

同一当前候选的全套测试
- S4 v2 实施者 fresh source：2307 passed，0 failed/error/skipped，579.497 秒。
- S4 v2 实施者 fresh noneditable wheel：2307 passed，0 failed/error/skipped，550.727 秒。
- 独立 r2 source：2307 passed，0 failed/error/skipped，556.280 秒，exit 0。
- 独立 r2 wheel：2307 passed，0 failed/error/skipped，577.967 秒，exit 0。
- source/wheel 开始与结束清单绑定同一产品快照。wheel 在外部 harness 中运行，无 editable hook、无复制源码包或源码 shadow，父子进程安装来源有独立记录。

当前独立失败探针
- corrected-adversarial.xml：10 项，3 passed、7 failed、0 error/skipped。
- 7 个失败分别是四个 non-read/read-shaped 结果分类反例、一个 257 项反例、两个 P13 oracle 反例。
- receipt-duplicate-parent.xml 与 receipt-duplicate-pinned-full.xml：各有一个重复 grant 路径未拒绝的真实失败；一个针对当前候选，一个针对完整归档固定 B 来源。
- 没有通过 xfail、skip 或删除断言隐藏这些失败。全套 2307 通过不能覆盖这些独立负例的失败事实。

历史重放
- A1 五项历史检查通过，原始历史用例保留。
- 实施者 A2 历史集合：422 passed、2 failed；这不是当前独立续做集合的数量。
- 独立 r2 retry-1 A2：482 项，480 passed、2 failed、0 error/skipped，114.478 秒，exit 1；14:30:58 开始，14:32:53 结束。
- A2 两个失败为 test_r4_boundaries.py::test_outcome_typed_and_id_boundaries_keep_unknown[items-list-execute] 和 [items-list-query]。它们是已知旧断言与后来已接受的“结构相同 tuple→list quote 可接受”语义冲突；对应正控制仍通过。原断言未删除，不把结果写成全绿，也不把它们与七个当前 A 反例混为一谈。
- 独立 retry-1 原始 B：224 项，204 passed、20 failed、0 error/skipped，217.411 秒，exit 1；14:32:53 至 14:36:31。
- 独立 retry-1 B 等价适配副本：224 passed、0 failed/error/skipped，111.134 秒，exit 0；14:36:31 至 14:38:22。
- 原 B 的 20 个失败集中在旧可重复双参与者 barrier 与当前真实 principal lock/final recheck 的交互。适配副本保留原业务断言和十轮，并保存 PID/锁等待/重检查证据。原始失败必须保留，不能声称原始 B 全绿。最终整体验收仍需明确认可这种等价性。
- retry-1 final-witnesses-source：3 passed，2.231 秒，exit 0。
- retry-1 final-witnesses-wheel：3 passed，2.738 秒，exit 0。

实施与已有质量记录
- Ruff check、Ruff format --check 和 git diff --check 均有 exit 0 记录。
- README 的程序优先/CLI 优先、重复迁移、完整 bundle 和 B demo 在 source/wheel 中均实跑。
- 保存了 TLS、默认 HTTPS DID、SM2/SM3 双向 OpenSSL 互操作、真实角色切换后权限拒绝、进程死亡/恢复及十轮竞态证据。
- 当前普通 P13 测试通过不证明其异常 oracle 有效。最终 67 项要求及 60 项独立运行义务没有形成完整本轮终结矩阵；原 --require-accepted 未成功完成。

五 中断时间线与资源状态

11:44 的只读观察
- 第二轮独立复核被平台阻断；当时同一任务的仅清理请求也被阻断。
- 当时历史 A2 的 exit、wrapper 终结和最终清理尚未读到；postmaster.pid 存在不能证明进程仍活着，也不能证明已经清理。

14:26 之后的已授权同一复核续做
- 用户请求重试后，沿用同一复核者与同一候选，没有换路径规避限制。
- binding-retry-start.json 在 14:28:36 确认快照一致。
- resource-reconciliation.json 识别到上次中断遗留的专属 schema 和 downstream database；interrupted-owned-cleanup.json 记录只清理这些已确认自有遗留，remaining_schemas=[]。
- 14:38:29 前，A2、原始 B、等价 B、source/wheel witnesses 和 final-resources 已有终结记录。
- 14:39:30 再次遇到同类平台风险阻断，没有最终报告。

本次交接只读补核得到的状态
- retry-1/run-receipts.json 记录 final-resources 在 14:38:28.997423 开始、14:38:29.265200 结束，exit 0。
- retry-1/final-resources.log 中 schemas=[]；数据库只余两套基础库和维护/模板库；连接记录仅检查命令自身的 active 连接。
- retry-1/wrapper.exit=0，wrapper.log 明确记录 server stopped。
- retry-1/resource-wrapper.exit=0，其日志也有 server stopped。
- 因此“该次受控 wrapper 已终结，专属测试遗留清理与数据库停止有记录”已经可验证。旧交接中相应 UNVERIFIED 状态被这些较新记录补充。
- 本次没有重新做跨执行 PID namespace 的实时进程检查，不能扩大为“当前不存在任何进程/资源”。下一位在开展任何新运行前仍需用受支持方式确认其实际资源状态与归属，不能按其他 namespace 的 PID 盲目操作。

六 尚待处理的最小范围与批准边界

B 离线回执重复 grant 路径
- ID：BR-FINAL-RECEIPT-DUPLICATE，blocking。
- 三个不同 DID/holder 的完整路径可有 root→middle→root 重复 grant ID，在真实临时受信密钥签名与摘要全部重算后通过离线验证，违反每节点一次的协议约束。
- 这是受信签名者产生异常材料时的结构验证缺陷；不是签名伪造，也没有证明普通在线 AS/DB 能生成这种路径或发生在线预算绕过。正常 grant 主键/路径约束会阻止正常生成。
- 最小已定位产品文件：src/agent_guard/evidence/receipt.py；应配真实签名的重复路径负例并保留相邻负/正控制。

B 新增测试分支遮蔽
- ID：BR-FINAL-RECEIPT-TEST-BRANCH，非 blocking 的测试覆盖问题。
- future-token 分支被 startswith('future-') 先匹配，导致测试没有测到其名称所指条件。独立真实未来 token 探针能正确拒绝；不能据此另称实现存在新漏洞。
- 两项 B 修复的 planning-r3 仅是草稿与 14 个拟议用例，尚无正式 plan/freeze/dispatch，不可直接按草稿开工。

三个等待额外用户批准的继承 A 修复
1. A21-R1-OUTCOME，HIGH/blocking。
   最小源路径：src/agent_guard/execution/service.py。
   non-read 工具收到匹配 read 形状的假成功结果时会错误终结、消耗额度且妨碍后续正常恢复；需要在终局前校验结果变体与工具一致。
2. BR-FINAL-ITEM-LIMIT，HIGH/blocking。
   最小源路径：src/agent_guard/tools/params.py。
   256 项正控制通过，257 项在接受后被既有读取上限拒绝，留下预留和 review 状态；最小方向是在接受前拒绝超过 256 项。不能未经批准扩大所有上限或处理历史被困数据。
3. BR-FINAL-P13-ORACLE，MEDIUM/blocking。
   最小测试路径：tests/integration/test_execution_concurrency.py。
   意外 RuntimeError 或不相关 ExecutionError 没有令原并发 oracle 正确失败；需要精确收集所有 worker 结果和允许错误，保留合法 UNKNOWN/恢复语义及竞态要求。

批准和状态
- 当前 handoff 文档与 GitHub 当前代码独立分支上传已获请求；集成授权问题已解决，发布结果尚待核验。
- 三项 A 修复尚未获批。新 B 实施也须先有具体版本化方案、独立包审查及既定开工门，并受平台限制约束。
- 未开始 A2.2/A2.3/A3。工程实施与复核阶段没有本轮新 commit/push/PR/merge/部署；后续仅新增获准的独立 handoff 分支发布，本文出具时尚未确认其 commit/push 完成。
- 不能通过改写、换执行路径或替换复核者绕过平台拒绝。合法续做须先满足平台与实际权限条件，不能把交接文档当成新增授权。

七 环境定位与复现证据

已验证运行环境记录
- Python 3.11.16，PostgreSQL 16.15。
- 独立复核环境：/workspace/scratch/a7ac4a3b238b/br-environment/independent-review
- source Python：上述目录 /venv/bin/python。
- wheel Python：上述目录 /validation-r2/wheel-venv/bin/python。
- 外部 wheel harness：上述目录 /validation-r2/wheel-harness。
- 独立复核 PG owner 为 br_review，端口 55444；S4 实施者环境端口 55442，二者不能混用。
- 18 个精确版本保存在该环境 requirements.freeze.txt 与仓库锁文件；包括 psycopg/psycopg-binary 3.2.13、pytest 8.3.5、tongsuopy 1.0.1、ruff 0.11.13、uvicorn 0.35.0。完整依赖以原文件为准。
- 既有构建路径使用已审查 setuptools 80.9.0、uv 0.12.19 的 Linux wheel-only 构建；不是任意升级依赖或重建环境的批准。
- 原生 Tongsuo/BabaSSL 报告 8.3.2；完整现时安全回补与精确 native wheel 构建 commit 未验证。OpenSSL 兼容字符串不能证明其未修补，也不能证明维护已充分验证。

以下是已执行命令的审计入口，不是重试指令
- 独立 source 的精确 argv、cwd：artifacts/workflow/br-final-independent-review-r2/source-full.argv.json。
- 独立 wheel 的精确 argv、cwd：同目录 wheel-full.argv.json。
- 最新历史回放、witnesses 和资源检查的 argv、起止 UTC、exit：同目录 retry-1/run-receipts.json。
- source 命令入口是上述 source Python 的 -B -m pytest tests，并包含 no:cacheprovider、明确 basetemp、junitxml 和 junit_logging=all。
- wheel 从外部 harness 用 wheel Python 执行，不可把源码 PYTHONPATH 注入后仍称 wheel 验证。
- 这些绝对路径仅适用当前云端工作区；在本地不能原样假定存在。没有在本次交接时验证新的本地重现命令。

安全的只读版本核对命令
在前述仓库目录内运行 git rev-parse HEAD、git branch --show-current、git status --short 可核对基线与差异；这些命令本次实际执行并得到第二节结果。产品字节必须另与 candidate-retry-start.json 的 206 项清单逐项核对，不能只比 HEAD。

八 证据索引

以下路径均相对仓库根目录。保留原件，不要以新摘要覆盖原证据。

E01 旧中断交接与绑定索引
artifacts/workflow/br-cloud-controller/INTERRUPTED-HANDOFF-20261003.md
artifacts/workflow/br-cloud-controller/interrupted-handoff-index.json
该索引中的 15 个文件 SHA-256 本次全部复核一致；它只反映旧静态交接，未包含后来的 retry-1 记录。

E02 累计产品变化与 tracked 补丁
artifacts/workflow/br-cloud-controller/interrupted-cumulative-source-delta.json
artifacts/workflow/br-cloud-controller/interrupted-tracked-candidate-vs-HEAD.patch

E03 当前候选与续做绑定
artifacts/workflow/br-final-independent-review-r2/candidate-retry-start.json
artifacts/workflow/br-final-independent-review-r2/binding-retry-start.json
artifacts/workflow/br-final-independent-review-r2/files-retry-start.json

E04 最后完整实施报告与停止证据
tasks/workflow/runs/B-remediation-integration/workers/integrator-1/implementation-cloud-r2.md
artifacts/workflow/br-cloud-S4-integrate-integrator-1-r2/stopped-output.json
artifacts/workflow/br-cloud-S4-integrate-integrator-1-r2/evidence-index.json
artifacts/workflow/br-cloud-S4-integrate-integrator-1-r2/report-navigation-erratum.json
artifacts/workflow/br-cloud-controller/ledger-s4-r2-transition.json

E05 最后完整独立 NOT_ACCEPTED 结论
artifacts/workflow/br-final-independent-review-r1/review.md
artifacts/workflow/br-final-independent-review-r1/requirements-matrix.json
artifacts/workflow/br-final-independent-review-r1/defects.json

E06 当前独立 r2 的局部结果与仍缺终结
artifacts/workflow/br-final-independent-review-r2/defects.json
artifacts/workflow/br-final-independent-review-r2/source-full.xml
artifacts/workflow/br-final-independent-review-r2/wheel-full.xml
artifacts/workflow/br-final-independent-review-r2/corrected-adversarial.xml
artifacts/workflow/br-final-independent-review-r2/receipt-duplicate-parent.xml
artifacts/workflow/br-final-independent-review-r2/receipt-duplicate-pinned-full.xml
同目录的最终 review.md 与 requirements-matrix.json 本次核对仍不存在。

E07 最新续做完整命令结果和清理
artifacts/workflow/br-final-independent-review-r2/retry-1/run-receipts.json
artifacts/workflow/br-final-independent-review-r2/retry-1/historical-a2.xml
artifacts/workflow/br-final-independent-review-r2/retry-1/historical-b-raw.xml
artifacts/workflow/br-final-independent-review-r2/retry-1/historical-b-equivalent.xml
artifacts/workflow/br-final-independent-review-r2/retry-1/final-witnesses-source.xml
artifacts/workflow/br-final-independent-review-r2/retry-1/final-witnesses-wheel.xml
artifacts/workflow/br-final-independent-review-r2/retry-1/interrupted-owned-cleanup.json
artifacts/workflow/br-final-independent-review-r2/retry-1/final-resources.log
artifacts/workflow/br-final-independent-review-r2/retry-1/final-resources.exit
artifacts/workflow/br-final-independent-review-r2/retry-1/wrapper.log
artifacts/workflow/br-final-independent-review-r2/retry-1/wrapper.exit

E08 历史语义、归因与草案
tasks/workflow/runs/A2.1-core/review-r7.md
artifacts/workflow/br-cloud-controller/audit-origin-attribution.json
artifacts/workflow/br-final-independent-review-r2/protocol-audit/duplicate-origin.json
artifacts/workflow/br-cloud-S4-integrate-planning-r3/HOLD.md

最新关键证据 SHA-256
candidate-retry-start.json = 94b5f5c5a6916b1ca24f4afe6d4818cba2ed5e175920e3a108ae11a1aad1305c
binding-retry-start.json = a6b9ffeee6a320794aa7869caa59ad5f188bf7b18efbe94b1f1d567f5e38d16f
defects.json = 6a28dfd28e6a8a679ec25895e2a84b7efa7c975c25ea133766f733088ec6b999
retry-1/run-receipts.json = ee134604b54a176f4bdb21d4132ab1812092be469dda9838ffb3cc779a82e749
retry-1/historical-a2.xml = 966b64192717b188a0be163b7a0831501d6345defce67ea24d947e2ee66e2b92
retry-1/historical-b-raw.xml = c25a1f63704e82efe38e8d236f0ad98509809fbf7443697103e7ca5d509291b8
retry-1/historical-b-equivalent.xml = 4465ccb578f5f873cbb875875de9dce15279fed6631b3ea728153c8b8f3ac631
retry-1/interrupted-owned-cleanup.json = de74d359539d0265640e073998b24b67deb8db599af7f672b5f002ddf02987f6
retry-1/final-resources.log = ffaf874ade25e54c892863b2efa4f2031bb7507232e0c23a8d426cea993f8bcc
retry-1/wrapper.log = 13bd440e6160594f06212f8d5d87ef18019cefaeb175665d2175fe88386c3390
retry-1/wrapper.exit = 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
这些简名的根目录是 artifacts/workflow/br-final-independent-review-r2/。

九 下一位接手者检查单

[ ] 先确认实际拿到的源码快照、HEAD、分支、未提交差异和 206 项文件字节；不可用主分支或单一 patch 冒充当前候选。
[ ] 阅读 E04、E05、E06 与最新 E07；按证据时间更新理解，保留失败原件和历史归因，不重复已完成实施。
[ ] 通过受支持方式核实当前执行环境、进程和资源归属；将“既有停止日志”与“实时不存在进程”分开，不误操作其他 owner 或 namespace。
[ ] GitHub 集成授权已补齐；只按当前候选独立 handoff 分支范围发布。核实远端分支、commit 和传输清单后再交付链接；186 项筛查输出不包含完整云端证据，旧工作流不是当前状态。
[ ] 三项 A 修复先取得具体批准；两项 B 收尾先完成正式版本化方案和既定审查/开工门。不得直接执行未冻结草案。
[ ] 只有在平台允许、权限齐备且候选确定的情况下才能合法续做；补齐最终独立报告、67/60 要求矩阵、已知反例处理和验收门，不绕过平台限制。
[ ] A2.2/A2.3/A3、PR/merge/部署另行明确授权和阶段条件；不要因测试总数通过自行推进。

十 本交接附件的范围

此 TXT 仅是可直接复制、搜索的 UTF-8 状态说明与证据导航，不内嵌完整源码、104 个未跟踪产品文件、全部测试、数据库、wheel 或完整证据目录。把它交给另一台机器或另一个接手者，仍需要交付对应源码快照和必要证据文件；仅此文档、仅 HEAD 或仅 tracked patch 都不足以重建当前候选。

GitHub 交付应明确实际包含/排除内容，并核实敏感运行配置、测试临时密钥和环境数据未混入。当前筛查计划为 186 项产品文件及安全传输清单，完整云端证据/控制记录不上传；历史已发布工作流状态仍可能过时。请将发布完成后的实际分支和 commit 验证记录与本文配套使用。本文不承诺仅 clone 后即可无额外环境准备复现，也不提供平台限制规避或未经批准的重试步骤。


公开代码交接范围补充（2026-10-03）
本次仅传输当前产品代码、测试、SQL、配置、已筛查技术文档、此HANDOFF和产品SHA256清单。以下六个当前内部报告未获公开披露授权，完整排除：
tasks/A2-report.md
tasks/B-handoff.md
tasks/B-integration-proposal.md
tasks/B-interop.md
tasks/B-progress.md
tasks/B-remediation-report.md
已在GitHub存在的A2-report与workflow控制文件保留旧版本，不代表当前候选状态；新B报告未上传，文档中指向它们或云端artifacts的链接可能不可用。本次不是完整云端项目/证据归档。已通过哈希验证的186项产品文件与冻结候选相应文件字节一致；HANDOFF是用户要求的新交接文档，不属于原冻结快照。当前状态仍为NOT_ACCEPTED/PARTIAL，上传不代表验收。
