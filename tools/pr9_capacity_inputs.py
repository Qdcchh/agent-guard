"""Private relocation of immutable PR9 capacity evidence; never generates business results."""

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path, PurePosixPath

if __package__:
    from tools import pr9_capacity_transport as transport
else:
    import pr9_capacity_transport as transport

PUBLIC_INPUT_ROOT = Path(__file__).resolve().parents[1] / "dependencies/pr9-capacity"
PUBLIC_MANIFEST_SHA256 = "844112ac00709241817b4bf8b48969e3e977810772c65c070c0811cf353fae9d"
PUBLIC_TRANSPORT_SHA256 = "00d6a155297e428e5f0109ffc9c68966c52b6cdac787222dc5643a580a91d2a4"


def binding_identity(binding_path):
    """Verify original raw identity or exact pinned transport reconstruction."""
    received_sha256 = transport.sha_file(binding_path)
    binding = transport.load_json(binding_path)
    if received_sha256 == transport.HISTORICAL_BINDING_SHA256:
        return binding, {
            "historical_binding_sha256": received_sha256,
            "received_binding_sha256": received_sha256,
            "transport_manifest_sha256": None,
        }
    manifest_path = checked(PUBLIC_INPUT_ROOT, "source-manifest.json")
    metadata_path = checked(PUBLIC_INPUT_ROOT, "transport.json")
    manifest = transport.load_json(manifest_path)
    manifest_sha256 = transport.digest(transport.canonical(manifest))
    if manifest_sha256 != PUBLIC_MANIFEST_SHA256:
        raise ValueError("fixed public manifest digest mismatch")
    if transport.sha_file(metadata_path) != PUBLIC_TRANSPORT_SHA256:
        raise ValueError("fixed public transport digest mismatch")
    metadata = transport.load_json(metadata_path, 16 * 1024)
    transport.validate_metadata(metadata, manifest)
    expected = transport.rebuild_binding(manifest)
    if (
        manifest["source_binding_sha256"] != transport.HISTORICAL_BINDING_SHA256
        or binding != expected
        or transport.read_limited(binding_path, 2 * transport.BLOCK)
        != transport.canonical(expected) + b"\n"
    ):
        raise ValueError("binding is not the exact fixed transport reconstruction")
    return binding, {
        "historical_binding_sha256": manifest["source_binding_sha256"],
        "received_binding_sha256": received_sha256,
        "transport_manifest_sha256": manifest_sha256,
    }


def checked(root, relative):
    """Resolve an existing regular file, refusing links and traversal."""
    root = Path(root).absolute()
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("input path escapes root")
    path = root / relative
    for part in [root, *root.parents, *path.parents, path]:
        if part.is_symlink():
            raise ValueError("symbolic links are forbidden")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("input is not a contained regular file")
    return path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1048576):
            digest.update(block)
    return digest.hexdigest()


def write_private(path, value):
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise ValueError("symbolic links are forbidden")
    with path.open("x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, indent=2)
        stream.write("\n")


def prepare(
    binding_path,
    historical_root,
    installed_root,
    output_root,
    container_root,
    container_installed_root,
):
    """Copy verified historical bytes and bind the actual current installation."""
    historical_root = Path(historical_root).absolute()
    binding_path = checked(
        historical_root, Path(binding_path).absolute().relative_to(historical_root)
    )
    binding, identity = binding_identity(binding_path)
    installed_root = Path(installed_root).absolute()
    output_root = Path(output_root).absolute()
    for parent in [output_root, *output_root.parents]:
        if parent.is_symlink():
            raise ValueError("symbolic links are forbidden")
    for prefix in (container_root, container_installed_root):
        if not PurePosixPath(prefix).is_absolute() or ".." in PurePosixPath(prefix).parts:
            raise ValueError("container root must be absolute without traversal")
    source_base = binding_path.parent
    inputs = []
    for number, member in enumerate(binding["members"]):
        if "original_path" in member:
            source = checked(historical_root, member["original_path"])
        else:
            source = checked(source_base, member["path"].removeprefix("/e/"))
        if sha256(source) != member["sha256"]:
            raise ValueError("historical member digest mismatch")
        inputs.append((number, member, source))
    installed = []
    for member in binding["actual_installed_business_members"]:
        relative = member["path"].split("/site-packages/", 1)[1]
        source = checked(installed_root, relative)
        installed.append((relative, source, sha256(source), member["sha256"]))
    output_root.mkdir(mode=0o700)
    output_root.chmod(0o700)
    host = dict(binding)
    container = dict(binding)
    host["members"], container["members"] = [], []
    for number, member, source in inputs:
        relative = Path("originals") / str(number) / source.name
        target = output_root / relative
        target.parent.mkdir(parents=True, mode=0o700)
        target.parent.parent.chmod(0o700)
        with source.open("rb") as inp, target.open("xb") as out:
            os.chmod(target, 0o600)
            shutil.copyfileobj(inp, out)
        if sha256(target) != member["sha256"]:
            raise ValueError("copied member digest mismatch")
        host["members"].append({**member, "path": str(target)})
        container["members"].append(
            {**member, "path": str(PurePosixPath(container_root) / relative.as_posix())}
        )
        if member["role"] == "formal_plan":
            host["formal_plan"] = str(target)
            container["formal_plan"] = container["members"][-1]["path"]
    host["actual_installed_business_members"] = [
        {"path": str(source), "sha256": digest} for _, source, digest, _ in installed
    ]
    container["actual_installed_business_members"] = [
        {"path": str(PurePosixPath(container_installed_root) / relative), "sha256": digest}
        for relative, _, digest, _ in installed
    ]
    qualification = {
        **identity,
        "status": "PENDING_CURRENT_SOURCE_SEMANTIC_REVIEW",
        "old_classification_is_historical_only": True,
        "installed_comparison": [
            {
                "relative_path": relative,
                "current_sha256": digest,
                "historical_sha256": old,
                "identical": digest == old,
            }
            for relative, _, digest, old in installed
        ],
        "source_mapping": {
            "host": str(output_root),
            "container": container_root,
            "installed_host": str(installed_root),
            "installed_container": container_installed_root,
        },
    }
    for document in (host, container):
        document["relocation_run"] = qualification
        document["classification_requires_current_semantic_review"] = True
    write_private(output_root / "host-binding.json", host)
    write_private(output_root / "container-binding.json", container)
    write_private(output_root / "qualification.json", qualification)
    return qualification


def bind_installed(binding_path, installed_root, expected_source_root, output_path):
    """Run under the consumer Python; verify imports and exact current source bytes."""
    import importlib
    import importlib.metadata
    import sys

    if sys.version_info[:2] != (3, 11) or os.environ.get("PYTHONPATH"):
        raise ValueError("requires Python3.11 without PYTHONPATH")
    installed_root = Path(installed_root).absolute()
    expected_source_root = Path(expected_source_root).absolute()
    binding = json.loads(Path(binding_path).read_text())
    distribution = importlib.metadata.distribution("agent-guard")
    direct = json.loads(distribution.read_text("direct_url.json") or "{}")
    if direct.get("dir_info", {}).get("editable"):
        raise ValueError("editable installations are forbidden")
    package = importlib.import_module("agent_guard")
    if Path(package.__file__).absolute() != checked(installed_root, "agent_guard/__init__.py"):
        raise ValueError("agent_guard import is shadowed")
    expected_files = {
        path.relative_to(expected_source_root)
        for path in (expected_source_root / "agent_guard").rglob("*.py")
    }
    installed_files = {
        path.relative_to(installed_root) for path in (installed_root / "agent_guard").rglob("*.py")
    }
    if not expected_files or expected_files != installed_files:
        raise ValueError("installation has missing or stale source modules")
    if any(path.is_symlink() for path in (installed_root / "agent_guard").rglob("*")):
        raise ValueError("symbolic links are forbidden")
    members = []
    for relative_path in sorted((expected_source_root / "agent_guard").rglob("*.py")):
        relative = relative_path.relative_to(expected_source_root)
        source = checked(expected_source_root, relative)
        installed = checked(installed_root, relative)
        if sha256(installed) != sha256(source):
            raise ValueError("current source and installation differ")
        module_name = ".".join(relative.with_suffix("").parts)
        if module_name.endswith(".__init__"):
            module_name = module_name.removesuffix(".__init__")
        # find_spec checks the actual import origin without executing application modules.
        spec = importlib.util.find_spec(module_name)
        if spec is None or Path(spec.origin).absolute() != installed:
            raise ValueError("installed module import is shadowed")
        members.append({"path": str(installed), "sha256": sha256(installed)})
    binding["actual_installed_business_members"] = members
    binding["actual_installation"] = {
        "python": sys.version,
        "executable": sys.executable,
        "package_file": package.__file__,
        "editable": False,
        "current_source_members_verified": len(members),
        "semantic_qualification": "REQUIRES_REVIEW_AND_REAL_COUNTER",
    }
    write_private(Path(output_path), binding)
    return binding["actual_installation"]


def audit_archive(archive_path, output_path, now):
    """Inventory every row/field and decoded JWT; emit aggregates, never values.

    JWT claims are decoded, not cryptographically authenticated. Expiration alone
    is never a clearance to publish credentials or source evidence.
    """
    import base64
    import re
    from collections import Counter

    whole = json.loads(Path(archive_path).read_bytes())
    tables, indicators, token_groups = {}, Counter(), {}
    pattern_contexts = Counter()
    binary_contexts = Counter()
    lifecycle = {}
    seen = set()
    jwt_pattern = re.compile(
        r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})(?![A-Za-z0-9_-])"
    )
    secret_fields = re.compile(
        r"password|secret|credential|private|dsn|login|session|bearer|api.?key|owner_token|code_verifier",
        re.I,
    )

    def decoded(segment):
        return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))

    def scan(value, depth=0, location="archive"):
        if depth > 12:
            indicators["decode_depth_limit"] += 1
            return
        if isinstance(value, dict):
            for field, child in value.items():
                if secret_fields.search(field):
                    indicators["sensitive_named_field:" + field] += 1
                    if child not in (None, "", [], {}):
                        indicators["nonempty_sensitive_named_field:" + field] += 1
                scan(child, depth + 1, location + "." + field)
        elif isinstance(value, list):
            for child in value:
                scan(child, depth + 1, location + "[]")
        elif isinstance(value, str):
            if "PRIVATE KEY-----" in value:
                indicators["private_pem"] += 1
            for label, pattern in {
                "postgres_dsn": r"postgres(?:ql)?://",
                "password_assignment": r"password\s*=",
                "libpq_keyword_dsn": (
                    r"(?is)(?:host|hostaddr|dbname|user|port)\s*=.{0,1200}?password\s*="
                    r"|password\s*=.{0,1200}?(?:host|hostaddr|dbname|user|port)\s*="
                ),
                "bearer_header": r"Bearer\s+",
                "api_key_pattern": r"\bsk-[A-Za-z0-9]{20,}",
            }.items():
                if re.search(pattern, value, re.I):
                    indicators[label] += 1
                    pattern_contexts[label + ":" + location] += 1
                    if label == "api_key_pattern" and jwt_pattern.fullmatch(value):
                        indicators["api_key_pattern_inside_compact_jws"] += 1
            if value.startswith("\\x"):
                try:
                    scan(
                        bytes.fromhex(value[2:]).decode("utf-8"), depth + 1, location + ".hex_utf8"
                    )
                except (ValueError, UnicodeDecodeError):
                    indicators["hex_binary_not_utf8"] += 1
                    binary_contexts[location + ":bytes=" + str((len(value) - 2) // 2)] += 1
                return
            if value.startswith(("{", "[")):
                try:
                    scan(json.loads(value), depth + 1, location + ".json")
                    return
                except (ValueError, RecursionError):
                    pass
            for match in jwt_pattern.finditer(value):
                compact = match.group(1)
                fingerprint = hashlib.sha256(compact.encode()).digest()
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                try:
                    header, claims = [decoded(part) for part in compact.split(".")[:2]]
                    if not isinstance(header, dict) or not isinstance(claims, dict):
                        raise ValueError("nonobject JWT")
                except (ValueError, UnicodeDecodeError):
                    indicators["jwt_decode_failed"] += 1
                    continue
                # Group only by known public JWT type names; never output arbitrary headers.
                kind = header.get("typ")
                allowed = {
                    "ag-at+jwt",
                    "ag-id+jwt",
                    "ag-pop+jwt",
                    "ag-receipt+jwt",
                    "ag-checkpoint+jwt",
                    "JWT",
                    "at+jwt",
                }
                kind = kind if kind in allowed else "other_type"
                group = token_groups.setdefault(
                    kind,
                    {
                        "count": 0,
                        "exp_min": None,
                        "exp_max": None,
                        "missing_or_invalid_exp": 0,
                        "expired": 0,
                        "issuer_matches_synthetic_test": 0,
                        "tenant_matches_synthetic_test": 0,
                        "task_matches_synthetic_test": 0,
                        "claim_fields": {},
                    },
                )
                group["count"] += 1
                for field in claims:
                    group["claim_fields"][field] = group["claim_fields"].get(field, 0) + 1
                exp = claims.get("exp")
                if isinstance(exp, int) and not isinstance(exp, bool):
                    group["exp_min"] = (
                        exp if group["exp_min"] is None else min(exp, group["exp_min"])
                    )
                    group["exp_max"] = (
                        exp if group["exp_max"] is None else max(exp, group["exp_max"])
                    )
                    group["expired"] += exp <= now
                else:
                    group["missing_or_invalid_exp"] += 1
                group["issuer_matches_synthetic_test"] += (
                    claims.get("iss") == "https://auth.agent-guard.test"
                )
                group["tenant_matches_synthetic_test"] += (
                    claims.get("tenant_id", claims.get("ag_tenant_id")) == "tenant-001"
                )
                group["task_matches_synthetic_test"] += (
                    claims.get("task_id", claims.get("ag_task_id")) == "task-001"
                )
                scan(claims, depth + 1, location + ".jwt_claims")

    for domain, state in whole["state"].items():
        for table, rows in state.items():
            fields = {}
            count = 0
            for item in rows:
                row = json.loads(item[0])
                count += 1
                for field, value in row.items():
                    fields.setdefault(field, Counter())[type(value).__name__] += 1
                for field in [
                    key for key in row if key.endswith("expires_at") or key == "consumed_at"
                ]:
                    if field not in row:
                        continue
                    stats = lifecycle.setdefault(
                        domain + "." + table + "." + field,
                        {
                            "nonnull": 0,
                            "null": 0,
                            "expired": 0,
                            "minimum_unix": None,
                            "maximum_unix": None,
                        },
                    )
                    value = row[field]
                    if value is None:
                        stats["null"] += 1
                    else:
                        from datetime import datetime

                        instant = datetime.fromisoformat(value).timestamp()
                        stats["nonnull"] += 1
                        stats["expired"] += instant <= now
                        stats["minimum_unix"] = (
                            instant
                            if stats["minimum_unix"] is None
                            else min(instant, stats["minimum_unix"])
                        )
                        stats["maximum_unix"] = (
                            instant
                            if stats["maximum_unix"] is None
                            else max(instant, stats["maximum_unix"])
                        )
                scan(row, location=domain + "." + table)
            tables[domain + "." + table] = {"rows": count, "field_types": fields}
    scan({k: v for k, v in whole.items() if k != "state"}, location="metadata")
    report = {
        "archive_sha256": sha256(Path(archive_path)),
        "audit_now_unix": now,
        "tables": tables,
        "jwt_distinct_decoded": token_groups,
        "sensitive_indicators": dict(indicators),
        "pattern_field_contexts": dict(pattern_contexts),
        "non_utf8_binary_contexts": dict(binary_contexts),
        "lifecycle_fields": lifecycle,
        "clearance": "BLOCKED_PENDING_SEMANTIC_CREDENTIAL_REVIEW",
        "limits": [
            "claims decoded, signatures not verified",
            "pattern absence and expiration do not prove no reusable credentials",
            "synthetic fixture correlation is evidence, not permission to publish",
        ],
    }
    write_private(Path(output_path), report)
    return report


def audit_support_files(binding_path, historical_root, output_path):
    """Count URI and libpq keyword DSNs in support files without emitting values."""
    import re

    historical_root = Path(historical_root).absolute()
    binding_path = checked(
        historical_root, Path(binding_path).absolute().relative_to(historical_root)
    )
    binding = json.loads(binding_path.read_text())
    results = []
    for member in binding["members"]:
        if member["role"] == "native_archive":
            continue
        source = (
            checked(historical_root, member["original_path"])
            if "original_path" in member
            else checked(binding_path.parent, member["path"].removeprefix("/e/"))
        )
        if sha256(source) != member["sha256"]:
            raise ValueError("historical member digest mismatch")
        text = source.read_text()
        results.append(
            {
                "role": member["role"],
                "sha256": member["sha256"],
                "bytes": source.stat().st_size,
                "password_assignment_matches": len(re.findall(r"password\s*=", text, re.I)),
                "libpq_keyword_dsn_matches": len(
                    re.findall(
                        r"(?is)(?:host|hostaddr|dbname|user|port)\s*=.{0,1200}?password\s*="
                        r"|password\s*=.{0,1200}?(?:host|hostaddr|dbname|user|port)\s*=",
                        text,
                    )
                ),
                "postgres_uri_matches": len(re.findall(r"postgres(?:ql)?://", text, re.I)),
            }
        )
    report = {
        "members": results,
        "credential_liveness": "UNKNOWN_NOT_PROBED",
        "clearance": "RAW_SUPPORT_LOGS_ARE_SENSITIVE_NOT_FOR_PUBLICATION",
        "correction": "URI-only scans missed libpq keyword DSNs; no values emitted",
    }
    write_private(Path(output_path), report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    relocation = commands.add_parser("prepare")
    for name in (
        "historical-binding",
        "historical-root",
        "installed-root",
        "output-root",
        "container-root",
        "container-installed-root",
    ):
        relocation.add_argument("--" + name, required=True)
    installed = commands.add_parser("bind-installed")
    for name in ("binding", "installed-root", "expected-source-root", "output"):
        installed.add_argument("--" + name, required=True)
    audit = commands.add_parser("audit")
    audit.add_argument("--archive", required=True)
    audit.add_argument("--output", required=True)
    audit.add_argument("--now", type=int, required=True)
    support = commands.add_parser("audit-support")
    support.add_argument("--binding", required=True)
    support.add_argument("--historical-root", required=True)
    support.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(
            args.historical_binding,
            args.historical_root,
            args.installed_root,
            args.output_root,
            args.container_root,
            args.container_installed_root,
        )
    elif args.command == "audit-support":
        audit_support_files(args.binding, args.historical_root, args.output)
    elif args.command == "audit":
        audit_archive(args.archive, args.output, args.now)
    else:
        bind_installed(args.binding, args.installed_root, args.expected_source_root, args.output)


if __name__ == "__main__":
    main()
