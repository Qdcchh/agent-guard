"""Real PG-backed ASGI boundary refusal, legal controls and failure mapping.

Only synthetic test-owned namespaces are used. State comparisons hash every row
of every table so diagnostic failures do not emit raw token/session evidence.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import psycopg
import pytest
from psycopg import sql

from agent_guard.authorization.discovery import DiscoveryEndpoint
from agent_guard.authorization.exchange_service import TokenExchangeService
from agent_guard.authorization.grant_revocation_service import GrantRevocationService
from agent_guard.authorization.http_app import AuthorizationHttpApp
from agent_guard.authorization.introspection import IntrospectionService
from agent_guard.authorization.introspection_endpoint import IntrospectionEndpoint
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.authorization.provisioning import grant_tenant_admin
from agent_guard.authorization.revocation_http import RevocationHttpApp
from agent_guard.authorization.revocation_service import TaskRevocationService
from agent_guard.authorization.token_endpoint import TokenClient, TokenEndpoint
from agent_guard.contracts.encoding import load_strict_json
from agent_guard.server.middleware import RequestTimeoutMiddleware
from tests.integration.test_consent_final_decision import _wait_blocked
from tests.integration.test_login_consent import (
    ISSUER,
    KID,
    PASSWORD,
    REDIRECT,
    SUBJECT,
    TENANT,
    TOKEN_ENDPOINT,
    VERIFIER,
    _params,
    _session,
    _setup,
)
from tests.test_http_request_limits import invoke, media, scope_for

pytestmark = pytest.mark.integration
CLIENT_SECRET = b"synthetic-only-http-client-secret-32-bytes"
GATEWAY_SECRET = b"synthetic-only-http-gateway-secret-32-bytes"
KINDS = ("login", "authorize", "consent", "token", "introspection", "task", "grant")
REASON = b'{"reason_code":"USER_CANCELLED"}'


def _basic(client, secret):
    return b"Basic " + base64.b64encode(client.encode() + b":" + secret)


def _stack(dsn):
    s = _setup(dsn)
    exchanges = TokenExchangeService(
        dsn,
        issuer=ISSUER,
        token_endpoint=TOKEN_ENDPOINT,
        signing_key=s.as_key,
        signing_kid="as-sign-1",
        identities=s.codes._identities,
    )
    inspector = IntrospectionService(
        dsn,
        issuer=ISSUER,
        as_keys={"as-sign-1": s.as_key.public_key()},
        identities=s.codes._identities,
    )
    tasks, grants = TaskRevocationService(dsn), GrantRevocationService(dsn)
    app = AuthorizationHttpApp(
        discovery=DiscoveryEndpoint(
            issuer=ISSUER, signing_keys={"as-sign-1": s.as_key.public_key()}
        ),
        token=TokenEndpoint(
            clients={
                "agent-planner": TokenClient(
                    "agent-planner", TENANT, REDIRECT, hashlib.sha256(CLIENT_SECRET).digest()
                )
            },
            codes=s.codes,
            exchanges=exchanges,
        ),
        introspection=IntrospectionEndpoint(
            gateway_client=TokenClient(
                "gateway-introspect", "service", None, hashlib.sha256(GATEWAY_SECRET).digest()
            ),
            inspector=inspector,
        ),
        browser=s.browser,
        revocation=RevocationHttpApp(sessions=s.login, tasks=tasks, grants=grants),
    )
    return SimpleNamespace(
        app=app, s=s, exchanges=exchanges, inspector=inspector, tasks=tasks, grants=grants, dsn=dsn
    )


def _state(dsn):
    with psycopg.connect(dsn) as conn:
        names = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema=current_schema() AND table_type='BASE TABLE' "
            "ORDER BY table_name"
        ).fetchall()
        result = {}
        for (name,) in names:
            rows = conn.execute(
                sql.SQL("SELECT row_to_json(t)::text FROM {} AS t").format(sql.Identifier(name))
            ).fetchall()
            hashes = sorted(hashlib.sha256(row[0].encode()).hexdigest() for row in rows)
            result[name] = (len(rows), hashlib.sha256("\n".join(hashes).encode()).hexdigest())
        assert "ag_authorization_codes" in result and "ag_operations" in result
        return result


def _send(ctx, path, body=b"", *, headers=None, events=None, method="POST", query=b""):
    if events is None:
        events = [{"type": "http.request", "body": body}]
    return asyncio.run(invoke(ctx.app, scope_for(path, method, headers, query), events))


def _session_headers(session):
    return [(b"cookie", f"ag_session={session.session_token}~{session.csrf_token}".encode())]


def _code_request(ctx, session):
    view = ctx.s.consent.create_request(
        session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
    )
    redirect = ctx.s.consent.decide(
        session_token=session.session_token,
        csrf_token=session.csrf_token,
        request_id=view.request_id,
        decision="approve",
    )
    code = parse_qs(urlsplit(redirect.location).query)["code"][0]
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "code_verifier": VERIFIER,
    }
    proof = sign_ag_proof(
        ctx.s.planner_key,
        kid=KID,
        client_id="agent-planner",
        purpose="code-exchange",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=None,
        now=int(time.time()),
    )
    return urlencode(form).encode(), [
        (b"content-type", media("/oauth/token")),
        (b"authorization", _basic("agent-planner", CLIENT_SECRET)),
        (b"ag-proof", proof.encode()),
    ]


def _valid(ctx, kind):
    if kind == "login":
        csrf = ctx.s.login.issue_login_csrf()
        body = urlencode(
            {
                "tenant_id": TENANT,
                "subject": SUBJECT,
                "password": PASSWORD,
                "csrf_token": csrf,
                "return_to": "/",
            }
        ).encode()
        return (
            "/ag/login",
            body,
            [(b"content-type", media("/ag/login")), (b"cookie", f"ag_login_csrf={csrf}".encode())],
            303,
        )
    session = _session(ctx.s)
    if kind == "authorize":
        return (
            "/oauth/authorize",
            urlencode(_params()).encode(),
            [(b"content-type", media("/oauth/authorize")), *_session_headers(session)],
            200,
        )
    if kind == "consent":
        view = ctx.s.consent.create_request(
            session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
        )
        return (
            "/ag/consent",
            urlencode(
                {
                    "request_id": view.request_id,
                    "decision": "approve",
                    "csrf_token": session.csrf_token,
                }
            ).encode(),
            [(b"content-type", media("/ag/consent")), *_session_headers(session)],
            303,
        )
    body, headers = _code_request(ctx, session)
    if kind == "token":
        return "/oauth/token", body, headers, 200
    status, data, _ = _send(ctx, "/oauth/token", body, headers=headers)
    assert status == 200
    issued = load_strict_json(data)
    if kind == "introspection":
        return (
            "/oauth/introspect",
            urlencode(
                {"token": issued["access_token"], "token_type_hint": "access_token"}
            ).encode(),
            [
                (b"content-type", media("/oauth/introspect")),
                (b"authorization", _basic("gateway-introspect", GATEWAY_SECRET)),
            ],
            200,
        )
    if kind == "grant":
        with psycopg.connect(ctx.dsn) as conn:
            grant_tenant_admin(conn, tenant_id=TENANT, subject=SUBJECT)
    path = (
        "/ag/tasks/task-001/revoke"
        if kind == "task"
        else (f"/ag/grants/{issued['ag_grant_id']}/revoke")
    )
    return (
        path,
        REASON,
        [
            (b"content-type", b"application/json"),
            *_session_headers(session),
            (b"x-csrf-token", session.csrf_token.encode()),
        ],
        200,
    )


def _refused(status, body, expected):
    assert status == expected
    assert b"synthetic" not in body and PASSWORD.encode() not in body
    assert CLIENT_SECRET not in body and GATEWAY_SECRET not in body
    assert b"secret-token-marker" not in body


@pytest.mark.parametrize("kind", KINDS)
def test_real_services_reject_transport_before_effects_with_positive_control(ledger, dsn, kind):
    ctx = _stack(dsn)
    path, valid, headers, success = _valid(ctx, kind)
    before = _state(dsn)
    # Every transport failure is tried against otherwise valid authenticated input.
    cases = [
        (b"x" * 65537, headers, None, 413),
        (valid, [], None, 415),
        (valid, [(b"content-type", b"text/plain"), *headers[1:]], None, 415),
        (valid, [*headers, headers[0]], None, 400),
        (valid, [*headers, (b"content-length", b"1")], None, 400),
        (
            valid,
            headers,
            [
                {"type": "http.request", "body": b"x" * 65536, "more_body": True},
                {"type": "http.request", "body": b"x"},
            ],
            413,
        ),
        (
            valid,
            headers,
            [
                {"type": "http.request", "body": valid[:3], "more_body": True},
                {"type": "http.disconnect"},
            ],
            400,
        ),
        (valid, headers, [{"type": "http.request", "body": "secret-token-marker"}], 400),
        (valid, headers, [{"type": "http.request", "body": valid, "more_body": 1}], 400),
    ]
    for body, supplied, events, expected in cases:
        status, error, _ = _send(ctx, path, body, headers=supplied, events=events)
        _refused(status, error, expected)
        assert _state(dsn) == before
    for method, query, expected in [("PUT", b"", 405), ("POST", b"secret=token", 400)]:
        status, error, _ = _send(ctx, path, valid, headers=headers, method=method, query=query)
        _refused(status, error, expected)
        assert _state(dsn) == before
    status, body, _ = _send(ctx, path, valid, headers=headers)
    assert status == success
    if kind == "introspection":
        assert load_strict_json(body)["active"] is True
        assert _state(dsn) == before
    else:
        assert _state(dsn) != before
    print(f"HTTP_PG_CONTROL route={kind} transport_refusals=11 positive={success}")


@pytest.mark.parametrize("kind", KINDS)
def test_real_malformed_and_unknown_fields_have_no_effects(ledger, dsn, kind):
    ctx = _stack(dsn)
    path, valid, headers, _ = _valid(ctx, kind)
    before = _state(dsn)
    if kind in {"task", "grant"}:
        malformed = [
            b'{"reason_code":"USER_CANCELLED","role":"admin"}',
            b'{"reason_code":"USER_CANCELLED","reason_code":"USER_CANCELLED"}',
            b'{"reason_code":true}',
            b"[]",
            b'{"reason_code":"\\ud800"}',
            b'{"reason_code":' + b"1" * 5000 + b"}",
            b"[" * 1500 + b"]" * 1500,
        ]
    else:
        malformed = [
            valid + b"&role=admin",
            valid + b"&" + valid.split(b"&")[0],
            b"x=%ZZ",
            b"x=%FF",
            b"x=%ED%A0%80",
            b"no-separator",
        ]
    for body in malformed:
        status, error, _ = _send(ctx, path, body, headers=headers)
        _refused(status, error, 400)
        assert _state(dsn) == before


@pytest.mark.parametrize("kind", ["task", "grant"])
@pytest.mark.parametrize("chunked", [False, True])
def test_real_legal_json_body_65536_revokes_with_valid_session(ledger, dsn, kind, chunked):
    ctx = _stack(dsn)
    path, _, headers, _ = _valid(ctx, kind)
    body = REASON + b" " * (65536 - len(REASON))
    events = (
        None
        if not chunked
        else [
            {"type": "http.request", "body": body[:32768], "more_body": True},
            {"type": "http.request", "body": body[32768:]},
        ]
    )
    status, data, _ = _send(ctx, path, body, headers=headers, events=events)
    assert status == 200
    assert load_strict_json(data)["scope"] == "SUBTREE"
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT bool_and(revoked) FROM ag_grants").fetchone() == (True,)
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (0,)


@pytest.mark.parametrize(
    "kind",
    ["login", "authorize", "consent", "token", "introspection", "task", "grant", "login-get"],
)
def test_real_postgresql_connection_refusal_is_503_and_state_preserved(
    ledger, dsn, kind, monkeypatch
):
    ctx = _stack(dsn)
    if kind == "login-get":
        path, valid, headers, method = "/ag/login", b"", [], "GET"
    else:
        path, valid, headers, _ = _valid(ctx, kind)
        method = "POST"
    before = _state(dsn)
    witnessed = []

    def unavailable(*args, **kwargs):
        # Actual server-backed failure, not an exception-only fake. This verified
        # owner cannot connect to a nonexistent database in its isolated cluster.
        try:
            return psycopg.connect(dsn, dbname="br_s2_missing_database", connect_timeout=2)
        except psycopg.OperationalError as exc:
            witnessed.append(type(exc).__name__)
            raise

    for service in (
        ctx.s.login,
        ctx.s.consent,
        ctx.s.codes,
        ctx.exchanges,
        ctx.inspector,
        ctx.tasks,
        ctx.grants,
    ):
        monkeypatch.setattr(service, "_connector", unavailable)
    status, body, _ = _send(ctx, path, valid, headers=headers, method=method)
    _refused(status, body, 503)
    assert witnessed == ["OperationalError"]
    assert _state(dsn) == before


@pytest.mark.parametrize(
    "kind", ["login", "authorize", "consent", "token", "introspection", "task", "grant"]
)
@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_real_adapter_internal_failure_is_500_without_secret_disclosure(
    ledger, dsn, kind, error_type, monkeypatch
):
    ctx = _stack(dsn)
    path, valid, headers, _ = _valid(ctx, kind)
    before = _state(dsn)
    target, name = {
        "login": (ctx.s.login, "login"),
        "authorize": (ctx.s.consent, "create_request"),
        "consent": (ctx.s.consent, "decide"),
        "token": (ctx.s.codes, "redeem"),
        "introspection": (ctx.inspector, "inspect"),
        "task": (ctx.tasks, "revoke_task"),
        "grant": (ctx.grants, "revoke_grant"),
    }[kind]
    calls = []

    def broken(**kwargs):
        calls.append(True)
        raise error_type("secret-token-marker")

    if kind == "introspection":

        def broken(token):
            calls.append(True)
            raise error_type("secret-token-marker")

    monkeypatch.setattr(target, name, broken)
    status, body, _ = _send(ctx, path, valid, headers=headers)
    assert status == 500 and body == b'{"error":"INTERNAL_ERROR"}'
    assert calls == [True]
    assert _state(dsn) == before


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("fault", ["lock-timeout", "terminated-backend", "positive"])
def test_actual_consent_wait_failures_are_503_and_atomic(ledger, dsn, round_id, fault, monkeypatch):
    ctx = _stack(dsn)
    path, valid, headers, _ = _valid(ctx, "consent")
    before = _state(dsn)
    original_connect = ctx.s.consent._connect
    observed = []

    class WitnessConnection(psycopg.Connection):
        def execute(self, query, params=None, **kwargs):
            try:
                return super().execute(query, params, **kwargs)
            except psycopg.Error as exc:
                observed.append(exc.sqlstate)
                raise

    def connection():
        conn = WitnessConnection.connect(dsn)
        conn.execute("SET lock_timeout='500ms'")
        conn.execute("SET statement_timeout='3000ms'")
        return conn

    monkeypatch.setattr(ctx.s.consent, "_connect", connection)
    with psycopg.connect(dsn, autocommit=True) as observer, psycopg.connect(dsn) as blocker:
        blocker.execute("SELECT * FROM ag_authorization_requests FOR UPDATE")
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(_send, ctx, path, valid, headers=headers)
            pid = _wait_blocked(
                observer, blocker.info.backend_pid, "FROM ag_authorization_requests"
            )
            if fault == "terminated-backend":
                assert observer.execute("SELECT pg_terminate_backend(%s)", (pid,)).fetchone() == (
                    True,
                )
            elif fault == "positive":
                blocker.commit()
            status, body, _ = future.result(timeout=5)
            blocker.rollback()
    if fault == "positive":
        assert status == 303 and observed == []
        assert _state(dsn) != before
    else:
        _refused(status, body, 503)
        assert observed == ["55P03" if fault == "lock-timeout" else "57P01"]
        assert _state(dsn) == before
        # Successful retry proves a genuinely usable consent was refused atomically.
        monkeypatch.setattr(ctx.s.consent, "_connect", original_connect)
        assert _send(ctx, path, valid, headers=headers)[0] == 303
    print(f"HTTP_DB_WITNESS round={round_id} kind={fault} sqlstates={observed}")


def test_real_stalled_body_outer_503_has_no_predispatch_effects(ledger, dsn):
    ctx = _stack(dsn)
    path, _, headers, _ = _valid(ctx, "login")
    before = _state(dsn)
    sent = []

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        sent.append(message)

    asyncio.run(
        RequestTimeoutMiddleware(ctx.app, timeout_seconds=1)(
            scope_for(path, headers=headers), receive, send
        )
    )
    assert sent[0]["status"] == 503 and sent[1]["body"] == b'{"error":"TIMEOUT"}'
    assert _state(dsn) == before


@pytest.mark.parametrize("kind", KINDS)
def test_http_authentication_and_ambiguous_security_inputs_still_refuse(ledger, dsn, kind):
    ctx = _stack(dsn)
    path, valid, headers, success = _valid(ctx, kind)
    before = _state(dsn)
    if kind in {"token", "introspection"}:
        credential = next(h for h in headers if h[0] == b"authorization")
        denied = [
            ([h for h in headers if h[0] != b"authorization"], 401),
            ([*headers, credential], 401),
        ]
        if kind == "token":
            denied.append(([*headers, next(h for h in headers if h[0] == b"ag-proof")], 400))
    else:
        cookie = next(h for h in headers if h[0] == b"cookie")
        denied = [([*headers, cookie], 400)]
        if kind in {"task", "grant"}:
            csrf = next(h for h in headers if h[0] == b"x-csrf-token")
            denied += [
                ([*headers, csrf], 400),
                ([h for h in headers if h[0] != b"x-csrf-token"], 401),
            ]
    for supplied, expected in denied:
        status, body, response_headers = _send(ctx, path, valid, headers=supplied)
        _refused(status, body, expected)
        if expected == 401 and kind in {"token", "introspection"}:
            assert any(
                k == b"www-authenticate" and v.startswith(b"Basic ") for k, v in response_headers
            )
        assert _state(dsn) == before
    assert _send(ctx, path, valid, headers=headers)[0] == success


def test_get_browser_queries_reject_malformed_before_creating_csrf_or_request(ledger, dsn):
    ctx = _stack(dsn)
    session = _session(ctx.s)
    before = _state(dsn)
    for path in ("/ag/login", "/oauth/authorize"):
        for query in (b"x=%ZZ", b"x=1&x=2", b"x=%ED%A0%80"):
            status, body, _ = _send(
                ctx, path, method="GET", query=query, headers=_session_headers(session)
            )
            _refused(status, body, 400)
            assert _state(dsn) == before
    status, _, _ = _send(
        ctx,
        "/oauth/authorize",
        method="GET",
        query=urlencode(_params()).encode(),
        headers=_session_headers(session),
    )
    assert status == 200 and _state(dsn) != before
