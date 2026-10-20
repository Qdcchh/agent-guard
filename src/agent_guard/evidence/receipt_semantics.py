"""Offline verification of one unanchored final receipt evidence bundle.

Trust keys and historical registrations must arrive through an independent
channel, never from fields inside the evidence bundle. This checks one
operation's cryptographic and delta consistency, not completeness of a task
history, current authorization state, or the truth of a downstream result.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields

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
    load_strict_json,
)
from agent_guard.contracts.execution import ExecutionError
from agent_guard.contracts.ledger import INVOKE_ENDPOINT
from agent_guard.contracts.ledger_changes import canonical_ledger_changes_bytes, load_ledger_changes
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


def _outer_encoded_size(components: Mapping[str, bytes]) -> int:
    """Exact RFC8785 object size from already validated canonical components."""
    return (
        2
        + sum(
            len(canonical_json_bytes(name)) + 1 + len(value) for name, value in components.items()
        )
        + max(0, len(components) - 1)
    )


@dataclass(frozen=True, slots=True)
class ReceiptComponents:
    token_jws: bytes
    proof_jws: bytes
    ancestor_tokens: tuple[bytes, ...]
    request_raw: bytes
    result_raw: bytes
    ledger_raw: bytes
    receipt_jws: bytes
    quote_raw: bytes | None = None
    context_raw: bytes | None = None
    source_raw: bytes | None = None

    def __post_init__(self):
        total = 0
        for field in fields(self):
            value = getattr(self, field.name)
            if value is None and field.name in {"quote_raw", "context_raw", "source_raw"}:
                continue
            values = value if field.name == "ancestor_tokens" else (value,)
            if field.name == "ancestor_tokens" and (
                type(value) is not tuple or not 1 <= len(value) <= 3
            ):
                raise ReceiptVerificationError("invalid ancestor component path")
            for raw in values:
                limit = (
                    16384
                    if field.name.endswith("jws") or field.name == "ancestor_tokens"
                    else 65536
                )
                if type(raw) is not bytes or not 1 <= len(raw) <= limit:
                    if field.name == "receipt_jws":
                        raise ReceiptVerificationError("invalid receipt_jws")
                    raise ReceiptVerificationError("invalid receipt component capacity or type")
                if limit == 16384:
                    try:
                        raw.decode("ascii")
                    except UnicodeError as exc:
                        raise ReceiptVerificationError("ASCII JWS required") from exc
                total += len(raw)
        if total > 1048576:
            raise ReceiptVerificationError("receipt component aggregate exceeded")


def verify_receipt_components(
    components: ReceiptComponents, trust: ReceiptTrust
) -> VerifiedReceipt:
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
        if type(components) is not ReceiptComponents:
            raise ReceiptVerificationError("immutable receipt components required")
        data = {
            "token_jws": components.token_jws.decode("ascii"),
            "proof_jws": components.proof_jws.decode("ascii"),
            "receipt_jws": components.receipt_jws.decode("ascii"),
            "ancestor_tokens": [raw.decode("ascii") for raw in components.ancestor_tokens],
            "request": load_strict_json(components.request_raw),
            "result": load_strict_json(components.result_raw),
            "ledger_changes": load_ledger_changes(components.ledger_raw),
        }
        ledger_bytes = canonical_ledger_changes_bytes(data["ledger_changes"])
        if ledger_bytes != components.ledger_raw:
            raise ReceiptVerificationError("noncanonical ledger component")
        if canonical_json_bytes(data["result"]) != components.result_raw:
            raise ReceiptVerificationError("noncanonical result component")
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
        parsed, normalized, _ = _validate_intent(components.request_raw, previous)
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
        _verify_supplemental(components, path, parsed, proof_payload, receipt)
        return VerifiedReceipt(receipt["operation_id"], receipt["status"], receipt["amount_fen"])
    except (
        ClaimsError,
        ExecutionError,
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


def _verify_supplemental(components, path, request, proof, receipt):
    """Bind optional task originals to the already authenticated receipt path."""
    from datetime import datetime, timezone

    from agent_guard.contracts.encoding import b64url_encode
    from agent_guard.contracts.execution import ToolId
    from agent_guard.tools.params import parse_tool_params
    from agent_guard.tools.policy import check_stored_snapshot

    leaf = path[-1]
    if components.context_raw is not None:
        expected = {
            "subject": leaf["sub"],
            "tenant_id": leaf["ag_tenant_id"],
            "task_id": leaf["ag_task_id"],
            "grant_id": leaf["ag_grant_id"],
            "root_id": leaf["ag_root_id"],
            "holder_client_id": leaf["client_id"],
            "holder_kid": leaf["ag_cnf"]["kid"],
            "tool_id": request["tool_id"],
            "idempotency_key": request["idempotency_key"],
            "canonical_params": b64url_encode(canonical_json_bytes(request["params"])),
            "token_exp": leaf["exp"],
            "proof_iat": proof["iat"],
            "proof_exp": proof["exp"],
            "proof_jti": proof["jti"],
            "token_digest": receipt["token_sm3"],
            "proof_digest": receipt["proof_sm3"],
            "intent_digest": receipt["intent_sm3"],
            "ancestor_ids": [p["ag_grant_id"] for p in path[:-1]],
            "profile": "GM-MVP-1",
            "purpose": "invoke",
            "endpoint": INVOKE_ENDPOINT,
            "method": "POST",
            "tool_version": "1",
        }
        if components.context_raw != canonical_json_bytes(expected):
            raise ReceiptVerificationError("historical invocation context mismatch")
    if components.source_raw is not None:
        source = _object(
            load_strict_json(components.source_raw), {"chain", "snapshot", "digest"}, "source"
        )
        chain_raw = source["chain"].encode("utf-8")
        rows = load_strict_json(chain_raw)
        if (
            type(rows) is not list
            or len(rows) != len(path)
            or source["digest"] != sm3_b64url(chain_raw)
        ):
            raise ReceiptVerificationError("historical source chain mismatch")
        for index, (row, claims, token) in enumerate(
            zip(rows, path, components.ancestor_tokens, strict=True)
        ):

            def dt(n, claims=claims):
                return datetime.fromtimestamp(claims[n], timezone.utc).isoformat()

            expected = {
                "grant_id": claims["ag_grant_id"],
                "parent_id": claims["ag_parent_id"],
                "root_id": claims["ag_root_id"],
                "tenant_id": claims["ag_tenant_id"],
                "task_id": claims["ag_task_id"],
                "subject": claims["sub"],
                "client_id": claims["client_id"],
                "kid": claims["ag_cnf"]["kid"],
                "depth": index,
                "nbf": dt("nbf"),
                "exp": dt("exp"),
                "amount": claims["ag_limits"]["amount_fen"],
                "calls": claims["ag_limits"]["calls"],
                "token": token.decode("ascii"),
                "token_sm3": sm3_b64url(token),
                "scope": claims["scope"],
                "constraints": canonical_json_bytes(claims["ag_constraints"]).decode(),
                "actor": canonical_json_bytes(claims["act"]).decode(),
                "spki": claims["ag_cnf"]["spki_sm3"],
                "saved_exp": dt("exp"),
            }
            if row != expected:
                raise ReceiptVerificationError("historical source signed binding mismatch")
        snapshot = {
            "grant_id": leaf["ag_grant_id"],
            "root_id": leaf["ag_root_id"],
            "tenant_id": leaf["ag_tenant_id"],
            "task_id": leaf["ag_task_id"],
            "subject": leaf["sub"],
            "scope": sorted(leaf["scope"].split()),
            "chain": [p["ag_constraints"] for p in path],
            "chain_grant_ids": [p["ag_grant_id"] for p in path],
        }
        if source["snapshot"] != snapshot or canonical_json_bytes(source) != components.source_raw:
            raise ReceiptVerificationError("historical permission snapshot mismatch")
    if components.quote_raw is not None:
        params = parse_tool_params(request["tool_id"], canonical_json_bytes(request["params"]))
        reserved = load_ledger_changes(components.ledger_raw)["events"][0]["nodes"][0][
            "amount_reserved_delta"
        ]
        snapshot = check_stored_snapshot(
            tool_id=ToolId(request["tool_id"]),
            params=params,
            amount_fen=reserved,
            quote_snapshot_bytes=components.quote_raw,
        )
        if (
            snapshot.quote_id != request["params"]["quote_id"]
            or snapshot.quote_version != request["params"]["quote_version"]
        ):
            raise ReceiptVerificationError("historical quote identity mismatch")
