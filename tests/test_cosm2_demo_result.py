"""Strict B7 contract fixtures and missing-dependency behavior."""

import copy
import json
import uuid
from pathlib import Path

import pytest

from tools import teacher_demo_server as demo


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "REPO", tmp_path)
    folder = tmp_path / "artifacts/cosm2-gateway-demo-live" / str(uuid.uuid4())
    folder.mkdir(parents=True)
    data = {
        "run_id": folder.name,
        "passed": True,
        "completed_at": 1760000000,
        "scheme": "sm2-2p",
        "public_key_fingerprint": "0123456789abcdef",
        "orders": 1,
        "operations": 1,
        "approvals": 1,
        "resources_remaining": 0,
        "cases": [
            {"name": name, "passed": True, **expected}
            for name, expected in demo.COSM2_CASES.items()
        ],
        "timing_ms": {"round1": 1.2, "round2_with_checks": 2, "round3_with_verify": 3},
    }
    return folder, data


def store(folder, data):
    (folder / "result.json").write_text(json.dumps(data))


def test_saved_source_time_and_missing_runner(saved):
    folder, data = saved
    store(folder, data)
    result = demo.cosm2_result(folder)
    assert result["completed_at"] == 1760000000
    assert result["source"] == "saved-result"
    assert result["resources_remaining"] == 0
    assert demo.DemoApp().state()["cosign_ready"] is False
    assert demo.cosm2_saved_state()[0] == result


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(run_id=str(uuid.uuid4())),
        lambda d: d.update(orders=True),
        lambda d: d.update(resources_remaining=[]),
        lambda d: d.update(completed_at=True),
        lambda d: d.update(completed_at=0),
        lambda d: d.update(scheme="frost"),
        lambda d: d.update(public_key_fingerprint=1234567890123456),
        lambda d: d.update(secret_share="SECRET"),
        lambda d: d.update(passed=False),
        lambda d: d.update(orders=2),
        lambda d: d["timing_ms"].update(round1=float("nan")),
        lambda d: d["timing_ms"].update(round1=float("inf")),
        lambda d: d["timing_ms"].update(round1=True),
        lambda d: d["timing_ms"].update(round1=-1),
        lambda d: d["cases"].pop(),
        lambda d: d["cases"].__setitem__(1, copy.deepcopy(d["cases"][0])),
        lambda d: d["cases"][0].update(http_status=True),
        lambda d: d["cases"][4].update(refused_by="gateway"),
        lambda d: d["cases"][5].update(code="INVALID_SIGNATURE"),
    ],
)
def test_invalid_contract_unready(saved, mutate):
    folder, data = saved
    mutate(data)
    store(folder, data)
    with pytest.raises(ValueError):
        demo.cosm2_result(folder)
    assert demo.cosm2_saved_state()[0] is None


def test_duplicate_keys_and_boundary(saved):
    folder, data = saved
    store(folder, data)
    p = folder / "result.json"
    p.write_text(p.read_text().replace('"orders": 1', '"orders": 1, "orders": 1'))
    with pytest.raises(ValueError, match="duplicate"):
        demo.cosm2_result(folder)
    outside = folder.parents[1] / "other" / folder.name
    outside.mkdir(parents=True)
    store(outside, data)
    with pytest.raises(ValueError):
        demo.cosm2_result(outside)
    p.unlink()
    p.symlink_to(outside / "result.json")
    with pytest.raises(ValueError):
        demo.cosm2_result(folder)


def test_missing_no_arbitrary_pointer(saved):
    folder, _ = saved
    assert demo.cosm2_saved_state()[0] is None
    (folder.parent / "latest-run.txt").write_text("/etc/passwd")
    assert demo.cosm2_saved_state()[0] is None
    assert not Path(demo.REPO / "tools/cosm2_gateway_demo.py").exists()


def test_failed_case_keeps_failure_visible(saved):
    folder, data = saved
    data["passed"] = False
    data["cases"][0]["passed"] = False
    store(folder, data)
    result, status = demo.cosm2_saved_state()
    assert result["passed"] is False
    assert result["cases"][0]["passed"] is False
    assert "保存结果回放" in status
