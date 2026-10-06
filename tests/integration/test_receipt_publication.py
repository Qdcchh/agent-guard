"""Real PostgreSQL AS→gateway→downstream→internal receipt publication."""

import json
import multiprocessing
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest

from agent_guard.authorization.evidence_store import EvidenceError
from agent_guard.authorization.verifier import VerificationError
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.contracts.ledger import LedgerError
from agent_guard.crypto.sm import sign_compact_jws, verify_compact_jws
from agent_guard.evidence.receipt import verify_receipt_bundle
from agent_guard.execution import store
from agent_guard.execution.original_material import scoped_trust_tx
from agent_guard.execution.query import AuthorizedQuery
from agent_guard.execution.receipt_projection import project_receipt
from agent_guard.execution.receipt_publication import evidence_bundle
from agent_guard.gateway.endpoint import GatewayEndpoint
from agent_guard.gateway.http_app import GatewayHttpApp
from tests.fixtures.gateway import query_bundle, raw_material, request
from tests.fixtures.receipts import (
    CorruptRow,
    collect_futures,
    full_state,
    publication_only,
    real_login_capacity_env,
    receipt_services,
    staged_only,
)
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


def test_real_as_public_256_sku_capacity_publish_query_offline(ledger, dsn, downstream_dsn):
    env = real_login_capacity_env(dsn, downstream_dsn)
    _, verifier, publisher = receipt_services(env, dsn)
    app = GatewayHttpApp(
        GatewayEndpoint(
            verifier=env.verifier,
            execution=env.adapter,
            queries=AuthorizedQuery(dsn, evidence_store=env.evidence, receipt_verifier=verifier),
            receipt_verifier=verifier,
        )
    )
    params = {
        "request_id": "req-001",
        "quote_id": "quote-001",
        "quote_version": "1",
        "items": [{"sku": f"s{i:03d}", "quantity": 1} for i in range(256)],
        "delivery_id": "office-001",
    }
    invocation = env.bundle("capacity256", params=params)
    token, proof, body = raw_material(dsn, invocation)
    status, accepted, _ = request(
        app,
        body=body,
        headers=[
            (b"content-type", b"application/json"),
            (b"authorization", b"AGPoP " + token),
            (b"ag-proof", proof),
        ],
    )
    assert status == 202, accepted
    operation_id = accepted["operation_id"]
    assert env.service.run_operation(operation_id).status == "SUCCEEDED"
    before = full_state(dsn, downstream_dsn)
    with psycopg.connect(dsn) as conn:
        projection = project_receipt(conn, operation_id)
        source = invocation.source.material()
        key = publisher._private_key
        signed = sign_compact_jws(
            key,
            load_strict_json(projection.claims_bytes),
            key_id="gw-receipt-1",
            token_type="ag-receipt+jwt",
        )
        bundle = evidence_bundle(projection, signed)
        components = {
            name: len(canonical_json_bytes(value))
            for name, value in bundle.items()
            if name != "ledger_changes"
        }
        components.update(
            source=len(source),
            ledger=len(projection.ledger_bytes),
            quote=len(bytes(store.fetch_operation(conn, operation_id).quote_snapshot)),
        )
        components["jws"] = {
            name: len(raw)
            for name, raw in {
                **{f"ancestor{i}": t for i, t in enumerate(projection.ancestor_tokens)},
                "proof": proof,
                "receipt": signed,
            }.items()
        }
        # Measure each old-profile component independently before the unchanged
        # SDK performs its aggregate preflight. Record sizes, never raw secrets.
        assert all(size <= 16384 for size in components["jws"].values())
        assert len(source) <= 65536
        trust = scoped_trust_tx(
            conn,
            operation_id,
            issuer=verifier.issuer,
            as_keys=verifier.as_keys,
            gateway_keys=verifier.gateway_keys,
            registrations=verifier.registrations,
            permission_provider=verifier.permission_provider,
        )
        output = os.environ.get("A23_RECEIPT_EVIDENCE")
        if output:
            Path(
                output, os.environ.get("A23_RUN_LABEL", "capacity") + "-components.json"
            ).write_text(json.dumps(components, indent=2))
        assert verify_receipt_bundle(bundle, trust=trust).amount_fen == 256
    publication = publisher.publish(operation_id)
    assert publication.receipt_status == "READY"
    assert publisher.publish(operation_id) == publication
    with psycopg.connect(dsn) as conn:
        assert (
            conn.execute(
                "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled "
                "FROM ag_grants ORDER BY depth"
            ).fetchall()
            == [(0, 256, 0, 1)] * 3
        )
    with psycopg.connect(downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_orders").fetchone() == (1,)
    current = query_bundle(env, operation_id)
    response = AuthorizedQuery(dsn, evidence_store=env.evidence, receipt_verifier=verifier).query(
        current
    )
    assert response["receipt_jws"] == publication.receipt_jws
    assert len(canonical_json_bytes(response)) <= 65536
    after = full_state(dsn, downstream_dsn)
    assert before["downstream"] == after["downstream"]


def final_env(dsn, downstream_dsn, *, failed=False, tool="procurement.order.create"):
    env = signed_env(dsn, downstream_dsn)
    if failed:
        from agent_guard.tools.downstream import MockDownstream
        from tests.fixtures.execution import DOWNSTREAM_SECRET

        env.service._downstream = MockDownstream(downstream_dsn, service_secret=DOWNSTREAM_SECRET)
    params = {"request_id": "req-001"} if tool == "procurement.request.read" else None
    accepted = env.adapter.accept(env.bundle(tool=tool, params=params))
    assert env.service.run_operation(accepted.operation_id).status == (
        "FAILED" if failed else "SUCCEEDED"
    )
    key, verifier, publisher = receipt_services(env, dsn)
    return env, accepted.operation_id, key, verifier, publisher


@pytest.mark.parametrize(
    "fault",
    [
        "unit-price",
        "total",
        "overflow",
        "quantity",
        "quote-id",
        "quote-version",
        "currency",
        "cost-currency",
        "cost-calls",
    ],
)
def test_original_accept_facts_coherent_quote_result_refused_before_sign(
    ledger, dsn, downstream_dsn, monkeypatch, fault
):
    """Two mutually consistent damaged columns cannot attest accepted business facts."""
    import copy

    import agent_guard.execution.receipt_publication as publication_module
    from agent_guard.contracts.ledger import MAX_SAFE_INT
    from tests.integration.test_gateway_receipt_query import app, query_http

    env, op, _, verifier, publisher = final_env(dsn, downstream_dsn)
    with psycopg.connect(dsn) as conn:
        original = store.fetch_outbox(conn, op)
        quote = load_strict_json(bytes(store.fetch_operation(conn, op).quote_snapshot))
        result = load_strict_json(original["result_bytes"])
    bad_quote, bad_result = copy.deepcopy(quote), copy.deepcopy(result)
    for value in (bad_quote, bad_result):
        if fault == "unit-price":
            value["items"][0]["unit_price_fen"] += 1
        elif fault == "total":
            value["total_fen"] += 1
        elif fault == "overflow":
            value["items"][0].update(quantity=2, unit_price_fen=MAX_SAFE_INT)
        elif fault == "quantity":
            # Keep arithmetic valid while violating the original signed items.
            value["items"][0].update(quantity=2, unit_price_fen=35000)
        elif fault == "quote-id":
            value["quote_id"] = "other-quote"
        elif fault == "quote-version":
            value["quote_version"] = "2"
        elif fault == "currency":
            value["currency"] = "USD"
    currency, calls_cost = (
        ("USD" if fault == "cost-currency" else "CNY"),
        (2 if fault == "cost-calls" else 1),
    )
    baseline = full_state(dsn, downstream_dsn)
    assert len(baseline["gateway"]) == 31 and len(baseline["downstream"]) == 3
    with pytest.raises(psycopg.Error):
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "UPDATE ag_operations SET quote_snapshot=%s,currency=%s,calls=%s "
                "WHERE operation_id=%s",
                (canonical_json_bytes(bad_quote), currency, calls_cost, op),
            )
    assert full_state(dsn, downstream_dsn) == baseline
    calls = []
    real_sign = publication_module.sign_compact_jws

    def sign(*args, **kwargs):
        calls.append(kwargs["token_type"])
        return real_sign(*args, **kwargs)

    monkeypatch.setattr(publication_module, "sign_compact_jws", sign)
    if fault == "cost-calls":
        # USER trigger bypass does not bypass the accepted single-call CHECK.
        # Retain this reachable SQL guard positive control rather than dropping
        # a database constraint to manufacture an impossible persisted row.
        with pytest.raises(psycopg.errors.CheckViolation):
            with CorruptRow(dsn, "ag_operations", {"operation_id": op}, {"calls": 2}):
                pytest.fail("single-call CHECK accepted an invalid operation")
        assert calls == [] and full_state(dsn, downstream_dsn) == baseline
        ready = publisher.publish(op)
        assert ready.receipt_status == "READY" and calls == ["ag-receipt+jwt"]
        publication_only(baseline, full_state(dsn, downstream_dsn))
        return
    application = app(env, dsn, verifier)
    current = query_bundle(env, op)
    try:
        with (
            CorruptRow(
                dsn,
                "ag_operations",
                {"operation_id": op},
                {
                    "quote_snapshot": canonical_json_bytes(bad_quote),
                    "currency": currency,
                    "calls": calls_cost,
                },
            ),
            CorruptRow(
                dsn,
                "ag_receipt_outbox",
                {"operation_id": op},
                {"result_bytes": canonical_json_bytes(bad_result)},
            ),
        ):
            damaged = full_state(dsn, downstream_dsn)
            with pytest.raises(EvidenceError):
                publisher.publish(op)
            assert calls == []
            assert full_state(dsn, downstream_dsn) == damaged
            with psycopg.connect(dsn) as conn:
                out = store.fetch_outbox(conn, op)
                assert (out["receipt_status"], out["receipt_jws"], out["signed_at"]) == (
                    "PENDING",
                    None,
                    None,
                )
                assert (out["receipt_id"], out["created_at"]) == (
                    original["receipt_id"],
                    original["created_at"],
                )
            status, response, _ = query_http(application, dsn, current)
            assert status == 503 and response["error"]["code"] == "TRUSTED_STATE_UNAVAILABLE"
            staged_only(damaged, full_state(dsn, downstream_dsn), proof_jti=current.query.proof_jti)
        restored = full_state(dsn, downstream_dsn)
        ready = publisher.publish(op)
        assert ready.receipt_status == "READY" and calls == ["ag-receipt+jwt"]
        publication_only(restored, full_state(dsn, downstream_dsn))
        with psycopg.connect(dsn) as conn:
            projection = verifier.verify_tx(conn, op, ready.receipt_jws)
            claims = load_strict_json(projection.claims_bytes)
            assert claims["receipt_id"] == original["receipt_id"]
            assert claims["iat"] == int(original["created_at"].timestamp())
        assert query_http(application, dsn, current)[0] == 200
        assert query_http(application, dsn, current)[0] == 409
    finally:
        application._executor.shutdown()


@pytest.mark.parametrize("fault", ["real_sign_backend_error", "typed_storage_rollback"])
def test_p18_sign_failure_then_same_material_recovers(
    ledger, dsn, downstream_dsn, monkeypatch, fault
):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    before = full_state(dsn, downstream_dsn)
    if fault == "real_sign_backend_error":
        from tongsuopy.crypto import hashes
        from tongsuopy.crypto.asymciphers import ec
        from tongsuopy.crypto.exceptions import UnsupportedAlgorithm

        class UnavailableDigest(hashes.HashAlgorithm):
            name = "a23-unavailable-backend-digest"
            digest_size = 32
            block_size = 64

        original_sign = key.sign
        calls = []

        def backend_unavailable(message, algorithm):
            # Fault the real Tongsuo signing path at its native EVP digest
            # lookup. No fabricated signature or raised exception substitutes
            # for the native backend's UnsupportedAlgorithm result.
            assert isinstance(algorithm.algorithm, hashes.SM3)
            calls.append(len(message))
            return original_sign(message, ec.ECDSA(UnavailableDigest()))

        with monkeypatch.context() as patch:
            patch.setattr(key, "sign", backend_unavailable)
            with pytest.raises(UnsupportedAlgorithm, match="not a supported hash on this backend"):
                publisher.publish(op)
        assert len(calls) == 1 and calls[0] > 100
    else:
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "ALTER TABLE ag_receipt_outbox ADD CONSTRAINT a23_reject "
                "CHECK(receipt_status<>'READY')"
            )
        with pytest.raises(LedgerError) as exc:
            publisher.publish(op)
        assert exc.value.__cause__.sqlstate == "23514"
        with psycopg.connect(dsn) as conn:
            conn.execute("ALTER TABLE ag_receipt_outbox DROP CONSTRAINT a23_reject")
    assert full_state(dsn, downstream_dsn) == before
    publication = publisher.publish(op)
    assert publication.receipt_status == "READY"
    publication_only(before, full_state(dsn, downstream_dsn))
    assert publisher.publish(op) == publication


def child_publish(publisher, op, pipe, hold=False):
    import hashlib
    import platform
    import sys

    import agent_guard.execution.receipt_publication as implementation
    from agent_guard.execution.receipt_publication import InternalPublisher

    assert isinstance(publisher, InternalPublisher)
    output = os.environ.get("A23_RECEIPT_EVIDENCE")
    if output:
        path = Path(implementation.__file__)
        label = os.environ.get("A23_RUN_LABEL", "core")
        Path(output, f"{label}-child-{os.getpid()}.json").write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "ppid": os.getppid(),
                    "python": platform.python_version(),
                    "executable": sys.executable,
                    "module": str(path),
                    "module_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "entry": "InternalPublisher.publish",
                },
                indent=2,
            )
        )
    result = publisher.publish(op)
    pipe.send((os.getpid(), result))
    if hold:
        # The actual reply remains unconsumed while the independent observer
        # verifies READY; killing this process loses its remaining IPC delivery.
        threading.Event().wait(30)


def test_p18_real_sigkill_after_sign_before_commit(ledger, dsn, downstream_dsn):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    before = full_state(dsn, downstream_dsn)
    ctx = multiprocessing.get_context("fork")
    with psycopg.connect(dsn, autocommit=True) as blocker:
        blocker.execute("SELECT pg_advisory_lock(2387101)")
        with psycopg.connect(dsn) as setup:
            setup.execute(
                "CREATE FUNCTION a23_before_ready() RETURNS trigger "
                "LANGUAGE plpgsql AS $$ BEGIN IF NEW.receipt_status='READY' THEN PERFO"
                "RM pg_advisory_xact_lock(2387101); END IF; RETURN NEW; END $$"
            )
            setup.execute(
                "CREATE TRIGGER a23_before_ready BEFORE UPDATE ON "
                "ag_receipt_outbox FOR EACH ROW EXECUTE FUNCTION a23_before_ready()"
            )
        reader, writer = ctx.Pipe(duplex=False)
        process = ctx.Process(target=child_publish, args=(publisher, op, writer))
        process.start()
        try:
            deadline = time.monotonic() + 10
            observed = None
            while time.monotonic() < deadline:
                rows = blocker.execute(
                    "SELECT pid,query,wait_event_type,wait_event FROM "
                    "pg_stat_activity WHERE datname=current_database() AND pid<>pg_bac"
                    "kend_pid() AND wait_event='advisory'"
                ).fetchall()
                if rows:
                    observed = rows[0]
                    break
                time.sleep(0.01)
            assert observed is not None
            assert "UPDATE ag_receipt_outbox SET receipt_status='READY'" in observed[1]
            assert observed[2:] == ("Lock", "advisory")
            os.kill(process.pid, signal.SIGKILL)
            process.join(10)
            assert process.exitcode == -signal.SIGKILL
            assert full_state(dsn, downstream_dsn) == before
        finally:
            if process.is_alive():
                process.kill()
                process.join(10)
            blocker.execute("SELECT pg_advisory_unlock(2387101)")
            with psycopg.connect(dsn) as setup:
                setup.execute("DROP TRIGGER a23_before_ready ON ag_receipt_outbox")
                setup.execute("DROP FUNCTION a23_before_ready()")
        recovery = ctx.Process(target=child_publish, args=(publisher, op, writer))
        recovery.start()
        assert reader.poll(10)
        pid, result = reader.recv()
        recovery.join(10)
        assert recovery.exitcode == 0 and pid == recovery.pid and pid != process.pid
        assert result.receipt_status == "READY"
        publication_only(before, full_state(dsn, downstream_dsn))
        reader.close()
        writer.close()


def test_p18_committed_ready_reply_lost_new_process_returns_original(ledger, dsn, downstream_dsn):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    before = full_state(dsn, downstream_dsn)
    ctx = multiprocessing.get_context("fork")
    reader, writer = ctx.Pipe(duplex=False)
    process = ctx.Process(target=child_publish, args=(publisher, op, writer, True))
    process.start()
    try:
        assert reader.poll(10)
        with psycopg.connect(dsn) as observer:
            saved = store.fetch_outbox(observer, op)
            assert saved["receipt_status"] == "READY"
        # Discard the reader without delivering the reply to the caller.
        reader.close()
        os.kill(process.pid, signal.SIGKILL)
        process.join(10)
        assert process.exitcode == -signal.SIGKILL
        new_reader, new_writer = ctx.Pipe(duplex=False)
        recovery = ctx.Process(target=child_publish, args=(publisher, op, new_writer))
        recovery.start()
        assert new_reader.poll(10)
        pid, result = new_reader.recv()
        recovery.join(10)
        assert recovery.exitcode == 0 and pid != process.pid
        assert result.receipt_jws == saved["receipt_jws"] and result.signed_at == saved["signed_at"]
        publication_only(before, full_state(dsn, downstream_dsn))
        new_reader.close()
        new_writer.close()
    finally:
        if process.is_alive():
            process.kill()
            process.join(10)
        writer.close()


@pytest.mark.parametrize("round", range(10))
def test_p18_publishers_same_operation_ten_rounds(ledger, dsn, downstream_dsn, monkeypatch, round):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    before = full_state(dsn, downstream_dsn)
    barrier = threading.Barrier(3)
    pids = []
    lock = threading.Lock()
    original = publisher._connect

    def connect():
        conn = original()
        with lock:
            pids.append(conn.info.backend_pid)
        return conn

    monkeypatch.setattr(publisher, "_connect", connect)

    def run():
        barrier.wait(5)
        return publisher.publish(op)

    with psycopg.connect(dsn) as blocker, psycopg.connect(dsn, autocommit=True) as observer:
        blocker_pid = blocker.info.backend_pid
        blocker.execute(
            "SELECT operation_id FROM ag_receipt_outbox WHERE operation_id=%s FOR UPDATE", (op,)
        )
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            barrier.wait(5)
            until = time.monotonic() + 5
            activities = []
            while time.monotonic() < until:
                with lock:
                    targets = list(pids)
                if len(targets) == 2:
                    activities = observer.execute(
                        "SELECT pid,wait_event_type,wait_event,query FROM "
                        "pg_stat_activity WHERE pid=ANY(%s) ORDER BY pid",
                        (targets,),
                    ).fetchall()
                    if len(activities) == 2 and all(
                        row[1] == "Lock" and "FOR UPDATE" in row[3] for row in activities
                    ):
                        break
                time.sleep(0.001)
            assert len(activities) == 2 and len(set(pids)) == 2
            assert all(
                row[1] == "Lock" and "ag_receipt_outbox" in row[3] and "FOR UPDATE" in row[3]
                for row in activities
            )
            blocker.rollback()
            results = collect_futures(futures)
    assert results[0] == results[1] and results[0].receipt_status == "READY"
    publication_only(before, full_state(dsn, downstream_dsn))
    output = os.environ.get("A23_RECEIPT_EVIDENCE")
    if output:
        label = os.environ.get("A23_RUN_LABEL", "core")
        Path(output, f"{label}-sameop-publisher-lock-{round}.json").write_text(
            json.dumps(
                {"blocker_pid": blocker_pid, "publisher_pids": pids, "target_activity": activities},
                indent=2,
            )
        )


@pytest.mark.parametrize("failed", [False, True])
def test_ready_update_only_three_fields_atomic_no_business_changes(
    ledger, dsn, downstream_dsn, failed
):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn, failed=failed)
    before = full_state(dsn, downstream_dsn)
    result = publisher.publish(op)
    publication_only(before, full_state(dsn, downstream_dsn))
    with psycopg.connect(dsn) as conn:
        claims = load_strict_json(project_receipt(conn, op).claims_bytes)
        assert claims["amount_fen"] == (0 if failed else 70000)
    assert result.receipt_status == "READY"


def test_original_receipt_id_iat_and_seventeen_claims_stable(ledger, dsn, downstream_dsn):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    with psycopg.connect(dsn) as conn:
        original = project_receipt(conn, op).claims_bytes
        assert len(load_strict_json(original)) == 17
    ready = publisher.publish(op)
    retry = env.adapter.accept_response(env.bundle(), receipt_verifier=verifier)
    assert retry == {
        "operation_id": op,
        "status": "SUCCEEDED",
        "receipt_status": "READY",
    }
    assert publisher.publish(op) == ready
    with psycopg.connect(dsn) as conn:
        assert project_receipt(conn, op).claims_bytes == original


@pytest.mark.parametrize("state", ["RESERVED", "EXECUTING", "UNKNOWN"])
def test_nonterminal_no_final_receipt_or_publication(ledger, dsn, downstream_dsn, state):
    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    op = accepted.operation_id
    if state != "RESERVED":
        env.service._claim(op, "a23-core-test-owner")
    if state == "UNKNOWN":
        with CorruptRow(dsn, "ag_operations", {"operation_id": op}, {"status": state}):
            _, verifier, publisher = receipt_services(env, dsn)
            before = full_state(dsn, downstream_dsn)
            result = publisher.publish(op)
            assert result.receipt_id is result.receipt_jws is result.signed_at is None
            assert result.receipt_status == "PENDING"
            assert full_state(dsn, downstream_dsn) == before
        return
    _, verifier, publisher = receipt_services(env, dsn)
    before = full_state(dsn, downstream_dsn)
    result = publisher.publish(op)
    assert result.receipt_id is result.receipt_jws is result.signed_at is None
    assert result.receipt_status == "PENDING"
    assert full_state(dsn, downstream_dsn) == before


def test_real_signer_publication_and_independent_sdk_rejection(ledger, dsn, downstream_dsn):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    result = publisher.publish(op)
    before = full_state(dsn, downstream_dsn)
    with psycopg.connect(dsn) as conn:
        projection = project_receipt(conn, op)
        trust = verifier._trust_tx(conn, op)
        assert (
            verify_receipt_bundle(
                evidence_bundle(projection, result.receipt_jws), trust=trust
            ).operation_id
            == op
        )
        for typ in ("ag-at+jwt", "ag-pop+jwt", "ag-id+jwt"):
            wrong = sign_compact_jws(
                key,
                load_strict_json(projection.claims_bytes),
                key_id="gw-receipt-1",
                token_type=typ,
            )
            with pytest.raises(EvidenceError):
                verifier.verify_tx(conn, op, wrong)
        claims = load_strict_json(projection.claims_bytes)
        for name in claims:
            bad = dict(claims)
            bad[name] = bad[name] + 1 if type(bad[name]) is int else "other"
            wrong = sign_compact_jws(key, bad, key_id="gw-receipt-1", token_type="ag-receipt+jwt")
            with pytest.raises(EvidenceError):
                verifier.verify_tx(conn, op, wrong)
    assert full_state(dsn, downstream_dsn) == before


@pytest.mark.parametrize(
    "mutation",
    [
        *[
            "ctx-" + n
            for n in (
                "tenant_id",
                "task_id",
                "root_id",
                "tool_id",
                "tool_version",
                "idempotency_key",
                "canonical_params",
                "ancestor_ids",
                "token_digest",
                "proof_digest",
                "intent_digest",
                "token_exp",
                "proof_iat",
                "proof_exp",
                "proof_jti",
                "profile",
            )
        ],
        "source",
        "raw-token",
        "raw-proof",
        "raw-request",
        "quote-supplier",
        "quote-price",
        "quote-quantity",
        "result-operation",
        "result-total",
        "result-variant",
        "ledger-phase",
        "ledger-seq",
        "ledger-missing",
        "ledger-reverse",
        "ledger-duplicate",
        *[
            f"delta-{event}-{node}-{field}"
            for event in range(2)
            for node in range(3)
            for field in (
                "amount_reserved_delta",
                "amount_settled_delta",
                "calls_reserved_delta",
                "calls_settled_delta",
            )
        ],
    ],
)
def test_all_first_context_source_quote_result_event_mutations_refuse(
    ledger, dsn, downstream_dsn, mutation
):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    with psycopg.connect(dsn) as conn:
        operation = store.fetch_operation(conn, op)
        out = store.fetch_outbox(conn, op)
        evidence = conn.execute(
            "SELECT "
            "context_json,chain_json,token_bytes,proof_bytes,body_bytes FROM ag_verifi"
            "ed_evidence WHERE evidence_ref=%s",
            (operation.evidence_ref,),
        ).fetchone()
    table, where = "ag_verified_evidence", {"evidence_ref": operation.evidence_ref}
    if mutation.startswith("ctx-"):
        context = load_strict_json(bytes(evidence[0]))
        field = mutation[4:]
        context[field] = (
            []
            if field == "ancestor_ids"
            else 1
            if field in {"token_exp", "proof_iat", "proof_exp"}
            else "other"
        )
        values = {"context_json": canonical_json_bytes(context)}
    elif mutation == "source":
        values = {"chain_json": b"{}"}
    elif mutation.startswith("raw-"):
        field, index = {
            "raw-token": ("token_bytes", 2),
            "raw-proof": ("proof_bytes", 3),
            "raw-request": ("body_bytes", 4),
        }[mutation]
        values = {field: bytes(evidence[index]) + b"x"}
    elif mutation.startswith("quote-"):
        table, where = "ag_operations", {"operation_id": op}
        quote = load_strict_json(bytes(operation.quote_snapshot))
        if mutation == "quote-supplier":
            quote["supplier_id"] = "other"
        elif mutation == "quote-price":
            quote["items"][0]["unit_price_fen"] += 1
        else:
            quote["items"][0]["quantity"] += 1
        values = {"quote_snapshot": canonical_json_bytes(quote)}
    else:
        table, where = "ag_receipt_outbox", {"operation_id": op}
        if mutation.startswith("result-"):
            result = load_strict_json(out["result_bytes"])
            if mutation == "result-operation":
                result["operation_id"] = "other"
            elif mutation == "result-total":
                result["total_fen"] += 1
            else:
                result = {
                    "kind": "read",
                    "operation_id": op,
                    "tool_id": "procurement.order.create",
                }
            values = {"result_bytes": canonical_json_bytes(result)}
        else:
            ledger = json.loads(out["ledger_changes_json"])
            if mutation == "ledger-phase":
                ledger["events"][1]["phase"] = "RELEASE"
            elif mutation == "ledger-seq":
                ledger["events"][0]["seq"] = 1
            elif mutation == "ledger-missing":
                ledger["events"][0]["nodes"].pop(1)
            elif mutation == "ledger-reverse":
                ledger["events"].reverse()
            elif mutation == "ledger-duplicate":
                ledger["events"][0]["nodes"][1] = ledger["events"][0]["nodes"][0]
            else:
                _, event, node, field = mutation.split("-", 3)
                ledger["events"][int(event)]["nodes"][int(node)][field] += 1
            values = {"ledger_changes_json": json.dumps(ledger).encode()}
    with CorruptRow(dsn, table, where, values):
        before = full_state(dsn, downstream_dsn)
        with pytest.raises(EvidenceError):
            publisher.publish(op)
        assert full_state(dsn, downstream_dsn) == before
    assert publisher.publish(op).receipt_status == "READY"


def test_old_ready_key_rotation_stays_byte_identical(ledger, dsn, downstream_dsn):
    from agent_guard.crypto.sm import generate_sm2_private_key
    from agent_guard.execution.receipt_publication import (
        InternalPublisher,
        ReceiptVerifier,
    )

    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    ready = publisher.publish(op)
    newer = generate_sm2_private_key()
    rotated = ReceiptVerifier(
        issuer=verifier.issuer,
        as_keys=verifier.as_keys,
        gateway_keys={**verifier.gateway_keys, "gw-receipt-new": newer.public_key()},
        registrations=verifier.registrations,
        permission_provider=verifier.permission_provider,
    )
    new = InternalPublisher(dsn, private_key=newer, signing_kid="gw-receipt-new", verifier=rotated)
    before = full_state(dsn, downstream_dsn)
    assert new.publish(op) == ready
    untrusted = ReceiptVerifier(
        issuer=verifier.issuer,
        as_keys=verifier.as_keys,
        gateway_keys={"gw-receipt-new": newer.public_key()},
        registrations=verifier.registrations,
        permission_provider=verifier.permission_provider,
    )
    with psycopg.connect(dsn) as conn:
        with pytest.raises(EvidenceError):
            untrusted.read_tx(conn, op)
    assert full_state(dsn, downstream_dsn) == before


@pytest.mark.parametrize("ancestor", range(3))
@pytest.mark.parametrize("change", ["revocation", "disable"])
def test_publish_after_ancestor_expiry_revocation_holder_disable(
    ledger, dsn, downstream_dsn, ancestor, change
):
    from agent_guard.ledger.provisioning import deactivate_principal, revoke_grant

    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT grant_id,tenant_id,holder_client_id,holder_kid FROM ag_grants ORDER BY depth"
        ).fetchall()[ancestor]
        if change == "revocation":
            revoke_grant(conn, row[0])
        else:
            deactivate_principal(conn, tenant_id=row[1], client_id=row[2], kid=row[3])
    before = full_state(dsn, downstream_dsn)
    assert publisher.publish(op).receipt_status == "READY"
    publication_only(before, full_state(dsn, downstream_dsn))
    with pytest.raises((LedgerError, EvidenceError, VerificationError)):
        env.adapter.accept(env.bundle())


@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("order", ["forward", "reverse"])
@pytest.mark.parametrize("round", range(10))
def test_two_legal_operations_shared_holder_kid_publish_independently(
    ledger, dsn, downstream_dsn, failed, order, round
):
    from tests.fixtures.receipts import legal_shared_operations

    records, verifier, publisher = legal_shared_operations(dsn, downstream_dsn, failed=failed)
    if order == "reverse":
        records.reverse()
    before = full_state(dsn, downstream_dsn)
    barrier = threading.Barrier(2)

    def publish(item):
        barrier.wait(5)
        return publisher.publish(item["op"])

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(publish, item) for item in records]
        results = collect_futures(futures)
    assert len({r.operation_id for r in results}) == 2
    publication_only(before, full_state(dsn, downstream_dsn))
    for item, result in zip(records, results, strict=True):
        with psycopg.connect(dsn) as conn:
            trust = verifier._trust_tx(conn, item["op"])
            assert (
                trust.historical_registrations[item["registration"].kid].tenant_id == item["tenant"]
            )
            assert verify_receipt_bundle(
                evidence_bundle(project_receipt(conn, item["op"]), result.receipt_jws),
                trust=trust,
            ).status == ("FAILED" if failed else "SUCCEEDED")


@pytest.mark.parametrize("fault", ["lock_timeout", "statement_timeout", "terminate_backend"])
def test_signing_and_real_database_faults_keep_pending(ledger, dsn, downstream_dsn, fault):
    from agent_guard.execution.receipt_publication import InternalPublisher

    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    before = full_state(dsn, downstream_dsn)
    publisher = InternalPublisher(
        dsn,
        private_key=key,
        signing_kid="gw-receipt-1",
        verifier=verifier,
        lock_timeout_ms=100 if fault == "lock_timeout" else 10000,
        statement_timeout_ms=100 if fault == "statement_timeout" else 15000,
    )
    with psycopg.connect(dsn) as blocker:
        blocker.execute(
            "SELECT operation_id FROM ag_receipt_outbox WHERE operation_id=%s FOR UPDATE",
            (op,),
        )
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(publisher.publish, op)
            if fault == "terminate_backend":
                with psycopg.connect(dsn, autocommit=True) as observer:
                    bound = time.monotonic() + 5
                    row = None
                    while time.monotonic() < bound:
                        row = observer.execute(
                            "SELECT pid,query FROM pg_stat_activity WHERE "
                            "datname=current_database() AND wait_event_type='Lock' AND"
                            " query LIKE 'SELECT operation_id FROM ag_receipt_outbox%'"
                        ).fetchone()
                        if row:
                            break
                        time.sleep(0.005)
                    assert row and "FOR UPDATE" in row[1]
                    assert observer.execute(
                        "SELECT pg_terminate_backend(%s)", (row[0],)
                    ).fetchone() == (True,)
            with pytest.raises(LedgerError) as exc:
                future.result(5)
            assert isinstance(exc.value.__cause__, psycopg.Error)
            if fault == "lock_timeout":
                assert exc.value.__cause__.sqlstate == "55P03"
            if fault == "statement_timeout":
                assert exc.value.__cause__.sqlstate == "57014"
        blocker.rollback()
    assert full_state(dsn, downstream_dsn) == before
    assert receipt_services(env, dsn, gateway_key=key)[2].publish(op).receipt_status == "READY"


@pytest.mark.parametrize("group", ["publisher-query", "publisher-retry"])
@pytest.mark.parametrize("round", range(10))
def test_publish_query_retry_recovery_races_ten_rounds(ledger, dsn, downstream_dsn, group, round):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    barrier = threading.Barrier(2)
    bundle = query_bundle(env, op) if group == "publisher-query" else env.bundle()
    before = full_state(dsn, downstream_dsn)

    def publish():
        barrier.wait(5)
        return publisher.publish(op)

    def public():
        barrier.wait(5)
        return (
            AuthorizedQuery(dsn, evidence_store=env.evidence, receipt_verifier=verifier).query(
                bundle
            )
            if group == "publisher-query"
            else env.adapter.accept_response(bundle, receipt_verifier=verifier)
        )

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(publish), pool.submit(public)]
        results = collect_futures(futures)
    assert results[0].receipt_status == "READY"
    assert results[1]["operation_id"] == op and results[1]["receipt_status"] in (
        "PENDING",
        "READY",
    )
    after = full_state(dsn, downstream_dsn)
    if group == "publisher-query":
        from tests.fixtures.receipts import result_read_only

        result_read_only(
            before,
            after,
            evidence_ref=bundle.evidence_ref,
            proof_jti=bundle.query.proof_jti,
            operation_id=op,
            publication=True,
        )
    else:
        from tests.fixtures.receipts import accept_retry_only

        accept_retry_only(
            before,
            after,
            evidence_ref=bundle.evidence_ref,
            proof_jti=bundle.invocation.proof_jti,
            operation_id=op,
            publication=True,
        )


@pytest.mark.parametrize("tool", ["procurement.request.read", "notification.template.send"])
def test_zero_amount_terminal_publication_only_three_fields(ledger, dsn, downstream_dsn, tool):
    env, previous, key, verifier, publisher = final_env(dsn, downstream_dsn)
    params = (
        {"request_id": "req-001"}
        if tool == "procurement.request.read"
        else {
            "template_id": "order-created",
            "recipient_id": "user-demo-001",
            "operation_id": previous,
        }
    )
    op = env.adapter.accept(env.bundle("zero-cost", tool=tool, params=params)).operation_id
    assert env.service.run_operation(op).status == "SUCCEEDED"
    before = full_state(dsn, downstream_dsn)
    result = publisher.publish(op)
    assert (
        verify_compact_jws(
            result.receipt_jws,
            expected_type="ag-receipt+jwt",
            trusted_keys=verifier.gateway_keys,
        )["amount_fen"]
        == 0
    )
    publication_only(before, full_state(dsn, downstream_dsn))


def test_legal_zero_price_order_publishes_without_current_quote(ledger, dsn, downstream_dsn):
    from dataclasses import replace

    env = signed_env(dsn, downstream_dsn)
    catalog = env.service._catalog
    quote = catalog._quotes[("quote-001", "1")]
    catalog._quotes[("quote-001", "1")] = replace(
        quote, lines=tuple(replace(line, unit_price_fen=0) for line in quote.lines)
    )
    op = env.adapter.accept(env.bundle("zero-price-order")).operation_id
    assert env.service.run_operation(op).status == "SUCCEEDED"
    # Historical publication must not need the mutable pricing source.
    catalog._quotes.clear()
    _, verifier, publisher = receipt_services(env, dsn)
    before = full_state(dsn, downstream_dsn)
    ready = publisher.publish(op)
    assert ready.receipt_status == "READY"
    publication_only(before, full_state(dsn, downstream_dsn))
    with psycopg.connect(dsn) as conn:
        projection = verifier.verify_tx(conn, op, ready.receipt_jws)
        result = verify_receipt_bundle(
            evidence_bundle(projection, ready.receipt_jws), trust=verifier._trust_tx(conn, op)
        )
        assert result.amount_fen == 0 and result.anchoring_status == "UNANCHORED"
        assert (
            conn.execute(
                "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled "
                "FROM ag_grants ORDER BY depth"
            ).fetchall()
            == [(0, 0, 0, 1)] * 3
        )
    with psycopg.connect(downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_orders").fetchone() == (1,)


def test_pending_nonnull_timestamp_fails_closed(ledger, dsn, downstream_dsn):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    with psycopg.connect(dsn) as conn:
        created = store.fetch_outbox(conn, op)["created_at"]
    with CorruptRow(dsn, "ag_receipt_outbox", {"operation_id": op}, {"signed_at": created}):
        before = full_state(dsn, downstream_dsn)
        with pytest.raises(EvidenceError):
            publisher.publish(op)
        assert full_state(dsn, downstream_dsn) == before
    assert publisher.publish(op).receipt_status == "READY"


@pytest.mark.parametrize(
    "column",
    [
        "receipt_status",
        "receipt_jws",
        "signed_at",
        "receipt_id",
        "result_bytes",
        "ledger_changes_json",
    ],
)
def test_ready_original_bytes_are_protected_by_real_pg_trigger(ledger, dsn, downstream_dsn, column):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    publisher.publish(op)
    before = full_state(dsn, downstream_dsn)
    values = {
        "receipt_status": "PENDING",
        "receipt_jws": "bad",
        "signed_at": None,
        "receipt_id": "bad",
        "result_bytes": b"{}",
        "ledger_changes_json": b"{}",
    }
    with psycopg.connect(dsn) as conn:
        with pytest.raises(psycopg.Error) as exc:
            with conn.transaction():
                conn.execute(
                    psycopg.sql.SQL(
                        "UPDATE ag_receipt_outbox SET {}=%s WHERE operation_id=%s"
                    ).format(psycopg.sql.Identifier(column)),
                    (values[column], op),
                )
        assert exc.value.sqlstate == "23514"
    assert full_state(dsn, downstream_dsn) == before


@pytest.mark.parametrize("ancestor", range(3))
@pytest.mark.parametrize("mutation", ["token-signature", "token-digest", "holder-spki"])
def test_each_persisted_ancestor_original_material_is_required(
    ledger, dsn, downstream_dsn, ancestor, mutation
):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT g.grant_id,t.token_jws,t.token_sm3,t.holder_spki_sm3 "
            "FROM ag_grants g JOIN ag_grant_tokens t USING(grant_id) ORDER BY g.depth"
        ).fetchall()[ancestor]
    field, value = {
        "token-signature": ("token_jws", row[1] + "x"),
        "token-digest": ("token_sm3", "A" * 43),
        "holder-spki": ("holder_spki_sm3", "B" * 43),
    }[mutation]
    with CorruptRow(dsn, "ag_grant_tokens", {"grant_id": row[0]}, {field: value}):
        before = full_state(dsn, downstream_dsn)
        with pytest.raises(EvidenceError):
            publisher.publish(op)
        assert full_state(dsn, downstream_dsn) == before
    before = full_state(dsn, downstream_dsn)
    assert publisher.publish(op).receipt_status == "READY"
    publication_only(before, full_state(dsn, downstream_dsn))


def test_internal_publication_after_actual_expiry_preserves_external_denial(
    ledger, dsn, downstream_dsn
):
    from agent_guard.execution.query import AuthorizedQuery
    from tests.fixtures.gateway import query_bundle, signed_env_window

    env = signed_env_window(dsn, downstream_dsn, "leaf")
    op = env.adapter.accept(env.bundle()).operation_id
    assert env.service.run_operation(op).status == "SUCCEEDED"
    key, verifier, publisher = receipt_services(env, dsn)
    query = query_bundle(env, op)
    with psycopg.connect(dsn, autocommit=True) as conn:
        deadline = conn.execute(
            "SELECT extract(epoch FROM expires_at) FROM ag_grants WHERE depth=2"
        ).fetchone()[0]
        while conn.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0] < deadline:
            time.sleep(0.01)
    before = full_state(dsn, downstream_dsn)
    assert publisher.publish(op).receipt_status == "READY"
    publication_only(before, full_state(dsn, downstream_dsn))
    ready = full_state(dsn, downstream_dsn)
    with pytest.raises(LedgerError):
        AuthorizedQuery(dsn, evidence_store=env.evidence, receipt_verifier=verifier).query(query)
    assert full_state(dsn, downstream_dsn) == ready


@pytest.mark.parametrize("state", ["RESERVED", "EXECUTING", "UNKNOWN"])
@pytest.mark.parametrize("publication", ["PENDING", "READY"])
def test_nonterminal_with_illegal_final_outbox_fails_closed(
    ledger, dsn, downstream_dsn, state, publication
):
    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    if publication == "READY":
        publisher.publish(op)
    with CorruptRow(dsn, "ag_operations", {"operation_id": op}, {"status": state}):
        before = full_state(dsn, downstream_dsn)
        with psycopg.connect(dsn) as conn:
            with pytest.raises(EvidenceError):
                verifier.read_tx(conn, op)
        with pytest.raises(EvidenceError):
            publisher.publish(op)
        assert full_state(dsn, downstream_dsn) == before


@pytest.mark.parametrize("group", ["revoke-external-query", "disable-external-accept"])
@pytest.mark.parametrize("winner", ["authorize", "mutation"])
@pytest.mark.parametrize("round", range(10))
def test_ready_external_mutation_races_follow_actual_lock_order(
    ledger, dsn, downstream_dsn, monkeypatch, group, winner, round
):
    from tests.integration.test_gateway_query import _wait_blocked

    env, op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    publisher.publish(op)
    bundle = query_bundle(env, op) if group == "revoke-external-query" else env.bundle()
    before = full_state(dsn, downstream_dsn)
    sync = threading.Barrier(2)

    def mutate(conn):
        if group == "revoke-external-query":
            conn.execute("SELECT * FROM ag_tasks FOR UPDATE")
            conn.execute("UPDATE ag_grants SET revoked=true WHERE depth=0")
        else:
            conn.execute("UPDATE ag_principals SET active=false WHERE client_id='agent-executor'")

    def authorize():
        return (
            AuthorizedQuery(dsn, evidence_store=env.evidence, receipt_verifier=verifier).query(
                bundle
            )
            if group == "revoke-external-query"
            else env.adapter.accept_response(bundle, receipt_verifier=verifier)
        )

    with psycopg.connect(dsn, autocommit=True) as observer, ThreadPoolExecutor(1) as pool:
        if winner == "mutation":
            with psycopg.connect(dsn) as blocker:
                mutate(blocker)

                def blocked_authorize():
                    sync.wait(5)
                    return authorize()

                future = pool.submit(blocked_authorize)
                sync.wait(5)
                _wait_blocked(
                    observer,
                    blocker.info.backend_pid,
                    "FROM ag_tasks" if group == "revoke-external-query" else "FROM ag_principals",
                )
                blocker.commit()
                with pytest.raises(LedgerError):
                    future.result(5)
        else:
            futures = []
            original = verifier.read_tx

            def mutate_other():
                sync.wait(5)
                with psycopg.connect(dsn) as conn:
                    mutate(conn)

            def held(conn, operation):
                result = original(conn, operation)
                futures.append(pool.submit(mutate_other))
                sync.wait(5)
                _wait_blocked(
                    observer,
                    conn.info.backend_pid,
                    "FROM ag_tasks" if group == "revoke-external-query" else "UPDATE ag_principals",
                )
                return result

            monkeypatch.setattr(verifier, "read_tx", held)
            assert authorize()["receipt_status"] == "READY"
            assert len(futures) == 1
            futures[0].result(5)
    after = full_state(dsn, downstream_dsn)
    assert after["downstream"] == before["downstream"]
    mutable = "ag_grants" if group == "revoke-external-query" else "ag_principals"
    column = "revoked" if group == "revoke-external-query" else "active"
    changed = 0
    # Normalize only the one authorized mutation column, preserving every
    # ancestor counter and all other table/row/column effects exactly.
    oldrows = [json.loads(row[0]) for row in before["gateway"][mutable]]
    newrows = [json.loads(row[0]) for row in after["gateway"][mutable]]
    primary = (
        ("grant_id",) if group == "revoke-external-query" else ("tenant_id", "client_id", "kid")
    )
    oldmap = {tuple(r[k] for k in primary): r for r in oldrows}
    for row in newrows:
        old = oldmap[tuple(row[k] for k in primary)]
        if row[column] != old[column]:
            changed += 1
            assert row[column] is (True if column == "revoked" else False)
        row[column] = old[column]
        assert row == old
    assert changed == 1
    after["gateway"][mutable] = before["gateway"][mutable]
    if winner == "mutation":
        assert after == before
    elif group == "disable-external-accept":
        from tests.fixtures.receipts import accept_retry_only

        accept_retry_only(
            before,
            after,
            evidence_ref=bundle.evidence_ref,
            proof_jti=bundle.invocation.proof_jti,
            operation_id=op,
        )
    else:
        from tests.fixtures.receipts import result_read_only

        result_read_only(
            before,
            after,
            evidence_ref=bundle.evidence_ref,
            proof_jti=bundle.query.proof_jti,
            operation_id=op,
        )


@pytest.mark.parametrize("round", range(10))
def test_two_signed_recoverers_and_stale_fenced_owner_then_single_publication(
    ledger, dsn, downstream_dsn, round
):
    from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode
    from tests.fixtures.execution import expire_lease

    env = signed_env(dsn, downstream_dsn)
    op = env.adapter.accept(env.bundle()).operation_id
    captured = []

    def hold(claim, outcome):
        captured.append((claim, outcome))
        raise RuntimeError("owned old worker suspended before terminal write")

    with pytest.raises(RuntimeError, match="suspended"):
        env.service.run_operation(op, owner_token="a23-old-owner", pause=hold)
    expire_lease(dsn, op)
    before = full_state(dsn, downstream_dsn)
    barrier = threading.Barrier(2)

    def recover(owner):
        barrier.wait(5)
        return env.service.reconcile(op, owner_token=owner)

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(recover, owner) for owner in ("a23-new-owner-A", "a23-new-owner-B")]
        outcomes, errors = [], []
        for future in futures:
            try:
                outcomes.append(future.result(10))
            except Exception as exc:
                errors.append(exc)
    assert len(outcomes) == len(errors) == 1 and outcomes[0].status == "SUCCEEDED"
    assert isinstance(errors[0], ExecutionError) and errors[0].code in (
        ExecutionErrorCode.LEASE_LOST,
        ExecutionErrorCode.ILLEGAL_TRANSITION,
    )
    recovered = full_state(dsn, downstream_dsn)
    assert recovered["downstream"] == before["downstream"]
    with psycopg.connect(dsn) as conn:
        assert (
            conn.execute(
                "SELECT "
                "amount_reserved,amount_settled,calls_reserved,calls_settled FROM ag_g"
                "rants ORDER BY depth"
            ).fetchall()
            == [(0, 70000, 0, 1)] * 3
        )
        assert conn.execute("SELECT count(*) FROM ag_ledger_events").fetchone() == (2,)
        assert conn.execute("SELECT count(*) FROM ag_ledger_event_nodes").fetchone() == (6,)
        assert conn.execute("SELECT count(*) FROM ag_receipt_outbox").fetchone() == (1,)
    old_claim, old_outcome = captured[0]
    with pytest.raises(ExecutionError):
        env.service._finalize(old_claim, old_outcome, downstream_called=True, reason="")
    assert full_state(dsn, downstream_dsn) == recovered
    _, verifier, publisher = receipt_services(env, dsn)
    assert publisher.publish(op).receipt_status == "READY"
    publication_only(recovered, full_state(dsn, downstream_dsn))


@pytest.mark.parametrize("sku_width", [12, 16, 17])
def test_real_as_bounded_capacity_preflight(ledger, dsn, downstream_dsn, sku_width):
    import rfc8785

    from agent_guard.contracts.encoding import MAX_SAFE_INTEGER
    from tests.fixtures.receipts import result_read_only

    quantity = MAX_SAFE_INTEGER // 256
    details = {
        "sku_width": sku_width,
        "quantity": quantity,
        "unit_price_fen": 1,
        "total": 256 * quantity,
        "phase": "actual-AS-root-two-exchanges",
        "outcome": "RUNNING",
    }

    def record():
        output = os.environ.get("A23_RECEIPT_EVIDENCE")
        if output:
            label = os.environ.get("A23_RUN_LABEL", "capacity-preflight")
            Path(output, f"{label}-capacity-width-{sku_width}.json").write_text(
                json.dumps(details, indent=2)
            )

    try:
        env = real_login_capacity_env(
            dsn, downstream_dsn, sku_width=sku_width, quantity=quantity, budget=MAX_SAFE_INTEGER
        )
        _, verifier, publisher = receipt_services(env, dsn)
        params = {
            "request_id": "req-001",
            "quote_id": "quote-001",
            "quote_version": "1",
            "items": [
                {"sku": f"s{i:03d}" + "x" * (sku_width - 4), "quantity": quantity}
                for i in range(256)
            ],
            "delivery_id": "office-001",
        }
        details["phase"] = "original-permission-source-and-invocation-verification"
        invocation = env.bundle("bounded-capacity", params=params)
        details["permission_source_bytes"] = len(invocation.source.material())
        token, proof, body = raw_material(dsn, invocation)
        details["request_body_bytes"] = len(body)
        details["phase"] = "actual-public-gateway-accept"
        application = GatewayHttpApp(
            GatewayEndpoint(
                verifier=env.verifier,
                execution=env.adapter,
                queries=AuthorizedQuery(
                    dsn, evidence_store=env.evidence, receipt_verifier=verifier
                ),
                receipt_verifier=verifier,
            )
        )
        status, accepted, _ = request(
            application,
            body=body,
            headers=[
                (b"content-type", b"application/json"),
                (b"authorization", b"AGPoP " + token),
                (b"ag-proof", proof),
            ],
        )
        details["public_accept_status"] = status
        assert status == 202, accepted
        op = accepted["operation_id"]
        details["phase"] = "actual-downstream-terminal"
        assert env.service.run_operation(op).status == "SUCCEEDED"
        before = full_state(dsn, downstream_dsn)
        with psycopg.connect(dsn) as conn:
            projection = project_receipt(conn, op)
            signed = sign_compact_jws(
                publisher._private_key,
                load_strict_json(projection.claims_bytes),
                key_id="gw-receipt-1",
                token_type="ag-receipt+jwt",
            )
            bundle = evidence_bundle(projection, signed)
            details["components"] = {
                k: len(canonical_json_bytes(v)) for k, v in bundle.items() if k != "ledger_changes"
            }
            details["ledger_bytes"] = len(projection.ledger_bytes)
            details["quote_bytes"] = len(bytes(store.fetch_operation(conn, op).quote_snapshot))
            details["jws_lengths"] = {
                "ancestor" + str(i): len(t) for i, t in enumerate(projection.ancestor_tokens)
            }
            details["jws_lengths"].update(proof=len(proof), receipt=len(signed))
            details["sdk_nonledger_actual_canonical_bytes"] = len(
                rfc8785.dumps({k: v for k, v in bundle.items() if k != "ledger_changes"})
            )
            assert all(n <= 16384 for n in details["jws_lengths"].values())
            assert details["permission_source_bytes"] <= 65536
            trust = verifier._trust_tx(conn, op)
            details["phase"] = "component-SDK-preflight"
            record()
            verify_receipt_bundle(bundle, trust=trust)
        details["phase"] = "InternalPublisher.publish"
        publication = publisher.publish(op)
        assert publication.receipt_status == "READY"
        published = full_state(dsn, downstream_dsn)
        publication_only(before, published)
        assert publisher.publish(op) == publication
        assert full_state(dsn, downstream_dsn) == published
        with psycopg.connect(dsn) as conn:
            assert (
                conn.execute(
                    "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled "
                    "FROM ag_grants ORDER BY depth"
                ).fetchall()
                == [(0, 256 * quantity, 0, 1)] * 3
            )
            assert conn.execute("SELECT count(*) FROM ag_ledger_events").fetchone() == (2,)
            assert conn.execute("SELECT count(*) FROM ag_ledger_event_nodes").fetchone() == (6,)
            assert conn.execute("SELECT count(*) FROM ag_receipt_outbox").fetchone() == (1,)
            actual = evidence_bundle(project_receipt(conn, op), publication.receipt_jws)
            verified = verify_receipt_bundle(actual, trust=verifier._trust_tx(conn, op))
            assert verified.amount_fen == 256 * quantity
            assert verified.operation_id == op and verified.status == "SUCCEEDED"
            details["sdk_outer_exact_bytes"] = len(rfc8785.dumps(actual))
        with psycopg.connect(downstream_dsn) as conn:
            assert conn.execute("SELECT count(*) FROM ds_orders").fetchone() == (1,)
        details["phase"] = "current-query-and-offline"
        current = query_bundle(env, op)
        query_before = full_state(dsn, downstream_dsn)
        query_token, query_proof, query_body = raw_material(dsn, current)
        status, response, _ = request(
            application,
            path="/v1/operations/query",
            body=query_body,
            headers=[
                (b"content-type", b"application/json"),
                (b"authorization", b"AGPoP " + query_token),
                (b"ag-proof", query_proof),
            ],
        )
        assert status == 200 and response["receipt_status"] == "READY"
        assert response["receipt_jws"] == publication.receipt_jws
        details["public_envelope_bytes"] = len(canonical_json_bytes(response))
        assert details["public_envelope_bytes"] <= 65536
        with psycopg.connect(dsn) as conn:
            actual_ref = conn.execute(
                "SELECT evidence_ref FROM ag_proofs WHERE proof_jti=%s AND purpose='result-read'",
                (current.query.proof_jti,),
            ).fetchone()[0]
            material = conn.execute(
                "SELECT token_bytes,proof_bytes,body_bytes FROM "
                "ag_verified_evidence WHERE evidence_ref=%s",
                (actual_ref,),
            ).fetchone()
            assert tuple(bytes(v) for v in material) == (query_token, query_proof, query_body)
        result_read_only(
            query_before,
            full_state(dsn, downstream_dsn),
            proof_jti=current.query.proof_jti,
            evidence_ref=actual_ref,
            operation_id=op,
            staging=True,
        )
        details["full_effect_oracle"] = (
            "all ag_* and ds_* rows exact; only publication3, query STAGED1/proof1"
        )
        details["outcome"] = "COMPLETE_LEGAL_PIPELINE_PASS"
    except Exception as exc:
        details["exception"] = {"type": type(exc).__name__, "text": str(exc)}
        details["outcome"] = (
            "SDK_COMPONENT_OR_CONSISTENCY_FAILURE"
            if details["phase"] == "component-SDK-preflight"
            else "REAL_PRECONDITION_REJECTION_OR_FAILURE"
        )
        with psycopg.connect(dsn) as conn:
            details["persisted_AS_tokens"] = conn.execute(
                "SELECT g.depth,length(t.token_jws),g.amount_limit FROM "
                "ag_grants g JOIN ag_grant_tokens t USING(grant_id) ORDER BY g.depth"
            ).fetchall()
        record()
        raise
    record()


def test_rotation_new_pending_and_bundle_self_key_never_supply_trust(ledger, dsn, downstream_dsn):
    from agent_guard.contracts.encoding import b64url_decode
    from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
    from agent_guard.evidence.receipt import ReceiptVerificationError
    from agent_guard.execution.receipt_publication import InternalPublisher, ReceiptVerifier

    env, old_op, key, verifier, publisher = final_env(dsn, downstream_dsn)
    old_ready = publisher.publish(old_op)
    new_key = generate_sm2_private_key()
    rotated = ReceiptVerifier(
        issuer=verifier.issuer,
        as_keys=verifier.as_keys,
        gateway_keys={**verifier.gateway_keys, "gw-receipt-new": new_key.public_key()},
        registrations=verifier.registrations,
        permission_provider=verifier.permission_provider,
    )
    new_publisher = InternalPublisher(
        dsn, private_key=new_key, signing_kid="gw-receipt-new", verifier=rotated
    )
    new_op = env.adapter.accept(
        env.bundle(
            "rotation-new", tool="procurement.request.read", params={"request_id": "req-001"}
        )
    ).operation_id
    assert env.service.run_operation(new_op).status == "SUCCEEDED"
    before = full_state(dsn, downstream_dsn)
    ready = new_publisher.publish(new_op)
    publication_only(before, full_state(dsn, downstream_dsn))
    header = load_strict_json(b64url_decode(ready.receipt_jws.split(".")[0]))
    assert header["kid"] == "gw-receipt-new"
    published = full_state(dsn, downstream_dsn)
    assert new_publisher.publish(old_op) == old_ready
    assert new_publisher.publish(new_op) == ready
    with psycopg.connect(dsn) as conn:
        projection = project_receipt(conn, new_op)
        trust = rotated._trust_tx(conn, new_op)
        actual = evidence_bundle(projection, ready.receipt_jws)
        assert verify_receipt_bundle(actual, trust=trust).operation_id == new_op
        outsider = generate_sm2_private_key()
        forged = sign_compact_jws(
            outsider,
            load_strict_json(projection.claims_bytes),
            key_id="untrusted-bundle-key",
            token_type="ag-receipt+jwt",
        )
        untrusted = evidence_bundle(projection, forged)
        with pytest.raises(ReceiptVerificationError):
            verify_receipt_bundle(untrusted, trust=trust)
        untrusted["gateway_keys"] = {
            "untrusted-bundle-key": serialize_sm2_public_key(outsider.public_key()).hex()
        }
        with pytest.raises(ReceiptVerificationError, match="evidence bundle fields"):
            verify_receipt_bundle(untrusted, trust=trust)
    assert full_state(dsn, downstream_dsn) == published
