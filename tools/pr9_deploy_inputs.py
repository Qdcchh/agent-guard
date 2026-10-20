"""Trusted, finite PR9 deployment inputs; never imports this module in normal roles.

Each context owns twelve roles and three PG instances. Only immutable Docker
build layers may be reused. All private results stay beneath a mode-0700 root.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def source_binding():
    """Hash actual candidate input bytes, never an old acceptance claim."""
    roots = (REPO / "src", REPO / "migrations", REPO / "deploy/demo")
    paths = [p for root in roots for p in root.rglob("*") if p.is_file()]
    paths += [
        REPO / n
        for n in (
            "pyproject.toml",
            "requirements.lock",
            "requirements-dev.lock",
            "requirements-ci.lock",
        )
    ]
    return {
        str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(paths)
        if "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def load_supervisor():
    spec = importlib.util.spec_from_file_location("pr9_owner", REPO / "deploy/demo/supervisor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def deployment(root, mode):
    """Create a real owner deployment and reap it even after assertion failure."""
    root = Path(root).absolute()
    for path in (root, *root.parents):
        if path.is_symlink():
            raise ValueError("deployment symlink root forbidden")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.stat().st_mode & 0o077:
        raise ValueError("PR9 private root must be mode 0700")
    if mode not in ("source", "wheel"):
        raise ValueError("unknown install mode")
    run = str(uuid.uuid4())
    module = load_supervisor()
    before = source_binding()
    args = argparse.Namespace(
        run_id=run,
        owner_id="pr9-deploy-" + run,
        evidence=str(root / run),
        mode=mode,
        capacity_items=1,
    )
    previous = os.umask(0o077)
    owner = module.Owner(args)
    try:
        owner.setup()
        if source_binding() != before:
            raise ValueError("candidate changed during deployment assembly")
        module.atomic(owner.root / "candidate-input-binding.json", before)
        yield owner
    finally:
        try:
            owner.cleanup()
        finally:
            os.umask(previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--mode", choices=("source", "wheel"))
    cleanup_options = parser.add_mutually_exclusive_group()
    cleanup_options.add_argument("--cleanup", action="store_true")
    cleanup_options.add_argument("--cleanup-all", action="store_true")
    parser.add_argument("--installation-evidence-root")
    args = parser.parse_args()
    if args.cleanup_all:
        cleanup_all(args.root, installation_evidence_root=args.installation_evidence_root)
        return 0
    if args.cleanup:
        cleanup_recorded(args.root)
        return 0
    if args.mode is None:
        parser.error("--mode is required unless --cleanup is selected")
    with deployment(args.root, args.mode) as owner:
        # Finite native smoke is reviewable without leaving a background owner.
        owner.call(
            owner.command("operator", ["normal", "--out", "/tmp/normal-output"]), timeout=14400
        )
        print(json.dumps({"run_id": owner.run, "owner_id": owner.owner, "status": "EXECUTED"}))
    return 0


SIDECAR_SHA256 = {
    "a31_enhanced_live_r1.py": "bcc25f52162d7a5d1609df89ecb3643ab801c2b8df1d36039e790d176b7208ec",
    "a31_enhanced_live_r1.pth": "2be4c84c34a38931c59eeca937245691990d7ad68f415b568c97bd6cf573b3ef",
    "a31_runtime_observer.py": "3406f8059492ccc0179623b23baa9333e28ffe12f16925aa64d9cfbfa576d6a3",
    "a31_runtime_observer.pth": "c14942db734f447a40d60eb96b7d98d9e4f6df4625627d0b01a4ab99e6fba324",
}


def prepare_legacy_sidecars(destination, mode):
    """Install only pinned public observer source with physical UID/path adapters."""
    import ast

    if mode not in ("source", "wheel"):
        raise ValueError("invalid observer mode")
    destination = Path(destination)
    destination.mkdir(mode=0o700)
    provenance = json.loads(
        (REPO / "tests/fixtures/pr9_legacy/sidecars-provenance.json").read_bytes()
    )
    rows = {}
    for name, expected in SIDECAR_SHA256.items():
        row = provenance["files"][mode + "/" + name]
        original = REPO / "tests/fixtures/pr9_legacy" / row["path"]
        raw = original.read_bytes()
        if row["sha256"] != expected or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("original observer byte SHA differs")
        text = raw.decode()
        changes = {}
        for old, new in {
            "os.geteuid()==501": "os.geteuid()==gate['expected_uid']",
            "pathlib.Path('/e/'+gate['mode']+'-venv/lib/python3.11/site-packages')": (
                "pathlib.Path(__import__('sys').prefix)/'lib/python3.11/site-packages'"
            ),
            "'/e/'+LIVE_MODE+'-venv/lib/python3.11/site-packages/agent_guard/'": (
                "__import__('sys').prefix+'/lib/python3.11/site-packages/agent_guard/'"
            ),
        }.items():
            if old in text:
                text = text.replace(old, new)
                changes[old] = new
        target = destination / name
        target.write_text(text)
        target.chmod(0o444)
        rows[name] = {
            "original_sha256": expected,
            "executed_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "original_ast_sha256": hashlib.sha256(ast.dump(ast.parse(raw)).encode()).hexdigest(),
            "executed_ast_sha256": hashlib.sha256(ast.dump(ast.parse(text)).encode()).hexdigest(),
            "physical_replacements": changes,
        }
        if name.endswith(".pth") and target.read_bytes() != raw:
            raise ValueError("observer pth bytes changed")
    return rows


def _actual_observer_installation():
    import importlib
    import importlib.metadata
    import sysconfig

    if sys.version_info[:2] != (3, 11) or os.environ.get("PYTHONPATH"):
        raise ValueError("observer requires actual noneditable Python3.11")
    root = Path(sysconfig.get_path("purelib"))
    distribution = importlib.metadata.distribution("agent-guard")
    direct = json.loads(distribution.read_text("direct_url.json") or "{}")
    package = importlib.import_module("agent_guard")
    if (
        direct.get("dir_info", {}).get("editable")
        or Path(package.__file__) != root / "agent_guard/__init__.py"
    ):
        raise ValueError("observer installation is editable or shadowed")
    sources = {p.relative_to(REPO / "src"): p for p in (REPO / "src/agent_guard").rglob("*.py")}
    actual = {p.relative_to(root): p for p in (root / "agent_guard").rglob("*.py")}
    if not sources or sources.keys() != actual.keys():
        raise ValueError("observer installed module inventory differs")
    members = {}
    for relative, source in sources.items():
        installed = actual[relative]
        if (
            installed.is_symlink()
            or source.is_symlink()
            or installed.read_bytes() != source.read_bytes()
        ):
            raise ValueError("observer installed module SHA differs")
        module_name = str(relative.with_suffix("")).replace("/", ".").removesuffix(".__init__")
        spec = importlib.util.find_spec(module_name)
        if spec is None or Path(spec.origin) != installed:
            raise ValueError("observer installed import origin differs")
        members[str(relative)] = hashlib.sha256(installed.read_bytes()).hexdigest()
    return root, members


def _observer_controller():
    import re
    import socket
    import subprocess

    observed = json.loads(subprocess.check_output(["docker", "inspect", socket.gethostname()]))[0]
    labels = observed["Config"].get("Labels", {})
    if (
        not re.fullmatch(r"[0-9a-f]{64}", observed["Id"])
        or observed["Name"] != "/" + socket.gethostname()
        or observed["Config"]["User"] != str(os.getuid()) + ":" + str(os.getgid())
        or observed["State"]["Running"] is not True
        or labels.get("agent-guard.owner") != os.environ["PR9_TEST_CONTROLLER_OWNER"]
        or labels.get("agent-guard.run") != os.environ["PR9_TEST_CONTROLLER_RUN"]
        or observed["Image"] != os.environ["PR9_TEST_CONTROLLER_IMAGE"]
    ):
        raise ValueError("actual observer controller identity differs")
    return observed


def validate_observer_gate(gate, mode):
    """Fail in the parent, never rely on swallowed Python pth exceptions."""
    import re

    keys = {
        "version",
        "mode",
        "role",
        "py_fullID",
        "owner_uuid",
        "controller_owner",
        "image_full_id",
        "expected_uid",
        "expected_gid",
        "role_owner_token",
        "installed_root",
        "installed_modules_sha256",
    }
    if type(gate) is not dict or set(gate) != keys:
        raise ValueError("closed observer gate required")
    if type(gate["version"]) is not int or gate["version"] != 1:
        raise ValueError("observer version differs")
    if any(
        type(gate[k]) is not str
        for k in keys - {"version", "expected_uid", "expected_gid", "installed_modules_sha256"}
    ):
        raise ValueError("observer identity exact string types required")
    if any(type(gate[k]) is not int or gate[k] < 0 for k in ("expected_uid", "expected_gid")):
        raise ValueError("observer UID/GID exact integer required")
    if gate["mode"] != mode or mode not in ("source", "wheel") or gate["role"] != mode:
        raise ValueError("observer mode/role differs")
    if gate["expected_uid"] != os.getuid() or gate["expected_gid"] != os.getgid():
        raise ValueError("observer actual process UID/GID differs")
    if (
        str(uuid.UUID(gate["owner_uuid"])) != gate["owner_uuid"]
        or str(uuid.UUID(gate["role_owner_token"])) != gate["role_owner_token"]
    ):
        raise ValueError("observer canonical ownership UUID required")
    if not re.fullmatch(r"[0-9a-f]{64}", gate["py_fullID"]) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", gate["image_full_id"]
    ):
        raise ValueError("observer full controller/image ID required")
    if type(gate["installed_modules_sha256"]) is not dict or any(
        type(k) is not str or type(v) is not str or not re.fullmatch(r"[0-9a-f]{64}", v)
        for k, v in gate["installed_modules_sha256"].items()
    ):
        raise ValueError("observer module map exact string/SHA types required")
    actual = _observer_controller()
    if (
        gate["py_fullID"] != actual["Id"]
        or gate["image_full_id"] != actual["Image"]
        or gate["owner_uuid"] != os.environ["PR9_TEST_CONTROLLER_RUN"]
        or gate["controller_owner"] != os.environ["PR9_TEST_CONTROLLER_OWNER"]
    ):
        raise ValueError("observer recorded full identity differs")
    root, members = _actual_observer_installation()
    if (
        type(gate["installed_modules_sha256"]) is not dict
        or gate["installed_root"] != str(root)
        or gate["installed_modules_sha256"] != members
    ):
        raise ValueError("observer actual installed module SHA differs")
    return actual


def create_observer_session(mode):
    actual = _observer_controller()
    installed, members = _actual_observer_installation()
    gate = {
        "version": 1,
        "mode": mode,
        "role": mode,
        "py_fullID": actual["Id"],
        "owner_uuid": os.environ["PR9_TEST_CONTROLLER_RUN"],
        "controller_owner": os.environ["PR9_TEST_CONTROLLER_OWNER"],
        "image_full_id": actual["Image"],
        "expected_uid": os.getuid(),
        "expected_gid": os.getgid(),
        "role_owner_token": str(uuid.uuid4()),
        "installed_root": str(installed),
        "installed_modules_sha256": members,
    }
    validate_observer_gate(gate, mode)
    root = Path("/tmp") / (
        "a31-" + hashlib.sha256(gate["role_owner_token"].encode()).hexdigest()[:12]
    )
    root.mkdir(mode=0o700)
    for name, value in (
        ("gate.json", gate),
        ("owner.json", {k: gate[k] for k in ("owner_uuid", "role", "py_fullID")}),
    ):
        path = root / name
        path.write_text(json.dumps(value, indent=2))
        path.chmod(0o600)
    observed = root / "observed"
    observed.mkdir(mode=0o700)
    return (
        root,
        gate,
        {
            "AG31_MODE": mode,
            "AG31_GATE": str(root / "gate.json"),
            "AG31_SESSION_DIR": str(root),
            "AG31_OBSERVER_DIR": str(observed),
        },
    )


def verify_observer_output(root, gate, pid, start_ticks, argv_sha256):
    """Require the real exiting process receipt in addition to original live tests."""
    path = Path(root) / "observed" / (str(pid) + ".json")
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_uid != os.getuid()
        or path.stat().st_mode & 0o777 != 0o600
    ):
        raise ValueError("real observer receipt missing or unsafe")
    value = json.loads(path.read_bytes())
    if (
        value.get("valid") is not True
        or value.get("phase") != "atexit"
        or value.get("pid") != pid
        or value.get("uid") != gate["expected_uid"]
        or value.get("kernel_start_ticks") != start_ticks
        or value.get("argv_sha256") != argv_sha256
        or type(value.get("loaded")) is not list
    ):
        raise ValueError("actual observer process receipt differs")
    for row in value["loaded"]:
        relative = str(Path(row["file"]).relative_to(gate["installed_root"]))
        if row["sha256"] != gate["installed_modules_sha256"].get(relative):
            raise ValueError("actual observed loaded module SHA differs")
    return value


CURRENT_APPEND_MIGRATIONS = {
    "008_threshold_approval.sql": (
        "2349e7551e8884f46224804a3d587f305" + "f2ce5b565cc66927fb8b73aa826a9d1"
    ),
    "009_x402_payment.sql": "e9e6f0a5d7046c10f2f7c3abe1144838696b6c40a0aeb47150c60504965105a4",
}


def qualify_legacy_migration_test(text):
    """Retain the exact historical prefix and qualify both current appendices."""
    old = 'assert applied==[f"{i:03}" for i in range(int(base)+1,7)]'
    if text.count(old) != 1:
        raise ValueError("unknown historical six-migration assertion")
    for name, expected in CURRENT_APPEND_MIGRATIONS.items():
        if hashlib.sha256((REPO / "migrations" / name).read_bytes()).hexdigest() != expected:
            raise ValueError("current appended migration source SHA mismatch")
    original_sequence = '[f"{i:03}" for i in range(int(base)+1,7)]'
    registry_rows = [
        (name[:3], name, expected) for name, expected in CURRENT_APPEND_MIGRATIONS.items()
    ]
    new = (
        "assert applied[:6-int(base)]=="
        + original_sequence
        + ";assert applied=="
        + original_sequence
        + "+['008','009']"
        + ";assert all(__import__('hashlib').sha256(p.read_bytes()).hexdigest()==expected "
        + "for name,expected in "
        + repr(CURRENT_APPEND_MIGRATIONS)
        + ".items() "
        + "for p in (DEFAULT_MIGRATIONS_DIR/name,Path("
        + repr(str(REPO / "migrations"))
        + ")/name))"
        + ";assert [row[:3] for row in registry(scratch.dsn) "
        + "if row[0] in ('008','009')]=="
        + repr(registry_rows)
    )
    return text.replace(old, new), {
        "kind": "current appended migration compatibility qualification",
        "historical_whole_equality_replaced_by_exact_prefix": True,
        "expected_appended_versions": ["008", "009"],
        "source_and_installed_raw_sha256": CURRENT_APPEND_MIGRATIONS,
        "expected_registry_rows": registry_rows,
        "original_assertion": old,
        "executed_assertions": new,
    }


CURRENT_LEGACY_CALLS = {
    "inherited/historical-adapted/a1/test_upgrade_nonzero.py": [
        ["002", "003", "004", "005", "006"]
    ],
    "inherited/historical-original/a2/test_review.py": [["004", "005", "006"]],
    "inherited/historical-original/a2/test_r2_variants.py": [["004", "005", "006"]],
    "inherited/historical-original/a2/test_r3_independent.py": [["005", "006"]],
    "inherited/historical-original/a2/test_r4_boundaries.py": [["006"], ["005", "006"]],
}


def verify_current_migration_sql_files(source_root):
    """Check the two reviewed appendices in current source and actual installation."""
    from agent_guard.ledger.migrate import DEFAULT_MIGRATIONS_DIR

    for name, expected in CURRENT_APPEND_MIGRATIONS.items():
        for path in (Path(source_root) / name, DEFAULT_MIGRATIONS_DIR / name):
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError("current appended source/installed SQL differs")


def verify_current_migration_append(connection, source_root):
    """Bind both current appendices to fixed source, installed SQL and actual PG rows."""
    verify_current_migration_sql_files(source_root)
    rows = connection.execute(
        "SELECT version,filename,checksum FROM ag_schema_migrations "
        "WHERE version IN ('008','009') ORDER BY version"
    ).fetchall()
    expected = [(name[:3], name, digest) for name, digest in CURRENT_APPEND_MIGRATIONS.items()]
    if rows != expected:
        raise ValueError("current appended registry metadata differs")


def verify_registry_extension(before, after):
    """Preserve every historical row and require exactly006,008,009 added rows."""
    expected = [
        (
            "006",
            "006_event_seal.sql",
            "3abb279bc88b2fd7b2ff427a57fda407b77908182ec612334d500bea2f76760c",
        ),
        *[(name[:3], name, digest) for name, digest in CURRENT_APPEND_MIGRATIONS.items()],
    ]
    if after[: len(before)] != before or [row[:3] for row in after[len(before) :]] != expected:
        raise ValueError("historical full registry prefix or exact appendices differ")


def qualify_current_legacy_calls(text, relative):
    """Qualify only the closed selected call sites, preserving all other source text."""
    import ast

    expected_calls = CURRENT_LEGACY_CALLS[relative]
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    edits, observed, metadata = [], [], []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Assert)
            and isinstance(node.test, ast.Compare)
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.Eq)
            and isinstance(node.test.left, ast.Call)
            and isinstance(node.test.left.func, ast.Name)
            and node.test.left.func.id == "apply_migrations"
            and len(node.test.left.args) == 1
            and not node.test.left.keywords
            and isinstance(node.test.comparators[0], ast.List)
        ):
            continue
        old_versions = ast.literal_eval(node.test.comparators[0])
        if not old_versions:
            continue
        observed.append(old_versions)
        if not isinstance(node.test.left.args[0], ast.Name) or node.lineno != node.end_lineno:
            raise ValueError("unknown historical migration call shape")
        connection = node.test.left.args[0].id
        original = ast.get_source_segment(text, node)
        replacement = (
            "assert (_pr9_applied:=apply_migrations("
            + connection
            + "))[:"
            + str(len(old_versions))
            + "]=="
            + repr(old_versions)
            + ";assert _pr9_applied=="
            + repr(old_versions + ["008", "009"])
            + ";__import__('tools.pr9_deploy_inputs',fromlist=['verify_current_migration_append'])"
            + ".verify_current_migration_append("
            + connection
            + ","
            + repr(str(REPO / "migrations"))
            + ")"
        )
        edits.append((node.lineno - 1, node.col_offset, node.end_col_offset, replacement))
        metadata.append({"original": original, "executed": replacement})
    if sorted(observed) != sorted(expected_calls):
        raise ValueError("historical migration call inventory differs")
    for line, start, end, replacement in sorted(edits, reverse=True):
        lines[line] = lines[line][:start] + replacement + lines[line][end:]
    result = "".join(lines)
    if relative.endswith("test_r4_boundaries.py"):
        old = "after[1][:-1]==before[1]"
        if result.count(old) != 1:
            raise ValueError("historical registry extension inventory differs")
        new = (
            "after[1][:len(before[1])]==before[1] and "
            "(__import__('tools.pr9_deploy_inputs',fromlist=['verify_registry_extension'])"
            ".verify_registry_extension(before[1],after[1]) is None)"
        )
        result = result.replace(old, new)
        metadata.append({"original": old, "executed": new})
    return result, {
        "kind": "current appended migration compatibility qualification",
        "edits": metadata,
    }


def materialize_historical_six(destination):
    """Copy exactly the six immutable historical standalone SQL files."""
    from agent_guard.ledger.migrate import DEFAULT_MIGRATIONS_DIR

    historical = json.loads(
        (REPO / "tests/fixtures/pr9_legacy/historical-migrations.json").read_bytes()
    )["standalone"]
    selected = {
        name: digest
        for name, digest in historical.items()
        if "/" not in name and name[:3] in {f"{i:03}" for i in range(1, 7)}
    }
    if len(selected) != 6:
        raise ValueError("historical six SQL inventory differs")
    destination.mkdir(mode=0o700)
    for name, expected in selected.items():
        source, installed = REPO / "migrations" / name, DEFAULT_MIGRATIONS_DIR / name
        if any(
            p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != expected
            for p in (source, installed)
        ):
            raise ValueError("historical six source/installed raw SHA differs")
        (destination / name).write_bytes(source.read_bytes())
        (destination / name).chmod(0o600)
    return selected


CURRENT_PROBE_TABLE_FILES = {
    "inherited/probes/test_reviewer_variants.py",
    "inherited/probes/test_reviewer_precommit_payload.py",
    "inherited/probes/test_public_boundary.py",
}
CURRENT_ADDED_TABLES = frozenset(
    {"ag_threshold_approvals", "ag_payment_intents", "ag_payment_budgets", "ag_payment_states"}
)
HISTORICAL_DOWNSTREAM_TABLES = frozenset({"ds_operations", "ds_orders", "ds_notifications"})
CURRENT_ADDED_DOWNSTREAM_TABLES = frozenset({"ds_cosm2_bindings"})
CURRENT_DOWNSTREAM_SOURCE_SHA256 = (
    "4a69b8e1cc404f26695101233dd0e3baeea43a6b1ca693993daedc5975b5c2af"
)


def verify_current_downstream_source(source_root):
    """Bind the new DS table to current source and the module actually imported."""
    import agent_guard.tools.downstream as installed

    source = Path(source_root) / "src/agent_guard/tools/downstream.py"
    actual = Path(installed.__file__)
    expected_installed = (
        Path(sys.prefix) / "lib/python3.11/site-packages/agent_guard/tools/downstream.py"
    )
    if actual != expected_installed or actual == source:
        raise ValueError("actual downstream module is not the current installed member")
    for path in (source, actual):
        if (
            path.is_symlink()
            or hashlib.sha256(path.read_bytes()).hexdigest() != CURRENT_DOWNSTREAM_SOURCE_SHA256
        ):
            raise ValueError("current downstream source/actual installed SHA differs")


def qualify_current_table_inventory(text, relative):
    """Keep the original31+007six and require all four fixed appended tables."""
    import ast

    if relative not in CURRENT_PROBE_TABLE_FILES:
        raise ValueError("unknown complete table-inventory qualification")
    old = "A31_ORIGINAL31 | A31_CURRENT007_SIX"
    if text.count(old) != 1:
        raise ValueError("historical complete table assertion inventory differs")
    new = old + " | PR9_CURRENT008009_FOUR"
    text = text.replace(old, new)
    tree = ast.parse(text)
    line = max(n.end_lineno for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)))
    lines = text.splitlines(keepends=True)
    declaration = (
        "PR9_CURRENT008009_FOUR = frozenset(" + repr(sorted(CURRENT_ADDED_TABLES)) + ")\n"
        "PR9_HISTORICAL_DS3 = frozenset(" + repr(sorted(HISTORICAL_DOWNSTREAM_TABLES)) + ")\n"
        "PR9_CURRENT_DS_ONE = frozenset(" + repr(sorted(CURRENT_ADDED_DOWNSTREAM_TABLES)) + ")\n"
        "__import__('tools.pr9_deploy_inputs',fromlist=['verify_current_migration_sql_files'])"
        ".verify_current_migration_sql_files(" + repr(str(REPO / "migrations")) + ")\n"
        "__import__('tools.pr9_deploy_inputs',fromlist=['verify_current_downstream_source'])"
        ".verify_current_downstream_source(" + repr(str(REPO)) + ")\n"
    )
    lines.insert(line, declaration)
    text = "".join(lines)
    edits = [{"original": old, "executed": new}, {"inserted": declaration}]
    if relative.endswith("test_reviewer_variants.py"):
        old_ds = "len(before['downstream'])==3"
        new_ds = "set(before['downstream'])==PR9_HISTORICAL_DS3 | PR9_CURRENT_DS_ONE"
    elif relative.endswith("test_reviewer_precommit_payload.py"):
        old_ds = 'len(before["downstream"]) == 3'
        new_ds = 'set(before["downstream"]) == PR9_HISTORICAL_DS3 | PR9_CURRENT_DS_ONE'
    else:
        old_ds = "assert set(before['gateway']) == set(after['gateway']) == " + new
        new_ds = (
            old_ds + " and set(before['downstream']) == set(after['downstream']) == "
            "PR9_HISTORICAL_DS3 | PR9_CURRENT_DS_ONE"
        )
    if text.count(old_ds) != 1:
        raise ValueError("historical downstream inventory assertion differs")
    text = text.replace(old_ds, new_ds)
    edits.append({"original": old_ds, "executed": new_ds})
    if relative.endswith("test_reviewer_variants.py"):
        old_label = "'current_gateway_tables':37"
        new_label = "'historical_gateway_tables':37,'current_gateway_tables':41"
    elif relative.endswith("test_reviewer_precommit_payload.py"):
        old_label = '"current37_gateway_and3ds_strict_publication_oracle": True'
        new_label = (
            '"historical37_gateway_inventory_preserved": True, "historical_gateway_tables": 37, '
            '"historical_downstream_tables": 3, "current_downstream_tables": 4, '
            '"current41_gateway_and4ds_strict_publication_oracle": True, '
            '"current_gateway_tables": 41'
        )
    else:
        old_label = "    return expected_before, expected_after"
        new_label = (
            "    for _pr9_domain,_pr9_tables in (('gateway',PR9_CURRENT008009_FOUR),"
            "('downstream',PR9_CURRENT_DS_ONE)):\n"
            "        for _pr9_table in _pr9_tables:\n"
            "            _pr9_mutant = deepcopy(expected_after)\n"
            "            _pr9_mutant[_pr9_domain][_pr9_table] = "
            "list(_pr9_mutant[_pr9_domain][_pr9_table]) + [('pr9-snapshot-negative-control',)]\n"
            "            with pytest.raises(AssertionError):\n"
            "                _original_result_read_only(expected_before, _pr9_mutant, "
            "observed_response=response, **kwargs)\n" + old_label
        )
    if text.count(old_label) != 1:
        raise ValueError("historical table observation/control inventory differs")
    text = text.replace(old_label, new_label)
    edits.append({"original": old_label, "executed": new_label})
    if relative.endswith("test_reviewer_variants.py"):
        old_observation = "'full_ds_tables':3"
        new_observation = "'historical_ds_tables':3,'full_ds_tables':4"
        if text.count(old_observation) != 1:
            raise ValueError("historical DS observation inventory differs")
        text = text.replace(old_observation, new_observation)
        edits.append({"original": old_observation, "executed": new_observation})
    return text, {
        "kind": "complete current41-table compatibility qualification",
        "preserved_historical_gateway_tables": 37,
        "current_gateway_tables": 41,
        "historical_downstream_tables": 3,
        "current_downstream_tables": 4,
        "fixed_added_downstream_tables": sorted(CURRENT_ADDED_DOWNSTREAM_TABLES),
        "current_downstream_source_and_actual_installed_sha256": CURRENT_DOWNSTREAM_SOURCE_SHA256,
        "fixed_added_tables": sorted(CURRENT_ADDED_TABLES),
        "current_source_and_installed_raw_sha256": CURRENT_APPEND_MIGRATIONS,
        "edits": edits,
    }


def materialize_legacy(mode, destination):
    """Restore publicly curated original bytes with explicit physical-path mapping.

    No original assertion is removed. Compatibility replacements are recorded
    beside both input and executed SHA, including the current migration count.
    """
    import ast

    fixtures = REPO / "tests/fixtures/pr9_legacy"
    manifest = json.loads((fixtures / "provenance.json").read_bytes())
    destination = Path(destination)
    destination.mkdir(mode=0o700, parents=True)
    evidence_logs = destination / "evidence-logs"
    evidence_logs.mkdir(mode=0o700)
    standalone = destination / "legacy-standalone"
    standalone_binding = (
        materialize_historical_six(standalone)
        if mode + "/inherited/historical-original/a2/test_upgrade.py" in manifest["files"]
        else {}
    )
    changes = {}
    for key, row in manifest["files"].items():
        if not key.startswith(mode + "/"):
            continue
        raw = (fixtures / row["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("legacy original SHA mismatch: " + key)
        text = raw.decode()
        replacements = {
            "/e/" + mode + "-tests/inherited": str(destination / "inherited"),
            "/e/" + mode + "-tests": str(REPO),
            "/e/" + mode + "-venv": sys.prefix,
            "/e/sourcecopy": str(REPO),
            "/e/snapshot-r6": str(REPO),
            "/e/native/busybox": "/bin/busybox",
            "/evidence/logs": str(evidence_logs),
            "/evidence/probe-observations.jsonl": str(evidence_logs / "probe-observations.jsonl"),
            "/e/s2-legacy-standalone": str(standalone),
            "pathlib.Path('/e/'+mode+'-venv/lib/python3.11/site-packages')": (
                "pathlib.Path(__import__('sys').prefix)/'lib/python3.11/site-packages'"
            ),
            "pathlib.Path('/e/'+mode+'-venv/share/agent-guard/migrations')": (
                "(pathlib.Path(__import__('sys').prefix)/'share/agent-guard/migrations')"
            ),
            "f'/e/{mode}-venv/lib/python3.11/site-packages/agent_guard/'": (
                "str(pathlib.Path(__import__('sys').prefix)/"
                "'lib/python3.11/site-packages/agent_guard')+'/'"
            ),
        }
        applied = {}
        qualification = None
        table_qualification = None
        for old, new in replacements.items():
            if old in text:
                applied[old] = new
                text = text.replace(old, new)
        if key.endswith("/runtime_provenance.py"):
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if "label=os.environ['A23_RUN_LABEL']; mode=" in line:
                    replacement = (
                        " label=os.environ['A23_RUN_LABEL']; mode=os.environ['PR9_INSTALL_MODE'];"
                        "prefix=sys.prefix+'/lib/python3.11/site-packages/'"
                    )
                    applied[line] = replacement
                    lines[i] = replacement
            text = "\n".join(lines) + "\n"
        # Runtime provenance already compares every loaded installed byte with
        # sourcecopy. The observer predates gateway migrations 016-018; retain
        # its exact-current-registry comparison while expecting current length.
        if key.endswith("/environment_observer.py"):
            from agent_guard.ledger.lineage import load_manifest

            old = "len(actual)==15"
            new = "len(actual)==" + str(len(load_manifest().migrations))
            if old not in text:
                raise ValueError("unknown historical environment observer")
            text = text.replace(old, new)
            applied[old] = new
        if key.endswith("/historical-adapted/b/test_r2_migrations.py"):
            text, qualification = qualify_legacy_migration_test(text)
        relative = key.split("/", 1)[1]
        if relative in CURRENT_LEGACY_CALLS:
            text, qualification = qualify_current_legacy_calls(text, relative)
        if relative in CURRENT_PROBE_TABLE_FILES:
            text, table_qualification = qualify_current_table_inventory(text, relative)
        target = destination / key.split("/", 1)[1]
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_text(text)
        ast.parse(text)
        changes[key] = {
            "original_sha256": row["sha256"],
            "executed_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "physical_and_current_registry_replacements": applied,
            "current_append_migration_qualification": qualification,
            "complete_current_table_inventory_qualification": table_qualification,
            "original_ast_sha256": hashlib.sha256(ast.dump(ast.parse(raw)).encode()).hexdigest(),
            "executed_ast_sha256": hashlib.sha256(ast.dump(ast.parse(text)).encode()).hexdigest(),
        }
    (destination / "inherited/sourcecopy").symlink_to(REPO, target_is_directory=True)
    plugin = destination / "inherited/pr9_legacy_db_router.py"
    plugin.write_text(
        "import pytest\n"
        "from tools.pr9_deploy_inputs import legacy_database_protocol\n"
        "pytest_runtest_protocol = pytest.hookimpl(hookwrapper=True, tryfirst=True)("
        "legacy_database_protocol)\n"
    )
    plugin.chmod(0o600)
    (destination / "adaptations.json").write_text(json.dumps(changes, indent=2))
    (destination / "historical-six-sql-binding.json").write_text(
        json.dumps(
            {"purpose": "original standalone six-SQL wrapper only", "files": standalone_binding}
        )
    )
    return manifest


def _process_snapshot(pid, proc_root=Path("/proc")):
    """Read one independently checked live kernel identity around its argv."""
    directory = proc_root / str(pid)

    def identity():
        stat = (directory / "stat").read_text()
        tail = stat[stat.rfind(")") + 2 :].split()
        status = (directory / "status").read_text()
        uid = next(line for line in status.splitlines() if line.startswith("Uid:")).split()[1:]
        value = {
            "pid": int(stat.split(" ", 1)[0]),
            "start_ticks": int(tail[19]),
            "uids": [int(item) for item in uid],
        }
        if (
            value["pid"] != pid
            or value["start_ticks"] <= 0
            or len(value["uids"]) != 4
            or tail[0] not in {"R", "S", "D", "T", "t", "W", "K", "P", "I"}
        ):
            raise ValueError("observer process identity malformed or dead")
        return value

    before = identity()
    raw = (directory / "cmdline").read_bytes()
    if identity() != before:
        raise ValueError("observer process identity changed during capture")
    return before, raw


def wait_declared_process(process, command, expected_uid, receipt_path, *, timeout=5.0):
    """Wait for exact declared exec bytes, never accepting an emulator prefix."""
    if (
        type(command) not in (list, tuple)
        or not command
        or any(not isinstance(item, str) or "\0" in item for item in command)
        or type(expected_uid) is not int
        or expected_uid < 0
        or type(timeout) not in (int, float)
        or not 0 < timeout <= 5.0
    ):
        raise ValueError("invalid declared observer command or startup budget")
    declared = b"\0".join(os.fsencode(item) for item in command) + b"\0"
    expected_sha = hashlib.sha256(declared).hexdigest()
    deadline = time.monotonic() + timeout
    first_identity, samples, total = None, [], 0
    outcome = "rejected"
    try:
        while True:
            if process.poll() is not None:
                raise ValueError("observer process exited before declared argv capture")
            identity, raw = _process_snapshot(process.pid)
            if identity["pid"] != process.pid:
                raise ValueError("observer process PID differs during startup")
            if identity["uids"] != [expected_uid] * 4:
                raise ValueError("observer process UID differs during startup")
            if first_identity is None:
                first_identity = identity
            if identity != first_identity:
                raise ValueError("observer process identity changed during startup")
            argv0 = raw.split(b"\0", 1)[0]
            safe_argv0 = (
                os.fsdecode(argv0)
                if b"\0" in raw and argv0.startswith(b"/") and len(argv0) <= 256
                else "<unavailable-or-invalid-argv0>"
            )
            sample = {
                **identity,
                "argv_sha256": hashlib.sha256(raw).hexdigest(),
                "argv_length": len(raw),
                "argv0": safe_argv0,
                "matches_declared": raw == declared,
            }
            total += 1
            if len(samples) < 128:
                samples.append(sample)
            else:
                samples[-1] = sample
            if process.poll() is not None:
                raise ValueError("observer process exited during declared argv capture")
            if raw == declared:
                if time.monotonic() > deadline:
                    raise ValueError("observer declared argv startup deadline exhausted")
                outcome = "matched_declared"
                return identity["start_ticks"], expected_sha
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("observer declared argv startup deadline exhausted")
            time.sleep(min(0.001, remaining))
    except (OSError, StopIteration, IndexError) as exc:
        raise ValueError("observer process disappeared or kernel identity malformed") from exc
    finally:
        receipt = {
            "outcome": outcome,
            "pid": process.pid,
            "expected_uid": expected_uid,
            "declared_argv_sha256": expected_sha,
            "declared_argv_length": len(declared),
            "sample_count": total,
            "samples": samples,
        }
        fd = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.fchmod(fd, 0o600)
        except BaseException:
            os.close(fd)
            raise
        with os.fdopen(fd, "w") as stream:
            json.dump(receipt, stream, indent=2)


def execute_observed_command(command, root, env, mode):
    """Run the real command and require independently bound observer output."""
    import shutil
    import subprocess

    root = Path(root)
    session, gate, observer_env = create_observer_session(mode)
    expected_sidecars = prepare_legacy_sidecars(session / "expected-sidecars", mode)
    installed = Path(gate["installed_root"])
    for name, row in expected_sidecars.items():
        if hashlib.sha256((installed / name).read_bytes()).hexdigest() != row["executed_sha256"]:
            raise ValueError("actual installed observer bytes differ")
    process_env = dict(env, **observer_env)
    with (root / "native.log").open("wb") as log:
        process = subprocess.Popen(
            command, cwd=REPO, env=process_env, stdout=log, stderr=subprocess.STDOUT
        )
        try:
            start_ticks, argv_sha = wait_declared_process(
                process, command, gate["expected_uid"], root / "parent-startup.json"
            )
            native_exit = process.wait(timeout=14400)
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            shutil.copytree(session, root / "observer-evidence")
    (root / "observed-process.json").write_text(
        json.dumps(
            {
                "pid": process.pid,
                "kernel_start_ticks": start_ticks,
                "argv_sha256": argv_sha,
                "native_exit": native_exit,
            }
        )
    )
    receipt = None
    if native_exit == 0:
        receipt = verify_observer_output(session, gate, process.pid, start_ticks, argv_sha)
    result = subprocess.CompletedProcess(command, native_exit)
    result.observer_root, result.observer_gate = session, gate
    result.observer_receipt = receipt
    return result


def verify_live_records(root, gate, required_pids):
    """Inspect real child records; missing records are parent-visible failures."""
    validate_observer_gate(gate, gate["mode"])
    root = Path(root).absolute()
    expected = Path("/tmp") / (
        "a31-" + hashlib.sha256(gate["role_owner_token"].encode()).hexdigest()[:12]
    )
    if root != expected or any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("observer ownership root differs")
    owner = json.loads((root / "owner.json").read_bytes())
    if owner != {k: gate[k] for k in ("owner_uuid", "role", "py_fullID")}:
        raise ValueError("observer ownership marker differs")
    if not required_pids or any(type(pid) is not int or pid <= 0 for pid in required_pids):
        raise ValueError("actual child PID list required")
    for pid in required_pids:
        path = root / "observed/live-provenance" / (gate["mode"] + "-" + str(pid) + ".json")
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_uid != os.getuid()
            or path.stat().st_mode & 0o777 != 0o600
        ):
            raise ValueError("real live child observer receipt missing or unsafe")
        value = json.loads(path.read_bytes())
        if (
            any(value.get(k) != gate[k] for k in ("py_fullID", "owner_uuid", "role"))
            or type(value.get("uid")) is not int
            or value["uid"] != gate["expected_uid"]
            or type(value.get("pid")) is not int
            or value["pid"] != pid
        ):
            raise ValueError("real live child identity differs")
        main_spec = value.get("main_spec")
        expected_module = {
            "agent_guard.execution.worker": "agent_guard.execution.service",
            "agent_guard.gateway.__main__": "agent_guard.gateway.http_app",
        }.get(main_spec)
        modules = value.get("modules")
        if expected_module is None or type(modules) is not dict or expected_module not in modules:
            raise ValueError("real live child main module differs")
        Path(value["main_file"]).relative_to(Path(gate["installed_root"]) / "agent_guard")
        if type(value.get("kernel_start_ticks")) is not int or value["kernel_start_ticks"] <= 0:
            raise ValueError("real kernel child start ticks required")
        for filename in modules.values():
            if filename is not None:
                path = Path(filename)
                relative = str(path.relative_to(gate["installed_root"]))
                if hashlib.sha256(path.read_bytes()).hexdigest() != gate[
                    "installed_modules_sha256"
                ].get(relative):
                    raise ValueError("real live child loaded module SHA differs")
    return len(required_pids)


def run_legacy_child_probe(mode, output):
    """Additional original node probe and real negative controls, not a20-group index."""
    import copy
    import shutil
    import subprocess
    import xml.etree.ElementTree as ET

    output = Path(output)
    output.mkdir(mode=0o700, parents=True)
    pure_tools = []
    for number in range(2):
        tool_root = output / ("pure-tool-" + str(number))
        tool_root.mkdir(mode=0o700)
        tool_argv = [sys.executable, "-m", "ruff", "--version"]
        wrapper_argv = [
            sys.executable,
            "-c",
            "import subprocess;raise SystemExit(subprocess.run("
            + repr(tool_argv)
            + ").returncode)",
        ]
        result = execute_observed_command(
            wrapper_argv,
            tool_root,
            dict(os.environ, PYTHONPATH=""),
            mode,
        )
        if result.returncode or result.observer_receipt["loaded"] != []:
            raise ValueError("actual pure tool empty-loaded observer control failed")
        pure_tools.append(
            {
                **{
                    k: result.observer_receipt[k]
                    for k in ("pid", "uid", "kernel_start_ticks", "argv_sha256", "phase", "loaded")
                },
                "tool_argv": tool_argv,
                "propagated_native_exit": result.returncode,
            }
        )
    (output / "pure-tool-controls.json").write_text(json.dumps(pure_tools, indent=2))
    legacy = output / "legacy"
    materialize_legacy(mode, legacy)
    label = mode + "-original-child-probe"
    (legacy / "inherited/runtime" / label).mkdir(mode=0o700, parents=True)
    target = legacy / (
        "inherited/historical-enhanced-" + mode + "/a22-probes/test_child_import_sources.py"
    )
    node = str(target) + "::test_real_tls_children_have_live_import_sources"
    argv = [
        "-m",
        "pytest",
        "-p",
        "runtime_provenance",
        node,
        "--rootdir=" + str(target.parent.parent),
        "--junitxml=" + str(output / "results.xml"),
        "-o",
        "cache_dir=" + str(output / "cache"),
        "-q",
    ]
    launcher = (
        "import sys,runpy;sys.path.insert(0,"
        + repr(str(REPO))
        + ");sys.path.insert(0,"
        + repr(str(legacy / "inherited"))
        + ");sys.argv=['pytest',*"
        + repr(argv[2:])
        + "];runpy.run_module('pytest',run_name='__main__')"
    )
    env = dict(os.environ, A23_RUN_LABEL=label, PR9_INSTALL_MODE=mode, PYTHONPATH="")
    result = execute_observed_command([sys.executable, "-c", launcher], output, env, mode)
    if result.returncode:
        raise RuntimeError("original real child-kill probe failed")
    tree = ET.parse(output / "results.xml")
    cases = list(tree.iter("testcase"))
    if (
        len(cases) != 1
        or cases[0].attrib["name"] != "test_real_tls_children_have_live_import_sources"
        or any(list(tree.iter(t)) for t in ("failure", "error", "skipped"))
    ):
        raise ValueError("original child-kill probe incomplete")
    session, gate = result.observer_root, result.observer_gate
    pids = []
    for path in (session / "observed/live-provenance").glob(mode + "-*.json"):
        value = json.loads(path.read_bytes())
        if value.get("main_spec") in (
            "agent_guard.execution.worker",
            "agent_guard.gateway.__main__",
        ):
            pids.append(value["pid"])
    if len(set(pids)) < 7:
        raise ValueError("actual original seven live child records required")
    verify_live_records(session, gate, pids)
    outcomes = []
    for case in ("wrong_uid", "wrong_module_sha", "wrong_full_id", "missing_live"):
        changed = copy.deepcopy(gate)
        if case == "wrong_uid":
            changed["expected_uid"] += 1
        elif case == "wrong_module_sha":
            changed["installed_modules_sha256"][next(iter(changed["installed_modules_sha256"]))] = (
                "0" * 64
            )
        elif case == "wrong_full_id":
            changed["py_fullID"] = "f" * 64
        path = output / (case + "-gate.json")
        path.write_text(json.dumps(changed))
        path.chmod(0o600)
        prefix = (
            "import sys,json;sys.path.insert(0,"
            + repr(str(REPO))
            + ");from pathlib import Path;"
            + "from tools.pr9_deploy_inputs import validate_observer_gate,verify_live_records;"
            + "gate=json.loads(Path("
            + repr(str(path))
            + ").read_bytes());"
        )
        if case == "missing_live":
            victim = session / "observed/live-provenance" / (mode + "-" + str(pids[0]) + ".json")
            retained = victim.with_suffix(".removed-for-negative")
            victim.rename(retained)
            code = (
                prefix + "verify_live_records(" + repr(str(session)) + ",gate," + repr(pids) + ")"
            )
        else:
            code = prefix + "validate_observer_gate(gate," + repr(mode) + ")"
        negative_env = {
            k: v
            for k, v in env.items()
            if k not in ("AG31_SESSION_DIR", "AG31_GATE", "AG31_OBSERVER_DIR", "AG31_MODE")
        }
        completed = subprocess.run(
            [sys.executable, "-c", code],
            env=negative_env,
            cwd=REPO,
            capture_output=True,
            timeout=180,
        )
        (output / (case + ".stdout")).write_bytes(completed.stdout)
        (output / (case + ".stderr")).write_bytes(completed.stderr)
        if case == "missing_live":
            retained.rename(victim)
        outcomes.append({"case": case, "native_exit": completed.returncode})
        if completed.returncode == 0:
            raise ValueError("observer negative control failed to reject: " + case)
    shutil.copytree(session, output / "observer-after-negative-controls")
    (output / "negative-controls.json").write_text(json.dumps(outcomes, indent=2))
    return {"mode": mode, "actual_live_child_records": len(pids), "negative_controls": outcomes}


LEGACY_DATABASE_FILES = {
    "a1-original-controls": {
        "inherited/historical-original/a1/test_missing_invariants.py": "ag_review_probe",
        "inherited/historical-original/a1/test_root_rebuild.py": "ag_review_f2",
    },
    "a1-upgrade-equivalent": {
        "inherited/historical-adapted/a1/test_upgrade_nonzero.py": "ag_review_upgrade_adapted",
    },
    "b-equivalent": {
        "inherited/historical-adapted/b/legacy/test_history1.py": "history_b_adapted",
        "inherited/historical-adapted/b/legacy/test_history4.py": "history_b_adapted",
    },
}


def validate_legacy_pg_gate(gate):
    """Closed, nonsecret parent binding to exactly one recorded owned authority PG."""
    import re

    fields = {
        "version",
        "owner_id",
        "run_id",
        "pg_full_id",
        "pg_image_full_id",
        "network_full_ids",
        "host",
        "port",
        "ca_sha256",
    }
    if type(gate) is not dict or set(gate) != fields:
        raise ValueError("closed legacy PG gate required")
    if type(gate["version"]) is not int or gate["version"] != 1:
        raise ValueError("legacy PG gate version differs")
    if any(type(gate[k]) is not str for k in fields - {"version", "port", "network_full_ids"}):
        raise ValueError("legacy PG exact string types required")
    if (
        type(gate["port"]) is not int
        or gate["port"] != 5432
        or gate["host"] != "pg-authority.agent-guard.test"
    ):
        raise ValueError("legacy PG host/port differs")
    run = str(uuid.UUID(gate["run_id"]))
    if run != gate["run_id"] or gate["owner_id"] != "pr9-deploy-" + run:
        raise ValueError("legacy PG owner/run differs")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", gate["pg_full_id"])
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", gate["pg_image_full_id"])
        or not re.fullmatch(r"[0-9a-f]{64}", gate["ca_sha256"])
    ):
        raise ValueError("legacy PG fullID/SHA differs")
    networks = gate["network_full_ids"]
    if (
        type(networks) is not list
        or not networks
        or any(type(v) is not str or not re.fullmatch(r"[0-9a-f]{64}", v) for v in networks)
        or len(set(networks)) != len(networks)
    ):
        raise ValueError("legacy PG network fullIDs differ")
    return gate


def _legacy_docker(*arguments):
    import subprocess

    return subprocess.run(
        ["docker", *arguments], capture_output=True, check=True, timeout=30
    ).stdout


def verify_legacy_pg(gate, dsn):
    """Match exact Docker identity and actual TLS PG system identity before DDL."""
    import psycopg
    from psycopg.conninfo import conninfo_to_dict

    validate_legacy_pg_gate(gate)
    params = conninfo_to_dict(dsn)
    ca = Path("/test-inputs/ca.pem")
    if (
        params.get("host") != gate["host"]
        or params.get("port", "5432") != "5432"
        or params.get("sslmode") != "verify-full"
        or params.get("sslrootcert") != str(ca)
        or params.get("dbname") != "ag_controller_test"
        or params.get("user") != "postgres"
        or params.get("options")
        or ca.is_symlink()
        or ca.stat().st_mode & 0o777 != 0o600
        or ca.stat().st_uid != os.getuid()
        or hashlib.sha256(ca.read_bytes()).hexdigest() != gate["ca_sha256"]
    ):
        raise ValueError("legacy PG TLS/admin DSN binding differs")
    actual = json.loads(_legacy_docker("inspect", gate["pg_full_id"]))[0]
    labels = actual["Config"].get("Labels", {})
    networks = actual["NetworkSettings"]["Networks"]
    if (
        actual["Id"] != gate["pg_full_id"]
        or actual["Image"] != gate["pg_image_full_id"]
        or actual["State"]["Running"] is not True
        or labels.get("agent-guard.owner") != gate["owner_id"]
        or labels.get("agent-guard.run") != gate["run_id"]
        or labels.get("com.docker.compose.service") != "pg-authority"
        or sorted(row["NetworkID"] for row in networks.values()) != sorted(gate["network_full_ids"])
    ):
        raise ValueError("actual legacy PG fullID/owner/run differs")
    for identifier in gate["network_full_ids"]:
        network = json.loads(_legacy_docker("network", "inspect", identifier))[0]
        if (
            network["Id"] != identifier
            or network["Labels"].get("agent-guard.owner") != gate["owner_id"]
            or network["Labels"].get("agent-guard.run") != gate["run_id"]
        ):
            raise ValueError("actual legacy PG network owner differs")
    local_id = (
        _legacy_docker(
            "exec",
            "--user",
            "postgres",
            gate["pg_full_id"],
            "psql",
            "-X",
            "-A",
            "-t",
            "-d",
            "postgres",
            "-c",
            "SELECT system_identifier FROM pg_control_system()",
        )
        .decode()
        .strip()
    )
    if not local_id.isdecimal():
        raise ValueError("actual legacy PG system identifier missing")
    with psycopg.connect(dsn, connect_timeout=5) as connection:
        row = connection.execute(
            "SELECT current_database(),current_user,host(inet_server_addr()),"
            "current_setting('server_version_num')::int,"
            "(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()),"
            "(SELECT system_identifier::text FROM pg_control_system())"
        ).fetchone()
    if (
        row[0:2] != ("ag_controller_test", "postgres")
        or row[2] not in {n["IPAddress"] for n in networks.values()}
        or not 160000 <= row[3] < 170000
        or row[4] is not True
        or row[5] != local_id
    ):
        raise ValueError("TLS connection is not the recorded owned PostgreSQL16")
    return local_id


def _legacy_private_json(path, value):
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@contextlib.contextmanager
def legacy_database_routes(suffix, legacy, output, default_dsn):
    """Create only required real fixed identities in the exact owned PG, then reap."""
    if suffix not in LEGACY_DATABASE_FILES:
        yield {}
        return
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    gate = validate_legacy_pg_gate(json.loads(os.environ["PR9_LEGACY_PG_GATE"]))
    system_id = verify_legacy_pg(gate, default_dsn)
    files = LEGACY_DATABASE_FILES[suffix]
    receipt = output / "legacy-database-routes.private.json"
    created, routes = [], {}
    value = {
        "version": 1,
        "group": suffix,
        "pg_gate": gate,
        "system_identifier": system_id,
        "legacy_root": str(legacy.absolute()),
        "default_dsn": default_dsn,
        "created": created,
        "routes": routes,
        "dropped": [],
    }
    _legacy_private_json(receipt, value)
    try:
        for name in sorted(set(files.values())):
            if verify_legacy_pg(gate, default_dsn) != system_id:
                raise ValueError("legacy PG system identifier changed")
            with psycopg.connect(default_dsn, autocommit=True, connect_timeout=5) as connection:
                if connection.execute(
                    "SELECT 1 FROM pg_database WHERE datname=%s", (name,)
                ).fetchone():
                    raise ValueError("legacy dedicated database preexists; refusing reuse")
                connection.execute(sql.SQL("CREATE DATABASE {} ").format(sql.Identifier(name)))
            created.append(name)
            _legacy_private_json(receipt, value)
        for relative, name in files.items():
            path = legacy / relative
            if path.is_symlink() or not path.is_file():
                raise ValueError("legacy routed file missing or symlinked")
            routes[relative] = {
                "database": name,
                "dsn": make_conninfo(default_dsn, dbname=name),
                "executed_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        _legacy_private_json(receipt, value)
        yield {"PR9_LEGACY_DATABASE_ROUTES": str(receipt)}
    finally:
        for name in reversed(created):
            if verify_legacy_pg(gate, default_dsn) != system_id:
                raise ValueError("legacy cleanup PG identity changed")
            with psycopg.connect(default_dsn, autocommit=True, connect_timeout=5) as connection:
                connection.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
                )
            value["dropped"].append(name)
            _legacy_private_json(receipt, value)


_VALIDATED_LEGACY_ROUTES = {}


def legacy_database_protocol(item, nextitem):
    """Set real selected-file identity before any session/function fixture resolves."""
    path = Path(os.environ["PR9_LEGACY_DATABASE_ROUTES"]).absolute()
    if (
        any(p.is_symlink() for p in (path, *path.parents))
        or not path.is_file()
        or path.stat().st_uid != os.getuid()
        or path.stat().st_mode & 0o777 != 0o600
        or path.parent.stat().st_mode & 0o777 != 0o700
    ):
        raise ValueError("private legacy routing receipt required")
    value = json.loads(path.read_bytes())
    if (
        type(value) is not dict
        or set(value)
        != {
            "version",
            "group",
            "pg_gate",
            "system_identifier",
            "legacy_root",
            "default_dsn",
            "created",
            "routes",
            "dropped",
        }
        or type(value["version"]) is not int
        or value["version"] != 1
    ):
        raise ValueError("closed legacy routing receipt required")
    validate_legacy_pg_gate(value["pg_gate"])
    if any(type(value[key]) is not str for key in ("group", "legacy_root", "default_dsn")):
        raise ValueError("legacy route exact string fields required")
    expected_files = LEGACY_DATABASE_FILES.get(value["group"])
    if (
        expected_files is None
        or type(value["routes"]) is not dict
        or set(value["routes"]) != set(expected_files)
        or value["created"] != sorted(set(expected_files.values()))
        or value["dropped"] != []
        or type(value["system_identifier"]) is not str
        or not value["system_identifier"].isdecimal()
    ):
        raise ValueError("legacy routing inventory differs")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if str(path) in _VALIDATED_LEGACY_ROUTES:
        if _VALIDATED_LEGACY_ROUTES[str(path)] != digest:
            raise ValueError("legacy routing receipt changed during execution")
    else:
        if verify_legacy_pg(value["pg_gate"], value["default_dsn"]) != value["system_identifier"]:
            raise ValueError("legacy routing PG identity differs")
        _VALIDATED_LEGACY_ROUTES[str(path)] = digest
    root = Path(value["legacy_root"])
    if (
        not root.is_absolute()
        or any(p.is_symlink() for p in (root, *root.parents))
        or root.stat().st_uid != os.getuid()
        or root.stat().st_mode & 0o777 != 0o700
    ):
        raise ValueError("private exact legacy root required")
    candidate = Path(item.path).absolute()
    try:
        relative = str(candidate.relative_to(root))
    except ValueError:
        relative = ""
    row = value["routes"].get(relative)
    previous = os.environ.get("AGENT_GUARD_TEST_DATABASE_URL")
    if row is not None:
        allowed = {p: name for files in LEGACY_DATABASE_FILES.values() for p, name in files.items()}
        from psycopg.conninfo import conninfo_to_dict

        expected_dsn = conninfo_to_dict(value["default_dsn"])
        expected_dsn["dbname"] = row.get("database") if type(row) is dict else None
        if (
            type(row) is not dict
            or set(row) != {"database", "dsn", "executed_sha256"}
            or allowed.get(relative) != row["database"]
            or row["database"] not in value["created"]
            or row["database"] in value["dropped"]
            or candidate.is_symlink()
            or hashlib.sha256(candidate.read_bytes()).hexdigest() != row["executed_sha256"]
            or conninfo_to_dict(row["dsn"]) != expected_dsn
            or "namespace" in item.fixturenames
        ):
            raise ValueError("legacy exact file/database routing differs")
    os.environ["AGENT_GUARD_TEST_DATABASE_URL"] = row["dsn"] if row else value["default_dsn"]
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("AGENT_GUARD_TEST_DATABASE_URL", None)
        else:
            os.environ["AGENT_GUARD_TEST_DATABASE_URL"] = previous


def prepare_export_tls(output):
    """Prepare this consumer's independent original export gateway TLS material."""
    output = Path(output).absolute()
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError("export TLS symlink path forbidden")
    if (
        not output.is_dir()
        or output.stat().st_uid != os.getuid()
        or output.stat().st_mode & 0o777 != 0o700
    ):
        raise ValueError("export TLS output must be owned mode 0700")
    directory = output / "export-tls"
    directory.mkdir(mode=0o700)
    from tests.integration.test_gateway_tls import certificates

    previous = os.umask(0o077)
    try:
        certificates(directory)
    finally:
        os.umask(previous)
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid():
            raise ValueError("export TLS member must be an owned regular file")
        path.chmod(0o600)
        if path.stat().st_mode & 0o777 != 0o600:
            raise ValueError("export TLS member must be mode 0600")
    if not all((directory / name).is_file() for name in ("ca.pem", "tls.pem", "tls.key")):
        raise ValueError("export TLS certificate material incomplete")
    return directory


def run_inherited_groups(mode, output, run_id, owner_id):
    """Always execute the complete original twenty groups."""
    return _run_inherited_groups(mode, output, run_id, owner_id, closure_only=False)


def run_legacy_closure_groups(mode, output, run_id, owner_id):
    """Diagnostic only: all affected original A1/A2/B groups, never full acceptance."""
    return _run_inherited_groups(mode, output, run_id, owner_id, closure_only=True)


def _run_inherited_groups(mode, output, run_id, owner_id, *, closure_only):
    """Execute the original twenty groups against this actual installation.

    JUnit for script commands is produced by a real pytest subprocess wrapper;
    ordinary pytest commands retain their actual original test identities.
    """
    import xml.etree.ElementTree as ET

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    export_tls = prepare_export_tls(output)
    legacy = output / "legacy"
    manifest = materialize_legacy(mode, legacy)
    registry = json.loads(
        (REPO / "tasks/workflow/runs/A3.3-delivery-20261011/node-bindings-v3.json").read_bytes()
    )["inherited_accepted_registry"][mode]["commands20"]
    if len(registry) != 20:
        raise ValueError("original twenty-group registry differs")
    if closure_only:
        suffixes = {
            "a1-original-controls",
            "a1-upgrade-equivalent",
            "a2-original",
            "b-equivalent",
            "independent-original-probes",
        }
        registry = {k: v for k, v in registry.items() if k.removeprefix(mode + "-") in suffixes}
        if len(registry) != 5:
            raise ValueError("complete affected legacy group inventory differs")
    index = []
    for group, expected in registry.items():
        root = output / group
        root.mkdir(mode=0o700)
        env = dict(
            os.environ,
            A23_RUN_LABEL=group,
            A23_CLI_RUN_LABEL=group,
            PYTHONPATH="",
            PR9_INSTALL_MODE=mode,
            A32_EXPORT_TLS_DIR=str(export_tls),
        )
        for key in ("A23_RECEIPT_EVIDENCE", "A23_CLI_EVIDENCE", "A23_HTTPS_EVIDENCE"):
            directory = root / key
            directory.mkdir(mode=0o700)
            env[key] = str(directory)
        runtime = legacy / "inherited/runtime" / group
        runtime.mkdir(parents=True, mode=0o700)
        argv = manifest["groups"][group]["argv"]
        # The old current-PG inventory intentionally predates A33, so its exact
        # file inventory is used: including all current integration here would
        # recursively invoke this very deployment acceptance test.
        suffix = group.removeprefix(mode + "-")
        if suffix in ("ordinary", "current-pg-nonclock", "current-clock1000"):
            files = sorted({n.split("::", 1)[0] for n in expected["actual_nodeids"]})
            argv = ["-m", "pytest", "-p", "runtime_provenance", *files]
        else:
            argv = list(argv)
            cleaned = []
            i = 0
            while i < len(argv):
                item = argv[i]
                if item.startswith(("--basetemp=", "--junitxml=")):
                    i += 1
                    continue
                if item == "-o" and i + 1 < len(argv) and argv[i + 1].startswith("cache_dir="):
                    i += 2
                    continue
                item = item.replace("/e/" + mode + "-tests/inherited", str(legacy / "inherited"))
                item = item.replace("/e/" + mode + "-tests", str(REPO))
                item = item.replace("/e/snapshot-r6", str(REPO))
                cleaned.append(item)
                i += 1
            argv = cleaned
        if suffix == "oracle60":
            argv = [
                "--rootdir=" + str(legacy) if item.startswith("--rootdir=") else item
                for item in argv
            ]
        xml = root / "results.xml"
        if argv[:2] != ["-m", "pytest"]:
            if suffix == "readme-old-two-flows":
                argv[-1] = "pr9_" + uuid.uuid4().hex[:12]
            if suffix == "environment":
                argv[0] = str(legacy / "environment_observer.py")
                _environment_gate(mode, root, env)
            command = [sys.executable, *argv]
            wrapper = root / "test_native_command.py"
            wrapper.write_text(
                "import subprocess\n"
                "def test_original_native_command():\n"
                "    result = subprocess.run(" + repr(command) + ", timeout=3600)\n"
                "    assert result.returncode == 0\n"
            )
            argv = ["-m", "pytest", str(wrapper), "--rootdir=" + str(root)]
        argv += ["--junitxml=" + str(xml), "-o", "cache_dir=" + str(root / "cache"), "-q"]
        with legacy_database_routes(
            suffix, legacy, root, env["AGENT_GUARD_TEST_DATABASE_URL"]
        ) as routing:
            env.update(routing)
            if routing:
                argv += ["-p", "pr9_legacy_db_router"]
            launcher = (
                "import sys,runpy;sys.path.insert(0," + repr(str(REPO)) + ");"
                "sys.path.insert(0," + repr(str(legacy / "inherited")) + ");"
                "sys.argv=['pytest',*"
                + repr(argv[2:])
                + "];runpy.run_module('pytest',run_name='__main__')"
            )
            command = [sys.executable, "-c", launcher]
            (root / "command.json").write_text(json.dumps({"argv": argv, "mode": mode}, indent=2))
            result = execute_observed_command(command, root, env, mode)
        (root / "exit.json").write_text(json.dumps({"exit": result.returncode}))
        if result.returncode:
            raise RuntimeError("original inherited group failed: " + group)
        tree = ET.parse(xml)
        if any(list(tree.iter(tag)) for tag in ("failure", "error", "skipped")):
            raise ValueError("incomplete inherited group: " + group)
        actual = {c.attrib["classname"] + "::" + c.attrib["name"] for c in tree.iter("testcase")}
        required = {
            n.split("::", 1)[0].removesuffix(".py").replace("/", ".") + "::" + n.split("::", 1)[1]
            for n in expected["actual_nodeids"]
        }
        if not actual or not actual >= required:
            raise ValueError(
                "inherited node coverage mismatch: "
                + group
                + " "
                + repr(sorted(required - actual)[:10])
            )
        index.append(
            {
                "id": group,
                "run_id": run_id,
                "owner_id": owner_id,
                "path": str(xml.relative_to(output)),
                "sha256": hashlib.sha256(xml.read_bytes()).hexdigest(),
            }
        )
    path = output / "index.json"
    path.write_text(json.dumps(index, indent=2))
    return path


def _environment_gate(mode, root, env):
    """Bind the historical observer to actual current installed migration bytes."""
    import psycopg

    from agent_guard.ledger.lineage import load_manifest
    from agent_guard.ledger.migrate import DEFAULT_MIGRATIONS_DIR

    migrations = load_manifest().migrations
    gateway = {m.relative_path: m.checksum for m in migrations}
    historical = json.loads(
        (REPO / "tests/fixtures/pr9_legacy/historical-migrations.json").read_bytes()
    )
    historical14 = historical["original14_raw_sha256"]
    if not gateway.items() >= historical14.items():
        raise ValueError("original fourteen migration bytes changed")
    share = Path(sys.prefix) / "share/agent-guard/migrations"
    historical_standalone = {}
    for relative, checksum in historical["standalone"].items():
        path = share / relative
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError("original standalone migration bytes changed")
        historical_standalone[str(path)] = checksum
    with psycopg.connect(env["AGENT_GUARD_TEST_DATABASE_URL"]) as conn:
        identity = list(conn.execute("SELECT current_database(),current_user").fetchone())
    gate = {
        "mode": mode,
        "runtime_uid": os.geteuid(),
        "current_gateway15_registry": gateway,
        "current_sql_raw_sha256": {
            k: hashlib.sha256((DEFAULT_MIGRATIONS_DIR / k).read_bytes()).hexdigest()
            for k in gateway
        },
        "original14_raw_sha256": historical14,
        "standalone001_006_and_audit001_installed_files": historical_standalone,
        "gateway_database_and_user": identity,
    }
    path = root / "gate.json"
    path.write_text(json.dumps(gate))
    env["AG31_INSTALLED_GATE"] = str(path)
    private = Path("/private")
    private.mkdir(exist_ok=True, mode=0o700)
    (private / "runtime.json").write_text(
        json.dumps({"dsn": {"gateway": env["AGENT_GUARD_TEST_DATABASE_URL"]}})
    )


def validate_capacity_inputs(root):
    """Accept only the pinned 110 original members; never trust arbitrary mounts."""
    root = Path(root).absolute()
    for path in (root, *root.parents):
        if path.is_symlink():
            raise ValueError("capacity symlink root forbidden")
    if not root.is_dir() or root.stat().st_mode & 0o777 != 0o700:
        raise ValueError("capacity root must be mode 0700")
    path = root / "container-binding.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o777 != 0o600:
        raise ValueError("capacity binding must be mode 0600")
    binding = json.loads(path.read_bytes())
    trusted = json.loads(
        (REPO / "tests/fixtures/pr9_legacy/trusted-capacity-members.json").read_bytes()
    )
    relocation = binding["relocation_run"]
    if (
        relocation["historical_binding_sha256"] != trusted["historical_binding_sha256"]
        or relocation["source_mapping"]["container"] != "/capacity/inputs"
    ):
        raise ValueError("capacity source or container prefix mismatch")
    members = binding["members"]
    if len(members) != 110 or len(trusted["members"]) != 110:
        raise ValueError("complete capacity inventory required")
    for index, (member, expected) in enumerate(zip(members, trusted["members"], strict=True)):
        if {k: member[k] for k in ("role", "sha256")} != expected:
            raise ValueError("capacity original identity mismatch")
        relative = Path(member["path"]).relative_to("/capacity/inputs")
        if (
            ".." in relative.parts
            or len(relative.parts) != 3
            or relative.parts[:2] != ("originals", str(index))
        ):
            raise ValueError("capacity member path mismatch")
        target = root / relative
        for candidate in (target, *target.parents):
            if candidate.is_symlink():
                raise ValueError("capacity member symlink forbidden")
        if not target.is_file() or target.stat().st_mode & 0o777 != 0o600:
            raise ValueError("capacity original must be mode 0600")
        checksum = hashlib.sha256()
        with target.open("rb") as stream:
            while block := stream.read(1048576):
                checksum.update(block)
        if checksum.hexdigest() != expected["sha256"]:
            raise ValueError("capacity original byte SHA mismatch")
    plans = [m["path"] for m in members if m["role"] == "formal_plan"]
    if plans != [binding["formal_plan"]]:
        raise ValueError("capacity formal plan mapping mismatch")
    return root


def cleanup_recorded(root):
    """Reap one recorded owner after interruption; any mismatch is an error."""
    import re
    import threading

    root = Path(root).absolute()
    for path in (root, *root.parents):
        if path.is_symlink():
            raise ValueError("cleanup root symlink forbidden")
    if not root.is_dir() or root.stat().st_mode & 0o777 != 0o700:
        raise ValueError("cleanup root must be mode 0700")
    documents = {}
    for name in ("owner-state.json", "owned-resources.json"):
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o777 != 0o600:
            raise ValueError("cleanup identity file must be mode 0600")
        documents[name] = json.loads(path.read_bytes())
    state = documents["owner-state.json"]
    state_keys = {"version", "run_id", "owner_id", "project", "image"}
    version = state.get("version")
    if type(version) is not int or version not in (1, 2):
        raise ValueError("invalid owner identity version")
    if version == 2:
        state_keys.add("image_full_id")
    if set(state) != state_keys:
        raise ValueError("invalid owner identity document")
    image_full_id = state.get("image_full_id")
    if image_full_id is not None and (
        type(image_full_id) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_full_id)
    ):
        raise ValueError("cleanup requires full image ID")
    run = str(uuid.UUID(state["run_id"]))
    if run != state["run_id"] or state["project"] != "ag33-" + run:
        raise ValueError("cleanup project/run mismatch")
    if not isinstance(state["owner_id"], str) or not state["owner_id"]:
        raise ValueError("invalid cleanup owner")
    if state["image"] not in {
        "agent-guard-normal-" + mode + ":" + run for mode in ("source", "wheel")
    }:
        raise ValueError("cleanup image identity mismatch")
    resources = documents["owned-resources.json"]
    if set(resources) != {"ids", "volumes", "networks"}:
        raise ValueError("invalid owned resources document")
    if any(not re.fullmatch("[0-9a-f]{64}", value) for value in resources["ids"].values()):
        raise ValueError("cleanup requires full container IDs")
    prefix = state["project"] + "-"
    for volume in resources["volumes"]:
        if not volume.startswith(prefix) or "/" in volume:
            raise ValueError("cleanup volume project mismatch")
    for network in resources["networks"]:
        if (
            set(network) != {"name", "id"}
            or not network["name"].startswith(prefix)
            or not re.fullmatch("[0-9a-f]{64}", network["id"])
        ):
            raise ValueError("cleanup network identity mismatch")
    module = load_supervisor()
    owner = module.Owner.__new__(module.Owner)
    owner.root, owner.control = root, root / "control"
    owner.run, owner.owner, owner.project, owner.image = (
        run,
        state["owner_id"],
        state["project"],
        state["image"],
    )
    owner.ids, owner.volumes, owner.networks = (
        resources["ids"],
        resources["volumes"],
        resources["networks"],
    )
    owner.env = dict(os.environ)
    owner.children, owner.logs, owner.queues = {}, [], {}
    owner.bridge = None
    owner.discover_partial = False
    owner.image_full_id = image_full_id
    owner.seq = max((int(p.name.split("-", 1)[0]) for p in root.glob("[0-9]*-native*")), default=0)
    owner.write_lock = threading.Lock()
    previous = os.umask(0o077)
    try:
        # Validate every present recorded identity before the first deletion.
        identities = [("container", value) for value in owner.ids.values()]
        identities += [("network", value["id"]) for value in owner.networks]
        identities += [("volume", value) for value in owner.volumes]
        identities += [("image", owner.image)]
        for kind, identity in identities:
            result = owner.call(["docker", kind, "inspect", identity], allow=True)
            if result.returncode:
                missing = result.stderr.lower()
                if not any(marker in missing for marker in (b"no such", b"not found")):
                    raise RuntimeError("owned identity inspection failed")
                continue
            observed = json.loads(result.stdout)[0]
            labels = (
                observed["Config"].get("Labels", {})
                if kind in ("container", "image")
                else observed.get("Labels", {})
            )
            if (
                labels.get("agent-guard.owner") != owner.owner
                or labels.get("agent-guard.run") != owner.run
            ):
                raise ValueError("cleanup recorded owner/run mismatch")
            if kind == "image" and (
                image_full_id is None
                or observed["Id"] != image_full_id
                or owner.image not in (observed.get("RepoTags") or [])
            ):
                raise ValueError("cleanup image requires recorded full ID/tag")
            if kind == "container" and (
                observed["Id"] != identity or not observed["Name"].startswith("/" + prefix)
            ):
                raise ValueError("cleanup container project/full ID mismatch")
            if (
                kind == "container"
                and "com.docker.compose.project" in labels
                and labels["com.docker.compose.project"] != owner.project
            ):
                raise ValueError("cleanup compose project mismatch")
            if kind == "network":
                expected_name = next(n["name"] for n in owner.networks if n["id"] == identity)
                if observed["Id"] != identity or observed["Name"] != expected_name:
                    raise ValueError("cleanup network full ID/project mismatch")
            if kind == "volume" and observed["Name"] != identity:
                raise ValueError("cleanup volume identity mismatch")
        prior = root / "cleanup.json"
        if prior.exists():
            retained = root / ("cleanup-prior-" + str(uuid.uuid4()) + ".json")
            retained.write_bytes(prior.read_bytes())
            retained.chmod(0o600)
        owner.cleanup()
    finally:
        os.umask(previous)


def cleanup_installations(root):
    """Reap only closed, persisted source/wheel installation identities."""
    import re
    import subprocess

    root = Path(root).absolute()
    if (
        any(p.is_symlink() for p in (root, *root.parents))
        or not root.is_dir()
        or root.stat().st_mode & 0o777 != 0o700
    ):
        raise ValueError("private nonsymlink installation evidence required")
    errors, cleaned = [], 0

    def docker(arguments):
        return subprocess.run(["docker", *arguments], capture_output=True, timeout=120, check=False)

    for mode_entry in sorted(root.iterdir()):
        if (
            mode_entry.is_symlink()
            or not mode_entry.is_dir()
            or mode_entry.name not in ("source", "wheel")
            or mode_entry.stat().st_mode & 0o777 != 0o700
        ):
            errors.append("unknown installation mode entry")
            continue
        for entry in sorted(mode_entry.iterdir()):
            try:
                run = str(uuid.UUID(entry.name))
                if (
                    run != entry.name
                    or entry.is_symlink()
                    or not entry.is_dir()
                    or entry.stat().st_mode & 0o777 != 0o700
                ):
                    raise ValueError("private installation run required")
                path = entry / "installation-state.json"
                if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o777 != 0o600:
                    raise ValueError("private installation state required")
                state = json.loads(path.read_bytes())
                keys = {
                    "version",
                    "mode",
                    "run_id",
                    "owner_id",
                    "image_full_id",
                    "image_tag",
                    "created_container_full_ids",
                }
                if (
                    type(state) is not dict
                    or set(state) != keys
                    or type(state["version"]) is not int
                    or state["version"] != 1
                    or state["run_id"] != run
                    or state["mode"] != mode_entry.name
                    or state["owner_id"] != "a33-deploy-" + run
                    or state["image_tag"] != "agent-guard-a33-deploy-" + run + ":" + mode_entry.name
                ):
                    raise ValueError("installation identity mismatch")
                if type(state["image_full_id"]) is not str or not re.fullmatch(
                    r"sha256:[0-9a-f]{64}", state["image_full_id"]
                ):
                    raise ValueError("full installation image ID required")
                containers = state["created_container_full_ids"]
                if (
                    type(containers) is not list
                    or len(containers) != len(set(containers))
                    or any(
                        type(c) is not str or not re.fullmatch(r"[0-9a-f]{64}", c)
                        for c in containers
                    )
                ):
                    raise ValueError("full installation container IDs required")
                present = []
                for kind, identity in [("container", c) for c in containers] + [
                    ("image", state["image_full_id"])
                ]:
                    result = docker([kind, "inspect", identity])
                    if result.returncode:
                        if not any(m in result.stderr.lower() for m in (b"no such", b"not found")):
                            raise RuntimeError("installation inspection failed")
                        continue
                    observed = json.loads(result.stdout)[0]
                    labels = observed["Config"].get("Labels", {})
                    if (
                        observed["Id"] != identity
                        or labels.get("agent-guard.owner") != state["owner_id"]
                        or labels.get("agent-guard.run") != run
                    ):
                        raise ValueError("installation full ID/owner/run mismatch")
                    if kind == "image" and state["image_tag"] not in (
                        observed.get("RepoTags") or []
                    ):
                        raise ValueError("installation image tag mismatch")
                    if kind == "container" and not observed["Name"].startswith(
                        ("/ag-a33-deploy-", "/ag-a33-inherited-", "/ag-a33-wheel-copy-")
                    ):
                        raise ValueError("installation container name mismatch")
                    present.append((kind, identity))
                for kind, identity in present:
                    arguments = (
                        ["rm", "-f", identity]
                        if kind == "container"
                        else ["image", "rm", state["image_tag"]]
                    )
                    if docker(arguments).returncode:
                        raise RuntimeError("installation resource removal failed")
                for arguments in (
                    ["ps", "-aq"],
                    ["network", "ls", "-q"],
                    ["volume", "ls", "-q"],
                    ["image", "ls", "-q"],
                ):
                    result = docker(
                        [
                            *arguments,
                            "--filter",
                            "label=agent-guard.owner=" + state["owner_id"],
                            "--filter",
                            "label=agent-guard.run=" + run,
                        ]
                    )
                    if result.returncode or result.stdout.strip():
                        raise RuntimeError("installation unknown owned resources remain")
                cleaned += 1
            except Exception as exc:
                errors.append(type(exc).__name__)
    if errors:
        raise RuntimeError("installation cleanup failed for " + str(len(errors)) + " entries")
    return cleaned


def cleanup_all(root, *, installation_evidence_root=None):
    """Strict UUID-only owner base traversal; unknown entries are never deleted."""
    root = Path(root).absolute()
    for path in (root, *root.parents):
        if path.is_symlink():
            raise ValueError("cleanup base symlink forbidden")
    if not root.is_dir() or root.stat().st_mode & 0o777 != 0o700:
        raise ValueError("cleanup base must be mode 0700")
    cleaned, errors = 0, []
    for entry in sorted(root.iterdir()):
        try:
            if entry.is_symlink() or not entry.is_dir():
                raise ValueError("unknown owner base entry")
            try:
                canonical = str(uuid.UUID(entry.name))
            except ValueError as exc:
                raise ValueError("unknown owner base directory") from exc
            if canonical != entry.name:
                raise ValueError("noncanonical owner directory")
            cleanup_recorded(entry)
            cleaned += 1
        except Exception as exc:
            errors.append(
                {
                    "entry_name_sha256": hashlib.sha256(entry.name.encode()).hexdigest(),
                    "error_type": type(exc).__name__,
                }
            )
    if installation_evidence_root is not None:
        installation_root = Path(installation_evidence_root).absolute()
        try:
            if installation_root.parent != root.parent or installation_root == root:
                raise ValueError("installation evidence must be sibling of owner base")
            cleaned += cleanup_installations(installation_root)
        except Exception as exc:
            errors.append(
                {
                    "entry_name_sha256": hashlib.sha256(
                        installation_root.name.encode()
                    ).hexdigest(),
                    "error_type": type(exc).__name__,
                }
            )
    summary = {"owners_cleaned": cleaned, "errors": errors}
    print(json.dumps(summary))
    if errors:
        raise RuntimeError("cleanup-all failed for " + str(len(errors)) + " entries")
    return summary


if __name__ == "__main__":
    sys.exit(main())
