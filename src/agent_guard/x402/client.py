"""Bounded HTTP client for the fixed loopback x402 resource server.

Only the two configured loopback URLs are ever contacted. There is no URL
taken from a 402 body, no redirect following, no proxy support and no
unbounded response: every request and response is strictly parsed and the
payment headers are decoded by :mod:`agent_guard.x402.wire`.
"""

from __future__ import annotations

import http.client
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from agent_guard.x402 import wire
from agent_guard.x402.contracts import X402Error

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_HEADER_VALUE = 16 * 1024
_OPERATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class HttpResponse:
    """One fully read, bounded HTTP response."""

    status: int
    headers: dict[str, str]
    body: bytes

    def header(self, name: str) -> bytes | None:
        value = self.headers.get(name.lower())
        if value is None:
            return None
        try:
            raw = value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise X402Error(f"invalid {name} header", code="INVALID_HTTP_RESPONSE") from exc
        if not 1 <= len(raw) <= MAX_HEADER_VALUE:
            raise X402Error(f"invalid {name} header", code="INVALID_HTTP_RESPONSE")
        return raw


class X402HttpClient:
    """The only network path from the payer/worker to the resource server."""

    def __init__(self, *, resource_url: str, timeout_seconds: int = 15):
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
            raise X402Error("invalid HTTP timeout", code="CONFIG_INVALID")
        if not 1 <= timeout_seconds <= 120:
            raise X402Error("invalid HTTP timeout", code="CONFIG_INVALID")
        parsed = urlsplit(resource_url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1", "localhost"):
            raise X402Error(
                "x402 client requires a loopback HTTP endpoint", code="CONFIG_NOT_LOOPBACK"
            )
        if parsed.username or parsed.password or parsed.fragment or parsed.query:
            raise X402Error("invalid resource URL", code="CONFIG_INVALID")
        self._host = parsed.hostname
        self._port = parsed.port
        self._path = parsed.path
        if self._path != "/v1/x402/resource/order-create":
            raise X402Error("unexpected resource endpoint", code="CONFIG_INVALID")
        self._timeout = timeout_seconds

    def order_create(self, *, operation_id: str, payment_header: bytes | None) -> HttpResponse:
        """POST the fixed order-create resource with an optional payment header."""
        if not isinstance(operation_id, str) or _OPERATION_PATTERN.fullmatch(operation_id) is None:
            raise X402Error("invalid operation id header", code="INVALID_OPERATION_ID")
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "ag-operation-id": operation_id,
            "connection": "close",
        }
        if payment_header is not None:
            if not isinstance(payment_header, bytes) or not 1 <= len(payment_header) <= 65536:
                raise X402Error("invalid payment header", code="INVALID_PAYMENT_HEADER")
            try:
                headers["payment-signature"] = payment_header.decode("ascii")
            except UnicodeDecodeError as exc:
                raise X402Error("invalid payment header", code="INVALID_PAYMENT_HEADER") from exc
        body = b"{}"
        connection = http.client.HTTPConnection(self._host, self._port, timeout=self._timeout)
        try:
            connection.request("POST", self._path, body=body, headers=headers)
            response = connection.getresponse()
            status = int(response.status)
            if 300 <= status < 400:
                raise X402Error("x402 resource must not redirect", code="INVALID_HTTP_RESPONSE")
            declared = response.getheader("content-length")
            if declared is not None:
                try:
                    length = int(declared)
                except ValueError as exc:
                    raise X402Error("invalid content length", code="INVALID_HTTP_RESPONSE") from exc
                if length < 0 or length > MAX_RESPONSE_BYTES:
                    raise X402Error("x402 response too large", code="INVALID_HTTP_RESPONSE")
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise X402Error("x402 response too large", code="INVALID_HTTP_RESPONSE")
            response_headers = {}
            for name, value in response.getheaders():
                key = name.strip().lower()
                if key in response_headers:
                    raise X402Error("duplicate HTTP response header", code="INVALID_HTTP_RESPONSE")
                if len(value) > MAX_HEADER_VALUE:
                    raise X402Error("invalid HTTP response header", code="INVALID_HTTP_RESPONSE")
                response_headers[key] = value.strip()
            return HttpResponse(status=status, headers=response_headers, body=payload)
        except X402Error:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise X402Error("x402 resource unreachable", code="RESOURCE_UNREACHABLE") from exc
        finally:
            connection.close()

    def payment_required(self, response: HttpResponse) -> dict:
        if response.status != 402:
            raise X402Error("expected a 402 challenge", code="INVALID_HTTP_RESPONSE")
        header = response.header("PAYMENT-REQUIRED")
        if header is None:
            raise X402Error("missing PAYMENT-REQUIRED header", code="INVALID_HTTP_RESPONSE")
        return wire.parse_payment_required(header)

    def settlement(self, response: HttpResponse) -> dict:
        header = response.header("PAYMENT-RESPONSE")
        if header is None:
            raise X402Error("missing PAYMENT-RESPONSE header", code="INVALID_HTTP_RESPONSE")
        return wire.parse_payment_response(header)


def encode_payment_header(document: bytes) -> bytes:
    """Canonical base64 PAYMENT-SIGNATURE header for persisted payload bytes."""
    return wire.encode_header(document)
