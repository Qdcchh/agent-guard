"""Reproduce A6 vector figures from explicit strict COSM2 or historical sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Direct script execution must resolve the shared strict reader.
sys.path.insert(0, str(ROOT))
OUT = ROOT / "复赛冲刺材料-20261018/论文模板/figures"
SOURCE = "artifacts/threshold-gateway-demo-live/9982ea76-0998-4832-9eab-c65a6cea4548/result.json"
RUN = "9982ea76-0998-4832-9eab-c65a6cea4548"
COMMAND = "python tools/threshold_gateway_demo.py (existing controller live run; not rerun by A6)"
# "行动越权" = the requested tool/parameters exceed the leaf token scope (refused by the
# authorization domain). It is NOT scenario 3 (delegation expansion refused by the AS).
ROWS = ("盗令牌", "行动越权", "撤销后", "篡改金额", "单域签名", "伪造签名", "超预算")
COLS = ("AS", "授权域", "网关验签", "接受事务")
OBSERVED = {
    ("撤销后", "接受事务"): ("revoked-ancestor", "REVOKED", 403),
    ("篡改金额", "网关验签"): ("tampered-amount", "APPROVAL_MISMATCH", 409),
    ("伪造签名", "网关验签"): ("fake-signature", "INVALID_SIGNATURE", 401),
}


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    return json.loads(data, object_pairs_hook=pairs)


def build_index(root=ROOT, *, cosm2_run=None):
    if cosm2_run is not None:
        return build_cosm2_index(root, cosm2_run)
    path = root / SOURCE
    result = strict_json(path.read_text())
    expected = {
        "demo",
        "run_id",
        "profile",
        "passed",
        "cases",
        "operations",
        "approvals",
        "orders",
        "budget",
        "resources_remaining",
        "limitations",
    }
    if (
        set(result) != expected
        or result["run_id"] != RUN
        or result["demo"] != "threshold-gateway-purchase"
        or result["profile"] != "AG-GUARD-THRESHOLD-APPROVAL-1"
        or result["passed"] is not True
    ):
        raise ValueError("source schema or provenance mismatch")
    names = [case.get("name") for case in result["cases"]]
    if len(names) != len(set(names)) or set(names) != {
        "missing-approval",
        "insufficient-and-duplicate",
        "fake-signature",
        "valid-approval-one-order",
        "tampered-amount",
        "revoked-ancestor",
    }:
        raise ValueError("case set mismatch")
    cases = {case["name"]: case for case in result["cases"]}
    cells = []
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != "93af9f36d8e3b4515e1a0ff2193d9c47b912597570e6c10762752b8562f0b092":
        raise ValueError("historical source hash changed; review required")
    for scheme in ("sm2-2p", "frost-ed25519"):
        for row in ROWS:
            for col in COLS:
                cell = dict(
                    scheme=scheme,
                    attack=row,
                    location=col,
                    status="NOT_MEASURED",
                    code=None,
                    evidence_path=None,
                    sha256=None,
                    run_id=None,
                    command=None,
                    case=None,
                )
                if scheme == "frost-ed25519" and (row, col) in OBSERVED:
                    name, code, status = OBSERVED[row, col]
                    case = cases[name]
                    if (
                        set(case) != {"name", "passed", "http_status", "code"}
                        or case["passed"] is not True
                        or type(case["http_status"]) is not int
                        or case["http_status"] != status
                        or case["code"] != code
                    ):
                        raise ValueError("unknown code or invalid observed case")
                    cell.update(
                        status="OBSERVED",
                        code=code,
                        evidence_path=SOURCE,
                        sha256=digest,
                        run_id=RUN,
                        command=COMMAND,
                        case=name,
                    )
                cells.append(cell)
    return dict(
        schema="cosm2-figures-sources-v1",
        status="PARTIAL",
        cells=cells,
        design_source="复赛冲刺材料-20261018/01-双域协同SM2实施规划-A与B分工.md",
        limitations=[
            "COSM2 B1/B3/B7 absent: every COSM2 cell is NOT_MEASURED.",
            (
                "Only three FROST rejection cases mapped; no inference from missing approval "
                "or insufficient quorum to stolen-token/single-domain SM2 attacks."
            ),
            (
                "Local writable result JSON is historical evidence, "
                "not an independent cryptographic proof."
            ),
            (
                "Gateway column includes approval binding validation; "
                "downstream independent cosign verification is not implemented."
            ),
        ],
    )


# Case-to-cell mapping is a reviewed taxonomy. Codes are read from the actual
# observations and validated against the permitted refusal contract below.
COSM2_OBSERVATIONS = {
    "missing-approval": (None, "gateway", {"APPROVAL_REQUIRED"}),
    "exec-domain-alone": ("单域签名", "gateway", {"INVALID_SIGNATURE"}),
    "fake64-signature": ("伪造签名", "gateway", {"INVALID_SIGNATURE"}),
    "stolen-token-wrong-holder": ("盗令牌", "gateway", {"INVALID_SIGNATURE", "HOLDER_MISMATCH"}),
    "expanded-scope": ("行动越权", "authorization_domain", {"AUTHZ_SCOPE"}),
    "tampered-amount": ("篡改金额", "gateway", {"APPROVAL_MISMATCH"}),
    "over-remaining-budget": ("超预算", "authorization_domain", {"AUTHZ_OVER_BUDGET"}),
    "revoked-before-cosign": ("撤销后", "authorization_domain", {"AUTHZ_REVOKED"}),
    "revoked-after-cosign": ("撤销后", "gateway_acceptance", {"REVOKED"}),
}
EFFECT_OBSERVATIONS = {
    name: (None, "downstream", {"DOWNSTREAM_UNAUTHORIZED"})
    for name in (
        "downstream-no-approval",
        "downstream-changed-amount",
        "downstream-replay-new-operation",
    )
}
LOCATION_COLUMNS = {
    "gateway": "网关验签",
    "authorization_domain": "授权域",
    "gateway_acceptance": "接受事务",
}


def _read_source(root, path):
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("symlink evidence is not accepted")
    path.resolve().relative_to(root.resolve())
    if path.stat().st_size > 1_000_000:
        raise ValueError("oversized evidence")
    return strict_json(path.read_text()), hashlib.sha256(path.read_bytes()).hexdigest()


def _check_snapshot(value):
    if type(value) is not dict or set(value) != {
        "orders",
        "operations",
        "counters",
        "authz_sign_count",
    }:
        raise ValueError("invalid negative snapshot fields")
    for name in ("orders", "operations", "authz_sign_count"):
        if type(value[name]) is not int or value[name] < 0:
            raise ValueError("invalid negative snapshot count")
    counters = value["counters"]
    if type(counters) is not list or len(counters) != 3:
        raise ValueError("all three ancestor counters required")
    for depth, row in enumerate(counters):
        if type(row) is not list or len(row) != 5 or row[0] != depth:
            raise ValueError("invalid ancestor counter path")
        if any(type(number) is not int or number < 0 for number in row):
            raise ValueError("invalid ancestor counter type")


def build_cosm2_index(root, run_id):
    from tools.teacher_demo_server import validate_cosm2_result

    if type(run_id) is not str or str(uuid.UUID(run_id)) != run_id:
        raise ValueError("canonical run UUID required")
    root = Path(root)
    folder = root / "artifacts/cosm2-gateway-demo-live" / run_id
    result, result_sha = _read_source(root, folder / "result.json")
    validate_cosm2_result(result, run_id)
    if result["passed"] is not True or result["resources_remaining"] != 0:
        raise ValueError("failed or unclean run cannot supply accepted observations")
    negative, negative_sha = _read_source(root, folder / "negative-matrix.json")
    if (
        type(negative) is not dict
        or set(negative) != {"version", "run_id", "observations", "unobserved_locations"}
        or type(negative["version"]) is not int
        or negative["version"] != 1
        or negative["run_id"] != run_id
        or negative["unobserved_locations"] != "not triggered; no refusal claim"
    ):
        raise ValueError("negative matrix provenance mismatch")
    observations = negative["observations"]
    if type(observations) is not list or len(observations) not in (9, 12):
        raise ValueError("complete negative observation set required")
    allowed = COSM2_OBSERVATIONS | EFFECT_OBSERVATIONS
    observed = {}
    for observation in observations:
        if type(observation) is not dict or set(observation) != {
            "case_id",
            "location",
            "observed_code",
            "before",
            "after",
            "passed",
        }:
            raise ValueError("invalid negative observation fields")
        name = observation["case_id"]
        if type(name) is not str or name not in allowed or name in observed:
            raise ValueError("unknown or duplicate negative case")
        row, location, allowed_codes = allowed[name]
        if (
            observation["passed"] is not True
            or observation["location"] != location
            or type(observation["observed_code"]) is not str
            or observation["observed_code"] not in allowed_codes
        ):
            raise ValueError("unverified refusal code or location")
        _check_snapshot(observation["before"])
        _check_snapshot(observation["after"])
        if observation["before"] != observation["after"]:
            raise ValueError("negative case mutated effects, counters or signing count")
        if name in EFFECT_OBSERVATIONS and (
            observation["before"]["orders"] != 1 or observation["before"]["operations"] != 1
        ):
            raise ValueError("effect refusal must preserve the original single order")
        observed[name] = observation
    if set(observed) not in (set(COSM2_OBSERVATIONS), set(allowed)):
        raise ValueError("incomplete original or effect observation set")
    evidence_path = str((folder / "negative-matrix.json").relative_to(root))
    cells = []
    for row in ROWS:
        for col in COLS:
            cell = dict(
                scheme="sm2-2p",
                attack=row,
                location=col,
                status="NOT_TRIGGERED",
                code=None,
                evidence_path=evidence_path,
                sha256=negative_sha,
                run_id=run_id,
                command="python tools/cosm2_gateway_demo.py",
                case=None,
            )
            for name, observation in observed.items():
                mapped_row, location, _ = allowed[name]
                if row == mapped_row and col == LOCATION_COLUMNS[location]:
                    cell.update(status="OBSERVED", code=observation["observed_code"], case=name)
            cells.append(cell)
    return dict(
        schema="cosm2-figures-sources-v2",
        status="OBSERVED_FIXED_RUN",
        run_id=run_id,
        completed_at=result["completed_at"],
        cells=cells,
        sources={
            "result": {
                "path": str((folder / "result.json").relative_to(root)),
                "sha256": result_sha,
            },
            "negative_matrix": {"path": evidence_path, "sha256": negative_sha},
        },
        observations=observations,
        additional_effect_observations=[
            o for o in observations if o["case_id"] in EFFECT_OBSERVATIONS
        ],
        design_source="复赛冲刺材料-20261018/01-双域协同SM2实施规划-A与B分工.md",
        limitations=[
            "半诚实、同主机；参考曲线运算非常数时间。",
            "P1 独立进程不等于 OS 强制隔离；智能体不持份额。",
            "未触发格无拒绝或通过结论；仅固定运行集，不是普适安全证明。",
            "本地可写 JSON 为运行证据，不是独立密码学证明。",
            "B9 效果端独立验签状态单独验收，本图不提前宣称。",
        ],
    )


def draw(out, index, font):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("CN", str(font), subfontIndex=0))
    real = index["status"] == "OBSERVED_FIXED_RUN"
    ink, blue, pale = "#17334D", "#197B94", "#EDF5F8"

    def page(name, title, subtitle):
        c = canvas.Canvas(str(out / name), pagesize=(900, 560), invariant=1)
        c.setTitle(title)
        text(c, 28, 526, title, 19)
        text(c, 28, 500, subtitle, 11)
        return c

    def text(c, x, y, value, size=11):
        c.setFillColor(ink)
        c.setFont("CN", size)
        c.drawString(x, y, value)

    def note(c, x, y, value, size=11):
        c.setFillColor("#FFFFFF")
        c.rect(
            x - 3, y - 4, pdfmetrics.stringWidth(value, "CN", size) + 6, size + 8, fill=1, stroke=0
        )
        text(c, x, y, value, size)

    def box(c, x, y, w, h, lines, dashed=False):
        c.setStrokeColor(blue)
        c.setFillColor(pale)
        c.setDash(5, 3) if dashed else c.setDash()
        c.roundRect(x, y, w, h, 7, fill=1)
        c.setDash()
        for i, line in enumerate(lines):
            text(c, x + 12, y + h - 24 - i * 21, line)

    def arrow(c, x, y, xx, yy):
        c.setStrokeColor(blue)
        c.line(x, y, xx, yy)
        from math import atan2, cos, sin

        angle = atan2(yy - y, xx - x)
        for offset in (-0.55, 0.55):
            c.line(xx, yy, xx - 7 * cos(angle + offset), yy - 7 * sin(angle + offset))

    c = page(
        "fig-system.pdf",
        "系统模型：双域协同 SM2 签名",
        "已实现 B1-B7 的结构示意（非运行时序记录）"
        if real
        else "历史设计示意 · 当时尚未集成 COSM2",
    )
    box(c, 28, 365, 125, 70, ["用户", "确认任务与预算"])
    box(
        c,
        180,
        340,
        190,
        115,
        ["统筹代理 → 选品代理", "              → 执行代理", "智能体不持有任何份额"],
    )
    arrow(c, 153, 400, 180, 400)
    box(
        c,
        410,
        305,
        210,
        165,
        [
            "授权信任域（逻辑边界）",
            "AS：签发与收窄委托链",
            "P2：授权域签名者",
            "独立检查链、撤销、预算",
            "仅持本域份额",
        ],
        True,
    )
    box(
        c,
        655,
        305,
        217,
        165,
        [
            "执行信任域（逻辑边界）",
            "P1：执行域签名者",
            "核对请求事实、发起共签",
            "执行网关：标准 SM2 验签",
            "仅持本域份额",
        ],
        True,
    )
    arrow(c, 370, 405, 410, 405)
    arrow(c, 620, 365, 655, 365)
    box(c, 410, 150, 210, 100, ["授权与预算库", "P2 只读谓词（不预留）", "网关接受事务重查并预留"])
    arrow(c, 515, 305, 515, 250)
    c.line(655, 330, 638, 330)
    c.line(638, 330, 638, 200)
    arrow(c, 638, 200, 620, 200)
    box(
        c,
        655,
        150,
        217,
        100,
        [
            "下游模拟订单与证据",
            "幂等效果、回执、审计",
            "独立共签验签另见 B9 证据" if real else "独立共签验签属后续工作",
        ],
    )
    arrow(c, 760, 305, 760, 250)
    text(c, 28, 90, "边界：半诚实 · n=2 · 同主机逻辑隔离 · 参考曲线实现非常数时间", 12)
    text(c, 28, 64, "假设 AS、网关验签与状态库可信；不证明宿主机强制隔离；效果端能力单独验收。")
    c.save()
    c = page(
        "fig-protocol.pdf",
        "协议时序：结构化行动驱动三轮共签",
        "AG-COSM2-APPROVAL-1 · 已实现协议的结构示意，非运行事件回放"
        if real
        else "历史设计示意 · AG-COSM2-APPROVAL-1 · 当时尚未集成",
    )
    for x, label in ((160, "P1 · 执行域"), (510, "P2 · 授权域"), (790, "网关")):
        text(c, x - 55, 465, label, 13)
        c.setStrokeColor(blue)
        c.line(x, 440, x, 95)
    note(c, 28, 415, "双方各自从规范结构化行动重算消息与 SM3 摘要；P2 不接受 P1 提供的摘要。")
    arrow(c, 160, 365, 510, 365)
    text(c, 185, 380, "第1轮：Q1 + 结构化行动 + 叶令牌")
    box(
        c,
        350,
        250,
        330,
        90,
        [
            "P2 独立谓词：链签名/路径、撤销、剩余额度",
            "校验 Q1；只读查询，不预留预算",
            "任一失败即拒绝，不调用签名轮次",
        ],
    )
    arrow(c, 510, 220, 160, 220)
    text(c, 190, 235, "第2轮：(r, s2, s3)，销毁临时随机量")
    note(c, 28, 175, "第3轮：P1 合成 (r,s)，标准 SM2 验签；成败均销毁会话随机量")
    arrow(c, 160, 130, 790, 130)
    text(c, 200, 143, "批准信封 → 网关标准 SM2 验签 + 请求绑定 → 接受事务重查撤销/预算")
    text(
        c,
        28,
        53,
        "半诚实 · 同主机 · 非常数时间；签名后撤销仍由接受事务拦截，不以先前谓词替代原子检查。",
    )
    c.save()
    if real:
        c = page(
            "fig-negative.pdf",
            "负例矩阵：七类攻击在实际触发位置拒绝",
            "COSM2 固定运行：" + index["run_id"] + " · 空格未触发，不作通过/拒绝结论",
        )
        for j, col in enumerate(COLS):
            text(c, 165 + j * 177, 450, col, 12)
        for i, row in enumerate(ROWS):
            yy = 407 - i * 43
            text(c, 40, yy, row, 12)
            for j, col in enumerate(COLS):
                cell = next(
                    v for v in index["cells"] if v["attack"] == row and v["location"] == col
                )
                text(c, 165 + j * 177, yy, cell["code"] or "-", 9.5)
        text(
            c,
            28,
            104,
            "8 个触发位置有真实拒绝记录；其余 20 格 NOT_TRIGGERED。网关验签列含持有者证明验签与共签验签。",
            11,
        )
        text(
            c,
            28,
            81,
            "行动越权：请求的工具或参数超出令牌授权范围，由授权域拒签；不同于场景 3 的委托扩权（由 AS 拒绝）。",
            11,
        )
        text(
            c,
            28,
            58,
            "来源：同 run_id 的 result.json + negative-matrix.json；逐格命令、SHA-256 见来源索引。",
            10,
        )
        text(
            c,
            28,
            35,
            "半诚实 · 同主机 · 非常数时间；P1 进程分离不等于 OS 强制隔离；固定测试集非普适证明。",
            10,
        )
        c.save()
    else:
        c = page(
            "fig-negative.pdf",
            "负例矩阵：COSM2 未测，FROST 历史对照仅覆盖三格",
            "真实历史 run：" + RUN + "；不声称七攻击全覆盖",
        )
        cells = {(v["scheme"], v["attack"], v["location"]): v for v in index["cells"]}
        for scheme, y, label in [
            ("sm2-2p", 455, "COSM2 / sm2-2p：28 格全部未测（待 B）"),
            ("frost-ed25519", 260, "FROST-Ed25519 历史对照：3 格有证据，其余未测"),
        ]:
            text(c, 28, y, label, 12)
            for j, col in enumerate(COLS):
                text(c, 190 + j * 169, y - 23, col, 10)
            for i, row in enumerate(ROWS):
                yy = y - 43 - i * 20
                text(c, 40, yy, row, 10)
                for j, col in enumerate(COLS):
                    cell = cells[scheme, row, col]
                    text(c, 190 + j * 169, yy, cell["code"] or "未测", 8.5)
        text(
            c, 28, 56, "网关验签列包含批准与请求绑定检查；未测不代表通过、拒绝或该路径不适用。", 10
        )
        text(
            c,
            28,
            34,
            "来源、SHA-256、方案、逐格 run_id/命令见 cosm2-figures-sources.json；"
            "无 COSM2 拒绝实证。",
            10,
        )
        c.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument(
        "--font", type=Path, default=Path("/System/Library/Fonts/STHeiti Light.ttc")
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--cosm2-run", help="Explicit real B7 run UUID")
    source.add_argument(
        "--historical", action="store_true", help="Rebuild historical partial figures"
    )
    args = parser.parse_args()
    index = build_index(cosm2_run=args.cosm2_run)
    args.output.mkdir(parents=True, exist_ok=True)
    draw(args.output, index, args.font)
    (args.output / "cosm2-figures-sources.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    )
    print(index["status"] + ": generated three sourced vector PDFs")


if __name__ == "__main__":
    main()
