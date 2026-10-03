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


def test_read_refuses_symlinked_parent_directory(tmp_path):
    out_dir = tmp_path / "dev-as"
    init_config(out_dir, "https://auth.agent-guard.test")
    linked = tmp_path / "linked-dev-as"
    try:
        linked.symlink_to(out_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks unavailable")
    with pytest.raises(ConfigError, match="symlink"):
        read_private_file(linked / "secrets.json")


def _cli(*args, umask=0o022, env=None):
    import subprocess
    import sys

    return subprocess.run(
        [sys.executable, "-B", "-m", "agent_guard.server", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=15,
        umask=umask,
        env=env,
    )


@pytest.mark.parametrize("mask", [0o022, 0o077, 0o777])
def test_actual_cli_umasks_and_natural_errors(tmp_path, mask):
    out = tmp_path / "new-cli"
    done = _cli("init", "--out", out, umask=mask)
    assert "Traceback" not in done.stderr
    if mask == 0o777:
        assert done.returncode == 2
        if out.exists():
            out.chmod(0o700)  # owned test cleanup only; product never repairs it
            assert list(out.iterdir()) == []
        return
    assert done.returncode == 0, done.stderr
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    assert len(list(out.iterdir())) == 6
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in out.iterdir())
    assert _cli("check", "--config", out / "config.json", umask=mask).returncode == 0
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    assert _cli("init", "--out", out, umask=mask).returncode == 2
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before


@pytest.mark.parametrize(
    "kind", ["fifo", "socket", "directory", "symlink", "parent-link", "unsafe-parent"]
)
@pytest.mark.parametrize("command", ["check", "run"])
def test_actual_cli_refuses_unsafe_inputs_without_trace(tmp_path, kind, command):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    candidate = directory / "config.json"
    if kind == "fifo":
        os.mkfifo(candidate, 0o600)
    elif kind == "socket":
        os.mknod(candidate, stat.S_IFSOCK | 0o600)
    elif kind == "directory":
        candidate.mkdir(mode=0o700)
    else:
        candidate.write_text("synthetic-secret-marker")
        candidate.chmod(0o600)
        if kind == "symlink":
            link = directory / "link"
            link.symlink_to(candidate)
            candidate = link
        elif kind == "parent-link":
            link = tmp_path / "linked"
            link.symlink_to(directory, target_is_directory=True)
            candidate = link / "config.json"
        else:
            directory.chmod(0o777)
    done = _cli(command, "--config", candidate)
    assert done.returncode == 2
    assert "Traceback" not in done.stderr
    assert "synthetic-secret-marker" not in done.stdout + done.stderr


@pytest.mark.parametrize("after_write", range(1, 7))
def test_cli_retains_one_context_and_rejects_replacement(tmp_path, monkeypatch, after_write):
    from agent_guard.server import private_files as pf

    out = tmp_path / "new"
    moved = tmp_path / "original"
    handles = []
    original = pf.PrivateDirectory.write_file

    def replace_after(self, name, data):
        handles.append(id(self))
        original(self, name, data)
        if len(handles) == after_write:
            out.rename(moved)
            out.mkdir(mode=0o700)
            (out / "replacement").write_text("do-not-touch")

    monkeypatch.setattr(pf.PrivateDirectory, "write_file", replace_after)
    with pytest.raises(SystemExit, match="2"):
        init_config(out, "https://auth.agent-guard.test")
    assert len(set(handles)) == 1
    assert list(p.name for p in out.iterdir()) == ["replacement"]
    assert (out / "replacement").read_text() == "do-not-touch"
    assert len(list(moved.iterdir())) == after_write
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in moved.iterdir())


@pytest.mark.parametrize("failure", ["unsupported", "partial"])
def test_cli_stable_private_failure_and_no_secret_echo(tmp_path, monkeypatch, capsys, failure):
    from agent_guard.server import private_files as pf

    out = tmp_path / "new"
    if failure == "unsupported":

        def unsupported():
            raise ConfigError("synthetic-secret-marker")

        monkeypatch.setattr(pf, "_require_supported", unsupported)
    else:
        original = pf.os.write
        calls = []

        def partial(fd, data):
            calls.append(fd)
            if len(calls) == 1:
                return original(fd, data[:10])
            raise OSError("synthetic-secret-marker")

        monkeypatch.setattr(pf.os, "write", partial)
    with pytest.raises(SystemExit, match="2"):
        init_config(out, "https://auth.agent-guard.test")
    output = capsys.readouterr()
    assert "synthetic-secret-marker" not in output.out + output.err
    if failure == "unsupported":
        assert not out.exists()
    else:
        assert [p.name for p in out.iterdir()] == ["as-sign-key.pem"]
        assert (out / "as-sign-key.pem").stat().st_size == 10
        assert stat.S_IMODE((out / "as-sign-key.pem").stat().st_mode) == 0o600


def test_actual_cli_check_and_run_share_composition_validation(tmp_path):
    import json
    import socket

    out = tmp_path / "composition"
    assert _cli("init", "--out", out).returncode == 0
    config = out / "config.json"
    assert _cli("check", "--config", config).returncode == 0
    raw = json.loads(config.read_bytes())
    raw["clients"]["agent-planner"]["tenant_id"] = "tenant:invalid"
    config.write_text(json.dumps(raw))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.setblocking(False)
        canary = "synthetic-config-password-do-not-log"
        dsn = f"postgresql://synthetic:{canary}@127.0.0.1:{listener.getsockname()[1]}/unused"
        env = dict(os.environ, AGENT_GUARD_DATABASE_URL=dsn)
        for command, args in (
            ("check", ()),
            ("run", ("--ssl-certfile", "unused-cert", "--ssl-keyfile", "unused-key")),
        ):
            result = _cli(command, "--config", config, *args, env=env)
            assert result.returncode == 2
            output = result.stdout + result.stderr
            assert "Traceback" not in output and canary not in output and dsn not in output
            assert "config ok" not in output and "starting" not in output
        with pytest.raises(BlockingIOError):
            listener.accept()


def test_check_uses_composition_without_database_and_does_not_hide_bugs(tmp_path, monkeypatch):
    from agent_guard.server import __main__ as cli

    out = tmp_path / "check"
    init_config(out, "https://auth.agent-guard.test")
    original = cli.build_app
    observed = []

    def inspect(config, secrets, *, dsn, connector):
        observed.append(True)
        with pytest.raises(ConfigError, match="must not connect"):
            connector(dsn)
        return original(config, secrets, dsn=dsn, connector=connector)

    monkeypatch.setattr(cli, "build_app", inspect)
    cli.check_config(argparse.Namespace(config=str(out / "config.json")))
    assert observed == [True]

    def bug(*args, **kwargs):
        raise RuntimeError("synthetic internal programming bug")

    monkeypatch.setattr(cli, "build_app", bug)
    with pytest.raises(RuntimeError, match="programming bug"):
        cli.check_config(argparse.Namespace(config=str(out / "config.json")))
