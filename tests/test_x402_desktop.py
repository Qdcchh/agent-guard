"""Focused mock-only tests for the Docker-hosted x402 desktop launcher.

The real ``tools/x402_gateway_demo.py`` driver does not exist yet, so these
tests exercise only the host launcher boundary with an in-memory Docker fake.
No Docker container, PostgreSQL server, Anvil process, x402 payment or chain
transaction is started here; synthetic ``result.json`` files are launcher
inputs, not evidence of a real x402 settlement. Only the bounded Docker command
constructors and the attach timeout wrapper are exercised directly with mocks.
"""

from __future__ import annotations

import hashlib
import io
import json
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
TEST_SCRATCH = REPO / "artifacts" / "x402-gateway-20261017" / "launcher-worker" / "test-scratch"
sys.path.insert(0, str(REPO))

from tools import threshold_desktop as threshold  # noqa: E402
from tools import x402_desktop as desktop  # noqa: E402

RUNNER_IMAGE = "agent-guard-x402-runner:20261017"
DEMO_ROOT = REPO / "artifacts" / "x402-gateway-demo-live"
SCRATCH_ROOT = REPO / "artifacts" / "x402-gateway-desktop"


def completed(stdout: bytes = b"", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=b"")


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
        self.labels_by_id: dict[str, dict] = {}
        self.removed: list[str] = []
        self.build_args: dict[str, str] = {}
        self.attach_handler = None
        self._sequence = 0

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def _next_id(self, prefix):
        self._sequence += 1
        return hashlib.sha256(f"{prefix}:{self._sequence}".encode()).hexdigest()

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
        container_id = self._next_id("runner")
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


def result_payload(run_id: str, passed: bool = True) -> dict:
    return {
        "demo": "x402-gateway-purchase",
        "run_id": run_id,
        "profile": "AG-GUARD-X402-PURCHASE-1",
        "passed": passed,
        "cases": [
            {
                "name": "payment-required",
                "passed": True,
                "http_status": 402,
                "code": "PAYMENT_REQUIRED",
            },
            {"name": "paid-purchase", "passed": passed, "http_status": 201},
        ],
        "operations": 1,
        "approvals": 1,
        "orders": 1,
        "payments": 1,
        "transactions": 1,
        "resources_remaining": [],
        "limitations": ["synthetic launcher test input only; no chain run"],
    }


class LauncherCase(unittest.TestCase):
    def setUp(self):
        TEST_SCRATCH.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.temp = tempfile.TemporaryDirectory(dir=TEST_SCRATCH)
        self.repo = (Path(self.temp.name) / "repo").resolve()
        (self.repo / "deploy" / "x402-runner").mkdir(parents=True)
        (self.repo / "deploy" / "x402-runner" / "Dockerfile").write_text("FROM scratch\n")
        self.fake = FakeDocker()
        self.runner_env_text = None
        self.runner_env_mode = None

    def tearDown(self):
        self.temp.cleanup()

    def new_launcher(self, **kwargs):
        kwargs.setdefault("repo", self.repo)
        kwargs.setdefault("docker", self.fake)
        kwargs.setdefault("timeout", 30.0)
        return desktop.Launcher(**kwargs)

    def make_result(self, *, run_id=None, passed: bool = True, mutate=None):
        run_id = run_id or str(uuid.uuid4())
        folder = self.repo / desktop.DEMO_ROOT_REL / run_id
        folder.mkdir(parents=True, mode=0o700)
        payload = result_payload(run_id, passed)
        if mutate is not None:
            mutate(payload)
        (folder / "result.json").write_text(json.dumps(payload), encoding="utf-8")
        return folder, run_id

    def attach_success(self, launcher, *, passed: bool = True, exit_code: int = 0):
        folder, run_id = self.make_result(passed=passed)
        container = f"/work/artifacts/x402-gateway-demo-live/{run_id}"

        def handler(container_id):
            env_file = self.fake.containers[container_id]["env_file"]
            self.runner_env_text = env_file.read_text(encoding="utf-8")
            self.runner_env_mode = stat.S_IMODE(env_file.stat().st_mode)
            return desktop.Attach(
                output=f"结果目录： {container}\n".encode(),
                exit_code=exit_code,
                timed_out=False,
            )

        self.fake.attach_handler = handler
        return folder

    def attach_path(self, path: str, *, exit_code: int = 0):
        self.fake.attach_handler = lambda _cid: desktop.Attach(
            output=f"结果目录： {path}\n".encode(),
            exit_code=exit_code,
            timed_out=False,
        )

    def run_launcher(self, launcher):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = launcher.run()
        return code, out.getvalue(), err.getvalue()

    def call_names(self):
        return [call[0] for call in self.fake.calls]


class ApprovalSchemeTests(LauncherCase):
    def test_sm2_scheme_is_passed_only_through_private_runner_env(self):
        launcher = self.new_launcher(approval_scheme="sm2-2p")
        folder = self.attach_success(launcher)
        code, out, err = self.run_launcher(launcher)
        self.assertEqual(code, 0, err)
        self.assertIn(f"结果目录： {folder}", out)
        lines = dict(
            line.split("=", 1) for line in self.runner_env_text.splitlines() if "=" in line
        )
        self.assertEqual(
            set(lines), {desktop.DEMO_DSN_ENV, "PYTHONPATH", desktop.APPROVAL_SCHEME_ENV}
        )
        self.assertEqual(lines[desktop.APPROVAL_SCHEME_ENV], "sm2-2p")
        self.assertEqual(self.runner_env_mode, 0o600)
        self.assertFalse((launcher.scratch / "runner.env").exists())

    def test_unknown_scheme_is_rejected_before_any_docker_call(self):
        with self.assertRaises(ValueError):
            self.new_launcher(approval_scheme="ed25519-single")
        self.assertEqual(self.fake.calls, [])

    def test_cli_rejects_unknown_scheme(self):
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit):
            desktop.main(["--approval-scheme", "bogus"])


class SuccessTests(LauncherCase):
    def test_success_translates_host_path_and_cleans_exact_owned_ids(self):
        launcher = self.new_launcher()
        folder = self.attach_success(launcher)
        code, out, err = self.run_launcher(launcher)
        self.assertEqual(code, 0, err)
        self.assertIn(f"结果目录： {folder}", out)
        data = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        self.assertTrue(data["passed"])
        self.assertEqual(data["resources_remaining"], [])
        self.assertEqual(data["payments"], 1)
        self.assertEqual(data["transactions"], 1)
        self.assertEqual(self.call_names().count("remove_container"), 2)
        self.assertEqual(self.call_names().count("remove_network"), 1)
        owned_ids = {resource_id for _, resource_id, _ in launcher.resources}
        self.assertEqual(set(self.fake.removed), owned_ids)
        self.assertTrue(all(len(resource_id) == 64 for resource_id in self.fake.removed))
        self.assertFalse(set(self.fake.removed) & set(launcher.names.values()))
        self.assertFalse((launcher.scratch / "pg.env").exists())
        self.assertFalse((launcher.scratch / "runner.env").exists())
        self.assertEqual(stat.S_IMODE(launcher.scratch.stat().st_mode), 0o700)
        summary = json.loads((launcher.scratch / "launcher.json").read_text(encoding="utf-8"))
        self.assertTrue(summary["docker_cleanup_ok"])
        self.assertEqual(summary["resources_remaining"], [])
        self.assertEqual(summary["runner_image"], RUNNER_IMAGE)
        self.assertEqual(summary["exit_code"], 0)

    def test_runner_env_uses_only_generated_dsn_and_never_host_dsn(self):
        host_dsn = "postgresql://host_user:hunter2@127.0.0.1:5432/host_db"
        launcher = self.new_launcher(environ={"AGENT_GUARD_X402_DEMO_DSN": host_dsn})
        folder = self.attach_success(launcher)
        code, out, err = self.run_launcher(launcher)
        self.assertEqual(code, 0, err)
        self.assertIn(f"结果目录： {folder}", out)
        self.assertIsNotNone(self.runner_env_text)
        lines = dict(
            line.split("=", 1) for line in self.runner_env_text.splitlines() if "=" in line
        )
        self.assertEqual(set(lines), {desktop.DEMO_DSN_ENV, "PYTHONPATH"})
        self.assertEqual(lines[desktop.DEMO_DSN_ENV], launcher._dsn())
        self.assertEqual(lines["PYTHONPATH"], "/work/src")
        self.assertNotIn("hunter2", self.runner_env_text)
        self.assertEqual(self.runner_env_mode, 0o600)
        recorded = repr(self.fake.calls)
        self.assertNotIn(launcher.password, recorded)
        self.assertNotIn("postgresql://", recorded)
        self.assertNotIn(launcher.password, out)
        self.assertNotIn(launcher.password, err)
        self.assertNotIn("postgresql://", out)
        self.assertNotIn("POSTGRES_PASSWORD", out)

    def test_ownership_label_is_verified_by_exact_id_before_each_removal(self):
        launcher = self.new_launcher()
        self.attach_success(launcher)
        code, _, err = self.run_launcher(launcher)
        self.assertEqual(code, 0, err)
        owned_ids = {resource_id for _, resource_id, _ in launcher.resources}
        for index, name in enumerate(self.call_names()):
            if name not in ("remove_container", "remove_network"):
                continue
            removal = self.fake.calls[index]
            resource_id = removal[1][0]
            resource = "network" if name == "remove_network" else "container"
            self.assertIn(resource_id, owned_ids)
            checked = [
                call
                for call in self.fake.calls[:index]
                if call[0] == "inspect_label"
                and call[1][0] == resource
                and call[1][1] == resource_id
                and call[1][2] == desktop.OWNER_LABEL
            ]
            self.assertTrue(checked, "removal without exact-ID ownership verification")

    def test_profile_is_optional(self):
        launcher = self.new_launcher()
        folder, run_id = self.make_result(mutate=lambda data: data.pop("profile"))
        self.attach_path(f"/work/artifacts/x402-gateway-demo-live/{run_id}")
        code, _, err = self.run_launcher(launcher)
        self.assertEqual(code, 0, err)
        data = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        self.assertNotIn("profile", data)
        self.assertTrue(data["passed"])

    def test_native_nonzero_returncode_is_preserved_with_result(self):
        launcher = self.new_launcher()
        folder = self.attach_success(launcher, passed=False, exit_code=1)
        code, out, err = self.run_launcher(launcher)
        self.assertEqual(code, 1, err)
        self.assertIn(f"结果目录： {folder}", out)
        data = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        self.assertFalse(data["passed"])
        self.assertEqual(data["resources_remaining"], [])

    def test_desktop_module_does_not_mutate_threshold_globals(self):
        before = (
            threshold.RUNNER_IMAGE,
            threshold.DEMO_ROOT_REL,
            threshold.OWNER_LABEL,
            threshold.PURPOSE_VALUE,
        )
        launcher = self.new_launcher()
        self.attach_success(launcher)
        code, _, err = self.run_launcher(launcher)
        self.assertEqual(code, 0, err)
        after = (
            threshold.RUNNER_IMAGE,
            threshold.DEMO_ROOT_REL,
            threshold.OWNER_LABEL,
            threshold.PURPOSE_VALUE,
        )
        self.assertEqual(before, after)
        self.assertNotEqual(desktop.RUNNER_IMAGE, threshold.RUNNER_IMAGE)
        self.assertNotEqual(desktop.DEMO_ROOT_REL, threshold.DEMO_ROOT_REL)


class CleanupTests(LauncherCase):
    def test_cleanup_failure_marks_result_failed_and_extends_resources(self):
        launcher = self.new_launcher()
        folder = self.attach_success(launcher)
        self.fake.cleanup_fail = {"container"}
        code, out, err = self.run_launcher(launcher)
        self.assertEqual(code, 1, err)
        self.assertIn(f"结果目录： {folder}", out)
        data = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        self.assertFalse(data["passed"])
        self.assertEqual(
            sum(item.startswith("docker:container:") for item in data["resources_remaining"]),
            2,
        )
        self.assertNotIn(launcher.password, json.dumps(data))
        summary = json.loads((launcher.scratch / "launcher.json").read_text(encoding="utf-8"))
        self.assertFalse(summary["docker_cleanup_ok"])
        self.assertFalse((launcher.scratch / "runner.env").exists())

    def test_foreign_label_refuses_removal_and_reports_remaining(self):
        launcher = self.new_launcher()
        folder = self.attach_success(launcher)
        self.fake.label_override = {"container": "someone-else", "network": "someone-else"}
        code, _, err = self.run_launcher(launcher)
        self.assertEqual(code, 1, err)
        self.assertEqual(self.fake.removed, [])
        data = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        self.assertFalse(data["passed"])
        self.assertEqual(len(data["resources_remaining"]), 3)


class FailureTests(LauncherCase):
    def test_timeout_reports_failure_without_result(self):
        launcher = self.new_launcher()
        self.fake.attach_handler = lambda _cid: desktop.Attach(
            output=b"", exit_code=None, timed_out=True
        )
        code, out, err = self.run_launcher(launcher)
        self.assertEqual(code, 1)
        self.assertNotIn("结果目录：", out)
        self.assertIn("限时", err)
        self.assertEqual(self.call_names().count("remove_container"), 2)
        self.assertEqual(self.call_names().count("remove_network"), 1)

    def test_result_path_outside_allowed_root_is_rejected(self):
        for path in (
            "/etc/passwd",
            "/work/artifacts/other/run",
            "/work/../outside",
            "/work/",
            "/work/artifacts/x402-gateway-demo-live/../escape",
            f"/work/artifacts/x402-gateway-demo-live/{uuid.uuid4()}/extra",
        ):
            with self.subTest(path=path):
                self.fake = FakeDocker()
                launcher = self.new_launcher()
                self.attach_path(path)
                code, out, err = self.run_launcher(launcher)
                self.assertEqual(code, 1)
                self.assertNotIn("结果目录：", out)
                self.assertIn("结果目录", err)

    def test_symlinked_result_directory_is_rejected(self):
        self.fake = FakeDocker()
        launcher = self.new_launcher()
        run_id = str(uuid.uuid4())
        outside = self.repo / "outside"
        outside.mkdir()
        demo_root = self.repo / desktop.DEMO_ROOT_REL
        demo_root.mkdir(parents=True, exist_ok=True)
        (demo_root / run_id).symlink_to(outside, target_is_directory=True)
        self.attach_path(f"/work/artifacts/x402-gateway-demo-live/{run_id}")
        code, out, err = self.run_launcher(launcher)
        self.assertEqual(code, 1)
        self.assertNotIn("结果目录：", out)
        self.assertIn("结果目录", err)

    def test_invalid_result_schema_is_rejected(self):
        mutations = {
            "wrong-demo": lambda data: data.__setitem__("demo", "threshold-gateway-purchase"),
            "missing-payments": lambda data: data.pop("payments"),
            "bool-transactions": lambda data: data.__setitem__("transactions", True),
            "bool-operations": lambda data: data.__setitem__("operations", True),
            "empty-cases": lambda data: data.__setitem__("cases", []),
            "run-id-mismatch": lambda data: data.__setitem__("run_id", str(uuid.uuid4())),
            "profile-number": lambda data: data.__setitem__("profile", 7),
            "resources-not-list": lambda data: data.__setitem__("resources_remaining", "none"),
            "case-passed-number": lambda data: data["cases"][0].__setitem__("passed", 1),
            "http-status-bool": lambda data: data["cases"][0].__setitem__("http_status", True),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                self.fake = FakeDocker()
                launcher = self.new_launcher()
                _, run_id = self.make_result(mutate=mutate)
                self.attach_path(f"/work/artifacts/x402-gateway-demo-live/{run_id}")
                code, out, err = self.run_launcher(launcher)
                self.assertEqual(code, 1)
                self.assertNotIn("结果目录：", out)
                self.assertIn("结果文件", err)

    def test_docker_unavailable_fails_closed(self):
        self.fake.available_value = False
        launcher = self.new_launcher()
        code, _, err = self.run_launcher(launcher)
        self.assertEqual(code, 2)
        self.assertIn("Docker", err)
        self.assertNotIn("network_create", self.call_names())

    def test_image_arch_mismatch_fails_before_resources(self):
        self.fake.arch = "arm64"
        launcher = self.new_launcher()
        code, _, err = self.run_launcher(launcher)
        self.assertEqual(code, 2)
        self.assertIn("amd64", err)
        self.assertNotIn("network_create", self.call_names())
        self.assertFalse((launcher.scratch / "runner.env").exists())

    def test_missing_image_builds_fallback_without_platform_and_maps_proxy(self):
        self.fake.image_value = False
        launcher = self.new_launcher(
            environ={"HTTP_PROXY": "http://127.0.0.1:7897", "HTTPS_PROXY": "http://localhost:7897"}
        )
        self.attach_success(launcher)
        code, _, err = self.run_launcher(launcher)
        self.assertEqual(code, 0, err)
        self.assertEqual(
            self.fake.build_args,
            {
                "HTTP_PROXY": "http://host.docker.internal:7897",
                "HTTPS_PROXY": "http://host.docker.internal:7897",
            },
        )
        builds = [call for call in self.fake.calls if call[0] == "build_runner"]
        self.assertEqual(len(builds), 1)
        dockerfile, context, _ = builds[0][1]
        self.assertEqual(dockerfile, self.repo / "deploy" / "x402-runner" / "Dockerfile")
        self.assertEqual(context, self.repo)
        self.assertLess(
            self.call_names().index("build_runner"),
            self.call_names().index("network_create"),
        )

    def test_build_failure_is_sanitized_and_no_container_is_created(self):
        self.fake.image_value = False
        self.fake.build_fail = True
        launcher = self.new_launcher()
        code, _, err = self.run_launcher(launcher)
        self.assertEqual(code, 2)
        self.assertIn("Docker 命令未成功", err)
        self.assertNotIn("container_create_pg", self.call_names())
        self.assertNotIn(launcher.password, err)

    def test_missing_dockerfile_fails_without_build(self):
        (self.repo / "deploy" / "x402-runner" / "Dockerfile").unlink()
        self.fake.image_value = False
        launcher = self.new_launcher()
        code, _, err = self.run_launcher(launcher)
        self.assertEqual(code, 2)
        self.assertIn("缺少", err)
        self.assertNotIn("build_runner", self.call_names())
        self.assertNotIn("network_create", self.call_names())


class CommandConstructionTests(unittest.TestCase):
    def capture(self):
        captured: list[tuple] = []

        def side_effect(args, timeout, **kwargs):
            captured.append((args, timeout, kwargs))
            return completed(stdout=b"resource-id\n")

        return captured, mock.patch.object(desktop.Docker, "_capture", side_effect=side_effect)

    def test_runner_create_omits_platform_and_has_no_host_ports_or_socket(self):
        captured, patcher = self.capture()
        with patcher:
            resource_id = desktop.Docker("docker").container_create_runner(
                RUNNER_IMAGE,
                "runner",
                "network-id",
                Path("/project/runner.env"),
                {desktop.OWNER_LABEL: "token", desktop.PURPOSE_LABEL: desktop.PURPOSE_VALUE},
                Path("/repo"),
                Path("/repo/artifacts/x402-gateway-demo-live"),
            )
        self.assertEqual(resource_id, "resource-id")
        args, _, _ = captured[0]
        mounts = [args[index + 1] for index, item in enumerate(args) if item == "--mount"]
        self.assertEqual(
            mounts,
            [
                "type=bind,src=/repo,dst=/work,readonly",
                "type=bind,src=/repo/artifacts/x402-gateway-demo-live,"
                "dst=/work/artifacts/x402-gateway-demo-live",
            ],
        )
        self.assertNotIn("--platform", args)
        self.assertNotIn("-p", args)
        self.assertNotIn("--publish", args)
        self.assertNotIn("--privileged", args)
        network_values = [args[index + 1] for index, item in enumerate(args) if item == "--network"]
        self.assertEqual(network_values, ["network-id"])
        self.assertNotIn("docker.sock", " ".join(args))
        self.assertNotIn("AGENT_GUARD_X402_DEMO_DSN", " ".join(args))
        self.assertEqual(
            args[-3:],
            [RUNNER_IMAGE, "/opt/venv/bin/python", "tools/x402_gateway_demo.py"],
        )

    def test_pg_create_omits_platform_and_publishes_no_port(self):
        captured, patcher = self.capture()
        with patcher:
            desktop.Docker("docker").container_create_pg(
                "postgres:16-alpine",
                "pg",
                "network-id",
                "pg",
                Path("/project/pg.env"),
                {desktop.OWNER_LABEL: "token"},
            )
        args, _, _ = captured[0]
        self.assertNotIn("--platform", args)
        self.assertNotIn("-p", args)
        self.assertNotIn("--publish", args)
        network_values = [args[index + 1] for index, item in enumerate(args) if item == "--network"]
        self.assertEqual(network_values, ["network-id"])
        self.assertIn("--tmpfs", args)
        self.assertNotIn("docker.sock", " ".join(args))

    def test_build_fallback_omits_platform_and_uses_repo_dockerfile(self):
        captured, patcher = self.capture()
        with patcher:
            desktop.Docker("docker").build_runner(
                Path("/repo/deploy/x402-runner/Dockerfile"),
                Path("/repo"),
                {"BASE_IMAGE": "agent-guard-threshold-gateway-runner:20261017"},
            )
        args, _, kwargs = captured[0]
        self.assertNotIn("--platform", args)
        self.assertIn(RUNNER_IMAGE, args)
        self.assertIn("/repo/deploy/x402-runner/Dockerfile", args)
        self.assertEqual(args[-1], "/repo")
        self.assertEqual(kwargs["cwd"], Path("/repo"))
        self.assertTrue(kwargs["check"])


class ConcurrencyTests(LauncherCase):
    def test_each_run_uses_unique_owned_resources(self):
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

    def test_timeout_kills_the_exact_owned_container(self):
        process = self._FakeProcess(b"partial\n")
        captured: list[list[str]] = []
        with (
            mock.patch.object(threshold.subprocess, "Popen", return_value=process),
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
            mock.patch.object(threshold.subprocess, "Popen", return_value=process),
            mock.patch.object(desktop.Docker, "container_exit_code", return_value=7),
        ):
            attach = desktop.Docker("docker").attach_runner("cid", timeout=5)
        self.assertFalse(attach.timed_out)
        self.assertEqual(attach.exit_code, 7)


class MainTests(unittest.TestCase):
    def test_invalid_timeout_fails_without_constructing_launcher(self):
        err = io.StringIO()
        with mock.patch.object(desktop, "Launcher") as launcher_type, redirect_stderr(err):
            code = desktop.main(["--timeout", "0"])
        self.assertEqual(code, 2)
        launcher_type.assert_not_called()
        self.assertIn("限时", err.getvalue())


if __name__ == "__main__":
    unittest.main()
