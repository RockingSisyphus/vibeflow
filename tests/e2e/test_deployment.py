"""Relocated deployable artifacts through normal application APIs."""
import json
from pathlib import Path
import shutil
import sys
import pytest
from .support import ROOT,cli,command,example,write


@pytest.mark.parametrize("execution", ["plan", "block", "compiled"])
def test_relocated_nodeset_bundle(tmp_path, execution):
    source = example(tmp_path / "source", "python/minimal")
    built = tmp_path / "built"
    cli(source, "build", "--workspace", source / "vibeflow_config.jsonc", "--config",
        source / "project/configs/config_with_imports.jsonc", "--out-dir", built)
    relocated = tmp_path / "relocated"
    built.rename(relocated)
    shutil.rmtree(source)
    application = write(tmp_path / "application.py", '''import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "_framework"))
from vibeflow.tooling.application.python import load_bundle
bundle = load_bundle(sys.argv[1])
result = bundle.run({}, run_root=sys.argv[3], runtime_options={"execution":sys.argv[2]})
print(json.dumps(result.public_outputs))
''')
    result = command(sys.executable, "-B", application, relocated, execution,
        tmp_path / "runs", cwd=tmp_path, env={"PYTHONPATH":None})
    assert json.loads(result.stdout) == {"value.out":5}, result.stdout

