"""Evidence gates for fixed presentation scenarios; no runtime security substitutes."""

import hashlib
import json
from pathlib import Path

import pytest

from tools import teacher_demo_scenarios as scenarios


def fixture(tmp_path, scenario="stolen-token"):
    folder = tmp_path
    (folder / "test-results").mkdir()
    (folder / "tests-snapshot/integration").mkdir(parents=True)
    (folder / "tests-snapshot/integration/test_a33_scenarios.py").write_text("assert True\n")
    digest = hashlib.sha256(
        (folder / "tests-snapshot/integration/test_a33_scenarios.py").read_bytes()
    ).hexdigest()
    (folder / "test-snapshot-sha256.json").write_text(
        json.dumps({"integration/test_a33_scenarios.py": digest})
    )
    (folder / "native-junit-summary.json").write_text(json.dumps({"native_exit": 0}))
    (folder / "cleanup.json").write_text(
        json.dumps({"resources_remaining": 0, "exact_removed_fullIDs": ["owned-id"]})
    )
    (folder / "scenario-native-exit.json").write_text(
        json.dumps({"native_exit": 0, "actual_wait": True})
    )
    name = scenarios.SPECS[scenario][4][0]
    (folder / "test-results/registration-tls.xml").write_text(
        '<testsuites><testsuite><testcase classname="tests.integration.test_a33_scenarios" name="'
        + name
        + '" /></testsuite></testsuites>'
    )
    return folder


def test_evidence_is_allowlisted_and_history_explicit(tmp_path):
    folder = fixture(tmp_path)
    actual = scenarios.result(folder, "stolen-token", historical=True)
    assert actual["mode"] == "history_replay"
    assert actual["total"] == 1 and actual["budget"] is None
    assert actual["evidence"]["snapshot_verified"] is True
    assert str(Path(tmp_path)) not in json.dumps(actual)


@pytest.mark.parametrize("damage", ["native", "snapshot", "missing", "failed", "cleanup"])
def test_incomplete_evidence_is_never_success(tmp_path, damage):
    folder = fixture(tmp_path)
    if damage == "native":
        (folder / "native-junit-summary.json").write_text('{"native_exit": 2}')
    elif damage == "snapshot":
        (folder / "tests-snapshot/integration/test_a33_scenarios.py").write_text("changed")
    elif damage == "missing":
        (folder / "test-results/registration-tls.xml").write_text("<testsuites/>")
    elif damage == "failed":
        xml = folder / "test-results/registration-tls.xml"
        xml.write_text(xml.read_text().replace(" />", "><failure>SECRET</failure></testcase>"))
    else:
        (folder / "cleanup.json").write_text('{"resources_remaining": 1}')
    with pytest.raises(ValueError):
        scenarios.result(folder, "stolen-token")


def test_deadline_uses_native_kill_and_wait(tmp_path):
    import subprocess
    import sys
    import time
    from types import SimpleNamespace

    from deploy.demo.supervisor import Owner

    class Bounded(scenarios.DeadlineCalls, Owner):
        pass

    ident = "95e85a87-2730-47b6-aa59-c0b33a9799da"
    owner = Bounded(
        SimpleNamespace(
            run_id=ident,
            owner_id="test-only",
            evidence=str(tmp_path / "run"),
            mode="wheel",
            capacity_items=1,
        )
    )
    owner.deadline = time.monotonic() + 0.1
    with pytest.raises(subprocess.TimeoutExpired):
        owner.call([sys.executable, "-c", "import time; time.sleep(10)"])
    native = json.loads((owner.root / "0001-native.json").read_text())
    assert native["timed_out"] is True
    assert type(native["native_exit"]) is int and native["native_exit"] != 0
