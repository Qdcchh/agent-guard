"""Clean deployment obligations, executed only after final S2 assembly.

The explicit S0 precheck does not import scenario code or claim final CLI coverage.
Full nodes require final resources and retained complete inherited JUnit reports.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.integration.test_a33_roles import (
    REPO,
    digest,
)
from tests.integration.test_a33_roles import (
    a33_final as _final_fixture,
)
from tests.integration.test_a33_roles import (
    a33_install as _install_fixture,
)

pytestmark = pytest.mark.integration
a33_final = _final_fixture
a33_install = _install_fixture

_INSTALL_PROGRAM = r"""import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import sysconfig
from pathlib import Path
import agent_guard.demo.config, agent_guard.demo.init, agent_guard.demo.did_bootstrap
import agent_guard.audit.delivery, agent_guard.audit.migrate, agent_guard.ledger.migrate

assert sys.version_info[:2] == (3, 11)
assert os.environ.get("PYTHONPATH", "") == ""
assert Path.cwd() == Path("/outside")
paths = {}
for module in (
    agent_guard.demo.config,
    agent_guard.demo.init,
    agent_guard.demo.did_bootstrap,
    agent_guard.audit.delivery,
    agent_guard.audit.migrate,
    agent_guard.ledger.migrate,
):
    p = Path(module.__file__)
    assert str(p).startswith("/opt/runtime/lib/python3.11/site-packages/")
    paths[module.__name__] = {
        "path": str(p),
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }
assert not any(n == "tests" or n.startswith("tests.") for n in sys.modules)
assert not Path("/opt/runtime/lib/python3.11/site-packages/agent_guard.egg-link").exists()
assert not list(Path("/opt/runtime/lib/python3.11/site-packages").glob("__editable__*"))
wheel = next(Path("/wheels").glob("agent_guard-*.whl"))
import zipfile

with zipfile.ZipFile(wheel) as z:
    names = set(z.namelist())
    assert "agent_guard/demo/__main__.py" in names
    assert any(n.endswith("migrations/audit/001_checkpoint_store.sql") for n in names)
    assert all(
        any(n.endswith("/" + p.name) for n in names)
        for p in Path("/package/migrations").rglob("*.sql")
    )
for args, expected in ((["--help"], 0), (["check", "--config", "/missing.json"], 2)):
    p = subprocess.run(
        [sys.executable, "-m", "agent_guard.demo", *args], capture_output=True, timeout=15
    )
    assert p.returncode == expected
    assert b"Traceback" not in p.stderr
pip = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, timeout=30)
assert pip.returncode == 0
print(
    json.dumps(
        {
            "status": "PRECHECK_ONLY",
            "python": platform.python_version(),
            "architecture": platform.machine(),
            "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "wheel_bytes": wheel.stat().st_size,
            "modules": paths,
            "pip_check_exit": pip.returncode,
            "distribution": importlib.metadata.version("agent-guard"),
        }
    )
)
"""


def test_s0_install_cli_precheck(a33_install):
    value = json.loads(a33_install["execute"](_INSTALL_PROGRAM))
    assert value["status"] == "PRECHECK_ONLY"
    assert value["python"].startswith("3.11.")
    assert value["pip_check_exit"] == 0
    for name, module in value["modules"].items():
        assert module["sha256"] == digest(REPO / "src" / (name.replace(".", "/") + ".py"))

    assert re.fullmatch(r"[0-9a-f]{64}", value["wheel_sha256"])
    # Retain the binary itself, not merely a claimed wheel hash.
    native = a33_install["native"]
    name = "ag-a33-wheel-copy-" + a33_install["run_id"]
    container_id = (
        native.call(
            [
                "docker",
                "create",
                "--name",
                name,
                "--label",
                "agent-guard.owner=" + a33_install["owner"],
                "--label",
                "agent-guard.run=" + a33_install["run_id"],
                a33_install["image"],
            ]
        )
        .stdout.decode()
        .strip()
    )
    a33_install["record_container"](container_id)
    try:
        result = json.loads(native.call(["docker", "inspect", container_id]).stdout)[0]
        assert (
            result["Id"] == container_id
            and result["Config"]["Labels"]["agent-guard.owner"] == a33_install["owner"]
        )
        native.call(["docker", "cp", container_id + ":/wheels/.", str(a33_install["evidence"])])
        wheels = list(a33_install["evidence"].glob("agent_guard-*.whl"))
        assert len(wheels) == 1 and digest(wheels[0]) == value["wheel_sha256"]
    finally:
        result = json.loads(native.call(["docker", "inspect", container_id]).stdout)[0]
        assert (
            result["Id"] == container_id
            and result["Config"]["Labels"]["agent-guard.owner"] == a33_install["owner"]
        )
        native.call(["docker", "rm", container_id])


def _junit_complete(path):
    root = ET.parse(path).getroot()
    suites = list(root.iter("testsuite"))
    assert not any(list(root.iter(tag)) for tag in ("failure", "error", "skipped"))
    assert suites and sum(int(s.attrib["tests"]) for s in suites) > 0
    assert all(
        int(s.attrib.get(k, 0)) == 0 for s in suites for k in ("failures", "errors", "skipped")
    )
    return {case.attrib["classname"] + "::" + case.attrib["name"] for case in root.iter("testcase")}


def _required_inherited(a33_final, a33_install, roots, *, group_mode=None):
    """Execute unchanged inherited assertions in a finite owned test controller.

    Test administrator connections never enter a normal role's environment or
    private mount. S2 supplies an exclusive three-domain test connection file;
    the controller mounts final tests read-only and imports the installed package.
    """
    connections = Path(
        getattr(a33_final, "controller_inputs", None) or os.environ["AG33_TEST_CONNECTIONS_FILE"]
    ).resolve()
    assert connections.is_file() and connections.stat().st_mode & 0o077 == 0
    if hasattr(a33_final, "owner_controller"):
        assert (connections.parent / "a31-tls/receipt.json").is_file()
    input_values = json.loads(connections.read_bytes())
    assert set(input_values) == {"authority", "downstream", "audit"}
    program = (
        r"""import json, os, subprocess, sys
from pathlib import Path
from psycopg.conninfo import conninfo_to_dict

os.umask(0o077)
Path(os.environ["HOME"]).mkdir(mode=0o700, exist_ok=True)
connections = json.loads(Path("/test-inputs/connections.json").read_bytes())
hosts = set()
for key, domain in (
    ("AGENT_GUARD_TEST_DATABASE_URL", "authority"),
    ("AGENT_GUARD_A31_TEST_DOWNSTREAM_DATABASE_URL", "downstream"),
    ("AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL", "audit"),
):
    params = conninfo_to_dict(connections[domain])
    assert params["sslmode"] == "verify-full"
    hosts.add(params["host"])
    os.environ[key] = connections[domain]
assert len(hosts) == 3
os.environ["PYTHONPATH"] = ""
os.environ["PR9_TEST_CONTROLLER_OWNER"] = __CONTROLLER_OWNER__
os.environ["PR9_TEST_CONTROLLER_RUN"] = __CONTROLLER_RUN__
os.environ["PR9_TEST_CONTROLLER_IMAGE"] = __CONTROLLER_IMAGE__
if Path("/test-inputs/a31-tls/receipt.json").is_file():
    os.environ["PR9_A31_TLS_RECEIPT"] = "/test-inputs/a31-tls/receipt.json"
    os.environ["PR9_CI_OWNER"] = EXPECTED_OWNER
os.environ["AG31_SERVICE_EVIDENCE_DIR"] = "/tmp/a33-inherited/native"
os.environ["A31_TEST_EVIDENCE_DIR"] = "/tmp/a33-inherited/native"
Path("/tmp/a33-inherited/native").mkdir(parents=True, exist_ok=True, mode=0o700)
result = subprocess.run(
    [
        sys.executable,
        "-m",
        "pytest",
        *ROOTS,
        "-q",
        "--junitxml=/tmp/a33-inherited/results.xml",
        "-o",
        "cache_dir=/tmp/a33-inherited/cache",
    ],
    cwd="/testsource",
    timeout=14400,
)
raise SystemExit(result.returncode)
""".replace("ROOTS", repr(roots))
        .replace("EXPECTED_OWNER", repr(a33_final.owner))
        .replace("__CONTROLLER_OWNER__", repr(a33_install["owner"]))
        .replace("__CONTROLLER_RUN__", repr(a33_install["run_id"]))
        .replace("__CONTROLLER_IMAGE__", repr(a33_install["image"]))
    )
    if group_mode is not None:
        prefix = program.split("result = subprocess.run(", 1)[0]
        if group_mode == "child-probe":
            program = prefix + (
                "import sys; sys.path.insert(0, '/testsource')\n"
                "from tools.pr9_deploy_inputs import run_legacy_child_probe\n"
                "value = run_legacy_child_probe("
                + repr(a33_install["mode"])
                + ", '/tmp/a33-inherited/child-probe')\n"
                "Path('/tmp/a33-inherited/child-probe.json').write_text(json.dumps(value))\n"
            )
        elif group_mode == "legacy-closure":
            program = prefix + (
                "import sys; sys.path.insert(0, '/testsource')\n"
                "from tools.pr9_deploy_inputs import run_legacy_closure_groups\n"
                "run_legacy_closure_groups("
                + repr(a33_install["mode"])
                + ", '/tmp/a33-inherited/groups', "
                + repr(a33_final.run_id)
                + ", "
                + repr(a33_final.owner)
                + ")\n"
            )
        else:
            program = prefix + (
                "import sys; sys.path.insert(0, '/testsource')\n"
                "from tools.pr9_deploy_inputs import run_inherited_groups\n"
                "run_inherited_groups("
                + repr(group_mode)
                + ", '/tmp/a33-inherited/groups', "
                + repr(a33_final.run_id)
                + ", "
                + repr(a33_final.owner)
                + ")\n"
            )
    capacity_mount = []
    if os.environ.get("PR9_CAPACITY_INPUTS_ROOT"):
        from tools.pr9_deploy_inputs import validate_capacity_inputs

        capacity_root = validate_capacity_inputs(os.environ["PR9_CAPACITY_INPUTS_ROOT"])
        capacity_mount = [
            "--mount",
            "type=bind,src=" + str(capacity_root) + ",dst=/capacity/inputs,readonly",
        ]
        binding_program = (
            "import sysconfig; sys.path.insert(0, '/testsource')\n"
            "from tools.pr9_capacity_inputs import bind_installed\n"
            "bind_installed('/capacity/inputs/container-binding.json', "
            "sysconfig.get_path('purelib'), '/testsource/src', "
            "'/tmp/a33-inherited/consumer-capacity-binding.json')\n"
            "os.environ['AG32_FIXED_CAPACITY_DEPENDENCY'] = "
            "'/tmp/a33-inherited/consumer-capacity-binding.json'\n"
        )
        program = program.replace(
            'Path("/tmp/a33-inherited/native").mkdir(parents=True, exist_ok=True, mode=0o700)\n',
            'Path("/tmp/a33-inherited/native").mkdir(parents=True, exist_ok=True, mode=0o700)\n'
            + binding_program,
        )
    native = a33_install["native"]
    cli_source = Path(shutil.which("docker"))
    cli_bytes = cli_source.read_bytes()
    assert cli_bytes.startswith(b"\x7fELF"), "trusted nested Docker CLI must be Linux ELF"
    cli = a33_install["evidence"] / "linux-docker-cli"
    if not cli.exists():
        cli.write_bytes(cli_bytes)
        cli.chmod(0o500)
    cli_sha = hashlib.sha256(cli_bytes).hexdigest()
    assert digest(cli) == cli_sha
    expected_cli_sha = os.environ.get("PR9_TRUSTED_DOCKER_CLI_SHA256")
    if expected_cli_sha is not None:
        assert re.fullmatch(r"[0-9a-f]{64}", expected_cli_sha) and cli_sha == expected_cli_sha
    cli_version = native.call([str(cli), "version", "--format", "{{.Client.Version}}"])
    (a33_install["evidence"] / "trusted-docker-cli-binding.json").write_text(
        json.dumps({"sha256": cli_sha, "client_version": cli_version.stdout.decode().strip()})
    )
    (a33_install["evidence"] / "trusted-docker-cli-binding.json").chmod(0o600)
    pg_ids = _pgs(a33_final)
    networks = set()
    for pg_id in pg_ids.values():
        pg = json.loads(a33_final.native.call(["docker", "inspect", pg_id]).stdout)[0]
        for network in pg["NetworkSettings"]["Networks"].values():
            network_id = network["NetworkID"]
            assert re.fullmatch(r"[0-9a-f]{64}", network_id)
            net = json.loads(native.call(["docker", "network", "inspect", network_id]).stdout)[0]
            assert net["Id"] == network_id and net["Labels"]["agent-guard.owner"] == a33_final.owner
            assert net["Labels"]["agent-guard.run"] == a33_final.run_id
            networks.add(network_id)
    assert len(networks) >= 3
    networks = sorted(networks)
    authority = json.loads(native.call(["docker", "inspect", pg_ids["authority"]]).stdout)[0]
    legacy_pg_gate = {
        "version": 1,
        "owner_id": a33_final.owner,
        "run_id": a33_final.run_id,
        "pg_full_id": authority["Id"],
        "pg_image_full_id": authority["Image"],
        "network_full_ids": sorted(
            n["NetworkID"] for n in authority["NetworkSettings"]["Networks"].values()
        ),
        "host": "pg-authority.agent-guard.test",
        "port": 5432,
        "ca_sha256": digest(connections.parent / "ca.pem"),
    }
    program = (
        "import os\nos.environ['PR9_LEGACY_PG_GATE'] = "
        + repr(json.dumps(legacy_pg_gate))
        + "\n"
        + program
    )
    name = "ag-a33-inherited-" + str(__import__("uuid").uuid4())
    created = (
        native.call(
            [
                "docker",
                "create",
                "--platform",
                "linux/amd64",
                "--name",
                name,
                "--hostname",
                name,
                "--user",
                str(os.getuid()) + ":" + str(os.getgid()),
                "--tmpfs",
                "/private:rw,noexec,nosuid,nodev,size=16m,uid="
                + str(os.getuid())
                + ",gid="
                + str(os.getgid())
                + ",mode=0700",
                "--add-host",
                "audit.agent-guard.test:127.0.0.1",
                "--add-host",
                "gateway.agent-guard.test:127.0.0.2",
                "--group-add",
                str(Path("/var/run/docker.sock").stat().st_gid),
                "--env",
                "HOME=/tmp/pr9-controller-home",
                "--label",
                "agent-guard.owner=" + a33_install["owner"],
                "--label",
                "agent-guard.run=" + a33_install["run_id"],
                "--network",
                networks[0],
                "--mount",
                "type=bind,src=" + str(REPO) + ",dst=/testsource,readonly",
                "--mount",
                "type=bind,src=" + str(connections.parent) + ",dst=/test-inputs,readonly",
                *capacity_mount,
                "--mount",
                "type=bind,src=" + str(cli) + ",dst=/usr/local/bin/docker,readonly",
                "--mount",
                "type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock",
                a33_install["image"],
                "/opt/runtime/bin/python",
                "-c",
                program,
            ]
        )
        .stdout.decode()
        .strip()
    )
    assert re.fullmatch(r"[0-9a-f]{64}", created)
    a33_install["containers"].append(created)
    a33_install["record_container"](created)
    value = json.loads(native.call(["docker", "inspect", created]).stdout)[0]
    assert (
        value["Id"] == created
        and value["Config"]["Labels"]["agent-guard.owner"] == a33_install["owner"]
    )
    for network_id in networks[1:]:
        native.call(["docker", "network", "connect", network_id, created])
    result = native.call(["docker", "start", "-a", created], timeout=14460, check=False)
    value = json.loads(native.call(["docker", "inspect", created]).stdout)[0]
    path = native.evidence / ("inherited-" + str(native.sequence))
    path.mkdir(mode=0o700)
    copied = native.call(
        ["docker", "cp", created + ":/tmp/a33-inherited/.", str(path)], check=False
    )
    assert value["State"]["ExitCode"] == 0, result.stdout.decode()[-1500:]
    assert copied.returncode == 0, "actual inherited evidence must be retained"
    native.call(["docker", "rm", created])
    a33_install["containers"].remove(created)
    if group_mode == "child-probe":
        value = json.loads((path / "child-probe.json").read_bytes())
        assert value["actual_live_child_records"] >= 7
        assert len(value["negative_controls"]) == 4
        assert all(row["native_exit"] != 0 for row in value["negative_controls"])
        return value
    if group_mode is not None:
        return path / "groups/index.json"
    ids = _junit_complete(path / "results.xml")
    for node in roots:
        file, _, function = node.partition("::")
        classname = file.removesuffix(".py").replace("/", ".")
        assert any(i.startswith(classname + "::" + function) for i in ids), (node, ids)
    return ids


def test_clean_source_wheel_without_model_api(a33_final, a33_install):
    test_s0_install_cli_precheck(a33_install)
    # The exact final A33 README block is executable, without rewriting commands.
    readme = (REPO / "README.md").read_text()
    begin, end = "# A33-REPRODUCE-BEGIN", "# A33-REPRODUCE-END"
    assert readme.count(begin) == readme.count(end) == 1
    script = readme.split(begin, 1)[1].split(end, 1)[0]
    assert "OPENAI_API_KEY" not in script and "MODEL_API_KEY" not in script
    assert "docker compose" in script and "agent_guard.demo" in script
    evidence = a33_final.native.evidence / "readme-execution"
    evidence.mkdir(exist_ok=True)
    environment = dict(
        os.environ,
        AG33_RUN_ID=a33_final.run_id,
        AG33_OWNER_ID=a33_final.owner,
        AG33_PROJECT=a33_final.manifest["project"],
        AG33_REPOSITORY=str(REPO),
    )
    if hasattr(a33_final, "owner_controller"):
        environment.update(
            AG33_FINAL_RESOURCE_MANIFEST=str(
                a33_final.owner_controller.root / "allocated-resources.json"
            ),
            AG33_FINAL_RUN_CONFIG=str(a33_final.config),
        )
    environment.pop("PYTHONPATH", None)
    for key in tuple(environment):
        if key.endswith("API_KEY"):
            environment.pop(key)
    a33_final.native.call(
        ["zsh", "-eu", "-c", script], cwd=evidence, env=environment, timeout=14400
    )
    # Observe actual final imports and lock versions after the documented commands.
    program = r"""import hashlib, importlib.metadata, json, os, subprocess, sys
from pathlib import Path
import agent_guard.demo.config

p = Path(agent_guard.demo.config.__file__)
assert "site-packages" in p.parts and "/testsource/" not in str(p)
assert os.environ.get("PYTHONPATH", "") == ""
assert not any(n == "tests" or n.startswith("tests.") for n in sys.modules)
assert sys.version_info[:2] == (3, 11)
assert not list(p.parents[1].glob("__editable__*"))
result = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, timeout=30)
assert result.returncode == 0
print(
    json.dumps(
        {
            "module_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "module_path": str(p),
            "version": importlib.metadata.version("agent-guard"),
            "locked_versions": {name: importlib.metadata.version(name) for name in LOCKS},
        }
    )
)
"""
    locks = {}
    for line in (REPO / "requirements.lock").read_text().splitlines():
        if "==" in line and not line.startswith("#"):
            name, version = line.split("==")
            locks[name] = version
    result = json.loads(a33_final.execute("operator", program.replace("LOCKS", repr(locks))).stdout)
    assert result["module_sha256"] == digest(REPO / "src/agent_guard/demo/config.py")
    assert result["locked_versions"] == locks
    # Full inherited group inventory is supplied as test XML, with exact node
    # coverage. JSON status booleans are deliberately not accepted as execution.
    if hasattr(a33_final, "owner_controller"):
        index = _required_inherited(a33_final, a33_install, [], group_mode=a33_install["mode"])
    else:
        index = Path(os.environ["AG33_INHERITED_XML_INDEX"])
    groups = json.loads(index.read_bytes())
    registry = json.loads(
        (REPO / "tasks/workflow/runs/A3.3-delivery-20261011/node-bindings-v3.json").read_bytes()
    )
    expected = registry["inherited_accepted_registry"][a33_install["mode"]]["commands20"]
    assert len(groups) == 20 and {g["id"] for g in groups} == set(expected)
    for group in groups:
        assert (group["run_id"], group["owner_id"]) == (a33_final.run_id, a33_final.owner)
        xml = index.parent / group["path"]
        assert digest(xml) == group["sha256"]
        required = set()
        for node in expected[group["id"]]["actual_nodeids"]:
            file, _, function = node.partition("::")
            required.add(file.removesuffix(".py").replace("/", ".") + "::" + function)
        assert _junit_complete(xml) >= required


def _pgs(a33_final):
    result = {}
    for domain in ("authority", "downstream", "audit"):
        native = a33_final.native
        ids = (
            native.call(
                [
                    "docker",
                    "ps",
                    "-aq",
                    "--no-trunc",
                    "--filter",
                    "label=agent-guard.owner=" + a33_final.owner,
                    "--filter",
                    "label=agent-guard.run=" + a33_final.run_id,
                    "--filter",
                    "label=com.docker.compose.service=pg-" + domain,
                ]
            )
            .stdout.decode()
            .split()
        )
        assert len(ids) == 1 and re.fullmatch(r"[0-9a-f]{64}", ids[0])
        value = json.loads(native.call(["docker", "inspect", ids[0]]).stdout)[0]
        assert value["Id"] == ids[0]
        assert value["Config"]["Labels"]["agent-guard.owner"] == a33_final.owner
        assert value["Config"]["Labels"]["agent-guard.run"] == a33_final.run_id
        result[domain] = ids[0]
    return result


def test_rotation_upgrade_backup_restore_owner_cleanup(a33_final, a33_install):
    _required_inherited(
        a33_final,
        a33_install,
        [
            "tests/integration/test_key_rotation.py::test_rotation_signs_with_new_kid_an"
            "d_keeps_old_tokens_verifiable",
            "tests/integration/test_key_rotation.py::test_current_client_disable_does_no"
            "t_replace_historical_receipt_trust",
            "tests/integration/test_receipt_publication.py::test_old_ready_key_rotation_"
            "stays_byte_identical",
            "tests/integration/test_a2_migrations.py::test_p19_upgrade_from_001_preserve"
            "s_nonzero_seven_tables",
            "tests/integration/test_a2_migrations.py::test_p19_upgrade_from_003_preserve"
            "s_nonzero_seven_tables",
            "tests/integration/test_a2_migrations.py::test_p19_illegal_upgrade_changes_nothing",
            "tests/integration/test_audit_service.py::test_checkpoint_history_encoded_pa"
            "ges_rotation",
            "tests/integration/test_audit_service.py::test_audit_restore_behind_external"
            "_pin_refused",
        ],
    )
    native = a33_final.native
    # Stop exact owner writers before taking an as-of snapshot; zero active
    # writer sessions and old container exit are independently observed.
    for role in ("as", "gateway", "worker", "publisher"):
        a33_final.inspect(role)
        native.call(["docker", "stop", "--time", "10", a33_final.ids[role]])
        assert a33_final.inspect(role)["State"]["Running"] is False
    projection_sql = r"""BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT format($q$SELECT %L,
  COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]'::jsonb)
  FROM %I t;$q$,tablename,tablename)
FROM pg_tables WHERE schemaname='public' ORDER BY tablename
\gexec
COMMIT;"""
    for domain, container_id in _pgs(a33_final).items():
        database = "ag_" + domain
        restore = "ag_a33_restore_" + domain
        prefix = ["docker", "exec", "-i", container_id]
        before = native.call(
            [
                *prefix,
                "psql",
                "-U",
                "postgres",
                "-d",
                database,
                "-qAt",
                "-v",
                "ON_ERROR_STOP=1",
            ],
            input=projection_sql.encode(),
        ).stdout
        assert before.strip()
        dump = native.call([*prefix, "pg_dump", "-U", "postgres", "-d", database, "-Fc"]).stdout
        assert dump.startswith(b"PGDMP")
        native.call(
            [
                *prefix,
                "psql",
                "-U",
                "postgres",
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                "CREATE DATABASE " + restore + " TEMPLATE template0;",
            ]
        )
        try:
            native.call(
                [*prefix, "pg_restore", "-U", "postgres", "-d", restore, "--exit-on-error"],
                input=dump,
            )
            after = native.call(
                [
                    *prefix,
                    "psql",
                    "-U",
                    "postgres",
                    "-d",
                    restore,
                    "-qAt",
                    "-v",
                    "ON_ERROR_STOP=1",
                ],
                input=projection_sql.encode(),
            ).stdout
            assert before == after, "restored per-column rows differ from the as-of snapshot"
        finally:
            native.call(
                [
                    *prefix,
                    "psql",
                    "-U",
                    "postgres",
                    "-d",
                    "postgres",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-c",
                    "DROP DATABASE " + restore + " WITH (FORCE);",
                ]
            )
    # Cleanup owns the whole fresh deployment for this root; S2 must supply a
    # separate deployment for the next full root. Full IDs are never reconstructed.
    for role in (
        "as",
        "gateway",
        "worker",
        "publisher",
        "planner",
        "selector",
        "executor",
        "export",
        "offline",
        "did",
        "audit",
        "operator",
    ):
        a33_final.inspect(role)
        native.call(["docker", "rm", "-f", a33_final.ids[role]])
    for container_id in _pgs(a33_final).values():
        native.call(["docker", "rm", "-f", container_id])
    # Network/volume inventory filters only this owner and verifies every item.
    for kind in ("network", "volume"):
        ids = (
            native.call(
                [
                    "docker",
                    kind,
                    "ls",
                    "-q",
                    "--filter",
                    "label=agent-guard.owner=" + a33_final.owner,
                ]
            )
            .stdout.decode()
            .split()
        )
        for item in ids:
            value = json.loads(native.call(["docker", kind, "inspect", item]).stdout)[0]
            assert value["Labels"]["agent-guard.owner"] == a33_final.owner
            assert value["Labels"]["agent-guard.run"] == a33_final.run_id
            exact = value["Id"] if kind == "network" else value["Name"]
            native.call(["docker", kind, "rm", exact])
        assert (
            native.call(
                [
                    "docker",
                    kind,
                    "ls",
                    "-q",
                    "--filter",
                    "label=agent-guard.owner=" + a33_final.owner,
                ]
            ).stdout.strip()
            == b""
        )
    assert (
        native.call(
            ["docker", "ps", "-aq", "--filter", "label=agent-guard.owner=" + a33_final.owner]
        ).stdout.strip()
        == b""
    )


def test_max_legal_payload_bounded_package_and_expired_public_export(a33_final, a33_install):
    _required_inherited(
        a33_final,
        a33_install,
        [
            "tests/integration/test_a32_joint_tls.py::test_real_accepted_wide_chain_256_"
            "items_component_export_offline",
            "tests/integration/test_execution_final_boundaries.py::test_item_bound_is_en"
            "forced_before_accept_and_full_256_recovers",
            "tests/integration/test_evidence_export.py::test_export_actual_wire_and_logi"
            "cal_capacity",
            "tests/unit/test_task_bundle_codec.py::test_exact_lf_line_boundary_and_count"
            "er_capacity",
            "tests/unit/test_task_evidence_verify.py::test_historical_keys_roles_registr"
            "ation_rotation",
        ],
    )
    # Final deterministic 256-item route, not a JSON PASS supplied by a peer.
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
            "/tmp/a33-capacity",
            "--capacity-items",
            "256",
        ],
        timeout=14400,
    )
    output = a33_final.native.evidence / "capacity"
    output.mkdir(exist_ok=True)
    a33_final.native.call(
        ["docker", "cp", a33_final.ids["operator"] + ":/tmp/a33-capacity/.", str(output)]
    )
    bundle = output / "task-bundle.ndjson"
    assert bundle.is_file() and bundle.stat().st_size <= 268435456
    with bundle.open("rb") as stream:
        assert sum(len(line) for line in stream) == bundle.stat().st_size
    # Actual independent network-free role verifier; distinct trust and external pin.
    program = r"""import dataclasses, json, os, socket
from pathlib import Path
from agent_guard.evidence.task_verify import verify_task_bundle, load_public_trust

p = Path("/inputs")
trust = load_public_trust(json.loads((p / "public-trust.json").read_bytes()))
pin = json.loads((p / "external-pin.json").read_bytes())
with (p / "task-bundle.ndjson").open("rb") as f:
    report = verify_task_bundle(f, external_trust=trust, external_pin=pin)
assert report.cryptographic_consistency == "VERIFIED"
print(json.dumps(dataclasses.asdict(report)))
"""
    result = a33_final.execute("offline", program, timeout=300)
    assert json.loads(result.stdout)["cryptographic_consistency"] == "VERIFIED"
    operator = r"""import hashlib, json, psycopg
from pathlib import Path
from agent_guard.demo.config import load_run_config
from agent_guard.demo.provision import _dsn
from agent_guard.contracts.encoding import load_strict_json
from psycopg.conninfo import conninfo_to_dict

p = Path("/owned/run")
c = load_run_config((p / "run.json").read_bytes(), base_dir=p)
with psycopg.connect(_dsn(c.roles["operator"], "authority_dsn")) as conn:
    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    grants = conn.execute(
        "SELECT "
        "depth,holder_client_id,amount_limit,call_limit,amount_reserved,amount_settl"
        "ed,calls_reserved,calls_settled,expires_at,revoked_at FROM ag_grants ORDER "
        "BY depth"
    ).fetchall()
    assert len(grants) == 3
    assert [(r[0], r[1], r[2], r[3]) for r in grants] == [
        (0, "agent-planner", 100000, 12),
        (1, "agent-selector", 80000, 10),
        (2, "agent-executor", 70000, 8),
    ]
    assert all(r[4:8] == (0, 70000, 0, 4) for r in grants)
    now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
    assert all(exp <= now or revoked is not None for *_, exp, revoked in grants)
    evidence = conn.execute(
        "SELECT "
        "v.body_bytes,v.token_bytes,v.proof_bytes,v.chain_json,o.operation_id,o.stat"
        "us FROM ag_verified_evidence v JOIN ag_operation_evidence e "
        "USING(evidence_ref) JOIN ag_operations o USING(operation_id) WHERE "
        "e.kind='first' AND o.tool_id='procurement.order.create'"
    ).fetchall()
    assert len(evidence) == 1
    body, token, proof, chain, operation, status = evidence[0]
    parsed = load_strict_json(bytes(body))
    items = parsed["params"]["items"]
    assert len(items) == 256 and {r["sku"] for r in items} == {
        "s" + str(i).zfill(3) for i in range(256)
    }
    assert all(r["quantity"] == 1 for r in items)
    assert len(body) <= 65536 and len(token) <= 16384 and len(proof) <= 16384
    assert (
        len(load_strict_json(load_strict_json(bytes(chain))["chain"].encode())) == 3
        and status == "SUCCEEDED"
    )
    outbox = conn.execute(
        "SELECT receipt_status,result_bytes,amount_fen FROM ag_receipt_outbox WHERE "
        "operation_id=%s",
        (operation,),
    ).fetchone()
    assert outbox[0] == "READY" and outbox[2] == 70000
    result = load_strict_json(bytes(outbox[1]))
    assert len(result["items"]) == 256 and result["total_fen"] == 70000
    phases = conn.execute(
        "SELECT phase,count(*) FROM ag_ledger_events WHERE operation_id=%s GROUP BY phase",
        (operation,),
    ).fetchall()
    assert dict(phases) == {"RESERVE": 1, "SETTLE": 1}
with psycopg.connect(_dsn(c.roles["operator"], "downstream_dsn")) as conn:
    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    actual = conn.execute(
        "SELECT amount_fen,result_bytes FROM ds_operations WHERE operation_id=%s", (operation,)
    ).fetchone()
    assert actual == (70000, outbox[1])
    assert conn.execute(
        "SELECT count(*) FROM ds_orders WHERE operation_id=%s", (operation,)
    ).fetchone() == (1,)
    assert conn.execute("SELECT count(*) FROM ds_notifications").fetchone() == (1,)
bundle = Path("/tmp/a33-capacity/task-bundle.ndjson").read_bytes()
assert b"BEGIN PRIVATE KEY" not in bundle and b"BEGIN EC PRIVATE KEY" not in bundle
needles = []
login = json.loads(c.roles["operator"].private_files["user_login"].read_bytes())
needles.append(login["password"].encode())
registration = json.loads(c.roles["operator"].private_files["audit_registration"].read_bytes())
needles += [v.encode() for k, v in registration.items() if k.endswith("_secret")]
needles.append(c.roles["operator"].private_files["downstream_secret"].read_bytes().strip())
for domain in ("authority", "downstream", "audit"):
    needles.append(
        conninfo_to_dict(_dsn(c.roles["operator"], domain + "_dsn"))["password"].encode()
    )
assert all(needle and needle not in bundle for needle in needles)
print(
    json.dumps(
        {
            "database_clock": now.isoformat(),
            "grants": len(grants),
            "actual_items": len(items),
            "result_items": len(result["items"]),
            "body_sha256": hashlib.sha256(bytes(body)).hexdigest(),
            "result_sha256": hashlib.sha256(bytes(outbox[1])).hexdigest(),
            "bundle_sha256": hashlib.sha256(bundle).hexdigest(),
            "bytes": len(bundle),
        }
    )
)
"""
    assert json.loads(a33_final.execute("operator", operator).stdout)["grants"] >= 3
