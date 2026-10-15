"""A34 release material consistency; real behavior lives in actual runs.

This node binds A34-12.01—12.05 release materials to the frozen inputs: the
experiment report, the experiments package entry, the technical report and the
workload/capability manifests must agree, list every original 30-goal ID, and
keep the honest PARTIAL / NOT_RUN markers. A missing run is never upgraded to
a PASS by this test.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

THIRTY_GOAL_IDS = (
    "M1",
    "M2",
    "M3",
    "M4",
    "M5",
    "M6",
    "M7",
    "M8",
    "M9",
    "M10",
    "M11",
    "M12",
    "M13",
    "SEC-01",
    "SEC-02",
    "SEC-03",
    "SEC-04",
    "SEC-05",
    "SEC-06",
    "SEC-07",
    "CON-01",
    "CON-02",
    "CON-03",
    "REC-01",
    "REC-02",
    "REC-03",
    "AUD-01",
    "AUD-02",
    "E2E-01",
    "ENG-01",
)


def test_final_thirty_goal_matrix_and_release_materials():
    manifest = json.loads((ROOT / "experiments/workload-v1.json").read_text())
    assert manifest["seeds"] == [2026100501, 2026100502]
    assert manifest["mode_orders"] == [
        ["staticACL", "realSM2delegation_noAtomic", "complete", "realSM2Bearer"],
        ["realSM2Bearer", "complete", "realSM2delegation_noAtomic", "staticACL"],
    ]
    assert manifest["counts"] == {"legal": 3500, "attack": 1000, "retry": 500, "warmup": 250}
    assert len(manifest["attack_classes"]) == 10
    assert manifest["tool_version"] == "1"
    assert set(manifest["tools"]) == {
        "procurement.request.read",
        "procurement.document.read",
        "procurement.order.create",
        "notification.template.send",
    }

    capabilities = json.loads((ROOT / "experiments/baseline-capabilities.json").read_text())
    assert capabilities["mode_mapping"] == {
        "staticACL": "staticACL",
        "realSM2delegation_noAtomic": "noAtomic",
        "complete": "full",
        "realSM2Bearer": "Bearer",
    }
    assert capabilities["modes"]["staticACL"]["proof"] == "NOT_APPLICABLE"
    assert capabilities["modes"]["staticACL"]["budget"] == "NOT_ENFORCED_RESEARCH_ONLY"
    assert capabilities["modes"]["noAtomic"]["proof"] == "VERIFIED"
    assert capabilities["modes"]["Bearer"]["proof"].startswith("NOT_VERIFIED")

    report = (ROOT / "docs/experiment-report.md").read_text()
    for goal in THIRTY_GOAL_IDS:
        assert goal in report, goal
    for required in ("40000", "2000", "50", "wheel", "NOT_RUN"):
        assert required in report, required
    assert "PARTIAL" in report
    assert "ACCEPTED" not in report

    readme = (ROOT / "experiments/README.md").read_text()
    for obligation in (
        "run_official_mode_repetition",
        "run_real_crypto_microbenchmark",
        "run_independent_database_trace",
        "run_independent_tls_roundtrip_reference",
    ):
        assert obligation in readme, obligation
    assert "40000" in readme and "PARTIAL" in readme
    assert "ACCEPTED" not in readme

    technical = (ROOT / "docs/technical-report.md").read_text()
    assert "PARTIAL" in technical
    assert "未接受" in technical or "尚未" in technical
    assert "SOURCE_WHEEL_PASS" not in technical
