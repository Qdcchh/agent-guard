# CoSeal（共印）展示版部署说明

这是独立的只读展示包，保留讲解页面、动画和打包时导出的历史测试摘要。
所有结果均为保存记录，不是本次服务器运行；右侧过程图为动画示意。
记录不自动更新；更新需要重新生成、替换部署包。包内没有现场实验执行接口。
不需要 Docker、数据库、Node.js、模型 API 或联网安装 Python 依赖。
不包含私钥、口令、原始日志、数据库文件或本机运行环境。

## 最快启动（Linux / macOS）

需要 Python 3.9 或以上。解压后进入包含本文件的目录：

```sh
python3 --version
sh start.sh --host 0.0.0.0 --port 8080
```

浏览器访问 `http://服务器IP:8080/`，服务器防火墙/云安全组需允许该端口。
终端按 Ctrl+C 停止。前台启动用于检查页面，长期运行建议使用下方 Nginx 或 systemd。
Windows 也可在此目录运行 `python server.py --host 0.0.0.0 --port 8080`。
不要直接双击 index.html，否则历史记录接口无法读取。

## 已有 Nginx 的服务器（推荐，无需 Python 常驻）

`site/` 已包含完整静态网页和只读 JSON 接口，可直接由 Nginx 托管。
把 `site/` 中所有内容（包含 `api/`）复制到 `/var/www/coseal/`，保持结构。
将随包 `nginx.conf.example` 放入服务器既有站点配置目录，修改域名和 root，
由管理员执行 `nginx -t` 检查后重载。不要覆盖服务器已有站点配置。
有证书时沿用学校现有 HTTPS 配置。网站需要部署在独立域名或域名根路径，
例如 `https://coseal.example.edu/`，目前不支持挂在 `/coseal/` 子路径。

## Python 服务长期运行（可选）

随包 `coseal-showcase.service.example` 是 Linux systemd 模板。
把整个目录放到 `/opt/coseal-showcase/`；修改模板中的运行用户（非 root）、
Python 路径和项目路径，确保运行用户能读取目录，然后安装为
`/etc/systemd/system/coseal-showcase.service`：

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now coseal-showcase
sudo systemctl status coseal-showcase
```

模板默认只监听 `127.0.0.1:8080`，供现有反向代理接入。
若需要直接通过服务器 IP:8080 访问，把 ExecStart 的 host 改成 `0.0.0.0`。
日志：`journalctl -u coseal-showcase -n 50`。停止：`sudo systemctl stop coseal-showcase`。

## 内容、边界及检查

- `site/`：网页和固定摘要；`snapshot-info.json`：导出时间、来源说明、缺失记录。
- `SHA256SUMS`：包内文件校验清单；在包根目录运行 `sha256sum -c SHA256SUMS`。
- `/api/state` 返回历史摘要，`/api/session` 返回空 token。现场运行按钮禁用。
- `/api/runs/…/events` 不提供历史事件流；既有摘要不重建为虚构事件。
- 未取得有效记录的模块保留“尚无记录”，不补造通过结果。
- 原型边界仍为半诚实、两方、同主机；x402 使用本机测试链和测试代币，无真实资产。
- 本包仅证明保存的展示摘要，不能用于独立重跑、验签或完整联合验收。

部署后检查：主页能打开；五个章节可切换；测试记录能显示；
页面底部提示“历史记录快照”；按钮禁用；刷新页面没有切回本机执行模式。
如果“服务未连接”，检查是否遗漏 `site/api/`，或反向代理是否覆盖了 `/api/` 路径。

开发者重新打包：在原项目根目录运行 `python3 tools/build_showcase.py`。
