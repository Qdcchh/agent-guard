"""Private relocation boundaries without historical secrets or database services."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools import pr9_capacity_inputs as inputs
from tools import pr9_capacity_transport as transport
from tools.pr9_capacity_inputs import audit_archive, checked, prepare, sha256


def small_fixture(tmp_path):
    historical = tmp_path / "historical"
    historical.mkdir()
    (historical / "original.json").write_text('{"real_fixture": true}')
    (historical / "plan.md").write_text("FORMAL_CAPACITY_FOLLOWUP_PLAN")
    installed = tmp_path / "installed"
    (installed / "agent_guard").mkdir(parents=True)
    (installed / "agent_guard/__init__.py").write_text('"""new current installation"""')
    members = [
        {
            "role": role,
            "path": "/e/" + name,
            "original_path": name,
            "sha256": sha256(historical / name),
        }
        for role, name in [("native_archive", "original.json"), ("formal_plan", "plan.md")]
    ]
    binding = historical / "binding.json"
    binding.write_text(
        json.dumps(
            {
                "classification": "HISTORICAL_ONLY",
                "members": members,
                "actual_installed_business_members": [
                    {"path": "/old/site-packages/agent_guard/__init__.py", "sha256": "0" * 64}
                ],
            }
        )
    )
    return historical, installed, binding


def test_relocation_preserves_bytes_and_maps_nested_paths(tmp_path, monkeypatch):
    historical, installed, binding = small_fixture(tmp_path)
    monkeypatch.setattr(transport, "HISTORICAL_BINDING_SHA256", sha256(binding))
    output = tmp_path / "new"
    report = prepare(binding, historical, installed, output, "/capacity/inputs", "/runtime/site")
    host = json.loads((output / "host-binding.json").read_text())
    container = json.loads((output / "container-binding.json").read_text())
    assert report["status"] == "PENDING_CURRENT_SOURCE_SEMANTIC_REVIEW"
    assert not report["installed_comparison"][0]["identical"]
    assert report["historical_binding_sha256"] == report["received_binding_sha256"]
    assert report["transport_manifest_sha256"] is None
    assert (
        Path(host["members"][0]["path"]).read_bytes() == (historical / "original.json").read_bytes()
    )
    assert container["members"][0]["path"] == "/capacity/inputs/originals/0/original.json"
    assert container["formal_plan"] == "/capacity/inputs/originals/1/plan.md"
    assert host["actual_installed_business_members"][0]["path"] == str(
        installed / "agent_guard/__init__.py"
    )
    for path in [output, *output.rglob("*")]:
        assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)


@pytest.mark.parametrize("relative", ["../secret", "/absolute"])
def test_path_traversal_refused(tmp_path, relative):
    with pytest.raises(ValueError, match="escapes"):
        checked(tmp_path, relative)


def test_symlink_refused(tmp_path):
    (tmp_path / "real").write_text("material")
    (tmp_path / "link").symlink_to(tmp_path / "real")
    with pytest.raises(ValueError, match="symbolic"):
        checked(tmp_path, "link")


def test_digest_failure_does_not_create_output(tmp_path, monkeypatch):
    historical, installed, binding = small_fixture(tmp_path)
    monkeypatch.setattr(transport, "HISTORICAL_BINDING_SHA256", sha256(binding))
    (historical / "original.json").write_text("changed")
    with pytest.raises(ValueError, match="digest"):
        prepare(binding, historical, installed, tmp_path / "new", "/inputs", "/site")
    assert not (tmp_path / "new").exists()


@pytest.fixture
def authenticated_inputs(tmp_path, monkeypatch):
    historical, installed, binding = small_fixture(tmp_path)
    value = json.loads(binding.read_text())
    value.update(
        classification=transport.CLASSIFICATION,
        journal_difference={"condition": "if all(...) -> if grants and all(...)"},
        native_rejection={
            "exception": "TaskBundleError",
            "message": "complete material capacity exceeded",
        },
    )
    value["actual_installed_business_members"][0]["path"] = (
        "/e/source-venv/lib/python3.11/site-packages/agent_guard/__init__.py"
    )
    binding.write_text(json.dumps(value))
    bundle = tmp_path / "bundle"
    transport.pack(binding, historical, bundle, "synthetic")
    decoded = transport.unpack(
        bundle / "source-manifest.json",
        bundle / "transport.json",
        bundle / "ciphertext.aesgcm",
        tmp_path / "decoded",
        key_file=bundle / "key.bin",
    )
    manifest = transport.load_json(bundle / "source-manifest.json")
    # Explicit synthetic trust anchors, never a production bypass or fixture fallback.
    monkeypatch.setattr(inputs, "PUBLIC_INPUT_ROOT", bundle)
    monkeypatch.setattr(
        inputs, "PUBLIC_MANIFEST_SHA256", transport.digest(transport.canonical(manifest))
    )
    monkeypatch.setattr(inputs, "PUBLIC_TRANSPORT_SHA256", sha256(bundle / "transport.json"))
    monkeypatch.setattr(transport, "HISTORICAL_BINDING_SHA256", sha256(binding))
    return decoded, installed, bundle


def test_authenticated_reconstruction_retains_distinct_identity_layers(
    authenticated_inputs, tmp_path
):
    decoded, installed, bundle = authenticated_inputs
    binding = decoded / "source-binding.json"
    report = prepare(binding, decoded, installed, tmp_path / "ready", "/capacity/inputs", "/site")
    assert report["historical_binding_sha256"] == transport.HISTORICAL_BINDING_SHA256
    assert report["received_binding_sha256"] == sha256(binding)
    assert report["received_binding_sha256"] != report["historical_binding_sha256"]
    assert report["transport_manifest_sha256"] == inputs.PUBLIC_MANIFEST_SHA256
    assert (tmp_path / "ready/originals/0/original.json").read_bytes() == (
        decoded / "original.json"
    ).read_bytes()
    assert (
        transport.load_json(bundle / "source-manifest.json")["source_binding_sha256"]
        == (report["historical_binding_sha256"])
    )


@pytest.mark.parametrize(
    "damage",
    [
        "original-missing",
        "manifest-missing",
        "both-missing",
        "original-forged",
        "manifest-forged",
        "classification",
        "installed",
        "formal-plan",
        "member",
        "extra-field",
        "whitespace",
        "member-bytes",
        "public-manifest",
        "public-transport",
        "metadata-crosscheck",
    ],
)
def test_reconstructed_input_damage_fails_before_output(
    authenticated_inputs, tmp_path, monkeypatch, damage
):
    decoded, installed, bundle = authenticated_inputs
    path = decoded / "source-binding.json"
    value = transport.load_json(path)
    if damage in ("original-missing", "both-missing"):
        del value["original_binding_sha256"]
    if damage in ("manifest-missing", "both-missing"):
        del value["transport_manifest_sha256"]
    if damage == "original-forged":
        value["original_binding_sha256"] = "f" * 64
    if damage == "manifest-forged":
        value["transport_manifest_sha256"] = "f" * 64
    if damage == "classification":
        value["classification"] = "FORGED"
    if damage == "installed":
        value["actual_installed_business_members"][0]["sha256"] = "f" * 64
    if damage == "formal-plan":
        value["formal_plan"] = "original.json"
    if damage == "member":
        value["members"][0]["sha256"] = "f" * 64
    if damage == "extra-field":
        value["unknown"] = True
    path.write_bytes(transport.canonical(value) + b"\n")
    if damage == "whitespace":
        path.write_text(json.dumps(value, indent=2))
    if damage == "member-bytes":
        (decoded / "original.json").write_bytes(b"changed")
    if damage == "public-manifest":
        manifest = transport.load_json(bundle / "source-manifest.json")
        manifest["members"][0]["sha256"] = "f" * 64
        (bundle / "source-manifest.json").write_bytes(transport.canonical(manifest))
    if damage in ("public-transport", "metadata-crosscheck"):
        metadata = transport.load_json(bundle / "transport.json")
        metadata["manifest_sha256"] = "f" * 64
        (bundle / "transport.json").write_bytes(transport.canonical(metadata))
        if damage == "metadata-crosscheck":
            monkeypatch.setattr(
                inputs, "PUBLIC_TRANSPORT_SHA256", sha256(bundle / "transport.json")
            )
    output = tmp_path / "refused"
    with pytest.raises(ValueError):
        prepare(path, decoded, installed, output, "/capacity/inputs", "/site")
    assert not output.exists()


@pytest.mark.parametrize("module", [False, True])
def test_cli_imports_without_pythonpath(module):
    repo = Path(__file__).resolve().parents[2]
    argv = (
        [sys.executable, "-m", "tools.pr9_capacity_inputs"]
        if module
        else [sys.executable, str(repo / "tools/pr9_capacity_inputs.py")]
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(argv + ["--help"], cwd=repo, env=env, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert b"prepare" in result.stdout


def test_audit_reports_expiration_and_credential_uncertainty_without_values(tmp_path):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    token = ".".join(
        [
            encode({"typ": "JWT"}),
            encode({"exp": 10, "client_secret": "never-emit-this"}),
            "abcdefgh",
        ]
    )
    archive = tmp_path / "archive.json"
    row = {"token_bytes": "\\x" + token.encode().hex()}
    archive.write_text(json.dumps({"state": {"gateway": {"synthetic": [[json.dumps(row)]]}}}))
    output = tmp_path / "audit.json"
    report = audit_archive(archive, output, 20)
    assert report["jwt_distinct_decoded"]["JWT"]["expired"] == 1
    assert report["sensitive_indicators"]["nonempty_sensitive_named_field:client_secret"] == 1
    assert "never-emit-this" not in output.read_text()
    assert token not in output.read_text()
    assert report["clearance"].startswith("BLOCKED")
    assert os.stat(output).st_mode & 0o777 == 0o600


def test_consumer_refuses_pythonpath_shadowing(tmp_path, monkeypatch):
    from tools.pr9_capacity_inputs import bind_installed

    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    with pytest.raises(ValueError, match="without PYTHONPATH"):
        bind_installed(tmp_path / "absent", tmp_path, tmp_path, tmp_path / "new")


def test_output_parent_symlink_refused(tmp_path):
    from tools.pr9_capacity_inputs import write_private

    (tmp_path / "private").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "private", target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic"):
        write_private(tmp_path / "link" / "secret.json", {"private": "do-not-write"})
