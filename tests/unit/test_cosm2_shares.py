"""Share persistence cannot precede confirmation; private values are never logged."""

import json
import os

import pytest

from agent_guard.cosign.protocol import AuthzParty, ExecParty
from agent_guard.cosign.shares import generate_shares, load_share


def test_roundtrip(tmp_path):
    directory = tmp_path / "keys"
    metadata = generate_shares(directory, key_epoch=1)
    assert set(metadata) == {"public_key_spki_b64url", "key_epoch"}
    assert json.loads((directory / "public.json").read_text()) == metadata
    p1 = load_share(directory / "exec", role="exec")
    p2 = load_share(directory / "authz", role="authz")
    assert "share=" not in repr(p1)
    one, two = ExecParty(p1.share, p1.public_point), AuthzParty(p2.share, p2.public_point)
    one.sign_round3(b"loaded", *two.sign_round2(b"loaded", one.sign_round1()))
    with pytest.raises(ValueError):
        load_share(directory / "exec", role="authz")
    with pytest.raises(ValueError):
        generate_shares(directory, key_epoch=2)


@pytest.mark.parametrize("target,mode", [("exec", 0o755), ("exec/share.json", 0o644)])
def test_permissions(tmp_path, target, mode):
    directory = tmp_path / "keys"
    generate_shares(directory, key_epoch=1)
    os.chmod(directory / target, mode)
    with pytest.raises(ValueError):
        load_share(directory / "exec", role="exec")


def test_failed_confirmation_zero_write(tmp_path, monkeypatch):
    def fail(*args):
        raise ValueError("confirmation failed")

    monkeypatch.setattr(ExecParty, "sign_round3", fail)
    with pytest.raises(ValueError):
        generate_shares(tmp_path / "keys", key_epoch=1)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("epoch", [True, 0, -1, 2**63, "1"])
def test_bad_epoch_zero_write(tmp_path, epoch):
    with pytest.raises(ValueError):
        generate_shares(tmp_path / "keys", key_epoch=epoch)
    assert list(tmp_path.iterdir()) == []
