"""Real AS-issued authorization and persistent scenario refusal/recovery probes.

These tests use fresh owned PostgreSQL namespaces and native HTTPS services.
The distinct-UID holder/IPC deployment is additionally exercised by the clean
assembly suite; this file never constructs a VerifiedInvocation or signed token.
"""

from __future__ import annotations

import copy
import io
import multiprocessing
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from threading import Barrier

import psycopg
import pytest

from agent_guard.audit.client import AuditClient, AuditUnavailable
from agent_guard.audit.delivery import DeliveryWorker, confirm_registered_tx
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.contracts.ledger import INVOKE_ENDPOINT
from agent_guard.crypto.sm import verify_compact_jws
from agent_guard.demo.faults import CommittedBoundary, kill_marked_process
from agent_guard.demo.holder import (
    TOOLS,
    capacity_workload,
    invocation_body,
    workload_skus,
)
from agent_guard.execution import receipt_publication as publication
from agent_guard.execution import store as execution_store
from agent_guard.execution.store import fetch_lease
from tests.fixtures.receipts import publication_only, receipt_services
from tests.integration.test_gateway_tls import signed_request

pytestmark = pytest.mark.integration
pytest_plugins = ("tests.fixtures.a31_joint",)


_ORACLE_AUDIT_DSNS = {}
_ORACLE_AUDIT_STATES = {}
_ORACLE_DOMAIN_BINDINGS = {}


def _snapshot_tables(conn, prefix, domain):
    from psycopg import sql

    from tests.fixtures.a31_audit_service import record_native

    metadata_sql = (
        "SELECT current_setting('transaction_isolation'), "
        "current_setting('transaction_read_only'), pg_backend_pid(), "
        "txid_current_snapshot()::text, current_schema(), current_database(), "
        "clock_timestamp()::text, current_user, inet_server_addr()::text, "
        "inet_server_port()"
    )
    metadata = conn.execute(metadata_sql).fetchone()
    assert metadata[0:2] == ("repeatable read", "on")
    binding = _ORACLE_DOMAIN_BINDINGS[(domain, conn.info.dbname)]
    assert metadata[4:6] == (binding["schema"], binding["database"])
    assert metadata[7] == binding["user"] and conn.info.host == binding["host"]
    if domain == "downstream":
        from tests.fixtures.isolation import DOWNSTREAM_DB_RE

        assert binding["created"] and DOWNSTREAM_DB_RE.fullmatch(binding["database"])
        assert binding["schema"] == "public"
    else:
        assert binding["schema"] != "public"
        marker = conn.execute("SELECT run_id, database_name FROM ag_test_ownership").fetchall()
        assert marker == [(binding["run_id"], binding["database"])]
    inventory_sql = (
        "SELECT tablename FROM pg_tables WHERE schemaname=current_schema() "
        "AND starts_with(tablename,%s) ORDER BY tablename"
    )
    names = [row[0] for row in conn.execute(inventory_sql, (prefix,)).fetchall()]
    required = {
        "authority": {
            "ag_tasks",
            "ag_grants",
            "ag_operations",
            "ag_proofs",
            "ag_ledger_events",
            "ag_ledger_event_nodes",
            "ag_execution_leases",
            "ag_receipt_outbox",
            "ag_audit_records",
        },
        "downstream": {"ds_operations", "ds_orders", "ds_notifications"},
        "audit": {
            "ag_checkpoint_streams",
            "ag_checkpoint_records",
            "ag_audit_checkpoint_keys",
            "ag_checkpoints",
            "ag_checkpoint_batches",
            "ag_audit_principals",
        },
    }[domain]
    assert names and required <= set(names)
    rows = {
        name: conn.execute(
            sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY row_to_json(t)::text").format(
                sql.Identifier(name)
            )
        ).fetchall()
        for name in names
    }
    record_native(
        "s1-rr-read-only-full-domain",
        {
            "domain": domain,
            "owned_target_binding": binding,
            "begin": "BEGIN; SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",
            "metadata_sql": metadata_sql,
            "metadata": metadata,
            "inventory_sql": inventory_sql,
            "prefix": prefix,
            "inventory": names,
            "row_sql": (
                "SELECT row_to_json(t)::text FROM <quoted table> t ORDER BY row_to_json(t)::text"
            ),
            "row_shape": "list[tuple[str]]; original row_to_json all columns",
            "tables": rows,
        },
    )
    return rows


def _audit_snapshot(dsn):
    with psycopg.connect(_ORACLE_AUDIT_DSNS[dsn]) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return _snapshot_tables(conn, "ag_", "audit")


def full_state(dsn, downstream_dsn):
    result = {}
    for label, target, prefix, domain in (
        ("gateway", dsn, "ag_", "authority"),
        ("downstream", downstream_dsn, "ds_", "downstream"),
    ):
        with psycopg.connect(target) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            result[label] = _snapshot_tables(conn, prefix, domain)
    # Independent domain transactions; preserve the original two-key return shape.
    _ORACLE_AUDIT_STATES[id(result)] = (result, _audit_snapshot(dsn))
    return result


def _owned_as_popen(original):
    """Keep the caller's native AS session bounded, including emulator descendants."""
    import os
    import signal

    from tests.fixtures.a31_audit_service import record_native

    launched = []

    class OwnedAS(original):
        def __init__(self, args, *positional, **kwargs):
            kwargs["start_new_session"] = True
            super().__init__(args, *positional, **kwargs)
            self.owned_session = os.getsid(self.pid)
            self.owned_group = os.getpgid(self.pid)
            assert self.owned_session == self.owned_group == self.pid
            self.owned_argv = list(args)
            launched.append(self)

        def members(self):
            rows = []
            for directory in Path("/proc").iterdir():
                if not directory.name.isdigit():
                    continue
                try:
                    raw = (directory / "stat").read_text()
                    tail = raw[raw.rfind(")") + 2 :].split()
                    if int(tail[2]) != self.owned_group:
                        continue
                    assert int(tail[3]) == self.owned_session
                    command = (directory / "cmdline").read_bytes()
                    if tail[0] != "Z":
                        assert b"agent_guard.server" in command
                    rows.append(
                        {
                            "pid": int(directory.name),
                            "state": tail[0],
                            "start_ticks": tail[19],
                            "argv_hex": command.hex(),
                            "pgid": int(tail[2]),
                            "session": int(tail[3]),
                        }
                    )
                except FileNotFoundError:
                    continue
            return rows

        def terminate(self):
            rows = self.members()
            record_native(
                "s1-owned-as-session-before-stop",
                {
                    "pid": self.pid,
                    "pgid": self.owned_group,
                    "session": self.owned_session,
                    "argv": self.owned_argv,
                    "members": rows,
                },
            )
            if rows:
                os.killpg(self.owned_group, signal.SIGTERM)

        def communicate(self, *args, **kwargs):
            result = super().communicate(*args, **kwargs)
            rows = self.members()
            if any(row["state"] != "Z" for row in rows):
                os.killpg(self.owned_group, signal.SIGKILL)
            deadline = time.monotonic() + 10
            while any(row["state"] != "Z" for row in self.members()):
                assert time.monotonic() < deadline, "owned AS descendants did not exit"
                time.sleep(0.01)
            record_native(
                "s1-owned-as-session-stop",
                {
                    "pid": self.pid,
                    "pgid": self.owned_group,
                    "session": self.owned_session,
                    "native_exit": self.returncode,
                    "members_before_reap": rows,
                    "live_members_after": [],
                    "remaining_zombies": self.members(),
                },
            )
            return result

    def launch(args, *positional, **kwargs):
        if isinstance(args, (list, tuple)) and list(args[1:4]) == [
            "-m",
            "agent_guard.server",
            "run",
        ]:
            return OwnedAS(args, *positional, **kwargs)
        return original(args, *positional, **kwargs)

    launch.owned_processes = launched
    return launch


@pytest.fixture(autouse=True)
def owned_as_lifecycle(monkeypatch):
    import subprocess

    launch = _owned_as_popen(subprocess.Popen)
    monkeypatch.setattr(subprocess, "Popen", launch)
    try:
        yield
    finally:
        for child in launch.owned_processes:
            if child.poll() is None or any(row["state"] != "Z" for row in child.members()):
                child.terminate()
            child.communicate(timeout=15)


@pytest.fixture
def scene(
    ledger,
    dsn,
    downstream_dsn,
    namespace,
    downstream_db,
    tmp_path,
    tmp_path_factory,
    monkeypatch,
    request,
):
    from agent_guard.authorization import provisioning
    from tests.fixtures.a31_joint import joint_context
    from tests.integration import test_exchange_service as exchange
    from tests.integration.test_audit_tls import service_tls

    register_policy = provisioning.register_task_policy
    form = exchange._form
    from tests.fixtures import execution as execution_fixture

    build_catalog = execution_fixture.build_catalog
    budget_variant = (
        getattr(request.node, "callspec", None) is not None
        and request.node.callspec.params.get("case") == "mid-money"
    )

    def scenario_catalog(tenant_id, task_id):
        catalog = build_catalog(tenant_id, task_id)
        if budget_variant:
            from agent_guard.tools.catalog import CatalogQuote, CatalogQuoteLine

            catalog.replace_quote(
                CatalogQuote(
                    "quote-001",
                    "1",
                    "supplier-001",
                    "req-001",
                    (
                        CatalogQuoteLine("sku-001", 1, 70000),
                        CatalogQuoteLine("sku-small", 1, 20000),
                    ),
                )
            )
        return catalog

    def scenario_policy(conn, **kwargs):
        # Trusted input to the existing task-policy API, before any root exists.
        kwargs["call_limit"] = 12
        if budget_variant:
            kwargs["constraints"] = copy.deepcopy(kwargs["constraints"])
            kwargs["constraints"]["skus"].append("sku-small")
        return register_policy(conn, **kwargs)

    def scenario_delegation(as_key, token, **kwargs):
        parent_claims = verify_compact_jws(
            token,
            expected_type="ag-at+jwt",
            trusted_keys={"as-sign-1": as_key.public_key()},
        )
        kwargs["ttl"] = min(
            240 if kwargs.get("recipient", "selector") == "selector" else 180,
            parent_claims["exp"] - int(time.time()),
        )
        request = form(as_key, token, **kwargs)
        request["ag_call_limit"] = (
            "10" if request["ag_delegate_client_id"] == "agent-selector" else "8"
        )
        constraints = load_strict_json(request["ag_constraints"].encode())
        constraints["max_quantity"] = 1
        request["ag_constraints"] = canonical_json_bytes(constraints).decode()
        return request

    tls = service_tls.__wrapped__(tmp_path_factory)
    with monkeypatch.context() as patch:
        patch.setattr(execution_fixture, "build_catalog", scenario_catalog)
        patch.setattr(provisioning, "register_task_policy", scenario_policy)
        patch.setattr(exchange, "_form", scenario_delegation)
        with joint_context(dsn, downstream_dsn, tmp_path / "scenario-native", tls) as f:
            # Remote operator CLI has committed stream/key and scoped principals.
            with psycopg.connect(f.audit_namespace.dsn) as remote:
                assert remote.execute(
                    "SELECT count(*) FROM ag_checkpoint_streams WHERE stream_id=%s",
                    (f.descriptor.scope.stream_id,),
                ).fetchone() == (1,)
                assert remote.execute(
                    "SELECT count(*) FROM ag_audit_principals WHERE stream_id=%s",
                    (f.descriptor.scope.stream_id,),
                ).fetchone() == (2,)
            with psycopg.connect(f.gateway_dsn) as local:
                assert confirm_registered_tx(local, descriptor=f.descriptor)
            from psycopg.conninfo import conninfo_to_dict

            from tests.fixtures.isolation import assert_owned

            assert_owned(namespace)
            assert_owned(f.audit_namespace)
            assert downstream_db.created and downstream_db.dsn == downstream_dsn
            bindings = []
            for domain, target, allocation in (
                ("authority", dsn, namespace),
                ("downstream", downstream_dsn, downstream_db),
                ("audit", f.audit_namespace.dsn, f.audit_namespace),
            ):
                info = conninfo_to_dict(target)
                binding = {
                    "database": info["dbname"],
                    "host": info["host"],
                    "user": info["user"],
                    "schema": "public" if domain == "downstream" else allocation.schema,
                    "created": allocation.created if domain == "downstream" else True,
                    "run_id": None if domain == "downstream" else allocation.run_id,
                }
                assert binding["database"] == (
                    allocation.name if domain == "downstream" else allocation.database
                )
                key = (domain, binding["database"])
                _ORACLE_DOMAIN_BINDINGS[key] = binding
                bindings.append(key)
            _ORACLE_AUDIT_DSNS[f.gateway_dsn] = f.audit_namespace.dsn
            try:
                yield f
            finally:
                _ORACLE_AUDIT_DSNS.pop(f.gateway_dsn)
                _ORACLE_AUDIT_STATES.clear()
                for key in bindings:
                    _ORACLE_DOMAIN_BINDINGS.pop(key)


def _business(state):
    names = {
        "ag_grants",
        "ag_tasks",
        "ag_operations",
        "ag_operation_evidence",
        "ag_ledger_events",
        "ag_ledger_event_nodes",
        "ag_event_seals",
        "ag_execution_leases",
        "ag_receipt_outbox",
        "ag_audit_records",
        "ag_audit_streams",
        "ag_audit_delivery",
        "ag_audit_delivery_batches",
    }
    return {
        "gateway": {k: v for k, v in state["gateway"].items() if k in names},
        "downstream": state["downstream"],
        "audit": _ORACLE_AUDIT_STATES[id(state)][1],
    }


def _effects(state):
    value = _business(state)
    value["gateway"] = {
        name: rows
        for name, rows in value["gateway"].items()
        if not name.startswith("ag_audit_") and name != "ag_operation_evidence"
    }
    return value


def _body(f, tool, *, key, order=None):
    value = invocation_body("task-001", tool, idempotency_key=key, order_operation_id=order)
    if tool == TOOLS[3]:
        value["params"]["recipient_id"] = "user-demo-001"
    return value


def _accept(f, body, *, proof=None, holder="executor", token=None):
    status, response, _ = signed_request(
        f.env if token is None else replace(f.env, token=token),
        f.gateway_port,
        f.gateway_context,
        body,
        proof_override=proof,
        holder=holder,
    )
    return status, response


def _counts(f):
    with psycopg.connect(f.gateway_dsn) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        counters = conn.execute(
            "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled "
            "FROM ag_grants ORDER BY depth"
        ).fetchall()
        operations = conn.execute(
            "SELECT operation_id,status,amount_fen FROM ag_operations ORDER BY operation_id"
        ).fetchall()
        events = conn.execute(
            "SELECT operation_id,phase FROM ag_ledger_events ORDER BY event_id"
        ).fetchall()
        outboxes = conn.execute("SELECT count(*) FROM ag_receipt_outbox").fetchone()[0]
        _snapshot_tables(conn, "ag_", "authority")
    with psycopg.connect(f.downstream_dsn) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        effects = conn.execute("SELECT count(*) FROM ds_operations").fetchone()[0]
        _snapshot_tables(conn, "ds_", "downstream")
    _audit_snapshot(f.gateway_dsn)
    return counters, operations, events, outboxes, effects


def _publisher(f):
    return receipt_services(
        f.env, f.gateway_dsn, gateway_key=f.receipt_key, signing_kid="joint-receipt-1"
    )[2]


def _query(f, operation):
    body = {"profile": "GM-MVP-1", "task_id": "task-001", "operation_id": operation}
    return signed_request(f.env, f.gateway_port, f.gateway_context, body, query=True)


def _export(f, client, directory, *, expected_tail=0, pin_mode="LATEST_OBSERVATION"):
    from agent_guard.audit.checkpoint import verify_checkpoint
    from agent_guard.evidence.export import materialize_task_export
    from agent_guard.evidence.task_bundle import load_checkpoint_history
    from agent_guard.evidence.task_verify import load_public_trust, verify_task_bundle
    from tests.fixtures.a32_export import readonly_export_factory
    from tests.fixtures.a32_joint import public_task_trust

    latest = client.latest(f.descriptor.scope.stream_id)
    checkpoint = verify_checkpoint(latest, trust=(f.trust,), expected_scope=f.descriptor.scope)
    pin = {
        "mode": pin_mode,
        "checkpoint_jws": latest if pin_mode != "UNKNOWN" else None,
        "observed_at": int(time.time()) if pin_mode != "UNKNOWN" else None,
        "scope": asdict(f.descriptor.scope),
    }
    page = client.history(
        f.descriptor.scope.stream_id,
        observed_checkpoint_id=checkpoint.claims.checkpoint_id,
        after_sequence=0,
    )
    assert page.next_after_sequence is None and page.checkpoints[-1] == latest
    trust = load_public_trust(
        public_task_trust(
            f.env,
            f.descriptor.scope,
            f.descriptor,
            (f.trust,),
            f.receipt_key,
            signing_kid="joint-receipt-1",
        )
    )
    raw_history = b"".join(
        canonical_json_bytes({"checkpoint_jws": cp}) + b"\n" for cp in page.checkpoints
    )
    directory.mkdir(mode=0o700)
    history_path = directory / "history.ndjson"
    history_path.write_bytes(raw_history)
    history_path.chmod(0o444)
    with history_path.open("rb") as stream:
        history = load_checkpoint_history(stream, external_trust=trust, external_pin=pin)
    before = full_state(f.gateway_dsn, f.downstream_dsn)
    with readonly_export_factory(f.gateway_dsn) as factory:
        spool = materialize_task_export(
            factory,
            f.descriptor.scope,
            pin,
            directory,
            external_checkpoint_history=history,
        )
        try:
            raw = Path(spool.path).read_bytes()
            report = verify_task_bundle(io.BytesIO(raw), trust, pin)
            assert report.cryptographic_consistency == "VERIFIED" and (
                expected_tail is None or report.tail == expected_tail
            )
            assert report.current_auth == "UNKNOWN"
            assert report.downstream_truth == "ATTESTED_NOT_INDEPENDENTLY_PROVEN"
        finally:
            spool.cleanup()
    assert full_state(f.gateway_dsn, f.downstream_dsn) == before
    from tests.fixtures.a31_audit_service import record_native

    record_native(
        "a33-export-original",
        {
            "bundle": raw,
            "external_trust": public_task_trust(
                f.env,
                f.descriptor.scope,
                f.descriptor,
                (f.trust,),
                f.receipt_key,
                signing_kid="joint-receipt-1",
            ),
            "external_pin": pin,
            "checkpoint_history": raw_history,
            "report": asdict(report),
        },
    )
    return raw, trust, pin, report


def _delivery_binding(f, client):
    from agent_guard.contracts.encoding import b64url_encode
    from tests.fixtures.a31_joint import JointDeliveryBinding, private_json

    class RegisteredDelivery(JointDeliveryBinding):
        def __init__(self):
            self.runtime = f
            self.directory = f.private / "scenario-delivery"
            self.directory.mkdir(mode=0o700)
            self.config = private_json(
                self.directory / "config.json",
                {
                    "origin": "https://localhost:" + str(f.audit_port),
                    "ca_file": str(f.audit_tls / "ca.pem"),
                    "writer_credential": "joint-writer:" + f.writer_token,
                    "reader_credential": "joint-reader:" + f.reader_token,
                    "trust": [{**asdict(f.trust), "spki_der": b64url_encode(f.trust.spki_der)}],
                },
            )
            self.client = client
            self.worker = DeliveryWorker(self.connect, client, trust=(f.trust,))
            self.replacement = None
            self.release = self.directory / "release"
            # scene already confirmed original descriptor after remote commit.
            with self.connect() as conn:
                assert conn.execute(
                    "SELECT registration_state FROM ag_audit_delivery WHERE stream_id=%s",
                    (f.descriptor.scope.stream_id,),
                ).fetchone() == ("REGISTERED",)

    return RegisteredDelivery()


def _wait_marker(path, process):
    deadline = time.monotonic() + 10
    while not path.exists():
        assert process.is_alive(), "fault child exited before its committed boundary"
        assert time.monotonic() < deadline, "finite committed-boundary wait"
        time.sleep(0.01)
    return load_strict_json(path.read_bytes())


def _wait_lease(f, operation):
    deadline = time.monotonic() + 40
    while True:
        with psycopg.connect(f.gateway_dsn) as conn:
            row = fetch_lease(conn, operation)
            now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
        assert row is not None
        if now >= row[2]:
            return row
        assert time.monotonic() < deadline, "original 30 second lease did not expire"
        time.sleep(0.1)


def _double_code(f, config, bundle, port, context, round_id):
    import base64
    import http.client
    import secrets
    from datetime import datetime, timedelta, timezone
    from http.cookies import SimpleCookie
    from urllib.parse import parse_qs, urlencode, urlsplit

    from agent_guard.authorization.oidc import pkce_s256_challenge, verify_id_token
    from agent_guard.authorization.provisioning import (
        register_task_policy,
        register_user,
    )
    from agent_guard.demo.client import _Inputs
    from tests.fixtures.a31_audit_service import record_native

    task = f"task-code-race-{round_id}"
    subject = f"user-code-race-{round_id}"
    password = secrets.token_urlsafe(36)
    with psycopg.connect(f.gateway_dsn) as conn:
        register_user(conn, tenant_id="tenant-001", subject=subject, password=password)
        register_task_policy(
            conn,
            tenant_id="tenant-001",
            task_id=task,
            owner_subject=subject,
            scope="openid " + " ".join(TOOLS),
            constraints=f.as_material["claims"][0]["ag_constraints"],
            amount_limit_fen=100000,
            call_limit=12,
            task_expires_at=datetime.now(timezone.utc) + timedelta(seconds=600),
        )

    def request(method, path, body=None, headers=None):
        connection = http.client.HTTPSConnection("localhost", port, context=context, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return (
                response.status,
                dict((k.lower(), v) for k, v in response.getheaders()),
                response.read(),
            )
        finally:
            connection.close()

    status, headers, raw = request("GET", "/ag/login")
    assert status == 200
    cookie = SimpleCookie()
    cookie.load(headers["set-cookie"])
    csrf = cookie["ag_login_csrf"].value
    status, headers, _ = request(
        "POST",
        "/ag/login",
        urlencode(
            dict(
                tenant_id="tenant-001",
                subject=subject,
                password=password,
                csrf_token=csrf,
                return_to="/dashboard",
            )
        ),
        {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": "ag_login_csrf=" + csrf,
        },
    )
    assert status == 303
    cookie = SimpleCookie()
    cookie.load(headers["set-cookie"])
    session = cookie["ag_session"].value
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    redirect = config.clients["agent-planner"].redirect_uri
    authorize = dict(
        response_type="code",
        client_id="agent-planner",
        redirect_uri=redirect,
        scope="openid " + " ".join(TOOLS),
        state=state,
        nonce=nonce,
        code_challenge=pkce_s256_challenge(verifier),
        code_challenge_method="S256",
        ag_task_id=task,
    )
    status, _, raw = request(
        "GET",
        "/oauth/authorize?" + urlencode(authorize),
        headers={"Cookie": "ag_session=" + session},
    )
    assert status == 200
    fields = _Inputs(raw).values
    assert set(fields) == {"request_id", "csrf_token"}
    status, headers, _ = request(
        "POST",
        "/ag/consent",
        urlencode(dict(fields, decision="approve")),
        {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": "ag_session=" + session,
        },
    )
    assert status == 303
    query = parse_qs(urlsplit(headers["location"]).query, strict_parsing=True)
    assert query["state"] == [state]
    form = dict(
        grant_type="authorization_code",
        code=query["code"][0],
        redirect_uri=redirect,
        code_verifier=verifier,
    )
    registration = f.env.registrations[("tenant-001", "agent-planner")]
    proofs = [
        sign_ag_proof(
            f.env.keys["planner"],
            kid=registration.kid,
            client_id="agent-planner",
            purpose="code-exchange",
            endpoint=config.issuer + "/oauth/token",
            body=form,
            token=None,
            now=int(time.time()),
        )
        for _ in range(2)
    ]
    basic = (
        "Basic "
        + base64.b64encode(
            ("agent-planner:" + bundle.client_secrets["agent-planner"]).encode()
        ).decode()
    )
    barrier = Barrier(2)

    def redeem(index):
        barrier.wait(timeout=5)
        return request(
            "POST",
            "/oauth/token",
            urlencode(form),
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": basic,
                "AG-Proof": proofs[index],
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(redeem, (0, 1)))
    assert sorted(status for status, _, _ in results) == [200, 400] or sorted(
        status for status, _, _ in results
    ) == [200, 401]
    success = load_strict_json(next(raw for status, _, raw in results if status == 200))
    claims = verify_id_token(
        success["id_token"],
        trusted_keys={"as-sign-1": f.env.as_key.public_key()},
        issuer=config.issuer,
        client_id="agent-planner",
        expected_nonce=nonce,
        now=int(time.time()),
    )
    assert claims["sub"] == subject
    with psycopg.connect(f.gateway_dsn) as conn:
        assert conn.execute(
            "SELECT count(*) FROM ag_grants WHERE task_id=%s", (task,)
        ).fetchone() == (1,)
        assert conn.execute(
            "SELECT count(*) FROM ag_auth_evidence e "
            "JOIN ag_authorization_codes c USING(code_sha256) WHERE c.task_id=%s",
            (task,),
        ).fetchone() == (1,)
    record_native(
        "a33-double-code",
        {
            "round": round_id,
            "statuses": [status for status, _, _ in results],
            "task_id": task,
            "two_connections": True,
        },
    )


def _as_refusal(
    f,
    attack,
    round_id,
    *,
    parent_token=None,
    holder="planner",
    recipient="selector",
    amount=None,
):
    import base64
    import hashlib
    import http.client
    import os
    import secrets
    import socket
    import ssl
    import subprocess
    import sys
    from urllib.parse import urlencode

    from agent_guard.server.config import (
        load_secrets,
        load_server_config,
        resolve_paths,
    )
    from agent_guard.server.private_files import read_private_file
    from tests.fixtures.a31_audit_service import record_native
    from tests.integration.test_exchange_service import _form

    directory = f.private / "as"
    config_path = directory / "config.json"
    config = resolve_paths(load_server_config(read_private_file(config_path)), directory)
    bundle = load_secrets(read_private_file(config.secrets_path))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    context = ssl.create_default_context(cafile=str(directory / "tls-cert.pem"))
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
        str(directory / "tls-cert.pem"),
        "--ssl-keyfile",
        str(directory / "tls-key.pem"),
    ]
    process = subprocess.Popen(
        args,
        env=dict(os.environ, AGENT_GUARD_DATABASE_URL=f.gateway_dsn),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        before = full_state(f.gateway_dsn, f.downstream_dsn)
        deadline = time.monotonic() + 10
        while True:
            assert process.poll() is None
            try:
                connection = http.client.HTTPSConnection(
                    "localhost", port, context=context, timeout=5
                )
                connection.request("GET", "/.well-known/openid-configuration")
                assert connection.getresponse().status == 200
                connection.close()
                break
            except OSError:
                assert time.monotonic() < deadline
                time.sleep(0.02)
        if attack == "code-race":
            _double_code(f, config, bundle, port, context, round_id)
            return
        token = parent_token or f.as_material["tokens"][0]
        form = _form(
            f.env.as_key,
            token,
            recipient=recipient,
            delegation_key=secrets.token_urlsafe(32),
        )
        if amount is not None:
            form["ag_amount_limit_fen"] = str(amount)
        form["scope"] = " ".join(TOOLS)
        if not attack.startswith("branch"):
            positive_registration = f.env.registrations[("tenant-001", "agent-" + holder)]
            positive_proof = sign_ag_proof(
                f.env.keys[holder],
                kid=positive_registration.kid,
                client_id="agent-" + holder,
                purpose="delegate",
                endpoint=config.issuer + "/oauth/token",
                body=form,
                token=token,
                now=int(time.time()),
            )
            positive_basic = (
                "Basic "
                + base64.b64encode(
                    ("agent-" + holder + ":" + bundle.client_secrets["agent-" + holder]).encode()
                ).decode()
            )
            positive_connection = http.client.HTTPSConnection(
                "localhost", port, context=context, timeout=5
            )
            try:
                positive_connection.request(
                    "POST",
                    "/oauth/token",
                    body=urlencode(form),
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Authorization": positive_basic,
                        "AG-Proof": positive_proof,
                    },
                )
                positive_response = positive_connection.getresponse()
                positive_raw = positive_response.read()
                assert positive_response.status == 200
            finally:
                positive_connection.close()
            record_native(
                "a33-as-positive-control",
                {
                    "case": attack,
                    "round": round_id,
                    "pid": process.pid,
                    "status": 200,
                    "response_sha256": hashlib.sha256(positive_raw).hexdigest(),
                },
            )
            form["ag_delegation_key"] = secrets.token_urlsafe(32)
            before = full_state(f.gateway_dsn, f.downstream_dsn)
        if attack == "amount":
            form["ag_amount_limit_fen"] = "100001"
        elif attack == "calls":
            form["ag_call_limit"] = "13"
        elif attack == "ttl":
            form["ag_ttl_seconds"] = "301"
        elif attack == "depth":
            form["ag_delegation_remaining"] = "2"
        elif attack == "scope":
            form["scope"] += " unauthorized.tool"
        elif attack == "audience":
            form["audience"] = "https://other.invalid"
        elif attack == "recipient":
            form["ag_delegate_client_id"] = "unregistered"
        elif attack == "resource":
            constraints = load_strict_json(form["ag_constraints"].encode())
            constraints["request_ids"].append("unapproved")
            form["ag_constraints"] = canonical_json_bytes(constraints).decode()
        if attack in ("parent-revoked", "key-revoked"):
            from agent_guard.ledger.provisioning import (
                deactivate_principal,
                revoke_grant,
            )

            with psycopg.connect(f.gateway_dsn) as conn:
                if attack == "parent-revoked":
                    revoke_grant(
                        conn,
                        verify_compact_jws(
                            token,
                            expected_type="ag-at+jwt",
                            trusted_keys={"as-sign-1": f.env.as_key.public_key()},
                        )["ag_grant_id"],
                    )
                else:
                    deactivate_principal(
                        conn,
                        tenant_id="tenant-001",
                        client_id="agent-" + holder,
                        kid=f.env.registrations[("tenant-001", "agent-" + holder)].kid,
                    )
            before = full_state(f.gateway_dsn, f.downstream_dsn)
        registration = f.env.registrations[("tenant-001", "agent-" + holder)]
        proof = sign_ag_proof(
            f.env.keys["executor" if attack == "key" else holder],
            kid=registration.kid,
            client_id="agent-" + holder,
            purpose="delegate",
            endpoint=config.issuer + "/oauth/token",
            body=form,
            token=token,
            now=int(time.time())
            - (61 if attack == "proof-expired" else 58 if attack == "proof-lock" else 0),
        )
        secret = "incorrect" if attack == "basic" else bundle.client_secrets["agent-" + holder]
        basic = "Basic " + base64.b64encode(("agent-" + holder + ":" + secret).encode()).decode()

        send_observation = {}

        def send_form():
            send_proof = proof
            if attack.startswith("branch"):
                parent_claims = verify_compact_jws(
                    token,
                    expected_type="ag-at+jwt",
                    trusted_keys={"as-sign-1": f.env.as_key.public_key()},
                )
                send_now = int(time.time())
                remaining = parent_claims["exp"] - send_now
                assert remaining > 1
                form["ag_ttl_seconds"] = str(min(int(form["ag_ttl_seconds"]), remaining - 1))
                send_observation.update(
                    parent_iat=parent_claims["iat"],
                    parent_exp=parent_claims["exp"],
                    proof_iat=send_now,
                    proof_exp=send_now + 60,
                    ttl_computed_at=time.time(),
                )
                send_proof = sign_ag_proof(
                    f.env.keys[holder],
                    kid=registration.kid,
                    client_id="agent-" + holder,
                    purpose="delegate",
                    endpoint=config.issuer + "/oauth/token",
                    body=form,
                    token=token,
                    now=send_now,
                )
            connection = http.client.HTTPSConnection("localhost", port, context=context, timeout=5)
            try:
                send_observation["https_request_at"] = time.time()
                connection.request(
                    "POST",
                    "/oauth/token",
                    body=urlencode(form),
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Authorization": basic,
                        "AG-Proof": send_proof,
                    },
                )
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()

        if attack == "proof-lock":
            with psycopg.connect(f.gateway_dsn) as lock:
                lock.execute(
                    "SELECT grant_id FROM ag_grants WHERE grant_id=%s FOR UPDATE",
                    (f.as_material["claims"][0]["ag_grant_id"],),
                ).fetchone()
                blocker = lock.execute("SELECT pg_backend_pid()").fetchone()[0]
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(send_form)
                    deadline = time.monotonic() + 5
                    while True:
                        with psycopg.connect(f.gateway_dsn) as probe:
                            waiting = probe.execute(
                                "SELECT pid FROM pg_stat_activity "
                                "WHERE %s=ANY(pg_blocking_pids(pid))",
                                (blocker,),
                            ).fetchall()
                        if waiting:
                            break
                        if future.done() or time.monotonic() >= deadline:
                            lock.rollback()
                            pytest.fail("actual AS root-lock proof wait absent")
                        time.sleep(0.01)
                    time.sleep(2.1)
                    db_clock = lock.execute(
                        "SELECT extract(epoch FROM clock_timestamp())"
                    ).fetchone()[0]
                    lock.commit()
                    status, raw = future.result(timeout=5)
            record_native(
                "a33-as-proof-final-clock",
                {
                    "round": round_id,
                    "as_pid": process.pid,
                    "blocker": blocker,
                    "waiting": waiting,
                    "db_clock": str(db_clock),
                    "status": status,
                    "response_sha256": hashlib.sha256(raw).hexdigest(),
                },
            )
        else:
            status, raw = send_form()
        if attack.startswith("branch"):
            record_native(
                "a33-branch-actual-response",
                {
                    "case": attack,
                    "round": round_id,
                    "status": status,
                    "response_utf8": raw.decode("utf-8"),
                    "requested_ttl": form["ag_ttl_seconds"],
                    "observed_at": time.time(),
                    "send_observation": send_observation,
                },
            )
            assert status == 200
            child = load_strict_json(raw)["access_token"]
            claims = verify_compact_jws(
                child,
                expected_type="ag-at+jwt",
                trusted_keys={"as-sign-1": f.env.as_key.public_key()},
            )
            record_native(
                "a33-branch-issued",
                {
                    "case": attack,
                    "pid": process.pid,
                    "parent": claims["ag_parent_id"],
                    "grant": claims["ag_grant_id"],
                    "exp": claims["exp"],
                },
            )
            return child, claims
        assert status in (400, 401, 403)
        assert _business(full_state(f.gateway_dsn, f.downstream_dsn)) == _business(before)
        record_native(
            "a33-as-refusal",
            {
                "case": attack,
                "round": round_id,
                "pid": process.pid,
                "status": status,
                "response_sha256": hashlib.sha256(raw).hexdigest(),
            },
        )
    finally:
        process.terminate()
        stdout, stderr = process.communicate(timeout=10)
        record_native(
            "a33-as-refusal-stop",
            {
                "pid": process.pid,
                "returncode": process.returncode,
                "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
            },
        )


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize(
    "case",
    (
        "positive",
        "basic",
        "key",
        "amount",
        "calls",
        "ttl",
        "depth",
        "scope",
        "audience",
        "recipient",
        "resource",
        "proof-expired",
        "key-revoked",
        "parent-revoked",
        "proof-lock",
        "code-race",
    ),
)
def test_browser_root_and_two_delegations_real_https(scene, round_id, case):
    f = scene
    claims = f.as_material["claims"]
    assert f.as_material["native_as_stopped"]
    assert f.as_material["as_pid"] > 0
    assert [c["client_id"] for c in claims] == [
        "agent-planner",
        "agent-selector",
        "agent-executor",
    ]
    assert claims[0]["ag_parent_id"] is None
    assert claims[1]["ag_parent_id"] == claims[0]["ag_grant_id"]
    assert claims[2]["ag_parent_id"] == claims[1]["ag_grant_id"]
    assert all(c["ag_root_id"] == claims[0]["ag_grant_id"] for c in claims)
    assert [c["ag_limits"]["amount_fen"] for c in claims] == [100000, 80000, 70000]
    assert [c["ag_delegation_remaining"] for c in claims] == [2, 1, 0]
    assert [c["ag_limits"]["calls"] for c in claims] == [12, 10, 8]
    assert claims[1]["exp"] - claims[1]["iat"] <= 240
    assert claims[2]["exp"] - claims[2]["iat"] <= 180
    assert claims[2]["exp"] <= claims[1]["exp"] <= claims[0]["exp"]
    assert [
        (r["method"], r["status"]) for r in f.as_material["calls"] if r["path"] == "/oauth/token"
    ] == [("POST", 200)] * 3
    with psycopg.connect(f.gateway_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_tasks").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM ag_grants").fetchone() == (3,)
        assert conn.execute("SELECT count(*) FROM ag_auth_evidence").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM ag_exchange_evidence").fetchone() == (2,)
    assert round_id in range(10)
    if case == "parent-revoked":
        _as_refusal(
            f,
            case,
            round_id,
            parent_token=f.as_material["tokens"][1],
            holder="selector",
            recipient="executor",
        )
    elif case != "positive":
        _as_refusal(f, case, round_id)


@pytest.mark.parametrize("round_id", range(10))
def test_three_holder_four_tools_query_receipt_anchor_export(scene, tmp_path, round_id):
    f = scene
    operations = []
    publisher = _publisher(f)
    for index, tool in enumerate(TOOLS):
        body = _body(
            f,
            tool,
            key=f"four-{round_id}-{index}",
            order=operations[2] if index == 3 else None,
        )
        status, accepted = _accept(f, body)
        assert status == 202 and accepted["status"] == "RESERVED"
        op = accepted["operation_id"]
        operations.append(op)
        assert f.env.service.run_operation(op).status == "SUCCEEDED"
        before = full_state(f.gateway_dsn, f.downstream_dsn)
        ready = publisher.publish(op)
        publication_only(before, full_state(f.gateway_dsn, f.downstream_dsn))
        assert ready.receipt_status == "READY"
        before_counts = _counts(f)
        query_body = {"profile": "GM-MVP-1", "task_id": "task-001", "operation_id": op}
        registration = f.env.registrations[("tenant-001", "agent-executor")]
        query_proof = sign_ag_proof(
            f.env.keys["executor"],
            kid=registration.kid,
            client_id="agent-executor",
            purpose="result-read",
            endpoint=INVOKE_ENDPOINT.replace("/v1/invocations", "/v1/operations/query"),
            body=query_body,
            token=f.env.token,
            now=int(time.time()),
        )
        status, answer, _ = signed_request(
            f.env,
            f.gateway_port,
            f.gateway_context,
            query_body,
            query=True,
            proof_override=query_proof,
        )
        assert status == 200 and answer["receipt_status"] == "READY"
        assert answer["receipt_jws"] == ready.receipt_jws
        assert answer["result"]["kind"] == (
            "read" if index < 2 else "order" if index == 2 else "notification"
        )
        assert _counts(f) == before_counts
        replay_before = full_state(f.gateway_dsn, f.downstream_dsn)
        replay_status, _, _ = signed_request(
            f.env,
            f.gateway_port,
            f.gateway_context,
            query_body,
            query=True,
            proof_override=query_proof,
        )
        assert replay_status in (401, 403, 409)
        assert _business(full_state(f.gateway_dsn, f.downstream_dsn)) == _business(replay_before)
        assert publisher.publish(op) == ready
    assert _counts(f)[0] == [(0, 70000, 0, 4)] * 3
    assert _counts(f)[3:] == (4, 4)
    client = AuditClient(
        "https://localhost:" + str(f.audit_port),
        ca_file=str(f.audit_tls / "ca.pem"),
        writer_credential="joint-writer:" + f.writer_token,
        reader_credential="joint-reader:" + f.reader_token,
    )
    delivery = DeliveryWorker(lambda: psycopg.connect(f.gateway_dsn), client, trust=(f.trust,))
    assert delivery.deliver_once(f.descriptor.scope.stream_id).status == "ACKED"
    status, latest = f.reader_latest()
    assert status == 200
    from agent_guard.audit.checkpoint import verify_checkpoint

    checkpoint = verify_checkpoint(
        latest["checkpoint_jws"], trust=(f.trust,), expected_scope=f.descriptor.scope
    )
    with psycopg.connect(f.gateway_dsn) as conn:
        local = conn.execute("SELECT max(seq) FROM ag_audit_records").fetchone()[0]
    assert checkpoint.claims.sequence == local
    _, _, _, report = _export(f, client, tmp_path / "export")
    assert len(report.runtime_status_as_of) == 4
    assert len(report.grant_counters) == 3


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("case", ("normal", "late-refusal"))
def test_downstream_separate_domain_service_auth_and_effects(scene, round_id, case):
    f = scene
    assert f.gateway_dsn != f.downstream_dsn
    body = _body(f, TOOLS[2], key=f"auth-{round_id}")
    _, accepted = _accept(f, body)
    op = accepted["operation_id"]
    from agent_guard.contracts.execution import ToolId
    from agent_guard.tools.catalog import snapshot_from_bytes

    with psycopg.connect(f.gateway_dsn) as conn:
        stored = execution_store.fetch_operation(conn, op)
    intent = dict(
        operation_id=op,
        tool_id=ToolId(stored.tool_id),
        canonical_params=bytes(stored.canonical_params),
        quote=snapshot_from_bytes(bytes(stored.quote_snapshot)),
        expected_amount_fen=stored.amount_fen,
    )
    before = full_state(f.gateway_dsn, f.downstream_dsn)
    for secret in (None, "wrong-service-secret"):
        with pytest.raises(Exception) as execute_denied:
            f.env.downstream.execute(service_secret=secret, **intent)
        assert execute_denied.value.code.value == "DOWNSTREAM_UNAUTHORIZED"
        assert full_state(f.gateway_dsn, f.downstream_dsn) == before
        with pytest.raises(Exception) as denied:
            f.env.downstream.query(service_secret=secret, operation_id=op)
        assert type(denied.value).__name__ == "ExecutionError"
        assert denied.value.code.value == "DOWNSTREAM_UNAUTHORIZED"
        assert full_state(f.gateway_dsn, f.downstream_dsn) == before
    if case == "late-refusal":
        approved = f.env.downstream._approved_suppliers
        f.env.downstream._approved_suppliers = frozenset()
        try:
            assert f.env.service.run_operation(op).status == "FAILED"
        finally:
            f.env.downstream._approved_suppliers = approved
        assert _counts(f)[0] == [(0, 0, 0, 0)] * 3
        assert _counts(f)[3:] == (1, 1)
        from tests.fixtures.execution import DOWNSTREAM_SECRET

        before = full_state(f.gateway_dsn, f.downstream_dsn)
        refused = f.env.downstream.execute(service_secret=DOWNSTREAM_SECRET, **intent)
        assert refused.already_existed and refused.final_rejection
        assert refused.effect_ref is None and refused.amount_fen == 0
        assert full_state(f.gateway_dsn, f.downstream_dsn) == before
        with psycopg.connect(f.downstream_dsn) as conn:
            assert conn.execute("SELECT count(*) FROM ds_orders").fetchone() == (0,)
        return
    assert f.env.service.run_operation(op).status == "SUCCEEDED"
    assert _counts(f)[0] == [(0, 70000, 0, 1)] * 3
    stable = full_state(f.gateway_dsn, f.downstream_dsn)
    from tests.fixtures.execution import DOWNSTREAM_SECRET

    replay = f.env.downstream.execute(service_secret=DOWNSTREAM_SECRET, **intent)
    assert replay.already_existed
    conflict = dict(
        intent,
        canonical_params=canonical_json_bytes(dict(body["params"], delivery_id="unapproved")),
    )
    with pytest.raises(Exception) as denied:
        f.env.downstream.execute(service_secret=DOWNSTREAM_SECRET, **conflict)
    assert denied.value.code.value == "DOWNSTREAM_INTENT_CONFLICT"
    assert full_state(f.gateway_dsn, f.downstream_dsn) == stable
    status, retried = _accept(f, body)
    assert status in (200, 202) and retried["operation_id"] == op
    actual = _effects(full_state(f.gateway_dsn, f.downstream_dsn))
    expected = _effects(stable)
    changed = [
        name for name in actual["gateway"] if actual["gateway"][name] != expected["gateway"][name]
    ]
    assert not changed, changed
    assert actual["downstream"] == expected["downstream"]


ATTACKS = (
    "stolen",
    "task",
    "version",
    "delivery",
    "quote",
    "bool",
    "negative",
    "overflow",
    "duplicate-sku",
    "empty",
    "url",
    "replay",
    "wrong-query-owner",
    "notification-url",
    "recipient",
    "template",
    "missing",
    "zero",
    "sku",
    "tool",
    "tenant",
    "proof-purpose",
    "proof-audience",
    "bound-idempotency",
    "bound-body",
    "duplicate-json",
)


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("attack", ATTACKS)
def test_attack_set_exact_binding_no_side_effects(scene, round_id, attack):
    f = scene
    body = _body(f, TOOLS[2], key=f"attack-{round_id}-{attack}")
    if attack == "task":
        body["task_id"] = "other-task"
    elif attack == "version":
        body["tool_version"] = "2"
    elif attack == "delivery":
        body["params"]["delivery_id"] = "other-office"
    elif attack == "quote":
        body["params"]["quote_version"] = "2"
    elif attack == "bool":
        body["params"]["items"][0]["quantity"] = True
    elif attack == "negative":
        body["params"]["items"][0]["quantity"] = -1
    elif attack == "overflow":
        body["params"]["items"][0]["quantity"] = 2**63
    elif attack == "duplicate-sku":
        body["params"]["items"] *= 2
    elif attack == "empty":
        body["params"]["items"] = []
    elif attack == "url":
        body["params"]["url"] = "https://unapproved.invalid/"
    elif attack == "missing":
        del body["params"]["items"][0]["quantity"]
    elif attack == "zero":
        body["params"]["items"][0]["quantity"] = 0
    elif attack == "sku":
        body["params"]["items"][0]["sku"] = "unapproved"
    elif attack == "tool":
        body["tool_id"] = "unapproved.tool"
    elif attack == "tenant":
        body["tenant_id"] = "other-tenant"
    proof = None
    if attack in (
        "proof-purpose",
        "proof-audience",
        "bound-idempotency",
        "bound-body",
        "duplicate-json",
    ):
        registration = f.env.registrations[("tenant-001", "agent-executor")]
        proof = sign_ag_proof(
            f.env.keys["executor"],
            kid=registration.kid,
            client_id="agent-executor",
            purpose="result-read" if attack == "proof-purpose" else "invoke",
            endpoint="https://other.invalid/v1/invocations"
            if attack == "proof-audience"
            else INVOKE_ENDPOINT,
            body=body,
            token=f.env.token,
            now=int(time.time()),
        )
        if attack == "bound-idempotency":
            body["idempotency_key"] += "-changed"
        if attack == "bound-body":
            body["params"]["delivery_id"] = "changed"
        if attack == "duplicate-json":
            from tests.integration.test_gateway_tls import HOST, LocalTLS

            before = full_state(f.gateway_dsn, f.downstream_dsn)
            raw = canonical_json_bytes(body)
            raw = b'{"task_id":"task-001",' + raw[1:]
            connection = LocalTLS(HOST, f.gateway_port, context=f.gateway_context, timeout=25)
            try:
                connection.request(
                    "POST",
                    "/v1/invocations",
                    body=raw,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "AGPoP " + f.env.token,
                        "AG-Proof": proof,
                    },
                )
                response = connection.getresponse()
                response.read()
                status = response.status
            finally:
                connection.close()
            assert status == 400
            assert _business(full_state(f.gateway_dsn, f.downstream_dsn)) == _business(before)
            return
    if attack == "stolen":
        registration = f.env.registrations[("tenant-001", "agent-planner")]
        proof = sign_ag_proof(
            f.env.keys["planner"],
            kid=registration.kid,
            client_id="agent-planner",
            purpose="invoke",
            endpoint=INVOKE_ENDPOINT,
            body=body,
            token=f.env.token,
            now=int(time.time()),
        )
    if attack in (
        "replay",
        "wrong-query-owner",
        "notification-url",
        "recipient",
        "template",
    ):
        registration = f.env.registrations[("tenant-001", "agent-executor")]
        validproof = sign_ag_proof(
            f.env.keys["executor"],
            kid=registration.kid,
            client_id="agent-executor",
            purpose="invoke",
            endpoint=INVOKE_ENDPOINT,
            body=body,
            token=f.env.token,
            now=int(time.time()),
        )
        status, accepted = _accept(f, body, proof=validproof)
        assert status == 202
        before = full_state(f.gateway_dsn, f.downstream_dsn)
        if attack == "replay":
            assert _accept(f, body, proof=validproof)[0] in (401, 409)
            assert _business(full_state(f.gateway_dsn, f.downstream_dsn)) == _business(before)
            status, retried = _accept(f, body)
            assert status in (200, 202) and retried["operation_id"] == accepted["operation_id"]
            assert _effects(full_state(f.gateway_dsn, f.downstream_dsn)) == _effects(before)
            return
        if attack == "wrong-query-owner":
            query = {
                "profile": "GM-MVP-1",
                "task_id": "task-001",
                "operation_id": accepted["operation_id"],
            }
            status, _, _ = signed_request(
                replace(f.env, token=f.as_material["tokens"][0]),
                f.gateway_port,
                f.gateway_context,
                query,
                query=True,
                holder="planner",
            )
            assert status in (401, 403)
            assert _business(full_state(f.gateway_dsn, f.downstream_dsn)) == _business(before)
            return
        # Real approved order effect supplies the fixed notification reference.
        assert f.env.service.run_operation(accepted["operation_id"]).status == "SUCCEEDED"
        body = _body(
            f,
            TOOLS[3],
            key=f"bad-notification-{round_id}-{attack}",
            order=accepted["operation_id"],
        )
        if attack == "notification-url":
            body["params"]["url"] = "https://unapproved.invalid/"
        elif attack == "recipient":
            body["params"]["recipient_id"] = "unapproved-user"
        else:
            body["params"]["template_id"] = "unapproved-template"
    before = full_state(f.gateway_dsn, f.downstream_dsn)
    if attack in ("negative", "overflow"):
        # The hostile wire is deliberately outside the safe signer/encoder domain.
        import hashlib
        import json

        from tests.fixtures.a31_audit_service import record_native
        from tests.integration.test_gateway_tls import HOST, LocalTLS

        legal_body = copy.deepcopy(body)
        legal_body["params"]["items"][0]["quantity"] = 1
        registration = f.env.registrations[("tenant-001", "agent-executor")]
        baseline_proof = sign_ag_proof(
            f.env.keys["executor"],
            kid=registration.kid,
            client_id="agent-executor",
            purpose="invoke",
            endpoint=INVOKE_ENDPOINT,
            body=legal_body,
            token=f.env.token,
            now=int(time.time()),
        )
        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
        connection = LocalTLS(HOST, f.gateway_port, context=f.gateway_context, timeout=25)
        try:
            connection.request(
                "POST",
                "/v1/invocations",
                body=raw,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "AGPoP " + f.env.token,
                    "AG-Proof": baseline_proof,
                },
            )
            response = connection.getresponse()
            response_raw = response.read()
            status = response.status
        finally:
            connection.close()
        assert status == 400
        record_native(
            "s1-hostile-json-actual-https",
            {
                "attack": attack,
                "round": round_id,
                "raw_utf8": raw.decode(),
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "baseline_proof_sha256": hashlib.sha256(baseline_proof.encode()).hexdigest(),
                "response_status": status,
                "response_sha256": hashlib.sha256(response_raw).hexdigest(),
                "TLS_verified": True,
                "original_hostile_value": body["params"]["items"][0]["quantity"],
            },
        )
    else:
        status, _ = _accept(f, body, proof=proof)
    after = full_state(f.gateway_dsn, f.downstream_dsn)
    assert status in (400, 401, 403, 409)
    assert _business(after) == _business(before)
    if attack in ("negative", "overflow"):
        assert after == before
        assert _ORACLE_AUDIT_STATES[id(after)][1] == _ORACLE_AUDIT_STATES[id(before)][1]
    # Inbound independently staged raw materials are accounted separately.
    assert len(after["gateway"].get("ag_verified_evidence", [])) >= len(
        before["gateway"].get("ag_verified_evidence", [])
    )


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize(
    "case",
    (
        "root-budget",
        "two-branches",
        "mid-money",
        "direct-descendant",
        "proof-final-clock",
        "leaf-calls",
        "revoke-first",
        "accept-first",
        "query-final-clock",
        "token-ancestor-invoke-clock",
        "token-ancestor-query-clock",
    ),
)
def test_root_mid_calls_revocation_final_clock_races(scene, round_id, case):
    f = scene
    if case in ("revoke-first", "accept-first"):
        from agent_guard.ledger.provisioning import revoke_grant
        from tests.fixtures.a31_audit_service import record_native

        root = f.as_material["claims"][0]["ag_grant_id"]
        lock = psycopg.connect(f.gateway_dsn)
        pool = ThreadPoolExecutor(max_workers=2)
        try:
            if case == "revoke-first":
                lock.execute("SELECT 1")
                revoke_grant(lock, root)
            else:
                lock.execute(
                    "SELECT stream_id FROM ag_audit_streams WHERE stream_id=%s FOR UPDATE",
                    (f.descriptor.scope.stream_id,),
                ).fetchone()
            blocker = lock.execute("SELECT pg_backend_pid()").fetchone()[0]
            accept = pool.submit(_accept, f, _body(f, TOOLS[2], key=f"ordered-{round_id}-{case}"))
            deadline = time.monotonic() + 5
            while True:
                with psycopg.connect(f.gateway_dsn) as conn:
                    waiting = conn.execute(
                        "SELECT pid FROM pg_stat_activity WHERE %s=ANY(pg_blocking_pids(pid))",
                        (blocker,),
                    ).fetchall()
                if waiting:
                    break
                if accept.done() or time.monotonic() >= deadline:
                    lock.rollback()
                    pytest.fail("actual accept lock wait absent")
                time.sleep(0.01)
            if case == "accept-first":

                def revoke():
                    with psycopg.connect(f.gateway_dsn) as conn:
                        revoke_grant(conn, root)

                revocation = pool.submit(revoke)
                deadline = time.monotonic() + 5
                while True:
                    with psycopg.connect(f.gateway_dsn) as conn:
                        revoker = conn.execute(
                            "SELECT pid FROM pg_stat_activity WHERE %s=ANY(pg_blocking_pids(pid))",
                            (waiting[0][0],),
                        ).fetchall()
                    if revoker:
                        break
                    if revocation.done() or time.monotonic() >= deadline:
                        lock.rollback()
                        pytest.fail("actual revoke behind accept absent")
                    time.sleep(0.01)
            lock.commit()
            status, result = accept.result(timeout=10)
            if case == "revoke-first":
                assert status in (401, 403)
                assert _counts(f)[0] == [(0, 0, 0, 0)] * 3
                assert _counts(f)[1:] == ([], [], 0, 0)
            else:
                assert status == 202
                revocation.result(timeout=10)
                assert _counts(f)[0] == [(70000, 0, 1, 0)] * 3
                assert f.env.service.run_operation(result["operation_id"]).status == "SUCCEEDED"
                assert _counts(f)[0] == [(0, 70000, 0, 1)] * 3
                assert _counts(f)[3:] == (1, 1)
            record_native(
                "a33-revocation-order",
                {
                    "case": case,
                    "round": round_id,
                    "blocker": blocker,
                    "waiting": waiting,
                    "status": status,
                },
            )
        finally:
            lock.rollback()
            lock.close()
            pool.shutdown(wait=True)
        return
    if case == "mid-money":
        body = _body(f, TOOLS[2], key=f"mid-direct-{round_id}")
        status, accepted = _accept(f, body, holder="selector", token=f.as_material["tokens"][1])
        assert status == 202
        assert _counts(f)[0] == [(70000, 0, 1, 0), (70000, 0, 1, 0), (0, 0, 0, 0)]
        small = _body(f, TOOLS[2], key=f"mid-small-{round_id}")
        small["params"]["items"][0]["sku"] = "sku-small"
        before = full_state(f.gateway_dsn, f.downstream_dsn)
        status, denied = _accept(f, small)
        assert status == 422 and denied["error"]["code"] == "BUDGET_EXCEEDED"
        assert _business(full_state(f.gateway_dsn, f.downstream_dsn)) == _business(before)
        assert _counts(f)[3:] == (0, 0)
        assert f.env.service.run_operation(accepted["operation_id"]).status == "SUCCEEDED"
        assert _counts(f)[0] == [(0, 70000, 0, 1), (0, 70000, 0, 1), (0, 0, 0, 0)]
        return
    if case == "direct-descendant":
        operations = []
        for holder, token in (
            ("selector", f.as_material["tokens"][1]),
            ("executor", f.env.token),
        ):
            status, result = _accept(
                f,
                _body(f, TOOLS[0], key=f"direct-desc-{round_id}-{holder}"),
                holder=holder,
                token=token,
            )
            assert status == 202
            operations.append(result["operation_id"])
        assert _counts(f)[0] == [(0, 0, 2, 0), (0, 0, 2, 0), (0, 0, 1, 0)]
        for operation in operations:
            assert f.env.service.run_operation(operation).status == "SUCCEEDED"
        assert _counts(f)[0] == [(0, 0, 0, 2), (0, 0, 0, 2), (0, 0, 0, 1)]
        return
    if case == "two-branches":
        mid_token, mid_claims = _as_refusal(f, "branch-middle", round_id, amount=70000)
        leaf_token, leaf_claims = _as_refusal(
            f,
            "branch-leaf",
            round_id,
            parent_token=mid_token,
            holder="selector",
            recipient="executor",
        )
        barrier = Barrier(2)

        def draw_branch(index):
            barrier.wait(timeout=5)
            return _accept(
                f,
                _body(f, TOOLS[2], key=f"branch-race-{round_id}-{index}"),
                token=f.env.token if index == 0 else leaf_token,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            answers = list(pool.map(draw_branch, (0, 1)))
        assert sum(status == 202 for status, _ in answers) == 1
        winner = next(result for status, result in answers if status == 202)
        with psycopg.connect(f.gateway_dsn) as conn:
            root = conn.execute(
                "SELECT amount_reserved,calls_reserved FROM ag_grants WHERE grant_id=%s",
                (f.as_material["claims"][0]["ag_grant_id"],),
            ).fetchone()
            assert root == (70000, 1)
            rows = conn.execute(
                "SELECT amount_reserved,calls_reserved FROM ag_grants WHERE depth>0"
            ).fetchall()
            assert sorted(rows) == [(0, 0), (0, 0), (70000, 1), (70000, 1)]
        assert _counts(f)[3:] == (0, 0)
        assert f.env.service.run_operation(winner["operation_id"]).status == "SUCCEEDED"
        assert _counts(f)[3:] == (1, 1)
        return
    if case == "leaf-calls":
        operations = []
        for index in range(8):
            status, accepted = _accept(
                f, _body(f, TOOLS[index % 2], key=f"calls-{round_id}-{index}")
            )
            assert status == 202
            operations.append(accepted["operation_id"])
        assert _counts(f)[0] == [(0, 0, 8, 0)] * 3
        before = full_state(f.gateway_dsn, f.downstream_dsn)
        status, denied = _accept(f, _body(f, TOOLS[0], key=f"calls-over-{round_id}"))
        assert status == 422 and denied["error"]["code"] == "CALL_LIMIT_EXCEEDED"
        assert _business(full_state(f.gateway_dsn, f.downstream_dsn)) == _business(before)
        for operation in operations:
            assert f.env.service.run_operation(operation).status == "SUCCEEDED"
        assert _counts(f)[0] == [(0, 0, 0, 8)] * 3
        assert _counts(f)[3:] == (8, 8)
        return
    if case in ("token-ancestor-invoke-clock", "token-ancestor-query-clock"):
        from tests.fixtures.a31_audit_service import record_native

        is_query = case == "token-ancestor-query-clock"
        root_claims = f.as_material["claims"][0]
        root_exp = root_claims["exp"]
        wait_started = time.time()
        # No artificial token, clock override, renewal, or grant-table expiry edit.
        # The existing root has its original 300-second lifetime.
        deadline = time.monotonic() + 310
        while time.time() < root_exp - 20:
            assert time.monotonic() < deadline
            time.sleep(min(1, max(0.01, root_exp - 20 - time.time())))
        middle_token, middle_claims = _as_refusal(f, "branch-middle", round_id, amount=70000)
        leaf_token, leaf_claims = _as_refusal(
            f,
            "branch-leaf",
            round_id,
            parent_token=middle_token,
            holder="selector",
            recipient="executor",
            amount=70000,
        )
        assert time.time() < leaf_claims["exp"] <= middle_claims["exp"] <= root_exp
        with psycopg.connect(f.gateway_dsn) as readback:
            chain_ids = [
                root_claims["ag_grant_id"],
                middle_claims["ag_grant_id"],
                leaf_claims["ag_grant_id"],
            ]
            expiry_rows = readback.execute(
                "SELECT grant_id,parent_grant_id,depth,extract(epoch FROM expires_at) "
                "FROM ag_grants WHERE grant_id=ANY(%s) ORDER BY depth",
                (chain_ids,),
            ).fetchall()
        assert [int(row[3]) for row in expiry_rows] == [
            root_exp,
            middle_claims["exp"],
            leaf_claims["exp"],
        ]
        env = replace(f.env, token=leaf_token)
        control_body = _body(f, TOOLS[0], key=f"expiry-control-{round_id}")
        status, accepted = _accept(f, control_body, token=leaf_token)
        assert status == 202
        if is_query:
            assert f.env.service.run_operation(accepted["operation_id"]).status == "SUCCEEDED"
            assert _publisher(f).publish(accepted["operation_id"]).receipt_status == "READY"
            body = {
                "profile": "GM-MVP-1",
                "task_id": "task-001",
                "operation_id": accepted["operation_id"],
            }
            assert (
                signed_request(env, f.gateway_port, f.gateway_context, body, query=True)[0] == 200
            )
        else:
            body = _body(f, TOOLS[0], key=f"expiry-target-{round_id}")
        # Observe all domains before entering the narrow live-token lock window.
        before = full_state(f.gateway_dsn, f.downstream_dsn)
        expiry_gap = root_exp - leaf_claims["exp"]
        assert 0 <= expiry_gap <= 2
        # Two one-second child margins leave a half-second live-token window
        # before crossing all three expiries within the original three-second wait.
        enter_at = root_exp - 2.5
        assert enter_at < leaf_claims["exp"]
        while time.time() < enter_at:
            assert time.monotonic() < deadline
            time.sleep(0.05)
        assert time.time() < leaf_claims["exp"]
        proof_started = int(time.time())
        registration = f.env.registrations[("tenant-001", "agent-executor")]
        proof = sign_ag_proof(
            f.env.keys["executor"],
            kid=registration.kid,
            client_id="agent-executor",
            purpose="result-read" if is_query else "invoke",
            endpoint=INVOKE_ENDPOINT.replace("/v1/invocations", "/v1/operations/query")
            if is_query
            else INVOKE_ENDPOINT,
            body=body,
            token=leaf_token,
            now=proof_started,
            lifetime_seconds=60,
        )
        with psycopg.connect(f.gateway_dsn) as lock:
            lock.execute(
                "SELECT stream_id FROM ag_audit_streams WHERE stream_id=%s FOR UPDATE",
                (f.descriptor.scope.stream_id,),
            ).fetchone()
            blocker = lock.execute("SELECT pg_backend_pid()").fetchone()[0]
            operator_lock_timeout = lock.execute("SHOW lock_timeout").fetchone()[0]
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    signed_request,
                    env,
                    f.gateway_port,
                    f.gateway_context,
                    body,
                    query=is_query,
                    proof_override=proof,
                )
                observed_deadline = time.monotonic() + 5
                while True:
                    with psycopg.connect(f.gateway_dsn) as probe:
                        waiting = probe.execute(
                            "SELECT pid FROM pg_stat_activity WHERE %s=ANY(pg_blocking_pids(pid))",
                            (blocker,),
                        ).fetchall()
                    if waiting:
                        break
                    if future.done() or time.monotonic() >= observed_deadline:
                        lock.rollback()
                        pytest.fail("live token/ancestor journal wait was not observed")
                    time.sleep(0.01)
                while True:
                    db_clock = lock.execute(
                        "SELECT extract(epoch FROM clock_timestamp())"
                    ).fetchone()[0]
                    if db_clock > root_exp:
                        break
                    assert time.monotonic() < deadline
                    time.sleep(0.1)
                assert float(db_clock) < proof_started + 60
                lock.commit()
                status, _, _ = future.result(timeout=5)
                assert status in (401, 403)
        after = full_state(f.gateway_dsn, f.downstream_dsn)
        assert _business(after) == _business(before)
        record_native(
            "a33-token-ancestor-final-clock",
            {
                "case": case,
                "round": round_id,
                "start": wait_started,
                "root_exp": root_exp,
                "root_iat": root_claims["iat"],
                "middle_iat": middle_claims["iat"],
                "leaf_iat": leaf_claims["iat"],
                "enter_at": enter_at,
                "expiry_gap": expiry_gap,
                "operator_lock_timeout": operator_lock_timeout,
                "gateway_configured_lock_timeout_ms": getattr(
                    f.env.service, "_lock_timeout_ms", None
                ),
                "as_lock_timeout_authority": "exchange_service._connect sets 10000ms",
                "middle_exp": middle_claims["exp"],
                "leaf_exp": leaf_claims["exp"],
                "proof_exp": proof_started + 60,
                "db_clock": str(db_clock),
                "waiting": waiting,
                "status": status,
                "before": before,
                "after": after,
                "expiry_readback": [[row[0], row[1], row[2], int(row[3])] for row in expiry_rows],
                "boundary": "valid leaf cannot outlive its ancestor; both naturally expired",
            },
        )
        return
    if case in ("proof-final-clock", "query-final-clock"):
        is_query = case == "query-final-clock"
        if is_query:
            status, accepted = _accept(f, _body(f, TOOLS[0], key=f"query-clock-op-{round_id}"))
            assert status == 202
            assert f.env.service.run_operation(accepted["operation_id"]).status == "SUCCEEDED"
            assert _publisher(f).publish(accepted["operation_id"]).receipt_status == "READY"
            body = {
                "profile": "GM-MVP-1",
                "task_id": "task-001",
                "operation_id": accepted["operation_id"],
            }
        else:
            body = _body(f, TOOLS[0], key=f"clock-{round_id}")
        registration = f.env.registrations[("tenant-001", "agent-executor")]
        proof = sign_ag_proof(
            f.env.keys["executor"],
            kid=registration.kid,
            client_id="agent-executor",
            purpose="result-read" if is_query else "invoke",
            endpoint=INVOKE_ENDPOINT.replace("/v1/invocations", "/v1/operations/query")
            if is_query
            else INVOKE_ENDPOINT,
            body=body,
            token=f.env.token,
            now=int(time.time()) - 58,
            lifetime_seconds=60,
        )
        before = full_state(f.gateway_dsn, f.downstream_dsn)
        lock = psycopg.connect(f.gateway_dsn)
        try:
            lock.execute(
                "SELECT stream_id FROM ag_audit_streams WHERE stream_id=%s FOR UPDATE",
                (f.descriptor.scope.stream_id,),
            ).fetchone()
            blocker = lock.execute("SELECT pg_backend_pid()").fetchone()[0]
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    signed_request,
                    f.env,
                    f.gateway_port,
                    f.gateway_context,
                    body,
                    query=is_query,
                    proof_override=proof,
                )
                deadline = time.monotonic() + 5
                while True:
                    with psycopg.connect(f.gateway_dsn) as probe:
                        waiting = probe.execute(
                            "SELECT pid FROM pg_stat_activity WHERE %s=ANY(pg_blocking_pids(pid))",
                            (blocker,),
                        ).fetchall()
                    if waiting:
                        break
                    if future.done() or time.monotonic() >= deadline:
                        lock.rollback()
                        pytest.fail("required live journal wait was not observed")
                    time.sleep(0.01)
                time.sleep(2.1)
                lock.commit()
                status, _, _ = future.result(timeout=5)
                assert status in (401, 403)
                from tests.fixtures.a31_audit_service import record_native

                record_native(
                    "a33-final-clock",
                    {
                        "round": round_id,
                        "blocker": blocker,
                        "waiting": waiting,
                        "clock": time.time(),
                        "status": status,
                    },
                )
        finally:
            lock.close()
        assert _business(full_state(f.gateway_dsn, f.downstream_dsn)) == _business(before)
        return
    barrier = Barrier(2)

    def draw(index):
        barrier.wait(timeout=5)
        return _accept(f, _body(f, TOOLS[2], key=f"race-{round_id}-{index}"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(draw, (0, 1)))
    accepted = [answer for status, answer in answers if status == 202]
    assert len(accepted) == 1
    assert [status for status, _ in answers if status != 202][0] in (400, 403, 409, 422)
    assert _counts(f)[0] == [(70000, 0, 1, 0)] * 3
    assert _counts(f)[3:] == (0, 0)
    # Revoke committed first: future external retry cannot revive the operation.
    from agent_guard.ledger.provisioning import revoke_grant

    leaf = f.as_material["claims"][-1]["ag_grant_id"]
    with psycopg.connect(f.gateway_dsn) as conn:
        revoke_grant(conn, grant_id=leaf)
    before = full_state(f.gateway_dsn, f.downstream_dsn)
    assert _accept(f, _body(f, TOOLS[0], key=f"after-revoke-{round_id}"))[0] in (
        401,
        403,
    )
    assert _business(full_state(f.gateway_dsn, f.downstream_dsn)) == _business(before)
    # Accepted internal immutable intent still completes after revocation.
    assert f.env.service.run_operation(accepted[0]["operation_id"]).status == "SUCCEEDED"
    assert _counts(f)[0] == [(0, 70000, 0, 1)] * 3


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize(
    "fault",
    (
        "before-worker",
        "after-downstream",
        "terminal-event",
        "terminal-node",
        "terminal-outbox",
        "none-late-multiple",
        "wrong-outcome",
        "quote-mutation",
        "stale-live-owner",
        "recovery-revoked",
    ),
)
def test_process_crash_late_success_recovery_fault_matrix(
    scene, tmp_path, monkeypatch, round_id, fault
):
    f = scene
    _, accepted = _accept(f, _body(f, TOOLS[2], key=f"fault-{round_id}-{fault}"))
    operation = accepted["operation_id"]
    assert _counts(f)[0] == [(70000, 0, 1, 0)] * 3
    assert _counts(f)[3:] == (0, 0)
    if fault in ("wrong-outcome", "quote-mutation"):
        owner = uuid.uuid4().hex
        real_execute = f.env.downstream.execute
        real_query = f.env.downstream.query

        def committed_lost(**kwargs):
            real_execute(**kwargs)
            raise TimeoutError("layered reply lost after real DS commit")

        with monkeypatch.context() as patch:
            patch.setattr(f.env.downstream, "execute", committed_lost)
            assert f.env.service.run_operation(operation, owner_token=owner).status == "UNKNOWN"
        assert _counts(f)[0] == [(70000, 0, 1, 0)] * 3
        assert _counts(f)[3:] == (0, 1)
        with psycopg.connect(f.gateway_dsn) as conn:
            stored = execution_store.fetch_operation(conn, operation)
        original_material = (
            stored.quote_snapshot,
            stored.canonical_params,
            stored.intent_digest,
            stored.evidence_ref,
            stored.accepted_at,
        )
        if fault == "quote-mutation":
            from agent_guard.tools.catalog import CatalogQuote, CatalogQuoteLine

            f.env.service._catalog.replace_quote(
                CatalogQuote(
                    "quote-001",
                    "1",
                    "unapproved-supplier",
                    "req-001",
                    (CatalogQuoteLine("sku-001", 1, 1),),
                )
            )
            f.env.service._catalog.remove_quote("quote-001", "1")
        else:
            from agent_guard.contracts.execution import ToolId
            from tests.fixtures.execution import DOWNSTREAM_SECRET

            outcome = real_query(service_secret=DOWNSTREAM_SECRET, operation_id=operation)
            assert outcome is not None
            variants = (
                replace(outcome, operation_id="wrong-op"),
                replace(outcome, tool_id=ToolId.REQUEST_READ),
                replace(outcome, amount_fen=True),
                replace(outcome, amount_fen=69999),
                replace(outcome, canonical_params=b"{}"),
                replace(outcome, quote=None),
                replace(outcome, result_bytes=b"{}"),
                replace(outcome, effect_ref="wrong-effect"),
            )
            for index, variant in enumerate(variants):
                with monkeypatch.context() as patch:
                    patch.setattr(
                        f.env.downstream,
                        "query",
                        lambda variant=variant, **kwargs: variant,
                    )
                    assert f.env.service.reconcile(operation, owner_token=owner).status == "UNKNOWN"
                assert _counts(f)[0] == [(70000, 0, 1, 0)] * 3
                assert _counts(f)[3:] == (0, 1)
                from tests.fixtures.a31_audit_service import record_native

                record_native(
                    "a33-layered-outcome",
                    {
                        "round": round_id,
                        "variant": index,
                        "reserved": 70000,
                        "status": "UNKNOWN",
                        "real_ds_effects": 1,
                    },
                )
        assert f.env.service.reconcile(operation, owner_token=owner).status == "SUCCEEDED"
        with psycopg.connect(f.gateway_dsn) as conn:
            after = execution_store.fetch_operation(conn, operation)
        assert (
            after.quote_snapshot,
            after.canonical_params,
            after.intent_digest,
            after.evidence_ref,
            after.accepted_at,
        ) == original_material
    elif fault == "none-late-multiple":
        owner = uuid.uuid4().hex
        real_execute = f.env.downstream.execute

        def unavailable(**kwargs):
            raise TimeoutError("layered pre-execute uncertainty")

        with monkeypatch.context() as patch:
            patch.setattr(f.env.downstream, "execute", unavailable)
            assert f.env.service.run_operation(operation, owner_token=owner).status == "UNKNOWN"
        assert f.env.service.reconcile(operation, owner_token=owner).status == "UNKNOWN"
        assert _counts(f)[0] == [(70000, 0, 1, 0)] * 3
        assert _counts(f)[3:] == (0, 0)
        from agent_guard.contracts.execution import ToolId
        from agent_guard.tools.catalog import snapshot_from_bytes
        from tests.fixtures.execution import DOWNSTREAM_SECRET

        with psycopg.connect(f.gateway_dsn) as conn:
            stored = execution_store.fetch_operation(conn, operation)
        real_execute(
            service_secret=DOWNSTREAM_SECRET,
            operation_id=operation,
            tool_id=ToolId(stored.tool_id),
            canonical_params=bytes(stored.canonical_params),
            quote=snapshot_from_bytes(bytes(stored.quote_snapshot)),
            expected_amount_fen=stored.amount_fen,
        )
        _wait_lease(f, operation)
        barrier = Barrier(2)

        def recover(index):
            barrier.wait(timeout=5)
            try:
                return f.env.service.reconcile(operation, owner_token=uuid.uuid4().hex).status
            except Exception as exc:
                assert exc.code.value == "LEASE_LOST"
                return "LEASE_LOST"

        with ThreadPoolExecutor(max_workers=2) as pool:
            recovered = list(pool.map(recover, (0, 1)))
        assert "SUCCEEDED" in recovered
        assert _counts(f)[1][0][1] == "SUCCEEDED"
    elif fault == "before-worker":
        directory = tmp_path / "reserve-kill"
        directory.mkdir(mode=0o700)
        boundary = CommittedBoundary(directory, name="accepted-before-worker")
        child = multiprocessing.get_context("fork").Process(target=boundary)
        child.start()
        try:
            marker = _wait_marker(directory / "accepted-before-worker.json", child)
            assert marker["native"]["pid"] == child.pid
            assert _counts(f)[3:] == (0, 0)
            kill_marked_process(directory / "accepted-before-worker.json")
            child.join(timeout=5)
            assert child.exitcode == -9
            replacement = multiprocessing.get_context("fork").Process(
                target=f.env.service.run_operation, args=(operation,)
            )
            replacement.start()
            replacement.join(timeout=10)
            assert replacement.exitcode == 0 and replacement.pid != child.pid
        finally:
            if child.is_alive():
                child.kill()
                child.join(timeout=5)
    elif fault in ("after-downstream", "stale-live-owner", "recovery-revoked"):
        directory = tmp_path / "fault"
        directory.mkdir(mode=0o700)
        boundary = CommittedBoundary(directory, name="ds-commit")
        child = multiprocessing.get_context("fork").Process(
            target=f.env.service.run_operation,
            args=(operation,),
            kwargs={"pause": boundary},
        )
        child.start()
        try:
            meta = _wait_marker(directory / "ds-commit.json", child)
            assert meta["native"]["pid"] == child.pid
            assert _counts(f)[0] == [(70000, 0, 1, 0)] * 3
            assert _counts(f)[4] == 1 and _counts(f)[3] == 0
            if fault != "stale-live-owner":
                kill = kill_marked_process(directory / "ds-commit.json")
                child.join(timeout=5)
                assert child.exitcode == -9 and kill["pid"] == child.pid
            if fault == "recovery-revoked":
                from agent_guard.ledger.provisioning import revoke_grant

                with psycopg.connect(f.gateway_dsn) as conn:
                    revoke_grant(conn, f.as_material["claims"][0]["ag_grant_id"])
                before = full_state(f.gateway_dsn, f.downstream_dsn)
                assert _accept(f, _body(f, TOOLS[0], key=f"recovery-revoke-{round_id}"))[0] in (
                    401,
                    403,
                )
                assert _business(full_state(f.gateway_dsn, f.downstream_dsn)) == _business(before)
            _wait_lease(f, operation)
            replacement = multiprocessing.get_context("fork").Process(
                target=f.env.service.reconcile, args=(operation,)
            )
            replacement.start()
            replacement.join(timeout=10)
            assert replacement.exitcode == 0 and replacement.pid != child.pid
            if fault == "stale-live-owner":
                (directory / "ds-commit.release").touch(mode=0o600)
                child.join(timeout=10)
                assert child.exitcode == 1
                from tests.fixtures.a31_audit_service import record_native

                record_native(
                    "a33-stale-fence",
                    {
                        "round": round_id,
                        "old_pid": child.pid,
                        "old_exit": child.exitcode,
                        "new_pid": replacement.pid,
                        "new_exit": replacement.exitcode,
                    },
                )
        finally:
            if child.is_alive():
                child.kill()
                child.join(timeout=5)
    else:
        target = {
            "terminal-event": "insert_terminal_event",
            "terminal-node": "insert_terminal_event",
            "terminal-outbox": "insert_pending_receipt",
        }[fault]
        original = getattr(execution_store, target)

        def fail(*args, **kwargs):
            if fault == "terminal-node":
                original(*args, **kwargs)
            raise RuntimeError("test-only terminal rollback")

        owner_token = uuid.uuid4().hex
        with monkeypatch.context() as patch:
            patch.setattr(execution_store, target, fail)
            with pytest.raises(RuntimeError, match="terminal rollback"):
                f.env.service.run_operation(operation, owner_token=owner_token)
        assert getattr(execution_store, target) is original
        assert _counts(f)[0] == [(70000, 0, 1, 0)] * 3
        assert _counts(f)[3:] == (0, 1)
        assert _counts(f)[2] == [(operation, "RESERVE")]
        with psycopg.connect(f.gateway_dsn) as conn:
            assert conn.execute("SELECT count(*) FROM ag_ledger_event_nodes").fetchone() == (3,)
        assert f.env.service.reconcile(operation, owner_token=owner_token).status == "SUCCEEDED"
    assert _counts(f)[0] == [(0, 70000, 0, 1)] * 3
    assert _counts(f)[3:] == (1, 1)
    assert _counts(f)[2] == [(operation, "RESERVE"), (operation, "SETTLE")]
    with psycopg.connect(f.gateway_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_ledger_event_nodes").fetchone() == (6,)
    with psycopg.connect(f.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_orders").fetchone() == (1,)
    from tests.fixtures.a31_audit_service import record_native

    record_native(
        "a33-fault-oracle",
        {
            "fault": fault,
            "round": round_id,
            "all_domains": full_state(f.gateway_dsn, f.downstream_dsn),
            "counts": _counts(f),
        },
    )


@pytest.mark.parametrize("round_id", range(10))
@pytest.mark.parametrize("fault", ("before-sign", "signed-before-save", "ready-lost-reply"))
def test_receipt_audit_export_faults_and_offline_mutations(scene, tmp_path, round_id, fault):
    f = scene
    _, accepted = _accept(f, _body(f, TOOLS[2], key=f"publisher-{round_id}"))
    op = accepted["operation_id"]
    assert f.env.service.run_operation(op).status == "SUCCEEDED"
    publisher = _publisher(f)
    directory = tmp_path / "publisher-fault"
    directory.mkdir(mode=0o700)

    def publish_then_wait():
        original = publication.sign_compact_jws
        boundary = CommittedBoundary(directory, name=fault)

        def signed(*args, **kwargs):
            if fault == "before-sign":
                boundary()
            result = original(*args, **kwargs)
            if fault == "signed-before-save":
                boundary()
            return result

        publication.sign_compact_jws = signed
        publisher.publish(op)
        if fault == "ready-lost-reply":
            boundary()

    child = multiprocessing.get_context("fork").Process(target=publish_then_wait)
    child.start()
    try:
        _wait_marker(directory / (fault + ".json"), child)
        before = _counts(f)
        committed_state = full_state(f.gateway_dsn, f.downstream_dsn)
        kill_marked_process(directory / (fault + ".json"))
        child.join(timeout=5)
        assert child.exitcode == -9
        assert _counts(f) == before
        ready = publisher.publish(op)
        assert ready.receipt_status == "READY"
        if fault == "ready-lost-reply":
            assert full_state(f.gateway_dsn, f.downstream_dsn) == committed_state
        stable = full_state(f.gateway_dsn, f.downstream_dsn)
        assert publisher.publish(op) == ready
        assert full_state(f.gateway_dsn, f.downstream_dsn) == stable
        payload = verify_compact_jws(
            ready.receipt_jws,
            expected_type="ag-receipt+jwt",
            trusted_keys={"joint-receipt-1": f.receipt_key.public_key()},
        )
        assert payload["amount_fen"] == 70000 and payload["operation_id"] == op
        from agent_guard.contracts.encoding import b64url_decode, b64url_encode

        pieces = ready.receipt_jws.split(".")
        header = load_strict_json(b64url_decode(pieces[0]))
        for name, value in (("typ", "wrong-type"), ("kid", "untrusted-kid")):
            changed = dict(header, **{name: value})
            mutated = ".".join((b64url_encode(canonical_json_bytes(changed)), pieces[1], pieces[2]))
            with pytest.raises(ValueError):
                verify_compact_jws(
                    mutated,
                    expected_type="ag-receipt+jwt",
                    trusted_keys={"joint-receipt-1": f.receipt_key.public_key()},
                )
        from agent_guard.authorization.evidence_store import EvidenceError
        from agent_guard.crypto.sm import sign_compact_jws

        verifier = receipt_services(
            f.env,
            f.gateway_dsn,
            gateway_key=f.receipt_key,
            signing_kid="joint-receipt-1",
        )[1]
        before_mutations = full_state(f.gateway_dsn, f.downstream_dsn)
        with psycopg.connect(f.gateway_dsn) as conn:
            verifier.verify_tx(conn, op, ready.receipt_jws)
            for name in payload:
                bad = dict(payload)
                bad[name] = bad[name] + 1 if type(bad[name]) is int else "other"
                changed = sign_compact_jws(
                    f.receipt_key,
                    bad,
                    key_id="joint-receipt-1",
                    token_type="ag-receipt+jwt",
                )
                with pytest.raises(EvidenceError):
                    verifier.verify_tx(conn, op, changed)
        assert full_state(f.gateway_dsn, f.downstream_dsn) == before_mutations
        raw = ready.receipt_jws.split(".")
        raw[-1] = ("A" if raw[-1][0] != "A" else "B") + raw[-1][1:]
        with pytest.raises(ValueError):
            verify_compact_jws(
                ".".join(raw),
                expected_type="ag-receipt+jwt",
                trusted_keys={"joint-receipt-1": f.receipt_key.public_key()},
            )
        client = AuditClient(
            "https://localhost:" + str(f.audit_port),
            ca_file=str(f.audit_tls / "ca.pem"),
            writer_credential="joint-writer:" + f.writer_token,
            reader_credential="joint-reader:" + f.reader_token,
        )
        delivery = _delivery_binding(f, client)
        pending = delivery.persist_pending()
        old_pid, new_pid = delivery.send_pending_lost_reply()
        assert old_pid != new_pid
        latest_before_restart = client.latest(f.descriptor.scope.stream_id)
        assert delivery.pending_snapshot() == pending
        import subprocess

        from tests.fixtures.a31_audit_service import record_native

        audit_pid = f.audit_process.pid
        f.audit_process.terminate()
        f.audit_process.communicate(timeout=10)
        assert f.audit_process.returncode == -15
        audit_replacement = subprocess.Popen(
            f.audit_process.args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        f.native_children.append(audit_replacement)
        deadline = time.monotonic() + 10
        while True:
            assert audit_replacement.poll() is None
            try:
                assert client.latest(f.descriptor.scope.stream_id) == latest_before_restart
                break
            except AuditUnavailable:
                assert time.monotonic() < deadline
                time.sleep(0.02)
        assert audit_replacement.pid != audit_pid
        record_native(
            "a33-audit-restart",
            {
                "old_pid": audit_pid,
                "old_exit": -15,
                "new_pid": audit_replacement.pid,
                "checkpoint_identical": True,
            },
        )
        delivery.restart_and_reconcile(latest_before_restart)
        assert client.latest(f.descriptor.scope.stream_id) == latest_before_restart
        exported, trust, pin, report = _export(f, client, tmp_path / "mutations")
        from agent_guard.evidence.task_verify import verify_task_bundle

        lines = exported.splitlines(keepends=True)
        for mutation in (
            exported[:-1],
            b"".join(reversed(lines)),
            b"".join(lines[:-1]),
            b"".join(lines[1:]),
        ):
            with pytest.raises(ValueError):
                verify_task_bundle(io.BytesIO(mutation), trust, pin)
        assert len(report.runtime_status_as_of) == 1
        assert _query(f, op)[0] == 200
        _, _, _, tail_report = _export(f, client, tmp_path / "tail-export", expected_tail=1)
        assert "UNANCHORED_TAIL" in tail_report.limitations
        _, _, _, unknown_report = _export(
            f,
            client,
            tmp_path / "unknown-export",
            expected_tail=None,
            pin_mode="UNKNOWN",
        )
        assert unknown_report.freshness == "UNKNOWN"
        assert (
            unknown_report.anchored_prefix == 0
            and unknown_report.tail == unknown_report.cutoff_sequence
        )
        assert "NO_LATEST_EXTERNAL_ANCHOR" in unknown_report.limitations
        assert (
            unknown_report.current_auth == "UNKNOWN"
            and unknown_report.downstream_truth == "ATTESTED_NOT_INDEPENDENTLY_PROVEN"
        )
        assert (
            DeliveryWorker(lambda: psycopg.connect(f.gateway_dsn), client, trust=(f.trust,))
            .deliver_once(f.descriptor.scope.stream_id)
            .status
            == "ACKED"
        )
        current_raw, current_trust, current_pin, current_report = _export(
            f, client, tmp_path / "continued-export"
        )
        assert current_pin["checkpoint_jws"] != pin["checkpoint_jws"]
        assert current_report.cutoff_sequence > report.cutoff_sequence
        with pytest.raises(ValueError):
            verify_task_bundle(io.BytesIO(current_raw), current_trust, pin)
    finally:
        if child.is_alive():
            child.kill()
            child.join(timeout=5)


def test_capacity_input_is_exact_bounded_integer_workload():
    from datetime import datetime, timedelta, timezone

    from tests.fixtures.a33_demo import task_policy

    policy = task_policy(expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
    catalog = {"quotes": [{"quote_id": "quote-001", "quote_version": "1", "lines": []}]}
    original = copy.deepcopy((policy, catalog))
    widened, resources = capacity_workload(task_policy=policy, catalog=catalog)
    assert (policy, catalog) == original
    assert len(widened["constraints"]["skus"]) == 256
    assert len(set(widened["constraints"]["skus"])) == 256
    assert sum(line["unit_price_fen"] for line in resources["quotes"][0]["lines"]) == 70000
    body = invocation_body("task-demo", TOOLS[2], idempotency_key="capacity", capacity_items=256)
    assert len(body["params"]["items"]) == 256
    assert len(canonical_json_bytes(body)) < 65536
    for invalid in (True, False, 0, 2, 255, 257, 256.0, "256"):
        with pytest.raises(ValueError):
            workload_skus(invalid)
