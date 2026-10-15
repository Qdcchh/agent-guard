"""Independent synthetic public A32 ingredients; real SM2, no peer or database.

Private signing keys are ephemeral test locals and are never returned as trust.
The fixture includes exact raw originals, typed identities and external pins.
"""

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from agent_guard.audit.checkpoint import sign_checkpoint
from agent_guard.audit.contracts import CheckpointTrust, JournalScope, genesis_digest
from agent_guard.authorization.permission_snapshot import PermissionSource
from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from agent_guard.contracts.execution import GrantConstraints, TrustedPermissionSnapshot
from agent_guard.contracts.ledger_changes import canonical_ledger_changes_bytes
from agent_guard.crypto.sm import (
    generate_sm2_private_key,
    serialize_sm2_public_key,
    sign_compact_jws,
    sm3_b64url,
    verify_compact_jws,
)
from agent_guard.evidence.receipt_semantics import ReceiptComponents
from agent_guard.evidence.task_bundle import (
    encode_object_chunks,
    index_fold,
    index_seed,
    object_id,
    wire_fold,
    wire_seed,
)
from tests.test_authorization import NOW
from tests.test_receipt_paths import _signed_path


def signed_receipt_material(*, noncanonical_request=False):
    bundle, trust, gateway, receipt = _signed_path()
    path = [
        verify_compact_jws(t, expected_type="ag-at+jwt", trusted_keys=trust.as_keys)
        for t in bundle["ancestor_tokens"]
    ]
    leaf = path[-1]
    request = canonical_json_bytes(bundle["request"])
    if noncanonical_request:
        request = b" \n" + request + b"\t"
    quote = {
        "quote_id": "quote-001",
        "quote_version": "1",
        "supplier_id": "supplier-001",
        "items": [{"sku": "sku-001", "quantity": 1, "unit_price_fen": 70000}],
        "total_fen": 70000,
        "currency": "CNY",
    }
    result = {
        "kind": "order",
        "operation_id": receipt["operation_id"],
        "order_id": "order-001",
        "supplier_id": "supplier-001",
        "quote_id": "quote-001",
        "quote_version": "1",
        "items": quote["items"],
        "total_fen": 70000,
    }
    receipt["result_sm3"] = sm3_b64url(canonical_json_bytes(result))
    bundle["result"] = result
    bundle["receipt_jws"] = sign_compact_jws(
        gateway, receipt, key_id="gateway-receipt-1", token_type="ag-receipt+jwt"
    )
    proof = verify_compact_jws(
        bundle["proof_jws"], expected_type="ag-pop+jwt", trusted_keys=trust.holder_keys
    )
    context = {
        "subject": leaf["sub"],
        "tenant_id": leaf["ag_tenant_id"],
        "task_id": leaf["ag_task_id"],
        "grant_id": leaf["ag_grant_id"],
        "root_id": leaf["ag_root_id"],
        "holder_client_id": leaf["client_id"],
        "holder_kid": leaf["ag_cnf"]["kid"],
        "tool_id": bundle["request"]["tool_id"],
        "idempotency_key": bundle["request"]["idempotency_key"],
        "canonical_params": b64url_encode(canonical_json_bytes(bundle["request"]["params"])),
        "token_exp": leaf["exp"],
        "proof_iat": proof["iat"],
        "proof_exp": proof["exp"],
        "proof_jti": proof["jti"],
        "token_digest": receipt["token_sm3"],
        "proof_digest": receipt["proof_sm3"],
        "intent_digest": receipt["intent_sm3"],
        "ancestor_ids": [p["ag_grant_id"] for p in path[:-1]],
        "profile": "GM-MVP-1",
        "purpose": "invoke",
        "endpoint": "https://gateway.agent-guard.test/v1/invocations",
        "method": "POST",
        "tool_version": "1",
    }
    rows = []
    for i, (claims, token) in enumerate(zip(path, bundle["ancestor_tokens"], strict=True)):

        def dt(name, claims=claims):
            return datetime.fromtimestamp(claims[name], timezone.utc).isoformat()

        rows.append(
            {
                "grant_id": claims["ag_grant_id"],
                "parent_id": claims["ag_parent_id"],
                "root_id": claims["ag_root_id"],
                "tenant_id": claims["ag_tenant_id"],
                "task_id": claims["ag_task_id"],
                "subject": claims["sub"],
                "client_id": claims["client_id"],
                "kid": claims["ag_cnf"]["kid"],
                "depth": i,
                "nbf": dt("nbf"),
                "exp": dt("exp"),
                "amount": claims["ag_limits"]["amount_fen"],
                "calls": claims["ag_limits"]["calls"],
                "token": token,
                "token_sm3": sm3_b64url(token.encode()),
                "scope": claims["scope"],
                "constraints": canonical_json_bytes(claims["ag_constraints"]).decode(),
                "actor": canonical_json_bytes(claims["act"]).decode(),
                "spki": claims["ag_cnf"]["spki_sm3"],
                "saved_exp": dt("exp"),
            }
        )
    snapshot = TrustedPermissionSnapshot(
        leaf["ag_grant_id"],
        leaf["ag_root_id"],
        leaf["ag_tenant_id"],
        leaf["ag_task_id"],
        leaf["sub"],
        tuple(sorted(leaf["scope"].split())),
        tuple(
            GrantConstraints(
                **{k: v if type(v) is int else tuple(v) for k, v in p["ag_constraints"].items()}
            )
            for p in path
        ),
        tuple(p["ag_grant_id"] for p in path),
    )
    raw_chain = canonical_json_bytes(rows)
    source = PermissionSource(snapshot, raw_chain, sm3_b64url(raw_chain))
    components = ReceiptComponents(
        bundle["token_jws"].encode(),
        bundle["proof_jws"].encode(),
        tuple(t.encode() for t in bundle["ancestor_tokens"]),
        request,
        canonical_json_bytes(result),
        canonical_ledger_changes_bytes(bundle["ledger_changes"]),
        bundle["receipt_jws"].encode(),
        canonical_json_bytes(quote),
        canonical_json_bytes(context),
        source.material(),
    )
    return {
        "components": components,
        "receipt_trust": trust,
        "v1_bundle": bundle,
        "receipt_claims": receipt,
        "path_claims": tuple(path),
        "source": source,
        "request_sm3": sm3_b64url(request),
        "expected": {
            "operation_id": receipt["operation_id"],
            "status": "SUCCEEDED",
            "amount_fen": 70000,
            "current_auth": "UNKNOWN",
            "downstream_truth": "ATTESTED_NOT_INDEPENDENTLY_PROVEN",
            "runtime_assurance": "UNANCHORED_AS_OF_DB_OBSERVATION",
        },
    }


def checkpoint_material(*, sequences=(1, 2, 3), mode="LATEST_OBSERVATION", scope=None):
    scope = scope or JournalScope(
        "https://gateway.agent-guard.test", "tenant-001", "task-001", str(uuid4()), 1
    )
    key = generate_sm2_private_key()
    trust = (
        CheckpointTrust(
            "audit-test-1",
            "AUDIT_SIGNER",
            serialize_sm2_public_key(key.public_key()),
            1,
            None,
        ),
    )
    previous = None
    originals = []
    for sequence in sequences:
        jws = sign_checkpoint(
            {
                "profile": "GM-MVP-1",
                "checkpoint_version": "AG-CHECKPOINT-1",
                "checkpoint_id": "cp-" + str(sequence),
                **asdict(scope),
                "sequence": sequence,
                "head_digest": sm3_b64url(str(sequence).encode()),
                "previous_checkpoint_digest": previous,
                "issued_at": "2027-01-15T08:00:00.000000Z",
                "kid": "audit-test-1",
            },
            private_key=key,
            key_id="audit-test-1",
        )
        originals.append(jws)
        previous = sm3_b64url(jws.encode("ascii"))
    pin = {
        "mode": mode,
        "checkpoint_jws": None if mode == "UNKNOWN" else originals[-1],
        "observed_at": NOW if mode == "LATEST_OBSERVATION" else None,
        "scope": asdict(scope),
    }
    return {
        "scope": scope,
        "external_trust": {"scope": scope, "audit_keys": trust},
        "external_pin": pin,
        "originals": tuple(originals),
        "history_raw": b"".join(
            canonical_json_bytes({"checkpoint_jws": jws}) + b"\n" for jws in originals
        ),
    }


def task_header(scope, *, object_count, chunk_count, journal_count=0, operation_count=0, head=None):
    return {
        "frame_type": "HEADER",
        "manifest_version": "AG-TASK-EVIDENCE-2",
        "scope": asdict(scope),
        "cutoff_sequence": journal_count,
        "cutoff_head_digest": head or genesis_digest(scope),
        "snapshot_as_of": NOW,
        "snapshot_id": "snapshot-test-1",
        "history_boundary": "NEW_EMPTY",
        "bootstrap_digest": sm3_b64url(b"test-bootstrap"),
        "object_count": object_count,
        "chunk_count": chunk_count,
        "journal_count": journal_count,
        "operation_count": operation_count,
    }


def encode_task(scope, objects, *, header=None):
    """Build folds from exact originals, stable (kind,id) ordering, complete EOF."""
    from agent_guard.contracts.encoding import load_strict_json

    objects = sorted(objects, key=lambda obj: obj[:2])
    chunks = [
        frame for kind, ident, raw in objects for frame in encode_object_chunks(kind, ident, raw)
    ]
    header = header or task_header(
        scope,
        object_count=len(objects),
        chunk_count=len(chunks),
        journal_count=sum(kind == "journal" for kind, _, _ in objects),
    )
    frames = [canonical_json_bytes(header) + b"\n"] + chunks
    index, wire = index_seed(scope), wire_seed(scope)
    for n, raw in enumerate(frames):
        frame = load_strict_json(raw[:-1])
        if (
            frame["frame_type"] == "OBJECT_CHUNK"
            and frame["chunk_index"] == frame["chunk_count"] - 1
        ):
            index = index_fold(index, frame)
        wire = wire_fold(wire, n, raw)
    footer = {
        "frame_type": "FOOTER",
        "object_index_root": index,
        "wire_root": wire,
        "before_footer_frames": len(frames),
        "before_footer_wire_bytes": sum(map(len, frames)),
    }
    return b"".join(frames) + canonical_json_bytes(footer) + b"\n"


def receipt_objects(material, *, evidence_ref="ev-test-1", operation_id="operation-001"):
    c = material["components"]
    objects, refs = [], []
    specifications = [
        ("token", c.token_jws, "evidence", evidence_ref),
        ("proof", c.proof_jws, "evidence", evidence_ref),
        ("request", c.request_raw, "evidence", evidence_ref),
        ("context", c.context_raw, "journal", "2"),
        ("source", c.source_raw, "journal", "2"),
        ("quote", c.quote_raw, "operation", operation_id),
        ("ledger", c.ledger_raw, "operation", operation_id),
        ("result", c.result_raw, "operation", operation_id),
        ("receipt", c.receipt_jws, "operation", operation_id),
    ]
    specifications += [("ancestor_token", raw, "journal", "2") for raw in c.ancestor_tokens]
    ordinal = 0
    for kind, raw, owner, owner_id in specifications:
        ident = object_id(kind, owner, owner_id, kind, ordinal if kind == "ancestor_token" else 0)
        if kind == "ancestor_token":
            ordinal += 1
        objects.append((kind, ident, raw))
        refs.append({"component": kind, "object_kind": kind, "object_id": ident})
    return tuple(objects), tuple(refs)


def public_trust_input(material, checkpoint, *, registration, catalog):
    """Exact independently supplied public trust JSON; no keys from bundle."""
    trust = material["receipt_trust"]

    def keys(values):
        return {kid: b64url_encode(serialize_sm2_public_key(key)) for kid, key in values.items()}

    return {
        "version": "AG-TASK-TRUST-1",
        "issuer": trust.issuer,
        "as_keys": keys(trust.as_keys),
        "gateway_keys": keys(trust.gateway_keys),
        "holder_keys": keys(trust.holder_keys),
        "historical_registrations": [
            {
                "tenant_id": r.tenant_id,
                "client_id": r.client_id,
                "did": r.did,
                "kid": r.kid,
                "spki_der": b64url_encode(r.spki_der),
                "active": r.active,
                "role": "HOLDER",
            }
            for r in trust.historical_registrations.values()
        ],
        "catalog": catalog,
        "audit_keys": [
            {**asdict(t), "spki_der": b64url_encode(t.spki_der)}
            for t in checkpoint["external_trust"]["audit_keys"]
        ],
        "scope": asdict(checkpoint["scope"]),
        "registration": registration,
    }


def signed_task_material(*, mode="LATEST_OBSERVATION", noncanonical_request=True):
    """Self-contained synthetic bootstrap/FIRST/TERMINAL/PUBLISH with authentic CP.

    This is independently usable public material, not a claim of PG execution.
    The joint acceptance must still run the actual AS and gateway business path.
    """
    from agent_guard.audit.contracts import decode_journal_record, scope_object
    from agent_guard.contracts.encoding import load_strict_json

    material = signed_receipt_material(noncanonical_request=noncanonical_request)
    cp = checkpoint_material(sequences=(), mode="UNKNOWN")
    scope = cp["scope"]
    c = material["components"]
    operation = material["expected"]["operation_id"]
    evidence = "ev-test-1"
    stamp = "2027-01-15T08:00:00.000000Z"
    schema = canonical_json_bytes([])
    snapshot_raw = canonical_json_bytes({"table": "ag_operations", "row_index": 0, "columns": {}})
    snapshot_id = "synthetic-empty-metadata"
    snapshot_digest = sm3_b64url(snapshot_raw)
    bootstrap_scope = [scope.gateway_id, scope.tenant_id, scope.task_id]
    bootstrap_index = sm3_b64url(
        canonical_json_bytes({"profile": "AG-BOOTSTRAP-INDEX-1", "scope": bootstrap_scope})
    )
    bootstrap_index = sm3_b64url(
        canonical_json_bytes(
            {
                "profile": "AG-BOOTSTRAP-INDEX-1",
                "previous": bootstrap_index,
                "kind": "typed_snapshot_metadata",
                "id": snapshot_id,
                "total_raw_bytes": len(snapshot_raw),
                "object_digest": snapshot_digest,
                "chunk_count": 1,
            }
        )
    )
    bootstrap_wire = sum(
        len(raw)
        for raw in encode_object_chunks("typed_snapshot_metadata", snapshot_id, snapshot_raw)
    )
    manifest = canonical_json_bytes(
        {
            "profile": "AG-BOOTSTRAP-1",
            "scope": bootstrap_scope,
            "root_grant_id": "grant-root",
            "snapshot_as_of": stamp,
            "origin": "FROM_EMPTY_TASK",
            "object_count": 1,
            "chunk_count": 1,
            "wire_bytes": bootstrap_wire,
            "index_root": bootstrap_index,
            "schema_lineage_digest": sm3_b64url(schema),
        }
    )
    bootstrap_digest = sm3_b64url(manifest)
    registration = {
        "genesis_digest": genesis_digest(scope),
        "bootstrap_digest": bootstrap_digest,
        "boundary": "NEW_EMPTY",
        "index_root": bootstrap_index,
        "object_count": 1,
        "chunk_count": 1,
        "wire_bytes": bootstrap_wire,
    }
    objects = []
    for component, raw in (
        ("manifest", manifest),
        ("schema_lineage", schema),
        (snapshot_id, snapshot_raw),
    ):
        objects.append(
            (
                "typed_snapshot_metadata",
                object_id("typed_snapshot_metadata", "bootstrap", component, component),
                raw,
            )
        )
    ledger = load_strict_json(material["source"].material())
    source_digest = ledger["digest"]
    path = material["path_claims"]
    ids = [p["ag_grant_id"] for p in path]
    reserve = material["v1_bundle"]["ledger_changes"]["events"][0]
    reserve_digest = sm3_b64url(
        canonical_json_bytes(
            [
                [
                    i,
                    n["grant_id"],
                    n["amount_reserved_delta"],
                    n["amount_settled_delta"],
                    n["calls_reserved_delta"],
                    n["calls_settled_delta"],
                ]
                for i, n in enumerate(reserve["nodes"])
            ]
        )
    )
    receipt = material["receipt_claims"]
    facts = [
        (
            "BOOTSTRAP",
            {
                "boundary": "NEW_EMPTY",
                "root_grant_id": "grant-root",
                "snapshot_as_of": stamp,
                "schema_lineage_digest": sm3_b64url(schema),
                "index_root": bootstrap_index,
                "manifest_digest": bootstrap_digest,
                "object_count": 1,
                "chunk_count": 1,
                "wire_bytes": bootstrap_wire,
            },
        ),
        (
            "FIRST",
            {
                "root_grant_id": ids[0],
                "grant_id": ids[-1],
                "path_ids": ids,
                "intent_digest": receipt["intent_sm3"],
                "token_digest": sm3_b64url(c.token_jws),
                "proof_digest": sm3_b64url(c.proof_jws),
                "body_digest": sm3_b64url(c.request_raw),
                "context_digest": sm3_b64url(c.context_raw),
                "source_digest": source_digest,
                "source_material_digest": sm3_b64url(c.source_raw),
                "reserve_digest": reserve_digest,
                "quote_digest": sm3_b64url(c.quote_raw),
                "amount_fen": 70000,
                "calls": 1,
                "currency": "CNY",
                "introduced_grants": [
                    {
                        "grant_id": p["ag_grant_id"],
                        "parent_id": p["ag_parent_id"],
                        "root_id": p["ag_root_id"],
                        "depth": i,
                        "holder_client_id": p["client_id"],
                        "holder_kid": p["ag_cnf"]["kid"],
                        "grant_token_digest": sm3_b64url(c.ancestor_tokens[i]),
                        "source_material_digest": sm3_b64url(c.source_raw),
                        "amount_reserved": 0,
                        "amount_settled": 0,
                        "calls_reserved": 0,
                        "calls_settled": 0,
                    }
                    for i, p in enumerate(path)
                ],
            },
        ),
        (
            "TERMINAL",
            {
                "first_evidence_ref": evidence,
                "status": "SUCCEEDED",
                "action": "SETTLE",
                "result_digest": sm3_b64url(c.result_raw),
                "ledger_digest": sm3_b64url(c.ledger_raw),
                "pending_receipt_digest": sm3_b64url(canonical_json_bytes(receipt)),
                "receipt_id": receipt["receipt_id"],
                "owner_token": "synthetic-owner",
                "fencing_version": 1,
                "lease_expires_at": stamp,
                "path_ids": ids,
            },
        ),
        (
            "PUBLISH",
            {
                "receipt_id": receipt["receipt_id"],
                "receipt_jws_digest": sm3_b64url(c.receipt_jws),
                "signed_at": stamp,
            },
        ),
    ]
    original_objects, refs = receipt_objects(
        material, evidence_ref=evidence, operation_id=operation
    )
    objects.extend(original_objects)
    previous = genesis_digest(scope)
    records = []
    for seq, (kind, record_facts) in enumerate(facts, 1):
        suffix = (
            scope.stream_id
            if kind == "BOOTSTRAP"
            else receipt["receipt_id"]
            if kind == "PUBLISH"
            else operation
        )
        raw = canonical_json_bytes(
            {
                **scope_object(scope),
                "seq": seq,
                "record_id": kind + ":" + suffix,
                "kind": kind,
                "operation_id": None if kind == "BOOTSTRAP" else operation,
                "evidence_ref": None if kind == "BOOTSTRAP" else evidence,
                "previous_digest": previous,
                "recorded_at": stamp,
                "facts": record_facts,
            }
        )
        record = decode_journal_record(raw)
        previous = record.digest
        records.append(record)
        objects.append(("journal", object_id("journal", "journal", str(seq), "journal"), raw))
        components = {
            "FIRST": {
                "token",
                "proof",
                "request",
                "context",
                "source",
                "quote",
                "ancestor_token",
            },
            "TERMINAL": {"ledger", "result", "quote"},
            "PUBLISH": {"receipt"},
        }.get(kind, set())
        references = [r for r in refs if r["component"] in components]
        refraw = canonical_json_bytes(
            {
                "metadata_profile": "AG-TASK-REFS-1",
                "record_seq": seq,
                "operation_id": None if kind == "BOOTSTRAP" else operation,
                "evidence_ref": None if kind == "BOOTSTRAP" else evidence,
                "refs": references,
            }
        )
        objects.append(
            (
                "typed_snapshot_metadata",
                object_id("typed_snapshot_metadata", "journal", str(seq), "refs"),
                refraw,
            )
        )
    runtime = canonical_json_bytes(
        {
            "metadata_profile": "AG-TASK-RUNTIME-OBSERVATION-1",
            "operation_id": operation,
            "status": "SUCCEEDED",
            "receipt_status": "READY",
        }
    )
    objects.append(
        (
            "typed_snapshot_metadata",
            object_id("typed_snapshot_metadata", "runtime", operation, "runtime"),
            runtime,
        )
    )
    audit_key = generate_sm2_private_key()
    audit_trust = (
        CheckpointTrust(
            "audit-test-1",
            "AUDIT_SIGNER",
            serialize_sm2_public_key(audit_key.public_key()),
            1,
            None,
        ),
    )
    cp_jws = sign_checkpoint(
        {
            "profile": "GM-MVP-1",
            "checkpoint_version": "AG-CHECKPOINT-1",
            "checkpoint_id": "cp-task-4",
            **asdict(scope),
            "sequence": 4,
            "head_digest": previous,
            "previous_checkpoint_digest": None,
            "issued_at": stamp,
            "kid": "audit-test-1",
        },
        private_key=audit_key,
        key_id="audit-test-1",
    )
    cp["external_trust"] = {"scope": scope, "audit_keys": audit_trust}
    cp["external_pin"] = {
        "mode": mode,
        "checkpoint_jws": None if mode == "UNKNOWN" else cp_jws,
        "observed_at": NOW if mode == "LATEST_OBSERVATION" else None,
        "scope": asdict(scope),
    }
    cp["originals"] = (cp_jws,)
    cp["history_raw"] = canonical_json_bytes({"checkpoint_jws": cp_jws}) + b"\n"
    objects.append(
        (
            "checkpoint",
            object_id("checkpoint", "checkpoint", "cp-task-4", "checkpoint"),
            cp_jws.encode("ascii"),
        )
    )
    catalog = {
        "requests": [
            {
                "request_id": "req-001",
                "tenant_id": "tenant-001",
                "task_id": "task-001",
                "status": "APPROVED",
            }
        ],
        "documents": [],
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
                "tenant_id": "tenant-001",
                "request_id": "req-001",
            }
        ],
        "templates": [],
        "recipients": [],
    }
    trust_input = public_trust_input(material, cp, registration=registration, catalog=catalog)
    chunks = sum((len(raw) + 24575) // 24576 for _, _, raw in objects)
    header = task_header(
        scope,
        object_count=len(objects),
        chunk_count=chunks,
        journal_count=4,
        operation_count=1,
        head=previous,
    )
    header["bootstrap_digest"] = bootstrap_digest
    return {
        **material,
        **cp,
        "public_trust": trust_input,
        "registration": registration,
        "objects": tuple(objects),
        "records": tuple(records),
        "bundle_raw": encode_task(scope, objects, header=header),
        "header": header,
        "bootstrap_original_ids": {snapshot_id: ("typed_snapshot_metadata", snapshot_raw)},
        "expected_report": {
            "cryptographic_consistency": "VERIFIED",
            "anchored_prefix": 0 if mode == "UNKNOWN" else 4,
            "cutoff_sequence": 4,
            "tail": 4 if mode == "UNKNOWN" else 0,
            "freshness": {
                "UNKNOWN": "UNKNOWN",
                "MINIMUM": "MINIMUM_ONLY",
                "LATEST_OBSERVATION": "EXTERNAL_OBSERVATION_PROVIDED",
            }[mode],
            "history_boundary": "NEW_EMPTY",
            "current_auth": "UNKNOWN",
            "downstream_truth": "ATTESTED_NOT_INDEPENDENTLY_PROVEN",
        },
    }


def write_codec_boundary_fixture(path, scope, objects, *, counts, snapshot_id="1:1:"):
    """Stream actual codec originals and folds; no journal/business semantic PASS."""
    from agent_guard.contracts.encoding import load_strict_json

    header = {
        "frame_type": "HEADER",
        "manifest_version": "AG-TASK-EVIDENCE-2",
        "scope": asdict(scope),
        "cutoff_sequence": counts["journal"],
        "cutoff_head_digest": genesis_digest(scope),
        "snapshot_as_of": 1,
        "snapshot_id": snapshot_id,
        "history_boundary": "NEW_EMPTY",
        "bootstrap_digest": genesis_digest(scope),
        "object_count": counts["objects"],
        "chunk_count": counts["chunks"],
        "journal_count": counts["journal"],
        "operation_count": counts["operations"],
    }
    index = index_seed(scope)
    wire = wire_seed(scope)
    frames = size = 0
    with path.open("xb") as output:
        raw = canonical_json_bytes(header) + b"\n"
        output.write(raw)
        size += len(raw)
        wire = wire_fold(wire, frames, raw)
        frames += 1
        for kind, ident, material in objects:
            for raw in encode_object_chunks(kind, ident, material):
                frame = load_strict_json(raw[:-1])
                output.write(raw)
                size += len(raw)
                wire = wire_fold(wire, frames, raw)
                frames += 1
                if frame["chunk_index"] == frame["chunk_count"] - 1:
                    index = index_fold(index, frame)
        footer = {
            "frame_type": "FOOTER",
            "object_index_root": index,
            "wire_root": wire,
            "before_footer_frames": frames,
            "before_footer_wire_bytes": size,
        }
        raw = canonical_json_bytes(footer) + b"\n"
        output.write(raw)
        size += len(raw)
    return {"wire_bytes": size, "frames": frames + 1, "counts": counts}


def exact_wire_codec_objects(scope, target):
    """Find real bounded objects and a valid header string reaching the exact byte count."""
    import math

    # All identities have fixed length and remain strictly ordered.
    raw = b"x" * 65536
    full_frame_size = sum(
        len(frame) for frame in encode_object_chunks("request", "obj:000000", raw)
    )
    full_count = target // full_frame_size - 1
    full_bytes = full_count * full_frame_size
    for snapshot_length in range(1, 17):
        snapshot_id = "s" * snapshot_length
        low, high = 1, 131072
        while low <= high:
            length = (low + high) // 2
            tail_sizes = [min(length, 65536)]
            if length > 65536:
                tail_sizes.append(length - 65536)
            tail_bytes = sum(
                len(frame)
                for size in tail_sizes
                for frame in encode_object_chunks("request", "obj:000000", b"x" * size)
            )
            chunks = full_count * 3 + sum(math.ceil(size / 24576) for size in tail_sizes)
            header = {
                "frame_type": "HEADER",
                "manifest_version": "AG-TASK-EVIDENCE-2",
                "scope": asdict(scope),
                "cutoff_sequence": 0,
                "cutoff_head_digest": genesis_digest(scope),
                "snapshot_as_of": 1,
                "snapshot_id": snapshot_id,
                "history_boundary": "NEW_EMPTY",
                "bootstrap_digest": genesis_digest(scope),
                "object_count": full_count + len(tail_sizes),
                "chunk_count": chunks,
                "journal_count": 0,
                "operation_count": 0,
            }
            before = len(canonical_json_bytes(header)) + 1 + full_bytes + tail_bytes
            footer = {
                "frame_type": "FOOTER",
                "object_index_root": index_seed(scope),
                "wire_root": wire_seed(scope),
                "before_footer_frames": chunks + 1,
                "before_footer_wire_bytes": before,
            }
            total = before + len(canonical_json_bytes(footer)) + 1
            if total == target:

                def originals(tail_sizes=tail_sizes):
                    for number in range(full_count):
                        yield "request", f"obj:{number:06d}", raw
                    for number, size in enumerate(tail_sizes, full_count):
                        yield "request", f"obj:{number:06d}", b"x" * size

                return (
                    originals(),
                    {
                        "objects": full_count + len(tail_sizes),
                        "chunks": chunks,
                        "journal": 0,
                        "operations": 0,
                    },
                    snapshot_id,
                )
            if total < target:
                low = length + 1
            else:
                high = length - 1
    raise AssertionError("exact target needs another bounded last-object allocation")
