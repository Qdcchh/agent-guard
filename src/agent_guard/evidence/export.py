"""Read-only repeatable-read task materialization into a private bounded spool."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

import rfc8785

from agent_guard.audit.contracts import (
    JournalScope,
    decode_checkpoint_claims,
    decode_journal_record,
    decode_material_projection,
    genesis_digest,
    utc_text,
)
from agent_guard.contracts.encoding import (
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.contracts.ledger_changes import (
    canonical_ledger_changes_bytes,
    load_ledger_changes,
)
from agent_guard.crypto.sm import sm3_b64url
from agent_guard.evidence import task_bundle as codec


@dataclass(frozen=True, slots=True)
class TaskExportSpool:
    path: str
    size: int
    digest: str
    object_count: int
    chunk_count: int
    journal_count: int
    operation_count: int
    cutoff_sequence: int
    cutoff_head_digest: str
    _cleanup_capability: object
    _guardian_pid: int

    def cleanup(self):
        """Delete only this freshly allocated private directory."""
        self._cleanup_capability.close()


class _CleanupCapability:
    def __init__(self, directory, fd, guardian):
        self._directory = directory
        self._fd = fd
        self._guardian = guardian
        self._lock = threading.Lock()

    def close(self):
        with self._lock:
            if self._fd is None:
                return
            shutil.rmtree(self._directory, ignore_errors=True)
            os.close(self._fd)
            self._fd = None
            self._guardian.wait(timeout=10)


class _Objects:
    def __init__(self, directory):
        self.directory = directory
        self.members = {}
        self.raw_bytes = 0

    def add(self, kind, owner, ident, component, raw, ordinal=0):
        key = (kind, codec.object_id(kind, owner, ident, component, ordinal))
        raw = bytes(raw)
        if not 1 <= len(raw) <= codec.OBJECT_LIMITS[kind]:
            raise codec.TaskBundleError("logical material capacity exceeded")
        digest = sm3_b64url(raw)
        if key in self.members:
            if (
                self.members[key][1:] != (len(raw), digest)
                or self.members[key][0].read_bytes() != raw
            ):
                raise codec.TaskBundleError("conflicting typed object identity")
        else:
            self.raw_bytes += len(raw)
            if len(self.members) >= codec.MAX_OBJECTS or self.raw_bytes > codec.MAX_WIRE_BYTES:
                raise codec.TaskBundleError("complete material capacity exceeded")
            path = self.directory / str(len(self.members))
            with path.open("xb") as out:
                os.chmod(path, 0o600)
                out.write(raw)
            self.members[key] = (path, len(raw), digest)
        return {"component": component, "object_kind": kind, "object_id": key[1]}


def _checkpoint(jws):
    return decode_checkpoint_claims(b64url_decode(jws.split(".")[1]))


def _stream(conn, name, query, parameters):
    cursor = conn.cursor(name=name)
    cursor.itersize = 16
    cursor.execute(query, parameters)
    return cursor


def _snapshot(conn, scope, pin, history, objects):
    row = conn.execute(
        "SELECT gateway_id,tenant_id,task_id,stream_id,epoch,genesis_digest,"
        "bootstrap_digest,head_seq,head_digest FROM ag_audit_streams WHERE stream_id=%s",
        (scope.stream_id,),
    ).fetchone()
    if row is None or JournalScope(*row[:5]) != scope or row[5] != genesis_digest(scope):
        raise codec.TaskBundleError("trusted stream missing or inconsistent")
    cutoff, head = row[7:9]
    if type(cutoff) is not int or not 1 <= cutoff <= codec.MAX_JOURNAL:
        raise codec.TaskBundleError("journal capacity exceeded")
    bootstrap = conn.execute(
        "SELECT boundary,manifest_bytes,schema_lineage_bytes FROM ag_audit_bootstrap "
        "WHERE stream_id=%s",
        (scope.stream_id,),
    ).fetchone()
    if bootstrap is None or sm3_b64url(bytes(bootstrap[1])) != row[6]:
        raise codec.TaskBundleError("bootstrap material unavailable")
    for component, raw in zip(("manifest", "schema_lineage"), bootstrap[1:], strict=True):
        objects.add("typed_snapshot_metadata", "bootstrap", component, component, raw)
    chunks = _stream(
        conn,
        "ag_export_bootstrap",
        "SELECT object_kind,object_id,chunk_index,chunk_count,total_raw_bytes,object_digest,raw "
        "FROM ag_audit_bootstrap_chunks WHERE stream_id=%s ORDER BY object_kind,object_id,"
        "chunk_index LIMIT %s",
        (scope.stream_id, codec.MAX_FRAMES + 1),
    )
    manifest = load_strict_json(bytes(bootstrap[1]))
    scope_key = [scope.gateway_id, scope.tenant_id, scope.task_id]
    index_root = sm3_b64url(
        canonical_json_bytes({"profile": "AG-BOOTSTRAP-INDEX-1", "scope": scope_key})
    )
    bootstrap_objects = 0
    bootstrap_wire = 0
    prior = None
    parts = bytearray()
    seen = 0
    for kind, ident, index, count, total, digest, raw in chunks:
        seen += 1
        if seen > codec.MAX_FRAMES:
            raise codec.TaskBundleError("bootstrap chunk capacity exceeded")
        key = (kind, ident, count, total, digest)
        if prior != key:
            if parts:
                raise codec.TaskBundleError("incomplete bootstrap object")
            prior = key
        if index != len(parts) // codec.CHUNK_BYTES or total > codec.OBJECT_LIMITS[kind]:
            raise codec.TaskBundleError("bootstrap chunk mismatch")
        expected_count = (total + codec.CHUNK_BYTES - 1) // codec.CHUNK_BYTES
        if count != expected_count or len(raw) != min(
            codec.CHUNK_BYTES, total - index * codec.CHUNK_BYTES
        ):
            raise codec.TaskBundleError("bootstrap original chunk shape mismatch")
        bootstrap_wire += (
            len(
                canonical_json_bytes(
                    {
                        "frame_type": "OBJECT_CHUNK",
                        "object_kind": kind,
                        "object_id": ident,
                        "chunk_index": index,
                        "chunk_count": count,
                        "total_raw_bytes": total,
                        "object_digest": digest,
                        "data": b64url_encode(bytes(raw)),
                    }
                )
            )
            + 1
        )
        parts.extend(bytes(raw))
        if index == count - 1:
            if len(parts) != total or sm3_b64url(bytes(parts)) != digest:
                raise codec.TaskBundleError("bootstrap original digest mismatch")
            bootstrap_objects += 1
            index_root = sm3_b64url(
                canonical_json_bytes(
                    {
                        "profile": "AG-BOOTSTRAP-INDEX-1",
                        "previous": index_root,
                        "kind": kind,
                        "id": ident,
                        "total_raw_bytes": total,
                        "object_digest": digest,
                        "chunk_count": count,
                    }
                )
            )
            objects.add(kind, "bootstrap", ident, ident, parts)
            parts.clear()
    if parts:
        raise codec.TaskBundleError("incomplete bootstrap tail")
    if (
        manifest.get("scope") != scope_key
        or manifest.get("origin")
        != ("FROM_EMPTY_TASK" if bootstrap[0] == "NEW_EMPTY" else bootstrap[0])
        or manifest.get("schema_lineage_digest") != sm3_b64url(bytes(bootstrap[2]))
        or (
            manifest.get("object_count"),
            manifest.get("chunk_count"),
            manifest.get("wire_bytes"),
            manifest.get("index_root"),
        )
        != (bootstrap_objects, seen, bootstrap_wire, index_root)
    ):
        raise codec.TaskBundleError("bootstrap complete index/count/wire mismatch")
    records = _stream(
        conn,
        "ag_export_records",
        "SELECT seq,raw,material_binding_bytes FROM ag_audit_records WHERE stream_id=%s "
        "ORDER BY seq LIMIT %s",
        (scope.stream_id, codec.MAX_JOURNAL + 1),
    )
    previous = row[5]
    heads = {}
    seq = 0
    for sequence, raw, projection in records:
        seq += 1
        record = decode_journal_record(bytes(raw))
        if sequence != seq or record.seq != seq or record.previous_digest != previous:
            raise codec.TaskBundleError("journal continuity mismatch")
        if record.scope != scope:
            raise codec.TaskBundleError("journal scope mismatch")
        previous = record.digest
        heads[seq] = previous
        objects.add("journal", "journal", str(seq), "journal", raw)
        refs = _record_material(conn, record, bytes(projection), objects)
        objects.add(
            "typed_snapshot_metadata",
            "journal",
            str(seq),
            "refs",
            canonical_json_bytes(
                {
                    "metadata_profile": "AG-TASK-REFS-1",
                    "record_seq": seq,
                    "operation_id": record.operation_id,
                    "evidence_ref": record.evidence_ref,
                    "refs": refs,
                }
            ),
        )
    if seq != cutoff or previous != head:
        raise codec.TaskBundleError("fixed journal head mismatch")
    cached = _stream(
        conn,
        "ag_export_checkpoints",
        "SELECT checkpoint_jws FROM ag_audit_delivery_batches WHERE stream_id=%s "
        "AND checkpoint_jws IS NOT NULL ORDER BY end_sequence LIMIT %s",
        (scope.stream_id, codec.MAX_JOURNAL + 1),
    )
    cache = {}
    cache_count = cache_bytes = 0
    for (jws,) in cached:
        cache_count += 1
        cache_bytes += len(jws)
        if cache_count > codec.MAX_JOURNAL or cache_bytes > codec.MAX_WIRE_BYTES:
            raise codec.TaskBundleError("cached checkpoint capacity exceeded")
        claim = _checkpoint(jws)
        if claim.sequence > cutoff:
            raise codec.TaskBundleError("cached checkpoint beyond local snapshot")
        if claim.checkpoint_id in cache and cache[claim.checkpoint_id] != jws:
            raise codec.TaskBundleError("cached checkpoint identity conflict")
        cache[claim.checkpoint_id] = jws
    if pin["mode"] == "UNKNOWN":
        terminal = max(cache.values(), key=lambda j: _checkpoint(j).sequence) if cache else None
        if (terminal is None) != (history.checkpoint_count == 0):
            raise codec.TaskBundleError("UNKNOWN history requires cached terminal")
        if terminal is not None and sm3_b64url(terminal.encode("ascii")) != history.last_jws_digest:
            raise codec.TaskBundleError("UNKNOWN history terminal mismatch")
    else:
        terminal = pin["checkpoint_jws"]
    boundary = _checkpoint(terminal).sequence if terminal else 0
    if boundary > cutoff:
        raise codec.TaskBundleError("snapshot behind independent checkpoint")
    originals = {}
    with history.open_readonly() as stream:
        for raw in stream:
            value = load_strict_json(raw[:-1])
            jws = value["checkpoint_jws"]
            claim = _checkpoint(jws)
            if claim.sequence > cutoff or heads.get(claim.sequence) != claim.head_digest:
                raise codec.TaskBundleError("public checkpoint forks local journal")
            originals[claim.checkpoint_id] = jws
            objects.add(
                "checkpoint",
                "checkpoint",
                claim.checkpoint_id,
                "checkpoint",
                jws.encode("ascii"),
            )
    for ident, jws in cache.items():
        if _checkpoint(jws).sequence <= boundary and originals.get(ident) != jws:
            raise codec.TaskBundleError("cached original absent from public chain")
    ops = conn.execute(
        "SELECT o.operation_id,o.status,r.receipt_status FROM ag_operations o LEFT JOIN "
        "ag_receipt_outbox r USING(operation_id) WHERE o.tenant_id=%s AND o.task_id=%s "
        "ORDER BY o.operation_id LIMIT %s",
        (scope.tenant_id, scope.task_id, codec.MAX_OPERATIONS + 1),
    ).fetchall()
    if len(ops) > codec.MAX_OPERATIONS:
        raise codec.TaskBundleError("operation capacity exceeded")
    for ident, status, receipt in ops:
        objects.add(
            "typed_snapshot_metadata",
            "runtime",
            ident,
            "runtime",
            canonical_json_bytes(
                {
                    "metadata_profile": "AG-TASK-RUNTIME-OBSERVATION-1",
                    "operation_id": ident,
                    "status": status,
                    "receipt_status": receipt,
                }
            ),
        )
    return cutoff, head, row[6], bootstrap[0], len(ops)


def _record_material(conn, record, raw, objects):
    material = decode_material_projection(record.kind, raw)
    facts = load_strict_json(record.facts_bytes)
    refs = []
    if record.kind in {"FIRST", "RETRY", "QUERY"}:
        evidence = conn.execute(
            "SELECT token_bytes,proof_bytes,body_bytes,token_sm3,proof_sm3,body_sm3 "
            "FROM ag_verified_evidence WHERE evidence_ref=%s AND tenant_id=%s AND task_id=%s",
            (record.evidence_ref, record.scope.tenant_id, record.scope.task_id),
        ).fetchone()
        if evidence is None or tuple(sm3_b64url(bytes(x)) for x in evidence[:3]) != evidence[3:]:
            raise codec.TaskBundleError("original evidence unavailable")
        for kind, component, value, expected in zip(
            ("token", "proof", "request"),
            ("token", "proof", "request"),
            evidence[:3],
            (facts["token_digest"], facts["proof_digest"], facts["body_digest"]),
            strict=True,
        ):
            if sm3_b64url(bytes(value)) != expected:
                raise codec.TaskBundleError("original evidence fact mismatch")
            refs.append(objects.add(kind, "evidence", record.evidence_ref, component, value))
        for component in ("context", "source"):
            value = b64url_decode(material[component])
            name = "source_material_digest" if component == "source" else "context_digest"
            if sm3_b64url(value) != facts[name]:
                raise codec.TaskBundleError("material fact mismatch")
            refs.append(objects.add(component, "journal", str(record.seq), component, value))
        source = load_strict_json(b64url_decode(material["source"]))
        chain = load_strict_json(source["chain"].encode("utf-8"))
        if type(chain) is not list or not 1 <= len(chain) <= 3:
            raise codec.TaskBundleError("complete bounded ancestry required")
        for ordinal, item in enumerate(chain):
            refs.append(
                objects.add(
                    "ancestor_token",
                    "journal",
                    str(record.seq),
                    "ancestor_token",
                    item["token"].encode("ascii"),
                    ordinal,
                )
            )
    if record.kind == "TERMINAL":
        refs.extend(_terminal_material(conn, record, material, objects))
    for component, value in material.items():
        if record.kind == "TERMINAL":
            break
        if component in {"context", "source"} or value is None:
            continue
        component = "receipt" if component == "jws" else component
        value = value.encode("ascii") if component == "receipt" else b64url_decode(value)
        refs.append(objects.add(component, "operation", record.operation_id, component, value))
    if record.kind == "RETRY" and facts["response_kind"] == "ACCEPT_RESULT":
        refs.extend(_accept_result_material(conn, record, objects))
    elif record.kind == "RETRY":
        response = {k: facts[k] for k in ("status", "receipt_status")}
        response["operation_id"] = record.operation_id
        if sm3_b64url(canonical_json_bytes(response)) != facts["response_digest"]:
            raise codec.TaskBundleError("historical accept response mismatch")
    if record.kind == "QUERY":
        refs.extend(_query_material(conn, record, objects))
    if record.kind == "RETRY" and facts["receipt_status"] == "READY":
        row = conn.execute(
            "SELECT receipt_jws FROM ag_receipt_outbox WHERE operation_id=%s",
            (record.operation_id,),
        ).fetchone()
        if (
            row is None
            or row[0] is None
            or sm3_b64url(row[0].encode("ascii")) != facts["receipt_jws_digest"]
        ):
            raise codec.TaskBundleError("historical retry publication missing")
        refs.append(
            objects.add(
                "receipt",
                "operation",
                record.operation_id,
                "receipt",
                row[0].encode("ascii"),
            )
        )
    if len(refs) > 16:
        raise codec.TaskBundleError("record reference capacity exceeded")
    return refs


def _accept_result_material(conn, record, objects):
    facts = load_strict_json(record.facts_bytes)
    row = conn.execute(
        "SELECT o.grant_id,g.root_grant_id,o.amount_fen,o.calls,o.currency,o.quote_id,"
        "o.quote_version,o.quote_snapshot,o.accepted_at FROM ag_operations o JOIN ag_grants g "
        "ON g.grant_id=o.grant_id WHERE o.operation_id=%s AND o.tenant_id=%s AND o.task_id=%s",
        (record.operation_id, record.scope.tenant_id, record.scope.task_id),
    ).fetchone()
    if row is None:
        raise codec.TaskBundleError("original accepted operation unavailable")
    cost = dict(
        zip(
            ("amount_fen", "calls", "currency", "quote_id", "quote_version"),
            row[2:7],
            strict=True,
        )
    )
    cost["quote_snapshot"] = None
    value = {
        "operation_id": record.operation_id,
        "grant_id": row[0],
        "root_id": row[1],
        "status": facts["status"],
        "disposition": "EXISTING",
        "cost": cost,
        "accepted_at": utc_text(row[8]),
    }
    original = canonical_json_bytes(value)
    refs = []
    if row[7] is not None:
        quote = bytes(row[7])
        if not 1 <= len(quote) <= 65536:
            raise codec.TaskBundleError("original accepted quote capacity exceeded")
        cost["quote_snapshot"] = b64url_encode(quote)
        encoded = rfc8785.dumps(value)
        if len(encoded) != len(original) - 2 + len(cost["quote_snapshot"]) or len(encoded) > 152916:
            raise codec.TaskBundleError("accept result aggregate capacity exceeded")
        refs.append(objects.add("quote", "operation", record.operation_id, "quote", quote))
        cost["quote_snapshot"] = None
    else:
        encoded = original
    if sm3_b64url(encoded) != facts["response_digest"]:
        raise codec.TaskBundleError("original accept result digest mismatch")
    value["metadata_profile"] = "AG-TASK-ACCEPT-RESULT-1"
    refs.append(
        objects.add(
            "typed_snapshot_metadata",
            "journal",
            str(record.seq),
            "accept_result_metadata",
            canonical_json_bytes(value),
        )
    )
    return refs


_PENDING_FIELDS = (
    "receipt_id",
    "operation_id",
    "profile",
    "tenant_id",
    "task_id",
    "root_grant_id",
    "grant_id",
    "tool_id",
    "tool_version",
    "status",
    "amount_fen",
    "token_digest",
    "proof_digest",
    "intent_digest",
    "evidence_ref",
    "created_at",
)


def _terminal_material(conn, record, material, objects):
    row = conn.execute(
        "SELECT receipt_id,operation_id,profile,tenant_id,task_id,root_grant_id,grant_id,"
        "tool_id,tool_version,status,amount_fen,token_digest,proof_digest,intent_digest,"
        "evidence_ref,created_at,ledger_changes_json,result_bytes FROM ag_receipt_outbox "
        "WHERE operation_id=%s AND tenant_id=%s AND task_id=%s",
        (record.operation_id, record.scope.tenant_id, record.scope.task_id),
    ).fetchone()
    if row is None:
        raise codec.TaskBundleError("original pending receipt unavailable")
    metadata = dict(zip(_PENDING_FIELDS, row[:16], strict=True))
    metadata["created_at"] = utc_text(row[15])
    internal, result = bytes(row[16]), bytes(row[17])
    if internal != b64url_decode(material["ledger"]) or result != b64url_decode(material["result"]):
        raise codec.TaskBundleError("terminal projection differs from original outbox")
    ledger = load_ledger_changes(internal, internal=True)
    from agent_guard.execution.receipt_projection import project_receipt

    projection = project_receipt(conn, record.operation_id)
    public = canonical_ledger_changes_bytes(
        {
            "operation_id": ledger["operation_id"],
            "events": [{"phase": e["phase"], "nodes": e["nodes"]} for e in ledger["events"]],
        }
    )
    pending = {
        **metadata,
        "ledger_changes_json": b64url_encode(internal),
        "result_bytes": b64url_encode(result),
    }
    facts = load_strict_json(record.facts_bytes)
    if (
        sm3_b64url(rfc8785.dumps(pending)) != facts["pending_receipt_digest"]
        or sm3_b64url(public) != facts["ledger_digest"]
        or sm3_b64url(result) != facts["result_digest"]
    ):
        raise codec.TaskBundleError("terminal original digest mismatch")
    if (
        public != projection.ledger_bytes
        or canonical_json_bytes(load_strict_json(result)) != projection.result_bytes
    ):
        raise codec.TaskBundleError("terminal canonical projection mismatch")
    metadata["metadata_profile"] = "AG-TASK-PENDING-RECEIPT-1"
    return [
        objects.add(kind, "operation", record.operation_id, component, raw)
        for kind, component, raw in (
            (
                "typed_snapshot_metadata",
                "pending_receipt_metadata",
                canonical_json_bytes(metadata),
            ),
            ("ledger", "internal_ledger", internal),
            ("ledger", "ledger", public),
            ("result", "result", result),
        )
    ]


def _query_material(conn, record, objects):
    facts = load_strict_json(record.facts_bytes)
    refs = []
    response = {
        "operation_id": record.operation_id,
        "status": facts["status"],
        "receipt_status": facts["receipt_status"],
        "result": None,
        "receipt_jws": None,
    }
    if facts["status"] in {"SUCCEEDED", "FAILED"}:
        row = conn.execute(
            "SELECT result_bytes,receipt_jws FROM ag_receipt_outbox WHERE operation_id=%s",
            (record.operation_id,),
        ).fetchone()
        if row is None:
            raise codec.TaskBundleError("historical query final material missing")
        response["result"] = load_strict_json(bytes(row[0]))
        if sm3_b64url(canonical_json_bytes(response["result"])) != facts["result_digest"]:
            raise codec.TaskBundleError("historical query result digest mismatch")
        refs.append(objects.add("result", "operation", record.operation_id, "result", row[0]))
        if facts["receipt_status"] == "READY":
            if row[1] is None or sm3_b64url(row[1].encode("ascii")) != facts["receipt_jws_digest"]:
                raise codec.TaskBundleError("historical query publication missing")
            response["receipt_jws"] = row[1]
            refs.append(
                objects.add(
                    "receipt",
                    "operation",
                    record.operation_id,
                    "receipt",
                    row[1].encode("ascii"),
                )
            )
    if sm3_b64url(canonical_json_bytes(response)) != facts["response_digest"]:
        raise codec.TaskBundleError("historical query response mismatch")
    return refs


def materialize_task_export(
    connection_factory,
    scope,
    external_pin,
    spool_parent,
    *,
    external_checkpoint_history,
):
    """Return only after the entire fixed snapshot is spooled and its TX has closed."""
    if type(scope) is not JournalScope or external_checkpoint_history.scope != scope:
        raise codec.TaskBundleError("trusted scope/history required")
    if (
        type(external_pin) is not dict
        or set(external_pin) != {"mode", "checkpoint_jws", "observed_at", "scope"}
        or external_pin["scope"] != asdict(scope)
        or external_pin["mode"] not in {"UNKNOWN", "MINIMUM", "LATEST_OBSERVATION"}
    ):
        raise codec.TaskBundleError("exact trusted external pin required")
    if external_pin["mode"] == "UNKNOWN":
        if external_pin["checkpoint_jws"] is not None or external_pin["observed_at"] is not None:
            raise codec.TaskBundleError("UNKNOWN external pin must be null")
    elif (
        sm3_b64url(external_pin["checkpoint_jws"].encode("ascii"))
        != external_checkpoint_history.last_jws_digest
    ):
        raise codec.TaskBundleError("descriptor terminal differs from trusted pin")
    parent = Path(spool_parent)
    if not parent.is_dir() or parent.is_symlink() or stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise codec.TaskBundleError("private 0700 spool parent required")
    directory = Path(tempfile.mkdtemp(prefix="export-", dir=parent))
    os.chmod(directory, 0o700)
    read_fd, cleanup_fd = os.pipe()
    try:
        guardian = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import os,shutil,sys; f=int(sys.argv[1]); "
                "os.read(f,1); os.close(f); shutil.rmtree(sys.argv[2],ignore_errors=True)",
                str(read_fd),
                str(directory),
            ],
            pass_fds=(read_fd,),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except BaseException:
        os.close(read_fd)
        os.close(cleanup_fd)
        shutil.rmtree(directory, ignore_errors=True)
        raise
    os.close(read_fd)
    try:
        objects = _Objects(directory)
        with connection_factory() as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                conn.execute("SET LOCAL statement_timeout='30s'")
                conn.execute("SET LOCAL lock_timeout='3s'")
                snapshot, at = conn.execute(
                    "SELECT pg_current_snapshot()::text,"
                    "EXTRACT(EPOCH FROM clock_timestamp())::bigint"
                ).fetchone()
                cutoff, head, bootstrap, boundary, opcount = _snapshot(
                    conn, scope, external_pin, external_checkpoint_history, objects
                )
                counts = sum(
                    (size + codec.CHUNK_BYTES - 1) // codec.CHUNK_BYTES
                    for _, size, _ in objects.members.values()
                )
                header = {
                    "frame_type": "HEADER",
                    "manifest_version": "AG-TASK-EVIDENCE-2",
                    "scope": asdict(scope),
                    "cutoff_sequence": cutoff,
                    "cutoff_head_digest": head,
                    "snapshot_as_of": at,
                    "snapshot_id": snapshot,
                    "history_boundary": boundary,
                    "bootstrap_digest": bootstrap,
                    "object_count": len(objects.members),
                    "chunk_count": counts,
                    "journal_count": cutoff,
                    "operation_count": opcount,
                }
                path = directory / "bundle.ndjson"
                size, sha = _write(path, scope, header, objects)
        # The download holds no database transaction or connection.
        for member, _, _ in objects.members.values():
            member.unlink()
        return TaskExportSpool(
            str(path),
            size,
            sha,
            len(objects.members),
            counts,
            cutoff,
            opcount,
            cutoff,
            head,
            _CleanupCapability(directory, cleanup_fd, guardian),
            guardian.pid,
        )
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        os.close(cleanup_fd)
        guardian.wait(timeout=10)
        raise


def _write(path, scope, header, objects):
    index, wire = codec.index_seed(scope), codec.wire_seed(scope)
    total = frames = 0
    hashed = hashlib.sha256()
    with path.open("xb") as out:
        os.chmod(path, 0o600)

        def emit(raw, *, footer=False):
            nonlocal wire, total, frames
            if (
                len(raw) > codec.MAX_LINE_BYTES
                or total + len(raw) > codec.MAX_WIRE_BYTES
                or frames >= codec.MAX_FRAMES
            ):
                raise codec.TaskBundleError("complete export wire capacity exceeded")
            if not footer:
                wire = codec.wire_fold(wire, frames, raw)
            total += len(raw)
            frames += 1
            out.write(raw)
            hashed.update(raw)

        emit(canonical_json_bytes(header) + b"\n")
        for (kind, ident), (member, _, _) in sorted(objects.members.items()):
            last = None
            for raw in codec.encode_object_chunks(kind, ident, member.read_bytes()):
                emit(raw)
                last = load_strict_json(raw[:-1])
            index = codec.index_fold(index, last)
        footer = {
            "frame_type": "FOOTER",
            "object_index_root": index,
            "wire_root": wire,
            "before_footer_frames": frames,
            "before_footer_wire_bytes": total,
        }
        emit(canonical_json_bytes(footer) + b"\n", footer=True)
        out.flush()
        os.fsync(out.fileno())
    with path.open("rb") as stream:
        for _ in codec.iter_frames(stream):
            pass
    return total, hashed.hexdigest()
