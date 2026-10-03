"""Bounded ASGI boundary for the implemented AS/OP routes.

Only a trusted ASGI server supplies the TLS scheme. Host/Forwarded never
construct proof targets. Raw credential occurrences survive until authentication.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from agent_guard.authorization.browser import BrowserLoginApp
from agent_guard.authorization.discovery import DiscoveryEndpoint
from agent_guard.authorization.introspection_endpoint import IntrospectionEndpoint
from agent_guard.authorization.revocation_http import RevocationHttpApp
from agent_guard.authorization.token_endpoint import TokenEndpoint, TokenResponse
from agent_guard.contracts.encoding import canonical_json_bytes

_MAX_BODY = 65536
_NO_STORE = {"Content-Type": "application/json", "Cache-Control": "no-store"}
_HEADER_NAME = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
_ASCII_HEADERS = frozenset(
    {
        b"authorization",
        b"ag-proof",
        b"content-type",
        b"content-length",
        b"transfer-encoding",
        b"content-encoding",
        b"cookie",
        b"x-csrf-token",
    }
)
_FORM = "application/x-www-form-urlencoded"


class _RequestError(Exception):
    """An explicitly identified untrusted request/transport failure only."""

    def __init__(self, status: int, code: str = "REQUEST_INVALID") -> None:
        self.status = status
        self.code = code
        super().__init__(code)


class AuthorizationHttpApp:
    """Mount public/token/introspection and optional browser/revocation handlers."""

    def __init__(
        self,
        *,
        discovery: DiscoveryEndpoint,
        token: TokenEndpoint,
        introspection: IntrospectionEndpoint,
        browser: BrowserLoginApp | None = None,
        revocation: RevocationHttpApp | None = None,
    ) -> None:
        if discovery is None or token is None or introspection is None:
            raise ValueError("all AS route handlers required")
        self._discovery = discovery
        self._token = token
        self._introspection = introspection
        self._browser = browser
        self._revocation = revocation

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            raise ValueError("only HTTP ASGI scopes are supported")
        if scope.get("scheme") != "https":
            await self._send(send, self._error(403, "HTTPS_REQUIRED"))
            return
        try:
            response = await self._dispatch(scope, receive)
        except _RequestError as exc:
            response = self._error(exc.status, exc.code)
        except Exception:
            # Service/domain failures are classified by their trusted adapters.
            # A programming error (including ValueError) is never client input.
            response = self._error(500, "INTERNAL_ERROR")
        await self._send(send, response)

    async def _dispatch(self, scope: dict, receive: Any) -> TokenResponse:
        path, method = scope.get("path"), scope.get("method")
        if type(path) is not str or type(method) is not str:
            raise _RequestError(400)
        if path in {"/.well-known/openid-configuration", "/ag/keys"}:
            route, methods = "public", {"GET"}
        elif self._browser is not None and path in self._browser.paths:
            route = "browser"
            methods = {"POST"} if path == "/ag/consent" else {"GET", "POST"}
        elif self._revocation is not None and self._revocation.handles(path):
            route, methods = "revocation", {"POST"}
        elif path in {"/oauth/token", "/oauth/introspect"}:
            route, methods = "token", {"POST"}
        else:
            return self._error(404, "NOT_FOUND")
        if method not in methods:
            return self._error(405, "METHOD_NOT_ALLOWED")
        query = scope.get("query_string", b"")
        if type(query) is not bytes or (query and not (route == "browser" and method == "GET")):
            raise _RequestError(400)
        if len(query) > _MAX_BODY:
            raise _RequestError(413, "REQUEST_TOO_LARGE")
        headers, values, length = self._headers(scope.get("headers"))
        content_type = None
        if method == "POST":
            content_type = self._media(
                values, "application/json" if route == "revocation" else _FORM
            )
        raw_body = await self._body(receive, length=length)
        if method == "GET" and raw_body:
            raise _RequestError(400)
        if route == "public":
            return self._discovery.handle_get(path)
        if route == "browser":
            return await asyncio.to_thread(
                self._browser.dispatch,
                method=method,
                path=path,
                query_string=query,
                headers=headers,
                body=raw_body,
            )
        if route == "revocation":
            return await asyncio.to_thread(
                self._revocation.dispatch,
                method=method,
                path=path,
                headers=headers,
                body=raw_body,
            )
        authorization = tuple(values.get(b"authorization", []))
        if path == "/oauth/token":
            return await asyncio.to_thread(
                self._token.handle,
                content_type=content_type,
                raw_form=raw_body,
                authorization_headers=authorization,
                proof_headers=tuple(values.get(b"ag-proof", [])),
            )
        return await asyncio.to_thread(
            self._introspection.handle,
            content_type=content_type,
            raw_form=raw_body,
            authorization_headers=authorization,
        )

    @staticmethod
    def _headers(raw: object) -> tuple[list, dict[bytes, list[str]], int | None]:
        if type(raw) is not list:
            raise _RequestError(400)
        values: dict[bytes, list[str]] = {}
        for header in raw:
            if type(header) not in (tuple, list) or len(header) != 2:
                raise _RequestError(400)
            name, value = header
            if (
                type(name) is not bytes
                or type(value) is not bytes
                or not _HEADER_NAME.fullmatch(name)
                or any(byte < 32 and byte != 9 or byte == 127 for byte in value)
            ):
                raise _RequestError(400)
            lower = name.lower()
            if lower in _ASCII_HEADERS:
                try:
                    text = value.decode("ascii")
                except UnicodeDecodeError as exc:
                    raise _RequestError(400) from exc
                values.setdefault(lower, []).append(text)
        for name in (b"content-type", b"content-length", b"transfer-encoding", b"content-encoding"):
            if len(values.get(name, [])) > 1:
                raise _RequestError(400)
        lengths = values.get(b"content-length", [])
        transfers = values.get(b"transfer-encoding", [])
        if transfers and (lengths or transfers[0].lower() != "chunked"):
            raise _RequestError(400)
        if values.get(b"content-encoding", ["identity"])[0].lower() != "identity":
            raise _RequestError(415, "UNSUPPORTED_MEDIA_TYPE")
        length = None
        if lengths:
            if not re.fullmatch(r"[0-9]{1,20}", lengths[0], flags=re.ASCII):
                raise _RequestError(400)
            length = int(lengths[0])
            if length > _MAX_BODY:
                raise _RequestError(413, "REQUEST_TOO_LARGE")
        return raw, values, length

    @staticmethod
    def _media(values: dict[bytes, list[str]], expected: str) -> str:
        content_types = values.get(b"content-type", [])
        if not content_types:
            raise _RequestError(415, "UNSUPPORTED_MEDIA_TYPE")
        value = content_types[0].lower()
        if "," in value:
            raise _RequestError(400)
        if value not in {expected, expected + "; charset=utf-8"}:
            raise _RequestError(415, "UNSUPPORTED_MEDIA_TYPE")
        return value

    @staticmethod
    async def _body(receive: Any, *, length: int | None = None) -> bytes:
        chunks = bytearray()
        while True:
            try:
                event = await receive()
            except Exception as exc:
                # Only the receive operation is classified here. CancelledError
                # deliberately propagates to the outer service deadline.
                raise _RequestError(400) from exc
            if type(event) is not dict or event.get("type") != "http.request":
                raise _RequestError(400)
            chunk, more = event.get("body", b""), event.get("more_body", False)
            if type(chunk) is not bytes or type(more) is not bool:
                raise _RequestError(400)
            if len(chunks) + len(chunk) > _MAX_BODY:
                raise _RequestError(413, "REQUEST_TOO_LARGE")
            chunks.extend(chunk)
            if length is not None and len(chunks) > length:
                raise _RequestError(400)
            if not more:
                if length is not None and len(chunks) != length:
                    raise _RequestError(400)
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
