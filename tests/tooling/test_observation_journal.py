"""A worker exception or termination must retain its completed observations."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import pytest


@pytest.mark.parametrize("ending", ["success", "exception", "signal"])
def test_worker_checkpoints_without_claiming_incomplete_results(tmp_path, ending):
    repo = Path(__file__).resolve().parents[2]
    fixtures = repo / "tests/fixtures/rule_gaps"
    copied = tmp_path / "fixture"
    copied.mkdir()
    for name in ["worker.py", "common.py"]:
        shutil.copy2(fixtures / name, copied / name)
    final = {"success": "return [value]", "exception": "raise RuntimeError('injected collection failure')",
             "signal": "import time;time.sleep(60)"}[ending]
    (copied / "probe.py").write_text("from common import row\n"
        "def run_cases(*args):\n"
        "    value=row('completed.case','Completed','probe',{'status':'PASS'})\n"
        "    " + final + "\n")
    output = tmp_path / "observations.json"
    journal = output.with_suffix(".partial.jsonl")
    command = [sys.executable, str(copied / "worker.py"), "--group", "probe",
               "--work", str(tmp_path / "work"), "--output", str(output)]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(repo), str(repo / "src")]),
           "PYTHONDONTWRITEBYTECODE": "1"}
    child = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        if ending == "signal":
            deadline = time.monotonic() + 5
            while (not journal.exists() or not journal.stat().st_size) and time.monotonic() < deadline:
                assert child.poll() is None
                time.sleep(0.02)
            assert journal.exists() and journal.stat().st_size
            child.terminate()
        stdout, stderr = child.communicate(timeout=8)
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()
    observations = [json.loads(line) for line in journal.read_text().splitlines()]
    assert [r["id"] for r in observations] == ["completed.case"]
    if ending == "success":
        assert child.returncode == 0, stderr
        assert json.loads(output.read_text()) == observations
    else:
        assert child.returncode == (143 if ending == "signal" else 1), (stdout, stderr)
        assert not output.exists()
        error = json.loads(output.with_suffix(".error.json").read_text())
        assert error["status"] == ("interrupted" if ending == "signal" else "failed")
        if ending == "exception":
            assert "injected collection failure" in error["traceback"]
    before = journal.read_bytes()
    duplicate = subprocess.run(command, env=env, capture_output=True, text=True, timeout=8)
    assert duplicate.returncode != 0 and journal.read_bytes() == before
