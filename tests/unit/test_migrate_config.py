"""Migrations directory override for installed deployments (no database)."""

from pathlib import Path

from agent_guard.ledger.migrate import DEFAULT_MIGRATIONS_DIR, _migrations_dir


def test_default_migrations_dir_points_at_a_real_migrations_copy():
    assert DEFAULT_MIGRATIONS_DIR.name == "migrations"
    assert (DEFAULT_MIGRATIONS_DIR / "001_init.sql").is_file()


def test_migrations_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_GUARD_MIGRATIONS_DIR", str(tmp_path))
    assert _migrations_dir() == Path(tmp_path)
    monkeypatch.delenv("AGENT_GUARD_MIGRATIONS_DIR")
    # Without an override the default is always a directory named "migrations"
    # (the repository copy in-development, or the installed layout otherwise).
    assert _migrations_dir().name == "migrations"
