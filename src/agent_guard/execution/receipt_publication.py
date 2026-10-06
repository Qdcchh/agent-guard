"""Internal atomic SM2 receipt publication and same-transaction public validation."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

import psycopg

from agent_guard.authorization.evidence_store import EvidenceError
from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.contracts.encoding import load_strict_json
from agent_guard.contracts.execution import ExecutionError
from agent_guard.contracts.ledger import ErrorCode, LedgerError
from agent_guard.contracts.ledger_changes import load_ledger_changes
from agent_guard.crypto.sm import (
    serialize_sm2_public_key,
    sign_compact_jws,
    verify_compact_jws,
)
from agent_guard.evidence.receipt import verify_receipt_bundle
from agent_guard.execution import store
from agent_guard.execution.original_material import scoped_trust_tx
from agent_guard.execution.receipt_projection import project_receipt
from agent_guard.identity.resolver import RegisteredIdentity


@dataclass(frozen=True)
class ReceiptPublication:
    operation_id: str
    receipt_id: str | None
    receipt_status: str
    receipt_jws: str | None
    signed_at: datetime | None


def evidence_bundle(projection, receipt_jws):
    """Assemble the SDK's unchanged version-one package from DB projection."""
    return {
        "manifest_version": "AG-EVIDENCE-1",
        "anchoring_status": "UNANCHORED",
        "receipt_jws": receipt_jws,
        "ancestor_tokens": list(projection.ancestor_tokens),
        "token_jws": projection.token_bytes.decode("ascii"),
        "proof_jws": projection.proof_bytes.decode("ascii"),
        "request": load_strict_json(projection.request_bytes),
        "result": load_strict_json(projection.result_bytes),
        "ledger_changes": load_ledger_changes(projection.ledger_bytes),
    }


class ReceiptVerifier:
    def __init__(
        self,
        *,
        issuer,
        as_keys,
        gateway_keys,
        registrations: Mapping[tuple[str, str, str], RegisteredIdentity],
        permission_provider: PermissionSnapshotProvider,
    ):
        if not isinstance(permission_provider, PermissionSnapshotProvider):
            raise ValueError("signed permission provider required")
        if type(issuer) is not str or not issuer.startswith("https://"):
            raise ValueError("fixed issuer required")
        if not as_keys or not gateway_keys or not registrations:
            raise ValueError("independent complete receipt trust required")
        for key, registration in registrations.items():
            if type(registration) is not RegisteredIdentity or key != (
                registration.tenant_id,
                registration.client_id,
                registration.kid,
            ):
                raise ValueError("exact historical registration tuple required")
        reserved_kids = set(as_keys) | {r.kid for r in registrations.values()}
        reserved_spki = {serialize_sm2_public_key(k) for k in as_keys.values()}
        reserved_spki.update(r.spki_der for r in registrations.values())
        for kid, key in gateway_keys.items():
            if (
                type(kid) is not str
                or not 1 <= len(kid) <= 128
                or not kid.isascii()
                or any(ord(c) < 33 or ord(c) > 126 for c in kid)
                or kid in reserved_kids
                or serialize_sm2_public_key(key) in reserved_spki
            ):
                raise ValueError("gateway receipt key must have an independent role")
        self.issuer = issuer
        self.as_keys = MappingProxyType(dict(as_keys))
        self.gateway_keys = MappingProxyType(dict(gateway_keys))
        self.registrations = MappingProxyType(dict(registrations))
        self.permission_provider = permission_provider

    def _trust_tx(self, conn, operation_id):
        return scoped_trust_tx(
            conn,
            operation_id,
            issuer=self.issuer,
            as_keys=self.as_keys,
            gateway_keys=self.gateway_keys,
            registrations=self.registrations,
            permission_provider=self.permission_provider,
        )

    def verify_tx(self, conn, operation_id, receipt_jws):
        try:
            projection = project_receipt(conn, operation_id)
            trust = self._trust_tx(conn, operation_id)
            verify_receipt_bundle(evidence_bundle(projection, receipt_jws), trust=trust)
            receipt = verify_compact_jws(
                receipt_jws,
                expected_type="ag-receipt+jwt",
                trusted_keys=self.gateway_keys,
            )
            if receipt != load_strict_json(projection.claims_bytes):
                raise EvidenceError("receipt claims do not equal immutable DB projection")
            return projection
        except (ValueError, TypeError, KeyError, UnicodeError, ExecutionError) as exc:
            raise EvidenceError("unusable trusted receipt material") from exc

    def read_tx(self, conn, operation_id) -> ReceiptPublication:
        try:
            op = store.fetch_operation(conn, operation_id)
            out = store.fetch_outbox(conn, operation_id)
            if op is None:
                raise EvidenceError("missing operation")
            if op.status in ("RESERVED", "EXECUTING", "UNKNOWN"):
                if out is not None:
                    raise EvidenceError("nonterminal operation has final outbox")
                return ReceiptPublication(operation_id, None, "PENDING", None, None)
            if op.status not in ("SUCCEEDED", "FAILED") or out is None:
                raise EvidenceError("inconsistent terminal outbox")
            if out["receipt_status"] == "PENDING":
                if out["receipt_jws"] is not None or out["signed_at"] is not None:
                    raise EvidenceError("inconsistent pending publication")
                project_receipt(conn, operation_id)
                self._trust_tx(conn, operation_id)
            elif out["receipt_status"] == "READY":
                now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
                signed_at = out["signed_at"]
                if (
                    type(signed_at) is not datetime
                    or signed_at.tzinfo is None
                    or not out["created_at"] <= signed_at <= now
                    or type(out["receipt_jws"]) is not str
                    or not out["receipt_jws"]
                ):
                    raise EvidenceError("inconsistent ready publication")
                self.verify_tx(conn, operation_id, out["receipt_jws"])
            else:
                raise EvidenceError("invalid publication status")
            return ReceiptPublication(
                operation_id,
                out["receipt_id"],
                out["receipt_status"],
                out["receipt_jws"],
                out["signed_at"],
            )
        except (ValueError, TypeError, KeyError, UnicodeError, ExecutionError) as exc:
            raise EvidenceError("unusable trusted publication") from exc


class InternalPublisher:
    def __init__(
        self,
        dsn,
        *,
        private_key,
        signing_kid,
        verifier,
        connect_timeout=5,
        lock_timeout_ms=10000,
        statement_timeout_ms=15000,
    ):
        if type(dsn) is not str or not dsn or type(verifier) is not ReceiptVerifier:
            raise ValueError("explicit database and receipt verifier required")
        for value, upper in (
            (connect_timeout, 30),
            (lock_timeout_ms, 60000),
            (statement_timeout_ms, 60000),
        ):
            if type(value) is not int or not 1 <= value <= upper:
                raise ValueError("bounded positive database timeouts required")
        expected = verifier.gateway_keys.get(signing_kid)
        if (
            expected is None
            or serialize_sm2_public_key(private_key.public_key())
            != (serialize_sm2_public_key(expected))
            or private_key.curve.name != "SM2"
        ):
            raise ValueError("configured independent signing key does not match public trust")
        self._dsn = dsn
        self._private_key = private_key
        self._signing_kid = signing_kid
        self._verifier = verifier
        self._connect_timeout = connect_timeout
        self._lock_timeout_ms = lock_timeout_ms
        self._statement_timeout_ms = statement_timeout_ms

    def _connect(self):
        conn = psycopg.connect(self._dsn, connect_timeout=self._connect_timeout)
        try:
            conn.execute(
                "SELECT set_config('lock_timeout', %s, true)",
                (str(self._lock_timeout_ms),),
            )
            conn.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(self._statement_timeout_ms),),
            )
        except BaseException:
            conn.close()
            raise
        return conn

    def publish(self, operation_id) -> ReceiptPublication:
        try:
            with self._connect() as conn:
                # Only the publication row is locked; never reverse the public
                # authorization lock order by acquiring grants or operations.
                conn.execute(
                    "SELECT operation_id FROM ag_receipt_outbox WHERE operation_id=%s FOR UPDATE",
                    (operation_id,),
                ).fetchone()
                publication = self._verifier.read_tx(conn, operation_id)
                if publication.receipt_id is None or publication.receipt_status == "READY":
                    return publication
                projection = project_receipt(conn, operation_id)
                signed = sign_compact_jws(
                    self._private_key,
                    load_strict_json(projection.claims_bytes),
                    key_id=self._signing_kid,
                    token_type="ag-receipt+jwt",
                )
                self._verifier.verify_tx(conn, operation_id, signed)
                row = conn.execute(
                    "UPDATE ag_receipt_outbox SET receipt_status='READY',receipt_jws=%s,"
                    "signed_at=clock_timestamp() WHERE operation_id=%s "
                    "AND receipt_status='PENDING' "
                    "RETURNING signed_at",
                    (signed, operation_id),
                ).fetchone()
                if row is None:
                    raise EvidenceError("publication state changed under lock")
                conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
                return ReceiptPublication(
                    operation_id, publication.receipt_id, "READY", signed, row[0]
                )
        except psycopg.Error as exc:
            raise LedgerError(ErrorCode.TRUSTED_STATE_UNAVAILABLE) from exc

    def pending_page(self, *, after_operation_id, limit):
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("bounded publication page required")
        if type(after_operation_id) is not str:
            raise ValueError("keyset cursor required")
        try:
            with self._connect() as conn:
                return tuple(
                    r[0]
                    for r in conn.execute(
                        "SELECT operation_id FROM ag_receipt_outbox WHERE receipt_status='PENDING' "
                        "AND operation_id>%s ORDER BY operation_id LIMIT %s",
                        (after_operation_id, limit),
                    ).fetchall()
                )
        except psycopg.Error as exc:
            raise LedgerError(ErrorCode.TRUSTED_STATE_UNAVAILABLE) from exc
