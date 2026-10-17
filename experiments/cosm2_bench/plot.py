"""Validate a benchmark run and render a vector figure with explicit timing boundaries."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

from experiments.cosm2_bench.bench import FIELDS, METRICS, run_status, summarize


def validate(directory):
    directory = Path(directory)
    summary = json.loads((directory / "summary.json").read_text())
    if summary["unit"] != "ms" or set(summary["metrics"]) != set(METRICS):
        raise ValueError("invalid units or metric set")
    if (
        type(summary["requested_samples"]) is not int
        or summary["requested_samples"] < 1
        or type(summary["warmup"]) is not int
        or summary["warmup"] < 0
    ):
        raise ValueError("invalid sample/warmup counts")
    expected = hashlib.sha256(
        json.dumps(summary["environment"], sort_keys=True).encode()
    ).hexdigest()
    if expected != summary["environment_id"]:
        raise ValueError("environment fingerprint mismatch")
    seen, values = set(), {m: [] for m in METRICS}
    attempts = dict.fromkeys(METRICS, 0)
    reader = csv.DictReader((directory / "raw.csv").open())
    if reader.fieldnames != list(FIELDS):
        raise ValueError("invalid raw header")
    for row in reader:
        metric = row["metric"]
        identity = (metric, int(row["sample"]))
        if metric not in METRICS or identity in seen or identity[1] < 0:
            raise ValueError("unknown metric, duplicate or invalid sample")
        seen.add(identity)
        if row["environment_id"] != expected or row["run_id"] != summary["run_id"]:
            raise ValueError("mixed environment/run")
        duration = float(row["elapsed_ms"])
        if not math.isfinite(duration) or duration < 0 or row["status"] not in ("OK", "ERROR"):
            raise ValueError("invalid duration/status")
        if row["status"] != "OK":
            raise ValueError("failed samples: refuse publication")
        if row["error"]:
            raise ValueError("successful row contains error")
        values[metric].append(duration)
        attempts[metric] += 1
    for metric, data in values.items():
        stats = summary["metrics"][metric]
        for key in ("n", "attempts", "failures"):
            if type(stats[key]) is not int or stats[key] < 0:
                raise ValueError("invalid count")
        for key in ("median", "p95", "min", "max"):
            if stats[key] is not None:
                summarize([stats[key]])
        if any(stats[k] != v for k, v in summarize(data).items()):
            raise ValueError("summary/raw mismatch")
        if stats["attempts"] != attempts[metric] or stats["failures"] != 0:
            raise ValueError("attempt/failure mismatch")
        if data:
            if (
                stats["status"] != "MEASURED"
                or stats["reason"] is not None
                or len(data) != summary["requested_samples"]
            ):
                raise ValueError("incomplete measurement")
        elif stats["status"] != "NOT_MEASURED" or not stats["reason"]:
            raise ValueError("missing metric needs explicit reason")
    # Warmup failures must not silently disappear from a publishable figure.
    warm_seen = set()
    warm_reader = csv.DictReader((directory / "warmup.csv").open())
    if warm_reader.fieldnames != list(FIELDS):
        raise ValueError("invalid warmup header")
    for row in warm_reader:
        identity = (row["metric"], int(row["sample"]))
        if (
            identity in warm_seen
            or row["metric"] not in METRICS
            or row["environment_id"] != expected
            or row["run_id"] != summary["run_id"]
            or row["status"] != "OK"
            or row["error"]
            or not math.isfinite(float(row["elapsed_ms"]))
            or float(row["elapsed_ms"]) < 0
        ):
            raise ValueError("invalid warmup")
        warm_seen.add(identity)
    for metric, data in values.items():
        if data and {i for m, i in warm_seen if m == metric} != set(range(summary["warmup"])):
            raise ValueError("warmup count mismatch")
        if data and {i for m, i in seen if m == metric} != set(range(len(data))):
            raise ValueError("sample indices not contiguous")
    if summary.get("schema_version", 1) >= 2:
        if re.fullmatch(r"sha256:[0-9a-f]{64}", summary["environment"].get("image_id", "")) is None:
            raise ValueError("complete immutable image id required")
        if not summary["environment"].get("image"):
            raise ValueError("fixed image tag required")
        if set(summary["boundaries"]) != set(METRICS) or any(
            not value for value in summary["boundaries"].values()
        ):
            raise ValueError("all timing boundaries required")
        if summary["metrics"]["gateway_e2e"]["n"]:
            evidence = summary.get("gateway_evidence")
            count = summary["requested_samples"] + summary["warmup"]
            if (
                type(evidence) is not dict
                or evidence.get("accepted") != count
                or evidence.get("distinct_business_keys") != count
                or evidence.get("approvals") != count
                or evidence.get("downstream_orders") != 0
                or evidence.get("all_ancestor_counters") != [[70000 * count, 0, count, 0]] * 3
            ):
                raise ValueError("fresh accepted-operation evidence mismatch")
        if summary.get("adapter_errors"):
            raise ValueError("adapter failure: refuse publication")
    if summary["status"] != run_status(summary["metrics"]):
        raise ValueError("overall status mismatch")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--font", type=Path, default=Path("/System/Library/Fonts/STHeiti Light.ttc")
    )
    args = parser.parse_args(argv)
    summary = validate(args.directory)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    font_manager.fontManager.addfont(str(args.font))
    font = font_manager.FontProperties(fname=str(args.font))
    plt.rcParams.update(
        {
            "font.family": font.get_name(),
            "font.size": 10,
            "text.color": "#183954",
            "axes.labelcolor": "#183954",
            "xtick.color": "#183954",
            "ytick.color": "#183954",
            "axes.edgecolor": "#183954",
            "pdf.fonttype": 42,
        }
    )

    measured = [(m, s) for m, s in summary["metrics"].items() if s["n"]]
    fig, ax = plt.subplots(figsize=(12, 6.4))
    positions = range(len(measured))
    ax.bar(positions, [s["median"] for _, s in measured], color="#007f9f", label="中位数")
    ax.scatter(
        list(positions),
        [s["p95"] for _, s in measured],
        marker="_",
        s=200,
        color="#C63A2E",
        label="p95（最近秩法）",
    )
    labels = {
        "cosm2_round1": "共签第一轮",
        "cosm2_round2": "共签第二轮\n纯密码计算",
        "cosm2_round3": "共签第三轮\n含最终复验",
        "cosm2_total": "共签三轮全程\n无数据库",
        "cosm2_round2_db": "共签第二轮\n含 AS / 只读数据库",
        "gateway_e2e": "网关完整受理\n发送至 202",
        "sm2_sign": "单方 SM2 签名",
        "sm2_verify": "SM2 验签",
        "frost_sign_quorum": "FROST 2-of-3\n含进程启动 / I/O\n及复验",
    }
    ax.set_xticks(list(positions), [labels.get(m, m) for m, _ in measured], fontsize=8)
    for index, (_, stats) in enumerate(measured):
        ax.annotate(
            f"中位数 {stats['median']:.3f}\np95 {stats['p95']:.3f}",
            (index, stats["p95"]),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=7,
        )
    ax.set_ylabel("耗时（ms）")
    ax.set_ylim(0, max(s["p95"] for _, s in measured) * 1.45)
    ax.legend(loc="upper left")
    cosm2_missing = any(not summary["metrics"][m]["n"] for m in METRICS[:4])
    coverage = "双域共签尚未测量" if cosm2_missing else "双域共签已测量"
    status_label = "完整实测" if summary["status"] == "COMPLETE" else "部分实测"
    ax.set_title(f"{status_label}：{coverage}", fontproperties=font, fontsize=15)
    env = summary["environment"]
    missing = [m for m, s in summary["metrics"].items() if not s["n"]]
    fig.text(
        0.06,
        0.15,
        f"Run: {summary['run_id']} | 每项预热={summary['warmup']}，"
        f"正式 n={summary['requested_samples']} | 所有样本均保留\n"
        f"Host: {env['host_cpu']} ({env['host_arch']}); "
        f"runner {env['machine']}; {env['emulation']}\n"
        f"Python {env['python']}; tongsuopy {env['tongsuopy']}; {env['image']}\n"
        "未测："
        + (", ".join(missing) or "none")
        + "\n受理 e2e 排除共签准备、下游执行与回执；三轮之和不作为受理 e2e。",
        fontsize=8,
    )
    fig.subplots_adjust(bottom=0.37, top=0.87, left=0.08, right=0.97)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, format="pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    source = dict(
        run_id=summary["run_id"],
        status=summary["status"],
        environment_id=summary["environment_id"],
        command=f"python -m experiments.cosm2_bench.plot {args.directory} --output {args.output}",
        sources={
            str(args.directory / name): hashlib.sha256(
                (args.directory / name).read_bytes()
            ).hexdigest()
            for name in ("summary.json", "raw.csv", "warmup.csv")
        },
        font=dict(path=str(args.font), sha256=hashlib.sha256(args.font.read_bytes()).hexdigest()),
        palette=dict(bar="#007f9f", ink="#183954", p95="#C63A2E"),
        figure_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
        limitations=dict(
            emulation=env["emulation"], unmeasured=missing, boundaries=summary["boundaries"]
        ),
    )
    args.output.with_suffix(".source.json").write_text(json.dumps(source, indent=2) + "\n")
    print(json.dumps(source))


if __name__ == "__main__":
    main()
