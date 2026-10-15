"""Independent CLI processes receive public files only."""

import hashlib
import json
import os
import subprocess
import sys

import pytest

from tests.fixtures.a32_offline import TOOLS, material
from tests.unit.test_task_evidence_verify import verify


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("state", ["READY", "PENDING", "UNKNOWN", "FAILED"])
def test_offline_real_signed_task_four_tools_counters(state, tool, round):
    value = material(
        terminal=state != "UNKNOWN",
        publish=state in {"READY", "FAILED"},
        tool=tool,
        failed=state == "FAILED",
    )
    report = verify(value)
    assert len(report.grant_counters) == 3
    for row in report.grant_counters:
        assert row["amount_reserved"] == (value["amount"] if state == "UNKNOWN" else 0)
        assert row["amount_settled"] == (0 if state in {"UNKNOWN", "FAILED"} else value["amount"])
        assert row["calls_reserved"] == (1 if state == "UNKNOWN" else 0)
        assert row["calls_settled"] == (
            value["base_calls"] if state in {"UNKNOWN", "FAILED"} else 1 + value["base_calls"]
        )


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("case", ["valid", "UNKNOWN", "badbundle", "missingtrust", "overwrite"])
def test_verify_cli_source_wheel_no_network_trust_separation(tmp_path, round, case):
    value = material(mode="UNKNOWN" if case == "UNKNOWN" else "LATEST_OBSERVATION")
    files = {name: tmp_path / name for name in ("bundle", "trust", "pin", "report")}
    files["bundle"].write_bytes(value["bundle"] + (b"extra\n" if case == "badbundle" else b""))
    files["trust"].write_text(json.dumps({} if case == "missingtrust" else value["trust"]))
    files["pin"].write_text(json.dumps(value["pin"]))
    before = {
        n: hashlib.sha256(files[n].read_bytes()).hexdigest() for n in ("bundle", "trust", "pin")
    }
    for name in ("bundle", "trust", "pin"):
        files[name].chmod(0o400)
    if case == "overwrite":
        files["report"].write_bytes(b"existing")
    command = [
        sys.executable,
        "-m",
        "agent_guard.evidence.verify_cli",
        "--bundle",
        str(files["bundle"]),
        "--trust",
        str(files["trust"]),
        "--external-pin",
        str(files["pin"]),
        "--report",
        str(files["report"]),
    ]
    # In source mode only the explicit immutable snapshot package path is
    # needed. The wheel runner supplies no PYTHONPATH and cannot see source.
    environment = {"PATH": os.defpath}
    import agent_guard

    package = str(next(iter(agent_guard.__path__)))
    if "site-packages" not in package:
        environment["PYTHONPATH"] = str(__import__("pathlib").Path(package).parent)
    child = subprocess.run(command, cwd=tmp_path, env=environment, capture_output=True, timeout=300)
    assert child.returncode == (0 if case in {"valid", "UNKNOWN"} else 2), child.stderr
    assert before == {n: hashlib.sha256(files[n].read_bytes()).hexdigest() for n in before}
    if child.returncode == 0:
        report = json.loads(files["report"].read_bytes())
        assert report["input_sha256"] == {
            "bundle": before["bundle"],
            "trust": before["trust"],
            "external_pin": before["pin"],
        }
        assert files["report"].stat().st_mode & 0o777 == 0o600
        assert report["current_auth"] == "UNKNOWN"
    elif case == "overwrite":
        assert files["report"].read_bytes() == b"existing"
    else:
        assert not files["report"].exists()
