"""Finite true CA/SAN HTTPS closure and attacks with full persistent oracles.

These local nodes cover N007/N028/N029/N033/N035; they do not stand in for
all119/112 or any A3 deployment/audit/scale obligation.
"""

import ssl
import time

import psycopg
import pytest

from agent_guard.contracts.encoding import load_strict_json
from agent_guard.contracts.ledger import QUERY_ENDPOINT
from agent_guard.ledger.provisioning import deactivate_principal, revoke_grant
from tests.fixtures.a23_https import (
    ReceiptScene,
    full_state,
    privacy,
    save_scene,
    unchanged_except_staged,
)
from tools.a2_receipt_demo import TOOLS

pytest_plugins = ("tests.fixtures.a23_https",)
pytestmark = pytest.mark.integration


def _positive(scene):
    results = scene.closure()
    assert len(results) == 4
    assert [entry[1]["request"]["tool_id"] for entry in results] == list(TOOLS)
    assert all(entry[1]["request"]["tool_version"] == "1" for entry in results)
    assert len({process.pid for process in scene.processes}) == 2
    assert all(process.poll() is None for process in scene.processes)
    assert [(r["holder"], r["recipient"]) for r in scene.lifecycle if r["kind"] == "exchange"] == [
        ("planner", "selector"),
        ("selector", "executor"),
    ]
    for _, _, response in results:
        privacy(scene, __import__("json").dumps(response).encode())
    return results


def test_p21_https_login_consent_pkce_two_exchanges_four_tools_publish_query_offline(https_scene):
    _positive(https_scene)
    for alias in ("notification.send", "request.read", "document.read", "order.create"):
        body = https_scene.body(TOOLS[0])
        body["tool_id"] = alias
        before = full_state(https_scene.dsn, https_scene.downstream_dsn)
        status, _, raw = https_scene.gateway(body)
        assert status == 400
        assert (
            unchanged_except_staged(before, full_state(https_scene.dsn, https_scene.downstream_dsn))
            == 0
        )
        privacy(https_scene, raw)


@pytest.mark.parametrize(
    "target,attack",
    [("as", "wrong_CA"), ("gw", "wrong_CA"), ("as", "wrong_SAN"), ("gw", "wrong_SAN")],
)
def test_wrong_ca_hostname_fixed_endpoint_refusals(https_scene, target, attack):
    before = full_state(https_scene.dsn, https_scene.downstream_dsn)
    kwargs = (
        {"context": ssl.create_default_context()}
        if attack == "wrong_CA"
        else {"host": "wrong.agent-guard.test"}
    )
    with pytest.raises(ssl.SSLCertVerificationError):
        https_scene.request(target, "GET", "/not-public", **kwargs)
    assert (
        unchanged_except_staged(before, full_state(https_scene.dsn, https_scene.downstream_dsn))
        == 0
    )
    # Positive CA and exact SAN control remains live for the same PID.
    assert https_scene.request(target, "GET", "/not-public")[0] == 404


ATTACKS = (
    "stolen_token",
    "parent_key_child_token",
    "body_tamper",
    "holder_tamper",
    "endpoint_tamper",
    "proof_replay",
    "query_proof_replay",
    "proof_expiry",
    "cross_tenant",
    "cross_task",
    "cross_grant",
    "cross_holder",
    "cross_key",
    "root_revoke",
    "mid_revoke",
    "leaf_revoke",
    "key_disable",
    "root_key_disable",
    "mid_key_disable",
    "actual_token_expiry",
    "root_expiry",
    "mid_expiry",
    "leaf_expiry",
    "public_sign",
    "public_recover",
    "public_settle",
)


@pytest.mark.parametrize("attack", ATTACKS)
def test_https_stolen_token_tamper_replay_owner_revoke_zero_effects(https_scene, attack):
    scene = https_scene
    op, _, _ = scene.close_operation(scene.body(TOOLS[0]))
    body = scene.body(TOOLS[0])
    kwargs = {}
    query = {"profile": "GM-MVP-1", "task_id": "task-001", "operation_id": op}
    if attack == "stolen_token":
        kwargs["proof"] = "stolen-token-no-holder-proof"
    elif attack == "parent_key_child_token":
        kwargs["proof"] = scene.proof(body, holder="planner")
    elif attack == "body_tamper":
        kwargs["proof"] = scene.proof(body)
        body["task_id"] = "task-other"
    elif attack == "holder_tamper":
        kwargs["proof"] = scene.proof(body, client="agent-selector")
    elif attack == "endpoint_tamper":
        kwargs["proof"] = scene.proof(body, endpoint=QUERY_ENDPOINT)
    elif attack == "proof_replay":
        kwargs["proof"] = scene.proof(body)
        assert scene.gateway(body, **kwargs)[0] == 202
    elif attack == "query_proof_replay":
        body = query
        kwargs = {"query": True, "proof": scene.proof(query, query=True)}
        assert scene.gateway(body, **kwargs)[0] == 200
    elif attack == "proof_expiry":
        kwargs["proof"] = scene.proof(body, lifetime=1)
        from agent_guard.crypto.sm import verify_compact_jws

        expiry = verify_compact_jws(
            kwargs["proof"],
            expected_type="ag-pop+jwt",
            trusted_keys={scene.kid("executor"): scene.keys["executor"].public_key()},
        )["exp"]
        until = time.monotonic() + 3
        while True:
            with psycopg.connect(scene.dsn) as conn:
                observed = conn.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[
                    0
                ]
            if observed >= expiry:
                break
            assert time.monotonic() < until
            time.sleep(0.01)
    elif attack == "cross_tenant":
        token = scene.foreign_token()
        body = dict(query, task_id="task-other")
        kwargs = {
            "query": True,
            "token": token,
            "proof": scene.proof(
                body,
                query=True,
                signing_key=scene.foreign_key,
                kid=scene.kid("outsider"),
                client="agent-outsider",
                token=token,
            ),
        }
    elif attack == "cross_task":
        body = dict(query, task_id="task-other")
        kwargs["query"] = True
    elif attack in ("cross_grant", "cross_holder"):
        body = query
        holder = "planner" if attack == "cross_grant" else "selector"
        token = scene.tokens[0 if holder == "planner" else 1]
        kwargs = {
            "query": True,
            "token": token,
            "proof": scene.proof(body, query=True, holder=holder, token=token),
        }
    elif attack == "cross_key":
        body = query
        kwargs = {"query": True, "proof": scene.proof(body, query=True, kid=scene.kid("selector"))}
    elif attack.endswith("_revoke"):
        index = {"root_revoke": 0, "mid_revoke": 1, "leaf_revoke": 2}[attack]
        with psycopg.connect(scene.dsn) as conn:
            revoke_grant(conn, grant_id=scene.claims(scene.tokens[index])["ag_grant_id"])
    elif attack.endswith("key_disable"):
        holder = {"root_key_disable": "planner", "mid_key_disable": "selector"}.get(
            attack, "executor"
        )
        with psycopg.connect(scene.dsn) as conn:
            deactivate_principal(
                conn, tenant_id="tenant-001", client_id="agent-" + holder, kid=scene.kid(holder)
            )
    elif attack == "actual_token_expiry" or attack.endswith("_expiry"):
        target = {"root_expiry": 0, "mid_expiry": 1}.get(attack, 2)
        expiry = scene.claims(scene.tokens[target])["exp"]
        deadline = time.monotonic() + 10
        while True:
            with psycopg.connect(scene.dsn) as conn:
                observed = conn.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[
                    0
                ]
            if observed >= expiry:
                break
            assert time.monotonic() < deadline, "real token expiry was not observed"
            time.sleep(0.01)
        assert observed >= expiry
    elif attack.startswith("public_"):
        kwargs["path"] = "/" + attack.removeprefix("public_")
    before = full_state(scene.dsn, scene.downstream_dsn)
    if attack.startswith("public_"):
        status, _, raw = scene.request(
            "gw", "POST", kwargs["path"], body=b"{}", headers={"Content-Type": "application/json"}
        )
    else:
        status, _, raw = scene.gateway(body, **kwargs)
    assert status in (400, 401, 403, 404, 409)
    payload = load_strict_json(raw)
    assert set(payload) == {"error"} and set(payload["error"]) == {"code", "request_id"}
    code = payload["error"]["code"]
    assert code
    expected = {
        "proof_replay": (409, "REPLAY"),
        "query_proof_replay": (409, "REPLAY"),
        "proof_expiry": (401, "STALE_REQUEST"),
        "root_revoke": (403, "REVOKED"),
        "mid_revoke": (403, "REVOKED"),
        "leaf_revoke": (403, "REVOKED"),
    }
    if attack in expected:
        assert (status, code) == expected[attack]
    staged = unchanged_except_staged(before, full_state(scene.dsn, scene.downstream_dsn))
    assert staged in (0, 1)
    privacy(scene, raw)
    if kwargs.get("proof"):
        assert kwargs["proof"].encode() not in raw
    scene.oracles.append(
        {
            "attack": attack,
            "status": status,
            "code": code,
            "allowed_staged": staged,
            "full_state_before": __import__(
                "tools.a2_receipt_demo", fromlist=["state_digest"]
            ).state_digest(before),
            "full_state_after": __import__(
                "tools.a2_receipt_demo", fromlist=["state_digest"]
            ).state_digest(full_state(scene.dsn, scene.downstream_dsn)),
        }
    )
    if (
        attack.endswith("_revoke")
        or attack.endswith("key_disable")
        or (attack.endswith("_expiry") and attack != "proof_expiry")
    ):
        before = full_state(scene.dsn, scene.downstream_dsn)
        assert scene.gateway(query, query=True)[0] in (401, 403)
        unchanged_except_staged(before, full_state(scene.dsn, scene.downstream_dsn))


def test_https_real_legal_256_sku_capacity_receipt_pipeline(ledger, dsn, downstream_dsn, request):
    scene = ReceiptScene(dsn, downstream_dsn, skus=[f"s{i:03d}" for i in range(256)])
    try:
        with scene:
            _positive(scene)
            assert len(scene.skus) == len(set(scene.skus)) == 256
            for item in scene.sizes:
                assert item["bundle_outer"] <= 1048576
                assert all(n <= 16384 for n in [*item["tokens"], item["proof"], item["receipt"]])
                assert all(
                    item[n] <= 65536
                    for n in ("request", "quote", "result", "ledger", "public", "permission_source")
                )
    finally:
        save_scene(scene, request.node.nodeid)


def test_a2_complete_receipt_closure(https_scene):
    # Local final scene, not proxy for G1/G2/P01–P21/full119 or A3.
    _positive(https_scene)
