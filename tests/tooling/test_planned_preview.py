"""Planned calls retain definition facts and remain inspectable in the offline viewer."""
import json
from pathlib import Path
import subprocess

import pytest


def planned_records(root):
    from vibeflow.core.descriptors import DescriptorCatalogs, NodeDescriptor, NodeContractDescriptor
    from vibeflow.targets.python.project import NodeRegistry
    from vibeflow.tooling.project.graph_config import parse_graph_config
    from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
    from vibeflow.tooling.application.javascript.presentation.architecture import build_architecture_facts
    from vibeflow.tooling.presentation.preview.exporter import publish_preview
    from vibeflow.tooling.presentation.viewer import install_page

    descriptor = NodeDescriptor("fixture.work", "Work", "Existing implementation", "1", "process",
                                contract=NodeContractDescriptor(), rulesets=(), node_type="vibeflow.node")
    registry = NodeRegistry()
    registry.register(descriptor, loader=lambda: pytest.fail("review must not execute implementations"))
    catalogs = DescriptorCatalogs.empty()
    catalogs.nodes.register(descriptor)

    def call(name, kind="fixture.work", **fields):
        if fields.get("status") == "planned":
            fields.update(flow_kind="process", requires=[], provides=[])
        return dict(id=name, definition_id=kind, display_name=name, description="Review " + name, **fields)

    def definition(key, behavior, body=None):
        return dict(type_key=key, display_name=key, description="Draft " + key, status="planned",
                    planned_behavior=behavior, requires=[], provides=[],
                    **({"pipeline": {"nodes": body}} if body else {}))

    calls = [call("future", status="planned"), call("first", "draft.body"), call("second", "draft.body"),
             call("empty", "draft.empty"), call("loop", "vibeflow.loop.while", requires=[], provides=[],
                 loop={"body": "draft.body", "max_iterations": 1, "stop_after": 1}),
             call("override", "draft.blocking", status="planned", planned_behavior="transparent")]
    graph = parse_graph_config({"rulesets": [], "nodeset_types": [
        definition("draft.body", "transparent", [call("child", status="planned")]),
        definition("draft.empty", "blocking"), definition("draft.blocking", "blocking", [call("work")])],
        "pipeline": {"nodes": calls, "edges": [[a["id"], b["id"]] for a, b in zip(calls, calls[1:])]}},
        project_root=root, root_path=root, root_id="planned", source_path=root / "workflow.jsonc")
    prepared = prepare_python_presentation(graph, registry=registry)
    javascript = build_architecture_facts(graph, compiled=prepared.compiled,
        compiled_nodeset_types={key: prepared.graph_for(value.graph)[1] for key, value in graph.nodeset_types.items()},
        catalogs=catalogs, used_node_ids=frozenset({descriptor.id}), active_base_lib_ids=frozenset(),
        plugin_records=(),  root_id="planned", source_path="workflow.jsonc")
    records = []
    for target, architecture in (("python", prepared.architecture()), ("javascript", javascript)):
        records.append(publish_preview(root=root, category="review", status="passed", architecture=architecture,
            workflow={"id": target + ":workflow.jsonc", "root_id": "planned", "path": "workflow.jsonc", "target": target}))
    install_page(root)
    return records


def test_planned_definition_and_effective_call_behavior_match_both_targets(tmp_path):
    for record in planned_records(tmp_path):
        data = json.loads((record.directory / "snapshot.js").read_text()[len("VibeFlowPreview.snapshot("):-3])
        architecture = data["architecture"]
        calls = {node["id"]: node for node in architecture["workflow"]["nodes"]}
        for name in ("first", "second", "loop"):
            assert calls[name]["status"] == "implemented"
            assert calls[name]["invokes"]["target_status"] == "planned"
            assert calls[name]["planned_behavior"] == {"kind": "transparent"}
        assert calls["empty"]["planned_behavior"] == calls["future"]["planned_behavior"] == {"kind": "blocking"}
        assert calls["override"]["planned_behavior"] == {"kind": "transparent"}
        assert architecture["nodeset_types"]["draft.blocking"]["planned_behavior"] == {"kind": "blocking"}
        assert architecture["nodeset_types"]["draft.empty"]["body"] is None
        assert architecture["nodeset_types"]["draft.body"]["body"]["nodes"][0]["id"] == "child"


def test_planned_calls_in_real_offline_browser(tmp_path):
    from vibeflow.tooling.presentation.mermaid import is_mermaid_svg_renderer_available, _find_mmdc
    if not is_mermaid_svg_renderer_available():
        pytest.skip("locked browser toolchain supplied by the full gate")
    records = planned_records(tmp_path)
    script = Path(__file__).resolve().parents[1] / "fixtures/preview/planned.cjs"
    result = subprocess.run(["node", str(script), str(_find_mmdc().resolve()),
        str(tmp_path / "vibeflow-preview.html"), *(r.metadata["id"] for r in records)],
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["targets"] == 2 and not report["page_errors"] and not report["network_requests"]


@pytest.mark.parametrize("target", ["python","javascript"])
def test_formal_svg_dims_whole_objects_once_in_nested_planned_nodesets(tmp_path, capsys, target):
    from vibeflow.tooling.presentation.mermaid import is_mermaid_svg_renderer_available, _find_mmdc
    from vibeflow.tooling.application.cli import main
    if not is_mermaid_svg_renderer_available():
        pytest.skip("locked renderer supplied by full gate")
    if target == "python":
        from tests.targets.python.test_code_plugins import project
        source='from vibeflow.targets.python.sdk import node\n@node(id="fixture.leaf",node_type="vibeflow.node",contract={},rulesets=[])\nclass Leaf:\n    def run_pure(self,inputs,params):return {}\n'
    else:
        from tests.targets.javascript.test_code_plugins import project
        source='import {defineNode} from "@vibeflow/plugin";\nexport const leaf=defineNode({id:"fixture.leaf",node_type:"vibeflow.node",contract:{},rulesets:[],run(){return {};}});\n'
    workspace, config = project(tmp_path/"project", source)
    child={"id":"leaf","definition_id":"fixture.leaf","display_name":"Future leaf","description":"Preserve authored colors",
        "status":"planned","flow_kind":"process","requires":[],"provides":[],"style":{"fill":"#ffbbaa","stroke":"#123456","text":"#234567"}}
    inner={"id":"inner","definition_id":"draft.inner","display_name":"Inner","description":"Nested planned Nodeset"}
    def definition(name,nodes):
        return {"type_key":name,"display_name":name,"description":"Planned subtree","status":"planned","planned_behavior":"transparent",
            "requires":[],"provides":[],"rulesets":[],"pipeline":{"nodes":nodes}}
    data=json.loads(config.read_text());data["rulesets"]=[]
    (config.parent/"inner.jsonc").write_text(json.dumps(definition("draft.inner",[child])))
    outer=definition("draft.outer",[inner]);outer["nodeset_imports"]=["inner.jsonc"]
    (config.parent/"outer.jsonc").write_text(json.dumps(outer))
    data["nodeset_imports"]=["outer.jsonc"]
    data["pipeline"]={"nodes":[{"id":"outer","definition_id":"draft.outer","display_name":"Outer","description":"Planned container"}]}
    config.write_text(json.dumps(data))
    root_config=config.parent/"vibeflow_project.jsonc"
    metadata=json.loads(root_config.read_text());metadata["architecture"]={"documents":[{"workflow":"workflow.jsonc","document":"ARCHITECTURE.jsonc"}]}
    root_config.write_text(json.dumps(metadata))
    workspace_path=tmp_path/"vibeflow_config.jsonc"
    workspace_path.write_text(json.dumps({"roots":[{"id":"project","path":"project"}]}))
    output=tmp_path/"planned.svg"
    assert main(["review","--workspace",str(workspace_path),"--config",str(config),"--output",str(output)])==0, capsys.readouterr().out
    script=Path(__file__).resolve().parents[1]/"fixtures/preview/planned-svg.cjs"
    result=subprocess.run(["node",str(script),str(_find_mmdc().resolve()),str(output)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
