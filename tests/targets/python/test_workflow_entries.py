"""Named entry selection preserves one execution path and shared joins."""
from dataclasses import replace
import json

import pytest

from tests.fixtures.support.strict_support import _registry, _seed_add_pipeline, _node_call
from tests.targets.python.test_code_plugins import EXECUTABLE, executable_project
from vibeflow.tooling.project.graph_config import parse_graph_config
from vibeflow.targets.python.runtime import PipelineRuntime
from vibeflow.targets.python.project.compiler import GraphCompileError
from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
from vibeflow.tooling.application.python.bundle import load_bundle


def graph(default=""):
    pipeline = _seed_add_pipeline(seed={"config": {"value": 4}}, add={"config": {"delta": 3}})
    pipeline["nodes"].append(_node_call("gui", "test.start", "GUI entry"))
    pipeline["edges"].append(["gui", "seed"])
    pipeline["nodes"][1]["join_policy"] = "all"
    pipeline["entries"] = {"cli": {"start": "start"}, "gui": {"start": "gui"}}
    if default:
        pipeline["default_entry"] = default
    return parse_graph_config({"pipeline": pipeline})


@pytest.mark.parametrize("execution", ["plan", "block", "compiled"])
@pytest.mark.parametrize("entry,other", [("cli", "gui"), ("gui", "start")])
def test_named_entries_do_not_execute_or_wait_for_unselected_branch(tmp_path, entry, other, execution):
    runtime = PipelineRuntime(graph(), registry=_registry(), entry=entry,
        runtime_options={"execution": execution}, run_dir=tmp_path / "run")
    result = runtime.run({})
    assert result.get("value.out")["value"] == 7
    assert other not in runtime._plan.frames
    assert len(runtime._plan.frames["seed"].incoming) == 1
    assert runtime.graph.selected_entry == entry


def test_entry_selection_and_invalid_start(tmp_path):
    with pytest.raises(ValueError, match="select a workflow entry"):
        PipelineRuntime(graph(), registry=_registry(), run_dir=tmp_path)
    runtime = PipelineRuntime(graph("gui"), registry=_registry(), run_dir=tmp_path)
    assert runtime.graph.selected_entry == "gui"
    bad = graph("gui")
    bad = replace(bad, entries={"bad": replace(bad.entries["gui"], start="seed")}, default_entry="")
    with pytest.raises(GraphCompileError, match="terminal without incoming"):
        PipelineRuntime(bad, registry=_registry(), entry="bad", run_dir=tmp_path)


@pytest.mark.parametrize("entry,key,value", [("cli", "value.in", 4), ("gui", "gui.in", 12)])
def test_entry_owns_its_public_input_output_contract(tmp_path, entry, key, value):
    from tests.fixtures.support.strict_support import _input_add_pipeline
    pipeline = _input_add_pipeline(add={"delta": 3})
    pipeline["nodes"].append(_node_call("gui", "test.start", "GUI entry"))
    pipeline["edges"].append(["gui", "add"])
    pipeline["inputs"], pipeline["outputs"] = [], []
    pipeline["entries"] = {name: {"start": start,
        "inputs": [{"key": name_key, "type": "value.in", "display_name": "Value", "required": True}],
        "outputs": [{"type": "value.out", "as": name+".result", "display_name": "Result", "cardinality": "exactly_one"}]}
        for name, start, name_key in [("cli", "start", "value.in"), ("gui", "gui", "gui.in")]}
    runtime = PipelineRuntime(parse_graph_config({"pipeline": pipeline}), registry=_registry(),
        entry=entry, run_dir=tmp_path / entry)
    assert runtime.run({key: value}).get(entry+".result")["value"] == value+3


def test_mutually_exclusive_preprocessors_can_provide_the_same_business_key(tmp_path):
    pipeline = _seed_add_pipeline(seed={"config": {"value": 4}}, add={"config": {"delta": 3}})
    pipeline["nodes"].extend([_node_call("gui", "test.start", "GUI entry"),
        _node_call("gui_seed", "test.seed", "GUI preprocessing", config={"value": 20})])
    pipeline["edges"].extend([["gui", "gui_seed"], ["gui_seed", "add"]])
    pipeline["entries"] = {"cli": {"start": "start"}, "gui": {"start": "gui"}}
    graph = parse_graph_config({"pipeline": pipeline})
    for name, expected in [("cli", 7), ("gui", 23)]:
        runtime = PipelineRuntime(graph, registry=_registry(), entry=name, run_dir=tmp_path / name)
        assert runtime.run({}).get("value.out")["value"] == expected
        assert runtime.compiled.providers["value.in"] == ("seed" if name == "cli" else "gui_seed")


@pytest.mark.parametrize("execution", ["plan", "block", "compiled"])
def test_aot_selects_saved_entry_without_compilation(tmp_path, monkeypatch, execution):
    workspace, config = executable_project(tmp_path, EXECUTABLE)
    data = json.loads(config.read_text())
    pipeline = data["pipeline"]
    pipeline["nodes"].extend([
        {"id": "gui", "type_used": "demo.start", "display_name": "GUI", "description": "GUI entry"},
        {"id": "end", "type_used": "demo.start", "display_name": "End", "description": "Finish"}])
    pipeline["edges"].extend([["gui", "demo"], ["demo", "end"]])
    pipeline["entries"] = {"cli": {"start": "start"}, "gui": {"start": "gui"}}
    config.write_text(json.dumps(data))
    built = build_python_aot(PythonBuildRequest(workspace, config, tmp_path / "bundle"))
    bundle = load_bundle(built.out_dir)

    def forbidden(*args, **kwargs):
        raise AssertionError("AOT recompiled the workflow")

    from vibeflow.targets.python.runtime import preparation, block_compiler
    monkeypatch.setattr(preparation, "prepare_python_workflow", forbidden)
    monkeypatch.setattr(block_compiler, "compile_blocks", forbidden)
    from vibeflow.core.workflows import entries
    monkeypatch.setattr(entries, "project_entry", forbidden)
    for entry, other in [("cli", "gui"), ("gui", "start")]:
        runtime = bundle.create_runtime(entry=entry, runtime_options={"execution": execution}, run_dir=tmp_path / entry)
        assert runtime.run({}).get("result")["value"] == 7
        assert other not in runtime._plan.frames


@pytest.mark.parametrize("execution", ["source", "plan", "block", "compiled"])
def test_entry_specific_contracts_and_duplicate_preprocessing_provider(tmp_path, execution):
    from tests.targets.python.test_code_plugins import project
    from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
    source = '''from vibeflow.targets.python.sdk import Plugin,node,data_schema
@node(type_key="boundary",flow_kind="terminal",contract={},rulesets=["vibeflow.process"])
class Boundary:
    def run_pure(self,inputs,params):return {}
@node(type_key="cli",rulesets=["vibeflow.process"],contract={"requires":[{"type":"cli.text","cardinality":"exactly_one","display_name":"Text"}],"provides":[{"key":"seed","type":"seed.value","display_name":"Seed"}],"input_semantics":{"cli.text":["CLI number"]},"output_semantics":{"seed":["Parsed value"]}})
class Cli:
    def run_pure(self,inputs,params):return {"seed":int(inputs["cli.text"]["value"])}
@node(type_key="gui",rulesets=["vibeflow.process"],contract={"requires":[{"type":"gui.number","cardinality":"exactly_one","display_name":"Value"}],"provides":[{"key":"seed","type":"seed.value","display_name":"Seed"}],"input_semantics":{"gui.number":["GUI number"]},"output_semantics":{"seed":["Numeric value"]}})
class Gui:
    def run_pure(self,inputs,params):return {"seed":inputs["gui.number"]["value"]}
@node(type_key="core",rulesets=["vibeflow.process"],contract={"requires":[{"type":"seed.value","cardinality":"exactly_one","display_name":"Seed"}],"provides":[{"key":"answer","type":"number","display_name":"Answer"}],"input_semantics":{"seed.value":["Preprocessed value"]},"output_semantics":{"answer":["Doubled value"]}})
class Core:
    def run_pure(self,inputs,params):return {"answer":inputs["seed.value"]["value"]*2}
plugin=Plugin(id="contracts",resources=[Boundary,Cli,Gui,Core,*[data_schema(type_key=k,schema={"type":t}) for k,t in [("cli.text","string"),("gui.number","number"),("seed.value","number"),("number","number")]]])
'''
    workspace, config = project(tmp_path, source)
    data = json.loads(config.read_text())
    data["rulesets"] = ["vibeflow.workflow"]
    data["pipeline"] = {"nodes": [{"id": key, "type_used": kind, "display_name": key, "description": key}
        for key,kind in [("cli_start","boundary"),("gui_start","boundary"),("cli","cli"),("gui","gui"),("core","core"),("end","boundary")]],
        "edges": [["cli_start","cli"],["gui_start","gui"],["cli","core"],["gui","core"],["core","end"]],
        "entries": {name: {"start":name+"_start",
            "inputs":[{"key":key,"type":kind,"required":True,"display_name":key}],
            "outputs":[{"type":"number","as":name+"_answer","cardinality":"exactly_one","display_name":"Answer"}]}
            for name,key,kind in [("cli","text","cli.text"),("gui","value","gui.number")]}}
    data["pipeline"]["nodes"][4]["join_policy"] = "all"
    config.write_text(json.dumps(data))
    bundle = None
    if execution != "source":
        bundle = load_bundle(build_python_aot(PythonBuildRequest(workspace,config,tmp_path / "bundle")).out_dir)
    for entry,initial in [("cli",{"text":"7"}),("gui",{"value":7})]:
        options = dict(entry=entry, initial=initial, run_root=tmp_path / "runs", runtime_options={"execution":"plan" if execution=="source" else execution})
        result = bundle.run(**options) if bundle else run_workspace_checked(config,workspace=workspace,**options)
        assert result.public_outputs == {entry+"_answer":14}
        assert result.context.get("runtime.stop_reason") == "completed"


def _partly_planned_project(root, kind):
    from tests.targets.python.test_code_plugins import project
    source = '''from vibeflow.targets.python.sdk import Plugin,node
@node(type_key="boundary",flow_kind="terminal",contract={},rulesets=["vibeflow.process"])
class Boundary:
    def run_pure(self,inputs,params):return {}
@node(type_key="work",contract={},rulesets=["vibeflow.process"])
class Work:
    def run_pure(self,inputs,params):return {}
plugin=Plugin(id="entries",resources=[Boundary,Work])
'''
    workspace, config = project(root, source)
    data = json.loads(config.read_text())
    data["rulesets"] = ["vibeflow.workflow"]
    nodes = [{"id": name, "type_used": node_type, "display_name": name, "description": name}
             for name, node_type in [("a", "boundary"), ("work", "work"), ("end_a", "boundary"),
                                     ("b", "boundary"), ("end_b", "boundary")]]
    draft = {"id": "draft", "type_used": "draft.work", "display_name": "Draft", "description": "Future branch"}
    if kind == "node":
        draft.update(status="planned", flow_kind="process", requires=[], provides=[])
    else:
        draft["type_used"] = "draftset"
        (root / "draftset.jsonc").write_text(json.dumps({"type_key": "draftset", "display_name": "Draft set",
            "description": "Future body", "status": "planned", "requires": [], "provides": []}))
        data["nodeset_imports"] = ["draftset.jsonc"]
    data["pipeline"] = {"nodes": [*nodes, draft], "edges": [["a", "work"], ["work", "end_a"], ["b", "draft"], ["draft", "end_b"]],
        "entries": {"ready": {"start": "a"}, "future": {"start": "b"}}, "default_entry": "ready"}
    config.write_text(json.dumps(data))
    return workspace, config


@pytest.mark.parametrize("kind", ["node", "nodeset"])
@pytest.mark.parametrize("execution", ["plan", "block", "compiled"])
def test_unselected_planned_branch_does_not_block_runtime_or_checked_run(tmp_path, kind, execution):
    from vibeflow.tooling.application.python.workspace_service import load_workspace_graph_for_export, run_workspace_checked
    from vibeflow.targets.python.runtime.errors import PipelineRuntimeError
    workspace, config = _partly_planned_project(tmp_path, kind)
    loaded = load_workspace_graph_for_export(config, workspace=workspace, validate_health=False)
    graph, _, registry = loaded[:3]
    assert loaded[4] is None, loaded[4].to_dict()
    runtime = PipelineRuntime(graph, registry=registry, run_dir=tmp_path / "direct", runtime_options={"execution": execution})
    runtime.run({})
    assert runtime._plan.order == ("a", "work", "end_a")
    with pytest.raises(PipelineRuntimeError, match="planned nodes/nodesets cannot run"):
        PipelineRuntime(graph, registry=registry, entry="future", run_dir=tmp_path / "blocked")
    result = run_workspace_checked(config, workspace=workspace, run_root=tmp_path / "runs",
        preview_root=tmp_path / "preview", runtime_options={"execution": execution})
    assert result.health.status not in {"FAIL", "ERROR"}
    assert result.health.info["entry"] == "ready"
    record = json.loads(next((tmp_path / "preview/vibeflow-preview/snapshots").glob("*/record.json")).read_text())
    assert record["entry"] == "ready" and record["status"] == "succeeded"


def test_run_history_keeps_each_selected_entry(tmp_path):
    from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
    workspace, config = _partly_planned_project(tmp_path, "node")
    data = json.loads(config.read_text())
    data["pipeline"]["nodes"] = [node for node in data["pipeline"]["nodes"] if node["id"] not in {"draft", "end_b"}]
    data["pipeline"]["edges"] = [["a", "work"], ["b", "work"], ["work", "end_a"]]
    config.write_text(json.dumps(data))
    for entry in ("ready", "future"):
        run_workspace_checked(config, workspace=workspace, entry=entry, run_root=tmp_path / "runs", preview_root=tmp_path / "preview")
    records = [json.loads(path.read_text()) for path in (tmp_path / "preview/vibeflow-preview/snapshots").glob("*/record.json")]
    assert {row["entry"] for row in records} == {"ready", "future"}
