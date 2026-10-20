"""Real subprocess checks for CI log confidentiality and failure preservation."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools.pr9_ci_run import run


@pytest.mark.parametrize(
    ("body", "no_skips", "expected"),
    [
        ("def test_ok(tmp_path):\n    assert True\n", True, 0),
        ("def test_fail(tmp_path):\n    assert False, 'PRIVATE_SENTINEL'\n", False, 1),
        (
            "import pytest\n@pytest.mark.skip(reason='PRIVATE_SENTINEL')\ndef test_skip(): pass\n",
            True,
            1,
        ),
        (
            "import pytest\n@pytest.mark.skip(reason='PRIVATE_SENTINEL')\ndef test_skip(): pass\n",
            False,
            0,
        ),
    ],
)
def test_real_pytest_counts_without_failure_text(tmp_path, capsys, body, no_skips, expected):
    sample = tmp_path / "test_sample.py"
    sample.write_text(body)
    output = tmp_path / "private"
    assert run(output, [sys.executable, "-m", "pytest", str(sample)], no_skips) == expected
    captured = capsys.readouterr()
    assert "PRIVATE_SENTINEL" not in captured.out + captured.err
    assert "counts=" in captured.out
    assert output.stat().st_mode & 0o777 == 0o700
    assert (output / "native.log").stat().st_mode & 0o777 == 0o600
    assert (output / "junit.xml").stat().st_mode & 0o777 == 0o600
    if "test_skip" not in body:
        assert (output / "pytest").is_dir()


def test_missing_junit_is_failure(tmp_path, capsys):
    assert run(tmp_path / "private", [sys.executable, "-c", "pass"]) == 1
    assert "JUnit missing" in capsys.readouterr().out


def test_existing_or_linked_root_is_preserved(tmp_path):
    marker = tmp_path / "marker"
    marker.write_text("preserve")
    linked = tmp_path / "link"
    linked.symlink_to(tmp_path, target_is_directory=True)
    for target in (tmp_path, linked / "new"):
        with pytest.raises(ValueError):
            run(target, [sys.executable, "-c", "pass"])
    assert marker.read_text() == "preserve"


def test_cancel_reaches_actual_child_and_cannot_pass(tmp_path):
    marker = tmp_path / "started"
    sample = tmp_path / "test_sample.py"
    sample.write_text(
        "import time\nfrom pathlib import Path\n"
        f"def test_wait():\n    Path({str(marker)!r}).touch()\n    time.sleep(120)\n"
    )
    runner = Path(__file__).resolve().parents[2] / "tools/pr9_ci_run.py"
    with (tmp_path / "controller.log").open("wb") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                str(runner),
                "--root",
                str(tmp_path / "private"),
                "--",
                sys.executable,
                "-m",
                "pytest",
                str(sample),
            ],
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 20
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            assert marker.exists()
            os.kill(process.pid, signal.SIGTERM)
            assert process.wait(timeout=25) == 130
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
