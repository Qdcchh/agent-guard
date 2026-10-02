"""Integration test fixtures: a real PostgreSQL is mandatory here.

The documented integration command must FAIL (not silently skip) when no
database is reachable — a green run without PostgreSQL would be a false pass.

Every session acquires a run-exclusive schema with an ownership marker
(:mod:`tests.fixtures.isolation`); destructive resets only ever touch that
schema after re-verifying ownership, so concurrent sessions and unrelated
databases are never wiped.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest

from agent_guard.ledger import apply_migrations
from agent_guard.ledger.service import ExecutionLedger
from tests.fixtures.execution import DOWNSTREAM_SECRET, A2Env, build_env
from tests.fixtures.isolation import (
    IsolationError,
    Namespace,
    ScratchDatabase,
    acquire_namespace,
    create_downstream_database,
    drop_downstream_database,
    release_namespace,
    reset_state,
)
from tests.fixtures.state import TreeFixture, build_tree

DSN_ENV = "AGENT_GUARD_TEST_DATABASE_URL"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: needs a reachable PostgreSQL")


@pytest.fixture(scope="session")
def namespace() -> Iterator[Namespace]:
    value = os.environ.get(DSN_ENV)
    if not value:
        pytest.fail(
            f"{DSN_ENV} is required for integration tests; start the test database "
            "with `docker compose -f compose.test.yaml up -d --wait` and export it "
            "(see README). Refusing to skip: skipping would fake a green run.",
            pytrace=False,
        )
    try:
        ns = acquire_namespace(value)
    except IsolationError as exc:
        pytest.fail(f"refusing unsafe test target: {exc}", pytrace=False)
    except psycopg.Error as exc:
        pytest.fail(f"integration tests require reachable PostgreSQL: {exc}", pytrace=False)
    try:
        yield ns
    finally:
        release_namespace(ns)


@pytest.fixture(scope="session")
def dsn(namespace: Namespace) -> str:
    return namespace.dsn


@pytest.fixture(scope="session")
def migrated(namespace: Namespace) -> Namespace:
    with psycopg.connect(namespace.dsn, connect_timeout=5) as conn:
        apply_migrations(conn)
    return namespace


@pytest.fixture()
def ledger(migrated: Namespace, namespace: Namespace) -> ExecutionLedger:
    reset_state(namespace)
    return ExecutionLedger(namespace.dsn)


@pytest.fixture()
def tree(ledger: ExecutionLedger, namespace: Namespace, migrated: Namespace) -> TreeFixture:
    """A fresh root -> mid -> leaf chain; use together with ``ledger``."""
    with psycopg.connect(namespace.dsn, connect_timeout=5) as conn:
        return build_tree(conn)


# ---------------------------------------------------------------- A2.1 core


@pytest.fixture(scope="session")
def downstream_db(namespace: Namespace) -> Iterator[ScratchDatabase]:
    """A random-named downstream database owned by this run (separate domain)."""
    created = create_downstream_database(namespace.base_dsn)
    try:
        yield created
    finally:
        drop_downstream_database(namespace.base_dsn, created)


@pytest.fixture(scope="session")
def downstream_dsn(downstream_db: ScratchDatabase) -> str:
    return downstream_db.dsn


@pytest.fixture()
def a2(
    ledger: ExecutionLedger,
    namespace: Namespace,
    migrated: Namespace,
    downstream_dsn: str,
) -> A2Env:
    """A wired A2.1 environment: real gateway DB plus an independent downstream.

    The downstream domain is provisioned and emptied here so every test starts
    from zero downstream effects and never reuses another test's order.
    """
    from agent_guard.tools.downstream import MockDownstream

    MockDownstream(downstream_dsn, service_secret=DOWNSTREAM_SECRET).provision()
    MockDownstream(downstream_dsn, service_secret=DOWNSTREAM_SECRET).reset()
    with psycopg.connect(namespace.dsn, connect_timeout=5) as conn:
        fresh = build_tree(conn)
    return build_env(
        tree=fresh,
        gateway_dsn=namespace.dsn,
        downstream_dsn=downstream_dsn,
    )
