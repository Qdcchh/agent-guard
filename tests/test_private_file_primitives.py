"""Owned synthetic POSIX probes for descriptor-bound development credentials.

Foreign UID cases inject metadata, never chown or read another user's files.
Subprocess timeouts fail the test; killing a hung process is not a passing probe.
"""

from __future__ import annotations

import errno
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agent_guard.server import private_files as pf
from agent_guard.server.config import ConfigError

DATA = b"synthetic-private-material"
REPLACEMENT = b"synthetic-replacement-do-not-touch"


def _file(path, data=DATA, mode=0o600):
    path.write_bytes(data)
    path.chmod(mode)
    return path


def _private(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    return directory


def _fd_set():
    # A descriptor listing includes its own transient directory descriptor, but
    # repeated listing produces the same set unless a product descriptor leaks.
    return set(os.listdir("/proc/self/fd"))


def _run(script, *args):
    return subprocess.run(
        [sys.executable, "-B", "-c", script, *map(str, args)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


@pytest.mark.parametrize("mode", [0o400, 0o600])
def test_valid_read_modes_path_and_context(tmp_path, mode, monkeypatch):
    directory = _private(tmp_path)
    key = _file(directory / "key", mode=mode)
    assert pf.read_private_file(str(key)) == DATA
    with pf.private_directory(directory) as context:
        assert context.read_file("key") == DATA
    monkeypatch.chdir(tmp_path)
    assert pf.read_private_file(Path("private/key")) == DATA


def test_create_context_retains_handle_for_six_exclusive_writes(tmp_path):
    directory = tmp_path / "new"
    with pf.private_directory(directory, create=True) as context:
        fds = _fd_set()
        for index in range(6):
            context.write_file(f"key-{index}", DATA)
            assert context.read_file(f"key-{index}") == DATA
            assert _fd_set() == fds
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in directory.iterdir())
    with pytest.raises(ConfigError, match="exists"):
        with pf.private_directory(directory, create=True):
            pytest.fail("existing directory reused")
    with pytest.raises(ConfigError, match="closed"):
        context.write_file("after-close", DATA)
    with pytest.raises(ConfigError, match="closed"):
        context.read_file("key-0")


def test_create_refuses_existing_empty_and_missing_ancestor(tmp_path):
    empty = _private(tmp_path)
    with pytest.raises(ConfigError, match="exists"):
        with pf.private_directory(empty, create=True):
            pytest.fail("existing empty directory reused")
    with pytest.raises(ConfigError):
        with pf.private_directory(tmp_path / "missing" / "child", create=True):
            pytest.fail("recursive mkdir")
    assert not (tmp_path / "missing").exists()
    assert list(empty.iterdir()) == []


@pytest.mark.parametrize("mode", [0o000, 0o200, 0o644, 0o640, 0o604, 0o700, 0o1600, 0o2600, 0o4600])
def test_rejects_file_modes_without_changing_them(tmp_path, mode):
    directory = _private(tmp_path)
    key = _file(directory / "key", mode=mode)
    before = _fd_set()
    with pytest.raises(ConfigError):
        pf.read_private_file(key)
    assert stat.S_IMODE(key.stat().st_mode) == mode
    assert _fd_set() == before


@pytest.mark.parametrize("mode", [0o755, 0o711, 0o770, 0o777, 0o1700, 0o2700])
def test_private_parent_requires_exact_0700(tmp_path, mode):
    directory = _private(tmp_path)
    key = _file(directory / "key")
    directory.chmod(mode)
    with pytest.raises(ConfigError):
        pf.read_private_file(key)
    with pytest.raises(ConfigError):
        pf.write_private_file(directory / "new", DATA)
    assert not (directory / "new").exists()
    assert stat.S_IMODE(directory.stat().st_mode) == mode


@pytest.mark.parametrize("mode", [0o702, 0o720, 0o777])
@pytest.mark.parametrize("depth", [0, 1])
def test_unsafe_ancestor_at_each_depth_refused(tmp_path, mode, depth):
    top = tmp_path / "top"
    top.mkdir(mode=0o700)
    middle = top / "middle"
    middle.mkdir(mode=0o700)
    private = middle / "private"
    private.mkdir(mode=0o700)
    key = _file(private / "key")
    unsafe = [top, middle][depth]
    unsafe.chmod(mode)
    with pytest.raises(ConfigError, match="writable"):
        pf.read_private_file(key)
    with pytest.raises(ConfigError):
        with pf.private_directory(middle / "new", create=True):
            pytest.fail("unsafe ancestor accepted")
    assert not (middle / "new").exists()
    assert stat.S_IMODE(unsafe.stat().st_mode) == mode


def test_trusted_sticky_ancestor_requires_secure_current_owned_child(tmp_path):
    sticky = tmp_path / "sticky"
    sticky.mkdir(mode=0o700)
    sticky.chmod(0o1777)
    private = sticky / "private"
    with pf.private_directory(private, create=True) as context:
        context.write_file("key", DATA)
    assert pf.read_private_file(private / "key") == DATA
    private.chmod(0o1777)
    nested = private / "nested"
    nested.mkdir(mode=0o700)
    _file(nested / "key")
    with pytest.raises(ConfigError, match="sticky"):
        pf.read_private_file(nested / "key")
    private.chmod(0o700)
    sticky.chmod(0o777)
    with pytest.raises(ConfigError, match="writable"):
        pf.read_private_file(private / "key")


def _fake_owner(monkeypatch, target, uid):
    """Inject metadata only; target contents and real ownership are unchanged."""
    identity = (target.stat().st_dev, target.stat().st_ino)
    real_stat, real_fstat = os.stat, os.fstat

    def changed(info):
        if (info.st_dev, info.st_ino) == identity:
            values = list(info)
            values[4] = uid
            return os.stat_result(values)
        return info

    monkeypatch.setattr(pf.os, "stat", lambda *a, **kw: changed(real_stat(*a, **kw)))
    monkeypatch.setattr(pf.os, "fstat", lambda fd: changed(real_fstat(fd)))


@pytest.mark.parametrize("target_name", ["root", "ancestor", "private", "key", "sticky"])
def test_injected_foreign_owners_rejected_everywhere(tmp_path, monkeypatch, target_name):
    top = tmp_path / "top"
    top.mkdir(mode=0o755)
    private = _private(top)
    key = _file(private / "key")
    target = {"root": Path("/"), "ancestor": top, "private": private, "key": key, "sticky": top}[
        target_name
    ]
    if target_name == "sticky":
        top.chmod(0o1777)
    _fake_owner(monkeypatch, target, os.geteuid() + 40000)
    with pytest.raises(ConfigError, match="owner|owned"):
        pf.read_private_file(key)


def test_injected_root_owned_sticky_and_ordinary_ancestors_allowed(tmp_path, monkeypatch):
    top = tmp_path / "top"
    top.mkdir(mode=0o700)
    private = _private(top)
    key = _file(private / "key")
    _fake_owner(monkeypatch, top, 0)
    assert pf.read_private_file(key) == DATA
    top.chmod(0o1777)
    assert pf.read_private_file(key) == DATA


def test_sticky_root_owned_child_refused_for_nonroot_current_uid(tmp_path, monkeypatch):
    assert os.geteuid() != 0, "mandatory unprivileged test environment"
    top = tmp_path / "top"
    top.mkdir(mode=0o700)
    top.chmod(0o1777)
    private = _private(top)
    key = _file(private / "key")
    _fake_owner(monkeypatch, private, 0)
    with pytest.raises(ConfigError, match="sticky"):
        pf.read_private_file(key)


def test_tmp_itself_forbidden_without_modifying_shared_permissions(monkeypatch):
    # Inject private metadata to prove /tmp identity is independently forbidden.
    real_stat, real_fstat = os.stat, os.fstat
    temporary = Path("/tmp").stat()

    def changed(info):
        if (info.st_dev, info.st_ino) == (temporary.st_dev, temporary.st_ino):
            values = list(info)
            values[0], values[4] = stat.S_IFDIR | 0o700, os.geteuid()
            return os.stat_result(values)
        return info

    monkeypatch.setattr(pf.os, "stat", lambda *a, **kw: changed(real_stat(*a, **kw)))
    monkeypatch.setattr(pf.os, "fstat", lambda fd: changed(real_fstat(fd)))
    with pytest.raises(ConfigError, match="/tmp"):
        with pf.private_directory("/tmp/../tmp"):
            pytest.fail("immediate tmp accepted")


@pytest.mark.parametrize("position", ["file", "parent", "ancestor", "dangling", "dotdot"])
def test_real_symlinks_refused_before_bytes(tmp_path, position):
    top = tmp_path / "top"
    top.mkdir(mode=0o700)
    private = _private(top)
    key = _file(private / "key")
    link = tmp_path / "link"
    if position == "file":
        link = private / "link"
        link.symlink_to(key)
        requested = link
    elif position == "dangling":
        link = private / "link"
        link.symlink_to(private / "absent")
        requested = link
    else:
        link.symlink_to(private if position == "parent" else top, target_is_directory=True)
        requested = link / "key" if position == "parent" else link / "private/key"
        if position == "dotdot":
            requested = link / "../top/private/key"
    with pytest.raises(ConfigError, match="symlink"):
        pf.read_private_file(requested)
    assert key.read_bytes() == DATA


@pytest.mark.parametrize("kind", ["fifo", "socket", "directory"])
def test_real_special_files_naturally_reject_in_bounded_child(tmp_path, kind):
    private = _private(tmp_path)
    target = private / "special"
    if kind == "fifo":
        os.mkfifo(target, 0o600)
    elif kind == "socket":
        # Real kernel socket inode; no AF_UNIX listener permission is required.
        os.mknod(target, stat.S_IFSOCK | 0o600)
    else:
        target.mkdir(mode=0o700)
    result = _run(
        """
import sys
from agent_guard.server.private_files import read_private_file
from agent_guard.server.config import ConfigError
try:
    read_private_file(sys.argv[1])
except ConfigError:
    print("naturally rejected")
else:
    raise SystemExit(4)
""",
        target,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "naturally rejected"


def test_regular_positive_control_and_nonblocking_open_flags(tmp_path, monkeypatch):
    key = _file(_private(tmp_path) / "key")
    real_open = os.open
    seen = []

    def observe(name, flags, *args, **kwargs):
        if name == "key":
            seen.append(flags)
        return real_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(pf.os, "open", observe)
    assert pf.read_private_file(key) == DATA
    assert seen and all(flags & os.O_NONBLOCK and flags & os.O_NOFOLLOW for flags in seen)


@pytest.mark.parametrize(
    "capability",
    [
        "O_NOFOLLOW",
        "O_NONBLOCK",
        "O_DIRECTORY",
        "fchmod",
        "geteuid",
        "dir_fd",
        "nofollow_stat",
        "windows",
    ],
)
def test_missing_capability_fails_before_io(tmp_path, monkeypatch, capability):
    key = _file(_private(tmp_path) / "key")
    if capability == "dir_fd":
        monkeypatch.setattr(pf.os, "supports_dir_fd", set())
    elif capability == "nofollow_stat":
        monkeypatch.setattr(pf.os, "supports_follow_symlinks", set())
    elif capability == "windows":
        monkeypatch.setattr(pf.os, "name", "nt")
    else:
        monkeypatch.delattr(pf.os, capability)
    with pytest.raises(ConfigError, match="unsupported"):
        pf.read_private_file(key)
    with pytest.raises(ConfigError, match="unsupported"):
        pf.write_private_file(key, DATA)


@pytest.mark.parametrize("name", ["", ".", "..", "nested/key", "/absolute", "bad\0name"])
def test_context_rejects_nonchild_names(tmp_path, name):
    with pf.private_directory(_private(tmp_path)) as context:
        with pytest.raises(ConfigError, match="child name"):
            context.write_file(name, DATA)
        with pytest.raises(ConfigError, match="child name"):
            context.read_file(name)


def test_missing_file_and_nonbytes_have_stable_errors(tmp_path):
    private = _private(tmp_path)
    with pytest.raises(ConfigError):
        pf.read_private_file(private / "absent")
    with pytest.raises(ConfigError, match="bytes"):
        pf.write_private_file(private / "new", "not-bytes")
    assert list(private.iterdir()) == []


@pytest.mark.parametrize("mask", [0o000, 0o022, 0o077])
def test_normal_umasks_create_exact_modes_in_child(tmp_path, mask):
    target = tmp_path / "new"
    result = _run(
        """
import os, stat, sys
from agent_guard.server.private_files import private_directory
os.umask(int(sys.argv[2]))
with private_directory(sys.argv[1], create=True) as directory:
    directory.write_file("key", b"synthetic")
    assert directory.read_file("key") == b"synthetic"
assert stat.S_IMODE(os.stat(sys.argv[1]).st_mode) == 0o700
assert stat.S_IMODE(os.stat(sys.argv[1]+"/key").st_mode) == 0o600
""",
        target,
        mask,
    )
    assert result.returncode == 0, result.stderr


def test_umask_0777_new_directory_fails_closed_before_secrets(tmp_path):
    target = tmp_path / "new"
    result = _run(
        """
import os, sys
from agent_guard.server.private_files import private_directory
from agent_guard.server.config import ConfigError
assert os.geteuid() != 0
os.umask(0o777)
try:
    with private_directory(sys.argv[1], create=True) as directory:
        directory.write_file("key", b"synthetic")
except ConfigError:
    print("bootstrap rejected before writes")
else:
    raise SystemExit(4)
""",
        target,
    )
    assert result.returncode == 0, result.stderr
    assert "bootstrap rejected before writes" in result.stdout
    assert stat.S_IMODE(target.stat().st_mode) == 0o000
    # Test-only cleanup of our exact owned directory, after recording the mode.
    target.chmod(0o700)
    assert list(target.iterdir()) == []


def test_umask_0777_existing_directory_can_secure_new_file(tmp_path):
    target = _private(tmp_path)
    result = _run(
        """
import os, stat, sys
from agent_guard.server.private_files import private_directory
os.umask(0o777)
with private_directory(sys.argv[1]) as directory:
    directory.write_file("key", b"synthetic")
    assert directory.read_file("key") == b"synthetic"
assert stat.S_IMODE(os.stat(sys.argv[1]+"/key").st_mode) == 0o600
""",
        target,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("create", [False, True])
@pytest.mark.parametrize("replacement_kind", ["directory", "symlink"])
def test_directory_replaced_between_stat_and_open_refused(
    tmp_path, monkeypatch, create, replacement_kind
):
    target = tmp_path / "private"
    if not create:
        target.mkdir(mode=0o700)
    moved = tmp_path / "moved"
    replacement = tmp_path / "replacement"
    replacement.mkdir(mode=0o700)
    real_open = os.open
    replaced = False
    before = _fd_set()

    def swap(name, flags, *args, **kwargs):
        nonlocal replaced
        if name == "private" and flags & os.O_DIRECTORY and not replaced:
            replaced = True
            target.rename(moved)
            if replacement_kind == "directory":
                target.mkdir(mode=0o700)
            else:
                target.symlink_to(replacement, target_is_directory=True)
        return real_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(pf.os, "open", swap)
    with pytest.raises(ConfigError):
        with pf.private_directory(target, create=create) as context:
            context.write_file("key", DATA)
    assert replaced
    assert list(moved.iterdir()) == []
    assert list(target.iterdir()) == []
    assert list(replacement.iterdir()) == []
    assert _fd_set() == before


@pytest.mark.parametrize("replacement_kind", ["file", "symlink", "fifo"])
def test_file_replaced_between_entry_and_open_reads_no_bytes(
    tmp_path, monkeypatch, replacement_kind
):
    private = _private(tmp_path)
    key = _file(private / "key")
    replacement = _file(private / "replacement", REPLACEMENT)
    moved = private / "moved"
    real_open, real_read = os.open, os.read
    reads = []
    swapped = False

    def swap(name, flags, *args, **kwargs):
        nonlocal swapped
        if name == "key" and not swapped:
            swapped = True
            key.rename(moved)
            if replacement_kind == "file":
                _file(key, REPLACEMENT)
            elif replacement_kind == "symlink":
                key.symlink_to(replacement)
            else:
                os.mkfifo(key, 0o600)
        return real_open(name, flags, *args, **kwargs)

    def observe_read(fd, size):
        reads.append(fd)
        return real_read(fd, size)

    monkeypatch.setattr(pf.os, "open", swap)
    monkeypatch.setattr(pf.os, "read", observe_read)
    with pytest.raises(ConfigError):
        pf.read_private_file(key)
    assert swapped and not reads
    assert moved.read_bytes() == DATA
    assert replacement.read_bytes() == REPLACEMENT


def test_ancestor_replaced_at_file_open_reads_no_bytes(tmp_path, monkeypatch):
    ancestor = tmp_path / "ancestor"
    ancestor.mkdir(mode=0o700)
    private = _private(ancestor)
    key = _file(private / "key")
    real_open, real_read = os.open, os.read
    moved = tmp_path / "moved"
    reads = []

    def swap(name, flags, *args, **kwargs):
        if name == "key":
            ancestor.rename(moved)
            ancestor.mkdir(mode=0o700)
            new_private = _private(ancestor)
            _file(new_private / "key", REPLACEMENT)
        return real_open(name, flags, *args, **kwargs)

    def observed_read(fd, size):
        reads.append(fd)
        return real_read(fd, size)

    monkeypatch.setattr(pf.os, "open", swap)
    monkeypatch.setattr(pf.os, "read", observed_read)
    with pytest.raises(ConfigError, match="entry changed"):
        pf.read_private_file(key)
    assert not reads
    assert key.read_bytes() == REPLACEMENT
    assert (moved / "private/key").read_bytes() == DATA


def test_file_replaced_during_read_does_not_return_success(tmp_path, monkeypatch):
    key = _file(_private(tmp_path) / "key")
    real_read = os.read
    moved = key.with_name("moved")
    swapped = False

    def swap(fd, size):
        nonlocal swapped
        result = real_read(fd, size)
        if not swapped:
            swapped = True
            key.rename(moved)
            _file(key, REPLACEMENT)
        return result

    monkeypatch.setattr(pf.os, "read", swap)
    with pytest.raises(ConfigError, match="entry changed"):
        pf.read_private_file(key)
    assert key.read_bytes() == REPLACEMENT
    assert moved.read_bytes() == DATA


@pytest.mark.parametrize("point", ["open", "chmod", "write"])
def test_file_replacement_never_modified_or_removed_on_write_failure(tmp_path, monkeypatch, point):
    private = _private(tmp_path)
    key, moved = private / "key", private / "moved"
    real_open, real_chmod, real_write = os.open, os.fchmod, os.write
    swapped = False

    def swap():
        nonlocal swapped
        if not swapped:
            swapped = True
            key.rename(moved)
            _file(key, REPLACEMENT, mode=0o400)

    def open_hook(name, flags, *args, **kwargs):
        fd = real_open(name, flags, *args, **kwargs)
        if name == "key" and point == "open":
            swap()
        return fd

    def chmod_hook(fd, mode):
        result = real_chmod(fd, mode)
        if point == "chmod":
            swap()
        return result

    def write_hook(fd, data):
        result = real_write(fd, data)
        if point == "write":
            swap()
        return result

    before = _fd_set()
    monkeypatch.setattr(pf.os, "open", open_hook)
    monkeypatch.setattr(pf.os, "fchmod", chmod_hook)
    monkeypatch.setattr(pf.os, "write", write_hook)
    with pytest.raises(ConfigError, match="entry changed"):
        pf.write_private_file(key, DATA)
    assert swapped
    assert key.read_bytes() == REPLACEMENT
    assert stat.S_IMODE(key.stat().st_mode) == 0o400
    assert moved.read_bytes() == (DATA if point == "write" else b"")
    assert _fd_set() == before


def test_context_replacement_between_writes_refused(tmp_path):
    private = tmp_path / "private"
    moved = tmp_path / "moved"
    before = _fd_set()
    with pytest.raises(ConfigError, match="entry changed"):
        with pf.private_directory(private, create=True) as context:
            context.write_file("first", DATA)
            private.rename(moved)
            private.mkdir(mode=0o700)
            _file(private / "sentinel", REPLACEMENT)
            context.write_file("second", DATA)
    assert (moved / "first").read_bytes() == DATA
    assert not (moved / "second").exists()
    assert not (private / "second").exists()
    assert (private / "sentinel").read_bytes() == REPLACEMENT
    assert _fd_set() == before


def test_context_revalidates_on_exit(tmp_path):
    private = _private(tmp_path)
    with pytest.raises(ConfigError, match="entry changed"):
        with pf.private_directory(private):
            private.rename(tmp_path / "moved")
            private.mkdir(mode=0o700)


@pytest.mark.parametrize("target", ["ancestor", "directory", "file"])
def test_modes_changed_during_read_fail_final_revalidation(tmp_path, monkeypatch, target):
    ancestor = tmp_path / "ancestor"
    ancestor.mkdir(mode=0o700)
    private = _private(ancestor)
    key = _file(private / "key")
    real_read = os.read
    changed = False

    def mutate(fd, size):
        nonlocal changed
        result = real_read(fd, size)
        if not changed:
            changed = True
            {"ancestor": ancestor, "directory": private, "file": key}[target].chmod(0o777)
        return result

    monkeypatch.setattr(pf.os, "read", mutate)
    with pytest.raises(ConfigError):
        pf.read_private_file(key)
    assert changed


@pytest.mark.parametrize(
    "operation",
    [
        "open_root",
        "open_file",
        "fstat_root",
        "fstat_file",
        "stat_directory",
        "fchmod",
        "read",
        "write",
    ],
)
def test_injected_os_errors_are_stable_and_close_descriptors(tmp_path, monkeypatch, operation):
    private = _private(tmp_path)
    key = _file(private / "key")
    before = _fd_set()
    real_open, real_fstat, real_stat = os.open, os.fstat, os.stat
    root_identity = (Path("/").stat().st_dev, Path("/").stat().st_ino)
    injected = False

    def fail():
        nonlocal injected
        injected = True
        raise OSError(errno.EIO, "synthetic I/O failure")

    def open_hook(name, flags, *args, **kwargs):
        if (operation == "open_root" and name == "/") or (
            operation == "open_file" and name == "key"
        ):
            fail()
        return real_open(name, flags, *args, **kwargs)

    def fstat_hook(fd):
        info = real_fstat(fd)
        if operation == "fstat_root" and (info.st_dev, info.st_ino) == root_identity:
            fail()
        if operation == "fstat_file" and stat.S_ISREG(info.st_mode):
            fail()
        return info

    def stat_hook(name, *args, **kwargs):
        if operation == "stat_directory" and name == "private":
            fail()
        return real_stat(name, *args, **kwargs)

    monkeypatch.setattr(pf.os, "open", open_hook)
    monkeypatch.setattr(pf.os, "fstat", fstat_hook)
    monkeypatch.setattr(pf.os, "stat", stat_hook)
    if operation in ("fchmod", "read", "write"):
        monkeypatch.setattr(pf.os, operation, lambda *a: fail())
    with pytest.raises(ConfigError) as caught:
        if operation in ("fchmod", "write"):
            pf.write_private_file(private / "new", DATA)
        else:
            pf.read_private_file(key)
    assert injected
    assert "synthetic" not in str(caught.value)
    assert _fd_set() == before
    assert key.read_bytes() == DATA


def test_short_writes_are_completed(tmp_path, monkeypatch):
    key = _private(tmp_path) / "key"
    real_write = os.write
    calls = []

    def short(fd, data):
        calls.append(len(data))
        return real_write(fd, data[:2])

    monkeypatch.setattr(pf.os, "write", short)
    pf.write_private_file(key, DATA)
    assert len(calls) > 1
    assert key.read_bytes() == DATA


@pytest.mark.parametrize("failure", ["exception", "zero", "negative", "too-large"])
def test_failed_writes_retain_private_partial_file_without_success(tmp_path, monkeypatch, failure):
    key = _private(tmp_path) / "key"
    real_write = os.write
    calls = 0

    def fail_after_partial(fd, data):
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_write(fd, data[:2])
        if failure == "exception":
            raise OSError(errno.EIO, "synthetic")
        return {"zero": 0, "negative": -1, "too-large": len(data) + 1}[failure]

    before = _fd_set()
    monkeypatch.setattr(pf.os, "write", fail_after_partial)
    with pytest.raises(ConfigError):
        pf.write_private_file(key, DATA)
    assert calls == 2
    assert key.read_bytes() == DATA[:2]
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert _fd_set() == before
    with pytest.raises(ConfigError, match="exists"):
        pf.write_private_file(key, DATA)
    assert key.read_bytes() == DATA[:2]


@pytest.mark.parametrize("existing", ["file", "symlink", "directory", "fifo"])
def test_exclusive_create_never_modifies_existing_target(tmp_path, existing):
    private = _private(tmp_path)
    target = private / "key"
    sentinel = _file(private / "sentinel", REPLACEMENT, 0o400)
    if existing == "file":
        _file(target, REPLACEMENT, 0o400)
    elif existing == "symlink":
        target.symlink_to(sentinel)
    elif existing == "directory":
        target.mkdir(mode=0o700)
    else:
        os.mkfifo(target, 0o600)
    before = target.lstat()
    with pytest.raises(ConfigError, match="exists"):
        pf.write_private_file(target, DATA)
    after = target.lstat()
    assert (before.st_dev, before.st_ino, before.st_mode) == (
        after.st_dev,
        after.st_ino,
        after.st_mode,
    )
    assert sentinel.read_bytes() == REPLACEMENT
    if existing == "file":
        assert target.read_bytes() == REPLACEMENT


_CONCURRENT = """
import sys, time
from pathlib import Path
from agent_guard.server.private_files import private_directory, write_private_file
from agent_guard.server.config import ConfigError
target, ready, go, kind, payload = sys.argv[1:]
Path(ready).write_text("ready")
deadline = time.monotonic()+8
while not Path(go).exists():
    if time.monotonic() > deadline:
        raise SystemExit(5)
    time.sleep(0.005)
try:
    if kind == "directory":
        with private_directory(target, create=True) as context:
            context.write_file("key", payload.encode())
    else:
        write_private_file(Path(target), payload.encode())
except ConfigError as exc:
    if "exists" not in str(exc):
        raise
    raise SystemExit(17)
"""


@pytest.mark.parametrize("round_number", range(10))
@pytest.mark.parametrize("kind", ["directory", "file"])
def test_two_real_processes_exclusive_creation_exactly_one_success(tmp_path, round_number, kind):
    private = _private(tmp_path)
    target = private / "race"
    go = tmp_path / "go"
    children = []
    try:
        for index in range(2):
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    _CONCURRENT,
                    str(target),
                    str(tmp_path / f"ready-{index}"),
                    str(go),
                    kind,
                    f"synthetic-{round_number}-{index}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            children.append(child)
        deadline = time.monotonic() + 8
        while not all((tmp_path / f"ready-{index}").exists() for index in range(2)):
            assert all(child.poll() is None for child in children), "child failed before barrier"
            assert time.monotonic() < deadline, "unreachable process barrier"
            time.sleep(0.005)
        go.write_text("go")
        results = [child.communicate(timeout=10) for child in children]
        assert sorted(child.returncode for child in children) == [0, 17], results
        winner = next(index for index, child in enumerate(children) if child.returncode == 0)
        key = target / "key" if kind == "directory" else target
        assert key.read_bytes() == f"synthetic-{round_number}-{winner}".encode()
        assert stat.S_IMODE(key.stat().st_mode) == 0o600
        if kind == "directory":
            assert stat.S_IMODE(target.stat().st_mode) == 0o700
        before = key.read_bytes()
        with pytest.raises(ConfigError, match="exists"):
            pf.write_private_file(key, b"synthetic-cannot-overwrite")
        assert key.read_bytes() == before
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)


@pytest.mark.parametrize("failure", ["not-implemented", "enotsup", "enosys"])
def test_runtime_unsupported_open_is_stable(tmp_path, monkeypatch, failure):
    private = _private(tmp_path)

    def unsupported(*args, **kwargs):
        if failure == "not-implemented":
            raise NotImplementedError("synthetic")
        raise OSError(errno.ENOTSUP if failure == "enotsup" else errno.ENOSYS, "synthetic")

    monkeypatch.setattr(pf.os, "open", unsupported)
    with pytest.raises(ConfigError, match="unsupported"):
        with pf.private_directory(private):
            pytest.fail("unsupported primitive accepted")


def test_directory_close_error_still_closes_remaining_descriptors(tmp_path, monkeypatch):
    private = _private(tmp_path)
    real_close = os.close
    failed = False
    before = _fd_set()

    def close_then_fail_once(fd):
        nonlocal failed
        real_close(fd)
        if not failed:
            failed = True
            raise OSError(errno.EIO, "synthetic close error")

    with pytest.raises(ConfigError):
        with pf.private_directory(private):
            monkeypatch.setattr(pf.os, "close", close_then_fail_once)
    assert failed
    assert _fd_set() == before


def test_file_close_error_is_stable_without_fd_leak(tmp_path, monkeypatch):
    key = _file(_private(tmp_path) / "key")
    real_close, real_fstat = os.close, os.fstat
    failed = False
    before = _fd_set()

    def close_then_fail_file(fd):
        nonlocal failed
        is_file = stat.S_ISREG(real_fstat(fd).st_mode)
        real_close(fd)
        if is_file:
            failed = True
            raise OSError(errno.EIO, "synthetic close error")

    monkeypatch.setattr(pf.os, "close", close_then_fail_file)
    with pytest.raises(ConfigError):
        pf.read_private_file(key)
    assert failed
    assert _fd_set() == before


def test_context_body_exception_closes_all_handles(tmp_path):
    private = _private(tmp_path)
    before = _fd_set()
    with pytest.raises(RuntimeError, match="synthetic caller"):
        with pf.private_directory(private):
            raise RuntimeError("synthetic caller")
    assert _fd_set() == before


def test_empty_file_is_valid_and_exclusive(tmp_path):
    key = _private(tmp_path) / "empty"
    pf.write_private_file(key, b"")
    assert pf.read_private_file(key) == b""
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    with pytest.raises(ConfigError, match="exists"):
        pf.write_private_file(key, DATA)
