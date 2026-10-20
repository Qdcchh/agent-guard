"""Linux-friendly demo: private operator and separate read-only reverse-proxy origin."""

import argparse
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools import teacher_demo_server as demo  # noqa: E402


class LimitedServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, app):
        self.app = app
        self.slots = threading.BoundedSemaphore(24)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        request.settimeout(5)
        if not self.slots.acquire(blocking=False):
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
    """Explicit route allowlist; never return a control token or accept an action."""

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {"error": "无效入口"})
        if self.path == "/api/session":
            return self.reply(200, {"token": "", "read_only": True})
        if self.path == "/api/state":
            return self.reply(200, self.server.app.state() | {"read_only": True})
        response = demo.event_response(self.server.app, self.path)
        if response is not None:
            return self.reply(*response)
        files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/style.css": ("style.css", "text/css; charset=utf-8"),
        }
        if self.path not in files:
            return self.reply(404, {"error": "不存在"})
        name, kind = files[self.path]
        return self.reply(200, (demo.STATIC / name).read_bytes(), kind)

    def do_POST(self):
        return self.reply(403, {"error": "公网只读；请通过 SSH 转发访问控制端"})


def make_servers(operator_port=8765, public_port=8766, app=None):
    app = app or demo.DemoApp()
    operator = LimitedServer(("127.0.0.1", operator_port), demo.Handler, app)
    try:
        public = LimitedServer(("127.0.0.1", public_port), PublicHandler, app)
    except BaseException:
        operator.server_close()
        raise
    return operator, public


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-port", type=int, default=8765)
    parser.add_argument("--public-port", type=int, default=8766)
    args = parser.parse_args()
    operator, public = make_servers(args.operator_port, args.public_port)
    threads = []
    for server in (operator, public):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        threads.append(thread)
    print(f"控制端（仅回环）：http://127.0.0.1:{operator.server_port}/", flush=True)
    print(f"只读反代源站：http://127.0.0.1:{public.server_port}/", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("停止接收请求；等待已启动演示完成及清理。", flush=True)
    finally:
        for server in (operator, public):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()
        while operator.app.job and operator.app.job["status"] == "running":
            time.sleep(1)


if __name__ == "__main__":
    main()
