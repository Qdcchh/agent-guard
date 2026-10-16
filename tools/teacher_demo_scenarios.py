"""Fixed, bounded scenario adapter; protocol assertions live in existing integration tests."""

import argparse
import hashlib
import json
import shutil
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools import teacher_demo_events as demo_events  # noqa: E402

HISTORY = Path(
    "artifacts/workflow/A3.3-delivery-20261011/s1-scenarios-resume-r3-2d20e49c-4419-4786-882b-248356c1b44b/source-complete-r14"
)
PREFIX = "tests/integration/test_a33_scenarios.py::"
ATTACK = "test_attack_set_exact_binding_no_side_effects"
DELEGATE = "test_browser_root_and_two_delegations_real_https"
RACE = "test_root_mid_calls_revocation_final_clock_races"
RECOVERY = "test_process_crash_late_success_recovery_fault_matrix"
SPECS = {
    "stolen-token": (
        "盗取令牌但没有私钥",
        "使用窃取的令牌发起调用",
        "持有者密钥绑定",
        "拒绝无绑定私钥的调用且无业务副作用",
        [f"{ATTACK}[stolen-0]"],
    ),
    "signed-parameters": (
        "篡改签名后的参数",
        "修改已签名请求体或幂等键",
        "请求体与幂等键精确绑定",
        "篡改请求被拒绝且无业务副作用",
        [f"{ATTACK}[bound-body-0]", f"{ATTACK}[bound-idempotency-0]"],
    ),
    "delegation-scope": (
        "委托不得扩权",
        "子委托扩大金额或工具权限",
        "授权逐级收窄",
        "扩权委托被真实授权中心拒绝",
        [f"{DELEGATE}[amount-0]", f"{DELEGATE}[scope-0]"],
    ),
    "shared-budget": (
        "并发分支共享预算",
        "两个分支同时竞争根预算",
        "事务内共享祖先预算",
        "预算竞争满足原测试的接受数与账本断言",
        [f"{RACE}[two-branches-0]"],
    ),
    "replay-idempotency": (
        "重放与业务幂等",
        "重放证明并重复相同业务意图",
        "新鲜证明与业务幂等分离",
        "重放拒绝，真实下游同意图不重复执行",
        [
            f"{ATTACK}[replay-0]",
            "test_downstream_separate_domain_service_auth_and_effects[normal-0]",
        ],
    ),
    "revocation": (
        "撤销后拒绝新接受",
        "祖先撤销先提交，再请求接受",
        "事务内检查当前祖先状态",
        "撤销后新接受拒绝",
        [f"{RACE}[revoke-first-0]"],
    ),
    "recovery-evidence": (
        "故障恢复与证据",
        "下游成功后进程中断，再恢复",
        "不可变意图与真实进程恢复",
        "恢复断言及离线证据篡改断言通过",
        [
            f"{RECOVERY}[after-downstream-0]",
            "test_receipt_audit_export_faults_and_offline_mutations[before-sign-0]",
        ],
    ),
}


def catalog():
    return [
        dict(
            id=k,
            title=v[0],
            request=v[1],
            defense=v[2],
            expected=v[3],
            run_available=True,
            history_available=history_available(k),
        )
        for k, v in SPECS.items()
    ]


def history_available(scenario):
    try:
        result(REPO / HISTORY, scenario, historical=True)
        return True
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError):
        return False


def checked_file(root, relative):
    path = root / relative
    path.resolve().relative_to(root.resolve())
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("symlink evidence")
    return path


def result(folder, scenario, *, historical=False):
    expected = SPECS[scenario][4]
    native = json.loads(checked_file(folder, "native-junit-summary.json").read_text())
    if type(native.get("native_exit")) is not int or native["native_exit"] != 0:
        raise ValueError("native failure")
    xml = checked_file(folder, "test-results/registration-tls.xml")
    tree = ET.parse(xml)
    cases = tree.findall(".//testcase")
    names = [c.attrib["name"] for c in cases]
    if len(names) != len(set(names)):
        raise ValueError("duplicate test names")
    selected = [c for c in cases if c.attrib["name"] in expected]
    if any(c.attrib.get("classname") != "tests.integration.test_a33_scenarios" for c in selected):
        raise ValueError("unexpected testcase class")
    if {c.attrib["name"] for c in selected} != set(expected):
        raise ValueError("incomplete test set")
    snapshot = json.loads(checked_file(folder, "test-snapshot-sha256.json").read_text())
    if not snapshot or "integration/test_a33_scenarios.py" not in snapshot:
        raise ValueError("missing test snapshot")
    for name, digest in snapshot.items():
        if ".." in Path(name).parts or Path(name).is_absolute() or not name.endswith(".py"):
            raise ValueError("invalid snapshot manifest")
        if (
            hashlib.sha256(checked_file(folder, "tests-snapshot/" + name).read_bytes()).hexdigest()
            != digest
        ):
            raise ValueError("snapshot mismatch")
    cleanup = json.loads(checked_file(folder, "cleanup.json").read_text())
    if not historical:
        parent = json.loads(checked_file(folder, "scenario-native-exit.json").read_text())
        if (
            parent.get("actual_wait") is not True
            or type(parent.get("native_exit")) is not int
            or parent["native_exit"] != 0
        ):
            raise ValueError("actual native completion absent")
    if not historical and cleanup.get("resources_remaining") != 0:
        raise ValueError("cleanup incomplete")
    if historical and not cleanup.get("exact_removed_fullIDs"):
        raise ValueError("historical cleanup absent")
    checks = [
        dict(
            name=c.attrib["name"],
            status="failed"
            if c.find("failure") is not None or c.find("error") is not None
            else "skipped"
            if c.find("skipped") is not None
            else "passed",
        )
        for c in selected
    ]
    if any(c["status"] != "passed" for c in checks):
        raise ValueError("scenario assertions failed")
    suite = tree.find(".//testsuite")
    completed_at = None
    if suite is not None and suite.get("timestamp"):
        stamp = datetime.fromisoformat(suite.attrib["timestamp"])
        if stamp.tzinfo is not None:
            completed_at = int(stamp.timestamp() + float(suite.get("time", "0")))
    budget = None
    if scenario == "shared-budget":
        test_source = checked_file(
            folder, "tests-snapshot/integration/test_a33_scenarios.py"
        ).read_text()
        required = (
            "assert sum(status == 202 for status, _ in answers) == 1",
            "assert root == (70000, 1)",
            "assert _counts(f)[3:] == (1, 1)",
        )
        if any(assertion not in test_source for assertion in required):
            raise ValueError("budget assertion source absent")
        budget = (
            "已通过测试的断言值，不是独立查询读数：两个并发分支仅接受1个；根预留70000分（700元）、预留调用1次；运行后回执待发布记录1个、下游操作1个。断言源SHA-256："
            + snapshot["integration/test_a33_scenarios.py"]
        )

    return dict(
        scenario_id=scenario,
        mode="history_replay" if historical else "current_run",
        status="passed",
        total=len(checks),
        passed=len(checks),
        failed=0,
        skipped=0,
        source_label="A3.3 source r14 历史自查记录（非本次运行，非联合验收）"
        if historical
        else "本次隔离 wheel 运行",
        checks=checks,
        budget=budget,
        observed=SPECS[scenario][3] + "；这是通过的测试断言，不是新的独立验收。",
        evidence=dict(
            native_exit=0,
            xml_sha256=hashlib.sha256(xml.read_bytes()).hexdigest(),
            snapshot_verified=True,
        ),
        completed_at=completed_at,
        completed_at_basis="JUnit开始时间加总耗时推算" if completed_at is not None else "UNKNOWN",
        read_at=int(time.time()),
    )


class DeadlineCalls:
    """Use Owner's kill-and-wait TimeoutExpired path; cleanup has its own finite calls."""

    deadline = None

    def call(self, argv, *, timeout=120, **kwargs):
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("bounded scenario deadline")
            timeout = min(timeout, remaining)
        return super().call(argv, timeout=timeout, **kwargs)


def run(scenarios, run_id=None):
    from deploy.demo.supervisor import Owner, atomic

    ident = str(uuid.UUID(run_id)) if run_id is not None else str(uuid.uuid4())
    folder = REPO / "artifacts/teacher-scenarios-live" / ident
    print("结果目录：" + str(folder), flush=True)

    class BoundedOwner(DeadlineCalls, Owner):
        pass

    owner = BoundedOwner(
        SimpleNamespace(
            run_id=ident,
            owner_id="teacher-scenarios-" + ident,
            evidence=str(folder),
            mode="wheel",
            capacity_items=1,
        )
    )
    snapshot = folder / "tests-snapshot"
    shutil.copytree(REPO / "tests", snapshot, ignore=shutil.ignore_patterns("__pycache__"))
    atomic(
        folder / "test-snapshot-sha256.json",
        {
            p.relative_to(snapshot).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in snapshot.rglob("*.py")
        },
    )
    results = folder / "test-results"
    results.mkdir()
    nodes = [PREFIX + n for s in scenarios for n in SPECS[s][4]]
    code = 1

    owner.deadline = time.monotonic() + 900
    try:
        owner.setup()
        for domain in ("authority", "downstream", "audit"):
            owner.call(
                [
                    "docker",
                    "exec",
                    owner.ids["pg-" + domain],
                    "psql",
                    "-U",
                    "postgres",
                    "-d",
                    "ag_" + domain,
                    "-c",
                    "CREATE DATABASE ag_teacher_test TEMPLATE template0 "
                    'ENCODING UTF8 LC_COLLATE "C" LC_CTYPE "C";',
                ]
            )
        program = """import json,os,subprocess,sys
from pathlib import Path
from psycopg.conninfo import make_conninfo
for domain,key in [
 ('authority','AGENT_GUARD_TEST_DATABASE_URL'),
 ('downstream','AGENT_GUARD_A31_TEST_DOWNSTREAM_DATABASE_URL'),
 ('audit','AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL')]:
 os.environ[key]=make_conninfo(host='pg-'+domain+'.agent-guard.test',
  dbname='ag_teacher_test',user='postgres',
  password=Path('/owned/pg/'+domain+'/admin-password').read_text(),
  sslmode='verify-full',sslrootcert='/owned/run/operator/ca.pem')
os.environ['AG31_SERVICE_EVIDENCE_DIR']='/results/native'
Path('/results/native').mkdir(mode=0o700)
command=[sys.executable,'-m','pytest',*NODES,'-q','-o','cache_dir=/results/cache',
 '--junitxml=/results/registration-tls.xml']
raise SystemExit(subprocess.run(command,cwd='/testsource').returncode)
""".replace("NODES", repr(nodes))
        name = owner.project + "-scenario-controller"
        command = [
            "docker",
            "create",
            "--name",
            name,
            "--label",
            "agent-guard.owner=" + owner.owner,
            "--label",
            "agent-guard.run=" + owner.run,
            "--network",
            owner.project + "-authority",
            "--mount",
            "type=volume,src=" + owner.project + "-private,dst=/owned,readonly",
            "--mount",
            "type=bind,src=" + str(snapshot) + ",dst=/testsource/tests,readonly",
            "--mount",
            "type=bind,src=" + str(results) + ",dst=/results",
            owner.image,
            "python",
            "-c",
            program,
        ]
        owner.call(command)
        owner.capture("scenario-controller", name)
        for domain in ("downstream", "audit"):
            owner.call(
                [
                    "docker",
                    "network",
                    "connect",
                    owner.project + "-" + domain,
                    owner.ids["scenario-controller"],
                ]
            )
        stop_events = threading.Event()

        def collect_events():
            while not stop_events.wait(0.25):
                try:
                    demo_events.persist(folder, ident, scenarios[0])
                except (OSError, ValueError, json.JSONDecodeError):
                    # A witness may still be being written; final validation is strict.
                    pass

        collector = None
        if len(scenarios) == 1 and scenarios[0] in demo_events.CASES:
            collector = threading.Thread(target=collect_events, daemon=True)
            collector.start()
        try:
            completed = owner.call(
                ["docker", "start", "-a", owner.ids["scenario-controller"]],
                timeout=600,
                allow=True,
            )
        finally:
            stop_events.set()
            if collector is not None:
                collector.join(timeout=2)
        code = completed.returncode
        if code:
            raise ValueError("scenario controller failed")
        cases = ET.parse(results / "registration-tls.xml").findall(".//testcase")
        if {c.attrib["name"] for c in cases} != {n.split("::")[-1] for n in nodes}:
            raise ValueError("unexpected test selection")
        atomic(folder / "native-junit-summary.json", dict(native_exit=code, testcases=len(cases)))
    finally:
        owner.deadline = None
        owner.cleanup()
        atomic(folder / "scenario-native-exit.json", dict(native_exit=code, actual_wait=True))
    for scenario in scenarios:
        result(folder, scenario)
        recorded = demo_events.persist(folder, ident, scenario, terminal=True)
        if scenario in demo_events.CASES and not recorded:
            raise ValueError("required event witness absent")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=tuple(SPECS), required=True)
    parser.add_argument("--run-id", type=uuid.UUID)
    args = parser.parse_args()
    ident = str(args.run_id or uuid.uuid4())
    try:
        return run([args.scenario], ident)
    except Exception:
        if args.scenario in demo_events.CASES:
            try:
                demo_events.fail(
                    REPO / "artifacts/teacher-scenarios-live" / ident,
                    ident,
                    args.scenario,
                )
            except (OSError, ValueError):
                pass
        raise


if __name__ == "__main__":
    sys.path.insert(0, str(REPO))
    raise SystemExit(main())
