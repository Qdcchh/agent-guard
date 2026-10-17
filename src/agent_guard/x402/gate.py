"""Payment-gated downstream port: the x402 flow in front of order creation.

Drop-in :class:`~agent_guard.contracts.execution.DownstreamPort` wrapper:

* ``query`` withholds the order until the payment is chain-confirmed settled;
* ``execute`` performs the real HTTP 402 flow (challenge -> persisted
  authorization -> ``PAYMENT-SIGNATURE``), confirms the settlement on the real
  local chain and only then returns the durable downstream outcome.

Every rejection is proven before any budget moves: a transport failure, a
refused HTTP status or a consumed-but-unconfirmed nonce keeps the operation
UNKNOWN with the asset budget still reserved, and never triggers a new
authorization or a new order. The asset budget is released only when the
configured chain proves the signed authorization can never settle any more:
its signed ``validBefore`` deadline has passed in the configured chain's own
time **and** the token's own ``authorizationState(payer, nonce)`` is
explicitly ``False`` at that head. Expiry alone proves no *future*
settlement; only an unused nonce also rules out a past settlement whose
lookup was temporarily unavailable. The persisted payload (same EIP-3009
nonce) is the only thing a retry sends.
"""

from __future__ import annotations

import hashlib
import json

from agent_guard.contracts.execution import DownstreamOutcome
from agent_guard.cosign.effect import check_effect_approval
from agent_guard.execution import store as exec_store
from agent_guard.threshold.contracts import ThresholdApprovalPolicy
from agent_guard.x402 import intent as intent_module
from agent_guard.x402 import state, wire
from agent_guard.x402.chain import ChainReader
from agent_guard.x402.client import X402HttpClient
from agent_guard.x402.config import X402Deployment
from agent_guard.x402.contracts import PaymentStatus, X402Error
from agent_guard.x402.signer import X402Payer, create_nonce


class PaymentGatedDownstream:
    """The only component that may turn an accepted operation into a payment."""

    def __init__(
        self,
        *,
        deployment: X402Deployment,
        downstream,
        downstream_secret: str,
        client: X402HttpClient,
        payer: X402Payer,
        reader: ChainReader,
        connector=None,
        cosign_policy=None,
    ):
        if type(deployment) is not X402Deployment:
            raise X402Error("trusted deployment required", code="CONFIG_INVALID")
        if type(client) is not X402HttpClient:
            raise X402Error("real HTTP client required", code="CONFIG_INVALID")
        if type(payer) is not X402Payer:
            raise X402Error("controlled payer required", code="CONFIG_INVALID")
        if type(reader) is not ChainReader:
            raise X402Error("real chain reader required", code="CONFIG_INVALID")
        if not downstream_secret:
            raise X402Error("downstream secret required", code="CONFIG_INVALID")
        if cosign_policy is not None and (
            type(cosign_policy) is not ThresholdApprovalPolicy or cosign_policy.scheme != "sm2-2p"
        ):
            raise X402Error("COSM2 policy required", code="CONFIG_INVALID")
        self._cosign_policy = cosign_policy
        self._deployment = deployment
        self._downstream = downstream
        self._secret = downstream_secret
        self._client = client
        self._payer = payer
        self._reader = reader
        self._connector = connector

    # -------------------------------------------------------------- port

    def query(self, *, service_secret: str, operation_id: str) -> DownstreamOutcome | None:
        record = state.load_payment(
            self._deployment.gateway_dsn, operation_id, connector=self._connector
        )
        if record.status is not PaymentStatus.SETTLED:
            return None
        return self._downstream.query(service_secret=service_secret, operation_id=operation_id)

    def execute(
        self,
        *,
        service_secret: str,
        operation_id: str,
        tool_id,
        canonical_params: bytes,
        quote,
        expected_amount_fen: int,
        approval_envelope=None,
        idempotency_key=None,
        tenant_id=None,
        task_id=None,
    ) -> DownstreamOutcome:
        del tool_id  # the API shape is fixed; facts are re-read from the operation
        record = state.load_payment(
            self._deployment.gateway_dsn, operation_id, connector=self._connector
        )
        intent = record.intent
        operation = self._read_operation(operation_id)
        self._assert_operation(
            operation=operation, intent=intent, canonical_params=canonical_params
        )
        if self._cosign_policy is not None:
            import psycopg

            connect = self._connector if self._connector is not None else psycopg.connect
            with connect(self._deployment.gateway_dsn, connect_timeout=5) as conn:
                row = conn.execute(
                    "SELECT envelope_bytes FROM ag_threshold_approvals WHERE operation_id=%s",
                    (operation_id,),
                ).fetchone()
            if (
                row is None
                or bytes(row[0]) != approval_envelope
                or (tenant_id, task_id, idempotency_key)
                != (operation.tenant_id, operation.task_id, operation.idempotency_key)
            ):
                raise X402Error(
                    "original COSM2 approval required", code="PAYMENT_APPROVAL_MISMATCH"
                )
            check_effect_approval(
                self._cosign_policy,
                envelope=approval_envelope,
                tenant_id=tenant_id,
                task_id=task_id,
                idempotency_key=idempotency_key,
                canonical_params=canonical_params,
                quote=quote,
                expected_amount_fen=expected_amount_fen,
            )

        if record.status is PaymentStatus.FAILED:
            raise X402Error("payment was refused for this operation", code="PAYMENT_REFUSED")
        if record.status is PaymentStatus.SETTLED:
            outcome = self._downstream.query(
                service_secret=service_secret, operation_id=operation_id
            )
            if outcome is None:
                raise X402Error(
                    "payment settled but the resource has no effect",
                    code="PAYMENT_EFFECT_MISSING",
                )
            return outcome

        profile = self._deployment.profile
        if record.status is PaymentStatus.UNPAID:
            challenge = self._client.payment_required(
                self._client.order_create(operation_id=operation_id, payment_header=None)
            )
            intent_module.check_challenge(profile=profile, intent=intent, challenge=challenge)
            signed = self._payer.create_payload(
                profile=profile, intent=intent, nonce=create_nonce()
            )
            raw = signed["document"]
            record = state.authorize(
                self._deployment.gateway_dsn,
                operation_id=operation_id,
                nonce=signed["nonce"],
                authorization_json=json.dumps(
                    signed["authorization"], ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8"),
                payload_json=raw,
                payload_sha256=signed["payload_sha256"],
                connector=self._connector,
            )

        if not record.has_authorization:
            self._fail_release(operation_id, failure_code="PAYMENT_NOT_AUTHORIZED")
            raise X402Error("no persisted authorization to retry", code="PAYMENT_NOT_AUTHORIZED")

        material = state.load_authorization_material(
            self._deployment.gateway_dsn, operation_id, connector=self._connector
        )
        if material is None:  # pragma: no cover - defensive
            raise X402Error("authorization material disappeared", code="PAYMENT_STATE_CONFLICT")
        _stored_authorization, raw, _sha = material
        parsed = wire.parse_payment_payload(wire.encode_header(raw))
        intent_module.check_signed_payload(intent=intent, payload=parsed)
        if hashlib.sha256(raw).hexdigest() != record.payload_sha256:
            raise X402Error(
                "persisted payment material is inconsistent", code="PAYMENT_STATE_CONFLICT"
            )
        authorization = parsed["payload"]["authorization"]
        payer = authorization["from"].lower()

        state.mark_submitting(
            self._deployment.gateway_dsn, operation_id=operation_id, connector=self._connector
        )
        try:
            response = self._client.order_create(
                operation_id=operation_id, payment_header=wire.encode_header(raw)
            )
        except X402Error:
            # the request may have reached the server and the response was
            # lost; only the chain can decide, and until it does the budget
            # stays reserved.
            if self._reconcile(
                operation_id=operation_id, intent=intent, payer=payer, authorization=authorization
            ):
                outcome = self._downstream.query(
                    service_secret=service_secret, operation_id=operation_id
                )
                if outcome is not None:
                    return outcome
            raise X402Error("payment outcome is unknown", code="PAYMENT_UNKNOWN") from None

        if response.status != 200:
            return self._handle_refusal(
                operation_id=operation_id,
                intent=intent,
                payer=payer,
                authorization=authorization,
                status=response.status,
            )

        settlement = self._client.settlement(response)
        tx_hash = settlement.get("transaction") or ""
        if not settlement.get("success") or not tx_hash:
            raise X402Error("settlement response is not confirmable", code="PAYMENT_UNKNOWN")
        confirmation = self._reader.confirm(
            payer=payer,
            pay_to=intent.pay_to,
            amount=intent.asset_amount,
            nonce=authorization["nonce"],
            candidate_tx=tx_hash,
        )
        if not confirmation.settled:
            state.mark_unknown(
                self._deployment.gateway_dsn,
                operation_id=operation_id,
                failure_code="SETTLEMENT_UNCONFIRMED",
                connector=self._connector,
            )
            raise X402Error("settlement is not confirmed on chain", code="PAYMENT_UNKNOWN")
        state.mark_settled(
            self._deployment.gateway_dsn,
            operation_id=operation_id,
            tx_hash=tx_hash,
            connector=self._connector,
        )
        outcome = self._downstream.query(service_secret=service_secret, operation_id=operation_id)
        if outcome is None:
            raise X402Error(
                "payment settled but the resource has no effect", code="PAYMENT_EFFECT_MISSING"
            )
        return outcome

    # ----------------------------------------------------------- internals

    def _read_operation(self, operation_id: str):
        import psycopg

        connect = self._connector if self._connector is not None else psycopg.connect
        with connect(self._deployment.gateway_dsn, autocommit=True, connect_timeout=5) as conn:
            return exec_store.fetch_operation(conn, operation_id)

    def _assert_operation(self, *, operation, intent, canonical_params: bytes) -> None:
        if operation is None:
            raise X402Error("unknown operation", code="OPERATION_MISMATCH")
        if (
            operation.tool_id != intent.tool_id
            or operation.tenant_id != intent.tenant_id
            or operation.task_id != intent.task_id
            or operation.idempotency_key != intent.idempotency_key
            or operation.quote_id != intent.quote_id
            or operation.quote_version != intent.quote_version
            or bytes(operation.canonical_params) != canonical_params
        ):
            raise X402Error(
                "operation facts differ from the payment intent", code="OPERATION_MISMATCH"
            )

    def _handle_refusal(
        self, *, operation_id: str, intent, payer: str, authorization: dict, status: int
    ) -> DownstreamOutcome:
        confirmation = self._reader.confirm(
            payer=payer,
            pay_to=intent.pay_to,
            amount=intent.asset_amount,
            nonce=authorization["nonce"],
        )
        if confirmation.settled:
            state.mark_settled(
                self._deployment.gateway_dsn,
                operation_id=operation_id,
                tx_hash=confirmation.tx_hash or "",
                connector=self._connector,
            )
            outcome = self._downstream.query(service_secret=self._secret, operation_id=operation_id)
            if outcome is None:
                raise X402Error(
                    "payment settled but the resource has no effect",
                    code="PAYMENT_EFFECT_MISSING",
                )
            return outcome
        if self._authorization_provably_dead(payer=payer, authorization=authorization):
            self._fail_release(operation_id, failure_code=f"PAYMENT_REFUSED_{status}")
            raise X402Error("payment was refused", code="PAYMENT_REFUSED")
        state.mark_unknown(
            self._deployment.gateway_dsn,
            operation_id=operation_id,
            failure_code=f"PAYMENT_HTTP_{status}",
            connector=self._connector,
        )
        raise X402Error("payment outcome is unknown", code="PAYMENT_UNKNOWN")

    def _authorization_provably_dead(self, *, payer: str, authorization: dict) -> bool:
        """Only the configured chain may prove the reservation can never settle.

        Releasing is a two-fact proof read in this order, never an expiry-only
        guess:

        * the endpoint currently serves the configured chain id and its head
          timestamp is at or past the signed ``validBefore`` deadline — on the
          fixed local chain block timestamps are monotonic, so no future block
          can settle this payload any more;
        * the token's own ``authorizationState(payer, nonce)`` is explicitly
          ``False`` — the nonce was never consumed by any block up to that
          head, and consumption is permanent.

        Expiry alone proves only that no *future* payment can happen: a
        settlement that succeeded before the deadline would still be owed, so
        a consumed nonce (``True``), an unreadable state (``None``), a missing
        or non-integer deadline, a mismatched chain and an unreadable head all
        keep the asset reserved.
        """
        valid_before = authorization.get("validBefore")
        if type(valid_before) is int:
            deadline = valid_before
        elif type(valid_before) is str and valid_before.isdigit():
            deadline = int(valid_before)
        else:
            return False
        if not self._reader.chain_matches():
            return False
        head = self._reader.latest_block_timestamp()
        if head is None or head < deadline:
            return False
        return self._reader.authorization_state(payer=payer, nonce=authorization["nonce"]) is False

    def _fail_release(self, operation_id: str, *, failure_code: str) -> None:
        state.mark_failed(
            self._deployment.gateway_dsn,
            operation_id=operation_id,
            failure_code=failure_code,
            connector=self._connector,
        )

    def _reconcile(self, *, operation_id: str, intent, payer: str, authorization: dict) -> bool:
        """After a lost response only the chain may confirm; never re-sign."""
        confirmation = self._reader.confirm(
            payer=payer,
            pay_to=intent.pay_to,
            amount=intent.asset_amount,
            nonce=authorization["nonce"],
        )
        if confirmation.settled:
            state.mark_settled(
                self._deployment.gateway_dsn,
                operation_id=operation_id,
                tx_hash=confirmation.tx_hash or "",
                connector=self._connector,
            )
            return True
        state.mark_unknown(
            self._deployment.gateway_dsn,
            operation_id=operation_id,
            failure_code="RESPONSE_LOST",
            connector=self._connector,
        )
        return False
