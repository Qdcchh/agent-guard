"""Off-lock verification of the detached threshold approval.

Verification never touches the database and never trusts anything carried by
the request except the opaque header bytes. The group public key, policy
version, key epoch and validity bound come only from trusted operator
configuration. The final expiry decision is repeated under the acceptance
transaction using the database clock (see ``binding.py``).
"""

from __future__ import annotations

import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from agent_guard.contracts.execution import ExecutionError, ToolId
from agent_guard.cosign.encoding import signature_rs_to_der
from agent_guard.crypto.sm import (
    InvalidSm2Signature,
    load_sm2_public_key,
    sm3_b64url,
    verify_sm2_message,
)
from agent_guard.threshold.codec import (
    action_message,
    compute_params_digest,
    cosm2_message,
    decode_header,
    parse_envelope,
)
from agent_guard.threshold.contracts import (
    COSM2_PROFILE,
    PROFILE,
    COSM2ApprovalExpired,
    ThresholdApprovalError,
    ThresholdApprovalExpectation,
    ThresholdApprovalPolicy,
    VerifiedThresholdApproval,
)
from agent_guard.tools.params import parse_tool_params


class ThresholdApprovalVerifier:
    """Strict detector for the trusted approval policy; no request-selected trust."""

    def __init__(self, *, policy: ThresholdApprovalPolicy) -> None:
        if type(policy) is not ThresholdApprovalPolicy:
            raise ValueError("validated trusted threshold policy required")
        self._policy = policy

    @property
    def policy(self) -> ThresholdApprovalPolicy:
        return self._policy

    def verify(
        self,
        header: bytes,
        *,
        expected: ThresholdApprovalExpectation,
        now: int,
    ) -> VerifiedThresholdApproval:
        if type(expected) is not ThresholdApprovalExpectation:
            raise ValueError("trusted expectation required")
        if type(now) is not int or isinstance(now, bool) or now < 0:
            raise ThresholdApprovalError("invalid verification time", code="INVALID_APPROVAL")

        envelope = decode_header(header)
        policy = self._policy
        is_cosm2 = policy.scheme == "sm2-2p"
        action, signature = parse_envelope(envelope, profile=COSM2_PROFILE if is_cosm2 else PROFILE)

        if (
            action["audience"] != policy.audience
            or action["policy_version"] != policy.policy_version
            or action["key_epoch"] != policy.key_epoch
        ):
            raise ThresholdApprovalError(
                "approval trust facts do not match the configured policy",
                code="APPROVAL_MISMATCH",
            )

        self._check_expectation(action, expected)

        expires_at = action["expires_at"]
        if now >= expires_at:
            if is_cosm2:
                raise COSM2ApprovalExpired()
            raise ThresholdApprovalError("threshold approval expired", code="EXPIRED")
        if expires_at - now > policy.max_lifetime_seconds:
            raise ThresholdApprovalError(
                "threshold approval exceeds the trusted validity bound",
                code="INVALID_APPROVAL",
            )

        message = cosm2_message(action) if is_cosm2 else action_message(action)
        try:
            if is_cosm2:
                verify_sm2_message(
                    load_sm2_public_key(policy.group_public_key),
                    message,
                    signature_rs_to_der(signature),
                )
            else:
                Ed25519PublicKey.from_public_bytes(policy.group_public_key).verify(
                    signature, message
                )
        except (InvalidSignature, InvalidSm2Signature) as exc:
            raise ThresholdApprovalError(
                "threshold group signature is invalid", code="INVALID_SIGNATURE"
            ) from exc

        return VerifiedThresholdApproval(
            action_id=action["action_id"],
            tenant_id=action["tenant_id"],
            task_id=action["task_id"],
            root_grant_id=action["root_grant_id"],
            grant_id=action["grant_id"],
            path_grant_ids=tuple(action["path_grant_ids"]),
            holder_client_id=action["holder_client_id"],
            holder_kid=action["holder_kid"],
            audience=action["audience"],
            tool_id=action["tool_id"],
            tool_version=action["tool_version"],
            currency=action["currency"],
            policy_version=action["policy_version"],
            key_epoch=action["key_epoch"],
            idempotency_key=action["idempotency_key"],
            request_id=action["request_id"],
            quote_id=action["quote_id"],
            quote_version=action["quote_version"],
            items=tuple((item["sku"], item["quantity"]) for item in action["items"]),
            delivery_id=action["delivery_id"],
            amount_fen=action["amount_fen"],
            canonical_params_sha256=action["canonical_params_sha256"],
            expires_at=expires_at,
            message_sha256=hashlib.sha256(message).hexdigest(),
            envelope_bytes=envelope,
            envelope_sm3=sm3_b64url(envelope),
            signature=signature,
            payment_digest=action.get("payment_digest"),
        )

    @staticmethod
    def _check_expectation(action: dict, expected: ThresholdApprovalExpectation) -> None:
        if expected.amount_fen is not None:
            if type(expected.amount_fen) is not int or expected.amount_fen < 0:
                raise ValueError("trusted integer approval amount required")
            if action["amount_fen"] != expected.amount_fen:
                raise ThresholdApprovalError("approval amount mismatch", code="APPROVAL_MISMATCH")
        if (
            action["tenant_id"] != expected.tenant_id
            or action["task_id"] != expected.task_id
            or action["root_grant_id"] != expected.root_grant_id
            or action["grant_id"] != expected.grant_id
            or action["holder_client_id"] != expected.holder_client_id
            or action["holder_kid"] != expected.holder_kid
            or action["tool_id"] != expected.tool_id
            or action["tool_version"] != expected.tool_version
            or action["idempotency_key"] != expected.idempotency_key
        ):
            raise ThresholdApprovalError(
                "approval does not match the verified invocation",
                code="APPROVAL_MISMATCH",
            )
        if expected.path_grant_ids is not None and tuple(action["path_grant_ids"]) != tuple(
            expected.path_grant_ids
        ):
            raise ThresholdApprovalError(
                "approval does not match the verified authorization path",
                code="APPROVAL_MISMATCH",
            )
        try:
            params = parse_tool_params(ToolId.ORDER_CREATE, expected.canonical_params)
        except (ExecutionError, ValueError, TypeError, RecursionError) as exc:
            raise ThresholdApprovalError(
                "verified invocation parameters are unusable", code="INVALID_APPROVAL"
            ) from exc
        digest = compute_params_digest(
            request_id=params.request_id,
            quote_id=params.quote_id,
            quote_version=params.quote_version,
            items=[(item.sku, item.quantity) for item in params.items],
            delivery_id=params.delivery_id,
        )
        if digest != action["canonical_params_sha256"]:
            raise ThresholdApprovalError(
                "approval does not match the verified order parameters",
                code="APPROVAL_MISMATCH",
            )
        if (
            action["request_id"] != params.request_id
            or action["quote_id"] != params.quote_id
            or action["quote_version"] != params.quote_version
            or action["delivery_id"] != params.delivery_id
            or tuple((item["sku"], item["quantity"]) for item in action["items"])
            != tuple((item.sku, item.quantity) for item in params.items)
        ):
            raise ThresholdApprovalError(
                "approval order fields do not match the verified parameters",
                code="APPROVAL_MISMATCH",
            )
