"""Real signed fixtures and ASGI transport helpers for the gateway."""

import asyncio
import time

import psycopg

from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.contracts.ledger import QUERY_ENDPOINT
from agent_guard.execution.query import AuthorizedQuery
from agent_guard.gateway.endpoint import GatewayEndpoint
from agent_guard.gateway.http_app import GatewayHttpApp


def query_bundle(env, operation_id, *, lifetime=60, proof_now=None):
    body = {"profile": "GM-MVP-1", "task_id": "task-001", "operation_id": operation_id}
    proof = sign_ag_proof(
        env.keys["executor"],
        kid=env.registrations[("tenant-001", "agent-executor")].kid,
        client_id="agent-executor",
        purpose="result-read",
        endpoint=QUERY_ENDPOINT,
        token=env.token,
        body=body,
        now=int(time.time()) if proof_now is None else proof_now,
        lifetime_seconds=lifetime,
    )
    return env.verifier.verify_query_bundle(
        env.token, proof, body=canonical_json_bytes(body), now=int(time.time())
    )


def app_for(env, dsn):
    return GatewayHttpApp(
        GatewayEndpoint(
            verifier=env.verifier,
            execution=env.adapter,
            queries=AuthorizedQuery(dsn, evidence_store=env.evidence),
        )
    )


def raw_material(dsn, bundle):
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT token_bytes,proof_bytes,body_bytes FROM ag_verified_evidence "
            "WHERE evidence_ref=%s",
            (bundle.evidence_ref,),
        ).fetchone()
    return tuple(bytes(v) for v in row)


async def asgi_request(
    app, *, path="/v1/invocations", body=b"{}", headers=None, events=None, **scope_fields
):
    scope = {
        "type": "http",
        "scheme": "https",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [(b"content-type", b"application/json")],
        **scope_fields,
    }
    messages = iter(events or [{"type": "http.request", "body": body}])
    sent = []

    async def receive():
        return next(messages)

    async def send(event):
        sent.append(event)

    await app(scope, receive, send)
    return sent[0]["status"], load_strict_json(sent[1]["body"]), dict(sent[0]["headers"])


def request(app, **kwargs):
    return asyncio.run(asgi_request(app, **kwargs))


def state(dsn, *, proofs=True):
    names = [
        "ag_grants",
        "ag_operations",
        "ag_ledger_events",
        "ag_ledger_event_nodes",
        "ag_receipt_outbox",
        "ag_execution_leases",
        "ag_operation_evidence",
        "ag_operation_review_flags",
    ]
    if proofs:
        names.append("ag_proofs")
    with psycopg.connect(dsn) as conn:
        return {
            name: conn.execute(
                f"SELECT row_to_json(t)::text FROM {name} t ORDER BY row_to_json(t)::text"
            ).fetchall()
            for name in names
        }


def config_document(env):
    """Operator public snapshots; no AS/agent private key is serialized."""
    import json
    from dataclasses import asdict

    from agent_guard.identity.resolver import did_web_url
    from agent_guard.server.__main__ import _did_document, _public_pem

    return json.loads(
        json.dumps(
            {
                "issuer": "https://auth.agent-guard.test",
                "as_keys": {"as-sign-1": _public_pem(env.as_key)},
                "identities": [
                    {
                        "tenant_id": r.tenant_id,
                        "client_id": r.client_id,
                        "did": r.did,
                        "kid": r.kid,
                        "spki_pem": _public_pem(env.keys[r.client_id.removeprefix("agent-")]),
                        "current": True,
                    }
                    for r in env.registrations.values()
                ],
                "identity_allowed_hosts": ["identity.agent-guard.test"],
                "did_documents": {
                    did_web_url(r.did): _did_document(
                        r.did, r.kid, r.spki_der, delegating=r.client_id != "agent-executor"
                    )
                    for r in env.registrations.values()
                },
                "catalog": {
                    name: [asdict(v) for v in getattr(env.service._catalog, "_" + name).values()]
                    for name in (
                        "requests",
                        "documents",
                        "quotes",
                        "deliveries",
                        "templates",
                        "recipients",
                    )
                },
                "secrets_path": "secrets.json",
                "request_timeout_seconds": 20,
                "max_workers": 8,
            }
        )
    )


def signed_env_window(dsn, downstream_dsn, window, *, cross_second=False, observations=None):
    """Real AS issuance with short root/mid/leaf windows, never forged DTOs.

    Child expiry cannot exceed its parent. Root/mid negative controls therefore
    intentionally expire the dependent leaf/token too; the chosen parent's
    exact persisted deadline is observed rather than claimed to be isolated.
    """
    import pytest

    from agent_guard.crypto.sm import verify_compact_jws
    from tests.integration import test_verified_execution as original

    root = original._root
    form = original._form

    def short_root(*args, approved_overrides=None):
        approved = dict(approved_overrides or {})
        if window == "root":
            approved["task_expires_at"] = int(time.time()) + 8
        return root(*args, approved_overrides=approved)

    def short_form(as_key, token, **kwargs):
        parent = verify_compact_jws(
            token,
            expected_type="ag-at+jwt",
            trusted_keys={"as-sign-1": as_key.public_key()},
        )
        if cross_second and parent["ag_delegation_remaining"] == 2:
            bound = time.monotonic() + 2
            while int(time.time()) <= parent["iat"]:
                assert time.monotonic() < bound, "real second boundary was not reached"
                time.sleep(0.01)
        now = int(time.time())
        requested = kwargs.get("ttl", 180)
        if window == "root":
            requested = min(requested, 8)
        elif window == "mid":
            requested = min(requested, 6)
        # Real AS computes child expiry at its own current time. Leave two
        # seconds for signing/DB setup, rather than borrowing the parent's
        # original lifetime after a real second boundary has elapsed.
        remaining = parent["exp"] - now - 2
        assert remaining > 0, "short fixture exhausted its parent issuance margin"
        kwargs["ttl"] = min(requested, remaining)
        if observations is not None:
            observations.append(
                {
                    "parent_iat": parent["iat"],
                    "parent_exp": parent["exp"],
                    "remaining_depth": parent["ag_delegation_remaining"],
                    "now": now,
                    "requested_ttl": requested,
                    "ttl": kwargs["ttl"],
                }
            )
        return form(as_key, token, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(original, "_root", short_root)
        patch.setattr(original, "_form", short_form)
        return original.signed_env(dsn, downstream_dsn, leaf_ttl=3)
