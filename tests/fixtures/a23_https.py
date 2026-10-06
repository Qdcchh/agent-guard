"""Actual joint AS/GW HTTPS scene; no synthetic VerifiedInvocation or root mint."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from tools.a2_receipt_demo import ReceiptScene, full_state


def unchanged_except_staged(before, after):
    """All persistent families exact; separately count optional STAGED verifier facts."""
    old, new = json.loads(json.dumps(before)), json.loads(json.dumps(after))
    prior = old["gateway"].pop("ag_verified_evidence")
    current = new["gateway"].pop("ag_verified_evidence")
    if old != new:
        changed = [
            name for domain in old for name in old[domain] if old[domain][name] != new[domain][name]
        ]
        raise AssertionError("unauthorized persistent changes: " + ",".join(changed))
    if any(row not in current for row in prior):
        raise AssertionError("original staged evidence changed")
    added = [json.loads(row[0]) for row in current if row not in prior]
    if len(added) > 1 or any(row["state"] != "STAGED" for row in added):
        raise AssertionError("unexpected verifier staging change")
    return len(added)


def privacy(scene, raw):
    """Response cannot return raw credential/evidence or private server material."""
    forbidden = [
        scene.password,
        scene.downstream_secret,
        scene.gateway_secret,
        scene.dsn,
        scene.downstream_dsn,
        *scene.tokens,
        *scene.clients.values(),
        "PRIVATE KEY",
        "Traceback",
        "token_bytes",
        "proof_bytes",
        "context_json",
    ]
    if any(value.encode() in raw for value in forbidden if value):
        raise AssertionError("public response leaked protected material")


def save_scene(scene, nodeid):
    destination = os.environ.get("A23_HTTPS_EVIDENCE")
    if not destination:
        return
    directory = Path(destination)
    directory.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(nodeid.encode()).hexdigest()[:20]
    path = directory / (key + ".json")
    # Every invocation has its own run directory; never overwrite first failures.
    if path.exists():
        raise AssertionError("scene evidence output already exists")
    path.write_text(
        json.dumps(
            {
                "nodeid": nodeid,
                "lifecycle": scene.lifecycle,
                "sizes": scene.sizes,
                "oracles": scene.oracles,
            },
            indent=2,
        )
    )


@pytest.fixture
def https_scene(ledger, dsn, downstream_dsn, request):
    callspec = getattr(request.node, "callspec", None)
    attack = callspec.params.get("attack") if callspec is not None else None
    options = {
        "actual_token_expiry": {"leaf_ttl": 3},
        "leaf_expiry": {"leaf_ttl": 3},
        "mid_expiry": {"leaf_ttl": 3, "middle_ttl": 6},
        "root_expiry": {"leaf_ttl": 3, "middle_ttl": 6, "task_ttl": 8},
    }.get(attack, {})
    scene = ReceiptScene(dsn, downstream_dsn, **options)
    try:
        with scene:
            yield scene
    finally:
        save_scene(scene, request.node.nodeid)


__all__ = [
    "ReceiptScene",
    "full_state",
    "https_scene",
    "privacy",
    "save_scene",
    "unchanged_except_staged",
]
