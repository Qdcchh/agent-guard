"""Reject current TLS context substitution before using delivery credentials."""

import hashlib
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from tests.fixtures import a31_delivery as delivery


@pytest.fixture
def context(tmp_path, monkeypatch):
    root = tmp_path / "tls"
    root.mkdir(mode=0o700)
    for name in ("ca.pem", "server.pem", "server.key"):
        path = root / name
        path.write_bytes(("TEST-ONLY " + name).encode())
        path.chmod(0o600)
    delivery_root = root / "delivery"
    delivery_root.mkdir(mode=0o700)
    for name in ("ca.pem", "server.pem", "server.key"):
        path = delivery_root / name
        path.write_bytes((root / name).read_bytes())
        path.chmod(0o600)
    receipt = {
        "container_id": "a" * 64,
        "owner": "unit-owner",
        "audit_host": "localhost",
        "sslmode": "verify-full",
        "verified_tcp_tls": True,
        "ca": str(root / "ca.pem"),
        "ephemeral": True,
        "tls_root": str(root),
        "ca_sha256": hashlib.sha256((root / "ca.pem").read_bytes()).hexdigest(),
        "server_certificate_sha256": hashlib.sha256((root / "server.pem").read_bytes()).hexdigest(),
        "delivery_server_certificate_sha256": hashlib.sha256(
            (delivery_root / "server.pem").read_bytes()
        ).hexdigest(),
    }
    path = root / "receipt.json"

    def save():
        path.write_text(json.dumps(receipt))
        path.chmod(0o600)

    save()
    monkeypatch.setenv("PR9_A31_TLS_RECEIPT", str(path))
    monkeypatch.setenv("PR9_CI_OWNER", "unit-owner")
    dsn = f"host=localhost dbname=unit user=unit sslmode=verify-full sslrootcert={root}/ca.pem"
    monkeypatch.setenv("AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL", dsn)
    inspect = [
        {
            "Id": "a" * 64,
            "Config": {"Labels": {"agent-guard.pr9-owner": "unit-owner"}},
            "State": {"Running": True},
        }
    ]
    calls = []

    def run(argv, **kwargs):
        assert argv == ["docker", "inspect", "a" * 64]
        calls.append("inspect")
        return SimpleNamespace(returncode=0, stdout=json.dumps(inspect))

    @contextmanager
    def connect(observed_dsn, *, connect_timeout):
        assert observed_dsn == dsn and connect_timeout == 5
        calls.append("connect")

        def execute(query):
            assert query == "SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()"
            return SimpleNamespace(fetchone=lambda: (True,))

        yield SimpleNamespace(execute=execute)

    monkeypatch.setattr(delivery.subprocess, "run", run)
    monkeypatch.setattr(delivery.psycopg, "connect", connect)
    return SimpleNamespace(
        root=root, receipt=receipt, path=path, save=save, inspect=inspect, calls=calls
    )


def test_current_context_checks_inspect_and_live_tls(context):
    assert delivery.tls_dir() == context.root / "delivery"
    assert context.calls == ["inspect", "connect"]


@pytest.mark.parametrize(
    "change", ["owner", "short_id", "extra", "false_tls", "false_ephemeral", "outside_ca", "digest"]
)
def test_untrusted_receipt_refused(context, change):
    if change == "owner":
        context.receipt["owner"] = "other-owner"
    elif change == "short_id":
        context.receipt["container_id"] = "a" * 12
    elif change == "extra":
        context.receipt["skip"] = True
    elif change == "false_tls":
        context.receipt["verified_tcp_tls"] = False
    elif change == "false_ephemeral":
        context.receipt["ephemeral"] = False
    elif change == "outside_ca":
        context.receipt["ca"] = str(context.root.parent / "ca.pem")
    else:
        context.receipt["server_certificate_sha256"] = "0" * 64
    context.save()
    with pytest.raises(ValueError):
        delivery.tls_dir()
    assert "connect" not in context.calls


@pytest.mark.parametrize("name", ["receipt.json", "ca.pem", "server.pem"])
def test_public_material_mode_refused(context, name):
    (context.root / name).chmod(0o644)
    with pytest.raises(ValueError):
        delivery.tls_dir()


def test_public_root_mode_refused(context):
    context.root.chmod(0o755)
    with pytest.raises(ValueError):
        delivery.tls_dir()


@pytest.mark.parametrize("name", ["ca.pem", "server.pem"])
def test_material_byte_substitution_refused(context, name):
    (context.root / name).write_bytes(b"TAMPERED TEST-ONLY")
    with pytest.raises(ValueError):
        delivery.tls_dir()


@pytest.mark.parametrize("ancestor", [False, True])
def test_symlink_path_refused(context, monkeypatch, ancestor):
    if ancestor:
        link = context.root.parent / "linked"
        link.symlink_to(context.root, target_is_directory=True)
        monkeypatch.setenv("PR9_A31_TLS_RECEIPT", str(link / "receipt.json"))
    else:
        original = context.root / "original.json"
        context.path.rename(original)
        context.path.symlink_to(original)
    with pytest.raises(ValueError):
        delivery.tls_dir()


@pytest.mark.parametrize("change", ["owner", "id", "stopped"])
def test_actual_container_inspect_must_match_receipt(context, change):
    if change == "owner":
        context.inspect[0]["Config"]["Labels"]["agent-guard.pr9-owner"] = "other"
    elif change == "id":
        context.inspect[0]["Id"] = "b" * 64
    else:
        context.inspect[0]["State"]["Running"] = False
    with pytest.raises(ValueError):
        delivery.tls_dir()
    assert "connect" not in context.calls


@pytest.mark.parametrize(
    "value",
    [
        "host=localhost sslmode=require",
        "host=localhost sslmode=verify-full sslrootcert=/other/ca.pem",
        "host=other sslmode=verify-full",
    ],
)
def test_unverified_or_unbound_database_refused(context, monkeypatch, value):
    monkeypatch.setenv("AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL", value)
    with pytest.raises(ValueError):
        delivery.tls_dir()
    assert "connect" not in context.calls


def test_receipt_true_does_not_replace_live_ssl_proof(context, monkeypatch):
    @contextmanager
    def connect(*args, **kwargs):
        yield SimpleNamespace(execute=lambda query: SimpleNamespace(fetchone=lambda: (False,)))

    monkeypatch.setattr(delivery.psycopg, "connect", connect)
    with pytest.raises(ValueError):
        delivery.tls_dir()


@pytest.mark.parametrize("name", ["ca.pem", "server.pem", "server.key"])
def test_delivery_material_mode_refused(context, name):
    (context.root / "delivery" / name).chmod(0o644)
    with pytest.raises(ValueError):
        delivery.tls_dir()


@pytest.mark.parametrize("name", ["ca.pem", "server.pem"])
def test_delivery_material_substitution_refused(context, name):
    (context.root / "delivery" / name).write_bytes(b"TAMPERED TEST-ONLY")
    with pytest.raises(ValueError):
        delivery.tls_dir()


def test_delivery_symlink_refused(context):
    original = context.root / "delivery/server.key"
    original.rename(context.root / "delivery/original.key")
    original.symlink_to(context.root / "delivery/original.key")
    with pytest.raises(ValueError):
        delivery.tls_dir()


@pytest.mark.parametrize("host", ["unknown.test", "pg-audit.agent-guard.test"])
def test_unknown_or_mismatched_audit_host_refused(context, host):
    context.receipt["audit_host"] = host
    context.save()
    with pytest.raises(ValueError):
        delivery.tls_dir()
    assert "connect" not in context.calls


def test_audit_server_private_key_need_not_be_exported(context):
    (context.root / "server.key").unlink()
    assert delivery.tls_dir() == context.root / "delivery"
