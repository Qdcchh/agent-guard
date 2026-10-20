# 改名与对外表述修改指导（2026-10-19，给执行修改的开发代理）

## 0. 背景与目标

10 月 18 日汇报时，老师指出三个问题：
1. 名词太"AI 腔"，懂行的人看名字不知道每部分是干什么的；
2. 项目名 Agent Guard 和已有项目撞名（GitHub 上已有至少 9 个不相关的 AgentGuard），新名定为 **CoSeal**；
3. 没讲清和市面方案比好在哪。

本轮**只改对外显示的文字和表述**，不改任何功能、协议、签名语义和测试预期。名称一律以 [术语表](glossary.md) 为准；遇到表里没有的新词，按表头的定名原则自己取，并**把它补进术语表**，不要在各文件里各取各的名字。

开工前必读：`AGENT.md`、`docs/glossary.md`、`web/teacher-demo/README.md`。

## 1. 修改顺序与范围

按下面的顺序做，每做完一步就跑一次第 3 节对应的检查，不要攒到最后一起跑。

### 步骤 1：演示前端（最优先）

文件：`web/teacher-demo/index.html`、`app.js`，必要时改 `style.css`（只用来修复改名后出现的文字溢出）。

- `index.html`：`<title>`、`meta description`、左上角品牌（`.brand` 的 `span` 和 `small`）、顶栏五个章节按钮、来源标签"示意推演"。
- `app.js`：
  - `CHAPTERS`（约 689 行）：章节名和分组名按术语表 3.1 改。
  - `SCENES.*.short`：按术语表 3.2 改。
  - `SCENES.*.lanes[].name`：按 3.4 改。注意只改 `name`，**`k`、`id` 不动**。
  - `SCENES.*` 里的 `lede`、`stack`、`delta`、`honest`、`narrate` 返回的文字，以及所有 `label(...)` 里的中文。
  - `MODULES`（约 699 行）：每项第 1 个元素是标题，后面是说明文字，全部按术语表替换。**对象键（如 `'exec-domain'`）不改。**
  - `FIXED_DEMOS`（约 1754 行）里的 `title: '双域共签'` 改为 `title: '协同签名'`，同时把 `tests/test_teacher_demo_frontend_logic.cjs:119` 的断言字符串同步改成新标题。这是**唯一允许修改的测试行**。
  - `CATALOG_FALLBACK` 的中文标题，与页面标题保持一致。
- 改写 `honest`（"与原有做法相比 / 局限"）时：保留全部局限事实，但先写本页解决了什么，再写局限；删掉"本项目不声称首创"这类开头防守语句，改成"标准方向是 X，本项目在 X 之上做了 Y"。
- 名称变长时优先换更短的说法，不要靠缩小字号。
- 演示服务器发给页面的状态文字也要同步：`tools/teacher_demo_server.py` 约 436、549、606 行里的"双域共签""授权域""接受事务"。

替换后用下面的命令找残留（应只剩代码标识符、协议字段，或"技术细节"括注里的内容）：

```sh
grep -n -E "双域|授权域|执行域|执行代理|执行网关|基础防线|三道防线|核心机制|更多保障|运行证据|示意推演|持有者绑定|委托收窄|动态撤销|接受事务|可信|Agent Guard|COSM2|GM-MVP-1" web/teacher-demo/index.html web/teacher-demo/app.js
```

### 步骤 2：阶段汇报说明 docx

文件：`复赛冲刺材料-20261018/03-阶段汇报说明-20261018.docx`。

- 先备份到同目录 `03-阶段汇报说明-20261018.改名前备份.docx`；备份**不提交**。
- 本机没有 `python-docx`。在一次性虚拟环境里安装（`python3 -m venv /tmp/docx-venv && /tmp/docx-venv/bin/pip install python-docx`），逐个 run 替换文字，**保留原有样式和表格**。不要用转纯文本再重建的办法，那样会丢格式。
- 内容修改：
  - 全文按术语表替换。
  - 第 1 节"一句话记住这个项目"改用术语表第 2 节的一句话。
  - 第 4、5 节的页面名、章节名与新页面完全一致。
  - 第 7 节名词词典：删掉"AGPoP""授权域 / 执行域"词条，换成新名词；保留其余白话解释。
  - 第 8 节"创新点""和协同签名有什么不同"两问按术语表第 2 节卖点重写。
  - 新增一小节"和现有方案比"，放第 4 节的对比表。
- 文件名中的日期不改。

### 步骤 3：论文

文件：`复赛冲刺材料-20261018/论文模板/main.tex`（ctexart，XeLaTeX 编译）。

- 题目、摘要、关键词按术语表第 1 节改。
- 全文替换：授权域→授权侧签名方（下文可简称"授权侧"），执行域→网关侧签名方（简称"网关侧"），授权谓词→授权检查条件，授权状态承诺→撤销名单快照，接受事务→受理事务，智能体→AI 代理（首次出现写"AI 代理（智能体）"）。`\label{sec:predicate}` 等标签名**不改**，避免交叉引用失效。
- 第 2 节相关工作末尾补一张对比表（内容见第 4 节），每一行都要有 `\cite`；没有可靠来源的行宁可删掉。
- 引言的"贡献"段以术语表第 2 节的三个卖点为主线重写，保留原有的局限说明。
- 编译：在论文目录下运行 `latexmk -xelatex main.tex`。生成的 `main.aux`、`main.out`、`main.synctex.gz`、`main.log` 不提交。

### 步骤 4：README 首屏

文件：`README.md`。

- 标题改为 `# CoSeal（共印）`，下面一行写副标题，然后写术语表第 2 节的一句话和三个卖点。
- 接着放"如何打开演示"（原来那段本机演示说明，保留命令）。
- 现在开头那几段阶段状态（x402 X1–X8、A3.1–A3.4、PARTIAL、PR #6 等）整体移到 README 末尾新建的"开发状态（内部）"一节。**原文和链接一个字都不删**，只移动位置。
- 第 3 节架构图里的"统一执行网关"改为"工具调用网关"，其他技术内容不动。
- 在"文档"清单里加上 `docs/glossary.md`。

### 步骤 5：桌面启动器与现行文档

- `tools/install_desktop_server.py`：文件夹名和说明文字改为"CoSeal 演示服务器"。旧的"Agent Guard 服务器"文件夹**不要自动删除**，在 `docs/desktop-server.md` 里说明可以手动删除。
- `tools/desktop_server.py`：页面标题和"关闭"提示同步。
- `tools/x402_desktop.py:566`、`tools/cosm2_desktop.py` 中面向用户的中文提示：把"双域共签"改为"协同签名"。
- 现行文档同步改名：`web/teacher-demo/README.md`、`docs/desktop-server.md`、`docs/teacher-demo-20261015.md`、`docs/project-status-and-demo-coverage-20261015.md`。

### 不要动的东西

- **代码标识符和接口**：Python 包名 `agent_guard`、模块名、函数名、类名、对象键、事件类型、拒绝码、API 路径、HTTP 头（`AG-Proof`、`Authorization: AGPoP`）、`ag_cnf`、`sm2-2p`、`AG-COSM2-APPROVAL-1` 等协议标识、命令行参数。
- `src/` 下的 docstring 可以不改；**`src/agent_guard/demo/init.py` 里的证书 CN 绝对不改**（会影响证书夹具）。
- 迁移 `migrations/`、`tests/`（除步骤 1 那一行）、`tests/fixtures/`。
- 历史证据：`tasks/workflow/runs/**`、带日期的验收/交接记录（如 `docs/integration-status-20261016.md`、`docs/cosm2-*.md`、`docs/threshold-gateway-20261017.md`）、`product-manifest.json`、所有 `.zip` 和 `C交付-*` 目录、`复赛冲刺材料-20261018/01-双域协同SM2实施规划-A与B分工.md/.pdf`（原始规划按规定保持原样）。
- 技术规范文档 `docs/oauth-oidc-sm2-mvp.md`、`docs/security-model.md`、`docs/crypto-profile-v1.md` 只允许在开头加一句"对外名称见 glossary.md"，正文不改。

## 2. 硬约束（违反任何一条都要返工）

1. **只改文字，不改含义。** 不能让任何能力听起来比实际更强。例如"撤销名单快照"仍是"设计，未实现"；协同签名仍是"半诚实、n=2、同主机、Python 原型、非常数时间"。
2. **局限一条都不能删**，只能调整顺序和措辞。
3. 前端三种来源（现场运行 / 记录回放 / 动画示意）必须醒目区分，不能用计时器或硬编码伪造成功；红叉只挂在真实拒绝的节点上，旁边写实际拒绝码。
4. CSP 为 `default-src 'self'`：不写内联脚本或样式，不用 CDN 和外部字体；`web/teacher-demo/` 下不新增文件（服务器只按白名单提供三个文件）。
5. 1366×768 投屏下不允许任何文字重叠、截断或溢出。
6. 不展示完整令牌、私钥、签名份额、口令、数据库连接串。
7. 对比表只写"通常 / 默认做法"，具体到某个产品的说法必须附可查证的来源；不写"首创""国内首个""优于""绝对安全"；性能数字不能拿来和别家比。
8. 除步骤 1 那一行断言外，不改、不删、不跳过任何测试。
9. 不 commit、不 push、不开 PR，除非用户明确授权。不覆盖工作区里他人未提交的修改：开工前先 `git status`，`style.css`、汇报 docx 现在已有未提交改动，要在这些改动的基础上继续修改。
10. 术语表是唯一来源：自己新起的名字要先补进 `docs/glossary.md`，再在各处使用。

## 3. 完成后的检查

### 3.1 自动检查（全部通过才能交）

```sh
node --check web/teacher-demo/app.js
node tests/test_teacher_demo_frontend_logic.cjs
python -m pytest tests/test_teacher_demo_server.py tests/test_cosm2_live_ui.py tests/test_desktop_server.py tests/test_cosm2_desktop.py tests/test_x402_desktop.py -q
python -m ruff check .
python -m ruff format --check .
python -m pytest tests --ignore=tests/integration -q
```

### 3.2 残留词扫描（对外文件）

```sh
grep -n -E "Agent Guard|双域|授权域|执行域|可信执行|可信授权|授权即密钥|谓词|门控|授权状态承诺|基础防线|核心机制|更多保障|示意推演|持有者绑定|委托收窄|动态撤销|COSM2|GM-MVP-1|PARTIAL|赋能|闭环|全链路|首创|首个" \
  web/teacher-demo/index.html web/teacher-demo/app.js web/teacher-demo/README.md \
  复赛冲刺材料-20261018/论文模板/main.tex docs/desktop-server.md docs/teacher-demo-20261015.md
textutil -convert txt -stdout "复赛冲刺材料-20261018/03-阶段汇报说明-20261018.docx" | grep -n -E "Agent Guard|双域|授权域|执行域|AGPoP|可信执行|授权即密钥|基础防线|核心机制|运行证据|示意推演"
sed -n '1,40p' README.md | grep -n -E "Agent Guard|PARTIAL|A3\.|PACKAGE_REVIEW|COSM2"
```

允许的残留只有三类：协议字段或代码标识符（如 `cosm2-run`、`AG-Proof`）、引用的历史文件名或链接、README"开发状态（内部）"一节。其余命中都要改掉，并在报告里逐条说明保留的理由。

### 3.3 范围检查

```sh
git status --short
git diff --stat
git diff -- tests/
```

`git diff -- tests/` 只能出现 `test_teacher_demo_frontend_logic.cjs` 的那一行。`src/`、`migrations/`、`tasks/workflow/runs/`、`docs/cosm2-*.md` 不应有任何改动。

### 3.4 人工检查

1. 打开 Docker Desktop，运行 `python3 tools/teacher_demo_server.py`，打开 `http://127.0.0.1:8765/`。
2. 浏览器窗口设为 1366×768、缩放 100%，按数字键 1–5 逐章、`]` 逐页截图，每页都要看：
   - 顶栏、左栏、泳道名、过程图标签都没有重叠或截断；
   - 点开每个角色的说明卡，确认文字已经换成新名字；
   - 右上角来源标签显示"动画示意"。
3. 在"协同签名"页和"支付扩展"页各点一次"现场运行"，确认显示"全部符合预期"，并且运行中、运行完成的状态提示都已换成新名字。
4. 论文：`latexmk -xelatex main.tex` 编译无报错，`main.log` 里没有未定义引用（`grep -n "undefined" main.log` 无输出）；翻一遍 PDF，确认题目、对比表和交叉引用都正常。
5. docx：用 Word 或 Pages 打开，确认表格、加粗和编号都没丢；和备份文件对比页数，差异应在 ±1 页以内。

### 3.5 交付报告

报告里必须列出：
- 改了哪些文件，每个文件改了什么；
- 3.1 每条命令的实际输出结果，失败的要贴原文；
- 3.2 剩余的命中，以及每条保留的理由；
- 截图存放位置（放 `artifacts/`，不入库）；
- 新补进术语表的词；
- 没做完或不确定的地方。

## 4. 对比表（放进汇报说明和论文，使用前须逐行核实来源）

| 现有方案类型 | 通常做法 | 本项目的不同 |
|---|---|---|
| 模型护栏（如 Llama Guard、NeMo Guardrails、提示注入检测） | 识别并拦截恶意输入或输出，靠概率判断 | 不需要识别出攻击；代理被骗了也越不了权，越权请求会被确定性拒绝 |
| 通用 OAuth / API 网关（含 MCP 授权规范的常见实现） | 签发和校验令牌，通常是 bearer 令牌 | 令牌绑定持有者；多级委托强制降权；并行分支共享祖先预算；网关被攻破也签不出下单签名 |
| 代理支付协议（如 x402、AP2） | 证明付款正确、用户同意 | 在付款之前还要检查多级委托链和共享额度，付款批准本身需要协同签名 |
| 传统 SM2 协同签名产品（CA 厂商移动端协同签名） | 私钥不落地；服务端出份额前核对口令或设备 | 服务端出份额前核对的是委托链、撤销和预算，即"这一笔现在还有没有被授权" |

用来证明这张表的数据：从现有测试导出一张"攻击 × 方案"拦截矩阵。行是盗令牌、扩权、撤销后再用、并发超支、重放、网关被攻破；列是 bearer 令牌、OAuth+DPoP、单网关、本项目。只能填测试实际覆盖到的格子，没测过的写"未测"。这项工作可以单独做，不要求在本轮改名里完成。
