"""Complete synthetic A31 original-material model with genuine SM2 signatures.

No claim of native PostgreSQL execution. Ephemeral test signing keys never
enter the public files or the independent offline validation process.
"""

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

import rfc8785

from agent_guard.audit.checkpoint import sign_checkpoint
from agent_guard.audit.contracts import JournalScope, genesis_digest, scope_object
from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.contracts.encoding import (
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.contracts.ledger_changes import canonical_ledger_changes_bytes
from agent_guard.crypto.sm import (
    generate_sm2_private_key,
    serialize_sm2_public_key,
    sign_compact_jws,
    sm3_b64url,
)
from agent_guard.evidence.task_bundle import encode_object_chunks, object_id
from tests.fixtures.a32_common import encode_task, signed_receipt_material, task_header
from tests.test_authorization import ISSUER, NOW

TOOLS = (
    "procurement.request.read",
    "procurement.document.read",
    "procurement.order.create",
    "notification.template.send",
)


def stamp(seconds=0):
    return datetime.fromtimestamp(NOW + seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def material(
    *,
    mode="LATEST_OBSERVATION",
    terminal=True,
    publish=True,
    baseline=0,
    tool="procurement.order.create",
    with_history=True,
    failed=False,
    rotate_audit=False,
    middle_checkpoint=False,
    repeat_retry=False,
    changed_accepted_at=False,
    accept_response=False,
    bootstrap_claim_overrides=None,
):
    template = signed_receipt_material()
    scope = JournalScope(
        "https://gateway.agent-guard.test", "tenant-001", "task-001", str(uuid4()), 1
    )
    as_key, gateway, audit = [generate_sm2_private_key() for _ in range(3)]
    holder_keys = [generate_sm2_private_key() for _ in range(3)]
    claims = deepcopy(list(template["path_claims"]))
    registrations, actor, tokens = [], None, []
    for i, (claim, key) in enumerate(zip(claims, holder_keys, strict=True)):
        did = f"did:web:identity.agent-guard.test:agents:holder-{i}"
        kid = did + "#key-1"
        spki = serialize_sm2_public_key(key.public_key())
        actor = {"sub": did, **({"act": actor} if actor else {})}
        claim.update(
            act=actor,
            scope=" ".join(TOOLS),
            ag_cnf={"kid": kid, "spki_sm3": sm3_b64url(spki)},
        )
        claim["ag_constraints"].update(template_ids=["order-created"], recipient_ids=["user-001"])
        registrations.append(
            {
                "tenant_id": "tenant-001",
                "client_id": claim["client_id"],
                "did": did,
                "kid": kid,
                "spki_der": b64url_encode(spki),
                "active": True,
                "role": "HOLDER",
            }
        )
        tokens.append(
            sign_compact_jws(as_key, claim, key_id="as-sign-1", token_type="ag-at+jwt").encode(
                "ascii"
            )
        )
    leaf, ids = claims[-1], [c["ag_grant_id"] for c in claims]
    op, first_ref = "operation-001", "ev-first"
    params = {
        "procurement.request.read": {"request_id": "req-001"},
        "procurement.document.read": {
            "document_id": "doc-001",
            "request_id": "req-001",
        },
        "procurement.order.create": template["v1_bundle"]["request"]["params"],
        "notification.template.send": {
            "template_id": "order-created",
            "recipient_id": "user-001",
            "operation_id": "prerequisite-001",
        },
    }[tool]
    request = {
        "profile": "GM-MVP-1",
        "task_id": "task-001",
        "tool_id": tool,
        "tool_version": "1",
        "idempotency_key": "purchase-001",
        "params": params,
    }
    raw_request = b" " + canonical_json_bytes(request) + b"\n"
    amount = 70000 if tool == "procurement.order.create" else 0
    quote_raw = template["components"].quote_raw if amount else None
    status = "FAILED" if failed else "SUCCEEDED"
    result = (
        {"kind": "refusal", "operation_id": op, "tool_id": tool, "reason": "DECLINED"}
        if failed
        else load_strict_json(template["components"].result_raw)
        if amount
        else {
            "kind": "notification",
            "operation_id": op,
            "notification_id": "notification-001",
            "template_id": params["template_id"],
            "recipient_id": params["recipient_id"],
        }
        if tool == "notification.template.send"
        else {"kind": "read", "operation_id": op, "tool_id": tool}
    )
    raw_result = b"\n" + canonical_json_bytes(result) + b" \t"
    reserve = [
        {
            "grant_id": g,
            "amount_reserved_delta": amount,
            "amount_settled_delta": 0,
            "calls_reserved_delta": 1,
            "calls_settled_delta": 0,
        }
        for g in ids
    ]
    finish = [
        {
            "grant_id": g,
            "amount_reserved_delta": -amount,
            "amount_settled_delta": 0 if failed else amount,
            "calls_reserved_delta": -1,
            "calls_settled_delta": 0 if failed else 1,
        }
        for g in ids
    ]
    public_ledger = {
        "operation_id": op,
        "events": [
            {"phase": "RESERVE", "nodes": reserve},
            {"phase": "RELEASE" if failed else "SETTLE", "nodes": finish},
        ],
    }
    ledger_raw = canonical_ledger_changes_bytes(public_ledger)
    internal = deepcopy(public_ledger)
    for i, e in enumerate(internal["events"]):
        e["seq"] = i
    internal_raw = b" \n" + rfc8785.dumps(internal) + b"\t"
    objects, records = [], []

    def add(component, raw, owner, owner_id, ordinal=0):
        kind = {
            "accept_result_metadata": "typed_snapshot_metadata",
            "pending_receipt_metadata": "typed_snapshot_metadata",
            "internal_ledger": "ledger",
        }.get(component, component)
        ident = object_id(kind, owner, owner_id, component, ordinal)
        row = (kind, ident, raw)
        if row not in objects:
            objects.append(row)
        return {"component": component, "object_kind": kind, "object_id": ident}

    def authorization(seq, evidence, query=False, seconds=0):
        body = (
            {"profile": "GM-MVP-1", "task_id": "task-001", "operation_id": op} if query else request
        )
        raw = canonical_json_bytes(body) if query else raw_request
        endpoint = (
            "https://gateway.agent-guard.test/v1/operations/query"
            if query
            else "https://gateway.agent-guard.test/v1/invocations"
        )
        purpose = "result-read" if query else "invoke"
        proof = sign_ag_proof(
            holder_keys[-1],
            kid=leaf["ag_cnf"]["kid"],
            client_id=leaf["client_id"],
            purpose=purpose,
            endpoint=endpoint,
            token=tokens[-1].decode("ascii"),
            body=body,
            now=NOW + seconds,
        )
        proof_claims = load_strict_json(
            __import__("agent_guard.contracts.encoding", fromlist=["b64url_decode"]).b64url_decode(
                proof.split(".")[1]
            )
        )
        context = {
            "subject": leaf["sub"],
            "tenant_id": leaf["ag_tenant_id"],
            "task_id": leaf["ag_task_id"],
            "grant_id": leaf["ag_grant_id"],
            "root_id": leaf["ag_root_id"],
            "holder_client_id": leaf["client_id"],
            "holder_kid": leaf["ag_cnf"]["kid"],
            "token_exp": leaf["exp"],
            "proof_iat": proof_claims["iat"],
            "proof_exp": proof_claims["exp"],
            "proof_jti": proof_claims["jti"],
            "token_digest": sm3_b64url(tokens[-1]),
            "proof_digest": sm3_b64url(proof.encode()),
            "profile": "GM-MVP-1",
            "purpose": purpose,
            "endpoint": endpoint,
        }
        if query:
            context["operation_id"] = op
            context["method"] = "POST"
        else:
            context.update(
                tool_id=tool,
                idempotency_key=request["idempotency_key"],
                canonical_params=b64url_encode(canonical_json_bytes(params)),
                intent_digest=sm3_b64url(canonical_json_bytes(request)),
                ancestor_ids=ids[:-1],
                method="POST",
                tool_version="1",
            )
        rows = []
        for i, (c, token) in enumerate(zip(claims, tokens, strict=True)):

            def dt(name, c=c):
                return datetime.fromtimestamp(c[name], timezone.utc).isoformat()

            rows.append(
                {
                    "grant_id": c["ag_grant_id"],
                    "parent_id": c["ag_parent_id"],
                    "root_id": c["ag_root_id"],
                    "tenant_id": c["ag_tenant_id"],
                    "task_id": c["ag_task_id"],
                    "subject": c["sub"],
                    "client_id": c["client_id"],
                    "kid": c["ag_cnf"]["kid"],
                    "depth": i,
                    "nbf": dt("nbf"),
                    "exp": dt("exp"),
                    "amount": c["ag_limits"]["amount_fen"],
                    "calls": c["ag_limits"]["calls"],
                    "token": token.decode("ascii"),
                    "token_sm3": sm3_b64url(token),
                    "scope": c["scope"],
                    "constraints": canonical_json_bytes(c["ag_constraints"]).decode(),
                    "actor": canonical_json_bytes(c["act"]).decode(),
                    "spki": c["ag_cnf"]["spki_sm3"],
                    "saved_exp": dt("exp"),
                }
            )
        chain = canonical_json_bytes(rows)
        source = {
            "chain": chain.decode(),
            "digest": sm3_b64url(chain),
            "snapshot": {
                "grant_id": ids[-1],
                "root_id": ids[0],
                "tenant_id": scope.tenant_id,
                "task_id": scope.task_id,
                "subject": leaf["sub"],
                "scope": sorted(leaf["scope"].split()),
                "chain": [c["ag_constraints"] for c in claims],
                "chain_grant_ids": ids,
            },
        }
        raw_context, raw_source = (
            canonical_json_bytes(context),
            canonical_json_bytes(source),
        )
        refs = [
            add(k, r, "evidence", evidence)
            for k, r in (
                ("token", tokens[-1]),
                ("proof", proof.encode()),
                ("request", raw),
            )
        ]
        refs += [
            add(k, r, "journal", str(seq))
            for k, r in (("context", raw_context), ("source", raw_source))
        ]
        refs += [
            add("ancestor_token", token, "journal", str(seq), i) for i, token in enumerate(tokens)
        ]
        facts = {
            "token_digest": sm3_b64url(tokens[-1]),
            "proof_digest": sm3_b64url(proof.encode()),
            "body_digest": sm3_b64url(raw),
            "context_digest": sm3_b64url(raw_context),
            "source_digest": source["digest"],
            "source_material_digest": sm3_b64url(raw_source),
        }
        return refs, facts

    previous = genesis_digest(scope)

    def journal(kind, facts, refs, evidence=None, seconds=0):
        nonlocal previous
        seq = len(records) + 1
        suffix = (
            scope.stream_id
            if kind == "BOOTSTRAP"
            else evidence
            if kind in {"RETRY", "QUERY"}
            else facts["receipt_id"]
            if kind == "PUBLISH"
            else op
        )
        value = {
            **scope_object(scope),
            "seq": seq,
            "record_id": kind + ":" + suffix,
            "kind": kind,
            "operation_id": None if kind == "BOOTSTRAP" else op,
            "evidence_ref": evidence,
            "previous_digest": previous,
            "recorded_at": stamp(seconds),
            "facts": facts,
        }
        raw = canonical_json_bytes(value)
        previous = sm3_b64url(raw)
        objects.append(("journal", object_id("journal", "journal", str(seq), "journal"), raw))
        refs_raw = canonical_json_bytes(
            {
                "metadata_profile": "AG-TASK-REFS-1",
                "record_seq": seq,
                "operation_id": value["operation_id"],
                "evidence_ref": evidence,
                "refs": refs,
            }
        )
        objects.append(
            (
                "typed_snapshot_metadata",
                object_id("typed_snapshot_metadata", "journal", str(seq), "refs"),
                refs_raw,
            )
        )
        records.append(value)

    bootstrap_scope = [scope.gateway_id, scope.tenant_id, scope.task_id]
    root_claim = claims[0]
    baseline_token = tokens[0]
    if bootstrap_claim_overrides is not None:
        overrides = (
            bootstrap_claim_overrides(deepcopy(claims))
            if callable(bootstrap_claim_overrides)
            else bootstrap_claim_overrides
        )
        root_claim = {**deepcopy(root_claim), **deepcopy(overrides)}
        baseline_token = sign_compact_jws(
            as_key, root_claim, key_id="as-sign-1", token_type="ag-at+jwt"
        ).encode("ascii")

    def dt(seconds):
        return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    root_columns = {
        "grant_id": ids[0],
        "parent_grant_id": None,
        "root_grant_id": ids[0],
        "tenant_id": scope.tenant_id,
        "task_id": scope.task_id,
        "subject": root_claim["sub"],
        "holder_client_id": root_claim["client_id"],
        "holder_kid": root_claim["ag_cnf"]["kid"],
        "depth": 0,
        "not_before": dt(root_claim["nbf"]),
        "expires_at": dt(root_claim["exp"]),
        "revoked": False,
        "revoked_at": None,
        "amount_limit": root_claim["ag_limits"]["amount_fen"],
        "call_limit": root_claim["ag_limits"]["calls"],
        "amount_reserved": baseline,
        "amount_settled": 0,
        "calls_reserved": 0,
        "calls_settled": 0,
        "created_at": dt(root_claim["iat"]),
    }
    bootstrap = [
        (
            "typed_snapshot_metadata",
            "ag_grants:0",
            canonical_json_bytes({"table": "ag_grants", "row_index": 0, "columns": root_columns}),
        )
    ]
    token_columns = {
        "grant_id": ids[0],
        "token_sm3": sm3_b64url(baseline_token),
        "scope": root_claim["scope"],
        "holder_spki_sm3": root_claim["ag_cnf"]["spki_sm3"],
        "issued_at": dt(root_claim["iat"]),
        "expires_at": dt(root_claim["exp"]),
    }
    for name, kind, raw in (
        ("token_jws", "token", baseline_token),
        (
            "constraints_json",
            "raw_authorization_snapshot",
            canonical_json_bytes(root_claim["ag_constraints"]),
        ),
        (
            "actor_json",
            "raw_authorization_snapshot",
            canonical_json_bytes(root_claim["act"]),
        ),
    ):
        ident = "ag_grant_tokens:0:" + name
        bootstrap.append((kind, ident, raw))
        token_columns[name] = {
            "kind": kind,
            "object_id": ident,
            "digest": sm3_b64url(raw),
        }
    bootstrap.append(
        (
            "typed_snapshot_metadata",
            "ag_grant_tokens:0",
            canonical_json_bytes(
                {"table": "ag_grant_tokens", "row_index": 0, "columns": token_columns}
            ),
        )
    )
    index = sm3_b64url(
        canonical_json_bytes({"profile": "AG-BOOTSTRAP-INDEX-1", "scope": bootstrap_scope})
    )
    wire = chunk_count = 0
    for kind, ident, raw in sorted(bootstrap):
        count = (len(raw) + 24575) // 24576
        index = sm3_b64url(
            canonical_json_bytes(
                {
                    "profile": "AG-BOOTSTRAP-INDEX-1",
                    "previous": index,
                    "kind": kind,
                    "id": ident,
                    "total_raw_bytes": len(raw),
                    "object_digest": sm3_b64url(raw),
                    "chunk_count": count,
                }
            )
        )
        wire += sum(map(len, encode_object_chunks(kind, ident, raw)))
        chunk_count += count
        objects.append((kind, object_id(kind, "bootstrap", ident, ident), raw))
    boundary = "LEGACY_WITH_GAPS" if baseline else "NEW_EMPTY"
    manifest = {
        "profile": "AG-BOOTSTRAP-1",
        "scope": bootstrap_scope,
        "root_grant_id": ids[0],
        "snapshot_as_of": stamp(),
        "origin": "LEGACY_WITH_GAPS" if baseline else "FROM_EMPTY_TASK",
        "object_count": len(bootstrap),
        "chunk_count": chunk_count,
        "wire_bytes": wire,
        "index_root": index,
        "schema_lineage_digest": sm3_b64url(canonical_json_bytes([])),
    }
    manifest_raw = canonical_json_bytes(manifest)
    for ident, raw in (
        ("manifest", manifest_raw),
        ("schema_lineage", canonical_json_bytes([])),
    ):
        objects.append(
            (
                "typed_snapshot_metadata",
                object_id("typed_snapshot_metadata", "bootstrap", ident, ident),
                raw,
            )
        )
    registration = {
        "genesis_digest": genesis_digest(scope),
        "bootstrap_digest": sm3_b64url(manifest_raw),
        "boundary": boundary,
        "index_root": index,
        "object_count": len(bootstrap),
        "chunk_count": chunk_count,
        "wire_bytes": wire,
    }
    journal(
        "BOOTSTRAP",
        {
            "boundary": boundary,
            "root_grant_id": ids[0],
            "snapshot_as_of": stamp(),
            "schema_lineage_digest": manifest["schema_lineage_digest"],
            "index_root": index,
            "manifest_digest": registration["bootstrap_digest"],
            "object_count": len(bootstrap),
            "chunk_count": chunk_count,
            "wire_bytes": wire,
        },
        [],
    )
    base_calls = 0
    if tool == "notification.template.send":
        saved = (op, tool, params, request, raw_request)
        op, tool, params = (
            "prerequisite-001",
            "procurement.request.read",
            {"request_id": "req-001"},
        )
        request = {
            "profile": "GM-MVP-1",
            "task_id": "task-001",
            "tool_id": tool,
            "tool_version": "1",
            "idempotency_key": "prerequisite-read",
            "params": params,
        }
        raw_request = canonical_json_bytes(request)
        refs, prior = authorization(len(records) + 1, "ev-prerequisite")
        prior.update(
            root_grant_id=ids[0],
            grant_id=ids[-1],
            path_ids=ids,
            intent_digest=sm3_b64url(raw_request),
            reserve_digest=sm3_b64url(
                canonical_json_bytes([[i, g, 0, 0, 1, 0] for i, g in enumerate(ids)])
            ),
            quote_digest=None,
            amount_fen=0,
            calls=1,
            currency="CNY",
            introduced_grants=[
                {
                    "grant_id": c["ag_grant_id"],
                    "parent_id": c["ag_parent_id"],
                    "root_id": c["ag_root_id"],
                    "depth": i,
                    "holder_client_id": c["client_id"],
                    "holder_kid": c["ag_cnf"]["kid"],
                    "grant_token_digest": sm3_b64url(tokens[i]),
                    "source_material_digest": prior["source_material_digest"],
                    "amount_reserved": 0,
                    "amount_settled": 0,
                    "calls_reserved": 0,
                    "calls_settled": 0,
                }
                for i, c in enumerate(claims)
                if i
            ],
        )
        journal("FIRST", prior, refs, "ev-prerequisite")
        prior_ledger = {
            "operation_id": op,
            "events": [
                {
                    "phase": "RESERVE",
                    "nodes": [
                        {
                            "grant_id": g,
                            "amount_reserved_delta": 0,
                            "amount_settled_delta": 0,
                            "calls_reserved_delta": 1,
                            "calls_settled_delta": 0,
                        }
                        for g in ids
                    ],
                },
                {
                    "phase": "SETTLE",
                    "nodes": [
                        {
                            "grant_id": g,
                            "amount_reserved_delta": 0,
                            "amount_settled_delta": 0,
                            "calls_reserved_delta": -1,
                            "calls_settled_delta": 1,
                        }
                        for g in ids
                    ],
                },
            ],
        }
        prior_internal = deepcopy(prior_ledger)
        for i, e in enumerate(prior_internal["events"]):
            e["seq"] = i
        prior_internal_raw = rfc8785.dumps(prior_internal)
        prior_public = canonical_ledger_changes_bytes(prior_ledger)
        prior_result = canonical_json_bytes({"kind": "read", "operation_id": op, "tool_id": tool})
        from agent_guard.execution.receipts import receipt_id_for

        prior_id = receipt_id_for(op)
        prior_pending = {
            "receipt_id": prior_id,
            "operation_id": op,
            "profile": "GM-MVP-1",
            "tenant_id": scope.tenant_id,
            "task_id": scope.task_id,
            "root_grant_id": ids[0],
            "grant_id": ids[-1],
            "tool_id": tool,
            "tool_version": "1",
            "status": "SUCCEEDED",
            "amount_fen": 0,
            "token_digest": prior["token_digest"],
            "proof_digest": prior["proof_digest"],
            "intent_digest": prior["intent_digest"],
            "evidence_ref": "ev-prerequisite",
            "created_at": stamp(),
        }
        pending_raw = rfc8785.dumps(
            {
                **prior_pending,
                "ledger_changes_json": b64url_encode(prior_internal_raw),
                "result_bytes": b64url_encode(prior_result),
            }
        )
        refs = [
            add(k, r, "operation", op)
            for k, r in (
                ("ledger", prior_public),
                ("internal_ledger", prior_internal_raw),
                ("result", prior_result),
                (
                    "pending_receipt_metadata",
                    canonical_json_bytes(
                        {
                            "metadata_profile": "AG-TASK-PENDING-RECEIPT-1",
                            **prior_pending,
                        }
                    ),
                ),
            )
        ]
        journal(
            "TERMINAL",
            {
                "first_evidence_ref": "ev-prerequisite",
                "status": "SUCCEEDED",
                "action": "SETTLE",
                "result_digest": sm3_b64url(prior_result),
                "ledger_digest": sm3_b64url(prior_public),
                "pending_receipt_digest": sm3_b64url(pending_raw),
                "receipt_id": prior_id,
                "owner_token": "synthetic-owner",
                "fencing_version": 1,
                "lease_expires_at": stamp(3),
                "path_ids": ids,
            },
            refs,
            "ev-prerequisite",
        )
        prior_claims = {
            "profile": "GM-MVP-1",
            "receipt_id": prior_id,
            "operation_id": op,
            "tenant_id": scope.tenant_id,
            "task_id": scope.task_id,
            "root_grant_id": ids[0],
            "grant_id": ids[-1],
            "token_sm3": prior["token_digest"],
            "proof_sm3": prior["proof_digest"],
            "intent_sm3": prior["intent_digest"],
            "tool_id": tool,
            "tool_version": "1",
            "status": "SUCCEEDED",
            "amount_fen": 0,
            "result_sm3": sm3_b64url(prior_result),
            "ledger_sm3": sm3_b64url(prior_public),
            "iat": NOW,
        }
        prior_receipt = sign_compact_jws(
            gateway,
            prior_claims,
            key_id="gateway-receipt-1",
            token_type="ag-receipt+jwt",
        )
        journal(
            "PUBLISH",
            {
                "receipt_id": prior_id,
                "receipt_jws_digest": sm3_b64url(prior_receipt.encode()),
                "signed_at": stamp(),
            },
            [add("receipt", prior_receipt.encode(), "operation", op)],
            "ev-prerequisite",
        )
        objects.append(
            (
                "typed_snapshot_metadata",
                object_id("typed_snapshot_metadata", "runtime", op, "runtime"),
                canonical_json_bytes(
                    {
                        "metadata_profile": "AG-TASK-RUNTIME-OBSERVATION-1",
                        "operation_id": op,
                        "status": "SUCCEEDED",
                        "receipt_status": "READY",
                    }
                ),
            )
        )
        op, tool, params, request, raw_request = saved
        base_calls = 1
    refs, first_facts = authorization(len(records) + 1, first_ref)
    if quote_raw:
        refs.append(add("quote", quote_raw, "operation", op))
    introduced = [
        {
            "grant_id": c["ag_grant_id"],
            "parent_id": c["ag_parent_id"],
            "root_id": c["ag_root_id"],
            "depth": i,
            "holder_client_id": c["client_id"],
            "holder_kid": c["ag_cnf"]["kid"],
            "grant_token_digest": sm3_b64url(tokens[i]),
            "source_material_digest": first_facts["source_material_digest"],
            "amount_reserved": 0,
            "amount_settled": 0,
            "calls_reserved": 0,
            "calls_settled": 0,
        }
        for i, c in enumerate(claims)
        if i and not base_calls
    ]
    first_facts.update(
        root_grant_id=ids[0],
        grant_id=ids[-1],
        path_ids=ids,
        intent_digest=sm3_b64url(canonical_json_bytes(request)),
        reserve_digest=sm3_b64url(
            canonical_json_bytes([[i, g, amount, 0, 1, 0] for i, g in enumerate(ids)])
        ),
        quote_digest=sm3_b64url(quote_raw) if quote_raw else None,
        amount_fen=amount,
        calls=1,
        currency="CNY",
        introduced_grants=introduced,
    )
    journal("FIRST", first_facts, refs, first_ref)
    if with_history:
        for retry_index in range(2 if repeat_retry else 1):
            retry_ref = "ev-retry" + (str(retry_index) if repeat_retry else "")
            refs, facts = authorization(len(records) + 1, retry_ref, seconds=1 + retry_index)
            quote = load_strict_json(quote_raw) if quote_raw else None
            cost = {
                "amount_fen": amount,
                "calls": 1,
                "currency": "CNY",
                "quote_id": quote["quote_id"] if quote else None,
                "quote_version": quote["quote_version"] if quote else None,
                "quote_snapshot": None,
            }
            metadata = {
                "metadata_profile": "AG-TASK-ACCEPT-RESULT-1",
                "operation_id": op,
                "grant_id": ids[-1],
                "root_id": ids[0],
                "status": "RESERVED",
                "disposition": "EXISTING",
                "cost": cost,
                "accepted_at": stamp(1 if retry_index and changed_accepted_at else 0),
            }
            response = {k: deepcopy(v) for k, v in metadata.items() if k != "metadata_profile"}
            if quote_raw:
                response["cost"]["quote_snapshot"] = b64url_encode(quote_raw)
                refs.append(add("quote", quote_raw, "operation", op))
            refs.append(
                add(
                    "accept_result_metadata",
                    canonical_json_bytes(metadata),
                    "journal",
                    str(len(records) + 1),
                )
            )
            facts.update(
                first_evidence_ref=first_ref,
                intent_digest=first_facts["intent_digest"],
                response_kind="ACCEPT_RESULT",
                response_digest=sm3_b64url(rfc8785.dumps(response)),
                status="RESERVED",
                receipt_status="PENDING",
                receipt_jws_digest=None,
            )
            if accept_response:
                refs = [
                    ref
                    for ref in refs
                    if ref["component"] not in {"accept_result_metadata", "quote"}
                ]
                objects[:] = [
                    row
                    for row in objects
                    if row[1]
                    != object_id(
                        "typed_snapshot_metadata",
                        "journal",
                        str(len(records) + 1),
                        "accept_result_metadata",
                    )
                ]
                facts["response_kind"] = "ACCEPT_RESPONSE"
                facts["response_digest"] = sm3_b64url(
                    canonical_json_bytes(
                        {
                            "operation_id": op,
                            "status": "RESERVED",
                            "receipt_status": "PENDING",
                        }
                    )
                )
            journal("RETRY", facts, refs, retry_ref, 1 + retry_index)
    receipt_id = "receipt-" + sm3_b64url(op.encode())
    # Use the accepted original deterministic receipt ID helper.
    from agent_guard.execution.receipts import receipt_id_for

    receipt_id = receipt_id_for(op)
    if terminal:
        pending = {
            "receipt_id": receipt_id,
            "operation_id": op,
            "profile": "GM-MVP-1",
            "tenant_id": scope.tenant_id,
            "task_id": scope.task_id,
            "root_grant_id": ids[0],
            "grant_id": ids[-1],
            "tool_id": tool,
            "tool_version": "1",
            "status": status,
            "amount_fen": 0 if failed else amount,
            "token_digest": first_facts["token_digest"],
            "proof_digest": first_facts["proof_digest"],
            "intent_digest": first_facts["intent_digest"],
            "evidence_ref": first_ref,
            "created_at": stamp(2),
        }
        pending_raw = rfc8785.dumps(
            {
                **pending,
                "ledger_changes_json": b64url_encode(internal_raw),
                "result_bytes": b64url_encode(raw_result),
            }
        )
        refs = [
            add(k, r, "operation", op)
            for k, r in (
                ("ledger", ledger_raw),
                ("internal_ledger", internal_raw),
                ("result", raw_result),
                (
                    "pending_receipt_metadata",
                    canonical_json_bytes(
                        {"metadata_profile": "AG-TASK-PENDING-RECEIPT-1", **pending}
                    ),
                ),
            )
        ]
        if quote_raw:
            refs.append(add("quote", quote_raw, "operation", op))
        journal(
            "TERMINAL",
            {
                "first_evidence_ref": first_ref,
                "status": status,
                "action": "RELEASE" if failed else "SETTLE",
                "result_digest": sm3_b64url(raw_result),
                "ledger_digest": sm3_b64url(ledger_raw),
                "pending_receipt_digest": sm3_b64url(pending_raw),
                "receipt_id": receipt_id,
                "owner_token": "synthetic-owner",
                "fencing_version": 1,
                "lease_expires_at": stamp(3),
                "path_ids": ids,
            },
            refs,
            first_ref,
            2,
        )
    receipt = None
    if terminal and publish:
        receipt_claims = {
            "profile": "GM-MVP-1",
            "receipt_id": receipt_id,
            "operation_id": op,
            "tenant_id": scope.tenant_id,
            "task_id": scope.task_id,
            "root_grant_id": ids[0],
            "grant_id": ids[-1],
            "token_sm3": first_facts["token_digest"],
            "proof_sm3": first_facts["proof_digest"],
            "intent_sm3": first_facts["intent_digest"],
            "tool_id": tool,
            "tool_version": "1",
            "status": status,
            "amount_fen": 0 if failed else amount,
            "result_sm3": sm3_b64url(canonical_json_bytes(result)),
            "ledger_sm3": sm3_b64url(ledger_raw),
            "iat": NOW + 2,
        }
        receipt = sign_compact_jws(
            gateway,
            receipt_claims,
            key_id="gateway-receipt-1",
            token_type="ag-receipt+jwt",
        )
        journal(
            "PUBLISH",
            {
                "receipt_id": receipt_id,
                "receipt_jws_digest": sm3_b64url(receipt.encode()),
                "signed_at": stamp(3),
            },
            [add("receipt", receipt.encode(), "operation", op)],
            first_ref,
            3,
        )
    if with_history:
        refs, facts = authorization(len(records) + 1, "ev-query", query=True, seconds=4)
        response = {
            "operation_id": op,
            "status": status if terminal else "UNKNOWN",
            "receipt_status": "READY" if receipt else "PENDING",
            "result": result if terminal else None,
            "receipt_jws": receipt,
        }
        facts.update(
            first_evidence_ref=first_ref,
            response_digest=sm3_b64url(canonical_json_bytes(response)),
            status=response["status"],
            receipt_status=response["receipt_status"],
            result_digest=sm3_b64url(canonical_json_bytes(result)) if terminal else None,
            receipt_jws_digest=sm3_b64url(receipt.encode()) if receipt else None,
        )
        if terminal:
            refs.append(add("result", raw_result, "operation", op))
        if receipt:
            refs.append(add("receipt", receipt.encode(), "operation", op))
        journal("QUERY", facts, refs, "ev-query", 4)
    runtime = {
        "metadata_profile": "AG-TASK-RUNTIME-OBSERVATION-1",
        "operation_id": op,
        "status": status if terminal else "UNKNOWN",
        "receipt_status": "READY" if receipt else "PENDING" if terminal else None,
    }
    objects.append(
        (
            "typed_snapshot_metadata",
            object_id("typed_snapshot_metadata", "runtime", op, "runtime"),
            canonical_json_bytes(runtime),
        )
    )
    rotated_audit = generate_sm2_private_key() if rotate_audit else audit
    cp_originals, cp_previous = [], None
    for seq in (1, 2, len(records)) if middle_checkpoint else (1, len(records)):
        audit_kid = "audit-test-2" if rotate_audit and seq > 1 else "audit-test-1"
        head = sm3_b64url(canonical_json_bytes(records[seq - 1]))
        cp = sign_checkpoint(
            {
                "profile": "GM-MVP-1",
                "checkpoint_version": "AG-CHECKPOINT-1",
                "checkpoint_id": "cp-" + str(seq),
                **asdict(scope),
                "sequence": seq,
                "head_digest": head,
                "previous_checkpoint_digest": cp_previous,
                "issued_at": stamp(5),
                "kid": audit_kid,
            },
            private_key=rotated_audit if seq > 1 else audit,
            key_id=audit_kid,
        )
        cp_previous = sm3_b64url(cp.encode("ascii"))
        cp_originals.append(cp)
        objects.append(
            (
                "checkpoint",
                object_id("checkpoint", "checkpoint", "cp-" + str(seq), "checkpoint"),
                cp.encode("ascii"),
            )
        )

    def key_map(kid, key):
        return {kid: b64url_encode(serialize_sm2_public_key(key.public_key()))}

    catalog = {
        "requests": [
            {
                "request_id": "req-001",
                "tenant_id": scope.tenant_id,
                "task_id": scope.task_id,
                "status": "APPROVED",
            }
        ],
        "documents": [{"document_id": "doc-001", "request_id": "req-001", "body": "synthetic"}],
        "quotes": [
            {
                "quote_id": "quote-001",
                "quote_version": "1",
                "supplier_id": "supplier-001",
                "request_id": "req-001",
                "lines": [{"sku": "sku-001", "quantity": 1, "unit_price_fen": 70000}],
            }
        ],
        "deliveries": [
            {
                "delivery_id": "office-001",
                "tenant_id": scope.tenant_id,
                "request_id": "req-001",
            }
        ],
        "templates": [{"template_id": "order-created", "body": "order-created"}],
        "recipients": [{"recipient_id": "user-001"}],
    }
    trust = {
        "version": "AG-TASK-TRUST-1",
        "issuer": ISSUER,
        "as_keys": key_map("as-sign-1", as_key),
        "gateway_keys": key_map("gateway-receipt-1", gateway),
        "holder_keys": {r["kid"]: r["spki_der"] for r in registrations},
        "historical_registrations": registrations,
        "catalog": catalog,
        "audit_keys": [
            {
                "kid": "audit-test-1",
                "role": "AUDIT_SIGNER",
                "spki_der": b64url_encode(serialize_sm2_public_key(audit.public_key())),
                "first_sequence": 1,
                "last_sequence": None,
            }
        ],
        "scope": asdict(scope),
        "registration": registration,
    }
    if rotate_audit:
        trust["audit_keys"][0]["last_sequence"] = 1
        trust["audit_keys"].append(
            {
                "kid": "audit-test-2",
                "role": "AUDIT_SIGNER",
                "spki_der": b64url_encode(serialize_sm2_public_key(rotated_audit.public_key())),
                "first_sequence": 2,
                "last_sequence": None,
            }
        )
    pin = {
        "mode": mode,
        "checkpoint_jws": None if mode == "UNKNOWN" else cp_originals[-1],
        "observed_at": NOW + 5 if mode == "LATEST_OBSERVATION" else None,
        "scope": asdict(scope),
    }
    header = task_header(
        scope,
        object_count=len(objects),
        chunk_count=len(objects),
        journal_count=len(records),
        operation_count=1 + base_calls,
        head=previous,
    )
    header.update(bootstrap_digest=registration["bootstrap_digest"], history_boundary=boundary)
    value = {
        "scope": scope,
        "objects": objects,
        "header": header,
        "trust": trust,
        "pin": pin,
        "records": records,
        "operation_id": op,
        "amount": amount,
        "base_calls": base_calls,
        "cp_originals": cp_originals,
    }
    value["bundle"] = rebuild(value)
    return value


def rebuild(value, objects=None):
    objects = value["objects"] if objects is None else objects
    header = dict(
        value["header"],
        object_count=len(objects),
        chunk_count=sum((len(raw) + 24575) // 24576 for _, _, raw in objects),
        journal_count=sum(k == "journal" for k, _, _ in objects),
    )
    return encode_task(value["scope"], objects, header=header)
