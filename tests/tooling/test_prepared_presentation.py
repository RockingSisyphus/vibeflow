"""Formal presentation reuses checked facts without binding implementations."""

from collections import Counter
import json

from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.project import GraphCompiler, NodeRegistry
from vibeflow.targets.python.quality.source_context import (
    PythonSourceFile, PythonSourceNode, build_python_source_context,
)
from vibeflow.tooling.application.python.presentation.architecture_document import build_architecture_document
from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid
from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
from vibeflow.tooling.project.graph_config import parse_graph_config


def _fixture(tmp_path):
    path = tmp_path / "implementation.py"
    path.write_text("class Demo:\n    def run_pure(self, inputs, params):\n        return {}\n")
    descriptor = NodeDescriptor("demo", "Demo", "Deferred implementation", "1", "process",
        contract=NodeContractDescriptor(), rulesets=(), presentation={"fill":"#abcdef", "shape":"hex"}, node_type="vibeflow.node")
    registry = NodeRegistry()
    calls = []

    def loader():
        calls.append("bound")
        raise AssertionError("presentation must never bind a Node")

    registry.register(descriptor, loader=loader, source=str(path))
    registry.source_locations = {"demo":(path, "Demo", "app", tmp_path)}
    registry.source_root_ids = {tmp_path:"app"}
    registry.source_context_snapshot = build_python_source_context(
        (PythonSourceNode(descriptor, str(path), "Demo", "app"),),
        (PythonSourceFile.parse(str(path), "implementation", path.read_text(), root_id="app"),))

    def call(name, kind):
        return {"id":name, "definition_id":kind, "display_name":name, "description":name}

    graph = parse_graph_config({"rulesets":[], "nodeset_types":[{
        "type_key":"body", "display_name":"Body", "description":"Shared body", "requires":[], "provides":[],
        "pipeline":{"nodes":[call("inside", "demo")]},
    }], "pipeline":{"nodes":[call("first", "body"), call("second", "body"), call("one", "demo")]}},
        project_root=tmp_path, root_path=tmp_path, root_id="app", source_path=tmp_path/"workflow.jsonc")
    return graph, registry, calls


def test_standalone_registry_refreshes_stale_compiled_but_prepared_facts_stay_fixed(tmp_path):
    graph, registry, bindings = _fixture(tmp_path)
    old = GraphCompiler().compile(graph, registry=registry)
    registry.record_effect_policy("demo", "terminal")
    document = build_architecture_document(graph, compiled=old, registry=registry)
    assert document["workflow"]["nodes"][-1]["effect_scope"] == "terminal"
    prepared = prepare_python_presentation(graph, registry=registry)
    registry.record_effect_policy("demo", "none")
    document = build_architecture_document(graph, prepared=prepared)
    assert document["workflow"]["nodes"][-1]["effect_scope"] == "terminal"
    assert document["node_definitions"]["demo"]["info"]["effect_scope"] == "terminal"
    assert bindings == []


def test_architecture_uses_checked_resource_selections_after_config_changes(tmp_path, monkeypatch):
    import pytest
    from tests.fixtures.python.resource_sections.fixtures import write_project
    from vibeflow.tooling.application.python.workspace_service import load_workspace_graph_for_export
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    from vibeflow.tooling.application.python.presentation.architecture_document import build_architecture_facts
    from vibeflow.tooling.project import config_loader
    project=tmp_path/"project";write_project(project)
    config=project/"workflow.jsonc"
    raw=json.loads(config.read_text());raw["base_lib"]["modules"]=[{"id":"layout.helper","style":{"fill":"#abcdef"}}]
    config.write_text(json.dumps(raw))
    loaded=load_workspace_graph_for_export(config,workspace=load_workspace_config(project.parent/"vibeflow_config.jsonc"),
        validate_health=True,_include_presentation=True)
    assert loaded[4] is None
    prepared=loaded[-1];facts=build_architecture_facts(prepared)
    assert facts["implementation_graph"]["resources"]["base_lib:layout.helper"]["effective_presentation"]["values"]["fill"] == "#abcdef"
    with pytest.raises(TypeError):prepared.resources.resource_use.annotations[0]["selection"]["style"]["fill"]="#000000"
    monkeypatch.setattr(config_loader,"load_raw_config_document",lambda *a,**k:pytest.fail("facts reread source configuration"))
    config.write_text('{"base_lib":{"modules":[]}}')
    assert build_architecture_facts(prepared) == facts
    config.unlink()
    assert build_architecture_facts(prepared) == facts


def test_without_registry_explicit_compiled_remains_authoritative(tmp_path):
    graph, registry, _ = _fixture(tmp_path)
    compiled = GraphCompiler().compile(graph, registry=registry)
    compiled.effect_scopes["one"] = "document"
    prepared = prepare_python_presentation(graph, compiled=compiled)
    compiled.effect_scopes["one"] = "none"
    assert build_architecture_document(graph, prepared=prepared)["workflow"]["nodes"][-1]["effect_scope"] == "document"


def test_planned_run_refusal_reuses_the_checked_presentation(tmp_path, monkeypatch):
    from dataclasses import replace
    import pytest
    from vibeflow.core.findings import HealthReport
    from vibeflow.tooling.application.python import execution, preflight

    graph, registry, bindings = _fixture(tmp_path)
    graph = replace(graph, nodes=(*graph.nodes[:-1], replace(graph.nodes[-1], status="planned")))
    prepared = prepare_python_presentation(graph, registry=registry)
    written = []

    def unexpected_compile(*_args, **_kwargs):
        raise AssertionError("planned run artifacts must reuse their checked compilation")

    def artifacts(*_args, **kwargs):
        written.append(kwargs["prepared"])

    monkeypatch.setattr(GraphCompiler, "compile_with_findings", unexpected_compile)
    monkeypatch.setattr(preflight, "_write_preflight_artifacts", artifacts)
    with pytest.raises(execution.CheckedRunError) as error:
        preflight._refuse_on_planned_run(graph, HealthReport(status="PASS"), tmp_path, "planned",
            registry=registry, resources=None, runtime_options=None,
            compiled=prepared.compiled, prepared=prepared)
    assert written == [prepared] and bindings == []
    assert error.value.result.health.errors[-1].rule_id == "GRAPH.PLANNED.NODE_IN_RUN"
