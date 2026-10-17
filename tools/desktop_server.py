"""macOS desktop launcher: local operator UI and a separate read-only tunnel origin.

Only standard-library dependencies. Never publishes the operator port or kills PIDs
read from a file. A private Unix socket controls the process holding the run lock.
"""

import argparse
import fcntl
import hashlib
import html
import ipaddress
import json
import os
import re
import secrets
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools import teacher_demo_server as demo  # noqa: E402

RUNTIME = REPO / "artifacts/desktop-server"
# macOS Unix socket paths are limited to 104 bytes; use a short private directory.
CONTROL_DIR = Path.home() / "Library/Application Support/AgentGuardServer"
SOCKET = CONTROL_DIR / "control.sock"
BINARY = RUNTIME / "bin/cloudflared"
LOCAL_PORT = 18765


def prepare():
    for directory in (RUNTIME, CONTROL_DIR):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.is_symlink() or directory.stat().st_uid != os.getuid():
            raise RuntimeError("启动目录必须属于当前用户且不能是符号链接")
        directory.chmod(0o700)


def control(action):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(3)
        client.connect(str(SOCKET))
        client.sendall(action.encode() + b"\n")
        data = b""
        while len(data) < 65536:
            block = client.recv(4096)
            if not block:
                return json.loads(data)
            data += block
        raise RuntimeError("控制响应过大")


def snapshot():
    try:
        return control("status")
    except (OSError, ValueError):
        return None


def edge_arguments():
    """Resolve the official edge over HTTPS without changing macOS DNS.

    The pinned binary supports an explicit edge address; its TLS verification and
    server name remain unchanged. Fall back to its normal DNS on lookup failure.
    """
    try:
        request = urllib.request.Request(
            "https://cloudflare-dns.com/dns-query?name=region1.v2.argotunnel.com&type=A",
            headers={"Accept": "application/dns-json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read(65536))
        if not isinstance(data, dict) or not isinstance(data.get("Answer"), list):
            return []
        args = []
        for record in data.get("Answer", []):
            if not isinstance(record, dict):
                continue
            if (
                record.get("type") != 1
                or record.get("name", "").rstrip(".") != "region1.v2.argotunnel.com"
            ):
                continue
            address = ipaddress.IPv4Address(record["data"])
            if address.is_global:
                args.extend(("--edge", f"{address}:7844"))
            if len(args) == 4:
                break
        return args
    except (OSError, ValueError, KeyError, TypeError):
        return []


class LimitedServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler):
        self.slots = threading.BoundedSemaphore(24)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        request.settimeout(5)
        if not self.slots.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.0 503 Busy\r\nContent-Length: 0\r\n\r\n")
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class PublicHandler(demo.Handler):
    """A separate listener, with no authority-bearing response or mutation route."""

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {"error": "无效入口"})
        if self.path == "/api/session":
            return self.reply(200, {"token": "", "read_only": True})
        if self.path == "/api/state":
            return self.reply(200, self.server.manager.public_state())
        response = demo.event_response(self.server.app, self.path)
        if response is not None:
            return self.reply(*response)
        # Explicit whitelist; future operator routes never become public by inheritance.
        if self.path not in ("/", "/app.js", "/style.css"):
            return self.reply(404, {"error": "不存在"})
        # Public navigation may carry a referring site's headers. It has no authority;
        # do not apply the private control listener's same-origin policy here.
        name, kind = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/style.css": ("style.css", "text/css; charset=utf-8"),
        }[self.path]
        return self.reply(200, (demo.STATIC / name).read_bytes(), kind)

    def do_POST(self):
        return self.reply(403, {"error": "公网为只读展示，运行操作请在本机进行"})


class LocalHandler(demo.Handler):
    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {"error": "仅允许本机地址"})
        if self.path == "/server":
            return self.reply(
                200, dashboard(self.server.manager.status()), "text/html; charset=utf-8"
            )
        if self.path == "/server-style.css":
            return self.reply(200, DASHBOARD_CSS.encode(), "text/css; charset=utf-8")
        return super().do_GET()

    def do_POST(self):
        with self.server.manager.request_gate:
            if self.server.manager.stopping.is_set():
                return self.reply(503, {"error": "正在关闭服务"})
            return super().do_POST()


class ProvisionHandler(demo.Handler):
    """One-shot private adapter for cloudflared's documented-in-source quick-service.

    The pinned client's provisioning transport ignores system/environment proxies.
    Only this fixed HTTPS call uses urllib's macOS proxy support. No tunnel credential
    is written to disk or sent through either presentation listener.
    """

    def do_GET(self):
        return self.reply(404, {})

    def do_POST(self):
        if (
            not self.valid_host()
            or self.path != self.server.provision_path
            or self.headers.get_all("Content-Length", []) not in ([], ["0"])
            or self.headers.get("Transfer-Encoding")
        ):
            return self.reply(403, {})
        with self.server.provision_lock:
            if self.server.consumed:
                return self.reply(409, {})
            self.server.consumed = True
        try:
            request = urllib.request.Request(
                "https://api.trycloudflare.com/tunnel",
                data=b"",
                headers={"Content-Type": "application/json", "User-Agent": "cloudflared/2026.10.1"},
            )
            with urllib.request.urlopen(request, timeout=12) as response:
                data = response.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise ValueError("oversized provisioning response")
            self.reply(200, data)
        except (OSError, ValueError):
            self.reply(502, {"success": False, "errors": ["provisioning network unavailable"]})


DASHBOARD_CSS = """
body{margin:0;background:#f4f6fa;color:#182337;font:17px/1.7 -apple-system,sans-serif}
main{max-width:820px;margin:48px auto;padding:32px 40px;background:white;border-radius:20px}
h1{font-size:30px}h2{font-size:20px;margin-top:28px}a{color:#175bc2;overflow-wrap:anywhere}
p{color:#48566b} @media(max-width:600px){main{margin:16px;padding:24px}}
"""


def dashboard(state):
    url = state.get("public_url")
    public = (
        '<p><a href="' + html.escape(url, quote=True) + '">' + html.escape(url) + "</a></p>"
        if url
        else "<p>" + html.escape(state["message"]) + "</p>"
    )
    local = html.escape(state["local_url"], quote=True)
    return (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="stylesheet" href="/server-style.css">'
        '<meta http-equiv="refresh" content="8"><title>Agent Guard 服务器</title>'
        "<body><main><h1>Agent Guard 服务器</h1><p>"
        + html.escape(state["message"])
        + '</p><h2>本机控制页面</h2><p><a href="'
        + local
        + '">打开网站并控制演示</a></p><h2>分享给评委的公网地址</h2>'
        + public
        + "<p>公网访客只浏览；真实运行由你在本机启动。"
        "刷新此页可查看连接状态，临时公网地址每次启动可能变化。</p>"
        "<p>关闭：双击桌面“Agent Guard 服务器”中的“关闭服务器.command”。"
        "关闭后先断开访问，已开始的演示等待完成和清理。</p>"
        "<p>请保持电脑联网、接通电源且不要合盖。服务运行时会阻止自动空闲休眠。</p>"
        "<p>现场任务需要 Docker Desktop 就绪；公网动画仍依当前页面标注区分示意与真实记录。</p>"
        "</main></body></html>"
    ).encode()


class Manager:
    def __init__(self, *, local_port=LOCAL_PORT, offline=False):
        self.stopping = threading.Event()
        self.request_gate = threading.Lock()
        self.lock = threading.Lock()
        self.cache_lock = threading.Lock()
        self.cached = None
        self.cached_at = 0.0
        self.app = demo.DemoApp()
        self.local = LimitedServer(("127.0.0.1", local_port), LocalHandler)
        try:
            self.public = LimitedServer(("127.0.0.1", 0), PublicHandler)
        except BaseException:
            self.local.server_close()
            raise
        for server in (self.local, self.public):
            server.app = self.app
            server.manager = self
        self.url = None
        self.connected = False
        self.message = "本机已启动，正在建立公网连接……"
        self.tunnel = None
        self.provision = None
        self.awake = None
        self.offline = offline
        self.threads = []

    def status(self):
        with self.lock:
            return {
                "status": "stopping" if self.stopping.is_set() else "running",
                "local_url": f"http://127.0.0.1:{self.local.server_port}/",
                "public_url": self.url if self.connected and not self.stopping.is_set() else None,
                "message": self.message,
            }

    def public_state(self):
        with self.cache_lock:
            if self.cached is None or time.monotonic() - self.cached_at > 2:
                self.cached = self.app.state() | {"read_only": True}
                self.cached_at = time.monotonic()
            return self.cached

    def preload(self):
        # Only verified historical summaries. Missing or damaged evidence stays absent.
        for scenario in demo.scenarios.SPECS:
            if self.stopping.is_set():
                return
            try:
                result = demo.scenarios.result(
                    demo.REPO / demo.scenarios.HISTORY, scenario, historical=True
                )
                with self.app.lock:
                    self.app.scenario_results.setdefault(scenario, result)
            except (OSError, ValueError, KeyError, TypeError, demo.scenarios.ET.ParseError):
                pass

    def start(self):
        for server in (self.local, self.public):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.threads.append(thread)
        threading.Thread(target=self.preload, daemon=True).start()
        if sys.platform == "darwin":
            self.awake = subprocess.Popen(
                ["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        if self.offline:
            self.message = "本机已启动；本次未启用公网隧道。"
            return
        if not BINARY.is_file():
            self.message = "本机已启动，但缺少 cloudflared；请查看启动说明。"
            return
        expected = json.loads((REPO / "tools/cloudflared-lock.json").read_text())
        if hashlib.sha256(BINARY.read_bytes()).hexdigest() != expected["binary_sha256"]:
            self.message = "本机已启动，但隧道客户端校验失败；请重新运行安装程序。"
            return
        port = self.public.server_port
        environment = os.environ.copy()
        # Go uses proxy environment variables for the Quick Tunnel API; Finder
        # doesn't export macOS network proxy settings. Honor that existing setting.
        for scheme, proxy in urllib.request.getproxies().items():
            if scheme in ("http", "https"):
                environment.setdefault(scheme.upper() + "_PROXY", proxy)
        environment["NO_PROXY"] = "127.0.0.1,localhost"
        edges = edge_arguments()
        if self.stopping.is_set():
            return
        self.provision = LimitedServer(("127.0.0.1", 0), ProvisionHandler)
        provision_secret = secrets.token_urlsafe(24)
        self.provision.provision_path = f"/{provision_secret}/tunnel"
        self.provision.provision_lock = threading.Lock()
        self.provision.consumed = False
        thread = threading.Thread(target=self.provision.serve_forever, daemon=True)
        thread.start()
        self.threads.append(thread)
        self.tunnel = subprocess.Popen(
            [
                str(BINARY),
                "tunnel",
                "--no-autoupdate",
                "--protocol",
                "http2",
                "--url",
                f"http://127.0.0.1:{port}",
                "--http-host-header",
                f"127.0.0.1:{port}",
                "--metrics",
                "127.0.0.1:0",
                "--quick-service",
                f"http://127.0.0.1:{self.provision.server_port}/{provision_secret}",
            ]
            + edges,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=RUNTIME,
            env=environment,
        )
        threading.Thread(target=self.watch_tunnel, daemon=True).start()

    def watch_tunnel(self):
        with (RUNTIME / "tunnel.log").open("w") as log:
            for line in self.tunnel.stdout:
                log.write(line)
                log.flush()
                match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com\b", line)
                with self.lock:
                    if match:
                        self.url = match[0]
                    if "Registered tunnel connection" in line:
                        self.connected = True
                        self.message = "本机和公网入口已启动。请用手机移动网络核对外部访问。"
                    elif "Unregistered tunnel connection" in line or "failed to serve" in line:
                        self.connected = False
                        self.message = "公网连接中断，隧道正在重连；本机仍可访问。"
        self.tunnel.wait()
        with self.lock:
            self.connected = False
            if not self.stopping.is_set():
                self.message = "公网连接未建立或已退出；本机仍可访问。关闭后重新启动可重试。"

    def stop(self):
        with self.request_gate:
            self.stopping.set()
        with self.lock:
            self.message = "网站入口正在关闭；已开始的任务会完成并清理。"

    def close(self):
        # Reap only our actual child handles, never a PID or Docker name from a state file.
        if self.tunnel is not None:
            self.tunnel.terminate() if self.tunnel.poll() is None else None
            try:
                self.tunnel.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.tunnel.kill()
                self.tunnel.wait()
        for server in (self.public, self.local, self.provision):
            if server is None:
                continue
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=6)
        while True:
            with self.app.lock:
                running = self.app.job and self.app.job["status"] == "running"
            if not running:
                break
            time.sleep(0.2)
        if self.awake is not None:
            if self.awake.poll() is None:
                self.awake.terminate()
            self.awake.wait()


class ControlHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(2)
        action = self.rfile.readline(32).strip()
        if action == b"stop":
            self.server.manager.stop()
        if action not in (b"stop", b"status"):
            result = {"error": "unknown action"}
        else:
            result = self.server.manager.status()
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode())


def serve(port, offline):
    prepare()
    with (CONTROL_DIR / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        SOCKET.unlink(missing_ok=True)
        manager = Manager(local_port=port, offline=offline)
        with socketserver.ThreadingUnixStreamServer(str(SOCKET), ControlHandler) as control_server:
            SOCKET.chmod(0o600)
            control_server.daemon_threads = True
            control_server.manager = manager
            controller = threading.Thread(target=control_server.serve_forever, daemon=True)
            controller.start()
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, lambda *_: manager.stop())
            try:
                manager.start()
                manager.stopping.wait()
            finally:
                manager.stop()
                manager.close()
                control_server.shutdown()
                controller.join()
                SOCKET.unlink(missing_ok=True)
    return 0


def show(state, *, open_browser=False):
    if state is None:
        print("服务器已关闭。")
        return
    print(state["message"])
    print("本机：", state["local_url"])
    print("公网：", state["public_url"] or "尚未连接；状态页会自动刷新。")
    if open_browser and state["status"] == "running":
        subprocess.run(["/usr/bin/open", state["local_url"] + "server"], check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status", "serve"))
    parser.add_argument("--port", type=int, default=LOCAL_PORT)
    parser.add_argument("--offline", action="store_true", help="只启动本机，用于离线检查")
    parser.add_argument("--open", action="store_true", help="打开本机状态页")
    args = parser.parse_args()
    os.umask(0o077)
    prepare()
    if args.action == "serve":
        return serve(args.port, args.offline)
    if args.action == "stop":
        try:
            control("stop")
        except (OSError, ValueError):
            print("服务器未运行。")
            return 0
        # Wait briefly for both listeners to close. Running demos may drain longer.
        deadline = time.monotonic() + 12
        while snapshot() and time.monotonic() < deadline:
            time.sleep(0.2)
        print("网站已停止；后台演示仍在收尾，请稍后查看状态。" if snapshot() else "服务器已关闭。")
        return 0
    state = snapshot()
    if args.action == "start" and state is None:
        with (CONTROL_DIR / "start.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = snapshot()
            if state is None:
                with (RUNTIME / "server.log").open("w") as log:
                    command = [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "serve",
                        "--port",
                        str(args.port),
                    ]
                    if args.offline:
                        command.append("--offline")
                    child = subprocess.Popen(
                        command,
                        cwd=REPO,
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=log,
                        start_new_session=True,
                    )
                deadline = time.monotonic() + 10
                while state is None and time.monotonic() < deadline and child.poll() is None:
                    time.sleep(0.1)
                    state = snapshot()
                if state is None:
                    print("启动失败（可能端口被占用）。日志：", RUNTIME / "server.log")
                    return 1
                if args.open and sys.platform == "darwin":
                    subprocess.run(
                        ["/usr/bin/open", "-gj", "-a", "Docker"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
    show(state, open_browser=args.open)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
