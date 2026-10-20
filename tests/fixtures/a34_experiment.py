"""Owned multi-task experiment assembly using real normal AS/holder/audit APIs.

Operator provisions policy/catalog only, never signs or inserts grants. Every
TaskHolder lives at the exact existing role UID and privately receives tokens
through the original credential-checked handoff. The runner sends labels and
public operation IDs only. No test fixture minting of AS grants is permitted.
"""

import os
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

import psycopg
from psycopg import sql

from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.authorization.provisioning import register_task_policy
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.demo.client import DemoClient
from agent_guard.demo.config import (
    DelegationRequest,
    DemoRunConfig,
    RootRequest,
    holder_config,
)
from agent_guard.demo.handoff import receive_child, send_child
from agent_guard.demo.provision import (
    bootstrap_journal,
    build_gateway,
    freeze_export_inputs,
    readonly_export_factory,
    register_bootstrap,
)
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

TOOLS = (
    "procurement.request.read",
    "procurement.document.read",
    "procurement.order.create",
    "notification.template.send",
)


@dataclass(frozen=True)
class TaskInputs:
    task_id: str
    tenant_id: str
    subject: str
    expires_at: datetime

    def __post_init__(self):
        import re

        if (
            any(
                type(value) is not str
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}", value) is None
                for value in (self.task_id, self.tenant_id, self.subject)
            )
            or not isinstance(self.expires_at, datetime)
            or self.expires_at.tzinfo is None
        ):
            raise ValueError("bounded safe task identifiers and aware expiry required")

    @property
    def resources(self):
        return {name: name + "." + self.task_id for name in ("req", "doc", "quote", "delivery")}

    def policy(self):
        r = self.resources
        return dict(
            tenant_id=self.tenant_id,
            task_id=self.task_id,
            owner_subject=self.subject,
            scope="openid " + " ".join(TOOLS),
            constraints={
                "request_ids": [r["req"]],
                "document_ids": [r["doc"]],
                "quote_versions": [r["quote"] + "@1"],
                "skus": ["sku-001"],
                "max_quantity": 2,
                "delivery_ids": [r["delivery"]],
                "template_ids": ["order-created"],
                "recipient_ids": ["user-demo"],
            },
            amount_limit_fen=100000,
            call_limit=12,
            task_expires_at=self.expires_at,
        )


def scoped_run(config, task: TaskInputs):
    """Trusted operator/role view, retaining exact UIDs/private mounts/public trust."""
    if (
        type(config) is not DemoRunConfig
        or type(task) is not TaskInputs
        or task.tenant_id != config.scope["tenant_id"]
    ):
        raise ValueError("approved owned task view required")
    roles = {}
    for name, role in config.roles.items():
        # The frozen handoff contract requires the exact child.sock path.
        # JIT authorization handoffs are serialized per pair; the checked
        # run/task envelope distinguishes tasks while private holders retain
        # their completed task tokens for concurrent business requests.
        pairs = tuple(replace(pair, task_id=task.task_id) for pair in role.handoff)
        roles[name] = replace(role, handoff=pairs)
    return replace(
        config,
        scope=MappingProxyType(dict(config.scope, task_id=task.task_id)),
        roles=MappingProxyType(roles),
    )


def provision_tasks(config, *, operator_dsn, tasks):
    """True server-side TaskPolicy registration on operator connection; no grants."""
    if (
        os.getuid() != config.roles["operator"].uid
        or not tasks
        or len({t.task_id for t in tasks}) != len(tasks)
    ):
        raise ValueError("distinct operator-approved task inputs required")
    with psycopg.connect(operator_dsn, connect_timeout=5) as conn:
        conn.execute("SET LOCAL statement_timeout='30s'")
        for task in tasks:
            if type(task) is not TaskInputs or task.tenant_id != config.scope["tenant_id"]:
                raise ValueError("approved tenant required")
            register_task_policy(conn, **task.policy())


def task_catalog(tasks):
    catalog = TrustedCatalog()
    catalog.add_template(CatalogTemplate("order-created"))
    catalog.add_recipient(CatalogRecipient("user-demo"))
    for task in tasks:
        r = task.resources
        catalog.add_request(CatalogRequest(r["req"], task.tenant_id, task.task_id))
        catalog.add_document(CatalogDocument(r["doc"], r["req"]))
        catalog.add_quote(
            CatalogQuote(
                r["quote"],
                "1",
                "supplier-001",
                r["req"],
                (CatalogQuoteLine("sku-001", 1, 70000),),
            )
        )
        catalog.add_delivery(CatalogDelivery(r["delivery"], task.tenant_id, r["req"]))
    return catalog


def task_catalog_mapping(tasks):
    """Approved normal GatewayConfig catalog input, frozen before server build."""
    return {
        "requests": [
            {
                "request_id": t.resources["req"],
                "tenant_id": t.tenant_id,
                "task_id": t.task_id,
                "status": "APPROVED",
            }
            for t in tasks
        ],
        "documents": [
            {
                "document_id": t.resources["doc"],
                "request_id": t.resources["req"],
                "body": "synthetic document body",
            }
            for t in tasks
        ],
        "quotes": [
            {
                "quote_id": t.resources["quote"],
                "quote_version": "1",
                "supplier_id": "supplier-001",
                "request_id": t.resources["req"],
                "lines": [{"sku": "sku-001", "quantity": 1, "unit_price_fen": 70000}],
            }
            for t in tasks
        ],
        "deliveries": [
            {
                "delivery_id": t.resources["delivery"],
                "tenant_id": t.tenant_id,
                "request_id": t.resources["req"],
            }
            for t in tasks
        ],
        "templates": [{"template_id": "order-created", "body": "order-created"}],
        "recipients": [{"recipient_id": "user-demo"}],
    }


def task_body(task, tool_id, *, key, order_operation_id=None):
    r = task.resources
    params = {
        TOOLS[0]: {"request_id": r["req"]},
        TOOLS[1]: {"request_id": r["req"], "document_id": r["doc"]},
        TOOLS[2]: {
            "request_id": r["req"],
            "quote_id": r["quote"],
            "quote_version": "1",
            "items": [{"sku": "sku-001", "quantity": 1}],
            "delivery_id": r["delivery"],
        },
        TOOLS[3]: {
            "template_id": "order-created",
            "recipient_id": "user-demo",
            "operation_id": order_operation_id,
        },
    }
    if tool_id not in TOOLS or tool_id == TOOLS[3] and order_operation_id is None:
        raise ValueError("canonical tool and accepted same-task order required")
    return {
        "profile": "GM-MVP-1",
        "task_id": task.task_id,
        "tool_id": tool_id,
        "tool_version": "1",
        "idempotency_key": key,
        "params": params[tool_id],
    }


class TaskHolder:
    def __init__(self, config, *, role, task, capture_directory=None):
        self.run = scoped_run(config, task)
        self.config = holder_config(self.run, holder=role)
        self.client = DemoClient(self.config)
        self.task, self.role = task, role
        self._token = None
        self._issued = None
        self.capture = None
        if capture_directory is not None:
            from experiments.agent_guard_bench.research_evidence import ResearchEvidence

            self.capture = ResearchEvidence(capture_directory)

    def root(self, *, login):
        if self.role != "planner":
            raise ValueError("planner browser root only")
        self._token = self.client.browser_root(
            login=login,
            request=RootRequest(self.task.task_id, self.task.policy()["scope"]),
        ).access_token
        self._issued = time.monotonic()

    def receive(self, *, parent):
        pair = next(
            p for p in self.run.roles[self.role].handoff if p.peer_client_id == "agent-" + parent
        )
        token = receive_child(pair, expected_parent="agent-" + parent)
        self._token = token.access_token
        self._issued = time.monotonic()

    def delegate(self, *, key):
        if self._token is None or self.role not in ("planner", "selector"):
            raise ValueError("authorized parent required")
        target, amount, calls, depth, ttl = (
            ("selector", 80000, 10, 1, 240)
            if self.role == "planner"
            else ("executor", 70000, 8, 0, 180)
        )
        request = DelegationRequest(
            "agent-" + target,
            " ".join(TOOLS),
            canonical_json_bytes(dict(self.task.policy()["constraints"], max_quantity=1)),
            key,
            ttl,
            amount,
            calls,
            depth,
        )
        child = self.client.exchange(parent_token=self._token, request=request)
        pair = next(
            p for p in self.run.roles[self.role].handoff if p.peer_client_id == "agent-" + target
        )
        return send_child(pair, target="agent-" + target, token=child)

    def raw_request(self, body, *, purpose="invoke"):
        """Only role-private channel consumers may receive this secret request."""
        if self._token is None or self._issued is None or time.monotonic() - self._issued >= 240:
            raise ValueError("task JIT deadline; no renewal or replacement")
        from tongsuopy.crypto import serialization

        key = serialization.load_pem_private_key(
            read_private_file(self.config.role.private_files["signing_key"]),
            password=None,
        )
        endpoint = self.config.gateway_origin + (
            "/v1/invocations" if purpose == "invoke" else "/v1/operations/query"
        )
        proof = sign_ag_proof(
            key,
            kid=self.config.kid,
            client_id=self.config.client_id,
            purpose=purpose,
            endpoint=endpoint,
            body=body,
            token=self._token,
            now=int(time.time()),
        )
        return {
            "token": self._token,
            "proof": proof,
            "body": canonical_json_bytes(body),
            "now": int(time.time()),
        }

    def invoke_full(self, body):
        if self._token is None:
            raise ValueError("no genuine AS authorization")
        return self.client.invoke(token=self._token, body=body)

    def query_full(self, operation_id):
        return self.client.query(token=self._token, operation_id=operation_id)

    def revoke_task(self):
        """Real browser session/CSRF cancellation; no SQL or asserted subject."""
        import ssl
        import urllib.error
        import urllib.request

        if self.role != "planner":
            raise ValueError("authenticated task-owner browser role required")
        # The normal browser client owns this actual cookie jar. Revocation
        # uses its emitted session+CSRF cookie, never a constructed context.
        cookies = self.client._cookies
        session = next((c.value for c in cookies if c.name == "ag_session"), None)
        if session is None or session.count("~") != 1:
            raise ValueError("genuine authenticated browser session required")
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(
                context=ssl.create_default_context(cafile=str(self.config.ca_file))
            ),
            urllib.request.HTTPCookieProcessor(cookies),
        )
        wire = urllib.request.Request(
            self.config.issuer + "/ag/tasks/" + self.task.task_id + "/revoke",
            data=canonical_json_bytes({"reason_code": "USER_CANCELLED"}),
            method="POST",
            headers={"Content-Type": "application/json", "X-CSRF-Token": session.split("~")[1]},
        )
        try:
            response = opener.open(wire, timeout=30)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError("bounded revocation response required")
            return response.status, load_strict_json(raw)

    def authorization_metadata(self):
        """Public IDs from this holder's verified genuine AS token; no secrets."""
        from agent_guard.authorization.claims import validate_access_claims
        from agent_guard.crypto.sm import verify_compact_jws

        claims = validate_access_claims(
            verify_compact_jws(
                self._token, expected_type="ag-at+jwt", trusted_keys=self.config.as_keys
            ),
            issuer=self.config.issuer,
            now=int(time.time()),
        ).raw
        if (claims["client_id"], claims["ag_task_id"], claims["ag_tenant_id"]) != (
            self.config.client_id,
            self.task.task_id,
            self.task.tenant_id,
        ):
            raise ValueError("genuine holder task binding required")
        return {
            "run_id": self.run.run_id,
            "task_id": claims["ag_task_id"],
            "tenant_id": claims["ag_tenant_id"],
            "client_id": claims["client_id"],
            "grant_id": claims["ag_grant_id"],
            "root_id": claims["ag_root_id"],
            "parent_id": claims["ag_parent_id"],
            "expires_at": claims["exp"],
            "amount_limit_fen": claims["ag_limits"]["amount_fen"],
            "call_limit": claims["ag_limits"]["calls"],
        }

    def request_research(self, body, *, mode, purpose="invoke", proof_override=None):
        """Role-private genuine JIT request over the existing verified origin.

        Only the public response crosses the runner boundary. No token/proof
        leaves this role except over its CA-verified fixed gateway connection.
        """
        import ssl
        import urllib.error
        import urllib.request

        if mode not in ("noAtomic", "Bearer") or purpose not in (
            "invoke",
            "result-read",
        ):
            raise ValueError("fixed research security channel required")
        if mode == "Bearer":
            if (
                self._token is None
                or self._issued is None
                or time.monotonic() - self._issued >= 240
            ):
                raise ValueError("task JIT deadline; no renewal or replacement")
            request = {"token": self._token, "body": canonical_json_bytes(body), "proof": None}
        else:
            request = self.raw_request(body, purpose=purpose)
        url = self.config.gateway_origin + (
            "/v1/invocations" if purpose == "invoke" else "/v1/operations/query"
        )
        context = ssl.create_default_context(cafile=str(self.config.ca_file))
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context),
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": ("AGPoP " if mode == "noAtomic" else "Bearer ") + request["token"],
        }
        proof = request["proof"] if proof_override is None else proof_override
        if proof is not None:
            headers["AG-Proof"] = proof
        if self.capture is not None:
            self.capture.stage(request["token"], proof, request["body"])
        wire = urllib.request.Request(
            url,
            data=request["body"],
            method="POST",
            headers=headers,
        )
        try:
            response = opener.open(wire, timeout=30)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError("bounded research response required")
            return response.status, load_strict_json(raw)


class ACLClient:
    """Role-private password client: no AS token or holder signing operation."""

    def __init__(self, config, *, role, password):
        if type(password) is not str or not password:
            raise ValueError("explicit approved private role credential required")
        self.config = holder_config(config, holder=role)
        self.role, self.password = role, password

    def request(self, body, *, purpose="invoke", credential_override=None):
        import ssl
        import urllib.error
        import urllib.request

        if purpose not in ("invoke", "result-read"):
            raise ValueError("fixed ACL purpose required")
        url = self.config.gateway_origin + (
            "/v1/invocations" if purpose == "invoke" else "/v1/operations/query"
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(
                context=ssl.create_default_context(cafile=str(self.config.ca_file))
            ),
        )
        wire = urllib.request.Request(
            url,
            data=canonical_json_bytes(body),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-ACL-Role": self.role,
                "Authorization": "ACL "
                + (self.password if credential_override is None else credential_override),
            },
        )
        try:
            response = opener.open(wire, timeout=30)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError("bounded ACL response required")
            return response.status, load_strict_json(raw)


def grant_research_authority(conn, *, research_role):
    """Owned operator-only permission adaptation; production budget UPDATE zero."""
    role = sql.Identifier(research_role)
    for table, column in (
        ("ag_principals", "active"),
        ("ag_tasks", "created_at"),
        ("ag_grants", "revoked_at"),
    ):
        conn.execute(
            sql.SQL("GRANT SELECT, UPDATE ({}) ON public.{} TO {}").format(
                sql.Identifier(column), sql.Identifier(table), role
            )
        )
    conn.execute(sql.SQL("GRANT SELECT ON public.ag_grant_tokens TO {}").format(role))
    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA r34 TO {}").format(role))
    conn.execute(
        sql.SQL("GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA r34 TO {}").format(role)
    )
    conn.execute(sql.SQL("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA r34 TO {}").format(role))


def initialize_research_paths(config, *, operator_dsn, task_paths):
    """Trusted setup from public IDs of already completed genuine AS handoffs.

    This performs no invocation or grant creation. Every signed persisted path
    is checked against the independently approved task and exact three roles,
    then all counters are initialized before any competing measured request.
    """
    if os.getuid() != config.roles["operator"].uid or not task_paths:
        raise ValueError("owned operator and completed AS paths required")
    result = []
    with psycopg.connect(operator_dsn, connect_timeout=5) as conn:
        conn.execute("SET LOCAL statement_timeout='30s'")
        for task, ids in task_paths:
            if type(task) is not TaskInputs or len(ids) != 3 or len(set(ids)) != 3:
                raise ValueError("approved complete root/mid/leaf path required")
            rows = conn.execute(
                "SELECT g.grant_id,g.parent_grant_id,g.root_grant_id,g.depth,"
                "g.holder_client_id,g.tenant_id,g.task_id,g.subject FROM ag_grants g "
                "JOIN ag_grant_tokens t USING(grant_id) WHERE g.grant_id=ANY(%s) "
                "ORDER BY g.depth",
                (list(ids),),
            ).fetchall()
            if len(rows) != 3 or any(
                row
                != (
                    ids[i],
                    ids[i - 1] if i else None,
                    ids[0],
                    i,
                    "agent-" + ("planner", "selector", "executor")[i],
                    task.tenant_id,
                    task.task_id,
                    task.subject,
                )
                for i, row in enumerate(rows)
            ):
                raise ValueError("completed genuine AS path does not match approval")
            for grant_id in ids:
                conn.execute(
                    "INSERT INTO r34.counters(grant_id) VALUES(%s) ON CONFLICT DO NOTHING",
                    (grant_id,),
                )
            result.append({"task_id": task.task_id, "path_ids": tuple(ids)})
    return tuple(result)


def research_connection_manifest(store):
    """Actual role/TLS/minimum SHARE permissions, with no credential output."""
    from experiments.agent_guard_bench.research_store import ResearchStore

    if type(store) is not ResearchStore:
        raise ValueError("owned research connection required")
    with store.transaction(readonly=True) as conn:
        facts = conn.execute(
            "SELECT current_user AS role,current_database() AS database,"
            "(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()) AS tls"
        ).fetchone()
        permissions = {}
        for table, column in (
            ("ag_principals", "active"),
            ("ag_tasks", "created_at"),
            ("ag_grants", "revoked_at"),
            ("ag_grants", "amount_reserved"),
            ("ag_grants", "amount_settled"),
            ("ag_grants", "calls_reserved"),
            ("ag_grants", "calls_settled"),
        ):
            permissions[table + "." + column] = conn.execute(
                "SELECT has_column_privilege(current_user,%s,%s,'UPDATE') AS allowed",
                (table, column),
            ).fetchone()["allowed"]
    if (
        not facts["tls"]
        or any(
            permissions["ag_grants." + name]
            for name in ("amount_reserved", "amount_settled", "calls_reserved", "calls_settled")
        )
        or not all(
            permissions[name]
            for name in (
                "ag_principals.active",
                "ag_tasks.created_at",
                "ag_grants.revoked_at",
            )
        )
    ):
        raise ValueError("isolated TLS research role with nonbudget SHARE authority required")
    return dict(facts, mode=store.mode, owner=store.owner, update_permissions=permissions)


def bootstrap_task_streams(config, *, tasks, stopped, trust_for, credentials_for):
    """Real four-writer stop receipt -> remote commit -> exact local confirm.

    Must be called on each completed JIT authorization wave while actual four
    writer processes and credentials are stopped/drained. No fabricated receipt.
    """
    result = {}
    for task in tasks:
        view = scoped_run(config, task)
        descriptor = bootstrap_journal(view, stopped=stopped)
        register_bootstrap(
            view,
            stopped=stopped,
            descriptor=descriptor,
            trust=trust_for(descriptor),
            **credentials_for(descriptor),
        )
        result[task.task_id] = descriptor
    return result


def freeze_task_exports(config, *, tasks, stopped, reader_for, public_trust_for, out_dir):
    return {
        task.task_id: freeze_export_inputs(
            scoped_run(config, task),
            stopped=stopped,
            reader=reader_for(task),
            public_trust=public_trust_for(task),
            out_dir=Path(out_dir) / task.task_id,
        )
        for task in tasks
    }


def build_task_export_gateway(config, *, task, approved, inputs, credentials, spool_parent):
    view = scoped_run(config, task)
    return build_gateway(
        view,
        approved=approved,
        export_connection_factory=readonly_export_factory(view, role="gateway"),
        export_spool_parent=spool_parent,
        export_inputs=inputs,
        export_credentials=credentials,
    )


def build_full_wave_app(config, *, tasks, approved):
    """Production public GW with a frozen <=50-task catalog, unchanged256 cap.

    Preapproved official tasks are partitioned before measurement. Each wave
    uses a real four-writer stop/bootstrap/resume boundary and genuine new AS
    authorization; historical operation/evidence/stream data stay persistent.
    """
    if not 1 <= len(tasks) <= 50 or os.getuid() != config.roles["gateway"].uid:
        raise ValueError("approved fifty-slot wave and gateway UID required")
    from agent_guard.demo.provision import _dsn
    from agent_guard.gateway.config import load_gateway_config, load_gateway_secrets
    from agent_guard.gateway.factory import build_app

    role = config.roles["gateway"]
    value = load_strict_json(read_private_file(role.public_config_file))
    value["catalog"] = task_catalog_mapping(tasks)
    value["max_workers"] = 32
    value["did_documents"] = approved.factory_documents()
    return build_app(
        load_gateway_config(canonical_json_bytes(value)),
        load_gateway_secrets(read_private_file(role.private_files["secrets"])),
        gateway_dsn=_dsn(role, "authority_dsn"),
        downstream_dsn=_dsn(role, "downstream_dsn"),
    )


def task_operation_registries(config, *, tasks, directory):
    """Distinct per-task normal registries, same exact operator/worker mounts."""
    from agent_guard.demo.worker import OwnedOperationRegistry

    result = {}
    for task in tasks:
        path = Path(directory) / task.task_id
        if os.getuid() == config.roles["operator"].uid and not path.exists():
            path.mkdir(mode=0o750)
            os.chown(path, -1, config.roles["worker"].gid)
            path.chmod(0o750)
        result[task.task_id] = OwnedOperationRegistry(
            path,
            run_id=config.run_id,
            owner_id=config.owner_id,
            tenant_id=task.tenant_id,
            task_id=task.task_id,
            runner_uid=config.roles["operator"].uid,
            worker_uid=config.roles["worker"].uid,
            reader_gid=config.roles["worker"].gid,
        )
    return result


class FullTaskWorker:
    """Fair persistent dispatcher of original production Worker per task."""

    def __init__(self, config, *, tasks, registries):
        from agent_guard.demo.config import worker_config
        from agent_guard.demo.worker import Worker

        base = worker_config(config)
        catalog = task_catalog(tasks)
        self.workers = tuple(
            Worker(
                replace(
                    base,
                    task_id=task.task_id,
                    catalog=catalog,
                    served_requests=frozenset(t.resources["req"] for t in tasks),
                ),
                operations=registries[task.task_id],
            )
            for task in tasks
        )
        self.cursor = 0

    def step(self):
        if not self.workers:
            return ()
        selected = tuple(
            self.workers[(self.cursor + i) % len(self.workers)]
            for i in range(min(32, len(self.workers)))
        )
        self.cursor = (self.cursor + len(selected)) % len(self.workers)
        reports = tuple(worker.step(batch_size=1) for worker in selected)
        if any(report.errors for report in reports):
            raise ValueError("full task worker failed: " + repr(tuple(r.errors for r in reports)))
        return reports

    def serve(self, *, deadline, stop_event):
        if not self.workers:
            raise ValueError("approved tasks required")
        while time.monotonic() < deadline and not stop_event.is_set():
            self.step()
            stop_event.wait(0.1)


class FullPublisher:
    """Real signed READY plus independent DeliveryWorker on approved streams."""

    def __init__(self, *, publisher, streams, delivery=None, deliveries=None):
        from agent_guard.audit.delivery import DeliveryWorker
        from agent_guard.execution.receipt_publication import InternalPublisher

        if (
            type(publisher) is not InternalPublisher
            or not streams
            or len(set(streams)) != len(streams)
        ):
            raise ValueError("genuine signer/delivery and registered stream IDs required")
        if deliveries is None:
            if len(streams) != 1 or type(delivery) is not DeliveryWorker:
                raise ValueError("each stream requires its own scoped audit client")
            deliveries = {streams[0]: delivery}
        if delivery is not None and len(streams) != 1:
            raise ValueError("single-stream credential cannot serve multiple tasks")
        if set(deliveries) != set(streams) or any(
            type(worker) is not DeliveryWorker for worker in deliveries.values()
        ):
            raise ValueError("exact independently scoped stream delivery workers required")
        self.publisher, self.deliveries, self.streams = publisher, dict(deliveries), tuple(streams)
        self.cursor = ""
        self.delivery_cursor = 0

    def step(self):
        rows = self.publisher.pending_page(after_operation_id=self.cursor, limit=64)
        for operation in rows:
            self.publisher.publish(operation)
        self.cursor = rows[-1] if rows else ""
        selected = tuple(
            self.streams[(self.delivery_cursor + i) % len(self.streams)]
            for i in range(min(64, len(self.streams)))
        )
        self.delivery_cursor = (self.delivery_cursor + len(selected)) % len(self.streams)
        return tuple(self.deliveries[stream].deliver_once(stream) for stream in selected)

    def serve(self, *, deadline, stop_event):
        while time.monotonic() < deadline and not stop_event.is_set():
            outcomes = self.step()
            if any(o.status not in ("ACKED", "NO_PENDING") for o in outcomes):
                raise ValueError("independent audit pending/gap; retain evidence")
            stop_event.wait(0.1)


def build_research(
    config, *, mode, owned_authority_dsn, approved, evidence_dir, tasks, acl_registry=()
):
    """Explicit isolated research connection; normal real signed source/trust."""
    from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
    from agent_guard.gateway.config import trusted_inputs
    from experiments.agent_guard_bench.research_contracts import ResearchAuthenticator
    from experiments.agent_guard_bench.research_evidence import ResearchEvidence
    from experiments.agent_guard_bench.research_service import ResearchService
    from experiments.agent_guard_bench.research_store import ResearchStore

    if os.getuid() != config.roles["gateway"].uid or approved.run_id != config.run_id:
        raise ValueError("gateway role/frozen approval required")
    role = config.roles["gateway"]
    value = load_strict_json(read_private_file(role.public_config_file))
    value["did_documents"] = approved.factory_documents()
    value["catalog"] = task_catalog_mapping(tasks)
    keys, identities, registrations, _ = trusted_inputs(value)
    provider = PermissionSnapshotProvider(
        owned_authority_dsn,
        issuer=value["issuer"],
        as_keys=keys,
        registrations=registrations,
    )
    auth = ResearchAuthenticator(
        issuer=value["issuer"],
        as_keys=keys,
        identities=identities,
        provider=provider,
        evidence=ResearchEvidence(evidence_dir),
        acl_registry=acl_registry,
    )
    return ResearchService(
        store=ResearchStore(owned_authority_dsn, mode=mode, owner=config.owner_id),
        authenticator=auth,
        catalog=task_catalog(tasks),
    )


def build_research_worker(config, *, mode, owned_authority_dsn, tasks):
    """Distinct normal worker UID/DS credentials; accepted immutable intents only."""
    from agent_guard.demo.provision import _dsn
    from agent_guard.tools.downstream import MockDownstream
    from experiments.agent_guard_bench.research_service import ResearchService
    from experiments.agent_guard_bench.research_store import ResearchStore
    from experiments.agent_guard_bench.research_worker import ResearchWorker

    role = config.roles["worker"]
    if os.getuid() != role.uid:
        raise ValueError("actual internal worker UID required")
    secret = read_private_file(role.private_files["downstream_secret"]).decode("ascii")
    service = ResearchService(
        store=ResearchStore(owned_authority_dsn, mode=mode, owner=config.owner_id),
        authenticator=None,
        catalog=task_catalog(tasks),
    )
    downstream = MockDownstream(
        _dsn(role, "downstream_dsn"),
        service_secret=secret,
        approved_suppliers=frozenset({"supplier-001"}),
        approved_recipients=frozenset({"user-demo"}),
        served_requests=frozenset(t.resources["req"] for t in tasks),
    )
    return ResearchWorker(service=service, downstream=downstream, service_secret=secret)


def build_full_publisher(config, *, registrations, credential_map):
    """Real normal signer and one separately scoped audit credential per task."""
    from agent_guard.audit.client import AuditClient
    from agent_guard.audit.contracts import CheckpointTrust
    from agent_guard.audit.delivery import DeliveryWorker
    from agent_guard.crypto.sm import serialize_sm2_public_key
    from agent_guard.demo.provision import _dsn
    from agent_guard.gateway.receipt_config import load_receipt_worker_config
    from agent_guard.server.factory import _load_public_key

    role = config.roles["publisher"]
    if os.getuid() != role.uid or not registrations or set(registrations) != set(credential_map):
        raise ValueError("real publisher UID and exact committed task registrations required")
    dsn = _dsn(role, "authority_dsn")
    publisher = load_receipt_worker_config(role.private_files["publisher_config"]).publisher(dsn)
    public = load_strict_json(config.public_manifest.read_bytes())
    trust = CheckpointTrust(
        "audit-sign-1",
        "AUDIT_SIGNER",
        serialize_sm2_public_key(_load_public_key(public["audit_keys"]["audit-sign-1"], "audit")),
        1,
        None,
    )
    deliveries = {}
    used = set()
    for task_id, descriptor in registrations.items():
        if (descriptor.scope.tenant_id, descriptor.scope.task_id, descriptor.scope.gateway_id) != (
            config.scope["tenant_id"],
            task_id,
            config.scope["gateway_origin"],
        ):
            raise ValueError("committed task stream scope required")
        credentials = credential_map[task_id]
        pair = (credentials["writer_id"], credentials["publisher_reader_id"])
        if any(identifier in used for identifier in pair) or pair[0] == pair[1]:
            raise ValueError("task audit principals must be independently scoped")
        used.update(pair)
        client = AuditClient(
            config.endpoints["audit_origin"],
            ca_file=str(role.public_config_file.parent / "ca.pem"),
            writer_credential=credentials["writer_id"] + ":" + credentials["writer_secret"],
            reader_credential=credentials["publisher_reader_id"]
            + ":"
            + credentials["publisher_reader_secret"],
        )
        deliveries[descriptor.scope.stream_id] = DeliveryWorker(
            lambda: psycopg.connect(dsn), client, trust=(trust,)
        )
    return FullPublisher(publisher=publisher, streams=tuple(deliveries), deliveries=deliveries)


def task_audit_credentials(config, *, tasks, directory):
    """Operator-private persistent CSPRNG credentials, separately scoped per task.

    The returned map is private material for operator registration and the
    approved publisher/export channels. Only credential IDs may enter public
    manifests. Existing files are reused exactly for idempotent registration.
    """
    import secrets
    import uuid

    role = config.roles["operator"]
    directory = Path(directory)
    if os.getuid() != role.uid or not directory.is_relative_to(role.public_config_file.parent):
        raise ValueError("operator-private credential directory required")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise ValueError("private owned credential directory required")
    purposes = ("writer", "reader", "publisher_reader", "export_reader", "gateway_reader")
    result = {}
    for task in tasks:
        path = directory / (task.task_id + ".json")
        if not path.exists():
            value = {}
            for purpose in purposes:
                value[purpose + "_id"] = "r34-" + uuid.uuid4().hex + "-" + purpose
                value[purpose + "_secret"] = secrets.token_urlsafe(32)
            with path.open("xb") as stream:
                os.chmod(path, 0o600)
                stream.write(canonical_json_bytes(value))
                stream.flush()
                os.fsync(stream.fileno())
        value = load_strict_json(read_private_file(path))
        if set(value) != {p + suffix for p in purposes for suffix in ("_id", "_secret")}:
            raise ValueError("exact persisted task credential record required")
        if any(type(v) is not str or not v for v in value.values()):
            raise ValueError("invalid persisted task credential")
        result[task.task_id] = value
    return result


def task_registration_arguments(credentials):
    """Private arguments for the real normal remote-commit/local-confirm API."""
    return {
        "writer_credential_id": credentials["writer_id"],
        "writer_credential": credentials["writer_secret"],
        "reader_credential_id": credentials["reader_id"],
        "reader_credential": credentials["reader_secret"],
        "additional_readers": tuple(
            (credentials[purpose + "_id"], credentials[purpose + "_secret"])
            for purpose in ("publisher_reader", "export_reader", "gateway_reader")
        ),
    }


def fixture_manifest(config, *, tasks):
    """Actual public owner/UID/resource/module provenance; no credentials."""
    import hashlib
    import importlib
    import importlib.metadata

    resources = load_strict_json((config.base_dir / "allocated-resources.json").read_bytes())
    if (resources["run_id"], resources["owner_id"]) != (config.run_id, config.owner_id):
        raise ValueError("exact owned normal resource manifest required")
    if set(resources.get("roles", {})) != set(config.roles) or any(
        resources["roles"][name]["uid"] != role.uid
        or len(resources["roles"][name]["container_id"]) != 64
        for name, role in config.roles.items()
    ):
        raise ValueError("actual allocated role UIDs and full container identities required")
    modules = []
    for name in (
        "agent_guard.authorization.verifier",
        "agent_guard.demo.client",
        "agent_guard.demo.handoff",
        "agent_guard.execution.receipt_publication",
        "agent_guard.audit.delivery",
    ):
        module = importlib.import_module(name)
        path = Path(module.__file__)
        if "site-packages" not in path.parts:
            raise ValueError("noneditable normal installed module required")
        modules.append(
            {
                "module": name,
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    direct = importlib.metadata.distribution("agent-guard").read_text("direct_url.json")
    origin = load_strict_json(direct.encode()) if direct else None
    if origin is not None and origin.get("dir_info", {}).get("editable"):
        raise ValueError("editable production installation forbidden")
    return {
        "run_id": config.run_id,
        "owner_id": config.owner_id,
        "uid": os.getuid(),
        "pid": os.getpid(),
        "resources": resources,
        "tasks": tuple(t.task_id for t in tasks),
        "modules": modules,
        "installed_origin": origin,
        "role_proxy_variables": tuple(
            name
            for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")
            if os.environ.get(name)
        ),
        "mode_mapping": {
            "staticACL": "staticACL",
            "realSM2delegation_noAtomic": "noAtomic",
            "complete": "full",
            "realSM2Bearer": "Bearer",
        },
    }


def task_public_trust(config, *, task, descriptor):
    """Independent normal public keys plus the approved task's exact catalog."""
    from dataclasses import asdict

    from agent_guard.audit.contracts import RegistrationDescriptor
    from agent_guard.contracts.encoding import b64url_encode
    from agent_guard.crypto.sm import serialize_sm2_public_key
    from agent_guard.server.factory import _load_public_key

    if (
        type(task) is not TaskInputs
        or type(descriptor) is not RegistrationDescriptor
        or (descriptor.scope.gateway_id, descriptor.scope.tenant_id, descriptor.scope.task_id)
        != (config.scope["gateway_origin"], task.tenant_id, task.task_id)
    ):
        raise ValueError("actual registered descriptor and independently approved task required")
    public = load_strict_json(config.public_manifest.read_bytes())
    value = {
        "version": "AG-TASK-TRUST-1",
        "issuer": public["issuer"],
        "as_keys": {
            kid: b64url_encode(serialize_sm2_public_key(_load_public_key(pem, "AS")))
            for kid, pem in public["as_keys"].items()
        },
        "gateway_keys": {
            kid: b64url_encode(serialize_sm2_public_key(_load_public_key(pem, "GW")))
            for kid, pem in public["receipt_keys"].items()
        },
        "holder_keys": {r["kid"]: r["spki_der"] for r in public["registrations"]},
        "historical_registrations": [
            {
                **{k: r[k] for k in ("tenant_id", "client_id", "did", "kid", "spki_der")},
                "active": True,
                "role": "HOLDER",
            }
            for r in public["registrations"]
        ],
        "catalog": task_catalog_mapping((task,)),
        "audit_keys": [
            {
                "kid": kid,
                "role": "AUDIT_SIGNER",
                "spki_der": b64url_encode(serialize_sm2_public_key(_load_public_key(pem, "audit"))),
                "first_sequence": 1,
                "last_sequence": None,
            }
            for kid, pem in public["audit_keys"].items()
        ],
        "scope": asdict(descriptor.scope),
        "registration": {k: v for k, v in asdict(descriptor).items() if k != "scope"},
    }
    return canonical_json_bytes(value)
