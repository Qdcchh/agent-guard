# 演示前端说明（给接手的开发代理）

## 范围
- 只改本目录的 `index.html`、`style.css`、`app.js`。服务器 `tools/teacher_demo_server.py` 只按白名单提供这三个文件，新增文件不会被加载。
- 页面内容集中在 `app.js` 的 `SCENES`（各章节与时序图）、`MODULES`（角色说明卡）、`FIXED_DEMOS`（现场运行结果）。事件契约见 `docs/teacher-demo-events-v1.md`。

## 运行
1. 打开 Docker Desktop。
2. `python3 tools/teacher_demo_server.py`，打开 `http://127.0.0.1:8765/`。也可以用桌面"Agent Guard 服务器"启动，地址是 `127.0.0.1:18765`。
3. 本机页面可以点"现场运行"，公网页面只读。

## 硬约束（不可违反）
- CSP 为 `default-src 'self'`：不写内联脚本或样式，不用 CDN 和外部字体。
- 三种来源必须醒目区分：现场运行、记录回放、示意推演。不能用计时器或硬编码伪造成功。
- 红叉只能挂在真实拒绝的节点上，旁边写实际的拒绝码。
- 不展示完整令牌、私钥、签名份额、口令或数据库连接串。
- 局限照实写，例如"半诚实、n=2、同主机"，不能删。

## 视觉方向
- 浅色、简洁、几乎不用框，无框时序图（生命线）是页面主角。
- 页面上要写清用了什么协议、相对原协议改进了什么。
- 不允许任何文字或图形重叠，1366×768 投屏下也要清晰。

## 改完必须验证
```sh
node --check web/teacher-demo/app.js
node tests/test_teacher_demo_frontend_logic.cjs
python -m pytest tests/test_teacher_demo_server.py tests/test_cosm2_live_ui.py -q
```
最后在真实浏览器里按 1366×768 逐页截图检查，并在"双域共签""x402 支付"页各点一次"现场运行"。

## 当前待办
- x402 页面按钮已改为双域共签（sm2-2p），但还没有在页面上端到端跑过。
- "授权状态承诺"实现后，需要新增讲解页，说明签名携带状态纪元、下游离线验证新鲜度。
