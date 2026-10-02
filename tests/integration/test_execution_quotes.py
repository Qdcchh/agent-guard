"""A2-P11 and the checkpoint-1 cost-candidate obligations OBL01/OBL02.

The deterministic race uses ``threading.Barrier``/``threading.Event`` with two
independent connections: the first accept observes a candidate *miss*, blocks
inside quote resolution, the second accept commits the business key, only then
does the quote disappear and the first accept safely re-check the candidate.
No sleeps and no "hope the scheduler agrees" ordering.
"""

from __future__ import annotations

import threading

import psycopg
import pytest

from agent_guard.contracts.execution import ExecutionError, ExecutionErrorCode
from agent_guard.contracts.ledger import AcceptDisposition, ErrorCode, LedgerError
from agent_guard.tools import policy
from tests.fixtures.dbstate import fetch_counters, fetch_counts
from tests.fixtures.execution import (
    ORDER_AMOUNT_FEN,
    QUOTE_ID,
    QUOTE_VERSION,
    REQUEST_ID,
    build_env,
    order_params,
    permission_for,
)

pytestmark = pytest.mark.integration


def _retry(env, key: str, *, jti: str, **kwargs):
    inv = env.tree.invocation(
        idempotency_key=key,
        jti=jti,
        tool_id="procurement.order.create",
        params=order_params(**kwargs),
    )
    return env.service.accept_invocation(inv, env.permission())


# ------------------------------------------------------------------- P11


def test_p11_existing_intent_survives_quote_edit_and_delete(a2):
    """P11: an accepted intent keeps its original cost and snapshot for ever."""
    key = "p11-existing"
    first = _retry(a2, key, jti="jti-p11-1")
    assert first.disposition is AcceptDisposition.CREATED
    original_snapshot = first.cost.quote_snapshot

    # the current quote is edited and then deleted entirely
    from agent_guard.tools.catalog import CatalogQuote, CatalogQuoteLine

    a2.catalog.replace_quote(
        CatalogQuote(
            QUOTE_ID,
            QUOTE_VERSION,
            "another-supplier",
            REQUEST_ID,
            (CatalogQuoteLine("sku-001", 1, 1),),
        )
    )
    a2.catalog.remove_quote(QUOTE_ID, QUOTE_VERSION)

    retried = _retry(a2, key, jti="jti-p11-2")
    assert retried.disposition is AcceptDisposition.EXISTING
    assert retried.operation_id == first.operation_id
    assert retried.cost.amount_fen == ORDER_AMOUNT_FEN
    assert retried.cost.quote_snapshot == original_snapshot
    assert retried.accepted_at == first.accepted_at

    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 1
    counters = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    assert counters["amount_reserved"] == ORDER_AMOUNT_FEN
    assert counters["calls_reserved"] == 1

    stored = retried.cost.quote_snapshot
    assert b"supplier-001" in stored  # the first accept's supplier is preserved


def test_p11_new_key_requires_a_valid_current_quote(a2):
    """P11: a brand new business key is refused once the quote is gone."""
    a2.catalog.remove_quote(QUOTE_ID, QUOTE_VERSION)
    inv = a2.tree.invocation(
        idempotency_key="p11-new-key",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    with pytest.raises(ExecutionError) as excinfo:
        a2.service.accept_invocation(inv, a2.permission())
    assert excinfo.value.code is ExecutionErrorCode.QUOTE_INVALID
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 0
    for grant_id in (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id):
        counters = fetch_counters(a2.gateway_dsn, grant_id)
        assert counters["amount_reserved"] == 0
        assert counters["calls_reserved"] == 0


def test_p11_wrong_quote_version_amount_or_association_is_refused(a2):
    """P11: a wrong quote version, SKU or delivery is never silently accepted."""
    for kwargs in (
        {"quote_version": "2"},  # a version that exists but is not granted
        {"quote_version": "9"},  # a version that does not exist at all
        {"quote_id": "quote-999"},
        {"items": (("sku-999", 1),)},
        {"items": (("sku-001", 9),)},  # over the granted max_quantity
        {"delivery_id": "office-999"},
        {"request_id": "req-999"},
    ):
        inv = a2.tree.invocation(
            idempotency_key=f"p11-wrong-{sorted(kwargs)}-{id(kwargs)}",
            tool_id="procurement.order.create",
            params=order_params(**kwargs),
        )
        with pytest.raises(ExecutionError) as excinfo:
            a2.service.accept_invocation(inv, a2.permission())
        assert excinfo.value.code in (
            ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED,
            ExecutionErrorCode.QUOTE_INVALID,
            ExecutionErrorCode.RESOURCE_NOT_FOUND,
        ), kwargs

    # nothing was reserved and nothing executed
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 0
    for grant_id in (a2.tree.root_id, a2.tree.mid_id, a2.tree.leaf_id):
        counters = fetch_counters(a2.gateway_dsn, grant_id)
        assert counters["amount_reserved"] == 0
        assert counters["calls_reserved"] == 0


def test_p11_changed_grant_holder_or_params_stay_conflicts(a2):
    """P11: the same key under another grant/holder/params is never a success."""
    key = "p11-conflict"
    first = _retry(a2, key, jti="jti-p11-c1")
    assert first.disposition is AcceptDisposition.CREATED

    other_params = a2.tree.invocation(
        idempotency_key=key,
        jti="jti-p11-c2",
        tool_id="procurement.order.create",
        params=order_params(items=(("sku-001", 2),)),
    )
    with pytest.raises(LedgerError) as excinfo:
        a2.service.accept_invocation(other_params, a2.permission())
    assert excinfo.value.code is ErrorCode.IDEMPOTENCY_CONFLICT

    other_grant = a2.tree.invocation(
        idempotency_key=key,
        jti="jti-p11-c3",
        grant_id=a2.tree.mid_id,
        ancestor_ids=(a2.tree.root_id,),
        holder=a2.tree.selector,
        tool_id="procurement.order.create",
        params=order_params(),
    )
    with pytest.raises(LedgerError) as excinfo:
        a2.service.accept_invocation(other_grant, permission_for(a2.tree, grant_id=a2.tree.mid_id))
    assert excinfo.value.code is ErrorCode.IDEMPOTENCY_CONFLICT

    # a replayed proof is REPLAY, never an idempotent success
    replay = a2.tree.invocation(
        idempotency_key=key,
        jti="jti-p11-c1",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    with pytest.raises(LedgerError) as excinfo:
        a2.service.accept_invocation(replay, a2.permission())
    assert excinfo.value.code is ErrorCode.REPLAY

    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 1


def test_p11_revocation_still_blocks_new_intents(a2):
    """P11: revocation is checked dynamically even for a well-formed request."""
    from agent_guard.ledger import provisioning as prov

    with psycopg.connect(a2.gateway_dsn) as conn:
        prov.revoke_grant(conn, a2.tree.leaf_id)
    inv = a2.tree.invocation(
        idempotency_key="p11-revoked",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    with pytest.raises(LedgerError) as excinfo:
        a2.service.accept_invocation(inv, a2.permission())
    assert excinfo.value.code is ErrorCode.REVOKED
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 0


# ------------------------------------------------------------------ OBL01


def test_obl01_candidate_lookup_never_requires_a_current_quote(a2):
    """OBL01: static/trusted-set checks come first and no quote is needed there.

    The candidate lookup and the hit path both run with the current quote
    completely gone; the hit still goes through ``ExecutionLedger.accept`` for
    the lock-after dynamic checks, the proof registration and the full intent
    comparison.
    """
    key = "obl01-candidate"
    first = _retry(a2, key, jti="jti-obl01-1")
    assert first.disposition is AcceptDisposition.CREATED
    a2.catalog.remove_quote(QUOTE_ID, QUOTE_VERSION)

    # the same key with a fresh proof: candidate hit -> A1 accept -> EXISTING
    retried = _retry(a2, key, jti="jti-obl01-2")
    assert retried.disposition is AcceptDisposition.EXISTING
    assert retried.operation_id == first.operation_id
    assert retried.cost.amount_fen == ORDER_AMOUNT_FEN

    # the fresh proof was registered and linked to the same operation
    with psycopg.connect(a2.gateway_dsn) as conn:
        rows = conn.execute(
            "SELECT proof_jti, operation_id FROM ag_proofs ORDER BY proof_jti"
        ).fetchall()
    assert [r[0] for r in rows] == ["jti-obl01-1", "jti-obl01-2"]
    assert {r[1] for r in rows} == {first.operation_id}

    # and the dynamic checks still run on the hit path
    replay = a2.tree.invocation(
        idempotency_key=key,
        jti="jti-obl01-2",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    with pytest.raises(LedgerError) as excinfo:
        a2.service.accept_invocation(replay, a2.permission())
    assert excinfo.value.code is ErrorCode.REPLAY


def test_obl01_static_authorization_rejects_before_any_candidate_lookup(a2):
    """OBL01: an unauthorized tool is refused before the candidate is read."""
    inv = a2.tree.invocation(
        idempotency_key="obl01-static",
        tool_id="procurement.order.create",
        params=order_params(items=(("sku-002", 1),)),
    )
    with pytest.raises(ExecutionError) as excinfo:
        a2.service.accept_invocation(inv, a2.permission())
    assert excinfo.value.code is ExecutionErrorCode.RESOURCE_NOT_AUTHORIZED
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 0
    assert fetch_counts(a2.gateway_dsn)["ag_proofs"] == 0  # nothing reached the ledger


# ------------------------------------------------------------------ OBL02


def _deterministic_miss_race(a2, monkeypatch, failure: str):
    """First accept misses the candidate, blocks, second accept commits, then
    the resolution fails and the first accept safely re-checks the candidate."""
    key = f"obl02-{failure}"
    original_resolve = policy.resolve_tool_resources
    calls = {"n": 0}
    first_resolve_started = threading.Event()
    second_done = threading.Event()

    def blocking_resolve(catalog, *, tenant_id, task_id, tool_id, params, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:  # the accept that observed the candidate miss
            first_resolve_started.set()
            assert second_done.wait(30), "the second accept never finished"
            if failure == "quote":
                a2.catalog.remove_quote(QUOTE_ID, QUOTE_VERSION)
                raise ExecutionError(ExecutionErrorCode.QUOTE_INVALID, "quote disappeared")
            a2.catalog.remove_request(REQUEST_ID)  # the resource disappears
            raise ExecutionError(ExecutionErrorCode.RESOURCE_NOT_FOUND, "request disappeared")
        return original_resolve(
            catalog, tenant_id=tenant_id, task_id=task_id, tool_id=tool_id, params=params, **kwargs
        )

    monkeypatch.setattr(policy, "resolve_tool_resources", blocking_resolve)

    results: dict[str, object] = {}
    errors: dict[str, object] = {}

    def first_accept() -> None:
        env = build_env(tree=a2.tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)
        try:
            results["first"] = _retry(env, key, jti=f"jti-{key}-a")
        except Exception as exc:  # pragma: no cover - surfaced below
            errors["first"] = exc

    def second_accept() -> None:
        assert first_resolve_started.wait(30), "the first accept never reached resolution"
        env = build_env(tree=a2.tree, gateway_dsn=a2.gateway_dsn, downstream_dsn=a2.downstream_dsn)
        try:
            results["second"] = _retry(env, key, jti=f"jti-{key}-b")
            second_done.set()
        except Exception as exc:  # pragma: no cover - surfaced below
            errors["second"] = exc
            second_done.set()

    threads = [
        threading.Thread(target=first_accept),
        threading.Thread(target=second_accept),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    second = results["second"]
    first = results["first"]
    assert second.disposition is AcceptDisposition.CREATED
    assert first.disposition is AcceptDisposition.EXISTING
    assert first.operation_id == second.operation_id
    assert first.cost.amount_fen == second.cost.amount_fen
    assert first.cost.quote_snapshot == second.cost.quote_snapshot
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1
    assert fetch_counts(a2.gateway_dsn)["ag_ledger_events"] == 1
    counters = fetch_counters(a2.gateway_dsn, a2.tree.root_id)
    assert counters["amount_reserved"] == ORDER_AMOUNT_FEN
    assert counters["calls_reserved"] == 1
    return first


@pytest.mark.parametrize("failure", ["quote", "resource"])
def test_obl02_deterministic_miss_accept_gone_then_safe_recheck(a2, monkeypatch, failure):
    """OBL02: any resource/quote resolution failure safely re-checks the
    candidate instead of rejecting a key another accept just committed."""
    _deterministic_miss_race(a2, monkeypatch, failure)


def test_obl02_recheck_still_refuses_new_keys_and_replays(a2, monkeypatch):
    """OBL02: the safe re-check never turns a genuinely new key into a success."""
    original_resolve = policy.resolve_tool_resources

    def failing_resolve(catalog, *, tenant_id, task_id, tool_id, params, **kwargs):
        raise ExecutionError(ExecutionErrorCode.QUOTE_INVALID, "quote gone")

    monkeypatch.setattr(policy, "resolve_tool_resources", failing_resolve)

    inv = a2.tree.invocation(
        idempotency_key="obl02-new-key",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    with pytest.raises(ExecutionError) as excinfo:
        a2.service.accept_invocation(inv, a2.permission())
    assert excinfo.value.code is ExecutionErrorCode.QUOTE_INVALID
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 0

    monkeypatch.setattr(policy, "resolve_tool_resources", original_resolve)
    first = _retry(a2, "obl02-new-key", jti="jti-obl02-new")
    assert first.disposition is AcceptDisposition.CREATED

    # a replayed proof is still refused even though the key now exists
    monkeypatch.setattr(policy, "resolve_tool_resources", failing_resolve)
    replay = a2.tree.invocation(
        idempotency_key="obl02-new-key",
        jti="jti-obl02-new",
        tool_id="procurement.order.create",
        params=order_params(),
    )
    with pytest.raises(LedgerError) as excinfo:
        a2.service.accept_invocation(replay, a2.permission())
    assert excinfo.value.code is ErrorCode.REPLAY


def test_obl02_changed_intent_is_still_refused_after_the_recheck(a2, monkeypatch):
    """OBL02: the re-check path enforces the full intent comparison."""
    key = "obl02-intent"
    first = _retry(a2, key, jti="jti-obl02-intent-1")
    assert first.disposition is AcceptDisposition.CREATED

    def failing_resolve(catalog, *, tenant_id, task_id, tool_id, params, **kwargs):
        raise ExecutionError(ExecutionErrorCode.QUOTE_INVALID, "quote gone")

    monkeypatch.setattr(policy, "resolve_tool_resources", failing_resolve)
    altered = a2.tree.invocation(
        idempotency_key=key,
        jti="jti-obl02-intent-2",
        tool_id="procurement.order.create",
        params=order_params(items=(("sku-001", 2),)),
    )
    with pytest.raises(LedgerError) as excinfo:
        a2.service.accept_invocation(altered, a2.permission())
    assert excinfo.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert fetch_counts(a2.gateway_dsn)["ag_operations"] == 1
