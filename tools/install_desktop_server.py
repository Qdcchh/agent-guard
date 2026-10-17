"""Install the pinned official tunnel client and three macOS desktop shortcuts."""

import hashlib
import io
import json
import os
import platform
import shlex
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise SystemExit("此安装入口针对 Apple Silicon Mac；其他平台需要单独固定客户端版本。")
    os.umask(0o077)
    lock = json.loads((REPO / "tools/cloudflared-lock.json").read_text())
    binary = REPO / "artifacts/desktop-server/bin/cloudflared"
    if (
        not binary.is_file()
        or hashlib.sha256(binary.read_bytes()).hexdigest() != lock["binary_sha256"]
    ):
        print("正在下载 Cloudflare 官方客户端并校验 SHA-256……", flush=True)
        # urllib on macOS honors the user's existing system proxy configuration.
        with urllib.request.urlopen(lock["url"], timeout=90) as response:
            data = response.read(64 * 1024 * 1024 + 1)
        if hashlib.sha256(data).hexdigest() != lock["sha256"]:
            raise SystemExit("下载校验失败，未安装。请检查网络后重新运行。")
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            member = archive.getmember("cloudflared")
            if not member.isfile():
                raise SystemExit("压缩包格式不符合预期")
            executable = archive.extractfile(member).read()
        if hashlib.sha256(executable).hexdigest() != lock["binary_sha256"]:
            raise SystemExit("客户端校验失败，未安装")
        binary.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        binary.write_bytes(executable)
        binary.chmod(0o700)
    folder = Path.home() / "Desktop/Agent Guard 服务器"
    folder.mkdir(exist_ok=True)
    python = shutil.which("python3") or sys.executable
    for name, action in (
        ("启动服务器", "start"),
        ("关闭服务器", "stop"),
        ("查看服务器地址", "status"),
    ):
        args = [python, str(REPO / "tools/desktop_server.py"), action]
        if action != "stop":
            args.append("--open")
        script = (
            "#!/bin/zsh\n"
            'export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"\n'
            + "cd "
            + shlex.quote(str(REPO))
            + " || exit 1\n"
            + shlex.join(args)
            + "\n"
        )
        path = folder / (name + ".command")
        path.write_text(script)
        path.chmod(0o700)
    (folder / "使用说明.txt").write_text(
        "Agent Guard 本机服务器\n\n"
        "1. 双击“启动服务器.command”。浏览器会打开状态页，公网地址建立后自动显示。\n"
        "2. 点击“打开网站并控制演示”用于本机操作；复制公网地址发给评委。\n"
        "3. 公网只能浏览、查看历史记录与本机新运行的结果，不能启动任务。\n"
        "4. 双击“关闭服务器.command”关闭网站。已启动的任务会完成并清理，期间不能重复启动。\n"
        "5. 双击“查看服务器地址.command”重新打开状态页。\n\n"
        "临时公网地址每次启动可能变化，不要收藏为永久地址。\n"
        "无需购买公网IP；服务依赖本机网络及Cloudflare临时隧道可用性。\n"
        "保持接电、联网，不要合盖或手动休眠；启动时会防止自动空闲休眠。\n"
        "现场运行需要Docker Desktop；启动入口会尝试打开它。首次运行前等待Docker就绪。\n"
        "场景1/3/6已接真实事件，按完成用例批次更新；示意动画不等于现场协议轨迹。\n"
        "关闭终端窗口不会停止服务器，请使用关闭入口。\n\n"
        "项目目录：" + str(REPO) + "\n"
        "诊断日志：" + str(REPO / "artifacts/desktop-server") + "\n"
    )
    print("已安装桌面入口：", folder)


if __name__ == "__main__":
    main()
