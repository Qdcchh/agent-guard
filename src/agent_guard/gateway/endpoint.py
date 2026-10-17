"""Pure schema boundary followed by existing real verifier and acceptance."""

import time

from agent_guard.authorization.verifier import InvocationVerifier, VerificationError
from agent_guard.contracts.encoding import (
    EncodingError,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.contracts.ledger import INVOKE_ENDPOINT, QUERY_ENDPOINT
from agent_guard.execution.query import AuthorizedQuery
from agent_guard.execution.verified import VerifiedExecution
from agent_guard.gateway.errors import GatewayError
from agent_guard.threshold.contracts import (
    TOOL_ID as THRESHOLD_TOOL_ID,
)
from agent_guard.threshold.contracts import (
    ThresholdApprovalError,
    ThresholdApprovalExpectation,
)
from agent_guard.threshold.verifier import ThresholdApprovalVerifier
from agent_guard.tools.params import (
    parse_tool_id,
    parse_tool_params,
    parse_tool_version,
)
from agent_guard.x402.accept import payment_binding
from agent_guard.x402.config import X402Deployment


class GatewayEndpoint:
    def __init__(
        self,
        *,
        verifier: InvocationVerifier,
        execution: VerifiedExecution,
        queries: AuthorizedQuery,
        receipt_verifier=None,
        threshold_verifier: ThresholdApprovalVerifier | None = None,
        payment: X402Deployment | None = None,
        now=None,
    ):
        if (
            type(verifier) is not InvocationVerifier
            or type(execution) is not VerifiedExecution
            or type(queries) is not AuthorizedQuery
        ):
            raise ValueError("real gateway services required")
        if threshold_verifier is not None and type(threshold_verifier) is not (
            ThresholdApprovalVerifier
        ):
            raise ValueError("real threshold verifier required")
        if payment is not None and type(payment) is not X402Deployment:
            raise ValueError("real x402 deployment required")
        if payment is not None and threshold_verifier is None:
            raise ValueError("x402 payment requires the threshold verifier")
        if now is not None and not callable(now):
            raise ValueError("verification clock must be callable")
        self._receipt_verifier = receipt_verifier
        self._verifier = verifier
        self._execution = execution
        self._queries = queries
        self._threshold = threshold_verifier
        self._payment = payment
        self._now = now if now is not None else (lambda: int(time.time()))

    @staticmethod
    def schema(body: bytes, *, query: bool):
        try:
            value = load_strict_json(body)
            fields = (
                {"profile", "task_id", "operation_id"}
                if query
                else {
                    "profile",
                    "task_id",
                    "tool_id",
                    "tool_version",
                    "idempotency_key",
                    "params",
                }
            )
            if type(value) is not dict or set(value) != fields or value["profile"] != "GM-MVP-1":
                raise GatewayError("INVALID_SCHEMA")
            for key in ("task_id", "operation_id") if query else ("task_id", "idempotency_key"):
                if (
                    type(value[key]) is not str
                    or not value[key].isascii()
                    or not 1 <= len(value[key]) <= 128
                    or any(ord(c) < 33 or ord(c) > 126 for c in value[key])
                ):
                    raise GatewayError("INVALID_SCHEMA")
            if not query:
                tool = parse_tool_id(value["tool_id"])
                parse_tool_version(value["tool_version"])
                parse_tool_params(tool, canonical_json_bytes(value["params"]))
            return value
        except (EncodingError, UnicodeError, TypeError, RecursionError) as exc:
            raise GatewayError("INVALID_SCHEMA") from exc

    def handle(self, path: str, token: str, proof: str, body: bytes, approval=None):
        query = path == "/v1/operations/query"
        request = self.schema(body, query=query)
        if query:
            if approval is not None:
                raise GatewayError("INVALID_SCHEMA")
            bundle = self._verifier.verify_query_bundle(
                token, proof, endpoint=QUERY_ENDPOINT, body=body, now=self._now()
            )
            return 200, self._queries.query(bundle)

        # Trusted policy decides whether this request must carry an approval;
        # the request can neither enable nor disable the requirement.
        requires_approval = (
            self._threshold is not None and request["tool_id"] == self._threshold.policy.tool_id
        )
        # The trusted deployment decides whether this tool is paid; a request
        # can never opt out of the payment or the V3 digest requirement.
        requires_payment = self._payment is not None and request["tool_id"] == THRESHOLD_TOOL_ID
        if self._threshold is not None and approval is not None and not requires_approval:
            raise GatewayError("INVALID_SCHEMA")
        if requires_approval and approval is None:
            raise VerificationError("threshold approval required", code="APPROVAL_REQUIRED")
        if self._threshold is None and approval is not None:
            raise GatewayError("INVALID_SCHEMA")

        bundle = self._verifier.verify_bundle(
            token, proof, endpoint=INVOKE_ENDPOINT, body=body, now=self._now()
        )
        verified_approval = None
        if requires_approval:
            verified_approval = self._verify_approval(approval, bundle)
        extra_binding = extra_final_check = None
        if requires_payment:
            if verified_approval is None:
                raise VerificationError("threshold approval required", code="APPROVAL_REQUIRED")
            extra_binding, extra_final_check = payment_binding(self._payment, verified_approval)
        return 202, self._execution.accept_response(
            bundle,
            receipt_verifier=self._receipt_verifier,
            approval=verified_approval,
            extra_binding=extra_binding,
            extra_final_check=extra_final_check,
        )

    def _verify_approval(self, header, bundle):
        invocation = bundle.invocation
        path_ids = None
        if invocation.ancestor_ids is not None:
            path_ids = (*invocation.ancestor_ids, invocation.grant_id)
        expected = ThresholdApprovalExpectation(
            tenant_id=invocation.tenant_id,
            task_id=invocation.task_id,
            root_grant_id=invocation.root_id,
            grant_id=invocation.grant_id,
            holder_client_id=invocation.holder_client_id,
            holder_kid=invocation.holder_kid,
            tool_id=invocation.tool_id,
            tool_version=invocation.tool_version,
            idempotency_key=invocation.idempotency_key,
            canonical_params=invocation.canonical_params,
            path_grant_ids=tuple(path_ids) if path_ids is not None else None,
        )
        try:
            return self._threshold.verify(header, expected=expected, now=self._now())
        except ThresholdApprovalError as exc:
            raise VerificationError("invalid threshold approval", code=exc.code) from exc
