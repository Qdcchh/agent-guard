"""Authenticated private transport of an immutable, publicly allowlisted capacity input.

Only safe JSON manifests belong in Git. Ciphertext and keys remain external.
No payload paths are parsed: the authenticated manifest defines file order/length.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import sys
import zlib
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FORMAT = "AG32-CAPACITY-TRANSPORT-1"
MAGIC = b"AG32-CAPACITY-CONTENT-1\n"
BLOCK = 1024 * 1024
MAX_MEMBERS = 110
MAX_PLAIN = 1024 * 1024 * 1024
MAX_GZIP = 256 * 1024 * 1024
HISTORICAL_BINDING_SHA256 = "4509d6f5620634104d51a682a58aacd7e6bff48c7939142f699600b31a9e2a45"
CLASSIFICATION = "QUALIFIED_UNAFFECTED_NATIVE_BUSINESS_REUSE_NOT_NEW_PG_EXPORT"
AAD_FIELDS = (
    "format",
    "dataset_id",
    "manifest_sha256",
    "framed_bytes",
    "framed_sha256",
    "gzip_bytes",
    "gzip_sha256",
    "compression",
    "nonce_hex",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def no_links(path):
    path = Path(path).absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("symbolic links are forbidden")
    return path


def safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("invalid member path")
    path = PurePosixPath(value)
    if (
        not path.parts
        or path.is_absolute()
        or path.as_posix() != value
        or any(
            part in (".", "..") or not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in path.parts
        )
    ):
        raise ValueError("invalid member path")
    return path


def regular(path):
    path = no_links(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("only single-link regular input files are allowed")
    return path


def open_regular(path):
    path = regular(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(descriptor)
        raise ValueError("only single-link regular input files are allowed")
    return os.fdopen(descriptor, "rb")


def read_limited(path, limit, exact=None):
    path = regular(path)
    if path.stat().st_size > limit:
        raise ValueError("input exceeds length limit")
    with open_regular(path) as stream:
        value = stream.read(limit + 1)
    if len(value) > limit or (exact is not None and len(value) != exact):
        raise ValueError("input length mismatch")
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def load_json(path, limit=2 * BLOCK):
    return json.loads(read_limited(path, limit), object_pairs_hook=unique_object)


def private_write(path, raw):
    path = no_links(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)


def private_directory(path):
    path = no_links(path)
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def sha_file(path):
    result = hashlib.sha256()
    with open_regular(path) as stream:
        while block := stream.read(BLOCK):
            result.update(block)
    return result.hexdigest()


def valid_sha(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("invalid SHA256")


def integer(value, maximum, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("invalid bounded length")


def validate_manifest(manifest):
    if set(manifest) != {"format", "dataset_id", "source_binding_sha256", "members", "binding"}:
        raise ValueError("unexpected manifest fields")
    if manifest["format"] != FORMAT or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,80}", manifest["dataset_id"]
    ):
        raise ValueError("unsupported manifest")
    valid_sha(manifest["source_binding_sha256"])
    members = manifest["members"]
    if not isinstance(members, list) or not 1 <= len(members) <= MAX_MEMBERS:
        raise ValueError("invalid member count")
    if manifest["dataset_id"] == "pr9-native10000-r6" and (
        len(members) != 110 or manifest["source_binding_sha256"] != HISTORICAL_BINDING_SHA256
    ):
        raise ValueError("fixed dataset requires the original110 binding")
    paths, total = set(), len(MAGIC) + 32
    for row in members:
        if set(row) != {"path", "role", "bytes", "sha256"}:
            raise ValueError("unexpected member fields")
        path = safe_relative(row["path"])
        if path in paths or any(parent in paths for parent in path.parents):
            raise ValueError("duplicate or overlapping member path")
        if any(path in previous.parents for previous in paths):
            raise ValueError("overlapping member path")
        paths.add(path)
        if not isinstance(row["role"], str) or not re.fullmatch(r"[a-z_]{1,64}", row["role"]):
            raise ValueError("invalid role")
        integer(row["bytes"], MAX_PLAIN)
        total += row["bytes"]
        valid_sha(row["sha256"])
    if total > MAX_PLAIN:
        raise ValueError("plaintext exceeds limit")
    if any(path.parts[0] == "source-binding.json" for path in paths):
        raise ValueError("reserved generated binding path")
    binding = manifest["binding"]
    if set(binding) != {
        "classification",
        "actual_installed_business_members",
        "journal_difference",
        "native_rejection",
    }:
        raise ValueError("unexpected binding fields")
    if binding["classification"] != CLASSIFICATION:
        raise ValueError("unsupported historical classification")
    if binding["journal_difference"] != {"condition": "if all(...) -> if grants and all(...)"}:
        raise ValueError("unexpected historical condition")
    if binding["native_rejection"] != {
        "exception": "TaskBundleError",
        "message": "complete material capacity exceeded",
    }:
        raise ValueError("unexpected rejection identity")
    installed = binding["actual_installed_business_members"]
    if not isinstance(installed, list) or not 1 <= len(installed) <= 256:
        raise ValueError("invalid historical installed manifest")
    installed_paths = set()
    prefix = "/e/source-venv/lib/python3.11/site-packages/"
    for row in installed:
        if set(row) != {"path", "sha256"} or not row["path"].startswith(prefix):
            raise ValueError("invalid historical installed member")
        relative = safe_relative(row["path"][len(prefix) :])
        if (
            relative.parts[0] != "agent_guard"
            or relative.suffix != ".py"
            or relative in installed_paths
        ):
            raise ValueError("invalid historical installed path")
        installed_paths.add(relative)
        valid_sha(row["sha256"])
    if sum(row["role"] == "formal_plan" for row in members) != 1:
        raise ValueError("exactly one formal plan is required")
    return total


def aad(metadata):
    return canonical({key: metadata[key] for key in AAD_FIELDS})


def validate_metadata(metadata, manifest):
    if set(metadata) != set(AAD_FIELDS) | {"cipher_bytes", "cipher_sha256", "asset"}:
        raise ValueError("unexpected transport fields")
    if metadata["format"] != FORMAT or metadata["dataset_id"] != manifest["dataset_id"]:
        raise ValueError("transport dataset mismatch")
    if metadata["manifest_sha256"] != digest(canonical(manifest)):
        raise ValueError("source manifest mismatch")
    if metadata["framed_bytes"] != validate_manifest(manifest):
        raise ValueError("declared plaintext length mismatch")
    integer(metadata["gzip_bytes"], MAX_GZIP, 1)
    integer(metadata["cipher_bytes"], MAX_GZIP + 16, 17)
    if metadata["cipher_bytes"] != metadata["gzip_bytes"] + 16:
        raise ValueError("cipher length mismatch")
    for key in ("manifest_sha256", "framed_sha256", "gzip_sha256", "cipher_sha256"):
        valid_sha(metadata[key])
    if not isinstance(metadata["nonce_hex"], str) or not re.fullmatch(
        "[0-9a-f]{24}", metadata["nonce_hex"]
    ):
        raise ValueError("invalid nonce")
    compression = metadata["compression"]
    if (
        set(compression) != {"algorithm", "level", "zlib_version"}
        or compression["algorithm"] != "gzip"
        or compression["level"] != 6
        or not isinstance(compression["zlib_version"], str)
    ):
        raise ValueError("unsupported compression metadata")
    asset = metadata["asset"]
    if set(asset) != {"status", "id"} or asset["status"] not in (
        "UNPUBLISHED_PENDING_ROOT",
        "FIXED_ASSET",
    ):
        raise ValueError("invalid asset locator")
    if asset["status"] == "FIXED_ASSET":
        integer(asset["id"], 2**63 - 1, 1)
    elif asset["id"] is not None:
        raise ValueError("pending asset has no ID")


def make_manifest(binding_path, historical_root, dataset_id):
    root = no_links(historical_root)
    binding_path = regular(binding_path)
    if not binding_path.is_relative_to(root):
        raise ValueError("binding escapes historical root")
    binding = load_json(binding_path)
    members, sources = [], []
    for row in binding["members"]:
        source = (
            (root / str(safe_relative(row["original_path"])))
            if "original_path" in row
            else (binding_path.parent / str(safe_relative(row["path"].removeprefix("/e/"))))
        )
        source = regular(source)
        if not source.is_relative_to(root):
            raise ValueError("source escapes historical root")
        if sha_file(source) != row["sha256"]:
            raise ValueError("historical source SHA mismatch")
        members.append(
            {
                "path": source.relative_to(root).as_posix(),
                "role": row["role"],
                "bytes": source.stat().st_size,
                "sha256": row["sha256"],
            }
        )
        sources.append(source)
    manifest = {
        "format": FORMAT,
        "dataset_id": dataset_id,
        "source_binding_sha256": sha_file(binding_path),
        "members": members,
        "binding": {
            "classification": binding["classification"],
            "actual_installed_business_members": binding["actual_installed_business_members"],
            "journal_difference": {"condition": binding["journal_difference"]["condition"]},
            "native_rejection": binding["native_rejection"],
        },
    }
    validate_manifest(manifest)
    return manifest, sources


def pack(binding_path, historical_root, output_root, dataset_id="pr9-native10000-r6"):
    """Create a new private package/key, never upload or persist plaintext in Git."""
    manifest, sources = make_manifest(binding_path, historical_root, dataset_id)
    root = private_directory(output_root)
    try:
        header = MAGIC + bytes.fromhex(digest(canonical(manifest)))
        plain_hash, gzip_hash = hashlib.sha256(), hashlib.sha256()
        plain_bytes, gzip_bytes = 0, 0
        compressor = zlib.compressobj(6, zlib.DEFLATED, 31)
        compressed_path = root / "compressed.private"
        descriptor = os.open(compressed_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)

            def emit(raw):
                nonlocal plain_bytes, gzip_bytes
                plain_hash.update(raw)
                plain_bytes += len(raw)
                encoded = compressor.compress(raw)
                gzip_hash.update(encoded)
                gzip_bytes += len(encoded)
                if gzip_bytes > MAX_GZIP:
                    raise ValueError("compressed input exceeds limit")
                stream.write(encoded)

            emit(header)
            for row, source in zip(manifest["members"], sources, strict=True):
                member_hash, size = hashlib.sha256(), 0
                with open_regular(source) as original:
                    while block := original.read(BLOCK):
                        size += len(block)
                        if size > row["bytes"]:
                            raise ValueError("source grew during pack")
                        member_hash.update(block)
                        emit(block)
                if size != row["bytes"] or member_hash.hexdigest() != row["sha256"]:
                    raise ValueError("source changed during pack")
            encoded = compressor.flush()
            stream.write(encoded)
            gzip_hash.update(encoded)
            gzip_bytes += len(encoded)
        if plain_bytes != validate_manifest(manifest) or gzip_bytes > MAX_GZIP:
            raise ValueError("content length mismatch")
        key, nonce = os.urandom(32), os.urandom(12)
        metadata = {
            "format": FORMAT,
            "dataset_id": dataset_id,
            "manifest_sha256": digest(canonical(manifest)),
            "framed_bytes": plain_bytes,
            "framed_sha256": plain_hash.hexdigest(),
            "gzip_bytes": gzip_bytes,
            "gzip_sha256": gzip_hash.hexdigest(),
            "compression": {"algorithm": "gzip", "level": 6, "zlib_version": zlib.ZLIB_VERSION},
            "nonce_hex": nonce.hex(),
        }
        ciphertext = AESGCM(key).encrypt(
            nonce, read_limited(compressed_path, MAX_GZIP), aad(metadata)
        )
        metadata.update(
            cipher_bytes=len(ciphertext),
            cipher_sha256=digest(ciphertext),
            asset={"status": "UNPUBLISHED_PENDING_ROOT", "id": None},
        )
        validate_metadata(metadata, manifest)
        private_write(root / "ciphertext.aesgcm", ciphertext)
        private_write(root / "key.bin", key)
        private_write(root / "source-manifest.json", canonical(manifest) + b"\n")
        private_write(root / "transport.json", canonical(metadata) + b"\n")
        compressed_path.unlink()
        return metadata
    except BaseException:
        shutil.rmtree(root)
        raise


def read_key(key_file=None, key_env=None):
    if (key_file is None) == (key_env is None):
        raise ValueError("exactly one private key source is required")
    if key_file is not None:
        path = regular(key_file)
        if stat.S_IMODE(path.stat().st_mode) != 0o600 or path.parent.stat().st_mode & 0o077:
            raise ValueError("key requires 0600 file in private directory")
        return read_limited(path, 32, exact=32)
    if not isinstance(key_env, str) or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key_env):
        raise ValueError("invalid key environment name")
    value = os.environ.pop(key_env, None)
    if not value:
        raise ValueError("capacity key unavailable")
    try:
        key = base64.b64decode(value, validate=True)
    except ValueError:
        raise ValueError("invalid key encoding") from None
    if len(key) != 32:
        raise ValueError("invalid key size")
    return key


def decompressed_blocks(compressed, metadata):
    decoder = zlib.decompressobj(31)
    total, checksum = 0, hashlib.sha256()
    for offset in range(0, len(compressed), BLOCK):
        remaining = compressed[offset : offset + BLOCK]
        while remaining:
            block = decoder.decompress(remaining, min(BLOCK, metadata["framed_bytes"] - total + 1))
            total += len(block)
            if total > metadata["framed_bytes"]:
                raise ValueError("decompressed input exceeds declared limit")
            checksum.update(block)
            if decoder.unused_data:
                raise ValueError("extra gzip stream or trailing bytes")
            remaining = decoder.unconsumed_tail
            if block:
                yield block
    if not decoder.eof or total != metadata["framed_bytes"]:
        raise ValueError("truncated decompressed input")
    if checksum.hexdigest() != metadata["framed_sha256"]:
        raise ValueError("plaintext SHA mismatch")


class ContentReader:
    def __init__(self, blocks):
        self.blocks = iter(blocks)
        self.buffer = bytearray()

    def take(self, count):
        while len(self.buffer) < count:
            try:
                self.buffer.extend(next(self.blocks))
            except StopIteration:
                raise ValueError("truncated member stream") from None
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result

    def finish(self):
        if self.buffer:
            raise ValueError("extra plaintext member data")
        try:
            next(self.blocks)
        except StopIteration:
            return
        raise ValueError("extra plaintext member data")


def rebuild_binding(manifest):
    """Reproduce the sole generated binding from validated public manifest fields."""
    validate_manifest(manifest)
    binding = dict(manifest["binding"])
    binding["members"] = [
        {
            "role": row["role"],
            "path": row["path"],
            "original_path": row["path"],
            "sha256": row["sha256"],
        }
        for row in manifest["members"]
    ]
    binding["formal_plan"] = next(
        row["path"] for row in manifest["members"] if row["role"] == "formal_plan"
    )
    binding["original_binding_sha256"] = manifest["source_binding_sha256"]
    binding["transport_manifest_sha256"] = digest(canonical(manifest))
    return binding


def unpack(
    manifest_path, metadata_path, ciphertext_path, output_root, *, key_file=None, key_env=None
):
    """Authenticate completely, validate bounded plaintext, then publish a ready root."""
    manifest = load_json(manifest_path)
    validate_manifest(manifest)
    metadata = load_json(metadata_path, 16 * 1024)
    validate_metadata(metadata, manifest)
    output_root = no_links(output_root)
    if output_root.exists():
        raise ValueError("output must be fresh")
    ciphertext = read_limited(ciphertext_path, MAX_GZIP + 16, exact=metadata["cipher_bytes"])
    if digest(ciphertext) != metadata["cipher_sha256"]:
        raise ValueError("cipher SHA mismatch")
    key = read_key(key_file, key_env)
    compressed = AESGCM(key).decrypt(
        bytes.fromhex(metadata["nonce_hex"]), ciphertext, aad(metadata)
    )
    del key, ciphertext
    if len(compressed) != metadata["gzip_bytes"] or digest(compressed) != metadata["gzip_sha256"]:
        raise ValueError("compressed SHA or length mismatch")
    root = private_directory(output_root)
    try:
        stage = private_directory(root / ".partial")
        reader = ContentReader(decompressed_blocks(compressed, metadata))
        if reader.take(len(MAGIC) + 32) != MAGIC + bytes.fromhex(metadata["manifest_sha256"]):
            raise ValueError("content header mismatch")
        for row in manifest["members"]:
            target = stage / str(safe_relative(row["path"]))
            # Every path is from the authenticated public allowlist, never the payload.
            for directory in reversed(target.parent.relative_to(stage).parents):
                if directory != Path("."):
                    (stage / directory).mkdir(exist_ok=True, mode=0o700)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            for directory in [target.parent, *target.parent.parents]:
                if directory == stage:
                    break
                directory.chmod(0o700)
            descriptor = os.open(
                target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            checksum, remaining = hashlib.sha256(), row["bytes"]
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                while remaining:
                    block = reader.take(min(BLOCK, remaining))
                    stream.write(block)
                    checksum.update(block)
                    remaining -= len(block)
            if checksum.hexdigest() != row["sha256"]:
                raise ValueError("member SHA mismatch")
        reader.finish()
        binding = rebuild_binding(manifest)
        private_write(stage / "source-binding.json", canonical(binding) + b"\n")
        ready = root / "historical-root"
        stage.rename(ready)
        return ready
    except BaseException:
        shutil.rmtree(root)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    packing = commands.add_parser("pack")
    for field in ("historical-binding", "historical-root", "output-root"):
        packing.add_argument("--" + field, required=True)
    packing.add_argument("--dataset-id", default="pr9-native10000-r6")
    unpacking = commands.add_parser("unpack")
    for field in ("manifest", "metadata", "ciphertext", "output-root"):
        unpacking.add_argument("--" + field, required=True)
    key = unpacking.add_mutually_exclusive_group(required=True)
    key.add_argument("--key-file")
    key.add_argument("--key-env")
    args = parser.parse_args()

    def cancelled(_number, _frame):
        raise KeyboardInterrupt

    previous_handler = signal.signal(signal.SIGTERM, cancelled)
    try:
        if args.command == "pack":
            pack(args.historical_binding, args.historical_root, args.output_root, args.dataset_id)
        else:
            unpack(
                args.manifest,
                args.metadata,
                args.ciphertext,
                args.output_root,
                key_file=args.key_file,
                key_env=args.key_env,
            )
    except (Exception, KeyboardInterrupt):
        # Never render a raw parser/crypto exception, input fragment or traceback.
        print("capacity transport failed; no input was released", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
