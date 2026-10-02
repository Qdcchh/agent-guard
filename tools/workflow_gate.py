#!/usr/bin/env python3
"""Read-only workflow consistency checks; JSON cannot establish human authorization.

Every artifact path in state is relative to --root. Snapshot control directories
are excluded; contract/report/evidence files are verified separately. Stop other
writers while capturing/verifying a snapshot: this is not an atomic filesystem
snapshot, an authorization system, or proof that recorded runs really occurred.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

STATUSES = {
    "AWAITING_USER_APPROVAL",
    "IN_PROGRESS",
    "READY_FOR_REVIEW",
    "CHANGES_REQUESTED",
    "ACCEPTED",
    "BLOCKED",
}
REQUIREMENT_STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "NOT_APPLICABLE"}
CONTROL_NAMES = {".git", ".opencode"}
CONTROL_FILES = {"tasks/workflow/state.json", "tasks/workflow/issues.md"}
CONTROL_PREFIXES = (
    "tasks/workflow/runs",
    "tasks/workflow/artifacts",
    ".codex/tasks/workflow",
)
GENERATED_NAMES = {
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".cache",
    ".tox",
    ".nox",
    ".hypothesis",
    "node_modules",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class GateError(Exception):
    def __init__(self, code: str, field: str | None = None):
        super().__init__(code)
        self.code = code
        self.field = field

    def json(self) -> dict[str, str]:
        result = {"code": self.code}
        if self.field is not None:
            result["field"] = self.field
        return result


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UsageError()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def contract_files_sha256(items: list[dict[str, Any]]) -> str:
    """Hash path/sha256 pairs, sorted by path, using canonical UTF-8 JSON."""
    pairs = [{"path": item["path"], "sha256": item["sha256"]} for item in items]
    return digest(sorted(pairs, key=lambda item: item["path"]))


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_digest(value: Any) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _file_sha256(path: Path) -> str:
    """Hash regular files without printing their contents; detect common races."""
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise GateError("not_regular_file")
    result = hashlib.sha256()
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise GateError("file_changed_during_read")
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
        after = os.fstat(handle.fileno())
    current = path.stat()

    def stamp(info: os.stat_result) -> tuple[int, int, int, int]:
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)

    if stamp(before) != stamp(after) or stamp(after) != stamp(current):
        raise GateError("file_changed_during_read")
    return result.hexdigest()


def _control(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return (
        any(part in CONTROL_NAMES for part in parts)
        or path in CONTROL_FILES
        or any(path == prefix or path.startswith(prefix + "/") for prefix in CONTROL_PREFIXES)
    )


def _generated(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return (
        any(part in GENERATED_NAMES or part.endswith(".egg-info") for part in parts)
        or parts[0] == "artifacts"
        or parts[-1] in {".DS_Store", ".coverage"}
        or parts[-1].startswith(".coverage.")
        or parts[-1].endswith((".pyc", ".pyo"))
    )


def _tracked(root: Path) -> dict[str, int]:
    env = dict(os.environ)
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(key, None)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        probe = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            timeout=15,
            check=False,
            env=env,
        )
        if probe.returncode != 0:
            if (root / ".git").exists():
                raise GateError("git_index_unavailable")
            return {}
        result = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(root), "ls-files", "--stage", "-z"],
            capture_output=True,
            timeout=30,
            check=False,
            env=env,
        )
    except FileNotFoundError:
        if (root / ".git").exists():
            raise GateError("git_unavailable") from None
        return {}
    except subprocess.TimeoutExpired:
        raise GateError("git_timeout") from None
    if result.returncode != 0:
        raise GateError("git_index_unavailable")
    tracked: dict[str, int] = {}
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, _, stage = metadata.split()
        path = os.fsdecode(raw_path)
        if not _control(path):
            if stage != b"0":
                raise GateError("git_unmerged_index")
            if mode == b"160000":
                raise GateError("git_submodule_unsupported")
            tracked[path] = int(mode, 8)
    return tracked


def snapshot(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise GateError("root_not_directory")
    tracked = _tracked(root)
    tracked_parents: set[str] = set()
    for path in tracked:
        for parent in PurePosixPath(path).parents:
            tracked_parents.add(parent.as_posix())
    manifest: dict[str, dict[str, Any]] = {}

    def walk(directory: Path) -> None:
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                if _control(relative):
                    continue
                is_tracked = relative in tracked
                if _generated(relative) and not is_tracked and relative not in tracked_parents:
                    continue
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    walk(path)
                    continue
                if stat.S_ISLNK(info.st_mode):
                    # Do not read external targets or silently fingerprint only an
                    # external production dependency's link name.
                    if not path.resolve(strict=False).is_relative_to(root):
                        raise GateError("snapshot_symlink_outside_root", relative)
                    kind = "symlink"
                    sha256 = hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
                elif stat.S_ISREG(info.st_mode):
                    kind = "file"
                    sha256 = _file_sha256(path)
                else:
                    raise GateError("snapshot_special_file", relative)
                manifest[relative] = {
                    "path": relative,
                    "state": "tracked" if is_tracked else "untracked",
                    "type": kind,
                    "mode": stat.S_IMODE(info.st_mode),
                    "sha256": sha256,
                }

    walk(root)
    for relative, mode in tracked.items():
        if relative not in manifest:
            manifest[relative] = {
                "path": relative,
                "state": "deleted",
                "type": "deleted",
                "mode": stat.S_IMODE(mode),
                "sha256": None,
            }
    result = {
        "schema_version": 1,
        "project_root": str(root),
        "algorithm": "sha256",
        "excluded_control_names": sorted(CONTROL_NAMES),
        "excluded_control_files": sorted(CONTROL_FILES),
        "excluded_control_prefixes": list(CONTROL_PREFIXES),
        "excluded_generated_names": sorted(GENERATED_NAMES),
        "manifest": [manifest[key] for key in sorted(manifest)],
    }
    return {**result, "fingerprint": digest(result)}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GateError("duplicate_json_key")
        result[key] = value
    return result


def load_state(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError):
        raise GateError("state_unreadable_or_invalid_json") from None
    if not isinstance(result, dict):
        raise GateError("state_not_object")
    return result


class Verification:
    def __init__(self, root: Path, state: dict[str, Any]):
        self.root = root
        self.state = state
        self.errors: list[dict[str, str]] = []

    def error(self, code: str, field: str) -> None:
        self.errors.append({"code": code, "field": field})

    def file(self, relative: Any, sha256: Any, field: str) -> bool:
        if not nonempty(relative) or not is_digest(sha256):
            self.error("artifact_path_or_hash_invalid", field)
            return False
        parts = PurePosixPath(relative)
        if parts.is_absolute() or ".." in parts.parts or parts.as_posix() != relative:
            self.error("artifact_path_not_relative_canonical", field)
            return False
        try:
            path = (self.root / relative).resolve(strict=True)
            if not path.is_relative_to(self.root):
                self.error("artifact_outside_root", field)
                return False
            actual = _file_sha256(path)
        except (OSError, GateError, RuntimeError):
            self.error("artifact_missing_or_unreadable", field)
            return False
        if actual != sha256:
            self.error("artifact_hash_mismatch", field)
            return False
        return True

    def identifiers(self, value: Any, field: str, *, required: bool) -> set[str]:
        if not isinstance(value, list) or (required and not value):
            self.error("requirement_ids_invalid", field)
            return set()
        seen: set[str] = set()
        for index, item in enumerate(value):
            if not nonempty(item):
                self.error("requirement_id_invalid", f"{field}/{index}")
            elif item in seen:
                self.error("requirement_id_duplicate", f"{field}/{index}")
            else:
                seen.add(item)
        return seen

    def contracts(self) -> str | None:
        items = self.state.get("contract_files")
        if not isinstance(items, list) or not items:
            self.error("contract_files_missing", "contract_files")
            return None
        seen: set[str] = set()
        valid: list[dict[str, str]] = []
        for index, item in enumerate(items):
            field = f"contract_files/{index}"
            if not isinstance(item, dict):
                self.error("contract_file_invalid", field)
                continue
            path = item.get("path")
            if nonempty(path):
                if path in seen:
                    self.error("contract_file_duplicate", field)
                seen.add(path)
            if self.file(path, item.get("sha256"), field):
                valid.append({"path": path, "sha256": item["sha256"]})
        return contract_files_sha256(valid) if len(valid) == len(items) else None

    def authorization(self, required: bool) -> bool:
        auth = self.state.get("authorization")
        if not isinstance(auth, dict):
            self.error("authorization_missing", "authorization")
            return False
        if auth.get("stage") != self.state.get("current_stage"):
            self.error("authorization_stage_mismatch", "authorization/stage")
        status = auth.get("status")
        if not isinstance(status, str) or status not in {"PENDING", "GRANTED"}:
            self.error("authorization_status_invalid", "authorization/status")
        if required and status != "GRANTED":
            self.error("authorization_not_granted", "authorization/status")
        if self.state.get("status") == "AWAITING_USER_APPROVAL" and status != "PENDING":
            self.error("awaiting_status_requires_pending_authorization", "authorization/status")
        allowed = auth.get("allowed_paths")
        forbidden = auth.get("forbidden_actions")
        if not isinstance(allowed, list) or not allowed or not all(nonempty(v) for v in allowed):
            self.error("allowed_paths_invalid", "authorization/allowed_paths")
        elif any(PurePosixPath(v).is_absolute() or ".." in PurePosixPath(v).parts for v in allowed):
            self.error("allowed_paths_outside_root", "authorization/allowed_paths")
        if not isinstance(forbidden, list) or not all(nonempty(v) for v in forbidden):
            self.error("forbidden_actions_invalid", "authorization/forbidden_actions")
        if status == "GRANTED":
            source = auth.get("source_message")
            if (
                not isinstance(source, dict)
                or source.get("role") != "user"
                or not all(
                    nonempty(source.get(key)) for key in ("session_id", "message_id", "text")
                )
            ):
                self.error("authorization_source_message_invalid", "authorization/source_message")
        return status == "GRANTED"

    def accepted(self, contracts_hash: str | None) -> None:
        state = self.state
        if state.get("status") not in ("READY_FOR_REVIEW", "ACCEPTED"):
            self.error("stage_not_ready_for_acceptance", "status")
        expected = self.identifiers(
            state.get("expected_requirement_ids"), "expected_requirement_ids", required=True
        )
        runs = self.identifiers(
            state.get("independent_run_requirement_ids"),
            "independent_run_requirement_ids",
            required=False,
        )
        if not runs.issubset(expected):
            self.error("runtime_requirement_not_expected", "independent_run_requirement_ids")
        recorded = state.get("snapshot")
        if not isinstance(recorded, dict):
            self.error("snapshot_missing", "snapshot")
            fingerprint = None
        else:
            fingerprint = recorded.get("fingerprint")
            body = {key: value for key, value in recorded.items() if key != "fingerprint"}
            if not is_digest(fingerprint) or digest(body) != fingerprint:
                self.error("snapshot_fingerprint_invalid", "snapshot/fingerprint")
            try:
                if recorded != snapshot(self.root):
                    self.error("code_snapshot_changed", "snapshot")
            except (OSError, GateError, RuntimeError):
                self.error("code_snapshot_unavailable", "snapshot")
        review = state.get("review")
        if not isinstance(review, dict):
            self.error("review_missing", "review")
            return
        if review.get("review_kind") != "IMPLEMENTATION_ACCEPTANCE":
            self.error("review_kind_not_implementation_acceptance", "review/review_kind")
        review_id = review.get("independent_session_id")
        auth = state.get("authorization")
        source = auth.get("source_message") if isinstance(auth, dict) else None
        source = source if isinstance(source, dict) else {}
        if not nonempty(review_id) or review_id == source.get("session_id"):
            self.error("review_session_not_independent", "review/independent_session_id")
        if not is_digest(review.get("snapshot_fingerprint")) or (
            review.get("snapshot_fingerprint") != fingerprint
        ):
            self.error("review_snapshot_mismatch", "review/snapshot_fingerprint")
        if not is_digest(review.get("contract_files_sha256")) or (
            review.get("contract_files_sha256") != contracts_hash
        ):
            self.error("review_contracts_mismatch", "review/contract_files_sha256")
        self.file(review.get("report_path"), review.get("report_sha256"), "review/report")
        if review.get("open_blockers") != []:
            self.error("open_blockers_not_empty", "review/open_blockers")
        requirements = review.get("requirements")
        if not isinstance(requirements, list) or not requirements:
            self.error("requirements_missing", "review/requirements")
            return
        seen: set[str] = set()
        for index, item in enumerate(requirements):
            field = f"review/requirements/{index}"
            if not isinstance(item, dict) or not nonempty(item.get("id")):
                self.error("requirement_invalid", field)
                continue
            requirement_id = item["id"]
            if requirement_id in seen:
                self.error("requirement_duplicate", field)
            seen.add(requirement_id)
            status = item.get("status")
            if not isinstance(status, str) or status not in REQUIREMENT_STATUSES:
                self.error("requirement_status_invalid", field)
            if requirement_id in expected and status != "PASS":
                self.error("mandatory_requirement_not_pass", field)
            elif not isinstance(status, str) or status not in {"PASS", "NOT_APPLICABLE"}:
                self.error("requirement_not_pass", field)
            elif status == "NOT_APPLICABLE" and not nonempty(item.get("reason")):
                self.error("not_applicable_reason_missing", field)
            evidence = item.get("evidence")
            if not isinstance(evidence, list):
                self.error("evidence_list_invalid", field)
                continue
            independent = False
            independent_run = False
            for evidence_index, proof in enumerate(evidence):
                proof_field = f"{field}/evidence/{evidence_index}"
                if not isinstance(proof, dict):
                    self.error("evidence_invalid", proof_field)
                    continue
                kind = proof.get("kind")
                if not isinstance(kind, str) or kind not in {
                    "independent_run",
                    "inspection",
                    "historical_log",
                }:
                    self.error("evidence_kind_invalid", proof_field)
                exit_code = proof.get("exit_code")
                valid_exit = (type(exit_code) is int and exit_code == 0) or (
                    exit_code is None and kind != "independent_run"
                )
                if not valid_exit:
                    self.error("evidence_exit_code_not_success", proof_field)
                valid_file = self.file(proof.get("path"), proof.get("sha256"), proof_field)
                if valid_exit and valid_file:
                    independent = independent or kind in ("inspection", "independent_run")
                    independent_run = independent_run or kind == "independent_run"
            if status == "PASS" and not independent:
                self.error("independent_evidence_missing", field)
            if requirement_id in runs and not independent_run:
                self.error("independent_run_missing", field)
        if not expected.issubset(seen):
            self.error("mandatory_requirements_missing", "review/requirements")

    def verify(self, *, require_authorized: bool, require_accepted: bool) -> dict[str, Any]:
        state = self.state
        if type(state.get("schema_version")) is not int or state["schema_version"] != 1:
            self.error("schema_version_invalid", "schema_version")
        if state.get("project_root") != str(self.root):
            self.error("project_root_mismatch", "project_root")
        if not nonempty(state.get("current_stage")):
            self.error("current_stage_invalid", "current_stage")
        status = state.get("status")
        valid_status = isinstance(status, str) and status in STATUSES
        if not valid_status:
            self.error("status_invalid", "status")
        if (
            require_authorized
            and not require_accepted
            and status not in ("IN_PROGRESS", "CHANGES_REQUESTED")
        ):
            self.error("stage_not_open_for_implementation", "status")
        needs_accepted = require_accepted or state.get("status") == "ACCEPTED"
        needs_authorized = (
            require_authorized
            or needs_accepted
            or (status not in ("AWAITING_USER_APPROVAL", "BLOCKED"))
        )
        granted = self.authorization(needs_authorized)
        contracts_hash = (
            self.contracts()
            if (needs_authorized or state.get("contract_files") is not None)
            else None
        )
        if needs_accepted:
            self.accepted(contracts_hash)
        ok = not self.errors
        # Structural grant is not a substitute for checking the actual message.
        can_start = ok and granted and status in ("IN_PROGRESS", "CHANGES_REQUESTED")
        return {
            "ok": ok,
            "status": status if valid_status else None,
            "can_start": can_start,
            "can_accept": ok and needs_accepted,
            "accepted": ok and needs_accepted and status == "ACCEPTED",
            "authorization_is_structural_only": True,
            "contract_files_sha256": contracts_hash,
            "errors": self.errors,
        }


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    snap = commands.add_parser("snapshot")
    snap.add_argument("--root", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--root", required=True)
    verify.add_argument("--state", required=True)
    verify.add_argument("--require-authorized", action="store_true")
    verify.add_argument("--require-accepted", action="store_true")
    try:
        args = parser.parse_args(argv)
        root = Path(args.root).resolve(strict=True)
        if not root.is_dir():
            raise GateError("root_not_directory")
        if args.command == "snapshot":
            result = snapshot(root)
            code = 0
        else:
            state_path = Path(args.state)
            if not state_path.is_absolute():
                state_path = root / state_path
            state = load_state(state_path)
            result = Verification(root, state).verify(
                require_authorized=args.require_authorized,
                require_accepted=args.require_accepted,
            )
            code = 0 if result["ok"] else 1
    except UsageError:
        result = {"ok": False, "errors": [{"code": "usage_error"}]}
        code = 2
    except GateError as error:
        result = {"ok": False, "errors": [error.json()]}
        code = 1
    except (OSError, ValueError, RuntimeError):
        result = {"ok": False, "errors": [{"code": "filesystem_or_input_error"}]}
        code = 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return code


if __name__ == "__main__":
    sys.exit(main())
