"""Strict HTTP-boundary adapter for the two supported OAuth token grants.

The caller supplies raw header occurrences and the raw form body from a TLS
HTTP server.  This class does not provide a listener, user login, consent UI,
or a bypass for client authentication. Client secret hashes must be loaded by
the deploying service from private configuration, never from request bodies.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
from dataclasses import asdict, dataclass
from typing import Protocol
from urllib.parse import urlsplit

from agent_guard.authorization.code_service import AuthorizationCodeError, CodeRedeemResult
from agent_guard.authorization.exchange import TOKEN_EXCHANGE_GRANT
from agent_guard.authorization.exchange_service import TokenExchangeError, TokenExchangeResult
from agent_guard.authorization.forms import FormError, decode_oauth_form
from agent_guard.contracts.encoding import canonical_json_bytes

_CLIENT_ID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z", re.ASCII)
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache", "Content-Type": "application/json"}


class CodeRedeemer(Protocol):
    def redeem(
        self,
        *,
        raw_form: bytes,
        proof: str,
        authenticated_client_id: str,
        tenant_id: str,
        expected_redirect_uri: str,
    ) -> CodeRedeemResult: ...


class Exchanger(Protocol):
    def exchange(
        self, *, raw_form: bytes, proof: str, authenticated_client_id: str
    ) -> TokenExchangeResult: ...


@dataclass(frozen=True)
class TokenClient:
    """Trusted server-side client registration; hash of a high-entropy secret."""

    client_id: str
    tenant_id: str
    redirect_uri: str | None
    secret_sha256: bytes
    active: bool = True


@dataclass(frozen=True)
class TokenResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class TokenEndpoint:
    """Map one authenticated OAuth form request to AS transaction services."""

    def __init__(
        self,
        *,
        clients: dict[str, TokenClient],
        codes: CodeRedeemer,
        exchanges: Exchanger,
    ) -> None:
        if not clients or codes is None or exchanges is None:
            raise ValueError("clients and both token grant services are required")
        for key, client in clients.items():
            redirect = (
                urlsplit(client.redirect_uri)
                if isinstance(client, TokenClient) and type(client.redirect_uri) is str
                else None
            )
            if (
                not isinstance(client, TokenClient)
                or key != client.client_id
                or type(key) is not str
                or not _CLIENT_ID.fullmatch(key)
                or type(client.tenant_id) is not str
                or not _CLIENT_ID.fullmatch(client.tenant_id)
                or (
                    client.redirect_uri is not None
                    and (
                        type(client.redirect_uri) is not str
                        or redirect is None
                        or redirect.scheme != "https"
                        or not redirect.netloc
                        or redirect.username is not None
                        or redirect.password is not None
                        or redirect.fragment
                    )
                )
                or type(client.secret_sha256) is not bytes
                or len(client.secret_sha256) != 32
                or type(client.active) is not bool
            ):
                raise ValueError("invalid trusted client registration")
        self._clients = dict(clients)
        self._codes = codes
        self._exchanges = exchanges

    def handle(
        self,
        *,
        content_type: str,
        raw_form: bytes,
        authorization_headers: tuple[str, ...],
        proof_headers: tuple[str, ...],
    ) -> TokenResponse:
        """Reject duplicate credentials and return a no-store OAuth response.

        Raw header occurrences, not a lossy name-to-value dictionary, are
        required so duplicate Authorization/AG-Proof lines cannot be merged.
        The surrounding HTTP server must enforce TLS and request-size limits.
        """
        client = self._authenticate(authorization_headers)
        if client is None:
            return self._error(
                401,
                "invalid_client",
                "CLIENT_AUTH_FAILED",
                challenge='Basic realm="agent-guard"',
            )
        if (
            type(content_type) is not str
            or content_type.lower()
            not in (
                "application/x-www-form-urlencoded",
                "application/x-www-form-urlencoded; charset=utf-8",
            )
            or type(proof_headers) is not tuple
            or len(proof_headers) != 1
        ):
            return self._error(400, "invalid_request", "REQUEST_INVALID")
        proof = proof_headers[0]
        if type(proof) is not str or not proof or len(proof) > 8192:
            return self._error(400, "invalid_request", "PROOF_INVALID")
        try:
            form = decode_oauth_form(raw_form)
        except FormError:
            return self._error(400, "invalid_request", "REQUEST_INVALID")
        grant_type = form.get("grant_type")
        try:
            if grant_type == "authorization_code":
                if client.redirect_uri is None:
                    return self._error(400, "invalid_grant", "CLIENT_GRANT_DENIED")
                result = self._codes.redeem(
                    raw_form=raw_form,
                    proof=proof,
                    authenticated_client_id=client.client_id,
                    tenant_id=client.tenant_id,
                    expected_redirect_uri=client.redirect_uri,
                )
            elif grant_type == TOKEN_EXCHANGE_GRANT:
                result = self._exchanges.exchange(
                    raw_form=raw_form,
                    proof=proof,
                    authenticated_client_id=client.client_id,
                )
            else:
                return self._error(400, "unsupported_grant_type", "GRANT_UNSUPPORTED")
        except AuthorizationCodeError as exc:
            if exc.code == "TRUSTED_STATE_UNAVAILABLE":
                return self._error(503, "temporarily_unavailable", exc.code)
            return self._error(400, "invalid_grant", exc.code)
        except TokenExchangeError as exc:
            if exc.code == "TRUSTED_STATE_UNAVAILABLE":
                return self._error(503, "temporarily_unavailable", exc.code)
            return self._error(400, "invalid_request", exc.code)
        return TokenResponse(200, dict(_NO_STORE), canonical_json_bytes(asdict(result)))

    def _authenticate(self, headers: tuple[str, ...]) -> TokenClient | None:
        if type(headers) is not tuple or len(headers) != 1:
            return None
        header = headers[0]
        if type(header) is not str or header[:6].lower() != "basic ":
            return None
        value = header[6:]
        if not value or len(value) > 2048 or not value.isascii():
            return None
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            return None
        if base64.b64encode(decoded).decode("ascii") != value or b":" not in decoded:
            return None
        raw_client_id, secret = decoded.split(b":", 1)
        try:
            client_id = raw_client_id.decode("ascii")
        except UnicodeDecodeError:
            return None
        if not _CLIENT_ID.fullmatch(client_id) or not secret:
            return None
        client = self._clients.get(client_id)
        expected = client.secret_sha256 if client is not None else b"\x00" * 32
        matched = hmac.compare_digest(hashlib.sha256(secret).digest(), expected)
        return client if matched and client is not None and client.active else None

    @staticmethod
    def _error(
        status: int, error: str, ag_error: str, *, challenge: str | None = None
    ) -> TokenResponse:
        headers = dict(_NO_STORE)
        if challenge is not None:
            headers["WWW-Authenticate"] = challenge
        return TokenResponse(
            status, headers, canonical_json_bytes({"error": error, "ag_error": ag_error})
        )
