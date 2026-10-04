"""Synthetic B-side demo against a run-exclusive PostgreSQL test schema.

Run with ``python -m tests.demo_b_flow`` after configuring the same test DSN
as the integration suite. No raw token, proof, client secret or private key is
printed. This demonstrates the authorization boundary, not an HTTP login or
the A-side procurement execution path.
"""

from __future__ import annotations

import os

import psycopg

from agent_guard.authorization.exchange_service import TokenExchangeError
from agent_guard.authorization.revocation_service import TaskRevocationService
from agent_guard.crypto.sm import verify_compact_jws
from agent_guard.ledger.lineage import apply_bundle_migrations as apply_migrations
from tests.fixtures.isolation import IsolationError, acquire_namespace, release_namespace
from tests.integration.test_exchange_service import (
    TENANT,
    _exchange,
    _form,
    _root,
)


def main() -> int:
    dsn = os.environ.get("AGENT_GUARD_TEST_DATABASE_URL")
    if not dsn:
        print("ERROR: AGENT_GUARD_TEST_DATABASE_URL is required; refusing to guess a database")
        return 2
    try:
        namespace = acquire_namespace(dsn)
    except (IsolationError, psycopg.Error) as exc:
        print(f"ERROR: cannot create an isolated test schema: {type(exc).__name__}")
        return 2
    try:
        with psycopg.connect(namespace.dsn) as conn:
            apply_migrations(conn)
        as_key, keys, registrations, exchanges, root = _root(namespace.dsn)
        print("1/5 One-use code redeemed; signed root created:", root.ag_grant_id)
        first_form = _form(as_key, root.access_token)

        try:
            _exchange(exchanges, keys, registrations, first_form, holder="selector")
        except TokenExchangeError as exc:
            if exc.code != "SUBJECT_OR_PROOF_INVALID":
                raise
            print("2/5 Stolen parent token without holder identity: DENIED")
        else:
            raise AssertionError("stolen-token exchange unexpectedly succeeded")

        first = _exchange(exchanges, keys, registrations, first_form)
        retry = _exchange(exchanges, keys, registrations, first_form)
        if first.access_token != retry.access_token:
            raise AssertionError("idempotent retry minted a different token")
        print("3/5 Planner to selector: signed child; fresh-proof retry returned same token")

        second_form = _form(as_key, first.access_token, recipient="executor", ttl=100)
        second = _exchange(exchanges, keys, registrations, second_form, holder="selector")
        claims = verify_compact_jws(
            second.access_token,
            expected_type="ag-at+jwt",
            trusted_keys={"as-sign-1": as_key.public_key()},
        )
        if (
            claims["ag_parent_id"] != first.ag_grant_id
            or claims["ag_root_id"] != root.ag_grant_id
            or claims["ag_delegation_remaining"] != 0
        ):
            raise AssertionError("second-level authorization chain mismatch")
        print("4/5 Selector to executor: AS-signed depth-0 child and parent chain verified")

        TaskRevocationService(namespace.dsn).revoke_task(
            tenant_id=TENANT, task_id="task-001", authenticated_subject="user-001"
        )
        try:
            _exchange(exchanges, keys, registrations, first_form)
        except TokenExchangeError as exc:
            if exc.code != "REVOKED":
                raise
            print("5/5 Owner revoked root; further delegated exchange: DENIED")
        else:
            raise AssertionError("revoked task was reused")
        print("B-side synthetic authorization demo: PASS (not an end-to-end procurement claim)")
        return 0
    finally:
        release_namespace(namespace)


if __name__ == "__main__":
    raise SystemExit(main())
