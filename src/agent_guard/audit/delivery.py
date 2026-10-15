"""Crash-stable exact pending batches and independently authenticated ACKs."""

from __future__ import annotations

import weakref
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg

from agent_guard.audit.client import AuditUnavailable, ReconcileRequired
from agent_guard.audit.contracts import (
    CheckpointTrust,
    ExistingStreamRef,
    HistoryPage,
    JournalRecord,
    JournalScope,
    ObservedCheckpoint,
    PendingBatch,
    RecordPage,
    RegistrationDescriptor,
    VerifiedRemotePrefix,
    decode_append_batch,
    decode_checkpoint_claims,
    decode_journal_record,
    digest,
    encode_append_batch,
    genesis_digest,
    integer,
    utc_text,
)
from agent_guard.contracts.encoding import (
    EncodingError,
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.crypto.sm import load_sm2_public_key, sm3_b64url, verify_compact_jws


class DeliveryError(Exception):
    pass


def verify_checkpoint(
    jws: str, *, trust: tuple[CheckpointTrust, ...], expected_scope: JournalScope
) -> ObservedCheckpoint:
    if type(jws) is not str or not jws.isascii() or not 1 <= len(jws) <= 16384:
        raise DeliveryError("invalid checkpoint capacity")
    keys = {}
    for key in trust:
        if key.kid in keys or key.role != "AUDIT_SIGNER":
            raise DeliveryError("invalid external checkpoint trust")
        keys[key.kid] = load_sm2_public_key(key.spki_der)
    payload = verify_compact_jws(jws, expected_type="ag-checkpoint+jwt", trusted_keys=keys)
    raw = b64url_decode(jws.split(".")[1])
    claims = decode_checkpoint_claims(raw)
    header_raw = b64url_decode(jws.split(".")[0])
    header = load_strict_json(header_raw)
    if header_raw != canonical_json_bytes(header) or canonical_json_bytes(payload) != raw:
        raise DeliveryError("noncanonical checkpoint JWS")
    scope = JournalScope(
        claims.gateway_id,
        claims.tenant_id,
        claims.task_id,
        claims.stream_id,
        claims.epoch,
    )
    key = next((k for k in trust if k.kid == header["kid"]), None)
    if (
        scope != expected_scope
        or claims.kid != header["kid"]
        or key is None
        or type(key.first_sequence) is not int
        or key.first_sequence < 1
        or claims.sequence < key.first_sequence
        or (
            key.last_sequence is not None
            and (key.last_sequence < key.first_sequence or claims.sequence > key.last_sequence)
        )
    ):
        raise DeliveryError("checkpoint scope or trust range mismatch")
    return ObservedCheckpoint(
        jws,
        claims,
        sm3_b64url(jws.encode("ascii")),
        utc_text(datetime.now(timezone.utc)),
    )


def _one(conn, sql, args):
    row = conn.execute(sql, args).fetchone()
    if row is None:
        raise DeliveryError("audit delivery state missing")
    return row


def _pending(row):
    pending = PendingBatch(row[0], row[1], bytes(row[2]), *row[3:])
    batch = decode_append_batch(pending.exact_body)
    if (
        batch.stream_id,
        batch.batch_id,
        batch.start_sequence,
        batch.end_sequence,
        batch.end_digest,
    ) != (
        pending.stream_id,
        pending.batch_id,
        pending.start_sequence,
        pending.end_sequence,
        pending.end_digest,
    ):
        raise DeliveryError("persisted pending mismatch")
    return pending


def confirm_registered_tx(conn, *, descriptor: RegistrationDescriptor) -> bool:
    """Confirm trusted maintenance registration after its remote transaction commits.

    This is local operator input, not an independently signed audit receipt.
    The caller owns the transaction and must commit remote registration first.
    """
    if type(descriptor) is not RegistrationDescriptor or type(descriptor.scope) is not JournalScope:
        raise DeliveryError("exact registration descriptor required")
    scope = descriptor.scope
    # Reconstruct scope to apply its original strict UUID/origin/integer checks.
    JournalScope(scope.gateway_id, scope.tenant_id, scope.task_id, scope.stream_id, scope.epoch)
    for value in (descriptor.genesis_digest, descriptor.bootstrap_digest, descriptor.index_root):
        digest(value)
    for value, cap in (
        (descriptor.object_count, 200000),
        (descriptor.chunk_count, 400000),
        (descriptor.wire_bytes, 268435456),
    ):
        integer(value, minimum=1, maximum=cap)
    if descriptor.boundary not in (
        "NEW_EMPTY",
        "LEGACY_WITH_GAPS",
    ) or descriptor.genesis_digest != genesis_digest(scope):
        raise DeliveryError("invalid registration descriptor")
    row = _one(
        conn,
        "SELECT s.gateway_id,s.tenant_id,s.task_id,s.epoch,s.genesis_digest,"
        "s.bootstrap_digest,b.boundary,b.index_root,b.object_count,b.chunk_count,"
        "b.wire_bytes,s.created_xid,b.created_xid,pg_current_xact_id()::text "
        "FROM ag_audit_streams s JOIN ag_audit_bootstrap b USING(stream_id) "
        "WHERE s.stream_id=%s",
        (scope.stream_id,),
    )
    expected = (
        scope.gateway_id,
        scope.tenant_id,
        scope.task_id,
        scope.epoch,
        descriptor.genesis_digest,
        descriptor.bootstrap_digest,
        descriptor.boundary,
        descriptor.index_root,
        descriptor.object_count,
        descriptor.chunk_count,
        descriptor.wire_bytes,
    )
    if row[:11] != expected or row[11] != row[12] or row[11] == row[13]:
        raise DeliveryError("registration must match the committed local bootstrap")
    cursor = _one(
        conn,
        "SELECT ack_sequence,ack_head_digest,ack_checkpoint_digest,pending_batch_id,"
        "registration_state FROM ag_audit_delivery WHERE stream_id=%s FOR UPDATE",
        (scope.stream_id,),
    )
    if cursor[4] == "REGISTERED":
        return False
    if cursor != (0, descriptor.genesis_digest, None, None, "REGISTRATION_REQUIRED"):
        raise DeliveryError("registration requires the initial delivery cursor")
    conn.execute(
        "UPDATE ag_audit_delivery SET registration_state='REGISTERED' WHERE stream_id=%s",
        (scope.stream_id,),
    )
    return True


def prepare_pending_tx(conn, stream_id: str) -> PendingBatch | None:
    """Caller owns short transaction; lock only the delivery row."""
    cursor = _one(
        conn,
        "SELECT "
        "ack_sequence,ack_head_digest,ack_checkpoint_digest,pending_batch_id"
        ",registration_state FROM ag_audit_delivery WHERE stream_id=%s FOR UPDATE",
        (stream_id,),
    )
    if cursor[4] != "REGISTERED":
        raise DeliveryError("REGISTRATION_REQUIRED")
    if cursor[3] is not None:
        return _pending(
            _one(
                conn,
                "SELECT "
                "stream_id,batch_id,exact_body,start_sequence,end_sequence,e"
                "nd_digest,base_checkpoint_digest FROM ag_audit_delivery_batches "
                "WHERE stream_id=%s AND batch_id=%s",
                (stream_id, cursor[3]),
            )
        )
    rows = conn.execute(
        "SELECT raw FROM ag_audit_records WHERE stream_id=%s AND seq>%s ORDER BY seq LIMIT 64",
        (stream_id, cursor[0]),
    ).fetchall()
    entries = ()
    batch = None
    previous = cursor[1]
    for row in rows:
        raw = bytes(row[0])
        record = decode_journal_record(raw)
        if record.seq != cursor[0] + len(entries) + 1 or record.previous_digest != previous:
            raise DeliveryError("local journal gap or fork")
        # Exact canonical JSON size, including base64 expansion, quotes and commas.
        prospective = entries + (raw,)
        framing = len(
            canonical_json_bytes(
                {
                    "batch_profile": "AG-AUDIT-BATCH-1",
                    "stream_id": stream_id,
                    "entries": [],
                }
            )
        )
        encoded_size = (
            framing
            + sum(len(b64url_encode(item)) + 2 for item in prospective)
            + len(prospective)
            - 1
        )
        if encoded_size > 65536:
            if not entries:
                raise DeliveryError("single journal record exceeds encoded batch capacity")
            break
        candidate = encode_append_batch(stream_id, prospective)
        assert len(candidate.exact_body) == encoded_size
        entries += (raw,)
        batch = candidate
        previous = record.digest
    if batch is None:
        return None
    conn.execute(
        "INSERT INTO "
        "ag_audit_delivery_batches(stream_id,batch_id,exact_body,start_seque"
        "nce,end_sequence,end_digest,base_checkpoint_digest) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (
            stream_id,
            batch.batch_id,
            batch.exact_body,
            batch.start_sequence,
            batch.end_sequence,
            batch.end_digest,
            cursor[2],
        ),
    )
    conn.execute(
        "UPDATE ag_audit_delivery SET pending_batch_id=%s WHERE stream_id=%s",
        (batch.batch_id, stream_id),
    )
    return PendingBatch(
        stream_id,
        batch.batch_id,
        batch.exact_body,
        batch.start_sequence,
        batch.end_sequence,
        batch.end_digest,
        cursor[2],
    )


def ack_pending_tx(conn, pending: PendingBatch, checkpoint: ObservedCheckpoint) -> bool:
    """Authenticated checkpoint supplied by worker; exact match, monotonic CAS."""
    claims = checkpoint.claims
    if (
        claims.stream_id != pending.stream_id
        or claims.sequence != pending.end_sequence
        or claims.head_digest != pending.end_digest
        or claims.previous_checkpoint_digest != pending.base_checkpoint_digest
        or checkpoint.jws_digest != sm3_b64url(checkpoint.jws.encode("ascii"))
    ):
        raise DeliveryError("checkpoint does not acknowledge exact pending batch")
    cursor = _one(
        conn,
        "SELECT ack_sequence,ack_head_digest,ack_checkpoint_digest,pending_batch_id "
        "FROM ag_audit_delivery WHERE stream_id=%s FOR UPDATE",
        (pending.stream_id,),
    )
    if cursor[3] != pending.batch_id:
        return cursor[:3] == (
            pending.end_sequence,
            pending.end_digest,
            checkpoint.jws_digest,
        )
    stored = _pending(
        _one(
            conn,
            "SELECT "
            "stream_id,batch_id,exact_body,start_sequence,end_sequence,end_d"
            "igest,base_checkpoint_digest FROM ag_audit_delivery_batches WHERE "
            "stream_id=%s AND batch_id=%s",
            (pending.stream_id, pending.batch_id),
        )
    )
    if (
        stored != pending
        or cursor[0] + 1 != pending.start_sequence
        or cursor[2] != pending.base_checkpoint_digest
    ):
        raise DeliveryError("stale pending ACK")
    conn.execute(
        "UPDATE ag_audit_delivery_batches SET "
        "checkpoint_jws=%s,ack_at=clock_timestamp() WHERE stream_id=%s AND "
        "batch_id=%s AND checkpoint_jws IS NULL",
        (checkpoint.jws, pending.stream_id, pending.batch_id),
    )
    conn.execute(
        "UPDATE ag_audit_delivery SET "
        "ack_sequence=%s,ack_head_digest=%s,ack_checkpoint_digest=%s,pending"
        "_batch_id=NULL WHERE stream_id=%s AND pending_batch_id=%s",
        (
            pending.end_sequence,
            pending.end_digest,
            checkpoint.jws_digest,
            pending.stream_id,
            pending.batch_id,
        ),
    )
    return True


def reconcile_remote_ahead(
    local_records: tuple[JournalRecord, ...],
    observed: ObservedCheckpoint,
    history_pages: tuple[HistoryPage, ...],
    record_pages: tuple[RecordPage, ...],
    trust: tuple[CheckpointTrust, ...],
    *,
    expected_stream: ExistingStreamRef,
) -> VerifiedRemotePrefix:
    scope = expected_stream.scope
    verified = verify_checkpoint(observed.jws, trust=trust, expected_scope=scope)
    if (
        verified.claims != observed.claims
        or verified.jws_digest != observed.jws_digest
        or expected_stream.genesis_digest != genesis_digest(scope)
    ):
        raise DeliveryError("inconsistent observed checkpoint or genesis")
    boundary, pin = verified.claims.sequence, verified.claims.checkpoint_id
    if not history_pages or not record_pages or len(local_records) < boundary:
        raise DeliveryError("incomplete remote proof")
    cps = []
    previous_cp = None
    last = 0
    for index, page in enumerate(history_pages):
        canonical_json_bytes(
            {
                "stream_id": page.stream_id,
                "observed_checkpoint_id": page.observed_checkpoint_id,
                "observed_sequence": page.observed_sequence,
                "checkpoints": list(page.checkpoints),
                "next_after_sequence": page.next_after_sequence,
            }
        )
        if (page.stream_id, page.observed_checkpoint_id, page.observed_sequence) != (
            scope.stream_id,
            pin,
            boundary,
        ) or not 1 <= len(page.checkpoints) <= 64:
            raise DeliveryError("history pin mismatch")
        for jws in page.checkpoints:
            cp = verify_checkpoint(jws, trust=trust, expected_scope=scope)
            if (
                cp.claims.sequence <= last
                or cp.claims.sequence > boundary
                or cp.claims.previous_checkpoint_digest != previous_cp
            ):
                raise DeliveryError("checkpoint history gap or reorder")
            cps.append(cp)
            last = cp.claims.sequence
            previous_cp = cp.jws_digest
        if page.next_after_sequence != (last if index < len(history_pages) - 1 else None):
            raise DeliveryError("history cursor mismatch")
    if cps[-1].jws != verified.jws:
        raise DeliveryError("history does not reach observed original JWS")
    remote = []
    for index, page in enumerate(record_pages):
        canonical_json_bytes(
            {
                "stream_id": page.stream_id,
                "observed_checkpoint_id": page.observed_checkpoint_id,
                "observed_sequence": page.observed_sequence,
                "entries": [b64url_encode(raw) for raw in page.entries],
                "next_after_sequence": page.next_after_sequence,
            }
        )
        if (page.stream_id, page.observed_checkpoint_id, page.observed_sequence) != (
            scope.stream_id,
            pin,
            boundary,
        ) or not 1 <= len(page.entries) <= 64:
            raise DeliveryError("records pin mismatch")
        remote.extend(decode_journal_record(raw) for raw in page.entries)
        if page.next_after_sequence != (remote[-1].seq if index < len(record_pages) - 1 else None):
            raise DeliveryError("record cursor mismatch")
    if len(remote) != boundary:
        raise DeliveryError("incomplete record prefix")
    previous = expected_stream.genesis_digest
    for seq, record in enumerate(remote, 1):
        local = decode_journal_record(local_records[seq - 1].raw)
        if (
            local != local_records[seq - 1]
            or record != local
            or record.scope != scope
            or record.seq != seq
            or record.previous_digest != previous
        ):
            raise DeliveryError("remote/local journal fork or gap")
        if seq == 1:
            facts = load_strict_json(record.facts_bytes)
            if (
                record.kind != "BOOTSTRAP"
                or facts["manifest_digest"] != expected_stream.bootstrap_digest
            ):
                raise DeliveryError("bootstrap mismatch")
        previous = record.digest
    for cp in cps:
        if remote[cp.claims.sequence - 1].digest != cp.claims.head_digest:
            raise DeliveryError("checkpoint journal boundary mismatch")
    return VerifiedRemotePrefix(scope, boundary, previous, verified.jws, verified.jws_digest)


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class AuthenticatedReconciliation:
    """Internal factory capability, containing only immutable authenticated values."""

    expected_stream: ExistingStreamRef
    prefix: VerifiedRemotePrefix
    local_raw: tuple[bytes, ...]
    checkpoint_digests: tuple[str, ...]


# Identity, rather than an inheritable/copyable field, proves factory provenance.
# Weak references retain no unbounded proof cache and cannot authorize copied DTOs.
_AUTHENTICATED = weakref.WeakValueDictionary()


def authenticate_reconciliation(
    local_records, observed, history_pages, record_pages, trust, *, expected_stream
) -> AuthenticatedReconciliation:
    if (
        type(expected_stream) is not ExistingStreamRef
        or type(expected_stream.scope) is not JournalScope
    ):
        raise DeliveryError("immutable local stream reference required")
    scope = expected_stream.scope
    # Do not retain the caller's nested reference, even for immutable public DTOs.
    expected_stream = ExistingStreamRef(
        JournalScope(
            scope.gateway_id, scope.tenant_id, scope.task_id, scope.stream_id, scope.epoch
        ),
        expected_stream.genesis_digest,
        expected_stream.bootstrap_digest,
    )
    prefix = reconcile_remote_ahead(
        local_records,
        observed,
        history_pages,
        record_pages,
        trust,
        expected_stream=expected_stream,
    )
    previous = expected_stream.genesis_digest
    local_raw = []
    for seq, supplied in enumerate(local_records, 1):
        record = decode_journal_record(supplied.raw)
        if (
            record != supplied
            or record.seq != seq
            or record.scope != expected_stream.scope
            or record.previous_digest != previous
        ):
            raise DeliveryError("inconsistent local reconciliation chain")
        local_raw.append(record.raw)
        previous = record.digest
    # Reparse originals, never use a caller's claims or membership assertion.
    digests = tuple(
        verify_checkpoint(jws, trust=trust, expected_scope=expected_stream.scope).jws_digest
        for page in history_pages
        for jws in page.checkpoints
    )
    proof = AuthenticatedReconciliation(expected_stream, prefix, tuple(local_raw), digests)
    _AUTHENTICATED[id(proof)] = proof
    return proof


def _authenticated(proof):
    if type(proof) is not AuthenticatedReconciliation or _AUTHENTICATED.get(id(proof)) is not proof:
        raise DeliveryError("authenticated reconciliation capability required")


def _reconciled_parent(conn, parent, proof):
    _authenticated(proof)
    batch = decode_append_batch(parent.exact_body)
    prefix = proof.prefix
    if (
        parent.stream_id != proof.expected_stream.scope.stream_id
        or parent
        != PendingBatch(
            batch.stream_id,
            batch.batch_id,
            batch.exact_body,
            batch.start_sequence,
            batch.end_sequence,
            batch.end_digest,
            parent.base_checkpoint_digest,
        )
        or parent.base_checkpoint_digest is not None
        and parent.base_checkpoint_digest not in proof.checkpoint_digests
        or prefix.sequence < parent.start_sequence - 1
        or tuple(proof.local_raw[parent.start_sequence - 1 : parent.end_sequence]) != batch.entries
    ):
        raise DeliveryError("pending reconciliation binding mismatch")
    cursor = _one(
        conn,
        "SELECT ack_sequence,ack_head_digest,ack_checkpoint_digest,pending_batch_id "
        "FROM ag_audit_delivery WHERE stream_id=%s FOR UPDATE",
        (parent.stream_id,),
    )
    stored = _pending(
        _one(
            conn,
            "SELECT stream_id,batch_id,exact_body,start_sequence,end_sequence,end_digest,"
            "base_checkpoint_digest FROM ag_audit_delivery_batches "
            "WHERE stream_id=%s AND batch_id=%s",
            (parent.stream_id, parent.batch_id),
        )
    )
    if stored != parent:
        raise DeliveryError("changed reconciliation parent")
    # Current immutable journal bytes must still be the factory-bound exact slice.
    rows = conn.execute(
        "SELECT raw FROM ag_audit_records WHERE stream_id=%s "
        "AND seq BETWEEN %s AND %s ORDER BY seq",
        (parent.stream_id, parent.start_sequence, parent.end_sequence),
    ).fetchall()
    if tuple(bytes(row[0]) for row in rows) != batch.entries:
        raise DeliveryError("local reconciliation slice mismatch")
    if cursor[3] != parent.batch_id:
        return None
    if (
        cursor[0] + 1 != parent.start_sequence
        or cursor[2] != parent.base_checkpoint_digest
        or cursor[1] != decode_journal_record(batch.entries[0]).previous_digest
    ):
        raise DeliveryError("stale reconciliation parent")
    return batch


def prepare_reconciliation_child_tx(conn, parent, proof) -> PendingBatch | None:
    """Persist a deterministic suffix without changing the parent or its cursor."""
    batch = _reconciled_parent(conn, parent, proof)
    if batch is None or proof.prefix.sequence >= parent.end_sequence:
        return None
    child_batch = encode_append_batch(
        parent.stream_id,
        batch.entries[proof.prefix.sequence - parent.start_sequence + 1 :],
    )
    child = PendingBatch(
        child_batch.stream_id,
        child_batch.batch_id,
        child_batch.exact_body,
        child_batch.start_sequence,
        child_batch.end_sequence,
        child_batch.end_digest,
        proof.prefix.checkpoint_digest,
    )
    conn.execute(
        "INSERT INTO ag_audit_delivery_batches(stream_id,batch_id,exact_body,start_sequence,"
        "end_sequence,end_digest,base_checkpoint_digest) VALUES (%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (stream_id,batch_id) DO NOTHING",
        (
            child.stream_id,
            child.batch_id,
            child.exact_body,
            child.start_sequence,
            child.end_sequence,
            child.end_digest,
            child.base_checkpoint_digest,
        ),
    )
    stored = _pending(
        _one(
            conn,
            "SELECT stream_id,batch_id,exact_body,start_sequence,end_sequence,end_digest,"
            "base_checkpoint_digest FROM ag_audit_delivery_batches "
            "WHERE stream_id=%s AND batch_id=%s",
            (child.stream_id, child.batch_id),
        )
    )
    completion = _one(
        conn,
        "SELECT checkpoint_jws,ack_at FROM ag_audit_delivery_batches "
        "WHERE stream_id=%s AND batch_id=%s",
        (child.stream_id, child.batch_id),
    )
    if stored != child or completion != (None, None):
        raise DeliveryError("reconciliation child collision")
    return stored


def ack_reconciled_pending_tx(conn, parent, proof) -> bool:
    """A covering original CP acknowledges only the exact immutable parent end."""
    batch = _reconciled_parent(conn, parent, proof)
    if proof.prefix.sequence < parent.end_sequence:
        raise DeliveryError("proof does not cover parent")
    if batch is None:
        return False
    conn.execute(
        "UPDATE ag_audit_delivery_batches SET checkpoint_jws=%s,ack_at=clock_timestamp() "
        "WHERE stream_id=%s AND batch_id=%s AND checkpoint_jws IS NULL",
        (proof.prefix.checkpoint_jws, parent.stream_id, parent.batch_id),
    )
    conn.execute(
        "UPDATE ag_audit_delivery SET ack_sequence=%s,ack_head_digest=%s,ack_checkpoint_digest=%s,"
        "pending_batch_id=NULL WHERE stream_id=%s AND pending_batch_id=%s",
        (
            parent.end_sequence,
            parent.end_digest,
            proof.prefix.checkpoint_digest,
            parent.stream_id,
            parent.batch_id,
        ),
    )
    return True


@dataclass(frozen=True)
class DeliveryOutcome:
    status: str
    stream_id: str


class DeliveryWorker:
    def __init__(self, connect, client, *, trust: tuple[CheckpointTrust, ...]):
        self.connect, self.client, self.trust = connect, client, trust

    def _proof(self, stream_id):
        # Snapshot local immutable data, close DB, then independently pin every reader page.
        with self.connect() as conn:
            row = _one(
                conn,
                "SELECT gateway_id,tenant_id,task_id,epoch,genesis_digest,"
                "bootstrap_digest FROM ag_audit_streams WHERE stream_id=%s",
                (stream_id,),
            )
            records = tuple(
                decode_journal_record(bytes(r[0]))
                for r in conn.execute(
                    "SELECT raw FROM ag_audit_records WHERE stream_id=%s ORDER BY seq",
                    (stream_id,),
                ).fetchall()
            )
        scope = JournalScope(row[0], row[1], row[2], stream_id, row[3])
        stream = ExistingStreamRef(scope, row[4], row[5])
        jws = self.client.latest(stream_id)
        if jws is None:
            raise DeliveryError("remote checkpoint required")
        observed = verify_checkpoint(jws, trust=self.trust, expected_scope=scope)
        if observed.claims.sequence > len(records):
            raise DeliveryError("remote prefix exceeds local journal")
        families = []
        for read in (self.client.history, self.client.records):
            pages, after = [], 0
            # Both page families must advance. No 409 chase, no unbounded reader loop.
            for _ in range(observed.claims.sequence):
                page = read(
                    stream_id,
                    observed_checkpoint_id=observed.claims.checkpoint_id,
                    after_sequence=after,
                )
                pages.append(page)
                next_after = page.next_after_sequence
                if next_after is None:
                    break
                if (
                    type(next_after) is not int
                    or not after < next_after <= observed.claims.sequence
                ):
                    raise DeliveryError("nonadvancing remote page")
                after = next_after
            else:
                raise DeliveryError("remote page capacity exceeded")
            families.append(tuple(pages))
        return authenticate_reconciliation(
            records, observed, *families, self.trust, expected_stream=stream
        )

    def _reconcile(self, pending):
        proof = self._proof(pending.stream_id)
        if proof.prefix.sequence < pending.end_sequence:
            with self.connect() as conn:
                with conn.transaction():
                    child = prepare_reconciliation_child_tx(conn, pending, proof)
            if child is None:
                return DeliveryOutcome("RECONCILE_REQUIRED", pending.stream_id)
            # Child reply never grants parent ACK authority. All locks are released.
            jws = self.client.append(decode_append_batch(child.exact_body))
            cp = verify_checkpoint(
                jws, trust=self.trust, expected_scope=proof.expected_stream.scope
            )
            if (
                cp.claims.sequence != child.end_sequence
                or cp.claims.head_digest != child.end_digest
                or cp.claims.previous_checkpoint_digest != child.base_checkpoint_digest
            ):
                raise DeliveryError("child checkpoint mismatch")
            proof = self._proof(pending.stream_id)
        with self.connect() as conn:
            with conn.transaction():
                acked = ack_reconciled_pending_tx(conn, pending, proof)
        return DeliveryOutcome("ACKED" if acked else "RECONCILE_REQUIRED", pending.stream_id)

    def deliver_once(self, stream_id: str) -> DeliveryOutcome:
        try:
            with self.connect() as conn:
                with conn.transaction():
                    pending = prepare_pending_tx(conn, stream_id)
            if pending is None:
                return DeliveryOutcome("NO_PENDING", stream_id)
            batch = decode_append_batch(pending.exact_body)
            # Connection and transaction have exited before every network operation.
            try:
                jws = self.client.append(batch)
            except ReconcileRequired:
                return self._reconcile(pending)
            scope = decode_journal_record(batch.entries[0]).scope
            cp = verify_checkpoint(jws, trust=self.trust, expected_scope=scope)
            with self.connect() as conn:
                with conn.transaction():
                    acked = ack_pending_tx(conn, pending, cp)
            return DeliveryOutcome("ACKED" if acked else "RECONCILE_REQUIRED", stream_id)
        except ReconcileRequired:
            return DeliveryOutcome("RECONCILE_REQUIRED", stream_id)
        except AuditUnavailable:
            return DeliveryOutcome("UNAVAILABLE", stream_id)
        except DeliveryError as exc:
            if str(exc) == "REGISTRATION_REQUIRED":
                return DeliveryOutcome("REGISTRATION_REQUIRED", stream_id)
            raise

    def deliver_round(self, stream_ids: tuple[str, ...]) -> tuple[DeliveryOutcome, ...]:
        # Finite single attempt per stream; failures cannot consume an unbounded retry loop.
        outcomes = []
        self.database_failures = []
        for stream_id in stream_ids:
            try:
                outcomes.append(self.deliver_once(stream_id))
            except psycopg.Error as exc:
                # The connection/transaction context has exited before this boundary.
                # Keep original errors for the trusted owner; outward result stays sanitized.
                self.database_failures.append((stream_id, exc, exc.sqlstate))
                outcomes.append(DeliveryOutcome("UNAVAILABLE", stream_id))
            except (DeliveryError, EncodingError, ValueError):
                outcomes.append(DeliveryOutcome("UNAVAILABLE", stream_id))
        return tuple(outcomes)
