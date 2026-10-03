"""Project a complete, signed AS chain from trusted persistent grant snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass

import psycopg

from agent_guard.authorization.claims import validate_access_claims, validate_child
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.contracts.execution import GrantConstraints, TrustedPermissionSnapshot
from agent_guard.crypto.sm import sm3_b64url, verify_compact_jws
from agent_guard.identity.resolver import RegisteredIdentity
from agent_guard.ledger import store


class PermissionSnapshotError(ValueError):
    """Missing or inconsistent trusted signed ancestry; never a partial chain."""


@dataclass(frozen=True)
class PermissionSource:
    snapshot: TrustedPermissionSnapshot
    chain_json: bytes
    digest: str

    def material(self) -> bytes:
        def arrays(value):
            if isinstance(value, (list, tuple)):
                return [arrays(x) for x in value]
            if type(value) is dict:
                return {k: arrays(v) for k, v in value.items()}
            return value

        return canonical_json_bytes(
            {
                "chain": self.chain_json.decode("utf-8"),
                "snapshot": arrays(asdict(self.snapshot)),
                "digest": self.digest,
            }
        )


def _chain_rows(conn, grant_id):
    path = store.load_path(conn, grant_id)
    if not 1 <= len(path) <= 3:
        raise PermissionSnapshotError("invalid grant path")
    records = []
    for grant in path:
        row = conn.execute(
            "SELECT token_jws,token_sm3,scope,constraints_json,actor_json,"
            "holder_spki_sm3,expires_at FROM ag_grant_tokens WHERE grant_id=%s",
            (grant.grant_id,),
        ).fetchone()
        if row is None:
            raise PermissionSnapshotError("missing signed ancestor")
        records.append((grant, row))
    return records


def _binding(records):
    return canonical_json_bytes(
        [
            {
                "grant_id": g.grant_id,
                "parent_id": g.parent_grant_id,
                "root_id": g.root_grant_id,
                "tenant_id": g.tenant_id,
                "task_id": g.task_id,
                "subject": g.subject,
                "client_id": g.holder_client_id,
                "kid": g.holder_kid,
                "depth": g.depth,
                "nbf": g.not_before.isoformat(),
                "exp": g.expires_at.isoformat(),
                "amount": g.amount_limit,
                "calls": g.call_limit,
                "token": r[0],
                "token_sm3": r[1],
                "scope": r[2],
                "constraints": bytes(r[3]).decode("utf-8"),
                "actor": bytes(r[4]).decode("utf-8"),
                "spki": r[5],
                "saved_exp": r[6].isoformat(),
            }
            for g, r in records
        ]
    )


class PermissionSnapshotProvider:
    """Trusted initialization supplies AS keys and historical (tenant,client,kid) registrations.

    History is explicit and keyed by kid. Never substitute the current DID key
    for a historical ancestor. Current active keys are checked by final accept.
    """

    def __init__(
        self,
        dsn: str,
        *,
        issuer: str,
        as_keys: Mapping,
        registrations: Mapping[tuple[str, str, str], RegisteredIdentity],
    ):
        if not issuer.startswith("https://") or not as_keys or not registrations:
            raise ValueError("fixed AS trust and complete historical registry required")
        for key, registration in registrations.items():
            if type(registration) is not RegisteredIdentity or key != (
                registration.tenant_id,
                registration.client_id,
                registration.kid,
            ):
                raise ValueError("invalid historical registration")
        self._dsn = dsn
        self._issuer = issuer
        self._as_keys = dict(as_keys)
        self._registrations = dict(registrations)

    def load(self, token: str, *, grant_id: str, now: int) -> PermissionSource:
        with psycopg.connect(self._dsn, connect_timeout=5) as conn:
            conn.execute("SET LOCAL statement_timeout='15s'")
            conn.execute("SET LOCAL lock_timeout='10s'")
            records = _chain_rows(conn, grant_id)
        previous = None
        constraints = []
        for position, (g, r) in enumerate(records):
            signed, digest, scope, raw_constraints, actor, spki, expires = r
            c = validate_access_claims(
                verify_compact_jws(signed, expected_type="ag-at+jwt", trusted_keys=self._as_keys),
                issuer=self._issuer,
                now=now,
            )
            raw = c.raw
            registration = self._registrations.get((g.tenant_id, g.holder_client_id, g.holder_kid))
            if registration is None or (
                digest != sm3_b64url(signed.encode("ascii"))
                or g.depth != position
                or g.root_grant_id != records[0][0].grant_id
                or g.parent_grant_id != (records[position - 1][0].grant_id if position else None)
                or raw["ag_grant_id"] != g.grant_id
                or raw["ag_parent_id"] != g.parent_grant_id
                or raw["ag_root_id"] != g.root_grant_id
                or raw["ag_tenant_id"] != g.tenant_id
                or raw["ag_task_id"] != g.task_id
                or raw["sub"] != g.subject
                or raw["client_id"] != g.holder_client_id
                or raw["ag_cnf"]["kid"] != g.holder_kid
                or raw["ag_cnf"]["spki_sm3"] != spki
                or registration.spki_sm3 != spki
                or c.actors[0] != registration.did
                or raw["ag_limits"]["amount_fen"] != g.amount_limit
                or raw["ag_limits"]["calls"] != g.call_limit
                or raw["scope"] != scope
                or canonical_json_bytes(raw["ag_constraints"]) != bytes(raw_constraints)
                or canonical_json_bytes(raw["act"]) != bytes(actor)
                or raw["nbf"] != int(g.not_before.timestamp())
                or raw["exp"] != int(g.expires_at.timestamp())
                or expires != g.expires_at
            ):
                raise PermissionSnapshotError("signed ancestor does not match trusted state")
            if previous is not None:
                validate_child(previous, c)
            previous = c
            constraints.append(
                GrantConstraints(
                    **{k: v if k == "max_quantity" else tuple(v) for k, v in c.constraints.items()}
                )
            )
        leaf = records[-1][0]
        if records[-1][1][0] != token:
            raise PermissionSnapshotError("leaf token is not the persisted signed snapshot")
        snapshot = TrustedPermissionSnapshot(
            grant_id=leaf.grant_id,
            root_id=leaf.root_grant_id,
            tenant_id=leaf.tenant_id,
            task_id=leaf.task_id,
            subject=leaf.subject,
            scope=tuple(sorted(previous.scopes)),
            chain=tuple(constraints),
            chain_grant_ids=tuple(g.grant_id for g, _ in records),
        )
        binding = _binding(records)
        return PermissionSource(snapshot, binding, sm3_b64url(binding))

    @staticmethod
    def revalidate(conn, source: PermissionSource) -> None:
        raw = _binding(_chain_rows(conn, source.snapshot.grant_id))
        if raw != source.chain_json or sm3_b64url(raw) != source.digest:
            raise PermissionSnapshotError("permission source changed before accept")
