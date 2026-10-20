"""Isolated deterministic holder; credentials and AS tokens stay in this process.

The control pipe carries only fixed scenario commands and public operation IDs.
There is no signing, token-export, recovery or verified-context command.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from agent_guard.authorization.claims import validate_access_claims
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.crypto.sm import verify_compact_jws
from agent_guard.demo.client import DemoClient
from agent_guard.demo.config import (
    HOLDERS,
    DelegationRequest,
    DemoConfigError,
    RootRequest,
    SyntheticLogin,
    holder_config,
    load_run_config,
    thaw,
)
from agent_guard.demo.handoff import receive_child, send_child

TOOLS = (
    "procurement.request.read",
    "procurement.document.read",
    "procurement.order.create",
    "notification.template.send",
)
CONSTRAINTS = {
    "request_ids": ["req-001"],
    "document_ids": ["doc-001"],
    "quote_versions": ["quote-001@1"],
    "skus": ["sku-001"],
    "max_quantity": 1,
    "delivery_ids": ["office-001"],
    "template_ids": ["order-created"],
    "recipient_ids": ["user-demo"],
}


def workload_skus(capacity_items):
    if type(capacity_items) is not int or capacity_items not in (1, 256):
        raise DemoConfigError("explicit 1 or 256 item workload required")
    return ["sku-001"] if capacity_items == 1 else [f"s{i:03d}" for i in range(256)]


def capacity_workload(*, task_policy: dict, catalog: dict):
    """Operator's pre-provision synthetic input, using existing policy/catalog APIs.

    Returns copies; callers distribute and freeze them before AS authorization.
    It cannot create a grant, change a limit, or alter an accepted quote snapshot.
    The 256 short SKUs cost exactly the same 70000 integer CNY fen as default.
    """
    import copy

    policy, resources = copy.deepcopy(task_policy), copy.deepcopy(catalog)
    if policy["amount_limit_fen"] != 100000 or policy["call_limit"] != 12:
        raise DemoConfigError("original capacity task limits required")
    quotes = resources["quotes"]
    if len(quotes) != 1 or (quotes[0]["quote_id"], quotes[0]["quote_version"]) != (
        "quote-001",
        "1",
    ):
        raise DemoConfigError("fixed capacity quote required")
    skus = workload_skus(256)
    policy["constraints"]["skus"] = skus
    quotes[0]["lines"] = [
        {"sku": sku, "quantity": 1, "unit_price_fen": 274 if index < 112 else 273}
        for index, sku in enumerate(skus)
    ]
    if sum(line["unit_price_fen"] for line in quotes[0]["lines"]) != 70000:
        raise DemoConfigError("capacity quote integer sum")
    return policy, resources


def invocation_body(
    task_id, tool_id, *, idempotency_key, order_operation_id=None, capacity_items=1
):
    """Fixed synthetic business inputs; trusted gateway calculates the price."""
    skus = workload_skus(capacity_items)
    params = {
        TOOLS[0]: {"request_id": "req-001"},
        TOOLS[1]: {"request_id": "req-001", "document_id": "doc-001"},
        TOOLS[2]: {
            "request_id": "req-001",
            "quote_id": "quote-001",
            "quote_version": "1",
            "items": [{"sku": sku, "quantity": 1} for sku in skus],
            "delivery_id": "office-001",
        },
        TOOLS[3]: {
            "template_id": "order-created",
            "recipient_id": "user-demo",
            "operation_id": order_operation_id,
        },
    }
    if tool_id not in TOOLS or (tool_id == TOOLS[3] and not order_operation_id):
        raise DemoConfigError("fixed tool and accepted order reference required")
    from agent_guard.demo.config import text

    text(task_id)
    text(idempotency_key)
    if order_operation_id is not None:
        text(order_operation_id)
    return {
        "profile": "GM-MVP-1",
        "task_id": task_id,
        "tool_id": tool_id,
        "tool_version": "1",
        "idempotency_key": idempotency_key,
        "params": params[tool_id],
    }


@dataclass(frozen=True)
class HolderAuthorization:
    client_id: str
    grant_id: str
    root_id: str
    parent_id: str | None
    limits: dict
    delegation_remaining: int
    expires_at: int


class Holder:
    """A single native UID, own key, live authorization, and owned operations."""

    def __init__(self, config, *, role, capacity_items=1):
        if role not in HOLDERS or os.getuid() != config.roles[role].uid:
            raise DemoConfigError("exact native holder role required")
        self.capacity_items = capacity_items
        self.constraints = dict(CONSTRAINTS, skus=workload_skus(capacity_items))
        self.config = config
        self.role = role
        self.client = DemoClient(holder_config(config, holder=role))
        self._token = None
        self._operations = {}
        self._order = None

    def authorization(self):
        if self._token is None:
            raise DemoConfigError("holder has no AS authorization")
        import time

        claims = validate_access_claims(
            verify_compact_jws(
                self._token,
                expected_type="ag-at+jwt",
                trusted_keys=self.client.config.as_keys,
            ),
            issuer=self.client.config.issuer,
            now=int(time.time()),
        ).raw
        if (claims["client_id"], claims["ag_tenant_id"], claims["ag_task_id"]) != (
            self.client.config.client_id,
            self.client.config.tenant_id,
            self.client.config.task_id,
        ):
            raise DemoConfigError("received AS authorization has foreign scope")
        from agent_guard.crypto.sm import serialize_sm2_public_key, sm3_b64url

        if claims["ag_cnf"] != {
            "kid": self.client.config.kid,
            "spki_sm3": sm3_b64url(serialize_sm2_public_key(self.client._key.public_key())),
        }:
            raise DemoConfigError("AS authorization possession binding mismatch")
        expected_constraints = dict(self.constraints)
        if self.role == "planner":
            expected_constraints["max_quantity"] = 2
        if claims["ag_constraints"] != expected_constraints:
            raise DemoConfigError("AS authorization workload constraints mismatch")
        return HolderAuthorization(
            claims["client_id"],
            claims["ag_grant_id"],
            claims["ag_root_id"],
            claims["ag_parent_id"],
            claims["ag_limits"],
            claims["ag_delegation_remaining"],
            claims["exp"],
        )

    def root(self, *, login):
        if self.role != "planner" or self._token is not None:
            raise DemoConfigError("single planner browser root required")
        result = self.client.browser_root(
            login=login,
            request=RootRequest(self.client.config.task_id, "openid " + " ".join(TOOLS)),
        )
        self._token = result.access_token
        return self.authorization()

    def receive(self):
        if self.role == "planner" or self._token is not None:
            raise DemoConfigError("single child reception required")
        parent = {"selector": "agent-planner", "executor": "agent-selector"}[self.role]
        pair = next(p for p in self.config.roles[self.role].handoff if p.peer_client_id == parent)
        child = receive_child(pair, expected_parent=parent)
        # Handoff authenticates the process; AS signature authenticates the token.
        self._token = child.access_token
        try:
            result = self.authorization()
        except Exception:
            self._token = None
            raise
        return result

    def delegate(self):
        parent = self.authorization()
        ttl = min(240 if self.role == "planner" else 180, parent.expires_at - int(time.time()))
        if ttl <= 0:
            raise DemoConfigError("parent authorization has expired")
        target, amount, calls, depth = {
            "planner": ("agent-selector", 80000, 10, 1),
            "selector": ("agent-executor", 70000, 8, 0),
        }.get(self.role, (None, None, None, None))
        if target is None:
            raise DemoConfigError("leaf cannot delegate")
        request = DelegationRequest(
            target,
            " ".join(sorted(TOOLS)),
            canonical_json_bytes(self.constraints),
            secrets.token_urlsafe(32),
            ttl,
            amount,
            calls,
            depth,
        )
        child = self.client.exchange(parent_token=self._token, request=request)
        pair = next(p for p in self.config.roles[self.role].handoff if p.peer_client_id == target)
        return send_child(pair, target=target, token=child)

    def invoke(self, *, tool_id, idempotency_key):
        self.authorization()
        if self.role != "executor":
            raise DemoConfigError("fixed demonstration execution holder required")
        body = invocation_body(
            self.client.config.task_id,
            tool_id,
            idempotency_key=idempotency_key,
            order_operation_id=self._order,
            capacity_items=self.capacity_items,
        )
        result = self.client.invoke(token=self._token, body=body)
        if result.status in (200, 202):
            operation = result.value.get("operation_id")
            from agent_guard.demo.config import text

            text(operation)
            previous = self._operations.get(idempotency_key)
            if previous is not None and previous != (tool_id, operation):
                raise DemoConfigError("same business key changed public operation")
            self._operations[idempotency_key] = (tool_id, operation)
            if tool_id == TOOLS[2]:
                self._order = operation
        return result

    def query(self, *, operation_id):
        self.authorization()
        if operation_id not in {row[1] for row in self._operations.values()}:
            raise DemoConfigError("only this holder's accepted operation may be queried")
        return self.client.query(token=self._token, operation_id=operation_id)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agent_guard.demo.holder")
    parser.add_argument("--config", required=True)
    parser.add_argument("--role", choices=sorted(HOLDERS), required=True)
    parser.add_argument("--capacity-items", type=int, choices=(1, 256), default=1)
    args = parser.parse_args(argv)
    path = Path(args.config)
    try:
        holder = Holder(
            load_run_config(path.read_bytes(), base_dir=path.parent),
            role=args.role,
            capacity_items=args.capacity_items,
        )

        def emit(value):
            print(canonical_json_bytes(value).decode(), flush=True)

        emit(
            {
                "event": "holder_ready",
                "role": args.role,
                "pid": os.getpid(),
                "uid": os.getuid(),
                "capacity_items": holder.capacity_items,
            }
        )
        for raw in sys.stdin.buffer:
            if len(raw) > 65536:
                raise DemoConfigError("bounded holder control required")
            command = load_strict_json(raw)
            if type(command) is not dict or type(command.get("action")) is not str:
                raise DemoConfigError("holder command rejected")
            action = command["action"]
            from dataclasses import asdict

            if action == "root" and set(command) == {"action", "login"}:
                value = asdict(holder.root(login=SyntheticLogin(**command["login"])))
            elif action == "receive" and set(command) == {"action"}:
                value = asdict(holder.receive())
            elif action == "delegate" and set(command) == {"action"}:
                value = asdict(holder.delegate())
            elif action == "invoke" and set(command) == {
                "action",
                "tool_id",
                "idempotency_key",
            }:
                response = holder.invoke(
                    tool_id=command["tool_id"],
                    idempotency_key=command["idempotency_key"],
                )
                value = {"status": response.status, "value": thaw(response.value)}
            elif action == "query" and set(command) == {"action", "operation_id"}:
                response = holder.query(operation_id=command["operation_id"])
                value = {"status": response.status, "value": thaw(response.value)}
            elif action == "stop" and set(command) == {"action"}:
                emit({"action": "stop", "inflight_zero": True})
                return 0
            else:
                raise DemoConfigError("unknown or extra holder command fields")
            emit({"action": action, "value": value})
        return 0
    except (OSError, ValueError, TypeError):
        print("holder scenario rejected", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
