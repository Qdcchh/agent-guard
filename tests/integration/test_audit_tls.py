"""Own real HTTPS transport, operator CLI and request-framing controls."""

import http.client
import json
import socket
import ssl
import subprocess
import sys
import threading
from dataclasses import asdict

import psycopg
import pytest
from tongsuopy.crypto import serialization

from agent_guard.audit.config import AuditConfig
from agent_guard.audit.contracts import encode_append_batch
from agent_guard.audit.server import create_server
from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from tests.fixtures.a31_audit_service import (
    all_rows,
    foreign_rows,
    private_json,
    service_context,
)


@pytest.fixture
def audit_service():
    with service_context() as fixture:
        yield fixture


@pytest.fixture(scope="session")
def service_tls(tmp_path_factory):
    directory = tmp_path_factory.mktemp("service-tls")
    directory.chmod(0o700)
    commands = [
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(directory / "ca.key"),
            "-out",
            str(directory / "ca.pem"),
            "-days",
            "2",
            "-subj",
            "/CN=S1 service private CA",
        ],
        [
            "openssl",
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(directory / "server.key"),
            "-out",
            str(directory / "server.csr"),
            "-subj",
            "/CN=localhost",
        ],
    ]
    for command in commands:
        result = subprocess.run(command, capture_output=True, timeout=30)
        assert result.returncode == 0
    (directory / "ext").write_text(
        "subjectAltName=DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n"
    )
    result = subprocess.run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(directory / "server.csr"),
            "-CA",
            str(directory / "ca.pem"),
            "-CAkey",
            str(directory / "ca.key"),
            "-CAcreateserial",
            "-out",
            str(directory / "server.pem"),
            "-days",
            "2",
            "-extfile",
            str(directory / "ext"),
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0
    for path in directory.iterdir():
        path.chmod(0o600)
    return directory


def tls_config(f, directory, port=0):
    return AuditConfig(
        f.dsn,
        f.owner_role,
        f.trust.kid,
        directory / "unused-signing.key",
        directory / "server.pem",
        directory / "server.key",
        "127.0.0.1",
        port,
        (),
        (),
    )


def request(
    port,
    directory,
    endpoint,
    body,
    *,
    credential_id="writer",
    credential="",
    method="POST",
    content_type="application/json",
    context=None,
):
    context = context or ssl.create_default_context(cafile=str(directory / "ca.pem"))
    connection = http.client.HTTPSConnection("localhost", port, timeout=5, context=context)
    try:
        connection.request(
            method,
            endpoint,
            body,
            {
                "Content-Type": content_type,
                "Authorization": "Bearer " + credential_id + ":" + credential,
            },
        )
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("case", ["TLSpositive", "badTLS", "wrongrole", "crossscope", "framing"])
def test_real_audit_tls_registered_roles_and_scope(audit_service, service_tls, case, round):
    f = audit_service
    foreign = foreign_rows()
    before = all_rows(f)
    config = tls_config(f, service_tls)
    server = create_server(config, store=f.store())
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.start()
    port = server.server_address[1]
    raw = encode_append_batch(f.scope.stream_id, f.records[:2]).exact_body
    try:
        if case == "TLSpositive":
            status, response = request(
                port,
                service_tls,
                "/v1/audit/latest",
                canonical_json_bytes({"stream_id": f.scope.stream_id}),
                credential_id="reader",
                credential=f.reader,
            )
            assert status == 404 and json.loads(response) == {"error": "NO_CHECKPOINT"}
            status, response = request(
                port, service_tls, "/v1/audit/append", raw, credential=f.writer
            )
            assert status == 200 and json.loads(response)["checkpoint_jws"] == f.latest()
            persisted = all_rows(f)
            assert (
                request(port, service_tls, "/v1/audit/append", raw, credential=f.writer)[1]
                == response
            )
            assert all_rows(f) == persisted
        elif case == "badTLS":
            with pytest.raises(ssl.SSLCertVerificationError):
                request(
                    port,
                    service_tls,
                    "/v1/audit/append",
                    raw,
                    credential=f.writer,
                    context=ssl.create_default_context(),
                )
            ctx = ssl.create_default_context(cafile=str(service_tls / "ca.pem"))
            with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                with pytest.raises(ssl.SSLCertVerificationError):
                    ctx.wrap_socket(sock, server_hostname="wrong.agent-guard.test")
            plain = http.client.HTTPConnection("localhost", port, timeout=5)
            with pytest.raises((ConnectionError, OSError, http.client.HTTPException)):
                plain.request("POST", "/v1/audit/append", raw)
                plain.getresponse()
            plain.close()
            # A stalled unauthenticated TLS handshake cannot monopolize the
            # fixed listener beyond its finite handshake deadline.
            with socket.create_connection(("127.0.0.1", port), timeout=5):
                status, _ = request(
                    port,
                    service_tls,
                    "/v1/audit/latest",
                    canonical_json_bytes({"stream_id": f.scope.stream_id}),
                    credential_id="reader",
                    credential=f.reader,
                )
                assert status == 404
            assert all_rows(f) == before
        elif case == "wrongrole":
            status, _ = request(
                port,
                service_tls,
                "/v1/audit/append",
                raw,
                credential_id="reader",
                credential=f.reader,
            )
            assert status == 403
            for name in ("as", "holder", "gateway", "downstream"):
                status, _ = request(
                    port,
                    service_tls,
                    "/v1/audit/append",
                    raw,
                    credential_id=name,
                    credential=f.writer,
                )
                assert status == 401
            status, _ = request(
                port,
                service_tls,
                "/v1/audit/latest",
                canonical_json_bytes({"stream_id": f.scope.stream_id}),
                credential=f.writer,
            )
            assert status == 403 and all_rows(f) == before
        elif case == "crossscope":
            from dataclasses import replace

            from tests.fixtures.a31_audit_service import records

            scope = replace(f.scope, stream_id="00000000-0000-0000-0000-000000000002")
            other = encode_append_batch(scope.stream_id, records(scope, 1)).exact_body
            assert (
                request(port, service_tls, "/v1/audit/append", other, credential=f.writer)[0] == 403
            )
            assert (
                request(port, service_tls, "/v1/audit/register", raw, credential=f.writer)[0] == 404
            )
            assert all_rows(f) == before
        else:
            for value, method, content_type, expected in [
                (raw, "GET", "application/json", 405),
                (raw, "POST", "text/plain", 415),
                (b'{"stream_id":"x","stream_id":"x"}', "POST", "application/json", 400),
                (b"A" * 65537, "POST", "application/json", 400),
            ]:
                status, response = request(
                    port,
                    service_tls,
                    "/v1/audit/append",
                    value,
                    credential=f.writer,
                    method=method,
                    content_type=content_type,
                )
                assert status == expected
                assert f.writer.encode() not in response and f.dsn.encode() not in response
            ctx = ssl.create_default_context(cafile=str(service_tls / "ca.pem"))
            for headers in (
                "Content-Length: 2\r\nContent-Length: 2",
                "Content-Length: 2\r\nTransfer-Encoding: chunked",
            ):
                with (
                    socket.create_connection(("127.0.0.1", port), timeout=5) as sock,
                    ctx.wrap_socket(sock, server_hostname="localhost") as tls,
                ):
                    tls.sendall(
                        (
                            "POST /v1/audit/append HTTP/1.1\r\nHost: localhost\r\nContent-Type: ap"
                            "plication/json\r\nAuthorization: Bearer writer:"
                            + f.writer
                            + "\r\n"
                            + headers
                            + "\r\n\r\n{}"
                        ).encode()
                    )
                    assert b"400" in tls.recv(4096).split(b"\r\n")[0]
            assert all_rows(f) == before
        assert foreign_rows() == foreign
    finally:
        server.shutdown()
        server.server_close()
        thread.join(10)
        assert not thread.is_alive()


def test_operator_cli_private_init_registration_and_config(audit_service, service_tls, tmp_path):
    f = audit_service
    private = tmp_path / "operator"
    private.mkdir(mode=0o700)
    connection = private_json(
        private / "connection.json", {"dsn": f.dsn, "owner_role": f.owner_role}
    )

    def run(action, value=None):
        args = [
            sys.executable,
            "-m",
            "agent_guard.audit.operator_cli",
            action,
            "--connection",
            str(connection),
        ]
        if value is not None:
            input_path = private_json(private / "input.json", value)
            args += ["--input", str(input_path)]
        result = subprocess.run(args, capture_output=True, timeout=30)
        assert (
            f.writer.encode() not in result.stdout + result.stderr
            and f.dsn.encode() not in result.stdout + result.stderr
        )
        return result

    assert run("init").returncode == 0 and run("check").returncode == 0
    value = {
        "credential_id": "cli-reader",
        "credential": f.reader,
        "role": "READER",
        "stream_id": f.scope.stream_id,
    }
    assert run("register-principal", value).returncode == 0
    assert run("register-principal", {**value, "role": "WRITER"}).returncode == 1
    assert (
        run(
            "register-key",
            {**asdict(f.trust), "spki_der": b64url_encode(f.trust.spki_der)},
        ).returncode
        == 0
    )
    with psycopg.connect(f.dsn) as conn:
        descriptor = json.loads(
            bytes(conn.execute("SELECT public_descriptor FROM ag_checkpoint_streams").fetchone()[0])
        )
    assert run("register-stream", descriptor).returncode == 0
    key_path = private / "audit.key"
    key_path.write_bytes(
        f.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    config = {
        "dsn": f.dsn,
        "owner_role": f.owner_role,
        "key_id": f.trust.kid,
        "private_key_path": str(key_path),
        "tls_certificate": str(service_tls / "server.pem"),
        "tls_private_key": str(service_tls / "server.key"),
        "host": "127.0.0.1",
        "port": 23456,
        "external_pins": [],
        "external_trust": [],
    }
    config_path = private_json(private / "config.json", config)
    assert AuditConfig.load(config_path).signing_key().curve.name == "SM2"
    config_path.chmod(0o644)
    with pytest.raises(ValueError):
        AuditConfig.load(config_path)
    config_path.chmod(0o600)
    for field, bad in (
        ("host", "0.0.0.0"),
        ("dsn", f.dsn.replace("verify-full", "require")),
        ("port", True),
    ):
        private_json(config_path, {**config, field: bad})
        with pytest.raises(ValueError):
            AuditConfig.load(config_path)


@pytest.mark.parametrize("host", ["10.23.0.4", "172.20.0.4", "192.168.23.4"])
def test_explicit_approved_private_listener_validation(host):
    from agent_guard.audit.config import validate_approved_listener

    validate_approved_listener(host, host)


@pytest.mark.parametrize(
    "host,approved",
    [
        ("10.23.0.4", None),
        ("10.23.0.4", "10.23.0.5"),
        ("0.0.0.0", "0.0.0.0"),
        ("8.8.8.8", "8.8.8.8"),
        ("169.254.1.1", "169.254.1.1"),
        ("224.0.0.1", "224.0.0.1"),
        ("127.0.0.1", "127.0.0.1"),
        ("audit.agent-guard.test", "audit.agent-guard.test"),
        ("010.23.0.4", "010.23.0.4"),
        ("10.23.0.4", True),
        (True, "10.23.0.4"),
        ("10.23.0.4", 123),
    ],
)
def test_server_rejects_unapproved_listener_before_store(host, approved):
    from types import SimpleNamespace

    with pytest.raises(ValueError):
        create_server(SimpleNamespace(host=host), approved_listener_host=approved)


@pytest.mark.parametrize(
    "host,approved",
    [
        ("10.23.0.4", None),
        ("10.23.0.4", "10.23.0.5"),
        ("0.0.0.0", "0.0.0.0"),
        ("8.8.8.8", "8.8.8.8"),
        ("10.23.0.4", True),
    ],
)
def test_load_rejects_unapproved_listener_independently(tmp_path, host, approved):
    directory = tmp_path / "private-listener"
    directory.mkdir(mode=0o700)
    path = directory / "config.json"
    value = {
        "dsn": "unused",
        "owner_role": "unused",
        "key_id": "unused",
        "private_key_path": "unused",
        "tls_certificate": "unused",
        "tls_private_key": "unused",
        "host": host,
        "port": 443,
        "external_pins": [],
        "external_trust": [],
    }
    path.write_bytes(canonical_json_bytes(value))
    path.chmod(0o600)
    with pytest.raises(ValueError):
        AuditConfig.load(path, approved_listener_host=approved)


@pytest.mark.parametrize("host", ["10.23.0.4", "172.20.0.4", "192.168.23.4"])
def test_load_exact_private_listener_preserves_tls_private_gates(tmp_path, service_tls, host):
    from agent_guard.crypto.sm import generate_sm2_private_key

    directory = tmp_path / "approved-listener"
    directory.mkdir(mode=0o700)
    key = generate_sm2_private_key()
    signing = directory / "signing.pem"
    signing.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    signing.chmod(0o600)
    value = {
        "dsn": (
            "host=pg-audit.agent-guard.test dbname=ag_audit user=demo_a"
            "udit sslmode=verify-full sslrootcert="
        )
        + str(service_tls / "ca.pem"),
        "owner_role": "demo_audit",
        "key_id": "audit-sign-1",
        "private_key_path": str(signing),
        "tls_certificate": str(service_tls / "server.pem"),
        "tls_private_key": str(service_tls / "server.key"),
        "host": host,
        "port": 443,
        "external_pins": [],
        "external_trust": [],
    }
    path = private_json(directory / "config.json", value)
    loaded = AuditConfig.load(path, approved_listener_host=host)
    assert loaded.host == host and loaded.port == 443
    assert loaded.signing_key().curve.name == "SM2"
    for field, bad in (
        ("dsn", value["dsn"].replace("verify-full", "require")),
        ("port", True),
    ):
        private_json(path, {**value, field: bad})
        with pytest.raises(ValueError):
            AuditConfig.load(path, approved_listener_host=host)
    private_json(path, value)
    signing.chmod(0o644)
    with pytest.raises(ValueError):
        AuditConfig.load(path, approved_listener_host=host)
