"""Detached descendants and termination must leave a recorded, reaped tree."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

SUPERVISOR = Path(__file__).resolve().parents[2] / "src/vibeflow/tooling/application/process_supervisor.py"
pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux subreaper contract")


def _ready(path, process):
    deadline = time.monotonic() + 5
    while not path.exists() and time.monotonic() < deadline:
        assert process.poll() is None, "supervisor exited before the fixture was ready"
        time.sleep(0.02)
    assert path.exists(), "fixture did not become ready"


@pytest.mark.parametrize("terminate", [False, True])
def test_supervisor_reaps_detached_descendants_and_records_signal(tmp_path, terminate):
    marker = tmp_path / "pids.json"
    state = tmp_path / "state.json"
    descendant = ("import subprocess,sys,time,json,os;from pathlib import Path;"
                  "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True);"
                  f"Path({str(marker)!r}).write_text(json.dumps([os.getpid(),child.pid]));time.sleep(60)")
    root = ("import subprocess,sys,time,signal;from pathlib import Path;"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
            f"subprocess.Popen([sys.executable,'-c',{descendant!r}],start_new_session=True);"
            f"marker=Path({str(marker)!r})\n"
            "while not marker.exists():time.sleep(0.01)\n" +
            ("time.sleep(60)" if terminate else "sys.exit(7)"))
    process = subprocess.Popen([sys.executable, str(SUPERVISOR), "--state", str(state),
                                "--grace", "0.3", "--", sys.executable, "-c", root],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        _ready(marker, process)
        pids = json.loads(marker.read_text())
        if terminate:
            process.terminate()
        stdout, stderr = process.communicate(timeout=8)
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=8)
    assert process.returncode == (143 if terminate else 7), (stdout, stderr)
    result = json.loads(state.read_text())
    assert result["subreaper"] and result["cleanup_complete"]
    assert result["reaped_descendants"] >= 2
    assert result["received_signal"] == (signal.SIGTERM if terminate else None)
    assert result["status"] == ("interrupted" if terminate else "completed")
    assert all(not Path(f"/proc/{pid}").exists() for pid in pids)


def test_supervisor_timeout_is_not_reported_as_success(tmp_path):
    state = tmp_path / "state.json"
    result = subprocess.run([sys.executable, str(SUPERVISOR), "--state", str(state),
                             "--timeout", "0.2", "--grace", "0.2", "--",
                             sys.executable, "-c", "import time;time.sleep(60)"], timeout=5)
    report = json.loads(state.read_text())
    assert result.returncode == 124
    assert report["timed_out"] and report["cleanup_complete"]
    assert report["status"] == "interrupted"
