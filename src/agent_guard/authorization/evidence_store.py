"""Restricted immutable exact verification evidence with same-transaction links.

Unaccepted staging attempts are retained indefinitely as isolated audit facts.
There is no TTL deletion or reassignment API; accepted materials are permanent.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass

import psycopg

from agent_guard.audit.contracts import AcceptDescriptor
from agent_guard.audit.journal import gateway_origin
from agent_guard.authorization.permission_snapshot import (
    PermissionSnapshotProvider,
    PermissionSource,
)
from agent_guard.contracts.encoding import b64url_encode, canonical_json_bytes
from agent_guard.contracts.ledger import AcceptDisposition
from agent_guard.crypto.sm import sm3_b64url


class EvidenceError(ValueError):
    """Missing or mismatched real material; no replacement of legacy evidence."""


def context_bytes(context) -> bytes:
    values = asdict(context)
    values.pop("evidence_ref", None)
    for key, value in list(values.items()):
        if type(value) is bytes:
            values[key] = b64url_encode(value)
        elif type(value) is tuple:
            values[key] = list(value)
    return canonical_json_bytes(values)


_BINDING_FACTORY = object()


@dataclass(frozen=True, slots=True, init=False)
class TrustedAcceptBinding:
    """Factory-created immutable descriptor and original same-TX validator.

    Composition adds a local callback without losing the verified descriptor or
    calling the original validator twice. It never derives trust from closures.
    A composed binding may also carry one *final check* callback. The ledger
    runs it after every deferred constraint, journal append and evidence write,
    with the database clock; it is the place where an approval deadline that
    elapsed while the transaction worked is refused.
    """

    descriptor: AcceptDescriptor
    _bind: Callable
    _response: Callable | None
    _final: Callable | None

    def __init__(self, descriptor, bind, response=None, final=None, *, _factory=None):
        if _factory is not _BINDING_FACTORY or type(descriptor) is not AcceptDescriptor:
            raise EvidenceError("trusted binding requires verified factory")
        if final is not None and not callable(final):
            raise EvidenceError("final check callback must be callable")
        object.__setattr__(self, "descriptor", descriptor)
        object.__setattr__(self, "_bind", bind)
        object.__setattr__(self, "_response", response)
        object.__setattr__(self, "_final", final)

    def __call__(self, conn, operation, disposition) -> None:
        if self._bind(conn, operation, disposition) is not None:
            raise EvidenceError("binding callback must return None")

    def compose(self, callback, *, final_check=None) -> TrustedAcceptBinding:
        if not callable(callback):
            raise EvidenceError("binding composition callback required")
        if final_check is not None and not callable(final_check):
            raise EvidenceError("final check callback must be callable")
        previous_final = self._final

        def combined(conn, operation, disposition):
            self(conn, operation, disposition)
            if callback(conn, operation, disposition) is not None:
                raise EvidenceError("binding callback must return None")

        def combined_final(conn, operation, disposition):
            if previous_final is not None:
                previous_final(conn, operation, disposition)
            if final_check is not None and final_check(conn, operation, disposition) is not None:
                raise EvidenceError("final check callback must return None")

        return TrustedAcceptBinding(
            self.descriptor,
            combined,
            self._response,
            combined_final if (previous_final or final_check) else None,
            _factory=_BINDING_FACTORY,
        )

    def final_check(self, conn, operation, disposition) -> None:
        """Run the composed final check, if any; called with locks still held."""
        if self._final is not None and self._final(conn, operation, disposition) is not None:
            raise EvidenceError("final check callback must return None")

    def _with_response(self, reader):
        if not callable(reader):
            raise EvidenceError("local response projection required")
        return TrustedAcceptBinding(
            self.descriptor, self._bind, reader, self._final, _factory=_BINDING_FACTORY
        )

    def response_bytes(self):
        return None if self._response is None else canonical_json_bytes(self._response())

    def after_link(self, callback=None):
        """Typed original binding attachment for direct accept/checked callers."""
        return TrustedAfterLink(self, callback, _factory=_BINDING_FACTORY)


@dataclass(frozen=True, slots=True, init=False)
class TrustedAfterLink:
    binding: TrustedAcceptBinding
    _callback: Callable | None

    def __init__(self, binding, callback=None, *, _factory=None):
        if _factory is not _BINDING_FACTORY or type(binding) is not TrustedAcceptBinding:
            raise EvidenceError("verified attachment factory required")
        if callback is not None and not callable(callback):
            raise EvidenceError("after-link observation must be callable")
        object.__setattr__(self, "binding", binding)
        object.__setattr__(self, "_callback", callback)

    def __call__(self, conn, operation, disposition, baseline) -> None:
        self.binding(conn, operation, disposition)
        if self._callback is not None:
            return self._callback(conn, operation, disposition, baseline)
        return None


class EvidenceStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def stage(
        self, *, token: str, proof: str, body: bytes, context, source: PermissionSource
    ) -> str:
        if (
            type(token) is not str
            or type(proof) is not str
            or type(body) is not bytes
            or type(source) is not PermissionSource
        ):
            raise EvidenceError("real verified raw materials and chain required")
        token_bytes = token.encode("ascii")
        proof_bytes = proof.encode("ascii")
        if (
            sm3_b64url(token_bytes) != context.token_digest
            or sm3_b64url(proof_bytes) != context.proof_digest
        ):
            raise EvidenceError("raw evidence digest mismatch")
        ref = "ev-" + secrets.token_hex(32)
        with psycopg.connect(self._dsn, connect_timeout=5) as conn:
            conn.execute("SET LOCAL statement_timeout='15s'")
            conn.execute("SET LOCAL lock_timeout='10s'")
            conn.execute(
                "INSERT INTO ag_verified_evidence "
                "(evidence_ref,token_bytes,proof_bytes,body_bytes,token_sm3,proof_sm3,body_sm3,"
                "tenant_id,task_id,subject,grant_id,root_id,holder_client_id,holder_kid,"
                "purpose,endpoint,method,proof_jti,chain_json,context_json) "
                "VALUES (" + ",".join(["%s"] * 20) + ")",
                (
                    ref,
                    token_bytes,
                    proof_bytes,
                    body,
                    context.token_digest,
                    context.proof_digest,
                    sm3_b64url(body),
                    context.tenant_id,
                    context.task_id,
                    context.subject,
                    context.grant_id,
                    context.root_id,
                    context.holder_client_id,
                    context.holder_kid,
                    context.purpose,
                    context.endpoint,
                    "POST",
                    context.proof_jti,
                    source.material(),
                    context_bytes(context),
                ),
            )
        return ref

    def binding(self, bundle):
        # This closure is per-call. Nothing is stored on a shared ledger/service.
        from agent_guard.contracts.verification import VerifiedInvocationBundle

        if type(bundle) is not VerifiedInvocationBundle:
            raise EvidenceError("verified bundle required")
        if bundle.permissions != bundle.source.snapshot or (
            bundle.evidence_ref != bundle.invocation.evidence_ref
        ):
            raise EvidenceError("bundle source mismatch")

        def bind(conn, operation, disposition):
            v = bundle.invocation
            PermissionSnapshotProvider.revalidate(conn, bundle.source)
            row = conn.execute(
                "SELECT token_bytes,proof_bytes,body_bytes,token_sm3,proof_sm3,"
                "body_sm3,context_json,chain_json FROM ag_verified_evidence WHERE evidence_ref=%s",
                (bundle.evidence_ref,),
            ).fetchone()
            if row is None or (
                sm3_b64url(bytes(row[0])) != row[3]
                or row[3] != v.token_digest
                or sm3_b64url(bytes(row[1])) != row[4]
                or row[4] != v.proof_digest
                or sm3_b64url(bytes(row[2])) != row[5]
                or bytes(row[6]) != context_bytes(v)
                or bytes(row[7]) != bundle.source.material()
            ):
                raise EvidenceError("evidence reference does not bind this verified request")
            first = conn.execute(
                "SELECT evidence_ref FROM ag_operation_evidence "
                "WHERE operation_id=%s AND kind='first'",
                (operation.operation_id,),
            ).fetchone()
            if disposition == AcceptDisposition.EXISTING:
                if first is None or first[0] != operation.evidence_ref:
                    raise EvidenceError("legacy operation lacks immutable first signed evidence")
                kind = "retry"
            else:
                if first is not None or operation.evidence_ref != bundle.evidence_ref:
                    raise EvidenceError("invalid first evidence link")
                kind = "first"
            conn.execute(
                "INSERT INTO ag_operation_evidence (evidence_ref,operation_id,kind) "
                "VALUES (%s,%s,%s)",
                (bundle.evidence_ref, operation.operation_id, kind),
            )

        descriptor = AcceptDescriptor(
            (gateway_origin(), bundle.invocation.tenant_id, bundle.invocation.task_id),
            bundle.invocation.root_id,
            bundle.source.snapshot.chain_grant_ids,
            bundle.evidence_ref,
            context_bytes(bundle.invocation),
            bundle.source.digest,
            bundle.source.material(),
            bundle.invocation.token_digest,
            bundle.invocation.proof_digest,
            sm3_b64url(bytes(row_body(bundle, self._dsn))),
        )
        return TrustedAcceptBinding(descriptor, bind, _factory=_BINDING_FACTORY)

    def query_binding(self, bundle):
        from agent_guard.contracts.verification import VerifiedQueryBundle

        if type(bundle) is not VerifiedQueryBundle or (
            bundle.permissions != bundle.source.snapshot
            or bundle.evidence_ref != bundle.query.evidence_ref
        ):
            raise EvidenceError("verified query bundle required")

        def bind(conn):
            v = bundle.query
            PermissionSnapshotProvider.revalidate(conn, bundle.source)
            row = conn.execute(
                "SELECT token_bytes,proof_bytes,body_bytes,token_sm3,proof_sm3,"
                "body_sm3,context_json,chain_json FROM ag_verified_evidence WHERE evidence_ref=%s",
                (bundle.evidence_ref,),
            ).fetchone()
            if row is None or (
                sm3_b64url(bytes(row[0])) != row[3]
                or row[3] != v.token_digest
                or sm3_b64url(bytes(row[1])) != row[4]
                or row[4] != v.proof_digest
                or sm3_b64url(bytes(row[2])) != row[5]
                or bytes(row[6]) != context_bytes(v)
                or bytes(row[7]) != bundle.source.material()
            ):
                raise EvidenceError("query evidence does not bind this verified request")

        return bind


def row_body(bundle, dsn):
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        row = conn.execute(
            "SELECT body_bytes FROM ag_verified_evidence WHERE evidence_ref=%s",
            (bundle.evidence_ref,),
        ).fetchone()
    if row is None:
        raise EvidenceError("missing verified staged request body")
    return bytes(row[0])
