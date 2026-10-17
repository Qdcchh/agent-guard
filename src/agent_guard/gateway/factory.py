"""Single production composition point, with no implicit DB provisioning."""

from agent_guard.authorization.evidence_store import EvidenceStore
from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.authorization.verifier import InvocationVerifier
from agent_guard.contracts.encoding import load_strict_json
from agent_guard.execution.query import AuthorizedQuery
from agent_guard.execution.receipt_publication import ReceiptVerifier
from agent_guard.execution.service import ExecutionService
from agent_guard.execution.verified import VerifiedExecution
from agent_guard.gateway.config import (
    GatewayConfig,
    GatewaySecrets,
    evidence_operator_inputs,
    receipt_public_keys,
    threshold_policy,
    trusted_inputs,
)
from agent_guard.gateway.endpoint import GatewayEndpoint
from agent_guard.gateway.http_app import GatewayHttpApp
from agent_guard.ledger.service import ExecutionLedger
from agent_guard.server.config import ConfigError, secret_sha256
from agent_guard.threshold.verifier import ThresholdApprovalVerifier
from agent_guard.tools.downstream import MockDownstream


def build_app(
    config: GatewayConfig,
    secrets: GatewaySecrets,
    *,
    gateway_dsn: str,
    downstream_dsn: str,
    export_connection_factory=None,
    export_spool_parent=None,
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
    policy = threshold_policy(value)
    threshold_verifier = ThresholdApprovalVerifier(policy=policy) if policy is not None else None
    evidence = EvidenceStore(gateway_dsn)
    provider = PermissionSnapshotProvider(
        gateway_dsn, issuer=value["issuer"], as_keys=keys, registrations=registrations
    )
    public_keys = receipt_public_keys(value, as_keys=keys, registrations=registrations)
    receipt_verifier = (
        ReceiptVerifier(
            issuer=value["issuer"],
            as_keys=keys,
            gateway_keys=public_keys,
            registrations=registrations,
            permission_provider=provider,
        )
        if public_keys is not None
        else None
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
        queries=AuthorizedQuery(
            gateway_dsn, evidence_store=evidence, receipt_verifier=receipt_verifier
        ),
        receipt_verifier=receipt_verifier,
        threshold_verifier=threshold_verifier,
    )
    gateway_app = GatewayHttpApp(
        endpoint,
        timeout_seconds=value["request_timeout_seconds"],
        max_workers=value["max_workers"],
    )
    credentials, local_inputs = evidence_operator_inputs(value)
    if local_inputs is None:
        if export_connection_factory is not None or export_spool_parent is not None:
            raise ConfigError("export resources require explicit export registration")
        return gateway_app
    if not callable(export_connection_factory) or export_spool_parent is None:
        raise ConfigError("independent SELECT-only export connection and private spool required")
    from agent_guard.evidence.task_bundle import load_checkpoint_history
    from agent_guard.evidence.task_verify import load_public_trust
    from agent_guard.evidence.verify_cli import _json
    from agent_guard.gateway.evidence_endpoint import (
        EvidenceExportEndpoint,
        ExportTaskInputs,
    )
    from agent_guard.gateway.evidence_http_app import EvidenceHttpApp

    with open(local_inputs.trust_file, "rb") as stream:
        trust = load_public_trust(_json(stream))
    with open(local_inputs.external_pin_file, "rb") as stream:
        pin = _json(stream)
    with open(local_inputs.external_checkpoint_history_file, "rb") as stream:
        history = load_checkpoint_history(stream, external_trust=trust, external_pin=pin)
    export_endpoint = EvidenceExportEndpoint(
        export_connection_factory,
        credentials=credentials,
        task_inputs=(
            ExportTaskInputs(
                trust.scope,
                pin["mode"],
                pin["checkpoint_jws"],
                pin["observed_at"],
                history,
            ),
        ),
        spool_parent=export_spool_parent,
    )
    return EvidenceHttpApp(export_endpoint, gateway_app=gateway_app)
