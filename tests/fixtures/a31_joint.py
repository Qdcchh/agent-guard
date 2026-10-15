"""Test-owned joint assembly using the frozen real delivery and HTTPS AS material.

The protocol below is a TEST adapter contract, not a claim about uninspected product APIs.
No ignored artifact, host absolute path, invented resource owner or token is consumed.
"""

from __future__ import annotations

import http.client
import json
import os
import secrets
import signal
import ssl
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

import psycopg
import pytest
from tongsuopy.crypto import serialization

from agent_guard.audit.contracts import CheckpointTrust, JournalScope, RegistrationDescriptor
from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes, load_strict_json
from agent_guard.crypto.sm import generate_sm2_private_key, serialize_sm2_public_key
from tests.fixtures.a31_audit_service import private_json, record_native
from tests.fixtures.isolation import acquire_namespace, assert_owned, release_namespace
from tests.fixtures.receipts import full_state, result_read_only
from tests.integration.test_gateway_tls import certificates, fresh_port, start_gateway, stop_gateway


def assert_query_delta(before, after, bundle, operation_id, *, observed_response=None):
    """Exact proof/ref/op and QUERY records, all tables/accepted alias/four counters retained."""
    result_read_only(
        {"gateway": before, "downstream": {}},
        {"gateway": after, "downstream": {}},
        evidence_ref=bundle.evidence_ref,
        proof_jti=bundle.query.proof_jti,
        operation_id=operation_id,
        staging=False,
        observed_response=observed_response,
    )


def run_operator(connection, action, value=None):
    argv = [
        sys.executable,
        "-m",
        "agent_guard.audit.operator_cli",
        action,
        "--connection",
        str(connection),
    ]
    if value is not None:
        path = private_json(connection.parent / "operator-input.json", value)
        argv += ["--input", str(path)]
    result = subprocess.run(argv, capture_output=True, timeout=60)
    record_native(
        "joint-operator-cli",
        {
            "argv": argv,
            "returncode": result.returncode,
            "stdout": result.stdout.decode("utf-8"),
            "stderr": result.stderr.decode("utf-8"),
        },
    )
    return result


def bootstrap_cli(dsn, action, *, tenant_id="tenant-001", task_id="task-001"):
    child = dict(os.environ, AGENT_GUARD_DATABASE_URL=dsn)
    args = [
        sys.executable,
        "-m",
        "agent_guard.audit.bootstrap_cli",
        action,
        "--tenant-id",
        tenant_id,
        "--task-id",
        task_id,
    ]
    if action == "bootstrap":
        args += ["--writers-stopped-and-drained"]
    result = subprocess.run(args, env=child, capture_output=True, timeout=60)
    record_native(
        "joint-bootstrap-cli",
        {
            "argv": args,
            "returncode": result.returncode,
            "stdout": result.stdout.decode("utf-8"),
            "stderr": result.stderr.decode("utf-8"),
        },
    )
    assert result.returncode == 0, "private bootstrap output retained by owned runner"
    return json.loads(result.stdout)


def audit_request(port, ca, route, value, *, credential_id, credential):
    ctx = ssl.create_default_context(cafile=str(ca))
    assert ctx.check_hostname and ctx.verify_mode == ssl.CERT_REQUIRED
    conn = http.client.HTTPSConnection("localhost", port, context=ctx, timeout=5)
    try:
        conn.request(
            "POST",
            route,
            canonical_json_bytes(value),
            {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + credential_id + ":" + credential,
            },
        )
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally:
        conn.close()


@dataclass
class JointRuntime:
    env: object = field(repr=False)
    gateway_dsn: str = field(repr=False)
    downstream_dsn: str = field(repr=False)
    audit_namespace: object = field(repr=False)
    descriptor: RegistrationDescriptor
    trust: CheckpointTrust
    reader_token: str = field(repr=False)
    writer_token: str = field(repr=False)
    audit_port: int
    gateway_port: int
    gateway_context: object = field(repr=False)
    audit_tls: Path
    private: Path
    connection: Path
    audit_process: object = field(repr=False)
    as_material: dict = field(repr=False)
    receipt_key: object = field(repr=False)
    native_children: list = field(default_factory=list, repr=False)

    def all_domains(self):
        assert_owned(self.audit_namespace)
        state = full_state(self.gateway_dsn, self.downstream_dsn)
        with psycopg.connect(self.audit_namespace.dsn) as conn:
            names = conn.execute(
                (
                    "SELECT tablename FROM pg_tables WHERE "
                    "schemaname=current_schema() ORDER BY tablename"
                )
            ).fetchall()
            state["audit"] = {
                name: conn.execute(
                    psycopg.sql.SQL(
                        "SELECT row_to_json(t)::text FROM {} t ORDER BY row_to_json(t)::text"
                    ).format(psycopg.sql.Identifier(name))
                ).fetchall()
                for (name,) in names
            }
        return state

    def reader_latest(self):
        return audit_request(
            self.audit_port,
            self.audit_tls / "ca.pem",
            "/v1/audit/latest",
            {"stream_id": self.descriptor.scope.stream_id},
            credential_id="joint-reader",
            credential=self.reader_token,
        )


class FrozenDeliveryBinding(Protocol):
    """Test adapter bound to the actual frozen product APIs.

    persist_pending: real immutable local batch, no HTTP while DB locks held.
    send_pending_lost_reply: native send/remote commit/process SIGKILL/new PID, same body.
    restart_and_reconcile: same persistent DB and externally acquired original JWS pin.
    read_remote_prefix: real external READER pages, fixed pin, pure authenticated proof.
    These names are deliberately not product API guesses.
    """

    def persist_pending(self): ...
    def pending_snapshot(self): ...
    def send_pending_lost_reply(self): ...
    def restart_and_reconcile(self, external_pin: str): ...
    def cursor_snapshot(self): ...
    def read_remote_prefix(self, external_pin: str): ...
    def check_cli(self): ...
    def reject_untrusted_pin(self, external_pin: str): ...


class JointDeliveryBinding:
    """Real frozen delivery, native CLI kill/restart and independently pinned HTTPS reader."""

    def __init__(self, runtime):
        from agent_guard.audit.client import AuditClient
        from agent_guard.audit.delivery import DeliveryWorker

        self.runtime = runtime
        self.directory = runtime.private / "delivery"
        self.directory.mkdir(mode=0o700)
        self.config = private_json(
            self.directory / "config.json",
            {
                "origin": "https://localhost:" + str(runtime.audit_port),
                "ca_file": str(runtime.audit_tls / "ca.pem"),
                "writer_credential": "joint-writer:" + runtime.writer_token,
                "reader_credential": "joint-reader:" + runtime.reader_token,
                "trust": [
                    {**asdict(runtime.trust), "spki_der": b64url_encode(runtime.trust.spki_der)}
                ],
            },
        )
        self.client = AuditClient(
            "https://localhost:" + str(runtime.audit_port),
            ca_file=str(runtime.audit_tls / "ca.pem"),
            writer_credential="joint-writer:" + runtime.writer_token,
            reader_credential="joint-reader:" + runtime.reader_token,
            timeout=5,
        )
        self.worker = DeliveryWorker(self.connect, self.client, trust=(runtime.trust,))
        self.replacement = None
        self.release = self.directory / "release"
        with self.connect() as conn:
            conn.execute(
                "UPDATE ag_audit_delivery SET registration_state='REGISTERED' WHERE stream_id=%s",
                (runtime.descriptor.scope.stream_id,),
            )

    def connect(self):
        conn = psycopg.connect(self.runtime.gateway_dsn, connect_timeout=5)
        conn.execute("SET lock_timeout='3s'")
        conn.execute("SET statement_timeout='30s'")
        conn.commit()
        return conn

    def persist_pending(self):
        from agent_guard.audit.delivery import prepare_pending_tx

        with self.connect() as conn:
            result = prepare_pending_tx(conn, self.runtime.descriptor.scope.stream_id)
        assert result is not None
        return result

    def pending_snapshot(self):
        return self.persist_pending()

    def cursor_snapshot(self):
        from agent_guard.audit.contracts import DeliveryCursor

        with self.connect() as conn:
            row = conn.execute(
                "SELECT "
                "stream_id,ack_sequence,ack_head_digest,"
                "ack_checkpoint_digest,pending_batch_id "
                "FROM ag_audit_delivery WHERE stream_id=%s",
                (self.runtime.descriptor.scope.stream_id,),
            ).fetchone()
        return DeliveryCursor(*row)

    def check_cli(self):
        done = subprocess.run(
            [sys.executable, "-m", "agent_guard.audit.delivery_cli", "--help"],
            capture_output=True,
            timeout=30,
        )
        record_native(
            "joint-delivery-cli-help",
            {
                "returncode": done.returncode,
                "stdout": done.stdout.decode(),
                "stderr": done.stderr.decode(),
            },
        )
        return done.returncode

    def _launch(self, *, kill_window):
        marker = self.directory / (
            "remote-committed.json" if kill_window else "replacement-ready.json"
        )
        # Test-only observer wraps the real client in the native CLI process. It pauses
        # only after the real audit service committed and returned its original JWS.
        script = r"""
import hashlib,json,os,pathlib,sys,time
from tests.fixtures.a31_delivery import atomic_marker
from agent_guard.audit.client import AuditClient
from agent_guard.audit.delivery_cli import main
marker,release,config,stream,window=sys.argv[1:]
def identity():
 raw=pathlib.Path('/proc/self/stat').read_text();tail=raw[raw.rfind(')')+2:].split()
 return {'pid':os.getpid(),'uid':os.getuid(),'kernel_start':tail[19],
         'pgid':os.getpgrp(),'argv_sha256':hashlib.sha256(pathlib.Path('/proc/self/cmdline').read_bytes()).hexdigest()}
if window=='kill':
 original=AuditClient.append
 def append(self,batch):
  answer=original(self,batch)
  atomic_marker(marker,identity())
  while True:time.sleep(.01)
 AuditClient.append=append
else:
 atomic_marker(marker,identity())
 deadline=time.monotonic()+30
 while not pathlib.Path(release).exists():
  assert time.monotonic()<deadline
  time.sleep(.01)
code=main(['--config',config,'--stream-id',stream])
print(json.dumps({'identity':identity(),'exit':code}))
sys.exit(code)
"""
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(marker),
                str(self.release),
                str(self.config),
                self.runtime.descriptor.scope.stream_id,
                "kill" if kill_window else "restart",
            ],
            env={**os.environ, "AGENT_GUARD_DATABASE_URL": self.runtime.gateway_dsn},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.runtime.native_children.append(child)
        deadline = time.monotonic() + 20
        while not marker.exists():
            assert child.poll() is None, "native delivery exited before observed barrier"
            assert time.monotonic() < deadline, "finite native delivery barrier"
            time.sleep(0.01)
        observed = load_strict_json(marker.read_bytes())
        assert observed["pid"] == child.pid and observed["uid"] == os.getuid()
        raw = Path("/proc/" + str(child.pid) + "/stat").read_text()
        assert observed["kernel_start"] == raw[raw.rfind(")") + 2 :].split()[19]
        import hashlib

        assert (
            observed["argv_sha256"]
            == hashlib.sha256(Path("/proc/" + str(child.pid) + "/cmdline").read_bytes()).hexdigest()
        )
        assert observed["pgid"] == os.getpgid(child.pid)
        record_native("joint-delivery-native-identity", observed)
        return child

    def send_pending_lost_reply(self):
        child = self._launch(kill_window=True)
        os.kill(child.pid, signal.SIGKILL)
        assert child.wait(10) == -signal.SIGKILL
        out, err = child.communicate()
        record_native(
            "joint-delivery-native-killed",
            {
                "pid": child.pid,
                "exit": child.returncode,
                "stdout": out.decode(),
                "stderr": err.decode(),
            },
        )
        self.replacement = self._launch(kill_window=False)
        assert self.replacement.pid != child.pid
        return child.pid, self.replacement.pid

    def read_remote_prefix(self, external_pin):
        from agent_guard.audit.contracts import ExistingStreamRef, decode_journal_record
        from agent_guard.audit.delivery import authenticate_reconciliation, verify_checkpoint

        observed = verify_checkpoint(
            external_pin, trust=(self.runtime.trust,), expected_scope=self.runtime.descriptor.scope
        )
        families = []
        for read in (self.client.history, self.client.records):
            pages, after = [], 0
            for _ in range(observed.claims.sequence):
                page = read(
                    observed.claims.stream_id,
                    observed_checkpoint_id=observed.claims.checkpoint_id,
                    after_sequence=after,
                )
                pages.append(page)
                if page.next_after_sequence is None:
                    break
                assert (
                    type(page.next_after_sequence) is int
                    and after < page.next_after_sequence <= observed.claims.sequence
                )
                after = page.next_after_sequence
            else:
                raise ValueError("finite reader page boundary exceeded")
            families.append(tuple(pages))
        with self.connect() as conn:
            records = tuple(
                decode_journal_record(bytes(r[0]))
                for r in conn.execute(
                    "SELECT raw FROM ag_audit_records WHERE stream_id=%s ORDER BY seq",
                    (observed.claims.stream_id,),
                )
            )
        proof = authenticate_reconciliation(
            records,
            observed,
            *families,
            (self.runtime.trust,),
            expected_stream=ExistingStreamRef(
                self.runtime.descriptor.scope,
                self.runtime.descriptor.genesis_digest,
                self.runtime.descriptor.bootstrap_digest,
            ),
        )
        return proof.prefix

    def reject_untrusted_pin(self, external_pin):
        return self.read_remote_prefix(external_pin)

    def restart_and_reconcile(self, external_pin):
        prefix = self.read_remote_prefix(external_pin)
        assert prefix.checkpoint_jws == external_pin
        assert self.replacement is not None and self.replacement.poll() is None
        self.release.touch(mode=0o600)
        out, err = self.replacement.communicate(timeout=30)
        assert self.replacement.returncode == 0, "real replacement CLI rejected"
        record_native(
            "joint-delivery-native-replacement",
            {
                "pid": self.replacement.pid,
                "exit": self.replacement.returncode,
                "stdout": out.decode(),
                "stderr": err.decode(),
            },
        )
        assert self.cursor_snapshot().ack_sequence == prefix.sequence


def bind_frozen_delivery(runtime: JointRuntime) -> FrozenDeliveryBinding:
    return JointDeliveryBinding(runtime)


def bind_original_https_as_issuance(dsn, downstream_dsn, private):
    """Native AS CLI, actual browser approval/root/two HTTPS exchanges, same GW material.

    Only trusted policy/principal/user provisioning is SQL. No root or child token
    is constructed through a direct AuthorizationCodeService/ApprovedAuthorization.
    The native listener is stopped and joined before returning maintenance ownership.
    """
    import base64
    import hashlib
    import re
    from datetime import datetime, timedelta, timezone
    from http.cookies import SimpleCookie
    from urllib.parse import parse_qs, urlencode, urlsplit

    from agent_guard.authorization.evidence_store import EvidenceStore
    from agent_guard.authorization.oidc import pkce_s256_challenge, verify_id_token
    from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
    from agent_guard.authorization.proof import sign_ag_proof
    from agent_guard.authorization.provisioning import register_task_policy, register_user
    from agent_guard.authorization.verifier import InvocationVerifier
    from agent_guard.crypto.sm import verify_compact_jws
    from agent_guard.execution.service import ExecutionService
    from agent_guard.execution.verified import VerifiedExecution
    from agent_guard.identity.resolver import IdentityResolver, RegisteredIdentity
    from agent_guard.ledger.provisioning import register_principal
    from agent_guard.ledger.service import ExecutionLedger
    from agent_guard.server.config import load_secrets, load_server_config, resolve_paths
    from agent_guard.server.private_files import read_private_file
    from agent_guard.tools.downstream import MockDownstream
    from tests.fixtures.execution import DOWNSTREAM_SECRET, build_catalog
    from tests.integration.test_exchange_service import _form
    from tests.integration.test_verified_execution import CONSTRAINTS, TOOLS, SignedEnv

    issuer = "https://auth.agent-guard.test"
    tenant = "tenant-001"
    subject = "user-001"
    task = "task-001"
    directory = private / "as"
    password = secrets.token_urlsafe(36)
    commands = []

    def cli(args, *, environment=None):
        done = subprocess.run(
            [sys.executable, "-m", "agent_guard.server", *args],
            env=environment,
            capture_output=True,
            timeout=60,
        )
        assert done.returncode == 0, "AS native CLI rejected; private raw output retained"
        commands.append({"action": args[0], "exit": done.returncode})
        record_native(
            "joint-as-cli",
            {
                "argv": [sys.executable, "-m", "agent_guard.server", *args],
                "returncode": done.returncode,
                "stdout": done.stdout.decode("utf-8"),
                "stderr": done.stderr.decode("utf-8"),
            },
        )
        return done

    cli(["init", "--out", str(directory), "--issuer", issuer])
    config_path = directory / "config.json"
    value = json.loads(read_private_file(config_path))
    assert value["issuer"] == issuer and value["signing_kid"] == "as-sign-1"
    assert set(value["clients"]) == {"agent-planner", "agent-selector", "agent-executor"}
    for registration in value["clients"].values():
        registration["tenant_id"] = tenant
    for registration in value["identities"].values():
        registration["tenant_id"] = tenant
    private_json(config_path, value)
    config = resolve_paths(load_server_config(read_private_file(config_path)), directory)
    secret_bundle = load_secrets(read_private_file(config.secrets_path))

    def load_key(name):
        return serialization.load_pem_private_key(
            read_private_file(directory / name), password=None
        )

    as_key = load_key("as-sign-key.pem")
    keys = {
        holder: load_key("agent-" + holder + ".pem")
        for holder in ("planner", "selector", "executor")
    }
    as_keys = {config.signing_kid: as_key.public_key()}
    for kid, pem in config.historical_verification_keys.items():
        as_keys[kid] = serialization.load_pem_public_key(pem.encode("ascii"))
    registrations = {}
    for client_id, identity in config.identities.items():
        key = keys[client_id.removeprefix("agent-")]
        public = serialization.load_pem_public_key(identity.spki_pem.encode("ascii"))
        assert serialize_sm2_public_key(key.public_key()) == serialize_sm2_public_key(public)
        registrations[(tenant, client_id)] = RegisteredIdentity(
            tenant, client_id, identity.did, identity.kid, serialize_sm2_public_key(public)
        )
    with psycopg.connect(dsn) as conn:
        for registration in registrations.values():
            register_principal(
                conn, tenant_id=tenant, client_id=registration.client_id, kid=registration.kid
            )
        register_user(conn, tenant_id=tenant, subject=subject, password=password)
        register_task_policy(
            conn,
            tenant_id=tenant,
            task_id=task,
            owner_subject=subject,
            scope="openid " + " ".join(TOOLS),
            constraints=CONSTRAINTS,
            amount_limit_fen=100000,
            call_limit=10,
            task_expires_at=datetime.now(timezone.utc) + timedelta(seconds=600),
        )
    # Preserve the mature original AS CLI configuration path and TLS-only startup.
    cli(["check", "--config", str(config_path)])
    cert = directory / "tls-cert.pem"
    cert_key = directory / "tls-key.pem"
    certificate = subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(cert_key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-nodes",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
        ],
        capture_output=True,
        timeout=60,
    )
    assert certificate.returncode == 0
    cert_key.chmod(0o600)
    cert.chmod(0o600)
    context = ssl.create_default_context(cafile=str(cert))
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    port = fresh_port()
    child = dict(os.environ, AGENT_GUARD_DATABASE_URL=dsn)
    args = [
        sys.executable,
        "-m",
        "agent_guard.server",
        "run",
        "--config",
        str(config_path),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--ssl-certfile",
        str(cert),
        "--ssl-keyfile",
        str(cert_key),
    ]
    process = subprocess.Popen(args, env=child, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    calls = []

    def request(method, path, body=None, headers=None, *, tls_context=None, host="localhost"):
        connection = http.client.HTTPSConnection(
            host, port, context=tls_context or context, timeout=5
        )
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            raw = response.read()
            calls.append(
                {
                    "method": method,
                    "path": path.split("?")[0],
                    "status": response.status,
                    "body_sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
            return response.status, {k.lower(): v for k, v in response.getheaders()}, raw
        finally:
            connection.close()

    def expected(method, path, code, body=None, headers=None):
        status, response_headers, raw = request(method, path, body, headers)
        assert status == code, "AS HTTPS step rejected; no credentials in assertion output"
        return response_headers, raw

    def cookie(headers, name):
        jar = SimpleCookie()
        jar.load(headers["set-cookie"])
        assert name in jar
        assert jar[name]["secure"] and jar[name]["httponly"]
        return jar[name].value

    def token_request(holder, form, purpose, token):
        client = "agent-" + holder
        registration = registrations[(tenant, client)]
        proof = sign_ag_proof(
            keys[holder],
            kid=registration.kid,
            client_id=client,
            purpose=purpose,
            endpoint=issuer + "/oauth/token",
            body=form,
            token=token,
            now=int(time.time()),
        )
        basic = "Basic " + base64.b64encode(
            (client + ":" + secret_bundle.client_secrets[client]).encode("ascii")
        ).decode("ascii")
        headers, raw = expected(
            "POST",
            "/oauth/token",
            200,
            urlencode(form),
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": basic,
                "AG-Proof": proof,
            },
        )
        assert headers["cache-control"] == "no-store" and headers["pragma"] == "no-cache"
        result = load_strict_json(raw)
        assert result["token_type"] == "AGPoP"
        return result

    tokens = []
    claims = []
    try:
        deadline = time.monotonic() + 15
        while True:
            assert process.poll() is None, "native AS exited before readiness"
            try:
                _, raw = expected("GET", "/.well-known/openid-configuration", 200)
                assert load_strict_json(raw)["issuer"] == issuer
                break
            except (ConnectionError, OSError):
                assert time.monotonic() < deadline, "finite AS readiness deadline"
                time.sleep(0.02)
        for host, ctx in [("localhost", ssl.create_default_context()), ("127.0.0.1", context)]:
            with pytest.raises(ssl.SSLCertVerificationError):
                request("GET", "/ag/keys", tls_context=ctx, host=host)
        headers, _ = expected("GET", "/ag/login", 200)
        login_csrf = cookie(headers, "ag_login_csrf")
        headers, _ = expected(
            "POST",
            "/ag/login",
            303,
            urlencode(
                {
                    "tenant_id": tenant,
                    "subject": subject,
                    "password": password,
                    "csrf_token": login_csrf,
                    "return_to": "/dashboard",
                }
            ),
            {
                "Cookie": "ag_login_csrf=" + login_csrf,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        session = cookie(headers, "ag_session")
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        redirect = config.clients["agent-planner"].redirect_uri
        authorize = {
            "response_type": "code",
            "client_id": "agent-planner",
            "redirect_uri": redirect,
            "scope": "openid " + " ".join(TOOLS),
            "state": state,
            "nonce": nonce,
            "code_challenge": pkce_s256_challenge(verifier),
            "code_challenge_method": "S256",
            "ag_task_id": task,
        }
        _, raw = expected(
            "GET",
            "/oauth/authorize?" + urlencode(authorize),
            200,
            headers={"Cookie": "ag_session=" + session},
        )
        match_id = re.search(rb'name="request_id" value="([^"]+)"', raw)
        match_csrf = re.search(rb'name="csrf_token" value="([^"]+)"', raw)
        assert match_id is not None and match_csrf is not None
        csrf = match_csrf.group(1).decode("ascii")
        assert csrf == session.split("~", 1)[1]
        headers, _ = expected(
            "POST",
            "/ag/consent",
            303,
            urlencode(
                {
                    "request_id": match_id.group(1).decode("ascii"),
                    "decision": "approve",
                    "csrf_token": csrf,
                }
            ),
            {
                "Cookie": "ag_session=" + session,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        location = urlsplit(headers["location"])
        registered = urlsplit(redirect)
        assert (location.scheme, location.netloc, location.path) == (
            registered.scheme,
            registered.netloc,
            registered.path,
        )
        query = parse_qs(location.query, strict_parsing=True)
        assert query["state"] == [state] and len(query["code"]) == 1 and "error" not in query
        root = token_request(
            "planner",
            {
                "grant_type": "authorization_code",
                "code": query["code"][0],
                "redirect_uri": redirect,
                "code_verifier": verifier,
            },
            "code-exchange",
            None,
        )
        id_claims = verify_id_token(
            root["id_token"],
            trusted_keys=as_keys,
            issuer=issuer,
            client_id="agent-planner",
            expected_nonce=nonce,
            now=int(time.time()),
        )
        assert id_claims["sub"] == subject
        assert root["ag_grant_id"] and type(root["ag_grant_id"]) is str
        tokens.append(root["access_token"])
        first_form = _form(as_key, tokens[0])
        first_form["scope"] = " ".join(TOOLS)
        mid = token_request("planner", first_form, "delegate", tokens[0])
        tokens.append(mid["access_token"])
        second_form = _form(as_key, tokens[1], recipient="executor", ttl=100)
        second_form["scope"] = " ".join(TOOLS)
        leaf = token_request("selector", second_form, "delegate", tokens[1])
        tokens.append(leaf["access_token"])
        claims = [
            verify_compact_jws(token, expected_type="ag-at+jwt", trusted_keys=as_keys)
            for token in tokens
        ]
        assert [c["client_id"] for c in claims] == [
            "agent-planner",
            "agent-selector",
            "agent-executor",
        ]
        assert claims[0]["ag_parent_id"] is None
        assert [c["ag_grant_id"] for c in claims] == [
            root["ag_grant_id"],
            mid["ag_grant_id"],
            leaf["ag_grant_id"],
        ]
        assert claims[1]["ag_parent_id"] == claims[0]["ag_grant_id"]
        assert claims[2]["ag_parent_id"] == claims[1]["ag_grant_id"]
        assert all(
            c["ag_root_id"] == claims[0]["ag_grant_id"]
            and c["iss"] == issuer
            and c["ag_tenant_id"] == tenant
            and c["ag_task_id"] == task
            for c in claims
        )
        assert claims[2]["ag_delegation_remaining"] == 0
        assert all(
            parent["iat"] <= descendant["iat"] < descendant["exp"] <= parent["exp"]
            for parent, descendant in zip(claims, claims[1:], strict=False)
        )
        basic = "Basic " + base64.b64encode(
            (config.gateway_client_id + ":" + secret_bundle.gateway_secret).encode("ascii")
        ).decode("ascii")
        for token in tokens:
            _, raw = expected(
                "POST",
                "/oauth/introspect",
                200,
                urlencode({"token": token, "token_type_hint": "access_token"}),
                {"Content-Type": "application/x-www-form-urlencoded", "Authorization": basic},
            )
            assert load_strict_json(raw)["active"] is True
        with psycopg.connect(dsn) as conn:
            rows = conn.execute(
                "SELECT grant_id,token_jws,token_sm3 FROM ag_grant_tokens ORDER BY grant_id"
            ).fetchall()
            assert len(rows) == 3
            stored = {row[0]: (row[1], row[2]) for row in rows}
            from agent_guard.crypto.sm import sm3_b64url

            assert stored == {
                c["ag_grant_id"]: (token, sm3_b64url(token.encode("ascii")))
                for c, token in zip(claims, tokens, strict=True)
            }
            assert conn.execute("SELECT count(*) FROM ag_delegations").fetchone() == (2,)
            assert conn.execute(
                "SELECT count(*) FROM ag_authorization_requests WHERE status=%s", ("approved",)
            ).fetchone() == (1,)
        record_native(
            "joint-as-issuance",
            {
                "pid": process.pid,
                "calls": calls,
                "cli": commands,
                "root_id": claims[0]["ag_grant_id"],
                "path_ids": [c["ag_grant_id"] for c in claims],
                "token_sha256": [hashlib.sha256(t.encode("ascii")).hexdigest() for t in tokens],
                "spki": {
                    kid: b64url_encode(serialize_sm2_public_key(key))
                    for kid, key in as_keys.items()
                },
                "pkce_method": "S256",
                "state_matched": True,
                "nonce_verified": True,
            },
        )
    finally:
        if process.poll() is None:
            process.terminate()
        out, err = process.communicate(timeout=15)
        record_native(
            "joint-as-stop",
            {
                "pid": process.pid,
                "exit": process.returncode,
                "stdout": out.decode("utf-8"),
                "stderr": err.decode("utf-8"),
            },
        )
        assert process.returncode in (0, -signal.SIGTERM)
        assert process.poll() is not None
    # Build existing mature GW services with exactly the HTTPS-returned leaf/key/trust.
    documents = {url: canonical_json_bytes(doc) for url, doc in config.did_documents.items()}
    resolver = IdentityResolver(
        registrations,
        allowed_hosts=config.identity_allowed_hosts,
        fetch_document=lambda url: documents[url],
    )
    evidence = EvidenceStore(dsn)
    registered = {(r.tenant_id, r.client_id, r.kid): r for r in registrations.values()}
    provider = PermissionSnapshotProvider(
        dsn, issuer=issuer, as_keys=as_keys, registrations=registered
    )
    invocation_verifier = InvocationVerifier(
        issuer=issuer,
        as_keys=as_keys,
        identities=resolver,
        permission_provider=provider,
        evidence_store=evidence,
    )
    downstream = MockDownstream(
        downstream_dsn,
        service_secret=DOWNSTREAM_SECRET,
        approved_suppliers={"supplier-001"},
        approved_recipients={"user-demo-001"},
        served_requests={"req-001"},
    )
    downstream.provision()
    downstream.reset()
    service = ExecutionService(
        gateway_dsn=dsn,
        ledger=ExecutionLedger(dsn),
        catalog=build_catalog(tenant, task),
        downstream=downstream,
        downstream_secret=DOWNSTREAM_SECRET,
    )
    env = SignedEnv(
        as_key,
        keys,
        registrations,
        tokens[2],
        invocation_verifier,
        evidence,
        service,
        VerifiedExecution(service, evidence_store=evidence),
        downstream,
    )
    material = {
        "tokens": tuple(tokens),
        "claims": tuple(claims),
        "as_keys": as_keys,
        "as_pid": process.pid,
        "as_exit": process.returncode,
        "native_as_stopped": process.poll() is not None,
        "calls": tuple(calls),
    }
    return env, material


@contextmanager
def joint_context(dsn, downstream_dsn, private, audit_tls):
    private.mkdir(mode=0o700)
    env, as_material = bind_original_https_as_issuance(dsn, downstream_dsn, private)
    assert as_material["native_as_stopped"]
    # No listener/worker/publisher is running: maintenance declaration is true here.
    value = bootstrap_cli(dsn, "bootstrap")
    assert bootstrap_cli(dsn, "describe-pending") == value
    value["scope"] = JournalScope(**value["scope"])
    descriptor = RegistrationDescriptor(**value)
    audit_ns = acquire_namespace(os.environ["AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL"])
    gateway = audit_process = runtime = None
    try:
        with psycopg.connect(audit_ns.dsn) as conn:
            owner = conn.execute("SELECT current_user").fetchone()[0]
            assert conn.execute("SELECT current_database()").fetchone()[0] == audit_ns.database
        connection = private_json(
            private / "audit-connection.json", {"dsn": audit_ns.dsn, "owner_role": owner}
        )
        assert run_operator(connection, "init").returncode == 0
        key = generate_sm2_private_key()
        trust = CheckpointTrust(
            "joint-audit-1", "AUDIT_SIGNER", serialize_sm2_public_key(key.public_key()), 1, None
        )
        assert (
            run_operator(
                connection,
                "register-key",
                {**asdict(trust), "spki_der": b64url_encode(trust.spki_der)},
            ).returncode
            == 0
        )
        assert run_operator(connection, "register-stream", asdict(descriptor)).returncode == 0
        writer, reader = secrets.token_urlsafe(36), secrets.token_urlsafe(36)
        for ident, token, role in [
            ("joint-writer", writer, "WRITER"),
            ("joint-reader", reader, "READER"),
        ]:
            assert (
                run_operator(
                    connection,
                    "register-principal",
                    {
                        "credential_id": ident,
                        "credential": token,
                        "role": role,
                        "stream_id": descriptor.scope.stream_id,
                    },
                ).returncode
                == 0
            )
        key_path = private / "audit-signing.key"
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        key_path.chmod(0o600)
        port = fresh_port()
        config = private_json(
            private / "audit-config.json",
            {
                "dsn": audit_ns.dsn,
                "owner_role": owner,
                "key_id": trust.kid,
                "private_key_path": str(key_path),
                "tls_certificate": str(audit_tls / "server.pem"),
                "tls_private_key": str(audit_tls / "server.key"),
                "host": "127.0.0.1",
                "port": port,
                "external_pins": [],
                "external_trust": [],
            },
        )
        audit_process = subprocess.Popen(
            [sys.executable, "-m", "agent_guard.audit", "--config", str(config)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 10
        while True:
            assert audit_process.poll() is None, "audit child exited; private output retained"
            try:
                status, answer = audit_request(
                    port,
                    audit_tls / "ca.pem",
                    "/v1/audit/latest",
                    {"stream_id": descriptor.scope.stream_id},
                    credential_id="joint-reader",
                    credential=reader,
                )
                assert status == 404 and answer == {"error": "NO_CHECKPOINT"}
                break
            except (ConnectionError, OSError):
                assert time.monotonic() < deadline, "audit readiness deadline"
                time.sleep(0.02)
        gw_dir = private / "gateway"
        gw_dir.mkdir(mode=0o700)
        certificates(gw_dir)
        from tests.fixtures.execution import DOWNSTREAM_SECRET
        from tests.fixtures.gateway import config_document

        gateway_config = config_document(env)
        receipt_key = generate_sm2_private_key()
        gateway_config["receipt_keys"] = {
            "joint-receipt-1": receipt_key.public_key()
            .public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
            .decode("ascii")
        }
        gateway_config["as_keys"] = {
            kid: key.public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode("ascii")
            for kid, key in as_material["as_keys"].items()
        }
        private_json(gw_dir / "config.json", gateway_config)
        private_json(
            gw_dir / "secrets.json",
            {"note": "synthetic test-only", "downstream_secret": DOWNSTREAM_SECRET},
        )
        gw_port = fresh_port()
        gateway, context = start_gateway(gw_dir, dsn, downstream_dsn, gw_port)
        runtime = JointRuntime(
            env,
            dsn,
            downstream_dsn,
            audit_ns,
            descriptor,
            trust,
            reader,
            writer,
            port,
            gw_port,
            context,
            audit_tls,
            private,
            connection,
            audit_process,
            as_material,
            receipt_key,
        )
        yield runtime
    finally:
        if runtime is not None:
            for child in runtime.native_children:
                if child.poll() is None:
                    child.kill()
                    child.wait(10)
                child.communicate()
        if gateway is not None:
            stop_gateway(gateway)
        if audit_process is not None:
            if audit_process.poll() is None:
                audit_process.terminate()
            audit_process.communicate(timeout=10)
            assert audit_process.returncode in (0, -signal.SIGTERM)
        assert_owned(audit_ns)
        release_namespace(audit_ns)


@pytest.fixture
def a31_joint(ledger, dsn, downstream_dsn, tmp_path, tmp_path_factory):
    # Existing self-generated service TLS has no resource-owner hard binding.
    from tests.integration.test_audit_tls import service_tls

    directory = service_tls.__wrapped__(tmp_path_factory)
    with joint_context(dsn, downstream_dsn, tmp_path / "joint-private", directory) as runtime:
        yield runtime
