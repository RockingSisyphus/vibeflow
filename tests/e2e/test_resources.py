"""Multi-file Node/Library/Plugin bundles and literal user source paths."""
import json
from pathlib import Path
import shutil
import sys

import pytest

from .support import ROOT, cli, command, example, write


@pytest.mark.parametrize("language",["python","javascript"])
def test_multifile_resource_edit_rebuild_and_relocation(tmp_path,toolchain,language):
    work=example(tmp_path / "source",language+"/multifile_resources",toolchain if language=="javascript" else None)
    helper=work / ("project/base_lib/math_support.py" if language=="python" else "project/base_lib/math_support.ts")
    original=helper.read_text(encoding="utf-8")
    changed=original.replace("left + right","left + right + 1").replace("left+right","left+right+1")
    assert changed!=original
    builds=[]
    for phase,source,expected in (("baseline",original,6),("edited",changed,8),("restored",original,6)):
        write(helper,source)
        target=tmp_path / phase
        args=["build","--workspace",work / "vibeflow_config.jsonc","--config",work / "project/configs/workflow.jsonc","--out-dir",target]
        if language=="javascript":args += ["--target","node","--profile","single-esm"]
        built=cli(work,*args)
        builds.append((target,json.loads(built.stdout),expected))
    shutil.rmtree(work)
    for target,built,expected in builds:
        request=write(tmp_path / "request.json",{})
        if language=="python":
            result=command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py","bundle",target,request,tmp_path / "runs",
                cwd=tmp_path,env={"PYTHONPATH":None})
            output=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))["outputs"]
        else:
            result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",built["entry"],request,cwd=tmp_path)
            output=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))["output"]
        assert output=={"number":expected},output


@pytest.mark.parametrize("name",["带空格 file.ts","percent%20.ts","fragment#.ts"])
def test_javascript_sdk_literal_source_paths_build_and_execute(tmp_path,toolchain,name):
    work=example(tmp_path / "source","javascript/minimal",toolchain)
    (work / "project/nodes/greet.ts").rename(work / "project/nodes" / name)
    built=cli(work,"build","--workspace",work / "vibeflow_config.jsonc","--config",work / "project/configs/greeting.jsonc",
        "--target","node","--profile","single-esm","--out-dir",tmp_path / "bundle")
    shutil.rmtree(work)
    request=write(tmp_path / "request.json",{"initial":{"name":"Ada"},"session":True,"mode":"async"})
    result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",json.loads(built.stdout)["entry"],request,cwd=tmp_path)
    output=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))["output"]
    assert output=={"greeting":"Hello, Ada! (2026-01-02T03:04:05Z)"}
