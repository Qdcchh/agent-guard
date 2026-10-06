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


def publication_only(before, after):
    """Exactly three permitted fields differ; every other persisted fact is identical."""
    import copy
    import json

    a, b = copy.deepcopy(before), copy.deepcopy(after)
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
    before, after, *, evidence_ref, proof_jti, operation_id, publication=False, staging=False
):
    """One fresh invoke proof/link; exact original effects or three publication columns."""
    import copy
    import json

    old, new = copy.deepcopy(before), copy.deepcopy(after)
    for table, bindings in (
        ("ag_proofs", {"proof_jti": proof_jti, "purpose": "invoke", "operation_id": operation_id}),
        (
            "ag_operation_evidence",
            {"evidence_ref": evidence_ref, "operation_id": operation_id, "kind": "retry"},
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
        publication_only(old, new)
    else:
        assert old == new


def result_read_only(
    before, after, *, evidence_ref, proof_jti, operation_id, staging=False, publication=False
):
    """One result-read proof, optional single STAGED material, all other rows stable."""
    import copy
    import json

    old, new = copy.deepcopy(before), copy.deepcopy(after)
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
        publication_only(old, new)
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
