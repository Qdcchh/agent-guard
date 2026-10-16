"""Native joint export/offline regressions; full transport controls follow separately."""

import psycopg
import pytest

from agent_guard.evidence.export import materialize_task_export
from agent_guard.evidence.task_verify import verify_task_bundle
from agent_guard.execution.query import AuthorizedQuery
from tests.fixtures.a32_export import export_full_state as full_state
from tests.fixtures.a32_export import readonly_export_factory
from tests.fixtures.a32_joint import native_public_inputs
from tests.fixtures.gateway import query_bundle
from tests.fixtures.receipts import receipt_services
from tests.integration.test_verified_execution import TOOLS, signed_env

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("published", [False, True])
@pytest.mark.parametrize("queried", [False, True])
def test_native_export_verifies_original_history(
    ledger, dsn, downstream_dsn, tmp_path, published, queried
):
    env = signed_env(dsn, downstream_dsn)
    key, receipt_verifier, publisher = receipt_services(env, dsn)
    ops = []
    for index, tool in enumerate(TOOLS):
        params = [
            {"request_id": "req-001"},
            {"request_id": "req-001", "document_id": "doc-001"},
            None,
            {
                "template_id": "order-created",
                "recipient_id": "user-demo-001",
                "operation_id": ops[0] if ops else "",
            },
        ][index]
        accepted = env.adapter.accept(env.bundle("joint-" + str(index), tool=tool, params=params))
        ops.append(accepted.operation_id)
        env.adapter.accept(env.bundle("joint-" + str(index), tool=tool, params=params))
        query = AuthorizedQuery(dsn, evidence_store=env.evidence, receipt_verifier=receipt_verifier)
        if queried:
            query.query(query_bundle(env, accepted.operation_id))
        assert env.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
        if published:
            publisher.publish(accepted.operation_id)
            env.adapter.accept(env.bundle("joint-" + str(index), tool=tool, params=params))
        if queried:
            query.query(query_bundle(env, accepted.operation_id))
    scope, pin, history, trust = native_public_inputs(env, dsn, tmp_path, key)
    before = full_state(dsn, downstream_dsn)
    parent = tmp_path / "spool"
    parent.mkdir(mode=0o700)
    with readonly_export_factory(dsn) as factory:
        spool = materialize_task_export(
            factory, scope, pin, parent, external_checkpoint_history=history
        )
        try:
            with open(spool.path, "rb") as stream:
                report = verify_task_bundle(stream, trust, pin)
            assert report.cryptographic_consistency == "VERIFIED"
            assert report.tail == 0
            assert len(report.runtime_status_as_of) == 4
        finally:
            spool.cleanup()
    assert full_state(dsn, downstream_dsn) == before
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SHOW server_encoding").fetchone()[0] == "UTF8"


def test_real_fixed_10000_capacity_preflight():
    """Reuse strictly bound native business originals and count this installation's codec."""
    import hashlib
    import json
    import os
    from pathlib import Path

    from agent_guard.evidence import task_bundle as codec
    from tests.fixtures.a32_joint import count_original_capacity

    dependency = Path(os.environ["AG32_FIXED_CAPACITY_DEPENDENCY"])
    binding = json.loads(dependency.read_text())
    assert (
        binding["classification"] == "QUALIFIED_UNAFFECTED_NATIVE_BUSINESS_REUSE_NOT_NEW_PG_EXPORT"
    )
    for row in binding["members"]:
        original = Path(row["path"])
        checksum = hashlib.sha256()
        with original.open("rb") as stream:
            while block := stream.read(1048576):
                checksum.update(block)
        assert checksum.hexdigest() == row["sha256"]
    for member in binding["actual_installed_business_members"]:
        assert hashlib.sha256(Path(member["path"]).read_bytes()).hexdigest() == member["sha256"]
    assert binding["journal_difference"]["condition"] == "if all(...) -> if grants and all(...)"
    generation = json.loads(
        Path(
            next(row["path"] for row in binding["members"] if row["role"] == "native_generation")
        ).read_text()
    )
    execution = json.loads(
        Path(
            next(row["path"] for row in binding["members"] if row["role"] == "native_execution")
        ).read_text()
    )
    assert len(generation["operations"]) == 10000 and not generation["failures"]
    assert len({operation[1] for operation in generation["operations"]}) == 10000
    assert execution["completed"] == 10000 and not execution["failures"]
    original_rejection = Path(
        next(row["path"] for row in binding["members"] if row["role"] == "native_rejection_xml")
    ).read_text()
    assert "complete material capacity exceeded" in original_rejection
    archive = next(row for row in binding["members"] if row["role"] == "native_archive")
    evidence = Path(os.environ["A31_TEST_EVIDENCE_DIR"]) / "fixed10000"
    evidence.mkdir(mode=0o700)
    report = count_original_capacity(archive["path"], archive["sha256"], evidence)
    assert report["native_operations"] == 10000
    assert report["qualified_nonempty_bootstrap_guard_reuse"]["first_records_checked"] == 10000
    assert report["qualified_nonempty_bootstrap_guard_reuse"][
        "all_first_paths_nonempty_and_in_immutable_bootstrap"
    ]
    assert report["journal"] == 30009
    assert report["fixed_legal_batches"] == 668
    assert report["objects"] == 203285
    assert report["raw_bytes"] == 291623992
    assert report["exact_object_chunk_wire_bytes"] == 439169636
    assert report["first_raw_cap_exceeded"]["source"] == {
        "journal_seq": 23963,
        "kind": "TERMINAL",
    }
    assert report["first_raw_cap_exceeded"]["object_number"] == 165414
    assert report["first_raw_cap_exceeded"]["raw_bytes_including_new"] == 268436418
    assert report["first_object_cap_exceeded"]["object_number"] == codec.MAX_OBJECTS + 1
    assert codec.MAX_WIRE_BYTES == 268435456 and codec.MAX_OBJECTS == 200000
    assert report["acceptance"] == "NOT_ASSERTED"
    assert report["footer_roots_are_length_only_seed_placeholders_not_valid_bundle"]
    assert report["terminal_material_is_original_row_arithmetic_not_new_PG_project_receipt"]
    assert binding["native_rejection"] == {
        "exception": "TaskBundleError",
        "message": "complete material capacity exceeded",
    }
    assert "FORMAL_CAPACITY_FOLLOWUP_PLAN" in Path(binding["formal_plan"]).read_text()


@pytest.mark.parametrize("round_id", range(10))
def test_real_export_independent_pin_offline_full_flow(
    ledger, dsn, downstream_dsn, tmp_path, tmp_path_factory, round_id
):
    import json
    import threading
    from dataclasses import replace

    from agent_guard.audit.config import AuditConfig
    from agent_guard.audit.server import create_server
    from agent_guard.contracts.encoding import canonical_json_bytes
    from agent_guard.evidence.task_verify import load_public_trust
    from tests.fixtures.a31_joint import bind_frozen_delivery, joint_context
    from tests.fixtures.a32_joint import (
        capture_reader_history,
        exact_host_certificates,
        public_task_trust,
    )
    from tests.integration.test_audit_tls import service_tls
    from tests.integration.test_gateway_tls import signed_request

    audit_tls = service_tls.__wrapped__(tmp_path_factory)
    with joint_context(dsn, downstream_dsn, tmp_path / "native-joint", audit_tls) as runtime:
        env = runtime.env
        _, receipt_verifier, publisher = receipt_services(
            env, dsn, gateway_key=runtime.receipt_key, signing_kid="joint-receipt-1"
        )
        delivery = bind_frozen_delivery(runtime)
        first = delivery.persist_pending()
        assert first is not None
        assert delivery.worker.deliver_once(runtime.descriptor.scope.stream_id) is not None
        ops = []
        for index, tool in enumerate(TOOLS):
            params = [
                {"request_id": "req-001"},
                {"request_id": "req-001", "document_id": "doc-001"},
                {
                    "request_id": "req-001",
                    "quote_id": "quote-001",
                    "quote_version": "1",
                    "items": [{"sku": "sku-001", "quantity": 1}],
                    "delivery_id": "office-001",
                },
                {
                    "template_id": "order-created",
                    "recipient_id": "user-demo-001",
                    "operation_id": ops[0] if ops else "",
                },
            ][index]
            request = {
                "profile": "GM-MVP-1",
                "task_id": "task-001",
                "tool_id": tool,
                "tool_version": "1",
                "idempotency_key": "tls-joint-" + str(index),
                "params": params,
            }
            status, accepted, _ = signed_request(
                env, runtime.gateway_port, runtime.gateway_context, request
            )
            assert status == 202
            operation_id = accepted["operation_id"]
            ops.append(operation_id)
            env.adapter.accept(env.bundle("tls-joint-" + str(index), tool=tool, params=params))
            query = AuthorizedQuery(
                dsn, evidence_store=env.evidence, receipt_verifier=receipt_verifier
            )
            query.query(query_bundle(env, operation_id))
            assert env.service.run_operation(operation_id).status == "SUCCEEDED"
            publisher.publish(operation_id)
            query.query(query_bundle(env, operation_id))
        for _ in range(100):
            outcome = delivery.worker.deliver_once(runtime.descriptor.scope.stream_id)
            if outcome.status == "NO_PENDING":
                break
            assert outcome.status == "ACKED"
        else:
            raise AssertionError("bounded delivery failed to drain")
        certificates = tmp_path / "reader-tls"
        exact_host_certificates(certificates, "audit.agent-guard.test")
        config = replace(
            AuditConfig.load(runtime.private / "audit-config.json"),
            port=443,
            tls_certificate=certificates / "server.pem",
            tls_private_key=certificates / "server.key",
        )
        server = create_server(config)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            before = runtime.all_domains()
            public = tmp_path / "public"
            public.mkdir(mode=0o700)
            scope = runtime.descriptor.scope
            pin, history, pin_path = capture_reader_history(
                scope=scope,
                audit_keys=(runtime.trust,),
                reader_credential="joint-reader:" + runtime.reader_token,
                ca_file=certificates / "ca.pem",
                directory=public,
            )
            trust = public_task_trust(
                env,
                scope,
                runtime.descriptor,
                (runtime.trust,),
                runtime.receipt_key,
                signing_kid="joint-receipt-1",
            )
            trust_path = public / "trust.json"
            trust_path.write_bytes(canonical_json_bytes(trust))
            assert runtime.all_domains() == before
            spool_parent = tmp_path / "export-spool"
            spool_parent.mkdir(mode=0o700)
            with readonly_export_factory(dsn) as factory:
                spool = materialize_task_export(
                    factory,
                    scope,
                    pin,
                    spool_parent,
                    external_checkpoint_history=history,
                )
                try:
                    with open(spool.path, "rb") as stream:
                        report = verify_task_bundle(stream, load_public_trust(trust), pin)
                    assert report.cryptographic_consistency == "VERIFIED"
                    assert len(report.runtime_status_as_of) == 4
                    assert report.tail == 0
                finally:
                    spool.cleanup()
            assert runtime.all_domains() == before
            import hashlib
            import http.client
            import os
            import secrets
            import ssl
            import subprocess
            import sys
            import time

            from agent_guard.server.__main__ import _public_pem
            from tests.fixtures.a31_audit_service import private_json, record_native
            from tests.fixtures.execution import DOWNSTREAM_SECRET
            from tests.fixtures.gateway import config_document

            gw_certificates = tmp_path / "export-tls"
            exact_host_certificates(gw_certificates, "gateway.agent-guard.test")
            export_config = config_document(env)
            export_config["receipt_keys"] = {"joint-receipt-1": _public_pem(runtime.receipt_key)}
            export_secret = secrets.token_urlsafe(36)
            export_config["export_credentials"] = [
                {
                    "credential_id": "joint-export",
                    "credential_sha256": hashlib.sha256(export_secret.encode("ascii")).hexdigest(),
                    "tenant_id": scope.tenant_id,
                    "task_ids": [scope.task_id],
                }
            ]
            export_config["evidence_local_inputs"] = {
                "trust_file": str(trust_path),
                "external_pin_file": str(pin_path),
                "external_checkpoint_history_file": history.source_path,
            }
            export_private = tmp_path / "export-private"
            export_private.mkdir(mode=0o700)
            export_path = private_json(export_private / "config.json", export_config)
            private_json(
                export_private / "secrets.json",
                {
                    "note": "synthetic independent test secret",
                    "downstream_secret": DOWNSTREAM_SECRET,
                },
            )
            with readonly_export_factory(dsn) as factory:
                with factory() as conn:
                    export_dsn = psycopg.conninfo.make_conninfo(
                        conn.info.dsn, password=conn.info.password
                    )
                command = [
                    sys.executable,
                    "-m",
                    "agent_guard.gateway",
                    "run",
                    "--config",
                    str(export_path),
                    "--host",
                    "127.0.0.2",
                    "--port",
                    "443",
                    "--ssl-certfile",
                    str(gw_certificates / "server.pem"),
                    "--ssl-keyfile",
                    str(gw_certificates / "server.key"),
                    "--export-spool-parent",
                    str(spool_parent),
                ]
                child = subprocess.Popen(
                    command,
                    env={
                        **os.environ,
                        "AG_GATEWAY_DATABASE_URL": dsn,
                        "AG_GATEWAY_DOWNSTREAM_DATABASE_URL": downstream_dsn,
                        "AG_GATEWAY_EXPORT_DATABASE_URL": export_dsn,
                    },
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                try:
                    context = ssl.create_default_context(cafile=str(gw_certificates / "ca.pem"))
                    deadline = time.monotonic() + 15
                    while True:
                        assert child.poll() is None
                        try:
                            connection = http.client.HTTPSConnection(
                                "gateway.agent-guard.test",
                                443,
                                context=context,
                                timeout=30,
                            )
                            connection.request(
                                "POST",
                                "/v1/evidence/export",
                                canonical_json_bytes({"task_id": scope.task_id}),
                                {
                                    "Content-Type": "application/json",
                                    "Authorization": "AGExport joint-export:" + export_secret,
                                },
                            )
                            response = connection.getresponse()
                            assert response.status == 200
                            raw = response.read(268435457)
                            connection.close()
                            assert len(raw) <= 268435456
                            break
                        except OSError:
                            assert time.monotonic() < deadline
                            time.sleep(0.02)
                    bundle_path = public / "bundle.ndjson"
                    bundle_path.write_bytes(raw)
                    report_path = public / "report.json"
                    cli = [
                        sys.executable,
                        "-m",
                        "agent_guard.evidence.verify_cli",
                        "--bundle",
                        str(bundle_path),
                        "--trust",
                        str(trust_path),
                        "--external-pin",
                        str(pin_path),
                        "--report",
                        str(report_path),
                    ]
                    result = subprocess.run(cli, capture_output=True, timeout=300)
                    record_native(
                        "a32-joint-offline-cli",
                        {
                            "argv": cli,
                            "returncode": result.returncode,
                            "stdout": result.stdout.decode(),
                            "stderr": result.stderr.decode(),
                        },
                    )
                    assert result.returncode == 0
                    assert (
                        json.loads(report_path.read_text())["cryptographic_consistency"]
                        == "VERIFIED"
                    )
                    assert not list(spool_parent.iterdir())
                    assert runtime.all_domains() == before
                finally:
                    if child.poll() is None:
                        child.terminate()
                    try:
                        stdout, stderr = child.communicate(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        stdout, stderr = child.communicate(timeout=10)
                    record_native(
                        "a32-joint-export-gateway-cli",
                        {
                            "argv": command,
                            "pid": child.pid,
                            "returncode": child.returncode,
                            "stdout": stdout.decode(),
                            "stderr": stderr.decode(),
                        },
                    )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(10)
            assert not thread.is_alive()


@pytest.mark.parametrize("published", [False, True])
def test_real_accepted_wide_chain_256_items_component_export_offline(
    ledger, dsn, downstream_dsn, tmp_path, published
):
    from agent_guard.contracts.encoding import load_strict_json
    from tests.fixtures.gateway import app_for, raw_material, request
    from tests.fixtures.receipts import real_login_capacity_env

    env = real_login_capacity_env(dsn, downstream_dsn)
    quote = env.service._catalog.get_quote("quote-001", "1")
    params = {
        "request_id": "req-001",
        "quote_id": "quote-001",
        "quote_version": "1",
        "items": [{"sku": row.sku, "quantity": 1} for row in quote.lines],
        "delivery_id": "office-001",
    }
    bundle = env.bundle("wide-256", params=params)
    token, proof, body = raw_material(dsn, bundle)
    app = app_for(env, dsn)
    status, accepted, _ = request(
        app,
        body=body,
        headers=[
            (b"content-type", b"application/json"),
            (b"authorization", b"AGPoP " + token),
            (b"ag-proof", proof),
        ],
    )
    assert status == 202
    operation_id = accepted["operation_id"]
    assert len(set(row.sku for row in quote.lines)) == 256
    assert len(load_strict_json(body)["params"]["items"]) == 256
    key, _, publisher = receipt_services(env, dsn)
    env.adapter.accept(env.bundle("wide-256", params=params))
    assert env.service.run_operation(operation_id).status == "SUCCEEDED"
    if published:
        publisher.publish(operation_id)
    scope, pin, history, trust = native_public_inputs(env, dsn, tmp_path, key)
    before = full_state(dsn, downstream_dsn)
    parent = tmp_path / "spool"
    parent.mkdir(mode=0o700)
    with readonly_export_factory(dsn) as factory:
        spool = materialize_task_export(
            factory, scope, pin, parent, external_checkpoint_history=history
        )
        try:
            with open(spool.path, "rb") as stream:
                report = verify_task_bundle(stream, trust, pin)
            assert report.cryptographic_consistency == "VERIFIED"
            assert len(report.runtime_status_as_of) == 1
        finally:
            spool.cleanup()
    assert full_state(dsn, downstream_dsn) == before


def test_native_bootstrap_path_scan_cost(ledger, dsn, downstream_dsn, tmp_path, monkeypatch):
    """Measure genuine FIRST decoding while all AS path nodes are bootstrapped."""
    import json
    import os
    from pathlib import Path

    from agent_guard.audit import journal

    env = signed_env(dsn, downstream_dsn)
    original = journal.decode_journal_record
    decoded = []

    def observe(raw):
        value = original(raw)
        decoded.append(value.seq)
        return value

    monkeypatch.setattr(journal, "decode_journal_record", observe)
    counts = []
    for index in range(6):
        before = len(decoded)
        env.adapter.accept(
            env.bundle(
                "scan-cost-" + str(index),
                tool=TOOLS[0],
                params={"request_id": "req-001"},
            )
        )
        counts.append(len(decoded) - before)
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT raw FROM ag_audit_bootstrap_chunks "
            "WHERE object_kind='typed_snapshot_metadata' ORDER BY object_id,chunk_index"
        ).fetchall()
        # Small genuine grants metadata fit one chunk in this fixed native fixture.
        metadata = [journal.load_strict_json(bytes(row[0])) for row in rows]
        bootstrap_ids = [m["columns"]["grant_id"] for m in metadata if m["table"] == "ag_grants"]
        actual_ids = [
            r[0]
            for r in conn.execute("SELECT grant_id FROM ag_grants ORDER BY grant_id").fetchall()
        ]
    path = Path(os.environ["A31_TEST_EVIDENCE_DIR"]) / "bootstrap-scan-cost.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "decode_counts": counts,
                "bootstrap_ids": bootstrap_ids,
                "actual_ids": actual_ids,
            },
            indent=2,
        )
    )
    assert sorted(bootstrap_ids) == actual_ids
    assert counts[1:] == [1] * 5


def test_native_bootstrap_first_cap_boundary(ledger, dsn, downstream_dsn, monkeypatch):
    from agent_guard.audit import journal

    env = signed_env(dsn, downstream_dsn)
    for index in range(6):
        env.adapter.accept(
            env.bundle(
                "cap-bound-" + str(index),
                tool=TOOLS[0],
                params={"request_id": "req-001"},
            )
        )
    monkeypatch.setattr(journal, "MAX_RECORDS", 5)
    bundle = env.bundle("cap-bound-reject", tool=TOOLS[0], params={"request_id": "req-001"})
    before = full_state(dsn, downstream_dsn)
    with pytest.raises(journal.JournalError, match="journal snapshot cap exceeded"):
        env.adapter.accept(bundle)
    assert full_state(dsn, downstream_dsn) == before
    # Proof staging occurs before the transaction; ledger/journal remain unchanged.
    with psycopg.connect(dsn) as conn:
        assert (
            conn.execute("SELECT count(*) FROM ag_audit_records WHERE kind='FIRST'").fetchone()[0]
            == 6
        )
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone()[0] == 6
    monkeypatch.setattr(journal, "MAX_RECORDS", 6)
    env.adapter.accept(
        env.bundle("cap-bound-accept", tool=TOOLS[0], params={"request_id": "req-001"})
    )
