# 独立小型 CI 审查：A2.2 timeout adjustment／r1

## 1. 分段结论与范围

**PACKAGE_REVIEW：PACKAGE_READY。** 本轮任务包对已接受 A2.2 的远端 CI 实际超时作最小时间配置修补，范围、依据、授权、冻结及验证计划完整，无已确认包审阻断项。

**CI_ONLY_IMPLEMENTATION_STATIC_REVIEW：CI_ONLY_CHANGE_REVIEWED。** 仅审查冻结的一行 `jobs.checks.timeout-minutes: 25 → 45`；实际字节、全部 tracked 路径、模式、Git 状态及 YAML/步骤核对通过，无已确认静态实施阻断项。

本轮不是完整产品 IMPLEMENTATION_ACCEPTANCE，也不新增 A2.2/A2.3/full A2 的 ACCEPTED 结论。既有 A2.2 ACCEPTED 仅按原报告和接受记录保留；项目整体 PARTIAL。新精确提交 SHA 的完整远端 required `checks` 为 **PENDING**。当前原 SHA 的远端结果仍 CANCELLED。管理员审核例外不继承，不对合并作额外豁免。

## 2. 会话、授权与版本绑定

| 项目 | 独立核对结果 |
| --- | --- |
| Reviewer | `/root/a22_ci_timeout_review_r1`；任务声明请求 gpt-6.1-sol/xhigh；工具未提供有效 backend/model/effort 元数据，记 UNKNOWN |
| 时间 | 2026-10-05，Asia/Shanghai；原始 API/命令证据使用 UTC |
| 主仓库 | `/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`；A2.3 全候选冻结，不修改 |
| 受审候选 | `/tmp/agent-guard-a22-ci-timeout-20261005`；真实独立 Git worktree，detached HEAD |
| HEAD／接受比较基线 | `8e4e7a3eba6a3e3f0a6a3eb9c3745e2cf7f17d40`，首尾相同 |
| task.md SHA256 | `370ee09f1751ca976d399baa0603a994f94109c5aa19ffe0bb7fb3e15c20dc06` |
| candidate.json SHA256 | `0364d566e254edcecb238b62fe5dfff50a431262ac84c6181280d7f48f079f83` |
| candidate CI SHA256／模式 | `59bdca726234f47209ba239123c9a150513341ae0f18a9d23a733248733f24dd`／0644，首尾相同 |
| 原 CI SHA256 | `ad65b8a15833f49e9015efa2de2f703039664800a0710c216baadb5a22f858c2` |
| Git 状态 | 仅 ` M .github/workflows/ci.yml`；staged diff 空；untracked、删除、重命名均无；语义 index/HEAD/branch/diff 首尾相同 |
| 全候选指纹 | 287 路径；entries SHA256 `c6dd918646065e3e959ebfcbde7921d94862d8178769624823b80b3e697b7626` |
| 主仓库 A2.3 指纹 | 295 路径；entries SHA256 `177729d090cc5caa1edf2edb01482867d0274a83626df0beeebbc97bb7bc5449`；包括全部 bytes/modes/pathset/Git/HEAD，首尾零漂移 |
| 写入与排除 | 仅本 reviewer ignored 目录；所有受审文件只读。既有 ignored 证据作为来源逐文件单独哈希核对，不当产品路径排除 |

已读 AGENTS/AGENT、current-policy、review-contract、review 模板、A2.2 acceptance、review-r2 的接受范围/正式运行/历史失败/问题关闭/资源与停止边界，以及本 CI 包、诊断 report 与实际原件。当前扩展授权记录保存真人原话“等2.2你确保复核完成了没有任何问题了直接合并到main分支，无论你是否能真正合并到main，都继续直接把2.3也做了，并完整验收A2”；记录边界是修补/发布遵守实际 CI 与审核规则，未授新管理员例外。该原消息 ID 未提供，不补造。本轮遵循主控已核的真人授权记录和明确 CI 修补委派，不自行授予权限。

## 3. PACKAGE_REVIEW 独立检查

| 包义务 | 独立查证与判断 |
| --- | --- |
| 真实故障来源 | 本轮亲自以只读 gh 取 run/job、annotations、完整日志、PR7 与保护。run37231901625/job111523246660/PR7 均绑定 accepted `8e4e7a3…`。failure annotation 原文 `The job has exceeded the maximum execution time of 25m0s`；故障来源明确为 job timeout，不仅凭持续时间推测 |
| 执行事实 | job 20:23:27Z 开始；前置约42秒，20:24:09Z 开始 PG；普通步骤 SUCCESS，日志1022 passed in18.92s；PG collected1930，到20:48:34Z为79%，20:48:40Z取消。没有完整 PG pytest 汇总；不得将1930记为本次PASS |
| 45分钟预算 | 已接受本地完整 PG source/wheel 约1314.8/1315.3秒；远端在24分25秒仅到79%，且真实锁/跨秒/到期等待矩阵仍持续推进。45分钟增加20分钟（80%）硬上限，为较慢 runner 留余量，合理且可逆。百分比进度不等时，不能据79%精确外推完成时间；45分钟并非已实测成功保证，异常 job 最长占用时间增加是该配置的实际代价 |
| 验收标准保持 | 全部普通/B/真实PG套件、锁/期限负例及10轮多参数矩阵、锁定安装、pip check、lint/format、两次迁移均完整保留。不得靠删测试、缩短真实安全等待、skip、改断言或限制 collection 达成绿 |
| 必需检查／审核 | 本轮开始与结束 API 相同：required context=`checks`、app_id15368、strict=true；CODEOWNER 必需、批准数1、dismiss_stale_reviews=true；PR7 OPEN/REVIEW_REQUIRED/BLOCKED。未改 required checks、保护、CODEOWNERS、权限或审核要求 |
| 隔离与后续验证计划 | 主仓库 A2.3 保持295全冻结；仅隔离检出的单行配置可供主控准确 commit/publish PR7 原分支。新SHA完整远端 CI 需真实 SUCCESS，若45分钟仍超时据新真实证据再建修补；静态结果不代替 required check |

**PACKAGE_READY** 只评价上述小型 CI 包，不关闭新的产品问题，不改变 stage 状态，不授管理员例外。

## 4. CI_ONLY_IMPLEMENTATION_STATIC_REVIEW 独立检查

实际 `git ls-tree -rz 8e4…`、逐 blob 比较、全部287实际文件 SHA256 和模式、tracked/untracked pathset、staged/unstaged diff 与 Git 状态已核。286 个文件与 accepted tree 字节完全相同，唯一差异为 CI 第15行；全287文件模式与 Git tree 一致，差异文本也精确等于一次 `timeout-minutes: 25` 替换为45。

Ruby Psych3.1.0 AST 对旧/新 YAML 作语法及结构解析，保留 `on` 词法键；除 timeout 以外整棵结构完全相同。仍只有 checks job/name；push-main 与 pull_request 触发、ubuntu-latest、contents:read、PostgreSQL16、Python3.11、checkout@v4/setup-python@v5、环境与服务参数均一致。9步骤的顺序及每段命令 SHA 相同。没有 continue-on-error、新增条件、权限提升或 collection 缩减。

独立静态读实际 `tests/integration/conftest.py`：缺 TEST DSN、目标不安全或 PG 不可达时 fail，未默许跳过；读 `test_gateway_query.py` 的真实 AS window×positive×cross_second×10轮160 case、DB锁等待/到期/全账本与下游断言，保持原测试。本轮未做 collection 或执行行为测试。

## 5. 既有 A2.2 接受证据与产品绑定

正式 review-r2 SHA256 `b9ae21a2c6537d0097e6d9a4e2b4da701953a24c496396b0aa2f1e77728cee13`；acceptance SHA256 `feb1d594b4535730562cc2ea236798aa9a8c50dc9593bb5e08ba9bbee7dfce2d`。原完整285 freeze 到 accepted8e4 的差异恰为已记录13项收尾文档/control状态及2份新增正式报告，逐项 before/after SHA 匹配；其余272路径与原freeze相同。当前 candidate 相对8e4只改CI一行，产品/src/tests/SQL/fixtures/deps零漂移。

本轮验证 r2 full-raw-hash-index 全619原始文件 bytes/modes/SHA，0差异，索引SHA256 `965bc23885c6658e3230e997ade731eeea964439e5a4dbedc086c7c169fabc14`。同时核实际 authoritative source复制树358文件：285原freeze＋73 build/lib映射副本，全实际SHA正确；wheel复制树202文件全部与原freeze对应相同，其73源码经原87项（73源码＋14SQL）wheel绑定核候选逐SHA相同。此为既有接受证据来源与版本核对，不是再次独立产品验收。

诊断的10 manifest列出原件（含report）、16来源SHA均与实际吻合。诊断 report SHA `e1f94d1e981b39a2465e4aafedd0f0c5e7163823c60b6a2246fcf65a869d693b`；本轮另取的原生 annotations 与 run JSON 也与诊断原件同SHA。完整日志只保存脱敏副本；新原始瞬态日志SHA等于诊断原日志SHA，未输出凭据。

复制树中的 `product-manifest.json` 是早期随树保留的186项历史 manifest，存在历史业务和文档差异，不能当当前产品绑定依据。本轮明确将它标为历史来源，实际绑定使用原285完整freeze、authoritative copy-shas、87项wheel-source-sql-exact-binding和accepted Git tree；没有把历史manifest误记成当前全文件相同。

| 既有 authoritative 运行（本轮未重跑） | exit | cases/PASS | fail/error/skip | PG wall秒 |
| --- | --- | --- | --- | --- |
| source nonintegration | 0 | 1022 | 0/0/0 | — |
| wheel nonintegration | 0 | 1022 | 0/0/0 | — |
| source integration | 0 | 1930 | 0/0/0 | 1314.814246 |
| wheel integration | 0 | 1930 | 0/0/0 | 1315.326081 |

本轮直接解析这些真实 command/log/JUnit并核SHA，合计5904历史PASS；早期失败与中断仍在原索引保留，不代计正式PASS。既有95语义/88义务的完整产品接受来自原r2与主控记录，本轮未冒称重新执行其全部断言。

## 6. 本轮执行、未执行与缺陷

本轮实际运行的是只读 Git/gh、SHA与模式核验、YAML AST解析及既有XML读取；没有运行 pytest、collection、ruff、安装依赖或准备测试资源。最初宿主 Python 缺 PyYAML 导致自有验证脚本一次 ModuleNotFoundError/exit1，随后使用系统已有 Ruby Psych AST 完成同等静态核验，未安装依赖或改候选。该工具探测错误不属于产品失败。

仅 timeout 标量的小型可逆配置不需无意义重跑本地完整suite；此判断只适用于本包的 CI_ONLY 静态范围，不是对任何新产品 IMPLEMENTATION_ACCEPTANCE 的豁免。新SHA远端完整CI PENDING是发布必需尚未完成项；本轮没有触发CI、commit/push、创建/修改PR或合并。

无本轮已确认需 CHANGES_REQUESTED 的包或静态缺陷。不能保证后续远端无业务失败或45分钟足够；后续实际required check和审核条件必须满足。

## 7. 首尾完整性、资源与停写

候选287及主仓库295的完整 bytes/modes/pathset/Git semantic index/status/HEAD/branch/staged/unstaged diff首尾一致；来源清单1498文件结束逐bytes/modes/SHA重查，0漂移。开始/结束的PR7和保护API完全相同。只写本reviewer ignored目录；没有任何Git mutation，没有测试进程、业务/测试资源、容器/库/schema或子agent；不存在本轮资源清理目标或存活测试子进程。

本reviewer交付后停写。原生 COMPLETED/STOP 由父任务实际平台回调核定，不用文件声明替代回调。

## 8. 证据入口与交主控动作

主控可核本完整报告和来源清单后，只对冻结CI单行修补作准确commit并发布到PR7原分支；随后读取新精确SHA的完整远端 `checks` 实际结果。保持 A2.3 冻结，直到其自身审查流程允许写入。现有独立审核要求与管理员例外边界保持。

- [source-manifest.json](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/controller/ci-timeout-reviewer-r1/source-manifest.json) — SHA256 `4a0dc9dc2c18e7848e4705dadefacd00444472b9fe60f8e37360b242b87e01ec`
- [static-review-results.json](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/controller/ci-timeout-reviewer-r1/static-review-results.json) — SHA256 `a932a546560a2c2985bb676736348afd7d618c3c7c0c46914233d05cef9e7eb7`
- [all-tracked-source-comparison.json](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/controller/ci-timeout-reviewer-r1/all-tracked-source-comparison.json) — SHA256 `255af770b73febd1f8fd11ba7322c1b81fc69f9ca257ea3d93e58bfaa68a3d68`
- [existing-a22-raw-hash-readback.json](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/controller/ci-timeout-reviewer-r1/existing-a22-raw-hash-readback.json) — SHA256 `c1d10dcaa6110a8d0e7f6606b87d46f42850d58bf021b71bfbef2abff22c99cc`
- [start-freeze.json](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/controller/ci-timeout-reviewer-r1/start-freeze.json) — SHA256 `968f63d232d9095ab0074025e0bb8027652bf1b77f9b34ea6abac77ce340f28c`
- [end-freeze.json](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/controller/ci-timeout-reviewer-r1/end-freeze.json) — SHA256 `51b5b16a47e9bd807d7d40ab11c3ee6254e5adb3db7b96e5f15d9e9b524bc4ab`
- [end-integrity.json](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/controller/ci-timeout-reviewer-r1/end-integrity.json) — SHA256 `3ed6c273eeb108520448faf30c95d4579f809918897a8cefe44be904f257fa8f`
- [candidate-unstaged.diff](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/controller/ci-timeout-reviewer-r1/candidate-unstaged.diff) — SHA256 `7a6ac7972f10d717b53e48e099666e7984c40f42a390d5b152ba53e6e418528c`

- [task.md](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/controller/ci-timeout-adjustment-r1/task.md)
- [candidate.json](/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff/artifacts/workflow/A2.2-integration-20261004/controller/ci-timeout-adjustment-r1/candidate.json)
- [远端实际取消任务](https://github.com/Qdcchh/agent-guard/actions/runs/37231901625/job/111523246660)；[PR7](https://github.com/Qdcchh/agent-guard/pull/7)
