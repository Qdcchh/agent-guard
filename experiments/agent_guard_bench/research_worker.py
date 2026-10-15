"""Internal accepted-intent worker; separate genuine downstream transaction."""

import time
import uuid

from agent_guard.contracts.execution import ToolId
from agent_guard.tools.catalog import snapshot_from_bytes

from .research_contracts import ResearchError


class ResearchWorker:
    def __init__(self, *, service, downstream, service_secret):
        from agent_guard.tools.downstream import MockDownstream

        if type(downstream) is not MockDownstream or not service_secret:
            raise ValueError("actual downstream and service credential required")
        self.service, self.downstream, self.secret = service, downstream, service_secret

    def _execute(self, row):
        return self.downstream.execute(
            service_secret=self.secret,
            operation_id=row["operation_id"],
            tool_id=ToolId(row["tool_id"]),
            canonical_params=bytes(row["canonical_params"]),
            quote=snapshot_from_bytes(
                bytes(row["quote_snapshot"]) if row["quote_snapshot"] else None
            ),
            expected_amount_fen=row["amount_fen"],
        )

    def run(self, operation_id, *, owner=None, reconcile_only=False, pause=None):
        lease = self.service.claim(operation_id, owner or uuid.uuid4().hex)
        row = self.service.load_operation(operation_id)
        outcome = None
        try:
            if reconcile_only or lease.previous_status in ("EXECUTING", "UNKNOWN"):
                outcome = self.downstream.query(
                    service_secret=self.secret, operation_id=operation_id
                )
                if outcome is None and not reconcile_only:
                    outcome = self._execute(row)
            else:
                outcome = self._execute(row)
        except Exception as exc:
            # Authentication errors remain hard failures; other downstream
            # anomalies retain UNKNOWN and reservation, never terminal release.
            if getattr(getattr(exc, "code", None), "value", None) == "DOWNSTREAM_UNAUTHORIZED":
                raise
        if pause is not None:
            pause(lease, outcome)
        return self.service.finalize(lease, outcome)

    def reconcile(self, operation_id, *, owner=None, pause=None):
        return self.run(operation_id, owner=owner, reconcile_only=True, pause=pause)

    def serve(self, *, deadline, stop, poll_seconds=0.1):
        if not callable(stop) or not 0 < poll_seconds <= 1:
            raise ValueError("bounded persistent worker required")
        while time.monotonic() < deadline and not stop():
            with self.service.store.transaction(readonly=True) as conn:
                rows = conn.execute(
                    "SELECT o.operation_id FROM r34.operations o LEFT JOIN r34.leases l "
                    "USING(operation_id) WHERE o.mode=%s AND o.status IN "
                    "('RESERVED','EXECUTING','UNKNOWN') AND (l.expires_at IS NULL OR "
                    "l.expires_at<=clock_timestamp()) ORDER BY "
                    "o.accepted_at,o.operation_id LIMIT 32",
                    (self.service.store.mode,),
                ).fetchall()
            for row in rows:
                try:
                    self.run(row["operation_id"])
                except ResearchError as exc:
                    if exc.code not in (
                        "LEASE_BUSY",
                        "ILLEGAL_TRANSITION",
                        "STALE_FENCE",
                    ):
                        raise
            if not rows:
                time.sleep(poll_seconds)
