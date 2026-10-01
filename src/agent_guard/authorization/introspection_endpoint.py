"""Strict HTTP-boundary adapter for gateway-only OAuth introspection.

The caller supplies raw headers and form bytes from a TLS server.  This is
not a network listener and does not authorize tool execution.
"""

from __future__ import annotations

from typing import Protocol

from agent_guard.authorization.forms import FormError, decode_oauth_form
from agent_guard.authorization.introspection import IntrospectionError, IntrospectionResult
from agent_guard.authorization.token_endpoint import (
    TokenClient,
    TokenResponse,
    authenticate_basic,
)
from agent_guard.contracts.encoding import canonical_json_bytes

_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache", "Content-Type": "application/json"}


class Inspector(Protocol):
    def inspect(self, token: str) -> IntrospectionResult: ...


class IntrospectionEndpoint:
    """Accept exactly one independently authenticated gateway service."""

    def __init__(self, *, gateway_client: TokenClient, inspector: Inspector) -> None:
        if (
            not isinstance(gateway_client, TokenClient)
            or not gateway_client.client_id
            or gateway_client.redirect_uri is not None
            or type(gateway_client.secret_sha256) is not bytes
            or len(gateway_client.secret_sha256) != 32
            or type(gateway_client.active) is not bool
            or inspector is None
        ):
            raise ValueError("trusted gateway service and inspector required")
        self._clients = {gateway_client.client_id: gateway_client}
        self._inspector = inspector

    def handle(
        self,
        *,
        content_type: str,
        raw_form: bytes,
        authorization_headers: tuple[str, ...],
    ) -> TokenResponse:
        if authenticate_basic(authorization_headers, self._clients) is None:
            return self._error(401, "invalid_client", challenge=True)
        if type(content_type) is not str or content_type.lower() not in (
            "application/x-www-form-urlencoded",
            "application/x-www-form-urlencoded; charset=utf-8",
        ):
            return self._error(400, "invalid_request")
        try:
            form = decode_oauth_form(raw_form)
        except FormError:
            return self._error(400, "invalid_request")
        if set(form) != {"token", "token_type_hint"} or form["token_type_hint"] != "access_token":
            return self._error(400, "invalid_request")
        try:
            result = self._inspector.inspect(form["token"])
        except IntrospectionError:
            return self._error(503, "temporarily_unavailable")
        return TokenResponse(200, dict(_NO_STORE), canonical_json_bytes(result.response()))

    @staticmethod
    def _error(status: int, error: str, *, challenge: bool = False) -> TokenResponse:
        headers = dict(_NO_STORE)
        if challenge:
            headers["WWW-Authenticate"] = 'Basic realm="agent-guard-gateway"'
        return TokenResponse(status, headers, canonical_json_bytes({"error": error}))
