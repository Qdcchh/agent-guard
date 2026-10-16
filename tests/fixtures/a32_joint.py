"""Native task export/verification composition and independent public inputs."""

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

import psycopg

from agent_guard.audit.checkpoint import sign_checkpoint
from agent_guard.audit.contracts import CheckpointTrust, utc_text
from agent_guard.audit.journal import describe_pending_tx
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.crypto.sm import (
    generate_sm2_private_key,
    serialize_sm2_public_key,
    sm3_b64url,
)
from agent_guard.evidence.receipt_semantics import ReceiptTrust
from agent_guard.evidence.task_bundle import load_checkpoint_history
from agent_guard.evidence.task_verify import TaskTrust
from tests.fixtures.a32_export import task_scope
from tests.integration.test_exchange_service import ISSUER


def native_public_inputs(env, dsn, directory, gateway_key):
    """Initial native joint probe; CP signatures are fixture-created, not TLS delivery."""
    scope = task_scope(dsn)
    key = generate_sm2_private_key()
    audit_keys = (
        CheckpointTrust(
            "joint-audit",
            "AUDIT_SIGNER",
            serialize_sm2_public_key(key.public_key()),
            1,
            None,
        ),
    )
    with psycopg.connect(dsn) as conn:
        registration = describe_pending_tx(
            conn, scope_key=(scope.gateway_id, scope.tenant_id, scope.task_id)
        )
        rows = conn.execute(
            "SELECT seq,digest FROM ag_audit_records WHERE stream_id=%s ORDER BY seq",
            (scope.stream_id,),
        ).fetchall()
    jwss, previous = [], None
    for seq, digest in rows:
        jws = sign_checkpoint(
            {
                **asdict(scope),
                "profile": "GM-MVP-1",
                "checkpoint_version": "AG-CHECKPOINT-1",
                "checkpoint_id": str(uuid4()),
                "sequence": seq,
                "head_digest": digest,
                "previous_checkpoint_digest": previous,
                "issued_at": utc_text(datetime.now(timezone.utc)),
                "kid": "joint-audit",
            },
            private_key=key,
            key_id="joint-audit",
        )
        jwss.append(jws)
        previous = sm3_b64url(jws.encode("ascii"))
    pin = {
        "mode": "LATEST_OBSERVATION",
        "checkpoint_jws": jwss[-1],
        "observed_at": int(datetime.now(timezone.utc).timestamp()),
        "scope": asdict(scope),
    }
    path = directory / "initial-native.history"
    path.write_bytes(b"".join(canonical_json_bytes({"checkpoint_jws": j}) + b"\n" for j in jwss))
    with path.open("rb") as stream:
        history = load_checkpoint_history(
            stream,
            external_trust={"scope": scope, "audit_keys": audit_keys},
            external_pin=pin,
        )
    registrations = {r.kid: r for r in env.registrations.values()}
    receipt = ReceiptTrust(
        ISSUER,
        {"as-sign-1": env.as_key.public_key()},
        {"gw-receipt-1": gateway_key.public_key()},
        {
            r.kid: env.keys[r.client_id.removeprefix("agent-")].public_key()
            for r in registrations.values()
        },
        registrations,
    )
    return (
        scope,
        pin,
        history,
        TaskTrust(scope, receipt, audit_keys, registration, env.service._catalog),
    )


def capture_reader_history(*, scope, audit_keys, reader_credential, ca_file, directory):
    """Reader-only fixed-origin TLS capture; freeze one observed CP for all pages."""
    import ssl
    from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

    from agent_guard.audit.checkpoint import verify_checkpoint
    from agent_guard.audit.client import AuditClient, _NoRedirect
    from agent_guard.audit.contracts import decode_history_page
    from agent_guard.evidence.task_bundle import MAX_WIRE_BYTES, TaskBundleError

    reader_credential = AuditClient._credential(reader_credential)
    context = ssl.create_default_context(cafile=str(ca_file))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), _NoRedirect())
    origin = "https://audit.agent-guard.test"

    def request(endpoint, value):
        req = Request(
            origin + "/v1/audit/" + endpoint,
            data=canonical_json_bytes(value),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + reader_credential,
            },
        )
        with opener.open(req, timeout=15) as response:
            if response.status != 200 or response.geturl() != req.full_url:
                raise TaskBundleError("unexpected reader response")
            raw = response.read(65537)
        if len(raw) > 65536:
            raise TaskBundleError("reader response capacity exceeded")
        return raw

    latest = AuditClient._checkpoint(request("latest", {"stream_id": scope.stream_id}))
    checkpoint = verify_checkpoint(latest, trust=audit_keys, expected_scope=scope)
    pin = {
        "mode": "LATEST_OBSERVATION",
        "checkpoint_jws": latest,
        "observed_at": int(datetime.now(timezone.utc).timestamp()),
        "scope": asdict(scope),
    }
    path = directory / ("reader-" + str(uuid4()) + ".history")
    previous, after, count, size, last = None, 0, 0, 0, None
    try:
        with path.open("xb") as out:
            while True:
                page = decode_history_page(
                    request(
                        "history",
                        {
                            "stream_id": scope.stream_id,
                            "observed_checkpoint_id": checkpoint.claims.checkpoint_id,
                            "after_sequence": after,
                        },
                    )
                )
                if (
                    page.stream_id,
                    page.observed_checkpoint_id,
                    page.observed_sequence,
                ) != (
                    scope.stream_id,
                    checkpoint.claims.checkpoint_id,
                    checkpoint.claims.sequence,
                ):
                    raise TaskBundleError("reader frozen boundary changed")
                cursor = after
                for jws in page.checkpoints:
                    cp = verify_checkpoint(jws, trust=audit_keys, expected_scope=scope)
                    if (
                        cp.claims.sequence <= cursor
                        or cp.claims.sequence > checkpoint.claims.sequence
                        or cp.claims.previous_checkpoint_digest != previous
                    ):
                        raise TaskBundleError("reader original history continuity mismatch")
                    raw = canonical_json_bytes({"checkpoint_jws": jws}) + b"\n"
                    size += len(raw)
                    count += 1
                    if len(raw) > 65536 or size > MAX_WIRE_BYTES or count > 100000:
                        raise TaskBundleError("reader history capacity exceeded")
                    out.write(raw)
                    previous, cursor, last = (
                        sm3_b64url(jws.encode("ascii")),
                        cp.claims.sequence,
                        jws,
                    )
                if cursor <= after:
                    raise TaskBundleError("reader history made no progress")
                if page.next_after_sequence is None:
                    if cursor != checkpoint.claims.sequence or last != latest:
                        raise TaskBundleError("reader original terminal missing")
                    break
                if page.next_after_sequence != cursor or cursor >= checkpoint.claims.sequence:
                    raise TaskBundleError("reader invalid next page")
                after = cursor
        with path.open("rb") as stream:
            history = load_checkpoint_history(
                stream,
                external_trust={"scope": scope, "audit_keys": audit_keys},
                external_pin=pin,
            )
        pin_path = directory / (path.stem + ".pin.json")
        pin_path.write_bytes(canonical_json_bytes(pin) + b"\n")
        return pin, history, pin_path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def public_task_trust(
    env, scope, registration, audit_keys, gateway_key, *, signing_kid="gw-receipt-1"
):
    from tests.fixtures.a32_common import public_trust_input
    from tests.fixtures.gateway import config_document

    registrations = {r.kid: r for r in env.registrations.values()}
    receipt = ReceiptTrust(
        ISSUER,
        {"as-sign-1": env.as_key.public_key()},
        {signing_kid: gateway_key.public_key()},
        {
            r.kid: env.keys[r.client_id.removeprefix("agent-")].public_key()
            for r in registrations.values()
        },
        registrations,
    )
    descriptor = asdict(registration)
    descriptor.pop("scope")
    return public_trust_input(
        {"receipt_trust": receipt},
        {"scope": scope, "external_trust": {"audit_keys": audit_keys}},
        registration=descriptor,
        catalog=config_document(env)["catalog"],
    )


def exact_host_certificates(directory, hostname):
    """A private CA and exactly one DNS SAN, with raw OpenSSL command receipts."""
    import os
    import subprocess

    directory.mkdir(mode=0o700)
    commands = [
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(directory / "ca.key"),
            "-out",
            str(directory / "ca.pem"),
            "-days",
            "2",
            "-subj",
            "/CN=A32 private test CA",
        ],
        [
            "openssl",
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(directory / "server.key"),
            "-out",
            str(directory / "server.csr"),
            "-subj",
            "/CN=" + hostname,
        ],
    ]
    (directory / "ext").write_text(
        "subjectAltName=DNS:" + hostname + "\nextendedKeyUsage=serverAuth\n"
    )
    commands.append(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(directory / "server.csr"),
            "-CA",
            str(directory / "ca.pem"),
            "-CAkey",
            str(directory / "ca.key"),
            "-CAcreateserial",
            "-out",
            str(directory / "server.pem"),
            "-days",
            "2",
            "-extfile",
            str(directory / "ext"),
        ]
    )
    for index, command in enumerate(commands):
        result = subprocess.run(command, capture_output=True, timeout=30)
        (directory / (str(index) + ".stdout")).write_bytes(result.stdout)
        (directory / (str(index) + ".stderr")).write_bytes(result.stderr)
        (directory / (str(index) + ".exit")).write_text(str(result.returncode))
        assert result.returncode == 0
    for path in directory.iterdir():
        os.chmod(path, 0o600)


def count_original_capacity(archive_path, archive_sha256, evidence_dir):
    """Encode unchanged native originals; this is neither PG export nor AUDIT delivery."""
    import datetime
    import gc
    import hashlib
    import json
    import time
    import uuid
    from collections import Counter
    from dataclasses import asdict
    from pathlib import Path

    from agent_guard.audit.checkpoint import sign_checkpoint
    from agent_guard.audit.contracts import (
        JournalScope,
        decode_journal_record,
        encode_append_batch,
        utc_text,
    )
    from agent_guard.contracts.encoding import (
        b64url_decode,
        canonical_json_bytes,
        load_strict_json,
    )
    from agent_guard.contracts.ledger_changes import (
        canonical_ledger_changes_bytes,
        load_ledger_changes,
    )
    from agent_guard.crypto.sm import generate_sm2_private_key, sm3_b64url
    from agent_guard.evidence import export as ex
    from agent_guard.evidence import task_bundle as codec

    E = Path(evidence_dir)
    A = Path(archive_path)
    start = time.monotonic()
    expected = archive_sha256
    h = hashlib.sha256()
    with A.open("rb") as f:
        while b := f.read(1048576):
            h.update(b)
    assert h.hexdigest() == expected
    whole = json.loads(A.read_text())
    gateway = whole["state"]["gateway"]
    needed = (
        "ag_audit_streams",
        "ag_audit_bootstrap",
        "ag_audit_bootstrap_chunks",
        "ag_audit_records",
        "ag_verified_evidence",
        "ag_operations",
        "ag_receipt_outbox",
        "ag_grants",
    )
    tables = {}
    for table in needed:
        rows = []
        for item in gateway[table]:
            assert len(item) == 1
            row = json.loads(item[0])
            for k, v in row.items():
                if isinstance(v, str) and v.startswith("\\x"):
                    row[k] = bytes.fromhex(v[2:])
                elif k in ("created_at", "accepted_at", "recorded_at") and isinstance(v, str):
                    row[k] = datetime.datetime.fromisoformat(v)
            rows.append(row)
        tables[table] = rows
        del gateway[table]
    del whole, gateway
    gc.collect()
    index = {
        name: {row[key]: row for row in tables[name]}
        for name, key in [
            ("ag_verified_evidence", "evidence_ref"),
            ("ag_operations", "operation_id"),
            ("ag_receipt_outbox", "operation_id"),
            ("ag_grants", "grant_id"),
        ]
    }
    stream = tables["ag_audit_streams"][0]
    scope = JournalScope(
        *(stream[k] for k in ("gateway_id", "tenant_id", "task_id", "stream_id", "epoch"))
    )
    records = sorted(tables["ag_audit_records"], key=lambda r: r["seq"])
    assert len(records) == 30009 and len(index["ag_operations"]) == 10000
    # Original delivery uses max64 candidates and maximum legal prefix under exact65536 body.
    ends = []
    batches = []
    at = 0
    while at < len(records):
        selected = []
        batch = None
        for row in records[at : at + 64]:
            candidate = tuple(selected + [row["raw"]])
            try:
                next_batch = encode_append_batch(scope.stream_id, candidate)
            except ValueError:
                assert selected
                break
            selected.append(row["raw"])
            batch = next_batch
        assert batch is not None
        batches.append(
            {
                "start": batch.start_sequence,
                "end": batch.end_sequence,
                "body_bytes": len(batch.exact_body),
                "body_sha256": hashlib.sha256(batch.exact_body).hexdigest(),
                "batch_id": batch.batch_id,
            }
        )
        ends.append(records[at + len(selected) - 1])
        at += len(selected)
    key = generate_sm2_private_key()
    previous = None
    cp_rows = []
    with (E / "fixed-batch-local-signed-history.ndjson").open("xb") as out:
        for row in ends:
            jws = sign_checkpoint(
                {
                    **asdict(scope),
                    "profile": "GM-MVP-1",
                    "checkpoint_version": "AG-CHECKPOINT-1",
                    "checkpoint_id": str(uuid.uuid4()),
                    "sequence": row["seq"],
                    "head_digest": row["digest"],
                    "previous_checkpoint_digest": previous,
                    "issued_at": utc_text(datetime.datetime.now(datetime.timezone.utc)),
                    "kid": "capacity-count-local",
                },
                private_key=key,
                key_id="capacity-count-local",
            )
            previous = sm3_b64url(jws.encode("ascii"))
            cp_rows.append(jws)
            out.write(canonical_json_bytes({"checkpoint_jws": jws}) + b"\n")
    (E / "legal-batch-originals.json").write_text(
        json.dumps(
            {
                "kind": (
                    "EXACT_NATIVE_ENCODE_APPEND_BATCH_PREFIX_FROM_ORIGINAL_RAW_RECORDS_"
                    "NOT_NETWORK_DELIVERY"
                ),
                "max_entries": 64,
                "max_body_bytes": 65536,
                "batches": batches,
            },
            indent=2,
        )
    )

    class Rows:
        def __init__(self, value):
            self.value = value

        def fetchone(self):
            return self.value

    class ArchiveReader:
        def execute(self, sql, args):
            if sql.startswith("SELECT token_bytes,proof_bytes,body_bytes"):
                row = index["ag_verified_evidence"][args[0]]
                assert row["tenant_id"] == args[1] and row["task_id"] == args[2]
                return Rows(
                    tuple(
                        row[k]
                        for k in (
                            "token_bytes",
                            "proof_bytes",
                            "body_bytes",
                            "token_sm3",
                            "proof_sm3",
                            "body_sm3",
                        )
                    )
                )
            if sql.startswith("SELECT o.grant_id,g.root_grant_id"):
                row = index["ag_operations"][args[0]]
                assert row["tenant_id"] == args[1] and row["task_id"] == args[2]
                grant = index["ag_grants"][row["grant_id"]]
                return Rows(
                    tuple(
                        [row["grant_id"], grant["root_grant_id"]]
                        + [
                            row[k]
                            for k in (
                                "amount_fen",
                                "calls",
                                "currency",
                                "quote_id",
                                "quote_version",
                                "quote_snapshot",
                                "accepted_at",
                            )
                        ]
                    )
                )
            row = index["ag_receipt_outbox"][args[0]]
            if sql.startswith("SELECT receipt_jws FROM"):
                return Rows((row["receipt_jws"],))
            if sql.startswith("SELECT result_bytes,receipt_jws FROM"):
                return Rows((row["result_bytes"], row["receipt_jws"]))
            raise AssertionError(sql)

    class ExactCounter:
        def __init__(self):
            self.members = {}
            self.raw_bytes = 0
            self.kind_counts = Counter()
            self.chunk_bytes = 0
            self.chunks = 0
            self.first_raw_cap = None
            self.first_object_cap = None
            self.source = None

        def add(self, kind, owner, ident, component, raw, ordinal=0):
            raw = bytes(raw)
            assert 1 <= len(raw) <= codec.OBJECT_LIMITS[kind]
            key = (kind, codec.object_id(kind, owner, ident, component, ordinal))
            ref = {"component": component, "object_kind": kind, "object_id": key[1]}
            if key in self.members:
                assert self.members[key] == raw
                return ref
            self.raw_bytes += len(raw)
            number = len(self.members) + 1
            event = {
                "object_number": number,
                "raw_bytes_including_new": self.raw_bytes,
                "kind": kind,
                "owner": owner,
                "component": component,
                "id": ident,
                "source": self.source,
            }
            if self.raw_bytes > codec.MAX_WIRE_BYTES and self.first_raw_cap is None:
                self.first_raw_cap = event.copy()
            if len(self.members) >= codec.MAX_OBJECTS and self.first_object_cap is None:
                self.first_object_cap = event.copy()
            self.members[key] = raw
            self.kind_counts[kind] += 1
            for frame in codec.encode_object_chunks(kind, key[1], raw):
                self.chunks += 1
                self.chunk_bytes += len(frame)
            return ref

    c = ExactCounter()
    bootstrap = tables["ag_audit_bootstrap"][0]
    for part in ("manifest", "schema_lineage"):
        c.add(
            "typed_snapshot_metadata",
            "bootstrap",
            part,
            part,
            bootstrap[part + "_bytes"],
        )
    groups = {}
    bootstrap_grant_ids = set()
    first_paths_checked = 0
    for row in tables["ag_audit_bootstrap_chunks"]:
        groups.setdefault((row["object_kind"], row["object_id"]), []).append(row)
    for (kind, ident), parts in sorted(groups.items()):
        parts.sort(key=lambda r: r["chunk_index"])
        raw = b"".join(r["raw"] for r in parts)
        assert (
            len(raw) == parts[0]["total_raw_bytes"] and sm3_b64url(raw) == parts[0]["object_digest"]
        )
        c.add(kind, "bootstrap", ident, ident, raw)
        if kind == "typed_snapshot_metadata":
            metadata = load_strict_json(raw)
            if metadata.get("table") == "ag_grants":
                bootstrap_grant_ids.add(metadata["columns"]["grant_id"])
    reader = ArchiveReader()
    previous = stream["genesis_digest"]
    statuses = Counter()
    for row in records:
        record = decode_journal_record(row["raw"])
        assert (
            record.scope == scope
            and record.previous_digest == previous
            and record.digest == row["digest"]
        )
        previous = record.digest
        statuses[record.kind] += 1
        if record.kind == "FIRST":
            original_facts = load_strict_json(record.facts_bytes)
            assert original_facts["path_ids"]
            assert all(ident in bootstrap_grant_ids for ident in original_facts["path_ids"])
            first_paths_checked += 1
        c.source = {"journal_seq": record.seq, "kind": record.kind}
        c.add("journal", "journal", str(record.seq), "journal", row["raw"])
        if record.kind != "TERMINAL":
            refs = ex._record_material(reader, record, row["material_binding_bytes"], c)
        else:
            # Independent arithmetic projection of exact persisted immutable original bytes.
            out = index["ag_receipt_outbox"][record.operation_id]
            material = ex.decode_material_projection(record.kind, row["material_binding_bytes"])
            facts = load_strict_json(record.facts_bytes)
            metadata = {k: out[k] for k in ex._PENDING_FIELDS}
            metadata["created_at"] = utc_text(metadata["created_at"])
            internal = out["ledger_changes_json"]
            result = out["result_bytes"]
            assert internal == b64url_decode(material["ledger"]) and result == b64url_decode(
                material["result"]
            )
            ledger = load_ledger_changes(internal, internal=True)
            public = canonical_ledger_changes_bytes(
                {
                    "operation_id": ledger["operation_id"],
                    "events": [
                        {"phase": x["phase"], "nodes": x["nodes"]} for x in ledger["events"]
                    ],
                }
            )
            pending = {
                **metadata,
                "ledger_changes_json": ex.b64url_encode(internal),
                "result_bytes": ex.b64url_encode(result),
            }
            assert (
                sm3_b64url(ex.rfc8785.dumps(pending)) == facts["pending_receipt_digest"]
                and sm3_b64url(public) == facts["ledger_digest"]
                and sm3_b64url(result) == facts["result_digest"]
            )
            metadata["metadata_profile"] = "AG-TASK-PENDING-RECEIPT-1"
            refs = [
                c.add(kind, "operation", record.operation_id, component, raw)
                for kind, component, raw in [
                    (
                        "typed_snapshot_metadata",
                        "pending_receipt_metadata",
                        canonical_json_bytes(metadata),
                    ),
                    ("ledger", "internal_ledger", internal),
                    ("ledger", "ledger", public),
                    ("result", "result", result),
                ]
            ]
        assert len(refs) <= 16
        c.add(
            "typed_snapshot_metadata",
            "journal",
            str(record.seq),
            "refs",
            canonical_json_bytes(
                {
                    "metadata_profile": "AG-TASK-REFS-1",
                    "record_seq": record.seq,
                    "operation_id": record.operation_id,
                    "evidence_ref": record.evidence_ref,
                    "refs": refs,
                }
            ),
        )
    assert previous == stream["head_digest"]
    c.source = {"phase": "fixed-batch-local-signed-checkpoints"}
    for jws in cp_rows:
        claim = ex._checkpoint(jws)
        c.add(
            "checkpoint",
            "checkpoint",
            claim.checkpoint_id,
            "checkpoint",
            jws.encode("ascii"),
        )
    c.source = {"phase": "original-runtime-observations"}
    for ident, row in sorted(index["ag_operations"].items()):
        c.add(
            "typed_snapshot_metadata",
            "runtime",
            ident,
            "runtime",
            canonical_json_bytes(
                {
                    "metadata_profile": "AG-TASK-RUNTIME-OBSERVATION-1",
                    "operation_id": ident,
                    "status": row["status"],
                    "receipt_status": index["ag_receipt_outbox"][ident]["receipt_status"],
                }
            ),
        )
    header = {
        "frame_type": "HEADER",
        "manifest_version": "AG-TASK-EVIDENCE-2",
        "scope": asdict(scope),
        "cutoff_sequence": stream["head_seq"],
        "cutoff_head_digest": stream["head_digest"],
        "snapshot_as_of": int(time.time()),
        "snapshot_id": "1:1:",
        "history_boundary": bootstrap["boundary"],
        "bootstrap_digest": stream["bootstrap_digest"],
        "object_count": len(c.members),
        "chunk_count": c.chunks,
        "journal_count": len(records),
        "operation_count": len(index["ag_operations"]),
    }
    header_size = len(canonical_json_bytes(header)) + 1
    before = header_size + c.chunk_bytes
    footer = {
        "frame_type": "FOOTER",
        "object_index_root": codec.index_seed(scope),
        "wire_root": codec.wire_seed(scope),
        "before_footer_frames": 1 + c.chunks,
        "before_footer_wire_bytes": before,
    }
    footer_size = len(canonical_json_bytes(footer)) + 1
    report = {
        "kind": (
            "INDEPENDENT_EXACT_ENCODING_PREFLIGHT_ORIGINAL_IMMUTABLE_NATIVE_ROWS_"
            "NOT_NATIVE_PG_EXPORT_NOT_FULLBUDGET_PASS"
        ),
        "archive_sha256": expected,
        "native_operations": 10000,
        "qualified_nonempty_bootstrap_guard_reuse": {
            "first_records_checked": first_paths_checked,
            "all_first_paths_nonempty_and_in_immutable_bootstrap": first_paths_checked == 10000,
            "bootstrap_grant_ids": sorted(bootstrap_grant_ids),
            "changed_condition": "if all(...) -> if grants and all(...)",
        },
        "journal": len(records),
        "journal_kinds": dict(statuses),
        "fixed_legal_batches": len(batches),
        "checkpoint_source": (
            "new local-SM2 capacity fixture over unchanged original journal; "
            "not AUDIT TLS observation"
        ),
        "objects": len(c.members),
        "kind_counts": dict(c.kind_counts),
        "raw_bytes": c.raw_bytes,
        "chunks": c.chunks,
        "frames": c.chunks + 2,
        "exact_object_chunk_wire_bytes": c.chunk_bytes,
        "representative_valid_header": header,
        "header_bytes": header_size,
        "footer_bytes": footer_size,
        "whole_wire_bytes_for_declared_header": before + footer_size,
        "header_snapshot_id_is_mathematical_example_not_PG_export": True,
        "footer_roots_are_length_only_seed_placeholders_not_valid_bundle": True,
        "terminal_material_is_original_row_arithmetic_not_new_PG_project_receipt": True,
        "first_raw_cap_exceeded": c.first_raw_cap,
        "first_object_cap_exceeded": c.first_object_cap,
        "object_cap": codec.MAX_OBJECTS,
        "raw_and_wire_cap": codec.MAX_WIRE_BYTES,
        "elapsed": time.monotonic() - start,
        "acceptance": "NOT_ASSERTED",
    }
    (E / "exact-original-encoding-counts.json").write_text(json.dumps(report, indent=2))
    return report
