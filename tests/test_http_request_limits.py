"""Exact transport rejection and dispatch controls for every mounted AS route.

Recording handlers intentionally test transport reachability only. Real services
and PostgreSQL side effects are tested separately in test_browser_boundary.py.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from agent_guard.authorization.http_app import AuthorizationHttpApp
from agent_guard.authorization.token_endpoint import TokenResponse
from agent_guard.server.middleware import RequestTimeoutMiddleware

POST_PATHS = (
    "/ag/login",
    "/oauth/authorize",
    "/ag/consent",
    "/oauth/token",
    "/oauth/introspect",
    "/ag/tasks/task-001/revoke",
    "/ag/grants/grant-001/revoke",
)
GET_PATHS = ("/ag/login", "/oauth/authorize", "/.well-known/openid-configuration", "/ag/keys")
ALL_ROUTES = [(p, "POST") for p in POST_PATHS] + [(p, "GET") for p in GET_PATHS]


class RecordingHandlers:
    paths = frozenset({"/ag/login", "/oauth/authorize", "/ag/consent"})

    def __init__(self):
        self.calls = []
        self.error = None
        self.status = 200

    @staticmethod
    def handles(path):
        return path in {"/ag/tasks/task-001/revoke", "/ag/grants/grant-001/revoke"}

    def _called(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return TokenResponse(self.status, {"Content-Type": "application/json"}, b"{}")

    def handle_get(self, path):
        return self._called(path=path)

    def dispatch(self, **kwargs):
        return self._called(**kwargs)

    def handle(self, **kwargs):
        return self._called(**kwargs)


def recording_app():
    handlers = RecordingHandlers()
    return AuthorizationHttpApp(
        discovery=handlers,
        token=handlers,
        introspection=handlers,
        browser=handlers,
        revocation=handlers,
    ), handlers


def media(path):
    return b"application/json" if path.endswith("/revoke") else b"application/x-www-form-urlencoded"


def scope_for(path, method="POST", headers=None, query=b"", scheme="https"):
    if headers is None:
        headers = [(b"content-type", media(path))] if method == "POST" else []
    return {
        "type": "http",
        "scheme": scheme,
        "path": path,
        "method": method,
        "query_string": query,
        "headers": headers,
    }


async def invoke(app, scope, events=None, receive_error=None):
    pending = list(events if events is not None else [{"type": "http.request", "body": b""}])
    sent = []

    async def receive():
        if receive_error is not None:
            raise receive_error
        assert pending, "test did not provide a complete request"
        return pending.pop(0)

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    assert len(sent) == 2
    assert sent[0]["type"] == "http.response.start"
    assert sent[1]["type"] == "http.response.body"
    assert (b"content-length", str(len(sent[1]["body"])).encode()) in sent[0]["headers"]
    return sent[0]["status"], sent[1]["body"], sent[0]["headers"]


def request(app, path, *, method="POST", body=b"", events=None, headers=None, **kwargs):
    if events is None:
        events = [{"type": "http.request", "body": body}]
    return asyncio.run(invoke(app, scope_for(path, method, headers, **kwargs), events))


@pytest.mark.parametrize("path", POST_PATHS)
@pytest.mark.parametrize("chunks", [[65536], [32768, 32768], [1, 65534, 1], [0, 65536, 0]])
def test_legal_exact_body_boundary_reaches_the_intended_handler(path, chunks):
    app, handlers = recording_app()
    events = [
        {"type": "http.request", "body": b"x" * size, "more_body": i < len(chunks) - 1}
        for i, size in enumerate(chunks)
    ]
    assert request(app, path, events=events)[0] == 200
    assert len(handlers.calls) == 1
    call = handlers.calls[0]
    assert call.get("body", call.get("raw_form")) == b"x" * 65536


@pytest.mark.parametrize("path", POST_PATHS)
@pytest.mark.parametrize("chunks", [[65537], [65536, 1], [32768, 32769], [0, 65537]])
def test_excess_body_is_413_and_never_dispatches(path, chunks):
    app, handlers = recording_app()
    events = [
        {"type": "http.request", "body": b"x" * size, "more_body": i < len(chunks) - 1}
        for i, size in enumerate(chunks)
    ]
    status, body, headers = request(app, path, events=events)
    assert status == 413
    assert body == b'{"error":"REQUEST_TOO_LARGE"}'
    assert (b"cache-control", b"no-store") in headers
    assert handlers.calls == []


BAD_EVENTS = [
    None,
    [],
    {},
    {"type": "http.disconnect"},
    {"type": "websocket.receive"},
    {"type": "http.request", "body": "secret-token"},
    {"type": "http.request", "body": bytearray(b"x")},
    {"type": "http.request", "body": None},
    {"type": "http.request", "more_body": 1},
    {"type": "http.request", "more_body": "false"},
]


@pytest.mark.parametrize("path", POST_PATHS)
@pytest.mark.parametrize("event", BAD_EVENTS)
def test_malformed_events_are_400_without_dispatch(path, event):
    app, handlers = recording_app()
    assert request(app, path, events=[event])[:2] == (400, b'{"error":"REQUEST_INVALID"}')
    assert handlers.calls == []


@pytest.mark.parametrize("path", POST_PATHS)
def test_partial_body_disconnect_and_explicit_receive_errors(path):
    for error in (
        ConnectionError("secret-token"),
        TimeoutError("secret-token"),
        RuntimeError("secret-token"),
    ):
        app, handlers = recording_app()
        result = asyncio.run(invoke(app, scope_for(path), receive_error=error))
        assert result[:2] == (400, b'{"error":"REQUEST_INVALID"}')
        assert handlers.calls == []
    app, handlers = recording_app()
    assert (
        request(
            app,
            path,
            events=[
                {"type": "http.request", "body": b"a", "more_body": True},
                {"type": "http.disconnect"},
            ],
        )[0]
        == 400
    )
    assert handlers.calls == []


@pytest.mark.parametrize("path", POST_PATHS)
@pytest.mark.parametrize(
    "kind,expected",
    [("missing", 415), ("wrong", 415), ("charset", 415), ("duplicate", 400), ("combined", 400)],
)
def test_media_required_exactly_once_before_business_dispatch(path, kind, expected):
    app, handlers = recording_app()
    headers = {
        "missing": [],
        "wrong": [(b"content-type", b"text/plain")],
        "charset": [(b"content-type", media(path) + b"; charset=latin1")],
        "duplicate": [(b"content-type", media(path)), (b"Content-Type", media(path))],
        "combined": [(b"content-type", media(path) + b", text/plain")],
    }[kind]
    assert request(app, path, headers=headers, body=b"secret-token")[0] == expected
    assert handlers.calls == []


@pytest.mark.parametrize("path", POST_PATHS)
@pytest.mark.parametrize("suffix", [b"", b"; charset=utf-8"])
def test_supported_media_case_and_utf8_controls(path, suffix):
    app, handlers = recording_app()
    assert request(app, path, headers=[(b"Content-Type", (media(path) + suffix).upper())])[0] == 200
    assert len(handlers.calls) == 1


@pytest.mark.parametrize("path,method", ALL_ROUTES)
@pytest.mark.parametrize(
    "headers",
    [
        None,
        (),
        [b"x"],
        [(b"x",)],
        [(b"x", b"v", b"z")],
        [("x", b"v")],
        [(b"x", "v")],
        [(b"", b"v")],
        [(b"bad name", b"v")],
        [(b"x", b"a\rb")],
        [(b"cookie", b"\xff")],
        [(b"ag-proof", b"\xff")],
    ],
)
def test_invalid_raw_header_shapes_are_client_errors_on_all_routes(path, method, headers):
    app, handlers = recording_app()
    scope = scope_for(path, method)
    scope["headers"] = headers
    assert asyncio.run(invoke(app, scope))[0] == 400
    assert handlers.calls == []


@pytest.mark.parametrize("path", POST_PATHS)
@pytest.mark.parametrize(
    "extra,body,expected",
    [
        ([(b"content-length", b"65537")], b"", 413),
        ([(b"content-length", b"2")], b"x", 400),
        ([(b"content-length", b"0")], b"x", 400),
        ([(b"content-length", b"1"), (b"Content-Length", b"1")], b"x", 400),
        ([(b"content-length", b"+1")], b"x", 400),
        ([(b"content-length", b"1, 1")], b"x", 400),
        ([(b"content-length", b"9" * 21)], b"x", 400),
        ([(b"transfer-encoding", b"chunked"), (b"content-length", b"1")], b"x", 400),
        ([(b"transfer-encoding", b"gzip")], b"x", 400),
        ([(b"transfer-encoding", b"chunked"), (b"transfer-encoding", b"chunked")], b"x", 400),
        ([(b"content-encoding", b"gzip")], b"x", 415),
    ],
)
def test_ambiguous_framing_and_unsupported_encoding_fail_closed(path, extra, body, expected):
    app, handlers = recording_app()
    assert (
        request(app, path, headers=[(b"content-type", media(path)), *extra], body=body)[0]
        == expected
    )
    assert handlers.calls == []


@pytest.mark.parametrize("path", POST_PATHS)
@pytest.mark.parametrize(
    "extra", [[(b"content-length", b"65536")], [(b"transfer-encoding", b"chunked")]]
)
def test_valid_framing_keeps_full_body(path, extra):
    app, handlers = recording_app()
    assert (
        request(app, path, headers=[(b"content-type", media(path)), *extra], body=b"x" * 65536)[0]
        == 200
    )
    assert len(handlers.calls) == 1


@pytest.mark.parametrize("path,method", ALL_ROUTES)
def test_route_method_query_and_trusted_tls_boundaries(path, method):
    app, handlers = recording_app()
    assert request(app, path, method="DELETE")[0] == 405
    assert request(app, path, method=method, scheme="http")[0] == 403
    assert request(app, path, method=method, query="not-bytes")[0] == 400
    if method == "POST" or path not in GET_PATHS[:2]:
        assert request(app, path, method=method, query=b"secret=token")[0] == 400
    assert handlers.calls == []
    assert request(app, path, method=method)[0] == 200
    assert len(handlers.calls) == 1


@pytest.mark.parametrize("path", GET_PATHS)
def test_get_body_refusal_and_empty_positive_control(path):
    app, handlers = recording_app()
    assert request(app, path, method="GET", body=b"x")[0] == 400
    assert request(app, path, method="GET", body=b"x" * 65537)[0] == 413
    assert handlers.calls == []
    assert request(app, path, method="GET")[0] == 200


@pytest.mark.parametrize("path,method", ALL_ROUTES)
@pytest.mark.parametrize("error", [ValueError("secret-token"), RuntimeError("secret-token")])
def test_true_internal_errors_are_sanitized_500(path, method, error):
    app, handlers = recording_app()
    handlers.error = error
    assert request(app, path, method=method)[:2] == (500, b'{"error":"INTERNAL_ERROR"}')
    assert len(handlers.calls) == 1


@pytest.mark.parametrize("path", POST_PATHS)
def test_sync_handlers_do_not_block_async_loop(path):
    app, handlers = recording_app()
    entered, released = threading.Event(), threading.Event()
    original = handlers._called

    def blocked(**kwargs):
        entered.set()
        assert released.wait(3), "event loop could not release the service thread"
        return original(**kwargs)

    handlers._called = blocked

    async def exercise():
        task = asyncio.create_task(invoke(app, scope_for(path)))
        try:
            for _ in range(1000):
                if entered.is_set():
                    break
                await asyncio.sleep(0.001)
            assert entered.is_set()
        finally:
            released.set()
        assert (await task)[0] == 200

    asyncio.run(exercise())
    assert len(handlers.calls) == 1


def test_outer_deadline_on_stalled_body_is_503_before_service_dispatch():
    app, handlers = recording_app()
    sent = []

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        sent.append(message)

    asyncio.run(
        RequestTimeoutMiddleware(app, timeout_seconds=1)(scope_for("/ag/login"), receive, send)
    )
    assert sent[0]["status"] == 503
    assert sent[1]["body"] == b'{"error":"TIMEOUT"}'
    assert handlers.calls == []


def test_outer_cancellation_is_not_misclassified_as_body_400():
    app, handlers = recording_app()

    async def receive():
        raise asyncio.CancelledError

    async def send(message):
        pytest.fail("cancelled request must not emit a client response")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(app(scope_for("/ag/login"), receive, send))
    assert handlers.calls == []


def test_optional_mounting_and_scope_contracts():
    app, handlers = recording_app()
    app._browser = app._revocation = None
    for path in ("/ag/login", "/ag/consent", "/ag/tasks/task-001/revoke", "/unknown"):
        assert request(app, path)[0] == 404
    assert handlers.calls == []
    for field in ("path", "method"):
        scope = scope_for("/oauth/token")
        scope[field] = None
        assert asyncio.run(invoke(app, scope))[0] == 400
    with pytest.raises(ValueError, match="HTTP"):
        asyncio.run(invoke(app, {"type": "websocket"}))


def test_outer_timeout_does_not_promise_dispatched_thread_rollback():
    app, handlers = recording_app()
    released, completed = threading.Event(), threading.Event()
    effects = []
    sent = []

    def slow(**kwargs):
        assert released.wait(3)
        effects.append("finished-after-timeout")
        completed.set()
        return TokenResponse(200, {}, b"{}")

    handlers._called = slow

    async def exercise():
        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            sent.append(message)
            if message["type"] == "http.response.body":
                released.set()

        try:
            await RequestTimeoutMiddleware(app, timeout_seconds=1)(
                scope_for("/ag/login"), receive, send
            )
            assert sent[0]["status"] == 503
            assert await asyncio.to_thread(completed.wait, 2)
            assert effects == ["finished-after-timeout"]
            assert len(sent) == 2
        finally:
            released.set()

    asyncio.run(exercise())
