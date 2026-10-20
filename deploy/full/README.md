# CoSeal 完整版试部署（Linux）

本包包含网页、Python 源码、固定实验入口、数据库迁移、测试、依赖锁文件与镜像构建材料。它是竞赛原型的完整源码试部署包，不代表生产服务，也不代表在老师服务器上完成了全链路验收。整体项目仍为 PARTIAL；各阶段的历史验收范围见仓库 README 和 `docs/acceptance.md`。

完整版允许老师通过 SSH 转发操作真实实验，公众通过 Nginx 浏览只读页面。两种入口共享本次实验结果。操作端只监听服务器回环地址，沿用既有 Host、Origin 和会话令牌检查；没有新增公网登录系统，因此不要将操作端反代到公网。

## 1. 服务器条件

- 优先使用 Linux x86_64（amd64）。现有实验、Rust signer、随源码附带的 Anvil 二进制使用 linux/amd64；ARM64 需要 amd64 仿真，未验证其兼容性和性能。
- Python 3.11 或以上；网页服务和宿主启动器只需标准库，密码库和数据库驱动在容器中安装。
- Docker Engine、Docker CLI、现代 Docker Compose v2。正常采购与安全场景需要 Compose 的 `volume.subpath` 支持，只有“已安装 Compose”还不够；若报 subpath 不支持，应升级 Engine/Compose 后重试。
- 操作系统允许启动独立容器、网络和卷，允许容器内 UID、只读挂载及 tmpfs。启动服务的用户必须有 Docker 权限，也有解压目录的写权限。使用同机 Docker daemon；远程 daemon 无法直接读取本机源码挂载路径。
- 能访问镜像仓库、PyPI 和 crates.io。首次构建会下载 Python/Rust/PostgreSQL 镜像和锁定依赖，磁盘和内存要留出余量；不附带已经构建的 Docker 镜像，不保证离线部署。
- 演示使用合成采购、确定性代理、临时 PostgreSQL 和本地测试链，无需模型 API、真实钱包或生产数据库。

## 2. 解压与构建

将 ZIP 解压后进入项目根目录（能看到 `pyproject.toml`）。不要将整个源码目录配置为 Nginx 静态根目录。

```sh
python3 --version
docker version
docker compose version
docker info
sh deploy/full/build-images.sh
```

脚本按顺序构建这三个准确标签：

1. `agent-guard-normal-wheel:local`
2. `agent-guard-threshold-gateway-runner:20261017`（基础镜像由命令显式传入，覆盖源码中旧本机 UUID 标签）
3. `agent-guard-x402-runner:20261017`

不要按旧说明将第二个镜像命名为 `agent-guard-threshold-runner:local`，现有协同签名和门限启动器不读取该名称。正常采购及安全场景仍会自行构建带运行 UUID 的隔离镜像，预构建不能省略它们的构建与网络需求。

Linux 上不要直接继承原 Mac 的 `127.0.0.1:7897` 之类代理。部分旧启动器会把本地代理改写为 `host.docker.internal`，Linux 默认没有此 DNS；请使用容器能访问的代理地址，或清除无效的 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 及对应小写变量。构建失败应保留原错误，不应修改依赖版本或关闭验权来绕过。

## 3. 启动与老师操作

在服务器项目根目录运行（建议先在 tmux 中前台运行）：

```sh
umask 077
python3 tools/full_demo_server.py
```

默认入口：

- `127.0.0.1:8765`：完整控制，仅服务器本机或 SSH 转发使用。
- `127.0.0.1:8766`：只读反代源站；无操作令牌，所有 POST 拒绝。

老师在自己的电脑终端建立隧道，将 `teacher` 和 `SERVER_IP` 替换为实际 SSH 用户和地址：

```sh
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 teacher@SERVER_IP
```

保持 SSH 运行，浏览器打开 `http://127.0.0.1:8765/`。本地转发端口需要与服务器操作端一致，现有 Host/Origin 校验要求 `127.0.0.1` 和相同端口。若本地 8765 已占用，可同时修改服务器的 `--operator-port` 和 SSH 两侧端口，不要关闭校验。

依次试运行正常采购、七类安全场景、协同 SM2、门限签名及 x402；同一时刻只接受一个任务。页面显示的依赖提示可能仍称 Docker Desktop，Linux 实际使用 Docker Engine 即可。每次以页面任务状态和新结果为准，不把“按钮可点击”“镜像构建完成”当作实验成功。

本包不包含本机原始 `artifacts`、历史凭据、私钥、数据库或日志，所以首次运行记录为空、历史读取不可用属于预期。先执行新的实验，成功后显示本次结果。

离线证据验证需要完整证据文件和对应运行镜像。正常采购会清理 UUID 镜像，但现有验证入口仍按该 UUID 寻找镜像。因此在成功完成采购后，先将同份源码构建的通用镜像加一个该次采购运行 ID 的标签，再点“验证”。以下用 `RUN_ID` 代表页面显示的采购运行 UUID（不是安全场景或协同签名 UUID），请替换为实际值：

```sh
docker tag agent-guard-normal-wheel:local agent-guard-normal-wheel:RUN_ID
```

仅在确认该确切标签不存在时创建，勿覆盖他人镜像标签；通用镜像必须由当前部署的同份源码构建。验证完成后，可 `docker image rm agent-guard-normal-wheel:RUN_ID` 删除自己刚创建的确切标签。此操作不补造证据，也不改变实验清理策略；缺少原证据仍应失败。需要独立证据验证时另按 `docs/teacher-demo-20261015.md` 检查证据和可信公钥来源。

## 4. Nginx 公网只读示例

将下面片段加入老师现有 Nginx 站点；替换域名，由服务器管理员按现有环境配置 HTTPS。只能代理 8766，不要将 8765 配成 upstream。

```nginx
server {
    listen 80;
    server_name demo.example.edu;

    location / {
        proxy_pass http://127.0.0.1:8766;
        proxy_set_header Host 127.0.0.1:8766;
        proxy_connect_timeout 5s;
        proxy_read_timeout 15s;
        client_max_body_size 1k;
    }
}
```

`Host` 必须按示例固定为反代源站地址，不能使用 `$host`；入口会拒绝其他 Host。此配置按域名根路径部署，未支持 `/coseal/` 子路径。Nginx 与 Python 需在同一主机网络环境。公网状态及事件只返回既有脱敏结果接口，文件访问仅允许三份网页资产，不公开源码、私密日志或任意文件。

## 5. 停止、故障与验证范围

按 Ctrl+C 停止 HTTP 入口后，程序会等待已经启动的实验结束及清理。不要在任务运行中直接强制杀进程或重启服务器。既有固定启动器按自身 owner 标签与资源 ID 清理；不要对共享服务器执行 `docker system prune` 或删除不明容器/卷。

新结果和诊断写入 `artifacts/`。失败时保留该轮记录，检查 Docker 权限、架构、网络、Compose subpath 支持和镜像标签。原始诊断可能含内部路径或测试凭据，不要直接传到公网或 GitHub。

本次新增入口的检查覆盖两端 HTTP 权限隔离、只读状态、静态文件白名单和控制端 Origin/令牌验证。这些边界测试不运行 Docker。完整 Linux 镜像构建、全部现场实验及老师服务器 Nginx/SSH 配置尚需在目标机器实际验证；本包没有将这些项目标为已通过。
