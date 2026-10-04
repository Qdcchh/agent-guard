"""Minimal in-process B→A acceptance adapter; no HTTP gateway or query execution."""

from agent_guard.authorization.evidence_store import EvidenceStore
from agent_guard.contracts.verification import VerifiedInvocationBundle
from agent_guard.execution.service import ExecutionService


class VerifiedExecution:
    def __init__(self, service: ExecutionService, *, evidence_store: EvidenceStore):
        if type(evidence_store) is not EvidenceStore or not isinstance(service, ExecutionService):
            raise ValueError("real execution and evidence services are required")
        self._service = service
        self._evidence = evidence_store

    def accept(self, bundle: VerifiedInvocationBundle):
        if type(bundle) is not VerifiedInvocationBundle:
            raise ValueError("a signed-source invocation bundle is required")
        return self._service.accept_invocation(
            bundle.invocation, bundle.permissions, binding=self._evidence.binding(bundle)
        )
