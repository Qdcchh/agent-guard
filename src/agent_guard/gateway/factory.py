"""Single production composition point, with no implicit DB provisioning."""

from agent_guard.authorization.evidence_store import EvidenceStore
from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.authorization.verifier import InvocationVerifier
from agent_guard.contracts.encoding import load_strict_json
from agent_guard.execution.query import AuthorizedQuery
from agent_guard.execution.service import ExecutionService
from agent_guard.execution.verified import VerifiedExecution
from agent_guard.gateway.config import GatewayConfig, GatewaySecrets, trusted_inputs
from agent_guard.gateway.endpoint import GatewayEndpoint
from agent_guard.gateway.http_app import GatewayHttpApp
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.server.config import ConfigError, secret_sha256
from agent_guard.tools.downstream import MockDownstream


def build_app(
    config: GatewayConfig, secrets: GatewaySecrets, *, gateway_dsn: str, downstream_dsn: str
):
    if type(config) is not GatewayConfig or type(secrets) is not GatewaySecrets:
        raise ConfigError("validated gateway configuration required")
    if (
        any(type(v) is not str or not v for v in (gateway_dsn, downstream_dsn))
        or gateway_dsn == downstream_dsn
    ):
        raise ConfigError("independent explicit database connections required")
    secret_sha256(secrets.downstream_secret)
    value = load_strict_json(config.raw)
    keys, identities, registrations, catalog = trusted_inputs(value)
    evidence = EvidenceStore(gateway_dsn)
    provider = PermissionSnapshotProvider(
        gateway_dsn, issuer=value["issuer"], as_keys=keys, registrations=registrations
    )
    verifier = InvocationVerifier(
        issuer=value["issuer"],
        as_keys=keys,
        identities=identities,
        permission_provider=provider,
        evidence_store=evidence,
    )
    downstream = MockDownstream(downstream_dsn, service_secret=secrets.downstream_secret)
    service = ExecutionService(
        gateway_dsn=gateway_dsn,
        ledger=ExecutionLedger(gateway_dsn),
        catalog=catalog,
        downstream=downstream,
        downstream_secret=secrets.downstream_secret,
    )
    endpoint = GatewayEndpoint(
        verifier=verifier,
        execution=VerifiedExecution(service, evidence_store=evidence),
        queries=AuthorizedQuery(gateway_dsn, evidence_store=evidence),
    )
    return GatewayHttpApp(
        endpoint, timeout_seconds=value["request_timeout_seconds"], max_workers=value["max_workers"]
    )
