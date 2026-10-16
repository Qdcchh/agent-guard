"""Four-parameter public-input-only task evidence verifier."""

import argparse
import hashlib
import json
import os
import stat
import sys
from contextlib import ExitStack
from dataclasses import asdict, replace
from pathlib import Path

from agent_guard.evidence.task_bundle import MAX_WIRE_BYTES, TaskBundleError
from agent_guard.evidence.task_verify import verify_task_bundle


def _identity(stream):
    value = os.fstat(stream.fileno())
    if not stat.S_ISREG(value.st_mode):
        raise TaskBundleError("regular public input required")
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _hash(stream):
    stream.seek(0)
    digest = hashlib.sha256()
    total = 0
    while raw := stream.read(65536):
        total += len(raw)
        if total > MAX_WIRE_BYTES:
            raise TaskBundleError("public input capacity exceeded")
        digest.update(raw)
    stream.seek(0)
    return digest.hexdigest()


def _json(stream):
    """Incremental external document parser, with bounded primitive buffering.

    The independent file total is bounded. Trust adapter validates each DTO
    with the unchanged generic codec limits, rather than treating an entire
    historical catalog as a single generic logical object.
    """
    buffer, position, total = b"", 0, 0

    def peek():
        nonlocal buffer, position, total
        if position == len(buffer):
            buffer = stream.read(4096)
            position = 0
            total += len(buffer)
            if total > MAX_WIRE_BYTES:
                raise TaskBundleError("external input capacity exceeded")
        return buffer[position : position + 1]

    def take():
        nonlocal position
        char = peek()
        position += bool(char)
        return char

    def space():
        while peek() in (b" ", b"\n", b"\r", b"\t"):
            take()

    def parse(depth=0):
        space()
        if depth > 64:
            raise TaskBundleError("external input depth exceeded")
        char = take()
        if char in (b"{", b"["):
            result = {} if char == b"{" else []
            closing = b"}" if char == b"{" else b"]"
            space()
            if peek() == closing:
                take()
                return result
            while True:
                if char == b"{":
                    key = parse(depth + 1)
                    if type(key) is not str or key in result:
                        raise TaskBundleError("duplicate or invalid external key")
                    space()
                    if take() != b":":
                        raise TaskBundleError("external object separator required")
                    result[key] = parse(depth + 1)
                else:
                    if len(result) >= 200000:
                        raise TaskBundleError("external array capacity exceeded")
                    result.append(parse(depth + 1))
                space()
                separator = take()
                if separator == closing:
                    return result
                if separator != b",":
                    raise TaskBundleError("external delimiter required")
                space()
        raw = bytearray(char)
        if char == b'"':
            escape = False
            while True:
                current = take()
                if not current:
                    raise TaskBundleError("incomplete external string")
                raw.extend(current)
                if len(raw) > 65536:
                    raise TaskBundleError("external string capacity exceeded")
                if current == b'"' and not escape:
                    break
                escape = current == b"\\" and not escape
        else:
            while peek() and peek() not in (b" ", b"\n", b"\r", b"\t", b",", b"]", b"}"):
                raw.extend(take())
                if len(raw) > 20:
                    raise TaskBundleError("external scalar capacity exceeded")
        from agent_guard.contracts.encoding import load_strict_json

        return load_strict_json(bytes(raw))

    value = parse()
    space()
    if peek():
        raise TaskBundleError("external trailing data")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bundle", "trust", "external-pin", "report"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        paths = {
            name: Path(getattr(args, name)).absolute()
            for name in ("bundle", "trust", "external_pin", "report")
        }
        if len(set(paths.values())) != 4 or any(str(p.resolve()) != str(p) for p in paths.values()):
            raise TaskBundleError("four distinct nonsymlink paths required")
        with ExitStack() as stack:
            streams, identities, hashes = {}, {}, {}
            for name in ("bundle", "trust", "external_pin"):
                fd = os.open(paths[name], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                stream = stack.enter_context(os.fdopen(fd, "rb"))
                streams[name] = stream
                identities[name], hashes[name] = _identity(stream), _hash(stream)
            if len({row[:2] for row in identities.values()}) != 3:
                raise TaskBundleError("distinct public input identities required")
            report = verify_task_bundle(
                streams["bundle"], _json(streams["trust"]), _json(streams["external_pin"])
            )
            for name, stream in streams.items():
                path_stat = os.stat(paths[name], follow_symlinks=False)
                identity = (
                    path_stat.st_dev,
                    path_stat.st_ino,
                    path_stat.st_size,
                    path_stat.st_mtime_ns,
                    path_stat.st_ctime_ns,
                )
                if (
                    identity != identities[name]
                    or _identity(stream) != identities[name]
                    or _hash(stream) != hashes[name]
                ):
                    raise TaskBundleError("public input changed during verification")
            encoded = (
                json.dumps(
                    asdict(replace(report, input_sha256=hashes)),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("ascii")
                + b"\n"
            )
            fd = os.open(
                paths["report"], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            try:
                with os.fdopen(fd, "wb") as out:
                    out.write(encoded)
                    out.flush()
                    os.fsync(out.fileno())
            except BaseException:
                paths["report"].unlink()
                raise
        return 0
    except (ValueError, TypeError, KeyError, OSError, UnicodeError, RecursionError):
        print("Task evidence verification failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
