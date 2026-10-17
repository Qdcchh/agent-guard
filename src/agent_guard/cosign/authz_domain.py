"""Read-only signed-AS-policy gate for the semi-honest COSM2 prototype."""

import psycopg

from agent_guard.authorization.claims import ClaimsError
from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.contracts.execution import ToolId
from agent_guard.cosign.encoding import point_from_hex
from agent_guard.cosign.protocol import AuthzParty
from agent_guard.cosign.shares import load_share
from agent_guard.ledger import store
from agent_guard.threshold.codec import cosm2_message, parse_action_v3
from agent_guard.tools.params import parse_tool_params
from agent_guard.tools.policy import check_static_authorization


class CosignRefused(ValueError):
    """Stable public refusal; never includes secret material or complete tokens."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def action_params(action):
    return {
        key: action[key]
        for key in ("request_id", "quote_id", "quote_version", "items", "delivery_id")
    }


class AuthorizationDomainSigner:
    def __init__(self, *, share_dir, dsn_readonly, snapshot_provider, policy):
        if type(snapshot_provider) is not PermissionSnapshotProvider:
            raise ValueError("real signed snapshot provider required")
        if snapshot_provider._dsn != dsn_readonly:
            raise ValueError("snapshot provider must use the same read-only DSN")
        if policy.scheme != "sm2-2p":
            raise ValueError("COSM2 policy required")
        share = load_share(share_dir, role="authz")
        if share.public_key_spki != policy.group_public_key or share.key_epoch != policy.key_epoch:
            raise ValueError("share does not match trusted policy")
        self._party = AuthzParty(share.share, share.public_point)
        self._dsn = dsn_readonly
        self._provider = snapshot_provider
        self._policy = policy
        self.sign_count = 0

    def respond(self, *, action, leaf_access_token, q1_hex, now):
        try:
            action = parse_action_v3(action)
        except Exception:
            raise CosignRefused("AUTHZ_PATH_MISMATCH") from None
        policy = self._policy
        if (
            action["audience"] != policy.audience
            or action["policy_version"] != policy.policy_version
            or action["key_epoch"] != policy.key_epoch
            or action["tool_id"] != policy.tool_id
        ):
            raise CosignRefused("AUTHZ_POLICY_MISMATCH")
        if (
            type(now) is not int
            or not now < action["expires_at"] <= now + policy.max_lifetime_seconds
        ):
            raise CosignRefused("AUTHZ_EXPIRED")
        try:
            source = self._provider.load(leaf_access_token, grant_id=action["grant_id"], now=now)
        except ClaimsError as exc:
            raise CosignRefused(
                "AUTHZ_EXPIRED" if exc.code == "EXPIRED" else "AUTHZ_PATH_MISMATCH"
            ) from None
        except Exception:
            raise CosignRefused("AUTHZ_PATH_MISMATCH") from None
        snapshot = source.snapshot
        if (
            list(snapshot.chain_grant_ids) != action["path_grant_ids"]
            or snapshot.tenant_id != action["tenant_id"]
            or snapshot.task_id != action["task_id"]
            or snapshot.root_id != action["root_grant_id"]
        ):
            raise CosignRefused("AUTHZ_PATH_MISMATCH")
        try:
            check_static_authorization(
                snapshot,
                grant_id=action["grant_id"],
                root_id=action["root_grant_id"],
                tenant_id=action["tenant_id"],
                task_id=action["task_id"],
                subject=snapshot.subject,
                tool_id=ToolId(action["tool_id"]),
                params=parse_tool_params(
                    action["tool_id"], canonical_json_bytes(action_params(action))
                ),
                db_path=tuple(action["path_grant_ids"]),
            )
        except Exception:
            raise CosignRefused("AUTHZ_SCOPE") from None
        try:
            with psycopg.connect(self._dsn, connect_timeout=5) as conn:
                conn.execute("SET TRANSACTION READ ONLY")
                conn.execute("SET LOCAL statement_timeout='15s'")
                path = store.load_path(conn, action["grant_id"])
                self._provider.revalidate(conn, source)
                leaf = path[-1]
                if (
                    tuple(g.grant_id for g in path) != tuple(action["path_grant_ids"])
                    or leaf.holder_client_id != action["holder_client_id"]
                    or leaf.holder_kid != action["holder_kid"]
                ):
                    raise CosignRefused("AUTHZ_PATH_MISMATCH")
                # Evaluate each predicate over the complete ancestry before
                # moving to the next: an exhausted root cannot mask a revoked
                # descendant. This is the original B3 policy order.
                if any(grant.revoked for grant in path):
                    raise CosignRefused("AUTHZ_REVOKED")
                if any(
                    not grant.not_before.timestamp() <= now < grant.expires_at.timestamp()
                    for grant in path
                ):
                    raise CosignRefused("AUTHZ_EXPIRED")
                remaining = min(
                    grant.amount_limit - grant.amount_reserved - grant.amount_settled
                    for grant in path
                )
                if action["amount_fen"] > remaining or any(
                    grant.calls_reserved + grant.calls_settled >= grant.call_limit for grant in path
                ):
                    raise CosignRefused("AUTHZ_OVER_BUDGET")
        except CosignRefused:
            raise
        except Exception:
            raise CosignRefused("AUTHZ_PATH_MISMATCH") from None
        try:
            q1 = point_from_hex(q1_hex)
            message = cosm2_message(action)
            self.sign_count += 1
            r, s2, s3 = self._party.sign_round2(message, q1)
            return {"r": r, "s2": s2, "s3": s3}
        except Exception:
            raise CosignRefused("COSIGN_ABORTED") from None
