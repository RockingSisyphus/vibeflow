"""SDK values and configuration policy observed by real commands/applications."""
import json
from pathlib import Path
import sys

import pytest

from sandbox.python.runtime_observation.project import write_project
from .support import ROOT, cli, command, example, findings, workspace, write


DEFAULTS=[("string","a"),("integer",1),("boolean",True),("array",[]),("array",["a"]),
    ("object",{}),("object",{"a":1}),("number",1.5),("null",None),("array",[["a"],[]]),
    ("array",[{"a":1}]),("object",{"a":["x"]}),("object",{"a":{"b":1}}),("array",[{"a":[1,{"b":[]}]}])]


@pytest.mark.parametrize("schema,value",DEFAULTS)
def test_sdk_defaults_reach_actual_node_as_native_values(tmp_path,schema,value):
    project=tmp_path / "project"
    write_project(project,schema,value)
    cli(tmp_path,"validate","--workspace",tmp_path / "vibeflow_config.jsonc","--config",project / "workflow.jsonc","--json")
    request=write(tmp_path / "request.json",{"workspace":str(tmp_path / "vibeflow_config.jsonc")})
    result=command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py","source",project / "workflow.jsonc",
        request,tmp_path / "runs",cwd=tmp_path)
    payload=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
    assert payload["outputs"]["inspection"]=={"value":value,"native_type":type(value).__name__}


@pytest.mark.parametrize("execution",["plan","block","compiled"])
@pytest.mark.parametrize("selection",["defaults","call_override","runtime_override"])
def test_reusable_bundle_parameter_isolation(tmp_path,execution,selection):
    project=tmp_path / "project"
    write_project(project,"object",{"a":[{"b":[]}]})
    source=project / "nodes/steps.py"
    source.write_text(source.read_text(encoding="utf-8").replace(
        '        return {"result": {"value": value, "native_type": type(value).__name__}}',
        '''        nested = value["a"][0]["b"]
        before = len(nested)
        nested.append("visited")
        return {"result": {"before": before, "after": len(nested),
            "native": isinstance(value, dict) and isinstance(value["a"], list) and isinstance(nested, list)}}'''),encoding="utf-8")
    config=project / "workflow.jsonc"
    if selection=="call_override":
        data=json.loads(config.read_text(encoding="utf-8"));data["pipeline"]["nodes"][1]["config"]={"cleanup_record_roots":{"a":[{"b":["configured"]}]}}
        write(config,data)
    target=tmp_path / "bundle"
    cli(tmp_path,"build","--workspace",tmp_path / "vibeflow_config.jsonc","--config",config,"--out-dir",target)
    application=write(tmp_path / "application.py",'''import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1]) / "_framework"))
from vibeflow.tooling.application.python import load_bundle
bundle=load_bundle(sys.argv[1])
override={"a":[{"b":["configured"]}]}
options={"runtime_options":{"execution":sys.argv[2]},"run_dir":Path(sys.argv[1]).parent / "runs"}
if sys.argv[3]=="runtime_override": options["node_config_overrides"]={"inspect":{"cleanup_record_roots":override}}
runtime=bundle.create_runtime(**options)
rows=[runtime.run({}).get("inspection")["value"] for _ in range(2)]
other=bundle.create_runtime(**options)
rows.append(other.run({}).get("inspection")["value"])
print(json.dumps({"rows":rows,"caller_override":override}))
''')
    result=command(sys.executable,"-B",application,target,execution,selection,cwd=tmp_path,env={"PYTHONPATH":None})
    payload=json.loads(result.stdout)
    before=0 if selection=="defaults" else 1
    assert payload["rows"]==[{"before":before,"after":before+1,"native":True}]*3
    assert payload["caller_override"]=={"a":[{"b":["configured"]}]}


@pytest.mark.parametrize("change,expected",[
    ({},"WORKSPACE.PROJECT_TARGET.MISSING"),
    ({"project_target":"other"},"WORKSPACE.PROJECT_TARGET.INVALID"),
    ({"project_target":"python","javascript":{"host_extensions":[]}},"WORKSPACE.PROJECT_TARGET.FIELD_CONFLICT"),
    ({"project_target":"javascript","javascript":{"host_extensions":[]}},"WORKSPACE.PROJECT_CONFIG.JAVASCRIPT"),
    ({"project_target":"python","runtime":{"status_interval":0}},"WORKSPACE.PROJECT_CONFIG.RUNTIME"),
    ({"project_target":"python","quality":{}},"WORKSPACE.PROJECT_CONFIG.UNKNOWN_FIELD"),
])
def test_project_configuration_errors_use_official_commands(tmp_path,change,expected):
    source=example(tmp_path / "source","python/minimal")
    write(source / "project/vibeflow_project.jsonc",change)
    result=cli(source,"validate","--workspace",source / "vibeflow_config.jsonc","--config",
        source / "project/configs/config.jsonc","--json",success=False)
    payload=json.loads(result.stdout)
    assert result.returncode==1 and payload["code"]==expected,payload
    assert Path(payload["details"]["path"]) == source / "project/vibeflow_project.jsonc",payload


@pytest.mark.parametrize("field",["unexpected","quality","target"])
def test_workspace_rejects_unknown_and_retired_configuration(tmp_path,field):
    source=example(tmp_path / "source","python/minimal")
    path=source / "vibeflow_config.jsonc";data=json.loads(path.read_text(encoding="utf-8"));data[field]={};write(path,data)
    result=cli(source,"validate","--workspace",path,"--config",source / "project/configs/config.jsonc","--json",success=False)
    payload=json.loads(result.stdout)
    assert result.returncode==1 and payload["status"]=="ERROR",payload
    assert payload["code"]=="WORKSPACE.UNKNOWN_FIELD" and field in payload["error"],payload
    assert payload["details"]["path"]==str(path),payload


def test_normal_sdk_file_reference_with_literal_path_characters(tmp_path):
    source=example(tmp_path / "source","python/minimal")
    old=source / "project/nodes/steps.py"
    path=old.with_name("计算 %# steps.py");old.rename(path)
    # Keep decorated source discoverable through its literal filename: inspection
    # and AOT loading must preserve '%' and '#' as ordinary path characters.
    target=tmp_path / "bundle"
    cli(source,"build","--workspace",source / "vibeflow_config.jsonc","--config",
        source / "project/configs/config_with_imports.jsonc","--out-dir",target)
    request=write(tmp_path / "request.json",{})
    result=command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py","bundle",target,request,
        tmp_path / "runs",cwd=tmp_path,env={"PYTHONPATH":None})
    payload=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
    assert payload["outputs"]=={"value.out":5}
