"""Synthetic S0 fixture constants; no fake token, grant or invocation context."""

from agent_guard.demo.config import HOLDERS, PAIR_NAMES, ROLES

ROLE_UIDS = {role: 21000 + index for index, role in enumerate(sorted(ROLES))}
HANDOFF_GIDS = {pair: 22000 + index for index, pair in enumerate(PAIR_NAMES)}
TENANT = "tenant-demo"
TASK = "task-demo"
TOOLS = (
    "procurement.request.read",
    "procurement.document.read",
    "procurement.order.create",
    "notification.template.send",
)
HOLDER_CLIENTS = {holder: "agent-" + holder for holder in HOLDERS}


def task_policy(*, expires_at):
    """Trusted synthetic policy sent to register_task_policy, never a grant."""
    return {
        "tenant_id": TENANT,
        "task_id": TASK,
        "owner_subject": "user-demo",
        "scope": "openid " + " ".join(TOOLS),
        "constraints": {
            "request_ids": ["req-001"],
            "document_ids": ["doc-001"],
            "quote_versions": ["quote-001@1"],
            "skus": ["sku-001"],
            "max_quantity": 2,
            "delivery_ids": ["office-001"],
            "template_ids": ["order-created"],
            "recipient_ids": ["user-demo"],
        },
        "amount_limit_fen": 100000,
        "call_limit": 12,
        "task_expires_at": expires_at.isoformat(),
    }


def invocation(tool_id, *, idempotency_key, order_operation_id=None):
    """Exact public HTTP body; all authorization comes from real AS/GW."""
    params = {
        TOOLS[0]: {"request_id": "req-001"},
        TOOLS[1]: {"request_id": "req-001", "document_id": "doc-001"},
        TOOLS[2]: {
            "request_id": "req-001",
            "quote_id": "quote-001",
            "quote_version": "1",
            "items": [{"sku": "sku-001", "quantity": 1}],
            "delivery_id": "office-001",
        },
        TOOLS[3]: {
            "template_id": "order-created",
            "recipient_id": "user-demo",
            "operation_id": order_operation_id,
        },
    }
    if tool_id not in TOOLS or (tool_id == TOOLS[3] and order_operation_id is None):
        raise ValueError("fixed tool/order reference required")
    return {
        "profile": "GM-MVP-1",
        "task_id": TASK,
        "tool_id": tool_id,
        "tool_version": "1",
        "idempotency_key": idempotency_key,
        "params": params[tool_id],
    }


def approved_registry(config):
    """Only operator-owned prior approval input, not fetched DID self-registration."""
    from types import MappingProxyType

    from agent_guard.contracts.encoding import b64url_decode, load_strict_json
    from agent_guard.demo.config import ApprovedRegistry
    from agent_guard.identity.resolver import RegisteredIdentity
    from agent_guard.server.private_files import read_private_file

    role = config.roles["operator"]
    value = load_strict_json(read_private_file(role.private_files["approval_registry"]))
    registrations = tuple(
        RegisteredIdentity(
            r["tenant_id"],
            r["client_id"],
            r["did"],
            r["kid"],
            b64url_decode(r["spki_der"]),
        )
        for r in value["registrations"]
    )
    purposes = MappingProxyType(
        {r["client_id"]: tuple(r["purposes"]) for r in value["registrations"]}
    )
    return ApprovedRegistry(
        config.run_id,
        registrations,
        purposes,
        role.public_config_file.parent / "ca.pem",
        b64url_decode(value["challenge"]),
    )


def delegation_request(*, parent, policy, delegation_key):
    from agent_guard.contracts.encoding import canonical_json_bytes
    from agent_guard.demo.config import DelegationRequest

    if parent == "planner":
        target, amount, calls, depth, ttl = "agent-selector", 80000, 10, 1, 240
    elif parent == "selector":
        target, amount, calls, depth, ttl = "agent-executor", 70000, 8, 0, 180
    else:
        raise ValueError("fixed delegating parent required")
    constraints = dict(policy["constraints"], max_quantity=1)
    return DelegationRequest(
        target,
        " ".join(sorted(set(policy["scope"].split()) - {"openid"})),
        canonical_json_bytes(constraints),
        delegation_key,
        ttl,
        amount,
        calls,
        depth,
    )


def grant_publisher_evidence_keyshare(conn):
    """Fixture-only minimum column permission for the existing FK/keyshare lock."""
    conn.execute("GRANT UPDATE(evidence_ref) ON ag_verified_evidence TO demo_publisher")
    assert conn.execute(
        "SELECT has_table_privilege('demo_publisher','ag_verified_evidence','UPDATE'),"
        "has_column_privilege('demo_publisher','ag_verified_evidence','evidence_ref','UPDATE')"
    ).fetchone() == (False, True)
    assert (
        conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='ag_verified_evidence' AND table_schema=current_schema() "
            "AND column_name<>'evidence_ref' AND "
            "has_column_privilege('demo_publisher','ag_verified_evidence',column_name,'UPDATE')"
        ).fetchall()
        == []
    )
