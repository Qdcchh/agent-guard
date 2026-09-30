"""Static token, holder proof and tool-intent verification for the gateway.

This does not register proof replay, read grant state, reserve budget, or
authorize execution. The ledger must perform those checks atomically.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

from tongsuopy.crypto.asymciphers.ec import EllipticCurvePublicKey

from agent_guard.authorization.claims import (
    GATEWAY_AUDIENCE,
    PROFILE,
    AccessClaims,
    ClaimsError,
    validate_access_claims,
)
from agent_guard.contracts.encoding import (
    EncodingError,
    JsonObject,
    b64url_decode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.contracts.ledger import INVOKE_ENDPOINT, VerifiedInvocation
from agent_guard.crypto.sm import InvalidSm2Signature, sm3_b64url, verify_compact_jws
from agent_guard.identity.resolver import IdentityError, IdentityResolver

_PROOF_FIELDS = {
    "profile",
    "purpose",
    "client_id",
    "jti",
    "iat",
    "exp",
    "htm",
    "htu",
    "token_sm3",
    "body_sm3",
}
_INVOKE_FIELDS = {"profile", "task_id", "tool_id", "tool_version", "idempotency_key", "params"}
_TOOLS = {
    "procurement.request.read": {"request_id"},
    "procurement.document.read": {"request_id", "document_id"},
    "procurement.order.create": {"request_id", "quote_id", "quote_version", "items", "delivery_id"},
    "notification.template.send": {"template_id", "recipient_id", "operation_id"},
}
_ID = re.compile(r"[\x21-\x7e]{1,128}\Z", re.ASCII)
_VERSION = re.compile(r"[1-9][0-9]*\Z", re.ASCII)


class VerificationError(ValueError):
    """The external token/proof/request is not a valid static invocation."""


def _id(value: object, name: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise VerificationError(f"invalid {name}")
    return value


def _object(value: object, fields: set[str], name: str) -> JsonObject:
    if type(value) is not dict or set(value) != fields:
        raise VerificationError(f"invalid {name} fields")
    return value


def _validate_intent(body: bytes, claims: AccessClaims) -> tuple[JsonObject, bytes, bytes]:
    try:
        request = _object(load_strict_json(body), _INVOKE_FIELDS, "invocation")
    except EncodingError as exc:
        raise VerificationError("invalid invocation JSON") from exc
    if request["profile"] != PROFILE or request["task_id"] != claims.raw["ag_task_id"]:
        raise VerificationError("profile or task mismatch")
    tool = request["tool_id"]
    if type(tool) is not str or tool not in _TOOLS or tool not in claims.scopes:
        raise VerificationError("tool is not in scope")
    if request["tool_version"] != "1":
        raise VerificationError("unsupported tool version")
    _id(request["idempotency_key"], "idempotency_key")
    params = _object(request["params"], _TOOLS[tool], "params")
    constraints = claims.constraints

    def allowed(field: str, collection: str) -> None:
        if _id(params[field], field) not in constraints[collection]:
            raise VerificationError(f"{field} is not authorized")

    if tool in {
        "procurement.request.read",
        "procurement.document.read",
        "procurement.order.create",
    }:
        allowed("request_id", "request_ids")
    if tool == "procurement.document.read":
        allowed("document_id", "document_ids")
    if tool == "procurement.order.create":
        if "@" in _id(params["quote_id"], "quote_id"):
            raise VerificationError("quote_id must not contain @")
        version = _id(params["quote_version"], "quote_version")
        if not _VERSION.fullmatch(version):
            raise VerificationError("invalid quote version")
        if f"{params['quote_id']}@{version}" not in constraints["quote_versions"]:
            raise VerificationError("quote version is not authorized")
        allowed("delivery_id", "delivery_ids")
        items = params["items"]
        if type(items) is not list or not items:
            raise VerificationError("order items must be nonempty")
        skus: set[str] = set()
        for item in items:
            row = _object(item, {"sku", "quantity"}, "order item")
            sku = _id(row["sku"], "sku")
            quantity = row["quantity"]
            if sku in skus or sku not in constraints["skus"]:
                raise VerificationError("duplicate or unauthorized SKU")
            if type(quantity) is not int or not 1 <= quantity <= constraints["max_quantity"]:
                raise VerificationError("quantity exceeds authorization")
            skus.add(sku)
    if tool == "notification.template.send":
        allowed("template_id", "template_ids")
        allowed("recipient_id", "recipient_ids")
        _id(params["operation_id"], "operation_id")
        # The operation's ownership and accessibility require trusted state.
    return request, canonical_json_bytes(request), canonical_json_bytes(params)


class InvocationVerifier:
    """Produce ledger input only after exact signed-token/proof validation.

    ``stage_evidence`` is a trusted storage callback. It must retain the exact
    first token/proof/body under access control and return an opaque reference.
    An HTTP request must never supply this reference or a VerifiedInvocation.
    """

    def __init__(
        self,
        *,
        issuer: str,
        as_keys: Mapping[str, EllipticCurvePublicKey],
        identities: IdentityResolver,
        stage_evidence: Callable[[str, str, bytes], str],
    ) -> None:
        if not issuer.startswith("https://") or not as_keys:
            raise ValueError("fixed HTTPS issuer and AS trust keys are required")
        self._issuer = issuer
        self._as_keys = dict(as_keys)
        self._identities = identities
        self._stage_evidence = stage_evidence

    def verify_static(
        self,
        token: str,
        proof: str,
        *,
        endpoint: str,
        method: str,
        body: bytes,
        now: int,
    ) -> VerifiedInvocation:
        if endpoint != INVOKE_ENDPOINT or method != "POST" or type(body) is not bytes:
            raise VerificationError("unexpected invocation endpoint, method or body")
        if type(now) is not int or now < 0:
            raise VerificationError("invalid verification time")
        try:
            raw_claims = verify_compact_jws(
                token, expected_type="ag-at+jwt", trusted_keys=self._as_keys
            )
            claims = validate_access_claims(
                raw_claims, issuer=self._issuer, audience=GATEWAY_AUDIENCE, now=now
            )
            identity = self._identities.resolve_registered(
                raw_claims["client_id"], raw_claims["ag_tenant_id"], "capabilityInvocation"
            )
            if (
                claims.actors[0] != identity.registration.did
                or raw_claims["ag_cnf"]["kid"] != identity.registration.kid
                or raw_claims["ag_cnf"]["spki_sm3"] != identity.registration.spki_sm3
            ):
                raise VerificationError("token holder does not match enterprise registry")
            signed_proof = verify_compact_jws(
                proof,
                expected_type="ag-pop+jwt",
                trusted_keys={identity.registration.kid: identity.public_key},
            )
        except (InvalidSm2Signature, ClaimsError, IdentityError, TypeError, ValueError) as exc:
            raise VerificationError("invalid access token, holder or proof") from exc
        p = _object(signed_proof, _PROOF_FIELDS, "AG-Proof")
        if p["profile"] != PROFILE or p["purpose"] != "invoke":
            raise VerificationError("wrong proof profile or purpose")
        if p["client_id"] != raw_claims["client_id"] or p["htm"] != method or p["htu"] != endpoint:
            raise VerificationError("proof client or endpoint mismatch")
        proof_jti = _id(p["jti"], "proof jti")
        try:
            if len(b64url_decode(proof_jti)) < 16:
                raise VerificationError("proof jti must encode at least 128 bits")
        except EncodingError as exc:
            raise VerificationError("proof jti must be unpadded base64url") from exc
        if type(p["iat"]) is not int or type(p["exp"]) is not int:
            raise VerificationError("proof timestamps must be integers")
        if not p["iat"] <= p["exp"] <= p["iat"] + 60:
            raise VerificationError("invalid proof validity window")
        if p["iat"] > now + 5 or now >= p["exp"]:
            raise VerificationError("stale proof")
        if p["token_sm3"] != sm3_b64url(token.encode("ascii")):
            raise VerificationError("proof does not bind token")
        try:
            request, normalized_body, params = _validate_intent(body, claims)
        except (UnicodeError, TypeError) as exc:
            raise VerificationError("invalid invocation body") from exc
        if p["body_sm3"] != sm3_b64url(normalized_body):
            raise VerificationError("proof does not bind body")
        evidence_ref = self._stage_evidence(token, proof, body)
        _id(evidence_ref, "evidence reference")
        return VerifiedInvocation(
            subject=raw_claims["sub"],
            tenant_id=raw_claims["ag_tenant_id"],
            task_id=raw_claims["ag_task_id"],
            grant_id=raw_claims["ag_grant_id"],
            root_id=raw_claims["ag_root_id"],
            holder_client_id=raw_claims["client_id"],
            holder_kid=identity.registration.kid,
            tool_id=request["tool_id"],
            idempotency_key=request["idempotency_key"],
            canonical_params=params,
            token_exp=raw_claims["exp"],
            proof_iat=p["iat"],
            proof_exp=p["exp"],
            proof_jti=p["jti"],
            token_digest=sm3_b64url(token.encode("ascii")),
            proof_digest=sm3_b64url(proof.encode("ascii")),
            intent_digest=sm3_b64url(normalized_body),
            evidence_ref=evidence_ref,
            ancestor_ids=None,
        )
