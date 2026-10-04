"""Transport rejection, privacy and wall-time capacity tests with layered doubles."""

import asyncio
import threading

import pytest

from agent_guard.gateway.endpoint import GatewayEndpoint
from agent_guard.gateway.http_app import GatewayHttpApp
from tests.fixtures.gateway import asgi_request, request


@pytest.mark.parametrize("result_size", [63000, 65536, 1024 * 1024])
def test_serialized_response_limit_and_safe_error(result_size):
    class LargeResult:
        schema = staticmethod(GatewayEndpoint.schema)

        def handle(self, *args):
            return 200, {"result": "private-response-marker" + "x" * result_size}

    app = GatewayHttpApp(LargeResult())
    try:
        status, body, headers = request(
            app,
            path="/v1/operations/query",
            body=QUERY,
            headers=[
                (b"content-type", b"application/json"),
                (b"authorization", b"AGPoP a.b.c"),
                (b"ag-proof", b"a.b.c"),
            ],
        )
        assert int(headers[b"content-length"]) <= 65536
        if result_size == 63000:
            assert status == 200 and len(body["result"]) > 63000
        else:
            assert status == 503 and body["error"]["code"] == "TRUSTED_STATE_UNAVAILABLE"
            assert "private-response-marker" not in str(body)
            assert headers[b"cache-control"] == b"no-store"
    finally:
        app._executor.shutdown()


QUERY = b'{"profile":"GM-MVP-1","task_id":"task-001","operation_id":"op"}'


class Never:
    schema = staticmethod(GatewayEndpoint.schema)

    def handle(self, *args):
        raise AssertionError("transport rejection must not reach trusted work")


@pytest.mark.parametrize(
    "changes,headers,body,expected",
    [
        ({"scheme": "http"}, None, QUERY, 400),
        ({"path": "/other"}, None, QUERY, 404),
        ({"method": "GET"}, None, QUERY, 405),
        ({"query_string": b"x=1"}, None, QUERY, 400),
        ({"raw_path": b"/v1/%6fperations/query"}, None, QUERY, 400),
        ({}, [(b"content-type", b"text/plain")], QUERY, 415),
        (
            {},
            [(b"content-type", b"application/json"), (b"content-type", b"application/json")],
            QUERY,
            400,
        ),
        (
            {},
            [
                (b"content-type", b"application/json"),
                (b"authorization", b"a"),
                (b"authorization", b"b"),
            ],
            QUERY,
            400,
        ),
        (
            {},
            [(b"content-type", b"application/json"), (b"ag-proof", b"a"), (b"ag-proof", b"b")],
            QUERY,
            400,
        ),
        ({}, [(b"content-type", b"application/json"), (b"content-length", b"1")], QUERY, 400),
        ({}, [(b"content-type", b"application/json"), (b"content-length", b"01")], QUERY, 400),
        ({}, [(b"content-type", b"application/json"), (b"content-length", b"65537")], QUERY, 413),
        (
            {},
            [(b"content-type", b"application/json"), (b"transfer-encoding", b"chunked")],
            QUERY,
            400,
        ),
        ({}, [(b"content-type", b"application/json"), (b"content-encoding", b"gzip")], QUERY, 400),
        ({}, [(b"content-type", b"application/json"), (b"dpop", b"attack")], QUERY, 400),
        ({}, [(b"content-type", b"application/json"), (b"x-test", b"\xff")], QUERY, 400),
        ({}, None, b"{" * 65 + b"}" * 65, 400),
        ({}, None, b'{"profile":"GM-MVP-1","profile":"GM-MVP-1"}', 400),
        ({}, None, b'{"x":NaN}', 400),
        ({}, None, b" " * 65537, 413),
        ({}, None, QUERY, 401),
    ],
)
def test_rejection_before_services(changes, headers, body, expected):
    app = GatewayHttpApp(Never())
    result = request(app, headers=headers, body=body, **{"path": "/v1/operations/query", **changes})
    assert result[0] == expected
    assert set(result[1]) == {"error"}
    assert set(result[1]["error"]) == {"code", "request_id"}
    assert len(result[1]["error"]["request_id"]) == 32
    assert result[2][b"cache-control"] == b"no-store"
    assert result[2][b"pragma"] == b"no-cache"
    if expected == 401:
        assert result[2][b"www-authenticate"].startswith(b"AGPoP ")
    app._executor.shutdown()


@pytest.mark.parametrize(
    "events",
    [
        [{"type": "http.disconnect"}],
        [{"type": "http.request", "body": "wrong"}],
        [{"type": "http.request", "body": QUERY, "more_body": 1}],
    ],
)
def test_bad_receive_event(events):
    app = GatewayHttpApp(Never())
    assert request(app, path="/v1/operations/query", events=events)[0] == 400
    app._executor.shutdown()


def test_timeout_retains_capacity_and_event_loop_remains_live():
    entered = threading.Event()
    release = threading.Event()

    class Slow:
        schema = staticmethod(GatewayEndpoint.schema)

        def handle(self, *args):
            entered.set()
            assert release.wait(5)
            raise ValueError("sensitive synthetic marker")

    async def run():
        app = GatewayHttpApp(Slow(), timeout_seconds=1, max_workers=1)
        headers = [
            (b"content-type", b"application/json"),
            (b"authorization", b"AGPoP a.b.c"),
            (b"ag-proof", b"a.b.c"),
            (b"x-request-id", b"attacker-id"),
        ]
        job = asyncio.create_task(
            asgi_request(app, path="/v1/operations/query", body=QUERY, headers=headers)
        )
        await asyncio.sleep(0.05)
        assert entered.is_set()
        assert (await asgi_request(app, path="/unknown"))[0] == 404
        result = await job
        assert result[0] == 503 and "sensitive" not in str(result)
        assert result[1]["error"]["request_id"] != "attacker-id"
        assert app._slots.locked()
        release.set()
        for _ in range(50):
            if not app._slots.locked():
                break
            await asyncio.sleep(0.01)
        assert not app._slots.locked()
        app._executor.shutdown()

    asyncio.run(run())
