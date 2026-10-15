"""Independent export authentication and trusted task scope selection."""

from dataclasses import dataclass

from agent_guard.audit.contracts import JournalScope
from agent_guard.contracts.encoding import load_strict_json
from agent_guard.evidence.export import materialize_task_export
from agent_guard.evidence.task_bundle import CheckpointHistoryDescriptor
from agent_guard.gateway.evidence_auth import authenticate_export
from agent_guard.server.config import ConfigError


@dataclass(frozen=True, slots=True)
class ExportTaskInputs:
    scope: JournalScope
    pin_mode: str
    checkpoint_jws: str | None
    observed_at: int | None
    history: CheckpointHistoryDescriptor

    @property
    def external_pin(self):
        from dataclasses import asdict

        return {
            "mode": self.pin_mode,
            "checkpoint_jws": self.checkpoint_jws,
            "observed_at": self.observed_at,
            "scope": asdict(self.scope),
        }


class EvidenceExportEndpoint:
    def __init__(self, connection_factory, *, credentials, task_inputs, spool_parent):
        if type(credentials) is not tuple or type(task_inputs) is not tuple or not task_inputs:
            raise ConfigError("immutable explicit operator export inputs required")
        self._inputs = {}
        for item in task_inputs:
            if type(item) is not ExportTaskInputs or item.history.scope != item.scope:
                raise ConfigError("trusted export scope and history required")
            key = (item.scope.tenant_id, item.scope.task_id)
            if key in self._inputs:
                raise ConfigError("duplicate trusted export task")
            self._inputs[key] = item
        self._credentials = credentials
        self._connection_factory = connection_factory
        self._spool_parent = spool_parent

    @staticmethod
    def schema(raw):
        value = load_strict_json(raw)
        if type(value) is not dict or set(value) != {"task_id"}:
            raise ConfigError("exact export task request required")
        # This same strict identifier boundary is used by the frozen authenticator.
        from agent_guard.gateway.evidence_auth import _id

        _id(value["task_id"])
        return value["task_id"]

    def handle(self, authorization, raw):
        task = self.schema(raw)
        key = authenticate_export(authorization, task, credentials=self._credentials)
        item = self._inputs.get(key)
        if item is None:
            raise ConfigError("export scope denied")
        return materialize_task_export(
            self._connection_factory,
            item.scope,
            item.external_pin,
            self._spool_parent,
            external_checkpoint_history=item.history,
        )
