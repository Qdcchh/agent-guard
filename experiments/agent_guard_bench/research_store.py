"""Owned research storage, with independent authority SHARE and budget row locks."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.ledger import store as production_read

from .research_contracts import (
    BearerContext,
    ResearchError,
    ResearchPoPContext,
    context_fields,
)


@dataclass(frozen=True)
class Lease:
    operation_id: str
    owner: str
    version: int
    expires_at: datetime
    previous_status: str


class ResearchStore:
    def __init__(self, dsn, *, mode, owner):
        if mode not in ("noAtomic", "Bearer", "staticACL") or type(owner) is not str or not owner:
            raise ValueError("explicit research mode and owner required")
        self.dsn, self.mode, self.owner = dsn, mode, owner

    @contextmanager
    def transaction(self, *, readonly=False):
        with psycopg.connect(self.dsn, connect_timeout=5, row_factory=dict_row) as conn:
            with conn.transaction():
                conn.execute(
                    "SET TRANSACTION ISOLATION LEVEL "
                    + ("REPEATABLE READ READ ONLY" if readonly else "READ COMMITTED")
                )
                conn.execute("SET LOCAL lock_timeout='3s'")
                conn.execute("SET LOCAL statement_timeout='30s'")
                yield conn

    def provision(self, schema=Path(__file__).parents[1] / "research-schema.sql"):
        with self.transaction() as conn:
            conn.execute(Path(schema).read_text())

    @staticmethod
    def authority_path(conn, context):
        f = context_fields(context)
        # Public path discovery parses tuples; obtain it on the same connection
        # via a tuple cursor without modifying connection row_factory.
        with conn.cursor(row_factory=psycopg.rows.tuple_row) as cursor:
            cursor.execute(
                "SELECT " + production_read.GRANT_COLUMNS + " FROM ag_grants WHERE grant_id=%s",
                (f["grant"],),
            )
            row = cursor.fetchone()
        if row is None:
            raise ResearchError("INVALID_CONTEXT")
        path = [
            dict(
                zip(
                    production_read.GRANT_COLUMNS.replace(" ", "").split(","),
                    row,
                    strict=True,
                )
            )
        ]
        seen = {f["grant"]}
        while path[0]["parent_grant_id"] is not None:
            parent = path[0]["parent_grant_id"]
            if parent in seen or len(path) >= 3:
                raise ResearchError("INVALID_CONTEXT")
            seen.add(parent)
            row = conn.execute(
                "SELECT " + production_read.GRANT_COLUMNS + " FROM ag_grants WHERE grant_id=%s",
                (parent,),
            ).fetchone()
            if row is None:
                raise ResearchError("INVALID_CONTEXT")
            path.insert(0, row)
        keys = sorted({(g["tenant_id"], g["holder_client_id"], g["holder_kid"]) for g in path})
        principals = []
        for key in keys:
            principal = conn.execute(
                "SELECT * FROM ag_principals WHERE tenant_id=%s AND client_id=%s AND "
                "kid=%s FOR SHARE",
                key,
            ).fetchone()
            if principal is None or not principal["active"]:
                raise ResearchError("HOLDER_MISMATCH")
            principals.append(principal)
        task = conn.execute(
            "SELECT * FROM ag_tasks WHERE tenant_id=%s AND task_id=%s FOR SHARE",
            (f["tenant"], f["task"]),
        ).fetchone()
        if task is None or task["root_grant_id"] != f["root"]:
            raise ResearchError("INVALID_CONTEXT")
        locked = []
        for grant in path:
            locked.append(
                conn.execute(
                    "SELECT "
                    + production_read.GRANT_COLUMNS
                    + " FROM ag_grants WHERE grant_id=%s FOR SHARE",
                    (grant["grant_id"],),
                ).fetchone()
            )
        if any(g is None for g in locked):
            raise ResearchError("INVALID_CONTEXT")
        ids = tuple(g["grant_id"] for g in locked)
        if (
            ids != f["source"].chain_grant_ids
            or locked[0]["grant_id"] != f["root"]
            or locked[-1]["grant_id"] != f["grant"]
        ):
            raise ResearchError("INVALID_CONTEXT")
        if (locked[-1]["holder_client_id"], locked[-1]["holder_kid"]) != (
            f["client"],
            f["kid"],
        ):
            raise ResearchError("HOLDER_MISMATCH")
        for i, g in enumerate(locked):
            if (
                g["tenant_id"],
                g["task_id"],
                g["subject"],
                g["root_grant_id"],
                g["depth"],
                g["parent_grant_id"],
            ) != (
                f["tenant"],
                f["task"],
                f["subject"],
                f["root"],
                i,
                ids[i - 1] if i else None,
            ):
                raise ResearchError("INVALID_CONTEXT")
            if g["revoked"] or g["revoked_at"] is not None:
                raise ResearchError("REVOKED")
        if type(context) in (ResearchPoPContext, BearerContext):
            with conn.cursor(row_factory=psycopg.rows.tuple_row) as cursor:
                # PermissionSnapshotProvider only requires execute/fetch cursor interface.
                PermissionSnapshotProvider.revalidate(cursor, context.source)
        return tuple(locked)

    @staticmethod
    def final_clock(conn, context, path):
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
        now = conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"].timestamp()
        f = context_fields(context)
        if now >= f["exp"] or any(
            not g["not_before"].timestamp() <= now < g["expires_at"].timestamp() for g in path
        ):
            raise ResearchError("EXPIRED")
        if type(context) is ResearchPoPContext:
            v = context.verified
            if (
                not v.proof_iat <= now + 5
                or now >= v.proof_exp
                or not v.proof_iat < v.proof_exp <= v.proof_iat + 60
            ):
                raise ResearchError("STALE_REQUEST")
        # Caller must perform no further SQL, signing or network before commit.

    def operation(self, conn, operation_id, *, lock=False):
        return conn.execute(
            "SELECT * FROM r34.operations WHERE operation_id=%s AND mode=%s"
            + (" FOR UPDATE" if lock else ""),
            (operation_id, self.mode),
        ).fetchone()

    def candidate(self, conn, context):
        f = context_fields(context)
        intent = context.intent
        return conn.execute(
            "SELECT * FROM r34.operations WHERE mode=%s AND tenant_id=%s AND task_id=%s "
            "AND tool_id=%s AND business_key=%s",
            (self.mode, f["tenant"], f["task"], intent.tool_id.value, intent.key),
        ).fetchone()

    def business_mutex(self, conn, context):
        f = context_fields(context)
        i = context.intent
        key = canonical_json_bytes(
            [self.mode, f["tenant"], f["task"], i.tool_id.value, i.key]
        ).decode()
        # Only exact business key; no shared task/root mutex.
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (key,))

    @staticmethod
    def record_proof(conn, context, operation_id=None):
        if type(context) is not ResearchPoPContext:
            return
        v = context.verified
        try:
            conn.execute(
                "INSERT INTO "
                "r34.proofs(kid,purpose,endpoint,jti,digest,evidence_ref,operation_id) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    v.holder_kid,
                    v.purpose,
                    v.endpoint,
                    v.proof_jti,
                    v.proof_digest,
                    v.evidence_ref,
                    operation_id,
                ),
            )
        except psycopg.errors.UniqueViolation as exc:
            raise ResearchError("REPLAY") from exc

    @staticmethod
    def link_proof(conn, context, operation_id):
        if type(context) is ResearchPoPContext:
            v = context.verified
            conn.execute(
                "UPDATE r34.proofs SET operation_id=%s WHERE kid=%s AND purpose=%s AND "
                "endpoint=%s AND jti=%s",
                (operation_id, v.holder_kid, v.purpose, v.endpoint, v.proof_jti),
            )

    @staticmethod
    def event(conn, operation, phase):
        amount, calls = operation["amount_fen"], operation["calls"]
        delta = (
            (amount, 0, calls, 0)
            if phase == "RESERVE"
            else (
                -amount,
                amount if phase == "SETTLE" else 0,
                -calls,
                calls if phase == "SETTLE" else 0,
            )
        )
        event = conn.execute(
            "INSERT INTO r34.events(operation_id,phase,seq) VALUES(%s,%s,%s) RETURNING event_id",
            (operation["operation_id"], phase, 0 if phase == "RESERVE" else 1),
        ).fetchone()["event_id"]
        for position, grant in enumerate(operation["path_ids"]):
            conn.execute(
                "INSERT INTO r34.nodes VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (event, position, grant, *delta),
            )

    def claim(self, operation_id, owner, *, ttl=30):
        if type(owner) is not str or not owner or type(ttl) is not int or ttl != 30:
            raise ResearchError("INVALID_LEASE")
        with self.transaction() as conn:
            operation = self.operation(conn, operation_id, lock=True)
            if operation is None or operation["status"] in ("SUCCEEDED", "FAILED"):
                raise ResearchError("ILLEGAL_TRANSITION")
            old = conn.execute(
                "SELECT * FROM r34.leases WHERE operation_id=%s FOR UPDATE",
                (operation_id,),
            ).fetchone()
            now = conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
            if old and old["expires_at"] > now:
                raise ResearchError("LEASE_BUSY")
            version = old["version"] + 1 if old else 1
            expires = conn.execute(
                "INSERT INTO r34.leases VALUES(%s,%s,%s,clock_timestamp()+interval '30 "
                "seconds') ON CONFLICT(operation_id) DO UPDATE SET "
                "owner=excluded.owner,version=excluded.version,expires_at=excluded.expi"
                "res_at RETURNING expires_at",
                (operation_id, owner, version),
            ).fetchone()["expires_at"]
            previous = operation["status"]
            if previous == "RESERVED":
                conn.execute(
                    "UPDATE r34.operations SET status='EXECUTING' WHERE operation_id=%s",
                    (operation_id,),
                )
            return Lease(operation_id, owner, version, expires, previous)
