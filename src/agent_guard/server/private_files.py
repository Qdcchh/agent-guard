"""Minimal local-file protections for development AS credentials."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from agent_guard.server.config import ConfigError


def write_private_file(path: Path, data: bytes) -> None:
    """Create one new credential file without following an existing symlink."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
    finally:
        os.close(fd)


def read_private_file(path: str | Path) -> bytes:
    """Read a regular private file, rejecting links and permissive POSIX modes."""
    candidate = Path(path)
    if candidate.is_symlink() or any(
        parent.is_symlink() for parent in candidate.absolute().parents
    ):
        raise ConfigError("private file must not be a symlink")
    if os.name != "nt":
        parent_mode = candidate.parent.stat().st_mode
        if parent_mode & 0o022:
            raise ConfigError("private file directory must not be group/other writable")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(candidate, flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ConfigError("private file must be regular")
            if os.name != "nt" and info.st_mode & 0o077:
                raise ConfigError("private file must not be accessible by group or others")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(fd)
    except OSError as exc:
        raise ConfigError("private file cannot be opened safely") from exc
