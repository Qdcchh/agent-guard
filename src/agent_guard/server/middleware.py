"""Wall-clock request timeout middleware for the assembled ASGI application.

This bounds the await of one request dispatch; it cannot kill a worker thread
once started, so the trusted services keep their own database statement and
lock timeouts as the real upper bound. After a timeout the response is not
sent late; the connection is closed by the server. Non-HTTP scopes pass through
untouched.
"""

from __future__ import annotations

import asyncio
from typing import Any


class RequestTimeoutMiddleware:
    """Return 503 when a request dispatch exceeds the configured wall clock."""

    def __init__(self, app: Any, *, timeout_seconds: int) -> None:
        if type(timeout_seconds) is not int or isinstance(timeout_seconds, bool):
            raise ValueError("timeout_seconds must be an integer")
        if not 1 <= timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be within [1, 60]")
        self._app = app
        self._timeout = timeout_seconds

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return
        started = False

        async def guarded_send(message: dict) -> None:
            nonlocal started
            if message.get("type") == "http.response.start":
                started = True
            await send(message)

        try:
            await asyncio.wait_for(self._app(scope, receive, guarded_send), timeout=self._timeout)
        except TimeoutError:
            if not started:
                try:
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 503,
                            "headers": [
                                (b"content-type", b"application/json"),
                                (b"cache-control", b"no-store"),
                            ],
                        }
                    )
                    await send({"type": "http.response.body", "body": b'{"error":"TIMEOUT"}'})
                except Exception:
                    pass
