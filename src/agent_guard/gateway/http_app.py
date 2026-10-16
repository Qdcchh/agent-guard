"""Bounded strict ASGI transport for exactly two fixed HTTPS POST endpoints."""

import asyncio
import re
import uuid
from concurrent.futures import ThreadPoolExecutor

from agent_guard.contracts.encoding import EncodingError, canonical_json_bytes
from agent_guard.contracts.execution import MAX_GATEWAY_RESPONSE_BYTES
from agent_guard.gateway.errors import GatewayError, classify

MAX_BODY = 65536
MAX_HEADERS = 65536
MAX_CREDENTIAL = 32768
_PATHS = {"/v1/invocations", "/v1/operations/query"}
_SENSITIVE = {
    b"authorization",
    b"ag-proof",
    b"content-type",
    b"content-length",
    b"transfer-encoding",
    b"host",
}


class GatewayHttpApp:
    def __init__(self, endpoint, *, timeout_seconds: int = 20, max_workers: int = 8):
        if (
            type(timeout_seconds) is not int
            or not 1 <= timeout_seconds <= 60
            or type(max_workers) is not int
            or not 1 <= max_workers <= 32
        ):
            raise ValueError("bounded positive HTTP configuration required")
        self._endpoint = endpoint
        self._timeout = timeout_seconds
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="gateway")
        self._slots = asyncio.Semaphore(max_workers)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
                    await asyncio.to_thread(self._executor.shutdown, wait=True)
                    await send({"type": "lifespan.shutdown.complete"})
                    return
            return
        if scope["type"] != "http":
            return
        request_id = uuid.uuid4().hex
        try:
            status, payload = await asyncio.wait_for(self._request(scope, receive), self._timeout)
            try:
                body = canonical_json_bytes(payload)
            except EncodingError as exc:
                raise GatewayError("TRUSTED_STATE_UNAVAILABLE") from exc
            if len(body) > MAX_GATEWAY_RESPONSE_BYTES:
                raise GatewayError("TRUSTED_STATE_UNAVAILABLE")
            headers = []
        except Exception as exc:  # noqa: BLE001 - public error drops internal detail
            status, code = classify(exc)
            payload = {"error": {"code": code, "request_id": request_id}}
            body = canonical_json_bytes(payload)
            headers = (
                [(b"www-authenticate", b'AGPoP error="' + code.encode("ascii") + b'"')]
                if status == 401
                else []
            )
        headers += [
            (b"content-type", b"application/json"),
            (b"cache-control", b"no-store"),
            (b"pragma", b"no-cache"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    async def _request(self, scope, receive):
        if scope.get("scheme") != "https":
            raise GatewayError("INVALID_SCHEMA")
        path = scope.get("path")
        if path not in _PATHS:
            raise GatewayError("NOT_FOUND")
        if scope.get("method") != "POST":
            raise GatewayError("METHOD_NOT_ALLOWED")
        if scope.get("query_string", b"") or scope.get("raw_path", path.encode()) != path.encode():
            raise GatewayError("INVALID_SCHEMA")
        raw = scope.get("headers", [])
        if len(raw) > 100 or sum(len(k) + len(v) for k, v in raw) > MAX_HEADERS:
            raise GatewayError("REQUEST_TOO_LARGE")
        headers = {}
        for key, value in raw:
            if (
                type(key) is not bytes
                or type(value) is not bytes
                or not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9a-z-]+", key)
                or any(c < 32 or c >= 127 for c in value)
            ):
                raise GatewayError("INVALID_SCHEMA")
            if key in _SENSITIVE and key in headers:
                raise GatewayError("INVALID_SCHEMA")
            headers[key] = value
        if any(
            k in headers
            for k in (b"transfer-encoding", b"content-encoding", b"dpop", b"proxy-authorization")
        ):
            raise GatewayError("INVALID_SCHEMA")
        if headers.get(b"content-type", b"").lower() not in (
            b"application/json",
            b"application/json; charset=utf-8",
        ):
            raise GatewayError("UNSUPPORTED_MEDIA_TYPE")
        length = headers.get(b"content-length")
        if length is not None:
            if not re.fullmatch(rb"0|[1-9][0-9]{0,8}", length):
                raise GatewayError("INVALID_SCHEMA")
            length = int(length)
            if length > MAX_BODY:
                raise GatewayError("REQUEST_TOO_LARGE")
        chunks = bytearray()
        while True:
            event = await receive()
            if event.get("type") != "http.request":
                raise GatewayError("INVALID_SCHEMA")
            chunk, more = event.get("body", b""), event.get("more_body", False)
            if type(chunk) is not bytes or type(more) is not bool:
                raise GatewayError("INVALID_SCHEMA")
            if len(chunks) + len(chunk) > MAX_BODY:
                raise GatewayError("REQUEST_TOO_LARGE")
            chunks.extend(chunk)
            if not more:
                break
        if length is not None and len(chunks) != length:
            raise GatewayError("INVALID_SCHEMA")
        # Schema is independent of authentication: no DB or verification before
        # the complete raw framing/body has been validated.
        self._endpoint.schema(bytes(chunks), query=path == "/v1/operations/query")
        authorization = headers.get(b"authorization", b"")
        proof = headers.get(b"ag-proof", b"")
        if not authorization.startswith(b"AGPoP ") or not proof:
            raise GatewayError("INVALID_SIGNATURE")
        token = authorization[6:]
        if (
            not token
            or len(token) > MAX_CREDENTIAL
            or len(proof) > MAX_CREDENTIAL
            or not re.fullmatch(rb"[A-Za-z0-9_.-]+", token)
            or not re.fullmatch(rb"[A-Za-z0-9_.-]+", proof)
        ):
            raise GatewayError("INVALID_SIGNATURE")
        # Retain capacity until real work finishes, even if the wall timeout
        # returns 503. Running threads cannot be killed; SQL waits are bounded.
        await self._slots.acquire()
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(
            self._executor,
            self._endpoint.handle,
            path,
            token.decode("ascii"),
            proof.decode("ascii"),
            bytes(chunks),
        )

        def completed(done):
            self._slots.release()
            if not done.cancelled():
                done.exception()  # consume sanitized-away failures after HTTP timeout

        future.add_done_callback(completed)
        return await asyncio.shield(future)
