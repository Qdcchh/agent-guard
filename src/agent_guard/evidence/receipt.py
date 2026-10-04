"""Offline verification of one unanchored final receipt evidence bundle.

Trust keys and historical registrations must arrive through an independent
channel, never from fields inside the evidence bundle. This checks one
operation's cryptographic and delta consistency, not completeness of a task
history, current authorization state, or the truth of a downstream result.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from tongsuopy.crypto.asymciphers.ec import EllipticCurvePublicKey

from agent_guard.authorization.claims import (
    ClaimsError,
    validate_access_claims,
    validate_child,
)
from agent_guard.authorization.proof import ProofVerificationError, verify_ag_proof
from agent_guard.authorization.verifier import VerificationError, _validate_intent
from agent_guard.contracts.encoding import (
    MAX_SAFE_INTEGER,
    EncodingError,
    canonical_json_bytes,
)
from agent_guard.contracts.ledger import INVOKE_ENDPOINT
from agent_guard.contracts.ledger_changes import canonical_ledger_changes_bytes
from agent_guard.crypto.sm import (
    InvalidSm2Signature,
    serialize_sm2_public_key,
    sm3_b64url,
    verify_compact_jws,
)
from agent_guard.identity.resolver import RegisteredIdentity

_BUNDLE_FIELDS = {
    "manifest_version",
    "anchoring_status",
    "receipt_jws",
    "ancestor_tokens",
    "token_jws",
    "proof_jws",
    "request",
    "result",
    "ledger_changes",
}
_RECEIPT_FIELDS = {
    "profile",
    "receipt_id",
    "operation_id",
    "tenant_id",
    "task_id",
    "root_grant_id",
    "grant_id",
    "token_sm3",
    "proof_sm3",
    "intent_sm3",
    "tool_id",
    "tool_version",
    "status",
    "amount_fen",
    "result_sm3",
    "ledger_sm3",
    "iat",
}
_NODE_FIELDS = {
    "grant_id",
    "amount_reserved_delta",
    "amount_settled_delta",
    "calls_reserved_delta",
    "calls_settled_delta",
}


class ReceiptVerificationError(ValueError):
    """The receipt package did not pass independent consistency checks."""


@dataclass(frozen=True)
class ReceiptTrust:
    issuer: str
    as_keys: Mapping[str, EllipticCurvePublicKey]
    gateway_keys: Mapping[str, EllipticCurvePublicKey]
    holder_keys: Mapping[str, EllipticCurvePublicKey]
    historical_registrations: Mapping[str, RegisteredIdentity]


@dataclass(frozen=True)
class VerifiedReceipt:
    operation_id: str
    status: str
    amount_fen: int
    anchoring_status: str = "UNANCHORED"


def _object(value: object, fields: set[str], name: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise ReceiptVerificationError(f"invalid {name} fields")
    return value


def _text(value: object, name: str) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 256
        or not value.isascii()
        or any(ord(char) < 33 or ord(char) > 126 for char in value)
    ):
        raise ReceiptVerificationError(f"invalid {name}")
    return value


def _integer(value: object, name: str, *, signed: bool = False) -> int:
    if (
        type(value) is not int
        or not (-MAX_SAFE_INTEGER if signed else 0) <= value <= MAX_SAFE_INTEGER
    ):
        raise ReceiptVerificationError(f"invalid {name}")
    return value


def _ascii_jws(value: object, name: str) -> str:
    if type(value) is not str or not value.isascii() or not 1 <= len(value) <= 16384:
        raise ReceiptVerificationError(f"invalid {name}")
    return value


def _verify_ledger(ledger: object, path: list[dict], receipt: dict) -> None:
    record = _object(ledger, {"operation_id", "events"}, "ledger_changes")
    if record["operation_id"] != receipt["operation_id"]:
        raise ReceiptVerificationError("ledger operation mismatch")
    events = record["events"]
    if type(events) is not list or len(events) != 2:
        raise ReceiptVerificationError("expected reserve and one terminal ledger event")
    reserve_amount = None
    for index, event in enumerate(events):
        row = _object(event, {"phase", "nodes"}, "ledger event")
        expected_phase = (
            "RESERVE" if index == 0 else "SETTLE" if receipt["status"] == "SUCCEEDED" else "RELEASE"
        )
        if row["phase"] != expected_phase:
            raise ReceiptVerificationError("ledger phase mismatch")
        nodes = row["nodes"]
        if type(nodes) is not list or len(nodes) != len(path):
            raise ReceiptVerificationError("ledger path length mismatch")
        for node, claims in zip(nodes, path, strict=True):
            delta = _object(node, _NODE_FIELDS, "ledger node")
            if delta["grant_id"] != claims["ag_grant_id"]:
                raise ReceiptVerificationError("ledger ancestor path mismatch")
            for name in _NODE_FIELDS - {"grant_id"}:
                _integer(delta[name], name, signed=True)
            if index == 0:
                amount = delta["amount_reserved_delta"]
                if (
                    amount < 0
                    or amount > claims["ag_limits"]["amount_fen"]
                    or delta["amount_settled_delta"] != 0
                    or delta["calls_reserved_delta"] != 1
                    or delta["calls_settled_delta"] != 0
                    or claims["ag_limits"]["calls"] < 1
                ):
                    raise ReceiptVerificationError("invalid reserve delta")
                if reserve_amount is None:
                    reserve_amount = amount
                elif amount != reserve_amount:
                    raise ReceiptVerificationError("different ancestor reserve amounts")
            elif (
                delta["amount_reserved_delta"] != -reserve_amount
                or delta["amount_settled_delta"]
                != (reserve_amount if expected_phase == "SETTLE" else 0)
                or delta["calls_reserved_delta"] != -1
                or delta["calls_settled_delta"] != (1 if expected_phase == "SETTLE" else 0)
            ):
                raise ReceiptVerificationError("invalid terminal delta")
    if receipt["amount_fen"] != (reserve_amount if receipt["status"] == "SUCCEEDED" else 0):
        raise ReceiptVerificationError("receipt amount does not match ledger")


def verify_receipt_bundle(bundle: object, *, trust: ReceiptTrust) -> VerifiedReceipt:
    """Verify one version-1 unanchored package against independently supplied trust."""
    if (
        not isinstance(trust, ReceiptTrust)
        or type(trust.issuer) is not str
        or not trust.issuer.startswith("https://")
        or not trust.as_keys
        or not trust.gateway_keys
    ):
        raise ValueError("independent AS and gateway trust configuration required")
    try:
        data = _object(bundle, _BUNDLE_FIELDS, "evidence bundle")
        if data["manifest_version"] != "AG-EVIDENCE-1" or data["anchoring_status"] != "UNANCHORED":
            raise ReceiptVerificationError("unsupported evidence manifest or anchoring claim")
        ledger_bytes = canonical_ledger_changes_bytes(data["ledger_changes"])
        other_bytes = canonical_json_bytes(
            {name: value for name, value in data.items() if name != "ledger_changes"}
        )
        if len(ledger_bytes) + len(other_bytes) > 1_048_576:
            raise ReceiptVerificationError("evidence bundle too large")
        receipt_jws = _ascii_jws(data["receipt_jws"], "receipt_jws")
        receipt = _object(
            verify_compact_jws(
                receipt_jws,
                expected_type="ag-receipt+jwt",
                trusted_keys=trust.gateway_keys,
            ),
            _RECEIPT_FIELDS,
            "receipt",
        )
        if receipt["profile"] != "GM-MVP-1" or receipt["status"] not in {
            "SUCCEEDED",
            "FAILED",
        }:
            raise ReceiptVerificationError("unsupported receipt profile or status")
        for name in (
            "receipt_id",
            "operation_id",
            "tenant_id",
            "task_id",
            "root_grant_id",
            "grant_id",
            "tool_id",
        ):
            _text(receipt[name], name)
        if receipt["tool_version"] != "1":
            raise ReceiptVerificationError("unsupported tool version")
        _integer(receipt["iat"], "receipt iat")
        _integer(receipt["amount_fen"], "receipt amount")
        for name in (
            "token_sm3",
            "proof_sm3",
            "intent_sm3",
            "result_sm3",
            "ledger_sm3",
        ):
            _text(receipt[name], name)

        token = _ascii_jws(data["token_jws"], "token_jws")
        proof = _ascii_jws(data["proof_jws"], "proof_jws")
        ancestors = data["ancestor_tokens"]
        if type(ancestors) is not list or not 1 <= len(ancestors) <= 3 or ancestors[-1] != token:
            raise ReceiptVerificationError("invalid ancestor token path")
        proof_payload = verify_compact_jws(
            proof, expected_type="ag-pop+jwt", trusted_keys=trust.holder_keys
        )
        ancestor_payloads = [
            verify_compact_jws(
                _ascii_jws(ancestor, "ancestor token"),
                expected_type="ag-at+jwt",
                trusted_keys=trust.as_keys,
            )
            for ancestor in ancestors
        ]
        # The receipt attests completion, not an encoded acceptance timestamp.
        # Find one common possible acceptance instant using the unchanged live
        # predicates, including five seconds of future proof skew and exclusive
        # expirations. Completion may legitimately occur after these expire.
        earliest = max(0, _integer(proof_payload.get("iat"), "proof iat") - 5)
        latest = min(receipt["iat"], _integer(proof_payload.get("exp"), "proof exp") - 1)
        for payload in ancestor_payloads:
            earliest = max(
                earliest,
                _integer(payload.get("iat"), "token iat"),
                _integer(payload.get("nbf"), "token nbf"),
            )
            latest = min(latest, _integer(payload.get("exp"), "token exp") - 1)
        if earliest > latest:
            raise ReceiptVerificationError("no common historical authorization time")
        path = []
        previous = None
        grant_ids: set[str] = set()
        for payload in ancestor_payloads:
            claims = validate_access_claims(payload, issuer=trust.issuer, now=earliest)
            raw = claims.raw
            if raw["ag_grant_id"] in grant_ids:
                raise ReceiptVerificationError("duplicate grant in ancestor path")
            grant_ids.add(raw["ag_grant_id"])
            kid = raw["ag_cnf"]["kid"]
            registration = trust.historical_registrations.get(kid)
            holder_key = trust.holder_keys.get(kid)
            if (
                registration is None
                or holder_key is None
                or registration.tenant_id != raw["ag_tenant_id"]
                or registration.client_id != raw["client_id"]
                or registration.did != claims.actors[0]
                or registration.kid != kid
                or registration.spki_sm3 != raw["ag_cnf"]["spki_sm3"]
                or registration.spki_der != serialize_sm2_public_key(holder_key)
            ):
                raise ReceiptVerificationError("historical holder binding mismatch")
            if previous is not None:
                validate_child(previous, claims)
            previous = claims
            path.append(raw)
        leaf = path[-1]
        if (
            len(path) != 3 - leaf["ag_delegation_remaining"]
            or receipt["tenant_id"] != leaf["ag_tenant_id"]
            or receipt["task_id"] != leaf["ag_task_id"]
            or receipt["root_grant_id"] != path[0]["ag_grant_id"]
            or receipt["grant_id"] != leaf["ag_grant_id"]
            or receipt["token_sm3"] != sm3_b64url(token.encode("ascii"))
            or receipt["proof_sm3"] != sm3_b64url(proof.encode("ascii"))
        ):
            raise ReceiptVerificationError("receipt authorization reference mismatch")
        request = data["request"]
        if type(request) is not dict:
            raise ReceiptVerificationError("invalid invocation request")
        parsed, normalized, _ = _validate_intent(canonical_json_bytes(request), previous)
        verify_ag_proof(
            proof,
            trusted_keys={leaf["ag_cnf"]["kid"]: trust.holder_keys[leaf["ag_cnf"]["kid"]]},
            client_id=leaf["client_id"],
            purpose="invoke",
            endpoint=INVOKE_ENDPOINT,
            token=token,
            body=parsed,
            now=earliest,
        )
        if (
            receipt["intent_sm3"] != sm3_b64url(normalized)
            or receipt["tool_id"] != parsed["tool_id"]
            or receipt["tool_version"] != parsed["tool_version"]
        ):
            raise ReceiptVerificationError("receipt intent mismatch")
        result = data["result"]
        if type(result) is not dict or receipt["result_sm3"] != sm3_b64url(
            canonical_json_bytes(result)
        ):
            raise ReceiptVerificationError("receipt result mismatch")
        ledger = data["ledger_changes"]
        if receipt["ledger_sm3"] != sm3_b64url(ledger_bytes):
            raise ReceiptVerificationError("ledger digest mismatch")
        _verify_ledger(ledger, path, receipt)
        return VerifiedReceipt(receipt["operation_id"], receipt["status"], receipt["amount_fen"])
    except (
        ClaimsError,
        EncodingError,
        InvalidSm2Signature,
        ProofVerificationError,
        VerificationError,
        UnicodeError,
        TypeError,
        ValueError,
    ) as exc:
        if isinstance(exc, ReceiptVerificationError):
            raise
        raise ReceiptVerificationError("invalid signed receipt evidence") from exc
