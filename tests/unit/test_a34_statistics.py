"""Independent analytical datasets and fail-closed public row validation.

Also owns the measurement runner's strict public/private encoding regressions
and the owned-stop cleanup/exit-record regressions; these consume only the
frozen shared measurement inputs and no baseline peer module.
"""

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict, replace
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import experiments.agent_guard_bench.runner as runner_module
from experiments.agent_guard_bench.runner import (
    MissingPrerequisite,
    NativeOwnedAssembly,
    NativeRolePipe,
    RoleTLSInvocation,
    _native_attack,
    _private_json,
    _public_fact,
    _reused_observability_connection,
    _runner_outcome_record,
    _stop_resource_samples,
)
from experiments.agent_guard_bench.statistics import (
    InvalidMeasurements,
    effect_budget_metrics,
    nearest_rank,
    revocation_bounds,
    summarize_repetition,
    summarize_two_seeds,
    validate_actual_rows,
)
from experiments.agent_guard_bench.workload import SEEDS, generate_plan


def actual_rows(plan):
    return [
        {
            **{
                k: asdict(intent)[k]
                for k in (
                    "index",
                    "seed",
                    "mode",
                    "task",
                    "tool_id",
                    "category",
                    "attack_class",
                    "retry_kind",
                )
            },
            "send_ns": 10_000,
            "end_ns": 10_000 + intent.index + 1,
            "send_unix_ns": 1_000_000,
            "request_bytes": 500,
            "response_bytes": 100,
            "http_status": None if intent.index == 4999 else 202,
            "error": "TimeoutError" if intent.index == 4999 else None,
            "auth_pass": None,
            "new_accept": None,
            "key_hash": hashlib.sha256(intent.business_key.encode()).hexdigest(),
            "wire_sent": True,
            "invoke_write": "OBSERVED",
        }
        for intent in plan.intentions
    ]


def test_all_rows_percentiles_failure_retention_and_rate_denominators():
    plan = generate_plan("complete", SEEDS[0])
    rows = actual_rows(plan)
    result = summarize_repetition(
        plan,
        rows,
        completions={
            "terminal": {
                "n": 10,
                "expected_n": 12,
                "start_ns": 10_000,
                "end_ns": 30_000,
                "deadline_ns": 50_000,
            }
        },
    )
    assert result["latency"]["all"] == {
        "n": 5000,
        "p50_ns": 2500,
        "p95_ns": 4750,
        "p99_ns": 4950,
    }
    assert result["latency"]["failed"]["n"] == 1
    assert result["latency"]["failed"]["p99_ns"] == 5000
    assert result["latency"]["legal"]["n"] == 3500
    assert result["latency"]["attack"]["n"] == 1000
    assert result["latency"]["retry"]["n"] == 500
    assert all(result["latency"][f"class:{c}"]["n"] == 100 for c in range(10))
    assert result["rates"]["attempt"]["duration_ns"] == 5000
    assert result["rates"]["attempt"]["per_second"] == 1_000_000_000
    assert result["rates"]["authpass"]["unknown_n"] == 5000
    assert result["rates"]["terminal"]["duration_ns"] == 20000
    assert result["rates"]["terminal"]["gap"] == 2
    other = generate_plan("complete", SEEDS[1])
    summary = summarize_two_seeds([result, summarize_repetition(other, actual_rows(other))])
    assert summary["raw_repetitions"][0] is result
    assert summary["attempt_per_second"]["mean"] == 1_000_000_000


def test_pre_send_failure_rows_never_substitute_actual_invokes():
    """All planned identities present but no HTTP write must stay INCOMPLETE.

    A connect failure before any byte is written is retained honestly as a
    failure row in the error/latency statistics, but it cannot fulfil a
    required actual invoke (real 5000/40000 denominator).
    """
    plan = generate_plan("complete", SEEDS[0])
    rows = actual_rows(plan)
    for row in rows:
        row.update(
            request_bytes=0,
            response_bytes=0,
            http_status=None,
            error="ConnectionRefusedError",
            wire_sent=False,
            invoke_write="NONE",
        )
    result = validate_actual_rows(plan, rows, require_complete=False)
    assert result["status"] == "INCOMPLETE"
    assert result["missing_indices"] == list(range(len(plan.intentions)))
    assert result["unobserved_write_indices"] == list(range(len(plan.intentions)))
    with pytest.raises(InvalidMeasurements, match="missing actual invokes"):
        validate_actual_rows(plan, rows)
    summary = summarize_repetition(plan, rows, require_complete=False)
    assert summary["status"] == "INCOMPLETE"
    assert summary["actual_n"] == len(plan.intentions)
    assert summary["latency"]["failed"]["n"] == len(plan.intentions)


def _instrumented_invocation(monkeypatch, connection_class):
    class Config:
        gateway_origin = "https://gateway.agent-guard.test"
        ca_file = "/unused/ca.pem"

    holder = SimpleNamespace(config=Config(), _token="synthetic-token")
    monkeypatch.setattr(runner_module.ssl, "create_default_context", lambda *a, **k: object())
    monkeypatch.setattr(runner_module.http.client, "HTTPSConnection", connection_class)
    return RoleTLSInvocation(holder, mode="complete")


def test_send_instrumentation_raising_transport_is_unknown_never_observed(monkeypatch):
    """A failed lower send must not be classified as an observed real write.

    The instrumentation counts bytes only after the underlying transport call
    returns success; a raising send may have written partially but that is
    unobservable, so the honest classification is UNKNOWN and the row can never
    fulfil a required actual invoke.
    """

    class RaisingConnection:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self):
            return None

        def send(self, data):
            raise OSError("transport failed without a confirmed byte")

        def request(self, method, url, body=None, headers=None):
            self.send(b"POST /v1/invocations HTTP/1.1\r\n")

        def getresponse(self):
            raise AssertionError("no response after a failed send")

        def close(self):
            return None

    plan = generate_plan("complete", SEEDS[0])
    intent = next(i for i in plan.intentions if i.material != "EXACT_ORIGINAL_BYTES")
    invocation = _instrumented_invocation(monkeypatch, RaisingConnection)
    row = invocation.send(
        intent,
        {
            "body": b'{"synthetic":true}',
            "token": "synthetic-token",
            "proof": "synthetic-proof",
            "issued_unix_ns": time.time_ns(),
            "as_refusal": None,
        },
    )
    assert row["invoke_write"] == "UNKNOWN"
    assert row["wire_sent"] is False
    assert row["error"] == "OSError"
    result = validate_actual_rows(plan, [row], require_complete=False)
    assert row["index"] in result["missing_indices"]
    assert result["status"] == "INCOMPLETE"


def test_send_instrumentation_confirmed_write_with_http_error_counts(monkeypatch):
    """A completed real request followed by an HTTP 500 still counts as actual."""

    class ErrorResponse:
        status = 500

        def read(self, amount):
            return b'{"code":"BUDGET_EXCEEDED"}'

        def close(self):
            return None

    class WorkingConnection:
        def __init__(self, *args, **kwargs):
            self.sent = 0

        def connect(self):
            return None

        def send(self, data):
            self.sent += len(data)
            return None

        def request(self, method, url, body=None, headers=None):
            self.send(b"POST /v1/invocations HTTP/1.1\r\n")
            self.send(body or b"")

        def getresponse(self):
            return ErrorResponse()

        def close(self):
            return None

    plan = generate_plan("complete", SEEDS[0])
    intent = next(i for i in plan.intentions if i.material != "EXACT_ORIGINAL_BYTES")
    invocation = _instrumented_invocation(monkeypatch, WorkingConnection)
    row = invocation.send(
        intent,
        {
            "body": b'{"synthetic":true}',
            "token": "synthetic-token",
            "proof": "synthetic-proof",
            "issued_unix_ns": time.time_ns(),
            "as_refusal": None,
        },
    )
    assert row["invoke_write"] == "OBSERVED"
    assert row["wire_sent"] is True and row["http_status"] == 500
    result = validate_actual_rows(plan, [row], require_complete=False)
    assert row["index"] not in result["missing_indices"]
    summary = summarize_repetition(plan, [row], require_complete=False)
    assert summary["latency"]["failed"]["n"] == 1


def test_observed_http_error_responses_count_as_actual_invokes():
    """A real write with an HTTP error response is still an actual invoke."""
    plan = generate_plan("staticACL", SEEDS[0])
    rows = actual_rows(plan)
    for row in rows[:100]:
        row.update(http_status=500, error="ServerError500")
    result = validate_actual_rows(plan, rows)
    assert result["status"] == "COMPLETE"
    assert result["missing_indices"] == [] and result["unobserved_write_indices"] == []
    summary = summarize_repetition(plan, rows)
    assert summary["status"] == "COMPLETE"
    assert summary["actual_n"] == len(plan.intentions)
    assert summary["latency"]["failed"]["n"] >= 100


@pytest.mark.parametrize(
    "mutation", ["duplicate", "missing", "boolean", "clock", "identity", "secret", "no-write"]
)
def test_invalid_actual_denominators_fail_closed(mutation):
    plan = generate_plan("complete", SEEDS[0])
    rows = actual_rows(plan)
    if mutation == "duplicate":
        rows.append(rows[0])
    elif mutation == "missing":
        rows.pop()
    elif mutation == "boolean":
        rows[0]["request_bytes"] = True
    elif mutation == "clock":
        rows[0]["end_ns"] = 1
    elif mutation == "identity":
        rows[0]["seed"] = True
    elif mutation == "no-write":
        rows[0]["wire_sent"] = False
        rows[0]["invoke_write"] = "NONE"
    else:
        rows[0]["Authorization"] = "secret"
    with pytest.raises(InvalidMeasurements):
        validate_actual_rows(plan, rows)


def test_nearest_rank_empty_small_sample_and_bad_values():
    assert nearest_rank([], 0.99) is None
    assert nearest_rank([7, 2], 0.95) == 7
    assert nearest_rank(range(1, 101), 0.95) == 95
    for samples, p in (([True], 0.5), ([1], True), ([1], float("nan")), ([-1], 0.5)):
        with pytest.raises(InvalidMeasurements):
            nearest_rank(samples, p)


def test_all_ancestor_transient_highwater_and_effect_theft_are_separate():
    policy = {g: {"amount_limit": 100, "call_limit": 4} for g in ("root", "mid", "leaf")}
    facts = {
        g: {
            "events": [
                {"sequence": 1, "delta": [150, 0, 1, 0]},
                {"sequence": 2, "delta": [-150, 0, -1, 0]},
            ],
            "final_counters": [0, 0, 0, 0],
        }
        for g in policy
    }
    effects = [
        {"intent_hash": "a", "operation_id": "x", "permitted_by_policy": True},
        {"intent_hash": "a", "operation_id": "y", "permitted_by_policy": False},
    ]
    result = effect_budget_metrics(policies=policy, facts=facts, effects=effects)
    assert len(result["budget_set_violations"]) == 3
    assert result["all_ancestor_highwater"]["mid"]["amount"] == 150
    assert result["permission_theft_effects"] == ["y"]
    assert result["duplicate_effects"] == [{"intent_hash": "a", "effects": 2}]
    facts.pop("mid")
    with pytest.raises(InvalidMeasurements):
        effect_budget_metrics(policies=policy, facts=facts, effects=effects)


def test_revocation_commit_uncertainty_retained():
    assert revocation_bounds(
        commit_lower_ns=10,
        commit_upper_ns=20,
        rejected_send_ns=30,
        rejected_end_ns=50,
        server_clock_ns=100,
    ) == {"lower_ns": 10, "upper_ns": 40, "server_clock_ns": 100}
    with pytest.raises(InvalidMeasurements):
        revocation_bounds(
            commit_lower_ns=10,
            commit_upper_ns=20,
            rejected_send_ns=19,
            rejected_end_ns=50,
            server_clock_ns=100,
        )


def test_observability_connection_pool_is_reused_and_bounded(monkeypatch):
    """The operator observability pool reuses connections without unbounded growth.

    Sustained complete-mode runs showed a thread-local cache accumulated one
    connection per handler thread per domain (up to 64+64), pushing each owned
    PostgreSQL towards max_connections and slowing the per-wave writer drain
    past the 180s child-token TTL. The bounded pool must reuse an available
    connection across calls and threads, never close it between calls, and
    cap the live cached count; callers beyond the budget use a single-use
    connection instead of waiting forever or churning per call.
    """
    import psycopg
    from psycopg.rows import dict_row

    connects = []

    class StubConnection:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

        def rollback(self):
            return None

    def fake_connect(dsn, **kwargs):
        connects.append((dsn, kwargs))
        return StubConnection()

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    monkeypatch.setattr(runner_module, "_OBSERVABILITY_BUDGET", 2)
    monkeypatch.setattr(runner_module, "_OBSERVABILITY_CHECKOUT_SECONDS", 0.2)
    slot = "regression-pool-" + uuid4().hex
    with _reused_observability_connection("dsn://authority", slot) as first:
        pass
    with _reused_observability_connection("dsn://authority", slot) as second:
        assert second is first
    assert len(connects) == 1
    assert connects[0][1] == {"connect_timeout": 5, "row_factory": dict_row}

    observed = []

    def worker(hold=None, release=None):
        with _reused_observability_connection("dsn://authority", slot) as conn:
            observed.append(conn)
            if hold is not None:
                hold.set()
                assert release.wait(timeout=10)

    hold_a, release_a = threading.Event(), threading.Event()
    thread_a = threading.Thread(target=worker, args=(hold_a, release_a))
    thread_a.start()
    assert hold_a.wait(timeout=5)
    # The first holder is using the pooled connection, so this call must open
    # a second one (budget 2) rather than reuse the busy connection.
    hold_b, release_b = threading.Event(), threading.Event()
    thread_b = threading.Thread(target=worker, args=(hold_b, release_b))
    thread_b.start()
    assert hold_b.wait(timeout=5)
    assert len(connects) == 2
    assert observed[0] is first
    assert observed[1] is not first

    # Budget exhausted: a third concurrent caller waits the bounded checkout
    # time and then falls back to a single-use connection, closed on exit.
    with _reused_observability_connection("dsn://authority", slot) as third:
        assert third is not first and third is not observed[1]
    assert len(connects) == 3
    assert third.closed is True

    release_a.set()
    release_b.set()
    thread_a.join(timeout=5)
    thread_b.join(timeout=5)
    assert not thread_a.is_alive() and not thread_b.is_alive()
    with _reused_observability_connection("dsn://authority", slot) as fourth:
        assert fourth in (first, observed[1])
    assert len(connects) == 3, "pooled connections must be reused, never re-created"
    # No pooled connection is closed between calls; every call keeps its own
    # bounded transaction only.
    assert first.closed is False


class _BlockingStdin:
    def __init__(self):
        self.hold = threading.Event()
        self.release = threading.Event()
        self.payload = bytearray()

    def write(self, data):
        if self.hold.is_set():
            assert self.release.wait(timeout=5)
        self.payload.extend(data)
        return len(data)

    def flush(self):
        return None

    def close(self):
        return None


def test_role_pipe_write_backpressure_never_blocks_response_delivery(tmp_path):
    """A blocked stdin write must not delay already-registered responses.

    The reader and submit helpers previously shared one lock, so a write that
    blocked on a full container pipe also blocked response delivery and could
    stall every in-flight call. The regression holds a write inside the pipe
    and requires an earlier response to still be delivered.
    """
    from concurrent.futures import Future

    pipe = NativeRolePipe.__new__(NativeRolePipe)
    pipe.future_type = Future
    pipe.lock = threading.Lock()
    pipe.write_lock = threading.Lock()
    pipe.pending = {}
    pipe.sequence = 0
    pipe.role = "regression"
    pipe.stderr = io.BytesIO()
    pipe.owner = SimpleNamespace(root=tmp_path, ids={"regression": "fake"})
    read_fd, write_fd = os.pipe()
    stdin = _BlockingStdin()
    pipe.process = SimpleNamespace(
        stdin=stdin,
        stdout=os.fdopen(read_fd, "rb"),
        poll=lambda: None,
        pid=1,
        wait=lambda: 0,
    )
    pipe.reader = threading.Thread(target=pipe._read, daemon=True)
    pipe.reader.start()
    try:
        first = pipe.submit({"x": 1})
        stdin.hold.set()
        holder = {}

        def blocked_writer():
            holder["future"] = pipe.submit({"x": 2})

        writer = threading.Thread(target=blocked_writer)
        writer.start()
        deadline = time.monotonic() + 2
        while pipe.sequence < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pipe.sequence == 2, "second submit must register before its blocking write"
        os.write(write_fd, b'{"id":1,"value":"one"}\n')
        assert first.result(timeout=2) == "one"
        assert writer.is_alive(), "writer must still be blocked inside the pipe write"
        stdin.release.set()
        writer.join(timeout=5)
        assert not writer.is_alive()
        os.write(write_fd, b'{"id":2,"value":"two"}\n')
        assert holder["future"].result(timeout=2) == "two"
    finally:
        stdin.release.set()
        # EOF first so the blocked reader finishes before its buffered-file
        # lock is taken by close(); never close the reader first.
        os.close(write_fd)
        pipe.reader.join(timeout=5)
        # The reader must be provably stopped before its file object is
        # closed: a live reader would still hold the buffered lock and the
        # close() below would deadlock the whole unit run.
        assert not pipe.reader.is_alive(), "reader thread must stop after write end EOF"
        pipe.process.stdout.close()


def test_role_pipe_bounded_write_times_out_when_container_pipe_is_full(tmp_path):
    """A full role stdin pipe fails fast instead of blocking the writer forever.

    The docker exec stdin is a finite kernel pipe. Before this regression the
    submission path used an untimed stream write under the write lock, so a
    stalled child could block the calling worker (and any close() waiting for
    the write lock) past the caller's timeout. The real descriptor write is
    now deadline-bounded and leaves no pending future behind.
    """
    from concurrent.futures import Future

    pipe = NativeRolePipe.__new__(NativeRolePipe)
    pipe.future_type = Future
    pipe.lock = threading.Lock()
    pipe.write_lock = threading.Lock()
    pipe.pending = {}
    pipe.sequence = 0
    pipe.role = "regression"
    pipe.stderr = io.BytesIO()
    pipe.owner = SimpleNamespace(root=tmp_path, ids={"regression": "fake"})
    read_fd, write_fd = os.pipe()
    stream = os.fdopen(write_fd, "wb")
    pipe.process = SimpleNamespace(stdin=stream)
    try:
        # Fill the kernel pipe completely so the next write cannot proceed.
        os.set_blocking(write_fd, False)
        filled = 0
        while True:
            try:
                filled += os.write(write_fd, b"x" * 65536)
            except BlockingIOError:
                break
        os.set_blocking(write_fd, True)
        assert filled > 0
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            pipe.submit({"x": 1}, timeout=0.5)
        assert time.monotonic() - started < 5
        assert pipe.pending == {}, "a failed bounded write must leave no pending future"
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            pipe.call({"x": 2}, timeout=0.5)
        assert time.monotonic() - started < 5
        assert pipe.pending == {}, "a bounded call must leave no pending future behind"
    finally:
        os.close(read_fd)
        stream.close()


def test_role_pipe_call_deadline_covers_lock_acquisition_and_pending(tmp_path):
    """call(timeout) must not restart its budget after waiting for write_lock.

    A writer holding write_lock longer than the caller budget used to leave
    submit waiting on an untimed lock acquisition, so a short call timeout
    could effectively wait for the whole blocking write behind it; the old
    remaining-time floor also extended past the deadline. The one absolute
    deadline now fails the call boundedly, leaves no pending future, and never
    releases a lock the caller does not own.
    """
    from concurrent.futures import Future

    pipe = NativeRolePipe.__new__(NativeRolePipe)
    pipe.future_type = Future
    pipe.lock = threading.Lock()
    pipe.write_lock = threading.Lock()
    pipe.pending = {}
    pipe.sequence = 0
    pipe.role = "regression"
    pipe.stderr = io.BytesIO()
    pipe.owner = SimpleNamespace(root=tmp_path, ids={"regression": "fake"})
    pipe.process = SimpleNamespace(stdin=_BlockingStdin())
    pipe.write_lock.acquire()
    try:
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            pipe.call({"x": 1}, timeout=0.5)
        elapsed = time.monotonic() - started
        assert 0.3 <= elapsed < 3, elapsed
        assert pipe.pending == {}, "no pending future may outlive a failed call"
        assert pipe.write_lock.locked(), "the holder's lock must stay held"
    finally:
        pipe.write_lock.release()


def test_public_fact_integral_decimal_and_prehashed_original_stay_strict():
    """Integral Decimal becomes an exact int; only prehashed originals pass twice.

    Regression for the real pilot TypeError: the operator already reduced a
    secret-named column to {"bytes","sha256"} and the outer public scan then
    fed that dict back through the raw-string branch.
    """
    assert _public_fact(Decimal("0")) == 0
    assert _public_fact(Decimal("70000")) == 70000
    assert type(_public_fact(Decimal("70000"))) is int
    with pytest.raises(ValueError):
        _public_fact(Decimal("0.5"))

    original = b"synthetic-token-jws-bytes"
    once = _public_fact(original.decode(), "token_jws")
    assert once == {
        "bytes": len(original),
        "sha256": hashlib.sha256(original).hexdigest(),
    }
    assert _public_fact(once, "token_jws") == once
    assert _public_fact(once, "proof") == once
    for malformed in (
        {"bytes": True, "sha256": "a" * 64},
        {"bytes": 1, "sha256": "short"},
        {"bytes": 1, "sha256": 7},
    ):
        with pytest.raises(ValueError):
            _public_fact(malformed, "token_jws")


def test_private_archive_uuid_decimal_and_raw_are_lossless():
    identifier = UUID("11111111-2222-3333-4444-555555555555")
    exact = Decimal("12345678901234567890.00000001")
    scaled = Decimal("1.50")
    raw = b"\x00\xff\x10"
    encoded = json.dumps(
        {"id": identifier, "amount": exact, "scaled": scaled, "raw": raw},
        default=_private_json,
    )
    decoded = json.loads(encoded)
    assert decoded["id"] == {"private_uuid": str(identifier)}
    assert UUID(decoded["id"]["private_uuid"]) == identifier
    assert decoded["amount"] == {"private_exact_decimal": str(exact)}
    assert Decimal(decoded["amount"]["private_exact_decimal"]) == exact
    assert decoded["scaled"] == {"private_exact_decimal": "1.50"}
    assert str(Decimal(decoded["scaled"]["private_exact_decimal"])) == "1.50"
    assert base64.b64decode(decoded["raw"]["private_raw_base64"]) == raw


def test_resource_sampler_stop_records_real_wait_and_bounded_escalation(tmp_path):
    class Owner:
        root = tmp_path

    class Fake:
        owner = Owner()
        resource_thread = None

    fake = Fake()
    fake.resource_process = None
    record = _stop_resource_samples(fake)
    assert record["status"] == "NOT_STARTED" and record["exited"] is True

    fake.resource_process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    record = _stop_resource_samples(fake)
    assert record["terminate_sent"] is True and record["kill_sent"] is False
    assert record["actual_wait"] is True and record["exited"] is True
    assert record["native_exit"] == -15  # real SIGTERM wait result, not a stub zero
    assert json.loads((tmp_path / "resource-sampler.native.json").read_text()) == record

    ignoring = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal,sys,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
            "sys.stdout.write('R');sys.stdout.flush();time.sleep(30)",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert ignoring.stdout.read(1) == b"R"
        fake.resource_process = ignoring
        record = _stop_resource_samples(fake, terminate_timeout=0.2, kill_timeout=5)
        assert record["terminate_sent"] is True and record["kill_sent"] is True
        assert record["actual_wait"] is True and record["exited"] is True
        assert record["native_exit"] == -9  # actual SIGKILL wait result
    finally:
        if ignoring.poll() is None:
            ignoring.kill()
            ignoring.wait(timeout=5)
        if ignoring.stdout is not None:
            ignoring.stdout.close()


def test_owned_stop_always_completes_cleanup_and_records_real_role_exit(tmp_path):
    class PipeProcess:
        returncode = None

    class FailingPipe:
        process = PipeProcess()

        def close(self):
            raise RuntimeError("native stdout writer has not STOPped")

    class CleanupOwner:
        owner, run = "owner-regression", "run-regression"

        def __init__(self):
            self.root = tmp_path

        def cleanup(self):
            (tmp_path / "cleanup.json").write_text(json.dumps({"resources_remaining": 0}))

    class FakeAssembly:
        closed = False
        pipes = {"planner": FailingPipe()}
        resource_process = None
        resource_thread = None

    fake = FakeAssembly()
    fake.owner = CleanupOwner()
    fake._stop_resource_samples = _stop_resource_samples.__get__(fake)
    with pytest.raises(MissingPrerequisite, match="stop error"):
        NativeOwnedAssembly.stop(fake)
    assert (tmp_path / "cleanup.json").exists()
    receipt = json.loads((tmp_path / "STOP.json").read_text())
    assert receipt["status"] == "STOP_ERRORS"
    assert receipt["resources_remaining"] == 0
    assert receipt["native_roles"] == {"planner": None}
    assert receipt["native_role_failures"] == {"planner": "RuntimeError"}
    assert fake.closed is True


def test_runner_outcome_record_leaves_native_exit_unobserved():
    ok = _runner_outcome_record(
        business_exit=0,
        cleanup_error=None,
        stop_receipt={
            "status": "STOP",
            "resources_remaining": 0,
            "native_roles": {"planner": 0, "executor": 0},
        },
        owner="owner-regression",
        run="run-regression",
        pilot=False,
        pid=1,
    )
    assert ok["runner_outcome"] == "SUCCESS"
    assert ok["native_exit"] is None
    assert ok["native_exit_status"] == "UNOBSERVED_IN_PROCESS_PARENT_WAIT_REQUIRED"
    assert ok["record_source"] == "IN_PROCESS_FINALLY_NOT_A_PARENT_WAIT"
    assert ok["role_native_exits"] == {"planner": 0, "executor": 0}
    failed_cleanup = _runner_outcome_record(
        business_exit=0,
        cleanup_error="MissingPrerequisite",
        stop_receipt=None,
        owner="owner-regression",
        run="run-regression",
        pilot=False,
        pid=1,
    )
    assert failed_cleanup["runner_outcome"] == "FAILURE"
    assert failed_cleanup["native_exit"] is None
    assert failed_cleanup["cleanup_ok"] is False
    failed_business = _runner_outcome_record(
        business_exit=1,
        cleanup_error=None,
        stop_receipt={"status": "STOP", "resources_remaining": 0},
        owner="owner-regression",
        run="run-regression",
        pilot=True,
        pid=1,
    )
    assert failed_business["runner_outcome"] == "FAILURE"
    assert failed_business["native_exit"] is None
    assert failed_business["business_exit"] == 1


def test_real_child_wait_separates_business_success_from_native_death(tmp_path):
    """Only a waiting parent sees the real returncode, including death/nonzero."""
    script = tmp_path / "child_native_probe.py"
    script.write_text(
        "import json, os, sys\n"
        "from experiments.agent_guard_bench.runner import _runner_outcome_record\n"
        "mode, target = sys.argv[1], sys.argv[2]\n"
        "cleanup_error = None if mode == 'success_then_die' else 'MissingPrerequisite'\n"
        "record = _runner_outcome_record(\n"
        "    business_exit=0,\n"
        "    cleanup_error=cleanup_error,\n"
        "    stop_receipt={'status': 'STOP', 'resources_remaining': 0,\n"
        "                  'native_roles': {'operator': 0}},\n"
        "    owner='owner-child', run='run-child', pilot=False, pid=os.getpid(),\n"
        ")\n"
        "with open(target, 'w') as stream:\n"
        "    json.dump(record, stream)\n"
        "os._exit(7 if mode == 'success_then_die' else 0)\n"
    )
    env = {
        **os.environ,
        "PYTHONPATH": os.getcwd(),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for mode, expected_exit, expected_outcome in (
        ("success_then_die", 7, "SUCCESS"),
        ("cleanup_failure_then_clean_exit", 0, "FAILURE"),
    ):
        target = tmp_path / (mode + ".json")
        child = subprocess.run(
            [sys.executable, str(script), mode, str(target)],
            cwd=os.getcwd(),
            env=env,
            capture_output=True,
            timeout=60,
        )
        # Real wait result of the actual child OS process, not an inference.
        assert child.returncode == expected_exit
        record = json.loads(target.read_text())
        assert record["native_exit"] is None
        assert record["native_exit_status"] == "UNOBSERVED_IN_PROCESS_PARENT_WAIT_REQUIRED"
        assert record["parent_wait_record"] == ("REQUIRED_FROM_WAITING_EXTERNAL_SUPERVISOR")
        assert record["business_exit"] == 0
        assert record["runner_outcome"] == expected_outcome


class _AttackHolder:
    """Minimal genuine material builder for the transform-path regressions."""

    _token = "synthetic-holder-token"

    def raw_request(self, body):
        from agent_guard.contracts.encoding import canonical_json_bytes

        return {
            "token": self._token,
            "proof": "synthetic-genuine-proof",
            "body": canonical_json_bytes(body),
        }


def _attack_body():
    return {
        "profile": "GM-MVP-1",
        "task_id": "A6-000",
        "tool_id": "procurement.order.create",
        "tool_version": "1",
        "idempotency_key": "synthetic-key",
        "params": {
            "request_id": "req-synthetic",
            "quote_id": "quote-synthetic",
            "quote_version": "1",
            "items": [{"sku": "sku-synthetic", "quantity": 1}],
            "delivery_id": "office-synthetic",
        },
    }


def test_numeric_attack_variants_transmit_malformed_bytes_all_modes():
    """Class6 numeric attacks must reach the wire for all five variants/modes.

    Root preflight confirmed the strict canonical encoder raises EncodingError
    for -1, 1.5 and 2**53 before any HTTP send, so the measurement attacker
    path must serialize the genuine malformed literal and disclose the
    body/proof binding honestly. The produced bytes must be rejected by the
    real production gateway schema function, not by a cloned check.
    """
    from agent_guard.contracts.encoding import EncodingError, canonical_json_bytes
    from agent_guard.contracts.execution import ExecutionError
    from agent_guard.gateway.endpoint import GatewayEndpoint
    from agent_guard.gateway.errors import GatewayError, classify

    variants = (True, -1, 1.5, 0, 2**53)
    assert len(variants) == 5
    literals = (
        b'"quantity":true',
        b'"quantity":-1',
        b'"quantity":1.5',
        b'"quantity":0',
        b'"quantity":9007199254740992',
    )
    modes = ("staticACL", "realSM2Bearer", "complete", "realSM2delegation_noAtomic")
    body = _attack_body()
    canonical = canonical_json_bytes(body)

    # The confirmed client-side blocker: strict canonicalization refuses the
    # root-preflight numerics, which is exactly why raw transmission is needed.
    for blocked in (-1, 1.5, 2**53):
        mutated = json.loads(canonical)
        mutated["params"]["items"][0]["quantity"] = blocked
        with pytest.raises(EncodingError):
            canonical_json_bytes(mutated)

    plan = generate_plan("complete", SEEDS[0])
    class6 = next(i for i in plan.intentions if i.attack_class == 6)
    for mode in modes:
        no_pop = mode in ("staticACL", "realSM2Bearer")
        material = {
            "body": canonical,
            "token": "synthetic-token",
            "proof": None if no_pop else "synthetic-genuine-proof",
        }
        for case in range(100):
            intent = replace(class6, mode=mode, case_index=case)
            result = _native_attack(_AttackHolder(), intent, body, material, mode)
            raw = result["body"]
            assert type(raw) is bytes
            assert literals[case % len(variants)] in raw
            assert result["body_binding"] == "RAW_MALFORMED_NUMERIC_NONCANONICAL"
            if no_pop:
                assert result["proof_binding"] is None
            else:
                assert result["proof_binding"] == (
                    "GENUINE_PROOF_BINDS_PRETRANSFORM_CANONICAL_BODY"
                )
                assert result["proof"] == "synthetic-genuine-proof"
            with pytest.raises((GatewayError, ExecutionError)) as failure:
                GatewayEndpoint.schema(raw, query=False)
            # The real production classification must answer 400 for every
            # transmitted malformed numeric, whatever internal layer refuses.
            assert classify(failure.value) == (400, "INVALID_SCHEMA")


def test_other_frozen_attack_classes_stay_transmittable():
    """Audit of the remaining body-rewriting attack classes before the run."""
    from agent_guard.contracts.encoding import load_strict_json

    body = _attack_body()
    canonical = json.dumps(body, separators=(",", ":")).encode()
    plan = generate_plan("staticACL", SEEDS[0])
    by_class = {}
    for intent in plan.intentions:
        if intent.attack_class is not None and intent.attack_class not in by_class:
            by_class[intent.attack_class] = intent
    material = {"body": canonical, "token": "synthetic-token", "proof": None}

    for cls, expected_field in ((3, "quantity"), (5, "request_id")):
        for mode in ("staticACL", "complete"):
            intent = replace(by_class[cls], mode=mode, case_index=0)
            proof = None if mode == "staticACL" else "synthetic-genuine-proof"
            result = _native_attack(
                _AttackHolder(), intent, body, {**material, "proof": proof}, mode
            )
            value = load_strict_json(result["body"])
            assert "params" in value  # genuine bytes, no pre-send encoding error
            assert (
                expected_field in value["params"]
                or expected_field in value["params"].get("items", [{}])[0]
            )

    research = replace(by_class[4], mode="staticACL", case_index=0)
    result = _native_attack(_AttackHolder(), research, body, material, "staticACL")
    assert load_strict_json(result["body"])["task_id"].endswith("-wrong-domain")

    stolen = replace(by_class[0], mode="complete", case_index=0)
    result = _native_attack(
        _AttackHolder(), stolen, body, {**material, "proof": "synthetic-genuine-proof"}, "complete"
    )
    assert result["proof"] is None

    for cls in (8, 9):
        intent = replace(by_class[cls], mode="staticACL", case_index=0)
        result = _native_attack(_AttackHolder(), intent, body, material, "staticACL")
        assert result["body"] == material["body"]
