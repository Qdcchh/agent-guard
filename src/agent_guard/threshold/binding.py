"""Atomic approval-to-operation binding inside the existing acceptance TX.

The composed callback runs under the acceptance transaction's locks (after the
operation row exists or the existing row was found) and does two things in one
transaction:

1. compares the immutable verified approval facts against the *actual*
   operation row and the authoritative database authorization path — retries
   use the original persisted cost, never today's catalog;
2. inserts the durable ``(tenant, task, action_id)`` binding without ever
   overwriting an existing row; a concurrent or repeated use must match the
   original binding exactly or it is rejected.

The final check runs after every deferred constraint, journal append and
evidence/publication write, using the database clock, so an approval that
expires while the transaction was working is refused after all other checks.
"""

from __future__ import annotations

import psycopg

from agent_guard.contracts.execution import ToolId
from agent_guard.contracts.ledger import ErrorCode, LedgerError
from agent_guard.ledger import store as ledger_store
from agent_guard.threshold.codec import compute_params_digest, parse_envelope
from agent_guard.threshold.contracts import (
    COSM2_PROFILE,
    COSM2ApprovalExpired,
    ThresholdApprovalError,
    VerifiedThresholdApproval,
)
from agent_guard.tools.params import parse_tool_params

_INSERT = (
    "INSERT INTO ag_threshold_approvals ("
    "tenant_id,task_id,action_id,operation_id,grant_id,root_grant_id,path_ids,"
    "holder_client_id,holder_kid,tool_id,tool_version,idempotency_key,"
    "amount_fen,currency,quote_id,quote_version,policy_version,key_epoch,"
    "expires_at,message_sha256,envelope_sm3,envelope_bytes,payment_digest"
    ") VALUES ("
    "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
    "to_timestamp(%s),%s,%s,%s,%s"
    ") ON CONFLICT (tenant_id,task_id,action_id) DO NOTHING "
    "RETURNING operation_id"
)
_SELECT = (
    "SELECT operation_id,grant_id,root_grant_id,path_ids,holder_client_id,holder_kid,"
    "tool_id,tool_version,idempotency_key,amount_fen,currency,quote_id,quote_version,"
    "policy_version,key_epoch,message_sha256,envelope_sm3,payment_digest "
    "FROM ag_threshold_approvals WHERE tenant_id=%s AND task_id=%s AND action_id=%s"
)


def approval_binding(approval: VerifiedThresholdApproval):
    """Return ``(callback, final_check)`` for ``TrustedAcceptBinding.compose``."""
    if type(approval) is not VerifiedThresholdApproval:
        raise ValueError("verified threshold approval required")

    def callback(conn: psycopg.Connection, operation, disposition) -> None:
        path_ids, _params = _checked_operation(conn, operation, approval)
        row = conn.execute(
            _INSERT,
            (
                approval.tenant_id,
                approval.task_id,
                approval.action_id,
                operation.operation_id,
                operation.grant_id,
                approval.root_grant_id,
                list(path_ids),
                approval.holder_client_id,
                approval.holder_kid,
                approval.tool_id,
                approval.tool_version,
                approval.idempotency_key,
                approval.amount_fen,
                approval.currency,
                approval.quote_id,
                approval.quote_version,
                approval.policy_version,
                approval.key_epoch,
                approval.expires_at,
                approval.message_sha256,
                approval.envelope_sm3,
                approval.envelope_bytes,
                approval.payment_digest,
            ),
        ).fetchone()
        if row is not None:
            return
        # A concurrent accept may have committed the same action while this
        # transaction waited on the unique key. Never overwrite: the existing
        # binding must describe exactly this action and operation.
        existing = conn.execute(
            _SELECT, (approval.tenant_id, approval.task_id, approval.action_id)
        ).fetchone()
        if existing is None or not _row_matches(existing, approval, operation, path_ids):
            raise LedgerError(
                ErrorCode.APPROVAL_MISMATCH,
                "threshold approval is already bound to a different operation",
            )

    def final_check(conn: psycopg.Connection, operation, disposition) -> None:
        row = conn.execute(
            "SELECT operation_id,message_sha256 FROM ag_threshold_approvals "
            "WHERE tenant_id=%s AND task_id=%s AND action_id=%s",
            (approval.tenant_id, approval.task_id, approval.action_id),
        ).fetchone()
        if row is None or row[0] != operation.operation_id or row[1] != approval.message_sha256:
            raise LedgerError(
                ErrorCode.APPROVAL_MISMATCH,
                "threshold approval binding disappeared or changed",
            )
        if ledger_store.db_now_epoch(conn) >= approval.expires_at:
            try:
                parse_envelope(approval.envelope_bytes, profile=COSM2_PROFILE)
            except ThresholdApprovalError:
                pass
            else:
                raise COSM2ApprovalExpired()
            raise LedgerError(ErrorCode.EXPIRED, "threshold approval expired before commit")

    return callback, final_check


def _checked_operation(conn, operation, approval: VerifiedThresholdApproval):
    """Compare the approval against the actual row and locked DB path."""
    path = ledger_store.load_path(conn, operation.grant_id)
    path_ids = tuple(grant.grant_id for grant in path)
    if (
        not path_ids
        or path_ids[0] != approval.root_grant_id
        or path_ids[-1] != operation.grant_id
        or path_ids != approval.path_grant_ids
        or operation.tenant_id != approval.tenant_id
        or operation.task_id != approval.task_id
        or operation.holder_client_id != approval.holder_client_id
        or operation.holder_kid != approval.holder_kid
        or operation.tool_id != approval.tool_id
        or operation.tool_version != approval.tool_version
        or operation.idempotency_key != approval.idempotency_key
        or operation.currency != approval.currency
        or operation.amount_fen != approval.amount_fen
        or operation.quote_id != approval.quote_id
        or operation.quote_version != approval.quote_version
    ):
        raise LedgerError(
            ErrorCode.APPROVAL_MISMATCH,
            "threshold approval does not match the accepted operation",
        )
    try:
        params = parse_tool_params(ToolId(operation.tool_id), operation.canonical_params)
    except (ValueError, TypeError, RecursionError) as exc:
        raise LedgerError(
            ErrorCode.APPROVAL_MISMATCH,
            "accepted operation parameters are unusable",
        ) from exc
    digest = compute_params_digest(
        request_id=params.request_id,
        quote_id=params.quote_id,
        quote_version=params.quote_version,
        items=[(item.sku, item.quantity) for item in params.items],
        delivery_id=params.delivery_id,
    )
    if (
        digest != approval.canonical_params_sha256
        or approval.request_id != params.request_id
        or approval.quote_id != params.quote_id
        or approval.quote_version != params.quote_version
        or approval.delivery_id != params.delivery_id
        or approval.items != tuple((item.sku, item.quantity) for item in params.items)
    ):
        raise LedgerError(
            ErrorCode.APPROVAL_MISMATCH,
            "threshold approval does not match the accepted order parameters",
        )
    return path_ids, params


def _row_matches(row, approval, operation, path_ids) -> bool:
    (
        operation_id,
        grant_id,
        root_grant_id,
        stored_path,
        holder_client_id,
        holder_kid,
        tool_id,
        tool_version,
        idempotency_key,
        amount_fen,
        currency,
        quote_id,
        quote_version,
        policy_version,
        key_epoch,
        message_sha256,
        envelope_sm3,
        payment_digest,
    ) = row
    return (
        operation_id == operation.operation_id
        and grant_id == operation.grant_id
        and root_grant_id == approval.root_grant_id
        and tuple(stored_path) == tuple(path_ids)
        and holder_client_id == approval.holder_client_id
        and holder_kid == approval.holder_kid
        and tool_id == approval.tool_id
        and tool_version == approval.tool_version
        and idempotency_key == approval.idempotency_key
        and amount_fen == approval.amount_fen
        and currency == approval.currency
        and quote_id == approval.quote_id
        and quote_version == approval.quote_version
        and policy_version == approval.policy_version
        and key_epoch == approval.key_epoch
        and message_sha256 == approval.message_sha256
        and envelope_sm3 == approval.envelope_sm3
        and payment_digest == approval.payment_digest
    )
