"""Persistent runner-owned public IDs; worker uses existing lease/fence service."""

from __future__ import annotations

import fcntl
import os
import secrets
import stat
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.demo.config import (
    DemoConfigError,
    WorkerConfig,
    integer,
    run_uuid,
    text,
)
from agent_guard.execution.service import ExecutionService, safe_reason
from agent_guard.execution.store import fetch_lease
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.server.private_files import read_private_file
from agent_guard.tools.downstream import MockDownstream


class OwnedOperationRegistry:
    """Append-only IDs written by trusted runner, read by distinct worker UID.

    Directory 0750 runner:worker-group, entries0440. No token/authority in IDs.
    Caller passes independent public ownership/scope; file contents cannot grant
    authority and every row must match scope before existing service execution.
    """

    def __init__(
        self,
        directory: Path,
        *,
        run_id: str,
        owner_id: str,
        tenant_id: str,
        task_id: str,
        runner_uid: int,
        worker_uid: int,
        reader_gid: int,
    ):
        self.directory = Path(directory)
        self.run_id = run_uuid(run_id)
        self.owner_id = text(owner_id)
        self.tenant_id = text(tenant_id)
        self.task_id = text(task_id)
        self.runner_uid = integer(runner_uid)
        self.worker_uid = integer(worker_uid)
        self.reader_gid = integer(reader_gid)
        if runner_uid == worker_uid:
            raise DemoConfigError("registry writer and reader UIDs must differ")
        self._check()

    def _check(self):
        info = self.directory.lstat()
        if (
            self.directory.is_symlink()
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != self.runner_uid
            or info.st_gid != self.reader_gid
            or stat.S_IMODE(info.st_mode) != 0o750
        ):
            raise DemoConfigError("registry ownership/mode rejected")
        for parent in self.directory.parents:
            if parent.is_symlink():
                raise DemoConfigError("registry path alias forbidden")
        if os.getuid() not in (self.runner_uid, self.worker_uid):
            raise DemoConfigError("registry role rejected")

    @contextmanager
    def _directory_lock(self, *, writer=False):
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            deadline = time.monotonic() + 5
            while True:
                try:
                    fcntl.flock(fd, (fcntl.LOCK_EX if writer else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise DemoConfigError("registry lock deadline") from None
                    time.sleep(0.01)
            self._check()
            yield fd
        finally:
            os.close(fd)

    def register(self, operation_id: str):
        with self._directory_lock(writer=True) as directory_fd:
            return self._register_locked(operation_id, directory_fd)

    def _register_locked(self, operation_id: str, directory_fd):
        self._check()
        text(operation_id)
        if os.getuid() != self.runner_uid:
            raise DemoConfigError("only trusted runner may register accepted IDs")
        value = {
            "version": "demo-operations-2",
            "run_id": self.run_id,
            "owner_id": self.owner_id,
            "tenant_id": self.tenant_id,
            "task_id": self.task_id,
            "operation_id": operation_id,
        }
        raw = canonical_json_bytes(value)
        path = self.directory / operation_id
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o440)
        except FileExistsError:
            if operation_id not in self._operation_ids_locked():
                raise DemoConfigError("registry conflicting entry") from None
            return False
        try:
            os.fchown(fd, self.runner_uid, self.reader_gid)
            os.fchmod(fd, 0o440)
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise DemoConfigError("registry persistence failed")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory_fd)
        return True

    def operation_ids(self):
        with self._directory_lock():
            return self._operation_ids_locked()

    def _operation_ids_locked(self):
        self._check()
        ids = []
        for path in sorted(self.directory.iterdir()):
            text(path.name)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or info.st_uid != self.runner_uid
                    or info.st_gid != self.reader_gid
                    or stat.S_IMODE(info.st_mode) != 0o440
                    or info.st_size > 1024
                ):
                    raise DemoConfigError("registry entry ownership/capacity rejected")
                value = load_strict_json(os.read(fd, 1025))
            finally:
                os.close(fd)
            expected = {
                "version": "demo-operations-2",
                "run_id": self.run_id,
                "owner_id": self.owner_id,
                "tenant_id": self.tenant_id,
                "task_id": self.task_id,
                "operation_id": path.name,
            }
            if value != expected:
                raise DemoConfigError("registry scope mismatch")
            ids.append(path.name)
            if len(ids) > 65536:
                raise DemoConfigError("registry capacity")
        return tuple(ids)


@dataclass(frozen=True)
class WorkerBatchReport:
    checked: tuple[str, ...]
    processed: tuple[tuple[str, str], ...]
    errors: tuple[tuple[str, str], ...]
    cursor: int


@dataclass(frozen=True)
class WorkerStopReport:
    batches: int
    processed: int
    drained: bool


class Worker:
    def __init__(self, config: WorkerConfig, *, operations: OwnedOperationRegistry):
        if (
            type(config) is not WorkerConfig
            or config.role.role != "worker"
            or os.getuid() != config.role.uid
            or type(operations) is not OwnedOperationRegistry
            or operations.worker_uid != config.role.uid
            or (operations.run_id, operations.tenant_id, operations.task_id)
            != (config.role.run_id, config.tenant_id, config.task_id)
        ):
            raise DemoConfigError("worker role and registry scope required")
        integer(config.lease_ttl_seconds, maximum=300)
        if type(config.poll_seconds) not in (float, int) or not 0.01 <= config.poll_seconds <= 5:
            raise DemoConfigError("bounded worker policy required")
        self.config, self.operations = config, operations
        from agent_guard.demo.provision import _dsn

        self._dsn = _dsn(config.role, "authority_dsn")
        ds_dsn = _dsn(config.role, "downstream_dsn")
        secret = read_private_file(config.role.private_files["downstream_secret"]).decode()
        if ds_dsn == self._dsn:
            raise DemoConfigError("independent downstream domain required")
        self._service = ExecutionService(
            gateway_dsn=self._dsn,
            ledger=ExecutionLedger(self._dsn),
            catalog=config.catalog,
            downstream=MockDownstream(
                ds_dsn,
                service_secret=secret,
                approved_suppliers=config.approved_suppliers,
                approved_recipients=config.approved_recipients,
                served_requests=config.served_requests,
            ),
            downstream_secret=secret,
            lease_ttl_seconds=config.lease_ttl_seconds,
        )
        self._cursor = 0
        self._owner = secrets.token_urlsafe(32)
        self._lock = threading.Lock()
        self._stop_event = None

    def step(self, *, batch_size: int) -> WorkerBatchReport:
        integer(batch_size, maximum=64)
        if not self._lock.acquire(blocking=False):
            raise DemoConfigError("worker step already in flight")
        try:
            ids = self.operations.operation_ids()
            if not ids:
                return WorkerBatchReport((), (), (), 0)
            start = self._cursor % len(ids)
            selected = tuple(ids[(start + i) % len(ids)] for i in range(min(batch_size, len(ids))))
            self._cursor = (start + len(selected)) % len(ids)
            processed, errors = [], []
            for ident in selected:
                if self._stop_event is not None and self._stop_event.is_set():
                    break
                try:
                    operation = self._service.load_operation(ident)
                    if operation is None or (
                        operation.tenant_id,
                        operation.task_id,
                    ) != (self.config.tenant_id, self.config.task_id):
                        raise DemoConfigError("registry missing or foreign operation")
                    with psycopg.connect(self._dsn, connect_timeout=5) as conn:
                        lease = fetch_lease(conn, ident)
                    if operation.status not in ("RESERVED", "EXECUTING", "UNKNOWN") or (
                        lease is not None and lease[2] > datetime.now(timezone.utc)
                    ):
                        continue
                    result = self._service.run_operation(ident, owner_token=self._owner)
                    processed.append((ident, result.status))
                except Exception as exc:
                    errors.append((ident, safe_reason(exc)))
            return WorkerBatchReport(selected, tuple(processed), tuple(errors), self._cursor)
        finally:
            self._lock.release()

    def serve(self, *, stop_event: threading.Event) -> WorkerStopReport:
        if not isinstance(stop_event, threading.Event):
            raise DemoConfigError("explicit stop event required")
        batches = processed = 0
        self._stop_event = stop_event
        while not stop_event.is_set():
            result = self.step(batch_size=64)
            batches += 1
            processed += len(result.processed)
            if result.errors:
                raise DemoConfigError("worker batch failed; inspect public error codes")
            stop_event.wait(self.config.poll_seconds)
        with self._lock:
            return WorkerStopReport(batches, processed, True)

    def reconcile(self, *, operation_id: str):
        """Trusted demo recovery seam; existing service performs query-only recovery."""
        text(operation_id)
        if not self._lock.acquire(blocking=False):
            raise DemoConfigError("worker step already in flight")
        try:
            if self._stop_event is not None and self._stop_event.is_set():
                raise DemoConfigError("worker stopped claiming")
            if operation_id not in self.operations.operation_ids():
                raise DemoConfigError("operation not registered by trusted runner")
            operation = self._service.load_operation(operation_id)
            if operation is None or (operation.tenant_id, operation.task_id) != (
                self.config.tenant_id,
                self.config.task_id,
            ):
                raise DemoConfigError("registry missing or foreign operation")
            return self._service.reconcile(operation_id, owner_token=self._owner)
        finally:
            self._lock.release()
