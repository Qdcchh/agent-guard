"""Strict immutable demo inputs. Public configuration contains only references."""

from __future__ import annotations

import os
import re
import stat
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json

VERSION = "demo-v2"
ROLES = frozenset(
    (
        "operator",
        "as",
        "gateway",
        "did",
        "audit",
        "publisher",
        "worker",
        "planner",
        "selector",
        "executor",
        "export",
        "offline",
    )
)
HOLDERS = ("planner", "selector", "executor")
PRIVATE_FILES = MappingProxyType(
    {
        "operator": frozenset(
            (
                "ca_key",
                "approval_registry",
                "user_login",
                "downstream_secret",
                "audit_registration",
                "authority_dsn",
                "downstream_dsn",
                "audit_dsn",
            )
        ),
        "as": frozenset(("signing_key", "secrets", "authority_dsn", "tls_key")),
        "gateway": frozenset(
            ("secrets", "authority_dsn", "downstream_dsn", "readonly_dsn", "tls_key")
        ),
        "did": frozenset(("tls_key",)),
        "audit": frozenset(("signing_key", "audit_dsn", "tls_key", "audit_config")),
        "publisher": frozenset(
            ("signing_key", "authority_dsn", "publisher_config", "audit_delivery")
        ),
        "worker": frozenset(("authority_dsn", "downstream_dsn", "downstream_secret")),
        **{h: frozenset(("signing_key", "basic_secret")) for h in HOLDERS},
        "export": frozenset(("readonly_dsn", "export_credential")),
        "offline": frozenset(),
    }
)
PAIR_NAMES = ("planner-selector", "selector-executor")


class DemoConfigError(ValueError):
    """Fail-closed configuration error; never includes secret values."""


def text(value, name="identifier"):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", value):
        raise DemoConfigError(f"invalid {name}")
    return value


def integer(value, *, minimum=1, maximum=2147483647):
    if type(value) is not int or not minimum <= value <= maximum:
        raise DemoConfigError("bounded integer required")
    return value


def run_uuid(value):
    if type(value) is not str or str(uuid.UUID(value)) != value:
        raise DemoConfigError("canonical run UUID required")
    return value


def exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise DemoConfigError("configuration fields do not match")
    return value


def decode(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 65536:
        raise DemoConfigError("configuration capacity")
    return load_strict_json(raw)


def freeze(value):
    if type(value) is dict:
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if type(value) is list:
        return tuple(freeze(v) for v in value)
    return value


def thaw(value):
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if type(value) is tuple:
        return [thaw(v) for v in value]
    return value


def leaf(value):
    if (
        type(value) is not str
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value)
        or value in (".", "..")
    ):
        raise DemoConfigError("relative leaf reference required")
    return value


def safe_base(path):
    path = Path(path)
    if not path.is_absolute() or str(path) != os.path.abspath(path):
        raise DemoConfigError("absolute canonical base required")
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise DemoConfigError("symlink base forbidden")
    return path


def reference(base, value):
    path = safe_base(base) / leaf(value)
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise DemoConfigError("aliased/nonregular file forbidden")
    return path


def origin(value):
    if type(value) is not str:
        raise DemoConfigError("HTTPS origin required")
    p = urlsplit(value)
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username
        or p.password
        or p.path
        or p.query
        or p.fragment
        or p.netloc != p.hostname
    ):
        raise DemoConfigError("canonical fixed HTTPS origin required")
    return value


@dataclass(frozen=True)
class HandoffConfig:
    socket_path: Path
    self_uid: int
    peer_uid: int
    self_client_id: str
    peer_client_id: str
    run_id: str
    task_id: str
    pair_gid: int
    receiver_uid: int

    def __post_init__(self):
        safe_base(self.socket_path.parent)
        if self.socket_path.name != "child.sock":
            raise DemoConfigError("fixed child socket required")
        for uid in (self.self_uid, self.peer_uid, self.pair_gid, self.receiver_uid):
            integer(uid)
        if self.self_uid == self.peer_uid or self.receiver_uid not in (
            self.self_uid,
            self.peer_uid,
        ):
            raise DemoConfigError("distinct pair identities required")
        run_uuid(self.run_id)
        for value in (self.self_client_id, self.peer_client_id, self.task_id):
            text(value)
        if frozenset((self.self_client_id, self.peer_client_id)) not in (
            frozenset(("agent-planner", "agent-selector")),
            frozenset(("agent-selector", "agent-executor")),
        ):
            raise DemoConfigError("unregistered handoff pair")


@dataclass(frozen=True)
class RoleConfig:
    version: str
    run_id: str
    owner_id: str
    role: str
    uid: int
    public_config_file: Path
    private_files: Mapping[str, Path] = field(repr=False)
    handoff: tuple[HandoffConfig, ...]
    gid: int
    supplementary_gids: tuple[int, ...]


@dataclass(frozen=True)
class DemoRunConfig:
    version: str
    run_id: str
    owner_id: str
    scope: Mapping[str, str]
    endpoints: Mapping
    roles: Mapping[str, RoleConfig]
    public_manifest: Path
    approved_did_manifest: Path
    resource_manifest: Path
    base_dir: Path = field(repr=False)


@dataclass(frozen=True)
class PublicCheckReport:
    run_id: str
    owner_id: str
    roles: tuple[str, ...]
    scope: Mapping[str, str]


@dataclass(frozen=True)
class InitManifest:
    run_id: str
    owner_id: str
    root: Path
    run_config: Path
    files: Mapping[str, str]


@dataclass(frozen=True)
class ApprovedRegistry:
    run_id: str
    registrations: tuple
    purposes: Mapping[str, tuple[str, ...]]
    ca_file: Path
    challenge: bytes = field(repr=False)


@dataclass(frozen=True)
class ApprovedDIDSnapshot:
    run_id: str
    documents: Mapping[str, bytes]
    digests: Mapping[str, str]
    certificate_fingerprints: Mapping[str, str]
    fetched_at: Mapping[str, str]

    def factory_documents(self):
        return {url: load_strict_json(raw) for url, raw in self.documents.items()}


@dataclass(frozen=True)
class SyntheticLogin:
    tenant_id: str
    subject: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class RootRequest:
    task_id: str
    scope: str


@dataclass(frozen=True)
class DelegationRequest:
    target_client_id: str
    scope: str
    constraints: bytes
    delegation_key: str
    ttl_seconds: int = 240
    amount_limit_fen: int = 80000
    call_limit: int = 10
    delegation_remaining: int = 1


@dataclass(frozen=True)
class RootTokens:
    access_token: str = field(repr=False)
    id_token: str = field(repr=False)
    id_claims: Mapping


@dataclass(frozen=True)
class ChildToken:
    access_token: str = field(repr=False)
    target_client_id: str
    parent_client_id: str
    run_id: str
    task_id: str


@dataclass(frozen=True)
class HolderConfig:
    role: RoleConfig
    issuer: str
    gateway_origin: str
    tenant_id: str
    task_id: str
    client_id: str
    kid: str
    redirect_uri: str
    ca_file: Path
    as_keys: Mapping


@dataclass(frozen=True)
class InvocationResponse:
    status: int
    raw: bytes = field(repr=False)
    value: Mapping


QueryResponse = InvocationResponse


@dataclass(frozen=True)
class HandoffAck:
    run_id: str
    task_id: str
    sender: str
    target: str


@dataclass(frozen=True)
class WorkerConfig:
    role: RoleConfig
    tenant_id: str
    task_id: str
    catalog: object
    approved_suppliers: frozenset[str]
    approved_recipients: frozenset[str]
    served_requests: frozenset[str]
    lease_ttl_seconds: int = 30
    poll_seconds: float = 0.1


@dataclass(frozen=True)
class WriterProcess:
    role: str
    pid: int
    start_identity: str
    argv_sha256: str
    process: object = field(repr=False, compare=False)
    inflight_zero: object = field(repr=False, compare=False)


@dataclass(frozen=True)
class DrainReceipt:
    run_id: str
    owner_id: str
    writers: tuple[WriterProcess, ...]
    stopped_at: str
    blocked_credentials: tuple[str, ...]


@dataclass(frozen=True)
class OperatorSecrets:
    role: RoleConfig
    login: SyntheticLogin
    task_policy: Mapping
    downstream_secret: str = field(repr=False)
    audit_registration: Mapping = field(repr=False)


@dataclass(frozen=True)
class ProvisionReport:
    run_id: str
    registered_clients: tuple[str, ...]


@dataclass(frozen=True)
class FrozenExportInputs:
    run_id: str
    public_trust_file: Path
    external_pin_file: Path
    checkpoint_history_file: Path
    history: object
    pin: Mapping


ROLE_FIELDS = frozenset(RoleConfig.__dataclass_fields__)


def load_role_config(raw: bytes, *, role: str, base_dir: Path) -> RoleConfig:
    v = exact(decode(raw), ROLE_FIELDS)
    if role not in ROLES or v["role"] != role or v["version"] != VERSION:
        raise DemoConfigError("role/version mismatch")
    run_uuid(v["run_id"])
    text(v["owner_id"])
    integer(v["uid"])
    integer(v["gid"])
    exact(v["private_files"], PRIVATE_FILES[role])
    if type(v["supplementary_gids"]) is not list or len(set(v["supplementary_gids"])) != len(
        v["supplementary_gids"]
    ):
        raise DemoConfigError("unique supplementary groups required")
    groups = tuple(integer(g) for g in v["supplementary_gids"])
    if type(v["handoff"]) is not list:
        raise DemoConfigError("handoff list required")
    pairs = []
    for h in v["handoff"]:
        exact(h, HandoffConfig.__dataclass_fields__)
        socket_path = Path(h["socket_path"])
        pairs.append(HandoffConfig(**{**h, "socket_path": socket_path}))
    files = {key: reference(base_dir, name) for key, name in v["private_files"].items()}
    if len(set(files.values())) != len(files):
        raise DemoConfigError("private aliases forbidden")
    return RoleConfig(
        **{
            **v,
            "public_config_file": reference(base_dir, v["public_config_file"]),
            "private_files": MappingProxyType(files),
            "handoff": tuple(pairs),
            "supplementary_gids": groups,
        }
    )


def load_run_config(raw: bytes, *, base_dir: Path) -> DemoRunConfig:
    fields = set(DemoRunConfig.__dataclass_fields__) - {"base_dir"}
    v = exact(decode(raw), fields)
    if v["version"] != VERSION:
        raise DemoConfigError("demo version mismatch")
    run_uuid(v["run_id"])
    text(v["owner_id"])
    exact(v["scope"], ("gateway_origin", "tenant_id", "task_id"))
    origin(v["scope"]["gateway_origin"])
    text(v["scope"]["tenant_id"])
    text(v["scope"]["task_id"])
    exact(v["endpoints"], ("issuer", "gateway_origin", "audit_origin", "did_urls"))
    for name in ("issuer", "gateway_origin", "audit_origin"):
        origin(v["endpoints"][name])
    if (
        v["endpoints"]["issuer"] != "https://auth.agent-guard.test"
        or v["endpoints"]["gateway_origin"] != "https://gateway.agent-guard.test"
        or v["endpoints"]["audit_origin"] != "https://audit.agent-guard.test"
    ):
        raise DemoConfigError("fixed demo service origins required")
    if v["scope"]["gateway_origin"] != v["endpoints"]["gateway_origin"]:
        raise DemoConfigError("gateway scope mismatch")
    did_urls = v["endpoints"]["did_urls"]
    exact(did_urls, HOLDERS)
    for holder, url in did_urls.items():
        if url != f"https://identity.agent-guard.test/agents/{holder}/did.json":
            raise DemoConfigError("fixed registered DID URL required")
    exact(v["roles"], ROLES)
    base_dir = safe_base(base_dir)
    roles = {
        name: load_role_config(canonical_json_bytes(data), role=name, base_dir=base_dir / name)
        for name, data in v["roles"].items()
    }
    if len({r.uid for r in roles.values()}) != len(ROLES):
        raise DemoConfigError("every runtime role requires a distinct nonroot UID")
    for role in roles.values():
        if role.run_id != v["run_id"] or role.owner_id != v["owner_id"] or role.gid != role.uid:
            raise DemoConfigError("role ownership mismatch")
    for h in HOLDERS:
        if len(roles[h].handoff) != (2 if h == "selector" else 1):
            raise DemoConfigError("holder handoff count mismatch")
        if set(roles[h].supplementary_gids) != {p.pair_gid for p in roles[h].handoff}:
            raise DemoConfigError("exact pair supplementary groups required")
        for p in roles[h].handoff:
            if (
                p.self_uid != roles[h].uid
                or p.self_client_id != "agent-" + h
                or p.run_id != v["run_id"]
                or p.task_id != v["scope"]["task_id"]
            ):
                raise DemoConfigError("handoff identity mismatch")
    for h in set(ROLES) - set(HOLDERS):
        if roles[h].handoff or roles[h].supplementary_gids:
            raise DemoConfigError("nonholder IPC membership forbidden")
    pair_gids = []
    for parent, receiver in (("planner", "selector"), ("selector", "executor")):
        outgoing = [p for p in roles[parent].handoff if p.peer_client_id == "agent-" + receiver]
        incoming = [p for p in roles[receiver].handoff if p.peer_client_id == "agent-" + parent]
        if len(outgoing) != 1 or len(incoming) != 1:
            raise DemoConfigError("exact reciprocal pair required")
        a, b = outgoing[0], incoming[0]
        if (
            a.socket_path != base_dir / "ipc" / (parent + "-" + receiver) / "child.sock"
            or (a.socket_path, a.peer_uid, a.receiver_uid, a.pair_gid)
            != (b.socket_path, roles[receiver].uid, roles[receiver].uid, b.pair_gid)
            or b.peer_uid != roles[parent].uid
            or b.receiver_uid != roles[receiver].uid
        ):
            raise DemoConfigError("reciprocal pair identity mismatch")
        pair_gids.append(a.pair_gid)
    if len(set(pair_gids)) != 2 or set(pair_gids) & {r.gid for r in roles.values()}:
        raise DemoConfigError("private and IPC groups must differ")
    return DemoRunConfig(
        **{
            **v,
            "scope": freeze(v["scope"]),
            "endpoints": freeze(v["endpoints"]),
            "roles": MappingProxyType(roles),
            **{
                n: reference(base_dir, v[n])
                for n in (
                    "public_manifest",
                    "approved_did_manifest",
                    "resource_manifest",
                )
            },
            "base_dir": base_dir,
        }
    )


def check_config(config: DemoRunConfig) -> PublicCheckReport:
    if type(config) is not DemoRunConfig:
        raise DemoConfigError("validated run configuration required")
    document = {
        name: thaw(getattr(config, name))
        for name in ("version", "run_id", "owner_id", "scope", "endpoints")
    }
    document["roles"] = {}
    for name, role in config.roles.items():
        directory = config.base_dir / name
        paths = [role.public_config_file, *role.private_files.values()]
        if any(path.parent != directory for path in paths):
            raise DemoConfigError("role reference outside private leaf")
        value = {
            name: getattr(role, name)
            for name in ROLE_FIELDS
            - {"public_config_file", "private_files", "handoff", "supplementary_gids"}
        }
        value.update(
            public_config_file=role.public_config_file.name,
            private_files={k: p.name for k, p in role.private_files.items()},
            supplementary_gids=list(role.supplementary_gids),
            handoff=[
                {
                    k: str(getattr(pair, k)) if k == "socket_path" else getattr(pair, k)
                    for k in HandoffConfig.__dataclass_fields__
                }
                for pair in role.handoff
            ],
        )
        document["roles"][name] = value
    for name in ("public_manifest", "approved_did_manifest", "resource_manifest"):
        path = getattr(config, name)
        if path.parent != config.base_dir:
            raise DemoConfigError("public reference outside owner tree")
        document[name] = path.name
    validated = load_run_config(canonical_json_bytes(document), base_dir=config.base_dir)
    return PublicCheckReport(
        validated.run_id,
        validated.owner_id,
        tuple(sorted(validated.roles)),
        validated.scope,
    )


def holder_config(config: DemoRunConfig, *, holder: str) -> HolderConfig:
    """Load only this holder's public trust and own role references."""
    from agent_guard.server.factory import _load_public_key
    from agent_guard.server.private_files import read_private_file

    if holder not in HOLDERS:
        raise DemoConfigError("registered holder required")
    role = config.roles[holder]
    if os.getuid() != role.uid:
        raise DemoConfigError("holder UID required")
    value = decode(read_private_file(role.public_config_file))
    exact(value, ("client_id", "kid", "redirect_uri"))
    public = decode(read_private_file(role.public_config_file.parent / "public-trust.json"))
    if (public["run_id"], public["owner_id"], public["issuer"]) != (
        config.run_id,
        config.owner_id,
        config.endpoints["issuer"],
    ):
        raise DemoConfigError("independent public trust run mismatch")
    if value["client_id"] != "agent-" + holder:
        raise DemoConfigError("holder client mismatch")
    keys = MappingProxyType(
        {
            kid: _load_public_key(pem, "independent AS public trust")
            for kid, pem in public["as_keys"].items()
        }
    )
    return HolderConfig(
        role,
        config.endpoints["issuer"],
        config.scope["gateway_origin"],
        config.scope["tenant_id"],
        config.scope["task_id"],
        value["client_id"],
        value["kid"],
        value["redirect_uri"],
        role.public_config_file.parent / "ca.pem",
        keys,
    )


def worker_config(config: DemoRunConfig) -> WorkerConfig:
    from agent_guard.gateway.config import load_gateway_config, trusted_inputs
    from agent_guard.server.private_files import read_private_file

    role = config.roles["worker"]
    if os.getuid() != role.uid:
        raise DemoConfigError("worker UID required")
    raw = read_private_file(role.public_config_file)
    load_gateway_config(raw)
    _, _, _, catalog = trusted_inputs(load_strict_json(raw))
    return WorkerConfig(
        role,
        config.scope["tenant_id"],
        config.scope["task_id"],
        catalog,
        frozenset(("supplier-001",)),
        frozenset(("user-demo",)),
        frozenset(("req-001",)),
    )
