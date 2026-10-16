"""Validate immutable first evidence and derive operation-scoped historical trust."""

from dataclasses import fields
from types import MappingProxyType

from agent_guard.authorization.evidence_store import EvidenceError, context_bytes
from agent_guard.authorization.proof import verify_ag_proof
from agent_guard.contracts.encoding import (
    b64url_decode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode
from agent_guard.contracts.ledger import VerifiedInvocation
from agent_guard.crypto.sm import load_sm2_public_key, sm3_b64url, verify_compact_jws
from agent_guard.evidence.receipt import ReceiptTrust
from agent_guard.execution import store
from agent_guard.execution.receipt_projection import project_receipt
from agent_guard.execution.service import verify_accept_facts


def validate_original_tx(conn, op, source):
    row = conn.execute(
        "SELECT e.token_bytes,e.proof_bytes,e.body_bytes,e.token_sm3,e.proof_sm3,e.body_sm3 "
        " ,e.context_json,e.chain_json FROM ag_operation_evidence l JOIN "
        "ag_verified_evidence e USING(evidence_ref) "
        "WHERE l.operation_id=%s AND l.kind='first' AND l.evidence_ref=%s",
        (op.operation_id, op.evidence_ref),
    ).fetchone()
    if row is None or tuple(sm3_b64url(bytes(v)) for v in row[:3]) != tuple(row[3:6]):
        raise EvidenceError("missing original signed material")
    request = load_strict_json(bytes(row[2]))
    context = load_strict_json(bytes(row[6]))
    if (
        type(request) is not dict
        or set(request)
        != {
            "profile",
            "task_id",
            "tool_id",
            "tool_version",
            "idempotency_key",
            "params",
        }
        or request["profile"] != "GM-MVP-1"
        or type(request["params"]) is not dict
        or type(context) is not dict
        or set(context) != {field.name for field in fields(VerifiedInvocation)} - {"evidence_ref"}
    ):
        raise EvidenceError("invalid original material schema")
    if bytes(row[7]) != source.material() or (
        context.get("purpose") != "invoke"
        or context.get("endpoint") != "https://gateway.agent-guard.test/v1/invocations"
        or context.get("method") != "POST"
        or context.get("grant_id") != op.grant_id
        or context.get("holder_client_id") != op.holder_client_id
        or context.get("holder_kid") != op.holder_kid
        or context.get("subject") != source.snapshot.subject
    ):
        raise EvidenceError("original evidence context/source mismatch")
    if (row[3], row[4], sm3_b64url(canonical_json_bytes(request))) != (
        op.token_digest,
        op.proof_digest,
        op.intent_digest,
    ) or (
        request.get("task_id"),
        request.get("tool_id"),
        request.get("tool_version"),
        request.get("idempotency_key"),
        canonical_json_bytes(request.get("params")),
    ) != (
        op.task_id,
        op.tool_id,
        op.tool_version,
        op.idempotency_key,
        op.canonical_params,
    ):
        raise ExecutionError(ExecutionErrorCode.LEGACY_SNAPSHOT_INVALID)

    # The raw first token/proof have already been digest-bound to the
    # immutable accepted operation. Decode those exact bytes to reconstruct
    # every context field; the original proof need not still be fresh.
    # Freshness belongs to this query's new proof and current grant path.
    def payload(raw):
        parts = bytes(raw).decode("ascii").split(".")
        if len(parts) != 3:
            raise EvidenceError("invalid original compact material")
        value = load_strict_json(b64url_decode(parts[1]))
        if type(value) is not dict:
            raise EvidenceError("invalid original compact payload")
        return value

    token, proof = payload(row[0]), payload(row[1])
    if (
        any(type(v) is not int or v < 0 for v in (token["exp"], proof["iat"], proof["exp"]))
        or type(proof["jti"]) is not str
        or proof["profile"] != "GM-MVP-1"
        or proof["purpose"] != "invoke"
        or proof["client_id"] != op.holder_client_id
        or proof["htm"] != "POST"
        or proof["htu"] != "https://gateway.agent-guard.test/v1/invocations"
        or proof["token_sm3"] != op.token_digest
        or proof["body_sm3"] != op.intent_digest
        or (
            token["sub"],
            token["ag_tenant_id"],
            token["ag_task_id"],
            token["ag_grant_id"],
            token["ag_root_id"],
            token["client_id"],
            token["ag_cnf"]["kid"],
        )
        != (
            source.snapshot.subject,
            op.tenant_id,
            op.task_id,
            op.grant_id,
            source.snapshot.root_id,
            op.holder_client_id,
            op.holder_kid,
        )
    ):
        raise EvidenceError("invalid original token/proof binding")
    expected = VerifiedInvocation(
        subject=source.snapshot.subject,
        tenant_id=op.tenant_id,
        task_id=op.task_id,
        grant_id=op.grant_id,
        root_id=source.snapshot.root_id,
        holder_client_id=op.holder_client_id,
        holder_kid=op.holder_kid,
        tool_id=op.tool_id,
        tool_version=op.tool_version,
        idempotency_key=op.idempotency_key,
        canonical_params=op.canonical_params,
        token_exp=token["exp"],
        proof_iat=proof["iat"],
        proof_exp=proof["exp"],
        proof_jti=proof["jti"],
        token_digest=op.token_digest,
        proof_digest=op.proof_digest,
        intent_digest=op.intent_digest,
        evidence_ref=op.evidence_ref,
        ancestor_ids=source.snapshot.chain_grant_ids[:-1],
    )
    if bytes(row[6]) != context_bytes(expected):
        raise EvidenceError("original context does not match accepted signed facts")
    # Bind quote arithmetic, accepted cost and every ledger delta to the
    # historically verified root-to-leaf path before any receipt is signed.
    # This pure validation uses immutable accepted facts, not current quotes
    # or the path's current authorization state.
    verify_accept_facts(
        op,
        store.fetch_event_nodes(conn, op.operation_id),
        db_path=source.snapshot.chain_grant_ids,
    )


def scoped_trust_tx(
    conn,
    operation_id,
    *,
    issuer,
    as_keys,
    gateway_keys,
    registrations,
    permission_provider,
):
    """Derive a fresh trust value from the verified immutable operation chain.

    Registry aliases across operations remain legal. Within this signed chain,
    the existing AS validation rejects repeated actors and ambiguous paths.
    No current DID resolver is used to reinterpret a historical key.
    """
    projection = project_receipt(conn, operation_id)
    op = store.fetch_operation(conn, operation_id)
    claims = [
        verify_compact_jws(t, expected_type="ag-at+jwt", trusted_keys=as_keys)
        for t in projection.ancestor_tokens
    ]
    holder_keys = {}
    history = {}
    for raw in claims:
        key = (raw["ag_tenant_id"], raw["client_id"], raw["ag_cnf"]["kid"])
        registration = registrations.get(key)
        if (
            registration is None
            or key != (registration.tenant_id, registration.client_id, registration.kid)
            or registration.spki_sm3 != raw["ag_cnf"]["spki_sm3"]
        ):
            raise EvidenceError("missing exact historical holder tuple")
        kid = registration.kid
        if kid in history:
            raise EvidenceError("ambiguous signed holder path")
        history[kid] = registration
        holder_keys[kid] = load_sm2_public_key(registration.spki_der)
    proof = verify_compact_jws(
        projection.proof_bytes.decode("ascii"),
        expected_type="ag-pop+jwt",
        trusted_keys=holder_keys,
    )
    completion = load_strict_json(projection.claims_bytes)["iat"]
    times = [proof["iat"], proof["exp"], completion]
    times.extend(v[n] for v in claims for n in ("iat", "nbf", "exp"))
    if any(type(v) is not int or v < 0 for v in times):
        raise EvidenceError("invalid historical time")
    earliest = max(0, proof["iat"] - 5, *(max(v["iat"], v["nbf"]) for v in claims))
    latest = min(completion, proof["exp"] - 1, *(v["exp"] - 1 for v in claims))
    if earliest > latest:
        raise EvidenceError("no common historical authorization time")
    source = permission_provider.load_tx(
        conn, projection.token_bytes.decode("ascii"), grant_id=op.grant_id, now=earliest
    )
    validate_original_tx(conn, op, source)
    verify_ag_proof(
        projection.proof_bytes.decode("ascii"),
        trusted_keys={op.holder_kid: holder_keys[op.holder_kid]},
        client_id=op.holder_client_id,
        purpose="invoke",
        endpoint="https://gateway.agent-guard.test/v1/invocations",
        token=projection.token_bytes.decode("ascii"),
        body=load_strict_json(projection.request_bytes),
        now=earliest,
    )
    return ReceiptTrust(
        issuer=issuer,
        as_keys=MappingProxyType(dict(as_keys)),
        gateway_keys=MappingProxyType(dict(gateway_keys)),
        holder_keys=MappingProxyType(holder_keys),
        historical_registrations=MappingProxyType(history),
    )
