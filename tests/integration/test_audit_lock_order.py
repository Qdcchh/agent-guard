"""Independent backend contention exercises the actual outbox-to-head order."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import psycopg
import pytest

from tests.fixtures.a31_common import read_records, wait_for_blocked
from tests.fixtures.receipts import collect_futures, receipt_services
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("round", range(10))
def test_pending_publishers_and_retry_share_existing_head(ledger, dsn, downstream_dsn, round):
    env = signed_env(dsn, downstream_dsn)
    op = env.adapter.accept(env.bundle()).operation_id
    assert env.service.run_operation(op).status == "SUCCEEDED"
    _, verifier, publisher = receipt_services(env, dsn)
    bundle = env.bundle()
    barrier = Barrier(3)

    def publish():
        barrier.wait(15)
        return publisher.publish(op)

    def retry():
        barrier.wait(15)
        return env.adapter.accept(bundle)

    with (
        psycopg.connect(dsn) as lock,
        psycopg.connect(dsn, autocommit=True) as observer,
    ):
        lock.execute("SELECT head_seq FROM ag_audit_streams FOR UPDATE")
        blocker = lock.execute("SELECT pg_backend_pid()").fetchone()[0]
        pool = ThreadPoolExecutor(3)
        futures = [pool.submit(publish), pool.submit(publish), pool.submit(retry)]
        try:
            try:
                pids = wait_for_blocked(
                    observer,
                    blocker_pid=blocker,
                    table="ag_audit_streams",
                    futures=futures,
                )
                assert pids and blocker not in pids
            finally:
                lock.rollback()
        finally:
            try:
                results = collect_futures(futures, timeout=60)
                assert len(results) == 3
            finally:
                pool.shutdown(wait=True)
    records = read_records(dsn)
    assert sorted(r.kind for r in records) == sorted(
        ["BOOTSTRAP", "FIRST", "TERMINAL", "PUBLISH", "RETRY"]
    )
    assert [r.seq for r in records] == list(range(1, 6))
    with psycopg.connect(dsn) as conn:
        receipt = conn.execute("SELECT receipt_jws FROM ag_receipt_outbox").fetchone()[0]
    assert receipt
    with psycopg.connect(dsn) as conn:
        verifier.verify_tx(conn, op, receipt)


@pytest.mark.parametrize("route", ("query", "retry"))
@pytest.mark.parametrize("round", range(10))
def test_publisher_parent_locks_precede_head(
    ledger, dsn, downstream_dsn, monkeypatch, route, round
):
    from threading import Event

    from agent_guard.execution.query import AuthorizedQuery
    from tests.fixtures.a31_common import state
    from tests.fixtures.gateway import query_bundle
    from tests.fixtures.receipts import accept_retry_only, publication_only, result_read_only

    env = signed_env(dsn, downstream_dsn)
    op = env.adapter.accept(env.bundle()).operation_id
    assert env.service.run_operation(op).status == "SUCCEEDED"
    _, verifier, publisher = receipt_services(env, dsn)
    bundle = query_bundle(env, op) if route == "query" else env.bundle()
    before = state(dsn, downstream_dsn)
    entered, release = Event(), Event()
    backend = []

    def pause(conn):
        backend.append(conn.info.backend_pid)
        entered.set()
        assert release.wait(20), "finite public-path pause"

    if route == "query":
        factory = env.evidence.query_binding

        def held(candidate):
            original = factory(candidate)

            def bind(conn):
                original(conn)
                pause(conn)

            return bind

        monkeypatch.setattr(env.evidence, "query_binding", held)

        def invoke():
            return AuthorizedQuery(dsn, evidence_store=env.evidence).query(bundle)
    else:
        factory = env.evidence.binding

        def held(candidate):
            return factory(candidate).compose(lambda conn, operation, disposition: pause(conn))

        monkeypatch.setattr(env.evidence, "binding", held)

        def invoke():
            return env.adapter.accept(bundle)

    with (
        psycopg.connect(dsn) as head,
        psycopg.connect(dsn, autocommit=True) as observer,
        ThreadPoolExecutor(2) as pool,
    ):
        if route == "retry":
            head.execute("SELECT head_seq FROM ag_audit_streams FOR UPDATE")
        public = pool.submit(invoke)
        publication = None
        try:
            assert entered.wait(15) and len(backend) == 1
            publication = pool.submit(publisher.publish, op)
            if route == "query":
                pids = wait_for_blocked(
                    observer,
                    blocker_pid=backend[0],
                    table="ag_operations",
                    futures=[publication],
                )
                assert len(pids) == 1 and backend[0] not in pids
                # A separate backend really obtains the head while publisher
                # waits on the strong operation lock held by public query.
                head.execute("SELECT head_seq FROM ag_audit_streams FOR UPDATE NOWAIT")
                head.rollback()
                release.set()
                response = public.result(20)
                published = publication.result(20)
                assert response["status"] == "SUCCEEDED"
                result_read_only(
                    before,
                    state(dsn, downstream_dsn),
                    evidence_ref=bundle.evidence_ref,
                    proof_jti=bundle.query.proof_jti,
                    operation_id=op,
                    publication=True,
                    observed_response=response,
                )
            else:
                pids = wait_for_blocked(
                    observer,
                    blocker_pid=head.info.backend_pid,
                    table="ag_audit_streams",
                    futures=[publication],
                )
                assert len(pids) == 1 and backend[0] not in pids
                assert not observer.execute(
                    "SELECT pg_blocking_pids(%s)", (backend[0],)
                ).fetchone()[0]
                head.rollback()
                published = publication.result(20)
                intermediate = state(dsn, downstream_dsn)
                publication_only(before, intermediate)
                release.set()
                response = public.result(20)
                assert response.operation_id == op and response.status == "SUCCEEDED"
                accept_retry_only(
                    intermediate,
                    state(dsn, downstream_dsn),
                    evidence_ref=bundle.evidence_ref,
                    proof_jti=bundle.invocation.proof_jti,
                    operation_id=op,
                )
            print("REAL_PARENT_HEAD_ORDER", route, round, backend[0], sorted(pids))
            assert published.receipt_status == "READY" and published.receipt_jws
        finally:
            head.rollback()
            release.set()
            collect_futures([public] + ([publication] if publication else []), timeout=30)
    stable = state(dsn, downstream_dsn)
    assert publisher.publish(op).receipt_jws == published.receipt_jws
    assert state(dsn, downstream_dsn) == stable
    with psycopg.connect(dsn) as conn:
        verifier.verify_tx(conn, op, published.receipt_jws)


@pytest.mark.parametrize("parent", ("operation", "evidence"))
def test_journal_missing_parent_fails_closed(ledger, dsn, downstream_dsn, parent):
    from agent_guard.audit import journal
    from agent_guard.contracts.encoding import canonical_json_bytes
    from tests.fixtures.a31_common import state

    env = signed_env(dsn, downstream_dsn)
    bundle = env.bundle()
    op = env.adapter.accept(bundle).operation_id
    before = state(dsn, downstream_dsn)
    with pytest.raises(journal.JournalError) as failure, psycopg.connect(dsn) as conn:
        stream = journal.require_stream_tx(
            conn, bundle.invocation.tenant_id, bundle.invocation.task_id
        )
        journal.append_tx(
            conn,
            stream,
            kind="FIRST",
            operation_id="missing-operation" if parent == "operation" else op,
            evidence_ref="missing-evidence" if parent == "evidence" else bundle.evidence_ref,
            facts_bytes=canonical_json_bytes({}),
        )
    assert str(failure.value) == (
        "missing operation material" if parent == "operation" else "missing signed request material"
    )
    assert getattr(failure.value, "sqlstate", None) is None
    assert state(dsn, downstream_dsn) == before
