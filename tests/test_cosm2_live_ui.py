"""Session provenance and fixed COSM2 server action, without running Docker."""

import io
import json
import uuid

from tests.test_cosm2_desktop import payload
from tools import teacher_demo_server as demo


def test_installed_launcher_is_ready_missing_dependency_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "REPO", tmp_path)
    app = demo.DemoApp()
    assert app.state()["cosign_ready"] is False
    (tmp_path / "tools").mkdir()
    for name in ("cosm2_gateway_demo.py", "cosm2_desktop.py"):
        (tmp_path / "tools" / name).touch()
    assert app.state()["cosign_ready"] is True
    assert app.state()["cosign"] is None


def test_new_session_keeps_saved_replay_and_live_job_has_original_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "REPO", tmp_path)
    folder = tmp_path / "artifacts/cosm2-gateway-demo-live" / str(uuid.uuid4())
    folder.mkdir(parents=True)
    data = payload(folder.name)
    (folder / "result.json").write_text(json.dumps(data))
    commands = []

    class Process:
        stdout = io.StringIO(f"结果目录： {folder}\n")

        def wait(self):
            return 0

    def launch(command, **kwargs):
        commands.append(command)
        return Process()

    app = demo.DemoApp(launcher=launch)
    assert app.state()["cosign"]["source"] == "saved-result"
    app.job = dict(action="cosm2-run", status="running", started=0)
    app._work("cosm2-run", None, None)
    state = app.state()
    assert state["job"]["status"] == "success"
    assert state["job"]["actual_wait"] is True
    assert state["cosign"]["source"] == "current-run"
    assert state["cosign"]["run_id"] == folder.name
    assert state["cosign"]["completed_at"] == data["completed_at"]
    assert commands[0][-1] == str(tmp_path / "tools/cosm2_desktop.py")
    assert demo.DemoApp().state()["cosign"]["source"] == "saved-result"


def test_cosm2_action_exclusivity_uses_existing_job_gate():
    app = demo.DemoApp()
    app.job = dict(status="running")
    assert app.start("cosm2-run") is False


def test_job_cannot_promote_old_result_to_live(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "REPO", tmp_path)
    folder = tmp_path / "artifacts/cosm2-gateway-demo-live" / str(uuid.uuid4())
    folder.mkdir(parents=True)
    data = payload(folder.name)
    (folder / "result.json").write_text(json.dumps(data))

    class Process:
        stdout = io.StringIO(f"结果目录： {folder}\n")

        def wait(self):
            return 0

    app = demo.DemoApp(launcher=lambda *a, **k: Process())
    app.job = dict(action="cosm2-run", status="running", started=data["completed_at"] + 10)
    app._work("cosm2-run", None, None)
    assert app.state()["job"]["status"] == "failed"
    assert app.state()["cosign"]["source"] == "saved-result"


def test_bad_historical_folder_does_not_hide_valid_saved_result(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "REPO", tmp_path)
    root = tmp_path / "artifacts/cosm2-gateway-demo-live"
    good, bad = root / str(uuid.uuid4()), root / str(uuid.uuid4())
    good.mkdir(parents=True)
    bad.mkdir()
    (good / "result.json").write_text(json.dumps(payload(good.name)))
    (bad / "result.json").write_text('{"private":"INVALID_TEST_ONLY"}')
    result, status = demo.cosm2_saved_state()
    assert result["run_id"] == good.name
    assert "1 份未通过格式校验" in status
    assert "INVALID_TEST_ONLY" not in json.dumps(result)
