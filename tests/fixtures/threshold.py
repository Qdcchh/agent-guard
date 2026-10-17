"""Real FROST driver and action builders for threshold approval tests.

The signer is the pinned Rust prototype; no cryptographic operation is
reimplemented in Python. Signature *verification* on the Python side uses the
mature ``cryptography`` Ed25519 implementation (same as the gateway).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from agent_guard.threshold.codec import (
    build_envelope,
    compute_params_digest,
    encode_header,
)

_REPO = Path(__file__).resolve().parents[2]
_BINARIES = (
    "tools/threshold_demo/target/release/agent-guard-threshold-demo",
    "tools/threshold_demo/target/debug/agent-guard-threshold-demo",
)


def threshold_binary() -> str:
    """Locate the compiled Rust demo; never silently skip a real FROST test."""
    explicit = os.environ.get("AGENT_GUARD_THRESHOLD_DEMO_BIN")
    candidates = [Path(explicit)] if explicit else []
    candidates += [_REPO / name for name in _BINARIES]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise RuntimeError(
        "threshold demo binary not found; run `cargo build --locked` in "
        "tools/threshold_demo or set AGENT_GUARD_THRESHOLD_DEMO_BIN"
    )


class RustThresholdSigner:
    """Trusted-dealer enrollment plus real 2-of-3 quorum signing for tests."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.parent.mkdir(parents=True, exist_ok=True)
        self._binary = threshold_binary()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self._binary, *args],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def enroll(self) -> str:
        completed = self._run("enroll", str(self.directory))
        assert completed.returncode == 0, completed.stderr
        key_hex = (self.directory / "public-key-hex.txt").read_text().strip()
        assert len(key_hex) == 64
        return key_hex

    def sign(self, action: dict, labels: tuple[str, ...] = ("signer-1", "signer-2")) -> bytes:
        action_path = self.directory / f"action-{action['action_id']}.json"
        signature_path = self.directory / f"sig-{action['action_id']}.json"
        action_path.write_text(json.dumps(action, separators=(",", ":")))
        completed = self._run(
            "sign-quorum",
            str(self.directory),
            str(signature_path),
            str(action_path),
            *labels,
        )
        assert completed.returncode == 0, completed.stderr
        return bytes.fromhex(json.loads(signature_path.read_text()))

    def sign_refused(self, action: dict, labels: tuple[str, ...]) -> subprocess.CompletedProcess:
        """Run the signer and return the real native refusal (1-of-3, duplicate)."""
        action_path = self.directory / f"refused-{'-'.join(labels)}.json"
        signature_path = self.directory / f"refused-{'-'.join(labels)}-sig.json"
        action_path.write_text(json.dumps(action, separators=(",", ":")))
        return self._run(
            "sign-quorum",
            str(self.directory),
            str(signature_path),
            str(action_path),
            *labels,
        )

    def header_for(self, action: dict, signature: bytes) -> bytes:
        return encode_header(build_envelope(action, signature))


def approval_action(
    bundle,
    *,
    action_id: str,
    policy_version: int,
    key_epoch: int,
    expires_at: int,
    tenant_id: str | None = None,
    task_id: str | None = None,
    root_grant_id: str | None = None,
    grant_id: str | None = None,
    path_grant_ids=None,
    holder_client_id: str | None = None,
    holder_kid: str | None = None,
    idempotency_key: str | None = None,
    request_id: str = "req-001",
    quote_id: str = "quote-001",
    quote_version: str = "1",
    items: tuple[tuple[str, int], ...] = (("sku-001", 1),),
    delivery_id: str = "office-001",
    amount_fen: int = 70_000,
    audience: str = "https://gateway.agent-guard.test",
    version: int = 2,
    payment_digest: str | None = None,
) -> dict:
    """Build one V2 action over a real verified invocation bundle."""
    invocation = bundle.invocation
    path = path_grant_ids
    if path is None:
        # ancestor_ids is the full root-to-parent path in root-first order.
        path = list(invocation.ancestor_ids or (invocation.root_id,))
        path.append(invocation.grant_id)
    action = {
        "version": 2,
        "tenant_id": invocation.tenant_id if tenant_id is None else tenant_id,
        "task_id": invocation.task_id if task_id is None else task_id,
        "root_grant_id": invocation.root_id if root_grant_id is None else root_grant_id,
        "grant_id": invocation.grant_id if grant_id is None else grant_id,
        "path_grant_ids": list(path),
        "holder_client_id": (
            invocation.holder_client_id if holder_client_id is None else holder_client_id
        ),
        "holder_kid": invocation.holder_kid if holder_kid is None else holder_kid,
        "audience": audience,
        "tool_id": "procurement.order.create",
        "tool_version": "1",
        "currency": "CNY",
        "policy_version": policy_version,
        "key_epoch": key_epoch,
        "action_id": action_id,
        "idempotency_key": (
            invocation.idempotency_key if idempotency_key is None else idempotency_key
        ),
        "request_id": request_id,
        "quote_id": quote_id,
        "quote_version": quote_version,
        "items": [{"sku": sku, "quantity": quantity} for sku, quantity in items],
        "delivery_id": delivery_id,
        "amount_fen": amount_fen,
        "canonical_params_sha256": compute_params_digest(
            request_id=request_id,
            quote_id=quote_id,
            quote_version=quote_version,
            items=[(sku, quantity) for sku, quantity in items],
            delivery_id=delivery_id,
        ),
        "expires_at": expires_at,
    }
    if version == 3:
        if payment_digest is None:
            raise ValueError("a V3 action needs the approved payment digest")
        action["version"] = 3
        action["payment_digest"] = payment_digest
    elif version != 2:
        raise ValueError("unsupported approval action version")
    return action
