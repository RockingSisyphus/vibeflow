"""Normal TypeScript/JavaScript builds and application-visible workflow results."""
import json
import shutil

import pytest

from .support import ROOT, cli, command, example, write


ROWS=[
 {"config":"linear","initial":{"x":10,"a":8,"b":3},"expected":{"result":15}},
 {"config":"nested_override","initial":{"x":5},"expected":{"result":19,"defaultResult":11}},
 {"config":"loop","initial":{"x":4},"expected":{"result":7,"iterations":3}},
 {"config":"nested_loop","initial":{"x":4},"expected":{"result":10,"iterations":2}},
 {"config":"edge_roles","initial":{"x":10},"expected":{"result":22}},
 {"config":"nested_async","initial":{"x":7},"mode":"async","session":True,"expected":{"doubled":14}},
 {"config":"detached","initial":{"x":7},"mode":"async","session":True,"expected":{"result":7}},
 {"config":"async_storage","initial":{"x":6,"key":"held"},"mode":"async","session":True,
  "expected":{"doubled":12,"value":"released"}},
 {"config":"loop_max_failure","initial":{"x":1},"error":"VF_MAX_STEPS"},
 {"config":"linear","initial":{},"error":"VF_INPUT_REQUIRED"},
 {"config":"linear","initial":{"x":"invalid"},"error":"VF_INPUT_SCHEMA"},
 {"config":"linear","initial":{"x":1,"surprise":1},"error":"VF_INPUT_UNKNOWN"},
]


@pytest.fixture(scope="module")
def javascript_builds(tmp_path_factory,toolchain):
    root=tmp_path_factory.mktemp("javascript-math")
    source=example(root / "source","javascript/workflow_math",toolchain)
    built={}
    for name in dict.fromkeys(row["config"] for row in ROWS):
        target=root / name
        cli(source,"build","--workspace",source / "vibeflow_config.jsonc","--config",
            source / f"project/configs/{name}.jsonc","--target","node","--profile","single-esm","--out-dir",target)
        built[name]=target / "index.js"
    shutil.rmtree(source)
    return built


@pytest.mark.parametrize("row",ROWS,ids=lambda row:row["config"]+"-"+row.get("error","result"))
@pytest.mark.parametrize("trace",["full","boundary","off"])
def test_javascript_deployed_results(javascript_builds,tmp_path,row,trace):
    request=write(tmp_path / "request.json",{**row,"options":{"trace":trace},"observe_business":True})
    result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",javascript_builds[row["config"]],request,
        cwd=tmp_path,success=not row.get("error"))
    prefix="FAILURE " if row.get("error") else "RESULT "
    payload=json.loads(next(line[len(prefix):] for line in result.stdout.splitlines() if line.startswith(prefix)))
    if row.get("error"):
        assert result.returncode==1 and payload["code"]==row["error"],payload
    else:
        assert payload["asynchronous"]==(row.get("mode")=="async"),payload
        for key,value in row["expected"].items():assert payload["output"][key]==value,payload
        if row["config"] in {"nested_async","detached"}:assert payload["audit"],payload
        kinds={event["kind"] for event in payload["events"]}
        if trace=="off":assert not kinds,payload
        else:
            assert {"run_start","run_end"} <= kinds,payload
            assert ("node_start" in kinds)==(trace=="full"),payload


@pytest.mark.parametrize("mode",["sync","async"])
@pytest.mark.parametrize("variant",["forward","reverse","exact_duplicate","overlap"])
def test_conditional_routes_and_unknown_status_control(tmp_path,toolchain,mode,variant):
    source=example(tmp_path / "source","javascript/workflow_math",toolchain)
    path=source / "project/configs/conditional_routes.jsonc"
    config=json.loads(path.read_text(encoding="utf-8"))
    routes=config["pipeline"]["edges"][1:3]
    config["pipeline"]["entry_mode"]=mode
    config["pipeline"]["edges"][1:3]={"forward":routes,"reverse":routes[::-1],"exact_duplicate":[*routes,routes[0]],
        "overlap":[*routes,{**routes[0],"when":"route != 'failed'"}]}[variant]
    write(path,config)
    target=tmp_path / "bundle"
    cli(source,"build","--workspace",source / "vibeflow_config.jsonc","--config",path,
        "--target","node","--profile","single-esm","--out-dir",target)
    for event in ("done","failed","unknown"):
        request=write(tmp_path / "request.json",{"mode":mode,"initial":{"event":event}})
        expected_error=event=="unknown" and variant!="overlap"
        result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",target / "index.js",request,
            cwd=tmp_path,success=not expected_error)
        prefix="FAILURE " if expected_error else "RESULT "
        payload=json.loads(next(line[len(prefix):] for line in result.stdout.splitlines() if line.startswith(prefix)))
        if expected_error:assert payload["code"]=="VF_OUTPUT_CARDINALITY",payload
        else:assert payload["output"]=={"result":43},payload


def test_typescript_app_supplies_live_clock(tmp_path,toolchain):
    source=example(tmp_path / "source","javascript/minimal",toolchain)
    target=tmp_path / "bundle"
    build=cli(source,"build","--workspace",source / "vibeflow_config.jsonc","--config",
        source / "project/configs/greeting.jsonc","--target","node","--profile","esm-module","--out-dir",target)
    shutil.rmtree(source)
    request=write(tmp_path / "request.json",{"initial":{"name":"  Ada  "},"mode":"async","session":True})
    entry=json.loads(build.stdout)["entry"]
    result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",entry,request,cwd=tmp_path)
    payload=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
    assert payload["output"]=={"greeting":"Hello, Ada! (2026-01-02T03:04:05Z)"},payload
