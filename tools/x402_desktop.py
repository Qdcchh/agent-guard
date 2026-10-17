"""Host launcher: run the fixed x402 gateway demo entirely inside Docker.

Ordinary desktop Python 3 (standard library only) starts this CLI. It creates
exactly owned, random-labelled Docker resources -- a private bridge network,
one temporary PostgreSQL 16 container without published ports and one runner
container from the pinned ``agent-guard-x402-runner:20261017`` image -- and then
runs the fixed ``tools/x402_gateway_demo.py`` inside that network. No host
cryptography, x402 SDK or psycopg is installed and no DSN is exported by the
operator: the private test DSN is written only to a mode-0600 ``--env-file``
that Docker reads, so it never appears in a command line or in this program's
output.

The inner demo owns its private Anvil process and all chain material inside the
runner. This launcher never mounts the Docker socket, publishes a port, forwards
a host RPC URL or accepts a real wallet/asset key. The repository is mounted
read-only at ``/work``; only ``/work/artifacts/x402-gateway-demo-live`` is
writable so the demo can write its sanitized result.

Cleanup verifies the random run label by exact resource ID before removing
anything and never inspects or prunes resources it did not create. The demo
prints its result directory as a container path (``/work/...``); this launcher
translates that to the validated repository path under
``artifacts/x402-gateway-demo-live/<run id>``, preserves the native demo exit
status and, when Docker cleanup failed, marks the sanitized result as failed and
extends ``resources_remaining`` instead of claiming success.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools.threshold_desktop import (  # noqa: E402
    Attach,
    DockerError,
    find_docker,
    map_loopback_proxy,
)
from tools.threshold_desktop import (  # noqa: E402
    Docker as _BaseDocker,
)

RUNNER_IMAGE = "agent-guard-x402-runner:20261017"
EXPECTED_RUNNER_ARCH = "amd64"
BASE_IMAGE_DEFAULT = "agent-guard-threshold-gateway-runner:20261017"
BASE_IMAGE_REPOSITORY = "agent-guard-threshold-gateway-runner"
PG_IMAGES = ("postgres:16-alpine", "postgres:16", "postgres:16-bookworm")
DEMO_ROOT_REL = Path("artifacts/x402-gateway-demo-live")
SCRATCH_ROOT_REL = Path("artifacts/x402-gateway-desktop")
WORKDIR = "/work"
DEMO_NAME = "x402-gateway-purchase"
DEMO_DSN_ENV = "AGENT_GUARD_X402_DEMO_DSN"
WORKDIR_DEMO_ROOT = f"{WORKDIR}/{DEMO_ROOT_REL.as_posix()}"
RESULT_LINE = "结果目录："
OWNER_LABEL = "agent-guard.x402-desktop"
PURPOSE_LABEL = "agent-guard.purpose"
PURPOSE_VALUE = "x402-desktop-demo"
OUTPUT_CAP = 262_144
READY_TIMEOUT = 90.0
DEFAULT_TIMEOUT = 900.0
BUILD_TIMEOUT = 3600.0
MAX_RESULT_BYTES = 1_000_000

PUBLIC_MESSAGES = {
    "docker_unavailable": "Docker Desktop 未就绪或不可访问",
    "docker_command_failed": "Docker 命令未成功",
    "dockerfile_missing": "缺少 deploy/x402-runner/Dockerfile",
    "runner_platform_mismatch": "x402 运行镜像不是 linux/amd64",
    "postgres_not_ready": "临时 PostgreSQL 未在限时内就绪",
    "demo_timeout": "演示限时内未完成，已停止运行容器",
    "demo_result_missing": "演示未返回可验证的结果目录",
    "demo_result_invalid": "演示结果文件不符合固定格式",
    "unsafe_directory": "本机结果目录不是安全的真实目录",
}


class Docker(_BaseDocker):
    """Docker CLI wrapper with x402-specific build and runner creation.

    The proven threshold wrapper supplies the bounded attach, inspect, remove
    and PostgreSQL methods. Only the image tag, build platform policy and runner
    container command differ here; no shared module globals are changed.
    """

    def build_runner(self, dockerfile: Path, context: Path, build_args: dict[str, str]) -> None:
        # Deliberately no --platform: Docker Desktop with a cached single-
        # platform amd64 base must not resolve the base from the registry. The
        # architecture is checked with image_arch() before any container starts.
        args = [
            "build",
            "-f",
            str(dockerfile),
            "-t",
            RUNNER_IMAGE,
        ]
        for key, value in sorted(build_args.items()):
            args += ["--build-arg", f"{key}={value}"]
        args.append(str(context))
        self._capture(args, BUILD_TIMEOUT, cwd=context, check=True)

    def container_create_runner(
        self,
        image: str,
        name: str,
        network: str,
        env_file: Path,
        labels: dict[str, str],
        repo_mount: Path,
        demo_mount: Path,
    ) -> str:
        args = ["create", "--name", name]
        for key, value in sorted(labels.items()):
            args += ["--label", f"{key}={value}"]
        args += [
            "--network",
            network,
            "--env-file",
            str(env_file),
            "--mount",
            f"type=bind,src={repo_mount},dst={WORKDIR},readonly",
            "--mount",
            f"type=bind,src={demo_mount},dst={WORKDIR_DEMO_ROOT}",
            "-w",
            WORKDIR,
            image,
            "/opt/venv/bin/python",
            "tools/x402_gateway_demo.py",
        ]
        return self._capture(args, 60, check=True).stdout.decode().strip()


#: Must match tools/x402_gateway_demo.py; kept literal so this launcher stays stdlib-only.
APPROVAL_SCHEME_ENV = "AGENT_GUARD_X402_APPROVAL_SCHEME"
APPROVAL_SCHEMES = frozenset({"frost-ed25519", "sm2-2p"})

X402Docker = Docker


class Launcher:
    """One isolated x402 demo run with exactly owned Docker resources."""

    def __init__(
        self,
        repo: Path = REPO,
        *,
        docker: Docker | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        pg_image: str | None = None,
        environ: dict[str, str] | None = None,
        approval_scheme: str = "frost-ed25519",
    ):
        if approval_scheme not in APPROVAL_SCHEMES:
            raise ValueError("invalid approval scheme")
        self.approval_scheme = approval_scheme
        self.repo = Path(repo).resolve()
        self.docker = docker if docker is not None else Docker(find_docker())
        self.timeout = float(timeout)
        self.pg_image = pg_image
        self.environ = dict(os.environ if environ is None else environ)
        self.token = uuid.uuid4().hex
        self.names = {
            "pg": f"ag-x402desk-pg-{self.token[:12]}",
            "runner": f"ag-x402desk-runner-{self.token[:12]}",
            "net": f"ag-x402desk-net-{self.token[:12]}",
        }
        self.user = f"ag_demo_{self.token[:12]}"
        self.database = self.user
        self.password = secrets.token_urlsafe(24)
        self.scratch = self.repo / SCRATCH_ROOT_REL / self.token
        self.demo_root = self.repo / DEMO_ROOT_REL
        self.resources: list[tuple[str, str, str]] = []
        self.remaining: list[str] = []
        self.secret_files: list[Path] = []
        self.pg_image_used: str | None = None

    # -- setup helpers ----------------------------------------------------

    def _prepare_dirs(self) -> None:
        for directory in (self.scratch.parent, self.scratch, self.demo_root):
            if directory.exists() and directory.is_symlink():
                raise DockerError("unsafe_directory")
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Result and scratch directories stay private to the current user.
        for directory in (self.scratch.parent, self.scratch, self.demo_root):
            try:
                os.chmod(directory, 0o700)
            except OSError:
                pass

    def _labels(self) -> dict[str, str]:
        return {OWNER_LABEL: self.token, PURPOSE_LABEL: PURPOSE_VALUE}

    def _dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.names['pg']}:5432/{self.database}"

    def _write_env_file(self, path: Path, values: dict[str, str]) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")

    def _write_env_files(self) -> None:
        pg_env = self.scratch / "pg.env"
        runner_env = self.scratch / "runner.env"
        self.secret_files = [pg_env, runner_env]
        self._write_env_file(
            pg_env,
            {
                "POSTGRES_USER": self.user,
                "POSTGRES_PASSWORD": self.password,
                "POSTGRES_DB": self.database,
            },
        )
        runner_values = {
            DEMO_DSN_ENV: self._dsn(),
            "PYTHONPATH": f"{WORKDIR}/src",
        }
        if self.approval_scheme != "frost-ed25519":
            runner_values[APPROVAL_SCHEME_ENV] = self.approval_scheme
        self._write_env_file(runner_env, runner_values)

    def _remove_secret_files(self) -> None:
        for path in self.secret_files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def _select_pg_image(self) -> str:
        if self.pg_image:
            return self.pg_image
        for candidate in PG_IMAGES:
            if self.docker.image_exists(candidate):
                return candidate
        return PG_IMAGES[0]

    def _build_runner(self) -> None:
        dockerfile = self.repo / "deploy" / "x402-runner" / "Dockerfile"
        if not dockerfile.is_file():
            raise DockerError("dockerfile_missing")
        build_args: dict[str, str] = {}
        if not self.docker.image_exists(BASE_IMAGE_DEFAULT):
            cached = self.docker.local_image_refs(BASE_IMAGE_REPOSITORY)
            if cached:
                build_args["BASE_IMAGE"] = cached[0]
        for canonical, names in (
            ("HTTP_PROXY", ("HTTP_PROXY", "http_proxy")),
            ("HTTPS_PROXY", ("HTTPS_PROXY", "https_proxy")),
            ("ALL_PROXY", ("ALL_PROXY", "all_proxy")),
        ):
            for name in names:
                value = self.environ.get(name)
                if value:
                    build_args[canonical] = map_loopback_proxy(value)
                    break
        self.docker.build_runner(dockerfile, self.repo, build_args)

    def _safe_mount(self, path: Path) -> Path:
        text = str(path)
        if any(character in text for character in (",", '"', "\n", "\r")):
            raise DockerError("unsafe_directory")
        return path

    def _wait_ready(self, container_id: str) -> bool:
        deadline = time.monotonic() + READY_TIMEOUT
        while time.monotonic() < deadline:
            try:
                if self.docker.exec_ready(container_id, self.user, self.database):
                    return True
            except DockerError:
                pass
            time.sleep(0.5)
        return False

    # -- result translation ----------------------------------------------

    def _translate(self, output: bytes) -> Path | None:
        text = output.decode("utf-8", "replace")
        folder = None
        for line in text.splitlines():
            if line.startswith(RESULT_LINE):
                folder = line[len(RESULT_LINE) :].strip()
        if not folder or not folder.startswith(WORKDIR_DEMO_ROOT + "/"):
            return None
        relative = folder[len(WORKDIR_DEMO_ROOT) + 1 :]
        parts = Path(relative).parts
        if len(parts) != 1 or parts[0] in ("", ".", ".."):
            return None
        try:
            run_id = str(uuid.UUID(parts[0]))
        except ValueError:
            return None
        candidate = self.demo_root / run_id
        if candidate.is_symlink():
            return None
        try:
            candidate.resolve().relative_to(self.demo_root.resolve())
        except ValueError:
            return None
        return candidate

    def _read_result(self, result_dir: Path) -> dict:
        if result_dir.is_symlink() or not result_dir.is_dir():
            raise DockerError("demo_result_missing")
        result_file = result_dir / "result.json"
        if result_file.is_symlink() or not result_file.is_file():
            raise DockerError("demo_result_missing")
        if result_file.stat().st_size > MAX_RESULT_BYTES:
            raise DockerError("demo_result_invalid")
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DockerError("demo_result_invalid") from exc
        self._validate_result(data, result_dir.name)
        return data

    @staticmethod
    def _validate_result(data: object, run_id: str) -> None:
        if not isinstance(data, dict):
            raise DockerError("demo_result_invalid")
        cases = data.get("cases")
        if (
            data.get("demo") != DEMO_NAME
            or data.get("run_id") != run_id
            or type(data.get("passed")) is not bool
            or type(cases) is not list
            or not cases
            or type(data.get("operations")) is not int
            or type(data.get("approvals")) is not int
            or type(data.get("orders")) is not int
            or type(data.get("payments")) is not int
            or type(data.get("transactions")) is not int
            or type(data.get("resources_remaining")) is not list
            or any(type(item) is not str for item in data.get("resources_remaining", []))
            or ("profile" in data and type(data["profile"]) is not str)
        ):
            raise DockerError("demo_result_invalid")
        try:
            uuid.UUID(run_id)
        except ValueError as exc:
            raise DockerError("demo_result_invalid") from exc
        for case in cases:
            if (
                type(case) is not dict
                or type(case.get("name")) is not str
                or type(case.get("passed")) is not bool
                or ("http_status" in case and type(case["http_status"]) is not int)
                or ("code" in case and case["code"] is not None and type(case["code"]) is not str)
            ):
                raise DockerError("demo_result_invalid")

    def _merge_result(self, result_dir: Path, data: dict) -> None:
        existing = [item for item in data.get("resources_remaining", []) if isinstance(item, str)]
        merged = existing + [item for item in self.remaining if item not in existing]
        data["resources_remaining"] = merged
        if data.get("passed") is True:
            data["passed"] = False
        result_file = result_dir / "result.json"
        temp_file = result_dir / "result.json.tmp"
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
            descriptor = os.open(temp_file, flags, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_file, result_file)
        except (OSError, ValueError):
            # The non-zero exit status and summary still report the failure.
            try:
                temp_file.unlink(missing_ok=True)
            except OSError:
                pass

    # -- cleanup ----------------------------------------------------------

    def _cleanup(self) -> list[str]:
        remaining: list[str] = []
        for resource, resource_id, name in reversed(self.resources):
            if not resource_id:
                remaining.append(f"docker:{resource}:{name}")
                continue
            try:
                label = self.docker.inspect_label(resource, resource_id, OWNER_LABEL)
            except DockerError:
                label = None
            if label != self.token:
                remaining.append(f"docker:{resource}:{name}")
                continue
            try:
                if resource == "network":
                    self.docker.remove_network(resource_id)
                else:
                    self.docker.remove_container(resource_id)
            except DockerError:
                remaining.append(f"docker:{resource}:{name}")
        return remaining

    # -- orchestration ----------------------------------------------------

    def run(self) -> int:
        started = time.time()
        failure: str | None = None
        attach: Attach | None = None
        result_dir: Path | None = None
        data: dict | None = None
        try:
            self._prepare_dirs()
            if not self.docker.available():
                raise DockerError("docker_unavailable")
            if not self.docker.image_exists(RUNNER_IMAGE):
                self._build_runner()
            if self.docker.image_arch(RUNNER_IMAGE) != EXPECTED_RUNNER_ARCH:
                raise DockerError("runner_platform_mismatch")
            self.pg_image_used = self._select_pg_image()
            self._write_env_files()
            network_id = self.docker.network_create(self.names["net"], self._labels())
            self.resources.append(("network", network_id, self.names["net"]))
            pg_id = self.docker.container_create_pg(
                self.pg_image_used,
                self.names["pg"],
                network_id,
                self.names["pg"],
                self.scratch / "pg.env",
                self._labels(),
            )
            self.resources.append(("container", pg_id, self.names["pg"]))
            self.docker.container_start(pg_id)
            if not self._wait_ready(pg_id):
                raise DockerError("postgres_not_ready")
            runner_id = self.docker.container_create_runner(
                RUNNER_IMAGE,
                self.names["runner"],
                network_id,
                self.scratch / "runner.env",
                self._labels(),
                self._safe_mount(self.repo),
                self._safe_mount(self.demo_root),
            )
            self.resources.append(("container", runner_id, self.names["runner"]))
            attach = self.docker.attach_runner(runner_id, self.timeout)
            if attach.timed_out:
                raise DockerError("demo_timeout")
            result_dir = self._translate(attach.output)
            if result_dir is None:
                raise DockerError("demo_result_missing")
            data = self._read_result(result_dir)
        except DockerError as exc:
            failure = exc.reason
        except Exception as exc:  # noqa: BLE001 - never expose internal detail
            failure = "launcher_error_" + type(exc).__name__
        finally:
            try:
                self.remaining = self._cleanup()
            finally:
                self._remove_secret_files()

        if data is not None and result_dir is not None and self.remaining:
            self._merge_result(result_dir, data)
        exit_code = self._exit_code(failure, attach, data)
        self._write_summary(failure, attach, data, exit_code, started)
        self._report(failure, result_dir, data, exit_code)
        return exit_code

    def _exit_code(self, failure: str | None, attach: Attach | None, data: dict | None) -> int:
        if data is None or failure is not None:
            if failure in {
                "docker_unavailable",
                "docker_command_failed",
                "dockerfile_missing",
                "runner_platform_mismatch",
                "unsafe_directory",
            }:
                return 2
            return 1
        if self.remaining:
            return 1
        native = attach.exit_code if attach is not None else None
        if native is None:
            return 1
        if native != 0:
            return native if 0 < native < 126 else 1
        return 0 if data.get("passed") is True else 1

    def _write_summary(
        self,
        failure: str | None,
        attach: Attach | None,
        data: dict | None,
        exit_code: int,
        started: float,
    ) -> None:
        summary = {
            "run_id": self.token,
            "runner_image": RUNNER_IMAGE,
            "pg_image": self.pg_image_used,
            "native_exit": attach.exit_code if attach is not None else None,
            "timed_out": bool(attach.timed_out) if attach is not None else None,
            "docker_cleanup_ok": not self.remaining,
            "resources_remaining": list(self.remaining),
            "failure": failure,
            "exit_code": exit_code,
            "demo_result_valid": data is not None,
            "started_at": int(started),
            "ended_at": int(time.time()),
            "resource_names": [name for _, _, name in self.resources],
        }
        payload = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
            descriptor = os.open(self.scratch / "launcher.json", flags, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
        except OSError:
            pass

    def _report(
        self,
        failure: str | None,
        result_dir: Path | None,
        data: dict | None,
        exit_code: int,
    ) -> None:
        if data is not None and result_dir is not None:
            passed = data.get("passed") is True and exit_code == 0
            print(
                "x402 采购固定演示（Docker 隔离运行）："
                + ("全部用例符合预期" if passed else "存在未符合预期的用例或资源"),
                flush=True,
            )
            for case in data["cases"]:
                line = f"  {case['name']}: {'通过' if case['passed'] else '未通过'}"
                if "http_status" in case:
                    line += f"（HTTP {case['http_status']}"
                    line += f" {case['code']}）" if case.get("code") else "）"
                print(line, flush=True)
            print(
                f"  操作 {data['operations']}，批准绑定 {data['approvals']}，"
                f"下游订单 {data['orders']}，支付 {data['payments']}，"
                f"交易 {data['transactions']}，资源剩余 {len(data['resources_remaining'])}",
                flush=True,
            )
            print(RESULT_LINE, result_dir, flush=True)
            return
        message = PUBLIC_MESSAGES.get(failure or "", "本次运行未成功")
        print(f"x402 采购演示未完成：{message}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="演示总限时秒数")
    parser.add_argument("--pg-image", default=None, help="覆盖临时 PostgreSQL 镜像")
    parser.add_argument(
        "--approval-scheme",
        choices=sorted(APPROVAL_SCHEMES),
        default="frost-ed25519",
        help="网关批准方案：frost-ed25519（默认）或 sm2-2p（双域共签）",
    )
    args = parser.parse_args(argv)
    os.umask(0o077)
    if not 1.0 <= args.timeout <= 7200.0:
        print("x402 采购演示未完成：限时参数无效", file=sys.stderr)
        return 2
    launcher = Launcher(
        timeout=args.timeout, pg_image=args.pg_image, approval_scheme=args.approval_scheme
    )
    return launcher.run()


if __name__ == "__main__":
    raise SystemExit(main())
