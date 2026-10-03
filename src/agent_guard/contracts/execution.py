"""A2 trusted in-process contracts: tool execution, recovery and receipts.

Continuation of GM-MVP-1 on top of the accepted A1 ledger. Same trust rules as
``contracts.ledger``: every type here is a *trusted in-process* object. Only
B's future verifiers may construct the verification contexts, and only
trusted initialization may seed resources. There is no "already verified
JSON" network entry, no client-declared cost, and no signature claim in this
module — SM3/JWS are produced by B's CryptoProvider at A2.3 signing time.

Design anchors (docs/oauth-oidc-sm2-mvp.md 8.3/9.4/9.5, docs/security-model.md
sections 5-8): strict four-tool parameters, immutable quote snapshots,
downstream idempotency keyed by the gateway ``operation_id``, the single
state machine RESERVED -> EXECUTING -> SUCCEEDED/FAILED/UNKNOWN, and a
pending-signature receipt outbox written in the same gateway transaction as
the terminal ledger change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

# ------------------------------------------------------------------ lifecycle


class OperationStatus(str, Enum):
    """The single state machine (docs/security-model.md section 5).

    RESERVED -> EXECUTING -> SUCCEEDED | FAILED | UNKNOWN;
    UNKNOWN -> SUCCEEDED | FAILED | UNKNOWN. SUCCEEDED/FAILED are terminal and
    never interchangeable.

    Enforcement status: the legal transitions are database-enforced by the
    ``ag_operations`` status guard added in migration 004, and the terminal
    ledger events are sealed by 005/006. This enum is the in-process spelling
    of that state machine; it is a *contract type*, not a functional promise
    about any behaviour the tests have not exercised.
    """

    RESERVED = "RESERVED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


TERMINAL_STATUSES = (OperationStatus.SUCCEEDED, OperationStatus.FAILED)


class TerminalAction(str, Enum):
    """Exactly one terminal ledger event per operation (mutually exclusive)."""

    SETTLE = "SETTLE"  # reserved -> settled, confirmed success
    RELEASE = "RELEASE"  # reserved released, persisted final failure


class ReceiptStatus(str, Enum):
    """Receipt outbox status, independent of the business status."""

    PENDING = "PENDING"  # material stored, signature dependency incomplete
    READY = "READY"  # real SM2 receipt signed over the stored material


# ------------------------------------------------------ trusted resources


@dataclass(frozen=True)
class QuoteItem:
    """One quoted SKU line; quantity and price are integers in fen (CNY)."""

    sku: str
    quantity: int
    unit_price_fen: int


@dataclass(frozen=True)
class TrustedQuoteSnapshot:
    """Immutable quote version fixed at first accept (8.3/9.5 binding).

    Built by the trusted quote service from seeded catalog data; never taken
    from request input. Retries and recovery reuse this exact snapshot, so
    later quote edits/deletions cannot re-price or break an accepted
    operation. ``total_fen`` is computed by the trusted service and must equal
    the reserved cost.
    """

    quote_id: str
    quote_version: str  # decimal positive integer string, no leading zeros
    supplier_id: str
    items: tuple[QuoteItem, ...]
    total_fen: int
    currency: str = "CNY"


@dataclass(frozen=True)
class GrantConstraints:
    """Trusted authorization-bound resource sets (8.3 ``ag_constraints``).

    All seven set fields are mandatory; a missing field is a format error and
    an empty set forbids every corresponding resource (it does NOT mean
    unlimited). Entries are unique ASCII strings. ``quote_versions`` entries
    use the fixed ``quote_id@version`` key and neither part may contain ``@``.

    Scope note: this type is only the resource-set portion of the grant's
    constraints. It is **not** the full immutable permission snapshot, which
    must additionally bind ``scope``, the grant/token identity and the
    complete ancestor narrowing chain (child sets subset of parent,
    non-increasing ``max_quantity``). Where that snapshot lives and how it is
    bound is B's contract to confirm; until then A2.1 consumes only
    test-fixture snapshots, the production path fails closed without one, and
    self-reported request constraints are never trusted.
    """

    request_ids: tuple[str, ...]
    document_ids: tuple[str, ...]
    quote_versions: tuple[str, ...]
    skus: tuple[str, ...]
    delivery_ids: tuple[str, ...]
    template_ids: tuple[str, ...]
    recipient_ids: tuple[str, ...]
    max_quantity: int


@dataclass(frozen=True)
class TrustedPermissionSnapshot:
    """Trusted in-process permission snapshot for the layered A2.1 checks.

    A2.1 ONLY. This is a *trusted fixture* object assembled by test/trusted
    initialization; it is **not** B's confirmed permission-snapshot contract
    and it is **not** signature verification. The production path fails closed
    without a B-verified snapshot and never accepts a request-supplied one.

    ``scope`` lists the tool ids the grant may call; an empty scope forbids
    every tool. ``chain`` holds the :class:`GrantConstraints` of the root, each
    intermediate ancestor and the leaf in root-first order and is what the
    narrowing check walks (every child set is a subset of its parent and
    ``max_quantity`` never increases). ``chain_grant_ids`` binds each of those
    layers to the grant node it describes, in the same root-first order, so a
    chain cannot be truncated, reordered, spliced from another path or padded:
    it must match the immutable database parent chain node for node. ``binding``
    fields must match the invocation context exactly, so a snapshot for another
    grant/task/tenant or another subject is rejected instead of silently reused.
    """

    grant_id: str
    root_id: str
    tenant_id: str
    task_id: str
    subject: str
    scope: tuple[str, ...]
    chain: tuple[GrantConstraints, ...]  # root-first, ends at the leaf grant
    chain_grant_ids: tuple[str, ...]  # root-first grant node each chain layer describes


# ------------------------------------------------------------ tool params


class ToolId(str, Enum):
    """The four complete tool identifiers from 9.4; no aliases or shortening."""

    REQUEST_READ = "procurement.request.read"
    DOCUMENT_READ = "procurement.document.read"
    ORDER_CREATE = "procurement.order.create"
    NOTIFICATION_SEND = "notification.template.send"


@dataclass(frozen=True)
class OrderItem:
    sku: str
    quantity: int  # positive integer, <= GrantConstraints.max_quantity


@dataclass(frozen=True)
class RequestReadParams:
    request_id: str


@dataclass(frozen=True)
class DocumentReadParams:
    request_id: str
    document_id: str


@dataclass(frozen=True)
class OrderCreateParams:
    request_id: str
    quote_id: str
    quote_version: str
    items: tuple[OrderItem, ...]  # >= 1 item, no duplicate SKUs
    delivery_id: str


@dataclass(frozen=True)
class NotificationSendParams:
    template_id: str
    recipient_id: str
    operation_id: str  # existing operation of the same task, accessible to the grant


# --------------------------------------------------------------- downstream


@dataclass(frozen=True)
class DownstreamOutcome:
    """What the mock downstream actually persisted for one operation key.

    Returned on first execution and on idempotent replay (``already_existed``).

    Quote binding (C6): ``quote`` carries the **complete**
    :class:`TrustedQuoteSnapshot` the downstream validated and executed —
    including supplier and unit-price allocation — not just ids or a total.
    The gateway settles an order only when this snapshot equals the accepted
    operation's stored snapshot field by field (structural comparison is
    enough for A2.1; no synthetic SM3), together with ``amount_fen`` and
    ``canonical_params``. Equal totals with a different supplier or price
    allocation therefore cannot settle; a mismatch that may already have
    produced an effect leads to UNKNOWN and never to a release.

    Field semantics per tool (9.4):

    - ``ORDER_CREATE``: ``quote`` set, ``amount_fen`` = snapshot total,
      ``effect_ref`` = order id, ``result_bytes`` = order record.
    - ``REQUEST_READ`` / ``DOCUMENT_READ``: ``quote`` is ``None``,
      ``amount_fen`` = 0, ``effect_ref`` is ``None`` (the fixed result *is*
      the effect), ``result_bytes`` = the read payload fixed on replay.
    - ``NOTIFICATION_SEND``: ``quote`` is ``None``, ``amount_fen`` = 0,
      ``effect_ref`` = notification id, ``result_bytes`` = delivery record.
    - ``final_rejection=True``: no order/notification was created
      (``effect_ref`` is ``None``, ``amount_fen`` = 0); ``result_bytes``
      holds the persisted terminal refusal record and ``canonical_params``
      still binds what was refused. A persisted rejection makes late success
      impossible for that key.

    ``result_bytes`` is **not** an opaque blob: it is parsed by the strict
    per-tool schema in ``agent_guard.tools.results`` (exact fields, exact
    types, bounded size/depth) and every field must bind to this operation's
    key, tool, intent, quote and amount. Anything else keeps the operation
    ``UNKNOWN``; a refusal record for another tool can never release it.
    """

    operation_id: str  # stable downstream key = gateway operation id
    tool_id: ToolId
    canonical_params: bytes  # exactly what the downstream executed
    quote: TrustedQuoteSnapshot | None  # full snapshot actually validated
    amount_fen: int  # confirmed amount; must equal the reserved cost
    effect_ref: str | None  # order/notification id; None for reads/rejections
    result_bytes: bytes  # persisted result payload, fixed on replay
    final_rejection: bool  # persisted terminal refusal (FAILED path)
    already_existed: bool  # idempotent replay of the same effect


@runtime_checkable
class DownstreamPort(Protocol):
    """Mock downstream service boundary (A2.1), later a real downstream.

    Every method requires the independent gateway service secret; agent or
    caller credentials are refused and no result is leaked on auth failure.
    Effects, intents, results and final rejections are persisted with database
    unique constraints inside the downstream's own transaction domain (a
    separate database; gateway connections/transactions are never reused).
    """

    def execute(
        self,
        *,
        service_secret: str,
        operation_id: str,
        tool_id: ToolId,
        canonical_params: bytes,
        quote: TrustedQuoteSnapshot | None,
        expected_amount_fen: int,
    ) -> DownstreamOutcome: ...

    def query(self, *, service_secret: str, operation_id: str) -> DownstreamOutcome | None:
        """Return the persisted record or ``None`` when nothing is known yet.

        ``None`` is not a final failure (a late success may still arrive);
        callers keep the budget reserved and continue recovery.
        """
        ...


# ------------------------------------------------------------------- lease


@dataclass(frozen=True)
class LeaseGrant:
    """Execution lease with a fencing token (docs/security-model.md 5.9).

    ``fencing_version`` increases on every acquisition; terminal writes are
    conditioned on holding the current version, so an expired owner can
    neither overwrite a newer owner nor a terminal state. Lease expiry is
    time-based and does not by itself mean failure: recovery re-checks the
    downstream first.

    Claim rules per state (enforced by the A2.1 worker, not widened here):

    - ``RESERVED``: claiming the lease **and** moving to ``EXECUTING`` happen
      in one gateway transaction.
    - expired ``EXECUTING``: a takeover claim acquires a new fencing version
      and then **reconciles with the downstream first**; it never releases or
      settles blindly.
    - ``UNKNOWN``: a recovery claim acquires a lease but the status **stays
      ``UNKNOWN``** while reconciling; only the reconciliation outcome moves
      it to SUCCEEDED/FAILED/UNKNOWN — claims never force UNKNOWN->EXECUTING.
    - live lease held by another owner, terminal status, or a quarantined
      operation: the entry is refused or returns no change.

    Time conditions use the database clock after locks (``clock_timestamp()``),
    never the application clock; an old worker late with a stale
    ``fencing_version`` gets its conditional updates refused.
    """

    operation_id: str
    owner_token: str
    fencing_version: int
    expires_at: datetime


# ----------------------------------------------------------------- receipt


@dataclass(frozen=True)
class PendingReceipt:
    """Immutable signing material for the receipt outbox (9.5).

    Persisted in the same gateway transaction as the terminal ledger event
    with ``receipt_status = PENDING``. This is *material*, not a receipt: no
    signature and no SM3 value has been produced yet.

    Byte-field semantics:

    - ``ledger_changes_json``: UTF-8 JSON serialization of the structured
      ``{operation_id, events:[...]}`` object (plain bytes chosen for
      immutability — no mutable dict is shared across the frozen boundary).
      It is **not** B's canonical encoding; at A2.3 B's encoder re-encodes the
      structure canonically and ``ledger_sm3`` covers those canonical bytes.
    - ``result_bytes``: the plain result payload; ``result_sm3`` later covers
      B's canonical form of it.

    ``created_at`` is the persisted outbox timestamp; the receipt ``iat`` is
    derived from it at signing time so retries reuse the same material and
    never roll a new id/iat. ``token_digest``/``proof_digest``/``intent_digest``
    are the **opaque** first-accept evidence strings stored by A1 — in
    production they carry B-computed SM3 digests, and A2.1 test fixtures use
    clearly-marked placeholders that are never presented as real SM3.

    FAILED receipts carry ``amount_fen = 0``; UNKNOWN operations get no final
    receipt.
    """

    receipt_id: str
    operation_id: str
    profile: str
    tenant_id: str
    task_id: str
    root_grant_id: str
    grant_id: str
    tool_id: str
    tool_version: str
    status: OperationStatus  # SUCCEEDED or FAILED only
    amount_fen: int
    ledger_changes_json: bytes  # structured JSON bytes; NOT canonical/SM3
    result_bytes: bytes  # plain result payload for the later result_sm3
    token_digest: str  # opaque first-accept evidence string as stored by A1
    proof_digest: str
    intent_digest: str
    evidence_ref: str
    created_at: datetime  # persisted outbox time; receipt iat derives from it


# ------------------------------------------------------- result-read query


@dataclass(frozen=True)
class VerifiedResultQuery:
    """Trusted in-process context for ``POST /v1/operations/query``.

    Purpose is fixed to ``result-read`` and this type is *not* accepted by
    ``ExecutionLedger.accept``: result reads have their own contract and
    verification path (A2.2) and never carry tool/idempotency fields. Only B's
    future verifier constructs it; result reads do not consume business calls.

    ``evidence_ref`` is mandatory here because the result-read path registers
    its fresh proof in ``ag_proofs`` whose ``evidence_ref`` column is NOT NULL
    (A1 schema), and each query proof must be traceable to staged evidence.

    Trusted-source note (A2.2 dependency): ``subject``/``grant_id``/``root_id``
    and the ancestor path must come from B's verification plus the immutable
    database path — never from request claims. :class:`GrantConstraints` is
    only the seven resource sets plus ``max_quantity``; it is **not** the full
    permission snapshot, which additionally binds scope, the grant/token
    identity and the complete ancestor narrowing chain. That binding contract
    is still pending with B; until it exists the production query path fails
    closed and nothing here may be treated as a confirmed B interface.
    """

    subject: str
    profile: str
    tenant_id: str
    task_id: str
    operation_id: str
    holder_client_id: str
    holder_kid: str
    grant_id: str
    root_id: str
    purpose: str  # "result-read"
    endpoint: str
    method: str
    token_exp: int
    proof_iat: int
    proof_exp: int
    proof_jti: str
    token_digest: str
    proof_digest: str
    evidence_ref: str  # required: ag_proofs.evidence_ref is NOT NULL


# ------------------------------------------------------------------ errors


class ExecutionErrorCode(str, Enum):
    """Internal rejection codes for the A2 execution layer.

    HTTP mapping follows 9.6 in A2.2; format, authorization and trusted
    dependency failures stay distinguishable and never collapse into a single
    generic server error.
    """

    INVALID_PARAMS = "INVALID_PARAMS"
    UNSUPPORTED_TOOL = "UNSUPPORTED_TOOL"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_NOT_AUTHORIZED = "RESOURCE_NOT_AUTHORIZED"
    CONSTRAINT_MISMATCH = "CONSTRAINT_MISMATCH"
    QUOTE_INVALID = "QUOTE_INVALID"
    OPERATION_NOT_FOUND = "OPERATION_NOT_FOUND"
    ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"
    LEASE_LOST = "LEASE_LOST"
    DOWNSTREAM_UNAUTHORIZED = "DOWNSTREAM_UNAUTHORIZED"
    DOWNSTREAM_UNAVAILABLE = "DOWNSTREAM_UNAVAILABLE"
    DOWNSTREAM_INCONSISTENT = "DOWNSTREAM_INCONSISTENT"
    #: The same downstream key arrived with a different intent; nothing is
    #: written and the already-persisted effect/rejection stays authoritative.
    DOWNSTREAM_INTENT_CONFLICT = "DOWNSTREAM_INTENT_CONFLICT"
    TRUSTED_DEPENDENCY_UNAVAILABLE = "TRUSTED_DEPENDENCY_UNAVAILABLE"
    LEGACY_SNAPSHOT_INVALID = "LEGACY_SNAPSHOT_INVALID"


class ExecutionError(Exception):
    """Raised for every rejected or unavailable execution-layer step."""

    def __init__(self, code: ExecutionErrorCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}" if detail else code.value)
