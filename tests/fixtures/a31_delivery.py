"""Delivery-owned real SM2/TLS transport, independent of unfinished service."""

from __future__ import annotations

import json
import os
import ssl
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psycopg

from agent_guard.audit.client import AuditClient
from agent_guard.audit.contracts import (
    CheckpointClaims,
    CheckpointTrust,
    decode_append_batch,
    decode_checkpoint_claims,
)
from agent_guard.contracts.encoding import (
    EncodingError,
    b64url_decode,
    b64url_encode,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.crypto.sm import (
    generate_sm2_private_key,
    serialize_sm2_public_key,
    sign_compact_jws,
    sm3_b64url,
)
from tests.fixtures.a31_common import STAMP
from tests.fixtures.isolation import acquire_namespace, release_namespace


class SignedTransport:
    def __init__(self, scope, tls_dir):
        self.scope = scope
        self.key = generate_sm2_private_key()
        self.trust = (
            CheckpointTrust(
                "delivery-fixture",
                "AUDIT_SIGNER",
                serialize_sm2_public_key(self.key.public_key()),
                1,
                None,
            ),
        )
        self.namespace = acquire_namespace(os.environ["AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL"])
        self.dsn = self.namespace.dsn
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                "CREATE TABLE transport_batches(batch_id text PRIMARY KEY,body bytea "
                "NOT NULL,jws text NOT NULL,sequence bigint NOT NULL,digest text NOT NULL)"
            )
        self.mutex = threading.Lock()
        self.requests = []
        self.failure = None
        self.after_commit = None
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                try:
                    expected = "writer" if self.path.endswith("/append") else "reader"
                    if (
                        self.headers.get("Authorization")
                        != "Bearer " + expected + ":DELIVERY_FIXTURE_SECRET_0123456789"
                    ):
                        self.send_error(403)
                        return
                    size = int(self.headers["Content-Length"])
                    if not 0 < size <= 65536:
                        self.send_error(413)
                        return
                    body = self.rfile.read(size)
                    fixture.requests.append((self.path, body))
                    if fixture.failure == "unavailable":
                        self.send_error(503)
                        return
                    if fixture.failure == "redirect":
                        self.send_response(302)
                        self.send_header("Location", "https://localhost:1/")
                        self.end_headers()
                        return
                    if self.path == "/v1/audit/append":
                        batch = decode_append_batch(body)
                        with fixture.mutex, psycopg.connect(fixture.dsn) as conn:
                            row = conn.execute(
                                "SELECT body,jws FROM transport_batches WHERE batch_id=%s",
                                (batch.batch_id,),
                            ).fetchone()
                            if row:
                                assert bytes(row[0]) == body
                                jws = row[1]
                            else:
                                prior = conn.execute(
                                    "SELECT jws,sequence,digest FROM "
                                    "transport_batches ORDER BY sequence DESC LIMIT 1"
                                ).fetchone()
                                if batch.start_sequence != (prior[1] + 1 if prior else 1):
                                    raw = canonical_json_bytes({"error": "RECONCILE_REQUIRED"})
                                    self.send_response(409)
                                    self.send_header("Content-Length", str(len(raw)))
                                    self.end_headers()
                                    self.wfile.write(raw)
                                    return
                                claims = CheckpointClaims(
                                    "GM-MVP-1",
                                    "AG-CHECKPOINT-1",
                                    batch.batch_id,
                                    fixture.scope.stream_id,
                                    fixture.scope.gateway_id,
                                    fixture.scope.tenant_id,
                                    fixture.scope.task_id,
                                    1,
                                    batch.end_sequence,
                                    batch.end_digest,
                                    sm3_b64url(prior[0].encode("ascii")) if prior else None,
                                    STAMP,
                                    "delivery-fixture",
                                )
                                jws = sign_compact_jws(
                                    fixture.key,
                                    asdict(claims),
                                    key_id="delivery-fixture",
                                    token_type="ag-checkpoint+jwt",
                                )
                                conn.execute(
                                    "INSERT INTO transport_batches VALUES (%s,%s,%s,%s,%s)",
                                    (
                                        batch.batch_id,
                                        body,
                                        jws,
                                        batch.end_sequence,
                                        batch.end_digest,
                                    ),
                                )
                        if fixture.after_commit:
                            fixture.after_commit()
                        if fixture.failure == "bad-signature":
                            jws = jws[:-4] + "AAAA"
                        output = {"checkpoint_jws": jws}
                    elif self.path == "/v1/audit/latest":
                        assert load_strict_json(body) == {"stream_id": fixture.scope.stream_id}
                        with psycopg.connect(fixture.dsn) as conn:
                            row = conn.execute(
                                "SELECT jws FROM transport_batches ORDER BY sequence DESC LIMIT 1"
                            ).fetchone()
                        output = {"checkpoint_jws": row[0]} if row else {"error": "NO_CHECKPOINT"}
                    elif self.path in ("/v1/audit/history", "/v1/audit/records"):
                        request = load_strict_json(body)
                        assert set(request) == {
                            "stream_id",
                            "observed_checkpoint_id",
                            "after_sequence",
                        }
                        assert request["stream_id"] == fixture.scope.stream_id
                        with psycopg.connect(fixture.dsn) as conn:
                            rows = conn.execute(
                                "SELECT body,jws,sequence FROM transport_batches ORDER BY sequence"
                            ).fetchall()
                        pin = next(
                            (
                                r
                                for r in rows
                                if decode_checkpoint_claims(
                                    b64url_decode(r[1].split(".")[1])
                                ).checkpoint_id
                                == request["observed_checkpoint_id"]
                            ),
                            None,
                        )
                        if pin is None:
                            self.send_error(404)
                            return
                        boundary = pin[2]
                        after = request["after_sequence"]
                        output = {
                            "stream_id": fixture.scope.stream_id,
                            "observed_checkpoint_id": request["observed_checkpoint_id"],
                            "observed_sequence": boundary,
                            "next_after_sequence": None,
                        }
                        if self.path.endswith("/history"):
                            values = [r for r in rows if after < r[2] <= boundary][:64]
                            output["checkpoints"] = [r[1] for r in values]
                            if values[-1][2] < boundary:
                                output["next_after_sequence"] = values[-1][2]
                        else:
                            entries = [
                                raw
                                for r in rows
                                if r[2] <= boundary
                                for raw in decode_append_batch(bytes(r[0])).entries
                            ]
                            output["entries"] = []
                            for raw in entries[after : after + 64]:
                                trial = {
                                    **output,
                                    "entries": output["entries"] + [b64url_encode(raw)],
                                    "next_after_sequence": boundary,
                                }
                                try:
                                    canonical_json_bytes(trial)
                                except EncodingError:
                                    break
                                output["entries"].append(b64url_encode(raw))
                            end = after + len(output["entries"])
                            if end < boundary:
                                output["next_after_sequence"] = end
                        if fixture.failure == "changed-pin":
                            output["observed_checkpoint_id"] = "other"
                        elif fixture.failure == "missing-page":
                            output["next_after_sequence"] = None
                        elif fixture.failure == "bad-record" and "entries" in output:
                            output["entries"][0] = b64url_encode(b"{}")
                        elif fixture.failure == "bad-history" and "checkpoints" in output:
                            output["checkpoints"][0] = output["checkpoints"][0][:-4] + "AAAA"
                    else:
                        self.send_error(404)
                        return
                    raw = canonical_json_bytes(output)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as exc:
                    fixture.handler_error = exc
                    self.send_error(500)

        self.handler_error = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(tls_dir / "server.pem"), str(tls_dir / "server.key"))
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = "https://localhost:" + str(self.server.server_port)
        self.client = AuditClient(
            self.origin,
            ca_file="/private/ca.pem",
            writer_credential="writer:DELIVERY_FIXTURE_SECRET_0123456789",
            reader_credential="reader:DELIVERY_FIXTURE_SECRET_0123456789",
            timeout=2,
        )

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        assert not self.thread.is_alive()
        release_namespace(self.namespace)
        assert self.handler_error is None, repr(self.handler_error)


def tls_dir():
    private = Path("/private")
    info = load_strict_json((private / "owner.json").read_bytes())
    role = info["role"]
    allowed = {
        "delivery",
        "integrator-source",
        "integrator-wheel",
        "reviewer-source",
        "reviewer-wheel",
    }
    assert role in allowed and info["owner_uuid"] == "78baf870-8f66-4961-9e24-8f4554e65c65"
    assert info["role_owner_token"] == "78baf8708f66-" + role
    manifest = json.loads(Path("/e/resources.json").read_text())
    owner = manifest["owner"]
    assert not manifest.get("cleaned") and manifest["role"] == role
    assert owner["owner_uuid"] == info["owner_uuid"]
    assert owner["role_owner_token"] == info["role_owner_token"]
    assert manifest["labels"] == {
        "ag.owner_uuid": info["owner_uuid"],
        "ag.role_owner_token": info["role_owner_token"],
        "com.docker.compose.project": "ag-a31-78baf8708f66-" + role,
    }
    expected = "ag-a31-78baf8708f66-" + role + "-pg"
    resource = next(row for row in manifest["resources"] if row["name"] == expected)
    assert len(resource["id"]) == 64 and resource["kind"] == "container"
    assert owner["GW_DS_PG_name"] == expected
    assert {
        "type": "bind",
        "source": owner["private_dir"] + "/" + expected,
        "destination": "/tls",
    } in resource["mounts"]
    runtime = json.loads((private / "runtime.json").read_text())
    assert runtime["role"] == role and runtime["owner_uuid"] == info["owner_uuid"]
    from psycopg.conninfo import conninfo_to_dict

    database = conninfo_to_dict(runtime["dsn"]["gateway"])
    assert database["host"] == expected and database["sslmode"] == "verify-full"
    assert database["sslrootcert"] == "/private/ca.pem"
    return private / expected


def atomic_marker(path, value):
    """Publish the same JSON bytes after a complete private write, for native observers."""
    path = Path(path)
    temporary = path.with_name(path.name + "." + str(os.getpid()) + ".tmp")
    with temporary.open("x") as output:
        output.write(json.dumps(value))
    os.replace(temporary, path)
