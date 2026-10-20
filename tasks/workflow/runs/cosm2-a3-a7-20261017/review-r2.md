# COSM2 A3–A7 · IMPLEMENTATION_ACCEPTANCE r2

## 1. 结论与范围

**ACCEPTED：仅接受当前冻结版本中可独立交付的 A 端工具、设计资产、已有来源媒体与新版 C 交接包。R1-01/P2 已独立复验关闭，无新增阻断。**

**完整 A3–A7 仍为 PARTIAL / B_DEPENDENCIES_MISSING，不接受全 A 完成。** B1/B3/B6/B7 缺失；三项真实交叉测试的既有结果仍是 **3 failed、0 skipped、exit 1**。共签三轮/总耗时、数据库谓词、网关 e2e 均未测，不能把 n=0/null 或参考实现写成通过。共签攻击实证、真实结果截图和三分钟共签现场视频仍待 B。

日期 2026-10-17，Asia/Shanghai；review_kind=`IMPLEMENTATION_ACCEPTANCE`。依据原规划第0/A3–A7/B7与接口表、本轮 package-v1 / PACKAGE_READY、r1完整审查及 remediation-r1。真人连续授权“直接继续A的内容吧，一直到全部完成为止”且“B没有开始”，由主控传达并保存在现行 policy/任务包；未提供平台消息ID，不编造。A1/A2前段接受维持。本轮不接管B、不恢复旧A3.3/A3.4长实验、不发布Git。

## 2. 独立会话、候选绑定与冻结

- Fresh reviewer：`/root/a3_a7_review_r2`；请求配置 `gpt-6.1-sol/high`，后台 effective metadata UNKNOWN；未调用子agent。
- 仓库：`/Users/qdcc/Documents/ChatGPT/密码竞赛/agent-guard-handoff`；分支 `codex/cosm2-2p-A`；HEAD `6ab288c928f8b63778856d426e3bbbec9511144c`。
- 主控明确全部源 writer/root STOP 后审查。独立开始/结束核验 `controller/candidate-r2-sha256.json`：**170/170文件一致、0缺失/不符**；清单 SHA-256 均为 `c01c641b410e8435d6c865ee2a68fa7a8bab49b46e6bc8546648b23ec8d50257`。证据为本轮 `start.json` / `end.json`。
- Git branch/HEAD/status、unstaged/staged stat 开始结束一致，完整差异保存在 `unstaged.patch` / `staged.patch`；不把 HEAD 或空 staged diff 作为 dirty 候选指纹。继承 dirty/untracked 保留。
- 独立与 r1 原116文件清单比较：**114同字节，仅helper/docs两项授权变化**。两份旧字节备份分别与r1 SHA吻合；原C包28文件、正式两轮数据、图、源截图/录屏保持。新增包/ZIP没有改写旧失败。
- 所有本轮写入只在 `artifacts/cosm2-a3-a7-20261017/review-r2/**`（Git忽略），包括隔离 REPO/fixtures、报告、探针、缓存与日志；未改受审代码、正式测试、原报告/图/媒体/数据。

下文证据简称均相对于上述 `review-r2/`；需主控原样保存报告时，证据根仍为该绝对仓库下的目录。

## 3. 实际静态查证

读取 AGENTS/AGENT、current-policy、review-contract适用规则与模板、本轮包审/实施r1/r2/补正/r1否决、原规划第0与A3–A7/B7/接口、A1/A2接受、handoff及README/安全/协议/验收适用内容。检查实际源码、调用链、测试断言、补正patch及旧文件备份。

重点核对：helper `validate_failed_history`（第34行起）独立校验run01身份/环境/全部raw与warmup/编号/错误类型/统计；`main`仍用plot.validate验证正式run02，历史日志JSON须匹配失败summary，全部源预检后新建目录，复制后同时复核源与副本SHA。historical目录六项均有FAILED/run_id/原路径/SHA与静态归因说明，不参与正式图。

同时检查bench异常保全与真实Rust边界、plot统计/坏输入拒绝、fixture原始AST、server固定根/64KiB/UUID/strict schema与safe_path、保存来源/时间、控制路由和前端禁用入口。保存summary始终标saved-result，右侧13步仍illustrative，无summary伪造逐帧事件；`DemoApp.start`与HTTP POST白名单没有cosm2执行分支。图生成器仅映射三格有固定SHA的FROST历史来源，COSM2全未测。capture工具只容许三条固定scenario replay，录屏说明为历史/示意导览。

## 4. 完整当段矩阵

每行同时保留“当前可独立实现”和“完整原要求”的状态；B行为不随工具接受转PASS。

| ID／原要求 | 实现、独立断言与证据类型 | 本轮独立交付结论 | 完整要求的真实状态 |
|---|---|---|---|
| A3-01 参考fixture与三项B交叉 | 本轮静态/`audit.json`：参考AST相等，固定d1/d2逐坐标、双向铜锁/参考签验、20随机消息e比较断言保留，无skip/参考回退。`reused-evidence.json`核对r1真实runner输出与SHA | 测试/adapter资产PASS | **FAIL/BLOCKED B1**：既有3 failed/0 skip/exit1，API待B确认，G1未过 |
| A4-01 固定环境/10预热100样本/全测量项/原始统计 | 本轮81套件含24工具测试；`audit.json`独立逐行全核两轮660条，分别重算所有metric的n/median/p95/min/max/attempt/failure。r1固定runner n3+预热1原语烟测仅“既有日志核对”，exit2/PARTIAL | 原语测量/统计/失败保全工具PASS | **PARTIAL**：共签四项、round2_db、gateway_e2e六项n0/null/NOT_MEASURED/reason；没有三轮相加假e2e |
| A4-02 性能矢量图/中位p95/环境与坏数据 | 本轮run02 validate成功，run01实际拒绝发布；完整raw统计与图source三SHA/figure SHA匹配。四图中latency重新渲染查看、单页0位图；显示单位、n100、10预热、ARM/amd64仿真与缺测 | 部分实测图/验证PASS | 共签性能未测，图题明确“部分实测：双域共签尚未测量” |
| A5-01 B7六例/来源/原time/run_id/单次耗时 | 本轮81套件含23解析测试；1366×768隔离REPO实跑无结果和固定saved-result fixture；六例、原1760000000、run_id、来源、非统计说明、13步与两卡各6字段均断言；`ui-probe.*`/`cards-probe.*` | 只读结果适配/示意PASS | **BLOCKED B7真实结果/现场**；fixture仅为解析显示测试，不是B运行 |
| A5-02 固定根读取/清洗/缺失禁用/无假后端 | 本轮root GET确认cosign=null/ready=false；隔离页面0 POST/0 pageerror/无横向溢出，按钮禁用。strict负例覆盖NaN/bool/额外secret/source-live/e2e；静态确认无cosm2 POST动作 | 当前缺失状态/读取控制边界PASS | **BLOCKED B7原生控制集成**；未伪造后端 |
| A6-01 系统/三轮设计图、中文、双域/P2/标准验签 | 本轮静态与Poppler四页查看；系统/协议单页0位图、中文可提取，双域逻辑边界、代理无份额、P2自算/链撤销预算、最终标准验签与设计/未集成声明清楚 | 设计资产PASS | 仅设计，半诚实/n2/同主机/非常数时间局限保留，B未实现 |
| A6-02 七攻击×四位置真实拒绝来源 | 本轮81套件含8坏来源/输入测试；重建source index与已有逐格相同，56格核对：FROST仅3 OBSERVED、COSM2 28 NOT_MEASURED；negative重新渲染查看 | 有来源的部分对照PASS | **BLOCKED B6/B7 COSM2七攻击实证**；单域签名/共签撤销等不填假码 |
| A7-01 无标注截图/3分钟现场录屏 | 原9图与两视频SHA核对；r1 capture实际9图/仅3 replay为“既有日志核对”。本轮ffprobe两种视频1366×768/185.36s，重新抽1/90/145/175秒帧查看示意及历史采购run_id；另查看原records-detail日期/来源 | 现有来源媒体/工具PASS | **PARTIAL**：视频为历史记录与示意导览，未重录；共签真实截图/三分钟现场仍待B7 |
| A7-02 C目录/全部raw-summary/来源命令/SHA/局限 | 本轮 `audit.py/json/txt`：32源/副本SHA全同，6历史FAILED项，32+manifest/说明=34；ZIP34项CRC及解压字节全同；隔离REPO独立重打34文件、manifest各源项相同。两轮完全分离，原26资产/旧包字节保持 | **PASS，R1-01关闭** | C包明确PARTIAL/complete=false/待B清单；不构成全A完成，未外发给C |
| V-01 strict/来源/统计/工程/冻结完整独验 | 本轮81 pytest+16补正、Node、9额外关键负例、局部10文件Ruff check/format与diff均通过；完整矩阵、开始结束SHA/Git检查齐全 | 当前局部检查PASS | 全仓Ruff仍继承16错误/3格式文件（本轮仅核旧日志）；B真实集成必跑未满足 |

## 5. 本轮实际执行与证据等级

本轮工具环境：Python **3.14.7**，pytest8.3.5、Ruff0.11.13、ReportLab4.4.4、matplotlib3.10.7、pypdf6.1.1，见 `environment.json`。不把宿主版本说成Python3.11；真实密码runner的Python3.11证据另列既有核对。

| 实际命令／自有探针 | 结果/退出码 | 证据、边界 |
|---|---|---|
| `/tmp/cosm2-a1-a2-tools-20261017/bin/python -m pytest --confcutdir=tests` 六套相关文件（完整argv在checks.json） | **81 passed，0 failed/error/skip，exit0，2.45s** | `pytest.txt/xml`；逻辑/server/来源范围，无共享DB |
| 同Python执行remediation-r1/test_handoff_remediation.py，自有basetemp/JUnit | **16 passed，0 failed/error/skip，exit0** | `remediation-tests.txt`/`remediation.xml`；重复/混run/NaN/错误状态类型/计数bool/缺失/符号链接/覆盖/穿越拒绝等 |
| `node tests/test_teacher_demo_frontend_logic.cjs` | passed/exit0 | `node.txt` |
| `PYTHONPATH=src:. .../python review-r2/audit.py` | exit0 | `audit.py/json/txt`；独立统计/32份复制/ZIP34/重打包/9关键负例；未用worker审计输出代替本轮执行 |
| `.../python review-r2/ui-probe.py`，`node review-r2/cards-probe.cjs` | 均exit0 | 隔离REPO+自有HTTP/浏览器，1366×768；两状态、13步、六例、两卡、禁用入口、来源；0业务POST/页面错误/溢出 |
| `.../python review-r2/media.py`：Poppler、pypdf、ffprobe、ffmpeg | exit0，四图/两视频/四抽帧 | `media.py/json`与render PNG/text、probe JSON、video PNG；逐页及帧实际查看。仅渲染/抽帧，无重绘/重录 |
| Ruff check / format --check --no-cache 10相关Python文件；`git diff --check` | 均exit0 | `ruff-check.txt`/`ruff-format.txt`/`diff-check.txt`；argv在checks.json |
| root服务GET `/api/state`、r1证据逐SHA核对 | exit0；缺B状态真实、64旧证据哈希一致 | `reused-evidence.json`；不调用现场业务 |

9个额外关键负例为：现有输出目录、失败日志run身份不符、正式run冒充历史、缺归因原件（均拒绝且后两种新输出不创建）；解析source=live、用例额外secret、契约外e2e、bool时间、NaN时延（均拒绝）。有效重打包在自有 `pack-fixture-repo/`，没有把输出放生产交付目录；结果fixture只在自有临时REPO，生产 `artifacts/cosm2-gateway-demo-live/` 仍不存在。

正式run02：300 raw+30 warmup，三项各100+10全OK，独立重算中位/p95：SM2签0.241729/0.255625ms，验签0.2381245/0.263834ms，FROST23.297625/25.866ms；全部min/max也相等，所有样本保留。run01：同样300+30，FROST100+10全部ERROR/AssertionError，n0/null/failures110；旧overall PARTIAL原字节保留，新包明确FAILED。错误归因仅为静态定位，原日志没有更细Rust错误码，不夸大。

ZIP SHA：`b5cea3dace5e1b516156ead6daf08afac172403edef51925a85bef5c190d00b7`；34文件CRC/全部字节与r2目录一致。正式图source仅run02，没有吸收run01样本。

## 6. 既有日志核对与未执行项

`reused-evidence.json`记录r1证据清单**64/64 SHA一致**；受影响源码均在r1未变114项中。r1 `crosscheck.txt/exit`记录固定runner **3 failed、0 skipped、exit1**；r1 `native-smoke.*`记录SM2签/验/真实Rust FROST各n3/预热1、整体PARTIAL/exit2。这些是**既有日志核对，本轮未重跑密码runner或100样本**。r1环境为Python3.11.17/tongsuopy1.0.1、固定镜像ID `sha256:997ccb375167a46fb019795a3a59da2d9bc59778b1027e8da85c4f603e8ec567`、Rust SHA `32282203d3fd11e39edf0547e297c6fc65e56fdfbb7585e156039da3b898903b`；ARM宿主/amd64 Docker仿真告警真实保留，不称CPU原生性能。

r1 capture smoke九图、原九媒体逐张视觉审查和完整原生行为记录、全仓Ruff16错误/3格式文件为既有核对；本轮对原件SHA、当前页面、PDF渲染和视频抽帧另有独立实证。没有宣称重录185秒、重新执行历史采购或真实FROST网关。原截图records-detail可见历史日期/来源，视频中历史采购 `372d14ad-6c78-49f5-b4a2-6234fcdf48bf` 与回放标签清楚。

本轮未执行真实COSM2/B集成、数据库谓词、网关e2e、COSM2七攻击、共签现场媒体；均因B缺失而 **NOT_RUN/BLOCKED**。不引入旧阶段PG/长实验/wheel/TLS/40000等不相关义务，也不声称这些范围已回归通过。A1参考公开向量OpenSSL接受仅属前段既有记录，B1公开向量仍不存在。

## 7. 缺陷闭环与剩余依赖

| Issue | 原阻断与补正位置 | 本轮复验 | 状态 |
|---|---|---|---|
| R1-01 / P2 | A7-02旧C包遗漏失败run01；helper第34/180/288行起增加独立历史验证、六项复制和FAILED manifest，handoff附命令与静态归因 | 32源/副本、历史六项与全660行统计、原始失败stdout/命令/归因、隔离重打包、ZIP34项CRC/字节、旧包/原图/媒体不变、16+9负例均有证据 | **CLOSED_REVIEWED**，仅关闭交接完整性缺陷 |

没有新增确认阻断，不因B尚未开始要求A伪造实现。全A仍必须保留以下真实解除条件：

- **B1** 核心/公开向量/最终API：三交叉真实通过及独立OpenSSL公开向量验证，G1才可闭合。
- **B3** 真数据库谓词与签名者：可定义三轮/总耗时及含DB round2边界，再以新run实际测量。
- **B4/B5/B6/B7** 共签网关、真实用例/拒绝位置/结果与运行命令：提供真正网关e2e（B7原timing只有三轮，不能相加充当e2e）、COSM2七攻击证据。
- **B7** 原生控制及真实保存结果：完成真实结果接入、共签截图和三分钟现场录屏；所有新结果另起run，不改当前CSV和失败原件。

## 8. 资源、结束核验与交主控动作

本轮未启动Docker/PG/共享数据库或现场业务；没有操作外部容器、份额或密钥，没有commit/push/PR/改Git配置、没有消息发给C。自有隔离fixture服务通过finally shutdown/server_close/thread join结束；Playwright浏览器finally关闭。root原HTTP仅GET/页面浏览，由root负责最终关闭，reviewer未关闭或改它。自有文件证据保留，未清理其他人资源。

结束170文件/清单SHA/Git状态与开始一致，详见 `end.json`。源候选不受审查写入影响。

主控可在读回本完整报告并抽查原始证据后，将**独立工具/设计资产/现有媒体/C交接范围**记录ACCEPTED，关闭R1-01；保存r1 NOT_ACCEPTED与原旧包，保留全A PARTIAL和上述B依赖。该建议不授权接管B、Git发布或另开业务阶段。

Reviewer **STOP**。
