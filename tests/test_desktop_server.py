"""Real HTTP boundary checks; no Docker, external tunnel, or protocol test shortcuts."""

import http.client
import io
import json
import socket
import threading
import time
import unittest
from unittest.mock import patch

from tools import desktop_server as desktop
from tools import teacher_demo_server as demo


class DesktopBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.manager = desktop.Manager(local_port=0, offline=True)
        self.manager.app = demo.DemoApp()
        for server in (self.manager.local, self.manager.public):
            server.app = self.manager.app
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.manager.threads.append(thread)

    def tearDown(self):
        if self.manager.app.job:
            self.manager.app.job["status"] = "failed"
        self.manager.stop()
        self.manager.close()

    def request(self, public, method, path, headers=None, body=None):
        server = self.manager.public if public else self.manager.local
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            conn.request(method, path, headers=headers or {}, body=body)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_public_cannot_obtain_operator_token_or_private_routes(self):
        status, body = self.request(True, "GET", "/api/session")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"token": "", "read_only": True})
        self.assertNotIn(self.manager.app.token.encode(), body)
        for path in ("/server", "/api/run", "/artifacts/", "/../README.md", "/api/session?x=1"):
            self.assertEqual(self.request(True, "GET", path)[0], 404)
        status, body = self.request(False, "GET", "/api/session")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["token"], self.manager.app.token)

    def test_public_cannot_mutate_even_with_real_token_or_forged_headers(self):
        app = self.manager.app
        valid = {
            "Origin": f"http://127.0.0.1:{self.manager.public.server_port}",
            "X-Demo-Token": app.token,
            "Content-Type": "application/json",
            "X-Forwarded-For": "127.0.0.1",
            "X-Forwarded-Host": f"127.0.0.1:{self.manager.local.server_port}",
        }
        with patch.object(app, "start") as start:
            for path in (
                "/api/run",
                "/api/verify",
                "/api/scenarios/stolen-token/run",
                "/api/scenarios/stolen-token/replay",
            ):
                self.assertEqual(self.request(True, "POST", path, valid, "{}")[0], 403)
            self.assertEqual(self.request(True, "PUT", "/api/run", valid, "{}")[0], 501)
            start.assert_not_called()

    def test_local_control_still_requires_origin_token_and_stops_accepting(self):
        valid = {
            "Origin": f"http://127.0.0.1:{self.manager.local.server_port}",
            "X-Demo-Token": self.manager.app.token,
            "Content-Type": "application/json",
        }
        with patch.object(self.manager.app, "start", return_value=True) as start:
            self.assertEqual(self.request(False, "POST", "/api/run", valid, "{}")[0], 202)
            start.assert_called_once_with("run")
            self.assertEqual(
                self.request(
                    False, "POST", "/api/run", valid | {"Origin": "https://bad.test"}, "{}"
                )[0],
                403,
            )
            self.manager.stop()
            self.assertEqual(self.request(False, "POST", "/api/run", valid, "{}")[0], 503)
            self.assertEqual(start.call_count, 1)

    def test_public_state_and_static_allowlist(self):
        with patch.object(self.manager.app, "state", return_value={"job": None}) as state:
            for _ in range(3):
                status, data = self.request(True, "GET", "/api/state")
                self.assertEqual(status, 200)
                self.assertTrue(json.loads(data)["read_only"])
            self.assertEqual(state.call_count, 1)
        for path in ("/", "/app.js", "/style.css"):
            self.assertEqual(self.request(True, "GET", path)[0], 200)
        self.assertEqual(self.request(True, "GET", "/", {"Host": "evil.test"})[0], 403)
        self.assertEqual(self.request(False, "GET", "/server", {"Host": "evil.test"})[0], 403)

    def test_event_route_public_readonly_and_local_navigation(self):
        route = "/api/runs/12345678-1234-4234-8234-123456789abc/events"
        with patch.object(self.manager.app, "event_page", return_value={"events": []}) as page:
            self.assertEqual(self.request(True, "GET", route)[0], 200)
            page.assert_called_once_with("12345678-1234-4234-8234-123456789abc", 0, 200)
            for query in ("?after_seq=", "?limit=1&limit=2", "?token=x", "?limit=no"):
                self.assertEqual(self.request(True, "GET", route + query)[0], 400)
            self.assertEqual(page.call_count, 1)
        self.assertEqual(self.request(False, "GET", "/", {"Sec-Fetch-Site": "none"})[0], 200)
        self.assertEqual(
            self.request(False, "GET", "/api/session", {"Sec-Fetch-Site": "cross-site"})[0], 403
        )
        self.assertEqual(self.request(True, "GET", "/", {"Sec-Fetch-Site": "cross-site"})[0], 200)

    def test_stop_closes_listeners_but_waits_for_active_job(self):
        self.manager.app.job = {"status": "running"}
        self.manager.stop()
        closer = threading.Thread(target=self.manager.close)
        closer.start()
        time.sleep(1.2)
        self.assertTrue(closer.is_alive())
        for server in (self.manager.local, self.manager.public):
            with self.assertRaises(OSError):
                socket.create_connection(("127.0.0.1", server.server_port), timeout=1)
        with self.manager.app.lock:
            self.manager.app.job["status"] = "failed"
        closer.join(3)
        self.assertFalse(closer.is_alive())


class ProvisionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.server = desktop.LimitedServer(("127.0.0.1", 0), desktop.ProvisionHandler)
        self.server.provision_path = "/test-only-random-path/tunnel"
        self.server.provision_lock = threading.Lock()
        self.server.consumed = False
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, path=None, headers=None, body=b""):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            conn.request("POST", path or self.server.provision_path, body, headers or {})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_fixed_upstream_and_one_shot_no_invalid_requests(self):
        with patch.object(
            desktop.urllib.request, "urlopen", return_value=io.BytesIO(b'{"success":true}')
        ) as upstream:
            self.assertEqual(self.post("/tunnel")[0], 403)
            self.assertEqual(self.post(headers={"Host": "evil.test"})[0], 403)
            self.assertEqual(self.post(body=b"{}")[0], 403)
            upstream.assert_not_called()
            self.assertEqual(self.post()[0], 200)
            self.assertEqual(self.post()[0], 409)
            upstream.assert_called_once()
            self.assertEqual(
                upstream.call_args.args[0].full_url, "https://api.trycloudflare.com/tunnel"
            )

    def test_network_failure_does_not_expose_error_details(self):
        with patch.object(desktop.urllib.request, "urlopen", side_effect=OSError("PRIVATE")):
            code, body = self.post()
            self.assertEqual(code, 502)
            self.assertNotIn(b"PRIVATE", body)

    def test_oversize_response_is_rejected(self):
        with patch.object(
            desktop.urllib.request, "urlopen", return_value=io.BytesIO(b"x" * (1024 * 1024 + 1))
        ):
            code, body = self.post()
            self.assertEqual(code, 502)
            self.assertLess(len(body), 200)

    def test_dns_only_uses_global_ipv4_for_exact_official_name(self):
        records = [
            {"name": "evil.test", "type": 1, "data": "8.8.8.8"},
            {"name": "region1.v2.argotunnel.com", "type": 1, "data": "127.0.0.1"},
            {"name": "region1.v2.argotunnel.com", "type": 28, "data": "::1"},
            {"name": "region1.v2.argotunnel.com", "type": 1, "data": "198.41.192.167"},
        ]
        for data, expected in (
            ([], []),
            ({"Answer": [None]}, []),
            ({"Answer": None}, []),
            ({"Answer": records}, ["--edge", "198.41.192.167:7844"]),
        ):
            with patch.object(
                desktop.urllib.request,
                "urlopen",
                return_value=io.BytesIO(json.dumps(data).encode()),
            ):
                self.assertEqual(desktop.edge_arguments(), expected)


if __name__ == "__main__":
    unittest.main()
