"""Unit-only launcher lifecycle, fixed commands, and cleanup boundaries."""

import io
import json
import os
import subprocess
import uuid
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import pytest

from tools import cosm2_desktop as desktop
from tools.teacher_demo_server import COSM2_CASES


def payload(run_id):
    return dict(
        run_id=run_id,
        passed=True,
        completed_at=1760000000,
        scheme="sm2-2p",
        public_key_fingerprint="0123456789abcdef",
        orders=1,
        operations=1,
        approvals=1,
        resources_remaining=0,
        cases=[dict(name=name, passed=True, **expected) for name, expected in COSM2_CASES.items()],
        timing_ms=dict(round1=1.2, round2_with_checks=2, round3_with_verify=3),
    )


class FakeDocker:
    def __init__(self, image=True, wrong_owner=False):
        self.image = image
        self.wrong_owner = wrong_owner
        self.labels = {}
        self.removed = []
        self.inspected = []
        self.launcher = None

    def available(self):
        return True

    def image_exists(self, image):
        return self.image

    def image_arch(self, image):
        return "amd64"

    def network_create(self, name, labels):
        self.labels["owned-network"] = labels
        return "owned-network"

    def container_create_pg(self, image, name, network, alias, env_file, labels):
        assert os.stat(env_file).st_mode & 0o777 == 0o600
        self.labels["owned-pg"] = labels
        return "owned-pg"

    def container_start(self, container):
        assert container == "owned-pg"

    def exec_ready(self, container, user, database):
        return True

    def container_create_runner(self, image, name, network, env_file, labels, repo, result):
        assert os.stat(env_file).st_mode & 0o777 == 0o600
        assert "AGENT_GUARD_COSM2_DEMO_DSN=" in env_file.read_text()
        self.labels["owned-runner"] = labels
        return "owned-runner"

    def attach_runner(self, container, timeout):
        folder = self.launcher.demo_root / str(uuid.uuid4())
        folder.mkdir()
        (folder / "result.json").write_text(json.dumps(payload(folder.name)))
        return desktop.Attach(
            output=f"结果目录： /work/{desktop.DEMO_ROOT_REL}/{folder.name}\n".encode(),
            exit_code=0,
            timed_out=False,
        )

    def inspect_label(self, resource, resource_id, label):
        self.inspected.append(resource_id)
        return "different-owner" if self.wrong_owner else self.labels[resource_id][label]

    def remove_container(self, resource_id):
        self.removed.append(resource_id)

    def remove_network(self, resource_id):
        self.removed.append(resource_id)


def test_fixed_launcher_lifecycle_private_secrets_and_owned_cleanup(tmp_path):
    docker = FakeDocker()
    launcher = desktop.Launcher(tmp_path, docker=docker)
    docker.launcher = launcher
    output = io.StringIO()
    with redirect_stdout(output):
        assert launcher.run() == 0
    assert docker.removed == ["owned-runner", "owned-pg", "owned-network"]
    assert set(docker.inspected) == set(docker.labels)
    assert not list(launcher.scratch.glob("*.env"))
    assert launcher.password not in output.getvalue()
    assert "postgresql://" not in output.getvalue()
    assert "资源剩余 0" in output.getvalue()


def test_missing_image_does_not_build_or_create_resources(tmp_path):
    docker = FakeDocker(image=False)
    launcher = desktop.Launcher(tmp_path, docker=docker)
    with redirect_stderr(io.StringIO()):
        assert launcher.run() == 2
    assert docker.labels == {}
    assert not list(launcher.scratch.glob("*.env"))


def test_wrong_owner_never_removed_and_result_records_integer_cleanup_failure(tmp_path):
    docker = FakeDocker(wrong_owner=True)
    launcher = desktop.Launcher(tmp_path, docker=docker)
    docker.launcher = launcher
    with redirect_stdout(io.StringIO()):
        assert launcher.run() == 1
    assert docker.removed == []
    result = json.loads(next(launcher.demo_root.glob("*/result.json")).read_text())
    assert result["passed"] is False
    assert result["resources_remaining"] == 3


def test_runner_command_is_fixed_no_platform_pull_or_dsn(tmp_path):
    docker = desktop.Docker("docker")
    calls = []

    def capture(args, *a, **k):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=b"owned-id", stderr=b"")

    with patch.object(docker, "_capture", capture):
        docker.container_create_runner(
            "fixed",
            "owned",
            "owned-network",
            tmp_path / "private.env",
            {},
            tmp_path,
            tmp_path / "results",
        )
    args = calls[0]
    assert args[:3] == ["create", "--pull", "never"]
    assert "--platform" not in args
    assert args[-1] == "tools/cosm2_gateway_demo.py"
    assert not any("postgresql://" in value for value in args)
    assert any("readonly" in value for value in args)


def test_translate_rejects_arbitrary_paths_and_symlinks(tmp_path):
    launcher = desktop.Launcher(tmp_path, docker=FakeDocker())
    launcher._prepare_dirs()
    for folder in [
        "/etc/passwd",
        "/work/artifacts/cosm2-gateway-demo-live/../evil",
        "/work/artifacts/threshold-gateway-demo-live/" + str(uuid.uuid4()),
    ]:
        assert launcher._translate(("结果目录： " + folder).encode()) is None
    run_id = str(uuid.uuid4())
    (launcher.demo_root / run_id).symlink_to(tmp_path, target_is_directory=True)
    assert (
        launcher._translate(f"结果目录： /work/{desktop.DEMO_ROOT_REL}/{run_id}".encode()) is None
    )


def test_exact_result_rejects_unknown_and_duplicate_json(tmp_path):
    launcher = desktop.Launcher(tmp_path, docker=FakeDocker())
    folder = tmp_path / str(uuid.uuid4())
    folder.mkdir()
    result = payload(folder.name)
    result["secret_share"] = "TEST_ONLY"
    (folder / "result.json").write_text(json.dumps(result))
    with pytest.raises(desktop.DockerError):
        launcher._read_result(folder)
    result.pop("secret_share")
    raw = json.dumps(result).replace('"orders": 1', '"orders": 1, "orders": 1')
    (folder / "result.json").write_text(raw)
    with pytest.raises(desktop.DockerError):
        launcher._read_result(folder)


def test_timeout_keeps_failure_and_still_cleans_owned_resources(tmp_path):
    docker = FakeDocker()
    launcher = desktop.Launcher(tmp_path, docker=docker)
    docker.launcher = launcher
    docker.attach_runner = lambda *a: desktop.Attach(b"private raw output", 137, True)
    output = io.StringIO()
    with redirect_stderr(output):
        assert launcher.run() == 1
    assert "private raw output" not in output.getvalue()
    assert docker.removed == ["owned-runner", "owned-pg", "owned-network"]
    assert not list(launcher.scratch.glob("*.env"))
