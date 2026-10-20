"""Package the committed source tree, preserving executable modes and symlinks."""

import argparse
import hashlib
import json
import stat
import subprocess
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def build(output):
    if git("diff", "--name-only", "HEAD"):
        raise SystemExit("Commit tracked changes first; the ZIP must match an exact commit.")
    commit = git("rev-parse", "HEAD")
    output.parent.mkdir(parents=True, exist_ok=True)
    prefix = "coseal-full/"
    subprocess.run(
        ["git", "archive", "--format=zip", "--prefix=" + prefix, "--output=" + str(output), commit],
        cwd=REPO,
        check=True,
    )
    with zipfile.ZipFile(output, "a", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(prefix + "START-HERE.md", archive.read(prefix + "deploy/full/README.md"))
        links = {}
        manifest = []
        for item in archive.infolist():
            if item.is_dir():
                continue
            relative = item.filename.removeprefix(prefix)
            data = archive.read(item)
            if stat.S_ISLNK(item.external_attr >> 16):
                links[relative] = data.decode("utf-8")
            else:
                manifest.append(hashlib.sha256(data).hexdigest() + "  " + relative)
        info = {
            "commit": commit,
            "source_url": "https://github.com/Qdcchh/agent-guard/tree/" + commit,
            "edition": "full demo source; not production deployment or offline images",
            "history": "Runtime evidence and credentials excluded; generate fresh on server.",
            "symlinks": links,
            "checksum_note": "SHA256SUMS covers regular files; symlink targets are listed here.",
        }
        encoded = (json.dumps(info, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        archive.writestr(prefix + "BUILD-INFO.json", encoded)
        manifest.append(hashlib.sha256(encoded).hexdigest() + "  BUILD-INFO.json")
        archive.writestr(prefix + "SHA256SUMS", "\n".join(sorted(manifest)) + "\n")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        digest + "  " + output.name + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "zip": str(output),
                "bytes": output.stat().st_size,
                "commit": commit,
                "sha256": digest,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=REPO.parent / "CoSeal-完整版部署包-20261020.zip"
    )
    args = parser.parse_args()
    build(args.output.resolve())


if __name__ == "__main__":
    main()
