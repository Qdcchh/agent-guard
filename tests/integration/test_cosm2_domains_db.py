"""Real signed ancestry, SELECT-only principal, and genuine JSON stdio process."""

import time

import psycopg
import pytest

from agent_guard.cosign.authz_domain import CosignRefused
from agent_guard.cosign.encoding import point_to_hex, signature_rs_to_der
from agent_guard.cosign.protocol import ExecParty
from agent_guard.crypto.sm import load_sm2_public_key, verify_sm2_message
from agent_guard.threshold.codec import compute_params_digest, cosm2_message
from tests.fixtures.cosm2 import CosignSigner, approval_action, readonly_provider, readonly_role
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


@pytest.fixture()
def domain_env(ledger, dsn, downstream_dsn, tmp_path):
    env = signed_env(dsn, downstream_dsn)
    with readonly_role(dsn) as ro:
        signer = CosignSigner(
            tmp_path / "keys",
            dsn_readonly=ro,
            snapshot_provider=readonly_provider(env.verifier._permission_provider, ro),
            catalog=env.service._catalog,
            token_provider=lambda bundle: env.token,
        )
        signer.enroll()
        bundle = env.bundle()
        action = approval_action(
            bundle,
            action_id="cosm2-domains",
            policy_version=1,
            key_epoch=1,
            expires_at=int(time.time()) + 60,
            version=3,
            payment_digest="0" * 64,
        )
        yield env, signer, bundle, action, ro


def respond(signer, token, action, q1=None):
    q1 = q1 or point_to_hex(ExecParty().sign_round1())
    return signer.authz_signer.respond(
        action=action, leaf_access_token=token, q1_hex=q1, now=int(time.time())
    )


def test_real_policy_domains(domain_env):
    env, signer, bundle, action, ro = domain_env
    sig = signer.sign(action, bundle=bundle)
    verify_sm2_message(
        load_sm2_public_key(signer.policy.group_public_key),
        cosm2_message(action),
        signature_rs_to_der(sig),
    )
    assert signer.exec_signer._party._k1 is None
    assert set(signer.last_timing_ms) == {"round1", "round2", "round3", "total"}
    with psycopg.connect(ro) as conn:
        assert conn.execute("SELECT count(*) FROM ag_grants").fetchone()[0] == 3
    for sql in (
        "UPDATE ag_grants SET amount_limit=amount_limit",
        "DELETE FROM ag_grants WHERE false",
        "INSERT INTO ag_grants SELECT * FROM ag_grants WHERE false",
        "SELECT * FROM ag_verified_evidence",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(ro) as conn:
            conn.execute(sql)


@pytest.mark.parametrize(
    "case,code",
    [
        ("policy", "AUTHZ_POLICY_MISMATCH"),
        ("expired", "AUTHZ_EXPIRED"),
        ("holder", "AUTHZ_PATH_MISMATCH"),
        ("scope", "AUTHZ_SCOPE"),
        ("revoked", "AUTHZ_REVOKED"),
        ("budget", "AUTHZ_OVER_BUDGET"),
        ("invalid_token", "AUTHZ_PATH_MISMATCH"),
        ("malformed", "AUTHZ_PATH_MISMATCH"),
        ("bad_q1", "COSIGN_ABORTED"),
    ],
)
def test_all_refusals_before_curve(domain_env, dsn, case, code):
    env, signer, bundle, action, ro = domain_env
    token = env.token
    if case == "policy":
        action["policy_version"] += 1
    elif case == "expired":
        action["expires_at"] = int(time.time()) - 1
    elif case == "holder":
        action["holder_kid"] = "wrong-kid"
    elif case == "scope":
        action["request_id"] = "req-forbidden"
        action["canonical_params_sha256"] = compute_params_digest(
            request_id=action["request_id"],
            quote_id=action["quote_id"],
            quote_version=action["quote_version"],
            items=[(x["sku"], x["quantity"]) for x in action["items"]],
            delivery_id=action["delivery_id"],
        )
    elif case in {"revoked", "budget"}:
        with psycopg.connect(dsn) as conn:
            if case == "revoked":
                conn.execute(
                    "UPDATE ag_grants SET revoked=true,revoked_at=clock_timestamp() "
                    "WHERE grant_id=%s",
                    (bundle.invocation.root_id,),
                )
            else:
                conn.execute(
                    "UPDATE ag_grants SET amount_reserved=40000 WHERE grant_id=%s",
                    (bundle.invocation.root_id,),
                )
    elif case == "invalid_token":
        token = token[:-1] + ("A" if token[-1] != "A" else "B")
    elif case == "malformed":
        action["unknown"] = True
    with pytest.raises(CosignRefused) as error:
        respond(signer, token, action, "04" + "0" * 128)
    assert error.value.code == code
    assert signer.authz_signer.sign_count == 0


@pytest.mark.parametrize(
    "field,value", [("amount_fen", 1), ("idempotency_key", "other"), ("payment_digest", "a" * 64)]
)
def test_execution_mismatch_before_nonce(domain_env, field, value):
    env, signer, bundle, action, ro = domain_env
    action[field] = value
    assert signer.sign_refused(action, bundle=bundle).code == "EXEC_MISMATCH"
    assert signer.exec_signer.round1_count == signer.authz_signer.sign_count == 0
    assert signer.exec_signer._party._k1 is None


def test_execution_clears_nonce_when_authorization_refuses(domain_env):
    env, signer, bundle, action, ro = domain_env
    action["policy_version"] += 1
    assert signer.sign_refused(action, bundle=bundle).code == "AUTHZ_POLICY_MISMATCH"
    assert signer.exec_signer.round1_count == 1
    assert signer.exec_signer._party._k1 is None
