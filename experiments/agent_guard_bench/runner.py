"""Frozen-plan scheduler and role-private real TLS transport.

No authority is minted here. Assembly calls the frozen normal three-role APIs
and returns actual private task clients. Planned and actual files are separate;
failed preparation cannot manufacture a wire attempt.
"""

from __future__ import annotations

import contextlib
import hashlib
import http.client
import json
import os
import queue
import socket
import ssl
import struct
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit

from .statistics import overlap_peak, summarize_repetition
from .workload import MODES, Plan, generate_suite

MODE_MAPPING = {
    "staticACL": "staticACL",
    "realSM2delegation_noAtomic": "noAtomic",
    "complete": "full",
    "realSM2Bearer": "Bearer",
}
SLOTS = 50
DRAIN_SECONDS = 600
JIT_SECONDS = 240


class MissingPrerequisite(ValueError):
    """The original attempt remains planned; required actual material is absent."""


class PublicSpool:
    """Append-and-fsync durable public records before moving to the next intent."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.lock = threading.Lock()
        self.peak_bytes = 0

    def append(self, name, value):
        if name not in {
            "planned",
            "actual",
            "warmup",
            "preparation",
            "completion",
            "oracle",
            "export",
            "failures",
        }:
            raise ValueError("fixed public spool section required")
        encoded = json.dumps(value, separators=(",", ":"), default=str).encode() + b"\n"
        with self.lock:
            with (self.directory / (name + ".jsonl")).open("ab") as file:
                file.write(encoded)
                file.flush()
                os.fsync(file.fileno())
            self.peak_bytes = max(
                self.peak_bytes,
                sum(p.stat().st_size for p in self.directory.iterdir() if p.is_file()),
            )


class RoleTLSInvocation:
    """Actual private holder TLS request, original bytes cache and received-byte loss.

    Instantiate within the holder UID only. Exact token/proof caches never leave
    this object/public outputs. No-PoP modes never call a holder signer.
    """

    def __init__(self, holder, *, mode, private_capture=None, acl_client=None):
        if mode not in MODES:
            raise ValueError("fixed mode required")
        self.holder = holder
        self.mode = mode
        self.acl = acl_client
        self.capture = private_capture
        self.originals = {}
        self.order_operation_id = None
        self.issued_ns = time.monotonic_ns()
        self.lock = threading.Lock()

    def _material(self, body, intent):
        if intent.material == "EXACT_ORIGINAL_BYTES":
            if intent.target_index not in self.originals:
                raise MissingPrerequisite("original exact token/proof/body never sent")
            return dict(self.originals[intent.target_index])
        if time.monotonic_ns() - self.issued_ns >= JIT_SECONDS * 1_000_000_000:
            raise MissingPrerequisite("JIT send deadline; grant cannot be renewed")
        if self.mode == "staticACL":
            if self.acl is None:
                raise MissingPrerequisite("distinct approved role ACL credential required")
            return {
                "body": canonical_json_bytes(body),
                "token": self.acl.password,
                "proof": None,
                "issued_unix_ns": time.time_ns(),
            }
        if self.mode == "realSM2Bearer":
            if self.holder._token is None:
                raise MissingPrerequisite("genuine AS Bearer token required")
            return {
                "body": canonical_json_bytes(body),
                "token": self.holder._token,
                "proof": None,
                "issued_unix_ns": time.time_ns(),
            }
        value = self.holder.raw_request(body)
        return {**value, "issued_unix_ns": time.time_ns()}

    def prepare(self, intent, *, body_builder, attack_transform=None):
        body = body_builder(
            self.holder.task,
            intent.tool_id,
            key=intent.business_key,
            order_operation_id=self.order_operation_id,
        )
        material = self._material(body, intent)
        # A class-specific real AS/holder/material operation is mandatory for
        # every attack; no generic "bad token" substitution closes a class.
        if intent.category == "attack" and intent.attack_class != 2:
            if attack_transform is None:
                raise MissingPrerequisite(
                    f"real class {intent.attack_class} attack material required"
                )
            material = attack_transform(intent, body, material)
        if type(material.get("body")) is not bytes:
            raise MissingPrerequisite("exact wire body bytes required")
        return material

    def send(self, intent, material, *, lose_response=False, barrier=None):
        config = self.holder.config
        origin = urlsplit(config.gateway_origin)
        if origin.scheme != "https" or origin.path or origin.query or origin.username:
            raise ValueError("fixed verified origin required")
        proof = material.get("proof")
        if self.mode in ("realSM2Bearer", "staticACL") and proof is not None:
            raise ValueError("no fabricated proof in no-PoP modes")
        scheme = {
            "complete": "AGPoP",
            "realSM2delegation_noAtomic": "AGPoP",
            "realSM2Bearer": "Bearer",
            "staticACL": "ACL",
        }[self.mode]
        headers = {
            "Content-Type": "application/json",
            "Authorization": scheme + " " + material["token"],
        }
        if proof is not None:
            headers["AG-Proof"] = proof
        if self.mode == "staticACL":
            headers["X-ACL-Role"] = self.acl.role
        capture_ref = (
            self.capture.stage(material["token"], proof, material["body"])
            if self.capture is not None
            else None
        )
        context = ssl.create_default_context(cafile=str(config.ca_file))
        connection = http.client.HTTPSConnection(
            origin.hostname, origin.port or 443, context=context, timeout=30
        )
        row = {
            "index": intent.index,
            "seed": intent.seed,
            "mode": intent.mode,
            "task": intent.task,
            "tool_id": intent.tool_id,
            "category": intent.category,
            "attack_class": intent.attack_class,
            "retry_kind": intent.retry_kind,
            "slot": intent.slot,
            "key_hash": hashlib.sha256(intent.business_key.encode()).hexdigest(),
            "body_sha256": hashlib.sha256(material["body"]).hexdigest(),
            "request_bytes": len(material["body"]),
            "response_bytes": 0,
            "http_status": None,
            "error": None,
            "auth_pass": None,
            "new_accept": None,
            "operation_id": None,
            "as_refusal": material.get("as_refusal"),
            "private_original_ref": capture_ref,
            "wire_sent": False,
            "invoke_write": "PENDING",
            "proof_capability": "PRESENT_CRYPTO_VALIDATION_INDEPENDENT"
            if proof is not None
            else "N/A",
            # Honest attack-material disclosure: malformed numeric bodies are
            # RAW_NONCANONICAL and no valid proof can bind them; a genuine
            # proof, when present, binds the pre-transform canonical body.
            "body_binding": material.get("body_binding", "STRICT_CANONICAL"),
            "proof_binding": material.get("proof_binding"),
            "malformed_quantity_variant": material.get("malformed_quantity_variant"),
            "connection_reuse": "NONE_NEW_VERIFIED_TLS_PER_ATTEMPT",
            "source_token_matches_genuine_task": material["token"] == self.holder._token
            if self.mode != "staticACL"
            else "N/A",
        }
        from agent_guard.crypto.sm import sm3_b64url

        row["token_digest"] = sm3_b64url(material["token"].encode("ascii"))
        row["proof_digest"] = sm3_b64url(proof.encode("ascii")) if proof is not None else None
        original_send = connection.send
        transmitted = [0]
        attempted_writes = [0]

        def counted_send(data):
            if isinstance(data, (bytes, bytearray, memoryview)):
                size = len(data)
            elif isinstance(data, str):
                size = len(data.encode("iso-8859-1"))
            else:
                raise TypeError("bounded byte HTTP transport required")
            # Count only transport writes that actually return success; a
            # raising send may have partially written but that is unobservable,
            # so it is recorded as an attempted write, never as observed bytes.
            attempted_writes[0] += 1
            result = original_send(data)
            transmitted[0] += size
            return result

        connection.send = counted_send
        row["body_bytes"] = len(material["body"])
        row["token_bytes"] = len(material["token"].encode("ascii"))
        row["proof_bytes"] = len(proof.encode("ascii")) if proof is not None else 0
        row["actual_source_path"] = (
            "SINGLE_ROLE_TASK_POLICY_NOT_PLANNED_AS_BRANCH"
            if self.mode == "staticACL"
            else (
                "REAL_AS_TOKEN_PATH"
                if material["token"] == self.holder._token
                else "INVALID_CHILD_NO_VALID_SOURCE"
            )
        )
        # Connect/handshake before the first wave barrier. send_ns immediately
        # precedes the actual write, not scheduling or credential generation.
        try:
            connection.connect()
        except Exception as exc:
            # No HTTP request was written: this honest failure row must never
            # fulfil a required actual invoke.
            row.update(
                send_ns=time.monotonic_ns(),
                send_unix_ns=time.time_ns(),
                end_ns=time.monotonic_ns(),
                error=type(exc).__name__,
                invoke_write="NONE",
            )
            if barrier is not None:
                barrier.abort()
            connection.close()
            return row
        if barrier is not None:
            barrier.wait(timeout=30)
        row.update(send_ns=time.monotonic_ns(), send_unix_ns=time.time_ns())
        self.originals[intent.index] = dict(material)
        try:
            # Proof was generated immediately before connection setup; measure
            # genuine proof age and never regenerate an exact replay.
            row["proof_age_at_send_ns"] = row["send_unix_ns"] - material["issued_unix_ns"]
            if (
                proof is not None
                and intent.material != "EXACT_ORIGINAL_BYTES"
                and row["proof_age_at_send_ns"] >= 60_000_000_000
            ):
                raise MissingPrerequisite("fresh proof60 expired before write")
            connection.request("POST", "/v1/invocations", body=material["body"], headers=headers)
            row["wire_sent"] = True
            row["invoke_write"] = "OBSERVED"
            response = connection.getresponse()
            row["http_status"] = response.status
            if lose_response:
                partial = response.read(1)
                row["response_bytes"] = len(partial)
                row["response_prefix_sha256"] = hashlib.sha256(partial).hexdigest()
                row["response_loss"] = {
                    "received_response_headers": True,
                    "received_body_bytes": len(partial),
                    "server_complete_write_observed": False,
                    "kind": "CLIENT_LOST_COMPLETE_RESPONSE_AFTER_REAL_RESPONSE_BYTES",
                }
                if not partial:
                    raise MissingPrerequisite("response-loss requires actual response body byte")
                # Actual shutdown of the live TLS transport after real bytes.
                transport = connection.sock or getattr(
                    getattr(response.fp, "raw", None), "_sock", None
                )
                if transport is not None:
                    transport.setsockopt(
                        socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
                    )
                    transport.close()
                response.close()
                row["response_loss"]["transport_closed"] = True
                row["http_status"] = None
                row["error"] = "IncompleteResponseLostByClient"
            else:
                raw = response.read(65537)
                row["response_bytes"] = len(raw)
                if len(raw) > 65536:
                    raise ValueError("response exceeds frozen bound")
                parsed = load_strict_json(raw)
                if type(parsed) is dict:
                    row["response_code"] = parsed.get("code")
                    row["operation_id"] = parsed.get("operation_id")
                row["response_sha256"] = hashlib.sha256(raw).hexdigest()
        except Exception as exc:
            row["error"] = type(exc).__name__
        finally:
            if row["invoke_write"] == "PENDING":
                # Only a normally completed request is an observed real invoke.
                # A raised request phase with any send attempt may have written
                # partially but unobservably: retained as UNKNOWN and never
                # able to fulfil a required actual invoke; no send attempt at
                # all is an honest no-write failure.
                if attempted_writes[0]:
                    row["invoke_write"] = "UNKNOWN"
                    row["transmitted_bytes_observed"] = transmitted[0]
                else:
                    row["invoke_write"] = "NONE"
            row["end_ns"] = time.monotonic_ns()
            row["end_unix_ns"] = time.time_ns()
            connection.close()
        return row

    def query(self, operation_id):
        if self.mode == "complete":
            return self.holder.query_full(operation_id)
        body = {
            "profile": "GM-MVP-1",
            "task_id": self.holder.task.task_id,
            "operation_id": operation_id,
        }
        if self.mode == "staticACL":
            return self.acl.request(body, purpose="result-read")
        return self.holder.request_research(
            body, mode=MODE_MAPPING[self.mode], purpose="result-read"
        )


def _task_groups(plan, intents):
    groups = defaultdict(list)
    for index in plan.send_order if intents is plan.intentions else range(len(intents)):
        intent = intents[index]
        groups[intent.task].append(intent)
    return list(groups.values())


def run_official_mode_repetition(
    plan: Plan, assembly, *, output_directory, final_stop_receipt=None
):
    """Run all fixed rows through a concrete frozen owned assembly.

    The trusted assembly performs normal provisioning/JIT/four-writer stop,
    actual bootstrap/resume, returns RoleTLSInvocation per task, and provides
    RR witnesses. This function never alters plan targets, caps, limits or TTL.
    Its lifecycle is also usable for a finite pilot via run_task_wave.
    """
    if type(plan) is not Plan or plan not in generate_suite():
        raise ValueError("exact frozen official plan required")
    if (
        not final_stop_receipt
        or final_stop_receipt.get("all_writers_STOP") is not True
        or final_stop_receipt.get("sole_integrator") is not True
    ):
        raise MissingPrerequisite("official run requires all STOP and sole final integrator")
    spool = PublicSpool(output_directory)
    for intent in plan.intentions:
        spool.append("planned", asdict(intent))
    for intent in plan.warmup:
        spool.append("planned", {**asdict(intent), "excluded_warmup": True})
    actual = []
    first_measured = True
    try:
        for intents, measured in ((plan.warmup, False), (plan.intentions, True)):
            groups = _task_groups(plan, intents)
            for wave in _bounded_waves(groups):
                try:
                    clients = assembly.prepare_wave(
                        plan, [g[0] for g in wave], excluded_warmup=not measured
                    )
                    spool.append("preparation", assembly.wave_receipt())
                except Exception as exc:
                    spool.append(
                        "failures",
                        {
                            "phase": "JIT_BOOTSTRAP",
                            "tasks": [g[0].task for g in wave],
                            "error": type(exc).__name__,
                            "measured": measured,
                        },
                    )
                    continue
                rows = run_task_wave(
                    wave,
                    clients=clients,
                    assembly=assembly,
                    spool=spool,
                    measured=measured,
                    barrier_first=measured and first_measured,
                )
                if measured:
                    actual.extend(rows)
                    first_measured = False
                deadline = time.monotonic_ns() + DRAIN_SECONDS * 1_000_000_000
                completion = assembly.drain_wave(deadline_ns=deadline)
                spool.append("completion", completion)
                # Export partitions/scopes are predetermined by the original
                # task IDs. All records are retained under the existing caps.
                if plan.mode == "complete":
                    for package in assembly.export_wave(wave, expiry_or_revoke_required=True):
                        spool.append("export", package)
                spool.append("oracle", assembly.snapshot_wave())
        final_deadline = (
            max((r["send_ns"] for r in actual), default=time.monotonic_ns())
            + DRAIN_SECONDS * 1_000_000_000
        )
        spool.append("completion", assembly.drain_repeat(deadline_ns=final_deadline))
        summary = summarize_repetition(
            plan,
            actual,
            require_complete=False,
            completions=assembly.completion_metrics(),
        )
        # COMPLETE requires the real first-wave pending prerequisite (50 actual
        # observed writes) and an actual row for every frozen plan index with an
        # observed real HTTP write; otherwise the run stays INCOMPLETE with the
        # reasons retained. Pre-send failures never substitute actual invokes.
        summary["first_wave_actual_peak_interval_inflight"] = assembly.first_wave_peak
        if summary.get("status") == "COMPLETE":
            reasons = []
            if assembly.first_wave_peak is None or assembly.first_wave_peak < SLOTS:
                reasons.append(
                    "first measured wave must observe " + str(SLOTS) + " actual pending requests"
                )
            if summary.get("actual_n") != summary.get("planned_n"):
                reasons.append("actual row count differs from the frozen plan")
            if summary.get("unobserved_write_indices"):
                reasons.append("rows without an observed HTTP write cannot count as actual invokes")
            if reasons:
                summary["status"] = "INCOMPLETE"
                summary["incomplete_reasons"] = reasons
        summary["spoolpeak_bytes"] = spool.peak_bytes
        summary["lineage"] = assembly.lineage()
        (spool.directory / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
        return summary
    finally:
        # STOP receipt must be actual; the assembly owns its own resources.
        receipt, stop_error = None, None
        try:
            receipt = assembly.stop()
        except BaseException as exc:
            stop_error = exc
        finally:
            (spool.directory / "STOP.json").write_text(
                json.dumps(
                    receipt
                    if receipt is not None
                    else {
                        "status": "STOP_FAILED",
                        "no_more_writes": True,
                        "error": type(stop_error).__name__,
                    },
                    indent=2,
                    default=str,
                )
            )
        if stop_error is not None and sys.exc_info()[0] is None:
            raise stop_error


def run_task_wave(groups, *, clients, assembly, spool, measured, barrier_first=False):
    """One sequential DAG per task, up to50 actual role-private TLS clients."""
    if not 1 <= len(groups) <= SLOTS:
        raise ValueError("bounded real task wave required")
    if barrier_first and len(groups) != SLOTS:
        raise MissingPrerequisite("first measured wave needs50 real clients")
    barrier = threading.Barrier(SLOTS, timeout=30) if barrier_first else None
    loss_targets = {4 * task + 2 for task in range(450, 500)}

    def task_run(group):
        if len(group) > 1 and all(i.category == "attack" and i.attack_class == 9 for i in group):
            if len(group) != 2:
                raise ValueError("fixed two-branch budget pair required")
            with ThreadPoolExecutor(max_workers=2) as siblings:
                return [
                    row for result in siblings.map(lambda i: task_run([i]), group) for row in result
                ]
        client = clients[group[0].task]
        rows = []
        for position, intent in enumerate(group):
            try:
                if intent.material == "EXACT_ORIGINAL_BYTES":
                    witness = assembly.proof_consumption_witness(intent)
                    if plan_pop(intent.mode) and witness.get("consumed") is not True:
                        raise MissingPrerequisite("original proof not independently consumed")
                if intent.retry_kind in ("terminalfreshidem", "lostresponsefreshretry"):
                    witness = assembly.original_witness(intent)
                    if witness.get("committed") is not True or witness.get("terminal") is not True:
                        raise MissingPrerequisite("fixed original terminal/commit witness missing")
                    if (
                        intent.retry_kind == "lostresponsefreshretry"
                        and witness.get("actual_response_loss") is not True
                    ):
                        raise MissingPrerequisite("real response loss and commit witness required")
                material = client.prepare(
                    intent,
                    body_builder=assembly.body_builder,
                    attack_transform=assembly.attack_transform,
                )
                row = client.send(
                    intent,
                    material,
                    lose_response=measured and intent.index in loss_targets,
                    barrier=barrier if position == 0 else None,
                )
            except Exception as exc:
                if barrier is not None and position == 0:
                    barrier.abort()
                spool.append(
                    "failures",
                    {
                        "index": intent.index,
                        "task": intent.task,
                        "category": intent.category,
                        "phase": "BEFORE_ACTUAL_INVOKE",
                        "error": type(exc).__name__,
                        "reason": str(exc),
                        "measured": measured,
                    },
                )
                continue
            spool.append("actual" if measured else "warmup", row)
            rows.append(row)
            # The response ID can be unavailable after true response loss;
            # resolve by original immutable key/body via independent RR facts.
            observation = assembly.observe_original(intent, row)
            spool.append("oracle", observation)
            if intent.tool_id == "procurement.order.create" and intent.category == "legal":
                if observation.get("committed") and observation.get("operation_id"):
                    client.order_operation_id = observation["operation_id"]
                else:
                    spool.append(
                        "failures",
                        {
                            "phase": "MISSING_ORDER_DEPENDENCY",
                            "index": intent.index,
                            "task": intent.task,
                            "measured": measured,
                        },
                    )
            if intent.category in ("legal", "warmup"):
                assembly.wait_terminal(
                    intent,
                    observation,
                    deadline_ns=time.monotonic_ns() + DRAIN_SECONDS * 1_000_000_000,
                )
                if intent.tool_id == "procurement.order.create" and observation.get("operation_id"):
                    client.order_operation_id = observation["operation_id"]
        return rows

    rows = []
    with ThreadPoolExecutor(max_workers=SLOTS) as pool:
        futures = {pool.submit(task_run, group): group[0].task for group in groups}
        for future in as_completed(futures):
            try:
                rows.extend(future.result())
            except Exception as exc:
                spool.append(
                    "failures",
                    {
                        "phase": "LATE_TASK_FUTURE",
                        "task": futures[future],
                        "error": type(exc).__name__,
                    },
                )
    if barrier_first:
        first_indices = {group[0].index for group in groups}
        # Only rows with an observed real HTTP write count as actual pending
        # requests; a pre-send failure cannot raise the in-flight peak.
        peak = overlap_peak(
            [
                row
                for row in rows
                if row["index"] in first_indices and row.get("invoke_write") == "OBSERVED"
            ]
        )
        spool.append(
            "preparation",
            {
                "first_wave_actual_peak_interval_inflight": peak,
                "required": SLOTS,
                "status": "OBSERVED" if peak >= SLOTS else "INCOMPLETE",
            },
        )
        assembly.first_wave_peak = peak
    return rows


def plan_pop(mode):
    return mode in ("complete", "realSM2delegation_noAtomic")


def complete_export_index(*, expected_task_ids, packages, output_path):
    """Hash every complete prepartitioned E4 package plus a total original index."""
    expected_task_ids = tuple(expected_task_ids)
    if len(set(expected_task_ids)) != len(expected_task_ids):
        raise ValueError("duplicate planned task partition")
    packages = list(packages)
    if {p["task_id"] for p in packages} != set(expected_task_ids) or len(packages) != len(
        expected_task_ids
    ):
        raise MissingPrerequisite("complete per-task export collection required")
    required = {"S", "H", "trust", "history", "latest", "pin"}
    indexed = []
    for package in packages:
        if set(package["files"]) != required or not package.get("expired_or_revoked"):
            raise MissingPrerequisite("fixed E4 file set and actual expiry/revocation required")
        files = {}
        for kind, source in package["files"].items():
            path = Path(source)
            raw = path.read_bytes()
            files[kind] = {
                "path": str(path.resolve()),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        indexed.append(
            {
                "task_id": package["task_id"],
                "files": files,
                "attempt_indices": package["attempt_indices"],
                "effect_ids": package["effect_ids"],
                "oracle_refs": package["oracle_refs"],
                "caps": package["caps"],
            }
        )
    result = {
        "status": "COMPLETE_ORIGINAL_INDEX",
        "task_count": len(indexed),
        "packages": indexed,
        "total_bytes": sum(f["bytes"] for p in indexed for f in p["files"].values()),
    }
    Path(output_path).write_text(json.dumps(result, indent=2))
    return result


# Native implementation below is source code, not an ignored historical driver.
# Its trusted host adapter uses the already frozen normal supervisor, and the
# holder/operator/gateway processes use only their exact normal role mounts.


def _fixture():
    try:
        import a34_fixture as fixture
    except ModuleNotFoundError:
        from tests.fixtures import a34_experiment as fixture
    return fixture


def _native_config():
    from agent_guard.demo.config import load_run_config

    return load_run_config(Path("/owned/run/run.json").read_bytes(), base_dir=Path("/owned/run"))


def _wave_tasks(config):
    from datetime import datetime

    fixture = _fixture()
    # Host writes this file per wave and each reader container independently
    # verified the current exact bytes before any read: there is no secondary
    # stale fallback.
    wave = load_strict_json(Path("/control/measurement-wave.json").read_bytes())
    return wave, tuple(
        fixture.TaskInputs(
            t,
            config.scope["tenant_id"],
            "user-demo",
            datetime.fromisoformat(wave["expires_at"]),
        )
        for t in wave["tasks"]
    )


class NativeRolePipe:
    """Multiplex public observations; private root login goes to planner stdin."""

    def __init__(self, owner, role):
        import subprocess
        from concurrent.futures import Future

        self.future_type = Future
        self.owner, self.role = owner, role
        # State lock guards id allocation/pending futures; the write lock only
        # serializes stdin writes so a blocked writer can never delay response
        # delivery to the reader (bounded backpressure: concurrent submits
        # queue on writes, responses stay deliverable).
        self.lock, self.pending, self.sequence = threading.Lock(), {}, 0
        self.write_lock = threading.Lock()
        owner.inspect(role)
        self.stderr = (owner.root / (role + "-measurement.stderr")).open("wb")
        self.process = subprocess.Popen(
            [
                "docker",
                "exec",
                "-i",
                owner.ids[role],
                "python",
                "-u",
                "/control/measurement-entry.py",
                "pipe",
                role,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr,
            start_new_session=True,
            env=owner.env,
        )
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                row = json.loads(line)
                with self.lock:
                    future = self.pending.pop(row["id"])
                if "error" in row:
                    future.set_exception(MissingPrerequisite(row["error"]))
                else:
                    future.set_result(row["value"])
        finally:
            code = self.process.wait()
            with self.lock:
                for future in self.pending.values():
                    if not future.done():
                        future.set_exception(MissingPrerequisite("native role exited"))
                self.pending.clear()
            (self.owner.root / (self.role + "-measurement.native.json")).write_text(
                json.dumps(
                    {
                        "role": self.role,
                        "launcher_pid": self.process.pid,
                        "native_exit": code,
                        "container_id": self.owner.ids[self.role],
                    }
                )
            )

    def _write_bounded(self, payload, deadline):
        """Write one control message under one absolute monotonic deadline.

        A docker exec stdin is a finite kernel pipe: an untimed write could
        block a worker thread past the caller's ``call`` timeout, and a
        blocked writer holding ``write_lock`` could stall ``close``. The real
        descriptor is therefore written in non-blocking mode with the caller
        deadline checked on every iteration (including after each successful
        partial write and around select); surrogate stdin objects without a
        descriptor keep the plain in-process write used by the unit
        regressions. Any failure that leaves an incomplete frame invalidates
        the stream so a later message can never be spliced onto a torn line.
        """
        stream = self.process.stdin
        try:
            fd = stream.fileno()
        except (AttributeError, OSError, ValueError):
            fd = None
        if fd is None:
            stream.write(payload)
            stream.flush()
            return
        import select

        if getattr(self, "_write_broken", False):
            raise MissingPrerequisite("role pipe protocol invalidated by partial write")
        written_total = 0
        os.set_blocking(fd, False)
        try:
            view = memoryview(payload)
            while view:
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("role pipe write deadline expired")
                try:
                    written = os.write(fd, view)
                except BlockingIOError:
                    written = 0
                if written:
                    view = view[written:]
                    written_total += written
                    continue
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("role pipe write deadline expired")
                select.select([], [fd], [], remaining)
        except BaseException:
            if 0 < written_total < len(payload):
                self._write_broken = True
            raise
        finally:
            try:
                os.set_blocking(fd, True)
            except OSError:
                pass

    def _submit_deadline(self, value, deadline):
        with self.lock:
            self.sequence += 1
            ident = self.sequence
            future = self.future_type()
            self.pending[ident] = future
        payload = json.dumps({"id": ident, "value": value}).encode() + b"\n"
        try:
            # The same absolute deadline covers lock acquisition and every
            # write/select step; a busy writer is never given a fresh full
            # timeout after the lock is granted.
            if deadline is None:
                acquired = self.write_lock.acquire()
            else:
                acquired = self.write_lock.acquire(timeout=max(deadline - time.monotonic(), 0))
            if not acquired:
                raise TimeoutError("role pipe write lock deadline expired")
            try:
                self._write_bounded(payload, deadline)
            finally:
                self.write_lock.release()
        except BaseException:
            with self.lock:
                self.pending.pop(ident, None)
            raise
        return future

    def submit(self, value, *, timeout=120):
        deadline = None if timeout is None else time.monotonic() + timeout
        return self._submit_deadline(value, deadline)

    def call(self, value, *, timeout=120):
        deadline = time.monotonic() + timeout
        future = self._submit_deadline(value, deadline)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("role call deadline expired")
        return future.result(remaining)

    def close(self):
        import subprocess

        code, failure = None, None
        try:
            if self.process.poll() is None:
                # A writer that overran its bounded deadline must not block
                # shutdown: escalate the child and leave the failure recorded.
                if self.write_lock.acquire(timeout=30):
                    try:
                        self.process.stdin.close()
                    finally:
                        self.write_lock.release()
                else:
                    failure = MissingPrerequisite("role pipe writer did not stop in 30s")
            try:
                code = self.process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                # Bounded escalation only; the actual wait result is recorded.
                self.process.terminate()
                try:
                    code = self.process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    code = self.process.wait(timeout=30)
            self.reader.join(timeout=5)
            if self.reader.is_alive():
                failure = MissingPrerequisite("native stdout writer has not STOPped")
        finally:
            self.stderr.close()
        if failure is not None:
            raise failure
        return code


class RemoteTaskClient:
    def __init__(self, assembly, task):
        self.assembly, self.task = assembly, task
        self.order_operation_id = None

    def prepare(self, intent, *, body_builder, attack_transform=None):
        # All body and attack material is constructed inside the role; the host
        # receives a bounded public handle only, never a token/proof.
        if intent.category == "attack" and intent.attack_class == 8:
            commit_start = time.monotonic_ns()
            result = self.assembly.pipes["planner"].call({"action": "revoke", "slot": intent.task})
            self.assembly.revocations[intent.index] = {
                "commit_lower_ns": commit_start,
                "commit_upper_ns": time.monotonic_ns(),
                "response_status": result[0],
            }
        as_control = None
        if intent.category == "attack" and intent.attack_class == 7:
            as_control = self.assembly.pipes["selector"].call(
                {"action": "delegation_expansion", "slot": intent.task, "intent": asdict(intent)}
            )
        return self.assembly.pipes["executor"].call(
            {
                "as_control": as_control,
                "action": "prepare",
                "intent": asdict(intent),
                "order_operation_id": self.order_operation_id,
            }
        )

    def send(self, intent, material, *, lose_response=False, barrier=None):
        row = self.assembly.pipes["executor"].call(
            {
                "action": "send",
                "intent": asdict(intent),
                "material_handle": material["handle"],
                "lose_response": lose_response,
                "first_barrier": barrier is not None,
            },
            timeout=120,
        )

        row["measurement_kind"] = (
            ("WARMUP" if intent.category == "warmup" else "PILOT")
            if self.assembly.receipt["excluded_warmup"]
            else "OFFICIAL"
        )
        row["excluded_from_official"] = self.assembly.receipt["excluded_warmup"]
        return row


class NativeOwnedAssembly:
    """Concrete genuine normal AS/three holders/TLS/PG/worker/audit assembly.

    The caller supplies a frozen Owner instance only to retain exact existing
    resource allocation and finally cleanup policy. No assembly callbacks are
    required. No peer baseline implementation is imported.
    """

    def __init__(self, owner, *, plan):
        self.owner, self.plan = owner, plan
        self.pipes, self.current_tasks, self.receipt = {}, [], {}
        self.rows, self.observations, self.revocations = {}, {}, {}
        self.packages, self.wave_history = [], []
        self.measurement_start_ns = None
        self.measurement_end_ns = None
        self.completion_rows = []
        self.final_completion = None
        self.first_wave_peak = None
        self.closed = False
        self.resource_process = None
        self.resource_thread = None
        self.resource_lock = threading.Lock()
        self.body_builder = None  # exact body is constructed inside the holder UID
        self.attack_transform = None  # remote role performs actual transformation
        self._install_control()
        # Writer role commands are fixed to this current source entry point.
        original = owner.command

        def command(role, stage):
            if role in ("gateway", "worker", "publisher") and "hold" not in stage:
                owner.inspect(role)
                return [
                    "docker",
                    "exec",
                    "-i",
                    owner.ids[role],
                    "python",
                    "-u",
                    "/control/measurement-entry.py",
                    "service",
                    role,
                ]
            return original(role, stage)

        owner.command = command
        self.original_services = owner.services

        def services(resume=False):
            if resume and plan.mode == "complete":
                # The publisher of this wave is built for exactly the current
                # wave's committed task descriptors; persist exactly those
                # tasks' credentials (the accumulated directory grows past the
                # strict JSON byte bound and the exact-set publisher check).
                owner.init(
                    "measurement-publisher-credentials",
                    "import os,json;from pathlib import Path;tasks="
                    + repr(list(self.current_tasks))
                    + ";v={p.stem:json.loads(p.read_text()) "
                    "for p in Path('/owned/run/operator/task-audit').glob('*.json')"
                    " if p.stem in tasks};"
                    "assert set(v)==set(tasks),'wave credentials required';"
                    "p=Path('/owned/run/publisher/task-audit.json');p.write_text(json.dumps(v));"
                    "os.chown(p,"
                    + str(owner.settings["uids"]["publisher"])
                    + ","
                    + str(owner.settings["uids"]["publisher"])
                    + ");p.chmod(0o400)",
                )
                return self.original_services(resume=resume)
            if resume:
                # Research-only modes have no production audit/checkpoint
                # registration (receipt/journal/audit capability is
                # NOT_APPLICABLE and only the complete-mode bootstrap
                # registers the audit signer), so the resumed writer set must
                # not require audit-serve; auth/gateway readiness only.
                for role in ("as", "gateway", "worker", "publisher"):
                    owner.call(["docker", "start", owner.ids[role]])
                    stage = (
                        ["worker-serve"]
                        if role == "worker"
                        else ["publisher-serve"]
                        if role == "publisher"
                        else ["actor", "--stage", role, "--role", role]
                    )
                    owner.start_child(role, stage)
                owner.ready(include_audit=False)
                return None
            # Non-resume: the official runner re-enters per wave, so an
            # already-serving as/gateway child must not be started twice.
            for role in ("as", "gateway"):
                current = owner.children.get(role)
                if current is None or current["process"].poll() is not None:
                    owner.start_child(role, ["actor", "--stage", role, "--role", role])
            owner.ready(include_audit=False)
            return None

        owner.services = services
        for role in ("operator", "planner", "selector", "executor"):
            self.pipes[role] = NativeRolePipe(owner, role)
        self._start_resource_samples()

    def _install_control(self):
        import shutil

        fixture_path = Path(__file__).resolve().parents[2] / "tests/fixtures/a34_experiment.py"
        shutil.copyfile(fixture_path, self.owner.control / "a34_fixture.py")
        package = self.owner.control / "experiments" / "agent_guard_bench"
        package.mkdir(parents=True, exist_ok=True)
        # Exact whitelist; never consume a currently written baseline module.
        for name in (
            "__init__",
            "workload",
            "runner",
            "statistics",
            "microbench",
            "oracle",
            "research_contracts",
            "research_store",
            "research_service",
            "research_worker",
            "research_evidence",
        ):
            shutil.copyfile(Path(__file__).parent / (name + ".py"), package / (name + ".py"))
        shutil.copyfile(
            Path(__file__).parents[1] / "workload-v1.json",
            package.parent / "workload-v1.json",
        )
        shutil.copyfile(
            Path(__file__).parents[1] / "research-schema.sql",
            package.parent / "research-schema.sql",
        )
        (self.owner.control / "measurement-entry.py").write_text(
            "import sys;sys.path.insert(0,'/control');from experiments.agent_guard_bench.runner "
            "import native_entry;native_entry()\n"
        )

    def prepare_wave(self, plan, first_intentions, *, excluded_warmup):
        import secrets
        from datetime import datetime, timedelta, timezone

        self.current_tasks = [i.task for i in first_intentions]
        if (
            len(set(self.current_tasks)) != len(self.current_tasks)
            or len(self.current_tasks) > SLOTS
        ):
            raise ValueError("distinct bounded task wave required")
        wave = {
            "mode": plan.mode,
            "seed": plan.seed,
            "tasks": self.current_tasks,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "excluded_warmup": excluded_warmup,
        }
        path = self.owner.control / "measurement-wave.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(wave))
        temporary.replace(path)
        # Every role that reads the wave independently re-reads the current
        # control-bind bytes, re-computes the SHA-256 and re-parses mode/tasks
        # before any reader acts; a stale or invisible wave fails closed and
        # can never masquerade as the current plan. The file keeps its original
        # tasks/expiry/permissions and no production flag changes.
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = json.dumps(
            {"sha256": digest, "mode": plan.mode, "tasks": self.current_tasks}
        ).encode()
        verify_program = (
            "import hashlib,json,sys;expected=json.loads(sys.stdin.read());"
            "raw=open('/control/measurement-wave.json','rb').read();"
            "assert hashlib.sha256(raw).hexdigest()==expected['sha256'];"
            "wave=json.loads(raw);"
            "assert wave['mode']==expected['mode'];"
            "assert wave['tasks']==expected['tasks'];"
            "print('WAVE_CURRENT')"
        )
        for role in ("operator", "planner", "selector", "executor"):
            self.owner.call(
                [
                    "docker",
                    "exec",
                    "-i",
                    self.owner.ids[role],
                    "python",
                    "-c",
                    verify_program,
                ],
                input=expected,
            )
        self.pipes["operator"].call({"action": "provision"}, timeout=180)
        self.resource_before = self.pipes["operator"].call({"action": "resources"}, timeout=180)
        if self.wave_history:
            for role in ("as", "gateway"):
                self.owner.call(["docker", "start", self.owner.ids[role]])
        self.owner.services()
        login = json.loads(
            self.owner.call(
                [
                    "docker",
                    "exec",
                    self.owner.ids["operator"],
                    "python",
                    "-c",
                    "from pathlib import Path;"
                    "print(Path('/owned/run/operator/user-login.json').read_text())",
                ],
                private=True,
            ).stdout
        )
        started = time.monotonic_ns()
        paths, metadata = [], []
        for intent in first_intentions:
            slot = intent.task
            for role in ("planner", "selector", "executor"):
                self.pipes[role].call({"action": "new", "slot": slot})
            self.pipes["planner"].call({"action": "root", "slot": slot, "login": login})
            path_ids = [self.pipes["planner"].call({"action": "metadata", "slot": slot})]
            for parent, child in (("planner", "selector"), ("selector", "executor")):
                receiving = self.pipes[child].submit(
                    {"action": "receive", "slot": slot, "parent": parent}
                )
                time.sleep(0.01)
                self.pipes[parent].call(
                    {
                        "action": "delegate",
                        "slot": slot,
                        "key": secrets.token_urlsafe(32),
                    }
                )
                receiving.result(60)
                path_ids.append(self.pipes[child].call({"action": "metadata", "slot": slot}))
            paths.append({"task": slot, "ids": [m["grant_id"] for m in path_ids]})
            metadata.append(path_ids)
            if intent.attack_class == 9:
                # A9 pairs have independent sibling middle/leaf grants sharing
                # the already genuine planner root, not copied counters.
                sibling = slot + "-sibling"
                for role in ("selector", "executor"):
                    self.pipes[role].call({"action": "new", "slot": sibling, "task": slot})
                receiving = self.pipes["selector"].submit(
                    {"action": "receive", "slot": sibling, "parent": "planner"}
                )
                time.sleep(0.01)
                self.pipes["planner"].call(
                    {
                        "action": "delegate",
                        "slot": slot,
                        "key": secrets.token_urlsafe(32),
                    }
                )
                receiving.result(60)
                receiving = self.pipes["executor"].submit(
                    {"action": "receive", "slot": sibling, "parent": "selector"}
                )
                time.sleep(0.01)
                self.pipes["selector"].call(
                    {
                        "action": "delegate",
                        "slot": sibling,
                        "key": secrets.token_urlsafe(32),
                    }
                )
                receiving.result(60)
                paths.append(
                    {
                        "task": slot,
                        "ids": [
                            path_ids[0]["grant_id"],
                            self.pipes["selector"].call({"action": "metadata", "slot": sibling})[
                                "grant_id"
                            ],
                            self.pipes["executor"].call({"action": "metadata", "slot": sibling})[
                                "grant_id"
                            ],
                        ],
                    }
                )
        del login
        if any(i.attack_class == 1 for i in first_intentions):
            self.pipes["operator"].call({"action": "prepare_stolen_parents"})
            self.owner.init(
                "measurement-private-wrong-holder-parent",
                "import os,shutil;from pathlib import Path;"
                "src=Path('/owned/run/operator/attack-parent');"
                "dst=Path('/owned/run/executor/attack-parent');dst.mkdir(mode=0o700,exist_ok=True);"
                "os.chown(dst,"
                + str(self.owner.settings["uids"]["executor"])
                + ","
                + str(self.owner.settings["uids"]["executor"])
                + ");\n"
                "for task in " + repr(self.current_tasks) + ":\n"
                " source=src/task;target=dst/task;shutil.copyfile(source,target);os.chown(target,"
                + str(self.owner.settings["uids"]["executor"])
                + ","
                + str(self.owner.settings["uids"]["executor"])
                + ");target.chmod(0o400)\n",
            )
        if plan.mode != "complete":
            self.pipes["operator"].call({"action": "initialize_paths", "paths": paths})
        before_bootstrap = time.monotonic_ns()
        phase = {"refresh_start_ns": before_bootstrap}
        if plan.mode == "complete":
            # This operator action obtains the actual four-native-writer stop
            # receipt through the normal bridge, then remote commit/local
            # confirm. Writers stopped by a previous wave's freeze need a live
            # hold launcher before that drain, exactly like the research path.
            self._refresh_stale_writer_handles()
            phase["bootstrap_call_start_ns"] = time.monotonic_ns()
            bootstrap = self.pipes["operator"].call({"action": "bootstrap"}, timeout=240)
            phase["bootstrap_call_end_ns"] = time.monotonic_ns()
        else:
            self._refresh_stale_writer_handles()
            phase["bootstrap_call_start_ns"] = time.monotonic_ns()
            bootstrap = {"status": "N/A_RESEARCH_AUDIT", "stopped": self.owner.drain()}
            phase["bootstrap_call_end_ns"] = time.monotonic_ns()
        self.owner.services(resume=True)
        phase["services_end_ns"] = time.monotonic_ns()
        end = time.monotonic_ns()
        self.receipt = {
            "tasks": self.current_tasks,
            "jit_start_ns": started,
            "jit_end_ns": before_bootstrap,
            "bootstrap_resume_end_ns": end,
            "genuine_path_metadata": metadata,
            "bootstrap": bootstrap,
            "excluded_warmup": excluded_warmup,
            "phase_timings_ns": phase,
        }
        self.receipt["resources_before"] = self.resource_before
        self.wave_history.append(self.receipt)
        return {task: RemoteTaskClient(self, task) for task in self.current_tasks}

    def wave_receipt(self):
        return self.receipt

    def observe_original(self, intent, row):
        observation = self.pipes["operator"].call(
            {"action": "observe", "intent": asdict(intent), "row": row}
        )
        row["auth_pass"] = observation.get("auth_pass")
        row["new_accept"] = observation.get("new_accept")
        self.rows[intent.index] = row
        self.observations[intent.index] = observation
        if row.get("wire_sent") and not self.receipt.get("excluded_warmup"):
            self.measurement_start_ns = min(
                self.measurement_start_ns or row["send_ns"], row["send_ns"]
            )
            self.measurement_end_ns = max(self.measurement_end_ns or row["end_ns"], row["end_ns"])
        return observation

    def original_witness(self, intent):
        original = self.observations.get(intent.target_index, {})
        if not original.get("operation_id"):
            return original
        fresh = self.pipes["operator"].call(
            {
                "action": "observe",
                "intent": asdict(intent),
                "row": self.rows.get(intent.target_index, {}),
            }
        )
        fresh["actual_response_loss"] = (
            self.rows.get(intent.target_index, {}).get("response_loss", {}).get("transport_closed")
            is True
        )
        return fresh

    def proof_consumption_witness(self, intent):
        return self.pipes["operator"].call(
            {
                "action": "proof_witness",
                "intent": asdict(intent),
                "proof_digest": self.rows.get(intent.target_index, {}).get("proof_digest"),
            }
        )

    def wait_terminal(self, intent, observation, *, deadline_ns):
        operation_id = observation.get("operation_id")
        if not operation_id:
            return {"status": "MISSING_COMMITTED_ORIGINAL"}
        while time.monotonic_ns() < deadline_ns:
            result = self.pipes["operator"].call(
                {"action": "operation", "operation_id": operation_id}
            )
            if result.get("terminal"):
                # Genuine fresh query while current authorization remains live.
                query = self.pipes["executor"].call(
                    {
                        "action": "query",
                        "slot": intent.task,
                        "operation_id": operation_id,
                    }
                )
                result["authorized_query_status"] = query["http_status"]
                result["host_observed_ns"] = time.monotonic_ns()
                self.completion_rows.append(result)
                return result
            time.sleep(0.05)
        return {
            "status": "DRAIN_TIMEOUT",
            "operation_id": operation_id,
            "deadline_ns": deadline_ns,
        }

    def drain_wave(self, *, deadline_ns):
        while time.monotonic_ns() < deadline_ns:
            facts = self.pipes["operator"].call({"action": "wave_completion"})
            if facts["nonterminal"] == 0 and (
                self.plan.mode != "complete"
                or facts["pending_receipts"] == 0
                and facts["unanchored_records"] == 0
            ):
                break
            time.sleep(0.1)
        facts.update(host_observed_ns=time.monotonic_ns(), lifecycle_host_deadline_ns=deadline_ns)
        facts["deadline_ns"] = facts["observed_ns"] + max(0, deadline_ns - time.monotonic_ns())
        self.completion_rows.append(facts)
        if self.plan.mode != "complete":
            self._refresh_stale_writer_handles()
            self.owner.drain()
        return facts

    def snapshot_wave(self):
        self.receipt["resources_after"] = self.pipes["operator"].call(
            {"action": "resources"}, timeout=180
        )
        value = self.pipes["operator"].call({"action": "snapshot"}, timeout=180)
        private = self.owner.root / "private-originals"
        private.mkdir(mode=0o700, exist_ok=True)
        wave = private / ("wave-" + str(len(self.wave_history)))
        wave.mkdir(mode=0o700)
        self.owner.call(
            [
                "docker",
                "cp",
                self.owner.ids["operator"] + ":" + value["private_snapshot_path"],
                str(wave / "database.json"),
            ]
        )
        wire = self.owner.call(
            [
                "docker",
                "exec",
                self.owner.ids["executor"],
                "python",
                "-c",
                "import io,sys,zipfile;from pathlib import Path;"
                "root=Path('/tmp/measurement-private-wire');"
                "out=io.BytesIO();z=zipfile.ZipFile(out,'w',compression=zipfile.ZIP_STORED);"
                "[z.writestr(str(p.relative_to(root)),p.read_bytes()) for p in "
                "sorted(root.rglob('*')) if p.is_file()];"
                "z.close();sys.stdout.buffer.write(out.getvalue())",
            ],
            private=True,
        )
        (wave / "wire-originals.zip").write_bytes(wire.stdout)
        for path in wave.rglob("*"):
            path.chmod(0o700 if path.is_dir() else 0o600)
        return value

    def export_wave(self, wave, *, expiry_or_revoke_required):
        for group in wave:
            self.pipes["planner"].call({"action": "revoke", "slot": group[0].task})
        # The freeze action drains the four writers through the same bridge
        # control: give a dead launcher a real hold actor first, never a stale
        # handle for a stopped container.
        self._refresh_stale_writer_handles()
        frozen = self.pipes["operator"].call({"action": "freeze"}, timeout=240)
        task_ids = self.current_tasks
        self.owner.init(
            "measurement-export-inputs",
            "import os,shutil;from pathlib import Path\nfor task in " + repr(task_ids) + ":\n"
            " src=Path('/owned/run/operator')/task;dst=Path('/owned/run/export')/task\n"
            " if dst.exists():raise ValueError('export overwrite')\n shutil.copytree(src,dst)\n"
            " for p in [dst,*dst.iterdir()]:os.chown(p,"
            + str(self.owner.settings["uids"]["export"])
            + ","
            + str(self.owner.settings["uids"]["export"])
            + ");p.chmod(0o700 if p.is_dir() else 0o444)\n"
            " out=Path('/results')/task;out.mkdir()\n"
            " for p in src.iterdir():shutil.copyfile(p,out/p.name);(out/p.name).chmod(0o444)\n"
            " os.chown(out,"
            + str(self.owner.settings["uids"]["export"])
            + ","
            + str(self.owner.settings["uids"]["export"])
            + ");out.chmod(0o755)",
        )
        self.owner.inspect("export")
        native = self.owner.call(
            [
                "docker",
                "exec",
                self.owner.ids["export"],
                "python",
                "/control/measurement-entry.py",
                "export",
            ],
            timeout=240,
        )
        exports = json.loads(native.stdout)
        target = self.owner.root / "complete-task-packages"
        target.mkdir(exist_ok=True)
        for task in task_ids:
            self.owner.call(
                [
                    "docker",
                    "cp",
                    self.owner.ids["export"] + ":/results/" + task,
                    str(target),
                ]
            )
        result = []
        for package in exports:
            folder = target / package["task_id"]
            mapping = {
                "S": "task-bundle.ndjson",
                "H": "checkpoint-history.ndjson",
                "trust": "public-trust.json",
                "history": "checkpoint-history.ndjson",
                "latest": "latest-checkpoint.json",
                "pin": "external-pin.json",
            }
            result.append(
                {
                    **package,
                    "files": {k: str(folder / f) for k, f in mapping.items()},
                    "frozen": frozen,
                    "expired_or_revoked": expiry_or_revoke_required,
                    "attempt_indices": [
                        r["index"] for r in self.rows.values() if r["task"] == package["task_id"]
                    ],
                    "effect_ids": [
                        o["operation_id"]
                        for o in self.observations.values()
                        if o.get("task") == package["task_id"] and o.get("operation_id")
                    ],
                    "oracle_refs": ["oracle.jsonl"],
                    "caps": {
                        "bundle_bytes": 268435456,
                        "production_http_body_bytes": 65536,
                    },
                }
            )
        self.packages.extend(result)
        return result

    def drain_repeat(self, *, deadline_ns):
        tasks = [
            t for wave in self.wave_history if not wave["excluded_warmup"] for t in wave["tasks"]
        ]
        while True:
            facts = self.pipes["operator"].call({"action": "wave_completion", "tasks": tasks})
            if facts["nonterminal"] == 0 and (
                self.plan.mode != "complete"
                or facts["pending_receipts"] == 0
                and facts["unanchored_records"] == 0
            ):
                break
            if facts["observed_ns"] >= deadline_ns:
                break
            time.sleep(0.1)
        facts.update(
            host_observed_ns=time.monotonic_ns(),
            deadline_ns=deadline_ns,
            last_measured_send_ns=deadline_ns - DRAIN_SECONDS * 1_000_000_000,
        )
        self.final_completion = facts
        return facts

    def completion_metrics(self):
        facts = self.final_completion
        if facts is None or self.measurement_start_ns is None:
            return {}
        result = {}
        for name, field in (
            ("terminal", "terminal_count"),
            ("READY", "ready_count"),
            ("anchor", "anchor_count"),
        ):
            if self.plan.mode != "complete" and name != "terminal":
                continue
            result[name] = {
                "n": facts[field],
                "expected_n": facts["accepted"],
                "start_ns": self.measurement_start_ns,
                "end_ns": facts["observed_ns"],
                "deadline_ns": facts["deadline_ns"],
            }
        return result

    def lineage(self):
        return {
            "owner": self.owner.owner,
            "run": self.owner.run,
            "installation": self.owner.args.mode,
            "waves": self.wave_history,
            "original_failed_runs_retained": True,
        }

    def stop(self):
        if self.closed:
            return json.loads((self.owner.root / "STOP.json").read_text())
        stop_errors, native_roles, native_role_failures = {}, {}, {}
        for role, pipe in self.pipes.items():
            try:
                native_roles[role] = pipe.close()
            except BaseException as exc:
                # A failing pipe must never skip owned-resource cleanup below.
                native_roles[role] = pipe.process.returncode
                native_role_failures[role] = type(exc).__name__
                stop_errors["role:" + role] = type(exc).__name__
        try:
            sampler = self._stop_resource_samples()
        except BaseException as exc:
            sampler = {
                "status": "STOP_HELPER_FAILED",
                "native_exit": None,
                "exited": False,
                "error": type(exc).__name__,
            }
            stop_errors["resource_sampler_helper"] = type(exc).__name__
        if sampler.get("exited") is not True:
            stop_errors["resource_sampler"] = sampler.get("error") or "NOT_EXITED"
        try:
            self.owner.cleanup()
        except BaseException as exc:
            stop_errors["cleanup"] = type(exc).__name__
        try:
            cleanup = json.loads((self.owner.root / "cleanup.json").read_text())
        except BaseException as exc:
            cleanup = {
                "resources_remaining": None,
                "cleanup_receipt_error": type(exc).__name__,
            }
        receipt = {
            "status": "STOP_ERRORS" if stop_errors else "STOP",
            "no_more_writes": True,
            "owner": self.owner.owner,
            "run": self.owner.run,
            "resources_remaining": cleanup.get("resources_remaining"),
            "cleanup_receipt": str(self.owner.root / "cleanup.json"),
            "native_roles": native_roles,
            "native_role_failures": native_role_failures,
            "resource_sampler": sampler,
            "stop_errors": stop_errors,
        }
        (self.owner.root / "STOP.json").write_text(json.dumps(receipt, indent=2))
        self.closed = True
        if cleanup.get("resources_remaining") != 0:
            raise MissingPrerequisite("owned runtime resources remain")
        if stop_errors:
            raise MissingPrerequisite(
                "native stop error: " + json.dumps(stop_errors, sort_keys=True)
            )
        return receipt


def _public_fact(value, name=""):
    from decimal import Decimal

    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            raise ValueError("non-integral Decimal in public integer observation")
        return int(value)
    if name in {
        "token_jws",
        "token",
        "proof",
        "receipt_jws",
        "checkpoint_jws",
        "source_material",
    }:
        if type(value) is dict and set(value) == {"bytes", "sha256"}:
            if (
                type(value["bytes"]) is not int
                or value["bytes"] < 0
                or type(value["sha256"]) is not str
                or len(value["sha256"]) != 64
            ):
                raise ValueError("strict prehashed original required")
            return value
        raw = value.encode() if isinstance(value, str) else bytes(value or b"")
        return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if isinstance(value, (bytes, memoryview)):
        raw = bytes(value)
        return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if isinstance(value, dict):
        return {k: _public_fact(v, k) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_public_fact(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


_OBSERVABILITY_POOLS = {}
_OBSERVABILITY_POOL_LOCK = threading.Lock()
_OBSERVABILITY_BUDGET = 16
_OBSERVABILITY_CHECKOUT_SECONDS = 30


@contextlib.contextmanager
def _reused_observability_connection(dsn, slot):
    """Bounded per-domain observability connection pool for operator handlers.

    Sustained complete-mode runs showed that a thread-local cache accumulated
    one connection per handler thread per domain (up to 64+64), driving the
    owned PostgreSQL towards max_connections and slowing the per-wave writer
    drain past the 180s child-token TTL (legal rows then answered 403 EXPIRED).
    The pool keeps at most ``_OBSERVABILITY_BUDGET`` live cached connections
    per domain process-wide, hands each connection to one caller at a time,
    and still opens a fresh REPEATABLE READ READ ONLY transaction per call, so
    no fact is cached and role separation is unchanged. When every pooled
    connection is checked out, a caller waits a bounded time and then uses a
    single-use connection instead of blocking forever or churning per call.
    """
    import psycopg
    from psycopg.rows import dict_row

    with _OBSERVABILITY_POOL_LOCK:
        state = _OBSERVABILITY_POOLS.get(slot)
        if state is None:
            state = _OBSERVABILITY_POOLS[slot] = {
                "queue": queue.LifoQueue(maxsize=_OBSERVABILITY_BUDGET),
                "live": 0,
            }
    conn = None
    pooled = False
    try:
        conn = state["queue"].get_nowait()
        pooled = True
    except queue.Empty:
        conn = None
    if conn is not None and (conn.closed or getattr(conn, "broken", False)):
        try:
            conn.close()
        except Exception:
            pass
        with _OBSERVABILITY_POOL_LOCK:
            state["live"] = max(state["live"] - 1, 0)
        conn = None
        pooled = False
    if conn is None:
        with _OBSERVABILITY_POOL_LOCK:
            if state["live"] < _OBSERVABILITY_BUDGET:
                state["live"] += 1
                pooled = True
        if pooled:
            conn = psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row)
        else:
            try:
                conn = state["queue"].get(timeout=_OBSERVABILITY_CHECKOUT_SECONDS)
                pooled = True
                if conn.closed or getattr(conn, "broken", False):
                    try:
                        conn.close()
                    except Exception:
                        pass
                    # Replace the dead pooled connection without changing the
                    # live count: the closed one already held a slot.
                    conn = psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row)
            except queue.Empty:
                # All pooled connections are checked out: single-use fallback,
                # closed on exit, so the live count stays bounded.
                conn = psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row)
    try:
        yield conn
    except BaseException:
        # A failed call must not poison the pool: roll back any open/implicit
        # transaction and discard a dead connection so the next observation
        # reconnects instead of failing forever.
        try:
            conn.rollback()
        except Exception:
            pass
        if getattr(conn, "closed", False) or getattr(conn, "broken", False):
            try:
                conn.close()
            except Exception:
                pass
            if pooled:
                with _OBSERVABILITY_POOL_LOCK:
                    state["live"] = max(state["live"] - 1, 0)
            pooled = False
        raise
    else:
        if pooled and not (conn.closed or getattr(conn, "broken", False)):
            try:
                state["queue"].put_nowait(conn)
            except queue.Full:
                try:
                    conn.close()
                except Exception:
                    pass
                with _OBSERVABILITY_POOL_LOCK:
                    state["live"] = max(state["live"] - 1, 0)
        else:
            try:
                conn.close()
            except Exception:
                pass
            if pooled:
                with _OBSERVABILITY_POOL_LOCK:
                    state["live"] = max(state["live"] - 1, 0)


def _native_operator(config, command):
    import psycopg

    from agent_guard.demo.__main__ import live_drain
    from agent_guard.demo.provision import _dsn

    fixture = _fixture()
    wave, tasks = _wave_tasks(config)
    mode = wave["mode"]
    action = command["action"]
    if command.get("tasks") is not None:
        wave = dict(wave, tasks=command["tasks"])
    dsn = _dsn(config.roles["operator"], "authority_dsn")
    op_table = "ag_operations" if mode == "complete" else "r34.operations"
    key_column = "idempotency_key" if mode == "complete" else "business_key"
    if action == "provision":
        fixture.provision_tasks(config, operator_dsn=dsn, tasks=tasks)
        fixture.task_operation_registries(config, tasks=tasks, directory="/registry")
        if mode == "complete":
            fixture.task_audit_credentials(
                config, tasks=tasks, directory=Path("/owned/run/operator/task-audit")
            )
        else:
            with psycopg.connect(dsn) as conn:
                if conn.execute("SELECT to_regclass('r34.counters')").fetchone()[0] is None:
                    conn.execute(Path("/control/experiments/research-schema.sql").read_text())
                    fixture.grant_research_authority(conn, research_role="demo_research")
        return {"provisioned": [t.task_id for t in tasks], "minted_grants": 0}
    if action == "prepare_stolen_parents":
        folder = Path("/owned/run/operator/attack-parent")
        folder.mkdir(mode=0o700, exist_ok=True)
        with psycopg.connect(dsn) as connection:
            for task in tasks:
                row = connection.execute(
                    "SELECT t.token_jws FROM ag_grants g JOIN ag_grant_tokens t USING(grant_id) "
                    "WHERE g.task_id=%s AND g.depth=0",
                    (task.task_id,),
                ).fetchone()
                if row is None:
                    raise MissingPrerequisite("genuine planner parent token absent")
                path = folder / task.task_id
                path.write_text(row[0])
                path.chmod(0o600)
        return {"private_parent_sources_prepared": len(tasks), "public_tokens": 0}
    if action == "initialize_paths":
        paths = command["paths"]
        by_task = {t.task_id: t for t in tasks}
        return fixture.initialize_research_paths(
            config,
            operator_dsn=dsn,
            task_paths=[(by_task[p["task"]], tuple(p["ids"])) for p in paths],
        )
    if action in ("bootstrap", "freeze"):
        from agent_guard.audit.client import AuditClient
        from agent_guard.audit.contracts import CheckpointTrust
        from agent_guard.audit.journal import describe_pending_tx
        from agent_guard.crypto.sm import serialize_sm2_public_key
        from agent_guard.server.factory import _load_public_key

        public = load_strict_json(config.public_manifest.read_bytes())
        trust = CheckpointTrust(
            "audit-sign-1",
            "AUDIT_SIGNER",
            serialize_sm2_public_key(
                _load_public_key(public["audit_keys"]["audit-sign-1"], "audit")
            ),
            1,
            None,
        )
        credentials = fixture.task_audit_credentials(
            config, tasks=tasks, directory=Path("/owned/run/operator/task-audit")
        )
        if action == "bootstrap":
            # Phase timings are recorded as an evidence line: sustained waves
            # showed the complete-mode bootstrap growing past the holder/token
            # deadlines, and the split isolates drain vs per-task registration.
            drain_start = time.monotonic_ns()
            stopped = live_drain(config)
            drain_end = time.monotonic_ns()
            descriptors = fixture.bootstrap_task_streams(
                config,
                tasks=tasks,
                stopped=stopped,
                trust_for=lambda _: trust,
                credentials_for=lambda d: fixture.task_registration_arguments(
                    credentials[d.scope.task_id]
                ),
            )
            streams_end = time.monotonic_ns()
            print(
                json.dumps(
                    {
                        "bootstrap_timing": {
                            "drain_ns": drain_end - drain_start,
                            "streams_ns": streams_end - drain_end,
                            "tasks": len(tasks),
                        }
                    }
                ),
                file=sys.stderr,
                flush=True,
            )
            return {task: asdict(descriptor) for task, descriptor in descriptors.items()}
        with psycopg.connect(dsn) as conn:
            descriptors = {
                t.task_id: describe_pending_tx(
                    conn,
                    scope_key=(config.scope["gateway_origin"], t.tenant_id, t.task_id),
                )
                for t in tasks
            }

        def reader(task):
            value = credentials[task.task_id]
            return AuditClient(
                config.endpoints["audit_origin"],
                ca_file=str(config.roles["operator"].public_config_file.parent / "ca.pem"),
                reader_credential=value["reader_id"] + ":" + value["reader_secret"],
                writer_credential=value["writer_id"] + ":" + value["writer_secret"],
            )

        frozen = fixture.freeze_task_exports(
            config,
            tasks=tasks,
            stopped=live_drain(config),
            reader_for=reader,
            public_trust_for=lambda t: fixture.task_public_trust(
                config, task=t, descriptor=descriptors[t.task_id]
            ),
            out_dir=config.roles["operator"].public_config_file.parent,
        )
        # latest is the real independently fetched signed checkpoint pin, not
        # a locally fabricated anchor. Preserve that exact JWS public artifact.
        for task in tasks:
            folder = Path("/owned/run/operator") / task.task_id
            pin = load_strict_json((folder / "external-pin.json").read_bytes())
            (folder / "latest-checkpoint.json").write_bytes(
                canonical_json_bytes({"checkpoint_jws": pin["checkpoint_jws"]})
            )
            (folder / "latest-checkpoint.json").chmod(0o444)
        return {
            task: {
                "checkpoints": value.history.checkpoint_count,
                "wire_bytes": value.history.wire_bytes,
            }
            for task, value in frozen.items()
        }
    if action == "resources":
        from .microbench import collect_database_storage, collect_process_hardware

        result = {
            "hardware": collect_process_hardware(),
            "connection_reuse": "NONE_PER_ATTEMPT_NEW_TLS_CONNECTION",
            "databases": {},
        }
        for domain in ("authority", "downstream", "audit"):
            with psycopg.connect(_dsn(config.roles["operator"], domain + "_dsn")) as db:
                result["databases"][domain] = collect_database_storage(db)
        return result
    with _reused_observability_connection(dsn, "authority") as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            conn.execute("SET LOCAL statement_timeout='30s'")
            if action == "observe":
                intent = command["intent"]
                operation = conn.execute(
                    "SELECT * FROM " + op_table + " WHERE tenant_id=%s AND task_id=%s "
                    "AND tool_id=%s AND " + key_column + "=%s",
                    (
                        config.scope["tenant_id"],
                        intent["task"],
                        intent["tool_id"],
                        intent["business_key"],
                    ),
                ).fetchone()
                now = conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
                if operation is None:
                    return {
                        "task": intent["task"],
                        "committed": False,
                        "terminal": False,
                        "db_clock": now.isoformat(),
                    }
                actual = command["row"]
                accepted_ns = int(operation["accepted_at"].timestamp() * 1_000_000_000)
                in_window = (
                    actual.get("send_unix_ns", 0) <= accepted_ns <= actual.get("end_unix_ns", 0)
                )
                result = {
                    "auth_pass": True,
                    "new_accept": in_window,
                    "task": intent["task"],
                    "committed": True,
                    "operation_id": operation["operation_id"],
                    "terminal": operation["status"] in ("SUCCEEDED", "FAILED"),
                    "status": operation["status"],
                    "immutable_intent": _public_fact(operation),
                    "db_clock": now.isoformat(),
                }
            elif action in ("operation", "proof_witness"):
                operation_id = command.get("operation_id")
                if action == "proof_witness":
                    intent = command["intent"]
                    operation = conn.execute(
                        "SELECT operation_id FROM " + op_table + " WHERE task_id=%s AND "
                        "tool_id=%s AND " + key_column + "=%s",
                        (intent["task"], intent["tool_id"], intent["business_key"]),
                    ).fetchone()
                    operation_id = operation["operation_id"] if operation else None
                    table = "ag_proofs" if mode == "complete" else "r34.proofs"
                    digest_column = "proof_digest" if mode == "complete" else "digest"
                    count = conn.execute(
                        "SELECT count(*) AS n FROM "
                        + table
                        + " WHERE operation_id=%s AND "
                        + digest_column
                        + "=%s",
                        (operation_id, command.get("proof_digest")),
                    ).fetchone()["n"]
                    return {
                        "consumed": count > 0,
                        "proof_registry_rows": count,
                        "operation_id": operation_id,
                        "capability": "MEASURED" if plan_pop(mode) else "N/A",
                    }
                row = conn.execute(
                    "SELECT status FROM " + op_table + " WHERE operation_id=%s",
                    (operation_id,),
                ).fetchone()
                return {
                    "observed_ns": time.monotonic_ns(),
                    "operation_id": operation_id,
                    "terminal": row and row["status"] in ("SUCCEEDED", "FAILED"),
                    "status": row["status"] if row else "MISSING",
                }
            elif action == "wave_completion":
                counts = conn.execute(
                    "SELECT count(*) AS accepted,count(*) FILTER (WHERE status IN "
                    "('SUCCEEDED','FAILED')) AS terminal,count(*) FILTER (WHERE status NOT IN "
                    "('SUCCEEDED','FAILED')) AS nonterminal FROM "
                    + op_table
                    + " WHERE task_id=ANY(%s)",
                    (wave["tasks"],),
                ).fetchone()
                result = dict(counts)
                result["terminal_count"] = result.pop("terminal")
                if mode == "complete":
                    receipts = conn.execute(
                        "SELECT count(*) FILTER (WHERE receipt_status='PENDING') AS pending,"
                        "count(*) FILTER (WHERE receipt_status='READY') AS ready "
                        "FROM ag_receipt_outbox "
                        "WHERE task_id=ANY(%s)",
                        (wave["tasks"],),
                    ).fetchone()
                    anchor = conn.execute(
                        "SELECT coalesce(sum(greatest(0,j.seq-coalesce(d.ack_sequence,0))),0) "
                        "AS gap "
                        "FROM (SELECT stream_id,max(seq) AS seq "
                        "FROM ag_audit_records GROUP BY stream_id) j "
                        "JOIN ag_audit_streams s USING(stream_id) "
                        "LEFT JOIN ag_audit_delivery d USING(stream_id) "
                        "WHERE s.task_id=ANY(%s)",
                        (wave["tasks"],),
                    ).fetchone()["gap"]
                    result.update(
                        pending_receipts=receipts["pending"],
                        ready_count=receipts["ready"],
                        unanchored_records=anchor,
                        anchor_count=receipts["ready"] if anchor == 0 else 0,
                    )
                else:
                    result.update(
                        pending_receipts="N/A",
                        ready_count="N/A",
                        unanchored_records="N/A",
                        anchor_count="N/A",
                    )
                result["excluded_warmup"] = wave["excluded_warmup"]
                result["observed_ns"] = time.monotonic_ns()
                result["clock_domain"] = "OWNED_LINUX_MONOTONIC"
                result["db_clock"] = (
                    conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"].isoformat()
                )
                return result
            elif action == "snapshot":
                tables = [
                    "ag_principals",
                    "ag_tasks",
                    "ag_grant_tokens",
                    "ag_verified_evidence",
                    "ag_operation_evidence",
                    "ag_grants",
                    "ag_operations",
                    "ag_ledger_events",
                    "ag_ledger_event_nodes",
                    "ag_proofs",
                    "ag_receipt_outbox",
                    "ag_execution_leases",
                    "ag_operation_review_flags",
                    "ag_audit_bootstrap",
                    "ag_audit_bootstrap_chunks",
                    "ag_audit_delivery_batches",
                    "ag_audit_streams",
                    "ag_audit_records",
                    "ag_audit_delivery",
                ]
                if mode != "complete":
                    tables += [
                        "r34." + t
                        for t in (
                            "counters",
                            "operations",
                            "events",
                            "nodes",
                            "proofs",
                            "leases",
                            "outbox",
                            "originals",
                        )
                    ]
                raw_snapshot = {
                    table: [dict(row) for row in conn.execute("SELECT * FROM " + table).fetchall()]
                    for table in tables
                }
                # Retain every original privately, with a public hash. No
                # token/proof bytes are put in public JSONL observations.
                folder = Path("/owned/run/operator/measurement-private")
                folder.mkdir(mode=0o700, exist_ok=True)
                path = folder / ("snapshot-" + wave["tasks"][0] + ".json")
                path.write_text(json.dumps(raw_snapshot, default=_private_json, sort_keys=True))
                path.chmod(0o600)
                snapshot = {
                    table: [_public_fact(row) for row in rows]
                    for table, rows in raw_snapshot.items()
                }
                snapshot["private_snapshot_path"] = str(path)
                snapshot["private_snapshot_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                snapshot["db_clock"] = (
                    conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"].isoformat()
                )
                snapshot["policy"] = {t.task_id: t.policy() for t in tasks}
                snapshot["scope"] = wave["tasks"]
                snapshot["production_budget_writes"] = (
                    "INDEPENDENT_COUNTER_SNAPSHOT_REQUIRES_BEFORE_AFTER_COMPARE"
                )
                snapshot["proof_capability"] = "MEASURED" if plan_pop(mode) else "N/A"
                snapshot["independent_audit"] = "MEASURED" if mode == "complete" else "N/A"
                result = snapshot
            else:
                raise ValueError("fixed operator action required")
    # DS has a separate RR connection, honestly not one distributed snapshot.
    with _reused_observability_connection(
        _dsn(config.roles["operator"], "downstream_dsn"), "downstream"
    ) as ds:
        with ds.transaction():
            ds.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if action == "observe":
                effects = ds.execute(
                    "SELECT * FROM ds_operations WHERE operation_id=%s",
                    (result["operation_id"],),
                ).fetchall()
                result["downstream_witness"] = [_public_fact(dict(r)) for r in effects]
            else:
                raw_downstream = {
                    table: [dict(r) for r in ds.execute("SELECT * FROM " + table).fetchall()]
                    for table in ("ds_operations", "ds_orders", "ds_notifications")
                }
                result["downstream"] = {
                    table: [_public_fact(r) for r in rows] for table, rows in raw_downstream.items()
                }
            result["downstream_db_clock"] = (
                ds.execute("SELECT clock_timestamp() AS now").fetchone()["now"].isoformat()
            )
    if action == "snapshot":
        raw_snapshot["independent_downstream"] = raw_downstream
        path.write_text(json.dumps(raw_snapshot, default=_private_json, sort_keys=True))
        path.chmod(0o600)
        result["private_snapshot_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        result["derived_metrics"] = _derive_independent_metrics(raw_snapshot, mode, tasks)
    if action == "observe" and mode == "complete":
        fixture.task_operation_registries(config, tasks=tasks, directory="/registry")[
            command["intent"]["task"]
        ].register(result["operation_id"])
    return result


def _malformed_quantity_bytes(changed, variant):
    """Exact wire bytes for one contract-invalid numeric quantity.

    The strict canonical encoder rejects -1/1.5/true/overflow before any wire
    write (root preflight: EncodingError in the pure dependency image), so the
    measurement attacker path serializes with a plain JSON encoder and then
    proves the exact variant round-trips inside the produced bytes. Production
    encoding, signatures and validation are untouched.
    """
    raw = json.dumps(changed, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )
    quantity = json.loads(raw)["params"]["items"][0]["quantity"]
    if type(quantity) is not type(variant) or quantity != variant:
        raise MissingPrerequisite("malformed numeric variant did not transmit exactly")
    return raw


def _native_attack(holder, intent, body, material, mode):
    """Ten frozen categories via actual material/AS calls, never mock verifier."""
    cls, case = intent.attack_class, intent.case_index
    if cls == 0:
        # Actual stolen token presentation without the cnf key. Bearer honestly
        # requires no proof; signed PoP endpoints receive no fabricated signature.
        return {**material, "proof": None}
    if cls in (1, 7):
        if cls == 1:
            from agent_guard.server.private_files import read_private_file

            parent = read_private_file(
                Path("/owned/run/executor/attack-parent") / holder.task.task_id
            ).decode()
            refusal = _real_as_negative(holder, intent, parent_token=parent, expand=False)
        else:
            refusal = material.get("as_control")
            if not refusal or refusal.get("actual_AS_request") is not True:
                raise MissingPrerequisite("real valid-selector expansion refusal required")
        return {
            **material,
            "token": "INVALID_CHILD_AFTER_ACTUAL_AS_REFUSAL",
            "proof": None,
            "as_refusal": refusal,
        }
    changed = json.loads(canonical_json_bytes(body))
    if cls == 3:
        changed["params"]["items"][0]["quantity"] = 2
        return {
            **material,
            "body": canonical_json_bytes(changed),
        }  # signed original bytes retained
    if cls == 4:
        if mode in ("realSM2Bearer", "staticACL"):
            changed["task_id"] += "-wrong-domain"
            return {**material, "body": canonical_json_bytes(changed)}
        from tongsuopy.crypto import serialization

        from agent_guard.authorization.proof import sign_ag_proof
        from agent_guard.server.private_files import read_private_file

        key = serialization.load_pem_private_key(
            read_private_file(holder.config.role.private_files["signing_key"]),
            password=None,
        )
        proof = sign_ag_proof(
            key,
            kid=holder.config.kid,
            client_id=holder.config.client_id,
            purpose="invoke",
            endpoint=holder.config.gateway_origin + "/v1/operations/query",
            body=body,
            token=holder._token,
            now=int(time.time()),
        )
        return {**material, "proof": proof}
    if cls == 5:
        changed["params"]["request_id"] += "-not-approved"
    elif cls == 6:
        variants = (True, -1, 1.5, 0, 2**53)
        variant = variants[case % len(variants)]
        changed["params"]["items"][0]["quantity"] = variant
        # Contract-invalid numerics cannot pass the strict canonical encoder
        # (client preflight and the server schema layer both reject them), so
        # the genuine malformed literal must be transmitted instead of failing
        # before any wire write. No valid AG-Proof can bind such bytes: the
        # already genuine pre-transform material is retained and both bindings
        # are recorded honestly for the independent reviewer.
        return {
            **material,
            "body": _malformed_quantity_bytes(changed, variant),
            "malformed_quantity_variant": "true" if type(variant) is bool else repr(variant),
            "body_binding": "RAW_MALFORMED_NUMERIC_NONCANONICAL",
            "proof_binding": (
                "GENUINE_PROOF_BINDS_PRETRANSFORM_CANONICAL_BODY"
                if material.get("proof") is not None
                else None
            ),
        }
    elif cls in (8, 9):
        return material  # real committed revoke or independently genuine sibling root
    else:
        raise MissingPrerequisite("unimplemented frozen attack class")
    if mode in ("complete", "realSM2delegation_noAtomic"):
        fresh = holder.raw_request(changed)
        return {**material, **fresh, "issued_unix_ns": time.time_ns()}
    return {**material, "body": canonical_json_bytes(changed)}


def _native_pipe(role):
    from concurrent.futures import ThreadPoolExecutor

    from agent_guard.demo.config import SyntheticLogin

    from .workload import Intention

    fixture, config = _fixture(), _native_config()
    holders, clients, materials = {}, {}, {}
    output_lock = threading.Lock()
    first_barrier = threading.Barrier(SLOTS, timeout=30)
    capture_root = Path("/tmp/measurement-private-wire")
    capture_root.mkdir(mode=0o700, exist_ok=True)

    def handle(message):
        command = message["value"]
        try:
            action = command["action"]
            if role == "operator":
                value = _native_operator(config, command)
            else:
                slot = command.get("slot")
                if action == "new":
                    _, tasks = _wave_tasks(config)
                    task = next(t for t in tasks if t.task_id == command.get("task", slot))
                    holders[slot] = fixture.TaskHolder(config, role=role, task=task)
                    value = True
                elif action == "root":
                    holders[slot].root(login=SyntheticLogin(**command["login"]))
                    value = True
                elif action == "receive":
                    holders[slot].receive(parent=command["parent"])
                    value = True
                elif action == "delegate":
                    value = asdict(holders[slot].delegate(key=command["key"]))
                elif action == "delegation_expansion":
                    intent = Intention(**command["intent"])
                    value = _real_as_negative(
                        holders[slot], intent, parent_token=holders[slot]._token, expand=True
                    )
                elif action == "metadata":
                    value = holders[slot].authorization_metadata()
                elif action == "revoke":
                    value = holders[slot].revoke_task()
                elif action in ("prepare", "send"):
                    intent = Intention(**command["intent"])
                    slot = intent.task + ("-sibling" if intent.leaf.endswith("leaf1") else "")
                    holder = holders[slot]
                    if slot not in clients:
                        from agent_guard.server.private_files import read_private_file

                        from .research_evidence import ResearchEvidence

                        acl = None
                        if intent.mode == "staticACL":
                            acl = fixture.ACLClient(
                                config,
                                role=role,
                                password=read_private_file(
                                    Path("/owned/run") / role / "acl-password"
                                ).decode(),
                            )
                        clients[slot] = RoleTLSInvocation(
                            holder,
                            mode=intent.mode,
                            private_capture=ResearchEvidence(capture_root / slot),
                            acl_client=acl,
                        )
                    client = clients[slot]
                    if action == "prepare":
                        client.order_operation_id = command.get("order_operation_id")
                        material = client.prepare(
                            intent,
                            body_builder=fixture.task_body,
                            attack_transform=lambda i, b, m: _native_attack(
                                holder,
                                i,
                                b,
                                {**m, "as_control": command.get("as_control")},
                                intent.mode,
                            ),
                        )
                        handle_key = str(intent.index) + ":" + intent.namespace
                        materials[handle_key] = material
                        value = {
                            "handle": handle_key,
                            "body_sha256": hashlib.sha256(material["body"]).hexdigest(),
                            "as_refusal": material.get("as_refusal"),
                        }
                    else:
                        material = materials.pop(command["material_handle"])
                        value = client.send(
                            intent,
                            material,
                            lose_response=command["lose_response"],
                            barrier=first_barrier if command["first_barrier"] else None,
                        )
                elif action == "query":
                    mode = _wave_tasks(config)[0]["mode"]
                    holder = holders[slot]
                    if slot not in clients:
                        clients[slot] = RoleTLSInvocation(holder, mode=mode)
                    response = clients[slot].query(command["operation_id"])
                    value = {
                        "http_status": response.status
                        if hasattr(response, "status")
                        else response[0]
                    }
                else:
                    raise ValueError("fixed private holder action required")
            row = {"id": message["id"], "value": _public_fact(value)}
        except Exception as exc:
            import traceback

            print(
                json.dumps(
                    {
                        "native_error": type(exc).__name__,
                        "frames": [
                            {"file": f.filename, "line": f.lineno, "function": f.name}
                            for f in traceback.extract_tb(exc.__traceback__)
                        ],
                    }
                ),
                file=sys.stderr,
                flush=True,
            )
            row = {"id": message["id"], "error": type(exc).__name__}
        with output_lock:
            print(json.dumps(row, default=str), flush=True)

    with ThreadPoolExecutor(max_workers=64) as pool:
        for line in sys.stdin:
            pool.submit(handle, json.loads(line))


def _native_service_inner(role):
    import signal

    import psycopg

    from agent_guard.demo.did_bootstrap import load_approved_snapshot
    from agent_guard.demo.provision import _dsn
    from agent_guard.server.private_files import read_private_file

    fixture, config = _fixture(), _native_config()
    wave, tasks = _wave_tasks(config)
    mode = wave["mode"]
    event = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: event.set())
    if role == "gateway":
        if mode == "complete":
            import uvicorn

            r = config.roles["gateway"]
            app = fixture.build_full_wave_app(
                config, tasks=tasks, approved=load_approved_snapshot(config)
            )
            host = load_strict_json(Path("/control/allocated-plan.json").read_bytes())["roles"][
                "gateway"
            ]["listener_host"]
            uvicorn.run(
                app,
                host=host,
                port=443,
                ssl_certfile=str(r.public_config_file.parent / "tls.pem"),
                ssl_keyfile=str(r.private_files["tls_key"]),
                log_level="warning",
                access_log=False,
            )
        else:
            from .research_service import create_research_tls_server

            service = fixture.build_research(
                config,
                mode=MODE_MAPPING[mode],
                owned_authority_dsn=read_private_file(
                    Path("/owned/run/gateway/research-dsn")
                ).decode(),
                approved=load_approved_snapshot(config),
                evidence_dir="/tmp/research-evidence",
                tasks=tasks,
            )
            if mode == "staticACL":
                from .research_contracts import ACLRegistration, ResearchAuthenticator

                hashes = load_strict_json(
                    read_private_file(Path("/owned/run/gateway/acl-hashes.json"))
                )
                registry = []
                with service.store.transaction(readonly=True) as conn:
                    rows = conn.execute(
                        "SELECT g.*,t.token_jws FROM ag_grants g "
                        "JOIN ag_grant_tokens t USING(grant_id) "
                        "WHERE g.task_id=ANY(%s) ORDER BY g.depth,g.grant_id",
                        (wave["tasks"],),
                    ).fetchall()
                for task in tasks:
                    for name in ("planner", "selector", "executor"):
                        row = next(
                            (
                                r
                                for r in rows
                                if r["task_id"] == task.task_id
                                and r["holder_client_id"] == "agent-" + name
                            ),
                            None,
                        )
                        if row is None:
                            continue  # pre-JIT startup accepts no unauthenticated credential
                        source = service.authenticator.provider.load(
                            row["token_jws"],
                            grant_id=row["grant_id"],
                            now=int(time.time()),
                        )
                        registry.append(
                            ACLRegistration(
                                name,
                                hashes[name],
                                row["tenant_id"],
                                row["task_id"],
                                row["subject"],
                                row["holder_client_id"],
                                row["holder_kid"],
                                row["grant_id"],
                                row["root_grant_id"],
                                source.snapshot,
                                int(row["expires_at"].timestamp()),
                            )
                        )
                a = service.authenticator
                service.authenticator = ResearchAuthenticator(
                    issuer=a.issuer,
                    as_keys=a.keys,
                    identities=a.identities,
                    provider=a.provider,
                    evidence=a.evidence,
                    acl_registry=tuple(registry),
                )
            r = config.roles["gateway"]
            host = load_strict_json(Path("/control/allocated-plan.json").read_bytes())["roles"][
                "gateway"
            ]["listener_host"]
            server = create_research_tls_server(
                service,
                host=host,
                port=443,
                certificate=r.public_config_file.parent / "tls.pem",
                private_key=r.private_files["tls_key"],
            )
            signal.signal(
                signal.SIGTERM,
                lambda *_: threading.Thread(target=server.shutdown).start(),
            )
            server.serve_forever(poll_interval=0.1)
            server.server_close()
    elif role == "worker":
        if mode == "complete":
            worker = fixture.FullTaskWorker(
                config,
                tasks=tasks,
                registries=fixture.task_operation_registries(
                    config, tasks=tasks, directory="/registry"
                ),
            )
            worker.serve(deadline=time.monotonic() + 3600, stop_event=event)
        else:
            worker = fixture.build_research_worker(
                config,
                mode=MODE_MAPPING[mode],
                owned_authority_dsn=read_private_file(
                    Path("/owned/run/worker/research-dsn")
                ).decode(),
                tasks=tasks,
            )
            while not event.is_set():
                with worker.service.store.transaction(readonly=True) as conn:
                    operations = conn.execute(
                        "SELECT operation_id FROM r34.operations WHERE task_id=ANY(%s) "
                        "AND status NOT IN ('SUCCEEDED','FAILED') ORDER BY accepted_at LIMIT 32",
                        (wave["tasks"],),
                    ).fetchall()
                for operation in operations:
                    worker.run(operation["operation_id"])
                event.wait(0.1)
    elif role == "publisher":
        if mode == "complete":
            from agent_guard.audit.journal import describe_pending_tx

            with psycopg.connect(_dsn(config.roles["publisher"], "authority_dsn")) as conn:
                descriptors = {
                    t.task_id: describe_pending_tx(
                        conn,
                        scope_key=(
                            config.scope["gateway_origin"],
                            t.tenant_id,
                            t.task_id,
                        ),
                    )
                    for t in tasks
                }
            credentials = load_strict_json(
                read_private_file(Path("/owned/run/publisher/task-audit.json"))
            )
            publisher = fixture.build_full_publisher(
                config, registrations=descriptors, credential_map=credentials
            )
            publisher.serve(deadline=time.monotonic() + 3600, stop_event=event)
        else:
            event.wait(3600)  # honest actual lifecycle holder; audit capability N/A
    else:
        raise ValueError("fixed normal writer service required")


def _native_export():
    import shutil

    from agent_guard.demo.provision import readonly_export_factory
    from agent_guard.evidence.export import materialize_task_export
    from agent_guard.evidence.task_bundle import load_checkpoint_history
    from agent_guard.evidence.task_verify import load_public_trust

    fixture, config = _fixture(), _native_config()
    _, tasks = _wave_tasks(config)
    result = []
    for task in tasks:
        folder = Path("/owned/run/export") / task.task_id
        trust = load_public_trust(load_strict_json((folder / "public-trust.json").read_bytes()))
        pin = load_strict_json((folder / "external-pin.json").read_bytes())
        with (folder / "checkpoint-history.ndjson").open("rb") as stream:
            history = load_checkpoint_history(stream, external_trust=trust, external_pin=pin)
        parent = Path("/tmp") / ("export-" + task.task_id)
        parent.mkdir(mode=0o700)
        spool = materialize_task_export(
            readonly_export_factory(fixture.scoped_run(config, task), role="export"),
            trust.scope,
            pin,
            parent,
            external_checkpoint_history=history,
        )
        try:
            target = Path("/results") / task.task_id / "task-bundle.ndjson"
            shutil.copyfile(spool.path, target)
            result.append(
                {
                    "task_id": task.task_id,
                    "operation_count": spool.operation_count,
                    "bytes": spool.size,
                    "sha256": spool.digest,
                    "guardian_pid": spool._guardian_pid,
                }
            )
        finally:
            spool.cleanup()
        if list(parent.iterdir()):
            raise ValueError("actual spool guardian cleanup failed")
    print(json.dumps(result))


def native_entry():
    raw = Path("/proc/self/cmdline").read_bytes()
    print(
        json.dumps(
            {
                "native_process": True,
                "pid": os.getpid(),
                "uid": os.getuid(),
                "start_ticks": Path("/proc/self/stat").read_text().split()[21],
                "argv_sha256": hashlib.sha256(raw).hexdigest(),
                "argv_nul_hex": raw.hex(),
            }
        ),
        file=sys.stderr,
        flush=True,
    )
    if sys.argv[1] == "pipe":
        _native_pipe(sys.argv[2])
    elif sys.argv[1] == "service":
        _native_service(sys.argv[2])
    elif sys.argv[1] == "export":
        _native_export()
    else:
        raise ValueError("fixed owned native entry action required")


def canonical_json_bytes(value):
    from agent_guard.contracts.encoding import canonical_json_bytes as encode

    return encode(value)


def load_strict_json(value):
    from agent_guard.contracts.encoding import load_strict_json as decode

    return decode(value)


def _prepare_research_role(owner, mode):
    if mode == "complete":
        return
    owner.init(
        "measurement-research-private-role",
        "import os,json,secrets;from pathlib import Path;"
        "from psycopg.conninfo import conninfo_to_dict,make_conninfo\n"
        "connections=json.loads(Path('/owned/connections.json').read_text());password=secrets.token_urlsafe(32)\n"
        "for role,uid in "
        + repr([(r, owner.settings["uids"][r]) for r in ("gateway", "worker")])
        + ":\n"
        " values=conninfo_to_dict(connections[role]['authority_dsn']);"
        "values.update(user='demo_research',password=password)\n"
        " p=Path('/owned/run')/role/'research-dsn';"
        "p.write_text(make_conninfo(**values));os.chown(p,uid,uid);p.chmod(0o400)\n"
        "p=Path('/owned/pg/authority/research-role.sql');"
        'p.write_text("CREATE ROLE demo_research LOGIN NOSUPERUSER '
        "NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '\"+password+\"';"
        "GRANT CONNECT ON DATABASE ag_authority "
        'TO demo_research;GRANT USAGE ON SCHEMA public TO demo_research;");'
        "os.chown(p,999,999);p.chmod(0o400)\n",
    )
    owner.inspect("pg-authority")
    owner.call(
        [
            "docker",
            "exec",
            owner.ids["pg-authority"],
            "psql",
            "-U",
            "postgres",
            "-d",
            "ag_authority",
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            "/pg/research-role.sql",
        ]
    )
    if mode == "staticACL":
        owner.init(
            "measurement-private-acl",
            "import os,json,secrets;from pathlib import Path;"
            "from agent_guard.authorization.passwords import hash_password\n"
            "passwords={r:secrets.token_urlsafe(32) for r in ('planner','selector','executor')}\n"
            "p=Path('/owned/run/gateway/acl-hashes.json');"
            "p.write_text(json.dumps({r:hash_password(v) "
            "for r,v in passwords.items()}));os.chown(p,"
            + str(owner.settings["uids"]["gateway"])
            + ","
            + str(owner.settings["uids"]["gateway"])
            + ");p.chmod(0o400)\n"
            "for role,uid in "
            + repr([(r, owner.settings["uids"][r]) for r in ("planner", "selector", "executor")])
            + ":\n"
            " p=Path('/owned/run')/role/'acl-password';"
            "p.write_text(passwords[role]);os.chown(p,uid,uid);p.chmod(0o400)\n",
        )


def run_native_owned_repetition(
    *,
    mode,
    seed,
    evidence_directory,
    installation="wheel",
    final_stop_receipt=None,
    pilot=False,
    pilot_group_offset=0,
):
    """Self-contained normal owner entry; pilot never counts toward official rows."""
    import importlib.util
    import signal
    import traceback
    import uuid
    from types import SimpleNamespace

    from .workload import generate_plan

    if mode not in MODES or installation not in ("source", "wheel"):
        raise ValueError("fixed mode/installation required")
    if not pilot and not (
        final_stop_receipt
        and final_stop_receipt.get("all_writers_STOP") is True
        and final_stop_receipt.get("sole_integrator") is True
    ):
        raise MissingPrerequisite("all STOP/sole integrator required before any official resources")
    if type(pilot_group_offset) is not int or pilot_group_offset not in (0, 450):
        raise ValueError("only fixed approved pilot groups0/450 allowed")
    plan = generate_plan(mode, seed)
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "a34_normal_supervisor", root / "deploy/demo/supervisor.py"
    )
    supervisor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(supervisor)
    run = str(uuid.uuid4())
    owner = supervisor.Owner(
        SimpleNamespace(
            run_id=run,
            owner_id="a34-measurement-" + run,
            evidence=str(Path(evidence_directory) / ("pilot-" if pilot else "official-") / run),
            mode=installation,
            capacity_items=1,
        )
    )
    assembly, code = None, 1
    previous_alarm = signal.signal(
        signal.SIGALRM,
        lambda *_: (_ for _ in ()).throw(TimeoutError("finite owned experiment")),
    )
    signal.alarm(3600 if pilot else 14400)
    try:
        owner.setup()
        _prepare_research_role(owner, mode)
        assembly = NativeOwnedAssembly(owner, plan=plan)
        if pilot:
            groups = _task_groups(plan, plan.intentions)[
                pilot_group_offset : pilot_group_offset + SLOTS
            ]
            clients = assembly.prepare_wave(plan, [g[0] for g in groups], excluded_warmup=True)
            spool = PublicSpool(owner.root / "pilot-rows")
            for group in groups:
                for intent in group:
                    spool.append("planned", {**asdict(intent), "pilot_excluded": True})
            rows = run_task_wave(
                groups,
                clients=clients,
                assembly=assembly,
                spool=spool,
                measured=True,
                barrier_first=True,
            )
            completion = assembly.drain_wave(
                deadline_ns=time.monotonic_ns() + DRAIN_SECONDS * 1_000_000_000
            )
            snapshot = assembly.snapshot_wave()
            spool.append("oracle", snapshot)
            result = {
                "status": "REAL_PILOT_NOT_OFFICIAL_NOT_ACCEPTANCE",
                "actual_n": len(rows),
                "first_wave_peak_interval_inflight": overlap_peak(rows),
                "wave_receipt": assembly.wave_receipt(),
                "completion": completion,
                "official_attempts": 0,
                "formal40000": "NOT_RUN",
            }
            if mode == "complete":
                result["exports"] = assembly.export_wave(groups, expiry_or_revoke_required=True)
            (owner.root / "pilot-result.json").write_text(json.dumps(result, indent=2, default=str))
        else:
            result = run_official_mode_repetition(
                plan,
                assembly,
                output_directory=owner.root / "official-rows",
                final_stop_receipt=final_stop_receipt,
            )
        code = 0
        return result
    except BaseException:
        (owner.root / "measurement-failure.txt").write_text(traceback.format_exc())
        raise
    finally:
        stop_receipt, cleanup_error = None, None
        try:
            if assembly is not None and not assembly.closed:
                stop_receipt = assembly.stop()
            elif assembly is None:
                owner.cleanup()
            if stop_receipt is None:
                try:
                    stop_receipt = json.loads((owner.root / "STOP.json").read_text())
                except Exception:
                    stop_receipt = None
        except BaseException as exc:
            cleanup_error = type(exc).__name__
            try:
                stop_receipt = json.loads((owner.root / "STOP.json").read_text())
            except Exception:
                stop_receipt = None
        (owner.root / "runner-outcome.json").write_text(
            json.dumps(
                _runner_outcome_record(
                    business_exit=code,
                    cleanup_error=cleanup_error,
                    stop_receipt=stop_receipt,
                    owner=owner.owner,
                    run=owner.run,
                    pilot=pilot,
                    pid=os.getpid(),
                )
            )
        )
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_alarm)
        if cleanup_error is not None and code == 0:
            # The process must actually exit non-zero; never a pre-written zero.
            raise MissingPrerequisite("owned cleanup failed: " + cleanup_error)


def _bounded_waves(groups):
    wave, slots = [], 0
    for group in groups:
        needed = 2 if group[0].attack_class == 9 else 1
        if slots + needed > SLOTS:
            yield wave
            wave, slots = [], 0
        wave.append(group)
        slots += needed
    if wave:
        yield wave


def _runner_outcome_record(
    *, business_exit, cleanup_error, stop_receipt, owner, run, pilot, pid=None
):
    """Honest in-process owned-run outcome; never claims a native exit code.

    The running manager cannot observe its own OS exit: a real returncode exists
    only in a parent that actually waits on this process. Therefore native_exit
    is UNOBSERVED here and the waiting external supervisor must write the actual
    child returncode (including crash/nonzero). Business outcome, cleanup result
    and role/sampler child waits (recorded by their own real wait calls) stay
    separate and are never converted into a fabricated native exit.
    """
    return {
        "record_source": "IN_PROCESS_FINALLY_NOT_A_PARENT_WAIT",
        "native_exit": None,
        "native_exit_status": "UNOBSERVED_IN_PROCESS_PARENT_WAIT_REQUIRED",
        "parent_wait_record": "REQUIRED_FROM_WAITING_EXTERNAL_SUPERVISOR",
        "runner_outcome": "SUCCESS" if business_exit == 0 and cleanup_error is None else "FAILURE",
        "business_exit": business_exit,
        "cleanup_error": cleanup_error,
        "cleanup_ok": cleanup_error is None,
        "resources_remaining": None
        if stop_receipt is None
        else stop_receipt.get("resources_remaining"),
        "role_native_exits": None if stop_receipt is None else stop_receipt.get("native_roles"),
        "stop_status": None if stop_receipt is None else stop_receipt.get("status"),
        "owner": owner,
        "run": run,
        "pid": pid,
        "pilot": pilot,
    }


def _private_json(value):
    import base64
    import uuid
    from decimal import Decimal

    if isinstance(value, uuid.UUID):
        return {"private_uuid": str(value)}
    if isinstance(value, Decimal):
        return {"private_exact_decimal": str(value)}

    if isinstance(value, (bytes, memoryview)):
        return {"private_raw_base64": base64.b64encode(bytes(value)).decode()}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError("unsupported original value")


def _native_service(role):
    import resource

    before = resource.getrusage(resource.RUSAGE_SELF)
    started = time.monotonic_ns()
    try:
        return _native_service_inner(role)
    finally:
        after = resource.getrusage(resource.RUSAGE_SELF)
        print(
            json.dumps(
                {
                    "kind": "ACTUAL_ROLE_CPU_RSS",
                    "role": role,
                    "pid": os.getpid(),
                    "start_ns": started,
                    "end_ns": time.monotonic_ns(),
                    "user_cpu_seconds": after.ru_utime - before.ru_utime,
                    "system_cpu_seconds": after.ru_stime - before.ru_stime,
                    "peak_RSS_KiB_linux": after.ru_maxrss,
                    "limits": "native process rusage; Docker cgroup samples separately retained",
                }
            ),
            file=sys.stderr,
            flush=True,
        )


def _start_resource_samples(self):
    import subprocess

    identifiers = list(self.owner.ids.values())
    # Only IDs allocated and inspected by this exact normal Owner.
    for role in self.owner.ids:
        self.owner.inspect(role)
    daemon = self.owner.call(
        [
            "docker",
            "info",
            "--format",
            '{"architecture":{{json .Architecture}},"cpus":{{json .NCPU}},'
            '"memory_bytes":{{json .MemTotal}}}',
        ]
    )
    quotas = {
        role: {
            field: self.owner.inspect(role)["HostConfig"].get(field)
            for field in ("Memory", "NanoCpus", "CpuQuota", "CpuPeriod", "CpusetCpus")
        }
        for role in self.owner.ids
    }
    (self.owner.root / "actual-docker-ceiling-quota.json").write_text(
        json.dumps(
            {
                "daemon": json.loads(daemon.stdout),
                "owned_container_quotas": quotas,
                "observed_unix_ns": time.time_ns(),
            },
            indent=2,
        )
    )
    self.resource_process = subprocess.Popen(
        ["docker", "stats", "--no-trunc", "--format", "{{json .}}", *identifiers],
        stdout=subprocess.PIPE,
        stderr=(self.owner.root / "resource-sampler.stderr").open("wb"),
        env=self.owner.env,
    )

    def read():
        import re

        with (
            (self.owner.root / "resource-samples.jsonl").open("a") as output,
            (self.owner.root / "resource-sampler.raw.stdout").open("ab") as raw,
        ):
            for line in self.resource_process.stdout:
                raw.write(line)
                raw.flush()
                cleaned = re.sub(rb"\x1b\[[0-9;]*[A-Za-z]", b"", line).strip()
                if not cleaned:
                    continue
                try:
                    value = json.loads(cleaned)
                except ValueError:
                    output.write(
                        json.dumps(
                            {
                                "kind": "RAW_DOCKER_STATS_DECODE_FAILURE",
                                "raw_sha256": hashlib.sha256(line).hexdigest(),
                            }
                        )
                        + "\n"
                    )
                    output.flush()
                    continue
                output.write(
                    json.dumps({"observed_monotonic_ns": time.monotonic_ns(), "actual": value})
                    + "\n"
                )
                output.flush()

    self.resource_thread = threading.Thread(target=read, daemon=True)
    self.resource_thread.start()


NativeOwnedAssembly._start_resource_samples = _start_resource_samples


def _stop_resource_samples(self, terminate_timeout=30, kill_timeout=30):
    """Bounded real wait for the owned docker-stats sampler; never skip cleanup.

    A TimeoutExpired here must not propagate out of stop() before owner cleanup:
    the sampler is escalated terminate -> kill and the actual wait result is
    recorded, including an honest not-exited outcome.
    """
    import subprocess

    process = self.resource_process
    if process is None:
        return {
            "status": "NOT_STARTED",
            "native_exit": None,
            "pid": None,
            "exited": True,
            "actual_wait": False,
        }
    record = {
        "kind": "REAL_OWNED_DOCKER_STATS",
        "pid": process.pid,
        "terminate_sent": False,
        "kill_sent": False,
        "actual_wait": False,
        "native_exit": None,
        "exited": False,
        "sampler_thread_stopped": None,
    }
    try:
        if process.poll() is None:
            process.terminate()
            record["terminate_sent"] = True
    except Exception as exc:
        record["error"] = type(exc).__name__
    try:
        record["native_exit"] = process.wait(timeout=terminate_timeout)
        record["actual_wait"] = True
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            record["kill_sent"] = True
            record["native_exit"] = process.wait(timeout=kill_timeout)
            record["actual_wait"] = True
        except subprocess.TimeoutExpired:
            record["error"] = "SamplerWaitTimeout"
    except Exception as exc:
        record["error"] = type(exc).__name__
    record["exited"] = process.poll() is not None
    try:
        if process.stdout is not None:
            process.stdout.close()
    except Exception as exc:
        record["stdout_close_error"] = type(exc).__name__
    if self.resource_thread is not None:
        self.resource_thread.join(timeout=5)
        record["sampler_thread_stopped"] = not self.resource_thread.is_alive()
    (self.owner.root / "resource-sampler.native.json").write_text(json.dumps(record))
    return record


NativeOwnedAssembly._stop_resource_samples = _stop_resource_samples


def _refresh_stale_writer_handles(self):
    """Give every writer a live hold launcher before an owned drain.

    ``supervisor.drain()`` starts a finite hold actor only when no child entry
    exists; after a previous drain the stopped container's launcher entry is
    still present but already exited, and reusing it would SIGTERM a stopped
    container. Any writer whose launcher exited gets the container restarted
    and a fresh real hold actor; live as/gateway services of the current wave
    are left untouched.
    """
    for role in ("as", "gateway", "worker", "publisher"):
        current = self.owner.children.get(role)
        if current is None or current["process"].poll() is not None:
            self.owner.call(["docker", "start", self.owner.ids[role]], allow=True)
            self.owner.start_child(role, ["actor", "--stage", "hold", "--role", role])


NativeOwnedAssembly._refresh_stale_writer_handles = _refresh_stale_writer_handles


def _derive_independent_metrics(snapshot, mode, tasks):
    """Approved fixed policy + actual RR original intents/event graph/DS facts."""
    from .statistics import effect_budget_metrics

    grants = snapshot["ag_grants"]
    # These limits come from the approved TaskInputs/root/two narrowing requests,
    # not from a mode's authorization verdict or mutable research counters.
    approved_limits = ((100000, 12), (80000, 10), (70000, 8))
    policies = {
        g["grant_id"]: {
            "amount_limit": approved_limits[g["depth"]][0],
            "call_limit": approved_limits[g["depth"]][1],
        }
        for g in grants
    }
    if any((g["amount_limit"], g["call_limit"]) != approved_limits[g["depth"]] for g in grants):
        raise MissingPrerequisite(
            "actual signed authority differs from preapproved fixed chain policy"
        )
    counter_rows = grants if mode == "complete" else snapshot["r34.counters"]
    node_rows = snapshot["ag_ledger_event_nodes"] if mode == "complete" else snapshot["r34.nodes"]
    by_grant = {r["grant_id"]: r for r in counter_rows}
    # Before any invoke, genuine unused paths may have no research counter only
    # in a failed initialization. That is incomplete, never a fabricated zero.
    if set(policies) - set(by_grant):
        raise MissingPrerequisite("missing independent all-ancestor counters")
    fields = ("amount_reserved", "amount_settled", "calls_reserved", "calls_settled")
    deltas = tuple(name + "_delta" for name in fields)
    facts = {
        g: {
            "final_counters": [by_grant[g][k] for k in fields],
            "events": [
                {"sequence": n["event_id"], "delta": [n[k] for k in deltas]}
                for n in sorted(node_rows, key=lambda r: r["event_id"])
                if n["grant_id"] == g
            ],
        }
        for g in policies
    }
    operations = snapshot["ag_operations"] if mode == "complete" else snapshot["r34.operations"]
    by_operation = {op["operation_id"]: op for op in operations}
    effects, scope_violations = [], []
    for effect in snapshot["independent_downstream"]["ds_operations"]:
        operation = by_operation.get(effect["operation_id"])
        if operation is None:
            raise MissingPrerequisite("downstream effect lacks immutable authority intent")
        permitted = _independent_intent_permitted(operation, grants, by_operation)
        theft = operation["task_id"].startswith("A0-") and mode in ("realSM2Bearer", "staticACL")
        if not permitted:
            scope_violations.append(operation["operation_id"])
        effects.append(
            {
                "operation_id": operation["operation_id"],
                "intent_hash": operation["intent_digest"],
                "permitted_by_policy": permitted and not theft,
            }
        )
    metrics = effect_budget_metrics(policies=policies, facts=facts, effects=effects)
    metrics["scope_effect_violations"] = scope_violations
    metrics["production_counter_nonzero_rows"] = (
        0 if mode == "complete" else sum(any(g[k] != 0 for k in fields) for g in grants)
    )
    metrics["oracle_sources"] = [
        "independently approved fixed policy",
        "RR authority originals/counters/event deltas",
        "separate RR independent downstream operations/effects",
    ]
    metrics["scope"] = [t.task_id for t in tasks]
    metrics["capabilities"] = {
        "proof": "MEASURED" if plan_pop(mode) else "N/A",
        "READY": "MEASURED" if mode == "complete" else "N/A",
        "independent_anchor": "MEASURED" if mode == "complete" else "N/A",
    }
    return metrics


def _independent_intent_permitted(operation, grants, operations):
    """Small independent fixed dataset oracle, not the service policy verifier."""
    task, tool = operation["task_id"], operation["tool_id"]
    params = load_strict_json(bytes(operation["canonical_params"]))
    ancestors = {g["grant_id"]: g for g in grants}
    grant = ancestors.get(operation["grant_id"])
    if grant is None or grant["task_id"] != task:
        return False
    while grant is not None:
        if (
            grant["expires_at"] <= operation["accepted_at"]
            or grant["not_before"] > operation["accepted_at"]
        ):
            return False
        if grant["revoked_at"] is not None and grant["revoked_at"] <= operation["accepted_at"]:
            return False
        grant = ancestors.get(grant["parent_grant_id"]) if grant["parent_grant_id"] else None
    if tool == "procurement.request.read":
        return params == {"request_id": "req." + task} and operation["amount_fen"] == 0
    if tool == "procurement.document.read":
        return (
            params == {"request_id": "req." + task, "document_id": "doc." + task}
            and operation["amount_fen"] == 0
        )
    if tool == "procurement.order.create":
        return (
            params
            == {
                "request_id": "req." + task,
                "quote_id": "quote." + task,
                "quote_version": "1",
                "items": [{"sku": "sku-001", "quantity": 1}],
                "delivery_id": "delivery." + task,
            }
            and type(params["items"][0]["quantity"]) is int
            and operation["amount_fen"] == 70000
        )
    if tool == "notification.template.send":
        order = operations.get(params.get("operation_id"))
        return (
            set(params) == {"operation_id", "template_id", "recipient_id"}
            and order is not None
            and order["task_id"] == task
            and order["tool_id"] == "procurement.order.create"
            and order["status"] == "SUCCEEDED"
            and order["accepted_at"] < operation["accepted_at"]
            and params["template_id"] == "order-created"
            and params["recipient_id"] == "user-demo"
            and operation["amount_fen"] == 0
        )
    return False


def _real_as_negative(holder, intent, *, parent_token, expand):
    """Real issuer HTTP with genuine caller key and deliberately invalid request.

    The SDK's normal narrowing precheck would reject these attack inputs before
    any wire send, so this research-only caller uses its existing private _token
    transport and leaves the actual issuer verifier fully active.
    """
    from agent_guard.authorization.claims import GATEWAY_AUDIENCE
    from agent_guard.authorization.exchange import ACCESS_TOKEN_TYPE, TOKEN_EXCHANGE_GRANT
    from agent_guard.contracts.encoding import b64url_encode
    from agent_guard.demo.config import DemoConfigError

    constraints = dict(holder.task.policy()["constraints"], max_quantity=2 if expand else 1)
    form = {
        "grant_type": TOKEN_EXCHANGE_GRANT,
        "subject_token": parent_token,
        "subject_token_type": ACCESS_TOKEN_TYPE,
        "requested_token_type": ACCESS_TOKEN_TYPE,
        "audience": GATEWAY_AUDIENCE,
        "scope": " ".join(_fixture().TOOLS),
        "ag_delegate_client_id": "agent-executor" if expand else "agent-selector",
        "ag_amount_limit_fen": "70000" if expand else "80000",
        "ag_call_limit": "8" if expand else "10",
        "ag_ttl_seconds": "180" if expand else "240",
        "ag_delegation_remaining": "0" if expand else "1",
        "ag_constraints": canonical_json_bytes(constraints).decode(),
        "ag_delegation_key": b64url_encode(hashlib.sha256(intent.business_key.encode()).digest()),
    }
    original = holder.client._request
    observations = []

    def observed(url, **kwargs):
        start = time.monotonic_ns()
        result = original(url, **kwargs)
        observations.append(
            {
                "http_status": result[0],
                "send_ns": start,
                "end_ns": time.monotonic_ns(),
                "response_sha256": hashlib.sha256(result[2]).hexdigest(),
                "request_body_sha256": hashlib.sha256(kwargs["body"]).hexdigest(),
            }
        )
        return result

    holder.client._request = observed
    try:
        try:
            holder.client._token(form, purpose="delegate", token=parent_token)
        except DemoConfigError:
            if len(observations) != 1 or observations[0]["http_status"] not in (
                400,
                401,
                403,
                409,
                422,
            ):
                raise MissingPrerequisite("actual expected AS refusal not observed") from None
        else:
            raise MissingPrerequisite("actual AS unexpectedly admitted invalid delegation")
    finally:
        holder.client._request = original
    return {
        "actual_AS_request": True,
        "kind": "VALID_PARENT_PERMISSION_EXPANSION" if expand else "WRONG_HOLDER_PARENT_EXCHANGE",
        "caller_client_id": holder.config.client_id,
        "parent_token_sha256": hashlib.sha256(parent_token.encode()).hexdigest(),
        **observations[0],
    }
