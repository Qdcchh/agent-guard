"""Bounded offline authentication of the complete task journal.

External registration, public keys and observation pins are the only trust
roots. Runtime rows are unsigned observations even when the journal is pinned.
No database, resolver, transport, environment or private key is consulted.
"""

from __future__ import annotations

import tempfile
from dataclasses import asdict, dataclass, fields
from datetime import datetime

import rfc8785

from agent_guard.audit.checkpoint import verify_checkpoint
from agent_guard.audit.contracts import (
    CheckpointTrust,
    JournalScope,
    RegistrationDescriptor,
    decode_journal_record,
    genesis_digest,
    identifier,
    integer,
)
from agent_guard.authorization.claims import validate_access_claims, validate_child
from agent_guard.authorization.proof import verify_ag_proof
from agent_guard.authorization.verifier import _validate_intent
from agent_guard.contracts.encoding import (
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.contracts.execution import ExecutionError, ToolId
from agent_guard.contracts.ledger_changes import (
    canonical_ledger_changes_bytes,
    load_ledger_changes,
)
from agent_guard.crypto.sm import (
    load_sm2_public_key,
    serialize_sm2_public_key,
    sm3_b64url,
    verify_compact_jws,
)
from agent_guard.evidence.receipt_semantics import (
    ReceiptComponents,
    ReceiptTrust,
    _verify_supplemental,
    verify_receipt_components,
)
from agent_guard.evidence.task_bundle import (
    CHUNK_BYTES,
    TaskBundleError,
    _external,
    encode_object_chunks,
    iter_frames,
    object_id,
)
from agent_guard.identity.resolver import RegisteredIdentity
from agent_guard.tools import catalog as catalog_module
from agent_guard.tools.params import parse_tool_params
from agent_guard.tools.policy import (
    check_operation_access,
    check_static_authorization,
    check_stored_snapshot,
    permission_snapshot_from_mapping,
)
from agent_guard.tools.results import (
    NotificationResult,
    OrderResult,
    RefusalResult,
    bind_result,
    parse_result,
)


def exact(value, names, label):
    if type(value) is not dict or set(value) != set(names):
        raise TaskBundleError("exact " + label + " required")
    return value


def array(value, maximum=200000):
    if type(value) is not list or len(value) > maximum:
        raise TaskBundleError("bounded array required")
    return value


def json_object(raw):
    value = load_strict_json(raw)
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        raise TaskBundleError("canonical original object required")
    return value


@dataclass(frozen=True)
class TaskTrust:
    scope: JournalScope
    receipt: ReceiptTrust
    audit_keys: tuple[CheckpointTrust, ...]
    registration: RegistrationDescriptor
    catalog: object


def load_public_trust(value):
    """Strictly decode independently supplied public trust; never bundle keys."""
    exact(
        value,
        (
            "version issuer as_keys gateway_keys holder_keys "
            "historical_registrations catalog audit_keys scope registration"
        ).split(),
        "trust",
    )
    if value["version"] != "AG-TASK-TRUST-1":
        raise TaskBundleError("unsupported external trust version")
    scope = JournalScope(**exact(value["scope"], [f.name for f in fields(JournalScope)], "scope"))
    maps = []
    for name in ("as_keys", "gateway_keys", "holder_keys"):
        keys = value[name]
        if type(keys) is not dict or not 1 <= len(keys) <= 200000:
            raise TaskBundleError("public key map required")
        maps.append({identifier(k): load_sm2_public_key(b64url_decode(v)) for k, v in keys.items()})
    registrations = {}
    for row in array(value["historical_registrations"]):
        canonical_json_bytes(row)
        exact(
            row,
            "tenant_id client_id did kid spki_der active role".split(),
            "historical registration",
        )
        if row["role"] != "HOLDER" or type(row["active"]) is not bool:
            raise TaskBundleError("historical HOLDER role required")
        for name in ("tenant_id", "client_id", "did", "kid"):
            identifier(row[name])
        identity = RegisteredIdentity(
            **{k: v for k, v in row.items() if k != "role" and k != "spki_der"},
            spki_der=b64url_decode(row["spki_der"]),
        )
        load_sm2_public_key(identity.spki_der)
        if (
            identity.kid in registrations
            or identity.kid not in maps[2]
            or serialize_sm2_public_key(maps[2][identity.kid]) != identity.spki_der
        ):
            raise TaskBundleError("duplicate or mismatched historical registration")
        registrations[identity.kid] = identity
    audit = []
    ranges = set()
    for row in array(value["audit_keys"]):
        canonical_json_bytes(row)
        exact(row, [f.name for f in fields(CheckpointTrust)], "audit trust")
        if row["role"] != "AUDIT_SIGNER":
            raise TaskBundleError("external AUDIT_SIGNER role required")
        identifier(row["kid"], maximum=128)
        integer(row["first_sequence"], minimum=1)
        if row["last_sequence"] is not None:
            integer(row["last_sequence"], minimum=row["first_sequence"])
        raw = b64url_decode(row["spki_der"])
        load_sm2_public_key(raw)
        key = (row["kid"], row["first_sequence"], row["last_sequence"])
        if key in ranges:
            raise TaskBundleError("duplicate audit range")
        ranges.add(key)
        audit.append(CheckpointTrust(**{**row, "spki_der": raw}))
    registration = exact(
        value["registration"],
        (
            "genesis_digest bootstrap_digest boundary index_root object_count "
            "chunk_count wire_bytes"
        ).split(),
        "registration",
    )
    if registration["genesis_digest"] != genesis_digest(scope) or registration["boundary"] not in {
        "NEW_EMPTY",
        "LEGACY_WITH_GAPS",
    }:
        raise TaskBundleError("external registration genesis or boundary mismatch")
    for name in ("object_count", "chunk_count", "wire_bytes"):
        integer(registration[name])
    catalog = exact(
        value["catalog"],
        "requests documents quotes deliveries templates recipients".split(),
        "catalog",
    )
    classes = {
        "requests": catalog_module.CatalogRequest,
        "documents": catalog_module.CatalogDocument,
        "quotes": catalog_module.CatalogQuote,
        "deliveries": catalog_module.CatalogDelivery,
        "templates": catalog_module.CatalogTemplate,
        "recipients": catalog_module.CatalogRecipient,
    }
    decoded = {}
    for name, cls in classes.items():
        rows, seen = [], set()
        for row in array(catalog[name]):
            canonical_json_bytes(row)
            exact(row, [f.name for f in fields(cls)], name)
            row = dict(row)
            if name == "quotes":
                lines = []
                for line in array(row["lines"], 256):
                    exact(
                        line,
                        [f.name for f in fields(catalog_module.CatalogQuoteLine)],
                        "quote line",
                    )
                    identifier(line["sku"])
                    integer(line["quantity"], minimum=1)
                    integer(line["unit_price_fen"])
                    lines.append(catalog_module.CatalogQuoteLine(**line))
                row["lines"] = tuple(lines)
            for key, item in row.items():
                if key != "lines" and type(item) is not str:
                    raise TaskBundleError("catalog text required")
            identity = tuple(row[k] for k in row if k.endswith("_id") or k == "quote_version")
            if identity in seen:
                raise TaskBundleError("duplicate catalog identity")
            seen.add(identity)
            rows.append(cls(**row))
        decoded[name] = rows
    return TaskTrust(
        scope,
        ReceiptTrust(value["issuer"], *maps, registrations),
        tuple(audit),
        RegistrationDescriptor(scope=scope, **registration),
        catalog_module.TrustedCatalog(**decoded),
    )


@dataclass(frozen=True)
class TaskVerificationReport:
    cryptographic_consistency: str
    anchored_prefix: int
    cutoff_sequence: int
    tail: int
    freshness: str
    history_boundary: str
    legacy_gap_ids: tuple[str, ...]
    grant_counters: tuple[dict, ...]
    anchored_execution_semantics: tuple[dict, ...]
    derivation: dict
    runtime_status_as_of: tuple[dict, ...]
    current_auth: str
    downstream_truth: str
    limitations: tuple[str, ...]
    input_sha256: dict


class _Objects:
    """Disk backing holds raw bytes; RAM only holds finite typed indices."""

    def __init__(self, stream):
        self.file = tempfile.TemporaryFile(dir="/tmp")
        self.index = {}
        self.used = set()
        payload = bytearray()
        try:
            for frame in iter_frames(stream):
                if frame["frame_type"] == "HEADER":
                    self.header = frame
                elif frame["frame_type"] == "OBJECT_CHUNK":
                    payload.extend(b64url_decode(frame["data"]))
                    if frame["chunk_index"] == frame["chunk_count"] - 1:
                        key = (frame["object_kind"], frame["object_id"])
                        self.index[key] = (self.file.tell(), len(payload))
                        self.file.write(payload)
                        payload.clear()
        except BaseException:
            self.file.close()
            raise

    def get(self, kind, ident):
        key = (kind, ident)
        if key not in self.index:
            raise TaskBundleError("missing typed original")
        self.used.add(key)
        offset, size = self.index[key]
        self.file.seek(offset)
        return self.file.read(size)

    def owned(self, kind, owner, ident, component, ordinal=0):
        return self.get(kind, object_id(kind, owner, ident, component, ordinal))

    def record(self, seq):
        return decode_journal_record(self.owned("journal", "journal", str(seq), "journal"))

    def references(self, seq):
        return _references(self, self.record(seq))


def _bootstrap(objects, trust):
    scope = [trust.scope.gateway_id, trust.scope.tenant_id, trust.scope.task_id]
    manifest_raw = objects.owned("typed_snapshot_metadata", "bootstrap", "manifest", "manifest")
    manifest = exact(
        json_object(manifest_raw),
        (
            "profile scope root_grant_id snapshot_as_of origin object_count "
            "chunk_count wire_bytes index_root schema_lineage_digest"
        ).split(),
        "bootstrap manifest",
    )
    lineage = objects.owned(
        "typed_snapshot_metadata", "bootstrap", "schema_lineage", "schema_lineage"
    )
    array(load_strict_json(lineage))
    if (
        sm3_b64url(lineage) != manifest["schema_lineage_digest"]
        or sm3_b64url(manifest_raw) != trust.registration.bootstrap_digest
        or manifest["scope"] != scope
        or manifest["profile"] != "AG-BOOTSTRAP-1"
        or manifest["origin"]
        != ("FROM_EMPTY_TASK" if trust.registration.boundary == "NEW_EMPTY" else "LEGACY_WITH_GAPS")
    ):
        raise TaskBundleError("external bootstrap authentication mismatch")
    originals = {}
    counters, gaps, bootstrap_ops = {}, set(), {}
    baseline_grants, baseline_tokens = {}, {}
    for kind, ident in objects.index:
        if kind != "typed_snapshot_metadata":
            continue
        offset, size = objects.index[(kind, ident)]
        objects.file.seek(offset)
        raw = objects.file.read(size)
        value = load_strict_json(raw)
        if type(value) is not dict or set(value) != {"table", "row_index", "columns"}:
            continue
        table = identifier(value["table"])
        integer(value["row_index"])
        original_id = table + ":" + str(value["row_index"])
        if ident != object_id(kind, "bootstrap", original_id, original_id):
            raise TaskBundleError("bootstrap typed row identity mismatch")
        if type(value["columns"]) is not dict:
            raise TaskBundleError("bootstrap columns required")
        objects.used.add((kind, ident))
        originals[(kind, original_id)] = ident
        columns = value["columns"]
        for name, item in columns.items():
            if type(item) is dict and set(item) == {"kind", "object_id", "digest"}:
                original = original_id + ":" + name
                if item["object_id"] != original:
                    raise TaskBundleError("bootstrap original reference identity mismatch")
                component = objects.owned(item["kind"], "bootstrap", original, original)
                if sm3_b64url(component) != item["digest"]:
                    raise TaskBundleError("bootstrap original digest mismatch")
                originals[(item["kind"], original)] = object_id(
                    item["kind"], "bootstrap", original, original
                )
            elif type(item) is dict and item != {"empty_bytes": True}:
                raise TaskBundleError("unknown bootstrap column descriptor")
        if table == "ag_grants":
            grant = identifier(columns["grant_id"])
            if grant in counters:
                raise TaskBundleError("duplicate bootstrap grant")
            baseline_grants[grant] = columns
            counters[grant] = [
                integer(columns[name])
                for name in (
                    "amount_reserved",
                    "amount_settled",
                    "calls_reserved",
                    "calls_settled",
                )
            ]
        if table == "ag_grant_tokens":
            baseline_tokens[columns["grant_id"]] = columns
        if table == "ag_operations":
            op = identifier(columns["operation_id"])
            bootstrap_ops[op] = tuple(
                columns[name]
                for name in (
                    "tenant_id",
                    "task_id",
                    "grant_id",
                    "holder_client_id",
                    "holder_kid",
                )
            )
            if trust.registration.boundary == "NEW_EMPTY":
                raise TaskBundleError("NEW_EMPTY contains historical operation")
            gaps.add(op)
    parsed_baseline = {}
    for grant, row in baseline_grants.items():
        token_row = baseline_tokens.get(grant)
        if token_row is None:
            raise TaskBundleError("baseline grant lacks original signed token")
        token_ref = token_row["token_jws"]
        token = objects.owned("token", "bootstrap", token_ref["object_id"], token_ref["object_id"])
        raw_claims = verify_compact_jws(
            token.decode("ascii"),
            expected_type="ag-at+jwt",
            trusted_keys=trust.receipt.as_keys,
        )
        claims = validate_access_claims(
            raw_claims,
            issuer=trust.receipt.issuer,
            now=max(raw_claims["iat"], raw_claims["nbf"]),
        )
        parsed_baseline[grant] = claims
        binding = {
            "grant_id": raw_claims["ag_grant_id"],
            "parent_grant_id": raw_claims["ag_parent_id"],
            "root_grant_id": raw_claims["ag_root_id"],
            "tenant_id": raw_claims["ag_tenant_id"],
            "task_id": raw_claims["ag_task_id"],
            "subject": raw_claims["sub"],
            "holder_client_id": raw_claims["client_id"],
            "holder_kid": raw_claims["ag_cnf"]["kid"],
            "amount_limit": raw_claims["ag_limits"]["amount_fen"],
            "call_limit": raw_claims["ag_limits"]["calls"],
            "depth": 2 - raw_claims["ag_delegation_remaining"],
        }
        if (
            any(row.get(k) != v for k, v in binding.items())
            or (row["tenant_id"], row["task_id"]) != (trust.scope.tenant_id, trust.scope.task_id)
            or _utc(row["not_before"]) != raw_claims["nbf"]
            or _utc(row["expires_at"]) != raw_claims["exp"]
            or token_row["token_sm3"] != sm3_b64url(token)
            or token_row["scope"] != raw_claims["scope"]
            or token_row["holder_spki_sm3"] != raw_claims["ag_cnf"]["spki_sm3"]
        ):
            raise TaskBundleError("baseline grant signed binding mismatch")
        reg = trust.receipt.historical_registrations.get(row["holder_kid"])
        if reg is None or (reg.tenant_id, reg.client_id, reg.did, reg.spki_sm3) != (
            row["tenant_id"],
            row["holder_client_id"],
            claims.actors[0],
            raw_claims["ag_cnf"]["spki_sm3"],
        ):
            raise TaskBundleError("baseline historical holder mismatch")
        for name, claim_field in (
            ("constraints_json", "ag_constraints"),
            ("actor_json", "act"),
        ):
            reference = token_row[name]
            raw = objects.owned(
                reference["kind"],
                "bootstrap",
                reference["object_id"],
                reference["object_id"],
            )
            if raw != canonical_json_bytes(raw_claims[claim_field]):
                raise TaskBundleError("baseline token source mismatch")
        if (
            counters[grant][0] + counters[grant][1] > row["amount_limit"]
            or counters[grant][2] + counters[grant][3] > row["call_limit"]
        ):
            raise TaskBundleError("baseline ancestor budget exceeded")
        if trust.registration.boundary == "LEGACY_WITH_GAPS" and any(counters[grant]):
            gaps.add(grant)
    for claims in parsed_baseline.values():
        parent = claims.raw["ag_parent_id"]
        if parent is not None:
            if parent not in parsed_baseline:
                raise TaskBundleError("missing bootstrap ancestor")
            validate_child(parsed_baseline[parent], claims)
    index = sm3_b64url(canonical_json_bytes({"profile": "AG-BOOTSTRAP-INDEX-1", "scope": scope}))
    chunks = wire = 0
    for (kind, ident), export_id in sorted(originals.items()):
        raw = objects.get(kind, export_id)
        count = (len(raw) + CHUNK_BYTES - 1) // CHUNK_BYTES
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
        chunks += count
        wire += sum(len(f) for f in encode_object_chunks(kind, ident, raw))
    if not counters or manifest["root_grant_id"] not in counters:
        raise TaskBundleError("bootstrap requires real task root and grant counters")
    if trust.registration.boundary == "NEW_EMPTY" and any(any(row) for row in counters.values()):
        raise TaskBundleError("NEW_EMPTY nonzero baseline")
    for name, computed in {
        "object_count": len(originals),
        "chunk_count": chunks,
        "wire_bytes": wire,
        "index_root": index,
    }.items():
        if manifest[name] != computed or getattr(trust.registration, name) != computed:
            raise TaskBundleError("external bootstrap index/count mismatch")
    grants = {
        grant: (
            sm3_b64url(canonical_json_bytes(claims.raw)),
            claims.raw["ag_limits"]["amount_fen"],
            claims.raw["ag_limits"]["calls"],
        )
        for grant, claims in parsed_baseline.items()
    }
    return manifest, counters, gaps, bootstrap_ops, grants


def _references(objects, record):
    value = exact(
        json_object(objects.owned("typed_snapshot_metadata", "journal", str(record.seq), "refs")),
        "metadata_profile record_seq operation_id evidence_ref refs".split(),
        "typed refs",
    )
    integer(value["record_seq"], minimum=1)
    if value["metadata_profile"] != "AG-TASK-REFS-1" or (
        value["record_seq"],
        value["operation_id"],
        value["evidence_ref"],
    ) != (record.seq, record.operation_id, record.evidence_ref):
        raise TaskBundleError("typed refs journal relation mismatch")
    result = {}
    for ref in array(value["refs"], 16):
        exact(ref, "component object_kind object_id".split(), "component reference")
        component, kind = ref["component"], ref["object_kind"]
        expected_kind = {
            "accept_result_metadata": "typed_snapshot_metadata",
            "pending_receipt_metadata": "typed_snapshot_metadata",
            "internal_ledger": "ledger",
        }.get(component, component)
        if (
            component
            not in {
                "token",
                "proof",
                "request",
                "context",
                "source",
                "quote",
                "ledger",
                "result",
                "receipt",
                "ancestor_token",
                "accept_result_metadata",
                "pending_receipt_metadata",
                "internal_ledger",
            }
            or kind != expected_kind
        ):
            raise TaskBundleError("unknown or mistyped component ref")
        ordinal = len(result.get(component, []))
        if ordinal and component != "ancestor_token" or ordinal >= 3:
            raise TaskBundleError("duplicate component ref")
        if component in {"token", "proof", "request"}:
            owner, ident = "evidence", record.evidence_ref
        elif component in {
            "context",
            "source",
            "ancestor_token",
            "accept_result_metadata",
        }:
            owner, ident = "journal", str(record.seq)
        elif component in {
            "quote",
            "ledger",
            "result",
            "receipt",
            "pending_receipt_metadata",
            "internal_ledger",
        }:
            owner, ident = "operation", record.operation_id
        else:
            raise TaskBundleError("unsupported journal component relation")
        if ref["object_id"] != object_id(kind, owner, ident, component, ordinal):
            raise TaskBundleError("typed original owner mismatch")
        result.setdefault(component, []).append(objects.get(kind, ref["object_id"]))
    return result


def _one(refs, name, optional=False):
    if name not in refs:
        if optional:
            return None
        raise TaskBundleError("missing required " + name)
    return refs[name][0]


def _authorization(refs, record, trust, amount=None):
    facts = load_strict_json(record.facts_bytes)
    for component, fact in {
        "token": "token_digest",
        "proof": "proof_digest",
        "request": "body_digest",
        "context": "context_digest",
        "source": "source_material_digest",
    }.items():
        if sm3_b64url(_one(refs, component)) != facts[fact]:
            raise TaskBundleError("journal original authorization digest mismatch")
    token, proof = (
        _one(refs, "token").decode("ascii"),
        _one(refs, "proof").decode("ascii"),
    )
    ancestors = refs.get("ancestor_token", [])
    if not ancestors or ancestors[-1] != token.encode():
        raise TaskBundleError("complete historical ancestor path required")
    signed = [
        verify_compact_jws(
            raw.decode("ascii"),
            expected_type="ag-at+jwt",
            trusted_keys=trust.receipt.as_keys,
        )
        for raw in ancestors
    ]
    proof_claims = verify_compact_jws(
        proof, expected_type="ag-pop+jwt", trusted_keys=trust.receipt.holder_keys
    )
    now = int(datetime.fromisoformat(record.recorded_at.replace("Z", "+00:00")).timestamp())
    previous, path = None, []
    for raw in signed:
        claims = validate_access_claims(raw, issuer=trust.receipt.issuer, now=now)
        registration = trust.receipt.historical_registrations.get(raw["ag_cnf"]["kid"])
        if (
            registration is None
            or not registration.active
            or (
                registration.tenant_id,
                registration.client_id,
                registration.did,
                registration.spki_sm3,
            )
            != (
                raw["ag_tenant_id"],
                raw["client_id"],
                claims.actors[0],
                raw["ag_cnf"]["spki_sm3"],
            )
        ):
            raise TaskBundleError("historical holder binding mismatch")
        if previous is not None:
            validate_child(previous, claims)
        previous = claims
        path.append(raw)
    leaf = path[-1]
    ids = [p["ag_grant_id"] for p in path]
    if (
        len(set(ids)) != len(ids)
        or len(ids) != 3 - leaf["ag_delegation_remaining"]
        or (leaf["ag_tenant_id"], leaf["ag_task_id"])
        != (trust.scope.tenant_id, trust.scope.task_id)
    ):
        raise TaskBundleError("historical path or task scope mismatch")
    query = record.kind == "QUERY"
    request = load_strict_json(_one(refs, "request"))
    if query:
        exact(request, "profile task_id operation_id".split(), "query request")
        if request != {
            "profile": "GM-MVP-1",
            "task_id": trust.scope.task_id,
            "operation_id": record.operation_id,
        }:
            raise TaskBundleError("query operation mismatch")
        endpoint, purpose = (
            "https://gateway.agent-guard.test/v1/operations/query",
            "result-read",
        )
        expected = {
            "subject": leaf["sub"],
            "tenant_id": leaf["ag_tenant_id"],
            "task_id": leaf["ag_task_id"],
            "grant_id": leaf["ag_grant_id"],
            "root_id": leaf["ag_root_id"],
            "holder_client_id": leaf["client_id"],
            "holder_kid": leaf["ag_cnf"]["kid"],
            "operation_id": record.operation_id,
            "token_exp": leaf["exp"],
            "token_digest": facts["token_digest"],
            "proof_digest": facts["proof_digest"],
            "proof_jti": proof_claims["jti"],
            "proof_iat": proof_claims["iat"],
            "proof_exp": proof_claims["exp"],
            "profile": "GM-MVP-1",
            "purpose": purpose,
            "endpoint": endpoint,
            "method": "POST",
        }
        if _one(refs, "context") != canonical_json_bytes(expected):
            raise TaskBundleError("historical query context mismatch")
    else:
        request, normalized, _ = _validate_intent(_one(refs, "request"), previous)
        if sm3_b64url(normalized) != facts["intent_digest"]:
            raise TaskBundleError("historical normalized intent mismatch")
        endpoint, purpose = "https://gateway.agent-guard.test/v1/invocations", "invoke"
    verify_ag_proof(
        proof,
        trusted_keys={leaf["ag_cnf"]["kid"]: trust.receipt.holder_keys[leaf["ag_cnf"]["kid"]]},
        client_id=leaf["client_id"],
        purpose=purpose,
        endpoint=endpoint,
        token=token,
        body=request,
        now=now,
    )
    source = json_object(_one(refs, "source"))
    if source.get("digest") != facts["source_digest"]:
        raise TaskBundleError("source chain digest mismatch")
    # Shared source binding checks every historical signed row and snapshot.
    # The supplemental helper needs an invocation-shaped object only for its
    # context/quote branches; neither is supplied on the source-only call.
    shell = type(
        "SourceOriginal",
        (),
        {
            "source_raw": _one(refs, "source"),
            "context_raw": None,
            "quote_raw": None,
            "ancestor_tokens": tuple(ancestors),
        },
    )()
    _verify_supplemental(shell, path, {}, proof_claims, {})
    if not query:
        shell.context_raw = _one(refs, "context")
        shell.source_raw = None
        _verify_supplemental(
            shell,
            path,
            request,
            proof_claims,
            {
                "token_sm3": facts["token_digest"],
                "proof_sm3": facts["proof_digest"],
                "intent_sm3": facts["intent_digest"],
            },
        )
        check_static_authorization(
            permission_snapshot_from_mapping(source["snapshot"]),
            grant_id=ids[-1],
            root_id=ids[0],
            tenant_id=trust.scope.tenant_id,
            task_id=trust.scope.task_id,
            subject=leaf["sub"],
            tool_id=ToolId(request["tool_id"]),
            params=parse_tool_params(request["tool_id"], canonical_json_bytes(request["params"])),
            db_path=tuple(ids),
        )
        if amount is not None:
            check_stored_snapshot(
                tool_id=ToolId(request["tool_id"]),
                params=parse_tool_params(
                    request["tool_id"], canonical_json_bytes(request["params"])
                ),
                amount_fen=amount,
                quote_snapshot_bytes=_one(refs, "quote", True),
            )
    return path, request, proof_claims


def _verify(stream, trust, pin):
    scope, _ = _external(trust, pin)
    objects = _Objects(stream)
    try:
        header = objects.header
        if (
            header["scope"] != asdict(scope)
            or header["history_boundary"] != trust.registration.boundary
            or header["bootstrap_digest"] != trust.registration.bootstrap_digest
        ):
            raise TaskBundleError("bundle scope/bootstrap does not match external registration")
        manifest, counters, gaps, bootstrap_ops, grants = _bootstrap(objects, trust)
        records, heads = {}, {0: genesis_digest(scope)}
        for kind, ident in objects.index:
            if kind == "journal":
                record = decode_journal_record(objects.get(kind, ident))
                if (
                    ident != object_id(kind, "journal", str(record.seq), "journal")
                    or record.scope != scope
                    or record.seq in records
                ):
                    raise TaskBundleError("journal typed identity or scope mismatch")
                records[record.seq] = (record.kind, record.operation_id, record.digest)
        previous = genesis_digest(scope)
        operations, proof_ids = {}, set()
        for seq in range(1, header["cutoff_sequence"] + 1):
            if seq not in records:
                raise TaskBundleError("missing journal sequence")
            record = objects.record(seq)
            if record.previous_digest != previous:
                raise TaskBundleError("journal chain mismatch")
            previous = heads[seq] = record.digest
            facts = load_strict_json(record.facts_bytes)
            refs = _references(objects, record)
            if record.kind == "BOOTSTRAP":
                if refs or facts != {
                    "boundary": trust.registration.boundary,
                    "root_grant_id": manifest["root_grant_id"],
                    "snapshot_as_of": manifest["snapshot_as_of"],
                    "schema_lineage_digest": manifest["schema_lineage_digest"],
                    "index_root": manifest["index_root"],
                    "manifest_digest": trust.registration.bootstrap_digest,
                    "object_count": manifest["object_count"],
                    "chunk_count": manifest["chunk_count"],
                    "wire_bytes": manifest["wire_bytes"],
                }:
                    raise TaskBundleError("bootstrap journal mismatch")
                continue
            op = record.operation_id
            if record.kind in {"FIRST", "RETRY", "QUERY"}:
                allowed = {
                    "token",
                    "proof",
                    "request",
                    "context",
                    "source",
                    "ancestor_token",
                } | (
                    {"quote"}
                    if record.kind == "FIRST"
                    else {"quote", "accept_result_metadata"}
                    if record.kind == "RETRY" and facts["response_kind"] == "ACCEPT_RESULT"
                    else set()
                )
                if record.kind == "QUERY" and facts["status"] in {
                    "SUCCEEDED",
                    "FAILED",
                }:
                    allowed.add("result")
                if record.kind in {"RETRY", "QUERY"} and facts["receipt_status"] == "READY":
                    allowed.add("receipt")
                if set(refs) - allowed:
                    raise TaskBundleError("unexpected authorization originals")
                path, request, proof = _authorization(refs, record, trust, facts.get("amount_fen"))
                proof_id = (
                    path[-1]["ag_cnf"]["kid"],
                    proof["purpose"],
                    proof["htu"],
                    proof["jti"],
                )
                if proof_id in proof_ids:
                    raise TaskBundleError("historical proof replay")
                proof_ids.add(proof_id)
                for claim in path:
                    grant = claim["ag_grant_id"]
                    if grant in grants and grants[grant][0] != sm3_b64url(
                        canonical_json_bytes(claim)
                    ):
                        raise TaskBundleError("grant identity changed in history")
                    grants[grant] = (
                        sm3_b64url(canonical_json_bytes(claim)),
                        claim["ag_limits"]["amount_fen"],
                        claim["ag_limits"]["calls"],
                    )
                ids = [p["ag_grant_id"] for p in path]
                if record.kind == "FIRST":
                    if (
                        op in operations
                        or op in bootstrap_ops
                        or facts["path_ids"] != ids
                        or facts["root_grant_id"] != ids[0]
                        or facts["grant_id"] != ids[-1]
                        or facts["calls"] != 1
                    ):
                        raise TaskBundleError("FIRST identity or reserve path mismatch")
                    leaf = path[-1]
                    parse_tool_params(request["tool_id"], canonical_json_bytes(request["params"]))
                    # Historical signatures authorize the original params;
                    # mutable catalog approval/price rows are not re-run as
                    # current authorization. Known immutable associations
                    # may not contradict the independently supplied scope.
                    request_id = request["params"].get("request_id")
                    catalog_request = trust.catalog.get_request(request_id) if request_id else None
                    if catalog_request is not None and (
                        catalog_request.tenant_id,
                        catalog_request.task_id,
                    ) != (scope.tenant_id, scope.task_id):
                        raise TaskBundleError("historical catalog task association mismatch")
                    if request["tool_id"] == "procurement.document.read":
                        doc = trust.catalog.get_document(request["params"]["document_id"])
                        if doc is not None and doc.request_id != request_id:
                            raise TaskBundleError("historical document request mismatch")
                    if request["tool_id"] == "procurement.order.create":
                        delivery = trust.catalog.get_delivery(request["params"]["delivery_id"])
                        if delivery is not None and (
                            delivery.tenant_id,
                            delivery.request_id,
                        ) != (
                            scope.tenant_id,
                            request_id,
                        ):
                            raise TaskBundleError("historical delivery association mismatch")
                    if request["tool_id"] == "notification.template.send":
                        referenced = request["params"]["operation_id"]
                        binding = (
                            operations[referenced]["binding"]
                            if referenced in operations
                            else bootstrap_ops.get(referenced)
                        )
                        check_operation_access(
                            binding,
                            tenant_id=scope.tenant_id,
                            task_id=scope.task_id,
                            grant_id=ids[-1],
                            holder_client_id=leaf["client_id"],
                            holder_kid=leaf["ag_cnf"]["kid"],
                        )
                    introduced = {row["grant_id"]: row for row in facts["introduced_grants"]}
                    if len(introduced) != len(facts["introduced_grants"]):
                        raise TaskBundleError("duplicate introduced grant")
                    for depth, claim in enumerate(path):
                        grant = claim["ag_grant_id"]
                        if grant not in counters:
                            expected = {
                                "grant_id": grant,
                                "parent_id": claim["ag_parent_id"],
                                "root_id": claim["ag_root_id"],
                                "depth": depth,
                                "holder_client_id": claim["client_id"],
                                "holder_kid": claim["ag_cnf"]["kid"],
                                "grant_token_digest": sm3_b64url(refs["ancestor_token"][depth]),
                                "source_material_digest": facts["source_material_digest"],
                                "amount_reserved": 0,
                                "amount_settled": 0,
                                "calls_reserved": 0,
                                "calls_settled": 0,
                            }
                            if introduced.pop(grant, None) != expected:
                                raise TaskBundleError("missing authenticated introduced grant")
                            counters[grant] = [0, 0, 0, 0]
                        counters[grant][0] += facts["amount_fen"]
                        counters[grant][2] += 1
                    if introduced:
                        raise TaskBundleError("introduced preexisting or foreign grant")
                    reserve = [
                        [i, grant, facts["amount_fen"], 0, 1, 0] for i, grant in enumerate(ids)
                    ]
                    if facts["reserve_digest"] != sm3_b64url(
                        canonical_json_bytes(reserve)
                    ) or facts["quote_digest"] != (
                        sm3_b64url(_one(refs, "quote")) if "quote" in refs else None
                    ):
                        raise TaskBundleError("FIRST reserve or quote digest mismatch")
                    operations[op] = {
                        "operation_id": op,
                        "first": seq,
                        "first_ref": record.evidence_ref,
                        "path_ids": ids,
                        "intent_digest": facts["intent_digest"],
                        "binding": (
                            scope.tenant_id,
                            scope.task_id,
                            ids[-1],
                            path[-1]["client_id"],
                            path[-1]["ag_cnf"]["kid"],
                        ),
                        "status": "ACCEPTED_NONTERMINAL",
                        "receipt_seq": None,
                        "terminal": None,
                        "sequence": seq,
                    }
                else:
                    if op not in operations:
                        if op in gaps:
                            continue
                        raise TaskBundleError("retry/query without complete FIRST")
                    original = operations[op]
                    first_record = objects.record(original["first"])
                    first_facts = load_strict_json(first_record.facts_bytes)
                    first_refs = objects.references(original["first"])
                    if (
                        facts["first_evidence_ref"] != original["first_ref"]
                        or ids != first_facts["path_ids"]
                    ):
                        raise TaskBundleError("retry/query original path mismatch")
                    original_request = load_strict_json(_one(first_refs, "request"))
                    if record.kind == "RETRY" and (
                        request != original_request
                        or facts["intent_digest"] != first_facts["intent_digest"]
                    ):
                        raise TaskBundleError("retry changed accepted intent")
                    if record.kind == "QUERY":
                        leaf = path[-1]
                        check_static_authorization(
                            permission_snapshot_from_mapping(
                                json_object(_one(refs, "source"))["snapshot"]
                            ),
                            grant_id=ids[-1],
                            root_id=ids[0],
                            tenant_id=scope.tenant_id,
                            task_id=scope.task_id,
                            subject=leaf["sub"],
                            tool_id=ToolId(original_request["tool_id"]),
                            params=parse_tool_params(
                                original_request["tool_id"],
                                canonical_json_bytes(original_request["params"]),
                            ),
                            db_path=tuple(ids),
                        )
                    _response(objects, facts, refs, record, original)
            elif record.kind == "TERMINAL":
                if op not in operations:
                    if op in gaps:
                        continue
                    raise TaskBundleError("terminal without FIRST")
                original = operations[op]
                first = load_strict_json(objects.record(original["first"]).facts_bytes)
                if (
                    original["terminal"] is not None
                    or set(refs)
                    - {
                        "ledger",
                        "result",
                        "quote",
                        "pending_receipt_metadata",
                        "internal_ledger",
                    }
                    or facts["first_evidence_ref"] != original["first_ref"]
                    or facts["path_ids"] != first["path_ids"]
                    or facts["action"]
                    != ("SETTLE" if facts["status"] == "SUCCEEDED" else "RELEASE")
                ):
                    raise TaskBundleError("terminal transition mismatch")
                ledger_raw, result_raw = _one(refs, "ledger"), _one(refs, "result")
                ledger = load_ledger_changes(ledger_raw)
                if canonical_ledger_changes_bytes(ledger) != ledger_raw:
                    raise TaskBundleError("canonical public B ledger required")
                if (
                    facts["ledger_digest"] != sm3_b64url(ledger_raw)
                    or facts["result_digest"] != sm3_b64url(result_raw)
                    or ledger["operation_id"] != op
                    or len(ledger["events"]) != 2
                ):
                    raise TaskBundleError("terminal original digest mismatch")
                for i, event in enumerate(ledger["events"]):
                    if event["phase"] != ("RESERVE" if i == 0 else facts["action"]) or len(
                        event["nodes"]
                    ) != len(first["path_ids"]):
                        raise TaskBundleError("terminal ledger path mismatch")
                    for grant, delta in zip(first["path_ids"], event["nodes"], strict=True):
                        amount = first["amount_fen"]
                        expected = {
                            "grant_id": grant,
                            "amount_reserved_delta": amount if i == 0 else -amount,
                            "amount_settled_delta": amount
                            if i and facts["action"] == "SETTLE"
                            else 0,
                            "calls_reserved_delta": 1 if i == 0 else -1,
                            "calls_settled_delta": 1 if i and facts["action"] == "SETTLE" else 0,
                        }
                        if delta != expected:
                            raise TaskBundleError("terminal ancestor delta mismatch")
                        if i:
                            for n, name in enumerate(
                                (
                                    "amount_reserved_delta",
                                    "amount_settled_delta",
                                    "calls_reserved_delta",
                                    "calls_settled_delta",
                                )
                            ):
                                counters[grant][n] += delta[name]
                _pending(objects, refs, record, original, trust)
                original.update(terminal=seq, status=facts["status"], sequence=seq)
            elif record.kind == "PUBLISH":
                if op not in operations:
                    if op in gaps:
                        continue
                    raise TaskBundleError("publication without FIRST")
                original = operations[op]
                if (
                    original["terminal"] is None
                    or original["receipt_seq"] is not None
                    or set(refs) != {"receipt"}
                ):
                    raise TaskBundleError("publication transition mismatch")
                receipt = _one(refs, "receipt")
                terminal = load_strict_json(objects.record(original["terminal"]).facts_bytes)
                if (
                    facts["receipt_jws_digest"] != sm3_b64url(receipt)
                    or facts["receipt_id"] != terminal["receipt_id"]
                ):
                    raise TaskBundleError("publication original mismatch")
                first_refs, terminal_refs = (
                    objects.references(original["first"]),
                    objects.references(original["terminal"]),
                )
                pending = json_object(_one(terminal_refs, "pending_receipt_metadata"))
                claims = verify_compact_jws(
                    receipt.decode("ascii"),
                    expected_type="ag-receipt+jwt",
                    trusted_keys=trust.receipt.gateway_keys,
                )
                if (
                    claims.get("iat") != _utc(pending["created_at"])
                    or claims.get("receipt_id") != pending["receipt_id"]
                ):
                    raise TaskBundleError(
                        "publication differs from immutable pending time/identity"
                    )
                verified = verify_receipt_components(
                    ReceiptComponents(
                        _one(first_refs, "token"),
                        _one(first_refs, "proof"),
                        tuple(first_refs["ancestor_token"]),
                        _one(first_refs, "request"),
                        _canonical_result(objects, original, terminal_refs, terminal["status"]),
                        _one(terminal_refs, "ledger"),
                        receipt,
                        _one(first_refs, "quote", True),
                        _one(first_refs, "context"),
                        _one(first_refs, "source"),
                    ),
                    trust.receipt,
                )
                if (verified.operation_id, verified.status) != (op, original["status"]):
                    raise TaskBundleError("signed receipt terminal mismatch")
                original.update(receipt_seq=seq, sequence=seq)
            for grant in operations.get(op, {}).get("path_ids", []):
                row = counters[grant]
                for value in row:
                    integer(value)
                if grant in grants and (
                    row[0] + row[1] > grants[grant][1] or row[2] + row[3] > grants[grant][2]
                ):
                    raise TaskBundleError("cumulative ancestor budget exceeded")
        if not records or records[1][0] != "BOOTSTRAP" or previous != header["cutoff_head_digest"]:
            raise TaskBundleError("complete journal boundary/head mismatch")
        checkpoints = []
        for kind, ident in objects.index:
            if kind == "checkpoint":
                raw = objects.get(kind, ident).decode("ascii")
                checkpoint = verify_checkpoint(raw, trust=trust.audit_keys, expected_scope=scope)
                if (
                    ident
                    != object_id(
                        kind,
                        "checkpoint",
                        checkpoint.claims.checkpoint_id,
                        "checkpoint",
                    )
                    or heads.get(checkpoint.claims.sequence) != checkpoint.claims.head_digest
                ):
                    raise TaskBundleError("checkpoint journal head or typed identity mismatch")
                checkpoints.append(
                    (
                        checkpoint.claims.sequence,
                        checkpoint.claims.checkpoint_id,
                        checkpoint.claims.previous_checkpoint_digest,
                        checkpoint.jws_digest,
                        ident,
                    )
                )
        checkpoints.sort()
        previous_cp, ids, cp_seq = None, set(), 0
        for sequence, checkpoint_id, previous_digest, jws_digest, _ident in checkpoints:
            if previous_digest != previous_cp or checkpoint_id in ids or sequence <= cp_seq:
                raise TaskBundleError("complete original checkpoint chain required")
            previous_cp, cp_seq = jws_digest, sequence
            ids.add(checkpoint_id)
        if pin["mode"] != "UNKNOWN":
            if (
                not checkpoints
                or objects.get("checkpoint", checkpoints[-1][4]).decode("ascii")
                != pin["checkpoint_jws"]
            ):
                raise TaskBundleError("original terminal checkpoint must equal external pin")
            anchored = checkpoints[-1][0]
        else:
            anchored = 0
        runtime = []
        for kind, ident in objects.index:
            if kind != "typed_snapshot_metadata" or (kind, ident) in objects.used:
                continue
            value = json_object(objects.get(kind, ident))
            exact(
                value,
                "metadata_profile operation_id status receipt_status".split(),
                "runtime observation",
            )
            if (
                value["metadata_profile"] != "AG-TASK-RUNTIME-OBSERVATION-1"
                or ident != object_id(kind, "runtime", value["operation_id"], "runtime")
                or value["operation_id"] not in operations.keys() | bootstrap_ops
            ):
                raise TaskBundleError("unowned runtime observation")
            runtime.append(
                {
                    **{k: value[k] for k in ("operation_id", "status", "receipt_status")},
                    "assurance": "UNANCHORED_AS_OF_DB_OBSERVATION",
                }
            )
        if {
            row["operation_id"] for row in runtime
        } != operations.keys() | bootstrap_ops or objects.used != objects.index.keys():
            raise TaskBundleError("missing runtime or orphan original object")
        semantics = []
        prefixes = {}
        for seq, row in sorted(records.items()):
            if row[1] is not None and seq <= anchored:
                prefixes.setdefault(row[1], []).append((seq, row))
        for op in sorted(operations):
            prefix = prefixes.get(op, [])
            if not prefix:
                continue
            terminal = next((seq for seq, row in prefix if row[0] == "TERMINAL"), None)
            # Fold per-record derivation, avoiding a task-sized JSON array.
            derived = sm3_b64url(
                canonical_json_bytes({"profile": "AG-TASK-DERIVATION-1", "operation_id": op})
            )
            for _, row in prefix:
                derived = sm3_b64url(
                    canonical_json_bytes({"previous": derived, "record_digest": row[2]})
                )
            semantics.append(
                {
                    "operation_id": op,
                    "status": load_strict_json(objects.record(terminal).facts_bytes)["status"]
                    if terminal
                    else "ACCEPTED_NONTERMINAL",
                    "through_sequence": prefix[-1][0],
                    "derivation_digest": derived,
                }
            )
        if anchored >= 1:
            for op in sorted(bootstrap_ops):
                semantics.append(
                    {
                        "operation_id": op,
                        "status": "LEGACY_GAP",
                        "through_sequence": 1,
                        "derivation_digest": trust.registration.bootstrap_digest,
                    }
                )
        limitations = [
            "UNSIGNED_RUNTIME_OBSERVATION",
            "CURRENT_AUTH_UNKNOWN",
            "DOWNSTREAM_ATTESTATION_ONLY",
            "PRE_BOOTSTRAP_HISTORY_UNPROVEN",
        ]
        if pin["mode"] != "LATEST_OBSERVATION":
            limitations.append("NO_LATEST_EXTERNAL_ANCHOR")
        if header["cutoff_sequence"] > anchored:
            limitations.append("UNANCHORED_TAIL")
        if gaps:
            limitations.append("HISTORICAL_GAP")
        names = ("amount_reserved", "amount_settled", "calls_reserved", "calls_settled")
        return TaskVerificationReport(
            "VERIFIED",
            anchored,
            header["cutoff_sequence"],
            header["cutoff_sequence"] - anchored,
            {
                "LATEST_OBSERVATION": "EXTERNAL_OBSERVATION_PROVIDED",
                "MINIMUM": "MINIMUM_ONLY",
                "UNKNOWN": "UNKNOWN",
            }[pin["mode"]],
            trust.registration.boundary,
            tuple(sorted(gaps)),
            tuple(
                {"grant_id": grant, **dict(zip(names, row, strict=True))}
                for grant, row in sorted(counters.items())
            ),
            tuple(semantics),
            {
                "scope": asdict(scope),
                "S": header["cutoff_sequence"],
                "H": header["cutoff_head_digest"],
                "bootstrap_digest": trust.registration.bootstrap_digest,
            },
            tuple(sorted(runtime, key=lambda row: row["operation_id"])),
            "UNKNOWN",
            "ATTESTED_NOT_INDEPENDENTLY_PROVEN",
            tuple(limitations),
            {},
        )
    finally:
        objects.file.close()


def _utc(value):
    if type(value) is not str:
        raise TaskBundleError("original UTC timestamp required")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if (
        dt.tzinfo is None
        or dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value
        or dt.utcoffset().total_seconds() != 0
    ):
        raise TaskBundleError("original UTC microsecond timestamp required")
    return int(dt.timestamp())


def _canonical_result(objects, original, terminal_refs, status):
    raw = _one(terminal_refs, "result")
    result = parse_result(raw)
    request = load_strict_json(_one(objects.references(original["first"]), "request"))
    bind_result(result, operation_id=original["operation_id"], tool_id=request["tool_id"])
    if isinstance(result, RefusalResult) != (status == "FAILED"):
        raise TaskBundleError("result terminal variant mismatch")
    if isinstance(result, OrderResult):
        quote = json_object(_one(objects.references(original["first"]), "quote"))
        if (
            result.total_fen != quote["total_fen"]
            or result.supplier_id != quote["supplier_id"]
            or result.quote_id != quote["quote_id"]
            or result.quote_version != quote["quote_version"]
            or list(result.items)
            != [(i["sku"], i["quantity"], i["unit_price_fen"]) for i in quote["items"]]
        ):
            raise TaskBundleError("result original order quote mismatch")
    if isinstance(result, NotificationResult):
        if (result.template_id, result.recipient_id) != (
            request["params"]["template_id"],
            request["params"]["recipient_id"],
        ):
            raise TaskBundleError("notification original params mismatch")
    return canonical_json_bytes(load_strict_json(raw))


def _pending(objects, refs, record, original, trust):
    metadata = json_object(_one(refs, "pending_receipt_metadata"))
    names = (
        "receipt_id operation_id profile tenant_id task_id root_grant_id "
        "grant_id tool_id tool_version status amount_fen token_digest "
        "proof_digest intent_digest evidence_ref created_at"
    ).split()
    exact(metadata, ["metadata_profile", *names], "pending metadata")
    if metadata["metadata_profile"] != "AG-TASK-PENDING-RECEIPT-1":
        raise TaskBundleError("pending metadata profile mismatch")
    facts = load_strict_json(record.facts_bytes)
    first = load_strict_json(objects.record(original["first"]).facts_bytes)
    request = load_strict_json(_one(objects.references(original["first"]), "request"))
    expected = {
        "receipt_id": facts["receipt_id"],
        "operation_id": record.operation_id,
        "profile": "GM-MVP-1",
        "tenant_id": trust.scope.tenant_id,
        "task_id": trust.scope.task_id,
        "root_grant_id": first["root_grant_id"],
        "grant_id": first["grant_id"],
        "tool_id": request["tool_id"],
        "tool_version": request["tool_version"],
        "status": facts["status"],
        "amount_fen": first["amount_fen"] if facts["status"] == "SUCCEEDED" else 0,
        "token_digest": first["token_digest"],
        "proof_digest": first["proof_digest"],
        "intent_digest": first["intent_digest"],
        "evidence_ref": original["first_ref"],
    }
    if any(metadata[k] != v for k, v in expected.items()):
        raise TaskBundleError("pending immutable FIRST/TERMINAL binding mismatch")
    integer(metadata["amount_fen"])
    for name in names:
        if name != "amount_fen":
            identifier(metadata[name])
    _utc(metadata["created_at"])
    internal_raw = _one(refs, "internal_ledger")
    internal = load_ledger_changes(internal_raw, internal=True)
    if len(internal["events"]) != 2 or [e["seq"] for e in internal["events"]] != [0, 1]:
        raise TaskBundleError("internal ledger original sequence mismatch")
    public = {
        "operation_id": internal["operation_id"],
        "events": [{"phase": e["phase"], "nodes": e["nodes"]} for e in internal["events"]],
    }
    if canonical_ledger_changes_bytes(public) != _one(refs, "ledger"):
        raise TaskBundleError("internal ledger differs from canonical B projection")
    result_raw = _one(refs, "result")
    _canonical_result(objects, original, refs, facts["status"])
    pending = {k: metadata[k] for k in names}
    metadata_raw = canonical_json_bytes(pending)
    pending.update(
        ledger_changes_json=b64url_encode(internal_raw),
        result_bytes=b64url_encode(result_raw),
    )
    raw = rfc8785.dumps(pending)
    overhead = len(rfc8785.dumps({"result_bytes": "", "ledger_changes_json": ""})) - 1
    if (
        overhead != 43
        or len(raw) > len(metadata_raw) + overhead + 2 * ((65536 * 4 + 2) // 3)
        or sm3_b64url(raw) != facts["pending_receipt_digest"]
    ):
        raise TaskBundleError("original pending receipt aggregate digest mismatch")


def _response(objects, facts, refs, record, original):
    op = record.operation_id
    if (
        original["terminal"] is None
        and facts["status"] in {"SUCCEEDED", "FAILED"}
        or original["terminal"] is not None
        and facts["status"] != original["status"]
    ):
        raise TaskBundleError("historical response status not derivable")
    receipt = (
        _one(objects.references(original["receipt_seq"]), "receipt")
        if original["receipt_seq"] is not None and facts["receipt_status"] == "READY"
        else None
    )
    if (
        facts["receipt_jws_digest"] != (sm3_b64url(receipt) if receipt else None)
        or facts["receipt_status"] == "READY"
        and receipt is None
    ):
        raise TaskBundleError("historical response publication mismatch")
    if _one(refs, "receipt", receipt is None) != receipt:
        raise TaskBundleError("response receipt differs from original publication")
    if record.kind == "QUERY":
        terminal_refs = objects.references(original["terminal"]) if original["terminal"] else None
        original_result = _one(terminal_refs, "result") if terminal_refs else None
        if _one(refs, "result", original_result is None) != original_result:
            raise TaskBundleError("query result differs from original terminal result")
        result = (
            _canonical_result(objects, original, terminal_refs, facts["status"])
            if terminal_refs
            else None
        )
        response = {
            "operation_id": op,
            "status": facts["status"],
            "receipt_status": facts["receipt_status"],
            "result": load_strict_json(result) if result else None,
            "receipt_jws": receipt.decode("ascii") if receipt else None,
        }
        if facts["result_digest"] != (sm3_b64url(result) if result else None):
            raise TaskBundleError("historical query result mismatch")
        if facts["response_digest"] != sm3_b64url(canonical_json_bytes(response)):
            raise TaskBundleError("historical query response mismatch")
    elif facts["response_kind"] == "ACCEPT_RESPONSE":
        response = {
            "operation_id": op,
            "status": facts["status"],
            "receipt_status": facts["receipt_status"],
        }
        if facts["response_digest"] != sm3_b64url(canonical_json_bytes(response)):
            raise TaskBundleError("historical retry response mismatch")
    else:
        metadata = exact(
            json_object(_one(refs, "accept_result_metadata")),
            (
                "metadata_profile operation_id grant_id root_id status disposition cost accepted_at"
            ).split(),
            "accept result metadata",
        )
        first = load_strict_json(objects.record(original["first"]).facts_bytes)
        if (
            metadata["metadata_profile"] != "AG-TASK-ACCEPT-RESULT-1"
            or metadata["operation_id"] != op
            or metadata["grant_id"] != first["grant_id"]
            or metadata["root_id"] != first["root_grant_id"]
            or metadata["status"] != facts["status"]
            or metadata["disposition"] != "EXISTING"
        ):
            raise TaskBundleError("historical accept result identity mismatch")
        _utc(metadata["accepted_at"])
        if original.get("accepted_at", metadata["accepted_at"]) != metadata["accepted_at"]:
            raise TaskBundleError("retry immutable accepted_at changed")
        cost = exact(
            metadata["cost"],
            "amount_fen calls currency quote_id quote_version quote_snapshot".split(),
            "accept result cost",
        )
        first_quote = _one(objects.references(original["first"]), "quote", True)
        quote = _one(refs, "quote", True)
        if (
            quote != first_quote
            or cost["quote_snapshot"] is not None
            or cost["amount_fen"] != first["amount_fen"]
            or cost["calls"] != first["calls"]
            or cost["currency"] != "CNY"
        ):
            raise TaskBundleError("historical accept result cost mismatch")
        integer(cost["amount_fen"])
        integer(cost["calls"])
        expected_quote = json_object(quote) if quote is not None else None
        if (cost["quote_id"], cost["quote_version"]) != (
            (expected_quote["quote_id"], expected_quote["quote_version"])
            if expected_quote
            else (None, None)
        ):
            raise TaskBundleError("historical accept quote identifiers mismatch")
        response = {k: v for k, v in metadata.items() if k != "metadata_profile"}
        base = canonical_json_bytes(response)
        if quote is not None:
            response["cost"] = {**cost, "quote_snapshot": b64url_encode(quote)}
            raw = rfc8785.dumps(response)
            if (
                len(raw) != len(base) - 2 + len(response["cost"]["quote_snapshot"])
                or len(raw) > 152916
            ):
                raise TaskBundleError("historical accept result aggregate capacity")
        else:
            raw = base
        if sm3_b64url(raw) != facts["response_digest"]:
            raise TaskBundleError("historical original accept result digest mismatch")
        original["accepted_at"] = metadata["accepted_at"]


def verify_task_bundle(binary_stream, external_trust, external_pin):
    """Authenticate every frame and original, or raise one public failure."""
    try:
        trust = (
            external_trust
            if type(external_trust) is TaskTrust
            else load_public_trust(external_trust)
        )
        return _verify(binary_stream, trust, external_pin)
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        UnicodeError,
        ExecutionError,
        AttributeError,
    ) as exc:
        if isinstance(exc, TaskBundleError):
            raise
        raise TaskBundleError("invalid complete task evidence") from exc
