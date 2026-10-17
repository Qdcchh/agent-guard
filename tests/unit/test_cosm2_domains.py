"""Public JSON stdio boundary refuses malformed inputs without token output."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "payload", [b'{"action":{},"action":{}}', b"[]", b'{"token":"secret-sentinel"}', b"X" * 65537]
)
def test_cli_strict_bounded_failure(payload):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_guard.cosign.authz_cli",
            "respond",
            "--share",
            "/missing/authz",
            "--trust",
            "/missing/public",
        ],
        input=payload,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2
    assert completed.stdout == b'{"code":"COSIGN_ABORTED","ok":false}\n'
    assert completed.stderr == b""
