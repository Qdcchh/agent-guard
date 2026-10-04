"""Read immutable final facts and project the sole GM-MVP-1 receipt payload.

No signing, publication, outbox update or dynamic result authorization occurs.
Caller must independently authorize access. Legacy opaque evidence fails closed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.contracts.ledger_changes import canonical_ledger_changes_bytes, load_ledger_changes
from agent_guard.crypto.sm import sm3_b64url
from agent_guard.execution import store
from agent_guard.execution.receipts import receipt_iat, receipt_id_for
from agent_guard.ledger import store as ledger_store
from agent_guard.tools.results import (
    NotificationResult,
    OrderResult,
    ReadResult,
    RefusalResult,
    bind_result,
    parse_result,
)


class ReceiptProjectionError(ValueError):
    """The persisted facts cannot safely become real signed receipt material."""


@dataclass(frozen=True)
class ReceiptProjection:
    claims_bytes: bytes
    ledger_bytes: bytes
    result_bytes: bytes
    token_bytes: bytes
    proof_bytes: bytes
    request_bytes: bytes
    ancestor_tokens: tuple[str, ...]


def project_receipt(conn, operation_id: str) -> ReceiptProjection:
    """Only the DB-backed entry point accepts input; no client-provided material."""
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM ag_receipt_outbox WHERE operation_id=%s", (operation_id,))
        row = cursor.fetchone()
        if row is None:
            raise ReceiptProjectionError("no final receipt material")
        out = dict(zip([col.name for col in cursor.description], row, strict=True))
    op = store.fetch_operation(conn, operation_id)
    if op is None or op.status not in ("SUCCEEDED", "FAILED") or out["status"] != op.status:
        raise ReceiptProjectionError("operation is not consistently final")
    path = ledger_store.load_path(conn, op.grant_id)
    ids = tuple(g.grant_id for g in path)
    if len(set(ids)) != len(ids) or not 1 <= len(ids) <= 3:
        raise ReceiptProjectionError("invalid complete path")
    for key, expected in {
        "receipt_id": receipt_id_for(operation_id),
        "profile": "GM-MVP-1",
        "tenant_id": op.tenant_id,
        "task_id": op.task_id,
        "grant_id": op.grant_id,
        "root_grant_id": ids[0],
        "tool_id": op.tool_id,
        "tool_version": op.tool_version,
        "token_digest": op.token_digest,
        "proof_digest": op.proof_digest,
        "intent_digest": op.intent_digest,
        "evidence_ref": op.evidence_ref,
        "amount_fen": op.amount_fen if op.status == "SUCCEEDED" else 0,
    }.items():
        if out[key] != expected:
            raise ReceiptProjectionError("outbox binding mismatch")
    internal = load_ledger_changes(bytes(out["ledger_changes_json"]), internal=True)
    events = store.fetch_event_nodes(conn, operation_id)
    if internal["operation_id"] != operation_id or len(events) != 2 or len(internal["events"]) != 2:
        raise ReceiptProjectionError("missing or mismatched terminal history")
    terminal = "SETTLE" if op.status == "SUCCEEDED" else "RELEASE"
    for index, (row, event) in enumerate(zip(internal["events"], events, strict=True)):
        phase = "RESERVE" if index == 0 else terminal
        if (row["phase"], row["seq"], event.phase, event.seq) != (phase, index, phase, index):
            raise ReceiptProjectionError("invalid phase or sequence")
        if tuple(n["grant_id"] for n in row["nodes"]) != ids:
            raise ReceiptProjectionError("wrong, reordered or incomplete ledger path")
        expected_deltas = (
            (op.amount_fen, 0, op.calls, 0)
            if index == 0
            else (
                -op.amount_fen,
                op.amount_fen if phase == "SETTLE" else 0,
                -op.calls,
                op.calls if phase == "SETTLE" else 0,
            )
        )
        for position, (node, persisted) in enumerate(zip(row["nodes"], event.nodes, strict=True)):
            saved = asdict(persisted)
            saved.pop("position")
            if (
                saved != node
                or persisted.position != position
                or tuple(
                    node[k]
                    for k in (
                        "amount_reserved_delta",
                        "amount_settled_delta",
                        "calls_reserved_delta",
                        "calls_settled_delta",
                    )
                )
                != expected_deltas
            ):
                raise ReceiptProjectionError("invalid persisted ledger delta")
    evidence = conn.execute(
        "SELECT e.token_bytes,e.proof_bytes,e.body_bytes,e.token_sm3,"
        "e.proof_sm3,e.body_sm3 FROM ag_operation_evidence l JOIN ag_verified_evidence e "
        "ON e.evidence_ref=l.evidence_ref WHERE l.operation_id=%s AND l.kind='first' "
        "AND l.evidence_ref=%s",
        (operation_id, op.evidence_ref),
    ).fetchone()
    if evidence is None:
        raise ReceiptProjectionError("legacy opaque first evidence cannot be reconstructed")
    token, proof, request = map(bytes, evidence[:3])
    if (sm3_b64url(token), sm3_b64url(proof), sm3_b64url(request)) != tuple(evidence[3:]):
        raise ReceiptProjectionError("raw evidence digest mismatch")
    request_object = load_strict_json(request)
    if sm3_b64url(canonical_json_bytes(request_object)) != op.intent_digest:
        raise ReceiptProjectionError("original intent mismatch")
    if evidence[3] != op.token_digest or evidence[4] != op.proof_digest:
        raise ReceiptProjectionError("first token/proof mismatch")
    result_raw = bytes(out["result_bytes"])
    result = load_strict_json(result_raw)
    parsed = parse_result(result_raw)
    bind_result(parsed, operation_id=operation_id, tool_id=op.tool_id)
    if isinstance(parsed, RefusalResult) != (op.status == "FAILED"):
        raise ReceiptProjectionError("result and terminal status disagree")
    success_type = {
        "procurement.request.read": ReadResult,
        "procurement.document.read": ReadResult,
        "procurement.order.create": OrderResult,
        "notification.template.send": NotificationResult,
    }.get(op.tool_id)
    if success_type is None or (op.status == "SUCCEEDED" and type(parsed) is not success_type):
        raise ReceiptProjectionError("result variant does not match operation tool")
    if isinstance(parsed, OrderResult):
        quote = load_strict_json(bytes(op.quote_snapshot))
        if (
            parsed.total_fen != op.amount_fen
            or parsed.supplier_id != quote["supplier_id"]
            or parsed.quote_id != op.quote_id
            or parsed.quote_version != op.quote_version
            or list(parsed.items)
            != [(x["sku"], x["quantity"], x["unit_price_fen"]) for x in quote["items"]]
        ):
            raise ReceiptProjectionError("result and original quote disagree")
    if isinstance(parsed, NotificationResult):
        params = load_strict_json(bytes(op.canonical_params))
        if (
            parsed.template_id != params["template_id"]
            or parsed.recipient_id != params["recipient_id"]
        ):
            raise ReceiptProjectionError("notification result mismatch")
    public = {
        "operation_id": operation_id,
        "events": [{"phase": e["phase"], "nodes": e["nodes"]} for e in internal["events"]],
    }
    encoded = canonical_ledger_changes_bytes(public)
    result_encoded = canonical_json_bytes(result)
    claims = {
        "profile": "GM-MVP-1",
        "receipt_id": out["receipt_id"],
        "operation_id": operation_id,
        "tenant_id": op.tenant_id,
        "task_id": op.task_id,
        "root_grant_id": ids[0],
        "grant_id": op.grant_id,
        "token_sm3": op.token_digest,
        "proof_sm3": op.proof_digest,
        "intent_sm3": op.intent_digest,
        "tool_id": op.tool_id,
        "tool_version": op.tool_version,
        "status": op.status,
        "amount_fen": out["amount_fen"],
        "result_sm3": sm3_b64url(result_encoded),
        "ledger_sm3": sm3_b64url(encoded),
        "iat": receipt_iat(out["created_at"]),
    }
    tokens = []
    for grant_id in ids:
        saved = conn.execute(
            "SELECT token_jws FROM ag_grant_tokens WHERE grant_id=%s", (grant_id,)
        ).fetchone()
        if saved is None:
            raise ReceiptProjectionError("missing signed ancestor evidence")
        tokens.append(saved[0])
    if tokens[-1].encode("ascii") != token:
        raise ReceiptProjectionError("first token is not immutable leaf token")
    return ReceiptProjection(
        canonical_json_bytes(claims), encoded, result_encoded, token, proof, request, tuple(tokens)
    )
