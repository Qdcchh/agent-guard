"""Real HTTPS browser/code/AS delegation and fresh gateway invocation adapter."""

from __future__ import annotations

import base64
import html
import http.cookiejar
import secrets
import ssl
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit

from tongsuopy.crypto import serialization

from agent_guard.authorization.claims import (
    GATEWAY_AUDIENCE,
    parse_scope,
    validate_access_claims,
    validate_child,
)
from agent_guard.authorization.exchange import ACCESS_TOKEN_TYPE, TOKEN_EXCHANGE_GRANT
from agent_guard.authorization.oidc import pkce_s256_challenge, verify_id_token
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.contracts.encoding import (
    b64url_decode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.crypto.sm import (
    serialize_sm2_public_key,
    sm3_b64url,
    verify_compact_jws,
)
from agent_guard.demo.config import (
    ChildToken,
    DelegationRequest,
    DemoConfigError,
    HolderConfig,
    InvocationResponse,
    RootRequest,
    RootTokens,
    SyntheticLogin,
    freeze,
    text,
)
from agent_guard.server.private_files import read_private_file


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class _Inputs(HTMLParser):
    def __init__(self, raw):
        super().__init__()
        self.values = {}
        self.feed(raw.decode("utf-8"))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input" and a.get("type") == "hidden":
            if a.get("name") in self.values:
                raise DemoConfigError("duplicate browser form input")
            self.values[a.get("name")] = html.unescape(a.get("value", ""))


class DemoClient:
    def __init__(self, role: HolderConfig):
        if (
            type(role) is not HolderConfig
            or role.role.role not in ("planner", "selector", "executor")
            or role.client_id != "agent-" + role.role.role
        ):
            raise DemoConfigError("registered holder configuration required")
        self.config = role
        self._key = serialization.load_pem_private_key(
            read_private_file(role.role.private_files["signing_key"]), password=None
        )
        if self._key.curve.name != "SM2":
            raise DemoConfigError("SM2 holder key required")
        self._secret = read_private_file(role.role.private_files["basic_secret"]).decode("ascii")
        from agent_guard.server.config import secret_sha256

        secret_sha256(self._secret)
        self._cookies = http.cookiejar.CookieJar()
        context = ssl.create_default_context(cafile=str(role.ca_file))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirect(),
            urllib.request.HTTPSHandler(context=context),
            urllib.request.HTTPCookieProcessor(self._cookies),
        )

    def _request(self, url, *, body=None, headers=None):
        p = urlsplit(url)
        if p.scheme != "https" or p.netloc not in (
            urlsplit(self.config.issuer).netloc,
            urlsplit(self.config.gateway_origin).netloc,
        ):
            raise DemoConfigError("unregistered request endpoint")
        if body is not None and len(body) > 65536:
            raise DemoConfigError("request capacity")
        request = urllib.request.Request(
            url,
            data=body,
            headers=headers or {},
            method="GET" if body is None else "POST",
        )
        try:
            response = self._opener.open(request, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise DemoConfigError("response capacity")
            return response.status, response.headers, raw

    def _local_redirect(self, location, path):
        if (
            type(location) is not str
            or not location.startswith(path)
            or location.startswith("//")
            or urlsplit(location).netloc
        ):
            raise DemoConfigError("unexpected browser redirect")
        return self.config.issuer + location

    def _token(self, form, *, purpose, token):
        endpoint = self.config.issuer + "/oauth/token"
        proof = sign_ag_proof(
            self._key,
            kid=self.config.kid,
            client_id=self.config.client_id,
            purpose=purpose,
            endpoint=endpoint,
            body=form,
            token=token,
            now=int(time.time()),
        )
        basic = base64.b64encode(
            (self.config.client_id + ":" + self._secret).encode("ascii")
        ).decode("ascii")
        status, headers, raw = self._request(
            endpoint,
            body=urlencode(form).encode("ascii"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": "Basic " + basic,
                "AG-Proof": proof,
            },
        )
        if status != 200 or headers.get_content_type() != "application/json":
            raise DemoConfigError("AS token request rejected")
        result = load_strict_json(raw)
        from agent_guard.authorization.code_service import CodeRedeemResult
        from agent_guard.authorization.exchange_service import TokenExchangeResult

        expected = CodeRedeemResult if purpose == "code-exchange" else TokenExchangeResult
        if (
            type(result) is not dict
            or set(result) != set(expected.__dataclass_fields__)
            or result["token_type"] != "AGPoP"
            or type(result["expires_in"]) is not int
            or not 1 <= result["expires_in"] <= 300
        ):
            raise DemoConfigError("token response schema rejected")
        claims = validate_access_claims(
            verify_compact_jws(
                result["access_token"],
                expected_type="ag-at+jwt",
                trusted_keys=self.config.as_keys,
            ),
            issuer=self.config.issuer,
            now=int(time.time()),
        )
        return result, claims

    def browser_root(self, *, login: SyntheticLogin, request: RootRequest) -> RootTokens:
        if (
            self.config.role.role != "planner"
            or request.task_id != self.config.task_id
            or login.tenant_id != self.config.tenant_id
        ):
            raise DemoConfigError("planner root scope required")
        self._cookies.clear()
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": request.scope,
            "state": state,
            "nonce": nonce,
            "code_challenge": pkce_s256_challenge(verifier),
            "code_challenge_method": "S256",
            "ag_task_id": request.task_id,
        }
        authorization = self.config.issuer + "/oauth/authorize?" + urlencode(params)
        status, headers, _ = self._request(authorization)
        if status != 302:
            raise DemoConfigError("login redirect required")
        login_url = self._local_redirect(headers.get("Location"), "/ag/login?")
        status, _, raw = self._request(login_url)
        inputs = _Inputs(raw).values
        if (
            status != 200
            or set(inputs) != {"csrf_token", "return_to"}
            or not inputs["return_to"].startswith("/oauth/authorize?")
        ):
            raise DemoConfigError("login CSRF form rejected")
        form = {
            **inputs,
            "tenant_id": login.tenant_id,
            "subject": login.subject,
            "password": login.password,
        }
        status, headers, _ = self._request(
            self.config.issuer + "/ag/login",
            body=urlencode(form).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if status != 303 or headers.get("Location") != inputs["return_to"]:
            raise DemoConfigError("login rejected")
        status, _, raw = self._request(authorization)
        inputs = _Inputs(raw).values
        if status != 200 or set(inputs) != {"request_id", "csrf_token"}:
            raise DemoConfigError("consent CSRF form rejected")
        status, headers, _ = self._request(
            self.config.issuer + "/ag/consent",
            body=urlencode({**inputs, "decision": "approve"}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        callback = urlsplit(headers.get("Location", ""))
        expected = urlsplit(self.config.redirect_uri)
        pairs = parse_qsl(callback.query, keep_blank_values=True)
        if (
            status != 303
            or (callback.scheme, callback.netloc, callback.path, callback.fragment)
            != (expected.scheme, expected.netloc, expected.path, "")
            or len(pairs) != 2
            or len(dict(pairs)) != 2
        ):
            raise DemoConfigError("authorization callback rejected")
        query = dict(pairs)
        if set(query) != {"state", "code"} or query["state"] != state or not query["code"]:
            raise DemoConfigError("authorization state/code rejected")
        result, claims = self._token(
            {
                "grant_type": "authorization_code",
                "code": query["code"],
                "redirect_uri": self.config.redirect_uri,
                "code_verifier": verifier,
            },
            purpose="code-exchange",
            token=None,
        )
        raw_claims = claims.raw
        if (
            raw_claims["client_id"],
            raw_claims["ag_tenant_id"],
            raw_claims["ag_task_id"],
            raw_claims["ag_parent_id"],
            raw_claims["ag_delegation_remaining"],
            raw_claims["ag_limits"],
        ) != (
            self.config.client_id,
            self.config.tenant_id,
            self.config.task_id,
            None,
            2,
            {"currency": "CNY", "amount_fen": 100000, "calls": 12},
        ):
            raise DemoConfigError("root token binding rejected")
        if raw_claims["ag_cnf"] != {
            "kid": self.config.kid,
            "spki_sm3": sm3_b64url(serialize_sm2_public_key(self._key.public_key())),
        }:
            raise DemoConfigError("root possession binding rejected")
        id_claims = verify_id_token(
            result["id_token"],
            trusted_keys=self.config.as_keys,
            issuer=self.config.issuer,
            client_id=self.config.client_id,
            expected_nonce=nonce,
            now=int(time.time()),
        )
        return RootTokens(result["access_token"], result["id_token"], freeze(id_claims))

    def exchange(self, *, parent_token: str, request: DelegationRequest) -> ChildToken:
        expected = {
            "planner": ("agent-selector", 80000, 10, 1),
            "selector": ("agent-executor", 70000, 8, 0),
        }.get(self.config.role.role)
        if (
            expected is None
            or any(
                type(v) is not int
                for v in (
                    request.amount_limit_fen,
                    request.call_limit,
                    request.delegation_remaining,
                )
            )
            or (
                request.target_client_id,
                request.amount_limit_fen,
                request.call_limit,
                request.delegation_remaining,
            )
            != expected
            or type(request.ttl_seconds) is not int
            or not 1 <= request.ttl_seconds <= 300
        ):
            raise DemoConfigError("fixed narrowing delegation required")
        constraints = load_strict_json(request.constraints)
        if canonical_json_bytes(constraints) != request.constraints:
            raise DemoConfigError("canonical delegation constraints required")
        if (
            "openid" in parse_scope(request.scope)
            or len(b64url_decode(request.delegation_key)) < 16
        ):
            raise DemoConfigError("business child scope and 128-bit delegation key required")
        form = {
            "grant_type": TOKEN_EXCHANGE_GRANT,
            "subject_token": parent_token,
            "subject_token_type": ACCESS_TOKEN_TYPE,
            "requested_token_type": ACCESS_TOKEN_TYPE,
            "audience": GATEWAY_AUDIENCE,
            "scope": request.scope,
            "ag_delegate_client_id": request.target_client_id,
            "ag_amount_limit_fen": str(request.amount_limit_fen),
            "ag_call_limit": str(request.call_limit),
            "ag_ttl_seconds": str(request.ttl_seconds),
            "ag_delegation_remaining": str(request.delegation_remaining),
            "ag_constraints": request.constraints.decode(),
            "ag_delegation_key": text(request.delegation_key),
        }
        parent_claims = validate_access_claims(
            verify_compact_jws(
                parent_token,
                expected_type="ag-at+jwt",
                trusted_keys=self.config.as_keys,
            ),
            issuer=self.config.issuer,
            now=int(time.time()),
        )
        parent = parent_claims.raw
        if (parent["client_id"], parent["ag_tenant_id"], parent["ag_task_id"]) != (
            self.config.client_id,
            self.config.tenant_id,
            self.config.task_id,
        ):
            raise DemoConfigError("delegating parent holder scope rejected")
        result, claims = self._token(form, purpose="delegate", token=parent_token)
        validate_child(parent_claims, claims)
        child = claims.raw
        if (
            child["ag_limits"]
            != {
                "currency": "CNY",
                "amount_fen": request.amount_limit_fen,
                "calls": request.call_limit,
            }
            or child["ag_constraints"] != constraints
        ):
            raise DemoConfigError("child requested policy binding rejected")
        if (
            child["client_id"],
            child["ag_tenant_id"],
            child["ag_task_id"],
            child["ag_parent_id"],
            child["ag_root_id"],
            child["ag_delegation_remaining"],
        ) != (
            request.target_client_id,
            self.config.tenant_id,
            self.config.task_id,
            parent["ag_grant_id"],
            parent["ag_root_id"],
            request.delegation_remaining,
        ):
            raise DemoConfigError("child token binding rejected")
        return ChildToken(
            result["access_token"],
            request.target_client_id,
            self.config.client_id,
            self.config.role.run_id,
            self.config.task_id,
        )

    def _gateway(self, token, body, path, purpose):
        endpoint = self.config.gateway_origin + path
        proof = sign_ag_proof(
            self._key,
            kid=self.config.kid,
            client_id=self.config.client_id,
            purpose=purpose,
            endpoint=endpoint,
            body=body,
            token=token,
            now=int(time.time()),
        )
        status, headers, raw = self._request(
            endpoint,
            body=canonical_json_bytes(body),
            headers={
                "Content-Type": "application/json",
                "Authorization": "AGPoP " + token,
                "AG-Proof": proof,
            },
        )
        if headers.get_content_type() != "application/json":
            raise DemoConfigError("gateway response media type")
        return InvocationResponse(status, raw, freeze(load_strict_json(raw)))

    def invoke(self, *, token: str, body: dict) -> InvocationResponse:
        return self._gateway(token, body, "/v1/invocations", "invoke")

    def query(self, *, token: str, operation_id: str) -> InvocationResponse:
        return self._gateway(
            token,
            {
                "profile": "GM-MVP-1",
                "task_id": self.config.task_id,
                "operation_id": text(operation_id),
            },
            "/v1/operations/query",
            "result-read",
        )
