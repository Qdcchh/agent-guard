"""HTTP separation checks without Docker or changes to protocol test assertions."""

import http.client
import json
import threading
from unittest.mock import patch

from tools import full_demo_server as full


def request(server, method, path, headers=None, body=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_listener_separation_and_private_action():
    app = full.demo.DemoApp()
    operator, public = full.make_servers(0, 0, app)
    threads = [threading.Thread(target=s.serve_forever) for s in (operator, public)]
    for thread in threads:
        thread.start()
    try:
        assert operator.server_address[0] == public.server_address[0] == "127.0.0.1"
        status, body = request(public, "GET", "/api/session")
        assert status == 200
        assert json.loads(body) == {"token": "", "read_only": True}
        assert app.token.encode() not in body
        assert json.loads(request(public, "GET", "/api/state")[1])["read_only"] is True
        assert request(public, "GET", "/", {"Host": "external.example"})[0] == 403
        for path in ("/", "/app.js", "/style.css"):
            assert request(public, "GET", path)[0] == 200
        for path in ("/api/run", "/artifacts/", "/../README.md", "/api/session?x=1"):
            assert request(public, "GET", path)[0] == 404
        headers = {
            "Origin": f"http://127.0.0.1:{operator.server_port}",
            "X-Demo-Token": app.token,
            "Content-Type": "application/json",
            "X-Forwarded-For": "127.0.0.1",
        }
        with patch.object(app, "start", return_value=True) as start:
            for path in ("/api/run", "/api/verify", "/api/cosm2/run", "/api/x402/run"):
                assert request(public, "POST", path, headers, "{}")[0] == 403
            start.assert_not_called()
            assert request(operator, "POST", "/api/run", headers, "{}")[0] == 202
            start.assert_called_once_with("run")
            assert (
                request(operator, "POST", "/api/run", headers | {"X-Demo-Token": "bad"}, "{}")[0]
                == 403
            )
            assert (
                request(
                    operator,
                    "POST",
                    "/api/run",
                    headers | {"Origin": "https://other.example"},
                    "{}",
                )[0]
                == 403
            )
    finally:
        for server in (operator, public):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()


def test_public_read_only_flag_does_not_modify_operator_state():
    app = full.demo.DemoApp()
    state = {"job": None}
    operator, public = full.make_servers(0, 0, app)
    thread = threading.Thread(target=public.serve_forever)
    thread.start()
    try:
        with patch.object(app, "state", return_value=state):
            assert json.loads(request(public, "GET", "/api/state")[1])["read_only"] is True
            assert "read_only" not in state
    finally:
        public.shutdown()
        public.server_close()
        operator.server_close()
        thread.join()
