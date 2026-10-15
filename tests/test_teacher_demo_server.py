"""Boundary checks for local UI; all process doubles remain test-only."""

import http.client
import io
import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from tools import teacher_demo_server as demo


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def successful_run(folder):
    write(folder / "manager-native-exit.json", {"native_exit": 0})
    write(
        folder / "normal-result/normal-report.json",
        {
            "run_id": str(uuid.uuid4()),
            "holder_uids": [1, 2, 3],
            "operation_ids": ["a", "b", "c", "d"],
            "queries": [{"receipt_status": "READY", "receipt_jws": "SECRET"}] * 4,
            "private": "SECRET",
        },
    )
    write(
        folder / "normal-result/database-oracle.json",
        {
            "real_orders": 1,
            "real_notifications": 1,
            "token_sha256": "SECRET",
            "ancestor_counters": [
                [0, 100000, 12, 0, 70000, 0, 4],
                [1, 80000, 10, 0, 70000, 0, 4],
                [2, 70000, 8, 0, 70000, 0, 4],
            ],
        },
    )
    write(folder / "cleanup.json", {"resources_remaining": 0, "private": "SECRET"})


class FakeProcess:
    def __init__(self, output="", code=0, release=None):
        self.stdout = io.StringIO(output)
        self.code = code
        self.release = release
        self.waited = False

    def wait(self):
        if self.release:
            self.release.wait(3)
        self.waited = True
        return self.code


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.patch = patch.object(demo, "REPO", self.repo)
        self.patch.start()
        self.historical = self.repo / "artifacts/teacher-demo-20261015/approved/run"
        successful_run(self.historical)
        pointer = self.repo / "artifacts/teacher-demo-20261015/latest-run.txt"
        pointer.write_text(str(self.historical))

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def complete(self, app):
        deadline = time.monotonic() + 3
        while app.job["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertNotEqual(app.job["status"], "running")

    def test_summary_allowlist_and_missing_data(self):
        app = demo.DemoApp()
        encoded = json.dumps(app.state())
        self.assertNotIn("SECRET", encoded)
        self.assertNotIn("receipt_jws", encoded)
        self.assertNotIn(str(self.repo), encoded)
        (self.historical / "cleanup.json").unlink()
        self.assertIsNone(app.state()["history"])

    def test_path_traversal_and_symlinks(self):
        with self.assertRaises(ValueError):
            demo.safe_path(self.repo / "artifacts/../private.json")
        outside = self.repo / "outside"
        outside.mkdir()
        link = self.repo / "artifacts/link"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            demo.safe_path(link / "private.json")
        with self.assertRaises(ValueError):
            demo.safe_path(outside)

    def test_mutual_exclusion_and_actual_parent_wait(self):
        release = threading.Event()
        folder = self.repo / "artifacts/teacher-demo-live/owned/run"
        successful_run(folder)
        child = FakeProcess("结果目录：" + str(folder) + "\nSECRET\n", release=release)
        calls = []

        def launcher(command, **kwargs):
            calls.append(command)
            return child

        app = demo.DemoApp(launcher=launcher)
        self.assertTrue(app.start("run"))
        self.assertFalse(app.start("run"))
        self.assertFalse(app.start("verify"))
        self.assertEqual(app.state()["job"]["status"], "running")
        release.set()
        self.complete(app)
        self.assertTrue(child.waited)
        self.assertEqual(app.job["status"], "success")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], [demo.sys.executable, str(self.repo / "tools/teacher_demo.py")])
        self.assertNotIn("SECRET", json.dumps(app.state()))
        self.assertIsNotNone(app.state()["live"])

    def test_child_failure_and_invalid_success_are_failures(self):
        for code, output in [
            (9, "SECRET"),
            (0, ""),
            (0, "结果目录：" + str(self.repo / "private") + "\n"),
        ]:
            child = FakeProcess(output, code)
            app = demo.DemoApp(launcher=lambda *_args, child=child, **_kwargs: child)
            app.start("run")
            self.complete(app)
            self.assertEqual(app.job["status"], "failed")
            self.assertTrue(child.waited)
            self.assertNotIn("result", app.job)

    def test_verification_binds_only_new_directory(self):
        old = self.historical.parent / "verify-old"
        old.mkdir()
        created = self.historical.parent / "verify-new"

        def launcher(command, **_kwargs):
            self.assertEqual(command[-2:], ["--verify", str(self.historical)])
            for label, code in [("original", 0), ("tampered", 2)]:
                write(
                    created / (label + ".json.native.json"),
                    {"actual_wait": True, "native_exit": code},
                )
            write(
                created / "original.json",
                {
                    "cryptographic_consistency": "VERIFIED",
                    "current_auth": "UNKNOWN",
                    "tail": 0,
                    "private": "SECRET",
                },
            )
            return FakeProcess()

        app = demo.DemoApp(launcher=launcher)
        app.start("verify")
        self.complete(app)
        self.assertEqual(app.job["status"], "success")
        self.assertEqual(app.state()["verification"]["boundaries"]["current_auth"], "UNKNOWN")
        self.assertNotIn("private", app.state()["verification"]["boundaries"])
        self.assertEqual(app.job["target_run_id"], demo.summary(self.historical)["run_id"])

    def test_damaged_verify_target_does_not_leave_running_job(self):
        app = demo.DemoApp()
        (self.historical / "cleanup.json").unlink()
        with self.assertRaises(ValueError):
            app.start("verify")
        self.assertIsNone(app.job)

    def test_no_new_verification_is_not_old_success(self):
        app = demo.DemoApp(launcher=lambda *_args, **_kwargs: FakeProcess())
        app.start("verify")
        self.complete(app)
        self.assertEqual(app.job["status"], "failed")
        self.assertIsNone(app.last_verification)

    def test_http_host_origin_csrf_paths_and_double_click(self):
        release = threading.Event()
        app = demo.DemoApp(launcher=lambda *_args, **_kwargs: FakeProcess(code=1, release=release))
        server = demo.make_server(0, app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"

        def request(method, path, headers=None, body=None):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            result = response.status, response.read(), dict(response.getheaders())
            conn.close()
            return result

        try:
            status, body, headers = request("GET", "/api/state")
            self.assertEqual(status, 200)
            self.assertNotIn(b"SECRET", body)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(request("GET", "/api/state", {"Host": "evil.test"})[0], 403)
            for path in ["/../README.md", "/%2e%2e/README.md", "/artifacts/run", "/?file=private"]:
                self.assertEqual(request("GET", path)[0], 404)
            valid = {
                "Origin": origin,
                "Content-Type": "application/json",
                "X-Demo-Token": app.token,
            }
            for change in [
                {"Origin": "https://evil.test"},
                {"X-Demo-Token": "bad"},
                {"Content-Type": "text/plain"},
                {"Sec-Fetch-Site": "cross-site"},
            ]:
                self.assertEqual(request("POST", "/api/run", valid | change, "{}")[0], 403)
            self.assertEqual(request("POST", "/api/run", {}, "{}")[0], 403)
            self.assertEqual(request("POST", "/api/run", valid, '{"command":"id"}')[0], 400)
            self.assertEqual(request("POST", "/api/other", valid, "{}")[0], 404)
            self.assertEqual(request("POST", "/api/run", valid, "{}")[0], 202)
            self.assertEqual(request("POST", "/api/run", valid, "{}")[0], 409)
            self.assertEqual(request("POST", "/api/verify", valid, "{}")[0], 409)
        finally:
            release.set()
            self.complete(app)
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
