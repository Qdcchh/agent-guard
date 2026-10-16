"""Private original byte storage, without independent audit claims."""

import hashlib
import os
import uuid
from pathlib import Path


class ResearchEvidence:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.is_symlink() or self.directory.stat().st_mode & 0o077:
            raise ValueError("private evidence directory required")

    def stage(self, token: str | None, proof: str | None, body: bytes) -> str:
        if type(body) is not bytes:
            raise ValueError("original bytes required")
        identifier = uuid.uuid4().hex
        target = self.directory / identifier
        target.mkdir(mode=0o700)
        for name, raw in (("token", token), ("proof", proof), ("body", body)):
            data = raw.encode("ascii") if type(raw) is str else raw
            if data is None:
                continue
            with open(target / name, "xb") as stream:
                os.chmod(target / name, 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        return identifier

    def original(self, reference: str, name: str) -> bytes | None:
        if (
            type(reference) is not str
            or len(reference) != 32
            or any(c not in "0123456789abcdef" for c in reference)
        ):
            raise ValueError("invalid reference")
        if name not in ("token", "proof", "body"):
            raise ValueError("invalid original kind")
        path = self.directory / reference / name
        return path.read_bytes() if path.exists() else None

    def hashes(self, reference: str) -> dict:
        return {
            name: hashlib.sha256(raw).hexdigest()
            for name in ("token", "proof", "body")
            if (raw := self.original(reference, name)) is not None
        }
