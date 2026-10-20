"""Raw-preserving bounded streaming, independent original checkpoint history."""

import hashlib
from dataclasses import replace
from io import BytesIO

import pytest

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.evidence.task_bundle import (
    TaskBundleError,
    encode_object_chunks,
    iter_frames,
    load_checkpoint_history,
    object_id,
)
from agent_guard.gateway.evidence_auth import (
    authenticate_export,
    load_evidence_local_inputs,
    load_export_credentials,
)
from tests.fixtures.a32_common import checkpoint_material, encode_task


@pytest.mark.parametrize("length", [1, 16384, 24576, 24577, 49152, 65536])
def test_chunk_wire_bounds_exact_raw_reassembly(length):
    m = checkpoint_material()
    raw = b"x" * length
    ident = object_id("request", "evidence", "ev-1", "request")
    parts = list(encode_object_chunks("request", ident, raw))
    assert all(len(p) <= 65536 for p in parts)
    assert [
        len(
            __import__("agent_guard.contracts.encoding", fromlist=["b64url_decode"]).b64url_decode(
                load_strict_json(p[:-1])["data"]
            )
        )
        for p in parts
    ] == [min(24576, length - i) for i in range(0, length, 24576)]
    wire = encode_task(m["scope"], [("request", ident, raw)])
    assert len(list(iter_frames(BytesIO(wire)))) == len(parts) + 2
    assert load_strict_json(parts[0][:-1])["total_raw_bytes"] == length


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-footer",
        "extra",
        "crlf",
        "bom",
        "empty",
        "oversized-no-lf",
        "duplicate-header",
        "chunk-order",
        "digest",
        "count",
        "unknown",
        "noncanonical",
    ],
)
def test_strict_chunks_index_package_limits(mutation):
    m = checkpoint_material()
    wire = encode_task(m["scope"], [("request", "obj:test", b"x" * 65536)])
    lines = wire.splitlines(keepends=True)
    if mutation == "missing-footer":
        lines.pop()
    elif mutation == "extra":
        lines.append(b"{}\n")
    elif mutation == "crlf":
        lines[0] = lines[0][:-1] + b"\r\n"
    elif mutation == "bom":
        lines[0] = b"\xef\xbb\xbf" + lines[0]
    elif mutation == "empty":
        lines.insert(1, b"\n")
    elif mutation == "oversized-no-lf":
        lines = [b"x" * 65537]
    elif mutation == "duplicate-header":
        lines.insert(1, lines[0])
    elif mutation == "chunk-order":
        lines[1], lines[2] = lines[2], lines[1]
    elif mutation == "noncanonical":
        lines[0] = b" " + lines[0]
    else:
        frame = load_strict_json(lines[1][:-1])
        if mutation == "digest":
            frame["object_digest"] = load_strict_json(lines[0][:-1])["bootstrap_digest"]
        elif mutation == "count":
            frame["chunk_count"] = 4
        else:
            frame["new"] = 1
        lines[1] = canonical_json_bytes(frame) + b"\n"
    with pytest.raises(ValueError):
        list(iter_frames(BytesIO(b"".join(lines))))


@pytest.mark.parametrize("kind,limit", [("token", 16384), ("journal", 32768), ("request", 65536)])
def test_logical_object_limits_no_fake_split(kind, limit):
    assert list(encode_object_chunks(kind, "obj:1", b"x" * limit))
    with pytest.raises(TaskBundleError):
        list(encode_object_chunks(kind, "obj:1", b"x" * (limit + 1)))


@pytest.mark.parametrize("mode", ["LATEST_OBSERVATION", "MINIMUM", "UNKNOWN"])
def test_history_real_chain_pin_and_readonly_descriptor(tmp_path, mode):
    m = checkpoint_material(mode=mode)
    path = tmp_path / "history.ndjson"
    path.write_bytes(m["history_raw"])
    with path.open("rb") as stream:
        descriptor = load_checkpoint_history(
            stream, external_trust=m["external_trust"], external_pin=m["external_pin"]
        )
    assert descriptor.checkpoint_count == 3
    assert descriptor.last_sequence == 3
    assert descriptor.sha256 == hashlib.sha256(m["history_raw"]).hexdigest()
    with descriptor.open_readonly() as stream:
        assert stream.read() == m["history_raw"]
    path.write_bytes(m["history_raw"] + b"\n")
    with pytest.raises(TaskBundleError):
        with descriptor.open_readonly():
            pass


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "reorder",
        "duplicate",
        "wrong-scope",
        "bad-range",
        "bad-role",
        "changed-ascii",
        "no-lf",
        "unknown",
        "noncanonical",
        "empty",
        "rw-handle",
    ],
)
def test_history_rejects_original_chain_mutations(tmp_path, mutation):
    m = checkpoint_material()
    raw = m["history_raw"]
    lines = raw.splitlines(keepends=True)
    if mutation == "missing":
        lines.pop(1)
    elif mutation == "reorder":
        lines[0], lines[1] = lines[1], lines[0]
    elif mutation == "duplicate":
        lines.insert(1, lines[0])
    elif mutation == "wrong-scope":
        m["external_pin"]["scope"]["task_id"] = "other"
    elif mutation in {"bad-range", "bad-role"}:
        t = m["external_trust"]["audit_keys"][0]
        m["external_trust"]["audit_keys"] = (
            replace(t, first_sequence=4) if mutation == "bad-range" else replace(t, role="READER"),
        )
    elif mutation == "changed-ascii":
        value = load_strict_json(lines[0][:-1])
        value["checkpoint_jws"] += "A"
        lines[0] = canonical_json_bytes(value) + b"\n"
    elif mutation == "no-lf":
        lines[-1] = lines[-1][:-1]
    elif mutation == "unknown":
        value = load_strict_json(lines[0][:-1])
        value["unknown"] = 1
        lines[0] = canonical_json_bytes(value) + b"\n"
    elif mutation == "noncanonical":
        lines[0] = b" " + lines[0]
    elif mutation == "empty":
        lines = []
    path = tmp_path / "history.ndjson"
    path.write_bytes(b"".join(lines))
    with (
        path.open("r+b" if mutation == "rw-handle" else "rb") as stream,
        pytest.raises(ValueError),
    ):
        load_checkpoint_history(
            stream, external_trust=m["external_trust"], external_pin=m["external_pin"]
        )


def test_unknown_empty_history_and_replacement(tmp_path):
    m = checkpoint_material(sequences=(), mode="UNKNOWN")
    path = tmp_path / "history"
    path.write_bytes(b"")
    with path.open("rb") as stream:
        d = load_checkpoint_history(
            stream, external_trust=m["external_trust"], external_pin=m["external_pin"]
        )
    assert d.checkpoint_count == 0 and d.last_sequence == 0
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"")
    replacement.replace(path)
    with pytest.raises(TaskBundleError):
        with d.open_readonly():
            pass


def test_independent_export_auth_and_local_inputs(tmp_path):
    secret = "A" * 43
    creds = load_export_credentials(
        [
            {
                "credential_id": "export-1",
                "credential_sha256": hashlib.sha256(secret.encode()).hexdigest(),
                "tenant_id": "tenant-1",
                "task_ids": ["task-1"],
            }
        ]
    )
    assert authenticate_export("AGExport export-1:" + secret, "task-1", credentials=creds) == (
        "tenant-1",
        "task-1",
    )
    for header, task in [
        ("Bearer " + secret, "task-1"),
        ("AGExport other:" + secret, "task-1"),
        ("AGExport export-1:" + "B" * 43, "task-1"),
        ("AGExport export-1:" + secret, "task-2"),
    ]:
        with pytest.raises(ValueError):
            authenticate_export(header, task, credentials=creds)
    inputs = {
        "trust_file": str(tmp_path / "trust"),
        "external_pin_file": str(tmp_path / "pin"),
        "external_checkpoint_history_file": str(tmp_path / "history"),
    }
    for path in inputs.values():
        __import__("pathlib").Path(path).write_bytes(b"public-test-input")
    assert load_evidence_local_inputs(inputs).trust_file == inputs["trust_file"]
    for change in [
        {"external_checkpoint_history_file": "https://wrong/history"},
        {"trust_file": "relative"},
    ]:
        with pytest.raises(ValueError):
            load_evidence_local_inputs(inputs | change)


def test_export_init_private_independent_secret_and_old_routes(tmp_path, monkeypatch):
    from agent_guard.gateway.__main__ import init_config
    from agent_guard.gateway.config import (
        evidence_operator_inputs,
        load_gateway_config,
        load_gateway_secrets,
    )
    from agent_guard.gateway.factory import build_app

    directory = tmp_path / "operator"
    inputs = {
        "trust_file": str(tmp_path / "trust"),
        "external_pin_file": str(tmp_path / "pin"),
        "external_checkpoint_history_file": str(tmp_path / "history"),
    }
    for path in inputs.values():
        __import__("pathlib").Path(path).write_bytes(b"public-test-input")
    init_config(
        directory,
        export_credential_id="export-1",
        export_tenant_id="tenant-1",
        export_task_ids=["task-1"],
        evidence_local_inputs=inputs,
    )
    config = load_gateway_config((directory / "config.json").read_bytes())
    value = load_strict_json(config.raw)
    credentials, local = evidence_operator_inputs(value)
    secret = load_strict_json((directory / "export-credential.json").read_bytes())["secret"]
    assert authenticate_export(
        "AGExport export-1:" + secret, "task-1", credentials=credentials
    ) == ("tenant-1", "task-1")
    downstream = load_gateway_secrets((directory / "secrets.json").read_bytes())
    assert secret != downstream.downstream_secret
    assert directory.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in directory.iterdir())
    assert local.external_checkpoint_history_file == inputs["external_checkpoint_history_file"]
    from agent_guard.server.config import ConfigError

    with pytest.raises(
        ConfigError,
        match="independent SELECT-only export connection and private spool required",
    ):
        build_app(
            config,
            downstream,
            gateway_dsn="offline-check",
            downstream_dsn="offline-downstream",
        )
    old_value = {
        k: v for k, v in value.items() if k not in {"export_credentials", "evidence_local_inputs"}
    }
    old_config = load_gateway_config(canonical_json_bytes(old_value))
    app = build_app(
        old_config,
        downstream,
        gateway_dsn="offline-check",
        downstream_dsn="offline-downstream",
    )
    app._executor.shutdown()
    for field in ("export_credentials", "evidence_local_inputs"):
        changed = dict(value)
        changed.pop(field)
        with pytest.raises(ValueError):
            load_gateway_config(canonical_json_bytes(changed))


def test_stream_operation_count_and_default_codec_not_relaxed():
    from agent_guard.contracts.encoding import EncodingError
    from tests.fixtures.a32_common import task_header

    m = checkpoint_material()
    runtime = canonical_json_bytes(
        {
            "metadata_profile": "AG-TASK-RUNTIME-OBSERVATION-1",
            "operation_id": "operation-1",
            "status": "UNKNOWN",
            "receipt_status": None,
        }
    )
    ident = object_id("typed_snapshot_metadata", "runtime", "operation-1", "runtime")
    header = task_header(m["scope"], object_count=1, chunk_count=1, operation_count=1)
    wire = encode_task(m["scope"], [("typed_snapshot_metadata", ident, runtime)], header=header)
    assert len(list(iter_frames(BytesIO(wire)))) == 3
    header["operation_count"] = 0
    with pytest.raises(TaskBundleError):
        list(
            iter_frames(
                BytesIO(
                    encode_task(
                        m["scope"],
                        [("typed_snapshot_metadata", ident, runtime)],
                        header=header,
                    )
                )
            )
        )
    with pytest.raises(EncodingError):
        load_strict_json(b'"' + b"x" * 65536 + b'"')
    with pytest.raises(EncodingError):
        canonical_json_bytes([0] * 4096)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-chunk",
        "duplicate-chunk",
        "splice",
        "wrong-size",
        "encoded-overhead",
        "object-count",
        "journal-count",
        "object-index",
        "wire-root",
        "footer-count",
        "footer-bytes",
    ],
)
def test_strict_chunks_additional_exact_controls(mutation):
    m = checkpoint_material()
    lines = encode_task(m["scope"], [("request", "obj:test", b"x" * 65536)]).splitlines(
        keepends=True
    )
    if mutation == "missing-chunk":
        lines.pop(2)
    elif mutation == "duplicate-chunk":
        lines.insert(2, lines[1])
    else:
        index = (
            0
            if mutation in {"object-count", "journal-count"}
            else -1
            if mutation in {"object-index", "wire-root", "footer-count", "footer-bytes"}
            else 2
        )
        frame = load_strict_json(lines[index][:-1])
        if mutation == "splice":
            frame["object_id"] = "obj:other"
        elif mutation == "wrong-size":
            frame["data"] = frame["data"][:-4]
        elif mutation == "encoded-overhead":
            frame["data"] = "A" * 32769
        elif mutation == "object-count":
            frame["object_count"] += 1
        elif mutation == "journal-count":
            frame["journal_count"] = frame["cutoff_sequence"] = 1
        elif mutation == "object-index":
            frame["object_index_root"] = frame["wire_root"]
        elif mutation == "wire-root":
            frame["wire_root"] = frame["object_index_root"]
        elif mutation == "footer-count":
            frame["before_footer_frames"] += 1
        elif mutation == "footer-bytes":
            frame["before_footer_wire_bytes"] += 1
        lines[index] = canonical_json_bytes(frame) + b"\n"
    with pytest.raises(ValueError):
        list(iter_frames(BytesIO(b"".join(lines))))


def test_exact_lf_line_boundary_and_counter_capacity(monkeypatch):
    import agent_guard.evidence.task_bundle as codec

    raw = b'{"x":"' + b"a" * (65535 - 8) + b'"}\n'
    assert len(raw) == 65536
    assert len(list(codec._lines(BytesIO(raw)))) == 1
    with pytest.raises(ValueError):
        list(codec._lines(BytesIO(raw[:-3] + b'a"}\n')))
    assert (
        codec.MAX_WIRE_BYTES,
        codec.MAX_FRAMES,
        codec.MAX_OBJECTS,
        codec.MAX_JOURNAL,
        codec.MAX_OPERATIONS,
    ) == (268435456, 400000, 200000, 100000, 20000)
    m = checkpoint_material()
    wire = encode_task(m["scope"], [])
    monkeypatch.setattr(codec, "MAX_WIRE_BYTES", len(wire))
    assert len(list(iter_frames(BytesIO(wire)))) == 2
    monkeypatch.setattr(codec, "MAX_WIRE_BYTES", len(wire) - 1)
    with pytest.raises(TaskBundleError):
        list(iter_frames(BytesIO(wire)))
    monkeypatch.setattr(codec, "MAX_WIRE_BYTES", 268435456)
    monkeypatch.setattr(codec, "MAX_FRAMES", 1)
    with pytest.raises(TaskBundleError):
        list(iter_frames(BytesIO(wire)))


def test_local_history_file_missing_and_uniform_history_error(tmp_path):
    inputs = {
        "trust_file": str(tmp_path / "trust"),
        "external_pin_file": str(tmp_path / "pin"),
        "external_checkpoint_history_file": str(tmp_path / "history"),
    }
    for path in inputs.values():
        __import__("pathlib").Path(path).write_bytes(b"public")
    __import__("pathlib").Path(inputs["external_checkpoint_history_file"]).unlink()
    with pytest.raises(ValueError):
        load_evidence_local_inputs(inputs)
    m = checkpoint_material()
    path = tmp_path / "history"
    path.write_bytes(m["history_raw"])
    with (
        path.open("rb") as stream,
        pytest.raises(TaskBundleError, match="invalid external checkpoint history"),
    ):
        load_checkpoint_history(stream, external_trust={}, external_pin=m["external_pin"])


@pytest.mark.parametrize("dimension", ["objects", "journal", "operations", "wire"])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_real_global_codec_boundaries(tmp_path, dimension, offset):
    """Actual original global limits; codec framing is separate from legal signed business."""
    import json
    import os
    from pathlib import Path

    from agent_guard.audit.contracts import JournalScope
    from agent_guard.evidence import task_bundle as codec
    from tests.fixtures.a32_common import (
        exact_wire_codec_objects,
        write_codec_boundary_fixture,
    )

    scope = JournalScope(
        "https://gateway.agent-guard.test",
        "tenant-bound",
        "task-bound",
        "00000000-0000-4000-8000-000000000001",
        1,
    )
    limits = {
        "objects": 200000,
        "journal": 100000,
        "operations": 20000,
        "wire": 268435456,
    }
    value = limits[dimension] + offset
    if dimension == "wire":
        objects, counts, snapshot_id = exact_wire_codec_objects(scope, value)
    else:
        kind = {
            "objects": "request",
            "journal": "journal",
            "operations": "typed_snapshot_metadata",
        }[dimension]

        def originals():
            for number in range(value):
                material = b"x"
                if dimension == "operations":
                    material = canonical_json_bytes(
                        {
                            "metadata_profile": "AG-TASK-RUNTIME-OBSERVATION-1",
                            "operation_id": f"op:{number:06d}",
                            "status": "SUCCEEDED",
                            "receipt_status": "READY",
                        }
                    )
                yield kind, f"obj:{number:06d}", material

        objects = originals()
        counts = {
            "objects": min(value, codec.MAX_OBJECTS),
            "chunks": value,
            "journal": min(value, codec.MAX_JOURNAL) if dimension == "journal" else 0,
            "operations": min(value, codec.MAX_OPERATIONS) if dimension == "operations" else 0,
        }
        snapshot_id = "1:1:"
    path = tmp_path / "actual-codec.ndjson"
    measured = write_codec_boundary_fixture(
        path, scope, objects, counts=counts, snapshot_id=snapshot_id
    )
    if dimension == "wire":
        assert path.stat().st_size == value == measured["wire_bytes"]
    with path.open("rb") as stream:
        if offset <= 0:
            assert sum(1 for _ in codec.iter_frames(stream)) == measured["frames"]
        else:
            message = {
                "objects": "object count exceeded",
                "journal": "header object counts mismatch",
                "operations": "operation count exceeded",
                "wire": "task wire capacity exceeded",
            }[dimension]
            with pytest.raises(codec.TaskBundleError, match=message):
                for _ in codec.iter_frames(stream):
                    pass
    report = {
        "classification": "ACTUAL_CODEC_BOUNDARY_NOT_LEGAL_SIGNED_BUSINESS",
        "dimension": dimension,
        "offset": offset,
        "value": value,
        **measured,
    }
    evidence = os.environ.get("A31_TEST_EVIDENCE_DIR")
    if evidence:
        target = Path(evidence) / f"whole-boundary-{dimension}-{offset}.json"
        target.write_text(json.dumps(report, indent=2))


@pytest.mark.parametrize("value", [399999, 400000, 400001])
def test_real_frame_header_boundary_and_body_unreachability(value):
    """Header declaration gate is real; a full body at this threshold hits wire first."""
    from agent_guard.audit.contracts import JournalScope
    from agent_guard.crypto.sm import sm3_b64url
    from agent_guard.evidence import task_bundle as codec

    scope = JournalScope(
        "https://gateway.agent-guard.test",
        "tenant-bound",
        "task-bound",
        "00000000-0000-4000-8000-000000000001",
        1,
    )
    header = {
        "frame_type": "HEADER",
        "manifest_version": "AG-TASK-EVIDENCE-2",
        "scope": __import__("dataclasses").asdict(scope),
        "cutoff_sequence": 0,
        "cutoff_head_digest": sm3_b64url(b"head"),
        "snapshot_as_of": 1,
        "snapshot_id": "1:1:",
        "history_boundary": "NEW_EMPTY",
        "bootstrap_digest": sm3_b64url(b"bootstrap"),
        "object_count": 200000,
        "chunk_count": value,
        "journal_count": 0,
        "operation_count": 0,
    }
    stream = codec.iter_frames(BytesIO(canonical_json_bytes(header) + b"\n"))
    if value <= 400000:
        assert next(stream) == header
    else:
        with pytest.raises(ValueError, match="invalid audit integer"):
            next(stream)
    # Each extra frame for an object requires a full 24576-byte preceding chunk.
    required_full_chunks = max(0, value - 2 - codec.MAX_OBJECTS)
    actual_full_chunk = next(encode_object_chunks("request", "obj:1", b"x" * 24577))
    actual_b64_bytes = len(load_strict_json(actual_full_chunk[:-1])["data"])
    assert actual_b64_bytes == 32768
    assert required_full_chunks * actual_b64_bytes > codec.MAX_WIRE_BYTES
