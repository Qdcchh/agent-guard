"""Real primitive measurements; no synthetic COSM2 or gateway timings."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

METRICS = (
    "cosm2_round1",
    "cosm2_round2",
    "cosm2_round3",
    "cosm2_total",
    "cosm2_round2_db",
    "sm2_sign",
    "sm2_verify",
    "frost_sign_quorum",
    "gateway_e2e",
)
FIELDS = ("run_id", "environment_id", "metric", "sample", "elapsed_ms", "status", "error")


def summarize(values):
    if any(type(v) not in (float, int) or not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("durations must be finite nonnegative numbers")
    if not values:
        return dict(n=0, median=None, p95=None, min=None, max=None)
    ordered = sorted(values)
    # Explicit nearest-rank percentile, including small n.
    return dict(
        n=len(values),
        median=statistics.median(values),
        p95=ordered[math.ceil(0.95 * len(values)) - 1],
        min=min(values),
        max=max(values),
    )


def run_status(metrics):
    if any(item["status"] == "ERROR" for item in metrics.values()):
        return "ERROR"
    return (
        "COMPLETE" if all(item["status"] == "MEASURED" for item in metrics.values()) else "PARTIAL"
    )


def emulation_description(host_arch, runner_arch):
    aliases = {"x86_64": "amd64", "aarch64": "arm64"}
    host, runner = aliases.get(host_arch, host_arch), aliases.get(runner_arch, runner_arch)
    if host == "UNKNOWN":
        return "UNKNOWN: host architecture not supplied"
    return (
        "none (matching architectures)"
        if host == runner
        else f"Docker emulation: {host} host / {runner} runner"
    )


def measure(operation, count, warmup, metric, run_id, environment_id, raw, warmups):
    for _phase, size, sink in (("warmup", warmup, warmups), ("sample", count, raw)):
        for index in range(size):
            start = time.perf_counter_ns()
            error = ""
            try:
                operation()
            except Exception as exc:
                error = type(exc).__name__  # never expose signer paths/secrets
            elapsed = (time.perf_counter_ns() - start) / 1e6
            sink.append(
                dict(
                    run_id=run_id,
                    environment_id=environment_id,
                    metric=metric,
                    sample=index,
                    elapsed_ms=elapsed,
                    status="ERROR" if error else "OK",
                    error=error,
                )
            )


def measure_prepared(prepare, count, warmup, metric, run_id, environment_id, raw, warmups):
    """Prepare outside timer; complete/validate outside timer, preserving every failure."""
    for size, sink in ((warmup, warmups), (count, raw)):
        for index in range(size):
            elapsed, error, finish, result = 0.0, "", None, None
            try:
                operation, finish = prepare()
                start = time.perf_counter_ns()
                try:
                    result = operation()
                finally:
                    elapsed = (time.perf_counter_ns() - start) / 1e6
            except Exception as exc:
                error = type(exc).__name__
            finally:
                if finish is not None:
                    try:
                        finish(result)
                    except Exception as exc:
                        error = error or type(exc).__name__
            sink.append(
                dict(
                    run_id=run_id,
                    environment_id=environment_id,
                    metric=metric,
                    sample=index,
                    elapsed_ms=elapsed,
                    status="ERROR" if error else "OK",
                    error=error,
                )
            )


def measure_cosm2(module, count, warmup, run_id, environment_id, raw, warmups):
    """Real frozen core API; three stages belong to the same signing session."""
    p1, p2 = module.ExecParty(), module.AuthzParty()
    public = p2.keygen_finish(p1.keygen_msg())
    p1.set_public(public)
    message = b"AGENT-GUARD-COSM2-ACTION-V1\nbenchmark-public-message"
    for size, sink in ((warmup, warmups), (count, raw)):
        for index in range(size):
            start = time.perf_counter_ns()
            timings = {}
            error = ""
            try:
                q1 = p1.sign_round1()
                end1 = time.perf_counter_ns()
                partial = p2.sign_round2(message, q1)
                end2 = time.perf_counter_ns()
                p1.sign_round3(message, *partial)
                end3 = time.perf_counter_ns()
                timings = dict(
                    cosm2_round1=(end1 - start) / 1e6,
                    cosm2_round2=(end2 - end1) / 1e6,
                    cosm2_round3=(end3 - end2) / 1e6,
                    cosm2_total=(end3 - start) / 1e6,
                )
            except Exception as exc:
                error = type(exc).__name__
            for metric in METRICS[:4]:
                sink.append(
                    dict(
                        run_id=run_id,
                        environment_id=environment_id,
                        metric=metric,
                        sample=index,
                        elapsed_ms=timings.get(metric, (time.perf_counter_ns() - start) / 1e6),
                        status="ERROR" if error else "OK",
                        error=error,
                    )
                )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument(
        "--with-gateway",
        action="store_true",
        help="measure real AS/read-only PG predicates and gateway acceptance",
    )
    args = parser.parse_args(argv)
    if args.samples < 1 or args.warmup < 0:
        parser.error("samples >= 1 and warmup >= 0 required")
    args.output.mkdir(parents=True, exist_ok=False)
    run_id = args.output.name
    environment = dict(
        cpu=Path("/proc/cpuinfo").read_text().split("model name")[-1].splitlines()[0].strip(),
        python=platform.python_version(),
        machine=platform.machine(),
        tongsuopy=importlib.metadata.version("tongsuopy"),
        image=os.environ.get("COSM2_IMAGE", "UNKNOWN"),
        image_id=os.environ.get("COSM2_IMAGE_ID", "UNKNOWN"),
        host_cpu=os.environ.get("COSM2_HOST_CPU", "UNKNOWN"),
        host_arch=os.environ.get("COSM2_HOST_ARCH", "UNKNOWN"),
        emulation=emulation_description(
            os.environ.get("COSM2_HOST_ARCH", "UNKNOWN"), platform.machine()
        ),
        frost_binary_sha256=hashlib.sha256(
            Path(os.environ["AGENT_GUARD_THRESHOLD_DEMO_BIN"]).read_bytes()
        ).hexdigest(),
    )
    environment_id = hashlib.sha256(json.dumps(environment, sort_keys=True).encode()).hexdigest()
    raw, warmups = [], []
    reasons = {m: "B1 core/API absent; no reference performance substitute" for m in METRICS[:4]}
    reasons["cosm2_round2_db"] = (
        "disabled: pass --with-gateway with isolated test database configuration"
    )
    reasons["gateway_e2e"] = (
        "disabled: pass --with-gateway with isolated test database configuration"
    )
    from agent_guard.crypto.sm import generate_sm2_private_key, sign_sm2_message, verify_sm2_message
    from agent_guard.threshold.codec import compute_params_digest
    from tests.fixtures.threshold import RustThresholdSigner

    try:
        protocol = importlib.import_module("agent_guard.cosign.protocol")
    except ModuleNotFoundError as exc:
        if exc.name not in ("agent_guard.cosign", "agent_guard.cosign.protocol"):
            raise
    else:
        measure_cosm2(protocol, args.samples, args.warmup, run_id, environment_id, raw, warmups)
    key = generate_sm2_private_key()
    message = b"AGENT-GUARD-COSM2-BENCH-PRIMITIVE-V1\nsynthetic-public-message"
    signature = sign_sm2_message(key, message)
    operations = {
        "sm2_sign": lambda: sign_sm2_message(key, message),
        "sm2_verify": lambda: verify_sm2_message(key.public_key(), message, signature),
    }
    with tempfile.TemporaryDirectory(prefix="cosm2-bench-private-") as private:
        os.chmod(private, 0o700)
        signer = RustThresholdSigner(Path(private) / "enrollment")
        public_hex = signer.enroll()
        action = dict(
            version=2,
            tenant_id="bench-tenant",
            task_id="bench-task",
            root_grant_id="root",
            grant_id="leaf",
            path_grant_ids=["root", "leaf"],
            tool_version="1",
            holder_client_id="holder",
            holder_kid="kid",
            audience="https://gateway.agent-guard.test",
            tool_id="procurement.order.create",
            currency="CNY",
            policy_version=1,
            key_epoch=1,
            action_id="benchmark-action",
            idempotency_key="bench-idempotency",
            request_id="req",
            quote_id="quote",
            quote_version="1",
            items=[dict(sku="sku-001", quantity=1)],
            delivery_id="office",
            amount_fen=100,
            expires_at=4102444800,
        )
        action["canonical_params_sha256"] = compute_params_digest(
            request_id="req",
            quote_id="quote",
            quote_version="1",
            items=[("sku-001", 1)],
            delivery_id="office",
        )
        # Python verification is INCLUDED in the documented timed boundary.
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        from agent_guard.threshold.codec import action_message

        sequence = 0

        def frost():
            nonlocal sequence
            sequence += 1
            action["action_id"] = f"benchmark-action-{sequence}"
            result = signer.sign(action)
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex)).verify(
                result, action_message(action)
            )

        operations["frost_sign_quorum"] = frost
        for metric, operation in operations.items():
            measure(
                operation, args.samples, args.warmup, metric, run_id, environment_id, raw, warmups
            )
    gateway_evidence, adapter_errors = None, {}
    if args.with_gateway:
        from tests.fixtures.cosm2_benchmark import GatewayBenchmark

        dsn = os.environ.get("AGENT_GUARD_TEST_DATABASE_URL")
        for metric in ("cosm2_round2_db", "gateway_e2e"):
            try:
                if not dsn:
                    raise ValueError("missing isolated test database configuration")
                expected = args.samples + args.warmup if metric == "gateway_e2e" else 0
                with GatewayBenchmark(dsn, expected_accepts=expected) as adapter:
                    prepare = adapter.prepare_gateway if expected else adapter.prepare_round2
                    measure_prepared(
                        prepare,
                        args.samples,
                        args.warmup,
                        metric,
                        run_id,
                        environment_id,
                        raw,
                        warmups,
                    )
                    if expected:
                        gateway_evidence = adapter.verify_gateway()
            except Exception as exc:
                adapter_errors[metric] = type(exc).__name__
    metrics = {}
    for metric in METRICS:
        rows = [r for r in raw if r["metric"] == metric]
        failures = [r for r in rows + warmups if r["metric"] == metric and r["status"] != "OK"]
        values = [r["elapsed_ms"] for r in rows if r["status"] == "OK"]
        metrics[metric] = dict(
            **summarize(values),
            status="ERROR"
            if failures or metric in adapter_errors
            else "MEASURED"
            if rows
            else "NOT_MEASURED",
            reason="adapter failure: " + adapter_errors[metric]
            if metric in adapter_errors
            else "sample/warmup failure; inspect raw.csv and warmup.csv"
            if failures
            else None
            if rows
            else reasons.get(metric),
            attempts=len(rows),
            failures=len(failures),
        )
    metadata = dict(
        schema_version=2,
        run_id=run_id,
        environment_id=environment_id,
        environment=environment,
        recorded_at=datetime.now(timezone.utc).isoformat(),
        requested_samples=args.samples,
        warmup=args.warmup,
        unit="ms",
        percentile="nearest-rank ceil(0.95*n)",
        status=run_status(metrics),
        gateway_evidence=gateway_evidence,
        adapter_errors=adapter_errors,
        boundaries={
            "cosm2_round1": "ExecParty round1 only; key generation excluded",
            "cosm2_round2": "AuthzParty round2 crypto only; no policy/database",
            "cosm2_round3": "ExecParty round3 including mature final SM2 verification",
            "cosm2_total": (
                "same session round1 through round3, including final verification; no DB"
            ),
            "cosm2_round2_db": (
                "Q1 prepared before timer; real AS fullchain, SELECT-only DB predicates "
                "and P2 round2; final P1 round3/verification after timer"
            ),
            "gateway_e2e": (
                "ASGI HTTP invocation send through 202 RESERVED response; fresh business key "
                "each attempt; bundle/proof/common signing and raw request preparation "
                "excluded; downstream worker/effect/receipt excluded"
            ),
            "sm2_sign": "mature Tongsuo sign only; ephemeral key generation excluded",
            "sm2_verify": "mature Tongsuo verification incl public_key() retrieval",
            "frost_sign_quorum": (
                "real Rust 2-of-3 V2 action; Python file I/O + process startup + "
                "native quorum + Python Ed25519 verification; enrollment excluded"
            ),
        },
        metrics=metrics,
    )
    for filename, rows in (("raw.csv", raw), ("warmup.csv", warmups)):
        with (args.output / filename).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    (args.output / "summary.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(dict(run_id=run_id, status=metadata["status"], metrics=metrics)))
    return (
        2
        if (args.require_complete and metadata["status"] != "COMPLETE")
        or metadata["status"] == "ERROR"
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
