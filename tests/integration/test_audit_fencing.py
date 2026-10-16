"""Legal same-TX terminal fence and genuine head wait crossing lease expiry."""

from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode
from tests.fixtures.a31_common import (
    read_records,
    state,
    wait_for_blocked,
    wait_past_database_deadline,
)
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("expired", (False, True))
def test_terminal_final_fence_after_journal_wait(ledger, dsn, downstream_dsn, expired, round):
    env = signed_env(dsn, downstream_dsn)
    env.service._lease_ttl = 2
    env.service._lock_timeout_ms = 180000
    env.service._statement_timeout_ms = 180000
    op = env.adapter.accept(env.bundle()).operation_id
    before = []
    claim_holder = []
    with (
        psycopg.connect(dsn) as lock,
        psycopg.connect(dsn, autocommit=True) as observer,
    ):
        lock.execute("SELECT head_seq FROM ag_audit_streams FOR UPDATE")
        blocker = lock.execute("SELECT pg_backend_pid()").fetchone()[0]

        def pause(claim, outcome):
            assert outcome is not None
            claim_holder.append(claim)
            before.append(state(dsn, downstream_dsn))

        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(env.service.run_operation, op, pause=pause)
            try:
                pids = wait_for_blocked(
                    observer,
                    blocker_pid=blocker,
                    table="ag_audit_streams",
                    futures=(future,),
                )
                assert len(pids) == 1 and len(before) == 1 and len(claim_holder) == 1
                expiry = observer.execute(
                    (
                        "SELECT extract(epoch FROM lease_expires_at) FROM ag_execution_leases "
                        "WHERE operation_id=%s"
                    ),
                    (op,),
                ).fetchone()[0]
                if expired:
                    wait_past_database_deadline(observer, expiry)
                else:
                    assert (
                        observer.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[
                            0
                        ]
                        < expiry
                    )
            finally:
                lock.commit()
            if expired:
                with pytest.raises(ExecutionError) as caught:
                    future.result(180)
                assert caught.value.code is ExecutionErrorCode.LEASE_LOST
                assert state(dsn, downstream_dsn) == before[0]
                # DS effect remains durable, reservation remains held. A later
                # legitimate owner recovers the original intent with no new effect.
                assert (
                    env.service.reconcile(op, owner_token="new-recovery-owner").status
                    == "SUCCEEDED"
                )
            else:
                assert future.result(180).status == "SUCCEEDED"
    records = read_records(dsn)
    assert [r.kind for r in records] == ["BOOTSTRAP", "FIRST", "TERMINAL"]
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_receipt_outbox").fetchone() == (1,)
        assert conn.execute(
            "SELECT count(*) FROM ag_ledger_events WHERE phase='SETTLE'"
        ).fetchone() == (1,)
