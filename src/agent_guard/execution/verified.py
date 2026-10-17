"""Signed B→A acceptance adapter with same-transaction publication responses."""

from agent_guard.authorization.evidence_store import EvidenceError, EvidenceStore
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.contracts.verification import VerifiedInvocationBundle
from agent_guard.execution import store
from agent_guard.execution.original_material import validate_original_tx
from agent_guard.execution.receipt_projection import project_receipt
from agent_guard.execution.receipt_publication import ReceiptVerifier
from agent_guard.execution.service import ExecutionService
from agent_guard.threshold.binding import approval_binding
from agent_guard.threshold.contracts import VerifiedThresholdApproval


def _with_approval(binding, approval):
    """Compose the verified threshold approval into the original binding."""
    if approval is None:
        return binding
    if type(approval) is not VerifiedThresholdApproval:
        raise ValueError("verified threshold approval required")
    callback, final_check = approval_binding(approval)
    return binding.compose(callback, final_check=final_check)


class VerifiedExecution:
    def __init__(self, service: ExecutionService, *, evidence_store: EvidenceStore):
        if type(evidence_store) is not EvidenceStore or not isinstance(service, ExecutionService):
            raise ValueError("real execution and evidence services are required")
        self._service = service
        self._evidence = evidence_store

    def accept(
        self,
        bundle: VerifiedInvocationBundle,
        *,
        approval: VerifiedThresholdApproval | None = None,
        extra_binding=None,
        extra_final_check=None,
    ):
        if type(bundle) is not VerifiedInvocationBundle:
            raise ValueError("a signed-source invocation bundle is required")
        binding = _with_approval(self._evidence.binding(bundle), approval)
        if extra_binding is not None:
            binding = binding.compose(extra_binding, final_check=extra_final_check)
        return self._service.accept_invocation(
            bundle.invocation,
            bundle.permissions,
            binding=binding,
        )

    def accept_response(
        self,
        bundle: VerifiedInvocationBundle,
        *,
        receipt_verifier,
        approval: VerifiedThresholdApproval | None = None,
        extra_binding=None,
        extra_final_check=None,
    ) -> dict:
        """Capture publication before the existing final proof/DB-clock gate."""
        if type(bundle) is not VerifiedInvocationBundle:
            raise ValueError("a signed-source invocation bundle is required")
        if receipt_verifier is not None and type(receipt_verifier) is not ReceiptVerifier:
            raise ValueError("real receipt verifier required")
        original_binding = _with_approval(self._evidence.binding(bundle), approval)
        if extra_binding is not None:
            original_binding = original_binding.compose(
                extra_binding, final_check=extra_final_check
            )
        response = None

        def binding(conn, operation, disposition):
            nonlocal response
            response = None
            if receipt_verifier is not None:
                publication = receipt_verifier.read_tx(conn, operation.operation_id)
                receipt_status = publication.receipt_status
            else:
                out = store.fetch_outbox(conn, operation.operation_id)
                if operation.status in ("SUCCEEDED", "FAILED"):
                    validate_original_tx(conn, operation, bundle.source)
                    project_receipt(conn, operation.operation_id)
                    if (
                        out is None
                        or out["receipt_status"] != "PENDING"
                        or out["receipt_jws"] is not None
                        or out["signed_at"] is not None
                    ):
                        raise EvidenceError("unsupported receipt publication state")
                elif out is not None:
                    raise EvidenceError("nonterminal operation has outbox")
                receipt_status = "PENDING"
            response = {
                "operation_id": operation.operation_id,
                "status": operation.status,
                "receipt_status": receipt_status,
            }
            canonical_json_bytes(response)

        accepted = self._service.accept_invocation(
            bundle.invocation,
            bundle.permissions,
            binding=original_binding.compose(binding)._with_response(lambda: response),
        )
        if response is None or response["operation_id"] != accepted.operation_id:
            raise RuntimeError("acceptance did not capture its transaction response")
        return response
