"""Minimal ASGI boundary for the implemented AS/OP public and token routes.

An ASGI server or trusted reverse proxy must provide TLS and set the actual
scheme. This app never trusts Host/X-Forwarded headers to construct proof
targets, and it preserves every raw Authorization/AG-Proof occurrence.
"""

from __future__ import annotations

import asyncio
from typing import Any

from agent_guard.authorization.browser import BrowserLoginApp
from agent_guard.authorization.discovery import DiscoveryEndpoint
from agent_guard.authorization.introspection_endpoint import IntrospectionEndpoint
from agent_guard.authorization.token_endpoint import TokenEndpoint, TokenResponse
from agent_guard.contracts.encoding import canonical_json_bytes

_MAX_BODY = 65536
_NO_STORE = {"Content-Type": "application/json", "Cache-Control": "no-store"}


class AuthorizationHttpApp:
    """ASGI adapter for the public, token, introspection and browser routes.

    Login/consent routes are mounted only when a :class:`BrowserLoginApp` is
    supplied; revocation routes remain unmounted and are a separate boundary.
    """

    def __init__(
        self,
        *,
        discovery: DiscoveryEndpoint,
        token: TokenEndpoint,
        introspection: IntrospectionEndpoint,
        browser: BrowserLoginApp | None = None,
    ) -> None:
        if discovery is None or token is None or introspection is None:
            raise ValueError("all AS route handlers required")
        self._discovery = discovery
        self._token = token
        self._introspection = introspection
        self._browser = browser

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            raise ValueError("only HTTP ASGI scopes are supported")
        if scope.get("scheme") != "https":
            await self._send(send, self._error(403, "HTTPS_REQUIRED"))
            return
        path = scope.get("path")
        method = scope.get("method")
        if type(path) is not str or type(method) is not str:
            await self._send(send, self._error(400, "REQUEST_INVALID"))
            return
        if path in {"/.well-known/openid-configuration", "/ag/keys"}:
            response = (
                self._discovery.handle_get(path)
                if method == "GET"
                else self._error(405, "METHOD_NOT_ALLOWED")
            )
            await self._send(send, response)
            return
        if self._browser is not None and path in self._browser.paths:
            if method not in {"GET", "POST"}:
                await self._send(send, self._error(405, "METHOD_NOT_ALLOWED"))
                return
            try:
                query_string = scope.get("query_string", b"")
                raw_body = await self._body(receive) if method == "POST" else b""
                response = await asyncio.to_thread(
                    self._browser.dispatch,
                    method=method,
                    path=path,
                    query_string=query_string,
                    headers=scope["headers"],
                    body=raw_body,
                )
            except Exception:
                response = self._error(500, "INTERNAL_ERROR")
            await self._send(send, response)
            return
        if path not in {"/oauth/token", "/oauth/introspect"}:
            await self._send(send, self._error(404, "NOT_FOUND"))
            return
        if method != "POST":
            await self._send(send, self._error(405, "METHOD_NOT_ALLOWED"))
            return
        if scope.get("query_string") not in (None, b""):
            await self._send(send, self._error(400, "REQUEST_INVALID"))
            return
        try:
            headers = scope["headers"]
            if type(headers) is not list or any(
                type(name) is not bytes or type(value) is not bytes for name, value in headers
            ):
                raise ValueError("invalid raw headers")
            values: dict[bytes, list[str]] = {}
            for name, value in headers:
                lower = name.lower()
                if lower in {b"authorization", b"ag-proof", b"content-type"}:
                    values.setdefault(lower, []).append(value.decode("ascii"))
            content_types = values.get(b"content-type", [])
            if len(content_types) != 1:
                raise ValueError("one content type required")
            raw_form = await self._body(receive)
        except (KeyError, TypeError, ValueError, UnicodeDecodeError):
            await self._send(send, self._error(400, "REQUEST_INVALID"))
            return
        authorization = tuple(values.get(b"authorization", []))
        try:
            if path == "/oauth/token":
                response = await asyncio.to_thread(
                    self._token.handle,
                    content_type=content_types[0],
                    raw_form=raw_form,
                    authorization_headers=authorization,
                    proof_headers=tuple(values.get(b"ag-proof", [])),
                )
            else:
                response = await asyncio.to_thread(
                    self._introspection.handle,
                    content_type=content_types[0],
                    raw_form=raw_form,
                    authorization_headers=authorization,
                )
        except Exception:
            response = self._error(500, "INTERNAL_ERROR")
        await self._send(send, response)

    @staticmethod
    async def _body(receive: Any) -> bytes:
        chunks = bytearray()
        while True:
            event = await receive()
            if event.get("type") != "http.request":
                raise ValueError("request interrupted")
            chunk = event.get("body", b"")
            if type(chunk) is not bytes or len(chunks) + len(chunk) > _MAX_BODY:
                raise ValueError("request body too large")
            chunks.extend(chunk)
            if not event.get("more_body", False):
                return bytes(chunks)

    @staticmethod
    async def _send(send: Any, response: TokenResponse) -> None:
        headers = [
            (key.lower().encode("ascii"), value.encode("ascii"))
            for key, value in response.headers.items()
        ]
        headers.append((b"content-length", str(len(response.body)).encode("ascii")))
        await send({"type": "http.response.start", "status": response.status, "headers": headers})
        await send({"type": "http.response.body", "body": response.body})

    @staticmethod
    def _error(status: int, code: str) -> TokenResponse:
        return TokenResponse(status, dict(_NO_STORE), canonical_json_bytes({"error": code}))
