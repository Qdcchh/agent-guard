"""Post-wait decisions with real row/advisory locks and ten independent rounds."""

from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from agent_guard.authorization.consent import ConsentError
from agent_guard.authorization.login import LoginError
from tests.integration.test_login_consent import (
    PASSWORD,
    SUBJECT,
    TENANT,
    _params,
    _session,
    _setup,
)

pytestmark = pytest.mark.integration


def _wait_blocked(conn, blocker_pid, query_fragment):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        rows = conn.execute(
            "SELECT pid, wait_event_type, pg_blocking_pids(pid) FROM pg_stat_activity "
            "WHERE datname=current_database() AND pid<>pg_backend_pid() "
            "AND query LIKE %s AND wait_event_type='Lock'",
            ("%" + query_fragment + "%",),
        ).fetchall()
        hits = [r for r in rows if blocker_pid in r[2]]
        if hits:
            assert hits[0][0] != blocker_pid
            print(f"LOCK_WITNESS blocker={blocker_pid} waiter={hits[0][0]} target={query_fragment}")
            return hits[0][0]
        time.sleep(0.01)
    raise AssertionError("target SQL never reached the real blocking lock")


def _wait_expired(conn, deadline):
    while conn.execute("SELECT clock_timestamp() < %s", (deadline,)).fetchone()[0]:
        time.sleep(0.01)
    observed = conn.execute("SELECT clock_timestamp()").fetchone()[0]
    print(f"EXPIRY_WITNESS deadline={deadline.isoformat()} db_now={observed.isoformat()}")


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("expiry", ["request", "session"])
@pytest.mark.parametrize("positive", [False, True])
def test_policy_lock_final_expiry(ledger, dsn, round_id, expiry, positive):
    stack = _setup(dsn)
    session = _session(stack)
    request = stack.consent.create_request(
        session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
    )
    with psycopg.connect(dsn, autocommit=True) as observer:
        table = "ag_authorization_requests" if expiry == "request" else "ag_login_sessions"
        deadline = observer.execute(
            f"UPDATE {table} SET expires_at=clock_timestamp()+"
            "interval '0.4 seconds' RETURNING expires_at"
        ).fetchone()[0]
        before_events = observer.execute("SELECT count(*) FROM ag_auth_events").fetchone()[0]
        with psycopg.connect(dsn) as blocker, ThreadPoolExecutor(1) as pool:
            blocker_pid = blocker.info.backend_pid
            blocker.execute("SELECT * FROM ag_task_policies FOR UPDATE")
            future = pool.submit(
                stack.consent.decide,
                session_token=session.session_token,
                csrf_token=session.csrf_token,
                request_id=request.request_id,
                decision="approve",
            )
            worker_pid = _wait_blocked(observer, blocker_pid, "FROM ag_task_policies")
            assert worker_pid != observer.info.backend_pid
            if not positive:
                _wait_expired(observer, deadline)
            blocker.commit()
            if positive:
                assert "code=" in future.result(timeout=5).location
            else:
                with pytest.raises(ConsentError) as failure:
                    future.result(timeout=5)
                assert failure.value.code in {"REQUEST_EXPIRED", "SESSION_INVALID"}
        status = observer.execute("SELECT status FROM ag_authorization_requests").fetchone()[0]
        assert status == ("approved" if positive else "pending")
        assert observer.execute("SELECT count(*) FROM ag_authorization_codes").fetchone()[0] == int(
            positive
        )
        assert observer.execute("SELECT count(*) FROM ag_auth_events").fetchone()[
            0
        ] == before_events + int(positive)


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("positive", [False, True])
def test_login_csrf_lock_expiry(ledger, dsn, round_id, positive):
    stack = _setup(dsn)
    csrf = stack.login.issue_login_csrf()
    digest = hashlib.sha256(csrf.encode()).digest()
    with psycopg.connect(dsn, autocommit=True) as observer:
        deadline = observer.execute(
            (
                "UPDATE ag_login_csrf SET expires_at=clock_timestamp()+interval "
                "'0.4 seconds' RETURNING expires_at"
            )
        ).fetchone()[0]
        with psycopg.connect(dsn) as blocker, ThreadPoolExecutor(1) as pool:
            blocker.execute(
                "SELECT * FROM ag_login_csrf WHERE token_sha256=%s FOR UPDATE", (digest,)
            )
            future = pool.submit(
                stack.login.login,
                login_csrf=csrf,
                csrf_cookie=csrf,
                tenant_id=TENANT,
                subject=SUBJECT,
                password=PASSWORD,
            )
            _wait_blocked(observer, blocker.info.backend_pid, "FROM ag_login_csrf")
            if not positive:
                _wait_expired(observer, deadline)
            blocker.commit()
            if positive:
                assert future.result(timeout=5).session_token
            else:
                with pytest.raises(LoginError, match="INVALID_CREDENTIALS"):
                    future.result(timeout=5)
        assert observer.execute("SELECT count(*) FROM ag_login_sessions").fetchone()[0] == int(
            positive
        )
        assert observer.execute("SELECT count(*) FROM ag_auth_events").fetchone()[0] == int(
            positive
        )
        assert (
            observer.execute("SELECT used_at FROM ag_login_csrf").fetchone()[0] is not None
        ) == positive


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("mode", ["did", "code-write", "deferred"])
@pytest.mark.parametrize("expiry", ["request", "session"])
@pytest.mark.parametrize("positive", [False, True])
def test_final_consent_after_late_dependencies(
    ledger, dsn, monkeypatch, round_id, mode, expiry, positive
):
    import threading

    from psycopg import sql

    stack = _setup(dsn)
    session = _session(stack)
    request = stack.consent.create_request(
        session_token=session.session_token, csrf_token=session.csrf_token, params=_params()
    )
    entered, released = threading.Event(), threading.Event()
    table = "ag_authorization_requests" if expiry == "request" else "ag_login_sessions"
    key = 8172613
    with psycopg.connect(dsn, autocommit=True) as observer:
        deadline = observer.execute(
            sql.SQL(
                "UPDATE {} SET expires_at=clock_timestamp()+"
                "interval '0.4 seconds' RETURNING expires_at"
            ).format(sql.Identifier(table))
        ).fetchone()[0]
        before_events = observer.execute("SELECT count(*) FROM ag_auth_events").fetchone()[0]
        if mode == "did":
            original = stack.codes._identities._fetch_document

            def delayed(url):
                entered.set()
                assert released.wait(5), "DID wait was not released"
                return original(url)

            monkeypatch.setattr(stack.codes._identities, "_fetch_document", delayed)
            target = None
        else:
            target = "ag_authorization_codes" if mode == "code-write" else "ag_auth_events"
            observer.execute(
                "CREATE FUNCTION ag_test_consent_wait() RETURNS trigger AS $$ "
                f"BEGIN PERFORM pg_advisory_xact_lock({key}); RETURN NEW; END $$ LANGUAGE plpgsql"
            )
            trigger = "CREATE CONSTRAINT TRIGGER" if mode == "deferred" else "CREATE TRIGGER"
            deferred = "DEFERRABLE INITIALLY DEFERRED" if mode == "deferred" else ""
            observer.execute(
                f"{trigger} ag_test_consent_wait_trg AFTER INSERT ON {target} "
                f"{deferred} FOR EACH ROW EXECUTE FUNCTION ag_test_consent_wait()"
            )
        try:
            with psycopg.connect(dsn) as blocker, ThreadPoolExecutor(1) as pool:
                blocker.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
                future = pool.submit(
                    stack.consent.decide,
                    session_token=session.session_token,
                    csrf_token=session.csrf_token,
                    request_id=request.request_id,
                    decision="approve",
                )
                if mode == "did":
                    assert entered.wait(5)
                else:
                    fragment = (
                        "INSERT INTO ag_authorization_codes"
                        if mode == "code-write"
                        else "SET CONSTRAINTS ALL IMMEDIATE"
                    )
                    _wait_blocked(observer, blocker.info.backend_pid, fragment)
                if not positive:
                    _wait_expired(observer, deadline)
                blocker.commit()
                released.set()
                if positive:
                    assert "code=" in future.result(timeout=5).location
                else:
                    with pytest.raises(ConsentError) as failure:
                        future.result(timeout=5)
                    assert failure.value.code in {"SESSION_INVALID", "REQUEST_EXPIRED"}
        finally:
            released.set()
            if target:
                observer.execute(f"DROP TRIGGER ag_test_consent_wait_trg ON {target}")
                observer.execute("DROP FUNCTION ag_test_consent_wait()")
        assert observer.execute("SELECT status FROM ag_authorization_requests").fetchone()[0] == (
            "approved" if positive else "pending"
        )
        assert observer.execute("SELECT count(*) FROM ag_authorization_codes").fetchone()[0] == int(
            positive
        )
        assert observer.execute("SELECT count(*) FROM ag_auth_events").fetchone()[
            0
        ] == before_events + int(positive)
