"""Verified TLS transport, default did:web networking and actual CLI processes.

Only controlled DNS is remapped; the production urllib fetcher and its certificate
and hostname validation remain intact. Synthetic factory snapshots are separate.
"""

from __future__ import annotations

import copy
import http.client
import socket
import ssl
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg
import pytest
import uvicorn

from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
from agent_guard.identity.resolver import (
    SPKI_PROPERTY,
    IdentityError,
    IdentityResolver,
    RegisteredIdentity,
)
from agent_guard.server.middleware import RequestTimeoutMiddleware
from tests.integration.test_browser_boundary import KINDS, _stack, _state, _valid
from tests.test_authorization import DID, KID, _fixture
from tests.test_http_request_limits import ALL_ROUTES, media, recording_app

pytestmark = pytest.mark.integration


def tls_files(directory, host="localhost"):
    """Generate a real test CA and a separately signed SAN server certificate."""
    ca, ca_key = directory / "ca.pem", directory / "ca-key.pem"
    cert, key, csr = directory / "cert.pem", directory / "key.pem", directory / "cert.csr"
    ext = directory / "cert.ext"
    ext.write_text(
        f"subjectAltName=DNS:{host}\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n"
    )
    commands = [
        [
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=Synthetic-CA",
            "-keyout",
            ca_key,
            "-out",
            ca,
        ],
        [
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            f"/CN={host}",
            "-keyout",
            key,
            "-out",
            csr,
        ],
        [
            "x509",
            "-req",
            "-in",
            csr,
            "-CA",
            ca,
            "-CAkey",
            ca_key,
            "-CAcreateserial",
            "-days",
            "1",
            "-extfile",
            ext,
            "-out",
            cert,
        ],
    ]
    for command in commands:
        done = subprocess.run(["openssl", *map(str, command)], capture_output=True, timeout=30)
        assert done.returncode == 0, "synthetic certificate generation failed"
    key.chmod(0o600)
    ca_key.chmod(0o600)
    return ca, cert, key


@contextmanager
def https_server(app, directory):
    ca, cert, key = tls_files(directory)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        ssl_certfile=str(cert),
        ssl_keyfile=str(key),
        log_level="critical",
        access_log=False,
        proxy_headers=False,
        lifespan="off",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started and server.servers
        port = server.servers[0].sockets[0].getsockname()[1]
        yield port, ca
    finally:
        server.should_exit = True
        thread.join(15)
        assert not thread.is_alive(), "owned HTTPS server failed to stop"


def connection(port, ca, host="localhost"):
    context = ssl.create_default_context(cafile=str(ca))
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    return http.client.HTTPSConnection(host, port, context=context, timeout=10)


def request(port, ca, path, body=b"", headers=(), method="POST", chunks=False):
    conn = connection(port, ca)
    try:
        conn.putrequest(method, path)
        for name, value in headers:
            conn.putheader(
                name.decode() if isinstance(name, bytes) else name,
                value.decode() if isinstance(value, bytes) else value,
            )
        conn.putheader(
            "Transfer-Encoding" if chunks else "Content-Length",
            "chunked" if chunks else str(len(body)),
        )
        conn.endheaders()
        if chunks:
            for chunk in (body[:32768], body[32768:]):
                if chunk:
                    conn.send(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
            conn.send(b"0\r\n\r\n")
        elif body:
            conn.send(body)
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


@pytest.mark.parametrize("kind", KINDS)
def test_real_https_route_refusals_preserve_rows_then_succeed(ledger, dsn, tmp_path, kind):
    ctx = _stack(dsn)
    path, valid, headers, success = _valid(ctx, kind)
    before = _state(dsn)
    with https_server(RequestTimeoutMiddleware(ctx.app, timeout_seconds=2), tmp_path) as (port, ca):
        cases = [
            (b"x" * 65537, headers, False, 413),
            (b"x" * 65537, headers, True, 413),
            (valid, [], False, 415),
            (valid, [(b"content-type", b"text/plain"), *headers[1:]], False, 415),
            (valid, [*headers, headers[0]], False, 400),
            (valid, [*headers, (b"content-encoding", b"gzip")], False, 415),
        ]
        for body, supplied, chunks, expected in cases:
            status, error = request(port, ca, path, body, supplied, chunks=chunks)
            assert status == expected
            assert all(
                secret not in error
                for secret in (b"synthetic", b"Traceback", b"secret-token-marker")
            )
            assert _state(dsn) == before
        # Exact maximum reaches real semantic validation, not transport413/500.
        status, _ = request(port, ca, path, b"x" * 65536, headers, chunks=True)
        assert 400 <= status < 500 and status != 413
        assert _state(dsn) == before
        # Valid authenticated requests still traverse the same verified TLS server.
        assert request(port, ca, path, valid, headers)[0] == success


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_verified_tls_exact_transport_boundary_and_get_routes(tmp_path, route):
    path, method = route
    app, handlers = recording_app()
    with https_server(app, tmp_path) as (port, ca):
        if method == "POST":
            for chunked in (False, True):
                assert (
                    request(
                        port,
                        ca,
                        path,
                        b"x" * 65536,
                        [(b"content-type", media(path))],
                        chunks=chunked,
                    )[0]
                    == 200
                )
                assert (
                    len(handlers.calls[-1].get("body", handlers.calls[-1].get("raw_form"))) == 65536
                )
        else:
            assert request(port, ca, path, method="GET")[0] == 200
            before = len(handlers.calls)
            assert request(port, ca, path, b"forbidden", method="GET")[0] == 400
            assert len(handlers.calls) == before
        # A trusted CA with the wrong hostname and an untrusted CA both refuse.
        for host, context in [
            ("127.0.0.1", ssl.create_default_context(cafile=str(ca))),
            ("localhost", ssl.create_default_context()),
        ]:
            conn = http.client.HTTPSConnection(host, port, context=context, timeout=5)
            try:
                with pytest.raises(ssl.SSLCertVerificationError):
                    conn.request("GET", "/ag/keys")
                    conn.getresponse()
            finally:
                conn.close()


def test_real_https_database_failure_internal_error_and_stalled_input(
    ledger, dsn, tmp_path, monkeypatch
):
    ctx = _stack(dsn)
    path, valid, headers, _ = _valid(ctx, "token")
    before = _state(dsn)
    with https_server(RequestTimeoutMiddleware(ctx.app, timeout_seconds=1), tmp_path) as (port, ca):
        with monkeypatch.context() as patch:
            patch.setattr(
                ctx.s.codes,
                "_dsn",
                psycopg.conninfo.make_conninfo(dsn, dbname="ag_s4_absent_database"),
            )
            assert request(port, ca, path, valid, headers)[0] == 503
        assert _state(dsn) == before

        def broken(**kwargs):
            raise RuntimeError("synthetic-secret-marker")

        with monkeypatch.context() as patch:
            patch.setattr(ctx.app._token, "handle", broken)
            status, body = request(port, ca, path, valid, headers)
            assert status == 500 and b"synthetic-secret-marker" not in body
        assert _state(dsn) == before
        conn = connection(port, ca)
        try:
            conn.putrequest("POST", path)
            for name, value in headers:
                conn.putheader(name.decode(), value.decode())
            conn.putheader("Content-Length", "100")
            conn.endheaders()
            conn.send(b"x")
            response = conn.getresponse()
            assert response.status == 503
            assert b"TIMEOUT" in response.read()
        finally:
            conn.close()
        assert _state(dsn) == before
        # Real disconnect before complete framing is observed; no response is
        # asserted after the client has gone, only the promised no effects.
        conn = connection(port, ca)
        conn.putrequest("POST", path)
        conn.putheader("Content-Type", "application/x-www-form-urlencoded")
        conn.putheader("Content-Length", "100")
        conn.endheaders()
        conn.send(b"x")
        conn.close()
        assert request(port, ca, "/ag/keys", method="GET")[0] == 200
        assert _state(dsn) == before
        assert request(port, ca, path, valid, headers)[0] == 200


@pytest.fixture
def did_network(tmp_path, monkeypatch):
    _, holder, doc, _, _ = _fixture()
    registered = RegisteredIdentity(
        "tenant-001", "agent-planner", DID, KID, serialize_sm2_public_key(holder.public_key())
    )
    host = "identity.agent-guard.test"
    ca, cert, key = tls_files(tmp_path, host)
    state = {
        "document": copy.deepcopy(doc),
        "hits": [],
        "redirect": False,
        "media": "application/did+json",
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state["hits"].append(self.path)
            self.send_response(302 if state["redirect"] else 200)
            if state["redirect"]:
                self.send_header("Location", "https://unapproved.example/internal")
            self.send_header("Content-Type", state["media"])
            self.end_headers()
            if not state["redirect"]:
                self.wfile.write(canonical_json_bytes(state["document"]))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    original_dns = socket.getaddrinfo

    def mapped(name, port, *args, **kwargs):
        if name in (host, "wrong.agent-guard.test"):
            return original_dns("127.0.0.1", server.server_port, *args, **kwargs)
        raise AssertionError("unapproved DNS target reached")

    monkeypatch.setattr(socket, "getaddrinfo", mapped)
    monkeypatch.setenv("SSL_CERT_FILE", str(ca))
    monkeypatch.setenv("NO_PROXY", "*")
    for name in (
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    resolver = IdentityResolver(
        {("tenant-001", "agent-planner"): registered}, allowed_hosts=frozenset({host})
    )
    try:
        yield resolver, state, registered, ca
    finally:
        server.shutdown()
        server.server_close()
        thread.join(10)
        assert not thread.is_alive()


def test_default_did_fetch_really_verifies_ca_hostname_and_redirects(did_network, monkeypatch):
    resolver, state, reg, _ = did_network
    assert (
        resolver.resolve_registered("agent-planner", "tenant-001", "authentication").registration
        == reg
    )
    assert state["hits"] == ["/agents/planner/did.json"]
    with monkeypatch.context() as patch:
        patch.delenv("SSL_CERT_FILE")
        with pytest.raises(IdentityError, match="unavailable"):
            resolver.resolve_registered("agent-planner", "tenant-001", "authentication")
    assert len(state["hits"]) == 1
    wrong = replace(
        reg, did=reg.did.replace("identity.", "wrong."), kid=reg.kid.replace("identity.", "wrong.")
    )
    with pytest.raises(IdentityError, match="unavailable"):
        IdentityResolver(
            {("tenant-001", "agent-planner"): wrong},
            allowed_hosts=frozenset({"wrong.agent-guard.test"}),
        ).resolve_registered("agent-planner", "tenant-001", "authentication")
    assert len(state["hits"]) == 1
    state["redirect"] = True
    with pytest.raises(IdentityError, match="redirect"):
        resolver.resolve_registered("agent-planner", "tenant-001", "authentication")
    assert len(state["hits"]) == 2


@pytest.mark.parametrize(
    "variant", ["unknown", "tenant", "host", "private-ip", "path", "purpose", "disabled"]
)
def test_default_did_unapproved_targets_never_reach_network(did_network, variant):
    resolver, state, reg, _ = did_network
    client, tenant, purpose = "agent-planner", "tenant-001", "authentication"
    if variant == "unknown":
        client = "unknown"
    elif variant == "tenant":
        tenant = "other"
    elif variant == "purpose":
        purpose = "receipt"
    else:
        did = {
            "host": "did:web:evil.example:agents:planner",
            "private-ip": "did:web:127.0.0.1:agents:planner",
            "path": "did:web:identity.agent-guard.test:..:planner",
            "disabled": reg.did,
        }[variant]
        reg = replace(reg, did=did, kid=did + "#key-1", active=variant != "disabled")
        resolver = IdentityResolver(
            {("tenant-001", "agent-planner"): reg},
            allowed_hosts=frozenset({"identity.agent-guard.test"}),
        )
    with pytest.raises(IdentityError):
        resolver.resolve_registered(client, tenant, purpose)
    assert state["hits"] == []


@pytest.mark.parametrize(
    "variant",
    [
        "authentication",
        "capabilityInvocation",
        "capabilityDelegation",
        "controller",
        "spki",
        "id",
        "media",
    ],
)
def test_default_did_live_document_binding_negatives_and_positive(did_network, variant):
    resolver, state, reg, _ = did_network
    original = copy.deepcopy(state["document"])
    purpose = (
        variant
        if variant in ("authentication", "capabilityInvocation", "capabilityDelegation")
        else "authentication"
    )
    assert resolver.resolve_registered("agent-planner", "tenant-001", purpose).registration == reg
    if variant == "controller":
        state["document"]["verificationMethod"][0]["controller"] = "did:web:evil.example"
    elif variant == "spki":
        state["document"]["verificationMethod"][0][SPKI_PROPERTY] = b64url_encode(
            serialize_sm2_public_key(generate_sm2_private_key().public_key())
        )
    elif variant == "id":
        state["document"]["id"] = "did:web:evil.example"
    elif variant == "media":
        state["media"] = "text/html"
    else:
        state["document"][variant] = []
    with pytest.raises(IdentityError):
        resolver.resolve_registered("agent-planner", "tenant-001", purpose)
    state["document"] = original
    state["media"] = "application/did+json"
    assert resolver.resolve_registered("agent-planner", "tenant-001", purpose).registration == reg


@pytest.mark.parametrize("mask", [0o022, 0o077])
def test_actual_cli_init_check_and_verified_tls_run(ledger, dsn, tmp_path, mask):
    import os

    from tests.test_server_private_files import _cli

    out = tmp_path / "cli-config"
    assert _cli("init", "--out", out, umask=mask).returncode == 0
    assert _cli("check", "--config", out / "config.json", umask=mask).returncode == 0
    ca, cert, key = tls_files(tmp_path)
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    env = dict(os.environ)
    env["AGENT_GUARD_DATABASE_URL"] = dsn  # explicit owned synthetic CLI target
    process = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-m",
            "agent_guard.server",
            "run",
            "--config",
            str(out / "config.json"),
            "--port",
            str(port),
            "--ssl-certfile",
            str(cert),
            "--ssl-keyfile",
            str(key),
        ],
        env=env,
        umask=mask,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 15
        while True:
            assert process.poll() is None, "CLI exited before listening"
            try:
                status, body = request(port, ca, "/.well-known/openid-configuration", method="GET")
                break
            except ConnectionRefusedError:
                assert time.monotonic() < deadline
                time.sleep(0.02)
        assert status == 200 and b"https://auth.agent-guard.test" in body
    finally:
        if process.poll() is None:
            process.terminate()
        stdout, stderr = process.communicate(timeout=15)
    # uvicorn 0.35 restores and re-raises captured SIGTERM after shutdown.
    # This is cleanup of a proven live HTTPS positive, not a refusal result.
    assert process.returncode == -15
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection(("127.0.0.1", port), timeout=2)
    assert b"Traceback" not in stderr
    assert b"BEGIN PRIVATE KEY" not in stdout + stderr
    assert dsn.encode() not in stdout + stderr


def test_default_did_new_key_requires_explicit_new_registration(did_network):
    resolver, state, reg, _ = did_network
    assert resolver.resolve_registered(reg.client_id, reg.tenant_id, "authentication")
    new_key = generate_sm2_private_key()
    new_reg = replace(
        reg, kid=reg.did + "#key-2", spki_der=serialize_sm2_public_key(new_key.public_key())
    )
    document = state["document"]
    document["verificationMethod"][0]["id"] = new_reg.kid
    document["verificationMethod"][0][SPKI_PROPERTY] = b64url_encode(new_reg.spki_der)
    for purpose in ("authentication", "capabilityInvocation", "capabilityDelegation"):
        document[purpose] = [new_reg.kid]
    with pytest.raises(IdentityError):
        resolver.resolve_registered(reg.client_id, reg.tenant_id, "authentication")
    approved = IdentityResolver(
        {(reg.tenant_id, reg.client_id): new_reg},
        allowed_hosts=frozenset({"identity.agent-guard.test"}),
    )
    assert (
        approved.resolve_registered(reg.client_id, reg.tenant_id, "authentication").registration
        == new_reg
    )
    stopped = IdentityResolver(
        {(reg.tenant_id, reg.client_id): replace(new_reg, active=False)},
        allowed_hosts=frozenset({"identity.agent-guard.test"}),
    )
    hits = len(state["hits"])
    with pytest.raises(IdentityError):
        stopped.resolve_registered(reg.client_id, reg.tenant_id, "authentication")
    assert len(state["hits"]) == hits
