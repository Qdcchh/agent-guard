"""Real HTTP x402 resource server for the fixed local test-chain profile.

Flow is exactly ``verify -> resource -> settle``:

* no ``PAYMENT-SIGNATURE`` -> ``402`` with a ``PAYMENT-REQUIRED`` challenge
  built only from the immutable intent persisted at acceptance;
* a payment signature is strictly parsed, compared against the persisted
  authorization and verified by the official SDK facilitator against the real
  local chain;
* only then is the downstream order executed (durable, idempotent by
  ``operation_id``), and finally the EIP-3009 authorization is settled on the
  local EVM. A settlement response alone is never trusted: the server reads
  the real receipt/Transfer event before returning success.

The server is read-only on the gateway database; payment state transitions
belong to the worker. It never writes files, secrets or user keys.
"""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from agent_guard.execution import store as exec_store
from agent_guard.tools import parse_tool_id, snapshot_from_bytes
from agent_guard.x402 import intent as intent_module
from agent_guard.x402 import state, wire
from agent_guard.x402.chain import ChainReader
from agent_guard.x402.config import X402Deployment
from agent_guard.x402.contracts import PaymentStatus, X402Error
from agent_guard.x402.facilitator import LocalFacilitator

MAX_REQUEST_BODY = 1024


def _json_body(document: dict) -> bytes:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _requirements(intent, max_timeout_seconds: int) -> dict:
    return wire.parse_requirements(
        {
            "scheme": "exact",
            "network": intent.network,
            "asset": intent.asset,
            "amount": intent.asset_amount,
            "payTo": intent.pay_to,
            "maxTimeoutSeconds": max_timeout_seconds,
            "extra": {
                "assetTransferMethod": "eip3009",
                "name": intent.asset_name,
                "version": intent.asset_version,
            },
        }
    )


class X402ResourceServer:
    """Loopback resource server; one instance per local demo run."""

    def __init__(
        self,
        *,
        deployment: X402Deployment,
        facilitator: LocalFacilitator,
        reader: ChainReader,
        downstream,
        downstream_secret: str,
        connector=None,
    ):
        if type(deployment) is not X402Deployment:
            raise X402Error("trusted deployment required", code="CONFIG_INVALID")
        if type(facilitator) is not LocalFacilitator:
            raise X402Error("real facilitator required", code="CONFIG_INVALID")
        if type(reader) is not ChainReader:
            raise X402Error("real chain reader required", code="CONFIG_INVALID")
        if not downstream_secret:
            raise X402Error("downstream secret required", code="CONFIG_INVALID")
        self._deployment = deployment
        self._facilitator = facilitator
        self._reader = reader
        self._downstream = downstream
        self._secret = downstream_secret
        self._connector = connector
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ----------------------------------------------------------- lifecycle

    def __enter__(self) -> "X402ResourceServer":
        parsed = urlsplit(self._deployment.profile.resource_url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1", "localhost"):
            raise X402Error("resource server requires loopback HTTP", code="CONFIG_NOT_LOOPBACK")
        handler = _handler_for(self)
        server = ThreadingHTTPServer((parsed.hostname, parsed.port), handler)
        server.daemon_threads = True
        self._httpd = server
        self._thread = threading.Thread(
            target=server.serve_forever, name="x402-resource", daemon=True
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    # ------------------------------------------------------------- handler

    def _connect(self):
        import psycopg

        connect = self._connector if self._connector is not None else psycopg.connect
        return connect(self._deployment.gateway_dsn, autocommit=True, connect_timeout=5)

    def _operation_facts(self, operation_id: str):
        with self._connect() as conn:
            return exec_store.fetch_operation(conn, operation_id)

    def _payment(self, operation_id: str) -> state.PaymentRecord:
        return state.load_payment(
            self._deployment.gateway_dsn, operation_id, connector=self._connector
        )

    def handle_post(
        self, operation_id: str | None, payment_header: bytes | None
    ) -> tuple[int, dict, bytes]:
        if operation_id is None or not operation_id.isascii() or not 1 <= len(operation_id) <= 128:
            return 400, {}, _json_body({"error": "INVALID_OPERATION_ID"})
        try:
            record = self._payment(operation_id)
        except X402Error:
            return 404, {}, _json_body({"error": "UNKNOWN_OPERATION"})
        intent = record.intent
        if intent.resource_url != self._deployment.profile.resource_url:
            return 409, {}, _json_body({"error": "RESOURCE_MISMATCH"})
        # Defense in depth: the worker already released this operation, but a
        # raw replay of an old payload must never reopen a refused payment.
        if record.status is PaymentStatus.FAILED:
            return 409, {}, _json_body({"error": "PAYMENT_FAILED"})
        requirements = _requirements(intent, self._deployment.profile.max_timeout_seconds)
        if not record.has_authorization and record.status is PaymentStatus.UNPAID:
            if payment_header is None:
                return self._challenge(intent, requirements, error=None)
            return 409, {}, _json_body({"error": "PAYMENT_NOT_PERSISTED"})
        if payment_header is None:
            return self._challenge(intent, requirements, error=None)

        try:
            raw = wire.decode_header(payment_header, label="PAYMENT-SIGNATURE")
            parsed = wire.parse_payment_payload(wire.encode_header(raw))
            intent_module.check_signed_payload(intent=intent, payload=parsed)
            intent_module.check_requirements_echo(intent=intent, accepted=parsed["accepted"])
            authorization = parsed["payload"]["authorization"]
            material = state.load_authorization_material(
                self._deployment.gateway_dsn, operation_id, connector=self._connector
            )
            if material is None:
                return 409, {}, _json_body({"error": "PAYMENT_NOT_PERSISTED"})
            stored_authorization, stored_payload, stored_sha = material
            if hashlib.sha256(raw).hexdigest() != stored_sha:
                return 409, {}, _json_body({"error": "PAYMENT_MATERIAL_MISMATCH"})
            if parsed["payload"]["authorization"] != json.loads(stored_authorization):
                return 409, {}, _json_body({"error": "PAYMENT_MATERIAL_MISMATCH"})
            if raw != stored_payload:
                return 409, {}, _json_body({"error": "PAYMENT_MATERIAL_MISMATCH"})
        except X402Error as exc:
            return self._challenge(intent, requirements, error=exc.code)

        payer = authorization["from"].lower()
        nonce = authorization["nonce"]

        # A replay after a lost success response is settled on chain already;
        # return the durable effect instead of verifying/transferring again.
        confirmation = self._reader.confirm(
            payer=payer,
            pay_to=intent.pay_to,
            amount=intent.asset_amount,
            nonce=nonce,
        )
        if confirmation.authorization_used and not confirmation.transfer_matched:
            return 409, {}, _json_body({"error": "PAYMENT_CONFLICT"})
        if confirmation.settled:
            return self._settled_response(operation_id, confirmation.tx_hash, payer, intent)

        verified = self._facilitator.verify(payload=parsed, requirements=requirements)
        if not verified.get("is_valid") or (verified.get("payer") or "").lower() != payer:
            if verified.get("invalid_reason") == "FACILITATOR_UNAVAILABLE":
                return 503, {}, _json_body({"error": "VERIFIER_UNAVAILABLE"})
            return self._challenge(intent, requirements, error="PAYMENT_VERIFICATION_FAILED")

        facts = self._operation_facts(operation_id)
        if facts is None or facts.tool_id != intent.tool_id:
            return 409, {}, _json_body({"error": "OPERATION_MISMATCH"})
        try:
            quote = snapshot_from_bytes(facts.quote_snapshot)
            outcome = self._downstream.execute(
                service_secret=self._secret,
                operation_id=operation_id,
                tool_id=parse_tool_id(facts.tool_id),
                canonical_params=bytes(facts.canonical_params),
                quote=quote,
                expected_amount_fen=facts.amount_fen,
            )
        except X402Error:
            raise
        except Exception:  # noqa: BLE001 - downstream failure is not a payment result
            return 503, {}, _json_body({"error": "RESOURCE_UNAVAILABLE"})
        if outcome.operation_id != operation_id:
            return 503, {}, _json_body({"error": "RESOURCE_UNAVAILABLE"})

        settled = self._facilitator.settle(payload=parsed, requirements=requirements)
        candidate = settled.get("transaction") or None
        confirmation = self._reader.confirm(
            payer=payer,
            pay_to=intent.pay_to,
            amount=intent.asset_amount,
            nonce=nonce,
            candidate_tx=candidate,
        )
        if confirmation.settled:
            return self._settled_response(operation_id, confirmation.tx_hash, payer, intent)
        if settled.get("error_reason") == "SETTLEMENT_PENDING" or not confirmation.nonce_consumed:
            return 502, {}, _json_body({"error": "PAYMENT_UNKNOWN"})
        return 502, {}, _json_body({"error": "PAYMENT_FAILED"})

    def _challenge(
        self, intent, requirements: dict, *, error: str | None
    ) -> tuple[int, dict, bytes]:
        document = wire.payment_required_wire(
            resource_url=intent.resource_url, requirements=requirements, error=error
        )
        header = wire.encode_header(document).decode("ascii")
        return 402, {"PAYMENT-REQUIRED": header}, _json_body({"error": error or "PAYMENT_REQUIRED"})

    def _settled_response(
        self, operation_id: str, tx_hash: str | None, payer: str, intent
    ) -> tuple[int, dict, bytes]:
        if tx_hash is None:
            return 502, {}, _json_body({"error": "PAYMENT_UNCONFIRMED"})
        outcome = self._downstream.query(service_secret=self._secret, operation_id=operation_id)
        if outcome is None:
            return 409, {}, _json_body({"error": "PAYMENT_SETTLED_NO_EFFECT"})
        document = wire.settlement_wire(
            success=True, transaction=tx_hash, network=intent.network, payer=payer
        )
        header = wire.encode_header(document).decode("ascii")
        return (
            200,
            {"PAYMENT-RESPONSE": header},
            _json_body(
                {
                    "operation_id": operation_id,
                    "payment": "SETTLED",
                    "effect_ref": outcome.effect_ref,
                    "already_existed": outcome.already_existed,
                }
            ),
        )


def _handler_for(server: X402ResourceServer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "x402-resource"
        sys_version = ""

        def log_message(self, format, *args):  # noqa: A003 - silence access logs
            return

        def _send(self, status: int, headers: dict, body: bytes) -> None:
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.send_header("connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802 - stdlib handler API
            self._send(405, {}, _json_body({"error": "METHOD_NOT_ALLOWED"}))

        def do_POST(self):  # noqa: N802 - stdlib handler API
            if self.path != "/v1/x402/resource/order-create":
                self._send(404, {}, _json_body({"error": "NOT_FOUND"}))
                return
            header_values = self.headers.get_all("payment-signature") or []
            if len(header_values) > 1:
                self._send(400, {}, _json_body({"error": "DUPLICATE_PAYMENT_HEADER"}))
                return
            try:
                length = int(self.headers.get("content-length", "0"))
            except ValueError:
                self._send(400, {}, _json_body({"error": "INVALID_BODY"}))
                return
            if length < 0 or length > MAX_REQUEST_BODY:
                self._send(413, {}, _json_body({"error": "BODY_TOO_LARGE"}))
                return
            if length:
                self.rfile.read(length)
            operation_id = self.headers.get("ag-operation-id")
            payment_header = None
            if header_values:
                try:
                    payment_header = header_values[0].encode("ascii")
                except UnicodeEncodeError:
                    self._send(400, {}, _json_body({"error": "INVALID_PAYMENT_HEADER"}))
                    return
            try:
                status, headers, body = server.handle_post(operation_id, payment_header)
            except Exception:  # noqa: BLE001 - never leak internals over HTTP
                status, headers, body = 500, {}, _json_body({"error": "INTERNAL_ERROR"})
            self._send(status, headers, body)

    return Handler
