"""Authenticated framing, bounded extraction and secret-safe failure regressions."""

import base64
import copy
import json
import os
import signal
import subprocess
import sys
import zlib

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tools import pr9_capacity_transport as transport


@pytest.fixture
def package(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    members = []
    for name, role, raw in [
        ("one", "native_archive", b"synthetic database-shaped fixture\n" * 50),
        ("plan", "formal_plan", b"FORMAL_CAPACITY_FOLLOWUP_PLAN"),
    ]:
        (source / name).write_bytes(raw)
        members.append(
            {
                "role": role,
                "original_path": name,
                "path": "/e/" + name,
                "sha256": transport.digest(raw),
            }
        )
    binding = {
        "members": members,
        "classification": transport.CLASSIFICATION,
        "actual_installed_business_members": [
            {
                "path": "/e/source-venv/lib/python3.11/site-packages/agent_guard/__init__.py",
                "sha256": "0" * 64,
            }
        ],
        "journal_difference": {"condition": "if all(...) -> if grants and all(...)"},
        "native_rejection": {
            "exception": "TaskBundleError",
            "message": "complete material capacity exceeded",
        },
    }
    (source / "binding.json").write_text(json.dumps(binding))
    bundle = tmp_path / "bundle"
    transport.pack(source / "binding.json", source, bundle, "synthetic")
    return source, bundle, tmp_path / "decoded"


def read_documents(bundle):
    return (
        json.loads((bundle / "source-manifest.json").read_text()),
        json.loads((bundle / "transport.json").read_text()),
    )


def decrypt(package, **kwargs):
    _, bundle, output = package
    return transport.unpack(
        bundle / "source-manifest.json",
        bundle / "transport.json",
        bundle / "ciphertext.aesgcm",
        output,
        **({"key_file": bundle / "key.bin"} | kwargs),
    )


def replace_documents(bundle, manifest, metadata, *, compressed=None):
    """Own-key fixture corruption reaches checks beyond successful AEAD authentication."""
    old = json.loads((bundle / "transport.json").read_text())
    key = (bundle / "key.bin").read_bytes()
    if compressed is None:
        compressed = AESGCM(key).decrypt(
            bytes.fromhex(old["nonce_hex"]),
            (bundle / "ciphertext.aesgcm").read_bytes(),
            transport.aad(old),
        )
    metadata["manifest_sha256"] = transport.digest(transport.canonical(manifest))
    metadata["gzip_bytes"] = len(compressed)
    metadata["gzip_sha256"] = transport.digest(compressed)
    encoded = AESGCM(key).encrypt(
        bytes.fromhex(metadata["nonce_hex"]), compressed, transport.aad(metadata)
    )
    metadata["cipher_bytes"] = len(encoded)
    metadata["cipher_sha256"] = transport.digest(encoded)
    (bundle / "source-manifest.json").write_bytes(transport.canonical(manifest))
    (bundle / "transport.json").write_bytes(transport.canonical(metadata))
    (bundle / "ciphertext.aesgcm").write_bytes(encoded)


def test_roundtrip_exact_files_and_private_modes(package):
    source, bundle, output = package
    ready = decrypt(package)
    assert ready == output / "historical-root"
    assert (ready / "one").read_bytes() == (source / "one").read_bytes()
    assert (ready / "plan").read_bytes() == (source / "plan").read_bytes()
    binding = json.loads((ready / "source-binding.json").read_text())
    manifest, metadata = read_documents(bundle)
    assert binding == transport.rebuild_binding(manifest)
    assert (ready / "source-binding.json").read_bytes() == transport.canonical(binding) + b"\n"
    assert binding["transport_manifest_sha256"] == metadata["manifest_sha256"]
    assert binding["members"][0]["original_path"] == "one"
    assert sorted(str(p.relative_to(ready)) for p in ready.rglob("*") if p.is_file()) == [
        "one",
        "plan",
        "source-binding.json",
    ]
    for root in (bundle, output):
        for path in [root, *root.rglob("*")]:
            assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)
    assert not (bundle / "compressed.private").exists()


@pytest.mark.parametrize(
    "damage",
    ["key", "nonce", "aad", "bit", "tag", "truncated", "manifest", "missing-key", "missing-asset"],
)
def test_authentication_or_source_failure_releases_nothing(package, damage):
    _, bundle, output = package
    manifest, metadata = read_documents(bundle)
    if damage == "key":
        (bundle / "key.bin").write_bytes(os.urandom(32))
    elif damage == "nonce":
        metadata["nonce_hex"] = "00" * 12
    elif damage == "aad":
        metadata["framed_sha256"] = "0" * 64
    elif damage in ("bit", "tag", "truncated"):
        raw = bytearray((bundle / "ciphertext.aesgcm").read_bytes())
        raw[0] ^= 1
        if damage == "truncated":
            raw = raw[:-1]
        (bundle / "ciphertext.aesgcm").write_bytes(raw)
        if damage == "tag":
            metadata["cipher_sha256"] = transport.digest(raw)
    elif damage == "manifest":
        manifest["members"][0]["sha256"] = "f" * 64
        (bundle / "source-manifest.json").write_text(json.dumps(manifest))
    elif damage == "missing-key":
        (bundle / "key.bin").unlink()
    elif damage == "missing-asset":
        (bundle / "ciphertext.aesgcm").unlink()
    (bundle / "transport.json").write_text(json.dumps(metadata))
    with pytest.raises((ValueError, InvalidTag, FileNotFoundError)):
        decrypt(package)
    assert not output.exists()


@pytest.mark.parametrize(
    "bad_path", ["../escape", "/absolute", "a/../escape", ".", "a\\b", "source-binding.json/child"]
)
def test_manifest_path_escape_refused(package, bad_path):
    _, bundle, output = package
    manifest, _ = read_documents(bundle)
    manifest["members"][0]["path"] = bad_path
    (bundle / "source-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        decrypt(package)
    assert not output.exists()


@pytest.mark.parametrize("damage", ["duplicate", "extra", "length", "sha", "link"])
def test_invalid_member_manifest_refused(package, damage):
    _, bundle, output = package
    manifest, _ = read_documents(bundle)
    if damage == "duplicate":
        manifest["members"].append(copy.deepcopy(manifest["members"][0]))
    elif damage == "extra":
        manifest["members"].append(
            {"path": "extra", "role": "native_archive", "bytes": 1, "sha256": "0" * 64}
        )
    elif damage == "link":
        manifest["members"][0]["type"] = "symlink"
    elif damage == "length":
        manifest["members"][0]["bytes"] = transport.MAX_PLAIN + 1
    else:
        manifest["members"][0]["sha256"] = "bad"
    (bundle / "source-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        decrypt(package)
    assert not output.exists()


@pytest.mark.parametrize(
    "damage",
    [
        "member-sha",
        "plaintext-sha",
        "extra-gzip",
        "gzip-tail",
        "overlong",
        "truncated-gzip",
        "gzip-sha",
    ],
)
def test_authenticated_invalid_plaintext_cleans_partial_tree(package, damage):
    source, bundle, output = package
    manifest, metadata = read_documents(bundle)
    key = (bundle / "key.bin").read_bytes()
    compressed = AESGCM(key).decrypt(
        bytes.fromhex(metadata["nonce_hex"]),
        (bundle / "ciphertext.aesgcm").read_bytes(),
        transport.aad(metadata),
    )
    plain = zlib.decompress(compressed, 31)
    if damage == "member-sha":
        manifest["members"][0]["sha256"] = "0" * 64
        plain = (
            transport.MAGIC
            + bytes.fromhex(transport.digest(transport.canonical(manifest)))
            + plain[len(transport.MAGIC) + 32 :]
        )
        metadata["framed_sha256"] = transport.digest(plain)
        compressor = zlib.compressobj(6, zlib.DEFLATED, 31)
        compressed = compressor.compress(plain) + compressor.flush()
    elif damage == "plaintext-sha":
        metadata["framed_sha256"] = "0" * 64
    elif damage == "extra-gzip":
        compressor = zlib.compressobj(6, zlib.DEFLATED, 31)
        compressed += compressor.compress(b"extra") + compressor.flush()
    elif damage == "gzip-tail":
        compressed += b"unauthorized tail"
    elif damage == "overlong":
        compressor = zlib.compressobj(6, zlib.DEFLATED, 31)
        compressed = compressor.compress(plain + b"extra member bytes") + compressor.flush()
    elif damage == "truncated-gzip":
        compressed = compressed[:-8]
    replace_documents(bundle, manifest, metadata, compressed=compressed)
    if damage == "gzip-sha":
        metadata["gzip_sha256"] = "0" * 64
        encoded = AESGCM(key).encrypt(
            bytes.fromhex(metadata["nonce_hex"]), compressed, transport.aad(metadata)
        )
        metadata["cipher_sha256"] = transport.digest(encoded)
        (bundle / "transport.json").write_text(json.dumps(metadata))
        (bundle / "ciphertext.aesgcm").write_bytes(encoded)
    with pytest.raises(ValueError):
        decrypt(package)
    assert not output.exists()
    assert (source / "one").exists()


def test_symlink_hardlink_and_existing_destination_refused(package, tmp_path):
    source, bundle, output = package
    (source / "link").symlink_to(source / "one")
    with pytest.raises(ValueError, match="symbolic"):
        transport.regular(source / "link")
    os.link(source / "one", source / "hardlink")
    with pytest.raises(ValueError, match="regular"):
        transport.regular(source / "one")
    output.mkdir()
    (output / "keep").write_text("other owner's material")
    with pytest.raises(ValueError, match="fresh"):
        decrypt(package)
    assert (output / "keep").read_text() == "other owner's material"
    assert (bundle / "key.bin").exists()


def test_key_env_consumed_without_publication(package, monkeypatch):
    _, bundle, output = package
    monkeypatch.setenv(
        "AG32_TEST_TRANSPORT_KEY", base64.b64encode((bundle / "key.bin").read_bytes()).decode()
    )
    ready = transport.unpack(
        bundle / "source-manifest.json",
        bundle / "transport.json",
        bundle / "ciphertext.aesgcm",
        output,
        key_env="AG32_TEST_TRANSPORT_KEY",
    )
    assert ready.is_dir()
    assert "AG32_TEST_TRANSPORT_KEY" not in os.environ
    assert not any("key" in p.name for p in output.rglob("*"))


def test_keyword_dsn_audit_detects_logs_without_emitting_values(tmp_path):
    from tools.pr9_capacity_inputs import audit_archive

    archive, report = tmp_path / "archive.json", tmp_path / "audit.json"
    row = {"trace": "dbname=isolated user=fixture password=never-print-this host=test-service"}
    archive.write_text(json.dumps({"state": {"synthetic": {"logs": [[json.dumps(row)]]}}}))
    value = audit_archive(archive, report, 1)
    assert value["sensitive_indicators"]["libpq_keyword_dsn"] == 1
    assert "never-print-this" not in report.read_text()
    assert value["clearance"].startswith("BLOCKED")


def test_missing_env_and_unsafe_key_permissions_fail(package, monkeypatch):
    _, bundle, output = package
    monkeypatch.delenv("AG32_MISSING_TEST_KEY", raising=False)
    with pytest.raises(ValueError, match="unavailable"):
        transport.unpack(
            bundle / "source-manifest.json",
            bundle / "transport.json",
            bundle / "ciphertext.aesgcm",
            output,
            key_env="AG32_MISSING_TEST_KEY",
        )
    assert not output.exists()
    (bundle / "key.bin").chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        decrypt(package)
    assert not output.exists()


def test_pack_crypto_failure_cleans_own_partial_and_preserves_source(package, monkeypatch):
    source, bundle, _ = package
    failed = bundle.parent / "failed-pack"

    def unavailable_crypto(*args):
        raise ValueError("synthetic crypto failure")

    monkeypatch.setattr(transport, "AESGCM", unavailable_crypto)
    with pytest.raises(ValueError, match="synthetic crypto"):
        transport.pack(source / "binding.json", source, failed, "synthetic")
    assert not failed.exists()
    assert (source / "one").exists()
    assert (bundle / "key.bin").exists()


def test_duplicate_json_field_is_refused(package):
    _, bundle, output = package
    raw = (bundle / "source-manifest.json").read_text()
    (bundle / "source-manifest.json").write_text('{"format":"duplicate",' + raw[1:])
    with pytest.raises(ValueError, match="duplicate JSON"):
        decrypt(package)
    assert not output.exists()


def test_cli_failure_output_is_allowlisted_not_raw_trace(package, monkeypatch):
    _, bundle, output = package
    monkeypatch.delenv("AG32_MISSING_TEST_KEY", raising=False)
    result = subprocess.run(
        [
            sys.executable,
            transport.__file__,
            "unpack",
            "--manifest",
            str(bundle / "source-manifest.json"),
            "--metadata",
            str(bundle / "transport.json"),
            "--ciphertext",
            str(bundle / "ciphertext.aesgcm"),
            "--output-root",
            str(output),
            "--key-env",
            "AG32_MISSING_TEST_KEY",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "capacity transport failed; no input was released\n"
    assert not output.exists()


def test_sigterm_cleans_pack_partial_and_sanitizes_cli(package, monkeypatch, capsys):
    source, bundle, _ = package
    failed = bundle.parent / "cancelled-pack"

    def interrupt_crypto(*args):
        signal.raise_signal(signal.SIGTERM)

    monkeypatch.setattr(transport, "AESGCM", interrupt_crypto)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "transport",
            "pack",
            "--historical-binding",
            str(source / "binding.json"),
            "--historical-root",
            str(source),
            "--output-root",
            str(failed),
            "--dataset-id",
            "synthetic",
        ],
    )
    assert transport.main() == 1
    assert not failed.exists()
    assert (source / "one").exists()
    assert capsys.readouterr().err == "capacity transport failed; no input was released\n"
