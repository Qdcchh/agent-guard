"""Trusted synthetic state and cost fixtures for A1 tests.

Building :class:`VerifiedInvocation` directly in tests is legitimate layered
testing; it is *not* a claim that any signature was verified. Production code
must only construct it through B's future verifier. These fixtures are test
assembly only and never ship as an external entry point.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import psycopg

from agent_guard.contracts.ledger import (
    CURRENCY,
    INVOKE_ENDPOINT,
    INVOKE_METHOD,
    PROFILE,
    PURPOSE_INVOKE,
    TOOL_VERSION,
    TrustedCost,
    VerifiedInvocation,
)
from agent_guard.ledger import provisioning as prov

DEFAULT_PARAMS = b'{"sku":"sku-001","quantity":1}'
DEFAULT_TOOL = "procurement.order.create"

_counter = itertools.count(1)
_jti_counter = itertools.count(1)


def unique(prefix: str) -> str:
    """Deterministic-but-unique id for isolated test data."""
    return f"{prefix}-{next(_counter)}"


def default_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(tz=timezone.utc)
    return now - timedelta(minutes=1), now + timedelta(hours=2)


@dataclass
class TreeFixture:
    """One synthetic root -> mid -> leaf chain with registered holder keys."""

    tenant_id: str
    task_id: str
    subject: str
    root_id: str
    mid_id: str
    leaf_id: str
    planner: tuple[str, str]
    selector: tuple[str, str]
    executor: tuple[str, str]
    not_before: datetime
    expires_at: datetime
    amount_limits: tuple[int, int, int]
    call_limits: tuple[int, int, int]
    _jti: itertools.count = field(default_factory=lambda: itertools.count(1))

    _ANCESTORS: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._ANCESTORS = {
            self.root_id: (),
            self.mid_id: (self.root_id,),
            self.leaf_id: (self.root_id, self.mid_id),
        }
        self._HOLDERS = {
            self.root_id: self.planner,
            self.mid_id: self.selector,
            self.leaf_id: self.executor,
        }

    # ------------------------------------------------------------- lookups

    def ancestors_for(self, grant_id: str) -> tuple[str, ...]:
        return self._ANCESTORS[grant_id]

    def holder_for(self, grant_id: str) -> tuple[str, str]:
        return self._HOLDERS[grant_id]

    def depth_for(self, grant_id: str) -> int:
        return len(self._ANCESTORS[grant_id])

    # ----------------------------------------------------------- builders

    def invocation(
        self,
        *,
        grant_id: str | None = None,
        root_id: str | None = None,
        ancestor_ids: tuple[str, ...] | None = None,
        holder: tuple[str, str] | None = None,
        jti: str | None = None,
        idempotency_key: str | None = None,
        params: bytes = DEFAULT_PARAMS,
        tool_id: str = DEFAULT_TOOL,
        tool_version: str = TOOL_VERSION,
        purpose: str = PURPOSE_INVOKE,
        profile: str = PROFILE,
        endpoint: str = INVOKE_ENDPOINT,
        method: str = INVOKE_METHOD,
        token_exp: int | None = None,
        proof_iat: int | None = None,
        proof_exp: int | None = None,
        proof_ttl: int = 30,
        subject: str | None = None,
        tenant_id: str | None = None,
        task_id: str | None = None,
        token_digest: str | None = None,
        proof_digest: str | None = None,
        intent_digest: str | None = None,
        evidence_ref: str | None = None,
    ) -> VerifiedInvocation:
        """Build a well-formed trusted context; every field is overridable so
        tests can forge paths, holders, timing and bindings on purpose."""
        gid = grant_id if grant_id is not None else self.leaf_id
        holder = holder if holder is not None else self._HOLDERS.get(gid, self.executor)
        if ancestor_ids is None:
            ancestor_ids = self._ANCESTORS.get(gid, self.leaf_ancestors)
        now = int(datetime.now(tz=timezone.utc).timestamp())
        return VerifiedInvocation(
            subject=subject or self.subject,
            tenant_id=tenant_id or self.tenant_id,
            task_id=task_id or self.task_id,
            grant_id=gid,
            root_id=root_id or self.root_id,
            holder_client_id=holder[0],
            holder_kid=holder[1],
            tool_id=tool_id,
            tool_version=tool_version,
            idempotency_key=idempotency_key or unique("purchase"),
            canonical_params=params,
            token_exp=token_exp if token_exp is not None else now + 300,
            proof_iat=proof_iat if proof_iat is not None else now,
            proof_exp=proof_exp if proof_exp is not None else (proof_iat or now) + proof_ttl,
            proof_jti=jti or f"jti-{next(self._jti)}-{next(_jti_counter)}",
            token_digest=token_digest or unique("tok-digest"),
            proof_digest=proof_digest or unique("proof-digest"),
            intent_digest=intent_digest or unique("intent-digest"),
            evidence_ref=evidence_ref or unique("evidence"),
            ancestor_ids=ancestor_ids,
            profile=profile,
            purpose=purpose,
            endpoint=endpoint,
            method=method,
        )

    @property
    def leaf_ancestors(self) -> tuple[str, ...]:
        return (self.root_id, self.mid_id)

    def cost(
        self,
        amount_fen: int = 70000,
        *,
        calls: int = 1,
        currency: str = CURRENCY,
        quote_id: str | None = None,
        quote_version: str | None = None,
        quote_snapshot: bytes | None = None,
    ) -> TrustedCost:
        return TrustedCost(
            amount_fen=amount_fen,
            calls=calls,
            currency=currency,
            quote_id=quote_id if quote_id is not None else unique("quote"),
            quote_version=quote_version if quote_version is not None else "1",
            quote_snapshot=(
                quote_snapshot if quote_snapshot is not None else unique("snap").encode()
            ),
        )


def build_tree(
    conn: psycopg.Connection,
    *,
    tenant_id: str | None = None,
    task_id: str | None = None,
    subject: str = "user-demo-001",
    root_limit: int = 100000,
    mid_limit: int = 80000,
    leaf_limit: int = 70000,
    root_calls: int = 10,
    mid_calls: int = 8,
    leaf_calls: int = 5,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    register_principals: bool = True,
    holder_overrides: dict | None = None,
) -> TreeFixture:
    """Create principals plus a root -> mid -> leaf chain under one task.

    Limits are created through the trusted provisioning fixtures, so child
    limits/window always stay inside the parent's (no self-contradictory state).
    """
    tenant_id = tenant_id or unique("tenant")
    task_id = task_id or unique("task")
    not_before, expires_at = default_window()
    if valid_from is not None:
        not_before = valid_from
    if valid_until is not None:
        expires_at = valid_until

    planner = (unique("client-plan"), unique("kid-plan"))
    selector = (unique("client-select"), unique("kid-select"))
    executor = (unique("client-exec"), unique("kid-exec"))
    if holder_overrides:
        planner = holder_overrides.get("planner", planner)
        selector = holder_overrides.get("selector", selector)
        executor = holder_overrides.get("executor", executor)

    root_id = unique("grant-root")
    mid_id = unique("grant-mid")
    leaf_id = unique("grant-leaf")

    if register_principals:
        for client_id, kid in (planner, selector, executor):
            prov.register_principal(conn, tenant_id=tenant_id, client_id=client_id, kid=kid)
    prov.create_task_root(
        conn,
        tenant_id=tenant_id,
        task_id=task_id,
        grant_id=root_id,
        subject=subject,
        holder_client_id=planner[0],
        holder_kid=planner[1],
        amount_limit=root_limit,
        call_limit=root_calls,
        not_before=not_before,
        expires_at=expires_at,
    )
    prov.create_child_grant(
        conn,
        parent_grant_id=root_id,
        grant_id=mid_id,
        holder_client_id=selector[0],
        holder_kid=selector[1],
        amount_limit=mid_limit,
        call_limit=mid_calls,
        not_before=not_before,
        expires_at=expires_at,
    )
    prov.create_child_grant(
        conn,
        parent_grant_id=mid_id,
        grant_id=leaf_id,
        holder_client_id=executor[0],
        holder_kid=executor[1],
        amount_limit=leaf_limit,
        call_limit=leaf_calls,
        not_before=not_before,
        expires_at=expires_at,
    )
    return TreeFixture(
        tenant_id=tenant_id,
        task_id=task_id,
        subject=subject,
        root_id=root_id,
        mid_id=mid_id,
        leaf_id=leaf_id,
        planner=planner,
        selector=selector,
        executor=executor,
        not_before=not_before,
        expires_at=expires_at,
        amount_limits=(root_limit, mid_limit, leaf_limit),
        call_limits=(root_calls, mid_calls, leaf_calls),
    )
