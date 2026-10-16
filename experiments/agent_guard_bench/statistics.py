"""Strict public attempt accounting; authorization truth belongs to independent oracles."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping
from statistics import mean

from .workload import MODES, SEEDS, TOOLS, Plan


class InvalidMeasurements(ValueError):
    """A denominator, identity, timestamp or observation is not complete."""


def integer(value, name, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise InvalidMeasurements(f"strict integer required: {name}")
    return value


def nearest_rank(values: Iterable[int], p: float):
    samples = list(values)
    if type(p) not in (float, int) or not math.isfinite(p) or not 0 < p <= 1:
        raise InvalidMeasurements("percentile must be in (0,1]")
    for value in samples:
        integer(value, "sample")
    samples.sort()
    return samples[math.ceil(p * len(samples)) - 1] if samples else None


def distribution(values):
    samples = list(values)
    return {
        "n": len(samples),
        **{f"p{int(p * 100)}_ns": nearest_rank(samples, p) for p in (0.5, 0.95, 0.99)},
    }


def validate_actual_rows(plan: Plan, rows, *, require_complete=True):
    """One actual row per attempted invoke. Missing plans are never synthesized.

    A planned row only fulfils the required actual denominator when a real
    HTTP write was observed (``invoke_write == "OBSERVED"``). Pre-send connect
    failures and unknown-write transport failures are retained as honest
    failure rows but cannot substitute an actual invoke; they stay in the
    error/latency statistics and are reported in ``unobserved_write_indices``.
    """
    if type(plan) is not Plan:
        raise InvalidMeasurements("frozen Plan required")
    rows = list(rows)
    seen = set()
    observed = set()
    unobserved = []
    for row in rows:
        if type(row) is not dict:
            raise InvalidMeasurements("actual row must be object")
        index = integer(row.get("index"), "index")
        if index >= len(plan.intentions) or index in seen:
            raise InvalidMeasurements("duplicate or unplanned actual row")
        seen.add(index)
        write = row.get("invoke_write")
        if write not in ("OBSERVED", "NONE", "UNKNOWN"):
            raise InvalidMeasurements("invoke write observation required")
        if write == "OBSERVED":
            if row.get("wire_sent") is not True:
                raise InvalidMeasurements("observed write requires a completed real request")
            observed.add(index)
        else:
            unobserved.append(index)
        intent = plan.intentions[index]
        for key in (
            "seed",
            "mode",
            "task",
            "tool_id",
            "category",
            "attack_class",
            "retry_kind",
        ):
            if type(row.get(key)) is not type(getattr(intent, key)) or row.get(key) != getattr(
                intent, key
            ):
                raise InvalidMeasurements(f"planned identity mismatch: {key}")
        for key in (
            "send_ns",
            "end_ns",
            "send_unix_ns",
            "request_bytes",
            "response_bytes",
        ):
            integer(row.get(key), key)
        if row["end_ns"] < row["send_ns"]:
            raise InvalidMeasurements("backwards monotonic clock")
        status = row.get("http_status")
        if status is not None and (type(status) is not int or not 100 <= status <= 599):
            raise InvalidMeasurements("invalid actual HTTP status")
        if status is None and not row.get("error"):
            raise InvalidMeasurements("transport failure requires error")
        if type(row.get("error")) not in (str, type(None)):
            raise InvalidMeasurements("invalid error")
        for field in ("auth_pass", "new_accept"):
            if row.get(field) is not None and type(row.get(field)) is not bool:
                raise InvalidMeasurements("observations must be bool or unknown")
        if (
            type(row.get("key_hash")) is not str
            or len(row["key_hash"]) != 64
            or any(c not in "0123456789abcdef" for c in row["key_hash"])
        ):
            raise InvalidMeasurements("key hash required")
        if any(
            k.lower().replace("_", "-")
            in {"authorization", "ag-proof", "token", "proof", "dsn", "private-key"}
            for k in row
        ):
            raise InvalidMeasurements("secret field in public actual row")
    missing = sorted(set(range(len(plan.intentions))) - observed)
    if require_complete and missing:
        raise InvalidMeasurements(f"missing actual invokes: {len(missing)}")
    return {
        "rows": rows,
        "missing_indices": missing,
        "unobserved_write_indices": sorted(unobserved),
        "status": "COMPLETE" if not missing else "INCOMPLETE",
    }


def overlap_peak(rows):
    events = [(r["send_ns"], 1) for r in rows] + [(r["end_ns"], -1) for r in rows]
    # End precedes send at equal timestamps: [send,end) intervals.
    active = peak = 0
    for _, delta in sorted(events):
        active += delta
        peak = max(peak, active)
    return peak


def rate(count, start_ns, end_ns):
    integer(count, "rate count")
    integer(start_ns, "window start")
    integer(end_ns, "window end")
    if end_ns <= start_ns:
        raise InvalidMeasurements("positive actual rate window required")
    return {
        "n": count,
        "start_ns": start_ns,
        "end_ns": end_ns,
        "duration_ns": end_ns - start_ns,
        "per_second": count * 1_000_000_000 / (end_ns - start_ns),
    }


def summarize_repetition(plan, rows, *, completions=None, require_complete=True):
    validated = validate_actual_rows(plan, rows, require_complete=require_complete)
    rows = validated.pop("rows")
    groups = {
        "all": rows,
        "failed": [
            r
            for r in rows
            if r["error"] is not None or r["http_status"] is None or r["http_status"] >= 400
        ],
    }
    groups.update(
        {
            category: [r for r in rows if r["category"] == category]
            for category in ("legal", "attack", "retry")
        }
    )
    groups.update({"tool:" + tool: [r for r in rows if r["tool_id"] == tool] for tool in TOOLS})
    groups.update(
        {f"class:{cls}": [r for r in rows if r["attack_class"] == cls] for cls in range(10)}
    )
    result = {
        **validated,
        "mode": plan.mode,
        "seed": plan.seed,
        "planned_n": len(plan.intentions),
        "actual_n": len(rows),
        "latency": {
            name: distribution(r["end_ns"] - r["send_ns"] for r in group)
            for name, group in groups.items()
        },
        "peak_interval_inflight": overlap_peak(rows),
        "status_counts": dict(Counter(str(r["http_status"]) for r in rows)),
        "capability_notes": {
            "proof_reuse": "MEASURED"
            if plan.mode in ("complete", "realSM2delegation_noAtomic")
            else "N/A",
            "signed_receipt": "MEASURED" if plan.mode == "complete" else "N/A",
            "independent_anchor": "MEASURED" if plan.mode == "complete" else "N/A",
        },
    }
    if not rows:
        result["rates"] = {}
        return result
    start, end = min(r["send_ns"] for r in rows), max(r["end_ns"] for r in rows)
    result["rates"] = {"attempt": rate(len(rows), start, end)}
    for metric, field in (("authpass", "auth_pass"), ("newaccept", "new_accept")):
        known = [r for r in rows if r[field] is not None]
        result["rates"][metric] = {
            **rate(sum(r[field] for r in known), start, end),
            "known_n": len(known),
            "unknown_n": len(rows) - len(known),
        }
    # Completion facts originate in an independent DB oracle, not HTTP202.
    for metric in ("terminal", "READY", "anchor"):
        if plan.mode != "complete" and metric in ("READY", "anchor"):
            result["rates"][metric] = "N/A"
            continue
        observation = (completions or {}).get(metric)
        if observation is None:
            result["rates"][metric] = {"status": "NOT_OBSERVED"}
            continue
        count = integer(observation["n"], metric)
        expected = integer(observation["expected_n"], "expected completion")
        if count > expected or observation["end_ns"] > observation["deadline_ns"]:
            raise InvalidMeasurements("invalid completion window")
        result["rates"][metric] = {
            **rate(count, observation["start_ns"], observation["end_ns"]),
            "expected_n": expected,
            "gap": expected - count,
            "deadline_ns": observation["deadline_ns"],
        }
    return result


def summarize_two_seeds(repetitions):
    repetitions = list(repetitions)
    if (
        len(repetitions) != 2
        or {r["seed"] for r in repetitions} != set(SEEDS)
        or len({r["mode"] for r in repetitions}) != 1
    ):
        raise InvalidMeasurements("both original seeds required")
    if repetitions[0]["mode"] not in MODES:
        raise InvalidMeasurements("unknown mode")
    throughput = [r["rates"]["attempt"]["per_second"] for r in repetitions]
    return {
        "mode": repetitions[0]["mode"],
        "raw_repetitions": repetitions,
        "attempt_per_second": {
            "mean": mean(throughput),
            "min": min(throughput),
            "max": max(throughput),
        },
        "limitations": "Two repetitions do not support reliable confidence intervals "
        "or causal superiority.",
    }


def effect_budget_metrics(*, policies: Mapping, facts: Mapping, effects: Iterable[Mapping]):
    """Independently approved limits and event replay, including intermediate maxima."""
    effects = list(effects)
    violations, highwater = [], {}
    for grant, policy in policies.items():
        integer(policy["amount_limit"], "approved amount limit")
        integer(policy["call_limit"], "approved call limit")
        if grant not in facts:
            raise InvalidMeasurements("missing all-ancestor oracle")
        events = facts[grant]["events"]
        counters = [0, 0, 0, 0]
        maximum = [0, 0]
        previous = -1
        for event in events:
            sequence = integer(event["sequence"], "sequence")
            if sequence <= previous:
                raise InvalidMeasurements("duplicate/backwards event sequence")
            previous = sequence
            delta = event["delta"]
            if type(delta) is not list or len(delta) != 4 or any(type(v) is not int for v in delta):
                raise InvalidMeasurements("four strict signed counter deltas required")
            counters = [a + b for a, b in zip(counters, delta, strict=True)]
            if min(counters) < 0:
                raise InvalidMeasurements("negative replay counter")
            amount, calls = counters[0] + counters[1], counters[2] + counters[3]
            maximum = [max(maximum[0], amount), max(maximum[1], calls)]
            if amount > policy["amount_limit"] or calls > policy["call_limit"]:
                violations.append(
                    {
                        "grant": grant,
                        "sequence": sequence,
                        "amount": amount,
                        "calls": calls,
                    }
                )
        final = facts[grant]["final_counters"]
        if type(final) is not list or len(final) != 4:
            raise InvalidMeasurements("four final counters required")
        for counter in final:
            integer(counter, "final counter")
        if counters != final:
            raise InvalidMeasurements("counter/event oracle mismatch")
        highwater[grant] = {"amount": maximum[0], "calls": maximum[1]}
    unauthorized, duplicates = [], []
    by_intent = Counter()
    for effect in effects:
        if type(effect.get("permitted_by_policy")) is not bool:
            raise InvalidMeasurements("independent policy effect decision required")
        by_intent[effect["intent_hash"]] += 1
        if not effect["permitted_by_policy"]:
            unauthorized.append(effect["operation_id"])
    duplicates = [{"intent_hash": key, "effects": n} for key, n in by_intent.items() if n > 1]
    return {
        "budget_set_violations": violations,
        "all_ancestor_highwater": highwater,
        "permission_theft_effects": unauthorized,
        "duplicate_effects": duplicates,
    }


def revocation_bounds(
    *,
    commit_lower_ns,
    commit_upper_ns,
    rejected_send_ns,
    rejected_end_ns,
    server_clock_ns,
):
    for value in (
        commit_lower_ns,
        commit_upper_ns,
        rejected_send_ns,
        rejected_end_ns,
        server_clock_ns,
    ):
        integer(value, "revocation clock")
    if (
        commit_lower_ns > commit_upper_ns
        or rejected_send_ns > rejected_end_ns
        or rejected_send_ns < commit_upper_ns
    ):
        raise InvalidMeasurements("fresh post-commit request required")
    return {
        "lower_ns": max(0, rejected_send_ns - commit_upper_ns),
        "upper_ns": rejected_end_ns - commit_lower_ns,
        "server_clock_ns": server_clock_ns,
    }
