"""Explicit ephemeral SELECT-only principal for owned synthetic test databases."""

import secrets
from contextlib import contextmanager

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


@contextmanager
def readonly_role(admin_dsn):
    name = "cosm2_ro_" + secrets.token_hex(8)
    password = secrets.token_urlsafe(32)
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
            ).format(sql.Identifier(name), sql.Literal(password))
        )
        try:
            schema = conn.execute("SELECT current_schema()").fetchone()[0]
            conn.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            )
            conn.execute(
                sql.SQL("GRANT SELECT ON ag_grants, ag_grant_tokens TO {}").format(
                    sql.Identifier(name)
                )
            )
            params = conninfo_to_dict(admin_dsn)
            params.update(user=name, password=password)
            yield make_conninfo(**params)
        finally:
            conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(name)))
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))


def readonly_provider(provider, dsn):
    from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider

    return PermissionSnapshotProvider(
        dsn,
        issuer=provider._issuer,
        as_keys=provider._as_keys,
        registrations=provider._registrations,
    )
