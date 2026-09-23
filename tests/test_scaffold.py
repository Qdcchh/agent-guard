"""Packaging checks only; these tests do not establish any security property."""

from importlib.metadata import version

import agent_guard


def test_package_version_matches_distribution():
    assert agent_guard.__version__ == version("agent-guard")
