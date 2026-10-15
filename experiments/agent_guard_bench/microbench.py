"""Independent real crypto, database trace and verified TLS reference measurements."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from tongsuopy.crypto.asymciphers import ec
from tongsuopy.crypto.asymciphers.utils import encode_dss_signature

from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.crypto.sm import (
    SM2_USER_ID,
    InvalidSm2Signature,
    serialize_sm2_public_key,
    sign_compact_jws,
    sign_sm2_message,
    sm3_digest,
    verify_compact_jws,
    verify_sm2_message,
)

from .statistics import distribution

MEASURED = 1000
WARMUP = 50
# Public synthetic benchmark key, NEVER a deployment key. Fixed across repeats.
BENCHMARK_SCALAR = int("3945208F7B213123ACD1BEB0BF65A9CA5F5FCFCAC79C925E5B5A64EB5C1071D6", 16)
BENCHMARK_BODY = canonical_json_bytes(
    {
        "profile": "GM-MVP-1",
        "task_id": "microbench-synthetic",
        "tool_id": "procurement.order.create",
        "tool_version": "1",
        "idempotency_key": "microbench-fixed",
        "params": {
            "request_id": "req.microbench",
            "quote_id": "quote.microbench",
            "quote_version": "1",
            "items": [{"sku": "sku-001", "quantity": 1}],
            "delivery_id": "delivery.microbench",
        },
    }
)


def _measure(operation):
    warm, samples = [], []
    for i in range(WARMUP + MEASURED):
        start = time.monotonic_ns()
        operation()
        end = time.monotonic_ns()
        (warm if i < WARMUP else samples).append({"start_ns": start, "end_ns": end})
    return {
        "warmup_n": len(warm),
        "measured_n": len(samples),
        "warmup": warm,
        "raw": samples,
        "latency": distribution(r["end_ns"] - r["start_ns"] for r in samples),
    }


def run_real_crypto_microbenchmark(*, out_path=None):
    """Run mature Tongsuo primitives, fixed profile/key/body/three-link JWS chain."""
    key = ec.derive_private_key(BENCHMARK_SCALAR, ec.SM2())
    public = key.public_key()
    signature = sign_sm2_message(key, BENCHMARK_BODY)
    verify_sm2_message(public, BENCHMARK_BODY, signature)
    expected = "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
    if sm3_digest(b"abc").hex() != expected:
        raise AssertionError("SM3 standard vector mismatch")
    vector_public = ec.EllipticCurvePublicNumbers(
        int("09F9DF311E5421A150DD7D161E4BC5C672179FAD1833FC076BB08FF356F35020", 16),
        int("CCEA490CE26775A52DC6EA718CC1AA600AED05FBF35E084A6632F6072DA9AD13", 16),
        ec.SM2(),
    ).public_key()
    verify_sm2_message(
        vector_public,
        b"message digest",
        encode_dss_signature(
            int("F5A03B0648D2C4630EEAC513E1BB81A15944DA3827D5B74143AC7EACEEE720B3", 16),
            int("B1B6AA29DF212FD8763182BC0D421CA1BB9038FD1F7F42D4840B69C485BBC1AA", 16),
        ),
    )
    negative = []
    for message, candidate in (
        (BENCHMARK_BODY + b"!", signature),
        (BENCHMARK_BODY, b"bad"),
    ):
        try:
            verify_sm2_message(public, message, candidate)
        except InvalidSm2Signature:
            negative.append("REJECTED")
        else:
            raise AssertionError("invalid SM2 input accepted")
    chain = [
        sign_compact_jws(
            key,
            {
                "profile": "GM-MVP-1",
                "depth": depth,
                "parent": None if depth == 0 else str(depth - 1),
                "body_hash": sm3_digest(BENCHMARK_BODY).hex(),
            },
            key_id="synthetic-benchmark",
            token_type="ag-at+jwt",
        )
        for depth in range(3)
    ]
    for token in chain:
        verify_compact_jws(
            token,
            expected_type="ag-at+jwt",
            trusted_keys={"synthetic-benchmark": public},
        )
    interop = _openssl_profile_control(key, signature, BENCHMARK_BODY)
    measurements = {
        "SM2sign": _measure(lambda: sign_sm2_message(key, BENCHMARK_BODY)),
        "SM2verify": _measure(lambda: verify_sm2_message(public, BENCHMARK_BODY, signature)),
        "SM3": _measure(lambda: sm3_digest(BENCHMARK_BODY)),
        "chain3verify": _measure(
            lambda: [
                verify_compact_jws(
                    t,
                    expected_type="ag-at+jwt",
                    trusted_keys={"synthetic-benchmark": public},
                )
                for t in chain
            ]
        ),
    }
    result = {
        "status": "REAL_CRYPTO_MEASURED",
        "model": "N/A",
        "profile": "GM-MVP-1",
        "SM2_user_id_ascii": SM2_USER_ID.decode(),
        "key_usage": "PUBLIC_SYNTHETIC_BENCHMARK_ONLY",
        "key_public_sha256": hashlib.sha256(serialize_sm2_public_key(public)).hexdigest(),
        "body_bytes": len(BENCHMARK_BODY),
        "body_sha256": hashlib.sha256(BENCHMARK_BODY).hexdigest(),
        "chain_length": 3,
        "library": "tongsuopy",
        "version": importlib.metadata.version("tongsuopy"),
        "module": sys.modules[sign_sm2_message.__module__].__file__,
        "python": sys.version,
        "OpenSSL_profile_control": interop,
        "vectors": {
            "SM3_abc": "VERIFIED",
            "SM2_published": "VERIFIED",
            "negative": negative,
        },
        "measurements": measurements,
        "limitations": "Isolated primitives and fixed chain; "
        "no DB or exact network cost decomposition.",
    }
    if out_path is not None:
        Path(out_path).write_text(json.dumps(result, indent=2))
    return result


class TracedConnection:
    """Log the actual supplied connection without adding SQL after final clock."""

    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def execute(self, query, params=None):
        start = time.monotonic_ns()
        error = None
        try:
            return self.connection.execute(query, params)
        except Exception as exc:
            error = type(exc).__name__
            raise
        finally:
            self.rows.append(
                {
                    "query_sha256": hashlib.sha256(str(query).encode()).hexdigest(),
                    "start_ns": start,
                    "end_ns": time.monotonic_ns(),
                    "error": error,
                }
            )


def run_independent_database_trace(connection_factory, operation, *, out_path=None):
    """Independent owned real connection; operation uses this traced connection.

    Final backend clock is deliberately the last SQL statement. Monitoring is
    sampled before it and never presented as the business transaction's exact
    lock duration. This measurement is excluded from official attempts.
    """
    start = time.monotonic_ns()
    with connection_factory() as connection:
        opened = time.monotonic_ns()
        traced = TracedConnection(connection)
        with connection.transaction():
            before = traced.execute("SELECT pg_backend_pid(),clock_timestamp()").fetchone()
            result = operation(traced)
            waits = traced.execute(
                "SELECT pid,wait_event_type,wait_event,state FROM pg_stat_activity "
                "WHERE pid=pg_backend_pid()"
            ).fetchall()
            locks = traced.execute(
                "SELECT locktype,mode,granted FROM pg_locks WHERE pid=pg_backend_pid()"
            ).fetchall()
            final = traced.execute("SELECT clock_timestamp()").fetchone()[0]
        closed = time.monotonic_ns()
    value = {
        "kind": "INDEPENDENT_DB_TRACE",
        "official_attempts": 0,
        "connections": 1,
        "connection_start_ns": start,
        "connection_opened_ns": opened,
        "connection_closed_ns": closed,
        "backend_pid": before[0],
        "db_clock_before": before[1].isoformat(),
        "db_clock_final": final.isoformat(),
        "queries": traced.rows,
        "query_count": len(traced.rows),
        "locks": locks,
        "wait_samples": waits,
        "operation_result_type": type(result).__name__,
        "trace_overhead": "monotonic timestamps/hash per query; "
        "lock/wait queries are separate instrumentation",
        "limits": "One backend sampling point; no inferred exact business lock/wait segmentation.",
    }
    if out_path is not None:
        Path(out_path).write_text(json.dumps(value, indent=2, default=str))
    return value


def run_independent_tls_roundtrip_reference(*, url, ca_file, samples=1000, out_path=None):
    """CA/SAN checked empty GET. Reference only; never subtract from total latency."""
    if not url.startswith("https://") or type(samples) is not int or samples < 1:
        raise ValueError("verified HTTPS endpoint and positive samples required")
    context = ssl.create_default_context(cafile=str(ca_file))
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise ValueError("trusted CA and hostname verification required")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context)
    )
    rows = []
    for index in range(samples):
        start = time.monotonic_ns()
        status, error, size = None, None, 0
        try:
            with opener.open(urllib.request.Request(url, method="GET"), timeout=30) as response:
                status = response.status
                wire = response.read(65537)
                size = len(wire)
                if size > 65536:
                    raise ValueError("bounded TLS reference response required")
        except urllib.error.HTTPError as exc:
            status = exc.code
            with exc:
                size = len(exc.read(65537))
        except Exception as exc:
            error = type(exc).__name__
        rows.append(
            {
                "index": index,
                "start_ns": start,
                "end_ns": time.monotonic_ns(),
                "http_status": status,
                "error": error,
                "response_bytes": size,
            }
        )
    result = {
        "kind": "TLS_EMPTY_RTT_REFERENCE",
        "official_attempts": 0,
        "model": "N/A",
        "reuse_policy": "urllib opener; no asserted persistent reuse; "
        "CA and SAN verification enabled",
        "rows": rows,
        "latency": distribution(r["end_ns"] - r["start_ns"] for r in rows),
        "limits": "Reference endpoint RTT only; never an exact decomposition of business latency.",
    }
    if out_path is not None:
        Path(out_path).write_text(json.dumps(result, indent=2))
    return result


def collect_process_hardware():
    """Actual local/kernel measurements. Missing facilities remain explicit N/A."""
    result = {
        "observed_unix_ns": time.time_ns(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "python": sys.version,
        "logical_cpus": os.cpu_count(),
        "pid": os.getpid(),
        "translation": "N/A_NOT_OBSERVED",
    }
    for field, path in (
        ("cpuinfo", "/proc/cpuinfo"),
        ("memory", "/proc/meminfo"),
        ("process_status", "/proc/self/status"),
        ("cpu_quota", "/sys/fs/cgroup/cpu.max"),
        ("memory_ceiling", "/sys/fs/cgroup/memory.max"),
        ("memory_current", "/sys/fs/cgroup/memory.current"),
    ):
        p = Path(path)
        result[field] = p.read_text() if p.exists() else "N/A"
    if sys.platform == "darwin":
        p = subprocess.run(
            ["sysctl", "-n", "hw.memsize", "hw.ncpu", "sysctl.proc_translated"],
            capture_output=True,
        )
        result["darwin_sysctl"] = {
            "native_exit": p.returncode,
            "stdout": p.stdout.decode(),
            "stderr": p.stderr.decode(),
        }
    return result


def collect_database_storage(connection):
    """Actual settings and every non-system relation's heap/index/TOAST sizes."""
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        settings = connection.execute(
            "SELECT name,setting,unit FROM pg_settings WHERE name=ANY(%s) ORDER BY name",
            (
                [
                    "server_version",
                    "max_connections",
                    "shared_buffers",
                    "work_mem",
                    "maintenance_work_mem",
                    "effective_cache_size",
                    "synchronous_commit",
                    "fsync",
                    "full_page_writes",
                    "wal_level",
                ],
            ),
        ).fetchall()
        tables = connection.execute(
            "SELECT n.nspname,c.relname,c.reltuples::bigint,pg_relation_size(c.oid),"
            "pg_indexes_size(c.oid),pg_total_relation_size(c.oid),"
            "CASE WHEN c.reltoastrelid=0 THEN 0 ELSE pg_total_relation_size(c.reltoastrelid) END "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema') "
            "AND n.nspname NOT LIKE 'pg_toast%%' ORDER BY 1,2"
        ).fetchall()
        from psycopg import sql

        exact_rows = [
            {
                "schema": row[0],
                "table": row[1],
                "rows": connection.execute(
                    sql.SQL("SELECT count(*) FROM {}.{}").format(
                        sql.Identifier(row[0]), sql.Identifier(row[1])
                    )
                ).fetchone()[0],
            }
            for row in tables
        ]
        wal = connection.execute("SELECT wal_records,wal_fpi,wal_bytes FROM pg_stat_wal").fetchone()
        now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    return {
        "settings": settings,
        "relation_sizes": tables,
        "row_estimates_are_not_exact": True,
        "exact_rows": exact_rows,
        "WAL": wal,
        "db_clock": now.isoformat(),
    }


def _openssl_profile_control(key, signature, message):
    import tempfile

    from tongsuopy.crypto import serialization

    with tempfile.TemporaryDirectory(prefix="a34-real-openssl-") as directory:
        root = Path(directory)
        public = root / "synthetic-public.pem"
        public.write_bytes(
            key.public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )
        body, signed = root / "body", root / "signature.der"
        body.write_bytes(message)
        signed.write_bytes(signature)
        command = [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public),
            "-in",
            str(body),
            "-rawin",
            "-digest",
            "sm3",
            "-pkeyopt",
            "distid:" + SM2_USER_ID.decode(),
            "-sigfile",
            str(signed),
        ]
        positive = subprocess.run(command, capture_output=True, timeout=60)
        wrong = list(command)
        wrong[wrong.index("distid:" + SM2_USER_ID.decode())] = "distid:WRONG-USER-ID"
        negative = subprocess.run(wrong, capture_output=True, timeout=60)
        version = subprocess.run(["openssl", "version"], capture_output=True, timeout=60)
        if positive.returncode != 0 or negative.returncode == 0 or version.returncode != 0:
            raise AssertionError("independent OpenSSL SM2 fixed-user-ID control failed")
        return {
            "positive_native_exit": positive.returncode,
            "wrong_user_id_native_exit": negative.returncode,
            "version": version.stdout.decode().strip(),
            "wrong_user_id": "REJECTED",
            "signature_sha256": hashlib.sha256(signature).hexdigest(),
            "public_key_sha256": hashlib.sha256(public.read_bytes()).hexdigest(),
        }
