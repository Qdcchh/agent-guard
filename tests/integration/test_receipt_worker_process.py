"""Actual receipt_worker CLI PIDs, PG crash windows and complete effect oracles."""

import hashlib
import importlib.metadata
import json
import os
import platform
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import psycopg
import pytest

import agent_guard.gateway.receipt_worker as worker
from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.execution import store
from agent_guard.gateway.__main__ import init_config
from agent_guard.gateway.receipt_config import BOUNDS, load_receipt_worker_config
from agent_guard.server.__main__ import _public_pem
from agent_guard.server.private_files import private_directory
from tests.fixtures.gateway import config_document
from tests.fixtures.isolation import assert_owned
from tests.fixtures.receipts import CorruptRow, full_state, publication_only
from tests.integration.test_receipt_publication import final_env

pytestmark = pytest.mark.integration
ENTRY = [sys.executable, "-m", "agent_guard.gateway.receipt_worker"]


def cli_config(tmp_path, env, key):
    directory = tmp_path / "signer"
    document = config_document(env)
    value = {n: document[n] for n in ("issuer", "as_keys", "identities")}
    value.update(
        receipt_keys={"gw-receipt-1": _public_pem(key)},
        signing_kid="gw-receipt-1",
        private_key_path="key.pem",
    )
    value.update({n: default for n, (_, _, default) in BOUNDS.items()})
    from tongsuopy.crypto import serialization

    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    with private_directory(directory, create=True) as handle:
        handle.write_file("config.json", canonical_json_bytes(value))
        handle.write_file("key.pem", pem)
    return directory / "config.json"


def child_env(dsn=None):
    env = os.environ.copy()
    for name in (
        "AGENT_GUARD_DATABASE_URL",
        "AGENT_GUARD_DOWNSTREAM_DATABASE_URL",
        "AG_GATEWAY_DATABASE_URL",
        "AG_GATEWAY_DOWNSTREAM_DATABASE_URL",
        "DATABASE_URL",
        "PGHOST",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
        "AG_RECEIPT_DATABASE_URL",
    ):
        env.pop(name, None)
    if dsn is not None:
        env["AG_RECEIPT_DATABASE_URL"] = dsn
    return env


def provenance_env(tmp_path, dsn=None):
    """Test-only profiler observes loaded child code without altering product behavior."""
    bootstrap = tmp_path / "bootstrap"
    bootstrap.mkdir(exist_ok=True)
    output = Path(os.environ.get("A23_CLI_EVIDENCE", tmp_path))
    label = os.environ.get("A23_CLI_RUN_LABEL", "local")
    prefix = str(output / (label + "-actual-cli-"))
    program = (
        "import sys,os,json,hashlib,importlib.metadata,platform\n"
        "def observe(frame,event,arg):\n"
        " if event=='call' and frame.f_code.co_name=='main' and "
        "frame.f_code.co_filename.endswith('/gateway/receipt_worker.py'):\n"
        "  path=frame.f_globals['__file__']\n"
        "  value={'pid':os.getpid(),'parent_pid':os.getppid(),"
        "'python':platform.python_version(),'executable':sys.executable,"
        "'module':path,'module_sha256':hashlib.sha256(open(path,'rb').read()).hexdigest(),"
        "'distribution_version':importlib.metadata.version('agent-guard')}\n"
        f"  with open({prefix!r}+str(os.getpid())+'.json','w') as f: "
        "json.dump(value,f,indent=2)\n"
        "  sys.setprofile(None)\n"
        "sys.setprofile(observe)\n"
    )
    (bootstrap / "sitecustomize.py").write_text(program)
    env = child_env(dsn)
    env["PYTHONPATH"] = str(bootstrap) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def observe_process(process, label, tmp_path):
    """Linux procfs attests the real -m entry, not a publisher multiprocessing target."""
    value = {
        "pid": process.pid,
        "parent_pid": os.getpid(),
        "python": platform.python_version(),
        "entry": [sys.executable, "-m", "agent_guard.gateway.receipt_worker"],
        "module": worker.__file__,
        "module_sha256": hashlib.sha256(Path(worker.__file__).read_bytes()).hexdigest(),
        "distribution_version": importlib.metadata.version("agent-guard"),
    }
    root = Path(os.environ.get("A23_CLI_EVIDENCE", tmp_path))
    name = os.environ.get("A23_CLI_RUN_LABEL", "local")
    actual_path = root / f"{name}-actual-cli-{process.pid}.json"

    def attested():
        assert process.poll() is None
        try:
            return json.loads(actual_path.read_bytes())
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    actual = wait_until(attested)
    cmdline = Path(f"/proc/{process.pid}/cmdline").read_bytes().split(b"\0")
    assert b"-m" in cmdline and b"agent_guard.gateway.receipt_worker" in cmdline
    assert process.poll() is None
    assert actual["module"] == worker.__file__ and actual["pid"] == process.pid
    assert actual["module_sha256"] == value["module_sha256"]
    (root / f"{name}-{label}-{process.pid}.json").write_text(json.dumps(value, indent=2))
    return value


def kill_and_drain(process):
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=10)
    assert process.poll() is not None


def run_one(config, dsn, operation):
    process = subprocess.Popen(
        ENTRY + ["run", "--config", str(config), "--operation-id", operation],
        env=provenance_env(config.parent.parent, dsn),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr.decode()
        return process.pid, json.loads(stdout)
    finally:
        kill_and_drain(process)


def wait_until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.01)
    pytest.fail("owned CLI target condition did not become observable")


def test_real_sigkill_between_signature_and_commit(ledger, dsn, downstream_dsn, tmp_path):
    env, op, key, verifier, _ = final_env(dsn, downstream_dsn)
    config = cli_config(tmp_path, env, key)
    before = full_state(dsn, downstream_dsn)
    with psycopg.connect(dsn, autocommit=True) as blocker:
        blocker.execute("SELECT pg_advisory_lock(2387201)")
        with psycopg.connect(dsn) as setup:
            setup.execute(
                "CREATE FUNCTION cli_before_ready() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN IF NEW.receipt_status='READY' THEN PERFORM pg_advisory_xact_lock(2387201); "
                "END IF; RETURN NEW; END $$"
            )
            setup.execute(
                "CREATE TRIGGER cli_before_ready BEFORE UPDATE ON ag_receipt_outbox "
                "FOR EACH ROW EXECUTE FUNCTION cli_before_ready()"
            )
        process = subprocess.Popen(
            ENTRY + ["run", "--config", str(config), "--operation-id", op],
            env=provenance_env(config.parent.parent, dsn),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            observe_process(process, "sign-crash", tmp_path)

            def waiting():
                return blocker.execute(
                    "SELECT pid,query,wait_event_type,wait_event FROM pg_stat_activity "
                    "WHERE datname=current_database() AND wait_event='advisory' "
                    "AND query LIKE 'UPDATE ag_receipt_outbox SET receipt_status=%'"
                ).fetchone()

            observed = wait_until(waiting)
            assert observed[2:] == ("Lock", "advisory")
            assert "receipt_jws=" in observed[1] and "signed_at=clock_timestamp()" in observed[1]
            # Reaching the UPDATE trigger proves real sign and verify already completed.
            os.kill(process.pid, signal.SIGKILL)
            out, err = process.communicate(timeout=10)
            assert process.returncode == -signal.SIGKILL and out == b"" and err == b""
            assert full_state(dsn, downstream_dsn) == before
        finally:
            kill_and_drain(process)
            blocker.execute("SELECT pg_advisory_unlock(2387201)")
            with psycopg.connect(dsn) as setup:
                setup.execute("DROP TRIGGER cli_before_ready ON ag_receipt_outbox")
                setup.execute("DROP FUNCTION cli_before_ready()")
    pid, result = run_one(config, dsn, op)
    assert pid != process.pid and result["receipt_status"] == "READY"
    with psycopg.connect(dsn) as conn:
        saved = store.fetch_outbox(conn, op)
        verifier.verify_tx(conn, op, result["receipt_jws"])
    assert result["receipt_id"] == saved["receipt_id"]
    publication_only(before, full_state(dsn, downstream_dsn))


def test_real_commit_reply_loss_recovers_original_jws(ledger, dsn, downstream_dsn, tmp_path):
    env, op, key, verifier, _ = final_env(dsn, downstream_dsn)
    config = cli_config(tmp_path, env, key)
    before = full_state(dsn, downstream_dsn)
    reader, writer = os.pipe()
    os.set_blocking(writer, False)
    filler = 0
    while True:
        try:
            filler += os.write(writer, b"x" * 4096)
        except BlockingIOError:
            break
    assert filler > 0
    os.set_blocking(writer, True)
    process = subprocess.Popen(
        ENTRY + ["run", "--config", str(config), "--operation-id", op],
        env=provenance_env(config.parent.parent, dsn),
        stdout=writer,
        stderr=subprocess.PIPE,
    )
    os.close(writer)
    try:
        observe_process(process, "reply-loss", tmp_path)

        def committed():
            with psycopg.connect(dsn) as observer:
                row = store.fetch_outbox(observer, op)
                return row if row["receipt_status"] == "READY" else None

        saved = wait_until(committed)
        committed_state = full_state(dsn, downstream_dsn)
        assert process.poll() is None
        # No byte of the CLI reply can cross the full pipe. Independent DB
        # observation occurs first, then SIGKILL loses that actual stdout reply.
        assert wait_until(
            lambda: Path(f"/proc/{process.pid}/wchan").read_text().strip()
            in ("pipe_write", "anon_pipe_write")
        )
        os.kill(process.pid, signal.SIGKILL)
        process.communicate(timeout=10)
        assert process.returncode == -signal.SIGKILL
        lost = bytearray()
        while chunk := os.read(reader, 65536):
            lost.extend(chunk)
        assert bytes(lost) == b"x" * filler
        pid, result = run_one(config, dsn, op)
        assert pid != process.pid
        assert result["receipt_jws"] == saved["receipt_jws"]
        assert result["signed_at"] == saved["signed_at"].isoformat()
        assert result["receipt_id"] == saved["receipt_id"]
        with psycopg.connect(dsn) as conn:
            verifier.verify_tx(conn, op, result["receipt_jws"])
        assert full_state(dsn, downstream_dsn) == committed_state
        publication_only(before, committed_state)
    finally:
        os.close(reader)
        kill_and_drain(process)


def test_continuous_cli_bounded_bad_row_fairness_and_restart(ledger, dsn, downstream_dsn, tmp_path):
    env, first, key, verifier, _ = final_env(dsn, downstream_dsn)
    operations = [first]
    for i in (2, 3):
        accepted = env.adapter.accept(
            env.bundle(
                "cli-fairness-" + str(i),
                tool="procurement.request.read",
                params={"request_id": "req-001"},
            )
        )
        assert env.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
        operations.append(accepted.operation_id)
    with psycopg.connect(dsn) as conn:
        counters = conn.execute(
            "SELECT amount_reserved,amount_settled,calls_reserved,calls_settled "
            "FROM ag_grants ORDER BY depth"
        ).fetchall()
    assert counters == [(0, 70000, 0, 3)] * 3
    bad, *valid = sorted(operations)
    config = cli_config(tmp_path, env, key)
    value = json.loads(config.read_bytes())
    value.update(batch_size=1, poll_interval_ms=100)
    config.write_bytes(canonical_json_bytes(value))
    with CorruptRow(dsn, "ag_receipt_outbox", {"operation_id": bad}, {"receipt_id": "invalid"}):
        before = full_state(dsn, downstream_dsn)
        process = subprocess.Popen(
            ENTRY + ["run", "--config", str(config)],
            env=provenance_env(config.parent.parent, dsn),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            observe_process(process, "continuous", tmp_path)

            def ready():
                with psycopg.connect(dsn) as conn:
                    return all(
                        store.fetch_outbox(conn, op)["receipt_status"] == "READY" for op in valid
                    )

            wait_until(ready)
            assert process.poll() is None
            with psycopg.connect(dsn) as conn:
                out = store.fetch_outbox(conn, bad)
                assert (
                    out["receipt_status"] == "PENDING"
                    and out["receipt_jws"] is None
                    and out["signed_at"] is None
                )
                for op in valid:
                    verifier.verify_tx(conn, op, store.fetch_outbox(conn, op)["receipt_jws"])
            publication_only(before, full_state(dsn, downstream_dsn))
        finally:
            kill_and_drain(process)
    before = full_state(dsn, downstream_dsn)
    pid, result = run_one(config, dsn, bad)
    assert pid != process.pid and result["receipt_status"] == "READY"
    publication_only(before, full_state(dsn, downstream_dsn))


def test_cli_coherent_bad_quote_first_batch_one_keeps_serving_and_recovers(
    ledger, dsn, downstream_dsn, tmp_path, monkeypatch
):
    """Actual CLI skips the earliest invalid accepted quote, then retries restored facts."""
    import uuid
    from types import SimpleNamespace

    import agent_guard.ledger.service as ledger_module

    # Deterministic operation IDs only; all tokens, proofs and signatures are real.
    ids = iter(uuid.UUID(int=n) for n in (1, 2, 3))
    monkeypatch.setattr(ledger_module, "uuid", SimpleNamespace(uuid4=lambda: next(ids)))
    env, bad, key, verifier, _ = final_env(dsn, downstream_dsn)
    valid = []
    for i in (2, 3):
        accepted = env.adapter.accept(
            env.bundle(
                "coherent-cli-" + str(i),
                tool="procurement.request.read",
                params={"request_id": "req-001"},
            )
        )
        assert env.service.run_operation(accepted.operation_id).status == "SUCCEEDED"
        valid.append(accepted.operation_id)
    assert bad < min(valid)
    with psycopg.connect(dsn) as conn:
        original = store.fetch_outbox(conn, bad)
        quote = json.loads(bytes(store.fetch_operation(conn, bad).quote_snapshot))
        result = json.loads(original["result_bytes"])
    quote["items"][0]["unit_price_fen"] += 1
    result["items"][0]["unit_price_fen"] += 1
    assert quote["items"] == result["items"]
    assert sum(x["quantity"] * x["unit_price_fen"] for x in quote["items"]) != quote["total_fen"]
    config = cli_config(tmp_path, env, key)
    settings = json.loads(config.read_bytes())
    settings.update(batch_size=1, poll_interval_ms=100)
    config.write_bytes(canonical_json_bytes(settings))
    with (
        CorruptRow(
            dsn,
            "ag_operations",
            {"operation_id": bad},
            {"quote_snapshot": canonical_json_bytes(quote)},
        ),
        CorruptRow(
            dsn,
            "ag_receipt_outbox",
            {"operation_id": bad},
            {"result_bytes": canonical_json_bytes(result)},
        ),
    ):
        before = full_state(dsn, downstream_dsn)
        process = subprocess.Popen(
            ENTRY + ["run", "--config", str(config)],
            env=provenance_env(config.parent.parent, dsn),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            observe_process(process, "coherent-first-batch-one", tmp_path)

            def ready():
                with psycopg.connect(dsn) as conn:
                    return all(
                        store.fetch_outbox(conn, op)["receipt_status"] == "READY" for op in valid
                    )

            wait_until(ready)
            assert process.poll() is None
            with psycopg.connect(dsn) as conn:
                pending = store.fetch_outbox(conn, bad)
                assert (
                    pending["receipt_status"],
                    pending["receipt_jws"],
                    pending["signed_at"],
                ) == ("PENDING", None, None)
                assert (pending["receipt_id"], pending["created_at"]) == (
                    original["receipt_id"],
                    original["created_at"],
                )
                for op in valid:
                    verifier.verify_tx(conn, op, store.fetch_outbox(conn, op)["receipt_jws"])
            publication_only(before, full_state(dsn, downstream_dsn))
        finally:
            kill_and_drain(process)
    before = full_state(dsn, downstream_dsn)
    pid, recovered = run_one(config, dsn, bad)
    assert pid != process.pid and recovered["receipt_status"] == "READY"
    publication_only(before, full_state(dsn, downstream_dsn))


@pytest.mark.parametrize("umask", [0o0000, 0o0022, 0o0077, 0o0777])
def test_actual_cli_init_umask_safe_partial_failure(tmp_path, umask):
    old = tmp_path / "old"
    init_config(old)
    original = (old / "config.json").read_bytes()
    out = tmp_path / "new"
    result = subprocess.run(
        ENTRY + ["init", "--gateway-config", str(old / "config.json"), "--out", str(out)],
        preexec_fn=lambda: os.umask(umask),
        env=child_env(),
        capture_output=True,
        timeout=10,
    )
    assert (old / "config.json").read_bytes() == original
    assert b"PRIVATE KEY" not in result.stdout + result.stderr
    if umask == 0o0777:
        assert result.returncode == 2 and stat.S_IMODE(out.stat().st_mode) == 0
        out.chmod(0o700)  # owned empty directory cleanup only, after fail-closed assertion
        assert list(out.iterdir()) == []
    else:
        assert result.returncode == 0 and stat.S_IMODE(out.stat().st_mode) == 0o700
        assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in out.iterdir())
        assert load_receipt_worker_config(out / "config.json")


def test_actual_two_init_processes_exclusive_old_bytes_preserved(tmp_path):
    old = tmp_path / "old"
    init_config(old)
    original = (old / "config.json").read_bytes()
    gate_read, gate_write = os.pipe()
    code = (
        "import os,sys; os.read(int(sys.argv[1]),1); "
        "os.execv(sys.executable,[sys.executable,'-m',"
        "'agent_guard.gateway.receipt_worker']+sys.argv[2:])"
    )
    children = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                code,
                str(gate_read),
                "init",
                "--gateway-config",
                str(old / "config.json"),
                "--out",
                str(tmp_path / "new"),
            ],
            env=child_env(),
            pass_fds=(gate_read,),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    os.close(gate_read)
    try:
        os.write(gate_write, b"xx")
        replies = [child.communicate(timeout=15) for child in children]
        assert sorted(p.returncode for p in children) == [0, 2]
        assert len({p.pid for p in children}) == 2
        assert all(b"PRIVATE KEY" not in a + b for a, b in replies)
        assert (old / "config.json").read_bytes() == original
        new = tmp_path / "new"
        before = {p.name: p.read_bytes() for p in new.iterdir()}
        assert load_receipt_worker_config(new / "config.json")
        again = subprocess.run(
            ENTRY + ["init", "--gateway-config", str(old / "config.json"), "--out", str(new)],
            env=child_env(),
            capture_output=True,
            timeout=10,
        )
        assert again.returncode == 2 and before == {p.name: p.read_bytes() for p in new.iterdir()}
    finally:
        os.close(gate_write)
        for child in children:
            kill_and_drain(child)


def test_installed_wheel_cli_parent_child_provenance_and_readme(
    ledger, dsn, downstream_dsn, tmp_path
):
    old = tmp_path / "gateway"
    init_config(old)
    out = tmp_path / "receipt"
    commands = [
        ["init", "--gateway-config", str(old / "config.json"), "--out", str(out)],
        ["check", "--config", str(out / "config.json")],
        ["run", "--config", str(out / "config.json"), "--once"],
    ]
    for command in commands:
        result = subprocess.run(
            ENTRY + command, env=provenance_env(tmp_path, dsn), capture_output=True, timeout=15
        )
        assert result.returncode == 0, result.stderr.decode()
    env, op, key, _, _ = final_env(dsn, downstream_dsn)
    config = cli_config(tmp_path, env, key)
    pid, result = run_one(config, dsn, op)
    assert result["receipt_status"] == "READY" and pid != os.getpid()
    # Both runtimes must resolve the same actual module and distribution; wheel
    # mode has no source package on PYTHONPATH and no editable installation.
    program = (
        "import agent_guard.gateway.receipt_worker as w,importlib.metadata as m,json; "
        "print(json.dumps({'module':w.__file__,'version':m.version('agent-guard')}))"
    )
    probe = subprocess.run(
        [sys.executable, "-c", program], env=child_env(), capture_output=True, timeout=10
    )
    assert probe.returncode == 0
    origins = json.loads(probe.stdout)
    assert origins == {
        "module": worker.__file__,
        "version": importlib.metadata.version("agent-guard"),
    }
    if "site-packages" in worker.__file__:
        assert "/src/" not in worker.__file__
        direct = importlib.metadata.distribution("agent-guard").read_text("direct_url.json")
        assert direct is None or not json.loads(direct).get("dir_info", {}).get("editable", False)


def test_owned_child_processes_exit_and_test_target_marker(ledger, namespace, dsn, tmp_path):
    assert_owned(namespace)
    assert namespace.database == psycopg.conninfo.conninfo_to_dict(dsn)["dbname"]
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT current_database(),current_schema()").fetchone() == (
            namespace.database,
            namespace.schema,
        )
    old = tmp_path / "gateway"
    init_config(old)
    result = subprocess.run(
        ENTRY
        + ["init", "--gateway-config", str(old / "config.json"), "--out", str(tmp_path / "worker")],
        env=child_env(),
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0
    config = tmp_path / "worker/config.json"
    env = child_env()
    env.update(
        AGENT_GUARD_DATABASE_URL="postgresql://do-not-use/private-password@wrong-target/db",
        DATABASE_URL="postgresql://do-not-use/private-password@wrong-target/db",
    )
    for command, expected in (
        (["check", "--config", str(config)], 0),
        (["run", "--config", str(config), "--once"], 2),
    ):
        process = subprocess.Popen(
            ENTRY + command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == expected
        assert not Path(f"/proc/{process.pid}").exists()
        assert b"private-password" not in stdout + stderr and b"wrong-target" not in stdout + stderr
    for arguments in (
        ["run", "--config", "postgresql://private-password@wrong-target", "--unknown"],
        ["secret-token-invalid-command"],
        ["init", "--out", "PRIVATE KEY"],
    ):
        failure = subprocess.run(ENTRY + arguments, env=env, capture_output=True, timeout=10)
        assert failure.returncode == 2 and failure.stdout == b""
        assert failure.stderr == b"error: invalid receipt worker arguments\n"
    assert_owned(namespace)
