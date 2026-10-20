# Mac 一键演示服务器

2026-10-16：保留现有协议、场景和前端，增加桌面启动、关闭、地址查看。公网只读，本机控制真实任务。此改造不代表 部署演示与规模实验 完整接受，也没有补造逐条真实事件。

## 使用

当前机器桌面上的 `CoSeal 演示服务器` 文件夹包含：

- `启动服务器.command`：双击启动后台服务，打开本机状态页，并尝试打开 Docker Desktop。等 Docker 就绪后再启动真实任务。
- `查看服务器地址.command`：重新打开状态页，复制当次公网 HTTPS 地址。
- `关闭服务器.command`：关闭隧道及网页入口；已经启动的固定任务等待实际完成及原驱动清理。收尾期间重复启动不会创建新服务。

本机控制页是 `http://127.0.0.1:18765/`，状态页是 `/server`。不复用旧服务的 8765 端口，不停止旧服务或 Docker Desktop。关闭终端窗口不停止后台服务器。

状态页仅在客户端报告隧道注册成功后给出分享地址。该信号不能证明评委所在网络可达，分享前还应使用手机移动网络试开。临时地址每次启动可能变化；免费 Quick Tunnel 无可用性保证，适合短期演示。若需要固定地址及更可靠的接入，再单独配置正式隧道/域名或服务器。

运行期间保持联网、接电且不要合盖或手动休眠；`caffeinate -i` 只防止空闲自动休眠。网络切换可能引起隧道重连，进程退出时状态页提示失败，不伪装公网可用。

## 安装与依赖

当前安装针对 Apple Silicon macOS，宿主 Python 3.11+，运行代码仅用标准库。真实演示继续使用原 Docker 环境。重新生成桌面入口：

```bash
python3 tools/install_desktop_server.py
```

新增外部客户端 `cloudflared 2026.10.1`（Cloudflare 维护，Apache-2.0），用途为出站 HTTPS 隧道。官方发行包 URL、官方资产摘要和解包后的客户端摘要固定在 `tools/cloudflared-lock.json`；安装和启动都校验摘要，不自动更新。二进制放在 Git 忽略的 `artifacts/desktop-server/bin/`。

该固定版本申请 Quick Tunnel 的 HTTP transport 不读取系统代理。启动器提供一个随机路径、只接受一次固定 POST 的回环适配端口，将请求发送到固定的 `https://api.trycloudflare.com/tunnel`，使用 macOS 现有代理并保持 TLS 校验。临时隧道凭据仅通过本机内存传递，不写入展示数据。代理仅在已有系统配置下使用，不修改系统网络设置。

本机实测系统 DNS 无法解析隧道节点，因此启动器通过 Cloudflare 官方 HTTPS DNS 查询 `region1.v2.argotunnel.com`，仅接受该域名的全球 IPv4 地址，取两个节点传入固定版本的 `--edge` 参数。DoH 失败时回退客户端原解析，不修改系统 DNS、不固定过期 IP、不关闭 TLS/SNI 验证。`--edge` 和 `--quick-service` 属于该版本源码提供的隐藏选项，因此升级客户端必须重新核验，不能只改版本号。

## 访问与停止边界

- 本机控制监听、公共展示监听是不同端口，均只绑定 `127.0.0.1`；隧道仅连接公共端口，并明确设置该端口的 Host。
- 公共入口仅允许首页、脚本、样式、脱敏状态、校验过的运行事件分页和返回空 token 的会话响应。所有 POST 拒绝，不转发任意路径，不公开文件目录、原始日志、凭据或管理页面。
- 本机沿用原有 Host、Origin、请求 token 检查；不信任 `X-Forwarded-For` 来授予控制权限。
- 七类历史摘要在启动时按原验证逻辑读取；缺失或损坏就不展示。不把旧摘要还原成虚构事件。已有本机任务的结果会自动同步到公网。
- 两个网页监听器限制处理线程及请求超时，公共状态缓存 2 秒；并非经过大规模公网压力验证的托管平台。
- 控制接口为当前用户私有目录中的 Unix socket（目录 0700、socket 0600），使用启动锁和运行锁；不凭磁盘中的 PID 结束进程。
- 正常关闭停止新任务、撤下网页入口，仅终止持有实际子进程对象的隧道/防休眠进程；等待既有演示及其 owner 清理，不执行全局 Docker 清理。强制结束 Python、关机或断电不属于正常关闭保证。

## 排错与命令行

```bash
python3 tools/desktop_server.py start
python3 tools/desktop_server.py status
python3 tools/desktop_server.py stop
# 仅本机调试（先关闭已有服务）
python3 tools/desktop_server.py start --offline
```

日志位于 `artifacts/desktop-server/server.log` 和 `tunnel.log`，仅本机保存。不要向公网开放整个 artifacts。端口被其他进程占用时启动会失败并保留日志，不结束未知进程。更换仓库位置后重新运行安装入口。

局部检查命令：

```bash
python3 -m unittest tests.test_desktop_server tests.test_teacher_demo_server -q
node tests/test_teacher_demo_frontend_logic.cjs
```

本轮只验证服务生命周期、访问边界与既有前端逻辑；不恢复长实验，不替代完整联合验收。

本轮已执行 17 项服务边界测试与既有前端逻辑检查。真实 HTTPS 隧道已验证首页/脚本/状态返回 200、会话无控制 token、公网 POST 返回 403、管理页及 artifacts 路径返回 404；七类历史摘要与采购历史可读取。外部请求使用本机已有出站代理，尚未代替学校或评委手机网络的实际访问检查。

合并 B 后，场景 1/3/6 可展示真实事件，按完成用例批次采集；旧记录缺少事件时不补造。运行索引重启后不恢复。最新检查见 [整合记录](integration-status-20261016.md)。

旧桌面文件夹 `Agent Guard 服务器` 不会自动删除；确认新入口可用后，可手动删除旧文件夹。
