"""Load a multi-file plugin, override its addend, edit and restore its helper."""
from pathlib import Path
import json
import os
import subprocess
import shutil
import sys
sys.dont_write_bytecode = True

FIXTURE = Path(__file__).resolve().parent
sys.path[:0] = [str(FIXTURE.parents[2]), str(FIXTURE.parents[2] / "src")]
from tests.fixtures.support.addition_sandboxes import main, workspace


def run(work, *, toolchain=None):
    workspace(FIXTURE, work)
    helper = work / "project/plugins/addition/math_support.py"
    original = helper.read_text()
    observations = []
    for phase, code, expected in [("baseline", original, 5), ("edited", original.replace("a + b", "a + b + 1"), 6), ("restored", original, 5)]:
        helper.write_text(code)
        stage = work / phase
        stage.mkdir()
        stage_workspace = {"roots": [{"id": "plugin-addition", "path": "project"}]}
        shutil.copytree(work / "project", stage / "project")
        (stage / "vibeflow_config.jsonc").write_text(json.dumps(stage_workspace))
        completed = subprocess.run([sys.executable, str(FIXTURE / "consumer.py"), str(stage)], cwd=stage,
            capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(FIXTURE.parents[2] / "src"), "PYTHONDONTWRITEBYTECODE": "1"})
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = json.loads(completed.stdout)
        observations.append({"phase": phase, "expected": expected, **result})
    return {"status": "PASS", "observations": observations}


if __name__ == "__main__":
    main(run, "Python plugin addition")
