"""Descriptor-bound private files for the development AS (POSIX only).

Root and the current effective UID are trusted. This is not protection against
compromise of either identity, or an atomicity guarantee after a call returns.
Unsupported platforms fail closed rather than treating mode bits as Windows ACLs.
"""

from __future__ import annotations

import errno
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from agent_guard.server.config import ConfigError

_DIR_FD_FUNCTIONS = (os.open, os.stat, os.mkdir)
_NOFOLLOW_STAT = os.stat


def _require_supported() -> None:
    if (
        os.name != "posix"
        or any(not hasattr(os, name) for name in ("geteuid", "fstat", "fchmod"))
        or any(not hasattr(os, name) for name in ("O_NOFOLLOW", "O_NONBLOCK", "O_DIRECTORY"))
        or not all(function in os.supports_dir_fd for function in _DIR_FD_FUNCTIONS)
        or _NOFOLLOW_STAT not in os.supports_follow_symlinks
    ):
        raise ConfigError("secure private files unsupported on this platform")


def _os_error(exc: OSError) -> ConfigError:
    if exc.errno in (errno.ENOSYS, errno.ENOTSUP):
        return ConfigError("secure private files unsupported on this platform")
    if exc.errno in (errno.ELOOP, errno.ENOTDIR):
        return ConfigError("private path must not contain a symlink or non-directory ancestor")
    if exc.errno == errno.EEXIST:
        return ConfigError("private path already exists; refusing to overwrite")
    return ConfigError("private path cannot be opened or used safely")


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _entry(parent: int, name: str) -> os.stat_result:
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if stat.S_ISLNK(info.st_mode):
        raise ConfigError("private path must not be a symlink")
    return info


def _directory_info(info: os.stat_result, uid: int) -> None:
    if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, uid):
        raise ConfigError("private directory must have a trusted owner and be a directory")
    if info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX:
        raise ConfigError("private ancestor must not be group/other writable")


def _selected_child(parent: os.stat_result, child: os.stat_result, uid: int) -> None:
    if parent.st_mode & 0o022 and (child.st_uid != uid or child.st_mode & 0o022):
        raise ConfigError("sticky ancestor requires a current-owned non-writable child")


def _child_name(name: str) -> str:
    if not isinstance(name, str) or name in ("", ".", "..") or "/" in name or "\0" in name:
        raise ConfigError("private file requires a single child name")
    return name


@dataclass(frozen=True)
class _Directory:
    fd: int
    identity: tuple[int, int]
    name: str | None


class PrivateDirectory:
    """A validated directory handle, usable only inside ``private_directory``.

    ``read_file(name)`` reads private 0400/0600 regular files. ``write_file(name,
    data)`` exclusively creates 0600 files. Names are single path components.
    Failures retain any newly created file (possibly partial, always private)
    rather than risk unlinking a concurrently replaced pathname. Retry must use
    a new name or explicit operator cleanup; no existing file is repaired.
    """

    def __init__(self, chain: list[_Directory], uid: int) -> None:
        self._chain = chain
        self._uid = uid
        self._closed = False

    def _validate(self) -> None:
        if self._closed:
            raise ConfigError("private directory context is closed")
        if os.geteuid() != self._uid:
            raise ConfigError("private directory effective owner changed")
        previous = None
        for index, directory in enumerate(self._chain):
            info = os.fstat(directory.fd)
            if _identity(info) != directory.identity:
                raise ConfigError("private directory identity changed")
            _directory_info(info, self._uid)
            if index:
                entry = _entry(self._chain[index - 1].fd, directory.name)
                if (
                    _identity(entry) != directory.identity
                    or entry.st_uid != info.st_uid
                    or entry.st_mode != info.st_mode
                ):
                    raise ConfigError("private directory entry changed")
                _directory_info(entry, self._uid)
                _selected_child(previous, info, self._uid)
            previous = info
        if previous.st_uid != self._uid or stat.S_IMODE(previous.st_mode) != 0o700:
            raise ConfigError("private file directory must be current-owned mode 0700")
        # /tmp cannot itself contain private files, even on an unusually private
        # local mount. Identity comparison also catches lexical '..' spellings.
        try:
            temporary = _entry(self._chain[0].fd, "tmp")
        except FileNotFoundError:
            pass
        else:
            if _identity(temporary) == self._chain[-1].identity:
                raise ConfigError("/tmp cannot be the immediate private file directory")

    def _file_info(self, fd: int, name: str, *, newly_created: bool = False) -> os.stat_result:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ConfigError("private file must be regular")
        if info.st_uid != self._uid:
            raise ConfigError("private file must be owned by the current effective user")
        mode = stat.S_IMODE(info.st_mode)
        if (newly_created and mode & ~0o600) or (not newly_created and mode not in (0o400, 0o600)):
            raise ConfigError("private file must have mode 0400 or 0600")
        entry = _entry(self._chain[-1].fd, name)
        if (
            _identity(entry) != _identity(info)
            or entry.st_mode != info.st_mode
            or entry.st_uid != info.st_uid
        ):
            raise ConfigError("private file entry changed")
        return info

    def read_file(self, name: str) -> bytes:
        """Read a validated regular file without blocking on FIFO open."""
        name = _child_name(name)
        fd = None
        try:
            self._validate()
            before = _entry(self._chain[-1].fd, name)
            fd = os.open(
                name,
                os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                dir_fd=self._chain[-1].fd,
            )
            opened = self._file_info(fd, name)
            if _identity(before) != _identity(opened):
                raise ConfigError("private file changed during open")
            self._validate()
            chunks = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            self._file_info(fd, name)
            self._validate()
            return b"".join(chunks)
        except NotImplementedError as exc:
            raise ConfigError("secure private files unsupported on this platform") from exc
        except OSError as exc:
            raise _os_error(exc) from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError as exc:
                    raise _os_error(exc) from exc

    def write_file(self, name: str, data: bytes) -> None:
        """Exclusively create a new 0600 file relative to the retained handle."""
        name = _child_name(name)
        if not isinstance(data, bytes):
            raise ConfigError("private file contents must be bytes")
        fd = None
        try:
            self._validate()
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=self._chain[-1].fd,
            )
            self._file_info(fd, name, newly_created=True)
            self._validate()
            os.fchmod(fd, 0o600)
            self._file_info(fd, name)
            self._validate()
            remaining = memoryview(data)
            while remaining:
                count = os.write(fd, remaining)
                if count <= 0 or count > len(remaining):
                    raise ConfigError("private file write did not complete")
                remaining = remaining[count:]
            self._file_info(fd, name)
            self._validate()
        except NotImplementedError as exc:
            raise ConfigError("secure private files unsupported on this platform") from exc
        except OSError as exc:
            raise _os_error(exc) from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError as exc:
                    raise _os_error(exc) from exc

    def _close(self) -> None:
        self._closed = True
        _close_directories(self._chain)


def _close_directories(chain: list[_Directory]) -> None:
    error = None
    for directory in reversed(chain):
        try:
            os.close(directory.fd)
        except OSError as exc:
            # Never retry an ambiguous close, but still close other owned FDs.
            error = error or exc
    if error is not None:
        raise _os_error(error) from error


@contextmanager
def private_directory(path: str | Path, *, create: bool = False) -> Iterator[PrivateDirectory]:
    """Retain one secure directory handle; ``create=True`` requires a new leaf.

    Only one final directory is created, never parents. There is no pathname
    chmod or process-global umask change. An inaccessible empty directory may
    remain after restrictive-umask bootstrap failure; no secret files are made.
    """
    _require_supported()
    chain: list[_Directory] = []
    handle = None
    try:
        candidate = Path(path).absolute()
        parts = candidate.parts[1:]
        if create and (not parts or parts[-1] in (".", "..")):
            raise ConfigError("new private directory requires a single final name")
        uid = os.geteuid()
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK
        root = os.open("/", flags)
        chain.append(_Directory(root, (-1, -1), None))
        root_info = os.fstat(root)
        chain[0] = _Directory(root, _identity(root_info), None)
        _directory_info(root_info, uid)
        for index, name in enumerate(parts):
            parent = chain[-1]
            parent_info = os.fstat(parent.fd)
            _directory_info(parent_info, uid)
            if create and index == len(parts) - 1:
                os.mkdir(name, mode=0o700, dir_fd=parent.fd)
            before = _entry(parent.fd, name)
            _directory_info(before, uid)
            _selected_child(parent_info, before, uid)
            fd = os.open(name, flags, dir_fd=parent.fd)
            # Register ownership before any validation that can raise.
            chain.append(_Directory(fd, _identity(before), name))
            after = os.fstat(fd)
            if _identity(before) != _identity(after):
                raise ConfigError("private directory changed during open")
            _directory_info(after, uid)
            _selected_child(parent_info, after, uid)
        handle = PrivateDirectory(chain, uid)
        handle._validate()
        yield handle
        handle._validate()
    except NotImplementedError as exc:
        raise ConfigError("secure private files unsupported on this platform") from exc
    except OSError as exc:
        raise _os_error(exc) from exc
    finally:
        if handle is not None:
            handle._close()
        else:
            _close_directories(chain)


def write_private_file(path: Path, data: bytes) -> None:
    """Create one private file exclusively, preserving the path-caller API."""
    _require_supported()
    candidate = Path(path)
    with private_directory(candidate.parent) as directory:
        directory.write_file(candidate.name, data)


def read_private_file(path: str | Path) -> bytes:
    """Read a current-owned private regular file through secured descriptors."""
    _require_supported()
    candidate = Path(path)
    with private_directory(candidate.parent) as directory:
        return directory.read_file(candidate.name)
