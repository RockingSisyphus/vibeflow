"""End-to-end latency/resource observations plus refresh and workspace isolation."""
import json
import os
from pathlib import Path
import sys
from time import perf_counter

import pytest

from .support import ROOT, cli, command, example, write


def usage():
    if os.name == "nt":
        return None
    import resource
    value=resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"cpu_seconds":value.ru_utime+value.ru_stime,"max_rss_kib":value.ru_maxrss}


@pytest.mark.parametrize("language",["python","javascript"])
def test_end_to_end_refresh_cost_and_project_isolation(tmp_path,toolchain,record_property,language):
    rows=[]
    source=example(tmp_path / "source",language+"/minimal",toolchain if language=="javascript" else None)
    other=example(tmp_path / "other",language+"/minimal",toolchain if language=="javascript" else None)
    if language=="python":
        helper=source / "project/base_lib/math_tools.py"
        config="config_with_imports.jsonc"
    else:
        helper=source / "project/base_lib/text.ts"
        config="greeting.jsonc"
    original=helper.read_text(encoding="utf-8")
    edited=original.replace("left + right","left + right + 1") if language=="python" else original.replace("return value.trim()", "return value.trim().toUpperCase()")
    assert edited != original,"The example's public helper input changed; update this edit scenario."
    for phase,work,code in (("cold",source,original),("repeated",source,original),("edited",source,edited),
        ("other-project",other,original),("restored",source,original)):
        if work==source:write(helper,code)
        started=perf_counter();before=usage();target=tmp_path / phase
        args=["build","--workspace",work / "vibeflow_config.jsonc","--config",work / "project/configs" / config,"--out-dir",target]
        if language=="javascript":args += ["--target","node","--profile","single-esm"]
        built=cli(work,*args)
        if language=="python":
            request=write(tmp_path / "request.json",{})
            result=command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py","bundle",target,request,
                tmp_path / (phase+"-runs"),cwd=tmp_path,env={"PYTHONPATH":None})
            output=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))["outputs"]
            assert output=={"value.out":6 if phase=="edited" else 5},output
        else:
            request=write(tmp_path / "request.json",{"initial":{"name":"Ada"},"mode":"async","session":True})
            result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",json.loads(built.stdout)["entry"],request,cwd=tmp_path)
            output=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))["output"]
            assert output=={"greeting":f"Hello, {'ADA' if phase=='edited' else 'Ada'}! (2026-01-02T03:04:05Z)"},output
        after=usage()
        rows.append({"phase":phase,"seconds":perf_counter()-started,"output":output,
            "cpu_seconds":after["cpu_seconds"]-before["cpu_seconds"] if after else None,
            "worker_child_max_rss_kib":after["max_rss_kib"] if after else None})
    write(tmp_path / "performance.json",rows)
    record_property("end_to_end_performance",json.dumps(rows))
