"""Bind the immutable x402 payment intent into the accept transaction.

The CNY operation, its ledger reservation, the V3 threshold approval row and
the payment intent (plus the independent test-asset budget reservation) are
one database transaction. A refusal at any step rolls all of them back, so a
refused payment can neither burn budget nor consume an approval.
"""

from __future__ import annotations

from agent_guard.threshold.contracts import VerifiedThresholdApproval
from agent_guard.x402.config import X402Deployment
from agent_guard.x402.contracts import X402Error, build_intent, require_approval_digest
from agent_guard.x402.state import assert_payment_tx, reserve_payment_tx


def _approval_matches_operation(approval: VerifiedThresholdApproval, operation) -> None:
    expected = (
        ("tenant_id", approval.tenant_id, operation.tenant_id),
        ("task_id", approval.task_id, operation.task_id),
        ("grant_id", approval.grant_id, operation.grant_id),
        ("tool_id", approval.tool_id, operation.tool_id),
        ("idempotency_key", approval.idempotency_key, operation.idempotency_key),
        ("quote_id", approval.quote_id, operation.quote_id),
        ("quote_version", approval.quote_version, operation.quote_version),
        ("amount_fen", approval.amount_fen, operation.amount_fen),
    )
    for name, approved, accepted in expected:
        if approved != accepted:
            raise X402Error(
                f"approved payment fact {name} differs from the accepted operation",
                code="PAYMENT_APPROVAL_MISMATCH",
            )


def payment_binding(deployment: X402Deployment, approval: VerifiedThresholdApproval):
    """Return (same-TX reservation callback, final same-TX digest check)."""
    if type(deployment) is not X402Deployment:
        raise X402Error("trusted x402 deployment required", code="CONFIG_INVALID")
    if type(approval) is not VerifiedThresholdApproval:
        raise X402Error("verified threshold approval required", code="PAYMENT_APPROVAL_MISSING")
    if approval.payment_digest is None:
        raise X402Error("V3 approval with a payment digest required", code="PAYMENT_DIGEST_MISSING")
    profile = deployment.profile

    def reserve(conn, operation, disposition):
        _approval_matches_operation(approval, operation)
        # The approved expiry fixes the authorization validity, so the payer
        # (V3 signing) and the gateway compute the exact same intent digest.
        intent = build_intent(
            profile=profile,
            tenant_id=operation.tenant_id,
            task_id=operation.task_id,
            grant_id=approval.grant_id,
            root_grant_id=approval.root_grant_id,
            tool_id=operation.tool_id,
            idempotency_key=operation.idempotency_key,
            quote_id=operation.quote_id,
            quote_version=operation.quote_version,
            amount_fen=operation.amount_fen,
            valid_before=approval.expires_at,
        )
        require_approval_digest(intent, approval.payment_digest)
        reserve_payment_tx(
            conn,
            operation=operation,
            action_id=approval.action_id,
            intent=intent,
            amount_fen=operation.amount_fen,
        )

    def final_check(conn, operation, disposition):
        assert_payment_tx(conn, operation_id=operation.operation_id, digest=approval.payment_digest)

    return reserve, final_check


def accept_with_payment(execution, bundle, *, approval, deployment):
    """Run the existing verified accept with the payment reservation composed in."""
    reserve, final_check = payment_binding(deployment, approval)
    return execution.accept(
        bundle,
        approval=approval,
        extra_binding=reserve,
        extra_final_check=final_check,
    )
