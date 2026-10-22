"""Formal presentation reuses checked facts without binding implementations."""

from collections import Counter
import json

from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.project import GraphCompiler, NodeRegistry
from vibeflow.targets.python.quality.source_context import (
    PythonSourceFile, PythonSourceNode, build_python_source_context,
)
from vibeflow.tooling.application.python.presentation.architecture_document import build_architecture_document
from vibeflow.tooling.application.python.presentation.ascii_flowchart import export_ascii_flowchart
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


def test_all_renderers_share_each_graph_compilation_and_never_bind(tmp_path, monkeypatch):
    from vibeflow.tooling.application.python.presentation.mermaid import review_fragments, review_svg
    from vibeflow.tooling.presentation.mermaid.types import SvgFragment

    graph, registry, bindings = _fixture(tmp_path)
    counts = Counter()
    original = GraphCompiler.compile_with_findings

    def compile(self, graph, **kwargs):
        counts["compiles"] += 1
        return original(self, graph, **kwargs)

    def fragment(title, *_args, **_kwargs):
        return SvgFragment(title, '<svg viewBox="0 0 100 40"><rect width="100" height="40"/></svg>', 100, 40)

    monkeypatch.setattr(GraphCompiler, "compile_with_findings", compile)
    monkeypatch.setattr(review_fragments, "_render_fragment", fragment)
    prepared = prepare_python_presentation(graph, registry=registry)
    assert counts["compiles"] == 2
    document = build_architecture_document(graph, prepared=prepared)
    assert counts["compiles"] == 2  # root and one shared definition
    export_ascii_flowchart(graph, expand_nodesets=True, prepared=prepared)
    mermaid = export_mermaid(graph, expand_nodesets=True, prepared=prepared)
    review_svg.render_review_columns_svg(graph, prepared.compiled, tmp_path/"diagram.svg",
                                          expand_nodesets=True, prepared=prepared)
    assert counts["compiles"] == 2
    assert bindings == []
    assert registry._registry == {}
    assert document["node_definitions"]["demo"]["source"] == {
        "module":"implementation", "class":"Demo", "root_id":"app", "path":"implementation.py", "line":1}
    assert document["workflow"]["nodes"][-1]["presentation"]["values"]["fill"] == "#abcdef"
    assert "shape: hex" in mermaid and "fill:#abcdef" in mermaid
    document["node_definitions"]["demo"]["source"]["class"] = "Changed"
    assert build_architecture_document(graph, prepared=prepared)["node_definitions"]["demo"]["source"]["class"] == "Demo"


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
    from tests.fixtures.python.review_layout.fixtures import write_project
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


def test_deferred_sdk_source_stays_unloaded_in_formal_export(tmp_path, monkeypatch):
    from tests.targets.python.test_code_plugins import project
    from vibeflow.targets.python.project.check_session import current_python_check
    from vibeflow.tooling.application.python.workspace_service import load_workspace_graph_for_export

    marker = tmp_path / "imported"
    implementation = tmp_path / "late.py"
    implementation.write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("loaded")\n'
                              'class Demo:\n    def run_pure(self, inputs, params): return {}\n')
    workspace, config = project(tmp_path,
        'from vibeflow.targets.python.sdk import Plugin, node, SourceLocator\n'
        'late=node(id="demo",node_type="vibeflow.node",contract={},rulesets=[],source=SourceLocator("file","late.py","Demo"))\n'
        , plugin_source='from vibeflow.targets.python.sdk import Plugin\nplugin=Plugin(id="deferred",resources=[],declaration_rulesets=[])\n')
    config.write_text(json.dumps({**json.loads(config.read_text()), "rulesets":[]}))
    graph, compiled, registry, resources, error, health, prepared = load_workspace_graph_for_export(
        config, workspace=workspace, validate_health=True, _include_presentation=True)
    assert error is None and not health.errors
    assert current_python_check(registry) is None
    assert registry._registry == {} and not marker.exists()
    from vibeflow.targets.python.project import source_closure

    def unexpected_scan(*_args, **_kwargs):
        raise AssertionError("renderers must consume their prepared source records")

    monkeypatch.setattr(source_closure, "collect_python_source_facts", unexpected_scan)
    document = build_architecture_document(graph, compiled=compiled, registry=registry, prepared=prepared)
    files = document["implementation_graph"]["files"].values()
    source = next(item for item in files if item["path"] == "late.py")
    assert source["load_state"] == "not_loaded"
    assert document["node_definitions"]["demo"]["source"]["line"] == 3
    export_ascii_flowchart(graph, prepared=prepared)
    export_mermaid(graph, prepared=prepared)
    assert registry._registry == {} and not marker.exists()


def test_plugin_preflight_and_presentation_share_one_parse(tmp_path, monkeypatch):
    import ast
    from pathlib import Path
    from tests.targets.python.test_code_plugins import project
    from vibeflow.tooling.application.python.workspace_service import load_workspace_graph_for_export

    workspace, config = project(tmp_path,
        'from vibeflow.targets.python.sdk import Plugin, node\n'
        '@node(id="demo",node_type="vibeflow.node",contract={},rulesets=[])\n'
        'class Demo:\n    def run_pure(self, inputs, params): return {}\n'
        , plugin_source='from vibeflow.targets.python.sdk import Plugin\nplugin=Plugin(id="shared",resources=[],declaration_rulesets=["vibeflow.plugin_declaration"])\n')
    config.write_text(json.dumps({**json.loads(config.read_text()), "rulesets":[]}))
    parses = Counter()
    original = ast.parse

    def parse(source, filename="<unknown>", *args, **kwargs):
        if Path(filename).resolve() == tmp_path / "plugins/demo/plugin.py":
            parses["plugin"] += 1
        return original(source, filename, *args, **kwargs)

    monkeypatch.setattr(ast, "parse", parse)
    graph, _, _, _, error, _, prepared = load_workspace_graph_for_export(
        config, workspace=workspace, validate_health=True, _include_presentation=True)
    assert error is None
    assert parses["plugin"] == 1
    build_architecture_document(graph, prepared=prepared)
    export_ascii_flowchart(graph, prepared=prepared)
    export_mermaid(graph, prepared=prepared)
    assert parses["plugin"] == 1


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
