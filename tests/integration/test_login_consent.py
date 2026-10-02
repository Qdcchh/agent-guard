"""Real PostgreSQL login, authorization-request, consent and code issuance.

The full browser boundary is driven through :class:`BrowserLoginApp` as well as
the trusted service API, so the tests cover cookie handling, session binding,
CSRF, policy validation, deny handling and the unique-root boundary.
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import psycopg
import pytest

from agent_guard.authorization.browser import BrowserLoginApp
from agent_guard.authorization.code_service import (
    AuthorizationCodeError,
    AuthorizationCodeService,
)
from agent_guard.authorization.consent import (
    AuthorizeClient,
    ConsentError,
    ConsentService,
)
from agent_guard.authorization.login import LoginError, LoginService
from agent_guard.authorization.oidc import pkce_s256_challenge, verify_id_token
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.authorization.provisioning import register_task_policy, register_user
from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from agent_guard.crypto.sm import (
    generate_sm2_private_key,
    serialize_sm2_public_key,
    verify_compact_jws,
)
from agent_guard.identity.resolver import (
    METHOD_TYPE,
    SPKI_PROPERTY,
    IdentityResolver,
    RegisteredIdentity,
)
from agent_guard.ledger.provisioning import register_principal
from tests.fixtures.dbstate import fetch_all, fetch_one

pytestmark = pytest.mark.integration

ISSUER = "https://auth.agent-guard.test"
TOKEN_ENDPOINT = ISSUER + "/oauth/token"
REDIRECT = "https://console.agent-guard.test/oauth/callback"
DID = "did:web:identity.agent-guard.test:agents:planner"
KID = DID + "#key-1"
TENANT = "tenant-001"
SUBJECT = "user-001"
PASSWORD = "synthetic-test-only-password"
VERIFIER = "A" * 43
CONSTRAINTS = {
    "request_ids": ["req-001"],
    "document_ids": ["doc-001"],
    "quote_versions": ["quote-001@1"],
    "skus": ["sku-001"],
    "max_quantity": 2,
    "delivery_ids": ["office-001"],
    "template_ids": [],
    "recipient_ids": [],
}


class Stack:
    __slots__ = ("codes", "login", "consent", "browser", "planner_key", "as_key")

    def __init__(self, codes, login, consent, browser, planner_key, as_key):
        self.codes = codes
        self.login = login
        self.consent = consent
        self.browser = browser
        self.planner_key = planner_key
        self.as_key = as_key


def _params(verifier=VERIFIER, **overrides):
    base = {
        "response_type": "code",
        "client_id": "agent-planner",
        "redirect_uri": REDIRECT,
        "scope": "openid procurement.order.create",
        "state": "state-value-123456",
        "nonce": b64url_encode(secrets.token_bytes(16)),
        "code_challenge": pkce_s256_challenge(verifier),
        "code_challenge_method": "S256",
        "ag_task_id": "task-001",
    }
    base.update(overrides)
    return base


def _setup(dsn, *, policy_owner=SUBJECT, active=True, task="task-001", expiry_delta=600):
    as_key = generate_sm2_private_key()
    planner_key = generate_sm2_private_key()
    spki = serialize_sm2_public_key(planner_key.public_key())
    document = {
        "id": DID,
        "verificationMethod": [
            {"id": KID, "type": METHOD_TYPE, "controller": DID, SPKI_PROPERTY: b64url_encode(spki)}
        ],
        "authentication": [KID],
        "capabilityInvocation": [KID],
        "capabilityDelegation": [KID],
    }
    registration = RegisteredIdentity(TENANT, "agent-planner", DID, KID, spki)
    resolver = IdentityResolver(
        {("tenant-001", "agent-planner"): registration},
        allowed_hosts=frozenset({"identity.agent-guard.test"}),
        fetch_document=lambda url: canonical_json_bytes(document),
    )
    codes = AuthorizationCodeService(
        dsn,
        issuer=ISSUER,
        token_endpoint=TOKEN_ENDPOINT,
        signing_key=as_key,
        signing_kid="as-sign-1",
        identities=resolver,
    )
    login = LoginService(dsn)
    consent = ConsentService(
        dsn,
        clients={"agent-planner": AuthorizeClient("agent-planner", TENANT, REDIRECT)},
        sessions=login,
        codes=codes,
    )
    browser = BrowserLoginApp(login=login, consent=consent)
    with psycopg.connect(dsn) as conn:
        register_principal(conn, tenant_id=TENANT, client_id="agent-planner", kid=KID)
        register_user(conn, tenant_id=TENANT, subject=SUBJECT, password=PASSWORD, active=active)
        register_task_policy(
            conn,
            tenant_id=TENANT,
            task_id=task,
            owner_subject=policy_owner,
            scope="openid procurement.order.create",
            constraints=CONSTRAINTS,
            amount_limit_fen=100000,
            call_limit=10,
            task_expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=expiry_delta),
        )
    return Stack(codes, login, consent, browser, planner_key, as_key)


def _session(stack):
    csrf = stack.login.issue_login_csrf()
    result = stack.login.login(
        login_csrf=csrf,
        csrf_cookie=csrf,
        tenant_id=TENANT,
        subject=SUBJECT,
        password=PASSWORD,
    )
    return result


def _approve(stack, session, *, params=None):
    params = params if params is not None else _params()
    request = stack.consent.create_request(
        session_token=session.session_token,
        csrf_token=session.csrf_token,
        params=params,
    )
    redirect = stack.consent.decide(
        session_token=session.session_token,
        csrf_token=session.csrf_token,
        request_id=request.request_id,
        decision="approve",
    )
    return redirect, params


def _code_from(location: str) -> str:
    match = re.search(r"[?&]code=([^&]+)", location)
    assert match is not None, location
    return match.group(1)


def _redeem(stack, code, verifier=VERIFIER):
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "code_verifier": verifier,
    }
    proof = sign_ag_proof(
        stack.planner_key,
        kid=KID,
        client_id="agent-planner",
        purpose="code-exchange",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=None,
        now=int(time.time()),
    )
    return stack.codes.redeem(
        raw_form=urlencode(form).encode("ascii"),
        proof=proof,
        authenticated_client_id="agent-planner",
        tenant_id=TENANT,
        expected_redirect_uri=REDIRECT,
    )


def _cookie_value(set_cookie: str, name: str) -> str:
    for part in set_cookie.split(","):
        segment = part.strip().split(";", 1)[0]
        key, _, value = segment.partition("=")
        if key.strip() == name:
            return value
    raise AssertionError(f"{name} not in {set_cookie!r}")


def test_full_login_authorize_consent_and_redeem(ledger, dsn):
    stack = _setup(dsn)
    session = _session(stack)
    assert fetch_one(dsn, "SELECT password_hash FROM ag_users")[0].startswith("scrypt$")
    assert PASSWORD not in fetch_one(dsn, "SELECT password_hash FROM ag_users")[0]

    redirect, params = _approve(stack, session)
    code = _code_from(redirect.location)
    issued = _redeem(stack, code)
    claims = verify_compact_jws(
        issued.access_token,
        expected_type="ag-at+jwt",
        trusted_keys={"as-sign-1": stack.as_key.public_key()},
    )
    assert claims["ag_grant_id"] == issued.ag_grant_id
    assert claims["ag_parent_id"] is None
    assert (
        verify_id_token(
            issued.id_token,
            trusted_keys={"as-sign-1": stack.as_key.public_key()},
            issuer=ISSUER,
            client_id="agent-planner",
            expected_nonce=params["nonce"],
            now=int(time.time()),
        )["sub"]
        == SUBJECT
    )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_tasks") == (1,)
    assert fetch_one(dsn, "SELECT status FROM ag_authorization_requests") == ("approved",)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_auth_events") == (3,)
    with pytest.raises(AuthorizationCodeError, match="CODE_OR_PKCE_INVALID"):
        _redeem(stack, code)


def test_login_rejections_do_not_create_sessions(ledger, dsn):
    stack = _setup(dsn)
    with pytest.raises(LoginError, match="INVALID_CREDENTIALS"):
        csrf = stack.login.issue_login_csrf()
        stack.login.login(
            login_csrf=csrf,
            csrf_cookie=csrf,
            tenant_id=TENANT,
            subject=SUBJECT,
            password="wrong-password",
        )
    with pytest.raises(LoginError, match="INVALID_CREDENTIALS"):
        csrf = stack.login.issue_login_csrf()
        stack.login.login(
            login_csrf=csrf,
            csrf_cookie=csrf,
            tenant_id=TENANT,
            subject="nobody",
            password=PASSWORD,
        )
    csrf = stack.login.issue_login_csrf()
    stack.login.login(
        login_csrf=csrf, csrf_cookie=csrf, tenant_id=TENANT, subject=SUBJECT, password=PASSWORD
    )
    with pytest.raises(LoginError, match="INVALID_CREDENTIALS"):
        stack.login.login(
            login_csrf=csrf, csrf_cookie=csrf, tenant_id=TENANT, subject=SUBJECT, password=PASSWORD
        )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_login_sessions") == (1,)


def test_inactive_user_cannot_login(ledger, dsn):
    stack = _setup(dsn, active=False)
    csrf = stack.login.issue_login_csrf()
    with pytest.raises(LoginError, match="INVALID_CREDENTIALS"):
        stack.login.login(
            login_csrf=csrf, csrf_cookie=csrf, tenant_id=TENANT, subject=SUBJECT, password=PASSWORD
        )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_login_sessions") == (0,)


def test_authorize_request_rejections(ledger, dsn):
    stack = _setup(dsn)
    session = _session(stack)
    for overrides, code in (
        ({"redirect_uri": "https://evil.example/callback"}, "REDIRECT_INVALID"),
        ({"scope": "openid notification.template.send"}, "SCOPE_DENIED"),
        ({"scope": "procurement.order.create"}, "SCOPE_DENIED"),
    ):
        with pytest.raises(ConsentError, match=code):
            stack.consent.create_request(
                session_token=session.session_token,
                csrf_token=session.csrf_token,
                params={**_params(), **overrides},
            )
    with pytest.raises(ConsentError, match="TASK_NOT_FOUND"):
        stack.consent.create_request(
            session_token=session.session_token,
            csrf_token=session.csrf_token,
            params={**_params(), "ag_task_id": "task-missing"},
        )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_authorization_requests") == (0,)


def test_task_owner_boundary_denies_other_subjects(ledger, dsn):
    stack = _setup(dsn, policy_owner="someone-else")
    session = _session(stack)
    with pytest.raises(ConsentError, match="NOT_TASK_OWNER"):
        stack.consent.create_request(
            session_token=session.session_token,
            csrf_token=session.csrf_token,
            params=_params(),
        )


def test_consent_csrf_deny_duplicate_and_expiry(ledger, dsn):
    stack = _setup(dsn)
    session = _session(stack)
    request = stack.consent.create_request(
        session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
    )
    with pytest.raises(LoginError, match="CSRF_INVALID"):
        stack.consent.decide(
            session_token=session.session_token,
            csrf_token="wrong-csrf-token-value-123456",
            request_id=request.request_id,
            decision="approve",
        )
    denied = stack.consent.decide(
        session_token=session.session_token,
        csrf_token=session.csrf_token,
        request_id=request.request_id,
        decision="deny",
    )
    assert "error=access_denied" in denied.location
    assert fetch_one(dsn, "SELECT status FROM ag_authorization_requests") == ("denied",)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_authorization_codes") == (0,)
    with pytest.raises(ConsentError, match="ALREADY_DECIDED"):
        stack.consent.decide(
            session_token=session.session_token,
            csrf_token=session.csrf_token,
            request_id=request.request_id,
            decision="approve",
        )

    expired = stack.consent.create_request(
        session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
    )
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "UPDATE ag_authorization_requests SET created_at = clock_timestamp() - interval '10 s',"
            " expires_at = clock_timestamp() - interval '1 s' WHERE request_id = %s",
            (expired.request_id,),
        )
    with pytest.raises(ConsentError, match="REQUEST_EXPIRED"):
        stack.consent.decide(
            session_token=session.session_token,
            csrf_token=session.csrf_token,
            request_id=expired.request_id,
            decision="approve",
        )


def test_two_authorizations_for_one_task_create_one_root(ledger, dsn):
    stack = _setup(dsn)
    session = _session(stack)
    first, _ = _approve(stack, session)
    second, _ = _approve(stack, session)
    first_code = _code_from(first.location)
    second_code = _code_from(second.location)
    _redeem(stack, first_code)
    with pytest.raises(AuthorizationCodeError, match="TASK_ALREADY_AUTHORIZED"):
        _redeem(stack, second_code)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_tasks") == (1,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (1,)


def test_existing_root_rejects_new_consent_without_marking_approved(ledger, dsn):
    stack = _setup(dsn)
    session = _session(stack)
    redirect, _ = _approve(stack, session)
    _redeem(stack, _code_from(redirect.location))
    request = stack.consent.create_request(
        session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
    )
    with pytest.raises(ConsentError, match="TASK_ALREADY_AUTHORIZED"):
        stack.consent.decide(
            session_token=session.session_token,
            csrf_token=session.csrf_token,
            request_id=request.request_id,
            decision="approve",
        )
    assert fetch_one(
        dsn,
        "SELECT status FROM ag_authorization_requests WHERE request_id = %s",
        (request.request_id,),
    ) == ("pending",)


@pytest.mark.parametrize(
    "change",
    [
        "amount_limit_fen = 200000",
        "call_limit = 20",
        "scope = 'openid procurement.order.create procurement.document.read'",
        "task_expires_at = task_expires_at + interval '1 hour'",
        "constraints_json = %s",
    ],
)
def test_policy_change_after_display_fails_closed(ledger, dsn, change):
    stack = _setup(dsn)
    session = _session(stack)
    request = stack.consent.create_request(
        session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
    )
    with psycopg.connect(dsn) as conn:
        changed_constraints = {**CONSTRAINTS, "skus": ["sku-001", "sku-002"]}
        values = (canonical_json_bytes(changed_constraints),) if "%s" in change else ()
        conn.execute(
            f"UPDATE ag_task_policies SET {change} WHERE tenant_id = %s AND task_id = %s",
            (*values, TENANT, "task-001"),
        )
    with pytest.raises(ConsentError, match="TASK_POLICY_CHANGED"):
        stack.consent.decide(
            session_token=session.session_token,
            csrf_token=session.csrf_token,
            request_id=request.request_id,
            decision="approve",
        )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_authorization_codes") == (0,)
    assert fetch_one(dsn, "SELECT status, consent_ref FROM ag_authorization_requests") == (
        "pending",
        None,
    )


def test_code_and_consent_rollback_together(ledger, dsn, monkeypatch):
    stack = _setup(dsn)
    session = _session(stack)
    request = stack.consent.create_request(
        session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
    )
    original_issue = stack.codes.issue_code

    def issue_then_fail(approved, *, conn):
        assert conn is not None
        original_issue(approved, conn=conn)
        raise psycopg.OperationalError("synthetic failure after code insert")

    monkeypatch.setattr(stack.codes, "issue_code", issue_then_fail)
    with pytest.raises(ConsentError, match="TRUSTED_STATE_UNAVAILABLE"):
        stack.consent.decide(
            session_token=session.session_token,
            csrf_token=session.csrf_token,
            request_id=request.request_id,
            decision="approve",
        )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_authorization_codes") == (0,)
    assert fetch_one(dsn, "SELECT status, consent_ref FROM ag_authorization_requests") == (
        "pending",
        None,
    )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_auth_events WHERE event_type = 'consent'") == (
        0,
    )


@pytest.mark.parametrize("fault_after", ["event", "mark"])
def test_consent_partial_writes_rollback(ledger, dsn, monkeypatch, fault_after):
    stack = _setup(dsn)
    session = _session(stack)
    request = stack.consent.create_request(
        session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
    )
    if fault_after == "event":
        original = stack.consent._insert_event

        def insert_then_fail(conn, **kwargs):
            original(conn, **kwargs)
            raise psycopg.OperationalError("synthetic failure after consent event")

        monkeypatch.setattr(stack.consent, "_insert_event", insert_then_fail)
    else:
        original = stack.consent._mark_decided

        def mark_then_fail(conn, *args):
            original(conn, *args)
            raise psycopg.OperationalError("synthetic failure after request update")

        monkeypatch.setattr(stack.consent, "_mark_decided", mark_then_fail)
    with pytest.raises(ConsentError, match="TRUSTED_STATE_UNAVAILABLE"):
        stack.consent.decide(
            session_token=session.session_token,
            csrf_token=session.csrf_token,
            request_id=request.request_id,
            decision="approve",
        )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_authorization_codes") == (0,)
    assert fetch_one(dsn, "SELECT status, consent_ref FROM ag_authorization_requests") == (
        "pending",
        None,
    )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_auth_events WHERE event_type = 'consent'") == (
        0,
    )


def test_policy_change_then_restore_still_requires_new_consent(ledger, dsn):
    stack = _setup(dsn)
    session = _session(stack)
    request = stack.consent.create_request(
        session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
    )
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "UPDATE ag_task_policies SET amount_limit_fen = 900000 "
            "WHERE tenant_id = %s AND task_id = %s",
            (TENANT, "task-001"),
        )
        conn.execute(
            "UPDATE ag_task_policies SET amount_limit_fen = 100000 "
            "WHERE tenant_id = %s AND task_id = %s",
            (TENANT, "task-001"),
        )
    assert fetch_one(dsn, "SELECT policy_version FROM ag_task_policies") == (3,)
    with pytest.raises(ConsentError, match="TASK_POLICY_CHANGED"):
        stack.consent.decide(
            session_token=session.session_token,
            csrf_token=session.csrf_token,
            request_id=request.request_id,
            decision="approve",
        )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_authorization_codes") == (0,)


def test_legacy_pending_request_without_policy_snapshot_fails_closed(ledger, dsn):
    stack = _setup(dsn)
    session = _session(stack)
    request = stack.consent.create_request(
        session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
    )
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "UPDATE ag_authorization_requests SET policy_snapshot_json = NULL "
            "WHERE request_id = %s",
            (request.request_id,),
        )
    with pytest.raises(ConsentError, match="TASK_POLICY_CHANGED"):
        stack.consent.decide(
            session_token=session.session_token,
            csrf_token=session.csrf_token,
            request_id=request.request_id,
            decision="approve",
        )
    assert fetch_one(dsn, "SELECT count(*) FROM ag_authorization_codes") == (0,)


def test_consent_rechecks_request_expiry_after_lock_wait(ledger, dsn, monkeypatch):
    stack = _setup(dsn)
    session = _session(stack)
    request = stack.consent.create_request(
        session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
    )
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "UPDATE ag_authorization_requests "
            "SET expires_at = clock_timestamp() + interval '2 seconds' "
            "WHERE request_id = %s",
            (request.request_id,),
        )
    prechecked = threading.Event()
    original_verify = stack.login.verify_session_csrf

    def signal_precheck(**kwargs):
        result = original_verify(**kwargs)
        prechecked.set()
        return result

    monkeypatch.setattr(stack.login, "verify_session_csrf", signal_precheck)
    with ThreadPoolExecutor(max_workers=1) as workers:
        with psycopg.connect(dsn) as blocker:
            with blocker.transaction():
                blocker.execute(
                    "SELECT 1 FROM ag_authorization_requests WHERE request_id = %s FOR UPDATE",
                    (request.request_id,),
                )
                result = workers.submit(
                    stack.consent.decide,
                    session_token=session.session_token,
                    csrf_token=session.csrf_token,
                    request_id=request.request_id,
                    decision="approve",
                )
                assert prechecked.wait(5)
                time.sleep(2.2)
        with pytest.raises(ConsentError, match="REQUEST_EXPIRED"):
            result.result(timeout=5)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_authorization_codes") == (0,)


@pytest.mark.parametrize("state_change", ["revoke_session", "disable_user"])
def test_consent_rechecks_session_after_lock_wait(ledger, dsn, monkeypatch, state_change):
    stack = _setup(dsn)
    session = _session(stack)
    request = stack.consent.create_request(
        session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
    )
    prechecked = threading.Event()
    original_verify = stack.login.verify_session_csrf

    def signal_precheck(**kwargs):
        result = original_verify(**kwargs)
        prechecked.set()
        return result

    monkeypatch.setattr(stack.login, "verify_session_csrf", signal_precheck)
    session_hash = fetch_one(dsn, "SELECT session_sha256 FROM ag_login_sessions")[0]
    with ThreadPoolExecutor(max_workers=1) as workers:
        with psycopg.connect(dsn) as blocker:
            with blocker.transaction():
                blocker.execute(
                    "SELECT 1 FROM ag_authorization_requests WHERE request_id = %s FOR UPDATE",
                    (request.request_id,),
                )
                result = workers.submit(
                    stack.consent.decide,
                    session_token=session.session_token,
                    csrf_token=session.csrf_token,
                    request_id=request.request_id,
                    decision="approve",
                )
                assert prechecked.wait(5)
                with psycopg.connect(dsn) as conn:
                    if state_change == "revoke_session":
                        conn.execute(
                            "UPDATE ag_login_sessions SET revoked_at = clock_timestamp() "
                            "WHERE session_sha256 = %s",
                            (session_hash,),
                        )
                    else:
                        conn.execute(
                            "UPDATE ag_users SET active = false "
                            "WHERE tenant_id = %s AND subject = %s",
                            (TENANT, SUBJECT),
                        )
        with pytest.raises(ConsentError, match="SESSION_INVALID"):
            result.result(timeout=5)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_authorization_codes") == (0,)
    assert fetch_one(dsn, "SELECT status FROM ag_authorization_requests") == ("pending",)


def test_browser_app_full_flow_over_http_boundary(ledger, dsn):
    stack = _setup(dsn)
    login_page = stack.browser.dispatch(
        method="GET", path="/ag/login", query_string=b"", headers=[], body=b""
    )
    assert login_page.status == 200
    login_csrf = _cookie_value(login_page.headers["Set-Cookie"], "ag_login_csrf")

    logged_in = stack.browser.dispatch(
        method="POST",
        path="/ag/login",
        query_string=b"",
        headers=[(b"cookie", f"ag_login_csrf={login_csrf}".encode())],
        body=urlencode(
            {
                "tenant_id": TENANT,
                "subject": SUBJECT,
                "password": PASSWORD,
                "csrf_token": login_csrf,
                "return_to": "/dashboard",
            }
        ).encode(),
    )
    assert logged_in.status == 303
    session_cookie = _cookie_value(logged_in.headers["Set-Cookie"], "ag_session")

    consent_page = stack.browser.dispatch(
        method="GET",
        path="/oauth/authorize",
        query_string=urlencode(_params()).encode(),
        headers=[(b"cookie", f"ag_session={session_cookie}".encode())],
        body=b"",
    )
    assert consent_page.status == 200
    assert b"Constraints:" in consent_page.body
    assert b"sku-001" in consent_page.body
    assert b"Expires (Unix time):" in consent_page.body
    assert b"Delegation depth: 2; policy version: 1" in consent_page.body
    request_id = re.search(rb'name="request_id" value="([^"]+)"', consent_page.body).group(1)
    csrf = re.search(rb'name="csrf_token" value="([^"]+)"', consent_page.body).group(1)
    assert csrf.decode() == session_cookie.split("~", 1)[1]

    decided = stack.browser.dispatch(
        method="POST",
        path="/ag/consent",
        query_string=b"",
        headers=[(b"cookie", f"ag_session={session_cookie}".encode())],
        body=urlencode(
            {
                "request_id": request_id.decode(),
                "decision": "approve",
                "csrf_token": csrf.decode(),
            }
        ).encode(),
    )
    assert decided.status == 303
    assert _redeem(stack, _code_from(decided.headers["Location"])).token_type == "AGPoP"

    events = fetch_all(dsn, "SELECT event_type FROM ag_auth_events ORDER BY created_at")
    assert {row[0] for row in events} == {"login", "authorize_request", "consent"}
