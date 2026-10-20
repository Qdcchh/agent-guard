"""Execution-domain coordination over actual verified request and trusted prices."""

import time
from time import perf_counter

from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.cosign.authz_domain import CosignRefused, action_params
from agent_guard.cosign.encoding import point_to_hex
from agent_guard.cosign.protocol import ExecParty
from agent_guard.cosign.shares import load_share
from agent_guard.threshold.codec import (
    build_envelope,
    cosm2_message,
    encode_header,
    parse_action_v3,
)

PROFILE = "AG-COSM2-APPROVAL-1"


class ExecutionDomainSigner:
    def __init__(
        self, *, share_dir, token_provider, catalog, clock=None, payment_digest_provider=None
    ):
        share = load_share(share_dir, role="exec")
        self._party = ExecParty(share.share, share.public_point)
        self._token_provider = token_provider
        self._catalog = catalog
        self._clock = clock or (lambda: int(time.time()))
        self._payment_digest_provider = payment_digest_provider or (lambda bundle: "0" * 64)
        self.round1_count = 0
        self.last_timing_ms = {}

    def approve(self, bundle, action, authz_client):
        try:
            action = parse_action_v3(action)
            inv = bundle.invocation
            expected = {
                "tenant_id": inv.tenant_id,
                "task_id": inv.task_id,
                "root_grant_id": inv.root_id,
                "grant_id": inv.grant_id,
                "holder_client_id": inv.holder_client_id,
                "holder_kid": inv.holder_kid,
                "tool_id": inv.tool_id,
                "tool_version": inv.tool_version,
                "idempotency_key": inv.idempotency_key,
                "payment_digest": self._payment_digest_provider(bundle),
                "path_grant_ids": list(bundle.permissions.chain_grant_ids),
            }
            if any(action[key] != value for key, value in expected.items()):
                raise ValueError("request mismatch")
            if canonical_json_bytes(action_params(action)) != inv.canonical_params:
                raise ValueError("params mismatch")
            quote = self._catalog.build_order_snapshot(
                tenant_id=inv.tenant_id,
                task_id=inv.task_id,
                **{k: v for k, v in action_params(action).items() if k != "items"},
                items=tuple((item["sku"], item["quantity"]) for item in action["items"]),
            )
            if quote.total_fen != action["amount_fen"]:
                raise ValueError("amount mismatch")
            token = self._token_provider(bundle)
        except Exception:
            self._party._k1 = None
            raise CosignRefused("EXEC_MISMATCH") from None
        try:
            started = perf_counter()
            q1 = self._party.sign_round1()
            first = perf_counter()
            self.round1_count += 1
            partial = authz_client.respond(
                action=action, leaf_access_token=token, q1_hex=point_to_hex(q1), now=self._clock()
            )
            if type(partial) is not dict or set(partial) != {"r", "s2", "s3"}:
                raise ValueError("invalid partial response")
            second = perf_counter()
            r, s = self._party.sign_round3(cosm2_message(action), **partial)
            third = perf_counter()
            self.last_timing_ms = {
                "round1": (first - started) * 1000,
                "round2": (second - first) * 1000,
                "round3": (third - second) * 1000,
                "total": (third - started) * 1000,
            }
            signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
            return encode_header(build_envelope(action, signature, profile=PROFILE))
        except CosignRefused:
            raise
        except Exception:
            raise CosignRefused("COSIGN_ABORTED") from None
        finally:
            self._party._k1 = None
