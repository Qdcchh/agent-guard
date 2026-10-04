"""Negative controls for the P13 thread collection and contention oracle."""

import threading

import pytest

from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode
from tests.integration.test_execution_concurrency import _assert_lease_contention, _race


def _raise(error):
    raise error


def test_race_collects_every_success_and_expected_error():
    error = ExecutionError(
        ExecutionErrorCode.LEASE_LOST, "operation is leased by another live owner"
    )
    values = _race([lambda: 1, lambda: _raise(error)])
    assert values == [("ok", 1), ("err", error)]
    _assert_lease_contention(values)


def test_runtime_error_fails_in_main_thread():
    error = RuntimeError("synthetic racer failure")
    with pytest.raises(AssertionError, match="unexpected race worker exception") as exc:
        _race([lambda: 1, lambda: _raise(error)])
    assert exc.value.__cause__ is error


@pytest.mark.parametrize(
    "code,detail",
    [
        (ExecutionErrorCode.DOWNSTREAM_INCONSISTENT, "synthetic"),
        (ExecutionErrorCode.LEASE_LOST, "lease expired before the terminal write"),
    ],
)
def test_unrelated_execution_error_is_not_lease_contention(code, detail):
    results = _race([lambda: 1, lambda: _raise(ExecutionError(code, detail))])
    with pytest.raises(AssertionError):
        _assert_lease_contention(results)


def test_missing_worker_completion_cannot_pass(monkeypatch):
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    monkeypatch.setattr(threading.Thread, "join", lambda self, timeout: None)
    with pytest.raises(AssertionError, match="did not report completion"):
        _race([lambda: 1, lambda: 2])


def test_worker_timeout_is_bounded_and_cannot_pass(monkeypatch):
    workers = []
    original_thread = threading.Thread
    release = threading.Event()
    entered = threading.Event()

    class OwnedThread(original_thread):
        def join(self, timeout=None):
            # Startup readiness is separate from the 50 ms race deadline. Call
            # the underlying join before observing entered: a delayed-start
            # scheduler may release its gate only when join is requested.
            if timeout != 1 and not entered.is_set():
                super().join(1)
                assert entered.is_set(), "blocked worker did not enter within startup bound"
            return super().join(timeout)

    def owned_thread(*args, **kwargs):
        thread = OwnedThread(*args, **kwargs)
        workers.append(thread)
        return thread

    monkeypatch.setattr(threading, "Thread", owned_thread)

    def blocked():
        entered.set()
        assert release.wait(5), "blocked worker was not released"

    try:
        with pytest.raises(AssertionError, match="timed out"):
            # Isolate real blocking from multi-worker barrier startup scheduling.
            _race([blocked], timeout=0.05)
        assert entered.is_set()
        assert not release.is_set()
        assert workers[0].is_alive()
    finally:
        release.set()
        for worker in workers:
            worker.join(1)
        assert all(not worker.is_alive() for worker in workers)
