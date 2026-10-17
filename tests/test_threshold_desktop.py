"""Focused tests for the Docker-hosted threshold desktop launcher.

The Docker boundary is mocked for lifecycle, ownership, secret-handling and
failure-path tests. One real end-to-end test runs the actual CLI on the host
Python interpreter with the existing runner image and a fresh, owned
PostgreSQL container, then proves the launcher removed every labelled
resource and secret file. No old regression suite is executed here.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools import threshold_desktop as desktop  # noqa: E402

RUNNER_IMAGE = "agent-guard-threshold-gateway-runner:20261017"
DEMO_ROOT = REPO / "artifacts" / "threshold-gateway-demo-live"
SCRATCH_ROOT = REPO / "artifacts" / "threshold-gateway-desktop"
LABEL_FILTER = "label=agent-guard.threshold-desktop"


def runner_image_present() -> bool:
    try:
        completed = subprocess.run(
            ["docker", "image", "inspect", RUNNER_IMAGE],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


class FakeDocker:
    """In-memory Docker boundary with the same method surface as desktop.Docker."""

    def __init__(
        self,
        *,
        available: bool = True,
        image: bool = True,
        arch: str = "amd64",
        cleanup_fail=(),
        label_override=None,
        build_fail: bool = False,
    ):
        self.calls: list[tuple] = []
        self.available_value = available
        self.image_value = image
        self.arch = arch
        self.cleanup_fail = set(cleanup_fail)
        self.label_override = dict(label_override or {})
        self.build_fail = build_fail
        self.containers: dict[str, dict] = {}
        self.network_labels: dict[str, dict] = {}
        self.labels_by_id: dict[str, dict] = {}
        self.removed: list[str] = []
        self.killed: list[str] = []
        self.build_args: dict[str, str] = {}
        self.attach_handler = None
        self._sequence = 0

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def _next_id(self, prefix):
        self._sequence += 1
        return f"{prefix}-{self._sequence:04d}"

    def available(self):
        self._record("available")
        return self.available_value

    def image_exists(self, image):
        self._record("image_exists", image)
        return self.image_value

    def image_arch(self, image):
        self._record("image_arch", image)
        return self.arch

    def local_image_refs(self, repository):
        self._record("local_image_refs", repository)
        return []

    def build_runner(self, dockerfile, context, build_args):
        self._record("build_runner", dockerfile, context, build_args)
        if self.build_fail:
            raise desktop.DockerError("docker_command_failed")
        self.build_args = dict(build_args)
        self.image_value = True

    def network_create(self, name, labels):
        self._record("network_create", name, labels)
        network_id = self._next_id("net")
        self.network_labels[network_id] = dict(labels)
        self.labels_by_id[network_id] = dict(labels)
        return network_id

    def container_create_pg(self, image, name, network, alias, env_file, labels):
        self._record("container_create_pg", image, name, network, alias, env_file, labels)
        container_id = self._next_id("pg")
        self._register(container_id, name, env_file, labels)
        return container_id

    def container_create_runner(
        self, image, name, network, env_file, labels, repo_mount, demo_mount
    ):
        self._record(
            "container_create_runner",
            image,
            name,
            network,
            env_file,
            labels,
            repo_mount,
            demo_mount,
        )
        container_id = self._next_id("run")
        self._register(container_id, name, env_file, labels)
        return container_id

    def _register(self, container_id, name, env_file, labels):
        self.containers[container_id] = {"name": name, "env_file": env_file, "labels": dict(labels)}
        self.labels_by_id[container_id] = dict(labels)

    def container_start(self, container_id):
        self._record("container_start", container_id)

    def exec_ready(self, container_id, user, database):
        self._record("exec_ready", container_id, user, database)
        return True

    def attach_runner(self, container_id, timeout):
        self._record("attach_runner", container_id, timeout)
        if self.attach_handler is None:
            return desktop.Attach(output=b"", exit_code=0, timed_out=False)
        return self.attach_handler(container_id)

    def container_exit_code(self, container_id):
        self._record("container_exit_code", container_id)
        return 0

    def inspect_label(self, resource, resource_id, label):
        self._record("inspect_label", resource, resource_id, label)
        if resource in self.label_override:
            return self.label_override[resource]
        return self.labels_by_id.get(resource_id, {}).get(label)

    def remove_container(self, container_id):
        self._record("remove_container", container_id)
        if "container" in self.cleanup_fail or container_id in self.cleanup_fail:
            raise desktop.DockerError("docker_command_failed")
        self.removed.append(container_id)
        self.labels_by_id.pop(container_id, None)

    def remove_network(self, network_id):
        self._record("remove_network", network_id)
        if "network" in self.cleanup_fail or network_id in self.cleanup_fail:
            raise desktop.DockerError("docker_command_failed")
        self.removed.append(network_id)
        self.labels_by_id.pop(network_id, None)

    def kill(self, resource_id):
        self.killed.append(resource_id)


def result_payload(run_id: str, passed: bool = True) -> dict:
    return {
        "demo": "threshold-gateway-purchase",
        "run_id": run_id,
        "profile": "AG-GUARD-THRESHOLD-APPROVAL-1",
        "passed": passed,
        "cases": [
            {
                "name": "missing-approval",
                "passed": True,
                "http_status": 401,
                "code": "APPROVAL_REQUIRED",
            },
            {"name": "valid-approval-one-order", "passed": passed, "http_status": 202},
        ],
        "operations": 1,
        "approvals": 1,
        "orders": 1,
        "budget": [],
        "resources_remaining": [],
        "limitations": [],
    }


class LauncherCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = (Path(self.temp.name) / "repo").resolve()
        (self.repo / "deploy" / "threshold-runner").mkdir(parents=True)
        (self.repo / "deploy" / "threshold-runner" / "Dockerfile").write_text("FROM scratch\n")
        self.fake = FakeDocker()

    def tearDown(self):
        self.temp.cleanup()

    def new_launcher(self, **kwargs):
        kwargs.setdefault("repo", self.repo)
        kwargs.setdefault("docker", self.fake)
        kwargs.setdefault("timeout", 30.0)
        return desktop.Launcher(**kwargs)

    def make_result(self, passed: bool = True):
        run_id = str(uuid.uuid4())
        folder = self.repo / desktop.DEMO_ROOT_REL / run_id
        folder.mkdir(parents=True, mode=0o700)
        (folder / "result.json").write_text(json.dumps(result_payload(run_id, passed)))
        return folder, run_id

    def attach_success(self, passed: bool = True):
        folder, run_id = self.make_result(passed)
        container = f"/work/artifacts/threshold-gateway-demo-live/{run_id}"

        def handler(container_id):
            env_text = self.fake.containers[container_id]["env_file"].read_text()
            self.assertIn("AGENT_GUARD_THRESHOLD_DEMO_DSN=", env_text)
            self.assertIn(self.launcher.password, env_text)
            return desktop.Attach(
                output=f"结果目录： {container}\n".encode(),
                exit_code=0,
                timed_out=False,
            )

        self.fake.attach_handler = handler
        if not hasattr(self, "launcher"):
            self.launcher = self.new_launcher()
        return folder

    def run_launcher(self, launcher=None):
        target = launcher or self.launcher
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = target.run()
        return code, out.getvalue(), err.getvalue()

    def call_names(self):
        return [call[0] for call in self.fake.calls]


class SuccessTests(LauncherCase):
    def test_success_translates_host_path_and_cleans_owned_resources(self):
        self.launcher = self.new_launcher()
        folder = self.attach_success()
        code, out, err = self.run_launcher()
        self.assertEqual(code, 0, err)
        self.assertIn(f"结果目录： {folder}", out)
        data = json.loads((folder / "result.json").read_text())
        self.assertTrue(data["passed"])
        self.assertEqual(data["resources_remaining"], [])
        self.assertEqual(self.call_names().count("remove_container"), 2)
        self.assertEqual(self.call_names().count("remove_network"), 1)
        self.assertFalse((self.launcher.scratch / "pg.env").exists())
        self.assertFalse((self.launcher.scratch / "runner.env").exists())
        self.assertTrue((self.launcher.scratch / "launcher.json").exists())
        summary = json.loads((self.launcher.scratch / "launcher.json").read_text())
        self.assertTrue(summary["docker_cleanup_ok"])
        self.assertEqual(summary["resources_remaining"], [])

    def test_no_secret_reaches_docker_arguments_or_stdout(self):
        self.launcher = self.new_launcher()
        self.attach_success()
        code, out, err = self.run_launcher()
        self.assertEqual(code, 0, err)
        recorded = repr(self.fake.calls)
        self.assertNotIn(self.launcher.password, recorded)
        self.assertNotIn("postgresql://", recorded)
        self.assertNotIn(self.launcher.password, out)
        self.assertNotIn("POSTGRES_PASSWORD", out)

    def test_ownership_label_is_verified_before_each_removal(self):
        self.launcher = self.new_launcher()
        self.attach_success()
        code, _, err = self.run_launcher()
        self.assertEqual(code, 0, err)
        for index, name in enumerate(self.call_names()):
            if name not in ("remove_container", "remove_network"):
                continue
            removal = self.fake.calls[index]
            resource = "network" if name == "remove_network" else "container"
            checked = [
                call
                for call in self.fake.calls[:index]
                if call[0] == "inspect_label"
                and call[1][0] == resource
                and call[1][1] == removal[1][0]
            ]
            self.assertTrue(checked, "removal without ownership verification")

    def test_native_nonzero_returncode_is_preserved_with_result(self):
        folder, run_id = self.make_result(passed=False)
        container = f"/work/artifacts/threshold-gateway-demo-live/{run_id}"
        self.fake.attach_handler = lambda _cid: desktop.Attach(
            output=f"结果目录： {container}\n".encode(), exit_code=1, timed_out=False
        )
        self.launcher = self.new_launcher()
        code, out, err = self.run_launcher()
        self.assertEqual(code, 1)
        self.assertIn(f"结果目录： {folder}", out)
        data = json.loads((folder / "result.json").read_text())
        self.assertFalse(data["passed"])
        self.assertEqual(data["resources_remaining"], [])


class CleanupTests(LauncherCase):
    def test_cleanup_failure_marks_result_failed_and_extends_resources(self):
        self.launcher = self.new_launcher()
        folder = self.attach_success()
        self.fake.cleanup_fail = {"container"}
        code, out, err = self.run_launcher()
        self.assertEqual(code, 1)
        self.assertIn(f"结果目录： {folder}", out)
        data = json.loads((folder / "result.json").read_text())
        self.assertFalse(data["passed"])
        self.assertTrue(
            any(item.startswith("docker:container:") for item in data["resources_remaining"])
        )
        self.assertNotIn(self.launcher.password, json.dumps(data))

    def test_foreign_label_refuses_removal_and_reports_remaining(self):
        self.launcher = self.new_launcher()
        folder = self.attach_success()
        self.fake.label_override = {"container": "someone-else", "network": "someone-else"}
        code, _, err = self.run_launcher()
        self.assertEqual(code, 1)
        self.assertEqual(self.fake.removed, [])
        data = json.loads((folder / "result.json").read_text())
        self.assertFalse(data["passed"])
        self.assertEqual(len(data["resources_remaining"]), 3)


class FailureTests(LauncherCase):
    def test_timeout_reports_failure_without_result(self):
        self.launcher = self.new_launcher()
        self.fake.attach_handler = lambda _cid: desktop.Attach(
            output=b"", exit_code=None, timed_out=True
        )
        code, out, err = self.run_launcher()
        self.assertEqual(code, 1)
        self.assertNotIn("结果目录：", out)
        self.assertIn("限时", err)
        self.assertFalse((self.repo / desktop.DEMO_ROOT_REL / "result.json").exists())
        self.assertEqual(self.call_names().count("remove_container"), 2)

    def test_result_path_outside_allowed_root_is_rejected(self):
        folder, _ = self.make_result()
        for path in ("/etc/passwd", "/work/artifacts/other/run", "/work/../outside", "/work/"):
            with self.subTest(path=path):
                self.fake.attach_handler = lambda _cid, path=path: desktop.Attach(
                    output=f"结果目录： {path}\n".encode(), exit_code=0, timed_out=False
                )
                self.launcher = self.new_launcher()
                code, out, err = self.run_launcher()
                self.assertEqual(code, 1)
                self.assertNotIn("结果目录：", out)
                self.assertIn("结果目录", err)
        self.assertTrue(json.loads((folder / "result.json").read_text())["passed"])

    def test_invalid_result_schema_is_rejected(self):
        folder, run_id = self.make_result()
        payload = json.loads((folder / "result.json").read_text())
        payload["demo"] = "something-else"
        (folder / "result.json").write_text(json.dumps(payload))
        container = f"/work/artifacts/threshold-gateway-demo-live/{run_id}"
        self.fake.attach_handler = lambda _cid: desktop.Attach(
            output=f"结果目录： {container}\n".encode(), exit_code=0, timed_out=False
        )
        self.launcher = self.new_launcher()
        code, _, err = self.run_launcher()
        self.assertEqual(code, 1)
        self.assertIn("结果文件", err)

    def test_docker_unavailable_fails_closed(self):
        self.fake.available_value = False
        self.launcher = self.new_launcher()
        code, _, err = self.run_launcher()
        self.assertEqual(code, 2)
        self.assertIn("Docker", err)
        self.assertNotIn("network_create", self.call_names())

    def test_missing_image_builds_with_mapped_local_proxy(self):
        self.fake.image_value = False
        self.launcher = self.new_launcher(
            environ={"HTTP_PROXY": "http://127.0.0.1:7897", "HTTPS_PROXY": "http://localhost:7897"}
        )
        self.attach_success()
        code, _, err = self.run_launcher()
        self.assertEqual(code, 0, err)
        self.assertEqual(
            self.fake.build_args,
            {
                "HTTP_PROXY": "http://host.docker.internal:7897",
                "HTTPS_PROXY": "http://host.docker.internal:7897",
            },
        )

    def test_build_failure_is_sanitized_and_no_container_is_created(self):
        self.fake.image_value = False
        self.fake.build_fail = True
        self.launcher = self.new_launcher()
        code, _, err = self.run_launcher()
        self.assertEqual(code, 2)
        self.assertIn("Docker 命令未成功", err)
        self.assertNotIn("container_create_pg", self.call_names())
        self.assertNotIn(self.launcher.password, err)


class ConcurrencyTests(LauncherCase):
    def test_each_run_uses_unique_resources(self):
        first = desktop.Launcher(repo=self.repo, docker=FakeDocker())
        second = desktop.Launcher(repo=self.repo, docker=FakeDocker())
        self.assertNotEqual(first.token, second.token)
        self.assertNotEqual(first.names, second.names)
        self.assertNotEqual(first.password, second.password)
        self.assertNotEqual(first.scratch, second.scratch)


class DockerAttachTests(unittest.TestCase):
    class _FakeProcess:
        def __init__(self, output: bytes = b""):
            self.stdout = io.BytesIO(output)
            self.exited = False
            self.killed = False
            self.returncode = None

        def wait(self, timeout=None):
            if self.exited:
                return self.returncode
            raise subprocess.TimeoutExpired(cmd="docker", timeout=timeout)

        def kill(self):
            self.killed = True
            self.exited = True
            self.returncode = -9

    def test_timeout_kills_the_owned_container(self):
        process = self._FakeProcess(b"partial\n")
        captured: list[list[str]] = []
        with (
            mock.patch.object(desktop.subprocess, "Popen", return_value=process),
            mock.patch.object(
                desktop.Docker,
                "_capture",
                side_effect=lambda args, *a, **k: captured.append(args),
            ),
            mock.patch.object(desktop.Docker, "container_exit_code", return_value=None),
        ):
            attach = desktop.Docker("docker").attach_runner("cid", timeout=0.01)
        self.assertTrue(attach.timed_out)
        self.assertIsNone(attach.exit_code)
        self.assertIn(["kill", "cid"], captured)
        self.assertTrue(process.killed)

    def test_container_exit_code_is_used_when_not_timed_out(self):
        process = self._FakeProcess(b"")
        process.exited = True
        process.returncode = 0
        with (
            mock.patch.object(desktop.subprocess, "Popen", return_value=process),
            mock.patch.object(desktop.Docker, "container_exit_code", return_value=7),
        ):
            attach = desktop.Docker("docker").attach_runner("cid", timeout=5)
        self.assertFalse(attach.timed_out)
        self.assertEqual(attach.exit_code, 7)


@unittest.skipUnless(runner_image_present(), "runner image or Docker daemon not available")
class RealCliTests(unittest.TestCase):
    """One actual CLI run: host Python, real image, fresh owned PostgreSQL, no ports."""

    def test_actual_cli_run_in_docker(self):
        with tempfile.TemporaryDirectory() as foreign_cwd:
            completed = subprocess.run(
                [sys.executable, str(REPO / "tools" / "threshold_desktop.py"), "--timeout", "600"],
                cwd=foreign_cwd,
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
                env=os.environ.copy(),
            )
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        lines = [
            line for line in completed.stdout.splitlines() if line.startswith(desktop.RESULT_LINE)
        ]
        self.assertEqual(len(lines), 1, completed.stdout[-2000:])
        folder = Path(lines[0].split("：", 1)[1].strip())
        self.assertTrue(folder.is_absolute())
        folder.relative_to(DEMO_ROOT)
        data = json.loads((folder / "result.json").read_text())
        self.assertTrue(data["passed"])
        self.assertEqual(data["resources_remaining"], [])
        self.assertEqual(data["run_id"], folder.name)
        self.assertEqual(len(data["cases"]), 6)
        self.assertTrue(all(case["passed"] for case in data["cases"]))
        self.assertNotIn("postgresql://", completed.stdout)
        self.assertEqual(self._labelled(["ps", "-a"]), [])
        self.assertEqual(self._labelled(["network", "ls"]), [])
        leftovers = list(SCRATCH_ROOT.rglob("*.env")) if SCRATCH_ROOT.exists() else []
        self.assertEqual(leftovers, [])

    @staticmethod
    def _labelled(kind_args: list[str]) -> list[str]:
        completed = subprocess.run(
            ["docker", *kind_args, "--filter", LABEL_FILTER, "--format", "{{.ID}}"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return [line for line in completed.stdout.splitlines() if line.strip()]


if __name__ == "__main__":
    unittest.main()
