"""Canonical facts and both Mermaid renderers share native and call styles."""

from types import SimpleNamespace

from vibeflow.core.descriptors import DescriptorCatalogs, NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.project import GraphCompiler, NodeRegistry
from vibeflow.tooling.application.javascript.presentation.architecture import _javascript_graph_document
from vibeflow.tooling.application.javascript.presentation.diagrams import render_mermaid
from vibeflow.tooling.application.python.presentation.architecture_document import build_architecture_document
from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid
from vibeflow.tooling.project.graph_config import parse_graph_config


class Empty:
    def run_pure(self, inputs, params):
        return {}


def test_external_composite_loop_and_planned_styles_match_canonical_facts():
    descriptor = NodeDescriptor("external", "External", "External block", "1.0", "process",
                                external=True, rulesets=(), contract=NodeContractDescriptor())
    registry = NodeRegistry()
    registry.register(descriptor, Empty)
    catalogs = DescriptorCatalogs.empty()
    catalogs.nodes.register(descriptor)

    def call(name, type_used, **extra):
        return {"id": name, "type_used": type_used, "display_name": name.title(),
                "description": name, **extra}

    graph = parse_graph_config({"rulesets": [], "nodesets": [
        {"type_key": "body", "display_name": "Body", "description": "Body", "requires": [], "provides": [],
         "pipeline": {"nodes": [call("step", "external")]}},
        {"type_key": "design", "display_name": "Design", "description": "Design", "status": "planned", "requires": [], "provides": []},
    ], "pipeline": {"nodes": [call("external", "external"),
        call("loop", "vibeflow.loop.while", requires=[], provides=[], loop={"body": "body", "stop_after": 1, "max_iterations": 2}),
        call("block", "body"), call("future", "design"),
    ]}})
    compiled = GraphCompiler().compile(graph, registry=registry)
    document = build_architecture_document(graph, compiled=compiled, registry=registry)
    python = document["workflow"]
    javascript = _javascript_graph_document(graph, compiled, source={}, graph_lock_scope="graph", catalogs=catalogs)
    python_nodes = {item["id"]: item["presentation"] for item in python["nodes"]}
    javascript_nodes = {item["id"]: item["presentation"] for item in javascript["nodes"]}
    assert python_nodes == javascript_nodes
    assert python_nodes["loop"]["values"]["shape"] == "trap-b"
    assert python_nodes["future"]["sources"]["fill"] == "status"
    assert python_nodes["external"]["values"]["fill"] != python_nodes["block"]["values"]["fill"]
    assert python["rulesets"] == javascript["rulesets"] == []
    assert document["nodesets"]["body"]["effect_scope"] == "unconstrained"
    assert document["nodesets"]["body"]["rulesets"] is None
    assert document["nodesets"]["design"]["effect_scope"] == "unavailable"
    assert document["node_types"]["vibeflow.loop.while"]["info"]["effect_scope"] == "unconstrained"
    assert {item["id"]: item["effect_scope"] for item in python["nodes"]} == {item["id"]: item["effect_scope"] for item in javascript["nodes"]}
    python_mermaid = export_mermaid(graph, compiled=compiled, registry=registry)
    javascript_mermaid = render_mermaid(SimpleNamespace(graph=graph, compiled=compiled, catalogs=catalogs))
    for name, presentation in python_nodes.items():
        style = "fill:{fill},stroke:{stroke},color:{text}".format(**presentation["values"])
        assert f"style {name} {style};" in python_mermaid
        assert f"style vf_{name} {style};" in javascript_mermaid
    assert 'shape: trap-b' in python_mermaid
    assert 'shape: trap-b' in javascript_mermaid
    assert 'effect_scope: unavailable' in python_mermaid
    assert 'effect_scope: unavailable' in javascript_mermaid
