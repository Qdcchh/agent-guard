"""S0 strict wire, deep immutability and exact capacity tests (no PG/transport)."""

from dataclasses import FrozenInstanceError, replace

import pytest

from agent_guard.audit.contracts import (
    MATERIAL_MAX_BYTES,
    AppendBatch,
    CheckpointClaims,
    JournalScope,
    RecordPage,
    SnapshotObject,
    canonical_json_bytes,
    decode_append_batch,
    decode_checkpoint_claims,
    decode_journal_record,
    decode_material_projection,
    decode_record_page,
    encode_append_batch,
    encode_material_projection,
)
from agent_guard.contracts.encoding import (
    EncodingError,
    b64url_encode,
    load_strict_json,
)
from agent_guard.crypto.sm import sm3_b64url
from tests.fixtures.a31_common import DIGEST, FACTS, SCOPE, STAMP, codec_record


@pytest.mark.parametrize("kind", tuple(FACTS))
def test_task_stream_canonical_sm3_schema(kind):
    raw = codec_record(kind)
    record = decode_journal_record(raw)
    assert record.kind == kind and record.scope == SCOPE
    assert record.digest == sm3_b64url(raw) and record.raw == raw
    assert record.facts_bytes == canonical_json_bytes(FACTS[kind])
    assert record.record_id.startswith(kind + ":") and record.recorded_at == STAMP
    with pytest.raises(FrozenInstanceError):
        record.seq = 3
    with pytest.raises(TypeError):
        RecordPage(SCOPE.stream_id, "cp", 1, [raw], None)
    with pytest.raises(TypeError):
        SnapshotObject("request", "id", bytearray(b"raw"), DIGEST)


@pytest.mark.parametrize(
    "field,value",
    [
        ("epoch", True),
        ("epoch", 2),
        ("seq", True),
        ("seq", 0),
        ("seq", 2**53),
        ("record_id", "wrong"),
        ("previous_digest", "not-sm3"),
        ("recorded_at", "2026-10-09T00:00:00Z"),
        ("gateway_id", "bad id"),
        ("operation_id", "op"),
        ("evidence_ref", "ref"),
        ("kind", "LEASE"),
    ],
)
def test_record_field_rejections(field, value):
    data = load_strict_json(codec_record())
    data[field] = value
    with pytest.raises((EncodingError, ValueError, TypeError)):
        decode_journal_record(canonical_json_bytes(data))


@pytest.mark.parametrize("kind", tuple(FACTS))
@pytest.mark.parametrize(
    "mutation", ("unknown", "missing", "null", "float", "duplicate", "noncanonical")
)
def test_facts_exact_keys_types_and_encoding(kind, mutation):
    data = load_strict_json(codec_record(kind))
    facts = data["facts"]
    key = next(key for key in facts if key != "first_evidence_ref")
    if mutation == "unknown":
        facts["not_allowed"] = "injected"
    elif mutation == "missing":
        facts.pop(key)
    elif mutation == "null":
        facts[key] = None
    if mutation in ("float", "duplicate", "noncanonical"):
        raw = codec_record(kind)
        if mutation == "float":
            raw = raw.replace(b'"epoch":1', b'"epoch":1.0')
        elif mutation == "duplicate":
            raw = raw.replace(b'"epoch":1', b'"epoch":1,"epoch":1')
        else:
            raw = b" " + raw
    else:
        raw = canonical_json_bytes(data)
    with pytest.raises((EncodingError, ValueError, TypeError)):
        decode_journal_record(raw)


def test_append_batch_exact_continuity_and_encoded_limit():
    first = codec_record()
    second = codec_record("FIRST", previous=sm3_b64url(first))
    batch = encode_append_batch(SCOPE.stream_id, (first, second))
    assert type(batch) is AppendBatch and decode_append_batch(batch.exact_body) == batch
    assert batch.batch_id == sm3_b64url(batch.exact_body)
    assert (batch.start_sequence, batch.end_sequence, batch.end_digest) == (
        1,
        2,
        sm3_b64url(second),
    )
    with pytest.raises(EncodingError):
        encode_append_batch(SCOPE.stream_id, (second, first))
    with pytest.raises(EncodingError):
        encode_append_batch(SCOPE.stream_id, ())
    with pytest.raises(EncodingError):
        decode_append_batch(batch.exact_body + b" ")
    with pytest.raises(EncodingError):
        decode_journal_record(b"x" * 32769)
    with pytest.raises(EncodingError):
        decode_append_batch(b"x" * 65537)


@pytest.mark.parametrize(
    "kind,keys",
    [
        ("FIRST", ("context", "quote", "source")),
        ("RETRY", ("context", "source")),
        ("QUERY", ("context", "source")),
        ("TERMINAL", ("ledger", "result")),
    ],
)
def test_material_logical_and_precise_aggregate_capacity(kind, keys):
    maximum = {key: b64url_encode(b"a" * 65536) for key in keys}
    raw = encode_material_projection(kind, maximum)
    assert len(raw) == MATERIAL_MAX_BYTES[kind]
    assert decode_material_projection(kind, raw) == maximum
    for key in keys:
        too_large = dict(maximum)
        too_large[key] = b64url_encode(b"a" * 65537)
        with pytest.raises(EncodingError):
            encode_material_projection(kind, too_large)
    with pytest.raises(EncodingError):
        decode_material_projection(kind, raw + b" ")
    wrong = dict(maximum)
    wrong["extra"] = "x"
    with pytest.raises(EncodingError):
        encode_material_projection(kind, wrong)


def test_checkpoint_claim_codec_cannot_authenticate_or_adopt_keys():
    value = dict(
        profile="GM-MVP-1",
        checkpoint_version="AG-CHECKPOINT-1",
        checkpoint_id="cp",
        stream_id=SCOPE.stream_id,
        gateway_id=SCOPE.gateway_id,
        tenant_id=SCOPE.tenant_id,
        task_id=SCOPE.task_id,
        epoch=1,
        sequence=1,
        head_digest=DIGEST,
        previous_checkpoint_digest=None,
        issued_at=STAMP,
        kid="audit-key",
    )
    claims = decode_checkpoint_claims(canonical_json_bytes(value))
    assert type(claims) is CheckpointClaims and claims.kid == "audit-key"
    for key, invalid in [
        ("sequence", True),
        ("epoch", 2),
        ("profile", "other"),
        ("head_digest", "short"),
        ("issued_at", "0"),
    ]:
        data = dict(value)
        data[key] = invalid
        with pytest.raises(EncodingError):
            decode_checkpoint_claims(canonical_json_bytes(data))
    value["key"] = "attacker-key"
    with pytest.raises(EncodingError):
        decode_checkpoint_claims(canonical_json_bytes(value))


def test_record_page_strict_pin_cursor_and_immutable_input():
    first = codec_record()
    second = codec_record("FIRST", previous=sm3_b64url(first))
    data = dict(
        stream_id=SCOPE.stream_id,
        observed_checkpoint_id="cp",
        observed_sequence=2,
        entries=[b64url_encode(first)],
        next_after_sequence=1,
    )
    page = decode_record_page(canonical_json_bytes(data))
    assert page.entries == (first,) and page.next_after_sequence == 1
    data["entries"] = [b64url_encode(first), b64url_encode(second)]
    data["next_after_sequence"] = None
    assert decode_record_page(canonical_json_bytes(data)).entries == (first, second)
    for bad in (0, True, 1, 3):
        data["next_after_sequence"] = bad
        with pytest.raises(EncodingError):
            decode_record_page(canonical_json_bytes(data))
    with pytest.raises((EncodingError, TypeError)):
        replace(SCOPE, epoch=True)
    with pytest.raises(EncodingError):
        JournalScope(SCOPE.gateway_id, SCOPE.tenant_id, SCOPE.task_id, "unsafe stream", 1)


@pytest.mark.parametrize(
    "field,value",
    [
        ("stream_id", "not-a-UUID"),
        ("stream_id", SCOPE.stream_id.upper()),
        ("stream_id", SCOPE.stream_id.replace("-", "")),
        ("gateway_id", "http://gateway.agent-guard.test"),
        ("gateway_id", "https://gateway.agent-guard.test/path"),
        ("gateway_id", "https://user@gateway.agent-guard.test"),
        ("gateway_id", "https://gateway.agent-guard.test?query"),
        ("gateway_id", "https://gateway.agent-guard.test#fragment"),
    ],
)
def test_scope_uuid_and_https_origin_required_at_wire_boundary(field, value):
    with pytest.raises(EncodingError):
        replace(SCOPE, **{field: value})
    wire = load_strict_json(codec_record())
    wire[field] = value
    with pytest.raises(EncodingError):
        decode_journal_record(canonical_json_bytes(wire))


def test_internal_accept_result_quote_independent_capacity_and_metadata_types():
    from datetime import datetime, timezone

    import rfc8785

    from agent_guard.audit.journal import JournalError, accept_result_bytes
    from agent_guard.contracts.ledger import (
        AcceptDisposition,
        AcceptResult,
        TrustedCost,
    )

    base = AcceptResult(
        "op",
        "leaf",
        "root",
        "RESERVED",
        AcceptDisposition.EXISTING,
        TrustedCost(1, quote_id="quote", quote_version="1"),
        datetime(2026, 10, 9, tzinfo=timezone.utc),
    )
    metadata = accept_result_bytes(base)
    assert metadata == canonical_json_bytes(load_strict_json(metadata))
    value = replace(base, cost=replace(base.cost, quote_snapshot=b"a" * 65536))
    encoded = accept_result_bytes(value)
    assert len(encoded) == len(metadata) - 2 + 87382 and len(encoded) <= 152916
    import json

    assert rfc8785.dumps(json.loads(encoded)) == encoded
    for quote in (b"a" * 65537, bytearray(b"raw"), "raw", True):
        with pytest.raises(JournalError):
            accept_result_bytes(replace(base, cost=replace(base.cost, quote_snapshot=quote)))
    for invalid in (
        replace(base, root_id=None),
        replace(base, status=True),
        replace(base, cost=replace(base.cost, amount_fen=True)),
        replace(base, cost=replace(base.cost, quote_id=["unknown"])),
    ):
        with pytest.raises((EncodingError, JournalError)):
            accept_result_bytes(invalid)


@pytest.mark.parametrize(
    "status", ("RESERVED", "EXECUTING", "UNKNOWN", "SUCCEEDED", "FAILED", "RUNNING")
)
def test_internal_accept_result_uses_actual_operation_state_machine(status):
    from datetime import datetime, timezone

    from agent_guard.audit.journal import JournalError, accept_result_bytes
    from agent_guard.contracts.ledger import (
        AcceptDisposition,
        AcceptResult,
        TrustedCost,
    )

    value = AcceptResult(
        "op",
        "leaf",
        "root",
        status,
        AcceptDisposition.EXISTING,
        TrustedCost(0),
        datetime(2026, 10, 9, tzinfo=timezone.utc),
    )
    if status == "RUNNING":
        with pytest.raises(JournalError):
            accept_result_bytes(value)
    else:
        assert load_strict_json(accept_result_bytes(value))["status"] == status


def _independent_snapshot_seed(kind, size):
    from agent_guard.audit.contracts import EmptyTaskBootstrapSeed, SnapshotChunk

    scope = ("https://gateway.test", "tenant-1", "task-1")
    raw = b"x" * size
    digest = sm3_b64url(raw)
    obj = SnapshotObject(kind, "logical-1", raw, digest)
    count = (size + 24575) // 24576
    chunks = tuple(
        SnapshotChunk(kind, "logical-1", i, count, size, digest, raw[i * 24576 : (i + 1) * 24576])
        for i in range(count)
    )
    index = sm3_b64url(
        canonical_json_bytes({"profile": "AG-BOOTSTRAP-INDEX-1", "scope": list(scope)})
    )
    index = sm3_b64url(
        canonical_json_bytes(
            {
                "profile": "AG-BOOTSTRAP-INDEX-1",
                "previous": index,
                "kind": kind,
                "id": "logical-1",
                "total_raw_bytes": size,
                "object_digest": digest,
                "chunk_count": count,
            }
        )
    )
    wire = sum(
        len(
            canonical_json_bytes(
                {
                    "frame_type": "OBJECT_CHUNK",
                    "object_kind": c.kind,
                    "object_id": c.object_id,
                    "chunk_index": c.index,
                    "chunk_count": c.count,
                    "total_raw_bytes": c.total_raw_bytes,
                    "object_digest": c.object_digest,
                    "data": b64url_encode(c.raw),
                }
            )
        )
        + 1
        for c in chunks
    )
    manifest = canonical_json_bytes(
        {
            "profile": "AG-BOOTSTRAP-1",
            "scope": list(scope),
            "root_grant_id": "root-1",
            "snapshot_as_of": STAMP,
            "origin": "FROM_EMPTY_TASK",
            "object_count": 1,
            "chunk_count": count,
            "wire_bytes": wire,
            "index_root": index,
            "schema_lineage_digest": sm3_b64url(canonical_json_bytes([])),
        }
    )
    return EmptyTaskBootstrapSeed(
        scope,
        "root-1",
        "1",
        STAMP,
        "FROM_EMPTY_TASK",
        (),
        (obj,),
        chunks,
        1,
        count,
        wire,
        index,
        manifest,
    )


@pytest.mark.parametrize(
    "kind",
    (
        "token",
        "proof",
        "ancestor_token",
        "receipt",
        "checkpoint",
        "journal",
        "request",
        "result",
        "ledger",
        "quote",
        "context",
        "source",
        "raw_authorization_snapshot",
        "typed_snapshot_metadata",
    ),
)
def test_snapshot_logical_actual_raw_cap_and_plus_one(kind):
    from agent_guard.audit import contracts, journal

    seed = _independent_snapshot_seed(kind, contracts.OBJECT_LIMITS[kind])
    journal._validate_seed(seed)
    assert b"".join(c.raw for c in seed.chunks) == seed.objects[0].raw
    with pytest.raises(journal.JournalError, match="bootstrap object bytes/digest mismatch"):
        journal._validate_seed(_independent_snapshot_seed(kind, contracts.OBJECT_LIMITS[kind] + 1))


@pytest.mark.parametrize("size", (24575, 24576, 24577, 49152, 65536))
def test_snapshot_real_chunk_boundaries_full_index_and_wire(size):
    from agent_guard.audit import journal

    seed = _independent_snapshot_seed("request", size)
    journal._validate_seed(seed)
    assert [len(c.raw) for c in seed.chunks] == [
        min(24576, size - i * 24576) for i in range((size + 24575) // 24576)
    ]
    assert seed.object_count == 1 and seed.chunk_count == len(seed.chunks)


def test_snapshot_actual_object_tuple_over_hard_cap_rejects_before_index():
    from agent_guard.audit import journal

    seed = _independent_snapshot_seed("request", 1)
    actual = (seed.objects[0],) * 200001
    assert len(actual) == 200001
    with pytest.raises(journal.JournalError, match="bootstrap object capacity mismatch"):
        journal._validate_seed(replace(seed, objects=actual, object_count=len(actual)))


def test_static_snapshot_hard_caps_and_exact_consumer_gates():
    """Static gate evidence, distinct from allocating 256MiB in a PG fixture."""
    import ast
    import inspect

    from agent_guard.audit import contracts, journal

    expected = {
        "CHUNK_BYTES": 24576,
        "MAX_OBJECTS": 200000,
        "MAX_CHUNKS": 400000,
        "MAX_WIRE_BYTES": 268435456,
        "MAX_OPERATIONS": 20000,
        "MAX_RECORDS": 100000,
    }
    assert {k: getattr(contracts, k) for k in expected} == expected
    assert {k: getattr(journal, k) for k in expected} == expected
    tree = ast.parse(inspect.getsource(journal))
    comparisons = {ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Compare)}
    assert {
        "len(objects) >= MAX_OBJECTS",
        "len(grants) > MAX_OBJECTS",
        "len(ops) > MAX_OPERATIONS",
        "len(chunks) > MAX_CHUNKS",
        "wire > MAX_WIRE_BYTES",
        "len(records) > MAX_RECORDS",
        "1 <= len(seed.objects) <= MAX_OBJECTS",
        "1 <= len(expected_chunks) <= MAX_CHUNKS",
        "1 <= wire <= MAX_WIRE_BYTES",
    } <= comparisons
    source = inspect.getsource(journal)
    assert "(tenant, task, MAX_OPERATIONS + 1)" in source
    assert "(baseline.scope.stream_id, MAX_RECORDS + 1)" in source


@pytest.mark.parametrize("consumer", ("operations", "records"))
def test_actual_snapshot_consumers_fetch_original_limit_plus_one_and_refuse(consumer):
    from datetime import datetime, timezone

    from agent_guard.audit import journal
    from agent_guard.audit.contracts import ExistingStreamRef

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.rows[0]

    class QueryWitness:
        def __init__(self):
            self.queries = []

        def execute(self, query, args=None):
            self.queries.append((query, args))
            if query == "SELECT clock_timestamp()":
                return Rows([(datetime(2026, 10, 9, tzinfo=timezone.utc),)])
            if query == "SELECT pg_current_xact_id()::text":
                return Rows([("1",)])
            if query.startswith("SELECT grant_id,amount_reserved"):
                assert args == ("tenant-1", "task-1", 200001)
                return Rows([("root-1", 0, 0, 0, 0)])
            if query.startswith("SELECT operation_id FROM ag_operations"):
                assert args == ("tenant-1", "task-1", 20001)
                return Rows([("op",)] * 20001)
            if query.startswith("SELECT object_id,chunk_index,raw"):
                return Rows([])
            if query.startswith("SELECT raw FROM ag_audit_records"):
                assert args == (SCOPE.stream_id, 100001)
                return Rows([(b"not-decoded-before-cap",)] * 100001)
            raise AssertionError((query, args))

    witness = QueryWitness()
    if consumer == "operations":
        with pytest.raises(journal.JournalError, match="task operation capacity exceeded"):
            journal._snapshot(
                witness, ("https://gateway.test", "tenant-1", "task-1"), "root-1", empty=False
            )
    else:
        baseline = ExistingStreamRef(SCOPE, DIGEST, DIGEST)
        with pytest.raises(journal.JournalError, match="journal snapshot cap exceeded"):
            journal.capture_introduced_tx(witness, baseline, object(), ())
    assert len(witness.queries) == (4 if consumer == "operations" else 2)


@pytest.mark.parametrize(
    "field,value",
    (
        ("objects", ([{}],)),
        ("chunks", (({},),)),
        ("scope_key", ("https://gateway.test", [], "task-1")),
        ("schema_lineage", (("authorization", "001", {}),)),
        ("manifest_bytes", bytearray(b"{}")),
        ("objects", (object(),)),
    ),
)
def test_bootstrap_seed_rejects_nested_mutable_and_non_data_objects(field, value):
    seed = _independent_snapshot_seed("request", 1)
    with pytest.raises(TypeError, match="deeply immutable"):
        replace(seed, **{field: value})
