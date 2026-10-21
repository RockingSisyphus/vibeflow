"""Real builds of native workflows scheduled on the JavaScript event loop."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.fixtures.support.plugins import write_plugin
from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot


def _requires(type_key):
    return {"type": type_key, "cardinality": "exactly_one", "display_name": type_key}


def _provides(key, type_key=None):
    return {"key": key, "type": type_key or key, "display_name": key}


def _call(node_id, type_key, **options):
    return {"id": node_id, "definition_id": type_key, "display_name": node_id,
            "description": "A real scheduled workflow call.", **options}


def _body(input_type, output_type, leaf_type):
    return {"inputs": [{**_provides(input_type), "required": True}],
            "nodes": [_call("start", "fixture.terminal"), _call("calculate", leaf_type),
                      _call("end", "fixture.terminal",join_policy="all")],
            "edges": [["start", "calculate"], ["calculate", "end"]],
            "outputs": [{**_requires(output_type), "as": "answer" if leaf_type == "fixture.double" else output_type}]}


@pytest.mark.parametrize("kind", ("nodeset", "loop"))
@pytest.mark.parametrize("mode", ("join", "background"))
def test_native_composite_task_builds_and_returns_numeric_result(tmp_path, kind, mode):
    project = tmp_path / "project"
    project.mkdir()
    toolchain = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    (project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copy2(toolchain / name, project / name)
    (project / "nodes.mjs").write_text('''
export function terminal() { return {}; }
export function double(inputs) { return {answer: inputs["number.in"].value * 2}; }
export function mainline(inputs) { return {"mainline.answer": inputs["number.in"].value * 2}; }
export function increment(inputs) { return {"loop.next": inputs["loop.current"].value + 1}; }
''')
    resources = [{"kind": "data_schema", "type_key": name, "schema": {"type": "number"}}
                 for name in ("number.in", "number.out", "number.mainline", "loop.current", "loop.next", "loop.final")]
    for key, flow, requires, provides, export in (
        ("fixture.terminal", "terminal", [], [], "terminal"),
        ("fixture.double", "process", [_requires("number.in")], [_provides("answer", "number.out")], "double"),
        ("fixture.mainline", "process", [_requires("number.in")], [_provides("mainline.answer", "number.mainline")], "mainline"),
        ("fixture.increment", "process", [_requires("loop.current")], [_provides("loop.next")], "increment"),
    ):
        resources.append({'node_type': 'vibeflow.node', "kind": "node", 'id': key, "display_name": key,
            "description": "A declared immediate JavaScript implementation.", "version": "1", "flow_kind": flow,
            "rulesets": [], "contract": {"requires": requires, "provides": provides,
                "input_semantics": {item["type"]: ["Numeric input."] for item in requires},
                "output_semantics": {item["key"]: ["Numeric result."] for item in provides}},
            "implementations": [{"language": "javascript", "targets": ["node"], "completion": "immediate",
                "source": {"kind": "file", "ref": "nodes.mjs", "export": export}}]})
    input_type, output_type = ("number.in", "number.out") if kind=="nodeset" else ("loop.current", "loop.final")
    selection = write_plugin(project, resources, target="javascript")
    project_config = project / "vibeflow_project.jsonc"
    project_config.write_text(json.dumps({"project_target": "javascript",
                                        "javascript": {"package_root": "."}}))
    workspace = tmp_path / "vibeflow_config.jsonc"
    workspace.write_text(json.dumps({"roots": [{"id": "project", "path": "project"}]}))
    input_type, output_type, leaf_type = (("number.in", "number.out", "fixture.double") if kind == "nodeset"
                                       else ("loop.current", "loop.next", "fixture.increment"))
    nodeset = {"type_key": "fixture.body", "display_name": "Body", "description": "An embedded native graph.",
        "requires": [_requires(input_type)],
        "provides": [_provides("answer", output_type)] if kind == "nodeset" else [_provides(output_type)],
        "pipeline": _body(input_type, output_type, leaf_type)}
    call_options = {}
    if kind == "loop":
        call_options.update(requires=[_requires("loop.current")], provides=[_provides("loop.final")],
            loop={"body": "fixture.body", "max_iterations": 5, "stop_after": 3,
                "carry": [{"from": "loop.current", "as": "loop.current", "update": "loop.next"}],
                "outputs": [{"from": "loop.current", "as": "loop.final"}]})
    calls = [_call("start", "fixture.terminal"),
             _call("composite", "fixture.body" if kind == "nodeset" else "vibeflow.loop.while", **call_options),
             _call("end", "fixture.terminal",join_policy="all")]
    edges = [["start", "composite"], ["composite", "end"]]
    public_type = "number.out" if kind == "nodeset" else "loop.final"
    if mode == "background":
        calls.insert(2, _call("value", "fixture.mainline"))
        edges = [["start", "composite"], ["start", "value"], ["composite","end"], ["value", "end"]]
        public_type = "number.mainline"
    inputs = [{**_provides(input_type), "required": True}]
    if mode == "background" and kind == "loop":
        inputs.append({**_provides("number.in"), "required": True})
    config = project / "workflow.jsonc"
    (project / "body.jsonc").write_text(json.dumps(nodeset))
    config.write_text(json.dumps({"plugins": [selection], "rulesets": [], "nodeset_imports": [{"path": "body.jsonc"}],
        "pipeline": {"entry_mode": "async", "inputs": inputs, "nodes": calls, "edges": edges,
                     "outputs": [{**_requires(public_type), "as": "result"}]}}))
    result = build_project_aot(ProjectBuildRequest(workspace=workspace, config=config,
        out_dir=tmp_path / "dist", target="node", profile="single-esm"))
    root = result.prepared.plan.block(result.prepared.plan.entry_block)
    assert root.node("composite").child_block
    assert root.node("start").executor == root.node("end").executor == "current"
    runtime_inputs = {input_type: 2}
    if mode == "background" and kind == "loop":
        runtime_inputs["number.in"] = 2
    script = f'''
import {{runWorkflowAsync}} from {json.dumps(result.entry.as_uri())};
const trace = [];
const outputs = await runWorkflowAsync({json.dumps(runtime_inputs)}, {{trace: "full", onTrace: item => trace.push(item)}});
console.log(JSON.stringify({{outputs, tasks: trace.filter(item => item.kind.startsWith("task_"))}}));
'''
    completed = subprocess.run(["node", "--input-type=module", "-e", script],
        cwd=tmp_path, capture_output=True, text=True, check=True)
    observed = json.loads(completed.stdout)
    assert observed["outputs"] == {"result": 5 if kind == "loop" and mode == "join" else 4}
    assert observed["tasks"] == []
