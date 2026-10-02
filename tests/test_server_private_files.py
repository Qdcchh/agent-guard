"""Credential initialization and startup checks for the development server."""

from __future__ import annotations

import argparse
import os
import stat

import pytest

from agent_guard.server.__main__ import check_config, init_config
from agent_guard.server.config import ConfigError
from agent_guard.server.private_files import read_private_file


@pytest.mark.parametrize("creation_umask", [0o022, 0o077])
def test_init_creates_exclusive_private_tree(tmp_path, creation_umask):
    out_dir = tmp_path / "dev-as"
    if os.name == "nt":
        init_config(out_dir, "https://auth.agent-guard.test")
    else:
        previous = os.umask(creation_umask)
        try:
            init_config(out_dir, "https://auth.agent-guard.test")
        finally:
            os.umask(previous)
    for name in (
        "as-sign-key.pem",
        "agent-planner.pem",
        "agent-selector.pem",
        "agent-executor.pem",
        "config.json",
        "secrets.json",
    ):
        path = out_dir / name
        assert path.is_file()
        assert read_private_file(path)
        if os.name != "nt":
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
    if os.name != "nt":
        assert stat.S_IMODE(out_dir.stat().st_mode) == 0o700
    check_config(argparse.Namespace(config=str(out_dir / "config.json")))
    old_key = (out_dir / "as-sign-key.pem").read_bytes()
    with pytest.raises(SystemExit, match="2"):
        init_config(out_dir, "https://auth.agent-guard.test")
    assert (out_dir / "as-sign-key.pem").read_bytes() == old_key


def test_init_rejects_existing_empty_directory_and_symlink(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit, match="2"):
        init_config(empty, "https://auth.agent-guard.test")
    assert list(empty.iterdir()) == []
    link = tmp_path / "link"
    try:
        link.symlink_to(empty, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks unavailable")
    with pytest.raises(SystemExit, match="2"):
        init_config(link, "https://auth.agent-guard.test")


def test_check_refuses_symlink_and_open_permissions(tmp_path):
    out_dir = tmp_path / "dev-as"
    init_config(out_dir, "https://auth.agent-guard.test")
    config = out_dir / "config.json"
    secrets = out_dir / "secrets.json"
    link = out_dir / "secrets-link.json"
    try:
        link.symlink_to(secrets)
    except (OSError, NotImplementedError):
        pass
    else:
        with pytest.raises(ConfigError, match="symlink"):
            read_private_file(link)
    if os.name != "nt":
        secrets.chmod(0o644)
        with pytest.raises(SystemExit, match="2"):
            check_config(argparse.Namespace(config=str(config)))
        secrets.chmod(0o600)
        (out_dir / "as-sign-key.pem").chmod(0o644)
        with pytest.raises(SystemExit, match="2"):
            check_config(argparse.Namespace(config=str(config)))
        (out_dir / "as-sign-key.pem").chmod(0o600)
        out_dir.chmod(0o777)
        with pytest.raises(SystemExit, match="2"):
            check_config(argparse.Namespace(config=str(config)))
