"""The B demo never guesses or mutates an unspecified database."""

from tests.demo_b_flow import main


def test_demo_requires_explicit_test_dsn(monkeypatch, capsys):
    monkeypatch.delenv("AGENT_GUARD_TEST_DATABASE_URL", raising=False)
    assert main() == 2
    assert "refusing to guess a database" in capsys.readouterr().out
