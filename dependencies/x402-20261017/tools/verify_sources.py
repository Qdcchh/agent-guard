#!/usr/bin/env python3
"""Verify vendored FiatTokenV2_2 compile inputs against SOURCES.lock.json.

Circle files are checked with their upstream git blob SHA-1 (exactly the value
listed in the GitHub tree API for the pinned commit), OpenZeppelin files with
plain SHA-256. Exits non-zero and lists every mismatch.
"""

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEPS = os.path.dirname(HERE)
MANIFEST = os.path.join(DEPS, "SOURCES.lock.json")


def git_blob_sha1(data: bytes) -> str:
    digest = hashlib.sha1()
    digest.update(b"blob %d\0" % len(data))
    digest.update(data)
    return digest.hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    with open(MANIFEST, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    failures = []
    checked = 0
    for entry in manifest["circle"]["files"]:
        path = os.path.join(DEPS, "stablecoin-evm", entry["path"])
        actual = git_blob_sha1(open(path, "rb").read())
        checked += 1
        if actual != entry["gitBlobSha1"]:
            failures.append(f"{path}: git blob {actual} != {entry['gitBlobSha1']}")
    for entry in manifest["openzeppelin"]["files"]:
        path = os.path.join(DEPS, entry["path"])
        actual = sha256(open(path, "rb").read())
        checked += 1
        if actual != entry["sha256"]:
            failures.append(f"{path}: sha256 {actual} != {entry['sha256']}")

    if failures:
        print("SOURCE VERIFICATION FAILED", file=sys.stderr)
        for failure in failures:
            print("  " + failure, file=sys.stderr)
        return 1

    print(
        f"verified {checked} source files against SOURCES.lock.json "
        f"(circlefin/stablecoin-evm@405efc1, @openzeppelin/contracts 3.4.2)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
