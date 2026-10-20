"""Fail-closed media/provenance/secret/path guards for complete candidate packaging."""

import base64
import json
import zipfile

import pytest

from tools.cosm2_full_handoff import (
    Plan,
    inside,
    scan_bytes,
    validate_capture,
    validate_old_bundle,
    validate_redacted_history,
    validate_run,
)


def test_paths_cannot_escape_or_follow_symlinks(tmp_path):
    (tmp_path / "actual").write_text("public")
    (tmp_path / "link").symlink_to(tmp_path / "actual")
    for path in (tmp_path / "link", tmp_path / "../outside", tmp_path.parent / "outside"):
        with pytest.raises(ValueError):
            inside(path, tmp_path)


def test_public_evidence_scan_refuses_actual_credentials_without_echoing():
    token = b".".join(
        base64.urlsafe_b64encode(value).rstrip(b"=")
        for value in (b'{"alg":"ES256","typ":"JWT"}', b'{"subject":"synthetic-fixture"}', b"s" * 64)
    )
    for content in (token, b"-----BEGIN PRIVATE KEY-----", b"password=the-actual-fixture-secret"):
        with pytest.raises(ValueError) as error:
            scan_bytes(content, (b"the-actual-fixture-secret",))
        assert "actual-fixture-secret" not in str(error.value)
    scan_bytes(b"Document the JWS regex and password=placeholder; [REDACTED_SYNTHETIC_TOKEN]")


def test_required_failed_evidence_is_not_quietly_dropped(tmp_path):
    source = tmp_path / "failed.log"
    source.write_text("actual-sensitive-fixture-password")
    plan = Plan(tmp_path, (b"actual-sensitive-fixture-password",))
    with pytest.raises(ValueError):
        plan.add(source, "history/failed.log", kind="failure", status="FAILED")
    assert plan.entries == {}


def test_copy_preserves_bytes_checks_archive_and_refuses_existing_output(tmp_path):
    source = tmp_path / "failed.log"
    source.write_bytes(b"18 passed, 1 failed\nREDACTED\n")
    plan = Plan(tmp_path)
    plan.add(source, "history/failed.log", kind="failure", status="FAILED")
    output = tmp_path / "candidate"
    manifest = plan.copy(output, {"status": "CANDIDATE_NOT_ACCEPTED"})
    assert (output / "history/failed.log").read_bytes() == source.read_bytes()
    assert manifest["files"][0]["status"] == "FAILED"
    with zipfile.ZipFile(output.with_suffix(".zip")) as archive:
        assert archive.testzip() is None
        assert archive.read("history/failed.log") == source.read_bytes()
    with pytest.raises(ValueError):
        plan.copy(output, {})


@pytest.mark.parametrize("mutation", ["partial", "foreign", "nowait", "native", "short"])
def test_capture_cannot_pass_from_partial_foreign_or_short_evidence(
    tmp_path, monkeypatch, mutation
):
    from tools.cosm2_full_handoff import digest

    run = "11111111-1111-4111-8111-111111111111"
    captures = []
    for name in ("overview.png", "s1.png", "s3.png", "s6.png", "cosign-live.png"):
        path = tmp_path / name
        path.write_bytes(b"synthetic image fixture")
        captures.append(dict(file=name, sha256=digest(path)))
    manifest = dict(
        schema_version=1,
        kind="actual-cosm2-live-and-replay-tour",
        page_errors=[],
        cosign_live=dict(status="PASSED", source="current-run", run_id=run),
        captures=captures,
    )
    terminal = dict(
        job=dict(
            native_exit=0,
            actual_wait=True,
            result=dict(run_id=run),
            status="success",
            action="cosm2-run",
        ),
        cosign=dict(run_id=run, source="current-run", passed=True),
    )
    if mutation == "partial":
        manifest["cosign_live"]["status"] = "BLOCKED"
    if mutation == "foreign":
        terminal["cosign"]["run_id"] = "foreign-run"
    if mutation == "nowait":
        terminal["job"]["actual_wait"] = False
    if mutation == "native":
        terminal["job"]["native_exit"] = 1
    (tmp_path / "capture-manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "live-terminal-state.json").write_text(json.dumps(terminal))
    media = dict(
        schema="cosm2-media-v1",
        run_id=run,
        capture_manifest=dict(sha256=digest(tmp_path / "capture-manifest.json")),
    )
    for kind in ("webm", "mp4"):
        path = tmp_path / ("video." + kind)
        path.write_bytes(b"synthetic video fixture")
        media[kind] = dict(
            path=path.name,
            sha256=digest(path),
            duration_seconds=179 if mutation == "short" else 181,
        )
    manifest["video"] = dict(file="video.webm", sha256=media["webm"]["sha256"])
    (tmp_path / "capture-manifest.json").write_text(json.dumps(manifest))
    media["capture_manifest"]["sha256"] = digest(tmp_path / "capture-manifest.json")
    (tmp_path / "media-metadata.json").write_text(json.dumps(media))
    monkeypatch.setattr("tools.cosm2_full_handoff.probe_video", lambda path: {})
    with pytest.raises(ValueError):
        validate_capture(tmp_path, run, root=tmp_path)


def test_redacted_failure_history_requires_original_unavailability_disclosure(tmp_path):
    (tmp_path / "controller").mkdir()
    (tmp_path / "domains").mkdir()
    (tmp_path / "controller/public-log-redactions.json").write_text(
        json.dumps(dict(notice="all evidence preserved verbatim"))
    )
    (tmp_path / "domains/implementation.md").write_text("All passed")
    with pytest.raises(ValueError):
        validate_redacted_history(tmp_path)


def test_foreign_or_incomplete_B7_result_rejected(tmp_path):
    run = "11111111-1111-4111-8111-111111111111"
    (tmp_path / "result.json").write_text(json.dumps(dict(run_id="foreign", passed=True)))
    with pytest.raises(ValueError):
        validate_run(tmp_path, run)


def test_prior_zip_requires_actual_failed_samples(tmp_path):
    path = tmp_path / "old.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name in ("raw.csv", "warmup.csv", "summary.json"):
            archive.writestr("historical-failed-run01/" + name, "status\nOK\n")
    with pytest.raises(ValueError):
        validate_old_bundle(path)


def test_actual_ffprobe_short_recording_rejected(monkeypatch):
    from types import SimpleNamespace

    from tools.cosm2_full_handoff import probe_video

    result = SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            dict(format=dict(duration="179.9"), streams=[dict(codec_type="video")])
        ).encode(),
    )
    monkeypatch.setattr("tools.cosm2_full_handoff.subprocess.run", lambda *args, **kwargs: result)
    with pytest.raises(ValueError, match="180 seconds"):
        probe_video("synthetic.webm")


def test_excluded_operator_env_is_explicitly_listed(tmp_path):
    (tmp_path / "runner.env").write_text("DATABASE=private-value")
    (tmp_path / "public.log").write_text("public failure count")
    plan = Plan(tmp_path)
    plan.tree(tmp_path, "history", status="HISTORICAL")
    assert list(plan.entries) == ["history/public.log"]
    assert plan.excluded_files[0]["source"] == "runner.env"
