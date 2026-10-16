"""A34 fair baselines on real PostgreSQL 16, TLS, and real process material.

These tests drive the frozen research-only baselines (static ACL, genuine
signed no-atomic budget, genuine signed SM2 Bearer) and the production path as
the full control. They never mint an AS grant by SQL: every task root and every
delegation is a real SM2-signed token issued by the native AS HTTPS listener
with a real browser login/consent and two HTTPS token exchanges.

Isolation: the module creates its own random test database on the session's
PostgreSQL instance (scratch ``ag_test_migrate_*`` name created and dropped by
the run-exclusive helper), applies the accepted bundle migrations there, and
uses a research-only ``r34`` schema inside that throwaway database. The
per-session schema database is not used for research state.

Honest boundaries:
- the no-atomic race runs the frozen research path; the production path on the
  same intents is the control that must stay at at most one acceptance;
- static ACL has exactly one approved policy per ``(role, task)`` and its
  receipt/audit/replay capability is NOT_APPLICABLE;
- Bearer has ``proof=None``/``holder_possession=NOT_VERIFIED`` and any supplied
  proof is IGNORED; proof replay is NOT_APPLICABLE for it;
- receipt signing, independent anchoring and the official 40000-attempt
  measurement are NOT in this file.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import http.client
import json
import os
import re
import secrets
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from threading import Barrier
from urllib.parse import urlencode

import psycopg
import pytest
from psycopg.rows import dict_row
from tongsuopy.crypto import serialization

from agent_guard.authorization.evidence_store import EvidenceStore
from agent_guard.authorization.oidc import pkce_s256_challenge
from agent_guard.authorization.passwords import hash_password, verify_password
from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.authorization.provisioning import register_task_policy, register_user
from agent_guard.authorization.verifier import InvocationVerifier, VerificationError
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.contracts.execution import (
    ExecutionError,
    GrantConstraints,
    ToolId,
    TrustedPermissionSnapshot,
)
from agent_guard.contracts.ledger import INVOKE_ENDPOINT, QUERY_ENDPOINT, LedgerError
from agent_guard.crypto.sm import (
    generate_sm2_private_key,
    serialize_sm2_public_key,
    verify_compact_jws,
)
from agent_guard.execution.service import ExecutionService
from agent_guard.execution.verified import VerifiedExecution
from agent_guard.identity.resolver import RegisteredIdentity
from agent_guard.ledger.lineage import apply_bundle_migrations
from agent_guard.ledger.provisioning import (
    deactivate_principal,
    register_principal,
    revoke_grant,
)
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.server.config import load_secrets, load_server_config, resolve_paths
from agent_guard.server.private_files import read_private_file
from agent_guard.tools.catalog import (
    CatalogDelivery,
    CatalogDocument,
    CatalogQuote,
    CatalogQuoteLine,
    CatalogRecipient,
    CatalogRequest,
    CatalogTemplate,
    TrustedCatalog,
)
from agent_guard.tools.downstream import MockDownstream
from experiments.agent_guard_bench.oracle import (
    OraclePolicy,
    downstream_oracle,
    snapshot_oracle,
)
from experiments.agent_guard_bench.research_contracts import (
    ACLRegistration,
    BearerContext,
    ResearchAuthenticator,
    ResearchError,
)
from experiments.agent_guard_bench.research_evidence import ResearchEvidence
from experiments.agent_guard_bench.research_service import (
    ResearchService,
    create_research_tls_server,
)
from experiments.agent_guard_bench.research_store import Lease, ResearchStore
from experiments.agent_guard_bench.research_worker import ResearchWorker
from experiments.agent_guard_bench.signed_no_atomic import SignedNoAtomic
from experiments.agent_guard_bench.sm2_bearer import SM2Bearer
from experiments.agent_guard_bench.static_acl import StaticACL
from experiments.agent_guard_bench.workload import (
    CLASSES,
    MODES,
    SEEDS,
    generate_suite,
)
from experiments.agent_guard_bench.workload import (
    TOOLS as WORKLOAD_TOOLS,
)
from tests.fixtures.execution import DOWNSTREAM_SECRET
from tests.fixtures.isolation import (
    create_downstream_database,
    create_scratch_database,
    drop_downstream_database,
    drop_scratch_database,
)
from tests.integration.test_exchange_service import TENANT, _resolver
from tests.integration.test_gateway_tls import certificates, fresh_port

pytestmark = pytest.mark.integration

ISSUER = "https://auth.agent-guard.test"
GATEWAY_AUDIENCE = "https://gateway.agent-guard.test"
SUBJECT = "user-baseline-001"
TOOLS = tuple(tool.value for tool in ToolId)
ROOT_AMOUNT, MID_AMOUNT, LEAF_AMOUNT = 100000, 80000, 70000
ROOT_CALLS, MID_CALLS, LEAF_CALLS = 12, 10, 8
ORDER_AMOUNT = 70000
EVIDENCE_ENV = "AG34B_NATIVE_EVIDENCE"

TOOL_READ, TOOL_ORDER = TOOLS[0], TOOLS[2]

BASELINE_TASKS = (
    "b34-fair-acl",
    "b34-fair-no",
    "b34-fair-bearer",
    *("b34-race-" + str(index) for index in range(10)),
    "b34-bearer",
    "b34-bearer-neg",
    "b34-bearer-lock",
    "b34-bearer-atomic",
    # Ten applicable rounds of real fault/permission controls, each with its
    # own isolated task/root/branch/credential lifecycle. The round-suffixed
    # task IDs replace the earlier single fixed set so no round reuses another
    # round's revoked, disabled or leased state.
    *(
        "b34-" + stem + "-r" + str(index)
        for stem in ("noint", "nostate", "nokey", "nottl", "nocrash")
        for index in range(10)
    ),
)


def canonical(body: dict) -> bytes:
    return canonical_json_bytes(body)


def record_native(name: str, value) -> None:
    """Public-ID evidence only; raw payload stays in the owned evidence dir."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    directory = os.environ.get(EVIDENCE_ENV)
    if directory:
        target = Path(directory)
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = target / (name + ".json")
        path.write_bytes(raw)
        path.chmod(0o600)
    print(
        json.dumps({"native_record": name, "sha256": hashlib.sha256(raw).hexdigest()}),
        flush=True,
    )


def private_json(path: Path, value) -> Path:
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))
    path.chmod(0o600)
    return path


def rejection_code(exc: BaseException):
    code = getattr(exc, "code", None)
    return getattr(code, "value", code)


def expect_rejected(call, *codes):
    with pytest.raises(Exception) as caught:
        call()
    value = rejection_code(caught.value)
    assert value in codes, (type(caught.value).__name__, value, codes)
    return value


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    constraints: dict
    resources: dict

    def grant_constraints(self) -> GrantConstraints:
        return GrantConstraints(
            request_ids=tuple(self.constraints["request_ids"]),
            document_ids=tuple(self.constraints["document_ids"]),
            quote_versions=tuple(self.constraints["quote_versions"]),
            skus=tuple(self.constraints["skus"]),
            delivery_ids=tuple(self.constraints["delivery_ids"]),
            template_ids=tuple(self.constraints["template_ids"]),
            recipient_ids=tuple(self.constraints["recipient_ids"]),
            max_quantity=int(self.constraints["max_quantity"]),
        )


@dataclass(frozen=True)
class Branch:
    root_id: str
    mid_id: str
    leaf_id: str
    mid_token: str
    leaf_token: str


@dataclass(frozen=True)
class Issued:
    access_token: str
    id_token: str
    claims: dict


class LocalTLS(http.client.HTTPSConnection):
    """Loopback connection with the fixed configured SAN as the TLS name."""

    def connect(self):
        raw = socket.create_connection(("127.0.0.1", self.port), timeout=self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class NativeAS:
    """Real browser authorization-code root plus HTTPS token exchanges.

    The fixed issuer identity is ``ISSUER``; the listener is TLS-only on
    loopback with a test CA. No token is minted by the test: every bearer
    string returned here came from the native AS process and is a genuine
    SM2-signed JWS.
    """

    def __init__(self, dsn: str, directory: Path):
        self.dsn = dsn
        self.directory = Path(directory)
        self.password = secrets.token_urlsafe(36)
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_guard.server",
                "init",
                "--out",
                str(self.directory),
                "--issuer",
                ISSUER,
            ],
            capture_output=True,
            timeout=120,
        )
        assert completed.returncode == 0, "native AS init failed; private output retained"
        config_path = self.directory / "config.json"
        value = json.loads(read_private_file(config_path))
        assert value["issuer"] == ISSUER and value["signing_kid"] == "as-sign-1"
        assert set(value["clients"]) == {"agent-planner", "agent-selector", "agent-executor"}
        for registration in list(value["clients"].values()) + list(value["identities"].values()):
            registration["tenant_id"] = TENANT
        private_json(config_path, value)
        self.config = resolve_paths(
            load_server_config(read_private_file(config_path)), self.directory
        )
        self.secret_bundle = load_secrets(read_private_file(self.config.secrets_path))

        def load_key(name):
            return serialization.load_pem_private_key(
                read_private_file(self.directory / name), password=None
            )

        self.keys = {
            holder: load_key("agent-" + holder + ".pem")
            for holder in ("planner", "selector", "executor")
        }
        self.as_key = load_key("as-sign-key.pem")
        self.as_keys = {"as-sign-1": self.as_key.public_key()}
        for kid, pem in self.config.historical_verification_keys.items():
            self.as_keys[kid] = serialization.load_pem_public_key(pem.encode("ascii"))
        self.registrations = {}
        for client_id, identity in self.config.identities.items():
            holder = client_id.removeprefix("agent-")
            public = serialization.load_pem_public_key(identity.spki_pem.encode("ascii"))
            assert serialize_sm2_public_key(self.keys[holder].public_key()) == (
                serialize_sm2_public_key(public)
            )
            self.registrations[(TENANT, client_id)] = RegisteredIdentity(
                TENANT,
                client_id,
                identity.did,
                identity.kid,
                serialize_sm2_public_key(public),
            )
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            for registration in self.registrations.values():
                register_principal(
                    conn,
                    tenant_id=TENANT,
                    client_id=registration.client_id,
                    kid=registration.kid,
                )
            register_user(conn, tenant_id=TENANT, subject=SUBJECT, password=self.password)
        self.resolver = _resolver(self.registrations)

        self.tls = self.directory / "tls"
        self.tls.mkdir(mode=0o700)
        certificates(self.tls)
        self.context = ssl.create_default_context(cafile=str(self.tls / "ca.pem"))
        assert self.context.check_hostname and self.context.verify_mode == ssl.CERT_REQUIRED
        self.port = fresh_port()
        child = dict(os.environ, AGENT_GUARD_DATABASE_URL=dsn)
        child.pop("PYTHONPATH", None)
        self.stdout_log = (self.directory / "as.stdout").open("wb")
        self.stderr_log = (self.directory / "as.stderr").open("wb")
        os.chmod(self.directory / "as.stdout", 0o600)
        os.chmod(self.directory / "as.stderr", 0o600)
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "agent_guard.server",
                "run",
                "--config",
                str(config_path),
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--ssl-certfile",
                str(self.tls / "tls.pem"),
                "--ssl-keyfile",
                str(self.tls / "tls.key"),
            ],
            env=child,
            stdout=self.stdout_log,
            stderr=self.stderr_log,
        )
        deadline = time.monotonic() + 20
        while True:
            assert self.process.poll() is None, "native AS exited before readiness"
            try:
                status, _, raw = self._request("GET", "/.well-known/openid-configuration")
                if status == 200 and load_strict_json(raw)["issuer"] == ISSUER:
                    break
            except (ConnectionError, OSError):
                pass
            assert time.monotonic() < deadline, "finite AS readiness deadline"
            time.sleep(0.02)
        self.session = self._login()
        record_native(
            "native-as-ready",
            {
                "pid": self.process.pid,
                "port": self.port,
                "issuer": ISSUER,
                "kid": self.config.signing_kid,
            },
        )

    # --------------------------------------------------------------- transport

    def _request(self, method, path, body=None, headers=None):
        connection = LocalTLS(
            "gateway.agent-guard.test", self.port, context=self.context, timeout=10
        )
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            raw = response.read()
            return response.status, {k.lower(): v for k, v in response.getheaders()}, raw
        finally:
            connection.close()

    def _cookie(self, headers, name):
        jar = SimpleCookie()
        jar.load(headers["set-cookie"])
        assert name in jar
        return jar[name].value

    def _login(self):
        status, headers, _ = self._request("GET", "/ag/login")
        assert status == 200
        csrf = self._cookie(headers, "ag_login_csrf")
        status, headers, _ = self._request(
            "POST",
            "/ag/login",
            body=urlencode(
                {
                    "tenant_id": TENANT,
                    "subject": SUBJECT,
                    "password": self.password,
                    "csrf_token": csrf,
                    "return_to": "/dashboard",
                }
            ),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": "ag_login_csrf=" + csrf,
            },
        )
        assert status == 303
        return self._cookie(headers, "ag_session")

    # ------------------------------------------------------------ issuing flow

    def browser_root(self, task_id: str, scope: str) -> Issued:
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        redirect = self.config.clients["agent-planner"].redirect_uri
        status, _, raw = self._request(
            "GET",
            "/oauth/authorize?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": "agent-planner",
                    "redirect_uri": redirect,
                    "scope": "openid " + scope,
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": pkce_s256_challenge(verifier),
                    "code_challenge_method": "S256",
                    "ag_task_id": task_id,
                }
            ),
            headers={"Cookie": "ag_session=" + self.session},
        )
        assert status == 200
        request_id = re.search(rb'name="request_id" value="([^"]+)"', raw)
        csrf = re.search(rb'name="csrf_token" value="([^"]+)"', raw)
        assert request_id is not None and csrf is not None
        status, headers, _ = self._request(
            "POST",
            "/ag/consent",
            body=urlencode(
                {
                    "request_id": request_id.group(1).decode("ascii"),
                    "decision": "approve",
                    "csrf_token": csrf.group(1).decode("ascii"),
                }
            ),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": "ag_session=" + self.session,
            },
        )
        assert status == 303
        location = headers["location"]
        assert "state=" + state in location and "code=" in location
        code = location.split("code=", 1)[1].split("&", 1)[0]
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect,
            "code_verifier": verifier,
        }
        answer = self._token(form, "planner", "code-exchange", None)
        claims = verify_compact_jws(
            answer["access_token"], expected_type="ag-at+jwt", trusted_keys=self.as_keys
        )
        assert claims["ag_task_id"] == task_id and claims["ag_parent_id"] is None
        return Issued(answer["access_token"], answer["id_token"], claims)

    def exchange(
        self,
        parent_token: str,
        *,
        holder: str,
        recipient: str,
        amount: int,
        calls: int,
        ttl: int,
    ) -> str:
        parent = verify_compact_jws(
            parent_token, expected_type="ag-at+jwt", trusted_keys=self.as_keys
        )
        form = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": parent_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "audience": GATEWAY_AUDIENCE,
            "scope": " ".join(TOOLS),
            "ag_delegate_client_id": "agent-" + recipient,
            "ag_amount_limit_fen": str(amount),
            "ag_call_limit": str(calls),
            "ag_ttl_seconds": str(ttl),
            "ag_delegation_remaining": str(parent["ag_delegation_remaining"] - 1),
            "ag_constraints": canonical_json_bytes(parent["ag_constraints"]).decode("utf-8"),
            "ag_delegation_key": secrets.token_urlsafe(32),
        }
        try:
            answer = self._token(form, holder, "delegate", parent_token)
        except AssertionError as exc:
            with psycopg.connect(self.dsn, connect_timeout=5) as conn:
                principals = conn.execute(
                    "SELECT client_id,kid,active FROM ag_principals ORDER BY client_id,kid"
                ).fetchall()
                grants = conn.execute(
                    "SELECT grant_id,depth,holder_client_id,holder_kid,revoked "
                    "FROM ag_grants WHERE task_id=%s ORDER BY depth,grant_id",
                    (parent["ag_task_id"],),
                ).fetchall()
            raise AssertionError(
                str(exc)
                + " | diag "
                + json.dumps(
                    {
                        "parent_grant": parent["ag_grant_id"],
                        "holder": holder,
                        "recipient": recipient,
                        "principals": principals,
                        "grants": grants,
                    },
                    default=str,
                )
            ) from None
        claims = verify_compact_jws(
            answer["access_token"], expected_type="ag-at+jwt", trusted_keys=self.as_keys
        )
        assert claims["client_id"] == "agent-" + recipient
        assert claims["ag_limits"]["amount_fen"] == amount
        assert claims["ag_limits"]["calls"] == calls
        return answer["access_token"]

    def _token(self, form: dict, holder: str, purpose: str, token):
        registration = self.registrations[(TENANT, "agent-" + holder)]
        proof = sign_ag_proof(
            self.keys[holder],
            kid=registration.kid,
            client_id="agent-" + holder,
            purpose=purpose,
            endpoint=ISSUER + "/oauth/token",
            body=form,
            token=token,
            now=int(time.time()),
        )
        basic = "Basic " + base64.b64encode(
            ("agent-" + holder + ":" + self.secret_bundle.client_secrets["agent-" + holder]).encode(
                "ascii"
            )
        ).decode("ascii")
        status, headers, raw = self._request(
            "POST",
            "/oauth/token",
            body=urlencode(form),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": basic,
                "AG-Proof": proof,
            },
        )
        assert status == 200, "native AS token endpoint rejected: " + json.dumps(
            {
                key: value
                for key, value in load_strict_json(raw).items()
                if key in ("error", "ag_error")
            }
        )
        assert headers["cache-control"] == "no-store"
        return load_strict_json(raw)

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=15)
        self.stdout_log.close()
        self.stderr_log.close()
        assert self.process.returncode in (0, -signal.SIGTERM)
        out = (self.directory / "as.stdout").read_bytes()
        err = (self.directory / "as.stderr").read_bytes()
        record_native(
            "native-as-stop",
            {
                "pid": self.process.pid,
                "native_exit": self.process.returncode,
                "stdout_sha256": hashlib.sha256(out).hexdigest(),
                "stderr_sha256": hashlib.sha256(err).hexdigest(),
            },
        )
        return self.process.returncode


class BaselineRuntime:
    """Owned real material: tasks (policy only), holders, catalog, downstream."""

    def __init__(self, dsn: str, downstream_dsn: str, private: Path):
        self.dsn = dsn
        self.downstream_dsn = downstream_dsn
        self.private = Path(private)
        self.owner = "a34b-" + secrets.token_hex(8)
        self.tasks: dict[str, TaskSpec] = {}
        self.acl_policies: dict[tuple[str, str], tuple[ACLRegistration, str]] = {}
        self.as_actor = NativeAS(dsn, self.private / "as")
        for name in BASELINE_TASKS:
            self._register(name)
        self.catalog = self._build_catalog()
        self.downstream = MockDownstream(
            downstream_dsn,
            service_secret=DOWNSTREAM_SECRET,
            approved_suppliers={"supplier-001"},
            approved_recipients={"user-demo-001"},
            served_requests={spec.resources["req"] for spec in self.tasks.values()},
        )
        self.downstream.provision()
        self.downstream.reset()
        self.evidence = ResearchEvidence(self.private / "research-evidence")

    # ------------------------------------------------------------ task policy

    @staticmethod
    def _constraints(task_id: str) -> dict:
        return {
            "request_ids": ["req." + task_id],
            "document_ids": ["doc." + task_id],
            "quote_versions": ["quote." + task_id + "@1"],
            "skus": ["sku-001"],
            "max_quantity": 1,
            "delivery_ids": ["delivery." + task_id],
            "template_ids": ["order-created"],
            "recipient_ids": ["user-demo-001"],
        }

    def _register(self, task_id: str) -> TaskSpec:
        constraints = self._constraints(task_id)
        with psycopg.connect(self.dsn, connect_timeout=5) as conn:
            register_task_policy(
                conn,
                tenant_id=TENANT,
                task_id=task_id,
                owner_subject=SUBJECT,
                scope="openid " + " ".join(TOOLS),
                constraints=constraints,
                amount_limit_fen=ROOT_AMOUNT,
                call_limit=ROOT_CALLS,
                task_expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=2400),
            )
        spec = TaskSpec(
            task_id,
            constraints,
            {name: name + "." + task_id for name in ("req", "doc", "quote", "delivery")},
        )
        self.tasks[task_id] = spec
        return spec

    def task(self, name: str) -> TaskSpec:
        return self.tasks[name]

    def _build_catalog(self) -> TrustedCatalog:
        catalog = TrustedCatalog()
        catalog.add_template(CatalogTemplate("order-created"))
        catalog.add_recipient(CatalogRecipient("user-demo-001"))
        for spec in self.tasks.values():
            r = spec.resources
            catalog.add_request(CatalogRequest(r["req"], TENANT, spec.task_id))
            catalog.add_document(CatalogDocument(r["doc"], r["req"]))
            catalog.add_quote(
                CatalogQuote(
                    r["quote"],
                    "1",
                    "supplier-001",
                    r["req"],
                    (CatalogQuoteLine("sku-001", 1, ORDER_AMOUNT),),
                )
            )
            catalog.add_delivery(CatalogDelivery(r["delivery"], TENANT, r["req"]))
        return catalog

    # ------------------------------------------------------------- rate paths

    def root(self, name: str) -> Issued:
        return self.as_actor.browser_root(self.task(name).task_id, " ".join(TOOLS))

    def branches(self, name: str, *, count: int = 1, root: Issued | None = None):
        root = root or self.root(name)
        result = []
        for _ in range(count):
            mid = self.as_actor.exchange(
                root.access_token,
                holder="planner",
                recipient="selector",
                amount=MID_AMOUNT,
                calls=MID_CALLS,
                ttl=240,
            )
            mid_claims = verify_compact_jws(
                mid, expected_type="ag-at+jwt", trusted_keys=self.as_actor.as_keys
            )
            leaf = self.as_actor.exchange(
                mid,
                holder="selector",
                recipient="executor",
                amount=LEAF_AMOUNT,
                calls=LEAF_CALLS,
                ttl=180,
            )
            leaf_claims = verify_compact_jws(
                leaf, expected_type="ag-at+jwt", trusted_keys=self.as_actor.as_keys
            )
            assert leaf_claims["ag_parent_id"] == mid_claims["ag_grant_id"]
            result.append(
                Branch(
                    root.claims["ag_grant_id"],
                    mid_claims["ag_grant_id"],
                    leaf_claims["ag_grant_id"],
                    mid,
                    leaf,
                )
            )
        return result

    def proof(self, holder: str, token: str, body, *, purpose="invoke", now=None, lifetime=60):
        registration = self.as_actor.registrations[(TENANT, "agent-" + holder)]
        return sign_ag_proof(
            self.as_actor.keys[holder],
            kid=registration.kid,
            client_id="agent-" + holder,
            purpose=purpose,
            endpoint=INVOKE_ENDPOINT if purpose == "invoke" else QUERY_ENDPOINT,
            body=body,
            token=token,
            now=int(time.time()) if now is None else now,
            lifetime_seconds=lifetime,
        )

    # --------------------------------------------------------------- services

    def _provider(self) -> PermissionSnapshotProvider:
        return PermissionSnapshotProvider(
            self.dsn,
            issuer=ISSUER,
            as_keys=self.as_actor.as_keys,
            registrations={
                (r.tenant_id, r.client_id, r.kid): r for r in self.as_actor.registrations.values()
            },
        )

    def research(self, mode: str) -> ResearchService:
        if mode not in ("noAtomic", "Bearer", "staticACL"):
            raise ValueError("known research mode required")
        authenticator = ResearchAuthenticator(
            issuer=ISSUER,
            as_keys=self.as_actor.as_keys,
            identities=self.as_actor.resolver,
            provider=self._provider(),
            evidence=self.evidence,
            acl_registry=tuple(reg for reg, _ in self.acl_policies.values()),
        )
        return ResearchService(
            store=ResearchStore(self.dsn, mode=mode, owner=self.owner),
            authenticator=authenticator,
            catalog=self.catalog,
        )

    def worker(self, mode: str) -> ResearchWorker:
        service = ResearchService(
            store=ResearchStore(self.dsn, mode=mode, owner=self.owner),
            authenticator=None,
            catalog=self.catalog,
        )
        return ResearchWorker(
            service=service, downstream=self.downstream, service_secret=DOWNSTREAM_SECRET
        )

    def production(self):
        evidence = EvidenceStore(self.dsn)
        verifier = InvocationVerifier(
            issuer=ISSUER,
            as_keys=self.as_actor.as_keys,
            identities=self.as_actor.resolver,
            permission_provider=self._provider(),
            evidence_store=evidence,
        )
        service = ExecutionService(
            gateway_dsn=self.dsn,
            ledger=ExecutionLedger(self.dsn),
            catalog=self.catalog,
            downstream=self.downstream,
            downstream_secret=DOWNSTREAM_SECRET,
        )
        return service, VerifiedExecution(service, evidence_store=evidence), verifier, evidence

    def acl(self, name: str, role: str, grant_id: str, path_ids) -> str:
        """Approved single policy for ``(role, task)``; returns its password."""
        spec = self.task(name)
        registration = self.as_actor.registrations[(TENANT, "agent-" + role)]
        password = secrets.token_urlsafe(24)
        snapshot = TrustedPermissionSnapshot(
            grant_id=grant_id,
            root_id=path_ids[0],
            tenant_id=TENANT,
            task_id=spec.task_id,
            subject=SUBJECT,
            scope=TOOLS,
            chain=tuple(spec.grant_constraints() for _ in path_ids),
            chain_grant_ids=tuple(path_ids),
        )
        bound = ACLRegistration(
            role=role,
            password_hash=hash_password(password),
            tenant_id=TENANT,
            task_id=spec.task_id,
            subject=SUBJECT,
            client_id="agent-" + role,
            kid=registration.kid,
            grant_id=grant_id,
            root_id=path_ids[0],
            snapshot=snapshot,
            expires_at=int(time.time()) + 1500,
        )
        self.acl_policies[(role, spec.task_id)] = (bound, password)
        return password

    def acl_policy(self, role: str, task_id: str):
        return self.acl_policies[(role, task_id)][0]

    # ------------------------------------------------------------- body utils

    def order_body(self, name: str, *, key: str, quantity: int = 1) -> dict:
        spec = self.task(name)
        r = spec.resources
        return {
            "profile": "GM-MVP-1",
            "task_id": spec.task_id,
            "tool_id": TOOL_ORDER,
            "tool_version": "1",
            "idempotency_key": key,
            "params": {
                "request_id": r["req"],
                "quote_id": r["quote"],
                "quote_version": "1",
                "items": [{"sku": "sku-001", "quantity": quantity}],
                "delivery_id": r["delivery"],
            },
        }

    def read_body(self, name: str, *, key: str) -> dict:
        spec = self.task(name)
        return {
            "profile": "GM-MVP-1",
            "task_id": spec.task_id,
            "tool_id": TOOL_READ,
            "tool_version": "1",
            "idempotency_key": key,
            "params": {"request_id": spec.resources["req"]},
        }

    def document_body(self, name: str, *, key: str) -> dict:
        spec = self.task(name)
        return {
            "profile": "GM-MVP-1",
            "task_id": spec.task_id,
            "tool_id": TOOLS[1],
            "tool_version": "1",
            "idempotency_key": key,
            "params": {
                "request_id": spec.resources["req"],
                "document_id": spec.resources["doc"],
            },
        }

    def stop(self):
        return self.as_actor.stop()


def _counters(dsn, task_id):
    with psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row) as conn:
        return conn.execute(
            "SELECT c.*,g.depth FROM r34.counters c JOIN ag_grants g USING(grant_id) "
            "WHERE g.task_id=%s ORDER BY g.depth",
            (task_id,),
        ).fetchall()


def _operations(dsn, task_id, mode=None):
    with psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row) as conn:
        if mode:
            return conn.execute(
                "SELECT * FROM r34.operations WHERE task_id=%s AND mode=%s ORDER BY accepted_at",
                (task_id, mode),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM r34.operations WHERE task_id=%s ORDER BY accepted_at",
            (task_id,),
        ).fetchall()


def _downstream_rows(dsn, operation_ids):
    return downstream_oracle(dsn, list(operation_ids))["ds_orders"]


def _downstream_operations(dsn, operation_ids):
    return downstream_oracle(dsn, list(operation_ids))["ds_operations"]


def _production_snapshot(dsn, task_id):
    with psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return {
            "operations": conn.execute(
                "SELECT operation_id,status,amount_fen FROM ag_operations WHERE task_id=%s "
                "ORDER BY operation_id",
                (task_id,),
            ).fetchall(),
            "grants": conn.execute(
                "SELECT grant_id,depth,amount_reserved,amount_settled,calls_reserved,"
                "calls_settled,amount_limit,call_limit FROM ag_grants WHERE task_id=%s "
                "ORDER BY depth,grant_id",
                (task_id,),
            ).fetchall(),
            "outbox": conn.execute(
                "SELECT count(*) AS n FROM ag_receipt_outbox o JOIN ag_operations p "
                "USING(operation_id) WHERE p.task_id=%s",
                (task_id,),
            ).fetchone(),
        }


def _policy_for(spec: TaskSpec, branches) -> OraclePolicy:
    def one(branch):
        return OraclePolicy(
            tenant_id=TENANT,
            task_id=spec.task_id,
            root_id=branch.root_id,
            path_ids=(branch.root_id, branch.mid_id, branch.leaf_id),
            amount_limits=(ROOT_AMOUNT, MID_AMOUNT, LEAF_AMOUNT),
            call_limits=(ROOT_CALLS, MID_CALLS, LEAF_CALLS),
        )

    first, *rest = branches
    head = one(first)
    return OraclePolicy(
        tenant_id=TENANT,
        task_id=spec.task_id,
        root_id=first.root_id,
        path_ids=head.path_ids,
        amount_limits=head.amount_limits,
        call_limits=head.call_limits,
        branches=tuple(one(branch) for branch in rest),
    )


def _replay_violations(facts, policy: OraclePolicy):
    """Independent event replay; returns (rebuilt counters, limit violations)."""
    rebuilt = {}
    violations = []
    branches = (policy, *policy.branches)
    for grant in policy.all_grant_ids:
        nodes = [n for n in facts["nodes"] if n["grant_id"] == grant]
        nodes.sort(key=lambda n: n["event_id"])
        total = [0, 0, 0, 0]
        maximum = [0, 0]
        for node in nodes:
            total = [
                a + b
                for a, b in zip(
                    total,
                    (
                        node["amount_reserved_delta"],
                        node["amount_settled_delta"],
                        node["calls_reserved_delta"],
                        node["calls_settled_delta"],
                    ),
                    strict=True,
                )
            ]
            maximum = [
                max(maximum[0], total[0] + total[1]),
                max(maximum[1], total[2] + total[3]),
            ]
        rebuilt[grant] = {"final": total, "high_water": maximum}
        counter = next(c for c in facts["counters"] if c["grant_id"] == grant)
        assert total == [
            counter["amount_reserved"],
            counter["amount_settled"],
            counter["calls_reserved"],
            counter["calls_settled"],
        ], "research counter/event oracle mismatch"
        assert maximum[0] <= counter["amount_high_water"]
        assert maximum[1] <= counter["calls_high_water"]
        owner = next(branch for branch in branches if grant in branch.path_ids)
        index = owner.path_ids.index(grant)
        if maximum[0] > owner.amount_limits[index] or maximum[1] > owner.call_limits[index]:
            violations.append(
                {
                    "grant": grant,
                    "amount": maximum[0],
                    "calls": maximum[1],
                    "amount_limit": owner.amount_limits[index],
                    "call_limit": owner.call_limits[index],
                }
            )
    return rebuilt, violations


_ARCHIVE_TABLES = (
    "r34.counters",
    "r34.operations",
    "r34.events",
    "r34.nodes",
    "r34.proofs",
    "r34.leases",
    "r34.outbox",
    "r34.originals",
    "ag_grants",
    "ag_tasks",
    "ag_task_policies",
    "ag_principals",
    "ag_grant_tokens",
)


def _archive_private_originals(authority, marker: str) -> None:
    """Owned private originals when the harness asked for native evidence."""
    directory = os.environ.get(EVIDENCE_ENV)
    if not directory:
        return
    target = Path(directory) / "archive"
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    with psycopg.connect(authority.dsn, connect_timeout=5, row_factory=dict_row) as conn:
        scratch_tables = [
            row["tablename"]
            for row in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='r34' ORDER BY tablename"
            ).fetchall()
        ]
        lines = [
            json.dumps(
                {
                    "database": authority.name,
                    "owner_run": marker,
                    "tables": scratch_tables,
                }
            )
        ]
        for table in _ARCHIVE_TABLES:
            rows = conn.execute(
                "SELECT row_to_json(t)::text AS raw FROM " + table + " t"
            ).fetchall()
            lines.append(
                json.dumps({"table": table, "count": len(rows), "rows": [r["raw"] for r in rows]})
            )
    path = target / "research-and-authority.ndjson"
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)


class OwnedScratch:
    """Scratch database handle whose repr never contains a DSN."""

    def __init__(self, scratch, kind: str):
        self._scratch = scratch
        self.kind = kind

    @property
    def dsn(self) -> str:
        return self._scratch.dsn

    @property
    def name(self) -> str:
        return self._scratch.name

    def __repr__(self) -> str:
        return "<owned " + self.kind + " test database>"


@pytest.fixture(scope="module")
def baseline_databases():
    """A fresh random owned authority database plus an independent downstream."""
    base = os.environ.get("AGENT_GUARD_TEST_DATABASE_URL")
    if not base:
        pytest.fail(
            "AGENT_GUARD_TEST_DATABASE_URL is required for integration tests; "
            "refusing to skip: skipping would fake a green run.",
            pytrace=False,
        )
    authority_scratch = create_scratch_database(base)
    downstream_scratch = create_downstream_database(base)
    authority = OwnedScratch(authority_scratch, "authority")
    downstream = OwnedScratch(downstream_scratch, "downstream")
    try:
        with psycopg.connect(authority.dsn, connect_timeout=5) as conn:
            apply_bundle_migrations(conn)
        yield authority, downstream
    finally:
        try:
            _archive_private_originals(authority, authority.name)
        finally:
            drop_scratch_database(base, authority_scratch)
            drop_downstream_database(base, downstream_scratch)


@pytest.fixture(scope="module")
def baseline_runtime(baseline_databases, tmp_path_factory):
    authority, downstream = baseline_databases
    private = tmp_path_factory.mktemp("a34-baselines")
    private.chmod(0o700)
    store = ResearchStore(authority.dsn, mode="noAtomic", owner="provision")
    with psycopg.connect(authority.dsn, connect_timeout=5) as conn:
        assert conn.execute("SELECT to_regclass('r34.ag_baseline_owner')").fetchone()[0] is None, (
            "refusing an existing foreign research schema"
        )
    store.provision()
    with psycopg.connect(authority.dsn, connect_timeout=5) as conn:
        with conn.transaction():
            conn.execute("CREATE TABLE r34.ag_baseline_owner (run_id text NOT NULL)")
            conn.execute(
                "INSERT INTO r34.ag_baseline_owner(run_id) VALUES (%s)",
                (authority.name,),
            )
    runtime = BaselineRuntime(authority.dsn, downstream.dsn, private)
    try:
        yield runtime
    finally:
        exit_code = runtime.stop()
        record_native(
            "baseline-runtime-stop",
            {"native_exit": exit_code, "owner": runtime.owner},
        )


# ---------------------------------------------------------------------------
# A34-02 fairness / capability facts
# ---------------------------------------------------------------------------


def test_fair_capabilities_and_equal_workload_resources(baseline_runtime, monkeypatch):
    runtime = baseline_runtime
    plans = generate_suite()
    assert [p.mode for p in plans[:4]] == [p.mode for p in plans[4:]][::-1]
    assert {p.seed for p in plans} == set(SEEDS)
    assert sorted({p.mode for p in plans}) == sorted(MODES)
    assert sum(len(p.intentions) for p in plans) == 40000
    assert sum(len(p.warmup) for p in plans) == 2000
    assert all(len(p.intentions) == 5000 and len(p.warmup) == 250 for p in plans)
    classes = {i.attack_class for p in plans for i in p.intentions if i.category == "attack"}
    assert classes == set(range(10)) and len(CLASSES) == 10
    assert {t for p in plans for t in WORKLOAD_TOOLS} == set(TOOLS)

    root = Path(__file__).resolve().parents[2]
    capabilities = load_strict_json(
        (root / "experiments" / "baseline-capabilities.json").read_bytes()
    )
    assert capabilities["mode_mapping"] == {
        "staticACL": "staticACL",
        "realSM2delegation_noAtomic": "noAtomic",
        "complete": "full",
        "realSM2Bearer": "Bearer",
    }
    assert capabilities["modes"]["staticACL"]["proof"] == "NOT_APPLICABLE"
    assert capabilities["modes"]["staticACL"]["budget"] == "NOT_ENFORCED_RESEARCH_ONLY"
    assert capabilities["modes"]["noAtomic"]["proof"] == "VERIFIED"
    assert capabilities["modes"]["Bearer"]["proof"].startswith("NOT_VERIFIED")

    # Research modules consult no production environment switch and have no
    # default endpoint or database fallback.
    package = root / "experiments" / "agent_guard_bench"
    for name in (
        "static_acl.py",
        "signed_no_atomic.py",
        "sm2_bearer.py",
        "research_contracts.py",
        "research_service.py",
        "research_store.py",
        "research_worker.py",
    ):
        text = (package / name).read_text()
        assert "environ" not in text and "getenv" not in text, name
        assert "AGENT_GUARD_" not in text, name
    with pytest.raises(ValueError):
        ResearchStore("", mode="unknown", owner="x")
    with pytest.raises(ValueError):
        create_research_tls_server(None, host="0.0.0.0", port=1, certificate="x", private_key="y")
    with pytest.raises(ValueError):
        ResearchService(store=object(), authenticator=None, catalog=None)

    # --- one real AS-issued three-node path per research mode -----------------
    acl_root = runtime.root("b34-fair-acl")
    acl_branch = runtime.branches("b34-fair-acl", root=acl_root)[0]
    passwords = {
        "planner": runtime.acl(
            "b34-fair-acl",
            "planner",
            acl_root.claims["ag_grant_id"],
            (acl_root.claims["ag_grant_id"],),
        ),
        "selector": runtime.acl(
            "b34-fair-acl", "selector", acl_branch.mid_id, (acl_branch.root_id, acl_branch.mid_id)
        ),
        "executor": runtime.acl(
            "b34-fair-acl",
            "executor",
            acl_branch.leaf_id,
            (acl_branch.root_id, acl_branch.mid_id, acl_branch.leaf_id),
        ),
    }
    assert len(set(passwords.values())) == 3
    for role, password in passwords.items():
        stored = runtime.acl_policy(role, runtime.task("b34-fair-acl").task_id)
        assert verify_password(password, stored.password_hash)
        assert all(
            not verify_password(other, stored.password_hash)
            for name, other in passwords.items()
            if name != role
        )
    acl = StaticACL(runtime.research("staticACL"))
    assert acl.mode == "staticACL" and acl.budget == "NOT_ENFORCED_RESEARCH_ONLY"
    assert acl.receipt == "NOT_APPLICABLE" and acl.independent_audit == "NOT_APPLICABLE"
    assert acl.possession == "PASSWORD_AUTHENTICATED"
    with pytest.raises(ValueError):
        StaticACL(runtime.research("noAtomic"))
    with pytest.raises(ValueError):
        acl.accept(object())

    # trusted setup: all counters exist before any measured invoke
    for role, password in passwords.items():
        body = canonical(runtime.read_body("b34-fair-acl", key="acl-setup-" + role))
        acl.initialize_path(
            acl.authenticate(body=body, now=int(time.time()), role=role, password=password)
        )
    for role, password in passwords.items():
        answer = acl.invoke(
            body=canonical(runtime.read_body("b34-fair-acl", key="acl-read-" + role)),
            now=int(time.time()),
            role=role,
            password=password,
        )
        assert answer.disposition == "NEW" and answer.amount_fen == 0

    # distinct credentials: wrong password and swapped role both refuse
    expect_rejected(
        lambda: acl.invoke(
            body=canonical(runtime.read_body("b34-fair-acl", key="acl-bad-pw")),
            now=int(time.time()),
            role="executor",
            password=passwords["selector"],
        ),
        "INVALID_CREDENTIAL",
    )
    expect_rejected(
        lambda: acl.invoke(
            body=canonical(runtime.read_body("b34-fair-acl", key="acl-bad-role")),
            now=int(time.time()),
            role="planner",
            password=passwords["executor"],
        ),
        "INVALID_CREDENTIAL",
    )

    # approved tenant/tool/resource/quantity/delivery scope, never allow-all
    cases = {}
    cases["quantity"] = runtime.order_body("b34-fair-acl", key="acl-q2", quantity=2)
    cases["resource"] = runtime.order_body("b34-fair-acl", key="acl-resource")
    cases["resource"]["params"]["request_id"] = "unapproved-request"
    cases["delivery"] = runtime.order_body("b34-fair-acl", key="acl-delivery")
    cases["delivery"]["params"]["delivery_id"] = "unapproved-delivery"
    cases["tool"] = runtime.order_body("b34-fair-acl", key="acl-tool")
    cases["tool"]["tool_id"] = "unapproved.tool"
    for _name, body in cases.items():
        expect_rejected(
            lambda body=body: acl.invoke(
                body=canonical(body),
                now=int(time.time()),
                role="executor",
                password=passwords["executor"],
            ),
            "RESOURCE_NOT_AUTHORIZED",
            "SCOPE_DENIED",
            "UNSUPPORTED_TOOL",
        )

    # A decoy production-style skip variable must not weaken any check.
    monkeypatch.setenv("AGENT_GUARD_SKIP_VERIFICATION", "1")
    monkeypatch.setenv("AG34_SKIP_ALL", "1")
    expect_rejected(
        lambda: acl.invoke(
            body=canonical(cases["resource"]),
            now=int(time.time()),
            role="executor",
            password=passwords["executor"],
        ),
        "RESOURCE_NOT_AUTHORIZED",
        "SCOPE_DENIED",
    )

    # single policy per (role, task): a duplicated registration is refused
    registration = runtime.acl_policy("executor", runtime.task("b34-fair-acl").task_id)
    with pytest.raises(ValueError):
        ResearchAuthenticator(
            issuer=ISSUER,
            as_keys=runtime.as_actor.as_keys,
            identities=runtime.as_actor.resolver,
            provider=runtime._provider(),
            evidence=runtime.evidence,
            acl_registry=(registration, registration),
        )

    # budget honestly NOT_ENFORCED for the ACL ablation: two 70000 orders on
    # the same leaf both commit, exceeding the leaf limit.
    orders = [
        acl.invoke(
            body=canonical(runtime.order_body("b34-fair-acl", key="acl-order-" + str(index))),
            now=int(time.time()),
            role="executor",
            password=passwords["executor"],
        )
        for index in (1, 2)
    ]
    assert all(
        answer.disposition == "NEW" and answer.amount_fen == ORDER_AMOUNT for answer in orders
    )
    leaf = _counters(runtime.dsn, runtime.task("b34-fair-acl").task_id)[-1]
    assert leaf["amount_reserved"] + leaf["amount_settled"] == 140000
    record_native(
        "acl-not-enforced",
        {
            "task_id": runtime.task("b34-fair-acl").task_id,
            "leaf_amount": leaf["amount_reserved"] + leaf["amount_settled"],
            "operations": [answer.operation_id for answer in orders],
        },
    )

    # --- genuine AG-Proof no-atomic positive and its locked check -------------
    no_root = runtime.root("b34-fair-no")
    no_branch = runtime.branches("b34-fair-no", root=no_root)[0]
    no = SignedNoAtomic(runtime.research("noAtomic"))
    assert no.possession == "VERIFIED"
    setup = no.authenticate(
        token=no_branch.leaf_token,
        proof=runtime.proof(
            "executor", no_branch.leaf_token, runtime.read_body("b34-fair-no", key="no-setup")
        ),
        body=canonical(runtime.read_body("b34-fair-no", key="no-setup")),
        now=int(time.time()),
    )
    no.initialize_path(setup)
    accepted = no.invoke(
        token=no_branch.leaf_token,
        proof=runtime.proof(
            "executor", no_branch.leaf_token, runtime.order_body("b34-fair-no", key="no-order")
        ),
        body=canonical(runtime.order_body("b34-fair-no", key="no-order")),
        now=int(time.time()),
    )
    assert accepted.disposition == "NEW" and accepted.amount_fen == ORDER_AMOUNT
    assert runtime.worker("noAtomic").run(accepted.operation_id) == "SUCCEEDED"
    expect_rejected(
        lambda: no.invoke(
            token=no_branch.leaf_token,
            proof=runtime.proof(
                "executor",
                no_branch.leaf_token,
                runtime.order_body("b34-fair-no", key="no-order-2"),
            ),
            body=canonical(runtime.order_body("b34-fair-no", key="no-order-2")),
            now=int(time.time()),
        ),
        "BUDGET_EXCEEDED",
    )

    # full production path as control on the same chain: accepted and settled
    # once through the genuine public verifier.
    service, adapter, verifier, _ = runtime.production()
    full_body = runtime.order_body("b34-fair-no", key="full-order")
    bundle = verifier.verify_bundle(
        no_branch.leaf_token,
        runtime.proof("executor", no_branch.leaf_token, full_body),
        body=canonical(full_body),
        now=int(time.time()),
    )
    full = adapter.accept(bundle)
    assert full.status == "RESERVED"
    assert service.run_operation(full.operation_id).status == "SUCCEEDED"

    # --- genuine Bearer positive: no holder key at invoke ---------------------
    bearer_root = runtime.root("b34-fair-bearer")
    bearer_branch = runtime.branches("b34-fair-bearer", root=bearer_root)[0]
    bearer = SM2Bearer(runtime.research("Bearer"))
    assert bearer.possession == "NOT_VERIFIED" and bearer.supplied_proof == "IGNORED"
    assert bearer.replay == "NOT_APPLICABLE" and bearer.receipt == "NOT_APPLICABLE"
    setup = bearer.authenticate(
        token=bearer_branch.leaf_token,
        body=canonical(runtime.read_body("b34-fair-bearer", key="bearer-setup")),
        now=int(time.time()),
        proof="supplied-but-ignored",
    )
    assert type(setup) is BearerContext and setup.proof is None
    assert setup.holder_possession == "NOT_VERIFIED"
    bearer.initialize_path(setup)
    answered = bearer.invoke(
        token=bearer_branch.leaf_token,
        body=canonical(runtime.order_body("b34-fair-bearer", key="bearer-order")),
        now=int(time.time()),
        proof="supplied-but-ignored",
    )
    assert answered.disposition == "NEW" and answered.amount_fen == ORDER_AMOUNT
    assert runtime.worker("Bearer").run(answered.operation_id) == "SUCCEEDED"
    with pytest.raises(ValueError):
        bearer.accept(object())
    expect_rejected(
        lambda: bearer.invoke(
            token=bearer_branch.leaf_token,
            body=canonical(runtime.order_body("b34-fair-bearer", key="bearer-order-2")),
            now=int(time.time()),
        ),
        "BUDGET_EXCEEDED",
    )

    # --- real TLS research listener: reuse, invalid credential, fixed paths ---
    server = create_research_tls_server(
        acl,
        host="127.0.0.1",
        port=fresh_port(),
        certificate=runtime.as_actor.tls / "tls.pem",
        private_key=runtime.as_actor.tls / "tls.key",
    )
    worker_thread = threading.Thread(target=server.serve_forever, daemon=True)
    worker_thread.start()
    try:
        context = ssl.create_default_context(cafile=str(runtime.as_actor.tls / "ca.pem"))
        connection = LocalTLS(
            "gateway.agent-guard.test", server.server_address[1], context=context, timeout=10
        )
        try:
            for index in (1, 2):
                connection.request(
                    "POST",
                    "/v1/invocations",
                    body=canonical(runtime.read_body("b34-fair-acl", key="acl-tls-" + str(index))),
                    headers={
                        "Content-Type": "application/json",
                        "X-ACL-Role": "planner",
                        "Authorization": "ACL " + passwords["planner"],
                    },
                )
                response = connection.getresponse()
                answer = load_strict_json(response.read())
                assert response.status == 200 and answer["disposition"] in ("NEW", "EXISTING")
            connection.request(
                "POST",
                "/v1/invocations",
                body=canonical(runtime.read_body("b34-fair-acl", key="acl-tls-bad")),
                headers={
                    "Content-Type": "application/json",
                    "X-ACL-Role": "planner",
                    "Authorization": "ACL wrong-password",
                },
            )
            response = connection.getresponse()
            assert response.status == 400 and load_strict_json(response.read()) == {
                "error": "INVALID_CREDENTIAL"
            }
            connection.request(
                "POST",
                "/v1/unknown",
                body=b"{}",
                headers={"Content-Type": "application/json", "Authorization": "ACL x"},
            )
            response = connection.getresponse()
            assert response.status == 400
        finally:
            connection.close()
        record_native("research-tls-reuse", {"port": server.server_address[1]})
    finally:
        server.shutdown()
        server.server_close()
        worker_thread.join(timeout=10)

    record_native(
        "fair-capabilities",
        {
            "acl_path": [acl_root.claims["ag_grant_id"], acl_branch.mid_id, acl_branch.leaf_id],
            "noAtomic_operation": accepted.operation_id,
            "full_operation": full.operation_id,
            "bearer_operation": answered.operation_id,
            "plans": [(p.mode, p.seed, len(p.intentions), len(p.warmup)) for p in plans],
        },
    )


# ---------------------------------------------------------------------------
# A34-03 real signed no-atomic isolated budget race
# ---------------------------------------------------------------------------


def _no_atomic_controls(runtime, round_id):
    """Race negatives: current state, TTL lock, crash/lease/fence/UNKNOWN.

    Runs in every applicable round with per-round isolated tasks, grants,
    branches and credential state; the real killed child, lease, fencing and
    TTL lock wait are re-established from scratch each round.
    """
    suffix = "-r" + str(round_id)
    noint = "b34-noint" + suffix
    nostate = "b34-nostate" + suffix
    nokey = "b34-nokey" + suffix
    nottl = "b34-nottl" + suffix
    nocrash = "b34-nocrash" + suffix
    service = runtime.research("noAtomic")
    worker = runtime.worker("noAtomic")
    results = {}

    # fresh identity / same proof / changed intent / query authorization
    intent_root = runtime.root(noint)
    intent_branch = runtime.branches(noint, root=intent_root)[0]
    setup = service.authenticate(
        token=intent_branch.leaf_token,
        proof=runtime.proof(
            "executor", intent_branch.leaf_token, runtime.read_body(noint, key="intent-setup")
        ),
        body=canonical(runtime.read_body(noint, key="intent-setup")),
        now=int(time.time()),
    )
    service.initialize_path(setup)
    body = canonical(runtime.order_body(noint, key="intent-order"))
    proof = runtime.proof(
        "executor", intent_branch.leaf_token, runtime.order_body(noint, key="intent-order")
    )
    first = service.accept(
        service.authenticate(
            token=intent_branch.leaf_token, proof=proof, body=body, now=int(time.time())
        )
    )
    assert first.disposition == "NEW"
    expect_rejected(
        lambda: service.accept(
            service.authenticate(
                token=intent_branch.leaf_token, proof=proof, body=body, now=int(time.time())
            )
        ),
        "REPLAY",
    )
    fresh = service.accept(
        service.authenticate(
            token=intent_branch.leaf_token,
            proof=runtime.proof(
                "executor",
                intent_branch.leaf_token,
                runtime.order_body(noint, key="intent-order"),
            ),
            body=body,
            now=int(time.time()),
        )
    )
    assert fresh.disposition == "EXISTING" and fresh.operation_id == first.operation_id
    expect_rejected(
        lambda: service.accept(
            service.authenticate(
                token=intent_branch.leaf_token,
                proof=runtime.proof(
                    "executor",
                    intent_branch.leaf_token,
                    runtime.order_body(noint, key="intent-order", quantity=2),
                ),
                body=canonical(runtime.order_body(noint, key="intent-order", quantity=2)),
                now=int(time.time()),
            )
        ),
        "SCOPE_DENIED",
    )
    other = runtime.branches(noint, root=intent_root)[0]
    expect_rejected(
        lambda: service.accept(
            service.authenticate(
                token=other.leaf_token,
                proof=runtime.proof(
                    "executor",
                    other.leaf_token,
                    runtime.order_body(noint, key="intent-order"),
                ),
                body=body,
                now=int(time.time()),
            )
        ),
        "IDEMPOTENCY_CONFLICT",
    )
    query_request = {
        "profile": "GM-MVP-1",
        "task_id": runtime.task(noint).task_id,
        "operation_id": first.operation_id,
    }
    query_body = canonical(query_request)
    query_proof = runtime.proof(
        "executor", intent_branch.leaf_token, query_request, purpose="result-read"
    )
    answer = service.query(
        service.authenticate_query(
            token=intent_branch.leaf_token, proof=query_proof, body=query_body, now=int(time.time())
        )
    )
    assert answer["status"] == "RESERVED" and answer["receipt"] == "NOT_APPLICABLE"
    expect_rejected(
        lambda: service.query(
            service.authenticate_query(
                token=intent_branch.leaf_token,
                proof=query_proof,
                body=query_body,
                now=int(time.time()),
            )
        ),
        "REPLAY",
    )
    expect_rejected(
        lambda: service.query(
            service.authenticate_query(
                token=other.leaf_token,
                proof=runtime.proof(
                    "executor", other.leaf_token, query_request, purpose="result-read"
                ),
                body=query_body,
                now=int(time.time()),
            )
        ),
        "SCOPE_DENIED",
    )
    results["intent"] = {
        "operation": first.operation_id,
        "counter": _counters(runtime.dsn, runtime.task(noint).task_id)[-1]["amount_reserved"],
    }

    # revocation and key deactivation: fresh requests fail, accepted recovery
    # still completes the original immutable intent.
    state_root = runtime.root(nostate)
    state_branch = runtime.branches(nostate, root=state_root)[0]
    service.initialize_path(
        service.authenticate(
            token=state_branch.leaf_token,
            proof=runtime.proof(
                "executor",
                state_branch.leaf_token,
                runtime.read_body(nostate, key="state-setup"),
            ),
            body=canonical(runtime.read_body(nostate, key="state-setup")),
            now=int(time.time()),
        )
    )
    held = service.accept(
        service.authenticate(
            token=state_branch.leaf_token,
            proof=runtime.proof(
                "executor",
                state_branch.leaf_token,
                runtime.read_body(nostate, key="state-held"),
            ),
            body=canonical(runtime.read_body(nostate, key="state-held")),
            now=int(time.time()),
        )
    )
    with psycopg.connect(runtime.dsn, connect_timeout=5) as conn:
        revoke_grant(conn, state_branch.mid_id)
    expect_rejected(
        lambda: service.accept(
            service.authenticate(
                token=state_branch.leaf_token,
                proof=runtime.proof(
                    "executor",
                    state_branch.leaf_token,
                    runtime.read_body(nostate, key="state-after"),
                ),
                body=canonical(runtime.read_body(nostate, key="state-after")),
                now=int(time.time()),
            )
        ),
        "REVOKED",
    )
    assert worker.run(held.operation_id) == "SUCCEEDED"
    results["revoked-recovery"] = held.operation_id

    key_root = runtime.root(nokey)
    key_branch = runtime.branches(nokey, root=key_root)[0]
    service.initialize_path(
        service.authenticate(
            token=key_branch.leaf_token,
            proof=runtime.proof(
                "executor", key_branch.leaf_token, runtime.read_body(nokey, key="key-setup")
            ),
            body=canonical(runtime.read_body(nokey, key="key-setup")),
            now=int(time.time()),
        )
    )
    held = service.accept(
        service.authenticate(
            token=key_branch.leaf_token,
            proof=runtime.proof(
                "executor", key_branch.leaf_token, runtime.read_body(nokey, key="key-held")
            ),
            body=canonical(runtime.read_body(nokey, key="key-held")),
            now=int(time.time()),
        )
    )
    with psycopg.connect(runtime.dsn, connect_timeout=5) as conn:
        deactivate_principal(
            conn,
            tenant_id=TENANT,
            client_id="agent-executor",
            kid=runtime.as_actor.registrations[(TENANT, "agent-executor")].kid,
        )
    expect_rejected(
        lambda: service.accept(
            service.authenticate(
                token=key_branch.leaf_token,
                proof=runtime.proof(
                    "executor",
                    key_branch.leaf_token,
                    runtime.read_body(nokey, key="key-after"),
                ),
                body=canonical(runtime.read_body(nokey, key="key-after")),
                now=int(time.time()),
            )
        ),
        "HOLDER_MISMATCH",
    )
    assert worker.run(held.operation_id) == "SUCCEEDED"
    results["key-disabled-recovery"] = held.operation_id
    # The disabled key is test-owned synthetic state; restore it so later real
    # AS exchanges remain genuine. This restores state, it never relaxes a check.
    with psycopg.connect(runtime.dsn, connect_timeout=5) as conn:
        restored = conn.execute(
            "UPDATE ag_principals SET active=TRUE, deactivated_at=NULL "
            "WHERE tenant_id=%s AND client_id=%s AND kid=%s RETURNING client_id",
            (
                TENANT,
                "agent-executor",
                runtime.as_actor.registrations[(TENANT, "agent-executor")].kid,
            ),
        ).fetchone()
    assert restored == ("agent-executor",)
    record_native(
        "principal-restored-round-" + str(round_id).zfill(2), {"client": "agent-executor"}
    )

    # TTL lock: a real grant row lock held past the proof window; the final
    # database clock check must reject with zero writes.
    ttl_root = runtime.root(nottl)
    ttl_branch = runtime.branches(nottl, root=ttl_root)[0]
    service.initialize_path(
        service.authenticate(
            token=ttl_branch.leaf_token,
            proof=runtime.proof(
                "executor", ttl_branch.leaf_token, runtime.read_body(nottl, key="ttl-setup")
            ),
            body=canonical(runtime.read_body(nottl, key="ttl-setup")),
            now=int(time.time()),
        )
    )
    ttl_body = canonical(runtime.order_body(nottl, key="ttl-order"))
    before_rows = _operations(runtime.dsn, runtime.task(nottl).task_id)
    with psycopg.connect(runtime.dsn, connect_timeout=5) as locker:
        locker.execute(
            "SELECT grant_id FROM ag_grants WHERE grant_id=%s FOR UPDATE",
            (ttl_branch.leaf_id,),
        )
        blocker = locker.execute("SELECT pg_backend_pid()").fetchone()[0]
        observed = []
        attempts = 0
        # A two-second live-proof margin keeps the freshness precheck inside the
        # service's three-second lock window; if host scheduling jitter beats
        # that margin before the first lock attempt, bounded fresh material is
        # retried. Every attempt still requires the real observed grant-lock
        # wait and the final database clock STALE_REQUEST.
        for attempt in range(4):
            attempts = attempt + 1
            sent = int(time.time()) - 58
            proof = runtime.proof(
                "executor",
                ttl_branch.leaf_token,
                runtime.order_body(nottl, key="ttl-order"),
                now=sent,
            )
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    lambda proof=proof: service.accept(
                        service.authenticate(
                            token=ttl_branch.leaf_token,
                            proof=proof,
                            body=ttl_body,
                            now=int(time.time()),
                        )
                    )
                )
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    with psycopg.connect(runtime.dsn, connect_timeout=5) as probe:
                        waiting = probe.execute(
                            "SELECT pid FROM pg_stat_activity WHERE %s=ANY(pg_blocking_pids(pid))",
                            (blocker,),
                        ).fetchall()
                    if waiting:
                        observed = [row[0] for row in waiting]
                        break
                    if future.done():
                        break
                    time.sleep(0.02)
                if not observed:
                    tries = 0
                    while not future.done() and tries < 100:
                        time.sleep(0.02)
                        tries += 1
                    if future.done():
                        try:
                            future.result(timeout=1)
                        except Exception:
                            pass
                    continue
                remaining = (sent + 60) - time.time()
                time.sleep(min(2.5, max(0.25, remaining + 0.35)))
                locker.rollback()
                with pytest.raises((ResearchError, VerificationError)) as caught:
                    future.result(timeout=10)
                assert rejection_code(caught.value) == "STALE_REQUEST"
                break
        assert observed, "real lock wait not observed within bounded attempts"
        record_native(
            "ttl-lock-wait-round-" + str(round_id).zfill(2),
            {
                "blocker_backend": blocker,
                "waiting_backends": observed,
                "proof_iat": sent,
                "attempts": attempts,
            },
        )
    assert _operations(runtime.dsn, runtime.task(nottl).task_id) == before_rows
    results["ttl"] = {"blocker": blocker, "waiting": observed, "attempts": attempts}

    # crash / lease / fencing / UNKNOWN with a real killed child process
    crash_root = runtime.root(nocrash)
    crash_branch = runtime.branches(nocrash, root=crash_root)[0]
    service.initialize_path(
        service.authenticate(
            token=crash_branch.leaf_token,
            proof=runtime.proof(
                "executor",
                crash_branch.leaf_token,
                runtime.read_body(nocrash, key="crash-setup"),
            ),
            body=canonical(runtime.read_body(nocrash, key="crash-setup")),
            now=int(time.time()),
        )
    )
    crashed = service.accept(
        service.authenticate(
            token=crash_branch.leaf_token,
            proof=runtime.proof(
                "executor",
                crash_branch.leaf_token,
                runtime.document_body(nocrash, key="crash-document"),
            ),
            body=canonical(runtime.document_body(nocrash, key="crash-document")),
            now=int(time.time()),
        )
    )
    unknown = service.accept(
        service.authenticate(
            token=crash_branch.leaf_token,
            proof=runtime.proof(
                "executor",
                crash_branch.leaf_token,
                runtime.document_body(nocrash, key="unknown-document"),
            ),
            body=canonical(runtime.document_body(nocrash, key="unknown-document")),
            now=int(time.time()),
        )
    )
    directory = runtime.private / "crash"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    marker = directory / ("crash-marker-" + secrets.token_hex(4) + ".json")
    script = (
        "import json,sys,time\n"
        "from pathlib import Path\n"
        "from experiments.agent_guard_bench.research_service import ResearchService\n"
        "from experiments.agent_guard_bench.research_store import ResearchStore\n"
        "from experiments.agent_guard_bench.research_worker import ResearchWorker\n"
        "from agent_guard.tools.downstream import MockDownstream\n"
        "payload=json.loads(sys.stdin.readline())\n"
        "worker=ResearchWorker(service=ResearchService(store=ResearchStore(payload['dsn'],"
        "mode='noAtomic',owner='killed-probe'),authenticator=None,catalog=None),"
        "downstream=MockDownstream(payload['downstream_dsn'],service_secret=payload['secret'],"
        "approved_suppliers={'supplier-001'},approved_recipients={'user-demo-001'},"
        "served_requests={payload['request_id']}),service_secret=payload['secret'])\n"
        "def pause(lease,outcome):\n"
        " Path(payload['marker']).write_text(json.dumps({'pid':__import__('os').getpid(),"
        "'operation_id':lease.operation_id,'owner':lease.owner,'version':lease.version,"
        "'expires_at':lease.expires_at.isoformat(),"
        "'previous_status':lease.previous_status,'effect':outcome is not None}))\n"
        " time.sleep(300)\n"
        "print(json.dumps({'child_started':True}),flush=True)\n"
        "worker.run(payload['operation_id'],owner='killed-probe',pause=pause)\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    child.stdin.write(
        json.dumps(
            {
                "dsn": runtime.dsn,
                "downstream_dsn": runtime.downstream_dsn,
                "secret": DOWNSTREAM_SECRET,
                "operation_id": crashed.operation_id,
                "request_id": runtime.task(nocrash).resources["req"],
                "marker": str(marker),
            }
        )
        + "\n"
    )
    child.stdin.flush()
    deadline = time.monotonic() + 20
    while not marker.exists():
        assert child.poll() is None, "crash child exited before its pause marker"
        assert time.monotonic() < deadline, "finite crash marker deadline"
        time.sleep(0.02)
    # The marker path exists as soon as the child opens it; read only after a
    # complete, strictly parseable record is visible (bounded by the same
    # finite deadline), otherwise a partially written file races the read.
    while True:
        try:
            observed = load_strict_json(marker.read_bytes())
            break
        except ValueError:
            assert child.poll() is None, "crash child exited before a complete marker"
            assert time.monotonic() < deadline, "finite crash marker deadline"
            time.sleep(0.02)
    assert observed["pid"] == child.pid and observed["effect"] is True
    start_ticks = Path("/proc/" + str(child.pid) + "/stat").read_text().split()[21]
    os.kill(child.pid, signal.SIGKILL)
    wait_return = child.wait(timeout=10)
    out, err = child.communicate()
    assert wait_return == -signal.SIGKILL
    record_native(
        "crash-child-killed-round-" + str(round_id).zfill(2),
        {
            "pid": child.pid,
            "start_ticks": start_ticks,
            "wait_return": wait_return,
            "stdout_sha256": hashlib.sha256(out.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(err.encode()).hexdigest(),
            "lease": observed,
        },
    )
    assert len(_downstream_operations(runtime.downstream_dsn, [crashed.operation_id])) == 1, (
        "real downstream read effect required"
    )
    crashed_row = [
        row
        for row in _operations(runtime.dsn, runtime.task(nocrash).task_id)
        if row["operation_id"] == crashed.operation_id
    ][0]
    assert crashed_row["status"] == "EXECUTING"
    old_lease = Lease(
        observed["operation_id"],
        observed["owner"],
        observed["version"],
        datetime.fromisoformat(observed["expires_at"]),
        observed["previous_status"],
    )
    with psycopg.connect(runtime.dsn, autocommit=True, connect_timeout=5) as conn:
        conn.execute(
            "UPDATE r34.leases SET expires_at=clock_timestamp()-interval '1 second' "
            "WHERE operation_id=%s",
            (crashed.operation_id,),
        )
    expect_rejected(lambda: worker.service.finalize(old_lease, None), "STALE_FENCE")
    recovered_lease = worker.service.claim(crashed.operation_id, "recover-2")
    assert recovered_lease.version == observed["version"] + 1
    expect_rejected(lambda: worker.service.finalize(old_lease, None), "STALE_FENCE")
    outcome = worker.downstream.query(
        service_secret=DOWNSTREAM_SECRET, operation_id=crashed.operation_id
    )
    assert worker.service.finalize(recovered_lease, outcome) == "SUCCEEDED"
    assert len(_downstream_operations(runtime.downstream_dsn, [crashed.operation_id])) == 1, (
        "recovery must not duplicate the downstream read effect"
    )
    results["crash"] = {"pid": child.pid, "wait_return": wait_return}

    # UNKNOWN keeps the reservation until a real recovery confirms the effect
    lease = worker.service.claim(unknown.operation_id, "probe-unknown")
    assert worker.service.finalize(lease, None) == "UNKNOWN"
    unknown_counters = _counters(runtime.dsn, runtime.task(nocrash).task_id)
    assert all(
        counter["amount_reserved"] == 0
        and counter["amount_settled"] == 0
        and counter["calls_reserved"] == 1
        and counter["calls_settled"] == 1
        for counter in unknown_counters
    ), "crash read settled one call; unknown must still reserve the second call"
    with psycopg.connect(runtime.dsn, autocommit=True, connect_timeout=5) as conn:
        conn.execute(
            "UPDATE r34.leases SET expires_at=clock_timestamp()-interval '1 second' "
            "WHERE operation_id=%s",
            (unknown.operation_id,),
        )
    assert worker.run(unknown.operation_id) == "SUCCEEDED"
    assert len(_downstream_operations(runtime.downstream_dsn, [unknown.operation_id])) == 1, (
        "unknown recovery must produce exactly one downstream read effect"
    )
    results["unknown"] = unknown.operation_id
    return results


@pytest.mark.parametrize("round_id", range(10))
def test_real_signed_no_atomic_isolated_budget_race(baseline_runtime, round_id):
    runtime = baseline_runtime
    task_name = "b34-race-" + str(round_id)
    spec = runtime.task(task_name)
    root = runtime.root(task_name)
    branches = runtime.branches(task_name, count=2, root=root)
    assert len({branch.mid_id for branch in branches}) == 2
    assert len({branch.leaf_id for branch in branches}) == 2
    service = runtime.research("noAtomic")
    worker = runtime.worker("noAtomic")

    for branch in branches:
        body = canonical(runtime.read_body(task_name, key="setup-" + branch.leaf_id))
        service.initialize_path(
            service.authenticate(
                token=branch.leaf_token,
                proof=runtime.proof(
                    "executor",
                    branch.leaf_token,
                    runtime.read_body(task_name, key="setup-" + branch.leaf_id),
                ),
                body=body,
                now=int(time.time()),
            )
        )

    barrier = Barrier(2)
    facts = {}
    local = threading.local()
    original_transaction = service.store.transaction

    @contextlib.contextmanager
    def observed_transaction(**kwargs):
        with original_transaction(**kwargs) as conn:
            local.connection = conn
            try:
                yield conn
            finally:
                local.connection = None

    service.store.transaction = observed_transaction

    def rendezvous():
        connection = local.connection
        backend = connection.execute("SELECT pg_backend_pid()").fetchone()["pg_backend_pid"]
        reads = connection.execute(
            "SELECT g.depth,r.amount_reserved,r.amount_settled,r.calls_reserved,"
            "r.calls_settled FROM r34.counters r JOIN ag_grants g USING(grant_id) "
            "WHERE g.task_id=%s ORDER BY g.depth",
            (spec.task_id,),
        ).fetchall()
        facts[backend] = [tuple(row.values()) for row in reads]
        barrier.wait(timeout=10)

    def accept(branch):
        body = runtime.order_body(task_name, key="race-" + branch.leaf_id)
        context = service.authenticate(
            token=branch.leaf_token,
            proof=runtime.proof("executor", branch.leaf_token, body),
            body=canonical(body),
            now=int(time.time()),
        )
        return service.accept(context, controlled_before_update=rendezvous)

    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(accept, branches))
    service.store.transaction = original_transaction
    assert all(answer.disposition == "NEW" for answer in answers)
    assert len({answer.operation_id for answer in answers}) == 2
    assert len(facts) == 2, "two real backend connections required"
    root_zero = {}
    for backend, reads in facts.items():
        assert sorted(read[0] for read in reads) == [0, 1, 1, 2, 2], (
            "root plus both branch mid/leaf rows required"
        )
        assert all(value == 0 for read in reads for value in read[1:]), (
            "every applicable ancestor must still read zero before the first update"
        )
        root_zero[backend] = reads[0][1]
    assert sorted(root_zero.values()) == [0, 0], "shared root read zero on both branches"
    for answer in answers:
        assert worker.run(answer.operation_id) == "SUCCEEDED"

    policy = _policy_for(spec, branches)
    oracle = snapshot_oracle(service.store, policy)
    rebuilt, violations = _replay_violations(oracle, policy)
    assert {violation["grant"] for violation in violations} == {branches[0].root_id}
    assert violations[0]["amount"] == 140000
    assert violations[0]["amount_limit"] == ROOT_AMOUNT
    orders = _downstream_rows(runtime.downstream_dsn, [answer.operation_id for answer in answers])
    assert len(orders) == 2
    assert sum(row["amount_fen"] for row in orders) == 140000
    record_native(
        "no-atomic-race-round-" + str(round_id).zfill(2),
        {
            "round": round_id,
            "task_id": spec.task_id,
            "root_id": branches[0].root_id,
            "paths": [[b.root_id, b.mid_id, b.leaf_id] for b in branches],
            "operations": [answer.operation_id for answer in answers],
            "backend_facts": {str(key): value for key, value in facts.items()},
            "root_zero": {str(key): value for key, value in root_zero.items()},
            "violations": violations,
            "rebuilt_root": rebuilt[branches[0].root_id],
        },
    )

    # Production control on the same two intents, every round: at most one
    # acceptance, all-ancestor occupancy inside the enforced limits.
    production, adapter, verifier, _ = runtime.production()
    bundles = [
        verifier.verify_bundle(
            branch.leaf_token,
            runtime.proof(
                "executor",
                branch.leaf_token,
                runtime.order_body(task_name, key="full-" + branch.leaf_id),
            ),
            body=canonical(runtime.order_body(task_name, key="full-" + branch.leaf_id)),
            now=int(time.time()),
        )
        for branch in branches
    ]

    def control(bundle):
        try:
            return ("ACCEPTED", adapter.accept(bundle).operation_id)
        except (LedgerError, ExecutionError) as exc:
            return ("REJECTED", rejection_code(exc))

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(control, bundles))
    accepted = [value for kind, value in outcomes if kind == "ACCEPTED"]
    rejected = [value for kind, value in outcomes if kind == "REJECTED"]
    assert len(accepted) == 1 and rejected == ["BUDGET_EXCEEDED"]
    assert production.run_operation(accepted[0]).status == "SUCCEEDED"
    granted = _production_snapshot(runtime.dsn, spec.task_id)["grants"]
    assert all(
        row["amount_reserved"] + row["amount_settled"] <= row["amount_limit"]
        and row["calls_reserved"] + row["calls_settled"] <= row["call_limit"]
        for row in granted
    ), "production occupancy must stay inside every applicable ancestor limit"
    root_row = next(row for row in granted if row["grant_id"] == branches[0].root_id)
    occupancy = root_row["amount_reserved"] + root_row["amount_settled"]
    assert occupancy == ORDER_AMOUNT
    record_native(
        "full-control-round-" + str(round_id).zfill(2),
        {
            "round": round_id,
            "outcomes": outcomes,
            "occupancy": occupancy,
            "operation": accepted[0],
            "grant_occupancy": [
                [
                    row["grant_id"],
                    row["amount_reserved"] + row["amount_settled"],
                    row["amount_limit"],
                ]
                for row in granted
            ],
        },
    )

    # Applicable real fault/permission controls run in every one of the ten
    # rounds (previously round 0 only): a real killed child, lease/fencing,
    # revocation, key deactivation, TTL lock wait and replay/current-state
    # negatives, each on round-isolated tasks and credential state.
    record_native(
        "no-atomic-controls-round-" + str(round_id).zfill(2),
        _no_atomic_controls(runtime, round_id),
    )


# ---------------------------------------------------------------------------
# A34-04 real SM2 Bearer stolen-token effect and full denial
# ---------------------------------------------------------------------------


def test_real_sm2_bearer_stolen_token_effect_and_full_denial(baseline_runtime):
    runtime = baseline_runtime
    spec = runtime.task("b34-bearer")
    root = runtime.root("b34-bearer")
    branch = runtime.branches("b34-bearer", root=root)[0]
    bearer = SM2Bearer(runtime.research("Bearer"))
    worker = runtime.worker("Bearer")

    # the genuine holder's own key is NOT needed: possession absent
    setup = bearer.authenticate(
        token=branch.leaf_token,
        body=canonical(runtime.read_body("b34-bearer", key="stolen-setup")),
        now=int(time.time()),
    )
    assert type(setup) is BearerContext and setup.proof is None
    bearer.initialize_path(setup)
    stolen = bearer.invoke(
        token=branch.leaf_token,
        body=canonical(runtime.order_body("b34-bearer", key="stolen-order")),
        now=int(time.time()),
    )
    assert stolen.disposition == "NEW" and stolen.amount_fen == ORDER_AMOUNT
    assert worker.run(stolen.operation_id) == "SUCCEEDED"
    effects = _downstream_rows(runtime.downstream_dsn, [stolen.operation_id])
    assert len(effects) == 1 and effects[0]["amount_fen"] == ORDER_AMOUNT
    record_native(
        "stolen-token-effect",
        {
            "operation": stolen.operation_id,
            "effect": {
                "operation_id": effects[0]["operation_id"],
                "amount_fen": effects[0]["amount_fen"],
                "supplier_id": effects[0]["supplier_id"],
            },
        },
    )

    # full path with the same valid token and no holder key: zero effect
    production, adapter, verifier, _ = runtime.production()
    before = _production_snapshot(runtime.dsn, spec.task_id)
    full_body = runtime.order_body("b34-bearer", key="full-no-key")
    fake_key = generate_sm2_private_key()

    def attempt_full(proof):
        bundle = verifier.verify_bundle(
            branch.leaf_token, proof, body=canonical(full_body), now=int(time.time())
        )
        return adapter.accept(bundle)

    with pytest.raises(VerificationError):
        attempt_full(None)
    with pytest.raises(VerificationError):
        attempt_full(
            sign_ag_proof(
                fake_key,
                kid=runtime.as_actor.registrations[(TENANT, "agent-executor")].kid,
                client_id="agent-executor",
                purpose="invoke",
                endpoint=INVOKE_ENDPOINT,
                body=full_body,
                token=branch.leaf_token,
                now=int(time.time()),
            )
        )
    with pytest.raises(ValueError):
        adapter.accept(object())
    after = _production_snapshot(runtime.dsn, spec.task_id)
    assert before["operations"] == after["operations"]
    assert before["outbox"] == after["outbox"]

    # Bearer negatives: mutated token, wrong type, revoked state, out-of-scope
    # resource dimensions and ignored (never verified) proof.
    neg_root = runtime.root("b34-bearer-neg")
    neg = runtime.branches("b34-bearer-neg", root=neg_root)[0]
    neg_service = runtime.research("Bearer")
    neg_service.initialize_path(
        neg_service.authenticate(
            token=neg.leaf_token,
            body=canonical(runtime.read_body("b34-bearer-neg", key="neg-setup")),
            now=int(time.time()),
        )
    )
    mutated = neg.leaf_token[:-1] + ("A" if neg.leaf_token[-1] != "A" else "B")
    expect_rejected(
        lambda: neg_service.authenticate(
            token=mutated,
            body=canonical(runtime.read_body("b34-bearer-neg", key="neg-mutated")),
            now=int(time.time()),
        ),
        "INVALID_SIGNATURE",
        "INVALID_TOKEN",
    )
    expect_rejected(
        lambda: neg_service.authenticate(
            token=root.id_token,
            body=canonical(runtime.read_body("b34-bearer-neg", key="neg-type")),
            now=int(time.time()),
        ),
        "INVALID_SIGNATURE",
        "INVALID_TOKEN",
    )
    cases = {}
    cases["resource"] = runtime.order_body("b34-bearer-neg", key="neg-resource")
    cases["resource"]["params"]["request_id"] = "unapproved-request"
    cases["quantity"] = runtime.order_body("b34-bearer-neg", key="neg-quantity", quantity=2)
    cases["delivery"] = runtime.order_body("b34-bearer-neg", key="neg-delivery")
    cases["delivery"]["params"]["delivery_id"] = "unapproved-delivery"
    for _name, body in cases.items():
        expect_rejected(
            lambda body=body: neg_service.authenticate(
                token=neg.leaf_token, body=canonical(body), now=int(time.time())
            ),
            "SCOPE_DENIED",
            "RESOURCE_NOT_AUTHORIZED",
        )

    # counter lock: the Bearer accept really waits on the all-ancestor row lock
    lock_root = runtime.root("b34-bearer-lock")
    lock_branch = runtime.branches("b34-bearer-lock", root=lock_root)[0]
    lock_service = runtime.research("Bearer")
    lock_service.initialize_path(
        lock_service.authenticate(
            token=lock_branch.leaf_token,
            body=canonical(runtime.read_body("b34-bearer-lock", key="lock-setup")),
            now=int(time.time()),
        )
    )
    with psycopg.connect(runtime.dsn, connect_timeout=5) as locker:
        locker.execute(
            "SELECT grant_id FROM r34.counters WHERE grant_id=%s FOR UPDATE",
            (lock_branch.leaf_id,),
        )
        blocker = locker.execute("SELECT pg_backend_pid()").fetchone()[0]
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                lambda: lock_service.accept(
                    lock_service.authenticate(
                        token=lock_branch.leaf_token,
                        body=canonical(runtime.order_body("b34-bearer-lock", key="lock-order")),
                        now=int(time.time()),
                    )
                )
            )
            observed = []
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                with psycopg.connect(runtime.dsn, connect_timeout=5) as probe:
                    waiting = probe.execute(
                        "SELECT pid FROM pg_stat_activity WHERE %s=ANY(pg_blocking_pids(pid))",
                        (blocker,),
                    ).fetchall()
                if waiting:
                    observed = [row[0] for row in waiting]
                    break
                if future.done():
                    break
                time.sleep(0.02)
            assert observed, "real Bearer FOR UPDATE wait not observed"
            record_native(
                "bearer-counter-lock",
                {"blocker_backend": blocker, "waiting_backends": observed},
            )
            locker.rollback()
            assert future.result(timeout=10).disposition == "NEW"

    # revoked and key-disabled state refuse fresh accepts after the fact
    with psycopg.connect(runtime.dsn, connect_timeout=5) as conn:
        revoke_grant(conn, neg.mid_id)
    expect_rejected(
        lambda: neg_service.accept(
            neg_service.authenticate(
                token=neg.leaf_token,
                body=canonical(runtime.read_body("b34-bearer-neg", key="neg-revoked")),
                now=int(time.time()),
            )
        ),
        "REVOKED",
    )
    # supplied proof is ignored, not verified: the very same call succeeds and
    # the context still reports absent possession.
    ignored = neg_service.authenticate(
        token=neg.leaf_token,
        body=canonical(runtime.read_body("b34-bearer-neg", key="neg-ignored")),
        now=int(time.time()),
        proof="totally-fake-proof",
    )
    assert type(ignored) is BearerContext and ignored.proof is None
    assert ignored.holder_possession == "NOT_VERIFIED"

    # atomic all-ancestor budget: two 70000 orders admit at most one
    atomic_root = runtime.root("b34-bearer-atomic")
    atomic = runtime.branches("b34-bearer-atomic", root=atomic_root)[0]
    atomic_service = runtime.research("Bearer")
    atomic_service.initialize_path(
        atomic_service.authenticate(
            token=atomic.leaf_token,
            body=canonical(runtime.read_body("b34-bearer-atomic", key="atomic-setup")),
            now=int(time.time()),
        )
    )
    barrier = Barrier(2)

    def atomic_accept(key):
        body = canonical(runtime.order_body("b34-bearer-atomic", key=key))
        barrier.wait(timeout=10)
        try:
            answer = atomic_service.accept(
                atomic_service.authenticate(
                    token=atomic.leaf_token, body=body, now=int(time.time())
                )
            )
            return (key, "NEW", answer.operation_id)
        except ResearchError as exc:
            return (key, "REJECTED", exc.code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(atomic_accept, ("atomic-a", "atomic-b")))
    kinds = sorted(kind for _, kind, _ in outcomes)
    assert kinds == ["NEW", "REJECTED"]
    assert [value for _, kind, value in outcomes if kind == "REJECTED"] == ["BUDGET_EXCEEDED"]
    winner_key, _, winner = next(
        (key, kind, value) for key, kind, value in outcomes if kind == "NEW"
    )
    record_native("bearer-atomic-pair", {"outcomes": outcomes})

    # same business key stays idempotent for Bearer: one effect, no second
    # reservation, while proof replay is honestly NOT_APPLICABLE.
    repeat = atomic_service.accept(
        atomic_service.authenticate(
            token=atomic.leaf_token,
            body=canonical(runtime.order_body("b34-bearer-atomic", key=winner_key)),
            now=int(time.time()),
        )
    )
    assert repeat.disposition == "EXISTING" and repeat.operation_id == winner
    record_native(
        "bearer-summary",
        {
            "stolen_operation": stolen.operation_id,
            "atomic": outcomes,
            "negatives": "mutated/type/scope/quantity/delivery/revoked rejected",
        },
    )
