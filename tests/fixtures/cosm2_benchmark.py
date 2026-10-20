"""Owned real-AS/PG adapters for benchmark boundaries, never an authorization bypass."""

import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

import psycopg

from agent_guard.cosign.encoding import point_to_hex
from agent_guard.ledger.lineage import apply_bundle_migrations
from agent_guard.threshold.codec import cosm2_message
from tests.fixtures.cosm2 import readonly_role
from tests.fixtures.gateway import raw_material, request
from tests.fixtures.isolation import (
    acquire_namespace,
    create_downstream_database,
    drop_downstream_database,
    release_namespace,
)
from tests.fixtures.threshold import approval_action
from tests.integration.test_cosm2_gateway import build_cosign_env
from tests.integration.test_verified_execution import signed_env


class GatewayBenchmark:
    """One adapter owns one namespace, independent downstream, and SELECT-only role."""

    def __init__(self, base_dsn, *, expected_accepts):
        self._stack = ExitStack()
        self.accepted = 0
        self.sequence = 0
        try:
            self.namespace = acquire_namespace(base_dsn)
            self._stack.callback(release_namespace, self.namespace)
            downstream = create_downstream_database(self.namespace.base_dsn)
            self._stack.callback(drop_downstream_database, self.namespace.base_dsn, downstream)
            self.downstream_dsn = downstream.dsn
            with psycopg.connect(self.namespace.dsn) as conn:
                apply_bundle_migrations(conn)
            n = expected_accepts + 10
            self.env = signed_env(
                self.namespace.dsn,
                downstream.dsn,
                root_limit_fen=n * 70000 * 3,
                selector_limit_fen=n * 70000 * 2,
                executor_limit_fen=n * 70000,
                root_calls=n * 3,
                selector_calls=n * 2,
                executor_calls=n,
            )
            ro = self._stack.enter_context(readonly_role(self.namespace.dsn))
            private = self._stack.enter_context(
                tempfile.TemporaryDirectory(prefix="cosm2-bench-domains-")
            )
            assembly = build_cosign_env(
                self.namespace.dsn,
                downstream.dsn,
                Path(private) / "keys",
                ro,
                env=self.env,
            )
            self.env, self.signer, self.app = assembly.env, assembly.signer, assembly.app
            self._stack.callback(self.app._executor.shutdown)
            self.expected_accepts = expected_accepts
        except Exception:
            self._stack.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self._stack.__exit__(*exc)

    def _action(self):
        self.sequence += 1
        bundle = self.env.bundle(f"benchmark-{self.sequence}")
        action = approval_action(
            bundle,
            action_id=f"bench-action-{self.sequence}",
            policy_version=self.signer.policy.policy_version,
            key_epoch=self.signer.policy.key_epoch,
            expires_at=int(time.time()) + 60,
            version=3,
            payment_digest="0" * 64,
        )
        return bundle, action

    def prepare_round2(self):
        _, action = self._action()
        party = self.signer.exec_signer._party
        q1_hex = point_to_hex(party.sign_round1())

        def operation():
            return self.signer.authz_signer.respond(
                action=action, leaf_access_token=self.env.token, q1_hex=q1_hex, now=int(time.time())
            )

        def finish(partial):
            try:
                if partial is not None:
                    party.sign_round3(cosm2_message(action), **partial)
            finally:
                party._k1 = None

        return operation, finish

    def prepare_gateway(self):
        bundle, action = self._action()
        signature = self.signer.sign(action, bundle=bundle)
        header = self.signer.header_for(action, signature)
        token, proof, body = raw_material(self.namespace.dsn, bundle)
        headers = [
            (b"content-type", b"application/json"),
            (b"authorization", b"AGPoP " + token),
            (b"ag-proof", proof),
            (b"ag-approval", header),
        ]

        def operation():
            return request(self.app, body=body, headers=headers)

        def finish(response):
            if response is None or response[0] != 202 or response[1]["status"] != "RESERVED":
                raise RuntimeError("gateway acceptance failed")
            self.accepted += 1

        return operation, finish

    def verify_gateway(self):
        with psycopg.connect(self.namespace.dsn) as conn:
            operations, keys = conn.execute(
                "SELECT count(*),count(DISTINCT idempotency_key) FROM ag_operations"
            ).fetchone()
            approvals = conn.execute("SELECT count(*) FROM ag_threshold_approvals").fetchone()[0]
            counters = conn.execute(
                "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled "
                "FROM ag_grants ORDER BY depth"
            ).fetchall()
        with psycopg.connect(self.downstream_dsn) as conn:
            effects = conn.execute("SELECT count(*) FROM ds_orders").fetchone()[0]
        if (
            self.accepted != self.expected_accepts
            or operations != self.expected_accepts
            or keys != self.expected_accepts
            or approvals != self.expected_accepts
            or counters != [(70000 * self.expected_accepts, 0, self.expected_accepts, 0)] * 3
            or effects != 0
        ):
            raise RuntimeError("benchmark did not accept one fresh reserved operation per attempt")
        return dict(
            accepted=operations,
            distinct_business_keys=keys,
            approvals=approvals,
            all_ancestor_counters=[list(row) for row in counters],
            downstream_orders=effects,
        )
