"""Test-only synchronization objects, explicitly passed into existing seams.

No environment switch, HTTP endpoint, token forgery or production auto-recovery.
A test may block at a committed boundary and its own controller sends SIGKILL.
"""

from __future__ import annotations

import hashlib
import os
import signal
import stat
import time
from pathlib import Path

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.demo.config import DemoConfigError, text


def native_identity():
    """Linux kernel identity; fail closed on unsupported platforms."""
    proc = Path("/proc/self")
    raw = (proc / "cmdline").read_bytes()
    fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
    return {
        "pid": os.getpid(),
        "uid": os.getuid(),
        "start_ticks": fields[19],
        "argv_sha256": hashlib.sha256(raw).hexdigest(),
    }


class CommittedBoundary:
    """Atomic marker plus bounded wait, instantiated only by test assembly."""

    def __init__(self, directory: Path, *, name: str, timeout_seconds=45):
        self.directory = Path(directory)
        self.name = text(name)
        if type(timeout_seconds) not in (int, float) or not 1 <= timeout_seconds <= 120:
            raise DemoConfigError("bounded fault wait required")
        self.timeout = timeout_seconds
        info = self.directory.lstat()
        if (
            self.directory.is_symlink()
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise DemoConfigError("owned private fault directory required")

    def __call__(self, *args):
        marker = self.directory / (self.name + ".json")
        pending = self.directory / (self.name + ".pending")
        fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            raw = canonical_json_bytes({"boundary": self.name, "native": native_identity()})
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if marker.exists():
                raise DemoConfigError("fault marker already exists")
            os.rename(pending, marker)
            directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            pending.unlink(missing_ok=True)
        deadline = time.monotonic() + self.timeout
        while not (self.directory / (self.name + ".release")).exists():
            if time.monotonic() >= deadline:
                raise DemoConfigError("test fault synchronization deadline")
            time.sleep(0.01)


def kill_marked_process(marker: Path):
    """Caller can kill only its own UID and exact still-live kernel start identity."""
    info = marker.lstat()
    if marker.is_symlink() or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise DemoConfigError("owned process marker required")
    value = load_strict_json(marker.read_bytes())
    expected = value["native"]
    pid = expected["pid"]
    if type(pid) is not int or pid <= 1 or pid == os.getpid() or expected["uid"] != os.getuid():
        raise DemoConfigError("owned child PID required")
    proc = Path("/proc") / str(pid)
    uid = int(
        next(
            line for line in (proc / "status").read_text().splitlines() if line.startswith("Uid:")
        ).split()[1]
    )
    start = (proc / "stat").read_text().rsplit(")", 1)[1].split()[19]
    argv_sha = hashlib.sha256((proc / "cmdline").read_bytes()).hexdigest()
    if (uid, start, argv_sha) != (
        expected["uid"],
        expected["start_ticks"],
        expected["argv_sha256"],
    ):
        raise DemoConfigError("child PID ownership changed")
    os.kill(pid, signal.SIGKILL)
    return {
        "pid": pid,
        "uid": uid,
        "start_ticks": start,
        "signal": "SIGKILL",
        "boundary": value["boundary"],
    }
