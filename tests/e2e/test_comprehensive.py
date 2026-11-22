"""Complete application arithmetic, branches, nested loops and real user queues."""
import json
from pathlib import Path
import sys

import pytest

from .support import ROOT, cli, command, example, findings, write


SCENARIOS=[{"name":"positive","x":4,"result":480,"history":[236,238,240]},
    {"name":"negative","x":-3,"result":20,"history":[6,8,10]},
    {"name":"zero_input","x":0,"result":32,"history":[12,14,16]},
    {"name":"optional_offset","x":4,"offset":7,"result":487,"history":[236,238,240]},
    {"name":"repeat","x":1,"result":90,"history":[41,43,45]},
    {"name":"branch_boundary","x":-1,"result":10,"history":[1,3,5]}]


@pytest.fixture(scope="module",params=["python","javascript"])
def composite(tmp_path_factory,request,toolchain):
    language=request.param;root=tmp_path_factory.mktemp("composite-"+language)
    source=example(root / "source",language+"/comprehensive_math",toolchain if language=="javascript" else None)
    config=source / "project/configs/formula.jsonc"
    validated=cli(source,"validate","--workspace",source / "vibeflow_config.jsonc","--config",config,"--json")
    selected=[item for item in findings(validated) if item["code"] in {"MATH.MIN_T","MATH.T_ADVICE"}]
    assert {item["code"] for item in selected}=={"MATH.MIN_T","MATH.T_ADVICE"}
    assert all(item["severity"]=="warning" and item["source_location"]["path"].endswith("square.py" if language=="python" else "square.ts") for item in selected)
    assert all(item["details"]["minimum"]==10 and item["details"]["actual"]==6 for item in selected)
    args=["build","--workspace",source / "vibeflow_config.jsonc","--config",config,"--out-dir",root / "bundle"]
    if language=="javascript":args += ["--target","node","--profile","single-esm"]
    built=cli(source,*args)
    return language,source,root,Path(json.loads(built.stdout)["entry"]) if language=="javascript" else root / "bundle"


@pytest.mark.parametrize("case",SCENARIOS,ids=lambda case:case["name"])
def test_complete_formula_and_port_messages(composite,tmp_path,case):
    language,source,root,entry=composite
    request=write(tmp_path / "request.json",{"initial_factory":"formula","formula_value":case["x"],"mode":"async",
        "initial":{"math.offset":case["offset"]} if "offset" in case else {}})
    if language=="python":
        result=command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py","bundle",entry,request,
            tmp_path / "runs",cwd=tmp_path,env={"PYTHONPATH":None})
        payload=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
        output=dict(payload["outputs"]);ports=output.pop("application_ports")
    else:
        result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",entry,request,cwd=tmp_path)
        payload=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
        output=payload["output"];ports=payload["application_ports"]
    assert output=={"result":case["result"],"history":case["history"],"iterations":3}
    assert ports=={"received":[{"port":"math.in"}],"sent":[{"port":"math.out","value":case["result"]}]}


def test_source_edit_removes_both_custom_warnings(composite):
    language,source,root,entry=composite
    square=source / ("project/nodes/square.py" if language=="python" else "project/nodes/square.ts")
    original=square.read_text(encoding="utf-8")
    changed=original.replace("        return ",'        padding = "tttttttttt"\n        return ',1) if language=="python" else original.replace("return ",'const padding="tttttttttt";return ',1)
    assert changed!=original
    write(square,changed)
    try:
        result=cli(source,"validate","--workspace",source / "vibeflow_config.jsonc","--config",source / "project/configs/formula.jsonc","--json")
        assert not {"MATH.MIN_T","MATH.T_ADVICE"} & {item["code"] for item in findings(result)},result.stdout
    finally:write(square,original)
