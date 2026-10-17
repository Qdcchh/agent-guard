"""Independently check a public COSM2 vector using OpenSSL 3 (no dependencies)."""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FIELDS = {"public_key_spki_b64url", "message_b64url", "signature_rs_hex"}
SPKI_PREFIX = bytes.fromhex("3059301306072a8648ce3d020106082a811ccf5501822d03420004")
ORDER = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123
DEFAULT_VECTOR = Path(__file__).resolve().parents[1] / "tests/cosm2-public-vector.json"


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def decode_url(value: object) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("expected nonempty unpadded base64url string")
    raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if base64.urlsafe_b64encode(raw).decode().rstrip("=") != value:
        raise ValueError("noncanonical base64url")
    return raw


def load_vector(path: Path) -> tuple[bytes, bytes, bytes]:
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("vector exceeds 2 MiB limit")
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if not isinstance(data, dict) or set(data) != FIELDS:
        raise ValueError("vector must contain exactly the three B1 public fields")
    pub = decode_url(data["public_key_spki_b64url"])
    message = decode_url(data["message_b64url"])
    if len(pub) != len(SPKI_PREFIX) + 64 or not pub.startswith(SPKI_PREFIX):
        raise ValueError("expected canonical uncompressed SM2 SPKI DER")
    signature = data["signature_rs_hex"]
    if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-fA-F]{128}", signature):
        raise ValueError("signature must be 64-byte r||s hex")
    raw = bytes.fromhex(signature)
    integers = []
    for offset in (0, 32):
        value = int.from_bytes(raw[offset : offset + 32], "big")
        if not 1 <= value < ORDER:
            raise ValueError("signature scalar out of range")
        encoded = value.to_bytes((value.bit_length() + 7) // 8, "big")
        if encoded[0] & 128:
            encoded = b"\0" + encoded
        integers.append(b"\x02" + bytes([len(encoded)]) + encoded)
    body = b"".join(integers)
    return pub, message, b"\x30" + bytes([len(body)]) + body


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)


def find_openssl(explicit: str | None) -> str:
    candidates = (
        [explicit]
        if explicit
        else [
            "/opt/homebrew/opt/openssl@3/bin/openssl",
            "/usr/local/opt/openssl@3/bin/openssl",
            shutil.which("openssl"),
        ]
    )
    for candidate in candidates:
        if not candidate:
            continue
        try:
            result = run([candidate, "version"])
        except OSError:
            continue
        if result.returncode == 0 and re.match(r"OpenSSL 3\.", result.stdout):
            return candidate
    raise ValueError("OpenSSL 3 not found; provide --openssl /path/to/openssl")


def clean_rejection_stderr(stderr: str) -> bool:
    """Some OpenSSL 3 builds emit this specific EVP error for an invalid SM2 signature."""
    return all(
        re.fullmatch(
            r"[0-9A-Fa-f]+:error:030000EA:digital envelope routines:"
            r"EVP_DigestVerifyFinal:provider signature failure:"
            r"[^:\r\n]+:[0-9]+:SM2 digest_verify_final:",
            line,
        )
        for line in stderr.splitlines()
    )


def check(openssl: str, vector: tuple[bytes, bytes, bytes]) -> None:
    pub, message, signature = vector
    with tempfile.TemporaryDirectory(prefix="cosm2-vector-") as directory:
        root = Path(directory)
        encoded = base64.b64encode(pub).decode()
        pem = "-----BEGIN PUBLIC KEY-----\n"
        pem += "\n".join(encoded[i : i + 64] for i in range(0, len(encoded), 64))
        (root / "pub.pem").write_text(pem + "\n-----END PUBLIC KEY-----\n", encoding="ascii")
        (root / "msg.bin").write_bytes(message)
        (root / "sig.der").write_bytes(signature)
        command = [
            openssl,
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(root / "pub.pem"),
            "-rawin",
            "-in",
            str(root / "msg.bin"),
            "-sigfile",
            str(root / "sig.der"),
            "-digest",
            "sm3",
            "-pkeyopt",
            "distid:1234567812345678",
        ]
        result = run(command)
        if (
            result.returncode != 0
            or result.stdout.strip() != "Signature Verified Successfully"
            or result.stderr.strip()
        ):
            raise ValueError("positive verification failed or OpenSSL execution error")
        print("positive: Signature Verified Successfully (exit 0)")
        (root / "msg.bin").write_bytes(bytes([message[0] ^ 1]) + message[1:])
        result = run(command)
        # OpenSSL pkeyutl returns 1 for a normal invalid signature. Any other
        # outcome (including unrecognized provider/key/I/O errors) is an error.
        if (
            result.returncode != 1
            or result.stdout.strip() != "Signature Verification Failure"
            or not clean_rejection_stderr(result.stderr)
        ):
            raise ValueError("tampered message was not cleanly rejected; OpenSSL execution error")
        print("negative: Signature Verification Failure (exit 1; exactly one byte flipped)")
    print("PASS: public vector checked with OpenSSL 3 / SM3 / fixed distid")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vector", nargs="?", type=Path, default=DEFAULT_VECTOR)
    parser.add_argument("--openssl", help="explicit OpenSSL 3 executable (no fallback)")
    args = parser.parse_args()
    try:
        vector = load_vector(args.vector)
        openssl = find_openssl(args.openssl)
        print(f"OpenSSL: {openssl}")
        check(openssl, vector)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # Do not echo public-file contents or subprocess diagnostics: unexpected
        # inputs might contain secrets despite the public-vector contract.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
