"""Synthetic real HTTPS receipt closure; no model API or fixed private keys.

This development demonstration requires two explicit, disposable TEST databases.
The caller migrates the gateway database before running it. It seeds approved
synthetic policy/resources, generates fresh private keys, starts actual AS/GW
CLI processes and verifies one UNANCHORED receipt per canonical tool. It does
not provide A3 deployment, orchestration, export or independent audit anchoring.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import http.cookiejar
import json
import os
import re
import secrets
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import psycopg
from tongsuopy.crypto import serialization

from agent_guard.authorization.oidc import pkce_s256_challenge, verify_id_token
from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.authorization.provisioning import register_task_policy, register_user
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.contracts.ledger import INVOKE_ENDPOINT, QUERY_ENDPOINT
from agent_guard.contracts.ledger_changes import canonical_ledger_changes_bytes
from agent_guard.crypto.sm import (
    generate_sm2_private_key,
    serialize_sm2_public_key,
    verify_compact_jws,
)
from agent_guard.evidence.receipt import ReceiptTrust, verify_receipt_bundle
from agent_guard.execution.receipt_projection import project_receipt
from agent_guard.execution.receipt_publication import (
    InternalPublisher,
    ReceiptVerifier,
    evidence_bundle,
)
from agent_guard.execution.service import ExecutionService
from agent_guard.gateway.config import load_gateway_config, trusted_inputs
from agent_guard.identity.resolver import RegisteredIdentity, did_web_url
from agent_guard.ledger.provisioning import register_principal
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.server.__main__ import _did_document, _public_pem
from agent_guard.server.private_files import private_directory
from agent_guard.tools.downstream import MockDownstream

ISSUER = "https://auth.agent-guard.test"
AS_HOST = "auth.agent-guard.test"
GW_HOST = "gateway.agent-guard.test"
REDIRECT = "https://console.agent-guard.test/oauth/callback"
TENANT = "tenant-001"
TASK = "task-001"
SUBJECT = "user-001"
TOOLS = (
    "procurement.request.read",
    "procurement.document.read",
    "procurement.order.create",
    "notification.template.send",
)


class LocalTLS(http.client.HTTPSConnection):
    """Resolve fixed public hostname to owned loopback, retaining SNI/SAN checks."""

    def connect(self):
        raw = socket.create_connection(("127.0.0.1", self.port), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def fresh_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def full_state(gateway_dsn, downstream_dsn):
    """Full rows of every ag_* and ds_* persistent family, without logging raw."""
    result = {}
    for label, target, prefix in (
        ("gateway", gateway_dsn, "ag_"),
        ("downstream", downstream_dsn, "ds_"),
    ):
        with psycopg.connect(target, connect_timeout=5) as conn:
            conn.execute("SET LOCAL statement_timeout='15000ms'")
            names = conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname=current_schema() "
                "AND starts_with(tablename,%s) ORDER BY tablename",
                (prefix,),
            ).fetchall()
            result[label] = {
                name: conn.execute(
                    psycopg.sql.SQL(
                        "SELECT row_to_json(t)::text FROM {} t ORDER BY row_to_json(t)::text"
                    ).format(psycopg.sql.Identifier(name))
                ).fetchall()
                for (name,) in names
            }
    return result


def state_digest(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def _certificates(directory):
    def run(args):
        result = subprocess.run(["openssl", *args], capture_output=True, timeout=30, umask=0o077)
        if result.returncode:
            raise RuntimeError("synthetic TLS certificate generation failed")

    run(
        [
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
            "1",
            "-subj",
            "/CN=AgentGuardFreshSyntheticCA",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
        ]
    )
    for label, host in (("as", AS_HOST), ("gw", GW_HOST)):
        run(
            [
                "req",
                "-new",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(directory / f"{label}.key"),
                "-out",
                str(directory / f"{label}.csr"),
                "-subj",
                "/CN=" + host,
            ]
        )
        extension = directory / f"{label}.ext"
        extension.write_text(
            "subjectAltName=DNS:" + host + "\nbasicConstraints=CA:FALSE\n"
            "keyUsage=digitalSignature,keyEncipherment\n"
            "extendedKeyUsage=serverAuth\n"
        )
        extension.chmod(0o600)
        run(
            [
                "x509",
                "-req",
                "-in",
                str(directory / f"{label}.csr"),
                "-CA",
                str(directory / "ca.pem"),
                "-CAkey",
                str(directory / "ca.key"),
                "-CAcreateserial",
                "-out",
                str(directory / f"{label}.pem"),
                "-days",
                "1",
                "-extfile",
                str(extension),
            ]
        )
    for path in directory.iterdir():
        path.chmod(0o600)


class ReceiptScene:
    """One owned genuine AS→GW scene with independent persistent downstream."""

    def __init__(
        self, gateway_dsn, downstream_dsn, *, skus=None, leaf_ttl=120, middle_ttl=180, task_ttl=600
    ):
        if not gateway_dsn or not downstream_dsn or gateway_dsn == downstream_dsn:
            raise ValueError("two distinct explicit TEST database targets required")
        self.dsn, self.downstream_dsn = gateway_dsn, downstream_dsn
        self.skus = list(skus or ["sku-001"])
        self.leaf_ttl = leaf_ttl
        self.middle_ttl = middle_ttl
        self.task_ttl = task_ttl
        self.as_key = generate_sm2_private_key()
        self.gateway_key = generate_sm2_private_key()
        self.keys = {n: generate_sm2_private_key() for n in ("planner", "selector", "executor")}
        self.registrations = {}
        self.clients = {"agent-" + n: secrets.token_urlsafe(32) for n in self.keys}
        self.foreign_key = generate_sm2_private_key()
        self.clients["agent-outsider"] = secrets.token_urlsafe(32)
        self.password = secrets.token_urlsafe(24)
        self.downstream_secret = secrets.token_urlsafe(32)
        self.gateway_secret = secrets.token_urlsafe(32)
        self.processes, self.lifecycle, self.responses, self.sizes = [], [], [], []
        self.cookies = http.cookiejar.CookieJar()
        self.oracles = []
        self.tokens = []
        self.scope = " ".join(TOOLS)
        self.constraints = {
            "request_ids": ["req-001"],
            "document_ids": ["doc-001"],
            "quote_versions": ["quote-001@1"],
            "skus": self.skus,
            "max_quantity": 1,
            "delivery_ids": ["office-001"],
            "template_ids": ["order-created"],
            "recipient_ids": ["user-demo-001"],
        }

    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="a23-https-private-")
        self.directory = Path(self.temp.name)
        self.directory.chmod(0o700)
        try:
            _certificates(self.directory)
            self._configure()
            self._seed()
            self.context = ssl.create_default_context(cafile=str(self.directory / "ca.pem"))
            assert self.context.check_hostname and self.context.verify_mode == ssl.CERT_REQUIRED
            self.as_port = self._start("agent_guard.server", "as.json", "as")
            self.gw_port = self._start("agent_guard.gateway", "gw.json", "gw")
            self._login_and_delegate()
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def _configure(self):
        identities, documents, registry = {}, {}, []
        for name, key in [*self.keys.items(), ("outsider", self.foreign_key)]:
            tenant = "tenant-other" if name == "outsider" else TENANT
            client = "agent-" + name
            did = "did:web:identity.agent-guard.test:agents:" + name
            registration = RegisteredIdentity(
                tenant, client, did, did + "#key-1", serialize_sm2_public_key(key.public_key())
            )
            self.registrations[registration.kid] = registration
            identities[client] = {
                "tenant_id": tenant,
                "did": did,
                "kid": registration.kid,
                "spki_pem": _public_pem(key),
            }
            registry.append({**identities[client], "client_id": client, "current": True})
            documents[did_web_url(did)] = _did_document(
                did, registration.kid, registration.spki_der, delegating=name != "executor"
            )
        as_config = {
            "issuer": ISSUER,
            "as_signing_key_path": "as-sign.pem",
            "secrets_path": "as-secrets.json",
            "signing_kid": "as-sign-1",
            "clients": {
                client: {
                    "tenant_id": "tenant-other" if client == "agent-outsider" else TENANT,
                    "redirect_uri": REDIRECT,
                }
                for client in self.clients
            },
            "gateway_client_id": "gateway-introspect",
            "identities": identities,
            "identity_allowed_hosts": ["identity.agent-guard.test"],
            "did_documents": documents,
            "session_ttl_seconds": 1800,
            "csrf_ttl_seconds": 600,
            "request_ttl_seconds": 300,
            "request_timeout_seconds": 10,
        }
        self.gw_config = {
            "issuer": ISSUER,
            "as_keys": {"as-sign-1": _public_pem(self.as_key)},
            "identities": registry,
            "identity_allowed_hosts": ["identity.agent-guard.test"],
            "did_documents": documents,
            "receipt_keys": {"gw-receipt-1": _public_pem(self.gateway_key)},
            "catalog": {
                "requests": [
                    {
                        "request_id": "req-001",
                        "tenant_id": TENANT,
                        "task_id": TASK,
                        "status": "APPROVED",
                    }
                ],
                "documents": [
                    {
                        "document_id": "doc-001",
                        "request_id": "req-001",
                        "body": "synthetic document",
                    }
                ],
                "quotes": [
                    {
                        "quote_id": "quote-001",
                        "quote_version": "1",
                        "supplier_id": "supplier-001",
                        "request_id": "req-001",
                        "lines": [
                            {"sku": s, "quantity": 1, "unit_price_fen": 1} for s in self.skus
                        ],
                    }
                ],
                "deliveries": [
                    {"delivery_id": "office-001", "tenant_id": TENANT, "request_id": "req-001"}
                ],
                "templates": [{"template_id": "order-created", "body": "Synthetic order created"}],
                "recipients": [{"recipient_id": "user-demo-001"}],
            },
            "secrets_path": "gw-secrets.json",
            "request_timeout_seconds": 20,
            "max_workers": 8,
        }
        load_gateway_config(canonical_json_bytes(self.gw_config))
        with private_directory(self.directory) as directory:
            for name, value in (
                ("as.json", as_config),
                ("gw.json", self.gw_config),
                (
                    "as-secrets.json",
                    {
                        "note": "fresh synthetic test-only secrets",
                        "client_secrets": self.clients,
                        "gateway_secret": self.gateway_secret,
                    },
                ),
                (
                    "gw-secrets.json",
                    {
                        "note": "fresh synthetic test-only secret",
                        "downstream_secret": self.downstream_secret,
                    },
                ),
            ):
                directory.write_file(name, canonical_json_bytes(value))
            directory.write_file(
                "as-sign.pem",
                self.as_key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                ),
            )
        as_keys, _, registrations, catalog = trusted_inputs(self.gw_config)
        provider = PermissionSnapshotProvider(
            self.dsn, issuer=ISSUER, as_keys=as_keys, registrations=registrations
        )
        self.receipt_verifier = ReceiptVerifier(
            issuer=ISSUER,
            as_keys=as_keys,
            gateway_keys={"gw-receipt-1": self.gateway_key.public_key()},
            registrations=registrations,
            permission_provider=provider,
        )
        self.publisher = InternalPublisher(
            self.dsn,
            private_key=self.gateway_key,
            signing_kid="gw-receipt-1",
            verifier=self.receipt_verifier,
        )
        self.downstream = MockDownstream(
            self.downstream_dsn,
            service_secret=self.downstream_secret,
            approved_suppliers={"supplier-001"},
            approved_recipients={"user-demo-001"},
            served_requests={"req-001"},
        )
        self.service = ExecutionService(
            gateway_dsn=self.dsn,
            ledger=ExecutionLedger(self.dsn),
            catalog=catalog,
            downstream=self.downstream,
            downstream_secret=self.downstream_secret,
        )

    def _seed(self):
        with psycopg.connect(self.dsn, connect_timeout=5) as conn:
            for r in self.registrations.values():
                register_principal(conn, tenant_id=r.tenant_id, client_id=r.client_id, kid=r.kid)
            register_user(conn, tenant_id=TENANT, subject=SUBJECT, password=self.password)
            register_task_policy(
                conn,
                tenant_id=TENANT,
                task_id=TASK,
                owner_subject=SUBJECT,
                scope="openid " + self.scope,
                constraints=self.constraints,
                amount_limit_fen=100000,
                call_limit=10,
                task_expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.task_ttl),
            )
            register_user(
                conn, tenant_id="tenant-other", subject="user-other", password=self.password
            )
            register_task_policy(
                conn,
                tenant_id="tenant-other",
                task_id="task-other",
                owner_subject="user-other",
                scope="openid " + self.scope,
                constraints=self.constraints,
                amount_limit_fen=100000,
                call_limit=10,
                task_expires_at=datetime.now(timezone.utc) + timedelta(seconds=600),
            )
        self.downstream.provision()
        self.downstream.reset()

    def _start(self, module, config, label):
        port = fresh_port()
        env = {
            k: v for k, v in os.environ.items() if not ("DATABASE_URL" in k or k.endswith("DSN"))
        }
        if label == "as":
            env["AGENT_GUARD_DATABASE_URL"] = self.dsn
        else:
            env.update(
                AG_GATEWAY_DATABASE_URL=self.dsn,
                AG_GATEWAY_DOWNSTREAM_DATABASE_URL=self.downstream_dsn,
            )
        # Actual child import identity is emitted before the real CLI executes.
        wrapper = (
            "import importlib,hashlib,json,os,runpy; "
            f"m=importlib.import_module('{module}.factory'); "
            "print('A23_CHILD '+json.dumps({'pid':os.getpid(),'module':m.__file__,"
            "'sha256':hashlib.sha256(open(m.__file__,'rb').read()).hexdigest()}),flush=True); "
            f"runpy.run_module('{module}',run_name='__main__')"
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                wrapper,
                "run",
                "--config",
                str(self.directory / config),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--ssl-certfile",
                str(self.directory / f"{label}.pem"),
                "--ssl-keyfile",
                str(self.directory / f"{label}.key"),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.processes.append(process)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("owned TLS child startup failed")
            try:
                status, _, _ = self.request(label, "GET", "/not-public", port=port)
                if status == 404:
                    self.lifecycle.append(
                        {
                            "kind": "started",
                            "label": label,
                            "pid": process.pid,
                            "port": port,
                            "host": AS_HOST if label == "as" else GW_HOST,
                        }
                    )
                    return port
            except OSError:
                time.sleep(0.02)
        raise RuntimeError("owned TLS readiness timeout")

    def request(
        self, label, method, path, *, body=None, headers=None, port=None, context=None, host=None
    ):
        actual_host = host or (AS_HOST if label == "as" else GW_HOST)
        target = port or (self.as_port if label == "as" else self.gw_port)
        connection = LocalTLS(actual_host, target, context=context or self.context, timeout=5)
        url = "https://" + actual_host + path
        cookie_request = urllib.request.Request(url)
        if label == "as":
            self.cookies.add_cookie_header(cookie_request)
        outgoing = dict(cookie_request.header_items()) | dict(headers or {})
        try:
            connection.request(method, path, body=body, headers=outgoing)
            response = connection.getresponse()
            data = response.read()
            fields = {k.lower(): v for k, v in response.getheaders()}
            if label == "as":
                self.cookies.extract_cookies(response, cookie_request)
            self.responses.append(data)
            return response.status, fields, data
        finally:
            connection.close()

    def form(self, path, values, *, holder=None, purpose=None, token=None):
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if holder:
            client = "agent-" + holder
            headers["Authorization"] = (
                "Basic " + base64.b64encode((client + ":" + self.clients[client]).encode()).decode()
            )
            headers["AG-Proof"] = sign_ag_proof(
                self.foreign_key if holder == "outsider" else self.keys[holder],
                kid=self.kid(holder),
                client_id=client,
                purpose=purpose,
                endpoint=ISSUER + path,
                body=values,
                token=token,
                now=int(time.time()),
            )
        return self.request("as", "POST", path, body=urlencode(values), headers=headers)

    def kid(self, holder):
        return next(r.kid for r in self.registrations.values() if r.client_id == "agent-" + holder)

    def _login_and_delegate(
        self, *, holder="planner", tenant=TENANT, task=TASK, subject=SUBJECT, delegate=True
    ):
        self.cookies.clear()
        status, _, _ = self.request("as", "GET", "/ag/login")
        assert status == 200
        csrf_cookie = next(c for c in self.cookies if c.name == "ag_login_csrf")
        assert csrf_cookie.secure and csrf_cookie.has_nonstandard_attr("HttpOnly")
        assert csrf_cookie.get_nonstandard_attr("SameSite").lower() == "lax"
        status, _, _ = self.form(
            "/ag/login",
            {
                "tenant_id": tenant,
                "subject": subject,
                "password": self.password,
                "csrf_token": csrf_cookie.value,
                "return_to": "/dashboard",
            },
        )
        assert status == 303
        session = next(c for c in self.cookies if c.name == "ag_session")
        assert session.secure and session.has_nonstandard_attr("HttpOnly")
        assert session.get_nonstandard_attr("SameSite").lower() == "lax"
        state, nonce, verifier = (
            secrets.token_urlsafe(24),
            secrets.token_urlsafe(24),
            secrets.token_urlsafe(48),
        )
        params = {
            "response_type": "code",
            "client_id": "agent-" + holder,
            "redirect_uri": REDIRECT,
            "scope": "openid " + self.scope,
            "state": state,
            "nonce": nonce,
            "code_challenge": pkce_s256_challenge(verifier),
            "code_challenge_method": "S256",
            "ag_task_id": task,
        }
        status, _, body = self.request("as", "GET", "/oauth/authorize?" + urlencode(params))
        assert status == 200
        request_id = re.search(rb'name="request_id" value="([^"]+)"', body)
        csrf = re.search(rb'name="csrf_token" value="([^"]+)"', body)
        assert request_id is not None and csrf is not None
        assert csrf.group(1).decode() == session.value.split("~", 1)[1]
        status, headers, _ = self.form(
            "/ag/consent",
            {
                "request_id": request_id.group(1).decode(),
                "decision": "approve",
                "csrf_token": csrf.group(1).decode(),
            },
        )
        assert status == 303
        location = urlsplit(headers["location"])
        assert location.scheme + "://" + location.netloc + location.path == REDIRECT
        query = parse_qs(location.query)
        assert query["state"] == [state] and set(query) == {"code", "state"}
        form = {
            "grant_type": "authorization_code",
            "code": query["code"][0],
            "redirect_uri": REDIRECT,
            "code_verifier": verifier,
        }
        status, _, raw = self.form("/oauth/token", form, holder=holder, purpose="code-exchange")
        assert status == 200
        root = load_strict_json(raw)
        identity = verify_id_token(
            root["id_token"],
            trusted_keys={"as-sign-1": self.as_key.public_key()},
            issuer=ISSUER,
            client_id="agent-" + holder,
            expected_nonce=nonce,
            now=int(time.time()),
        )
        assert identity["sub"] == subject
        if not delegate:
            return root["access_token"]
        self.tokens.append(root["access_token"])
        for holder, recipient, amount, calls, requested_ttl in (
            ("planner", "selector", 80000, 8, self.middle_ttl),
            ("selector", "executor", 70000, 7, self.leaf_ttl),
        ):
            token = self.tokens[-1]
            parent = self.claims(token)
            ttl = min(requested_ttl, parent["exp"] - int(time.time()) - 2)
            assert ttl > 0, "real AS issuance margin exhausted"
            values = {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "audience": "https://gateway.agent-guard.test",
                "scope": self.scope,
                "ag_delegate_client_id": "agent-" + recipient,
                "ag_amount_limit_fen": str(amount),
                "ag_call_limit": str(calls),
                "ag_ttl_seconds": str(ttl),
                "ag_delegation_remaining": str(parent["ag_delegation_remaining"] - 1),
                "ag_constraints": canonical_json_bytes(self.constraints).decode(),
                "ag_delegation_key": secrets.token_urlsafe(24),
            }
            status, _, raw = self.form(
                "/oauth/token", values, holder=holder, purpose="delegate", token=token
            )
            assert status == 200
            child = load_strict_json(raw)
            assert child["token_type"] == "AGPoP"
            self.tokens.append(child["access_token"])
            claims = self.claims(self.tokens[-1])
            assert parent["iat"] <= claims["iat"] < claims["exp"] <= parent["exp"]
            self.lifecycle.append(
                {
                    "kind": "exchange",
                    "holder": holder,
                    "recipient": recipient,
                    "parent_iat": parent["iat"],
                    "parent_exp": parent["exp"],
                    "child_iat": claims["iat"],
                    "child_exp": claims["exp"],
                    "requested_ttl": requested_ttl,
                    "actual_ttl": ttl,
                }
            )
        self.token = self.tokens[-1]
        assert len({self.kid(n) for n in self.keys}) == 3
        assert len({self.claims(t)["ag_grant_id"] for t in self.tokens}) == 3

    def foreign_token(self):
        return self._login_and_delegate(
            holder="outsider",
            tenant="tenant-other",
            task="task-other",
            subject="user-other",
            delegate=False,
        )

    def claims(self, token):
        return verify_compact_jws(
            token, expected_type="ag-at+jwt", trusted_keys={"as-sign-1": self.as_key.public_key()}
        )

    def body(self, tool, *, prior_operation=None, key=None):
        params = {
            TOOLS[0]: {"request_id": "req-001"},
            TOOLS[1]: {"request_id": "req-001", "document_id": "doc-001"},
            TOOLS[2]: {
                "request_id": "req-001",
                "quote_id": "quote-001",
                "quote_version": "1",
                "items": [{"sku": s, "quantity": 1} for s in self.skus],
                "delivery_id": "office-001",
            },
            TOOLS[3]: {
                "template_id": "order-created",
                "recipient_id": "user-demo-001",
                "operation_id": prior_operation,
            },
        }[tool]
        return {
            "profile": "GM-MVP-1",
            "task_id": TASK,
            "tool_id": tool,
            "tool_version": "1",
            "idempotency_key": key or secrets.token_urlsafe(24),
            "params": params,
        }

    def proof(
        self,
        body,
        *,
        query=False,
        holder="executor",
        token=None,
        signing_key=None,
        endpoint=None,
        kid=None,
        client=None,
        lifetime=60,
    ):
        return sign_ag_proof(
            signing_key or self.keys[holder],
            kid=kid or self.kid(holder),
            client_id=client or "agent-" + holder,
            purpose="result-read" if query else "invoke",
            endpoint=endpoint or (QUERY_ENDPOINT if query else INVOKE_ENDPOINT),
            body=body,
            token=token or self.token,
            now=int(time.time()),
            lifetime_seconds=lifetime,
        )

    def gateway(self, body, *, query=False, proof=None, token=None, path=None):
        return self.request(
            "gw",
            "POST",
            path or ("/v1/operations/query" if query else "/v1/invocations"),
            body=canonical_json_bytes(body),
            headers={
                "Content-Type": "application/json",
                "Authorization": "AGPoP " + (token or self.token),
                "AG-Proof": proof or self.proof(body, query=query, token=token),
            },
        )

    def counters(self):
        with psycopg.connect(self.dsn) as conn:
            return conn.execute(
                "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled "
                "FROM ag_grants WHERE tenant_id=%s AND task_id=%s ORDER BY depth",
                (TENANT, TASK),
            ).fetchall()

    def close_operation(self, body):
        initial = self.counters()
        amount = len(self.skus) if body["tool_id"] == TOOLS[2] else 0
        status, _, raw = self.gateway(body)
        assert status == 202
        accepted = load_strict_json(raw)
        assert accepted["status"] == "RESERVED" and accepted["receipt_status"] == "PENDING"
        operation_id = accepted["operation_id"]
        assert self.counters() == [(ar + amount, aset, cr + 1, cs) for ar, aset, cr, cs in initial]
        assert self.service.run_operation(operation_id).status == "SUCCEEDED"
        assert self.counters() == [(ar, aset + amount, cr, cs + 1) for ar, aset, cr, cs in initial]
        before = full_state(self.dsn, self.downstream_dsn)
        publication = self.publisher.publish(operation_id)
        assert publication.receipt_status == "READY"
        after = full_state(self.dsn, self.downstream_dsn)
        assert_publication_only(before, after)
        assert self.publisher.publish(operation_id) == publication
        if full_state(self.dsn, self.downstream_dsn) != after:
            raise AssertionError("repeat publisher changed persisted facts")
        query = {"profile": "GM-MVP-1", "task_id": TASK, "operation_id": operation_id}
        query_before = full_state(self.dsn, self.downstream_dsn)
        query_proof = self.proof(query, query=True)
        status, _, raw = self.gateway(query, query=True, proof=query_proof)
        assert status == 200 and len(raw) <= 65536
        public = load_strict_json(raw)
        assert (
            public["receipt_status"] == "READY" and public["receipt_jws"] == publication.receipt_jws
        )
        assert public["status"] == "SUCCEEDED"
        query_after = full_state(self.dsn, self.downstream_dsn)
        assert_query_only(query_before, query_after, operation_id)
        self.oracles.append(
            {
                "operation_id": operation_id,
                "publish_before": state_digest(before),
                "publish_after": state_digest(after),
                "query_before": state_digest(query_before),
                "query_after": state_digest(query_after),
                "query_only_families": ["ag_proofs", "ag_verified_evidence"],
            }
        )
        with psycopg.connect(self.dsn) as conn:
            projection = project_receipt(conn, operation_id)
        bundle = evidence_bundle(projection, publication.receipt_jws)
        # Trust is created from independently provisioned parent-side public inputs,
        # not from the bundle, server helper or current DID state.
        trust = ReceiptTrust(
            issuer=ISSUER,
            as_keys={"as-sign-1": self.as_key.public_key()},
            gateway_keys={"gw-receipt-1": self.gateway_key.public_key()},
            holder_keys={self.kid(n): key.public_key() for n, key in self.keys.items()},
            historical_registrations=dict(self.registrations),
        )
        verified = verify_receipt_bundle(bundle, trust=trust)
        assert verified.operation_id == operation_id and verified.anchoring_status == "UNANCHORED"
        assert verified.amount_fen == (len(self.skus) if body["tool_id"] == TOOLS[2] else 0)
        claims = verify_compact_jws(
            publication.receipt_jws,
            expected_type="ag-receipt+jwt",
            trusted_keys={"gw-receipt-1": self.gateway_key.public_key()},
        )
        assert len(claims) == 17 and claims == load_strict_json(projection.claims_bytes)
        self.sizes.append(
            {
                "tool": body["tool_id"],
                "request": len(projection.request_bytes),
                "quote": self._quote_size(operation_id),
                "result": len(projection.result_bytes),
                "ledger": len(projection.ledger_bytes),
                "receipt": len(publication.receipt_jws),
                "public": len(raw),
                "tokens": [len(t) for t in self.tokens],
                "proof": len(projection.proof_bytes),
                "permission_source": len(
                    self.receipt_verifier.permission_provider.load(
                        self.token,
                        grant_id=self.claims(self.token)["ag_grant_id"],
                        now=int(time.time()),
                    ).material()
                ),
                "bundle_outer": 2
                + sum(
                    len(canonical_json_bytes(k))
                    + 1
                    + len(
                        canonical_ledger_changes_bytes(v)
                        if k == "ledger_changes"
                        else canonical_json_bytes(v)
                    )
                    for k, v in bundle.items()
                )
                + len(bundle)
                - 1,
            }
        )
        return operation_id, bundle, public

    def _quote_size(self, operation_id):
        with psycopg.connect(self.dsn) as conn:
            row = conn.execute(
                "SELECT quote_snapshot FROM ag_operations WHERE operation_id=%s", (operation_id,)
            ).fetchone()
        return len(bytes(row[0])) if row[0] is not None else 0

    def closure(self):
        results = []
        prior = None
        for tool in TOOLS:
            item = self.close_operation(self.body(tool, prior_operation=prior))
            results.append(item)
            if tool == TOOLS[2]:
                prior = item[0]
        with psycopg.connect(self.dsn) as conn:
            rows = conn.execute(
                "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled "
                "FROM ag_grants ORDER BY depth"
            ).fetchall()
            assert rows == [(0, len(self.skus), 0, 4)] * 3
            assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (4,)
            assert conn.execute(
                "SELECT phase,count(*) FROM ag_ledger_events GROUP BY phase ORDER BY phase"
            ).fetchall() == [("RESERVE", 4), ("SETTLE", 4)]
            assert conn.execute("SELECT count(*) FROM ag_ledger_event_nodes").fetchone() == (24,)
            assert conn.execute(
                "SELECT count(*) FROM ag_receipt_outbox WHERE receipt_status='READY'"
            ).fetchone() == (4,)
        with psycopg.connect(self.downstream_dsn) as conn:
            assert conn.execute("SELECT count(*) FROM ds_orders").fetchone() == (1,)
            assert conn.execute("SELECT count(*) FROM ds_notifications").fetchone() == (1,)
            assert conn.execute("SELECT count(*) FROM ds_operations").fetchone() == (4,)
        return results

    def __exit__(self, *_):
        errors = []
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
                errors.append("owned TLS child required forced kill")
            self.lifecycle.append(
                {
                    "kind": "stopped",
                    "pid": process.pid,
                    "exit": process.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                }
            )
            if process.returncode not in (0, -signal.SIGTERM):
                errors.append("owned TLS child abnormal exit")
        self.temp.cleanup()
        if errors and not _[0]:
            raise RuntimeError("; ".join(errors))


def assert_publication_only(before, after):
    old, new = json.loads(json.dumps(before)), json.loads(json.dumps(after))
    for state in (old, new):
        rows = state["gateway"]["ag_receipt_outbox"]
        cleaned = []
        for (raw,) in rows:
            row = json.loads(raw)
            for name in ("receipt_status", "receipt_jws", "signed_at"):
                row.pop(name)
            cleaned.append(row)
        state["gateway"]["ag_receipt_outbox"] = cleaned
    if old != new:
        raise AssertionError("publication changed non-publication persisted facts")


def assert_query_only(before, after, operation_id):
    old, new = json.loads(json.dumps(before)), json.loads(json.dumps(after))
    added = {}
    for table in ("ag_proofs", "ag_verified_evidence"):
        prior = old["gateway"].pop(table)
        current = new["gateway"].pop(table)
        if any(row not in current for row in prior):
            raise AssertionError("query modified original proof/evidence rows")
        rows = [json.loads(row[0]) for row in current if row not in prior]
        if len(rows) != 1 or rows[0]["purpose"] != "result-read":
            raise AssertionError("query did not add exactly one fresh result-read proof/material")
        added[table] = rows[0]
    proof, material = added["ag_proofs"], added["ag_verified_evidence"]
    if (
        proof["operation_id"] != operation_id
        or proof["proof_jti"] != material["proof_jti"]
        or proof["evidence_ref"] != material["evidence_ref"]
    ):
        raise AssertionError("query new proof/material/operation binding mismatch")
    if old != new:
        raise AssertionError("query changed persisted business/effect families")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    dsn = os.environ.get("AGENT_GUARD_TEST_DATABASE_URL")
    downstream_dsn = os.environ.get("AGENT_GUARD_TEST_DOWNSTREAM_DATABASE_URL")
    if not dsn or not downstream_dsn:
        parser.error("two explicit disposable TEST database variables are required")
    try:
        with ReceiptScene(dsn, downstream_dsn) as scene:
            scene.closure()
            report = {
                "status": "SYNTHETIC_HTTPS_RECEIPTS_VERIFIED",
                "anchoring_status": "UNANCHORED",
                "tools": list(TOOLS),
                "sizes": scene.sizes,
            }
        report["processes"] = scene.lifecycle
        print(json.dumps(report, sort_keys=True))
        return 0
    except (OSError, ValueError, AssertionError, psycopg.Error, RuntimeError):
        print("error: synthetic receipt demonstration failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
