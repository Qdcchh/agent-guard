"""Local HTTPS-only audit server with finite connection and body limits."""

from __future__ import annotations

import ssl
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent_guard.audit.config import validate_approved_listener
from agent_guard.audit.http_app import AuditHTTPApp
from agent_guard.audit.store import AuditStore
from agent_guard.contracts.encoding import canonical_json_bytes


def create_server(config, *, store=None, approved_listener_host: str | None = None):
    if approved_listener_host is not None:
        validate_approved_listener(config.host, approved_listener_host)
    elif config.host != "127.0.0.1":
        raise ValueError("IPv4 loopback listener required")
    app = AuditHTTPApp(
        store
        or AuditStore(
            config.dsn,
            owner_role=config.owner_role,
            private_key=config.signing_key(),
            key_id=config.key_id,
            external_pins=config.external_pins,
            external_trust=config.external_trust,
        )
    )

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, format, *args):
            pass

        def _reply(self, status, raw):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(raw)
            self.close_connection = True

        def _discard_oversize_body(self):
            deadline = time.monotonic() + 1
            remaining = 65537
            original_timeout = self.connection.gettimeout()
            try:
                while remaining:
                    timeout = deadline - time.monotonic()
                    if timeout <= 0:
                        break
                    self.connection.settimeout(timeout)
                    try:
                        chunk = self.rfile.read1(min(remaining, 16384))
                    except (TimeoutError, OSError):
                        break
                    if not chunk:
                        break
                    remaining -= len(chunk)
            finally:
                self.connection.settimeout(original_timeout)

        def do_POST(self):
            try:
                if self.headers.get_all("Transfer-Encoding") or any(
                    len(self.headers.get_all(k, [])) != 1
                    for k in ("Content-Length", "Content-Type", "Authorization")
                ):
                    raise ValueError("ambiguous HTTP envelope")
                length_text = self.headers["Content-Length"]
                if (
                    not length_text.isascii()
                    or not length_text.isdecimal()
                    or str(int(length_text)) != length_text
                    or int(length_text) < 1
                ):
                    raise ValueError("invalid body length")
                if int(length_text) > 65536:
                    self._discard_oversize_body()
                    raise ValueError("invalid body length")
                raw = self.rfile.read(int(length_text))
                if len(raw) != int(length_text):
                    raise ValueError("incomplete request")
                status, result = app.dispatch("POST", self.path, self.headers, raw)
                self._reply(status, result)
            except (ValueError, TimeoutError, OSError):
                self._reply(400, canonical_json_bytes({"error": "INVALID_REQUEST"}))

        def do_GET(self):
            self._reply(405, canonical_json_bytes({"error": "METHOD_NOT_ALLOWED"}))

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(config.tls_certificate), str(config.tls_private_key))

    class TLSServer(ThreadingHTTPServer):
        def get_request(self):
            raw, address = super().get_request()
            raw.settimeout(3)
            try:
                return context.wrap_socket(raw, server_side=True), address
            except BaseException:
                raw.close()
                raise

    server = TLSServer((config.host, config.port), Handler)
    server.daemon_threads = True
    return server


def serve(config):
    with create_server(config) as server:
        server.serve_forever(poll_interval=0.1)
