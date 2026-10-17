# 2026-10-16 本地合并与进度核对

2026-10-17 最新：合并后的门限采购批准和 x402 本地测试链闭环均已完成阶段独立验收；x402 139 个不同测试通过、最终页面 6/6。见[x402 接受记录](../tasks/workflow/runs/x402-gateway-20261017/acceptance.md)。下文合并表为 10 月 16 日历史状态，全项目仍 PARTIAL，生产支付与旧长实验未完成。

本轮合并 Claude 最新前端、桌面服务器和 B 的 `origin/codex/role-b-events-threshold-20261016`（`7e81acc`，包含 `2cdf0bc`）。基线为 A 分支 `5c03d47`。本地工作分支 `codex/integrate-a-b-20261016`，采用 squash 合并并恢复原工作区，尚未 commit/push；没有修改协议核心或恢复长实验。

合并前逐文件备份、SHA-256 清单和 patch 位于 `artifacts/merge-backups/20261016-221925/`，原 stash 仍保留。Claude 的 index.html/style.css 与备份逐字节一致；app.js 保留交互修改并作下述兼容修复。

## 合并修复

- 接受 B 的 `waiting` 状态，避免撤销序列在 seq=2 出现永久缺口。
- 盗令牌场景支持实际 `accept.rejected` 事件；委托读回不再误称整个用例没有签发子令牌。
- 当前浏览器保留每个场景最近收到的事件，避免启动下一场景后覆盖上一个场景的轨迹。
- 本机与公网共用严格校验的只读事件路由；公网仍没有控制 token、POST 权限、文件目录或管理页。
- 本机允许地址栏导航的 `Sec-Fetch-Site: none`；跨站读取本机控制会话仍拒绝。
- 门限面板更新为“独立原型已交付，未接入采购”，时序图仍明确标为设计示意。

## 目前进度

| 部分 | 已有成果 | 尚未完成 |
|---|---|---|
| A 前端 | 系统总览、七场景、可点击步骤条、真实记录、本机控制/公网只读 | 新增事件目前只覆盖 1/3/6；其余场景时序图仍示意 |
| B 真实事件 | 盗令牌、委托扩权、撤销的白名单观测、分页、因果关联、完成标识 | 按完成用例批次采集，不是每个内部步骤即时上报；旧历史无事件时不补造 |
| B 门限 | 独立 FROST-Ed25519 2-of-3 原型、分进程签名、策略拒绝与公开验签向量 | 非 SM2；未接网关/采购；同 OS 用户管理份额；防重放仍在内存，无认证审批渠道 |
| x402 | 适配设计文档 | 支付链路尚未实现 |
| 核心项目 | A2、A3.1、A3.2 的历史冻结版本已有接受记录 | 当前整合不继承为最终接受；A3.3/A3.4 最终联合验收和正式规模实验仍未完成，整体 PARTIAL |

> 2026-10-17 更新：x402 本机固定演示已实现（真实 HTTP 402 + EIP-3009 + 本地测试链结算；公网只读、无真实资产），见 [x402 设计文档的实现状态](x402-adapter-design-20261016.md)。上表其余内容保留 2026-10-16 合并当时记录。

当前服务重启不会恢复运行索引；刷新浏览器后只自动接当前 job 的事件，已完成的其他场景摘要仍可看。浏览器内缓存不是持久化历史回放库。

## 本轮验证

- `python -m pytest tests/test_teacher_demo_scenarios.py tests/test_teacher_demo_events.py tests/test_teacher_demo_server.py tests/test_desktop_server.py -q`：34 passed。
- `node tests/test_teacher_demo_frontend_logic.cjs`、JS 语法检查通过。
- `ruff check .`、`ruff format --check .`：通过，280 个 Python 文件格式符合。
- 门限 `cargo test --locked`：6 passed；`cargo fmt --check` 通过。既有和新生成公开向量均独立 OpenSSL 验签并拒绝篡改。
- 多进程门限脚本通过本地副本验证；仅把 GNU stat 换成 BSD stat 并指定 crate 路径，原 Linux 脚本不宣称在 macOS 原样通过。没有修改 Rust 源码。
- 公网 HTTPS：首页、session、state 为 200；session 不含控制 token；POST 为 403；管理页和 artifacts 为 404。本机代理出口可达，不代表所有评委网络可达。

实际运行与诊断记录位于 `artifacts/merge-validation-20261016/`，原件保留于各自 `artifacts/teacher-scenarios-live/<run_id>/`。不执行整个项目长测试，不将本轮局部联调称为正式联合验收。

## 打开和停止

桌面 `Agent Guard 服务器` 中原一键启动、关闭、查看地址入口仍可用。本机 `http://127.0.0.1:18765/`；公网地址从本机 `/server` 复制，每次启动可能变化。

### 本轮实际隔离运行

| 场景 | run_id | 真实事件数 | 结果 |
|---|---|---|---|
| stolen-token | `8b6868d7-d5e6-49f7-907f-42535c15b199` | 5 | 完整、原生退出 0、自有资源剩余 0 |
| delegation-scope | `a05a8544-a356-40bb-9336-ac99ca4e4ad0` | 11 | 完整、原生退出 0、自有资源剩余 0 |
| revocation | `4ee1803d-b709-453d-9ab5-7da652495d54` | 6 | 完整、原生退出 0、自有资源剩余 0 |

三个实际事件流均通过前端 EventStore 校验，无拒收、冲突和缺口。浏览器实测撤销真实来源标签与步骤条第 2 步锁等待交互正常；公网相同运行事件返回 200、6 条且 complete=true。
