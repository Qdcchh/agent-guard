"""Independent preapproved policy + RR READ ONLY facts, never response authorization."""

from dataclasses import dataclass

from .research_contracts import ResearchError


@dataclass(frozen=True)
class OraclePolicy:
    tenant_id: str
    task_id: str
    root_id: str
    path_ids: tuple[str, ...]
    amount_limits: tuple[int, ...]
    call_limits: tuple[int, ...]
    branches: tuple["OraclePolicy", ...] = ()

    def __post_init__(self):
        if (
            not 1 <= len(self.path_ids) <= 3
            or len(set(self.path_ids)) != len(self.path_ids)
            or self.path_ids[0] != self.root_id
            or len(self.amount_limits) != len(self.path_ids)
            or len(self.call_limits) != len(self.path_ids)
            or any(
                type(v) is not int or not 0 <= v <= 2**53 - 1
                for v in self.amount_limits + self.call_limits
            )
        ):
            raise ValueError("strict independently preapproved policy required")
        if type(self.branches) is not tuple or any(
            type(branch) is not OraclePolicy
            or branch.branches
            or (branch.tenant_id, branch.task_id, branch.root_id)
            != (self.tenant_id, self.task_id, self.root_id)
            for branch in self.branches
        ):
            raise ValueError("same-task independently approved sibling paths required")
        limits = {}
        for branch in (self, *self.branches):
            for grant, amount, calls in zip(
                branch.path_ids, branch.amount_limits, branch.call_limits, strict=True
            ):
                if grant in limits and limits[grant] != (amount, calls):
                    raise ValueError("shared ancestor policy limits must agree")
                limits[grant] = (amount, calls)

    @property
    def all_grant_ids(self):
        return tuple(dict.fromkeys(g for b in (self, *self.branches) for g in b.path_ids))


def snapshot_oracle(store, policy: OraclePolicy):
    if type(policy) is not OraclePolicy:
        raise ValueError("preapproved oracle policy required")
    with store.transaction(readonly=True) as conn:
        authority = conn.execute(
            "SELECT "
            "grant_id,amount_reserved,amount_settled,calls_reserved,calls_settled,r"
            "evoked,expires_at FROM public.ag_grants WHERE grant_id=ANY(%s) ORDER BY "
            "depth,grant_id",
            (list(policy.all_grant_ids),),
        ).fetchall()
        counters = conn.execute(
            "SELECT * FROM r34.counters WHERE grant_id=ANY(%s) ORDER BY grant_id",
            (list(policy.all_grant_ids),),
        ).fetchall()
        operations = conn.execute(
            "SELECT * FROM r34.operations WHERE mode=%s AND tenant_id=%s AND task_id=%s "
            "ORDER BY accepted_at,operation_id",
            (store.mode, policy.tenant_id, policy.task_id),
        ).fetchall()
        ids = [o["operation_id"] for o in operations]
        tables = {}
        for table in ("events", "proofs", "leases", "outbox"):
            tables[table] = conn.execute(
                "SELECT * FROM r34." + table + " WHERE operation_id=ANY(%s)", (ids,)
            ).fetchall()
        tables["nodes"] = conn.execute(
            "SELECT n.* FROM r34.nodes n JOIN r34.events e USING(event_id) WHERE "
            "e.operation_id=ANY(%s) ORDER BY event_id,position",
            (ids,),
        ).fetchall()
        tables["originals"] = conn.execute(
            "SELECT r.* FROM r34.originals r JOIN r34.operations o ON "
            "o.first_ref=r.reference WHERE o.operation_id=ANY(%s)",
            (ids,),
        ).fetchall()
        now = conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
    if {g["grant_id"] for g in authority} != set(policy.all_grant_ids):
        raise ResearchError("INCOMPLETE_ORACLE")
    return {
        "mode": store.mode,
        "policy": policy,
        "observed_at": now,
        "authority": authority,
        "counters": counters,
        "operations": operations,
        **tables,
        "independent_audit": "NOT_APPLICABLE",
    }


def downstream_oracle(dsn, operation_ids):
    """Independent downstream instance/TX; not falsely one cross-domain snapshot."""
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            conn.execute("SET LOCAL statement_timeout='30s'")
            return {
                table: conn.execute(
                    "SELECT * FROM " + table + " WHERE operation_id=ANY(%s)",
                    (list(operation_ids),),
                ).fetchall()
                for table in ("ds_operations", "ds_orders", "ds_notifications")
            }
