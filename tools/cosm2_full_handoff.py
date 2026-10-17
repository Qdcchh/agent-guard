"""Build an evidence-checked complete COSM2 candidate bundle, never acceptance."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID

from experiments.cosm2_bench.plot import validate as validate_benchmark

REPO = Path(__file__).resolve().parents[1]
STAGE = Path("artifacts/cosm2-full-20261017")
PUBLIC_SUFFIXES = {
    ".log",
    ".xml",
    ".exit",
    ".json",
    ".md",
    ".txt",
    ".png",
    ".webm",
    ".mp4",
    ".pdf",
    ".csv",
}
SENSITIVE_PARTS = {"private", "private-originals", "secrets", "exec", "authz", ".git"}
JWS = re.compile(
    rb"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{16,4096})\.([A-Za-z0-9_-]{16,65536})\.([A-Za-z0-9_-]{32,4096})(?![A-Za-z0-9_-])"
)
PRIVATE_PEM = re.compile(rb"-----BEGIN (?:[A-Z0-9 ]* )?PRIVATE KEY-----")


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def inside(path, root=REPO):
    path, root = Path(path).absolute(), Path(root).absolute()
    if ".." in path.parts:
        raise ValueError("parent traversal refused")
    path.relative_to(root)
    path.resolve().relative_to(root.resolve())
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("symlink refused")
    return path


def is_sensitive(path):
    path = Path(path)
    return (
        any(part.lower() in SENSITIVE_PARTS for part in path.parts)
        or path.name.lower().endswith(".env")
        or ".env." in path.name.lower()
        or path.name.lower() == "share.json"
        or "dsn" in path.name.lower()
        or "privkey" in path.name.lower()
        or "private-key" in path.name.lower()
        or path.suffix.lower() in {".key", ".pem"}
    )


def strict_json(path):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    return json.loads(Path(path).read_text(), object_pairs_hook=pairs)


def secret_values(env_file=None):
    """Read private scan material without copying, printing, or persisting its values."""
    values = set()
    sources = list(os.environ.values())
    if env_file is not None:
        for line in Path(env_file).read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                sources.append(line.split("=", 1)[1].strip().strip("\"'"))
    for value in sources:
        if value.startswith(("postgresql://", "postgres://")):
            password = urlsplit(value).password
            if password:
                values.add(unquote(password).encode())
                values.add(value.encode())
        elif "password=" in value:
            match = re.search(r"password=(?:'([^']+)'|([^\s]+))", value)
            if match:
                values.add((match.group(1) or match.group(2)).encode())
    return tuple(v for v in values if len(v) >= 8)


def scan_bytes(data, secrets=()):
    real_jws = False
    for match in JWS.finditer(data):
        try:
            decoded = [
                json.loads(base64.urlsafe_b64decode(part + b"=" * ((-len(part)) % 4)))
                for part in match.groups()[:2]
            ]
            real_jws = (
                isinstance(decoded[0], dict)
                and "alg" in decoded[0]
                and isinstance(decoded[1], dict)
            )
        except (ValueError, UnicodeError):
            continue
        if real_jws:
            break
    if real_jws or PRIVATE_PEM.search(data) or any(v in data for v in secrets):
        raise ValueError("public source contains credential material (value withheld)")


def scan_source(path, secrets=()):
    path = Path(path)
    if is_sensitive(path):
        raise ValueError("sensitive source path refused")
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError("historical ZIP CRC failure")
            for item in archive.infolist():
                if item.is_dir():
                    continue
                if (
                    Path(item.filename).is_absolute()
                    or ".." in Path(item.filename).parts
                    or is_sensitive(item.filename)
                ):
                    raise ValueError("unsafe historical ZIP member")
                scan_bytes(archive.read(item), secrets)
    else:
        with path.open("rb") as stream:
            tail = b""
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                scan_bytes(tail + chunk, secrets)
                tail = chunk[-65536:]


def validate_formal_benchmark(path):
    summary = validate_benchmark(path)
    if (
        summary["status"] != "COMPLETE"
        or summary["requested_samples"] != 100
        or summary["warmup"] != 10
        or any(v["n"] != 100 for v in summary["metrics"].values())
    ):
        raise ValueError("complete 100+10 benchmark required")
    return summary


def validate_run(run_dir, run_id):
    if str(UUID(run_id)) != run_id:
        raise ValueError("canonical run UUID required")
    from tools.teacher_demo_server import validate_cosm2_result

    result = strict_json(run_dir / "result.json")
    validate_cosm2_result(result, run_id)
    if (
        result.get("run_id") != run_id
        or result.get("passed") is not True
        or result.get("scheme") != "sm2-2p"
        or result.get("resources_remaining") != 0
        or any(result.get(k) != 1 for k in ("orders", "operations", "approvals"))
    ):
        raise ValueError("same-run real one-order COSM2 result required")
    expected = {
        "cosign-valid-one-order",
        "missing-approval",
        "exec-domain-alone",
        "tampered-amount",
        "revoked-before-cosign",
        "revoked-after-cosign",
    }
    cases = result.get("cases", [])
    if (
        len(cases) != 6
        or {c.get("name") for c in cases} != expected
        or any(c.get("passed") is not True for c in cases)
    ):
        raise ValueError("all six genuine demo cases required")
    matrix = strict_json(run_dir / "negative-matrix.json")
    if (
        matrix.get("run_id") != run_id
        or len(matrix.get("observations", [])) != 12
        or any(item.get("passed") is not True for item in matrix.get("observations", []))
    ):
        raise ValueError("same-run twelve real observations required")
    return result


def probe_video(path):
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("actual ffprobe failed")
    probe = json.loads(completed.stdout)
    duration = float(probe["format"]["duration"])
    if (
        not math.isfinite(duration)
        or duration < 180
        or not any(s.get("codec_type") == "video" for s in probe["streams"])
    ):
        raise ValueError("actual video must contain at least 180 seconds")
    return probe


def validate_redacted_history(stage):
    notice = strict_json(stage / "controller/public-log-redactions.json").get("notice", "")
    domain = (stage / "domains/implementation.md").read_text()
    if not (
        "redact" in notice.lower()
        and "original" in notice.lower()
        and ("unavailable" in notice.lower() or "no unredacted original" in notice.lower())
    ):
        raise ValueError("explicit unavailable redacted-original history disclosure required")
    if (
        "REDACTED failed history" not in domain
        or "no original raw copy or original SHA" not in domain
    ):
        raise ValueError("domain failed-history evidence limitation required")


class Plan:
    def __init__(self, repo=REPO, secrets=()):
        self.repo, self.secrets, self.entries = Path(repo), secrets, {}
        self.excluded_files = []

    def add(self, source, relative, *, kind, status, run_id=None, command="source evidence"):
        source = inside(source, self.repo)
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts or relative.as_posix() in self.entries:
            raise ValueError("unsafe or duplicate output path")
        if not source.is_file():
            raise ValueError("required public source missing")
        scan_source(source, self.secrets)
        self.entries[relative.as_posix()] = dict(
            source=str(source.relative_to(self.repo)),
            file=relative.as_posix(),
            kind=kind,
            status=status,
            run_id=run_id,
            command=command,
            sha256=digest(source),
        )

    def tree(self, source, relative, *, status, kind="evidence", run_id=None):
        source = inside(source, self.repo)
        for path in sorted(source.rglob("*")):
            inside(path, source)
            if is_sensitive(path):
                if path.is_file():
                    self.excluded_files.append(
                        dict(
                            source=str(path.relative_to(self.repo)),
                            reason="sensitive operator/private path; never copied",
                        )
                    )
                    continue
                continue
            if path.is_file() and path.suffix.lower() in PUBLIC_SUFFIXES:
                self.add(
                    path,
                    Path(relative) / path.relative_to(source),
                    kind=kind,
                    status=status,
                    run_id=run_id,
                )

    def copy(self, output, metadata):
        output = inside(output, self.repo)
        if output.exists() or output.with_suffix(".zip").exists():
            raise ValueError("output and ZIP must be new")
        output.mkdir(parents=True, exist_ok=False)
        for item in self.entries.values():
            source, target = (
                inside(self.repo / item["source"], self.repo),
                inside(output / item["file"], output),
            )
            if digest(source) != item["sha256"]:
                raise ValueError("source changed after validation")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if digest(target) != item["sha256"] or digest(source) != item["sha256"]:
                raise ValueError("copy integrity failure")
        metadata = {
            **metadata,
            "files": list(self.entries.values()),
            "excluded_files": self.excluded_files,
        }
        (output / "manifest.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
        )
        table = [
            "# C交付来源表",
            "",
            "完整实施候选；未独立验收，不得写 ACCEPTED。失败和排除数据独立保留。",
            "",
            "| 文件 | 类型/状态 | run_id | SHA256 | 原路径 | 命令/说明 |",
            "|---|---|---|---|---|---|",
        ]
        table += [
            f"| {x['file']} | {x['kind']} / {x['status']} | {x['run_id'] or '-'} | "
            f"{x['sha256']} | {x['source']} | {x['command']} |"
            for x in self.entries.values()
        ]
        (output / "sources").mkdir(exist_ok=True)
        (output / "sources/table.md").write_text("\n".join(table) + "\n")
        archive_path = output.with_suffix(".zip")
        with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(output.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(output))
        with zipfile.ZipFile(archive_path) as archive:
            if archive.testzip() is not None:
                raise ValueError("output ZIP CRC failure")
            for item in archive.infolist():
                if hashlib.sha256(archive.read(item)).hexdigest() != digest(output / item.filename):
                    raise ValueError("ZIP/fullcopy mismatch")
        return metadata


def validate_capture(directory, run_id, *, root=REPO):
    directory = inside(directory, root)
    manifest = strict_json(directory / "capture-manifest.json")
    live = manifest.get("cosign_live", {})
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "actual-cosm2-live-and-replay-tour"
        or manifest.get("page_errors") != []
        or live.get("status") != "PASSED"
        or live.get("source") != "current-run"
        or live.get("run_id") != run_id
    ):
        raise ValueError("successful actual current-run capture required")
    terminal = strict_json(directory / "live-terminal-state.json")
    job, result = terminal.get("job", {}), terminal.get("cosign", {})
    if (
        type(job.get("native_exit")) is not int
        or job.get("native_exit") != 0
        or job.get("status") != "success"
        or job.get("action") != "cosm2-run"
        or job.get("actual_wait") is not True
        or job.get("result", {}).get("run_id") != run_id
        or result.get("run_id") != run_id
        or result.get("source") != "current-run"
        or result.get("passed") is not True
    ):
        raise ValueError("actual native exit/wait/result provenance required")
    seen = set()
    for item in manifest.get("captures", []):
        name = item["file"]
        source = inside(directory / name, directory)
        if not name.endswith(".png") or digest(source) != item["sha256"] or name in seen:
            raise ValueError("capture PNG integrity mismatch")
        seen.add(name)
    if not {"overview.png", "s1.png", "s3.png", "s6.png", "cosign-live.png"} <= seen:
        raise ValueError("required real overview/scenes/current-run captures missing")
    media = strict_json(directory / "media-metadata.json")
    if media.get("run_id") != run_id or media.get("schema") != "cosm2-media-v1":
        raise ValueError("same-run real media metadata required")
    if media["capture_manifest"]["sha256"] != digest(directory / "capture-manifest.json"):
        raise ValueError("media/capture manifest mismatch")
    if (
        manifest.get("video", {}).get("sha256") != media["webm"]["sha256"]
        or manifest["video"].get("file") != Path(media["webm"]["path"]).name
    ):
        raise ValueError("recorded WebM/capture binding mismatch")
    for kind in ("webm", "mp4"):
        item = media[kind]
        source = (
            inside(root / item["path"], root)
            if not Path(item["path"]).is_absolute()
            else inside(item["path"], root)
        )
        source.relative_to(directory)
        if digest(source) != item["sha256"] or float(item["duration_seconds"]) < 180:
            raise ValueError("media SHA/duration mismatch")
        probe_video(source)  # Actual independent ffprobe, not just trusting a stored duration.
    return manifest, media


def validate_figures(figure_root, run_id, bench_run, *, root=REPO):
    index_path = figure_root / "cosm2-figures-sources.json"
    index = strict_json(index_path)
    if (
        index.get("schema") != "cosm2-figures-sources-v2"
        or index.get("run_id") != run_id
        or index.get("status") != "OBSERVED_FIXED_RUN"
    ):
        raise ValueError("final same-run observed figure index required")
    expected_sources = {"result": "result.json", "negative_matrix": "negative-matrix.json"}
    if set(index.get("sources", {})) != set(expected_sources):
        raise ValueError("exact final result/matrix source bindings required")
    for key, filename in expected_sources.items():
        item = index["sources"][key]
        expected = root / "artifacts/cosm2-gateway-demo-live" / run_id / filename
        source = inside(root / item["path"], root)
        if source != expected or digest(source) != item["sha256"]:
            raise ValueError("foreign or changed figure observation source")
    observations = strict_json(root / index["sources"]["negative_matrix"]["path"])["observations"]
    if (
        index.get("observations") != observations
        or len(index.get("cells", [])) != 28
        or len(index.get("additional_effect_observations", [])) != 3
    ):
        raise ValueError("complete observed matrix/effect evidence required")
    metadata = strict_json(root / STAGE / "figures/pdf-metadata.json")
    if (
        metadata.get("run_id") != run_id
        or metadata["source_index"]["sha256"] != digest(index_path)
        or not metadata.get("font", {}).get("sha256")
        or not metadata.get("command")
    ):
        raise ValueError("figure metadata/source/font binding mismatch")
    outputs = metadata.get("outputs", [])
    required = {"fig-system.pdf", "fig-protocol.pdf", "fig-negative.pdf"}
    if {Path(x["path"]).name for x in outputs} != required:
        raise ValueError("all three figure PDF bindings required")
    for item in outputs:
        source = (
            inside(root / item["path"], root)
            if not Path(item["path"]).is_absolute()
            else inside(item["path"], root)
        )
        if (
            source != figure_root / source.name
            or digest(source) != item["sha256"]
            or item.get("pages") != 1
        ):
            raise ValueError("figure PDF/source integrity mismatch")
    latency = strict_json(figure_root / "fig-latency.source.json")
    if (
        latency.get("run_id") != bench_run.name
        or latency.get("status") != "COMPLETE"
        or latency.get("figure_sha256") != digest(figure_root / "fig-latency.pdf")
    ):
        raise ValueError("latency figure does not match formal benchmark")
    for name in ("raw.csv", "warmup.csv", "summary.json"):
        expected = digest(bench_run / name)
        entries = [value for key, value in latency["sources"].items() if Path(key).name == name]
        if entries != [expected]:
            raise ValueError("latency source dataset mismatch")
    return index


def validate_old_bundle(path):
    with zipfile.ZipFile(path) as archive:
        failures = 0
        for name in ("raw.csv", "warmup.csv", "summary.json"):
            members = [
                x for x in archive.namelist() if x.endswith("historical-failed-run01/" + name)
            ]
            if len(members) != 1:
                raise ValueError("prior bundle must retain all failed run01 artifacts")
            data = archive.read(members[0])
            if name.endswith(".csv"):
                failures += sum(
                    row["status"] == "ERROR" for row in csv.DictReader(io.StringIO(data.decode()))
                )
        if failures != 110:
            raise ValueError("prior bundle must preserve 100+10 genuine failed attempts")


def build_plan(bench, captures, run_id, *, repo=REPO):
    bench, captures = inside(bench, repo), inside(captures, repo)
    summary = validate_formal_benchmark(bench)
    run_dir = inside(repo / "artifacts/cosm2-gateway-demo-live" / run_id, repo)
    validate_run(run_dir, run_id)
    capture, _ = validate_capture(captures, run_id, root=repo)
    figures = repo / "复赛冲刺材料-20261018/论文模板/figures"
    validate_figures(figures, run_id, bench, root=repo)
    stage = repo / STAGE
    validate_redacted_history(stage)
    env_file = inside(stage / "controller/runner.env", repo)
    plan = Plan(repo, secret_values(env_file if env_file.exists() else None))
    for path in sorted(figures.iterdir()):
        if path.suffix.lower() in {".pdf", ".json", ".md", ".txt"}:
            plan.add(
                path,
                "figures/" + path.name,
                kind="figure/provenance",
                status="COMPLETE_CANDIDATE",
                run_id=bench.name if path.name.startswith("fig-latency") else run_id,
            )
    plan.tree(bench, "benchmark/formal", status="MEASURED_COMPLETE", run_id=bench.name)
    plan.add(
        repo / "experiments/cosm2_bench/README.md",
        "benchmark/README.md",
        kind="boundaries",
        status="CURRENT",
    )
    for path in sorted((repo / "experiments/cosm2_bench/results").glob("20261017-full-*")):
        if path != bench and path.is_dir():
            plan.tree(
                path,
                "history/benchmark/" + path.name,
                status="EXCLUDED_NOT_FORMAL",
                run_id=path.name,
            )
    plan.tree(
        captures,
        "media/current",
        status="ACTUAL_CURRENT_RUN",
        kind="media/provenance",
        run_id=run_id,
    )
    # Preserve all current-stage public records, including failed captures and redacted histories.
    plan.tree(stage, "history/current-stage", status="PRESERVED_PUBLIC_HISTORY_SEE_CONTENT")
    for path in sorted((repo / "artifacts/cosm2-gateway-demo-live").iterdir()):
        if path.is_dir():
            plan.tree(
                path,
                "history/B7/" + path.name,
                status="CURRENT_RUN" if path.name == run_id else "PRESERVED_RUN_SEE_RESULT",
                run_id=path.name,
            )
    old = repo / "复赛冲刺材料-20261018/A交付-20261017-r2.zip"
    validate_old_bundle(old)
    plan.add(
        old, "history/A-prior-partial-r2.zip", kind="historical-bundle", status="PARTIAL_HISTORICAL"
    )
    for name in ("review-r1.md", "review-r2.md", "acceptance.md"):
        plan.add(
            repo / "tasks/workflow/runs/cosm2-a3-a7-20261017" / name,
            "history/A3/" + name,
            kind="historical-review",
            status="HISTORICAL_SCOPE_ONLY",
        )
    plan.add(
        repo / "artifacts/cosm2-a3-a7-20261017/measure/crosscheck-tests.txt",
        "history/A3/crosscheck-B1-missing.txt",
        kind="historical-failure",
        status="FAILED_HISTORICAL",
    )
    plan.tree(
        repo / "tasks/workflow/runs/cosm2-full-20261017", "workflow", status="CANDIDATE_WORKFLOW"
    )
    for source, destination, kind in (
        ("docs/cosm2-gateway-20261020.md", "启动与实现说明.md", "startup-and-limits"),
        ("tests/cosm2-public-vector.json", "公开向量/cosm2-public-vector.json", "public-vector"),
        (
            "tools/cosm2_vector_check.py",
            "公开向量/cosm2_vector_check.py",
            "independent-OpenSSL-checker",
        ),
        (
            "复赛冲刺材料-20261018/01-双域协同SM2实施规划-A与B分工.md",
            "需求原文.md",
            "original-requirements",
        ),
    ):
        plan.add(
            repo / source,
            destination,
            kind=kind,
            status="PUBLIC_REPRODUCTION_MATERIAL",
            run_id=run_id,
        )
    plan.add(
        repo / "docs/cosm2-paper-claims-20261017.md",
        "论文可写清单.md",
        kind="claims-and-limits",
        status="CANDIDATE_NOT_ACCEPTED",
        run_id=run_id,
    )
    return plan, dict(
        schema_version=1,
        status="COMPLETE_IMPLEMENTATION_CANDIDATE_NOT_INDEPENDENTLY_ACCEPTED",
        complete=True,
        independently_accepted=False,
        benchmark_run_id=summary["run_id"],
        cosm2_run_id=run_id,
        capture_source=capture["cosign_live"]["source"],
        redacted_history=(
            "Public failed histories explicitly redacted; original raw bytes/original SHA "
            "unavailable as disclosed in included reports. Never claim unredacted verbatim "
            "failure preservation."
        ),
        excluded=[
            "private files/operator env/DSN/share/key material",
            "full-01 benchmark truncated image identity",
            "capture-01 and capture-02 failed harnesses, preserved separately",
        ],
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench-run", type=Path, required=True)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--cosm2-run", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = inside(args.output)
    if output.exists() or output.with_suffix(".zip").exists():
        raise ValueError("output must be new")
    plan, metadata = build_plan(args.bench_run, args.captures, args.cosm2_run)
    result = plan.copy(output, metadata)
    print(
        json.dumps(
            dict(
                status=result["status"],
                files=len(result["files"]),
                output=str(output),
                zip_sha256=digest(output.with_suffix(".zip")),
            ),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
