"""Immutable synthetic intentions only; no credential, execution or success evidence.

Consumers must resolve source/quote/credential labels at actual send, JIT. Missing
material/dependencies must retain the original row and report INCOMPLETE. Ordinary
plans never install race barriers; ten-round controlled races are separate work.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

TOOLS = (
    "procurement.request.read",
    "procurement.document.read",
    "procurement.order.create",
    "notification.template.send",
)
MODES = ("staticACL", "realSM2delegation_noAtomic", "complete", "realSM2Bearer")
SEEDS = (2026100501, 2026100502)
CLASSES = (
    "盗token",
    "错holder父交换",
    "重放",
    "body替换",
    "域错配",
    "资源扩权",
    "strictSKU",
    "委托扩权",
    "失效状态",
    "预算次数竞争",
)
DEFAULT_CONFIG = Path(__file__).parents[1] / "workload-v1.json"


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def load_manifest(path=DEFAULT_CONFIG):
    """Parse a pinned, strict plan manifest, rejecting unknown or changed inputs."""
    if (
        hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest()
        != "c41a1243fec50e936ecbffcb44c491f0066602472842dcab562023c9e852dc0b"
    ):
        raise ValueError("fixed manifest fingerprint mismatch")
    data = json.loads(Path(path).read_text(), object_pairs_hook=_pairs)
    expected = json.loads(DEFAULT_CONFIG.read_text(), object_pairs_hook=_pairs)
    # Compare JSON types too: Python equality alone admits True == 1.
    if json.dumps(data, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("manifest differs from fixed approved inputs")
    return data


@dataclass(frozen=True, slots=True)
class Intention:
    namespace: str
    seed: int
    mode: str
    index: int
    category: str
    task: str
    slot: int
    tool_id: str
    tool_version: str
    business_key: str
    root: str
    mid: str
    leaf: str
    amount: int
    target_index: int | None = None
    attack_class: int | None = None
    case_index: int | None = None
    retry_kind: str | None = None
    material: str = "JIT_FRESH"
    source_label: str = "AS_ROOT_TWO_EXCHANGES"
    quote_label: str = "TRUSTED_FIXED_QUOTE"
    credential_label: str = "ROLE_PRIVATE_JIT"
    resource_label: str = "PREAPPROVED_FIXED_RESOURCE"
    witness: str | None = None


@dataclass(frozen=True, slots=True)
class Plan:
    seed: int
    mode: str
    intentions: tuple[Intention, ...]
    warmup: tuple[Intention, ...]
    send_order: tuple[int, ...]
    planned_slots: int = 50
    status: str = "PLANNED_NOT_RUN"


def generate_plan(mode: str, seed: int) -> Plan:
    """Return all 5000 predetermined rows, 250 separate warmups, and task-local DAG order."""
    if type(seed) is not int or seed not in SEEDS or type(mode) is not str or mode not in MODES:
        raise ValueError("unknown mode/seed")
    load_manifest()
    ns = f"{mode}-{seed}"
    rows = []

    def emit(
        category,
        task,
        tool,
        *,
        target=None,
        attack=None,
        case=None,
        retry=None,
        side=0,
        material="JIT_FRESH",
        witness=None,
    ):
        index = len(rows)
        if target is not None:
            original = rows[target]
            root, mid, leaf, key = (
                original.root,
                original.mid,
                original.leaf,
                original.business_key,
            )
            slot = original.slot
        else:
            root, mid, leaf = (
                f"{ns}/{task}/root",
                f"{ns}/{task}/mid{side}",
                f"{ns}/{task}/leaf{side}",
            )
            key = f"{ns}/{task}/{tool}/{side}"
            slot = (int(task[1:]) if task.startswith("T") else case or 0) % 50
        row = Intention(
            ns,
            seed,
            mode,
            index,
            category,
            task,
            slot,
            tool,
            "1",
            key,
            root,
            mid,
            leaf,
            70000 if tool == TOOLS[2] else 0,
            target,
            attack,
            case,
            retry,
            material,
            witness=witness,
        )
        rows.append(row)

    for task in range(875):
        for tool in TOOLS:
            emit("legal", f"T{task:04d}", tool)
    for cls in range(10):
        for case in range(100):
            if cls == 2:
                target = 4 * (500 + case)
                emit(
                    "attack",
                    rows[target].task,
                    TOOLS[0],
                    target=target,
                    attack=cls,
                    case=case,
                    material="EXACT_ORIGINAL_BYTES",
                    witness="COMMITTED_ORIGINAL_PROOF_CONSUMPTION",
                )
            else:
                task = f"A9-P{case // 2:02d}" if cls == 9 else f"A{cls}-{case:03d}"
                emit(
                    "attack",
                    task,
                    TOOLS[2],
                    attack=cls,
                    case=case,
                    side=case % 2 if cls == 9 else 0,
                )
    retry_specs = (
        ("freshidem", 0, 250, 0),
        ("sameproof", 250, 100, 0),
        ("terminalfreshidem", 350, 100, 2),
        ("lostresponsefreshretry", 450, 50, 2),
    )
    for kind, start, count, offset in retry_specs:
        for task in range(start, start + count):
            target = 4 * task + offset
            emit(
                "retry",
                rows[target].task,
                TOOLS[offset],
                target=target,
                retry=kind,
                material="EXACT_ORIGINAL_BYTES" if kind == "sameproof" else "JIT_FRESH_SAME_INTENT",
                witness={
                    "terminalfreshidem": "INDEPENDENT_TERMINAL",
                    "lostresponsefreshretry": "REAL_RESPONSE_WRITE_COMMIT_LOSS",
                }.get(kind),
            )
    after = {}
    for row in rows[3500:]:
        if row.target_index is not None:
            after.setdefault(row.target_index, []).append(row.index)
    order = []
    # Wave by tool ensures first 50 legal requests are available for future real
    # inflight observation; repeats/duplicates follow target before next tool.
    for wave in range(0, 875, 50):
        for offset in range(4):
            for task in range(wave, min(wave + 50, 875)):
                index = 4 * task + offset
                order.append(index)
                order.extend(after.get(index, ()))
    order.extend(r.index for r in rows[3500:4500] if r.target_index is None)
    # Notification needs the same task's accepted order. Keep exactly 250
    # warmup sends: 62 complete four-tool tasks and a final two-read task.
    warm = tuple(
        Intention(
            f"{ns}/warmup",
            seed,
            mode,
            i,
            "warmup",
            f"W{i // 4:04d}",
            (i // 4) % 50,
            TOOLS[i % 4],
            "1",
            f"{ns}/warmup/{i}",
            f"{ns}/warmup/{i // 4}/root",
            f"{ns}/warmup/{i // 4}/mid",
            f"{ns}/warmup/{i // 4}/leaf",
            70000 if i % 4 == 2 else 0,
        )
        for i in range(250)
    )
    return Plan(seed, mode, tuple(rows), warm, tuple(order))


def generate_suite() -> tuple[Plan, ...]:
    """Eight fixed repeats; second seed reverses the first mode order."""
    return tuple(
        generate_plan(mode, seed)
        for seed in SEEDS
        for mode in (MODES if seed == SEEDS[0] else MODES[::-1])
    )
