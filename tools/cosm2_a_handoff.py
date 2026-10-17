"""Package available A deliverables with explicit, evidence-bound B dependencies."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(path: Path, root: Path) -> Path:
    path = path.absolute()
    if ".." in path.parts:
        raise ValueError("parent traversal")
    path.relative_to(root)
    path.resolve().relative_to(root.resolve())
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("symlink source or destination")
    return path


def validate_failed_history(directory: Path) -> dict:
    """Check the immutable failed run separately; it must never enter plot input."""
    expected_run = "20261017-measure-a3a4-01"
    summary = json.loads(inside(directory / "summary.json", directory).read_text())
    if (
        summary["run_id"] != expected_run
        or directory.name != expected_run
        or summary["status"] != "PARTIAL"
        or summary["unit"] != "ms"
        or type(summary["requested_samples"]) is not int
        or summary["requested_samples"] != 100
        or type(summary["warmup"]) is not int
        or summary["warmup"] != 10
    ):
        raise ValueError("unexpected historical failed run identity/counts/status")
    from experiments.cosm2_bench.bench import FIELDS, METRICS, summarize

    if set(summary["metrics"]) != set(METRICS):
        raise ValueError("historical metric set mismatch")
    expected_env = hashlib.sha256(
        json.dumps(summary["environment"], sort_keys=True).encode()
    ).hexdigest()
    if expected_env != summary["environment_id"]:
        raise ValueError("historical environment mismatch")
    collected = {}
    for name, count in (("raw.csv", 100), ("warmup.csv", 10)):
        with inside(directory / name, directory).open(newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(FIELDS):
                raise ValueError("historical CSV header mismatch")
            rows = list(reader)
        if len(rows) != count * 3:
            raise ValueError("historical row count mismatch")
        seen = set()
        for row in rows:
            identity = (row["metric"], int(row["sample"]))
            if (
                row["metric"] not in ("sm2_sign", "sm2_verify", "frost_sign_quorum")
                or identity in seen
                or not 0 <= identity[1] < count
                or row["run_id"] != expected_run
                or row["environment_id"] != expected_env
            ):
                raise ValueError("historical duplicate/mixed/invalid sample")
            seen.add(identity)
            value = float(row["elapsed_ms"])
            if not math.isfinite(value) or value < 0:
                raise ValueError("historical invalid duration")
            failed = row["metric"] == "frost_sign_quorum"
            if row["status"] != ("ERROR" if failed else "OK") or row["error"] != (
                "AssertionError" if failed else ""
            ):
                raise ValueError("historical error evidence mismatch")
        collected[name] = rows
    for metric, stats in summary["metrics"].items():
        raw = [r for r in collected["raw.csv"] if r["metric"] == metric]
        warmup = [r for r in collected["warmup.csv"] if r["metric"] == metric]
        failed = metric == "frost_sign_quorum"
        successes = [float(r["elapsed_ms"]) for r in raw if r["status"] == "OK"]
        for key in ("n", "attempts", "failures"):
            if type(stats[key]) is not int:
                raise ValueError("historical invalid integer count")
        for key in ("median", "p95", "min", "max"):
            if stats[key] is not None:
                summarize([stats[key]])
        if (
            any(stats[k] != v for k, v in summarize(successes).items())
            or stats["attempts"] != len(raw)
            or stats["failures"] != (len(raw) + len(warmup) if failed else 0)
            or stats["status"] != ("ERROR" if failed else "MEASURED" if raw else "NOT_MEASURED")
        ):
            raise ValueError("historical summary/raw mismatch")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench-run", type=Path, required=True)
    parser.add_argument(
        "--failed-bench-run",
        type=Path,
        default=REPO / "experiments/cosm2_bench/results/20261017-measure-a3a4-01",
    )
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bench = inside(args.bench_run, REPO / "experiments/cosm2_bench/results")
    failed_bench = inside(args.failed_bench_run, REPO / "experiments/cosm2_bench/results")
    captures = inside(args.captures, REPO / "artifacts/cosm2-a3-a7-20261017")
    output = inside(args.output, REPO / "复赛冲刺材料-20261018")
    sys.path.insert(0, str(REPO))
    from experiments.cosm2_bench.plot import validate

    summary = validate(bench)
    failed_summary = validate_failed_history(failed_bench)
    if bench == failed_bench:
        raise ValueError("formal and historical failed runs must be separate")
    capture = json.loads((captures / "capture-manifest.json").read_text())
    if capture.get("page_errors") or capture.get("cosign_live", {}).get("status") != "BLOCKED":
        raise ValueError("unexpected capture status; independently review before repackaging")
    if summary["status"] != "PARTIAL":
        raise ValueError("this partial handoff requires renewed review for complete measurements")
    if output.exists():
        raise ValueError("output must be a new directory")
    # Validate all source names/checksums before creating a deliverable directory.
    planned = []

    def include(
        source: Path,
        relative: str,
        kind: str,
        evidence: str,
        run_id: str | None = None,
        status: str = "AVAILABLE_PARTIAL",
    ) -> None:
        source = inside(source, REPO)
        if not source.is_file():
            raise ValueError(f"required source missing: {source.relative_to(REPO)}")
        planned.append((source, relative, kind, evidence, digest(source), run_id, status))

    figure_root = REPO / "复赛冲刺材料-20261018/论文模板/figures"
    for name in ("fig-system.pdf", "fig-protocol.pdf", "fig-negative.pdf", "fig-latency.pdf"):
        include(figure_root / name, "figures/" + name, "pdf", "figures/source-index files")
    for name in (
        "cosm2-figures-sources.json",
        "cosm2-figures-README.md",
        "fig-latency.source.json",
    ):
        include(
            figure_root / name, "figures/" + name, "provenance", "source paths, commands and SHA"
        )
    for name in ("raw.csv", "warmup.csv", "summary.json"):
        include(
            bench / name,
            "benchmark/" + name,
            "measurement",
            summary["run_id"],
            run_id=summary["run_id"],
            status="MEASURED_PARTIAL",
        )
    include(
        REPO / "experiments/cosm2_bench/README.md",
        "benchmark/README.md",
        "instructions",
        "measurement boundaries, failed run history and B API contract",
    )
    historical_note = (
        "FAILED historical run; original overall PARTIAL is legacy wording; "
        "FROST ERROR: 100 measured attempts + 10 warmups failed; "
        "never included in formal run02 statistics or figures"
    )
    historical_id = failed_summary["run_id"]
    for name in ("raw.csv", "warmup.csv", "summary.json"):
        include(
            failed_bench / name,
            "historical-failed-run01/" + name,
            "historical-failure",
            historical_note,
            historical_id,
            "FAILED",
        )
    measure_root = REPO / "artifacts/cosm2-a3-a7-20261017/measure"
    failure_output = inside(measure_root / "formal-command-output.txt", REPO)
    output_records = [
        json.loads(line) for line in failure_output.read_text().splitlines() if line.startswith("{")
    ]
    if (
        len(output_records) != 1
        or output_records[0].get("run_id") != historical_id
        or output_records[0].get("status") != failed_summary["status"]
        or output_records[0].get("metrics") != failed_summary["metrics"]
    ):
        raise ValueError("historical output log does not match failed run")
    include(
        failure_output,
        "historical-failed-run01/formal-command-output.txt",
        "original-failure-output",
        historical_note + "; original stdout/stderr, exit 2",
        historical_id,
        "FAILED",
    )
    include(
        measure_root / "implementation.md",
        "historical-failed-run01/implementation-static-attribution.md",
        "static-attribution",
        "Static diagnosis only; includes later plot/style notes, none is B evidence",
        historical_id,
        "FAILED",
    )
    include(
        REPO / "docs/cosm2-a-handoff-20261017.md",
        "historical-failed-run01/command-and-attribution.md",
        "historical-command",
        "Historical run01 command and explicitly static schema attribution; not rerun",
        historical_id,
        "FAILED",
    )
    for item in capture["captures"]:
        name = item["file"]
        if Path(name).name != name or not name.endswith(".png"):
            raise ValueError("invalid capture filename")
        source = inside(captures / name, captures)
        if digest(source) != item["sha256"]:
            raise ValueError("capture SHA mismatch")
        include(
            source,
            "screenshots/" + name,
            "screenshot",
            item["source"]
            + "; "
            + item["note"]
            + "; "
            + capture.get("capture_command", "node tools/cosm2_a_capture.cjs"),
        )
    include(
        captures / "capture-manifest.json",
        "screenshots/capture-manifest.json",
        "provenance",
        "unannotated actual UI captures",
    )
    if "video" in capture:
        item = capture["video"]
        name = item["file"]
        if Path(name).name != name or digest(captures / name) != item["sha256"]:
            raise ValueError("video filename/SHA mismatch")
        include(captures / name, "video/" + name, "replay-tour", item["description"])
        if "mp4" in item:
            converted = item["mp4"]
            name = converted["file"]
            if Path(name).name != name or digest(captures / name) != converted["sha256"]:
                raise ValueError("converted video filename/SHA mismatch")
            include(captures / name, "video/" + name, "replay-tour", item["description"])
        include(
            captures / "video-probe.json",
            "video/video-probe.json",
            "provenance",
            "ffprobe duration/dimensions/codec",
        )
    stage = REPO / "tasks/workflow/runs/cosm2-a3-a7-20261017"
    include(stage / "package-v1.md", "evidence/scope.md", "scope", "human-authorized A3-A7 scope")
    include(
        REPO / "artifacts/cosm2-a3-a7-20261017/measure/crosscheck-tests.txt",
        "evidence/crosscheck-B1-missing.txt",
        "blocked-check",
        "three real crosscheck failures; B1 absent; no skip or substitute",
    )
    created = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    manifest = {
        "schema_version": 1,
        "created_at": created,
        "timezone": "Asia/Shanghai",
        "status": "PARTIAL_B_DEPENDENCIES_MISSING",
        "complete": False,
        "benchmark_run_id": summary["run_id"],
        "historical_failed_run": {
            "run_id": historical_id,
            "status": "FAILED",
            "original_summary_status": "PARTIAL",
            "frost_status": "ERROR",
            "frost_formal_failures": 100,
            "frost_warmup_failures": 10,
            "included_in_formal_statistics": False,
        },
        "environment_id": summary["environment_id"],
        "environment": summary["environment"],
        "files": [],
        "blocked": [
            "A1: B1 public vector independent OpenSSL verification",
            "A3: B1 core/API and three real crosschecks",
            "A4: COSM2 rounds/total, B3 predicate DB timing, real gateway e2e",
            "A5: B7 real result and native live-run integration",
            "A6: COSM2 seven-attack evidence matrix",
            "A7: COSM2 real screenshot and three-minute live-run recording",
        ],
    }
    output.mkdir(parents=True, exist_ok=False)
    for source, relative, kind, evidence, sha, run_id, status in planned:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if digest(target) != sha or digest(source) != sha:
            raise RuntimeError("copy integrity failure")
        manifest["files"].append(
            {
                "file": relative,
                "source": str(source.relative_to(REPO)),
                "kind": kind,
                "evidence": evidence,
                "sha256": sha,
                "run_id": run_id,
                "status": status,
            }
        )
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    rows = [
        "# A 交付给 C：独立工作与真实依赖清单",
        "",
        f"生成时间：{created}。状态：**PARTIAL，不能写全部 A 已完成**。",
        "",
        "系统与协议是设计图；负例矩阵中的 COSM2 全未测，FROST 三格仅历史对照。",
        "延迟图仅含真实单SM2签名/验签及FROST，各100样本、10预热；共签/DB/e2e未测。",
        "录屏是实际浏览器的历史记录与示意导览，不是共签现场演示。截图未经后期标注。",
        "historical-failed-run01独立携带失败三原件、原样输出、历史命令与静态归因。",
        "run01旧summary整体PARTIAL不代表成功：FROST为ERROR，100正式+10预热全部失败。",
        "该目录状态FAILED，不并入benchmark/正式run02的300正式+30预热数据或图。",
        "",
        "## 可写入论文的内容",
        "",
        "- 双域设计、信任边界与三轮协议（明确设计状态、半诚实/同主机局限）。",
        "- 本机固定环境的单SM2/FROST原语对照；FROST包含进程启动、I/O及复验。",
        "- ARM宿主上的amd64 Docker仿真数据，不能外推原生或共签端到端性能。",
        "- 已完成的A端工具和示意界面，不宣称B核心/动态谓词签名已实现。",
        "",
        "## 待 B 后才能闭合",
        "",
    ]
    rows.extend("- " + reason for reason in manifest["blocked"])
    rows.extend(
        [
            "",
            "## 图、截图和数据与来源的映射",
            "",
            "每项原始命令、run_id、来源路径、SHA和状态见manifest.json及各source-index。",
            "",
            "| 文件 | 类型 | 状态 | run_id | 原路径 | SHA-256 | 命令 / 说明 |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    rows.extend(
        f"| {item['file']} | {item['kind']} | {item['status']} | {item['run_id'] or '—'} | "
        f"{item['source']} | {item['sha256']} | {item['evidence']} |"
        for item in manifest["files"]
    )
    rows.extend(
        [
            "",
            "## 后续复验",
            "",
            "B1到位后先确认benchmark/README.md的最小API，再在固定runner运行交叉测试，",
            "用tools/cosm2_vector_check.py验证B公开向量，按README用全新run目录重测。",
            "B3/B7到位后接真实谓词/网关样本，再更换矩阵与真实媒体；不得补写当前CSV。",
            "本目录不包含密钥、令牌或完整业务凭据。没有向C发送外部消息。",
            "",
        ]
    )
    (output / "交付说明.md").write_text("\n".join(rows))
    print(
        json.dumps(
            {"status": manifest["status"], "output": str(output), "files": len(planned)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
