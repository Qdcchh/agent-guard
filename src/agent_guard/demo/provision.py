"""Trusted provisioning and evidence-bound maintenance; never mint grants."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import psycopg

from agent_guard.audit.delivery import confirm_registered_tx
from agent_guard.audit.journal import bootstrap_task_tx, gateway_origin
from agent_guard.audit.store import (
    register_key,
    register_stream,
)
from agent_guard.audit.store import (
    register_principal as register_audit_principal,
)
from agent_guard.authorization.provisioning import register_task_policy, register_user
from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.demo.config import (
    ApprovedDIDSnapshot,
    DemoConfigError,
    DemoRunConfig,
    DrainReceipt,
    FrozenExportInputs,
    OperatorSecrets,
    ProvisionReport,
    SyntheticLogin,
    decode,
    exact,
    freeze,
    thaw,
)
from agent_guard.ledger.lineage import apply_bundle_migrations
from agent_guard.ledger.provisioning import register_principal
from agent_guard.server.private_files import read_private_file
from agent_guard.tools.downstream import MockDownstream

AUTHORITY_WRITERS = frozenset(("as", "gateway", "worker", "publisher"))


def load_operator_secrets(config: DemoRunConfig, *, task_policy, audit_registration=None):
    role = config.roles["operator"]
    if os.getuid() != role.uid:
        raise DemoConfigError("operator UID required")
    login = exact(
        decode(read_private_file(role.private_files["user_login"])),
        ("tenant_id", "subject", "password"),
    )
    registration = decode(read_private_file(role.private_files["audit_registration"]))
    exact(
        registration,
        (
            "writer_id",
            "writer_secret",
            "reader_id",
            "reader_secret",
            "publisher_reader_id",
            "publisher_reader_secret",
        ),
    )
    if audit_registration is not None and thaw(audit_registration) != registration:
        raise DemoConfigError("independent audit registration mismatch")
    return OperatorSecrets(
        role,
        SyntheticLogin(**login),
        freeze(thaw(task_policy)),
        read_private_file(role.private_files["downstream_secret"]).decode("ascii"),
        freeze(registration),
    )


def _dsn(role, name):
    value = read_private_file(role.private_files[name]).decode("utf-8")
    from psycopg.conninfo import conninfo_to_dict

    parsed = conninfo_to_dict(value)
    if (
        parsed.get("sslmode") != "verify-full"
        or parsed.get("sslrootcert") != str(role.public_config_file.parent / "ca.pem")
        or parsed.get("user")
        != (
            "demo_gateway_export"
            if role.role == "gateway" and name == "readonly_dsn"
            else "demo_" + role.role
        )
        or parsed.get("dbname") in (None, "postgres", "template0", "template1")
    ):
        raise DemoConfigError("role-specific verified PostgreSQL TLS required")
    return value


def provision_run(
    config: DemoRunConfig, *, operator: OperatorSecrets, approved: ApprovedDIDSnapshot
) -> ProvisionReport:
    if (
        type(config) is not DemoRunConfig
        or type(operator) is not OperatorSecrets
        or operator.role != config.roles["operator"]
        or os.getuid() != operator.role.uid
        or type(approved) is not ApprovedDIDSnapshot
        or approved.run_id != config.run_id
    ):
        raise DemoConfigError("approved operator scope required")
    public = load_strict_json(config.public_manifest.read_bytes())
    registrations = public["registrations"]
    if {r["client_id"] for r in registrations} != {
        "agent-planner",
        "agent-selector",
        "agent-executor",
    }:
        raise DemoConfigError("fixed principal registry required")
    policy = thaw(operator.task_policy)
    if (
        policy["amount_limit_fen"] != 100000
        or policy["call_limit"] != 12
        or policy["tenant_id"] != config.scope["tenant_id"]
        or policy["task_id"] != config.scope["task_id"]
        or policy["owner_subject"] != operator.login.subject
    ):
        raise DemoConfigError("fixed root task policy required")
    policy["task_expires_at"] = datetime.fromisoformat(policy["task_expires_at"])
    authority = _dsn(operator.role, "authority_dsn")
    downstream = _dsn(operator.role, "downstream_dsn")
    if authority == downstream:
        raise DemoConfigError("independent downstream domain required")
    with psycopg.connect(authority, connect_timeout=5) as conn:
        apply_bundle_migrations(conn)
        register_user(
            conn,
            tenant_id=operator.login.tenant_id,
            subject=operator.login.subject,
            password=operator.login.password,
        )
        register_task_policy(conn, **policy)
        for registration in registrations:
            register_principal(
                conn,
                tenant_id=registration["tenant_id"],
                client_id=registration["client_id"],
                kid=registration["kid"],
            )
    downstream_service = MockDownstream(
        downstream,
        service_secret=operator.downstream_secret,
        approved_suppliers=frozenset(("supplier-001",)),
        approved_recipients=frozenset(policy["constraints"]["recipient_ids"]),
        served_requests=frozenset(policy["constraints"]["request_ids"]),
    )
    downstream_service.provision()
    return ProvisionReport(config.run_id, tuple(sorted(r["client_id"] for r in registrations)))


def validate_drain(config: DemoRunConfig, stopped: DrainReceipt):
    if (
        type(stopped) is not DrainReceipt
        or (stopped.run_id, stopped.owner_id) != (config.run_id, config.owner_id)
        or {w.role for w in stopped.writers} != AUTHORITY_WRITERS
        or len(stopped.writers) != len(AUTHORITY_WRITERS)
        or set(stopped.blocked_credentials) != AUTHORITY_WRITERS
    ):
        raise DemoConfigError("complete authority writer drain evidence required")
    datetime.fromisoformat(stopped.stopped_at)
    for writer in stopped.writers:
        if (
            writer.process.pid != writer.pid
            or not writer.start_identity
            or len(writer.argv_sha256) != 64
            or writer.process.poll() is None
            or not writer.inflight_zero.is_set()
        ):
            raise DemoConfigError("writer exit and inflight drain evidence required")
    # Existing bootstrap locks additionally drain all in-flight authority TXs.
    # Credentials stay physically unmounted until operator registers descriptor.


def bootstrap_journal(config: DemoRunConfig, *, stopped: DrainReceipt):
    validate_drain(config, stopped)
    if os.getuid() != config.roles["operator"].uid:
        raise DemoConfigError("maintenance operator UID required")
    with psycopg.connect(
        _dsn(config.roles["operator"], "authority_dsn"), connect_timeout=5
    ) as conn:
        return bootstrap_task_tx(
            conn,
            scope_key=(
                gateway_origin(),
                config.scope["tenant_id"],
                config.scope["task_id"],
            ),
        )


def register_bootstrap(
    config: DemoRunConfig,
    *,
    stopped: DrainReceipt,
    descriptor,
    trust,
    writer_credential_id: str,
    writer_credential: str,
    reader_credential_id: str,
    reader_credential: str,
    additional_readers: tuple[tuple[str, str], ...] = (),
):
    validate_drain(config, stopped)
    if os.getuid() != config.roles["operator"].uid or (
        descriptor.scope.gateway_id,
        descriptor.scope.tenant_id,
        descriptor.scope.task_id,
    ) != (
        config.scope["gateway_origin"],
        config.scope["tenant_id"],
        config.scope["task_id"],
    ):
        raise DemoConfigError("independent audit registration scope required")
    with psycopg.connect(_dsn(config.roles["operator"], "audit_dsn"), connect_timeout=5) as conn:
        register_stream(conn, descriptor)
        register_key(conn, trust)
        register_audit_principal(
            conn,
            credential_id=writer_credential_id,
            credential=writer_credential,
            role="WRITER",
            stream_id=descriptor.scope.stream_id,
        )
        register_audit_principal(
            conn,
            credential_id=reader_credential_id,
            credential=reader_credential,
            role="READER",
            stream_id=descriptor.scope.stream_id,
        )
        if type(additional_readers) is not tuple or len(additional_readers) > 8:
            raise DemoConfigError("bounded independent audit readers required")
        identifiers = {writer_credential_id, reader_credential_id}
        for identifier, credential in additional_readers:
            if identifier in identifiers:
                raise DemoConfigError("duplicate audit credential identifier")
            identifiers.add(identifier)
            register_audit_principal(
                conn,
                credential_id=identifier,
                credential=credential,
                role="READER",
                stream_id=descriptor.scope.stream_id,
            )
    # Exiting the remote connection above commits stream, key and every principal.
    # A separate authority transaction cannot confirm a rolled-back remote registration.
    with psycopg.connect(
        _dsn(config.roles["operator"], "authority_dsn"), connect_timeout=5
    ) as conn:
        confirm_registered_tx(conn, descriptor=descriptor)
    return descriptor


def freeze_export_inputs(
    config: DemoRunConfig,
    *,
    stopped: DrainReceipt,
    reader,
    public_trust: bytes,
    out_dir: Path,
) -> FrozenExportInputs:
    """Freeze one independently approved scope and exact remote history at fixed H."""
    import time
    from dataclasses import asdict

    from agent_guard.audit.checkpoint import verify_checkpoint
    from agent_guard.audit.client import AuditClient
    from agent_guard.evidence.task_bundle import (
        MAX_JOURNAL,
        MAX_WIRE_BYTES,
        load_checkpoint_history,
    )
    from agent_guard.evidence.task_verify import load_public_trust
    from agent_guard.server.private_files import private_directory

    validate_drain(config, stopped)
    role = config.roles["operator"]
    if (
        os.getuid() != role.uid
        or type(reader) is not AuditClient
        or reader.origin != config.endpoints["audit_origin"]
    ):
        raise DemoConfigError("independent fixed audit reader and operator required")
    value = decode(public_trust)
    if canonical_json_bytes(value) != public_trust:
        raise DemoConfigError("canonical independent public trust required")
    trust = load_public_trust(value)
    if (trust.scope.gateway_id, trust.scope.tenant_id, trust.scope.task_id) != (
        config.scope["gateway_origin"],
        config.scope["tenant_id"],
        config.scope["task_id"],
    ):
        raise DemoConfigError("export trust scope mismatch")
    out_dir = Path(out_dir)
    if out_dir.parent != role.public_config_file.parent:
        raise DemoConfigError("exclusive operator export inputs leaf required")
    checkpoint = reader.latest(trust.scope.stream_id)
    if checkpoint is None:
        raise DemoConfigError("persisted audit checkpoint required before freeze")
    observed = verify_checkpoint(checkpoint, trust=trust.audit_keys, expected_scope=trust.scope)
    pin = {
        "mode": "LATEST_OBSERVATION",
        "checkpoint_jws": checkpoint,
        "observed_at": int(time.time()),
        "scope": asdict(trust.scope),
    }
    with private_directory(out_dir, create=True) as directory:
        directory.write_file("public-trust.json", public_trust)
        directory.write_file("external-pin.json", canonical_json_bytes(pin))
        directory.write_file("checkpoint-history.ndjson", b"")
    history_path = out_dir / "checkpoint-history.ndjson"
    after = total = count = 0
    with history_path.open("ab") as output:
        while True:
            page = reader.history(
                trust.scope.stream_id,
                observed_checkpoint_id=observed.claims.checkpoint_id,
                after_sequence=after,
            )
            if (
                page.stream_id,
                page.observed_checkpoint_id,
                page.observed_sequence,
            ) != (
                trust.scope.stream_id,
                observed.claims.checkpoint_id,
                observed.claims.sequence,
            ):
                raise DemoConfigError("audit history changed fixed observation")
            for jws in page.checkpoints:
                raw = canonical_json_bytes({"checkpoint_jws": jws}) + b"\n"
                total += len(raw)
                count += 1
                if total > MAX_WIRE_BYTES or count > MAX_JOURNAL:
                    raise DemoConfigError("audit history capacity")
                output.write(raw)
            next_after = page.next_after_sequence
            if next_after is None:
                break
            if (
                type(next_after) is not int
                or not after < next_after <= observed.claims.sequence
                or not page.checkpoints
            ):
                raise DemoConfigError("audit history did not advance")
            after = next_after
        output.flush()
        os.fsync(output.fileno())
    for path in out_dir.iterdir():
        path.chmod(0o444)
    with history_path.open("rb") as stream:
        history = load_checkpoint_history(stream, external_trust=trust, external_pin=pin)
    return FrozenExportInputs(
        config.run_id,
        out_dir / "public-trust.json",
        out_dir / "external-pin.json",
        history_path,
        history,
        freeze(pin),
    )


def readonly_export_factory(config: DemoRunConfig, *, role: str = "export"):
    """Fresh accepted exporter connections under the separately provisioned SELECT role."""
    if type(role) is not str or role not in ("export", "gateway"):
        raise DemoConfigError("fixed export connection role required")
    selected = config.roles[role]
    if os.getuid() != selected.uid:
        raise DemoConfigError("export connection role UID required")
    dsn = _dsn(selected, "readonly_dsn")
    return lambda: psycopg.connect(dsn, connect_timeout=5)


def build_as(config: DemoRunConfig, *, approved: ApprovedDIDSnapshot):
    from agent_guard.server.config import (
        load_secrets,
        load_server_config,
        resolve_paths,
    )
    from agent_guard.server.factory import build_app

    role = config.roles["as"]
    if approved.run_id != config.run_id or os.getuid() != role.uid:
        raise DemoConfigError("AS role and frozen DID approval required")
    value = load_strict_json(read_private_file(role.public_config_file))
    value["did_documents"] = approved.factory_documents()
    parsed = resolve_paths(
        load_server_config(canonical_json_bytes(value)), role.public_config_file.parent
    )
    return build_app(
        parsed,
        load_secrets(read_private_file(role.private_files["secrets"])),
        dsn=_dsn(role, "authority_dsn"),
    )


def build_gateway(
    config: DemoRunConfig,
    *,
    approved: ApprovedDIDSnapshot,
    export_connection_factory=None,
    export_spool_parent=None,
    export_inputs: FrozenExportInputs | None = None,
    export_credentials: tuple = (),
):
    from agent_guard.gateway.config import load_gateway_config, load_gateway_secrets
    from agent_guard.gateway.factory import build_app

    role = config.roles["gateway"]
    if approved.run_id != config.run_id or os.getuid() != role.uid:
        raise DemoConfigError("gateway role and frozen DID approval required")
    value = load_strict_json(read_private_file(role.public_config_file))
    value["did_documents"] = approved.factory_documents()
    if export_inputs is not None:
        from dataclasses import asdict

        from agent_guard.gateway.evidence_auth import ExportCredential

        if (
            type(export_inputs) is not FrozenExportInputs
            or export_inputs.run_id != config.run_id
            or type(export_credentials) is not tuple
            or not export_credentials
            or any(
                type(item) is not ExportCredential
                or item.tenant_id != config.scope["tenant_id"]
                or item.task_ids != (config.scope["task_id"],)
                for item in export_credentials
            )
        ):
            raise DemoConfigError("frozen independent single-scope export inputs required")
        for path in (
            export_inputs.public_trust_file,
            export_inputs.external_pin_file,
            export_inputs.checkpoint_history_file,
        ):
            if path.is_symlink() or path.resolve() != path or path.stat().st_mode & 0o222:
                raise DemoConfigError("frozen canonical read-only export files required")
        value["export_credentials"] = [
            dict(asdict(item), task_ids=list(item.task_ids)) for item in export_credentials
        ]
        value["evidence_local_inputs"] = {
            "trust_file": str(export_inputs.public_trust_file),
            "external_pin_file": str(export_inputs.external_pin_file),
            "external_checkpoint_history_file": str(export_inputs.checkpoint_history_file),
        }
    elif export_credentials:
        raise DemoConfigError("complete frozen export inputs required")
    return build_app(
        load_gateway_config(canonical_json_bytes(value)),
        load_gateway_secrets(read_private_file(role.private_files["secrets"])),
        gateway_dsn=_dsn(role, "authority_dsn"),
        downstream_dsn=_dsn(role, "downstream_dsn"),
        export_connection_factory=export_connection_factory,
        export_spool_parent=export_spool_parent,
    )
