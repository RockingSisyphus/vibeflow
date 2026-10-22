"""Canonical facts and both Mermaid renderers share native and call styles."""

from types import SimpleNamespace
import pytest

from vibeflow.core.descriptors import DescriptorCatalogs, NodeContractDescriptor, NodeDescriptor
from vibeflow.core.descriptors.models import CapabilityRequirementDescriptor
from vibeflow.targets.python.project import GraphCompiler, NodeRegistry
from vibeflow.tooling.architecture.workflow import graph_document
from vibeflow.tooling.application.javascript.presentation.diagrams import render_mermaid
from vibeflow.tooling.application.python.presentation.architecture_document import build_architecture_document
from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid
from vibeflow.tooling.project.graph_config import parse_graph_config


class Empty:
    def run_pure(self, inputs, params):
        return {}


@pytest.mark.parametrize("primary,color", [("call", "#fef3c7"), ("send", "#e0f2fe"),
    ("receive", "#1e3a8a"), ("kill", "#ffe4e6")])
def test_coordination_helpers_preserve_primary_shape_and_color_in_both_targets(primary, color):
    descriptor = NodeDescriptor("operation", "Operation", "Coordinate work", "1.0", "workflow-io",
        node_type="vibeflow.node", rulesets=(), contract=NodeContractDescriptor(),
        capabilities=(CapabilityRequirementDescriptor("vibeflow.workflow", (primary, "wait")),))
    registry = NodeRegistry()
    registry.register(descriptor, Empty)
    catalogs = DescriptorCatalogs.empty()
    catalogs.nodes.register(descriptor)
    graph = parse_graph_config({"rulesets": [], "pipeline": {"nodes": [
        {"id": "coordinate", "definition_id": "operation", "display_name": "Coordinate", "description": "Coordinate work"},
        {"id": "custom", "definition_id": "operation", "display_name": "Custom", "description": "Author styled call",
         "style": {"shape": "diamond", "fill": "#123456"}},
    ]}})
    compiled = GraphCompiler().compile(graph, registry=registry)
    document = build_architecture_document(graph, compiled=compiled, registry=registry)
    rows = {row["id"]: row for row in document["workflow"]["nodes"]}
    assert rows["coordinate"]["presentation"]["values"]["shape"] == "notch-rect"
    assert rows["coordinate"]["presentation"]["values"]["fill"] == color
    assert rows["custom"]["presentation"]["values"]["shape"] == "diamond"
    assert rows["custom"]["presentation"]["values"]["fill"] == "#123456"
    for text in (export_mermaid(graph, compiled=compiled, registry=registry),
                 render_mermaid(SimpleNamespace(graph=graph, compiled=compiled, catalogs=catalogs))):
        assert "shape: notch-rect" in text
        assert "fill:" + color in text


def test_external_composite_loop_and_planned_styles_match_canonical_facts():
    descriptor = NodeDescriptor("external", "External", "External block", "1.0", "process",
                                external=True, rulesets=(), contract=NodeContractDescriptor(), node_type="vibeflow.node")
    registry = NodeRegistry()
    registry.register(descriptor, Empty)
    catalogs = DescriptorCatalogs.empty()
    catalogs.nodes.register(descriptor)

    def call(name, definition_id, **extra):
        return {"id": name, "definition_id": definition_id, "display_name": name.title(),
                "description": name, **extra}

    graph = parse_graph_config({"rulesets": [], "nodeset_types": [
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
    javascript = graph_document(graph, compiled, source={}, graph_lock_scope="graph", descriptor=catalogs.nodes.get)
    python_nodes = {item["id"]: item["presentation"] for item in python["nodes"]}
    javascript_nodes = {item["id"]: item["presentation"] for item in javascript["nodes"]}
    assert python_nodes == javascript_nodes
    assert python_nodes["loop"]["values"]["shape"] == "trap-b"
    assert python_nodes["future"]["sources"]["fill"] == "native"
    assert python_nodes["future"]["modifiers"]["planned"] is True
    assert python_nodes["external"]["values"]["fill"] != python_nodes["block"]["values"]["fill"]
    assert python["rulesets"] == javascript["rulesets"] == []
    assert document["nodeset_types"]["body"]["effect_scope"] == "unconstrained"
    assert document["nodeset_types"]["body"]["rulesets"] is None
    assert document["nodeset_types"]["design"]["effect_scope"] == "unavailable"
    assert document["node_definitions"]["vibeflow.loop.while"]["info"]["effect_scope"] == "unconstrained"
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
