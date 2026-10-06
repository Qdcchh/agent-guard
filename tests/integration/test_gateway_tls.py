"""Independent TLS CLI process, real four tools, SIGKILL and restart reads."""

import http.client
import json
import os
import signal
import socket
import ssl
import subprocess
import sys
import time

import psycopg
import pytest

from agent_guard.authorization.proof import sign_ag_proof
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.contracts.ledger import INVOKE_ENDPOINT, QUERY_ENDPOINT
from tests.fixtures.execution import DOWNSTREAM_SECRET, expire_lease
from tests.fixtures.gateway import config_document, state
from tests.integration.test_verified_execution import TOOLS, signed_env

pytestmark = pytest.mark.integration
HOST = "gateway.agent-guard.test"


class LocalTLS(http.client.HTTPSConnection):
    def connect(self):
        raw = socket.create_connection(("127.0.0.1", self.port), timeout=self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def certificates(directory):
    commands = [
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(directory / "ca.key"),
            "-out",
            str(directory / "ca.pem"),
            "-days",
            "1",
            "-subj",
            "/CN=AgentGuardSyntheticCA",
        ],
        [
            "openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(directory / "tls.key"),
            "-out",
            str(directory / "tls.csr"),
            "-subj",
            "/CN=" + HOST,
        ],
    ]
    (directory / "extensions").write_text(
        "subjectAltName=DNS:" + HOST + "\nbasicConstraints=CA:FALSE\n"
        "keyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n"
    )
    commands.append(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(directory / "tls.csr"),
            "-CA",
            str(directory / "ca.pem"),
            "-CAkey",
            str(directory / "ca.key"),
            "-CAcreateserial",
            "-out",
            str(directory / "tls.pem"),
            "-days",
            "1",
            "-extfile",
            str(directory / "extensions"),
        ]
    )
    for command in commands:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
        assert completed.returncode == 0
    for name in ["ca.key", "tls.key"]:
        (directory / name).chmod(0o600)


def fresh_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_gateway(directory, dsn, downstream_dsn, port):
    env = dict(os.environ)
    env.pop("AGENT_GUARD_DATABASE_URL", None)
    env.update(AG_GATEWAY_DATABASE_URL=dsn, AG_GATEWAY_DOWNSTREAM_DATABASE_URL=downstream_dsn)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agent_guard.gateway",
            "run",
            "--config",
            str(directory / "config.json"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--ssl-certfile",
            str(directory / "tls.pem"),
            "--ssl-keyfile",
            str(directory / "tls.key"),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    context = ssl.create_default_context(cafile=str(directory / "ca.pem"))
    until = time.monotonic() + 10
    while time.monotonic() < until:
        if process.poll() is not None:
            out, err = process.communicate()
            pytest.fail("gateway startup failed (private output suppressed)")
        try:
            connection = LocalTLS(HOST, port, context=context, timeout=0.2)
            connection.request("GET", "/not-public")
            assert connection.getresponse().status == 404
            connection.close()
            return process, context
        except OSError:
            time.sleep(0.02)
    process.kill()
    process.communicate(timeout=5)
    pytest.fail("gateway readiness timed out")


def stop_gateway(process):
    if process.poll() is None:
        process.terminate()
    out, err = process.communicate(timeout=30)
    # uvicorn restores and re-raises the received SIGTERM after graceful
    # shutdown. Both exits mean the requested process has actually stopped.
    assert process.returncode in (0, -signal.SIGTERM)
    print(f"GATEWAY_EXIT pid={process.pid} returncode={process.returncode}")
    return out + err


def signed_request(
    env, port, context, body, *, query=False, holder="executor", proof_override=None
):
    endpoint = QUERY_ENDPOINT if query else INVOKE_ENDPOINT
    registration = env.registrations[("tenant-001", "agent-" + holder)]
    proof = proof_override or sign_ag_proof(
        env.keys[holder],
        kid=registration.kid,
        client_id="agent-" + holder,
        purpose="result-read" if query else "invoke",
        endpoint=endpoint,
        token=env.token,
        body=body,
        now=int(time.time()),
    )
    connection = LocalTLS(HOST, port, context=context, timeout=25)
    connection.request(
        "POST",
        "/v1/operations/query" if query else "/v1/invocations",
        body=canonical_json_bytes(body),
        headers={
            "Content-Type": "application/json",
            "Authorization": "AGPoP " + env.token,
            "AG-Proof": proof,
            "X-Request-ID": "untrusted-sensitive-marker",
        },
    )
    response = connection.getresponse()
    result = (response.status, json.loads(response.read()), dict(response.getheaders()))
    connection.close()
    return result


def worker(env, dsn, downstream_dsn, operation_id, *, pause=None):
    child = dict(os.environ)
    child.pop("AGENT_GUARD_DATABASE_URL", None)
    child.update(
        AG_WORKER_GATEWAY_DSN=dsn,
        AG_WORKER_DOWNSTREAM_DSN=downstream_dsn,
        AG_WORKER_SERVICE_SECRET=DOWNSTREAM_SECRET,
        AG_WORKER_OPERATION_ID=operation_id,
        AG_WORKER_SERVED_REQUESTS="req-001",
        AG_WORKER_APPROVED_SUPPLIERS="supplier-001",
        AG_WORKER_APPROVED_RECIPIENTS="user-demo-001",
    )
    if pause:
        child.update(AG_WORKER_SYNC_FILE=str(pause[0]), AG_WORKER_RELEASE_FILE=str(pause[1]))
    return subprocess.Popen(
        [sys.executable, "-m", "agent_guard.execution.worker"],
        env=child,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_real_tls_four_tools_killed_worker_and_gateway_restart(
    ledger, dsn, downstream_dsn, tmp_path
):
    env = signed_env(dsn, downstream_dsn)
    certificates(tmp_path)
    (tmp_path / "config.json").write_bytes(canonical_json_bytes(config_document(env)))
    (tmp_path / "secrets.json").write_bytes(
        canonical_json_bytes(
            {"note": "synthetic test-only", "downstream_secret": DOWNSTREAM_SECRET}
        )
    )
    for name in ["config.json", "secrets.json"]:
        (tmp_path / name).chmod(0o600)
    port = fresh_port()
    gateway, context = start_gateway(tmp_path, dsn, downstream_dsn, port)
    original_pid = gateway.pid
    outputs = []
    operations = []
    active_worker = None
    try:
        for hostname, ctx in [
            (HOST, ssl.create_default_context()),
            ("wrong.agent-guard.test", context),
        ]:
            with pytest.raises(ssl.SSLCertVerificationError):
                connection = LocalTLS(hostname, port, context=ctx, timeout=2)
                connection.connect()
        for index, tool in enumerate(TOOLS):
            params = [
                {"request_id": "req-001"},
                {"request_id": "req-001", "document_id": "doc-001"},
                {
                    "request_id": "req-001",
                    "quote_id": "quote-001",
                    "quote_version": "1",
                    "items": [{"sku": "sku-001", "quantity": 1}],
                    "delivery_id": "office-001",
                },
                {
                    "template_id": "order-created",
                    "recipient_id": "user-demo-001",
                    "operation_id": operations[0] if operations else "missing",
                },
            ][index]
            body = {
                "profile": "GM-MVP-1",
                "task_id": "task-001",
                "tool_id": tool,
                "tool_version": "1",
                "idempotency_key": "tls-tool-" + str(index),
                "params": params,
            }
            before_reject = state(dsn)
            status, rejected, _ = signed_request(env, port, context, body, holder="planner")
            assert status == 401 and rejected["error"]["code"] == "INVALID_SIGNATURE"
            assert state(dsn) == before_reject
            proof = sign_ag_proof(
                env.keys["executor"],
                kid=env.registrations[("tenant-001", "agent-executor")].kid,
                client_id="agent-executor",
                purpose="invoke",
                endpoint=INVOKE_ENDPOINT,
                token=env.token,
                body=body,
                now=int(time.time()),
            )
            status, accepted, _ = signed_request(env, port, context, body, proof_override=proof)
            assert status == 202 and accepted["status"] == "RESERVED"
            before_reject = state(dsn)
            status, rejected, _ = signed_request(env, port, context, body, proof_override=proof)
            assert status == 409 and rejected["error"]["code"] == "REPLAY"
            tampered = dict(body, idempotency_key="tampered")
            status, rejected, _ = signed_request(env, port, context, tampered, proof_override=proof)
            assert status == 401 and rejected["error"]["code"] == "INVALID_SIGNATURE"
            assert state(dsn) == before_reject
            operation_id = accepted["operation_id"]
            operations.append(operation_id)
            with psycopg.connect(downstream_dsn) as conn:
                assert conn.execute(
                    "SELECT count(*) FROM ds_operations WHERE operation_id=%s", (operation_id,)
                ).fetchone() == (0,)
            if index == 2:
                sync = tmp_path / "worker-sync"
                release = tmp_path / "worker-release"
                active_worker = worker(
                    env, dsn, downstream_dsn, operation_id, pause=(sync, release)
                )
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not sync.exists():
                    assert active_worker.poll() is None
                    time.sleep(0.01)
                assert sync.exists() and json.loads(sync.read_text())["pid"] == active_worker.pid
                killed_pid = active_worker.pid
                active_worker.kill()
                out, err = active_worker.communicate(timeout=5)
                assert active_worker.returncode == -9
                outputs.append(out + err)
                with psycopg.connect(dsn) as conn:
                    assert conn.execute(
                        "SELECT status FROM ag_operations WHERE operation_id=%s", (operation_id,)
                    ).fetchone() == ("EXECUTING",)
                    assert (
                        conn.execute(
                            "SELECT amount_reserved,calls_reserved FROM ag_grants ORDER BY depth"
                        ).fetchall()
                        == [(70000, 1)] * 3
                    )
                expire_lease(dsn, operation_id)
                active_worker = worker(env, dsn, downstream_dsn, operation_id)
                assert active_worker.pid != killed_pid
            else:
                active_worker = worker(env, dsn, downstream_dsn, operation_id)
            out, err = active_worker.communicate(timeout=30)
            outputs.append(out + err)
            assert active_worker.returncode == 0 and json.loads(out)["status"] == "SUCCEEDED"
            before = state(dsn, proofs=False)
            query = {"profile": "GM-MVP-1", "task_id": "task-001", "operation_id": operation_id}
            status, answer, headers = signed_request(env, port, context, query, query=True)
            assert status == 200 and answer["status"] == "SUCCEEDED"
            assert (
                answer["result"]
                and answer["receipt_status"] == "PENDING"
                and answer["receipt_jws"] is None
            )
            assert headers["cache-control"] == "no-store"
            assert state(dsn, proofs=False) == before
            status, retry, _ = signed_request(env, port, context, body)
            assert (
                status == 202
                and retry["status"] == "SUCCEEDED"
                and retry["operation_id"] == operation_id
            )
        outputs.append(stop_gateway(gateway))
        gateway, context = start_gateway(tmp_path, dsn, downstream_dsn, port)
        assert gateway.pid != original_pid
        assert (
            signed_request(
                env,
                port,
                context,
                {"profile": "GM-MVP-1", "task_id": "task-001", "operation_id": operations[2]},
                query=True,
            )[1]["result"]["kind"]
            == "order"
        )
        with psycopg.connect(dsn) as conn:
            assert (
                conn.execute(
                    "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled FROM "
                    "ag_grants ORDER BY depth"
                ).fetchall()
                == [(0, 70000, 0, 4)] * 3
            )
            assert conn.execute("SELECT count(*) FROM ag_operations").fetchone() == (4,)
            assert conn.execute(
                "SELECT phase,count(*) FROM ag_ledger_events GROUP BY phase ORDER BY phase"
            ).fetchall() == [("RESERVE", 4), ("SETTLE", 4)]
            assert (
                conn.execute("SELECT receipt_status,receipt_jws FROM ag_receipt_outbox").fetchall()
                == [("PENDING", None)] * 4
            )
        with psycopg.connect(downstream_dsn) as conn:
            assert conn.execute("SELECT count(*) FROM ds_orders").fetchone() == (1,)
            assert conn.execute("SELECT count(*) FROM ds_notifications").fetchone() == (1,)
        print(
            "PROCESS_WITNESS gateway_restart=true killed_worker=true persistent_four_tools=true "
            "CA_hostname_default_verified=true"
        )
    finally:
        if active_worker and active_worker.poll() is None:
            active_worker.kill()
            active_worker.communicate(timeout=5)
        outputs.append(stop_gateway(gateway))
    assert all(
        marker not in "".join(outputs)
        for marker in [
            env.token,
            DOWNSTREAM_SECRET,
            dsn,
            downstream_dsn,
            "untrusted-sensitive-marker",
            "PRIVATE KEY",
            "Traceback",
        ]
    )
