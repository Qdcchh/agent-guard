"""F5 regressions: connection and configuration bounds (no database needed).

Uses a connection-factory double to verify parameter passing and exception
mapping. This is not a real network black-hole experiment and must not be
reported as one.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from agent_guard.contracts.ledger import ErrorCode, LedgerError
from agent_guard.ledger.service import ExecutionLedger
from tests.fixtures.state import TreeFixture

pytestmark = pytest.mark.unit


class RecordingConnector:
    """Connection-factory double: records kwargs, then fails like a dead socket."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.error = error or psycopg.OperationalError("connection refused (double)")

    def __call__(self, dsn: str, **kwargs):
        self.calls.append({"dsn": dsn, **kwargs})
        raise self.error


class FakeCursor:
    def __init__(self, records: list) -> None:
        self._records = records

    def fetchone(self):
        return self._records.pop(0) if self._records else None


class FakeConnection:
    """Minimal connection double recording every executed statement."""

    def __init__(self) -> None:
        self.executed: list[tuple] = []
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return FakeCursor([])

    def transaction(self):  # pragma: no cover - exercised via contextlib
        import contextlib

        return contextlib.nullcontext()

    def close(self) -> None:
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _tree() -> TreeFixture:
    now = datetime.now(tz=timezone.utc)
    return TreeFixture(
        tenant_id="t",
        task_id="k",
        subject="s",
        root_id="r",
        mid_id="m",
        leaf_id="l",
        planner=("p", "pk"),
        selector=("s", "sk"),
        executor=("e", "ek"),
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        amount_limits=(1, 1, 1),
        call_limits=(1, 1, 1),
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"connect_timeout_s": 0},
        {"connect_timeout_s": -1},
        {"connect_timeout_s": 61},
        {"connect_timeout_s": True},
        {"connect_timeout_s": 2.5},
        {"lock_timeout_ms": 0},
        {"lock_timeout_ms": -5},
        {"lock_timeout_ms": 600_001},
        {"statement_timeout_ms": 0},
        {"statement_timeout_ms": 10**7},
        {"max_retries": 0},
        {"max_retries": -1},
        {"max_retries": 11},
        {"max_retries": False},
    ],
)
def test_f5_rejects_unbounded_or_illegal_configuration(kwargs):
    with pytest.raises(ValueError):
        ExecutionLedger("postgresql://user:pw@localhost/db", **kwargs)


def test_f5_accepts_bounded_configuration():
    ledger = ExecutionLedger(
        "postgresql://user:pw@localhost/db",
        connect_timeout_s=1,
        lock_timeout_ms=1,
        statement_timeout_ms=1,
        max_retries=1,
    )
    assert ledger is not None


def test_f5_connector_receives_bounded_timeouts():
    connector = RecordingConnector()
    ledger = ExecutionLedger(
        "postgresql://user:pw@localhost/db",
        connect_timeout_s=7,
        lock_timeout_ms=8000,
        statement_timeout_ms=9000,
        max_retries=1,
        connector=connector,
    )
    with pytest.raises(LedgerError) as caught:
        ledger.accept(_tree().invocation(), _tree().cost(1))
    assert caught.value.code is ErrorCode.TRUSTED_STATE_UNAVAILABLE
    assert len(connector.calls) == 1
    call = connector.calls[0]
    assert call["connect_timeout"] == 7
    assert call["autocommit"] is False
    assert call["dsn"].startswith("postgresql://")


def test_f5_connection_failure_maps_to_fail_closed():
    connector = RecordingConnector()
    ledger = ExecutionLedger(
        "postgresql://user:pw@localhost/db", max_retries=1, connector=connector
    )
    with pytest.raises(LedgerError) as caught:
        ledger.accept(_tree().invocation(), _tree().cost(1))
    assert caught.value.code is ErrorCode.TRUSTED_STATE_UNAVAILABLE


def test_f5_set_config_applies_lock_and_statement_timeouts():
    fake = FakeConnection()
    ledger = ExecutionLedger(
        "postgresql://user:pw@localhost/db",
        lock_timeout_ms=1234,
        statement_timeout_ms=5678,
        connector=lambda *a, **kw: fake,
    )
    conn = ledger._connect()
    assert conn is fake
    settings = [params for sql, params in fake.executed if "set_config" in sql]
    assert settings == [("1234ms", "5678ms")]


def test_f5_deadlock_retries_are_bounded():
    attempts = {"n": 0}

    def flaky(dsn, **kwargs):
        attempts["n"] += 1
        raise psycopg.errors.DeadlockDetected("deadlock (double)")

    ledger = ExecutionLedger(
        "postgresql://user:pw@localhost/db",
        max_retries=3,
        connector=flaky,
    )
    with pytest.raises(LedgerError) as caught:
        ledger.accept(_tree().invocation(), _tree().cost(1))
    assert caught.value.code is ErrorCode.TRUSTED_STATE_UNAVAILABLE
    assert attempts["n"] == 3
