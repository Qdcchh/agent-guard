"""Real PostgreSQL tests for AS-owned child issuance and idempotent retries."""

from __future__ import annotations

import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import psycopg
import pytest

from agent_guard.authorization.code_service import (
    ApprovedAuthorization,
    AuthorizationCodeError,
    AuthorizationCodeService,
)
from agent_guard.authorization.exchange_service import TokenExchangeError, TokenExchangeService
from agent_guard.authorization.oidc import pkce_s256_challenge
from agent_guard.authorization.proof import sign_ag_proof
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
    did_web_url,
)
from agent_guard.ledger import store
from agent_guard.ledger.provisioning import deactivate_principal, register_principal, revoke_grant
from tests.fixtures.dbstate import fetch_one

pytestmark = pytest.mark.integration

ISSUER = "https://auth.agent-guard.test"
TOKEN_ENDPOINT = ISSUER + "/oauth/token"
REDIRECT = "https://console.agent-guard.test/oauth/callback"
VERIFIER = "A" * 43
TENANT = "tenant-001"
TASK = "task-001"


def _resolver(registrations):
    """Rebuild the DID-document resolver for already registered identities."""
    documents = {}
    for registration in registrations.values():
        name = registration.client_id.removeprefix("agent-")
        document = {
            "id": registration.did,
            "verificationMethod": [
                {
                    "id": registration.kid,
                    "type": METHOD_TYPE,
                    "controller": registration.did,
                    SPKI_PROPERTY: b64url_encode(registration.spki_der),
                }
            ],
            "authentication": [registration.kid],
            "capabilityInvocation": [registration.kid],
        }
        if name != "executor":
            document["capabilityDelegation"] = [registration.kid]
        documents[did_web_url(registration.did)] = document
    return IdentityResolver(
        registrations,
        allowed_hosts=frozenset({"identity.agent-guard.test"}),
        fetch_document=lambda url: canonical_json_bytes(documents[url]),
    )


def _identities():
    keys = {name: generate_sm2_private_key() for name in ("planner", "selector", "executor")}
    registrations = {}
    for name, key in keys.items():
        did = f"did:web:identity.agent-guard.test:agents:{name}"
        kid = did + "#key-1"
        spki = serialize_sm2_public_key(key.public_key())
        registrations[(TENANT, f"agent-{name}")] = RegisteredIdentity(
            TENANT, f"agent-{name}", did, kid, spki
        )
    return keys, registrations, _resolver(registrations)


def _root(dsn, *, approved_overrides=None):
    as_key = generate_sm2_private_key()
    keys, registrations, resolver = _identities()
    with psycopg.connect(dsn) as conn:
        for registration in registrations.values():
            register_principal(
                conn, tenant_id=TENANT, client_id=registration.client_id, kid=registration.kid
            )
    codes = AuthorizationCodeService(
        dsn,
        issuer=ISSUER,
        token_endpoint=TOKEN_ENDPOINT,
        signing_key=as_key,
        signing_kid="as-sign-1",
        identities=resolver,
    )
    exchanges = TokenExchangeService(
        dsn,
        issuer=ISSUER,
        token_endpoint=TOKEN_ENDPOINT,
        signing_key=as_key,
        signing_kid="as-sign-1",
        identities=resolver,
    )
    now = int(time.time())
    approved = ApprovedAuthorization(
        tenant_id=TENANT,
        task_id=TASK,
        subject="user-001",
        client_id="agent-planner",
        redirect_uri=REDIRECT,
        pkce_challenge=pkce_s256_challenge(VERIFIER),
        scope="openid procurement.order.create",
        constraints={
            "request_ids": ["req-001"],
            "document_ids": [],
            "quote_versions": ["quote-001@1"],
            "skus": ["sku-001"],
            "max_quantity": 2,
            "delivery_ids": ["office-001"],
            "template_ids": [],
            "recipient_ids": [],
        },
        amount_limit_fen=100000,
        call_limit=10,
        task_expires_at=now + 240,
        auth_time=now - 10,
        nonce=secrets.token_urlsafe(16),
        consent_ref="consent-001",
    )
    if approved_overrides:
        from dataclasses import replace

        approved = replace(approved, **approved_overrides)
    code = codes.issue_code(approved).code
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "code_verifier": VERIFIER,
    }
    planner = registrations[(TENANT, "agent-planner")]
    proof = sign_ag_proof(
        keys["planner"],
        kid=planner.kid,
        client_id="agent-planner",
        purpose="code-exchange",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=None,
        now=int(time.time()),
    )
    root = codes.redeem(
        raw_form=urlencode(form).encode("ascii"),
        proof=proof,
        authenticated_client_id="agent-planner",
        tenant_id=TENANT,
        expected_redirect_uri=REDIRECT,
    )
    return as_key, keys, registrations, exchanges, root


def _form(as_key, token, *, recipient="selector", delegation_key=None, ttl=180):
    parent = verify_compact_jws(
        token, expected_type="ag-at+jwt", trusted_keys={"as-sign-1": as_key.public_key()}
    )
    return {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "audience": "https://gateway.agent-guard.test",
        "scope": "procurement.order.create",
        "ag_delegate_client_id": f"agent-{recipient}",
        "ag_amount_limit_fen": "80000" if recipient == "selector" else "70000",
        "ag_call_limit": "8" if recipient == "selector" else "7",
        "ag_ttl_seconds": str(ttl),
        "ag_delegation_remaining": str(parent["ag_delegation_remaining"] - 1),
        "ag_constraints": canonical_json_bytes(parent["ag_constraints"]).decode("utf-8"),
        "ag_delegation_key": delegation_key or secrets.token_urlsafe(16),
    }


def _exchange(service, keys, registrations, form, *, holder="planner", proof=None):
    registration = registrations[(TENANT, f"agent-{holder}")]
    if proof is None:
        proof = sign_ag_proof(
            keys[holder],
            kid=registration.kid,
            client_id=f"agent-{holder}",
            purpose="delegate",
            endpoint=TOKEN_ENDPOINT,
            body=form,
            token=form["subject_token"],
            now=int(time.time()),
        )
    return service.exchange(
        raw_form=urlencode(form).encode("ascii"),
        proof=proof,
        authenticated_client_id=f"agent-{holder}",
    )


def test_two_levels_are_as_signed_and_idempotent(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    first_form = _form(as_key, root.access_token)
    first = _exchange(service, keys, registrations, first_form)
    retry = _exchange(service, keys, registrations, first_form)
    assert retry.access_token == first.access_token
    assert retry.ag_grant_id == first.ag_grant_id
    assert retry.expires_in <= first.expires_in
    second = _exchange(
        service,
        keys,
        registrations,
        _form(as_key, first.access_token, recipient="executor", ttl=100),
        holder="selector",
    )
    claims = verify_compact_jws(
        second.access_token,
        expected_type="ag-at+jwt",
        trusted_keys={"as-sign-1": as_key.public_key()},
    )
    assert claims["ag_parent_id"] == first.ag_grant_id
    assert claims["ag_root_id"] == root.ag_grant_id
    assert claims["ag_delegation_remaining"] == 0
    assert claims["client_id"] == "agent-executor"
    assert claims["act"]["act"]["act"]["sub"].endswith(":planner")
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (3,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grant_tokens") == (3,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (2,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_exchange_evidence") == (3,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_proofs") == (4,)


def test_conflicting_intent_and_stolen_token_are_rejected(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    _exchange(service, keys, registrations, form)
    changed = dict(form, ag_amount_limit_fen="70000")
    with pytest.raises(TokenExchangeError, match="DELEGATION_KEY_CONFLICT"):
        _exchange(service, keys, registrations, changed)
    with pytest.raises(TokenExchangeError, match="SUBJECT_OR_PROOF_INVALID"):
        _exchange(service, keys, registrations, form, holder="selector")
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (1,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_proofs") == (2,)


def test_first_issuance_rejects_expansion_and_revoked_parent(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    expanded = dict(form, ag_amount_limit_fen="100001")
    with pytest.raises(TokenExchangeError, match="DELEGATION_INVALID"):
        _exchange(service, keys, registrations, expanded)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (0,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_proofs") == (1,)
    with psycopg.connect(dsn) as conn:
        revoke_grant(conn, root.ag_grant_id)
    with pytest.raises(TokenExchangeError, match="REVOKED"):
        _exchange(service, keys, registrations, form)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (1,)


def test_proof_replay_is_distinct_from_delegation_retry(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    registration = registrations[(TENANT, "agent-planner")]
    proof = sign_ag_proof(
        keys["planner"],
        kid=registration.kid,
        client_id="agent-planner",
        purpose="delegate",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=root.access_token,
        now=int(time.time()),
    )
    _exchange(service, keys, registrations, form, proof=proof)
    with pytest.raises(TokenExchangeError, match="PROOF_REPLAY"):
        _exchange(service, keys, registrations, form, proof=proof)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (1,)


def test_revocation_and_key_deactivation_block_retries(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    first = _exchange(service, keys, registrations, form)
    with psycopg.connect(dsn) as conn:
        revoke_grant(conn, first.ag_grant_id)
    with pytest.raises(TokenExchangeError, match="CHILD_INACTIVE"):
        _exchange(service, keys, registrations, form)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (2,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_exchange_evidence") == (1,)
    with psycopg.connect(dsn) as conn:
        deactivate_principal(
            conn,
            tenant_id=TENANT,
            client_id="agent-selector",
            kid=registrations[(TENANT, "agent-selector")].kid,
        )
    with pytest.raises(TokenExchangeError, match="CLIENT_KEY_INVALID"):
        _exchange(service, keys, registrations, form)


def test_concurrent_same_key_returns_one_child(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_exchange, service, keys, registrations, form) for _ in range(2)]
        results = [future.result() for future in futures]
    assert results[0].access_token == results[1].access_token
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (2,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (1,)


def test_expired_child_cannot_be_revived_by_retry(ledger, dsn):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token, ttl=2)
    issued = _exchange(service, keys, registrations, form)
    payload = verify_compact_jws(
        issued.access_token,
        expected_type="ag-at+jwt",
        trusted_keys={"as-sign-1": as_key.public_key()},
    )
    time.sleep(max(0, payload["exp"] - time.time() + 0.2))
    with pytest.raises(TokenExchangeError, match="CHILD_INACTIVE"):
        _exchange(service, keys, registrations, form)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (2,)


def test_proof_expiring_while_waiting_for_task_lock_is_rejected(ledger, dsn, monkeypatch):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    issued_at = int(time.time())
    proof = sign_ag_proof(
        keys["planner"],
        kid=registrations[(TENANT, "agent-planner")].kid,
        client_id="agent-planner",
        purpose="delegate",
        endpoint=TOKEN_ENDPOINT,
        body=form,
        token=root.access_token,
        now=issued_at,
        lifetime_seconds=5,
    )
    waiting = threading.Event()
    original_lock_task = store.lock_task

    def observed_lock_task(conn, tenant_id, task_id):
        waiting.set()
        return original_lock_task(conn, tenant_id, task_id)

    monkeypatch.setattr(store, "lock_task", observed_lock_task)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with psycopg.connect(dsn) as blocker:
            with blocker.transaction():
                blocker.execute(
                    "SELECT root_grant_id FROM ag_tasks WHERE tenant_id = %s AND task_id = %s "
                    "FOR UPDATE",
                    (TENANT, TASK),
                )
                future = pool.submit(_exchange, service, keys, registrations, form, proof=proof)
                assert waiting.wait(timeout=5), "exchange did not reach task lock"
                time.sleep(max(0, issued_at + 5 - time.time() + 0.2))
        with pytest.raises(TokenExchangeError, match="PROOF_EXPIRED"):
            future.result()
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (0,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_proofs") == (1,)


def locked_race(dsn, first, second):
    """Prove two distinct real backends wait at the shared principal lock."""
    with psycopg.connect(dsn) as blocker, psycopg.connect(dsn, autocommit=True) as observer:
        blocker.execute("SELECT * FROM ag_principals ORDER BY tenant_id,client_id,kid FOR UPDATE")
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(first), pool.submit(second)]
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    rows = observer.execute(
                        "SELECT pid,query,wait_event_type,pg_blocking_pids(pid) "
                        "FROM pg_stat_activity WHERE datname=current_database() "
                        "AND wait_event_type='Lock' AND query LIKE %s",
                        ("%FROM ag_principals%",),
                    ).fetchall()
                    if len(rows) == 2:
                        assert len({row[0] for row in rows}) == 2
                        assert all("ag_principals" in row[1] and row[2] == "Lock" for row in rows)
                        # PostgreSQL can queue the second tuple waiter behind
                        # the first. Verify the full wait graph reaches the
                        # owned blocker rather than assuming both direct edges.
                        graph = {row[0]: row[3] for row in rows}
                        print(
                            f"RACE_WITNESS blocker={blocker.info.backend_pid} "
                            f"principal_wait_graph={graph}"
                        )
                        for pid in graph:
                            frontier, seen = [pid], set()
                            while frontier:
                                current = frontier.pop()
                                if current == blocker.info.backend_pid:
                                    break
                                if current in seen:
                                    continue
                                seen.add(current)
                                frontier.extend(graph.get(current, []))
                            else:
                                raise AssertionError("wait graph misses owned blocker")
                        break
                    time.sleep(0.01)
                else:
                    raise AssertionError("both independent calls did not reach principal lock")
            finally:
                blocker.commit()
            results = []
            for future in futures:
                try:
                    results.append(future.result(timeout=10))
                except (TokenExchangeError, AuthorizationCodeError) as exc:
                    results.append(exc)
            return results


@pytest.mark.parametrize("round_id", range(10))
def test_same_delegation_key_real_lock_race(ledger, dsn, round_id):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    results = locked_race(
        dsn,
        lambda: _exchange(service, keys, registrations, form),
        lambda: _exchange(service, keys, registrations, form),
    )
    assert not any(isinstance(x, Exception) for x in results)
    assert results[0].access_token == results[1].access_token
    assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (2,)
    assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (1,)
    assert fetch_one(dsn, "SELECT sum(amount_reserved),sum(calls_reserved) FROM ag_grants") == (
        0,
        0,
    )


def test_exchange_commit_response_lost_real_process_restart(ledger, dsn):
    import multiprocessing
    import os

    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)
    context = multiprocessing.get_context("fork")
    reader, writer = context.Pipe(duplex=False)

    def run():
        issued = _exchange(service, keys, registrations, form)
        writer.send((os.getpid(), issued.ag_grant_id))
        time.sleep(60)

    process = context.Process(target=run)
    process.start()
    try:
        assert reader.poll(10), "child never committed the exchange"
        pid, grant_id = reader.recv()
        assert pid == process.pid and pid != os.getpid()
        print(f"PROCESS_WITNESS exchange_committed_child={pid} parent={os.getpid()}")
        process.terminate()
        process.join(5)
        assert not process.is_alive() and process.exitcode != 0
        # A new service instance and connection uses durable idempotency only.
        restarted = TokenExchangeService(
            dsn,
            issuer=ISSUER,
            token_endpoint=TOKEN_ENDPOINT,
            signing_key=as_key,
            signing_kid="as-sign-1",
            identities=_resolver(registrations),
        )
        retry = _exchange(restarted, keys, registrations, form)
        assert retry.ag_grant_id == grant_id
        assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (1,)
        assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (2,)
        assert fetch_one(
            dsn, "SELECT token_jws FROM ag_grant_tokens WHERE grant_id=%s", (grant_id,)
        ) == (retry.access_token,)
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        reader.close()
        writer.close()


def late_issuance_wait(dsn, call, *, table, action, deferred, positive, error_type):
    from datetime import datetime, timezone

    from tests.integration.test_consent_final_decision import _wait_blocked, _wait_expired

    key = 8371623
    with psycopg.connect(dsn, autocommit=True) as observer:
        observer.execute(
            "CREATE FUNCTION ag_test_issuance_wait() RETURNS trigger AS $$ "
            f"BEGIN PERFORM pg_advisory_xact_lock({key}); RETURN NEW; END $$ LANGUAGE plpgsql"
        )
        create = "CREATE CONSTRAINT TRIGGER" if deferred else "CREATE TRIGGER"
        defer = "DEFERRABLE INITIALLY DEFERRED" if deferred else ""
        observer.execute(
            f"{create} ag_test_issuance_wait_trg AFTER {action} ON {table} "
            f"{defer} FOR EACH ROW EXECUTE FUNCTION ag_test_issuance_wait()"
        )
        try:
            while time.time() % 1 > 0.2:
                time.sleep(0.01)
            deadline = datetime.fromtimestamp(int(time.time()) + 1, tz=timezone.utc)
            with psycopg.connect(dsn) as blocker, ThreadPoolExecutor(1) as pool:
                blocker.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
                future = pool.submit(call)
                fragment = "SET CONSTRAINTS ALL IMMEDIATE" if deferred else f"{action} "
                # Before repair deferred work executes at COMMIT. Accept either
                # location to prove the old defect, then assert new SET site.
                if deferred:
                    end = time.monotonic() + 5
                    while time.monotonic() < end:
                        waits = observer.execute(
                            "SELECT pid,query FROM pg_stat_activity "
                            "WHERE %s=ANY(pg_blocking_pids(pid))",
                            (blocker.info.backend_pid,),
                        ).fetchall()
                        if waits:
                            assert waits[0][0] != blocker.info.backend_pid
                            print(
                                f"DEFERRED_WITNESS blocker={blocker.info.backend_pid} "
                                f"waiter={waits[0][0]}"
                            )
                            assert "SET CONSTRAINTS ALL IMMEDIATE" in waits[0][1]
                            break
                        time.sleep(0.01)
                    else:
                        raise AssertionError("issuance never reached deferred wait")
                else:
                    _wait_blocked(observer, blocker.info.backend_pid, fragment)
                if not positive:
                    _wait_expired(observer, deadline)
                blocker.commit()
                if positive:
                    assert future.result(timeout=5).access_token
                else:
                    with pytest.raises(error_type) as failure:
                        future.result(timeout=5)
                    assert failure.value.code == (
                        "CODE_OR_PROOF_EXPIRED"
                        if error_type is AuthorizationCodeError
                        else "PROOF_EXPIRED"
                    )
        finally:
            observer.execute(f"DROP TRIGGER ag_test_issuance_wait_trg ON {table}")
            observer.execute("DROP FUNCTION ag_test_issuance_wait()")


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("deferred", [False, True])
@pytest.mark.parametrize("positive", [False, True])
def test_exchange_final_proof_after_late_write(ledger, dsn, round_id, deferred, positive):
    as_key, keys, registrations, service, root = _root(dsn)
    form = _form(as_key, root.access_token)

    def issue():
        proof = sign_ag_proof(
            keys["planner"],
            kid=registrations[(TENANT, "agent-planner")].kid,
            client_id="agent-planner",
            purpose="delegate",
            endpoint=TOKEN_ENDPOINT,
            body=form,
            token=root.access_token,
            now=int(time.time()),
            lifetime_seconds=1,
        )
        return _exchange(service, keys, registrations, form, proof=proof)

    late_issuance_wait(
        dsn,
        issue,
        table="ag_exchange_evidence",
        action="INSERT",
        deferred=deferred,
        positive=positive,
        error_type=TokenExchangeError,
    )
    if not positive:
        assert fetch_one(dsn, "SELECT count(*) FROM ag_grants") == (1,)
        assert fetch_one(dsn, "SELECT count(*) FROM ag_delegations") == (0,)
        assert fetch_one(dsn, "SELECT count(*) FROM ag_exchange_evidence") == (0,)
        assert fetch_one(dsn, "SELECT count(*) FROM ag_proofs") == (1,)
        assert _exchange(service, keys, registrations, form).ag_grant_id
