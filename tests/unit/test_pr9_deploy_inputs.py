"""Negative controls for the trusted owner inputs; no Docker or service needed."""

import hashlib
import json

import pytest

from tools import pr9_deploy_inputs as inputs


def test_private_root_rejected_before_supervisor_import(tmp_path, monkeypatch):
    tmp_path = tmp_path.resolve()
    tmp_path.chmod(0o755)

    def forbidden():
        pytest.fail("unsafe root reached resource owner")

    monkeypatch.setattr(inputs, "load_supervisor", forbidden)
    with pytest.raises(ValueError, match="0700"), inputs.deployment(tmp_path, "source"):
        pytest.fail("unsafe root accepted")


def test_legacy_tamper_rejected_before_execution(tmp_path, monkeypatch):
    fixtures = tmp_path / "tests/fixtures/pr9_legacy"
    fixtures.mkdir(parents=True)
    original = fixtures / "test_original.py.txt"
    original.write_text("assert False\n")
    (fixtures / "provenance.json").write_text(
        json.dumps(
            {
                "files": {
                    "source/inherited/test_original.py": {
                        "path": original.name,
                        "sha256": hashlib.sha256(b"assert True\n").hexdigest(),
                    }
                }
            }
        )
    )
    monkeypatch.setattr(inputs, "REPO", tmp_path)
    with pytest.raises(ValueError, match="original SHA mismatch"):
        inputs.materialize_legacy("source", tmp_path / "restored")
    assert not (tmp_path / "restored/inherited/test_original.py").exists()


def test_legacy_materialization_preserves_assertion_ast(tmp_path, monkeypatch):
    fixtures = tmp_path / "tests/fixtures/pr9_legacy"
    fixtures.mkdir(parents=True)
    raw = b"def test_refusal():\n    assert 2 + 2 == 4\n"
    (fixtures / "original.txt").write_bytes(raw)
    (fixtures / "provenance.json").write_text(
        json.dumps(
            {
                "files": {
                    "source/inherited/test_original.py": {
                        "path": "original.txt",
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                }
            }
        )
    )
    monkeypatch.setattr(inputs, "REPO", tmp_path)
    output = tmp_path / "restored"
    inputs.materialize_legacy("source", output)
    assert (output / "inherited/test_original.py").read_bytes() == raw
    row = json.loads((output / "adaptations.json").read_bytes())[
        "source/inherited/test_original.py"
    ]
    assert row["original_ast_sha256"] == row["executed_ast_sha256"]


def test_capacity_symlink_root_cannot_authorize_host_mount(tmp_path):
    tmp_path = tmp_path.resolve()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(private, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink root"):
        inputs.validate_capacity_inputs(alias)


def test_capacity_binding_cannot_choose_container_mount(tmp_path, monkeypatch):
    tmp_path = tmp_path.resolve()
    private = tmp_path / "inputs"
    private.mkdir(mode=0o700)
    path = private / "container-binding.json"
    path.write_text(
        json.dumps(
            {
                "relocation_run": {
                    "historical_binding_sha256": "0" * 64,
                    "source_mapping": {"container": "/var/run"},
                }
            }
        )
    )
    path.chmod(0o600)
    fixtures = tmp_path / "tests/fixtures/pr9_legacy"
    fixtures.mkdir(parents=True)
    (fixtures / "trusted-capacity-members.json").write_text(
        json.dumps({"historical_binding_sha256": "0" * 64})
    )
    monkeypatch.setattr(inputs, "REPO", tmp_path)
    with pytest.raises(ValueError, match="container prefix mismatch"):
        inputs.validate_capacity_inputs(private)


def test_cleanup_short_identity_refused_before_docker(tmp_path, monkeypatch):
    tmp_path = tmp_path.resolve()
    tmp_path.chmod(0o700)
    run = "11111111-1111-4111-8111-111111111111"
    state = {
        "version": 1,
        "run_id": run,
        "owner_id": "pr9-deploy-" + run,
        "project": "ag33-" + run,
        "image": "agent-guard-normal-source:" + run,
    }
    for name, value in (
        ("owner-state.json", state),
        ("owned-resources.json", {"ids": {"operator": "abc"}, "volumes": [], "networks": []}),
    ):
        path = tmp_path / name
        path.write_text(json.dumps(value))
        path.chmod(0o600)

    def forbidden():
        pytest.fail("short ID reached Docker")

    monkeypatch.setattr(inputs, "load_supervisor", forbidden)
    with pytest.raises(ValueError, match="full container IDs"):
        inputs.cleanup_recorded(tmp_path)


def test_cleanup_wrong_owner_is_refused_before_any_deletion(tmp_path, monkeypatch):
    from types import SimpleNamespace

    tmp_path = tmp_path.resolve()
    tmp_path.chmod(0o700)
    run = "11111111-1111-4111-8111-111111111111"
    state = {
        "version": 1,
        "run_id": run,
        "owner_id": "pr9-deploy-" + run,
        "project": "ag33-" + run,
        "image": "agent-guard-normal-source:" + run,
    }
    for name, value in (
        ("owner-state.json", state),
        ("owned-resources.json", {"ids": {"operator": "a" * 64}, "volumes": [], "networks": []}),
    ):
        path = tmp_path / name
        path.write_text(json.dumps(value))
        path.chmod(0o600)

    class WrongOwner:
        def call(self, argv, **kwargs):
            assert argv[:3] == ["docker", "container", "inspect"]
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [{"Id": "a" * 64, "Config": {"Labels": {"agent-guard.owner": "foreign"}}}]
                ),
            )

        def cleanup(self):
            pytest.fail("foreign identity reached deletion")

    monkeypatch.setattr(inputs, "load_supervisor", lambda: SimpleNamespace(Owner=WrongOwner))
    with pytest.raises(ValueError, match="owner/run mismatch"):
        inputs.cleanup_recorded(tmp_path)


@pytest.mark.parametrize("ancestor", (False, True))
def test_deployment_rejects_symlink_before_resolving(tmp_path, monkeypatch, ancestor):
    tmp_path = tmp_path.resolve()
    target = tmp_path / "real"
    target.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    requested = alias / "child" if ancestor else alias

    def forbidden():
        pytest.fail("symlink input reached resource owner")

    monkeypatch.setattr(inputs, "load_supervisor", forbidden)
    with pytest.raises(ValueError, match="symlink root"), inputs.deployment(requested, "source"):
        pytest.fail("symlink deployment accepted")


def test_private_stdout_uses_bounded_pipe_and_retains_native_exit(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    module = inputs.load_supervisor()
    owner = module.Owner.__new__(module.Owner)
    owner.root, owner.seq, owner.env = tmp_path.resolve(), 0, dict(os.environ)
    original = subprocess.Popen

    def pipe_required(*args, **kwargs):
        assert kwargs["stdout"] is subprocess.PIPE
        return original(*args, **kwargs)

    monkeypatch.setattr(module.subprocess, "Popen", pipe_required)
    result = owner.call([sys.executable, "-c", "print('SYNTHETIC_PRIVATE_PROBE')"], private=True)
    assert result.stdout == b"SYNTHETIC_PRIVATE_PROBE\n" and result.returncode == 0
    assert b"SYNTHETIC_PRIVATE_PROBE" not in (owner.root / "0001-native.stdout").read_bytes()
    with pytest.raises(ValueError, match="exceeds 65536"):
        owner.call([sys.executable, "-c", "print('x'*70000)"], private=True)
    receipt = json.loads((owner.root / "0002-native.json").read_bytes())
    assert receipt["private_output"] is True
    assert b"x" * 100 not in (owner.root / "0002-native.stdout").read_bytes()


def test_private_stdout_timeout_keeps_native_timeout_receipt(tmp_path):
    import os
    import subprocess
    import sys

    module = inputs.load_supervisor()
    owner = module.Owner.__new__(module.Owner)
    owner.root, owner.seq, owner.env = tmp_path.resolve(), 0, dict(os.environ)
    with pytest.raises(subprocess.TimeoutExpired):
        owner.call([sys.executable, "-c", "import time; time.sleep(3)"], private=True, timeout=0.05)
    receipt = json.loads((owner.root / "0001-native.json").read_bytes())
    assert receipt["timed_out"] is True and receipt["native_exit"] != 0


def test_cleanup_all_refuses_unknown_entry_but_reaps_valid_owner(tmp_path, monkeypatch):
    tmp_path = tmp_path.resolve()
    tmp_path.chmod(0o700)
    run = "11111111-1111-4111-8111-111111111111"
    owner = tmp_path / run
    owner.mkdir(mode=0o700)
    unknown = tmp_path / "SYNTHETIC_UNRECOGNIZED_EVIDENCE"
    unknown.mkdir(mode=0o700)
    calls = []
    monkeypatch.setattr(inputs, "cleanup_recorded", lambda path: calls.append(path))
    with pytest.raises(RuntimeError, match="cleanup-all failed"):
        inputs.cleanup_all(tmp_path)
    assert calls == [owner] and unknown.is_dir()


def test_cleanup_all_never_follows_uuid_symlink(tmp_path, monkeypatch):
    tmp_path = tmp_path.resolve()
    base = tmp_path / "base"
    base.mkdir(mode=0o700)
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    (base / "11111111-1111-4111-8111-111111111111").symlink_to(target, target_is_directory=True)

    def forbidden(path):
        pytest.fail("symlink owner was followed")

    monkeypatch.setattr(inputs, "cleanup_recorded", forbidden)
    with pytest.raises(RuntimeError, match="cleanup-all failed"):
        inputs.cleanup_all(base)
    assert target.is_dir()


def test_public_control_is_fixed_and_readable(tmp_path):
    module = inputs.load_supervisor()
    control = tmp_path / "control"
    control.mkdir(mode=0o700)
    module.public_control(control, "settings.json", {"run_id": "public"})
    assert control.stat().st_mode & 0o777 == 0o755
    assert (control / "settings.json").stat().st_mode & 0o777 == 0o444
    with pytest.raises(ValueError, match="unknown"):
        module.public_control(control, "secret.json", {"secret": "never"})
    assert not (control / "secret.json").exists()


def test_bootstrap_closed_public_descriptor():
    import base64
    import copy
    import uuid

    module = inputs.load_supervisor()
    scope = {
        "journal_profile": "AG-AUDIT-JOURNAL-1",
        "gateway_id": "https://gateway.agent-guard.test",
        "tenant_id": "tenant-demo",
        "task_id": "task-demo",
        "stream_id": str(uuid.uuid4()),
        "epoch": 1,
    }
    digest = base64.urlsafe_b64encode(bytes(32)).decode().rstrip("=")
    descriptor = {
        "scope": {k: v for k, v in scope.items() if k != "journal_profile"},
        "genesis_digest": digest,
        "bootstrap_digest": digest,
        "index_root": digest,
        "boundary": "NEW_EMPTY",
        "object_count": 0,
        "chunk_count": 0,
        "wire_bytes": 0,
    }
    value = {"scope": scope, "descriptor": descriptor}
    assert module.validate_bootstrap(value) == value
    for mutation in (
        lambda v: v.update(secret="forbidden"),
        lambda v: v["descriptor"].update(secret="forbidden"),
        lambda v: v["scope"].update(epoch=True),
        lambda v: v["descriptor"]["scope"].update(epoch=True),
        lambda v: v["descriptor"].update(wire_bytes=True),
        lambda v: v["descriptor"].update(index_root="a" * 43),
        lambda v: v["scope"].update(task_id="foreign"),
    ):
        bad = copy.deepcopy(value)
        mutation(bad)
        with pytest.raises(ValueError):
            module.validate_bootstrap(bad)


def test_installation_cleanup_rejects_unknown_without_docker(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    root.chmod(0o700)
    (root / "unknown").mkdir()
    import subprocess

    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: pytest.fail("unknown entry reached Docker")
    )
    with pytest.raises(RuntimeError, match="installation cleanup failed"):
        inputs.cleanup_installations(root)


@pytest.mark.parametrize("foreign", [False, True])
def test_installation_cleanup_checks_every_identity_before_removal(tmp_path, monkeypatch, foreign):
    import subprocess
    import types
    import uuid

    root = tmp_path.resolve()
    root.chmod(0o700)
    run = str(uuid.uuid4())
    entry = root / "source" / run
    (root / "source").mkdir(mode=0o700)
    entry.mkdir(mode=0o700)
    state = {
        "version": 1,
        "mode": "source",
        "run_id": run,
        "owner_id": "a33-deploy-" + run,
        "image_full_id": "sha256:" + "a" * 64,
        "image_tag": "agent-guard-a33-deploy-" + run + ":source",
        "created_container_full_ids": ["b" * 64],
    }
    path = entry / "installation-state.json"
    path.write_text(json.dumps(state))
    path.chmod(0o600)
    calls = []

    def docker(argv, **kwargs):
        calls.append(argv)
        if "inspect" in argv:
            image = argv[1] == "image"
            labels = {
                "agent-guard.owner": "foreign" if image and foreign else state["owner_id"],
                "agent-guard.run": run,
            }
            observed = {
                "Id": state["image_full_id"] if image else "b" * 64,
                "Config": {"Labels": labels},
                "RepoTags": [state["image_tag"]],
                "Name": "/ag-a33-wheel-copy-" + run,
            }
            return types.SimpleNamespace(
                returncode=0, stdout=json.dumps([observed]).encode(), stderr=b""
            )
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", docker)
    if foreign:
        with pytest.raises(RuntimeError, match="installation cleanup failed"):
            inputs.cleanup_installations(root)
        assert all("inspect" in call for call in calls)
    else:
        assert inputs.cleanup_installations(root) == 1
        assert [call for call in calls if "rm" in call] == [
            ["docker", "rm", "-f", "b" * 64],
            ["docker", "image", "rm", state["image_tag"]],
        ]


@pytest.mark.parametrize(
    "version,recorded,present,accepted",
    [
        (1, None, True, False),
        (1, None, False, True),
        (2, "sha256:" + "b" * 64, True, False),
        (2, "sha256:" + "a" * 64, True, True),
    ],
)
def test_owner_cleanup_requires_recorded_image_full_id(
    tmp_path, monkeypatch, version, recorded, present, accepted
):
    import uuid
    from types import SimpleNamespace

    root = tmp_path.resolve()
    root.chmod(0o700)
    run = str(uuid.uuid4())
    image = "agent-guard-normal-source:" + run
    owner = "pr9-deploy-" + run
    state = {
        "version": version,
        "run_id": run,
        "owner_id": owner,
        "project": "ag33-" + run,
        "image": image,
    }
    if version == 2:
        state["image_full_id"] = recorded
    for name, value in (
        ("owner-state.json", state),
        ("owned-resources.json", {"ids": {}, "volumes": [], "networks": []}),
    ):
        path = root / name
        path.write_text(json.dumps(value))
        path.chmod(0o600)
    cleaned = []

    class ImageOwner:
        def call(self, argv, **kwargs):
            assert argv == ["docker", "image", "inspect", image]
            if not present:
                return SimpleNamespace(returncode=1, stdout=b"", stderr=b"No such image")
            value = {
                "Id": "sha256:" + "a" * 64,
                "RepoTags": [image],
                "Config": {"Labels": {"agent-guard.owner": owner, "agent-guard.run": run}},
            }
            return SimpleNamespace(returncode=0, stdout=json.dumps([value]), stderr=b"")

        def cleanup(self):
            assert self.discover_partial is False
            assert self.image_full_id == recorded
            cleaned.append(True)

    monkeypatch.setattr(inputs, "load_supervisor", lambda: SimpleNamespace(Owner=ImageOwner))
    if accepted:
        inputs.cleanup_recorded(root)
        assert cleaned == [True]
    else:
        with pytest.raises(ValueError, match="recorded full ID"):
            inputs.cleanup_recorded(root)
        assert not cleaned


@pytest.mark.parametrize("mode", ["source", "wheel"])
def test_sidecars_preserve_original_pth_and_record_only_physical_adapters(tmp_path, mode):
    destination = tmp_path / "sidecars"
    rows = inputs.prepare_legacy_sidecars(destination, mode)
    assert set(rows) == set(inputs.SIDECAR_SHA256)
    for name, row in rows.items():
        assert row["original_sha256"] == inputs.SIDECAR_SHA256[name]
        assert (
            hashlib.sha256((destination / name).read_bytes()).hexdigest() == row["executed_sha256"]
        )
        if name.endswith(".pth"):
            assert row["original_sha256"] == row["executed_sha256"]
            assert not row["physical_replacements"]
        else:
            assert row["physical_replacements"]
    enhanced = (destination / "a31_enhanced_live_r1.py").read_text()
    assert "os.geteuid()==gate['expected_uid']" in enhanced
    assert "os.register_at_fork(after_in_child=start_live)" in enhanced
    assert "path.read_bytes()).hexdigest()==gate['installed_modules_sha256'][relative]" in enhanced


def test_sidecar_tamper_rejected_even_if_manifest_sha_is_rewritten(tmp_path, monkeypatch):
    import shutil

    fixtures = tmp_path / "tests/fixtures/pr9_legacy"
    shutil.copytree(inputs.REPO / "tests/fixtures/pr9_legacy/sidecars", fixtures / "sidecars")
    provenance = json.loads(
        (inputs.REPO / "tests/fixtures/pr9_legacy/sidecars-provenance.json").read_bytes()
    )
    row = provenance["files"]["source/a31_enhanced_live_r1.py"]
    path = fixtures / row["path"]
    path.write_text("raise RuntimeError('tampered')\n")
    row["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (fixtures / "sidecars-provenance.json").write_text(json.dumps(provenance))
    monkeypatch.setattr(inputs, "REPO", tmp_path)
    with pytest.raises(ValueError, match="original observer byte SHA"):
        inputs.prepare_legacy_sidecars(tmp_path / "output", "source")


@pytest.mark.parametrize(
    "loaded,accepted",
    [
        ([], True),
        ({}, False),
        (None, False),
        ([{"file": "/installed/agent_guard/__init__.py", "sha256": "b" * 64}], False),
    ],
)
def test_observer_empty_loaded_is_valid_but_type_and_member_sha_are_checked(
    tmp_path, loaded, accepted
):
    import os

    root = tmp_path.resolve()
    directory = root / "observed"
    directory.mkdir(mode=0o700)
    pid, ticks, argv_sha = 12345, 98765, "c" * 64
    gate = {
        "expected_uid": os.getuid(),
        "installed_root": "/installed",
        "installed_modules_sha256": {"agent_guard/__init__.py": "a" * 64},
    }
    value = {
        "valid": True,
        "phase": "atexit",
        "pid": pid,
        "uid": os.getuid(),
        "kernel_start_ticks": ticks,
        "argv_sha256": argv_sha,
        "loaded": loaded,
    }
    path = directory / (str(pid) + ".json")
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    if accepted:
        assert inputs.verify_observer_output(root, gate, pid, ticks, argv_sha) == value
    else:
        with pytest.raises(ValueError):
            inputs.verify_observer_output(root, gate, pid, ticks, argv_sha)


def test_export_tls_uses_original_generator_and_private_fresh_directory(tmp_path, monkeypatch):
    import os
    import sys
    import types

    output = tmp_path.resolve()
    output.chmod(0o700)
    seen = []

    def certificates(directory):
        seen.append(directory)
        for name in ("ca.pem", "tls.pem", "tls.key", "ca.key"):
            (directory / name).write_text("test-only")
            (directory / name).chmod(0o644)

    monkeypatch.setitem(
        sys.modules,
        "tests.integration.test_gateway_tls",
        types.SimpleNamespace(certificates=certificates),
    )
    directory = inputs.prepare_export_tls(output)
    assert seen == [directory]
    assert directory.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_uid == os.getuid() for p in directory.iterdir())
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in directory.iterdir())
    with pytest.raises(FileExistsError):
        inputs.prepare_export_tls(output)


def test_export_tls_rejects_symlink_ancestor_and_public_output(tmp_path):
    root = tmp_path.resolve()
    root.chmod(0o700)
    alias = root / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        inputs.prepare_export_tls(alias / "child")
    root.chmod(0o755)
    with pytest.raises(ValueError, match="0700"):
        inputs.prepare_export_tls(root)


def test_legacy_dynamic_prefix_and_logs_only_map_physical_paths(tmp_path, monkeypatch):
    import ast
    import sys

    root = tmp_path.resolve()
    fixtures = root / "tests/fixtures/pr9_legacy"
    fixtures.mkdir(parents=True)
    raw = (
        "import pathlib\nmode='source'\n"
        "prefix=pathlib.Path('/e/'+mode+'-venv/lib/python3.11/site-packages')\n"
        "assert prefix.is_relative_to("
        "pathlib.Path('/e/'+mode+'-venv/share/agent-guard/migrations'))\n"
        "pathlib.Path('/evidence/logs/result.json').write_text('observed')\n"
        "assert not pathlib.Path('/e/'+mode+'-tests/src').exists()\n"
    ).encode()
    (fixtures / "original.txt").write_bytes(raw)
    (fixtures / "provenance.json").write_text(
        json.dumps(
            {
                "files": {
                    "source/inherited/test_paths.py": {
                        "path": "original.txt",
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                }
            }
        )
    )
    monkeypatch.setattr(inputs, "REPO", root)
    destination = root / "restored"
    inputs.materialize_legacy("source", destination)
    executed = (destination / "inherited/test_paths.py").read_text()
    tree = ast.parse(executed)
    assert sum(isinstance(node, ast.Assert) for node in ast.walk(tree)) == 2
    assert "'/e/'+mode+'-tests/src'" in executed
    assert "'/e/'+mode+'-venv" not in executed
    namespace = {}
    exec(compile(ast.Module(body=tree.body[:3], type_ignores=[]), "paths", "exec"), namespace)
    assert namespace["prefix"] == inputs.Path(sys.prefix) / "lib/python3.11/site-packages"
    assert str(destination / "evidence-logs/result.json") in executed
    assert (destination / "evidence-logs").stat().st_mode & 0o777 == 0o700
    assert (fixtures / "original.txt").read_bytes() == raw


@pytest.mark.parametrize("fault", [None, "prefix", "missing_append", "registry", "installed_sha"])
def test_current_migration_qualification_keeps_prefix_and_checks_each_append(tmp_path, fault):
    import ast
    import shutil
    from pathlib import Path
    from types import SimpleNamespace

    original = (
        inputs.REPO
        / "tests/fixtures/pr9_legacy/originals/source/inherited/historical-adapted/b"
        / "test_r2_migrations.py.txt"
    ).read_text()
    executed, qualification = inputs.qualify_legacy_migration_test(original)
    ast.parse(executed)
    assert "assert registry(scratch.dsn)[:int(base)]==reg" in executed
    assert "assert _snapshot_business_tables(scratch.dsn)==before" in executed
    assert "assert registry(scratch.dsn)==reg_after" in executed
    assert "with pytest.raises((MigrationError,psycopg.IntegrityError)):" in executed
    installed = tmp_path.resolve()
    for name in inputs.CURRENT_APPEND_MIGRATIONS:
        shutil.copyfile(inputs.REPO / "migrations" / name, installed / name)
    applied = ["002", "003", "004", "005", "006", "008", "009"]
    rows = [tuple(row) for row in qualification["expected_registry_rows"]]
    if fault == "prefix":
        applied[0] = "003"
    elif fault == "missing_append":
        applied.pop()
    elif fault == "registry":
        rows[-1] = ("009", "009_x402_payment.sql", "0" * 64)
    elif fault == "installed_sha":
        (installed / "009_x402_payment.sql").write_text("tampered")
    namespace = {
        "base": "001",
        "applied": applied,
        "Path": Path,
        "DEFAULT_MIGRATIONS_DIR": installed,
        "registry": lambda dsn: rows,
        "scratch": SimpleNamespace(dsn="test-only"),
    }
    if fault is None:
        exec(qualification["executed_assertions"], namespace)
    else:
        with pytest.raises(AssertionError):
            exec(qualification["executed_assertions"], namespace)


def test_current_migration_qualification_rejects_unpinned_source(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    (root / "migrations").mkdir()
    for name in inputs.CURRENT_APPEND_MIGRATIONS:
        (root / "migrations" / name).write_text("not the pinned source")
    monkeypatch.setattr(inputs, "REPO", root)
    old = 'assert applied==[f"{i:03}" for i in range(int(base)+1,7)]'
    with pytest.raises(ValueError, match="source SHA mismatch"):
        inputs.qualify_legacy_migration_test(old)


def _legacy_pg_gate():
    import uuid

    run = str(uuid.uuid4())
    return {
        "version": 1,
        "owner_id": "pr9-deploy-" + run,
        "run_id": run,
        "pg_full_id": "a" * 64,
        "pg_image_full_id": "sha256:" + "b" * 64,
        "network_full_ids": ["c" * 64],
        "host": "pg-authority.agent-guard.test",
        "port": 5432,
        "ca_sha256": "d" * 64,
    }


@pytest.mark.parametrize("fault", ["owner", "fullid", "extra", "bool", "network"])
def test_legacy_pg_gate_rejects_ambiguous_identity(fault):
    gate = _legacy_pg_gate()
    assert inputs.validate_legacy_pg_gate(gate) is gate
    if fault == "owner":
        gate["owner_id"] = "shared-existing-server"
    elif fault == "fullid":
        gate["pg_full_id"] = "a" * 12
    elif fault == "extra":
        gate["discover_by_name"] = True
    elif fault == "bool":
        gate["port"] = True
    else:
        gate["network_full_ids"] = [{}]
    with pytest.raises(ValueError):
        inputs.validate_legacy_pg_gate(gate)


@pytest.mark.parametrize("fault", [None, "missing", "installed", "source"])
def test_historical_six_sql_preserves_exact_bytes_and_excludes_later_migrations(
    tmp_path, monkeypatch, fault
):
    import shutil
    import sys
    import types

    root = tmp_path.resolve()
    repository, installed = root / "repo", root / "installed"
    (repository / "migrations").mkdir(parents=True)
    installed.mkdir()
    fixtures = repository / "tests/fixtures/pr9_legacy"
    fixtures.mkdir(parents=True)
    original = inputs.REPO
    historical = json.loads(
        (original / "tests/fixtures/pr9_legacy/historical-migrations.json").read_bytes()
    )
    (fixtures / "historical-migrations.json").write_text(json.dumps(historical))
    selected = {
        n: h
        for n, h in historical["standalone"].items()
        if "/" not in n and n[:3] in {f"{i:03}" for i in range(1, 7)}
    }
    for name in selected:
        shutil.copyfile(original / "migrations" / name, repository / "migrations" / name)
        shutil.copyfile(original / "migrations" / name, installed / name)
    for name in ("007_audit_journal.sql", "008_threshold_approval.sql", "009_x402_payment.sql"):
        (installed / name).write_text("must not enter historical six snapshot")
    name = "006_event_seal.sql"
    if fault == "missing":
        (installed / name).unlink()
    elif fault == "installed":
        (installed / name).write_text("tampered")
    elif fault == "source":
        (repository / "migrations" / name).write_text("tampered")
    monkeypatch.setattr(inputs, "REPO", repository)
    monkeypatch.setitem(
        sys.modules,
        "agent_guard.ledger.migrate",
        types.SimpleNamespace(DEFAULT_MIGRATIONS_DIR=installed),
    )
    if fault:
        with pytest.raises((ValueError, FileNotFoundError)):
            inputs.materialize_historical_six(root / "snapshot")
    else:
        result = inputs.materialize_historical_six(root / "snapshot")
        assert result == selected
        assert {p.name for p in (root / "snapshot").iterdir()} == set(selected)
        assert all(
            hashlib.sha256(p.read_bytes()).hexdigest() == selected[p.name]
            and p.stat().st_mode & 0o777 == 0o600
            for p in (root / "snapshot").iterdir()
        )


@pytest.mark.parametrize("relative", list(inputs.CURRENT_LEGACY_CALLS))
def test_every_selected_current_migration_call_is_explicitly_qualified(relative):
    import ast

    original = (
        inputs.REPO / "tests/fixtures/pr9_legacy/originals/source" / (relative + ".txt")
    ).read_text()
    executed, metadata = inputs.qualify_current_legacy_calls(original, relative)
    ast.parse(executed)
    assert len(metadata["edits"]) == len(inputs.CURRENT_LEGACY_CALLS[relative]) + (
        relative.endswith("test_r4_boundaries.py")
    )
    for prefix in inputs.CURRENT_LEGACY_CALLS[relative]:
        assert "assert _pr9_applied==" + repr(prefix + ["008", "009"]) in executed
    if relative.endswith("test_r4_boundaries.py"):
        assert "apply_migrations(c,pre005)==['004','005']" in executed
        assert "match='006 pre-check'" in executed
        assert "after[0]==before[0]" in executed
        assert "after[1][:len(before[1])]==before[1]" in executed
        assert "verify_registry_extension(before[1],after[1])" in executed
    assert metadata["kind"] == "current appended migration compatibility qualification"


@pytest.mark.parametrize("fault", [None, "prefix", "extra", "checksum"])
def test_complete_registry_prefix_and_exact_006008009_extension(fault):
    before = [("005", "005_event_node_seal.sql", "old-checksum", "old-time")]
    expected = [
        (
            "006",
            "006_event_seal.sql",
            "3abb279bc88b2fd7b2ff427a57fda407b77908182ec612334d500bea2f76760c",
        ),
        *[(name[:3], name, digest) for name, digest in inputs.CURRENT_APPEND_MIGRATIONS.items()],
    ]
    after = before + [(*row, "new-time") for row in expected]
    if fault == "prefix":
        after[0] = (*before[0][:-1], "changed-time")
    elif fault == "extra":
        after.append(("010", "unknown.sql", "unknown", "extra"))
    elif fault == "checksum":
        after[-1] = (*after[-1][:2], "wrong", "new-time")
    if fault:
        with pytest.raises(ValueError):
            inputs.verify_registry_extension(before, after)
    else:
        assert inputs.verify_registry_extension(before, after) is None


@pytest.mark.parametrize("fault", [None, "host", "database", "sha", "namespace", "unmapped"])
def test_legacy_file_routing_precedes_fixtures_and_restores_default(tmp_path, monkeypatch, fault):
    import os
    import sys
    import types

    root = tmp_path.resolve()
    root.chmod(0o700)
    legacy = root / "legacy"
    legacy.mkdir(mode=0o700)
    files = inputs.LEGACY_DATABASE_FILES["a1-original-controls"]
    default = {"host": "own-pg.test", "dbname": "ag_controller_test", "user": "postgres"}
    routes = {}
    for relative, database in files.items():
        path = legacy / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("assert True\n")
        routes[relative] = {
            "database": database,
            "dsn": json.dumps({**default, "dbname": database}),
            "executed_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    relative = next(iter(files))
    if fault == "host":
        routes[relative]["dsn"] = json.dumps(
            {**default, "dbname": files[relative], "host": "shared-pg"}
        )
    elif fault == "database":
        routes[relative]["database"] = "shared_existing_database"
    elif fault == "sha":
        routes[relative]["executed_sha256"] = "0" * 64
    value = {
        "version": 1,
        "group": "a1-original-controls",
        "pg_gate": _legacy_pg_gate(),
        "system_identifier": "123456",
        "legacy_root": str(legacy),
        "default_dsn": json.dumps(default),
        "created": sorted(set(files.values())),
        "routes": routes,
        "dropped": [],
    }
    receipt = root / "routes.private.json"
    receipt.write_text(json.dumps(value))
    receipt.chmod(0o600)
    monkeypatch.setenv("PR9_LEGACY_DATABASE_ROUTES", str(receipt))
    monkeypatch.setenv("AGENT_GUARD_TEST_DATABASE_URL", "previous-default")
    monkeypatch.setattr(inputs, "verify_legacy_pg", lambda gate, dsn: "123456")
    monkeypatch.setattr(inputs, "_VALIDATED_LEGACY_ROUTES", {})
    module = types.ModuleType("psycopg.conninfo")
    module.conninfo_to_dict = json.loads
    monkeypatch.setitem(sys.modules, "psycopg.conninfo", module)
    item = types.SimpleNamespace(path=legacy / relative, fixturenames=[])
    if fault == "namespace":
        item.fixturenames = ["namespace"]
    elif fault == "unmapped":
        item.path = root / "current_unrouted_test.py"
    protocol = inputs.legacy_database_protocol(item, None)
    if fault not in (None, "unmapped"):
        with pytest.raises(ValueError):
            next(protocol)
        assert os.environ["AGENT_GUARD_TEST_DATABASE_URL"] == "previous-default"
    else:
        next(protocol)
        selected = json.loads(os.environ["AGENT_GUARD_TEST_DATABASE_URL"])
        assert selected == (
            default if fault == "unmapped" else {**default, "dbname": files[relative]}
        )
        with pytest.raises(StopIteration):
            next(protocol)
        assert os.environ["AGENT_GUARD_TEST_DATABASE_URL"] == "previous-default"


def test_preexisting_database_is_preserved_and_only_own_created_database_is_dropped(
    tmp_path, monkeypatch
):
    import sys
    import types

    root = tmp_path.resolve()
    root.chmod(0o700)
    legacy = root / "legacy"
    legacy.mkdir(mode=0o700)
    databases = {"ag_review_probe"}
    commands = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, command, parameters=None):
            commands.append((str(command), parameters))
            if parameters is not None:
                return types.SimpleNamespace(
                    fetchone=lambda: (1,) if parameters[0] in databases else None
                )
            name = str(command).split()[2]
            if str(command).startswith("CREATE DATABASE"):
                databases.add(name)
            elif str(command).startswith("DROP DATABASE"):
                databases.remove(name)
            return types.SimpleNamespace(fetchone=lambda: None)

    module = types.ModuleType("psycopg")
    module.connect = lambda *args, **kwargs: Connection()
    module.sql = types.SimpleNamespace(SQL=str, Identifier=lambda name: name)
    conninfo = types.ModuleType("psycopg.conninfo")
    conninfo.make_conninfo = lambda *args, **kwargs: "test-only"
    monkeypatch.setitem(sys.modules, "psycopg", module)
    monkeypatch.setitem(sys.modules, "psycopg.conninfo", conninfo)
    monkeypatch.setattr(inputs, "verify_legacy_pg", lambda gate, dsn: "123456")
    monkeypatch.setenv("PR9_LEGACY_PG_GATE", json.dumps(_legacy_pg_gate()))
    with pytest.raises(ValueError, match="preexists"):
        with inputs.legacy_database_routes("a1-original-controls", legacy, root, "test-only"):
            pytest.fail("preexisting database was accepted")
    assert databases == {"ag_review_probe"}
    assert any(command.startswith("CREATE DATABASE ag_review_f2") for command, _ in commands)
    assert any(command.startswith("DROP DATABASE ag_review_f2") for command, _ in commands)
    assert not any(command.startswith("DROP DATABASE ag_review_probe") for command, _ in commands)
    receipt = json.loads((root / "legacy-database-routes.private.json").read_bytes())
    assert receipt["created"] == ["ag_review_f2"] and receipt["dropped"] == ["ag_review_f2"]


@pytest.mark.parametrize("relative", sorted(inputs.CURRENT_PROBE_TABLE_FILES))
@pytest.mark.parametrize("fault", [None, "missing_new", "unexpected", "missing_old"])
def test_current_probe_inventory_retains_original37_and_exact_four(relative, fault):
    import ast

    original = (
        inputs.REPO / "tests/fixtures/pr9_legacy/originals/source" / (relative + ".txt")
    ).read_text()
    executed, metadata = inputs.qualify_current_table_inventory(original, relative)
    tree = ast.parse(executed)
    namespace = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in (
                "A31_ORIGINAL31",
                "A31_CURRENT007_SIX",
                "PR9_CURRENT008009_FOUR",
                "PR9_HISTORICAL_DS3",
                "PR9_CURRENT_DS_ONE",
            ):
                namespace[name] = frozenset(ast.literal_eval(node.value.args[0]))
    assert len(namespace["A31_ORIGINAL31"]) == 31
    assert len(namespace["A31_CURRENT007_SIX"]) == 6
    assert namespace["PR9_CURRENT008009_FOUR"] == inputs.CURRENT_ADDED_TABLES
    expected = set().union(
        namespace["A31_ORIGINAL31"],
        namespace["A31_CURRENT007_SIX"],
        namespace["PR9_CURRENT008009_FOUR"],
    )
    assert len(expected) == 41
    actual = set(expected)
    if fault == "missing_new":
        actual.remove("ag_payment_states")
    elif fault == "unexpected":
        actual.add("ag_unqualified_extra_table")
    elif fault == "missing_old":
        actual.remove("ag_grants")
    namespace.update(
        before={
            "gateway": dict.fromkeys(actual),
            "downstream": dict.fromkeys(
                inputs.HISTORICAL_DOWNSTREAM_TABLES | inputs.CURRENT_ADDED_DOWNSTREAM_TABLES
            ),
        },
        after={
            "gateway": dict.fromkeys(actual),
            "downstream": dict.fromkeys(
                inputs.HISTORICAL_DOWNSTREAM_TABLES | inputs.CURRENT_ADDED_DOWNSTREAM_TABLES
            ),
        },
    )
    assertion = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Assert) and "PR9_CURRENT008009_FOUR" in ast.unparse(n.test)
    )
    compiled = compile(ast.Module(body=[assertion], type_ignores=[]), "inventory", "exec")
    if fault:
        with pytest.raises(AssertionError):
            exec(compiled, namespace)
    else:
        exec(compiled, namespace)
    assert metadata["preserved_historical_gateway_tables"] == 37
    assert metadata["current_gateway_tables"] == 41
    assert "verify_current_migration_sql_files" in executed


def test_public_boundary_added_table_mutants_reach_actual_full_snapshot_comparison():
    import ast
    import copy

    relative = "inherited/probes/test_public_boundary.py"
    original = (
        inputs.REPO / "tests/fixtures/pr9_legacy/originals/source" / (relative + ".txt")
    ).read_text()
    executed, _ = inputs.qualify_current_table_inventory(original, relative)
    tree = ast.parse(executed)
    namespace = {"pytest": pytest, "json": json}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in (
                "A31_ORIGINAL31",
                "A31_CURRENT007_SIX",
                "PR9_CURRENT008009_FOUR",
                "PR9_HISTORICAL_DS3",
                "PR9_CURRENT_DS_ONE",
            ):
                namespace[name] = frozenset(ast.literal_eval(node.value.args[0]))
    # Exercise the actual upstream Python full-snapshot comparator. Its audit
    # delta is irrelevant to this isolated proof-row/new-table mutation control.
    receipts = ast.parse((inputs.REPO / "tests/fixtures/receipts.py").read_text())
    comparator = next(
        n for n in receipts.body if isinstance(n, ast.FunctionDef) and n.name == "result_read_only"
    )
    upstream = {"_journal_delta": lambda *args, **kwargs: None}
    exec(compile(ast.Module(body=[comparator], type_ignores=[]), "upstream", "exec"), upstream)
    changed = []

    def compare(before, after, **kwargs):
        changed.extend(
            (domain, name)
            for domain, names in (
                ("gateway", inputs.CURRENT_ADDED_TABLES),
                ("downstream", inputs.CURRENT_ADDED_DOWNSTREAM_TABLES),
            )
            for name in names
            if before[domain][name] != after[domain][name]
        )
        return upstream["result_read_only"](before, after, **kwargs)

    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    namespace.update(_original_result_read_only=compare, canonical_json_bytes=canonical)
    oracle = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_a31_fault_projection_oracle"
    )
    exec(compile(ast.Module(body=[oracle], type_ignores=[]), "qualified", "exec"), namespace)
    tables = set().union(
        namespace["A31_ORIGINAL31"], namespace["A31_CURRENT007_SIX"], inputs.CURRENT_ADDED_TABLES
    )
    before = {
        "gateway": {name: [] for name in tables},
        "downstream": {
            name: []
            for name in inputs.HISTORICAL_DOWNSTREAM_TABLES | inputs.CURRENT_ADDED_DOWNSTREAM_TABLES
        },
    }
    before["gateway"]["ag_receipt_outbox"] = [
        (json.dumps({"operation_id": "op", "result_bytes": "old"}),)
    ]
    after = copy.deepcopy(before)
    after["gateway"]["ag_proofs"] = [
        (
            json.dumps(
                {
                    "proof_jti": "j",
                    "operation_id": "op",
                    "purpose": "result-read",
                    "evidence_ref": "e",
                }
            ),
        )
    ]
    response = {"operation_id": "op", "result": {"body": ""}}
    response["result"]["body"] = "x" * (65536 - len(canonical(response)))
    namespace["_a31_fault_projection_oracle"](
        before,
        after,
        response=response,
        raw_response=canonical(response),
        operation_id="op",
        proof_jti="j",
        evidence_ref="e",
    )
    assert (
        set(changed)
        == (
            {("gateway", n) for n in inputs.CURRENT_ADDED_TABLES}
            | {("downstream", "ds_cosm2_bindings")}
        )
        and len(changed) == 5
    )


@pytest.mark.parametrize("fault", ["missing", "extra"])
def test_current_downstream_inventory_is_exact_historical_three_plus_one(fault):
    import ast

    relative = "inherited/probes/test_reviewer_variants.py"
    original = (
        inputs.REPO / "tests/fixtures/pr9_legacy/originals/source" / (relative + ".txt")
    ).read_text()
    executed, metadata = inputs.qualify_current_table_inventory(original, relative)
    tree = ast.parse(executed)
    namespace = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in (
                "A31_ORIGINAL31",
                "A31_CURRENT007_SIX",
                "PR9_CURRENT008009_FOUR",
                "PR9_HISTORICAL_DS3",
                "PR9_CURRENT_DS_ONE",
            ):
                namespace[node.targets[0].id] = frozenset(ast.literal_eval(node.value.args[0]))
    gateway = (
        namespace["A31_ORIGINAL31"] | namespace["A31_CURRENT007_SIX"] | inputs.CURRENT_ADDED_TABLES
    )
    downstream = set(inputs.HISTORICAL_DOWNSTREAM_TABLES | inputs.CURRENT_ADDED_DOWNSTREAM_TABLES)
    if fault == "missing":
        downstream.remove("ds_cosm2_bindings")
    else:
        downstream.add("ds_unqualified_extra")
    namespace["before"] = {
        "gateway": dict.fromkeys(gateway),
        "downstream": dict.fromkeys(downstream),
    }
    assertion = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Assert) and "PR9_HISTORICAL_DS3" in ast.unparse(n.test)
    )
    with pytest.raises(AssertionError):
        exec(
            compile(ast.Module(body=[assertion], type_ignores=[]), "ds-inventory", "exec"),
            namespace,
        )
    assert (
        metadata["historical_downstream_tables"] == 3 and metadata["current_downstream_tables"] == 4
    )


@pytest.mark.parametrize("fault", [None, "source", "installed", "shadow"])
def test_downstream_binding_checks_actual_installed_origin_and_both_raw_shas(
    tmp_path, monkeypatch, fault
):
    import shutil
    import sys
    import types

    root = tmp_path.resolve()
    original = inputs.REPO / "src/agent_guard/tools/downstream.py"
    source = root / "repo/src/agent_guard/tools/downstream.py"
    actual = root / "venv/lib/python3.11/site-packages/agent_guard/tools/downstream.py"
    for path in (source, actual):
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, path)
    if fault in ("source", "installed"):
        (source if fault == "source" else actual).write_text("tampered")
    module = types.ModuleType("agent_guard.tools.downstream")
    module.__file__ = str(source if fault == "shadow" else actual)
    package = types.ModuleType("agent_guard")
    package.__path__ = []
    tools_package = types.ModuleType("agent_guard.tools")
    tools_package.__path__ = []
    package.tools = tools_package
    tools_package.downstream = module
    monkeypatch.setitem(sys.modules, "agent_guard", package)
    monkeypatch.setitem(sys.modules, "agent_guard.tools", tools_package)
    monkeypatch.setitem(sys.modules, "agent_guard.tools.downstream", module)
    monkeypatch.setattr(inputs.sys, "prefix", str(root / "venv"))
    if fault:
        with pytest.raises(ValueError):
            inputs.verify_current_downstream_source(root / "repo")
    else:
        assert inputs.verify_current_downstream_source(root / "repo") is None


class _StartupProcess:
    pid = 123

    def __init__(self, exits=None):
        self.exits = iter(exits) if exits is not None else None

    def poll(self):
        return next(self.exits) if self.exits is not None else None


def _startup_identity(**changes):
    return dict(pid=123, start_ticks=987, uids=[501] * 4, **changes)


def test_startup_requires_exact_declared_bytes_after_emulator(tmp_path, monkeypatch):
    command = ["/opt/runtime/bin/python", "-c", "pass"]
    declared = b"/opt/runtime/bin/python\0-c\0pass\0"
    snapshots = iter(
        [
            (_startup_identity(), b"/usr/bin/rosetta-wrapper\0" + declared),
            (_startup_identity(), declared),
        ]
    )
    monkeypatch.setattr(inputs, "_process_snapshot", lambda pid: next(snapshots))
    path = tmp_path / "startup.json"
    ticks, sha = inputs.wait_declared_process(_StartupProcess(), command, 501, path)
    assert ticks == 987 and sha == hashlib.sha256(declared).hexdigest()
    receipt = json.loads(path.read_bytes())
    assert path.stat().st_mode & 0o777 == 0o600
    assert receipt["outcome"] == "matched_declared"
    assert [row["matches_declared"] for row in receipt["samples"]] == [False, True]
    assert receipt["samples"][0]["argv0"] == "/usr/bin/rosetta-wrapper"
    assert '"pass"' not in path.read_text()


@pytest.mark.parametrize("raw", [b"", b"/different/python\0-c\0pass\0"])
def test_startup_wrong_or_empty_argv_never_authorizes(tmp_path, monkeypatch, raw):
    monkeypatch.setattr(inputs, "_process_snapshot", lambda pid: (_startup_identity(), raw))
    path = tmp_path / "rejected.json"
    with pytest.raises(ValueError, match="deadline exhausted"):
        inputs.wait_declared_process(
            _StartupProcess(), ["/python", "-c", "pass"], 501, path, timeout=0.002
        )
    receipt = json.loads(path.read_bytes())
    assert receipt["outcome"] == "rejected"
    assert not any(row["matches_declared"] for row in receipt["samples"])


@pytest.mark.parametrize(
    ("first", "second", "message"),
    [
        ({"pid": 124}, {}, "PID differs"),
        ({"uids": [501, 0, 501, 501]}, {}, "UID differs"),
        ({}, {"start_ticks": 988}, "identity changed"),
        ({}, {"uids": [502] * 4}, "UID differs"),
    ],
)
def test_startup_identity_mutation_rejected(tmp_path, monkeypatch, first, second, message):
    def identity(changes):
        value = _startup_identity()
        value.update(changes)
        return value

    snapshots = iter([(identity(first), b"/wrapper\0"), (identity(second), b"/python\0-c\0pass\0")])
    monkeypatch.setattr(inputs, "_process_snapshot", lambda pid: next(snapshots))
    with pytest.raises(ValueError, match=message):
        inputs.wait_declared_process(
            _StartupProcess(), ["/python", "-c", "pass"], 501, tmp_path / "rejected.json"
        )


@pytest.mark.parametrize("exits", [[0], [None, 0]])
def test_startup_reaped_zero_exit_is_not_independent_capture(tmp_path, monkeypatch, exits):
    monkeypatch.setattr(
        inputs, "_process_snapshot", lambda pid: (_startup_identity(), b"/python\0")
    )
    with pytest.raises(ValueError, match="process exited"):
        inputs.wait_declared_process(
            _StartupProcess(exits), ["/python"], 501, tmp_path / "rejected.json"
        )


def test_startup_missing_proc_fails_closed(tmp_path, monkeypatch):
    def missing(pid):
        raise FileNotFoundError("process gone")

    monkeypatch.setattr(inputs, "_process_snapshot", missing)
    with pytest.raises(ValueError, match="disappeared"):
        inputs.wait_declared_process(
            _StartupProcess(), ["/python"], 501, tmp_path / "rejected.json"
        )


@pytest.mark.parametrize("state", ["Z", "X"])
def test_kernel_snapshot_refuses_dead_process(tmp_path, state):
    proc = tmp_path / "123"
    proc.mkdir()
    (proc / "stat").write_text("123 (name with spaces) " + state + " " + "0 " * 18 + "987")
    (proc / "status").write_text("Uid:\t501\t501\t501\t501\n")
    (proc / "cmdline").write_bytes(b"/python\0")
    with pytest.raises(ValueError, match="malformed or dead"):
        inputs._process_snapshot(123, tmp_path)


def test_kernel_snapshot_reads_real_uid_and_ticks(tmp_path):
    proc = tmp_path / "123"
    proc.mkdir()
    (proc / "stat").write_text("123 (name with spaces) S " + "0 " * 18 + "987")
    (proc / "status").write_text("Uid:\t501\t501\t501\t501\n")
    (proc / "cmdline").write_bytes(b"/python\0")
    identity, raw = inputs._process_snapshot(123, tmp_path)
    assert identity == _startup_identity() and raw == b"/python\0"


@pytest.mark.parametrize("command", ["/python", [], ["/python", "bad\0argument"]])
def test_startup_invalid_declaration_rejected_before_proc(tmp_path, monkeypatch, command):
    monkeypatch.setattr(
        inputs, "_process_snapshot", lambda pid: pytest.fail("invalid reached proc")
    )
    with pytest.raises(ValueError, match="invalid declared"):
        inputs.wait_declared_process(_StartupProcess(), command, 501, tmp_path / "absent.json")
    assert not (tmp_path / "absent.json").exists()


def test_startup_matching_argv_after_read_consumed_budget_is_rejected(tmp_path, monkeypatch):
    clock = iter([1.0, 6.001])
    monkeypatch.setattr(inputs.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(
        inputs, "_process_snapshot", lambda pid: (_startup_identity(), b"/python\0")
    )
    path = tmp_path / "rejected.json"
    with pytest.raises(ValueError, match="deadline exhausted"):
        inputs.wait_declared_process(_StartupProcess(), ["/python"], 501, path)
    value = json.loads(path.read_bytes())
    assert value["outcome"] == "rejected"
    assert value["samples"][-1]["matches_declared"] is True


@pytest.mark.parametrize(("state", "ticks"), [("?", 987), ("S", 0), ("R", -1)])
def test_kernel_snapshot_refuses_unknown_state_or_nonpositive_ticks(tmp_path, state, ticks):
    proc = tmp_path / "123"
    proc.mkdir()
    (proc / "stat").write_text("123 (name) " + state + " " + "0 " * 18 + str(ticks))
    (proc / "status").write_text("Uid:\t501\t501\t501\t501\n")
    (proc / "cmdline").write_bytes(b"/python\0")
    with pytest.raises(ValueError, match="malformed or dead"):
        inputs._process_snapshot(123, tmp_path)


@pytest.mark.parametrize("state", ["R", "S", "D", "T", "t", "W", "K", "P", "I"])
def test_kernel_snapshot_accepts_only_documented_live_states(tmp_path, state):
    proc = tmp_path / "123"
    proc.mkdir()
    (proc / "stat").write_text("123 (name) " + state + " " + "0 " * 18 + "987")
    (proc / "status").write_text("Uid:\t501\t501\t501\t501\n")
    (proc / "cmdline").write_bytes(b"/python\0")
    assert inputs._process_snapshot(123, tmp_path) == (_startup_identity(), b"/python\0")


def test_parent_startup_receipt_remains_0600_under_restrictive_umask(tmp_path, monkeypatch):
    monkeypatch.setattr(
        inputs, "_process_snapshot", lambda pid: (_startup_identity(), b"/python\0")
    )
    path = tmp_path / "receipt.json"
    previous = inputs.os.umask(0o777)
    try:
        inputs.wait_declared_process(_StartupProcess(), ["/python"], 501, path)
    finally:
        inputs.os.umask(previous)
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_bytes())["outcome"] == "matched_declared"
