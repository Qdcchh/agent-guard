"""Real AS root→two children→controlled evidence→four-tool A execution."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

import psycopg
import pytest

from agent_guard.authorization.evidence_store import EvidenceError, EvidenceStore
from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.authorization.verifier import InvocationVerifier
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode
from agent_guard.contracts.ledger import INVOKE_ENDPOINT, AcceptDisposition, LedgerError
from agent_guard.crypto.sm import generate_sm2_private_key, sign_compact_jws
from agent_guard.evidence.receipt import ReceiptTrust, verify_receipt_bundle
from agent_guard.execution.receipt_projection import project_receipt
from agent_guard.execution.service import ExecutionService
from agent_guard.execution.verified import VerifiedExecution
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.tools.downstream import MockDownstream
from tests.fixtures.execution import DOWNSTREAM_SECRET, build_catalog
from tests.integration.test_exchange_service import (
    ISSUER,
    TENANT,
    _exchange,
    _form,
    _root,
)

pytestmark = pytest.mark.integration
TOOLS = (
    "procurement.request.read",
    "procurement.document.read",
    "procurement.order.create",
    "notification.template.send",
)
CONSTRAINTS = {
    "request_ids": ["req-001"],
    "document_ids": ["doc-001"],
    "quote_versions": ["quote-001@1"],
    "skus": ["sku-001"],
    "max_quantity": 2,
    "delivery_ids": ["office-001"],
    "template_ids": ["order-created"],
    "recipient_ids": ["user-demo-001"],
}


@dataclass
class SignedEnv:
    as_key: object
    keys: dict
    registrations: dict
    token: str
    verifier: InvocationVerifier
    evidence: EvidenceStore
    service: ExecutionService
    adapter: VerifiedExecution
    downstream: MockDownstream

    def bundle(
        self,
        key="purchase-1",
        *,
        tool=TOOLS[2],
        params=None,
        now=None,
        proof_now=None,
        proof_lifetime=60,
    ):
        if params is None:
            params = {
                "request_id": "req-001",
                "quote_id": "quote-001",
                "quote_version": "1",
                "items": [{"sku": "sku-001", "quantity": 1}],
                "delivery_id": "office-001",
            }
        request = {
            "profile": "GM-MVP-1",
            "task_id": "task-001",
            "tool_id": tool,
            "tool_version": "1",
            "idempotency_key": key,
            "params": params,
        }
        now = int(time.time()) if now is None else now
        proof = sign_ag_proof(
            self.keys["executor"],
            kid=self.registrations[(TENANT, "agent-executor")].kid,
            client_id="agent-executor",
            purpose="invoke",
            endpoint=INVOKE_ENDPOINT,
            body=request,
            token=self.token,
            now=now if proof_now is None else proof_now,
            lifetime_seconds=proof_lifetime,
        )
        return self.verifier.verify_bundle(
            self.token, proof, body=canonical_json_bytes(request), now=now
        )


def signed_env(dsn, downstream_dsn, *, leaf_ttl=100):
    as_key, keys, registrations, exchanges, root = _root(
        dsn,
        approved_overrides={
            "scope": "openid " + " ".join(TOOLS),
            "constraints": CONSTRAINTS,
        },
    )
    form = _form(as_key, root.access_token)
    form["scope"] = " ".join(TOOLS)
    child = _exchange(exchanges, keys, registrations, form)
    form = _form(as_key, child.access_token, recipient="executor", ttl=leaf_ttl)
    form["scope"] = " ".join(TOOLS)
    leaf = _exchange(exchanges, keys, registrations, form, holder="selector")
    evidence = EvidenceStore(dsn)
    provider = PermissionSnapshotProvider(
        dsn,
        issuer=ISSUER,
        as_keys={"as-sign-1": as_key.public_key()},
        registrations={(r.tenant_id, r.client_id, r.kid): r for r in registrations.values()},
    )
    verifier = InvocationVerifier(
        issuer=ISSUER,
        as_keys={"as-sign-1": as_key.public_key()},
        identities=exchanges._identities,
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
        catalog=build_catalog(TENANT, "task-001"),
        downstream=downstream,
        downstream_secret=DOWNSTREAM_SECRET,
    )
    return SignedEnv(
        as_key,
        keys,
        registrations,
        leaf.access_token,
        verifier,
        evidence,
        service,
        VerifiedExecution(service, evidence_store=evidence),
        downstream,
    )


def test_signed_chain_all_four_tools_and_real_receipt(ledger, dsn, downstream_dsn):
    env = signed_env(dsn, downstream_dsn)
    operations = []
    for index, tool in enumerate(TOOLS):
        params = [
            {"request_id": "req-001"},
            {"request_id": "req-001", "document_id": "doc-001"},
            None,
            {
                "template_id": "order-created",
                "recipient_id": "user-demo-001",
                "operation_id": operations[0] if operations else "",
            },
        ][index]
        bundle = env.bundle(f"tool-{index}", tool=tool, params=params)
        accepted = env.adapter.accept(bundle)
        operations.append(accepted.operation_id)
        assert env.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
        retry = env.adapter.accept(env.bundle(f"tool-{index}", tool=tool, params=params))
        assert retry.disposition is AcceptDisposition.EXISTING
        assert retry.operation_id == accepted.operation_id
        with psycopg.connect(dsn) as conn:
            projection = project_receipt(conn, accepted.operation_id)
            claims = load_strict_json(projection.claims_bytes)
            gateway = generate_sm2_private_key()
            signed = sign_compact_jws(
                gateway, claims, key_id="gw-sign", token_type="ag-receipt+jwt"
            )
            from agent_guard.contracts.ledger_changes import load_ledger_changes

            evidence = {
                "manifest_version": "AG-EVIDENCE-1",
                "anchoring_status": "UNANCHORED",
                "receipt_jws": signed,
                "ancestor_tokens": list(projection.ancestor_tokens),
                "token_jws": projection.token_bytes.decode(),
                "proof_jws": projection.proof_bytes.decode(),
                "request": load_strict_json(projection.request_bytes),
                "result": load_strict_json(projection.result_bytes),
                "ledger_changes": load_ledger_changes(projection.ledger_bytes),
            }
            trust = ReceiptTrust(
                issuer=ISSUER,
                as_keys={"as-sign-1": env.as_key.public_key()},
                gateway_keys={"gw-sign": gateway.public_key()},
                holder_keys={
                    r.kid: env.keys[r.client_id.removeprefix("agent-")].public_key()
                    for r in env.registrations.values()
                },
                historical_registrations={r.kid: r for r in env.registrations.values()},
            )
            verified = verify_receipt_bundle(evidence, trust=trust)
            assert verified.operation_id == accepted.operation_id
            assert conn.execute(
                "SELECT receipt_status,receipt_jws FROM ag_receipt_outbox WHERE operation_id=%s",
                (accepted.operation_id,),
            ).fetchone() == ("PENDING", None)
    with psycopg.connect(dsn) as conn:
        assert (
            conn.execute(
                "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled "
                "FROM ag_grants ORDER BY depth"
            ).fetchall()
            == [(0, 70000, 0, 4)] * 3
        )
        assert conn.execute(
            "SELECT kind,count(*) FROM ag_operation_evidence GROUP BY kind ORDER BY kind"
        ).fetchall() == [("first", 4), ("retry", 4)]


@pytest.mark.parametrize("tool", TOOLS[2:])
def test_projection_rejects_read_shaped_nonread_success(ledger, dsn, downstream_dsn, tool):
    env = signed_env(dsn, downstream_dsn)
    order = env.adapter.accept(env.bundle())
    assert env.service.run_operation(order.operation_id).status == "SUCCEEDED"
    operation = order
    if tool == TOOLS[3]:
        operation = env.adapter.accept(
            env.bundle(
                "notify",
                tool=tool,
                params={
                    "template_id": "order-created",
                    "recipient_id": "user-demo-001",
                    "operation_id": order.operation_id,
                },
            )
        )
        assert env.service.run_operation(operation.operation_id).status == "SUCCEEDED"
    with psycopg.connect(dsn) as conn:
        before = conn.execute("SELECT * FROM ag_receipt_outbox ORDER BY operation_id").fetchall()
        original = project_receipt(conn, operation.operation_id)
        with conn.transaction(force_rollback=True):
            conn.execute(
                "ALTER TABLE ag_receipt_outbox DISABLE TRIGGER ag_receipt_outbox_guard_trg"
            )
            conn.execute(
                "UPDATE ag_receipt_outbox SET result_bytes=%s WHERE operation_id=%s",
                (
                    canonical_json_bytes(
                        {
                            "kind": "read",
                            "operation_id": operation.operation_id,
                            "tool_id": tool,
                        }
                    ),
                    operation.operation_id,
                ),
            )
            with pytest.raises(ExecutionError) as exc:
                project_receipt(conn, operation.operation_id)
            assert exc.value.code is ExecutionErrorCode.DOWNSTREAM_INCONSISTENT
        assert project_receipt(conn, operation.operation_id) == original
        assert (
            conn.execute("SELECT * FROM ag_receipt_outbox ORDER BY operation_id").fetchall()
            == before
        )


@pytest.mark.parametrize("change", ["ref", "scope", "chain", "subject", "proof", "source"])
def test_tampered_bundle_fails_without_new_accept(ledger, dsn, downstream_dsn, change):
    env = signed_env(dsn, downstream_dsn)
    b = env.bundle()
    if change == "ref":
        b = replace(b, evidence_ref="ev-" + "0" * 64)
    if change == "scope":
        b = replace(b, permissions=replace(b.permissions, scope=()))
    if change == "chain":
        b = replace(
            b,
            permissions=replace(b.permissions, chain_grant_ids=(b.invocation.grant_id,)),
        )
    if change == "subject":
        b = replace(b, invocation=replace(b.invocation, subject="other-user"))
    if change == "proof":
        b = replace(b, invocation=replace(b.invocation, proof_jti="forged-jti"))
    if change == "source":
        modified = replace(
            b.permissions,
            chain=tuple(replace(c, max_quantity=5) for c in b.permissions.chain),
        )
        b = replace(b, permissions=modified, source=replace(b.source, snapshot=modified))
    with psycopg.connect(dsn) as conn:
        before = conn.execute("SELECT count(*) FROM ag_proofs").fetchone()
    with pytest.raises((EvidenceError, ExecutionError, LedgerError)):
        env.adapter.accept(b)
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM ag_operation_evidence").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM ag_proofs").fetchone() == before
        assert conn.execute(
            "SELECT sum(amount_reserved),sum(calls_reserved) FROM ag_grants"
        ).fetchone() == (0, 0)


def test_canonical_query_real_verification_and_zero_budget_effect(ledger, dsn, downstream_dsn):
    from agent_guard.contracts.execution import VerifiedResultQuery
    from agent_guard.contracts.ledger import QUERY_ENDPOINT, TrustedCost

    env = signed_env(dsn, downstream_dsn)
    now = int(time.time())
    request = {
        "profile": "GM-MVP-1",
        "task_id": "task-001",
        "operation_id": "unowned-operation",
    }
    proof = sign_ag_proof(
        env.keys["executor"],
        kid=env.registrations[(TENANT, "agent-executor")].kid,
        client_id="agent-executor",
        purpose="result-read",
        endpoint=QUERY_ENDPOINT,
        body=request,
        token=env.token,
        now=now,
    )
    with psycopg.connect(dsn) as conn:
        before = conn.execute("SELECT count(*) FROM ag_proofs").fetchone()
    canonical = env.verifier.verify_canonical_result_read(
        env.token, proof, body=canonical_json_bytes(request), now=now
    )
    assert type(canonical) is VerifiedResultQuery
    assert canonical.subject == "user-001" and canonical.method == "POST"
    assert canonical.operation_id == "unowned-operation" and canonical.purpose == "result-read"
    assert canonical.endpoint == QUERY_ENDPOINT and canonical.tenant_id == TENANT
    # It stages raw query evidence but does not claim ownership authorization.
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_proofs").fetchone() == before
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM ag_operation_evidence").fetchone() == (0,)
        assert conn.execute(
            "SELECT purpose,method,proof_jti FROM ag_verified_evidence"
        ).fetchone() == ("result-read", "POST", canonical.proof_jti)
    with pytest.raises(LedgerError):
        ledger.accept(canonical, TrustedCost(0))
    with pytest.raises(ValueError):
        env.adapter.accept(canonical)


@pytest.mark.parametrize(
    "mutation",
    ["seq", "duplicate", "truncated", "reorder", "phase", "delta", "unknown", "result"],
)
def test_persisted_projection_refuses_adversarial_material(ledger, dsn, downstream_dsn, mutation):
    import json

    from agent_guard.contracts.encoding import EncodingError
    from agent_guard.contracts.ledger_changes import load_ledger_changes
    from agent_guard.execution.receipt_projection import ReceiptProjectionError

    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    assert env.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
    with psycopg.connect(dsn) as conn:
        original = conn.execute("SELECT ledger_changes_json FROM ag_receipt_outbox").fetchone()[0]
        row = load_ledger_changes(bytes(original), internal=True)
        if mutation == "seq":
            row["events"][1]["seq"] = 0
        if mutation == "duplicate":
            row["events"][0]["nodes"][1] = row["events"][0]["nodes"][0]
        if mutation == "truncated":
            row["events"][0]["nodes"].pop()
        if mutation == "reorder":
            row["events"].reverse()
        if mutation == "phase":
            row["events"][1]["phase"] = "RELEASE"
        if mutation == "delta":
            row["events"][1]["nodes"][0]["amount_reserved_delta"] = 0
        if mutation == "unknown":
            row["events"][0]["extra"] = 1
        with conn.transaction(force_rollback=True):
            conn.execute(
                "ALTER TABLE ag_receipt_outbox DISABLE TRIGGER ag_receipt_outbox_guard_trg"
            )
            if mutation == "result":
                conn.execute(
                    "UPDATE ag_receipt_outbox SET result_bytes=%s",
                    (
                        b'{"kind":"read","operation_id":"other","tool_id":"procurement.request.read"}',
                    ),
                )
            else:
                conn.execute(
                    "UPDATE ag_receipt_outbox SET ledger_changes_json=%s",
                    (json.dumps(row).encode(),),
                )
            with pytest.raises((ReceiptProjectionError, EncodingError, ExecutionError)):
                project_receipt(conn, accepted.operation_id)
        assert (
            conn.execute("SELECT ledger_changes_json FROM ag_receipt_outbox").fetchone()[0]
            == original
        )
        assert project_receipt(conn, accepted.operation_id)


@pytest.mark.parametrize("depth", [0, 1])
@pytest.mark.parametrize(
    "variant", ["signature", "digest", "constraints", "actor", "spki", "missing"]
)
def test_real_signed_ancestor_mismatch_is_rejected_before_staging(
    ledger, dsn, downstream_dsn, depth, variant
):
    from agent_guard.authorization.claims import ClaimsError
    from agent_guard.authorization.permission_snapshot import PermissionSnapshotError
    from agent_guard.crypto.sm import (
        InvalidSm2Signature,
        sm3_b64url,
        verify_compact_jws,
    )

    env = signed_env(dsn, downstream_dsn)
    with psycopg.connect(dsn) as conn:
        before = conn.execute("SELECT count(*) FROM ag_proofs").fetchone()
        grant_id = conn.execute(
            "SELECT grant_id FROM ag_grants WHERE depth=%s", (depth,)
        ).fetchone()[0]
        saved = conn.execute(
            "SELECT token_jws,token_sm3,constraints_json,actor_json,holder_spki_sm3 "
            "FROM ag_grant_tokens WHERE grant_id=%s",
            (grant_id,),
        ).fetchone()
        raw = verify_compact_jws(
            saved[0],
            expected_type="ag-at+jwt",
            trusted_keys={"as-sign-1": env.as_key.public_key()},
        )
        conn.execute("ALTER TABLE ag_grant_tokens DISABLE TRIGGER ag_grant_tokens_immutable_trg")
        if variant == "missing":
            conn.execute("DELETE FROM ag_grant_tokens WHERE grant_id=%s", (grant_id,))
        elif variant == "signature":
            conn.execute(
                "UPDATE ag_grant_tokens SET token_jws=token_jws||%s WHERE grant_id=%s",
                ("x", grant_id),
            )
        elif variant == "digest":
            conn.execute(
                "UPDATE ag_grant_tokens SET token_sm3=%s WHERE grant_id=%s",
                ("wrong-digest", grant_id),
            )
        else:
            if variant == "constraints":
                raw["ag_constraints"]["request_ids"] = []
            if variant == "actor":
                raw["act"]["sub"] = "did:web:other.agent-guard.test:forged"
            if variant == "spki":
                raw["ag_cnf"]["spki_sm3"] = sm3_b64url(b"other-key")
            token = sign_compact_jws(env.as_key, raw, key_id="as-sign-1", token_type="ag-at+jwt")
            conn.execute(
                "UPDATE ag_grant_tokens SET token_jws=%s,token_sm3=%s,"
                "constraints_json=%s,actor_json=%s,holder_spki_sm3=%s WHERE grant_id=%s",
                (
                    token,
                    sm3_b64url(token.encode()),
                    canonical_json_bytes(raw["ag_constraints"]),
                    canonical_json_bytes(raw["act"]),
                    raw["ag_cnf"]["spki_sm3"],
                    grant_id,
                ),
            )
        conn.execute("ALTER TABLE ag_grant_tokens ENABLE TRIGGER ag_grant_tokens_immutable_trg")
    with pytest.raises((PermissionSnapshotError, ClaimsError, InvalidSm2Signature)):
        env.bundle()
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ag_verified_evidence").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM ag_proofs").fetchone() == before
        assert conn.execute(
            "SELECT sum(amount_reserved),sum(calls_reserved) FROM ag_grants"
        ).fetchone() == (0, 0)


def signed_projection_material(env, projection):
    from agent_guard.contracts.ledger_changes import load_ledger_changes

    gateway = generate_sm2_private_key()
    receipt = sign_compact_jws(
        gateway,
        load_strict_json(projection.claims_bytes),
        key_id="gw-independent",
        token_type="ag-receipt+jwt",
    )
    bundle = {
        "manifest_version": "AG-EVIDENCE-1",
        "anchoring_status": "UNANCHORED",
        "receipt_jws": receipt,
        "ancestor_tokens": list(projection.ancestor_tokens),
        "token_jws": projection.token_bytes.decode(),
        "proof_jws": projection.proof_bytes.decode(),
        "request": load_strict_json(projection.request_bytes),
        "result": load_strict_json(projection.result_bytes),
        "ledger_changes": load_ledger_changes(projection.ledger_bytes),
    }
    trust = ReceiptTrust(
        issuer=ISSUER,
        as_keys={"as-sign-1": env.as_key.public_key()},
        gateway_keys={"gw-independent": gateway.public_key()},
        holder_keys={
            r.kid: env.keys[r.client_id.removeprefix("agent-")].public_key()
            for r in env.registrations.values()
        },
        historical_registrations={r.kid: r for r in env.registrations.values()},
    )
    return bundle, trust, gateway


def verify_projection(env, projection):
    bundle, trust, _ = signed_projection_material(env, projection)
    return verify_receipt_bundle(bundle, trust=trust)


def test_real_failed_projection_has_zero_final_amount_and_releases_all_nodes(
    ledger, dsn, downstream_dsn
):
    env = signed_env(dsn, downstream_dsn)
    env.service._downstream = MockDownstream(downstream_dsn, service_secret=DOWNSTREAM_SECRET)
    accepted = env.adapter.accept(env.bundle())
    assert env.service.run_operation(accepted.operation_id).status == "FAILED"
    with psycopg.connect(dsn) as conn:
        projected = project_receipt(conn, accepted.operation_id)
        assert projected == project_receipt(conn, accepted.operation_id)
        verified = verify_projection(env, projected)
        assert verified.status == "FAILED" and verified.amount_fen == 0
        assert (
            conn.execute(
                "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled FROM ag_grants"
            ).fetchall()
            == [(0, 0, 0, 0)] * 3
        )
        assert conn.execute(
            "SELECT receipt_status,receipt_jws FROM ag_receipt_outbox"
        ).fetchone() == ("PENDING", None)


def test_real_unknown_evidence_stays_bound_until_recovery_without_early_receipt(
    ledger, dsn, downstream_dsn
):
    from agent_guard.execution.receipt_projection import ReceiptProjectionError

    env = signed_env(dsn, downstream_dsn)

    class LoseResponse:
        def execute(self, **kwargs):
            env.downstream.execute(**kwargs)
            raise ConnectionError("synthetic response loss after independent commit")

        def query(self, **kwargs):
            return env.downstream.query(**kwargs)

    env.service._downstream = LoseResponse()
    accepted = env.adapter.accept(env.bundle())
    assert env.service.run_operation(accepted.operation_id).status == "UNKNOWN"
    with psycopg.connect(dsn) as conn:
        assert (
            conn.execute(
                "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled FROM ag_grants"
            ).fetchall()
            == [(70000, 0, 1, 0)] * 3
        )
        assert conn.execute(
            "SELECT kind,count(*) FROM ag_operation_evidence GROUP BY kind"
        ).fetchall() == [("first", 1)]
        with pytest.raises(ReceiptProjectionError, match="no final"):
            project_receipt(conn, accepted.operation_id)
    # The held lease is the original worker's; use its existing owner explicitly.
    with psycopg.connect(dsn) as conn:
        owner = conn.execute(
            "SELECT owner_token FROM ag_execution_leases WHERE operation_id=%s",
            (accepted.operation_id,),
        ).fetchone()[0]
    assert env.service.reconcile(accepted.operation_id, owner_token=owner).status == "SUCCEEDED"
    with psycopg.connect(dsn) as conn:
        projection = project_receipt(conn, accepted.operation_id)
        assert verify_projection(env, projection).status == "SUCCEEDED"
        assert (
            conn.execute(
                "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled FROM ag_grants"
            ).fetchall()
            == [(0, 70000, 0, 1)] * 3
        )


def _receipt_database_state(dsn):
    with psycopg.connect(dsn) as conn:
        return {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
            for table, order in (
                ("ag_operations", "operation_id"),
                ("ag_grants", "grant_id"),
                ("ag_proofs", "holder_kid,purpose,endpoint,proof_jti"),
                ("ag_ledger_events", "event_id"),
                ("ag_ledger_event_nodes", "event_id,position"),
                ("ag_operation_evidence", "operation_id,kind,evidence_ref"),
                ("ag_receipt_outbox", "operation_id"),
            )
        }


@pytest.mark.parametrize("offset", [0, 4, -2, 5])
def test_real_live_proof_offsets_remain_valid_offline(ledger, dsn, downstream_dsn, offset):
    env = signed_env(dsn, downstream_dsn)
    now = int(time.time())
    accepted = env.adapter.accept(env.bundle(now=now, proof_now=now + offset))
    assert env.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
    before = _receipt_database_state(dsn)
    with psycopg.connect(dsn) as conn:
        projection = project_receipt(conn, accepted.operation_id)
        assert verify_projection(env, projection).status == "SUCCEEDED"
        assert project_receipt(conn, accepted.operation_id) == projection
        assert (
            conn.execute(
                "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled FROM ag_grants"
            ).fetchall()
            == [(0, 70000, 0, 1)] * 3
        )
    assert _receipt_database_state(dsn) == before
    with psycopg.connect(downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_orders").fetchone() == (1,)


def test_real_delayed_recovery_receipt_survives_token_and_proof_expiry(ledger, dsn, downstream_dsn):
    from agent_guard.crypto.sm import verify_compact_jws

    env = signed_env(dsn, downstream_dsn, leaf_ttl=5)

    class LoseResponse:
        def execute(self, **kwargs):
            env.downstream.execute(**kwargs)
            raise ConnectionError("synthetic response loss")

        def query(self, **kwargs):
            return env.downstream.query(**kwargs)

    env.service._downstream = LoseResponse()
    bundle = env.bundle(proof_lifetime=3)
    accepted = env.adapter.accept(bundle)
    assert env.service.run_operation(accepted.operation_id).status == "UNKNOWN"
    leaf = verify_compact_jws(
        env.token,
        expected_type="ag-at+jwt",
        trusted_keys={"as-sign-1": env.as_key.public_key()},
    )
    with psycopg.connect(dsn) as conn:
        evidence_before = conn.execute("SELECT * FROM ag_operation_evidence").fetchall()
        owner = conn.execute("SELECT owner_token FROM ag_execution_leases").fetchone()[0]
    # Real elapsed time, original timestamps and original immutable accepted intent.
    time.sleep(max(0, leaf["exp"] + 1 - time.time()))
    assert int(time.time()) > leaf["exp"]
    assert env.service.reconcile(accepted.operation_id, owner_token=owner).status == "SUCCEEDED"
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT * FROM ag_operation_evidence").fetchall() == evidence_before
        projection = project_receipt(conn, accepted.operation_id)
        assert load_strict_json(projection.claims_bytes)["iat"] > leaf["exp"]
        before = _receipt_database_state(dsn)
        assert verify_projection(env, projection).status == "SUCCEEDED"
        assert project_receipt(conn, accepted.operation_id) == projection
    assert _receipt_database_state(dsn) == before
    with psycopg.connect(downstream_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM ds_orders").fetchone() == (1,)


@pytest.mark.parametrize(
    "variant,valid",
    [
        ("future-five", True),
        ("future-six", False),
        ("pre-token-fresh", True),
        ("pre-token-expired", False),
        ("expiry-one-after", True),
        ("expiry-at-start", False),
        ("receipt-before-token", False),
        ("future-token", False),
        ("ancestor-disjoint", False),
        ("proof-after-token", False),
        ("proof-lifetime-too-long", False),
        ("proof-iat-bool", False),
        ("delayed-completion", True),
    ],
)
def test_offline_receipt_common_time_window_with_authentic_rebindings(
    ledger, dsn, downstream_dsn, variant, valid
):
    from agent_guard.crypto.sm import sm3_b64url, verify_compact_jws
    from agent_guard.evidence.receipt import ReceiptVerificationError

    env = signed_env(dsn, downstream_dsn)
    accepted = env.adapter.accept(env.bundle())
    assert env.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
    with psycopg.connect(dsn) as conn:
        projection = project_receipt(conn, accepted.operation_id)
    original = _receipt_database_state(dsn)
    bundle, trust, gateway = signed_projection_material(env, projection)
    receipt = load_strict_json(projection.claims_bytes)
    base = receipt["iat"]
    path = [
        verify_compact_jws(token, expected_type="ag-at+jwt", trusted_keys=trust.as_keys)
        for token in bundle["ancestor_tokens"]
    ]
    for token in path:
        token.update(iat=base, nbf=base, exp=base + 20)
    proof = verify_compact_jws(
        bundle["proof_jws"], expected_type="ag-pop+jwt", trusted_keys=trust.holder_keys
    )
    proof.update(iat=base, exp=base + 5)
    if variant in {"future-five", "future-six"}:
        proof.update(iat=base + (5 if variant == "future-five" else 6), exp=base + 20)
    elif variant.startswith("pre-token-"):
        proof.update(iat=base - 10, exp=base + (1 if valid else 0))
    elif variant.startswith("expiry-"):
        proof["exp"] = base + (1 if valid else 0)
    elif variant == "receipt-before-token":
        receipt["iat"] = base - 1
    elif variant == "future-token":
        for token in path:
            token.update(iat=base + 1, nbf=base + 1)
    elif variant == "ancestor-disjoint":
        receipt["iat"] = base + 30
        path[0]["exp"] = base + 10
        path[-1]["nbf"] = base + 10
        proof["exp"] = base + 20
    elif variant == "proof-after-token":
        for token in path:
            token.update(iat=base - 30, nbf=base - 30, exp=base - 1)
        proof.update(iat=base + 4, exp=base + 20)
    elif variant == "proof-lifetime-too-long":
        proof["exp"] = base + 61
    elif variant == "proof-iat-bool":
        proof["iat"] = True
    elif variant == "delayed-completion":
        receipt["iat"] = base + 1000
    bundle["ancestor_tokens"] = [
        sign_compact_jws(env.as_key, token, key_id="as-sign-1", token_type="ag-at+jwt")
        for token in path
    ]
    bundle["token_jws"] = bundle["ancestor_tokens"][-1]
    if variant == "future-token":
        signed_leaf = verify_compact_jws(
            bundle["token_jws"], expected_type="ag-at+jwt", trusted_keys=trust.as_keys
        )
        assert signed_leaf["iat"] == signed_leaf["nbf"] == base + 1
        assert proof["iat"] == base
        assert receipt["iat"] == base
    proof["token_sm3"] = sm3_b64url(bundle["token_jws"].encode())
    bundle["proof_jws"] = sign_compact_jws(
        env.keys["executor"],
        proof,
        key_id=env.registrations[(TENANT, "agent-executor")].kid,
        token_type="ag-pop+jwt",
    )
    receipt["token_sm3"] = proof["token_sm3"]
    receipt["proof_sm3"] = sm3_b64url(bundle["proof_jws"].encode())
    bundle["receipt_jws"] = sign_compact_jws(
        gateway, receipt, key_id="gw-independent", token_type="ag-receipt+jwt"
    )
    # All signatures and token/proof digests were genuinely rebound to reach the
    # temporal oracle. Synthetic changes exist only in this offline copy.
    if valid:
        assert verify_receipt_bundle(bundle, trust=trust).status == "SUCCEEDED"
    else:
        with pytest.raises(ReceiptVerificationError):
            verify_receipt_bundle(bundle, trust=trust)
    assert _receipt_database_state(dsn) == original
    with psycopg.connect(dsn) as conn:
        assert project_receipt(conn, accepted.operation_id) == projection
