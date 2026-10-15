"""Pure model controls for whole-history verification, not native PG claims."""

from copy import deepcopy
from io import BytesIO

import pytest

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.evidence.task_bundle import TaskBundleError, object_id
from agent_guard.evidence.task_verify import verify_task_bundle
from tests.fixtures.a32_offline import material, rebuild


def verify(value, bundle=None):
    return verify_task_bundle(
        BytesIO(value["bundle"] if bundle is None else bundle), value["trust"], value["pin"]
    )


@pytest.mark.parametrize(
    "component",
    [
        "token",
        "proof",
        "request",
        "context",
        "source",
        "quote",
        "ledger",
        "result",
        "receipt",
        "ancestor_token",
        "journal",
        "checkpoint",
    ],
)
def test_component_and_all_node_delta_mutations(component):
    value = material()
    changed = list(value["objects"])
    n = next(i for i, (kind, _, _) in enumerate(changed) if kind == component)
    kind, ident, raw = changed[n]
    changed[n] = kind, ident, raw[:-1] + bytes([raw[-1] ^ 1])
    with pytest.raises(TaskBundleError):
        verify(value, rebuild(value, changed))


@pytest.mark.parametrize("kind", ["FIRST", "TERMINAL", "PUBLISH", "BOOTSTRAP"])
def test_anchored_deletion_reordering_entire_operation(kind):
    value = material()
    seq = next(r["seq"] for r in value["records"] if r["kind"] == kind)
    ident = object_id("journal", "journal", str(seq), "journal")
    with pytest.raises(TaskBundleError):
        verify(value, rebuild(value, [row for row in value["objects"] if row[1] != ident]))


@pytest.mark.parametrize("mode", ["LATEST_OBSERVATION", "MINIMUM", "UNKNOWN"])
def test_external_anchor_old_valid_checkpoint_rollback(mode):
    value = material(mode=mode)
    report = verify(value)
    assert (
        report.freshness
        == {
            "LATEST_OBSERVATION": "EXTERNAL_OBSERVATION_PROVIDED",
            "MINIMUM": "MINIMUM_ONLY",
            "UNKNOWN": "UNKNOWN",
        }[mode]
    )
    if mode != "UNKNOWN":
        with pytest.raises(TaskBundleError):
            verify(value, rebuild(value, [r for r in value["objects"] if r[0] != "checkpoint"]))


def test_unanchored_tail_deletion_unknown_freshness():
    full = material(mode="UNKNOWN")
    prefix = material(mode="UNKNOWN", terminal=False, publish=False)
    a, b = verify(full), verify(prefix)
    assert a.cutoff_sequence == 6 and b.cutoff_sequence == 4
    assert a.freshness == b.freshness == "UNKNOWN"
    assert "NO_LATEST_EXTERNAL_ANCHOR" in b.limitations and "UNANCHORED_TAIL" in b.limitations


@pytest.mark.parametrize(
    "change", ["wrongrole", "keyrange", "registration", "bundlekey", "currentDID"]
)
def test_historical_keys_roles_registration_rotation(change):
    value = material()
    if change == "wrongrole":
        value["trust"]["audit_keys"][0]["role"] = "HOLDER"
    elif change == "keyrange":
        value["trust"]["audit_keys"][0]["first_sequence"] = 7
    elif change == "registration":
        value["trust"]["historical_registrations"][0]["did"] += "x"
    elif change == "bundlekey":
        value["trust"]["as_keys"] = value["trust"]["gateway_keys"]
    else:
        # A current resolver is never consulted; keys remain historical.
        assert verify(value).current_auth == "UNKNOWN"
        return
    with pytest.raises(TaskBundleError):
        verify(value)


@pytest.mark.parametrize("change", ["none", "runtime", "nonlegacy_missing", "legacy_baseline"])
def test_limitations_legacy_current_auth_effect_truth(change):
    value = material(baseline=1 if change == "legacy_baseline" else 0)
    if change == "runtime":
        rows = []
        for kind, ident, raw in value["objects"]:
            if kind == "typed_snapshot_metadata":
                decoded = load_strict_json(raw)
                if (
                    type(decoded) is dict
                    and decoded.get("metadata_profile") == "AG-TASK-RUNTIME-OBSERVATION-1"
                ):
                    decoded.update(status="UNKNOWN", receipt_status=None)
                    raw = canonical_json_bytes(decoded)
            rows.append((kind, ident, raw))
        value["bundle"] = rebuild(value, rows)
    elif change == "nonlegacy_missing":
        value["bundle"] = rebuild(value, [row for row in value["objects"] if row[0] != "source"])
        with pytest.raises(TaskBundleError):
            verify(value)
        return
    report = verify(value)
    assert report.current_auth == "UNKNOWN"
    assert report.downstream_truth == "ATTESTED_NOT_INDEPENDENTLY_PROVEN"
    assert all(
        r["assurance"] == "UNANCHORED_AS_OF_DB_OBSERVATION" for r in report.runtime_status_as_of
    )
    assert "UNSIGNED_RUNTIME_OBSERVATION" in report.limitations


def _replace(value, ident, raw):
    return [
        (kind, key, raw if key == ident else original) for kind, key, original in value["objects"]
    ]


def _rechain(value, rows):
    from agent_guard.audit.contracts import genesis_digest
    from agent_guard.crypto.sm import sm3_b64url

    originals = {
        load_strict_json(raw)["seq"]: (ident, load_strict_json(raw))
        for kind, ident, raw in rows
        if kind == "journal"
    }
    previous = genesis_digest(value["scope"])
    replacements = {}
    for _seq, (ident, record) in sorted(originals.items()):
        record["previous_digest"] = previous
        raw = canonical_json_bytes(record)
        replacements[ident] = raw
        previous = sm3_b64url(raw)
    changed = [(kind, ident, replacements.get(ident, raw)) for kind, ident, raw in rows]
    value = {**value, "header": {**value["header"], "cutoff_head_digest": previous}}
    return rebuild(value, changed)


CONTEXT_FIELDS = (
    "subject tenant_id task_id grant_id root_id holder_client_id "
    "holder_kid tool_id idempotency_key canonical_params token_exp "
    "proof_iat proof_exp proof_jti token_digest proof_digest "
    "intent_digest ancestor_ids profile purpose endpoint method "
    "tool_version"
).split()
SOURCE_FIELDS = (
    "grant_id parent_id root_id tenant_id task_id subject client_id kid "
    "depth nbf exp amount calls token token_sm3 scope constraints actor "
    "spki saved_exp"
).split()


@pytest.mark.parametrize("field", CONTEXT_FIELDS)
def test_each_context_field_is_bound(field):
    value = material()
    ident = object_id("context", "journal", "2", "context")
    raw = next(raw for _, key, raw in value["objects"] if key == ident)
    decoded = load_strict_json(raw)
    decoded.pop(field)
    with pytest.raises(TaskBundleError):
        verify(value, rebuild(value, _replace(value, ident, canonical_json_bytes(decoded))))


@pytest.mark.parametrize("node", range(3))
@pytest.mark.parametrize("field", SOURCE_FIELDS)
def test_each_source_node_field_is_bound(node, field):
    value = material()
    ident = object_id("source", "journal", "2", "source")
    decoded = load_strict_json(next(raw for _, key, raw in value["objects"] if key == ident))
    chain = load_strict_json(decoded["chain"])
    chain[node].pop(field)
    decoded["chain"] = canonical_json_bytes(chain).decode()
    with pytest.raises(TaskBundleError):
        verify(value, rebuild(value, _replace(value, ident, canonical_json_bytes(decoded))))


@pytest.mark.parametrize("node", range(3))
@pytest.mark.parametrize("event", range(2))
@pytest.mark.parametrize(
    "field",
    [
        "amount_reserved_delta",
        "amount_settled_delta",
        "calls_reserved_delta",
        "calls_settled_delta",
    ],
)
def test_each_ancestor_delta_semantic_rejection(node, event, field):
    from agent_guard.contracts.ledger_changes import (
        canonical_ledger_changes_bytes,
        load_ledger_changes,
    )
    from agent_guard.crypto.sm import sm3_b64url

    value = material()
    ident = object_id("ledger", "operation", value["operation_id"], "ledger")
    ledger = load_ledger_changes(next(raw for _, key, raw in value["objects"] if key == ident))
    ledger["events"][event]["nodes"][node][field] += 1
    raw = canonical_ledger_changes_bytes(ledger)
    rows = _replace(value, ident, raw)
    terminal = next(record for record in value["records"] if record["kind"] == "TERMINAL")
    terminal = deepcopy(terminal)
    terminal["facts"]["ledger_digest"] = sm3_b64url(raw)
    journal_id = object_id("journal", "journal", str(terminal["seq"]), "journal")
    rows = [
        (kind, key, canonical_json_bytes(terminal) if key == journal_id else original)
        for kind, key, original in rows
    ]
    with pytest.raises(TaskBundleError, match="terminal ancestor delta mismatch"):
        verify(value, _rechain(value, rows))


@pytest.mark.parametrize(
    "component,field",
    [
        ("accept_result_metadata", "accepted_at"),
        ("accept_result_metadata", "operation_id"),
        ("accept_result_metadata", "status"),
        ("accept_result_metadata", "disposition"),
        ("pending_receipt_metadata", "created_at"),
        ("pending_receipt_metadata", "evidence_ref"),
        ("pending_receipt_metadata", "operation_id"),
        ("pending_receipt_metadata", "amount_fen"),
        ("pending_receipt_metadata", "status"),
    ],
)
def test_v3_original_metadata_mutations(component, field):
    value = material()
    owner, owner_id = (
        ("journal", "3")
        if component == "accept_result_metadata"
        else ("operation", value["operation_id"])
    )
    ident = object_id("typed_snapshot_metadata", owner, owner_id, component)
    decoded = load_strict_json(next(raw for _, key, raw in value["objects"] if key == ident))
    decoded[field] = decoded[field] + 1 if type(decoded[field]) is int else decoded[field] + "x"
    with pytest.raises(TaskBundleError):
        verify(value, rebuild(value, _replace(value, ident, canonical_json_bytes(decoded))))


@pytest.mark.parametrize(
    "component", ["accept_result_metadata", "pending_receipt_metadata", "internal_ledger"]
)
def test_v3_required_original_ref_missing(component):
    value = material()
    ident = next(
        key
        for kind, key, raw in value["objects"]
        if (
            kind == "typed_snapshot_metadata"
            and type(load_strict_json(raw)) is dict
            and load_strict_json(raw).get("metadata_profile")
            == {
                "accept_result_metadata": "AG-TASK-ACCEPT-RESULT-1",
                "pending_receipt_metadata": "AG-TASK-PENDING-RECEIPT-1",
            }.get(component)
        )
        or component == "internal_ledger"
        and key == object_id("ledger", "operation", value["operation_id"], component)
    )
    with pytest.raises(TaskBundleError):
        verify(value, rebuild(value, [row for row in value["objects"] if row[1] != ident]))


@pytest.mark.parametrize("field", ["gateway_id", "tenant_id", "task_id", "stream_id", "epoch"])
def test_each_external_scope_field_refused(field):
    value = material()
    value["trust"]["scope"][field] = "wrong" if field != "epoch" else 2
    with pytest.raises(TaskBundleError):
        verify(value)


def test_unanchored_deletion_same_public_trust():
    value = material(mode="UNKNOWN")
    rows = []
    keep = 3
    for kind, ident, raw in value["objects"]:
        if kind == "journal" and load_strict_json(raw)["seq"] > keep:
            continue
        if kind in {"result", "ledger", "receipt"}:
            continue
        if kind == "checkpoint" and ident != object_id(
            "checkpoint", "checkpoint", "cp-1", "checkpoint"
        ):
            continue
        if kind == "typed_snapshot_metadata":
            decoded = load_strict_json(raw)
            if type(decoded) is dict:
                profile = decoded.get("metadata_profile")
                if (
                    profile == "AG-TASK-REFS-1"
                    and decoded["record_seq"] > keep
                    or profile == "AG-TASK-PENDING-RECEIPT-1"
                ):
                    continue
                if profile == "AG-TASK-RUNTIME-OBSERVATION-1":
                    decoded.update(status="UNKNOWN", receipt_status=None)
                    raw = canonical_json_bytes(decoded)
        rows.append((kind, ident, raw))
    referenced = set()
    for kind, _ident, raw in rows:
        if kind == "typed_snapshot_metadata":
            decoded = load_strict_json(raw)
            if type(decoded) is dict and decoded.get("metadata_profile") == "AG-TASK-REFS-1":
                referenced.update(r["object_id"] for r in decoded["refs"])
            if type(decoded) is dict and "table" in decoded:
                for component in decoded["columns"].values():
                    if type(component) is dict and "object_id" in component:
                        referenced.add(
                            object_id(
                                component["kind"],
                                "bootstrap",
                                component["object_id"],
                                component["object_id"],
                            )
                        )
    rows = [
        row
        for row in rows
        if row[0] not in {"token", "proof", "request", "context", "source", "ancestor_token"}
        or row[1] in referenced
    ]
    header = {**value["header"], "cutoff_sequence": keep}
    deleted = {**value, "header": header}
    report = verify(deleted, _rechain(deleted, rows))
    assert report.freshness == "UNKNOWN" and report.cutoff_sequence == keep
    assert "NO_LATEST_EXTERNAL_ANCHOR" in report.limitations
    assert all(
        row["amount_reserved"] == 70000 and row["calls_reserved"] == 1
        for row in report.grant_counters
    )


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize(
    "change", ["valid", "missingmiddle", "oldpin", "rotatedrange", "wrongscope"]
)
def test_original_checkpoint_chain_rotation_and_external_pin(round, change):
    value = material(rotate_audit=True, middle_checkpoint=True)
    if change == "valid":
        assert verify(value).freshness == "EXTERNAL_OBSERVATION_PROVIDED"
        return
    if change == "missingmiddle":
        middle = object_id("checkpoint", "checkpoint", "cp-2", "checkpoint")
        value["bundle"] = rebuild(value, [row for row in value["objects"] if row[1] != middle])
    elif change == "oldpin":
        value["pin"]["checkpoint_jws"] = value["cp_originals"][0]
    elif change == "rotatedrange":
        value["trust"]["audit_keys"][1]["first_sequence"] = 999
    else:
        value["trust"]["scope"]["task_id"] += "-other"
    with pytest.raises(TaskBundleError):
        verify(value)


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("changed", [False, True])
def test_accept_result_immutable_timestamp_across_genuine_signed_retries(round, changed):
    value = material(repeat_retry=True, changed_accepted_at=changed)
    if changed:
        with pytest.raises(TaskBundleError, match="retry immutable accepted_at changed"):
            verify(value)
    else:
        assert verify(value).freshness == "EXTERNAL_OBSERVATION_PROVIDED"


@pytest.mark.parametrize("round", range(10))
def test_historical_accept_response_original_digest(round):
    assert verify(material(accept_response=True)).freshness == "EXTERNAL_OBSERVATION_PROVIDED"


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("change", ["control", "amount-limit", "call-limit"])
def test_authenticated_bootstrap_grant_authority_continuity(round, change):
    overrides = (
        {"ag_limits": {"currency": "CNY", "amount_fen": 69999, "calls": 10}}
        if change == "amount-limit"
        else {"ag_limits": {"currency": "CNY", "amount_fen": 100000, "calls": 1}}
        if change == "call-limit"
        else None
    )
    value = material(
        tool="notification.template.send" if change == "call-limit" else "procurement.order.create",
        bootstrap_claim_overrides=overrides,
    )
    if change != "control":
        with pytest.raises(TaskBundleError, match="grant identity changed in history"):
            verify(value)
        return
    report = verify(value)
    assert report.cryptographic_consistency == "VERIFIED"
    assert len(report.grant_counters) == 3
    assert all(row["amount_settled"] == 70000 for row in report.grant_counters)
    assert all(row["calls_settled"] == 1 for row in report.grant_counters)
    assert all(
        row["amount_reserved"] == row["calls_reserved"] == 0 for row in report.grant_counters
    )
    assert report.current_auth == "UNKNOWN"


@pytest.mark.parametrize("change", ["jti", "expiry", "scope", "constraints", "holder"])
def test_same_id_bootstrap_immutable_claim_variants_refused(change):
    def overrides(claims):
        root = claims[0]
        if change == "jti":
            return {"jti": root["jti"] + "-baseline"}
        if change == "expiry":
            return {"exp": root["exp"] - 1}
        if change == "scope":
            return {"scope": "procurement.order.create"}
        if change == "constraints":
            return {"ag_constraints": {**root["ag_constraints"], "max_quantity": 1}}
        other = claims[1]
        return {
            "client_id": other["client_id"],
            "act": {"sub": other["act"]["sub"]},
            "ag_cnf": other["ag_cnf"],
        }

    with pytest.raises(TaskBundleError, match="grant identity changed in history"):
        verify(material(bootstrap_claim_overrides=overrides))


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize("baseline", [0, 1])
def test_bootstrap_authority_preserves_legacy_and_introduced_grants(round, baseline):
    value = material(baseline=baseline)
    report = verify(value)
    assert report.cryptographic_consistency == "VERIFIED"
    assert report.history_boundary == ("LEGACY_WITH_GAPS" if baseline else "NEW_EMPTY")
    assert len(report.grant_counters) == 3
    root_id = value["records"][0]["facts"]["root_grant_id"]
    root = next(row for row in report.grant_counters if row["grant_id"] == root_id)
    introduced = [row for row in report.grant_counters if row["grant_id"] != root_id]
    assert root["amount_reserved"] == baseline
    assert all(row["amount_reserved"] == 0 for row in introduced)
    assert all(row["amount_settled"] == 70000 for row in report.grant_counters)
    assert all(row["calls_settled"] == 1 for row in report.grant_counters)
    assert bool(report.legacy_gap_ids) == bool(baseline)
    assert ("HISTORICAL_GAP" in report.limitations) == bool(baseline)
    assert report.current_auth == "UNKNOWN"
    assert "PRE_BOOTSTRAP_HISTORY_UNPROVEN" in report.limitations
