"""Trusted finite scenario runner over isolated holder control pipes.

Deployment supplies exact role launch commands and maintenance callbacks. Only
public operation IDs enter the existing append-only worker registry. No token,
private key, database credential or verified-context JSON crosses this API.
"""

from __future__ import annotations

import os
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.demo.config import DemoConfigError, SyntheticLogin, text
from agent_guard.demo.holder import TOOLS, workload_skus
from agent_guard.demo.worker import OwnedOperationRegistry


@dataclass(frozen=True)
class ScenarioReport:
    run_id: str
    owner_id: str
    holder_uids: tuple[int, ...]
    authorizations: tuple[dict, ...]
    operation_ids: tuple[str, ...]
    queries: tuple[dict, ...]


@dataclass
class HolderProcess:
    role: str
    uid: int
    process: subprocess.Popen = field(repr=False)
    messages: queue.Queue = field(repr=False)
    reader: threading.Thread = field(repr=False)
    ready: dict
    transcript: list = field(default_factory=list, repr=False)
    pending: str | None = None

    def send(self, value):
        if self.pending is not None or self.process.poll() is not None:
            raise DemoConfigError("holder command overlaps or process stopped")
        raw = canonical_json_bytes(value) + b"\n"
        if len(raw) > 65536:
            raise DemoConfigError("holder control capacity")
        self.process.stdin.write(raw)
        self.process.stdin.flush()
        self.pending = value["action"]

    def receive(self, *, timeout=15):
        try:
            message = self.messages.get(timeout=timeout)
        except queue.Empty:
            raise DemoConfigError("holder response deadline") from None
        if isinstance(message, Exception):
            raise DemoConfigError("holder output rejected") from message
        if message is None:
            raise DemoConfigError("holder exited before response")
        if message.get("action") != self.pending:
            raise DemoConfigError("holder response action mismatch")
        self.pending = None
        self.transcript.append(message)
        return message

    def command(self, value, *, timeout=15):
        self.send(value)
        return self.receive(timeout=timeout)


def _read_messages(stream, messages):
    try:
        while True:
            raw = stream.readline(65537)
            if not raw:
                break
            if len(raw) > 65536 or not raw.endswith(b"\n"):
                raise DemoConfigError("holder output capacity")
            value = load_strict_json(raw)
            if type(value) is not dict:
                raise DemoConfigError("holder output schema")
            messages.put(value)
    except Exception as exc:
        messages.put(exc)
    finally:
        messages.put(None)


class ScenarioRunner:
    """Operator process; launchers must preserve the frozen per-role mounts/UIDs.

    ``launch`` returns argv for the installed holder module, e.g. an exact owned
    container exec. No shell is used. Stderr is an already-open private evidence
    stream chosen by the deployment. Maintenance callbacks are trusted lifecycle
    operations supplied by S2, never commands accepted by a holder or HTTP route.
    """

    def __init__(
        self,
        config,
        *,
        registry: OwnedOperationRegistry,
        launch: Callable,
        stderr,
        wait_receiver: Callable,
        capacity_items=1,
    ):
        role = config.roles["operator"]
        if os.getuid() != role.uid or type(registry) is not OwnedOperationRegistry:
            raise DemoConfigError("trusted operator runner required")
        if (
            registry.run_id,
            registry.owner_id,
            registry.tenant_id,
            registry.task_id,
        ) != (
            config.run_id,
            config.owner_id,
            config.scope["tenant_id"],
            config.scope["task_id"],
        ) or (registry.runner_uid, registry.worker_uid, registry.reader_gid) != (
            role.uid,
            config.roles["worker"].uid,
            config.roles["worker"].uid,
        ):
            raise DemoConfigError("exact registry lifecycle scope required")
        if not callable(launch) or not callable(wait_receiver):
            raise DemoConfigError("role launcher required")
        self.config, self.registry, self.launch, self.stderr = (
            config,
            registry,
            launch,
            stderr,
        )
        workload_skus(capacity_items)
        self.capacity_items = capacity_items
        self.wait_receiver = wait_receiver
        self.holders = {}
        self.authorizations = ()

    def start(self):
        if self.holders:
            raise DemoConfigError("holders already launched")
        try:
            for role in ("executor", "selector", "planner"):
                argv = self.launch(role)
                if (
                    type(argv) not in (tuple, list)
                    or not argv
                    or any(type(x) is not str for x in argv)
                ):
                    raise DemoConfigError("exact holder argv required")
                process = subprocess.Popen(
                    argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=self.stderr,
                    bufsize=0,
                )
                messages = queue.Queue()
                reader = threading.Thread(
                    target=_read_messages, args=(process.stdout, messages), daemon=True
                )
                reader.start()
                # Retain handle before any validation so failed starts are reaped.
                child = HolderProcess(
                    role, self.config.roles[role].uid, process, messages, reader, {}
                )
                self.holders[role] = child
                ready = messages.get(timeout=15)
                if type(ready) is not dict or set(ready) != {
                    "event",
                    "role",
                    "pid",
                    "uid",
                    "capacity_items",
                }:
                    raise DemoConfigError("holder native readiness schema")
                if (
                    (
                        ready["event"],
                        ready["role"],
                        ready["uid"],
                        ready["capacity_items"],
                    )
                    != ("holder_ready", role, child.uid, self.capacity_items)
                    or type(ready["capacity_items"]) is not int
                    or type(ready["pid"]) is not int
                    or ready["pid"] < 1
                ):
                    raise DemoConfigError("holder native identity mismatch")
                child.ready = ready
            if len({h.uid for h in self.holders.values()}) != 3:
                raise DemoConfigError("three distinct holder UIDs required")
        except Exception:
            self.stop(force=True)
            raise

    def authorize(self, *, login: SyntheticLogin):
        if self.authorizations or set(self.holders) != {
            "planner",
            "selector",
            "executor",
        }:
            raise DemoConfigError("fresh three-holder authorization required")
        if type(login) is not SyntheticLogin:
            raise DemoConfigError("synthetic login required")
        planner, selector, executor = (self.holders[r] for r in ("planner", "selector", "executor"))
        root = planner.command(
            {
                "action": "root",
                "login": {
                    "tenant_id": login.tenant_id,
                    "subject": login.subject,
                    "password": login.password,
                },
            }
        )["value"]
        selector.send({"action": "receive"})
        self._wait_socket("planner", "agent-selector")
        ack1 = planner.command({"action": "delegate"})["value"]
        middle = selector.receive()["value"]
        executor.send({"action": "receive"})
        self._wait_socket("selector", "agent-executor")
        ack2 = selector.command({"action": "delegate"})["value"]
        leaf = executor.receive()["value"]
        for row, role, limits, depth in zip(
            (root, middle, leaf),
            ("planner", "selector", "executor"),
            ((100000, 12), (80000, 10), (70000, 8)),
            (2, 1, 0),
            strict=True,
        ):
            if (
                row["client_id"] != "agent-" + role
                or row["limits"] != {"currency": "CNY", "amount_fen": limits[0], "calls": limits[1]}
                or row["delegation_remaining"] != depth
                or row["root_id"] != root["grant_id"]
            ):
                raise DemoConfigError("public AS chain narrowing mismatch")
        if (
            root["parent_id"] is not None
            or middle["parent_id"] != root["grant_id"]
            or leaf["parent_id"] != middle["grant_id"]
        ):
            raise DemoConfigError("public AS ancestor binding mismatch")
        if middle["expires_at"] > root["expires_at"] or leaf["expires_at"] > middle["expires_at"]:
            raise DemoConfigError("public AS expiry expansion")
        for ack, sender, target in (
            (ack1, "agent-planner", "agent-selector"),
            (ack2, "agent-selector", "agent-executor"),
        ):
            if ack != {
                "run_id": self.config.run_id,
                "task_id": self.config.scope["task_id"],
                "sender": sender,
                "target": target,
            }:
                raise DemoConfigError("handoff acknowledgment scope")
        self.authorizations = (root, middle, leaf)
        return self.authorizations

    def _wait_socket(self, role, target):
        pair = next(p for p in self.config.roles[role].handoff if p.peer_client_id == target)
        # Operator has no pair mount/group. Readiness is checked inside the exact
        # receiver by the trusted launcher, preserving the reciprocal IPC ACL.
        self.wait_receiver(target.removeprefix("agent-"), pair.socket_path, 5)

    def four_tools(self, *, progress: Callable[[str], None]):
        """Trusted callback processes/publishes registered IDs; query is external fresh proof."""
        if not self.authorizations or not callable(progress):
            raise DemoConfigError("live authorization and trusted progress required")
        operations, queries = [], []
        executor = self.holders["executor"]
        for index, tool in enumerate(TOOLS):
            response = executor.command(
                {
                    "action": "invoke",
                    "tool_id": tool,
                    "idempotency_key": "demo-" + self.config.run_id + "-" + str(index),
                }
            )["value"]
            if response["status"] != 202:
                raise DemoConfigError("new fixed operation was not accepted")
            operation = text(response["value"]["operation_id"])
            self.registry.register(operation)
            operations.append(operation)
            progress(operation)
            query = executor.command({"action": "query", "operation_id": operation})["value"]
            if query["status"] != 200 or query["value"]["receipt_status"] != "READY":
                raise DemoConfigError("live authorized READY result required")
            queries.append(query["value"])
        return ScenarioReport(
            self.config.run_id,
            self.config.owner_id,
            tuple(self.holders[r].uid for r in ("planner", "selector", "executor")),
            self.authorizations,
            tuple(operations),
            tuple(queries),
        )

    def stop(self, *, force=False):
        receipts = []
        for holder in reversed(tuple(self.holders.values())):
            p = holder.process
            try:
                if p.poll() is None and not force and holder.pending is None:
                    receipt = holder.command({"action": "stop"}, timeout=5)
                    if receipt != {"action": "stop", "inflight_zero": True}:
                        raise DemoConfigError("holder did not drain")
                elif p.poll() is None:
                    p.terminate()
                try:
                    code = p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    code = p.wait(timeout=5)
                receipts.append(
                    {
                        "role": holder.role,
                        "uid": holder.uid,
                        "pid": holder.ready.get("pid"),
                        "launcher_pid": p.pid,
                        "native_exit": code,
                    }
                )
            finally:
                p.stdin.close()
                p.stdout.close()
                holder.reader.join(timeout=1)
        self.holders.clear()
        return tuple(receipts)


def operation_registry(config, *, directory: Path):
    """One stable constructor shared by trusted runner and read-only worker."""
    return OwnedOperationRegistry(
        directory,
        run_id=config.run_id,
        owner_id=config.owner_id,
        tenant_id=config.scope["tenant_id"],
        task_id=config.scope["task_id"],
        runner_uid=config.roles["operator"].uid,
        worker_uid=config.roles["worker"].uid,
        reader_gid=config.roles["worker"].uid,
    )
