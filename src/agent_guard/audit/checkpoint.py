"""Authenticate checkpoints exclusively against externally registered SM2 keys."""

from dataclasses import asdict
from datetime import datetime, timezone

from agent_guard.audit.contracts import (
    CheckpointTrust,
    JournalScope,
    ObservedCheckpoint,
    decode_checkpoint_claims,
    integer,
    utc_text,
)
from agent_guard.contracts.encoding import EncodingError, b64url_decode, canonical_json_bytes
from agent_guard.crypto.sm import (
    load_sm2_public_key,
    sign_compact_jws,
    sm3_b64url,
    verify_compact_jws,
)


def sign_checkpoint(claims, *, private_key, key_id: str) -> str:
    value = asdict(claims) if not isinstance(claims, dict) else claims
    checked = decode_checkpoint_claims(canonical_json_bytes(value))
    if checked.kid != key_id:
        raise EncodingError("checkpoint key binding mismatch")
    jws = sign_compact_jws(private_key, value, key_id=key_id, token_type="ag-checkpoint+jwt")
    if len(jws) > 16384:
        raise EncodingError("checkpoint capacity exceeded")
    return jws


def verify_checkpoint(
    jws: str, *, trust: tuple[CheckpointTrust, ...], expected_scope: JournalScope
) -> ObservedCheckpoint:
    if type(jws) is not str or not jws.isascii() or not 1 <= len(jws) <= 16384:
        raise EncodingError("invalid checkpoint capacity")
    if type(trust) is not tuple or not trust:
        raise EncodingError("external checkpoint trust required")
    keys = {}
    for entry in trust:
        if type(entry) is not CheckpointTrust or entry.role != "AUDIT_SIGNER" or entry.kid in keys:
            raise EncodingError("invalid external checkpoint trust")
        integer(entry.first_sequence, minimum=1)
        if entry.last_sequence is not None:
            integer(entry.last_sequence, minimum=entry.first_sequence)
        keys[entry.kid] = load_sm2_public_key(entry.spki_der)
    value = verify_compact_jws(jws, expected_type="ag-checkpoint+jwt", trusted_keys=keys)
    claims = decode_checkpoint_claims(b64url_decode(jws.split(".")[1]))
    if value != asdict(claims):
        raise EncodingError("checkpoint canonical claims mismatch")
    from agent_guard.contracts.encoding import load_strict_json

    header = load_strict_json(b64url_decode(jws.split(".")[0]))
    if header["kid"] != claims.kid:
        raise EncodingError("checkpoint protected key mismatch")
    scope = JournalScope(
        claims.gateway_id, claims.tenant_id, claims.task_id, claims.stream_id, claims.epoch
    )
    if scope != expected_scope:
        raise EncodingError("checkpoint scope mismatch")
    key = next((entry for entry in trust if entry.kid == claims.kid), None)
    if (
        key is None
        or claims.sequence < key.first_sequence
        or (key.last_sequence is not None and claims.sequence > key.last_sequence)
    ):
        raise EncodingError("checkpoint key sequence outside external range")
    return ObservedCheckpoint(
        jws, claims, sm3_b64url(jws.encode("ascii")), utc_text(datetime.now(timezone.utc))
    )
