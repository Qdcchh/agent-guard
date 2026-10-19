"""Fetch only the fixed public encrypted asset; this process never receives its key."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from tools.pr9_capacity_transport import (
    BLOCK,
    load_json,
    no_links,
    private_directory,
    private_write,
    unique_object,
    validate_manifest,
    validate_metadata,
)

REPOSITORY = "Qdcchh/agent-guard"
ASSET_NAME = "pr9-native10000-r6.aesgcm"
RELEASE_TAG = "ci-capacity-inputs-20261018-r6-v1"


def request(url, accept):
    # Public ciphertext needs no token. Never forward an Authorization header
    # across GitHub's redirect to its release-asset storage.
    return Request(url, headers={"Accept": accept, "User-Agent": "agent-guard-capacity-ci/1"})


def fetch(manifest_path, metadata_path, output_root, *, opener=urlopen):
    manifest = load_json(manifest_path)
    validate_manifest(manifest)
    metadata = load_json(metadata_path, 16384)
    validate_metadata(metadata, manifest)
    locator = metadata["asset"]
    if locator["status"] != "FIXED_ASSET":
        raise ValueError("encrypted asset has not been published")
    asset_id = locator["id"]
    api_url = f"https://api.github.com/repos/{REPOSITORY}/releases/assets/{asset_id}"
    with opener(request(api_url, "application/vnd.github+json"), timeout=30) as response:
        raw = response.read(1048577)
    if len(raw) > 1048576:
        raise ValueError("oversized asset metadata")
    asset = json.loads(raw, object_pairs_hook=unique_object)
    expected_url = f"https://github.com/{REPOSITORY}/releases/download/{RELEASE_TAG}/{ASSET_NAME}"
    if (
        type(asset.get("id")) is not int
        or asset["id"] != asset_id
        or asset.get("name") != ASSET_NAME
        or type(asset.get("size")) is not int
        or asset["size"] != metadata["cipher_bytes"]
        or asset.get("state") != "uploaded"
        or asset.get("browser_download_url") != expected_url
    ):
        raise ValueError("fixed asset identity differs")
    root = no_links(output_root)
    if root.exists():
        raise ValueError("download output must be fresh")
    root = private_directory(root)
    try:
        path = root / "ciphertext.aesgcm"
        checksum, size = hashlib.sha256(), 0
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            with opener(request(expected_url, "application/octet-stream"), timeout=30) as response:
                if urlsplit(response.geturl()).scheme != "https":
                    raise ValueError("asset transport must remain HTTPS")
                while block := response.read(BLOCK):
                    size += len(block)
                    if size > metadata["cipher_bytes"]:
                        raise ValueError("asset exceeds fixed length")
                    stream.write(block)
                    checksum.update(block)
        if size != metadata["cipher_bytes"] or checksum.hexdigest() != metadata["cipher_sha256"]:
            raise ValueError("asset digest or length differs")
        receipt = {"asset_id": asset_id, "bytes": size, "sha256": checksum.hexdigest()}
        private_write(root / "fetch-receipt.json", json.dumps(receipt).encode() + b"\n")
        return receipt
    except BaseException:
        shutil.rmtree(root)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("manifest", "metadata", "output-root"):
        parser.add_argument("--" + field, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        receipt = fetch(args.manifest, args.metadata, args.output_root)
    except Exception:
        print("encrypted capacity asset unavailable or invalid", file=sys.stderr)
        return 1
    print(json.dumps(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
