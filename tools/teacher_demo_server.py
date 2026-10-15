"""Loopback-only, fixed-action presentation UI for teacher_demo.py."""

import argparse
import json
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "web/teacher-demo"
sys.path.insert(0, str(REPO))
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
        self.scenario_results = {}
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
        return {
            "history": historical,
            "live": live,
            "verification": self.last_verification,
            "job": job,
            "catalog": scenarios.catalog(),
            "scenario_results": dict(self.scenario_results),
        }

    def start(self, action, scenario_id=None):
        if action not in ("run", "verify", "scenario-run", "scenario-replay"):
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
            self.job = {
                "id": str(uuid.uuid4()),
                "action": action,
                "status": "running",
                "started": time.time(),
                "stage": "正在启动独占环境" if action == "run" else "正在离线验证原件与篡改副本",
            }
            if scenario_id:
                self.scenario_results.pop(scenario_id, None)
                self.job["scenario_id"] = scenario_id
                self.job["stage"] = (
                    "校验历史记录" if action == "scenario-replay" else "准备固定场景独占环境"
                )
            target = self.live_folder or self.history
            if action == "verify":
                self.job["target_run_id"] = target_run_id
            threading.Thread(
                target=self._work, args=(action, target, scenario_id), daemon=True
            ).start()
            return True

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
            if action == "scenario-run":
                command = [
                    sys.executable,
                    str(REPO / "tools/teacher_demo_scenarios.py"),
                    "--scenario",
                    scenario_id,
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
            for line in process.stdout:
                if action in ("run", "scenario-run") and line.startswith("结果目录："):
                    folder = Path(line.split("：", 1)[1].strip())
                    with self.lock:
                        self.job["stage"] = (
                            "固定安全场景运行中：准备环境、执行检查与清理"
                            if action == "scenario-run"
                            else "真实流程运行中：构建、授权、四工具执行与证据导出"
                        )
                # Raw process output is deliberately never returned to the browser.
            code = process.wait()
            with self.lock:
                self.job["native_exit"] = code
                self.job["actual_wait"] = True
            if folder is not None:
                folder = safe_path(folder)
                folder.relative_to(
                    REPO
                    / (
                        "artifacts/teacher-scenarios-live"
                        if action == "scenario-run"
                        else "artifacts/teacher-demo-live"
                    )
                )
            if code != 0:
                raise RuntimeError("child failed")
            if action == "scenario-run":
                data = scenarios.result(folder, scenario_id)
                self.scenario_results[scenario_id] = data
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
                    stage="真实场景断言通过且资源已清理"
                    if action == "scenario-run"
                    else "真实运行已完成"
                    if action == "run"
                    else "原件通过，篡改副本已拒绝",
                    result=data,
                    ended=time.time(),
                )
        except Exception:
            # Keep exclusivity until any launched child has actually exited.
            if "process" in locals():
                process.wait()
            with self.lock:
                self.job.update(
                    status="failed",
                    stage="本次动作未成功；请由演示人员检查本机记录。历史回放仍可查看。",
                    ended=time.time(),
                )


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
        if self.path == "/api/state":
            return self.reply(200, self.server.app.state())
        if self.path == "/api/session":
            return self.reply(200, {"token": self.server.app.token})
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
        if self.path not in ("/api/run", "/api/verify") and not scenario_match:
            return self.reply(404, {"error": "不存在"})
        if self.headers.get("Transfer-Encoding") or self.headers.get_all("Content-Length", []) != [
            "2"
        ]:
            return self.reply(400, {"error": "只接受固定动作"})
        if self.rfile.read(2) != b"{}":
            return self.reply(400, {"error": "只接受固定动作"})
        try:
            accepted = (
                self.server.app.start("scenario-" + scenario_match[2], scenario_match[1])
                if scenario_match
                else self.server.app.start(self.path.rsplit("/", 1)[1])
            )
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
