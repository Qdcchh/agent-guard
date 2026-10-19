"""Run real pytest privately; publish only counts, never raw historical failure text."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path


def run(root, command, require_no_skips=False):
    root = Path(root).absolute()
    if any(path.is_symlink() for path in (root, *root.parents)) or root.exists():
        raise ValueError("private test output must be fresh and unlinked")
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    xml = root / "junit.xml"
    command = [*command, f"--junitxml={xml}", f"--basetemp={root / 'pytest'}"]
    cancelled = False
    process = None

    def cancel(_number, _frame):
        nonlocal cancelled
        cancelled = True
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)

    previous = {sig: signal.signal(sig, cancel) for sig in (signal.SIGTERM, signal.SIGINT)}
    started = time.monotonic()
    try:
        with (root / "native.log").open("xb") as log:
            os.fchmod(log.fileno(), 0o600)
            process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
            while True:
                try:
                    code = process.wait(timeout=20)
                    break
                except subprocess.TimeoutExpired:
                    if cancelled:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                        return 130
                    print(
                        f"Real test process running; elapsed {int(time.monotonic() - started)}s",
                        flush=True,
                    )
        if cancelled:
            return 130
        if not xml.is_file() or xml.is_symlink():
            print(f"Real test process exit={code}; JUnit missing", flush=True)
            return code or 1
        xml.chmod(0o600)
        cases = list(ET.parse(xml).getroot().iter("testcase"))
        counts = {
            "total": len(cases),
            "failed": sum(case.find("failure") is not None for case in cases),
            "errors": sum(case.find("error") is not None for case in cases),
            "skipped": sum(case.find("skipped") is not None for case in cases),
        }
        print(f"Real test process exit={code}; counts={counts}", flush=True)
        return code or int(
            not cases
            or counts["failed"]
            or counts["errors"]
            or (require_no_skips and counts["skipped"])
        )
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--require-no-skips", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a real pytest command is required")
    os.umask(0o077)
    try:
        return run(args.root, command, args.require_no_skips)
    except Exception:
        print("Private test runner failed; raw details withheld", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
