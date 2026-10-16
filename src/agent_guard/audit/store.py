"""Independent atomic checkpoint store. Network operations never hold its locks."""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from dataclasses import asdict

import psycopg

from agent_guard.audit.checkpoint import sign_checkpoint, verify_checkpoint
from agent_guard.audit.contracts import (
    CheckpointClaims,
    CheckpointTrust,
    JournalScope,
    RegistrationDescriptor,
    decode_append_batch,
    decode_journal_record,
    digest,
    genesis_digest,
    identifier,
    integer,
    utc_text,
)
from agent_guard.audit.migrate import require_domain
from agent_guard.contracts.encoding import EncodingError, b64url_encode, canonical_json_bytes
from agent_guard.crypto.sm import load_sm2_public_key, serialize_sm2_public_key


class AuditStoreError(ValueError):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


def credential_verifier(credential: str) -> bytes:
    if (
        type(credential) is not str
        or not 32 <= len(credential) <= 512
        or re.fullmatch(r"[A-Za-z0-9_-]{32,512}", credential) is None
    ):
        raise AuditStoreError("INVALID_CREDENTIAL", 401)
    return hashlib.sha256(credential.encode("ascii")).digest()


class AuditStore:
    def __init__(
        self,
        dsn: str,
        *,
        owner_role: str,
        private_key,
        key_id: str,
        external_pins: tuple[str, ...] = (),
        external_trust: tuple[CheckpointTrust, ...] = (),
    ):
        self.dsn, self.owner_role, self.private_key, self.key_id = (
            dsn,
            owner_role,
            private_key,
            identifier(key_id, maximum=128),
        )
        self.external_pins, self.external_trust = external_pins, external_trust
        self.rollback_assurance = "MINIMUM_ONLY" if external_pins else "UNKNOWN"
        with self.connect() as conn:
            require_domain(conn, owner_role=owner_role)
            self._check_key(conn)
            self._pins(conn)

    def connect(self):
        from psycopg.conninfo import conninfo_to_dict

        options = conninfo_to_dict(self.dsn).get("options", "")
        return psycopg.connect(
            self.dsn,
            connect_timeout=5,
            options=options + " -c lock_timeout=3000 -c statement_timeout=30000",
        )

    def _check_key(self, conn):
        row = conn.execute(
            "SELECT role,spki_der,first_sequence,last_sequence FROM ag_audit_c"
            "heckpoint_keys WHERE kid=%s FOR SHARE",
            (self.key_id,),
        ).fetchone()
        if (
            row is None
            or row[0] != "AUDIT_SIGNER"
            or bytes(row[1]) != serialize_sm2_public_key(self.private_key.public_key())
        ):
            raise AuditStoreError("SIGNER_NOT_REGISTERED", 503)
        return CheckpointTrust(self.key_id, row[0], bytes(row[1]), row[2], row[3])

    def _pins(self, conn):
        for pin in self.external_pins:
            # The operator supplies the expected scope from the immutable registry;
            # no key or scope from a pin is promoted to trust.
            from agent_guard.audit.contracts import decode_checkpoint_claims
            from agent_guard.contracts.encoding import b64url_decode

            claims = decode_checkpoint_claims(b64url_decode(pin.split(".")[1]))
            row = self._stream(conn, claims.stream_id)
            scope = self._scope(row)
            observed = verify_checkpoint(pin, trust=self.external_trust, expected_scope=scope)
            if row[7] < observed.claims.sequence:
                raise AuditStoreError("EXTERNAL_PIN_ROLLBACK", 503)
            local = conn.execute(
                "SELECT digest FROM ag_checkpoint_records WHERE stream_id=%s AND seq=%s",
                (claims.stream_id, claims.sequence),
            ).fetchone()
            cp = conn.execute(
                "SELECT jws FROM ag_checkpoints WHERE stream_id=%s AND sequence=%s",
                (claims.stream_id, claims.sequence),
            ).fetchone()
            if local is None or local[0] != claims.head_digest or cp is None or cp[0] != pin:
                raise AuditStoreError("EXTERNAL_PIN_FORK", 503)

    @staticmethod
    def _scope(row):
        return JournalScope(row[1], row[2], row[3], row[0], row[4])

    @staticmethod
    def _stream(conn, stream_id, *, lock=False):
        row = conn.execute(
            "SELECT stream_id,gateway_id,tenant_id,task_id,epoch,genesis_diges"
            "t,bootstrap_digest,latest_sequence,latest_digest,latest_checkpoin"
            "t_id,boundary,public_descriptor FROM ag_checkpoint_streams WHERE "
            "stream_id=%s" + (" FOR UPDATE" if lock else ""),
            (identifier(stream_id),),
        ).fetchone()
        if row is None:
            raise AuditStoreError("REGISTRATION_REQUIRED", 404)
        return row

    @staticmethod
    def authorize(conn, credential_id, credential, stream_id, role):
        row = conn.execute(
            "SELECT role,credential_verifier,stream_id FROM ag_audit_principal"
            "s WHERE credential_id=%s",
            (identifier(credential_id),),
        ).fetchone()
        candidate = credential_verifier(credential)
        if row is None or not hmac.compare_digest(bytes(row[1]), candidate):
            raise AuditStoreError("UNAUTHORIZED", 401)
        if row[0] != role or row[2] != stream_id:
            raise AuditStoreError("FORBIDDEN", 403)

    def append(self, raw: bytes, *, credential_id: str, credential: str) -> str:
        batch = decode_append_batch(raw)
        with self.connect() as conn, conn.transaction():
            self.authorize(conn, credential_id, credential, batch.stream_id, "WRITER")
            row = self._stream(conn, batch.stream_id, lock=True)
            self._pins(conn)
            old = conn.execute(
                "SELECT b.exact_body,c.jws FROM ag_checkpoint_batches b JOIN ag_ch"
                "eckpoints c ON c.checkpoint_id=b.checkpoint_id WHERE b.stream_id="
                "%s AND b.batch_id=%s",
                (batch.stream_id, batch.batch_id),
            ).fetchone()
            if old:
                if bytes(old[0]) != raw:
                    raise AuditStoreError("BATCH_COLLISION", 409)
                return old[1]
            if batch.start_sequence != row[7] + 1:
                raise AuditStoreError("RECONCILE_REQUIRED", 409)
            scope, previous = self._scope(row), row[8]
            for entry in batch.entries:
                record = decode_journal_record(entry)
                if record.scope != scope or record.previous_digest != previous:
                    raise AuditStoreError("JOURNAL_FORK", 409)
                if record.seq == 1:
                    if record.kind != "BOOTSTRAP":
                        raise AuditStoreError("BOOTSTRAP_BINDING", 409)
                    from agent_guard.contracts.encoding import load_strict_json

                    facts = load_strict_json(entry)["facts"]
                    desc = load_strict_json(bytes(row[11]))
                    if facts["manifest_digest"] != row[6] or any(
                        facts[k] != desc[k]
                        for k in (
                            "boundary",
                            "index_root",
                            "object_count",
                            "chunk_count",
                            "wire_bytes",
                        )
                    ):
                        raise AuditStoreError("BOOTSTRAP_DESCRIPTOR", 409)
                conn.execute(
                    "INSERT INTO ag_checkpoint_records(stream_id,seq,raw,digest,previo"
                    "us_digest,record_id) VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        batch.stream_id,
                        record.seq,
                        entry,
                        record.digest,
                        record.previous_digest,
                        record.record_id,
                    ),
                )
                previous = record.digest
            key = self._check_key(conn)
            previous_cp = (
                None
                if row[9] is None
                else conn.execute(
                    "SELECT jws_digest FROM ag_checkpoints WHERE checkpoint_id=%s", (row[9],)
                ).fetchone()[0]
            )
            now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
            claims = CheckpointClaims(
                "GM-MVP-1",
                "AG-CHECKPOINT-1",
                str(uuid.uuid4()),
                batch.stream_id,
                scope.gateway_id,
                scope.tenant_id,
                scope.task_id,
                scope.epoch,
                batch.end_sequence,
                batch.end_digest,
                previous_cp,
                utc_text(now),
                self.key_id,
            )
            jws = sign_checkpoint(claims, private_key=self.private_key, key_id=self.key_id)
            observed = verify_checkpoint(jws, trust=(key,), expected_scope=scope)
            conn.execute(
                "INSERT INTO ag_checkpoints(checkpoint_id,stream_id,sequence,head_"
                "digest,previous_checkpoint_digest,issued_at,kid,jws,jws_digest) V"
                "ALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    claims.checkpoint_id,
                    batch.stream_id,
                    claims.sequence,
                    claims.head_digest,
                    previous_cp,
                    now,
                    self.key_id,
                    jws,
                    observed.jws_digest,
                ),
            )
            conn.execute(
                "INSERT INTO ag_checkpoint_batches(stream_id,batch_id,exact_body,s"
                "tart_sequence,end_sequence,end_digest,checkpoint_id) VALUES (%s,%"
                "s,%s,%s,%s,%s,%s)",
                (
                    batch.stream_id,
                    batch.batch_id,
                    raw,
                    batch.start_sequence,
                    batch.end_sequence,
                    batch.end_digest,
                    claims.checkpoint_id,
                ),
            )
            conn.execute(
                "UPDATE ag_checkpoint_streams SET latest_sequence=%s,latest_digest"
                "=%s,latest_checkpoint_id=%s WHERE stream_id=%s",
                (batch.end_sequence, batch.end_digest, claims.checkpoint_id, batch.stream_id),
            )
        return jws

    def latest(self, stream_id, *, credential_id, credential):
        with self.connect() as conn:
            self.authorize(conn, credential_id, credential, stream_id, "READER")
            row = self._stream(conn, stream_id)
            if row[9] is None:
                return None
            return conn.execute(
                "SELECT jws FROM ag_checkpoints WHERE checkpoint_id=%s", (row[9],)
            ).fetchone()[0]

    def page(
        self,
        stream_id,
        *,
        observed_checkpoint_id,
        after_sequence,
        credential_id,
        credential,
        records=False,
    ):
        identifier(observed_checkpoint_id)
        integer(after_sequence)
        with self.connect() as conn:
            self.authorize(conn, credential_id, credential, stream_id, "READER")
            row = conn.execute(
                "SELECT sequence FROM ag_checkpoints WHERE stream_id=%s AND checkpoint_id=%s",
                (stream_id, observed_checkpoint_id),
            ).fetchone()
            if row is None:
                raise AuditStoreError("UNKNOWN_OBSERVATION", 404)
            boundary = row[0]
            if after_sequence >= boundary:
                raise AuditStoreError("INVALID_CURSOR")
            table, column = (
                ("ag_checkpoint_records", "raw") if records else ("ag_checkpoints", "jws")
            )
            sequence = "seq" if records else "sequence"
            rows = conn.execute(
                f"SELECT {sequence},{column} FROM {table} WHERE stream_id=%s AND "
                f"{sequence}>%s AND {sequence}<=%s ORDER BY {sequence} LIMIT 64",
                (stream_id, after_sequence, boundary),
            ).fetchall()
            if not rows or (records and rows[0][0] != after_sequence + 1):
                raise AuditStoreError("MISSING_PREFIX", 409)
            values = []
            result = None
            for seq, value in rows:
                values.append(b64url_encode(bytes(value)) if records else value)
                candidate = {
                    "stream_id": stream_id,
                    "observed_checkpoint_id": observed_checkpoint_id,
                    "observed_sequence": boundary,
                    "entries" if records else "checkpoints": values[:],
                    "next_after_sequence": None if seq == boundary else seq,
                }
                try:
                    wire = canonical_json_bytes(candidate)
                except EncodingError:
                    break
                if len(wire) > 65536:
                    break
                result = wire
            if result is None:
                raise AuditStoreError("PAGE_CAPACITY")
            return result


def register_stream(conn, descriptor: RegistrationDescriptor):
    scope = descriptor.scope
    digest(descriptor.genesis_digest)
    digest(descriptor.bootstrap_digest)
    digest(descriptor.index_root)
    if descriptor.genesis_digest != genesis_digest(scope) or descriptor.boundary not in (
        "NEW_EMPTY",
        "LEGACY_WITH_GAPS",
    ):
        raise EncodingError("invalid registration descriptor")
    for value, cap in (
        (descriptor.object_count, 200000),
        (descriptor.chunk_count, 400000),
        (descriptor.wire_bytes, 268435456),
    ):
        integer(value, maximum=cap)
    raw = canonical_json_bytes({**asdict(descriptor), "scope": asdict(scope)})
    if len(raw) > 32768:
        raise EncodingError("registration capacity")
    existing = conn.execute(
        "SELECT public_descriptor FROM ag_checkpoint_streams WHERE stream_"
        "id=%s OR (gateway_id=%s AND tenant_id=%s AND task_id=%s)",
        (scope.stream_id, scope.gateway_id, scope.tenant_id, scope.task_id),
    ).fetchall()
    if existing:
        if len(existing) != 1 or bytes(existing[0][0]) != raw:
            raise AuditStoreError("REGISTRATION_CONFLICT", 409)
        return False
    conn.execute(
        "INSERT INTO ag_checkpoint_streams(stream_id,gateway_id,tenant_id,"
        "task_id,epoch,genesis_digest,bootstrap_digest,boundary,public_des"
        "criptor,latest_digest) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            scope.stream_id,
            scope.gateway_id,
            scope.tenant_id,
            scope.task_id,
            scope.epoch,
            descriptor.genesis_digest,
            descriptor.bootstrap_digest,
            descriptor.boundary,
            raw,
            descriptor.genesis_digest,
        ),
    )
    return True


def register_key(conn, trust: CheckpointTrust):
    identifier(trust.kid, maximum=128)
    if trust.role != "AUDIT_SIGNER":
        raise EncodingError("audit signer role required")
    load_sm2_public_key(trust.spki_der)
    integer(trust.first_sequence, minimum=1)
    if trust.last_sequence is not None:
        integer(trust.last_sequence, minimum=trust.first_sequence)
    value = (trust.kid, trust.role, trust.spki_der, trust.first_sequence, trust.last_sequence)
    existing = conn.execute(
        "SELECT kid,role,spki_der,first_sequence,last_sequence FROM ag_aud"
        "it_checkpoint_keys WHERE kid=%s FOR UPDATE",
        (trust.kid,),
    ).fetchone()
    if existing:
        old = (existing[0], existing[1], bytes(existing[2]), existing[3], existing[4])
        if old == value:
            return False
        # Operator may retire an open range exactly once, without changing
        # key identity or invalidating any checkpoint already signed by it.
        if old[:4] != value[:4] or old[4] is not None or trust.last_sequence is None:
            raise AuditStoreError("KEY_REGISTRATION_CONFLICT", 409)
        maximum = conn.execute(
            "SELECT max(sequence) FROM ag_checkpoints WHERE kid=%s", (trust.kid,)
        ).fetchone()[0]
        if maximum is not None and maximum > trust.last_sequence:
            raise AuditStoreError("KEY_RANGE_INVALIDATES_HISTORY", 409)
        conn.execute(
            "UPDATE ag_audit_checkpoint_keys SET last_sequence=%s WHERE kid=%s"
            " AND last_sequence IS NULL",
            (trust.last_sequence, trust.kid),
        )
        return True
    conn.execute(
        "INSERT INTO ag_audit_checkpoint_keys(kid,role,spki_der,first_sequ"
        "ence,last_sequence) VALUES (%s,%s,%s,%s,%s)",
        value,
    )
    return True


def register_principal(conn, *, credential_id, credential, role, stream_id):
    identifier(credential_id)
    identifier(stream_id)
    if role not in ("WRITER", "READER"):
        raise EncodingError("invalid audit credential role")
    verifier = credential_verifier(credential)
    old = conn.execute(
        "SELECT role,credential_verifier,stream_id FROM ag_audit_principals WHERE credential_id=%s",
        (credential_id,),
    ).fetchone()
    if old:
        if old[0] != role or bytes(old[1]) != verifier or old[2] != stream_id:
            raise AuditStoreError("PRINCIPAL_REGISTRATION_CONFLICT", 409)
        return False
    conn.execute(
        "INSERT INTO ag_audit_principals(credential_id,role,credential_ver"
        "ifier,stream_id) VALUES (%s,%s,%s,%s)",
        (credential_id, role, verifier, stream_id),
    )
    return True
