"""Test-only real AS material, independent gateway keys and complete effect oracles."""

from dataclasses import replace

import psycopg
import pytest

from agent_guard.authorization.evidence_store import EvidenceStore
from agent_guard.authorization.exchange_service import TokenExchangeService
from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.authorization.verifier import InvocationVerifier
from agent_guard.crypto.sm import generate_sm2_private_key
from agent_guard.execution.receipt_publication import InternalPublisher, ReceiptVerifier
from agent_guard.execution.service import ExecutionService
from agent_guard.execution.verified import VerifiedExecution
from agent_guard.ledger.provisioning import register_principal
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.tools.catalog import CatalogQuoteLine
from agent_guard.tools.downstream import MockDownstream
from tests.fixtures.execution import DOWNSTREAM_SECRET, build_catalog
from tests.integration import test_exchange_service as exchange
from tests.integration import test_login_consent as login
from tests.integration.test_verified_execution import SignedEnv


def receipt_services(env, dsn, *, gateway_key=None, signing_kid="gw-receipt-1"):
    key = gateway_key or generate_sm2_private_key()
    registrations = {(r.tenant_id, r.client_id, r.kid): r for r in env.registrations.values()}
    provider = PermissionSnapshotProvider(
        dsn,
        issuer=exchange.ISSUER,
        as_keys={"as-sign-1": env.as_key.public_key()},
        registrations=registrations,
    )
    verifier = ReceiptVerifier(
        issuer=exchange.ISSUER,
        as_keys={"as-sign-1": env.as_key.public_key()},
        gateway_keys={signing_kid: key.public_key()},
        registrations=registrations,
        permission_provider=provider,
    )
    return (
        key,
        verifier,
        InternalPublisher(dsn, private_key=key, signing_kid=signing_kid, verifier=verifier),
    )


def real_login_capacity_env(
    dsn, downstream_dsn, *, sku_width=4, quantity=1, unit_price=1, budget=None
):
    """Actual login/consent/code root and two real exchanges for all 256 SKUs."""
    skus = [f"s{i:03d}" + "x" * (sku_width - 4) for i in range(256)]
    constraints = dict(login.CONSTRAINTS, skus=skus, max_quantity=quantity)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(login, "CONSTRAINTS", constraints)
        if budget is not None:
            original_register = login.register_task_policy

            def register(conn, **kwargs):
                kwargs["amount_limit_fen"] = budget
                return original_register(conn, **kwargs)

            patch.setattr(login, "register_task_policy", register)
        stack = login._setup(dsn)
    keys, registrations, _ = exchange._identities()
    keys["planner"] = stack.planner_key
    planner = stack.codes._identities._registrations[(exchange.TENANT, "agent-planner")]
    registrations[(exchange.TENANT, "agent-planner")] = planner
    identities = exchange._resolver(registrations)
    stack.codes._identities = identities
    with psycopg.connect(dsn) as conn:
        for r in registrations.values():
            if r.client_id != "agent-planner":
                register_principal(conn, tenant_id=r.tenant_id, client_id=r.client_id, kid=r.kid)
    session = login._session(stack)
    redirect, _ = login._approve(stack, session)
    root = login._redeem(stack, login._code_from(redirect.location))
    exchanges = TokenExchangeService(
        dsn,
        issuer=exchange.ISSUER,
        token_endpoint=exchange.TOKEN_ENDPOINT,
        signing_key=stack.as_key,
        signing_kid="as-sign-1",
        identities=identities,
    )
    child_form = exchange._form(stack.as_key, root.access_token)
    if budget is not None:
        child_form["ag_amount_limit_fen"] = str(budget)
    child = exchange._exchange(exchanges, keys, registrations, child_form)
    leaf_form = exchange._form(stack.as_key, child.access_token, recipient="executor", ttl=100)
    if budget is not None:
        leaf_form["ag_amount_limit_fen"] = str(budget)
    leaf = exchange._exchange(exchanges, keys, registrations, leaf_form, holder="selector")
    evidence = EvidenceStore(dsn)
    provider = PermissionSnapshotProvider(
        dsn,
        issuer=exchange.ISSUER,
        as_keys={"as-sign-1": stack.as_key.public_key()},
        registrations={(r.tenant_id, r.client_id, r.kid): r for r in registrations.values()},
    )
    verifier = InvocationVerifier(
        issuer=exchange.ISSUER,
        as_keys={"as-sign-1": stack.as_key.public_key()},
        identities=identities,
        permission_provider=provider,
        evidence_store=evidence,
    )
    catalog = build_catalog(exchange.TENANT, "task-001")
    quote = catalog._quotes[("quote-001", "1")]
    catalog._quotes[("quote-001", "1")] = replace(
        quote, lines=tuple(CatalogQuoteLine(sku, quantity, unit_price) for sku in skus)
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
        catalog=catalog,
        downstream=downstream,
        downstream_secret=DOWNSTREAM_SECRET,
    )
    return SignedEnv(
        stack.as_key,
        keys,
        registrations,
        leaf.access_token,
        verifier,
        evidence,
        service,
        VerifiedExecution(service, evidence_store=evidence),
        downstream,
    )


def full_state(dsn, downstream_dsn):
    """Every persistent business/proof/material family, with no partial counter oracle."""
    result = {}
    for label, target, prefix in (
        ("gateway", dsn, "ag_"),
        ("downstream", downstream_dsn, "ds_"),
    ):
        with psycopg.connect(target) as conn:
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


class CorruptRow:
    """Exact owned test row corruption, restoring all original bytes and triggers."""

    def __init__(self, dsn, table, where, values):
        self.dsn, self.table, self.where, self.values = dsn, table, where, values

    def _write(self, values):
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                psycopg.sql.SQL("ALTER TABLE {} DISABLE TRIGGER USER").format(
                    psycopg.sql.Identifier(self.table)
                )
            )
            assignments = psycopg.sql.SQL(",").join(
                psycopg.sql.SQL("{}=%s").format(psycopg.sql.Identifier(k)) for k in values
            )
            conditions = psycopg.sql.SQL(" AND ").join(
                psycopg.sql.SQL("{}=%s").format(psycopg.sql.Identifier(k)) for k in self.where
            )
            conn.execute(
                psycopg.sql.SQL("UPDATE {} SET {} WHERE {}").format(
                    psycopg.sql.Identifier(self.table), assignments, conditions
                ),
                (*values.values(), *self.where.values()),
            )
            conn.execute(
                psycopg.sql.SQL("ALTER TABLE {} ENABLE TRIGGER USER").format(
                    psycopg.sql.Identifier(self.table)
                )
            )

    def __enter__(self):
        with psycopg.connect(self.dsn) as conn:
            conditions = psycopg.sql.SQL(" AND ").join(
                psycopg.sql.SQL("{}=%s").format(psycopg.sql.Identifier(k)) for k in self.where
            )
            row = conn.execute(
                psycopg.sql.SQL("SELECT {} FROM {} WHERE {}").format(
                    psycopg.sql.SQL(",").join(psycopg.sql.Identifier(k) for k in self.values),
                    psycopg.sql.Identifier(self.table),
                    conditions,
                ),
                tuple(self.where.values()),
            ).fetchone()
            assert row is not None
            self.original = dict(zip(self.values, row, strict=True))
        self._write(self.values)
        return self

    def __exit__(self, *args):
        self._write(self.original)


def publication_only(before, after, *, _journal_checked=False):
    """Exactly three permitted fields differ; every other persisted fact is identical."""
    import copy
    import json

    a, b = copy.deepcopy(before), copy.deepcopy(after)
    if not _journal_checked:
        _journal_delta(a, b, publication=True)
    for state in (a, b):
        rows = state["gateway"]["ag_receipt_outbox"]
        cleaned = []
        for (raw,) in rows:
            value = json.loads(raw)
            for name in ("receipt_status", "receipt_jws", "signed_at"):
                value.pop(name)
            cleaned.append(value)
        state["gateway"]["ag_receipt_outbox"] = cleaned
    assert a == b


def staged_only(before, after, *, proof_jti, purpose="result-read"):
    import copy
    import json

    a, b = copy.deepcopy(before), copy.deepcopy(after)
    old = a["gateway"].pop("ag_verified_evidence")
    new = b["gateway"].pop("ag_verified_evidence")
    assert a == b
    added = [row for row in new if row not in old]
    assert len(added) == 1 and all(row in new for row in old)
    row = json.loads(added[0][0])
    assert row["purpose"] == purpose and row["proof_jti"] == proof_jti


def legal_shared_operations(dsn, downstream_dsn, *, failed=False, public=False):
    """Two actual AS roots with legal cross-tenant/client aliases of one holder key."""
    import time

    from agent_guard.authorization.proof import sign_ag_proof
    from agent_guard.contracts.encoding import canonical_json_bytes
    from agent_guard.contracts.ledger import INVOKE_ENDPOINT
    from agent_guard.crypto.sm import serialize_sm2_public_key
    from agent_guard.identity.resolver import RegisteredIdentity
    from tests.integration import test_verified_execution as original

    as_key, shared = generate_sm2_private_key(), generate_sm2_private_key()
    records = []
    downstream = MockDownstream(
        downstream_dsn,
        service_secret=DOWNSTREAM_SECRET,
        approved_suppliers=set() if failed else {"supplier-001"},
    )
    downstream.provision()
    downstream.reset()
    for label in ("A", "B"):
        tenant, client = "tenant-a23-" + label, "client-a23-" + label

        def identities(*, label=label, client=client, tenant=tenant):
            keys = {name: generate_sm2_private_key() for name in ("planner", "selector")}
            keys["executor"] = shared
            entries = {}
            for name, key in keys.items():
                did = (
                    "did:web:identity.agent-guard.test:shared-holder"
                    if name == "executor"
                    else "did:web:identity.agent-guard.test:agents:" + name + "-" + label
                )
                actual_client = client if name == "executor" else "agent-" + name
                entries[(tenant, actual_client)] = RegisteredIdentity(
                    tenant,
                    actual_client,
                    did,
                    did + "#key-1",
                    serialize_sm2_public_key(key.public_key()),
                )
            return keys, entries, exchange._resolver(entries)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(exchange, "TENANT", tenant)
            patch.setattr(exchange, "_identities", identities)
            patch.setattr(exchange, "generate_sm2_private_key", lambda: as_key)
            _, keys, registry, exchanges, root = exchange._root(
                dsn,
                approved_overrides={
                    "scope": "openid procurement.order.create",
                    "constraints": original.CONSTRAINTS,
                },
            )
            child = exchange._exchange(
                exchanges, keys, registry, exchange._form(as_key, root.access_token)
            )
            form = exchange._form(as_key, child.access_token, recipient="executor", ttl=100)
            form["ag_delegate_client_id"] = client
            leaf = exchange._exchange(exchanges, keys, registry, form, holder="selector")
        evidence = EvidenceStore(dsn)
        provider = PermissionSnapshotProvider(
            dsn,
            issuer=exchange.ISSUER,
            as_keys={"as-sign-1": as_key.public_key()},
            registrations={(r.tenant_id, r.client_id, r.kid): r for r in registry.values()},
        )
        iv = InvocationVerifier(
            issuer=exchange.ISSUER,
            as_keys={"as-sign-1": as_key.public_key()},
            identities=exchanges._identities,
            permission_provider=provider,
            evidence_store=evidence,
        )
        service = ExecutionService(
            gateway_dsn=dsn,
            ledger=ExecutionLedger(dsn),
            catalog=build_catalog(tenant, "task-001"),
            downstream=downstream,
            downstream_secret=DOWNSTREAM_SECRET,
        )
        body = {
            "profile": "GM-MVP-1",
            "task_id": "task-001",
            "tool_id": "procurement.order.create",
            "tool_version": "1",
            "idempotency_key": "shared-" + label,
            "params": {
                "request_id": "req-001",
                "quote_id": "quote-001",
                "quote_version": "1",
                "items": [{"sku": "sku-001", "quantity": 1}],
                "delivery_id": "office-001",
            },
        }
        registration = registry[(tenant, client)]
        proof = sign_ag_proof(
            shared,
            kid=registration.kid,
            client_id=client,
            purpose="invoke",
            endpoint=INVOKE_ENDPOINT,
            body=body,
            token=leaf.access_token,
            now=int(time.time()),
        )
        bundle = iv.verify_bundle(
            leaf.access_token,
            proof,
            body=canonical_json_bytes(body),
            now=int(time.time()),
        )
        adapter = VerifiedExecution(service, evidence_store=evidence)
        if public:
            from agent_guard.execution.query import AuthorizedQuery
            from agent_guard.gateway.endpoint import GatewayEndpoint
            from agent_guard.gateway.http_app import GatewayHttpApp
            from tests.fixtures.gateway import request

            application = GatewayHttpApp(
                GatewayEndpoint(
                    verifier=iv,
                    execution=adapter,
                    queries=AuthorizedQuery(dsn, evidence_store=evidence),
                )
            )
            status, response, _ = request(
                application,
                body=canonical_json_bytes(body),
                headers=[
                    (b"content-type", b"application/json"),
                    (b"authorization", b"AGPoP " + leaf.access_token.encode("ascii")),
                    (b"ag-proof", proof.encode("ascii")),
                ],
            )
            assert status == 202 and response["receipt_status"] == "PENDING"
            op = response["operation_id"]
        else:
            op = adapter.accept(bundle).operation_id
        assert service.run_operation(op).status == ("FAILED" if failed else "SUCCEEDED")
        records.append(
            dict(
                op=op,
                tenant=tenant,
                client=client,
                registration=registration,
                token=leaf.access_token,
                iv=iv,
                evidence=evidence,
                adapter=adapter,
                service=service,
                key=shared,
                registry=registry,
                as_key=as_key,
            )
        )
    combined = {
        (r.tenant_id, r.client_id, r.kid): r for item in records for r in item["registry"].values()
    }
    provider = PermissionSnapshotProvider(
        dsn,
        issuer=exchange.ISSUER,
        as_keys={"as-sign-1": as_key.public_key()},
        registrations=combined,
    )
    gateway = generate_sm2_private_key()
    verifier = ReceiptVerifier(
        issuer=exchange.ISSUER,
        as_keys={"as-sign-1": as_key.public_key()},
        gateway_keys={"gw-shared": gateway.public_key()},
        registrations=combined,
        permission_provider=provider,
    )
    publisher = InternalPublisher(
        dsn, private_key=gateway, signing_kid="gw-shared", verifier=verifier
    )
    return records, verifier, publisher


def accept_retry_only(
    before,
    after,
    *,
    evidence_ref,
    proof_jti,
    operation_id,
    publication=False,
    staging=False,
    observed_response=None,
):
    """One fresh invoke proof/link; exact original effects or three publication columns."""
    import copy
    import json

    old, new = copy.deepcopy(before), copy.deepcopy(after)
    _journal_delta(
        old,
        new,
        interactions=(("RETRY", operation_id, evidence_ref),),
        publication=publication,
        observed_response=observed_response,
    )
    for table, bindings in (
        (
            "ag_proofs",
            {"proof_jti": proof_jti, "purpose": "invoke", "operation_id": operation_id},
        ),
        (
            "ag_operation_evidence",
            {
                "evidence_ref": evidence_ref,
                "operation_id": operation_id,
                "kind": "retry",
            },
        ),
    ):
        original = old["gateway"].pop(table)
        current = new["gateway"].pop(table)
        added = [r for r in current if r not in original]
        assert len(added) == 1 and all(r in current for r in original)
        row = json.loads(added[0][0])
        assert all(row[k] == v for k, v in bindings.items())
    if staging:
        original = old["gateway"].pop("ag_verified_evidence")
        current = new["gateway"].pop("ag_verified_evidence")
        added = [r for r in current if r not in original]
        assert len(added) == 1 and all(r in current for r in original)
        row = json.loads(added[0][0])
        assert (
            row["evidence_ref"] == evidence_ref
            and row["proof_jti"] == proof_jti
            and row["purpose"] == "invoke"
            and row["state"] == "STAGED"
        )
    if publication:
        publication_only(old, new, _journal_checked=True)
    else:
        assert old == new


def result_read_only(
    before,
    after,
    *,
    evidence_ref,
    proof_jti,
    operation_id,
    staging=False,
    publication=False,
    observed_response=None,
):
    """One result-read proof, optional single STAGED material, all other rows stable."""
    import copy
    import json

    old, new = copy.deepcopy(before), copy.deepcopy(after)
    _journal_delta(
        old,
        new,
        interactions=(("QUERY", operation_id, evidence_ref),),
        publication=publication,
        observed_response=observed_response,
    )
    original = old["gateway"].pop("ag_proofs")
    current = new["gateway"].pop("ag_proofs")
    added = [r for r in current if r not in original]
    assert len(added) == 1 and all(r in current for r in original)
    row = json.loads(added[0][0])
    assert (
        row["proof_jti"] == proof_jti
        and row["operation_id"] == operation_id
        and row["purpose"] == "result-read"
        and row["evidence_ref"] == evidence_ref
    )
    if staging:
        staged_only(old, new, proof_jti=proof_jti)
    elif publication:
        publication_only(old, new, _journal_checked=True)
    else:
        assert old == new


def collect_futures(futures, *, timeout=10):
    """Drain every worker result, retaining all unexpected exceptions together."""
    from builtins import ExceptionGroup

    results, errors = [], []
    for future in futures:
        try:
            results.append(future.result(timeout))
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise ExceptionGroup("all owned race worker exceptions", errors)
    return results


# Frozen old inventory, retained exactly; new inventory is explicit, never ag_%.
OLD_GATEWAY_TABLES = frozenset(
    {
        "ag_auth_events",
        "ag_authorization_requests",
        "ag_login_sessions",
        "ag_login_csrf",
        "ag_task_policies",
        "ag_users",
        "ag_grant_revocations",
        "ag_tenant_admins",
        "ag_task_revocations",
        "ag_exchange_evidence",
        "ag_delegations",
        "ag_auth_evidence",
        "ag_grant_tokens",
        "ag_authorization_codes",
        "ag_proofs",
        "ag_ledger_event_nodes",
        "ag_ledger_events",
        "ag_operations",
        "ag_grants",
        "ag_tasks",
        "ag_principals",
        "ag_receipt_outbox",
        "ag_execution_leases",
        "ag_operation_review_flags",
        "ag_verified_evidence",
        "ag_operation_evidence",
        "ag_event_seals",
        "ag_schema_migrations",
        "ag_schema_migration_lineages",
        "ag_schema_legacy_binding",
        "ag_test_ownership",
    }
)
AUDIT_GATEWAY_TABLES = frozenset(
    {
        "ag_audit_streams",
        "ag_audit_records",
        "ag_audit_bootstrap",
        "ag_audit_bootstrap_chunks",
        "ag_audit_delivery",
        "ag_audit_delivery_batches",
    }
)


def _journal_delta(old, new, *, interactions=(), publication=False, observed_response=None):
    """Validate exact new records and normalize only their proven head advance.

    All other domains/rows remain present for the original full equality oracle.
    No audit table is removed or generally ignored.
    """
    import json
    from datetime import datetime

    from agent_guard.audit.contracts import (
        decode_journal_record,
        decode_material_projection,
        utc_text,
    )
    from agent_guard.contracts.encoding import (
        b64url_encode,
        canonical_json_bytes,
        load_strict_json,
    )
    from agent_guard.crypto.sm import sm3_b64url

    a, b = old["gateway"], new["gateway"]
    if "ag_audit_records" not in a:
        assert "ag_audit_records" not in b
        return

    def rows(state, table):
        return [json.loads(raw) for (raw,) in state[table]]

    def raw(value):
        assert type(value) is str and value.startswith("\\x")
        return bytes.fromhex(value[2:])

    def instant(value):
        return utc_text(datetime.fromisoformat(value.replace("Z", "+00:00")))

    operations = {r["operation_id"]: r for r in rows(b, "ag_operations")}
    evidence = {r["evidence_ref"]: r for r in rows(b, "ag_verified_evidence")}
    proofs = {r["evidence_ref"]: r for r in rows(b, "ag_proofs") if r["operation_id"] is not None}
    outboxes = {r["operation_id"]: r for r in rows(b, "ag_receipt_outbox")}
    oldout = {r["operation_id"]: r for r in rows(a, "ag_receipt_outbox")}
    expected = list(interactions)
    if publication:
        for op, out in outboxes.items():
            previous = oldout.get(op)
            assert previous is not None
            if previous["receipt_status"] == "PENDING" and out["receipt_status"] == "READY":
                expected.append(("PUBLISH", op, None))
            else:
                assert (
                    previous["receipt_status"],
                    previous["receipt_jws"],
                    previous["signed_at"],
                    previous.get("audit_ready_xid"),
                ) == (
                    out["receipt_status"],
                    out["receipt_jws"],
                    out["signed_at"],
                    out.get("audit_ready_xid"),
                )
    before = a["ag_audit_records"]
    after = b["ag_audit_records"]
    assert all(row in after for row in before)
    added = [row for row in after if row not in before]
    assert len(added) == len(expected)
    streams = {r["stream_id"]: r for r in rows(a, "ag_audit_streams")}
    newstreams = {r["stream_id"]: r for r in rows(b, "ag_audit_streams")}
    assert set(streams) == set(newstreams)
    bystream = {}
    for stored in added:
        row = json.loads(stored[0])
        record = decode_journal_record(raw(row["raw"]))
        for column in (
            "seq",
            "record_id",
            "kind",
            "operation_id",
            "evidence_ref",
            "previous_digest",
            "digest",
        ):
            assert row[column] == getattr(record, column)
        assert row["stream_id"] == record.scope.stream_id
        assert instant(row["recorded_at"]) == record.recorded_at
        matching = [
            x
            for x in expected
            if x[0] == record.kind
            and x[1] == record.operation_id
            and (x[2] is None or x[2] == record.evidence_ref)
        ]
        assert len(matching) == 1
        expected.remove(matching[0])
        assert row["digest"] == record.digest and row["previous_digest"] == record.previous_digest
        assert (
            row["seq"] == record.seq
            and row["record_id"] == record.record_id
            and row["kind"] == record.kind
        )
        assert (
            row["operation_id"] == record.operation_id
            and row["evidence_ref"] == record.evidence_ref
        )
        assert instant(row["recorded_at"]) == record.recorded_at
        stream = streams[record.scope.stream_id]
        assert (
            record.scope.gateway_id,
            record.scope.tenant_id,
            record.scope.task_id,
            record.scope.epoch,
        ) == (
            stream["gateway_id"],
            stream["tenant_id"],
            stream["task_id"],
            stream["epoch"],
        )
        op = operations[record.operation_id]
        out = outboxes.get(record.operation_id)
        assert (op["tenant_id"], op["task_id"]) == (
            record.scope.tenant_id,
            record.scope.task_id,
        )
        facts = load_strict_json(record.facts_bytes)
        material = decode_material_projection(record.kind, raw(row["material_binding_bytes"]))
        if record.kind == "PUBLISH":
            assert record.evidence_ref == op["evidence_ref"]
            assert facts == {
                "receipt_id": out["receipt_id"],
                "receipt_jws_digest": sm3_b64url(out["receipt_jws"].encode("ascii")),
                "signed_at": instant(out["signed_at"]),
            }
            assert material == {"jws": out["receipt_jws"]}
            witness = out["audit_ready_xid"]
        else:
            e = evidence[record.evidence_ref]
            proof = proofs[record.evidence_ref]
            assert proof["operation_id"] == record.operation_id
            assert proof["purpose"] == ("invoke" if record.kind == "RETRY" else "result-read")
            witness = proof["audit_linked_xid"]
            assert material == {
                "context": b64url_encode(raw(e["context_json"])),
                "source": b64url_encode(raw(e["chain_json"])),
            }
            for key, column in [
                ("token_digest", "token_sm3"),
                ("proof_digest", "proof_sm3"),
                ("body_digest", "body_sm3"),
            ]:
                assert facts[key] == e[column]
            assert facts["context_digest"] == sm3_b64url(raw(e["context_json"]))
            assert facts["source_material_digest"] == sm3_b64url(raw(e["chain_json"]))
            assert facts["source_digest"] == load_strict_json(raw(e["chain_json"]))["digest"]
            assert (
                facts["first_evidence_ref"] == op["evidence_ref"]
                and facts["status"] == op["status"]
            )
            receipt_status = out["receipt_status"] if out else "PENDING"
            receipt_jws = out["receipt_jws"] if out else None
            if (
                publication
                and observed_response is not None
                and oldout[record.operation_id]["receipt_status"] == "PENDING"
                and receipt_status == "READY"
            ):
                # Response is captured before append/head wait. The publisher
                # may commit between that read and the journal append.
                receipt_status = observed_response["receipt_status"]
                assert receipt_status in ("PENDING", "READY")
                receipt_jws = out["receipt_jws"] if receipt_status == "READY" else None
            assert facts["receipt_status"] == receipt_status
            assert facts["receipt_jws_digest"] == (
                sm3_b64url(receipt_jws.encode("ascii")) if receipt_jws is not None else None
            )
            if record.kind == "RETRY":
                assert facts["intent_digest"] == op["intent_digest"]
                if facts["response_kind"] == "ACCEPT_RESPONSE":
                    response = {
                        "operation_id": op["operation_id"],
                        "status": op["status"],
                        "receipt_status": facts["receipt_status"],
                    }
                else:
                    assert facts["response_kind"] == "ACCEPT_RESULT"
                    response = {
                        "operation_id": op["operation_id"],
                        "grant_id": op["grant_id"],
                        "root_id": load_strict_json(raw(e["context_json"]))["root_id"],
                        "status": op["status"],
                        "disposition": "EXISTING",
                        "accepted_at": instant(op["accepted_at"]),
                        "cost": {
                            key: op[key]
                            for key in (
                                "amount_fen",
                                "calls",
                                "currency",
                                "quote_id",
                                "quote_version",
                            )
                        },
                    }
                    response["cost"]["quote_snapshot"] = (
                        None
                        if op["quote_snapshot"] is None
                        else b64url_encode(raw(op["quote_snapshot"]))
                    )
                linked = next(
                    r
                    for r in rows(b, "ag_operation_evidence")
                    if r["evidence_ref"] == record.evidence_ref
                )
                assert linked["kind"] == "retry" and linked["audit_linked_xid"] == witness
            else:
                assert record.kind == "QUERY"
                result = load_strict_json(raw(out["result_bytes"])) if out else None
                response = {
                    "operation_id": op["operation_id"],
                    "status": op["status"],
                    "receipt_status": facts["receipt_status"],
                    "result": result,
                    "receipt_jws": receipt_jws,
                }
                assert facts["result_digest"] == (
                    sm3_b64url(canonical_json_bytes(result)) if result is not None else None
                )
            if (
                record.kind == "RETRY"
                and facts["response_kind"] == "ACCEPT_RESULT"
                and op["quote_snapshot"] is not None
            ):
                from copy import deepcopy

                import rfc8785

                quote_raw = raw(op["quote_snapshot"])
                assert type(quote_raw) is bytes and len(quote_raw) <= 65536
                complete = rfc8785.dumps(response)
                metadata = deepcopy(response)
                metadata["cost"]["quote_snapshot"] = None
                metadata_bytes = canonical_json_bytes(metadata)
                assert len(complete) == len(metadata_bytes) - 2 + len(b64url_encode(quote_raw))
                assert len(complete) <= 152916
            else:
                complete = canonical_json_bytes(response)
            assert facts["response_digest"] == sm3_b64url(complete)
            if observed_response is not None:
                assert len(interactions) == 1 and type(observed_response) is dict
                assert observed_response == response
        assert row["created_xid"] == witness
        bystream.setdefault(record.scope.stream_id, []).append(record)
    assert not expected
    for stream_id, records in bystream.items():
        original = streams[stream_id]
        current = newstreams[stream_id]
        prior_seq, prior_digest = original["head_seq"], original["head_digest"]
        for record in sorted(records, key=lambda r: r.seq):
            assert record.seq == prior_seq + 1 and record.previous_digest == prior_digest
            prior_seq, prior_digest = record.seq, record.digest
        assert (current["head_seq"], current["head_digest"]) == (
            prior_seq,
            prior_digest,
        )
        current["head_seq"], current["head_digest"] = (
            original["head_seq"],
            original["head_digest"],
        )
    assert streams == newstreams
    b["ag_audit_records"] = list(before)
    b["ag_audit_streams"] = list(a["ag_audit_streams"])
    if publication:
        cleaned = []
        for out in rows(b, "ag_receipt_outbox"):
            prior = oldout[out["operation_id"]]
            if "audit_ready_xid" in out:
                out["audit_ready_xid"] = prior["audit_ready_xid"]
            cleaned.append((json.dumps(out, separators=(",", ":")),))
        # Preserve the same row_to_json spelling for subsequent original oracle.
        for out in rows(b, "ag_receipt_outbox"):
            if "audit_ready_xid" in out:
                out["audit_ready_xid"] = oldout[out["operation_id"]]["audit_ready_xid"]
        b["ag_receipt_outbox"] = cleaned


def accept_created_only(before, after, *, bundle, result):
    """Exact second CREATED effect in an existing stream, retaining every old domain."""
    import json
    from copy import deepcopy
    from datetime import datetime

    from agent_guard.audit.contracts import (
        decode_journal_record,
        decode_material_projection,
        utc_text,
    )
    from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes, load_strict_json
    from agent_guard.crypto.sm import sm3_b64url

    old, new = deepcopy(before), deepcopy(after)
    a, b = old["gateway"], new["gateway"]

    def rows(table):
        return [json.loads(item[0]) for item in b[table]]

    def raw(value):
        assert type(value) is str and value.startswith("\\x")
        return bytes.fromhex(value[2:])

    def delta(table, expected):
        original, current = a[table], b[table]
        assert all(item in current for item in original)
        added = [json.loads(item[0]) for item in current if item not in original]
        assert len(added) == expected
        b[table] = list(original)
        return added

    invocation = bundle.invocation
    path = list(bundle.source.snapshot.chain_grant_ids)
    (operation,) = delta("ag_operations", 1)
    assert operation["operation_id"] == result.operation_id
    assert operation["status"] == result.status == "RESERVED"
    assert result.disposition.value == "CREATED"
    for key in (
        "tenant_id",
        "task_id",
        "grant_id",
        "holder_client_id",
        "holder_kid",
        "tool_id",
        "tool_version",
        "idempotency_key",
        "intent_digest",
        "token_digest",
        "proof_digest",
        "evidence_ref",
    ):
        assert operation[key] == getattr(invocation, key)
    assert raw(operation["canonical_params"]) == invocation.canonical_params
    assert operation["amount_fen"] == result.cost.amount_fen
    assert operation["calls"] == result.cost.calls == 1 and operation["currency"] == "CNY"
    assert (
        operation["quote_id"] == result.cost.quote_id
        and operation["quote_version"] == result.cost.quote_version
    )
    assert (
        None if operation["quote_snapshot"] is None else raw(operation["quote_snapshot"])
    ) == result.cost.quote_snapshot
    assert utc_text(datetime.fromisoformat(operation["accepted_at"])) == utc_text(
        result.accepted_at
    )
    witness = operation["audit_created_xid"]
    assert witness.isdigit() and operation["audit_terminal_xid"] is None
    (proof,) = delta("ag_proofs", 1)
    assert (proof["holder_kid"], proof["endpoint"], proof["proof_digest"]) == (
        invocation.holder_kid,
        invocation.endpoint,
        invocation.proof_digest,
    )
    assert (
        proof["operation_id"],
        proof["evidence_ref"],
        proof["purpose"],
        proof["proof_jti"],
        proof["audit_linked_xid"],
    ) == (
        result.operation_id,
        bundle.evidence_ref,
        "invoke",
        invocation.proof_jti,
        witness,
    )
    (link,) = delta("ag_operation_evidence", 1)
    assert (
        link["operation_id"],
        link["evidence_ref"],
        link["kind"],
        link["audit_linked_xid"],
    ) == (result.operation_id, bundle.evidence_ref, "first", witness)
    evidence = next(
        row for row in rows("ag_verified_evidence") if row["evidence_ref"] == bundle.evidence_ref
    )
    if b["ag_verified_evidence"] != a["ag_verified_evidence"]:
        (staged,) = delta("ag_verified_evidence", 1)
        assert (
            staged == evidence
            and staged["state"] == "STAGED"
            and staged["proof_jti"] == invocation.proof_jti
        )
    (event,) = delta("ag_ledger_events", 1)
    assert (event["operation_id"], event["phase"], event["seq"]) == (
        result.operation_id,
        "RESERVE",
        0,
    )
    nodes = sorted(delta("ag_ledger_event_nodes", len(path)), key=lambda node: node["position"])
    projection = []
    for i, (grant, node) in enumerate(zip(path, nodes, strict=True)):
        assert (node["event_id"], node["position"], node["grant_id"]) == (
            event["event_id"],
            i,
            grant,
        )
        amounts = [
            node[key]
            for key in (
                "amount_reserved_delta",
                "amount_settled_delta",
                "calls_reserved_delta",
                "calls_settled_delta",
            )
        ]
        assert amounts == [result.cost.amount_fen, 0, 1, 0]
        projection.append([i, grant, *amounts])
    (seal,) = delta("ag_event_seals", 1)
    assert seal == {"event_id": event["event_id"], "created_xid": witness}
    grants = rows("ag_grants")
    assert len(grants) == len(a["ag_grants"])
    for grant in grants:
        if grant["grant_id"] in path:
            grant["amount_reserved"] -= result.cost.amount_fen
            grant["calls_reserved"] -= 1
    b["ag_grants"] = sorted((json.dumps(grant, separators=(",", ":")),) for grant in grants)
    a["ag_grants"] = sorted(
        (json.dumps(json.loads(item[0]), separators=(",", ":")),) for item in a["ag_grants"]
    )
    (stored,) = delta("ag_audit_records", 1)
    record = decode_journal_record(raw(stored["raw"]))
    for column in (
        "seq",
        "record_id",
        "kind",
        "operation_id",
        "evidence_ref",
        "previous_digest",
        "digest",
    ):
        assert stored[column] == getattr(record, column)
    assert stored["stream_id"] == record.scope.stream_id
    assert utc_text(datetime.fromisoformat(stored["recorded_at"])) == record.recorded_at
    assert (
        record.kind == "FIRST"
        and record.operation_id == result.operation_id
        and record.evidence_ref == bundle.evidence_ref
    )
    assert stored["digest"] == record.digest and stored["created_xid"] == witness
    facts = load_strict_json(record.facts_bytes)
    expected_facts = {
        "root_grant_id": invocation.root_id,
        "grant_id": invocation.grant_id,
        "path_ids": path,
        "intent_digest": invocation.intent_digest,
        "token_digest": evidence["token_sm3"],
        "proof_digest": evidence["proof_sm3"],
        "body_digest": evidence["body_sm3"],
        "context_digest": sm3_b64url(raw(evidence["context_json"])),
        "source_digest": bundle.source.digest,
        "source_material_digest": sm3_b64url(raw(evidence["chain_json"])),
        "reserve_digest": sm3_b64url(canonical_json_bytes(projection)),
        "quote_digest": None
        if result.cost.quote_snapshot is None
        else sm3_b64url(result.cost.quote_snapshot),
        "amount_fen": result.cost.amount_fen,
        "calls": 1,
        "currency": "CNY",
        "introduced_grants": [],
    }
    assert facts == expected_facts
    assert decode_material_projection("FIRST", raw(stored["material_binding_bytes"])) == {
        "context": b64url_encode(raw(evidence["context_json"])),
        "source": b64url_encode(raw(evidence["chain_json"])),
        "quote": None
        if result.cost.quote_snapshot is None
        else b64url_encode(result.cost.quote_snapshot),
    }
    streams = rows("ag_audit_streams")
    previous = next(
        json.loads(item[0])
        for item in a["ag_audit_streams"]
        if json.loads(item[0])["stream_id"] == record.scope.stream_id
    )
    current = next(item for item in streams if item["stream_id"] == record.scope.stream_id)
    assert (
        record.seq == previous["head_seq"] + 1 and record.previous_digest == previous["head_digest"]
    )
    assert (
        current["gateway_id"],
        current["tenant_id"],
        current["task_id"],
        current["stream_id"],
        current["epoch"],
    ) == (
        record.scope.gateway_id,
        record.scope.tenant_id,
        record.scope.task_id,
        record.scope.stream_id,
        record.scope.epoch,
    )
    assert (current["head_seq"], current["head_digest"]) == (record.seq, record.digest)
    current["head_seq"], current["head_digest"] = (
        previous["head_seq"],
        previous["head_digest"],
    )
    b["ag_audit_streams"] = sorted((json.dumps(item, separators=(",", ":")),) for item in streams)
    a["ag_audit_streams"] = sorted(
        (json.dumps(json.loads(item[0]), separators=(",", ":")),) for item in a["ag_audit_streams"]
    )
    assert old == new


def _initial_rows(state, table):
    import json

    return [json.loads(item[0]) for item in state["gateway"][table]]


def _initial_raw(value):
    assert value.startswith("\\x")
    return bytes.fromhex(value[2:])


def accept_initial_only(before, after, *, seed, bundle, result):
    import copy
    import json

    from agent_guard.audit.contracts import (
        EmptyTaskBootstrapSeed,
        JournalScope,
        decode_journal_record,
        decode_material_projection,
        genesis_digest,
        utc_text,
    )
    from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes, load_strict_json
    from agent_guard.crypto.sm import sm3_b64url

    assert not _initial_rows(before, "ag_audit_streams") and not _initial_rows(
        before, "ag_audit_records"
    )
    assert type(seed) is EmptyTaskBootstrapSeed and seed.origin == "FROM_EMPTY_TASK"
    from urllib.parse import urlsplit

    from agent_guard.contracts.ledger import INVOKE_ENDPOINT

    endpoint = urlsplit(INVOKE_ENDPOINT)
    assert seed.scope_key[0] == endpoint.scheme + "://" + endpoint.netloc
    invocation = bundle.invocation
    assert seed.scope_key[1:] == (invocation.tenant_id, invocation.task_id)
    assert seed.root_grant_id == invocation.root_id == bundle.source.snapshot.chain_grant_ids[0]
    assert seed.object_count == len(seed.objects) and seed.chunk_count == len(seed.chunks)
    metadata = [
        load_strict_json(o.raw)
        for o in seed.objects
        if o.kind == "typed_snapshot_metadata" and o.object_id.split(":")[-1].isdigit()
    ]
    grants = [m["columns"] for m in metadata if m["table"] == "ag_grants"]
    assert {g["grant_id"] for g in grants} == {
        g["grant_id"]
        for g in _initial_rows(before, "ag_grants")
        if (g["tenant_id"], g["task_id"]) == seed.scope_key[1:]
    }
    assert not any(
        m["table"]
        in ("ag_operations", "ag_ledger_events", "ag_ledger_event_nodes", "ag_event_seals")
        for m in metadata
    )
    assert all(
        g[k] == 0
        for g in grants
        for k in ("amount_reserved", "amount_settled", "calls_reserved", "calls_settled")
    )
    # Independent reverse projection: every required pre-transaction SQL row
    # and every original bytea value must appear exactly once, without staging.
    import re
    from collections import Counter
    from datetime import datetime

    original_tables = {table: _initial_rows(before, table) for table in before["gateway"]}
    task_grants = {
        row["grant_id"]
        for row in original_tables["ag_grants"]
        if (row["tenant_id"], row["task_id"]) == seed.scope_key[1:]
    }
    task_ops = {
        row["operation_id"]
        for row in original_tables["ag_operations"]
        if (row["tenant_id"], row["task_id"]) == seed.scope_key[1:]
    }
    assert not task_ops
    requests = {
        row["request_id"]
        for row in original_tables["ag_authorization_requests"]
        if (row["tenant_id"], row["task_id"]) == seed.scope_key[1:]
    }
    sessions = {
        row["session_sha256"]
        for row in original_tables["ag_authorization_requests"]
        if row["request_id"] in requests
    }
    codes = {
        row["code_sha256"]
        for row in original_tables["ag_authorization_codes"]
        if (row["tenant_id"], row["task_id"]) == seed.scope_key[1:]
    }
    principals = {
        (row["tenant_id"], row["holder_client_id"], row["holder_kid"])
        for row in original_tables["ag_grants"]
        if row["grant_id"] in task_grants
    }
    events = {
        row["event_id"]
        for row in original_tables["ag_ledger_events"]
        if row["operation_id"] in task_ops
    }

    def selected(table, row):
        if table.startswith(("ag_audit_", "ag_schema_")) or table == "ag_test_ownership":
            return False
        if "tenant_id" in row and "task_id" in row:
            return (row["tenant_id"], row["task_id"]) == seed.scope_key[1:]
        if "operation_id" in row:
            return row["operation_id"] in task_ops
        if "grant_id" in row:
            return row["grant_id"] in task_grants
        if table == "ag_auth_evidence":
            return row["code_sha256"] in codes
        if table == "ag_exchange_evidence":
            return row["parent_grant_id"] in task_grants
        if table == "ag_auth_events":
            return row["request_id"] in requests
        if table == "ag_login_sessions":
            return row["session_sha256"] in sessions
        if table == "ag_principals":
            return (row["tenant_id"], row["client_id"], row["kid"]) in principals
        if table in ("ag_ledger_event_nodes", "ag_event_seals"):
            return row["event_id"] in events
        return False

    expected_rows = {
        table: [
            row
            for row in rows
            if selected(table, row) and table not in ("ag_proofs", "ag_verified_evidence")
        ]
        for table, rows in original_tables.items()
    }
    expected_rows = {table: rows for table, rows in expected_rows.items() if rows}
    assert set(m["table"] for m in metadata) == set(expected_rows), (
        "complete task metadata table coverage"
    )
    raw_objects = {
        (o.kind, o.object_id): o
        for o in seed.objects
        if o.kind != "typed_snapshot_metadata" or not o.object_id.split(":")[-1].isdigit()
    }
    assert len(raw_objects) == len(seed.objects) - len(metadata)
    consumed = set()

    def scalar(value):
        if type(value) is str and re.fullmatch(r"\d{4}-\d\d-\d\dT.*[+-]\d\d:\d\d", value):
            return utc_text(datetime.fromisoformat(value))
        return value

    for table, rows in expected_rows.items():
        entries = [m for m in metadata if m["table"] == table]
        assert sorted(m["row_index"] for m in entries) == list(range(len(rows)))
        reconstructed = []
        for m in entries:
            assert set(m) == {"table", "row_index", "columns"}
            recovered = {}
            for name, value in m["columns"].items():
                if type(value) is dict and set(value) == {"kind", "object_id", "digest"}:
                    assert value["object_id"] == table + ":" + str(m["row_index"]) + ":" + name
                    key = (value["kind"], value["object_id"])
                    assert key not in consumed
                    assert key in raw_objects, "referenced raw object exists"
                    obj = raw_objects[key]
                    assert obj.digest == value["digest"] == sm3_b64url(obj.raw)
                    signed_fields = {
                        ("ag_grant_tokens", "token_jws"): "token",
                        ("ag_auth_evidence", "proof_jws"): "proof",
                        ("ag_exchange_evidence", "proof_jws"): "proof",
                        ("ag_receipt_outbox", "receipt_jws"): "receipt",
                    }
                    if (table, name) in signed_fields:
                        assert (
                            value["kind"] == signed_fields[(table, name)] and len(obj.raw) <= 16384
                        )
                        recovered[name] = obj.raw.decode("ascii")
                    else:
                        recovered[name] = "\\x" + obj.raw.hex()
                    consumed.add(key)
                elif type(value) is dict and value == {"empty_bytes": True}:
                    recovered[name] = "\\x"
                elif type(value) is dict and set(value) == {"signed_integer_text"}:
                    recovered[name] = int(value["signed_integer_text"])
                else:
                    recovered[name] = scalar(value)
            reconstructed.append(recovered)
        expected = [{name: scalar(value) for name, value in row.items()} for row in rows]
        assert Counter(canonical_json_bytes(row) for row in reconstructed) == Counter(
            canonical_json_bytes(row) for row in expected
        )
    assert consumed == set(raw_objects)
    index = sm3_b64url(
        canonical_json_bytes({"profile": "AG-BOOTSTRAP-INDEX-1", "scope": list(seed.scope_key)})
    )
    wire = 0
    chunkmap = {}
    for obj in seed.objects:
        assert sm3_b64url(obj.raw) == obj.digest
        expected = tuple(
            c for c in seed.chunks if (c.kind, c.object_id) == (obj.kind, obj.object_id)
        )
        assert len(expected) == (len(obj.raw) + 24575) // 24576
        assert b"".join(c.raw for c in expected) == obj.raw
        index = sm3_b64url(
            canonical_json_bytes(
                {
                    "profile": "AG-BOOTSTRAP-INDEX-1",
                    "previous": index,
                    "kind": obj.kind,
                    "id": obj.object_id,
                    "total_raw_bytes": len(obj.raw),
                    "object_digest": obj.digest,
                    "chunk_count": len(expected),
                }
            )
        )
        for i, c in enumerate(expected):
            assert (
                c.index == i
                and c.count == len(expected)
                and c.total_raw_bytes == len(obj.raw)
                and c.object_digest == obj.digest
            )
            chunkmap[(c.kind, c.object_id, i)] = c
            wire += (
                len(
                    canonical_json_bytes(
                        {
                            "frame_type": "OBJECT_CHUNK",
                            "object_kind": c.kind,
                            "object_id": c.object_id,
                            "chunk_index": i,
                            "chunk_count": c.count,
                            "total_raw_bytes": c.total_raw_bytes,
                            "object_digest": c.object_digest,
                            "data": b64url_encode(c.raw),
                        }
                    )
                )
                + 1
            )
    assert seed.index_root == index and seed.wire_bytes == wire
    (stream,) = _initial_rows(after, "ag_audit_streams")
    (base,) = _initial_rows(after, "ag_audit_bootstrap")
    (delivery,) = _initial_rows(after, "ag_audit_delivery")
    expected_scope = JournalScope(*seed.scope_key, stream["stream_id"], 1)
    assert (stream["gateway_id"], stream["tenant_id"], stream["task_id"], stream["epoch"]) == (
        *seed.scope_key,
        1,
    )
    assert stream["genesis_digest"] == genesis_digest(expected_scope)
    assert set(stream) == {
        "stream_id",
        "gateway_id",
        "tenant_id",
        "task_id",
        "epoch",
        "genesis_digest",
        "bootstrap_digest",
        "enabled_at",
        "created_xid",
        "head_seq",
        "head_digest",
    }
    assert set(base) == {
        "stream_id",
        "boundary",
        "snapshot_as_of",
        "root_grant_id",
        "index_root",
        "manifest_digest",
        "manifest_bytes",
        "schema_lineage_bytes",
        "object_count",
        "chunk_count",
        "wire_bytes",
        "created_xid",
    }
    assert base["stream_id"] == stream["stream_id"]
    expected_manifest = canonical_json_bytes(
        dict(
            profile="AG-BOOTSTRAP-1",
            scope=list(seed.scope_key),
            root_grant_id=invocation.root_id,
            snapshot_as_of=seed.captured_at,
            origin="FROM_EMPTY_TASK",
            object_count=len(seed.objects),
            chunk_count=len(seed.chunks),
            wire_bytes=wire,
            index_root=index,
            schema_lineage_digest=sm3_b64url(
                canonical_json_bytes([list(row) for row in seed.schema_lineage])
            ),
        )
    )
    assert seed.manifest_bytes == expected_manifest
    lineage = sorted(
        (row["namespace"], row["version"], row["checksum"])
        for row in _initial_rows(before, "ag_schema_migration_lineages")
    )
    assert list(seed.schema_lineage) == lineage
    assert stream["created_xid"] == base["created_xid"] == seed.tx_id
    assert base["boundary"] == "NEW_EMPTY" and base["root_grant_id"] == seed.root_grant_id
    assert (
        _initial_raw(base["manifest_bytes"]) == seed.manifest_bytes
        and base["manifest_digest"] == sm3_b64url(seed.manifest_bytes) == stream["bootstrap_digest"]
    )
    assert (
        base["index_root"] == index
        and base["object_count"] == seed.object_count
        and base["chunk_count"] == len(chunkmap)
        and base["wire_bytes"] == wire
    )
    assert _initial_raw(base["schema_lineage_bytes"]) == canonical_json_bytes(
        [list(item) for item in seed.schema_lineage]
    )

    assert utc_text(datetime.fromisoformat(base["snapshot_as_of"])) == seed.captured_at
    chunks = _initial_rows(after, "ag_audit_bootstrap_chunks")
    assert len(chunks) == len(chunkmap)
    for stored in chunks:
        c = chunkmap.pop((stored["object_kind"], stored["object_id"], stored["chunk_index"]))
        assert stored == dict(
            stream_id=stream["stream_id"],
            object_kind=c.kind,
            object_id=c.object_id,
            chunk_index=c.index,
            chunk_count=c.count,
            total_raw_bytes=c.total_raw_bytes,
            object_digest=c.object_digest,
            raw="\\x" + c.raw.hex(),
            created_xid=seed.tx_id,
        )
    assert not chunkmap and not _initial_rows(after, "ag_audit_delivery_batches")
    records = _initial_rows(after, "ag_audit_records")
    assert len(records) == 2
    bootstraps = [r for r in records if r["kind"] == "BOOTSTRAP"]
    assert len(bootstraps) == 1
    bootstrap = bootstraps[0]
    record = decode_journal_record(_initial_raw(bootstrap["raw"]))
    assert record.scope == expected_scope and record.kind == "BOOTSTRAP"
    assert set(bootstrap) == {
        "stream_id",
        "seq",
        "record_id",
        "kind",
        "operation_id",
        "evidence_ref",
        "previous_digest",
        "digest",
        "raw",
        "material_binding_bytes",
        "recorded_at",
        "created_xid",
    }
    for column in (
        "seq",
        "record_id",
        "kind",
        "operation_id",
        "evidence_ref",
        "previous_digest",
        "digest",
    ):
        assert bootstrap[column] == getattr(record, column)
    assert bootstrap["stream_id"] == record.scope.stream_id
    assert bootstrap["raw"] == "\\x" + record.raw.hex()
    assert utc_text(datetime.fromisoformat(bootstrap["recorded_at"])) == record.recorded_at
    assert (
        seed.captured_at
        <= utc_text(datetime.fromisoformat(stream["enabled_at"]))
        <= record.recorded_at
    )
    assert (
        record.seq == 1
        and record.previous_digest == stream["genesis_digest"]
        and record.operation_id is None
        and record.evidence_ref is None
    )
    assert (
        bootstrap["created_xid"] == seed.tx_id
        and bootstrap["digest"] == record.digest
        and decode_material_projection(
            "BOOTSTRAP", _initial_raw(bootstrap["material_binding_bytes"])
        )
        == {}
    )
    assert load_strict_json(record.facts_bytes) == dict(
        boundary="NEW_EMPTY",
        root_grant_id=seed.root_grant_id,
        snapshot_as_of=seed.captured_at,
        schema_lineage_digest=sm3_b64url(_initial_raw(base["schema_lineage_bytes"])),
        index_root=index,
        manifest_digest=base["manifest_digest"],
        object_count=seed.object_count,
        chunk_count=seed.chunk_count,
        wire_bytes=wire,
    )
    assert delivery == dict(
        stream_id=stream["stream_id"],
        ack_sequence=0,
        ack_head_digest=stream["genesis_digest"],
        ack_checkpoint_digest=None,
        pending_batch_id=None,
        registration_state="REGISTRATION_REQUIRED",
    )
    virtual = copy.deepcopy(before)
    for table in ("ag_audit_bootstrap", "ag_audit_bootstrap_chunks", "ag_audit_delivery"):
        assert not _initial_rows(before, table)
        virtual["gateway"][table] = copy.deepcopy(after["gateway"][table])
    stream = copy.deepcopy(stream)
    stream["head_seq"] = 1
    stream["head_digest"] = record.digest
    virtual["gateway"]["ag_audit_streams"] = [(json.dumps(stream, separators=(",", ":")),)]
    virtual["gateway"]["ag_audit_records"] = [(json.dumps(bootstrap, separators=(",", ":")),)]
    accept_created_only(virtual, after, bundle=bundle, result=result)


def accept_introduced_only(before, after, *, bundle, result, introduced_grants):
    """Prove introduced facts, then reuse the unchanged complete CREATED oracle."""
    import copy
    import json

    from agent_guard.audit.contracts import decode_journal_record
    from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
    from agent_guard.crypto.sm import sm3_b64url

    assert type(introduced_grants) is tuple and all(
        type(item) is bytes for item in introduced_grants
    )
    expected = [load_strict_json(item) for item in introduced_grants]
    assert all(
        canonical_json_bytes(value) == item
        for value, item in zip(expected, introduced_grants, strict=True)
    )
    virtual = copy.deepcopy(after)
    matches = []
    for index, (encoded,) in enumerate(virtual["gateway"]["ag_audit_records"]):
        stored = json.loads(encoded)
        if stored["kind"] == "FIRST" and stored["operation_id"] == result.operation_id:
            matches.append((index, stored))
    assert len(matches) == 1
    index, stored = matches[0]
    record = decode_journal_record(_initial_raw(stored["raw"]))
    assert stored["digest"] == record.digest
    payload = load_strict_json(record.raw)
    assert payload["facts"]["introduced_grants"] == expected
    # Normalize only these independently proven facts and the resulting hashes.
    # No row/domain disappears; all remaining fields are checked by the full oracle.
    payload["facts"]["introduced_grants"] = []
    normalized = canonical_json_bytes(payload)
    normalized_digest = sm3_b64url(normalized)
    stored["raw"] = "\\x" + normalized.hex()
    stored["digest"] = normalized_digest
    virtual["gateway"]["ag_audit_records"][index] = (json.dumps(stored, separators=(",", ":")),)
    heads = 0
    for index, (encoded,) in enumerate(virtual["gateway"]["ag_audit_streams"]):
        head = json.loads(encoded)
        if head["stream_id"] == record.scope.stream_id:
            assert head["head_seq"] == record.seq and head["head_digest"] == record.digest
            head["head_digest"] = normalized_digest
            heads += 1
            virtual["gateway"]["ag_audit_streams"][index] = (
                json.dumps(head, separators=(",", ":")),
            )
    assert heads == 1
    accept_created_only(before, virtual, bundle=bundle, result=result)
