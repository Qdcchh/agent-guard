"""Read-only database-state helpers for integration assertions.

Destructive cleanup lives in :mod:`tests.fixtures.isolation` and requires a
verified run-owned namespace; nothing here writes or deletes.
"""

from __future__ import annotations

import psycopg

from tests.fixtures.isolation import TABLES

__all__ = ["TABLES", "fetch_all", "fetch_counts", "fetch_counters", "fetch_one"]


def fetch_counters(dsn: str, grant_id: str) -> dict[str, int]:
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        row = conn.execute(
            "SELECT amount_reserved, amount_settled, calls_reserved, calls_settled "
            "FROM ag_grants WHERE grant_id = %s",
            (grant_id,),
        ).fetchone()
    if row is None:
        raise AssertionError(f"unknown grant {grant_id}")
    return {
        "amount_reserved": row[0],
        "amount_settled": row[1],
        "calls_reserved": row[2],
        "calls_settled": row[3],
    }


def fetch_counts(dsn: str) -> dict[str, int]:
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        return {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in TABLES
        }


def fetch_one(dsn: str, sql: str, params: tuple = ()) -> tuple | None:
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        return conn.execute(sql, params).fetchone()


def fetch_all(dsn: str, sql: str, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        return conn.execute(sql, params).fetchall()
