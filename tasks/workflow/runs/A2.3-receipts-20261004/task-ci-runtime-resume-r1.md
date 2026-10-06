# A2 完整矩阵 CI 时间预算提案 r1（正式待审；未实施）

review_kind PACKAGE_REVIEW；附单行候选CI_ONLY_IMPLEMENTATION_STATIC_REVIEW，后者不代替完整产品验收。作者主控gpt-6.1-sol/high、effective UNKNOWN；新独立reviewer须gpt-6.1-sol/xhigh/UNKNOWN。真人user-resume-20261005授权本次必要补正、PR和实际CI/审核满足后合并；同类有限运行适配持续批准。A3不实施，管理员例外不继承。

拟唯一配置变更 .github/workflows/ci.yml checks job timeout-minutes 45→75。原文件与提案字节指纹另存JSON。原45分钟依据接受A22的1930项，而当前完整A2实际收集2799项，含真实SM2/TLS/PG、500晚依赖deadline、10轮竞争及真实进程恢复。当前source/wheel完整2799正式已执行，实际2894.27/2906.01秒（48.24/48.43分钟），两run均exit1，2797PASS/2FAIL/0ERROR/0SKIP；两FAIL都是README/CI规定br_s1_untrusted测试role漏设，本轮自有环境已精确补正并source/wheel各两例复验exit0，原失败保留，不能冒称原整套exit0。此前core882历史约1339/1336秒仅用于调度参考，不计本轮通过。本机mixed-architecture且两套并行，不能直接外推Ubuntu CI；拟75分钟保留有限上限和运行余量，不保证远端已通过。这两个真实完整时长均超过当前45分钟；环境角色补正的实际flags/原run+correction闭合SHA已由主控读回，全部STOP仍须在正式派发前核实。

根/中/叶金额次数预算、TTL/撤销语义、测试矩阵、全部assert/轮数、锁等待、源码、SDK、SQL、依赖锁、CODEOWNERS、required checks、分支保护和CI触发/权限/服务/步骤顺序及命令均不变。不continue-on-error、不skip、不缩collection。实际较长job最长占用时间增加30分钟，是配置代价。

新独立reviewer只读核实际原文件、提案差异、完整真实耗时证据、原A22 timeout接受/实际CI及本次授权、工作流/review契约；核YAML有效且结构除timeout全等、全tests目录仍明确收集、新suite缺TESTDSN会fail。仅写本人ignored证据，无children/业务环境/Git修改。包审冻结提案/关联契约，所有candidate writer停止事实须先核实；本正式包及关联契约、全候选由主控冻结后才能派发。若PACKAGE_READY与CI_ONLY_CHANGE_REVIEWED无阻断，主控allSTOP后仅将已审字节应用至唯一配置路径并记录正式报告/本轮runtime overlay，再完整候选冻结交NEW完整IMPLEMENTATION_ACCEPTANCE。只有新精确HEAD真实CI SUCCESS和GitHub审核条件满足才能合并。

补正证据入口：integrator-resume-r1/denial-role-actual-permissions.json、source-formal-closure.json、wheel-formal-closure.json；主控已核controller-resume-r1/denial-role-correction-readback.json。此为已执行完整矩阵耗时的来源分类，不能替代NEW reviewer从起跑预置低权限role后的完整独立2799实跑。

## 正式冻结与单行候选

全部worker实际原生COMPLETED、所有自有test wrappers/PID结束、资源0已由主控核实。业务API/范围未变，119/112保持，原v3及消费者PACKAGE_READY仅沿用其业务包范围；本轮仅独立审核新的有限CI预算。主控待本轮reviewer原生STOP后才应用获审唯一单行字节，然后再全候选冻结交另一NEW完整产品验收reviewer。当前完整A2 NOT_ACCEPTED。

受审原文件SHA256 `59bdca726234f47209ba239123c9a150513341ae0f18a9d23a733248733f24dd`；拟单行候选 `artifacts/workflow/A2.3-receipts-20261004/controller-resume-r1/ci-proposed-75.yml`，SHA256 `f30187ff12c1bdfef273f58d7d096a801581eb2a8dc40758492815292309537c`。当前CI原文件仍45分钟未变。

reviewer证据独占 `artifacts/workflow/A2.3-receipts-20261004/ci-runtime-reviewer-r1/`；不启业务/测试资源，不运行产品suite、不spawn children，不改候选、提案/正式文件、Git或保护。读取本包、真实恢复授权、AGENTS/AGENT/HANDOFF、workflow/current-policy/context/issues/implementation-contract/review-contract/原workflow-contract、A2原task/全v3包/需求与当前整合报告/原A22 CI review及publication、actual原CI/ proposed YAML/TESTDSN缺失fail语义及所有相关raw耗时/精确两例环境补正。独立起止核全部候选pathset/bytes/modes/Git/HEAD/index及本包关联契约，精确YAML AST除了timeout45→75全部一致；本人只读取实时PR7/保护/CI上下文，不能把旧SUCCESS移为本轮CI。完整报告review.md用项目实际绝对链接，结论分PACKAGE_REVIEW和CI_ONLY_IMPLEMENTATION_STATIC_REVIEW两栏；remoteCI NOT_RUN但该小包静态审查可据充分证据PACKAGE_READY/CI_ONLY_CHANGE_REVIEWED，未保证未来75足够/完整A2通过/审核豁免。生成自己的run来源SHA/start-end/stop0并返回原生FINAL STOP。

完整候选冻结入口在 `artifacts/workflow/A2.3-receipts-20261004/controller-resume-r1/pre-ci-runtime-review-freeze-r1.json`（本正式包写毕后主控创建，避免自引用散列）。开始/结束须自己独立枚举核实，不以该清单为已验事实。
