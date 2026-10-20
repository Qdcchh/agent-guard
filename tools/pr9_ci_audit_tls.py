"""Configure real TLS only on the explicitly owned, ephemeral CI audit service."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

LABEL = "agent-guard.pr9-owner"


def run(argv, *, input=None):
    result = subprocess.run(argv, input=input, capture_output=True, text=True, check=False)
    if result.returncode:
        # argv/output may contain transient configuration: keep errors non-secret.
        raise RuntimeError("CI audit TLS command failed: " + argv[0])
    return result.stdout


def owned(container, owner):
    if not re.fullmatch(r"[0-9a-f]{64}", container):
        raise ValueError("a full container ID is required")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", owner):
        raise ValueError("invalid owner")
    info = json.loads(run(["docker", "inspect", container]))
    if len(info) != 1 or info[0]["Id"] != container:
        raise ValueError("container identity differs")
    if info[0]["Config"].get("Labels", {}).get(LABEL) != owner:
        raise ValueError("container ownership differs")


def tls_dsn(base, ca):
    if "\n" in base or "\r" in base:
        raise ValueError("invalid database URL")
    parts = urlsplit(base)
    if parts.scheme not in {"postgres", "postgresql"} or not parts.hostname:
        raise ValueError("an explicit audit database URL is required")
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in {"sslmode", "sslrootcert"}]
    query.extend([("sslmode", "verify-full"), ("sslrootcert", str(ca))])
    return urlunsplit(parts._replace(query=urlencode(query)))


def prepare(*, container, owner, root, user, database, base_dsn, github_env=None):
    owned(container, owner)
    for value in (user, database):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", value):
            raise ValueError("invalid CI database identifier")
    audit_host = urlsplit(base_dsn).hostname
    if audit_host not in {"localhost", "127.0.0.1", "pg-audit.agent-guard.test"}:
        raise ValueError("unknown test audit host")
    root = Path(root).absolute()
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError("TLS root and its parents cannot be symlinks")
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    root.chmod(0o700)
    ca, ca_key = root / "ca.pem", root / "ca.key"
    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "2",
            "-keyout",
            str(ca_key),
            "-out",
            str(ca),
            "-subj",
            "/CN=PR9 ephemeral audit CA",
        ]
    )

    def issue_server(directory, subject_alt_name):
        server_key = directory / "server.key"
        request = directory / "server.csr"
        certificate = directory / "server.pem"
        extension = directory / "extensions.cnf"
        extension.write_text("subjectAltName=" + subject_alt_name + "\n")
        run(
            [
                "openssl",
                "req",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(server_key),
                "-out",
                str(request),
                "-subj",
                "/CN=localhost",
            ]
        )
        run(
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                str(request),
                "-CA",
                str(ca),
                "-CAkey",
                str(ca_key),
                "-CAcreateserial",
                "-out",
                str(certificate),
                "-days",
                "2",
                "-extfile",
                str(extension),
            ]
        )
        for item in directory.iterdir():
            if item.is_file():
                item.chmod(0o600)
        return server_key, certificate

    pg_names = "DNS:localhost,IP:127.0.0.1"
    if audit_host == "pg-audit.agent-guard.test":
        pg_names += ",DNS:pg-audit.agent-guard.test"
    key, cert = issue_server(root, pg_names)
    # Keep the HTTPS fixture's original wrong-IP SAN negative meaningful.
    delivery = root / "delivery"
    delivery.mkdir(mode=0o700)
    (delivery / "ca.pem").write_bytes(ca.read_bytes())
    _, delivery_cert = issue_server(delivery, "DNS:localhost")
    remote = "/tmp/pr9-audit-" + owner

    def docker(*args):
        owned(container, owner)
        return run(["docker", *args])

    docker(
        "exec",
        "--user",
        "0",
        container,
        "install",
        "-d",
        "-m",
        "700",
        "-o",
        "postgres",
        "-g",
        "postgres",
        remote,
    )
    for path in (ca, key, cert):
        docker("cp", str(path), container + ":" + remote + "/" + path.name)
    docker("exec", "--user", "0", container, "chown", "-R", "postgres:postgres", remote)
    docker(
        "exec",
        "--user",
        "0",
        container,
        "chmod",
        "600",
        *(remote + "/" + p.name for p in (ca, key, cert)),
    )
    psql = [
        "exec",
        "--user",
        "postgres",
        container,
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        user,
        "-d",
        database,
        "-At",
        "-c",
    ]
    for statement in (
        "ALTER SYSTEM SET ssl = 'on'",
        "ALTER SYSTEM SET ssl_cert_file = '" + remote + "/server.pem'",
        "ALTER SYSTEM SET ssl_key_file = '" + remote + "/server.key'",
        "SELECT pg_reload_conf()",
    ):
        docker(*psql, statement)
    # A fresh TCP connection must verify the generated CA and host, not just SHOW ssl.
    conninfo = (
        "host="
        + audit_host
        + " dbname="
        + database
        + " user="
        + user
        + " sslmode=verify-full sslrootcert="
        + remote
        + "/ca.pem"
    )
    proof = docker(
        "exec",
        "--user",
        "postgres",
        container,
        "sh",
        "-c",
        'PGPASSWORD="$POSTGRES_PASSWORD" exec psql "$@"',
        "sh",
        conninfo,
        "-X",
        "-At",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()",
    )
    if proof.strip() != "t":
        raise RuntimeError("audit TCP TLS verification failed")
    result = tls_dsn(base_dsn, ca.resolve())
    receipt = {
        "container_id": container,
        "owner": owner,
        "sslmode": "verify-full",
        "verified_tcp_tls": True,
        "ca": str(ca.resolve()),
        "ephemeral": True,
        "audit_host": audit_host,
        "tls_root": str(root),
        "ca_sha256": hashlib.sha256(ca.read_bytes()).hexdigest(),
        "server_certificate_sha256": hashlib.sha256(cert.read_bytes()).hexdigest(),
        "delivery_server_certificate_sha256": hashlib.sha256(
            delivery_cert.read_bytes()
        ).hexdigest(),
    }
    (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (root / "receipt.json").chmod(0o600)
    if github_env is not None:
        environment_file = Path(github_env)
        if environment_file.is_symlink():
            raise ValueError("CI environment file cannot be a symlink")
        with environment_file.open("a") as stream:
            stream.write("AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL=" + result + "\n")
            stream.write("PR9_A31_TLS_RECEIPT=" + str(root / "receipt.json") + "\n")
        environment_file.chmod(0o600)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container-id", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--tls-root", type=Path, required=True)
    parser.add_argument("--user", default="agent_guard_ci")
    parser.add_argument("--database", default="agent_guard_ci_audit")
    args = parser.parse_args(argv)
    os.umask(0o077)
    receipt = prepare(
        container=args.container_id,
        owner=args.owner,
        root=args.tls_root,
        user=args.user,
        database=args.database,
        base_dsn=os.environ["AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL"],
        github_env=os.environ.get("GITHUB_ENV"),
    )
    print(json.dumps(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
