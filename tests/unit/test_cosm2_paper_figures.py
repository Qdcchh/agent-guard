"""Source integrity and refusal to manufacture matrix evidence."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "tests/fixtures/cosm2_paper_evidence"
SPEC = importlib.util.spec_from_file_location("figures", ROOT / "tools/cosm2_paper_figures.py")
figures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(figures)


def test_partial_evidence_only():
    index = figures.build_index(DATA_ROOT)
    assert len(index["cells"]) == 56
    observed = [cell for cell in index["cells"] if cell["status"] == "OBSERVED"]
    assert len(observed) == 3
    assert all(cell["scheme"] == "frost-ed25519" for cell in observed)
    assert all(cell["sha256"] and cell["run_id"] and cell["command"] for cell in observed)
    assert all(cell["code"] is None for cell in index["cells"] if cell["scheme"] == "sm2-2p")


@pytest.mark.parametrize(
    "change", ["scheme", "unknown_code", "bool_status", "extra", "duplicate_case"]
)
def test_bad_source_refused(tmp_path, change):
    result = json.loads((DATA_ROOT / figures.SOURCE).read_text())
    if change == "scheme":
        result["profile"] = "AG-COSM2-APPROVAL-1"
    elif change == "unknown_code":
        result["cases"][2]["code"] = "MADE_UP"
    elif change == "bool_status":
        result["cases"][2]["http_status"] = True
    elif change == "extra":
        result["unexpected"] = "unsafe"
    else:
        result["cases"].append(result["cases"][2])
    path = tmp_path / figures.SOURCE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError):
        figures.build_index(tmp_path)


def test_duplicate_json_key_refused():
    with pytest.raises(ValueError, match="duplicate"):
        figures.strict_json('{"passed":true,"passed":false}')


def test_missing_evidence_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        figures.build_index(tmp_path)


LIVE_RUN = "b944d1ab-4525-46a9-8bb1-1a9dbdbdca00"


def test_actual_run_index_maps_only_observed_locations():
    index = figures.build_index(DATA_ROOT, cosm2_run=LIVE_RUN)
    assert index["status"] == "OBSERVED_FIXED_RUN"
    assert len(index["cells"]) == 28
    observed = [cell for cell in index["cells"] if cell["status"] == "OBSERVED"]
    assert len(observed) == 8
    assert all(cell["sha256"] and cell["run_id"] == LIVE_RUN for cell in index["cells"])
    assert all(
        cell["status"] == "NOT_TRIGGERED" for cell in index["cells"] if cell["location"] == "AS"
    )
    assert (
        next(cell for cell in observed if cell["attack"] == "盗令牌")["code"] == "INVALID_SIGNATURE"
    )
    assert len(index["observations"]) == 9


@pytest.fixture
def live_source(tmp_path):
    relative = Path("artifacts/cosm2-gateway-demo-live") / LIVE_RUN
    folder = tmp_path / relative
    folder.mkdir(parents=True)
    for name in ("result.json", "negative-matrix.json"):
        (folder / name).write_bytes((DATA_ROOT / relative / name).read_bytes())
    return tmp_path, folder


@pytest.mark.parametrize(
    "change",
    [
        "wrong_run",
        "failed_run",
        "unclean",
        "unknown_result",
        "bool_count",
        "bool_version",
        "extra_observation",
        "duplicate_case",
        "unknown_case",
        "unknown_code",
        "wrong_location",
        "failed_observation",
        "changed_sign_count",
        "changed_counters",
        "bool_snapshot_count",
        "bool_counter",
        "missing_ancestor",
        "duplicate_json",
        "symlink",
    ],
)
def test_invalid_actual_observations_cannot_supply_figure(live_source, change):
    root, folder = live_source
    result_path, matrix_path = folder / "result.json", folder / "negative-matrix.json"
    result = json.loads(result_path.read_text())
    matrix = json.loads(matrix_path.read_text())
    observation = matrix["observations"][0]
    if change == "wrong_run":
        matrix["run_id"] = "00000000-0000-0000-0000-000000000000"
    elif change == "failed_run":
        result["passed"] = False
    elif change == "unclean":
        result["resources_remaining"] = 1
    elif change == "unknown_result":
        result["extra"] = "TEST_ONLY"
    elif change == "bool_count":
        result["orders"] = True
    elif change == "bool_version":
        matrix["version"] = True
    elif change == "extra_observation":
        observation["private"] = "TEST_ONLY"
    elif change == "duplicate_case":
        matrix["observations"][1] = observation
    elif change == "unknown_case":
        observation["case_id"] = "unknown"
    elif change == "unknown_code":
        observation["observed_code"] = "MADE_UP"
    elif change == "wrong_location":
        observation["location"] = "AS"
    elif change == "failed_observation":
        observation["passed"] = False
    elif change == "changed_sign_count":
        observation["after"]["authz_sign_count"] += 1
    elif change == "changed_counters":
        observation["after"]["counters"][0][1] += 1
    elif change == "bool_snapshot_count":
        observation["before"]["orders"] = False
    elif change == "bool_counter":
        observation["before"]["counters"][0][0] = False
    elif change == "missing_ancestor":
        observation["before"]["counters"].pop()
    result_path.write_text(json.dumps(result))
    matrix_path.write_text(json.dumps(matrix))
    if change == "duplicate_json":
        matrix_path.write_text(
            matrix_path.read_text().replace('"version": 1', '"version": 1,"version": 1')
        )
    elif change == "symlink":
        target = folder / "other.json"
        matrix_path.rename(target)
        matrix_path.symlink_to(target)
    with pytest.raises(ValueError):
        figures.build_index(root, cosm2_run=LIVE_RUN)


def test_actual_b9_effect_refusals_are_provenance_outside_four_columns():
    run = "5efd0b13-bf3e-4062-b8ed-0048e110dbb9"
    index = figures.build_index(DATA_ROOT, cosm2_run=run)
    assert len(index["cells"]) == 28
    assert len(index["additional_effect_observations"]) == 3
    assert all(
        o["observed_code"] == "DOWNSTREAM_UNAUTHORIZED"
        for o in index["additional_effect_observations"]
    )
    assert all(cell["location"] in figures.COLS for cell in index["cells"])


@pytest.mark.parametrize(
    "change", ["partial_effect_set", "effect_code", "extra_order", "effect_bool"]
)
def test_effect_observations_remain_strict(tmp_path, change):
    run = "5efd0b13-bf3e-4062-b8ed-0048e110dbb9"
    relative = Path("artifacts/cosm2-gateway-demo-live") / run
    folder = tmp_path / relative
    folder.mkdir(parents=True)
    for name in ("result.json", "negative-matrix.json"):
        (folder / name).write_bytes((DATA_ROOT / relative / name).read_bytes())
    path = folder / "negative-matrix.json"
    matrix = json.loads(path.read_text())
    effect = next(o for o in matrix["observations"] if o["case_id"].startswith("downstream-"))
    if change == "partial_effect_set":
        matrix["observations"].remove(effect)
    elif change == "effect_code":
        effect["observed_code"] = "INVALID_SIGNATURE"
    elif change == "extra_order":
        effect["before"]["orders"] = effect["after"]["orders"] = 2
    else:
        effect["before"]["orders"] = effect["after"]["orders"] = True
    path.write_text(json.dumps(matrix))
    with pytest.raises(ValueError):
        figures.build_index(tmp_path, cosm2_run=run)
