"""Explicit local share initialization; no complete private key is constructed."""

import os
import shutil
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from agent_guard.contracts.encoding import (
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.cosign.encoding import public_point_to_spki, spki_to_public_point
from agent_guard.cosign.protocol import AuthzParty, ExecParty, scalar

CONFIRM_MESSAGE = b"AGENT-GUARD-COSM2-KEYGEN-CONFIRM"


@dataclass(frozen=True)
class Share:
    role: str
    share: int = field(repr=False)
    public_key_spki: bytes
    key_epoch: int

    @property
    def public_point(self):
        return spki_to_public_point(self.public_key_spki)


def _epoch(value):
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ValueError("invalid key epoch")
    return value


def generate_shares(directory, *, key_epoch: int):
    epoch = _epoch(key_epoch)
    destination = Path(directory)
    if destination.exists() or destination.is_symlink():
        raise ValueError("share destination already exists")
    p1, p2 = ExecParty(), AuthzParty()
    public = p2.keygen_finish(p1.keygen_msg())
    p1.set_public(public)
    p1.sign_round3(CONFIRM_MESSAGE, *p2.sign_round2(CONFIRM_MESSAGE, p1.sign_round1()))
    metadata = {
        "public_key_spki_b64url": b64url_encode(public_point_to_spki(public)),
        "key_epoch": epoch,
    }
    stage = Path(tempfile.mkdtemp(prefix=".cosm2-", dir=destination.parent))
    try:
        for role, value in (("exec", p1.d1), ("authz", p2.d2)):
            (stage / role).mkdir(mode=0o700)
            payload = {"scheme": "sm2-2p", "role": role, "share_hex": f"{value:064x}", **metadata}
            _write(stage / role / "share.json", payload)
        _write(stage / "public.json", metadata)
        # Do not replace an existing destination, including one created concurrently.
        if destination.exists() or destination.is_symlink():
            raise ValueError("share destination already exists")
        os.rename(stage, destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return metadata


def _write(path, payload):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(canonical_json_bytes(payload) + b"\n")


def load_share(share_dir, *, role: str):
    if role not in {"exec", "authz"}:
        raise ValueError("invalid role")
    directory = Path(share_dir)
    status = directory.lstat()
    if not stat.S_ISDIR(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o700:
        raise ValueError("share directory permissions must be 0700")
    descriptor = os.open(directory / "share.json", os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as source:
        status = os.fstat(source.fileno())
        if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600:
            raise ValueError("share permissions must be 0600")
        raw = source.read(4097)
    if len(raw) > 4096:
        raise ValueError("oversized share file")
    payload = load_strict_json(raw)
    if type(payload) is not dict or set(payload) != {
        "scheme",
        "role",
        "share_hex",
        "public_key_spki_b64url",
        "key_epoch",
    }:
        raise ValueError("invalid share schema")
    if payload["scheme"] != "sm2-2p" or payload["role"] != role:
        raise ValueError("share scheme or role mismatch")
    value = payload["share_hex"]
    if type(value) is not str or len(value) != 64:
        raise ValueError("invalid share encoding")
    try:
        share = scalar(int(value, 16))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid share encoding") from exc
    if f"{share:064x}" != value:
        raise ValueError("noncanonical share encoding")
    spki = b64url_decode(payload["public_key_spki_b64url"])
    spki_to_public_point(spki)
    return Share(role, share, spki, _epoch(payload["key_epoch"]))
