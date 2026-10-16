"""Local plan assertions only, never official measurement or security execution."""

import importlib.util
import json
import sys
from collections import Counter
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[2] / "experiments/agent_guard_bench/workload.py"
spec = importlib.util.spec_from_file_location("a34_workload", MODULE_PATH)
w = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = w
spec.loader.exec_module(w)


def test_fixed_seeds_counts_classes_and_no_posthoc_selection():
    suite = w.generate_suite()
    assert len(suite) == 8
    assert sum(len(p.intentions) for p in suite) == 40000
    assert sum(len(p.warmup) for p in suite) == 2000
    assert [p.mode for p in suite[:4]] == list(w.MODES)
    assert [p.mode for p in suite[4:]] == list(reversed(w.MODES))
    assert {p.seed for p in suite} == {2026100501, 2026100502}
    for p in suite:
        assert p.status == "PLANNED_NOT_RUN"
        assert p.planned_slots == 50
        assert Counter(r.category for r in p.intentions) == {
            "legal": 3500,
            "attack": 1000,
            "retry": 500,
        }
        assert Counter(
            r.attack_class for r in p.intentions if r.category == "attack"
        ) == dict.fromkeys(range(10), 100)
        assert len(set(p.send_order)) == 5000 and set(p.send_order) == set(range(5000))
        assert {r.slot for r in p.intentions[:3500]} == set(range(50))
        assert not ({r.business_key for r in p.warmup} & {r.business_key for r in p.intentions})
        for t in range(875):
            rs = p.intentions[t * 4 : t * 4 + 4]
            assert tuple(r.tool_id for r in rs) == w.TOOLS
            assert all(r.task == f"T{t:04d}" and r.slot == t % 50 for r in rs)
            assert [r.amount for r in rs] == [0, 0, 70000, 0]
        assert all(type(r.tool_version) is str and r.tool_version == "1" for r in p.intentions)
        assert p == w.generate_plan(p.mode, p.seed)
        with pytest.raises(FrozenInstanceError):
            p.intentions[0].category = "success"
        with pytest.raises(TypeError):
            p.intentions[0] = p.intentions[1]
        assert "result" not in asdict(p.intentions[0])


def test_attack_retry_intents_and_policy_oracle():
    p = w.generate_plan("complete", 2026100501)
    position = {i: at for at, i in enumerate(p.send_order)}
    replay = [r for r in p.intentions if r.attack_class == 2]
    assert [r.target_index for r in replay] == [4 * (500 + c) for c in range(100)]
    retries = [r for r in p.intentions if r.category == "retry"]
    assert Counter(r.retry_kind for r in retries) == {
        "freshidem": 250,
        "sameproof": 100,
        "terminalfreshidem": 100,
        "lostresponsefreshretry": 50,
    }
    expected = (
        list(range(0, 1000, 4))
        + list(range(1000, 1400, 4))
        + list(range(1402, 1800, 4))
        + list(range(1802, 2000, 4))
    )
    assert [r.target_index for r in retries] == expected
    assert not ({r.target_index for r in replay} & {r.target_index for r in retries})
    for r in replay + retries:
        original = p.intentions[r.target_index]
        assert original.category == "legal"
        assert (r.task, r.business_key, r.root, r.mid, r.leaf, r.tool_id) == (
            original.task,
            original.business_key,
            original.root,
            original.mid,
            original.leaf,
            original.tool_id,
        )
        assert position[original.index] < position[r.index] < position[original.index + 1]
    races = [r for r in p.intentions if r.attack_class == 9]
    for pair in range(50):
        left, right = races[2 * pair : 2 * pair + 2]
        assert left.task == right.task == f"A9-P{pair:02d}"
        assert left.root == right.root
        assert left.mid != right.mid and left.leaf != right.leaf
        assert left.business_key != right.business_key
        assert left.amount == right.amount == 70000
    assert len({r.root for r in races}) == 50
    manifest = w.load_manifest()
    assert manifest["policy"]["amount_limits"] == [100000, 80000, 70000]
    assert manifest["policy"]["call_limits"] == [12, 10, 8]
    assert manifest["schedule"]["tool_version"] == "1"
    assert all("JIT" in r.credential_label for r in p.intentions)


def test_warmup_has_same_task_order_before_notification_without_extra_sends():
    for plan in w.generate_suite():
        rows = plan.warmup
        assert len(rows) == len({r.business_key for r in rows}) == 250
        assert len({r.task for r in rows}) == 63
        assert not {r.namespace for r in rows} & {r.namespace for r in plan.intentions}
        for start in range(0, 248, 4):
            read_request, read_document, order, notification = rows[start : start + 4]
            assert [r.tool_id for r in rows[start : start + 4]] == [
                "procurement.request.read",
                "procurement.document.read",
                "procurement.order.create",
                "notification.template.send",
            ]
            assert len({r.task for r in rows[start : start + 4]}) == 1
            assert (order.task, order.root, order.mid, order.leaf, order.slot) == (
                notification.task,
                notification.root,
                notification.mid,
                notification.leaf,
                notification.slot,
            )
            assert order.index < notification.index and order.amount == 70000
            assert read_request.amount == read_document.amount == notification.amount == 0
        assert [r.tool_id for r in rows[-2:]] == [
            "procurement.request.read",
            "procurement.document.read",
        ]
        assert rows[-2].task == rows[-1].task


@pytest.mark.parametrize(
    "field,value",
    [
        ("clients", True),
        ("clients", 49),
        ("tool_version", 1),
        ("seeds", [2026100501]),
        ("unknown", 1),
        ("legal_tasks", 875.0),
        ("policy", {}),
        ("status", "PASS"),
    ],
)
def test_manifest_rejects_changed_or_ambiguous_inputs(tmp_path, field, value):
    data = w.load_manifest()
    data[field] = value
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        w.load_manifest(path)


def test_duplicate_fields_and_invalid_mode_seed(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"clients":50,"clients":50}')
    with pytest.raises(ValueError):
        w.load_manifest(path)
    for mode, seed in [
        ("complete", True),
        ("full", 2026100501),
        ("complete", 2026100503),
        ("complete", 2026100501.0),
    ]:
        with pytest.raises(ValueError):
            w.generate_plan(mode, seed)
