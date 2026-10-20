"""Independent checkpoint trust and complete pinned-prefix rejection matrix."""

from dataclasses import asdict, replace

import pytest

from agent_guard.audit.client import AuditClient
from agent_guard.audit.contracts import (
    CheckpointClaims,
    CheckpointTrust,
    ExistingStreamRef,
    HistoryPage,
    RecordPage,
    decode_journal_record,
    genesis_digest,
)
from agent_guard.audit.delivery import (
    DeliveryError,
    authenticate_reconciliation,
    reconcile_remote_ahead,
    verify_checkpoint,
)
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.crypto.sm import (
    generate_sm2_private_key,
    serialize_sm2_public_key,
    sign_compact_jws,
)
from tests.fixtures.a31_common import DIGEST, SCOPE, STAMP, codec_record


@pytest.fixture
def proof():
    key = generate_sm2_private_key()
    trust = (
        CheckpointTrust(
            "test-audit",
            "AUDIT_SIGNER",
            serialize_sm2_public_key(key.public_key()),
            1,
            None,
        ),
    )
    records = []
    previous = genesis_digest(SCOPE)
    for seq in range(1, 131):
        raw = codec_record("BOOTSTRAP" if seq == 1 else "PUBLISH", seq=seq, previous=previous)
        value = load_strict_json(raw)
        if seq > 1:
            value["facts"]["receipt_id"] = "receipt-" + str(seq)
            value["record_id"] = "PUBLISH:receipt-" + str(seq)
        record = decode_journal_record(canonical_json_bytes(value))
        records.append(record)
        previous = record.digest
    checkpoints = []
    previous_cp = None
    for seq in (32, 64, 96, 130):
        claims = CheckpointClaims(
            "GM-MVP-1",
            "AG-CHECKPOINT-1",
            "cp-" + str(seq),
            SCOPE.stream_id,
            SCOPE.gateway_id,
            SCOPE.tenant_id,
            SCOPE.task_id,
            1,
            seq,
            records[seq - 1].digest,
            previous_cp,
            STAMP,
            "test-audit",
        )
        jws = sign_compact_jws(
            key, asdict(claims), key_id="test-audit", token_type="ag-checkpoint+jwt"
        )
        cp = verify_checkpoint(jws, trust=trust, expected_scope=SCOPE)
        checkpoints.append(cp)
        previous_cp = cp.jws_digest
    observed = checkpoints[-1]
    history = (
        HistoryPage(SCOPE.stream_id, "cp-130", 130, tuple(c.jws for c in checkpoints[:2]), 64),
        HistoryPage(SCOPE.stream_id, "cp-130", 130, tuple(c.jws for c in checkpoints[2:]), None),
    )
    pages = tuple(
        RecordPage(
            SCOPE.stream_id,
            "cp-130",
            130,
            tuple(r.raw for r in records[start : start + 64]),
            min(start + 64, 130) if start + 64 < 130 else None,
        )
        for start in (0, 64, 128)
    )
    return key, trust, tuple(records), observed, history, pages


def test_complete_multipage_proof(proof):
    _, trust, records, observed, history, pages = proof
    verified = reconcile_remote_ahead(
        records,
        observed,
        history,
        pages,
        trust,
        expected_stream=ExistingStreamRef(SCOPE, genesis_digest(SCOPE), DIGEST),
    )
    assert verified.sequence == 130 and verified.head_digest == records[-1].digest
    assert (
        verified.checkpoint_jws == observed.jws
        and verified.checkpoint_digest == observed.jws_digest
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "history_missing",
        "records_missing",
        "record_gap",
        "record_reorder",
        "history_reorder",
        "history_cursor",
        "record_cursor",
        "pin",
        "scope",
        "bootstrap",
        "genesis",
        "local_forgery",
        "observed_forgery",
        "boundary",
    ),
)
def test_reconciliation_rejects_incomplete_or_forked_proofs(proof, mutation):
    _, trust, records, observed, history, pages = proof
    stream = ExistingStreamRef(SCOPE, genesis_digest(SCOPE), DIGEST)
    if mutation == "history_missing":
        history = history[1:]
    elif mutation == "records_missing":
        pages = pages[:-1]
    elif mutation == "record_gap":
        pages = (replace(pages[0], entries=pages[0].entries[1:]),) + pages[1:]
    elif mutation == "record_reorder":
        pages = (pages[1], pages[0], pages[2])
    elif mutation == "history_reorder":
        history = tuple(reversed(history))
    elif mutation == "history_cursor":
        history = (replace(history[0], next_after_sequence=63), history[1])
    elif mutation == "record_cursor":
        pages = (replace(pages[0], next_after_sequence=63),) + pages[1:]
    elif mutation == "pin":
        pages = (replace(pages[0], observed_checkpoint_id="other"),) + pages[1:]
    elif mutation == "scope":
        stream = replace(stream, scope=replace(SCOPE, task_id="other"))
    elif mutation == "bootstrap":
        stream = replace(stream, bootstrap_digest=genesis_digest(SCOPE))
    elif mutation == "genesis":
        stream = replace(stream, genesis_digest=DIGEST)
    elif mutation == "local_forgery":
        records = (replace(records[0], digest=DIGEST),) + records[1:]
    elif mutation == "observed_forgery":
        observed = replace(observed, jws_digest=DIGEST)
    elif mutation == "boundary":
        pages = (replace(pages[0], observed_sequence=129),) + pages[1:]
    with pytest.raises((DeliveryError, ValueError)):
        reconcile_remote_ahead(records, observed, history, pages, trust, expected_stream=stream)


@pytest.mark.parametrize(
    "mutation",
    (
        "wrongrole",
        "unknownkid",
        "range",
        "wrongscope",
        "signature",
        "duplicatekey",
        "wrongtype",
        "payloadkid",
        "unknownclaim",
        "noncanonical",
    ),
)
def test_independent_checkpoint_rejection(proof, mutation):
    key, trust, records, observed, history, pages = proof
    jws = observed.jws
    scope = SCOPE
    if mutation == "wrongrole":
        trust = (replace(trust[0], role="WRITER"),)
    elif mutation == "unknownkid":
        trust = (replace(trust[0], kid="unknown"),)
    elif mutation == "range":
        trust = (replace(trust[0], last_sequence=129),)
    elif mutation == "wrongscope":
        scope = replace(SCOPE, tenant_id="other")
    elif mutation == "signature":
        jws = jws[:-4] + "AAAA"
    elif mutation == "duplicatekey":
        trust += trust
    else:
        claims = asdict(observed.claims)
        if mutation == "payloadkid":
            claims["kid"] = "different"
        elif mutation == "unknownclaim":
            claims["unsafe"] = True
        elif mutation == "noncanonical":
            from agent_guard.contracts.encoding import b64url_encode
            from agent_guard.crypto.sm import _der_to_jws_signature, sign_sm2_message

            header = jws.split(".")[0]
            body = b64url_encode(b" " + canonical_json_bytes(claims))
            original = header + "." + body
            jws = (
                original
                + "."
                + b64url_encode(
                    _der_to_jws_signature(sign_sm2_message(key, original.encode("ascii")))
                )
            )
        if mutation != "noncanonical":
            jws = sign_compact_jws(
                key,
                claims,
                key_id="test-audit",
                token_type="ag-receipt+jwt" if mutation == "wrongtype" else "ag-checkpoint+jwt",
            )
    with pytest.raises((DeliveryError, ValueError)):
        verify_checkpoint(jws, trust=trust, expected_scope=scope)
    with pytest.raises((DeliveryError, ValueError)):
        authenticate_reconciliation(
            records,
            replace(observed, jws=jws),
            history,
            pages,
            trust,
            expected_stream=ExistingStreamRef(scope, genesis_digest(scope), DIGEST),
        )


@pytest.mark.parametrize(
    "origin",
    (
        "http://localhost",
        "https://u:p@localhost",
        "https://localhost/path",
        "https://localhost?x=1",
        "https://localhost#x",
    ),
)
def test_transport_rejects_arbitrary_urls(origin):
    with pytest.raises(ValueError):
        AuditClient(
            origin,
            ca_file="unused",
            writer_credential="w:secret",
            reader_credential="r:secret",
        )


@pytest.mark.parametrize("boundary", (32, 64, 65, 130))
def test_authenticated_reconciliation_factory_and_exact_parent_boundaries(proof, boundary):
    import copy
    from dataclasses import FrozenInstanceError

    from agent_guard.audit.contracts import encode_append_batch
    from agent_guard.audit.delivery import (
        _authenticated,
        authenticate_reconciliation,
    )

    key, trust, records, _, _, _ = proof
    previous = None
    checkpoints = []
    for seq in sorted({32, boundary}):
        claims = CheckpointClaims(
            "GM-MVP-1",
            "AG-CHECKPOINT-1",
            "pin-" + str(seq),
            SCOPE.stream_id,
            SCOPE.gateway_id,
            SCOPE.tenant_id,
            SCOPE.task_id,
            1,
            seq,
            records[seq - 1].digest,
            previous,
            STAMP,
            "test-audit",
        )
        cp = verify_checkpoint(
            sign_compact_jws(
                key, asdict(claims), key_id="test-audit", token_type="ag-checkpoint+jwt"
            ),
            trust=trust,
            expected_scope=SCOPE,
        )
        checkpoints.append(cp)
        previous = cp.jws_digest
    observed = checkpoints[-1]
    history = (
        HistoryPage(
            SCOPE.stream_id,
            observed.claims.checkpoint_id,
            boundary,
            tuple(c.jws for c in checkpoints),
            None,
        ),
    )
    pages = tuple(
        RecordPage(
            SCOPE.stream_id,
            observed.claims.checkpoint_id,
            boundary,
            tuple(r.raw for r in records[start : min(start + 64, boundary)]),
            start + 64 if start + 64 < boundary else None,
        )
        for start in range(0, boundary, 64)
    )
    authenticated = authenticate_reconciliation(
        records,
        observed,
        history,
        pages,
        trust,
        expected_stream=ExistingStreamRef(SCOPE, genesis_digest(SCOPE), DIGEST),
    )
    _authenticated(authenticated)
    mutable_stream = type("MutableStream", (), {})()
    mutable_stream.scope = SCOPE
    mutable_stream.genesis_digest = genesis_digest(SCOPE)
    mutable_stream.bootstrap_digest = DIGEST
    with pytest.raises(DeliveryError):
        authenticate_reconciliation(
            records, observed, history, pages, trust, expected_stream=mutable_stream
        )
    assert authenticated.expected_stream.scope is not SCOPE
    assert authenticated.local_raw == tuple(r.raw for r in records)
    assert authenticated.prefix.sequence == boundary
    assert authenticated.checkpoint_digests == tuple(c.jws_digest for c in checkpoints)
    with pytest.raises(FrozenInstanceError):
        authenticated.local_raw = ()
    with pytest.raises(TypeError):
        authenticated.local_raw[0] = b"{}"
    for forged in (
        type(authenticated)(
            authenticated.expected_stream,
            authenticated.prefix,
            authenticated.local_raw,
            authenticated.checkpoint_digests,
        ),
        copy.copy(authenticated),
        replace(authenticated, local_raw=()),
        authenticated.prefix,
        observed,
        asdict(authenticated),
    ):
        with pytest.raises(DeliveryError):
            _authenticated(forged)
    # This pure-wire fixture has compact PUBLISH records; full SM2 authenticates CP32->65.
    # It is not a substitute for the separate real business/SQL journal integration.
    parent = encode_append_batch(SCOPE.stream_id, tuple(r.raw for r in records[:64]))
    assert parent.start_sequence == 1 and parent.end_sequence == 64
    if boundary == 32:
        child = encode_append_batch(SCOPE.stream_id, parent.entries[32:])
        assert (child.start_sequence, child.end_sequence) == (33, 64)
    if boundary == 65:
        crossing = encode_append_batch(SCOPE.stream_id, tuple(r.raw for r in records[64:70]))
        assert (crossing.start_sequence, crossing.end_sequence) == (65, 70)
        child = encode_append_batch(SCOPE.stream_id, crossing.entries[1:])
        assert (child.start_sequence, child.end_sequence) == (66, 70)
