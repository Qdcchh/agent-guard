"""Loopback-only, fixed-action presentation UI for teacher_demo.py."""

import argparse
import json
import math
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "web/teacher-demo"
sys.path.insert(0, str(REPO))
from tools import teacher_demo_events as events  # noqa: E402
from tools import teacher_demo_scenarios as scenarios  # noqa: E402


def safe_path(path):
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("parent traversal")
    path.relative_to(REPO / "artifacts")
    path.resolve().relative_to((REPO / "artifacts").resolve())
    for part in (path, *path.parents):
        if part == REPO:
            break
        if part.is_symlink():
            raise ValueError("symlink")
    return path


def read(path):
    return json.loads(safe_path(path).read_text())


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("invalid integer")
    return value


def summary(folder):
    folder = safe_path(folder)
    if read(folder / "manager-native-exit.json")["native_exit"] != 0:
        raise ValueError("not successful")
    report = read(folder / "normal-result/normal-report.json")
    oracle = read(folder / "normal-result/database-oracle.json")
    run_id = str(uuid.UUID(report["run_id"]))
    receipts = [q["receipt_status"] for q in report["queries"]]
    if len(receipts) != 4 or any(s != "READY" for s in receipts):
        raise ValueError("incomplete receipts")
    rows = oracle["ancestor_counters"]
    if len(rows) != 3 or len(set(report["holder_uids"])) != 3:
        raise ValueError("incomplete chain")
    counters = []
    for row in rows:
        if len(row) != 7:
            raise ValueError("invalid counters")
        counters.append([integer(v) for v in row])
    return {
        "run_id": run_id,
        "receipts": receipts,
        "orders": integer(oracle["real_orders"]),
        "notifications": integer(oracle["real_notifications"]),
        "counters": counters,
        "resources_remaining": integer(read(folder / "cleanup.json")["resources_remaining"]),
    }


COSM2_CASES = {
    "cosign-valid-one-order": {"http_status": 202},
    "missing-approval": {"http_status": 401, "code": "APPROVAL_REQUIRED"},
    "exec-domain-alone": {"http_status": 401, "code": "INVALID_SIGNATURE"},
    "tampered-amount": {"http_status": 409, "code": "APPROVAL_MISMATCH"},
    "revoked-before-cosign": {"refused_by": "authz", "code": "AUTHZ_REVOKED"},
    "revoked-after-cosign": {"http_status": 403, "code": "REVOKED"},
}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def cosm2_result(folder):
    """Strict B7 saved-result reader. Summary evidence never implies live events."""
    folder = safe_path(folder)
    root = safe_path(REPO / "artifacts/cosm2-gateway-demo-live")
    if folder.parent != root or str(uuid.UUID(folder.name)) != folder.name:
        raise ValueError("invalid COSM2 result directory")
    path = safe_path(folder / "result.json")
    if path.stat().st_size > 65536:
        raise ValueError("oversized COSM2 result")
    data = json.loads(path.read_text(), object_pairs_hook=unique_object)
    validate_cosm2_result(data, folder.name)
    return {
        **data,
        "source": "saved-result",
        "source_label": "保存结果回放（本地文件，非独立证明）",
    }


def validate_cosm2_result(data, run_id):
    """Shared strict B7 wire contract; no extra output or private fields."""
    fields = {
        "run_id",
        "passed",
        "completed_at",
        "scheme",
        "public_key_fingerprint",
        "orders",
        "operations",
        "approvals",
        "resources_remaining",
        "cases",
        "timing_ms",
    }
    if type(data) is not dict or set(data) != fields:
        raise ValueError("invalid COSM2 fields")
    if data["run_id"] != run_id or data["scheme"] != "sm2-2p":
        raise ValueError("invalid COSM2 source")
    if (
        type(data["passed"]) is not bool
        or type(data["public_key_fingerprint"]) is not str
        or not re.fullmatch(r"[0-9a-f]{16}", data["public_key_fingerprint"])
    ):
        raise ValueError("invalid COSM2 summary")
    integer(data["completed_at"])
    if not 0 < data["completed_at"] <= 253402300799:
        raise ValueError("invalid completion time")
    for field in ("orders", "operations", "approvals", "resources_remaining"):
        integer(data[field])
    cases = data["cases"]
    if type(cases) is not list or len(cases) != len(COSM2_CASES):
        raise ValueError("incomplete COSM2 cases")
    seen = set()
    for case in cases:
        if type(case) is not dict or type(case.get("name")) is not str:
            raise ValueError("invalid COSM2 case")
        name = case["name"]
        if name not in COSM2_CASES or name in seen:
            raise ValueError("unknown or duplicate COSM2 case")
        expected = COSM2_CASES[name]
        if set(case) != {"name", "passed", *expected} or type(case["passed"]) is not bool:
            raise ValueError("invalid COSM2 case fields")
        if any(type(case[k]) is not type(v) or case[k] != v for k, v in expected.items()):
            raise ValueError("inconsistent COSM2 refusal")
        seen.add(name)
    success = all(case["passed"] for case in cases)
    if data["passed"] != success or (
        success
        and any(
            data[k] != v
            for k, v in {
                "orders": 1,
                "operations": 1,
                "approvals": 1,
                "resources_remaining": 0,
            }.items()
        )
    ):
        raise ValueError("inconsistent COSM2 aggregate")
    timing = data["timing_ms"]
    if (
        type(timing) is not dict
        or set(timing) != {"round1", "round2_with_checks", "round3_with_verify"}
        or any(
            type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in timing.values()
        )
    ):
        raise ValueError("invalid COSM2 timing")


def cosm2_saved_state():
    """Read only the fixed root; no pointer, arbitrary path, or job execution."""
    try:
        root = safe_path(REPO / "artifacts/cosm2-gateway-demo-live")
        candidates = []
        rejected = 0
        for folder in root.iterdir():
            if re.fullmatch(r"[0-9a-f-]{36}", folder.name):
                try:
                    candidates.append(cosm2_result(folder))
                except (OSError, ValueError, KeyError, TypeError, OverflowError):
                    rejected += 1
        if candidates:
            return max(candidates, key=lambda item: (item["completed_at"], item["run_id"])), (
                "保存结果回放；可在本机重新运行"
                + (f"；{rejected} 份未通过格式校验的历史结果未采用" if rejected else "")
            )
        return None, "未就绪：尚无协同签名保存结果；继续动画示意"
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return None, "未就绪：协同签名保存结果缺失或校验失败；继续动画示意"


def threshold_result(folder):
    """Read one sanitized threshold demo result; never returns raw material."""
    folder = safe_path(folder)
    data = read(folder / "result.json")
    if (
        data.get("demo") != "threshold-gateway-purchase"
        or type(data.get("passed")) is not bool
        or type(data.get("run_id")) is not str
        or type(data.get("cases")) is not list
        or len(data["cases"]) == 0
        or type(data.get("orders")) is not int
        or type(data.get("approvals")) is not int
        or type(data.get("operations")) is not int
        or type(data.get("resources_remaining")) is not list
    ):
        raise ValueError("invalid threshold demo result")
    cases = []
    for case in data["cases"]:
        if (
            type(case) is not dict
            or type(case.get("name")) is not str
            or type(case.get("passed")) is not bool
            or ("http_status" in case and type(case["http_status"]) is not int)
            or ("code" in case and not (case["code"] is None or type(case["code"]) is str))
        ):
            raise ValueError("invalid threshold demo case")
        cases.append(
            {
                "name": case["name"][:64],
                "passed": case["passed"],
                "http_status": case.get("http_status"),
                "code": case.get("code"),
            }
        )
    return {
        "run_id": str(uuid.UUID(data["run_id"])),
        "passed": data["passed"],
        "cases": cases,
        "operations": integer(data["operations"]),
        "approvals": integer(data["approvals"]),
        "orders": integer(data["orders"]),
        "resources_remaining": integer(len(data["resources_remaining"])),
        "completed_at": int(time.time()),
    }


def x402_result(folder):
    """Read one sanitized x402 demo result; never returns raw material."""
    folder = safe_path(folder)
    data = read(folder / "result.json")
    if (
        data.get("demo") != "x402-gateway-purchase"
        or type(data.get("passed")) is not bool
        or type(data.get("run_id")) is not str
        or type(data.get("cases")) is not list
        or len(data["cases"]) == 0
        or any(
            type(data.get(key)) is not int
            for key in ("operations", "approvals", "orders", "payments", "transactions")
        )
        or type(data.get("resources_remaining")) is not list
    ):
        raise ValueError("invalid x402 demo result")
    cases = []
    for case in data["cases"]:
        if (
            type(case) is not dict
            or type(case.get("name")) is not str
            or type(case.get("passed")) is not bool
            or ("http_status" in case and type(case["http_status"]) is not int)
            or ("code" in case and not (case["code"] is None or type(case["code"]) is str))
        ):
            raise ValueError("invalid x402 demo case")
        cases.append(
            {
                "name": case["name"][:64],
                "passed": case["passed"],
                "http_status": case.get("http_status"),
                "code": case.get("code"),
            }
        )
    return {
        "run_id": str(uuid.UUID(data["run_id"])),
        "passed": data["passed"],
        "cases": cases,
        "operations": integer(data["operations"]),
        "approvals": integer(data["approvals"]),
        "orders": integer(data["orders"]),
        "payments": integer(data["payments"]),
        "transactions": integer(data["transactions"]),
        "resources_remaining": integer(len(data["resources_remaining"])),
        "completed_at": int(time.time()),
    }


def verification(folder):
    result = {}
    for label, expected in (("original", 0), ("tampered", 2)):
        native = read(folder / (label + ".json.native.json"))
        if native.get("actual_wait") is not True or native.get("native_exit") != expected:
            raise ValueError("verification incomplete")
        result[label] = {"exit": expected}
    report = read(folder / "original.json")
    allowed = {
        "cryptographic_consistency",
        "current_auth",
        "downstream_truth",
        "freshness",
        "history_boundary",
        "anchored_prefix",
        "cutoff_sequence",
        "tail",
    }
    result["boundaries"] = {
        k: v
        for k, v in report.items()
        if k in allowed
        and (type(v) is int or (isinstance(v, str) and re.fullmatch(r"[A-Z_]{1,80}", v)))
    }
    return result


class DemoApp:
    def __init__(self, launcher=subprocess.Popen):
        self.launcher = launcher
        self.lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)
        self.job = None
        self.live_folder = None
        self.last_verification = None
        self.history = None
        self.threshold = None
        self.x402 = None
        self.cosign = None
        self.scenario_results = {}
        self.runs = {}
        try:
            pointer = safe_path(REPO / "artifacts/teacher-demo-live/latest-run.txt")
            if not pointer.exists():
                pointer = safe_path(REPO / "artifacts/teacher-demo-20261015/latest-run.txt")
            self.history = safe_path(Path(pointer.read_text().strip()))
            summary(self.history)
        except (OSError, ValueError, KeyError, TypeError):
            self.history = None

    def state(self):
        with self.lock:
            job = dict(self.job) if self.job else None
        if job:
            job["elapsed"] = int((job.get("ended") or time.time()) - job["started"])
        historical = None
        try:
            if self.history:
                historical = summary(self.history)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        live = None
        try:
            if self.live_folder:
                live = summary(self.live_folder)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        cosign, cosign_status = cosm2_saved_state()
        if self.cosign is not None:
            cosign = self.cosign
            cosign_status = "本次现场运行；右侧仍为动画示意"
        cosign_ready = (REPO / "tools/cosm2_desktop.py").is_file() and (
            REPO / "tools/cosm2_gateway_demo.py"
        ).is_file()
        if cosign_ready and cosign is None:
            cosign_status = "尚未运行：本机入口已安装；需要 Docker Desktop 与固定运行镜像"
        return {
            "cosign": cosign,
            "cosign_status": cosign_status,
            "cosign_ready": cosign_ready,
            "history": historical,
            "live": live,
            "verification": self.last_verification,
            "threshold": self.threshold,
            "x402": self.x402,
            "job": job,
            "catalog": scenarios.catalog(),
            "scenario_results": dict(self.scenario_results),
        }

    def start(self, action, scenario_id=None):
        if action not in (
            "run",
            "verify",
            "scenario-run",
            "scenario-replay",
            "cosm2-run",
            "threshold-run",
            "x402-run",
        ):
            raise ValueError("unknown action")
        if action.startswith("scenario-") and scenario_id not in scenarios.SPECS:
            raise ValueError("unknown scenario")
        with self.lock:
            if self.job and self.job["status"] == "running":
                return False
            if action == "verify" and not (self.live_folder or self.history):
                raise ValueError("no approved run")
            target = self.live_folder or self.history
            try:
                target_run_id = summary(target)["run_id"] if action == "verify" else None
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ValueError("invalid verification target") from exc
            job_id = str(uuid.uuid4())
            event_run_id = job_id
            replay_folder = None
            if action == "scenario-replay":
                replay_folder = safe_path(REPO / scenarios.HISTORY)
                saved = replay_folder / events.FILE
                try:
                    if not saved.is_symlink() and saved.stat().st_size <= events.MAX_FILE_BYTES:
                        candidate = str(uuid.UUID(json.loads(saved.read_text())["run_id"]))
                        events.page(replay_folder, candidate, scenario_id, replay=True)
                        event_run_id = candidate
                except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                    pass
            self.job = {
                "id": job_id,
                "run_id": event_run_id,
                "action": action,
                "status": "running",
                "started": time.time(),
                "stage": {
                    "run": "正在启动独占环境",
                    "verify": "正在离线验证原件与篡改副本",
                    "cosm2-run": "正在准备协同签名固定采购演示",
                    "threshold-run": "正在准备本机固定门限采购演示",
                    "x402-run": "正在准备本机固定 x402 采购演示（首次运行需构建隔离镜像）",
                    "scenario-run": "准备固定场景独占环境",
                    "scenario-replay": "校验历史记录",
                }[action],
            }
            if scenario_id:
                self.scenario_results.pop(scenario_id, None)
                self.job["scenario_id"] = scenario_id
                self.job["stage"] = (
                    "校验历史记录" if action == "scenario-replay" else "准备固定场景独占环境"
                )
                self.runs[event_run_id] = (
                    replay_folder
                    if action == "scenario-replay"
                    else safe_path(REPO / "artifacts/teacher-scenarios-live" / event_run_id),
                    scenario_id,
                    action == "scenario-replay",
                )
            else:
                self.runs[event_run_id] = (
                    safe_path(REPO / "artifacts/teacher-demo-live" / event_run_id),
                    "normal" if action == "run" else "verification",
                    False,
                )
            if len(self.runs) > 32:
                oldest = next(iter(self.runs))
                del self.runs[oldest]
            target = self.live_folder or self.history
            if action == "verify":
                self.job["target_run_id"] = target_run_id
            threading.Thread(
                target=self._work, args=(action, target, scenario_id), daemon=True
            ).start()
            return True

    def event_page(self, run_id, after_seq, limit):
        with self.lock:
            target = self.runs.get(run_id)
        if target is None:
            raise KeyError("unknown run")
        folder, scenario_id, replay = target
        return events.page(
            safe_path(folder),
            run_id,
            scenario_id,
            after_seq=after_seq,
            limit=limit,
            replay=replay,
        )

    def _work(self, action, target, scenario_id=None):
        try:
            if action == "scenario-replay":
                data = scenarios.result(
                    safe_path(REPO / scenarios.HISTORY), scenario_id, historical=True
                )
                with self.lock:
                    self.scenario_results[scenario_id] = data
                    self.job.update(
                        status="success",
                        stage="历史记录校验完成；不是本次安全运行",
                        result=data,
                        ended=time.time(),
                    )
                return
            before = set(target.parent.glob("verify-*")) if action == "verify" else set()
            command = [sys.executable, str(REPO / "tools/teacher_demo.py")]
            if action == "cosm2-run":
                command = [sys.executable, str(REPO / "tools/cosm2_desktop.py")]
            if action == "threshold-run":
                command = [sys.executable, str(REPO / "tools/threshold_desktop.py")]
            if action == "x402-run":
                command = [
                    sys.executable,
                    str(REPO / "tools/x402_desktop.py"),
                    "--approval-scheme",
                    "sm2-2p",
                ]
            if action == "scenario-run":
                command = [
                    sys.executable,
                    str(REPO / "tools/teacher_demo_scenarios.py"),
                    "--scenario",
                    scenario_id,
                    "--run-id",
                    self.job["run_id"],
                ]
            if action == "verify":
                command += ["--verify", str(safe_path(target))]
            process = self.launcher(
                command,
                cwd=REPO,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                stdin=subprocess.DEVNULL,
            )
            folder = None
            captures_folder = action in (
                "run",
                "scenario-run",
                "threshold-run",
                "x402-run",
                "cosm2-run",
            )
            for line in process.stdout:
                if captures_folder and line.startswith("结果目录："):
                    folder = Path(line.split("：", 1)[1].strip())
                    with self.lock:
                        self.job["stage"] = {
                            "scenario-run": "固定安全场景运行中：准备环境、执行检查与清理",
                            "cosm2-run": "协同签名运行中：真实授权链、独立授权侧签名方与受理事务",
                            "threshold-run": "门限固定演示运行中：真实签发、门限批准与拒绝用例",
                            "x402-run": "x402 固定演示运行中：真实 402、链上结算与拒绝用例",
                        }.get(action, "真实流程运行中：构建、授权、四工具执行与证据导出")
                # Raw process output is deliberately never returned to the browser.
            code = process.wait()
            with self.lock:
                self.job["native_exit"] = code
                self.job["actual_wait"] = True
            if folder is not None:
                folder = safe_path(folder)
                folder.relative_to(
                    REPO
                    / {
                        "scenario-run": "artifacts/teacher-scenarios-live",
                        "cosm2-run": "artifacts/cosm2-gateway-demo-live",
                        "threshold-run": "artifacts/threshold-gateway-demo-live",
                        "x402-run": "artifacts/x402-gateway-demo-live",
                    }.get(action, "artifacts/teacher-demo-live")
                )
            if code != 0:
                raise RuntimeError("child failed")
            if action == "scenario-run":
                data = scenarios.result(folder, scenario_id)
                self.scenario_results[scenario_id] = data
            elif action == "cosm2-run":
                data = cosm2_result(folder)
                if data["completed_at"] < int(self.job["started"]):
                    raise ValueError("COSM2 result predates this job")
                data.update(source="current-run", source_label="本次现场运行（本机会话）")
                self.cosign = data
            elif action == "threshold-run":
                data = threshold_result(folder)
                self.threshold = data
            elif action == "x402-run":
                data = x402_result(folder)
                self.x402 = data
            elif action == "run":
                data = summary(folder) if folder else None
                if data is None:
                    raise ValueError("no result")
                self.live_folder = folder
                pointer = REPO / "artifacts/teacher-demo-live/latest-run.txt"
                pointer.write_text(str(folder) + "\n")
            else:
                created = set(target.parent.glob("verify-*")) - before
                if len(created) != 1:
                    raise ValueError("ambiguous verification")
                data = verification(created.pop())
                data["run_id"] = summary(target)["run_id"]
                data["verified_at"] = int(time.time())
                self.last_verification = data
            with self.lock:
                self.job.update(
                    status="success",
                    stage={
                        "scenario-run": "真实场景断言通过且资源已清理",
                        "cosm2-run": "协同签名完成：六用例与真实三轮耗时已记录",
                        "threshold-run": "门限固定演示完成：用例结果与资源清理已记录",
                        "x402-run": "x402 固定演示完成：真实链上结算、用例结果与资源清理已记录",
                        "run": "真实运行已完成",
                        "verify": "原件通过，篡改副本已拒绝",
                    }[action],
                    result=data,
                    ended=time.time(),
                )
        except Exception:
            # Keep exclusivity until any launched child has actually exited.
            if "process" in locals():
                process.wait()
            if action == "scenario-run" and scenario_id in events.CASES:
                try:
                    run_id = self.job["run_id"]
                    events.fail(
                        safe_path(REPO / "artifacts/teacher-scenarios-live" / run_id),
                        run_id,
                        scenario_id,
                    )
                except (OSError, ValueError, KeyError, TypeError):
                    pass
            with self.lock:
                self.job.update(
                    status="failed",
                    stage="本次动作未成功；请由演示人员检查本机记录。历史回放仍可查看。",
                    ended=time.time(),
                )


def event_response(app, path):
    """Shared read-only event route; callers separately enforce their access boundary."""
    if len(path) > 256:
        return 400, {"error": "请求路径过长"}
    try:
        url = urlsplit(path)
        match = re.fullmatch(r"/api/runs/([^/]+)/events", url.path)
        if not match:
            return None
        # A path addressed to the event route with a malformed/non-canonical run
        # id is an invalid query (400); only a well-formed unknown UUID is 404.
        run_id = str(uuid.UUID(match[1]))
        if run_id != match[1]:
            raise ValueError("invalid run id")
        # An absent query is valid; older Pythons reject "" under strict parsing.
        query = (
            parse_qs(url.query, strict_parsing=True, keep_blank_values=True) if url.query else {}
        )
        if set(query) - {"after_seq", "limit"} or any(len(v) != 1 for v in query.values()):
            raise ValueError("invalid query")
        after_seq = int(query.get("after_seq", ["0"])[0])
        limit = int(query.get("limit", ["200"])[0])
        return 200, app.event_page(run_id, after_seq, limit)
    except KeyError:
        return 404, {"error": "运行不存在"}
    except (OSError, ValueError, TypeError):
        return 400, {"error": "事件查询无效"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, code, body, kind="application/json; charset=utf-8"):
        data = (
            json.dumps(body, ensure_ascii=False).encode() if not isinstance(body, bytes) else body
        )
        self.send_response(code)
        for k, v in {
            "Content-Type": kind,
            "Content-Length": str(len(data)),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
            ),
        }.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def valid_host(self):
        return self.headers.get_all("Host", []) == [f"127.0.0.1:{self.server.server_port}"]

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {"error": "仅允许本机地址"})
        if len(self.path) > 256:
            return self.reply(400, {"error": "请求路径过长"})
        origin = self.headers.get_all("Origin", [])
        if origin and origin != [f"http://127.0.0.1:{self.server.server_port}"]:
            return self.reply(403, {"error": "请求来源未获允许"})
        # Address-bar/bookmark navigation sends 'none'; cross-site API fetches stay denied.
        if self.headers.get("Sec-Fetch-Site") not in (None, "none", "same-origin"):
            return self.reply(403, {"error": "请求来源未获允许"})
        if self.path == "/api/state":
            return self.reply(200, self.server.app.state())
        if self.path == "/api/session":
            return self.reply(200, {"token": self.server.app.token})
        response = event_response(self.server.app, self.path)
        if response is not None:
            return self.reply(*response)
        files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/style.css": ("style.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        }
        if self.path not in files:
            return self.reply(404, {"error": "不存在"})
        name, kind = files[self.path]
        return self.reply(200, (STATIC / name).read_bytes(), kind)

    def do_POST(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if (
            not self.valid_host()
            or self.headers.get_all("Origin", []) != [origin]
            or self.headers.get("X-Demo-Token") != self.server.app.token
            or self.headers.get("Sec-Fetch-Site") not in (None, "same-origin")
            or self.headers.get("Content-Type") != "application/json"
        ):
            return self.reply(403, {"error": "请求来源未获允许"})
        scenario_match = re.fullmatch(r"/api/scenarios/([a-z-]+)/(run|replay)", self.path)
        if scenario_match and scenario_match[1] not in scenarios.SPECS:
            scenario_match = None
        cosm2_match = self.path == "/api/cosm2/run"
        threshold_match = self.path == "/api/threshold/run"
        x402_match = self.path == "/api/x402/run"
        if (
            self.path not in ("/api/run", "/api/verify")
            and not scenario_match
            and not cosm2_match
            and not threshold_match
            and not x402_match
        ):
            return self.reply(404, {"error": "不存在"})
        if self.headers.get("Transfer-Encoding") or self.headers.get_all("Content-Length", []) != [
            "2"
        ]:
            return self.reply(400, {"error": "只接受固定动作"})
        if self.rfile.read(2) != b"{}":
            return self.reply(400, {"error": "只接受固定动作"})
        try:
            if scenario_match:
                accepted = self.server.app.start("scenario-" + scenario_match[2], scenario_match[1])
            elif cosm2_match:
                accepted = self.server.app.start("cosm2-run")
            elif threshold_match:
                accepted = self.server.app.start("threshold-run")
            elif x402_match:
                accepted = self.server.app.start("x402-run")
            else:
                accepted = self.server.app.start(self.path.rsplit("/", 1)[1])
            return self.reply(202 if accepted else 409, {"accepted": accepted})
        except ValueError:
            return self.reply(409, {"error": "没有可验证的成功运行"})


def make_server(port=8765, app=None):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.app = app or DemoApp()
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f"老师演示页：http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("网页服务已停止；已启动的演示仍等待真实子进程完成。", flush=True)
        while server.app.job and server.app.job["status"] == "running":
            time.sleep(1)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
