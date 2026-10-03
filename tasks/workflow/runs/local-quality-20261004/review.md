# B 整合分支本地质量复核（2026-10-04）

结论：**当前不可直接合并 main；保留候选分支补正，不执行回退。** 这是有明确范围的代码质量复核，不是补充契约定义的正式阶段验收。正式验收仍为 **BLOCKED / NOT_ACCEPTED**，完整项目仍为 **PARTIAL**。本轮没有修改产品源码、正式测试、SQL 或依赖，也没有关闭旧缺陷。

## 1. 版本、授权与资料范围

- 当前仓库：`/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`。父目录是另一个尚无提交的 Git 仓库，不能在那里执行本项目回退或合并。
- 候选分支：`handoff/b-integration-20261003`；HEAD：`2051b402c99a3d400d8f12749287075e23a9a521`。开始时工作树干净。
- 远端 main：`153f14e9be180a1eb26b0f0e0898048d45170569`，已通过 `git ls-remote origin refs/heads/main refs/heads/handoff/b-integration-20261003` 核实。候选是其直接后继提交，115 个路径变化、22655 行增加、304 行删除。
- 传输清单 `product-manifest.json` 的 186 项产品文件在文档修改前逐项 SHA-256 一致；它是原交付快照清单，不是本轮文档更新后的新清单。不得用它的 206 项云端候选指纹冒充当前 Git commit。
- 用户本轮要求：阅读 workflow/HANDOFF/Git/必要资料，复核分支质量及是否可合并，可酌情回退，清理无用文件并修改文档。未执行 commit、push、PR、merge、部署或后续阶段开发。
- 用户补充契约来自桌面，原文复制到 [workflow-contract.md](../setup/codex-astra-sol-v1/workflow-contract.md)，SHA-256 为 `c542d3f9cc80f51712538942480aff7c423fa2ecfea5598f68c9e32f36c75845`。历史文件中的授权、旧会话 ID、模型配置和暂停点不是本轮新授权。
- 已阅读当前 AGENT/AGENTS、README、HANDOFF、设计/安全/验收/密码配置、A1 最终验收、A2 完整任务、A2.1 acceptance、工作流契约/上下文/问题台账及相关实现、差异和测试。
- 原本地仓库 `/Users/qdcc/code/密码技术竞赛/agent-guard` 中找到了 B 整合 `task-v1.md`、`requirements-v1.json`、接口及迁移设计。它们标为 DRAFT/PLANNED，能帮助恢复 67 项要求、60 项独立运行义务，不能当作当前已生效包或云端 r2 终结证据；没有复制这些未公开内部报告入交付包。

## 2. 项目目的与阶段位置

最终目标是企业三代理协同采购的可验证授权与可信执行原型：用户登录和同意 → AS 统一签发 SM2 令牌 → 两级逐维收窄委托 → DID/企业登记绑定 → AGPoP 工具请求 → 共享祖先预算与幂等执行 → 故障恢复 → 回执和独立审计证据。比赛最终交付还包括可复现部署、攻击/恢复演示、实验数据和技术报告，目标日期为 2026-10-20。

| 阶段 | 当前准确位置 | 后续工作 |
| --- | --- | --- |
| A1 | 原子账本有历史验收 | 保留全部默认 API、预算/撤销/重放及迁移回归 |
| A2.1 | 执行/恢复核心有历史验收，但本轮确认继承缺陷仍在 | 结果变体、输入数量边界、P13 测试效力补正及完整复验 |
| B-remediation-integration | S1—S4 及五项后续修复已交付候选；当前未验收 | 关闭重复 grant 等阻断，补齐正式包、运行绑定、完整独立证据 |
| A2.2 | 当前只有进程内真实 B→A 接入及静态 query DTO | 公开调用 HTTP、最终动态权限查询及完整联合拒绝路径 |
| A2.3 | 只读回执投影/离线验证 SDK 存在，outbox 仍 PENDING | 持续签发发布、签名故障恢复及完整 A2 联合验收 |
| A3/最终交付 | 未完成 | 独立审计锚点、导出、三代理端到端演示、规模与对照实验、材料 |

A2.2/A2.3/A3 均没有因本轮复核获得开工或验收结论。

## 3. 阻断项和覆盖问题

| ID / 严重度 | 实际位置、触发和影响 | 本轮证据与最小修复方向 |
| --- | --- | --- |
| BR-FINAL-RECEIPT-DUPLICATE / 阻断 | `src/agent_guard/evidence/receipt.py:254–277`，相邻 validate_child 不能排除 root→middle→root 的非相邻重复 grant；ledger 也仅逐位置比较 | 静态确认缺少全路径唯一性。需增加唯一性拒绝和真实临时受信签名正负例。本轮未重新运行签名反例；不声称签名伪造或在线预算绕过 |
| A21-R1-OUTCOME / HIGH | `execution/service.py:630–638`，订单/通知收到同操作/工具的 read 形状结果，在其余绑定吻合时可错误返回 SETTLE；投影器后验拒绝不能撤销此前结算 | 纯函数探针中订单、通知两项实际失败，两个合法 read 控制通过。需终局前按工具约束结果变体，随后 PG 验证 execute/query、UNKNOWN 保留预算及合法恢复 |
| BR-FINAL-ITEM-LIMIT / HIGH | `tools/params.py:198–215` 不限 256 项，而 `tools/catalog.py:262` 和结果读取限定 256；请求接受域与持久材料读取域不一致 | 256 项解析/快照回读通过，257 项请求未拒绝，257 项快照读取拒绝。本轮未重演 DB 接受后隔离；需在接受前拒绝超限并证明零新增状态 |
| BR-FINAL-P13-ORACLE / MEDIUM、阻断 | `tests/integration/test_execution_concurrency.py:70–89,351–355`，worker RuntimeError 不进入结果集合，未校验完整结果数；允许一个错误但未限定错误码 | 静态确认。需收集全部 worker 结果/异常、限定合法争抢错误并设有界等待，注入 RuntimeError/无关 ExecutionError 必须令 oracle 失败 |
| BR-FINAL-RECEIPT-TEST-BRANCH / 覆盖缺口 | `tests/integration/test_verified_execution.py:698,706`，future-token 先命中 startswith("future-")，专用 token 分支不可达 | 静态确认；不能将其当未来 token 测试证据。修分支条件并核验负例实际改变 token，不据此宣称时间校验实现有漏洞 |
| LOCAL-DOC-LINK / 工程失败 | README 指向未交付的 `tasks/B-remediation-report.md` | 正式文档测试实际失败；本轮改为当前可用报告入口，保留旧内部材料未交付的说明 |

前三项 A 相关问题（OUTCOME、ITEM-LIMIT、P13-ORACLE）在 A2.1 基线已存在。相关 params/catalog/results/P13 文件与基线没有差异，execution.service 的本分支修改没有改变有缺陷的终局分支。因此回退到 `153f14e` 不能声称恢复到无已知缺陷的版本。原六份 A SQL 与基线逐字不变。

## 4. 本轮实际检查，不能和历史数字相加

在独占、标记 owner=`ag-local-quality-20261004` 的 Linux amd64 Python 容器中运行；源码只读挂载，未连接既有 PostgreSQL 或业务库。最终环境为 CPython 3.11.17、UID 501、独立 venv，按原锁安装依赖并非 editable 安装包；65 个安装后的 Python 源文件与仓库逐项哈希一致，`pip check` 通过。这不是仓库外全套 source/wheel 双验收。

| 检查 | 实际结果 / 证据 |
| --- | --- |
| 原锁依赖安装、包安装与 pip check | 成功，见 `install-venv.log`、`package-venv.log`、`pip-check-venv.log`、`installed-source-binding.json` |
| `python -m ruff check . --no-cache` | exit 0，`ruff.log` |
| `python -m ruff format --check . --no-cache` | exit 0，`format.log` |
| 文档修改前 `pytest tests --ignore=tests/integration -p no:cacheprovider` | **925 passed、1 failed、0 skipped**；失败为 README 链接，`nonintegration-venv.xml` |
| 本轮纯函数诊断 `pytest /evidence/test_boundary_probes.py` | **4 passed、3 failed、0 skipped**；两项错误结果 SETTLE、一项 257 数量漏拒绝，`boundary-probes.xml` |
| `workflow_gate.py verify ... --require-accepted`（只读历史门） | exit 1，`can_accept=false`；旧根目录、快照不同及原始证据缺失等，`historical-gate.json`；未修改旧状态/门脚本伪造通过 |
| 首尾源码/正式测试/SQL/依赖完整性 | 独立静态审计的 223 tracked 清单首尾一致；后续主控仅更新文档，新清单与差异另存 |

首次测试环境的两次诊断保留原日志：root/PYTHONPATH 运行 922 passed/4 failed，非 root 的 pip --target 运行 924 passed/2 failed。root 权限用例、缺 distribution metadata、--target 未落到 sys.prefix 的 SQL 数据目录属于本轮 harness 问题，不能报成产品新缺陷；正确 venv 下只剩文档链接失败。未删除这些失败记录或修改断言。

本轮没有执行 PostgreSQL 集成、真实进程恢复/并发/故障、完整 source/wheel、历史 A/B 探针、真实 HTTPS/OpenSSL 联合套件或远程 CI。HANDOFF 的 2307 项通过及旧失败探针数量仅为交接陈述，本地没有相应云端原始材料，不能写成本轮核验通过。

文档修正后的验证结果见本报告收尾记录及本轮证据索引。

## 5. 质量判断与正式验收缺口

新增代码有明确模块和信任边界，复用真实密码实现、保留旧 SQL、采用同事务证据绑定和最终时刻检查，配置 DID 快照也在工厂中复制为不可变字节；本轮基础检查支持这些实现具有继续补正的价值。上述正向事实不足以抵消错误结算、离线重复路径和测试效力缺陷。

辅助子审计只完成定点静态检查，未逐行覆盖约 2.3 万行新增实现；主控基础测试也不代替完整 67 项验收。不能将本报告称为全面安全审计、生产就绪或正式 ACCEPTED。

补充契约明确要求“缺失测试/资料/运行绑定时保持 NOT_ACCEPTED/BLOCKED”，且“当前尚无通过真实 Codex 回执验证的完整机器门移植”。当前没有核验其指定主控/worker/reviewer 有效模型档位和原生父子绑定，没有当前生效的完整包/冻结/验收门，也缺少云端 r2 的完整矩阵及原始失败/终结证据。收到补充契约前已启动的辅助审计不冒充符合其要求的新正式 reviewer。没有遇到本轮新的平台自动审批拒绝；旧 HANDOFF 的阻断也不因本次工具可运行而宣布解除。

67/60 项恢复目录见 [requirements-matrix.json](requirements-matrix.json)，逐项保留阻断、部分证据或未运行状态；这是恢复清单，不是有效验收矩阵或批准后的新阶段 state。

## 6. 处置与继续条件

保留候选，不删除分支、不重置到 main。阻断问题边界明确，尚无证据支持丢弃全部 B 工作；回退无法解决继承 A 缺陷。若以后运行过 bundle 数据库升级，源码 Git 回退也不等于可无损降级数据库。

正式继续前需要：取得当前阶段的最终任务包、完整失败与实跑证据、实际有效的运行绑定/验收适配；或由用户明确批准调整该工作流后重新审包。补正包应精确覆盖上述四类阻断和测试分支，经过新包审、实施、冻结、新独立全矩阵复验。任何实际合并仍在全部合并条件满足后处理。

用户随后明确要求删除不影响项目的过时/错误文档。本轮删除已由 Codex 补充契约替代、且不属于旧 state.contract_files 的 `tasks/workflow/runs/setup/20261001-setup.md`；历史包审中的该文件名保留为当时阅读清单，原件可由 Git `2051b40` 恢复。当前 HANDOFF、workflow README/context、A2-report 已直接改为准确短索引，删除旧启动命令和错误状态，不再只加提示后保留整段失效操作说明。正式任务、验收/失败报告、原始证据及原 state/门脚本保留。

同时只清理本仓库 `.DS_Store` 和本轮自建容器；SQL、锁文件、源码、正式测试不改。既有 `agent-guard-a2-pg` 与 verivote 容器不停止、不连接、不删除。

原始证据：仓库内 `artifacts/workflow/local-review-20261004/`（Git 忽略）。辅助报告原件为 `reviewer/review.md`；主控日志、JUnit、探针、绑定清单和清理记录在 `controller/`。没有原始材料的历史引用保留为缺口，不补造。

## 7. 收尾记录

- 文档修正后定向执行 `python -m pytest tests/test_docs.py -p no:cacheprovider`：**2 passed、0 failed/error/skipped**，exit 0，见 `controller/docs-final.xml`。源码和正式测试未改，未为文档修改重复运行整个非集成套件；不能把此结果写成全部项目测试通过。
- 12 份现行文档的本地 Markdown 链接核对无失效目标；`git diff --check` 通过。
- 删除 1 份过时 setup 文档、5 个本仓库 `.DS_Store`；本轮 3 个自建容器已核验 owner/ID 后清理，剩余自有容器为 0。原 3 个运行容器身份及运行状态保持不变，仅做清单核对，不宣称业务数据比较。
- 旧 state、门脚本、历史验收/失败报告、产品源码、SQL、正式测试、依赖锁保持原字节。文档清理后的差异和逐文件哈希见 `controller/final-integrity.json`；原始证据文件哈希索引见 `controller/evidence-index.json`。
- 本轮没有产品修补、commit、push、PR 或 merge。**合并结论仍为否；正式工作流验收未完成，下一步是解除资料/运行绑定缺口后按包完成补正和独立复验。**
