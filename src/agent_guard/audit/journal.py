"""Local structural journal writer. All functions use the caller's transaction.

Business rows and material are read before locking the journal head. No function
here commits, connects, signs, calls a network or acquires a business lock after
that head lock. SQL transaction witnesses independently guard required coverage.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime
from urllib.parse import urlsplit

import rfc8785
from psycopg import sql

from agent_guard.audit.contracts import (
    CHUNK_BYTES,
    MAX_CHUNKS,
    MAX_OBJECTS,
    MAX_OPERATIONS,
    MAX_RECORDS,
    MAX_WIRE_BYTES,
    OBJECT_LIMITS,
    EmptyTaskBootstrapSeed,
    ExistingStreamRef,
    JournalScope,
    LockedAcceptContext,
    RegistrationDescriptor,
    SnapshotChunk,
    SnapshotObject,
    canonical_json_bytes,
    decode_journal_record,
    encode_material_projection,
    genesis_digest,
    scope_object,
    utc_text,
)
from agent_guard.contracts.encoding import b64url_encode, load_strict_json
from agent_guard.contracts.ledger import INVOKE_ENDPOINT
from agent_guard.crypto.sm import sm3_b64url


class JournalError(ValueError):
    """Required audit capability, trustworthy material or bounded snapshot unavailable."""


def gateway_origin() -> str:
    parsed = urlsplit(INVOKE_ENDPOINT)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise JournalError("trusted HTTPS invocation origin required")
    return parsed.scheme + "://" + parsed.netloc


def tx_id(conn) -> str:
    return conn.execute("SELECT pg_current_xact_id()::text").fetchone()[0]


def available(conn) -> bool:
    return conn.execute("SELECT to_regclass('ag_audit_streams') IS NOT NULL").fetchone()[0]


def stream_tx(conn, scope_key: tuple[str, str, str]) -> ExistingStreamRef | None:
    if not available(conn):
        return None
    row = conn.execute(
        "SELECT stream_id,epoch,genesis_digest,bootstrap_digest FROM ag_audit_streams "
        "WHERE gateway_id=%s AND tenant_id=%s AND task_id=%s",
        scope_key,
    ).fetchone()
    if row is None:
        return None
    return ExistingStreamRef(JournalScope(*scope_key, row[0], row[1]), row[2], row[3])


def require_stream_tx(conn, tenant_id: str, task_id: str) -> ExistingStreamRef | None:
    return stream_tx(conn, (gateway_origin(), tenant_id, task_id))


def _json_value(value):
    if type(value) is int and value < 0:
        return {"signed_integer_text": str(value)}
    if isinstance(value, datetime):
        return utc_text(value)
    if isinstance(value, memoryview):
        return b64url_encode(bytes(value))
    if type(value) is bytes:
        return b64url_encode(value)
    if type(value) is tuple:
        return [_json_value(x) for x in value]
    return value


def _schema(conn) -> tuple[tuple[str, str, str], ...]:
    if conn.execute("SELECT to_regclass('ag_schema_migration_lineages') IS NOT NULL").fetchone()[0]:
        return tuple(
            conn.execute(
                "SELECT namespace,version,checksum FROM ag_schema_migration_lineages "
                "ORDER BY namespace,version"
            ).fetchall()
        )
    raise JournalError("qualified audit migration lineage required")


def _snapshot(conn, scope_key, root, *, empty: bool) -> EmptyTaskBootstrapSeed:
    _, tenant, task = scope_key
    at = utc_text(conn.execute("SELECT clock_timestamp()").fetchone()[0])
    xid = tx_id(conn)
    # Every object is bounded before chunking. Metadata references raw objects;
    # it never embeds a task-sized array or doubles a 64KiB bytea through base64.
    objects = []

    def add(kind, ident, raw):
        if type(raw) is not bytes or not 1 <= len(raw) <= OBJECT_LIMITS[kind]:
            raise JournalError("logical snapshot object capacity exceeded")
        if len(objects) >= MAX_OBJECTS:
            raise JournalError("snapshot object capacity exceeded")
        objects.append(SnapshotObject(kind, ident, raw, sm3_b64url(raw)))

    grants = conn.execute(
        "SELECT grant_id,amount_reserved,amount_settled,calls_reserved,calls_settled "
        "FROM ag_grants WHERE tenant_id=%s AND task_id=%s ORDER BY grant_id LIMIT %s",
        (tenant, task, MAX_OBJECTS + 1),
    ).fetchall()
    if len(grants) > MAX_OBJECTS or not grants:
        raise JournalError("task grant capacity or missing root")
    ops = conn.execute(
        "SELECT operation_id FROM ag_operations WHERE tenant_id=%s AND task_id=%s "
        "ORDER BY operation_id LIMIT %s",
        (tenant, task, MAX_OPERATIONS + 1),
    ).fetchall()
    if len(ops) > MAX_OPERATIONS:
        raise JournalError("task operation capacity exceeded")
    if empty and (ops or any(any(x != 0 for x in g[1:]) for g in grants)):
        raise JournalError("nonempty task requires drained maintenance bootstrap")
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema() "
        "AND table_name LIKE 'ag_%' AND table_type='BASE TABLE' ORDER BY table_name"
    ).fetchall()
    for (table,) in tables:
        if (
            table.startswith("ag_audit_")
            or table.startswith("ag_schema_")
            or table == "ag_test_ownership"
        ):
            continue
        columns = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=%s ORDER BY ordinal_position",
            (table,),
        ).fetchall()
        names = tuple(c[0] for c in columns)
        if "tenant_id" in names and "task_id" in names:
            where, args = "tenant_id=%s AND task_id=%s", (tenant, task)
        elif "operation_id" in names:
            where, args = (
                "operation_id IN (SELECT operation_id FROM ag_operations WHERE "
                "tenant_id=%s AND task_id=%s)",
                (tenant, task),
            )
        elif "grant_id" in names:
            where, args = (
                "grant_id IN (SELECT grant_id FROM ag_grants WHERE tenant_id=%s AND task_id=%s)",
                (tenant, task),
            )
        elif table == "ag_auth_evidence":
            where, args = (
                "code_sha256 IN (SELECT code_sha256 FROM ag_authorization_codes "
                "WHERE tenant_id=%s AND task_id=%s)",
                (tenant, task),
            )
        elif table == "ag_exchange_evidence":
            where, args = (
                "parent_grant_id IN (SELECT grant_id FROM ag_grants "
                "WHERE tenant_id=%s AND task_id=%s)",
                (tenant, task),
            )
        elif table == "ag_auth_events":
            where, args = (
                "request_id IN (SELECT request_id FROM ag_authorization_requests "
                "WHERE tenant_id=%s AND task_id=%s)",
                (tenant, task),
            )
        elif table == "ag_login_sessions":
            where, args = (
                "session_sha256 IN (SELECT session_sha256 FROM ag_authorization_requests "
                "WHERE tenant_id=%s AND task_id=%s)",
                (tenant, task),
            )
        elif table == "ag_principals":
            where, args = (
                "(tenant_id,client_id,kid) IN (SELECT "
                "tenant_id,holder_client_id,holder_kid FROM ag_grants WHERE "
                "tenant_id=%s AND task_id=%s)",
                (tenant, task),
            )
        elif table in ("ag_ledger_event_nodes", "ag_event_seals"):
            where, args = (
                "event_id IN (SELECT event_id FROM ag_ledger_events WHERE "
                "operation_id IN (SELECT operation_id FROM ag_operations WHERE "
                "tenant_id=%s AND task_id=%s))",
                (tenant, task),
            )
        else:
            continue
        # Only accepted linked proofs/evidence belong to the execution baseline.
        if table in ("ag_proofs", "ag_verified_evidence"):
            where += " AND " + (
                "operation_id IS NOT NULL"
                if table == "ag_proofs"
                else "evidence_ref IN (SELECT evidence_ref FROM ag_proofs WHERE "
                "operation_id IS NOT NULL)"
            )
        query = sql.SQL(
            "SELECT * FROM {} WHERE " + where + " ORDER BY to_jsonb({})::text LIMIT %s"
        ).format(sql.Identifier(table), sql.Identifier(table))
        rows = conn.execute(query, (*args, MAX_OBJECTS + 1)).fetchall()
        if len(rows) > MAX_OBJECTS:
            raise JournalError("snapshot row capacity exceeded")
        for index, row in enumerate(rows):
            ident = table + ":" + str(index)
            metadata = {"table": table, "row_index": index, "columns": {}}
            for name, value in zip(names, row, strict=True):
                signed_kind = {
                    ("ag_grant_tokens", "token_jws"): "token",
                    ("ag_auth_evidence", "proof_jws"): "proof",
                    ("ag_exchange_evidence", "proof_jws"): "proof",
                    ("ag_receipt_outbox", "receipt_jws"): "receipt",
                }.get((table, name))
                if signed_kind is not None and value is not None:
                    if type(value) is not str:
                        raise JournalError("signed snapshot text type mismatch")
                    try:
                        raw = value.encode("ascii")
                    except UnicodeEncodeError as exc:
                        raise JournalError("signed snapshot text must be ASCII") from exc
                    raw_id = ident + ":" + name
                    add(signed_kind, raw_id, raw)
                    metadata["columns"][name] = {
                        "kind": signed_kind,
                        "object_id": raw_id,
                        "digest": sm3_b64url(raw),
                    }
                elif isinstance(value, (bytes, memoryview)):
                    kind = {
                        "token_bytes": "token",
                        "proof_bytes": "proof",
                        "body_bytes": "request",
                        "result_bytes": "result",
                        "ledger_changes_json": "ledger",
                        "quote_snapshot": "quote",
                        "context_json": "context",
                        "chain_json": "source",
                        "claims_json": "typed_snapshot_metadata",
                    }.get(name, "raw_authorization_snapshot")
                    raw_id = ident + ":" + name
                    raw = bytes(value)
                    if raw:
                        add(kind, raw_id, raw)
                        metadata["columns"][name] = {
                            "kind": kind,
                            "object_id": raw_id,
                            "digest": sm3_b64url(raw),
                        }
                    else:
                        metadata["columns"][name] = {"empty_bytes": True}
                else:
                    metadata["columns"][name] = _json_value(value)
            add("typed_snapshot_metadata", ident, canonical_json_bytes(metadata))
    lineage = _schema(conn)
    chunks = []
    index_root = sm3_b64url(
        canonical_json_bytes({"profile": "AG-BOOTSTRAP-INDEX-1", "scope": list(scope_key)})
    )
    wire = 0
    for obj in sorted(objects, key=lambda item: (item.kind, item.object_id)):
        count = (len(obj.raw) + CHUNK_BYTES - 1) // CHUNK_BYTES
        index_root = sm3_b64url(
            canonical_json_bytes(
                {
                    "profile": "AG-BOOTSTRAP-INDEX-1",
                    "previous": index_root,
                    "kind": obj.kind,
                    "id": obj.object_id,
                    "total_raw_bytes": len(obj.raw),
                    "object_digest": obj.digest,
                    "chunk_count": count,
                }
            )
        )
        for i in range(count):
            chunk = SnapshotChunk(
                obj.kind,
                obj.object_id,
                i,
                count,
                len(obj.raw),
                obj.digest,
                obj.raw[i * CHUNK_BYTES : (i + 1) * CHUNK_BYTES],
            )
            frame = {
                "frame_type": "OBJECT_CHUNK",
                "object_kind": chunk.kind,
                "object_id": chunk.object_id,
                "chunk_index": i,
                "chunk_count": count,
                "total_raw_bytes": len(obj.raw),
                "object_digest": obj.digest,
                "data": b64url_encode(chunk.raw),
            }
            wire += len(canonical_json_bytes(frame)) + 1
            chunks.append(chunk)
            if len(chunks) > MAX_CHUNKS or wire > MAX_WIRE_BYTES:
                raise JournalError("complete snapshot frame capacity exceeded")
    manifest = canonical_json_bytes(
        {
            "profile": "AG-BOOTSTRAP-1",
            "scope": list(scope_key),
            "root_grant_id": root,
            "snapshot_as_of": at,
            "origin": "FROM_EMPTY_TASK" if empty else "LEGACY_WITH_GAPS",
            "object_count": len(objects),
            "chunk_count": len(chunks),
            "wire_bytes": wire,
            "index_root": index_root,
            "schema_lineage_digest": sm3_b64url(
                canonical_json_bytes([list(row) for row in lineage])
            ),
        }
    )
    if len(manifest) > 32768:
        raise JournalError("bootstrap manifest capacity exceeded")
    return EmptyTaskBootstrapSeed(
        scope_key,
        root,
        xid,
        at,
        "FROM_EMPTY_TASK" if empty else "LEGACY_WITH_GAPS",
        lineage,
        tuple(sorted(objects, key=lambda o: (o.kind, o.object_id))),
        tuple(chunks),
        len(objects),
        len(chunks),
        wire,
        index_root,
        manifest,
    )


def capture_empty_task_tx(conn, context: LockedAcceptContext):
    if not available(conn):
        if context.source_digest is not None:
            raise JournalError("signed audit acceptance requires execution007")
        return None
    existing = stream_tx(conn, context.scope_key)
    if existing is not None:
        if context.source_digest is None:
            raise JournalError("enabled task requires trusted signed acceptance material")
        return existing
    if context.source_digest is None:
        return None
    if context.tx_id != tx_id(conn):
        raise JournalError("bootstrap capture transaction mismatch")
    return _snapshot(conn, context.scope_key, context.root_grant_id, empty=True)


def _validate_seed(seed: EmptyTaskBootstrapSeed) -> None:
    """Recompute every complete snapshot bound before the first write."""
    if seed.origin not in ("FROM_EMPTY_TASK", "LEGACY_WITH_GAPS"):
        raise JournalError("bootstrap seed origin mismatch")
    if not 1 <= len(seed.objects) <= MAX_OBJECTS:
        raise JournalError("bootstrap object capacity mismatch")
    ordered = tuple(sorted(seed.objects, key=lambda obj: (obj.kind, obj.object_id)))
    if ordered != seed.objects or len({(obj.kind, obj.object_id) for obj in ordered}) != len(
        ordered
    ):
        raise JournalError("bootstrap object index mismatch")
    expected_chunks = []
    wire = 0
    index_root = sm3_b64url(
        canonical_json_bytes({"profile": "AG-BOOTSTRAP-INDEX-1", "scope": list(seed.scope_key)})
    )
    for obj in ordered:
        if (
            obj.kind not in OBJECT_LIMITS
            or not 1 <= len(obj.raw) <= OBJECT_LIMITS[obj.kind]
            or sm3_b64url(obj.raw) != obj.digest
        ):
            raise JournalError("bootstrap object bytes/digest mismatch")
        count = (len(obj.raw) + CHUNK_BYTES - 1) // CHUNK_BYTES
        index_root = sm3_b64url(
            canonical_json_bytes(
                {
                    "profile": "AG-BOOTSTRAP-INDEX-1",
                    "previous": index_root,
                    "kind": obj.kind,
                    "id": obj.object_id,
                    "total_raw_bytes": len(obj.raw),
                    "object_digest": obj.digest,
                    "chunk_count": count,
                }
            )
        )
        for i in range(count):
            chunk = SnapshotChunk(
                obj.kind,
                obj.object_id,
                i,
                count,
                len(obj.raw),
                obj.digest,
                obj.raw[i * CHUNK_BYTES : (i + 1) * CHUNK_BYTES],
            )
            expected_chunks.append(chunk)
            wire += (
                len(
                    canonical_json_bytes(
                        {
                            "frame_type": "OBJECT_CHUNK",
                            "object_kind": chunk.kind,
                            "object_id": chunk.object_id,
                            "chunk_index": i,
                            "chunk_count": count,
                            "total_raw_bytes": len(obj.raw),
                            "object_digest": obj.digest,
                            "data": b64url_encode(chunk.raw),
                        }
                    )
                )
                + 1
            )
    if (
        tuple(expected_chunks) != seed.chunks
        or not 1 <= len(expected_chunks) <= MAX_CHUNKS
        or not 1 <= wire <= MAX_WIRE_BYTES
    ):
        raise JournalError("bootstrap complete chunks/capacity mismatch")
    if (seed.object_count, seed.chunk_count, seed.wire_bytes, seed.index_root) != (
        len(ordered),
        len(expected_chunks),
        wire,
        index_root,
    ):
        raise JournalError("bootstrap counts/index/wire mismatch")
    manifest = canonical_json_bytes(
        {
            "profile": "AG-BOOTSTRAP-1",
            "scope": list(seed.scope_key),
            "root_grant_id": seed.root_grant_id,
            "snapshot_as_of": seed.captured_at,
            "origin": seed.origin,
            "object_count": len(ordered),
            "chunk_count": len(expected_chunks),
            "wire_bytes": wire,
            "index_root": index_root,
            "schema_lineage_digest": sm3_b64url(
                canonical_json_bytes([list(row) for row in seed.schema_lineage])
            ),
        }
    )
    if len(manifest) > 32768 or manifest != seed.manifest_bytes:
        raise JournalError("bootstrap manifest mismatch")


def ensure_stream_tx(conn, seed: EmptyTaskBootstrapSeed) -> ExistingStreamRef:
    if (
        type(seed) is not EmptyTaskBootstrapSeed
        or seed.tx_id != tx_id(conn)
        or seed.schema_lineage != _schema(conn)
    ):
        raise JournalError("bootstrap seed transaction/schema mismatch")
    _validate_seed(seed)
    if stream_tx(conn, seed.scope_key) is not None:
        raise JournalError("bootstrap cannot replace existing genesis")
    scope = JournalScope(*seed.scope_key, str(uuid.uuid4()), 1)
    genesis = genesis_digest(scope)
    bootstrap = sm3_b64url(seed.manifest_bytes)
    lineage_raw = canonical_json_bytes([list(row) for row in seed.schema_lineage])
    conn.execute(
        "INSERT INTO ag_audit_streams (stream_id,gateway_id,tenant_id,task_id,epoch,genesis_digest,"
        "bootstrap_digest,head_digest,created_xid) VALUES (%s,%s,%s,%s,1,%s,%s,%s,%s)",
        (scope.stream_id, *seed.scope_key, genesis, bootstrap, genesis, seed.tx_id),
    )
    boundary = "NEW_EMPTY" if seed.origin == "FROM_EMPTY_TASK" else "LEGACY_WITH_GAPS"
    conn.execute(
        "INSERT INTO ag_audit_bootstrap "
        "(stream_id,boundary,snapshot_as_of,root_grant_id,index_root,"
        "manifest_digest,manifest_bytes,schema_lineage_bytes,object_count,"
        "chunk_count,wire_bytes,created_xid) "
        "VALUES (" + ",".join(["%s"] * 12) + ")",
        (
            scope.stream_id,
            boundary,
            seed.captured_at,
            seed.root_grant_id,
            seed.index_root,
            bootstrap,
            seed.manifest_bytes,
            lineage_raw,
            seed.object_count,
            seed.chunk_count,
            seed.wire_bytes,
            seed.tx_id,
        ),
    )
    for chunk in seed.chunks:
        conn.execute(
            "INSERT INTO ag_audit_bootstrap_chunks "
            "(stream_id,object_kind,object_id,chunk_index,chunk_count,"
            "total_raw_bytes,object_digest,raw,created_xid) VALUES (" + ",".join(["%s"] * 9) + ")",
            (
                scope.stream_id,
                chunk.kind,
                chunk.object_id,
                chunk.index,
                chunk.count,
                chunk.total_raw_bytes,
                chunk.object_digest,
                chunk.raw,
                seed.tx_id,
            ),
        )
    conn.execute(
        "INSERT INTO ag_audit_delivery (stream_id,ack_head_digest) VALUES (%s,%s)",
        (scope.stream_id, genesis),
    )
    ref = ExistingStreamRef(scope, genesis, bootstrap)
    facts = {
        "boundary": boundary,
        "root_grant_id": seed.root_grant_id,
        "snapshot_as_of": seed.captured_at,
        "schema_lineage_digest": sm3_b64url(lineage_raw),
        "index_root": seed.index_root,
        "manifest_digest": bootstrap,
        "object_count": seed.object_count,
        "chunk_count": seed.chunk_count,
        "wire_bytes": seed.wire_bytes,
    }
    append_tx(
        conn,
        ref,
        kind="BOOTSTRAP",
        operation_id=None,
        evidence_ref=None,
        facts_bytes=canonical_json_bytes(facts),
    )
    return ref


def _material_tx(conn, kind, op_id, ref):
    material = {}
    if kind in ("FIRST", "RETRY", "QUERY"):
        row = conn.execute(
            "SELECT context_json,chain_json FROM ag_verified_evidence WHERE evidence_ref=%s",
            (ref,),
        ).fetchone()
        if row is None:
            raise JournalError("missing signed request material")
        material.update(context=b64url_encode(bytes(row[0])), source=b64url_encode(bytes(row[1])))
        if kind == "FIRST":
            operation = conn.execute(
                "SELECT quote_snapshot FROM ag_operations WHERE operation_id=%s",
                (op_id,),
            ).fetchone()
            if operation is None:
                raise JournalError("missing operation material")
            quote = operation[0]
            material["quote"] = None if quote is None else b64url_encode(bytes(quote))
    elif kind in ("TERMINAL", "PUBLISH"):
        row = conn.execute(
            "SELECT result_bytes,ledger_changes_json,receipt_jws FROM "
            "ag_receipt_outbox WHERE operation_id=%s",
            (op_id,),
        ).fetchone()
        if row is None:
            raise JournalError("missing final outbox material")
        if kind == "TERMINAL":
            material.update(
                result=b64url_encode(bytes(row[0])), ledger=b64url_encode(bytes(row[1]))
            )
        else:
            material["jws"] = row[2]
    return encode_material_projection(kind, material)


def append_tx(
    conn,
    stream: ExistingStreamRef,
    *,
    kind: str,
    operation_id: str | None,
    evidence_ref: str | None,
    facts_bytes: bytes,
):
    facts = load_strict_json(facts_bytes)
    if canonical_json_bytes(facts) != facts_bytes:
        raise JournalError("canonical facts required")
    material = _material_tx(conn, kind, operation_id, evidence_ref)
    # INSERT's FK checks acquire these same weak parent locks. Acquire them
    # before the head, in a fixed order, so a query holding an operation's
    # strong lock can append without forming a head -> operation cycle.
    for table, column, value in (
        ("ag_operations", "operation_id", operation_id),
        ("ag_verified_evidence", "evidence_ref", evidence_ref),
    ):
        if value is not None:
            row = conn.execute(
                f"SELECT {column} FROM {table} WHERE {column}=%s FOR KEY SHARE",
                (value,),
            ).fetchone()
            if row is None:
                raise JournalError("missing journal parent: " + table)
    head = conn.execute(
        "SELECT head_seq,head_digest FROM ag_audit_streams WHERE stream_id=%s FOR UPDATE",
        (stream.scope.stream_id,),
    ).fetchone()
    if head is None:
        raise JournalError("missing existing stream head")
    suffix = (
        stream.scope.stream_id
        if kind == "BOOTSTRAP"
        else evidence_ref
        if kind in ("RETRY", "QUERY")
        else facts["receipt_id"]
        if kind == "PUBLISH"
        else operation_id
    )
    at = utc_text(conn.execute("SELECT clock_timestamp()").fetchone()[0])
    raw = canonical_json_bytes(
        {
            **scope_object(stream.scope),
            "seq": head[0] + 1,
            "record_id": kind + ":" + suffix,
            "kind": kind,
            "operation_id": operation_id,
            "evidence_ref": evidence_ref,
            "previous_digest": head[1],
            "recorded_at": at,
            "facts": facts,
        }
    )
    record = decode_journal_record(raw)
    conn.execute(
        "INSERT INTO ag_audit_records (stream_id,seq,record_id,kind,operation_id,evidence_ref,"
        "previous_digest,digest,raw,material_binding_bytes,recorded_at,created_xid) "
        "VALUES (" + ",".join(["%s"] * 12) + ")",
        (
            stream.scope.stream_id,
            record.seq,
            record.record_id,
            kind,
            operation_id,
            evidence_ref,
            record.previous_digest,
            record.digest,
            raw,
            material,
            at,
            tx_id(conn),
        ),
    )
    conn.execute(
        "UPDATE ag_audit_streams SET head_seq=%s,head_digest=%s WHERE stream_id=%s",
        (record.seq, record.digest, stream.scope.stream_id),
    )
    return record


def bootstrap_task_tx(conn, *, scope_key: tuple[str, str, str]) -> RegistrationDescriptor:
    if not available(conn):
        raise JournalError("execution007 required")
    _, tenant, task = scope_key
    # Explicit maintenance entry point: caller must have stopped and drained all
    # writers. Table locks also drain transactions already touching these rows.
    conn.execute(
        "LOCK TABLE ag_tasks,ag_grants,ag_operations,ag_proofs,ag_operation_evidence,"
        "ag_execution_leases,ag_receipt_outbox IN EXCLUSIVE MODE"
    )
    row = conn.execute(
        "SELECT root_grant_id FROM ag_tasks WHERE tenant_id=%s AND task_id=%s FOR UPDATE",
        (tenant, task),
    ).fetchone()
    if row is None:
        raise JournalError("unknown maintenance task")
    for table, where in [
        ("ag_grants", "tenant_id=%s AND task_id=%s"),
        ("ag_operations", "tenant_id=%s AND task_id=%s"),
    ]:
        conn.execute(
            sql.SQL("SELECT 1 FROM {} WHERE " + where + " ORDER BY 1 FOR UPDATE").format(
                sql.Identifier(table)
            ),
            (tenant, task),
        ).fetchall()
    if stream_tx(conn, scope_key) is None:
        ensure_stream_tx(conn, _snapshot(conn, scope_key, row[0], empty=False))
    return describe_pending_tx(conn, scope_key=scope_key)


def describe_pending_tx(conn, *, scope_key) -> RegistrationDescriptor:
    ref = stream_tx(conn, scope_key)
    if ref is None:
        raise JournalError("task has no local bootstrap")
    row = conn.execute(
        "SELECT boundary,index_root,object_count,chunk_count,wire_bytes FROM ag_audit_bootstrap "
        "WHERE stream_id=%s",
        (ref.scope.stream_id,),
    ).fetchone()
    return RegistrationDescriptor(ref.scope, ref.genesis_digest, ref.bootstrap_digest, *row)


def accept_result_bytes(result) -> bytes:
    """Fixed internal DTO projection; preserve the independent logical quote cap."""
    from agent_guard.audit.contracts import identifier, integer
    from agent_guard.contracts.ledger import (
        AcceptDisposition,
        AcceptResult,
        TrustedCost,
    )

    if type(result) is not AcceptResult or type(result.cost) is not TrustedCost:
        raise JournalError("exact internal accept DTO required")
    from agent_guard.contracts.execution import OperationStatus

    if (
        type(result.disposition) is not AcceptDisposition
        or type(result.status) is not str
        or result.status not in {state.value for state in OperationStatus}
    ):
        raise JournalError("strict internal accept result state")
    for value in (result.operation_id, result.grant_id, result.root_id):
        identifier(value)
    integer(result.cost.amount_fen)
    integer(result.cost.calls)
    if result.cost.currency != "CNY":
        raise JournalError("strict internal accept currency")
    for value in (result.cost.quote_id, result.cost.quote_version):
        if value is not None:
            identifier(value)
    quote = result.cost.quote_snapshot
    if quote is not None and (type(quote) is not bytes or len(quote) > 65536):
        raise JournalError("internal accept quote logical capacity/type")
    cost = asdict(result.cost)
    cost["quote_snapshot"] = None
    value = {
        "operation_id": result.operation_id,
        "grant_id": result.grant_id,
        "root_id": result.root_id,
        "status": result.status,
        "disposition": result.disposition.value,
        "cost": cost,
        "accepted_at": utc_text(result.accepted_at),
    }
    metadata = canonical_json_bytes(value)
    if quote is None:
        return metadata
    cost["quote_snapshot"] = b64url_encode(quote)
    raw = rfc8785.dumps(value)
    # Replace literal null (4 bytes) by a quoted b64 string (2+encoded bytes).
    # B <= 65536; encoded <= ceil(65536*4/3)=87382; maximum 152916.
    if len(raw) != len(metadata) - 2 + len(cost["quote_snapshot"]) or len(raw) > 152916:
        raise JournalError("internal accept aggregate capacity")
    return raw


def request_facts(descriptor):
    return {
        "token_digest": descriptor.token_digest,
        "proof_digest": descriptor.proof_digest,
        "body_digest": descriptor.body_digest,
        "context_digest": sm3_b64url(descriptor.context_bytes),
        "source_digest": descriptor.source_digest,
        "source_material_digest": sm3_b64url(descriptor.source_material_bytes),
    }


def append_accept_tx(
    conn,
    baseline,
    operation,
    disposition,
    descriptor,
    result,
    response_bytes=None,
    *,
    introduced=(),
):
    if descriptor is None:
        if baseline is not None:
            raise JournalError("enabled acceptance lacks trusted descriptor")
        return
    ref = ensure_stream_tx(conn, baseline) if type(baseline) is EmptyTaskBootstrapSeed else baseline
    if ref is None:
        raise JournalError("signed acceptance requires immutable bootstrap")
    facts = request_facts(descriptor)
    if disposition.value == "CREATED":
        # Original reserve projection retains all root-to-leaf node values.
        nodes = conn.execute(
            "SELECT n.position,n.grant_id,n.amount_reserved_delta,n.amount_settled_delta,"
            "n.calls_reserved_delta,n.calls_settled_delta FROM ag_ledger_event_nodes n "
            "JOIN ag_ledger_events e ON e.event_id=n.event_id "
            "WHERE e.operation_id=%s AND e.phase='RESERVE' ORDER BY n.position",
            (operation.operation_id,),
        ).fetchall()
        reserve_raw = canonical_json_bytes([list(row) for row in nodes])
        facts.update(
            root_grant_id=descriptor.root_id,
            grant_id=operation.grant_id,
            path_ids=list(descriptor.path_ids),
            intent_digest=operation.intent_digest,
            reserve_digest=sm3_b64url(reserve_raw),
            quote_digest=None
            if operation.quote_snapshot is None
            else sm3_b64url(operation.quote_snapshot),
            amount_fen=operation.amount_fen,
            calls=operation.calls,
            currency=operation.currency,
            introduced_grants=[load_strict_json(x) for x in introduced],
        )
        kind = "FIRST"
    else:
        out = conn.execute(
            "SELECT receipt_status,receipt_jws FROM ag_receipt_outbox WHERE operation_id=%s",
            (operation.operation_id,),
        ).fetchone()
        receipt_status = out[0] if out else "PENDING"
        receipt_jws = out[1] if out else None
        if response_bytes is not None:
            response = load_strict_json(response_bytes)
            if (
                type(response) is not dict
                or set(response) != {"operation_id", "status", "receipt_status"}
                or canonical_json_bytes(response) != response_bytes
                or response["operation_id"] != operation.operation_id
                or response["status"] != operation.status
                or response["receipt_status"] not in ("PENDING", "READY")
            ):
                raise JournalError("strict captured accept response required")
            receipt_status = response["receipt_status"]
            if receipt_status == "PENDING":
                receipt_jws = None
            elif out is None or out[0] != "READY" or not receipt_jws:
                raise JournalError("captured READY response requires real immutable publication")
        facts.update(
            first_evidence_ref=operation.evidence_ref,
            intent_digest=operation.intent_digest,
            response_kind="ACCEPT_RESULT" if response_bytes is None else "ACCEPT_RESPONSE",
            response_digest=sm3_b64url(
                accept_result_bytes(result) if response_bytes is None else response_bytes
            ),
            status=operation.status,
            receipt_status=receipt_status,
            receipt_jws_digest=sm3_b64url(receipt_jws.encode("ascii")) if receipt_jws else None,
        )
        kind = "RETRY"
    append_tx(
        conn,
        ref,
        kind=kind,
        operation_id=operation.operation_id,
        evidence_ref=descriptor.evidence_ref,
        facts_bytes=canonical_json_bytes(facts),
    )


def append_terminal_tx(conn, operation, material, fence, path_ids, action):
    ref = require_stream_tx(conn, operation.tenant_id, operation.task_id)
    if ref is None:
        return
    from agent_guard.contracts.ledger_changes import (
        canonical_ledger_changes_bytes,
        load_ledger_changes,
    )

    first = conn.execute(
        "SELECT evidence_ref FROM ag_operation_evidence WHERE operation_id=%s AND kind='first'",
        (operation.operation_id,),
    ).fetchone()
    internal_ledger = load_ledger_changes(material.ledger_changes_json, internal=True)
    signed_ledger = {
        "operation_id": internal_ledger["operation_id"],
        "events": [
            {"phase": event["phase"], "nodes": event["nodes"]}
            for event in internal_ledger["events"]
        ],
    }
    # Preserve complete pending material rather than a subset of receipt claims.
    pending = {
        key: _json_value(value.value if hasattr(value, "value") else value)
        for key, value in asdict(material).items()
    }
    # Each original logical byte field keeps its existing independent 64KiB cap.
    # The two base64 strings can exceed the generic JSON object cap together.
    if any(len(raw) > 65536 for raw in (material.result_bytes, material.ledger_changes_json)):
        raise JournalError("pending receipt logical capacity exceeded")
    metadata = dict(pending)
    metadata.pop("result_bytes")
    metadata.pop("ledger_changes_json")
    metadata_raw = canonical_json_bytes(metadata)
    pending_raw = rfc8785.dumps(pending)
    # Replacing two absent entries costs exact key punctuation plus two b64 values.
    overhead = len(rfc8785.dumps({"result_bytes": "", "ledger_changes_json": ""})) - 1
    if len(pending_raw) > len(metadata_raw) + overhead + 2 * ((65536 * 4 + 2) // 3):
        raise JournalError("pending receipt aggregate capacity exceeded")
    facts = {
        "first_evidence_ref": first[0] if first else None,
        "status": material.status.value,
        "action": action.value,
        "result_digest": sm3_b64url(material.result_bytes),
        "ledger_digest": sm3_b64url(canonical_ledger_changes_bytes(signed_ledger)),
        "pending_receipt_digest": sm3_b64url(pending_raw),
        "receipt_id": material.receipt_id,
        "owner_token": fence.owner_token,
        "fencing_version": fence.fencing_version,
        "lease_expires_at": fence.expires_at,
        "path_ids": list(path_ids),
    }
    append_tx(
        conn,
        ref,
        kind="TERMINAL",
        operation_id=operation.operation_id,
        evidence_ref=first[0] if first else None,
        facts_bytes=canonical_json_bytes(facts),
    )


def capture_introduced_tx(conn, baseline, descriptor, grants) -> tuple[bytes, ...]:
    """Capture zero counters before reservation for genuine post-bootstrap nodes."""
    if type(baseline) is not ExistingStreamRef or descriptor is None:
        return ()
    rows = conn.execute(
        "SELECT object_id,chunk_index,raw FROM ag_audit_bootstrap_chunks "
        "WHERE stream_id=%s AND object_kind='typed_snapshot_metadata' "
        "ORDER BY object_id,chunk_index",
        (baseline.scope.stream_id,),
    ).fetchall()
    grouped = {}
    for ident, index, raw in rows:
        grouped.setdefault(ident, []).append((index, bytes(raw)))
    old_ids = set()
    for parts in grouped.values():
        metadata = load_strict_json(b"".join(raw for _, raw in sorted(parts)))
        if metadata["table"] == "ag_grants":
            old_ids.add(metadata["columns"]["grant_id"])
    if grants and all(grant.grant_id in old_ids for grant in grants):
        # Preserve the original FIRST snapshot cap without fetching or decoding
        # every prior record for paths authenticated in the immutable bootstrap.
        over_cap = conn.execute(
            "SELECT 1 FROM ag_audit_records WHERE stream_id=%s AND kind='FIRST' "
            "ORDER BY seq OFFSET %s LIMIT 1",
            (baseline.scope.stream_id, MAX_RECORDS),
        ).fetchone()
        if over_cap is not None:
            raise JournalError("journal snapshot cap exceeded")
        return ()
    # A node introduced by an earlier FIRST already has a documented origin.
    records = conn.execute(
        "SELECT raw FROM ag_audit_records WHERE stream_id=%s AND kind='FIRST' "
        "ORDER BY seq LIMIT %s",
        (baseline.scope.stream_id, MAX_RECORDS + 1),
    ).fetchall()
    if len(records) > MAX_RECORDS:
        raise JournalError("journal snapshot cap exceeded")
    for (raw,) in records:
        facts = load_strict_json(decode_journal_record(bytes(raw)).facts_bytes)
        old_ids.update(item["grant_id"] for item in facts["introduced_grants"])
    result = []
    for grant in grants:
        if grant.grant_id in old_ids:
            continue
        if any(
            getattr(grant, key) != 0
            for key in (
                "amount_reserved",
                "amount_settled",
                "calls_reserved",
                "calls_settled",
            )
        ):
            raise JournalError("introduced grant has nonzero pre-reservation counters")
        if conn.execute(
            "SELECT 1 FROM ag_operations WHERE grant_id=%s LIMIT 1", (grant.grant_id,)
        ).fetchone():
            raise JournalError("introduced grant has accepted history")
        token = conn.execute(
            "SELECT token_jws FROM ag_grant_tokens WHERE grant_id=%s", (grant.grant_id,)
        ).fetchone()
        if token is None or grant.grant_id not in descriptor.path_ids:
            raise JournalError("introduced grant lacks verified AS creation source")
        result.append(
            canonical_json_bytes(
                {
                    "grant_id": grant.grant_id,
                    "parent_id": grant.parent_grant_id,
                    "root_id": grant.root_grant_id,
                    "depth": grant.depth,
                    "holder_client_id": grant.holder_client_id,
                    "holder_kid": grant.holder_kid,
                    "grant_token_digest": sm3_b64url(token[0].encode("ascii")),
                    "source_material_digest": sm3_b64url(descriptor.source_material_bytes),
                    "amount_reserved": 0,
                    "amount_settled": 0,
                    "calls_reserved": 0,
                    "calls_settled": 0,
                }
            )
        )
    return tuple(result)
