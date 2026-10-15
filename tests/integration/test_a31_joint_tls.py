"""Native AS/GW/audit HTTPS+CLI, exact durable delivery and independent external pin.

Delivery uses the real frozen APIs and native CLI; behavior requires actual execution.
"""

import http.client
import ssl

import psycopg
import pytest

from agent_guard.audit.checkpoint import verify_checkpoint
from agent_guard.audit.contracts import encode_append_batch
from agent_guard.contracts.encoding import load_strict_json
from agent_guard.crypto.sm import sm3_b64url
from tests.fixtures.a31_joint import audit_request, bind_frozen_delivery
from tests.fixtures.receipts import full_state, publication_only, receipt_services, result_read_only
from tests.integration.test_gateway_tls import signed_request
from tests.integration.test_server_tls import test_tls_server_runs_the_full_as_flow as _as_full_flow

pytestmark = pytest.mark.integration
pytest_plugins = ("tests.fixtures.a31_joint",)


def test_verified_ca_hostname_and_full_tls_flow(ledger, dsn, tmp_path, monkeypatch):
    """Original independent AS probe copied into formal code, same negative controls/order."""
    import tests.integration.test_server_tls as tls

    called = []

    def verified_request(port, method, path, body=None, headers=None):
        if not called:
            with pytest.raises(ssl.SSLCertVerificationError):
                c = http.client.HTTPSConnection(
                    "localhost", port, context=ssl.create_default_context(), timeout=5
                )
                try:
                    c.request("GET", "/ag/keys")
                    c.getresponse()
                finally:
                    c.close()
            with pytest.raises(ssl.SSLCertVerificationError):
                c = http.client.HTTPSConnection(
                    "127.0.0.1",
                    port,
                    context=ssl.create_default_context(cafile=str(tmp_path / "tls-cert.pem")),
                    timeout=5,
                )
                try:
                    c.request("GET", "/ag/keys")
                    c.getresponse()
                finally:
                    c.close()
        context = ssl.create_default_context(cafile=str(tmp_path / "tls-cert.pem"))
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        c = http.client.HTTPSConnection("localhost", port, context=context, timeout=20)
        try:
            c.request(method, path, body=body, headers=headers or {})
            r = c.getresponse()
            called.append((method, path.split("?")[0], r.status))
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            c.close()

    monkeypatch.setattr(tls, "_request", verified_request)
    _as_full_flow(ledger, dsn, tmp_path)
    assert called == [
        ("GET", "/.well-known/openid-configuration", 200),
        ("GET", "/ag/login", 200),
        ("POST", "/ag/login", 303),
        ("GET", "/oauth/authorize", 200),
        ("POST", "/ag/consent", 303),
        ("POST", "/oauth/token", 200),
        ("POST", "/oauth/introspect", 200),
        ("POST", "/ag/tasks/task-001/revoke", 200),
    ]


@pytest.mark.parametrize("round_id", range(10))
def test_real_joint_gateway_bootstrap_operator_durable_delivery_external_reader(
    a31_joint, round_id
):
    f = a31_joint
    assert f.env.as_key.curve.name == "SM2"
    assert f.as_material["native_as_stopped"] and f.as_material["as_exit"] in (0, -15)
    assert f.env.token == f.as_material["tokens"][2]
    claims = f.as_material["claims"]
    assert [c["client_id"] for c in claims] == ["agent-planner", "agent-selector", "agent-executor"]
    assert (
        claims[1]["ag_parent_id"] == claims[0]["ag_grant_id"]
        and claims[2]["ag_parent_id"] == claims[1]["ag_grant_id"]
    )
    assert all(c["ag_root_id"] == claims[0]["ag_grant_id"] for c in claims)
    assert [
        (c["method"], c["path"], c["status"])
        for c in f.as_material["calls"]
        if c["path"] == "/oauth/token"
    ] == [("POST", "/oauth/token", 200)] * 3
    with psycopg.connect(f.gateway_dsn) as conn:
        assert conn.execute("SELECT grant_id FROM ag_grants ORDER BY depth").fetchall() == [
            (c["ag_grant_id"],) for c in claims
        ]
        assert conn.execute(
            "SELECT count(*) FROM ag_authorization_requests WHERE status=%s", ("approved",)
        ).fetchone() == (1,)
    assert f.descriptor.scope.gateway_id == "https://gateway.agent-guard.test"
    assert f.trust.role == "AUDIT_SIGNER"
    original = f.all_domains()
    # Reader cannot become writer; denial retains all three domains byte-for-byte.
    with psycopg.connect(f.gateway_dsn) as conn:
        initial = tuple(
            bytes(row[0])
            for row in conn.execute(
                "SELECT raw FROM ag_audit_records WHERE stream_id=%s ORDER BY seq",
                (f.descriptor.scope.stream_id,),
            )
        )
    denied_body = load_strict_json(
        encode_append_batch(f.descriptor.scope.stream_id, initial).exact_body
    )
    status, _ = audit_request(
        f.audit_port,
        f.audit_tls / "ca.pem",
        "/v1/audit/append",
        denied_body,
        credential_id="joint-reader",
        credential=f.reader_token,
    )
    assert status == 403
    assert f.all_domains() == original
    operations = []
    _, verifier, publisher = receipt_services(
        f.env, f.gateway_dsn, gateway_key=f.receipt_key, signing_kid="joint-receipt-1"
    )
    tools = [
        ("procurement.request.read", {"request_id": "req-001"}),
        ("procurement.document.read", {"request_id": "req-001", "document_id": "doc-001"}),
        (
            "procurement.order.create",
            {
                "request_id": "req-001",
                "quote_id": "quote-001",
                "quote_version": "1",
                "items": [{"sku": "sku-001", "quantity": 1}],
                "delivery_id": "office-001",
            },
        ),
        ("notification.template.send", None),
    ]
    for index, (tool, params) in enumerate(tools):
        if params is None:
            params = {
                "template_id": "order-created",
                "recipient_id": "user-demo-001",
                "operation_id": operations[2],
            }
        invocation = f.env.bundle(
            "a31-joint-" + str(round_id) + "-" + str(index), tool=tool, params=params
        )
        from tests.fixtures.gateway import raw_material

        _, _, body = raw_material(f.gateway_dsn, invocation)
        payload = load_strict_json(body)
        status, accepted, _ = signed_request(f.env, f.gateway_port, f.gateway_context, payload)
        assert (
            status == 202
            and accepted["status"] == "RESERVED"
            and accepted["receipt_status"] == "PENDING"
        )
        op = accepted["operation_id"]
        operations.append(op)
        with psycopg.connect(f.downstream_dsn) as conn:
            assert conn.execute(
                "SELECT count(*) FROM ds_operations WHERE operation_id=%s", (op,)
            ).fetchone() == (0,)
        assert f.env.service.run_operation(op).status == "SUCCEEDED"
        before = full_state(f.gateway_dsn, f.downstream_dsn)
        receipt = publisher.publish(op)
        after = full_state(f.gateway_dsn, f.downstream_dsn)
        publication_only(before, after)
        with psycopg.connect(f.gateway_dsn) as conn:
            jws = conn.execute(
                "SELECT receipt_jws FROM ag_receipt_outbox WHERE operation_id=%s", (op,)
            ).fetchone()[0]
            assert jws
            verifier.verify_tx(conn, op, jws)
        from tests.fixtures.gateway import query_bundle

        bundle = query_bundle(f.env, op)
        _, query_proof, query_raw = raw_material(f.gateway_dsn, bundle)
        before_query = full_state(f.gateway_dsn, f.downstream_dsn)
        status, answer, _ = signed_request(
            f.env,
            f.gateway_port,
            f.gateway_context,
            load_strict_json(query_raw),
            query=True,
            proof_override=query_proof.decode("ascii"),
        )
        assert status == 200 and answer["operation_id"] == op and answer["status"] == "SUCCEEDED"
        assert answer["receipt_status"] == "READY" and answer["receipt_jws"] == jws
        with psycopg.connect(f.gateway_dsn) as conn:
            actual_refs = conn.execute(
                "SELECT evidence_ref FROM ag_proofs WHERE proof_jti=%s",
                (bundle.query.proof_jti,),
            ).fetchall()
            assert len(actual_refs) == 1
            actual_ref = actual_refs[0][0]
            assert actual_ref != bundle.evidence_ref
            actual_material = conn.execute(
                "SELECT token_bytes,proof_bytes,body_bytes FROM ag_verified_evidence "
                "WHERE evidence_ref=%s",
                (actual_ref,),
            ).fetchone()
            original_material = raw_material(f.gateway_dsn, bundle)
            assert tuple(bytes(part) for part in actual_material) == original_material
        result_read_only(
            before_query,
            full_state(f.gateway_dsn, f.downstream_dsn),
            evidence_ref=actual_ref,
            proof_jti=bundle.query.proof_jti,
            operation_id=op,
            staging=True,
            observed_response=answer,
        )
        stable = full_state(f.gateway_dsn, f.downstream_dsn)
        assert publisher.publish(op) == receipt
        assert full_state(f.gateway_dsn, f.downstream_dsn) == stable
    with psycopg.connect(f.gateway_dsn) as conn:
        raw_records = tuple(
            bytes(row[0])
            for row in conn.execute(
                "SELECT raw FROM ag_audit_records WHERE stream_id=%s ORDER BY seq",
                (f.descriptor.scope.stream_id,),
            )
        )
        assert [load_strict_json(r)["kind"] for r in raw_records] == ["BOOTSTRAP"] + [
            "FIRST",
            "TERMINAL",
            "PUBLISH",
            "QUERY",
        ] * 4
        assert (
            conn.execute(
                (
                    "SELECT "
                    "amount_reserved,amount_settled,calls_reserved"
                    ",calls_settled FROM ag_grants ORDER BY depth"
                )
            ).fetchall()
            == [(0, 70000, 0, 4)] * 3
        )
    with psycopg.connect(f.downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_operations").fetchone() == (4,)
        assert conn.execute("SELECT count(*) FROM ds_orders").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM ds_notifications").fetchone() == (1,)
    # Real immutable pending and native CLI recovery against the independent HTTPS service.
    delivery = bind_frozen_delivery(f)
    assert delivery.check_cli() == 0
    pending = delivery.persist_pending()
    saved = delivery.pending_snapshot()
    assert pending.exact_body == saved.exact_body and pending.batch_id == saved.batch_id
    before_lost = f.all_domains()
    old_pid, new_pid = delivery.send_pending_lost_reply()
    assert type(old_pid) is int and type(new_pid) is int and old_pid != new_pid
    assert delivery.pending_snapshot() == saved
    status, answer = f.reader_latest()
    assert status == 200
    pin = answer["checkpoint_jws"]
    observed = verify_checkpoint(pin, trust=(f.trust,), expected_scope=f.descriptor.scope)
    assert observed.claims.sequence == pending.end_sequence
    assert observed.claims.head_digest == pending.end_digest == sm3_b64url(raw_records[-1])
    before_bad = f.all_domains()
    with pytest.raises((ValueError, RuntimeError)):
        delivery.reject_untrusted_pin(pin[:-1] + ("A" if pin[-1] != "A" else "B"))
    assert f.all_domains() == before_bad
    delivery.restart_and_reconcile(pin)
    cursor = delivery.cursor_snapshot()
    assert cursor.ack_sequence == pending.end_sequence
    assert cursor.ack_head_digest == pending.end_digest
    assert cursor.ack_checkpoint_digest == observed.jws_digest
    assert cursor.pending_batch_id is None
    prefix = delivery.read_remote_prefix(pin)
    assert prefix.scope == f.descriptor.scope
    assert prefix.sequence == len(raw_records) and prefix.head_digest == sm3_b64url(raw_records[-1])
    assert prefix.checkpoint_jws == pin
    assert (
        f.all_domains()["gateway"]["ag_receipt_outbox"]
        == before_lost["gateway"]["ag_receipt_outbox"]
    )
    assert f.all_domains()["downstream"] == before_lost["downstream"]


def test_cli_init_must_create_private_material(tmp_path):
    """Original AS CLI private-material permissions control, ordinary umask."""
    import stat
    import subprocess
    import sys

    target = tmp_path / "cli-output"
    done = subprocess.run(
        [sys.executable, "-m", "agent_guard.server", "init", "--out", str(target)],
        capture_output=True,
        text=True,
        umask=0o022,
        timeout=60,
    )
    assert done.returncode == 0
    files = [target / "as-sign-key.pem", target / "agent-planner.pem", target / "secrets.json"]
    observed = {p.name: oct(stat.S_IMODE(p.stat().st_mode)) for p in files}
    assert all(p.stat().st_mode & 0o077 == 0 for p in files), (
        "private material permissions: " + str(observed)
    )
