# COSM2 A3–A7 v1 独立包审

## 1. 结论与范围

**PACKAGE_READY**。review_kind 为 `PACKAGE_REVIEW`，日期 2026-10-17（Asia/Shanghai）。无包审阻断；项目仍 PARTIAL，未给 A3–A7 作 IMPLEMENTATION_ACCEPTANCE。

原始范围为《复赛冲刺材料-20261018/01-双域协同SM2实施规划-A与B分工.md》第0节、A3–A7及B7/第4节接口表；受审包 `tasks/workflow/runs/cosm2-a3-a7-20261017/package-v1.md`。依据主控传达的真人连续授权“直接继续A的内容吧，一直到全部完成为止”及“B没有开始”，允许完成独立工具、设计资产和有真实来源的现有结果整理，不接管 B、不伪造 B 行为、不把 PARTIAL 标为全部 A 完成。平台消息ID未提供，不编造授权记录。

本结论只评价方案可实施性。B1/B3/B7依赖缺失不阻止独立工作启动，但阻止相关行为通过及完整 A3–A7 接受。A1/A2前段接受保持，不重开旧长期 A3.3/A3.4，不增加40000等无关门槛。

## 2. 独立会话与冻结版本

- 新独立 reviewer：`/root/a3_a7_package_review`。请求配置 gpt-6.1-sol/high；后台 effective metadata UNKNOWN。
- 仓库：`/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`。
- 实际分支 `codex/cosm2-2p-A`；HEAD `6ab288c928f8b63778856d426e3bbbec9511144c`。
- 主控明确确认：自派审以来包、current-policy、相关契约和业务代码冻结，尚未派实施。审查未启动任何 writer。
- 主控基线：`artifacts/cosm2-a3-a7-20261017/controller/baseline-status.txt`、`baseline.patch`；本轮独立 status/diff/staged 另保存在本报告同目录。继承 dirty/untracked 均保留；不能以 HEAD 代表当前工作树。
- 指纹清单：同目录 `candidate-sha256.json`，覆盖23个原始要求、包/契约、基线、实际调用方/测试/runner文件。清单 SHA-256：`fa4e98636a7637fdd88446876de2104f8d2f306145058ef7cbde236b8d88e65c`。各关键文档内容哈希均可逐项查看，未用提交号替代 dirty 内容。
- `snapshot.json`记录时间、分支、HEAD及缺失依赖；报告写完后独立再核对所有清单和Git状态。快照排除仅本轮自有报告/指纹证据目录（Git忽略的artifacts）；没有排除任何受审代码或需求。

## 3. 实际静态检查

直接读取 AGENTS/AGENT、现行 policy、review-contract、包全文、原规划全文（含第0节、A3–A7、B1/B3/B7及接口表）、A1/A2接受记录；检查 README、安全/接口/验收文档相关边界、实际 Git 状态与 diff。

核对实际 `tools/teacher_demo_server.py` 的 `safe_path/read`、threshold/x402结果白名单清洗及固定POST控制路由；`web/teacher-demo/app.js` 的 FIXED_DEMOS、fixedBlock、renderProof；当前 cosign 仍明确示意。现有结果解析器会用读取时刻补 completed_at，COSM2 新解析必须按包保存 B7 原始 completed_at，不能复制这一做法伪造来源时间。现有 threshold 的 resources_remaining 为列表而 B7明确为整数，新读取端应遵守 B7，不能照搬列表转换。

核对参考实现 Party1/Party2、digest_e、verify及math；`src/agent_guard/crypto/sm.py` 的成熟铜锁签验/编码；`tests/fixtures/threshold.py` 的真实 Rust sign-quorum驱动；threshold runner Dockerfile及前端现有事件来源/CSP/拒绝位置断言。B生产模块尚不存在，不以参考库充当它。

## 4. 完整本段矩阵（均为计划审查，非行为PASS）

| ID／原要求 | 方案、所有权与关键断言 | 验证计划与状态 |
|---|---|---|
| 第0节／统一安全边界 | 不动001–009及V1–V3字节/GM语义；不实现B；参考曲线仅测试；不输出份额、nonce标量、token或私钥；半诚实、同主机、非常数时间如实披露 | 计划diff/来源/去敏静态核查；包符合，行为未执行 |
| A3-01／A3三项交叉核对 | measure独占fixture与crosscheck；参考公式不改；固定d1/d2公钥逐坐标；参考→铜锁、B→参考双向；20随机消息e一致 | 新crosscheck真实调用B，缺B明确错误而非skip/参考替代。计划完整，B1缺失 |
| A4-01／A4全部测量 | measure独占bench；runner固定环境/镜像/CPU/Python/tongsuopy；10预热100样本；三轮、总计、含DB round2、单SM2签/验、真实FROST含启动、B7真实e2e；CSV全样本及n/median/p95/min/max | 统计/采样/缺依赖负例；n0/null/status/reason、完整模式非零。计划完整，共签/DB/e2e待依赖 |
| A4-02／A4性能图 | measure独占plot；矢量fig-latency.pdf，中位/p95、单位、n、环境与缺测注释；不混机器不删异常值 | 坏输入/统计边界测试与PDF视觉核对；可先测单SM2/FROST，部分图须醒目标未覆盖。未执行 |
| A5-01／A5真实结果展示 | ui独占三前端文件及server；FIXED_DEMOS cosign/cosm2-run和六例译名，run_id/原完成时间/来源，三轮耗时“单次运行，非统计结果” | Node/页面及六例坏result/误来源探针；无结果保持示意，summary不能生成live帧。计划完整，B7缺失 |
| A5-02／B7读取与控制边界 | 只读固定artifacts根真实result，严格白名单去敏，无任意路径/份额读取；无B后端时禁用动作，不增加假运行接口 | server边界/缺失/异常/跨run路径等负例；公网只读、原Origin/token/CSP保护保持。计划完整，真实集成待B7 |
| A6-01／A6系统与协议图 | figures独占新增生成器及新图/来源；系统含用户/三代理/AS/P2/网关/P1/账本/下游证据、两个信任域、代理无份额；协议三轮、P2独立链/撤销/预算、标准SM2验签 | reportlab可复现矢量两图，中文统一字体配色；标设计/未集成；生成前技能流程，Poppler逐页视觉核查。计划完整 |
| A6-02／A6七攻击×四拒绝位置 | 七攻击及AS/授权域/网关验签/接受事务全部保留；格子必须真实证据拒绝码；已有FROST/安全场景单列来源，不冒COSM2 | 输入来源/缺证据测试及图核查；COSM2单域/撤销缺失明确未测；合法部分矩阵可导出，否则只交生成器/待补。计划完整 |
| A7-01／A7截图录屏 | 主控唯一服务/截图/录屏；总览、1/3/6、共签示意/真实、真实记录页原图无标注；3分钟可见run_id/日期/来源 | Playwright实页与视频检查；共签真实截图/现场视频待B7；现有真实记录导览单列，不冒共签视频完成。计划完整 |
| A7-02／A7交C及接口表 | 本地C交付目录和图/截图/summary/raw→命令或run_id映射，SHA、日期/环境、状态/局限/缺失及续跑命令；不擅发消息 | 交付索引逐文件读回/哈希；B未闭合不可全部A完成。计划完整 |
| V-01／工程、回归与验收 | 纯逻辑/严格输入/误来源/坏result/统计测试；保现有断言；Node/pytest/ruff/diff；不随意改锁；自查STOP、完整候选冻结后fresh high完整独验 | 计划新逻辑与相关现有套件，独立实跑只在实施验收；A1/A2既有基线16ruff问题/3format文件须分清继承与新增。未执行 |

## 5. 所有权、安全与专项

measure、ui、figures三组核心文件边界清晰，共享接口沿用冻结B7；主控唯一整合和HTTP/A7资源管理，STOP后冻结审查。调度每个worker前，主控应把“必要新增专用测试”“论文figures新图/来源”展开成实际文件清单，尤其fig-latency最终由measure产出、figures不覆盖。该执行细化不构成当前方案阻断。

B7原契约只有三轮timing_ms，没有网关e2e字段。因此当前e2e只能未测n=0/null/reason；三轮相加不是网关完整受理时延。今后若有独立真实e2e证据须记录对应命令/样本边界，不能擅改B接口补造字段。本要求与包“缺依赖未测”一致，主控已明确同意。

读取端的“严格”应落实：整数排除bool，时间/时延有限非负，拒绝重复键及不明安全字段、缺/重/未知六用例与不一致passed汇总；run_id与目录相符；保留authz拒绝位置；不把本地可写JSON等同独立密码学证明。现有safe_path的限制和公网只读须保留。这些是包已有严格输入/来源/去敏目标的具体检查点，不是新增B义务。

旧长期A3事务/恢复/40000不属本次A3编号，不挪用其矩阵；也不修改旧迁移、协议、账本、授权、份额及旧FROST/x402生产实现。

## 6. 本轮独立执行

仅执行只读文件/Git检查、Python标准库依赖存在性和SHA快照、报告写入及读回；未执行未实现行为测试，未创建业务资源，未运行性能测量或签名业务。不把计划、历史计数或静态核对称PASS。

## 7. 既有证据与待运行项

A1/A2 acceptance记录已直接读取：OpenSSL参考向量和示意前端已接受，B1公开向量未到；此轮未重跑其30探针/浏览器，也未把该计数当本轮证据。缺失依赖经本轮文件存在性核对：`src/agent_guard/cosign/`、`tests/cosm2-public-vector.json`、`tools/cosm2_gateway_demo.py`、`artifacts/cosm2-gateway-demo-live/` 均不存在。B1交叉测试、共签/谓词时延、B7集成、真实共签矩阵及现场媒体均NOT_RUN/待B。完整A3–A7接受须这些条件真正闭合。

## 8. 缺陷与问题闭环

无确认的包审阻断，无伪造issue。上述e2e字段和文件枚举是实施约束/接口事实；不要求当前包在尚未实施时已有运行通过。若后续改B7契约、扩大生产范围或改变安全/验收语义，应重新冻结相应包并fresh审查。

## 9. 资源与结束核对

本轮仅写 `artifacts/cosm2-a3-a7-20261017/package-review/` 自有报告与指纹/只读快照。未调用其他agent，未开服务、数据库、容器、浏览器或业务子进程；未连接任何共享库，未清理外部资源，未Git发布或改身份。结束清单核验结果见 `end-check.json`；受审23文件与Git状态必须和本轮快照一致，否则本结论失效。

## 10. 交主控动作与STOP

主控读回本报告、核对指纹后可按既有真人连续授权调度独立工作；必须按矩阵保留真实待B项，完成自查STOP后再fresh实施验收。可分别接受工具/设计资产，但此包审不能接受全A或项目完成。Reviewer现在 **STOP**。
