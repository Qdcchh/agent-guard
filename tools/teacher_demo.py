"""Presentation helper for the existing isolated demo; never changes protocol logic."""

import argparse
import json
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def show(folder):
    folder = Path(folder).resolve()
    result = folder / "normal-result"
    outcome = read(folder / "manager-native-exit.json")
    if outcome["native_exit"] != 0:
        raise ValueError("本轮未通过，请检查私密日志；不能作为成功演示。")
    report = read(result / "normal-report.json")
    oracle = read(result / "database-oracle.json")
    print("\n这是已完成运行的结果回放，运行 ID：", report["run_id"])
    print("三代理独立 UID：", report["holder_uids"])
    print("四工具操作数：", len(report["operation_ids"]))
    print("四工具回执：", [q["receipt_status"] for q in report["queries"]])
    print("实际订单：", oracle["real_orders"], "；实际通知：", oracle["real_notifications"])
    print("预算单位：分；根 / 中间 / 末级授权：")
    for row in oracle["ancestor_counters"]:
        depth, limit, calls, reserved, settled, calls_reserved, calls_settled = row
        print(
            f"  深度 {depth}：额度 {limit / 100:.2f} 元，已结算 {settled / 100:.2f} 元，"
            f"预留 {reserved} 分；调用 {calls_settled}/{calls}，预留调用 {calls_reserved}"
        )
    print("资源剩余：", read(folder / "cleanup.json")["resources_remaining"])
    print("公开证据：", result / "task-bundle.ndjson")
    print("说明：合成采购、确定性代理；本次演练不等于完整规模实验或联合验收。")


def run():
    ident = str(uuid.uuid4())
    parent = REPO / "artifacts" / "teacher-demo-live" / ident
    parent.mkdir(parents=True, mode=0o700)
    folder = parent / "run"
    cmd = [
        "python3",
        str(REPO / "deploy/demo/supervisor.py"),
        "--run-id",
        ident,
        "--owner-id",
        "teacher-demo-" + ident,
        "--evidence",
        str(folder),
        "--mode",
        "wheel",
        "--cap-seconds",
        "900",
    ]
    print("开始全新隔离演示。首次构建取决于网络；最长 15 分钟。", flush=True)
    print("结果目录：", folder, flush=True)
    started = time.monotonic()
    with (parent / "stdout.log").open("xb") as out, (parent / "stderr.log").open("xb") as err:
        child = subprocess.Popen(
            cmd, cwd=REPO, stdout=out, stderr=err, stdin=subprocess.DEVNULL, start_new_session=True
        )
        try:
            while child.poll() is None:
                print(
                    f"运行中，已用 {int(time.monotonic() - started)} 秒："
                    "构建 / 授权 / 执行 / 导出或等待授权到期。",
                    flush=True,
                )
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    pass
        except KeyboardInterrupt:
            child.send_signal(signal.SIGINT)
            print("已要求停止，等待自有资源清理……", flush=True)
        code = child.wait()
    (parent / "parent-wait.json").write_text(
        json.dumps(
            {"native_exit": code, "actual_wait": True, "ended": time.time(), "pid": child.pid}
        )
    )
    if code != 0:
        print("演示未成功；日志保留在", parent)
        return 1
    show(folder)
    return 0


def verify(folder):
    """Verify real public evidence, then a modified copy, without network access."""
    folder = Path(folder).resolve()
    if read(folder / "manager-native-exit.json")["native_exit"] != 0:
        raise ValueError("只能验证已成功完成的演示。")
    result = folder / "normal-result"
    run_id = read(result / "normal-report.json")["run_id"]
    image = "agent-guard-normal-wheel:" + run_id
    destination = folder.parent / ("verify-" + str(uuid.uuid4()))
    destination.mkdir(mode=0o700)
    inputs = destination / "inputs"
    inputs.mkdir(mode=0o700)
    for name in ("task-bundle.ndjson", "public-trust.json", "external-pin.json"):
        shutil.copyfile(result / name, inputs / name)
    rows = (inputs / "task-bundle.ndjson").read_text().splitlines()
    for index, line in enumerate(rows):
        row = json.loads(line)
        if isinstance(row.get("data"), str) and row["data"]:
            row["data"] = ("A" if row["data"][0] != "A" else "B") + row["data"][1:]
            rows[index] = json.dumps(row, separators=(",", ":"))
            break
    else:
        raise ValueError("没有找到可修改的证据数据帧。")
    (inputs / "tampered.ndjson").write_text("\n".join(rows) + "\n")
    for label, bundle, expected in (
        ("原始证据", "task-bundle.ndjson", 0),
        ("篡改副本", "tampered.ndjson", 2),
    ):
        name = "teacher-verify-" + str(uuid.uuid4())
        output_name = "original.json" if expected == 0 else "tampered.json"
        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--label",
            "agent-guard.owner=" + name,
            "--network",
            "none",
            "-v",
            str(inputs) + ":/inputs:ro",
            "-v",
            str(destination) + ":/output",
            "--entrypoint",
            "python",
            image,
            "-m",
            "agent_guard.evidence.verify_cli",
            "--bundle",
            "/inputs/" + bundle,
            "--trust",
            "/inputs/public-trust.json",
            "--external-pin",
            "/inputs/external-pin.json",
            "--report",
            "/output/" + output_name,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=120)
        finally:
            found = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "agent-guard.owner"}}',
                    name,
                ],
                capture_output=True,
                text=True,
            )
            if found.returncode == 0 and found.stdout.strip() == name:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=True)
        (destination / (output_name + ".native.json")).write_text(
            json.dumps(
                {"native_exit": proc.returncode, "actual_wait": True, "expected_exit": expected}
            )
        )
        if proc.returncode != expected:
            raise RuntimeError(
                f"{label}结果不符合预期，实际退出码 {proc.returncode}；保留记录：{destination}"
            )
        print(label, "：验证通过" if expected == 0 else "：检测到篡改，拒绝通过")
        if expected == 0:
            report = read(destination / output_name)
            for key in ("cryptographic_consistency", "current_authorization", "downstream_effect"):
                if key in report:
                    print(" ", key, "=", report[key])
    print("两次验证均禁用网络；只改副本，原始证据未改动。结果：", destination)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--show", type=Path, help="回放某个已完成 run 目录，不启动任何服务")
    mode.add_argument("--verify", type=Path, help="离线验证原件，再验证篡改副本")
    args = parser.parse_args()
    if args.show:
        show(args.show)
        return 0
    if args.verify:
        return verify(args.verify)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
