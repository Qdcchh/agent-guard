"""Static token, holder proof and tool-intent verification for the gateway.

``verify_static`` covers tool invocations; ``verify_result_read`` covers the
read-only operation query. Neither registers proof replay, reads grant state,
reserves budget, authorizes execution or deducts business calls; the gateway
must perform those checks in its own locked transaction.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from tongsuopy.crypto.asymciphers.ec import EllipticCurvePublicKey

from agent_guard.authorization.claims import (
    GATEWAY_AUDIENCE,
    PROFILE,
    AccessClaims,
    ClaimsError,
    validate_access_claims,
)
from agent_guard.authorization.proof import ProofVerificationError, verify_ag_proof
from agent_guard.contracts.encoding import (
    EncodingError,
    JsonObject,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.contracts.ledger import (
    INVOKE_ENDPOINT,
    PURPOSE_RESULT_READ,
    QUERY_ENDPOINT,
    VerifiedInvocation,
)
from agent_guard.crypto.sm import InvalidSm2Signature, sm3_b64url, verify_compact_jws
from agent_guard.identity.resolver import IdentityError, IdentityResolver, ResolvedIdentity

_INVOKE_FIELDS = {"profile", "task_id", "tool_id", "tool_version", "idempotency_key", "params"}
_QUERY_FIELDS = {"profile", "task_id", "operation_id"}
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


@dataclass(frozen=True)
class VerifiedOperationQuery:
    """Trusted in-process context of one authorized, read-only operation query.

    It proves the token holder asked for this exact operation under a fresh
    proof. It never authorizes execution, deducts budget or proves the
    operation belongs to the caller; the gateway must recheck all of that
    against its own state in the read transaction.
    """

    subject: str
    tenant_id: str
    task_id: str
    grant_id: str
    root_id: str
    holder_client_id: str
    holder_kid: str
    operation_id: str
    token_exp: int
    token_digest: str
    proof_digest: str
    proof_jti: str
    proof_iat: int
    proof_exp: int
    evidence_ref: str
    profile: str = PROFILE
    purpose: str = PURPOSE_RESULT_READ
    endpoint: str = QUERY_ENDPOINT


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
        stage_evidence: Callable[[str, str, bytes], str] | None = None,
        permission_provider=None,
        evidence_store=None,
    ) -> None:
        if not issuer.startswith("https://") or not as_keys:
            raise ValueError("fixed HTTPS issuer and AS trust keys are required")
        self._issuer = issuer
        self._as_keys = dict(as_keys)
        self._identities = identities
        self._stage_evidence = stage_evidence
        self._permission_provider = permission_provider
        self._evidence_store = evidence_store

    def verify_static(self, token, proof, *, endpoint, method, body, now):
        if self._stage_evidence is None:
            raise VerificationError("legacy evidence callback is not configured")
        return self._verify_static(
            token,
            proof,
            endpoint=endpoint,
            method=method,
            body=body,
            now=now,
            stage=self._stage_evidence,
        )

    def _verify_static(
        self,
        token: str,
        proof: str,
        *,
        endpoint: str,
        method: str,
        body: bytes,
        now: int,
        stage,
    ) -> VerifiedInvocation:
        if endpoint != INVOKE_ENDPOINT or method != "POST" or type(body) is not bytes:
            raise VerificationError("unexpected invocation endpoint, method or body")
        if type(now) is not int or now < 0:
            raise VerificationError("invalid verification time")
        claims, identity = self._verify_token_and_holder(token, now)
        raw_claims = claims.raw
        try:
            request, normalized_body, params = _validate_intent(body, claims)
        except (UnicodeError, TypeError) as exc:
            raise VerificationError("invalid invocation body") from exc
        try:
            p = verify_ag_proof(
                proof,
                trusted_keys={identity.registration.kid: identity.public_key},
                client_id=raw_claims["client_id"],
                purpose="invoke",
                endpoint=endpoint,
                token=token,
                body=request,
                now=now,
            )
        except ProofVerificationError as exc:
            raise VerificationError("invalid AG-Proof") from exc
        evidence_ref = stage(token, proof, body)
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

    def verify_result_read(
        self, token, proof, *, endpoint=QUERY_ENDPOINT, method="POST", body, now
    ):
        if self._stage_evidence is None:
            raise VerificationError("legacy evidence callback is not configured")
        return self._verify_result_read(
            token,
            proof,
            endpoint=endpoint,
            method=method,
            body=body,
            now=now,
            stage=self._stage_evidence,
        )

    def _verify_result_read(
        self,
        token: str,
        proof: str,
        *,
        endpoint: str = QUERY_ENDPOINT,
        method: str = "POST",
        body: bytes,
        now: int,
        stage,
    ) -> VerifiedOperationQuery:
        """Verify one read-only operation query; never deducts business calls.

        The returned context carries the exact ``operation_id`` the holder
        asked about; the gateway must still verify that the operation belongs
        to the same tenant/task/grant/holder and that the authorization state
        is currently valid, inside its own read transaction.
        """
        if endpoint != QUERY_ENDPOINT or method != "POST" or type(body) is not bytes:
            raise VerificationError("unexpected query endpoint, method or body")
        if type(now) is not int or now < 0:
            raise VerificationError("invalid verification time")
        claims, identity = self._verify_token_and_holder(token, now)
        raw_claims = claims.raw
        try:
            request = _object(load_strict_json(body), _QUERY_FIELDS, "operation query")
        except EncodingError as exc:
            raise VerificationError("invalid operation query JSON") from exc
        if request["profile"] != PROFILE or request["task_id"] != raw_claims["ag_task_id"]:
            raise VerificationError("profile or task mismatch")
        _id(request["operation_id"], "operation_id")
        try:
            p = verify_ag_proof(
                proof,
                trusted_keys={identity.registration.kid: identity.public_key},
                client_id=raw_claims["client_id"],
                purpose=PURPOSE_RESULT_READ,
                endpoint=endpoint,
                token=token,
                body=request,
                now=now,
            )
        except ProofVerificationError as exc:
            raise VerificationError("invalid AG-Proof") from exc
        evidence_ref = stage(token, proof, body)
        _id(evidence_ref, "evidence reference")
        return VerifiedOperationQuery(
            subject=raw_claims["sub"],
            tenant_id=raw_claims["ag_tenant_id"],
            task_id=raw_claims["ag_task_id"],
            grant_id=raw_claims["ag_grant_id"],
            root_id=raw_claims["ag_root_id"],
            holder_client_id=raw_claims["client_id"],
            holder_kid=identity.registration.kid,
            operation_id=request["operation_id"],
            token_exp=raw_claims["exp"],
            token_digest=sm3_b64url(token.encode("ascii")),
            proof_digest=sm3_b64url(proof.encode("ascii")),
            proof_jti=p["jti"],
            proof_iat=p["iat"],
            proof_exp=p["exp"],
            evidence_ref=evidence_ref,
        )

    def _providers(self):
        from agent_guard.authorization.evidence_store import EvidenceStore
        from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider

        if (
            type(self._permission_provider) is not PermissionSnapshotProvider
            or type(self._evidence_store) is not EvidenceStore
        ):
            raise VerificationError("real trusted permission and evidence providers required")
        return self._permission_provider, self._evidence_store

    def verify_bundle(self, token, proof, *, endpoint=INVOKE_ENDPOINT, method="POST", body, now):
        from agent_guard.contracts.verification import VerifiedInvocationBundle

        provider, evidence = self._providers()
        invocation = self._verify_static(
            token,
            proof,
            endpoint=endpoint,
            method=method,
            body=body,
            now=now,
            stage=lambda *_: "pending-verified-material",
        )
        source = provider.load(token, grant_id=invocation.grant_id, now=now)
        invocation = replace(invocation, ancestor_ids=source.snapshot.chain_grant_ids[:-1])
        ref = evidence.stage(token=token, proof=proof, body=body, context=invocation, source=source)
        invocation = replace(invocation, evidence_ref=ref)
        return VerifiedInvocationBundle(invocation, source.snapshot, ref, source)

    def verify_canonical_result_read(
        self, token, proof, *, endpoint=QUERY_ENDPOINT, method="POST", body, now
    ):
        from agent_guard.contracts.execution import VerifiedResultQuery

        provider, evidence = self._providers()
        query = self._verify_result_read(
            token,
            proof,
            endpoint=endpoint,
            method=method,
            body=body,
            now=now,
            stage=lambda *_: "pending-verified-material",
        )
        source = provider.load(token, grant_id=query.grant_id, now=now)
        canonical = VerifiedResultQuery(
            subject=query.subject,
            profile=query.profile,
            tenant_id=query.tenant_id,
            task_id=query.task_id,
            operation_id=query.operation_id,
            holder_client_id=query.holder_client_id,
            holder_kid=query.holder_kid,
            grant_id=query.grant_id,
            root_id=query.root_id,
            purpose=query.purpose,
            endpoint=query.endpoint,
            method="POST",
            token_exp=query.token_exp,
            proof_iat=query.proof_iat,
            proof_exp=query.proof_exp,
            proof_jti=query.proof_jti,
            token_digest=query.token_digest,
            proof_digest=query.proof_digest,
            evidence_ref=query.evidence_ref,
        )
        ref = evidence.stage(token=token, proof=proof, body=body, context=canonical, source=source)
        return replace(canonical, evidence_ref=ref)

    def _verify_token_and_holder(
        self, token: str, now: int
    ) -> tuple[AccessClaims, ResolvedIdentity]:
        """Shared token, claims and enterprise-registry holder verification."""
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
        except VerificationError:
            raise
        except (InvalidSm2Signature, ClaimsError, IdentityError, TypeError, ValueError) as exc:
            raise VerificationError("invalid access token or holder") from exc
        return claims, identity
