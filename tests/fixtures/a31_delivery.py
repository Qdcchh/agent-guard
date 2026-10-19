"""Delivery-owned real SM2/TLS transport, independent of unfinished service."""

from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import stat
import subprocess
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
        ca_file = "/private/ca.pem"
        if os.environ.get("PR9_A31_TLS_RECEIPT") is not None:
            verified_root = _current_tls_dir()
            if Path(tls_dir) != verified_root:
                raise ValueError("delivery TLS root differs from verified context")
            ca_file = str(verified_root / "ca.pem")
        self.ca_file = ca_file
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
                    try:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(raw)))
                        self.end_headers()
                        self.wfile.write(raw)
                    except ssl.SSLEOFError:
                        # The SIGKILL recovery probe may close TLS after remote commit.
                        pass
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
            ca_file=ca_file,
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


def _regular_private_path(path, *, mode):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("absolute TLS context path required")
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise ValueError("TLS context symlink forbidden")
    info = path.stat()
    if stat.S_IMODE(info.st_mode) != mode or info.st_uid != os.getuid():
        raise ValueError("TLS context ownership or mode differs")
    return path


def _current_tls_dir():
    receipt_path = _regular_private_path(os.environ["PR9_A31_TLS_RECEIPT"], mode=0o600)
    if not receipt_path.is_file():
        raise ValueError("regular TLS receipt required")
    receipt = load_strict_json(receipt_path.read_bytes())
    fields = {
        "container_id",
        "owner",
        "sslmode",
        "verified_tcp_tls",
        "ca",
        "ephemeral",
        "tls_root",
        "ca_sha256",
        "server_certificate_sha256",
        "delivery_server_certificate_sha256",
        "audit_host",
    }
    if not isinstance(receipt, dict) or set(receipt) != fields:
        raise ValueError("unknown TLS receipt fields")
    owner = os.environ.get("PR9_CI_OWNER")
    if (
        not isinstance(owner, str)
        or re.fullmatch(r"[A-Za-z0-9_-]{1,100}", owner) is None
        or receipt["owner"] != owner
        or not isinstance(receipt["container_id"], str)
        or re.fullmatch(r"[0-9a-f]{64}", receipt["container_id"]) is None
        or receipt["sslmode"] != "verify-full"
        or receipt["verified_tcp_tls"] is not True
        or receipt["ephemeral"] is not True
    ):
        raise ValueError("TLS receipt owner or identity differs")
    root = _regular_private_path(receipt["tls_root"], mode=0o700)
    if not root.is_dir() or receipt_path != root / "receipt.json":
        raise ValueError("TLS receipt must belong to its bound root")
    ca = root / "ca.pem"
    if receipt["ca"] != str(ca):
        raise ValueError("TLS CA must belong to its bound root")
    for name in ("ca.pem", "server.pem"):
        path = _regular_private_path(root / name, mode=0o600)
        if not path.is_file():
            raise ValueError("regular TLS material required")
    for name, field in (("ca.pem", "ca_sha256"), ("server.pem", "server_certificate_sha256")):
        checksum = receipt[field]
        if (
            not isinstance(checksum, str)
            or re.fullmatch(r"[0-9a-f]{64}", checksum) is None
            or hashlib.sha256((root / name).read_bytes()).hexdigest() != checksum
        ):
            raise ValueError("TLS material digest differs")
    delivery_root = _regular_private_path(root / "delivery", mode=0o700)
    if not delivery_root.is_dir():
        raise ValueError("bound delivery TLS directory required")
    for name in ("ca.pem", "server.pem", "server.key"):
        path = _regular_private_path(delivery_root / name, mode=0o600)
        if not path.is_file():
            raise ValueError("regular delivery TLS material required")
    if (delivery_root / "ca.pem").read_bytes() != ca.read_bytes():
        raise ValueError("delivery CA differs from the bound audit CA")
    delivery_checksum = receipt["delivery_server_certificate_sha256"]
    if (
        not isinstance(delivery_checksum, str)
        or re.fullmatch(r"[0-9a-f]{64}", delivery_checksum) is None
        or hashlib.sha256((delivery_root / "server.pem").read_bytes()).hexdigest()
        != delivery_checksum
    ):
        raise ValueError("delivery certificate digest differs")
    observed = subprocess.run(
        ["docker", "inspect", receipt["container_id"]],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if observed.returncode:
        raise ValueError("cannot inspect owned TLS service")
    info = load_strict_json(observed.stdout)
    if (
        not isinstance(info, list)
        or len(info) != 1
        or info[0].get("Id") != receipt["container_id"]
        or info[0].get("Config", {}).get("Labels", {}).get("agent-guard.pr9-owner") != owner
        or info[0].get("State", {}).get("Running") is not True
    ):
        raise ValueError("actual TLS service ownership differs")
    from psycopg.conninfo import conninfo_to_dict

    dsn = os.environ["AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL"]
    database = conninfo_to_dict(dsn)
    if (
        database.get("sslmode") != "verify-full"
        or database.get("sslrootcert") != str(ca)
        or receipt["audit_host"] not in {"localhost", "127.0.0.1", "pg-audit.agent-guard.test"}
        or database.get("host") != receipt["audit_host"]
    ):
        raise ValueError("verified audit database TLS required")
    with psycopg.connect(dsn, connect_timeout=5) as connection:
        ssl_row = connection.execute(
            "SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()"
        ).fetchone()
        if ssl_row != (True,):
            raise ValueError("audit connection did not negotiate TLS")
    return delivery_root


def tls_dir():
    if os.environ.get("PR9_A31_TLS_RECEIPT") is not None:
        return _current_tls_dir()
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
