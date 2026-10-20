"""Standalone read-only showcase server; Python standard library only."""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "site"
ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/api/state": ("api/state", "application/json; charset=utf-8"),
    "/api/session": ("api/session", "application/json; charset=utf-8"),
}


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        self.slots = threading.BoundedSemaphore(32)
        # Freeze an explicit allowlist in memory. No filesystem route resolution.
        self.responses = {
            route: ((ROOT / name).read_bytes(), kind) for route, (name, kind) in ROUTES.items()
        }
        super().__init__(address, Handler)

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


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, kind="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        for name, value in {
            "Content-Type": kind,
            "Content-Length": str(len(body)),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
            ),
            "Connection": "close",
        }.items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        response = self.server.responses.get(self.path)
        if response is None:
            return self.reply(404, {"error": "不存在"})
        body, kind = response
        return self.reply(200, body, kind)

    do_HEAD = do_GET

    def reject(self):
        return self.reply(403, {"error": "展示版只读，不提供现场运行"})

    do_POST = reject
    do_PUT = reject
    do_PATCH = reject
    do_DELETE = reject


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    with Server((args.host, args.port)) as server:
        print(f"CoSeal 展示版：http://{args.host}:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
