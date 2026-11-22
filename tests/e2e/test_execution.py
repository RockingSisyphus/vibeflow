"""Configured graph behavior through real source and deployed applications."""
import json

import pytest

from .support import ROOT, cli, command, example, findings, write
import sys


def cases(name):
    return json.loads((ROOT / "tests/e2e/cases" / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def projects(tmp_path_factory):
    root = tmp_path_factory.mktemp("execution-projects")
    values = {}
    for family, relative in (("math","python/workflow_math"),("execution","python/integration"),("piecewise","python/piecewise_math"),("objects","python/object_addition")):
        work = example(root / family, relative)
        values[family] = work
    configs = values["execution"] / "project/configs"
    async_lock = json.loads((configs / "pass_global_state_execution_lock.jsonc").read_text(encoding="utf-8"))
    async_lock["pipeline"]["entry_mode"] = "async"
    write(configs / "pass_global_state_execution_lock_async.jsonc", async_lock)
    return values


@pytest.fixture(scope="module")
def bundles(projects, tmp_path_factory):
    root = tmp_path_factory.mktemp("execution-bundles")
    result = {}
    def build(family, config):
        key = (family, config)
        if key not in result:
            target = root / family / config.removesuffix(".jsonc")
            cli(projects[family], "build", "--workspace", projects[family] / "vibeflow_config.jsonc",
                "--config", projects[family] / "project/configs" / config, "--out-dir", target)
            result[key] = target
        return result[key]
    return build


ROWS = [(family,row) for family,name in (("math","python_math.json"),("execution","python_execution.json"),("piecewise","python_piecewise.json"),("objects","python_objects.json"))
    for row in cases(name)]


DEPLOYED_ROWS = [(family,row,deployment) for family,row in ROWS for deployment in ("source","bundle")
    if deployment == "source" or not row.get("runtime_options",{}).get("allow_planned_stub")]

@pytest.mark.parametrize("family,row,deployment", DEPLOYED_ROWS,
    ids=[f"{family}-{row.get('name',row['config'])}-{deployment}" for family,row,deployment in DEPLOYED_ROWS])
@pytest.mark.parametrize("execution", ["plan","block","compiled"])
def test_python_graph_results(projects, bundles, tmp_path, family, row, execution, deployment):
    config = row["config"] + (".jsonc" if family != "execution" else "")
    path = projects[family] / "project/configs" / config if deployment == "source" else bundles(family,config)
    request = {**row,"workspace":str(projects[family] / "vibeflow_config.jsonc"),
        "runtime_options":{**row.get("runtime_options",{}),"execution":execution}}
    input_file = write(tmp_path / "request.json", request)
    planned_block = execution == "block" and row.get("runtime_options",{}).get("allow_planned_stub")
    result = command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py", deployment,path,
        input_file,tmp_path / "runs",cwd=tmp_path,env={"PYTHONPATH":None} if deployment == "bundle" else None,
        success=not planned_block)
    if planned_block:
        assert result.returncode != 0 and "block execution requires a compiled graph block" in result.stderr
        return
    payload = json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
    actual = payload["outputs"]
    for key, value in row["expected_outputs"].items():
        assert actual[key] == value, payload
    assert all(key not in actual for key in row.get("expected_absent_outputs",())), payload
    if row.get("initial_factory") == "training":
        assert actual["application_objects"] == {"model_returned":True,"optimizer_returned":True,"weight":.7,"steps":1}
    if row.get("initial_factory") == "objects":
        assert actual["application_objects"]=={"box_returned":True,"counter_returned":True,"nested_box_returned":True,
            "tags":["add","sandbox"],"unstable_is_nan":True,"value":row["expected_object_value"],"steps":row["expected_object_steps"]}
    assert payload["health"]["status"] in {"PASS","CONCERNS"}, payload
    assert set(row.get("expected_health_warnings",())) <= set(payload["health"]["warnings"]),payload


@pytest.mark.parametrize("row",cases("python_diagnostics.json"),ids=lambda row:row["config"])
def test_graph_error_boundaries(projects,tmp_path,row):
    work = projects["execution"]
    args = ["run" if row["kind"] in {"runtime_run","run"} else "validate","--workspace",work / "vibeflow_config.jsonc",
        "--config",work / "project/configs" / row["config"]]
    if args[0] == "run":
        args += ["--input",write(tmp_path / "input.json",row.get("initial",{})),"--run-root",tmp_path / "runs"]
        if row.get("runtime_options",{}).get("allow_planned_stub"):
            args += ["--allow-planned-stub"]
    else:
        args += ["--json"]
    result = cli(work,*args,success=False)
    assert result.returncode == row["expected_exit"],result.stdout + result.stderr
    if row["kind"] == "runtime_run":
        assert row["expect"] in result.stdout + result.stderr
        return
    report = findings(result)
    if row["expected_exit"] == 0:
        payload = json.loads(result.stdout)
        health = payload.get("health", payload)
        assert health["status"] == "CONCERNS" and not health["errors"],health
    matching = [item for item in report if row["expect"] in item["code"]]
    assert matching,result.stdout + result.stderr
    assert all(item["severity"] == row.get("severity", "warning" if row["kind"] == "concerns" else "error")
        for item in matching)
    # Topology diagnostics identify calls/owners; source diagnostics also carry
    # source_path or a concrete file location in the normal report.
    assert all(item.get("object_id") or item.get("source_path") or item.get("source_location",{}).get("path")
        for item in matching), matching
    assert not set(row.get("absent",())) & {item["code"] for item in report}
    for field in row.get("details",()):
        assert any(field in item.get("details",{}) for item in matching),(field,matching)


@pytest.mark.parametrize("execution",["plan","block","compiled"])
@pytest.mark.parametrize("trace",["full","boundary","off"])
def test_deployed_trace_modes_publish_user_visible_detail(bundles,tmp_path,execution,trace):
    from pathlib import Path
    target=bundles("math","nested.jsonc")
    request=write(tmp_path / "request.json",{"initial":{"calc.a":4,"calc.b":6},
        "runtime_options":{"execution":execution,"trace":trace}})
    result=command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py","bundle",target,request,
        tmp_path / "runs",cwd=tmp_path,env={"PYTHONPATH":None})
    payload=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
    assert payload["outputs"]=={"calc.scaled":20,"calc.branch":20,"calc.final":25}
    files=list(Path(payload["run_dir"]).glob("runtime_trace.jsonl"))
    events=[json.loads(line) for path in files for line in path.read_text(encoding="utf-8").splitlines()]
    kinds={event["kind"] for event in events}
    if trace=="off":
        assert kinds=={"runtime_summary"} and events[0]["stop_reason"]=="completed",events
    elif trace=="boundary":
        assert {"run_start","run_end"} <= kinds and "node" not in kinds,events
    else:
        assert any(event["kind"]=="node" and len(event["path"])>1 for event in events),events
