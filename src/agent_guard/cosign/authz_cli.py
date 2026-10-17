"""Bounded JSON stdio authorization process; trust is operator configuration."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.contracts.encoding import (
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.cosign.authz_domain import AuthorizationDomainSigner, CosignRefused
from agent_guard.cosign.protocol import scalar
from agent_guard.crypto.sm import load_sm2_public_key, serialize_sm2_public_key
from agent_guard.identity.resolver import RegisteredIdentity
from agent_guard.threshold.contracts import ThresholdApprovalPolicy

MAX_REQUEST = 65536
DSN_ENV = "AGENT_GUARD_AUTHZ_READONLY_DSN"


def write_public_trust(provider, policy, path):
    """Explicit trusted initialization exports public AS/registry/policy only."""
    payload = {
        "issuer": provider._issuer,
        "as_keys": {
            kid: b64url_encode(serialize_sm2_public_key(key))
            for kid, key in provider._as_keys.items()
        },
        "registrations": [
            {
                "tenant_id": r.tenant_id,
                "client_id": r.client_id,
                "did": r.did,
                "kid": r.kid,
                "spki_der": b64url_encode(r.spki_der),
                "active": r.active,
            }
            for r in provider._registrations.values()
        ],
        "policy": {
            "group_public_key": b64url_encode(policy.group_public_key),
            "policy_version": policy.policy_version,
            "key_epoch": policy.key_epoch,
            "max_lifetime_seconds": policy.max_lifetime_seconds,
            "tool_id": policy.tool_id,
            "audience": policy.audience,
            "scheme": "sm2-2p",
        },
    }
    Path(path).write_bytes(canonical_json_bytes(payload))


def load_public_trust(path, dsn):
    with Path(path).open("rb") as source:
        raw = source.read(MAX_REQUEST + 1)
    if len(raw) > MAX_REQUEST:
        raise ValueError("oversized public trust")
    data = load_strict_json(raw)
    if type(data) is not dict or set(data) != {"issuer", "as_keys", "registrations", "policy"}:
        raise ValueError("invalid public trust schema")
    if type(data["as_keys"]) is not dict or type(data["registrations"]) is not list:
        raise ValueError("invalid trust collections")
    keys = {
        kid: load_sm2_public_key(b64url_decode(value)) for kid, value in data["as_keys"].items()
    }
    registrations = {}
    for entry in data["registrations"]:
        if type(entry) is not dict or set(entry) != {
            "tenant_id",
            "client_id",
            "did",
            "kid",
            "spki_der",
            "active",
        }:
            raise ValueError("invalid registration")
        if type(entry["active"]) is not bool:
            raise ValueError("invalid registration active flag")
        registration = RegisteredIdentity(**{**entry, "spki_der": b64url_decode(entry["spki_der"])})
        key = registration.tenant_id, registration.client_id, registration.kid
        if key in registrations:
            raise ValueError("duplicate historical registration")
        registrations[key] = registration
    policy_data = data["policy"]
    policy = ThresholdApprovalPolicy(
        **{**policy_data, "group_public_key": b64url_decode(policy_data["group_public_key"])}
    )
    return PermissionSnapshotProvider(
        dsn, issuer=data["issuer"], as_keys=keys, registrations=registrations
    ), policy


class SubprocessAuthzClient:
    def __init__(self, *, share_dir, trust_file, dsn_readonly):
        self.share_dir, self.trust_file, self._dsn = str(share_dir), str(trust_file), dsn_readonly

    def respond(self, **request):
        payload = canonical_json_bytes(request)
        if len(payload) > MAX_REQUEST:
            raise CosignRefused("COSIGN_ABORTED")
        env = {**os.environ, DSN_ENV: self._dsn}
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_guard.cosign.authz_cli",
                "respond",
                "--share",
                self.share_dir,
                "--trust",
                self.trust_file,
            ],
            input=payload,
            capture_output=True,
            timeout=30,
            env=env,
            check=False,
        )
        try:
            if len(completed.stdout) > 4096 or completed.returncode not in {0, 2}:
                raise ValueError("invalid child result")
            response = load_strict_json(completed.stdout)
            if type(response) is not dict:
                raise ValueError("invalid child result")
            if set(response) == {"ok", "code"} and response["ok"] is False:
                if response["code"] not in {
                    "AUTHZ_REVOKED",
                    "AUTHZ_EXPIRED",
                    "AUTHZ_PATH_MISMATCH",
                    "AUTHZ_SCOPE",
                    "AUTHZ_OVER_BUDGET",
                    "AUTHZ_POLICY_MISMATCH",
                    "COSIGN_ABORTED",
                }:
                    raise ValueError("invalid refusal")
                raise CosignRefused(response["code"])
            if (
                completed.returncode != 0
                or set(response) != {"ok", "partial"}
                or response["ok"] is not True
            ):
                raise ValueError("invalid child result")
            partial = response["partial"]
            if type(partial) is not dict or set(partial) != {"r", "s2", "s3"}:
                raise ValueError("invalid partial schema")
            for value in partial.values():
                if (
                    type(value) is not str
                    or len(value) != 64
                    or value != value.lower()
                    or bytes.fromhex(value).hex() != value
                ):
                    raise ValueError("invalid partial encoding")
            return {key: scalar(int(value, 16)) for key, value in partial.items()}
        except CosignRefused:
            raise
        except Exception:
            raise CosignRefused("COSIGN_ABORTED") from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["respond"])
    parser.add_argument("--share", required=True)
    parser.add_argument("--trust", required=True)
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise ValueError("oversized request")
        request = load_strict_json(raw)
        if type(request) is not dict or set(request) != {
            "action",
            "leaf_access_token",
            "q1_hex",
            "now",
        }:
            raise ValueError("invalid request")
        dsn = os.environ[DSN_ENV]
        provider, policy = load_public_trust(args.trust, dsn)
        signer = AuthorizationDomainSigner(
            share_dir=args.share, dsn_readonly=dsn, snapshot_provider=provider, policy=policy
        )
        partial = signer.respond(**request)
        response = {"ok": True, "partial": {key: f"{value:064x}" for key, value in partial.items()}}
        status = 0
    except Exception as exc:
        response = {
            "ok": False,
            "code": exc.code if isinstance(exc, CosignRefused) else "COSIGN_ABORTED",
        }
        status = 2
    sys.stdout.buffer.write(canonical_json_bytes(response) + b"\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
