"""Instance identity is ordinary Node context data, independent of Rule grants."""
import json
import subprocess

import pytest

from tests.targets.python.test_code_plugins import project
from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
from vibeflow.tooling.application.python.bundle import load_bundle


def test_source_and_aot_identity_need_no_capability_declaration_or_grant(tmp_path):
    source = '''from vibeflow.targets.python.sdk import node
@node(id="demo",node_type="vibeflow.node",flow_kind="terminal",rulesets=[],contract={
    "provides":[{"key":"identity","type":"example.identity","display_name":"Current instance"}],
    "output_semantics":{"identity":["Current workflow invocation identity"]}})
class Work:
    def run_pure(self,inputs,params,context):
        return {"identity":context.workflow.self()["id"]}
'''
    plugin = '''from vibeflow.targets.python.sdk import Plugin,data_schema
plugin=Plugin(id="identity.schemas",resources=[data_schema(type_key="example.identity",schema={"type":"string"})])
'''
    workspace, config = project(tmp_path / "project", source, plugin_source=plugin)
    data = json.loads(config.read_text(encoding="utf-8"))
    data["rulesets"] = ["vibeflow.workflow", {"rule_id":"vibeflow.capability.restrict"}]
    data["pipeline"]["outputs"] = [{"type":"example.identity","as":"identity","display_name":"Identity","cardinality":"exactly_one"}]
    config.write_text(json.dumps(data), encoding="utf-8")
    first = run_workspace_checked(config, workspace=workspace, run_root=tmp_path / "runs").public_outputs["identity"]
    second = run_workspace_checked(config, workspace=workspace, run_root=tmp_path / "runs").public_outputs["identity"]
    assert isinstance(first, str) and first and first != second
    built = build_python_aot(PythonBuildRequest(workspace, config, tmp_path / "bundle"))
    result = load_bundle(built.out_dir).run(workflow_instance_id="registered-instance", run_root=tmp_path / "aot-runs")
    assert result.public_outputs == {"identity":"registered-instance"}


@pytest.mark.parametrize("kind", ["nodeset", "loop"])
def test_javascript_identity_is_shared_with_composites_and_fresh_per_invocation(tmp_path, kind):
    from tests.targets.javascript.aot_fixtures import emit_fixture
    implementation = {"kind":"file", "ref":"./nodes.mjs", "export":"read"}
    leaf = {"id":"read", "definition_id":"ordinary.read", "is_terminal":True,
            "flow_kind":"terminal", "implementation":implementation}
    composite = {"id":"child", "definition_id":"ordinary.child", "is_nodeset":True,
                 "subplan":{"nodes":[leaf]}}
    if kind == "loop":
        composite.update(is_loop=True, loop={"stop_after":2})
    plan = {"nodes":[{**leaf, "id":"start"}, composite],
            "routes":[{"source":"start", "target":"child"}]}
    (tmp_path / "workflow.mjs").write_text(emit_fixture(plan).source, encoding="utf-8")
    (tmp_path / "nodes.mjs").write_text('''export function read(inputs,params,context){
globalThis.identities.push(context.workflow.self().id);return {};
}''', encoding="utf-8")
    (tmp_path / "probe.mjs").write_text('''import {runWorkflow} from './workflow.mjs';
globalThis.identities=[];
runWorkflow({});const first=identities.splice(0);
runWorkflow({});const second=identities.splice(0);
runWorkflow({},{workflowInstanceId:'registered-instance'});const registered=identities;
console.log(JSON.stringify({first,second,registered}));''', encoding="utf-8")
    result = subprocess.run(["node", str(tmp_path / "probe.mjs")], capture_output=True,
                            text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    count = 3 if kind == "loop" else 2
    assert len(values["first"]) == len(values["second"]) == count
    assert len(set(values["first"])) == len(set(values["second"])) == 1
    assert values["first"][0] != values["second"][0]
    assert values["registered"] == ["registered-instance"] * count
