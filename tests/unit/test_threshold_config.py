"""Trusted threshold policy configuration: strict startup and legacy compat."""

import json

import pytest

from agent_guard.gateway.config import load_gateway_config, load_gateway_secrets, threshold_policy
from agent_guard.gateway.factory import build_app
from agent_guard.server.config import ConfigError
from agent_guard.threshold.contracts import ThresholdApprovalPolicy
from tests.unit.test_gateway_config import synthetic

VALID = {
    "group_public_key": "ab" * 32,
    "policy_version": 3,
    "key_epoch": 5,
    "max_lifetime_seconds": 300,
}


def test_absent_threshold_section_keeps_documented_legacy_behavior(tmp_path):
    _, value = synthetic(tmp_path)
    assert "threshold_approval" not in value
    config = load_gateway_config(json.dumps(value).encode())
    assert threshold_policy(json.loads(config.raw)) is None


def test_valid_threshold_policy_is_loaded_from_trusted_config(tmp_path):
    _, value = synthetic(tmp_path)
    value["threshold_approval"] = dict(VALID)
    config = load_gateway_config(json.dumps(value).encode())
    policy = threshold_policy(json.loads(config.raw))
    assert type(policy) is ThresholdApprovalPolicy
    assert policy.group_public_key == bytes.fromhex(VALID["group_public_key"])
    assert policy.policy_version == 3 and policy.key_epoch == 5
    assert policy.max_lifetime_seconds == 300


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.pop("policy_version"),
        lambda data: data.update({"extra": 1}),
        lambda data: data.update({"group_public_key": "AB" * 32}),
        lambda data: data.update({"group_public_key": "ab" * 31}),
        lambda data: data.update({"group_public_key": 5}),
        lambda data: data.update({"policy_version": True}),
        lambda data: data.update({"policy_version": 0}),
        lambda data: data.update({"key_epoch": 0}),
        lambda data: data.update({"max_lifetime_seconds": 0}),
        lambda data: data.update({"max_lifetime_seconds": 86401}),
    ],
)
def test_partial_or_malformed_threshold_config_is_rejected_at_startup(tmp_path, mutate):
    _, value = synthetic(tmp_path)
    data = dict(VALID)
    mutate(data)
    value["threshold_approval"] = data
    with pytest.raises(ConfigError):
        load_gateway_config(json.dumps(value).encode())


def test_threshold_section_must_be_an_exact_object(tmp_path):
    _, value = synthetic(tmp_path)
    value["threshold_approval"] = [VALID]
    with pytest.raises(ConfigError):
        load_gateway_config(json.dumps(value).encode())


def test_build_app_wires_the_trusted_threshold_policy(tmp_path, monkeypatch):
    directory, value = synthetic(tmp_path)
    value["threshold_approval"] = dict(VALID)
    raw = json.dumps(value, separators=(",", ":")).encode()
    monkeypatch.setattr("psycopg.connect", lambda *a, **k: pytest.fail("no database at build"))
    config = load_gateway_config(raw)
    secrets = load_gateway_secrets((directory / "secrets.json").read_bytes())
    app = build_app(
        config, secrets, gateway_dsn="offline-gateway", downstream_dsn="offline-downstream"
    )
    verifier = app._endpoint._threshold
    assert verifier is not None
    assert verifier.policy.group_public_key == bytes.fromhex(VALID["group_public_key"])
    assert verifier.policy.policy_version == VALID["policy_version"]
    app._executor.shutdown()


def test_build_app_without_threshold_stays_legacy(tmp_path, monkeypatch):
    directory, value = synthetic(tmp_path)
    raw = json.dumps(value, separators=(",", ":")).encode()
    monkeypatch.setattr("psycopg.connect", lambda *a, **k: pytest.fail("no database at build"))
    config = load_gateway_config(raw)
    secrets = load_gateway_secrets((directory / "secrets.json").read_bytes())
    app = build_app(
        config, secrets, gateway_dsn="offline-gateway", downstream_dsn="offline-downstream"
    )
    assert app._endpoint._threshold is None
    app._executor.shutdown()
