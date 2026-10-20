"""Deeply immutable audit DTOs and strict, canonical wire codecs.

This module has no database, transport or signing capability. Checkpoint claims
are decoded here; authenticating them belongs to the independent consumer.
"""

from __future__ import annotations

import re
import types
import uuid
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Callable, get_args, get_origin, get_type_hints
from urllib.parse import urlsplit

from agent_guard.contracts.encoding import (
    MAX_SAFE_INTEGER,
    EncodingError,
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.crypto.sm import sm3_b64url

JOURNAL_PROFILE = "AG-AUDIT-JOURNAL-1"
BATCH_PROFILE = "AG-AUDIT-BATCH-1"
MAX_RECORD_BYTES = 32768
MAX_BATCH_BYTES = 65536
MAX_BATCH_ENTRIES = 64
CHUNK_BYTES = 24576
MAX_OBJECTS = 200000
MAX_CHUNKS = 400000
MAX_WIRE_BYTES = 268435456
MAX_OPERATIONS = 20000
MAX_RECORDS = 100000
OBJECT_LIMITS = {
    **dict.fromkeys(("token", "proof", "ancestor_token", "receipt", "checkpoint"), 16384),
    "journal": 32768,
    **dict.fromkeys(
        (
            "request",
            "result",
            "ledger",
            "quote",
            "context",
            "source",
            "raw_authorization_snapshot",
            "typed_snapshot_metadata",
        ),
        65536,
    ),
}
FACT_KEYS = {
    "BOOTSTRAP": (
        "boundary root_grant_id snapshot_as_of schema_lineage_digest "
        "index_root manifest_digest object_count chunk_count wire_bytes"
    ).split(),
    "FIRST": (
        "root_grant_id grant_id path_ids intent_digest token_digest "
        "proof_digest body_digest context_digest source_digest "
        "source_material_digest reserve_digest quote_digest amount_fen "
        "calls currency introduced_grants"
    ).split(),
    "RETRY": (
        "first_evidence_ref intent_digest token_digest proof_digest "
        "body_digest context_digest source_digest source_material_digest "
        "response_kind response_digest status receipt_status "
        "receipt_jws_digest"
    ).split(),
    "QUERY": (
        "first_evidence_ref token_digest proof_digest body_digest "
        "context_digest source_digest source_material_digest "
        "response_digest status receipt_status result_digest "
        "receipt_jws_digest"
    ).split(),
    "TERMINAL": (
        "first_evidence_ref status action result_digest ledger_digest "
        "pending_receipt_digest receipt_id owner_token fencing_version "
        "lease_expires_at path_ids"
    ).split(),
    "PUBLISH": "receipt_id receipt_jws_digest signed_at".split(),
}


def identifier(value: object, *, maximum: int = 512) -> str:
    if type(value) is not str or not re.fullmatch(r"[\x21-\x7e]{1," + str(maximum) + "}", value):
        raise EncodingError("invalid audit identifier")
    return value


def integer(value: object, *, minimum: int = 0, maximum: int = MAX_SAFE_INTEGER) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise EncodingError("invalid audit integer")
    return value


def digest(value: object) -> str:
    if type(value) is not str or len(b64url_decode(value)) != 32:
        raise EncodingError("invalid SM3 digest")
    return value


def timestamp(value: object) -> str:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", value):
        raise EncodingError("invalid precise UTC timestamp")
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    if parsed.timestamp() < 0:
        raise EncodingError("negative timestamp")
    return value


def utc_text(value: datetime) -> str:
    if type(value) is not datetime or value.tzinfo is None:
        raise EncodingError("aware database timestamp required")
    return timestamp(value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def exact_object(raw: bytes, keys: set[str], *, maximum: int = 65536) -> dict:
    if type(raw) is not bytes or len(raw) > maximum:
        raise EncodingError("audit wire capacity exceeded")
    value = load_strict_json(raw)
    if type(value) is not dict or set(value) != keys or canonical_json_bytes(value) != raw:
        raise EncodingError("exact canonical audit object required")
    return value


@dataclass(frozen=True, slots=True)
class ImmutableDTO:
    def __post_init__(self):
        def check(value):
            if value is None or type(value) in (str, bytes, int):
                return
            if type(value) is tuple:
                for item in value:
                    check(item)
                return
            if isinstance(value, ImmutableDTO):
                return
            raise TypeError("audit DTO requires deeply immutable values")

        def typed(value, annotation):
            origin = get_origin(annotation)
            args = get_args(annotation)
            if origin is types.UnionType:
                return any(typed(value, choice) for choice in args)
            if origin is tuple:
                if type(value) is not tuple:
                    return False
                if len(args) == 2 and args[1] is Ellipsis:
                    return all(typed(item, args[0]) for item in value)
                return len(value) == len(args) and all(
                    typed(item, arg) for item, arg in zip(value, args, strict=True)
                )
            return type(value) is annotation

        annotations = get_type_hints(type(self))
        for field in fields(self):
            value = getattr(self, field.name)
            check(value)
            if not typed(value, annotations[field.name]):
                raise TypeError("audit DTO field has wrong exact type")


@dataclass(frozen=True, slots=True)
class JournalScope(ImmutableDTO):
    gateway_id: str
    tenant_id: str
    task_id: str
    stream_id: str
    epoch: int

    def __post_init__(self):
        super(JournalScope, self).__post_init__()
        for name in ("gateway_id", "tenant_id", "task_id", "stream_id"):
            identifier(getattr(self, name))
        integer(self.epoch, minimum=1, maximum=1)
        try:
            if str(uuid.UUID(self.stream_id)) != self.stream_id:
                raise ValueError("noncanonical stream UUID")
            parsed = urlsplit(self.gateway_id)
            _ = parsed.port
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or self.gateway_id != parsed.scheme + "://" + parsed.netloc
            ):
                raise ValueError("HTTPS gateway origin required")
        except ValueError as exc:
            raise EncodingError("invalid journal UUID/origin scope") from exc


@dataclass(frozen=True, slots=True)
class ExistingStreamRef(ImmutableDTO):
    scope: JournalScope
    genesis_digest: str
    bootstrap_digest: str


@dataclass(frozen=True, slots=True)
class LockedAcceptContext(ImmutableDTO):
    scope_key: tuple[str, str, str]
    root_grant_id: str
    path_ids: tuple[str, ...]
    invocation_context: bytes
    source_digest: str | None
    tx_id: str


@dataclass(frozen=True, slots=True)
class SnapshotObject(ImmutableDTO):
    kind: str
    object_id: str
    raw: bytes
    digest: str


@dataclass(frozen=True, slots=True)
class SnapshotChunk(ImmutableDTO):
    kind: str
    object_id: str
    index: int
    count: int
    total_raw_bytes: int
    object_digest: str
    raw: bytes


@dataclass(frozen=True, slots=True)
class EmptyTaskBootstrapSeed(ImmutableDTO):
    scope_key: tuple[str, str, str]
    root_grant_id: str
    tx_id: str
    captured_at: str
    origin: str
    schema_lineage: tuple[tuple[str, str, str], ...]
    objects: tuple[SnapshotObject, ...]
    chunks: tuple[SnapshotChunk, ...]
    object_count: int
    chunk_count: int
    wire_bytes: int
    index_root: str
    manifest_bytes: bytes


@dataclass(frozen=True, slots=True)
class AcceptDescriptor(ImmutableDTO):
    scope_key: tuple[str, str, str]
    root_id: str
    path_ids: tuple[str, ...]
    evidence_ref: str
    context_bytes: bytes
    source_digest: str
    source_material_bytes: bytes
    token_digest: str
    proof_digest: str
    body_digest: str


@dataclass(frozen=True, slots=True)
class JournalRecord(ImmutableDTO):
    scope: JournalScope
    seq: int
    record_id: str
    kind: str
    operation_id: str | None
    evidence_ref: str | None
    previous_digest: str
    recorded_at: str
    facts_bytes: bytes
    raw: bytes
    digest: str


@dataclass(frozen=True, slots=True)
class WriteFence(ImmutableDTO):
    operation_id: str
    owner_token: str
    fencing_version: int
    pre_status: str
    expires_at: str
    tx_id: str


@dataclass(frozen=True, slots=True)
class AppendBatch(ImmutableDTO):
    stream_id: str
    entries: tuple[bytes, ...]
    exact_body: bytes
    batch_id: str
    start_sequence: int
    end_sequence: int
    end_digest: str


@dataclass(frozen=True, slots=True)
class CheckpointClaims(ImmutableDTO):
    profile: str
    checkpoint_version: str
    checkpoint_id: str
    stream_id: str
    gateway_id: str
    tenant_id: str
    task_id: str
    epoch: int
    sequence: int
    head_digest: str
    previous_checkpoint_digest: str | None
    issued_at: str
    kid: str


@dataclass(frozen=True, slots=True)
class CheckpointTrust(ImmutableDTO):
    kid: str
    role: str
    spki_der: bytes
    first_sequence: int
    last_sequence: int | None


@dataclass(frozen=True, slots=True)
class ObservedCheckpoint(ImmutableDTO):
    jws: str
    claims: CheckpointClaims
    jws_digest: str
    observed_at: str


@dataclass(frozen=True, slots=True)
class RegistrationDescriptor(ImmutableDTO):
    scope: JournalScope
    genesis_digest: str
    bootstrap_digest: str
    boundary: str
    index_root: str
    object_count: int
    chunk_count: int
    wire_bytes: int


@dataclass(frozen=True, slots=True)
class PendingBatch(ImmutableDTO):
    stream_id: str
    batch_id: str
    exact_body: bytes
    start_sequence: int
    end_sequence: int
    end_digest: str
    base_checkpoint_digest: str | None


@dataclass(frozen=True, slots=True)
class DeliveryCursor(ImmutableDTO):
    stream_id: str
    ack_sequence: int
    ack_head_digest: str
    ack_checkpoint_digest: str | None
    pending_batch_id: str | None


@dataclass(frozen=True, slots=True)
class HistoryPage(ImmutableDTO):
    stream_id: str
    observed_checkpoint_id: str
    observed_sequence: int
    checkpoints: tuple[str, ...]
    next_after_sequence: int | None


@dataclass(frozen=True, slots=True)
class RecordPage(ImmutableDTO):
    stream_id: str
    observed_checkpoint_id: str
    observed_sequence: int
    entries: tuple[bytes, ...]
    next_after_sequence: int | None


@dataclass(frozen=True, slots=True)
class VerifiedRemotePrefix(ImmutableDTO):
    scope: JournalScope
    sequence: int
    head_digest: str
    checkpoint_jws: str
    checkpoint_digest: str


BeforeCreate = Callable[[object, LockedAcceptContext], None]
AfterLink = Callable[
    [object, object, object, ExistingStreamRef | EmptyTaskBootstrapSeed | None], None
]


def scope_object(scope: JournalScope) -> dict:
    return {
        "journal_profile": JOURNAL_PROFILE,
        "gateway_id": scope.gateway_id,
        "tenant_id": scope.tenant_id,
        "task_id": scope.task_id,
        "stream_id": scope.stream_id,
        "epoch": scope.epoch,
    }


def genesis_digest(scope: JournalScope) -> str:
    return sm3_b64url(canonical_json_bytes(scope_object(scope)))


def validate_facts(kind: str, facts: dict) -> None:
    if kind not in FACT_KEYS or type(facts) is not dict or set(facts) != set(FACT_KEYS[kind]):
        raise EncodingError("invalid exact journal facts")
    for key, value in facts.items():
        if key.endswith("digest") or key in ("index_root",):
            if value is None and key in (
                "quote_digest",
                "receipt_jws_digest",
                "result_digest",
            ):
                continue
            digest(value)
        elif key in ("snapshot_as_of", "lease_expires_at", "signed_at"):
            timestamp(value)
        elif key in (
            "amount_fen",
            "calls",
            "fencing_version",
            "object_count",
            "chunk_count",
            "wire_bytes",
        ):
            integer(value)
        elif key == "path_ids":
            if type(value) is not list or not 1 <= len(value) <= 3:
                raise EncodingError("invalid journal path")
            for item in value:
                identifier(item)
        elif key == "introduced_grants":
            if type(value) is not list or len(value) > 3:
                raise EncodingError("invalid introduced grants")
            expected = set(
                (
                    "grant_id parent_id root_id depth holder_client_id holder_kid "
                    "grant_token_digest source_material_digest amount_reserved "
                    "amount_settled calls_reserved calls_settled"
                ).split()
            )
            for item in value:
                if type(item) is not dict or set(item) != expected:
                    raise EncodingError("invalid introduced grant")
                for counter in (
                    "amount_reserved",
                    "amount_settled",
                    "calls_reserved",
                    "calls_settled",
                ):
                    integer(item[counter], maximum=0)
                integer(item["depth"], maximum=2)
                for name in ("grant_token_digest", "source_material_digest"):
                    digest(item[name])
                for name in ("grant_id", "root_id", "holder_client_id", "holder_kid"):
                    identifier(item[name])
                if item["parent_id"] is not None:
                    identifier(item["parent_id"])
        elif value is None and key == "first_evidence_ref" and kind == "TERMINAL":
            continue
        else:
            identifier(value)
    enums = {
        "boundary": ("NEW_EMPTY", "LEGACY_WITH_GAPS"),
        "currency": ("CNY",),
        "response_kind": ("ACCEPT_RESULT", "ACCEPT_RESPONSE"),
        "status": ("RESERVED", "EXECUTING", "UNKNOWN", "SUCCEEDED", "FAILED"),
        "receipt_status": ("PENDING", "READY"),
        "action": ("SETTLE", "RELEASE"),
    }
    for key, values in enums.items():
        if key in facts and facts[key] not in values:
            raise EncodingError("invalid journal fact enum")


def decode_journal_record(raw: bytes) -> JournalRecord:
    keys = set(
        (
            "journal_profile stream_id gateway_id tenant_id task_id epoch seq "
            "record_id kind operation_id evidence_ref previous_digest "
            "recorded_at facts"
        ).split()
    )
    value = exact_object(raw, keys, maximum=MAX_RECORD_BYTES)
    if value["journal_profile"] != JOURNAL_PROFILE:
        raise EncodingError("unsupported journal profile")
    scope = JournalScope(
        *(value[k] for k in ("gateway_id", "tenant_id", "task_id", "stream_id", "epoch"))
    )
    seq = integer(value["seq"], minimum=1)
    kind = value["kind"]
    validate_facts(kind, value["facts"])
    op, ref = value["operation_id"], value["evidence_ref"]
    if kind == "BOOTSTRAP":
        if op is not None or ref is not None or seq != 1:
            raise EncodingError("invalid bootstrap relation")
        suffix = scope.stream_id
    else:
        identifier(op)
        if kind in ("FIRST", "RETRY", "QUERY"):
            identifier(ref)
        elif ref is not None:
            identifier(ref)
        suffix = (
            ref
            if kind in ("RETRY", "QUERY")
            else (value["facts"]["receipt_id"] if kind == "PUBLISH" else op)
        )
    if value["record_id"] != kind + ":" + suffix:
        raise EncodingError("invalid record event identity")
    return JournalRecord(
        scope,
        seq,
        identifier(value["record_id"], maximum=2048),
        kind,
        op,
        ref,
        digest(value["previous_digest"]),
        timestamp(value["recorded_at"]),
        canonical_json_bytes(value["facts"]),
        raw,
        sm3_b64url(raw),
    )


def encode_append_batch(stream_id: str, entries: tuple[bytes, ...]) -> AppendBatch:
    identifier(stream_id)
    if type(entries) is not tuple or not 1 <= len(entries) <= MAX_BATCH_ENTRIES:
        raise EncodingError("invalid append entry count")
    records = tuple(decode_journal_record(entry) for entry in entries)
    for index, record in enumerate(records):
        if record.scope.stream_id != stream_id or (
            index
            and (
                record.scope != records[0].scope
                or record.seq != records[index - 1].seq + 1
                or record.previous_digest != records[index - 1].digest
            )
        ):
            raise EncodingError("noncontiguous append batch")
    body = canonical_json_bytes(
        {
            "batch_profile": BATCH_PROFILE,
            "stream_id": stream_id,
            "entries": [b64url_encode(raw) for raw in entries],
        }
    )
    return AppendBatch(
        stream_id,
        entries,
        body,
        sm3_b64url(body),
        records[0].seq,
        records[-1].seq,
        records[-1].digest,
    )


def decode_append_batch(raw: bytes) -> AppendBatch:
    value = exact_object(raw, {"batch_profile", "stream_id", "entries"})
    if value["batch_profile"] != BATCH_PROFILE or type(value["entries"]) is not list:
        raise EncodingError("invalid batch schema")
    batch = encode_append_batch(
        value["stream_id"], tuple(b64url_decode(x) for x in value["entries"])
    )
    if batch.exact_body != raw:
        raise EncodingError("noncanonical batch")
    return batch


def decode_checkpoint_claims(raw: bytes) -> CheckpointClaims:
    value = exact_object(raw, {f.name for f in fields(CheckpointClaims)})
    if value["profile"] != "GM-MVP-1" or value["checkpoint_version"] != "AG-CHECKPOINT-1":
        raise EncodingError("unsupported checkpoint profile")
    JournalScope(*(value[k] for k in ("gateway_id", "tenant_id", "task_id", "stream_id", "epoch")))
    integer(value["sequence"], minimum=1)
    digest(value["head_digest"])
    if value["previous_checkpoint_digest"] is not None:
        digest(value["previous_checkpoint_digest"])
    timestamp(value["issued_at"])
    identifier(value["checkpoint_id"])
    identifier(value["kid"], maximum=128)
    return CheckpointClaims(**value)


def _page(raw: bytes, cls, field: str):
    value = exact_object(raw, {f.name for f in fields(cls)})
    identifier(value["stream_id"])
    identifier(value["observed_checkpoint_id"])
    boundary = integer(value["observed_sequence"], minimum=1)
    cursor = value["next_after_sequence"]
    if cursor is not None:
        integer(cursor, minimum=1, maximum=boundary - 1)
    values = value[field]
    if type(values) is not list or not 1 <= len(values) <= 64:
        raise EncodingError("invalid page entries")
    if field == "entries":
        value[field] = tuple(b64url_decode(item) for item in values)
        records = tuple(decode_journal_record(item) for item in value[field])
        for i, record in enumerate(records):
            if (
                record.scope.stream_id != value["stream_id"]
                or record.seq > boundary
                or (
                    i
                    and (
                        record.seq != records[i - 1].seq + 1
                        or record.previous_digest != records[i - 1].digest
                    )
                )
            ):
                raise EncodingError("invalid record page continuity")
        if (cursor is None and records[-1].seq != boundary) or (
            cursor is not None and cursor != records[-1].seq
        ):
            raise EncodingError("invalid record page cursor")
    else:
        for item in values:
            if type(item) is not str or not item.isascii() or not 1 <= len(item) <= 16384:
                raise EncodingError("invalid checkpoint JWS capacity")
        value[field] = tuple(values)
    return cls(**value)


def decode_record_page(raw: bytes) -> RecordPage:
    return _page(raw, RecordPage, "entries")


def decode_history_page(raw: bytes) -> HistoryPage:
    return _page(raw, HistoryPage, "checkpoints")


# A base64url encoding of N bytes has ceil(4*N/3) characters, without padding.
# The fixed canonical bodies below are measured with empty string values. Each
# projection is shallow and exact; these private DB bounds do not alter any
# generic JSON, journal record, batch or logical raw limit.
MATERIAL_FIELDS = {
    "BOOTSTRAP": (),
    "FIRST": ("context", "quote", "source"),
    "RETRY": ("context", "source"),
    "QUERY": ("context", "source"),
    "TERMINAL": ("ledger", "result"),
    "PUBLISH": ("jws",),
}
MATERIAL_RAW_CAP = 65536
MATERIAL_ENCODED_CAP = (4 * MATERIAL_RAW_CAP + 2) // 3
MATERIAL_FIXED_BYTES = {
    "BOOTSTRAP": 2,
    "FIRST": 37,
    "RETRY": 26,
    "QUERY": 26,
    "TERMINAL": 25,
    "PUBLISH": 10,
}
MATERIAL_MAX_BYTES = {
    "BOOTSTRAP": 2,
    "FIRST": 37 + 3 * MATERIAL_ENCODED_CAP,
    "RETRY": 26 + 2 * MATERIAL_ENCODED_CAP,
    "QUERY": 26 + 2 * MATERIAL_ENCODED_CAP,
    "TERMINAL": 25 + 2 * MATERIAL_ENCODED_CAP,
    "PUBLISH": 10 + 16384,
}


def encode_material_projection(kind: str, value: dict) -> bytes:
    """Canonical DB projection with independently bounded logical raw values."""
    import rfc8785

    if (
        kind not in MATERIAL_FIELDS
        or type(value) is not dict
        or set(value) != set(MATERIAL_FIELDS[kind])
    ):
        raise EncodingError("exact material projection required")
    for key, item in value.items():
        if key == "quote" and item is None:
            continue
        if type(item) is not str:
            raise EncodingError("strict material projection scalar required")
        if key == "jws":
            if (
                not item.isascii()
                or not 1 <= len(item) <= 16384
                or not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", item)
            ):
                raise EncodingError("strict material JWS capacity")
        else:
            if (
                len(item) > MATERIAL_ENCODED_CAP
                or not 1 <= len(b64url_decode(item)) <= MATERIAL_RAW_CAP
            ):
                raise EncodingError("material logical raw capacity exceeded")
    raw = rfc8785.dumps(value)
    if len(raw) > MATERIAL_MAX_BYTES[kind]:
        raise EncodingError("material projection capacity exceeded")
    return raw


def decode_material_projection(kind: str, raw: bytes) -> dict:
    import json

    from agent_guard.contracts.encoding import DuplicateKeyError

    if (
        kind not in MATERIAL_MAX_BYTES
        or type(raw) is not bytes
        or len(raw) > MATERIAL_MAX_BYTES[kind]
    ):
        raise EncodingError("material projection capacity exceeded")

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise DuplicateKeyError("duplicate material member")
            value[key] = item
        return value

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise EncodingError("malformed material projection") from exc
    if encode_material_projection(kind, value) != raw:
        raise EncodingError("canonical material projection required")
    return value
