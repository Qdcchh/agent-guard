"""Mutually exclusive genuine research security contexts and strict wire parsing."""

import re
from dataclasses import dataclass

from agent_guard.authorization.claims import ClaimsError, validate_access_claims
from agent_guard.authorization.passwords import verify_password
from agent_guard.authorization.permission_snapshot import (
    PermissionSnapshotProvider,
    PermissionSource,
)
from agent_guard.authorization.verifier import (
    InvocationVerifier,
    VerifiedOperationQuery,
)
from agent_guard.contracts.encoding import EncodingError, canonical_json_bytes, load_strict_json
from agent_guard.contracts.execution import ToolId, TrustedPermissionSnapshot
from agent_guard.contracts.ledger import (
    INVOKE_ENDPOINT,
    PROFILE,
    QUERY_ENDPOINT,
    VerifiedInvocation,
)
from agent_guard.crypto.sm import InvalidSm2Signature, sm3_b64url, verify_compact_jws
from agent_guard.tools.params import (
    parse_tool_id,
    parse_tool_params,
    parse_tool_version,
)
from agent_guard.tools.policy import check_static_authorization


class ResearchError(ValueError):
    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(code + (": " + detail if detail else ""))


def identifier(value):
    if type(value) is not str or not re.fullmatch(r"[\x21-\x7e]{1,128}", value):
        raise ResearchError("INVALID_SCHEMA")
    return value


@dataclass(frozen=True)
class Intent:
    task_id: str
    tool_id: ToolId
    key: str
    params: bytes
    body: bytes
    digest: str


def parse_intent(body: bytes) -> Intent:
    if type(body) is not bytes or len(body) > 65536:
        raise ResearchError("INVALID_SCHEMA")
    try:
        data = load_strict_json(body)
    except (EncodingError, UnicodeError) as exc:
        raise ResearchError("INVALID_SCHEMA") from exc
    if (
        type(data) is not dict
        or set(data)
        != {
            "profile",
            "task_id",
            "tool_id",
            "tool_version",
            "idempotency_key",
            "params",
        }
        or data["profile"] != PROFILE
    ):
        raise ResearchError("INVALID_SCHEMA")
    tool = parse_tool_id(data["tool_id"])
    if parse_tool_version(data["tool_version"]) != "1":
        raise ResearchError("INVALID_SCHEMA")
    task, key = identifier(data["task_id"]), identifier(data["idempotency_key"])
    params = canonical_json_bytes(data["params"])
    parse_tool_params(tool, params)
    normalized = canonical_json_bytes(data)
    return Intent(task, tool, key, params, normalized, sm3_b64url(normalized))


def parse_query(body: bytes):
    if type(body) is not bytes or len(body) > 65536:
        raise ResearchError("INVALID_SCHEMA")
    try:
        data = load_strict_json(body)
    except (EncodingError, UnicodeError) as exc:
        raise ResearchError("INVALID_SCHEMA") from exc
    if (
        type(data) is not dict
        or set(data) != {"profile", "task_id", "operation_id"}
        or data["profile"] != PROFILE
    ):
        raise ResearchError("INVALID_SCHEMA")
    return identifier(data["task_id"]), identifier(data["operation_id"])


@dataclass(frozen=True)
class ResearchPoPContext:
    verified: VerifiedInvocation | VerifiedOperationQuery
    source: PermissionSource
    token: str
    proof: str
    body: bytes
    intent: Intent | None
    purpose: str


@dataclass(frozen=True)
class BearerContext:
    claims: object
    source: PermissionSource
    token: str
    body: bytes
    first_ref: str
    intent: Intent | None
    operation_id: str | None
    purpose: str
    proof: None = None
    holder_possession: str = "NOT_VERIFIED"
    supplied_proof: str = "IGNORED"


@dataclass(frozen=True)
class ACLRegistration:
    role: str
    password_hash: str
    tenant_id: str
    task_id: str
    subject: str
    client_id: str
    kid: str
    grant_id: str
    root_id: str
    snapshot: TrustedPermissionSnapshot
    expires_at: int

    def __post_init__(self):
        if (
            self.role not in ("planner", "selector", "executor")
            or self.client_id != "agent-" + self.role
            or type(self.password_hash) is not str
            or type(self.snapshot) is not TrustedPermissionSnapshot
            or type(self.expires_at) is not int
            or not 0 < self.expires_at <= 2**53 - 1
        ):
            raise ValueError("approved role credential and strict ACL policy required")
        for value in (
            self.tenant_id,
            self.task_id,
            self.subject,
            self.client_id,
            self.kid,
            self.grant_id,
            self.root_id,
        ):
            identifier(value)
        if (
            self.snapshot.tenant_id,
            self.snapshot.task_id,
            self.snapshot.subject,
            self.snapshot.grant_id,
            self.snapshot.root_id,
        ) != (
            self.tenant_id,
            self.task_id,
            self.subject,
            self.grant_id,
            self.root_id,
        ):
            raise ValueError("approved ACL snapshot binding required")


@dataclass(frozen=True)
class ACLContext:
    registration: ACLRegistration
    body: bytes
    first_ref: str
    intent: Intent | None
    operation_id: str | None
    purpose: str
    proof: None = None
    holder_possession: str = "PASSWORD_AUTHENTICATED"


def context_fields(context):
    if type(context) is ResearchPoPContext:
        v = context.verified
        return dict(
            tenant=v.tenant_id,
            task=v.task_id,
            subject=v.subject,
            client=v.holder_client_id,
            kid=v.holder_kid,
            grant=v.grant_id,
            root=v.root_id,
            exp=v.token_exp,
            ref=v.evidence_ref,
            source=context.source.snapshot,
        )
    if type(context) is BearerContext:
        c = context.claims.raw
        return dict(
            tenant=c["ag_tenant_id"],
            task=c["ag_task_id"],
            subject=c["sub"],
            client=c["client_id"],
            kid=c["ag_cnf"]["kid"],
            grant=c["ag_grant_id"],
            root=c["ag_root_id"],
            exp=c["exp"],
            ref=context.first_ref,
            source=context.source.snapshot,
        )
    if type(context) is ACLContext:
        c = context.registration
        return dict(
            tenant=c.tenant_id,
            task=c.task_id,
            subject=c.subject,
            client=c.client_id,
            kid=c.kid,
            grant=c.grant_id,
            root=c.root_id,
            exp=c.expires_at,
            ref=context.first_ref,
            source=c.snapshot,
        )
    raise ResearchError("INVALID_CONTEXT")


class ResearchAuthenticator:
    def __init__(self, *, issuer, as_keys, identities, provider, evidence, acl_registry=()):
        if type(provider) is not PermissionSnapshotProvider:
            raise ValueError("real permission provider required")
        self.issuer, self.keys, self.identities = issuer, dict(as_keys), identities
        self.provider, self.evidence = provider, evidence
        if type(acl_registry) is not tuple or any(
            type(r) is not ACLRegistration for r in acl_registry
        ):
            raise ValueError("distinct approved roles required")
        self.acl = {(r.role, r.task_id): r for r in acl_registry}
        credentials = {}
        for registration in acl_registry:
            roles = credentials.setdefault(registration.password_hash, set())
            roles.add(registration.role)
        if len(self.acl) != len(acl_registry) or any(
            len(roles) > 1 for roles in credentials.values()
        ):
            raise ValueError("distinct approved role credentials required")
        self.verifier = InvocationVerifier(
            issuer=issuer,
            as_keys=as_keys,
            identities=identities,
            stage_evidence=evidence.stage,
        )

    def authenticate(
        self,
        *,
        mode,
        body,
        now,
        token=None,
        proof=None,
        role=None,
        password=None,
        purpose="invoke",
    ):
        if type(now) is not int or now < 0 or purpose not in ("invoke", "result-read"):
            raise ResearchError("INVALID_SCHEMA")
        intent = parse_intent(body) if purpose == "invoke" else None
        task, operation = (intent.task_id, None) if intent else parse_query(body)
        if mode == "noAtomic":
            method = self.verifier.verify_static if intent else self.verifier.verify_result_read
            verified = method(
                token,
                proof,
                endpoint=INVOKE_ENDPOINT if intent else QUERY_ENDPOINT,
                method="POST",
                body=body,
                now=now,
            )
            source = self.provider.load(token, grant_id=verified.grant_id, now=now)
            context = ResearchPoPContext(verified, source, token, proof, body, intent, purpose)
        elif mode == "Bearer":
            try:
                claims = validate_access_claims(
                    verify_compact_jws(token, expected_type="ag-at+jwt", trusted_keys=self.keys),
                    issuer=self.issuer,
                    now=now,
                )
            except InvalidSm2Signature as exc:
                raise ResearchError("INVALID_SIGNATURE") from exc
            except (ClaimsError, EncodingError, ValueError, TypeError) as exc:
                raise ResearchError("INVALID_TOKEN") from exc
            c = claims.raw
            identity = self.identities.resolve_registered(
                c["client_id"], c["ag_tenant_id"], "authentication"
            )
            if (
                identity.registration.kid != c["ag_cnf"]["kid"]
                or identity.registration.spki_sm3 != c["ag_cnf"]["spki_sm3"]
            ):
                raise ResearchError("HOLDER_MISMATCH")
            source = self.provider.load(token, grant_id=c["ag_grant_id"], now=now)
            context = BearerContext(
                claims,
                source,
                token,
                body,
                self.evidence.stage(token, None, body),
                intent,
                operation,
                purpose,
            )
        elif mode == "staticACL":
            registration = self.acl.get((role, task))
            if registration is None or not verify_password(password, registration.password_hash):
                raise ResearchError("INVALID_CREDENTIAL")
            if registration.expires_at <= now:
                raise ResearchError("EXPIRED")
            context = ACLContext(
                registration,
                body,
                self.evidence.stage(None, None, body),
                intent,
                operation,
                purpose,
            )
        else:
            raise ResearchError("INVALID_MODE")
        fields = context_fields(context)
        if task != fields["task"]:
            raise ResearchError("SCOPE_DENIED")
        if intent:
            check_static_authorization(
                fields["source"],
                grant_id=fields["grant"],
                root_id=fields["root"],
                tenant_id=fields["tenant"],
                task_id=fields["task"],
                subject=fields["subject"],
                tool_id=intent.tool_id,
                params=parse_tool_params(intent.tool_id, intent.params),
            )
        return context
