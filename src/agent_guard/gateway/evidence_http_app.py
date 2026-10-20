"""Strict HTTPS export transport and composition with the accepted gateway app."""

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor

from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.server.config import ConfigError

EXPORT_PATH = "/v1/evidence/export"


class EvidenceHttpApp:
    def __init__(self, endpoint, *, gateway_app=None, max_workers=2, timeout_seconds=600):
        if type(max_workers) is not int or not 1 <= max_workers <= 8:
            raise ValueError("bounded export workers required")
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 600:
            raise ValueError("bounded export materialization timeout required")
        self._endpoint = endpoint
        self._gateway = gateway_app
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="export")
        self._slots = asyncio.Semaphore(max_workers)
        self._timeout = timeout_seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            if self._gateway is not None:

                async def forwarded(event):
                    if event["type"] == "lifespan.shutdown.complete":
                        await asyncio.to_thread(self._executor.shutdown, wait=True)
                    await send(event)

                return await self._gateway(scope, receive, forwarded)
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
                    await asyncio.to_thread(self._executor.shutdown, wait=True)
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        if scope.get("path") != EXPORT_PATH and self._gateway is not None:
            return await self._gateway(scope, receive, send)
        spool = None
        try:
            authorization, raw = await asyncio.wait_for(self._request(scope, receive), 30)
            await asyncio.wait_for(self._slots.acquire(), self._timeout)
            future = asyncio.get_running_loop().run_in_executor(
                self._executor, self._endpoint.handle, authorization, raw
            )
            abandoned = False

            def finished(done):
                self._slots.release()
                if not done.cancelled():
                    try:
                        result = done.result()
                        if abandoned:
                            result.cleanup()
                    except Exception:
                        pass

            future.add_done_callback(finished)
            try:
                spool = await asyncio.wait_for(asyncio.shield(future), self._timeout)
            except BaseException:
                abandoned = True
                if future.done() and not future.cancelled() and future.exception() is None:
                    future.result().cleanup()
                raise
        except Exception as exc:
            status = getattr(exc, "status", 503)
            if isinstance(exc, ConfigError):
                status = 401
            body = canonical_json_bytes({"error": "EXPORT_UNAVAILABLE"})
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"cache-control", b"no-store"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        try:
            with open(spool.path, "rb") as stream:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            (b"content-type", b"application/x-ndjson"),
                            (b"cache-control", b"no-store"),
                            (b"pragma", b"no-cache"),
                            (b"content-length", str(spool.size).encode("ascii")),
                        ],
                    }
                )
                while True:
                    raw = await asyncio.to_thread(stream.read, 65536)
                    if not raw:
                        break
                    await send({"type": "http.response.body", "body": raw, "more_body": True})
                await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            spool.cleanup()

    async def _request(self, scope, receive):
        def refuse(status=400):
            error = ValueError("invalid export transport")
            error.status = status
            raise error

        if scope.get("scheme") != "https":
            refuse()
        if scope.get("path") != EXPORT_PATH:
            refuse(404)
        if scope.get("method") != "POST":
            refuse(405)
        if (
            scope.get("query_string", b"")
            or scope.get("raw_path", EXPORT_PATH.encode()) != EXPORT_PATH.encode()
        ):
            refuse()
        entries = scope.get("headers", [])
        if len(entries) > 100 or sum(len(k) + len(v) for k, v in entries) > 65536:
            refuse(413)
        headers = {}
        for key, value in entries:
            if (
                type(key) is not bytes
                or type(value) is not bytes
                or not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9a-z-]+", key)
                or any(c < 32 or c >= 127 for c in value)
                or key in headers
            ):
                refuse()
            headers[key] = value
        if any(
            k in headers
            for k in (
                b"transfer-encoding",
                b"content-encoding",
                b"dpop",
                b"proxy-authorization",
                b"ag-proof",
            )
        ):
            refuse()
        if headers.get(b"content-type") not in (
            b"application/json",
            b"application/json; charset=utf-8",
        ):
            refuse(415)
        length = headers.get(b"content-length")
        if length is not None:
            if not re.fullmatch(rb"0|[1-9][0-9]{0,5}", length):
                refuse()
            length = int(length)
            if length > 65536:
                refuse(413)
        body = bytearray()
        while True:
            event = await receive()
            if event.get("type") != "http.request":
                refuse()
            chunk, more = event.get("body", b""), event.get("more_body", False)
            if type(chunk) is not bytes or type(more) is not bool:
                refuse()
            body.extend(chunk)
            if len(body) > 65536:
                refuse(413)
            if not more:
                break
        if length is not None and length != len(body):
            refuse()
        try:
            self._endpoint.schema(bytes(body))
        except ValueError:
            refuse()
        return headers.get(b"authorization", b"").decode("ascii"), bytes(body)
