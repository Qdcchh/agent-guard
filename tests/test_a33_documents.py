"""Document/normal CLI consistency; real behavior lives in integration runs."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_materials_commands_and_actual_demo_artifacts():
    readme = (ROOT / "README.md").read_text()
    begin, end = "# A33-REPRODUCE-BEGIN", "# A33-REPRODUCE-END"
    assert readme.count(begin) == readme.count(end) == 1
    script = readme.split(begin)[1].split(end)[0]
    assert "docker compose" in script and "agent_guard.demo normal" in script
    assert "OPENAI_API_KEY" not in script and "PYTHONPATH" not in script
    main = (ROOT / "src/agent_guard/demo/__main__.py").read_text()
    ast.parse(main)
    assert "SO_PEERCRED" in main and "SyntheticLogin" in main
    compose = json.loads((ROOT / "deploy/demo/compose.yaml").read_text())
    expected = {
        "operator",
        "as",
        "gateway",
        "did",
        "audit",
        "publisher",
        "worker",
        "planner",
        "selector",
        "executor",
        "export",
        "offline",
    }
    assert set(compose["services"]) == expected | {"pg-authority", "pg-downstream", "pg-audit"}
    for role in expected:
        service = compose["services"][role]
        assert service["user"].split(":")[0] != "0"
        assert service["read_only"] and service["cap_drop"] == ["ALL"]
        assert all("docker.sock" not in str(m) for m in service["volumes"])
    assert compose["services"]["offline"]["network_mode"] == "none"
    for name in ("docs/deployment-demo.md", "docs/technical-report.md"):
        text = (ROOT / name).read_text()
        assert "未接受" in text or "尚未完成" in text
        assert "SOURCE_WHEEL_PASS" not in text
