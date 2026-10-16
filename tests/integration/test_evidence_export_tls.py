"""Real HTTPS with exact SAN, independent AGExport role, and download cleanup."""

import hashlib
import io
import os
import ssl
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from agent_guard.evidence.task_bundle import iter_frames
from agent_guard.gateway.evidence_auth import load_export_credentials
from agent_guard.gateway.evidence_endpoint import (
    EvidenceExportEndpoint,
    ExportTaskInputs,
)
from agent_guard.gateway.evidence_http_app import EvidenceHttpApp
from tests.fixtures.a32_export import export_full_state as full_state
from tests.fixtures.a32_export import history_inputs, readonly_export_factory
from tests.integration.test_gateway_tls import HOST, LocalTLS, fresh_port
from tests.integration.test_verified_execution import signed_env

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("round", range(10))
@pytest.mark.parametrize(
    "case",
    [
        "allowed",
        "cross_tenant_same_task",
        "wrongrole",
        "badTLS",
        "framing",
        "disconnect",
        "slot_saturation",
    ],
)
def test_export_tls_registered_audit_role_scope(ledger, dsn, downstream_dsn, tmp_path, round, case):
    env = signed_env(dsn, downstream_dsn)
    env.adapter.accept(env.bundle())
    scope, pin, history = history_inputs(dsn, tmp_path)
    parent = tmp_path / "spool"
    parent.mkdir(mode=0o700)
    secret = "synthetic_export_credential_" + "0" * 32
    credentials = load_export_credentials(
        [
            {
                "credential_id": "audit-export",
                "credential_sha256": hashlib.sha256(secret.encode()).hexdigest(),
                "tenant_id": scope.tenant_id
                if case != "cross_tenant_same_task"
                else "unrelated-tenant",
                "task_ids": [scope.task_id],
            }
        ]
    )
    tls = Path(os.environ["A32_EXPORT_TLS_DIR"])
    port = fresh_port()
    before = full_state(dsn, downstream_dsn)
    with readonly_export_factory(dsn) as factory:
        endpoint = EvidenceExportEndpoint(
            factory,
            credentials=credentials,
            task_inputs=(
                ExportTaskInputs(
                    scope,
                    pin["mode"],
                    pin["checkpoint_jws"],
                    pin["observed_at"],
                    history,
                ),
            ),
            spool_parent=parent,
        )
        app = (
            EvidenceHttpApp(endpoint, max_workers=1, timeout_seconds=1)
            if case == "slot_saturation"
            else EvidenceHttpApp(endpoint)
        )
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                ssl_certfile=str(tls / "tls.pem"),
                ssl_keyfile=str(tls / "tls.key"),
                log_level="critical",
                access_log=False,
            )
        )
        thread = threading.Thread(target=server.run)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started
            context = ssl.create_default_context(cafile=str(tls / "ca.pem"))
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
            if case == "slot_saturation":
                _real_tls_slot_saturation(factory, dsn, parent, scope, port, context, secret)
            elif case == "badTLS":
                with pytest.raises(ssl.SSLCertVerificationError):
                    connection = LocalTLS(
                        HOST, port, context=ssl.create_default_context(), timeout=5
                    )
                    connection.connect()
                with pytest.raises(ssl.SSLCertVerificationError):
                    connection = LocalTLS(
                        "wrong.agent-guard.test", port, context=context, timeout=5
                    )
                    connection.connect()
            else:
                connection = LocalTLS(HOST, port, context=context, timeout=5)
                authorization = "AGExport audit-export:" + secret
                if case == "wrongrole":
                    authorization = "AGPoP business-token"
                body = '{"task_id":"' + scope.task_id + '"}'
                if case == "framing":
                    body = (
                        '{"task_id":"' + scope.task_id + '","tenant_id":"' + scope.tenant_id + '"}'
                    )
                connection.request(
                    "POST",
                    "/v1/evidence/export",
                    body=body,
                    headers={
                        "Authorization": authorization,
                        "Content-Type": "application/json",
                    },
                )
                response = connection.getresponse()
                if case in {"allowed", "disconnect"}:
                    assert response.status == 200
                    if case == "disconnect":
                        response.read(1)
                    else:
                        raw = response.read()
                        assert len(raw) == int(response.getheader("Content-Length"))
                        list(iter_frames(io.BytesIO(raw)))
                else:
                    assert response.status in {400, 401}
                connection.close()
                deadline = time.monotonic() + 10
                while list(parent.iterdir()) and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert list(parent.iterdir()) == []
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()
    assert full_state(dsn, downstream_dsn) == before


def _real_tls_slot_saturation(factory, dsn, parent, scope, port, context, secret):
    """Occupy the actual export worker on a real PG table lock over verified TLS."""
    from concurrent.futures import ThreadPoolExecutor

    import psycopg

    from tests.fixtures.a32_export import record_export_native_evidence

    def request():
        connection = LocalTLS(HOST, port, context=context, timeout=5)
        start = time.monotonic()
        try:
            connection.request(
                "POST",
                "/v1/evidence/export",
                body='{"task_id":"' + scope.task_id + '"}',
                headers={
                    "Authorization": "AGExport audit-export:" + secret,
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            return (
                response.status,
                dict(response.getheaders()),
                response.read(),
                time.monotonic() - start,
            )
        finally:
            connection.close()

    with factory() as observed:
        readonly_role = observed.info.user
    blocker = psycopg.connect(dsn)
    try:
        blocker.execute("LOCK TABLE ag_audit_streams IN ACCESS EXCLUSIVE MODE")
        with ThreadPoolExecutor(max_workers=1) as callers:
            first = callers.submit(request)
            deadline = time.monotonic() + 5
            waiting = None
            while waiting is None and time.monotonic() < deadline:
                blocker.execute("SELECT pg_stat_clear_snapshot()")
                waiting = blocker.execute(
                    "SELECT pid,usename,wait_event_type,wait_event,query FROM pg_stat_activity "
                    "WHERE usename=%s AND wait_event_type='Lock' "
                    "AND query LIKE '%%ag_audit_streams%%'",
                    (readonly_role,),
                ).fetchone()
                if waiting is None:
                    time.sleep(0.01)
            assert waiting is not None
            second = request()
            primary = first.result(timeout=5)
            assert primary[0] == second[0] == 503
            for response in (primary, second):
                assert response[1]["content-type"] == "application/json"
                assert response[2] == b'{"error":"EXPORT_UNAVAILABLE"}'
                assert response[3] < 5
                assert not any("evidence" in key.lower() for key in response[1])
            record_export_native_evidence(
                "real-tls-slot-saturation",
                {
                    "readonly_backend": list(waiting),
                    "first_status": primary[0],
                    "second_status": second[0],
                    "first_seconds": primary[3],
                    "second_seconds": second[3],
                },
            )
        blocker.commit()
    finally:
        blocker.close()
    deadline = time.monotonic() + 10
    while list(parent.iterdir()) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert list(parent.iterdir()) == []
    resumed = request()
    assert resumed[0] == 200
    list(iter_frames(io.BytesIO(resumed[2])))
    deadline = time.monotonic() + 10
    while list(parent.iterdir()) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert list(parent.iterdir()) == []
    record_export_native_evidence(
        "real-tls-slot-restored",
        {
            "status": resumed[0],
            "seconds": resumed[3],
            "wire_bytes": len(resumed[2]),
            "spool_remaining": 0,
        },
    )
