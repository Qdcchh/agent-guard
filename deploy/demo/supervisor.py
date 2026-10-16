"""Finite trusted owner supervisor. Control uses private operator exec pipes only.

The normal operator has neither host credentials nor a Docker socket. Every
resource and fixed child command is checked against this run's full identities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROLES = sorted(
    (
        "operator",
        "as",
        "gateway",
        "did",
        "audit",
        "publisher",
        "worker",
        "planner",
        "selector",
        "executor",
        "export",
        "offline",
    )
)
UIDS = {role: 21000 + i for i, role in enumerate(ROLES)}
WRITERS = ("as", "gateway", "worker", "publisher")
REPO = Path(__file__).resolve().parents[2]


def atomic(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


class Owner:
    def __init__(self, args):
        self.args = args
        self.run = str(uuid.UUID(args.run_id))
        self.owner = args.owner_id
        self.project = "ag33-" + self.run
        self.root = Path(args.evidence).resolve()
        self.root.mkdir(parents=True, exist_ok=False)
        self.control = self.root / "control"
        self.control.mkdir()
        self.image = "agent-guard-normal-" + args.mode + ":" + self.run
        subnet = "10." + str(100 + int(self.run[:2], 16) % 80) + "." + str(int(self.run[2:4], 16))
        self.env = {
            **os.environ,
            "AG33_PROJECT": self.project,
            "AG33_CONTROL": str(self.control),
            "AG33_IMAGE": self.image,
            "AG33_RUN_ID": self.run,
            "AG33_OWNER_ID": self.owner,
            "AG33_SUBNET_PREFIX": subnet,
        }
        for key in tuple(self.env):
            if key.startswith("AGENT_GUARD_") or key == "PYTHONPATH":
                self.env.pop(key)
        # Docker's host client keeps its host proxy. RUN steps get a separate VM endpoint.
        from urllib.parse import urlsplit

        self.build_proxy_args = []
        for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            value = self.env.get(key) or self.env.get(key.lower())
            if value:
                parsed = urlsplit(value)
                if parsed.username or parsed.password:
                    raise ValueError("credentialed build proxy requires private supported channel")
                mapped = (
                    value.replace(parsed.hostname, "host.docker.internal", 1)
                    if parsed.hostname in ("127.0.0.1", "localhost")
                    else value
                )
                self.build_proxy_args += ["--build-arg", key + "=" + mapped]
        self.settings = {
            "run_id": self.run,
            "owner_id": self.owner,
            "uids": UIDS,
            "capacity_items": args.capacity_items,
            "audit_listener_host": subnet + ".13",
        }
        atomic(self.control / "settings.json", self.settings)
        self.ids = {}
        self.volumes = []
        self.networks = []
        self.children = {}
        self.logs = []
        self.seq = 0
        self.write_lock = threading.Lock()
        self.queues = {}
        self.bridge = None

    def call(self, argv, *, input=None, timeout=120, allow=False, private=False):
        shown = [
            a.split("=", 1)[0] + "=<REDACTED_BUILD_PROXY>" if "_proxy=" in a.lower() else a
            for a in argv
        ]
        self.seq += 1
        stem = self.root / f"{self.seq:04d}-native"
        started = time.time()
        stdout_path = stem.with_suffix(".stdout")
        stderr_path = stem.with_suffix(".stderr")
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                env=self.env,
            )
            atomic(
                stem.with_suffix(".started.json"),
                {"argv": shown, "pid": process.pid, "started": started, "timeout": timeout},
            )
            try:
                process.communicate(input=input, timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                atomic(
                    stem.with_suffix(".json"),
                    {
                        "argv": shown,
                        "native_exit": process.returncode,
                        "timed_out": True,
                        "timeout": timeout,
                    },
                )
                raise
        result = subprocess.CompletedProcess(
            argv, process.returncode, stdout_path.read_bytes(), stderr_path.read_bytes()
        )
        stem.with_suffix(".stdout").write_bytes(
            b"PRIVATE_OUTPUT_RETAINED_ONLY_IN_MEMORY\n" if private else result.stdout
        )
        stem.with_suffix(".stderr").write_bytes(result.stderr)
        atomic(
            stem.with_suffix(".json"),
            {
                "argv": shown,
                "native_exit": result.returncode,
                "started": started,
                "elapsed": time.time() - started,
                "private_output": private,
            },
        )
        if result.returncode and not allow:
            raise RuntimeError("native command failed: " + str(stem))
        return result

    def inspect(self, role):
        expected = self.ids[role]
        value = json.loads(self.call(["docker", "inspect", expected]).stdout)[0]
        labels = value["Config"]["Labels"]
        if (
            value["Id"] != expected
            or labels.get("agent-guard.run") != self.run
            or labels.get("agent-guard.owner") != self.owner
        ):
            raise ValueError("owned resource mismatch")
        return value

    def capture(self, name, container):
        value = json.loads(self.call(["docker", "inspect", container]).stdout)[0]
        if (
            value["Config"]["Labels"].get("agent-guard.owner") != self.owner
            or value["Config"]["Labels"].get("agent-guard.run") != self.run
        ):
            raise ValueError("creation receipt mismatch")
        self.ids[name] = value["Id"]
        atomic(
            self.root / "owned-resources.json",
            {"ids": self.ids, "volumes": self.volumes, "networks": self.networks},
        )
        return value["Id"]

    def compose(self, *arguments):
        return self.call(
            [
                "docker",
                "compose",
                "-f",
                str(REPO / "deploy/demo/compose.yaml"),
                "--project-name",
                self.project,
                *arguments,
            ],
            timeout=300,
        )

    def actor(self, role, stage, *extra, timeout=120):
        self.inspect(role)
        argv = [
            "docker",
            "exec",
            "-i",
            self.ids[role],
            "python",
            "-m",
            "agent_guard.demo",
            "actor",
            "--stage",
            stage,
            "--role",
            role,
        ]
        if extra:
            argv += ["--extra", *extra]
        return self.call(argv, timeout=timeout).stdout

    def init(self, stage, program=None):
        name = "init-" + stage + "-" + str(self.seq)
        argv = [
            "docker",
            "run",
            "--name",
            self.project + "-" + name,
            "--user",
            "0:0",
            "--network",
            "none",
            "--label",
            "agent-guard.owner=" + self.owner,
            "--label",
            "agent-guard.run=" + self.run,
            "--mount",
            "type=volume,src=" + self.project + "-private,dst=/owned",
            "--mount",
            "type=volume,src=" + self.project + "-public,dst=/public",
            "--mount",
            "type=volume,src=" + self.project + "-registry,dst=/registry",
            "--mount",
            "type=volume,src=" + self.project + "-outputs,dst=/results",
            "--mount",
            "type=volume,src=" + self.project + "-operator-tmp,dst=/operator-tmp",
            "--mount",
            "type=bind,src=" + str(self.control) + ",dst=/control,readonly",
            self.image,
            "python",
        ]
        argv += (
            ["-c", program] if program else ["-m", "agent_guard.demo", "actor", "--stage", stage]
        )
        try:
            return self.call(argv, timeout=180).stdout
        finally:
            value = self.call(["docker", "inspect", self.project + "-" + name], allow=True)
            if value.returncode == 0:
                self.capture(name, self.project + "-" + name)

    def build(self):
        context = self.root / "build-context"
        context.mkdir()
        for name in ("src", "migrations"):
            shutil.copytree(
                REPO / name, context / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
            )
        for name in ("pyproject.toml", "requirements.lock", "requirements-dev.lock", "README.md"):
            shutil.copyfile(REPO / name, context / name)
        shutil.copytree(REPO / "deploy/demo", context / "deploy/demo")
        atomic(
            self.root / "source-input-sha.json",
            {
                str(p.relative_to(context)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in context.rglob("*")
                if p.is_file()
            },
        )
        self.call(
            [
                "docker",
                "build",
                "--platform",
                "linux/amd64",
                "--build-arg",
                "INSTALL_MODE=" + self.args.mode,
                *self.build_proxy_args,
                "--add-host",
                "host.docker.internal:host-gateway",
                "-f",
                str(context / "deploy/demo/Dockerfile"),
                "-t",
                self.image,
                str(context),
            ],
            timeout=1800,
        )

    def provenance(self):
        modules = [
            "agent_guard.demo." + name
            for name in (
                "__init__",
                "config",
                "init",
                "did_bootstrap",
                "provision",
                "client",
                "handoff",
                "worker",
                "__main__",
                "holder",
                "runner",
                "faults",
            )
        ] + ["agent_guard.audit." + name for name in ("config", "server", "delivery", "contracts")]
        program = """
import dataclasses, hashlib, importlib, importlib.metadata, inspect, json, platform, sys
from pathlib import Path

assert sys.version_info[:2] == (3, 11)
rows = []
for name in MODULES:
    module = importlib.import_module(name)
    path = Path(module.__file__)
    assert "site-packages" in path.parts
    symbols = {}
    for key, value in vars(module).items():
        if (
            not key.startswith("_")
            and (inspect.isfunction(value) or inspect.isclass(value))
            and value.__module__ == module.__name__
        ):
            try:
                signature = str(inspect.signature(value))
            except (ValueError, TypeError):
                signature = None
            symbols[key] = {
                "signature": signature,
                "fields": [f.name for f in dataclasses.fields(value)]
                if inspect.isclass(value) and dataclasses.is_dataclass(value)
                else [],
            }
    rows.append(
        {
            "module": name,
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "symbols": symbols,
        }
    )
assert not any(n == "tests" or n.startswith("tests.") for n in sys.modules)
print(
    json.dumps(
        {
            "python": sys.version,
            "architecture": platform.machine(),
            "modules": rows,
            "versions": {n: importlib.metadata.version(n) for n in LOCKS},
            "SQL": {
                str(p.relative_to(sys.prefix)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in Path(sys.prefix).rglob("share/agent-guard/migrations/**/*.sql")
            },
            "wheel": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in Path("/wheels").glob("*.whl")
            },
        }
    )
)
"""
        locks = {}
        for line in (REPO / "requirements.lock").read_text().splitlines():
            if "==" in line and not line.startswith("#"):
                name, version = line.split("==")
                locks[name] = version
        raw = self.init(
            "install-provenance",
            program.replace("MODULES", repr(modules)).replace("LOCKS", repr(locks)),
        )
        value = json.loads(raw)
        if value["versions"] != locks:
            raise ValueError("actual lock versions differ")
        for row in value["modules"]:
            relative = "src/" + row["module"].replace(".", "/") + ".py"
            if hashlib.sha256((REPO / relative).read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("installed module differs from current candidate")
        atomic(self.root / "install-provenance.json", value)

    def setup(self):
        self.build()
        for suffix in (
            "private",
            "public",
            "registry",
            "outputs",
            "operator-tmp",
            "pgdata-authority",
            "pgdata-downstream",
            "pgdata-audit",
        ):
            name = self.project + "-" + suffix
            self.call(
                [
                    "docker",
                    "volume",
                    "create",
                    "--label",
                    "agent-guard.owner=" + self.owner,
                    "--label",
                    "agent-guard.run=" + self.run,
                    name,
                ]
            )
            self.volumes.append(name)
        for suffix in ("front", "authority", "downstream", "audit"):
            name = self.project + "-" + suffix
            argv = [
                "docker",
                "network",
                "create",
                "--internal",
                "--label",
                "agent-guard.owner=" + self.owner,
                "--label",
                "agent-guard.run=" + self.run,
            ]
            if suffix == "front":
                argv += ["--subnet", self.env["AG33_SUBNET_PREFIX"] + ".0/24"]
            result = self.call([*argv, name])
            self.networks.append({"name": name, "id": result.stdout.decode().strip()})
        self.provenance()
        self.init("init")
        self.init("pg-init")
        self.compose("up", "-d", "pg-authority", "pg-downstream", "pg-audit")
        for domain in ("authority", "downstream", "audit"):
            name = "pg-" + domain
            container = self.compose("ps", "-q", name).stdout.decode().strip()
            self.capture(name, container)
            deadline = time.monotonic() + 90
            while True:
                result = self.call(
                    [
                        "docker",
                        "exec",
                        self.ids[name],
                        "pg_isready",
                        "-h",
                        "127.0.0.1",
                        "-U",
                        "postgres",
                        "-d",
                        "ag_" + domain,
                    ],
                    allow=True,
                )
                if result.returncode == 0:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("PG TCP readiness deadline")
                time.sleep(0.2)
            locale = self.call(
                [
                    "docker",
                    "exec",
                    self.ids[name],
                    "psql",
                    "-U",
                    "postgres",
                    "-d",
                    "ag_" + domain,
                    "-Atc",
                    (
                        "SELECT datcollate,datctype,pg_encoding_to_char(encoding) F"
                        "ROM pg_database WHERE datname=current_database()"
                    ),
                ]
            ).stdout.strip()
            if locale != b"C|C|UTF8":
                raise ValueError("PG locale/encoding mismatch")
        self.compose("up", "-d", *ROLES)
        for role in ROLES:
            self.capture(role, self.compose("ps", "-q", role).stdout.decode().strip())
        manifest = {
            "version": "demo-v2",
            "run_id": self.run,
            "owner_id": self.owner,
            "project": self.project,
            "roles": {
                r: {
                    "uid": UIDS[r],
                    "gid": UIDS[r],
                    "listener_host": self.env["AG33_SUBNET_PREFIX"]
                    + "."
                    + str({"did": 10, "as": 11, "gateway": 12, "audit": 13}[r])
                    if r in ("did", "as", "gateway", "audit")
                    else None,
                    "container_id": self.ids[r],
                }
                for r in ROLES
            },
            "databases": {
                d: "pg-" + d + ".agent-guard.test" for d in ("authority", "downstream", "audit")
            },
            "networks": [x["name"] for x in self.networks],
        }
        atomic(self.control / "allocated-plan.json", manifest)
        messages = self.actor("operator", "messages")
        (self.control / "approval-messages.json").write_bytes(messages)
        proofs = {
            "agent-" + r: self.actor(r, "proof").decode().strip()
            for r in ("planner", "selector", "executor")
        }
        atomic(self.control / "approval-proofs.json", proofs)
        self.actor("operator", "approve")
        self.init("activate")
        self.actor("operator", "provision")
        self.actor("audit", "audit-migrate")
        for domain in ("authority", "downstream", "audit"):
            self.actor("audit" if domain == "audit" else "operator", "grants", domain)
        for role in ROLES:
            self.actor(role, "role-precheck")
        self.call(
            [
                "docker",
                "cp",
                self.ids["operator"] + ":/owned/run/run.json",
                str(self.root / "run.json"),
            ]
        )
        atomic(self.root / "allocated-resources.json", manifest)
        self.start_bridge()

    def command(self, role, stage):
        self.inspect(role)
        return [
            "docker",
            "exec",
            "-i",
            self.ids[role],
            "python",
            "-u",
            "-m",
            "agent_guard.demo",
            *stage,
        ]

    def start_child(self, role, stage):
        previous = self.children.get(role)
        if previous and previous["process"].poll() is None:
            raise ValueError("role already running")
        generation = 1 + (previous["generation"] if previous else 0)
        stdout = (self.root / (role + "-" + str(generation) + ".stdout")).open("wb")
        stderr = (self.root / (role + "-" + str(generation) + ".stderr")).open("wb")
        process = subprocess.Popen(
            self.command(role, stage),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
            env=self.env,
        )
        self.logs.extend((stdout, stderr))
        row = {
            "process": process,
            "stderr": stderr,
            "generation": generation,
            "role": role,
            "container_id": self.ids[role],
        }
        self.children[role] = row

        def finalize():
            code = process.wait()
            stdout.flush()
            stderr.flush()
            atomic(
                self.root / (role + "-" + str(generation) + ".native-exit.json"),
                {
                    "native_exit": code,
                    "launcher_pid": process.pid,
                    "role": role,
                    "argv": process.args,
                    "run_id": self.run,
                    "owner_id": self.owner,
                },
            )

        row["finalizer"] = threading.Thread(target=finalize, daemon=True)
        row["finalizer"].start()
        return row

    def ready(self, include_audit=False):
        program = (
            "import socket,time;\nfor host in ['auth.agent-guard.test','"
            "gateway.agent-guard.test','audit.agent-guard.test']:\n dead"
            "line=time.monotonic()+30\n while True:\n  try:s=socket.creat"
            "e_connection((host,443),1);s.close();break\n  except OSErro"
            "r:\n   assert time.monotonic()<deadline;time.sleep(.05)"
        )
        if not include_audit:
            program = program.replace(",'audit.agent-guard.test'", "")
        self.call(["docker", "exec", self.ids["operator"], "python", "-c", program])

    def services(self, resume=False):
        roles = WRITERS if resume else ("as", "gateway")
        for role in roles:
            if resume:
                self.call(["docker", "start", self.ids[role]])
            stage = (
                ["worker-serve"]
                if role == "worker"
                else ["publisher-serve"]
                if role == "publisher"
                else ["actor", "--stage", role, "--role", role]
            )
            self.start_child(role, stage)
        if resume and "audit" not in self.children:
            self.start_child("audit", ["audit-serve"])
        self.ready(include_audit=resume)

    def writer_status(self, role):
        if role not in WRITERS:
            raise ValueError("fixed authority writer")
        row = self.children[role]
        process = row["process"]
        row["stderr"].flush()
        native = []
        deadline = time.monotonic() + 15
        while not native:
            row["stderr"].flush()
            for line in Path(row["stderr"].name).read_bytes().splitlines():
                try:
                    value = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if value.get("native_process"):
                    native.append(value)
            if not native:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise ValueError("missing actual role kernel identity")
                time.sleep(0.02)
        value = native[0]
        inspected = self.inspect(role)
        return {
            "role": role,
            "pid": value["pid"],
            "uid": value["uid"],
            "start_identity": str(value["start_ticks"]) + ":" + inspected["State"]["StartedAt"],
            "argv_sha256": value["argv_sha256"],
            "argv_nul_hex": value["argv_nul_hex"],
            "container_id": self.ids[role],
            "launcher_pid": process.pid,
            "native_exit": process.poll(),
            "container_stopped": not inspected["State"]["Running"],
        }

    def drain(self):
        # Before bootstrap only AS/GW were active; start finite idle writer actors
        # so all four native handles/credential unmounts are observed, never fabricated.
        for role in WRITERS:
            if role not in self.children:
                self.start_child(role, ["actor", "--stage", "hold", "--role", role])
        identities = {r: self.writer_status(r) for r in WRITERS}
        for role in WRITERS:
            row = identities[role]
            program = (
                "import os,signal;from pathlib import Path;p="
                + str(row["pid"])
                + ";stat=Path('/proc/'+str(p)+'/stat').read_text().split();assert stat[21]=="
                + repr(row["start_identity"].split(":")[0])
                + (
                    ";assert int(Path('/proc/'+str(p)+'/status').read_text().sp"
                    "lit('Uid:')[1].split()[0])=="
                )
                + str(UIDS[role])
                + ";os.kill(p,signal.SIGTERM)"
            )
            self.call(["docker", "exec", self.ids[role], "python", "-c", program])
            try:
                self.children[role]["process"].wait(timeout=15)
            except subprocess.TimeoutExpired:
                raise ValueError("graceful owned writer drain deadline") from None
            self.inspect(role)
            self.call(["docker", "stop", "--time", "10", self.ids[role]])
        rows = [self.writer_status(r) for r in WRITERS]
        for row in rows:
            old = identities[row["role"]]
            if (
                row["uid"] != UIDS[row["role"]]
                or row["pid"] != old["pid"]
                or row["native_exit"] is None
                or not row["container_stopped"]
            ):
                raise ValueError("actual writer drain failed")
        atomic(self.root / ("drain-" + str(self.seq) + ".json"), rows)
        return rows

    def start_bridge(self):
        stderr = (self.root / "operator-bridge.stderr").open("wb")
        self.logs.append(stderr)
        self.bridge = subprocess.Popen(
            self.command("operator", ["bridge"]),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            bufsize=0,
            start_new_session=True,
            env=self.env,
        )
        threading.Thread(target=self.read_bridge, daemon=True).start()
        deadline = time.monotonic() + 20
        while True:
            result = self.call(
                [
                    "docker",
                    "exec",
                    self.ids["operator"],
                    "python",
                    "-c",
                    (
                        "from pathlib import Path;raise SystemExit(0 if Path('/tmp/"
                        "agent-guard-control/bridge.sock').is_socket() else 1)"
                    ),
                ],
                allow=True,
            )
            if result.returncode == 0:
                break
            if self.bridge.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("private bridge readiness")
            time.sleep(0.1)

    def reply(self, ident, value=None, close=False):
        row = {"id": ident, "event": "close" if close else "data"}
        if not close:
            row["value"] = value
        with self.write_lock:
            self.bridge.stdin.write(json.dumps(row, separators=(",", ":")).encode() + b"\n")
            self.bridge.stdin.flush()

    def read_bridge(self):
        try:
            for raw in self.bridge.stdout:
                if len(raw) > 65536:
                    raise ValueError("private bridge bound")
                row = json.loads(raw)
                ident = row["id"]
                if row["event"] == "open":
                    value = row["value"]
                    if (value.get("run_id"), value.get("owner_id")) != (self.run, self.owner):
                        raise ValueError("private bridge scope")
                    self.queues[ident] = queue.Queue()
                    threading.Thread(target=self.dispatch, args=(ident, value), daemon=True).start()
                elif ident in self.queues:
                    self.queues[ident].put(row)
        finally:
            atomic(
                self.root / "bridge-native-exit.json",
                {"native_exit": self.bridge.wait(), "launcher_pid": self.bridge.pid},
            )

    def dispatch(self, ident, value):
        try:
            action = value["action"]
            fields = set(value) - {"run_id", "owner_id", "action"}
            if action == "holder":
                if fields != {"role"} or value["role"] not in ("planner", "selector", "executor"):
                    raise ValueError("fixed holder request")
                process = subprocess.Popen(
                    [
                        "docker",
                        "exec",
                        "-i",
                        self.ids[value["role"]],
                        "python",
                        "-u",
                        "-m",
                        "agent_guard.demo.holder",
                        "--config",
                        "/owned/run/run.json",
                        "--role",
                        value["role"],
                        "--capacity-items",
                        str(self.args.capacity_items),
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=(self.root / ("holder-" + value["role"] + ".stderr")).open("wb"),
                    bufsize=0,
                    env=self.env,
                )

                # Holders use their own installed module.
                def commands():
                    while True:
                        message = self.queues[ident].get()
                        if message["event"] == "end":
                            process.stdin.close()
                            return
                        command = message["value"]
                        if command.get("action") == "root" and value["role"] != "planner":
                            raise ValueError("private login recipient")
                        process.stdin.write(
                            json.dumps(command, separators=(",", ":")).encode() + b"\n"
                        )
                        process.stdin.flush()

                threading.Thread(target=commands, daemon=True).start()
                public_output = (self.root / ("holder-" + value["role"] + ".public.ndjson")).open(
                    "wb"
                )
                for raw in process.stdout:
                    public_output.write(raw)
                    public_output.flush()
                    if len(raw) > 65536:
                        raise ValueError("holder output bound")
                    self.reply(ident, json.loads(raw))
                code = process.wait(timeout=30)
                public_output.close()
                atomic(
                    self.root / ("holder-" + value["role"] + ".native-exit.json"),
                    {"native_exit": code, "launcher_pid": process.pid, "role": value["role"]},
                )
                return
            if action == "start-services" and not fields:
                self.services()
                result = True
            elif action == "resume-services" and not fields:
                self.services(resume=True)
                result = True
            elif action == "drain" and not fields:
                result = self.drain()
            elif action == "writer-status" and fields == {"role"}:
                result = self.writer_status(value["role"])
            elif action == "wait-receiver" and fields == {"role", "path", "seconds"}:
                role = value["role"]
                path = (
                    "/owned/run/ipc/"
                    + ("planner-selector" if role == "selector" else "selector-executor")
                    + "/child.sock"
                )
                if (
                    role not in ("selector", "executor")
                    or value["path"] != path
                    or value["seconds"] != 5
                ):
                    raise ValueError("fixed receiver socket")
                program = (
                    "import time;from pathlib import Path;p=Path("
                    + repr(path)
                    + (
                        ");deadline=time.monotonic()+5\nwhile not p.is_socket():\n as"
                        "sert time.monotonic()<deadline;time.sleep(.02)"
                    )
                )
                self.call(["docker", "exec", self.ids[role], "python", "-c", program])
                result = True
            elif action == "record-bootstrap" and fields == {"value"}:
                atomic(self.control / "bootstrap.json", value["value"])
                result = True
            elif action == "wait-anchor" and not fields:
                deadline = time.monotonic() + 30
                while True:
                    result = self.actor("operator", "anchor-status").decode().strip()
                    if result == "True":
                        break
                    if time.monotonic() > deadline:
                        raise ValueError("anchor deadline")
                    time.sleep(0.1)
                result = True
            elif action == "export-offline" and fields == {"out"}:
                result = self.export_offline(value["out"])
            else:
                raise ValueError("fixed private control action")
            self.reply(ident, {"ok": True, "value": result})
        except Exception as exc:
            atomic(
                self.root / ("control-failure-" + ident + ".json"),
                {"type": type(exc).__name__, "message": str(exc), "action": value.get("action")},
            )
            self.reply(ident, {"ok": False, "error": type(exc).__name__})
        finally:
            self.reply(ident, close=True)

    def export_offline(self, out):
        if not out.startswith("/tmp/") or ".." in Path(out).parts:
            raise ValueError("fixed normal output path")
        self.init(
            "freeze-copy",
            (
                "import shutil,os,json;from pathlib import Path;src=Path('/"
                "owned/run/operator/frozen-export');dst=Path('/owned/run/ga"
                "teway/frozen-export');shutil.copytree(src,dst);\nfor p in ["
                "dst,*dst.iterdir()]:os.chown(p,"
            )
            + str(UIDS["gateway"])
            + ","
            + str(UIDS["gateway"])
            + (
                ");p.chmod(0o555 if p.is_dir() else 0o444)\npublic=json.load"
                "s(Path('/owned/run/gateway/public-trust.json').read_bytes("
                "));p=Path('/owned/run/gateway/export-registration.json');p"
                ".write_text(json.dumps(public['export_credentials'][0]));o"
                "s.chown(p,"
            )
            + str(UIDS["gateway"])
            + ","
            + str(UIDS["gateway"])
            + (
                ");p.chmod(0o400)\nfor f in ('public-trust.json','external-p"
                "in.json','checkpoint-history.ndjson'):shutil.copyfile(src/"
                "f,Path('/results')/f);(Path('/results')/f).chmod(0o444)\nos"
                ".chown('/results',"
            )
            + str(UIDS["export"])
            + ","
            + str(UIDS["export"])
            + ");os.chmod('/results',0o755)",
        )
        self.call(["docker", "start", self.ids["gateway"]])
        self.start_child("gateway", ["actor", "--stage", "gateway-export", "--role", "gateway"])
        self.actor("gateway", "readonly")
        self.actor("export", "readonly")
        self.actor("export", "export")
        self.actor("offline", "offline")
        self.call(
            [
                "docker",
                "exec",
                self.ids["offline"],
                "python",
                "-m",
                "agent_guard.evidence.verify_cli",
                "--bundle",
                "/inputs/task-bundle.ndjson",
                "--trust",
                "/inputs/public-trust.json",
                "--external-pin",
                "/inputs/external-pin.json",
                "--report",
                "/tmp/offline-report.json",
            ],
            timeout=300,
        )
        output = self.root / "public-output"
        output.mkdir()
        self.call(["docker", "cp", self.ids["export"] + ":/results/.", str(output)])
        for path in output.iterdir():
            if path.is_file():
                self.call(
                    ["docker", "cp", str(path), self.ids["operator"] + ":" + out + "/" + path.name]
                )
        atomic(
            self.root / "public-output-manifest.json",
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in output.iterdir()
                if p.is_file()
            },
        )
        return True

    def cleanup(self):
        receipts = []
        if "operator" in self.ids:
            target = self.root / "normal-result"
            target.mkdir(exist_ok=True)
            self.call(
                ["docker", "cp", self.ids["operator"] + ":/tmp/normal-output/.", str(target)],
                allow=True,
            )
        # Discover only this newly created exact run/owner after a partial Compose failure.
        actual = (
            self.call(
                [
                    "docker",
                    "ps",
                    "-aq",
                    "--filter",
                    "label=agent-guard.run=" + self.run,
                    "--filter",
                    "label=agent-guard.owner=" + self.owner,
                ]
            )
            .stdout.decode()
            .split()
        )
        for container in actual:
            if container not in self.ids.values():
                self.capture("partial-" + container[:12], container)
        for role, container in reversed(list(self.ids.items())):
            try:
                self.inspect(role)
                result = self.call(["docker", "rm", "-f", container], allow=True)
                receipts.append({"container": container, "exit": result.returncode})
            except Exception as exc:
                receipts.append({"container": container, "error": type(exc).__name__})
        for network in reversed(self.networks):
            value = json.loads(self.call(["docker", "network", "inspect", network["id"]]).stdout)[0]
            if (
                value["Id"] != network["id"]
                or value["Labels"].get("agent-guard.owner") != self.owner
            ):
                raise ValueError("owned network mismatch")
            self.call(["docker", "network", "rm", network["id"]])
        for volume in reversed(self.volumes):
            value = json.loads(self.call(["docker", "volume", "inspect", volume]).stdout)[0]
            if (
                value["Labels"].get("agent-guard.owner") != self.owner
                or value["Labels"].get("agent-guard.run") != self.run
            ):
                raise ValueError("owned volume mismatch")
            self.call(["docker", "volume", "rm", volume])
        for kind, command in [
            ("containers", ["docker", "ps", "-aq"]),
            ("networks", ["docker", "network", "ls", "-q"]),
            ("volumes", ["docker", "volume", "ls", "-q"]),
        ]:
            result = self.call(
                [
                    *command,
                    "--filter",
                    "label=agent-guard.run=" + self.run,
                    "--filter",
                    "label=agent-guard.owner=" + self.owner,
                ]
            )
            if result.stdout.strip():
                raise ValueError("owned " + kind + " remain")
        atomic(
            self.root / "cleanup.json", {"resources_remaining": 0, "container_receipts": receipts}
        )
        for row in self.children.values():
            process = row["process"]
            if process.poll() is None:
                process.wait(timeout=30)
        for row in self.children.values():
            row["finalizer"].join(timeout=5)
        for stream in self.logs:
            stream.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--mode", choices=("source", "wheel"), default="wheel")
    parser.add_argument("--capacity-items", type=int, choices=(1, 256), default=1)
    parser.add_argument("--cap-seconds", type=int, default=14400)
    parser.add_argument("--serve-only", action="store_true")
    args = parser.parse_args()
    import signal

    if not 1 <= args.cap_seconds <= 14400:
        raise ValueError("finite manager cap")

    def timed_out(*_):
        raise TimeoutError("finite owned manager deadline")

    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(args.cap_seconds)
    owner = Owner(args)
    started = time.time()
    code = 1
    atomic(
        owner.root / "manager-start.json",
        {
            "pid": os.getpid(),
            "run_id": owner.run,
            "owner_id": owner.owner,
            "start_epoch": started,
            "cap_seconds": args.cap_seconds,
            "argv_sha256": hashlib.sha256(b"\0".join(os.fsencode(x) for x in sys.argv)).hexdigest(),
        },
    )
    try:
        owner.setup()
        if args.serve_only:
            while time.time() - started < args.cap_seconds:
                time.sleep(0.5)
        else:
            owner.call(
                owner.command(
                    "operator",
                    [
                        "normal",
                        "--out",
                        "/tmp/normal-output",
                        "--capacity-items",
                        str(args.capacity_items),
                    ],
                ),
                timeout=args.cap_seconds,
            )
        code = 0
    except Exception as exc:
        atomic(owner.root / "failure.json", {"type": type(exc).__name__, "message": str(exc)})
    finally:
        try:
            owner.cleanup()
        except Exception as exc:
            atomic(
                owner.root / "cleanup-failure.json",
                {"type": type(exc).__name__, "message": str(exc)},
            )
            code = 1
        atomic(
            owner.root / "manager-native-exit.json",
            {"native_exit": code, "pid": os.getpid(), "elapsed": time.time() - started},
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
