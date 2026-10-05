"""Strict private receipt CLI configuration, independent keys and safe initialization."""

import json
import os
import socket
import stat
from pathlib import Path

import pytest

from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
from agent_guard.gateway.__main__ import init_config
from agent_guard.gateway.receipt_config import (
    BOUNDS,
    init_receipt_worker,
    load_receipt_worker_config,
)
from agent_guard.gateway.receipt_worker import main
from agent_guard.server.__main__ import _public_pem
from agent_guard.server.config import ConfigError


def initialized(tmp_path):
    old, new = tmp_path / "gateway", tmp_path / "receipt"
    init_config(old)
    init_receipt_worker(old / "config.json", new)
    return old, new, json.loads((new / "config.json").read_bytes())


def write_config(directory, value):
    (directory / "config.json").write_text(json.dumps(value))


@pytest.mark.parametrize(
    "case",
    [
        "AS_SPKI_reuse",
        "holder_SPKI_reuse",
        "new_gateway_kid_role_conflict",
        "wrong_private_public_match",
        "unknown_kid",
        "valid_distinct_signer",
        "holder_tuple_alias",
        "duplicate_exact_tuple",
        "holder_kid_conflict",
    ],
)
def test_gateway_key_role_spki_kid_and_public_match(tmp_path, case):
    old, new, value = initialized(tmp_path)
    if case == "AS_SPKI_reuse":
        value["receipt_keys"][value["signing_kid"]] = next(iter(value["as_keys"].values()))
    elif case == "holder_SPKI_reuse":
        value["receipt_keys"][value["signing_kid"]] = value["identities"][0]["spki_pem"]
    elif case in ("new_gateway_kid_role_conflict", "holder_kid_conflict"):
        kid = (
            next(iter(value["as_keys"]))
            if case.startswith("new")
            else value["identities"][0]["kid"]
        )
        value["receipt_keys"] = {kid: value["receipt_keys"][value["signing_kid"]]}
        value["signing_kid"] = kid
    elif case == "wrong_private_public_match":
        value["receipt_keys"][value["signing_kid"]] = _public_pem(generate_sm2_private_key())
    elif case == "unknown_kid":
        value["signing_kid"] = "missing"
    elif case == "holder_tuple_alias":
        value["identities"].append(
            dict(value["identities"][0], tenant_id="tenant-B", client_id="client-B")
        )
    elif case == "duplicate_exact_tuple":
        value["identities"].append(dict(value["identities"][0]))
    write_config(new, value)
    if case in ("valid_distinct_signer", "holder_tuple_alias"):
        config = load_receipt_worker_config(new / "config.json")
        assert "PRIVATE KEY" not in repr(config)
        pub = config.publisher("offline-no-connect")
        assert pub._signing_kid == value["signing_kid"]
    else:
        with pytest.raises(ConfigError):
            load_receipt_worker_config(new / "config.json")
    assert "downstream_secret" not in value and "secrets_path" not in value
    assert b"PRIVATE KEY" not in (new / "gateway-public.json").read_bytes()


@pytest.mark.parametrize("name", BOUNDS)
@pytest.mark.parametrize(
    "kind", ["min", "default", "max", "below_min", "zero", "negative", "over", "bool", "float"]
)
def test_exact_bounded_integer_settings(tmp_path, name, kind):
    _, new, value = initialized(tmp_path)
    low, high, default = BOUNDS[name]
    value[name] = {
        "min": low,
        "default": default,
        "max": high,
        "zero": 0,
        "below_min": low - 1,
        "float": 1.0,
        "negative": -1,
        "over": high + 1,
        "bool": True,
    }[kind]
    write_config(new, value)
    if kind in ("min", "default", "max"):
        assert load_receipt_worker_config(new / "config.json")
    else:
        with pytest.raises(ConfigError):
            load_receipt_worker_config(new / "config.json")


@pytest.mark.parametrize("case", ["unknown", "missing", "duplicate", "pem_type", "receipt_empty"])
def test_exact_schema_and_strict_json(tmp_path, case):
    _, new, value = initialized(tmp_path)
    if case == "unknown":
        value["downstream_secret"] = "never-allowed"
    elif case == "missing":
        del value["issuer"]
    elif case == "pem_type":
        value["as_keys"]["as-sign-1"] = True
    elif case == "receipt_empty":
        value["receipt_keys"] = {}
    write_config(new, value)
    if case == "duplicate":
        data = (new / "config.json").read_text()
        (new / "config.json").write_text('{"batch_size":1,' + data[1:])
    with pytest.raises(ConfigError):
        load_receipt_worker_config(new / "config.json")


@pytest.mark.parametrize(
    "case",
    [
        "existing_target",
        "file_symlink",
        "parent_symlink",
        "FIFO",
        "socket",
        "directory",
        "unsafe_ancestor",
        "relative_secret_reference",
        "historical_receipt_key",
    ],
)
def test_init_private_paths_modes_umask_exclusive_old_config_preserved(tmp_path, monkeypatch, case):
    old = tmp_path / "gateway"
    init_config(old)
    source = old / "config.json"
    original = source.read_bytes()
    out = tmp_path / "new"
    sock = None
    if case == "relative_secret_reference":
        value = json.loads(original)
        value["secrets_path"] = "../gateway/secrets.json"
        source.write_text(json.dumps(value))
        original = source.read_bytes()
        from agent_guard.gateway import receipt_config

        actual_read = receipt_config.read_private_file

        def no_secret(path):
            assert Path(path).name != "secrets.json"
            return actual_read(path)

        monkeypatch.setattr(receipt_config, "read_private_file", no_secret)
    elif case == "historical_receipt_key":
        value = json.loads(original)
        value["receipt_keys"] = {"old-receipt": _public_pem(generate_sm2_private_key())}
        source.write_text(json.dumps(value))
        original = source.read_bytes()
    elif case == "existing_target":
        out.write_bytes(b"preserved")
    elif case == "file_symlink":
        out.symlink_to(source)
    elif case == "parent_symlink":
        link = tmp_path / "link"
        link.symlink_to(old, target_is_directory=True)
        out = link / "new"
    elif case == "FIFO":
        os.mkfifo(out)
    elif case == "socket":
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(out))
    elif case == "directory":
        out.mkdir(mode=0o700)
    elif case == "unsafe_ancestor":
        parent = tmp_path / "unsafe"
        parent.mkdir(mode=0o777)
        parent.chmod(0o777)
        out = parent / "new"
    try:
        if case in ("relative_secret_reference", "historical_receipt_key"):
            init_receipt_worker(source, out)
            assert stat.S_IMODE(out.stat().st_mode) == 0o700
            assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in out.iterdir())
            assert set(p.name for p in out.iterdir()) == {
                "config.json",
                "receipt-key.pem",
                "gateway-public.json",
            }
            public = json.loads((out / "gateway-public.json").read_bytes())
            assert Path(public["secrets_path"]).is_absolute()
            assert public["secrets_path"] == str(old / "secrets.json")
            assert "downstream_secret" not in public
            if case == "historical_receipt_key":
                assert public["receipt_keys"]["old-receipt"] == value["receipt_keys"]["old-receipt"]
            key1 = load_receipt_worker_config(out / "config.json").private_key
            second = tmp_path / "second"
            init_receipt_worker(source, second)
            key2 = load_receipt_worker_config(second / "config.json").private_key
            assert serialize_sm2_public_key(key1.public_key()) != serialize_sm2_public_key(
                key2.public_key()
            )
            before = {p.name: p.read_bytes() for p in out.iterdir()}
            with pytest.raises(ConfigError):
                init_receipt_worker(source, out)
            assert before == {p.name: p.read_bytes() for p in out.iterdir()}
        else:
            with pytest.raises(ConfigError):
                init_receipt_worker(source, out)
            if case == "existing_target":
                assert out.read_bytes() == b"preserved"
        assert source.read_bytes() == original
    finally:
        if sock:
            sock.close()


@pytest.mark.parametrize("kid_case", ["AS", "holder", "old_gateway"])
def test_init_rejects_all_existing_signing_roles(tmp_path, kid_case):
    old = tmp_path / "old"
    init_config(old)
    value = json.loads((old / "config.json").read_bytes())
    if kid_case == "AS":
        kid = next(iter(value["as_keys"]))
    elif kid_case == "holder":
        kid = value["identities"][0]["kid"]
    else:
        kid = "already-gateway"
        value["receipt_keys"] = {kid: _public_pem(generate_sm2_private_key())}
        (old / "config.json").write_text(json.dumps(value))
    original = (old / "config.json").read_bytes()
    with pytest.raises(ConfigError):
        init_receipt_worker(old / "config.json", tmp_path / "new", signing_kid=kid)
    assert not (tmp_path / "new").exists() and (old / "config.json").read_bytes() == original


def test_check_run_share_private_loader_no_database_fallback(tmp_path, monkeypatch, capsys):
    _, new, _ = initialized(tmp_path)

    def refuse(*args, **kwargs):
        pytest.fail("offline check/missing explicit receipt DSN must not connect")

    monkeypatch.setattr("psycopg.connect", refuse)
    monkeypatch.delenv("AG_RECEIPT_DATABASE_URL", raising=False)
    for name in ("AGENT_GUARD_DATABASE_URL", "DATABASE_URL", "AG_GATEWAY_DATABASE_URL"):
        monkeypatch.setenv(name, "ordinary-secret-must-never-be-used")
    assert main(["check", "--config", str(new / "config.json")]) == 0
    assert main(["run", "--config", str(new / "config.json"), "--once"]) == 2
    output = capsys.readouterr()
    assert "offline" in output.out and "ordinary-secret" not in output.err
    (new / "config.json").chmod(0o644)
    assert main(["check", "--config", str(new / "config.json")]) == 2
    assert main(["run", "--config", str(new / "config.json"), "--once"]) == 2


@pytest.mark.parametrize("target", ["config", "key"])
@pytest.mark.parametrize(
    "case",
    [
        "file_symlink",
        "parent_symlink",
        "FIFO",
        "socket",
        "directory",
        "public_mode",
        "unsafe_ancestor",
    ],
)
def test_loader_rejects_unsafe_operator_paths(tmp_path, target, case):
    _, new, value = initialized(tmp_path)
    selected = new / ("config.json" if target == "config" else "receipt-key.pem")
    raw = selected.read_bytes()
    sock = None
    original_config = new / "config.json"
    if case == "parent_symlink":
        link = tmp_path / "link"
        link.symlink_to(new, target_is_directory=True)
        if target == "config":
            original_config = link / "config.json"
        else:
            value["private_key_path"] = str(link / "receipt-key.pem")
            write_config(new, value)
    elif case == "unsafe_ancestor":
        tmp_path.chmod(0o777)
    elif case == "public_mode":
        selected.chmod(0o644)
    else:
        selected.unlink()
        if case == "file_symlink":
            other = new / "other"
            other.write_bytes(raw)
            other.chmod(0o600)
            selected.symlink_to(other)
        elif case == "FIFO":
            os.mkfifo(selected, mode=0o600)
        elif case == "socket":
            sock = socket.socket(socket.AF_UNIX)
            sock.bind(str(selected))
        else:
            selected.mkdir(mode=0o700)
    try:
        with pytest.raises(ConfigError):
            load_receipt_worker_config(original_config)
    finally:
        if sock:
            sock.close()
        if case == "unsafe_ancestor":
            tmp_path.chmod(0o700)


@pytest.mark.parametrize(
    "case", ["file_symlink", "parent_symlink", "FIFO", "directory", "public_mode"]
)
def test_init_secret_reference_is_safe_without_reading_secret(tmp_path, case):
    old = tmp_path / "gateway"
    init_config(old)
    source = old / "config.json"
    original = source.read_bytes()
    secret = old / "secrets.json"
    if case == "parent_symlink":
        link = tmp_path / "linked-gateway"
        link.symlink_to(old, target_is_directory=True)
        value = json.loads(original)
        value["secrets_path"] = str(link / "secrets.json")
        source.write_text(json.dumps(value))
        original = source.read_bytes()
    elif case == "public_mode":
        secret.chmod(0o644)
    else:
        secret.unlink()
        if case == "file_symlink":
            secret.symlink_to(source)
        elif case == "FIFO":
            os.mkfifo(secret, mode=0o600)
        else:
            secret.mkdir(mode=0o700)
    with pytest.raises(ConfigError):
        init_receipt_worker(source, tmp_path / "new")
    assert source.read_bytes() == original and not (tmp_path / "new").exists()
