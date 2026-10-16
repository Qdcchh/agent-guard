"""Normal isolated demo actors and fixed trusted owner control relay."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import shutil
import signal
import socket
import ssl
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_guard.contracts.encoding import (
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.demo.config import ROLES, SyntheticLogin, load_run_config, thaw


def task_policy(*, expires_at):
    tools = (
        "procurement.request.read",
        "procurement.document.read",
        "procurement.order.create",
        "notification.template.send",
    )
    return {
        "tenant_id": "tenant-demo",
        "task_id": "task-demo",
        "owner_subject": "user-demo",
        "scope": "openid " + " ".join(tools),
        "constraints": {
            "request_ids": ["req-001"],
            "document_ids": ["doc-001"],
            "quote_versions": ["quote-001@1"],
            "skus": ["sku-001"],
            "max_quantity": 2,
            "delivery_ids": ["office-001"],
            "template_ids": ["order-created"],
            "recipient_ids": ["user-demo"],
        },
        "amount_limit_fen": 100000,
        "call_limit": 12,
        "task_expires_at": expires_at.isoformat(),
    }


CONTROL = Path("/tmp/agent-guard-control/bridge.sock")


def _connect():
    import struct

    config = load_run_config(Path("/owned/run/run.json").read_bytes(), base_dir=Path("/owned/run"))
    uid = config.roles["operator"].uid
    if os.getuid() != uid:
        raise ValueError("operator control identity")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(600)
    sock.connect(str(CONTROL))
    _, peer, _ = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if peer != uid:
        sock.close()
        raise ValueError("operator bridge peer")
    return sock, config


def remote(action, **params):
    sock, config = _connect()
    with sock:
        sock.sendall(
            canonical_json_bytes(
                {"run_id": config.run_id, "owner_id": config.owner_id, "action": action, **params}
            )
            + b"\n"
        )
        with sock.makefile("rb") as stream:
            value = load_strict_json(stream.readline(65537))
            if not value.get("ok"):
                raise RuntimeError("owned supervisor action failed")
            return value["value"]


def bridge(config):
    """Only operator UID local sockets; host owns private native stdio pipe."""
    import secrets
    import struct

    uid = config.roles["operator"].uid
    if os.getuid() != uid:
        raise ValueError("operator bridge UID")
    CONTROL.parent.mkdir(mode=0o700)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(CONTROL))
    CONTROL.chmod(0o600)
    server.listen(16)
    clients = {}
    write_lock = threading.Lock()
    lock = threading.Lock()

    def emit(row):
        with write_lock:
            sys.stdout.buffer.write(canonical_json_bytes(row) + b"\n")
            sys.stdout.buffer.flush()

    def client(sock):
        ident = secrets.token_hex(16)
        try:
            _, peer, _ = struct.unpack(
                "3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            )
            if peer != uid:
                raise ValueError("operator socket peer")
            with lock:
                clients[ident] = sock
            with sock.makefile("rb") as stream:
                header = load_strict_json(stream.readline(65537))
                if (header.get("run_id"), header.get("owner_id")) != (
                    config.run_id,
                    config.owner_id,
                ):
                    raise ValueError("bridge scope")
                emit({"id": ident, "event": "open", "value": header})
                if header["action"] == "holder":
                    for raw in stream:
                        if len(raw) > 65536 or not raw.endswith(b"\n"):
                            raise ValueError("bounded holder control")
                        emit({"id": ident, "event": "data", "value": load_strict_json(raw)})
                    emit({"id": ident, "event": "end"})
                else:
                    # Keep local connection alive until the private host response.
                    while sock.fileno() >= 0:
                        time.sleep(0.02)
        except (OSError, ValueError):
            emit({"id": ident, "event": "end"})
        finally:
            with lock:
                clients.pop(ident, None)
            sock.close()

    def responses():
        try:
            for raw in sys.stdin.buffer:
                if len(raw) > 65536:
                    raise ValueError("host response capacity")
                row = load_strict_json(raw)
                with lock:
                    sock = clients.get(row["id"])
                if sock is not None:
                    if row.get("event") == "close":
                        sock.shutdown(socket.SHUT_RDWR)
                        sock.close()
                    else:
                        sock.sendall(canonical_json_bytes(row["value"]) + b"\n")
        finally:
            server.close()
            with lock:
                for sock in clients.values():
                    sock.close()

    threading.Thread(target=responses, daemon=True).start()
    try:
        while True:
            sock, _ = server.accept()
            threading.Thread(target=client, args=(sock,), daemon=True).start()
    finally:
        CONTROL.unlink(missing_ok=True)


class LiveProcess:
    """Poll actual trusted owner child handle plus stopped full container identity."""

    def __init__(self, row):
        self.row = row
        self.pid = row["pid"]

    def poll(self):
        row = remote("writer-status", role=self.row["role"])
        if (row["pid"], row["start_identity"], row["container_id"]) != (
            self.pid,
            self.row["start_identity"],
            self.row["container_id"],
        ):
            raise ValueError("drain native identity changed")
        return row["native_exit"] if row["container_stopped"] else None


def live_drain(config):
    from agent_guard.demo.config import DrainReceipt, WriterProcess

    rows = remote("drain")
    counts = writer_connections(config)
    writers = []
    for row in rows:
        event = threading.Event()
        process = LiveProcess(row)
        if counts[row["role"]] != 0 or process.poll() is None:
            raise ValueError("writer not truly drained")
        event.set()
        writers.append(
            WriterProcess(
                row["role"], row["pid"], row["start_identity"], row["argv_sha256"], process, event
            )
        )
    return DrainReceipt(
        config.run_id,
        config.owner_id,
        tuple(writers),
        datetime.now(timezone.utc).isoformat(),
        tuple(x["role"] for x in rows),
    )


def writer_connections(config):
    import psycopg

    from agent_guard.demo.provision import _dsn

    with psycopg.connect(_dsn(config.roles["operator"], "authority_dsn")) as conn:
        return {
            r: conn.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE usename=%s", ("demo_" + r,)
            ).fetchone()[0]
            for r in ("as", "gateway", "worker", "publisher")
        }


def relay(role):
    sock, config = _connect()
    sock.sendall(
        canonical_json_bytes(
            {"run_id": config.run_id, "owner_id": config.owner_id, "action": "holder", "role": role}
        )
        + b"\n"
    )

    def upload():
        try:
            for raw in sys.stdin.buffer:
                if len(raw) > 65536 or not raw.endswith(b"\n"):
                    raise ValueError("bounded role control")
                sock.sendall(raw)
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass

    threading.Thread(target=upload, daemon=True).start()
    with sock, sock.makefile("rb") as stream:
        for raw in stream:
            if len(raw) > 65536:
                raise ValueError("bounded role output")
            sys.stdout.buffer.write(raw)
            sys.stdout.buffer.flush()


def run_actor(stage, role):
    from datetime import datetime, timezone

    settings = load_strict_json(Path("/control/settings.json").read_bytes())
    RUN, OWNER = settings["run_id"], settings["owner_id"]
    UIDS = settings["uids"]
    root = Path("/owned/run")
    GIDS = {"planner-selector": 22000, "selector-executor": 22001}
    raw = Path("/proc/self/cmdline").read_bytes()
    print(
        json.dumps(
            {
                "native_process": True,
                "stage": stage,
                "pid": os.getpid(),
                "uid": os.getuid(),
                "start_ticks": Path("/proc/self/stat").read_text().split()[21],
                "argv_sha256": hashlib.sha256(raw).hexdigest(),
                "argv_nul_hex": raw.hex(),
            }
        ),
        file=sys.stderr,
        flush=True,
    )
    if stage == "init":
        from agent_guard.demo.init import init_run

        init_run(root, run_id=RUN, owner_id=OWNER, role_uids=UIDS, handoff_gids=GIDS)
        if settings["capacity_items"] == 256:
            from agent_guard.demo.holder import capacity_workload

            public_document = json.loads((root / "public-manifest.json").read_bytes())
            _, catalog = capacity_workload(
                task_policy=task_policy(
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)
                ),
                catalog=public_document["catalog"],
            )
            public_document["catalog"] = catalog
            (root / "public-manifest.json").write_bytes(canonical_json_bytes(public_document))
            for name in ("gateway", "worker"):
                path = root / name / "config.json"
                value = json.loads(path.read_bytes())
                value["catalog"] = catalog
                path.write_bytes(canonical_json_bytes(value))
        public = Path("/public/run")
        public.mkdir(mode=493)
        for r in ROLES:
            (public / r).mkdir(mode=493)
        (public / "ipc").mkdir(mode=493)
        for pair in GIDS:
            (public / "ipc" / pair).mkdir(mode=493)
        for f in ["run.json", "public-manifest.json", "resource-manifest.json"]:
            shutil.copyfile(root / f, public / f)
            (public / f).chmod(292)
        print("exclusive_init_complete")
        Path("/operator-tmp").chmod(0o1777)
        registry = Path("/registry")
        os.chown(registry, UIDS["operator"], UIDS["worker"])
        registry.chmod(0o750)
    elif stage == "pg-init":
        import secrets
        import subprocess

        from psycopg.conninfo import make_conninfo

        from agent_guard.demo.init import _openssl

        domains = {
            "authority": [
                "operator",
                "as",
                "gateway",
                "worker",
                "publisher",
                "export",
                "gateway_export",
            ],
            "downstream": ["operator", "gateway", "worker"],
            "audit": ["operator", "audit"],
        }
        connections = {
            r: {} for r in ["operator", "as", "gateway", "worker", "publisher", "export", "audit"]
        }
        tests = {}
        pg = root.parent / "pg"
        pg.mkdir(mode=448)
        for domain, roles in domains.items():
            directory = pg / domain
            directory.mkdir(mode=448)
            host = "pg-" + domain + ".agent-guard.test"
            _openssl(
                [
                    "req",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-keyout",
                    str(directory / "server.key"),
                    "-out",
                    str(directory / "server.csr"),
                    "-subj",
                    "/CN=" + host,
                ]
            )
            ext = directory / "ext"
            ext.write_text("subjectAltName=DNS:" + host + "\nextendedKeyUsage=serverAuth\n")
            _openssl(
                [
                    "x509",
                    "-req",
                    "-in",
                    str(directory / "server.csr"),
                    "-CA",
                    str(root / "operator/ca.pem"),
                    "-CAkey",
                    str(root / "operator/ca-key.pem"),
                    "-CAcreateserial",
                    "-out",
                    str(directory / "server.pem"),
                    "-days",
                    "2",
                    "-extfile",
                    str(ext),
                ]
            )
            shutil.copyfile(root / "operator/ca.pem", directory / "ca.pem")
            admin = secrets.token_urlsafe(32)
            (directory / "admin-password").write_text(admin)
            tests[domain] = make_conninfo(
                host=host,
                port="5432",
                dbname="ag_controller_test",
                user="postgres",
                password=admin,
                sslmode="verify-full",
                sslrootcert="/owned/run/operator/ca.pem",
            )
            sql = []
            for r in roles:
                password = secrets.token_urlsafe(32)
                sql.append(
                    "CREATE ROLE demo_"
                    + r
                    + " LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '"
                    + password
                    + "';"
                )
                key = "readonly_dsn" if r == "export" else domain + "_dsn"
                target = "gateway" if r == "gateway_export" else r
                if r == "gateway_export":
                    key = "readonly_dsn"
                connections[target][key] = make_conninfo(
                    host=host,
                    port="5432",
                    dbname="ag_" + domain,
                    user="demo_" + r,
                    password=password,
                    sslmode="verify-full",
                    sslrootcert="/owned/run/" + target + "/ca.pem",
                )
            owner = "demo_audit" if domain == "audit" else "demo_operator"
            sql += [
                "ALTER DATABASE ag_" + domain + " OWNER TO " + owner + ";",
                "ALTER SCHEMA public OWNER TO " + owner + ";",
                "REVOKE ALL ON DATABASE ag_" + domain + " FROM PUBLIC;",
                "REVOKE ALL ON SCHEMA public FROM PUBLIC;",
            ]
            sql += [
                "GRANT CONNECT ON DATABASE ag_"
                + domain
                + " TO demo_"
                + r
                + "; GRANT USAGE ON SCHEMA public TO demo_"
                + r
                + ";"
                for r in roles
            ]
            if domain == "authority":
                sql += [
                    "ALTER ROLE demo_export SET default_transaction_read_only=on;",
                    "ALTER ROLE demo_gateway_export SET default_transaction_read_only=on;",
                ]
            (directory / "init.sql").write_text("\n".join(sql))
            (directory / "pg_hba.conf").write_text(
                (
                    "local all all trust\nhostssl all all 0.0.0.0/0 scram-sha-25"
                    "6\nhostnossl all all 0.0.0.0/0 reject\n"
                )
            )
            for file in directory.iterdir():
                os.chown(file, 999, 999)
                file.chmod(384)
            os.chown(directory, 999, 999)
        path = root.parent / "connections.json"
        path.write_text(json.dumps(connections))
        path.chmod(384)
        p = root.parent / "test-connections.json"
        p.write_text(json.dumps(tests))
        p.chmod(384)

        print("three_pg_tls_materials_created")
        sys.exit(0)
    elif stage == "activate":
        from agent_guard.demo.init import activate_runtime

        config = load_run_config((root / "run.json").read_bytes(), base_dir=root)
        resources = json.loads(Path("/control/allocated-plan.json").read_bytes())
        connections = json.loads((root.parent / "connections.json").read_bytes())
        activate_runtime(
            config,
            role_dsns=connections,
            audit_listener_host=settings["audit_listener_host"],
            resource_manifest=resources,
        )
        shutil.copyfile(
            root / "operator/approved-did-manifest.json",
            Path("/public/run/approved-did-manifest.json"),
        )
        Path("/public/run/approved-did-manifest.json").chmod(292)
        shutil.copyfile(
            root / "allocated-resources.json", Path("/public/run/allocated-resources.json")
        )
        Path("/public/run/allocated-resources.json").chmod(292)
        print("activation_frozen")
        sys.exit(0)
    if stage in ("init", "pg-init", "activate"):
        return
    config = load_run_config((root / "run.json").read_bytes(), base_dir=root)
    assert os.getuid() == config.roles[role].uid
    if stage in ["as", "gateway", "gateway-export"]:
        import uvicorn

        from agent_guard.demo.did_bootstrap import load_approved_snapshot
        from agent_guard.demo.provision import build_as, build_gateway

        deadline = time.monotonic() + 300
        while (
            not config.roles[role].private_files["authority_dsn"].exists()
            or not config.approved_did_manifest.exists()
        ):
            if time.monotonic() > deadline:
                raise RuntimeError("activation deadline")
            time.sleep(0.1)
        approved = load_approved_snapshot(config)
        if stage == "gateway-export":
            from agent_guard.demo.config import FrozenExportInputs, freeze
            from agent_guard.demo.provision import readonly_export_factory
            from agent_guard.evidence.task_bundle import load_checkpoint_history
            from agent_guard.evidence.task_verify import load_public_trust
            from agent_guard.gateway.evidence_auth import load_export_credentials

            p = root / "gateway/frozen-export"
            pin = json.loads((p / "external-pin.json").read_bytes())
            trust = load_public_trust(json.loads((p / "public-trust.json").read_bytes()))
            with (p / "checkpoint-history.ndjson").open("rb") as f:
                history = load_checkpoint_history(f, external_trust=trust, external_pin=pin)
            inputs = FrozenExportInputs(
                config.run_id,
                p / "public-trust.json",
                p / "external-pin.json",
                p / "checkpoint-history.ndjson",
                history,
                freeze(pin),
            )
            credential = json.loads((root / "gateway/export-registration.json").read_bytes())
            spool = Path("/tmp/export-spool")
            spool.mkdir(mode=448)
            app = build_gateway(
                config,
                approved=approved,
                export_connection_factory=readonly_export_factory(config, role="gateway"),
                export_spool_parent=spool,
                export_inputs=inputs,
                export_credentials=load_export_credentials([credential]),
            )
        else:
            app = (
                build_as(config, approved=approved)
                if role == "as"
                else build_gateway(config, approved=approved)
            )
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=443,
            ssl_certfile=str(root / role / "tls.pem"),
            ssl_keyfile=str(root / role / "tls-key.pem"),
            access_log=False,
            log_level="warning",
            proxy_headers=False,
        )
    elif stage in ("hold", "freeze-hold", "tls-hold"):
        while True:
            time.sleep(1)
    elif stage == "did":
        from http.server import BaseHTTPRequestHandler, HTTPServer

        docs = json.loads((root / "did/config.json").read_bytes())["documents"]

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                value = docs.get("https://identity.agent-guard.test" + self.path)
                raw = canonical_json_bytes(value) if value is not None else b"{}"
                self.send_response(200 if value is not None else 404)
                self.send_header("Content-Type", "application/did+json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = HTTPServer(("0.0.0.0", 443), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(root / "did/tls.pem", root / "did/tls-key.pem")
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        server.serve_forever()
    elif stage == "messages":
        from agent_guard.demo.did_bootstrap import load_registry, possession_message

        registry = load_registry(config)
        out = {
            r.client_id: b64url_encode(possession_message(config, registry, r))
            for r in registry.registrations
        }
        print(json.dumps(out))
    elif stage == "proof":
        from tongsuopy.crypto import serialization

        from agent_guard.crypto.sm import sign_sm2_message
        from agent_guard.server.private_files import read_private_file

        messages = json.loads(Path("/control/approval-messages.json").read_bytes())
        key = serialization.load_pem_private_key(
            read_private_file(config.roles[role].private_files["signing_key"]), None
        )
        print(b64url_encode(sign_sm2_message(key, b64url_decode(messages["agent-" + role]))))
    elif stage == "approve":
        from agent_guard.demo.did_bootstrap import (
            approve_dids,
            load_registry,
            save_approved_snapshot,
        )

        registry = load_registry(config)
        proofs = {
            k: b64url_decode(v)
            for k, v in json.loads(Path("/control/approval-proofs.json").read_bytes()).items()
        }
        approved = approve_dids(config, registry=registry, proof_of_possession=proofs)
        path = save_approved_snapshot(config, approved=approved)
        print(
            json.dumps(
                {
                    "run_id": approved.run_id,
                    "urls": list(approved.documents),
                    "digests": dict(approved.digests),
                    "path": str(path),
                }
            )
        )
    elif stage == "provision":
        from agent_guard.demo.config import freeze
        from agent_guard.demo.did_bootstrap import load_approved_snapshot
        from agent_guard.demo.provision import load_operator_secrets, provision_run

        policy = task_policy(expires_at=datetime.now(timezone.utc) + timedelta(minutes=30))
        if settings["capacity_items"] == 256:
            from agent_guard.demo.holder import capacity_workload

            policy, _ = capacity_workload(
                task_policy=policy,
                catalog=json.loads(config.public_manifest.read_bytes())["catalog"],
            )
        operator = load_operator_secrets(config, task_policy=policy)
        result = provision_run(config, operator=operator, approved=load_approved_snapshot(config))
        print(
            json.dumps({"run_id": result.run_id, "registered_clients": result.registered_clients})
        )
    elif stage == "audit-migrate":
        import psycopg

        from agent_guard.audit.migrate import apply_migrations
        from agent_guard.demo.provision import _dsn

        with psycopg.connect(_dsn(config.roles["audit"], "audit_dsn"), connect_timeout=5) as conn:
            print("audit_migration_applied", apply_migrations(conn, owner_role="demo_audit"))
    elif stage == "grants":
        import psycopg
        from psycopg import sql

        from agent_guard.demo.provision import _dsn

        domain = sys.argv[3]
        with psycopg.connect(_dsn(config.roles[role], domain + "_dsn"), connect_timeout=5) as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                ).fetchall()
            }
            if domain == "authority":
                sensitive = {
                    "ag_users",
                    "ag_task_policies",
                    "ag_login_csrf",
                    "ag_login_sessions",
                    "ag_authorization_requests",
                    "ag_auth_events",
                    "ag_authorization_codes",
                }
                ledger = {
                    "ag_principals",
                    "ag_tasks",
                    "ag_grants",
                    "ag_proofs",
                    "ag_ledger_events",
                    "ag_ledger_event_nodes",
                    "ag_event_seals",
                    "ag_audit_streams",
                    "ag_audit_records",
                    "ag_audit_bootstrap",
                    "ag_audit_bootstrap_chunks",
                }
                writes = {
                    "as": ledger
                    | sensitive
                    | {
                        "ag_grant_tokens",
                        "ag_auth_evidence",
                        "ag_delegations",
                        "ag_exchange_evidence",
                        "ag_task_revocations",
                        "ag_grant_revocations",
                    },
                    "gateway": ledger
                    | {
                        "ag_operations",
                        "ag_operation_review_flags",
                        "ag_execution_leases",
                        "ag_receipt_outbox",
                        "ag_verified_evidence",
                        "ag_operation_evidence",
                    },
                    "worker": ledger
                    | {
                        "ag_operations",
                        "ag_operation_review_flags",
                        "ag_execution_leases",
                        "ag_receipt_outbox",
                        "ag_verified_evidence",
                        "ag_operation_evidence",
                    },
                    "publisher": ledger
                    | {
                        "ag_operations",
                        "ag_receipt_outbox",
                        "ag_audit_delivery",
                        "ag_audit_delivery_batches",
                    },
                    "export": set(),
                    "gateway_export": set(),
                }
                for target, write_tables in writes.items():
                    readable = (
                        tables
                        if target in ("as", "export", "gateway_export")
                        else tables - sensitive
                    )
                    for table in sorted(readable):
                        conn.execute(
                            sql.SQL("GRANT SELECT ON {} TO {}").format(
                                sql.Identifier(table), sql.Identifier("demo_" + target)
                            )
                        )
                    for table in sorted(write_tables & tables):
                        conn.execute(
                            sql.SQL("GRANT INSERT,UPDATE,DELETE ON {} TO {}").format(
                                sql.Identifier(table), sql.Identifier("demo_" + target)
                            )
                        )
                    if write_tables:
                        conn.execute(
                            sql.SQL(
                                "GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}"
                            ).format(sql.Identifier("demo_" + target))
                        )
                conn.execute("GRANT UPDATE(evidence_ref) ON ag_verified_evidence TO demo_publisher")
                for table in sorted(tables):
                    conn.execute(
                        sql.SQL("GRANT SELECT ON {} TO demo_gateway_export").format(
                            sql.Identifier(table)
                        )
                    )
            elif domain == "downstream":
                for target in ["gateway", "worker"]:
                    for table in sorted(tables):
                        conn.execute(
                            sql.SQL("GRANT SELECT,INSERT,UPDATE ON {} TO {}").format(
                                sql.Identifier(table), sql.Identifier("demo_" + target)
                            )
                        )
            else:
                for table in sorted(tables):
                    conn.execute(
                        sql.SQL("GRANT SELECT,INSERT,UPDATE ON {} TO demo_operator").format(
                            sql.Identifier(table)
                        )
                    )
        print("least_privilege_role_grants", domain)
    elif stage == "bootstrap":
        import psycopg

        from agent_guard.audit.contracts import CheckpointTrust, scope_object
        from agent_guard.crypto.sm import serialize_sm2_public_key
        from agent_guard.demo.provision import _dsn, bootstrap_journal, register_bootstrap
        from agent_guard.server.factory import _load_public_key

        stopped = live_drain(config)
        descriptor = bootstrap_journal(config, stopped=stopped)
        public = json.loads(config.public_manifest.read_text())
        key = _load_public_key(public["audit_keys"]["audit-sign-1"], "audit trust")
        trust = CheckpointTrust(
            "audit-sign-1", "AUDIT_SIGNER", serialize_sm2_public_key(key), 1, None
        )
        credentials = json.loads((root / "operator/audit-registration.json").read_text())
        register_bootstrap(
            config,
            stopped=stopped,
            descriptor=descriptor,
            trust=trust,
            writer_credential_id=credentials["writer_id"],
            writer_credential=credentials["writer_secret"],
            reader_credential_id=credentials["reader_id"],
            reader_credential=credentials["reader_secret"],
            additional_readers=(
                (credentials["publisher_reader_id"], credentials["publisher_reader_secret"]),
            ),
        )
        print(
            json.dumps(
                {
                    "scope": scope_object(descriptor.scope),
                    "descriptor": __import__("dataclasses").asdict(descriptor),
                }
            )
        )
    elif stage == "writer-connections":
        import psycopg

        from agent_guard.demo.provision import _dsn

        with psycopg.connect(
            _dsn(config.roles["operator"], "authority_dsn"), connect_timeout=5
        ) as conn:
            counts = {
                r: conn.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE usename=%s", ("demo_" + r,)
                ).fetchone()[0]
                for r in ["as", "gateway", "worker", "publisher"]
            }
        print(json.dumps(counts))
    elif stage == "freeze":
        from agent_guard.audit.client import AuditClient
        from agent_guard.crypto.sm import serialize_sm2_public_key
        from agent_guard.demo.provision import freeze_export_inputs
        from agent_guard.server.factory import _load_public_key

        public = json.loads(config.public_manifest.read_text())
        descriptor = json.loads(Path("/control/bootstrap.json").read_text())["descriptor"]
        trust = {
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
            "catalog": public["catalog"],
            "audit_keys": [
                {
                    "kid": kid,
                    "role": "AUDIT_SIGNER",
                    "spki_der": b64url_encode(
                        serialize_sm2_public_key(_load_public_key(pem, "audit"))
                    ),
                    "first_sequence": 1,
                    "last_sequence": None,
                }
                for kid, pem in public["audit_keys"].items()
            ],
            "scope": descriptor["scope"],
            "registration": {
                k: descriptor[k]
                for k in (
                    "genesis_digest",
                    "bootstrap_digest",
                    "boundary",
                    "index_root",
                    "object_count",
                    "chunk_count",
                    "wire_bytes",
                )
            },
        }
        stopped = live_drain(config)
        credentials = json.loads((root / "operator/audit-registration.json").read_text())
        client = AuditClient(
            config.endpoints["audit_origin"],
            ca_file=str(root / "operator/ca.pem"),
            writer_credential=credentials["writer_id"] + ":" + credentials["writer_secret"],
            reader_credential=credentials["reader_id"] + ":" + credentials["reader_secret"],
        )
        frozen = freeze_export_inputs(
            config,
            stopped=stopped,
            reader=client,
            public_trust=canonical_json_bytes(trust),
            out_dir=root / "operator/frozen-export",
        )
        print(
            json.dumps(
                {
                    "run_id": frozen.run_id,
                    "history_wire_bytes": frozen.history.wire_bytes,
                    "history_checkpoint_count": frozen.history.checkpoint_count,
                }
            )
        )
    elif stage == "readonly":
        import psycopg

        from agent_guard.demo.provision import readonly_export_factory

        factory = readonly_export_factory(config, role=role)
        with factory() as conn:
            info = conn.execute(
                (
                    "SELECT current_user,current_setting('transaction_read_only"
                    "'),(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()"
                    ")"
                )
            ).fetchone()
            assert info == (
                "demo_gateway_export" if role == "gateway" else "demo_export",
                "on",
                True,
            )
            print(json.dumps({"account": info[0], "read_only": info[1], "tls": info[2]}))
        for sql in [
            "UPDATE ag_tasks SET tenant_id=tenant_id",
            "CREATE TABLE a33_forbidden(id integer)",
        ]:
            try:
                with factory() as conn:
                    conn.execute(sql)
            except psycopg.Error as exc:
                assert exc.sqlstate in ("25006", "42501")
                print(json.dumps({"rejected_sql": sql, "SQLSTATE": exc.sqlstate}))
            else:
                raise AssertionError("read-only role can write")
            try:
                with factory() as conn:
                    conn.execute("SET TRANSACTION READ WRITE")
                    conn.execute(sql)
            except psycopg.Error as exc:
                assert exc.sqlstate == "42501"
                print(json.dumps({"privilege_rejected_sql": sql, "SQLSTATE": exc.sqlstate}))
            else:
                raise AssertionError("account privilege permits write or DDL")
    elif stage == "export":
        import urllib.error
        import urllib.request

        secret = json.loads((root / "export/export-credential.json").read_bytes())
        url = config.endpoints["gateway_origin"] + "/v1/evidence/export"
        context = ssl.create_default_context(cafile=str(root / "export/ca.pem"))
        body = canonical_json_bytes({"task_id": "task-demo"})
        authorization = "AGExport " + secret["credential_id"] + ":" + secret["secret"]
        for case, badbody, badauth in [
            ("wrong-scope", canonical_json_bytes({"task_id": "other-task"}), authorization),
            ("wrong-role", body, "AGPoP business-token"),
        ]:
            denied = urllib.request.Request(
                url,
                data=badbody,
                headers={"Authorization": badauth, "Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(denied, context=context, timeout=15)
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                assert exc.code == 401
                print(
                    json.dumps(
                        {"export_denial_case": case, "status": exc.code, "raw": raw.decode()}
                    )
                )
            else:
                raise AssertionError("unregistered export scope or role accepted")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Authorization": authorization, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, context=context, timeout=60) as reply:
            assert reply.status == 200
            data = reply.read()
        Path("/results/task-bundle.ndjson").write_bytes(data)
        print(
            json.dumps(
                {
                    "export_status": 200,
                    "bytes": len(data),
                    "sha256": __import__("hashlib").sha256(data).hexdigest(),
                }
            )
        )
    elif stage == "offline":
        from agent_guard.evidence.task_verify import load_public_trust, verify_task_bundle

        trust = load_public_trust(load_strict_json(Path("/inputs/public-trust.json").read_bytes()))
        pin = load_strict_json(Path("/inputs/external-pin.json").read_bytes())
        with Path("/inputs/task-bundle.ndjson").open("rb") as stream:
            result = verify_task_bundle(stream, external_trust=trust, external_pin=pin)
        if result.cryptographic_consistency != "VERIFIED":
            raise ValueError("offline consistency")
        print(canonical_json_bytes(thaw(dataclasses.asdict(result))).decode())
    elif stage == "anchor-status":
        import psycopg

        from agent_guard.demo.provision import _dsn

        with psycopg.connect(_dsn(config.roles["operator"], "authority_dsn")) as conn:
            head = conn.execute("SELECT max(seq) FROM ag_audit_records").fetchone()[0]
            ack = conn.execute("SELECT max(ack_sequence) FROM ag_audit_delivery").fetchone()[0]
        print(head is not None and ack is not None and ack >= head)
    elif stage == "role-precheck":
        from agent_guard.server.private_files import read_private_file

        for key, path in config.roles[role].private_files.items():
            if path.exists():
                raw = read_private_file(path)
                print(
                    json.dumps(
                        {
                            "own_private_read": key,
                            "bytes": len(raw),
                            "sha256": __import__("hashlib").sha256(raw).hexdigest(),
                        }
                    )
                )
        denied = 0
        for other, other_role in config.roles.items():
            if other == role:
                continue
            for key, path in other_role.private_files.items():
                try:
                    with path.open("rb") as f:
                        f.read(1)
                except (FileNotFoundError, PermissionError) as exc:
                    denied += 1
                    print(
                        json.dumps(
                            {
                                "other_role_private_denied": other,
                                "file_key": key,
                                "errno": exc.errno,
                            }
                        )
                    )
                else:
                    raise AssertionError("cross-role private mount readable")
        assert denied > 0
        if role in ("planner", "selector", "executor"):
            import subprocess

            for domain in ("authority", "downstream", "audit"):
                program = (
                    "import socket,sys;\ntry:s=socket.create_connection((sys.arg"
                    "v[1],5432),1);s.close()\nexcept OSError as e:print(type(e)."
                    "__name__);sys.exit(0)\nraise AssertionError('holder DB rout"
                    "e unexpectedly reachable')"
                )
                child = subprocess.run(
                    [sys.executable, "-c", program, "pg-" + domain + ".agent-guard.test"],
                    capture_output=True,
                    timeout=5,
                )
                assert child.returncode == 0
                print(
                    json.dumps(
                        {
                            "holder_database_route_denied": domain,
                            "native_exit": child.returncode,
                            "stdout": child.stdout.decode(),
                            "stderr": child.stderr.decode(),
                        }
                    )
                )


def worker_service(config):
    from agent_guard.demo.config import worker_config
    from agent_guard.demo.runner import operation_registry
    from agent_guard.demo.worker import Worker

    event = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: event.set())
    worker = Worker(
        worker_config(config), operations=operation_registry(config, directory=Path("/registry"))
    )
    report = worker.serve(stop_event=event)
    print(canonical_json_bytes(thaw(dataclasses.asdict(report))).decode(), flush=True)


def publisher_service(config):
    import psycopg

    from agent_guard.audit.client import AuditClient
    from agent_guard.audit.contracts import CheckpointTrust
    from agent_guard.audit.delivery import DeliveryWorker
    from agent_guard.crypto.sm import serialize_sm2_public_key
    from agent_guard.demo.provision import _dsn
    from agent_guard.gateway.receipt_config import load_receipt_worker_config
    from agent_guard.server.factory import _load_public_key

    role = config.roles["publisher"]
    dsn = _dsn(role, "authority_dsn")
    publisher = load_receipt_worker_config(role.private_files["publisher_config"]).publisher(dsn)
    credentials = load_strict_json(
        (role.public_config_file.parent / "audit-delivery.json").read_bytes()
    )
    public = load_strict_json(config.public_manifest.read_bytes())
    trust = CheckpointTrust(
        "audit-sign-1",
        "AUDIT_SIGNER",
        serialize_sm2_public_key(_load_public_key(public["audit_keys"]["audit-sign-1"], "audit")),
        1,
        None,
    )
    client = AuditClient(
        config.endpoints["audit_origin"],
        ca_file=str(role.public_config_file.parent / "ca.pem"),
        writer_credential=credentials["writer_id"] + ":" + credentials["writer_secret"],
        reader_credential=credentials["reader_id"] + ":" + credentials["reader_secret"],
    )
    delivery = DeliveryWorker(lambda: psycopg.connect(dsn), client, trust=(trust,))
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    stream = load_strict_json(Path("/control/bootstrap.json").read_bytes())["descriptor"]["scope"][
        "stream_id"
    ]
    while not stopped.is_set():
        with psycopg.connect(dsn) as conn:
            ids = conn.execute(
                (
                    "SELECT operation_id FROM ag_receipt_outbox WHERE receipt_s"
                    "tatus='PENDING' ORDER BY created_at LIMIT 64"
                )
            ).fetchall()
        for (operation,) in ids:
            publisher.publish(operation)
        result = delivery.deliver_once(stream)
        if result.status not in ("ACKED", "NO_PENDING"):
            raise ValueError("audit delivery did not complete")
        stopped.wait(0.1)
    print(canonical_json_bytes({"role": "publisher", "inflight_zero": True}).decode(), flush=True)


def observe_oracle(config, operations, capacity_items):
    """Independent read-only authority/downstream facts, never HTTP success alone."""
    import psycopg

    from agent_guard.demo.provision import _dsn

    with psycopg.connect(_dsn(config.roles["operator"], "authority_dsn")) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        grants = conn.execute(
            (
                "SELECT depth,amount_limit,call_limit,amount_reserved,amoun"
                "t_settled,calls_reserved,calls_settled FROM ag_grants ORDE"
                "R BY depth"
            )
        ).fetchall()
        if grants != [
            (0, 100000, 12, 0, 70000, 0, 4),
            (1, 80000, 10, 0, 70000, 0, 4),
            (2, 70000, 8, 0, 70000, 0, 4),
        ]:
            raise ValueError("all ancestor counters differ from actual four-tool effects")
        rows = conn.execute("SELECT operation_id,status,tool_id FROM ag_operations").fetchall()
        if {r[0] for r in rows} != set(operations) or any(r[1] != "SUCCEEDED" for r in rows):
            raise ValueError("terminal operation oracle")
        if conn.execute(
            "SELECT count(*) FROM ag_receipt_outbox WHERE receipt_status='READY'"
        ).fetchone() != (4,):
            raise ValueError("READY oracle")
        if dict(
            conn.execute("SELECT phase,count(*) FROM ag_ledger_events GROUP BY phase").fetchall()
        ) != {"RESERVE": 4, "SETTLE": 4}:
            raise ValueError("mutually exclusive terminal event oracle")
        order = next(r[0] for r in rows if r[2] == "procurement.order.create")
        evidence = conn.execute(
            (
                "SELECT v.body_bytes,v.token_bytes,v.proof_bytes,v.chain_js"
                "on FROM ag_verified_evidence v JOIN ag_operation_evidence "
                "e USING(evidence_ref) WHERE e.operation_id=%s AND e.kind='"
                "first'"
            ),
            (order,),
        ).fetchall()
        if len(evidence) != 1:
            raise ValueError("first immutable order material")
        body, token, proof, chain = map(bytes, evidence[0])
        request = load_strict_json(body)
        if (
            len(request["params"]["items"]) != capacity_items
            or len(body) > 65536
            or len(token) > 16384
            or len(proof) > 16384
        ):
            raise ValueError("actual capacity material")
        result = conn.execute(
            "SELECT result_bytes,amount_fen FROM ag_receipt_outbox WHERE operation_id=%s", (order,)
        ).fetchone()
        value = load_strict_json(bytes(result[0]))
        if (
            result[1] != 70000
            or len(value["items"]) != capacity_items
            or value["total_fen"] != 70000
        ):
            raise ValueError("actual capacity result")
        clock = conn.execute("SELECT clock_timestamp()").fetchone()[0].isoformat()
    with psycopg.connect(_dsn(config.roles["operator"], "downstream_dsn")) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        if conn.execute("SELECT count(*) FROM ds_orders").fetchone() != (1,) or conn.execute(
            "SELECT count(*) FROM ds_notifications"
        ).fetchone() != (1,):
            raise ValueError("real DS once-effect oracle")
        ds = conn.execute(
            "SELECT amount_fen,result_bytes FROM ds_operations WHERE operation_id=%s", (order,)
        ).fetchone()
        if ds != (70000, result[0]):
            raise ValueError("authority/DS persistent result mismatch")
    return {
        "clock": clock,
        "ancestor_counters": [list(r) for r in grants],
        "operation_ids": list(operations),
        "real_orders": 1,
        "real_notifications": 1,
        "actual_items": capacity_items,
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "token_sha256": hashlib.sha256(token).hexdigest(),
        "proof_sha256": hashlib.sha256(proof).hexdigest(),
        "chain_sha256": hashlib.sha256(chain).hexdigest(),
        "result_sha256": hashlib.sha256(bytes(result[0])).hexdigest(),
    }


def normal(config, out, capacity_items):
    import contextlib
    import io

    import psycopg

    from agent_guard.demo.provision import _dsn
    from agent_guard.demo.runner import ScenarioRunner, operation_registry

    settings = load_strict_json(Path("/control/settings.json").read_bytes())
    if capacity_items != settings["capacity_items"]:
        raise ValueError("capacity workload must be frozen before provisioning")
    out = Path(out)
    if out.exists() or not out.is_absolute():
        raise ValueError("new absolute output leaf required")
    out.mkdir(mode=0o700)
    registry = operation_registry(config, directory=Path("/registry"))
    stderr = (out / "holder-native.ndjson").open("wb")
    runner = ScenarioRunner(
        config,
        registry=registry,
        launch=lambda role: [sys.executable, "-m", "agent_guard.demo", "relay", "--role", role],
        stderr=stderr,
        wait_receiver=lambda role, path, seconds: remote(
            "wait-receiver", role=role, path=str(path), seconds=seconds
        ),
        capacity_items=capacity_items,
    )
    try:
        remote("start-services")
        runner.start()
        login = SyntheticLogin(
            **load_strict_json(config.roles["operator"].private_files["user_login"].read_bytes())
        )
        runner.authorize(login=login)
        (out / "authorizations.json").write_bytes(canonical_json_bytes(thaw(runner.authorizations)))
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            run_actor("bootstrap", "operator")
        bootstrap = load_strict_json(capture.getvalue().encode())
        remote("record-bootstrap", value=bootstrap)
        remote("resume-services")

        def progress(operation):
            deadline = time.monotonic() + 60
            while True:
                with psycopg.connect(_dsn(config.roles["operator"], "authority_dsn")) as conn:
                    row = conn.execute(
                        "SELECT receipt_status FROM ag_receipt_outbox WHERE operation_id=%s",
                        (operation,),
                    ).fetchone()
                if row == ("READY",):
                    return
                if time.monotonic() > deadline:
                    raise ValueError("bounded READY wait")
                time.sleep(0.05)

        report = runner.four_tools(progress=progress)
        (out / "normal-report.json").write_bytes(
            canonical_json_bytes(thaw(dataclasses.asdict(report)))
        )
        (out / "database-oracle.json").write_bytes(
            canonical_json_bytes(observe_oracle(config, report.operation_ids, capacity_items))
        )
        (out / "holder-stop.json").write_text(json.dumps(runner.stop(), indent=2) + "\n")
        remote("wait-anchor")
        with contextlib.redirect_stdout(io.StringIO()):
            run_actor("freeze", "operator")
        remote("export-offline", out=str(out))
        # Public synthetic material is distributed only after actual authorization expiry.
        expiry = max(x["expires_at"] for x in report.authorizations)
        remaining = max(0, expiry - int(time.time()) + 1)
        if remaining > 301:
            raise ValueError("bounded public expiry")
        time.sleep(remaining)
        (out / "public-expiry.json").write_bytes(
            canonical_json_bytes(
                {
                    "observed_at": int(time.time()),
                    "latest_expiry": expiry,
                    "expired": int(time.time()) > expiry,
                }
            )
        )
        return {
            "run_id": config.run_id,
            "owner_id": config.owner_id,
            "out": str(out),
            "operation_ids": report.operation_ids,
            "status": "NORMAL_COMPLETE_NOT_JOINT_ACCEPTANCE",
        }
    finally:
        if runner.holders:
            runner.stop(force=True)
        stderr.close()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agent_guard.demo")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("normal", "bridge", "check", "audit-serve", "worker-serve", "publisher-serve"):
        command = sub.add_parser(name)
        command.add_argument("--config", default="/owned/run/run.json")
        if name == "normal":
            command.add_argument("--out", required=True)
            command.add_argument("--capacity-items", type=int, choices=(1, 256), default=1)
    relay_parser = sub.add_parser("relay")
    relay_parser.add_argument("--role", choices=("planner", "selector", "executor"), required=True)
    actor = sub.add_parser("actor")
    actor.add_argument("--stage", required=True)
    actor.add_argument("--role", choices=sorted(ROLES), default="operator")
    actor.add_argument("--extra", nargs="*", default=[])
    init = sub.add_parser("init")
    init.add_argument("--out", required=True)
    init.add_argument("--run-id", required=True)
    init.add_argument("--owner-id", required=True)
    init.add_argument("--identity-map", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "actor":
            allowed = {
                "init",
                "pg-init",
                "activate",
                "as",
                "gateway",
                "gateway-export",
                "hold",
                "did",
                "messages",
                "proof",
                "approve",
                "provision",
                "audit-migrate",
                "grants",
                "bootstrap",
                "writer-connections",
                "freeze",
                "readonly",
                "export",
                "offline",
                "anchor-status",
                "role-precheck",
            }
            if args.stage not in allowed:
                raise ValueError("fixed actor stage")
            sys.argv = ["agent_guard.demo", args.stage, args.role, *args.extra]
            run_actor(args.stage, args.role)
            return 0
        if args.command == "init":
            from agent_guard.demo.init import init_run

            result = init_run(
                Path(args.out),
                run_id=args.run_id,
                owner_id=args.owner_id,
                **load_strict_json(Path(args.identity_map).read_bytes()),
            )
            print(
                canonical_json_bytes(
                    {
                        "run_id": result.run_id,
                        "owner_id": result.owner_id,
                        "run_config": str(result.run_config),
                    }
                ).decode()
            )
            return 0
        if args.command == "relay":
            relay(args.role)
            return 0
        path = Path(args.config)
        config = load_run_config(path.read_bytes(), base_dir=path.parent)
        if args.command in ("worker-serve", "publisher-serve", "bridge"):
            raw = Path("/proc/self/cmdline").read_bytes()
            print(
                json.dumps(
                    {
                        "native_process": True,
                        "stage": args.command,
                        "pid": os.getpid(),
                        "uid": os.getuid(),
                        "start_ticks": Path("/proc/self/stat").read_text().split()[21],
                        "argv_sha256": hashlib.sha256(raw).hexdigest(),
                        "argv_nul_hex": raw.hex(),
                    }
                ),
                file=sys.stderr,
                flush=True,
            )
        if args.command == "normal":
            print(
                canonical_json_bytes(thaw(normal(config, args.out, args.capacity_items))).decode()
            )
        elif args.command == "bridge":
            bridge(config)
        elif args.command == "worker-serve":
            worker_service(config)
        elif args.command == "publisher-serve":
            publisher_service(config)
        elif args.command == "audit-serve":
            from agent_guard.audit.config import AuditConfig
            from agent_guard.audit.server import create_server

            allocated = load_strict_json(
                (config.base_dir / "allocated-resources.json").read_bytes()
            )
            role = config.roles["audit"]
            if os.getuid() != role.uid or (
                allocated["run_id"],
                allocated["owner_id"],
                allocated["roles"]["audit"]["uid"],
            ) != (config.run_id, config.owner_id, role.uid):
                raise ValueError("approved audit identity")
            host = allocated["roles"]["audit"]["listener_host"]
            parsed = AuditConfig.load(
                role.private_files["audit_config"], approved_listener_host=host
            )
            with create_server(parsed, approved_listener_host=host) as server:
                server.serve_forever(poll_interval=0.1)
        else:
            from agent_guard.demo.config import check_config

            report = check_config(config)
            print(
                canonical_json_bytes(
                    {
                        "run_id": report.run_id,
                        "owner_id": report.owner_id,
                        "roles": list(report.roles),
                        "scope": thaw(report.scope),
                    }
                ).decode()
            )
        return 0
    except (OSError, ValueError, TypeError) as exc:
        import traceback

        # Frames and validator messages carry no input credentials or variable values.
        print(
            json.dumps(
                {
                    "error_type": type(exc).__name__,
                    "frames": [
                        {"file": f.filename, "line": f.lineno, "function": f.name}
                        for f in traceback.extract_tb(exc.__traceback__)
                    ],
                    "validation_reason": str(exc)
                    if isinstance(exc, ValueError)
                    else type(exc).__name__,
                }
            ),
            file=sys.stderr,
        )
        print("demo action rejected; inspect private owned evidence", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
