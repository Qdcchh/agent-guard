"""A33 deployment checks. S0 tests are PRECHECK_ONLY, never complete deployment PASS.

S1: select the three ``test_s0_*`` roots explicitly. S2: provide the final
allocated-resources.json and run.json through AG33_FINAL_RESOURCE_MANIFEST and
AG33_FINAL_RUN_CONFIG. No fallback to historical images, helpers, or credentials.
Every Docker operation on a deployment container verifies its full ID and owner.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ROLES = tuple(
    sorted(
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
)
UIDS = {role: 21000 + i for i, role in enumerate(ROLES)}
GIDS = {"planner-selector": 22000, "selector-executor": 22001}
DOMAINS = ("authority", "downstream", "audit")
pytestmark = pytest.mark.integration


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Native:
    """Retain native output and exit codes, including every failed attempt."""

    def __init__(self, evidence):
        self.evidence = Path(evidence).absolute()
        if any(p.is_symlink() for p in (self.evidence, *self.evidence.parents)):
            raise ValueError("native evidence symlink forbidden")
        missing = []
        current = self.evidence
        while not current.exists():
            missing.append(current)
            current = current.parent
        for directory in reversed(missing):
            directory.mkdir(mode=0o700)
        if self.evidence.stat().st_mode & 0o777 != 0o700:
            raise ValueError("native evidence must be mode 0700")
        self.sequence = 0

    def call(self, argv, *, input=None, timeout=60, check=True, cwd=REPO, env=None):
        self.sequence += 1
        stem = self.evidence / f"{self.sequence:04d}"
        started = time.time()
        try:
            result = subprocess.run(
                argv, input=input, capture_output=True, timeout=timeout, cwd=cwd, env=env
            )
        except subprocess.TimeoutExpired as exc:
            stem.with_suffix(".stdout").write_bytes(exc.stdout or b"")
            stem.with_suffix(".stderr").write_bytes(exc.stderr or b"")
            stem.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "argv": argv,
                        "native_exit": "TIMEOUT",
                        "timeout": timeout,
                        "started": started,
                    }
                )
            )
            for suffix in (".stdout", ".stderr", ".json"):
                stem.with_suffix(suffix).chmod(0o600)
            raise
        stem.with_suffix(".stdout").write_bytes(result.stdout)
        stem.with_suffix(".stderr").write_bytes(result.stderr)
        stem.with_suffix(".json").write_text(
            json.dumps(
                {
                    "argv": argv,
                    "native_exit": result.returncode,
                    "started": started,
                    "elapsed": time.time() - started,
                },
                indent=2,
            )
        )
        for suffix in (".stdout", ".stderr", ".json"):
            stem.with_suffix(suffix).chmod(0o600)
        if check:
            assert result.returncode == 0, f"native exit {result.returncode}: {stem}"
        return result


@pytest.fixture(scope="session", params=("source", "wheel"))
def a33_install(request, tmp_path_factory):
    """Fresh, exact-lock Python3.11 installations; generated context is test-only."""
    mode = request.param
    current_assembly = bool(os.environ.get("PR9_DEPLOY_INPUTS_ROOT"))
    if current_assembly:
        private_root = Path(os.environ["PR9_DEPLOY_INPUTS_ROOT"]).absolute()
        assert not any(path.is_symlink() for path in (private_root, *private_root.parents)), (
            "deployment symlink root forbidden"
        )
        private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        assert private_root.stat().st_mode & 0o077 == 0, "private deployment root must be 0700"
    run_id = str(uuid.uuid4())
    owner = "a33-deploy-" + run_id
    context = tmp_path_factory.mktemp("a33-install-" + mode)
    evidence = Path(os.environ.get("AG33_EVIDENCE_DIR", str(context / "evidence"))) / mode / run_id
    native = Native(evidence)
    package = context / "package"
    package.mkdir()
    for name in (
        "pyproject.toml",
        "README.md",
        "requirements.lock",
        "requirements-dev.lock",
        "requirements-ci.lock",
    ):
        shutil.copyfile(REPO / name, package / name)

    def isolated_source_ignore(directory, names):
        ignored = set(shutil.ignore_patterns("__pycache__", "*.egg-info")(directory, names))
        if (
            not current_assembly
            and not os.environ.get("AG33_FINAL_RESOURCE_MANIFEST")
            and Path(directory).name == "demo"
        ):
            ignored.update({"holder.py", "runner.py", "faults.py"})
        return ignored

    if not current_assembly and not os.environ.get("AG33_FINAL_RESOURCE_MANIFEST"):
        frozen = json.loads(
            (
                REPO / "tasks/workflow/runs/A3.3-delivery-20261011/shared-interface-s0-r2.json"
            ).read_bytes()
        )
        assert (
            digest(REPO / "tasks/workflow/runs/A3.3-delivery-20261011/shared-interface-s0-r2.json")
            == "79c90c6e6f313241481ad23aac8ee0867269abdd7c490ed95f28714a57c7af89"
        )
        assert all(
            digest(REPO / p) == value["SHA256"] for p, value in frozen["source_files"].items()
        )
    for name in ("src", "migrations"):
        shutil.copytree(REPO / name, package / name, ignore=isolated_source_ignore)
    shutil.copytree(REPO / "deploy/demo", package / "deploy/demo")
    # Both variants build wheels; source installation is separately noneditable.
    from tools.pr9_deploy_inputs import prepare_legacy_sidecars

    sidecar_binding = prepare_legacy_sidecars(context / "test-sidecars", mode)
    (evidence / "sidecar-install-binding.json").write_text(json.dumps(sidecar_binding, indent=2))
    (evidence / "sidecar-install-binding.json").chmod(0o600)
    (context / "Dockerfile").write_text(
        "FROM --platform=linux/amd64 python:3.11-slim\n"
        "RUN apt-get update && apt-get install -y --no-install-recommends openssl busybox "
        "&& rm -rf /var/lib/apt/lists/*\n"
        "COPY package /package\n"
        "RUN python -m venv /opt/runtime && /opt/runtime/bin/pip install "
        "--require-hashes --only-binary=:all: -r /package/requirements-ci.lock "
        "&& /opt/runtime/bin/pip wheel --no-deps --no-build-isolation "
        "--wheel-dir /wheels /package\n"
        + (
            "RUN /opt/runtime/bin/pip install --no-deps --no-build-isolation /package\n"
            if mode == "source"
            else "RUN /opt/runtime/bin/pip install --no-deps /wheels/agent_guard-*.whl\n"
        )
        + "RUN /opt/runtime/bin/pip check\n"
        + "COPY test-sidecars /opt/runtime/lib/python3.11/site-packages/\nWORKDIR /outside\n"
        'ENV PYTHONPATH=""\n'
    )
    tag = "agent-guard-a33-deploy-" + run_id + ":" + mode
    native.call(
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "--label",
            "agent-guard.owner=" + owner,
            "--label",
            "agent-guard.run=" + run_id,
            "-t",
            tag,
            str(context),
        ],
        timeout=1800,
    )
    image = json.loads(native.call(["docker", "image", "inspect", tag]).stdout)[0]
    assert image["Config"]["Labels"]["agent-guard.owner"] == owner
    image_id = image["Id"]
    containers = []
    created_containers = []

    def persist_installation():
        state = {
            "version": 1,
            "mode": mode,
            "run_id": run_id,
            "owner_id": owner,
            "image_full_id": image_id,
            "image_tag": tag,
            "created_container_full_ids": list(created_containers),
        }
        path = evidence / "installation-state.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(path)

    persist_installation()

    def record_container(identity):
        assert re.fullmatch(r"[0-9a-f]{64}", identity)
        assert identity not in created_containers
        created_containers.append(identity)
        persist_installation()

    def execute(program, *, expected=0, timeout=180):
        name = "ag-a33-deploy-" + str(uuid.uuid4())
        created = (
            native.call(
                [
                    "docker",
                    "create",
                    "--platform",
                    "linux/amd64",
                    "--name",
                    name,
                    "--label",
                    "agent-guard.owner=" + owner,
                    "--label",
                    "agent-guard.run=" + run_id,
                    "--network",
                    "none",
                    "--add-host",
                    "identity.agent-guard.test:127.0.0.1",
                    image_id,
                    "/opt/runtime/bin/python",
                    "-c",
                    program,
                ]
            )
            .stdout.decode()
            .strip()
        )
        assert re.fullmatch(r"[0-9a-f]{64}", created)
        containers.append(created)
        record_container(created)
        value = json.loads(native.call(["docker", "inspect", created]).stdout)[0]
        assert value["Id"] == created and value["Config"]["Labels"]["agent-guard.owner"] == owner
        result = native.call(["docker", "start", "-a", created], timeout=timeout, check=False)
        value = json.loads(native.call(["docker", "inspect", created]).stdout)[0]
        assert value["Id"] == created and value["Config"]["Labels"]["agent-guard.owner"] == owner
        assert value["State"]["ExitCode"] == expected, result.stderr.decode()[-1500:]
        return result.stdout

    try:
        if current_assembly or os.environ.get("AG33_FINAL_RESOURCE_MANIFEST"):
            source_hashes = {
                str(p.relative_to(REPO / "src/agent_guard")): digest(p)
                for p in (REPO / "src/agent_guard").rglob("*.py")
            }
            program = """import hashlib, importlib.metadata, json, sys
from pathlib import Path
import agent_guard
root = Path(agent_guard.__file__).parent
assert "site-packages" in root.parts
expected = EXPECTED
actual = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in root.rglob("*.py")}
assert actual == expected, (set(actual) ^ set(expected))
lock = Path(sys.prefix) / "share/agent-guard/requirements-ci.lock"
assert hashlib.sha256(lock.read_bytes()).hexdigest() == CI_LOCK_SHA
versions = {}
for line in lock.read_text().splitlines():
    if "==" in line and not line.startswith("#"):
        name, version = line.split("==", 1)
        version = version.strip().split()[0]
        versions[name] = importlib.metadata.version(name)
        assert versions[name] == version
print(json.dumps({"installed_source_files": actual, "root": str(root),
                  "dependency_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
                  "dependency_versions": versions}))

""".replace("EXPECTED", repr(source_hashes)).replace(
                "CI_LOCK_SHA", repr(digest(REPO / "requirements-ci.lock"))
            )
            installed = json.loads(execute(program))
            (evidence / "current-install-binding.json").write_text(json.dumps(installed, indent=2))

        yield {
            "mode": mode,
            "run_id": run_id,
            "owner": owner,
            "native": native,
            "execute": execute,
            "image": image_id,
            "containers": containers,
            "record_container": record_container,
            "evidence": evidence,
        }
    finally:
        for container_id in containers:
            value = json.loads(native.call(["docker", "inspect", container_id]).stdout)[0]
            assert value["Id"] == container_id
            assert value["Config"]["Labels"]["agent-guard.owner"] == owner
            native.call(["docker", "rm", "-f", container_id])
        value = json.loads(native.call(["docker", "image", "inspect", image_id]).stdout)[0]
        assert value["Id"] == image_id and value["Config"]["Labels"]["agent-guard.owner"] == owner
        native.call(["docker", "image", "rm", image_id])
        leftovers = native.call(
            ["docker", "ps", "-aq", "--filter", "label=agent-guard.owner=" + owner]
        )
        assert leftovers.stdout.strip() == b""
        (evidence / "STOP.json").write_text(
            json.dumps(
                {
                    "status": "PRECHECK_ONLY_RESOURCE_REAPED",
                    "run_id": run_id,
                    "owner_id": owner,
                    "containers": containers,
                    "leftovers": 0,
                    "no_more_writes": True,
                }
            )
        )


_INIT_PROGRAM = r'''import hashlib, json, os, stat, subprocess, sys, uuid
from pathlib import Path
from agent_guard.demo.init import init_run
from agent_guard.demo.config import ROLES, DemoConfigError, load_run_config, check_config

uids = {r: 21000 + i for i, r in enumerate(sorted(ROLES))}
run = str(uuid.uuid4())
root = Path("/private/run")
root.parent.mkdir(mode=0o755)
manifest = init_run(
    root,
    run_id=run,
    owner_id="test-" + run,
    role_uids=uids,
    handoff_gids={"planner-selector": 22000, "selector-executor": 22001},
)
config = load_run_config(manifest.run_config.read_bytes(), base_dir=root)
assert check_config(config).run_id == run
assert stat.S_IMODE(root.stat().st_mode) == 0o700
before = {
    str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()
}
try:
    init_run(
        root,
        run_id=run,
        owner_id="test-" + run,
        role_uids=uids,
        handoff_gids={"planner-selector": 22000, "selector-executor": 22001},
    )
except (ValueError, FileExistsError):
    pass
else:
    raise AssertionError("repeat init overwrote tree")
assert before == {
    str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()
}
alias = Path("/private/alias")
alias.symlink_to(root, target_is_directory=True)
try:
    init_run(
        alias,
        run_id=run,
        owner_id="test-" + run,
        role_uids=uids,
        handoff_gids={"planner-selector": 22000, "selector-executor": 22001},
    )
except (ValueError, OSError):
    pass
else:
    raise AssertionError("alias accepted")
keys = []
for role, rc in config.roles.items():
    info = (root / role).stat()
    assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (rc.uid, rc.uid, 0o700)
    for path in (root / role).iterdir():
        info = path.stat()
        assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (rc.uid, rc.uid, 0o600)
    if "signing_key" in rc.private_files:
        keys.append(hashlib.sha256(rc.private_files["signing_key"].read_bytes()).hexdigest())
assert len(keys) == 6 and len(set(keys)) == 6
public = json.loads(config.public_manifest.read_bytes())
assert (
    set(public["as_keys"]) == {"as-sign-1"}
    and set(public["receipt_keys"]) == {"gw-receipt-1"}
    and set(public["audit_keys"]) == {"audit-sign-1"}
)
assert len(public["registrations"]) == 3
# Only the public parent gains traversal; private role ownership remains exact.
root.chmod(0o755)
program = r"""import os, json, sys
from pathlib import Path

role = sys.argv[1]
uid = int(sys.argv[2])
own = Path("/private/run") / role
os.setgroups([])
os.setgid(uid)
os.setuid(uid)
assert os.getuid() == uid and os.getgid() == uid
assert (own / "role.json").read_bytes()
for other in sys.argv[3:]:
    try:
        (Path("/private/run") / other / "role.json").read_bytes()
    except PermissionError as exc:
        assert exc.errno == 13
    else:
        raise AssertionError("foreign role readable")
print(
    json.dumps(
        {
            "role": role,
            "uid": os.getuid(),
            "gid": os.getgid(),
            "pid": os.getpid(),
            "denied": len(sys.argv[3:]),
        }
    )
)
"""
rows = []
for role in sorted(ROLES):
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            program,
            role,
            str(uids[role]),
            *[r for r in sorted(ROLES) if r != role],
        ],
        capture_output=True,
        timeout=15,
    )
    assert child.returncode == 0, child.stderr.decode()
    rows.append(json.loads(child.stdout))
assert len({r["pid"] for r in rows}) == 12
print(
    json.dumps(
        {
            "status": "PRECHECK_ONLY",
            "run_id": run,
            "roles": rows,
            "key_count": len(keys),
            "public_manifest_sha256": hashlib.sha256(
                config.public_manifest.read_bytes()
            ).hexdigest(),
        }
    )
)
'''


_DID_PROGRAM = r'''import copy
import dataclasses
import hashlib
import json
import os
import ssl
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from agent_guard.demo.config import ROLES, load_run_config
from agent_guard.demo.init import init_run
from agent_guard.contracts.encoding import canonical_json_bytes, b64url_encode, b64url_decode
from agent_guard.crypto.sm import (
    sign_sm2_message,
    generate_sm2_private_key,
    serialize_sm2_public_key,
)
from agent_guard.demo.did_bootstrap import load_registry, possession_message
from tongsuopy.crypto import serialization

root = Path("/private/run")
root.parent.mkdir(mode=0o755)
uids = {r: 21000 + i for i, r in enumerate(sorted(ROLES))}
run = str(uuid.uuid4())
manifest = init_run(
    root,
    run_id=run,
    owner_id="test-" + run,
    role_uids=uids,
    handoff_gids={"planner-selector": 22000, "selector-executor": 22001},
)
root.chmod(0o755)
config = load_run_config(manifest.run_config.read_bytes(), base_dir=root)
docs = json.loads((root / "did/config.json").read_bytes())["documents"]
original = copy.deepcopy(docs)
# Operator gets only public run metadata and its own private leaf.
registry_raw = json.loads((root / "operator/approval-registry.json").read_bytes())
from agent_guard.demo.config import ApprovedRegistry
from agent_guard.identity.resolver import RegisteredIdentity
from types import MappingProxyType

registrations = tuple(
    RegisteredIdentity(
        r["tenant_id"], r["client_id"], r["did"], r["kid"], b64url_decode(r["spki_der"])
    )
    for r in registry_raw["registrations"]
)
registry = ApprovedRegistry(
    run,
    registrations,
    MappingProxyType(
        {r["client_id"]: tuple(r["purposes"]) for r in registry_raw["registrations"]}
    ),
    root / "operator/ca.pem",
    b64url_decode(registry_raw["challenge"]),
)
proofs = {}
for r in registrations:
    key = serialization.load_pem_private_key(
        (root / r.client_id.removeprefix("agent-") / "signing-key.pem").read_bytes(), None
    )
    proofs[r.client_id] = b64url_encode(
        sign_sm2_message(key, possession_message(config, registry, r))
    )
(root / "operator/proofs.json").write_text(json.dumps(proofs))
os.chown(root / "operator/proofs.json", uids["operator"], uids["operator"])
(root / "operator/proofs.json").chmod(0o600)
state = {"case": "normal"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        value = docs.get("https://identity.agent-guard.test" + self.path)
        raw = canonical_json_bytes(value) if value is not None else b"{}"
        case = state["case"]
        if case == "oversize":
            raw = b" " * 65537
        self.send_response(302 if case == "redirect" else (200 if value is not None else 404))
        if case == "redirect":
            self.send_header("Location", "https://other.agent-guard.test/did.json")
        self.send_header(
            "Content-Type", "text/plain" if case == "media" else "application/did+json"
        )
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


server = HTTPServer(("0.0.0.0", 443), Handler)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(root / "did/tls.pem", root / "did/tls-key.pem")
server.socket = context.wrap_socket(server.socket, server_side=True)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
program = r"""import dataclasses, json, os, sys, ssl
from pathlib import Path
from agent_guard.demo.config import load_run_config, DemoConfigError
from agent_guard.demo.did_bootstrap import (
    load_registry,
    approve_dids,
    save_approved_snapshot,
    load_approved_snapshot,
)
from agent_guard.contracts.encoding import b64url_decode

root = Path("/private/run")
config = load_run_config((root / "run.json").read_bytes(), base_dir=root)
os.setgroups([])
os.setgid(config.roles["operator"].uid)
os.setuid(config.roles["operator"].uid)
registry = load_registry(config)
case = sys.argv[1]
proofs = {
    k: b64url_decode(v)
    for k, v in json.loads((root / "operator/proofs.json").read_text()).items()
}
if case == "wrongCA":
    registry = dataclasses.replace(registry, ca_file=Path("/etc/ssl/certs/ca-certificates.crt"))
if case == "unknownURL":
    registry = dataclasses.replace(
        registry,
        registrations=(
            dataclasses.replace(
                registry.registrations[0], did="did:web:identity.agent-guard.test:unknown"
            ),
            *registry.registrations[1:],
        ),
    )
if case == "wrong-purpose":
    registry = dataclasses.replace(
        registry, purposes=dict(registry.purposes, **{"agent-planner": ("authentication",)})
    )
if case == "wrong-kid":
    registry = dataclasses.replace(
        registry,
        registrations=(
            dataclasses.replace(
                registry.registrations[0], kid=registry.registrations[0].did + "#foreign"
            ),
            *registry.registrations[1:],
        ),
    )
try:
    approved = approve_dids(config, registry=registry, proof_of_possession=proofs)
    if case != "normal":
        raise AssertionError("bad approval accepted")
    path = save_approved_snapshot(config, approved=approved)
    config = dataclasses.replace(config, approved_did_manifest=path)
    assert load_approved_snapshot(config).documents == approved.documents
    factory = approved.factory_documents()
    first = next(iter(factory))
    factory[first]["id"] = "changed"
    assert approved.factory_documents()[first]["id"] != "changed"
    saved = path.read_bytes()
    missing = dataclasses.replace(
        config, approved_did_manifest=path.parent / "missing-manifest.json"
    )
    try:
        load_approved_snapshot(missing)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing approved manifest accepted")
    changed = json.loads(saved)
    changed["documents"][first]["sm3"] = "A" * 43
    path.chmod(0o600)
    path.write_text(json.dumps(changed))
    try:
        load_approved_snapshot(config)
    except ValueError:
        pass
    else:
        raise AssertionError("modified approved hash accepted")
    path.write_bytes(saved)
    path.chmod(0o444)
    assert load_approved_snapshot(config).documents == approved.documents

    print(
        json.dumps(
            {
                "status": "PRECHECK_ONLY",
                "urls": list(approved.documents),
                "digests": dict(approved.digests),
                "certificate_fingerprints": dict(approved.certificate_fingerprints),
                "fetched_at": dict(approved.fetched_at),
                "uid": os.getuid(),
                "pid": os.getpid(),
            }
        )
    )
except (ValueError, OSError, ssl.SSLError) as exc:
    if case == "normal":
        raise
    print(
        json.dumps(
            {
                "rejected": case,
                "exception": type(exc).__name__,
                "uid": os.getuid(),
                "pid": os.getpid(),
            }
        )
    )
"""


def check(case):
    state["case"] = case
    p = subprocess.run([sys.executable, "-c", program, case], capture_output=True, timeout=30)
    assert p.returncode == 0, (case, p.stderr.decode())
    row = json.loads(p.stdout)
    print(json.dumps(row), flush=True)
    assert ("status" in row) == (case == "normal")


check("normal")
for case in (
    "wrongCA",
    "redirect",
    "media",
    "oversize",
    "unknownURL",
    "wrong-purpose",
    "wrong-kid",
):
    check(case)
url = "https://identity.agent-guard.test/agents/planner/did.json"
for case in (
    "id",
    "controller",
    "authentication",
    "capabilityInvocation",
    "capabilityDelegation",
    "SPKI",
):
    docs.clear()
    docs.update(copy.deepcopy(original))
    doc = docs[url]
    if case == "id":
        doc["id"] = "did:web:other.agent-guard.test"
    elif case == "controller":
        doc["verificationMethod"][0]["controller"] = "did:web:other.agent-guard.test"
    elif case == "SPKI":
        from agent_guard.identity.resolver import SPKI_PROPERTY

        doc["verificationMethod"][0][SPKI_PROPERTY] = b64url_encode(
            serialize_sm2_public_key(generate_sm2_private_key().public_key())
        )
    else:
        doc[case] = []
    check(case)
server.shutdown()
server.server_close()
thread.join(timeout=5)
assert not thread.is_alive()
# Exact SAN rejection uses an actual second server with an AS certificate.
server = HTTPServer(("0.0.0.0", 443), Handler)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(root / "as/tls.pem", root / "as/tls-key.pem")
server.socket = ctx.wrap_socket(server.socket, server_side=True)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
docs.clear()
docs.update(original)
check("wrongSAN")
server.shutdown()
server.server_close()
thread.join(timeout=5)
assert not thread.is_alive()
'''


def test_s0_role_init_private_permissions_precheck(a33_install):
    value = json.loads(a33_install["execute"](_INIT_PROGRAM))
    assert value["status"] == "PRECHECK_ONLY"
    assert len(value["roles"]) == 12
    ipc = [json.loads(line) for line in a33_install["execute"](_IPC_PROGRAM).splitlines()]
    assert len(ipc) == 40
    assert sum("sender" in row for row in ipc) == 20
    assert {r["round"] for r in ipc} == set(range(10))

    assert all(row["uid"] == UIDS[row["role"]] and row["denied"] == 11 for row in value["roles"])


def test_s0_did_bootstrap_approval_precheck(a33_install):
    rows = [json.loads(line) for line in a33_install["execute"](_DID_PROGRAM).splitlines()]
    assert len(rows[0]["urls"]) == 3
    assert set(rows[0]["digests"]) == set(rows[0]["certificate_fingerprints"])
    assert {r["rejected"] for r in rows[1:]} == {
        "wrongCA",
        "wrongSAN",
        "redirect",
        "media",
        "oversize",
        "unknownURL",
        "wrong-purpose",
        "wrong-kid",
        "id",
        "controller",
        "authentication",
        "capabilityInvocation",
        "capabilityDelegation",
        "SPKI",
    }


class FinalDeployment:
    def __init__(self, native, manifest, config):
        self.native, self.manifest, self.config = native, manifest, Path(config)
        self.run_id, self.owner = manifest["run_id"], manifest["owner_id"]
        assert str(uuid.UUID(self.run_id)) == self.run_id
        assert set(manifest) == {
            "version",
            "run_id",
            "owner_id",
            "project",
            "roles",
            "databases",
            "networks",
        }
        assert set(manifest["roles"]) == set(ROLES)
        assert set(manifest["databases"]) == set(DOMAINS)
        self.ids = {r: manifest["roles"][r]["container_id"] for r in ROLES}
        assert len(set(self.ids.values())) == 12
        self.inspections = {r: self.inspect(r) for r in ROLES}

    def inspect(self, role):
        container_id = self.ids[role]
        assert re.fullmatch(r"[0-9a-f]{64}", container_id), "full container ID required"
        result = json.loads(self.native.call(["docker", "inspect", container_id]).stdout)[0]
        labels = result["Config"]["Labels"]
        assert result["Id"] == container_id
        assert labels["agent-guard.run"] == self.run_id
        assert labels["agent-guard.owner"] == self.owner
        assert labels["com.docker.compose.service"] == role
        assert labels["com.docker.compose.project"] == self.manifest["project"]
        return result

    def execute(self, role, program, *, timeout=180, check=True):
        self.inspect(role)
        # Production interpreter is discovered from the final role image, not an ignored venv.
        value = self.native.call(
            ["docker", "exec", "-i", self.ids[role], "python", "-c", program],
            timeout=timeout,
            check=check,
        )
        return value


def _load_final_deployment(manifest_path, config_path, evidence):
    assert manifest_path.is_file() and config_path.is_file()
    assert (REPO / "deploy/demo/compose.yaml").is_file()
    assert (REPO / "deploy/demo/Dockerfile").is_file()
    native = Native(evidence / "final")
    manifest = json.loads(manifest_path.read_bytes())
    config = json.loads(config_path.read_bytes())
    assert (config["run_id"], config["owner_id"]) == (manifest["run_id"], manifest["owner_id"])
    result = FinalDeployment(native, manifest, config_path)
    (native.evidence / "bindings.json").write_text(
        json.dumps(
            {
                "resource_manifest_sha256": digest(manifest_path),
                "run_config_sha256": digest(config_path),
                "files": {
                    p: digest(REPO / p)
                    for p in (
                        "deploy/demo/compose.yaml",
                        "deploy/demo/Dockerfile",
                        "pyproject.toml",
                        "README.md",
                        "src/agent_guard/demo/__main__.py",
                        "tests/integration/test_a33_roles.py",
                        "tests/integration/test_a33_clean_deploy.py",
                    )
                },
                "run_id": result.run_id,
                "owner_id": result.owner,
            },
            indent=2,
        )
    )
    return result


@pytest.fixture
def a33_final(tmp_path_factory, request):
    if os.environ.get("PR9_DEPLOY_INPUTS_ROOT"):
        from tools.pr9_deploy_inputs import deployment

        install = request.getfixturevalue("a33_install")
        with deployment(os.environ["PR9_DEPLOY_INPUTS_ROOT"], install["mode"]) as owner:
            result = _load_final_deployment(
                owner.root / "allocated-resources.json",
                owner.root / "run.json",
                owner.root / "assertions",
            )
            result.controller_inputs = owner.root / "test-inputs/connections.json"
            result.owner_controller = owner
            yield result
        return
    required = ("AG33_FINAL_RESOURCE_MANIFEST", "AG33_FINAL_RUN_CONFIG")
    assert all(os.environ.get(k) for k in required), "S2 final assembly is required; no S1 PASS"
    manifest_path, config_path = (Path(os.environ[k]).resolve() for k in required)
    evidence = Path(os.environ.get("AG33_EVIDENCE_DIR", str(tmp_path_factory.mktemp("a33-final"))))
    yield _load_final_deployment(manifest_path, config_path, evidence)


def test_role_init_trust_and_private_mounts(a33_final, a33_install):
    # Repeat direct init checks in each final installation variant; they are not sufficient alone.
    test_s0_role_init_private_permissions_precheck(a33_install)
    for role in ROLES:
        inspected = a33_final.inspect(role)
        assert inspected["Config"]["User"] == f"{UIDS[role]}:{UIDS[role]}"
        assert inspected["HostConfig"]["Privileged"] is False
        assert "ALL" in inspected["HostConfig"]["CapDrop"]
        assert any(
            opt.split(":", 1)[0] == "no-new-privileges"
            for opt in inspected["HostConfig"]["SecurityOpt"]
        )
        row = json.loads(
            a33_final.execute(
                role,
                "import os,json; print(json.dumps({'uid':os.getuid(),"
                "'gid':os.getgid(),'pid':os.getpid(),'groups':os.getgroups()}))",
            ).stdout
        )
        assert (row["uid"], row["gid"]) == (UIDS[role], UIDS[role])
        program = r"""import hashlib, json, os
from pathlib import Path
from agent_guard.demo.config import load_run_config
from agent_guard.server.private_files import read_private_file

p = Path("/owned/run")
c = load_run_config((p / "run.json").read_bytes(), base_dir=p)
role = ROLE
assert os.getuid() == c.roles[role].uid
rows = []
for key, path in c.roles[role].private_files.items():
    value = read_private_file(path)
    assert value
    rows.append(
        {"file_key": key, "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    )
print(json.dumps({"role": role, "private_files": rows}))
""".replace("ROLE", repr(role))
        observed = json.loads(a33_final.execute(role, program).stdout)
        assert observed["role"] == role
        assert len(observed["private_files"]) == len(
            json.loads(a33_final.config.read_bytes())["roles"][role]["private_files"]
        )

        own = [m for m in inspected["Mounts"] if m["Destination"].endswith("/" + role)]
        assert len(own) == 1
        assert own[0]["RW"] is (role == "operator")
        foreign = [
            m
            for m in inspected["Mounts"]
            if any(m["Destination"].endswith("/" + r) for r in ROLES if r != role)
        ]
        assert foreign == []
        for mount in inspected["Mounts"]:
            assert mount["Destination"] not in ("/var/run/docker.sock", "/", "/private")
    for role in ("operator", "worker"):
        mounts = [m for m in a33_final.inspect(role)["Mounts"] if m["Destination"] == "/registry"]
        assert len(mounts) == 1 and mounts[0]["RW"] is (role == "operator")
        program = r"""import json, os, stat
from pathlib import Path

p = Path("/registry")
info = p.stat()
assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (21007, 21011, 0o750)
if os.getuid() == 21007:
    assert 21011 in os.getgroups()
else:
    assert os.getuid() == 21011
    try:
        (p / "forbidden-worker-write").write_bytes(b"x")
    except OSError as exc:
        assert exc.errno in (13, 30)
    else:
        raise AssertionError("worker wrote metadata registry")
print(
    json.dumps(
        {"uid": os.getuid(), "groups": os.getgroups(), "mode": stat.S_IMODE(info.st_mode)}
    )
)
"""
        assert json.loads(a33_final.execute(role, program).stdout)["uid"] == UIDS[role]
    offline = a33_final.inspect("offline")
    assert offline["HostConfig"]["NetworkMode"] == "none"
    # Independently TLS-connect all three PGs in the actual operator role.
    program = r"""import json, os, psycopg
from pathlib import Path
from agent_guard.demo.config import load_run_config
from agent_guard.demo.provision import _dsn

root = Path("/owned/run")
c = load_run_config((root / "run.json").read_bytes(), base_dir=root)
rows = {}
for domain in ("authority", "downstream", "audit"):
    dsn = _dsn(c.roles["operator"], domain + "_dsn")
    from psycopg.conninfo import conninfo_to_dict

    params = conninfo_to_dict(dsn)
    assert params["sslmode"] == "verify-full"
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        locale = conn.execute(
            "SELECT datcollate,datctype,pg_encoding_to_char(encoding) FROM pg_database "
            "WHERE datname=current_database()"
        ).fetchone()
        assert locale == ("C", "C", "UTF8")
        assert conn.execute(
            "SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()"
        ).fetchone() == (True,)
        rows[domain] = {
            "host": params["host"],
            "locale": locale,
            "backend_pid": conn.info.backend_pid,
        }
with psycopg.connect(_dsn(c.roles["operator"], "authority_dsn"), connect_timeout=5) as conn:
    assert conn.execute(
        "SELECT has_table_privilege('demo_publisher','ag_verified_evidence','UPDATE')"
    ).fetchone() == (False,)
    privileges = conn.execute(
        "SELECT "
        "column_name,has_column_privilege('demo_publisher','ag_verified_evidence',co"
        "lumn_name,'UPDATE') FROM information_schema.columns WHERE "
        "table_schema='public' AND table_name='ag_verified_evidence' ORDER BY "
        "ordinal_position"
    ).fetchall()
    assert len(privileges) == 22
    assert [name for name, allowed in privileges if allowed] == ["evidence_ref"]
    for account in ("demo_export", "demo_gateway_export"):
        assert conn.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles "
            "WHERE rolname=%s",
            (account,),
        ).fetchone() == (False, False, False, False)
        denied = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND "
            "has_table_privilege(%s,quote_ident(schemaname)||'.'||quote_ident(tablename),"
            "'INSERT,UPDATE,DELETE,TRUNCAT"
            "E')",
            (account,),
        ).fetchall()
        assert denied == []
assert len({x["host"] for x in rows.values()}) == 3
print(json.dumps(rows))
"""
    assert set(json.loads(a33_final.execute("operator", program).stdout)) == set(DOMAINS)
    a33_final.native.call(
        [
            "docker",
            "exec",
            a33_final.ids["operator"],
            "python",
            "-m",
            "agent_guard.demo",
            "normal",
            "--config",
            "/owned/run/run.json",
            "--out",
            "/tmp/a33-trust-flow",
        ],
        timeout=14400,
    )
    for role in ("worker", "publisher"):
        a33_final.inspect(role)
        a33_final.native.call(["docker", "stop", "--time", "10", a33_final.ids[role]])
    rows = _audit_rows_after_expiry(a33_final)
    assert set(rows[0]["positive"]) == {"append", "latest", "history", "records"}
    assert {r["denied"] for r in rows[1:]} >= {
        "wrongCA",
        "wrongSAN",
        "wrongcredential",
        "wrongrole",
        "crossscope",
        "unregistered",
        "badframing",
        "plainHTTP",
    }


_FROZEN_PROJECTION_PROGRAM = r"""import hashlib, json, time
from pathlib import Path
import psycopg
from psycopg import sql
from agent_guard.demo.config import load_run_config
from agent_guard.demo.provision import _dsn

root = Path("/owned/run")
c = load_run_config((root / "run.json").read_bytes(), base_dir=root)
expiry = json.loads(Path("/tmp/a33-trust-flow/public-expiry.json").read_bytes())
assert expiry["expired"] is True
assert expiry["observed_at"] > expiry["latest_expiry"]
assert int(time.time()) > expiry["latest_expiry"]
result = {}
for domain in ("authority", "audit"):
    with psycopg.connect(_dsn(c.roles["operator"], domain + "_dsn")) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        names = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        ).fetchall()
        projection = {
            name: conn.execute(
                sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY 1").format(
                    sql.Identifier("public", name)
                )
            ).fetchall()
            for (name,) in names
        }
        assert projection
        result[domain] = hashlib.sha256(json.dumps(projection, sort_keys=True).encode()).hexdigest()
print(json.dumps(result))
"""


def _audit_rows_after_expiry(final):
    """Run unchanged TLS probes on the original AS only; preserve frozen state."""
    if not hasattr(final, "owner_controller"):
        return [
            json.loads(line)
            for line in final.execute("operator", _AUDIT_PROGRAM).stdout.splitlines()
        ]
    owner = final.owner_controller
    assert not final.inspect("as")["State"]["Running"]
    for role in ("worker", "publisher"):
        assert not final.inspect(role)["State"]["Running"]
    before = json.loads(final.execute("operator", _FROZEN_PROJECTION_PROGRAM).stdout)
    primary = None
    try:
        owner.call(["docker", "start", final.ids["as"]])
        owner.start_child("as", ["actor", "--stage", "as", "--role", "as"])
        owner.ready(include_audit=True)
        return [
            json.loads(line)
            for line in final.execute("operator", _AUDIT_PROGRAM).stdout.splitlines()
        ]
    except BaseException as exc:
        primary = exc
        raise
    finally:
        failures = []
        try:
            final.inspect("as")
            owner.call(["docker", "stop", "--time", "10", final.ids["as"]])
            assert not final.inspect("as")["State"]["Running"]
        except Exception as exc:
            failures.append(("stop", exc))
        try:
            after = json.loads(final.execute("operator", _FROZEN_PROJECTION_PROGRAM).stdout)
            assert after == before, "temporary TLS listener changed frozen database rows"
        except Exception as exc:
            failures.append(("projection", exc))
        if failures:
            record = {stage: type(exc).__name__ for stage, exc in failures}
            try:
                (final.native.evidence / "temporary-as-probe-failure.json").write_text(
                    json.dumps(record)
                )
            except OSError:
                pass
            if primary is not None:
                primary.add_note("Temporary AS cleanup/projection also failed: " + repr(record))
            else:
                raise AssertionError(
                    "Temporary AS cleanup/projection failed: " + repr(record)
                ) from failures[0][1]


def test_operator_https_did_approval_and_immutable_distribution(a33_final, a33_install):
    for _round in range(10):
        test_s0_did_bootstrap_approval_precheck(a33_install)
    for role in ("as", "gateway"):
        value = a33_final.execute(
            role,
            r"""import json, hashlib
from pathlib import Path
from agent_guard.demo.config import load_run_config
from agent_guard.demo.did_bootstrap import load_approved_snapshot

p = Path("/owned/run")
c = load_run_config((p / "run.json").read_bytes(), base_dir=p)
a = load_approved_snapshot(c)
before = dict(a.documents)
docs = a.factory_documents()
for doc in docs.values():
    doc["id"] = "unapproved-mutated"
assert dict(a.documents) == before
assert all(d["id"] != "unapproved-mutated" for d in a.factory_documents().values())
assert c.approved_did_manifest.stat().st_mode & 0o222 == 0
print(
    json.dumps(
        {
            "digests": dict(a.digests),
            "manifest_sha256": hashlib.sha256(c.approved_did_manifest.read_bytes()).hexdigest(),
        }
    )
)
""",
        )
        assert len(json.loads(value.stdout)["digests"]) == 3
    for holder in ("planner", "selector", "executor"):
        result = a33_final.execute(
            holder,
            r"""from pathlib import Path

for p in (
    Path("/owned/run/public-manifest.json"),
    Path("/owned/run/approved-did-manifest.json"),
):
    try:
        with p.open("r+b") as f:
            f.write(b"X")
    except (PermissionError, OSError) as exc:
        assert exc.errno in (13, 30)
    else:
        raise AssertionError("holder rewrote trust")
print("TRUST_WRITE_DENIED")
""",
        )
        assert result.stdout.strip() == b"TRUST_WRITE_DENIED"


def test_three_holder_processes_os_and_network_denials(a33_final, a33_install):
    ipc = [json.loads(line) for line in a33_install["execute"](_IPC_PROGRAM).splitlines()]
    assert len(ipc) == 40
    assert sum("sender" in row for row in ipc) == 20
    a33_final.native.call(
        [
            "docker",
            "exec",
            a33_final.ids["operator"],
            "python",
            "-m",
            "agent_guard.demo",
            "normal",
            "--config",
            "/owned/run/run.json",
            "--out",
            "/tmp/a33-role-flow",
        ],
        timeout=14400,
    )
    host_pids = set()
    for role in ("planner", "selector", "executor"):
        inspected = a33_final.inspect(role)
        assert inspected["State"]["Running"]
        host_pids.add(inspected["State"]["Pid"])
        groups = {GIDS[p] for p in GIDS if role in p.split("-")}
        program = r"""import json, os, socket, stat
from pathlib import Path
from agent_guard.demo.config import load_run_config

root = Path("/owned/run")
c = load_run_config((root / "run.json").read_bytes(), base_dir=root)
role = ROLE
rc = c.roles[role]
assert os.getuid() == rc.uid
for other, foreign in c.roles.items():
    if other == role:
        continue
    for key, path in foreign.private_files.items():
        try:
            path.read_bytes()
        except (FileNotFoundError, PermissionError):
            pass
        else:
            raise AssertionError("foreign private readable: " + other + "/" + key)
for round in range(10):
    for domain in ("authority", "downstream", "audit"):
        try:
            sock = socket.create_connection(("pg-" + domain + ".agent-guard.test", 5432), 1)
            sock.close()
        except OSError as exc:
            print(json.dumps({"round": round, "denied_domain": domain, "errno": exc.errno}))
        else:
            raise AssertionError("holder reached private database")
for pair in rc.handoff:
    info = pair.socket_path.parent.stat()
    assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (
        pair.receiver_uid,
        pair.pair_gid,
        0o710,
    )
    assert pair.pair_gid in os.getgroups()
print(json.dumps({"uid": os.getuid(), "pid": os.getpid(), "groups": os.getgroups()}))
""".replace("ROLE", repr(role))
        rows = [json.loads(line) for line in a33_final.execute(role, program).stdout.splitlines()]
        assert len(rows[:-1]) == 30
        assert {row["round"] for row in rows[:-1]} == set(range(10))
        assert {row["denied_domain"] for row in rows[:-1]} == set(DOMAINS)
        assert groups <= set(rows[-1]["groups"])
        assert rows[-1]["uid"] == UIDS[role]
    assert len(host_pids) == 3 and 0 not in host_pids
    program = r"""import json, psycopg
from pathlib import Path
from agent_guard.demo.config import load_run_config
from agent_guard.demo.provision import _dsn
from agent_guard.authorization.claims import validate_access_claims, validate_child
from agent_guard.crypto.sm import verify_compact_jws, load_sm2_public_key
from agent_guard.contracts.encoding import b64url_decode
from agent_guard.server.factory import _load_public_key

p = Path("/owned/run")
c = load_run_config((p / "run.json").read_bytes(), base_dir=p)
public = json.loads(c.public_manifest.read_bytes())
as_keys = {k: _load_public_key(v, "independent AS trust") for k, v in public["as_keys"].items()}
holder_keys = {
    r["kid"]: load_sm2_public_key(b64url_decode(r["spki_der"])) for r in public["registrations"]
}
with psycopg.connect(_dsn(c.roles["operator"], "authority_dsn")) as conn:
    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    tokens = conn.execute(
        "SELECT g.depth,g.holder_client_id,t.token_jws FROM ag_grants g "
        "JOIN ag_grant_tokens t USING(grant_id) ORDER BY g.depth"
    ).fetchall()
    assert len(tokens) == 3
    claims = []
    for depth, holder, token in tokens:
        payload = verify_compact_jws(token, expected_type="ag-at+jwt", trusted_keys=as_keys)
        claim = validate_access_claims(payload, issuer=public["issuer"], now=payload["iat"])
        assert payload["client_id"] == holder
        claims.append(claim)
    assert [r[0:2] for r in tokens] == [
        (0, "agent-planner"),
        (1, "agent-selector"),
        (2, "agent-executor"),
    ]
    validate_child(claims[0], claims[1])
    validate_child(claims[1], claims[2])
    for parent, child, upper in zip(claims, claims[1:], (240, 180)):
        assert child.raw["exp"] <= parent.raw["exp"]
        assert 0 < child.raw["exp"] - child.raw["iat"] <= upper
    rows = conn.execute(
        "SELECT d.requesting_client_id,e.proof_jws FROM ag_delegations d "
        "JOIN ag_exchange_evidence e ON d.child_grant_id=e.child_grant_id "
        "AND d.parent_grant_id=e.parent_grant_id ORDER BY d.requesting_client_id"
    ).fetchall()
    assert len(rows) == 2 and {r[0] for r in rows} == {"agent-planner", "agent-selector"}
    for holder, proof in rows:
        value = verify_compact_jws(proof, expected_type="ag-pop+jwt", trusted_keys=holder_keys)
        assert value["client_id"] == holder and value["purpose"] == "delegate"
        assert (
            value["htu"] == "https://auth.agent-guard.test/oauth/token"
            and value["htm"] == "POST"
        )
        assert 0 < value["exp"] - value["iat"] <= 60
print(json.dumps({"signed_AS_chain": 3, "signed_holder_delegations": len(rows)}))
"""
    assert json.loads(a33_final.execute("operator", program).stdout) == {
        "signed_AS_chain": 3,
        "signed_holder_delegations": 2,
    }


_IPC_PROGRAM = r'''import dataclasses, json, os, socket, stat, struct, subprocess, sys, time, uuid
from pathlib import Path
from agent_guard.demo.config import HandoffConfig, ChildToken
from agent_guard.demo.handoff import send_child, receive_child

root = Path("/ipc-probes")
root.mkdir(mode=0o755)
run = str(uuid.uuid4())
receiver = r"""import dataclasses, json, os, socket, struct, sys
from pathlib import Path
from agent_guard.demo.config import HandoffConfig
import agent_guard.demo.handoff as h

v = json.loads(sys.argv[1])
v["socket_path"] = Path(v["socket_path"])
c = HandoffConfig(**v)
os.setgroups([c.pair_gid])
os.setgid(c.self_uid)
os.setuid(c.self_uid)
original = h._peer
checks = []


def peer(sock, config):
    value = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    checks.append({"self_uid": os.getuid(), "peer_pid": value[0], "peer_uid": value[1]})
    original(sock, config)


h._peer = peer
original_listen = socket.socket.listen


def listen(sock, *args, **kwargs):
    result = original_listen(sock, *args, **kwargs)
    marker = c.socket_path.parent / ("receiver-" + sys.argv[2] + ".ready")
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    return result


socket.socket.listen = listen
try:
    token = h.receive_child(c, expected_parent=c.peer_client_id)
    assert token.access_token == "IPC_FRAME_ONLY_NOT_AUTHORIZATION"
    assert sys.argv[2] == "positive"
    print(json.dumps({"checks": checks, "uid": os.getuid(), "pid": os.getpid()}))
except ValueError:
    assert sys.argv[2] == "wrongUID" and checks[0]["peer_uid"] != c.peer_uid
    print(
        json.dumps(
            {"checks": checks, "rejected": "wrongUID", "uid": os.getuid(), "pid": os.getpid()}
        )
    )
"""
sender = r"""import json, os, socket, struct, sys
from pathlib import Path
from agent_guard.demo.config import HandoffConfig, ChildToken
import agent_guard.demo.handoff as h

v = json.loads(sys.argv[1])
v["socket_path"] = Path(v["socket_path"])
c = HandoffConfig(**v)
os.setgroups([c.pair_gid])
os.setgid(c.self_uid)
os.setuid(c.self_uid)
original = h._peer
checks = []


def peer(sock, config):
    value = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    checks.append({"self_uid": os.getuid(), "peer_pid": value[0], "peer_uid": value[1]})
    original(sock, config)


h._peer = peer
bad = ChildToken(
    "IPC_FRAME_ONLY_NOT_AUTHORIZATION", c.peer_client_id, c.self_client_id, c.run_id, c.task_id
)
try:
    h.send_child(c, target="agent-foreign", token=bad)
except ValueError:
    pass
else:
    raise AssertionError("arbitrary target allowed")
ack = h.send_child(c, target=c.peer_client_id, token=bad)
assert ack.sender == c.self_client_id and ack.target == c.peer_client_id
print(json.dumps({"checks": checks, "uid": os.getuid(), "pid": os.getpid()}))
"""


def wire(c):
    value = dataclasses.asdict(c)
    value["socket_path"] = str(c.socket_path)
    return json.dumps(value)


for round in range(10):
    for parent, target, suid, ruid, gid in (
        ("planner", "selector", 21008, 21010, 22000),
        ("selector", "executor", 21010, 21003, 22001),
    ):
        directory = root / (parent + "-" + target + "-" + str(round))
        directory.mkdir()
        os.chown(directory, ruid, gid)
        directory.chmod(0o710)
        path = directory / "child.sock"
        a = HandoffConfig(
            path, suid, ruid, "agent-" + parent, "agent-" + target, run, "task-demo", gid, ruid
        )
        b = HandoffConfig(
            path, ruid, suid, "agent-" + target, "agent-" + parent, run, "task-demo", gid, ruid
        )
        p = subprocess.Popen(
            [sys.executable, "-c", receiver, wire(b), "positive"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        ready = directory / "receiver-positive.ready"
        deadline = time.monotonic() + 5
        while not ready.is_file():
            assert p.poll() is None and time.monotonic() < deadline
            time.sleep(0.01)
        ready.unlink()
        info = path.stat()
        assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (ruid, gid, 0o660)
        q = subprocess.run(
            [sys.executable, "-c", sender, wire(a)], capture_output=True, timeout=15
        )
        stdout, stderr = p.communicate(timeout=15)
        assert p.returncode == q.returncode == 0, (stderr, q.stderr)
        recv, send = json.loads(stdout), json.loads(q.stdout)
        assert recv["checks"][0]["peer_uid"] == suid and send["checks"][0]["peer_uid"] == ruid
        assert (
            recv["checks"][0]["peer_pid"] == send["pid"]
            and send["checks"][0]["peer_pid"] == recv["pid"]
        )
        print(
            json.dumps(
                {
                    "round": round,
                    "pair": parent + "-" + target,
                    "sender": send,
                    "receiver": recv,
                }
            ),
            flush=True,
        )
        assert not path.exists()
        # Give the unauthorized UID the exact group deliberately: kernel UID check,
        # rather than directory denial, must independently reject it.
        p = subprocess.Popen(
            [sys.executable, "-c", receiver, wire(b), "wrongUID"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        ready = directory / "receiver-wrongUID.ready"
        deadline = time.monotonic() + 5
        while not ready.is_file():
            assert p.poll() is None and time.monotonic() < deadline
            time.sleep(0.01)
        ready.unlink()
        rogue = (
            "import "
            "os,socket,sys;os.setgroups([int(sys.argv[2])]);os.setgid(21006);os.setuid(2"
            "1006);s=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1]);s.close()"
        )
        q = subprocess.run(
            [sys.executable, "-c", rogue, str(path), str(gid)], capture_output=True, timeout=15
        )
        stdout, stderr = p.communicate(timeout=15)
        assert p.returncode == q.returncode == 0, (stderr, q.stderr)
        row = json.loads(stdout)
        assert row["rejected"] == "wrongUID"
        print(
            json.dumps({"round": round, "pair": parent + "-" + target, "rejected": row}),
            flush=True,
        )
'''

_AUDIT_PROGRAM = r"""import hashlib, json, secrets, socket, ssl, uuid
from pathlib import Path
import psycopg
from psycopg import sql
from urllib.request import Request, build_opener, HTTPSHandler, ProxyHandler
from urllib.error import HTTPError, URLError
from agent_guard.demo.config import load_run_config
from agent_guard.demo.provision import _dsn
from agent_guard.audit.client import AuditClient, AuditUnavailable
from agent_guard.audit.contracts import decode_append_batch, JournalScope, CheckpointTrust
from agent_guard.audit.delivery import verify_checkpoint
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.crypto.sm import serialize_sm2_public_key
from agent_guard.server.factory import _load_public_key

p = Path("/owned/run")
c = load_run_config((p / "run.json").read_bytes(), base_dir=p)
credential = json.loads(c.roles["operator"].private_files["audit_registration"].read_bytes())
writer = credential["writer_id"] + ":" + credential["writer_secret"]
reader = credential["reader_id"] + ":" + credential["reader_secret"]
ca = p / "operator/ca.pem"
origin = c.endpoints["audit_origin"]


def state():
    with psycopg.connect(_dsn(c.roles["operator"], "audit_dsn"), connect_timeout=5) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        names = [
            "ag_checkpoint_streams",
            "ag_checkpoint_records",
            "ag_checkpoint_batches",
            "ag_checkpoints",
            "ag_audit_principals",
            "ag_audit_checkpoint_keys",
        ]
        return {
            name: conn.execute(
                sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY 1").format(
                    sql.Identifier(name)
                )
            ).fetchall()
            for name in names
        }


with psycopg.connect(_dsn(c.roles["operator"], "audit_dsn"), connect_timeout=5) as conn:
    row = conn.execute(
        "SELECT stream_id,gateway_id,tenant_id,task_id,epoch,latest_checkpoint_id "
        "FROM ag_checkpoint_streams"
    ).fetchone()
    assert row is not None and row[5] is not None
    original = conn.execute(
        "SELECT exact_body,checkpoint_id FROM ag_checkpoint_batches WHERE "
        "stream_id=%s ORDER BY start_sequence LIMIT 1",
        (row[0],),
    ).fetchone()
    expected = conn.execute(
        "SELECT jws FROM ag_checkpoints WHERE checkpoint_id=%s", (original[1],)
    ).fetchone()[0]
scope = JournalScope(row[1], row[2], row[3], row[0], row[4])
stream = row[0]
client = AuditClient(
    origin, ca_file=str(ca), writer_credential=writer, reader_credential=reader
)
before = state()
assert client.append(decode_append_batch(bytes(original[0]))) == expected
public = json.loads(c.public_manifest.read_bytes())
trust = tuple(
    CheckpointTrust(
        k,
        "AUDIT_SIGNER",
        serialize_sm2_public_key(_load_public_key(v, "independent audit trust")),
        1,
        None,
    )
    for k, v in public["audit_keys"].items()
)
latest = client.latest(stream)
observed = verify_checkpoint(latest, trust=trust, expected_scope=scope)
assert observed.claims.checkpoint_id == row[5]
history = client.history(stream, observed_checkpoint_id=row[5], after_sequence=0)
records = client.records(stream, observed_checkpoint_id=row[5], after_sequence=0)
assert history.checkpoints and records.entries
assert history.observed_sequence == records.observed_sequence == observed.claims.sequence
assert state() == before
print(
    json.dumps(
        {
            "positive": ["append", "latest", "history", "records"],
            "stream_id": stream,
            "sequence": observed.claims.sequence,
        }
    )
)
context = ssl.create_default_context(cafile=str(ca))
opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context))
for case, endpoint, body, auth in (
    (
        "wrongcredential",
        "latest",
        canonical_json_bytes({"stream_id": stream}),
        credential["reader_id"] + ":" + secrets.token_urlsafe(32),
    ),
    ("wrongrole", "append", bytes(original[0]), reader),
    ("writer-read", "latest", canonical_json_bytes({"stream_id": stream}), writer),
    ("crossscope", "latest", canonical_json_bytes({"stream_id": str(uuid.uuid4())}), reader),
    (
        "unregistered",
        "latest",
        canonical_json_bytes({"stream_id": stream}),
        "unregistered:" + secrets.token_urlsafe(32),
    ),
    ("badframing", "latest", b'{"stream_id":"x","stream_id":"x"}', reader),
    ("oversize", "latest", b" " * 65537, reader),
):
    snap = state()
    request = Request(
        origin + "/v1/audit/" + endpoint,
        data=body,
        method="POST",
        headers={"Authorization": "Bearer " + auth, "Content-Type": "application/json"},
    )
    try:
        with opener.open(request, timeout=5) as response:
            response.read(65537)
    except HTTPError as exc:
        status = exc.code
        exc.read(65537)
        assert status in (400, 401, 403, 413)
    else:
        raise AssertionError("audit denial accepted: " + case)
    assert state() == snap
    print(
        json.dumps(
            {
                "denied": case,
                "status": status,
                "state_sha256": hashlib.sha256(json.dumps(snap).encode()).hexdigest(),
            }
        )
    )
for host in ("auth.agent-guard.test", "gateway.agent-guard.test", "audit.agent-guard.test"):
    with socket.create_connection((host, 443), 5) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            assert tls.getpeercert() and tls.version() in ("TLSv1.2", "TLSv1.3")
    for case, badcontext, name in (
        ("wrongCA", ssl.create_default_context(), host),
        ("wrongSAN", context, "foreign.agent-guard.test"),
    ):
        snap = state()
        try:
            with socket.create_connection((host, 443), 5) as raw:
                with badcontext.wrap_socket(raw, server_hostname=name):
                    pass
        except ssl.SSLCertVerificationError:
            pass
        else:
            raise AssertionError("TLS " + case + " accepted")
        assert state() == snap
        print(json.dumps({"denied": case, "host": host}))
snap = state()
try:
    with socket.create_connection(("audit.agent-guard.test", 443), 5) as plain:
        plain.settimeout(5)
        plain.sendall(
            b"POST /v1/audit/latest HTTP/1.1\r\nHost: "
            b"audit.agent-guard.test\r\nContent-Length: 2\r\n\r\n{}"
        )
        response = plain.recv(65536)
        assert not response.startswith(b"HTTP/")
except (ConnectionResetError, ssl.SSLError):
    pass
assert state() == snap
print(json.dumps({"denied": "plainHTTP"}))
"""
