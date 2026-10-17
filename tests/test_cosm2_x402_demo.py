"""COSM2 x402 operator selection has an explicit, compatible default."""

from tools import x402_gateway_demo as demo


def test_default_and_explicit_scheme_are_routed(monkeypatch):
    calls = []
    monkeypatch.setenv("AGENT_GUARD_X402_DEMO_DSN", "synthetic-test-target")

    def run(dsn, *, approval_scheme):
        calls.append((dsn, approval_scheme))
        return 0, {
            "run_id": "test-run",
            "cases": [],
            "operations": 0,
            "approvals": 0,
            "orders": 0,
            "payments": 0,
            "transactions": 0,
            "resources_remaining": [],
        }

    monkeypatch.setattr(demo, "run_demo", run)
    assert demo.main([]) == 0
    assert demo.main(["--approval-scheme", "sm2-2p"]) == 0
    assert calls == [
        ("synthetic-test-target", "frost-ed25519"),
        ("synthetic-test-target", "sm2-2p"),
    ]
