"""Current authorization of persisted READY receipts, with atomic proof rollback."""

import builtins
from datetime import timedelta

import psycopg
import pytest

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.crypto.sm import sign_compact_jws
from agent_guard.execution.query import AuthorizedQuery
from agent_guard.gateway.config import load_gateway_config, load_gateway_secrets
from agent_guard.gateway.endpoint import GatewayEndpoint
from agent_guard.gateway.factory import build_app
from agent_guard.gateway.http_app import GatewayHttpApp
from agent_guard.server.__main__ import _public_pem
from tests.fixtures.gateway import config_document, query_bundle, raw_material, request
from tests.fixtures.receipts import CorruptRow, collect_futures, full_state, staged_only
from tests.integration.test_receipt_publication import final_env

pytestmark = pytest.mark.integration


def app(env, dsn, verifier):
    return GatewayHttpApp(
        GatewayEndpoint(
            verifier=env.verifier,
            execution=env.adapter,
            queries=AuthorizedQuery(dsn, evidence_store=env.evidence, receipt_verifier=verifier),
            receipt_verifier=verifier,
        )
    )


def query_http(application, dsn, bundle):
    token, proof, body = raw_material(dsn, bundle)
    return request(
        application,
        path="/v1/operations/query",
        body=body,
        headers=[
            (b"content-type", b"application/json"),
            (b"authorization", b"AGPoP " + token),
            (b"ag-proof", proof),
        ],
    )


def test_pending_compatibility_ready_verified_current_query(ledger, dsn, downstream_dsn):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    for validator in (None, verifier):
        status, response, _ = query_http(app(env, dsn, validator), dsn, query_bundle(env, op))
        assert status == 200 and response["receipt_status"] == "PENDING"
    publication = publisher.publish(op)
    bundle = query_bundle(env, op)
    before = full_state(dsn, downstream_dsn)
    assert query_http(app(env, dsn, None), dsn, bundle)[0] == 503
    staged_only(before, full_state(dsn, downstream_dsn), proof_jti=bundle.query.proof_jti)
    status, response, _ = query_http(app(env, dsn, verifier), dsn, bundle)
    assert status == 200 and response["receipt_jws"] == publication.receipt_jws
    assert query_http(app(env, dsn, verifier), dsn, bundle)[0] == 409


@pytest.mark.parametrize(
    "mutation",
    [
        "profile",
        "receipt_id",
        "operation_id",
        "tenant_id",
        "task_id",
        "root_grant_id",
        "grant_id",
        "token_sm3",
        "proof_sm3",
        "intent_sm3",
        "tool_id",
        "tool_version",
        "status",
        "amount_fen",
        "result_sm3",
        "ledger_sm3",
        "iat",
        "typ",
        "signature",
        "unknown-kid",
        "signed-at-null",
        "signed-at-future",
        "signed-at-before",
    ],
)
def test_ready_corruption_rolls_back_query_proof_then_same_proof_succeeds(
    ledger, dsn, downstream_dsn, mutation
):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    publication = publisher.publish(op)
    claims = load_strict_json(verify_compact_payload(publication.receipt_jws))
    values = {}
    if mutation.startswith("signed-at-"):
        values["signed_at"] = {
            "signed-at-null": None,
            "signed-at-future": publication.signed_at + timedelta(days=1),
            "signed-at-before": publication.signed_at - timedelta(days=1),
        }[mutation]
    else:
        typ, kid = "ag-receipt+jwt", "gw-receipt-1"
        if mutation == "typ":
            typ = "ag-at+jwt"
        elif mutation == "unknown-kid":
            kid = "gw-unknown"
        elif mutation != "signature":
            claims[mutation] = claims[mutation] + 1 if type(claims[mutation]) is int else "other"
        signed = sign_compact_jws(key, claims, key_id=kid, token_type=typ)
        if mutation == "signature":
            signed = signed[:-3] + ("A" if signed[-3] != "A" else "B") + signed[-2:]
        values["receipt_jws"] = signed
    bundle = query_bundle(env, op)
    application = app(env, dsn, verifier)
    with CorruptRow(dsn, "ag_receipt_outbox", {"operation_id": op}, values):
        before = full_state(dsn, downstream_dsn)
        assert query_http(application, dsn, bundle)[0] == 503
        staged_only(before, full_state(dsn, downstream_dsn), proof_jti=bundle.query.proof_jti)
    assert query_http(application, dsn, bundle)[0] == 200
    assert query_http(application, dsn, bundle)[0] == 409


def verify_compact_payload(jws):
    from agent_guard.contracts.encoding import b64url_decode

    return b64url_decode(jws.split(".")[1])


def test_http_factory_public_keys_only_never_opens_signer_private_file(
    ledger, dsn, downstream_dsn, monkeypatch, tmp_path
):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    publisher.publish(op)
    from tongsuopy.crypto import serialization

    private_file = tmp_path / "signer.pem"
    private_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private_file.chmod(0o600)
    assert private_file.is_file()
    config = config_document(env)
    config["receipt_keys"] = {"gw-receipt-1": _public_pem(key)}
    original_open = builtins.open

    def guarded_open(file, *args, **kwargs):
        assert "signer.pem" not in str(file)
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    application = build_app(
        load_gateway_config(canonical_json_bytes(config)),
        load_gateway_secrets(
            b'{"note":"TEST ONLY","downstream_secret":"test-only-downstream-service-secret"}'
        ),
        gateway_dsn=dsn,
        downstream_dsn=downstream_dsn,
    )
    status, response, _ = query_http(application, dsn, query_bundle(env, op))
    assert status == 200 and response["receipt_status"] == "READY"
    for reused in (env.as_key, env.keys["executor"]):
        config["receipt_keys"] = {"gw-receipt-1": _public_pem(reused)}
        with pytest.raises(ValueError):
            load_gateway_config(canonical_json_bytes(config))


def test_invoke_terminal_ready_state_collected_before_accept_final_clock(
    ledger, dsn, downstream_dsn
):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    assert (
        env.adapter.accept_response(env.bundle(), receipt_verifier=verifier)["receipt_status"]
        == "PENDING"
    )
    publisher.publish(op)
    assert env.adapter.accept_response(env.bundle(), receipt_verifier=verifier) == {
        "operation_id": op,
        "status": "SUCCEEDED",
        "receipt_status": "READY",
    }


def test_shared_holder_kid_current_query_and_offline_use_operation_scope(
    ledger, dsn, downstream_dsn
):
    import time

    from agent_guard.authorization.proof import sign_ag_proof
    from agent_guard.contracts.ledger import QUERY_ENDPOINT
    from tests.fixtures.receipts import legal_shared_operations

    records, verifier, publisher = legal_shared_operations(dsn, downstream_dsn)
    for item in records:
        publication = publisher.publish(item["op"])
        body = {
            "profile": "GM-MVP-1",
            "task_id": "task-001",
            "operation_id": item["op"],
        }
        proof = sign_ag_proof(
            item["key"],
            kid=item["registration"].kid,
            client_id=item["client"],
            purpose="result-read",
            endpoint=QUERY_ENDPOINT,
            body=body,
            token=item["token"],
            now=int(time.time()),
        )
        bundle = item["iv"].verify_query_bundle(
            item["token"], proof, body=canonical_json_bytes(body), now=int(time.time())
        )
        query = AuthorizedQuery(dsn, evidence_store=item["evidence"], receipt_verifier=verifier)
        assert query.query(bundle)["receipt_jws"] == publication.receipt_jws
        from agent_guard.contracts.ledger import LedgerError

        with pytest.raises(LedgerError):
            query.query(bundle)


@pytest.mark.parametrize(
    "dependency", ["outbox", "projection", "key-lookup", "source-load", "deferred"]
)
@pytest.mark.parametrize("expired", [False, True])
@pytest.mark.parametrize("deadline_kind", ["proof", "token", "root", "mid", "leaf"])
@pytest.mark.parametrize("round", range(10))
def test_all_added_late_dependencies_before_final_clock(
    ledger, dsn, downstream_dsn, monkeypatch, dependency, expired, deadline_kind, round
):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
    from agent_guard.contracts.ledger import LedgerError
    from agent_guard.execution import query as query_module
    from agent_guard.execution.receipt_publication import ReceiptVerifier
    from tests.fixtures.receipts import full_state

    issuance_observations = []
    if deadline_kind == "proof":
        env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    else:
        from tests.fixtures.gateway import signed_env_window
        from tests.fixtures.receipts import receipt_services

        env = signed_env_window(
            dsn,
            downstream_dsn,
            "leaf" if deadline_kind == "token" else deadline_kind,
            observations=issuance_observations,
        )
        op = env.adapter.accept(env.bundle()).operation_id
        assert env.service.run_operation(op).status == "SUCCEEDED"
        key, verifier, publisher = receipt_services(env, dsn)
    publisher.publish(op)
    # Complete the expensive material/oracle preparation before minting the
    # authentic proof. STAGED evidence is the only permitted pre-query addition.
    before = full_state(dsn, downstream_dsn)
    reached = threading.Event()
    observations = []
    fired = False
    if dependency == "outbox":
        target, name = query_module.store, "fetch_outbox"
    elif dependency == "projection":
        target, name = query_module, "project_receipt"
    elif dependency == "key-lookup":
        target, name = ReceiptVerifier, "_trust_tx"
    elif dependency == "source-load":
        target, name = PermissionSnapshotProvider, "load_tx"
    else:
        target, name = psycopg.Connection, "execute"
    original = getattr(target, name)

    def gate(*args, **kwargs):
        nonlocal fired
        conn = args[1] if dependency in ("key-lookup", "source-load") else args[0]
        applies = dependency != "deferred" or args[1] == "SET CONSTRAINTS ALL IMMEDIATE"
        if not fired and applies:
            fired = True
            observations.append(conn.info.backend_pid)
            reached.set()
            if dependency == "deferred":
                original(conn, "SELECT pg_advisory_xact_lock(2387102)")
            else:
                conn.execute("SELECT pg_advisory_xact_lock(2387102)")
        return original(*args, **kwargs)

    monkeypatch.setattr(target, name, gate)
    with psycopg.connect(dsn, autocommit=True) as blocker:
        blocker.execute("SELECT pg_advisory_lock(2387102)")
        expiries = blocker.execute(
            "SELECT depth,extract(epoch FROM expires_at) FROM ag_grants ORDER BY depth"
        ).fetchall()
        if deadline_kind == "proof":
            # Real DB and wall clocks only; align once before actual signing.
            while (
                float(blocker.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0])
                % 1
                > 0.1
            ):
                time.sleep(0.001)
        bundle = query_bundle(env, op, lifetime=1 if deadline_kind == "proof" else 60)
        actual_deadline = (
            bundle.query.proof_exp
            if deadline_kind == "proof"
            else bundle.query.token_exp
            if deadline_kind == "token"
            else int(dict(expiries)[{"root": 0, "mid": 1, "leaf": 2}[deadline_kind]])
        )
        diagnostic = {
            "dependency": dependency,
            "expired": expired,
            "deadline_kind": deadline_kind,
            "round": round,
            "proof_iat": bundle.query.proof_iat,
            "proof_exp": bundle.query.proof_exp,
            "token_exp": bundle.query.token_exp,
            "ancestor_expiries": [(depth, str(exp)) for depth, exp in expiries],
            "actual_AS_issuance": issuance_observations,
            "target_deadline": actual_deadline,
            "before_submit_dbclock": str(
                blocker.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0]
            ),
        }

        def record():
            import json
            import os
            from pathlib import Path

            output = os.environ.get("A23_RECEIPT_EVIDENCE")
            if output:
                label = os.environ.get("A23_RUN_LABEL", "core")
                Path(
                    output, f"{label}-deadline-{round}-{deadline_kind}-{expired}-{dependency}.json"
                ).write_text(json.dumps(diagnostic, indent=2))

        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(
                AuthorizedQuery(dsn, evidence_store=env.evidence, receipt_verifier=verifier).query,
                bundle,
            )
            if not reached.wait(5):
                diagnostic["gate_reached"] = False
                diagnostic["failed_dbclock"] = str(
                    blocker.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0]
                )
                blocker.execute("SELECT pg_advisory_unlock(2387102)")
                try:
                    future.result(5)
                except Exception as exc:
                    diagnostic["future_exception"] = {
                        "type": type(exc).__name__,
                        "code": str(getattr(exc, "code", None)),
                        "text": str(exc),
                    }
                record()
                pytest.fail("unreached real dependency gate: " + str(diagnostic))
            diagnostic["gate_reached"] = True
            diagnostic["backend_pid"] = observations[0]
            deadline = time.monotonic() + 5
            activity = None
            while time.monotonic() < deadline:
                activity = blocker.execute(
                    "SELECT wait_event_type,wait_event,query FROM pg_stat_activity WHERE pid=%s",
                    (observations[0],),
                ).fetchone()
                if activity and activity[:2] == ("Lock", "advisory"):
                    break
                time.sleep(0.001)
            diagnostic["target_activity"] = list(activity)
            assert activity[:2] == ("Lock", "advisory") and "pg_advisory_xact_lock" in activity[2]
            now = blocker.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0]
            if expired:
                while now < actual_deadline:
                    time.sleep(0.005)
                    now = blocker.execute(
                        "SELECT extract(epoch FROM clock_timestamp())"
                    ).fetchone()[0]
                assert now >= actual_deadline
            else:
                if now >= actual_deadline:
                    blocker.execute("SELECT pg_advisory_unlock(2387102)")
                    diagnostic["positive_window_exhausted_dbclock"] = str(now)
                    try:
                        future.result(5)
                    except Exception as exc:
                        diagnostic["future_exception"] = {
                            "type": type(exc).__name__,
                            "code": str(getattr(exc, "code", None)),
                            "text": str(exc),
                        }
                    record()
                    pytest.fail("positive real deadline exhausted: " + str(diagnostic))
            diagnostic["release_dbclock"] = str(now)
            blocker.execute("SELECT pg_advisory_unlock(2387102)")
            if expired:
                with pytest.raises(LedgerError):
                    future.result(5)
                diagnostic["outcome"] = "rejected-at-final-clock"
                staged_only(
                    before, full_state(dsn, downstream_dsn), proof_jti=bundle.query.proof_jti
                )
            else:
                assert future.result(5)["receipt_status"] == "READY"
                diagnostic["outcome"] = "accepted-before-deadline"
                from tests.fixtures.receipts import result_read_only

                result_read_only(
                    before,
                    full_state(dsn, downstream_dsn),
                    evidence_ref=bundle.evidence_ref,
                    proof_jti=bundle.query.proof_jti,
                    operation_id=op,
                    staging=True,
                )
            record()


def test_unknown_receipt_runtime_error_stays_http500(ledger, dsn, downstream_dsn, monkeypatch):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    publisher.publish(op)
    bundle = query_bundle(env, op)
    before = full_state(dsn, downstream_dsn)

    def unknown(*args):
        raise RuntimeError("test-only unexpected program fault")

    monkeypatch.setattr(verifier, "read_tx", unknown)
    assert query_http(app(env, dsn, verifier), dsn, bundle)[0] == 500
    staged_only(before, full_state(dsn, downstream_dsn), proof_jti=bundle.query.proof_jti)


@pytest.mark.parametrize("round", range(10))
def test_accept_response_two_successful_calls_have_independent_status(
    ledger, dsn, downstream_dsn, round
):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    publisher.publish(op)
    ready = env.bundle()
    created = env.bundle(
        "concurrent-read",
        tool="procurement.request.read",
        params={"request_id": "req-001"},
    )
    barrier = threading.Barrier(2)

    def accept(bundle):
        barrier.wait(5)
        return env.adapter.accept_response(bundle, receipt_verifier=verifier)

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(accept, b) for b in (ready, created)]
        outcomes = collect_futures(futures)
    assert outcomes[0] == {
        "operation_id": op,
        "status": "SUCCEEDED",
        "receipt_status": "READY",
    }
    assert (
        outcomes[1]["operation_id"] != op
        and outcomes[1]["status"] == "RESERVED"
        and outcomes[1]["receipt_status"] == "PENDING"
    )


@pytest.mark.parametrize("round", range(10))
def test_accept_response_per_call_closures_never_cross_talk(ledger, dsn, downstream_dsn, round):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from agent_guard.contracts.ledger import LedgerError
    from tests.fixtures.receipts import receipt_services
    from tests.integration.test_verified_execution import signed_env

    env = signed_env(dsn, downstream_dsn)
    _, verifier, publisher = receipt_services(env, dsn)
    bundles = [env.bundle("closure-" + str(i)) for i in range(2)]
    barrier = threading.Barrier(2)

    def accept(bundle):
        barrier.wait(5)
        return env.adapter.accept_response(bundle, receipt_verifier=verifier)

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(accept, b) for b in bundles]
        outcomes = []
        errors = []
        for f in futures:
            try:
                outcomes.append(f.result(10))
            except BaseException as exc:
                errors.append(exc)
    # Root budget100000 admits exactly one70000 order; capture cannot leak
    # another invocation's operation or turn a failed transaction into a reply.
    assert len(outcomes) == 1 and len(errors) == 1 and isinstance(errors[0], LedgerError)
    assert outcomes[0]["receipt_status"] == "PENDING"
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT operation_id FROM ag_operations").fetchone() == (
            outcomes[0]["operation_id"],
        )
        assert (
            conn.execute("SELECT amount_reserved,calls_reserved FROM ag_grants").fetchall()
            == [(70000, 1)] * 3
        )


@pytest.mark.parametrize("mutation", ["missing-exact-tuple", "wrong-spki"])
def test_bad_historical_registration_rolls_back_then_original_proof_recovers(
    ledger, dsn, downstream_dsn, mutation
):
    from dataclasses import replace

    from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
    from agent_guard.execution.receipt_publication import ReceiptVerifier

    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    ready = publisher.publish(op)
    registrations = dict(verifier.registrations)
    target = next(k for k in registrations if k[1] == "agent-executor")
    if mutation == "missing-exact-tuple":
        registrations.pop(target)
    else:
        registrations[target] = replace(
            registrations[target],
            spki_der=serialize_sm2_public_key(generate_sm2_private_key().public_key()),
        )
    broken = ReceiptVerifier(
        issuer=verifier.issuer,
        as_keys=verifier.as_keys,
        gateway_keys=verifier.gateway_keys,
        registrations=registrations,
        permission_provider=verifier.permission_provider,
    )
    bundle = query_bundle(env, op)
    before = full_state(dsn, downstream_dsn)
    assert query_http(app(env, dsn, broken), dsn, bundle)[0] == 503
    staged_only(before, full_state(dsn, downstream_dsn), proof_jti=bundle.query.proof_jti)
    status, response, _ = query_http(app(env, dsn, verifier), dsn, bundle)
    assert status == 200 and response["receipt_jws"] == ready.receipt_jws
    assert query_http(app(env, dsn, verifier), dsn, bundle)[0] == 409


@pytest.mark.parametrize("round", range(10))
def test_accept_response_real_serialization_retry_discards_pending_capture(
    ledger, dsn, downstream_dsn, monkeypatch, round
):
    from contextlib import contextmanager

    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    bundle = env.bundle()
    before = full_state(dsn, downstream_dsn)
    actual_ledger = env.service._ledger
    original_connect = actual_ledger._connect
    original_final = actual_ledger._final_bound_check
    original_read = verifier.read_tx
    captures = []
    ledger_pids = set()
    attempts = []
    injected = False

    def read(conn, operation):
        result = original_read(conn, operation)
        if conn.info.backend_pid in ledger_pids:
            captures.append((conn.info.backend_pid, result.receipt_status))
        return result

    def final(conn, *args):
        nonlocal injected
        original_final(conn, *args)
        attempts.append(conn.info.backend_pid)
        if not injected:
            injected = True
            conn.execute(
                "DO $$ BEGIN RAISE EXCEPTION 'owned a23 serialization fault "
                "after capture' USING ERRCODE='40001'; END $$"
            )

    @contextmanager
    def connect():
        with original_connect() as conn:
            ledger_pids.add(conn.info.backend_pid)
            try:
                yield conn
            except psycopg.errors.SerializationFailure as exc:
                assert exc.sqlstate == "40001"
                # The inner real transaction has rolled back before this
                # context receives its exception. A separate publisher now
                # commits READY; the next ledger attempt must recapture it.
                assert publisher.publish(op).receipt_status == "READY"
                raise

    monkeypatch.setattr(verifier, "read_tx", read)
    monkeypatch.setattr(actual_ledger, "_final_bound_check", final)
    monkeypatch.setattr(actual_ledger, "_connect", connect)
    response = env.adapter.accept_response(bundle, receipt_verifier=verifier)
    assert response == {"operation_id": op, "status": "SUCCEEDED", "receipt_status": "READY"}
    assert [s for pid, s in captures] == ["PENDING", "READY"]
    assert len(attempts) == 2 and attempts[0] != attempts[1]
    from tests.fixtures.receipts import accept_retry_only

    accept_retry_only(
        before,
        full_state(dsn, downstream_dsn),
        evidence_ref=bundle.evidence_ref,
        proof_jti=bundle.invocation.proof_jti,
        operation_id=op,
        publication=True,
    )


@pytest.mark.parametrize("expired", [False, True])
@pytest.mark.parametrize("round", range(10))
def test_accept_response_publication_wait_precedes_final_actual_proof_clock(
    ledger, dsn, downstream_dsn, monkeypatch, expired, round
):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    from agent_guard.contracts.ledger import LedgerError

    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    publisher.publish(op)
    before = full_state(dsn, downstream_dsn)
    reached = threading.Event()
    pids = []
    original = verifier.read_tx

    def gate(conn, operation):
        pids.append(conn.info.backend_pid)
        reached.set()
        conn.execute("SELECT pg_advisory_xact_lock(2387103)")
        return original(conn, operation)

    monkeypatch.setattr(verifier, "read_tx", gate)
    with psycopg.connect(dsn, autocommit=True) as blocker:
        blocker.execute("SELECT pg_advisory_lock(2387103)")
        while (
            float(blocker.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0]) % 1
            > 0.1
        ):
            time.sleep(0.001)
        bundle = env.bundle(proof_lifetime=1)
        deadline = bundle.invocation.proof_exp
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(env.adapter.accept_response, bundle, receipt_verifier=verifier)
            if not reached.wait(5):
                blocker.execute("SELECT pg_advisory_unlock(2387103)")
                future.result(5)
                pytest.fail("authentic accept publication gate was not reached")
            until = time.monotonic() + 5
            while time.monotonic() < until:
                activity = blocker.execute(
                    "SELECT wait_event_type,wait_event,query FROM pg_stat_activity WHERE pid=%s",
                    (pids[0],),
                ).fetchone()
                if activity and activity[:2] == ("Lock", "advisory"):
                    break
                time.sleep(0.001)
            assert activity[:2] == ("Lock", "advisory") and "pg_advisory_xact_lock" in activity[2]
            now = blocker.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0]
            if expired:
                while now < deadline:
                    time.sleep(0.005)
                    now = blocker.execute(
                        "SELECT extract(epoch FROM clock_timestamp())"
                    ).fetchone()[0]
            else:
                assert now < deadline
            blocker.execute("SELECT pg_advisory_unlock(2387103)")
            if expired:
                with pytest.raises(LedgerError):
                    future.result(5)
                staged_only(
                    before,
                    full_state(dsn, downstream_dsn),
                    proof_jti=bundle.invocation.proof_jti,
                    purpose="invoke",
                )
            else:
                assert future.result(5) == {
                    "operation_id": op,
                    "status": "SUCCEEDED",
                    "receipt_status": "READY",
                }
                from tests.fixtures.receipts import accept_retry_only

                accept_retry_only(
                    before,
                    full_state(dsn, downstream_dsn),
                    evidence_ref=bundle.evidence_ref,
                    proof_jti=bundle.invocation.proof_jti,
                    operation_id=op,
                    staging=True,
                )


@pytest.mark.parametrize("order", ["forward", "reverse"])
@pytest.mark.parametrize("round", range(10))
def test_shared_kid_concurrent_current_query_cross_owner_and_trust_repair(
    ledger, dsn, downstream_dsn, monkeypatch, order, round
):
    import copy
    import json
    import os
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from pathlib import Path

    from agent_guard.authorization.proof import sign_ag_proof
    from agent_guard.contracts.ledger import QUERY_ENDPOINT, ErrorCode, LedgerError
    from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
    from agent_guard.evidence.receipt import verify_receipt_bundle
    from agent_guard.execution.receipt_projection import project_receipt
    from agent_guard.execution.receipt_publication import ReceiptVerifier, evidence_bundle
    from tests.fixtures.receipts import legal_shared_operations, publication_only, result_read_only

    records, verifier, publisher = legal_shared_operations(
        dsn, downstream_dsn, failed=order == "reverse", public=True
    )
    if order == "reverse":
        verifier = ReceiptVerifier(
            issuer=verifier.issuer,
            as_keys=verifier.as_keys,
            gateway_keys=verifier.gateway_keys,
            registrations=dict(reversed(list(verifier.registrations.items()))),
            permission_provider=verifier.permission_provider,
        )
        records.reverse()
    before = full_state(dsn, downstream_dsn)
    published = {item["op"]: publisher.publish(item["op"]) for item in records}
    publication_only(before, full_state(dsn, downstream_dsn))

    def bundle_for(item, op):
        body = {"profile": "GM-MVP-1", "task_id": "task-001", "operation_id": op}
        proof = sign_ag_proof(
            item["key"],
            kid=item["registration"].kid,
            client_id=item["client"],
            purpose="result-read",
            endpoint=QUERY_ENDPOINT,
            token=item["token"],
            body=body,
            now=int(time.time()),
        )
        return item["iv"].verify_query_bundle(
            item["token"], proof, body=canonical_json_bytes(body), now=int(time.time())
        )

    bundles = [bundle_for(item, item["op"]) for item in records]
    queries = [
        AuthorizedQuery(dsn, evidence_store=item["evidence"], receipt_verifier=verifier)
        for item in records
    ]
    baseline = full_state(dsn, downstream_dsn)
    gate = threading.Barrier(3)
    pids = []
    guard = threading.Lock()
    for query in queries:
        original = query._ledger._connect

        def connect(original=original):
            conn = original()
            with guard:
                pids.append(conn.info.backend_pid)
            gate.wait(timeout=5)
            return conn

        monkeypatch.setattr(query._ledger, "_connect", connect)
    with ThreadPoolExecutor(2) as pool:
        futures = [
            pool.submit(query.query, bundle) for query, bundle in zip(queries, bundles, strict=True)
        ]
        gate.wait(timeout=5)
        assert len(pids) == len(set(pids)) == 2
        results = collect_futures(futures)
    monkeypatch.undo()
    after = full_state(dsn, downstream_dsn)
    old, new = copy.deepcopy(baseline), copy.deepcopy(after)
    existing = old["gateway"].pop("ag_proofs")
    current = new["gateway"].pop("ag_proofs")
    added = [json.loads(row[0]) for row in current if row not in existing]
    assert len(added) == 2 and all(row in current for row in existing)
    for item, bundle, response in zip(records, bundles, results, strict=True):
        row = next(row for row in added if row["proof_jti"] == bundle.query.proof_jti)
        assert row["operation_id"] == item["op"] and row["evidence_ref"] == bundle.evidence_ref
        assert row["purpose"] == "result-read" and row["endpoint"] == QUERY_ENDPOINT
        assert row["holder_kid"] == item["registration"].kid
        assert row["proof_digest"] == bundle.query.proof_digest
        assert response["receipt_jws"] == published[item["op"]].receipt_jws
        with psycopg.connect(dsn) as conn:
            assert (
                verify_receipt_bundle(
                    evidence_bundle(project_receipt(conn, item["op"]), response["receipt_jws"]),
                    trust=verifier._trust_tx(conn, item["op"]),
                ).operation_id
                == item["op"]
            )
        unchanged = full_state(dsn, downstream_dsn)
        with pytest.raises(LedgerError) as exc:
            AuthorizedQuery(dsn, evidence_store=item["evidence"], receipt_verifier=verifier).query(
                bundle
            )
        assert exc.value.code == ErrorCode.REPLAY
        assert full_state(dsn, downstream_dsn) == unchanged
    assert old == new

    def application(item, trusted):
        return GatewayHttpApp(
            GatewayEndpoint(
                verifier=item["iv"],
                execution=item["adapter"],
                queries=AuthorizedQuery(
                    dsn, evidence_store=item["evidence"], receipt_verifier=trusted
                ),
                receipt_verifier=trusted,
            )
        )

    item, other = records
    cross = bundle_for(item, other["op"])
    before = full_state(dsn, downstream_dsn)
    status, response, _ = query_http(application(item, verifier), dsn, cross)
    cross_status = status
    assert cross_status == 403 and set(response) == {"error"}
    staged_only(before, full_state(dsn, downstream_dsn), proof_jti=cross.query.proof_jti)

    registrations = dict(verifier.registrations)
    target = (item["tenant"], item["client"], item["registration"].kid)
    mutation = "wrong-exact-tuple" if round % 2 == 0 else "wrong-spki"
    if mutation == "wrong-exact-tuple":
        selected = registrations.pop(target)
        wrong = replace(selected, client_id=other["client"])
        registrations[(wrong.tenant_id, wrong.client_id, wrong.kid)] = wrong
    else:
        registrations[target] = replace(
            registrations[target],
            spki_der=serialize_sm2_public_key(generate_sm2_private_key().public_key()),
        )
    bad = ReceiptVerifier(
        issuer=verifier.issuer,
        as_keys=verifier.as_keys,
        gateway_keys=verifier.gateway_keys,
        registrations=registrations,
        permission_provider=verifier.permission_provider,
    )
    repair = bundle_for(item, item["op"])
    before = full_state(dsn, downstream_dsn)
    assert query_http(application(item, bad), dsn, repair)[0] == 503
    staged_only(before, full_state(dsn, downstream_dsn), proof_jti=repair.query.proof_jti)
    before = full_state(dsn, downstream_dsn)
    status, response, _ = query_http(application(item, verifier), dsn, repair)
    assert status == 200 and response["receipt_jws"] == published[item["op"]].receipt_jws
    with psycopg.connect(dsn) as conn:
        actual_ref = conn.execute(
            "SELECT evidence_ref FROM ag_proofs WHERE proof_jti=%s AND purpose='result-read'",
            (repair.query.proof_jti,),
        ).fetchone()[0]
        actual = conn.execute(
            "SELECT token_bytes,proof_bytes,body_bytes FROM ag_verified_evidence WHERE"
            " evidence_ref=%s",
            (actual_ref,),
        ).fetchone()
    assert tuple(bytes(v) for v in actual) == raw_material(dsn, repair)
    result_read_only(
        before,
        full_state(dsn, downstream_dsn),
        evidence_ref=actual_ref,
        proof_jti=repair.query.proof_jti,
        operation_id=item["op"],
        staging=True,
    )
    before = full_state(dsn, downstream_dsn)
    assert query_http(application(item, verifier), dsn, repair)[0] == 409
    staged_only(before, full_state(dsn, downstream_dsn), proof_jti=repair.query.proof_jti)
    output = os.environ.get("A23_RECEIPT_EVIDENCE")
    if output:
        label = os.environ.get("A23_RUN_LABEL", "core")
        Path(output, f"{label}-shared-query-{order}-{round}.json").write_text(
            json.dumps(
                dict(
                    order=order,
                    round=round,
                    backend_pids=pids,
                    mutation=mutation,
                    concurrent_queries=2,
                    crossowner_status=cross_status,
                    bad_trust_status=503,
                    repaired_same_proof_status=200,
                    replay_status=409,
                    oracle="all ag_* and ds_* rows exact except two query proofs; publ"
                    "ic failures one stage only; repaired one stage+proof",
                ),
                indent=2,
            )
        )
