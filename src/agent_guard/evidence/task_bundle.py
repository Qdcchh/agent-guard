"""Bounded AG-TASK-EVIDENCE-2 framing and authenticated public history inputs."""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from agent_guard.audit.checkpoint import verify_checkpoint
from agent_guard.audit.contracts import JournalScope, digest, integer
from agent_guard.contracts.encoding import (
    EncodingError,
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.crypto.sm import InvalidSm2Signature, sm3_b64url

CHUNK_BYTES = 24576
MAX_LINE_BYTES = 65536
MAX_WIRE_BYTES = 268435456
MAX_FRAMES = 400000
MAX_OBJECTS = 200000
MAX_JOURNAL = 100000
MAX_OPERATIONS = 20000
OBJECT_LIMITS = {
    **dict.fromkeys(("token", "proof", "ancestor_token", "receipt", "checkpoint"), 16384),
    "journal": 32768,
    **dict.fromkeys(
        (
            "request",
            "result",
            "ledger",
            "quote",
            "context",
            "source",
            "raw_authorization_snapshot",
            "typed_snapshot_metadata",
        ),
        65536,
    ),
}
HEADER_FIELDS = {
    "frame_type",
    "manifest_version",
    "scope",
    "cutoff_sequence",
    "cutoff_head_digest",
    "snapshot_as_of",
    "snapshot_id",
    "history_boundary",
    "bootstrap_digest",
    "object_count",
    "chunk_count",
    "journal_count",
    "operation_count",
}
CHUNK_FIELDS = {
    "frame_type",
    "object_kind",
    "object_id",
    "chunk_index",
    "chunk_count",
    "total_raw_bytes",
    "object_digest",
    "data",
}
FOOTER_FIELDS = {
    "frame_type",
    "object_index_root",
    "wire_root",
    "before_footer_frames",
    "before_footer_wire_bytes",
}


class TaskBundleError(EncodingError):
    """A task stream is malformed, incomplete, inconsistent, or over capacity."""


def _text(value, name, maximum=512):
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or not value.isascii()
        or any(ord(c) < 33 or ord(c) > 126 for c in value)
    ):
        raise TaskBundleError(f"invalid {name}")
    return value


def _scope(value):
    if type(value) is JournalScope:
        return value
    if type(value) is not dict or set(value) != {
        "gateway_id",
        "tenant_id",
        "task_id",
        "stream_id",
        "epoch",
    }:
        raise TaskBundleError("exact scope required")
    return JournalScope(**value)


def object_id(object_kind, owner_type, owner_id, component, ordinal=0):
    """Identity is typed and stable, independent of object content."""
    if object_kind not in OBJECT_LIMITS or owner_type not in {
        "bootstrap",
        "journal",
        "evidence",
        "operation",
        "checkpoint",
        "runtime",
    }:
        raise TaskBundleError("invalid object identity")
    _text(owner_id, "owner_id")
    _text(component, "component")
    integer(ordinal, maximum=2 if component == "ancestor_token" else 0)
    return "obj:" + sm3_b64url(
        canonical_json_bytes(
            {
                "profile": "AG-TASK-OBJECT-ID-1",
                "object_kind": object_kind,
                "owner_type": owner_type,
                "owner_id": owner_id,
                "component": component,
                "ordinal": ordinal,
            }
        )
    )


def index_seed(scope):
    return sm3_b64url(
        canonical_json_bytes({"profile": "AG-TASK-OBJECT-INDEX-1", "scope": asdict(_scope(scope))})
    )


def index_fold(previous, frame):
    return sm3_b64url(
        canonical_json_bytes(
            {
                "profile": "AG-TASK-OBJECT-INDEX-1",
                "previous": previous,
                "kind": frame["object_kind"],
                "id": frame["object_id"],
                "total_raw_bytes": frame["total_raw_bytes"],
                "object_digest": frame["object_digest"],
                "chunk_count": frame["chunk_count"],
            }
        )
    )


def wire_seed(scope):
    return sm3_b64url(
        canonical_json_bytes({"profile": "AG-TASK-WIRE-1", "scope": asdict(_scope(scope))})
    )


def wire_fold(previous, index, raw):
    return sm3_b64url(
        canonical_json_bytes(
            {
                "profile": "AG-TASK-WIRE-1",
                "previous": previous,
                "index": index,
                "frame_digest": sm3_b64url(raw),
                "wire_bytes": len(raw),
            }
        )
    )


def encode_object_chunks(kind, id, raw):
    """Yield canonical NDJSON bytes; do not parse or normalize the original."""
    _text(id, "object_id")
    if (
        kind not in OBJECT_LIMITS
        or type(raw) is not bytes
        or not 1 <= len(raw) <= OBJECT_LIMITS[kind]
    ):
        raise TaskBundleError("logical object capacity exceeded")
    count = (len(raw) + CHUNK_BYTES - 1) // CHUNK_BYTES
    for index in range(count):
        yield (
            canonical_json_bytes(
                {
                    "frame_type": "OBJECT_CHUNK",
                    "object_kind": kind,
                    "object_id": id,
                    "chunk_index": index,
                    "chunk_count": count,
                    "total_raw_bytes": len(raw),
                    "object_digest": sm3_b64url(raw),
                    "data": b64url_encode(raw[index * CHUNK_BYTES : (index + 1) * CHUNK_BYTES]),
                }
            )
            + b"\n"
        )


def _lines(stream):
    while True:
        raw = stream.readline(MAX_LINE_BYTES + 1)
        if raw == b"":
            return
        if (
            type(raw) is not bytes
            or len(raw) > MAX_LINE_BYTES
            or not raw.endswith(b"\n")
            or raw == b"\n"
            or b"\r" in raw
            or raw.startswith(b"\xef\xbb\xbf")
        ):
            raise TaskBundleError("invalid bounded NDJSON line or incomplete LF")
        value = load_strict_json(raw[:-1])
        if type(value) is not dict or canonical_json_bytes(value) != raw[:-1]:
            raise TaskBundleError("canonical NDJSON object required")
        yield raw, value


def iter_frames(binary_stream):
    """Yield validated frame dicts, retaining at most one bounded raw object.

    Full validation requires exhausting the iterator through the footer and EOF.
    """
    header = None
    objects = chunks = journal = frames = wire_bytes = 0
    operations = set()
    current = None
    payload = bytearray()
    previous_key = None
    complete = False
    for raw, frame in _lines(binary_stream):
        if complete:
            raise TaskBundleError("extra data after footer")
        wire_bytes += len(raw)
        frames += 1
        if wire_bytes > MAX_WIRE_BYTES or frames > MAX_FRAMES:
            raise TaskBundleError("task wire capacity exceeded")
        kind = frame.get("frame_type")
        if header is None:
            if (
                kind != "HEADER"
                or set(frame) != HEADER_FIELDS
                or frame["manifest_version"] != "AG-TASK-EVIDENCE-2"
            ):
                raise TaskBundleError("unique exact first header required")
            scope = _scope(frame["scope"])
            for name, maximum in (
                ("cutoff_sequence", MAX_JOURNAL),
                ("object_count", MAX_OBJECTS),
                ("chunk_count", MAX_FRAMES),
                ("journal_count", MAX_JOURNAL),
                ("operation_count", MAX_OPERATIONS),
                ("snapshot_as_of", 2**53 - 1),
            ):
                integer(frame[name], maximum=maximum)
            if frame["journal_count"] != frame["cutoff_sequence"] or frame[
                "history_boundary"
            ] not in {"NEW_EMPTY", "LEGACY_WITH_GAPS"}:
                raise TaskBundleError("invalid header counts or history boundary")
            _text(frame["snapshot_id"], "snapshot_id")
            digest(frame["cutoff_head_digest"])
            digest(frame["bootstrap_digest"])
            header = frame
            index_root = index_seed(scope)
            wire_root = wire_seed(scope)
        elif kind == "OBJECT_CHUNK":
            if set(frame) != CHUNK_FIELDS:
                raise TaskBundleError("exact chunk fields required")
            k, ident = frame["object_kind"], _text(frame["object_id"], "object_id")
            if k not in OBJECT_LIMITS:
                raise TaskBundleError("unknown logical object kind")
            total = integer(frame["total_raw_bytes"], minimum=1, maximum=OBJECT_LIMITS[k])
            count = (total + CHUNK_BYTES - 1) // CHUNK_BYTES
            integer(frame["chunk_index"], maximum=count - 1)
            if type(frame["chunk_count"]) is not int or frame["chunk_count"] != count:
                raise TaskBundleError("invalid chunk count")
            digest(frame["object_digest"])
            if type(frame["data"]) is not str or len(frame["data"]) > 32768:
                raise TaskBundleError("encoded chunk capacity exceeded")
            part = b64url_decode(frame["data"])
            expected_size = (
                CHUNK_BYTES
                if frame["chunk_index"] < count - 1
                else total - CHUNK_BYTES * (count - 1)
            )
            if len(part) != expected_size:
                raise TaskBundleError("chunk raw size mismatch")
            metadata = (k, ident, count, total, frame["object_digest"])
            if current is None:
                if frame["chunk_index"] != 0 or (
                    previous_key is not None and (k, ident) <= previous_key
                ):
                    raise TaskBundleError("duplicate or unordered object")
                current = metadata
                payload.clear()
            if current != metadata or frame["chunk_index"] != len(payload) // CHUNK_BYTES:
                raise TaskBundleError("noncontiguous chunk metadata or index")
            payload.extend(part)
            chunks += 1
            if len(payload) == total:
                if sm3_b64url(bytes(payload)) != frame["object_digest"]:
                    raise TaskBundleError("object digest mismatch")
                if k == "typed_snapshot_metadata":
                    metadata_value = load_strict_json(bytes(payload))
                    if (
                        type(metadata_value) is dict
                        and metadata_value.get("metadata_profile")
                        == "AG-TASK-RUNTIME-OBSERVATION-1"
                    ):
                        if (
                            set(metadata_value)
                            != {"metadata_profile", "operation_id", "status", "receipt_status"}
                            or metadata_value["status"]
                            not in {"RESERVED", "EXECUTING", "UNKNOWN", "SUCCEEDED", "FAILED"}
                            or metadata_value["receipt_status"] not in {None, "PENDING", "READY"}
                        ):
                            raise TaskBundleError("invalid runtime observation")
                        op = _text(metadata_value["operation_id"], "operation_id")
                        if op in operations:
                            raise TaskBundleError("duplicate runtime operation")
                        operations.add(op)
                        if len(operations) > MAX_OPERATIONS:
                            raise TaskBundleError("operation count exceeded")
                objects += 1
                journal += k == "journal"
                if objects > MAX_OBJECTS:
                    raise TaskBundleError("object count exceeded")
                index_root = index_fold(index_root, frame)
                previous_key = (k, ident)
                current = None
        elif kind == "FOOTER":
            if set(frame) != FOOTER_FIELDS or current is not None:
                raise TaskBundleError("exact complete footer required")
            if (
                frame["object_index_root"] != index_root
                or frame["wire_root"] != wire_root
                or type(frame["before_footer_frames"]) is not int
                or frame["before_footer_frames"] != frames - 1
                or type(frame["before_footer_wire_bytes"]) is not int
                or frame["before_footer_wire_bytes"] != wire_bytes - len(raw)
            ):
                raise TaskBundleError("footer fold or counts mismatch")
            if (objects, chunks, journal, len(operations)) != (
                header["object_count"],
                header["chunk_count"],
                header["journal_count"],
                header["operation_count"],
            ):
                raise TaskBundleError("header object counts mismatch")
            complete = True
        else:
            raise TaskBundleError("unknown or repeated frame type")
        if not complete:
            wire_root = wire_fold(wire_root, frames - 1, raw)
        yield frame
    if not complete:
        raise TaskBundleError("INCOMPLETE task stream")


@dataclass(frozen=True, slots=True)
class CheckpointHistoryDescriptor:
    sha256: str
    wire_bytes: int
    checkpoint_count: int
    scope: JournalScope
    last_checkpoint_id: str | None
    last_sequence: int
    last_jws_digest: str | None
    source_path: str
    _identity: tuple[int, int, int, int, int]

    def __post_init__(self):
        if (
            type(self.scope) is not JournalScope
            or type(self.source_path) is not str
            or type(self._identity) is not tuple
            or len(self._identity) != 5
            or any(type(n) is not int for n in self._identity)
        ):
            raise TaskBundleError("deeply immutable history descriptor required")
        if (
            type(self.sha256) is not str
            or len(self.sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.sha256)
        ):
            raise TaskBundleError("invalid history SHA256")
        integer(self.wire_bytes, maximum=MAX_WIRE_BYTES)
        integer(self.checkpoint_count, maximum=MAX_JOURNAL)
        integer(self.last_sequence)
        if self.last_checkpoint_id is not None:
            _text(self.last_checkpoint_id, "checkpoint_id")
        if self.last_jws_digest is not None:
            digest(self.last_jws_digest)

    @contextmanager
    def open_readonly(self):
        """Revalidate identity and full digest around a consumer's readonly use."""
        with _open_public(self.source_path) as stream:
            if _identity(stream) != self._identity or _sha(stream) != self.sha256:
                raise TaskBundleError("history file identity or digest changed")
            stream.seek(0)
            yield stream
            if (
                _identity(stream) != self._identity
                or _sha(stream) != self.sha256
                or _path_identity(self.source_path) != self._identity
            ):
                raise TaskBundleError("history file changed during materialization")


def _identity(stream):
    stat = os.fstat(stream.fileno())
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _path_identity(path):
    stat = os.stat(path, follow_symlinks=False)
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@contextmanager
def _open_public(path):
    import stat

    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise TaskBundleError("regular local public history required")
        yield stream


def _sha(stream):
    stream.seek(0)
    result = hashlib.sha256()
    total = 0
    while True:
        raw = stream.read(65536)
        if not raw:
            break
        total += len(raw)
        if total > MAX_WIRE_BYTES:
            raise TaskBundleError("history capacity exceeded")
        result.update(raw)
    return result.hexdigest()


def _external(external_trust, external_pin):
    # Trust adapters may supply a decoded immutable object, or the explicit
    # {scope,audit_keys} subset with already constructed CheckpointTrust values.
    if type(external_trust) is dict:
        scope = _scope(external_trust["scope"])
        trust = external_trust["audit_keys"]
    else:
        scope = _scope(external_trust.scope)
        trust = external_trust.audit_keys
    if type(trust) is not tuple:
        raise TaskBundleError("immutable external checkpoint trust required")
    if (
        type(external_pin) is not dict
        or set(external_pin) != {"mode", "checkpoint_jws", "observed_at", "scope"}
        or _scope(external_pin["scope"]) != scope
    ):
        raise TaskBundleError("exact external pin and scope required")
    mode = external_pin["mode"]
    jws, observed = external_pin["checkpoint_jws"], external_pin["observed_at"]
    if mode == "UNKNOWN":
        if jws is not None or observed is not None:
            raise TaskBundleError("UNKNOWN pin must contain null checkpoint and time")
    elif mode in {"LATEST_OBSERVATION", "MINIMUM"}:
        verify_checkpoint(jws, trust=trust, expected_scope=scope)
        if observed is not None:
            integer(observed)
        elif mode == "LATEST_OBSERVATION":
            raise TaskBundleError("latest observation timestamp required")
    else:
        raise TaskBundleError("invalid external pin mode")
    return scope, trust


def _load_checkpoint_history(binary_stream, *, external_trust, external_pin):
    """Authenticate every unchanged original JWS from a trusted local file.

    UNKNOWN accepts a signed chain without promoting it to an external latest;
    the exporter must subsequently match its terminal to the local cached CP.
    """
    scope, trust = _external(external_trust, external_pin)
    try:
        path = str(Path(binary_stream.name).absolute())
        if str(Path(path).resolve()) != path:
            raise TaskBundleError("canonical nonsymlink history path required")
        start = _identity(binary_stream)
        if start != _path_identity(path):
            raise TaskBundleError("history path does not identify opened file")
    except (AttributeError, TypeError, OSError) as exc:
        raise TaskBundleError("trusted readonly local history file required") from exc
    import fcntl

    if fcntl.fcntl(binary_stream.fileno(), fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
        raise TaskBundleError("history handle must be readonly")
    binary_stream.seek(0)
    hashed = hashlib.sha256()
    wire = count = sequence = 0
    previous = last_id = None
    last_jws = None
    ids = set()
    for raw, value in _lines(binary_stream):
        wire += len(raw)
        count += 1
        if wire > MAX_WIRE_BYTES or count > MAX_JOURNAL or set(value) != {"checkpoint_jws"}:
            raise TaskBundleError("bounded exact checkpoint history required")
        jws = value["checkpoint_jws"]
        observed = verify_checkpoint(jws, trust=trust, expected_scope=scope)
        claims = observed.claims
        if (
            claims.checkpoint_id in ids
            or claims.sequence <= sequence
            or claims.previous_checkpoint_digest != previous
        ):
            raise TaskBundleError("checkpoint history order or previous mismatch")
        ids.add(claims.checkpoint_id)
        sequence, previous = claims.sequence, observed.jws_digest
        last_id, last_jws = claims.checkpoint_id, jws
        hashed.update(raw)
    if external_pin["mode"] != "UNKNOWN" and last_jws != external_pin["checkpoint_jws"]:
        raise TaskBundleError("history terminal does not equal original external pin")
    if (
        _identity(binary_stream) != start
        or _path_identity(path) != start
        or _sha(binary_stream) != hashed.hexdigest()
    ):
        raise TaskBundleError("history changed during validation")
    return CheckpointHistoryDescriptor(
        hashed.hexdigest(), wire, count, scope, last_id, sequence, previous, path, start
    )


def load_checkpoint_history(binary_stream, *, external_trust, external_pin):
    """Return a readonly descriptor, or one public TaskBundleError failure."""
    try:
        return _load_checkpoint_history(
            binary_stream, external_trust=external_trust, external_pin=external_pin
        )
    except (ValueError, TypeError, KeyError, OSError, UnicodeError, InvalidSm2Signature) as exc:
        if isinstance(exc, TaskBundleError):
            raise
        raise TaskBundleError("invalid external checkpoint history") from exc
