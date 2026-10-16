"""Bounded, allowlisted projection of test-only observations for DemoEvent v1."""

import json
import re
import uuid
from datetime import datetime, timezone

from deploy.demo.supervisor import atomic

SCHEMA_VERSION = 1
FILE = "demo-events-v1.json"
MAX_EVENTS = 64
MAX_FILE_BYTES = 131072
MAX_WITNESS_BYTES = 16384
CASES = {
    "stolen-token": ("stolen",),
    "delegation-scope": ("amount", "scope"),
    "revocation": ("revoke-first",),
}
PATTERNS = {
    "stolen": ("fixture.setup", "request.sent", "accept.rejected", "readback.state"),
    "amount": (
        "delegation.requested",
        "delegation.issued",
        "delegation.requested",
        "delegation.rejected",
        "readback.state",
    ),
    "scope": (
        "delegation.requested",
        "delegation.issued",
        "delegation.requested",
        "delegation.rejected",
        "readback.state",
    ),
    "revoke-first": (
        "request.sent",
        "lock.waiting",
        "revocation.committed",
        "accept.rejected",
        "readback.state",
    ),
}
TYPES = {
    "fixture.setup": ("attacker", "attacker", "passed"),
    "request.sent": (None, "gateway", "in_progress"),
    "delegation.requested": ("planner", "as", "in_progress"),
    "delegation.issued": ("as", "selector", "passed"),
    "delegation.rejected": ("as", "planner", "rejected"),
    "lock.waiting": ("gateway", "ledger", "waiting"),
    "revocation.committed": ("ledger", "gateway", "passed"),
    "accept.rejected": ("gateway", None, "rejected"),
    "readback.state": ("ledger", "user", "passed"),
}
PAYLOAD_KEYS = {
    "fixture.setup": {"token_holder", "proof_signer_kid"},
    "request.sent": {"endpoint", "token_holder", "proof_signer_kid", "tool_id"},
    "delegation.requested": {
        "parent_limits",
        "requested_limits",
        "parent_scope",
        "requested_scope",
    },
    "delegation.issued": {
        "grant_alias",
        "parent_alias",
        "holder",
        "holder_kid",
        "limits",
        "scope",
        "expires_in",
        "http_status",
    },
    "delegation.rejected": {"dimension", "http_status"},
    "lock.waiting": {"waiting_on"},
    "revocation.committed": {"grant_alias", "txn_ref"},
    "accept.rejected": {"http_status"},
    "readback.state": {
        "budget_before",
        "budget_after",
        "orders_before",
        "orders_after",
        "notifications_before",
        "notifications_after",
    },
}
SAFE_TEXT = re.compile(r"[A-Za-z0-9_.#:/-]{1,80}\Z")
REASON = re.compile(r"[A-Za-z0-9_.-]{1,80}\Z")
KID = re.compile(
    r"(?:did:web:identity\.agent-guard\.test:agents:(?:planner|selector|executor)"
    r"|selector)#key-1\Z"
)
TOOLS = {
    "procurement.request.read",
    "procurement.document.read",
    "procurement.order.create",
    "notification.template.send",
}


def _valid_uuid(value):
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _number(value):
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise ValueError("unsafe event number")
    return value


def _payload(event_type, value):
    if type(value) is not dict or set(value) - PAYLOAD_KEYS[event_type]:
        raise ValueError("unsafe event payload")
    result = {}
    for key, item in value.items():
        if key.startswith("budget_"):
            if type(item) is not list or len(item) != 3:
                raise ValueError("invalid budget")
            result[key] = []
            for row in item:
                if type(row) is not dict or set(row) != {"reserved_fen", "settled_fen", "calls"}:
                    raise ValueError("invalid budget row")
                result[key].append({name: _number(row[name]) for name in row})
        elif key.endswith("_limits") or key == "limits":
            if type(item) is not dict or set(item) != {"amount_fen", "calls"}:
                raise ValueError("invalid limits")
            result[key] = {name: _number(item[name]) for name in item}
        elif key.endswith("_scope") or key == "scope":
            if (
                type(item) is not list
                or len(item) > 8
                or any(
                    type(tool) is not str or tool not in TOOLS | {"unauthorized.tool"}
                    for tool in item
                )
            ):
                raise ValueError("invalid scope")
            result[key] = item
        elif key in {
            "http_status",
            "expires_in",
            "orders_before",
            "orders_after",
            "notifications_before",
            "notifications_after",
        }:
            result[key] = _number(item)
        elif key in {"proof_signer_kid", "holder_kid"} and (
            type(item) is str and len(item) <= 160 and KID.fullmatch(item)
        ):
            result[key] = item
        elif (
            key == "waiting_on"
            and type(item) is str
            and (item == "root-revocation" or _valid_uuid(item))
        ):
            result[key] = item
        elif (
            type(item) is str
            and item
            in {
                "executor",
                "planner",
                "selector",
                "root",
                "mid",
                "root-revocation",
                "/v1/invocations",
                "amount",
                "scope",
            }
            | TOOLS
        ):
            result[key] = item
        else:
            raise ValueError("unsafe event text")
    return result


def _event(run_id, scenario_id, case, seq, step):
    if type(step) is not dict or set(step) != {
        "event_type",
        "actor",
        "target",
        "status",
        "safe_payload",
        "reason_code",
        "observed_at",
        "monotonic_ms",
    }:
        raise ValueError("invalid event observation")
    event_type = step["event_type"]
    if event_type not in TYPES:
        raise ValueError("unknown event type")
    actor, target, status = TYPES[event_type]
    if (
        (actor is not None and step["actor"] != actor)
        or (target is not None and step["target"] != target)
        or step["status"] != status
    ):
        raise ValueError("invalid event direction or status")
    if step["actor"] not in {"attacker", "planner", "executor", "as", "gateway", "ledger"}:
        raise ValueError("invalid actor")
    if step["target"] not in {
        "attacker",
        "planner",
        "selector",
        "executor",
        "as",
        "gateway",
        "ledger",
        "user",
    }:
        raise ValueError("invalid target")
    reason = step["reason_code"]
    if reason is not None and (type(reason) is not str or not REASON.fullmatch(reason)):
        raise ValueError("invalid reason")
    observed = step["observed_at"]
    if type(observed) not in (int, float) or not 0 < observed < 2**40:
        raise ValueError("invalid observed time")
    event_id = str(uuid.uuid5(uuid.UUID(run_id), f"{scenario_id}:{seq}"))
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "scenario_id": scenario_id,
        "seq": seq,
        "event_id": event_id,
        "cause_id": None,
        "source": "live",
        "actor": step["actor"],
        "target": step["target"],
        "stage": event_type.split(".", 1)[0],
        "event_type": event_type,
        "status": status,
        "reason_code": reason,
        "observed_at": datetime.fromtimestamp(observed, timezone.utc).isoformat(),
        "monotonic_ms": _number(step["monotonic_ms"]),
        "safe_payload": _payload(event_type, step["safe_payload"]),
        "evidence_ref": f"test:{case}",
    }


def _load_witnesses(folder, scenario_id):
    found = {}
    directory = folder / "test-results/native"
    if not directory.exists():
        return found
    if folder.is_symlink() or directory.parent.is_symlink() or directory.is_symlink():
        raise ValueError("unsafe witness directory")
    for path in directory.glob("teacher-demo-witness-*.json"):
        if path.is_symlink() or path.stat().st_size > MAX_WITNESS_BYTES:
            raise ValueError("unsafe witness file")
        witness = json.loads(path.read_text(encoding="utf-8"))
        if type(witness) is not dict or set(witness) != {"scenario_id", "case", "steps"}:
            raise ValueError("invalid witness")
        if witness["scenario_id"] != scenario_id or witness["case"] not in CASES[scenario_id]:
            raise ValueError("unexpected witness")
        if witness["case"] in found or type(witness["steps"]) is not list:
            raise ValueError("duplicate or invalid witness")
        found[witness["case"]] = witness["steps"]
    return found


def persist(folder, run_id, scenario_id, *, terminal=False):
    """Project an ordered prefix of completed test witnesses."""
    if scenario_id not in CASES:
        return False
    witnesses = _load_witnesses(folder, scenario_id)
    cases = CASES[scenario_id]
    if terminal and set(witnesses) != set(cases):
        return False
    prefix = []
    for case in cases:
        if case not in witnesses:
            break
        prefix.append(case)
    if not prefix:
        return False
    events = []
    for case in prefix:
        if tuple(step.get("event_type") for step in witnesses[case]) != PATTERNS[case]:
            raise ValueError("incomplete event witness")
        for step in witnesses[case]:
            events.append(_event(run_id, scenario_id, case, len(events) + 1, step))
    if len(events) + 1 > MAX_EVENTS:
        raise ValueError("too many events")
    revocation = next(
        (event for event in events if event["event_type"] == "revocation.committed"), None
    )
    last_request = {}
    for event in events:
        case = event["evidence_ref"]
        if event["event_type"] in {"request.sent", "delegation.requested"}:
            last_request[case] = event["event_id"]
        if event["event_type"] in {"accept.rejected", "delegation.rejected"}:
            event["cause_id"] = last_request.get(case)
        if event["event_type"] == "lock.waiting" and revocation:
            event["safe_payload"]["waiting_on"] = revocation["event_id"]
        if event["event_type"] == "accept.rejected" and revocation:
            event["cause_id"] = revocation["event_id"]
    terminal_event = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "scenario_id": scenario_id,
        "seq": len(events) + 1,
        "event_id": str(uuid.uuid5(uuid.UUID(run_id), f"{scenario_id}:terminal")),
        "cause_id": events[-1]["event_id"] if events else None,
        "source": "live",
        "actor": "verifier",
        "target": "user",
        "stage": "run",
        "event_type": "run.terminal",
        "status": "passed",
        "reason_code": None,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "monotonic_ms": 0,
        "safe_payload": {},
        "evidence_ref": "test:completed",
    }
    if terminal:
        events.append(terminal_event)
    data = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "scenario_id": scenario_id,
        "events": events,
        "terminal": terminal,
        "complete": terminal,
    }
    if len(json.dumps(data, ensure_ascii=False).encode()) > MAX_FILE_BYTES:
        raise ValueError("event file too large")
    atomic(folder / FILE, data)
    return True


def fail(folder, run_id, scenario_id):
    """Record a program failure without exposing native logs or claiming a test refusal."""
    folder.mkdir(parents=True, exist_ok=True)
    try:
        previous = page(folder, run_id, scenario_id)
        if previous["terminal"]:
            return
        observed = previous["events"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        observed = []
    event = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "scenario_id": scenario_id,
        "seq": len(observed) + 1,
        "event_id": str(uuid.uuid5(uuid.UUID(run_id), f"{scenario_id}:error")),
        "cause_id": observed[-1]["event_id"] if observed else None,
        "source": "live",
        "actor": "verifier",
        "target": "user",
        "stage": "run",
        "event_type": "run.error",
        "status": "failed",
        "reason_code": "RUN_FAILED",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "monotonic_ms": 0,
        "safe_payload": {},
        "evidence_ref": "test:run-failed",
    }
    observed.append(event)
    atomic(
        folder / FILE,
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "scenario_id": scenario_id,
            "events": observed,
            "terminal": True,
            "complete": False,
        },
    )


def page(folder, run_id, scenario_id, *, after_seq=0, limit=200, replay=False):
    if (
        type(after_seq) is not int
        or after_seq < 0
        or type(limit) is not int
        or not 1 <= limit <= 200
    ):
        raise ValueError("invalid event cursor")
    path = folder / FILE
    if not path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "scenario_id": scenario_id,
            "source": "replay" if replay else "live",
            "events": [],
            "next_after_seq": after_seq,
            "terminal": False,
            "complete": False,
        }
    if path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("unsafe event file")
    data = json.loads(path.read_text(encoding="utf-8"))
    if type(data) is not dict or set(data) != {
        "schema_version",
        "run_id",
        "scenario_id",
        "events",
        "terminal",
        "complete",
    }:
        raise ValueError("invalid saved event file")
    if type(data["terminal"]) is not bool or type(data["complete"]) is not bool:
        raise ValueError("invalid event completion flags")
    if (
        data.get("schema_version") != SCHEMA_VERSION
        or data.get("run_id") != run_id
        or data.get("scenario_id") != scenario_id
    ):
        raise ValueError("event identity mismatch")
    events = data["events"]
    if (
        type(events) is not list
        or len(events) > MAX_EVENTS
        or any(
            type(event) is not dict or event.get("seq") != index or event.get("run_id") != run_id
            for index, event in enumerate(events, 1)
        )
    ):
        raise ValueError("invalid saved events")
    required = {
        "schema_version",
        "run_id",
        "scenario_id",
        "seq",
        "event_id",
        "cause_id",
        "source",
        "actor",
        "target",
        "stage",
        "event_type",
        "status",
        "reason_code",
        "observed_at",
        "monotonic_ms",
        "safe_payload",
        "evidence_ref",
    }
    for event in events:
        if (
            set(event) != required
            or event["scenario_id"] != scenario_id
            or event["source"] != "live"
        ):
            raise ValueError("invalid saved event schema")
        if event["schema_version"] != SCHEMA_VERSION or not _valid_uuid(event["event_id"]):
            raise ValueError("invalid saved event identity")
        if event["cause_id"] is not None and not _valid_uuid(event["cause_id"]):
            raise ValueError("invalid saved event cause")
        if event["actor"] not in {
            "attacker",
            "planner",
            "executor",
            "as",
            "gateway",
            "ledger",
            "verifier",
        } or event["target"] not in {
            "attacker",
            "planner",
            "selector",
            "executor",
            "as",
            "gateway",
            "ledger",
            "user",
        }:
            raise ValueError("invalid saved event participant")
        if type(event["stage"]) is not str or not re.fullmatch(r"[a-z]{1,32}", event["stage"]):
            raise ValueError("invalid saved event stage")
        if type(event["observed_at"]) is not str or len(event["observed_at"]) > 40:
            raise ValueError("invalid saved event time")
        try:
            datetime.fromisoformat(event["observed_at"])
        except ValueError as exc:
            raise ValueError("invalid saved event time") from exc
        _number(event["monotonic_ms"])
        event_type = event["event_type"]
        if event_type in ("run.terminal", "run.error"):
            if (
                event["safe_payload"] != {}
                or event["stage"] != "run"
                or event["status"] != ("passed" if event_type == "run.terminal" else "failed")
            ):
                raise ValueError("invalid terminal event")
        elif event_type in TYPES:
            if event["stage"] != event_type.split(".", 1)[0]:
                raise ValueError("invalid saved event stage")
            if event["safe_payload"] != _payload(event_type, event["safe_payload"]):
                raise ValueError("invalid saved payload")
            actor, target, status = TYPES[event_type]
            if (
                (actor is not None and event["actor"] != actor)
                or (target is not None and event["target"] != target)
                or event["status"] != status
            ):
                raise ValueError("invalid saved event")
        else:
            raise ValueError("unknown saved event type")
        if event["reason_code"] is not None and (
            type(event["reason_code"]) is not str or not REASON.fullmatch(event["reason_code"])
        ):
            raise ValueError("invalid saved reason")
        if type(event["evidence_ref"]) is not str or not re.fullmatch(
            r"test:(stolen|amount|scope|revoke-first|completed|run-failed)", event["evidence_ref"]
        ):
            raise ValueError("invalid evidence reference")
    if (data.get("terminal") is True) != (
        bool(events) and events[-1]["event_type"] in ("run.terminal", "run.error")
    ):
        raise ValueError("invalid terminal state")
    if data["complete"] is True and (not events or events[-1]["event_type"] != "run.terminal"):
        raise ValueError("invalid completeness")
    selected = [
        event | {"source": "replay" if replay else "live"}
        for event in events
        if event["seq"] > after_seq
    ][:limit]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "scenario_id": scenario_id,
        "source": "replay" if replay else "live",
        "events": selected,
        "next_after_seq": selected[-1]["seq"] if selected else after_seq,
        "terminal": data.get("terminal") is True,
        "complete": data.get("complete") is True,
    }
