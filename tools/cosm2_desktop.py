"""Host launcher: run the fixed cosm2-gateway demo entirely inside Docker.

Ordinary desktop Python 3 (standard library only) starts this CLI. It creates
exactly owned, random-labelled Docker resources -- a private bridge network,
one temporary PostgreSQL 16 container without published ports and one runner
container from the fixed threshold runner image -- and then runs
the fixed ``tools/cosm2_gateway_demo.py`` inside that network. No host
cryptography or psycopg is installed and no DSN is exported by the operator:
the private test DSN is written only to a mode-0600 ``--env-file`` that Docker
reads, so it never appears in a command line or in this program's output.

Cleanup verifies the random run label by resource ID before removing anything
and never inspects or prunes resources it did not create. The demo prints its
result directory as a container path (``/work/...``); this launcher translates
that to the validated repository path under
``artifacts/cosm2-gateway-demo-live/<run id>``, preserves the native demo
exit status and, when Docker cleanup failed, marks the sanitized result as
failed and increments ``resources_remaining`` instead of claiming success.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

RUNNER_IMAGE = "agent-guard-threshold-gateway-runner:20261017"
PG_IMAGES = ("postgres:16-alpine", "postgres:16", "postgres:16-bookworm")
DEMO_ROOT_REL = Path("artifacts/cosm2-gateway-demo-live")
SCRATCH_ROOT_REL = Path("artifacts/cosm2-gateway-desktop")
WORKDIR = "/work"
RESULT_LINE = "结果目录："
OWNER_LABEL = "agent-guard.cosm2-desktop"
PURPOSE_LABEL = "agent-guard.purpose"
PURPOSE_VALUE = "cosm2-desktop-demo"
OUTPUT_CAP = 262_144
READY_TIMEOUT = 90.0
DEFAULT_TIMEOUT = 900.0
MAX_RESULT_BYTES = 1_000_000

PUBLIC_MESSAGES = {
    "runner_missing": "缺少固定协同签名运行镜像，请先按部署说明安装",
    "docker_unavailable": "Docker Desktop 未就绪或不可访问",
    "docker_command_failed": "Docker 命令未成功",
    "dockerfile_missing": "缺少 deploy/cosm2-runner/Dockerfile",
    "runner_platform_mismatch": "协同签名运行镜像不是 linux/amd64",
    "postgres_not_ready": "临时 PostgreSQL 未在限时内就绪",
    "demo_timeout": "演示限时内未完成，已停止运行容器",
    "demo_result_missing": "演示未返回可验证的结果目录",
    "demo_result_invalid": "演示结果文件不符合固定格式",
    "unsafe_directory": "本机结果目录不是安全的真实目录",
}


class DockerError(Exception):
    """A sanitized Docker-side failure; the reason is a public-safe token."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Attach:
    """Bounded, in-memory view of one runner container execution."""

    output: bytes
    exit_code: int | None
    timed_out: bool


def find_docker() -> str:
    """Locate the Docker CLI, preferring an explicit override."""
    candidates = []
    override = os.environ.get("AGENT_GUARD_DOCKER")
    if override:
        candidates.append(override)
    candidates.extend(
        (
            "docker",
            "/usr/local/bin/docker",
            "/opt/homebrew/bin/docker",
            "/Applications/Docker.app/Contents/Resources/bin/docker",
        )
    )
    for candidate in candidates:
        if os.sep in candidate:
            if os.access(candidate, os.X_OK):
                return candidate
            continue
        found = shutil.which(candidate)
        if found:
            return found
    return "docker"


class Docker:
    """Thin wrapper around the Docker CLI; never echoes raw stderr to callers."""

    def __init__(self, binary: str):
        self.binary = binary

    def _capture(
        self,
        args: list[str],
        timeout: float,
        *,
        cwd: Path | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        try:
            completed = subprocess.run(
                [self.binary, *args],
                capture_output=True,
                timeout=timeout,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise DockerError("docker_command_failed") from exc
        if check and completed.returncode != 0:
            error = DockerError("docker_command_failed")
            # Kept in memory only for callers that need it; never printed.
            error.detail = completed.stderr[-4096:]
            raise error
        return completed

    def available(self) -> bool:
        try:
            return self._capture(["version", "--format", "{{.Server.Version}}"], 45).returncode == 0
        except DockerError:
            return False

    def image_exists(self, image: str) -> bool:
        return self._capture(["image", "inspect", image], 60).returncode == 0

    def image_arch(self, image: str) -> str:
        completed = self._capture(
            ["image", "inspect", "--format", "{{.Architecture}}", image], 60, check=True
        )
        return completed.stdout.decode("utf-8", "replace").strip()

    def network_create(self, name: str, labels: dict[str, str]) -> str:
        args = ["network", "create"]
        for key, value in sorted(labels.items()):
            args += ["--label", f"{key}={value}"]
        args.append(name)
        return self._capture(args, 60, check=True).stdout.decode().strip()

    def container_create_pg(
        self,
        image: str,
        name: str,
        network: str,
        alias: str,
        env_file: Path,
        labels: dict[str, str],
    ) -> str:
        args = ["create", "--pull", "never", "--name", name]
        for key, value in sorted(labels.items()):
            args += ["--label", f"{key}={value}"]
        args += [
            "--network",
            network,
            "--network-alias",
            alias,
            "--env-file",
            str(env_file),
            "--tmpfs",
            "/var/lib/postgresql/data:rw",
            image,
        ]
        return self._capture(args, 60, check=True).stdout.decode().strip()

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
        args = ["create", "--pull", "never", "--name", name]
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
            f"type=bind,src={demo_mount},dst={WORKDIR}/artifacts/cosm2-gateway-demo-live",
            "-w",
            WORKDIR,
            image,
            "/opt/venv/bin/python",
            "tools/cosm2_gateway_demo.py",
        ]
        return self._capture(args, 60, check=True).stdout.decode().strip()

    def container_start(self, container_id: str) -> None:
        self._capture(["start", container_id], 120, check=True)

    def exec_ready(self, container_id: str, user: str, database: str) -> bool:
        completed = self._capture(
            ["exec", container_id, "pg_isready", "-U", user, "-d", database], 30
        )
        return completed.returncode == 0

    def attach_runner(self, container_id: str, timeout: float) -> Attach:
        try:
            process = subprocess.Popen(
                [self.binary, "start", "-a", container_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                bufsize=0,
            )
        except OSError as exc:
            raise DockerError("docker_command_failed") from exc
        chunks: list[bytes] = []
        total = 0

        def drain() -> None:
            nonlocal total
            assert process.stdout is not None
            while True:
                block = process.stdout.read(65536)
                if not block:
                    return
                if total < OUTPUT_CAP:
                    take = block[: OUTPUT_CAP - total]
                    chunks.append(take)
                    total += len(take)

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        if timed_out:
            try:
                self._capture(["kill", container_id], 30)
            except DockerError:
                pass
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        reader.join(timeout=15)
        if process.stdout is not None:
            try:
                process.stdout.close()
            except OSError:
                pass
        return Attach(
            output=b"".join(chunks),
            exit_code=self.container_exit_code(container_id),
            timed_out=timed_out,
        )

    def container_exit_code(self, container_id: str) -> int | None:
        completed = self._capture(["inspect", "--format", "{{.State.ExitCode}}", container_id], 30)
        if completed.returncode != 0:
            return None
        try:
            return int(completed.stdout.decode().strip())
        except ValueError:
            return None

    def inspect_label(self, resource: str, resource_id: str, label: str) -> str | None:
        if resource == "network":
            args = ["network", "inspect", "--format", f'{{{{ index .Labels "{label}" }}}}']
        else:
            args = ["inspect", "--format", f'{{{{ index .Config.Labels "{label}" }}}}']
        completed = self._capture([*args, resource_id], 30)
        if completed.returncode != 0:
            return None
        value = completed.stdout.decode("utf-8", "replace").strip()
        return None if value in ("", "<no value>") else value

    def remove_container(self, container_id: str) -> None:
        self._capture(["rm", "-f", container_id], 120, check=True)

    def remove_network(self, network_id: str) -> None:
        self._capture(["network", "rm", network_id], 60, check=True)


class Launcher:
    """One isolated demo run with exactly owned Docker resources."""

    def __init__(
        self,
        repo: Path = REPO,
        *,
        docker: Docker | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        pg_image: str | None = None,
        environ: dict[str, str] | None = None,
    ):
        self.repo = Path(repo).resolve()
        self.docker = docker if docker is not None else Docker(find_docker())
        self.timeout = float(timeout)
        self.pg_image = pg_image
        self.environ = dict(os.environ if environ is None else environ)
        self.token = uuid.uuid4().hex
        self.names = {
            "pg": f"ag-cosm2desk-pg-{self.token[:12]}",
            "runner": f"ag-cosm2desk-runner-{self.token[:12]}",
            "net": f"ag-cosm2desk-net-{self.token[:12]}",
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
        self._write_env_file(
            pg_env,
            {
                "POSTGRES_USER": self.user,
                "POSTGRES_PASSWORD": self.password,
                "POSTGRES_DB": self.database,
            },
        )
        self._write_env_file(
            runner_env,
            {
                "AGENT_GUARD_COSM2_DEMO_DSN": self._dsn(),
                "PYTHONPATH": f"{WORKDIR}/src",
            },
        )
        self.secret_files = [pg_env, runner_env]

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
        raise DockerError("runner_missing")

    def _safe_mount(self, path: Path) -> Path:
        text = str(path)
        if "," in text or '"' in text:
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
        if not folder or not folder.startswith(WORKDIR + "/"):
            return None
        relative = folder[len(WORKDIR) + 1 :]
        parts = Path(relative).parts
        expected = DEMO_ROOT_REL.parts
        if ".." in parts or Path(relative).is_absolute():
            return None
        if len(parts) != len(expected) + 1 or tuple(parts[: len(expected)]) != expected:
            return None
        try:
            run_id = str(uuid.UUID(parts[-1]))
        except ValueError:
            return None
        candidate = self.repo / DEMO_ROOT_REL / run_id
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
            from tools.teacher_demo_server import unique_object

            data = json.loads(
                result_file.read_text(encoding="utf-8"), object_pairs_hook=unique_object
            )
        except (OSError, ValueError) as exc:
            raise DockerError("demo_result_invalid") from exc
        self._validate_result(data, result_dir.name)
        return data

    @staticmethod
    def _validate_result(data: object, run_id: str) -> None:
        from tools.teacher_demo_server import validate_cosm2_result

        try:
            validate_cosm2_result(data, run_id)
        except (ValueError, TypeError, KeyError) as exc:
            raise DockerError("demo_result_invalid") from exc

    def _merge_result(self, result_dir: Path, data: dict) -> None:
        data["resources_remaining"] += len(self.remaining)
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
            if self.docker.image_arch(RUNNER_IMAGE) != "amd64":
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
            self.remaining = self._cleanup()
            self._remove_secret_files()

        if data is not None and self.remaining:
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
                "runner_missing",
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
                "协同签名采购固定演示（Docker 隔离运行）："
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
                f"下游订单 {data['orders']}，资源剩余 {data['resources_remaining']}",
                flush=True,
            )
            print(RESULT_LINE, result_dir, flush=True)
            return
        message = PUBLIC_MESSAGES.get(failure or "", "本次运行未成功")
        print(f"协同签名采购演示未完成：{message}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="演示总限时秒数")
    parser.add_argument("--pg-image", default=None, help="覆盖临时 PostgreSQL 镜像")
    args = parser.parse_args(argv)
    os.umask(0o077)
    if not 1.0 <= args.timeout <= 7200.0:
        print("协同签名采购演示未完成：限时参数无效", file=sys.stderr)
        return 2
    launcher = Launcher(timeout=args.timeout, pg_image=args.pg_image)
    return launcher.run()


if __name__ == "__main__":
    raise SystemExit(main())
