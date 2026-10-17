"""Necessary statistics, preservation and publication-boundary tests."""

import csv
import hashlib
import json

import pytest

from experiments.cosm2_bench.bench import (
    FIELDS,
    METRICS,
    emulation_description,
    measure,
    run_status,
    summarize,
)
from experiments.cosm2_bench.plot import validate


def test_statistics_nearest_rank_retains_outlier():
    stats = summarize(list(range(99)) + [10000])
    assert stats == dict(n=100, median=49.5, p95=94, min=0, max=10000)
    assert summarize([]) == dict(n=0, median=None, p95=None, min=None, max=None)
    assert summarize([3])["p95"] == 3


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, True, "2"])
def test_bad_durations(bad):
    with pytest.raises(ValueError):
        summarize([bad])


def test_sampler_keeps_errors_including_warmup():
    def fail():
        raise ValueError("private data must never be logged")

    raw, warmups = [], []
    measure(fail, 3, 2, "sm2_sign", "run", "env", raw, warmups)
    assert len(raw) == 3 and len(warmups) == 2
    assert all(r["status"] == "ERROR" and r["error"] == "ValueError" for r in raw + warmups)
    assert all(r["elapsed_ms"] >= 0 for r in raw + warmups)


def fixture_run(tmp_path):
    environment = dict(
        cpu="fixture", machine="amd64", image="fixture-runner:1", image_id="sha256:" + "a" * 64
    )
    env = hashlib.sha256(json.dumps(environment, sort_keys=True).encode()).hexdigest()
    metrics = {
        m: dict(**summarize([]), status="NOT_MEASURED", reason="B missing", attempts=0, failures=0)
        for m in METRICS
    }
    metrics["sm2_sign"] = dict(
        **summarize([1.0, 100.0]), status="MEASURED", reason=None, attempts=2, failures=0
    )
    summary = dict(
        status="PARTIAL",
        unit="ms",
        environment=environment,
        environment_id=env,
        run_id="run",
        metrics=metrics,
        requested_samples=2,
        warmup=1,
    )
    (tmp_path / "summary.json").write_text(json.dumps(summary))
    rows = [
        dict(
            run_id="run",
            environment_id=env,
            metric="sm2_sign",
            sample=i,
            elapsed_ms=v,
            status="OK",
            error="",
        )
        for i, v in enumerate([1.0, 100.0])
    ]
    write_rows(tmp_path / "raw.csv", rows)
    write_rows(tmp_path / "warmup.csv", [rows[0]])
    return rows, summary


def write_rows(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_plot_accepts_honest_partial_run(tmp_path):
    fixture_run(tmp_path)
    assert validate(tmp_path)["metrics"]["sm2_sign"]["max"] == 100.0


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "mixed_environment",
        "mixed_run",
        "nan",
        "negative",
        "failure",
        "gap",
        "unknown",
        "error",
    ],
)
def test_plot_rejects_bad_raw(tmp_path, mutation):
    rows, _ = fixture_run(tmp_path)
    if mutation == "duplicate":
        rows.append(rows[0].copy())
    elif mutation == "mixed_environment":
        rows[0]["environment_id"] = "other"
    elif mutation == "mixed_run":
        rows[0]["run_id"] = "other"
    elif mutation == "nan":
        rows[0]["elapsed_ms"] = "nan"
    elif mutation == "negative":
        rows[0]["elapsed_ms"] = -1
    elif mutation == "failure":
        rows[0]["status"] = "ERROR"
    elif mutation == "gap":
        rows[0]["sample"] = 7
    elif mutation == "unknown":
        rows[0]["metric"] = "fabricated"
    elif mutation == "error":
        rows[0]["error"] = "ValueError"
    write_rows(tmp_path / "raw.csv", rows)
    with pytest.raises(ValueError):
        validate(tmp_path)


@pytest.mark.parametrize(
    "mutation", ["summary", "fingerprint", "missing_reason", "warmup", "bool_count", "bool_stat"]
)
def test_plot_rejects_bad_metadata(tmp_path, mutation):
    _, summary = fixture_run(tmp_path)
    if mutation == "summary":
        summary["metrics"]["sm2_sign"]["median"] = 2
    elif mutation == "fingerprint":
        summary["environment"]["cpu"] = "different host"
    elif mutation == "missing_reason":
        summary["metrics"]["gateway_e2e"]["reason"] = None
    elif mutation == "bool_count":
        summary["requested_samples"] = True
    elif mutation == "bool_stat":
        summary["metrics"]["sm2_sign"]["min"] = True
    elif mutation == "warmup":
        write_rows(tmp_path / "warmup.csv", [])
    (tmp_path / "summary.json").write_text(json.dumps(summary))
    with pytest.raises(ValueError):
        validate(tmp_path)


def test_status_and_architecture_are_derived():
    assert run_status({"one": {"status": "MEASURED"}}) == "COMPLETE"
    assert run_status({"one": {"status": "NOT_MEASURED"}}) == "PARTIAL"
    assert run_status({"one": {"status": "ERROR"}}) == "ERROR"
    assert emulation_description("arm64", "aarch64") == "none (matching architectures)"
    assert emulation_description("amd64", "x86_64") == "none (matching architectures)"
    assert "emulation" in emulation_description("arm64", "x86_64")
    assert "UNKNOWN" in emulation_description("UNKNOWN", "x86_64")


def test_prepared_measurement_excludes_prepare_and_finish(monkeypatch):
    from experiments.cosm2_bench.bench import measure_prepared

    events = []
    times = iter([1000000, 4000000])
    monkeypatch.setattr("experiments.cosm2_bench.bench.time.perf_counter_ns", lambda: next(times))

    def prepare():
        events.append("prepare:Q1/proof/signature")

        def operation():
            events.append("operation:predicate-or-HTTP")
            return "result"

        def finish(result):
            assert result == "result"
            events.append("finish:verify-or-counters")

        return operation, finish

    raw, warmups = [], []
    measure_prepared(prepare, 1, 0, "gateway_e2e", "run", "env", raw, warmups)
    assert events == [
        "prepare:Q1/proof/signature",
        "operation:predicate-or-HTTP",
        "finish:verify-or-counters",
    ]
    assert raw[0]["elapsed_ms"] == 3.0 and raw[0]["status"] == "OK"


def test_prepared_failure_still_completes_nonce_cleanup():
    from experiments.cosm2_bench.bench import measure_prepared

    completions = []

    def prepare():
        def operation():
            raise RuntimeError("must not log credentials")

        return operation, lambda result: completions.append(result)

    raw, warmups = [], []
    measure_prepared(prepare, 2, 1, "cosm2_round2_db", "run", "env", raw, warmups)
    assert completions == [None, None, None]
    assert all(row["error"] == "RuntimeError" for row in raw + warmups)


@pytest.mark.parametrize("mutation", ["accepted", "keys", "ancestor", "effects", "boundary"])
def test_schema2_requires_fresh_acceptance_evidence(tmp_path, mutation):
    rows, summary = fixture_run(tmp_path)
    summary["schema_version"] = 2
    summary["boundaries"] = dict.fromkeys(METRICS, "explicit actual timing boundary")
    summary["adapter_errors"] = {}
    summary["metrics"]["gateway_e2e"] = summary["metrics"]["sm2_sign"].copy()
    summary["gateway_evidence"] = dict(
        accepted=3,
        distinct_business_keys=3,
        approvals=3,
        all_ancestor_counters=[[210000, 0, 3, 0]] * 3,
        downstream_orders=0,
    )
    gateway = [{**row, "metric": "gateway_e2e"} for row in rows]
    write_rows(tmp_path / "raw.csv", rows + gateway)
    write_rows(tmp_path / "warmup.csv", [rows[0], gateway[0]])
    # Validate the correct evidence before changing exactly one boundary.
    (tmp_path / "summary.json").write_text(json.dumps(summary))
    validate(tmp_path)
    if mutation == "accepted":
        summary["gateway_evidence"]["accepted"] = 2
    elif mutation == "keys":
        summary["gateway_evidence"]["distinct_business_keys"] = 1
    elif mutation == "ancestor":
        summary["gateway_evidence"]["all_ancestor_counters"][1] = [0, 0, 0, 0]
    elif mutation == "effects":
        summary["gateway_evidence"]["downstream_orders"] = 1
    else:
        del summary["boundaries"]["cosm2_round2_db"]
    (tmp_path / "summary.json").write_text(json.dumps(summary))
    with pytest.raises(ValueError):
        validate(tmp_path)


def test_schema2_refuses_truncated_image_identity(tmp_path):
    rows, summary = fixture_run(tmp_path)
    summary["schema_version"] = 2
    summary["environment"]["image_id"] = "sha256:truncated"
    environment_id = hashlib.sha256(
        json.dumps(summary["environment"], sort_keys=True).encode()
    ).hexdigest()
    summary["environment_id"] = environment_id
    summary["boundaries"] = dict.fromkeys(METRICS, "actual boundary")
    summary["adapter_errors"] = {}
    for row in rows:
        row["environment_id"] = environment_id
    write_rows(tmp_path / "raw.csv", rows)
    write_rows(tmp_path / "warmup.csv", [rows[0]])
    (tmp_path / "summary.json").write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="immutable image id"):
        validate(tmp_path)
