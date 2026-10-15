"""Independent operator-registered export credentials and local public inputs."""

import hashlib
import hmac
import re
from dataclasses import dataclass
from pathlib import Path

from agent_guard.server.config import ConfigError

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class ExportCredential:
    credential_id: str
    credential_sha256: str
    tenant_id: str
    task_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceLocalInputs:
    trust_file: str
    external_pin_file: str
    external_checkpoint_history_file: str


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ConfigError("invalid export identifier")
    return value


def load_export_credentials(value):
    if type(value) is not list or not 1 <= len(value) <= 256:
        raise ConfigError("bounded independent export registration required")
    credentials = []
    seen = set()
    for row in value:
        if type(row) is not dict or set(row) != {
            "credential_id",
            "credential_sha256",
            "tenant_id",
            "task_ids",
        }:
            raise ConfigError("exact export credential fields required")
        cid, tenant = _id(row["credential_id"]), _id(row["tenant_id"])
        digest = row["credential_sha256"]
        tasks = row["task_ids"]
        if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest) or cid in seen:
            raise ConfigError("invalid or duplicate export credential")
        if (
            type(tasks) is not list
            or not 1 <= len(tasks) <= 256
            or any(_id(task) != task for task in tasks)
            or len(set(tasks)) != len(tasks)
        ):
            raise ConfigError("bounded unique export tasks required")
        seen.add(cid)
        credentials.append(ExportCredential(cid, digest, tenant, tuple(tasks)))
    return tuple(credentials)


def load_evidence_local_inputs(value):
    fields = {"trust_file", "external_pin_file", "external_checkpoint_history_file"}
    if type(value) is not dict or set(value) != fields:
        raise ConfigError("exact trusted evidence local inputs required")
    paths = {}
    for name in fields:
        raw = value[name]
        if type(raw) is not str or not raw or "\x00" in raw or "://" in raw:
            raise ConfigError("explicit local public file path required")
        path = Path(raw)
        if not path.is_absolute() or str(path.resolve()) != raw or not path.is_file():
            raise ConfigError("canonical absolute local public file required")
        paths[name] = raw
    if len(set(paths.values())) != len(paths):
        raise ConfigError("independent local input paths required")
    return EvidenceLocalInputs(**paths)


def authenticate_export(authorization, task_id, *, credentials):
    """Return trusted tenant/task scope; no caller-provided tenant or role."""
    _id(task_id)
    if (
        type(authorization) is not str
        or not authorization.startswith("AGExport ")
        or len(authorization) > 512
    ):
        raise ConfigError("invalid export authorization")
    value = authorization[len("AGExport ") :]
    if value.count(":") != 1:
        raise ConfigError("invalid export authorization")
    cid, secret = value.split(":")
    _id(cid)
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", secret, flags=re.ASCII):
        raise ConfigError("invalid export secret")
    computed = hashlib.sha256(secret.encode("ascii")).hexdigest()
    matched = None
    for row in credentials:
        if type(row) is not ExportCredential:
            raise ConfigError("independent immutable export registrations required")
        if hmac.compare_digest(cid, row.credential_id) & hmac.compare_digest(
            computed, row.credential_sha256
        ):
            matched = row
    if matched is None or task_id not in matched.task_ids:
        raise ConfigError("export scope denied")
    return matched.tenant_id, task_id
