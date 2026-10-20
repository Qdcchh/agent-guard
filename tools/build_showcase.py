"""Export checked summaries and an explicit file allowlist into a standalone ZIP."""

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools import teacher_demo_server as demo  # noqa: E402


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(output):
    stamp = datetime.now(timezone(timedelta(hours=8)))
    info = {
        "exported_at": stamp.isoformat(timespec="seconds"),
        "edition": "read-only historical snapshot",
        "notes": [
            "摘要经既有读取器校验，不构成独立验收或重新验签。",
            "原始证据、密钥、口令、令牌、日志及本机绝对路径不随包分发。",
            "无事件流回放；页面过程图仍为动画示意。",
        ],
        "sources": {},
        "unavailable": [],
    }
    app = demo.DemoApp()
    for scenario in demo.scenarios.SPECS:
        try:
            app.scenario_results[scenario] = demo.scenarios.result(
                REPO / demo.scenarios.HISTORY, scenario, historical=True
            )
        except (OSError, ValueError, KeyError, TypeError, demo.scenarios.ET.ParseError):
            info["unavailable"].append(scenario)
    state = app.state()
    state.update(read_only=True, live=None, job=None, cosign_ready=False)
    state["cosign_status"] = state["cosign_status"].replace(
        "可在本机重新运行", "本包仅展示保存结果"
    )
    for entry in state["catalog"]:
        entry["history_available"] = entry["id"] in state["scenario_results"]
    info["sources"]["scenarios"] = demo.scenarios.HISTORY.as_posix()
    if app.history:
        info["sources"]["procurement"] = app.history.relative_to(REPO).as_posix()
    else:
        info["unavailable"].append("procurement")
    if state["cosign"]:
        info["sources"]["cosign"] = (
            "artifacts/cosm2-gateway-demo-live/" + state["cosign"]["run_id"] + "/result.json"
        )
    else:
        info["unavailable"].append("cosign")
    for key, reader in (("threshold", demo.threshold_result), ("x402", demo.x402_result)):
        candidates = []
        root = REPO / f"artifacts/{key}-gateway-demo-live"
        for path in root.glob("*/result.json"):
            if not re.fullmatch(r"[0-9a-f-]{36}", path.parent.name):
                continue
            try:
                result = reader(path.parent)
                # Existing readers use the read time. Do not call it a run timestamp.
                result["completed_at"] = None
                result["source"] = "saved-result"
                result["source_label"] = "历史结果摘要；原记录未提供完成时间"
                candidates.append((path.stat().st_mtime_ns, path.as_posix(), result))
            except (OSError, ValueError, KeyError, TypeError, OverflowError):
                continue
        if candidates:
            _, source, state[key] = max(candidates, key=lambda item: (item[0], item[1]))
            info["sources"][key] = Path(source).relative_to(REPO).as_posix()
            info["notes"].append(f"{key} 按结果文件修改时间选择最近一份有效摘要；完成时间未知。")
        else:
            info["unavailable"].append(key)
    with tempfile.TemporaryDirectory(prefix="coseal-showcase-") as temporary:
        package = Path(temporary) / "coseal-showcase"
        package.mkdir()
        for name in (
            "server.py",
            "start.sh",
            "README.md",
            "nginx.conf.example",
            "coseal-showcase.service.example",
        ):
            shutil.copyfile(REPO / "deploy/showcase" / name, package / name)
        site = package / "site"
        site.mkdir()
        for name in ("index.html", "style.css", "app.js"):
            shutil.copyfile(demo.STATIC / name, site / name)
        script = (site / "app.js").read_text(encoding="utf-8")
        replacements = [
            (
                "公网只读展示：可浏览页面和真实记录；现场任务由演示者在本机启动，结果会自动更新。",
                (
                    "展示版 · 历史记录快照：可浏览讲解、动画和保存摘要；"
                    "不执行现场任务，记录不自动更新。"
                ),
            ),
            (
                ": '本次现场运行'}，${timeText(demo.completed_at)}",
                ": '保存结果回放'}，${timeText(demo.completed_at)}",
            ),
            (
                (
                    "if (kind === 'cosign' && !ui.state?.cosign_ready) "
                    "btn.textContent = '执行入口未就绪（缺少本机依赖）';"
                ),
                "if (ui.state?.read_only) btn.textContent = '展示版不执行现场任务';",
            ),
            (
                "前面各页的过程图是动画示意。这里只显示本机真实运行留下的结果，或者现场再跑一次。",
                "前面各页的过程图是动画示意。这里展示打包时保存的历史测试摘要，不是本次服务器运行。",
            ),
            (
                "本机服务已启动，Docker Desktop 正在运行",
                "展示版只需网页托管；历史记录为固定快照，无需 Docker",
            ),
            (
                "这里的结果全部来自本机服务；没有读到的内容显示为未读取。",
                "这里展示导出的历史结果摘要；没有有效记录的内容显示为未读取。",
            ),
            (
                "结果来自本机服务",
                "历史记录快照",
            ),
            (
                "本次三轮耗时（单次运行，非统计结果）",
                "保存记录中的三轮耗时（单次运行，非统计结果）",
            ),
            (
                '每一项对应一组真实的集成测试。"读取记录"回放之前保存的结果，"现场运行"重新执行一次；"看过程"打开对应讲解页。',
                '每一项对应一组历史集成测试摘要，已随包加载；"查看详情"展开记录，"看过程"打开讲解页。展示版不执行现场任务。',
            ),
        ]
        for old, new in replacements:
            if script.count(old) != 1:
                raise ValueError("frontend export replacement no longer matches")
            script = script.replace(old, new)
        (site / "app.js").write_text(script, encoding="utf-8")
        dump(site / "api/state", state)
        dump(site / "api/session", {"token": "", "read_only": True})
        dump(package / "snapshot-info.json", info)
        files = sorted(p for p in package.rglob("*") if p.is_file())
        manifest = "".join(
            hashlib.sha256(p.read_bytes()).hexdigest()
            + "  "
            + p.relative_to(package).as_posix()
            + "\n"
            for p in files
        )
        (package / "SHA256SUMS").write_text(manifest, encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(p for p in package.rglob("*") if p.is_file()):
                archive.write(path, path.relative_to(package.parent))
    print(
        json.dumps(
            {"zip": str(output), "bytes": output.stat().st_size, **info},
            ensure_ascii=False,
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=REPO.parent / "CoSeal-展示版部署包-20261020.zip"
    )
    args = parser.parse_args()
    build(args.output.resolve())


if __name__ == "__main__":
    main()
