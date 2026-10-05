"""Final dynamic authorization for zero-cost result reads in one transaction."""

from __future__ import annotations

import re

import psycopg

from agent_guard.authorization.evidence_store import EvidenceError, EvidenceStore
from agent_guard.contracts.encoding import (
    EncodingError,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.contracts.execution import (
    MAX_GATEWAY_RESPONSE_BYTES,
    ExecutionError,
    ExecutionErrorCode,
    VerifiedResultQuery,
)
from agent_guard.contracts.ledger import (
    PURPOSE_RESULT_READ,
    QUERY_ENDPOINT,
    ErrorCode,
    LedgerError,
)
from agent_guard.contracts.verification import VerifiedQueryBundle
from agent_guard.execution import store
from agent_guard.execution.original_material import validate_original_tx
from agent_guard.execution.receipt_projection import project_receipt
from agent_guard.execution.receipt_publication import ReceiptVerifier
from agent_guard.execution.service import verify_accept_facts
from agent_guard.ledger import store as ledger_store
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.tools import policy
from agent_guard.tools.params import parse_tool_id, parse_tool_params


class AuthorizedQuery:
    """No downstream, catalog pricing, budget write or lease acquisition."""

    def __init__(self, dsn: str, *, evidence_store: EvidenceStore, receipt_verifier=None):
        if type(dsn) is not str or not dsn or type(evidence_store) is not EvidenceStore:
            raise ValueError("real database and evidence store required")
        if receipt_verifier is not None and type(receipt_verifier) is not ReceiptVerifier:
            raise ValueError("real receipt verifier required")
        self._receipt_verifier = receipt_verifier
        self._dsn = dsn
        self._evidence = evidence_store
        self._ledger = ExecutionLedger(dsn)

    @staticmethod
    def _validate(bundle):
        if type(bundle) is not VerifiedQueryBundle or type(bundle.query) is not VerifiedResultQuery:
            raise ValueError("verified query bundle required")
        q = bundle.query
        if (q.profile, q.purpose, q.endpoint, q.method) != (
            "GM-MVP-1",
            PURPOSE_RESULT_READ,
            QUERY_ENDPOINT,
            "POST",
        ):
            raise ValueError("invalid query purpose")
        for name in (
            "subject",
            "tenant_id",
            "task_id",
            "operation_id",
            "holder_client_id",
            "holder_kid",
            "grant_id",
            "root_id",
            "proof_jti",
            "token_digest",
            "proof_digest",
            "evidence_ref",
        ):
            value = getattr(q, name)
            if type(value) is not str or not re.fullmatch(r"[\x21-\x7e]{1,512}", value):
                raise ValueError("invalid query context")
        if any(
            type(getattr(q, n)) is not int or getattr(q, n) < 0
            for n in ("token_exp", "proof_iat", "proof_exp")
        ):
            raise ValueError("invalid query time")
        if not q.proof_iat <= q.proof_exp <= q.proof_iat + 60:
            raise LedgerError(ErrorCode.STALE_REQUEST)

    @staticmethod
    def _path(path, q, source):
        if (
            not path
            or not 1 <= len(path) <= 3
            or (
                tuple(g.grant_id for g in path) != source.snapshot.chain_grant_ids
                or path[0].grant_id != q.root_id
                or path[-1].grant_id != q.grant_id
            )
        ):
            raise LedgerError(ErrorCode.INVALID_CONTEXT)
        for i, g in enumerate(path):
            if (
                g.tenant_id,
                g.task_id,
                g.subject,
                g.root_grant_id,
                g.depth,
                g.parent_grant_id,
            ) != (
                q.tenant_id,
                q.task_id,
                q.subject,
                q.root_id,
                i,
                path[i - 1].grant_id if i else None,
            ):
                raise LedgerError(ErrorCode.INVALID_CONTEXT)

    def query(self, bundle):
        self._validate(bundle)
        binding = self._evidence.query_binding(bundle)
        try:
            with self._ledger._connect() as conn:
                with conn.transaction():
                    return self._query_tx(conn, bundle, binding)
        except psycopg.Error as exc:
            raise LedgerError(ErrorCode.TRUSTED_STATE_UNAVAILABLE) from exc

    def _query_tx(self, conn, bundle, binding):
        q = bundle.query
        path = ledger_store.load_path(conn, q.grant_id)
        self._path(path, q, bundle.source)
        keys = [(g.tenant_id, g.holder_client_id, g.holder_kid) for g in path]
        principals = ledger_store.lock_principals(conn, keys)
        task = ledger_store.lock_task(conn, q.tenant_id, q.task_id)
        if task.root_grant_id != q.root_id:
            raise LedgerError(ErrorCode.INVALID_CONTEXT)
        grants = ledger_store.lock_grants_root_to_leaf(conn, [g.grant_id for g in path])
        self._path(grants, q, bundle.source)
        self._ledger._check_freshness(grants, principals, q, ledger_store.db_now_epoch(conn))
        op = store.lock_operation(conn, q.operation_id)
        policy.check_operation_access(
            None
            if op is None
            else (
                op.tenant_id,
                op.task_id,
                op.grant_id,
                op.holder_client_id,
                op.holder_kid,
            ),
            tenant_id=q.tenant_id,
            task_id=q.task_id,
            grant_id=q.grant_id,
            holder_client_id=q.holder_client_id,
            holder_kid=q.holder_kid,
        )
        ids = tuple(g.grant_id for g in grants)
        verify_accept_facts(op, store.fetch_event_nodes(conn, op.operation_id), db_path=ids)
        try:
            self._original(conn, op, bundle.source)
        except (EncodingError, ValueError, TypeError, KeyError) as exc:
            raise EvidenceError("unusable original signed material") from exc
        tool = parse_tool_id(op.tool_id)
        policy.check_static_authorization(
            bundle.permissions,
            grant_id=q.grant_id,
            root_id=q.root_id,
            tenant_id=q.tenant_id,
            task_id=q.task_id,
            subject=q.subject,
            tool_id=tool,
            params=parse_tool_params(tool, op.canonical_params),
            db_path=ids,
        )
        binding(conn)
        ledger_store.record_proof(
            conn,
            holder_kid=q.holder_kid,
            purpose=q.purpose,
            endpoint=q.endpoint,
            proof_jti=q.proof_jti,
            proof_digest=q.proof_digest,
            evidence_ref=q.evidence_ref,
        )
        ledger_store.link_proof_to_operation(
            conn,
            holder_kid=q.holder_kid,
            purpose=q.purpose,
            endpoint=q.endpoint,
            proof_jti=q.proof_jti,
            operation_id=op.operation_id,
        )
        out = store.fetch_outbox(conn, op.operation_id)
        result = None
        if op.status in ("SUCCEEDED", "FAILED"):
            try:
                projection = project_receipt(conn, op.operation_id)
                result = load_strict_json(projection.result_bytes)
            except ExecutionError as exc:
                if exc.code is not ExecutionErrorCode.DOWNSTREAM_INCONSISTENT:
                    raise
                raise EvidenceError("unusable persisted final result") from exc
            except (ValueError, TypeError, KeyError) as exc:
                raise EvidenceError("unusable persisted final material") from exc
            if self._receipt_verifier is None and (
                out is None
                or out["receipt_status"] != "PENDING"
                or out["receipt_jws"] is not None
                or out["signed_at"] is not None
            ):
                raise EvidenceError("unsupported receipt publication state")
        elif op.status not in ("RESERVED", "EXECUTING", "UNKNOWN") or out is not None:
            raise EvidenceError("inconsistent operation state")
        publication = (
            self._receipt_verifier.read_tx(conn, op.operation_id)
            if self._receipt_verifier is not None
            else None
        )
        response = {
            "operation_id": op.operation_id,
            "status": op.status,
            "receipt_status": publication.receipt_status if publication else "PENDING",
            "result": result,
            "receipt_jws": publication.receipt_jws if publication else None,
        }
        try:
            response_bytes = canonical_json_bytes(response)
        except EncodingError as exc:
            raise EvidenceError("unusable persisted response") from exc
        if len(response_bytes) > MAX_GATEWAY_RESPONSE_BYTES:
            raise EvidenceError("persisted result exceeds public response limit")
        # No SQL or external dependency work follows the final clock. Commit
        # constraints are made immediate before it, including proof-link FKs.
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
        principals = ledger_store.lock_principals(conn, keys)
        current = ledger_store.lock_grants_root_to_leaf(conn, [g.grant_id for g in grants])
        self._path(current, q, bundle.source)
        self._ledger._check_freshness(current, principals, q, ledger_store.db_now_epoch(conn))
        return response

    _original = staticmethod(validate_original_tx)
