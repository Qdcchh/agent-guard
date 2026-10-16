"""Independent OpenSSL Ed25519 check of the public FROST fixture."""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main(path: Path) -> None:
    vector = json.loads(path.read_text(encoding="utf-8"))
    assert vector["test_only"] is True
    assert vector["algorithm"] == "FROST-Ed25519/2-of-3"
    message = b"AGENT-GUARD-THRESHOLD-ACTION-V1\n" + json.dumps(
        vector["action"], separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert hashlib.sha256(message).hexdigest() == vector["message_sha256"]
    public = bytes.fromhex(vector["group_public_key_hex"])
    signature = bytes.fromhex(vector["signature_hex"])
    assert len(public) == 32 and len(signature) == 64
    # RFC 8410 Ed25519 SubjectPublicKeyInfo prefix.
    spki = bytes.fromhex("302a300506032b6570032100") + public
    with tempfile.TemporaryDirectory(prefix="agent-guard-threshold-vector-") as temp:
        directory = Path(temp)
        (directory / "pub.der").write_bytes(spki)
        (directory / "sig.bin").write_bytes(signature)
        (directory / "msg.bin").write_bytes(message)
        command = [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-keyform",
            "DER",
            "-inkey",
            str(directory / "pub.der"),
            "-rawin",
            "-sigfile",
            str(directory / "sig.bin"),
            "-in",
            str(directory / "msg.bin"),
        ]
        good = subprocess.run(command, capture_output=True, text=True, check=False)
        assert good.returncode == 0, good.stderr
        (directory / "msg.bin").write_bytes(message + b"x")
        bad = subprocess.run(command, capture_output=True, text=True, check=False)
        assert bad.returncode != 0
    print("OpenSSL Ed25519 public vector verification and tamper rejection passed")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
