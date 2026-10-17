"""Independent cryptographic/intent gate for already accepted order effects.

This gate does not repeat AS, budget, revocation or wall-clock expiry policy.
Those decisions belong to gateway acceptance; delayed immutable work can recover.
"""

from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode, ToolId
from agent_guard.cosign.encoding import signature_rs_to_der
from agent_guard.crypto.sm import load_sm2_public_key, verify_sm2_message
from agent_guard.threshold.codec import compute_params_digest, cosm2_message, parse_envelope
from agent_guard.threshold.contracts import COSM2_PROFILE, ThresholdApprovalPolicy
from agent_guard.tools.params import parse_tool_params


def check_effect_approval(
    policy,
    *,
    envelope,
    tenant_id,
    task_id,
    idempotency_key,
    canonical_params,
    quote,
    expected_amount_fen,
):
    """Return the signed action only after mature signature and exact binding."""
    try:
        if type(policy) is not ThresholdApprovalPolicy or policy.scheme != "sm2-2p":
            raise ValueError("invalid effect policy")
        action, signature = parse_envelope(envelope, profile=COSM2_PROFILE)
        verify_sm2_message(
            load_sm2_public_key(policy.group_public_key),
            cosm2_message(action),
            signature_rs_to_der(signature),
        )
        params = parse_tool_params(ToolId.ORDER_CREATE, canonical_params)
        digest = compute_params_digest(
            request_id=params.request_id,
            quote_id=params.quote_id,
            quote_version=params.quote_version,
            items=[(i.sku, i.quantity) for i in params.items],
            delivery_id=params.delivery_id,
        )
        if (
            action["policy_version"] != policy.policy_version
            or action["key_epoch"] != policy.key_epoch
            or action["audience"] != policy.audience
            or action["tool_id"] != policy.tool_id
            or action["tenant_id"] != tenant_id
            or action["task_id"] != task_id
            or action["idempotency_key"] != idempotency_key
            or type(expected_amount_fen) is not int
            or action["amount_fen"] != expected_amount_fen
            or action["canonical_params_sha256"] != digest
            or action["request_id"] != params.request_id
            or action["quote_id"] != params.quote_id
            or action["quote_version"] != params.quote_version
            or action["delivery_id"] != params.delivery_id
            or action["items"] != [{"sku": i.sku, "quantity": i.quantity} for i in params.items]
            or quote is None
            or quote.total_fen != expected_amount_fen
            or quote.quote_id != action["quote_id"]
            or quote.quote_version != action["quote_version"]
            or quote.currency != action["currency"]
            or [(i.sku, i.quantity) for i in quote.items]
            != [(i.sku, i.quantity) for i in params.items]
        ):
            raise ValueError("effect intent mismatch")
        return action
    except Exception:
        raise ExecutionError(
            ExecutionErrorCode.DOWNSTREAM_UNAUTHORIZED,
            "COSM2 effect approval missing, invalid or mismatched",
        ) from None
